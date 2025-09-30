#!/usr/bin/env python3
"""Очистка зомби-ордеров (ордера без позиций)"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def clean_zombie_orders():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': True
        }
    })

    try:
        print("="*80)
        print("ОЧИСТКА ЗОМБИ-ОРДЕРОВ НА BYBIT")
        print("="*80)

        # Получаем позиции
        positions = await exchange.fetch_positions()
        active_positions = [p for p in positions if p['contracts'] > 0]
        position_symbols = {p['symbol'] for p in active_positions}

        print(f"\n📈 Активные позиции ({len(active_positions)}):")
        for symbol in position_symbols:
            print(f"  • {symbol}")

        # Получаем все открытые ордера
        all_orders = await exchange.fetch_open_orders()
        print(f"\n📋 Всего открытых ордеров: {len(all_orders)}")

        # Находим зомби-ордера
        zombie_orders = []
        for order in all_orders:
            symbol = order.get('symbol')
            if symbol and symbol not in position_symbols:
                zombie_orders.append(order)

        if not zombie_orders:
            print("\n✅ Зомби-ордеров не найдено")
            return

        print(f"\n🧟 Найдено {len(zombie_orders)} зомби-ордеров для отмены:")

        # Группируем по символам для удобства
        from collections import defaultdict
        zombies_by_symbol = defaultdict(list)
        for order in zombie_orders:
            zombies_by_symbol[order['symbol']].append(order)

        for symbol, orders in zombies_by_symbol.items():
            print(f"\n  {symbol}: {len(orders)} ордеров")
            for order in orders:
                print(f"    • ID: {order['id'][:8]}... Type: {order.get('type', '?')}")

        # Спрашиваем подтверждение
        print(f"\n⚠️  Будет отменено {len(zombie_orders)} ордеров")
        confirm = input("Продолжить? (y/n): ")

        if confirm.lower() != 'y':
            print("Отмена операции")
            return

        # Отменяем зомби-ордера
        cancelled_count = 0
        failed_count = 0

        for order in zombie_orders:
            try:
                symbol = order['symbol']
                order_id = order['id']

                print(f"  Отмена ордера {order_id[:8]}... для {symbol}...", end="")
                await exchange.cancel_order(order_id, symbol)
                print(" ✅")
                cancelled_count += 1

                # Небольшая задержка для избежания rate limits
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f" ❌ Ошибка: {e}")
                failed_count += 1

        # Итоги
        print(f"\n" + "="*80)
        print("ИТОГИ ОЧИСТКИ:")
        print(f"  ✅ Успешно отменено: {cancelled_count} ордеров")
        if failed_count > 0:
            print(f"  ❌ Не удалось отменить: {failed_count} ордеров")
        print("="*80)

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(clean_zombie_orders())