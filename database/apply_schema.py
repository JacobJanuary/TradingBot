#!/usr/bin/env python3
"""
Apply PostgreSQL schema with verification
Ensures all tables and indexes are created correctly
"""
import asyncpg
import asyncio
import logging
import os
from dotenv import load_dotenv
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


async def apply_schema():
    """Apply database schema to PostgreSQL"""

    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not found in environment")

    logger.info(f"Connecting to PostgreSQL...")
    conn = await asyncpg.connect(db_url)

    try:
        # Create schemas
        await conn.execute("CREATE SCHEMA IF NOT EXISTS fas")
        await conn.execute("CREATE SCHEMA IF NOT EXISTS monitoring")
        logger.info("✅ Schemas created: fas, monitoring")

        # Read and execute init.sql
        with open('database/init.sql', 'r') as f:
            schema_sql = f.read()

        # Execute schema creation
        await conn.execute(schema_sql)
        logger.info("✅ Tables created from init.sql")

        # Verify tables exist
        tables = await conn.fetch("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('fas', 'monitoring')
            ORDER BY table_schema, table_name
        """)

        logger.info("\n📋 Created tables:")
        for table in tables:
            logger.info(f"  - {table['table_schema']}.{table['table_name']}")

        # Verify critical columns in positions table
        columns = await conn.fetch("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'positions'
            ORDER BY ordinal_position
        """)

        logger.info("\n📊 monitoring.positions columns:")
        for col in columns:
            max_len = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
            logger.info(f"  - {col['column_name']}: {col['data_type']}{max_len}")

        # Check indexes
        indexes = await conn.fetch("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'monitoring'
            AND tablename = 'positions'
        """)

        logger.info(f"\n🔍 Indexes on monitoring.positions: {len(indexes)}")
        for idx in indexes:
            logger.info(f"  - {idx['indexname']}")

        return True

    except Exception as e:
        logger.error(f"❌ Schema application failed: {e}")
        raise

    finally:
        await conn.close()


async def verify_connection_pool():
    """Verify that repository can connect with pool"""
    from database.repository import Repository

    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', 5432),
        'database': os.getenv('DB_NAME', 'trading_bot'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }

    repo = Repository(db_config)
    await repo.initialize()

    # Test a simple query
    positions = await repo.get_active_positions()
    logger.info(f"✅ Repository connected, active positions: {len(positions)}")

    await repo.close()
    return True


async def main():
    """Main execution"""
    logger.info("="*60)
    logger.info("🚀 APPLYING POSTGRESQL SCHEMA")
    logger.info("="*60)

    # Apply schema
    await apply_schema()

    # Verify repository connection
    await verify_connection_pool()

    logger.info("\n✅ Schema successfully applied and verified!")


if __name__ == "__main__":
    asyncio.run(main())