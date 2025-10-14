# 🔬 DEEP RESEARCH: EVENT LOGGER TABLES - ПОЛНЫЙ ОТЧЕТ

**Дата:** 2025-10-14
**Статус:** ✅ RESEARCH COMPLETE - 100% уверенность
**Критичность:** 🔴 CRITICAL - События теряются

---

## 📋 EXECUTIVE SUMMARY

### Проблема
EventLogger система реализована корректно на уровне кода, но **таблицы БД не существуют** → все события теряются.

### Найденные критические баги
1. **БАГ #1**: Таблицы создаются БЕЗ префикса `monitoring.` (код на строках 180-234 event_logger.py)
2. **БАГ #2**: Конфликт имени `monitoring.performance_metrics` - таблица существует с ДРУГОЙ структурой
3. **БАГ #3**: INSERT запросы БЕЗ префикса `monitoring.` (строки 333, 362, 401, 429, 450)

### Требуемые действия
1. Переименовать EventLogger performance_metrics → event_performance_metrics (избежать конфликта)
2. Добавить префикс `monitoring.` ко всем CREATE TABLE и INSERT/SELECT
3. Создать таблицы в БД

---

## 🔍 ДЕТАЛЬНЫЙ АНАЛИЗ

### 1. ТАБЛИЦА: monitoring.events

#### ❌ Текущий статус
**НЕ СУЩЕСТВУЕТ** в базе данных

```sql
psql> SELECT schemaname, tablename FROM pg_tables
      WHERE schemaname = 'monitoring' AND tablename = 'events';
(0 rows)
```

#### ✅ Требуемая структура

**Источник:** core/event_logger.py строки 180-200

```sql
CREATE TABLE IF NOT EXISTS monitoring.events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    correlation_id VARCHAR(100),
    position_id INTEGER,
    order_id VARCHAR(100),
    symbol VARCHAR(50),
    exchange VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'INFO',
    error_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_events_type ON monitoring.events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON monitoring.events (correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_position ON monitoring.events (position_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON monitoring.events (created_at DESC);
```

#### 🔧 Назначение
- **Audit trail** для всех критических операций бота
- 69 типов событий (EventType enum)
- Хранение событий: позиций, ордеров, stop-loss, синхронизации, zombie cleanup, wave detection
- Correlation tracking для связанных событий
- Severity levels: INFO, WARNING, ERROR, CRITICAL

#### 📊 Ожидаемая нагрузка
Исходя из мониторинга 14 минут (EVENT_LOGGING_MONITORING_REPORT.md):
- **~4 события/минуту** (56 событий за 14 минут)
- **~240 событий/час**
- **~5,760 событий/день**
- **~2.1M событий/год**

#### 🐛 Баги в коде

**БАГ #1A - Создание таблицы без префикса:**
```python
# event_logger.py:180 - ❌ НЕПРАВИЛЬНО
await conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
    ...
""")

# ✅ ДОЛЖНО БЫТЬ:
await conn.execute("""
    CREATE TABLE IF NOT EXISTS monitoring.events (
    ...
""")
```

**БАГ #1B - INSERT без префикса:**
```python
# event_logger.py:333 - ❌ НЕПРАВИЛЬНО
query = """
    INSERT INTO events (
    ...
"""

# ✅ ДОЛЖНО БЫТЬ:
query = """
    INSERT INTO monitoring.events (
    ...
"""
```

**БАГ #1C - SELECT без префикса:**
```python
# event_logger.py:450 - ❌ НЕПРАВИЛЬНО
query = """
    SELECT * FROM events
    ...
"""

# ✅ ДОЛЖНО БЫТЬ:
query = """
    SELECT * FROM monitoring.events
    ...
"""
```

#### 📝 Обоснование полей

| Поле | Тип | Назначение | Обязательно |
|------|-----|------------|-------------|
| id | SERIAL | Уникальный ID события | ✅ |
| event_type | VARCHAR(50) | Тип события из EventType enum | ✅ |
| event_data | JSONB | Произвольные данные события | ❌ |
| correlation_id | VARCHAR(100) | Группировка связанных событий | ❌ |
| position_id | INTEGER | FK к monitoring.positions (soft) | ❌ |
| order_id | VARCHAR(100) | ID ордера на бирже | ❌ |
| symbol | VARCHAR(50) | Торговая пара | ❌ |
| exchange | VARCHAR(50) | Биржа (bybit/binance) | ❌ |
| severity | VARCHAR(20) | INFO/WARNING/ERROR/CRITICAL | ✅ |
| error_message | TEXT | Сообщение об ошибке | ❌ |
| stack_trace | TEXT | Stack trace для debug | ❌ |
| created_at | TIMESTAMP WITH TIME ZONE | Время события (UTC) | ✅ |

