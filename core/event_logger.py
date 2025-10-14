"""
Event Logger - Comprehensive audit trail for all critical operations

CRITICAL: This module ensures complete traceability of system operations
⚠️ DO NOT DISABLE logging in production!
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum
import asyncpg
import traceback

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events to log"""
    # Position events
    POSITION_CREATED = "position_created"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"
    POSITION_ERROR = "position_error"

    # Order events
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_ERROR = "order_error"

    # Stop-loss events
    STOP_LOSS_PLACED = "stop_loss_placed"
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    STOP_LOSS_UPDATED = "stop_loss_updated"
    STOP_LOSS_ERROR = "stop_loss_error"

    # System events
    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"
    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"
    ERROR_OCCURRED = "error_occurred"
    WARNING_RAISED = "warning_raised"

    # Transaction events
    TRANSACTION_STARTED = "transaction_started"
    TRANSACTION_COMMITTED = "transaction_committed"
    TRANSACTION_ROLLED_BACK = "transaction_rolled_back"

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
    TRAILING_STOP_SL_UPDATED = "trailing_stop_sl_updated"
    TRAILING_STOP_SL_UPDATE_FAILED = "trailing_stop_sl_update_failed"

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

    # Database events (Data Persistence)
    DATABASE_ERROR = "database_error"

    # Exchange API events (External Communication)
    EXCHANGE_ERROR = "exchange_error"

    # Position Age Management events
    AGED_POSITION_DETECTED = "aged_position_detected"

    # WebSocket events (Connectivity)
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"
    WEBSOCKET_ERROR = "websocket_error"
    SIGNALS_RECEIVED = "signals_received"


