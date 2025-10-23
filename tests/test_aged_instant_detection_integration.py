#!/usr/bin/env python3
"""
Интеграционный тест мгновенного обнаружения с реальными компонентами
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Настройка логирования для проверки
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def integration_test():
    """Полный интеграционный тест с симуляцией реальной работы"""

    print("=" * 60)
    print("ИНТЕГРАЦИОННЫЙ ТЕСТ: Мгновенное обнаружение aged позиций")
    print("=" * 60)

    # Импортируем после настройки логирования
    from core.position_manager import PositionManager, PositionState
    from core.aged_position_monitor_v2 import AgedPositionMonitorV2
    from core.unified_protection import UnifiedProtection
    from config.settings import TradingConfig
    from unittest.mock import Mock, AsyncMock

    # Создаем реальные компоненты
    config = TradingConfig()
    config.max_position_age_hours = 3

    # Моки для внешних зависимостей
    mock_repo = AsyncMock()
    mock_exchanges = {
        'binance': Mock(),
        'bybit': Mock()
    }
    mock_event_router = Mock()

    # Создаем PositionManager
    position_manager = PositionManager(
        config,
        mock_exchanges,
        mock_repo,
        mock_event_router
    )

    # Создаем AgedPositionMonitorV2
    aged_monitor = AgedPositionMonitorV2(
        repository=mock_repo,
        exchange_manager=mock_exchanges,
        position_manager=position_manager
    )

    # Создаем UnifiedProtection
    unified_protection = UnifiedProtection(
        repository=mock_repo,
        exchanges=mock_exchanges,
        position_manager=position_manager,
        config=config
    )

    # Связываем компоненты
    position_manager.unified_protection = {
        'aged_monitor': aged_monitor
    }

    print("\n1. Создание тестовых позиций...")

    # Создаем позиции разного возраста
    test_positions = [
        ("BTCUSDT", 1.5, "молодая (1.5ч)"),    # Не aged
        ("ETHUSDT", 2.9, "почти aged (2.9ч)"),  # Не aged
        ("SOLUSDT", 3.1, "только что aged (3.1ч)"),  # Aged!
        ("AVAXUSDT", 5.0, "давно aged (5ч)"),   # Aged!
        ("DOTUSDT", 8.5, "очень старая (8.5ч)")  # Aged!
    ]

    detection_results = []

    for symbol, age_hours, description in test_positions:
        # Создаем позицию
        position = PositionState(
            id=f"test_{symbol}",
            symbol=symbol,
            exchange="binance",
            side="long",
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            current_price=Decimal("95"),
            unrealized_pnl=Decimal("-5"),
            unrealized_pnl_percent=Decimal("-5"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=age_hours)
        )

        position_manager.positions[symbol] = position
        print(f"  ✅ Создана позиция {symbol}: {description}")

    print("\n2. Симуляция WebSocket обновлений...")

    # Счетчик обнаружений до
    initial_count = getattr(position_manager, 'instant_aged_detections', 0)

    # Симулируем WebSocket обновления для всех позиций
    for symbol, age_hours, description in test_positions:
        ws_data = {
            'symbol': f'{symbol[:-4]}/USDT:USDT',
            'mark_price': 95.0
        }

        print(f"\n  Обработка {symbol} ({description})...")

        # Обрабатываем обновление
        await position_manager._on_position_update(ws_data)

        # Проверяем результат
        is_tracked = symbol in aged_monitor.aged_targets
        should_be_aged = age_hours > 3.0

        if is_tracked:
            print(f"    ⚡ ОБНАРУЖЕНА как aged!")
        else:
            print(f"    ⏭️  Пропущена (не aged)")

        # Сохраняем результат
        detection_results.append({
            'symbol': symbol,
            'age_hours': age_hours,
            'description': description,
            'should_be_aged': should_be_aged,
            'is_tracked': is_tracked,
            'correct': is_tracked == should_be_aged
        })

    # Финальный счетчик
    final_count = getattr(position_manager, 'instant_aged_detections', 0)

    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)

    print("\nОбнаружение позиций:")
    for result in detection_results:
        status = "✅" if result['correct'] else "❌"
        print(f"{status} {result['symbol']:10} {result['description']:20} "
              f"Должна быть aged: {result['should_be_aged']:5} "
              f"Обнаружена: {result['is_tracked']:5}")

    # Подсчет статистики
    total_positions = len(detection_results)
    correct_detections = sum(1 for r in detection_results if r['correct'])
    aged_positions = sum(1 for r in detection_results if r['should_be_aged'])
    detected_aged = sum(1 for r in detection_results if r['is_tracked'])

    print(f"\nСтатистика:")
    print(f"  Всего позиций: {total_positions}")
    print(f"  Должно быть aged: {aged_positions}")
    print(f"  Обнаружено aged: {detected_aged}")
    print(f"  Правильных определений: {correct_detections}/{total_positions}")
    print(f"  Счетчик обнаружений: {initial_count} → {final_count} (+{final_count - initial_count})")

    # Проверка корректности
    all_correct = all(r['correct'] for r in detection_results)

    if all_correct:
        print("\n🎉 ТЕСТ ПРОЙДЕН УСПЕШНО!")
        print("Мгновенное обнаружение работает корректно")
    else:
        print("\n❌ ТЕСТ ПРОВАЛЕН!")
        print("Есть ошибки в обнаружении")
        return False

    # Проверка производительности
    print("\n3. Тест производительности...")

    start_time = asyncio.get_event_loop().time()

    # Обработка 100 обновлений
    for i in range(100):
        ws_data = {
            'symbol': 'BTC/USDT:USDT',
            'mark_price': 95000 + i
        }
        await position_manager._on_position_update(ws_data)

    elapsed = asyncio.get_event_loop().time() - start_time
    avg_time = elapsed / 100 * 1000  # В миллисекундах

    print(f"  Обработано 100 обновлений за {elapsed:.3f} сек")
    print(f"  Среднее время обработки: {avg_time:.2f} мс")

    if avg_time < 10:  # Должно быть меньше 10мс
        print("  ✅ Производительность отличная!")
    else:
        print("  ⚠️ Производительность требует оптимизации")

    print("\n" + "=" * 60)
    print("✅ ИНТЕГРАЦИОННЫЙ ТЕСТ ЗАВЕРШЕН УСПЕШНО")
    print("=" * 60)

    return True


if __name__ == "__main__":
    import sys
    # Запуск теста
    result = asyncio.run(integration_test())

    if result:
        print("\n✅ Все тесты пройдены! Можно переходить к следующей фазе.")
    else:
        print("\n❌ Тесты провалены. Необходимо исправить ошибки.")
        sys.exit(1)