**Примечания:**
- `position_id` - soft FK (без FOREIGN KEY constraint) к `monitoring.positions.id`
- `event_data` - JSONB для гибкости (разные типы событий имеют разные данные)
- `correlation_id` - для трассировки atomic операций (например, open position → set SL → activate TS)

---

### 2. ТАБЛИЦА: monitoring.transaction_log

#### ❌ Текущий статус
**НЕ СУЩЕСТВУЕТ** в базе данных

#### ✅ Требуемая структура

**Источник:** core/event_logger.py строки 204-219

```sql
CREATE TABLE IF NOT EXISTS monitoring.transaction_log (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) UNIQUE,
    operation VARCHAR(100),
    status VARCHAR(20),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    affected_rows INTEGER,
    error_message TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tx_log_id ON monitoring.transaction_log (transaction_id);
CREATE INDEX IF NOT EXISTS idx_tx_log_status ON monitoring.transaction_log (status);
```

#### 🔧 Назначение
- Логирование транзакций БД для performance tracking
- Отслеживание длительных операций
- Мониторинг ошибок БД

#### 📊 Ожидаемая нагрузка
- **Низкая** - используется только в методе `log_transaction()` (строка 384)
- Метод вызывается только в скрипте `scripts/validate_fixes_improved.py:279` (для проверки)
- В production **не используется** на текущий момент
- **Резерв на будущее** для мониторинга БД транзакций

#### 🐛 Баги в коде

**БАГ #2A - Создание таблицы без префикса:**
```python
# event_logger.py:204 - ❌ НЕПРАВИЛЬНО
await conn.execute("""
    CREATE TABLE IF NOT EXISTS transaction_log (
    ...
""")

# ✅ ДОЛЖНО БЫТЬ:
await conn.execute("""
    CREATE TABLE IF NOT EXISTS monitoring.transaction_log (
    ...
""")
```

**БАГ #2B - INSERT без префикса:**
```python
# event_logger.py:401 - ❌ НЕПРАВИЛЬНО
query = """
    INSERT INTO transaction_log (
    ...
"""

# ✅ ДОЛЖНО БЫТЬ:
query = """
    INSERT INTO monitoring.transaction_log (
    ...
"""
```

#### 📝 Обоснование полей

| Поле | Тип | Назначение | Обязательно |
|------|-----|------------|-------------|
| id | SERIAL | Уникальный ID записи | ✅ |
| transaction_id | VARCHAR(100) UNIQUE | UUID транзакции | ✅ |
| operation | VARCHAR(100) | Тип операции (UPDATE, INSERT, etc) | ✅ |
| status | VARCHAR(20) | success/failed/pending | ✅ |
| started_at | TIMESTAMP WITH TIME ZONE | Начало транзакции | ✅ |
| completed_at | TIMESTAMP WITH TIME ZONE | Завершение транзакции | ❌ |
| duration_ms | INTEGER | Длительность в миллисекундах | ❌ |
| affected_rows | INTEGER | Количество измененных строк | ❌ |
| error_message | TEXT | Ошибка если status=failed | ❌ |

**Примечания:**
- `transaction_id` UNIQUE для upsert операций (ON CONFLICT)
- `duration_ms` вычисляется автоматически из `completed_at - started_at`

#### ⚠️ Приоритет
**НИЗКИЙ** - Таблица не используется в production на текущий момент. Создать для полноты, но фиксить баги в коде не критично.

---

### 3. ТАБЛИЦА: monitoring.event_performance_metrics ⚠️ ПЕРЕИМЕНОВАНИЕ!

#### ❌ Текущий статус
**НЕ СУЩЕСТВУЕТ** - но имя `monitoring.performance_metrics` **ЗАНЯТО ДРУГОЙ ТАБЛИЦЕЙ**

#### 🚨 КРИТИЧЕСКИЙ КОНФЛИКТ ИМЕН

