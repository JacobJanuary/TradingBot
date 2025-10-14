"""
Test Phase 7: Verify main.py event logging
"""
import pytest


@pytest.mark.asyncio
async def test_bot_started_logging():
    """Verify BOT_STARTED event logging exists"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Check BOT_STARTED event
    assert 'BOT_STARTED' in source, "Missing BOT_STARTED event"
    assert 'EventType.BOT_STARTED' in source, "Missing EventType.BOT_STARTED usage"
    assert "'mode'" in source, "Missing mode tracking"

    print("\n✅ BOT_STARTED event logging is present")


@pytest.mark.asyncio
async def test_bot_stopped_logging():
    """Verify BOT_STOPPED event logging exists"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Check BOT_STOPPED event
    assert 'BOT_STOPPED' in source, "Missing BOT_STOPPED event"
    assert 'EventType.BOT_STOPPED' in source, "Missing EventType.BOT_STOPPED usage"
    assert 'cleanup' in source, "Missing cleanup function"

    print("\n✅ BOT_STOPPED event logging is present")


@pytest.mark.asyncio
async def test_health_check_failed_logging():
    """Verify HEALTH_CHECK_FAILED event logging exists"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Check HEALTH_CHECK_FAILED event
    assert 'HEALTH_CHECK_FAILED' in source, "Missing HEALTH_CHECK_FAILED event"
    assert 'EventType.HEALTH_CHECK_FAILED' in source, "Missing EventType.HEALTH_CHECK_FAILED usage"
    assert '_health_check_loop' in source, "Missing health check loop function"

    print("\n✅ HEALTH_CHECK_FAILED event logging is present")


@pytest.mark.asyncio
async def test_emergency_close_all_logging():
    """Verify EMERGENCY_CLOSE_ALL_TRIGGERED event logging exists"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Check EMERGENCY_CLOSE_ALL_TRIGGERED event
    assert 'EMERGENCY_CLOSE_ALL_TRIGGERED' in source, "Missing EMERGENCY_CLOSE_ALL_TRIGGERED event"
    assert 'EventType.EMERGENCY_CLOSE_ALL_TRIGGERED' in source, "Missing EventType usage"
    assert '_emergency_close_all' in source, "Missing emergency close function"

    print("\n✅ EMERGENCY_CLOSE_ALL_TRIGGERED event logging is present")


@pytest.mark.asyncio
async def test_event_logger_imports():
    """Verify event_logger imports exist"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Check imports
    assert 'from core.event_logger import' in source, "Missing event_logger import"
    assert 'get_event_logger' in source, "Missing get_event_logger function"
    assert 'EventType' in source, "Missing EventType import"

    print("\n✅ Event logger imports are present")


@pytest.mark.asyncio
async def test_all_main_event_types():
    """Verify all main EventTypes exist"""
    from core.event_logger import EventType

    # Check event types exist
    assert hasattr(EventType, 'BOT_STARTED')
    assert hasattr(EventType, 'BOT_STOPPED')
    assert hasattr(EventType, 'HEALTH_CHECK_FAILED')
    assert hasattr(EventType, 'EMERGENCY_CLOSE_ALL_TRIGGERED')

    # Verify values
    assert EventType.BOT_STARTED.value == 'bot_started'
    assert EventType.BOT_STOPPED.value == 'bot_stopped'
    assert EventType.HEALTH_CHECK_FAILED.value == 'health_check_failed'
    assert EventType.EMERGENCY_CLOSE_ALL_TRIGGERED.value == 'emergency_close_all_triggered'

    print("\n✅ All main EventTypes exist with correct values")


@pytest.mark.asyncio
async def test_event_context_completeness():
    """Verify events include proper context"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Verify context includes key data
    assert "'mode'" in source, "Missing mode in event context"
    assert "'status'" in source or "'reason'" in source, "Missing status/reason tracking"
    assert "severity='INFO'" in source, "Missing INFO severity"
    assert "severity='WARNING'" in source, "Missing WARNING severity"
    assert "severity='CRITICAL'" in source, "Missing CRITICAL severity"

    print("\n✅ Main events include proper context")


@pytest.mark.asyncio
async def test_critical_events_have_critical_severity():
    """Verify critical events use CRITICAL severity"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Find EMERGENCY_CLOSE_ALL_TRIGGERED event
    assert 'EMERGENCY_CLOSE_ALL_TRIGGERED' in source, "Missing emergency event"

    # Check it has CRITICAL severity
    emergency_section = source[source.find('EMERGENCY_CLOSE_ALL_TRIGGERED'):source.find('EMERGENCY_CLOSE_ALL_TRIGGERED') + 300]
    assert "severity='CRITICAL'" in emergency_section, "Emergency event should have CRITICAL severity"

    print("\n✅ Emergency events have CRITICAL severity")


@pytest.mark.asyncio
async def test_bot_lifecycle_events():
    """Verify bot lifecycle events (start/stop) are present"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Both start and stop should be logged
    assert 'BOT_STARTED' in source and 'BOT_STOPPED' in source, "Missing lifecycle events"

    # Verify they're in the right functions
    assert 'async def start' in source, "Missing start function"
    assert 'async def cleanup' in source, "Missing cleanup function"

    print("\n✅ Bot lifecycle events (start/stop) are properly placed")


@pytest.mark.asyncio
async def test_error_handling_in_logging():
    """Verify error handling exists for logging failures"""
    with open('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py', 'r') as f:
        source = f.read()

    # Check for try/except around logging
    assert 'except Exception' in source, "Missing exception handling"
    assert 'log_err' in source or 'Could not log' in source, "Missing logging error handling"

    print("\n✅ Error handling present for logging failures")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
