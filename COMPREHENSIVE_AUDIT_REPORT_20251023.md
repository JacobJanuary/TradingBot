# 🔍 КОМПЛЕКСНЫЙ КРИТИЧЕСКИЙ АУДИТ СИСТЕМЫ
## Дата: 2025-10-23 21:30
## Статус: РАССЛЕДОВАНИЕ ЗАВЕРШЕНО

---

# 📊 EXECUTIVE SUMMARY

## Найденные критические проблемы

| № | Проблема | Файл | Строки | Severity | Status |
|---|----------|------|--------|----------|--------|
| 1 | Duplicate method `create_aged_monitoring_event` | database/repository.py | 1211, 1267 | 🔴 CRITICAL | NEW |
| 2 | Missing method `log_aged_monitoring_event` | database/repository.py | 1285 | 🔴 CRITICAL | NEW |
| 3 | String 'pending' passed to INTEGER column | aged_position_monitor_v2.py | 167 | 🔴 CRITICAL | NEW |
| 4 | String 'pending' passed to INTEGER in events | position_manager.py | Multiple | 🔴 CRITICAL | NEW |
| 5 | Missing table `monitoring.orders_cache` | database | N/A | 🔴 CRITICAL | NEW |
| 6 | SHORT SL validation | protection/trailing_stop.py | 595-610 | ✅ FIXED | DEPLOYED |

---

# 🔥 PROBLEM 1: Duplicate create_aged_monitoring_event Method

## Локация
- **Файл:** `database/repository.py`
- **Строки:** 1211-1265 (первая версия), 1267-1295 (вторая версия)

## Описание
Метод `create_aged_monitoring_event` определен ДВАЖДЫ с разными сигнатурами:

### Первая версия (строка 1211):
```python
async def create_aged_monitoring_event(
    self,
    aged_position_id: str,
    event_type: str,
    market_price: Decimal = None,
    target_price: Decimal = None,
    price_distance_percent: Decimal = None,
    action_taken: str = None,
    success: bool = None,
    error_message: str = None,
    event_metadata: Dict = None
) -> bool:
    """Log aged position monitoring event"""
    query = """
        INSERT INTO aged_monitoring_events (
            aged_position_id, event_type, market_price,
            target_price, price_distance_percent,
            action_taken, success, error_message,
            event_metadata, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
    """
    # ... implementation
```

### Вторая версия (строка 1267) - ДУБЛИКАТ:
```python
async def create_aged_monitoring_event(
    self,
    aged_position_id: str,
    event_type: str,
    event_metadata: Dict = None,
    **kwargs
) -> bool:
    """Simplified method for order_executor"""
    return await self.log_aged_monitoring_event(  # ← ОШИБКА!
        aged_position_id=aged_position_id,
        event_type=event_type,
        market_price=None,
        target_price=None,
        price_distance_percent=None,
        action_taken=event_metadata.get('order_type') if event_metadata else None,
        success=True,
        error_message=None,
        event_metadata=event_metadata
    )
```

## Корневая причина
Вторая версия была добавлена как wrapper для `order_executor.py`, но:
1. **Python использует только последнее определение** - первая версия переопределяется
2. Вторая версия вызывает **несуществующий метод** `log_aged_monitoring_event`
3. Это вызывает AttributeError при каждом вызове из aged_position_monitor_v2

## Ошибки в логах
```
2025-10-23 21:22:46,773 - core.aged_position_monitor_v2 - ERROR - Failed to log monitoring event: 'Repository' object has no attribute 'log_aged_monitoring_event'
```
**Частота:** Постоянно (каждые 10-30 секунд)

## Воздействие
- ❌ Aged position monitoring события НЕ логируются в БД
- ❌ Order execution события НЕ логируются
- ❌ Потеря телеметрии и мониторинга
- ❌ Невозможно отследить aged positions в БД

---

# 🔥 PROBLEM 2: String 'pending' as INTEGER - Aged Positions

## Локация
- **Файл:** `core/aged_position_monitor_v2.py`
- **Строка:** 167
- **Метод:** `add_aged_position()`

## Описание

