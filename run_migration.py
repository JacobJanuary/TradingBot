#!/usr/bin/env python3
"""Execute SL Conflict DB Migration"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os
from datetime import datetime

async def run_migration():
    # Load environment variables
    load_dotenv()

    # Get DB credentials from .env
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', '5433'))
    db_name = os.getenv('DB_NAME', 'fox_crypto_test')
    db_user = os.getenv('DB_USER', 'elcrypto')
    db_password = os.getenv('DB_PASSWORD')

    print(f"🔗 Connecting to {db_name} at {db_host}:{db_port} as {db_user}...")

    # Connect to database
    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password
    )

    try:
        print("\n" + "=" * 80)
        print("STEP 1: CREATE BACKUP (via Python)")
        print("=" * 80)

        # Count positions before migration
        count_before = await conn.fetchval("SELECT COUNT(*) FROM monitoring.positions")
        print(f"✅ Positions count before migration: {count_before}")

        # Note: Full pg_dump backup should be done externally
        # Here we just verify DB is accessible
        print("⚠️  Note: Full pg_dump backup recommended (done externally)")
        print("✅ Database connection verified")

        print("\n" + "=" * 80)
        print("STEP 2: ADD ts_last_update_time COLUMN")
        print("=" * 80)

        # Check if column already exists
        ts_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'monitoring'
                  AND table_name = 'positions'
                  AND column_name = 'ts_last_update_time'
            )
        """)

        if ts_exists:
            print("⚠️  Column ts_last_update_time already exists, skipping...")
        else:
            print("Adding column ts_last_update_time...")
            await conn.execute("""
                ALTER TABLE monitoring.positions
                ADD COLUMN ts_last_update_time TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL
            """)
            print("✅ Column ts_last_update_time added successfully")

        # Verify
        ts_check = await conn.fetchrow("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
              AND table_name = 'positions'
              AND column_name = 'ts_last_update_time'
        """)

        if ts_check:
            print(f"✅ Verified: {ts_check['column_name']} | {ts_check['data_type']} | nullable={ts_check['is_nullable']}")
        else:
            print("❌ ERROR: Column not found after creation!")
            return False

        print("\n" + "=" * 80)
        print("STEP 3: ADD sl_managed_by COLUMN")
        print("=" * 80)

        # Check if column already exists
        sl_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'monitoring'
                  AND table_name = 'positions'
                  AND column_name = 'sl_managed_by'
            )
        """)

        if sl_exists:
            print("⚠️  Column sl_managed_by already exists, skipping...")
        else:
            print("Adding column sl_managed_by...")
            await conn.execute("""
                ALTER TABLE monitoring.positions
                ADD COLUMN sl_managed_by VARCHAR(20) DEFAULT NULL
            """)
            print("✅ Column sl_managed_by added successfully")

        # Verify
        sl_check = await conn.fetchrow("""
            SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
              AND table_name = 'positions'
              AND column_name = 'sl_managed_by'
        """)

        if sl_check:
            print(f"✅ Verified: {sl_check['column_name']} | {sl_check['data_type']}({sl_check['character_maximum_length']}) | nullable={sl_check['is_nullable']}")
        else:
            print("❌ ERROR: Column not found after creation!")
            return False

        print("\n" + "=" * 80)
        print("STEP 4: VERIFY MIGRATION")
        print("=" * 80)

        # Count positions after migration
        count_after = await conn.fetchval("SELECT COUNT(*) FROM monitoring.positions")
        print(f"✅ Positions count after migration: {count_after}")

        if count_before != count_after:
            print(f"❌ ERROR: Position count changed! Before: {count_before}, After: {count_after}")
            return False
        else:
            print(f"✅ No data loss ({count_before} positions)")

        # Count total columns
        total_columns = await conn.fetchval("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
              AND table_name = 'positions'
        """)
        print(f"✅ Total columns in monitoring.positions: {total_columns}")

        # Check all TS fields
        ts_fields = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
              AND table_name = 'positions'
              AND column_name IN ('has_trailing_stop', 'trailing_activated', 'ts_last_update_time', 'sl_managed_by')
            ORDER BY column_name
        """)

        print("\n📊 All TS fields:")
        for field in ts_fields:
            print(f"  ✅ {field['column_name']:<25} | {field['data_type']:<30} | nullable={field['is_nullable']}")

        # Check that new fields are NULL for existing positions
        null_check = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(ts_last_update_time) as has_ts_time,
                COUNT(sl_managed_by) as has_sl_managed
            FROM monitoring.positions
        """)

        print(f"\n📊 New fields data check:")
        print(f"  Total positions: {null_check['total']}")
        print(f"  With ts_last_update_time: {null_check['has_ts_time']}")
        print(f"  With sl_managed_by: {null_check['has_sl_managed']}")

        if null_check['has_ts_time'] == 0 and null_check['has_sl_managed'] == 0:
            print(f"  ✅ All existing positions have NULL in new fields (correct)")
        else:
            print(f"  ⚠️  Some positions have non-NULL values (may be from previous test)")

        print("\n" + "=" * 80)
        print("STEP 5: TEST WRITE (OPTIONAL)")
        print("=" * 80)

        # Test write
        print("Creating test position...")
        test_id = await conn.fetchval("""
            INSERT INTO monitoring.positions (
                symbol, exchange, side, quantity, entry_price, status,
                has_trailing_stop, trailing_activated,
                ts_last_update_time, sl_managed_by
            ) VALUES (
                'TEST_MIGRATION_' || TO_CHAR(NOW(), 'YYYYMMDDHH24MISS'),
                'binance', 'long', 1.0, 100.0, 'active',
                true, false,
                NOW(), 'trailing_stop'
            ) RETURNING id
        """)

        print(f"✅ Test position created (id={test_id})")

        # Read back
        test_data = await conn.fetchrow("""
            SELECT symbol, ts_last_update_time, sl_managed_by
            FROM monitoring.positions
            WHERE id = $1
        """, test_id)

        print(f"✅ Test read successful:")
        print(f"  Symbol: {test_data['symbol']}")
        print(f"  ts_last_update_time: {test_data['ts_last_update_time']}")
        print(f"  sl_managed_by: {test_data['sl_managed_by']}")

        # Delete test
        await conn.execute("DELETE FROM monitoring.positions WHERE id = $1", test_id)
        print(f"✅ Test position deleted (id={test_id})")

        print("\n" + "=" * 80)
        print("🎉 MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"✅ Added 2 columns: ts_last_update_time, sl_managed_by")
        print(f"✅ Total columns: {total_columns}")
        print(f"✅ No data loss: {count_after} positions")
        print(f"✅ Test write/read: PASSED")
        print(f"✅ Ready for production use")

        return True

    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await conn.close()

if __name__ == '__main__':
    success = asyncio.run(run_migration())
    exit(0 if success else 1)
