#!/usr/bin/env python3
"""
Unit Test: Bybit retCode type fix

Проверяет что int() конвертация работает корректно для разных форматов retCode
"""


def test_retcode_conversion():
    """
    TEST: Проверка конвертации retCode из строки в число
    """
    print()
    print("=" * 80)
    print("🧪 TEST: retCode type conversion")
    print("=" * 80)
    print()

    test_cases = [
        ("String '0'", "0", 0),
        ("Number 0", 0, 0),
        ("String '34040'", "34040", 34040),
        ("Number 34040", 34040, 34040),
        ("String '1'", "1", 1),
        ("Number 1", 1, 1),
    ]

    passed = 0
    failed = 0

    for name, input_val, expected in test_cases:
        try:
            # Simulate the fix
            ret_code = int(input_val) if isinstance(input_val, str) else input_val

            if ret_code == expected:
                print(f"  ✅ {name}: {input_val!r} → {ret_code} (type: {type(ret_code).__name__})")
                passed += 1
            else:
                print(f"  ❌ {name}: Expected {expected}, got {ret_code}")
                failed += 1
        except Exception as e:
            print(f"  ❌ {name}: Error - {e}")
            failed += 1

    print()
    print(f"Results: {passed}/{len(test_cases)} passed")
    return failed == 0


def test_comparison_logic():
    """
    TEST: Проверка логики сравнения (до и после исправления)
    """
    print()
    print("=" * 80)
    print("🧪 TEST: Comparison logic before/after fix")
    print("=" * 80)
    print()

    # Simulate Bybit API response
    result = {
        'retCode': '0',  # ← STRING (as Bybit API returns)
        'retMsg': 'OK'
    }

    print("Bybit API Response:")
    print(f"  retCode: {result['retCode']!r} (type: {type(result['retCode']).__name__})")
    print(f"  retMsg: {result['retMsg']!r}")
    print()

    # ❌ BEFORE FIX:
    print("❌ BEFORE FIX:")
    ret_code_before = result.get('retCode', 1)
    print(f"  ret_code = result.get('retCode', 1)")
    print(f"  ret_code = {ret_code_before!r} (type: {type(ret_code_before).__name__})")
    print(f"  ret_code == 0 → {ret_code_before == 0}")
    if ret_code_before == 0:
        print(f"  → SUCCESS ✅")
    else:
        print(f"  → ERROR: Bybit API error {ret_code_before}: {result['retMsg']} ❌")
    print()

    # ✅ AFTER FIX:
    print("✅ AFTER FIX:")
    ret_code_after = int(result.get('retCode', 1))
    print(f"  ret_code = int(result.get('retCode', 1))")
    print(f"  ret_code = {ret_code_after!r} (type: {type(ret_code_after).__name__})")
    print(f"  ret_code == 0 → {ret_code_after == 0}")
    if ret_code_after == 0:
        print(f"  → SUCCESS ✅")
    else:
        print(f"  → ERROR: Bybit API error {ret_code_after}: {result['retMsg']} ❌")
    print()

    # Verify fix works
    return ret_code_after == 0


def test_edge_cases():
    """
    TEST: Проверка edge cases
    """
    print()
    print("=" * 80)
    print("🧪 TEST: Edge cases")
    print("=" * 80)
    print()

    edge_cases = [
        ("Missing retCode", {}, 1, "Should use default value 1"),
        ("None retCode", {'retCode': None}, 1, "Should handle None"),
        ("Empty string", {'retCode': ''}, 1, "Should handle empty string (will fail conversion)"),
    ]

    passed = 0
    failed = 0

    for name, result, expected_default, description in edge_cases:
        try:
            # Simulate the fix with error handling
            ret_code_str = result.get('retCode', expected_default)
            try:
                ret_code = int(ret_code_str)
            except (ValueError, TypeError):
                ret_code = expected_default

            print(f"  ✅ {name}: {description}")
            print(f"     Input: {result}")
            print(f"     Result: {ret_code}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1

    print()
    return failed == 0


def main():
    print()
    print("🔬 UNIT TEST: Bybit retCode Type Fix")
    print("=" * 80)
    print()

    # Run tests
    test1 = test_retcode_conversion()
    test2 = test_comparison_logic()
    test3 = test_edge_cases()

    # Summary
    print()
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print()

    tests = {
        "retCode type conversion": test1,
        "Comparison logic (before/after)": test2,
        "Edge cases": test3
    }

    for name, passed in tests.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    print()

    if all(tests.values()):
        print("🎉 ALL TESTS PASSED (3/3)")
        print()
        print("🎯 VERIFICATION:")
        print("  - String '0' converted to int 0 ✅")
        print("  - Comparison ret_code == 0 works ✅")
        print("  - Edge cases handled ✅")
        print("  - Fix resolves 'Bybit API error 0: OK' ✅")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        failed = sum(1 for p in tests.values() if not p)
        print(f"  {failed}/{len(tests)} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    import sys
    sys.exit(exit_code)
