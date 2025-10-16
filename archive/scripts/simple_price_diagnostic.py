#!/usr/bin/env python3
"""
Простая диагностика цен для ошибки 170193
Проверяет: возвращает ли Bybit testnet price=0 или проблема в округлении
"""
import asyncio
import ccxt.async_support as ccxt
from decimal import Decimal
import os
from dotenv import load_dotenv

load_dotenv()

async def check_price_issue():
    """Проверить цены на символах с ошибкой 170193"""

    # Инициализация Bybit testnet
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_TESTNET_API_KEY'),
        'secret': os.getenv('BYBIT_TESTNET_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })
    exchange.set_sandbox_mode(True)

    # Символы из логов с ошибкой 170193 (примеры)
    test_symbols = [
        'XDC/USDT:USDT',  # Основной символ с ошибкой из логов
        'HNT/USDT:USDT',
        'AUCTION/USDT:USDT',
        'GALA/USDT:USDT',
        'ZEN/USDT:USDT'
    ]

    print("=" * 70)
    print("ДИАГНОСТИКА ЦЕН - Bybit Testnet")
    print("=" * 70)

    results = {
        'zero_prices': [],
        'valid_prices': [],
        'precision_issues': []
    }

    for symbol in test_symbols:
        try:
            # Получить текущую цену
            ticker = await exchange.fetch_ticker(symbol)
            current_price = ticker['last']

            # Получить market info
            markets = await exchange.load_markets()
            market = markets[symbol]
            price_precision = market['precision']['price']
            min_price = market['limits']['price']['min']

            print(f"\n📊 {symbol}")
            print(f"   Current Price: {current_price}")
            print(f"   Price Precision: {price_precision}")
            print(f"   Min Price: {min_price}")

            # Проверка 1: Нулевая цена?
            if current_price == 0 or current_price is None:
                print(f"   ❌ ZERO PRICE - testnet без ликвидности")
                results['zero_prices'].append(symbol)
            else:
                results['valid_prices'].append(symbol)

                # Проверка 2: Округление
                decimal_price = Decimal(str(current_price))

                # Симуляция расчета как в aged_position_manager.py
                distance = Decimal('0.015')  # 1.5%
                target_price = decimal_price * (Decimal('1') - distance)

                # Округление вниз (как сейчас в коде)
                rounded_down = float(target_price)

                # Вычислить количество знаков после запятой
                from math import log10
                if price_precision > 0:
                    decimals = int(-log10(price_precision))
                else:
                    decimals = 8  # По умолчанию

                # Округление с правильной точностью
                rounded_precise = round(float(target_price), decimals)

                print(f"   Target Price (calc): {target_price}")
                print(f"   Rounded Down: {rounded_down}")
                print(f"   Rounded Precise: {rounded_precise}")
                print(f"   Min Allowed: {min_price}")

                if rounded_precise < min_price:
                    print(f"   ⚠️ PRECISION ISSUE - округление < min_price")
                    results['precision_issues'].append(symbol)
                else:
                    print(f"   ✅ OK - нет проблем с округлением")

        except Exception as e:
            print(f"\n❌ {symbol}: Ошибка - {e}")

    await exchange.close()

    # Итоговый отчет
    print("\n" + "=" * 70)
    print("РЕЗУЛЬТАТЫ ДИАГНОСТИКИ")
    print("=" * 70)

    print(f"\n🔴 Zero Prices (testnet без ликвидности): {len(results['zero_prices'])}")
    for s in results['zero_prices']:
        print(f"   - {s}")

    print(f"\n🟡 Precision Issues (округление): {len(results['precision_issues'])}")
    for s in results['precision_issues']:
        print(f"   - {s}")

    print(f"\n🟢 Valid Prices (нет проблем): {len(results['valid_prices']) - len(results['precision_issues'])}")

    # Рекомендация
    print("\n" + "=" * 70)
    print("РЕКОМЕНДАЦИЯ")
    print("=" * 70)

    if len(results['zero_prices']) > len(results['precision_issues']):
        print("\n✅ Основная проблема: Testnet возвращает price=0")
        print("   Решение: Добавить проверку на нулевые цены в _get_current_price()")
        print("   Файл: core/aged_position_manager.py")
        print("   Время: 15 минут")
    elif len(results['precision_issues']) > 0:
        print("\n✅ Основная проблема: Округление ниже min_price")
        print("   Решение: Использовать ceil округление для buy orders")
        print("   Файл: core/aged_position_manager.py")
        print("   Время: 20 минут")
    else:
        print("\n✅ Проблемы не обнаружены на проверенных символах")
        print("   Возможно, ошибка возникает редко или на других символах")

    print("\n" + "=" * 70)

if __name__ == '__main__':
    asyncio.run(check_price_issue())
