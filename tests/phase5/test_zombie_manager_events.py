"""
Test Phase 5: Verify zombie manager event logging in zombie_manager.py
"""
import pytest


@pytest.mark.asyncio
async def test_zombie_orders_detected_logging():
    """Verify ZOMBIE_ORDERS_DETECTED event logging code exists"""
    import inspect
    import core.zombie_manager as zm

    source = inspect.getsource(zm.EnhancedZombieOrderManager)

    # Check ZOMBIE_ORDERS_DETECTED event
    assert 'ZOMBIE_ORDERS_DETECTED' in source, "Missing ZOMBIE_ORDERS_DETECTED event"
    assert 'detect_zombie_orders' in source, "Missing detect_zombie_orders function"
    assert 'zombie_count' in source, "Missing zombie_count context"

    print("\n✅ ZOMBIE_ORDERS_DETECTED event logging is present")


@pytest.mark.asyncio
async def test_zombie_order_cancelled_logging():
    """Verify ZOMBIE_ORDER_CANCELLED event logging code exists"""
    import inspect
    import core.zombie_manager as zm

    source = inspect.getsource(zm.EnhancedZombieOrderManager)

    # Check ZOMBIE_ORDER_CANCELLED event
    assert 'ZOMBIE_ORDER_CANCELLED' in source, "Missing ZOMBIE_ORDER_CANCELLED event"
    assert '_cancel_order_safe' in source, "Missing cancel_order_safe function"
    assert 'order_id' in source, "Missing order_id tracking"

    print("\n✅ ZOMBIE_ORDER_CANCELLED event logging is present")


@pytest.mark.asyncio
async def test_zombie_cleanup_completed_logging():
    """Verify ZOMBIE_CLEANUP_COMPLETED event logging code exists"""
    import inspect
    import core.zombie_manager as zm

    source = inspect.getsource(zm.EnhancedZombieOrderManager)

    # Check ZOMBIE_CLEANUP_COMPLETED event
    assert 'ZOMBIE_CLEANUP_COMPLETED' in source, "Missing ZOMBIE_CLEANUP_COMPLETED event"
    assert 'cleanup_zombie_orders' in source, "Missing cleanup_zombie_orders function"
    assert 'Cleanup complete' in source, "Missing cleanup log message"

    print("\n✅ ZOMBIE_CLEANUP_COMPLETED event logging is present")


@pytest.mark.asyncio
async def test_zombie_alert_triggered_logging():
    """Verify ZOMBIE_ALERT_TRIGGERED event logging code exists"""
    import inspect
    import core.zombie_manager as zm

    source = inspect.getsource(zm.ZombieOrderMonitor)

    # Check ZOMBIE_ALERT_TRIGGERED event
    assert 'ZOMBIE_ALERT_TRIGGERED' in source, "Missing ZOMBIE_ALERT_TRIGGERED event"
    assert '_send_alert' in source, "Missing send_alert function"
    assert 'alert_threshold' in source, "Missing alert_threshold tracking"

    print("\n✅ ZOMBIE_ALERT_TRIGGERED event logging is present")


@pytest.mark.asyncio
async def test_aggressive_cleanup_triggered_logging():
    """Verify AGGRESSIVE_CLEANUP_TRIGGERED event logging code exists"""
    import inspect
    import core.zombie_manager as zm

    source = inspect.getsource(zm.EnhancedZombieOrderManager)

    # Check AGGRESSIVE_CLEANUP_TRIGGERED event
    assert 'AGGRESSIVE_CLEANUP_TRIGGERED' in source, "Missing AGGRESSIVE_CLEANUP_TRIGGERED event"
    assert 'Aggressive cleanup' in source, "Missing aggressive cleanup message"
    assert 'symbols_for_aggressive' in source, "Missing symbols tracking"

    print("\n✅ AGGRESSIVE_CLEANUP_TRIGGERED event logging is present")


