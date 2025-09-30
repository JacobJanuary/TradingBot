import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

async def cancel_duplicate_orders():
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
        print("ОЧИСТКА ДУБЛИКАТОВ СТОП-ЛОСС ОРДЕРОВ")
        print("=" * 80)

        # Получаем все открытые ордера
        orders = await exchange.fetch_open_orders()
        print(f'\n📊 Найдено открытых ордеров: {len(orders)}')

        # Группируем по символам
        orders_by_symbol = defaultdict(list)
        for order in orders:
            orders_by_symbol[order['symbol']].append(order)

        # Отменяем дубликаты (оставляем только последний)
        total_cancelled = 0
        for symbol, symbol_orders in orders_by_symbol.items():
            if len(symbol_orders) > 1:
                print(f'\n{symbol}: найдено {len(symbol_orders)} ордеров')

                # Сортируем по времени создания (старые первые)
                symbol_orders.sort(key=lambda x: x['datetime'])

                # Отменяем все кроме последнего
                for order in symbol_orders[:-1]:
                    try:
                        await exchange.cancel_order(order['id'], symbol)
                        print(f'  ✅ Отменен старый ордер от {order["datetime"]}')
                        total_cancelled += 1
                        await asyncio.sleep(0.5)  # Задержка для rate limit
                    except Exception as e:
                        print(f'  ❌ Ошибка отмены ордера: {e}')

                print(f'  📌 Оставлен последний ордер от {symbol_orders[-1]["datetime"]}')

        print(f'\n✨ Всего отменено дубликатов: {total_cancelled}')

    except Exception as e:
        print(f'❌ Ошибка: {e}')
    finally:
        await exchange.close()

asyncio.run(cancel_duplicate_orders())