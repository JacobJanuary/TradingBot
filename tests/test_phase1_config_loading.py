#!/usr/bin/env python3
"""
Phase 1 Test: Verify leverage config loading
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_phase1_config_loading():
    """Test that leverage configuration is loaded correctly"""

    print("=" * 80)
    print("🧪 PHASE 1 TEST: Config Loading")
    print("=" * 80)
    print()

    # Import config (this will load .env)
    from config.settings import config

    # Test 1: Check that leverage field exists
    print("✅ Test 1: Check leverage field exists")
    assert hasattr(config.trading, 'leverage'), "❌ FAIL: leverage field missing!"
    print(f"   ✓ config.trading.leverage = {config.trading.leverage}")
    print()

    # Test 2: Check that max_leverage field exists
    print("✅ Test 2: Check max_leverage field exists")
    assert hasattr(config.trading, 'max_leverage'), "❌ FAIL: max_leverage field missing!"
    print(f"   ✓ config.trading.max_leverage = {config.trading.max_leverage}")
    print()

    # Test 3: Check that auto_set_leverage field exists
    print("✅ Test 3: Check auto_set_leverage field exists")
    assert hasattr(config.trading, 'auto_set_leverage'), "❌ FAIL: auto_set_leverage field missing!"
    print(f"   ✓ config.trading.auto_set_leverage = {config.trading.auto_set_leverage}")
    print()

    # Test 4: Verify defaults or .env values
    print("✅ Test 4: Verify values are reasonable")
    assert isinstance(config.trading.leverage, int), "❌ FAIL: leverage should be int!"
    assert isinstance(config.trading.max_leverage, int), "❌ FAIL: max_leverage should be int!"
    assert isinstance(config.trading.auto_set_leverage, bool), "❌ FAIL: auto_set_leverage should be bool!"

    assert 1 <= config.trading.leverage <= 125, f"❌ FAIL: leverage {config.trading.leverage} out of range!"
    assert 1 <= config.trading.max_leverage <= 125, f"❌ FAIL: max_leverage {config.trading.max_leverage} out of range!"
    assert config.trading.leverage <= config.trading.max_leverage, "❌ FAIL: leverage > max_leverage!"

    print(f"   ✓ leverage: {config.trading.leverage}x (valid range)")
    print(f"   ✓ max_leverage: {config.trading.max_leverage}x (valid range)")
    print(f"   ✓ auto_set_leverage: {config.trading.auto_set_leverage}")
    print()

    # Test 5: Check .env loading
    print("✅ Test 5: Check .env loading")
    leverage_from_env = os.getenv('LEVERAGE')
    if leverage_from_env:
        expected = int(leverage_from_env)
        assert config.trading.leverage == expected, f"❌ FAIL: Expected {expected}, got {config.trading.leverage}"
        print(f"   ✓ LEVERAGE loaded from .env: {leverage_from_env}")
    else:
        print(f"   ℹ️  LEVERAGE not in .env, using default: {config.trading.leverage}")

    max_leverage_from_env = os.getenv('MAX_LEVERAGE')
    if max_leverage_from_env:
        expected = int(max_leverage_from_env)
        assert config.trading.max_leverage == expected, f"❌ FAIL: Expected {expected}, got {config.trading.max_leverage}"
        print(f"   ✓ MAX_LEVERAGE loaded from .env: {max_leverage_from_env}")
    else:
        print(f"   ℹ️  MAX_LEVERAGE not in .env, using default: {config.trading.max_leverage}")

    auto_set_from_env = os.getenv('AUTO_SET_LEVERAGE')
    if auto_set_from_env:
        expected = auto_set_from_env.lower() == 'true'
        assert config.trading.auto_set_leverage == expected, f"❌ FAIL: Expected {expected}, got {config.trading.auto_set_leverage}"
        print(f"   ✓ AUTO_SET_LEVERAGE loaded from .env: {auto_set_from_env}")
    else:
        print(f"   ℹ️  AUTO_SET_LEVERAGE not in .env, using default: {config.trading.auto_set_leverage}")
    print()

    # Summary
    print("=" * 80)
    print("✅ ALL PHASE 1 TESTS PASSED!")
    print("=" * 80)
    print()
    print("📊 Config Summary:")
    print(f"   Leverage:           {config.trading.leverage}x")
    print(f"   Max Leverage:       {config.trading.max_leverage}x")
    print(f"   Auto-Set Leverage:  {config.trading.auto_set_leverage}")
    print()
    print("🎯 Phase 1 Complete: Config loading is working correctly!")
    print("=" * 80)

if __name__ == '__main__':
    try:
        test_phase1_config_loading()
        sys.exit(0)
    except AssertionError as e:
        print()
        print("=" * 80)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 80)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 80)
        print(f"❌ ERROR: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)
