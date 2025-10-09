#!/usr/bin/env python3
"""
Test ExchangeManager Rate Limiters

Проверяет что все критичные методы используют rate_limiter.execute_request
"""
import sys
import inspect
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.exchange_manager import ExchangeManager


def test_rate_limiters():
    """Test that critical methods use rate limiter"""

    print("="*80)
    print("⚡ EXCHANGE MANAGER RATE LIMITERS TEST")
    print("="*80)
    print()

    passed = []
    failed = []

    # Methods that MUST use rate_limiter.execute_request
    critical_methods = [
        'cancel_order',
        'cancel_all_orders',
        'fetch_order',
        'fetch_open_orders',
        'fetch_closed_orders',
        'fetch_closed_order',
    ]

    print(f"Checking {len(critical_methods)} critical methods...\n")

    for method_name in critical_methods:
        try:
            # Get method from ExchangeManager
            if not hasattr(ExchangeManager, method_name):
                failed.append(f"❌ Method '{method_name}' NOT found in ExchangeManager")
                continue

            method = getattr(ExchangeManager, method_name)

            # Get source code
            source = inspect.getsource(method)

            # Check if it uses rate_limiter.execute_request
            if 'rate_limiter.execute_request' in source:
                passed.append(f"✅ {method_name}: uses rate_limiter")
                print(f"   ✓ {method_name}")
            else:
                failed.append(f"❌ {method_name}: NO rate_limiter usage!")
                print(f"   ✗ {method_name} - MISSING rate_limiter!")

        except Exception as e:
            failed.append(f"❌ {method_name}: check failed - {e}")

    # Additional check: Count rate_limiter.execute_request calls
    try:
        em_source = inspect.getsource(ExchangeManager)
        limiter_count = em_source.count('rate_limiter.execute_request')
        print(f"\n📊 Total rate_limiter.execute_request calls: {limiter_count}")

        # We expect at least 15 calls (many methods already had it)
        if limiter_count >= 15:
            passed.append(f"✅ Rate limiter used {limiter_count} times (healthy)")
        else:
            failed.append(f"❌ Rate limiter only used {limiter_count} times (too few!)")

    except Exception as e:
        failed.append(f"❌ Failed to count rate_limiter calls: {e}")

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
    success = test_rate_limiters()

    if success:
        print("\n✅ RATE LIMITERS TEST PASSED")
        print("   All critical methods are protected from rate limit violations")
        return 0
    else:
        print("\n❌ RATE LIMITERS TEST FAILED")
        print("   Some methods are missing rate limiter protection!")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
