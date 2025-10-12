"""
Production-ready Bybit Zombie Order Cleaner
Based on verified solutions from:
- Freqtrade Issue #9273: https://github.com/freqtrade/freqtrade/issues/9273
- CCXT PR #13116: https://github.com/ccxt/ccxt/pull/13116
- Bybit API v5 Documentation: https://bybit-exchange.github.io/docs/v5/
- Stack Overflow: https://stackoverflow.com/questions/77339832/
"""

import ccxt.async_support as ccxt
import logging
import asyncio
import time
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class ZombieOrderAnalysis:
    """Analysis result for zombie order detection"""
    order_id: str
    symbol: str
    position_idx: int
    order_type: str
    is_zombie: bool
    reason: str
    needs_special_handling: bool = False
    special_method: str = ""


class BybitZombieOrderCleaner:
    """
    Production-ready zombie order cleaner for Bybit API v5

    Handles all critical issues identified in production systems:
    - Conditional orders (status="Untriggered")
    - TP/SL orders via trading-stop endpoint
    - Proper positionIdx matching for hedge mode
    - Exponential backoff retry logic
    - Rate limiting compliance
    - Status update delays

    Sources:
    - Freqtrade production bot implementation
    - CCXT official Bybit fixes
    - Bybit API v5 official documentation
    """

    def __init__(self, exchange: ccxt.bybit):
        """
        Initialize with CCXT exchange instance

        Args:
            exchange: Pre-configured ccxt.bybit exchange instance
        """
        self.exchange = exchange
        self.stats = {
            'total_scanned': 0,
            'zombies_found': 0,
            'zombies_cancelled': 0,
            'tpsl_cleared': 0,
            'errors': []
        }

        logger.info("BybitZombieOrderCleaner initialized")

    async def get_active_positions_map(self, category: str = "linear") -> Dict[Tuple[str, int], dict]:
        """
        Get map of active positions
        Key: (symbol, positionIdx) for proper hedge mode support

        Source: Bybit API v5 - https://bybit-exchange.github.io/docs/v5/position/list
        """
        try:
            # Fetch positions using CCXT
            positions = await self.exchange.fetch_positions()
            active_positions = {}

            for pos in positions:
                # Check for active position (size > 0)
                position_size = float(pos.get('contracts', 0) or pos.get('size', 0))
                if position_size > 0:
                    symbol = pos['symbol']
                    # Extract positionIdx from info (Bybit-specific)
                    position_idx = int(pos.get('info', {}).get('positionIdx', 0))
                    key = (symbol, position_idx)
                    active_positions[key] = pos

            logger.info(f"Active positions map: {len(active_positions)} positions")
            for (symbol, idx), pos in active_positions.items():
                size = pos.get('contracts', pos.get('size', 0))
                side = pos.get('side', 'unknown')
                logger.debug(f"  {symbol} idx={idx}: {side} {size}")

            return active_positions

        except Exception as e:
            logger.error(f"Failed to get active positions: {e}")
            raise

    def analyze_order_for_zombie(self, order: dict, active_positions: Dict[Tuple[str, int], dict]) -> ZombieOrderAnalysis:
        """
        Analyze order using official Bybit API v5 zombie criteria

        Sources:
        - Freqtrade Issue #7694: https://github.com/freqtrade/freqtrade/issues/7694
        - Bybit API v5 Enums: https://bybit-exchange.github.io/docs/v5/enum
        """
        symbol = order.get('symbol', '')
        order_id = order.get('id', '')
        order_info = order.get('info', {})

        # Extract positionIdx (critical for hedge mode!)
        position_idx = int(order_info.get('positionIdx', 0))
        order_key = (symbol, position_idx)

        order_type = order.get('type', '').lower()
        order_status = order.get('status', '')

        # Skip completed orders
        if order_status in ['closed', 'canceled', 'filled', 'rejected']:
            return ZombieOrderAnalysis(
                order_id=order_id,
                symbol=symbol,
                position_idx=position_idx,
                order_type=order_type,
                is_zombie=False,
                reason="Order already completed"
            )

        # CRITICAL ZOMBIE CRITERIA based on Bybit API v5 docs:

        # CRITERION 1: No matching active position
        if order_key not in active_positions:
            # Check for special order types that require different handling

            # Reduce-only orders MUST have a position (Freqtrade Issue #7694)
            if order_info.get('reduceOnly'):
                return ZombieOrderAnalysis(
                    order_id=order_id,
                    symbol=symbol,
                    position_idx=position_idx,
                    order_type=order_type,
                    is_zombie=True,
                    reason="Reduce-only order without position",
                    needs_special_handling=True,
                    special_method="cancel_with_retry"
                )

            # TP/SL orders for closed positions (Stack Overflow source)
            stop_order_type = order_info.get('stopOrderType', '')
            if stop_order_type in ['TakeProfit', 'StopLoss', 'PartialTakeProfit', 'PartialStopLoss']:
                return ZombieOrderAnalysis(
                    order_id=order_id,
                    symbol=symbol,
                    position_idx=position_idx,
                    order_type=order_type,
                    is_zombie=True,
                    reason=f"TP/SL ({stop_order_type}) for closed position",
                    needs_special_handling=True,
                    special_method="clear_via_trading_stop"
                )

            # closeOnTrigger without position (Bybit API v5 Enums)
            if order_info.get('closeOnTrigger'):
                return ZombieOrderAnalysis(
                    order_id=order_id,
                    symbol=symbol,
                    position_idx=position_idx,
                    order_type=order_type,
                    is_zombie=True,
                    reason="closeOnTrigger order without position",
                    needs_special_handling=True,
                    special_method="cancel_conditional"
                )

            # Conditional orders (CCXT PR #13116)
            if order_status == 'untriggered' or 'conditional' in order_type:
                return ZombieOrderAnalysis(
                    order_id=order_id,
                    symbol=symbol,
                    position_idx=position_idx,
                    order_type=order_type,
                    is_zombie=True,
                    reason="Conditional order without position",
                    needs_special_handling=True,
                    special_method="cancel_conditional"
                )

            # Regular limit order without position
            return ZombieOrderAnalysis(
                order_id=order_id,
                symbol=symbol,
                position_idx=position_idx,
                order_type=order_type,
                is_zombie=True,
                reason="Regular order without position"
            )

        # Order has matching position - not a zombie
        return ZombieOrderAnalysis(
            order_id=order_id,
            symbol=symbol,
            position_idx=position_idx,
            order_type=order_type,
            is_zombie=False,
            reason="Has matching position"
        )

    async def cancel_order_with_retry(self, symbol: str, order_id: str, is_conditional: bool = False) -> bool:
        """
        Cancel order with exponential backoff retry logic

        Source: Freqtrade exchange.py retry decorator
        """
        for attempt in range(3):
            try:
                if is_conditional:
                    # For conditional orders use special parameter (CCXT PR #13116)
                    await self.exchange.cancel_order(order_id, symbol, {'stop': True})
                else:
                    await self.exchange.cancel_order(order_id, symbol)

                logger.info(f"✅ Cancelled order {order_id}")

                # Bybit status update delay (Freqtrade Issue #9273)
                await asyncio.sleep(2.0)
                return True

            except Exception as e:
                error_msg = str(e).lower()

                # Expected errors to ignore (from production experience)
                if any(phrase in error_msg for phrase in [
                    'does not exist', 'order not found', 'nothing to change',
                    'reduceonly', 'already cancelled', 'invalid order status'
                ]):
                    logger.info(f"Order {order_id} already handled: {error_msg}")
                    return True

                if attempt < 2:
                    wait_time = 1 * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Retry {attempt + 1}/3 for {order_id} after {wait_time}s: {error_msg}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed to cancel {order_id} after 3 attempts: {e}")
                    self.stats['errors'].append(f"Cancel failed {order_id}: {e}")
                    return False

        return False

    async def clear_tpsl_via_trading_stop(self, symbol: str, category: str = "linear") -> bool:
        """
        Clear TP/SL via trading-stop endpoint

        Source: Stack Overflow - https://stackoverflow.com/questions/77339832/
        Important: TP/SL created via set_trading_stop don't have orderId!

        CRITICAL FIX: Added symbol validation to prevent retCode:181001 errors
        """
        # CRITICAL FIX: Check if symbol supports trading-stop endpoint
        # Some symbols cause retCode:181001 "category only support linear or option"
        try:
            # Verify symbol exists and supports perpetual trading
            markets = await self.exchange.load_markets()
            if symbol not in markets:
                logger.warning(f"Symbol {symbol} not found in markets - skipping trading-stop")
                return False

            market = markets[symbol]

            # Only perpetual swap contracts support trading-stop endpoint
            # This prevents retCode:181001 errors for unsupported symbols
            if not market.get('swap', False) or market.get('type') != 'swap':
                logger.debug(f"Symbol {symbol} is not a perpetual swap - skipping trading-stop endpoint")
                return False

            logger.debug(f"Symbol {symbol} validated for trading-stop endpoint")

        except Exception as e:
            logger.warning(f"Failed to validate symbol {symbol} for trading-stop: {e}")
            return False

        success_count = 0

        # Check all positionIdx values (critical for hedge mode!)
        for position_idx in [0, 1, 2]:
            try:
                # Use CCXT's set_leverage method with special params for trading-stop
                # This is a workaround since CCXT doesn't have direct trading-stop method
                params = {
                    'category': category,
                    'symbol': symbol,
                    'positionIdx': position_idx,
                    'takeProfit': '0',  # '0' means cancel TP
                    'stopLoss': '0'     # '0' means cancel SL
                }

                # Make direct API call since CCXT doesn't support this endpoint
                response = await self.exchange.private_post_v5_position_trading_stop(params)

                # CRITICAL FIX: Convert retCode to int (Bybit API returns string "0")
                if int(response.get('retCode', 1)) == 0:
                    logger.info(f"✅ Cleared TP/SL for {symbol} positionIdx={position_idx}")
                    success_count += 1

            except Exception as e:
                error_msg = str(e).lower()
                # CRITICAL FIX: Handle retCode:181001 specifically
                if 'retcode":181001' in error_msg or 'category only support' in error_msg:
                    logger.error(f"❌ retCode:181001 for {symbol} idx={position_idx} - symbol not supported by trading-stop endpoint")
                    logger.error(f"   This should have been caught by symbol validation - please check market data")
                    break  # Stop trying other position indices for this symbol
                # Ignore expected errors
                elif 'nothing to change' in error_msg or 'position not exists' in error_msg:
                    logger.debug(f"No TP/SL to clear for {symbol} idx={position_idx}")
                else:
                    logger.warning(f"Failed to clear TP/SL for {symbol} idx={position_idx}: {e}")

            # Rate limiting
            await asyncio.sleep(0.1)

        return success_count > 0

    async def identify_zombie_orders(self, symbols: Optional[List[str]] = None, category: str = "linear") -> List[ZombieOrderAnalysis]:
        """
        Identify all zombie orders using comprehensive criteria

        Args:
            symbols: Optional list of symbols to check (None = all symbols)
            category: Bybit category (linear, spot, inverse)
        """
        try:
            logger.info(f"🔍 Scanning for zombie orders (category: {category})")

            # Get active positions
            active_positions = await self.get_active_positions_map(category)

            # Get all open orders
            if symbols:
                all_orders = []
                for symbol in symbols:
                    orders = await self.exchange.fetch_open_orders(symbol)
                    all_orders.extend(orders)
            else:
                all_orders = await self.exchange.fetch_open_orders()

            logger.info(f"📋 Total open orders: {len(all_orders)}")
            self.stats['total_scanned'] = len(all_orders)

            # Analyze each order
            zombie_analyses = []
            for order in all_orders:
                analysis = self.analyze_order_for_zombie(order, active_positions)

                if analysis.is_zombie:
                    zombie_analyses.append(analysis)
                    logger.warning(f"🧟 ZOMBIE: {analysis.symbol} {analysis.order_type} - {analysis.reason}")
                else:
                    logger.debug(f"✅ OK: {analysis.symbol} {analysis.order_type} - {analysis.reason}")

            self.stats['zombies_found'] = len(zombie_analyses)
            logger.info(f"Found {len(zombie_analyses)} zombie orders")

            return zombie_analyses

        except Exception as e:
            logger.error(f"Failed to identify zombie orders: {e}")
            self.stats['errors'].append(f"Identification failed: {e}")
            raise

    async def cleanup_zombie_orders(self, symbols: Optional[List[str]] = None, category: str = "linear",
                                  dry_run: bool = False) -> Dict:
        """
        Complete zombie order cleanup with all production fixes

        Args:
            symbols: Optional list of symbols to clean (None = all)
            category: Bybit category
            dry_run: If True, only identify but don't cancel

        Returns:
            Dictionary with cleanup results
        """
        try:
            logger.info(f"🧹 Starting zombie order cleanup (dry_run={dry_run})")

            # Reset stats
            self.stats = {
                'total_scanned': 0,
                'zombies_found': 0,
                'zombies_cancelled': 0,
                'tpsl_cleared': 0,
                'errors': []
            }

            # Identify zombies
            zombie_analyses = await self.identify_zombie_orders(symbols, category)

            if not zombie_analyses:
                logger.info("✅ No zombie orders found")
                return self.stats

            if dry_run:
                logger.info(f"📊 DRY RUN: Would cancel {len(zombie_analyses)} zombie orders")
                return self.stats

            # Group by special handling method
            regular_cancels = []
            conditional_cancels = []
            tpsl_symbols = set()

            for analysis in zombie_analyses:
                if analysis.special_method == "cancel_conditional":
                    conditional_cancels.append(analysis)
                elif analysis.special_method == "clear_via_trading_stop":
                    tpsl_symbols.add(analysis.symbol)
                else:
                    regular_cancels.append(analysis)

            # Cancel regular orders
            logger.info(f"Cancelling {len(regular_cancels)} regular zombie orders...")
            for analysis in regular_cancels:
                success = await self.cancel_order_with_retry(
                    analysis.symbol,
                    analysis.order_id,
                    is_conditional=False
                )
                if success:
                    self.stats['zombies_cancelled'] += 1

                # Rate limiting (critical for Bybit!)
                await asyncio.sleep(0.2)

            # Cancel conditional orders (CCXT PR #13116)
            logger.info(f"Cancelling {len(conditional_cancels)} conditional zombie orders...")
            for analysis in conditional_cancels:
                success = await self.cancel_order_with_retry(
                    analysis.symbol,
                    analysis.order_id,
                    is_conditional=True
                )
                if success:
                    self.stats['zombies_cancelled'] += 1

                await asyncio.sleep(0.2)

            # Clear TP/SL via trading-stop
            logger.info(f"Clearing TP/SL for {len(tpsl_symbols)} symbols...")
            for symbol in tpsl_symbols:
                success = await self.clear_tpsl_via_trading_stop(symbol, category)
                if success:
                    self.stats['tpsl_cleared'] += 1

                await asyncio.sleep(0.2)

            # Final verification
            await asyncio.sleep(3.0)  # Wait for Bybit status updates
            final_zombies = await self.identify_zombie_orders(symbols, category)

            if final_zombies:
                logger.warning(f"⚠️ {len(final_zombies)} zombie orders still remain!")
                for analysis in final_zombies:
                    logger.warning(f"  Remaining: {analysis.symbol} {analysis.order_id} - {analysis.reason}")
            else:
                logger.info("🎉 All zombie orders successfully cleaned!")

            return self.stats

        except Exception as e:
            logger.error(f"❌ Zombie cleanup failed: {e}", exc_info=True)
            self.stats['errors'].append(f"Cleanup failed: {e}")
            return self.stats

    def print_stats(self):
        """Print cleanup statistics"""
        print("\n" + "="*60)
        print("BYBIT ZOMBIE ORDER CLEANUP RESULTS")
        print("="*60)
        print(f"📊 Orders scanned: {self.stats['total_scanned']}")
        print(f"🧟 Zombies found: {self.stats['zombies_found']}")
        print(f"✅ Zombies cancelled: {self.stats['zombies_cancelled']}")
        print(f"🎯 TP/SL cleared: {self.stats['tpsl_cleared']}")

        if self.stats['errors']:
            print(f"❌ Errors: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:3]:  # Show first 3 errors
                print(f"   • {error}")

        print("="*60)


# Integration wrapper for existing codebase
class BybitZombieIntegration:
    """
    Integration wrapper for existing position_manager.py
    Provides drop-in replacement for current cleanup_zombie_orders method
    """

    def __init__(self, exchange_manager):
        """Initialize with existing exchange manager"""
        self.exchange_manager = exchange_manager
        self.bybit_cleaners = {}

        # Create cleaners for each Bybit exchange
        for name, exchange in exchange_manager.exchanges.items():
            if 'bybit' in name.lower() and hasattr(exchange, 'exchange'):
                self.bybit_cleaners[name] = BybitZombieOrderCleaner(exchange.exchange)

    async def cleanup_zombie_orders_improved(self, symbols: Optional[List[str]] = None, dry_run: bool = False) -> Dict:
        """
        Improved zombie cleanup that can replace the current method
        """
        if not self.bybit_cleaners:
            logger.warning("No Bybit exchanges found for zombie cleanup")
            return {'message': 'No Bybit exchanges configured'}

        all_results = {}

        for exchange_name, cleaner in self.bybit_cleaners.items():
            logger.info(f"🔧 Running improved zombie cleanup for {exchange_name}")

            try:
                results = await cleaner.cleanup_zombie_orders(symbols, dry_run=dry_run)
                all_results[exchange_name] = results

                logger.info(f"✅ {exchange_name}: {results['zombies_cancelled']}/{results['zombies_found']} zombies cleaned")

            except Exception as e:
                logger.error(f"❌ {exchange_name} cleanup failed: {e}")
                all_results[exchange_name] = {'error': str(e)}

        return all_results


# Example usage for testing
async def test_bybit_zombie_cleanup():
    """Test function - DO NOT use in production without proper API keys"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Configure exchange
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'sandbox': True,  # Use testnet
        'options': {
            'defaultType': 'swap',  # For linear perpetuals
        }
    })

    try:
        # Create cleaner
        cleaner = BybitZombieOrderCleaner(exchange)

        # Run cleanup (dry run first!)
        logger.info("Running DRY RUN...")
        dry_results = await cleaner.cleanup_zombie_orders(dry_run=True)
        cleaner.print_stats()

        if dry_results['zombies_found'] > 0:
            confirm = input(f"\nFound {dry_results['zombies_found']} zombies. Run actual cleanup? (y/N): ")
            if confirm.lower() == 'y':
                logger.info("Running ACTUAL cleanup...")
                results = await cleaner.cleanup_zombie_orders(dry_run=False)
                cleaner.print_stats()

    finally:
        await exchange.close()


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(test_bybit_zombie_cleanup())