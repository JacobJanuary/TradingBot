"""
Enhanced Zombie Order Manager
Production-safe module for detecting and removing zombie orders
Surgical integration without breaking existing functionality
"""

from typing import Dict, List, Set, Optional, Tuple
import logging
import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ZombieOrderInfo:
    """Information about a detected zombie order"""
    order_id: str
    symbol: str
    exchange: str
    order_type: str
    side: str
    amount: float
    price: float
    reason: str
    positionIdx: int = 0
    is_conditional: bool = False
    is_tpsl: bool = False


class EnhancedZombieOrderManager:
    """
    Enhanced zombie order detection and cleanup
    Integrates seamlessly with existing position_manager
    """

    def __init__(self, exchange_manager):
        """
        Initialize with existing exchange manager

        Args:
            exchange_manager: ExchangeManager instance from position_manager
        """
        self.exchange = exchange_manager
        self.category = 'linear'  # For perpetual futures

        # Statistics
        self.stats = {
            'last_check': None,
            'zombies_detected': 0,
            'zombies_cleaned': 0,
            'errors': [],
            'check_count': 0
        }

        # Cache for performance
        self._position_cache = {}
        self._cache_timestamp = None
        self._cache_lifetime = 30  # seconds

        logger.info(f"EnhancedZombieOrderManager initialized for {exchange_manager.name}")

    async def _get_active_positions_cached(self) -> Dict[Tuple[str, int], Dict]:
        """
        Get active positions with caching to reduce API calls
        Returns: Dict with (symbol, positionIdx) as key
        """
        now = time.time()

        # Check cache validity
        if self._cache_timestamp and (now - self._cache_timestamp) < self._cache_lifetime:
            return self._position_cache

        # Fetch fresh positions
        try:
            positions = await self.exchange.fetch_positions()
            self._position_cache = {}

            for pos in positions:
                # Positions are dictionaries from exchange_manager
                contracts = pos.get('contracts', 0)
                if contracts > 0:
                    symbol = pos.get('symbol')
                    # Extract positionIdx for Bybit (hedge mode support)
                    position_idx = 0
                    if pos.get('info'):
                        position_idx = int(pos['info'].get('positionIdx', 0))

                    key = (symbol, position_idx)
                    self._position_cache[key] = {
                        'symbol': symbol,
                        'side': pos.get('side'),
                        'quantity': contracts,
                        'entry_price': pos.get('entryPrice') or pos.get('markPrice'),
                        'positionIdx': position_idx
                    }

            self._cache_timestamp = now
            logger.debug(f"Position cache updated: {len(self._position_cache)} active positions")

        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            # Return stale cache if available
            if self._position_cache:
                logger.warning("Using stale position cache due to fetch error")

        return self._position_cache

    async def detect_zombie_orders(self, use_cache: bool = True) -> List[ZombieOrderInfo]:
        """
        Detect zombie orders with enhanced criteria

        Args:
            use_cache: Whether to use position cache (faster but may miss recent changes)

        Returns:
            List of detected zombie orders
        """
        zombies = []
        self.stats['check_count'] += 1
        self.stats['last_check'] = datetime.now(timezone.utc)

        try:
            # Get active positions
            if use_cache:
                active_positions = await self._get_active_positions_cached()
            else:
                # Force refresh
                self._cache_timestamp = None
                active_positions = await self._get_active_positions_cached()

            active_symbols = {pos[0] for pos in active_positions.keys()}

            # Fetch all open orders with proper pagination for Bybit
            all_orders = await self._fetch_all_open_orders_paginated()

            logger.info(f"🔍 Checking {len(all_orders)} orders against {len(active_symbols)} active positions")

            # Analyze each order
            for order in all_orders:
                zombie_info = self._analyze_order(order, active_positions, active_symbols)
                if zombie_info:
                    zombies.append(zombie_info)
                    self.stats['zombies_detected'] += 1

            if zombies:
                logger.warning(f"🧟 Detected {len(zombies)} zombie orders")
                for z in zombies[:5]:  # Log first 5
                    logger.debug(f"  - {z.symbol} {z.order_type} {z.side}: {z.reason}")
            else:
                logger.info("✨ No zombie orders detected")

        except Exception as e:
            logger.error(f"Error detecting zombie orders: {e}")
            self.stats['errors'].append(f"Detection error: {str(e)[:100]}")

        return zombies

    def _analyze_order(self, order: Dict, active_positions: Dict, active_symbols: Set) -> Optional[ZombieOrderInfo]:
        """
        Analyze single order for zombie criteria

        Returns:
            ZombieOrderInfo if order is a zombie, None otherwise
        """
        # Extract order details
        order_id = order.get('id', '')
        symbol = order.get('symbol', '')
        order_type = order.get('type', '').lower()
        order_status = order.get('status', '').lower()
        side = order.get('side', '')
        amount = float(order.get('amount', 0))
        price = float(order.get('price', 0))

        # Skip already completed orders
        if order_status in ['closed', 'canceled', 'filled', 'rejected', 'expired']:
            return None

        # Extract Bybit-specific info
        order_info = order.get('info', {})
        position_idx = int(order_info.get('positionIdx', 0))
        reduce_only = order_info.get('reduceOnly', False)
        close_on_trigger = order_info.get('closeOnTrigger', False)
        stop_order_type = order_info.get('stopOrderType', '')

        # Key for position lookup
        position_key = (symbol, position_idx)

        # CRITERION 1: Order for symbol without any position
        if symbol not in active_symbols:
            # Special handling for different order types

            if reduce_only:
                return ZombieOrderInfo(
                    order_id=order_id,
                    symbol=symbol,
                    exchange=self.exchange.name,
                    order_type=order_type,
                    side=side,
                    amount=amount,
                    price=price,
                    reason="Reduce-only order without position",
                    positionIdx=position_idx,
                    is_conditional='stop' in order_type or 'conditional' in order_type
                )

            if stop_order_type in ['TakeProfit', 'StopLoss', 'PartialTakeProfit', 'PartialStopLoss']:
                return ZombieOrderInfo(
                    order_id=order_id,
                    symbol=symbol,
                    exchange=self.exchange.name,
                    order_type=order_type,
                    side=side,
                    amount=amount,
                    price=price,
                    reason=f"{stop_order_type} for non-existent position",
                    positionIdx=position_idx,
                    is_tpsl=True
                )

            if close_on_trigger:
                return ZombieOrderInfo(
                    order_id=order_id,
                    symbol=symbol,
                    exchange=self.exchange.name,
                    order_type=order_type,
                    side=side,
                    amount=amount,
                    price=price,
                    reason="CloseOnTrigger order without position",
                    positionIdx=position_idx,
                    is_conditional=True
                )

            # Regular order without position
            if 'stop' not in order_type:  # Don't flag stop orders as zombies yet
                return ZombieOrderInfo(
                    order_id=order_id,
                    symbol=symbol,
                    exchange=self.exchange.name,
                    order_type=order_type,
                    side=side,
                    amount=amount,
                    price=price,
                    reason="Order for symbol without position",
                    positionIdx=position_idx
                )

        # CRITERION 2: Order with wrong positionIdx (hedge mode)
        elif position_key not in active_positions and position_idx != 0:
            return ZombieOrderInfo(
                order_id=order_id,
                symbol=symbol,
                exchange=self.exchange.name,
                order_type=order_type,
                side=side,
                amount=amount,
                price=price,
                reason=f"Wrong positionIdx ({position_idx}) for position",
                positionIdx=position_idx,
                is_conditional='stop' in order_type
            )

        # CRITERION 3: Opposite side order that would open new position
        elif position_key in active_positions:
            position = active_positions[position_key]
            pos_side = position['side'].lower()
            order_side_lower = side.lower()

            # Check if order would open opposite position
            if not reduce_only and not close_on_trigger:
                if (pos_side == 'long' and order_side_lower == 'buy' and
                    amount > position['quantity'] * 1.5):  # Much larger than position
                    return ZombieOrderInfo(
                        order_id=order_id,
                        symbol=symbol,
                        exchange=self.exchange.name,
                        order_type=order_type,
                        side=side,
                        amount=amount,
                        price=price,
                        reason="Order size would flip position",
                        positionIdx=position_idx
                    )

        # Not a zombie
        return None

    async def _fetch_all_open_orders_paginated(self) -> List[Dict]:
        """
        Fetch all open orders with proper pagination handling
        Critical for Bybit which limits to 50 orders per request
        """
        all_orders = []

        try:
            # Try CCXT first (handles pagination internally for some exchanges)
            if hasattr(self.exchange.exchange, 'fetch_open_orders'):
                orders = await self.exchange.exchange.fetch_open_orders()
                return orders

            # Manual pagination for Bybit if needed
            # This is a fallback if CCXT doesn't handle it
            logger.debug("Using manual pagination for orders")
            cursor = None
            page = 0
            max_pages = 20  # Safety limit

            while page < max_pages:
                params = {'limit': 50}
                if cursor:
                    params['cursor'] = cursor

                # Fetch page
                response = await self.exchange.exchange.fetch_open_orders(params=params)

                if not response:
                    break

                all_orders.extend(response)

                # Check for more pages (Bybit specific)
                if len(response) < 50:
                    break  # Last page

                page += 1
                await asyncio.sleep(0.1)  # Rate limiting

            if page >= max_pages:
                logger.warning(f"Reached pagination limit ({max_pages} pages)")

        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            self.stats['errors'].append(f"Fetch error: {str(e)[:100]}")

        return all_orders

    async def cleanup_zombie_orders(self, dry_run: bool = False,
                                   aggressive: bool = False) -> Dict:
        """
        Clean up detected zombie orders

        Args:
            dry_run: If True, only log but don't cancel
            aggressive: If True, use more aggressive cleanup (cancel all for symbol)

        Returns:
            Cleanup statistics
        """
        results = {
            'detected': 0,
            'cancelled': 0,
            'failed': 0,
            'errors': []
        }

        try:
            # Detect zombies
            zombies = await self.detect_zombie_orders(use_cache=not aggressive)
            results['detected'] = len(zombies)

            if not zombies:
                logger.info("No zombie orders to clean")
                return results

            if dry_run:
                logger.info(f"🔍 DRY RUN: Would cancel {len(zombies)} zombie orders")
                for z in zombies:
                    logger.info(f"  [DRY] {z.symbol} {z.order_type} {z.side}: {z.reason}")
                return results

            # Group by handling method
            regular_orders = []
            conditional_orders = []
            tpsl_orders = []
            symbols_for_aggressive = set()

            for zombie in zombies:
                if zombie.is_tpsl:
                    tpsl_orders.append(zombie)
                    if aggressive:
                        symbols_for_aggressive.add(zombie.symbol)
                elif zombie.is_conditional:
                    conditional_orders.append(zombie)
                else:
                    regular_orders.append(zombie)

            # Cancel regular orders
            for zombie in regular_orders:
                success = await self._cancel_order_safe(zombie)
                if success:
                    results['cancelled'] += 1
                    self.stats['zombies_cleaned'] += 1
                else:
                    results['failed'] += 1

                await asyncio.sleep(0.2)  # Rate limiting

            # Cancel conditional orders with special handling
            for zombie in conditional_orders:
                success = await self._cancel_conditional_order(zombie)
                if success:
                    results['cancelled'] += 1
                    self.stats['zombies_cleaned'] += 1
                else:
                    results['failed'] += 1

                await asyncio.sleep(0.2)

            # Handle TP/SL orders
            if tpsl_orders and 'bybit' in self.exchange.name.lower():
                success = await self._clear_tpsl_orders(tpsl_orders)
                if success:
                    results['cancelled'] += len(tpsl_orders)
                    self.stats['zombies_cleaned'] += len(tpsl_orders)

            # Aggressive cleanup for problematic symbols
            if aggressive and symbols_for_aggressive:
                logger.warning(f"🔥 Aggressive cleanup for symbols: {symbols_for_aggressive}")
                for symbol in symbols_for_aggressive:
                    await self._cancel_all_orders_for_symbol(symbol)
                    await asyncio.sleep(0.5)

            # Log results
            logger.info(
                f"🧹 Cleanup complete: {results['cancelled']}/{results['detected']} cancelled, "
                f"{results['failed']} failed"
            )

        except Exception as e:
            logger.error(f"Error in zombie cleanup: {e}")
            results['errors'].append(str(e))

        return results

    async def _cancel_order_safe(self, zombie: ZombieOrderInfo) -> bool:
        """
        Safely cancel a zombie order with retry logic
        """
        max_retries = 3

        for attempt in range(max_retries):
            try:
                await self.exchange.exchange.cancel_order(zombie.order_id, zombie.symbol)
                logger.info(f"✅ Cancelled zombie order {zombie.order_id} for {zombie.symbol}")
                return True

            except Exception as e:
                error_msg = str(e).lower()

                # Order already gone - success
                if any(phrase in error_msg for phrase in [
                    'not found', 'does not exist', 'already cancelled', 'no order'
                ]):
                    logger.debug(f"Order {zombie.order_id} already gone")
                    return True

                # Retry on temporary errors
                if attempt < max_retries - 1:
                    if 'rate limit' in error_msg:
                        await asyncio.sleep(2 ** attempt)
                        continue

                logger.error(f"Failed to cancel {zombie.order_id}: {e}")

        return False

    async def _cancel_conditional_order(self, zombie: ZombieOrderInfo) -> bool:
        """
        Cancel conditional/stop order with special parameters
        """
        try:
            # Use special parameter for conditional orders
            await self.exchange.exchange.cancel_order(
                zombie.order_id,
                zombie.symbol,
                params={'stop': True, 'orderFilter': 'StopOrder'}
            )
            logger.info(f"✅ Cancelled conditional zombie {zombie.order_id}")
            return True

        except Exception as e:
            error_msg = str(e).lower()
            if 'not found' in error_msg or 'does not exist' in error_msg:
                return True

            logger.error(f"Failed to cancel conditional {zombie.order_id}: {e}")
            return False

    async def _clear_tpsl_orders(self, tpsl_zombies: List[ZombieOrderInfo]) -> bool:
        """
        Clear TP/SL orders via trading-stop endpoint (Bybit specific)
        """
        try:
            # Group by symbol and positionIdx
            by_position = {}
            for zombie in tpsl_zombies:
                key = (zombie.symbol, zombie.positionIdx)
                if key not in by_position:
                    by_position[key] = []
                by_position[key].append(zombie)

            # Clear TP/SL for each position
            for (symbol, position_idx), orders in by_position.items():
                try:
                    # Make direct API call for Bybit
                    params = {
                        'category': self.category,
                        'symbol': symbol,
                        'positionIdx': position_idx,
                        'takeProfit': '0',  # Cancel TP
                        'stopLoss': '0'     # Cancel SL
                    }

                    response = await self.exchange.exchange.private_post_v5_position_trading_stop(params)

                    if response.get('retCode') == 0:
                        logger.info(f"✅ Cleared TP/SL for {symbol} positionIdx={position_idx}")

                except Exception as e:
                    logger.error(f"Failed to clear TP/SL for {symbol}: {e}")

                await asyncio.sleep(0.2)

            return True

        except Exception as e:
            logger.error(f"Error clearing TP/SL orders: {e}")
            return False

    async def _cancel_all_orders_for_symbol(self, symbol: str) -> bool:
        """
        Cancel ALL orders for a symbol (aggressive cleanup)
        """
        try:
            # Cancel regular orders
            await self.exchange.exchange.cancel_all_orders(symbol)
            logger.info(f"✅ Cancelled all regular orders for {symbol}")

            # Also try to cancel conditional orders (Bybit specific)
            try:
                await self.exchange.exchange.cancel_all_orders(
                    symbol,
                    params={'orderFilter': 'StopOrder'}
                )
                logger.info(f"✅ Cancelled all stop orders for {symbol}")
            except:
                pass  # Not all exchanges support this

            return True

        except Exception as e:
            logger.error(f"Failed to cancel all orders for {symbol}: {e}")
            return False

    def get_stats(self) -> Dict:
        """Get manager statistics"""
        return {
            'last_check': self.stats['last_check'].isoformat() if self.stats['last_check'] else None,
            'check_count': self.stats['check_count'],
            'total_detected': self.stats['zombies_detected'],
            'total_cleaned': self.stats['zombies_cleaned'],
            'error_count': len(self.stats['errors']),
            'recent_errors': self.stats['errors'][-5:]  # Last 5 errors
        }


