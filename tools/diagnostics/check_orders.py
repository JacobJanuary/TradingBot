import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

async def check_orders():
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
        print("=" * 80)
        print("ПРОВЕРКА ОРДЕРОВ НА BYBIT TESTNET")
        print("=" * 80)

        # Получаем все открытые ордера
        orders = await exchange.fetch_open_orders()
        print(f'\n📊 Всего открытых ордеров: {len(orders)}')

        # Группируем по символам
        orders_by_symbol = {}
        limit_orders = 0
        stop_orders = 0

        for order in orders:
            symbol = order['symbol']
            if symbol not in orders_by_symbol:
                orders_by_symbol[symbol] = []
            orders_by_symbol[symbol].append(order)

            if order['type'] == 'limit':
                limit_orders += 1
            elif 'stop' in order['type'].lower():
                stop_orders += 1

        print(f'  - Лимитных ордеров: {limit_orders}')
        print(f'  - Стоп ордеров: {stop_orders}')

        # Выводим информацию по символам с множественными ордерами
        print('\n⚠️ СИМВОЛЫ С МНОЖЕСТВЕННЫМИ ОРДЕРАМИ:')
        multiple_orders_found = False
        for symbol, symbol_orders in sorted(orders_by_symbol.items(), key=lambda x: -len(x[1])):
            if len(symbol_orders) > 1:
                multiple_orders_found = True
                print(f'\n{symbol}: {len(symbol_orders)} ордеров')
                for i, order in enumerate(symbol_orders[:5], 1):  # Показываем первые 5 ордеров
                    created = order.get('datetime', 'unknown')
                    print(f'  {i}. {order["type"]:10} {order["side"]:4} '
                          f'amount: {order.get("amount", "?")} '
                          f'price: {order.get("price", "?")} '
                          f'created: {created}')
                if len(symbol_orders) > 5:
                    print(f'  ... и еще {len(symbol_orders) - 5} ордеров')

        if not multiple_orders_found:
            print("  Нет символов с множественными ордерами")

        # Проверяем открытые позиции
        print('\n' + "=" * 80)
        print("ПРОВЕРКА ПОЗИЦИЙ")
        print("=" * 80)
        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if p['contracts'] > 0]
        print(f'\n📈 Всего открытых позиций: {len(open_positions)}')

        # Сравниваем позиции и ордера
        print('\n🔍 АНАЛИЗ СООТВЕТСТВИЯ:')
        positions_with_orders = 0
        positions_without_orders = 0

        for pos in open_positions:
            symbol = pos['symbol']
            if symbol in orders_by_symbol:
                positions_with_orders += 1
                order_count = len(orders_by_symbol[symbol])
                if order_count > 10:
                    print(f'  ⚠️ {symbol}: позиция имеет {order_count} ордеров!')
            else:
                positions_without_orders += 1

        print(f'  - Позиций с ордерами: {positions_with_orders}')
        print(f'  - Позиций без ордеров: {positions_without_orders}')

        # Проверяем стоп-ордера через отдельный запрос
        print('\n' + "=" * 80)
        print("ПРОВЕРКА СТОП-ЛОСС ОРДЕРОВ")
        print("=" * 80)

        # Для Bybit используем специальный метод
        stop_loss_orders = await exchange.private_get_v5_order_realtime({
            'category': 'linear',
            'orderFilter': 'StopOrder'
        })

        if stop_loss_orders['result']['list']:
            print(f"Найдено стоп-ордеров: {len(stop_loss_orders['result']['list'])}")
            for sl in stop_loss_orders['result']['list'][:5]:
                print(f"  - {sl['symbol']}: {sl['side']} @ {sl['triggerPrice']}")
        else:
            print("Стоп-ордеров не найдено")

    except Exception as e:
        print(f'❌ Ошибка: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

asyncio.run(check_orders())