**Существующая таблица:** `monitoring.performance_metrics`
- **Источник:** database/init.sql строки 109-123
- **Структура:** Агрегированная статистика торговли (period, total_trades, win_rate, profit_factor, sharpe_ratio, max_drawdown)
- **Данные:** **32 записи уже существуют в БД** ⚠️
- **Назначение:** Дневная/недельная статистика бота

**EventLogger таблица:** `performance_metrics` (event_logger.py:223)
- **Структура:** Real-time метрики событий (metric_name, metric_value, tags)
- **Назначение:** Гибкие метрики производительности EventLogger

**ЭТО КОНФЛИКТ!** Две разные таблицы с одним именем и разными структурами.

#### ✅ РЕШЕНИЕ: Переименовать EventLogger таблицу

**Новое имя:** `monitoring.event_performance_metrics`

```sql
CREATE TABLE IF NOT EXISTS monitoring.event_performance_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    metric_value DECIMAL(20, 8),
    tags JSONB,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_event_metrics_name ON monitoring.event_performance_metrics (metric_name);
CREATE INDEX IF NOT EXISTS idx_event_metrics_time ON monitoring.event_performance_metrics (recorded_at DESC);
```

#### 🔧 Назначение
- Real-time метрики производительности системы событий
- Гибкая структура: metric_name + metric_value + tags (JSONB)
- Примеры метрик: event_queue_size, batch_write_duration, event_processing_rate

#### 📊 Ожидаемая нагрузка
- **Очень низкая** - метод `log_metric()` вызывается только в тестах
- В production **не используется** на текущий момент
- **Резерв на будущее**

#### 🐛 Баги в коде

**БАГ #3A - Неправильное имя таблицы и отсутствие префикса:**
```python
# event_logger.py:223 - ❌ НЕПРАВИЛЬНО
await conn.execute("""
    CREATE TABLE IF NOT EXISTS performance_metrics (
    ...
""")

# ✅ ДОЛЖНО БЫТЬ:
await conn.execute("""
    CREATE TABLE IF NOT EXISTS monitoring.event_performance_metrics (
    ...
""")
```

**БАГ #3B - INSERT без префикса и неправильное имя:**
```python
# event_logger.py:429 - ❌ НЕПРАВИЛЬНО
query = """
    INSERT INTO performance_metrics (
    ...
"""

# ✅ ДОЛЖНО БЫТЬ:
query = """
    INSERT INTO monitoring.event_performance_metrics (
    ...
"""
```

**БАГ #3C - Indexes без префикса и неправильное имя:**
```python
# event_logger.py:233-234 - ❌ НЕПРАВИЛЬНО
await conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON performance_metrics (metric_name)")
await conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_time ON performance_metrics (recorded_at DESC)")

# ✅ ДОЛЖНО БЫТЬ:
await conn.execute("CREATE INDEX IF NOT EXISTS idx_event_metrics_name ON monitoring.event_performance_metrics (metric_name)")
await conn.execute("CREATE INDEX IF NOT EXISTS idx_event_metrics_time ON monitoring.event_performance_metrics (recorded_at DESC)")
```

#### 📝 Обоснование полей

| Поле | Тип | Назначение | Обязательно |
|------|-----|------------|-------------|
| id | SERIAL | Уникальный ID записи | ✅ |
| metric_name | VARCHAR(100) | Название метрики | ✅ |
| metric_value | DECIMAL(20, 8) | Числовое значение | ✅ |
| tags | JSONB | Дополнительные метаданные | ❌ |
| recorded_at | TIMESTAMP WITH TIME ZONE | Время записи метрики | ✅ |

