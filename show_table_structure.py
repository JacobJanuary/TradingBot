#!/usr/bin/env python3
"""Show structure of monitoring.positions table"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

async def show_table_structure():
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
        # Get table structure
        columns = await conn.fetch("""
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'positions'
            ORDER BY ordinal_position
        """)

        print(f"\n📋 СТРУКТУРА ТАБЛИЦЫ monitoring.positions ({len(columns)} полей):\n")
        print(f"{'№':<4} {'Column Name':<30} {'Type':<25} {'Nullable':<10} {'Default':<20}")
        print("=" * 100)

        for idx, col in enumerate(columns, 1):
            col_name = col['column_name']
            data_type = col['data_type']

            # Add length for varchar
            if col['character_maximum_length']:
                data_type += f"({col['character_maximum_length']})"

            nullable = "YES" if col['is_nullable'] == 'YES' else "NO"
            default = str(col['column_default'])[:20] if col['column_default'] else ""

            print(f"{idx:<4} {col_name:<30} {data_type:<25} {nullable:<10} {default:<20}")

        # Check if specific columns exist
        print("\n\n🔍 ПРОВЕРКА КЛЮЧЕВЫХ ПОЛЕЙ TS:\n")

        column_names = [col['column_name'] for col in columns]

        ts_fields = {
            'has_trailing_stop': '✅' if 'has_trailing_stop' in column_names else '❌',
            'trailing_activated': '✅' if 'trailing_activated' in column_names else '❌',
            'ts_last_update_time': '✅' if 'ts_last_update_time' in column_names else '❌',
            'sl_managed_by': '✅' if 'sl_managed_by' in column_names else '❌'
        }

        for field, exists in ts_fields.items():
            print(f"  {exists} {field}")

    finally:
        await conn.close()
        print("\n✅ Проверка завершена")

if __name__ == '__main__':
    asyncio.run(show_table_structure())
