#!/usr/bin/env python3
"""
Синхронизация позиций Bybit с базой данных
"""
import asyncio
import asyncpg
import ccxt.async_support as ccxt
import os
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

async def sync_bybit_positions():
    """Синхронизирует позиции Bybit с базой данных"""

    # Подключение к БД
    db_url = os.getenv('DATABASE_URL', 'postgresql://evgeniyyanvarskiy@localhost:5432/postgres')
    conn = await asyncpg.connect(db_url)

    # Инициализация Bybit
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',
            'recvWindow': 10000
        }
    })
    exchange.set_sandbox_mode(True)

    print('=== СИНХРОНИЗАЦИЯ ПОЗИЦИЙ BYBIT С БД ===\n')

    try:
        # Проверяем существование схемы и таблицы
        schemas = await conn.fetch("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'fas'")
        if not schemas:
            print('Создаю схему fas...')
            await conn.execute('CREATE SCHEMA IF NOT EXISTS fas')

        # Создаем таблицу позиций если не существует
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fas.position (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(50) NOT NULL,
                exchange VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                quantity DECIMAL(20, 8) NOT NULL,
                entry_price DECIMAL(20, 8) NOT NULL,
                current_price DECIMAL(20, 8),
                stop_loss DECIMAL(20, 8),
                take_profit DECIMAL(20, 8),
                status VARCHAR(20) DEFAULT 'open',
                pnl DECIMAL(20, 8),
                pnl_percentage DECIMAL(10, 2),
                trailing_activated BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                strategy VARCHAR(50),
                timeframe VARCHAR(10),
                notes TEXT
            )
        ''')

        # Создаем индексы
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_exchange_status
            ON fas.position(exchange, status)
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_symbol
            ON fas.position(symbol)
        ''')

        # Получаем позиции с Bybit
        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if p['contracts'] > 0]

        print(f'Найдено {len(open_positions)} открытых позиций на Bybit\n')

        if open_positions:
            # Закрываем старые позиции Bybit в БД
            await conn.execute('''
                UPDATE fas.position
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP
                WHERE exchange = 'bybit' AND status = 'open'
            ''')

            # Добавляем текущие позиции
            added = 0
            for pos in open_positions:
                symbol = pos['symbol']
                side = pos['side']
                contracts = pos['contracts']
                entry_price = float(pos['info'].get('avgPrice', 0)) if pos['info'] else 0
                mark_price = float(pos['info'].get('markPrice', entry_price)) if pos['info'] else entry_price

                # Рассчитываем PnL
                if side == 'long':
                    pnl_pct = ((mark_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                else:
                    pnl_pct = ((entry_price - mark_price) / entry_price) * 100 if entry_price > 0 else 0

                pnl = contracts * (mark_price - entry_price) if side == 'long' else contracts * (entry_price - mark_price)

                # Проверяем наличие stop loss
                stop_loss = None
                try:
                    orders = await exchange.fetch_open_orders(symbol)
                    for order in orders:
                        if order['type'] in ['stop', 'stop_market', 'stop_loss']:
                            stop_loss = order.get('stopPrice')
                            break
                except:
                    pass

                # Вставляем в БД
                await conn.execute('''
                    INSERT INTO fas.position
                    (symbol, exchange, side, quantity, entry_price, current_price,
                     stop_loss, status, pnl, pnl_percentage, strategy)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ''', symbol, 'bybit', side, Decimal(str(contracts)),
                    Decimal(str(entry_price)), Decimal(str(mark_price)),
                    Decimal(str(stop_loss)) if stop_loss else None,
                    'open', Decimal(str(pnl)), Decimal(str(pnl_pct)), 'manual')

                added += 1
                status = '✅ SL установлен' if stop_loss else '❌ БЕЗ SL'
                print(f'{added:2}. {symbol:20} | {side:5} | Вход: ${entry_price:.4f} | PnL: {pnl_pct:+.2f}% | {status}')

            print(f'\n✅ Синхронизировано {added} позиций с базой данных')

            # Проверяем результат
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM fas.position
                WHERE exchange = 'bybit' AND status = 'open'
            ''')
            print(f'Всего позиций Bybit в БД: {count}')
        else:
            print('Нет открытых позиций для синхронизации')

    except Exception as e:
        print(f'❌ Ошибка: {e}')

    finally:
        await conn.close()
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(sync_bybit_positions())