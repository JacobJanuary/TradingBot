#!/usr/bin/env python3
"""
Apply database migrations to PostgreSQL
Handles schema updates and data migrations
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


async def create_migrations_table(conn):
    """Create migrations tracking table"""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS monitoring.schema_migrations (
            id SERIAL PRIMARY KEY,
            migration_name VARCHAR(255) UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)


async def is_migration_applied(conn, migration_name: str) -> bool:
    """Check if migration was already applied"""
    result = await conn.fetchval("""
        SELECT COUNT(*)
        FROM monitoring.schema_migrations
        WHERE migration_name = $1
    """, migration_name)
    return result > 0


async def record_migration(conn, migration_name: str):
    """Record that migration was applied"""
    await conn.execute("""
        INSERT INTO monitoring.schema_migrations (migration_name)
        VALUES ($1)
        ON CONFLICT (migration_name) DO NOTHING
    """, migration_name)


async def migration_001_expand_exit_reason(conn):
    """Expand exit_reason field to TEXT for full error messages"""
    migration_name = "001_expand_exit_reason"

    if await is_migration_applied(conn, migration_name):
        logger.info(f"⏭️ Migration {migration_name} already applied")
        return

    logger.info(f"🔄 Applying migration: {migration_name}")

    # Change exit_reason to TEXT
    await conn.execute("""
        ALTER TABLE monitoring.positions
        ALTER COLUMN exit_reason TYPE TEXT
    """)

    # Add audit fields
    await conn.execute("""
        ALTER TABLE monitoring.positions
        ADD COLUMN IF NOT EXISTS error_details JSONB,
        ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMP
    """)

    # Create index for error analysis
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_exit_reason
        ON monitoring.positions(exit_reason)
        WHERE exit_reason IS NOT NULL
    """)

    await record_migration(conn, migration_name)
    logger.info(f"✅ Migration {migration_name} completed")


async def migration_002_add_event_log(conn):
    """Add event_log table for comprehensive audit trail"""
    migration_name = "002_add_event_log"

    if await is_migration_applied(conn, migration_name):
        logger.info(f"⏭️ Migration {migration_name} already applied")
        return

    logger.info(f"🔄 Applying migration: {migration_name}")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS monitoring.event_log (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB,
            correlation_id VARCHAR(100),
            position_id INTEGER,
            signal_id INTEGER,
            symbol VARCHAR(50),
            exchange VARCHAR(50),
            severity VARCHAR(20) DEFAULT 'INFO',
            timestamp TIMESTAMP DEFAULT NOW(),

            -- Indexes
            CONSTRAINT fk_position
                FOREIGN KEY(position_id)
                REFERENCES monitoring.positions(id)
                ON DELETE CASCADE
        )
    """)

    # Create indexes
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_log_type
        ON monitoring.event_log(event_type);

        CREATE INDEX IF NOT EXISTS idx_event_log_timestamp
        ON monitoring.event_log(timestamp DESC);

        CREATE INDEX IF NOT EXISTS idx_event_log_position
        ON monitoring.event_log(position_id)
        WHERE position_id IS NOT NULL;
    """)

    await record_migration(conn, migration_name)
    logger.info(f"✅ Migration {migration_name} completed")


async def migration_003_add_sync_tracking(conn):
    """Add fields for position synchronization tracking"""
    migration_name = "003_add_sync_tracking"

    if await is_migration_applied(conn, migration_name):
        logger.info(f"⏭️ Migration {migration_name} already applied")
        return

    logger.info(f"🔄 Applying migration: {migration_name}")

    # Add sync tracking fields
    await conn.execute("""
        ALTER TABLE monitoring.positions
        ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS sync_status VARCHAR(50),
        ADD COLUMN IF NOT EXISTS exchange_order_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS sl_order_id VARCHAR(100)
    """)

    # Add sync status table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS monitoring.sync_status (
            id SERIAL PRIMARY KEY,
            exchange VARCHAR(50) NOT NULL,
            last_sync_at TIMESTAMP,
            positions_synced INTEGER DEFAULT 0,
            discrepancies_found INTEGER DEFAULT 0,
            auto_fixed INTEGER DEFAULT 0,
            status VARCHAR(50),
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    await record_migration(conn, migration_name)
    logger.info(f"✅ Migration {migration_name} completed")


async def apply_all_migrations():
    """Apply all pending migrations"""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not found in environment")

    conn = await asyncpg.connect(db_url)

    try:
        # Create migrations table
        await create_migrations_table(conn)

        # List of migrations to apply
        migrations = [
            migration_001_expand_exit_reason,
            migration_002_add_event_log,
            migration_003_add_sync_tracking
        ]

        # Apply each migration
        for migration_func in migrations:
            await migration_func(conn)

        # Show migration status
        applied = await conn.fetch("""
            SELECT migration_name, applied_at
            FROM monitoring.schema_migrations
            ORDER BY applied_at DESC
        """)

        logger.info("\n📋 Applied migrations:")
        for m in applied:
            logger.info(f"  ✓ {m['migration_name']} - {m['applied_at']}")

        logger.info(f"\n✅ All migrations completed successfully!")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(apply_all_migrations())