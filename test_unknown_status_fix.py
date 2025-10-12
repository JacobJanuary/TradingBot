#!/usr/bin/env python3
"""
Unit Test: Fix for Bybit "unknown" status issue

Verifies that status_map now handles both:
- Bybit API format (uppercase): 'Filled', 'New', 'PartiallyFilled'
- CCXT normalized format (lowercase): 'closed', 'open', 'canceled'
"""
import sys
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.exchange_response_adapter import ExchangeResponseAdapter, NormalizedOrder


def test_ccxt_lowercase_status():
    """
    Test: CCXT lowercase 'open' status is mapped correctly

    BEFORE FIX: 'open' → 'unknown' → order rejection
    AFTER FIX: 'open' → 'open' → order accepted
    """
    print("=" * 80)
    print("🧪 TEST 1: CCXT lowercase 'open' status")
    print("=" * 80)
    print()

    # Simulate OrderResult.__dict__ with CCXT lowercase status
    order_data = {
        'id': 'test-order-123',
        'status': 'open',  # CCXT normalized (lowercase)
        'type': 'market',
        'side': 'sell',
        'amount': 100,
        'filled': 100,
        'price': 0.05,
        'average': 0.05,
        'symbol': 'AGIUSDT',
        'info': {
            'orderStatus': None,  # Bybit returns None for instant orders
            'orderId': 'test-order-123'
        }
    }

    print("Input data:")
    print(f"  data['status']: '{order_data['status']}'")
    print(f"  data['info']['orderStatus']: {order_data['info']['orderStatus']}")
    print(f"  data['type']: '{order_data['type']}'")
    print()

    # Normalize
    normalized = ExchangeResponseAdapter.normalize_order(order_data, 'bybit')

    print("Normalized order:")
    print(f"  status: '{normalized.status}'")
    print()

    # Check
    if normalized.status == 'open':
        print("✅ PASS: Status correctly mapped to 'open'")

        # Check if order is considered filled for market orders
        is_filled = ExchangeResponseAdapter.is_order_filled(normalized)
        print(f"  is_order_filled: {is_filled}")

        if is_filled:
            print("✅ PASS: Market order with 'open' status is considered filled")
            return True
        else:
            print("❌ FAIL: Market order should be considered filled")
            return False
    else:
        print(f"❌ FAIL: Expected 'open', got '{normalized.status}'")
        return False


def test_ccxt_closed_status():
    """
    Test: CCXT lowercase 'closed' status is mapped correctly
    """
    print()
    print("=" * 80)
    print("🧪 TEST 2: CCXT lowercase 'closed' status")
    print("=" * 80)
    print()

    order_data = {
        'id': 'test-order-456',
        'status': 'closed',  # CCXT normalized (lowercase)
        'type': 'market',
        'side': 'buy',
        'amount': 50,
        'filled': 50,
        'price': 0.10,
        'average': 0.10,
        'symbol': 'COOKUSDT',
        'info': {
            'orderStatus': None,
            'orderId': 'test-order-456'
        }
    }

    print("Input data:")
    print(f"  data['status']: '{order_data['status']}'")
    print()

    normalized = ExchangeResponseAdapter.normalize_order(order_data, 'bybit')

    print("Normalized order:")
    print(f"  status: '{normalized.status}'")
    print()

    if normalized.status == 'closed':
        print("✅ PASS: Status correctly mapped to 'closed'")

        is_filled = ExchangeResponseAdapter.is_order_filled(normalized)
        print(f"  is_order_filled: {is_filled}")

        if is_filled:
            print("✅ PASS: Order with 'closed' status is considered filled")
            return True
        else:
            print("❌ FAIL: Closed order should be considered filled")
            return False
    else:
        print(f"❌ FAIL: Expected 'closed', got '{normalized.status}'")
        return False


