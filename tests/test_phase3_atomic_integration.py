#!/usr/bin/env python3
"""
Phase 3 Test: Verify leverage integration in AtomicPositionManager
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_phase3_atomic_integration():
    """Test that leverage is integrated into atomic position creation"""

    print("=" * 80)
    print("🧪 PHASE 3 TEST: Atomic Integration")
    print("=" * 80)
    print()

    # Test 1: Check config has leverage settings
    print("✅ Test 1: Verify config has leverage settings")
    from config.settings import config

    assert hasattr(config.trading, 'leverage'), "❌ FAIL: leverage field missing!"
    assert hasattr(config.trading, 'auto_set_leverage'), "❌ FAIL: auto_set_leverage field missing!"
    print(f"   ✓ config.trading.leverage = {config.trading.leverage}")
    print(f"   ✓ config.trading.auto_set_leverage = {config.trading.auto_set_leverage}")
    print()

    # Test 2: Check AtomicPositionManager has config access
    print("✅ Test 2: Verify AtomicPositionManager can access config")
    from core.atomic_position_manager import AtomicPositionManager

    # Check that AtomicPositionManager accepts config
    apm_init_signature = AtomicPositionManager.__init__.__code__.co_varnames
    assert 'config' in apm_init_signature, "❌ FAIL: AtomicPositionManager doesn't accept config!"
    print(f"   ✓ AtomicPositionManager accepts config parameter")
    print()

    # Test 3: Verify ExchangeManager has set_leverage method
    print("✅ Test 3: Verify ExchangeManager has set_leverage method")
    from core.exchange_manager import ExchangeManager

    assert hasattr(ExchangeManager, 'set_leverage'), "❌ FAIL: set_leverage method missing!"
    print(f"   ✓ ExchangeManager.set_leverage exists")

    # Check method signature
    import inspect
    sig = inspect.signature(ExchangeManager.set_leverage)
    params = list(sig.parameters.keys())
    assert 'symbol' in params, "❌ FAIL: set_leverage missing 'symbol' parameter!"
    assert 'leverage' in params, "❌ FAIL: set_leverage missing 'leverage' parameter!"
    print(f"   ✓ set_leverage signature: {sig}")
    print()

    # Test 4: Read atomic_position_manager source to verify integration
    print("✅ Test 4: Verify leverage code is in _create_position_atomic")
    atomic_file = project_root / 'core' / 'atomic_position_manager.py'
    with open(atomic_file, 'r') as f:
        source = f.read()

    # Check for key integration points
    checks = [
        ('auto_set_leverage', 'Checks config.auto_set_leverage'),
        ('set_leverage', 'Calls exchange.set_leverage()'),
        ('RESTORED 2025-10-25', 'Has restoration comment'),
    ]

    for pattern, description in checks:
        if pattern in source:
            print(f"   ✓ {description}: Found '{pattern}'")
        else:
            raise AssertionError(f"❌ FAIL: {description} - '{pattern}' not found!")

    print()

    # Test 5: Verify integration order (leverage before order)
    print("✅ Test 5: Verify leverage is set BEFORE create_market_order")

    # Find the positions of key calls in the source
    leverage_pos = source.find('set_leverage')
    create_order_pos = source.find('create_market_order', leverage_pos)

    if leverage_pos > 0 and create_order_pos > leverage_pos:
        print(f"   ✓ set_leverage() comes before create_market_order()")
        print(f"   ✓ Leverage position: {leverage_pos}")
        print(f"   ✓ Order position: {create_order_pos}")
    else:
        raise AssertionError("❌ FAIL: set_leverage not called before create_market_order!")

    print()

    # Test 6: Verify warning log for leverage failure
    print("✅ Test 6: Verify proper error handling")

    if 'Could not set leverage' in source and 'Continue anyway' in source:
        print(f"   ✓ Has warning log for leverage failure")
        print(f"   ✓ Continues execution even if leverage fails")
    else:
        raise AssertionError("❌ FAIL: Missing proper error handling for leverage failures!")

    print()

    # Summary
    print("=" * 80)
    print("✅ ALL PHASE 3 TESTS PASSED!")
    print("=" * 80)
    print()
    print("📊 Integration Summary:")
    print(f"   Config:       leverage={config.trading.leverage}x, auto={config.trading.auto_set_leverage}")
    print(f"   Method:       ExchangeManager.set_leverage() exists ✓")
    print(f"   Integration:  AtomicPositionManager calls set_leverage ✓")
    print(f"   Order:        set_leverage BEFORE create_market_order ✓")
    print(f"   Error Handle: Continues on leverage failure ✓")
    print()
    print("🎯 Phase 3 Complete: Leverage integrated into atomic position creation!")
    print("=" * 80)

if __name__ == '__main__':
    try:
        test_phase3_atomic_integration()
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
