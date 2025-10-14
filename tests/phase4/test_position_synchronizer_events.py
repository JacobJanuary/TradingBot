"""
Test Phase 4: Verify position synchronizer event logging in position_synchronizer.py
"""
import pytest


@pytest.mark.asyncio
async def test_synchronization_started_logging():
    """Verify SYNCHRONIZATION_STARTED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check SYNCHRONIZATION_STARTED event
    assert 'SYNCHRONIZATION_STARTED' in source, "Missing SYNCHRONIZATION_STARTED event"
    assert 'synchronize_all_exchanges' in source, "Missing synchronize_all_exchanges function"
    assert 'exchange_count' in source, "Missing exchange_count context"

    print("\n✅ SYNCHRONIZATION_STARTED event logging is present")


@pytest.mark.asyncio
async def test_synchronization_completed_logging():
    """Verify SYNCHRONIZATION_COMPLETED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check SYNCHRONIZATION_COMPLETED event
    assert 'SYNCHRONIZATION_COMPLETED' in source, "Missing SYNCHRONIZATION_COMPLETED event"
    assert 'verified' in source, "Missing verified count tracking"
    assert 'closed_phantom' in source, "Missing closed_phantom count tracking"

    print("\n✅ SYNCHRONIZATION_COMPLETED event logging is present")


@pytest.mark.asyncio
async def test_position_verified_logging():
    """Verify POSITION_VERIFIED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check POSITION_VERIFIED event
    assert 'POSITION_VERIFIED' in source, "Missing POSITION_VERIFIED event"
    assert 'db_quantity' in source, "Missing db_quantity tracking"
    assert 'exchange_quantity' in source, "Missing exchange_quantity tracking"

    print("\n✅ POSITION_VERIFIED event logging is present")


@pytest.mark.asyncio
async def test_quantity_mismatch_detected_logging():
    """Verify QUANTITY_MISMATCH_DETECTED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check QUANTITY_MISMATCH_DETECTED event
    assert 'QUANTITY_MISMATCH_DETECTED' in source, "Missing QUANTITY_MISMATCH_DETECTED event"
    assert 'difference' in source, "Missing difference calculation"
    assert 'Quantity mismatch' in source, "Missing mismatch log message"

    print("\n✅ QUANTITY_MISMATCH_DETECTED event logging is present")


@pytest.mark.asyncio
async def test_quantity_updated_logging():
    """Verify QUANTITY_UPDATED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check QUANTITY_UPDATED event
    assert 'QUANTITY_UPDATED' in source, "Missing QUANTITY_UPDATED event"
    assert '_update_position_quantity' in source, "Missing update quantity function"
    assert 'new_quantity' in source, "Missing new_quantity tracking"

    print("\n✅ QUANTITY_UPDATED event logging is present")


@pytest.mark.asyncio
async def test_phantom_position_detected_logging():
    """Verify PHANTOM_POSITION_DETECTED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check PHANTOM_POSITION_DETECTED event
    assert 'PHANTOM_POSITION_DETECTED' in source, "Missing PHANTOM_POSITION_DETECTED event"
    assert 'PHANTOM position' in source, "Missing phantom position log message"
    assert 'not on exchange' in source, "Missing phantom reason tracking"

    print("\n✅ PHANTOM_POSITION_DETECTED event logging is present")


@pytest.mark.asyncio
async def test_phantom_position_closed_logging():
    """Verify PHANTOM_POSITION_CLOSED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check PHANTOM_POSITION_CLOSED event
    assert 'PHANTOM_POSITION_CLOSED' in source, "Missing PHANTOM_POSITION_CLOSED event"
    assert '_close_phantom_position' in source, "Missing close phantom function"
    assert 'not_on_exchange' in source, "Missing closure reason"

    print("\n✅ PHANTOM_POSITION_CLOSED event logging is present")


@pytest.mark.asyncio
async def test_missing_position_rejected_logging():
    """Verify MISSING_POSITION_REJECTED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check MISSING_POSITION_REJECTED event
    assert 'MISSING_POSITION_REJECTED' in source, "Missing MISSING_POSITION_REJECTED event"
    assert 'no_exchange_order_id' in source, "Missing rejection reason"
    assert 'REJECTED' in source, "Missing rejection log message"

    print("\n✅ MISSING_POSITION_REJECTED event logging is present")


