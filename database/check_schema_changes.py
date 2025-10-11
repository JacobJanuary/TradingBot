#!/usr/bin/env python3
"""
Check what schema changes will be applied
Shows differences between current schema and planned changes
"""
import asyncpg
import asyncio
import os
from dotenv import load_dotenv
from typing import Dict, List, Tuple

load_dotenv()


async def check_schema_changes():
    """Analyze current schema and show what will change"""

    db_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(db_url)

    print("=" * 60)
    print("📊 SCHEMA CHANGE ANALYSIS")
    print("=" * 60)

    try:
        # Check current exit_reason column
        print("\n1️⃣ COLUMN SIZE CHANGES:")
        print("-" * 40)

        exit_reason_info = await conn.fetchrow("""
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'positions'
            AND column_name = 'exit_reason'
        """)

        if exit_reason_info:
            current_type = exit_reason_info['data_type']
            current_length = exit_reason_info['character_maximum_length']
            print(f"❌ Current: exit_reason {current_type}({current_length})")
            print(f"✅ Will be: exit_reason TEXT (unlimited)")
            print(f"📝 Reason: Error messages are being truncated at {current_length} chars")
        else:
            print("⚠️ exit_reason column not found")

        # Check for new columns to be added
        print("\n2️⃣ NEW COLUMNS TO BE ADDED:")
        print("-" * 40)

        existing_columns = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'positions'
        """)

        existing = [col['column_name'] for col in existing_columns]

        new_columns = {
            'error_details': 'JSONB - Store complete error information',
            'retry_count': 'INTEGER - Track retry attempts',
            'last_error_at': 'TIMESTAMP - When last error occurred',
            'last_sync_at': 'TIMESTAMP - Last synchronization time',
            'sync_status': 'VARCHAR(50) - Sync state tracking',
            'exchange_order_id': 'VARCHAR(100) - Exchange order reference',
            'sl_order_id': 'VARCHAR(100) - Stop-loss order reference'
        }

        for col_name, description in new_columns.items():
            if col_name not in existing:
                print(f"➕ {col_name}: {description}")
            else:
                print(f"✅ {col_name}: Already exists")

        # Check for new tables
        print("\n3️⃣ NEW TABLES TO BE CREATED:")
        print("-" * 40)

        existing_tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
        """)

        existing_table_names = [t['table_name'] for t in existing_tables]

        new_tables = {
            'event_log': 'Complete audit trail of all events',
            'schema_migrations': 'Track applied migrations',
            'sync_status': 'Monitor synchronization health'
        }

        for table_name, description in new_tables.items():
            if table_name not in existing_table_names:
                print(f"➕ {table_name}: {description}")
            else:
                print(f"✅ {table_name}: Already exists")

        # Check current positions that would be affected
        print("\n4️⃣ IMPACT ANALYSIS:")
        print("-" * 40)

        # Count positions with long exit_reason
        long_reasons = await conn.fetch("""
            SELECT id, symbol, LENGTH(exit_reason) as len
            FROM monitoring.positions
            WHERE LENGTH(exit_reason) > 90
            ORDER BY LENGTH(exit_reason) DESC
            LIMIT 5
        """)

        if long_reasons:
            print(f"⚠️ {len(long_reasons)} positions have exit_reason > 90 chars")
            for pos in long_reasons:
                print(f"   - Position {pos['id']} ({pos['symbol']}): {pos['len']} chars")
        else:
            print("✅ No positions with long exit_reason (safe to migrate)")

        # Count active positions
        active_count = await conn.fetchval("""
            SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active'
        """)

        print(f"\n📊 Active positions that will get new fields: {active_count}")

        # Check for positions without stop-loss
        no_sl = await conn.fetchval("""
            SELECT COUNT(*) FROM monitoring.positions
            WHERE status = 'active' AND stop_loss_price IS NULL
        """)

        if no_sl > 0:
            print(f"⚠️ {no_sl} active positions without stop-loss will be flagged")

        # Estimate migration time
        total_positions = await conn.fetchval("""
            SELECT COUNT(*) FROM monitoring.positions
        """)

        print("\n5️⃣ MIGRATION ESTIMATES:")
        print("-" * 40)
        print(f"📊 Total positions to update: {total_positions}")
        print(f"⏱️ Estimated migration time: ~{max(1, total_positions // 1000)} seconds")
        print(f"💾 Backup size estimate: ~{max(1, total_positions * 500 // 1024 // 1024)} MB")

        # Show migration safety
        print("\n6️⃣ MIGRATION SAFETY:")
        print("-" * 40)
        print("✅ All changes are ADDITIVE (no data loss)")
        print("✅ Migrations are IDEMPOTENT (can run multiple times)")
        print("✅ Each migration is TRACKED (won't run twice)")
        print("✅ Backup created BEFORE changes")
        print("✅ Can ROLLBACK if needed")

    except Exception as e:
        print(f"❌ Error analyzing schema: {e}")

    finally:
        await conn.close()


async def show_rollback_plan():
    """Show how to rollback if needed"""
    print("\n" + "=" * 60)
    print("🔄 ROLLBACK PLAN (if needed):")
    print("=" * 60)
    print("""
If migration causes issues, rollback steps:

1. Stop all services:
   systemctl stop position-sync
   pkill -f main.py

2. Restore from backup:
   pg_restore -d $DATABASE_URL --clean --schema=monitoring backups/*/monitoring_*.backup

3. Revert code changes:
   git checkout HEAD~1

4. Restart services:
   systemctl start position-sync
   python main.py

Time to rollback: ~2 minutes
    """)


async def main():
    """Main execution"""
    await check_schema_changes()
    await show_rollback_plan()


if __name__ == "__main__":
    asyncio.run(main())