class EventLogger:
    """
    Centralized event logging system

    Features:
    - Structured logging to database
    - Automatic correlation of related events
    - Error tracking and analysis
    - Performance metrics
    - Audit trail for compliance
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Args:
            pool: Database connection pool
        """
        self.pool = pool
        self._event_queue = asyncio.Queue(maxsize=1000)
        self._batch_size = 100
        self._flush_interval = 5.0  # seconds
        self._worker_task = None
        self._shutdown = False

    async def initialize(self):
        """Initialize event logger and verify tables exist"""
        try:
            await self._verify_tables()
            self._worker_task = asyncio.create_task(self._event_worker())
            logger.info("EventLogger initialized")
        except Exception as e:
            logger.error(f"EventLogger initialization failed: {e}", exc_info=True)
            raise

    async def _verify_tables(self):
        """Verify that required event logging tables exist"""
        async with self.pool.acquire() as conn:
            # Check if required tables exist
            missing_tables = []

            required_tables = [
                'events',
                'transaction_log',
                'event_performance_metrics'
            ]

            for table_name in required_tables:
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'monitoring'
                        AND table_name = $1
                    )
                """, table_name)

                if not exists:
                    missing_tables.append(table_name)

            if missing_tables:
                error_msg = (
                    f"EventLogger tables missing: {', '.join(missing_tables)}. "
                    f"Please apply database migration 004_create_event_logger_tables.sql first. "
                    f"Run: PGPASSWORD='your_password' psql -h localhost -U postgres -d fox_crypto -f database/migrations/004_create_event_logger_tables.sql"
                )
                raise RuntimeError(error_msg)

    async def log_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None,
        position_id: Optional[int] = None,
        order_id: Optional[str] = None,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        severity: str = "INFO",
        error: Optional[Exception] = None
    ):
        """
        Log an event to the database

        Args:
            event_type: Type of event
            data: Event data as dict
            correlation_id: ID to correlate related events
            position_id: Related position ID
            order_id: Related order ID
            symbol: Trading symbol
            exchange: Exchange name
            severity: INFO, WARNING, ERROR, CRITICAL
            error: Exception if this is an error event
        """
        event = {
            'event_type': event_type.value,
            'event_data': json.dumps(data),
            'correlation_id': correlation_id,
            'position_id': position_id,
            'order_id': order_id,
            'symbol': symbol,
            'exchange': exchange,
            'severity': severity,
            'error_message': str(error) if error else None,
            'stack_trace': traceback.format_exc() if error else None,
            'created_at': datetime.now(timezone.utc)
        }

        # Try to add to queue, if full log directly
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event queue full, logging directly")
            await self._write_event(event)

        # Also log to standard logger
        log_msg = f"{event_type.value}: {data}"
        if severity == "ERROR":
            logger.error(log_msg)
        elif severity == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    async def _event_worker(self):
        """Background worker to batch write events"""
        batch = []
        last_flush = asyncio.get_event_loop().time()
        logger.info("EventLogger worker started")

        while not self._shutdown:
            try:
                # Try to get event with timeout
                try:
                    event = await asyncio.wait_for(
                        self._event_queue.get(),
                        timeout=1.0
                    )
                    batch.append(event)
                except asyncio.TimeoutError:
                    pass

                # Check if we should flush
                current_time = asyncio.get_event_loop().time()
                should_flush = (
                    len(batch) >= self._batch_size or
                    (batch and current_time - last_flush > self._flush_interval)
                )

                if should_flush and batch:
                    logger.info(f"EventLogger flushing {len(batch)} events")
                    await self._write_batch(batch)
                    batch = []
                    last_flush = current_time

            except Exception as e:
                logger.error(f"EventLogger worker error: {e}", exc_info=True)
                await asyncio.sleep(1)

        # Final flush on shutdown
        if batch:
            await self._write_batch(batch)

    async def _write_event(self, event: Dict[str, Any]):
        """Write single event to database"""
        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO monitoring.events (
                    event_type, event_data, correlation_id,
                    position_id, order_id, symbol, exchange,
                    severity, error_message, stack_trace, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """
            await conn.execute(
                query,
                event['event_type'],
                event['event_data'],
                event['correlation_id'],
                event['position_id'],
                event['order_id'],
                event['symbol'],
                event['exchange'],
                event['severity'],
                event['error_message'],
                event['stack_trace'],
                event['created_at']
            )

    async def _write_batch(self, batch: List[Dict[str, Any]]):
        """Write batch of events to database"""
        if not batch:
            return

        async with self.pool.acquire() as conn:
            # DEBUG: показать куда подключились
            db_info = await conn.fetchrow("""
                SELECT current_database() as db,
                       inet_server_addr() as host,
                       inet_server_port() as port
            """)
            logger.info(f"EventLogger connected to: {db_info['host']}:{db_info['port']}/{db_info['db']}")

            # Count BEFORE insert
            count_before = await conn.fetchval("SELECT COUNT(*) FROM monitoring.events")

            # Prepare batch insert
            query = """
                INSERT INTO monitoring.events (
                    event_type, event_data, correlation_id,
                    position_id, order_id, symbol, exchange,
                    severity, error_message, stack_trace, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """

            logger.info(f"EventLogger executing INSERT for {len(batch)} events (count_before={count_before})")

            try:
                # Execute batch
                await conn.executemany(
                    query,
                    [
                        (
                            e['event_type'], e['event_data'], e['correlation_id'],
                            e['position_id'], e['order_id'], e['symbol'], e['exchange'],
                            e['severity'], e['error_message'], e['stack_trace'], e['created_at']
                        )
                        for e in batch
                    ]
                )

                # Count AFTER insert (same connection)
                count_after = await conn.fetchval("SELECT COUNT(*) FROM monitoring.events")

                # Get last 3 IDs to verify
                last_ids = await conn.fetch("SELECT id, event_type FROM monitoring.events ORDER BY id DESC LIMIT 3")
                last_ids_str = ', '.join([f"id={r['id']}:{r['event_type']}" for r in last_ids])

                logger.info(f"EventLogger wrote {len(batch)} events to DB (count_before={count_before}, count_after={count_after}, delta={count_after - count_before}, last_ids=[{last_ids_str}])")
            except Exception as e:
                logger.error(f"EventLogger batch write failed: {e}", exc_info=True)

        # Verify write from new connection
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM monitoring.events")
            logger.info(f"EventLogger DB verify from NEW connection: {count}")

    async def log_transaction(
        self,
        transaction_id: str,
        operation: str,
        status: str,
        started_at: datetime,
        completed_at: Optional[datetime] = None,
        affected_rows: Optional[int] = None,
        error: Optional[str] = None
    ):
        """Log database transaction"""
        duration_ms = None
        if completed_at and started_at:
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO monitoring.transaction_log (
                    transaction_id, operation, status,
                    started_at, completed_at, duration_ms,
                    affected_rows, error_message
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (transaction_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    completed_at = EXCLUDED.completed_at,
                    duration_ms = EXCLUDED.duration_ms,
                    affected_rows = EXCLUDED.affected_rows,
                    error_message = EXCLUDED.error_message
            """
            await conn.execute(
                query,
                transaction_id, operation, status,
                started_at, completed_at, duration_ms,
                affected_rows, error
            )

    async def log_metric(
        self,
        metric_name: str,
        metric_value: float,
        tags: Optional[Dict[str, Any]] = None
    ):
        """Log performance metric"""
        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO monitoring.event_performance_metrics (
                    metric_name, metric_value, tags, recorded_at
                ) VALUES ($1, $2, $3, $4)
            """
            await conn.execute(
                query,
                metric_name,
                metric_value,
                json.dumps(tags) if tags else None,
                datetime.now(timezone.utc)
            )

    async def get_recent_events(
        self,
        event_type: Optional[EventType] = None,
        position_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent events from the log"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT * FROM monitoring.events
                WHERE ($1::varchar IS NULL OR event_type = $1)
                  AND ($2::integer IS NULL OR position_id = $2)
                ORDER BY created_at DESC
                LIMIT $3
            """
            rows = await conn.fetch(
                query,
                event_type.value if event_type else None,
                position_id,
                limit
            )

            return [dict(row) for row in rows]

    async def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary for recent period"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT
                    event_type,
                    COUNT(*) as count,
                    MAX(created_at) as last_occurrence
                FROM monitoring.events
                WHERE severity IN ('ERROR', 'CRITICAL')
                  AND created_at > NOW() - INTERVAL '%s hours'
                GROUP BY event_type
                ORDER BY count DESC
            """
            rows = await conn.fetch(query, hours)

            return {
                'total_errors': sum(row['count'] for row in rows),
                'by_type': [dict(row) for row in rows]
            }

    async def shutdown(self):
        """Graceful shutdown"""
        self._shutdown = True
        if self._worker_task:
            await self._worker_task
        logger.info("EventLogger shut down")


# Global instance
_event_logger: Optional[EventLogger] = None


def get_event_logger() -> Optional[EventLogger]:
    """Get global event logger instance"""
    return _event_logger


def set_event_logger(logger_instance: EventLogger):
    """Set global event logger instance"""
    global _event_logger
    _event_logger = logger_instance


# Convenience functions
async def log_event(*args, **kwargs):
    """Convenience function to log event"""
    logger = get_event_logger()
    if logger:
        await logger.log_event(*args, **kwargs)


async def log_error(message: str, error: Exception, **kwargs):
    """Convenience function to log error"""
    logger = get_event_logger()
    if logger:
        await logger.log_event(
            EventType.ERROR_OCCURRED,
            {'message': message, 'error': str(error)},
            severity='ERROR',
            error=error,
            **kwargs
        )