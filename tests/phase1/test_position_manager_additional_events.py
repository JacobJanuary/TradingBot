"""
Test Phase 1.8-1.12: Verify additional position_manager.py event logging
"""
import pytest


@pytest.mark.asyncio
async def test_symbol_unavailable_logging():
    """Verify SYMBOL_UNAVAILABLE event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check SYMBOL_UNAVAILABLE event
    assert 'SYMBOL_UNAVAILABLE' in source, "Missing SYMBOL_UNAVAILABLE event"
    assert 'Symbol' in source and 'unavailable' in source, "Missing symbol unavailable context"

    print("\n✅ SYMBOL_UNAVAILABLE event logging is present")


@pytest.mark.asyncio
async def test_order_below_minimum_logging():
    """Verify ORDER_BELOW_MINIMUM event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check ORDER_BELOW_MINIMUM event
    assert 'ORDER_BELOW_MINIMUM' in source, "Missing ORDER_BELOW_MINIMUM event"
    assert 'minimum limit' in source or 'minimum' in source, "Missing minimum order context"

    print("\n✅ ORDER_BELOW_MINIMUM event logging is present")


@pytest.mark.asyncio
async def test_orphaned_sl_cleaned_logging():
    """Verify ORPHANED_SL_CLEANED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check ORPHANED_SL_CLEANED event
    assert 'ORPHANED_SL_CLEANED' in source, "Missing ORPHANED_SL_CLEANED event"
    assert 'Cleaning up SL order' in source, "Missing SL cleanup context"

    print("\n✅ ORPHANED_SL_CLEANED event logging is present")


@pytest.mark.asyncio
async def test_stop_loss_set_on_load_logging():
    """Verify STOP_LOSS_SET_ON_LOAD event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check STOP_LOSS_SET_ON_LOAD event
    assert 'STOP_LOSS_SET_ON_LOAD' in source, "Missing STOP_LOSS_SET_ON_LOAD event"
    assert 'Stop loss set for' in source, "Missing SL set context"

    print("\n✅ STOP_LOSS_SET_ON_LOAD event logging is present")


@pytest.mark.asyncio
async def test_stop_loss_set_failed_logging():
    """Verify STOP_LOSS_SET_FAILED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check STOP_LOSS_SET_FAILED event
    assert 'STOP_LOSS_SET_FAILED' in source, "Missing STOP_LOSS_SET_FAILED event"
    assert 'Failed to set stop loss' in source, "Missing SL failed context"

    print("\n✅ STOP_LOSS_SET_FAILED event logging is present")


@pytest.mark.asyncio
async def test_all_new_event_types_exist():
    """Verify all EventTypes added in phases 1.8-1.12 exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'SYMBOL_UNAVAILABLE')
    assert hasattr(EventType, 'ORDER_BELOW_MINIMUM')
    assert hasattr(EventType, 'ORPHANED_SL_CLEANED')
    assert hasattr(EventType, 'STOP_LOSS_SET_ON_LOAD')
    assert hasattr(EventType, 'STOP_LOSS_SET_FAILED')

    # Verify values
    assert EventType.SYMBOL_UNAVAILABLE.value == 'symbol_unavailable'
    assert EventType.ORDER_BELOW_MINIMUM.value == 'order_below_minimum'
    assert EventType.ORPHANED_SL_CLEANED.value == 'orphaned_sl_cleaned'
    assert EventType.STOP_LOSS_SET_ON_LOAD.value == 'stop_loss_set_on_load'
    assert EventType.STOP_LOSS_SET_FAILED.value == 'stop_loss_set_failed'

    print("\n✅ All EventTypes (phases 1.8-1.12) exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls():
    """Verify position_manager has increased event logger calls"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count event logger calls (should be >= 14 now)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    # Previous: 9, New: +5, Total: >= 14
    assert event_logger_count >= 14, f"Expected >= 14 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 14, f"Expected >= 14 log_event calls, found {log_event_count}"

    print(f"\n✅ Position manager has {event_logger_count} event logger instances")
    print(f"✅ Position manager has {log_event_count} log_event calls")
    print(f"   (Previous: 9, Added: {event_logger_count - 9})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
