"""
Aged Position Manager - Progressive liquidation strategy for aged positions
Manages position lifecycle with grace period and gradual liquidation based on age

LOGIC:
1. Age 0-MAX_POSITION_AGE_HOURS: Normal position, no action
2. Age MAX_POSITION_AGE to +AGED_GRACE_PERIOD_HOURS: Breakeven attempts (grace period)
3. Age beyond grace period: Progressive liquidation with increasing loss tolerance
4. Emergency market close for extremely old positions
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import asyncio
import os

logger = logging.getLogger(__name__)


class AgedPositionManager:
    """
    Manager for closing aged positions with progressive liquidation strategy

    CRITICAL:
    - NO balance checks
    - NO duplicate orders
    - ONE limit exit order per position (update existing)
    - Stop Loss remains active independently
    """

    def __init__(self, config, position_manager, exchanges):
        self.config = config
        self.position_manager = position_manager
        self.exchanges = exchanges  # Dict of exchange instances

        # Age parameters from environment/config
        self.max_position_age_hours = float(os.getenv('MAX_POSITION_AGE_HOURS',
                                                      getattr(config, 'max_position_age_hours', 3)))
        self.grace_period_hours = float(os.getenv('AGED_GRACE_PERIOD_HOURS', 8))
        self.loss_step_percent = float(os.getenv('AGED_LOSS_STEP_PERCENT', 0.5))
        self.max_loss_percent = float(os.getenv('AGED_MAX_LOSS_PERCENT', 10.0))
        self.acceleration_factor = float(os.getenv('AGED_ACCELERATION_FACTOR', 1.2))
        self.commission_percent = float(os.getenv('COMMISSION_PERCENT',
                                               getattr(config, 'commission_percent', 0.1))) / 100

        # Track managed positions to avoid duplicate processing
        self.managed_positions = {}  # position_id: {'last_update': datetime, 'order_id': str}

        # 🔒 CRITICAL: Locks for preventing duplicate exit order creation (same as SL locks)
        self._exit_order_locks: Dict[str, asyncio.Lock] = {}  # {symbol: Lock}
        self._exit_order_locks_lock = asyncio.Lock()  # Meta-lock for creating locks safely

        # Statistics
        self.stats = {
            'positions_checked': 0,
            'aged_positions': 0,
            'grace_period_positions': 0,
            'progressive_positions': 0,
            'emergency_closes': 0,
            'orders_updated': 0,
            'orders_created': 0,
            'breakeven_closes': 0,
            'gradual_liquidations': 0
        }

        logger.info(
            f"🎯 Aged Position Manager initialized:\n"
            f"  • Max age: {self.max_position_age_hours}h\n"
            f"  • Grace period: {self.grace_period_hours}h\n"
            f"  • Loss step: {self.loss_step_percent}% per hour\n"
            f"  • Max loss: {self.max_loss_percent}%\n"
            f"  • Acceleration: ×{self.acceleration_factor} after 10h\n"
            f"  • Commission: {self.commission_percent*100:.2f}%"
        )

    async def check_and_process_aged_positions(self) -> int:
        """
        Main method to check and process aged positions
        Returns number of aged positions processed
        """
        try:
            # Get all active positions
            positions = []
            for symbol, position in self.position_manager.positions.items():
                if position and hasattr(position, 'opened_at'):
                    positions.append(position)

            if not positions:
                return 0

            self.stats['positions_checked'] += len(positions)
            aged_positions = []

            current_time = datetime.now(timezone.utc)

            for position in positions:
                if position.opened_at:
                    # Calculate age in hours with proper timezone handling
                    if hasattr(position.opened_at, 'tzinfo') and position.opened_at.tzinfo:
                        # position.opened_at is timezone-aware
                        position_age = current_time - position.opened_at
                    else:
                        # position.opened_at is naive - assume UTC and make timezone-aware
                        opened_at_utc = position.opened_at.replace(tzinfo=timezone.utc)
                        position_age = current_time - opened_at_utc

                    age_hours = position_age.total_seconds() / 3600

                    # Check if position is aged (beyond MAX_POSITION_AGE_HOURS)
                    if age_hours >= self.max_position_age_hours:
                        position.age_hours = age_hours
                        aged_positions.append(position)

                        logger.warning(
                            f"⏰ Found aged position {position.symbol}: "
                            f"age={age_hours:.1f}h (max={self.max_position_age_hours}h), "
                            f"pnl={position.unrealized_pnl:.2f} USD"
                        )

            if aged_positions:
                self.stats['aged_positions'] += len(aged_positions)
                logger.info(f"📊 Processing {len(aged_positions)} aged positions")

                # Process each aged position
                for position in aged_positions:
                    await self.process_aged_position(position)

            return len(aged_positions)

        except Exception as e:
            logger.error(f"Error checking aged positions: {e}", exc_info=True)
            return 0

    async def process_aged_position(self, position):
        """
        Process a single aged position based on age

        PHASES:
        1. Grace period (0-AGED_GRACE_PERIOD_HOURS after max age): Breakeven
        2. Progressive (after grace period): Increasing loss tolerance
        3. Emergency (extremely old): Market price
        """
        try:
            age_hours = position.age_hours
            symbol = position.symbol

            # CRITICAL: Verify position exists on exchange before any operations
            position_exists = await self.position_manager.verify_position_exists(symbol, position.exchange)
            if not position_exists:
                logger.warning(f"🗑️ Position {symbol} not found on {position.exchange} - marking as phantom")
                # Position doesn't exist on exchange - close it in database
                await self.position_manager.repository.close_position(
                    position.id,
                    close_price=position.current_price or position.entry_price,
                    pnl=0,
                    pnl_percentage=0,
                    reason='PHANTOM_AGED'
                )
                # Remove from position manager's memory
                if symbol in self.position_manager.positions:
                    del self.position_manager.positions[symbol]
                return

            # Get current market price
            current_price = await self._get_current_price(symbol, position.exchange)
            if not current_price:
                logger.error(f"Could not get price for {symbol}")
                return

            position.current_price = current_price

            # Calculate hours over limit
            hours_over_limit = age_hours - self.max_position_age_hours

            # Determine phase and calculate target price
            phase, target_price, loss_percent = self._calculate_target_price(
                position, hours_over_limit, current_price
            )

            logger.info(
                f"📈 Processing aged position {symbol}:\n"
                f"  • Age: {age_hours:.1f}h total ({hours_over_limit:.1f}h over limit)\n"
                f"  • Phase: {phase}\n"
                f"  • Side: {position.side}\n"
                f"  • Entry: ${position.entry_price:.4f}\n"
                f"  • Current: ${current_price:.4f}\n"
                f"  • Target: ${target_price:.4f}\n"
                f"  • Loss tolerance: {loss_percent:.2f}%"
            )

            # Update statistics
            if 'GRACE' in phase:
                self.stats['grace_period_positions'] += 1
            elif 'PROGRESSIVE' in phase:
                self.stats['progressive_positions'] += 1
            elif 'EMERGENCY' in phase:
                self.stats['emergency_closes'] += 1

            # Update or create limit exit order
            await self._update_single_exit_order(position, target_price, phase)

        except Exception as e:
            logger.error(f"Error processing aged position {position.symbol}: {e}", exc_info=True)

    def _calculate_target_price(self, position, hours_over_limit: float, current_price: float) -> Tuple[str, float, float]:
        """
        Calculate target price based on position age

        Returns:
            Tuple of (phase_name, target_price, loss_percent)
        """
        entry_price = float(position.entry_price)

        if hours_over_limit <= self.grace_period_hours:
            # PHASE 1: GRACE PERIOD - Strict breakeven
            # Breakeven = entry + double commission
            double_commission = 2 * self.commission_percent

            if position.side in ['long', 'buy']:
                target_price = entry_price * (1 + double_commission)
            else:  # short/sell
                target_price = entry_price * (1 - double_commission)

            phase = f"GRACE_PERIOD_BREAKEVEN ({hours_over_limit:.1f}/{self.grace_period_hours}h)"
            loss_percent = 0.0

        elif hours_over_limit <= self.grace_period_hours + 20:
            # PHASE 2: PROGRESSIVE LIQUIDATION
            hours_after_grace = hours_over_limit - self.grace_period_hours

            # Base loss calculation
            loss_percent = hours_after_grace * self.loss_step_percent

            # Acceleration after 10 hours in progression
            if hours_after_grace > 10:
                extra_hours = hours_after_grace - 10
                acceleration_loss = extra_hours * self.loss_step_percent * (self.acceleration_factor - 1)
                loss_percent += acceleration_loss

            # Cap at maximum loss
            loss_percent = min(loss_percent, self.max_loss_percent)

            # Calculate target price with loss
            if position.side in ['long', 'buy']:
                target_price = entry_price * (1 - loss_percent / 100)
            else:  # short/sell
                target_price = entry_price * (1 + loss_percent / 100)

            phase = f"PROGRESSIVE_LIQUIDATION (loss: {loss_percent:.1f}%)"

        else:
            # PHASE 3: EMERGENCY - Use current market price
            target_price = current_price
            phase = "EMERGENCY_MARKET_CLOSE"

            # Calculate actual loss for logging
            if position.side in ['long', 'buy']:
                loss_percent = ((entry_price - current_price) / entry_price) * 100
            else:
                loss_percent = ((current_price - entry_price) / entry_price) * 100

        return phase, target_price, loss_percent

    async def _update_single_exit_order(self, position, target_price: float, phase: str):
        """
        Update or create a SINGLE limit exit order for the position

        CRITICAL:
        - Check for existing order first
        - Cancel old order before creating new one
        - Use EnhancedExchangeManager for duplicate prevention
        - 🔒 USE LOCK to prevent race condition (same as SL)
        """
        # 🔒 CRITICAL: Acquire meta-lock to safely get/create per-symbol lock
        async with self._exit_order_locks_lock:
            if position.symbol not in self._exit_order_locks:
                self._exit_order_locks[position.symbol] = asyncio.Lock()
            symbol_lock = self._exit_order_locks[position.symbol]

        # 🔒 CRITICAL: Hold lock for ENTIRE order creation/update process
        async with symbol_lock:
            logger.debug(f"🔒 Acquired exit order lock for {position.symbol}")
            
            try:
                position_id = f"{position.symbol}_{position.exchange}"

                # Get exchange
                exchange = self.exchanges.get(position.exchange)
                if not exchange:
                    logger.error(f"Exchange {position.exchange} not available")
                    logger.debug(f"🔓 Released exit order lock for {position.symbol} (no exchange)")
                    return

                # Determine order side (opposite of position)
                order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

                # Try to use enhanced manager for better order management
                try:
                    from core.exchange_manager_enhanced import EnhancedExchangeManager

                    # Create enhanced manager
                    enhanced_manager = EnhancedExchangeManager(exchange.exchange)

                    # Check for existing exit order
                    existing = await enhanced_manager._check_existing_exit_order(
                        position.symbol, order_side
                    )

                    if existing:
                        # Check if price needs update
                        existing_price = float(existing.get('price', 0))
                        price_diff_pct = abs(target_price - existing_price) / existing_price * 100

                        if price_diff_pct > 0.5:  # Update if > 0.5% difference
                            logger.info(
                                f"📊 Updating exit order for {position.symbol}:\n"
                                f"  Old price: ${existing_price:.4f}\n"
                                f"  New price: ${target_price:.4f}\n"
                                f"  Difference: {price_diff_pct:.1f}%\n"
                                f"  Phase: {phase}"
                            )

                            # Cancel old order
                            try:
                                await enhanced_manager.safe_cancel_with_verification(
                                    existing['id'], position.symbol
                                )
                            except Exception as e:
                                logger.warning(f"Could not cancel old order: {e}")

                            # Wait for cancellation to process
                            await asyncio.sleep(0.2)

                            # Create new order with updated price
                            order = await enhanced_manager.create_limit_exit_order(
                                symbol=position.symbol,
                                side=order_side,
                                amount=abs(float(position.quantity)),
                                price=target_price,
                                check_duplicates=True
                            )

                            if order:
                                self.managed_positions[position_id] = {
                                    'last_update': datetime.now(),
                                    'order_id': order['id'],
                                    'phase': phase
                                }
                                self.stats['orders_updated'] += 1
                        else:
                            logger.debug(
                                f"Exit order price acceptable (diff {price_diff_pct:.1f}% < 0.5%), "
                                f"keeping existing order at ${existing_price:.4f}"
                            )
                    else:
                        # No existing order, create new one
                        logger.info(
                            f"📝 Creating initial exit order for {position.symbol}:\n"
                            f"  Price: ${target_price:.4f}\n"
                            f"  Phase: {phase}"
                        )

                        order = await enhanced_manager.create_limit_exit_order(
                            symbol=position.symbol,
                            side=order_side,
                            amount=abs(float(position.quantity)),
                            price=target_price,
                            check_duplicates=True
                        )

                        if order:
                            self.managed_positions[position_id] = {
                                'last_update': datetime.now(),
                                'order_id': order['id'],
                                'phase': phase
                            }
                            self.stats['orders_created'] += 1

                except ImportError:
                    # Fallback to standard method if enhanced manager not available
                    logger.warning("Enhanced ExchangeManager not available, using standard method")

                    # Get all open orders for the symbol
                    orders = await exchange.fetch_open_orders(position.symbol)

                    # Find existing limit exit order
                    existing_order = None
                    for order in orders:
                        if (order.get('type') == 'limit' and
                            order.get('side') == order_side and
                            order.get('reduceOnly') == True):
                            # Check it's not a stop loss
                            info = order.get('info', {})
                            if not info.get('stopOrderType'):
                                existing_order = order
                                break

                    if existing_order:
                        # Check if price needs update
                        existing_price = float(existing_order.get('price', 0))
                        price_diff_pct = abs(target_price - existing_price) / existing_price * 100

                        if price_diff_pct > 0.5:
                            # Cancel old order
                            try:
                                await exchange.cancel_order(existing_order['id'], position.symbol)
                                logger.info(f"Cancelled old order {existing_order['id'][:12]}...")
                                await asyncio.sleep(0.2)
                            except Exception as e:
                                logger.warning(f"Could not cancel order: {e}")

                    # Create new order
                    params = {
                        'reduceOnly': True,
                        'timeInForce': 'GTC'
                    }

                    if exchange.id == 'bybit':
                        params['positionIdx'] = 0

                    order = await exchange.create_order(
                        symbol=position.symbol,
                        type='limit',
                        side=order_side,
                        amount=abs(float(position.quantity)),
                        price=target_price,
                        params=params
                    )

                    if order:
                        self.managed_positions[position_id] = {
                            'last_update': datetime.now(),
                            'order_id': order['id'],
                            'phase': phase
                        }
                        logger.info(
                            f"✅ Placed limit order for {position.symbol}: "
                            f"{order_side} @ ${target_price:.4f}"
                        )

            except Exception as e:
                logger.error(f"Error updating exit order: {e}", exc_info=True)
            finally:
                logger.debug(f"🔓 Released exit order lock for {position.symbol}")

    async def _get_current_price(self, symbol: str, exchange_name: str) -> Optional[float]:
        """
        Get current market price for symbol
        """
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                return None

            ticker = await exchange.fetch_ticker(symbol)
            return float(ticker['last'])

        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None

    def get_statistics(self) -> Dict:
        """
        Get manager statistics
        """
        return {
            'positions_checked': self.stats['positions_checked'],
            'aged_positions': self.stats['aged_positions'],
            'grace_period': self.stats['grace_period_positions'],
            'progressive': self.stats['progressive_positions'],
            'emergency_closes': self.stats['emergency_closes'],
            'orders_updated': self.stats['orders_updated'],
            'orders_created': self.stats['orders_created'],
            'managed_positions': len(self.managed_positions),
            'breakeven_closes': self.stats.get('breakeven_closes', 0),
            'gradual_liquidations': self.stats.get('gradual_liquidations', 0)
        }

    async def cleanup(self):
        """
        Cleanup method for graceful shutdown
        """
        logger.info("Aged Position Manager shutting down...")
        logger.info(f"Final statistics: {self.get_statistics()}")