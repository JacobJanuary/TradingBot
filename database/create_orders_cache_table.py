#!/usr/bin/env python3
"""
Create orders cache table for solving Bybit 500 order limit issue

This cache stores all orders locally, allowing us to:
1. Fetch order details even when Bybit returns "500 orders limit" error
2. Provide historical order data for analysis
3. Reduce API calls to exchanges

Schema: monitoring.orders_cache
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_orders_cache_table():
    """Create orders cache table"""
    import asyncpg

    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://evgeniyyanvarskiy@localhost:5432/postgres')

    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Create monitoring schema if not exists
        await conn.execute("""
            CREATE SCHEMA IF NOT EXISTS monitoring;
        """)
        logger.info("Schema monitoring created/verified")

        # Create orders_cache table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS monitoring.orders_cache (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(50) NOT NULL,
                exchange_order_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                order_type VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                price DECIMAL(20, 8),
                amount DECIMAL(20, 8) NOT NULL,
                filled DECIMAL(20, 8) DEFAULT 0,
                status VARCHAR(20) NOT NULL,
                created_at TIMESTAMP NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                order_data JSONB,

                CONSTRAINT unique_exchange_order UNIQUE (exchange, exchange_order_id)
            );
        """)
        logger.info("✅ Table monitoring.orders_cache created/verified")

        # Create indexes for faster queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_cache_exchange_symbol
            ON monitoring.orders_cache(exchange, symbol);
        """)
        logger.info("✅ Index idx_orders_cache_exchange_symbol created")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_cache_created_at
            ON monitoring.orders_cache(created_at DESC);
        """)
        logger.info("✅ Index idx_orders_cache_created_at created")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_cache_order_id
            ON monitoring.orders_cache(exchange_order_id);
        """)
        logger.info("✅ Index idx_orders_cache_order_id created")

        logger.info("✅ Orders cache table setup complete!")

    except Exception as e:
        logger.error(f"❌ Failed to create orders_cache table: {e}")
        raise

    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(create_orders_cache_table())