def test_bybit_uppercase_still_works():
    """
    Test: Bybit uppercase statuses still work (backward compatibility)
    """
    print()
    print("=" * 80)
    print("🧪 TEST 3: Backward compatibility - Bybit uppercase 'Filled'")
    print("=" * 80)
    print()

    order_data = {
        'id': 'test-order-789',
        'status': None,  # Will be determined from info.orderStatus
        'type': 'market',
        'side': 'sell',
        'amount': 200,
        'filled': 200,
        'price': 0.15,
        'average': 0.15,
        'symbol': 'DBRUSDT',
        'info': {
            'orderStatus': 'Filled',  # Bybit API format (uppercase)
            'orderId': 'test-order-789'
        }
    }

    print("Input data:")
    print(f"  data['status']: {order_data['status']}")
    print(f"  data['info']['orderStatus']: '{order_data['info']['orderStatus']}'")
    print()

    normalized = ExchangeResponseAdapter.normalize_order(order_data, 'bybit')

    print("Normalized order:")
    print(f"  status: '{normalized.status}'")
    print()

    if normalized.status == 'closed':
        print("✅ PASS: 'Filled' correctly mapped to 'closed'")

        is_filled = ExchangeResponseAdapter.is_order_filled(normalized)
        if is_filled:
            print("✅ PASS: Filled order is considered filled")
            return True
        else:
            print("❌ FAIL: Filled order should be considered filled")
            return False
    else:
        print(f"❌ FAIL: Expected 'closed', got '{normalized.status}'")
        return False


def test_empty_status_fix_still_works():
    """
    Test: Previous fix for empty status still works
    """
    print()
    print("=" * 80)
    print("🧪 TEST 4: Previous fix - empty status for market orders")
    print("=" * 80)
    print()

    order_data = {
        'id': 'test-order-999',
        'status': None,
        'type': 'market',
        'side': 'buy',
        'amount': 150,
        'filled': 150,
        'price': 0.08,
        'average': 0.08,
        'symbol': 'L3USDT',
        'info': {
            'orderStatus': None,  # Empty status
            'orderId': 'test-order-999'
        }
    }

    print("Input data:")
    print(f"  data['status']: {order_data['status']}")
    print(f"  data['info']['orderStatus']: {order_data['info']['orderStatus']}")
    print(f"  data['type']: '{order_data['type']}'")
    print()

    normalized = ExchangeResponseAdapter.normalize_order(order_data, 'bybit')

    print("Normalized order:")
    print(f"  status: '{normalized.status}'")
    print()

    if normalized.status == 'closed':
        print("✅ PASS: Empty status + market order → 'closed' (previous fix works)")

        is_filled = ExchangeResponseAdapter.is_order_filled(normalized)
        if is_filled:
            print("✅ PASS: Order is considered filled")
            return True
        else:
            print("❌ FAIL: Order should be considered filled")
            return False
    else:
        print(f"❌ FAIL: Expected 'closed', got '{normalized.status}'")
        return False


def main():
    print()
    print("🔬 UNIT TESTS: Bybit 'unknown' Status Fix")
    print("=" * 80)
    print()
    print("Testing fix for: CCXT lowercase status → 'unknown' → order rejection")
    print("Solution: Add lowercase mappings to status_map")
    print()

    # Run tests
    test1 = test_ccxt_lowercase_status()
    test2 = test_ccxt_closed_status()
    test3 = test_bybit_uppercase_still_works()
    test4 = test_empty_status_fix_still_works()

    # Summary
    print()
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print()

    tests = {
        "CCXT 'open' status mapping": test1,
        "CCXT 'closed' status mapping": test2,
        "Bybit uppercase backward compatibility": test3,
        "Empty status fix (previous fix)": test4
    }

    for name, passed in tests.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    print()

    if all(tests.values()):
        print("🎉 ALL TESTS PASSED")
        print()
        print("🎯 VERIFICATION:")
        print("  - CCXT lowercase statuses mapped correctly ✅")
        print("  - Bybit uppercase statuses still work ✅")
        print("  - Previous empty status fix preserved ✅")
        print("  - Orders will no longer be rejected as 'unknown' ✅")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        failed = sum(1 for p in tests.values() if not p)
        print(f"  {failed}/{len(tests)} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
