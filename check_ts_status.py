#!/usr/bin/env python3
"""Check trailing_activated status for all positions"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

async def check_ts_status():
    # Load environment variables
    load_dotenv()

    # Get DB credentials from .env
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', '5433'))
    db_name = os.getenv('DB_NAME', 'fox_crypto_test')
    db_user = os.getenv('DB_USER', 'elcrypto')
    db_password = os.getenv('DB_PASSWORD')

    print(f"Connecting to {db_name} at {db_host}:{db_port} as {db_user}...")

    # Connect to database
    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password
    )

    try:
        # Get statistics
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_positions,
                COUNT(CASE WHEN trailing_activated = true THEN 1 END) as activated_ts,
                COUNT(CASE WHEN has_trailing_stop = true THEN 1 END) as initialized_ts,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_positions
            FROM monitoring.positions
        """)

        print("\n📊 СТАТИСТИКА:")
        print(f"  Всего позиций: {stats['total_positions']}")
        print(f"  Активных позиций: {stats['active_positions']}")
        print(f"  TS инициализирован (has_trailing_stop): {stats['initialized_ts']}")
        print(f"  TS активирован (trailing_activated): {stats['activated_ts']}")

        # Get positions with trailing_activated = true
        activated_positions = await conn.fetch("""
            SELECT
                symbol,
                exchange,
                status,
                entry_price,
                current_price,
                has_trailing_stop,
                trailing_activated,
                created_at
            FROM monitoring.positions
            WHERE trailing_activated = true
            ORDER BY created_at DESC
        """)

        print(f"\n✅ ПОЗИЦИИ С АКТИВИРОВАННЫМ TS (trailing_activated=true): {len(activated_positions)}")
        if activated_positions:
            for pos in activated_positions:
                print(f"  - {pos['symbol']:15} | {pos['exchange']:8} | {pos['status']:8} | "
                      f"Entry: ${pos['entry_price']:10.4f} | Current: ${pos['current_price']:10.4f} | "
                      f"Created: {pos['created_at']}")
        else:
            print("  (нет позиций с активированным TS)")

        # Get active positions
        active_positions = await conn.fetch("""
            SELECT
                symbol,
                exchange,
                status,
                entry_price,
                current_price,
                has_trailing_stop,
                trailing_activated,
                created_at
            FROM monitoring.positions
            WHERE status = 'active'
            ORDER BY created_at DESC
        """)

        print(f"\n📈 АКТИВНЫЕ ПОЗИЦИИ (status='active'): {len(active_positions)}")
        for pos in active_positions:
            ts_init = "✅" if pos['has_trailing_stop'] else "❌"
            ts_active = "✅" if pos['trailing_activated'] else "❌"
            print(f"  - {pos['symbol']:15} | {pos['exchange']:8} | "
                  f"Entry: ${pos['entry_price']:10.4f} | Current: ${pos['current_price']:10.4f} | "
                  f"TS_init: {ts_init} | TS_active: {ts_active} | "
                  f"Created: {pos['created_at']}")

    finally:
        await conn.close()
        print("\n✅ Проверка завершена")

if __name__ == '__main__':
    asyncio.run(check_ts_status())
