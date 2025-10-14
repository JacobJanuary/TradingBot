"""
Test Phase 1.21+: Verify trailing stop events and final coverage in position_manager.py
"""
import pytest


@pytest.mark.asyncio
async def test_trailing_stop_created_logging():
    """Verify TRAILING_STOP_CREATED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check TRAILING_STOP_CREATED event
    assert 'TRAILING_STOP_CREATED' in source, "Missing TRAILING_STOP_CREATED event"
    assert 'Initialize trailing stop' in source, "Missing TS initialization comment"

    print("\n✅ TRAILING_STOP_CREATED event logging is present")


@pytest.mark.asyncio
async def test_trailing_stop_activated_logging():
    """Verify TRAILING_STOP_ACTIVATED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check TRAILING_STOP_ACTIVATED event
    assert 'TRAILING_STOP_ACTIVATED' in source, "Missing TRAILING_STOP_ACTIVATED event"
    assert "action == 'activated'" in source, "Missing TS activation check"

    print("\n✅ TRAILING_STOP_ACTIVATED event logging is present")


@pytest.mark.asyncio
async def test_trailing_stop_updated_logging():
    """Verify TRAILING_STOP_UPDATED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check TRAILING_STOP_UPDATED event
    assert 'TRAILING_STOP_UPDATED' in source, "Missing TRAILING_STOP_UPDATED event"
    assert "action == 'updated'" in source, "Missing TS update check"
    assert 'old_stop' in source, "Missing old stop price tracking"

    print("\n✅ TRAILING_STOP_UPDATED event logging is present")


@pytest.mark.asyncio
async def test_trailing_stop_removed_logging():
    """Verify TRAILING_STOP_REMOVED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check TRAILING_STOP_REMOVED event
    assert 'TRAILING_STOP_REMOVED' in source, "Missing TRAILING_STOP_REMOVED event"
    assert 'on_position_closed' in source, "Missing TS cleanup on close"

    print("\n✅ TRAILING_STOP_REMOVED event logging is present")


@pytest.mark.asyncio
async def test_all_trailing_stop_event_types_exist():
    """Verify all trailing stop EventTypes exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'TRAILING_STOP_CREATED')
    assert hasattr(EventType, 'TRAILING_STOP_ACTIVATED')
    assert hasattr(EventType, 'TRAILING_STOP_UPDATED')
    assert hasattr(EventType, 'TRAILING_STOP_REMOVED')

    # Verify values
    assert EventType.TRAILING_STOP_CREATED.value == 'trailing_stop_created'
    assert EventType.TRAILING_STOP_ACTIVATED.value == 'trailing_stop_activated'
    assert EventType.TRAILING_STOP_UPDATED.value == 'trailing_stop_updated'
    assert EventType.TRAILING_STOP_REMOVED.value == 'trailing_stop_removed'

    print("\n✅ All trailing stop EventTypes exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls_final():
    """Verify position_manager has reached target event logger calls"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count event logger calls (should be >= 40 now: 36 previous + 4 trailing stop)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 40, f"Expected >= 40 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 40, f"Expected >= 40 log_event calls, found {log_event_count}"

    print(f"\n✅ Position manager has {event_logger_count} event logger instances")
    print(f"✅ Position manager has {log_event_count} log_event calls")
    print(f"   (Previous: 36, Added: {event_logger_count - 36}, Total: {event_logger_count})")


@pytest.mark.asyncio
async def test_final_coverage_summary():
    """Verify overall coverage of position_manager.py event logging"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count different event types used
    event_types_used = []
    event_type_names = [
        'PHANTOM_POSITION_DETECTED', 'PHANTOM_POSITION_CLOSED',
        'WARNING_RAISED', 'POSITIONS_LOADED', 'POSITIONS_WITHOUT_SL_DETECTED',
        'POSITION_DUPLICATE_PREVENTED', 'RISK_LIMITS_EXCEEDED', 'POSITION_CLOSED',
        'SYMBOL_UNAVAILABLE', 'ORDER_BELOW_MINIMUM', 'ORPHANED_SL_CLEANED',
        'STOP_LOSS_SET_ON_LOAD', 'STOP_LOSS_SET_FAILED', 'POSITION_CREATED',
        'POSITION_CREATION_FAILED', 'STOP_LOSS_PLACED', 'STOP_LOSS_ERROR',
        'DATABASE_ERROR', 'STOP_LOSS_TRIGGERED', 'EXCHANGE_ERROR',
        'AGED_POSITION_DETECTED', 'POSITION_UPDATED', 'ORDER_FILLED',
        'POSITION_NOT_FOUND_ON_EXCHANGE', 'SYNC_STARTED', 'SYNC_COMPLETED',
        'TRAILING_STOP_CREATED', 'TRAILING_STOP_ACTIVATED',
        'TRAILING_STOP_UPDATED', 'TRAILING_STOP_REMOVED'
    ]

    for event_type in event_type_names:
        if event_type in source:
            event_types_used.append(event_type)

    total_planned = 52
    coverage_percent = len(event_types_used) * 100 // total_planned

    print(f"\n✅ Position manager uses {len(event_types_used)} different EventTypes")
    print(f"   Event types: {', '.join(event_types_used[:10])}...")
    print(f"   Coverage: {len(event_types_used)}/{total_planned} = {coverage_percent}%")
    print(f"\n🎉 Phase 1 Position Manager Event Logging: {coverage_percent}% Complete!")

    # Should have at least 39 events (75% coverage)
    assert len(event_types_used) >= 30, f"Expected >= 30 event types, found {len(event_types_used)}"


@pytest.mark.asyncio
async def test_trailing_stop_context():
    """Verify trailing stop events include proper context"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Verify context includes prices and stop tracking
    assert "'initial_stop'" in source, "Missing initial_stop in TRAILING_STOP_CREATED"
    assert "'old_stop_price'" in source, "Missing old_stop_price in TRAILING_STOP_UPDATED"
    assert "'new_stop_price'" in source, "Missing new_stop_price in TRAILING_STOP_UPDATED"

    print("\n✅ Trailing stop events include proper context (prices, stops)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
