"""
Specialized Binance Zombie Order Manager
Handles ALL known Binance API bugs and quirks
Production-ready with minimal impact on existing code
"""

import ccxt
import ccxt.async_support as ccxt_async
import time
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Set, Any
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BinanceZombieOrder:
    """Detailed information about a Binance zombie order"""
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    amount: float
    price: float
    status: str
    timestamp: int
    zombie_type: str  # 'orphaned', 'phantom', 'stuck', 'async_lost', 'oco_orphan'
    reason: str
    order_list_id: Optional[int] = None  # For OCO orders


class BinanceZombieManager:
    """
    Specialized manager for Binance-specific zombie order issues

    Handles:
    - Empty fetchOpenOrders responses (Binance bug)
    - Weight-based rate limits (not simple counting)
    - Asynchronous order appearance (up to 5 seconds delay)
    - OCO order special handling
    - Error codes -2011, -2013
    - Caching to mitigate empty responses
    """

    def __init__(self, exchange_connector):
        """
        Initialize with existing Binance exchange connector

        Args:
            exchange_connector: Existing CCXT Binance instance or ExchangeManager
        """
        # Support both raw CCXT and wrapped ExchangeManager
        if hasattr(exchange_connector, 'exchange'):
            self.exchange = exchange_connector.exchange
            self.exchange_manager = exchange_connector
        else:
            self.exchange = exchange_connector
            self.exchange_manager = None

        # Suppress Binance warning about fetching orders without symbol
        if hasattr(self.exchange, 'options'):
            self.exchange.options['warnOnFetchOpenOrdersWithoutSymbol'] = False

        # Critical caching for Binance empty response bug
        self.orders_cache = {}
        self.cache_timestamp = {}
        self.CACHE_TTL = 5  # seconds - short TTL for safety

        # Weight-based rate limiting (Binance specific)
        self.weight_used = 0
        self.weight_reset_time = time.time() + 60
        self.WEIGHT_LIMIT = 1180  # Leave buffer from 1200 limit

        # Binance API operation weights
        self.operation_weights = {
            'fetch_open_orders_symbol': 3,
            'fetch_open_orders_all': 40,
            'fetch_order': 2,
            'cancel_order': 1,
            'cancel_all_orders': 1,
            'fetch_balance': 10,
            'fetch_positions': 5,
            'create_order': 1,
            'fetch_ticker': 1,
            'fetch_my_trades': 10,
            'fetch_order_trades': 2,
        }

        # Tracking for metrics
        self.metrics = {
            'empty_responses': 0,
            'rate_limit_waits': 0,
            'error_2011_count': 0,
            'error_2013_count': 0,
            'oco_handled': 0,
            'zombies_cleaned': 0,
            'async_delays_detected': 0,
        }

        # Binance error codes
        self.BINANCE_ERROR_CODES = {
            -1000: 'Unknown error',
            -1003: 'Too many requests',
            -1013: 'Invalid quantity',
            -1021: 'Timestamp ahead of server time',
            -2010: 'New order rejected',
            -2011: 'Cancel rejected - Unknown order',
            -2013: 'Order does not exist',
            -2014: 'Invalid API key',
            -2015: 'Invalid API key or permissions',
            -4005: 'Order would immediately match',
            -4131: 'The counterparty\'s best price does not meet the PERCENT_PRICE filter limit',
        }

        logger.info("BinanceZombieManager initialized")
        logger.info(f"Weight limit: {self.WEIGHT_LIMIT}, Cache TTL: {self.CACHE_TTL}s")

    def get_metrics(self) -> Dict:
        """Get current metrics for monitoring"""
        return {
            'total_cleanups': self.metrics.get('total_cleanups', 0),
            'total_zombies_found': self.metrics.get('zombies_found', 0),
            'total_zombies_cleaned': self.metrics.get('zombies_cleaned', 0),
            'empty_responses': self.metrics.get('empty_responses', 0),
            'cache_hits': self.metrics.get('cache_hits', 0),
            'rate_limit_waits': self.metrics.get('rate_limit_waits', 0),
            'weight_used': self.weight_used,
            'weight_limit': self.WEIGHT_LIMIT
        }

    async def check_and_wait_rate_limit(self, operation: str, symbol: str = None):
        """
        Check and enforce weight-based rate limits (Binance specific)

        Args:
            operation: API operation name
            symbol: Trading symbol (affects weight for some operations)
        """
        # Determine operation weight
        if operation == 'fetch_open_orders':
            weight = self.operation_weights['fetch_open_orders_symbol' if symbol else 'fetch_open_orders_all']
        else:
            weight = self.operation_weights.get(operation, 1)

        # Reset weight counter every minute
        current_time = time.time()
        if current_time > self.weight_reset_time:
            self.weight_used = 0
            self.weight_reset_time = current_time + 60
            logger.debug("Weight counter reset for new minute")

        # Check if we need to wait
        if self.weight_used + weight > self.WEIGHT_LIMIT:
            sleep_time = max(self.weight_reset_time - current_time, 0.1)
            logger.warning(f"⚠️ Binance weight limit approaching: {self.weight_used}/{self.WEIGHT_LIMIT}")
            logger.warning(f"Sleeping {sleep_time:.1f}s until weight reset")
            self.metrics['rate_limit_waits'] += 1
            await asyncio.sleep(sleep_time)

            # Reset after wait
            self.weight_used = 0
            self.weight_reset_time = time.time() + 60

        # Update weight counter
        self.weight_used += weight
        logger.debug(f"Weight: {self.weight_used}/{self.WEIGHT_LIMIT} (+{weight} for {operation})")

    async def fetch_open_orders_safe(self, symbol: str = None,
                                    use_cache: bool = True,
                                    max_retries: int = 3) -> List[Dict]:
        """
        Fetch open orders with retry logic for Binance empty response bug

        This is CRITICAL for Binance which often returns empty arrays incorrectly

        Args:
            symbol: Trading pair symbol (None for all symbols)
            use_cache: Whether to use cached results
            max_retries: Maximum retry attempts

        Returns:
            List of open orders
        """
        cache_key = symbol or 'ALL'

        # Check cache first (mitigates empty response bug)
        if use_cache and cache_key in self.orders_cache:
            cache_age = time.time() - self.cache_timestamp.get(cache_key, 0)
            if cache_age < self.CACHE_TTL:
                logger.debug(f"Using cached orders for {cache_key} (age: {cache_age:.1f}s)")
                return self.orders_cache[cache_key]

        # Retry loop for empty response bug
        for attempt in range(max_retries):
            try:
                # Check rate limit
                await self.check_and_wait_rate_limit('fetch_open_orders', symbol)

                # Fetch orders
                if hasattr(self.exchange, 'fetch_open_orders'):
                    orders = await self.exchange.fetch_open_orders(symbol)
                else:
                    # Fallback for sync exchange
                    orders = self.exchange.fetch_open_orders(symbol)

                # If we got orders, cache and return
                if orders:
                    self.orders_cache[cache_key] = orders
                    self.cache_timestamp[cache_key] = time.time()
                    logger.info(f"✅ Fetched {len(orders)} orders" + (f" for {symbol}" if symbol else ""))
                    return orders

                # BINANCE BUG: Empty response when orders exist
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"⚠️ Binance empty response (known bug), "
                        f"retry {attempt + 1}/{max_retries} in {wait_time}s"
                    )
                    self.metrics['empty_responses'] += 1
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"⚠️ Still empty after {max_retries} attempts")
                    # Return empty list, not None
                    return []

            except ccxt.RateLimitExceeded:
                logger.error("Rate limit exceeded, waiting 60s")
                self.metrics['rate_limit_waits'] += 1
                await asyncio.sleep(60)
                self.weight_used = 0

            except Exception as e:
                error_str = str(e)
                logger.error(f"Error fetching orders (attempt {attempt + 1}/{max_retries}): {e}")

                # Check for specific Binance errors
                for code, desc in self.BINANCE_ERROR_CODES.items():
                    if str(code) in error_str:
                        logger.error(f"Binance error {code}: {desc}")
                        break

                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)

        return []

    async def detect_zombie_orders(self, check_async_delay: bool = True) -> Dict[str, List[BinanceZombieOrder]]:
        """
        Detect all types of zombie orders specific to Binance

        Args:
            check_async_delay: Whether to wait and recheck for async delays

        Returns:
            Dictionary of zombie orders categorized by type
        """
        zombies = {
            'orphaned': [],      # Orders without matching positions/balances
            'phantom': [],       # Orders returning error -2011/-2013
            'stuck': [],         # Orders older than 24 hours
            'async_lost': [],    # Recently created but not appearing
            'oco_orphans': [],   # Unpaired OCO orders
        }

        try:
            # Fetch all orders with retry (critical for Binance!)
            all_orders = await self.fetch_open_orders_safe(use_cache=False)

            if not all_orders:
                logger.info("No open orders found (or all fetch attempts failed)")
                return zombies

            logger.info(f"🔍 Checking {len(all_orders)} orders for zombies...")

            # Get account balances for orphan detection
            await self.check_and_wait_rate_limit('fetch_balance')

            if hasattr(self.exchange, 'fetch_balance'):
                balance = await self.exchange.fetch_balance()
            else:
                balance = self.exchange.fetch_balance()

            # Build list of symbols with actual balances
            active_symbols = set()
            min_balance_usd = 10  # Minimum balance to consider active

            for asset, amounts in balance['total'].items():
                if amounts and float(amounts) > 0:
                    # Add common quote pairs for this asset
                    for quote in ['USDT', 'BUSD', 'FDUSD', 'BTC', 'ETH', 'BNB']:
                        active_symbols.add(f"{asset}/{quote}")
                        active_symbols.add(f"{asset}{quote}")  # Binance format

            # Process each order
            for order in all_orders:
                zombie_order = await self._analyze_order(order, active_symbols)

                if zombie_order:
                    zombies[zombie_order.zombie_type].append(zombie_order)
                    logger.warning(
                        f"🧟 {zombie_order.zombie_type}: {zombie_order.order_id} "
                        f"on {zombie_order.symbol} - {zombie_order.reason}"
                    )

            # Check for async delay issues (Binance specific)
            if check_async_delay and zombies['async_lost']:
                logger.info(f"⏳ Waiting 10s to recheck {len(zombies['async_lost'])} async orders...")
                self.metrics['async_delays_detected'] += len(zombies['async_lost'])
                await asyncio.sleep(10)

                # Recheck
                recheck_orders = await self.fetch_open_orders_safe(use_cache=False)
                recheck_ids = {o.get('id') for o in recheck_orders}

                # Filter out orders that appeared after delay
                zombies['async_lost'] = [
                    z for z in zombies['async_lost']
                    if z.order_id not in recheck_ids
                ]

                if zombies['async_lost']:
                    logger.warning(f"⚠️ {len(zombies['async_lost'])} orders still missing after delay")

            # Log summary
            total_zombies = sum(len(orders) for orders in zombies.values())
            if total_zombies > 0:
                logger.warning(f"🧟 Found {total_zombies} zombie orders total:")
                for category, orders in zombies.items():
                    if orders:
                        logger.warning(f"  {category}: {len(orders)}")
            else:
                logger.info("✨ No zombie orders detected")

            return zombies

        except Exception as e:
            logger.error(f"Critical error detecting zombie orders: {e}", exc_info=True)
            return zombies

    async def _analyze_order(self, order: Dict, active_symbols: Set[str]) -> Optional[BinanceZombieOrder]:
        """
        Analyze single order for zombie characteristics

        Args:
            order: Order dictionary from exchange
            active_symbols: Set of symbols with active positions/balances

        Returns:
            BinanceZombieOrder if zombie detected, None otherwise
        """
        try:
            # Extract order details
            order_id = order.get('id', '')
            client_order_id = order.get('clientOrderId', '')
            symbol = order.get('symbol', '')
            side = order.get('side', '')
            order_type = order.get('type', '')
            amount = float(order.get('amount', 0) or 0)
            price = float(order.get('price', 0) or 0)
            status = order.get('status', 'unknown')
            timestamp = order.get('timestamp', 0)
            order_list_id = order.get('info', {}).get('orderListId', -1) if order.get('info') else -1

            # CRITICAL FIX: Skip protective orders - exchange manages their lifecycle
            # On futures, exchange auto-cancels these when position closes
            # If they exist → position is ACTIVE → NOT orphaned
            PROTECTIVE_ORDER_TYPES = [
                'STOP_LOSS', 'STOP_LOSS_LIMIT', 'STOP_MARKET',
                'TAKE_PROFIT', 'TAKE_PROFIT_LIMIT', 'TAKE_PROFIT_MARKET',
                'TRAILING_STOP_MARKET', 'STOP', 'TAKE_PROFIT'
            ]
            # CCXT returns lowercase types, so convert to uppercase for comparison
            if order_type.upper() in PROTECTIVE_ORDER_TYPES:
                logger.debug(f"Skipping protective order {order_id} ({order_type}) - managed by exchange")
                return None

            # CRITICAL FIX: Additional protection - check for protective keywords
            # Protects against format mismatches (e.g. 'StopMarket' vs 'STOP_MARKET')
            PROTECTIVE_KEYWORDS = ['STOP', 'TAKE_PROFIT', 'TRAILING']
            order_type_upper = order_type.upper()
            if any(keyword in order_type_upper for keyword in PROTECTIVE_KEYWORDS):
                logger.debug(f"Skipping protective order {order_id} ({order_type}) - contains protective keyword")
                return None

            # CRITICAL FIX: reduceOnly orders are always protective (SL/TP)
            if order.get('reduceOnly') == True:
                logger.debug(f"Skipping reduceOnly order {order_id} - likely SL/TP")
                return None

            # Skip if already closed
            if status in ['closed', 'canceled', 'filled', 'rejected', 'expired']:
                return None

            # 1. Check for orphaned orders (no balance for symbol)
            symbol_clean = symbol.replace(':', '')  # Remove Binance perp suffix
            if symbol not in active_symbols and symbol_clean not in active_symbols:
                return BinanceZombieOrder(
                    order_id=order_id,
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    amount=amount,
                    price=price,
                    status=status,
                    timestamp=timestamp,
                    zombie_type='orphaned',
                    reason='No balance for trading pair',
                    order_list_id=order_list_id if order_list_id != -1 else None
                )

            # 2. Check for phantom orders (exist in list but not fetchable)
            try:
                await self.check_and_wait_rate_limit('fetch_order')

                if hasattr(self.exchange, 'fetch_order'):
                    fetched = await self.exchange.fetch_order(order_id, symbol)
                else:
                    fetched = self.exchange.fetch_order(order_id, symbol)

                # Check if status mismatch
                if fetched.get('status') != 'open':
                    return BinanceZombieOrder(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        amount=amount,
                        price=price,
                        status=fetched.get('status', 'unknown'),
                        timestamp=timestamp,
                        zombie_type='phantom',
                        reason=f"Status mismatch: listed as open but is {fetched.get('status')}",
                        order_list_id=order_list_id if order_list_id != -1 else None
                    )

            except Exception as e:
                error_str = str(e)

                # Binance specific errors indicating phantom order
                if '-2011' in error_str or 'Unknown order' in error_str.lower():
                    self.metrics['error_2011_count'] += 1
                    return BinanceZombieOrder(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        amount=amount,
                        price=price,
                        status=status,
                        timestamp=timestamp,
                        zombie_type='phantom',
                        reason='Binance error -2011: Unknown order',
                        order_list_id=order_list_id if order_list_id != -1 else None
                    )

                if '-2013' in error_str or 'does not exist' in error_str.lower():
                    self.metrics['error_2013_count'] += 1
                    return BinanceZombieOrder(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        amount=amount,
                        price=price,
                        status=status,
                        timestamp=timestamp,
                        zombie_type='phantom',
                        reason='Binance error -2013: Order does not exist',
                        order_list_id=order_list_id if order_list_id != -1 else None
                    )

            # 3. Check for stuck orders (older than 24 hours)
            if timestamp:
                age_hours = (time.time() * 1000 - timestamp) / (1000 * 3600)
                if age_hours > 24:
                    return BinanceZombieOrder(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        amount=amount,
                        price=price,
                        status=status,
                        timestamp=timestamp,
                        zombie_type='stuck',
                        reason=f'Order is {age_hours:.1f} hours old',
                        order_list_id=order_list_id if order_list_id != -1 else None
                    )

            # 4. Check for async lost (very new orders that might be delayed)
            if timestamp:
                age_seconds = (time.time() * 1000 - timestamp) / 1000
                if age_seconds < 10:  # Less than 10 seconds old
                    return BinanceZombieOrder(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        amount=amount,
                        price=price,
                        status=status,
                        timestamp=timestamp,
                        zombie_type='async_lost',
                        reason=f'Very new order ({age_seconds:.1f}s), possible async delay',
                        order_list_id=order_list_id if order_list_id != -1 else None
                    )

            # 5. Check for OCO orphans (unpaired OCO orders)
            if order_list_id and order_list_id != -1:
                # Count orders with same orderListId
                all_orders = self.orders_cache.get('ALL', [])
                oco_count = sum(
                    1 for o in all_orders
                    if o.get('info', {}).get('orderListId') == order_list_id
                )

                if oco_count == 1:  # Should be 2 for valid OCO
                    self.metrics['oco_handled'] += 1
                    return BinanceZombieOrder(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        amount=amount,
                        price=price,
                        status=status,
                        timestamp=timestamp,
                        zombie_type='oco_orphans',
                        reason='Unpaired OCO order (missing companion)',
                        order_list_id=order_list_id
                    )

            return None

        except Exception as e:
            logger.error(f"Error analyzing order {order.get('id')}: {e}")
            return None

    async def cleanup_zombie_orders(self, dry_run: bool = True, aggressive: bool = False) -> Dict:
        """
        Clean up detected zombie orders with Binance-specific handling

        Args:
            dry_run: If True, only log but don't cancel
            aggressive: If True, skip async delay checks for faster cleanup

        Returns:
            Statistics of cleanup operation
        """
        stats = {
            'found': 0,
            'removed': 0,
            'failed': 0,
            'errors': []
        }

        try:
            # Detect zombies
            zombies = await self.detect_zombie_orders(check_async_delay=not aggressive)

            # Count total
            total_zombies = sum(len(orders) for orders in zombies.values())
            stats['found'] = total_zombies

            if total_zombies == 0:
                logger.info("✨ No zombie orders to clean")
                return stats

            if dry_run:
                logger.info(f"🔍 DRY RUN: Would remove {total_zombies} zombie orders")
                for category, orders in zombies.items():
                    if orders:
                        logger.info(f"  {category}: {len(orders)} orders")
                        for order in orders[:3]:  # Show first 3
                            logger.info(f"    - {order.symbol} {order.side} {order.order_type}")
                return stats

            # Process zombies by category
            logger.info(f"🧹 Starting cleanup of {total_zombies} zombie orders...")

            # Handle OCO orders specially
            if zombies['oco_orphans']:
                logger.info(f"Processing {len(zombies['oco_orphans'])} OCO orphans...")
                for zombie in zombies['oco_orphans']:
                    success = await self._cancel_oco_order(zombie)
                    if success:
                        stats['removed'] += 1
                    else:
                        stats['failed'] += 1
                    await asyncio.sleep(0.5)

            # Process other zombies
            all_regular_zombies = (
                zombies['orphaned'] +
                zombies['phantom'] +
                zombies['stuck'] +
                ([] if aggressive else zombies['async_lost'])  # Skip async_lost in aggressive mode
            )

            for zombie in all_regular_zombies:
                success = await self._cancel_order_safe(zombie)
                if success:
                    stats['removed'] += 1
                    self.metrics['zombies_cleaned'] += 1
                else:
                    stats['failed'] += 1

                # Rate limiting
                await asyncio.sleep(0.3)

            # Log results
            logger.info(f"✅ Cleanup complete: {stats['removed']}/{stats['found']} removed")
            if stats['failed'] > 0:
                logger.warning(f"⚠️ Failed to remove {stats['failed']} orders")

            return stats

        except Exception as e:
            logger.error(f"Critical error during cleanup: {e}", exc_info=True)
            stats['errors'].append(str(e))
            return stats

    async def _cancel_order_safe(self, zombie: BinanceZombieOrder) -> bool:
        """
        Safely cancel order with Binance error handling

        Args:
            zombie: Zombie order to cancel

        Returns:
            True if successfully cancelled
        """
        max_retries = 3

        for attempt in range(max_retries):
            try:
                await self.check_and_wait_rate_limit('cancel_order')

                # CRITICAL FIX: Log detailed information BEFORE cancelling
                logger.warning(
                    f"🧟 DELETING ORDER: {zombie.order_id} on {zombie.symbol}\n"
                    f"  Type: {zombie.order_type}, Side: {zombie.side}, Amount: {zombie.amount}\n"
                    f"  Zombie Type: {zombie.zombie_type}, Reason: {zombie.reason}\n"
                    f"  ⚠️ IF THIS IS A STOP-LOSS - CRITICAL BUG!"
                )

                if hasattr(self.exchange, 'cancel_order'):
                    result = await self.exchange.cancel_order(zombie.order_id, zombie.symbol)
                else:
                    result = self.exchange.cancel_order(zombie.order_id, zombie.symbol)

                logger.info(f"✅ Cancelled {zombie.zombie_type} order {zombie.order_id}")
                return True

            except Exception as e:
                error_str = str(e)

                # Binance specific error codes - order already gone
                if any(code in error_str for code in ['-2011', '-2013', 'Unknown order', 'does not exist']):
                    logger.info(f"Order {zombie.order_id} already cancelled/filled")
                    return True

                # Rate limit error
                if '-1003' in error_str or 'Too many requests' in error_str:
                    logger.warning("Rate limit hit, waiting 60s")
                    await asyncio.sleep(60)
                    self.weight_used = 0
                    continue

                # Retry logic
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to cancel {zombie.order_id} after {max_retries} attempts: {e}")
                    return False

        return False

    async def _cancel_oco_order(self, zombie: BinanceZombieOrder) -> bool:
        """
        Special handling for OCO order cancellation

        Args:
            zombie: OCO zombie order

        Returns:
            True if successfully cancelled
        """
        try:
            await self.check_and_wait_rate_limit('cancel_order')

            # Try native Binance OCO cancel
            if hasattr(self.exchange, 'private_delete_order_list'):
                market = self.exchange.market(zombie.symbol)
                response = await self.exchange.private_delete_order_list({
                    'symbol': market['id'],
                    'orderListId': zombie.order_list_id
                })
                logger.info(f"✅ Cancelled OCO list {zombie.order_list_id}")
                return True
            else:
                # Fallback to regular cancel
                return await self._cancel_order_safe(zombie)

        except Exception as e:
            error_str = str(e)

            # OCO already cancelled
            if any(code in error_str for code in ['-2011', '-2013']):
                logger.info(f"OCO {zombie.order_list_id} already cancelled")
                return True

            logger.error(f"Failed to cancel OCO {zombie.order_list_id}: {e}")

            # Try fallback - cancel individual order
            return await self._cancel_order_safe(zombie)

    def get_metrics(self) -> Dict:
        """
        Get performance metrics

        Returns:
            Dictionary of metrics
        """
        return {
            'binance_specific': {
                'empty_responses': self.metrics['empty_responses'],
                'rate_limit_waits': self.metrics['rate_limit_waits'],
                'error_2011_count': self.metrics['error_2011_count'],
                'error_2013_count': self.metrics['error_2013_count'],
                'oco_handled': self.metrics['oco_handled'],
                'zombies_cleaned': self.metrics['zombies_cleaned'],
                'async_delays_detected': self.metrics['async_delays_detected'],
                'current_weight': f"{self.weight_used}/{self.WEIGHT_LIMIT}",
                'health': self._calculate_health()
            }
        }

    def _calculate_health(self) -> str:
        """Calculate health status based on metrics"""
        if self.metrics['rate_limit_waits'] > 10:
            return 'CRITICAL - Too many rate limits'
        elif self.metrics['empty_responses'] > 50:
            return 'WARNING - Many empty responses'
        elif self.metrics['error_2011_count'] + self.metrics['error_2013_count'] > 20:
            return 'WARNING - Many phantom orders'
        elif self.weight_used > 1000:
            return 'WARNING - High API weight usage'
        return 'OK'

    def reset_metrics(self):
        """Reset metrics counters"""
        self.metrics = {
            'empty_responses': 0,
            'rate_limit_waits': 0,
            'error_2011_count': 0,
            'error_2013_count': 0,
            'oco_handled': 0,
            'zombies_cleaned': 0,
            'async_delays_detected': 0,
        }
        logger.info("Metrics reset")


