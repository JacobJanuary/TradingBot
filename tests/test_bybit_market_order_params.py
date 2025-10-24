#!/usr/bin/env python3
"""
Тестовый скрипт для исследования ошибки Bybit 170003 "unknown parameter"
Проверяет какие параметры вызывают ошибку при создании market ордера
"""
import sys
import os
import asyncio
import json
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt.async_support as ccxt


async def test_bybit_market_order():
    """Тест различных комбинаций параметров для market ордера Bybit"""

    print("\n" + "=" * 70)
    print("ТЕСТ: Bybit Market Order Parameters")
    print("=" * 70)

    # Initialize Bybit testnet
    exchange = ccxt.bybit({
        'apiKey': 'test_key',  # Replace with your testnet API key if testing
        'secret': 'test_secret',
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
        }
    })

    # Set to testnet (if you have credentials)
    exchange.set_sandbox_mode(True)

    test_symbol = 'BTC/USDT:USDT'
    test_side = 'sell'
    test_amount = 0.001

    # Test cases
    test_cases = [
        {
            'name': 'CURRENT CODE (reduceOnly: True)',
            'params': {'reduceOnly': True}
        },
        {
            'name': 'Empty params',
            'params': {}
        },
        {
            'name': 'reduceOnly as string "true"',
            'params': {'reduceOnly': 'true'}
        },
        {
            'name': 'reduceOnly: False',
            'params': {'reduceOnly': False}
        },
        {
            'name': 'reduce_only (snake_case)',
            'params': {'reduce_only': True}
        },
        {
            'name': 'With positionIdx=0',
            'params': {'reduceOnly': True, 'positionIdx': 0}
        },
        {
            'name': 'With category=linear',
            'params': {'reduceOnly': True, 'category': 'linear'}
        },
        {
            'name': 'Without reduceOnly, with category',
            'params': {'category': 'linear'}
        },
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- ТЕСТ {i}: {test_case['name']} ---")
        print(f"Параметры: {json.dumps(test_case['params'], indent=2)}")

        try:
            # Note: This will fail without valid API keys
            # But we can see what CCXT sends

            # Enable verbose mode to see requests
            exchange.verbose = True

            # Try to create order (will fail on testnet without position)
            result = await exchange.create_order(
                symbol=test_symbol,
                type='market',
                side=test_side,
                amount=test_amount,
                params=test_case['params']
            )

            print(f"✅ SUCCESS: {result}")

        except ccxt.AuthenticationError as e:
            print(f"⚠️  AUTH ERROR (expected без API ключей): {e}")
            # This is expected without real API keys

        except ccxt.ExchangeError as e:
            error_str = str(e)
            print(f"❌ EXCHANGE ERROR: {error_str}")

            # Check for error code 170003
            if '170003' in error_str or 'unknown parameter' in error_str.lower():
                print(f"🔴 ПРОБЛЕМА НАЙДЕНА! Это тот же error 170003!")
                print(f"   Параметры вызвавшие ошибку: {test_case['params']}")

        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}")

        finally:
            exchange.verbose = False

    await exchange.close()

    print("\n" + "=" * 70)
    print("ТЕСТЫ ЗАВЕРШЕНЫ")
    print("=" * 70)


async def test_ccxt_param_conversion():
    """Проверка как CCXT конвертирует параметры для Bybit"""

    print("\n" + "=" * 70)
    print("ТЕСТ: CCXT Parameter Conversion для Bybit")
    print("=" * 70)

    exchange = ccxt.bybit({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
        }
    })

    # Check if CCXT has any built-in transformations
    print("\nCCXT Bybit options:")
    print(json.dumps(exchange.options, indent=2, default=str))

    print("\nCCXT Bybit default params:")
    if hasattr(exchange, 'defaultParams'):
        print(json.dumps(exchange.defaultParams, indent=2, default=str))
    else:
        print("No defaultParams attribute")

    # Check if there's a method that shows what params will be sent
    print("\nCCXT Bybit has_feature:")
    features = [
        'createMarketOrder',
        'createOrder',
        'reduceOnly',
    ]
    for feature in features:
        if hasattr(exchange, 'has'):
            print(f"  {feature}: {exchange.has.get(feature, 'N/A')}")

    await exchange.close()


async def main():
    """Run all tests"""
    print("🔍 ИССЛЕДОВАНИЕ: Bybit Error 170003 - Unknown Parameter")

    # Test 1: CCXT param conversion
    await test_ccxt_param_conversion()

    # Test 2: Market order with different params
    # Note: Comment out if you don't have API keys
    # await test_bybit_market_order()

    print("\n" + "=" * 70)
    print("📋 СЛЕДУЮЩИЕ ШАГИ:")
    print("=" * 70)
    print("1. Если у вас есть Bybit testnet API ключи:")
    print("   - Раскомментируйте await test_bybit_market_order()")
    print("   - Вставьте ваши API ключи")
    print("   - Запустите снова")
    print("")
    print("2. Проверьте вывод CCXT options")
    print("   - Ищите любые дефолтные параметры")
    print("")
    print("3. Попробуйте запросить Bybit API напрямую (без CCXT)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
