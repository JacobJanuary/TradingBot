#!/usr/bin/env python3
"""
Детальная проверка SL ордеров на биржах
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange_manager import ExchangeManager
from config.settings import config
from database.repository import Repository


async def check_binance_sl_orders():
    """Проверка SL ордеров на Binance"""
    print("=" * 100)
    print("BINANCE: STOP-LOSS ОРДЕРА")
    print("=" * 100)

    binance_config = config.get_exchange_config('binance')
    binance = ExchangeManager('binance', binance_config.__dict__)
    await binance.initialize()

    # Получить позиции
    positions = await binance.exchange.fetch_positions()
    active_positions = [p for p in positions if abs(float(p.get('contracts', 0))) > 0]

    print(f"\nПроверяю {len(active_positions)} активных позиций...\n")

    sl_count = 0
    no_sl_count = 0

    for pos in active_positions:
        symbol = pos.get('symbol')
        norm_symbol = symbol.replace('/USDT:USDT', 'USDT')
        contracts = float(pos.get('contracts', 0))
        side = pos.get('side')

        # Получить открытые ордера для символа
        try:
            orders = await binance.exchange.fetch_open_orders(symbol=symbol)
            sl_orders = [o for o in orders if o.get('type') in ['STOP_MARKET', 'stop', 'stop_market', 'STOP']]

            if sl_orders:
                for order in sl_orders:
                    stop_price = order.get('stopPrice') or order.get('triggerPrice')
                    order_side = order.get('side')
                    reduce_only = order.get('info', {}).get('reduceOnly', False)
                    time_in_force = order.get('timeInForce')
                    post_only = order.get('postOnly', False)

                    print(f"✅ {norm_symbol:15} | {side:5} | contracts={contracts:10.2f} | "
                          f"SL={float(stop_price):10.6f} | side={order_side:4} | "
                          f"reduceOnly={reduce_only} | TIF={time_in_force} | postOnly={post_only}")
                    sl_count += 1
            else:
                print(f"❌ {norm_symbol:15} | {side:5} | contracts={contracts:10.2f} | NO SL ORDER")
                no_sl_count += 1

        except Exception as e:
            print(f"⚠️  {norm_symbol:15} | ERROR: {e}")

    await binance.close()

    print(f"\n{'=' * 100}")
    print(f"Binance: {sl_count} позиций с SL, {no_sl_count} БЕЗ SL")
    print(f"{'=' * 100}\n")

    return sl_count, no_sl_count


async def check_bybit_sl_orders():
    """Проверка SL ордеров на Bybit (trading stop)"""
    print("=" * 100)
    print("BYBIT: STOP-LOSS (TRADING STOP)")
    print("=" * 100)

    bybit_config = config.get_exchange_config('bybit')
    bybit = ExchangeManager('bybit', bybit_config.__dict__)
    await bybit.initialize()

    # Получить позиции
    positions = await bybit.exchange.fetch_positions()
    active_positions = [p for p in positions if abs(float(p.get('contracts', 0))) > 0]

    print(f"\nПроверяю {len(active_positions)} активных позиций...\n")

    sl_count = 0
    no_sl_count = 0

    for pos in active_positions:
        symbol = pos.get('symbol')
        norm_symbol = symbol.replace('/USDT:USDT', 'USDT')
        contracts = float(pos.get('contracts', 0))
        side = pos.get('side')

        # Bybit использует stopLoss в позиции напрямую
        stop_loss = pos.get('stopLoss')
        take_profit = pos.get('takeProfit')

        if stop_loss and float(stop_loss) > 0:
            print(f"✅ {norm_symbol:15} | {side:5} | contracts={contracts:10.2f} | "
                  f"SL={float(stop_loss):10.6f} | (trading_stop)")
            sl_count += 1
        else:
            print(f"❌ {norm_symbol:15} | {side:5} | contracts={contracts:10.2f} | NO SL (trading_stop)")
            no_sl_count += 1

    await bybit.close()

    print(f"\n{'=' * 100}")
    print(f"Bybit: {sl_count} позиций с SL, {no_sl_count} БЕЗ SL")
    print(f"{'=' * 100}\n")

    return sl_count, no_sl_count


async def compare_with_database():
    """Сравнение с данными в базе"""
    print("=" * 100)
    print("СРАВНЕНИЕ С БАЗОЙ ДАННЫХ")
    print("=" * 100)

    db_config = {
        'host': config.database.host,
        'port': config.database.port,
        'database': config.database.database,
        'user': config.database.user,
        'password': config.database.password
    }

    repo = Repository(db_config)
    await repo.initialize()

    query = """
        SELECT
            symbol,
            exchange,
            side,
            quantity,
            entry_price,
            stop_loss_price,
            has_stop_loss,
            has_trailing_stop,
            trailing_activated
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY exchange, symbol
    """

    async with repo.pool.acquire() as conn:
        rows = await conn.fetch(query)

    print(f"\nВ базе {len(rows)} активных позиций\n")

    has_sl_count = 0
    no_sl_count = 0

    print(f"{'SYMBOL':15} | {'EXCHANGE':8} | {'SIDE':5} | {'QTY':10} | {'ENTRY':10} | "
          f"{'SL_PRICE':10} | {'HAS_SL':7} | {'TS':5} | {'ACTIV':5}")
    print("=" * 100)

    for row in rows:
        has_sl = row['has_stop_loss']
        if has_sl:
            has_sl_count += 1
        else:
            no_sl_count += 1

        sl_price = row['stop_loss_price'] or 0
        ts = "YES" if row['has_trailing_stop'] else "NO"
        activ = "YES" if row['trailing_activated'] else "NO"
        has_sl_str = "YES" if has_sl else "NO"

        print(f"{row['symbol']:15} | {row['exchange']:8} | {row['side']:5} | "
              f"{float(row['quantity']):10.2f} | {float(row['entry_price']):10.6f} | "
              f"{float(sl_price):10.6f} | {has_sl_str:7} | {ts:5} | {activ:5}")

    await repo.close()

    print(f"\n{'=' * 100}")
    print(f"База данных: {has_sl_count} с SL, {no_sl_count} БЕЗ SL")
    print(f"{'=' * 100}\n")

    return has_sl_count, no_sl_count


async def main():
    """Главная функция"""
    try:
        # Проверить биржи
        binance_sl, binance_no_sl = await check_binance_sl_orders()
        bybit_sl, bybit_no_sl = await check_bybit_sl_orders()

        # Проверить базу
        db_sl, db_no_sl = await compare_with_database()

        # Итоговая сводка
        print("\n" + "=" * 100)
        print("ИТОГОВАЯ СВОДКА")
        print("=" * 100)
        print(f"Binance:  {binance_sl} с SL, {binance_no_sl} БЕЗ SL (всего {binance_sl + binance_no_sl})")
        print(f"Bybit:    {bybit_sl} с SL, {bybit_no_sl} БЕЗ SL (всего {bybit_sl + bybit_no_sl})")
        print(f"Биржи:    {binance_sl + bybit_sl} с SL, {binance_no_sl + bybit_no_sl} БЕЗ SL (всего {binance_sl + bybit_sl + binance_no_sl + bybit_no_sl})")
        print(f"-" * 100)
        print(f"База:     {db_sl} с SL, {db_no_sl} БЕЗ SL (всего {db_sl + db_no_sl})")
        print("=" * 100)

        if binance_no_sl + bybit_no_sl > 0:
            print(f"\n⚠️  ВНИМАНИЕ: {binance_no_sl + bybit_no_sl} позиций БЕЗ SL на биржах!")
        else:
            print(f"\n✅ ВСЕ ПОЗИЦИИ ЗАЩИЩЕНЫ SL")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
