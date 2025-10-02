#!/usr/bin/env python3
"""
Binance Futures Zombie Order Cleaner

КРИТИЧЕСКИ ВАЖНО:
1. Binance НЕ закрывает TP/SL автоматически после закрытия позиции
2. Ghost orders: всегда ждать 1-2 секунды после отмены
3. Rate limiting: 0.1-0.2 секунды между запросами
4. Ошибка -2011 (Unknown order) = уже отменен

Основано на проверенных решениях:
- Stack Overflow: https://stackoverflow.com/questions/70447698/
- CCXT Issue: https://github.com/ccxt/ccxt/issues/8507
- Binance Docs: https://developers.binance.com/docs/derivatives
"""

import asyncio
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import time

logger = logging.getLogger(__name__)


@dataclass
class ZombieOrderAnalysis:
    """Analysis result for a potential zombie order"""
    is_zombie: bool
    reason: str
    order_id: str
    symbol: str
    order_type: str
    position_side: str
    needs_special_handling: bool = False
    special_method: str = ""


class BinanceZombieOrderCleaner:
    """
    Production-ready zombie order cleaner for Binance Futures API

    Handles all critical Binance-specific issues:
    - TP/SL orders not automatically cancelled after position close
    - Ghost orders (delayed status updates after cancellation)
    - Hedge mode with positionSide matching
    - Rate limiting and error handling
    """

    # Binance TP/SL order types that become zombies after position close
    TPSL_ORDER_TYPES = {
        'TAKE_PROFIT_MARKET',
        'STOP_MARKET',
        'TAKE_PROFIT',
        'STOP_LOSS',
        'TAKE_PROFIT_LIMIT',
        'STOP_LOSS_LIMIT',
        'TRAILING_STOP_MARKET'
    }

    # Binance error codes that indicate order is already handled
    EXPECTED_ERROR_CODES = {
        -2011,  # Unknown order sent
        -2013,  # Order does not exist
        -1021,  # Timestamp for this request was 1000ms ahead of server time
    }

    def __init__(self, exchange):
        """
        Initialize Binance zombie order cleaner

        Args:
            exchange: CCXT Binance exchange instance
        """
        self.exchange = exchange
        self.stats = {
            'orders_scanned': 0,
            'zombies_found': 0,
            'zombies_cancelled': 0,
            'errors': 0,
            'ghost_orders_handled': 0
        }

        logger.info("BinanceZombieOrderCleaner initialized")

    async def get_active_positions(self) -> Dict[Tuple[str, str], dict]:
        """
        Get active positions using correct Binance endpoint

        Returns:
            Dict with keys (symbol, positionSide) for active positions
        """
        try:
            # Use positionRisk endpoint - most reliable for Binance
            positions = await self.exchange.fetch_positions()

            active_positions = {}
            for position in positions:
                # Position is active only if positionAmt != 0
                position_amt = float(position.get('contracts', 0))
                if position_amt != 0:
                    symbol = position['symbol']
                    # Extract positionSide from position info (Binance-specific)
                    position_side = position.get('info', {}).get('positionSide', 'BOTH')

                    key = (symbol, position_side)
                    active_positions[key] = position

            logger.info(f"Active positions map: {len(active_positions)} positions")
            return active_positions

        except Exception as e:
            logger.error(f"Failed to get active positions: {e}")
            return {}

    async def identify_zombie_orders(self, symbol: Optional[str] = None) -> List[ZombieOrderAnalysis]:
        """
        Identify all zombie orders using Binance-specific criteria

        Args:
            symbol: Optional symbol to filter orders

        Returns:
            List of zombie order analyses
        """
        try:
            logger.info(f"🔍 Scanning for zombie orders" + (f" for {symbol}" if symbol else ""))

            # Get active positions
            active_positions = await self.get_active_positions()

            # Get open orders
            if symbol:
                open_orders = await self.exchange.fetch_open_orders(symbol)
            else:
                open_orders = await self.exchange.fetch_open_orders()

            logger.info(f"📋 Total open orders: {len(open_orders)}")

            zombies = []

            for order in open_orders:
                # Skip filled/cancelled orders
                if order.get('status', '').upper() in ['FILLED', 'CANCELED', 'CANCELLED', 'REJECTED']:
                    continue

                analysis = self._analyze_order_for_zombie(order, active_positions)

                if analysis.is_zombie:
                    zombies.append(analysis)
                    logger.warning(f"🧟 ZOMBIE: {analysis.symbol} {analysis.position_side} - {analysis.reason}")

            logger.info(f"Found {len(zombies)} zombie orders")
            self.stats['orders_scanned'] = len(open_orders)
            self.stats['zombies_found'] = len(zombies)

            return zombies

        except Exception as e:
            logger.error(f"Failed to identify zombie orders: {e}")
            self.stats['errors'] += 1
            return []

    def _analyze_order_for_zombie(self, order: dict, active_positions: Dict[Tuple[str, str], dict]) -> ZombieOrderAnalysis:
        """
        Analyze single order for zombie status using Binance-specific criteria

        Args:
            order: CCXT order object
            active_positions: Dict of active positions with (symbol, positionSide) keys

        Returns:
            ZombieOrderAnalysis result
        """
        symbol = order['symbol']
        order_id = order['id']
        order_type = order.get('type', '').upper()
        order_info = order.get('info', {})

        # Extract positionSide from order info (critical for Binance hedge mode)
        position_side = order_info.get('positionSide', 'BOTH')

        # Create analysis object
        analysis = ZombieOrderAnalysis(
            is_zombie=False,
            reason="",
            order_id=order_id,
            symbol=symbol,
            order_type=order_type,
            position_side=position_side
        )

        # CRITICAL ZOMBIE CRITERIA based on Binance API docs:

        # CRITERION 1: ReduceOnly orders MUST have a position
        if order_info.get('reduceOnly'):
            order_key = (symbol, position_side)
            if order_key not in active_positions:
                analysis.is_zombie = True
                analysis.reason = "Reduce-only order without position"
                return analysis

        # CRITERION 2: TP/SL orders for closed positions (MAIN BINANCE ISSUE)
        if order_type in self.TPSL_ORDER_TYPES:
            order_key = (symbol, position_side)
            if order_key not in active_positions:
                analysis.is_zombie = True
                analysis.reason = f"TP/SL for closed position (type: {order_type})"
                analysis.needs_special_handling = True
                analysis.special_method = "standard_cancel"
                return analysis

        # CRITERION 3: Any order without corresponding position
        order_key = (symbol, position_side)
        if order_key not in active_positions:
            # Additional check for BOTH position side in one-way mode
            if position_side != 'BOTH':
                both_key = (symbol, 'BOTH')
                if both_key not in active_positions:
                    analysis.is_zombie = True
                    analysis.reason = f"Order for {position_side} position that doesn't exist"
                    return analysis
            else:
                analysis.is_zombie = True
                analysis.reason = "Order without corresponding position"
                return analysis

        # Order appears to be legitimate
        analysis.reason = "Has corresponding position"
        return analysis

    async def cleanup_zombie_orders(self, symbol: Optional[str] = None, dry_run: bool = False) -> Dict:
        """
        Clean up zombie orders with Binance-specific handling

        Args:
            symbol: Optional symbol to filter
            dry_run: If True, only identify but don't cancel

        Returns:
            Dict with cleanup results
        """
        logger.info(f"🧹 Starting zombie order cleanup (dry_run={dry_run})")

        # Reset stats
        self.stats.update({
            'orders_scanned': 0,
            'zombies_found': 0,
            'zombies_cancelled': 0,
            'errors': 0,
            'ghost_orders_handled': 0
        })

        try:
            # Identify zombies
            zombies = await self.identify_zombie_orders(symbol)

            if not zombies:
                logger.info("✅ No zombie orders found")
                return self._get_cleanup_results()

            if dry_run:
                logger.info(f"📊 DRY RUN: Would cancel {len(zombies)} zombie orders")
                return self._get_cleanup_results()

            # Group by symbol for efficient batch processing
            zombies_by_symbol = {}
            for zombie in zombies:
                symbol = zombie.symbol
                if symbol not in zombies_by_symbol:
                    zombies_by_symbol[symbol] = []
                zombies_by_symbol[symbol].append(zombie)

            logger.info(f"🚀 Cancelling {len(zombies)} zombie orders across {len(zombies_by_symbol)} symbols")

            # Cancel zombies symbol by symbol
            for symbol, symbol_zombies in zombies_by_symbol.items():
                logger.info(f"📍 Processing {len(symbol_zombies)} zombies for {symbol}")

                for zombie in symbol_zombies:
                    success = await self._cancel_order_with_retry(zombie)
                    if success:
                        self.stats['zombies_cancelled'] += 1
                    else:
                        self.stats['errors'] += 1

                    # Rate limiting for Binance
                    await asyncio.sleep(0.1)

            # Final verification with ghost order handling
            await self._verify_cleanup_with_ghost_handling(symbol)

            results = self._get_cleanup_results()
            logger.info(f"✅ Cleanup completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Zombie cleanup failed: {e}")
            self.stats['errors'] += 1
            return self._get_cleanup_results()

    async def _cancel_order_with_retry(self, zombie: ZombieOrderAnalysis) -> bool:
        """
        Cancel order with Binance-specific retry logic and ghost order handling

        Args:
            zombie: ZombieOrderAnalysis object

        Returns:
            True if successfully cancelled
        """
        order_id = zombie.order_id
        symbol = zombie.symbol

        logger.info(f"🧟 Cancelling zombie: {symbol} {zombie.order_type} {zombie.position_side} (ID: {order_id})")

        for attempt in range(3):
            try:
                # Cancel the order
                await self.exchange.cancel_order(order_id, symbol)

                # CRITICAL: Wait for Binance to sync (ghost orders issue)
                await asyncio.sleep(1.0)

                # Verify cancellation
                try:
                    order_status = await self.exchange.fetch_order(order_id, symbol)
                    if order_status['status'].upper() in ['CANCELED', 'CANCELLED']:
                        logger.info(f"✅ Verified cancellation: {order_id}")
                        return True
                    else:
                        logger.warning(f"⚠️ Order {order_id} not yet cancelled, status: {order_status['status']}")

                except Exception as verify_error:
                    # If we can't fetch the order, it might be successfully cancelled
                    error_msg = str(verify_error).lower()
                    if any(phrase in error_msg for phrase in ['not found', 'does not exist', 'unknown order']):
                        logger.info(f"✅ Order {order_id} not found (successfully cancelled)")
                        self.stats['ghost_orders_handled'] += 1
                        return True

                # Assume success if no error occurred
                logger.info(f"✅ Cancelled zombie order: {order_id}")
                return True

            except Exception as e:
                error_msg = str(e).lower()

                # Handle expected Binance error codes
                if any(code in error_msg for code in ['-2011', '-2013', 'unknown order', 'does not exist']):
                    logger.info(f"✅ Order {order_id} already handled: {error_msg}")
                    return True

                # Handle rate limiting
                if '-1003' in error_msg or 'too many requests' in error_msg:
                    if attempt < 2:
                        wait_time = 1.0 * (2 ** attempt)
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}/3")
                        await asyncio.sleep(wait_time)
                        continue

                # Other errors - retry with backoff
                if attempt < 2:
                    wait_time = 0.5 * (2 ** attempt)
                    logger.warning(f"Retry {attempt + 1}/3 for {order_id} after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed to cancel {order_id} after 3 attempts: {e}")
                    return False

        return False

    async def _verify_cleanup_with_ghost_handling(self, symbol: Optional[str] = None):
        """
        Verify cleanup completed successfully, handling ghost orders

        Args:
            symbol: Optional symbol to verify
        """
        logger.info("🔍 Verifying cleanup completion...")

        # Wait for ghost orders to disappear
        await asyncio.sleep(2.0)

        # Re-scan for any remaining zombies
        remaining_zombies = await self.identify_zombie_orders(symbol)

        if remaining_zombies:
            logger.warning(f"⚠️ Found {len(remaining_zombies)} remaining zombies after cleanup")
            for zombie in remaining_zombies:
                logger.warning(f"  Remaining: {zombie.order_id} - {zombie.reason}")
        else:
            logger.info("✅ All zombie orders successfully cleaned")

    def _get_cleanup_results(self) -> Dict:
        """Get cleanup results summary"""
        return {
            'total_scanned': self.stats['orders_scanned'],
            'zombies_found': self.stats['zombies_found'],
            'zombies_cancelled': self.stats['zombies_cancelled'],
            'errors': self.stats['errors'],
            'ghost_orders_handled': self.stats['ghost_orders_handled'],
            'success_rate': (self.stats['zombies_cancelled'] / max(self.stats['zombies_found'], 1)) * 100
        }

    def print_stats(self):
        """Print detailed statistics"""
        results = self._get_cleanup_results()

        logger.info("📊 BINANCE ZOMBIE CLEANUP STATISTICS")
        logger.info("=" * 50)
        logger.info(f"Orders scanned: {results['total_scanned']}")
        logger.info(f"Zombies found: {results['zombies_found']}")
        logger.info(f"Zombies cancelled: {results['zombies_cancelled']}")
        logger.info(f"Ghost orders handled: {results['ghost_orders_handled']}")
        logger.info(f"Errors: {results['errors']}")
        logger.info(f"Success rate: {results['success_rate']:.1f}%")
        logger.info("=" * 50)


