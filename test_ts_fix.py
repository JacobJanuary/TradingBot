#!/usr/bin/env python3
"""Test TS initialization fix for ATOMIC path"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

async def monitor_new_positions():
    # Load environment variables
    load_dotenv()

    # Get DB credentials from .env
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', '5433'))
    db_name = os.getenv('DB_NAME', 'fox_crypto_test')
    db_user = os.getenv('DB_USER', 'elcrypto')
    db_password = os.getenv('DB_PASSWORD')

    print("🔍 Monitoring for new positions to test TS initialization fix...")
    print(f"Connected to {db_name} at {db_host}:{db_port}\n")

    # Connect to database
    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password
    )

    try:
        # Get current max ID
        max_id_before = await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM monitoring.positions")
        print(f"📊 Current max position ID: {max_id_before}")
        print(f"📊 Waiting for new positions (ID > {max_id_before})...\n")

        # Get current count
        count_before = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN has_trailing_stop = true THEN 1 END) as with_ts,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active
            FROM monitoring.positions
        """)

        print("📊 BEFORE (current state):")
        print(f"  Total positions: {count_before['total']}")
        print(f"  With TS: {count_before['with_ts']}")
        print(f"  Active: {count_before['active']}\n")

        print("⏳ Waiting for next position to open...")
        print("   (Press Ctrl+C to stop)\n")

        last_check_time = datetime.now()
        check_interval = 5  # Check every 5 seconds

        while True:
            await asyncio.sleep(check_interval)

            # Check for new positions
            new_positions = await conn.fetch("""
                SELECT
                    id,
                    symbol,
                    exchange,
                    status,
                    entry_price,
                    has_trailing_stop,
                    trailing_activated,
                    created_at
                FROM monitoring.positions
                WHERE id > $1
                ORDER BY id DESC
            """, max_id_before)

            if new_positions:
                print("\n" + "=" * 80)
                print("✨ NEW POSITION(S) DETECTED!")
                print("=" * 80 + "\n")

                for pos in new_positions:
                    ts_status = "✅ TRUE" if pos['has_trailing_stop'] else "❌ FALSE"
                    ts_active = "✅ TRUE" if pos['trailing_activated'] else "❌ FALSE"

                    print(f"📍 Position #{pos['id']}: {pos['symbol']} ({pos['exchange']})")
                    print(f"   Status: {pos['status']}")
                    print(f"   Entry Price: ${pos['entry_price']}")
                    print(f"   has_trailing_stop: {ts_status}")
                    print(f"   trailing_activated: {ts_active}")
                    print(f"   Created: {pos['created_at']}\n")

                    # Verdict
                    if pos['has_trailing_stop']:
                        print(f"   ✅ TEST PASSED: TS initialized for {pos['symbol']}!")
                    else:
                        print(f"   ❌ TEST FAILED: TS NOT initialized for {pos['symbol']}!")

                    print()

                # Update max_id
                max_id_before = new_positions[0]['id']

                # Get updated stats
                count_after = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN has_trailing_stop = true THEN 1 END) as with_ts,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active
                    FROM monitoring.positions
                """)

                print("📊 AFTER (updated state):")
                print(f"  Total positions: {count_after['total']} (+{count_after['total'] - count_before['total']})")
                print(f"  With TS: {count_after['with_ts']} (+{count_after['with_ts'] - count_before['with_ts']})")
                print(f"  Active: {count_after['active']} (+{count_after['active'] - count_before['active']})\n")

                print("⏳ Waiting for next position...\n")

            # Periodic status update
            elapsed = (datetime.now() - last_check_time).total_seconds()
            if elapsed > 60:  # Every minute
                print(f"⏰ Still monitoring... (last check: {datetime.now().strftime('%H:%M:%S')})")
                last_check_time = datetime.now()

    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()
        print("\n✅ Test monitoring completed")

if __name__ == '__main__':
    asyncio.run(monitor_new_positions())