### Код с ошибкой:
```python
150:  target = AgedPositionTarget(
151:      symbol=symbol,
152:      entry_price=Decimal(str(position.entry_price)),
153:      target_price=target_price,
154:      phase=phase,
155:      loss_tolerance=loss_tolerance,
156:      hours_aged=age_hours,
157:      position_id=getattr(position, 'id', symbol)  # ⚠️ Can be 'pending'
158:  )
...
164:  if self.repository:
165:      try:
166:          await self.repository.create_aged_position(
167:              position_id=target.position_id,  # ⚠️ Passing 'pending' string!
168:              symbol=symbol,
169:              exchange=position.exchange,
170:              entry_price=target.entry_price,
171:              target_price=target_price,
172:              phase=phase,
173:              loss_tolerance=loss_tolerance,
174:              age_hours=age_hours
175:          )
```

### База данных ожидает:
```sql
-- migration 009, line 15
position_id BIGINT NOT NULL REFERENCES monitoring.positions(id) ON DELETE CASCADE
```

### Что передается:
- **Ожидается:** `BIGINT` (integer)
- **Фактически:** String `'pending'` (из pre_register_position)

## Источник проблемы

**Файл:** `core/position_manager.py`, строки 1485-1500

```python
async def pre_register_position(self, symbol: str, exchange: str):
    """Pre-register position for WebSocket updates before it's fully created"""
    if symbol not in self.positions:
        # Create temporary placeholder
        self.positions[symbol] = PositionState(
            id="pending",  # ⚠️ STRING instead of integer
            symbol=symbol,
            exchange=exchange,
            side="pending",
            quantity=0,
            entry_price=0,
            ...
```

## Сценарий возникновения

1. `atomic_position_manager.py` открывает позицию (line 255)
2. Вызывается `pre_register_position(symbol, exchange)`
3. Создается `PositionState` с `id="pending"`
4. **Aged position monitor** обнаруживает позицию (возраст > 3 часа)
5. Пытается записать в БД с `position_id="pending"`
6. PostgreSQL отклоняет: `invalid input syntax for type bigint: "pending"`

## Ошибки в логах
```
2025-10-23 21:20:17,147 - core.position_manager - ERROR - Error syncing bybit positions: invalid input for query argument $5: 'pending' ('str' object cannot be interpreted as an integer)
```

## Воздействие
- ❌ Aged positions НЕ создаются в БД
- ❌ Нет отслеживания старых позиций
- ❌ Потеря критической телеметрии

---

# 🔥 PROBLEM 3: String 'pending' as INTEGER - Event Logger

## Локация
- **Файл:** `core/event_logger.py`
- **Строка:** 373 (`_write_batch`)
- **Таблица:** `monitoring.events`

## Описание

### SQL Query:
```sql
INSERT INTO monitoring.events (
    event_type, event_data, correlation_id,
    position_id, order_id, symbol, exchange,        -- $4 = position_id
    severity, error_message, stack_trace, created_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
```

### База данных ожидает:
```sql
-- migration 004, line 43
position_id INTEGER,  -- Soft FK to monitoring.positions.id
```

### Что передается:
- **$4 parameter:** `position_id`
- **Ожидается:** `INTEGER` или `NULL`
- **Фактически:** String `'pending'` из pre-registered positions

## Источник проблемы

**Файл:** `core/position_manager.py`

### 40 мест вызова event_logger.log_event()

Критические вызовы в методе `_on_position_update()` (обрабатывает WebSocket):

**Line 1962-1975:** TRAILING_STOP_ACTIVATED
```python
await event_logger.log_event(
    EventType.TRAILING_STOP_ACTIVATED,
    {..., 'position_id': position.id, ...},
    position_id=position.id,  # ⚠️ Can be "pending"
```

**Line 1986-1998:** DATABASE_ERROR
**Line 2010-2023:** TRAILING_STOP_UPDATED
**Line 2037-2050:** DATABASE_ERROR
**Line 2066-2081:** POSITION_UPDATED
**Line 2089-2102:** DATABASE_ERROR
**Line 2146-2158:** ORDER_FILLED (в `_on_order_filled`)

