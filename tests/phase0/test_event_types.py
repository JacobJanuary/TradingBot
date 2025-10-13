"""
Test Phase 0: Verify all new EventTypes added correctly
"""
import pytest
from core.event_logger import EventType


def test_all_original_event_types_exist():
    """Verify original EventTypes still exist (no breaking changes)"""
    # Position events
    assert hasattr(EventType, 'POSITION_CREATED')
    assert hasattr(EventType, 'POSITION_UPDATED')
    assert hasattr(EventType, 'POSITION_CLOSED')
    assert hasattr(EventType, 'POSITION_ERROR')

    # Order events
    assert hasattr(EventType, 'ORDER_PLACED')
    assert hasattr(EventType, 'ORDER_FILLED')
    assert hasattr(EventType, 'ORDER_CANCELLED')
    assert hasattr(EventType, 'ORDER_ERROR')

    # Stop-loss events
    assert hasattr(EventType, 'STOP_LOSS_PLACED')
    assert hasattr(EventType, 'STOP_LOSS_TRIGGERED')
    assert hasattr(EventType, 'STOP_LOSS_UPDATED')
    assert hasattr(EventType, 'STOP_LOSS_ERROR')

    # System events
    assert hasattr(EventType, 'BOT_STARTED')
    assert hasattr(EventType, 'BOT_STOPPED')
    assert hasattr(EventType, 'SYNC_STARTED')
    assert hasattr(EventType, 'SYNC_COMPLETED')
    assert hasattr(EventType, 'ERROR_OCCURRED')
    assert hasattr(EventType, 'WARNING_RAISED')

    # Transaction events
    assert hasattr(EventType, 'TRANSACTION_STARTED')
    assert hasattr(EventType, 'TRANSACTION_COMMITTED')
    assert hasattr(EventType, 'TRANSACTION_ROLLED_BACK')


def test_wave_event_types_added():
    """Verify Wave event types added (8 types)"""
    assert hasattr(EventType, 'WAVE_MONITORING_STARTED')
    assert hasattr(EventType, 'WAVE_DETECTED')
    assert hasattr(EventType, 'WAVE_COMPLETED')
    assert hasattr(EventType, 'WAVE_NOT_FOUND')
    assert hasattr(EventType, 'WAVE_DUPLICATE_DETECTED')
    assert hasattr(EventType, 'WAVE_PROCESSING_STARTED')
    assert hasattr(EventType, 'WAVE_TARGET_REACHED')
    assert hasattr(EventType, 'WAVE_BUFFER_EXHAUSTED')


def test_signal_event_types_added():
    """Verify Signal event types added (6 types)"""
    assert hasattr(EventType, 'SIGNAL_EXECUTED')
    assert hasattr(EventType, 'SIGNAL_EXECUTION_FAILED')
    assert hasattr(EventType, 'SIGNAL_FILTERED')
    assert hasattr(EventType, 'SIGNAL_VALIDATION_FAILED')
    assert hasattr(EventType, 'BAD_SYMBOL_LEAKED')
    assert hasattr(EventType, 'INSUFFICIENT_FUNDS')


def test_trailing_stop_event_types_added():
    """Verify Trailing Stop event types added (7 types)"""
    assert hasattr(EventType, 'TRAILING_STOP_CREATED')
    assert hasattr(EventType, 'TRAILING_STOP_ACTIVATED')
    assert hasattr(EventType, 'TRAILING_STOP_UPDATED')
    assert hasattr(EventType, 'TRAILING_STOP_BREAKEVEN')
    assert hasattr(EventType, 'TRAILING_STOP_REMOVED')
    assert hasattr(EventType, 'PROTECTION_SL_CANCELLED')
    assert hasattr(EventType, 'PROTECTION_SL_CANCEL_FAILED')


def test_synchronization_event_types_added():
    """Verify Synchronization event types added (9 types)"""
    assert hasattr(EventType, 'SYNCHRONIZATION_STARTED')
    assert hasattr(EventType, 'SYNCHRONIZATION_COMPLETED')
    assert hasattr(EventType, 'PHANTOM_POSITION_CLOSED')
    assert hasattr(EventType, 'PHANTOM_POSITION_DETECTED')
    assert hasattr(EventType, 'MISSING_POSITION_ADDED')
    assert hasattr(EventType, 'MISSING_POSITION_REJECTED')
    assert hasattr(EventType, 'QUANTITY_MISMATCH_DETECTED')
    assert hasattr(EventType, 'QUANTITY_UPDATED')
    assert hasattr(EventType, 'POSITION_VERIFIED')


