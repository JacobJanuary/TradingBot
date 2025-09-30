#!/usr/bin/env python3
"""Детальная проверка ордеров и позиций на Bybit"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime, timezone

load_dotenv()

async def check_bybit():
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
        print("ДЕТАЛЬНАЯ ПРОВЕРКА BYBIT TESTNET")
        print("="*80)

        # 1. Проверяем позиции
        print("\n📈 ПОЗИЦИИ:")
        positions = await exchange.fetch_positions()
        active_positions = [p for p in positions if p['contracts'] > 0]

        print(f"Всего активных позиций: {len(active_positions)}")
        position_symbols = set()
        for pos in active_positions:
            position_symbols.add(pos['symbol'])
            print(f"  • {pos['symbol']}: {pos['side']} {pos['contracts']} @ {pos['markPrice']}")

        # 2. Проверяем ВСЕ ордера через CCXT
        print("\n📋 ОРДЕРА (через CCXT fetch_open_orders):")
        all_orders = await exchange.fetch_open_orders()
        print(f"Всего ордеров: {len(all_orders)}")

        # Группируем по типам
        order_types = defaultdict(list)
        for order in all_orders:
            order_type = order.get('type', 'unknown')
            order_types[order_type].append(order)

        for order_type, orders in order_types.items():
            print(f"\n  {order_type}: {len(orders)} ордеров")
            for order in orders[:3]:  # Показываем первые 3
                print(f"    • {order['symbol']} {order['side']} {order.get('amount', '?')} @ {order.get('price', order.get('stopPrice', '?'))}")

        # 3. Проверяем через нативный API Bybit для лимитных ордеров
        print("\n📊 ЛИМИТНЫЕ ОРДЕРА (через Bybit API v5):")
        try:
            limit_orders = await exchange.private_get_v5_order_realtime({
                'category': 'linear',
                'settleCoin': 'USDT'
            })

            if limit_orders['result']['list']:
                print(f"Найдено лимитных ордеров: {len(limit_orders['result']['list'])}")
                for order in limit_orders['result']['list'][:5]:
                    print(f"  • {order['symbol']}: {order['side']} {order['qty']} @ {order['price']}")
                    print(f"    Статус: {order['orderStatus']}, Тип: {order['orderType']}")
            else:
                print("Лимитных ордеров не найдено")

        except Exception as e:
            print(f"Ошибка получения лимитных ордеров: {e}")

        # 4. Проверяем стоп-ордера
        print("\n🛑 СТОП-ОРДЕРА (через Bybit API v5):")
        try:
            # Для стоп-ордеров используем другой фильтр
            stop_orders = await exchange.private_get_v5_order_realtime({
                'category': 'linear',
                'settleCoin': 'USDT',
                'orderFilter': 'StopOrder'
            })

            if stop_orders['result']['list']:
                print(f"Найдено стоп-ордеров: {len(stop_orders['result']['list'])}")
                for order in stop_orders['result']['list'][:5]:
                    print(f"  • {order['symbol']}: {order['side']} {order['qty']} @ trigger: {order.get('triggerPrice', 'N/A')}")
                    print(f"    Статус: {order['orderStatus']}, Тип: {order['orderType']}")
            else:
                print("Стоп-ордеров не найдено")

        except Exception as e:
            print(f"Ошибка получения стоп-ордеров: {e}")

        # 5. Анализ зомби-ордеров
        print("\n🧟 АНАЛИЗ ЗОМБИ-ОРДЕРОВ:")
        zombie_orders = []
        for order in all_orders:
            symbol = order.get('symbol')
            if symbol and symbol not in position_symbols:
                zombie_orders.append(order)

        if zombie_orders:
            print(f"⚠️ Найдено {len(zombie_orders)} ордеров без позиций:")
            for order in zombie_orders:
                print(f"  • {order['symbol']}: {order.get('type', '?')} {order['side']} {order.get('amount', '?')}")
                print(f"    ID: {order['id']}, Создан: {order.get('datetime', 'unknown')}")
        else:
            print("✅ Зомби-ордеров не найдено")

        # 6. Проверка соответствия
        print("\n🔍 СООТВЕТСТВИЕ ПОЗИЦИЙ И ОРДЕРОВ:")
        for symbol in position_symbols:
            symbol_orders = [o for o in all_orders if o.get('symbol') == symbol]
            print(f"  {symbol}: {len(symbol_orders)} ордеров")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

asyncio.run(check_bybit())