## Traceback из логов
```python
Traceback (most recent call last):
  File "/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/event_logger.py", line 373, in _write_batch
    await conn.executemany(
  ...
asyncpg.exceptions.DataError: invalid input for query argument $4 in element #20 of executemany() sequence: 'pending' ('str' object cannot be interpreted as an integer)
```

## Сценарий возникновения

1. Position pre-registered with `id="pending"`
2. WebSocket update arrives → `_on_position_update()` called
3. Tries to log event with `position_id="pending"`
4. Event added to batch queue
5. Batch write fails on executemany()
6. **Все события в батче теряются!**

## Воздействие
- ❌ События НЕ логируются в БД
- ❌ Потеря всего батча (до 100 событий!)
- ❌ Нет телеметрии trailing stop
- ❌ Нет аудита изменений позиций

---

# 🔥 PROBLEM 4: Missing table monitoring.orders_cache

## Локация
- **База данных:** `fox_crypto`
- **Ожидаемая таблица:** `monitoring.orders_cache`
- **Статус:** НЕ СУЩЕСТВУЕТ

## Описание

### Код использует таблицу:

**Файл:** `database/repository.py`

**Line 754:** INSERT
```python
query = """
    INSERT INTO monitoring.orders_cache
    (exchange, exchange_order_id, symbol, order_type, side, price, amount, filled, status, created_at, order_data)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    ON CONFLICT (exchange, exchange_order_id) DO UPDATE
    SET status = $9, filled = $8, ...
"""
```

**Line 800:** SELECT (get_cached_order)
```python
query = """
    SELECT order_data
    FROM monitoring.orders_cache
    WHERE exchange = $1 AND exchange_order_id = $2
"""
```

**Line 836:** SELECT (get_recent_orders)
```python
query = """
    SELECT order_data
    FROM monitoring.orders_cache
    WHERE exchange = $1 AND symbol = $2
    ORDER BY created_at DESC
    LIMIT $3
"""
```

### Таблица должна быть создана:

**Файл:** `database/create_orders_cache_table.py` (НЕ ВЫПОЛНЕН!)

```python
await conn.execute("""
    CREATE TABLE IF NOT EXISTS monitoring.orders_cache (
        id SERIAL PRIMARY KEY,
        exchange VARCHAR(50) NOT NULL,
        exchange_order_id VARCHAR(100) NOT NULL,
        symbol VARCHAR(50) NOT NULL,
        order_type VARCHAR(20) NOT NULL,
        side VARCHAR(10) NOT NULL,
        price DECIMAL(20, 8),
        amount DECIMAL(20, 8) NOT NULL,
        filled DECIMAL(20, 8) DEFAULT 0,
        status VARCHAR(20) NOT NULL,
        created_at TIMESTAMP NOT NULL,
        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        order_data JSONB,

        CONSTRAINT unique_exchange_order UNIQUE (exchange, exchange_order_id)
    );
""")
```

## Назначение таблицы

Решает проблему лимита 500 ордеров Bybit:
1. Кэширует все ордера локально
2. Позволяет получить информацию об ордере без API вызова
3. Обходит ограничение "500 orders limit" от Bybit
4. Хранит исторические данные для анализа

## Ошибки в логах
```
2025-10-23 21:20:11,963 - database.repository - ERROR - Failed to retrieve cached order c962ce52-cb8c-4d6f-a70f-72ef68336b37: relation "monitoring.orders_cache" does not exist
```

## Воздействие
- ❌ Невозможно кэшировать ордера
- ❌ Проблема с Bybit 500 orders limit остается
- ❌ Нет истории ордеров для анализа
- ❌ Дополнительные API вызовы

---

# ✅ PROBLEM 5: SHORT SL Validation (FIXED)

## Статус: ИСПРАВЛЕНО (commit 56e2ad0)

### Что было исправлено:

**Файл:** `protection/trailing_stop.py`, строки 595-610

```python
else:  # SHORT позиция
    # For short: trail above lowest price
    potential_stop = ts.lowest_price * (1 + distance / 100)

    # CRITICAL FIX: Only update SL when price is falling or at minimum
    price_at_or_below_minimum = ts.current_price <= ts.lowest_price

    if price_at_or_below_minimum:
        # Price is at minimum or making new low - can update SL
        if potential_stop < ts.current_stop_price:
            new_stop_price = potential_stop
            logger.debug(f"SHORT {ts.symbol}: updating SL on new low")
    else:
        # Price is above minimum - SL should stay in place
        logger.debug(f"SHORT {ts.symbol}: keeping SL")
```

