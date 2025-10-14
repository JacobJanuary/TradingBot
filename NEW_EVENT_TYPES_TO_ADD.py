# NEW EVENT TYPES TO ADD TO core/event_logger.py
#
# Instructions:
# 1. Open /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/event_logger.py
# 2. Find class EventType(Enum): (around line 19)
# 3. Add these new types AFTER the existing ones (after TRANSACTION_ROLLED_BACK)
# 4. Keep the existing types unchanged

# ============================================================
# ADD THESE LINES TO EventType(Enum) CLASS
# ============================================================

    # Wave events (Signal Processing)
    WAVE_MONITORING_STARTED = "wave_monitoring_started"
    WAVE_DETECTED = "wave_detected"
    WAVE_COMPLETED = "wave_completed"
    WAVE_NOT_FOUND = "wave_not_found"
    WAVE_DUPLICATE_DETECTED = "wave_duplicate_detected"
    WAVE_PROCESSING_STARTED = "wave_processing_started"
    WAVE_TARGET_REACHED = "wave_target_reached"
    WAVE_BUFFER_EXHAUSTED = "wave_buffer_exhausted"

    # Signal events (Individual Signal Execution)
    SIGNAL_EXECUTED = "signal_executed"
    SIGNAL_EXECUTION_FAILED = "signal_execution_failed"
    SIGNAL_FILTERED = "signal_filtered"
    SIGNAL_VALIDATION_FAILED = "signal_validation_failed"
    BAD_SYMBOL_LEAKED = "bad_symbol_leaked"
    INSUFFICIENT_FUNDS = "insufficient_funds"

    # Trailing Stop events (Protection)
    TRAILING_STOP_CREATED = "trailing_stop_created"
    TRAILING_STOP_ACTIVATED = "trailing_stop_activated"
    TRAILING_STOP_UPDATED = "trailing_stop_updated"
    TRAILING_STOP_BREAKEVEN = "trailing_stop_breakeven"
    TRAILING_STOP_REMOVED = "trailing_stop_removed"
    PROTECTION_SL_CANCELLED = "protection_sl_cancelled"
    PROTECTION_SL_CANCEL_FAILED = "protection_sl_cancel_failed"

    # Synchronization events (Position Sync)
    SYNCHRONIZATION_STARTED = "synchronization_started"
    SYNCHRONIZATION_COMPLETED = "synchronization_completed"
    PHANTOM_POSITION_CLOSED = "phantom_position_closed"
    PHANTOM_POSITION_DETECTED = "phantom_position_detected"
    MISSING_POSITION_ADDED = "missing_position_added"
    MISSING_POSITION_REJECTED = "missing_position_rejected"
    QUANTITY_MISMATCH_DETECTED = "quantity_mismatch_detected"
    QUANTITY_UPDATED = "quantity_updated"
    POSITION_VERIFIED = "position_verified"

    # Zombie Order events (Cleanup)
    ZOMBIE_ORDERS_DETECTED = "zombie_orders_detected"
    ZOMBIE_ORDER_CANCELLED = "zombie_order_cancelled"
    ZOMBIE_CLEANUP_COMPLETED = "zombie_cleanup_completed"
    ZOMBIE_ALERT_TRIGGERED = "zombie_alert_triggered"
    AGGRESSIVE_CLEANUP_TRIGGERED = "aggressive_cleanup_triggered"
    TPSL_ORDERS_CLEARED = "tpsl_orders_cleared"

    # Position Manager events (Lifecycle)
    POSITION_DUPLICATE_PREVENTED = "position_duplicate_prevented"
    POSITION_NOT_FOUND_ON_EXCHANGE = "position_not_found_on_exchange"
    POSITIONS_LOADED = "positions_loaded"
    POSITIONS_WITHOUT_SL_DETECTED = "positions_without_sl_detected"
    POSITION_CREATION_FAILED = "position_creation_failed"

    # Risk Management events
    RISK_LIMITS_EXCEEDED = "risk_limits_exceeded"

    # Symbol/Order Validation events
    SYMBOL_UNAVAILABLE = "symbol_unavailable"
    ORDER_BELOW_MINIMUM = "order_below_minimum"

    # Stop Loss Management events (General)
    STOP_LOSS_SET_ON_LOAD = "stop_loss_set_on_load"
    STOP_LOSS_SET_FAILED = "stop_loss_set_failed"
    ORPHANED_SL_CLEANED = "orphaned_sl_cleaned"
    EMERGENCY_STOP_PLACED = "emergency_stop_placed"
    STOP_MOVED_TO_BREAKEVEN = "stop_moved_to_breakeven"

    # Recovery events (System Health)
    POSITION_RECOVERY_STARTED = "position_recovery_started"
    POSITION_RECOVERY_COMPLETED = "position_recovery_completed"
    INCOMPLETE_POSITION_DETECTED = "incomplete_position_detected"

    # System Health events
    PERIODIC_SYNC_STARTED = "periodic_sync_started"
    EMERGENCY_CLOSE_ALL_TRIGGERED = "emergency_close_all_triggered"
    HEALTH_CHECK_FAILED = "health_check_failed"

    # WebSocket events (Connectivity)
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"
    WEBSOCKET_ERROR = "websocket_error"
    SIGNALS_RECEIVED = "signals_received"

