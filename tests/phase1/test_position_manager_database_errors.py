"""
Test Phase 1.16: Verify DATABASE_ERROR event logging in position_manager.py
"""
import pytest


@pytest.mark.asyncio
async def test_database_error_logging_stop_loss():
    """Verify DATABASE_ERROR event logging for stop loss update"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check DATABASE_ERROR event for stop loss update
    assert 'DATABASE_ERROR' in source, "Missing DATABASE_ERROR event"
    assert 'update_position_stop_loss' in source, "Missing stop loss update operation"
    assert 'Failed to update stop loss in database' in source, "Missing SL update error message"

    print("\n✅ DATABASE_ERROR event logging for stop loss update is present")


@pytest.mark.asyncio
async def test_database_error_logging_trailing_stop():
    """Verify DATABASE_ERROR event logging for trailing stop updates"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check DATABASE_ERROR events for trailing stop operations
    assert 'update_position_trailing_stop' in source or 'update_trailing_activation' in source, "Missing TS update operation"
    assert 'Failed to update trailing' in source, "Missing TS update error message"

    print("\n✅ DATABASE_ERROR event logging for trailing stop updates is present")


@pytest.mark.asyncio
async def test_database_error_logging_websocket():
    """Verify DATABASE_ERROR event logging for WebSocket updates"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check DATABASE_ERROR event for WebSocket update
    assert 'update_position_from_websocket' in source, "Missing WebSocket update operation"
    assert 'Failed to update position from websocket in database' in source, "Missing WS update error message"

    print("\n✅ DATABASE_ERROR event logging for WebSocket updates is present")


@pytest.mark.asyncio
async def test_database_error_logging_pending_close():
    """Verify DATABASE_ERROR event logging for pending close order"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check DATABASE_ERROR event for pending close order
    assert 'update_pending_close_order' in source, "Missing pending close order operation"
    assert 'Failed to update pending close order in database' in source, "Missing pending close error message"

    print("\n✅ DATABASE_ERROR event logging for pending close order is present")


@pytest.mark.asyncio
async def test_database_error_event_type_exists():
    """Verify DATABASE_ERROR EventType exists"""
    from core.event_logger import EventType

    # Check that DATABASE_ERROR exists
    assert hasattr(EventType, 'DATABASE_ERROR')
    assert EventType.DATABASE_ERROR.value == 'database_error'

    print("\n✅ DATABASE_ERROR EventType exists with correct value")


@pytest.mark.asyncio
async def test_total_event_logger_calls_phase_16():
    """Verify position_manager has increased event logger calls after Phase 1.16"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count event logger calls (should be >= 24 now: 19 previous + 5 new DATABASE_ERROR)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 24, f"Expected >= 24 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 24, f"Expected >= 24 log_event calls, found {log_event_count}"

    print(f"\n✅ Position manager has {event_logger_count} event logger instances")
    print(f"✅ Position manager has {log_event_count} log_event calls")
    print(f"   (Previous: 19, Added: {event_logger_count - 19}, Total: {event_logger_count})")


@pytest.mark.asyncio
async def test_database_error_context():
    """Verify DATABASE_ERROR events include proper context"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Verify context includes operation type and error details
    assert "'operation'" in source, "Missing 'operation' field in DATABASE_ERROR context"
    assert "'error': str(db_error)" in source, "Missing 'error' field in DATABASE_ERROR context"
    assert "severity='ERROR'" in source, "Missing ERROR severity for DATABASE_ERROR events"

    print("\n✅ DATABASE_ERROR events include proper context (operation, error, severity)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
