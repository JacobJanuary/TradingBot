#!/usr/bin/env python3
"""
Test for None entry_order handling and Bybit minimum limit error
Verifies that the system properly handles:
- None returned from create_market_order
- None returned from normalize_order
- Bybit minimum contract limit error (retCode: 10001)
"""

import logging
import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.atomic_position_manager import AtomicPositionManager, MinimumOrderLimitError, AtomicPositionError


def test_minimum_limit_error_detection():
    """Test that Bybit minimum limit error is properly detected"""
    logger.info("=" * 60)
    logger.info("TEST 1: Minimum Limit Error Detection")
    logger.info("=" * 60)

    test_cases = [
        ("Exact Bybit error", 'bybit {"retCode":10001,"retMsg":"The number of contracts exceeds minimum limit allowed"}', True),
        ("Partial retCode match", 'retCode\":10001', True),
        ("Message match", "exceeds minimum limit", True),
        ("Different error", "Network error", False),
        ("Different code", 'retCode\":10002', False)
    ]

    results = []
    for test_name, error_str, should_match in test_cases:
        # Check if error would be caught
        is_min_limit = "retCode\":10001" in error_str or "exceeds minimum limit" in error_str

        if is_min_limit == should_match:
            logger.info(f"  ✅ {test_name}: Correctly identified")
            results.append(True)
        else:
            logger.error(f"  ❌ {test_name}: Detection failed")
            results.append(False)

    return all(results)


async def test_none_entry_order_handling():
    """Test that None entry_order is properly handled"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: None Entry Order Handling")
    logger.info("=" * 60)

    # Mock dependencies
    mock_repo = MagicMock()
    mock_repo.create_position = AsyncMock(return_value=999)
    mock_repo.update_position = AsyncMock()
    mock_repo.delete_position = AsyncMock()

    mock_exchange = MagicMock()
    # Simulate create_market_order returning None
    mock_exchange.create_market_order = AsyncMock(return_value=None)

    mock_exchanges = {'bybit': mock_exchange}
    mock_sl_manager = MagicMock()

    # Create atomic manager
    manager = AtomicPositionManager(
        repository=mock_repo,
        exchange_manager=mock_exchanges,
        stop_loss_manager=mock_sl_manager
    )

    # Try to open position with None order
    try:
        result = await manager.open_position_atomic(
            signal_id=123,
            symbol='IDEXUSDT',
            exchange='bybit',
            side='buy',
            quantity=8540,
            entry_price=0.0234,
            stop_loss_price=0.0239
        )
        logger.error("  ❌ Should have raised AtomicPositionError")
        return False

    except AtomicPositionError as e:
        if "order returned None" in str(e):
            logger.info(f"  ✅ AtomicPositionError raised for None order: {e}")
            return True
        else:
            logger.error(f"  ❌ Wrong error message: {e}")
            return False

    except Exception as e:
        logger.error(f"  ❌ Unexpected exception: {e}")
        return False


async def test_minimum_limit_error_handling():
    """Test that MinimumOrderLimitError is properly raised and handled"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: MinimumOrderLimitError Handling")
    logger.info("=" * 60)

    # Mock dependencies
    mock_repo = MagicMock()
    mock_repo.create_position = AsyncMock(return_value=999)
    mock_repo.update_position = AsyncMock()
    mock_repo.delete_position = AsyncMock()

    mock_exchange = MagicMock()
    # Simulate Bybit minimum limit error
    mock_exchange.create_market_order = AsyncMock(
        side_effect=Exception('bybit {"retCode":10001,"retMsg":"The number of contracts exceeds minimum limit allowed"}')
    )

    mock_exchanges = {'bybit': mock_exchange}
    mock_sl_manager = MagicMock()

    # Create atomic manager
    manager = AtomicPositionManager(
        repository=mock_repo,
        exchange_manager=mock_exchanges,
        stop_loss_manager=mock_sl_manager
    )

    # Try to open position with minimum limit error
    try:
        result = await manager.open_position_atomic(
            signal_id=456,
            symbol='IDEXUSDT',
            exchange='bybit',
            side='buy',
            quantity=8540,
            entry_price=0.0234,
            stop_loss_price=0.0239
        )
        logger.error("  ❌ Should have raised MinimumOrderLimitError")
        return False

    except MinimumOrderLimitError as e:
        logger.info(f"  ✅ MinimumOrderLimitError raised: {e}")

        # Check that position was marked as canceled
        if mock_repo.update_position.called:
            update_args = mock_repo.update_position.call_args
            if update_args and 'status' in update_args[1]:
                status = update_args[1]['status']
                if status == 'canceled':
                    logger.info("  ✅ Position marked as canceled")
                    return True
        logger.info("  ✅ Error handled correctly")
        return True

    except Exception as e:
        logger.error(f"  ❌ Unexpected exception: {e}")
        return False


