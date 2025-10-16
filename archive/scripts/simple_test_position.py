#!/usr/bin/env python3
"""
Простой тест - создаёт минимальный сигнал и отправляет в работающий бот через БД
"""
import asyncio
from database.repository import Repository
from config.settings import Config
from datetime import datetime, timezone

async def create_test_signal():
    """Создать тестовый сигнал в БД для обработки ботом"""
    print("🧪 Creating test signal for bot to process...\n")

    cfg = Config()
    db_config = {
        'host': cfg.database.host,
        'port': cfg.database.port,
        'database': cfg.database.database,
        'user': cfg.database.user,
        'password': cfg.database.password,
        'pool_size': cfg.database.pool_size,
        'max_overflow': cfg.database.max_overflow
    }
    repository = Repository(db_config)
    await repository.initialize()

    # Проверяем последний сигнал
    async with repository.pool.acquire() as conn:
        last_signal = await conn.fetchrow("""
            SELECT id, symbol, timestamp_15m
            FROM fas.signals
            ORDER BY id DESC
            LIMIT 1
        """)

    print(f"📊 Last signal in DB:")
    print(f"   ID: {last_signal['id']}")
    print(f"   Symbol: {last_signal['symbol']}")
    print(f"   Time: {last_signal['timestamp_15m']}\n")

    # Создаём тестовый сигнал (копия последнего но с новым временем)
    test_symbol = 'BTCUSDT'  # Ликвидный символ
    test_timestamp = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    # Проверяем есть ли уже сигнал на это время
    async with repository.pool.acquire() as conn:
        existing = await conn.fetchval("""
            SELECT COUNT(*)
            FROM fas.signals
            WHERE symbol = $1 AND timestamp_15m = $2
        """, test_symbol, test_timestamp)

    if existing > 0:
        print(f"⚠️  Signal for {test_symbol} at {test_timestamp} already exists")
        print("   Bot should process it automatically\n")
    else:
        print(f"📝 Creating new test signal:")
        print(f"   Symbol: {test_symbol}")
        print(f"   Timestamp: {test_timestamp}\n")

        confirm = input("⚠️  Create test signal? Bot will try to open position. (yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ Cancelled")
            await repository.pool.close()
            return

        # Вставляем тестовый сигнал
        async with repository.pool.acquire() as conn:
            signal_id = await conn.fetchval("""
                INSERT INTO fas.signals (
                    symbol, timestamp_15m, timestamp_1d,
                    score_week, score_month, score_combo, signal_strength,
                    created_at
                ) VALUES (
                    $1, $2, $2,
                    100, 100, 100, 100,
                    NOW()
                ) RETURNING id
            """, test_symbol, test_timestamp)

        print(f"✅ Test signal created with ID: {signal_id}")
        print(f"\n📢 Now watch bot logs for position creation:")
        print(f"   tail -f logs/trading_bot.log | grep -E 'BTCUSDT|📝|Entry order|Entry trade'\n")

    await repository.pool.close()

if __name__ == "__main__":
    asyncio.run(create_test_signal())
