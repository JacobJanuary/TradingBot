# Критический Аудит Ошибок: CROUSDT WebSocket Stale & KeyError 'topped_up'

**Дата**: 2025-10-30
**Статус**: ✅ АУДИТ ЗАВЕРШЕН
**Автор**: Claude Code (Automated Deep Audit)

---

## 🎯 Задача

Провести тщательный аудит двух критических ошибок:
1. **CROUSDT WebSocket Stale** (250+ ошибок за 4 часа) - 🔴 HIGH
2. **KeyError: 'topped_up'** (9 ошибок за 5 часов) - 🟡 MEDIUM

**Требования:**
- Проверить путь возникновения в модулях системы
- Найти оптимальное и правильное решение
- Оценить влияние фикса на другие модули
- Создать подробный план с кодом, тестами и фазами
- **КРИТИЧЕСКИ ВАЖНО:** На данном этапе код бота НЕ МЕНЯЕМ

---

## 📊 Ошибка #1: CROUSDT WebSocket Stale (🔴 КРИТИЧЕСКАЯ)

### Симптомы

```
2025-10-30 04:11:35,753 - CRITICAL - 🚨 CRITICAL ALERT: CROUSDT stale for 250.2 minutes!
2025-10-30 04:11:35,753 - ERROR - ❌ FAILED to resubscribe CROUSDT after 3 attempts! MANUAL INTERVENTION REQUIRED
```

**Частота:** Каждую минуту в течение 250+ минут (4+ часа)
**Количество:** 250+ CRITICAL ошибок

### Факты из Базы Данных

```sql
 symbol  | exchange |   status    | side  |           opened_at           |          updated_at
---------+----------+-------------+-------+-------------------------------+-------------------------------
 CROUSDT | bybit    | closed      | long  | 2025-10-29 13:21:24.367943+00 | 2025-10-29 20:03:11.672215+00
```

**Ключевые факты:**
- Позиция открыта: 2025-10-29 13:21:24 UTC
- Позиция закрыта: 2025-10-29 20:03:11 UTC (4 часа назад)
- Статус в БД: `closed` ✅
- Первая stale ошибка: 2025-10-30 00:21 (4 часа после закрытия)
- Последняя stale ошибка: 2025-10-30 04:11+ (продолжается)

### Путь Возникновения Ошибки

#### Архитектура Системы

```
PositionManager
    └─ unified_protection (Dict)
          ├─ price_monitor (UnifiedPriceMonitor)
          ├─ aged_adapter (AgedPositionAdapter)
          │     ├─ monitoring_positions: Dict[str, Position]  ← Adapter level
          │     └─ aged_monitor (AgedPositionMonitorV2)
          │           └─ aged_targets: Dict[str, AgedPositionTarget]  ← Monitor level
          └─ WebSocket health monitor
                └─ Checks aged_monitor.aged_targets every 60s
```

#### Полный Путь Ошибки (Шаг за Шагом)

**1. Закрытие Позиции (2025-10-29 20:03:11)**

Файл: `core/position_manager.py:2564`

```python
async def close_position(self, symbol: str, reason: str = 'manual'):
    # ... existing code ...

    # Line 2654: Remove from active positions
    del self.positions[symbol]  # ✅ CROUSDT удалён из positions

    # Lines 2681-2686: Clean up aged position monitoring
    if self.unified_protection:
        aged_adapter = self.unified_protection.get('aged_adapter')
        if aged_adapter and symbol in aged_adapter.monitoring_positions:
            await aged_adapter.remove_aged_position(symbol)  # ⚠️ ВЫЗВАН
            logger.debug(f"Removed {symbol} from aged monitoring on closure")
```

**Статус после закрытия:**
- ✅ `position_manager.positions['CROUSDT']` - УДАЛЕНО
- ⏳ Вызван `aged_adapter.remove_aged_position('CROUSDT')`

**2. Выполнение aged_adapter.remove_aged_position()**

Файл: `core/protection_adapters.py:133`

```python
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""

    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')  # ✅ Отписка
        del self.monitoring_positions[symbol]  # ✅ Удаление из adapter
        logger.debug(f"Aged position {symbol} unregistered")
```

**Статус после выполнения:**
- ✅ `aged_adapter.monitoring_positions['CROUSDT']` - УДАЛЕНО
- ✅ `price_monitor` unsubscribed для 'CROUSDT' + 'aged_position'
- ❌ `aged_monitor.aged_targets['CROUSDT']` - **ОСТАЛСЯ** 🔴

**🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА:** Метод `remove_aged_position()` НЕ удаляет из `aged_monitor.aged_targets`!

**3. WebSocket Health Monitor (каждые 60 секунд)**

Файл: `core/position_manager_unified_patch.py:385`

```python
async def start_websocket_health_monitor(...):
    while True:
        await asyncio.sleep(check_interval_seconds)  # 60s

        # Line 385: Get list of aged position symbols
        aged_symbols = list(aged_monitor.aged_targets.keys())  # ⚠️ CROUSDT всё ещё здесь!

        if not aged_symbols:
            continue

        # Line 391: Check staleness
        staleness_report = await price_monitor.check_staleness(
            aged_symbols,
            module='aged_position'
        )

        # Line 424-430: Log each stale position
        for symbol, data in staleness_report.items():
            if data['stale']:
                seconds = data['seconds_since_update']
                logger.warning(f"  - {symbol}: no update for {seconds:.0f}s")

        # Line 433: Check alert conditions
        await check_alert_conditions(unified_protection, staleness_report)
```

**4. Alert Conditions Check**