def test_zombie_order_event_types_added():
    """Verify Zombie Order event types added (6 types)"""
    assert hasattr(EventType, 'ZOMBIE_ORDERS_DETECTED')
    assert hasattr(EventType, 'ZOMBIE_ORDER_CANCELLED')
    assert hasattr(EventType, 'ZOMBIE_CLEANUP_COMPLETED')
    assert hasattr(EventType, 'ZOMBIE_ALERT_TRIGGERED')
    assert hasattr(EventType, 'AGGRESSIVE_CLEANUP_TRIGGERED')
    assert hasattr(EventType, 'TPSL_ORDERS_CLEARED')


def test_position_manager_event_types_added():
    """Verify Position Manager event types added (5 types)"""
    assert hasattr(EventType, 'POSITION_DUPLICATE_PREVENTED')
    assert hasattr(EventType, 'POSITION_NOT_FOUND_ON_EXCHANGE')
    assert hasattr(EventType, 'POSITIONS_LOADED')
    assert hasattr(EventType, 'POSITIONS_WITHOUT_SL_DETECTED')
    assert hasattr(EventType, 'POSITION_CREATION_FAILED')


def test_risk_management_event_types_added():
    """Verify Risk Management event types added (1 type)"""
    assert hasattr(EventType, 'RISK_LIMITS_EXCEEDED')


def test_symbol_validation_event_types_added():
    """Verify Symbol Validation event types added (2 types)"""
    assert hasattr(EventType, 'SYMBOL_UNAVAILABLE')
    assert hasattr(EventType, 'ORDER_BELOW_MINIMUM')


def test_stop_loss_management_event_types_added():
    """Verify Stop Loss Management event types added (5 types)"""
    assert hasattr(EventType, 'STOP_LOSS_SET_ON_LOAD')
    assert hasattr(EventType, 'STOP_LOSS_SET_FAILED')
    assert hasattr(EventType, 'ORPHANED_SL_CLEANED')
    assert hasattr(EventType, 'EMERGENCY_STOP_PLACED')
    assert hasattr(EventType, 'STOP_MOVED_TO_BREAKEVEN')


def test_recovery_event_types_added():
    """Verify Recovery event types added (3 types)"""
    assert hasattr(EventType, 'POSITION_RECOVERY_STARTED')
    assert hasattr(EventType, 'POSITION_RECOVERY_COMPLETED')
    assert hasattr(EventType, 'INCOMPLETE_POSITION_DETECTED')


def test_system_health_event_types_added():
    """Verify System Health event types added (3 types)"""
    assert hasattr(EventType, 'PERIODIC_SYNC_STARTED')
    assert hasattr(EventType, 'EMERGENCY_CLOSE_ALL_TRIGGERED')
    assert hasattr(EventType, 'HEALTH_CHECK_FAILED')


def test_websocket_event_types_added():
    """Verify WebSocket event types added (4 types)"""
    assert hasattr(EventType, 'WEBSOCKET_CONNECTED')
    assert hasattr(EventType, 'WEBSOCKET_DISCONNECTED')
    assert hasattr(EventType, 'WEBSOCKET_ERROR')
    assert hasattr(EventType, 'SIGNALS_RECEIVED')


def test_total_event_types_count():
    """Verify total EventTypes count (17 original + 63 new = 80)"""
    event_types = [e for e in dir(EventType) if not e.startswith('_')]
    # Enum class has additional members, filter only event types
    event_values = [getattr(EventType, e) for e in event_types if isinstance(getattr(EventType, e), EventType)]

    assert len(event_values) >= 80, f"Expected at least 80 EventTypes, found {len(event_values)}"


def test_event_types_have_unique_values():
    """Verify all EventTypes have unique string values"""
    event_types = [e for e in dir(EventType) if not e.startswith('_')]
    event_values = [getattr(EventType, e).value for e in event_types if isinstance(getattr(EventType, e), EventType)]

    assert len(event_values) == len(set(event_values)), "Duplicate event type values found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
