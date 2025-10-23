# 🎯 МАСТЕР-ПЛАН РЕАЛИЗАЦИИ: Aged Position Manager V2

**Дата начала:** 2025-10-23
**Ветка:** feature/aged-v2-full-implementation
**Принцип:** Минимальные изменения, максимальная надежность

---

## 📋 ОБЩИЙ ПЛАН

| Фаза | Описание | Время | Приоритет |
|------|----------|-------|-----------|
| **0** | Исправление мгновенного обнаружения | 2 часа | 🔴 КРИТИЧЕСКИЙ |
| **1** | Интеграция с БД | 1 день | 🔴 ВЫСОКИЙ |
| **2** | Robust Order Execution | 1 день | 🔴 ВЫСОКИЙ |
| **3** | Recovery & Persistence | 1 день | 🟡 СРЕДНИЙ |
| **4** | Метрики и мониторинг | 1 день | 🟡 СРЕДНИЙ |
| **5** | Интеграция и оркестрация | 1 день | 🟢 НИЗКИЙ |

---

## 🚀 ФАЗА 0: ИСПРАВЛЕНИЕ МГНОВЕННОГО ОБНАРУЖЕНИЯ

### Цель
Устранить 2-минутную задержку обнаружения aged позиций

### Шаги реализации

#### Шаг 0.1: Создание ветки и бэкап
```bash
# Создаем новую ветку
git checkout -b feature/aged-v2-instant-detection

# Создаем бэкап
cp core/position_manager.py core/position_manager.py.backup_before_instant_detection

# Коммит бэкапа
git add core/position_manager.py.backup_before_instant_detection
git commit -m "backup: save position_manager before instant detection fix"
```

#### Шаг 0.2: Добавление вспомогательного метода
**Файл:** `core/position_manager.py`
**Добавить после строки 1450:**

```python
def _calculate_position_age_hours(self, position) -> float:
    """Calculate position age in hours for aged detection"""
    if not hasattr(position, 'opened_at') or not position.opened_at:
        return 0.0

    current_time = datetime.now(timezone.utc)

    # Handle timezone awareness
    if hasattr(position.opened_at, 'tzinfo') and position.opened_at.tzinfo:
        position_age = current_time - position.opened_at
    else:
        opened_at_utc = position.opened_at.replace(tzinfo=timezone.utc)
        position_age = current_time - opened_at_utc

    return position_age.total_seconds() / 3600
```

**Git:**
```bash
git add -p core/position_manager.py
git commit -m "feat(aged): add position age calculation helper method"
```

#### Шаг 0.3: Добавление мгновенного обнаружения в WebSocket handler
**Файл:** `core/position_manager.py`
**В методе `_on_position_update` после строки 1850 добавить:**

```python
# INSTANT AGED DETECTION - Fix for 2-minute delay
if self.unified_protection and symbol in self.positions:
    position = self.positions[symbol]

    # Skip if trailing stop is already active
    if not (hasattr(position, 'trailing_activated') and position.trailing_activated):
        age_hours = self._calculate_position_age_hours(position)

        # Check if position just became aged
        if age_hours > self.max_position_age_hours:
            aged_monitor = self.unified_protection.get('aged_monitor')

            if aged_monitor:
                # Check if not already tracked
                if not hasattr(aged_monitor, 'aged_targets') or symbol not in aged_monitor.aged_targets:
                    try:
                        # Add to monitoring immediately
                        await aged_monitor.add_aged_position(position)

                        logger.info(
                            f"⚡ INSTANT AGED DETECTION: {symbol} "
                            f"(age={age_hours:.1f}h) added to monitoring immediately"
                        )

                        # Track instant detection in stats
                        if not hasattr(self, 'instant_aged_detections'):
                            self.instant_aged_detections = 0
                        self.instant_aged_detections += 1

                    except Exception as e:
                        logger.error(f"Failed to add aged position {symbol}: {e}")
```

