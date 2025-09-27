#!/usr/bin/env python3
"""
Create missing database tables for trading bot
"""
import asyncio
import logging
from datetime import datetime
import asyncpg
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_tables():
    """Create all missing tables"""
    
    # Database connection
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://evgeniyyanvarskiy@localhost:5432/postgres')
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Create schema if not exists
        await conn.execute("""
            CREATE SCHEMA IF NOT EXISTS trading_bot;
        """)
        logger.info("Schema trading_bot created/verified")
        
        # Create scoring_history table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.scoring_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(50) NOT NULL,
                exchange VARCHAR(50) NOT NULL,
                signal_type VARCHAR(20) NOT NULL,
                score_week FLOAT,
                score_month FLOAT,
                patterns_week TEXT,
                patterns_month TEXT,
                indicators_week TEXT,
                indicators_month TEXT,
                volume_profile JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Table scoring_history created/verified")
        
        # Create index for faster queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scoring_history_symbol_exchange 
            ON trading_bot.scoring_history(symbol, exchange);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scoring_history_created_at 
            ON trading_bot.scoring_history(created_at DESC);
        """)
        
        # Create positions table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.positions (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(50) NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                side VARCHAR(10) NOT NULL,
                contracts FLOAT NOT NULL,
                entry_price FLOAT NOT NULL,
                mark_price FLOAT,
                unrealized_pnl FLOAT,
                realized_pnl FLOAT DEFAULT 0,
                status VARCHAR(20) DEFAULT 'open',
                stop_loss FLOAT,
                take_profit FLOAT,
                trailing_stop_activated BOOLEAN DEFAULT FALSE,
                trailing_stop_price FLOAT,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Table positions created/verified")
        
        # Create trades table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.trades (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(50) NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                order_id VARCHAR(100) NOT NULL,
                side VARCHAR(10) NOT NULL,
                price FLOAT NOT NULL,
                amount FLOAT NOT NULL,
                cost FLOAT NOT NULL,
                fee FLOAT DEFAULT 0,
                fee_currency VARCHAR(20),
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Table trades created/verified")
        
        # Create orders table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.orders (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(50) NOT NULL,
                order_id VARCHAR(100) NOT NULL UNIQUE,
                symbol VARCHAR(50) NOT NULL,
                type VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                price FLOAT,
                amount FLOAT NOT NULL,
                filled FLOAT DEFAULT 0,
                remaining FLOAT,
                status VARCHAR(20) NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Table orders created/verified")
        
        # Create performance_metrics table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.performance_metrics (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(50) NOT NULL,
                total_pnl FLOAT DEFAULT 0,
                realized_pnl FLOAT DEFAULT 0,
                unrealized_pnl FLOAT DEFAULT 0,
                win_rate FLOAT DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                max_drawdown FLOAT DEFAULT 0,
                sharpe_ratio FLOAT DEFAULT 0,
                profit_factor FLOAT DEFAULT 0,
                total_balance FLOAT DEFAULT 0,
                free_balance FLOAT DEFAULT 0,
                used_balance FLOAT DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Table performance_metrics created/verified")
        
        # Create signals table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.signals (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(50) NOT NULL,
                exchange VARCHAR(50) NOT NULL,
                signal_type VARCHAR(20) NOT NULL,
                strength FLOAT NOT NULL,
                price FLOAT NOT NULL,
                volume FLOAT,
                metadata JSONB,
                executed BOOLEAN DEFAULT FALSE,
                execution_price FLOAT,
                execution_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Table signals created/verified")
        
        # Create health_checks table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_bot.health_checks (
                id SERIAL PRIMARY KEY,
                component VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL,
                message TEXT,
                details JSONB,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Table health_checks created/verified")
        
        # Add exchange_id and total_balance columns to existing tables if missing
        try:
            # Check if columns exist
            result = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'trading_bot' 
                AND table_name = 'performance_metrics'
            """)
            
            columns = [row['column_name'] for row in result]
            
            if 'exchange_id' not in columns:
                await conn.execute("""
                    ALTER TABLE trading_bot.performance_metrics 
                    ADD COLUMN IF NOT EXISTS exchange_id VARCHAR(50);
                """)
                logger.info("Added exchange_id column to performance_metrics")
            
        except Exception as e:
            logger.warning(f"Could not check/add columns: {e}")
        
        logger.info("✅ All tables created/verified successfully!")
        
        # Show all tables
        result = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'trading_bot'
            ORDER BY table_name;
        """)
        
        logger.info("\nTables in trading_bot schema:")
        for row in result:
            logger.info(f"  - {row['table_name']}")
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_tables())