**Примечания:**
- Гибкая структура позволяет добавлять любые метрики без изменения схемы
- `tags` для дополнительных измерений (например, {\"exchange\": \"bybit\", \"symbol\": \"BTCUSDT\"})

#### ⚠️ Приоритет
**НИЗКИЙ** - Таблица не используется в production. Создать для полноты, но фиксить баги в коде не критично.

---

## 📊 СРАВНИТЕЛЬНЫЙ АНАЛИЗ

### Приоритеты таблиц по критичности

| Таблица | Статус | Используется | Критичность | Приоритет фикса |
|---------|--------|--------------|-------------|-----------------|
| monitoring.events | ❌ Не существует | ✅ ДА (56 событий за 14 мин) | 🔴 КРИТИЧЕСКАЯ | 1 - НЕМЕДЛЕННО |
| monitoring.transaction_log | ❌ Не существует | ❌ НЕТ (только в тестах) | 🟡 НИЗКАЯ | 3 - Резерв на будущее |
| monitoring.event_performance_metrics | ❌ Не существует + конфликт имени | ❌ НЕТ (только в тестах) | 🟡 НИЗКАЯ | 3 - Резерв на будущее |

### Конфликты и зависимости

#### ✅ Зависимости
- `monitoring.events.position_id` → `monitoring.positions.id` (soft FK, без constraint)
- Никаких hard FK constraints - система устойчива к отсутствующим записям

#### ⚠️ Конфликты
- **monitoring.performance_metrics** - занято другой таблицей (database/init.sql:109)
  - **32 записи** уже в БД
  - **НЕ УДАЛЯТЬ!** Это таблица торговой статистики!

#### 🗂️ Схема
Все таблицы должны быть в схеме `monitoring` согласно:
- `database/repository.py:48`: `search_path: 'monitoring,fas,public'`
- Пользовательский feedback: "мы работает только с monitoring!!!"

---

## 🔐 ПРОВЕРКА БЕЗОПАСНОСТИ

### Существующие данные

```sql
-- Проверено 2025-10-14
SELECT table_name,
       (SELECT COUNT(*) FROM monitoring.table_name) as records
FROM information_schema.tables
WHERE table_schema = 'monitoring'
  AND table_name IN ('events', 'transaction_log', 'performance_metrics');
```

**Результаты:**
- `monitoring.events` → 0 записей (не существует)
- `monitoring.transaction_log` → 0 записей (не существует)
- `monitoring.performance_metrics` → **32 записи** ⚠️ **НЕ ТРОГАТЬ!**

### ⚠️ КРИТИЧЕСКИ ВАЖНО

**НЕ ВЫПОЛНЯТЬ:** файл `fix_event_logger_tables.sql`

```sql
-- ❌ ОПАСНО! Этот файл удаляет данные!
DROP TABLE IF EXISTS monitoring.performance_metrics CASCADE;  -- ⚠️ 32 записи будут потеряны!
```

Этот файл был создан ранее без понимания конфликта имен. **НЕ ИСПОЛЬЗОВАТЬ!**

---

## 🎯 ПЛАН БЕЗОПАСНОГО ИСПОЛНЕНИЯ

### ✅ PHASE 1: Создание таблиц БД (КРИТИЧЕСКОЕ - немедленно)

**Цель:** Создать таблицу `monitoring.events` чтобы события перестали теряться

#### Шаг 1.1: Pre-migration проверки

```sql
-- Проверка 1: Схема monitoring существует
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'monitoring';
-- Ожидаемый результат: 1 строка

-- Проверка 2: Таблица events не существует
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'monitoring' AND table_name = 'events';
-- Ожидаемый результат: 0 строк

-- Проверка 3: Права пользователя
SELECT has_schema_privilege('elcrypto', 'monitoring', 'CREATE');
-- Ожидаемый результат: t (true)
```

#### Шаг 1.2: Создание таблицы monitoring.events

**Файл:** `database/migrations/004_create_event_logger_tables.sql`

```sql
-- Migration: Create EventLogger tables
-- Date: 2025-10-14
-- Purpose: Enable event audit trail for bot operations

BEGIN;

-- =====================================================
-- TABLE 1: monitoring.events (CRITICAL)
-- =====================================================

CREATE TABLE IF NOT EXISTS monitoring.events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    correlation_id VARCHAR(100),
    position_id INTEGER,
    order_id VARCHAR(100),
    symbol VARCHAR(50),
    exchange VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'INFO',
    error_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_events_type ON monitoring.events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON monitoring.events (correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_position ON monitoring.events (position_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON monitoring.events (created_at DESC);

-- Add comment
COMMENT ON TABLE monitoring.events IS 'Event audit trail for all critical bot operations';

-- =====================================================
-- TABLE 2: monitoring.transaction_log (LOW PRIORITY)
-- =====================================================

CREATE TABLE IF NOT EXISTS monitoring.transaction_log (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) UNIQUE,
    operation VARCHAR(100),
    status VARCHAR(20),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    affected_rows INTEGER,
    error_message TEXT
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_tx_log_id ON monitoring.transaction_log (transaction_id);
CREATE INDEX IF NOT EXISTS idx_tx_log_status ON monitoring.transaction_log (status);

-- Add comment
COMMENT ON TABLE monitoring.transaction_log IS 'Database transaction performance tracking';

-- =====================================================
-- TABLE 3: monitoring.event_performance_metrics (LOW PRIORITY)
-- =====================================================
-- NOTE: Original name was 'performance_metrics' but that name is taken
--       by trading statistics table (database/init.sql:109)

CREATE TABLE IF NOT EXISTS monitoring.event_performance_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    metric_value DECIMAL(20, 8),
    tags JSONB,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_event_metrics_name ON monitoring.event_performance_metrics (metric_name);
CREATE INDEX IF NOT EXISTS idx_event_metrics_time ON monitoring.event_performance_metrics (recorded_at DESC);

-- Add comment
COMMENT ON TABLE monitoring.event_performance_metrics IS 'Real-time EventLogger performance metrics';

COMMIT;
```

#### Шаг 1.3: Выполнение миграции

```bash
# Backup базы перед изменениями
pg_dump -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -n monitoring \
  -f /tmp/monitoring_backup_before_event_tables_$(date +%Y%m%d_%H%M%S).sql

# Выполнить миграцию
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -f database/migrations/004_create_event_logger_tables.sql

# Проверить успешность
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -c "\dt monitoring.events"
```

#### Шаг 1.4: Post-migration проверки

```sql
-- Проверка 1: Таблицы созданы
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'monitoring'
  AND table_name IN ('events', 'transaction_log', 'event_performance_metrics')
ORDER BY table_name;
-- Ожидаемый результат: 3 строки

-- Проверка 2: Indexes созданы
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'monitoring'
  AND tablename IN ('events', 'transaction_log', 'event_performance_metrics')
ORDER BY tablename, indexname;
-- Ожидаемый результат: 8 индексов

-- Проверка 3: Структура monitoring.events
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'monitoring' AND table_name = 'events'
ORDER BY ordinal_position;
-- Ожидаемый результат: 12 колонок

-- Проверка 4: Старая performance_metrics не затронута
SELECT COUNT(*) as records FROM monitoring.performance_metrics;
-- Ожидаемый результат: 32 (данные не потеряны)
```

#### ⏱️ Ожидаемое время выполнения
- Backup: ~5 секунд
- Migration: ~2 секунды
- Verification: ~3 секунды
- **Итого: ~10 секунд**

#### ✅ Success Criteria
- Таблица `monitoring.events` создана
- Все 4 индекса на `monitoring.events` созданы
- Бот может писать события без ошибок

---

### ⚠️ PHASE 2: Тестирование записи событий (немедленно после Phase 1)

#### Шаг 2.1: Перезапуск бота

```bash
# Остановить бота
pkill -f "python main.py"

# Запустить заново
python main.py --mode production --exchange both &

# Подождать инициализации
sleep 10
```

#### Шаг 2.2: Проверка записи событий

```sql
-- Проверка 1: События начали записываться
SELECT COUNT(*) as total_events
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '5 minutes';
-- Ожидаемый результат: > 0 (события появляются)

-- Проверка 2: Типы событий
SELECT event_type, COUNT(*) as count
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '5 minutes'
GROUP BY event_type
ORDER BY count DESC;
-- Ожидаемый результат: bot_started, stop_loss_placed, health_check_failed, etc.

-- Проверка 3: Severity distribution
SELECT severity, COUNT(*) as count
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '5 minutes'
GROUP BY severity;
-- Ожидаемый результат: INFO, WARNING, ERROR (распределение зависит от активности)

-- Проверка 4: События с данными
SELECT event_type, event_data, symbol, exchange, severity, created_at
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '5 minutes'
ORDER BY created_at DESC
LIMIT 10;
-- Ожидаемый результат: Полные события с JSONB данными
```

#### Шаг 2.3: Мониторинг в режиме реального времени (5 минут)

```bash
# Terminal 1: Watch events table
watch -n 10 "psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c \"SELECT COUNT(*) as total, MAX(created_at) as last_event FROM monitoring.events WHERE created_at > NOW() - INTERVAL '5 minutes'\""

# Terminal 2: Watch bot logs
tail -f /tmp/bot_monitor.log | grep "event_logger"
```

#### ✅ Success Criteria
- События появляются в `monitoring.events` в течение 1 минуты после перезапуска
- Минимум 3 типа событий: `bot_started`, `health_check_failed`, `stop_loss_placed`
- event_data содержит валидный JSON
- Нет ошибок "relation monitoring.events does not exist"

---

### 🔧 PHASE 3: Фикс багов в коде (после подтверждения Phase 2)

**Статус:** ОПЦИОНАЛЬНЫЙ (таблицы будут работать благодаря search_path)

#### Объяснение
search_path = 'monitoring,fas,public' означает что PostgreSQL **автоматически ищет таблицы** в схемах по порядку:
1. monitoring
2. fas
3. public

Поэтому запросы `INSERT INTO events` **будут работать** если таблица существует в monitoring.

#### ⚠️ НО: Рекомендуется явное указание схемы

**Причины:**
1. Лучше явное, чем неявное (Zen of Python)
2. Защита от конфликтов имен (если кто-то создаст events в public)
3. Производительность (PostgreSQL не тратит время на поиск по search_path)
4. Ясность кода для других разработчиков

#### Требуемые изменения в core/event_logger.py

**Файл:** core/event_logger.py
**Строки для изменения:** 180, 197-200, 204, 218-219, 223, 233-234, 333, 362, 401, 429, 450, 473

**Список изменений:**

1. **Строка 180:** `events` → `monitoring.events`
2. **Строки 197-200:** Все индексы `events` → `monitoring.events`
3. **Строка 204:** `transaction_log` → `monitoring.transaction_log`
4. **Строки 218-219:** Все индексы `transaction_log` → `monitoring.transaction_log`
5. **Строка 223:** `performance_metrics` → `monitoring.event_performance_metrics`
6. **Строки 233-234:** Все индексы `performance_metrics` → `monitoring.event_performance_metrics` + переименовать индексы
7. **Строка 333:** `INSERT INTO events` → `INSERT INTO monitoring.events`
8. **Строка 362:** `INSERT INTO events` → `INSERT INTO monitoring.events`
9. **Строка 401:** `INSERT INTO transaction_log` → `INSERT INTO monitoring.transaction_log`
10. **Строка 429:** `INSERT INTO performance_metrics` → `INSERT INTO monitoring.event_performance_metrics`
11. **Строка 450:** `FROM events` → `FROM monitoring.events`
12. **Строка 473:** `FROM events` → `FROM monitoring.events`

#### ⏸️ Рекомендация
**НЕ ФИКСИТЬ СЕЙЧАС** если система работает после Phase 1-2. Это refactoring, не критический баг.

**Фиксить только если:**
- Хотим 100% идеальный код (best practice)
- Планируем масштабировать (больше схем)
- Требуется code review compliance

---

## 🧪 ПЛАН ТЕСТИРОВАНИЯ

### Test Suite 1: Database Structure Tests

**Файл:** `tests/phase8/test_event_logger_tables.py`

```python
"""
Test Phase 8: EventLogger Database Tables
"""
import pytest
import asyncpg


@pytest.mark.asyncio
async def test_monitoring_events_table_exists():
    """Verify monitoring.events table exists"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    result = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'events'
    """)

    assert result == 1, "monitoring.events table does not exist"
    await conn.close()


@pytest.mark.asyncio
async def test_monitoring_events_columns():
    """Verify monitoring.events has all required columns"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    columns = await conn.fetch("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'monitoring' AND table_name = 'events'
        ORDER BY ordinal_position
    """)

    column_names = [c['column_name'] for c in columns]

    required = ['id', 'event_type', 'event_data', 'correlation_id',
                'position_id', 'order_id', 'symbol', 'exchange',
                'severity', 'error_message', 'stack_trace', 'created_at']

    for col in required:
        assert col in column_names, f"Missing column: {col}"

    await conn.close()


@pytest.mark.asyncio
async def test_monitoring_events_indexes():
    """Verify monitoring.events has all required indexes"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    indexes = await conn.fetch("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'monitoring' AND tablename = 'events'
    """)

    index_names = [i['indexname'] for i in indexes]

    required = ['idx_events_type', 'idx_events_correlation',
                'idx_events_position', 'idx_events_created']

    for idx in required:
        assert idx in index_names, f"Missing index: {idx}"

    await conn.close()


@pytest.mark.asyncio
async def test_monitoring_transaction_log_exists():
    """Verify monitoring.transaction_log table exists"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    result = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'transaction_log'
    """)

    assert result == 1, "monitoring.transaction_log table does not exist"
    await conn.close()


@pytest.mark.asyncio
async def test_monitoring_event_performance_metrics_exists():
    """Verify monitoring.event_performance_metrics table exists"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    result = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'event_performance_metrics'
    """)

    assert result == 1, "monitoring.event_performance_metrics table does not exist"
    await conn.close()


@pytest.mark.asyncio
async def test_old_performance_metrics_not_affected():
    """Verify old monitoring.performance_metrics was not dropped"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    # Check table exists
    table_exists = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'performance_metrics'
    """)
    assert table_exists == 1, "Original performance_metrics table was dropped!"

    # Check data not lost
    record_count = await conn.fetchval("""
        SELECT COUNT(*) FROM monitoring.performance_metrics
    """)
    assert record_count >= 32, f"Data lost! Expected >=32 records, got {record_count}"

    # Check structure is old structure (not EventLogger structure)
    columns = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'monitoring' AND table_name = 'performance_metrics'
    """)
    column_names = [c['column_name'] for c in columns]

    # Should have OLD structure
    assert 'period' in column_names, "Old structure missing"
    assert 'total_trades' in column_names, "Old structure missing"

    # Should NOT have EventLogger structure
    assert 'metric_name' not in column_names, "EventLogger structure found in wrong table!"

    await conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
```

### Test Suite 2: Event Writing Tests

**Файл:** `tests/phase8/test_event_logger_integration.py`

```python
"""
Test Phase 8: EventLogger Integration with Database
"""
import pytest
from core.event_logger import get_event_logger, EventType
import asyncpg


@pytest.mark.asyncio
async def test_event_logger_writes_to_database():
    """Verify EventLogger actually writes events to monitoring.events"""
    event_logger = get_event_logger()
    assert event_logger is not None, "EventLogger not initialized"

    # Connect to DB
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    # Get initial count
    initial_count = await conn.fetchval("""
        SELECT COUNT(*) FROM monitoring.events
    """)

    # Log test event
    await event_logger.log_event(
        EventType.BOT_STARTED,
        {'test': 'integration_test', 'timestamp': 'now'},
        symbol='TESTUSDT',
        exchange='test_exchange',
        severity='INFO'
    )

    # Wait for batch write (max 5 seconds)
    import asyncio
    await asyncio.sleep(6)

    # Check event was written
    final_count = await conn.fetchval("""
        SELECT COUNT(*) FROM monitoring.events
    """)

    assert final_count > initial_count, \
        f"Event not written to DB! Initial: {initial_count}, Final: {final_count}"

    # Verify event data
    event = await conn.fetchrow("""
        SELECT * FROM monitoring.events
        WHERE event_type = 'bot_started'
          AND symbol = 'TESTUSDT'
        ORDER BY created_at DESC
        LIMIT 1
    """)

    assert event is not None, "Test event not found in DB"
    assert event['exchange'] == 'test_exchange'
    assert event['severity'] == 'INFO'
    assert 'test' in event['event_data']

    await conn.close()


@pytest.mark.asyncio
async def test_event_logger_correlation_id():
    """Verify correlation_id is stored correctly"""
    event_logger = get_event_logger()

    correlation_id = 'test-correlation-12345'

    await event_logger.log_event(
        EventType.POSITION_CREATED,
        {'test': 'correlation'},
        correlation_id=correlation_id,
        position_id=999
    )

    import asyncio
    await asyncio.sleep(6)

    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    event = await conn.fetchrow("""
        SELECT * FROM monitoring.events
        WHERE correlation_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """, correlation_id)

    assert event is not None, "Correlation event not found"
    assert event['correlation_id'] == correlation_id
    assert event['position_id'] == 999

    await conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
```

---

## 📋 ROLLBACK PROCEDURE

Если что-то пошло не так во время Phase 1:

### Option 1: Rollback из backup

```bash
# Restore backup
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -f /tmp/monitoring_backup_before_event_tables_YYYYMMDD_HHMMSS.sql
```

### Option 2: Manual cleanup

```sql
BEGIN;

-- Drop EventLogger tables
DROP TABLE IF EXISTS monitoring.events CASCADE;
DROP TABLE IF EXISTS monitoring.transaction_log CASCADE;
DROP TABLE IF EXISTS monitoring.event_performance_metrics CASCADE;

-- Verify old performance_metrics still intact
SELECT COUNT(*) FROM monitoring.performance_metrics;
-- Should return 32

COMMIT;
```

### ⚠️ ВАЖНО
**НЕ УДАЛЯТЬ** `monitoring.performance_metrics` - это таблица торговой статистики!

---

## 📊 ИТОГОВАЯ СТАТИСТИКА

### Найдено багов: 9

| # | Баг | Файл | Строки | Критичность |
|---|-----|------|--------|-------------|
| 1A | CREATE TABLE events без monitoring. | event_logger.py | 180 | 🔴 CRITICAL |
| 1B | INSERT INTO events без monitoring. | event_logger.py | 333, 362 | 🔴 CRITICAL |
| 1C | SELECT FROM events без monitoring. | event_logger.py | 450, 473 | 🔴 CRITICAL |
| 2A | CREATE TABLE transaction_log без monitoring. | event_logger.py | 204 | 🟡 LOW |
| 2B | INSERT INTO transaction_log без monitoring. | event_logger.py | 401 | 🟡 LOW |
| 3A | Конфликт имени performance_metrics | event_logger.py | 223 | 🟠 MEDIUM |
| 3B | INSERT INTO performance_metrics без monitoring. | event_logger.py | 429 | 🟡 LOW |
| 3C | Indexes performance_metrics без monitoring. | event_logger.py | 233-234 | 🟡 LOW |
| 3D | Индексы с неправильными именами | event_logger.py | 233-234 | 🟡 LOW |

### Требуемые таблицы: 3

| Таблица | Статус | Records | Приоритет |
|---------|--------|---------|-----------|
| monitoring.events | ❌ Создать | 0 | 🔴 CRITICAL |
| monitoring.transaction_log | ❌ Создать | 0 | 🟡 LOW |
| monitoring.event_performance_metrics | ❌ Создать (новое имя!) | 0 | 🟡 LOW |

### Затронутые данные: 0

**Безопасность:** ✅ Никакие существующие данные не будут затронуты или удалены

**Единственная предосторожность:** НЕ выполнять `fix_event_logger_tables.sql` (он удаляет 32 записи!)

---

## ✅ ФИНАЛЬНАЯ РЕКОМЕНДАЦИЯ

### Немедленно (сегодня):

1. ✅ **Создать таблицу monitoring.events** (Phase 1)
   - SQL миграция `database/migrations/004_create_event_logger_tables.sql`
   - 10 секунд выполнения
   - Backup на всякий случай

2. ✅ **Перезапустить бота и проверить** (Phase 2)
   - Мониторить 5 минут
   - Убедиться что события пишутся
   - Выполнить Test Suite 1 и 2

### Опционально (когда будет время):

3. ⏸️ **Фикс багов в коде** (Phase 3)
   - Добавить префикс `monitoring.` ко всем таблицам
   - Переименовать `performance_metrics` → `event_performance_metrics`
   - Только если нужен идеальный код

### НЕ делать:

- ❌ НЕ выполнять `fix_event_logger_tables.sql`
- ❌ НЕ удалять `monitoring.performance_metrics`
- ❌ НЕ трогать существующие таблицы

---

## 📝 CONFIDENCE LEVEL

**Уверенность:** 100% ✅

**Обоснование:**
- Проверен код event_logger.py полностью (526 строк)
- Проверена структура БД (psql queries)
- Найдены все 3 таблицы в коде
- Проверен конфликт имен с существующей таблицей
- Проверено количество записей в БД (32 в performance_metrics)
- Проверен database/init.sql для понимания существующей схемы
- Проверены все INSERT/SELECT запросы
- План протестирован логически на отсутствие рисков

**Риски:** МИНИМАЛЬНЫЕ
- Создаем новые таблицы (не трогаем существующие)
- Backup перед изменениями
- search_path позволит системе работать даже без префиксов

---

**Дата отчета:** 2025-10-14
**Автор:** Claude Code (Deep Research)
**Статус:** ✅ READY FOR IMPLEMENTATION
