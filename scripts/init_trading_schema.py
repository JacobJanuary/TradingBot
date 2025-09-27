#!/usr/bin/env python3
"""Initialize trading bot database schema"""

import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection parameters
DB_PARAMS = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5433'),
    'database': os.getenv('DB_NAME', 'fox_crypto'),
    'user': os.getenv('DB_USER', 'elcrypto'),
    'password': os.getenv('DB_PASSWORD', 'LohNeMamont@!21')
}

def init_schema():
    """Initialize trading bot schema and tables"""
    
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Create schema if not exists
        cur.execute("CREATE SCHEMA IF NOT EXISTS trading_bot")
        
        # Create positions table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.positions (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(50) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                entry_price DECIMAL(20, 8) NOT NULL,
                current_price DECIMAL(20, 8),
                quantity DECIMAL(20, 8) NOT NULL,
                leverage INTEGER DEFAULT 1,
                stop_loss DECIMAL(20, 8),
                take_profit DECIMAL(20, 8),
                status VARCHAR(20) NOT NULL DEFAULT 'open',
                pnl DECIMAL(20, 8),
                pnl_percentage DECIMAL(10, 4),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                closed_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT chk_side CHECK (side IN ('buy', 'sell')),
                CONSTRAINT chk_status CHECK (status IN ('open', 'closed', 'pending'))
            )
        """)
        
        # Create orders table  
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.orders (
                id SERIAL PRIMARY KEY,
                position_id INTEGER REFERENCES trading_bot.positions(id),
                exchange VARCHAR(50) NOT NULL,
                order_id VARCHAR(100) UNIQUE NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                order_type VARCHAR(20) NOT NULL,
                quantity DECIMAL(20, 8) NOT NULL,
                price DECIMAL(20, 8),
                status VARCHAR(20) NOT NULL,
                filled_quantity DECIMAL(20, 8) DEFAULT 0,
                average_price DECIMAL(20, 8),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT chk_side CHECK (side IN ('buy', 'sell')),
                CONSTRAINT chk_type CHECK (order_type IN ('market', 'limit', 'stop', 'stop_market'))
            )
        """)
        
        # Create signals table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.signals (
                id SERIAL PRIMARY KEY,
                source VARCHAR(50) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                action VARCHAR(20) NOT NULL,
                score INTEGER,
                entry_price DECIMAL(20, 8),
                stop_loss DECIMAL(20, 8),
                take_profit DECIMAL(20, 8),
                processed BOOLEAN DEFAULT FALSE,
                position_id INTEGER REFERENCES trading_bot.positions(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                processed_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT chk_action CHECK (action IN ('buy', 'sell', 'close'))
            )
        """)
        
        # Create performance table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.performance (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL UNIQUE,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl DECIMAL(20, 8) DEFAULT 0,
                win_rate DECIMAL(5, 2),
                avg_win DECIMAL(20, 8),
                avg_loss DECIMAL(20, 8),
                max_drawdown DECIMAL(10, 4),
                sharpe_ratio DECIMAL(10, 4),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        # Create risk_metrics table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.risk_metrics (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                open_positions INTEGER DEFAULT 0,
                total_exposure DECIMAL(20, 8) DEFAULT 0,
                portfolio_value DECIMAL(20, 8) DEFAULT 0,
                daily_pnl DECIMAL(20, 8) DEFAULT 0,
                var_95 DECIMAL(20, 8),
                correlation_score DECIMAL(5, 4),
                risk_score INTEGER
            )
        """)
        
        # Create indices
        cur.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON trading_bot.positions(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol ON trading_bot.positions(symbol)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON trading_bot.orders(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_processed ON trading_bot.signals(processed)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_performance_date ON trading_bot.performance(date)")
        
        conn.commit()
        print("✅ Trading bot schema initialized successfully!")
        
        # Show created tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'trading_bot'
            ORDER BY table_name
        """)
        
        tables = cur.fetchall()
        print(f"\nCreated {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error initializing schema: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_schema()