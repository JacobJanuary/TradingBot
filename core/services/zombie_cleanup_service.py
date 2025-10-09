"""
Zombie Cleanup Service

Extracted from PositionManager (God Object refactoring)
Handles all zombie order and position cleanup logic.

Responsibilities:
- Handle phantom positions (in DB but not on exchange)
- Handle untracked positions (on exchange but not in DB)
- Clean up zombie orders (limit orders without positions)
- Clean up orphaned stop orders

Date: 2025-10-04
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

from utils.order_helpers import (
    get_order_id, get_order_symbol, get_order_type, 
    get_order_side, get_order_amount
)

logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format for consistent comparison
    
    Converts exchange format 'HIGH/USDT:USDT' to database format 'HIGHUSDT'
    
    Args:
        symbol: Symbol in any format
        
    Returns:
        Normalized symbol (database format)
    """
    if '/' in symbol and ':' in symbol:
        # Exchange format: 'HIGH/USDT:USDT' -> 'HIGHUSDT'
        base_quote = symbol.split(':')[0]  # 'HIGH/USDT'
        return base_quote.replace('/', '')  # 'HIGHUSDT'
    return symbol  # Already normalized (database format)


class ZombieCleanupService:
    """
    Service for cleaning up zombie orders and positions
    """
    
    def __init__(self,
                 repository,
                 exchanges: Dict,
                 sync_interval: int = 600,
                 aggressive_cleanup_threshold: int = 10,
                 moderate_zombie_threshold: int = 5):
        """
        Initialize ZombieCleanupService
        
        Args:
            repository: Database repository
            exchanges: Dict of exchange managers
            sync_interval: Sync interval in seconds
            aggressive_cleanup_threshold: Threshold for aggressive cleanup (critical level)
            moderate_zombie_threshold: Threshold for moderate zombie warning
        """
        self.repository = repository
        self.exchanges = exchanges
        self.sync_interval = sync_interval
        self.aggressive_cleanup_threshold = aggressive_cleanup_threshold
        self.moderate_zombie_threshold = moderate_zombie_threshold
        
        # Tracking
        self.zombie_check_counter = 0
        self.last_zombie_count = 0
    
    async def handle_real_zombies(self, positions: Dict) -> Dict[str, int]:
        """
        Handle REAL zombie positions:
        - PHANTOM: in DB but not on exchange
        - UNTRACKED: on exchange but not in DB
        
        Args:
            positions: Current positions dict {symbol: PositionState}
            
        Returns:
            Dict with counts: {'phantom': N, 'untracked': N}
        """
        try:
            logger.info("🔍 Checking for real zombie positions...")
            
            phantom_count = 0
            untracked_count = 0

            for exchange_name, exchange in self.exchanges.items():
                try:
                    # Get positions from exchange
                    exchange_positions = await exchange.fetch_positions()
                    active_exchange_positions = [p for p in exchange_positions if p['contracts'] > 0]

                    # Get local positions for this exchange
                    # CRITICAL FIX: Use normalized symbols as keys for consistent comparison
                    local_positions = {
                        normalize_symbol(symbol): pos for symbol, pos in positions.items()
                        if pos.exchange == exchange_name
                    }

                    # Create sets for comparison
                    # CRITICAL FIX: Normalize symbols for comparison
                    # Exchange: 'ASTER/USDT:USDT' -> 'ASTERUSDT'
                    # DB: 'ASTERUSDT' -> 'ASTERUSDT'
                    exchange_symbols = {normalize_symbol(p['symbol']) for p in active_exchange_positions}
                    local_symbols = set(local_positions.keys())  # Already normalized

                    # 1. PHANTOM POSITIONS (in DB but not on exchange)
                    phantom_symbols = local_symbols - exchange_symbols

                    if phantom_symbols:
                        phantom_count += len(phantom_symbols)
                        logger.warning(f"👻 Found {len(phantom_symbols)} PHANTOM positions on {exchange_name}")

                        for symbol in phantom_symbols:
                            position = local_positions[symbol]
                            logger.warning(f"Phantom position detected: {symbol} (in DB but not on {exchange_name})")

                            try:
                                # Update database - mark as closed
                                await self.repository.close_position(
                                    position.id,
                                    close_price=position.current_price or 0.0,
                                    pnl=0.0,
                                    pnl_percentage=0.0,
                                    reason='PHANTOM_CLEANUP'
                                )

                                logger.info(f"✅ Cleaned phantom position: {symbol}")

                            except Exception as cleanup_error:
                                logger.error(f"Failed to clean phantom position {symbol}: {cleanup_error}")

                    # 2. UNTRACKED POSITIONS (on exchange but not in DB)
                    untracked_positions = []
                    for ex_pos in active_exchange_positions:
                        # CRITICAL FIX: Use normalized symbol for comparison
                        normalized_ex_symbol = normalize_symbol(ex_pos['symbol'])
                        if normalized_ex_symbol not in local_symbols:
                            untracked_positions.append(ex_pos)

                    if untracked_positions:
                        untracked_count += len(untracked_positions)
                        logger.warning(f"🤖 Found {len(untracked_positions)} UNTRACKED positions on {exchange_name}")

                        for ex_pos in untracked_positions:
                            symbol = ex_pos['symbol']
                            size = ex_pos['contracts']
                            side = ex_pos['side']
                            entry_price = ex_pos.get('entryPrice', 0)

                            logger.warning(f"Untracked position: {symbol} {side} {size} @ {entry_price}")

                            # For now, just log and alert - don't auto-close
                            # Manual decision required
                            logger.critical(f"⚠️ MANUAL REVIEW REQUIRED: Untracked position {symbol} on {exchange_name}")

                            # Save to monitoring table for review
                            if hasattr(self.repository, 'log_untracked_position'):
                                await self.repository.log_untracked_position({
                                    'exchange': exchange_name,
                                    'symbol': symbol,
                                    'side': side,
                                    'size': size,
                                    'entry_price': entry_price,
                                    'detected_at': datetime.now(),
                                    'raw_data': ex_pos
                                })

                except Exception as exchange_error:
                    logger.error(f"Error checking zombies on {exchange_name}: {exchange_error}")

            if phantom_count == 0 and untracked_count == 0:
                logger.info("✅ No zombie positions found")
            
            return {'phantom': phantom_count, 'untracked': untracked_count}

        except Exception as e:
            logger.error(f"Error in zombie position handling: {e}", exc_info=True)
            return {'phantom': 0, 'untracked': 0}

    async def cleanup_zombie_orders(self) -> Dict[str, int]:
        """
        Enhanced zombie order cleanup using specialized cleaners:
        - BybitZombieOrderCleaner for Bybit exchanges
        - BinanceZombieManager for Binance exchanges with weight-based rate limiting
        Falls back to basic cleanup for other exchanges
        
        Returns:
            Dict with counts: {'found': N, 'cleaned': N}
        """
        try:
            cleanup_start_time = asyncio.get_event_loop().time()
            logger.info("🧹 Starting enhanced zombie order cleanup...")
            logger.info(f"📊 Cleanup interval: {self.sync_interval} seconds")
            total_zombies_cleaned = 0
            total_zombies_found = 0

            for exchange_name, exchange in self.exchanges.items():
                try:
                    # Use specialized cleaner for Bybit
                    if 'bybit' in exchange_name.lower():
                        try:
                            from core.bybit_zombie_cleaner import BybitZombieOrderCleaner

                            cleaner = BybitZombieOrderCleaner(exchange.exchange)
                            logger.info(f"🔧 Running advanced Bybit zombie cleanup for {exchange_name}")
                            results = await cleaner.cleanup_zombie_orders(
                                symbols=None,  # Check all symbols
                                category="linear",  # For perpetual futures
                                dry_run=False  # Actually cancel orders
                            )

                            if results['zombies_found'] > 0:
                                logger.warning(
                                    f"🧟 Bybit: Found {results['zombies_found']} zombies, "
                                    f"cancelled {results['zombies_cancelled']}, "
                                    f"TP/SL cleared: {results.get('tpsl_cleared', 0)}"
                                )
                                total_zombies_found += results['zombies_found']
                                total_zombies_cleaned += results['zombies_cancelled']

                                logger.info(f"📈 Zombie cleanup metrics for {exchange_name}:")
                                logger.info(f"  - Detection rate: {results['zombies_found']}/{results.get('total_scanned', 0)} orders")
                                logger.info(f"  - Cleanup success rate: {results['zombies_cancelled']}/{results['zombies_found']}")
                                logger.info(f"  - Errors: {len(results.get('errors', []))}")
                            else:
                                logger.debug(f"✨ No zombie orders found on {exchange_name}")

                            if results.get('errors'):
                                logger.error(f"⚠️ Errors during cleanup: {results['errors'][:3]}")

                        except ImportError as ie:
                            logger.warning(f"BybitZombieOrderCleaner not available, using basic cleanup: {ie}")
                            await self._basic_zombie_cleanup(exchange_name, exchange)

                    # Use specialized cleaner for Binance
                    elif 'binance' in exchange_name.lower():
                        try:
                            from core.binance_zombie_manager import BinanceZombieIntegration

                            integration = BinanceZombieIntegration(exchange.exchange)
                            logger.info(f"🔧 Running advanced Binance zombie cleanup for {exchange_name}")
                            await integration.enable_zombie_protection()
                            results = await integration.cleanup_zombies(dry_run=False)

                            if results['zombie_orders_found'] > 0:
                                logger.warning(
                                    f"🧟 Binance: Found {results['zombie_orders_found']} zombies, "
                                    f"cancelled {results['zombie_orders_cancelled']}, "
                                    f"OCO handled: {results.get('oco_orders_handled', 0)}"
                                )
                                total_zombies_found += results['zombie_orders_found']
                                total_zombies_cleaned += results['zombie_orders_cancelled']

                                logger.info(f"📈 Zombie cleanup metrics for {exchange_name}:")
                                logger.info(f"  - Empty responses mitigated: {results.get('empty_responses_mitigated', 0)}")
                                logger.info(f"  - API weight used: {results.get('weight_used', 0)}")
                                logger.info(f"  - Async delays detected: {results.get('async_delays_detected', 0)}")
                                logger.info(f"  - Errors: {len(results.get('errors', []))}")
                            else:
                                logger.debug(f"✨ No zombie orders found on {exchange_name}")

                            if results.get('weight_used', 0) > 900:
                                logger.warning(f"⚠️ Binance API weight high: {results['weight_used']}/1200")

                        except ImportError as ie:
                            logger.warning(f"BinanceZombieManager not available, using basic cleanup: {ie}")
                            await self._basic_zombie_cleanup(exchange_name, exchange)

                    else:
                        # Use basic cleanup for other exchanges
                        cleaned = await self._basic_zombie_cleanup(exchange_name, exchange)
                        if cleaned > 0:
                            total_zombies_found += cleaned
                            total_zombies_cleaned += cleaned

                except Exception as exchange_error:
                    logger.error(f"Error cleaning zombie orders on {exchange_name}: {exchange_error}")

            # Log final summary with timing
            cleanup_duration = asyncio.get_event_loop().time() - cleanup_start_time

            # Update zombie tracking
            self.zombie_check_counter += 1
            self.last_zombie_count = total_zombies_found

            if total_zombies_found > 0:
                logger.warning(f"⚠️ ZOMBIE CLEANUP SUMMARY:")
                logger.warning(f"  🧟 Total found: {total_zombies_found}")
                logger.warning(f"  ✅ Total cleaned: {total_zombies_cleaned}")
                logger.warning(f"  ❌ Failed to clean: {total_zombies_found - total_zombies_cleaned}")
                logger.warning(f"  ⏱️ Duration: {cleanup_duration:.2f} seconds")
                logger.warning(f"  📊 Check #: {self.zombie_check_counter}")

                # Alert and adjust if too many zombies
                if total_zombies_found > self.aggressive_cleanup_threshold:
                    logger.critical(f"🚨 HIGH ZOMBIE COUNT DETECTED: {total_zombies_found} zombies!")
                    logger.critical(f"🔄 Temporarily reducing sync interval from {self.sync_interval}s to 300s")
                    self.sync_interval = min(300, self.sync_interval)
                    logger.critical("📢 Manual intervention may be required - check exchange UI")
                elif total_zombies_found > self.moderate_zombie_threshold:
                    logger.warning(f"⚠️ Moderate zombie count: {total_zombies_found}")
                    if self.sync_interval > 300:
                        self.sync_interval = 450  # 7.5 minutes
                        logger.info(f"📉 Reduced sync interval to {self.sync_interval}s")
            else:
                logger.info(f"✨ No zombie orders found (check #{self.zombie_check_counter}, duration: {cleanup_duration:.2f}s)")

                # Gradually increase interval if no zombies found for multiple checks
                if self.zombie_check_counter > 3 and self.last_zombie_count == 0:
                    if self.sync_interval < 600:
                        self.sync_interval = min(600, self.sync_interval + 60)
                        logger.info(f"📈 Increased sync interval back to {self.sync_interval}s")

            return {'found': total_zombies_found, 'cleaned': total_zombies_cleaned}

        except Exception as e:
            logger.error(f"Error in enhanced zombie order cleanup: {e}")
            return {'found': 0, 'cleaned': 0}

    async def _basic_zombie_cleanup(self, exchange_name: str, exchange) -> int:
        """
        Basic zombie order cleanup for non-Bybit exchanges
        Returns number of orders cancelled
        """
        cancelled_count = 0

        try:
            # Get all open orders from exchange
            open_orders = await exchange.exchange.fetch_open_orders()

            # Get current positions
            positions = await exchange.fetch_positions()
            position_symbols = {p.get('symbol') for p in positions if p.get('contracts', 0) > 0}

            # Find zombie orders (orders for symbols without positions)
            zombie_orders = []
            for order in open_orders:
                # Use unified order accessor (handles both dict and OrderResult)
                symbol = get_order_symbol(order)
                order_type = (get_order_type(order) or '').lower()

                # Check if this is a limit order for a symbol without position
                if symbol and symbol not in position_symbols:
                    # Skip stop orders as they might be protective orders
                    if 'stop' not in order_type and 'limit' in order_type:
                        zombie_orders.append(order)

            if zombie_orders:
                logger.warning(f"🧟 Found {len(zombie_orders)} zombie orders on {exchange_name}")

                # Cancel zombie orders
                for order in zombie_orders:
                    try:
                        # Use unified order accessors (handles both dict and OrderResult)
                        symbol = get_order_symbol(order)
                        order_id = get_order_id(order)
                        order_side = get_order_side(order)
                        order_amount = get_order_amount(order)

                        logger.info(f"Cancelling zombie order: {symbol} {order_side} {order_amount} (ID: {order_id})")
                        await exchange.exchange.cancel_order(order_id, symbol)
                        logger.info(f"✅ Cancelled zombie order {order_id} for {symbol}")
                        cancelled_count += 1

                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.5)

                    except Exception as cancel_error:
                        order_id = get_order_id(order) or 'unknown'
                        logger.error(f"Failed to cancel zombie order {order_id}: {cancel_error}")

            # Also check for orphaned stop orders
            stop_orders = []
            for o in open_orders:
                order_type = (get_order_type(o) or '').lower()
                if 'stop' in order_type:
                    stop_orders.append(o)
            
            orphaned_stops = []
            for order in stop_orders:
                symbol = get_order_symbol(order)
                if symbol and symbol not in position_symbols:
                    orphaned_stops.append(order)

            if orphaned_stops:
                logger.warning(f"🛑 Found {len(orphaned_stops)} orphaned stop orders on {exchange_name}")

                for order in orphaned_stops:
                    try:
                        symbol = get_order_symbol(order)
                        order_id = get_order_id(order)

                        logger.info(f"Cancelling orphaned stop order for {symbol} (ID: {order_id})")
                        await exchange.exchange.cancel_order(order_id, symbol)
                        logger.info(f"✅ Cancelled orphaned stop order {order_id}")
                        cancelled_count += 1

                        await asyncio.sleep(0.5)

                    except Exception as cancel_error:
                        order_id = get_order_id(order) or 'unknown'
                        logger.error(f"Failed to cancel orphaned stop order {order_id}: {cancel_error}")

        except Exception as e:
            logger.error(f"Error in basic zombie cleanup for {exchange_name}: {e}")

        return cancelled_count

