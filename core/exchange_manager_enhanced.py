"""
Enhanced Exchange Manager with centralized duplicate checking and CCXT-first approach
Solves: Duplicate orders, direct API calls, inconsistent error handling

Architecture:
- 95%+ operations through CCXT
- Centralized duplicate checking before order creation
- Safe cancel with race condition handling
- Proper Stop Loss vs Limit Exit differentiation
"""

import ccxt.async_support as ccxt
import logging
import time
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass

from utils.decimal_utils import to_decimal

logger = logging.getLogger(__name__)


@dataclass
class OrderInfo:
    """Enhanced order information"""
    id: str
    symbol: str
    side: str
    type: str
    amount: float
    price: float
    filled: float
    remaining: float
    status: str
    timestamp: datetime
    reduce_only: bool
    stop_order_type: Optional[str]
    trigger_price: Optional[float]
    info: Dict


class EnhancedExchangeManager:
    """
    Enhanced Exchange Manager with duplicate prevention and CCXT-first approach

    Key features:
    - Centralized duplicate checking
    - Safe cancel with verification
    - Progressive price calculation for aged positions
    - Proper Stop Loss detection
    """

    def __init__(self, exchange: ccxt.Exchange):
        """Initialize with CCXT exchange instance"""
        self.exchange = exchange
        self.exchange_id = exchange.id

        # Cache for duplicate prevention
        self._order_cache = {}  # symbol -> list of open orders
        self._cache_timestamp = {}  # symbol -> last cache update time
        self._cache_ttl = 5  # Cache TTL in seconds

        # Track pending operations to prevent race conditions
        self._pending_operations = set()

        # Statistics
        self.stats = {
            'orders_created': 0,
            'duplicates_prevented': 0,
            'orders_cancelled': 0,
            'race_conditions_detected': 0
        }

        logger.info(
            f"🚀 Enhanced Exchange Manager initialized for {self.exchange_id} "
            f"(CCXT v{ccxt.__version__})"
        )

    async def create_limit_exit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        check_duplicates: bool = True
    ) -> Optional[Dict]:
        """
        Create limit exit order with automatic duplicate prevention

        This is the MAIN function for creating exit orders.
        Automatically checks for duplicates and handles exchange-specific params.

        Args:
            symbol: Trading pair symbol (CCXT format)
            side: 'buy' or 'sell'
            amount: Order amount
            price: Limit price
            check_duplicates: Whether to check for existing orders (default True)

        Returns:
            Order dict or existing order if duplicate found
        """
        try:
            # Step 1: Duplicate check (if enabled)
            if check_duplicates:
                existing = await self._check_existing_exit_order(symbol, side, price)
                if existing:
                    logger.info(f"✅ Exit order already exists: {existing['id']} at {existing['price']}")
                    self.stats['duplicates_prevented'] += 1
                    return existing

            # Step 2: Precision handling
            if hasattr(self.exchange, 'price_to_precision'):
                price = float(self.exchange.price_to_precision(symbol, price))
            if hasattr(self.exchange, 'amount_to_precision'):
                amount = float(self.exchange.amount_to_precision(symbol, amount))

            # Step 3: Prepare universal CCXT params
            params = {
                'reduceOnly': True,  # CCXT handles conversion to exchange format
                'timeInForce': 'GTC'  # Good Till Cancelled
            }

            # Exchange-specific parameters
            if self.exchange_id == 'bybit':
                # Bybit V5 specific
                params['positionIdx'] = 0  # One-way mode
                params['orderType'] = 'Limit'
                params['closeOnTrigger'] = False

            elif self.exchange_id in ['binance', 'binanceusdm']:
                # Binance specific
                params['postOnly'] = True  # Maker order only

            # Step 4: Create order through CCXT
            logger.info(
                f"📝 Creating limit exit order: {side} {amount} {symbol} @ {price}"
            )

            order = await self.exchange.create_order(
                symbol=symbol,
                type='limit',
                side=side,
                amount=amount,
                price=price,
                params=params
            )

            if order:
                logger.info(
                    f"✅ Exit order created: {order['id']} "
                    f"({side} {amount} @ {price})"
                )

                # Update cache
                await self._invalidate_order_cache(symbol)
                self.stats['orders_created'] += 1

                return order

        except ccxt.InvalidOrder as e:
            error_msg = str(e)
            if '-2022' in error_msg or '110017' in error_msg:
                logger.error(f"❌ ReduceOnly rejected - no position exists for {symbol}")
            elif '-1111' in error_msg or '110025' in error_msg:
                logger.error(f"❌ Precision error for {symbol}: {error_msg}")
            else:
                logger.error(f"❌ Invalid order: {error_msg}")
            raise

        except ccxt.InsufficientFunds as e:
            logger.error(f"❌ Insufficient funds for {symbol}: {e}")
            raise

        except Exception as e:
            logger.error(f"❌ Unexpected error creating exit order: {e}", exc_info=True)
            raise

    async def _check_existing_exit_order(
        self,
        symbol: str,
        side: str,
        target_price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Check for existing limit exit orders

        CRITICAL function: prevents duplicate order creation

        Args:
            symbol: Trading pair
            side: Order side to check
            target_price: Optional price to compare (for updates)

        Returns:
            Existing order dict or None
        """
        try:
            # Get cached or fresh orders
            orders = await self._get_open_orders_cached(symbol)

            for order in orders:
                # Check if it's a limit exit order
                is_limit = order.get('type') == 'limit'
                is_same_side = order.get('side') == side

                # CRITICAL: Proper reduceOnly check
                # CCXT normalizes this to boolean
                is_reduce_only = order.get('reduceOnly') == True

                # Not a stop loss (important distinction!)
                is_not_stop = not self._is_stop_loss_order(order)

                if is_limit and is_same_side and is_reduce_only and is_not_stop:
                    # Check if price needs update
                    if target_price:
                        current_price = float(order.get('price', 0))
                        price_diff_pct = abs(target_price - current_price) / current_price * 100

                        if price_diff_pct > 0.5:  # More than 0.5% difference
                            logger.info(
                                f"📊 Existing order {order['id']} has {price_diff_pct:.1f}% "
                                f"price difference, may need update"
                            )

                    return order

            return None

        except Exception as e:
            logger.error(f"Error checking existing orders: {e}")
            return None

    def _is_stop_loss_order(self, order: Dict) -> bool:
        """
        Correctly identify Stop Loss orders vs Limit Exit orders

        Based on:
        - Bybit V5 API documentation
        - Binance Futures API documentation
        - CCXT unified format
        - Freqtrade implementation

        CRITICAL: stopOrderType is the PRIMARY identifier!
        """
        # Get raw info from exchange
        info = order.get('info', {})

        # Priority 1: stopOrderType (Bybit V5)
        stop_order_type = info.get('stopOrderType', '')
        if stop_order_type in ['StopLoss', 'PartialStopLoss', 'TrailingStop', 'tpslOrder']:
            return True

        # Priority 2: CCXT unified type
        order_type = order.get('type', '')
        if order_type in ['stop', 'stop_market', 'stop_limit']:
            return True

        # Priority 3: Binance origType
        orig_type = info.get('origType', '')
        if orig_type in ['STOP', 'STOP_MARKET', 'STOP_LIMIT']:
            return True

        # Priority 4: Trigger price indicates stop order
        trigger_price = float(order.get('triggerPrice', 0) or info.get('triggerPrice', 0) or 0)
        if trigger_price > 0:
            return True

        # NOT a Stop Loss if:
        # - type == 'limit' with reduceOnly but NO stopOrderType
        # - This is just a regular limit exit order!
        return False

    async def safe_cancel_with_verification(
        self,
        order_id: str,
        symbol: str
    ) -> Dict:
        """
        Safely cancel order with race condition protection

        Features:
        - Verification after cancel
        - Filled-during-cancel detection
        - Partial fill handling
        """
        operation_key = f"{symbol}:{order_id}"

        # Prevent concurrent operations
        if operation_key in self._pending_operations:
            logger.warning(f"⚠️ Cancel already in progress for {order_id}")
            return {'status': 'already_pending', 'order': None}

        self._pending_operations.add(operation_key)

        try:
            # Step 1: Cancel order
            logger.info(f"🔄 Cancelling order {order_id} for {symbol}")
            await self.exchange.cancel_order(order_id, symbol)

            # Step 2: CRITICAL delay for exchange processing
            await asyncio.sleep(0.2)

            # Step 3: Verify cancellation
            try:
                order = await self.exchange.fetch_order(order_id, symbol)

                # Check if filled during cancel
                if order['status'] in ['closed', 'filled']:
                    logger.warning(
                        f"⚠️ Order {order_id} was FILLED during cancel! "
                        f"Filled: {order.get('filled', 0)}"
                    )
                    self.stats['race_conditions_detected'] += 1
                    return {'status': 'filled_during_cancel', 'order': order}

                # Check partial fill
                filled = float(order.get('filled', 0))
                if filled > 0:
                    logger.info(f"📊 Order {order_id} was partially filled: {filled}")
                    return {'status': 'canceled_partial', 'order': order, 'filled': filled}

                self.stats['orders_cancelled'] += 1
                return {'status': 'canceled', 'order': order}

            except ccxt.OrderNotFound:
                # Order successfully cancelled and removed
                self.stats['orders_cancelled'] += 1
                return {'status': 'canceled', 'order': None}

        except ccxt.OrderNotFound:
            logger.info(f"Order {order_id} not found (already cancelled/filled)")
            return {'status': 'not_found', 'order': None}

        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return {'status': 'error', 'order': None, 'error': str(e)}

        finally:
            self._pending_operations.discard(operation_key)
            await self._invalidate_order_cache(symbol)

    async def update_exit_order_price(
        self,
        existing_order: Dict,
        new_price: float,
        amount: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Update exit order price using cancel-and-replace pattern

        Handles:
        - Safe cancellation
        - Race conditions
        - Partial fills
        """
        symbol = existing_order['symbol']
        side = existing_order['side']

        # Use original amount if not specified
        if amount is None:
            amount = float(existing_order['amount'])

        logger.info(
            f"📝 Updating order {existing_order['id']}: "
            f"price {existing_order['price']} → {new_price}"
        )

        # Step 1: Safe cancel
        cancel_result = await self.safe_cancel_with_verification(
            existing_order['id'],
            symbol
        )

        # Step 2: Handle race conditions
        if cancel_result['status'] == 'filled_during_cancel':
            logger.warning(f"⚠️ Order filled during cancel - NOT creating new order")
            return None

        # Step 3: Adjust for partial fills
        if cancel_result['status'] == 'canceled_partial':
            filled = cancel_result.get('filled', 0)
            amount = amount - filled
            logger.info(f"📊 Adjusting amount for partial fill: {amount} remaining")

        # Step 4: Create new order if needed
        if amount > 0:
            min_amount = self._get_min_order_amount(symbol)
            if amount < min_amount:
                logger.warning(f"⚠️ Remaining amount {amount} below minimum {min_amount}")
                return None

            return await self.create_limit_exit_order(
                symbol, side, amount, new_price,
                check_duplicates=False  # We just cancelled the old one
            )

        return None

    async def _get_open_orders_cached(self, symbol: str) -> List[Dict]:
        """
        Get open orders with caching to reduce API calls
        """
        # Check cache validity
        cache_time = self._cache_timestamp.get(symbol, 0)
        if time.time() - cache_time < self._cache_ttl:
            cached = self._order_cache.get(symbol)
            if cached is not None:
                return cached

        # Fetch fresh data
        try:
            orders = await self.exchange.fetch_open_orders(symbol)

            # Update cache
            self._order_cache[symbol] = orders
            self._cache_timestamp[symbol] = time.time()

            return orders

        except Exception as e:
            logger.error(f"Error fetching orders for {symbol}: {e}")
            return []

    async def _invalidate_order_cache(self, symbol: str):
        """Invalidate order cache for symbol"""
        self._cache_timestamp[symbol] = 0

    def _get_min_order_amount(self, symbol: str) -> float:
        """Get minimum order amount for symbol"""
        try:
            market = self.exchange.market(symbol)
            return float(market.get('limits', {}).get('amount', {}).get('min', 0.001))
        except:
            # Default minimums
            if 'BTC' in symbol:
                return 0.001
            return 0.01

    def calculate_progressive_exit_price(
        self,
        entry_price: float,
        side: str,
        hours_open: float,
        max_age_hours: float = 24
    ) -> float:
        """
        Calculate progressive exit price for aged positions

        NEW STRATEGY:
        - Grace period (0-AGED_GRACE_PERIOD_HOURS): Breakeven only
        - Progressive (after grace): Linear loss increase with acceleration
        - Emergency (extremely old): Market price

        Args:
            entry_price: Position entry price
            side: Position side ('long' or 'short')
            hours_open: How many hours position has been open
            max_age_hours: Maximum age before liquidation starts

        Returns:
            Target exit price

        NOTE: This method is kept for backward compatibility.
        New code should use aged_position_manager directly.
        """
        import os

        # Load parameters from environment
        max_position_age = float(os.getenv('MAX_POSITION_AGE_HOURS', max_age_hours))
        grace_period = float(os.getenv('AGED_GRACE_PERIOD_HOURS', 8))
        loss_step = float(os.getenv('AGED_LOSS_STEP_PERCENT', 0.5))
        max_loss = float(os.getenv('AGED_MAX_LOSS_PERCENT', 10.0))
        acceleration = float(os.getenv('AGED_ACCELERATION_FACTOR', 1.2))
        commission = float(os.getenv('COMMISSION_PERCENT', 0.1)) / 100

        # Calculate hours over limit
        if hours_open < max_position_age:
            # Position not aged yet
            return entry_price * (1 + 2 * commission) if side == 'long' else entry_price * (1 - 2 * commission)

        hours_over_limit = hours_open - max_position_age

        if hours_over_limit <= grace_period:
            # GRACE PERIOD: Strict breakeven
            if side in ['long', 'buy']:
                exit_price = entry_price * (1 + 2 * commission)
            else:
                exit_price = entry_price * (1 - 2 * commission)

        else:
            # PROGRESSIVE LIQUIDATION
            hours_after_grace = hours_over_limit - grace_period

            # Base loss calculation
            loss_percent = hours_after_grace * loss_step

            # Acceleration after 10 hours
            if hours_after_grace > 10:
                extra_hours = hours_after_grace - 10
                loss_percent += extra_hours * loss_step * (acceleration - 1)

            # Cap at maximum
            loss_percent = min(loss_percent, max_loss)

            # Apply loss
            if side in ['long', 'buy']:
                exit_price = entry_price * (1 - loss_percent / 100)
            else:
                exit_price = entry_price * (1 + loss_percent / 100)

        logger.debug(
            f"Progressive price: entry={entry_price:.2f}, "
            f"age={hours_open:.1f}h, exit={exit_price:.2f}"
        )

        return exit_price

    def get_statistics(self) -> Dict:
        """Get manager statistics"""
        return {
            'exchange': self.exchange_id,
            'orders_created': self.stats['orders_created'],
            'duplicates_prevented': self.stats['duplicates_prevented'],
            'orders_cancelled': self.stats['orders_cancelled'],
            'race_conditions_detected': self.stats['race_conditions_detected'],
            'cache_size': len(self._order_cache)
        }


async def check_position_has_stop_loss(
    exchange_manager: EnhancedExchangeManager,
    symbol: str
) -> bool:
    """
    Comprehensive Stop Loss check for position

    Checks both:
    1. Order-based Stop Loss
    2. Position-attached Stop Loss (trading-stop)

    Returns:
        True if position has any type of Stop Loss protection
    """
    try:
        # Check 1: Order-based Stop Loss
        orders = await exchange_manager.exchange.fetch_open_orders(symbol)

        for order in orders:
            if exchange_manager._is_stop_loss_order(order):
                logger.info(f"✅ Stop Loss order found: {order['id']}")
                return True

        # Check 2: Position-attached Stop Loss
        try:
            positions = await exchange_manager.exchange.fetch_positions([symbol])
            if positions:
                position = positions[0]

                # Check various stop loss fields
                stop_loss_price = (
                    position.get('stopLoss') or
                    position.get('info', {}).get('stopLoss') or
                    position.get('info', {}).get('stopLossPrice') or
                    0
                )

                if stop_loss_price and float(stop_loss_price) > 0:
                    logger.info(f"✅ Position Stop Loss found at {stop_loss_price}")
                    return True

        except Exception as e:
            logger.debug(f"Could not check position SL: {e}")

        logger.warning(f"⚠️ No Stop Loss protection found for {symbol}")
        return False

    except Exception as e:
        logger.error(f"Error checking Stop Loss for {symbol}: {e}")
        return False