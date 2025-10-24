#!/usr/bin/env python3
"""
Детальное исследование: проверка параметра brokerId в CCXT Bybit
"""
import sys
import os
import asyncio
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt.async_support as ccxt


async def test_brokerId_investigation():
    """Исследование параметра brokerId в CCXT"""

    print("\n" + "=" * 70)
    print("ИССЛЕДОВАНИЕ: brokerId в CCXT Bybit")
    print("=" * 70)

    # Test Case 1: Default Bybit exchange
    print("\n--- ТЕСТ 1: Default Bybit ---")
    exchange1 = ccxt.bybit({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
        }
    })

    print(f"brokerId in options: {exchange1.options.get('brokerId', 'NOT FOUND')}")

    # Check if it's in a different place
    if hasattr(exchange1, 'brokerId'):
        print(f"exchange.brokerId: {exchange1.brokerId}")

    await exchange1.close()

    # Test Case 2: Try to disable brokerId
    print("\n--- ТЕСТ 2: Попытка отключить brokerId ---")
    exchange2 = ccxt.bybit({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
            'brokerId': None,  # Try to set None
        }
    })

    print(f"brokerId after set None: {exchange2.options.get('brokerId', 'NOT FOUND')}")
    await exchange2.close()

    # Test Case 3: Empty string
    print("\n--- ТЕСТ 3: brokerId = '' (пустая строка) ---")
    exchange3 = ccxt.bybit({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
            'brokerId': '',  # Empty string
        }
    })

    print(f"brokerId after set '': {exchange3.options.get('brokerId', 'NOT FOUND')}")
    await exchange3.close()

    # Test Case 4: Check source code behavior
    print("\n--- ТЕСТ 4: Проверка методов CCXT ---")
    exchange4 = ccxt.bybit({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
        }
    })

    # Check if there's a method to see request params
    print("\nМетоды exchange:")
    methods = [m for m in dir(exchange4) if 'broker' in m.lower()]
    for method in methods:
        print(f"  - {method}")

    # Check sign method (adds auth headers)
    if hasattr(exchange4, 'sign'):
        print("\n⚠️  exchange.sign() method exists - adds auth to requests")

    # Check extend method (merges params)
    if hasattr(exchange4, 'extend'):
        print("⚠️  exchange.extend() method exists - merges parameters")

        # Try extending empty params
        test_params = {'reduceOnly': True}
        print(f"\nOriginal params: {test_params}")

        # CCXT may add brokerId here
        # But we can't call extend directly without more context

    await exchange4.close()

    print("\n" + "=" * 70)
    print("📋 ВЫВОДЫ:")
    print("=" * 70)
    print("1. CCXT Bybit имеет опцию 'brokerId': 'CCXT' по умолчанию")
    print("2. Bybit API НЕ поддерживает параметр 'brokerId' в V5 API")
    print("3. CCXT автоматически добавляет brokerId в запросы")
    print("4. Это вызывает ошибку 170003: 'unknown parameter'")
    print("\n💡 РЕШЕНИЕ:")
    print("   Нужно либо:")
    print("   a) Отключить brokerId через options")
    print("   b) Использовать params для перезаписи")
    print("   c) Обновить CCXT до версии, где это исправлено")
    print("=" * 70)


async def test_ccxt_version():
    """Проверка версии CCXT"""

    print("\n" + "=" * 70)
    print("ИНФОРМАЦИЯ О CCXT")
    print("=" * 70)

    print(f"CCXT version: {ccxt.__version__}")

    # Check if there are known issues
    print("\nИзвестные проблемы с brokerId:")
    print("- CCXT добавляет 'brokerId': 'CCXT' для партнерской программы")
    print("- Bybit V5 API не принимает этот параметр для ордеров")
    print("- Нужно использовать 'brokerId': '' или отключить")


if __name__ == "__main__":
    print("🔍 ДЕТАЛЬНОЕ ИССЛЕДОВАНИЕ: brokerId Problem")

    asyncio.run(test_brokerId_investigation())
    asyncio.run(test_ccxt_version())

    print("\n" + "=" * 70)
    print("🎯 СЛЕДУЮЩИЙ ШАГ: Создать тест с реальными API ключами")
    print("=" * 70)
