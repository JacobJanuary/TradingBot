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
        """Initialize event logger and create tables if needed"""
        await self._create_tables()
        self._worker_task = asyncio.create_task(self._event_worker())
        logger.info("EventLogger initialized")

    async def _create_tables(self):
        """Create event logging tables if not exists"""
        async with self.pool.acquire() as conn:
            # Events table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    event_type VARCHAR(50) NOT NULL,
                    event_data JSONB,
                    correlation_id VARCHAR(100),
                    position_id INTEGER,
                    order_id VARCHAR(100),
                    symbol VARCHAR(50),
                    exchange VARCHAR(50),
                    severity VARCHAR(20) DEFAULT 'INFO',
                    error_message TEXT,
                    stack_trace TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    -- Indexes for fast queries
                    INDEX idx_events_type (event_type),
                    INDEX idx_events_correlation (correlation_id),
                    INDEX idx_events_position (position_id),
                    INDEX idx_events_created (created_at DESC)
                )
            """)

            # Transaction log table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transaction_log (
                    id SERIAL PRIMARY KEY,
                    transaction_id VARCHAR(100) UNIQUE,
                    operation VARCHAR(100),
                    status VARCHAR(20),
                    started_at TIMESTAMP WITH TIME ZONE,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    duration_ms INTEGER,
                    affected_rows INTEGER,
                    error_message TEXT,

                    INDEX idx_tx_log_id (transaction_id),
                    INDEX idx_tx_log_status (status)
                )
            """)

            # Performance metrics table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id SERIAL PRIMARY KEY,
                    metric_name VARCHAR(100),
                    metric_value DECIMAL(20, 8),
                    tags JSONB,
                    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    INDEX idx_metrics_name (metric_name),
                    INDEX idx_metrics_time (recorded_at DESC)
                )
            """)

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
                    await self._write_batch(batch)
                    batch = []
                    last_flush = current_time

            except Exception as e:
                logger.error(f"Event worker error: {e}")
                await asyncio.sleep(1)

        # Final flush on shutdown
        if batch:
            await self._write_batch(batch)

    async def _write_event(self, event: Dict[str, Any]):
        """Write single event to database"""
        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO events (
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
            # Prepare batch insert
            query = """
                INSERT INTO events (
                    event_type, event_data, correlation_id,
                    position_id, order_id, symbol, exchange,
                    severity, error_message, stack_trace, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """

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

            logger.debug(f"Wrote batch of {len(batch)} events")

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
                INSERT INTO transaction_log (
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
                INSERT INTO performance_metrics (
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
                SELECT * FROM events
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
                FROM events
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