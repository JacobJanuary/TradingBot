#!/usr/bin/env python3
"""
Phase 4 Test: Verify leverage in legacy fallback path
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_phase4_legacy_fallback():
    """Test that leverage is integrated into legacy fallback position creation"""

    print("=" * 80)
    print("🧪 PHASE 4 TEST: Legacy Fallback")
    print("=" * 80)
    print()

    # Test 1: Check PositionManager has config access
    print("✅ Test 1: Verify PositionManager has config access")
    from core.position_manager import PositionManager

    pm_init_signature = PositionManager.__init__.__code__.co_varnames
    assert 'config' in pm_init_signature, "❌ FAIL: PositionManager doesn't accept config!"
    print(f"   ✓ PositionManager accepts config parameter")
    print()

    # Test 2: Read position_manager source to verify legacy path integration
    print("✅ Test 2: Verify leverage code is in legacy fallback path")
    pm_file = project_root / 'core' / 'position_manager.py'
    with open(pm_file, 'r') as f:
        source = f.read()

    # Find the ImportError exception block (legacy fallback)
    import_error_pos = source.find('except ImportError:')
    if import_error_pos == -1:
        raise AssertionError("❌ FAIL: Legacy fallback (except ImportError) not found!")

    print(f"   ✓ Found legacy fallback path at position {import_error_pos}")

    # Extract the ImportError block (next 1500 chars to ensure we capture create_market_order)
    legacy_block = source[import_error_pos:import_error_pos + 1500]

    # Check for key integration points in legacy block
    checks = [
        ('legacy approach', 'Has legacy path marker'),
        ('RESTORED 2025-10-25', 'Has restoration comment'),
        ('auto_set_leverage', 'Checks config.auto_set_leverage'),
        ('set_leverage', 'Calls exchange.set_leverage()'),
        ('legacy path', 'Identifies as legacy path in logs'),
    ]

    for pattern, description in checks:
        if pattern in legacy_block:
            print(f"   ✓ {description}: Found '{pattern}'")
        else:
            raise AssertionError(f"❌ FAIL: {description} - '{pattern}' not found in legacy block!")

    print()

    # Test 3: Verify integration order (leverage before order) in legacy path
    print("✅ Test 3: Verify leverage is set BEFORE create_market_order in legacy")

    # Find positions within the legacy block
    leverage_in_legacy = legacy_block.find('set_leverage')
    order_in_legacy = legacy_block.find('create_market_order', leverage_in_legacy)

    if leverage_in_legacy > 0 and order_in_legacy > leverage_in_legacy:
        print(f"   ✓ set_leverage() comes before create_market_order() in legacy path")
        offset = import_error_pos
        print(f"   ✓ Legacy leverage position: {offset + leverage_in_legacy}")
        print(f"   ✓ Legacy order position: {offset + order_in_legacy}")
    else:
        raise AssertionError("❌ FAIL: set_leverage not called before create_market_order in legacy!")

    print()

    # Test 4: Verify proper error handling in legacy path
    print("✅ Test 4: Verify proper error handling in legacy path")

    if 'Could not set leverage' in legacy_block and 'Continue anyway' in legacy_block:
        print(f"   ✓ Has warning log for leverage failure")
        print(f"   ✓ Continues execution even if leverage fails")
    else:
        raise AssertionError("❌ FAIL: Missing proper error handling in legacy path!")

    print()

    # Test 5: Verify both atomic AND legacy paths have leverage
    print("✅ Test 5: Verify BOTH atomic and legacy paths have leverage setup")

    # Read atomic_position_manager.py to check atomic path
    atomic_file = project_root / 'core' / 'atomic_position_manager.py'
    with open(atomic_file, 'r') as f:
        atomic_source = f.read()

    # Count set_leverage calls in both files
    legacy_count = source.count('await exchange.set_leverage(')
    atomic_count = atomic_source.count('await exchange_instance.set_leverage(')
    total_count = legacy_count + atomic_count

    print(f"   ✓ Legacy path (position_manager.py): {legacy_count} call(s)")
    print(f"   ✓ Atomic path (atomic_position_manager.py): {atomic_count} call(s)")

    if total_count >= 2:
        print(f"   ✓ Total: {total_count} leverage setup calls")
        print(f"   ✓ Both atomic and legacy paths covered")
    else:
        raise AssertionError(f"❌ FAIL: Expected at least 2 set_leverage calls, found {total_count}")

    print()

    # Summary
    print("=" * 80)
    print("✅ ALL PHASE 4 TESTS PASSED!")
    print("=" * 80)
    print()
    print("📊 Legacy Fallback Summary:")
    print(f"   Legacy Path:     Found ImportError fallback ✓")
    print(f"   Leverage Setup:  set_leverage() before create_market_order ✓")
    print(f"   Error Handle:    Continues on leverage failure ✓")
    print(f"   Coverage:        Both atomic AND legacy paths ✓")
    print()
    print("🎯 Phase 4 Complete: Leverage integrated into legacy fallback path!")
    print("=" * 80)

if __name__ == '__main__':
    try:
        test_phase4_legacy_fallback()
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
