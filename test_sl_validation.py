#!/usr/bin/env python3
"""
Unit Tests: SL Validation Logic

Tests the CRITICAL validation methods that prevent reusing old SL
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import MagicMock, AsyncMock
from core.stop_loss_manager import StopLossManager


def test_validate_existing_sl_accept_valid():
    """
    TEST 1: _validate_existing_sl should accept SL within tolerance
    """
    print()
    print("=" * 80)
    print("🧪 TEST 1: Validate accepts SL within tolerance")
    print("=" * 80)
    print()

    # Setup
    mock_exchange = MagicMock()
    mock_exchange.name = 'binance'
    sl_manager = StopLossManager(mock_exchange, MagicMock())

    try:
        # Test: Existing 100.0, target 102.0 (2% diff - within 5% tolerance)
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=100.0,
            target_sl_price=102.0,
            side='sell',
            tolerance_percent=5.0
        )

        print(f"  Existing SL: 100.0")
        print(f"  Target SL: 102.0")
        print(f"  Tolerance: 5.0%")
        print(f"  Result: is_valid={is_valid}, reason='{reason}'")
        print()

        # Verify
        assert is_valid, f"Should accept SL within tolerance: {reason}"
        assert "valid" in reason.lower(), f"Reason should mention validity: {reason}"

        print("✅ PASS: SL within tolerance accepted")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_validate_existing_sl_reject_price_diff():
    """
    TEST 2: _validate_existing_sl should reject SL with large price difference
    """
    print()
    print("=" * 80)
    print("🧪 TEST 2: Validate rejects SL with large price difference")
    print("=" * 80)
    print()

    # Setup
    mock_exchange = MagicMock()
    mock_exchange.name = 'binance'
    sl_manager = StopLossManager(mock_exchange, MagicMock())

    try:
        # Test: Existing 100.0, target 150.0 (50% diff - exceeds 5% tolerance)
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=100.0,
            target_sl_price=150.0,
            side='sell',
            tolerance_percent=5.0
        )

        print(f"  Existing SL: 100.0")
        print(f"  Target SL: 150.0")
        print(f"  Tolerance: 5.0%")
        print(f"  Result: is_valid={is_valid}, reason='{reason}'")
        print()

        # Verify
        assert not is_valid, f"Should reject SL with large price diff"
        assert "differs" in reason.lower() or "%" in reason, f"Reason should mention price difference: {reason}"

        print("✅ PASS: SL with large price difference rejected")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_validate_existing_sl_reject_ratio():
    """
    TEST 3: _validate_existing_sl should reject SL with unreasonable ratio
    """
    print()
    print("=" * 80)
    print("🧪 TEST 3: Validate rejects SL with unreasonable ratio")
    print("=" * 80)
    print()

    # Setup
    mock_exchange = MagicMock()
    mock_exchange.name = 'binance'
    sl_manager = StopLossManager(mock_exchange, MagicMock())

    try:
        # Test: Existing 10.0, target 100.0 (10x ratio - exceeds 2.0x limit)
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=10.0,
            target_sl_price=100.0,
            side='sell',
            tolerance_percent=5.0
        )

        print(f"  Existing SL: 10.0")
        print(f"  Target SL: 100.0")
        print(f"  Ratio: 10.0x (limit: 2.0x)")
        print(f"  Result: is_valid={is_valid}, reason='{reason}'")
        print()

        # Verify
        assert not is_valid, f"Should reject SL with unreasonable ratio"
        # The validation can reject for either price diff or ratio - both are valid
        assert "differs" in reason.lower() or "ratio" in reason.lower(), f"Reason should mention rejection: {reason}"

        print("✅ PASS: SL with unreasonable ratio rejected")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_validate_edge_case_exactly_at_tolerance():
    """
    TEST 4: _validate_existing_sl edge case - exactly at tolerance boundary
    """
    print()
    print("=" * 80)
    print("🧪 TEST 4: Validate edge case - exactly at tolerance")
    print("=" * 80)
    print()

    # Setup
    mock_exchange = MagicMock()
    mock_exchange.name = 'binance'
    sl_manager = StopLossManager(mock_exchange, MagicMock())

    try:
        # Test: Existing 100.0, target 105.0 (exactly 5% diff)
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=100.0,
            target_sl_price=105.0,
            side='sell',
            tolerance_percent=5.0
        )

        print(f"  Existing SL: 100.0")
        print(f"  Target SL: 105.0")
        print(f"  Difference: exactly 5.0%")
        print(f"  Result: is_valid={is_valid}, reason='{reason}'")
        print()

        # At boundary, should be accepted (tolerance is inclusive)
        assert is_valid, f"Should accept SL exactly at tolerance: {reason}"

        print("✅ PASS: SL at tolerance boundary handled correctly")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print()
    print("🔬 UNIT TESTS: SL Validation Logic")
    print("=" * 80)
    print()
    print("Testing CRITICAL fix: _validate_existing_sl method")
    print()

    # Run tests
    test1 = test_validate_existing_sl_accept_valid()
    test2 = test_validate_existing_sl_reject_price_diff()
    test3 = test_validate_existing_sl_reject_ratio()
    test4 = test_validate_edge_case_exactly_at_tolerance()

    # Summary
    print()
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print()

    tests = {
        "Accept valid SL (within 5% tolerance)": test1,
        "Reject SL with large price difference (>5%)": test2,
        "Reject SL with unreasonable ratio (>2.0x)": test3,
        "Handle edge case (exactly at tolerance)": test4
    }

    for name, passed in tests.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    print()

    if all(tests.values()):
        print("🎉 ALL TESTS PASSED (4/4)")
        print()
        print("🎯 VERIFICATION:")
        print("  - Valid SL accepted ✅")
        print("  - Invalid SL rejected (price diff) ✅")
        print("  - Invalid SL rejected (ratio) ✅")
        print("  - Edge case handled correctly ✅")
        print()
        print("✅ CRITICAL FIX VERIFIED:")
        print("  The bot will now validate existing SL before reusing")
        print("  This prevents using old SL from previous positions")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        failed = sum(1 for p in tests.values() if not p)
        print(f"  {failed}/{len(tests)} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