**Файл:** `core/exchange_manager.py`, строки 793-810

```python
# ЗАЩИТНАЯ ВАЛИДАЦИЯ
# Validate SL for SHORT positions before sending to exchange
if position_side in ['short', 'sell']:
    try:
        ticker = await self.exchange.fetch_ticker(symbol)
        current_market_price = float(ticker['last'])

        if new_sl_price <= current_market_price:
            logger.warning(
                f"⚠️ SHORT {symbol}: Attempted SL {new_sl_price:.8f} <= market {current_market_price:.8f}, "
                f"skipping to avoid exchange rejection"
            )
            result['success'] = False
            result['error'] = f"Invalid SL for SHORT: {new_sl_price:.8f} must be > {current_market_price:.8f}"
            return result
    except Exception as e:
        logger.error(f"Failed to validate SHORT SL: {e}")
```

### Результат
- ✅ Нет ошибок SHORT SL после 21:00
- ✅ Логи чистые от Bybit rejections
- ✅ Trailing stop для SHORT работает корректно

---

# 📋 DETAILED FIX PLAN

## ФАЗА 1: Исправление repository.py

### Шаг 1.1: Удалить дубликат метода create_aged_monitoring_event

**Файл:** `database/repository.py`
**Действие:** Удалить строки 1267-1295 (второй дубликат)

**Обоснование:** Python использует только последнее определение метода. Вторая версия переопределяет первую и вызывает несуществующий метод.

### Шаг 1.2: Переименовать первый метод (опционально)

Если нужна упрощенная версия для order_executor, создать отдельный метод:

```python
async def create_aged_monitoring_event(
    self,
    aged_position_id: str,
    event_type: str,
    market_price: Decimal = None,
    target_price: Decimal = None,
    price_distance_percent: Decimal = None,
    action_taken: str = None,
    success: bool = None,
    error_message: str = None,
    event_metadata: Dict = None
) -> bool:
    """Log aged position monitoring event (MAIN METHOD)"""
    query = """
        INSERT INTO aged_monitoring_events (
            aged_position_id, event_type, market_price,
            target_price, price_distance_percent,
            action_taken, success, error_message,
            event_metadata, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
    """

    async with self.pool.acquire() as conn:
        try:
            await conn.execute(
                query,
                aged_position_id,
                event_type,
                market_price,
                target_price,
                price_distance_percent,
                action_taken,
                success,
                error_message,
                json.dumps(event_metadata) if event_metadata else None
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create monitoring event: {e}")
            return False

async def log_order_execution(
    self,
    aged_position_id: str,
    event_type: str,
    event_metadata: Dict = None
) -> bool:
    """Simplified wrapper for order_executor"""
    return await self.create_aged_monitoring_event(
        aged_position_id=aged_position_id,
        event_type=event_type,
        market_price=None,
        target_price=None,
        price_distance_percent=None,
        action_taken=event_metadata.get('order_type') if event_metadata else None,
        success=True,
        error_message=None,
        event_metadata=event_metadata
    )
```

---

## ФАЗА 2: Исправление 'pending' в aged_position_monitor_v2.py

### Шаг 2.1: Добавить валидацию position_id

**Файл:** `core/aged_position_monitor_v2.py`
**Метод:** `add_aged_position()`
**Строка:** 164-175

**ВАРИАНТ A: Пропускать pre-registered positions**

```python
# Database tracking - create aged position entry
if self.repository:
    # Skip if position is not yet in database (pre-registered)
    if target.position_id == 'pending' or not isinstance(target.position_id, int):
        logger.debug(f"Skipping DB tracking for pre-registered position {symbol}")
        return

    try:
        await self.repository.create_aged_position(
            position_id=target.position_id,
            symbol=symbol,
            exchange=position.exchange,
            entry_price=target.entry_price,
            target_price=target_price,
            phase=phase,
            loss_tolerance=loss_tolerance,
            age_hours=age_hours
        )
```