# Integration helper for existing position_manager
class BinanceZombieIntegration:
    """
    Integration wrapper for existing position_manager.py
    Provides seamless integration without breaking existing code
    """

    def __init__(self, exchange_connector):
        """Initialize with existing exchange manager or direct ccxt exchange"""
        self.exchange_connector = exchange_connector
        self.binance_managers = {}
        self.manager = None  # For direct exchange access

        # Handle both ExchangeManager and direct ccxt exchange
        if hasattr(exchange_connector, 'exchanges'):
            # ExchangeManager passed - iterate through exchanges
            for name, exchange in exchange_connector.exchanges.items():
                if 'binance' in name.lower():
                    self.binance_managers[name] = BinanceZombieManager(exchange)
                    logger.info(f"✅ BinanceZombieManager initialized for {name}")
        else:
            # Direct ccxt exchange passed (from position_manager or tests)
            self.manager = BinanceZombieManager(exchange_connector)
            self.binance_managers['binance'] = self.manager
            logger.info(f"✅ BinanceZombieManager initialized for direct exchange")

    async def enable_zombie_protection(self):
        """Enable zombie order protection for all managed exchanges"""
        logger.info("🛡️ Enabling zombie order protection for Binance exchanges")
        # Protection is enabled by default through the manager initialization
        return True

    async def cleanup_zombies(self, dry_run: bool = False) -> Dict:
        """
        Main cleanup method for compatibility with position_manager and tests

        Args:
            dry_run: If True, only detect but don't cancel

        Returns:
            Cleanup results with standard fields
        """
        # Use the enhanced cleanup internally
        detailed_results = await self.cleanup_zombie_orders_enhanced(
            symbols=None,
            dry_run=dry_run,
            aggressive=False
        )

        # Aggregate results for simple interface
        total_found = 0
        total_cancelled = 0
        total_errors = []
        total_weight = 0
        empty_responses = 0
        async_delays = 0
        oco_handled = 0
        zombie_details = []

        for exchange_name, result in detailed_results.items():
            if isinstance(result, dict):
                total_found += result.get('zombies_found', 0)
                total_cancelled += result.get('zombies_cancelled', 0)
                total_errors.extend(result.get('errors', []))

                metrics = result.get('metrics', {})
                total_weight += metrics.get('weight_used', 0)
                empty_responses += metrics.get('empty_responses', 0)
                async_delays += metrics.get('async_delays', 0)
                oco_handled += result.get('oco_orders', 0)

                # Collect zombie details for display
                if result.get('zombie_orders'):
                    zombie_details.extend(result['zombie_orders'])

        return {
            'zombie_orders_found': total_found,
            'zombie_orders_cancelled': total_cancelled,
            'oco_orders_handled': oco_handled,
            'weight_used': total_weight,
            'empty_responses_mitigated': empty_responses,
            'async_delays_detected': async_delays,
            'errors': total_errors,
            'zombie_details': zombie_details[:10]  # First 10 for display
        }

    async def get_metrics(self) -> Dict:
        """Get aggregated metrics from all managers"""
        metrics = {
            'total_cleanups': 0,
            'total_zombies_found': 0,
            'total_zombies_cleaned': 0,
            'empty_responses': 0,
            'cache_hits': 0
        }

        for manager in self.binance_managers.values():
            manager_metrics = manager.get_metrics()
            metrics['total_cleanups'] += manager_metrics.get('total_cleanups', 0)
            metrics['total_zombies_found'] += manager_metrics.get('total_zombies_found', 0)
            metrics['total_zombies_cleaned'] += manager_metrics.get('total_zombies_cleaned', 0)
            metrics['empty_responses'] += manager_metrics.get('empty_responses', 0)
            metrics['cache_hits'] += manager_metrics.get('cache_hits', 0)

        return metrics

    async def cleanup_zombie_orders_enhanced(self, symbols: List[str] = None,
                                            dry_run: bool = False,
                                            aggressive: bool = False) -> Dict:
        """
        Enhanced zombie cleanup specifically for Binance

        Args:
            symbols: Optional list of symbols to check
            dry_run: If True, only detect but don't cancel
            aggressive: If True, skip async delay checks

        Returns:
            Cleanup results by exchange
        """
        if not self.binance_managers:
            logger.warning("No Binance exchanges found for zombie cleanup")
            return {'message': 'No Binance exchanges configured'}

        all_results = {}

        for exchange_name, manager in self.binance_managers.items():
            logger.info(f"🔧 Running Binance zombie cleanup for {exchange_name}")

            try:
                results = await manager.cleanup_zombie_orders(
                    dry_run=dry_run,
                    aggressive=aggressive
                )
                all_results[exchange_name] = results

                # Log metrics
                metrics = manager.get_metrics()
                logger.info(f"📊 {exchange_name} metrics: {metrics['binance_specific']}")

            except Exception as e:
                logger.error(f"❌ {exchange_name} cleanup failed: {e}")
                all_results[exchange_name] = {'error': str(e)}

        return all_results

    def enhance_fetch_open_orders(self):
        """
        Replace fetch_open_orders with safe version for all Binance exchanges
        """
        for name, manager in self.binance_managers.items():
            exchange = self.exchange_manager.exchanges[name]

            # Store original method
            original_fetch = exchange.exchange.fetch_open_orders

            # Replace with safe version
            exchange.exchange.fetch_open_orders = manager.fetch_open_orders_safe

            logger.info(f"✅ Enhanced fetch_open_orders for {name}")


# Convenience function for quick integration
async def setup_binance_zombie_protection(position_manager):
    """
    Quick setup function to add Binance zombie protection to existing bot

    Args:
        position_manager: Existing PositionManager instance
    """
    try:
        # Check for Binance exchanges
        binance_exchanges = [
            name for name in position_manager.exchanges.keys()
            if 'binance' in name.lower()
        ]

        if not binance_exchanges:
            logger.info("No Binance exchanges found, skipping zombie protection setup")
            return

        logger.info(f"Setting up Binance zombie protection for: {binance_exchanges}")

        # Create integration wrapper
        integration = BinanceZombieIntegration(position_manager)

        # Enhance fetch_open_orders
        integration.enhance_fetch_open_orders()

        # Store reference in position_manager
        position_manager.binance_zombie_integration = integration

        logger.info("✅ Binance zombie protection fully activated")

        # Log initial metrics
        for name, manager in integration.binance_managers.items():
            metrics = manager.get_metrics()
            logger.info(f"📊 Initial metrics for {name}: {metrics}")

        return integration

    except Exception as e:
        logger.error(f"Failed to setup Binance zombie protection: {e}")
        return None