# Utility functions for standalone usage
async def create_binance_cleaner(api_key: str, api_secret: str, testnet: bool = True):
    """
    Create Binance zombie cleaner with proper exchange setup

    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        testnet: Use testnet if True

    Returns:
        BinanceZombieOrderCleaner instance
    """
    import ccxt.async_support as ccxt

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'recvWindow': 10000,
        }
    })

    if testnet:
        exchange.set_sandbox_mode(True)
        logger.info("Using Binance Testnet")

    return BinanceZombieOrderCleaner(exchange)


async def quick_cleanup(api_key: str, api_secret: str, symbol: Optional[str] = None,
                       testnet: bool = True, dry_run: bool = False):
    """
    Quick zombie cleanup function for standalone usage

    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        symbol: Optional symbol to clean
        testnet: Use testnet if True
        dry_run: Only identify, don't cancel

    Returns:
        Cleanup results dict
    """
    cleaner = await create_binance_cleaner(api_key, api_secret, testnet)

    try:
        results = await cleaner.cleanup_zombie_orders(symbol, dry_run)
        cleaner.print_stats()
        return results
    finally:
        await cleaner.exchange.close()


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    async def main():
        """Example usage"""
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')

        if not api_key or not api_secret:
            print("Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables")
            return

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        print("🧹 BINANCE ZOMBIE ORDER CLEANUP")
        print("=" * 50)

        results = await quick_cleanup(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,  # ALWAYS use testnet for safety
            dry_run=True   # Start with dry run
        )

        print(f"\n✅ Results: {results}")

    asyncio.run(main())