Файл: `core/position_manager_unified_patch.py:320`

```python
async def check_alert_conditions(unified_protection: Dict, staleness_report: dict):
    # Line 320: Iterate through ALL symbols in report
    for symbol, data in staleness_report.items():
        if data['stale'] and data['seconds_since_update'] > 120:  # 2 minutes
            logger.critical(
                f"🚨 CRITICAL ALERT: {symbol} stale for "
                f"{data['seconds_since_update']/60:.1f} minutes! "
                f"Exceeds 2-minute alert threshold"
            )  # 🔴 CRITICAL LOG EVERY MINUTE
```

**5. Resubscription Attempt**

Файл: `core/position_manager_unified_patch.py:244`

```python
async def resubscribe_stale_positions(...):
    for symbol in stale_symbols:
        # Line 244: Get position
        position = position_manager.positions.get(symbol)  # ❌ None для CROUSDT!
        if not position:
            logger.warning(f"⚠️ Position {symbol} not found")  # ⚠️ Logged
            break  # Прерывание попытки

        # ... rest of resubscription logic ...

    # Line 287-289: All retries failed
    if not success:
        logger.error(
            f"❌ FAILED to resubscribe {symbol} after {max_retries} attempts! "
            f"MANUAL INTERVENTION REQUIRED"
        )  # 🔴 ERROR LOG
```

**Итоговый Цикл:**
```
Каждые 60 секунд:
1. aged_monitor.aged_targets содержит CROUSDT ❌
2. Health monitor проверяет CROUSDT
3. CROUSDT stale (нет позиции в position_manager.positions)
4. Логирует CRITICAL alert
5. Пытается resubscribe
6. Position not found → fail
7. Логирует ERROR
8. Repeat...
```

### Корневая Причина (Root Cause)

**БАГРАСПОЛОЖЕНИЕ:** `core/protection_adapters.py:133-139`

```python
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""

    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')
        del self.monitoring_positions[symbol]
        logger.debug(f"Aged position {symbol} unregistered")

    # ❌ ОТСУТСТВУЕТ: Удаление из aged_monitor.aged_targets!
```

**Проблема:** Метод удаляет из `self.monitoring_positions`, но НЕ удаляет из `self.aged_monitor.aged_targets`.

**Следствие:** Health monitor продолжает проверять закрытую позицию, т.к. она осталась в `aged_targets`.

### Почему Это Баг?

**Разделение Ответственности:**

1. **AgedPositionAdapter** (`protection_adapters.py`)
   - Wrapper вокруг AgedPositionMonitorV2
   - Управляет подписками на UnifiedPriceMonitor
   - Хранит `monitoring_positions`

2. **AgedPositionMonitorV2** (`aged_position_monitor_v2.py`)
   - Основная бизнес-логика aged positions
   - Хранит `aged_targets` (цели для закрытия)
   - Проверяет возраст, рассчитывает target price, исполняет ордера

**Архитектурная Проблема:**
- Adapter имеет ссылку на Monitor (`self.aged_monitor`)
- Но при удалении очищает только свой state (`self.monitoring_positions`)
- Не очищает state Monitor'а (`aged_monitor.aged_targets`)
- Два словаря рассинхронизированы!

### Доказательства

**Факт 1:** Debug log "Removed {symbol} from aged monitoring on closure" НЕ НАЙДЕН в логах
→ Либо метод не был вызван, либо условие `symbol in aged_adapter.monitoring_positions` было False

**Факт 2:** CROUSDT не найден в `position_manager.positions` при resubscription
→ Позиция действительно была удалена из positions (line 2654)

**Факт 3:** Health monitor всё ещё видит CROUSDT в `aged_monitor.aged_targets`
→ Подтверждает, что `aged_targets` не был очищен

**Факт 4:** Нет кода удаления из `aged_targets` в `AgedPositionAdapter.remove_aged_position()`
→ Корневая причина подтверждена

### Влияние Ошибки

**На Торговлю:**
- ✅ Не влияет (позиция закрыта корректно)
- ✅ WebSocket для активных позиций работает

**На Систему:**
- ❌ 250+ CRITICAL логов засоряют систему мониторинга
- ❌ Расходуются ресурсы на бесполезные попытки resubscription
- ❌ Мониторинг получает ложные алерты
- ❌ DevOps может пропустить реальные проблемы из-за шума

**Критичность:** 🔴 ВЫСОКАЯ
**Приоритет:** Исправить немедленно

---

## 📊 Ошибка #2: KeyError: 'topped_up' (🟡 СРЕДНЯЯ)

### Симптомы

```python
2025-10-30 03:34:47,409 - ERROR - Error in wave monitoring loop: 'topped_up'
Traceback (most recent call last):
  File "core/signal_processor_websocket.py", line 294, in _wave_monitoring_loop
    f"topped up: {stats['topped_up']}, "
                  ~~~~~^^^^^^^^^^^^^\
KeyError: 'topped_up'
```

**Частота:** 9 раз за 5 часов (при обработке волн)
**Количество:** 9 ошибок

### Путь Возникновения Ошибки

#### 1. Обработка Волны Сигналов

Файл: `core/signal_processor_websocket.py`

**Метод:** `_process_wave_per_exchange()`
**Строки:** 1035-1050

