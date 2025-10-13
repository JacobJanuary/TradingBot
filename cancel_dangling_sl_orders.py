#!/usr/bin/env python3
"""
Отмена всех висящих SL/TP ордеров без открытых позиций
"""

import asyncio
import ccxt.async_support as ccxt
from config.settings import Config
from datetime import datetime

async def main():
    print("=" * 80)
    print("🧹 ОТМЕНА ВИСЯЩИХ SL/TP ОРДЕРОВ")
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

        # 1. Получаем открытые позиции
        print("=" * 80)
        print("1️⃣ ПРОВЕРКА ОТКРЫТЫХ ПОЗИЦИЙ")
        print("=" * 80)
        print()

        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if float(p.get('contracts', 0)) != 0]
        open_symbols = {p['symbol'] for p in open_positions}

        print(f"📊 Открытых позиций: {len(open_positions)}")
        if open_positions:
            print("⚠️  Открытые позиции:")
            for pos in open_positions:
                print(f"   • {pos['symbol']}: {pos['side']} {pos['contracts']} контрактов")
        else:
            print("✅ Нет открытых позиций")
        print()

        # 2. Получаем все открытые ордера
        print("=" * 80)
        print("2️⃣ АНАЛИЗ ОТКРЫТЫХ ОРДЕРОВ")
        print("=" * 80)
        print()

        open_orders = await exchange.fetch_open_orders()
        print(f"📊 Всего открытых ордеров: {len(open_orders)}")
        print()

        # Группируем ордера
        dangling_orders = []  # Висящие (без позиций)
        active_orders = []    # Активные (с позициями)

        for order in open_orders:
            symbol = order['symbol']
            order_type = order.get('type', 'unknown')
            reduce_only = order.get('reduceOnly', False)

            # SL/TP ордера с reduceOnly
            if order_type in ['stop_market', 'take_profit_market', 'stop_loss', 'stop'] and reduce_only:
                if symbol in open_symbols:
                    active_orders.append(order)
                else:
                    dangling_orders.append(order)

        print(f"✅ Активных SL/TP ордеров (с позициями): {len(active_orders)}")
        print(f"⚠️  Висящих SL/TP ордеров (БЕЗ позиций): {len(dangling_orders)}")
        print()

        if not dangling_orders:
            print("🎉 Висящих ордеров нет! Все чисто.")
            print()
            return

        # 3. Показываем что будем отменять
        print("=" * 80)
        print("3️⃣ СПИСОК ВИСЯЩИХ ОРДЕРОВ ДЛЯ ОТМЕНЫ")
        print("=" * 80)
        print()

        # Группируем по символам
        by_symbol = {}
        for order in dangling_orders:
            symbol = order['symbol']
            if symbol not in by_symbol:
                by_symbol[symbol] = []
            by_symbol[symbol].append(order)

        print(f"📊 Символов с висящими ордерами: {len(by_symbol)}")
        print()

        for symbol, orders in sorted(by_symbol.items()):
            print(f"   {symbol}: {len(orders)} ордеров")
            for order in orders:
                order_type = order['type']
                side = order['side']
                stop_price = order.get('info', {}).get('stopPrice', 'N/A')
                amount = order['amount']
                print(f"      • {order_type} {side} @ {stop_price} ({amount} контрактов) [ID: {order['id']}]")
        print()

        # 4. Подтверждение
        print("=" * 80)
        print("⚠️  ВНИМАНИЕ!")
        print("=" * 80)
        print()
        print(f"Будет отменено: {len(dangling_orders)} висящих SL/TP ордеров")
        print(f"Активные ордера (с позициями): {len(active_orders)} - НЕ будут тронуты")
        print()
        print("Эти ордера висят без позиций и должны быть отменены.")
        print()

        confirmation = input("Продолжить? (yes/no): ").strip().lower()
        if confirmation != 'yes':
            print("❌ Отменено пользователем")
            return

        print()
        print("=" * 80)
        print("4️⃣ ОТМЕНА ОРДЕРОВ")
        print("=" * 80)
        print()

        # 5. Отменяем ордера
        canceled = 0
        failed = 0
        errors = []

        for i, order in enumerate(dangling_orders, 1):
            symbol = order['symbol']
            order_id = order['id']
            order_type = order['type']
            side = order['side']

            try:
                await exchange.cancel_order(order_id, symbol)
                print(f"   [{i}/{len(dangling_orders)}] ✅ {symbol} - {order_type} {side} (ID: {order_id})")
                canceled += 1

                # Небольшая задержка для rate limit
                if i % 10 == 0:
                    await asyncio.sleep(0.5)

            except Exception as e:
                error_msg = str(e)
                print(f"   [{i}/{len(dangling_orders)}] ❌ {symbol} - {order_type} {side} (ID: {order_id})")
                print(f"      Ошибка: {error_msg[:80]}")
                failed += 1
                errors.append({
                    'symbol': symbol,
                    'order_id': order_id,
                    'error': error_msg
                })

        print()
        print("=" * 80)
        print("📊 ИТОГОВЫЙ РЕЗУЛЬТАТ")
        print("=" * 80)
        print()

        print(f"✅ Успешно отменено: {canceled}")
        print(f"❌ Ошибок отмены: {failed}")
        print()

        if errors:
            print("Ошибки:")
            for err in errors[:10]:  # Первые 10 ошибок
                print(f"   • {err['symbol']} (ID: {err['order_id']}): {err['error'][:60]}")
            if len(errors) > 10:
                print(f"   ... и еще {len(errors) - 10} ошибок")
            print()

        if canceled == len(dangling_orders):
            print("🎉 ВСЕ ВИСЯЩИЕ ОРДЕРА УСПЕШНО ОТМЕНЕНЫ!")
        elif canceled > 0:
            print("⚠️  Частичный успех - некоторые ордера не удалось отменить")
        else:
            print("❌ Не удалось отменить ни одного ордера")

        print()

        # 6. Проверяем результат
        print("=" * 80)
        print("5️⃣ ФИНАЛЬНАЯ ПРОВЕРКА")
        print("=" * 80)
        print()

        final_orders = await exchange.fetch_open_orders()
        final_sl_tp = [o for o in final_orders
                       if o['type'] in ['stop_market', 'take_profit_market', 'stop_loss', 'stop']
                       and o.get('reduceOnly', False)
                       and o['symbol'] not in open_symbols]

        print(f"📊 Осталось висящих SL/TP ордеров: {len(final_sl_tp)}")
        print()

        if len(final_sl_tp) == 0:
            print("✅ ОТЛИЧНО! Висящих ордеров не осталось.")
        else:
            print("⚠️  Остались висящие ордера (возможно появились новые или не удалось отменить):")
            for order in final_sl_tp[:10]:
                print(f"   • {order['symbol']}: {order['type']} {order['side']} (ID: {order['id']})")

        print()
        print("=" * 80)

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