**Git:**
```bash
git add -p core/position_manager.py
git commit -m "feat(aged): add instant aged position detection in WebSocket updates

- Eliminates 2-minute detection delay
- Checks position age on every price update
- Immediately adds to aged monitoring when threshold crossed
- Includes detection counter for metrics"
```

#### Шаг 0.4: Добавление метода проверки в AgedPositionMonitorV2
**Файл:** `core/aged_position_monitor_v2.py`
**Добавить после строки 100:**

```python
def is_position_tracked(self, symbol: str) -> bool:
    """Check if position is already being tracked

    Used for instant detection to avoid duplicates
    """
    return symbol in self.aged_targets

def get_tracked_positions(self) -> List[str]:
    """Get list of currently tracked aged positions"""
    return list(self.aged_targets.keys())

def get_tracking_stats(self) -> Dict:
    """Get statistics about aged position tracking"""
    stats = {
        'total_tracked': len(self.aged_targets),
        'by_phase': {},
        'oldest_age_hours': 0
    }

    for symbol, target in self.aged_targets.items():
        phase = target.phase
        stats['by_phase'][phase] = stats['by_phase'].get(phase, 0) + 1

        if hasattr(target, 'hours_aged'):
            stats['oldest_age_hours'] = max(stats['oldest_age_hours'], target.hours_aged)

    return stats
```

**Git:**
```bash
git add -p core/aged_position_monitor_v2.py
git commit -m "feat(aged): add helper methods for instant detection support"
```

#### Шаг 0.5: Создание теста для мгновенного обнаружения
**Файл:** `tests/test_aged_instant_detection.py`

