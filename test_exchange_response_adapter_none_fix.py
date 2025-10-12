#!/usr/bin/env python3
"""
Тесты для проверки проблемы с None в ExchangeResponseAdapter

Эти тесты проверяют что нормализаторы правильно обрабатывают:
1. dict.get() с None значениями
2. status=None от биржи
3. is_order_filled() с invalid status
"""

import sys
from core.exchange_response_adapter import ExchangeResponseAdapter, NormalizedOrder


def test_python_dict_get_behavior():
    """
    BASELINE TEST: Демонстрирует проблему dict.get() с None
    """
    print("=" * 70)
    print("TEST 1: Python dict.get() behavior with None")
    print("=" * 70)

    # Случай 1: Ключ отсутствует
    data1 = {}
    result1 = data1.get('status', 'unknown')
    print(f"\nCase 1: Key missing")
    print(f"  data = {{}}")
    print(f"  data.get('status', 'unknown') = {repr(result1)}")
    assert result1 == 'unknown', "Should return 'unknown' when key missing"
    print(f"  ✅ PASS: Returns default")

    # Случай 2: Ключ есть но = None (ПРОБЛЕМА!)
    data2 = {'status': None}
    result2 = data2.get('status', 'unknown')
    print(f"\nCase 2: Key exists but value is None")
    print(f"  data = {{'status': None}}")
    print(f"  data.get('status', 'unknown') = {repr(result2)}")

    if result2 is None:
        print(f"  ❌ PROBLEM CONFIRMED: Returns None (not 'unknown')!")
        print(f"     This is the root cause of the bug!")
    else:
        print(f"  ✅ Returns default")

    # Правильный способ
    result3 = data2.get('status') or 'unknown'
    print(f"\nCorrect way:")
    print(f"  data.get('status') or 'unknown' = {repr(result3)}")
    assert result3 == 'unknown', "Should return 'unknown' with or operator"
    print(f"  ✅ PASS: or operator handles None correctly")

    return result2 is None  # True if problem exists


def test_normalize_bybit_order_with_none_status():
    """
    TEST 2: Нормализация Bybit ордера с status=None
    """
    print("\n" + "=" * 70)
    print("TEST 2: Normalize Bybit order with status=None")
    print("=" * 70)

    # Имитируем ответ от Bybit с status=None
    bybit_order = {
        'id': 'test_order_123',
        'symbol': 'MNTUSDT',
        'status': None,  # ← Проблема
        'side': 'sell',
        'amount': 94.7,
        'filled': 0,
        'price': 2.1118,
        'average': None,
        'type': 'market',
        'info': {
            'orderId': 'test_order_123',
            'orderStatus': None,  # ← Тоже None
            'symbol': 'MNTUSDT',
            'side': 'Sell',
            'qty': '94.7',
            'cumExecQty': '0'
        }
    }

    print(f"\nBybit order data:")
    print(f"  status: {repr(bybit_order['status'])}")
    print(f"  info.orderStatus: {repr(bybit_order['info'].get('orderStatus'))}")

    # Нормализуем
    try:
        normalized = ExchangeResponseAdapter.normalize_order(bybit_order, 'bybit')

        print(f"\nNormalized order:")
        print(f"  id: {normalized.id}")
        print(f"  status: {repr(normalized.status)}")
        print(f"  side: {normalized.side}")
        print(f"  amount: {normalized.amount}")

        # Проверка
        if normalized.status is None:
            print(f"\n  ❌ FAIL: status is None (bug exists)")
            print(f"     This will cause 'Entry order failed: None' error!")
            return False
        elif normalized.status == 'unknown':
            print(f"\n  ✅ PASS: status is 'unknown' (bug fixed)")
            return True
        else:
            print(f"\n  ⚠️ UNEXPECTED: status is {repr(normalized.status)}")
            return True

    except Exception as e:
        print(f"\n  ❌ EXCEPTION: {e}")
        return False


def test_normalize_binance_order_with_none_status():
    """
    TEST 3: Нормализация Binance ордера с status=None
    """
    print("\n" + "=" * 70)
    print("TEST 3: Normalize Binance order with status=None")
    print("=" * 70)

    binance_order = {
        'id': 'test_order_456',
        'symbol': 'BTCUSDT',
        'status': None,  # ← Проблема
        'side': 'buy',
        'amount': 0.001,
        'filled': 0,
        'price': 50000,
        'average': None,
        'type': 'market',
        'info': {
            'orderId': 'test_order_456',
            'status': None,
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'origQty': '0.001',
            'executedQty': '0'
        }
    }

    print(f"\nBinance order data:")
    print(f"  status: {repr(binance_order['status'])}")

    try:
        normalized = ExchangeResponseAdapter.normalize_order(binance_order, 'binance')

        print(f"\nNormalized order:")
        print(f"  status: {repr(normalized.status)}")

        if normalized.status is None:
            print(f"\n  ❌ FAIL: status is None (bug exists)")
            return False
        elif normalized.status == 'unknown':
            print(f"\n  ✅ PASS: status is 'unknown' (bug fixed)")
            return True
        else:
            print(f"\n  ⚠️ UNEXPECTED: status is {repr(normalized.status)}")
            return True

    except Exception as e:
        print(f"\n  ❌ EXCEPTION: {e}")
        return False


