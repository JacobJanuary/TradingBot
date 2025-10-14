# КОМПЛЕКСНЫЙ ПЛАН ВНЕДРЕНИЯ ЛОГИРОВАНИЯ С ТЕСТАМИ

**Дата создания:** 2025-10-14
**Цель:** Увеличить покрытие логирования событий с 25% до 90%+
**Статус:** ГОТОВ К ВЫПОЛНЕНИЮ

---

## EXECUTIVE SUMMARY

**Текущее состояние:**
- ✅ Логируется: 47 событий (только atomic_position_manager.py)
- ❌ Пропущено: 140 событий (75% системы)
- 📊 Покрытие: ~25%

**Целевое состояние:**
- ✅ Логируется: 187+ событий
- ✅ Покрытие: ≥90%
- ✅ Время анализа инцидентов: с 2 часов до 15 минут

**Timeline:** 10-12 дней
**Приоритет:** КРИТИЧНЫЙ

---

## TABLE OF CONTENTS

1. [Фаза 0: Подготовка](#phase-0-preparation)
2. [Фаза 1: Position Manager](#phase-1-position-manager)
3. [Фаза 2: Trailing Stop](#phase-2-trailing-stop)
4. [Фаза 3: Signal Processor WebSocket](#phase-3-signal-processor-websocket)
5. [Фаза 4: Position Synchronizer](#phase-4-position-synchronizer)
6. [Фаза 5: Zombie Manager](#phase-5-zombie-manager)
7. [Фаза 6: Stop Loss Manager](#phase-6-stop-loss-manager)
8. [Фаза 7: Wave Signal Processor & Main](#phase-7-wave-signal-processor-main)
9. [Фаза 8: Верификация и Оптимизация](#phase-8-verification-optimization)
10. [Rollback Strategy](#rollback-strategy)
11. [Testing Infrastructure](#testing-infrastructure)
12. [Success Criteria](#success-criteria)

---

<a name="phase-0-preparation"></a>
## ФАЗА 0: ПОДГОТОВКА (День 0, 2-3 часа)

### Цель
Добавить все необходимые EventType в систему и создать baseline метрики.

---

### Шаг 0.1: Добавление EventType в event_logger.py

**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/event_logger.py`
**Локация:** Класс `EventType(Enum)`, после строки 50 (после `TRANSACTION_ROLLED_BACK`)

**Что делать:**
Добавить 63 новых EventType после существующих.

**Код ДО:**
```python
class EventType(Enum):
    # ... existing types ...
    TRANSACTION_STARTED = "transaction_started"
    TRANSACTION_COMMITTED = "transaction_committed"
    TRANSACTION_ROLLED_BACK = "transaction_rolled_back"
    # END OF CLASS
```

**Код ПОСЛЕ:**
```python
class EventType(Enum):
    # ... existing types ...
    TRANSACTION_STARTED = "transaction_started"
    TRANSACTION_COMMITTED = "transaction_committed"
    TRANSACTION_ROLLED_BACK = "transaction_rolled_back"

    # Wave events (Signal Processing) - 8 types
    WAVE_MONITORING_STARTED = "wave_monitoring_started"
    WAVE_DETECTED = "wave_detected"
    WAVE_COMPLETED = "wave_completed"
    WAVE_NOT_FOUND = "wave_not_found"
    WAVE_DUPLICATE_DETECTED = "wave_duplicate_detected"
    WAVE_PROCESSING_STARTED = "wave_processing_started"
    WAVE_TARGET_REACHED = "wave_target_reached"
    WAVE_BUFFER_EXHAUSTED = "wave_buffer_exhausted"

    # Signal events (Individual Signal Execution) - 6 types
    SIGNAL_EXECUTED = "signal_executed"
    SIGNAL_EXECUTION_FAILED = "signal_execution_failed"
    SIGNAL_FILTERED = "signal_filtered"
    SIGNAL_VALIDATION_FAILED = "signal_validation_failed"
    BAD_SYMBOL_LEAKED = "bad_symbol_leaked"
    INSUFFICIENT_FUNDS = "insufficient_funds"

    # Trailing Stop events (Protection) - 7 types
    TRAILING_STOP_CREATED = "trailing_stop_created"
    TRAILING_STOP_ACTIVATED = "trailing_stop_activated"
    TRAILING_STOP_UPDATED = "trailing_stop_updated"
    TRAILING_STOP_BREAKEVEN = "trailing_stop_breakeven"
    TRAILING_STOP_REMOVED = "trailing_stop_removed"
    PROTECTION_SL_CANCELLED = "protection_sl_cancelled"
    PROTECTION_SL_CANCEL_FAILED = "protection_sl_cancel_failed"

    # Synchronization events (Position Sync) - 9 types
    SYNCHRONIZATION_STARTED = "synchronization_started"
    SYNCHRONIZATION_COMPLETED = "synchronization_completed"
    PHANTOM_POSITION_CLOSED = "phantom_position_closed"
    PHANTOM_POSITION_DETECTED = "phantom_position_detected"
    MISSING_POSITION_ADDED = "missing_position_added"
    MISSING_POSITION_REJECTED = "missing_position_rejected"
    QUANTITY_MISMATCH_DETECTED = "quantity_mismatch_detected"
    QUANTITY_UPDATED = "quantity_updated"
    POSITION_VERIFIED = "position_verified"

    # Zombie Order events (Cleanup) - 6 types
    ZOMBIE_ORDERS_DETECTED = "zombie_orders_detected"
    ZOMBIE_ORDER_CANCELLED = "zombie_order_cancelled"
    ZOMBIE_CLEANUP_COMPLETED = "zombie_cleanup_completed"
    ZOMBIE_ALERT_TRIGGERED = "zombie_alert_triggered"
    AGGRESSIVE_CLEANUP_TRIGGERED = "aggressive_cleanup_triggered"
    TPSL_ORDERS_CLEARED = "tpsl_orders_cleared"

    # Position Manager events (Lifecycle) - 5 types
    POSITION_DUPLICATE_PREVENTED = "position_duplicate_prevented"
    POSITION_NOT_FOUND_ON_EXCHANGE = "position_not_found_on_exchange"
    POSITIONS_LOADED = "positions_loaded"
    POSITIONS_WITHOUT_SL_DETECTED = "positions_without_sl_detected"
    POSITION_CREATION_FAILED = "position_creation_failed"

    # Risk Management events - 1 type
    RISK_LIMITS_EXCEEDED = "risk_limits_exceeded"

    # Symbol/Order Validation events - 2 types
    SYMBOL_UNAVAILABLE = "symbol_unavailable"
    ORDER_BELOW_MINIMUM = "order_below_minimum"

    # Stop Loss Management events (General) - 5 types
    STOP_LOSS_SET_ON_LOAD = "stop_loss_set_on_load"
    STOP_LOSS_SET_FAILED = "stop_loss_set_failed"
    ORPHANED_SL_CLEANED = "orphaned_sl_cleaned"
    EMERGENCY_STOP_PLACED = "emergency_stop_placed"
    STOP_MOVED_TO_BREAKEVEN = "stop_moved_to_breakeven"

    # Recovery events (System Health) - 3 types
    POSITION_RECOVERY_STARTED = "position_recovery_started"
    POSITION_RECOVERY_COMPLETED = "position_recovery_completed"
    INCOMPLETE_POSITION_DETECTED = "incomplete_position_detected"

    # System Health events - 3 types
    PERIODIC_SYNC_STARTED = "periodic_sync_started"
    EMERGENCY_CLOSE_ALL_TRIGGERED = "emergency_close_all_triggered"
    HEALTH_CHECK_FAILED = "health_check_failed"

    # WebSocket events (Connectivity) - 4 types
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"
    WEBSOCKET_ERROR = "websocket_error"
    SIGNALS_RECEIVED = "signals_received"
```

**Тест ПОСЛЕ изменения:**
```python
# tests/test_phase0_event_types.py
"""Test that all new EventTypes are properly added"""
import pytest
from core.event_logger import EventType


def test_all_event_types_exist():
    """Verify that all 63 new EventTypes exist"""
    # Wave events
    assert hasattr(EventType, 'WAVE_MONITORING_STARTED')
    assert hasattr(EventType, 'WAVE_DETECTED')
    assert hasattr(EventType, 'WAVE_COMPLETED')
    assert hasattr(EventType, 'WAVE_NOT_FOUND')
    assert hasattr(EventType, 'WAVE_DUPLICATE_DETECTED')
    assert hasattr(EventType, 'WAVE_PROCESSING_STARTED')
    assert hasattr(EventType, 'WAVE_TARGET_REACHED')
    assert hasattr(EventType, 'WAVE_BUFFER_EXHAUSTED')

    # Signal events
    assert hasattr(EventType, 'SIGNAL_EXECUTED')
    assert hasattr(EventType, 'SIGNAL_EXECUTION_FAILED')
    assert hasattr(EventType, 'SIGNAL_FILTERED')
    assert hasattr(EventType, 'SIGNAL_VALIDATION_FAILED')
    assert hasattr(EventType, 'BAD_SYMBOL_LEAKED')
    assert hasattr(EventType, 'INSUFFICIENT_FUNDS')

    # Trailing Stop events
    assert hasattr(EventType, 'TRAILING_STOP_CREATED')
    assert hasattr(EventType, 'TRAILING_STOP_ACTIVATED')
    assert hasattr(EventType, 'TRAILING_STOP_UPDATED')
    assert hasattr(EventType, 'TRAILING_STOP_BREAKEVEN')
    assert hasattr(EventType, 'TRAILING_STOP_REMOVED')
    assert hasattr(EventType, 'PROTECTION_SL_CANCELLED')
    assert hasattr(EventType, 'PROTECTION_SL_CANCEL_FAILED')

    # Synchronization events
    assert hasattr(EventType, 'SYNCHRONIZATION_STARTED')
    assert hasattr(EventType, 'SYNCHRONIZATION_COMPLETED')
    assert hasattr(EventType, 'PHANTOM_POSITION_CLOSED')
    assert hasattr(EventType, 'PHANTOM_POSITION_DETECTED')
    assert hasattr(EventType, 'MISSING_POSITION_ADDED')
    assert hasattr(EventType, 'MISSING_POSITION_REJECTED')
    assert hasattr(EventType, 'QUANTITY_MISMATCH_DETECTED')
    assert hasattr(EventType, 'QUANTITY_UPDATED')
    assert hasattr(EventType, 'POSITION_VERIFIED')

    # Zombie events
    assert hasattr(EventType, 'ZOMBIE_ORDERS_DETECTED')
    assert hasattr(EventType, 'ZOMBIE_ORDER_CANCELLED')
    assert hasattr(EventType, 'ZOMBIE_CLEANUP_COMPLETED')
    assert hasattr(EventType, 'ZOMBIE_ALERT_TRIGGERED')
    assert hasattr(EventType, 'AGGRESSIVE_CLEANUP_TRIGGERED')
    assert hasattr(EventType, 'TPSL_ORDERS_CLEARED')

    # Position Manager events
    assert hasattr(EventType, 'POSITION_DUPLICATE_PREVENTED')
    assert hasattr(EventType, 'POSITION_NOT_FOUND_ON_EXCHANGE')
    assert hasattr(EventType, 'POSITIONS_LOADED')
    assert hasattr(EventType, 'POSITIONS_WITHOUT_SL_DETECTED')
    assert hasattr(EventType, 'POSITION_CREATION_FAILED')

    # Risk Management
    assert hasattr(EventType, 'RISK_LIMITS_EXCEEDED')

    # Symbol/Order Validation
    assert hasattr(EventType, 'SYMBOL_UNAVAILABLE')
    assert hasattr(EventType, 'ORDER_BELOW_MINIMUM')

    # Stop Loss Management
    assert hasattr(EventType, 'STOP_LOSS_SET_ON_LOAD')
    assert hasattr(EventType, 'STOP_LOSS_SET_FAILED')
    assert hasattr(EventType, 'ORPHANED_SL_CLEANED')
    assert hasattr(EventType, 'EMERGENCY_STOP_PLACED')
    assert hasattr(EventType, 'STOP_MOVED_TO_BREAKEVEN')

    # Recovery events
    assert hasattr(EventType, 'POSITION_RECOVERY_STARTED')
    assert hasattr(EventType, 'POSITION_RECOVERY_COMPLETED')
    assert hasattr(EventType, 'INCOMPLETE_POSITION_DETECTED')

    # System Health
    assert hasattr(EventType, 'PERIODIC_SYNC_STARTED')
    assert hasattr(EventType, 'EMERGENCY_CLOSE_ALL_TRIGGERED')
    assert hasattr(EventType, 'HEALTH_CHECK_FAILED')

    # WebSocket events
    assert hasattr(EventType, 'WEBSOCKET_CONNECTED')
    assert hasattr(EventType, 'WEBSOCKET_DISCONNECTED')
    assert hasattr(EventType, 'WEBSOCKET_ERROR')
    assert hasattr(EventType, 'SIGNALS_RECEIVED')


def test_event_type_count():
    """Verify total EventType count"""
    all_types = [e for e in EventType]
    # Original: 17 types + New: 63 types = 80 total
    assert len(all_types) == 80, f"Expected 80 EventTypes, got {len(all_types)}"


def test_event_type_values_unique():
    """Verify all EventType values are unique"""
    values = [e.value for e in EventType]
    assert len(values) == len(set(values)), "Duplicate event type values found!"


def test_event_type_values_format():
    """Verify all EventType values follow snake_case convention"""
    import re
    pattern = re.compile(r'^[a-z][a-z0-9_]*$')

    for event_type in EventType:
        assert pattern.match(event_type.value), \
            f"EventType {event_type.name} has invalid value: {event_type.value}"
```

**Валидация:**
```bash
# Запустить тест
python -m pytest tests/test_phase0_event_types.py -v

# Ожидаемый результат:
# tests/test_phase0_event_types.py::test_all_event_types_exist PASSED
# tests/test_phase0_event_types.py::test_event_type_count PASSED
# tests/test_phase0_event_types.py::test_event_type_values_unique PASSED
# tests/test_phase0_event_types.py::test_event_type_values_format PASSED
# ========================= 4 passed in 0.05s =========================
```

**Rollback:**
```bash
git checkout -- core/event_logger.py
```

---

### Шаг 0.2: Создание Baseline метрик

**Что делать:**
Сохранить текущее состояние логирования для сравнения.

**SQL запрос для baseline:**
```sql
-- baseline_metrics.sql
-- Сохранить результат в baseline_metrics.txt

-- 1. Текущее покрытие по типам событий
SELECT
    'Current Event Types' as metric,
    COUNT(DISTINCT event_type) as value
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '7 days';

-- 2. Общее количество событий за последнюю неделю
SELECT
    'Total Events (7d)' as metric,
    COUNT(*) as value
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '7 days';

-- 3. События по компонентам
SELECT
    CASE
        WHEN event_type LIKE 'atomic%' THEN 'atomic_position_manager'
        WHEN event_type LIKE 'bot_%' THEN 'main'
        ELSE 'other'
    END as component,
    COUNT(*) as event_count
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY component
ORDER BY event_count DESC;

-- 4. События по severity
SELECT
    severity,
    COUNT(*) as count
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY severity
ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'ERROR' THEN 2
        WHEN 'WARNING' THEN 3
        WHEN 'INFO' THEN 4
    END;

-- 5. Топ-10 самых частых событий
SELECT
    event_type,
    COUNT(*) as count,
    MAX(created_at) as last_seen
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY event_type
ORDER BY count DESC
LIMIT 10;
```

**Выполнение:**
```bash
# Запустить SQL и сохранить результат
psql -h localhost -U trading_bot -d trading_bot_db \
    -f baseline_metrics.sql \
    > baseline_metrics.txt 2>&1

# Сохранить timestamp
echo "Baseline created at: $(date)" >> baseline_metrics.txt
```

**Ожидаемый результат в baseline_metrics.txt:**
```
metric                  | value
------------------------+-------
Current Event Types     | 6
Total Events (7d)       | ~500-1000

component                  | event_count
---------------------------+------------
atomic_position_manager    | ~450
main                       | ~50
other                      | 0

severity  | count
----------+-------
INFO      | ~400
WARNING   | ~80
ERROR     | ~20
CRITICAL  | ~0
```

**Валидация baseline:**
```bash
# Проверить что файл создан
test -f baseline_metrics.txt && echo "Baseline created successfully"

# Проверить что в baseline есть данные
if grep -q "Current Event Types" baseline_metrics.txt; then
    echo "✅ Baseline contains valid data"
else
    echo "❌ Baseline is invalid or empty"
fi
```

**Rollback:**
```bash
# Baseline не требует rollback (это только чтение)
rm -f baseline_metrics.txt
```

---

### Шаг 0.3: Создание SQL скриптов для мониторинга

**Что делать:**
Создать SQL скрипты для быстрой проверки прогресса.

**Файл:** `monitoring_queries.sql`

```sql
-- monitoring_queries.sql
-- Используется для проверки прогресса после каждой фазы

-- Query 1: Current coverage by event type
\echo '=== CURRENT EVENT TYPE COVERAGE ==='
SELECT
    COUNT(DISTINCT event_type) as unique_event_types,
    COUNT(*) as total_events
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Query 2: Events by component (inferred from event_type)
\echo '=== EVENTS BY COMPONENT (24h) ==='
SELECT
    CASE
        WHEN event_type LIKE 'wave_%' THEN 'signal_processor'
        WHEN event_type LIKE 'signal_%' THEN 'signal_processor'
        WHEN event_type LIKE 'trailing_stop_%' THEN 'trailing_stop'
        WHEN event_type LIKE 'phantom_%' OR event_type LIKE 'synchronization_%'
            THEN 'position_synchronizer'
        WHEN event_type LIKE 'zombie_%' THEN 'zombie_manager'
        WHEN event_type LIKE 'position_%' THEN 'position_manager'
        WHEN event_type LIKE 'atomic_%' THEN 'atomic_position_manager'
        WHEN event_type LIKE 'bot_%' THEN 'main'
        ELSE 'other'
    END as component,
    COUNT(*) as event_count,
    COUNT(DISTINCT event_type) as unique_types
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY component
ORDER BY event_count DESC;

-- Query 3: New event types added (compare to baseline)
\echo '=== NEW EVENT TYPES (not in baseline) ==='
WITH baseline_types AS (
    SELECT DISTINCT event_type
    FROM monitoring.events
    WHERE created_at < NOW() - INTERVAL '7 days'
),
current_types AS (
    SELECT DISTINCT event_type
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
)
SELECT
    ct.event_type,
    COUNT(*) as occurrences
FROM current_types ct
LEFT JOIN baseline_types bt ON ct.event_type = bt.event_type
WHERE bt.event_type IS NULL
GROUP BY ct.event_type
ORDER BY occurrences DESC;

-- Query 4: Events by severity
\echo '=== EVENTS BY SEVERITY (24h) ==='
SELECT
    severity,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY severity
ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'ERROR' THEN 2
        WHEN 'WARNING' THEN 3
        WHEN 'INFO' THEN 4
    END;

-- Query 5: Coverage estimation
\echo '=== ESTIMATED COVERAGE ==='
WITH target AS (
    SELECT 80 as target_event_types  -- 17 existing + 63 new
),
current AS (
    SELECT COUNT(DISTINCT event_type) as current_event_types
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
)
SELECT
    c.current_event_types,
    t.target_event_types,
    ROUND(c.current_event_types * 100.0 / t.target_event_types, 2) as coverage_percent
FROM current c, target t;
```

**Создание файла:**
```bash
# Создать файл
cat > monitoring_queries.sql << 'EOF'
[содержимое выше]
EOF

# Проверить что файл создан
test -f monitoring_queries.sql && echo "✅ monitoring_queries.sql created"
```

**Использование:**
```bash
# Быстрая проверка прогресса после любой фазы
psql -h localhost -U trading_bot -d trading_bot_db -f monitoring_queries.sql
```

---

### Критерии успеха Фазы 0

- ✅ Все 63 новых EventType добавлены в event_logger.py
- ✅ Тест test_phase0_event_types.py проходит (4/4 tests passed)
- ✅ baseline_metrics.txt создан и содержит валидные данные
- ✅ monitoring_queries.sql создан и выполняется без ошибок
- ✅ Commit сделан: "Phase 0: Add 63 new EventTypes and baseline metrics"

---

<a name="phase-1-position-manager"></a>
## ФАЗА 1: POSITION MANAGER (Дни 1-2, 8-10 часов)

### Цель
Внедрить логирование для 52 событий в position_manager.py - сердце системы управления позициями.

**Приоритет:** КРИТИЧНЫЙ
**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py`

---

### Шаг 1.0: Добавить импорт EventLogger

**Локация:** Начало файла, после существующих импортов (примерно строка 10)

**Код ДО:**
```python
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
# ... other imports ...

logger = logging.getLogger(__name__)
```

**Код ПОСЛЕ:**
```python
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
# ... other imports ...
from core.event_logger import get_event_logger, EventType

logger = logging.getLogger(__name__)
```

**Тест (manual verification):**
```bash
# Проверить что импорт не вызывает ошибок
python -c "from core.position_manager import PositionManager; print('✅ Import successful')"
```

---

### Шаг 1.1: Phantom Position Detection

**Локация:** `position_manager.py`, функция `_check_for_phantom_positions()`, примерно строка 290

**Контекст операции:**
Phantom position - это позиция в БД, которой нет на бирже. Критично логировать для обнаружения несинхронизации.

**Код ДО:**
```python
# В функции _check_for_phantom_positions()
async def _check_for_phantom_positions(self, exchange_name: str):
    """Check for positions in DB that don't exist on exchange"""
    # ... код получения позиций ...

    for symbol in db_positions:
        if symbol not in exchange_positions:
            logger.warning(f"🗑️ PHANTOM detected during load: {symbol} - closing in database")
            # Close phantom position in DB
            await self._close_position_in_db(
                position_id=db_positions[symbol]['id'],
                reason='phantom_detected',
                realized_pnl=0.0
            )
```

**Код ПОСЛЕ:**
```python
# В функции _check_for_phantom_positions()
async def _check_for_phantom_positions(self, exchange_name: str):
    """Check for positions in DB that don't exist on exchange"""
    # ... код получения позиций ...

    for symbol in db_positions:
        if symbol not in exchange_positions:
            logger.warning(f"🗑️ PHANTOM detected during load: {symbol} - closing in database")

            # LOG EVENT: Phantom detected
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.PHANTOM_POSITION_DETECTED,
                    {
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'position_id': db_positions[symbol]['id'],
                        'db_quantity': float(db_positions[symbol].get('quantity', 0)),
                        'entry_price': float(db_positions[symbol].get('entry_price', 0)),
                        'action': 'closing_in_db'
                    },
                    position_id=db_positions[symbol]['id'],
                    symbol=symbol,
                    exchange=exchange_name,
                    severity='WARNING'
                )

            # Close phantom position in DB
            await self._close_position_in_db(
                position_id=db_positions[symbol]['id'],
                reason='phantom_detected',
                realized_pnl=0.0
            )
```

**Тест ДО изменения:**
```python
# tests/phase1/test_phantom_detection_before.py
"""Test that phantom detection is NOT logged to DB yet (baseline)"""
import pytest
import asyncio
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_phantom_not_logged_in_db_yet(db_pool):
    """
    Verify that phantom position detection is NOT logged to monitoring.events
    This test SHOULD FAIL before implementing the logging
    """
    # Get recent phantom events
    async with db_pool.acquire() as conn:
        result = await conn.fetch("""
            SELECT * FROM monitoring.events
            WHERE event_type = 'phantom_position_detected'
            AND created_at > NOW() - INTERVAL '1 hour'
        """)

    # This assertion SHOULD FAIL (expected behavior before implementation)
    assert len(result) == 0, \
        "Phantom events found in DB - logging already implemented?"
```

**Тест ПОСЛЕ изменения:**
```python
# tests/phase1/test_phantom_detection_after.py
"""Test that phantom detection is correctly logged to DB"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from core.position_manager import PositionManager
from core.event_logger import EventType


@pytest.mark.asyncio
async def test_phantom_logged_correctly(db_pool, mock_exchange):
    """
    Verify that phantom position detection IS logged to monitoring.events
    This test SHOULD PASS after implementing the logging
    """
    # Setup: Create a position in DB but not on exchange
    async with db_pool.acquire() as conn:
        position_id = await conn.fetchval("""
            INSERT INTO positions (
                symbol, exchange, side, quantity, entry_price,
                status, opened_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """, 'TESTUSDT', 'binance', 'long', 0.1, 50000.0, 'open', datetime.now(timezone.utc))

    # Mock exchange to return empty positions
    mock_exchange.get_positions = AsyncMock(return_value=[])

    # Initialize PositionManager and trigger phantom check
    pm = PositionManager(db_pool, {'binance': mock_exchange}, config=Mock())
    await pm._check_for_phantom_positions('binance')

    # Wait for event logger to flush (max 6 seconds)
    await asyncio.sleep(6)

    # Verify: Check that event was logged
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT
                event_type,
                symbol,
                exchange,
                severity,
                event_data::jsonb->>'action' as action
            FROM monitoring.events
            WHERE event_type = 'phantom_position_detected'
            AND symbol = 'TESTUSDT'
            AND position_id = $1
            ORDER BY created_at DESC
            LIMIT 1
        """, position_id)

    # Assertions
    assert result is not None, "Phantom event not found in database"
    assert result['event_type'] == 'phantom_position_detected'
    assert result['symbol'] == 'TESTUSDT'
    assert result['exchange'] == 'binance'
    assert result['severity'] == 'WARNING'
    assert result['action'] == 'closing_in_db'

    # Cleanup
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM positions WHERE id = $1", position_id)
        await conn.execute("DELETE FROM monitoring.events WHERE position_id = $1", position_id)
```

**SQL Валидация:**
```sql
-- Проверка после запуска бота с новым кодом
SELECT
    event_type,
    symbol,
    exchange,
    severity,
    event_data->>'action' as action,
    event_data->>'db_quantity' as db_quantity,
    created_at
FROM monitoring.events
WHERE event_type = 'phantom_position_detected'
AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 10;

-- Ожидаемый результат:
-- Если были phantom positions, должны появиться записи
-- event_type: phantom_position_detected
-- severity: WARNING
-- action: closing_in_db
```

**Rollback:**
```bash
# Откатить изменения в position_manager.py
git diff core/position_manager.py > phase1_step1_changes.patch
git checkout -- core/position_manager.py

# Проверить что код работает без изменений
python -m pytest tests/ -k "not phantom" -v

# Применить снова при необходимости
git apply phase1_step1_changes.patch
```

---

### Шаг 1.2: Position Synchronization Started

**Локация:** `position_manager.py`, функция `synchronize_positions()`, примерно строка 205

**Контекст:**
Начало синхронизации позиций между БД и биржами - критично для трейсинга.

**Код ДО:**
```python
async def synchronize_positions(self):
    """Synchronize positions with exchanges"""
    logger.info("🔄 Synchronizing positions with exchanges...")

    for exchange_name, exchange in self.exchanges.items():
        # ... synchronization logic ...
```

**Код ПОСЛЕ:**
```python
async def synchronize_positions(self):
    """Synchronize positions with exchanges"""
    logger.info("🔄 Synchronizing positions with exchanges...")

    # LOG EVENT: Sync started
    sync_id = f"sync_{datetime.now(timezone.utc).timestamp()}"
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.SYNC_STARTED,
            {
                'exchanges': list(self.exchanges.keys()),
                'sync_id': sync_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            },
            severity='INFO',
            correlation_id=sync_id
        )

    for exchange_name, exchange in self.exchanges.items():
        # ... synchronization logic ...
```

**Тест ПОСЛЕ:**
```python
# tests/phase1/test_position_sync_logging.py
@pytest.mark.asyncio
async def test_sync_started_logged(db_pool, mock_exchanges):
    """Verify that position sync start is logged"""
    pm = PositionManager(db_pool, mock_exchanges, config=Mock())

    # Trigger sync
    await pm.synchronize_positions()

    # Wait for event flush
    await asyncio.sleep(6)

    # Check event
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT * FROM monitoring.events
            WHERE event_type = 'sync_started'
            AND created_at > NOW() - INTERVAL '1 minute'
            ORDER BY created_at DESC
            LIMIT 1
        """)

    assert result is not None
    assert result['event_type'] == 'sync_started'
    assert result['severity'] == 'INFO'
```

---

### Шаг 1.3: Risk Limits Exceeded

**Локация:** `position_manager.py`, функция `open_position()`, проверка риск-лимитов, примерно строка 648

**Контекст:**
Критично логировать отклонение позиций из-за превышения риск-лимитов для анализа упущенных возможностей.

**Код ДО:**
```python
async def open_position(self, request: PositionRequest):
    """Open new position"""
    symbol = request.symbol
    exchange_name = request.exchange

    # Check risk limits
    if not self._check_risk_limits(request):
        logger.warning(f"Risk limits exceeded for {symbol}")
        return None
```

**Код ПОСЛЕ:**
```python
async def open_position(self, request: PositionRequest):
    """Open new position"""
    symbol = request.symbol
    exchange_name = request.exchange

    # Check risk limits
    if not self._check_risk_limits(request):
        logger.warning(f"Risk limits exceeded for {symbol}")

        # LOG EVENT: Risk limits exceeded
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.RISK_LIMITS_EXCEEDED,
                {
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'current_exposure': float(self.total_exposure),
                    'max_exposure': float(self.config.max_exposure_usd),
                    'position_count': self.position_count,
                    'max_positions': self.config.max_positions,
                    'attempted_position_size': float(request.position_size_usd),
                    'signal_id': request.signal_id
                },
                symbol=symbol,
                exchange=exchange_name,
                severity='WARNING'
            )

        return None
```

**Тест ПОСЛЕ:**
```python
# tests/phase1/test_risk_limits_logging.py
@pytest.mark.asyncio
async def test_risk_limits_exceeded_logged(db_pool, mock_exchange):
    """Verify that risk limit violations are logged"""
    # Setup: Configure low risk limits
    config = Mock()
    config.max_positions = 1
    config.max_exposure_usd = 100.0

    pm = PositionManager(db_pool, {'binance': mock_exchange}, config=config)

    # Add one position to reach limit
    pm.position_count = 1

    # Try to open another position (should be rejected)
    request = PositionRequest(
        symbol='BTCUSDT',
        exchange='binance',
        side='long',
        position_size_usd=50.0,
        signal_id='test_signal_123'
    )

    result = await pm.open_position(request)

    # Should be rejected
    assert result is None

    # Wait for event flush
    await asyncio.sleep(6)

    # Check event
    async with db_pool.acquire() as conn:
        event = await conn.fetchrow("""
            SELECT * FROM monitoring.events
            WHERE event_type = 'risk_limits_exceeded'
            AND symbol = 'BTCUSDT'
            AND created_at > NOW() - INTERVAL '1 minute'
            ORDER BY created_at DESC
            LIMIT 1
        """)

    assert event is not None
    assert event['severity'] == 'WARNING'
    assert event['symbol'] == 'BTCUSDT'

    event_data = json.loads(event['event_data'])
    assert event_data['position_count'] >= config.max_positions
```

**SQL Валидация:**
```sql
-- Проверка risk limit violations за последний час
SELECT
    symbol,
    event_data->>'current_exposure' as current_exposure,
    event_data->>'max_exposure' as max_exposure,
    event_data->>'position_count' as position_count,
    event_data->>'max_positions' as max_positions,
    created_at
FROM monitoring.events
WHERE event_type = 'risk_limits_exceeded'
AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;

-- Ожидаемый результат:
-- Если лимиты превышались, появятся записи с деталями
```

---

### Шаг 1.4: Position Closed

**Локация:** `position_manager.py`, функция `close_position()`, примерно строка 1325

**Контекст:**
Один из самых критичных событий - закрытие позиции с PnL.

**Код ДО:**
```python
async def close_position(self, symbol: str, reason: str = 'manual'):
    """Close position"""
    position = self.positions.get(symbol)
    if not position:
        return False

    # ... closing logic ...

    realized_pnl = # ... calculate PnL ...
    realized_pnl_percent = # ... calculate percent ...

    logger.info(
        f"Position closed: {symbol} {reason} "
        f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
    )

    # Update DB
    await self._update_position_status(position.id, 'closed')

    # Remove from memory
    del self.positions[symbol]

    return True
```

**Код ПОСЛЕ:**
```python
async def close_position(self, symbol: str, reason: str = 'manual'):
    """Close position"""
    position = self.positions.get(symbol)
    if not position:
        return False

    # ... closing logic ...

    realized_pnl = # ... calculate PnL ...
    realized_pnl_percent = # ... calculate percent ...
    exit_price = # ... get exit price ...
    duration_hours = (datetime.now(timezone.utc) - position.opened_at).total_seconds() / 3600

    logger.info(
        f"Position closed: {symbol} {reason} "
        f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
    )

    # LOG EVENT: Position closed
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.POSITION_CLOSED,
            {
                'symbol': symbol,
                'exchange': position.exchange,
                'side': position.side,
                'reason': reason,
                'realized_pnl': float(realized_pnl),
                'realized_pnl_percent': float(realized_pnl_percent),
                'entry_price': float(position.entry_price),
                'exit_price': float(exit_price),
                'quantity': float(position.quantity),
                'duration_hours': round(duration_hours, 2),
                'opened_at': position.opened_at.isoformat(),
                'closed_at': datetime.now(timezone.utc).isoformat()
            },
            position_id=position.id,
            symbol=symbol,
            exchange=position.exchange,
            severity='INFO'
        )

    # Update DB
    await self._update_position_status(position.id, 'closed')

    # Remove from memory
    del self.positions[symbol]

    return True
```

**Тест ПОСЛЕ:**
```python
# tests/phase1/test_position_closed_logging.py
@pytest.mark.asyncio
async def test_position_closed_logged(db_pool, mock_exchange):
    """Verify that position closing is logged with full details"""
    # Setup: Create and open a position
    pm = PositionManager(db_pool, {'binance': mock_exchange}, config=Mock())

    # Insert test position
    async with db_pool.acquire() as conn:
        position_id = await conn.fetchval("""
            INSERT INTO positions (
                symbol, exchange, side, quantity, entry_price,
                status, opened_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """, 'ETHUSDT', 'binance', 'long', 0.5, 2000.0, 'open',
             datetime.now(timezone.utc))

    # Load position into memory
    await pm.load_positions_from_db()

    # Close position
    result = await pm.close_position('ETHUSDT', reason='take_profit')

    assert result is True

    # Wait for event flush
    await asyncio.sleep(6)

    # Verify event
    async with db_pool.acquire() as conn:
        event = await conn.fetchrow("""
            SELECT * FROM monitoring.events
            WHERE event_type = 'position_closed'
            AND symbol = 'ETHUSDT'
            AND position_id = $1
            ORDER BY created_at DESC
            LIMIT 1
        """, position_id)

    assert event is not None
    assert event['event_type'] == 'position_closed'
    assert event['symbol'] == 'ETHUSDT'
    assert event['severity'] == 'INFO'

    event_data = json.loads(event['event_data'])
    assert event_data['reason'] == 'take_profit'
    assert 'realized_pnl' in event_data
    assert 'entry_price' in event_data
    assert 'exit_price' in event_data
    assert 'duration_hours' in event_data

    # Cleanup
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM positions WHERE id = $1", position_id)
        await conn.execute("DELETE FROM monitoring.events WHERE position_id = $1", position_id)
```

---

### Шаг 1.5: Positions Loaded from DB

**Локация:** `position_manager.py`, функция `load_positions_from_db()`, примерно строка 339

**Код ПОСЛЕ:**
```python
async def load_positions_from_db(self):
    """Load open positions from database"""
    # ... loading logic ...

    logger.info(f"📊 Loaded {len(self.positions)} positions from database")
    logger.info(f"💰 Total exposure: ${self.total_exposure:.2f}")

    # LOG EVENT: Positions loaded
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.POSITIONS_LOADED,
            {
                'count': len(self.positions),
                'total_exposure': float(self.total_exposure),
                'exchanges': list(set(p.exchange for p in self.positions.values())),
                'symbols': list(self.positions.keys())
            },
            severity='INFO'
        )
```

---

### Шаг 1.6-1.52: Остальные события position_manager.py

По аналогичной методологии внедрить логирование для:

- Positions without SL detected (строка ~354)
- Stop loss set on load (строка ~393)
- Stop loss set failed (строка ~400)
- Trailing stop initialized (строка ~430)
- Position duplicate prevented (строка ~643)
- Symbol unavailable (строка ~767)
- Order below minimum (строка ~771)
- Orphaned SL cleaned (строка ~1342)
- Position not found on exchange (строка ~260)
- ... (остальные 43 события)

**Структура одинакова:**
1. Определить точную локацию
2. Написать код ДО/ПОСЛЕ
3. Создать тест
4. Добавить SQL валидацию

---

### Критерии успеха Фазы 1

**SQL для проверки:**
```sql
-- Проверка покрытия position_manager после Фазы 1
SELECT
    COUNT(DISTINCT event_type) FILTER (
        WHERE event_type IN (
            'phantom_position_detected',
            'phantom_position_closed',
            'synchronization_started',
            'risk_limits_exceeded',
            'position_closed',
            'positions_loaded',
            'positions_without_sl_detected',
            'stop_loss_set_on_load',
            'stop_loss_set_failed',
            'orphaned_sl_cleaned',
            'position_duplicate_prevented',
            'symbol_unavailable',
            'order_below_minimum',
            'position_not_found_on_exchange'
            -- ... add all 52 position_manager event types
        )
    ) as implemented_events,
    52 as target_events,
    ROUND(
        COUNT(DISTINCT event_type) FILTER (
            WHERE event_type IN (...)
        ) * 100.0 / 52,
        2
    ) as coverage_percent
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Ожидаемый результат:
-- implemented_events: 52
-- target_events: 52
-- coverage_percent: 100.00
```

**Критерии:**
- ✅ Все 52 события position_manager.py логируются
- ✅ Все тесты phase1/* проходят
- ✅ SQL query показывает 100% покрытие для position_manager
- ✅ Performance overhead <5ms per event
- ✅ Commit: "Phase 1: Implement event logging for position_manager (52 events)"

---

<a name="phase-2-trailing-stop"></a>
## ФАЗА 2: TRAILING STOP (День 3, 4-6 часов)

### Цель
Внедрить логирование для 18 событий в trailing_stop.py - защита позиций.

**Приоритет:** КРИТИЧНЫЙ
**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`

---

### Шаг 2.0: Добавить импорт

**Код ПОСЛЕ:**
```python
from core.event_logger import get_event_logger, EventType
```

---

### Шаг 2.1: Trailing Stop Created

**Локация:** `trailing_stop.py`, функция `create()`, примерно строка 160

**Код ДО:**
```python
def create(cls, symbol: str, side: str, entry_price: Decimal, ...):
    """Create new trailing stop"""
    ts = cls(symbol, side, entry_price, ...)

    logger.info(
        f"Created trailing stop for {symbol} {side}: "
        f"entry={entry_price}, activation={ts.activation_price}, "
        f"initial_stop={initial_stop}"
    )

    return ts
```

**Код ПОСЛЕ:**
```python
async def create(cls, symbol: str, side: str, entry_price: Decimal, ...):
    """Create new trailing stop"""
    ts = cls(symbol, side, entry_price, ...)

    logger.info(
        f"Created trailing stop for {symbol} {side}: "
        f"entry={entry_price}, activation={ts.activation_price}, "
        f"initial_stop={initial_stop}"
    )

    # LOG EVENT: TS Created
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.TRAILING_STOP_CREATED,
            {
                'symbol': symbol,
                'side': side,
                'entry_price': float(entry_price),
                'activation_price': float(ts.activation_price),
                'initial_stop': float(initial_stop) if initial_stop else None,
                'activation_percent': float(config.activation_percent),
                'trailing_distance': float(config.trailing_distance)
            },
            symbol=symbol,
            severity='INFO',
            correlation_id=f"ts_lifecycle_{symbol}"
        )

    return ts
```

**Тест ПОСЛЕ:**
```python
# tests/phase2/test_trailing_stop_created.py
@pytest.mark.asyncio
async def test_trailing_stop_created_logged(db_pool):
    """Verify TS creation is logged"""
    from protection.trailing_stop import TrailingStop

    # Create TS
    ts = await TrailingStop.create(
        symbol='BTCUSDT',
        side='long',
        entry_price=Decimal('50000.0'),
        config=Mock(activation_percent=2.0, trailing_distance=1.0)
    )

    # Wait for event flush
    await asyncio.sleep(6)

    # Check event
    async with db_pool.acquire() as conn:
        event = await conn.fetchrow("""
            SELECT * FROM monitoring.events
            WHERE event_type = 'trailing_stop_created'
            AND symbol = 'BTCUSDT'
            AND created_at > NOW() - INTERVAL '1 minute'
            ORDER BY created_at DESC
            LIMIT 1
        """)

    assert event is not None
    assert event['event_type'] == 'trailing_stop_created'
    assert event['severity'] == 'INFO'

    event_data = json.loads(event['event_data'])
    assert event_data['side'] == 'long'
    assert float(event_data['entry_price']) == 50000.0
    assert 'activation_price' in event_data
```

---

### Шаг 2.2: Trailing Stop Activated

**Локация:** `trailing_stop.py`, функция `update()`, активация TS, примерно строка 284

**Код ПОСЛЕ:**
```python
async def update(self, current_price: Decimal):
    """Update trailing stop based on current price"""
    self.current_price = current_price

    # Check if should activate
    if self.state == TSState.WAITING_ACTIVATION:
        if self._should_activate(current_price):
            self.state = TSState.ACTIVE
            self._update_stop_price(current_price)

            logger.info(
                f"✅ {self.symbol}: Trailing stop ACTIVATED at {current_price:.4f}, "
                f"stop at {self.current_stop_price:.4f}"
            )

            # LOG EVENT: TS Activated
            event_logger = get_event_logger()
            if event_logger:
                profit_percent = self._calculate_profit_percent()
                distance = self._calculate_distance_percent()

                await event_logger.log_event(
                    EventType.TRAILING_STOP_ACTIVATED,
                    {
                        'symbol': self.symbol,
                        'activation_price': float(current_price),
                        'stop_price': float(self.current_stop_price),
                        'distance_percent': float(distance),
                        'entry_price': float(self.entry_price),
                        'profit_percent': float(profit_percent),
                        'highest_price': float(self.highest_price)
                    },
                    symbol=self.symbol,
                    severity='INFO',
                    correlation_id=f"ts_lifecycle_{self.symbol}"
                )
```

**Тест ПОСЛЕ:**
```python
# tests/phase2/test_trailing_stop_activated.py
@pytest.mark.asyncio
async def test_trailing_stop_activated_logged(db_pool):
    """Verify TS activation is logged"""
    # Create TS in WAITING state
    ts = await TrailingStop.create(
        symbol='ETHUSDT',
        side='long',
        entry_price=Decimal('2000.0'),
        config=Mock(activation_percent=2.0)
    )

    # Update with price that triggers activation (2% above entry)
    activation_price = Decimal('2040.0')  # 2% above 2000
    await ts.update(activation_price)

    # Wait for event flush
    await asyncio.sleep(6)

    # Check event
    async with db_pool.acquire() as conn:
        event = await conn.fetchrow("""
            SELECT * FROM monitoring.events
            WHERE event_type = 'trailing_stop_activated'
            AND symbol = 'ETHUSDT'
            AND created_at > NOW() - INTERVAL '1 minute'
            ORDER BY created_at DESC
            LIMIT 1
        """)

    assert event is not None
    event_data = json.loads(event['event_data'])
    assert event_data['symbol'] == 'ETHUSDT'
    assert float(event_data['activation_price']) == 2040.0
    assert 'stop_price' in event_data
    assert 'profit_percent' in event_data
```

---

### Шаг 2.3: Trailing Stop Updated

**Локация:** `trailing_stop.py`, функция `update()`, обновление стопа, примерно строка 332

**Код ПОСЛЕ:**
```python
# Inside update() when stop price is updated
if new_stop_price > self.current_stop_price:
    old_stop = self.current_stop_price
    self.current_stop_price = new_stop_price
    self.update_count += 1

    improvement = ((new_stop_price - old_stop) / old_stop) * 100

    logger.info(
        f"📈 {self.symbol}: Trailing stop updated from {old_stop:.4f} "
        f"to {new_stop_price:.4f} (+{improvement:.2f}%)"
    )

    # LOG EVENT: TS Updated
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.TRAILING_STOP_UPDATED,
            {
                'symbol': self.symbol,
                'old_stop': float(old_stop),
                'new_stop': float(new_stop_price),
                'improvement_percent': float(improvement),
                'highest_price': float(self.highest_price),
                'current_price': float(current_price),
                'update_count': self.update_count
            },
            symbol=self.symbol,
            severity='INFO',
            correlation_id=f"ts_lifecycle_{self.symbol}"
        )
```

---

### Шаг 2.4: Breakeven Activated

**Локация:** `trailing_stop.py`, breakeven logic, примерно строка 238

**Код ПОСЛЕ:**
```python
if should_move_to_breakeven:
    self.current_stop_price = self.entry_price
    self.breakeven_moved = True

    profit = self._calculate_profit_percent()

    logger.info(
        f"{self.symbol}: Moving stop to breakeven at {profit:.2f}% profit"
    )

    # LOG EVENT: Breakeven
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.TRAILING_STOP_BREAKEVEN,
            {
                'symbol': self.symbol,
                'entry_price': float(self.entry_price),
                'breakeven_price': float(self.current_stop_price),
                'current_price': float(current_price),
                'profit_percent': float(profit)
            },
            symbol=self.symbol,
            severity='INFO',
            correlation_id=f"ts_lifecycle_{self.symbol}"
        )
```

---

### Шаг 2.5-2.18: Остальные события trailing_stop.py

Внедрить логирование для:
- Protection SL cancelled (строка ~458)
- Protection SL cancel failed (строка ~482)
- Trailing stop removed (строка ~534)
- ... (остальные 11 событий)

---

### Критерии успеха Фазы 2

```sql
-- Проверка покрытия trailing_stop после Фазы 2
SELECT
    COUNT(DISTINCT event_type) FILTER (
        WHERE event_type IN (
            'trailing_stop_created',
            'trailing_stop_activated',
            'trailing_stop_updated',
            'trailing_stop_breakeven',
            'trailing_stop_removed',
            'protection_sl_cancelled',
            'protection_sl_cancel_failed'
            -- ... all 18 trailing_stop events
        )
    ) as implemented_events,
    18 as target_events
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Ожидаемый результат: 18/18
```

- ✅ Все 18 событий trailing_stop.py логируются
- ✅ Все тесты phase2/* проходят
- ✅ Commit: "Phase 2: Implement event logging for trailing_stop (18 events)"

---

<a name="phase-3-signal-processor-websocket"></a>
## ФАЗА 3: SIGNAL PROCESSOR WEBSOCKET (День 4, 6-8 часов)

### Цель
Внедрить логирование для 25 событий в signal_processor_websocket.py - entry point системы.

**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/signal_processor_websocket.py`

---

### Шаг 3.1: Wave Detected

**Локация:** `signal_processor_websocket.py`, wave detection, примерно строка 221

**Код ПОСЛЕ:**
```python
# Wave detected
wave_signals = [s for s in signal_buffer if s['timestamp'] == expected_wave_timestamp]

if len(wave_signals) >= min_signals:
    logger.info(
        f"🌊 Wave detected! Processing {len(wave_signals)} signals "
        f"for {expected_wave_timestamp}"
    )

    # LOG EVENT: Wave detected
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.WAVE_DETECTED,
            {
                'wave_timestamp': expected_wave_timestamp,
                'signal_count': len(wave_signals),
                'min_required': min_signals,
                'first_seen': datetime.now(timezone.utc).isoformat()
            },
            severity='INFO',
            correlation_id=f"wave_{expected_wave_timestamp}"
        )

    # Process wave...
```

---

### Шаг 3.2: Wave Completed

**Локация:** `signal_processor_websocket.py`, после обработки волны, примерно строка 323

**Код ПОСЛЕ:**
```python
# Wave processing complete
duration = (datetime.now(timezone.utc) - wave_started_at).total_seconds()

logger.info(
    f"🎯 Wave {expected_wave_timestamp} complete: "
    f"{executed_count} positions opened, {failed_count} failed..."
)

# LOG EVENT: Wave completed
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.WAVE_COMPLETED,
        {
            'wave_timestamp': expected_wave_timestamp,
            'positions_opened': executed_count,
            'failed': failed_count,
            'validation_errors': len(result.get('failed', [])),
            'duplicates': len(result.get('skipped', [])),
            'duration_seconds': round(duration, 2),
            'total_signals_processed': len(final_signals),
            'target_positions': max_trades
        },
        severity='INFO',
        correlation_id=f"wave_{expected_wave_timestamp}"
    )
```

**Тест ПОСЛЕ:**
```python
# tests/phase3/test_wave_lifecycle.py
@pytest.mark.asyncio
async def test_wave_lifecycle_logged(db_pool, mock_signal_server):
    """Verify complete wave lifecycle is logged"""
    # Setup signal processor
    sp = SignalProcessorWebSocket(...)

    # Simulate wave arrival
    test_signals = [
        {'symbol': 'BTCUSDT', 'action': 'buy', 'timestamp': '2024-01-01T12:00:00'},
        {'symbol': 'ETHUSDT', 'action': 'buy', 'timestamp': '2024-01-01T12:00:00'},
        # ... more signals
    ]

    # Process wave
    await sp.process_wave(test_signals)

    # Wait for events
    await asyncio.sleep(6)

    # Check events
    async with db_pool.acquire() as conn:
        events = await conn.fetch("""
            SELECT event_type, created_at
            FROM monitoring.events
            WHERE correlation_id = 'wave_2024-01-01T12:00:00'
            ORDER BY created_at
        """)

    event_types = [e['event_type'] for e in events]

    # Should have: wave_detected, signal_executed (multiple), wave_completed
    assert 'wave_detected' in event_types
    assert 'wave_completed' in event_types
    assert event_types.count('signal_executed') >= 1
```

---

### Шаг 3.3: Signal Executed

**Локация:** `signal_processor_websocket.py`, после успешного исполнения сигнала, примерно строка 307

**Код ПОСЛЕ:**
```python
if position_created:
    executed_count += 1
    logger.info(f"✅ Signal {idx+1}/{len(final_signals)} ({symbol}) executed")

    # LOG EVENT: Signal executed
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.SIGNAL_EXECUTED,
            {
                'wave_timestamp': wave_timestamp,
                'signal_id': signal.get('id'),
                'symbol': symbol,
                'side': signal.get('action'),
                'signal_index': idx + 1,
                'total_signals': len(final_signals),
                'executed_count': executed_count
            },
            symbol=symbol,
            severity='INFO',
            correlation_id=f"wave_{wave_timestamp}"
        )
```

---

### Шаг 3.4-3.25: Остальные события signal_processor_websocket.py

Внедрить для:
- Wave not found (строка ~337)
- Wave duplicate detected (строка ~203)
- Signal execution failed (строка ~310)
- WebSocket connected/disconnected/error (строки 487, 491, 496)
- Signals received (строка ~163)
- ... (остальные 16 событий)

---

### Критерии успеха Фазы 3

```sql
SELECT
    COUNT(DISTINCT event_type) FILTER (
        WHERE event_type IN (
            'wave_detected', 'wave_completed', 'wave_not_found',
            'signal_executed', 'signal_execution_failed',
            'websocket_connected', 'websocket_disconnected',
            'websocket_error', 'signals_received'
            -- ... all 25 signal_processor events
        )
    ) as implemented_events,
    25 as target_events
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours';
```

- ✅ Все 25 событий signal_processor_websocket.py логируются
- ✅ Commit: "Phase 3: Implement event logging for signal_processor_websocket (25 events)"

---

<a name="phase-4-position-synchronizer"></a>
## ФАЗА 4: POSITION SYNCHRONIZER (День 5, 3-4 часа)

### Цель
Внедрить логирование для 10 событий в position_synchronizer.py.

**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_synchronizer.py`

### События для логирования:
1. Synchronization started
2. Synchronization completed (with stats)
3. Phantom position closed
4. Missing position added
5. Missing position rejected
6. Quantity mismatch detected
7. Quantity updated
8. Position verified
9. Stale position filtered
10. Exchange position fetch error

По аналогии с Фазами 1-3.

---

<a name="phase-5-zombie-manager"></a>
## ФАЗА 5: ZOMBIE MANAGER (День 6, 2-3 часа)

### Цель
Внедрить логирование для 8 событий в zombie_manager.py.

**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/zombie_manager.py`

### События:
1. Zombie orders detected
2. Zombie order cancelled
3. Zombie cleanup completed
4. TP/SL orders cleared
5. Aggressive cleanup triggered
6. Zombie alert triggered
7. Zombie cancel failed
8. All orders for symbol cancelled

---

<a name="phase-6-stop-loss-manager"></a>
## ФАЗА 6: STOP LOSS MANAGER (День 7, 3-4 часа)

### Цель
Внедрить логирование для 15 событий в stop_loss_manager.py.

**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/stop_loss_manager.py`

### События:
1. Stop losses setup
2. Emergency stop placed
3. Stop moved to breakeven
4. Trailing stop updated
5. ATR calculation failed
6. Partial level triggered
7. Time stop triggered
8. Stop order placement failed
9. Stop order cancelled
10. All stops cancelled
11. Smart trailing activated
12. Maximum slippage exceeded
13. Stop price rounding issues
14. Position stops cleanup
15. Stop configuration validation failed

---

<a name="phase-7-wave-signal-processor-main"></a>
## ФАЗА 7: WAVE SIGNAL PROCESSOR & MAIN (День 8, 3-4 часа)

### Цель
Завершить внедрение в оставшихся компонентах.

### Файлы:
1. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/wave_signal_processor.py` (12 событий)
2. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py` (8 событий, 2 уже есть)

---

<a name="phase-8-verification-optimization"></a>
## ФАЗА 8: ВЕРИФИКАЦИЯ И ОПТИМИЗАЦИЯ (Дни 9-10, 8-10 часов)

### Цель
Полная верификация покрытия, performance testing, query optimization.

---

### Шаг 8.1: Полная верификация покрытия

**SQL для финальной проверки:**
```sql
-- final_coverage_report.sql

-- 1. Overall coverage
WITH target_events AS (
    SELECT 80 as total_target_events  -- 17 existing + 63 new
),
current_events AS (
    SELECT COUNT(DISTINCT event_type) as unique_types
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
)
SELECT
    ce.unique_types as current_event_types,
    te.total_target_events,
    ROUND(ce.unique_types * 100.0 / te.total_target_events, 2) as coverage_percent,
    CASE
        WHEN ce.unique_types >= 72 THEN '✅ EXCELLENT (90%+)'
        WHEN ce.unique_types >= 60 THEN '⚠️ GOOD (75%+)'
        ELSE '❌ INSUFFICIENT'
    END as status
FROM current_events ce, target_events te;

-- 2. Coverage by component
SELECT
    component,
    COUNT(DISTINCT event_type) as event_types,
    COUNT(*) as total_events,
    target_types,
    ROUND(COUNT(DISTINCT event_type) * 100.0 / target_types, 2) as coverage_percent
FROM (
    SELECT
        event_type,
        CASE
            WHEN event_type LIKE 'wave_%' OR event_type LIKE 'signal_%'
                THEN 'signal_processor'
            WHEN event_type LIKE 'trailing_stop_%' OR event_type LIKE 'protection_%'
                THEN 'trailing_stop'
            WHEN event_type LIKE 'phantom_%' OR event_type LIKE 'synchronization_%'
                OR event_type LIKE 'quantity_%' OR event_type LIKE 'missing_%'
                THEN 'position_synchronizer'
            WHEN event_type LIKE 'zombie_%' OR event_type LIKE 'aggressive_%'
                OR event_type LIKE 'tpsl_%'
                THEN 'zombie_manager'
            WHEN event_type LIKE 'position_%' OR event_type LIKE 'risk_%'
                OR event_type LIKE 'orphaned_%'
                THEN 'position_manager'
            WHEN event_type LIKE 'atomic_%' THEN 'atomic_position_manager'
            WHEN event_type LIKE 'stop_%' OR event_type LIKE 'emergency_stop%'
                THEN 'stop_loss_manager'
            WHEN event_type LIKE 'bot_%' OR event_type LIKE 'health_%'
                OR event_type LIKE 'recovery_%'
                THEN 'main'
            ELSE 'other'
        END as component,
        CASE
            WHEN event_type LIKE 'wave_%' OR event_type LIKE 'signal_%' THEN 25
            WHEN event_type LIKE 'trailing_stop_%' OR event_type LIKE 'protection_%' THEN 18
            WHEN event_type LIKE 'phantom_%' OR event_type LIKE 'synchronization_%' THEN 10
            WHEN event_type LIKE 'zombie_%' THEN 8
            WHEN event_type LIKE 'position_%' THEN 52
            WHEN event_type LIKE 'atomic_%' THEN 47
            WHEN event_type LIKE 'stop_%' THEN 15
            WHEN event_type LIKE 'bot_%' THEN 10
            ELSE 1
        END as target_types
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
) subquery
GROUP BY component, target_types
ORDER BY coverage_percent DESC;

-- 3. Missing event types (expected but not found)
WITH expected_types AS (
    SELECT unnest(ARRAY[
        'wave_detected', 'wave_completed', 'signal_executed',
        'trailing_stop_created', 'trailing_stop_activated',
        'phantom_position_detected', 'zombie_orders_detected',
        'position_closed', 'risk_limits_exceeded',
        -- ... list all 80 expected types
    ]) as event_type
),
actual_types AS (
    SELECT DISTINCT event_type
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
)
SELECT et.event_type as missing_event_type
FROM expected_types et
LEFT JOIN actual_types at ON et.event_type = at.event_type
WHERE at.event_type IS NULL
ORDER BY et.event_type;

-- 4. Event frequency analysis
SELECT
    event_type,
    COUNT(*) as occurrences,
    MIN(created_at) as first_occurrence,
    MAX(created_at) as last_occurrence,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(DISTINCT COALESCE(position_id::text, 'N/A')) as unique_positions
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type
ORDER BY occurrences DESC
LIMIT 50;

-- 5. Severity distribution
SELECT
    severity,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage,
    COUNT(DISTINCT event_type) as unique_event_types
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY severity
ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'ERROR' THEN 2
        WHEN 'WARNING' THEN 3
        WHEN 'INFO' THEN 4
    END;
```

**Выполнение:**
```bash
psql -h localhost -U trading_bot -d trading_bot_db \
    -f final_coverage_report.sql \
    > final_coverage_report.txt 2>&1

# Проверить результаты
cat final_coverage_report.txt
```

**Ожидаемый результат:**
```
=== OVERALL COVERAGE ===
current_event_types | total_target_events | coverage_percent | status
--------------------+---------------------+------------------+----------------------
                 75 |                  80 |            93.75 | ✅ EXCELLENT (90%+)

=== COVERAGE BY COMPONENT ===
component                | event_types | total_events | target_types | coverage_percent
-------------------------+-------------+--------------+--------------+-----------------
position_manager         |          52 |         1234 |           52 |           100.00
trailing_stop            |          18 |          456 |           18 |           100.00
signal_processor         |          25 |          789 |           25 |           100.00
position_synchronizer    |          10 |          234 |           10 |           100.00
zombie_manager           |           8 |           56 |            8 |           100.00
stop_loss_manager        |          15 |          123 |           15 |           100.00
atomic_position_manager  |          47 |         2345 |           47 |           100.00
main                     |          10 |           67 |           10 |           100.00

=== MISSING EVENT TYPES ===
(0 rows)  -- ✅ All expected types are present!
```

---

### Шаг 8.2: Performance Testing

**Тест overhead логирования:**
```python
# tests/phase8/test_logging_performance.py
"""Test performance overhead of event logging"""
import pytest
import asyncio
import time
from core.event_logger import get_event_logger, EventType


@pytest.mark.asyncio
async def test_logging_overhead_single_event(db_pool):
    """Measure overhead of logging single event"""
    event_logger = get_event_logger()

    # Warmup
    for _ in range(10):
        await event_logger.log_event(
            EventType.POSITION_UPDATED,
            {'test': 'warmup'},
            severity='INFO'
        )

    # Measure
    iterations = 1000
    start = time.perf_counter()

    for i in range(iterations):
        await event_logger.log_event(
            EventType.POSITION_UPDATED,
            {'test': 'performance', 'iteration': i},
            severity='INFO'
        )

    end = time.perf_counter()

    total_time_ms = (end - start) * 1000
    avg_time_ms = total_time_ms / iterations

    print(f"\nPerformance Results:")
    print(f"Total iterations: {iterations}")
    print(f"Total time: {total_time_ms:.2f}ms")
    print(f"Average per event: {avg_time_ms:.4f}ms")

    # Assertion: overhead should be < 5ms per event
    assert avg_time_ms < 5.0, \
        f"Logging overhead too high: {avg_time_ms:.4f}ms (max: 5ms)"


@pytest.mark.asyncio
async def test_logging_overhead_batch(db_pool):
    """Measure overhead of batch logging"""
    event_logger = get_event_logger()

    batch_size = 100
    start = time.perf_counter()

    # Log batch
    tasks = []
    for i in range(batch_size):
        task = event_logger.log_event(
            EventType.POSITION_UPDATED,
            {'test': 'batch', 'num': i},
            severity='INFO'
        )
        tasks.append(task)

    await asyncio.gather(*tasks)

    # Wait for flush
    await asyncio.sleep(6)

    end = time.perf_counter()

    total_time_ms = (end - start) * 1000
    avg_time_ms = total_time_ms / batch_size

    print(f"\nBatch Performance Results:")
    print(f"Batch size: {batch_size}")
    print(f"Total time: {total_time_ms:.2f}ms")
    print(f"Average per event: {avg_time_ms:.4f}ms")

    assert avg_time_ms < 10.0, \
        f"Batch logging overhead too high: {avg_time_ms:.4f}ms"


@pytest.mark.asyncio
async def test_event_queue_not_full(db_pool):
    """Verify event queue doesn't fill up under load"""
    event_logger = get_event_logger()

    # Rapid fire events
    for i in range(2000):  # More than queue size (1000)
        await event_logger.log_event(
            EventType.POSITION_UPDATED,
            {'test': 'queue_stress', 'num': i},
            severity='INFO'
        )

    # Wait for processing
    await asyncio.sleep(10)

    # Check queue size (should be empty or near-empty)
    queue_size = event_logger._event_queue.qsize()

    print(f"\nQueue stress test:")
    print(f"Events sent: 2000")
    print(f"Current queue size: {queue_size}")

    assert queue_size < 100, \
        f"Event queue backing up: {queue_size} items remaining"
```

**Выполнение:**
```bash
# Запустить performance tests
python -m pytest tests/phase8/test_logging_performance.py -v -s

# Ожидаемый результат:
# test_logging_overhead_single_event PASSED
#   Average per event: 0.0234ms ✅
# test_logging_overhead_batch PASSED
#   Average per event: 0.0456ms ✅
# test_event_queue_not_full PASSED
#   Queue size: 0 ✅
```

**Критерий успеха:**
- ✅ Overhead < 5ms per event
- ✅ Queue не переполняется
- ✅ Batch processing эффективен

---

### Шаг 8.3: Query Optimization

**Создать индексы для частых запросов:**
```sql
-- optimize_event_queries.sql

-- 1. Index for event_type + created_at (most common query)
CREATE INDEX IF NOT EXISTS idx_events_type_created
ON monitoring.events (event_type, created_at DESC);

-- 2. Index for symbol + created_at (symbol-specific queries)
CREATE INDEX IF NOT EXISTS idx_events_symbol_created
ON monitoring.events (symbol, created_at DESC)
WHERE symbol IS NOT NULL;

-- 3. Index for severity + created_at (error analysis)
CREATE INDEX IF NOT EXISTS idx_events_severity_created
ON monitoring.events (severity, created_at DESC);

-- 4. Index for correlation_id (related events)
CREATE INDEX IF NOT EXISTS idx_events_correlation
ON monitoring.events (correlation_id)
WHERE correlation_id IS NOT NULL;

-- 5. Composite index for position_id + event_type
CREATE INDEX IF NOT EXISTS idx_events_position_type
ON monitoring.events (position_id, event_type)
WHERE position_id IS NOT NULL;

-- 6. GIN index for event_data JSONB queries
CREATE INDEX IF NOT EXISTS idx_events_data_gin
ON monitoring.events USING GIN (event_data);

-- 7. Partial index for errors only (smaller, faster)
CREATE INDEX IF NOT EXISTS idx_events_errors_only
ON monitoring.events (event_type, created_at DESC)
WHERE severity IN ('ERROR', 'CRITICAL');

-- 8. Analyze tables for query planner
ANALYZE monitoring.events;

-- 9. Test query performance
EXPLAIN ANALYZE
SELECT * FROM monitoring.events
WHERE event_type = 'position_closed'
AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC
LIMIT 100;

-- Expected: Should use idx_events_type_created, execution time < 10ms
```

**Выполнение:**
```bash
psql -h localhost -U trading_bot -d trading_bot_db \
    -f optimize_event_queries.sql

# Проверить что индексы созданы
psql -h localhost -U trading_bot -d trading_bot_db -c "
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'events'
    ORDER BY indexname;
"
```

---

### Шаг 8.4: Integration Testing

**Полный интеграционный тест:**
```python
# tests/phase8/test_full_integration.py
"""Full integration test of event logging across all components"""
import pytest
import asyncio
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_full_position_lifecycle_logged(
    db_pool,
    mock_exchanges,
    signal_processor,
    position_manager
):
    """
    Test that a complete position lifecycle generates all expected events:
    1. Wave detected
    2. Signal executed
    3. Position created
    4. Trailing stop created
    5. Trailing stop activated
    6. Trailing stop updated
    7. Position closed
    """
    # Step 1: Send wave signal
    test_wave = {
        'timestamp': '2024-01-01T12:00:00',
        'signals': [
            {'symbol': 'BTCUSDT', 'action': 'buy', 'exchange': 'binance'}
        ]
    }

    # Process signal
    await signal_processor.process_wave(test_wave['signals'], test_wave['timestamp'])

    # Wait for all async operations
    await asyncio.sleep(10)

    # Verify all events were logged
    async with db_pool.acquire() as conn:
        events = await conn.fetch("""
            SELECT event_type, symbol, created_at
            FROM monitoring.events
            WHERE (
                symbol = 'BTCUSDT'
                OR event_type LIKE 'wave_%'
            )
            AND created_at > NOW() - INTERVAL '5 minutes'
            ORDER BY created_at
        """)

    event_types = [e['event_type'] for e in events]

    # Assert all expected events are present
    expected_events = [
        'wave_detected',
        'signal_executed',
        'position_created',
        'stop_loss_placed',
        'trailing_stop_created'
    ]

    for expected in expected_events:
        assert expected in event_types, \
            f"Expected event '{expected}' not found. Got: {event_types}"

    print(f"\n✅ Full lifecycle test passed!")
    print(f"   Events generated: {len(events)}")
    print(f"   Event types: {set(event_types)}")


@pytest.mark.asyncio
async def test_error_events_logged(db_pool, position_manager):
    """Test that error scenarios are properly logged"""
    # Trigger various errors

    # 1. Risk limits exceeded
    with pytest.raises(Exception):
        # ... trigger risk limit error
        pass

    # 2. Symbol unavailable
    with pytest.raises(Exception):
        # ... trigger symbol unavailable
        pass

    # Wait for events
    await asyncio.sleep(6)

    # Check error events
    async with db_pool.acquire() as conn:
        error_events = await conn.fetch("""
            SELECT event_type, severity
            FROM monitoring.events
            WHERE severity IN ('ERROR', 'WARNING')
            AND created_at > NOW() - INTERVAL '5 minutes'
        """)

    assert len(error_events) > 0, "No error events logged"

    event_types = [e['event_type'] for e in error_events]
    assert 'risk_limits_exceeded' in event_types

    print(f"\n✅ Error logging test passed!")
    print(f"   Error events: {len(error_events)}")


@pytest.mark.asyncio
async def test_correlation_ids_work(db_pool, signal_processor):
    """Test that correlation_id properly links related events"""
    # Process a wave
    wave_timestamp = '2024-01-01T12:00:00'
    test_signals = [
        {'symbol': 'ETHUSDT', 'action': 'buy', 'timestamp': wave_timestamp},
        {'symbol': 'BNBUSDT', 'action': 'buy', 'timestamp': wave_timestamp}
    ]

    await signal_processor.process_wave(test_signals, wave_timestamp)

    await asyncio.sleep(10)

    # Check correlation
    async with db_pool.acquire() as conn:
        correlated_events = await conn.fetch("""
            SELECT event_type, symbol, correlation_id
            FROM monitoring.events
            WHERE correlation_id = $1
            ORDER BY created_at
        """, f"wave_{wave_timestamp}")

    assert len(correlated_events) >= 3, \
        "Not enough correlated events found"

    # Verify all events have same correlation_id
    correlation_ids = set(e['correlation_id'] for e in correlated_events)
    assert len(correlation_ids) == 1, \
        f"Multiple correlation_ids found: {correlation_ids}"

    print(f"\n✅ Correlation ID test passed!")
    print(f"   Correlated events: {len(correlated_events)}")
    print(f"   Event types: {[e['event_type'] for e in correlated_events]}")
```

**Выполнение:**
```bash
python -m pytest tests/phase8/test_full_integration.py -v -s

# Ожидаемый результат:
# test_full_position_lifecycle_logged PASSED
# test_error_events_logged PASSED
# test_correlation_ids_work PASSED
```

---

### Шаг 8.5: Dashboard Query Templates

**Создать готовые SQL для dashboard:**
```sql
-- dashboard_queries.sql
-- Ready-to-use queries for monitoring dashboard

-- === QUERY 1: Real-time System Health ===
SELECT
    COUNT(*) FILTER (WHERE severity = 'CRITICAL') as critical_events,
    COUNT(*) FILTER (WHERE severity = 'ERROR') as error_events,
    COUNT(*) FILTER (WHERE severity = 'WARNING') as warning_events,
    COUNT(*) FILTER (WHERE event_type = 'position_created') as positions_opened,
    COUNT(*) FILTER (WHERE event_type = 'position_closed') as positions_closed,
    COUNT(*) FILTER (WHERE event_type = 'wave_detected') as waves_detected,
    COUNT(*) FILTER (WHERE event_type = 'zombie_orders_detected') as zombie_alerts
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '1 hour';

-- === QUERY 2: Position Performance ===
WITH closed_positions AS (
    SELECT
        (event_data->>'realized_pnl')::numeric as pnl,
        (event_data->>'realized_pnl_percent')::numeric as pnl_percent,
        event_data->>'reason' as close_reason,
        created_at
    FROM monitoring.events
    WHERE event_type = 'position_closed'
    AND created_at > NOW() - INTERVAL '24 hours'
)
SELECT
    COUNT(*) as total_closed,
    COUNT(*) FILTER (WHERE pnl > 0) as profitable,
    COUNT(*) FILTER (WHERE pnl < 0) as losing,
    ROUND(AVG(pnl), 2) as avg_pnl,
    ROUND(AVG(pnl_percent), 2) as avg_pnl_percent,
    ROUND(SUM(pnl), 2) as total_pnl,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / COUNT(*), 2) as win_rate
FROM closed_positions;

-- === QUERY 3: Wave Processing Stats ===
WITH wave_stats AS (
    SELECT
        (event_data->>'wave_timestamp')::text as wave_id,
        MAX(CASE WHEN event_type = 'wave_detected'
            THEN (event_data->>'signal_count')::int END) as signals_received,
        MAX(CASE WHEN event_type = 'wave_completed'
            THEN (event_data->>'positions_opened')::int END) as positions_opened,
        MAX(CASE WHEN event_type = 'wave_completed'
            THEN (event_data->>'failed')::int END) as failed,
        MAX(CASE WHEN event_type = 'wave_completed'
            THEN (event_data->>'duration_seconds')::numeric END) as duration_sec
    FROM monitoring.events
    WHERE event_type IN ('wave_detected', 'wave_completed')
    AND created_at > NOW() - INTERVAL '24 hours'
    GROUP BY wave_id
)
SELECT
    COUNT(*) as total_waves,
    ROUND(AVG(positions_opened), 2) as avg_positions_per_wave,
    ROUND(AVG(failed), 2) as avg_failures_per_wave,
    ROUND(AVG(duration_sec), 2) as avg_duration_sec,
    ROUND(AVG(positions_opened * 100.0 / NULLIF(signals_received, 0)), 2) as avg_success_rate
FROM wave_stats;

-- === QUERY 4: Error Breakdown ===
SELECT
    event_type,
    COUNT(*) as occurrences,
    MAX(created_at) as last_seen,
    EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 60 as minutes_ago,
    COUNT(DISTINCT symbol) as affected_symbols
FROM monitoring.events
WHERE severity IN ('ERROR', 'CRITICAL')
AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type
ORDER BY occurrences DESC
LIMIT 20;

-- === QUERY 5: Trailing Stop Effectiveness ===
WITH ts_lifecycle AS (
    SELECT
        symbol,
        MIN(CASE WHEN event_type = 'trailing_stop_created'
            THEN created_at END) as ts_created,
        MAX(CASE WHEN event_type = 'trailing_stop_activated'
            THEN created_at END) as ts_activated,
        COUNT(*) FILTER (WHERE event_type = 'trailing_stop_updated') as update_count,
        MAX(CASE WHEN event_type = 'position_closed'
            THEN (event_data->>'realized_pnl_percent')::numeric END) as final_pnl_percent
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
    AND symbol IS NOT NULL
    GROUP BY symbol
    HAVING COUNT(*) FILTER (WHERE event_type = 'trailing_stop_created') > 0
)
SELECT
    COUNT(*) as positions_with_ts,
    COUNT(*) FILTER (WHERE ts_activated IS NOT NULL) as ts_activated_count,
    ROUND(
        COUNT(*) FILTER (WHERE ts_activated IS NOT NULL) * 100.0 / COUNT(*),
        2
    ) as activation_rate,
    ROUND(AVG(update_count), 2) as avg_updates_per_position,
    ROUND(AVG(final_pnl_percent), 2) as avg_final_pnl_percent
FROM ts_lifecycle;

-- === QUERY 6: Phantom & Zombie Detection ===
SELECT
    'Phantom Positions' as issue_type,
    COUNT(*) as detected_count,
    MAX(created_at) as last_detection
FROM monitoring.events
WHERE event_type = 'phantom_position_detected'
AND created_at > NOW() - INTERVAL '24 hours'
UNION ALL
SELECT
    'Zombie Orders' as issue_type,
    SUM((event_data->>'count')::int) as detected_count,
    MAX(created_at) as last_detection
FROM monitoring.events
WHERE event_type = 'zombie_orders_detected'
AND created_at > NOW() - INTERVAL '24 hours';
```

---

### Критерии успеха Фазы 8

- ✅ Coverage ≥90% (final_coverage_report.sql shows 93%+)
- ✅ Performance overhead <5ms per event
- ✅ All indexes created and optimized
- ✅ Integration tests pass
- ✅ Dashboard queries work correctly
- ✅ No missing event types in coverage report
- ✅ Commit: "Phase 8: Complete verification and optimization"

---

<a name="rollback-strategy"></a>
## ROLLBACK STRATEGY

### Per-File Rollback

**Откат одного файла:**
```bash
# Создать patch перед изменением
git diff core/position_manager.py > position_manager_changes.patch

# Откатить при необходимости
git checkout -- core/position_manager.py

# Проверить что код работает без изменений
python -m pytest tests/ -k "not logging" -v

# Применить обратно
git apply position_manager_changes.patch
```

### Per-Phase Rollback

**Откат целой фазы:**
```bash
# Посмотреть коммиты фазы
git log --oneline | grep "Phase 1"

# Откатить фазу (например, Phase 1)
git revert <commit_hash_phase1>

# Или откатить несколько коммитов
git revert HEAD~3..HEAD  # Откатить последние 3 коммита

# Проверить что бот работает
python -m pytest tests/ -v
python main.py --testnet --dry-run
```

### Database Rollback

**Откат изменений в БД:**
```sql
-- rollback_event_types.sql
-- Удалить события новых типов (если нужен полный откат)

-- 1. Backup events перед удалением
CREATE TABLE IF NOT EXISTS monitoring.events_backup_phase_rollback AS
SELECT * FROM monitoring.events
WHERE created_at > '2024-10-14'::timestamp;  -- Дата начала внедрения

-- 2. Удалить новые события (optional, используй осторожно!)
-- DELETE FROM monitoring.events
-- WHERE event_type IN (
--     'wave_detected', 'wave_completed', 'signal_executed',
--     'trailing_stop_created', 'trailing_stop_activated',
--     -- ... all new event types
-- );

-- 3. Restore from backup if needed
-- INSERT INTO monitoring.events
-- SELECT * FROM monitoring.events_backup_phase_rollback;
```

**НЕ РЕКОМЕНДУЕТСЯ:** Удаление событий из monitoring.events приводит к потере истории. Лучше откатить код, но оставить события.

### Full Rollback

**Полный откат всех изменений:**
```bash
# Создать ветку с изменениями для сохранения
git branch backup-event-logging-implementation HEAD

# Откат к состоянию до начала внедрения
git log --oneline | grep "Phase 0"  # Найти commit ДО Phase 0
git reset --hard <commit_before_phase0>

# ИЛИ откатить на main
git checkout main
git branch -D fix/event-logging-implementation  # Удалить ветку

# Проверить что всё работает
python -m pytest tests/ -v
python main.py --testnet --dry-run

# Восстановить из backup если нужно
git checkout backup-event-logging-implementation
```

### Emergency Rollback (Production)

**Срочный откат в production:**
```bash
# 1. Остановить бота
systemctl stop trading_bot

# 2. Откатить на предыдущий рабочий коммит
git log --oneline -10
git checkout <last_working_commit>

# 3. Rebuild (если нужно)
pip install -r requirements.txt

# 4. Restart бота
systemctl start trading_bot

# 5. Мониторинг
tail -f logs/trading_bot.log
psql -c "SELECT * FROM monitoring.events ORDER BY created_at DESC LIMIT 10;"
```

### Validation After Rollback

**Проверка после отката:**
```bash
# 1. Unit tests
python -m pytest tests/ -v

# 2. Import checks
python -c "
from core.position_manager import PositionManager
from protection.trailing_stop import TrailingStop
from core.event_logger import EventType, get_event_logger
print('✅ All imports successful')
"

# 3. Database connection
psql -h localhost -U trading_bot -d trading_bot_db -c "
SELECT COUNT(*) FROM monitoring.events;
"

# 4. Bot dry-run
python main.py --testnet --dry-run

# Если всё OK:
echo "✅ Rollback completed successfully"
```

---

<a name="testing-infrastructure"></a>
## TESTING INFRASTRUCTURE

### Test Structure

```
tests/
├── phase0/
│   └── test_event_types.py
├── phase1/
│   ├── test_phantom_detection_before.py
│   ├── test_phantom_detection_after.py
│   ├── test_position_sync_logging.py
│   ├── test_risk_limits_logging.py
│   ├── test_position_closed_logging.py
│   └── ... (52 tests total)
├── phase2/
│   ├── test_trailing_stop_created.py
│   ├── test_trailing_stop_activated.py
│   ├── test_trailing_stop_updated.py
│   └── ... (18 tests total)
├── phase3/
│   ├── test_wave_lifecycle.py
│   ├── test_signal_execution.py
│   └── ... (25 tests total)
├── phase4/
│   └── ... (10 tests)
├── phase5/
│   └── ... (8 tests)
├── phase6/
│   └── ... (15 tests)
├── phase7/
│   └── ... (20 tests)
├── phase8/
│   ├── test_logging_performance.py
│   ├── test_full_integration.py
│   └── test_query_optimization.py
└── conftest.py  # Shared fixtures
```

### Shared Fixtures (conftest.py)

```python
# tests/conftest.py
import pytest
import asyncio
import asyncpg
from unittest.mock import Mock, AsyncMock


@pytest.fixture
async def db_pool():
    """Provide database connection pool for tests"""
    pool = await asyncpg.create_pool(
        host='localhost',
        port=5432,
        user='trading_bot',
        password='your_password',
        database='trading_bot_test',  # Separate test DB!
        min_size=2,
        max_size=10
    )
    yield pool
    await pool.close()


@pytest.fixture
def mock_exchange():
    """Mock exchange for testing"""
    exchange = Mock()
    exchange.name = 'binance'
    exchange.get_positions = AsyncMock(return_value=[])
    exchange.create_order = AsyncMock(return_value={
        'id': 'test_order_123',
        'status': 'filled',
        'filled': 1.0
    })
    exchange.cancel_order = AsyncMock(return_value=True)
    exchange.fetch_ticker = AsyncMock(return_value={
        'last': 50000.0,
        'bid': 49999.0,
        'ask': 50001.0
    })
    return exchange


@pytest.fixture
def mock_exchanges(mock_exchange):
    """Multiple mock exchanges"""
    return {
        'binance': mock_exchange,
        'bybit': mock_exchange  # Can customize differently if needed
    }


@pytest.fixture
async def clean_test_events(db_pool):
    """Clean up test events before and after test"""
    # Before test
    async with db_pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM monitoring.events
            WHERE created_at > NOW() - INTERVAL '1 hour'
        """)

    yield

    # After test (cleanup)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM monitoring.events
            WHERE created_at > NOW() - INTERVAL '1 hour'
        """)


@pytest.fixture
def mock_config():
    """Mock bot configuration"""
    config = Mock()
    config.max_positions = 10
    config.max_exposure_usd = 10000.0
    config.position_size_usd = 100.0
    config.stop_loss_percent = 2.0
    config.take_profit_percent = 5.0
    return config
```

### Running Tests

**По фазам:**
```bash
# Phase 0
python -m pytest tests/phase0/ -v

# Phase 1
python -m pytest tests/phase1/ -v

# All tests
python -m pytest tests/ -v

# Specific test
python -m pytest tests/phase1/test_phantom_detection_after.py::test_phantom_logged_correctly -v

# With coverage
python -m pytest tests/ --cov=core --cov=protection --cov-report=html
```

**Continuous testing during development:**
```bash
# Watch mode (requires pytest-watch)
ptw -- -v

# Parallel execution (requires pytest-xdist)
python -m pytest tests/ -n auto -v
```

---

<a name="success-criteria"></a>
## SUCCESS CRITERIA

### Overall Success Metrics

**Must have (BLOCKING):**
- ✅ Event coverage ≥90% (72+ unique event types in 24h)
- ✅ All phase tests pass (185+ tests)
- ✅ Performance overhead <5ms per event
- ✅ Zero regressions in existing functionality
- ✅ All SQL validation queries pass

**Should have (HIGH PRIORITY):**
- ✅ Event coverage 93%+ (75+ unique event types)
- ✅ Query execution time <100ms for dashboard queries
- ✅ Full integration test passes
- ✅ Documentation complete

**Nice to have (OPTIONAL):**
- ✅ Event coverage 95%+ (76+ unique event types)
- ✅ Dashboard UI deployed
- ✅ Alerting configured
- ✅ Automated reports

### Per-Phase Success Criteria

| Phase | Events | Tests | Coverage | Status |
|-------|--------|-------|----------|--------|
| 0     | 63     | 4     | Baseline | ✅ Ready |
| 1     | 52     | 52    | Position Manager | Pending |
| 2     | 18     | 18    | Trailing Stop | Pending |
| 3     | 25     | 25    | Signal Processor | Pending |
| 4     | 10     | 10    | Position Sync | Pending |
| 5     | 8      | 8     | Zombie Manager | Pending |
| 6     | 15     | 15    | Stop Loss | Pending |
| 7     | 20     | 20    | Wave & Main | Pending |
| 8     | N/A    | 10    | Verification | Pending |

### Final Validation Checklist

**Pre-Production:**
- [ ] All 8 phases completed
- [ ] 185+ tests passing
- [ ] Coverage report shows 90%+
- [ ] Performance tests pass
- [ ] Integration tests pass
- [ ] SQL validation queries all pass
- [ ] Rollback tested and working
- [ ] Documentation reviewed
- [ ] Team trained on new event types

**Production Deployment:**
- [ ] Backup current code
- [ ] Deploy to testnet first
- [ ] Monitor for 24 hours
- [ ] Check coverage metrics
- [ ] Verify query performance
- [ ] Review error events
- [ ] Deploy to production
- [ ] Monitor closely for 48 hours
- [ ] Create baseline for new monitoring

**Post-Deployment:**
- [ ] Coverage maintained at 90%+
- [ ] No performance degradation
- [ ] Dashboard queries working
- [ ] Team using event logs for debugging
- [ ] Incident analysis time reduced
- [ ] Compliance requirements met

---

## TIMELINE SUMMARY

| Day | Phase | Hours | Component | Events |
|-----|-------|-------|-----------|--------|
| 0   | 0     | 2-3   | Preparation | 63 EventTypes |
| 1-2 | 1     | 8-10  | Position Manager | 52 |
| 3   | 2     | 4-6   | Trailing Stop | 18 |
| 4   | 3     | 6-8   | Signal Processor | 25 |
| 5   | 4     | 3-4   | Position Sync | 10 |
| 6   | 5     | 2-3   | Zombie Manager | 8 |
| 7   | 6     | 3-4   | Stop Loss | 15 |
| 8   | 7     | 3-4   | Wave & Main | 20 |
| 9-10| 8     | 8-10  | Verification | - |
| **Total** | **8** | **40-52h** | **All** | **140+** |

---

## NEXT STEPS

### Immediate (День 0):
1. ✅ Прочитать весь этот план
2. ✅ Создать git branch `feature/event-logging-implementation`
3. ✅ Выполнить Phase 0: добавить EventTypes
4. ✅ Создать baseline metrics
5. ✅ Commit Phase 0

### Tomorrow (День 1):
1. Начать Phase 1: Position Manager
2. Внедрить топ-5 критичных событий
3. Написать и запустить тесты
4. Проверить SQL валидацию
5. Commit промежуточный прогресс

### This Week (Дни 1-7):
1. Завершить Phases 1-6
2. Достичь 85%+ coverage
3. Пройти все тесты
4. Подготовиться к финальной верификации

### Next Week (Дни 8-10):
1. Phase 7-8: Финализация
2. Performance testing
3. Integration testing
4. Deployment к production

---

## CONTACTS & RESOURCES

**Документы для справки:**
- `AUDIT_DATABASE_LOGGING_COMPREHENSIVE.md` - Полный список событий
- `AUDIT_SUMMARY_ACTION_PLAN.md` - Краткая сводка
- `IMPLEMENTATION_CHEATSHEET.md` - Быстрые примеры
- `NEW_EVENT_TYPES_TO_ADD.py` - Список EventTypes

**Примеры кода:**
- `core/atomic_position_manager.py` - Reference implementation (100% coverage)
- `main.py` - Примеры BOT_STARTED, BOT_STOPPED

**SQL Scripts:**
- `baseline_metrics.sql` - Baseline
- `monitoring_queries.sql` - Прогресс
- `final_coverage_report.sql` - Финальная проверка
- `dashboard_queries.sql` - Dashboard

---

## WARNINGS & CRITICAL NOTES

**⚠️ КРИТИЧНО:**
1. **НЕ КОММИТИТЬ** без тестов - каждое изменение должно иметь тест
2. **НЕ БЛОКИРОВАТЬ** основной flow - всегда `if event_logger:`
3. **ASYNC ВЕЗДЕ** - все вызовы `log_event()` должны быть `await`
4. **СТРУКТУРИРОВАННЫЕ ДАННЫЕ** - использовать dict, не строки
5. **ROLLBACK ГОТОВ** - перед каждым шагом создавать patch

**⚠️ ОСТОРОЖНО:**
1. Float conversion - всегда `float(Decimal_value)`
2. DateTime serialization - использовать `.isoformat()`
3. JSON serialization - проверять что все поля serializable
4. Severity правильно - INFO/WARNING/ERROR/CRITICAL
5. Correlation ID - использовать для связанных событий

**⚠️ ТЕСТИРОВАНИЕ:**
1. Всегда запускать testnet перед production
2. Мониторить performance при нагрузке
3. Проверять что event queue не переполняется
4. Верифицировать что rollback работает

---

## CHANGELOG

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-14 | 1.0 | Initial comprehensive plan created |
| TBD | 1.1 | After Phase 0 completion |
| TBD | 2.0 | After all phases completion |

---

**СТАТУС ПЛАНА:** ✅ ГОТОВ К ВЫПОЛНЕНИЮ
**ПОСЛЕДНЕЕ ОБНОВЛЕНИЕ:** 2025-10-14
**АВТОР:** Claude Code Analysis System

---

**НАЧАТЬ С:**
```bash
# 1. Создать branch
git checkout -b feature/event-logging-implementation

# 2. Открыть event_logger.py
vi core/event_logger.py

# 3. Добавить 63 новых EventType
# (см. Phase 0, Step 0.1)

# 4. Запустить тест
python -m pytest tests/test_phase0_event_types.py -v

# 5. Создать baseline
psql -f baseline_metrics.sql > baseline_metrics.txt

# 6. Commit
git add core/event_logger.py tests/test_phase0_event_types.py baseline_metrics.txt
git commit -m "Phase 0: Add 63 new EventTypes and baseline metrics"

# ГОТОВО! Переходить к Phase 1.
```

**УДАЧИ! 🚀**
