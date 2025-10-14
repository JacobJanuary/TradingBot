"""
Test Phase 1.3-1.7: Verify position_manager.py event logging works
"""
import pytest


@pytest.mark.asyncio
async def test_positions_loaded_logging():
    """Verify POSITIONS_LOADED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITIONS_LOADED event
    assert 'POSITIONS_LOADED' in source, "Missing POSITIONS_LOADED event"
    assert 'total_exposure' in source, "Missing total_exposure in event data"
    assert source.count('Loaded') > 0, "Missing load positions context"

    print("\n✅ POSITIONS_LOADED event logging is present")


@pytest.mark.asyncio
async def test_positions_without_sl_logging():
    """Verify POSITIONS_WITHOUT_SL_DETECTED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITIONS_WITHOUT_SL_DETECTED event
    assert 'POSITIONS_WITHOUT_SL_DETECTED' in source, "Missing POSITIONS_WITHOUT_SL_DETECTED event"
    assert 'positions without stop losses' in source, "Missing positions without SL context"

    print("\n✅ POSITIONS_WITHOUT_SL_DETECTED event logging is present")


@pytest.mark.asyncio
async def test_position_duplicate_prevented_logging():
    """Verify POSITION_DUPLICATE_PREVENTED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITION_DUPLICATE_PREVENTED event
    assert 'POSITION_DUPLICATE_PREVENTED' in source, "Missing POSITION_DUPLICATE_PREVENTED event"
    assert 'Position already exists' in source, "Missing duplicate position context"

    print("\n✅ POSITION_DUPLICATE_PREVENTED event logging is present")


@pytest.mark.asyncio
async def test_risk_limits_exceeded_logging():
    """Verify RISK_LIMITS_EXCEEDED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check RISK_LIMITS_EXCEEDED event
    assert 'RISK_LIMITS_EXCEEDED' in source, "Missing RISK_LIMITS_EXCEEDED event"
    assert 'current_exposure' in source, "Missing exposure data in event"
    assert 'Risk limits exceeded' in source, "Missing risk limits context"

    print("\n✅ RISK_LIMITS_EXCEEDED event logging is present")


@pytest.mark.asyncio
async def test_position_closed_logging():
    """Verify POSITION_CLOSED event logging code exists"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Check POSITION_CLOSED event
    assert 'POSITION_CLOSED' in source, "Missing POSITION_CLOSED event"
    assert 'realized_pnl' in source, "Missing PnL data in event"
    assert 'exit_price' in source, "Missing exit price in event"

    print("\n✅ POSITION_CLOSED event logging is present")


@pytest.mark.asyncio
async def test_all_event_types_exist():
    """Verify all EventTypes added in phases 1.3-1.7 exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'POSITIONS_LOADED')
    assert hasattr(EventType, 'POSITIONS_WITHOUT_SL_DETECTED')
    assert hasattr(EventType, 'POSITION_DUPLICATE_PREVENTED')
    assert hasattr(EventType, 'RISK_LIMITS_EXCEEDED')
    assert hasattr(EventType, 'POSITION_CLOSED')

    # Verify values
    assert EventType.POSITIONS_LOADED.value == 'positions_loaded'
    assert EventType.POSITIONS_WITHOUT_SL_DETECTED.value == 'positions_without_sl_detected'
    assert EventType.POSITION_DUPLICATE_PREVENTED.value == 'position_duplicate_prevented'
    assert EventType.RISK_LIMITS_EXCEEDED.value == 'risk_limits_exceeded'
    assert EventType.POSITION_CLOSED.value == 'position_closed'

    print("\n✅ All EventTypes (phases 1.3-1.7) exist with correct values")


@pytest.mark.asyncio
async def test_event_logger_calls_count():
    """Verify position_manager has multiple event logger calls"""
    import inspect
    import core.position_manager as pm

    source = inspect.getsource(pm.PositionManager)

    # Count event logger calls (should be >= 7 now: phantom + untracked + 5 new)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 7, f"Expected >= 7 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 7, f"Expected >= 7 log_event calls, found {log_event_count}"

    print(f"\n✅ Position manager has {event_logger_count} event logger instances")
    print(f"✅ Position manager has {log_event_count} log_event calls")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