def test_is_order_filled_with_none():
    """
    TEST 4: is_order_filled() с invalid status
    """
    print("\n" + "=" * 70)
    print("TEST 4: is_order_filled() with None/unknown status")
    print("=" * 70)

    test_cases = [
        (None, 'market', 0, 0, "status=None"),
        ('unknown', 'market', 0, 0, "status='unknown'"),
        ('', 'market', 0, 0, "status=''"),
        (None, 'market', 100, 0, "status=None, filled=0"),
    ]

    all_passed = True

    for status, order_type, amount, filled, description in test_cases:
        order = NormalizedOrder(
            id='test',
            status=status,
            side='sell',
            amount=amount,
            filled=filled,
            price=1.0,
            average=1.0,
            symbol='TEST',
            type=order_type,
            raw_data={}
        )

        try:
            result = ExchangeResponseAdapter.is_order_filled(order)
            print(f"\n  Test: {description}")
            print(f"    is_order_filled() = {result}")

            if result is False:
                print(f"    ✅ PASS: Correctly returns False")
            else:
                print(f"    ❌ FAIL: Should return False for invalid status")
                all_passed = False

        except Exception as e:
            print(f"\n  Test: {description}")
            print(f"    ❌ EXCEPTION: {e}")
            all_passed = False

    return all_passed


def test_edge_cases():
    """
    TEST 5: Edge cases
    """
    print("\n" + "=" * 70)
    print("TEST 5: Edge cases")
    print("=" * 70)

    edge_cases = [
        {'status': ''},  # Empty string
        {'status': 0},   # Falsy number
        {'status': False},  # Boolean False
        {},  # Key missing entirely
    ]

    for i, data in enumerate(edge_cases, 1):
        print(f"\n  Case {i}: {data}")

        # Old way (WRONG)
        old_result = data.get('status', 'unknown')
        print(f"    Old: data.get('status', 'unknown') = {repr(old_result)}")

        # New way (CORRECT)
        new_result = data.get('status') or 'unknown'
        print(f"    New: data.get('status') or 'unknown' = {repr(new_result)}")

        if new_result == 'unknown':
            print(f"    ✅ PASS: Handles edge case correctly")
        else:
            print(f"    ❌ FAIL: Should be 'unknown'")


def main():
    """Запуск всех тестов"""
    print("\n" + "🔬" * 35)
    print("TESTING: ExchangeResponseAdapter None handling")
    print("🔬" * 35)

    results = {}

    # Test 1: Python behavior
    results['dict_get_none'] = test_python_dict_get_behavior()

    # Test 2: Bybit normalizer
    results['bybit_normalizer'] = test_normalize_bybit_order_with_none_status()

    # Test 3: Binance normalizer
    results['binance_normalizer'] = test_normalize_binance_order_with_none_status()

    # Test 4: is_order_filled
    results['is_order_filled'] = test_is_order_filled_with_none()

    # Test 5: Edge cases
    test_edge_cases()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"\n1. Python dict.get() has None trap: {'❌ CONFIRMED' if results['dict_get_none'] else '✅ OK'}")
    print(f"2. Bybit normalizer handles None: {'✅ FIXED' if results['bybit_normalizer'] else '❌ BUG EXISTS'}")
    print(f"3. Binance normalizer handles None: {'✅ FIXED' if results['binance_normalizer'] else '❌ BUG EXISTS'}")
    print(f"4. is_order_filled handles None: {'✅ FIXED' if results['is_order_filled'] else '❌ BUG EXISTS'}")

    # Overall verdict
    print("\n" + "=" * 70)
    if all([results['bybit_normalizer'], results['binance_normalizer'], results['is_order_filled']]):
        print("✅ ALL TESTS PASSED - BUG IS FIXED")
        print("\nThe code correctly handles None/unknown status values.")
        return 0
    else:
        print("❌ SOME TESTS FAILED - BUG STILL EXISTS")
        print("\nThe bug needs to be fixed in exchange_response_adapter.py:")
        print("  1. Line 86: _normalize_bybit_order status handling")
        print("  2. Line 153: _normalize_binance_order status handling")
        print("  3. Line 195: is_order_filled None check")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
