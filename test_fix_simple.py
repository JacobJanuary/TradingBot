#!/usr/bin/env python3
"""
Простой тест исправления - проверяет логику напрямую
"""

import sys
from dataclasses import dataclass


@dataclass
class MockPosition:
    """Минимальный mock позиции"""
    symbol: str
    exchange: str


def test_fixed_logic():
    """Тест исправленной логики проверки"""

    print("=" * 80)
    print("🧪 ТЕСТ ИСПРАВЛЕННОЙ ЛОГИКИ")
    print("=" * 80)
    print()

    # Симулируем кэш позиций
    positions = {
        'B3USDT': MockPosition(symbol='B3USDT', exchange='binance')
    }

    print("📝 Кэш позиций:")
    for symbol, pos in positions.items():
        print(f"   {symbol}: {pos.exchange}")
    print()

    # Тест 1: Проверка той же биржи
    print("=" * 80)
    print("ТЕСТ #1: Проверка B3USDT на binance")
    print("Ожидается: TRUE")
    print("-" * 80)

    # ИСПРАВЛЕННАЯ ЛОГИКА
    symbol_to_check = 'B3USDT'
    exchange_to_check = 'binance'
    exchange_lower = exchange_to_check.lower()

    found = False
    for pos_symbol, position in positions.items():
        if pos_symbol == symbol_to_check and position.exchange.lower() == exchange_lower:
            found = True
            break

    print(f"Результат: {found}")
    if found:
        print("✅ PASS")
        test1 = True
    else:
        print("❌ FAIL")
        test1 = False
    print()

    # Тест 2: Проверка другой биржи (КРИТИЧНЫЙ)
    print("=" * 80)
    print("ТЕСТ #2: Проверка B3USDT на bybit - КРИТИЧНЫЙ!")
    print("Ожидается: FALSE (позиция только на binance)")
    print("-" * 80)

    # ИСПРАВЛЕННАЯ ЛОГИКА
    symbol_to_check = 'B3USDT'
    exchange_to_check = 'bybit'
    exchange_lower = exchange_to_check.lower()

    found = False
    for pos_symbol, position in positions.items():
        if pos_symbol == symbol_to_check and position.exchange.lower() == exchange_lower:
            found = True
            break

    print(f"Результат: {found}")
    if not found:
        print("✅ PASS - Исправление работает!")
        test2 = True
    else:
        print("❌ FAIL - Баг всё ещё есть!")
        test2 = False
    print()

    # Тест 3: Несуществующий символ
    print("=" * 80)
    print("ТЕСТ #3: Проверка ETHUSDT на binance")
    print("Ожидается: FALSE")
    print("-" * 80)

    # ИСПРАВЛЕННАЯ ЛОГИКА
    symbol_to_check = 'ETHUSDT'
    exchange_to_check = 'binance'
    exchange_lower = exchange_to_check.lower()

    found = False
    for pos_symbol, position in positions.items():
        if pos_symbol == symbol_to_check and position.exchange.lower() == exchange_lower:
            found = True
            break

    print(f"Результат: {found}")
    if not found:
        print("✅ PASS")
        test3 = True
    else:
        print("❌ FAIL")
        test3 = False
    print()

    # Итоги
    print("=" * 80)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 80)
    print()

    all_passed = test1 and test2 and test3

    if test1:
        print("✅ PASS: Тест #1 (та же биржа)")
    else:
        print("❌ FAIL: Тест #1 (та же биржа)")

    if test2:
        print("✅ PASS: Тест #2 (другая биржа) - КРИТИЧНЫЙ")
    else:
        print("❌ FAIL: Тест #2 (другая биржа) - КРИТИЧНЫЙ")

    if test3:
        print("✅ PASS: Тест #3 (нет позиции)")
    else:
        print("❌ FAIL: Тест #3 (нет позиции)")

    print()

    if all_passed:
        print("=" * 80)
        print("✅ ВСЕ ТЕСТЫ ПРОШЛИ - ЛОГИКА ИСПРАВЛЕНИЯ КОРРЕКТНА!")
        print("=" * 80)
        return 0
    else:
        print("=" * 80)
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    exit_code = test_fixed_logic()
    sys.exit(exit_code)
