"""
Test Phase 6: Verify stop loss manager event logging in stop_loss_manager.py
"""
import pytest


@pytest.mark.asyncio
async def test_stop_loss_placed_bybit_logging():
    """Verify STOP_LOSS_PLACED event logging for Bybit"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm.StopLossManager._set_bybit_stop_loss)

    # Check STOP_LOSS_PLACED event
    assert 'STOP_LOSS_PLACED' in source, "Missing STOP_LOSS_PLACED event"
    assert 'method' in source and 'position_attached' in source, "Missing method tracking"
    assert 'trigger_by' in source, "Missing trigger_by tracking"

    print("\n✅ STOP_LOSS_PLACED (Bybit) event logging is present")


@pytest.mark.asyncio
async def test_stop_loss_placed_generic_logging():
    """Verify STOP_LOSS_PLACED event logging for generic exchanges"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm.StopLossManager._set_generic_stop_loss)

    # Check STOP_LOSS_PLACED event
    assert 'STOP_LOSS_PLACED' in source, "Missing STOP_LOSS_PLACED event"
    assert 'order_id' in source, "Missing order_id tracking"
    assert 'stop_market' in source, "Missing method tracking"

    print("\n✅ STOP_LOSS_PLACED (generic) event logging is present")


@pytest.mark.asyncio
async def test_stop_loss_error_bybit_logging():
    """Verify STOP_LOSS_ERROR event logging for Bybit"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm.StopLossManager._set_bybit_stop_loss)

    # Check STOP_LOSS_ERROR event
    assert 'STOP_LOSS_ERROR' in source, "Missing STOP_LOSS_ERROR event"
    assert 'ret_code' in source, "Missing ret_code tracking"
    assert "severity='ERROR'" in source, "Missing ERROR severity"

    print("\n✅ STOP_LOSS_ERROR (Bybit) event logging is present")


@pytest.mark.asyncio
async def test_stop_loss_error_generic_logging():
    """Verify STOP_LOSS_ERROR event logging for generic exchanges"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm.StopLossManager._set_generic_stop_loss)

    # Check STOP_LOSS_ERROR event
    assert 'STOP_LOSS_ERROR' in source, "Missing STOP_LOSS_ERROR event"
    assert 'attempts' in source, "Missing attempts tracking"
    assert "severity='ERROR'" in source, "Missing ERROR severity"

    print("\n✅ STOP_LOSS_ERROR (generic) event logging is present")


@pytest.mark.asyncio
async def test_event_logger_import():
    """Verify event_logger import exists"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm)

    # Check import
    assert 'from core.event_logger import get_event_logger, EventType' in source, \
        "Missing event_logger import"

    print("\n✅ Event logger import is present")


@pytest.mark.asyncio
async def test_all_stop_loss_event_types():
    """Verify all stop loss EventTypes exist"""
    from core.event_logger import EventType

    # Check event types exist
    assert hasattr(EventType, 'STOP_LOSS_PLACED')
    assert hasattr(EventType, 'STOP_LOSS_ERROR')

    # Verify values
    assert EventType.STOP_LOSS_PLACED.value == 'stop_loss_placed'
    assert EventType.STOP_LOSS_ERROR.value == 'stop_loss_error'

    print("\n✅ All stop loss EventTypes exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls():
    """Verify stop_loss_manager.py has event logger calls"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm.StopLossManager)

    # Count event logger calls (should be >= 5: 2 PLACED + 3 ERROR)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 5, f"Expected >= 5 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 5, f"Expected >= 5 log_event calls, found {log_event_count}"

    print(f"\n✅ Stop loss manager has {event_logger_count} event logger instances")
    print(f"✅ Stop loss manager has {log_event_count} log_event calls")


@pytest.mark.asyncio
async def test_event_context_completeness():
    """Verify events include proper context"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm.StopLossManager)

    # Verify context includes key data
    assert "'symbol'" in source, "Missing symbol in event context"
    assert "'exchange'" in source, "Missing exchange in event context"
    assert "'stop_price'" in source, "Missing stop_price in event context"
    assert "severity='INFO'" in source, "Missing INFO severity"
    assert "severity='ERROR'" in source, "Missing ERROR severity"

    print("\n✅ Stop loss manager events include proper context")


@pytest.mark.asyncio
async def test_bybit_specific_logging():
    """Verify Bybit-specific SL logging includes position_attached method"""
    import inspect
    import core.stop_loss_manager as slm

    source = inspect.getsource(slm.StopLossManager._set_bybit_stop_loss)

    # Verify Bybit-specific fields
    assert "'method': 'position_attached'" in source, "Missing position_attached method"
    assert "'trigger_by': 'LastPrice'" in source, "Missing trigger_by field"

    print("\n✅ Bybit-specific SL logging includes correct fields")


@pytest.mark.asyncio
async def test_error_logging_coverage():
    """Verify error logging covers all error paths"""
    import inspect
    import core.stop_loss_manager as slm

    bybit_source = inspect.getsource(slm.StopLossManager._set_bybit_stop_loss)
    generic_source = inspect.getsource(slm.StopLossManager._set_generic_stop_loss)

    # Verify error logging in multiple paths
    assert bybit_source.count('STOP_LOSS_ERROR') >= 2, "Missing error logging in Bybit paths"
    assert generic_source.count('STOP_LOSS_ERROR') >= 3, "Missing error logging in generic paths"

    print("\n✅ Error logging covers all error paths")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
