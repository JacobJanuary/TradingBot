"""
Aged Position Monitor V2 - MINIMAL implementation
Works through UnifiedPriceMonitor
Does NOT replace existing aged_position_manager.py until tested
"""

import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timezone
from utils.datetime_helpers import now_utc, ensure_utc
from decimal import Decimal
from dataclasses import dataclass
import os
from core.order_executor import OrderExecutor, OrderResult

# Phase 4 import - added for metrics, does not modify existing code
try:
    from core.aged_position_metrics import AgedPositionMetrics, MetricsCollector
except ImportError:
    AgedPositionMetrics = None
    MetricsCollector = None

# Phase 5 import - added for events, does not modify existing code
try:
    from core.aged_position_events import (
        AgedPositionEventEmitter,
        AgedEventFactory,
        EventOrchestrator,
        AgedEventType
    )
except ImportError:
    AgedPositionEventEmitter = None
    AgedEventFactory = None
    EventOrchestrator = None
    AgedEventType = None

logger = logging.getLogger(__name__)


@dataclass
class AgedPositionTarget:
    """Simple target tracking for aged position"""
    symbol: str
    entry_price: Decimal
    target_price: Decimal
    phase: str  # 'grace', 'progressive', 'emergency'
    loss_tolerance: Decimal
    hours_aged: float
    position_id: str


