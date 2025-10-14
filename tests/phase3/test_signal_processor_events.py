"""
Test Phase 3: Verify signal processor event logging in signal_processor_websocket.py
"""
import pytest


@pytest.mark.asyncio
async def test_signal_executed_logging():
    """Verify SIGNAL_EXECUTED event logging code exists"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Check SIGNAL_EXECUTED event
    assert 'SIGNAL_EXECUTED' in source, "Missing SIGNAL_EXECUTED event"
    assert 'Signal' in source and 'executed successfully' in source, "Missing execution success message"
    assert 'score_week' in source, "Missing score tracking"

    print("\n✅ SIGNAL_EXECUTED event logging is present")


@pytest.mark.asyncio
async def test_signal_execution_failed_logging():
    """Verify SIGNAL_EXECUTION_FAILED event logging code exists"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Check SIGNAL_EXECUTION_FAILED event
    assert 'SIGNAL_EXECUTION_FAILED' in source, "Missing SIGNAL_EXECUTION_FAILED event"
    assert 'position_manager_returned_none' in source, "Missing failure reason tracking"

    print("\n✅ SIGNAL_EXECUTION_FAILED event logging is present")


@pytest.mark.asyncio
async def test_signal_filtered_logging():
    """Verify SIGNAL_FILTERED event logging code exists"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Check SIGNAL_FILTERED event
    assert 'SIGNAL_FILTERED' in source, "Missing SIGNAL_FILTERED event"
    assert 'symbol_filter' in source or 'is_symbol_allowed' in source, "Missing filter check"
    assert 'filter_reason' in source, "Missing filter reason tracking"

    print("\n✅ SIGNAL_FILTERED event logging is present")


@pytest.mark.asyncio
async def test_signal_validation_failed_logging():
    """Verify SIGNAL_VALIDATION_FAILED event logging code exists"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Check SIGNAL_VALIDATION_FAILED event
    assert 'SIGNAL_VALIDATION_FAILED' in source, "Missing SIGNAL_VALIDATION_FAILED event"
    assert 'validate_signal' in source, "Missing validation function call"

    print("\n✅ SIGNAL_VALIDATION_FAILED event logging is present")


@pytest.mark.asyncio
async def test_wave_detected_logging():
    """Verify WAVE_DETECTED event logging code exists"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Check WAVE_DETECTED event
    assert 'WAVE_DETECTED' in source, "Missing WAVE_DETECTED event"
    assert 'Wave detected' in source, "Missing wave detection message"
    assert 'wave_timestamp' in source, "Missing wave timestamp tracking"

    print("\n✅ WAVE_DETECTED event logging is present")


@pytest.mark.asyncio
async def test_wave_completed_logging():
    """Verify WAVE_COMPLETED event logging code exists"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Check WAVE_COMPLETED event
    assert 'WAVE_COMPLETED' in source, "Missing WAVE_COMPLETED event"
    assert 'Wave' in source and 'complete' in source, "Missing wave completion message"
    assert 'positions_opened' in source, "Missing position count tracking"

    print("\n✅ WAVE_COMPLETED event logging is present")


@pytest.mark.asyncio
async def test_event_logger_import():
    """Verify event_logger import exists"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp)

    # Check import
    assert 'from core.event_logger import get_event_logger, EventType' in source, \
        "Missing event_logger import"

    print("\n✅ Event logger import is present")


@pytest.mark.asyncio
async def test_all_signal_event_types():
    """Verify all signal processor EventTypes exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'SIGNAL_EXECUTED')
    assert hasattr(EventType, 'SIGNAL_EXECUTION_FAILED')
    assert hasattr(EventType, 'SIGNAL_FILTERED')
    assert hasattr(EventType, 'SIGNAL_VALIDATION_FAILED')
    assert hasattr(EventType, 'WAVE_DETECTED')
    assert hasattr(EventType, 'WAVE_COMPLETED')

    # Verify values
    assert EventType.SIGNAL_EXECUTED.value == 'signal_executed'
    assert EventType.SIGNAL_EXECUTION_FAILED.value == 'signal_execution_failed'
    assert EventType.SIGNAL_FILTERED.value == 'signal_filtered'
    assert EventType.SIGNAL_VALIDATION_FAILED.value == 'signal_validation_failed'
    assert EventType.WAVE_DETECTED.value == 'wave_detected'
    assert EventType.WAVE_COMPLETED.value == 'wave_completed'

    print("\n✅ All signal processor EventTypes exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls():
    """Verify signal_processor_websocket.py has event logger calls"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Count event logger calls (should be >= 6)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 6, f"Expected >= 6 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 6, f"Expected >= 6 log_event calls, found {log_event_count}"

    print(f"\n✅ Signal processor has {event_logger_count} event logger instances")
    print(f"✅ Signal processor has {log_event_count} log_event calls")


@pytest.mark.asyncio
async def test_event_context_completeness():
    """Verify events include proper context"""
    import inspect
    import core.signal_processor_websocket as sp

    source = inspect.getsource(sp.WebSocketSignalProcessor)

    # Verify context includes key data
    assert "'signal_id'" in source, "Missing signal_id in event context"
    assert "'symbol'" in source, "Missing symbol in event context"
    assert "'wave_timestamp'" in source, "Missing wave_timestamp in event context"

    print("\n✅ Signal processor events include proper context")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
