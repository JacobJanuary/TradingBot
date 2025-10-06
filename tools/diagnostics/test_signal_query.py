#!/usr/bin/env python3
"""
Тестируем точный запрос, который использует бот для получения сигналов
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def test_signal_query():
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

    # ТОЧНЫЙ запрос из бота
    query = """
        SELECT
            sc.id,
            sc.pair_symbol as symbol,
            sc.recommended_action as action,
            sc.score_week,
            sc.score_month,
            sc.patterns_details,
            sc.combinations_details,
            sc.created_at,
            LOWER(ex.exchange_name) as exchange,
            date_trunc('hour', sc.created_at) +
                interval '15 min' * floor(date_part('minute', sc.created_at) / 15) as wave_timestamp
        FROM fas.scoring_history sc
        JOIN public.trading_pairs tp ON tp.id = sc.trading_pair_id
        JOIN public.exchanges ex ON ex.id = tp.exchange_id
        WHERE sc.created_at > NOW() - INTERVAL '1 minute' * $1
            AND sc.score_week >= $2
            AND sc.score_month >= $3
            AND sc.is_active = true
            AND sc.recommended_action IN ('BUY', 'SELL', 'LONG', 'SHORT')
            AND sc.recommended_action IS NOT NULL
            AND sc.recommended_action != 'NO_TRADE'
        ORDER BY
            wave_timestamp DESC,
            sc.score_week DESC,
            sc.score_month DESC
        LIMIT $4
    """

    # Параметры из конфига бота
    time_window_minutes = 1440  # 24 часа (из config/settings.py)
    min_score_week = 50.0        # из config/settings.py
    min_score_month = 50.0       # из config/settings.py
    limit = 10                   # max_trades_per_15min

    print('=' * 80)
    print('ПОЛНЫЙ ЗАПРОС БОТА К БАЗЕ ДАННЫХ')
    print('=' * 80)
    print(f'\nПараметры запроса:')
    print(f'  $1 = {time_window_minutes} (окно времени в минутах)')
    print(f'  $2 = {min_score_week} (минимальный score_week)')
    print(f'  $3 = {min_score_month} (минимальный score_month)')
    print(f'  $4 = {limit} (лимит записей)')
    print(f'\nЭто значит бот ищет сигналы за последние {time_window_minutes} минут ({time_window_minutes/60:.1f} часов)')
    print('=' * 80)

    # Выполняем запрос
    rows = await conn.fetch(query, time_window_minutes, min_score_week, min_score_month, limit)

    print(f'\nРезультат: найдено {len(rows)} сигналов\n')

    if rows:
        print('Сигналы, которые бот должен обработать:')
        print('-' * 80)
        for i, row in enumerate(rows, 1):
            print(f"{i:2}. ID: {row['id']:8} | {row['symbol']:15} | {row['action']:5} | Week: {row['score_week']:5.1f} | Month: {row['score_month']:5.1f}")
            print(f"    Создан: {row['created_at']} | Биржа: {row['exchange']}")
    else:
        print('❌ НЕТ СИГНАЛОВ соответствующих критериям!')

        # Проверим когда был последний сигнал
        check_query = """
            SELECT
                COUNT(*) as total,
                MAX(created_at) as newest,
                MIN(created_at) as oldest
            FROM fas.scoring_history
            WHERE sc.is_active = true
                AND sc.recommended_action IN ('BUY', 'SELL', 'LONG', 'SHORT')
                AND created_at > NOW() - INTERVAL '48 hours'
        """
        check = await conn.fetchrow(check_query)

        print(f'\nПроверка данных в fas.scoring_history:')
        print(f'  Записей за последние 48 часов: {check["total"]}')
        if check["total"] > 0:
            print(f'  Самая новая запись: {check["newest"]}')
            print(f'  Самая старая запись: {check["oldest"]}')

            # Время с последнего сигнала
            if check["newest"]:
                time_diff = datetime.now(check["newest"].tzinfo) - check["newest"]
                hours = time_diff.total_seconds() / 3600
                print(f'\n⚠️ Последний сигнал был {hours:.1f} часов назад!')
                print(f'⚠️ Бот ищет сигналы за последние {time_window_minutes/60:.1f} часов')
                if hours > time_window_minutes/60:
                    print(f'❌ Поэтому бот НЕ ВИДИТ сигналов - они слишком старые!')

    await conn.close()

if __name__ == '__main__':
    asyncio.run(test_signal_query())