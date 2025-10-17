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
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import asyncio
import os
import ccxt

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
        # Use int for age hours to be compatible with Decimal arithmetic
        self.max_position_age_hours = int(os.getenv('MAX_POSITION_AGE_HOURS',
                                                     getattr(config, 'max_position_age_hours', 3)))
        self.grace_period_hours = int(os.getenv('AGED_GRACE_PERIOD_HOURS', 8))
        # Use Decimal for all calculations to avoid float/Decimal type errors
        self.loss_step_percent = Decimal(str(os.getenv('AGED_LOSS_STEP_PERCENT', 0.5)))
        self.max_loss_percent = Decimal(str(os.getenv('AGED_MAX_LOSS_PERCENT', 10.0)))
        self.acceleration_factor = Decimal(str(os.getenv('AGED_ACCELERATION_FACTOR', 1.2)))
        self.commission_percent = Decimal(str(os.getenv('COMMISSION_PERCENT',
                                               getattr(config, 'commission_percent', 0.1)))) / 100

        # Track managed positions to avoid duplicate processing
        self.managed_positions = {}  # position_id: {'last_update': datetime, 'order_id': str}

        # Statistics
        self.stats = {
            'positions_checked': 0,
            'aged_positions': 0,
            'grace_period_positions': 0,
            'progressive_positions': 0,
            'emergency_closes': 0,
            'orders_updated': 0,
            'orders_created': 0,
            'orders_failed': 0,
            'market_orders_created': 0,
            'market_orders_failed': 0,
            'limit_orders_created': 0,
            'profit_closes': 0,
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

    def _apply_price_precision(self, price: float, symbol: str, exchange_name: str) -> float:
        """Apply exchange price precision to avoid rounding errors"""
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                return price

            markets = exchange.exchange.markets
            if symbol not in markets:
                return price

            market = markets[symbol]
            precision = market.get('precision', {}).get('price')

            if precision and precision > 0:
                from math import log10
                decimals = int(-log10(precision))
                return round(price, decimals)

            return price
        except Exception as e:
            logger.warning(f"Could not apply price precision for {symbol}: {e}")
            return price

    def _calculate_current_pnl_percent(
        self,
        side: str,
        entry_price: Decimal,
        current_price: Decimal
    ) -> Decimal:
        """
        Calculate current PnL percentage

        Args:
            side: 'long', 'buy', 'short', or 'sell'
            entry_price: Entry price
            current_price: Current market price

        Returns:
            PnL in percent (positive = profit, negative = loss)
        """
        if side in ['long', 'buy']:
            # LONG: profit when current > entry
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
        else:  # short/sell
            # SHORT: profit when current < entry
            pnl_percent = ((entry_price - current_price) / entry_price) * 100

        return pnl_percent

    def _validate_limit_price(
        self,
        side: str,
        target_price: float,
        current_price: float,
        buffer_pct: float = 0.1
    ) -> bool:
        """
        Validate if LIMIT order can be placed at target price

        Args:
            side: 'buy' or 'sell'
            target_price: Desired order price
            current_price: Current market price
            buffer_pct: Buffer in percent (default 0.1%)

        Returns:
            True if LIMIT order is valid, False otherwise
        """
        if side == 'buy':
            # BUY LIMIT must be BELOW market
            max_allowed = current_price * (1 - buffer_pct / 100)
            return target_price <= max_allowed
        else:  # sell
            # SELL LIMIT must be ABOVE market
            min_allowed = current_price * (1 + buffer_pct / 100)
            return target_price >= min_allowed

    async def _create_market_exit_order(
        self,
        exchange,
        symbol: str,
        side: str,
        amount: float,
        reason: str = "MARKET_CLOSE"
    ) -> Optional[Dict]:
        """
        Create MARKET order for immediate position closure

        Args:
            exchange: Exchange object
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Position quantity
            reason: Closure reason (for logging)

        Returns:
            Order dict if successful, None otherwise
        """
        try:
            # CRITICAL FIX: Ensure futures symbol format for Bybit
            # Bot only trades futures, so always use futures format
            if exchange.exchange.id == 'bybit' and ':' not in symbol:
                if symbol.endswith('USDT'):
                    base = symbol[:-4]
                    symbol = f"{base}/USDT:USDT"
                logger.info(f"🔄 Converted to futures format: {symbol}")

            logger.info(f"📤 MARKET {reason}: {side} {amount} {symbol}")

            params = {
                'reduceOnly': True
            }

            if exchange.exchange.id == 'bybit':
                params['positionIdx'] = 0

            order = await exchange.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=amount,
                params=params
            )

            if order:
                logger.info(f"✅ MARKET order executed: {order['id']}")
                self.stats['market_orders_created'] = self.stats.get('market_orders_created', 0) + 1
                return order

        except Exception as e:
            logger.error(f"❌ MARKET order failed for {symbol}: {e}")
            self.stats['market_orders_failed'] = self.stats.get('market_orders_failed', 0) + 1
            return None

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

                    age_hours = Decimal(str(position_age.total_seconds() / 3600))

                    # Check if position is aged (beyond MAX_POSITION_AGE_HOURS)
                    if age_hours >= self.max_position_age_hours:
                        position.age_hours = age_hours
                        aged_positions.append(position)

                        # Calculate PnL value for formatting
                        pnl_value = float(position.unrealized_pnl) if position.unrealized_pnl is not None else 0.0

                        logger.warning(
                            f"⏰ Found aged position {position.symbol}: "
                            f"age={age_hours:.1f}h (max={self.max_position_age_hours}h), "
                            f"pnl={pnl_value:.2f} USD"
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

            # Determine phase, calculate target price and determine order type
            phase, target_price, loss_percent, order_type = self._calculate_target_price(
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
                f"  • Loss tolerance: {loss_percent:.2f}%\n"
                f"  • Order type: {order_type}"
            )

            # Update statistics
            if 'GRACE' in phase:
                self.stats['grace_period_positions'] += 1
            elif 'PROGRESSIVE' in phase:
                self.stats['progressive_positions'] += 1
            elif 'EMERGENCY' in phase:
                self.stats['emergency_closes'] += 1

            # Update or create exit order with correct type
            await self._update_single_exit_order(position, target_price, phase, order_type)

        except ccxt.ExchangeError as e:
            error_msg = str(e)
            # Handle geographic restrictions
            if '170209' in error_msg or 'China region' in error_msg:
                logger.error(
                    f"⛔ {position.symbol} not available in this region - "
                    f"skipping aged position management for 24h"
                )
                # Mark to skip for 24h
                position_id = f"{position.symbol}_{position.exchange}"
                self.managed_positions[position_id] = {
                    'last_update': datetime.now(),
                    'order_id': None,
                    'phase': 'SKIPPED_GEO_RESTRICTED',
                    'skip_until': datetime.now() + timedelta(days=1)
                }
            # Handle invalid price errors
            elif '170193' in error_msg or 'price cannot be' in error_msg.lower():
                logger.warning(
                    f"⚠️ Invalid price for {position.symbol}: {error_msg[:100]}"
                )
            else:
                # Re-raise other exchange errors
                raise

        except Exception as e:
            logger.error(f"Error processing aged position {position.symbol}: {e}", exc_info=True)

    def _calculate_target_price(self, position, hours_over_limit: float, current_price: float) -> Tuple[str, float, float, str]:
        """
        Calculate target price based on position age and determine order type

        Returns:
            Tuple of (phase_name, target_price, loss_percent, order_type)
        """
        # Convert to Decimal for consistent arithmetic
        entry_price = Decimal(str(position.entry_price))
        current_price_decimal = Decimal(str(current_price))

        # STEP 1: CHECK PROFITABILITY (NEW - PRIORITY)
        current_pnl_percent = self._calculate_current_pnl_percent(
            position.side,
            entry_price,
            current_price_decimal
        )

        if current_pnl_percent > 0:
            # POSITION IN PROFIT - CLOSE IMMEDIATELY WITH MARKET ORDER
            logger.info(
                f"💰 {position.symbol} in profit {current_pnl_percent:.2f}% "
                f"(age {hours_over_limit:.1f}h) - MARKET close"
            )
            return (
                f"IMMEDIATE_PROFIT_CLOSE (PnL: +{current_pnl_percent:.2f}%)",
                current_price_decimal,
                Decimal('0'),
                'MARKET'
            )

        # STEP 2: CALCULATE BY PHASES (for PnL <= 0%)
        if hours_over_limit <= self.grace_period_hours:
            # PHASE 1: GRACE PERIOD - Strict breakeven
            # Breakeven = entry + double commission
            double_commission = 2 * self.commission_percent

            if position.side in ['long', 'buy']:
                target_price = entry_price * (1 + double_commission)
            else:  # short/sell
                target_price = entry_price * (1 - double_commission)

            phase = f"GRACE_PERIOD_BREAKEVEN ({hours_over_limit:.1f}/{self.grace_period_hours}h)"
            loss_percent = Decimal('0')

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
            # PHASE 3: EMERGENCY - Use current market price, ALWAYS MARKET ORDER
            target_price = current_price_decimal
            phase = "EMERGENCY_MARKET_CLOSE"

            # Calculate actual loss for logging
            if position.side in ['long', 'buy']:
                loss_percent = ((entry_price - current_price_decimal) / entry_price) * 100
            else:
                loss_percent = ((current_price_decimal - entry_price) / entry_price) * 100

            # EMERGENCY always uses MARKET
            return (phase, target_price, loss_percent, 'MARKET')

        # STEP 3: VALIDATE LIMIT FOR GRACE AND PROGRESSIVE
        order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

        can_use_limit = self._validate_limit_price(
            side=order_side,
            target_price=float(target_price),
            current_price=float(current_price_decimal),
            buffer_pct=0.1
        )

        if can_use_limit:
            order_type = 'LIMIT'
        else:
            logger.warning(
                f"⚠️ LIMIT impossible for {position.symbol} "
                f"(target=${target_price:.4f}, market=${current_price:.4f}) "
                f"- using MARKET"
            )
            order_type = 'MARKET'
            target_price = current_price_decimal  # Update to market price

        return (phase, target_price, loss_percent, order_type)

    async def _update_single_exit_order(self, position, target_price: float, phase: str, order_type: str):
        """
        Update or create exit order with correct order type (LIMIT or MARKET)

        Args:
            position: Position object
            target_price: Target price
            phase: Current phase
            order_type: 'LIMIT' or 'MARKET'

        CRITICAL:
        - Check for existing order first
        - Cancel old order before creating new one
        - Use EnhancedExchangeManager for duplicate prevention
        """
        try:
            position_id = f"{position.symbol}_{position.exchange}"

            # Get exchange
            exchange = self.exchanges.get(position.exchange)
            if not exchange:
                logger.error(f"Exchange {position.exchange} not available")
                return

            # Determine order side (opposite of position)
            order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

            # NEW: Choose between MARKET and LIMIT
            if order_type == 'MARKET':
                # Use MARKET order for immediate execution
                order = await self._create_market_exit_order(
                    exchange=exchange,
                    symbol=position.symbol,
                    side=order_side,
                    amount=abs(float(position.quantity)),
                    reason=phase
                )

                if order:
                    self.managed_positions[position_id] = {
                        'last_update': datetime.now(),
                        'order_id': order['id'],
                        'phase': phase,
                        'order_type': 'MARKET'
                    }
                    logger.info(f"✅ MARKET close: {position.symbol} in phase {phase}")
                    if 'PROFIT' in phase:
                        self.stats['profit_closes'] = self.stats.get('profit_closes', 0) + 1

                return

            # LIMIT order path (existing logic)
            # Apply price precision to avoid rounding errors
            precise_price = self._apply_price_precision(
                float(target_price),
                position.symbol,
                position.exchange
            )

            # FIXED: Use unified method to prevent order proliferation
            try:
                from core.exchange_manager_enhanced import EnhancedExchangeManager

                # Create enhanced manager
                enhanced_manager = EnhancedExchangeManager(exchange.exchange)

                # Use unified method - handles all duplicate logic internally
                order = await enhanced_manager.create_or_update_exit_order(
                    symbol=position.symbol,
                    side=order_side,
                    amount=abs(float(position.quantity)),
                    price=precise_price,
                    min_price_diff_pct=0.5
                )

                if order:
                    self.managed_positions[position_id] = {
                        'last_update': datetime.now(),
                        'order_id': order['id'],
                        'phase': phase,
                        'order_type': 'LIMIT'
                    }
                    # Update statistics based on whether order was updated or created
                    if order.get('_was_updated'):
                        self.stats['orders_updated'] += 1
                    else:
                        self.stats['orders_created'] += 1
                    self.stats['limit_orders_created'] = self.stats.get('limit_orders_created', 0) + 1

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
                    price=precise_price,
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

    async def _get_current_price(self, symbol: str, exchange_name: str) -> Optional[float]:
        """
        Get current market price for symbol
        """
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                return None

            ticker = await exchange.fetch_ticker(symbol, use_cache=False)
            if ticker is None:
                logger.warning(f"Could not get price for {symbol}")
                return None
            price = float(ticker['last'])

            # Check for invalid price
            if price == 0:
                logger.warning(f"Price for {symbol} is 0, skipping aged position update")
                return None

            return price

        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None

    async def _get_total_balance(self) -> float:
        """
        Get total account balance in USD
        Note: Not used in new logic but kept for compatibility
        """
        try:
            total_balance = 0.0

            for exchange_name, exchange in self.exchanges.items():
                try:
                    balance = await exchange.fetch_balance()

                    # Get USDT balance (main trading currency)
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    total_balance += float(usdt_balance)

                except Exception as e:
                    logger.error(f"Error fetching balance from {exchange_name}: {e}")

            return total_balance

        except Exception as e:
            logger.error(f"Error calculating total balance: {e}")
            return 0.0

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