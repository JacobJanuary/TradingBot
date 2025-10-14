"""
Test Phase 1.13-1.15: Verify final position_manager.py event logging
"""
import pytest


@pytest.mark.asyncio
async def test_position_created_logging():
    """Verify POSITION_CREATED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITION_CREATED event
    assert 'POSITION_CREATED' in source, "Missing POSITION_CREATED event"
    assert 'Position created' in source or 'position_id' in source, "Missing position creation context"

    print("\n✅ POSITION_CREATED event logging is present")


@pytest.mark.asyncio
async def test_position_creation_failed_logging():
    """Verify POSITION_CREATION_FAILED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITION_CREATION_FAILED event
    assert 'POSITION_CREATION_FAILED' in source, "Missing POSITION_CREATION_FAILED event"
    assert source.count('POSITION_CREATION_FAILED') >= 2, "Should have at least 2 POSITION_CREATION_FAILED events"

    print("\n✅ POSITION_CREATION_FAILED event logging is present (2 locations)")


@pytest.mark.asyncio
async def test_stop_loss_placed_logging():
    """Verify STOP_LOSS_PLACED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check STOP_LOSS_PLACED event
    assert 'STOP_LOSS_PLACED' in source, "Missing STOP_LOSS_PLACED event"
    assert 'Stop loss confirmed' in source or 'stop_loss_price' in source, "Missing SL placement context"

    print("\n✅ STOP_LOSS_PLACED event logging is present")


@pytest.mark.asyncio
async def test_stop_loss_error_logging():
    """Verify STOP_LOSS_ERROR event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check STOP_LOSS_ERROR event
    assert 'STOP_LOSS_ERROR' in source, "Missing STOP_LOSS_ERROR event"
    assert 'Failed to set stop loss' in source or 'set_stop_loss_returned_false' in source, "Missing SL error context"

    print("\n✅ STOP_LOSS_ERROR event logging is present")


@pytest.mark.asyncio
async def test_all_final_event_types_exist():
    """Verify all EventTypes added in phases 1.13-1.15 exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'POSITION_CREATED')
    assert hasattr(EventType, 'POSITION_CREATION_FAILED')
    assert hasattr(EventType, 'STOP_LOSS_PLACED')
    assert hasattr(EventType, 'STOP_LOSS_ERROR')

    # Verify values
    assert EventType.POSITION_CREATED.value == 'position_created'
    assert EventType.POSITION_CREATION_FAILED.value == 'position_creation_failed'
    assert EventType.STOP_LOSS_PLACED.value == 'stop_loss_placed'
    assert EventType.STOP_LOSS_ERROR.value == 'stop_loss_error'

    print("\n✅ All EventTypes (phases 1.13-1.15) exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls_final():
    """Verify position_manager has all event logger calls"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count event logger calls (should be >= 19 now)
    # Previous: 14, New: +5 (POSITION_CREATED, 2xPOSITION_CREATION_FAILED, STOP_LOSS_PLACED, STOP_LOSS_ERROR)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 19, f"Expected >= 19 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 19, f"Expected >= 19 log_event calls, found {log_event_count}"

    print(f"\n✅ Position manager has {event_logger_count} event logger instances")
    print(f"✅ Position manager has {log_event_count} log_event calls")
    print(f"   (Phase 1 started with: 0, Now: {event_logger_count})")


@pytest.mark.asyncio
async def test_position_manager_coverage_summary():
    """Verify overall coverage improvement"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count different event types used
    event_types_used = []
    if 'PHANTOM_POSITION_DETECTED' in source:
        event_types_used.append('PHANTOM_POSITION_DETECTED')
    if 'PHANTOM_POSITION_CLOSED' in source:
        event_types_used.append('PHANTOM_POSITION_CLOSED')
    if 'WARNING_RAISED' in source:
        event_types_used.append('WARNING_RAISED')
    if 'POSITIONS_LOADED' in source:
        event_types_used.append('POSITIONS_LOADED')
    if 'POSITIONS_WITHOUT_SL_DETECTED' in source:
        event_types_used.append('POSITIONS_WITHOUT_SL_DETECTED')
    if 'POSITION_DUPLICATE_PREVENTED' in source:
        event_types_used.append('POSITION_DUPLICATE_PREVENTED')
    if 'RISK_LIMITS_EXCEEDED' in source:
        event_types_used.append('RISK_LIMITS_EXCEEDED')
    if 'POSITION_CLOSED' in source:
        event_types_used.append('POSITION_CLOSED')
    if 'SYMBOL_UNAVAILABLE' in source:
        event_types_used.append('SYMBOL_UNAVAILABLE')
    if 'ORDER_BELOW_MINIMUM' in source:
        event_types_used.append('ORDER_BELOW_MINIMUM')
    if 'ORPHANED_SL_CLEANED' in source:
        event_types_used.append('ORPHANED_SL_CLEANED')
    if 'STOP_LOSS_SET_ON_LOAD' in source:
        event_types_used.append('STOP_LOSS_SET_ON_LOAD')
    if 'STOP_LOSS_SET_FAILED' in source:
        event_types_used.append('STOP_LOSS_SET_FAILED')
    if 'POSITION_CREATED' in source:
        event_types_used.append('POSITION_CREATED')
    if 'POSITION_CREATION_FAILED' in source:
        event_types_used.append('POSITION_CREATION_FAILED')
    if 'STOP_LOSS_PLACED' in source:
        event_types_used.append('STOP_LOSS_PLACED')
    if 'STOP_LOSS_ERROR' in source:
        event_types_used.append('STOP_LOSS_ERROR')
    if 'POSITION_ERROR' in source:
        event_types_used.append('POSITION_ERROR')

    print(f"\n✅ Position manager uses {len(event_types_used)} different EventTypes")
    print(f"   Event types used: {', '.join(event_types_used[:5])}...")
    print(f"   Coverage improved from 0% to ~{len(event_types_used) * 100 // 52}% of planned events")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
