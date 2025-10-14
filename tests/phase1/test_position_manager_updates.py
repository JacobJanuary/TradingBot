"""
Test Phase 1.20: Verify position update and sync event logging in position_manager.py
"""
import pytest


@pytest.mark.asyncio
async def test_position_updated_logging():
    """Verify POSITION_UPDATED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITION_UPDATED event
    assert 'POSITION_UPDATED' in source, "Missing POSITION_UPDATED event"
    assert '_on_position_update' in source, "Missing position update handler"
    assert 'old_price' in source and 'new_price' in source, "Missing price tracking"

    print("\n✅ POSITION_UPDATED event logging is present")


@pytest.mark.asyncio
async def test_order_filled_logging():
    """Verify ORDER_FILLED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check ORDER_FILLED event
    assert 'ORDER_FILLED' in source, "Missing ORDER_FILLED event"
    assert '_on_order_filled' in source, "Missing order filled handler"

    print("\n✅ ORDER_FILLED event logging is present")


@pytest.mark.asyncio
async def test_position_not_found_logging():
    """Verify POSITION_NOT_FOUND_ON_EXCHANGE event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITION_NOT_FOUND_ON_EXCHANGE event
    assert 'POSITION_NOT_FOUND_ON_EXCHANGE' in source, "Missing POSITION_NOT_FOUND_ON_EXCHANGE event"
    assert 'verify_position_exists' in source, "Missing verify position exists function"
    assert 'Position' in source and 'not found on' in source, "Missing not found message"

    print("\n✅ POSITION_NOT_FOUND_ON_EXCHANGE event logging is present")


@pytest.mark.asyncio
async def test_sync_started_logging():
    """Verify SYNC_STARTED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check SYNC_STARTED event
    assert 'SYNC_STARTED' in source, "Missing SYNC_STARTED event"
    assert 'synchronize_with_exchanges' in source, "Missing sync function"
    assert 'Synchronizing positions with exchanges' in source, "Missing sync message"

    print("\n✅ SYNC_STARTED event logging is present")


@pytest.mark.asyncio
async def test_sync_completed_logging():
    """Verify SYNC_COMPLETED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check SYNC_COMPLETED event
    assert 'SYNC_COMPLETED' in source, "Missing SYNC_COMPLETED event"
    assert 'phantom_closed' in source or 'missing_added' in source, "Missing sync results tracking"

    print("\n✅ SYNC_COMPLETED event logging is present")


@pytest.mark.asyncio
async def test_all_new_event_types_exist():
    """Verify all EventTypes added in phase 1.20 exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'POSITION_UPDATED')
    assert hasattr(EventType, 'ORDER_FILLED')
    assert hasattr(EventType, 'POSITION_NOT_FOUND_ON_EXCHANGE')
    assert hasattr(EventType, 'SYNC_STARTED')
    assert hasattr(EventType, 'SYNC_COMPLETED')

    # Verify values
    assert EventType.POSITION_UPDATED.value == 'position_updated'
    assert EventType.ORDER_FILLED.value == 'order_filled'
    assert EventType.POSITION_NOT_FOUND_ON_EXCHANGE.value == 'position_not_found_on_exchange'
    assert EventType.SYNC_STARTED.value == 'sync_started'
    assert EventType.SYNC_COMPLETED.value == 'sync_completed'

    print("\n✅ All EventTypes (phase 1.20) exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls_phase_20():
    """Verify position_manager has increased event logger calls after Phase 1.20"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count event logger calls (should be >= 36 now: 31 previous + 5 new)
    # Added: POSITION_UPDATED (1) + ORDER_FILLED (1) + POSITION_NOT_FOUND (1) + SYNC_STARTED (1) + SYNC_COMPLETED (1) = 5
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 36, f"Expected >= 36 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 36, f"Expected >= 36 log_event calls, found {log_event_count}"

    print(f"\n✅ Position manager has {event_logger_count} event logger instances")
    print(f"✅ Position manager has {log_event_count} log_event calls")
    print(f"   (Previous: 31, Added: {event_logger_count - 31}, Total: {event_logger_count})")


@pytest.mark.asyncio
async def test_position_update_context():
    """Verify position update events include proper context"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Verify context includes price changes and PnL
    assert "'unrealized_pnl'" in source, "Missing unrealized_pnl in update context"
    assert "'source': 'websocket'" in source, "Missing source tracking in update"

    print("\n✅ Position update events include proper context (prices, PnL, source)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
