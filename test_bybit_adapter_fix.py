#!/usr/bin/env python3
"""
Test the Bybit adapter fix for None type field
Tests that the adapter properly handles None values in the 'type' field
"""

import logging
import sys
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.exchange_response_adapter import ExchangeResponseAdapter


def test_bybit_none_type():
    """Test that Bybit adapter handles None type field correctly"""
    logger.info("=" * 60)
    logger.info("TESTING BYBIT ADAPTER FIX FOR None TYPE")
    logger.info("=" * 60)

    # Test case 1: type field is None
    test_order_1 = {
        'id': '12345',
        'status': 'closed',
        'side': 'buy',
        'amount': 100,
        'filled': 100,
        'price': 50000,
        'type': None,  # This was causing the error!
        'info': {
            'orderId': '12345',
            'orderStatus': 'Filled',
            'side': 'Buy',
            'qty': '100',
            'cumExecQty': '100',
            'price': '50000',
            'avgPrice': '50000'
        }
    }

    # Test case 2: type field is missing
    test_order_2 = {
        'id': '12346',
        'status': 'closed',
        'side': 'sell',
        'amount': 200,
        'filled': 200,
        'price': 51000,
        # 'type' field missing
        'info': {
            'orderId': '12346',
            'orderStatus': 'Filled',
            'side': 'Sell',
            'qty': '200',
            'cumExecQty': '200',
            'price': '51000',
            'avgPrice': '51000'
        }
    }

    # Test case 3: type field is empty string
    test_order_3 = {
        'id': '12347',
        'status': 'open',
        'side': 'buy',
        'amount': 300,
        'filled': 150,
        'price': 52000,
        'type': '',  # Empty string
        'info': {
            'orderId': '12347',
            'orderStatus': 'PartiallyFilled',
            'side': 'Buy',
            'qty': '300',
            'cumExecQty': '150',
            'price': '52000'
        }
    }

    # Test case 4: normal case with type='limit'
    test_order_4 = {
        'id': '12348',
        'status': 'open',
        'side': 'sell',
        'amount': 400,
        'filled': 0,
        'price': 53000,
        'type': 'limit',  # Normal case
        'info': {
            'orderId': '12348',
            'orderStatus': 'New',
            'side': 'Sell',
            'qty': '400',
            'cumExecQty': '0',
            'price': '53000'
        }
    }

    results = []
    test_cases = [
        ("None type", test_order_1),
        ("Missing type", test_order_2),
        ("Empty type", test_order_3),
        ("Normal type", test_order_4)
    ]

    for test_name, test_order in test_cases:
        try:
            normalized = ExchangeResponseAdapter.normalize_order(test_order, 'bybit')

            # Check the result
            if normalized.type in ['market', 'limit']:
                logger.info(f"  ✅ {test_name}: Success - type={normalized.type}")
                results.append(True)
            else:
                logger.error(f"  ❌ {test_name}: Unexpected type={normalized.type}")
                results.append(False)

        except AttributeError as e:
            if "'NoneType' object has no attribute 'lower'" in str(e):
                logger.error(f"  ❌ {test_name}: FAILED - AttributeError not fixed!")
                results.append(False)
            else:
                logger.error(f"  ❌ {test_name}: Different error - {e}")
                results.append(False)
        except Exception as e:
            logger.error(f"  ❌ {test_name}: Unexpected error - {e}")
            results.append(False)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    passed = sum(results)
    total = len(results)

    if passed == total:
        logger.info(f"✅ ALL TESTS PASSED ({passed}/{total})")
        logger.info("\nThe Bybit adapter now correctly handles:")
        logger.info("  • None values in type field")
        logger.info("  • Missing type field")
        logger.info("  • Empty string type field")
        logger.info("  • Normal type values")
        return True
    else:
        logger.error(f"❌ SOME TESTS FAILED ({passed}/{total} passed)")
        return False


def test_binance_none_type():
    """Test that Binance adapter also handles None type field correctly"""
    logger.info("\n" + "=" * 60)
    logger.info("TESTING BINANCE ADAPTER FOR None TYPE")
    logger.info("=" * 60)

    # Test Binance order with None type
    test_order = {
        'id': 'BIN123',
        'status': 'closed',
        'side': 'buy',
        'amount': 500,
        'filled': 500,
        'price': 60000,
        'type': None,  # Test None for Binance too
        'info': {
            'orderId': 'BIN123',
            'status': 'FILLED',
            'side': 'BUY',
            'origQty': '500',
            'executedQty': '500',
            'price': '60000'
        }
    }

    try:
        normalized = ExchangeResponseAdapter.normalize_order(test_order, 'binance')

        if normalized.type in ['market', 'limit']:
            logger.info(f"  ✅ Binance None type: Success - type={normalized.type}")
            return True
        else:
            logger.error(f"  ❌ Binance None type: Unexpected type={normalized.type}")
            return False

    except AttributeError as e:
        if "'NoneType' object has no attribute 'lower'" in str(e):
            logger.error(f"  ❌ Binance None type: FAILED - AttributeError not fixed!")
            return False
        else:
            logger.error(f"  ❌ Binance None type: Different error - {e}")
            return False
    except Exception as e:
        logger.error(f"  ❌ Binance None type: Unexpected error - {e}")
        return False


if __name__ == "__main__":
    bybit_ok = test_bybit_none_type()
    binance_ok = test_binance_none_type()

    logger.info("\n" + "=" * 60)
    logger.info("FINAL RESULTS")
    logger.info("=" * 60)

    if bybit_ok and binance_ok:
        logger.info("🎉 ALL ADAPTERS FIXED AND TESTED!")
        logger.info("\nThe AttributeError is resolved for:")
        logger.info("  • Bybit orders")
        logger.info("  • Binance orders")
        logger.info("\nPositions can now be opened on both exchanges without crashes.")
    else:
        logger.error("⚠️ SOME TESTS FAILED")
        if not bybit_ok:
            logger.error("  • Bybit adapter needs review")
        if not binance_ok:
            logger.error("  • Binance adapter needs review")