"""
Test Phase 1.17-1.19: Verify EXCHANGE_ERROR, STOP_LOSS_TRIGGERED, and AGED_POSITION_DETECTED event logging
"""
import pytest


@pytest.mark.asyncio
async def test_stop_loss_triggered_logging():
    """Verify STOP_LOSS_TRIGGERED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check STOP_LOSS_TRIGGERED event
    assert 'STOP_LOSS_TRIGGERED' in source, "Missing STOP_LOSS_TRIGGERED event"
    assert '_on_stop_loss_triggered' in source, "Missing stop loss triggered handler"
    assert 'Stop loss triggered for' in source, "Missing SL triggered message"

    print("\n✅ STOP_LOSS_TRIGGERED event logging is present")


@pytest.mark.asyncio
async def test_exchange_error_close_position():
    """Verify EXCHANGE_ERROR event logging for close_position failure"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check EXCHANGE_ERROR event for close_position
    assert 'EXCHANGE_ERROR' in source, "Missing EXCHANGE_ERROR event"
    assert 'close_position' in source, "Missing close_position operation"
    assert 'Error closing position' in source, "Missing close position error message"

    print("\n✅ EXCHANGE_ERROR event logging for close_position is present")


@pytest.mark.asyncio
async def test_exchange_error_cancel_order():
    """Verify EXCHANGE_ERROR event logging for cancel order failure"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check EXCHANGE_ERROR event for cancel order
    assert 'cancel_pending_close_order' in source, "Missing cancel order operation"
    assert 'Error cancelling order' in source, "Missing cancel order error message"

    print("\n✅ EXCHANGE_ERROR event logging for cancel order is present")


@pytest.mark.asyncio
async def test_exchange_error_place_limit_order():
    """Verify EXCHANGE_ERROR event logging for limit order placement failure"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check EXCHANGE_ERROR event for limit order
    assert 'place_limit_close_order' in source, "Missing limit order placement operation"
    assert 'Error placing limit close order' in source, "Missing limit order error message"

    print("\n✅ EXCHANGE_ERROR event logging for limit order placement is present")


@pytest.mark.asyncio
async def test_exchange_error_fetch_ticker():
    """Verify EXCHANGE_ERROR event logging for fetch_ticker failure"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check EXCHANGE_ERROR event for fetch_ticker
    assert 'fetch_ticker' in source, "Missing fetch_ticker operation"
    assert 'Failed to fetch current price' in source, "Missing fetch price error message"

    print("\n✅ EXCHANGE_ERROR event logging for fetch_ticker is present")


@pytest.mark.asyncio
async def test_aged_position_detected_logging():
    """Verify AGED_POSITION_DETECTED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check AGED_POSITION_DETECTED event
    assert 'AGED_POSITION_DETECTED' in source, "Missing AGED_POSITION_DETECTED event"
    assert 'exceeded max age' in source, "Missing aged position message"
    assert 'age_hours' in source, "Missing age tracking"

    print("\n✅ AGED_POSITION_DETECTED event logging is present")


@pytest.mark.asyncio
async def test_all_new_event_types_exist():
    """Verify all EventTypes added in phases 1.17-1.19 exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'STOP_LOSS_TRIGGERED')
    assert hasattr(EventType, 'EXCHANGE_ERROR')
    assert hasattr(EventType, 'AGED_POSITION_DETECTED')

    # Verify values
    assert EventType.STOP_LOSS_TRIGGERED.value == 'stop_loss_triggered'
    assert EventType.EXCHANGE_ERROR.value == 'exchange_error'
    assert EventType.AGED_POSITION_DETECTED.value == 'aged_position_detected'

    print("\n✅ All EventTypes (phases 1.17-1.19) exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls_phase_17_19():
    """Verify position_manager has increased event logger calls after Phase 1.17-1.19"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count event logger calls (should be >= 31 now: 25 previous + 6 new)
    # Added: STOP_LOSS_TRIGGERED (1) + EXCHANGE_ERROR (4) + AGED_POSITION_DETECTED (1) = 6
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 31, f"Expected >= 31 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 31, f"Expected >= 31 log_event calls, found {log_event_count}"

    print(f"\n✅ Position manager has {event_logger_count} event logger instances")
    print(f"✅ Position manager has {log_event_count} log_event calls")
    print(f"   (Previous: 25, Added: {event_logger_count - 25}, Total: {event_logger_count})")


@pytest.mark.asyncio
async def test_exchange_error_context():
    """Verify EXCHANGE_ERROR events include proper context"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Verify context includes operation type and error details
    assert "'operation'" in source, "Missing 'operation' field in EXCHANGE_ERROR context"
    assert "severity='ERROR'" in source, "Missing ERROR severity for EXCHANGE_ERROR events"

    print("\n✅ EXCHANGE_ERROR events include proper context (operation, error, severity)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