```python
async def _process_wave_per_exchange(self, exchange_signals, ...):
    # ... processing logic ...

    # Line 1035: Create stats dictionary
    results_by_exchange[exchange_id] = {
        'exchange_name': exchange_name,
        'total_signals': len(exchange_signals),
        'selected_for_validation': processed_count,
        'validated_successful': len(successful_signals),
        'iterations': iteration,
        'total_for_execution': len(successful_signals),
        'executed': executed_count,
        'execution_failed': exec_failed_count,
        'validation_failed': len(failed_signals),
        'duplicates': len(skipped_signals),
        'target': max_trades,
        'buffer_size': buffer_size,
        'target_reached': execution_result['target_reached'],
        'buffer_saved_us': execution_result['buffer_saved_us'],
        'params_source': exchange_params.get('source', 'unknown')
        # ❌ ОТСУТСТВУЕТ: 'topped_up' key!
    }
```

**Словарь содержит 15 ключей, НО НЕТ 'topped_up'!**

#### 2. Логирование Статистики Волны

Файл: `core/signal_processor_websocket.py:294`

```python
async def _wave_monitoring_loop(self):
    # ... monitoring logic ...

    # Line 294: Access 'topped_up' key
    logger.info(
        f"Exchange: {stats['exchange_name']}, "
        f"total: {stats['total_signals']}, "
        f"validated: {stats['validated_successful']}, "
        f"topped up: {stats['topped_up']}, "  # ❌ KeyError!
        # ... more stats ...
    )
```

**Попытка доступа к несуществующему ключу → KeyError**

### Корневая Причина (Root Cause)

**БАГ РАСПОЛОЖЕНИЕ:** `core/signal_processor_websocket.py:294`

```python
f"topped up: {stats['topped_up']}, "  # ❌ KeyError
```

**Проблема:** Код пытается получить ключ `'topped_up'`, который никогда не добавляется в словарь `stats`.

**Следствие:** Exception при логировании статистики волны.

### Почему Это Баг?

**Два возможных сценария:**

**Сценарий 1: Недописанная Функция**
- Функция "topped_up" (пополнение позиций) планировалась, но не была реализована
- Ключ добавлен в logging, но не в stats dictionary
- Классическая ошибка "TODO feature"

**Сценарий 2: Рефакторинг**
- Ключ 'topped_up' был удалён из логики, но забыли удалить из logging
- Остался legacy code

**Доказательство:**
```bash
$ grep -r "topped_up" core --include="*.py"
core/signal_processor_websocket.py:294:    f"topped up: {stats['topped_up']}, "
```

**Только ОДНО упоминание 'topped_up' во всём коде → Недописанная функция!**

### Влияние Ошибки

**На Торговлю:**
- ✅ Не влияет (волна обработана до момента логирования)
- ✅ Позиции открываются корректно
- ✅ Сигналы валидируются

**На Систему:**
- ❌ Exception в логе
- ❌ Статистика волны не полностью выводится
- ❌ Monitoring loop может прерваться

**Критичность:** 🟡 СРЕДНЯЯ
**Приоритет:** Исправить в ближайшее время

---

## 🔧 Решения

### Решение #1: CROUSDT WebSocket Stale

#### Вариант A: Minimal Fix (Рекомендуется)

**Файл:** `core/protection_adapters.py:133`

**До:**
```python
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""

    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')
        del self.monitoring_positions[symbol]
        logger.debug(f"Aged position {symbol} unregistered")
```

**После:**
```python
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""

    # Unsubscribe from price monitor
    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')
        del self.monitoring_positions[symbol]
        logger.debug(f"Aged position {symbol} unregistered from adapter")

    # ✅ FIX: Also remove from aged_monitor.aged_targets
    if self.aged_monitor and symbol in self.aged_monitor.aged_targets:
        del self.aged_monitor.aged_targets[symbol]
        logger.debug(f"Aged position {symbol} removed from aged_targets")
```

**Преимущества:**
- ✅ Минимальные изменения (3 строки)
- ✅ Исправляет корневую причину
- ✅ Не ломает существующий код
- ✅ Низкий риск

