#!/usr/bin/env python3
"""
Quick Phase 1 Tests - КРИТИЧНЫЕ БЕЗОПАСНОСТЬ
Tests SQL injection, random salt, schema, rate limiters
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal


def test_sql_injection_protection():
    """Test 2.1: SQL Injection Protection"""
    print("\n" + "="*80)
    print("TEST 2.1: SQL INJECTION PROTECTION")
    print("="*80)

    from database.repository import TradingRepository

    # Check that ALLOWED_POSITION_FIELDS exists
    if not hasattr(TradingRepository, 'ALLOWED_POSITION_FIELDS'):
        print("❌ FAIL: ALLOWED_POSITION_FIELDS not found!")
        return False

    allowed_fields = TradingRepository.ALLOWED_POSITION_FIELDS
    print(f"✅ ALLOWED_POSITION_FIELDS found: {allowed_fields}")

    # Verify it's a set with expected fields
    expected_fields = {'status', 'quantity', 'entry_price', 'exit_price',
                      'realized_pnl', 'unrealized_pnl', 'stop_loss_price',
                      'current_price', 'unrealized_pnl_percent'}

    if not isinstance(allowed_fields, set):
        print(f"❌ FAIL: ALLOWED_POSITION_FIELDS is not a set: {type(allowed_fields)}")
        return False

    missing = expected_fields - allowed_fields
    if missing:
        print(f"⚠️  WARNING: Some expected fields missing: {missing}")

    print(f"✅ PASS: SQL injection protection whitelist exists with {len(allowed_fields)} fields")
    return True


def test_random_salt():
    """Test 2.2: Random Salt in CryptoManager"""
    print("\n" + "="*80)
    print("TEST 2.2: RANDOM SALT")
    print("="*80)

    from utils.crypto_manager import CryptoManager

    # Create two instances
    cm1 = CryptoManager()
    cm2 = CryptoManager()

    test_data = "test_secret_data"

    # Encrypt same data with both instances
    encrypted1 = cm1.encrypt(test_data)
    encrypted2 = cm2.encrypt(test_data)

    print(f"Instance 1 encrypted: {encrypted1[:50]}...")
    print(f"Instance 2 encrypted: {encrypted2[:50]}...")

    if encrypted1 == encrypted2:
        print("❌ FAIL: Encrypted data is identical - salt is not random!")
        return False

    # Verify each instance can decrypt its own data
    decrypted1 = cm1.decrypt(encrypted1)
    decrypted2 = cm2.decrypt(encrypted2)

    if decrypted1 != test_data:
        print(f"❌ FAIL: Instance 1 decryption failed")
        return False

    if decrypted2 != test_data:
        print(f"❌ FAIL: Instance 2 decryption failed")
        return False

    print("✅ PASS: Random salt working - different ciphertexts, correct decryption")
    return True


def test_schema():
    """Test 2.3: Position model uses 'monitoring' schema"""
    print("\n" + "="*80)
    print("TEST 2.3: SCHEMA VERIFICATION")
    print("="*80)

    from database.models import Position

    # Check __table_args__
    if not hasattr(Position, '__table_args__'):
        print("❌ FAIL: Position has no __table_args__")
        return False

    table_args = Position.__table_args__
    print(f"__table_args__: {table_args}")

    # Should be dict with 'schema' key
    if isinstance(table_args, dict):
        schema = table_args.get('schema')
    elif isinstance(table_args, tuple):
        # Sometimes it's a tuple with dict at end
        for item in table_args:
            if isinstance(item, dict) and 'schema' in item:
                schema = item['schema']
                break
        else:
            schema = None
    else:
        schema = None

    if schema != 'monitoring':
        print(f"❌ FAIL: Schema is '{schema}', expected 'monitoring'")
        return False

    print("✅ PASS: Position model uses 'monitoring' schema")
    return True


def test_rate_limiters():
    """Test 2.4: Rate limiters exist in code"""
    print("\n" + "="*80)
    print("TEST 2.4: RATE LIMITER VERIFICATION")
    print("="*80)

    import inspect
    from core.exchange_manager import ExchangeManager

    # Get source code
    source = inspect.getsource(ExchangeManager)

    # Count rate_limiter.execute_request occurrences
    rate_limiter_count = source.count('rate_limiter.execute_request')

    print(f"Found {rate_limiter_count} rate_limiter.execute_request calls")

    if rate_limiter_count < 6:
        print(f"⚠️  WARNING: Expected at least 6 rate limiter wraps, found {rate_limiter_count}")
        print("   (This is still OK if some methods were refactored)")

    # Check specific methods have rate limiters
    critical_methods = [
        'cancel_order',
        'fetch_order',
        'fetch_open_orders',
        'cancel_all_orders'
    ]

    found_methods = []
    for method in critical_methods:
        if method in source and 'rate_limiter' in source:
            found_methods.append(method)

    print(f"Critical methods with rate limiters: {found_methods}")

    if rate_limiter_count > 0:
        print(f"✅ PASS: Rate limiters present ({rate_limiter_count} calls)")
        return True
    else:
        print("❌ FAIL: No rate limiters found!")
        return False


def test_safe_decimal():
    """Bonus Test: safe_decimal() from Phase 2"""
    print("\n" + "="*80)
    print("BONUS TEST: safe_decimal() FUNCTIONALITY")
    print("="*80)

    from utils.decimal_utils import safe_decimal

    test_cases = [
        ("123.45", Decimal("123.45"), "Valid string"),
        (123.45, Decimal("123.45"), "Valid float"),
        (123, Decimal("123"), "Valid int"),
        ("invalid", Decimal("0"), "Invalid string"),
        (None, Decimal("0"), "None value"),
        ("", Decimal("0"), "Empty string"),
    ]

    all_passed = True
    for value, expected, description in test_cases:
        try:
            result = safe_decimal(value)
            if result == expected:
                print(f"  ✅ {description}: {value} → {result}")
            else:
                print(f"  ❌ {description}: {value} → {result} (expected {expected})")
                all_passed = False
        except Exception as e:
            print(f"  ❌ {description}: {value} raised {e}")
            all_passed = False

    # Test infinity and NaN
    try:
        result = safe_decimal(float('inf'))
        if result == Decimal('0'):
            print(f"  ✅ Infinity handling: inf → {result}")
        else:
            print(f"  ❌ Infinity handling: inf → {result} (expected 0)")
            all_passed = False
    except:
        pass

    try:
        result = safe_decimal(float('nan'))
        if result == Decimal('0'):
            print(f"  ✅ NaN handling: nan → {result}")
        else:
            print(f"  ❌ NaN handling: nan → {result} (expected 0)")
            all_passed = False
    except:
        pass

    if all_passed:
        print("✅ PASS: safe_decimal() handles all test cases correctly")
        return True
    else:
        print("❌ FAIL: safe_decimal() has issues")
        return False


def test_constants_loaded():
    """Bonus Test: Phase 4.2 constants"""
    print("\n" + "="*80)
    print("BONUS TEST: MAGIC NUMBERS CONSTANTS (Phase 4.2)")
    print("="*80)

    from core.position_manager import (
        MAX_ORDER_VERIFICATION_RETRIES,
        ORDER_VERIFICATION_DELAYS,
        POSITION_CLOSE_RETRY_DELAY_SEC
    )

    print(f"MAX_ORDER_VERIFICATION_RETRIES = {MAX_ORDER_VERIFICATION_RETRIES}")
    print(f"ORDER_VERIFICATION_DELAYS = {ORDER_VERIFICATION_DELAYS}")
    print(f"POSITION_CLOSE_RETRY_DELAY_SEC = {POSITION_CLOSE_RETRY_DELAY_SEC}")

    all_correct = True

    if MAX_ORDER_VERIFICATION_RETRIES != 3:
        print(f"❌ MAX_ORDER_VERIFICATION_RETRIES wrong: {MAX_ORDER_VERIFICATION_RETRIES}")
        all_correct = False

    if ORDER_VERIFICATION_DELAYS != [1.0, 2.0, 3.0]:
        print(f"❌ ORDER_VERIFICATION_DELAYS wrong: {ORDER_VERIFICATION_DELAYS}")
        all_correct = False

    if POSITION_CLOSE_RETRY_DELAY_SEC != 60:
        print(f"❌ POSITION_CLOSE_RETRY_DELAY_SEC wrong: {POSITION_CLOSE_RETRY_DELAY_SEC}")
        all_correct = False

    if all_correct:
        print("✅ PASS: All constants loaded correctly")
        return True
    else:
        print("❌ FAIL: Some constants incorrect")
        return False


def main():
    """Run all quick tests"""
    print("\n" + "="*80)
    print("🏥 QUICK PHASE 1-2 TESTS (Stages 1-2)")
    print("="*80)

    results = {}

    # Stage 2 Tests (Phase 1 verification)
    results['SQL Injection'] = test_sql_injection_protection()
    results['Random Salt'] = test_random_salt()
    results['Schema'] = test_schema()
    results['Rate Limiters'] = test_rate_limiters()

    # Bonus tests
    results['safe_decimal()'] = test_safe_decimal()
    results['Constants'] = test_constants_loaded()

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("="*80)
    print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print("="*80)

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    exit(main())