# ============================================================
# TOTAL NEW EVENTS: 63
# ============================================================

# VERIFICATION:
# After adding these, run this in Python:
#
# from core.event_logger import EventType
# all_types = [e.value for e in EventType]
# print(f"Total EventType count: {len(all_types)}")
# print(f"Expected: ~80 (17 existing + 63 new)")
#
# Expected output:
# Total EventType count: 80

# ============================================================
# EXAMPLE USAGE AFTER ADDING
# ============================================================

"""
Example 1: Wave Detection
-------------------------
from core.event_logger import get_event_logger, EventType

event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.WAVE_DETECTED,
        {
            'wave_timestamp': expected_wave_timestamp,
            'signal_count': len(wave_signals),
            'first_seen': datetime.now(timezone.utc).isoformat()
        },
        severity='INFO',
        correlation_id=f"wave_{expected_wave_timestamp}"
    )

Example 2: Trailing Stop Activated
-----------------------------------
from core.event_logger import get_event_logger, EventType

event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.TRAILING_STOP_ACTIVATED,
        {
            'symbol': symbol,
            'activation_price': float(current_price),
            'stop_price': float(stop_price),
            'profit_percent': float(profit)
        },
        symbol=symbol,
        severity='INFO'
    )

Example 3: Phantom Position
---------------------------
from core.event_logger import get_event_logger, EventType

event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.PHANTOM_POSITION_CLOSED,
        {
            'symbol': symbol,
            'position_id': position_id,
            'reason': 'not_on_exchange'
        },
        position_id=position_id,
        symbol=symbol,
        exchange=exchange,
        severity='WARNING'
    )

Example 4: Zombie Orders
------------------------
from core.event_logger import get_event_logger, EventType

event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.ZOMBIE_ORDERS_DETECTED,
        {
            'exchange': exchange_name,
            'count': len(zombies),
            'symbols': [z.symbol for z in zombies[:10]]
        },
        exchange=exchange_name,
        severity='WARNING'
    )
"""

# ============================================================
# TESTING CHECKLIST
# ============================================================

"""
After adding these EventTypes to event_logger.py:

1. Verify syntax is correct:
   python -m py_compile core/event_logger.py

2. Test import:
   python -c "from core.event_logger import EventType; print(len([e for e in EventType]))"

3. Verify enum values are unique:
   python -c "from core.event_logger import EventType; values = [e.value for e in EventType]; print('Duplicates:', [v for v in values if values.count(v) > 1])"

4. Check total count (should be ~80):
   python -c "from core.event_logger import EventType; print(f'Total: {len([e for e in EventType])}')"

Expected output for step 4:
Total: 80

If all tests pass, proceed with implementation!
"""