@pytest.mark.asyncio
async def test_tpsl_orders_cleared_logging():
    """Verify TPSL_ORDERS_CLEARED event logging code exists"""
    import inspect
    import core.zombie_manager as zm

    source = inspect.getsource(zm.EnhancedZombieOrderManager)

    # Check TPSL_ORDERS_CLEARED event
    assert 'TPSL_ORDERS_CLEARED' in source, "Missing TPSL_ORDERS_CLEARED event"
    assert '_clear_tpsl_orders' in source, "Missing clear_tpsl_orders function"
    assert 'Cleared TP/SL' in source, "Missing TP/SL clear message"

    print("\n✅ TPSL_ORDERS_CLEARED event logging is present")


@pytest.mark.asyncio
async def test_event_logger_import():
    """Verify event_logger import exists"""
    import inspect
    import core.zombie_manager as zm

    source = inspect.getsource(zm)

    # Check import
    assert 'from core.event_logger import get_event_logger, EventType' in source, \
        "Missing event_logger import"

    print("\n✅ Event logger import is present")


@pytest.mark.asyncio
async def test_all_zombie_event_types():
    """Verify all zombie manager EventTypes exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'ZOMBIE_ORDERS_DETECTED')
    assert hasattr(EventType, 'ZOMBIE_ORDER_CANCELLED')
    assert hasattr(EventType, 'ZOMBIE_CLEANUP_COMPLETED')
    assert hasattr(EventType, 'ZOMBIE_ALERT_TRIGGERED')
    assert hasattr(EventType, 'AGGRESSIVE_CLEANUP_TRIGGERED')
    assert hasattr(EventType, 'TPSL_ORDERS_CLEARED')

    # Verify values
    assert EventType.ZOMBIE_ORDERS_DETECTED.value == 'zombie_orders_detected'
    assert EventType.ZOMBIE_ORDER_CANCELLED.value == 'zombie_order_cancelled'
    assert EventType.ZOMBIE_CLEANUP_COMPLETED.value == 'zombie_cleanup_completed'
    assert EventType.ZOMBIE_ALERT_TRIGGERED.value == 'zombie_alert_triggered'
    assert EventType.AGGRESSIVE_CLEANUP_TRIGGERED.value == 'aggressive_cleanup_triggered'
    assert EventType.TPSL_ORDERS_CLEARED.value == 'tpsl_orders_cleared'

    print("\n✅ All zombie manager EventTypes exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls():
    """Verify zombie_manager.py has event logger calls"""
    import inspect
    import core.zombie_manager as zm

    # Get both classes
    manager_source = inspect.getsource(zm.EnhancedZombieOrderManager)
    monitor_source = inspect.getsource(zm.ZombieOrderMonitor)
    combined_source = manager_source + monitor_source

    # Count event logger calls (should be >= 6)
    event_logger_count = combined_source.count('event_logger = get_event_logger()')
    log_event_count = combined_source.count('await event_logger.log_event(')

    assert event_logger_count >= 6, f"Expected >= 6 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 6, f"Expected >= 6 log_event calls, found {log_event_count}"

    print(f"\n✅ Zombie manager has {event_logger_count} event logger instances")
    print(f"✅ Zombie manager has {log_event_count} log_event calls")


@pytest.mark.asyncio
async def test_event_context_completeness():
    """Verify events include proper context"""
    import inspect
    import core.zombie_manager as zm

    manager_source = inspect.getsource(zm.EnhancedZombieOrderManager)
    monitor_source = inspect.getsource(zm.ZombieOrderMonitor)
    combined_source = manager_source + monitor_source

    # Verify context includes key data
    assert "'exchange'" in combined_source, "Missing exchange in event context"
    assert "'zombie_count'" in combined_source, "Missing zombie_count in event context"
    assert "'order_id'" in combined_source, "Missing order_id in event context"
    assert "severity='INFO'" in combined_source, "Missing INFO severity"
    assert "severity='WARNING'" in combined_source, "Missing WARNING severity"
    assert "severity='CRITICAL'" in combined_source, "Missing CRITICAL severity"

    print("\n✅ Zombie manager events include proper context")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
