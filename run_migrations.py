#!/usr/bin/env python3
"""
Task 2.2: Apply database migrations
Wrapper around apply_migrations.py that uses Config class
"""
import asyncio
import asyncpg
import logging
from config.settings import Config

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import migration functions
import sys
sys.path.append('database/migrations')
from apply_migrations import (
    create_migrations_table,
    migration_001_expand_exit_reason,
    migration_002_add_event_log,
    migration_003_add_sync_tracking
)

async def apply_all_migrations():
    """Apply all pending migrations using Config class"""

    print("=" * 70)
    print("Task 2.2: Applying Database Migrations")
    print("=" * 70)

    # Load config
    config = Config()
    db = config.database

    print(f"\n📊 Connecting to: {db.host}:{db.port}/{db.database}")

    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=db.host,
            port=db.port,
            database=db.database,
            user=db.user,
            password=db.password
        )

        print("✅ Connected successfully\n")

        # Create migrations table
        logger.info("Creating migrations tracking table...")
        await create_migrations_table(conn)

        # List of migrations to apply
        migrations = [
            ("001_expand_exit_reason", migration_001_expand_exit_reason),
            ("002_add_event_log", migration_002_add_event_log),
            ("003_add_sync_tracking", migration_003_add_sync_tracking)
        ]

        print("=" * 70)
        print("APPLYING MIGRATIONS")
        print("=" * 70)

        # Apply each migration
        for name, migration_func in migrations:
            print(f"\n📋 Migration: {name}")
            await migration_func(conn)

        # Show migration status
        applied = await conn.fetch("""
            SELECT migration_name, applied_at
            FROM monitoring.schema_migrations
            ORDER BY applied_at ASC
        """)

        print("\n" + "=" * 70)
        print("📋 MIGRATION STATUS")
        print("=" * 70)

        for m in applied:
            print(f"  ✅ {m['migration_name']}")
            print(f"     Applied: {m['applied_at']}")

        print("\n" + "=" * 70)
        print("✅ ALL MIGRATIONS COMPLETED SUCCESSFULLY")
        print("=" * 70)

        await conn.close()
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        print("\n" + "=" * 70)
        print("❌ MIGRATION FAILED")
        print("=" * 70)
        print(f"\nError: {e}")
        print("\n🔄 Rollback instructions:")
        print("   1. Restore from backup:")
        print("      psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test < backup_monitoring_20251012_034548.sql")
        print("   2. Or recreate manually from backup file")
        return False

if __name__ == "__main__":
    import sys
    success = asyncio.run(apply_all_migrations())
    sys.exit(0 if success else 1)