# Monitoring helper
class ZombieOrderMonitor:
    """
    Continuous monitoring for zombie orders
    Integrates with health monitoring systems
    """

    def __init__(self, manager: EnhancedZombieOrderManager):
        self.manager = manager
        self.alert_threshold = 10  # Alert if more than 10 zombies
        self.check_interval = 300  # 5 minutes
        self.last_alert = None

    async def monitor_loop(self):
        """Continuous monitoring loop"""
        while True:
            try:
                # Detect zombies
                zombies = await self.manager.detect_zombie_orders()

                # Check if alert needed
                if len(zombies) > self.alert_threshold:
                    await self._send_alert(len(zombies))

                # Auto-cleanup if too many
                if len(zombies) > self.alert_threshold * 2:
                    logger.warning(f"🚨 Auto-cleanup triggered: {len(zombies)} zombies")
                    await self.manager.cleanup_zombie_orders(dry_run=False)

                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(60)

    async def _send_alert(self, zombie_count: int):
        """Send alert about zombie orders"""
        now = time.time()

        # Rate limit alerts
        if self.last_alert and (now - self.last_alert) < 3600:  # 1 hour
            return

        logger.critical(
            f"🚨 ZOMBIE ORDER ALERT: {zombie_count} zombie orders detected! "
            f"Threshold: {self.alert_threshold}"
        )

        self.last_alert = now