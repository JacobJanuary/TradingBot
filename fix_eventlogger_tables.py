#!/usr/bin/env python3
"""
Исправление таблиц EventLogger
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_tables():
    # Подключение к БД
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5433)),
        database=os.getenv('DB_NAME', 'fox_crypto_test'),
        user=os.getenv('DB_USER', 'elcrypto'),
        password=os.getenv('DB_PASSWORD', 'LohNeMamont@!21')
    )

    try:
        print("Удаляю старые таблицы...")

        # Удаляем таблицы в monitoring схеме
        await conn.execute("DROP TABLE IF EXISTS monitoring.performance_metrics CASCADE")
        print("✓ monitoring.performance_metrics удалена")

        await conn.execute("DROP TABLE IF EXISTS monitoring.transaction_log CASCADE")
        print("✓ monitoring.transaction_log удалена")

        await conn.execute("DROP TABLE IF EXISTS monitoring.events CASCADE")
        print("✓ monitoring.events удалена")

        # Удаляем таблицы в public схеме
        await conn.execute("DROP TABLE IF EXISTS performance_metrics CASCADE")
        print("✓ performance_metrics удалена")

        await conn.execute("DROP TABLE IF EXISTS transaction_log CASCADE")
        print("✓ transaction_log удалена")

        await conn.execute("DROP TABLE IF EXISTS events CASCADE")
        print("✓ events удалена")

        print("\n✅ Все старые таблицы удалены!")
        print("Теперь при следующем запуске бот создаст их с правильной структурой.")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_tables())