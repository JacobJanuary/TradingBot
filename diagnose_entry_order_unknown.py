#!/usr/bin/env python3
"""
Диагностика: Entry order failed: unknown
Проверяет что возвращает биржа при создании ордера
"""

import asyncio
import ccxt.async_support as ccxt
from config.settings import Config
from core.exchange_response_adapter import ExchangeResponseAdapter
import json

async def test_small_order():
    """Тестирует создание ордера с маленьким количеством"""

    config = Config()

    # Создаем exchange instance
    exchange_config = None
    for exch in config.exchanges:
        if exch.name == 'bybit' and exch.enabled:
            exchange_config = exch
            break

    if not exchange_config:
        print("❌ Bybit не найден в конфигурации")
        return

    exchange = ccxt.bybit({
        'apiKey': exchange_config.api_key,
        'secret': exchange_config.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': exchange_config.testnet
        }
    })

    print("="*80)
    print("🔍 ТЕСТИРОВАНИЕ: Entry order failed: unknown")
    print("="*80)
    print()

    try:
        # Test 1: Создание ордера с очень маленьким количеством (должен вернуть ошибку)
        print("Test 1: Создание market order с маленьким количеством")
        print("-"*80)

        symbol = 'SUNDOG/USDT:USDT'
        side = 'sell'
        amount = 0.1  # Очень маленькое количество

        print(f"Symbol: {symbol}")
        print(f"Side: {side}")
        print(f"Amount: {amount}")
        print()

        try:
            raw_order = await exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=amount
            )

            print("✅ Ордер создан!")
            print()
            print("RAW ORDER:")
            print(json.dumps(raw_order, indent=2, default=str))
            print()

            # Нормализуем ордер
            normalized = ExchangeResponseAdapter.normalize_order(raw_order, 'bybit')

            print("NORMALIZED ORDER:")
            print(f"  ID: {normalized.id}")
            print(f"  Symbol: {normalized.symbol}")
            print(f"  Side: {normalized.side}")
            print(f"  Status: {normalized.status}")
            print(f"  Type: {normalized.type}")
            print(f"  Amount: {normalized.amount}")
            print(f"  Filled: {normalized.filled}")
            print(f"  Price: {normalized.price}")
            print()

            # Проверяем is_order_filled
            is_filled = ExchangeResponseAdapter.is_order_filled(normalized)
            print(f"is_order_filled: {is_filled}")
            print()

        except ccxt.InsufficientFunds as e:
            print(f"❌ InsufficientFunds: {e}")
            print()

        except ccxt.InvalidOrder as e:
            print(f"❌ InvalidOrder: {e}")
            print()

        except Exception as e:
            print(f"❌ Exception: {type(e).__name__}")
            print(f"   Message: {e}")
            print()

            # Проверим есть ли в исключении данные
            if hasattr(e, 'args') and len(e.args) > 0:
                print(f"   Args: {e.args}")

            print()

        # Test 2: Проверим минимальные лимиты для SUNDOGUSDT
        print()
        print("Test 2: Минимальные лимиты для SUNDOGUSDT")
        print("-"*80)

        markets = await exchange.load_markets()

        if symbol in markets:
            market = markets[symbol]
            print(f"Market info for {symbol}:")
            print(f"  Min amount: {market['limits']['amount']['min']}")
            print(f"  Max amount: {market['limits']['amount']['max']}")
            print(f"  Min cost: {market['limits']['cost']['min']}")
            print(f"  Max cost: {market['limits']['cost']['max']}")
            print(f"  Contract size: {market.get('contractSize', 'N/A')}")
            print(f"  Precision amount: {market['precision']['amount']}")
            print(f"  Precision price: {market['precision']['price']}")
            print()

        # Test 3: Попробуем создать ордер с правильным количеством
        print()
        print("Test 3: Создание market order с правильным количеством")
        print("-"*80)

        # Проверим баланс
        balance = await exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        free_usdt = usdt_balance.get('free', 0)

        print(f"USDT Balance: {free_usdt}")
        print()

        if free_usdt < 1:
            print("⚠️ Недостаточно USDT для тестового ордера")
        else:
            # Рассчитаем правильное количество
            if symbol in markets:
                min_amount = market['limits']['amount']['min']
                min_cost = market['limits']['cost']['min']

                # Используем current price для расчета
                ticker = await exchange.fetch_ticker(symbol)
                current_price = ticker['last']

                # Количество должно быть >= min_amount И стоимость >= min_cost
                amount_from_cost = min_cost / current_price
                proper_amount = max(min_amount, amount_from_cost) * 2  # x2 для гарантии

                print(f"Current price: {current_price}")
                print(f"Min amount: {min_amount}")
                print(f"Min cost: {min_cost}")
                print(f"Calculated proper amount: {proper_amount}")
                print()

                print(f"⚠️ Для реального теста раскомментируйте код ниже:")
                print()
                print("# try:")
                print(f"#     raw_order = await exchange.create_market_order(")
                print(f"#         symbol='{symbol}',")
                print(f"#         side='{side}',")
                print(f"#         amount={proper_amount}")
                print("# )")
                print("#     print('✅ Ордер создан!')")
                print("#     print(json.dumps(raw_order, indent=2, default=str))")
                print("# except Exception as e:")
                print("#     print(f'❌ Error: {e}')")
                print()

    finally:
        await exchange.close()

    print("="*80)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_small_order())
