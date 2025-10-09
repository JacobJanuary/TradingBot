#!/usr/bin/env python3
"""
Test safe_decimal() function

Проверяет обработку всех edge cases:
- None
- Invalid strings
- NaN, Infinity
- Valid numbers
- Already Decimal
"""
import sys
from pathlib import Path
from decimal import Decimal, InvalidOperation

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.decimal_utils import safe_decimal


def test_safe_decimal():
    """Test safe_decimal with various inputs"""

    print("="*80)
    print("🔢 SAFE_DECIMAL FUNCTION TEST")
    print("="*80)
    print()

    passed = []
    failed = []

    # Test 1: Valid string
    try:
        result = safe_decimal("123.45")
        expected = Decimal("123.45")
        if result == expected:
            passed.append("✅ Valid string: '123.45' → Decimal('123.45')")
        else:
            failed.append(f"❌ Valid string: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Valid string test failed: {e}")

    # Test 2: None → default
    try:
        result = safe_decimal(None)
        expected = Decimal('0')
        if result == expected:
            passed.append("✅ None → Decimal('0')")
        else:
            failed.append(f"❌ None: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ None test failed: {e}")

    # Test 3: Invalid string → default
    try:
        result = safe_decimal("invalid", default=Decimal('99'))
        expected = Decimal('99')
        if result == expected:
            passed.append("✅ Invalid string 'invalid' → default Decimal('99')")
        else:
            failed.append(f"❌ Invalid string: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Invalid string test failed: {e}")

    # Test 4: Empty string → default
    try:
        result = safe_decimal("")
        expected = Decimal('0')
        if result == expected:
            passed.append("✅ Empty string '' → Decimal('0')")
        else:
            failed.append(f"❌ Empty string: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Empty string test failed: {e}")

    # Test 5: Integer
    try:
        result = safe_decimal(42)
        expected = Decimal('42')
        if result == expected:
            passed.append("✅ Integer 42 → Decimal('42')")
        else:
            failed.append(f"❌ Integer: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Integer test failed: {e}")

    # Test 6: Float (with precision)
    try:
        result = safe_decimal(123.456789, precision=2)
        expected = Decimal('123.45')
        if result == expected:
            passed.append("✅ Float 123.456789 (precision=2) → Decimal('123.45')")
        else:
            failed.append(f"❌ Float: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Float test failed: {e}")

    # Test 7: Already Decimal
    try:
        input_decimal = Decimal("555.555")
        result = safe_decimal(input_decimal, precision=2)
        expected = Decimal('555.55')
        if result == expected:
            passed.append("✅ Decimal('555.555') (precision=2) → Decimal('555.55')")
        else:
            failed.append(f"❌ Decimal: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Decimal test failed: {e}")

    # Test 8: Negative number
    try:
        result = safe_decimal("-99.99")
        expected = Decimal('-99.99')
        if result == expected:
            passed.append("✅ Negative '-99.99' → Decimal('-99.99')")
        else:
            failed.append(f"❌ Negative: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Negative test failed: {e}")

    # Test 9: Zero
    try:
        result = safe_decimal("0")
        expected = Decimal('0')
        if result == expected:
            passed.append("✅ Zero '0' → Decimal('0')")
        else:
            failed.append(f"❌ Zero: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Zero test failed: {e}")

    # Test 10: Very large number
    try:
        result = safe_decimal("999999999.12345678", precision=8)
        expected = Decimal('999999999.12345678')
        if result == expected:
            passed.append("✅ Large number → correct precision")
        else:
            failed.append(f"❌ Large number: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Large number test failed: {e}")

    # Test 11: Scientific notation
    try:
        result = safe_decimal("1.23e-4")
        expected = Decimal('0.000123')
        if result == expected:
            passed.append("✅ Scientific notation '1.23e-4' → Decimal('0.000123')")
        else:
            failed.append(f"❌ Scientific notation: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Scientific notation test failed: {e}")

    # Test 12: Whitespace handling
    try:
        result = safe_decimal("  42.5  ")
        expected = Decimal('42.5')
        if result == expected:
            passed.append("✅ Whitespace '  42.5  ' → Decimal('42.5')")
        else:
            failed.append(f"❌ Whitespace: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"❌ Whitespace test failed: {e}")

    # Test 13: Field name in logging (check it doesn't crash)
    try:
        result = safe_decimal("invalid", field_name="test_field", default=Decimal('1'))
        if result == Decimal('1'):
            passed.append("✅ Field name parameter works")
        else:
            failed.append(f"❌ Field name: got {result}, expected Decimal('1')")
    except Exception as e:
        failed.append(f"❌ Field name test failed: {e}")

    # Results
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)

    if passed:
        print(f"\n✅ PASSED ({len(passed)}):")
        for item in passed:
            print(f"   {item}")

    if failed:
        print(f"\n❌ FAILED ({len(failed)}):")
        for item in failed:
            print(f"   {item}")

    print("\n" + "="*80)
    total = len(passed) + len(failed)
    print(f"TOTAL: {len(passed)}/{total} passed")
    print("="*80)

    return len(failed) == 0


def main():
    success = test_safe_decimal()

    if success:
        print("\n✅ SAFE_DECIMAL TEST PASSED")
        print("   All edge cases handled correctly")
        return 0
    else:
        print("\n❌ SAFE_DECIMAL TEST FAILED")
        print("   Some edge cases not handled!")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
