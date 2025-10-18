#!/usr/bin/env python3
"""
Тест проверки исправления _position_exists()

Этот тест использует РЕАЛЬНЫЙ код из core/position_manager.py
чтобы убедиться что исправление работает.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import TradingConfig
from core.position_manager import PositionManager, PositionState
from database.repository import Repository as TradingRepository
from websocket.event_router import EventRouter


class MockExchangeManager:
    """Mock exchange"""
    def __init__(self, exchange_id: str):
        self.id = exchange_id
        self.exchange = self  # For compatibility

    async def fetch_positions(self, **params):
        return []


class MockRepository:
    """Mock repository"""
    async def get_open_position(self, symbol: str, exchange: str):
        return None


class MockEventRouter:
    """Mock event router"""
    async def route_event(self, event_type, data):
        pass


async def test_fix():
    print("=" * 80)
    print("🧪 ТЕСТ ПРОВЕРКИ ИСПРАВЛЕНИЯ _position_exists()")
    print("=" * 80)
    print()
    print("Используем РЕАЛЬНЫЙ код из core/position_manager.py")
    print()

    # Создаём минимальную конфигурацию
    config = TradingConfig()

    # Создаём mock exchanges
    exchanges = {
        'binance': MockExchangeManager('binance'),
        'bybit': MockExchangeManager('bybit')
    }

    # Создаём mock repository и event router
    repository = MockRepository()
    event_router = MockEventRouter()

    # Создаём РЕАЛЬНЫЙ PositionManager
    pm = PositionManager(
        config=config,
        exchanges=exchanges,
        repository=repository,
        event_router=event_router
    )

    print("✅ PositionManager создан с реальным кодом")
    print()

    # Добавляем позицию B3USDT на BINANCE в кэш
    print("📝 Добавляем B3USDT позицию на BINANCE в кэш")
    position_state = PositionState(
        id=874,
        symbol='B3USDT',
        exchange='binance',
        side='short',
        quantity=Decimal('100'),
        entry_price=Decimal('0.002167'),
        current_price=Decimal('0.002167'),
        unrealized_pnl=Decimal('0'),
        unrealized_pnl_percent=Decimal('0'),
        has_stop_loss=True,
        stop_loss_price=Decimal('0.00221'),
        has_trailing_stop=True,
        trailing_activated=True,
        opened_at=datetime.now(),
        age_hours=1
    )

    pm.positions['B3USDT'] = position_state
    print(f"✅ Позиция добавлена: {position_state.symbol} на {position_state.exchange}")
    print()

    # ТЕСТ #1: Проверка на той же бирже
    print("=" * 80)
    print("ТЕСТ #1: _position_exists('B3USDT', 'binance')")
    print("Ожидается: TRUE (позиция существует на binance)")
    print("-" * 80)

    result1 = await pm._position_exists('B3USDT', 'binance')
    print(f"Результат: {result1}")

    if result1:
        print("✅ PASS: Правильно вернул TRUE")
        test1_passed = True
    else:
        print("❌ FAIL: Должен был вернуть TRUE!")
        test1_passed = False
    print()

    # ТЕСТ #2: Проверка на ДРУГОЙ бирже (КРИТИЧНЫЙ!)
    print("=" * 80)
    print("ТЕСТ #2: _position_exists('B3USDT', 'bybit') - КРИТИЧНЫЙ ТЕСТ!")
    print("Ожидается: FALSE (позиция только на binance, НЕ на bybit)")
    print("=" * 80)
    print()

    result2 = await pm._position_exists('B3USDT', 'bybit')
    print(f"Результат: {result2}")
    print()

    if result2:
        print("❌ FAIL: ИСПРАВЛЕНИЕ НЕ РАБОТАЕТ!")
        print("   Вернул TRUE хотя позиция только на binance!")
        print("   Баг всё ещё присутствует!")
        test2_passed = False
        bug_still_exists = True
    else:
        print("✅ PASS: Правильно вернул FALSE!")
        print("   Исправление работает корректно!")
        test2_passed = True
        bug_still_exists = False
    print()

    # ТЕСТ #3: Несуществующий символ
    print("=" * 80)
    print("ТЕСТ #3: _position_exists('ETHUSDT', 'binance')")
    print("Ожидается: FALSE (позиции нет)")
    print("-" * 80)

    result3 = await pm._position_exists('ETHUSDT', 'binance')
    print(f"Результат: {result3}")

    if not result3:
        print("✅ PASS: Правильно вернул FALSE")
        test3_passed = True
    else:
        print("❌ FAIL: Должен был вернуть FALSE!")
        test3_passed = False
    print()

    # Итоги
    print("=" * 80)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 80)
    print()

    tests = [
        ("Тест #1 (та же биржа)", test1_passed),
        ("Тест #2 (другая биржа) - КРИТИЧНЫЙ", test2_passed),
        ("Тест #3 (нет позиции)", test3_passed)
    ]

    for name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    passed_count = sum(1 for _, p in tests if p)
    print()
    print(f"📈 Результат: {passed_count}/3 тестов прошли")
    print()

    if bug_still_exists:
        print("=" * 80)
        print("🔴 ИСПРАВЛЕНИЕ НЕ РАБОТАЕТ - БАГ ВСЁ ЕЩЁ ПРИСУТСТВУЕТ!")
        print("=" * 80)
        return 1
    elif passed_count == 3:
        print("=" * 80)
        print("✅ ВСЕ ТЕСТЫ ПРОШЛИ - ИСПРАВЛЕНИЕ РАБОТАЕТ!")
        print("=" * 80)
        return 0
    else:
        print("=" * 80)
        print("⚠️  НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        print("=" * 80)
        return 2


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(test_fix())
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