**ВАРИАНТ B: Использовать None для pending**

```python
target = AgedPositionTarget(
    symbol=symbol,
    entry_price=Decimal(str(position.entry_price)),
    target_price=target_price,
    phase=phase,
    loss_tolerance=loss_tolerance,
    hours_aged=age_hours,
    position_id=getattr(position, 'id', None) if hasattr(position, 'id') and position.id != 'pending' else None
)
```

---

## ФАЗА 3: Исправление 'pending' в position_manager.py

### Шаг 3.1: Валидация перед event_logger.log_event()

**Файл:** `core/position_manager.py`
**Метод:** `_on_position_update()` и другие

**Добавить в начало метода:**

```python
async def _on_position_update(self, symbol: str, update_data: dict):
    """WebSocket position update handler"""

    # Skip if position not registered
    if symbol not in self.positions:
        return

    position = self.positions[symbol]

    # ⚠️ CRITICAL: Skip operations on pre-registered positions
    if position.id == "pending":
        logger.debug(f"{symbol}: Skipping update for pending position (waiting for DB ID)")
        return

    # Rest of the method...
```

### Шаг 3.2: Валидация перед database updates

**Все вызовы repository.update_position():**

```python
# Before any database update
if isinstance(position.id, int):
    await self.repository.update_position(position.id, ...)
else:
    logger.warning(f"{symbol}: Skipping DB update - position.id is {position.id}")
```

### Шаг 3.3: Валидация перед event logging

**Все вызовы event_logger.log_event():**

```python
# Only log events for real positions
if isinstance(position.id, int):
    await event_logger.log_event(
        EventType.POSITION_UPDATED,
        {...},
        position_id=position.id
    )
```

---

## ФАЗА 4: Создание таблицы monitoring.orders_cache

### Шаг 4.1: Создать миграцию

**Файл:** `database/migrations/010_create_orders_cache.sql`

```sql
-- Migration: Create orders cache table
-- Date: 2025-10-23
-- Purpose: Solve Bybit 500 orders limit issue

CREATE TABLE IF NOT EXISTS monitoring.orders_cache (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    exchange_order_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price DECIMAL(20, 8),
    amount DECIMAL(20, 8) NOT NULL,
    filled DECIMAL(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_data JSONB,

    CONSTRAINT unique_exchange_order UNIQUE (exchange, exchange_order_id)
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_orders_cache_exchange_symbol
ON monitoring.orders_cache(exchange, symbol);

CREATE INDEX IF NOT EXISTS idx_orders_cache_created_at
ON monitoring.orders_cache(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_cache_order_id
ON monitoring.orders_cache(exchange_order_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON monitoring.orders_cache TO evgeniyyanvarskiy;
GRANT USAGE, SELECT ON SEQUENCE monitoring.orders_cache_id_seq TO evgeniyyanvarskiy;
```

### Шаг 4.2: Применить миграцию

```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto < database/migrations/010_create_orders_cache.sql
```

---

## ФАЗА 5: Тестирование

### Тест 1: Repository методы
```python
# tests/test_repository_aged_events.py
import pytest
from database.repository import Repository

async def test_create_aged_monitoring_event():
    """Test that aged monitoring events can be created"""
    repo = Repository(db_config)
    await repo.connect()

    result = await repo.create_aged_monitoring_event(
        aged_position_id="TEST_001",
        event_type="price_check",
        market_price=Decimal("100.50"),
        target_price=Decimal("105.00"),
        price_distance_percent=Decimal("4.5"),
        action_taken="check_distance",
        success=True,
        error_message=None,
        event_metadata={"test": True}
    )

    assert result == True

async def test_no_duplicate_method():
    """Verify only one create_aged_monitoring_event exists"""
    repo = Repository(db_config)

    # Check method exists
    assert hasattr(repo, 'create_aged_monitoring_event')

    # Check log_aged_monitoring_event does NOT exist
    assert not hasattr(repo, 'log_aged_monitoring_event')
```