@pytest.mark.asyncio
async def test_missing_position_added_logging():
    """Verify MISSING_POSITION_ADDED event logging code exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Check MISSING_POSITION_ADDED event
    assert 'MISSING_POSITION_ADDED' in source, "Missing MISSING_POSITION_ADDED event"
    assert '_add_missing_position' in source, "Missing add missing position function"
    assert 'Added missing position' in source, "Missing add success message"

    print("\n✅ MISSING_POSITION_ADDED event logging is present")


@pytest.mark.asyncio
async def test_event_logger_import():
    """Verify event_logger import exists"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps)

    # Check import
    assert 'from core.event_logger import get_event_logger, EventType' in source, \
        "Missing event_logger import"

    print("\n✅ Event logger import is present")


@pytest.mark.asyncio
async def test_all_synchronizer_event_types():
    """Verify all position synchronizer EventTypes exist"""
    from core.event_logger import EventType

    # Check all event types exist
    assert hasattr(EventType, 'SYNCHRONIZATION_STARTED')
    assert hasattr(EventType, 'SYNCHRONIZATION_COMPLETED')
    assert hasattr(EventType, 'POSITION_VERIFIED')
    assert hasattr(EventType, 'QUANTITY_MISMATCH_DETECTED')
    assert hasattr(EventType, 'QUANTITY_UPDATED')
    assert hasattr(EventType, 'PHANTOM_POSITION_DETECTED')
    assert hasattr(EventType, 'PHANTOM_POSITION_CLOSED')
    assert hasattr(EventType, 'MISSING_POSITION_REJECTED')
    assert hasattr(EventType, 'MISSING_POSITION_ADDED')

    # Verify values
    assert EventType.SYNCHRONIZATION_STARTED.value == 'synchronization_started'
    assert EventType.SYNCHRONIZATION_COMPLETED.value == 'synchronization_completed'
    assert EventType.POSITION_VERIFIED.value == 'position_verified'
    assert EventType.QUANTITY_MISMATCH_DETECTED.value == 'quantity_mismatch_detected'
    assert EventType.QUANTITY_UPDATED.value == 'quantity_updated'
    assert EventType.PHANTOM_POSITION_DETECTED.value == 'phantom_position_detected'
    assert EventType.PHANTOM_POSITION_CLOSED.value == 'phantom_position_closed'
    assert EventType.MISSING_POSITION_REJECTED.value == 'missing_position_rejected'
    assert EventType.MISSING_POSITION_ADDED.value == 'missing_position_added'

    print("\n✅ All position synchronizer EventTypes exist with correct values")


@pytest.mark.asyncio
async def test_total_event_logger_calls():
    """Verify position_synchronizer.py has event logger calls"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Count event logger calls (should be >= 9: 2 sync, 1 verified, 2 quantity, 2 phantom, 2 missing)
    event_logger_count = source.count('event_logger = get_event_logger()')
    log_event_count = source.count('await event_logger.log_event(')

    assert event_logger_count >= 9, f"Expected >= 9 get_event_logger() calls, found {event_logger_count}"
    assert log_event_count >= 9, f"Expected >= 9 log_event calls, found {log_event_count}"

    print(f"\n✅ Position synchronizer has {event_logger_count} event logger instances")
    print(f"✅ Position synchronizer has {log_event_count} log_event calls")


@pytest.mark.asyncio
async def test_event_context_completeness():
    """Verify events include proper context"""
    import inspect
    import core.position_synchronizer as ps

    source = inspect.getsource(ps.PositionSynchronizer)

    # Verify context includes key data
    assert "'symbol'" in source, "Missing symbol in event context"
    assert "'exchange'" in source, "Missing exchange in event context"
    assert "'position_id'" in source, "Missing position_id in event context"
    assert "severity='INFO'" in source, "Missing INFO severity"
    assert "severity='WARNING'" in source, "Missing WARNING severity"

    print("\n✅ Position synchronizer events include proper context")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
