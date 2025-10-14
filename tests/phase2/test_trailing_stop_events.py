"""
Test Phase 2: Verify trailing stop event logging in trailing_stop.py
"""
import pytest


@pytest.mark.asyncio
async def test_trailing_stop_created_logging():
    """Verify TRAILING_STOP_CREATED event logging code exists"""
    import inspect
    import protection.trailing_stop as ts

    source = inspect.getsource(ts.TrailingStopManager)

    # Check TRAILING_STOP_CREATED event
    assert 'TRAILING_STOP_CREATED' in source, "Missing TRAILING_STOP_CREATED event"
    assert 'create_trailing_stop' in source, "Missing create_trailing_stop function"
    assert 'activation_percent' in source, "Missing activation_percent context"

    print("\n✅ TRAILING_STOP_CREATED event logging is present")


@pytest.mark.asyncio
async def test_trailing_stop_activated_logging():
    """Verify TRAILING_STOP_ACTIVATED event logging code exists"""
    import inspect
    import protection.trailing_stop as ts

    source = inspect.getsource(ts.TrailingStopManager)

    # Check TRAILING_STOP_ACTIVATED event
    assert 'TRAILING_STOP_ACTIVATED' in source, "Missing TRAILING_STOP_ACTIVATED event"
    assert '_activate_trailing_stop' in source, "Missing activation function"
    assert 'Trailing stop ACTIVATED' in source, "Missing activation log message"

    print("\n✅ TRAILING_STOP_ACTIVATED event logging is present")


@pytest.mark.asyncio
async def test_trailing_stop_updated_logging():
    """Verify TRAILING_STOP_UPDATED event logging code exists"""
    import inspect
    import protection.trailing_stop as ts

    source = inspect.getsource(ts.TrailingStopManager)

    # Check TRAILING_STOP_UPDATED event
    assert 'TRAILING_STOP_UPDATED' in source, "Missing TRAILING_STOP_UPDATED event"
    assert '_update_trailing_stop' in source, "Missing update function"
    assert 'improvement_percent' in source, "Missing improvement tracking"

    print("\n✅ TRAILING_STOP_UPDATED event logging is present")


@pytest.mark.asyncio
async def test_trailing_stop_removed_logging():
    """Verify TRAILING_STOP_REMOVED event logging code exists"""
    import inspect
    import protection.trailing_stop as ts

    source = inspect.getsource(ts.TrailingStopManager)

    # Check TRAILING_STOP_REMOVED event
    assert 'TRAILING_STOP_REMOVED' in source, "Missing TRAILING_STOP_REMOVED event"
    assert 'on_position_closed' in source, "Missing position closed handler"
    assert 'trailing stop removed' in source, "Missing removal log message"

    print("\n✅ TRAILING_STOP_REMOVED event logging is present")


@pytest.mark.asyncio
async def test_event_logger_import():
    """Verify event_logger import exists"""
    import inspect
    import protection.trailing_stop as ts

    source = inspect.getsource(ts)

    # Check import
    assert 'from core.event_logger import get_event_logger, EventType' in source, \
        "Missing event_logger import"

    print("\n✅ Event logger import is present")


@pytest.mark.asyncio
async def test_all_trailing_stop_event_types():
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
async def test_total_event_logger_calls():
    """Verify trailing_stop.py has event logger calls"""
    import inspect
    import protection.trailing_stop as ts

    source = inspect.getsource(ts.TrailingStopManager)

    # Count event logger calls (should be >= 4: created, activated, updated, removed)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 4, f"Expected >= 4 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 4, f"Expected >= 4 log_event calls, found {log_event_count}"

    print(f"\n✅ Trailing stop manager has {event_logger_count} event logger instances")
    print(f"✅ Trailing stop manager has {log_event_count} log_event calls")


@pytest.mark.asyncio
async def test_event_context_completeness():
    """Verify events include proper context"""
    import inspect
    import protection.trailing_stop as ts

    source = inspect.getsource(ts.TrailingStopManager)

    # Verify context includes key data
    assert "'symbol'" in source, "Missing symbol in event context"
    assert "'stop_price'" in source or "'new_stop'" in source, "Missing stop price tracking"
    assert "severity='INFO'" in source, "Missing INFO severity"

    print("\n✅ Trailing stop events include proper context")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