### Тест 2: Position ID validation
```python
# tests/test_pending_position_handling.py
async def test_aged_monitor_skips_pending():
    """Test that aged monitor skips pre-registered positions"""

    # Create pre-registered position
    position = PositionState(
        id="pending",
        symbol="TESTUSDT",
        exchange="bybit"
    )

    # Try to add to aged monitor
    await aged_monitor.add_aged_position(position, ...)

    # Verify no database insert attempted
    assert not db_mock.create_aged_position.called

async def test_event_logger_with_pending():
    """Test that event logger handles pending positions"""

    position = PositionState(id="pending", symbol="TEST")

    # Should not raise exception
    await event_logger.log_event(
        EventType.POSITION_UPDATED,
        {"test": True},
        position_id=position.id
    )

    # Event should not be in batch
    assert len(event_logger.batch) == 0
```

### Тест 3: Orders cache
```bash
# Verify table exists
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "\d monitoring.orders_cache"

# Test insert
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "
INSERT INTO monitoring.orders_cache (exchange, exchange_order_id, symbol, order_type, side, amount, status, created_at)
VALUES ('bybit', 'TEST_001', 'BTCUSDT', 'market', 'buy', 0.001, 'filled', NOW());
"
```

---

## ФАЗА 6: Deployment Plan

### Pre-deployment Checklist
- [ ] Создать бэкапы всех модифицируемых файлов
- [ ] Создать SQL миграцию 010_create_orders_cache.sql
- [ ] Проверить синтаксис всех изменений
- [ ] Запустить unit тесты локально

### Deployment Steps

1. **Применить database миграцию:**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto < database/migrations/010_create_orders_cache.sql
```

2. **Обновить код:**
```bash
git add database/repository.py core/aged_position_monitor_v2.py core/position_manager.py
git commit -m "fix: resolve 'pending' position ID and duplicate method issues

- Remove duplicate create_aged_monitoring_event method
- Add validation for pending positions in aged_monitor
- Add validation for pending positions in event_logger
- Skip database operations on pre-registered positions

Fixes:
- 'Repository' object has no attribute 'log_aged_monitoring_event'
- invalid input for query argument: 'pending' (str vs integer)
"
```

3. **Перезапустить бота:**
```bash
# Stop bot
pkill -f main.py

# Start bot
nohup python main.py > logs/bot_restart_$(date +%Y%m%d_%H%M).log 2>&1 &
```

4. **Мониторинг логов:**
```bash
# Watch for errors
tail -f logs/trading_bot.log | grep -E "ERROR|CRITICAL"

# Should NOT see:
# - 'log_aged_monitoring_event'
# - 'pending' ('str' object cannot be interpreted as an integer)
# - relation "monitoring.orders_cache" does not exist
```

---

## ФАЗА 7: Verification

### Success Criteria

✅ **Repository методы:**
```bash
# No AttributeError in logs
grep "log_aged_monitoring_event" logs/trading_bot.log
# Should return EMPTY
```

✅ **Pending position handling:**
```bash
# No type conversion errors
grep "'pending' ('str' object cannot be interpreted as an integer)" logs/trading_bot.log
# Should return EMPTY
```

✅ **Orders cache:**
```bash
# No missing table errors
grep "relation \"monitoring.orders_cache\" does not exist" logs/trading_bot.log
# Should return EMPTY
```

✅ **Aged monitoring working:**
```bash
# Check database for aged events
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT COUNT(*) FROM aged_monitoring_events WHERE created_at > NOW() - INTERVAL '1 hour';
"
# Should show events
```

---

## 📊 SUMMARY TABLE

| Issue | File | Fix Type | Priority | Complexity |
|-------|------|----------|----------|------------|
| Duplicate method | repository.py | Delete lines | P0 | Low |
| 'pending' in aged_monitor | aged_position_monitor_v2.py | Add validation | P0 | Low |
| 'pending' in position_manager | position_manager.py | Add validation | P0 | Medium |
| 'pending' in event_logger | (implicit) | Via position_manager fix | P0 | Low |
| Missing orders_cache table | database | Create migration | P1 | Low |

---

**Дата создания:** 2025-10-23 21:30
**Автор:** AI Assistant (Claude Code)
**Статус:** READY FOR IMPLEMENTATION
**Версия:** 1.0 COMPREHENSIVE
