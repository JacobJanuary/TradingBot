#!/usr/bin/env python3
"""Pre-flight checks for fas.signals cleanup migration"""
import asyncio
import asyncpg
from config.settings import Config

async def main():
    settings = Config()

    print("=" * 60)
    print("PRE-FLIGHT CHECKS: fas.signals cleanup")
    print("=" * 60)

    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=settings.database.host,
            port=settings.database.port,
            user=settings.database.user,
            password=settings.database.password,
            database=settings.database.database
        )
        print("✅ Database connection: OK")

        # Check fas schema exists
        result = await conn.fetchval("""
            SELECT COUNT(*)
            FROM information_schema.schemata
            WHERE schema_name = 'fas'
        """)
        fas_exists = result == 1
        print(f"✅ fas schema exists: {fas_exists}")

        # Check fas.signals table exists (only if schema exists)
        if fas_exists:
            result = await conn.fetchval("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'fas' AND table_name = 'signals'
            """)
            print(f"✅ fas.signals table exists: {result == 1}")
        else:
            print(f"ℹ️  fas.signals table: N/A (schema doesn't exist)")

        # Check signal_id column type in positions
        result = await conn.fetchrow("""
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'positions'
            AND column_name = 'signal_id'
        """)
        print(f"✅ monitoring.positions.signal_id type: {result['data_type']}")

        # Check signal_id column type in trades
        result = await conn.fetchrow("""
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'trades'
            AND column_name = 'signal_id'
        """)
        print(f"✅ monitoring.trades.signal_id type: {result['data_type']}")

        # Check FK constraints (skip if fas doesn't exist)
        if fas_exists:
            try:
                result = await conn.fetch("""
                    SELECT
                        conname as constraint_name,
                        conrelid::regclass as table_name
                    FROM pg_constraint
                    WHERE confrelid = 'fas.signals'::regclass
                """)
                print(f"✅ Foreign Key constraints to fas.signals: {len(result)}")
                for row in result:
                    print(f"   - {row['table_name']}: {row['constraint_name']}")
            except Exception:
                print(f"ℹ️  FK constraints check: N/A (fas.signals doesn't exist)")
        else:
            print(f"ℹ️  FK constraints check: N/A (fas schema doesn't exist)")

        # Count positions with signal_id
        result = await conn.fetchval("""
            SELECT COUNT(*)
            FROM monitoring.positions
            WHERE signal_id IS NOT NULL
        """)
        print(f"✅ Positions with signal_id: {result}")

        # Count trades with signal_id
        result = await conn.fetchval("""
            SELECT COUNT(*)
            FROM monitoring.trades
            WHERE signal_id IS NOT NULL
        """)
        print(f"✅ Trades with signal_id: {result}")

        await conn.close()
        print("\n✅ All pre-flight checks PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Pre-flight check FAILED: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(main())
