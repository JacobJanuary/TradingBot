#!/usr/bin/env python3
"""
Проверка позиций на биржах через API
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange_manager import ExchangeManager
from config.settings import config


async def check_binance_positions():
    """Проверка позиций на Binance"""
    print("=" * 80)
    print("ПРОВЕРКА ПОЗИЦИЙ НА BINANCE")
    print("=" * 80)

    binance_config = config.get_exchange_config('binance')
    binance = ExchangeManager('binance', binance_config.__dict__)
    await binance.initialize()

    # Получить все активные позиции
    positions = await binance.exchange.fetch_positions()

    active_positions = [p for p in positions if abs(float(p.get('contracts', 0))) > 0]

    print(f"\nВсего активных позиций: {len(active_positions)}\n")

    for pos in active_positions:
        symbol = pos.get('symbol', '').replace('/USDT:USDT', 'USDT')
        contracts = float(pos.get('contracts', 0))
        side = pos.get('side')
        entry_price = pos.get('entryPrice')
        mark_price = pos.get('markPrice')

        print(f"{symbol:15} | {side:5} | contracts={contracts:12.2f} | entry={entry_price:10.6f} | mark={mark_price:10.6f}")

    await binance.close()
    return active_positions


async def check_bybit_positions():
    """Проверка позиций на Bybit"""
    print("\n" + "=" * 80)
    print("ПРОВЕРКА ПОЗИЦИЙ НА BYBIT")
    print("=" * 80)

    bybit_config = config.get_exchange_config('bybit')
    bybit = ExchangeManager('bybit', bybit_config.__dict__)
    await bybit.initialize()

    # Получить все активные позиции
    positions = await bybit.exchange.fetch_positions()

    active_positions = [p for p in positions if abs(float(p.get('contracts', 0))) > 0]

    print(f"\nВсего активных позиций: {len(active_positions)}\n")

    for pos in active_positions:
        symbol = pos.get('symbol', '').replace('/USDT:USDT', 'USDT')
        contracts = float(pos.get('contracts', 0))
        side = pos.get('side')
        entry_price = pos.get('entryPrice')
        mark_price = pos.get('markPrice')

        print(f"{symbol:15} | {side:5} | contracts={contracts:12.2f} | entry={entry_price:10.6f} | mark={mark_price:10.6f}")

    await bybit.close()
    return active_positions


async def check_stop_loss_orders():
    """Проверка SL ордеров на биржах"""
    print("\n" + "=" * 80)
    print("ПРОВЕРКА STOP-LOSS ОРДЕРОВ")
    print("=" * 80)

    # Binance
    print("\n=== BINANCE ===")
    binance_config = config.get_exchange_config('binance')
    binance = ExchangeManager('binance', binance_config.__dict__)
    await binance.initialize()

    try:
        orders = await binance.exchange.fetch_open_orders()
        sl_orders = [o for o in orders if o.get('type') in ['STOP_MARKET', 'stop', 'stop_market']]

        print(f"Всего SL ордеров: {len(sl_orders)}\n")

        for order in sl_orders:
            symbol = order.get('symbol', '').replace('/USDT:USDT', 'USDT')
            order_type = order.get('type')
            side = order.get('side')
            stop_price = order.get('stopPrice') or order.get('triggerPrice')
            reduce_only = order.get('reduceOnly', False)

            print(f"{symbol:15} | {order_type:12} | {side:4} | stop={stop_price:10.6f} | reduceOnly={reduce_only}")

    except Exception as e:
        print(f"Ошибка получения ордеров Binance: {e}")

    await binance.close()

    # Bybit
    print("\n=== BYBIT ===")
    bybit_config = config.get_exchange_config('bybit')
    bybit = ExchangeManager('bybit', bybit_config.__dict__)
    await bybit.initialize()

    try:
        # Для Bybit используем специальный метод для получения условных ордеров
        positions = await bybit.exchange.fetch_positions()
        active_symbols = [p.get('symbol') for p in positions if abs(float(p.get('contracts', 0))) > 0]

        print(f"Проверяем позиции: {len(active_symbols)}\n")

        sl_count = 0
        for symbol in active_symbols:
            try:
                # Получаем trading stop для позиции
                params = {'symbol': symbol, 'category': 'linear'}
                response = await bybit.exchange.privateGetV5PositionList(params)

                if response and 'result' in response and 'list' in response['result']:
                    for pos_data in response['result']['list']:
                        sl_price = pos_data.get('stopLoss')
                        if sl_price and float(sl_price) > 0:
                            norm_symbol = symbol.replace('/USDT:USDT', 'USDT')
                            side = pos_data.get('side')
                            sl_count += 1
                            print(f"{norm_symbol:15} | trading_stop  | {side:4} | stop={float(sl_price):10.6f}")

            except Exception as e:
                pass

        print(f"\nВсего SL (trading stop): {sl_count}")

    except Exception as e:
        print(f"Ошибка получения позиций Bybit: {e}")

    await bybit.close()


async def main():
    """Главная функция"""
    try:
        binance_positions = await check_binance_positions()
        bybit_positions = await check_bybit_positions()
        await check_stop_loss_orders()

        print("\n" + "=" * 80)
        print("ИТОГО")
        print("=" * 80)
        print(f"Binance: {len(binance_positions)} позиций")
        print(f"Bybit: {len(bybit_positions)} позиций")
        print(f"ВСЕГО: {len(binance_positions) + len(bybit_positions)} позиций")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
