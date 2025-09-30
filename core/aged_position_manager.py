"""
Aged Position Manager - Smart liquidation strategy for old positions
Manages position lifecycle with gradual liquidation based on age and balance
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import asyncio

logger = logging.getLogger(__name__)


class AgedPositionManager:
    """
    Manager for closing aged positions with gradual liquidation strategy

    Phases:
    1. Breakeven attempt (0 - MAX_POSITION_AGE_HOURS)
    2. Gradual liquidation if low balance (MAX_POSITION_AGE_HOURS + 4-8h)
    3. Force close after 8 hours over limit
    """

    def __init__(self, config, position_manager, exchanges):
        self.config = config
        self.position_manager = position_manager
        self.exchanges = exchanges  # Dict of exchange instances

        # Age parameters from config
        self.max_position_age_hours = float(getattr(config, 'max_position_age_hours', 24))
        self.commission_percent = float(getattr(config, 'commission_percent', 0.3)) / 100

        # Balance threshold for triggering liquidation
        position_size = float(getattr(config, 'position_size_usd', 200))
        self.min_balance_threshold = position_size * 10  # 10x position size

        # Gradual liquidation steps (hours_over_limit, approach_factor)
        self.liquidation_steps = [
            (4, 0.2),  # Hour 4: 20% approach to market
            (5, 0.4),  # Hour 5: 40% approach
            (6, 0.6),  # Hour 6: 60% approach
            (7, 0.8),  # Hour 7: 80% approach
            (8, 1.0),  # Hour 8: 100% (market close)
        ]

        # Track pending orders for aged positions
        self.position_orders = {}  # position_id: order_id
        self.last_price_update = {}  # position_id: datetime

        # Statistics
        self.stats = {
            'positions_checked': 0,
            'aged_positions': 0,
            'breakeven_closes': 0,
            'gradual_liquidations': 0,
            'forced_closes': 0,
            'total_loss_avoided': Decimal('0')
        }

        logger.info(
            f"🎯 Aged Position Manager initialized: "
            f"max_age={self.max_position_age_hours}h, "
            f"commission={self.commission_percent*100:.1f}%, "
            f"balance_threshold=${self.min_balance_threshold:.0f}"
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
                    # Calculate age in hours
                    if hasattr(position.opened_at, 'tzinfo') and position.opened_at.tzinfo:
                        position_age = current_time.replace(tzinfo=position.opened_at.tzinfo) - position.opened_at
                    else:
                        position_age = current_time - position.opened_at

                    age_hours = position_age.total_seconds() / 3600

                    # Check if position is aged
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

                # Check balance once for all positions
                total_balance = await self._get_total_balance()
                logger.info(f"💰 Current total balance: ${total_balance:.2f}")

                for position in aged_positions:
                    await self.process_aged_position(position, total_balance)

            return len(aged_positions)

        except Exception as e:
            logger.error(f"Error checking aged positions: {e}", exc_info=True)
            return 0

    async def process_aged_position(self, position, total_balance: float):
        """
        Process a single aged position based on age and balance
        """
        try:
            age_hours = position.age_hours
            symbol = position.symbol

            # Get current market price
            current_price = await self._get_current_price(symbol, position.exchange)
            if not current_price:
                logger.error(f"Could not get price for {symbol}")
                return

            position.current_price = current_price

            # Calculate breakeven price with commissions
            breakeven_price = self._calculate_breakeven_price(
                position.entry_price,
                position.side
            )

            logger.info(
                f"📈 Processing aged position {symbol}:\n"
                f"  • Age: {age_hours:.1f} hours\n"
                f"  • Side: {position.side}\n"
                f"  • Entry: ${position.entry_price:.2f}\n"
                f"  • Current: ${current_price:.2f}\n"
                f"  • Breakeven: ${breakeven_price:.2f}\n"
                f"  • Balance: ${total_balance:.2f}"
            )

            # Determine liquidation phase
            hours_over_limit = age_hours - self.max_position_age_hours

            # Phase 1: Just expired - try breakeven exit
            if hours_over_limit < 4:
                await self._try_breakeven_exit(position, current_price, breakeven_price)

            # Phase 2: Check if gradual liquidation needed
            elif hours_over_limit < 8:
                # Low balance triggers gradual liquidation
                if total_balance < self.min_balance_threshold:
                    logger.warning(
                        f"💸 Low balance (${total_balance:.2f} < ${self.min_balance_threshold:.0f}), "
                        f"starting gradual liquidation"
                    )
                    await self._gradual_liquidation(position, current_price, hours_over_limit)
                else:
                    # Balance OK, keep trying breakeven
                    await self._try_breakeven_exit(position, current_price, breakeven_price)

            # Phase 3: Force close after 8 hours
            else:
                logger.error(
                    f"🚨 CRITICAL: Position {symbol} is {age_hours:.1f}h old "
                    f"(>{self.max_position_age_hours + 8}h). Force closing!"
                )
                await self._close_position_market(position)
                self.stats['forced_closes'] += 1

        except Exception as e:
            logger.error(f"Error processing aged position {position.symbol}: {e}", exc_info=True)

    def _calculate_breakeven_price(self, entry_price: float, side: str) -> float:
        """
        Calculate breakeven price including commissions

        For LONG: need to sell higher = entry * (1 + 2*commission)
        For SHORT: need to buy lower = entry * (1 - 2*commission)
        """
        double_commission = 2 * self.commission_percent

        if side in ['long', 'buy']:
            return float(entry_price) * (1 + double_commission)
        else:  # short/sell
            return float(entry_price) * (1 - double_commission)

    async def _try_breakeven_exit(self, position, current_price: float, breakeven_price: float):
        """
        Attempt to exit at breakeven or better
        """
        # Check if we can exit profitably now
        if position.side in ['long', 'buy']:
            can_exit_profitable = current_price >= breakeven_price
        else:  # short/sell
            can_exit_profitable = current_price <= breakeven_price

        if can_exit_profitable:
            logger.info(
                f"✅ Position {position.symbol} reached breakeven "
                f"(current: ${current_price:.2f} vs breakeven: ${breakeven_price:.2f}). "
                f"Closing by market order."
            )
            await self._close_position_market(position)
            self.stats['breakeven_closes'] += 1
        else:
            # Place/update limit order at breakeven
            logger.info(
                f"📌 Setting limit order for {position.symbol} at breakeven ${breakeven_price:.2f}"
            )
            await self._place_or_update_limit_order(position, breakeven_price)

    async def _gradual_liquidation(self, position, current_price: float, hours_over_limit: float):
        """
        Gradual approach to market price based on time
        Uses universal formula: target = entry + (current - entry) * factor
        """
        # Find appropriate liquidation factor
        factor = 0.0
        for step_hours, step_factor in self.liquidation_steps:
            if hours_over_limit >= step_hours:
                factor = step_factor

        if factor >= 1.0:
            # Final step - close at market
            logger.warning(
                f"🔴 Final liquidation hour for {position.symbol}. "
                f"Closing at market price ${current_price:.2f}"
            )
            await self._close_position_market(position)
            self.stats['gradual_liquidations'] += 1
        else:
            # Calculate target price approaching market
            # Universal formula works for both long and short
            # Fix: Ensure Decimal compatibility
            from decimal import Decimal
            target_price = float(position.entry_price) + (float(current_price) - float(position.entry_price)) * factor

            # Log the approach
            distance_percent = abs((target_price - float(position.entry_price)) / float(position.entry_price) * 100)
            logger.info(
                f"📉 Gradual liquidation {position.symbol}:\n"
                f"  • Factor: {factor*100:.0f}% approach to market\n"
                f"  • Entry: ${position.entry_price:.2f}\n"
                f"  • Target: ${target_price:.2f}\n"
                f"  • Current: ${current_price:.2f}\n"
                f"  • Movement: {distance_percent:.1f}% from entry"
            )

            # Update limit order
            await self._place_or_update_limit_order(position, target_price)

    async def _place_or_update_limit_order(self, position, target_price: float):
        """
        Place or update limit order for position exit
        """
        try:
            position_id = f"{position.symbol}_{position.exchange}"

            # Check if we need to update (once per hour)
            if not self._should_update_price(position_id):
                return

            # Cancel existing order if any
            existing_order_id = self.position_orders.get(position_id)
            if existing_order_id:
                try:
                    exchange = self.exchanges.get(position.exchange)
                    if exchange:
                        await exchange.cancel_order(existing_order_id, position.symbol)
                        logger.info(f"Cancelled old order {existing_order_id}")
                except Exception as e:
                    logger.debug(f"Could not cancel order {existing_order_id}: {e}")

            # Determine order side (opposite of position)
            order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

            # Place new limit order
            exchange = self.exchanges.get(position.exchange)
            if not exchange:
                logger.error(f"Exchange {position.exchange} not available")
                return

            try:
                order = await exchange.create_order(
                    symbol=position.symbol,
                    type='limit',
                    side=order_side,
                    amount=abs(position.size),
                    price=target_price
                )

                if order:
                    self.position_orders[position_id] = order['id']
                    self.last_price_update[position_id] = datetime.now()

                    logger.info(
                        f"📝 Placed limit order for {position.symbol}: "
                        f"{order_side} {abs(position.size)} @ ${target_price:.2f}"
                    )
            except Exception as e:
                logger.error(f"Failed to place limit order: {e}")

        except Exception as e:
            logger.error(f"Error in place_or_update_limit_order: {e}", exc_info=True)

    def _should_update_price(self, position_id: str) -> bool:
        """
        Check if price should be updated (once per hour)
        """
        last_update = self.last_price_update.get(position_id)

        if not last_update:
            return True

        time_since_update = (datetime.now() - last_update).total_seconds() / 3600
        return time_since_update >= 1.0  # Update every hour

    async def _check_position_exists_on_exchange(self, position, exchange):
        """
        Check if position actually exists on exchange
        Based on Bybit API v5 documentation and GitHub pybit issues
        """
        try:
            symbol = position.symbol

            # Fetch current positions from exchange
            positions = await exchange.fetch_positions([symbol])

            # Check if position exists with non-zero size
            for pos in positions:
                if pos.get('symbol') == symbol:
                    size = float(pos.get('contracts', 0) or pos.get('size', 0) or pos.get('amount', 0))
                    if size > 0:
                        return {
                            'size': size,
                            'side': pos.get('side'),
                            'unrealizedPnl': pos.get('unrealizedPnl', 0)
                        }

            # No position found
            return None

        except Exception as e:
            logger.error(f"Error checking position on exchange: {e}")
            # On error, assume position exists to be safe
            return {'size': getattr(position, 'quantity', getattr(position, 'contracts', 1))}

    async def force_close_aged_position(self, position, max_retries: int = 5):
        """
        Force close aged position with aggressive retry logic
        Handles various error scenarios and ensures position gets closed
        """
        symbol = position.symbol
        position_id = f"{symbol}_{position.exchange}"
        exchange = self.exchanges.get(position.exchange)

        if not exchange:
            logger.error(f"Exchange {position.exchange} not found for {symbol}")
            return False

        # Cancel any pending orders first
        if position_id in self.position_orders:
            try:
                await exchange.cancel_order(self.position_orders[position_id], symbol)
                logger.info(f"Cancelled pending order for {symbol}")
            except:
                pass

        retry_count = 0
        amount = float(position.contracts if hasattr(position, 'contracts') else position.quantity)

        # CRITICAL: Check if position exists on exchange before trying to close
        # Solution from Bybit documentation and GitHub issues
        exchange_position = await self._check_position_exists_on_exchange(position, exchange)

        if not exchange_position:
            # Position doesn't exist on exchange - it's a phantom position
            logger.warning(f"⚠️ Position {symbol} does not exist on {position.exchange} - cleaning DB only")

            # Update position status without trying to close on exchange
            # Note: repository method accepts position_id, status, and optional notes
            await self.repository.update_position_status(
                position_id=position.id,
                status='phantom_closed',
                notes='Position not found on exchange - phantom close'
            )

            # Clean up tracking
            self.position_orders.pop(position_id, None)
            self.last_price_update.pop(position_id, None)
            self.stats['phantom_closes'] = self.stats.get('phantom_closes', 0) + 1

            return True

        # Position exists - get actual size from exchange
        actual_amount = exchange_position.get('size', amount)

        while retry_count < max_retries:
            try:
                logger.info(f"🔄 Force close attempt {retry_count + 1}/{max_retries} for {symbol}")

                # Determine closing side (opposite of position)
                closing_side = 'buy' if position.side.lower() in ['short', 'sell'] else 'sell'

                # Check if this is spot or futures
                is_spot = not symbol.endswith(':USDT') and '/' in symbol

                # Prepare params based on market type
                order_params = {}
                if not is_spot:
                    # Only use reduceOnly for futures/perpetuals
                    order_params['reduceOnly'] = True

                # Try market order through exchange manager
                order = await exchange.create_market_order(
                    symbol=symbol,
                    side=closing_side,
                    amount=Decimal(str(actual_amount)),
                    params=order_params
                )

                logger.info(f"✅ FORCE CLOSED aged position {symbol} (age: {position.age_hours:.1f}h)")

                # Clean up tracking
                self.position_orders.pop(position_id, None)
                self.last_price_update.pop(position_id, None)
                self.stats['forced_closes'] += 1

                return True

            except Exception as e:
                error_msg = str(e).lower()
                retry_count += 1

                # Handle specific errors
                if 'insufficient' in error_msg or 'not enough' in error_msg:
                    logger.warning(f"Insufficient balance for {symbol}, reducing size by 1%")
                    amount *= 0.99

                elif 'position not found' in error_msg or 'no position' in error_msg:
                    logger.warning(f"Position {symbol} not found, marking as closed")
                    self.position_orders.pop(position_id, None)
                    self.last_price_update.pop(position_id, None)
                    return True

                elif 'rate limit' in error_msg:
                    wait_time = min(60, 2 ** retry_count)
                    logger.warning(f"Rate limit hit, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)

                elif 'max quantity' in error_msg or '-4005' in error_msg:
                    # Split large orders
                    logger.warning(f"Max quantity exceeded for {symbol}, halving size")
                    amount /= 2

                else:
                    logger.error(f"Attempt {retry_count} failed for {symbol}: {e}")
                    await asyncio.sleep(2 ** retry_count)  # Exponential backoff

                if retry_count >= max_retries:
                    logger.critical(
                        f"🚨 CRITICAL: Failed to close {symbol} after {max_retries} attempts! "
                        f"MANUAL INTERVENTION REQUIRED!"
                    )
                    # Here you could send alert to Telegram/Email
                    return False

        return False

    async def _close_position_market(self, position):
        """
        Close position at market price immediately with improved logic
        """
        try:
            # Use the new force close method with retries
            success = await self.force_close_aged_position(position)

            if success:
                # Calculate avoided loss
                if hasattr(position, 'unrealized_pnl') and position.unrealized_pnl < 0:
                    self.stats['total_loss_avoided'] += abs(position.unrealized_pnl)

                logger.info(
                    f"✅ Closed aged position {position.symbol} "
                    f"(age: {position.age_hours:.1f}h)"
                )
            else:
                logger.error(f"❌ Failed to close aged position {position.symbol}")

        except Exception as e:
            logger.error(f"Failed to close position {position.symbol}: {e}", exc_info=True)

    async def _get_current_price(self, symbol: str, exchange_name: str) -> Optional[float]:
        """Get current market price for symbol"""
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                return None

            ticker = await exchange.fetch_ticker(symbol)
            return ticker.get('last', ticker.get('close'))

        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None

    async def _get_total_balance(self) -> float:
        """Get total USDT balance across all exchanges"""
        try:
            total = 0.0

            for exchange_name, exchange in self.exchanges.items():
                try:
                    balance = await exchange.fetch_balance()
                    usdt_balance = balance.get('USDT', {})
                    free = usdt_balance.get('free', 0)
                    total += float(free)
                except Exception as e:
                    logger.debug(f"Could not get balance from {exchange_name}: {e}")

            return total

        except Exception as e:
            logger.error(f"Error getting total balance: {e}")
            return float('inf')  # Don't trigger liquidation on error

    def get_statistics(self) -> Dict:
        """Get manager statistics"""
        return {
            **self.stats,
            'pending_orders': len(self.position_orders),
            'positions_tracking': len(self.last_price_update)
        }

    def reset_statistics(self):
        """Reset statistics counters"""
        self.stats = {
            'positions_checked': 0,
            'aged_positions': 0,
            'breakeven_closes': 0,
            'gradual_liquidations': 0,
            'forced_closes': 0,
            'total_loss_avoided': Decimal('0')
        }
        logger.info("Aged position manager statistics reset")