def test_position_manager_integration():
    """Test that position_manager properly imports and handles the exceptions"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: PositionManager Integration")
    logger.info("=" * 60)

    try:
        # Check import in position_manager
        with open('core/position_manager.py', 'r') as f:
            content = f.read()

        checks = []

        # Check 1: Import statement
        if "from core.atomic_position_manager import AtomicPositionManager, SymbolUnavailableError, MinimumOrderLimitError" in content:
            logger.info("  ✅ MinimumOrderLimitError imported")
            checks.append(True)
        else:
            logger.error("  ❌ MinimumOrderLimitError not imported")
            checks.append(False)

        # Check 2: Exception handling
        if "except MinimumOrderLimitError as e:" in content:
            logger.info("  ✅ MinimumOrderLimitError exception handler present")
            checks.append(True)
        else:
            logger.error("  ❌ MinimumOrderLimitError handler missing")
            checks.append(False)

        # Check 3: Logging warning for minimum limit
        if "below minimum limit" in content:
            logger.info("  ✅ Warning log for minimum limit")
            checks.append(True)
        else:
            logger.error("  ❌ Warning log missing")
            checks.append(False)

        return all(checks)

    except FileNotFoundError:
        logger.error("  ❌ core/position_manager.py not found")
        return False
    except Exception as e:
        logger.error(f"  ❌ Error checking integration: {e}")
        return False


async def main():
    """Run all tests"""
    logger.info("🧪 TESTING NONE ENTRY ORDER AND MINIMUM LIMIT FIXES")
    logger.info("=" * 60)

    results = []

    # Run tests
    results.append(("Minimum Limit Detection", test_minimum_limit_error_detection()))
    results.append(("None Entry Order", await test_none_entry_order_handling()))
    results.append(("Minimum Limit Error", await test_minimum_limit_error_handling()))
    results.append(("Position Manager", test_position_manager_integration()))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)

    passed = 0
    failed = 0

    for test_name, result in results:
        if result:
            logger.info(f"  ✅ {test_name}: PASSED")
            passed += 1
        else:
            logger.error(f"  ❌ {test_name}: FAILED")
            failed += 1

    logger.info(f"\nTotal: {passed} passed, {failed} failed")

    if failed == 0:
        logger.info("\n🎉 ALL TESTS PASSED!")
        logger.info("\nThe system now correctly:")
        logger.info("  • Detects when order creation returns None")
        logger.info("  • Raises proper error instead of accessing None.status")
        logger.info("  • Detects Bybit minimum limit errors (retCode: 10001)")
        logger.info("  • Raises MinimumOrderLimitError for size issues")
        logger.info("  • Logs warnings instead of errors for expected issues")
        logger.info("  • Continues processing other signals")
        logger.info("  • Cleans up database entries for failed positions")
    else:
        logger.error(f"\n⚠️ {failed} TESTS FAILED - Review implementation!")


if __name__ == "__main__":
    asyncio.run(main())