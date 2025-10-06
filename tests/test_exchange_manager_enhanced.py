"""
Unit tests for Enhanced Exchange Manager

Tests:
1. Duplicate order prevention
2. Safe cancel with race condition handling
3. Stop Loss vs Limit Exit differentiation
4. Progressive price calculation
5. CCXT parameter handling
"""

import unittest
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt
from core.exchange_manager_enhanced import EnhancedExchangeManager
from core.order_utils import is_stop_loss_order, is_limit_exit_order


class TestEnhancedExchangeManager(unittest.TestCase):
    """Test suite for Enhanced Exchange Manager"""

    def setUp(self):
        """Setup for each test"""
        # Create mock CCXT exchange
        self.mock_exchange = Mock(spec=ccxt.Exchange)
        self.mock_exchange.id = 'binanceusdm'

        # Mock precision methods
        self.mock_exchange.price_to_precision = lambda s, p: round(p, 2)
        self.mock_exchange.amount_to_precision = lambda s, a: round(a, 3)

        # Create manager instance
        self.manager = EnhancedExchangeManager(self.mock_exchange)

    def test_1_no_duplicate_order_created(self):
        """TEST 1: Should not create duplicate if order exists"""
        print("\n" + "="*60)
        print("TEST 1: Duplicate Prevention")
        print("="*60)

        # Setup: Existing order
        existing_order = {
            'id': 'existing123',
            'symbol': 'BTC/USDT:USDT',
            'type': 'limit',
            'side': 'sell',
            'price': 50000,
            'amount': 0.1,
            'reduceOnly': True,
            'info': {'stopOrderType': ''}  # Not a stop loss
        }

        # Mock fetch_open_orders to return existing order
        async def mock_fetch(symbol):  # Added symbol parameter
            return [existing_order]

        self.mock_exchange.fetch_open_orders = Mock(side_effect=mock_fetch)

        # Mock create_order as async
        async def mock_create(*args, **kwargs):
            return {'id': 'should_not_be_called'}

        self.mock_exchange.create_order = Mock(side_effect=mock_create)

        # Test: Try to create duplicate
        async def test_create():
            result = await self.manager.create_limit_exit_order(
                'BTC/USDT:USDT', 'sell', 0.1, 50000
            )
            return result

        result = asyncio.run(test_create())

        # Verify: Should return existing, not create new
        self.assertEqual(result['id'], 'existing123')
        self.mock_exchange.create_order.assert_not_called()
        self.assertEqual(self.manager.stats['duplicates_prevented'], 1)

        print("✅ TEST 1 PASSED: No duplicate created")

    def test_2_handles_filled_during_cancel(self):
        """TEST 2: Detects when order fills during cancellation"""
        print("\n" + "="*60)
        print("TEST 2: Race Condition Handling")
        print("="*60)

        # Mock cancel_order (doesn't matter what it returns)
        async def mock_cancel(order_id, symbol):
            return None

        self.mock_exchange.cancel_order = Mock(side_effect=mock_cancel)

        # Mock fetch_order to return filled status
        async def mock_fetch(order_id, symbol):
            return {
                'id': 'test123',
                'status': 'closed',  # Filled!
                'filled': 0.1,
                'remaining': 0
            }

        self.mock_exchange.fetch_order = Mock(side_effect=mock_fetch)

        # Test cancellation
        async def test_cancel():
            result = await self.manager.safe_cancel_with_verification(
                'test123', 'BTC/USDT:USDT'
            )
            return result

        result = asyncio.run(test_cancel())

        # Verify: Should detect filled during cancel
        self.assertEqual(result['status'], 'filled_during_cancel')
        self.assertEqual(self.manager.stats['race_conditions_detected'], 1)

        print("✅ TEST 2 PASSED: Filled-during-cancel detected")

    def test_3_stop_loss_vs_limit_exit(self):
        """TEST 3: Correctly distinguishes Stop Loss from Limit Exit"""
        print("\n" + "="*60)
        print("TEST 3: Stop Loss vs Limit Exit")
        print("="*60)

        # Test case 1: Limit Exit (NOT stop loss)
        limit_exit_order = {
            'id': 'limit123',
            'type': 'limit',
            'side': 'sell',
            'reduceOnly': True,
            'triggerPrice': 0,
            'info': {
                'stopOrderType': '',  # Empty = not stop
                'triggerPrice': '0'
            }
        }

        # Test case 2: Stop Loss order
        stop_loss_order = {
            'id': 'stop123',
            'type': 'limit',
            'side': 'sell',
            'reduceOnly': True,
            'triggerPrice': 48000,
            'info': {
                'stopOrderType': 'StopLoss',  # Explicit stop loss
                'triggerPrice': '48000'
            }
        }

        # Test case 3: Another Stop Loss variant
        stop_market_order = {
            'id': 'stop456',
            'type': 'stop_market',
            'side': 'sell',
            'reduceOnly': True,
            'info': {}
        }

        # Verify classifications
        self.assertFalse(is_stop_loss_order(limit_exit_order))
        self.assertTrue(is_limit_exit_order(limit_exit_order))

        self.assertTrue(is_stop_loss_order(stop_loss_order))
        self.assertFalse(is_limit_exit_order(stop_loss_order))

        self.assertTrue(is_stop_loss_order(stop_market_order))
        self.assertFalse(is_limit_exit_order(stop_market_order))

        print("✅ TEST 3 PASSED: SL vs Limit correctly distinguished")

    def test_4_progressive_price_calculation(self):
        """TEST 4: Progressive price calculation for aged positions"""
        print("\n" + "="*60)
        print("TEST 4: Progressive Price Calculation")
        print("="*60)

        entry_price = 50000
        test_cases = [
            # (hours_open, side, expected_adjustment)
            (3, 'long', 1.0008),     # <6h: breakeven + commission
            (3, 'short', 0.9992),    # <6h: breakeven + commission
            (12, 'long', 0.9977),    # 6-24h: gradual tolerance
            (12, 'short', 1.0023),   # 6-24h: gradual tolerance
            (25, 'long', 0.9925),    # >24h: progressive liquidation
            (25, 'short', 1.0075),   # >24h: progressive liquidation
        ]

        for hours, side, expected_multiplier in test_cases:
            exit_price = self.manager.calculate_progressive_exit_price(
                entry_price, side, hours
            )
            expected = entry_price * expected_multiplier

            # Allow small tolerance for float precision
            self.assertAlmostEqual(exit_price, expected, places=0)

            print(f"  {side.upper()} @ {hours}h: "
                  f"entry={entry_price} → exit={exit_price:.0f} "
                  f"({'✅' if abs(exit_price - expected) < 10 else '❌'})")

        print("✅ TEST 4 PASSED: Progressive price correct")

    def test_5_ccxt_parameter_handling(self):
        """TEST 5: CCXT correctly handles exchange-specific parameters"""
        print("\n" + "="*60)
        print("TEST 5: CCXT Parameter Handling")
        print("="*60)

        # Mock empty order list (no duplicates)
        async def mock_fetch(symbol):  # Added parameter
            return []

        self.mock_exchange.fetch_open_orders = Mock(side_effect=mock_fetch)

        # Mock create_order to capture parameters
        async def mock_create(symbol, type, side, amount, price, params):
            return {
                'id': 'new123',
                'symbol': symbol,
                'type': type,
                'side': side,
                'amount': amount,
                'price': price,
                'params_received': params
            }

        self.mock_exchange.create_order = Mock(side_effect=mock_create)

        # Test Binance parameters
        self.manager.exchange_id = 'binanceusdm'

        async def test_binance():
            result = await self.manager.create_limit_exit_order(
                'BTC/USDT:USDT', 'sell', 0.1, 50000
            )
            return result

        result = asyncio.run(test_binance())

        # Verify Binance-specific params
        call_args = self.mock_exchange.create_order.call_args
        params = call_args[1]['params']

        self.assertEqual(params['reduceOnly'], True)
        self.assertEqual(params['timeInForce'], 'GTC')
        self.assertEqual(params.get('postOnly'), True)

        print(f"  Binance params: {params}")

        # Test Bybit parameters
        self.manager.exchange_id = 'bybit'
        self.mock_exchange.id = 'bybit'
        self.mock_exchange.create_order.reset_mock()

        result = asyncio.run(test_binance())

        call_args = self.mock_exchange.create_order.call_args
        params = call_args[1]['params']

        self.assertEqual(params['reduceOnly'], True)
        self.assertEqual(params['positionIdx'], 0)

        print(f"  Bybit params: {params}")
        print("✅ TEST 5 PASSED: CCXT params correct")

    def test_6_partial_fill_handling(self):
        """TEST 6: Handles partial fills during cancel-and-replace"""
        print("\n" + "="*60)
        print("TEST 6: Partial Fill Handling")
        print("="*60)

        # Mock cancel
        async def mock_cancel(order_id, symbol):
            return None

        self.mock_exchange.cancel_order = Mock(side_effect=mock_cancel)

        # Mock fetch showing partial fill
        async def mock_fetch(order_id, symbol):
            return {
                'id': order_id,
                'status': 'canceled',
                'filled': 0.03,  # Partially filled!
                'amount': 0.1,
                'remaining': 0.07
            }

        self.mock_exchange.fetch_order = Mock(side_effect=mock_fetch)

        # Mock create for new order
        async def mock_create(symbol, type, side, amount, price, params):
            return {
                'id': 'new456',
                'amount': amount  # Should be reduced!
            }

        self.mock_exchange.create_order = Mock(side_effect=mock_create)

        # Test update with partial fill
        existing_order = {
            'id': 'old123',
            'symbol': 'BTC/USDT:USDT',
            'side': 'sell',
            'amount': 0.1,
            'price': 50000
        }

        async def test_update():
            result = await self.manager.update_exit_order_price(
                existing_order, 49500, 0.1  # Original amount
            )
            return result

        result = asyncio.run(test_update())

        # Verify new order has reduced amount
        call_args = self.mock_exchange.create_order.call_args
        new_amount = call_args[1]['amount']

        self.assertAlmostEqual(new_amount, 0.07, places=3)  # 0.1 - 0.03

        print(f"  Original: 0.1, Filled: 0.03, New order: {new_amount}")
        print("✅ TEST 6 PASSED: Partial fill handled correctly")


def run_all_tests():
    """Run all unit tests"""
    print("\n" + "="*80)
    print("RUNNING ENHANCED EXCHANGE MANAGER UNIT TESTS")
    print("="*80)

    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestEnhancedExchangeManager)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "="*80)
    if result.wasSuccessful():
        print("✅ ALL UNIT TESTS PASSED")
    else:
        print(f"❌ TESTS FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
    print("="*80)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)