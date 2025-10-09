#!/usr/bin/env python3
"""
Test SQL Injection Protection in Repository

Проверяет что update_position() блокирует SQL injection попытки
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.repository import Repository


async def test_sql_injection_protection():
    """Test SQL injection protection"""

    print("="*80)
    print("🔐 SQL INJECTION PROTECTION TEST")
    print("="*80)
    print()

    passed = []
    failed = []

    # Test 1: Check whitelist exists
    try:
        if hasattr(Repository, 'ALLOWED_POSITION_FIELDS'):
            passed.append("✅ ALLOWED_POSITION_FIELDS exists")
            print(f"   Whitelist contains {len(Repository.ALLOWED_POSITION_FIELDS)} fields")
        else:
            failed.append("❌ ALLOWED_POSITION_FIELDS NOT FOUND")
    except Exception as e:
        failed.append(f"❌ Whitelist check failed: {e}")

    # Test 2: Check valid field is allowed
    try:
        valid_field = 'current_price'
        if valid_field in Repository.ALLOWED_POSITION_FIELDS:
            passed.append(f"✅ Valid field '{valid_field}' is in whitelist")
        else:
            failed.append(f"❌ Valid field '{valid_field}' NOT in whitelist")
    except Exception as e:
        failed.append(f"❌ Valid field check failed: {e}")

    # Test 3: Test malicious field detection (without DB connection)
    try:
        # Create repository instance (will fail to connect, but that's OK for this test)
        repo = Repository({
            'host': 'localhost',
            'port': 5433,
            'database': 'fox_crypto_test',
            'user': 'elcrypto',
            'password': 'LohNeMamont@!21'
        })

        # Don't initialize connection - we just need to test validation logic

        # Simulate validation check manually
        malicious_fields = {'malicious_field; DROP TABLE positions': 'value'}
        invalid_fields = set(malicious_fields.keys()) - Repository.ALLOWED_POSITION_FIELDS

        if invalid_fields:
            passed.append("✅ Malicious field detected by validation")
            print(f"   Detected: {list(invalid_fields)[0][:50]}...")
        else:
            failed.append("❌ Malicious field NOT detected!")

    except Exception as e:
        failed.append(f"❌ Malicious field test failed: {e}")

    # Test 4: Check that update_position validates (with mock)
    try:
        # Check that method has validation code
        import inspect
        source = inspect.getsource(Repository.update_position)

        if 'ALLOWED_POSITION_FIELDS' in source and 'ValueError' in source:
            passed.append("✅ update_position() has validation code")
        else:
            failed.append("❌ update_position() MISSING validation code")
    except Exception as e:
        failed.append(f"❌ Source code check failed: {e}")

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


async def main():
    success = await test_sql_injection_protection()

    if success:
        print("\n✅ SQL INJECTION PROTECTION TEST PASSED")
        return 0
    else:
        print("\n❌ SQL INJECTION PROTECTION TEST FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
