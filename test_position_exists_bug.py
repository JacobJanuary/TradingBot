#!/usr/bin/env python3
"""
Test to verify the _position_exists() bug theory

THEORY:
The method _position_exists(symbol, exchange) at line 1349 checks:
    if symbol in self.positions:
        return True

Without verifying the exchange parameter.

This means if B3USDT exists on binance in cache, calling
_position_exists('B3USDT', 'bybit') will incorrectly return TRUE.

TEST:
1. Add B3USDT position on binance to mock cache
2. Call _position_exists('B3USDT', 'binance') - expect TRUE ✅
3. Call _position_exists('B3USDT', 'bybit') - expect FALSE (critical test)
4. If step 3 returns TRUE, bug confirmed ❌

EXIT CODES:
- 0: Bug NOT found (theory disproven)
- 1: Bug CONFIRMED (fix needed)
- 2: Test error
"""

import asyncio
import sys
from dataclasses import dataclass
from typing import Dict


@dataclass
class MockPosition:
    """Minimal position mock"""
    symbol: str
    exchange: str
    id: int = 1


class MockRepository:
    """Mock repository that always returns None"""

    async def get_open_position(self, symbol: str, exchange: str):
        """Always return None - we're testing cache logic only"""
        return None


class SimplifiedPositionManager:
    """
    Simplified version with only the _position_exists method
    to test the bug in isolation

    This is an EXACT COPY of the buggy code from position_manager.py:1339-1359
    """

    def __init__(self):
        self.positions: Dict[str, MockPosition] = {}
        self.check_locks: Dict[str, asyncio.Lock] = {}
        self.repository = MockRepository()

    async def _position_exists(self, symbol: str, exchange: str) -> bool:
        """
        EXACT COPY of the buggy code from position_manager.py line 1339-1359
        """
        lock_key = f"{exchange}_{symbol}"

        if lock_key not in self.check_locks:
            self.check_locks[lock_key] = asyncio.Lock()

        async with self.check_locks[lock_key]:
            # Check local tracking
            if symbol in self.positions:  # ← BUG! Doesn't check exchange!
                return True

            # Check database
            db_position = await self.repository.get_open_position(symbol, exchange)
            if db_position:
                return True

            return False


async def run_test():
    """Run the bug verification test"""

    print("=" * 80)
    print("🧪 ТЕСТ БАГА В _position_exists()")
    print("=" * 80)
    print()
    print("ТЕОРИЯ:")
    print("  Метод _position_exists(symbol, exchange) проверяет:")
    print("    if symbol in self.positions:")
    print("        return True")
    print()
    print("  Без проверки параметра exchange!")
    print()
    print("  Это значит если B3USDT существует на binance в кэше,")
    print("  вызов _position_exists('B3USDT', 'bybit') вернет TRUE (неправильно!)")
    print()

    # Setup
    manager = SimplifiedPositionManager()

    # Add B3USDT position on BINANCE to cache
    manager.positions['B3USDT'] = MockPosition(
        symbol='B3USDT',
        exchange='binance',
        id=874
    )

    print("📝 Настройка:")
    print(f"   Добавили в кэш: B3USDT на binance")
    print(f"   Содержимое кэша: {list(manager.positions.keys())}")
    print()

    # Test 1: Check same symbol and exchange (should return TRUE)
    print("=" * 80)
    print("ТЕСТ #1: _position_exists('B3USDT', 'binance')")
    print("Ожидается: TRUE (позиция существует на binance)")
    print("-" * 80)

    result1 = await manager._position_exists('B3USDT', 'binance')
    status1 = "✅ PASS" if result1 else "❌ FAIL"
    print(f"Результат: {result1}")
    print(f"{status1}")
    print()

    if not result1:
        print("❌ ТЕСТ ПРОВАЛЕН: Должен был вернуть TRUE для существующей позиции")
        return 2

    # Test 2: Check same symbol, DIFFERENT exchange (should return FALSE)
    print("=" * 80)
    print("ТЕСТ #2: _position_exists('B3USDT', 'bybit') - КРИТИЧНЫЙ ТЕСТ!")
    print("Ожидается: FALSE (позиция существует на binance, НЕ на bybit)")
    print("=" * 80)
    print()
    print("🔍 КРИТИЧНЫЙ ТЕСТ - Это показывает баг:")
    print()

    result2 = await manager._position_exists('B3USDT', 'bybit')

    print(f"Результат: {result2}")
    print()

    if result2:
        # Bug confirmed!
        print("🐛 БАГ ПОДТВЕРЖДЁН!")
        print()
        print("❌ _position_exists('B3USDT', 'bybit') вернул TRUE")
        print("   но B3USDT существует только на binance, НЕ на bybit!")
        print()
        print("📊 ПРИЧИНА:")
        print("   Строка 1349 в position_manager.py:")
        print("   ```python")
        print("   if symbol in self.positions:  # ← БАГ!")
        print("       return True")
        print("   ```")
        print()
        print("   Должно быть:")
        print("   ```python")
        print("   for pos_symbol, position in self.positions.items():")
        print("       if pos_symbol == symbol and position.exchange == exchange:")
        print("           return True")
        print("   ```")
        print()
        print("💥 ПОСЛЕДСТВИЯ:")
        print("   - Signal processor вызывает _position_exists('B3USDT', 'bybit')")
        print("   - Возвращает TRUE хотя позиция на binance")
        print("   - Выполнение сигнала блокируется как дубликат")
        print("   - Позиция никогда не открывается на bybit")
        print()
        return 1  # Bug confirmed
    else:
        # Bug NOT found
        print("✅ БАГ НЕ ОБНАРУЖЕН")
        print()
        print("_position_exists('B3USDT', 'bybit') правильно вернул FALSE")
        print()
        print("⚠️  Теория опровергнута - баг в другом месте")
        print()
        return 0  # Bug not found


async def main():
    try:
        exit_code = await run_test()

        print()
        print("=" * 80)
        print("ТЕСТ ЗАВЕРШЁН")
        print("=" * 80)
        print()

        if exit_code == 0:
            print("✅ Теория опровергнута - баг НЕ в _position_exists()")
            print("   Нужно исследовать другие причины")
        elif exit_code == 1:
            print("🐛 Баг подтверждён - _position_exists() не проверяет exchange")
            print("   Требуется исправление в core/position_manager.py строка 1349")
        else:
            print("❌ Ошибка теста")

        print()
        sys.exit(exit_code)

    except Exception as e:
        print()
        print("=" * 80)
        print("❌ ОШИБКА ТЕСТА")
        print("=" * 80)
        print(f"Исключение: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
