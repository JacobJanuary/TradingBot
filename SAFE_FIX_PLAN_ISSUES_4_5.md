# ДЕТАЛЬНЫЙ И БЕЗОПАСНЫЙ ПЛАН ИСПРАВЛЕНИЯ ПРОБЛЕМ #4 И #5
## База данных: fox_crypto, Схема: monitoring

Дата создания плана: 2025-10-14
Статус: **ТОЛЬКО ПЛАН - БЕЗ ИЗМЕНЕНИЙ КОДА**

---

## ОГЛАВЛЕНИЕ

1. [Текущее состояние системы](#текущее-состояние-системы)
2. [Проблема #4: Триггеры updated_at](#проблема-4-триггеры-updated_at)
3. [Проблема #5: Динамическое создание таблиц](#проблема-5-динамическое-создание-таблиц)
4. [Порядок выполнения исправлений](#порядок-выполнения-исправлений)
5. [План отката (Rollback Plan)](#план-отката-rollback-plan)
6. [Чек-листы верификации](#чек-листы-верификации)

---

## ТЕКУЩЕЕ СОСТОЯНИЕ СИСТЕМЫ

### Структура базы данных

**Таблицы с колонкой updated_at**:
```
✅ monitoring.positions     - updated_at TIMESTAMP DEFAULT NOW()
✅ monitoring.trades        - updated_at TIMESTAMP DEFAULT NOW()
✅ monitoring.alert_rules   - updated_at TIMESTAMP DEFAULT NOW()
✅ monitoring.daily_stats   - updated_at TIMESTAMP DEFAULT NOW()
```

**Таблицы без колонки updated_at**:
```
⚠️ monitoring.events                      - события неизменяемые (не нужна)
⚠️ monitoring.transaction_log             - логи неизменяемые (не нужна)
⚠️ monitoring.event_performance_metrics   - метрики неизменяемые (не нужна)
⚠️ monitoring.protection_events           - НУЖНА колонка updated_at
⚠️ monitoring.orders                      - НУЖНА колонка updated_at
```

### Существующие триггеры

**Триггеры updated_at**: НОЛЬ в схеме monitoring

**Функции updated_at в базе**:
- ✅ `public.update_updated_at_column` - существует, можно переиспользовать
- ✅ `trading.update_updated_at_column` - существует в другой схеме
- ✅ `ats.update_orders_updated_at` - существует в другой схеме

### EventLogger таблицы

**Созданы постоянно в схеме**:
- ✅ monitoring.events
- ✅ monitoring.transaction_log
- ✅ monitoring.event_performance_metrics

**Также создаются динамически в коде**:
- ⚠️ core/event_logger.py:172 - вызов `await self._create_tables()`
- ⚠️ core/event_logger.py:179-238 - метод `_create_tables()` с 59 строками SQL

### Применённые миграции

```
✅ add_exit_reason_column.sql           - 2025-10-04 02:27:02
✅ add_missing_position_fields.sql      - 2025-10-04 02:27:48
✅ add_realized_pnl_column.sql          - 2025-10-04 02:28:09
✅ create_processed_signals_table.sql   - 2025-10-04 02:28:09
✅ fix_field_sync.sql                   - 2025-10-04 02:28:10
```

**Отсутствующие миграции**:
- ⚠️ Миграция 004_create_event_logger_tables.sql НЕ ПРИМЕНЕНА (файл существует, но не в базе)
- ⚠️ Нет системы нумерации миграций (001_, 002_, 003_...)

---

## ПРОБЛЕМА #4: ТРИГГЕРЫ UPDATED_AT

### Описание проблемы

**Текущее поведение**:
- Колонки `updated_at` существуют в 4 таблицах
- При INSERT устанавливается `DEFAULT NOW()`
- При UPDATE колонка `updated_at` НЕ обновляется автоматически
- Требуется ручное обновление: `UPDATE positions SET updated_at = NOW(), ...`

**Желаемое поведение**:
- При любом UPDATE автоматически обновлять `updated_at = NOW()`
- Стандартный PostgreSQL паттерн через триггеры

**Риски**:
- ⚠️ Минимальный риск - только добавление триггеров, без изменения данных
- ⚠️ Триггер срабатывает на КАЖДЫЙ UPDATE - небольшая нагрузка CPU
- ✅ Стандартный паттерн, используется в других схемах базы

---

### ПЛАН ИСПРАВЛЕНИЯ ПРОБЛЕМЫ #4

#### ФАЗ 1: ПОДГОТОВКА (Оценка: 10 минут)

**Шаг 1.1: Проверить существование функции триггера**

```sql
-- Запрос для проверки
SELECT
    routine_schema,
    routine_name,
    routine_definition
FROM information_schema.routines
WHERE routine_name = 'update_updated_at_column'
AND routine_schema = 'public';
```

**Ожидаемый результат**: Функция `public.update_updated_at_column` существует

**Если функции нет** - нужно будет создать в миграции.

---

**Шаг 1.2: Определить список таблиц для добавления триггеров**

**Приоритет ВЫСОКИЙ** (часто обновляются):
- ✅ `monitoring.positions` - обновления позиций (quantity, current_price, pnl, status)
- ✅ `monitoring.orders` - обновления ордеров (status, filled, remaining)

**Приоритет СРЕДНИЙ** (иногда обновляются):
- ✅ `monitoring.trades` - обновления сделок (status, executed_qty)
- ✅ `monitoring.protection_events` - обновления защитных событий

**НЕ НУЖНЫ** (таблицы неизменяемые):
- ❌ `monitoring.events` - события только INSERT, никогда UPDATE
- ❌ `monitoring.transaction_log` - логи только INSERT
- ❌ `monitoring.event_performance_metrics` - метрики только INSERT

---

**Шаг 1.3: Проверить существующие UPDATE операции в коде**

```bash
# Найти все UPDATE запросы в коде
grep -r "UPDATE monitoring\." --include="*.py" /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/

# Проверить, устанавливают ли они updated_at вручную
grep -r "updated_at.*NOW()" --include="*.py" /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/
```

**Цель**: Убедиться, что после добавления триггеров не будет дублирования установки updated_at.

**Если находим ручную установку** - это нормально, триггер перезапишет значение автоматически.

---

**Шаг 1.4: Проверить текущее состояние updated_at**

```sql
-- Проверить значения updated_at для активных позиций
SELECT
    id,
    symbol,
    status,
    created_at,
    updated_at,
    CASE
        WHEN created_at = updated_at THEN 'NEVER UPDATED'
        ELSE 'WAS UPDATED'
    END as update_status
FROM monitoring.positions
WHERE status = 'active'
ORDER BY id DESC
LIMIT 10;

-- То же для trades
SELECT
    id,
    symbol,
    status,
    executed_at as created_at,
    updated_at,
    CASE
        WHEN updated_at IS NULL THEN 'NO UPDATED_AT'
        ELSE 'HAS UPDATED_AT'
    END as update_status
FROM monitoring.trades
ORDER BY id DESC
LIMIT 10;
```

**Цель**: Понять текущее поведение для тестирования после применения триггеров.

---

#### ФАЗА 2: СОЗДАНИЕ МИГРАЦИИ (Оценка: 20 минут)

**Шаг 2.1: Создать файл миграции**

**Имя файла**: `database/migrations/005_add_updated_at_triggers.sql`

**Содержимое миграции**:

```sql
-- =====================================================
-- Migration 005: Add updated_at Auto-Update Triggers
-- =====================================================
-- Date: 2025-10-14
-- Purpose: Automatically update updated_at column on UPDATE
-- Dependencies: Tables positions, trades, orders, protection_events must exist
-- Safety: Only adds triggers, does NOT modify existing data
-- Impact: Minimal - triggers add ~0.1ms overhead per UPDATE
-- =====================================================

BEGIN;

-- =====================================================
-- PRE-CHECKS
-- =====================================================

DO $$
BEGIN
    -- Verify monitoring schema exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE EXCEPTION 'Schema monitoring does not exist';
    END IF;

    -- Verify target tables exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'positions') THEN
        RAISE EXCEPTION 'Table monitoring.positions does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'trades') THEN
        RAISE EXCEPTION 'Table monitoring.trades does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'orders') THEN
        RAISE EXCEPTION 'Table monitoring.orders does not exist';
    END IF;

    -- Verify updated_at columns exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = 'positions' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'Column monitoring.positions.updated_at does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = 'trades' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'Column monitoring.trades.updated_at does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = 'orders' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'Column monitoring.orders.updated_at does not exist';
    END IF;

    RAISE NOTICE 'Pre-checks passed';
END $$;

-- =====================================================
-- STEP 1: Create or replace trigger function
-- =====================================================
-- Note: Function created in public schema for reusability
-- Same function can be used by multiple triggers

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION public.update_updated_at_column() IS
    'Trigger function to automatically set updated_at = NOW() on UPDATE. Used by multiple triggers in monitoring schema.';

-- =====================================================
-- STEP 2: Add updated_at column to protection_events
-- =====================================================
-- This table needs updated_at column first

ALTER TABLE monitoring.protection_events
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

COMMENT ON COLUMN monitoring.protection_events.updated_at IS
    'Auto-updated timestamp of last row modification';

-- =====================================================
-- STEP 3: Create triggers for each table
-- =====================================================

-- Trigger for positions table
DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON monitoring.positions
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_positions_updated_at ON monitoring.positions IS
    'Auto-updates updated_at column on any UPDATE';

-- Trigger for trades table
DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;

CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON monitoring.trades
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_trades_updated_at ON monitoring.trades IS
    'Auto-updates updated_at column on any UPDATE';

-- Trigger for orders table
DROP TRIGGER IF EXISTS update_orders_updated_at ON monitoring.orders;

CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON monitoring.orders
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_orders_updated_at ON monitoring.orders IS
    'Auto-updates updated_at column on any UPDATE';

-- Trigger for protection_events table
DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;

CREATE TRIGGER update_protection_events_updated_at
    BEFORE UPDATE ON monitoring.protection_events
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_protection_events_updated_at ON monitoring.protection_events IS
    'Auto-updates updated_at column on any UPDATE';

-- =====================================================
-- POST-MIGRATION VERIFICATION
-- =====================================================

DO $$
DECLARE
    trigger_count INTEGER;
BEGIN
    -- Count created triggers
    SELECT COUNT(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_schema = 'monitoring'
    AND trigger_name IN (
        'update_positions_updated_at',
        'update_trades_updated_at',
        'update_orders_updated_at',
        'update_protection_events_updated_at'
    );

    IF trigger_count != 4 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Expected 4 triggers, found %', trigger_count;
    END IF;

    -- Verify function exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.routines
        WHERE routine_schema = 'public'
        AND routine_name = 'update_updated_at_column'
    ) THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Trigger function not created';
    END IF;

    -- Success message
    RAISE NOTICE '✅ Migration 005 completed successfully!';
    RAISE NOTICE '   - Trigger function: public.update_updated_at_column()';
    RAISE NOTICE '   - Triggers created: 4';
    RAISE NOTICE '     * monitoring.positions';
    RAISE NOTICE '     * monitoring.trades';
    RAISE NOTICE '     * monitoring.orders';
    RAISE NOTICE '     * monitoring.protection_events';
    RAISE NOTICE '   - Column added: protection_events.updated_at';
END $$;

COMMIT;

-- =====================================================
-- ROLLBACK INSTRUCTIONS
-- =====================================================
-- If you need to rollback this migration, run:
--
-- BEGIN;
-- DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;
-- DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;
-- DROP TRIGGER IF EXISTS update_orders_updated_at ON monitoring.orders;
-- DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;
-- DROP FUNCTION IF EXISTS public.update_updated_at_column();
-- ALTER TABLE monitoring.protection_events DROP COLUMN IF EXISTS updated_at;
-- COMMIT;
--
-- WARNING: This will stop automatic updated_at updates!
-- =====================================================
```

---

**Шаг 2.2: Валидация синтаксиса миграции**

```bash
# Проверить SQL синтаксис без выполнения
psql -h localhost -p 5433 -U elcrypto -d fox_crypto --dry-run -f database/migrations/005_add_updated_at_triggers.sql 2>&1 | grep -i error

# Если команда --dry-run не поддерживается, использовать альтернативный метод:
# Создать временную копию базы и применить там
```

---

#### ФАЗА 3: ТЕСТИРОВАНИЕ НА DEV/TEST БАЗЕ (Оценка: 30 минут)

**КРИТИЧЕСКИ ВАЖНО**: НЕ применять на продакшен базе сразу!

**Шаг 3.1: Создать тестовую копию базы данных**

```bash
# Создать дамп текущей базы
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto -F c -b -v -f /tmp/fox_crypto_before_migration_005.backup

# Создать тестовую базу
psql -h localhost -p 5433 -U elcrypto -c "CREATE DATABASE fox_crypto_test TEMPLATE fox_crypto;"

# Или восстановить из бэкапа
psql -h localhost -p 5433 -U elcrypto -c "CREATE DATABASE fox_crypto_test;"
pg_restore -h localhost -p 5433 -U elcrypto -d fox_crypto_test /tmp/fox_crypto_before_migration_005.backup
```

---

**Шаг 3.2: Применить миграцию на тестовой базе**

```bash
# Применить миграцию
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -f database/migrations/005_add_updated_at_triggers.sql

# Проверить результат
echo $?  # Должно быть 0 (успех)
```

**Ожидаемый вывод**:
```
NOTICE:  Pre-checks passed
NOTICE:  ✅ Migration 005 completed successfully!
NOTICE:     - Trigger function: public.update_updated_at_column()
NOTICE:     - Triggers created: 4
NOTICE:       * monitoring.positions
NOTICE:       * monitoring.trades
NOTICE:       * monitoring.orders
NOTICE:       * monitoring.protection_events
NOTICE:     - Column added: protection_events.updated_at
COMMIT
```

---

**Шаг 3.3: Верификация триггеров**

```sql
-- Подключиться к тестовой базе
-- psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test

-- Проверка 1: Триггеры созданы
SELECT
    event_object_table as table_name,
    trigger_name,
    event_manipulation,
    action_timing
FROM information_schema.triggers
WHERE trigger_schema = 'monitoring'
AND trigger_name LIKE '%updated_at%'
ORDER BY event_object_table;

-- Ожидаемый результат: 4 строки
-- positions        | update_positions_updated_at         | UPDATE | BEFORE
-- trades           | update_trades_updated_at            | UPDATE | BEFORE
-- orders           | update_orders_updated_at            | UPDATE | BEFORE
-- protection_events| update_protection_events_updated_at | UPDATE | BEFORE

-- Проверка 2: Функция создана
SELECT routine_name, routine_schema
FROM information_schema.routines
WHERE routine_name = 'update_updated_at_column'
AND routine_schema = 'public';

-- Ожидаемый результат: 1 строка
-- update_updated_at_column | public

-- Проверка 3: Колонка добавлена
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema = 'monitoring'
AND table_name = 'protection_events'
AND column_name = 'updated_at';

-- Ожидаемый результат: 1 строка
-- updated_at | timestamp with time zone | now()
```

---

**Шаг 3.4: Функциональное тестирование триггеров**

```sql
-- TEST 1: Проверить триггер на positions
-- Создать тестовую позицию
INSERT INTO monitoring.positions (symbol, exchange, side, quantity, entry_price, status)
VALUES ('TESTUSDT', 'bybit', 'long', 1.0, 50000.0, 'active')
RETURNING id, created_at, updated_at;

-- Запомнить id и updated_at из результата
-- Пусть id = 999, updated_at = 2025-10-14 15:30:00

-- Подождать 2 секунды
SELECT pg_sleep(2);

-- Обновить позицию
UPDATE monitoring.positions
SET quantity = 2.0
WHERE id = 999
RETURNING id, quantity, created_at, updated_at;

-- КРИТИЧЕСКАЯ ПРОВЕРКА:
-- updated_at ДОЛЖЕН измениться и быть ПОЗЖЕ created_at!
-- Если updated_at = created_at → ТРИГГЕР НЕ РАБОТАЕТ!

-- Проверить разницу
SELECT
    id,
    quantity,
    created_at,
    updated_at,
    (updated_at - created_at) as time_diff,
    CASE
        WHEN updated_at > created_at THEN '✅ TRIGGER WORKS'
        WHEN updated_at = created_at THEN '❌ TRIGGER FAILED'
        ELSE '⚠️ UNEXPECTED STATE'
    END as trigger_status
FROM monitoring.positions
WHERE id = 999;

-- Ожидаемый результат:
-- time_diff > 0 seconds
-- trigger_status = '✅ TRIGGER WORKS'

-- TEST 2: Проверить триггер на trades
INSERT INTO monitoring.trades (symbol, exchange, side, quantity, price, status)
VALUES ('TESTUSDT', 'bybit', 'buy', 1.0, 50000.0, 'pending')
RETURNING id, executed_at as created_at, updated_at;

SELECT pg_sleep(2);

UPDATE monitoring.trades SET status = 'filled' WHERE id = (SELECT MAX(id) FROM monitoring.trades)
RETURNING id, status, executed_at, updated_at;

-- Проверить
SELECT
    id, status,
    CASE WHEN updated_at > executed_at THEN '✅ WORKS' ELSE '❌ FAILED' END
FROM monitoring.trades
WHERE id = (SELECT MAX(id) FROM monitoring.trades);

-- TEST 3: Проверить триггер на orders
INSERT INTO monitoring.orders (exchange, symbol, type, side, status)
VALUES ('bybit', 'TESTUSDT', 'limit', 'buy', 'pending')
RETURNING id, created_at, updated_at;

SELECT pg_sleep(2);

UPDATE monitoring.orders SET status = 'filled' WHERE id = (SELECT MAX(id) FROM monitoring.orders)
RETURNING id, status, created_at, updated_at;

-- Проверить
SELECT
    id, status,
    CASE WHEN updated_at > created_at THEN '✅ WORKS' ELSE '❌ FAILED' END
FROM monitoring.orders
WHERE id = (SELECT MAX(id) FROM monitoring.orders);

-- Очистить тестовые данные
DELETE FROM monitoring.positions WHERE symbol = 'TESTUSDT';
DELETE FROM monitoring.trades WHERE symbol = 'TESTUSDT';
DELETE FROM monitoring.orders WHERE symbol = 'TESTUSDT';
```

**Критерий успеха**:
- ✅ Все 3 теста показывают "✅ WORKS"
- ✅ updated_at автоматически обновляется при UPDATE
- ✅ Нет ошибок при выполнении UPDATE

---

**Шаг 3.5: Нагрузочное тестирование**

```sql
-- Измерить влияние триггера на производительность
-- TEST: 1000 UPDATE операций

-- Создать тестовую позицию
INSERT INTO monitoring.positions (symbol, exchange, side, quantity, entry_price, status)
VALUES ('LOADTEST', 'bybit', 'long', 1.0, 50000.0, 'active')
RETURNING id;

-- Запомнить id, пусть id = 1000

-- Тест БЕЗ триггера (откатить триггер временно)
DROP TRIGGER update_positions_updated_at ON monitoring.positions;

-- Измерить время
\timing on

DO $$
BEGIN
    FOR i IN 1..1000 LOOP
        UPDATE monitoring.positions SET quantity = i WHERE id = 1000;
    END LOOP;
END $$;

\timing off
-- Запомнить время, например: Time: 1234.567 ms

-- Создать триггер снова
CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON monitoring.positions
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- Тест С триггером
\timing on

DO $$
BEGIN
    FOR i IN 1..1000 LOOP
        UPDATE monitoring.positions SET quantity = i WHERE id = 1000;
    END LOOP;
END $$;

\timing off
-- Запомнить время, например: Time: 1256.789 ms

-- Очистить
DELETE FROM monitoring.positions WHERE symbol = 'LOADTEST';

-- АНАЛИЗ:
-- Overhead триггера = (время_с_триггером - время_без_триггера) / количество_операций
-- Ожидаемый overhead: ~0.1-0.5 ms на UPDATE
-- Приемлемо если < 1 ms
```

**Критерий успеха**:
- ✅ Overhead триггера < 1 ms на UPDATE
- ✅ Триггер не вызывает deadlocks
- ✅ Производительность приемлемая

---

**Шаг 3.6: Тестирование с реальными операциями бота**

```bash
# Запустить бота на тестовой базе
# Изменить .env временно:
DB_NAME=fox_crypto_test

# Запустить бота на 5-10 минут
python main.py

# Мониторить логи на ошибки
tail -f /tmp/bot_test.log | grep -i error

# После 5-10 минут остановить бота
# Проверить что updated_at обновляется корректно
```

**Критерий успеха**:
- ✅ Бот работает без ошибок
- ✅ Нет ошибок, связанных с updated_at
- ✅ Триггеры не замедляют операции бота

---

#### ФАЗА 4: ПРИМЕНЕНИЕ НА ПРОДАКШЕН БАЗЕ (Оценка: 15 минут)

**КРИТИЧЕСКИ ВАЖНО**: Выполнять только после успешного тестирования!

**Шаг 4.1: Создать бэкап продакшен базы**

```bash
# ОБЯЗАТЕЛЬНЫЙ ШАГ - НЕ ПРОПУСКАТЬ!
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto -F c -b -v -f /tmp/fox_crypto_backup_before_005_$(date +%Y%m%d_%H%M%S).backup

# Проверить размер бэкапа
ls -lh /tmp/fox_crypto_backup_before_005_*.backup

# Проверить что бэкап валидный
pg_restore --list /tmp/fox_crypto_backup_before_005_*.backup | head -20
```

**Критерий успеха**:
- ✅ Файл бэкапа создан
- ✅ Размер бэкапа разумный (не 0 байт)
- ✅ pg_restore может прочитать бэкап

---

**Шаг 4.2: Остановить бота (опционально)**

**Рекомендация**: Миграция 005 может применяться на работающей базе (триггеры создаются быстро).

**Если хотите перестраховаться**:
```bash
# Остановить бота
ps aux | grep "python.*main.py"
kill <PID>

# Или если бот в systemd
# sudo systemctl stop trading-bot
```

---

**Шаг 4.3: Применить миграцию**

```bash
# Применить миграцию на продакшен базе
psql -h localhost -p 5433 -U elcrypto -d fox_crypto -f database/migrations/005_add_updated_at_triggers.sql

# Проверить exit code
if [ $? -eq 0 ]; then
    echo "✅ Migration applied successfully"
else
    echo "❌ Migration FAILED! Rolling back..."
    # Выполнить rollback (см. секцию ROLLBACK)
fi
```

**Ожидаемое время выполнения**: 1-3 секунды

---

**Шаг 4.4: Верификация применения**

```sql
-- Быстрая проверка что триггеры созданы
SELECT COUNT(*) as trigger_count
FROM information_schema.triggers
WHERE trigger_schema = 'monitoring'
AND trigger_name IN (
    'update_positions_updated_at',
    'update_trades_updated_at',
    'update_orders_updated_at',
    'update_protection_events_updated_at'
);

-- Ожидаемый результат: trigger_count = 4
```

**Если trigger_count != 4** → откатить миграцию немедленно!

---

**Шаг 4.5: Запустить бота**

```bash
# Запустить бота
python main.py &

# Или если в systemd
# sudo systemctl start trading-bot

# Мониторить логи первые 5 минут
tail -f /tmp/bot_verification.log
```

---

**Шаг 4.6: Мониторинг после применения (первые 24 часа)**

```sql
-- Проверять каждые 2 часа в первые сутки

-- Проверка 1: Триггеры работают
SELECT
    symbol,
    status,
    created_at,
    updated_at,
    (updated_at - created_at) as age,
    CASE
        WHEN updated_at > created_at THEN '✅ Updated'
        WHEN updated_at = created_at THEN '⚠️ Never updated'
        ELSE '❌ Error'
    END as trigger_status
FROM monitoring.positions
WHERE status = 'active'
ORDER BY id DESC
LIMIT 5;

-- Проверка 2: Нет ошибок в логах
-- (проверить логи бота)

-- Проверка 3: Производительность UPDATE не упала
SELECT
    schemaname,
    relname,
    n_tup_upd as updates_count,
    n_tup_hot_upd as hot_updates_count,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'monitoring'
AND relname IN ('positions', 'trades', 'orders', 'protection_events')
ORDER BY relname;
```

---

#### ФАЗА 5: ДОКУМЕНТАЦИЯ (Оценка: 10 минут)

**Шаг 5.1: Обновить README миграций**

Добавить в `database/migrations/README.md`:

```markdown
## Migration 005: Add updated_at Auto-Update Triggers

**Date**: 2025-10-14
**Status**: ✅ Applied
**Applied at**: 2025-10-14 HH:MM:SS

### Changes
- Created trigger function `public.update_updated_at_column()`
- Added triggers to 4 tables:
  - `monitoring.positions`
  - `monitoring.trades`
  - `monitoring.orders`
  - `monitoring.protection_events`
- Added column `monitoring.protection_events.updated_at`

### Impact
- Automatic `updated_at` updates on UPDATE operations
- Minimal overhead: ~0.1ms per UPDATE
- Improves auditability and debugging

### Rollback
```sql
-- See database/migrations/005_add_updated_at_triggers.sql for rollback instructions
```
```

---

**Шаг 5.2: Записать в applied_migrations**

```sql
-- Вручную записать в таблицу миграций
INSERT INTO monitoring.applied_migrations (migration_file, applied_at)
VALUES ('005_add_updated_at_triggers.sql', NOW());
```

---

### ИТОГОВЫЙ ЧЕК-ЛИСТ ПРОБЛЕМЫ #4

```
Подготовка:
[ ] Шаг 1.1: Проверена функция триггера
[ ] Шаг 1.2: Определен список таблиц
[ ] Шаг 1.3: Проверены UPDATE операции в коде
[ ] Шаг 1.4: Проверено текущее состояние updated_at

Создание миграции:
[ ] Шаг 2.1: Создан файл 005_add_updated_at_triggers.sql
[ ] Шаг 2.2: Валидирован синтаксис SQL

Тестирование:
[ ] Шаг 3.1: Создана тестовая копия БД
[ ] Шаг 3.2: Миграция применена на тестовой БД
[ ] Шаг 3.3: Верификация триггеров пройдена
[ ] Шаг 3.4: Функциональное тестирование успешно
[ ] Шаг 3.5: Нагрузочное тестирование приемлемо
[ ] Шаг 3.6: Тестирование с ботом успешно

Применение на продакшен:
[ ] Шаг 4.1: Создан бэкап продакшен БД
[ ] Шаг 4.2: Бот остановлен (опционально)
[ ] Шаг 4.3: Миграция применена успешно
[ ] Шаг 4.4: Верификация применения пройдена
[ ] Шаг 4.5: Бот запущен без ошибок
[ ] Шаг 4.6: Мониторинг первые 24 часа

Документация:
[ ] Шаг 5.1: Обновлен README миграций
[ ] Шаг 5.2: Записано в applied_migrations

ОБЩИЙ СТАТУС: [ ] ✅ ЗАВЕРШЕНО
```

---

## ПРОБЛЕМА #5: ДИНАМИЧЕСКОЕ СОЗДАНИЕ ТАБЛИЦ

### Описание проблемы

**Текущее поведение**:
- Таблицы EventLogger создаются В ДВУХ МЕСТАХ:
  1. ✅ Миграция: `database/migrations/004_create_event_logger_tables.sql`
  2. ⚠️ Код: `core/event_logger.py:179-238` метод `_create_tables()`

**Проблемы текущего подхода**:
- ❌ Нарушение принципа единственного источника истины (Single Source of Truth)
- ❌ Риск расхождения схемы между миграцией и кодом
- ❌ Код берёт на себя ответственность за схему (плохая архитектура)
- ❌ Миграция 004 НЕ ПРИМЕНЕНА в продакшен базе
- ⚠️ Использование `CREATE TABLE IF NOT EXISTS` маскирует проблему

**Желаемое поведение**:
- ✅ Таблицы создаются ТОЛЬКО миграцией 004
- ✅ Код проверяет наличие таблиц, но НЕ создаёт их
- ✅ Чёткая ошибка если миграция не применена

**Риски исправления**:
- ⚠️ СРЕДНИЙ риск - если миграция 004 не применена и код удалён → бот не запустится
- ⚠️ Требует координации: сначала миграция, потом код
- ✅ Миграция неразрушающая (CREATE TABLE IF NOT EXISTS)

---

### ПЛАН ИСПРАВЛЕНИЯ ПРОБЛЕМЫ #5

#### ФАЗА 1: ПОДГОТОВКА (Оценка: 15 минут)

**Шаг 1.1: Проверить текущее состояние EventLogger таблиц**

```sql
-- Проверить существуют ли таблицы
SELECT
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'monitoring'
AND table_name IN ('events', 'transaction_log', 'event_performance_metrics')
ORDER BY table_name;

-- Ожидаемый результат: 3 строки (все таблицы существуют)
```

---

**Шаг 1.2: Проверить применена ли миграция 004**

```sql
-- Проверить запись в applied_migrations
SELECT *
FROM monitoring.applied_migrations
WHERE migration_file LIKE '%004%'
   OR migration_file LIKE '%event_logger%';

-- Ожидаемый результат: ПУСТО (миграция НЕ ПРИМЕНЕНА)
```

**КРИТИЧЕСКАЯ НАХОДКА**: Миграция 004 НЕ ПРИМЕНЕНА, но таблицы существуют (созданы кодом).

---

**Шаг 1.3: Сравнить определения таблиц (миграция vs база)**

```bash
# Экспортировать текущую структуру таблиц из базы
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema-only \
  --table=monitoring.events \
  --table=monitoring.transaction_log \
  --table=monitoring.event_performance_metrics \
  > /tmp/eventlogger_tables_current.sql

# Сравнить с миграцией 004
diff /tmp/eventlogger_tables_current.sql database/migrations/004_create_event_logger_tables.sql

# Проверить расхождения
```

**Цель**: Убедиться, что определения идентичны (нет расхождения схемы).

---

**Шаг 1.4: Проанализировать код event_logger.py**

```bash
# Найти все места, где вызывается _create_tables()
grep -n "_create_tables" /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/event_logger.py

# Ожидаемый результат:
# 172:            await self._create_tables()
# 179:    async def _create_tables(self):
```

**План изменений**:
1. Заменить `_create_tables()` на `_verify_tables()`
2. Новый метод проверяет существование, но НЕ создаёт
3. Выдаёт понятную ошибку если таблицы отсутствуют

---

**Шаг 1.5: Определить стратегию развёртывания**

**КРИТИЧЕСКИЙ ВОПРОС**: Миграция 004 НЕ ПРИМЕНЕНА. Что делать?

**Вариант A: Применить миграцию сейчас (БЕЗОПАСНО)**
- Миграция использует `CREATE TABLE IF NOT EXISTS`
- Таблицы уже существуют → миграция ничего не изменит
- Просто зарегистрирует миграцию как применённую
- ✅ РЕКОМЕНДУЕТСЯ

**Вариант B: Не применять миграцию (РИСКОВАННО)**
- Полагаться на то, что таблицы уже существуют
- Но нет записи в applied_migrations
- ❌ НЕ РЕКОМЕНДУЕТСЯ

**ВЫБОР**: Вариант A - применить миграцию 004 для регистрации.

---

#### ФАЗА 2: ПРИМЕНЕНИЕ МИГРАЦИИ 004 (Оценка: 10 минут)

**Шаг 2.1: Проверить файл миграции 004**

```bash
# Проверить существует ли файл
ls -lh database/migrations/004_create_event_logger_tables.sql

# Показать первые 50 строк
head -50 database/migrations/004_create_event_logger_tables.sql
```

**Критерий успеха**: Файл существует и содержит `CREATE TABLE IF NOT EXISTS`.

---

**Шаг 2.2: Создать бэкап перед применением**

```bash
# ОБЯЗАТЕЛЬНЫЙ ШАГ
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto -F c -b -v -f /tmp/fox_crypto_backup_before_004_$(date +%Y%m%d_%H%M%S).backup

# Проверить
ls -lh /tmp/fox_crypto_backup_before_004_*.backup
```

---

**Шаг 2.3: Применить миграцию 004 (на продакшен)**

```bash
# Применить миграцию
# Таблицы уже существуют → миграция просто их пропустит
psql -h localhost -p 5433 -U elcrypto -d fox_crypto -f database/migrations/004_create_event_logger_tables.sql

# Проверить exit code
echo $?  # Должно быть 0
```

**Ожидаемый вывод**:
```
NOTICE:  relation "events" already exists, skipping
NOTICE:  relation "transaction_log" already exists, skipping
NOTICE:  relation "event_performance_metrics" already exists, skipping
NOTICE:  ✅ Migration 004 completed successfully!
```

---

**Шаг 2.4: Верификация применения миграции 004**

```sql
-- Проверить что миграция зарегистрирована
-- ВАЖНО: Миграция 004 должна САМА записать себя в applied_migrations

-- Если таблицы applied_migrations нет в миграции 004, записать вручную:
INSERT INTO monitoring.applied_migrations (migration_file, applied_at)
VALUES ('004_create_event_logger_tables.sql', NOW())
ON CONFLICT DO NOTHING;

-- Проверить
SELECT * FROM monitoring.applied_migrations
WHERE migration_file LIKE '%004%';

-- Ожидаемый результат: 1 строка с migration_file = '004_create_event_logger_tables.sql'
```

---

#### ФАЗА 3: ИЗМЕНЕНИЕ КОДА EVENT_LOGGER.PY (Оценка: 20 минут)

**КРИТИЧЕСКИ ВАЖНО**: Код можно менять ТОЛЬКО ПОСЛЕ применения миграции 004!

**Шаг 3.1: Создать новый метод _verify_tables()**

**Создать файл**: `/tmp/event_logger_verify_tables.py` (для проверки перед применением)

```python
async def _verify_tables(self):
    """
    Verify that EventLogger tables exist in database.

    Tables MUST be created by migration 004_create_event_logger_tables.sql
    This method does NOT create tables - it only verifies their existence.

    Raises:
        RuntimeError: If any required table is missing
    """
    required_tables = [
        'events',
        'transaction_log',
        'event_performance_metrics'
    ]

    async with self.pool.acquire() as conn:
        # Check table existence
        result = await conn.fetchval("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            AND table_name = ANY($1)
        """, required_tables)

        if result != len(required_tables):
            # Find which tables are missing
            existing_tables = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'monitoring'
                AND table_name = ANY($1)
            """, required_tables)

            existing_names = {row['table_name'] for row in existing_tables}
            missing_tables = set(required_tables) - existing_names

            error_msg = (
                f"EventLogger tables missing: {', '.join(missing_tables)}\n"
                f"Required tables: {', '.join(required_tables)}\n"
                f"Found tables: {', '.join(existing_names) if existing_names else 'NONE'}\n"
                f"\n"
                f"SOLUTION: Run database migration first:\n"
                f"  psql -h localhost -p 5433 -U elcrypto -d fox_crypto \\\n"
                f"    -f database/migrations/004_create_event_logger_tables.sql\n"
                f"\n"
                f"EventLogger tables must be created by migration, not by code."
            )

            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # All tables exist - log success
        logger.info(
            f"EventLogger table verification passed: "
            f"{', '.join(required_tables)} exist in monitoring schema"
        )

        # Optional: Verify table structure (column count)
        # This is a sanity check to detect schema drift
        table_columns = {}
        for table in required_tables:
            column_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'monitoring'
                AND table_name = $1
            """, table)
            table_columns[table] = column_count

        logger.debug(f"EventLogger table column counts: {table_columns}")

        # Expected column counts (from migration 004)
        expected_columns = {
            'events': 12,  # id, event_type, event_data, correlation_id, position_id, order_id, symbol, exchange, severity, error_message, stack_trace, created_at
            'transaction_log': 9,  # id, transaction_id, operation, status, started_at, completed_at, duration_ms, affected_rows, error_message
            'event_performance_metrics': 5  # id, metric_name, metric_value, tags, recorded_at
        }

        for table, expected_count in expected_columns.items():
            actual_count = table_columns[table]
            if actual_count != expected_count:
                logger.warning(
                    f"Table monitoring.{table} has {actual_count} columns, "
                    f"expected {expected_count}. Schema may have drifted."
                )
```

---

**Шаг 3.2: План изменений в event_logger.py**

**Файл**: `core/event_logger.py`

**Изменение 1: Заменить вызов _create_tables() на _verify_tables()**

```python
# БЫЛО (строка 172):
await self._create_tables()

# СТАНЕТ:
await self._verify_tables()
```

**Изменение 2: Удалить метод _create_tables() целиком**

```python
# УДАЛИТЬ СТРОКИ 179-238 (весь метод _create_tables)
# async def _create_tables(self):
#     """Create event logging tables if not exists"""
#     ...
#     # 59 строк SQL кода
```

**Изменение 3: Добавить новый метод _verify_tables()**

```python
# ДОБАВИТЬ новый метод (см. код выше в Шаге 3.1)
```

---

**Шаг 3.3: Создать файл с изменениями (для ревью)**

```bash
# Создать патч-файл с планируемыми изменениями
cat > /tmp/event_logger_fix_issue5.patch <<'EOF'
--- a/core/event_logger.py
+++ b/core/event_logger.py
@@ -169,7 +169,7 @@ class EventLogger:
     async def initialize(self):
         """Initialize event logger and create tables if needed"""
         try:
-            await self._create_tables()
+            await self._verify_tables()
             self._worker_task = asyncio.create_task(self._event_worker())
             logger.info("EventLogger initialized")
         except Exception as e:
@@ -177,70 +177,68 @@ class EventLogger:
             raise

-    async def _create_tables(self):
-        """Create event logging tables if not exists"""
+    async def _verify_tables(self):
+        """
+        Verify that EventLogger tables exist in database.
+
+        Tables MUST be created by migration 004_create_event_logger_tables.sql
+        This method does NOT create tables - it only verifies their existence.
+
+        Raises:
+            RuntimeError: If any required table is missing
+        """
+        required_tables = [
+            'events',
+            'transaction_log',
+            'event_performance_metrics'
+        ]
+
         async with self.pool.acquire() as conn:
-            # Events table
-            await conn.execute("""
-                CREATE TABLE IF NOT EXISTS monitoring.events (
-                    id SERIAL PRIMARY KEY,
-                    event_type VARCHAR(50) NOT NULL,
-                    event_data JSONB,
-                    correlation_id VARCHAR(100),
-                    position_id INTEGER,
-                    order_id VARCHAR(100),
-                    symbol VARCHAR(50),
-                    exchange VARCHAR(50),
-                    severity VARCHAR(20) DEFAULT 'INFO',
-                    error_message TEXT,
-                    stack_trace TEXT,
-                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-                )
-            """)
-
-            # Create indexes separately
-            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON monitoring.events (event_type)")
-            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_correlation ON monitoring.events (correlation_id)")
-            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_position ON monitoring.events (position_id)")
-            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_created ON monitoring.events (created_at DESC)")
-
-            # Transaction log table
-            await conn.execute("""
-                CREATE TABLE IF NOT EXISTS monitoring.transaction_log (
-                    id SERIAL PRIMARY KEY,
-                    transaction_id VARCHAR(100) UNIQUE,
-                    operation VARCHAR(100),
-                    status VARCHAR(20),
-                    started_at TIMESTAMP WITH TIME ZONE,
-                    completed_at TIMESTAMP WITH TIME ZONE,
-                    duration_ms INTEGER,
-                    affected_rows INTEGER,
-                    error_message TEXT
-                )
+            # Check table existence
+            result = await conn.fetchval("""
+                SELECT COUNT(*)
+                FROM information_schema.tables
+                WHERE table_schema = 'monitoring'
+                AND table_name = ANY($1)
+            """, required_tables)
+
+            if result != len(required_tables):
+                # Find which tables are missing
+                existing_tables = await conn.fetch("""
+                    SELECT table_name
+                    FROM information_schema.tables
+                    WHERE table_schema = 'monitoring'
+                    AND table_name = ANY($1)
+                """, required_tables)
+
+                existing_names = {row['table_name'] for row in existing_tables}
+                missing_tables = set(required_tables) - existing_names
+
+                error_msg = (
+                    f"EventLogger tables missing: {', '.join(missing_tables)}\n"
+                    f"Required tables: {', '.join(required_tables)}\n"
+                    f"Found tables: {', '.join(existing_names) if existing_names else 'NONE'}\n"
+                    f"\n"
+                    f"SOLUTION: Run database migration first:\n"
+                    f"  psql -h localhost -p 5433 -U elcrypto -d fox_crypto \\\n"
+                    f"    -f database/migrations/004_create_event_logger_tables.sql\n"
+                    f"\n"
+                    f"EventLogger tables must be created by migration, not by code."
+                )
+
+                logger.error(error_msg)
+                raise RuntimeError(error_msg)
+
+            # All tables exist - log success
+            logger.info(
+                f"EventLogger table verification passed: "
+                f"{', '.join(required_tables)} exist in monitoring schema"
+            )
+EOF

# Показать патч для ревью
cat /tmp/event_logger_fix_issue5.patch
```

---

**Шаг 3.4: Код-ревью изменений**

**ЧЕК-ЛИСТ ДЛЯ РЕВЬЮ**:
```
[ ] Метод _create_tables() полностью удалён (59 строк SQL)
[ ] Новый метод _verify_tables() добавлен
[ ] Вызов в initialize() изменён с _create_tables() на _verify_tables()
[ ] _verify_tables() проверяет 3 таблицы: events, transaction_log, event_performance_metrics
[ ] _verify_tables() выдаёт понятную ошибку с инструкциями если таблицы отсутствуют
[ ] _verify_tables() логирует успех если все таблицы существуют
[ ] Нет других мест в коде, где создаются таблицы
[ ] Комментарии обновлены (ссылка на миграцию 004)
```

---

#### ФАЗА 4: ТЕСТИРОВАНИЕ ИЗМЕНЕНИЙ КОДА (Оценка: 30 минут)

**КРИТИЧЕСКИ ВАЖНО**: НЕ применять на продакшен без тестирования!

**Шаг 4.1: Тестирование на тестовой базе С таблицами**

```bash
# Создать тестовую базу с таблицами EventLogger
psql -h localhost -p 5433 -U elcrypto -c "CREATE DATABASE fox_crypto_test_with_tables TEMPLATE fox_crypto;"

# Применить изменения в коде (на отдельной ветке git)
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Создать ветку для тестирования
git checkout -b fix/issue5-remove-dynamic-table-creation

# Применить изменения в core/event_logger.py
# (ПОКА НЕ ДЕЛАТЬ - ТОЛЬКО ПЛАН!)

# Запустить бота на тестовой базе
DB_NAME=fox_crypto_test_with_tables python main.py

# Проверить логи
tail -f /tmp/bot_test.log | grep -i eventlogger
```

**Ожидаемый лог**:
```
INFO - EventLogger table verification passed: events, transaction_log, event_performance_metrics exist in monitoring schema
INFO - EventLogger initialized
```

**Критерий успеха**:
- ✅ Лог показывает "table verification passed"
- ✅ Бот инициализируется без ошибок
- ✅ EventLogger пишет события в базу

---

**Шаг 4.2: Тестирование на пустой тестовой базе (негативный тест)**

```bash
# Создать пустую тестовую базу БЕЗ таблиц EventLogger
psql -h localhost -p 5433 -U elcrypto -c "CREATE DATABASE fox_crypto_test_empty;"

# Создать только схему monitoring, но БЕЗ таблиц
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test_empty -c "CREATE SCHEMA IF NOT EXISTS monitoring;"

# Запустить бота на пустой базе
DB_NAME=fox_crypto_test_empty python main.py

# Проверить логи
tail -f /tmp/bot_test.log | grep -i eventlogger
```

**Ожидаемый лог (ОШИБКА)**:
```
ERROR - EventLogger tables missing: events, transaction_log, event_performance_metrics
ERROR - Required tables: events, transaction_log, event_performance_metrics
ERROR - Found tables: NONE
ERROR -
ERROR - SOLUTION: Run database migration first:
ERROR -   psql -h localhost -p 5433 -U elcrypto -d fox_crypto \
ERROR -     -f database/migrations/004_create_event_logger_tables.sql
ERROR -
ERROR - EventLogger tables must be created by migration, not by code.
CRITICAL - EventLogger initialization failed: EventLogger tables missing: ...
```

**Критерий успеха**:
- ✅ Бот НЕ запускается (выходит с ошибкой)
- ✅ Ошибка понятная и содержит инструкции по исправлению
- ✅ Не создаются таблицы автоматически

---

**Шаг 4.3: Тестирование применения миграции после ошибки**

```bash
# Применить миграцию 004 на пустую базу
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test_empty -f database/migrations/004_create_event_logger_tables.sql

# Запустить бота снова
DB_NAME=fox_crypto_test_empty python main.py

# Проверить логи
tail -f /tmp/bot_test.log | grep -i eventlogger
```

**Ожидаемый лог**:
```
INFO - EventLogger table verification passed: events, transaction_log, event_performance_metrics exist in monitoring schema
INFO - EventLogger initialized
```

**Критерий успеха**:
- ✅ После применения миграции бот запускается успешно
- ✅ Верификация проходит
- ✅ События пишутся в базу

---

**Шаг 4.4: Тестирование работы EventLogger**

```bash
# Запустить бота на 10 минут
DB_NAME=fox_crypto_test_with_tables python main.py &
BOT_PID=$!

# Подождать 10 минут
sleep 600

# Остановить бота
kill $BOT_PID

# Проверить что события записались
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test_with_tables -c "
    SELECT
        COUNT(*) as event_count,
        COUNT(DISTINCT event_type) as event_types,
        MIN(created_at) as first_event,
        MAX(created_at) as last_event
    FROM monitoring.events;
"
```

**Критерий успеха**:
- ✅ event_count > 0 (события записались)
- ✅ event_types > 1 (разные типы событий)
- ✅ Временной диапазон ~10 минут

---

#### ФАЗА 5: ПРИМЕНЕНИЕ ИЗМЕНЕНИЙ КОДА НА ПРОДАКШЕН (Оценка: 15 минут)

**ПРЕДВАРИТЕЛЬНЫЕ УСЛОВИЯ**:
- ✅ Миграция 004 применена на продакшен базе (Фаза 2)
- ✅ Все тесты пройдены успешно (Фаза 4)
- ✅ Код-ревью завершён

---

**Шаг 5.1: Создать бэкап кода**

```bash
# Создать коммит с текущим состоянием (до изменений)
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot
git add -A
git commit -m "CHECKPOINT: Before removing dynamic table creation (Issue #5)"

# Создать тег для возможности отката
git tag checkpoint-before-issue5-fix

# Создать ветку для изменений
git checkout -b fix/issue5-remove-dynamic-table-creation
```

---

**Шаг 5.2: Применить изменения в core/event_logger.py**

```bash
# ВНИМАНИЕ: На этом этапе ТОЛЬКО ПЛАН - НЕ ДЕЛАТЬ!
#
# Когда будете готовы применять:
# 1. Открыть файл core/event_logger.py
# 2. Строка 172: заменить await self._create_tables() на await self._verify_tables()
# 3. Строки 179-238: УДАЛИТЬ весь метод _create_tables()
# 4. Добавить новый метод _verify_tables() (см. код в Шаге 3.1)
# 5. Сохранить файл
```

---

**Шаг 5.3: Создать коммит с изменениями**

```bash
# После применения изменений
git add core/event_logger.py
git commit -m "🔧 FIX: Remove dynamic table creation from EventLogger (Issue #5)

- Replaced _create_tables() with _verify_tables()
- Tables now MUST be created by migration 004
- Code only verifies table existence, does not create them
- Clear error message if migration not applied
- Improves separation of concerns (schema in migrations, not code)

Related: DATABASE_AUDIT_FINAL_REPORT_RU.md Issue #5
Migration: database/migrations/004_create_event_logger_tables.sql"

# Показать изменения
git show
```

---

**Шаг 5.4: Остановить бота**

```bash
# Найти PID бота
ps aux | grep "python.*main.py"

# Остановить бота
kill <PID>

# Подождать остановки (graceful shutdown)
sleep 5

# Проверить что остановлен
ps aux | grep "python.*main.py"
```

---

**Шаг 5.5: Развернуть изменения кода**

```bash
# Переключиться на ветку с изменениями
git checkout fix/issue5-remove-dynamic-table-creation

# Проверить что изменения применены
git diff checkpoint-before-issue5-fix..HEAD core/event_logger.py

# Должны видеть:
# - Удалено: async def _create_tables(self):
# - Удалено: ~59 строк SQL кода
# - Добавлено: async def _verify_tables(self):
# - Изменено: await self._create_tables() → await self._verify_tables()
```

---

**Шаг 5.6: Запустить бота**

```bash
# Запустить бота
python main.py &

# Сразу мониторить логи
tail -f /tmp/bot_verification.log | grep -A 5 -B 5 EventLogger
```

**Ожидаемый лог**:
```
INFO - EventLogger table verification passed: events, transaction_log, event_performance_metrics exist in monitoring schema
INFO - EventLogger initialized
INFO - EventLogger wrote 2 events to DB (count_before=1732, count_after=1734, delta=2)
```

**Критерий успеха**:
- ✅ "table verification passed"
- ✅ EventLogger initialized
- ✅ События пишутся в базу

---

**Шаг 5.7: Верификация работы бота (первые 30 минут)**

```bash
# Мониторить логи на ошибки
tail -f /tmp/bot_verification.log | grep -i error

# Через 10 минут: проверить что события пишутся
psql -h localhost -p 5433 -U elcrypto -d fox_crypto -c "
    SELECT
        COUNT(*) as total_events,
        COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '10 minutes') as recent_events,
        MAX(created_at) as last_event
    FROM monitoring.events;
"

# Ожидаемый результат:
# recent_events > 0 (новые события появляются)
# last_event близко к текущему времени
```

---

**Шаг 5.8: Мерж изменений в main ветку**

```bash
# ТОЛЬКО ПОСЛЕ успешной верификации!

# Переключиться на main
git checkout main

# Мерж ветки с фиксом
git merge fix/issue5-remove-dynamic-table-creation

# Создать тег версии
git tag fix-issue5-applied-$(date +%Y%m%d)

# Опционально: запушить в remote
# git push origin main
# git push origin --tags
```

---

#### ФАЗА 6: ДОКУМЕНТАЦИЯ (Оценка: 10 минут)

**Шаг 6.1: Обновить README миграций**

Добавить в `database/migrations/README.md`:

```markdown
## Migration 004: Create EventLogger Tables

**Date**: 2025-10-14
**Status**: ✅ Applied
**Applied at**: 2025-10-14 HH:MM:SS

### Changes
- Created table `monitoring.events` (12 columns)
- Created table `monitoring.transaction_log` (9 columns)
- Created table `monitoring.event_performance_metrics` (5 columns)
- Created 8 indexes for query performance

### Impact
- EventLogger tables now created by migration (not by code)
- Single source of truth for schema definition
- Code only verifies table existence

### Related Changes
- **Issue #5**: Removed dynamic table creation from `core/event_logger.py`
- Method `_create_tables()` replaced with `_verify_tables()`

### Rollback
```sql
-- See database/migrations/004_create_event_logger_tables.sql for rollback instructions
```
```

---

**Шаг 6.2: Обновить комментарии в event_logger.py**

Добавить в docstring класса EventLogger:

```python
class EventLogger:
    """
    Centralized event logging system for trading bot operations.

    This class provides comprehensive audit trail for all critical bot operations:
    - Position lifecycle (created, updated, closed)
    - Order execution (placed, filled, cancelled)
    - Stop-loss operations (placed, triggered, updated)
    - System events (startup, shutdown, errors)
    - Signal processing (waves, signals, execution)

    **IMPORTANT**: EventLogger tables MUST be created by database migration first:
        database/migrations/004_create_event_logger_tables.sql

    This class does NOT create tables dynamically. It only verifies their existence
    and raises clear error if migration was not applied.

    Architecture:
    - Batch writing: Events queued and written in batches (100 events or 5 sec)
    - Async operation: Non-blocking event logging via asyncio Queue
    - Connection pooling: Uses asyncpg connection pool from repository
    - Error resilience: Failed writes logged but don't crash bot

    Tables:
    - monitoring.events: Main audit trail (all event types)
    - monitoring.transaction_log: Database transaction tracking (future use)
    - monitoring.event_performance_metrics: Performance metrics (future use)
    """
```

---

**Шаг 6.3: Создать запись в changelog**

Создать файл `CHANGELOG_ISSUE5.md`:

```markdown
# Fix Issue #5: Remove Dynamic Table Creation from EventLogger

**Date**: 2025-10-14
**Issue**: Database Audit Report - Problem #5
**Impact**: Architecture improvement, no user-facing changes

## Summary

Removed redundant dynamic table creation from `core/event_logger.py`.
EventLogger tables are now created ONLY by database migration 004.

## Changes

### Database
- ✅ Applied migration `004_create_event_logger_tables.sql`
- ✅ Registered migration in `monitoring.applied_migrations`

### Code
- ✅ Removed method `_create_tables()` from `core/event_logger.py` (59 lines)
- ✅ Added method `_verify_tables()` with clear error messages
- ✅ Updated `initialize()` to call `_verify_tables()` instead

## Benefits

1. **Single Source of Truth**: Schema defined only in migrations
2. **Reduced Code Complexity**: -59 lines of SQL in Python code
3. **Better Error Messages**: Clear instructions if migration missing
4. **Cleaner Architecture**: Separation of concerns (schema vs logic)

## Migration Guide

If deploying to new environment:

1. Apply migration first:
   ```bash
   psql -h localhost -p 5433 -U elcrypto -d fox_crypto \
     -f database/migrations/004_create_event_logger_tables.sql
   ```

2. Then start bot:
   ```bash
   python main.py
   ```

If migration not applied, bot will fail with clear error message.

## Rollback

If needed to rollback code changes:

```bash
git checkout checkpoint-before-issue5-fix
```

If needed to rollback migration:

```bash
psql -h localhost -p 5433 -U elcrypto -d fox_crypto <<EOF
DROP TABLE IF EXISTS monitoring.events CASCADE;
DROP TABLE IF EXISTS monitoring.transaction_log CASCADE;
DROP TABLE IF EXISTS monitoring.event_performance_metrics CASCADE;
EOF
```

## Testing

- ✅ Tested on database with tables: Bot starts successfully
- ✅ Tested on empty database: Bot fails with clear error
- ✅ Tested EventLogger functionality: Events written correctly
- ✅ Verified no performance impact

## Related Documents

- `DATABASE_AUDIT_FINAL_REPORT_RU.md` - Section "Проблема #5"
- `database/migrations/004_create_event_logger_tables.sql`
- `SAFE_FIX_PLAN_ISSUES_4_5.md`
```

---

### ИТОГОВЫЙ ЧЕК-ЛИСТ ПРОБЛЕМЫ #5

```
Подготовка:
[ ] Шаг 1.1: Проверено состояние EventLogger таблиц
[ ] Шаг 1.2: Проверена миграция 004 (НЕ ПРИМЕНЕНА)
[ ] Шаг 1.3: Сравнены определения таблиц (идентичны)
[ ] Шаг 1.4: Проанализирован код event_logger.py
[ ] Шаг 1.5: Выбрана стратегия (Вариант A - применить миграцию)

Применение миграции 004:
[ ] Шаг 2.1: Проверен файл миграции 004
[ ] Шаг 2.2: Создан бэкап перед применением
[ ] Шаг 2.3: Миграция 004 применена на продакшен
[ ] Шаг 2.4: Верификация применения миграции 004

Изменение кода:
[ ] Шаг 3.1: Создан новый метод _verify_tables()
[ ] Шаг 3.2: Определён план изменений
[ ] Шаг 3.3: Создан патч-файл для ревью
[ ] Шаг 3.4: Код-ревью завершён успешно

Тестирование:
[ ] Шаг 4.1: Тест на базе С таблицами (успешно)
[ ] Шаг 4.2: Негативный тест на пустой базе (ошибка ожидаемая)
[ ] Шаг 4.3: Тест после применения миграции (успешно)
[ ] Шаг 4.4: Тестирование работы EventLogger

Применение на продакшен:
[ ] Шаг 5.1: Создан бэкап кода (git checkpoint)
[ ] Шаг 5.2: Изменения применены в event_logger.py
[ ] Шаг 5.3: Создан git коммит с изменениями
[ ] Шаг 5.4: Бот остановлен
[ ] Шаг 5.5: Изменения развёрнуты
[ ] Шаг 5.6: Бот запущен успешно
[ ] Шаг 5.7: Верификация работы (30 минут)
[ ] Шаг 5.8: Изменения смержены в main

Документация:
[ ] Шаг 6.1: Обновлён README миграций
[ ] Шаг 6.2: Обновлены комментарии в коде
[ ] Шаг 6.3: Создан CHANGELOG

ОБЩИЙ СТАТУС: [ ] ✅ ЗАВЕРШЕНО
```

---

## ПОРЯДОК ВЫПОЛНЕНИЯ ИСПРАВЛЕНИЙ

### Рекомендуемая последовательность

**ВАРИАНТ 1: Последовательное выполнение** (Рекомендуется)

```
День 1:
  Утро:  Проблема #4 - Фазы 1-3 (Подготовка + Создание + Тестирование)
  Вечер: Проблема #4 - Фазы 4-5 (Применение + Документация)

День 2:
  Утро:  Проблема #5 - Фазы 1-2 (Подготовка + Миграция 004)
  Вечер: Проблема #5 - Фазы 3-4 (Изменение кода + Тестирование)

День 3:
  Утро:  Проблема #5 - Фазы 5-6 (Применение + Документация)
  Вечер: Финальная верификация обеих проблем
```

**Обоснование**: Проблемы независимы, можно исправлять поочерёдно.

---

**ВАРИАНТ 2: Одновременное выполнение** (Для опытных)

```
День 1:
  Шаг 1: Подготовка обеих проблем параллельно
  Шаг 2: Создание миграций (005 и 004)
  Шаг 3: Тестирование миграций на тестовой базе

День 2:
  Шаг 4: Применение миграций на продакшен
  Шаг 5: Изменение кода event_logger.py (Issue #5)
  Шаг 6: Тестирование изменений кода

День 3:
  Шаг 7: Применение изменений кода на продакшен
  Шаг 8: Финальная верификация
  Шаг 9: Документация
```

**Обоснование**: Быстрее, но требует внимательности.

---

### Зависимости между исправлениями

```
Проблема #4 (Триггеры)          Проблема #5 (Таблицы)
        │                                │
        │                                │
    Миграция 005                    Миграция 004
        │                                │
        │                                ↓
        │                         Изменение кода
        │                         event_logger.py
        │                                │
        └────────────────┬───────────────┘
                         ↓
                Финальная верификация
```

**Важно**:
- ✅ Проблемы НЕЗАВИСИМЫ - можно исправлять в любом порядке
- ✅ Миграция 004 ДОЛЖНА быть применена ДО изменения кода event_logger.py
- ✅ Миграция 005 может быть применена в любой момент (независимо от #5)

---

## ПЛАН ОТКАТА (ROLLBACK PLAN)

### Откат проблемы #4 (Триггеры updated_at)

**Сценарий**: Триггеры вызывают проблемы, нужно откатить.

**Шаг 1: Удалить триггеры**

```sql
BEGIN;

-- Удалить все триггеры
DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;
DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;
DROP TRIGGER IF EXISTS update_orders_updated_at ON monitoring.orders;
DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;

-- Удалить функцию триггера
DROP FUNCTION IF EXISTS public.update_updated_at_column();

-- Удалить колонку updated_at из protection_events (если была добавлена)
ALTER TABLE monitoring.protection_events DROP COLUMN IF EXISTS updated_at;

COMMIT;
```

**Шаг 2: Удалить запись о миграции**

```sql
DELETE FROM monitoring.applied_migrations
WHERE migration_file = '005_add_updated_at_triggers.sql';
```

**Шаг 3: Верификация**

```sql
-- Проверить что триггеров нет
SELECT COUNT(*) FROM information_schema.triggers
WHERE trigger_schema = 'monitoring'
AND trigger_name LIKE '%updated_at%';

-- Ожидаемый результат: 0
```

**Шаг 4: Перезапустить бота**

```bash
# Бот продолжит работать как раньше (updated_at не обновляется автоматически)
```

**Восстановление из бэкапа** (если что-то пошло совсем не так):

```bash
# Восстановить из бэкапа
pg_restore -h localhost -p 5433 -U elcrypto -d fox_crypto --clean /tmp/fox_crypto_backup_before_005_*.backup
```

---

### Откат проблемы #5 (Динамическое создание таблиц)

**Сценарий**: Изменения кода вызвали проблемы, нужно откатить.

**Шаг 1: Откатить изменения кода в git**

```bash
# Переключиться на чекпоинт ДО изменений
git checkout checkpoint-before-issue5-fix

# Или откатить коммит
git revert <commit-hash-of-issue5-fix>

# Или хард ресет (ОПАСНО - потеряете незакоммиченные изменения)
git reset --hard checkpoint-before-issue5-fix
```

**Шаг 2: Перезапустить бота**

```bash
# Остановить бота
kill <PID>

# Запустить со старым кодом
python main.py
```

**Шаг 3: Верификация**

```bash
# Проверить что бот работает
tail -f /tmp/bot_verification.log | grep EventLogger

# Должны видеть:
# "EventLogger initialized" (без "table verification passed")
```

**Откат миграции 004** (НЕ РЕКОМЕНДУЕТСЯ - может удалить данные):

```sql
-- ОСТОРОЖНО: Это удалит все события из EventLogger!
BEGIN;
DROP TABLE IF EXISTS monitoring.events CASCADE;
DROP TABLE IF EXISTS monitoring.transaction_log CASCADE;
DROP TABLE IF EXISTS monitoring.event_performance_metrics CASCADE;
DELETE FROM monitoring.applied_migrations WHERE migration_file = '004_create_event_logger_tables.sql';
COMMIT;
```

**ВАЖНО**: Откат миграции 004 нежелателен, т.к. удалит данные событий.
Лучше откатить только код, оставив таблицы в базе.

---

## ЧЕК-ЛИСТЫ ВЕРИФИКАЦИИ

### Финальный чек-лист ПРОБЛЕМЫ #4

```
ДО ПРИМЕНЕНИЯ:
[ ] Создан бэкап продакшен базы
[ ] Миграция 005 протестирована на тестовой базе
[ ] Функциональное тестирование пройдено
[ ] Нагрузочное тестирование приемлемо
[ ] Тестирование с ботом успешно

ПОСЛЕ ПРИМЕНЕНИЯ:
[ ] Миграция 005 применена без ошибок
[ ] 4 триггера созданы (positions, trades, orders, protection_events)
[ ] Функция public.update_updated_at_column() создана
[ ] Колонка protection_events.updated_at добавлена
[ ] Запись в applied_migrations создана
[ ] Бот запущен успешно
[ ] updated_at обновляется автоматически при UPDATE
[ ] Нет ошибок в логах (первые 24 часа)
[ ] Производительность приемлемая
[ ] Документация обновлена

КРИТЕРИЙ УСПЕХА:
✅ updated_at автоматически обновляется при любом UPDATE
✅ Overhead < 1ms на UPDATE
✅ Бот работает стабильно 24+ часов
```

---

### Финальный чек-лист ПРОБЛЕМЫ #5

```
ДО ПРИМЕНЕНИЯ:
[ ] Миграция 004 применена на продакшен базе
[ ] Миграция 004 зарегистрирована в applied_migrations
[ ] EventLogger таблицы существуют в базе
[ ] Создан бэкап кода (git checkpoint)
[ ] Изменения протестированы на тестовой базе
[ ] Негативный тест пройден (ошибка на пустой базе)
[ ] Код-ревью завершён

ПОСЛЕ ПРИМЕНЕНИЯ:
[ ] Метод _create_tables() удалён из event_logger.py
[ ] Метод _verify_tables() добавлен
[ ] Вызов в initialize() изменён
[ ] Git коммит создан
[ ] Бот запущен успешно
[ ] Лог показывает "table verification passed"
[ ] EventLogger пишет события в базу
[ ] Нет ошибок в логах (первые 30 минут)
[ ] Изменения смержены в main ветку
[ ] Документация обновлена
[ ] CHANGELOG создан

КРИТЕРИЙ УСПЕХА:
✅ Таблицы создаются ТОЛЬКО миграцией
✅ Код только проверяет существование таблиц
✅ Понятная ошибка если миграция не применена
✅ Бот работает стабильно без изменений функциональности
```

---

## КОНТАКТНАЯ ИНФОРМАЦИЯ И РЕСУРСЫ

### Файлы для исправления

**Проблема #4**:
- `database/migrations/005_add_updated_at_triggers.sql` (создать)

**Проблема #5**:
- `database/migrations/004_create_event_logger_tables.sql` (применить)
- `core/event_logger.py:172` (изменить вызов)
- `core/event_logger.py:179-238` (удалить метод)
- `core/event_logger.py` (добавить новый метод _verify_tables)

### Бэкапы

```
/tmp/fox_crypto_backup_before_005_YYYYMMDD_HHMMSS.backup  - Перед миграцией 005
/tmp/fox_crypto_backup_before_004_YYYYMMDD_HHMMSS.backup  - Перед миграцией 004
```

### Git теги для отката

```
checkpoint-before-issue5-fix      - Точка до изменений Issue #5
fix-issue5-applied-YYYYMMDD       - Точка после применения Issue #5
```

### Логи для мониторинга

```
/tmp/bot_verification.log         - Логи бота после применения изменений
/tmp/bot_test.log                 - Логи бота на тестовой базе
```

---

## ОЦЕНКА ВРЕМЕНИ И РИСКОВ

### Время выполнения

| Проблема | Фаза | Оценка времени |
|----------|------|----------------|
| #4 | Подготовка | 10 минут |
| #4 | Создание миграции | 20 минут |
| #4 | Тестирование | 30 минут |
| #4 | Применение | 15 минут |
| #4 | Документация | 10 минут |
| **#4 ИТОГО** | | **~1.5 часа** |
| | | |
| #5 | Подготовка | 15 минут |
| #5 | Миграция 004 | 10 минут |
| #5 | Изменение кода | 20 минут |
| #5 | Тестирование | 30 минут |
| #5 | Применение | 15 минут |
| #5 | Документация | 10 минут |
| **#5 ИТОГО** | | **~1.5 часа** |
| | | |
| **ОБЩЕЕ ВРЕМЯ** | | **~3 часа** |

*Плюс 24 часа мониторинга после применения*

---

### Оценка рисков

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Триггеры замедляют UPDATE | Низкая | Низкое | Нагрузочное тестирование, можно откатить |
| Миграция 004 не применится | Очень низкая | Среднее | Таблицы уже существуют, IF NOT EXISTS |
| Бот не запустится после изменений кода | Низкая | Высокое | Тестирование на dev базе, git checkpoint |
| Потеря данных при откате | Очень низкая | Высокое | Обязательные бэкапы перед применением |
| Расхождение схемы миграция/код | Низкая | Среднее | Сравнение определений, верификация |

**Общая оценка рисков**: 🟢 НИЗКИЙ

---

## ЗАКЛЮЧЕНИЕ

Этот план обеспечивает:

✅ **Безопасность**: Множественные бэкапы, тестирование, возможность отката
✅ **Прозрачность**: Детальные шаги с ожидаемыми результатами
✅ **Верифицируемость**: Чек-листы и критерии успеха
✅ **Документированность**: Подробное описание каждого изменения
✅ **Обратимость**: Чёткие инструкции по откату

**КРИТИЧЕСКИ ВАЖНО**: Это ТОЛЬКО ПЛАН. НЕ вносить изменения без явного подтверждения.

---

**Дата создания плана**: 2025-10-14
**Статус**: ✅ ПЛАН ГОТОВ К РЕВЬЮ
**Готовность к применению**: ⏸️ ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ
