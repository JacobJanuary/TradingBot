"""
SQLite Repository - унифицированный интерфейс для работы с SQLite
Совместим с интерфейсом PostgreSQL Repository для легкой замены
"""
import sqlite3
import asyncio
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class SQLiteRepository:
    """
    SQLite implementation of Repository pattern
    Drop-in replacement for PostgreSQL Repository
    """

    def __init__(self, db_path: str = 'trading_bot.db'):
        """Initialize SQLite repository"""
        self.db_path = db_path
        self._local = None

    async def initialize(self):
        """Initialize database connection"""
        # SQLite doesn't need connection pool, but we maintain interface compatibility
        self._local = sqlite3.connect(self.db_path, check_same_thread=False)
        self._local.row_factory = sqlite3.Row  # Return rows as dictionaries
        logger.info(f"SQLite database initialized: {self.db_path}")

    async def close(self):
        """Close database connection"""
        if self._local:
            self._local.close()

    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager for atomic operations"""
        cursor = self._local.cursor()
        try:
            yield cursor
            self._local.commit()
        except Exception as e:
            self._local.rollback()
            logger.error(f"Transaction rollback: {e}")
            raise
        finally:
            cursor.close()

    # ============== Position Operations ==============

    async def create_position(self, position_data: Dict) -> int:
        """Create new position record"""
        query = """
            INSERT INTO positions (
                signal_id, symbol, exchange, side, quantity,
                entry_price, stop_loss_price, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        cursor = self._local.cursor()
        cursor.execute(query, (
            position_data.get('signal_id'),
            position_data['symbol'],
            position_data['exchange'],
            position_data['side'],
            position_data['quantity'],
            position_data['entry_price'],
            position_data.get('stop_loss_price'),
            position_data.get('status', 'pending'),
            datetime.now()
        ))
        self._local.commit()

        return cursor.lastrowid

    async def update_position(self, position_id: int, **updates):
        """Update position with given fields"""
        # Build UPDATE query dynamically
        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values())
        values.append(position_id)

        query = f"""
            UPDATE positions
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """

        cursor = self._local.cursor()
        cursor.execute(query, values)
        self._local.commit()

        return cursor.rowcount > 0

    async def get_position(self, position_id: int) -> Optional[Dict]:
        """Get position by ID"""
        cursor = self._local.cursor()
        cursor.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    async def get_active_positions(self, exchange: Optional[str] = None) -> List[Dict]:
        """Get all active positions"""
        query = "SELECT * FROM positions WHERE status = 'active'"
        params = []

        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)

        query += " ORDER BY opened_at DESC"

        cursor = self._local.cursor()
        cursor.execute(query, params)

        return [dict(row) for row in cursor.fetchall()]

    async def get_positions_by_status(self, statuses: List[str]) -> List[Dict]:
        """Get positions by status list"""
        placeholders = ','.join(['?' for _ in statuses])
        query = f"""
            SELECT * FROM positions
            WHERE status IN ({placeholders})
            ORDER BY created_at DESC
        """

        cursor = self._local.cursor()
        cursor.execute(query, statuses)

        return [dict(row) for row in cursor.fetchall()]

    # ============== Order Operations ==============

    async def create_order(self, order_data: Dict) -> int:
        """Create order record"""
        query = """
            INSERT INTO orders (
                position_id, exchange, symbol, order_id, type,
                side, size, price, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        cursor = self._local.cursor()
        cursor.execute(query, (
            order_data.get('position_id'),
            order_data['exchange'],
            order_data['symbol'],
            order_data['order_id'],
            order_data['type'],
            order_data['side'],
            order_data.get('size'),
            order_data.get('price'),
            order_data['status'],
            datetime.now()
        ))
        self._local.commit()

        return cursor.lastrowid

    async def update_order(self, order_id: str, **updates):
        """Update order by exchange order_id"""
        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values())
        values.append(order_id)

        query = f"""
            UPDATE orders
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
        """

        cursor = self._local.cursor()
        cursor.execute(query, values)
        self._local.commit()

        return cursor.rowcount > 0

    # ============== Event Logging ==============

    async def log_event(self, event_type: str, event_data: Dict, **metadata):
        """Log event to database"""
        query = """
            INSERT INTO event_log (
                event_type, event_data, correlation_id, position_id,
                signal_id, symbol, exchange, severity, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        cursor = self._local.cursor()
        cursor.execute(query, (
            event_type,
            json.dumps(event_data),
            metadata.get('correlation_id'),
            metadata.get('position_id'),
            metadata.get('signal_id'),
            metadata.get('symbol'),
            metadata.get('exchange'),
            metadata.get('severity', 'INFO'),
            datetime.now()
        ))
        self._local.commit()

    # ============== Helper Methods ==============

    async def execute_query(self, query: str, params: tuple = None):
        """Execute arbitrary query"""
        cursor = self._local.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        self._local.commit()

        return cursor

    async def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Fetch single row"""
        cursor = self._local.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Fetch all rows"""
        cursor = self._local.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        return [dict(row) for row in cursor.fetchall()]


# Singleton instance for easy access
_repository_instance = None

async def get_repository() -> SQLiteRepository:
    """Get or create repository instance"""
    global _repository_instance
    if not _repository_instance:
        _repository_instance = SQLiteRepository()
        await _repository_instance.initialize()
    return _repository_instance