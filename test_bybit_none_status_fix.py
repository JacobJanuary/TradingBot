#!/usr/bin/env python3
"""
Unit Test: Bybit None status fix

Проверяет что None status корректно обрабатывается
"""
import sys
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.exchange_response_adapter import ExchangeResponseAdapter


def test_none_status():
    """
    TEST: Bybit create_order returns None status
    """
    print()
    print("="*80)
    print("🧪 TEST: Bybit None status handling")
    print("="*80)
    print()

    # Симулируем реальный ответ Bybit API v5 create_order
    order_data = {
        'info': {
            'orderId': 'test-order-123',
            'orderLinkId': ''
            # orderStatus отсутствует
        },
        'id': 'test-order-123',
        'status': None,    # ← CCXT возвращает None
        'type': None,      # ← Тоже None
        'side': None,
        'price': None,
        'amount': None,
        'filled': None,
        'symbol': 'BTC/USDT:USDT'
    }

    print("Input order_data:")
    print(f"  order['status'] = {order_data['status']!r} (type: {type(order_data['status']).__name__})")
    print(f"  order['info']['orderStatus'] = {order_data['info'].get('orderStatus')!r}")
    print()

    # Нормализуем
    normalized = ExchangeResponseAdapter.normalize_order(order_data, 'bybit')

    print("Normalized result:")
    print(f"  normalized.status = {normalized.status!r}")
    print()

    # Проверяем
    if normalized.status == 'closed':
        print("✅ TEST PASSED: None status → 'closed'")
        print()
        print("Verification:")
        print("  - None status correctly handled")
        print("  - Mapped to 'closed' (instant market execution)")
        print("  - Will NOT trigger 'Entry order failed: unknown'")
        return True
    else:
        print(f"❌ TEST FAILED: Expected 'closed', got '{normalized.status}'")
        return False


def test_created_status():
    """
    TEST: Bybit 'Created' status mapping
    """
    print()
    print("="*80)
    print("🧪 TEST: Bybit 'Created' status mapping")
    print("="*80)
    print()

    order_data = {
        'info': {
            'orderId': 'test-order-456',
            'orderStatus': 'Created'  # ← Bybit native status
        },
        'id': 'test-order-456',
        'status': 'open',
        'symbol': 'ETH/USDT:USDT'
    }

    print("Input order_data:")
    print(f"  order['info']['orderStatus'] = {order_data['info']['orderStatus']!r}")
    print()

    normalized = ExchangeResponseAdapter.normalize_order(order_data, 'bybit')

    print("Normalized result:")
    print(f"  normalized.status = {normalized.status!r}")
    print()

    if normalized.status == 'open':
        print("✅ TEST PASSED: 'Created' → 'open'")
        print()
        print("Verification:")
        print("  - 'Created' status correctly mapped")
        print("  - Added to status_map")
        return True
    else:
        print(f"❌ TEST FAILED: Expected 'open', got '{normalized.status}'")
        return False


def test_empty_string_status():
    """
    TEST: Empty string status
    """
    print()
    print("="*80)
    print("🧪 TEST: Empty string status")
    print("="*80)
    print()

    order_data = {
        'info': {
            'orderId': 'test-order-789',
            'orderStatus': ''  # ← Empty string
        },
        'id': 'test-order-789',
        'status': '',
        'symbol': 'SOL/USDT:USDT'
    }

    print("Input order_data:")
    print(f"  order['info']['orderStatus'] = {order_data['info']['orderStatus']!r}")
    print()

    normalized = ExchangeResponseAdapter.normalize_order(order_data, 'bybit')

    print("Normalized result:")
    print(f"  normalized.status = {normalized.status!r}")
    print()

    if normalized.status == 'closed':
        print("✅ TEST PASSED: Empty string → 'closed'")
        return True
    else:
        print(f"❌ TEST FAILED: Expected 'closed', got '{normalized.status}'")
        return False


def main():
    print()
    print("🔬 UNIT TEST: Bybit None Status Fix")
    print("="*80)
    print()

    tests = {
        "None status handling": test_none_status(),
        "'Created' status mapping": test_created_status(),
        "Empty string status": test_empty_string_status()
    }

    print()
    print("="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print()

    for name, passed in tests.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    print()

    if all(tests.values()):
        print("🎉 ALL TESTS PASSED (3/3)")
        print()
        print("🎯 VERIFICATION:")
        print("  - None status → 'closed' ✅")
        print("  - Empty string → 'closed' ✅")
        print("  - 'Created' status → 'open' ✅")
        print("  - Fix resolves 'Entry order failed: unknown' ✅")
        print()
        print("✅ Ready for git commit")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        failed = sum(1 for p in tests.values() if not p)
        print(f"  {failed}/{len(tests)} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