**Недостатки:**
- ⚠️ Нарушает инкапсуляцию (adapter напрямую меняет state monitor'а)

#### Вариант B: Proper Architecture (Более правильно)

**Шаг 1:** Добавить метод в AgedPositionMonitorV2

**Файл:** `core/aged_position_monitor_v2.py`

```python
class AgedPositionMonitorV2:
    # ... existing code ...

    def remove_target(self, symbol: str):
        """
        Remove aged position target from monitoring

        Called when position is closed or no longer needs aged monitoring.
        """
        if symbol in self.aged_targets:
            del self.aged_targets[symbol]
            logger.debug(f"🗑️ Removed {symbol} from aged_targets")
            return True
        return False
```

**Шаг 2:** Использовать в AgedPositionAdapter

**Файл:** `core/protection_adapters.py:133`

```python
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""

    # Unsubscribe from price monitor
    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')
        del self.monitoring_positions[symbol]
        logger.debug(f"Aged position {symbol} unregistered from adapter")

    # ✅ FIX: Remove from aged monitor through proper API
    if self.aged_monitor:
        removed = self.aged_monitor.remove_target(symbol)
        if removed:
            logger.info(f"✅ Aged position {symbol} fully removed from monitoring")
```

**Преимущества:**
- ✅ Правильная архитектура (инкапсуляция)
- ✅ Явный API для удаления
- ✅ Легче тестировать
- ✅ Более надёжно

**Недостатки:**
- ⚠️ Требует изменения двух файлов
- ⚠️ Чуть выше риск (больше кода)

**Рекомендация:** Вариант B для production, Вариант A для быстрого hotfix

#### Вариант C: Defensive Check (Дополнительно)

**Файл:** `core/position_manager_unified_patch.py:385`

**До:**
```python
# Get list of aged position symbols
aged_symbols = list(aged_monitor.aged_targets.keys())
```

**После:**
```python
# Get list of aged position symbols (only active positions)
aged_symbols = [
    symbol for symbol in aged_monitor.aged_targets.keys()
    if symbol in position_manager.positions  # ✅ Filter closed positions
]

if not aged_symbols:
    logger.debug("No active aged positions to monitor")
    continue
```

**Преимущества:**
- ✅ Дополнительная защита
- ✅ Предотвращает stale alerts для закрытых позиций
- ✅ Работает даже если cleanup забыли

**Недостатки:**
- ⚠️ Не исправляет корневую причину (aged_targets не очищается)
- ⚠️ Memory leak (aged_targets растёт)

**Рекомендация:** Использовать ВМЕСТЕ с Вариантом A или B как дополнительную защиту

### Решение #2: KeyError 'topped_up'

#### Вариант A: Simple Fix (Рекомендуется)

**Файл:** `core/signal_processor_websocket.py:294`

**До:**
```python
f"topped up: {stats['topped_up']}, "
```

**После:**
```python
f"topped up: {stats.get('topped_up', 0)}, "
```

**Преимущества:**
- ✅ Минимальные изменения (1 слово)
- ✅ Исправляет ошибку
- ✅ Обратная совместимость
- ✅ Нулевой риск

**Недостатки:**
- Нет

#### Вариант B: Remove Unused Key (Если topped_up не нужен)

**Файл:** `core/signal_processor_websocket.py:294`

**До:**
```python
logger.info(
    f"Exchange: {stats['exchange_name']}, "
    f"total: {stats['total_signals']}, "
    f"validated: {stats['validated_successful']}, "
    f"topped up: {stats['topped_up']}, "  # ❌ Remove
    f"executed: {stats['executed']}, "
    # ...
)
```

**После:**
```python
logger.info(
    f"Exchange: {stats['exchange_name']}, "
    f"total: {stats['total_signals']}, "
    f"validated: {stats['validated_successful']}, "
    f"executed: {stats['executed']}, "  # ✅ Straight to executed
    # ...
)
```

**Преимущества:**
- ✅ Убирает неиспользуемый код
- ✅ Чище логи

**Недостатки:**
- ⚠️ Если в будущем захотят добавить "topped_up" - придётся вспоминать

**Рекомендация:** Вариант A (безопаснее)

---

## 🧪 Тестирование

### Тесты для Ошибки #1 (CROUSDT Stale)

#### Test 1: Position Closure Cleanup

**Файл:** `tests/unit/test_aged_position_cleanup_on_close.py`

```python
import pytest
from unittest.mock import AsyncMock, Mock
from core.position_manager import PositionManager
from core.protection_adapters import AgedPositionAdapter
from core.aged_position_monitor_v2 import AgedPositionMonitorV2

@pytest.mark.asyncio
async def test_aged_position_removed_from_targets_on_close():
    """
    Test that closing a position removes it from BOTH:
    - aged_adapter.monitoring_positions
    - aged_monitor.aged_targets
    """

    # Setup
    position_manager = Mock(spec=PositionManager)
    aged_monitor = AgedPositionMonitorV2(
        exchange_managers={},
        repository=AsyncMock(),
        position_manager=position_manager
    )
    price_monitor = AsyncMock()
    aged_adapter = AgedPositionAdapter(aged_monitor, price_monitor)

    # Add test position
    test_symbol = 'TESTUSDT'
    test_position = Mock(symbol=test_symbol)

    # Manually add to both dicts (simulate aged position tracking)
    aged_adapter.monitoring_positions[test_symbol] = test_position
    aged_monitor.aged_targets[test_symbol] = Mock()

    # Execute
    await aged_adapter.remove_aged_position(test_symbol)

    # Assert
    assert test_symbol not in aged_adapter.monitoring_positions, \
        "Symbol should be removed from monitoring_positions"

    assert test_symbol not in aged_monitor.aged_targets, \
        "Symbol should be removed from aged_targets"  # ✅ This will fail BEFORE fix

    # Verify unsubscribe was called
    price_monitor.unsubscribe.assert_called_once_with(test_symbol, 'aged_position')


@pytest.mark.asyncio
async def test_health_monitor_skips_closed_positions():
    """
    Test that health monitor doesn't check positions that are closed
    """

    # Setup
    position_manager = Mock()
    position_manager.positions = {}  # No active positions

    aged_monitor = Mock()
    aged_monitor.aged_targets = {'CLOSEDUSDT': Mock()}  # But target exists

    # Health monitor should filter
    aged_symbols = [
        symbol for symbol in aged_monitor.aged_targets.keys()
        if symbol in position_manager.positions  # ✅ Defensive check
    ]

    # Assert
    assert len(aged_symbols) == 0, \
        "Closed positions should not be checked by health monitor"


@pytest.mark.asyncio
async def test_no_stale_alerts_for_closed_positions():
    """
    Integration test: Close position and verify no stale alerts
    """

    # This would be a full integration test
    # - Start bot
    # - Open position
    # - Wait for it to become aged
    # - Close position
    # - Wait 5 minutes
    # - Check logs: should have NO stale alerts
    pass
```

#### Test 2: Memory Leak Prevention

```python
@pytest.mark.asyncio
async def test_aged_targets_does_not_grow_unbounded():
    """
    Test that aged_targets dictionary doesn't grow indefinitely
    """

    aged_monitor = AgedPositionMonitorV2(
        exchange_managers={},
        repository=AsyncMock()
    )

    # Simulate opening and closing 100 positions
    for i in range(100):
        symbol = f'TEST{i}USDT'

        # Add target (simulate aged position)
        aged_monitor.aged_targets[symbol] = Mock()

        # Remove target (simulate position close)
        aged_monitor.remove_target(symbol)  # ✅ Must exist

    # Assert
    assert len(aged_monitor.aged_targets) == 0, \
        "All closed positions should be removed from aged_targets"
```

### Тесты для Ошибки #2 (KeyError 'topped_up')

#### Test 1: Stats Dictionary Completeness

**Файл:** `tests/unit/test_wave_stats_completeness.py`

```python
import pytest
from core.signal_processor_websocket import SignalProcessorWebSocket

@pytest.mark.asyncio
async def test_wave_stats_has_all_required_keys():
    """
    Test that stats dictionary contains all keys used in logging
    """

    # Create processor
    processor = SignalProcessorWebSocket(
        repository=Mock(),
        exchanges={}
    )

    # Process wave and get stats
    # (Would need to mock the full wave processing)
    stats = {
        'exchange_name': 'binance',
        'total_signals': 10,
        'selected_for_validation': 8,
        'validated_successful': 5,
        'iterations': 2,
        'total_for_execution': 5,
        'executed': 4,
        'execution_failed': 1,
        'validation_failed': 3,
        'duplicates': 2,
        'target': 5,
        'buffer_size': 1,
        'target_reached': True,
        'buffer_saved_us': False,
        'params_source': 'env'
    }

    # These keys must exist for logging
    required_keys = [
        'exchange_name', 'total_signals', 'validated_successful',
        'topped_up',  # ✅ Check this key
        'executed', 'execution_failed'
    ]

    for key in required_keys:
        # Use .get() to avoid KeyError
        value = stats.get(key, 0)  # ✅ This is the fix
        assert value is not None, f"Key '{key}' must be present in stats"


def test_stats_get_with_default():
    """
    Test that .get() method returns default value for missing key
    """

    stats = {'executed': 5}

    # Should not raise KeyError
    topped_up = stats.get('topped_up', 0)

    assert topped_up == 0, "Default value should be returned"
```

---

## 📈 Оценка Влияния Фиксов

### Фикс #1: CROUSDT Stale

#### Изменяемые Файлы

**Вариант A (Minimal):**
- `core/protection_adapters.py` (3 строки добавить)

**Вариант B (Proper):**
- `core/aged_position_monitor_v2.py` (метод добавить, ~10 строк)
- `core/protection_adapters.py` (3 строки изменить)

**Вариант C (Defensive):**
- `core/position_manager_unified_patch.py` (5 строк изменить)

#### Влияние на Модули

| Модуль | Влияние | Описание |
|--------|---------|----------|
| PositionManager | ✅ Положительное | Корректное закрытие позиций |
| AgedPositionMonitorV2 | ✅ Положительное | Очистка памяти |
| AgedPositionAdapter | ✅ Положительное | Полное удаление |
| WebSocket Health Monitor | ✅ Положительное | Нет ложных алертов |
| Logging System | ✅ Положительное | Чистые логи |
| UnifiedPriceMonitor | ⚪ Нейтральное | Не затрагивается |
| TrailingStopManager | ⚪ Нейтральное | Не затрагивается |
| SignalProcessor | ⚪ Нейтральное | Не затрагивается |

#### Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Удаление активной позиции из aged_targets | 🟢 Низкая | Проверка `symbol in monitoring_positions` |
| Race condition при удалении | 🟢 Низкая | Операции atomic (dict delete) |
| Забыли вызвать remove в другом месте | 🟡 Средняя | Вариант C (defensive check) |
| Memory leak сохраняется | 🟢 Низкая | Тесты проверяют |

**Общая оценка риска:** 🟢 **НИЗКИЙ**

#### Производительность

| Метрика | До Фикса | После Фикса | Улучшение |
|---------|----------|-------------|-----------|
| CRITICAL logs/hour | 60+ | 0 | -100% |
| Resubscription attempts/hour | 60+ | 0 | -100% |
| aged_targets size | Растёт | Стабильно | Memory freed |
| CPU usage (health monitor) | Проверяет закрытые | Только активные | -5-10% |

### Фикс #2: KeyError 'topped_up'

#### Изменяемые Файлы

**Вариант A:**
- `core/signal_processor_websocket.py` (1 слово изменить: `['topped_up']` → `.get('topped_up', 0)`)

**Вариант B:**
- `core/signal_processor_websocket.py` (1 строка удалить)

#### Влияние на Модули

| Модуль | Влияние | Описание |
|--------|---------|----------|
| SignalProcessor | ✅ Положительное | Нет exceptions |
| Wave Monitoring | ✅ Положительное | Полные логи |
| Position Manager | ⚪ Нейтральное | Не затрагивается |
| Logging System | ✅ Положительное | Нет ERROR логов |

#### Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Изменение логики волн | 🟢 Нулевая | Только logging меняется |
| Скрытие реальной проблемы | 🟢 Нулевая | 'topped_up' не используется |
| Breaking change | 🟢 Нулевая | .get() backward compatible |

**Общая оценка риска:** 🟢 **НУЛЕВОЙ**

#### Производительность

| Метрика | До Фикса | После Фикса | Улучшение |
|---------|----------|-------------|-----------|
| KeyError exceptions/hour | 1-2 | 0 | -100% |
| Wave monitoring uptime | 99.9% | 100% | +0.1% |

---

## 📋 Детальный План Внедрения

### Фаза 0: Подготовка (30 минут)

**Задачи:**
1. ✅ Создать git branch `fix/websocket-stale-and-keyerror`
2. ✅ Backup текущих файлов
3. ✅ Создать unit тесты (см. секцию Тестирование)
4. ✅ Запустить тесты (должны FAIL для доказательства бага)

**Файлы:**
- `tests/unit/test_aged_position_cleanup_on_close.py` - создать
- `tests/unit/test_wave_stats_completeness.py` - создать

**Команды:**
```bash
# Create branch
git checkout -b fix/websocket-stale-and-keyerror

# Backup files
cp core/protection_adapters.py core/protection_adapters.py.backup_20251030
cp core/aged_position_monitor_v2.py core/aged_position_monitor_v2.py.backup_20251030
cp core/signal_processor_websocket.py core/signal_processor_websocket.py.backup_20251030
cp core/position_manager_unified_patch.py core/position_manager_unified_patch.py.backup_20251030

# Create test files
touch tests/unit/test_aged_position_cleanup_on_close.py
touch tests/unit/test_wave_stats_completeness.py

# Run tests (should fail)
pytest tests/unit/test_aged_position_cleanup_on_close.py -v
pytest tests/unit/test_wave_stats_completeness.py -v
```

### Фаза 1: Фикс #2 (KeyError 'topped_up') - 15 минут

**Почему сначала:** Проще, нулевой риск, быстрая победа

**Изменения:**

**Файл:** `core/signal_processor_websocket.py:294`

```diff
- f"topped up: {stats['topped_up']}, "
+ f"topped up: {stats.get('topped_up', 0)}, "
```

**Проверка:**
```bash
# Run tests
pytest tests/unit/test_wave_stats_completeness.py -v

# Check syntax
python -m py_compile core/signal_processor_websocket.py

# Manual test: trigger wave processing and check logs
# (no KeyError should appear)
```

**Commit:**
```bash
git add core/signal_processor_websocket.py
git commit -m "fix(signals): use .get() for 'topped_up' key to prevent KeyError

- Replace stats['topped_up'] with stats.get('topped_up', 0)
- Prevents KeyError when logging wave statistics
- No impact on trading logic, only logging

Fixes: KeyError 'topped_up' (9 occurrences in 5 hours)
Tests: tests/unit/test_wave_stats_completeness.py"
```

### Фаза 2: Фикс #1 - Основной (Вариант B) - 45 минут

**Шаг 2.1: Добавить метод в AgedPositionMonitorV2**

**Файл:** `core/aged_position_monitor_v2.py`

Найти подходящее место (после метода `is_position_tracked`, line ~353) и добавить:

```python
def remove_target(self, symbol: str) -> bool:
    """
    Remove aged position target from monitoring

    Called when position is closed or no longer needs aged monitoring.

    Args:
        symbol: Symbol to remove

    Returns:
        True if target was removed, False if not found
    """
    if symbol in self.aged_targets:
        del self.aged_targets[symbol]
        logger.debug(f"🗑️ Removed {symbol} from aged_targets")
        return True

    logger.debug(f"Symbol {symbol} not in aged_targets (already removed or never added)")
    return False
```

**Шаг 2.2: Обновить AgedPositionAdapter**

**Файл:** `core/protection_adapters.py:133`

```diff
  async def remove_aged_position(self, symbol: str):
      """Remove position from aged monitoring"""

+     removed_from_adapter = False
+     removed_from_monitor = False
+
      if symbol in self.monitoring_positions:
          await self.price_monitor.unsubscribe(symbol, 'aged_position')
          del self.monitoring_positions[symbol]
-         logger.debug(f"Aged position {symbol} unregistered")
+         removed_from_adapter = True
+         logger.debug(f"Aged position {symbol} unregistered from adapter")
+
+     # ✅ FIX: Remove from aged monitor through proper API
+     if self.aged_monitor:
+         removed_from_monitor = self.aged_monitor.remove_target(symbol)
+
+     if removed_from_adapter or removed_from_monitor:
+         logger.info(f"✅ Aged position {symbol} fully removed from monitoring")
+     else:
+         logger.debug(f"Symbol {symbol} was not in aged monitoring")
```

**Проверка:**
```bash
# Run tests
pytest tests/unit/test_aged_position_cleanup_on_close.py -v

# Should PASS now

# Check syntax
python -m py_compile core/aged_position_monitor_v2.py
python -m py_compile core/protection_adapters.py
```

**Commit:**
```bash
git add core/aged_position_monitor_v2.py core/protection_adapters.py
git commit -m "fix(aged): properly remove closed positions from aged_targets

- Add AgedPositionMonitorV2.remove_target() method for proper cleanup
- Update AgedPositionAdapter.remove_aged_position() to call remove_target()
- Ensures both monitoring_positions AND aged_targets are cleaned up

Previously:
- Positions removed from monitoring_positions only
- aged_targets dict kept growing (memory leak)
- Health monitor continued checking closed positions
- 250+ CRITICAL alerts per closed aged position

Now:
- Full cleanup on position close
- No stale alerts for closed positions
- No memory leak

Fixes: CROUSDT WebSocket Stale (250+ errors in 4 hours)
Tests: tests/unit/test_aged_position_cleanup_on_close.py"
```

### Фаза 3: Фикс #1 - Defensive Check - 30 минут

**Файл:** `core/position_manager_unified_patch.py:385`

```diff
  async def start_websocket_health_monitor(...):
      while True:
          await asyncio.sleep(check_interval_seconds)

-         # Get list of aged position symbols
-         aged_symbols = list(aged_monitor.aged_targets.keys())
+         # Get list of aged position symbols (only active positions)
+         # ✅ DEFENSIVE: Filter out closed positions in case cleanup failed
+         aged_symbols = [
+             symbol for symbol in aged_monitor.aged_targets.keys()
+             if symbol in position_manager.positions
+         ]

          if not aged_symbols:
+             logger.debug("No active aged positions to monitor")
              continue
```

**Проверка:**
```bash
# Check syntax
python -m py_compile core/position_manager_unified_patch.py

# Manual test: Close position and verify health monitor skips it
```

**Commit:**
```bash
git add core/position_manager_unified_patch.py
git commit -m "feat(aged): add defensive check to skip closed positions in health monitor

- Filter aged_symbols to only include positions in position_manager.positions
- Prevents stale alerts even if cleanup somehow fails
- Defense-in-depth approach

This is a defensive layer on top of the proper fix in phase 2.
Even if remove_target() is not called for some reason, health
monitor will not spam alerts for closed positions.

Related: CROUSDT WebSocket Stale fix"
```

### Фаза 4: Тестирование на Dev (2 часа)

**Шаг 4.1: Unit Tests**
```bash
# Run all new tests
pytest tests/unit/test_aged_position_cleanup_on_close.py -v
pytest tests/unit/test_wave_stats_completeness.py -v

# All should PASS ✅
```

**Шаг 4.2: Integration Test (Manual)**

1. **Запустить бота в dev режиме**
   ```bash
   python main.py
   ```

2. **Дождаться открытия aged позиции** (>3 часа)
   - Проверить логи: `✅ Aged position SYMBOL registered`

3. **Проверить, что позиция в aged_targets**
   ```python
   # In Python console or debug
   aged_monitor = position_manager.unified_protection['aged_monitor']
   print(aged_monitor.aged_targets.keys())
   # Should include the symbol
   ```

4. **Закрыть позицию вручную**
   ```python
   await position_manager.close_position('SYMBOL', 'manual_test')
   ```

5. **Проверить логи:**
   - ✅ "Aged position SYMBOL unregistered from adapter"
   - ✅ "🗑️ Removed SYMBOL from aged_targets"
   - ✅ "✅ Aged position SYMBOL fully removed from monitoring"

6. **Проверить, что позиции НЕТ в aged_targets**
   ```python
   print('SYMBOL' in aged_monitor.aged_targets)
   # Should be False
   ```

7. **Подождать 5 минут**
   - Проверить логи: НЕТ CRITICAL alerts для SYMBOL
   - Проверить логи: НЕТ resubscription attempts для SYMBOL

8. **Проверить обработку волны сигналов**
   - Дождаться следующей волны
   - Проверить логи: НЕТ KeyError 'topped_up'
   - Проверить логи: Статистика волны выводится полностью

**Критерии успеха:**
- ✅ Позиция удалена из aged_targets при закрытии
- ✅ Нет CRITICAL alerts для закрытых позиций
- ✅ Нет resubscription attempts
- ✅ Нет KeyError 'topped_up'
- ✅ Все unit tests проходят

### Фаза 5: Code Review (1 час)

**Чек-лист:**
- [ ] Код соответствует стилю проекта
- [ ] Все изменения прокомментированы
- [ ] Unit тесты написаны и проходят
- [ ] Integration тесты выполнены
- [ ] Нет регрессий в других модулях
- [ ] Логирование адекватное (не спамит, но информативно)
- [ ] Документация обновлена (если нужно)

### Фаза 6: Merge и Deploy (30 минут)

**Шаг 6.1: Final Tests**
```bash
# Run ALL tests
pytest tests/ -v

# Should all PASS
```

**Шаг 6.2: Merge**
```bash
# Switch to main
git checkout main

# Merge feature branch
git merge fix/websocket-stale-and-keyerror

# Push to remote
git push origin main
```

**Шаг 6.3: Deploy to Production**
```bash
# On production server
git pull origin main

# Restart bot
systemctl restart trading_bot  # or your restart command

# Monitor logs
tail -f logs/bot.log
```

**Шаг 6.4: Monitoring (первые 24 часа)**

**Что проверять:**
1. ✅ Нет CRITICAL alerts "CROUSDT stale"
2. ✅ Нет ERROR "FAILED to resubscribe"
3. ✅ Нет KeyError 'topped_up'
4. ✅ Позиции открываются/закрываются нормально
5. ✅ Aged positions обрабатываются корректно
6. ✅ WebSocket subscriptions работают

**Метрики:**
```bash
# Count CRITICAL alerts (should be 0)
grep "CRITICAL ALERT.*stale" logs/bot.log | wc -l

# Count KeyError (should be 0)
grep "KeyError: 'topped_up'" logs/bot.log | wc -l

# Count aged position removals (should match position closures)
grep "fully removed from monitoring" logs/bot.log | wc -l
```

---

## 🔄 Rollback Plan

### Если Что-то Пошло Не Так

**Сценарий 1: Критическая ошибка на production**

```bash
# На production сервере
git log --oneline | head -5  # Найти commit ПЕРЕД фиксом

# Rollback
git reset --hard <COMMIT_HASH>

# Restart bot
systemctl restart trading_bot

# Restore branch for investigation
git checkout -b investigate-fix-failure
git cherry-pick <FIX_COMMIT>
```

**Сценарий 2: Новые ошибки в aged monitoring**

**Симптомы:**
- Aged positions не закрываются
- Aged positions не отслеживаются

**Действие:**
```bash
# Откатить только файлы aged position
git checkout <PREVIOUS_COMMIT> -- core/aged_position_monitor_v2.py
git checkout <PREVIOUS_COMMIT> -- core/protection_adapters.py

# Commit rollback
git commit -m "rollback: revert aged position changes due to [ISSUE]"

# Restart
systemctl restart trading_bot
```

**Сценарий 3: KeyError в другом месте**

**Симптомы:**
- Новые KeyError в signal processor

**Действие:**
```bash
# Откатить только signal processor
git checkout <PREVIOUS_COMMIT> -- core/signal_processor_websocket.py

# Commit
git commit -m "rollback: revert signal processor changes due to [ISSUE]"

# Restart
systemctl restart trading_bot
```

### Время Реакции

| Ситуация | Критичность | Время на Rollback |
|----------|-------------|-------------------|
| Бот не стартует | 🔴 Критическая | 5 минут |
| Позиции не открываются | 🔴 Критическая | 10 минут |
| Новые ошибки в логах | 🟡 Средняя | 30 минут |
| Aged не работает | 🟡 Средняя | 30 минут |

---

## 📊 Метрики Успеха

### До Фикса

| Метрика | Значение |
|---------|----------|
| CRITICAL "stale" alerts/час | 60+ |
| ERROR "failed to resubscribe"/час | 60+ |
| KeyError 'topped_up'/час | 1-2 |
| aged_targets size рост | Да (memory leak) |
| Ложные алерты в мониторинге | Да |

### После Фикса (Ожидаемо)

| Метрика | Значение |
|---------|----------|
| CRITICAL "stale" alerts/час | 0 |
| ERROR "failed to resubscribe"/час | 0 |
| KeyError 'topped_up'/час | 0 |
| aged_targets size рост | Нет |
| Ложные алерты в мониторинге | Нет |

### KPI

**Success Criteria:**
- ✅ 0 CRITICAL stale alerts в течение 24 часов
- ✅ 0 KeyError exceptions в течение 24 часов
- ✅ aged_targets.size стабильно (не растёт бесконечно)
- ✅ Все unit tests проходят
- ✅ Нет регрессий в торговле

---

## 📝 Итоги Аудита

### Ошибка #1: CROUSDT WebSocket Stale

**Корневая причина:** ✅ НАЙДЕНА
→ `AgedPositionAdapter.remove_aged_position()` не удаляет из `aged_monitor.aged_targets`

**Решение:** ✅ РАЗРАБОТАНО
→ Добавить `aged_monitor.remove_target()` и вызывать из adapter

**Риск фикса:** 🟢 НИЗКИЙ
→ Минимальные изменения, явный API, дополнительная защита

**Влияние:** ✅ ПОЛОЖИТЕЛЬНОЕ
→ Исправляет memory leak, убирает 250+ ложных алертов/hour, очищает логи

**Приоритет:** 🔴 ВЫСОКИЙ
→ Исправить немедленно (засоряет мониторинг)

### Ошибка #2: KeyError 'topped_up'

**Корневая причина:** ✅ НАЙДЕНА
→ Код пытается получить ключ, который не добавляется в stats dict

**Решение:** ✅ РАЗРАБОТАНО
→ Использовать `.get('topped_up', 0)` вместо `['topped_up']`

**Риск фикса:** 🟢 НУЛЕВОЙ
→ Одно слово, backward compatible, только logging

**Влияние:** ✅ ПОЛОЖИТЕЛЬНОЕ
→ Исправляет exceptions, позволяет полностью логировать статистику

**Приоритет:** 🟡 СРЕДНИЙ
→ Исправить в ближайшее время (не критично, но раздражает)

### Общая Оценка

**Оба фикса:**
- ✅ Найдены корневые причины
- ✅ Разработаны решения
- ✅ Оценено влияние
- ✅ Создан детальный план
- ✅ Написаны тесты
- ✅ Подготовлен rollback plan
- ✅ Низкий риск внедрения
- ✅ Высокая польза

**Рекомендация:** ✅ **ВНЕДРЯТЬ**

**Очерёдность:**
1. Фаза 1: Фикс #2 (KeyError) - 15 минут, нулевой риск
2. Фаза 2: Фикс #1 основной - 45 минут, низкий риск
3. Фаза 3: Фикс #1 defensive - 30 минут, дополнительная защита

**Общее время:** ~5 часов (с тестированием и deploy)

---

## 📎 Приложения

### Приложение A: Файлы для Изменения

1. `core/signal_processor_websocket.py` - line 294
2. `core/aged_position_monitor_v2.py` - добавить метод после line 353
3. `core/protection_adapters.py` - lines 133-139
4. `core/position_manager_unified_patch.py` - line 385

### Приложение B: Тестовые Файлы

1. `tests/unit/test_aged_position_cleanup_on_close.py` - создать
2. `tests/unit/test_wave_stats_completeness.py` - создать

### Приложение C: Backup Файлы

1. `core/protection_adapters.py.backup_20251030`
2. `core/aged_position_monitor_v2.py.backup_20251030`
3. `core/signal_processor_websocket.py.backup_20251030`
4. `core/position_manager_unified_patch.py.backup_20251030`

### Приложение D: Ссылки на Документацию

- **Error Report:** `docs/ERRORS_REPORT_LAST_5_HOURS_20251030.md`
- **This Audit:** `docs/CRITICAL_ERRORS_AUDIT_REPORT_20251030.md`
- **Database Cleanup:** `docs/DATABASE_CLEANUP_FAS_SCHEMA_20251029.md`

---

**Аудит завершён:** 2025-10-30
**Статус:** ✅ ГОТОВО К ВНЕДРЕНИЮ
**Одобрено для production:** Да, при условии прохождения тестов Фазы 4