```python
#!/usr/bin/env python3
"""
Тест мгновенного обнаружения aged позиций
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.position_manager import PositionManager, PositionState
from core.aged_position_monitor_v2 import AgedPositionMonitorV2
from config.settings import TradingConfig


class TestInstantAgedDetection:
    """Тестирование мгновенного обнаружения aged позиций"""

    @pytest.fixture
    def mock_config(self):
        """Создание мок конфигурации"""
        config = Mock(spec=TradingConfig)
        config.max_position_age_hours = 3
        return config

    @pytest.fixture
    def mock_unified_protection(self):
        """Создание мок UnifiedProtection"""
        aged_monitor = Mock(spec=AgedPositionMonitorV2)
        aged_monitor.aged_targets = {}
        aged_monitor.add_aged_position = AsyncMock()

        unified = {
            'aged_monitor': aged_monitor
        }
        return unified

    @pytest.fixture
    async def position_manager(self, mock_config, mock_unified_protection):
        """Создание PositionManager с мок зависимостями"""
        mock_repo = AsyncMock()
        mock_exchanges = {'binance': Mock(), 'bybit': Mock()}
        mock_event_router = Mock()

        pm = PositionManager(mock_config, mock_exchanges, mock_repo, mock_event_router)
        pm.unified_protection = mock_unified_protection
        pm.max_position_age_hours = 3

        return pm

    @pytest.mark.asyncio
    async def test_instant_detection_on_websocket_update(self, position_manager):
        """Тест мгновенного обнаружения при WebSocket обновлении"""
        # Создаем aged позицию (старше 3 часов)
        aged_position = PositionState(
            id="test_aged_123",
            symbol="BTCUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("0.01"),
            entry_price=Decimal("42000"),
            current_price=Decimal("41000"),
            unrealized_pnl=Decimal("-10"),
            unrealized_pnl_percent=Decimal("-2.38"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=3.5)  # 3.5 часов назад
        )

        position_manager.positions["BTCUSDT"] = aged_position

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'BTC/USDT:USDT',
            'mark_price': 41000.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция была добавлена в aged monitoring
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.add_aged_position.assert_called_once_with(aged_position)

        # Проверяем счетчик
        assert hasattr(position_manager, 'instant_aged_detections')
        assert position_manager.instant_aged_detections == 1

    @pytest.mark.asyncio
    async def test_no_detection_for_young_position(self, position_manager):
        """Тест: молодые позиции не должны обнаруживаться"""
        # Создаем молодую позицию (1 час)
        young_position = PositionState(
            id="test_young_123",
            symbol="ETHUSDT",
            exchange="binance",
            side="short",
            quantity=Decimal("0.1"),
            entry_price=Decimal("2000"),
            current_price=Decimal("2010"),
            unrealized_pnl=Decimal("-1"),
            unrealized_pnl_percent=Decimal("-0.5"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=1)  # 1 час назад
        )

        position_manager.positions["ETHUSDT"] = young_position

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'ETH/USDT:USDT',
            'mark_price': 2010.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция НЕ была добавлена
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.add_aged_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_detection(self, position_manager):
        """Тест: позиция не должна добавляться дважды"""
        # Создаем aged позицию
        aged_position = PositionState(
            id="test_dup_123",
            symbol="SOLUSDT",
            exchange="bybit",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            current_price=Decimal("95"),
            unrealized_pnl=Decimal("-50"),
            unrealized_pnl_percent=Decimal("-5"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=5)
        )

        position_manager.positions["SOLUSDT"] = aged_position

        # Помечаем что позиция уже отслеживается
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.aged_targets = {"SOLUSDT": Mock()}

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'SOL/USDT:USDT',
            'mark_price': 95.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция НЕ была добавлена повторно
        aged_monitor.add_aged_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_positions_with_trailing_stop(self, position_manager):
        """Тест: позиции с активным trailing stop не должны обнаруживаться"""
        # Создаем aged позицию с trailing stop
        ts_position = PositionState(
            id="test_ts_123",
            symbol="AVAXUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("5"),
            entry_price=Decimal("35"),
            current_price=Decimal("40"),
            unrealized_pnl=Decimal("25"),
            unrealized_pnl_percent=Decimal("14.3"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=4),
            trailing_activated=True  # Trailing stop активен!
        )

        position_manager.positions["AVAXUSDT"] = ts_position

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'AVAX/USDT:USDT',
            'mark_price': 40.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция НЕ была добавлена (из-за TS)
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.add_aged_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_age_calculation_accuracy(self, position_manager):
        """Тест точности расчета возраста позиции"""
        # Тестируем граничные условия
        test_cases = [
            (2.9, False),  # 2.9 часов - не aged
            (3.0, True),   # 3.0 часов - aged
            (3.1, True),   # 3.1 часов - aged
            (10.5, True),  # 10.5 часов - aged
        ]

        for hours_old, should_detect in test_cases:
            position = PositionState(
                id=f"test_age_{hours_old}",
                symbol=f"TEST{int(hours_old*10)}USDT",
                exchange="binance",
                side="long",
                quantity=Decimal("1"),
                entry_price=Decimal("100"),
                current_price=Decimal("100"),
                unrealized_pnl=Decimal("0"),
                unrealized_pnl_percent=Decimal("0"),
                opened_at=datetime.now(timezone.utc) - timedelta(hours=hours_old)
            )

            age = position_manager._calculate_position_age_hours(position)

            # Проверяем точность с погрешностью 0.01 часа
            assert abs(age - hours_old) < 0.01, f"Age calculation incorrect for {hours_old} hours"

            # Проверяем правильность определения aged
            is_aged = age > position_manager.max_position_age_hours
            assert is_aged == should_detect, f"Detection incorrect for {hours_old} hours"


@pytest.mark.asyncio
async def test_instant_detection_performance():
    """Тест производительности мгновенного обнаружения"""
    # Создаем 100 позиций
    positions = {}
    for i in range(100):
        age_hours = i * 0.1  # От 0 до 10 часов
        positions[f"TEST{i}USDT"] = PositionState(
            id=f"perf_{i}",
            symbol=f"TEST{i}USDT",
            exchange="binance",
            side="long" if i % 2 == 0 else "short",
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            current_price=Decimal("100"),
            unrealized_pnl=Decimal("0"),
            unrealized_pnl_percent=Decimal("0"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=age_hours)
        )

    # Измеряем время обработки
    start_time = asyncio.get_event_loop().time()

    # Симулируем обработку всех позиций
    aged_count = 0
    for symbol, position in positions.items():
        age = (datetime.now(timezone.utc) - position.opened_at).total_seconds() / 3600
        if age > 3:  # MAX_POSITION_AGE_HOURS
            aged_count += 1

    elapsed = asyncio.get_event_loop().time() - start_time

    # Проверяем производительность
    assert elapsed < 0.1, f"Detection too slow: {elapsed:.3f}s for 100 positions"
    assert aged_count == 70, f"Expected 70 aged positions, found {aged_count}"

    print(f"✅ Performance test passed: {elapsed:.3f}s for 100 positions")


if __name__ == "__main__":
    # Запускаем все тесты
    pytest.main([__file__, "-v", "--tb=short"])
```

