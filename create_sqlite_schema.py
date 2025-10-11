#!/usr/bin/env python3
"""
Create SQLite database schema for testing
Mirrors the PostgreSQL schema from database/init.sql
"""
import sqlite3
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_schema():
    """Create SQLite database with tables matching PostgreSQL schema"""

    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()

    try:
        # Create positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL,
                stop_loss_price REAL,
                take_profit_price REAL,
                unrealized_pnl REAL,
                realized_pnl REAL,
                fees REAL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                exit_reason TEXT,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                leverage REAL DEFAULT 1.0,
                stop_loss REAL,
                take_profit REAL,
                pnl REAL,
                pnl_percentage REAL,
                trailing_activated BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ Created positions table")

        # Create orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                order_id TEXT,
                client_order_id TEXT,
                type TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL,
                price REAL,
                status TEXT NOT NULL,
                filled REAL DEFAULT 0,
                remaining REAL,
                fee REAL,
                fee_currency TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ Created orders table")

        # Create trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT,
                quantity REAL,
                price REAL,
                executed_qty REAL,
                average_price REAL,
                order_id TEXT,
                client_order_id TEXT,
                status TEXT,
                fee REAL,
                fee_currency TEXT,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ Created trades table")

        # Create event_log table for EventLogger
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_data TEXT,
                correlation_id TEXT,
                position_id INTEGER,
                signal_id INTEGER,
                symbol TEXT,
                exchange TEXT,
                severity TEXT DEFAULT 'INFO',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ Created event_log table")

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_position ON orders(position_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type)')

        logger.info("✅ Created indexes")

        conn.commit()
        logger.info("✅ Database schema created successfully")

        # Show tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        logger.info(f"Tables in database: {[t[0] for t in tables]}")

    except Exception as e:
        logger.error(f"❌ Error creating schema: {e}")
        conn.rollback()

    finally:
        conn.close()


if __name__ == "__main__":
    create_schema()