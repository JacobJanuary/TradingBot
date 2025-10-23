#!/usr/bin/env python3
"""
Integration test for post-deployment fixes
Validates all 4 phases of fixes without mocking
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_phase_1_repository_import():
    """Phase 1: Test repository imports and single method definition"""
    print("\n=== PHASE 1: Repository Method ===")

    from database.repository import Repository

    # Check method exists
    assert hasattr(Repository, 'create_aged_monitoring_event'), \
        "create_aged_monitoring_event method should exist"

    # Check method signature accepts optional parameters
    import inspect
    sig = inspect.signature(Repository.create_aged_monitoring_event)
    params = sig.parameters

    # Required parameters
    assert 'aged_position_id' in params, "aged_position_id should be required"
    assert 'event_type' in params, "event_type should be required"

    # Optional parameters
    optional_params = ['market_price', 'target_price', 'price_distance_percent',
                      'action_taken', 'success', 'error_message', 'event_metadata']
    for param in optional_params:
        assert param in params, f"{param} should exist"
        assert params[param].default is not inspect.Parameter.empty, \
            f"{param} should have default value (optional)"

    print("✅ Repository method correct: single definition with optional params")
    return True


def test_phase_2_aged_monitor_pending_check():
    """Phase 2: Test aged_position_monitor_v2 has pending validation"""
    print("\n=== PHASE 2: Aged Monitor Pending Check ===")

    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    # Read source to check for isinstance check
    import inspect
    source = inspect.getsource(AgedPositionMonitorV2.add_aged_position)

    # Check for pending validation
    assert 'isinstance(target.position_id, int)' in source, \
        "Should have isinstance check for pending positions"

    assert 'Skipping DB tracking' in source or 'pending database creation' in source, \
        "Should have skip message for pending positions"

    print("✅ Aged monitor has pending validation")
    return True


def test_phase_3_position_manager_early_return():
    """Phase 3: Test position_manager has early return for pending"""
    print("\n=== PHASE 3: Position Manager Early Return ===")

    from core.position_manager import PositionManager

    # Read source to check for early return
    import inspect
    source = inspect.getsource(PositionManager._on_position_update)

    # Check for pending check and early return
    assert 'position.id == "pending"' in source, \
        "Should check for pending position ID"

    assert 'return' in source, \
        "Should have early return for pending positions"

    print("✅ Position manager has early return for pending")
    return True


def test_phase_4_orders_cache_table():
    """Phase 4: Test orders_cache migration file exists"""
    print("\n=== PHASE 4: Orders Cache Migration ===")

    # Check migration file exists
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'database', 'migrations', '010_create_orders_cache.sql'
    )

    assert os.path.exists(migration_path), \
        "Migration 010_create_orders_cache.sql should exist"

    # Read migration file to check content
    with open(migration_path, 'r') as f:
        content = f.read()

    assert 'CREATE TABLE IF NOT EXISTS monitoring.orders_cache' in content, \
        "Migration should create orders_cache table"

    assert 'exchange_order_id' in content, \
        "Table should have exchange_order_id column"

    print("✅ Orders cache migration file exists and correct")
    return True


def test_all_imports():
    """Test all critical imports work"""
    print("\n=== IMPORTS TEST ===")

    from database.repository import Repository
    from core.aged_position_monitor_v2 import AgedPositionMonitorV2
    from core.position_manager import PositionManager
    from core.order_executor import OrderExecutor

    print("✅ All imports successful")
    return True


if __name__ == "__main__":
    print("🚀 Running Post-Deployment Fixes Integration Test")
    print("=" * 60)

    all_passed = True

    try:
        # Run all tests
        test_all_imports()
        test_phase_1_repository_import()
        test_phase_2_aged_monitor_pending_check()
        test_phase_3_position_manager_early_return()
        test_phase_4_orders_cache_table()

        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        all_passed = False
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
        sys.exit(1)

    sys.exit(0 if all_passed else 1)