class AgedPositionMonitorV2:
    """
    MINIMAL V2 implementation for aged positions
    Uses MARKET orders instead of LIMIT
    Integrates with UnifiedPriceMonitor
    """

    def __init__(self, exchange_managers, repository, position_manager=None, config=None):
        self.exchanges = exchange_managers
        self.repository = repository
        self.position_manager = position_manager

        # Configuration from env/config
        # Phase 2: Use config instead of os.getenv() with defaults
        if config is None:
            from config.settings import config as global_config
            config = global_config.trading

        self.max_age_hours = config.max_position_age_hours
        self.grace_period_hours = config.aged_grace_period_hours
        self.loss_step_percent = config.aged_loss_step_percent
        self.max_loss_percent = config.aged_max_loss_percent
        # Note: config.commission_percent is already in percent, divide by 100
        self.commission_percent = config.commission_percent / Decimal('100')

        # Tracked aged positions
        self.aged_targets: Dict[str, AgedPositionTarget] = {}

        # Initialize robust order executor
        self.order_executor = OrderExecutor(exchange_managers, repository)

        # Simple stats
        self.stats = {
            'positions_monitored': 0,
            'market_closes_triggered': 0,
            'grace_closes': 0,
            'progressive_closes': 0,
            'ghost_positions_detected': 0,
            'ghost_positions_handled': 0,
            'position_validation_failures': 0,
            'quantity_mismatches': 0,
        }

        logger.info(
            f"AgedPositionMonitorV2 initialized: "
            f"max_age={self.max_age_hours}h, grace={self.grace_period_hours}h"
        )

        # Phase 4: Initialize metrics (optional, does not affect existing code)
        self.metrics = None
        self.metrics_collector = None
        if AgedPositionMetrics:
            try:
                self.metrics = AgedPositionMetrics()
                self.metrics_collector = MetricsCollector(self.metrics, self)
                logger.info("Metrics initialized for aged positions")
            except Exception as e:
                logger.warning(f"Metrics initialization failed (non-critical): {e}")

        # Phase 5: Initialize events (optional, does not affect existing code)
        self.event_emitter = None
        self.event_factory = None
        self.event_orchestrator = None
        if AgedPositionEventEmitter:
            try:
                # Try to get EventRouter from position_manager if available
                event_router = None
                if position_manager and hasattr(position_manager, 'event_router'):
                    event_router = position_manager.event_router

                self.event_emitter = AgedPositionEventEmitter(event_router)
                self.event_factory = AgedEventFactory()
                self.event_orchestrator = EventOrchestrator(self.event_emitter)
                logger.info("Events initialized for aged positions")
            except Exception as e:
                logger.warning(f"Events initialization failed (non-critical): {e}")

    async def _validate_position_on_exchange(self, position) -> tuple:
        """
        Validate position exists on exchange and get current quantity.

        Args:
            position: Position object from database

        Returns:
            tuple: (exists: bool, quantity: float, error_msg: str)
                exists=True if position found on exchange
                quantity=actual quantity from exchange (0 if not found)
                error_msg=error description if validation failed
        """
        symbol = position.symbol
        exchange_name = position.exchange

        try:
            # Get exchange manager
            exchange = self.position_manager.exchange_managers.get(exchange_name)
            if not exchange:
                error_msg = f"Exchange {exchange_name} not found in managers"
                logger.error(f"❌ {symbol}: {error_msg}")
                return (False, 0.0, error_msg)

            # Fetch positions from exchange
            try:
                positions = await exchange.exchange.fetch_positions([symbol])
            except Exception as fetch_error:
                # If fetch fails, log but don't block close attempt
                error_msg = f"Failed to fetch positions: {fetch_error}"
                logger.warning(f"⚠️ {symbol}: {error_msg}")
                # Return None to indicate "unknown" state
                return (None, 0.0, error_msg)

            # Find active position (non-zero contracts)
            active_position = None
            for p in positions:
                contracts = float(p.get('contracts', 0))
                if contracts != 0:
                    active_position = p
                    break

            if not active_position:
                # Position NOT found on exchange
                logger.warning(
                    f"🔍 {symbol}: Position NOT FOUND on exchange "
                    f"(DB shows {position.quantity}, but exchange shows 0)"
                )
                return (False, 0.0, "Position not found on exchange")

            # Position exists, get quantity
            exchange_qty = abs(float(active_position.get('contracts', 0)))
            db_qty = abs(float(position.quantity))

            # Check quantity mismatch
            qty_diff = abs(exchange_qty - db_qty)
            if qty_diff > 0.01:  # Allow 0.01 difference for rounding
                logger.warning(
                    f"⚠️ {symbol}: Quantity MISMATCH detected!\n"
                    f"   Exchange: {exchange_qty}\n"
                    f"   Database: {db_qty}\n"
                    f"   Difference: {qty_diff}\n"
                    f"   → Will use EXCHANGE quantity for close"
                )
                self.stats['quantity_mismatches'] = self.stats.get('quantity_mismatches', 0) + 1
            else:
                logger.debug(
                    f"✅ {symbol}: Position validated on exchange "
                    f"(qty={exchange_qty})"
                )

            return (True, exchange_qty, "")

        except Exception as e:
            error_msg = f"Unexpected error during validation: {e}"
            logger.error(
                f"❌ {symbol}: {error_msg}",
                exc_info=True
            )
            self.stats['position_validation_failures'] = self.stats.get('position_validation_failures', 0) + 1
            # Return None to indicate "unknown" state
            return (None, 0.0, error_msg)

    async def _mark_position_as_ghost(self, position, reason: str = "ghost_detected_aged_close"):
        """
        Mark position as closed in database (ghost position cleanup).

        Args:
            position: Position object from database
            reason: Reason for ghost detection
        """
        symbol = position.symbol

        try:
            # Close position in database
            await self.repository.close_position(
                position_id=position.id,
                exit_price=position.entry_price,  # Use entry as exit (unknown actual)
                exit_reason=reason,
                realized_pnl=Decimal('0')  # Unknown actual PnL
            )

            logger.info(
                f"✅ {symbol}: Ghost position closed in database\n"
                f"   Position ID: {position.id}\n"
                f"   Entry price: {position.entry_price}\n"
                f"   Reason: {reason}"
            )

            # Update statistics
            if hasattr(self, 'stats'):
                if 'ghost_positions_detected' not in self.stats:
                    self.stats['ghost_positions_detected'] = 0
                self.stats['ghost_positions_detected'] += 1

            # Remove from aged_targets if present
            if symbol in self.aged_targets:
                del self.aged_targets[symbol]
                logger.debug(f"🗑️ {symbol}: Removed from aged_targets")

            # Emit event
            from core.event_logger import event_logger
            await event_logger.log_event(
                'aged_ghost_position_detected',
                {
                    'symbol': symbol,
                    'exchange': position.exchange,
                    'position_id': position.id,
                    'entry_price': float(position.entry_price),
                    'quantity': float(position.quantity),
                    'reason': reason
                }
            )

        except Exception as e:
            logger.error(
                f"❌ {symbol}: Failed to mark ghost position in database: {e}",
                exc_info=True
            )
            raise  # Re-raise to caller

    async def check_position_age(self, position) -> bool:
        """Check if position qualifies as aged"""

        # Skip if trailing stop is active
        if hasattr(position, 'trailing_activated') and position.trailing_activated:
            return False

        # Calculate age
        age_hours = self._calculate_age_hours(position)

        # Check if aged
        return age_hours > self.max_age_hours

    async def add_aged_position(self, position):
        """Add position to aged monitoring"""

        symbol = position.symbol

        if symbol in self.aged_targets:
            return  # Already monitoring

        age_hours = self._calculate_age_hours(position)
        hours_over_limit = age_hours - self.max_age_hours

        # Determine phase and target
        phase, target_price, loss_tolerance = self._calculate_target(
            position,
            hours_over_limit
        )

        # Create target tracking
        target = AgedPositionTarget(
            symbol=symbol,
            entry_price=Decimal(str(position.entry_price)),
            target_price=target_price,
            phase=phase,
            loss_tolerance=loss_tolerance,
            hours_aged=age_hours,
            position_id=str(getattr(position, 'id', symbol))
        )

        self.aged_targets[symbol] = target
        self.stats['positions_monitored'] += 1

        # Database tracking - create aged position entry
        if self.repository:
            # ✅ CRITICAL FIX: Only track in DB if position has real database ID
            # Pre-registered positions (id="pending") are skipped until they get real ID
            if not isinstance(target.position_id, int):
                logger.debug(
                    f"⏳ {symbol}: Skipping DB tracking - position pending database creation "
                    f"(id={target.position_id}). Will track after position is persisted."
                )
                # Target is still tracked in memory (self.aged_targets[symbol])
                # It will be added to DB later when position gets real ID
            else:
                # Position has real database ID - safe to create aged_position
                try:
                    await self.repository.create_aged_position(
                        position_id=str(target.position_id),
                        symbol=symbol,
                        exchange=position.exchange,
                        entry_price=target.entry_price,
                        target_price=target_price,
                        phase=phase,
                        age_hours=age_hours,
                        loss_tolerance=loss_tolerance
                    )
                    logger.debug(f"✅ {symbol}: Aged position tracked in DB (position_id={target.position_id})")
                except Exception as e:
                    logger.error(f"Failed to create aged position in DB for {symbol}: {e}")

        logger.info(
            f"📍 Aged position added: {symbol} "
            f"(age={age_hours:.1f}h, phase={phase}, target=${target_price:.4f})"
        )

    def is_position_tracked(self, symbol: str) -> bool:
        """Check if position is already being tracked

        Used for instant detection to avoid duplicates
        """
        return symbol in self.aged_targets

    def get_tracked_positions(self) -> List[str]:
        """Get list of currently tracked aged positions"""
        return list(self.aged_targets.keys())

    def get_tracking_stats(self) -> Dict:
        """Get statistics about aged position tracking"""
        stats = {
            'total_tracked': len(self.aged_targets),
            'by_phase': {},
            'oldest_age_hours': 0
        }

        for symbol, target in self.aged_targets.items():
            phase = target.phase
            stats['by_phase'][phase] = stats['by_phase'].get(phase, 0) + 1

            if hasattr(target, 'hours_aged'):
                stats['oldest_age_hours'] = max(stats['oldest_age_hours'], target.hours_aged)

        return stats

    async def check_price_target(self, symbol: str, current_price: Decimal):
        """
        Check if current price reached target for aged position
        Called by UnifiedPriceMonitor through adapter
        """

        if symbol not in self.aged_targets:
            return

        target = self.aged_targets[symbol]

        # Check if target reached based on position side
        should_close = False

        # Get position to check side
        position = await self._get_position(symbol)
        if not position:
            del self.aged_targets[symbol]
            return

        # Check profitability first
        pnl_percent = self._calculate_pnl_percent(position, current_price)

        # Check for phase update
        await self._update_phase_if_needed(position, target)

        # Log monitoring event to database
        if self.repository:
            try:
                await self.repository.create_aged_monitoring_event(
                    aged_position_id=target.position_id,
                    event_type='price_check',
                    market_price=current_price,
                    target_price=target.target_price,
                    price_distance_percent=abs((current_price - target.target_price) / target.target_price * Decimal('100')),
                    event_metadata={
                        'pnl_percent': str(pnl_percent),
                        'phase': target.phase
                    }
                )
            except Exception as e:
                logger.error(f"Failed to log monitoring event: {e}")

        if pnl_percent > Decimal('0'):
            # Profitable - close immediately
            should_close = True
            logger.info(f"💰 {symbol} profitable at {pnl_percent:.2f}% - triggering close")

        else:
            # Check target based on side
            if position.side in ['long', 'buy']:
                # LONG: close if price >= target (accepting loss)
                should_close = current_price >= target.target_price
            else:
                # SHORT: close if price <= target
                should_close = current_price <= target.target_price

        if should_close:
            logger.info(
                f"🎯 Aged target reached for {symbol}: "
                f"current=${current_price:.4f} vs target=${target.target_price:.4f}"
            )

            # Trigger market close
            await self._trigger_market_close(position, target, current_price)

            # Remove from monitoring
            del self.aged_targets[symbol]

    async def _trigger_market_close(self, position, target, trigger_price):
        """Execute robust close order for aged position using OrderExecutor"""

        symbol = position.symbol
        exchange_name = position.exchange

        logger.info(
            f"📤 Triggering robust close for aged {symbol}: "
            f"phase={target.phase}"
        )

        # === NEW: VALIDATE POSITION EXISTS ON EXCHANGE ===
        exists, exchange_qty, error_msg = await self._validate_position_on_exchange(position)

        if exists is False:
            # Position confirmed NOT FOUND on exchange - GHOST POSITION
            logger.warning(
                f"⚠️ {symbol}: GHOST POSITION detected! "
                f"Position exists in DB but NOT on exchange. "
                f"Marking as closed in database (no exchange close needed)."
            )

            try:
                await self._mark_position_as_ghost(position, "ghost_detected_aged_close")

                # Update statistics
                self.stats['ghost_positions_handled'] = self.stats.get('ghost_positions_handled', 0) + 1

                logger.info(
                    f"✅ {symbol}: Ghost position handled successfully "
                    f"(closed in DB, no exchange action taken)"
                )

                # Remove from monitoring
                if symbol in self.aged_targets:
                    del self.aged_targets[symbol]

                return  # EXIT - don't attempt close on exchange

            except Exception as ghost_error:
                logger.error(
                    f"❌ {symbol}: Failed to handle ghost position: {ghost_error}",
                    exc_info=True
                )
                # Continue to attempt close (fallback behavior)

        elif exists is None:
            # Validation FAILED (API error, timeout, etc.)
            logger.warning(
                f"⚠️ {symbol}: Position validation FAILED: {error_msg}\n"
                f"   → Proceeding with close attempt using DB values (fallback mode)"
            )
            amount = abs(float(position.quantity))

        else:
            # Position EXISTS on exchange (exists=True)
            logger.info(
                f"✅ {symbol}: Position validated on exchange (qty={exchange_qty})"
            )
            amount = exchange_qty

        # === END NEW CODE ===

        # Use OrderExecutor for robust execution
        try:
            result = await self.order_executor.execute_close(
                symbol=symbol,
                exchange_name=exchange_name,
                position_side=position.side,
                amount=amount,
                reason=f'aged_{target.phase}'
            )
        except Exception as e:
            # Unexpected exception from execute_close
            logger.error(
                f"❌ CRITICAL: Unexpected error in execute_close for {symbol}: {e}",
                exc_info=True
            )
            # Create OrderResult manually for error handling below
            result = OrderResult(
                success=False,
                error_message=f"Unexpected exception: {str(e)}",
                attempts=0,
                execution_time=0.0,
                order_id=None,
                executed_amount=Decimal('0'),
                order_type='unknown',
                price=None
            )

        if result.success:
            # Update statistics
            self.stats['market_closes_triggered'] += 1

            if target.phase == 'grace':
                self.stats['grace_closes'] += 1
            else:
                self.stats['progressive_closes'] += 1

            logger.info(
                f"✅ Aged position {symbol} closed: "
                f"order_id={result.order_id}, type={result.order_type}, "
                f"attempts={result.attempts}, phase={target.phase}"
            )

            # Update database - mark aged position as closed
            if self.repository:
                try:
                    # Mark aged position as closed
                    await self.repository.mark_aged_position_closed(
                        position_id=str(target.position_id),
                        close_reason=f'aged_{target.phase}'
                    )

                    # Update main position record
                    await self.repository.update_position(
                        position.id,
                        status='closed',
                        exit_reason=f'aged_{target.phase}'
                    )

                    # Log successful close event with execution details
                    await self.repository.create_aged_monitoring_event(
                        aged_position_id=target.position_id,
                        event_type='closed',
                        event_metadata={
                            'order_id': result.order_id,
                            'order_type': result.order_type,
                            'close_price': str(result.price if result.price else trigger_price),
                            'phase': target.phase,
                            'attempts': result.attempts,
                            'execution_time': result.execution_time
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to update DB: {e}")

        else:
            # Order execution failed
            logger.error(
                f"❌ Failed to close aged position {symbol} after {result.attempts} attempts: "
                f"{result.error_message}"
            )

            # Mark as failed in database
            if self.repository:
                try:
                    await self.repository.create_aged_monitoring_event(
                        aged_position_id=target.position_id,
                        event_type='close_failed',
                        event_metadata={
                            'error': result.error_message,
                            'attempts': result.attempts,
                            'execution_time': result.execution_time
                        }
                    )
                except Exception as db_err:
                    logger.error(f"Failed to log error in DB: {db_err}")

            # ✅ ENHANCEMENT #1E: Специальная обработка ошибок Bybit

            # Check for specific error types
            error_msg = result.error_message or ""

            if '170193' in error_msg or 'price cannot be' in error_msg.lower():
                # Bybit price validation error
                logger.warning(
                    f"⚠️ Bybit price error for {symbol} - may need manual intervention. "
                    f"Error: {error_msg[:100]}"
                )
                # Mark position as requiring manual review
                if self.repository:
                    try:
                        await self.repository.create_aged_monitoring_event(
                            aged_position_id=target.position_id,
                            event_type='requires_manual_review',
                            event_metadata={
                                'error_code': '170193',
                                'error_message': error_msg,
                                'reason': 'bybit_price_validation'
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to log manual review event: {e}")

            elif 'no asks' in error_msg.lower() or 'no bids' in error_msg.lower():
                # No liquidity in order book
                logger.warning(
                    f"⚠️ No liquidity for {symbol} - market order failed. "
                    f"Position may need manual close or wait for liquidity."
                )
                if self.repository:
                    try:
                        await self.repository.create_aged_monitoring_event(
                            aged_position_id=target.position_id,
                            event_type='low_liquidity',
                            event_metadata={
                                'error_message': error_msg,
                                'order_attempts': result.attempts
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to log low liquidity event: {e}")

            elif '170003' in error_msg:
                # Bybit brokerId error
                logger.error(
                    f"⚠️ Bybit brokerId error for {symbol}. "
                    f"This should be fixed by exchange_manager brokerId='' patch."
                )

    def _calculate_target(self, position, hours_over_limit: float):
        """Calculate target price and phase for aged position"""

        entry_price = Decimal(str(position.entry_price))

        # Check phase
        if hours_over_limit <= self.grace_period_hours:
            # GRACE PERIOD - try breakeven
            phase = 'grace'
            loss_tolerance = Decimal('0')

            # Breakeven = entry + commission
            double_commission = Decimal('2') * self.commission_percent

            if position.side in ['long', 'buy']:
                target_price = entry_price * (Decimal('1') + double_commission)
            else:
                target_price = entry_price * (Decimal('1') - double_commission)

        else:
            # PROGRESSIVE LIQUIDATION
            phase = 'progressive'
            hours_in_progressive = hours_over_limit - self.grace_period_hours

            # Calculate loss tolerance (convert float to Decimal)
            loss_tolerance = Decimal(str(hours_in_progressive)) * self.loss_step_percent

            # Cap at max loss
            loss_tolerance = min(loss_tolerance, self.max_loss_percent)

            # Calculate target with loss
            if position.side in ['long', 'buy']:
                target_price = entry_price * (Decimal('1') - loss_tolerance / Decimal('100'))
            else:
                target_price = entry_price * (Decimal('1') + loss_tolerance / Decimal('100'))

        return phase, target_price, loss_tolerance

    def _calculate_age_hours(self, position) -> float:
        """
        Calculate position age in hours.

        After UTC migration, all timestamps from DB are timezone-aware (timestamptz).
        Uses ensure_utc() to handle any edge cases.
        """
        if not hasattr(position, 'opened_at'):
            return 0.0

        now = now_utc()
        opened_at = ensure_utc(position.opened_at)

        age = now - opened_at
        return age.total_seconds() / 3600

    def _calculate_pnl_percent(self, position, current_price: Decimal) -> Decimal:
        """Calculate current PnL percentage"""

        entry_price = Decimal(str(position.entry_price))

        if position.side in ['long', 'buy']:
            pnl = ((current_price - entry_price) / entry_price) * Decimal('100')
        else:
            pnl = ((entry_price - current_price) / entry_price) * Decimal('100')

        return pnl

    async def _update_phase_if_needed(self, position, target: AgedPositionTarget):
        """Check and update phase if position aged further"""

        current_age_hours = self._calculate_age_hours(position)
        hours_over_limit = current_age_hours - self.max_age_hours

        # Calculate new phase
        new_phase, new_target_price, new_loss_tolerance = self._calculate_target(
            position, hours_over_limit
        )

        # Check if phase changed
        if new_phase != target.phase:
            old_phase = target.phase
            target.phase = new_phase
            target.target_price = new_target_price
            target.loss_tolerance = new_loss_tolerance
            target.hours_aged = current_age_hours

            logger.info(
                f"📈 Phase transition for {position.symbol}: "
                f"{old_phase} → {new_phase} (age={current_age_hours:.1f}h)"
            )

            # Update database
            if self.repository:
                try:
                    await self.repository.update_aged_position(
                        position_id=target.position_id,
                        phase=new_phase,
                        target_price=new_target_price,
                        loss_tolerance=new_loss_tolerance
                    )

                    # Log phase change event
                    await self.repository.create_aged_monitoring_event(
                        aged_position_id=target.position_id,
                        event_type='phase_change',
                        event_metadata={
                            'old_phase': old_phase,
                            'new_phase': new_phase,
                            'age_hours': current_age_hours
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to update phase in DB: {e}")

    async def _get_position(self, symbol: str):
        """Get position from position manager"""
        if self.position_manager and hasattr(self.position_manager, 'positions'):
            return self.position_manager.positions.get(symbol)
        return None

    def get_stats(self) -> Dict:
        """Get statistics"""
        return {
            'monitored': len(self.aged_targets),
            'total_processed': self.stats['positions_monitored'],
            'market_closes': self.stats['market_closes_triggered'],
            'grace_closes': self.stats['grace_closes'],
            'progressive_closes': self.stats['progressive_closes']
        }

    # ============================================================
    # PHASE 3: Recovery & Persistence Methods
    # Added for crash recovery - DO NOT modify existing methods!
    # ============================================================

    async def persist_state(self) -> bool:
        """
        Persist current aged_targets to database
        Called periodically or before shutdown
        """
        if not self.repository:
            return False

        try:
            # Save each tracked target to DB
            for symbol, target in self.aged_targets.items():
                await self.repository.update_aged_position(
                    position_id=target.position_id,
                    phase=target.phase,
                    target_price=target.target_price,
                    loss_tolerance=target.loss_tolerance,
                    hours_aged=target.hours_aged
                )

            logger.info(f"Persisted {len(self.aged_targets)} aged targets to DB")
            return True

        except Exception as e:
            logger.error(f"Failed to persist aged targets: {e}")
            return False

    async def recover_state(self) -> int:
        """
        Recover aged_targets from database on startup
        Returns number of recovered positions
        """
        if not self.repository:
            return 0

        try:
            # Get active aged positions from DB
            active_positions = await self.repository.get_active_aged_positions()

            recovered_count = 0
            for db_record in active_positions:
                # Reconstruct target from DB
                target = AgedPositionTarget(
                    symbol=db_record['symbol'],
                    entry_price=Decimal(str(db_record['entry_price'])),
                    target_price=Decimal(str(db_record['target_price'])),
                    phase=db_record['phase'],
                    loss_tolerance=Decimal(str(db_record['loss_tolerance'])),
                    hours_aged=float(db_record.get('age_hours', 0)),
                    position_id=db_record['position_id']
                )

                # Verify position still exists
                if self.position_manager:
                    position = self.position_manager.positions.get(db_record['symbol'])
                    if position:
                        self.aged_targets[db_record['symbol']] = target
                        recovered_count += 1
                        logger.info(f"Recovered aged position: {db_record['symbol']}")
                    else:
                        # Position no longer exists, mark as stale in DB
                        await self.repository.update_aged_position(
                            position_id=db_record['position_id'],
                            phase='stale'
                        )

            logger.info(f"Recovery complete: {recovered_count} aged positions restored")
            return recovered_count

        except Exception as e:
            logger.error(f"Failed to recover aged positions: {e}")
            return 0

    async def cleanup_stale_records(self) -> int:
        """
        Clean up stale aged position records
        Called periodically to maintain DB hygiene
        """
        if not self.repository:
            return 0

        try:
            # Get all active aged records
            active_records = await self.repository.get_active_aged_positions()
            cleaned_count = 0

            for record in active_records:
                # Check if position still exists
                if self.position_manager:
                    position = self.position_manager.positions.get(record['symbol'])
                    if not position:
                        # Mark as stale
                        await self.repository.update_aged_position(
                            position_id=record['position_id'],
                            phase='stale'
                        )
                        cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned {cleaned_count} stale aged position records")

            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup stale records: {e}")
            return 0

    # ============================================================
    # PHASE 4: Metrics Methods
    # Added for monitoring - DO NOT modify existing methods!
    # ============================================================

    async def update_metrics(self):
        """Update Prometheus metrics - called periodically"""
        if self.metrics and self.metrics_collector:
            try:
                await self.metrics_collector.update_metrics()
            except Exception as e:
                logger.debug(f"Metrics update failed (non-critical): {e}")

    def record_detection_metrics(self, position):
        """Record metrics when aged position detected"""
        if self.metrics:
            try:
                age_hours = self._calculate_age_hours(position)
                hours_over_limit = age_hours - self.max_age_hours
                phase, _, _ = self._calculate_target(position, hours_over_limit)
                self.metrics.record_detection(position.exchange, phase)
            except Exception as e:
                logger.debug(f"Failed to record detection metrics: {e}")

    def record_close_metrics(self, position, target, result):
        """Record metrics when position closed"""
        if self.metrics and result:
            try:
                age_hours = self._calculate_age_hours(position)
                pnl_percent = float(self._calculate_pnl_percent(
                    position,
                    Decimal(str(position.current_price))
                ))

                if result.success:
                    self.metrics.record_close_success(
                        exchange=position.exchange,
                        phase=target.phase,
                        order_type=result.order_type,
                        execution_time=result.execution_time,
                        attempts=result.attempts,
                        age_hours=age_hours,
                        pnl_percent=pnl_percent
                    )
                else:
                    self.metrics.record_close_failure(
                        position.exchange,
                        result.error_message or "unknown"
                    )
            except Exception as e:
                logger.debug(f"Failed to record close metrics: {e}")

    def record_phase_transition_metrics(self, old_phase: str, new_phase: str):
        """Record metrics for phase transition"""
        if self.metrics:
            try:
                self.metrics.record_phase_transition(old_phase, new_phase)
            except Exception as e:
                logger.debug(f"Failed to record phase transition metrics: {e}")

    # ============================================================
    # PHASE 5: Event Methods
    # Added for event-driven architecture - DO NOT modify existing methods!
    # ============================================================

    async def emit_detection_event(self, position, phase: str):
        """Emit event when aged position detected"""
        if self.event_emitter and self.event_factory:
            try:
                event = self.event_factory.create_detection_event(position, phase)
                await self.event_emitter.emit(event)
            except Exception as e:
                logger.debug(f"Failed to emit detection event: {e}")

    async def emit_phase_change_event(
        self,
        position_id: str,
        symbol: str,
        exchange: str,
        old_phase: str,
        new_phase: str,
        age_hours: float
    ):
        """Emit event when phase changes"""
        if self.event_emitter and self.event_factory:
            try:
                event = self.event_factory.create_phase_change_event(
                    position_id, symbol, exchange, old_phase, new_phase, age_hours
                )
                await self.event_emitter.emit(event)
            except Exception as e:
                logger.debug(f"Failed to emit phase change event: {e}")

    async def emit_close_event(self, position, target, result):
        """Emit event when position close attempted"""
        if self.event_emitter and self.event_factory:
            try:
                if result.success:
                    event = self.event_factory.create_close_success_event(
                        position,
                        target.phase,
                        result.order_id,
                        result.order_type,
                        result.execution_time,
                        result.attempts
                    )
                else:
                    event = self.event_factory.create_close_failed_event(
                        position,
                        target.phase,
                        result.error_message,
                        result.attempts
                    )
                await self.event_emitter.emit(event)
            except Exception as e:
                logger.debug(f"Failed to emit close event: {e}")

    def add_event_listener(self, event_type, callback):
        """Add external event listener"""
        if self.event_emitter and AgedEventType:
            try:
                # Convert string to enum if needed
                if isinstance(event_type, str):
                    event_type = AgedEventType[event_type]
                self.event_emitter.add_listener(event_type, callback)
            except Exception as e:
                logger.debug(f"Failed to add event listener: {e}")

    def add_webhook(self, url: str):
        """Add webhook for event notifications"""
        if self.event_emitter:
            try:
                self.event_emitter.add_webhook(url)
            except Exception as e:
                logger.debug(f"Failed to add webhook: {e}")

    def get_event_stats(self) -> Dict:
        """Get event statistics"""
        if self.event_emitter:
            return self.event_emitter.get_stats()
        return {}

    # ============================================================
    # CRITICAL FIX: Periodic Full Scan
    # Defense in depth - don't rely solely on price update triggers
    # ============================================================

    async def periodic_full_scan(self):
        """
        Periodically scan all active positions for aged detection
        Independent of price updates - provides additional safety layer

        This catches positions that might be missed by instant detection
        (e.g., positions created before bot restart)
        """
        if not self.position_manager:
            return

        scanned_count = 0
        detected_count = 0

        try:
            for symbol, position in self.position_manager.positions.items():
                scanned_count += 1

                # Skip if already tracked
                if symbol in self.aged_targets:
                    continue

                # Skip if trailing stop is active
                if hasattr(position, 'trailing_activated') and position.trailing_activated:
                    continue

                # Check age
                age_hours = self._calculate_age_hours(position)

                if age_hours > self.max_age_hours:
                    try:
                        await self.add_aged_position(position)
                        detected_count += 1

                        logger.info(
                            f"🔍 Periodic scan detected aged position: {symbol} "
                            f"(age={age_hours:.1f}h, already aged for {age_hours - self.max_age_hours:.1f}h)"
                        )

                    except Exception as e:
                        logger.error(f"Failed to add aged position {symbol} during periodic scan: {e}")

            if detected_count > 0:
                logger.info(
                    f"🔍 Periodic aged scan complete: scanned {scanned_count} positions, "
                    f"detected {detected_count} new aged position(s)"
                )

        except Exception as e:
            logger.error(f"Periodic aged scan failed: {e}")

    async def verify_subscriptions(self, aged_adapter):
        """
        ✅ FIX #5: Verify that all aged positions have active subscriptions
        Re-subscribe if missing
        """
        if not aged_adapter:
            return 0

        resubscribed_count = 0

        for symbol in list(self.aged_targets.keys()):
            if symbol not in aged_adapter.monitoring_positions:
                logger.warning(f"⚠️ Subscription missing for {symbol}! Re-subscribing...")

                if self.position_manager and symbol in self.position_manager.positions:
                    position = self.position_manager.positions[symbol]
                    await aged_adapter.add_aged_position(position)
                    resubscribed_count += 1
                    logger.info(f"✅ Re-subscribed {symbol}")

        if resubscribed_count > 0:
            logger.warning(f"⚠️ Re-subscribed {resubscribed_count} position(s)")

        return resubscribed_count

    async def check_websocket_health(self) -> dict:
        """
        ✅ ENHANCEMENT #2D: Check WebSocket health for aged positions

        Returns:
            dict: Health report with stale symbols
        """
        if not hasattr(self, 'price_monitor') or not self.price_monitor:
            logger.warning("Price monitor not available for health check")
            return {'healthy': False, 'reason': 'no_price_monitor'}

        # Get aged symbols
        aged_symbols = list(self.aged_targets.keys())

        if not aged_symbols:
            return {'healthy': True, 'aged_count': 0}

        # Check staleness
        staleness_report = await self.price_monitor.check_staleness(aged_symbols)

        stale_symbols = [
            symbol for symbol, data in staleness_report.items()
            if data['stale']
        ]

        health_report = {
            'healthy': len(stale_symbols) == 0,
            'aged_count': len(aged_symbols),
            'stale_count': len(stale_symbols),
            'stale_symbols': stale_symbols,
            'staleness_details': staleness_report
        }

        if stale_symbols:
            logger.warning(
                f"⚠️ {len(stale_symbols)} aged positions have stale WebSocket prices: "
                f"{', '.join(stale_symbols)}"
            )

        return health_report

    async def _periodic_position_validation_task(self):
        """
        Background task: Periodically validate aged positions exist on exchange.
        Runs every 5 minutes.
        """
        logger.info("🔄 Starting periodic aged position validation task (interval: 5 min)")

        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes

                # Get current aged positions
                aged_symbols = list(self.aged_targets.keys())

                if not aged_symbols:
                    logger.debug("No aged positions to validate")
                    continue

                logger.info(
                    f"🔍 Running periodic validation for {len(aged_symbols)} aged positions"
                )

                ghosts_detected = 0
                validation_errors = 0

                for symbol in aged_symbols:
                    try:
                        # Get position from position_manager
                        position = self.position_manager.positions.get(symbol)
                        if not position:
                            logger.debug(f"⚠️ {symbol}: Not found in position_manager (already closed?)")
                            # Remove from aged_targets
                            if symbol in self.aged_targets:
                                del self.aged_targets[symbol]
                            continue

                        # Validate position on exchange
                        exists, exchange_qty, error_msg = await self._validate_position_on_exchange(position)

                        if exists is False:
                            # GHOST DETECTED
                            logger.warning(
                                f"🔍 Periodic validation: GHOST POSITION detected for {symbol}!\n"
                                f"   Aged position exists in DB but NOT on exchange.\n"
                                f"   Cleaning up immediately."
                            )

                            await self._mark_position_as_ghost(
                                position,
                                reason="ghost_detected_periodic_validation"
                            )

                            ghosts_detected += 1

                        elif exists is None:
                            # Validation failed
                            logger.debug(
                                f"⚠️ {symbol}: Periodic validation failed: {error_msg}"
                            )
                            validation_errors += 1

                        else:
                            # Position valid
                            logger.debug(f"✅ {symbol}: Validated (qty={exchange_qty})")

                    except Exception as symbol_error:
                        logger.error(
                            f"❌ {symbol}: Error during periodic validation: {symbol_error}",
                            exc_info=True
                        )
                        validation_errors += 1

                # Log summary
                if ghosts_detected > 0 or validation_errors > 0:
                    logger.info(
                        f"🔍 Periodic validation complete: "
                        f"{len(aged_symbols)} checked, "
                        f"{ghosts_detected} ghosts detected, "
                        f"{validation_errors} validation errors"
                    )

            except Exception as e:
                logger.error(
                    f"❌ Error in periodic aged position validation task: {e}",
                    exc_info=True
                )
                # Continue running despite errors

    async def start(self):
        """Start the aged position monitor"""
        logger.info("🔄 Starting AgedPositionMonitor...")

        # Start periodic validation task
        self.validation_task = asyncio.create_task(self._periodic_position_validation_task())

        logger.info("✅ AgedPositionMonitor started (validation task running)")

    async def stop(self):
        """Stop the aged position monitor"""
        # Stop validation task
        if hasattr(self, 'validation_task') and self.validation_task:
            self.validation_task.cancel()
            try:
                await self.validation_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ AgedPositionMonitor stopped (validation task cancelled)")