#!/usr/bin/env python3
"""Run migration 003_cleanup_fas_signals.sql"""
import asyncio
import asyncpg
from config.settings import Config
from pathlib import Path

async def main():
    settings = Config()
    migration_file = Path(__file__).parent / 'database' / 'migrations' / '003_cleanup_fas_signals.sql'

    print("=" * 60)
    print("Running Migration: 003_cleanup_fas_signals")
    print("=" * 60)

    # Read migration SQL
    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=settings.database.host,
            port=settings.database.port,
            user=settings.database.user,
            password=settings.database.password,
            database=settings.database.database
        )
        print("✅ Connected to database")

        # Execute migration
        print("\nExecuting migration SQL...")
        await conn.execute(migration_sql)

        print("\n✅ Migration completed successfully!")

        # Verify changes
        print("\nVerifying changes:")
        result = await conn.fetch("""
            SELECT
                table_name,
                column_name,
                data_type,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name IN ('positions', 'trades')
            AND column_name = 'signal_id'
            ORDER BY table_name
        """)

        for row in result:
            print(f"  {row['table_name']}.{row['column_name']}: {row['data_type']}")

        await conn.close()

    except Exception as e:
        print(f"\n❌ Migration FAILED: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
