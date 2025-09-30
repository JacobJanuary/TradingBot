#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

async def check_bot_signals():
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

    print('=' * 80)
    print('ПРОВЕРКА СИГНАЛОВ ДЛЯ БОТА')
    print('=' * 80)

    # Точный запрос бота
    query = """
        SELECT
            sc.id,
            sc.pair_symbol as symbol,
            sc.recommended_action as action,
            sc.score_week,
            sc.score_month,
            sc.created_at,
            LOWER(ex.exchange_name) as exchange
        FROM fas.scoring_history sc
        JOIN public.trading_pairs tp ON tp.id = sc.trading_pair_id
        JOIN public.exchanges ex ON ex.id = tp.exchange_id
        WHERE sc.created_at > NOW() - INTERVAL '1440 minutes'
            AND sc.score_week >= 50.0
            AND sc.score_month >= 50.0
            AND sc.is_active = true
            AND sc.recommended_action IN ('BUY', 'SELL', 'LONG', 'SHORT')
            AND sc.recommended_action IS NOT NULL
            AND sc.recommended_action != 'NO_TRADE'
        ORDER BY sc.created_at DESC
        LIMIT 20
    """

    signals = await conn.fetch(query)

    print(f'\n✅ Найдено {len(signals)} сигналов для бота\n')

    if signals:
        print('Топ-20 последних сигналов:')
        print('-' * 80)
        for i, row in enumerate(signals, 1):
            age = datetime.now(row['created_at'].tzinfo) - row['created_at']
            hours = age.total_seconds() / 3600
            print(f"{i:2}. {row['symbol']:15} {row['action']:5} | Week:{row['score_week']:6.1f} Month:{row['score_month']:6.1f} | {row['exchange']:7} | {hours:.1f}h назад")

    # Проверим последнюю обработку
    processed = await conn.fetch("""
        SELECT * FROM trading_bot.processed_signals
        ORDER BY processed_at DESC
        LIMIT 5
    """)

    print(f'\n📝 Последние обработанные сигналы (trading_bot.processed_signals):')
    if processed:
        for row in processed:
            print(f"  {row['processed_at']}: Signal {row['signal_id']} - {row['status']}")
    else:
        print('  НЕТ ЗАПИСЕЙ - бот еще не обрабатывал сигналы!')

    await conn.close()

if __name__ == '__main__':
    asyncio.run(check_bot_signals())