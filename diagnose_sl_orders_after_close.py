#!/usr/bin/env python3
"""
Диагностика: Проверка SL ордеров после закрытия всех позиций
Ожидание: Все SL ордера должны быть отменены (привязаны к позициям)
"""

import asyncio
import ccxt.async_support as ccxt
from config.settings import Config
from datetime import datetime

async def main():
    print("=" * 80)
    print("🔍 ДИАГНОСТИКА: Stop-Loss ордера после закрытия позиций")
    print("=" * 80)
    print()

    config = Config()

    # Получаем конфигурацию Binance
    binance_config = config.exchanges.get('binance')
    if not binance_config:
        print("❌ Binance не настроен в конфигурации!")
        return

    # Подключаемся к Binance
    exchange = ccxt.binance({
        'apiKey': binance_config.api_key,
        'secret': binance_config.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'recvWindow': 60000,
            'warnOnFetchOpenOrdersWithoutSymbol': False,
        }
    })

    if binance_config.testnet:
        exchange.set_sandbox_mode(True)
        print("⚠️  TESTNET MODE")
        print()

    try:
        print("📡 Подключение к Binance Futures...")
        print()

        # 1. Проверяем открытые позиции
        print("=" * 80)
        print("1️⃣ ПРОВЕРКА ОТКРЫТЫХ ПОЗИЦИЙ")
        print("=" * 80)
        print()

        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if float(p.get('contracts', 0)) != 0]

        print(f"📊 Всего позиций: {len(positions)}")
        print(f"📊 Открытых позиций (contracts != 0): {len(open_positions)}")
        print()

        if open_positions:
            print("⚠️  НАЙДЕНЫ ОТКРЫТЫЕ ПОЗИЦИИ:")
            for pos in open_positions[:10]:
                symbol = pos['symbol']
                contracts = pos['contracts']
                side = pos['side']
                entry_price = pos.get('entryPrice', 'N/A')
                unrealized_pnl = pos.get('unrealizedPnl', 0)
                print(f"   • {symbol}: {side} {contracts} контрактов, entry={entry_price}, PnL={unrealized_pnl:.2f}")
            print()
        else:
            print("✅ Открытых позиций нет (все закрыты)")
            print()

        # 2. Проверяем открытые ордера
        print("=" * 80)
        print("2️⃣ ПРОВЕРКА ОТКРЫТЫХ ОРДЕРОВ")
        print("=" * 80)
        print()

        # Получаем все открытые ордера
        open_orders = await exchange.fetch_open_orders()

        print(f"📊 Всего открытых ордеров: {len(open_orders)}")
        print()

        if not open_orders:
            print("✅ Открытых ордеров нет!")
            print("✅ Все SL ордера были отменены при закрытии позиций (как и ожидалось)")
            print()
        else:
            print("⚠️  НАЙДЕНЫ ОТКРЫТЫЕ ОРДЕРА:")
            print()

            # Группируем по типам
            by_type = {}
            by_symbol = {}

            for order in open_orders:
                order_type = order.get('type', 'unknown')
                symbol = order['symbol']

                if order_type not in by_type:
                    by_type[order_type] = []
                by_type[order_type].append(order)

                if symbol not in by_symbol:
                    by_symbol[symbol] = []
                by_symbol[symbol].append(order)

            # Статистика по типам
            print("📊 Распределение по типам:")
            for order_type, orders in sorted(by_type.items()):
                print(f"   {order_type}: {len(orders)} ордеров")
            print()

            # Детали по каждому ордеру
            print("📋 ДЕТАЛИ КАЖДОГО ОРДЕРА:")
            print()

            for i, order in enumerate(open_orders, 1):
                symbol = order['symbol']
                order_id = order['id']
                order_type = order.get('type', 'unknown')
                side = order.get('side', 'unknown')
                price = order.get('price', 'N/A')
                amount = order.get('amount', 'N/A')
                status = order.get('status', 'unknown')

                # Проверяем reduceOnly флаг (для SL)
                reduce_only = order.get('reduceOnly', False)
                info = order.get('info', {})
                stop_price = info.get('stopPrice', 'N/A')

                print(f"   {i}. {symbol}")
                print(f"      ID:          {order_id}")
                print(f"      Type:        {order_type}")
                print(f"      Side:        {side}")
                print(f"      Price:       {price}")
                print(f"      Stop Price:  {stop_price}")
                print(f"      Amount:      {amount}")
                print(f"      Status:      {status}")
                print(f"      ReduceOnly:  {reduce_only}")
                print()

        # 3. Проверяем каждый символ из позиций (если были)
        if open_positions:
            print("=" * 80)
            print("3️⃣ ПРОВЕРКА ОРДЕРОВ ПО СИМВОЛАМ С ОТКРЫТЫМИ ПОЗИЦИЯМИ")
            print("=" * 80)
            print()

            for pos in open_positions:
                symbol = pos['symbol']
                print(f"🔍 Проверка {symbol}:")

                # Открытые ордера для этого символа
                symbol_orders = [o for o in open_orders if o['symbol'] == symbol]

                if symbol_orders:
                    print(f"   ⚠️  Найдено {len(symbol_orders)} открытых ордеров:")
                    for order in symbol_orders:
                        order_type = order.get('type', 'unknown')
                        side = order.get('side', 'unknown')
                        price = order.get('price', 'N/A')
                        reduce_only = order.get('reduceOnly', False)
                        print(f"      • {order_type} {side} @ {price} (reduceOnly={reduce_only})")
                else:
                    print(f"   ⚠️  Ордеров нет, но позиция ОТКРЫТА!")
                    print(f"   🔴 КРИТИЧНО: Позиция БЕЗ ЗАЩИТЫ SL!")
                print()

        # 4. Итоговый вывод
        print("=" * 80)
        print("📊 ИТОГОВЫЙ РЕЗУЛЬТАТ")
        print("=" * 80)
        print()

        if len(open_positions) == 0 and len(open_orders) == 0:
            print("✅ ВСЕ ОТЛИЧНО!")
            print("✅ Позиции закрыты: 0")
            print("✅ Открытых ордеров: 0")
            print("✅ SL ордера корректно отменились при закрытии позиций")
            print()
            print("🎉 Механизм привязки SL к позициям работает ПРАВИЛЬНО!")
        elif len(open_positions) == 0 and len(open_orders) > 0:
            print("⚠️  ПРОБЛЕМА!")
            print("✅ Позиции закрыты: 0")
            print(f"❌ Открытых ордеров: {len(open_orders)}")
            print()
            print("🔴 КРИТИЧНО: SL ордера НЕ отменились при закрытии позиций!")
            print("🔴 Это значит что SL НЕ ПРИВЯЗАНЫ к позициям на бирже!")
            print()
            print("Типы оставшихся ордеров:")
            for order_type, orders in sorted(by_type.items()):
                print(f"   • {order_type}: {len(orders)} ордеров")
        elif len(open_positions) > 0:
            print("⚠️  ПОЗИЦИИ НЕ ВСЕ ЗАКРЫТЫ!")
            print(f"⚠️  Открытых позиций: {len(open_positions)}")
            print(f"📊 Открытых ордеров: {len(open_orders)}")
            print()
            print("Закройте все позиции и запустите скрипт снова.")

        print()
        print("=" * 80)

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