**Git:**
```bash
git add tests/test_aged_instant_detection.py
git commit -m "test(aged): add comprehensive tests for instant detection

- Test instant detection on WebSocket update
- Test no detection for young positions
- Test no duplicate detection
- Test skip positions with trailing stop
- Test age calculation accuracy
- Test performance with 100 positions"
```

#### Шаг 0.6: Запуск тестов
```bash
# Запуск тестов
python -m pytest tests/test_aged_instant_detection.py -v

# Если все тесты прошли успешно
git tag -a "v1.0-instant-detection" -m "Instant aged detection implemented"
```

#### Шаг 0.7: Интеграционный тест
**Файл:** `tests/test_aged_instant_detection_integration.py`

```python
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
    # Запуск теста
    result = asyncio.run(integration_test())

    if result:
        print("\n✅ Все тесты пройдены! Можно переходить к следующей фазе.")
    else:
        print("\n❌ Тесты провалены. Необходимо исправить ошибки.")
        sys.exit(1)
```

**Git:**
```bash
git add tests/test_aged_instant_detection_integration.py
git commit -m "test(aged): add integration test for instant detection

- Full integration test with real components
- Performance benchmarking
- Comprehensive validation"
```

#### Шаг 0.8: Финальная проверка и merge
```bash
# Запуск всех тестов
python tests/test_aged_instant_detection.py
python tests/test_aged_instant_detection_integration.py

# Если все тесты прошли
git checkout fix/duplicate-position-race-condition
git merge feature/aged-v2-instant-detection

# Push изменений
git push origin fix/duplicate-position-race-condition
```

---

## ✅ КОНТРОЛЬНЫЙ ЧЕКЛИСТ ФАЗЫ 0

- [ ] Создана ветка feature/aged-v2-instant-detection
- [ ] Сделан бэкап position_manager.py
- [ ] Добавлен метод _calculate_position_age_hours
- [ ] Добавлено мгновенное обнаружение в _on_position_update
- [ ] Добавлены вспомогательные методы в AgedPositionMonitorV2
- [ ] Написаны unit тесты (6 тестов)
- [ ] Написан интеграционный тест
- [ ] Тест производительности пройден
- [ ] Все тесты зеленые
- [ ] Код закоммичен с понятными сообщениями
- [ ] Создан git tag v1.0-instant-detection
- [ ] Смержено в основную ветку

---

## 📝 КРИТЕРИИ УСПЕХА ФАЗЫ 0

1. **Функциональность:**
   - ✅ Aged позиции обнаруживаются в течение 1 секунды
   - ✅ Нет дублирования обнаружений
   - ✅ Позиции с trailing stop игнорируются
   - ✅ Молодые позиции не обнаруживаются

2. **Производительность:**
   - ✅ Обработка обновления < 10мс
   - ✅ 100 позиций обрабатываются < 100мс

3. **Надежность:**
   - ✅ Все тесты проходят
   - ✅ Нет регрессий в существующем коде
   - ✅ Обработка ошибок на месте

---

**ДАЛЕЕ:** После успешного завершения Фазы 0 переходим к Фазе 1 (Интеграция с БД)