#!/usr/bin/env python3
"""Check has_trailing_stop status for active positions"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

async def check_active_positions_ts():
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
        # Get statistics for active positions
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_active,
                COUNT(CASE WHEN has_trailing_stop = true THEN 1 END) as ts_initialized,
                COUNT(CASE WHEN has_trailing_stop = false OR has_trailing_stop IS NULL THEN 1 END) as ts_not_initialized
            FROM monitoring.positions
            WHERE status = 'active'
        """)

        print("\n📊 СТАТИСТИКА АКТИВНЫХ ПОЗИЦИЙ:")
        print(f"  Всего активных: {stats['total_active']}")
        print(f"  has_trailing_stop = TRUE: {stats['ts_initialized']}")
        print(f"  has_trailing_stop = FALSE/NULL: {stats['ts_not_initialized']}")

        if stats['ts_not_initialized'] > 0:
            print(f"\n⚠️  ПРОБЛЕМА: {stats['ts_not_initialized']} активных позиций БЕЗ инициализированного TS!")
        else:
            print(f"\n✅ ВСЕ активные позиции имеют has_trailing_stop = TRUE")

        # Get detailed list of active positions
        active_positions = await conn.fetch("""
            SELECT
                id,
                symbol,
                exchange,
                side,
                entry_price,
                current_price,
                has_trailing_stop,
                trailing_activated,
                created_at
            FROM monitoring.positions
            WHERE status = 'active'
            ORDER BY has_trailing_stop NULLS FIRST, created_at DESC
        """)

        print(f"\n📋 ДЕТАЛЬНЫЙ СПИСОК АКТИВНЫХ ПОЗИЦИЙ ({len(active_positions)}):\n")
        print(f"{'ID':<6} {'Symbol':<15} {'Exchange':<10} {'TS Init':<10} {'TS Active':<10} {'Created':<20}")
        print("=" * 80)

        for pos in active_positions:
            ts_init = "✅ TRUE" if pos['has_trailing_stop'] else "❌ FALSE"
            ts_active = "✅ TRUE" if pos['trailing_activated'] else "❌ FALSE"
            created = pos['created_at'].strftime('%Y-%m-%d %H:%M:%S') if pos['created_at'] else 'N/A'

            print(f"{pos['id']:<6} {pos['symbol']:<15} {pos['exchange']:<10} {ts_init:<10} {ts_active:<10} {created:<20}")

        # Get positions WITHOUT has_trailing_stop
        positions_without_ts = await conn.fetch("""
            SELECT
                id,
                symbol,
                exchange,
                entry_price,
                created_at
            FROM monitoring.positions
            WHERE status = 'active'
              AND (has_trailing_stop = false OR has_trailing_stop IS NULL)
            ORDER BY created_at DESC
        """)

        if positions_without_ts:
            print(f"\n🚨 ПОЗИЦИИ БЕЗ ИНИЦИАЛИЗИРОВАННОГО TS ({len(positions_without_ts)}):\n")
            for pos in positions_without_ts:
                created = pos['created_at'].strftime('%Y-%m-%d %H:%M:%S') if pos['created_at'] else 'N/A'
                print(f"  ID: {pos['id']:<6} | {pos['symbol']:<15} | {pos['exchange']:<10} | Created: {created}")

        # Check if TS should be initialized based on research
        print("\n\n🔍 ПРОВЕРКА СООТВЕТСТВИЯ ОЖИДАНИЯМ:")
        print("=" * 80)
        print("Согласно исследованию TS_AUTOMATIC_ACTIVATION_LOGIC_DEEP_RESEARCH.md:")
        print("  - ВСЕ позиции должны иметь has_trailing_stop = TRUE при открытии")
        print("  - TS инициализируется в core/position_manager.py:832-849 (open_position)")
        print("  - TS инициализируется в core/position_manager.py:410-434 (load_positions_from_db)")

        if stats['ts_not_initialized'] > 0:
            print(f"\n❌ НЕСООТВЕТСТВИЕ: {stats['ts_not_initialized']} активных позиций БЕЗ TS!")
            print("\nВозможные причины:")
            print("  1. Позиции открыты до внедрения фикса has_trailing_stop persistence")
            print("  2. Бот не был перезапущен после внедрения фикса")
            print("  3. Ошибка в логике инициализации TS")
            print("\nРешение:")
            print("  - Перезапустить бота → load_positions_from_db() инициализирует TS для всех")
        else:
            print(f"\n✅ СООТВЕТСТВИЕ: ВСЕ {stats['total_active']} активных позиций имеют TS!")

    finally:
        await conn.close()
        print("\n✅ Проверка завершена")

if __name__ == '__main__':
    asyncio.run(check_active_positions_ts())
