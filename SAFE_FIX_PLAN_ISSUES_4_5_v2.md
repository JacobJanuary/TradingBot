# ДЕТАЛЬНЫЙ И БЕЗОПАСНЫЙ ПЛАН ИСПРАВЛЕНИЯ ПРОБЛЕМ #4 И #5
## База данных: fox_crypto, Схема: monitoring

Дата создания плана: 2025-10-14 (обновлено)
Статус: **ТОЛЬКО ПЛАН - БЕЗ ИЗМЕНЕНИЙ КОДА**
Версия: 2.0 (оптимизированы бэкапы - только схема monitoring)

---

## ВАЖНОЕ УТОЧНЕНИЕ ПО БЭКАПАМ

**КРИТИЧЕСКИ ВАЖНО**: Мы работаем ТОЛЬКО со схемой `monitoring`.

**НЕ НУЖНО** бэкапить всю базу fox_crypto (может быть сотни ГБ).

**ПРАВИЛЬНЫЙ ПОДХОД**:
- Бэкапить только схему `monitoring` (~десятки МБ)
- Создавать тестовые копии только схемы `monitoring`
- Быстрее, эффективнее, безопаснее

---

## ОГЛАВЛЕНИЕ

1. [Правильные команды бэкапа](#правильные-команды-бэкапа)
2. [Текущее состояние системы](#текущее-состояние-системы)
3. [Проблема #4: Триггеры updated_at](#проблема-4-триггеры-updated_at)
4. [Проблема #5: Динамическое создание таблиц](#проблема-5-динамическое-создание-таблиц)
5. [Порядок выполнения исправлений](#порядок-выполнения-исправлений)
6. [План отката (Rollback Plan)](#план-отката-rollback-plan)
7. [Чек-листы верификации](#чек-листы-верификации)

---

## ПРАВИЛЬНЫЕ КОМАНДЫ БЭКАПА

### Бэкап только схемы monitoring (ПРАВИЛЬНО ✅)

```bash
# Полный бэкап схемы monitoring (структура + данные)
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema=monitoring \
  -F c -b -v \
  -f /tmp/monitoring_schema_backup_$(date +%Y%m%d_%H%M%S).backup

# Проверить размер (должно быть ~десятки МБ, не сотни ГБ)
ls -lh /tmp/monitoring_schema_backup_*.backup

# Только структура схемы (без данных, для быстрой проверки)
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema=monitoring \
  --schema-only \
  -f /tmp/monitoring_schema_structure_$(date +%Y%m%d_%H%M%S).sql

# Проверить (должно быть несколько КБ)
ls -lh /tmp/monitoring_schema_structure_*.sql
```

### Создание тестовой копии схемы monitoring (ПРАВИЛЬНО ✅)

```bash
# Вариант 1: Создать пустую схему и восстановить в неё
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "CREATE SCHEMA IF NOT EXISTS monitoring;"

pg_restore -h localhost -p 5433 -U elcrypto -d fox_crypto_test \
  --schema=monitoring \
  /tmp/monitoring_schema_backup_*.backup

# Вариант 2: Скопировать структуру без данных (для быстрого тестирования)
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema=monitoring --schema-only | \
  psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test

# Вариант 3: Скопировать только определённые таблицы
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --table=monitoring.positions \
  --table=monitoring.trades \
  --table=monitoring.events \
  -F c | \
  pg_restore -h localhost -p 5433 -U elcrypto -d fox_crypto_test
```

### Сравнение: Полная база vs Схема monitoring

| Объект | Размер | Время бэкапа | Время восстановления |
|--------|--------|--------------|---------------------|
| Вся база fox_crypto | ~сотни ГБ | ~часы | ~часы |
| Схема monitoring | ~десятки МБ | ~секунды | ~секунды |

**Вывод**: Работаем ТОЛЬКО со схемой monitoring! ✅

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

#### ФАЗА 1: ПОДГОТОВКА (Оценка: 10 минут)

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

**Содержимое миграции**: (см. полный SQL код в приложении)

---

**Шаг 2.2: Валидация синтаксиса миграции**

```bash
# Проверить SQL синтаксис без выполнения
psql -h localhost -p 5433 -U elcrypto -d fox_crypto --dry-run -f database/migrations/005_add_updated_at_triggers.sql 2>&1 | grep -i error

# Если команда --dry-run не поддерживается, использовать альтернативный метод:
# Создать временную копию ТОЛЬКО СХЕМЫ monitoring и применить там
```

---

#### ФАЗА 3: ТЕСТИРОВАНИЕ НА DEV/TEST БАЗЕ (Оценка: 30 минут)

**КРИТИЧЕСКИ ВАЖНО**: НЕ применять на продакшен базе сразу!

**Шаг 3.1: Создать тестовую копию ТОЛЬКО СХЕМЫ monitoring**

```bash
# ✅ ПРАВИЛЬНО: Бэкап ТОЛЬКО схемы monitoring
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema=monitoring \
  -F c -b -v \
  -f /tmp/monitoring_backup_before_005_$(date +%Y%m%d_%H%M%S).backup

# Проверить размер (должно быть ~десятки МБ)
ls -lh /tmp/monitoring_backup_before_005_*.backup

# Создать тестовую базу
psql -h localhost -p 5433 -U elcrypto -c "CREATE DATABASE fox_crypto_test;"

# Создать необходимые схемы
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "CREATE SCHEMA monitoring;"
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "CREATE SCHEMA fas;"

# Восстановить ТОЛЬКО схему monitoring в тестовую базу
pg_restore -h localhost -p 5433 -U elcrypto -d fox_crypto_test \
  --schema=monitoring \
  /tmp/monitoring_backup_before_005_*.backup

# Проверить что схема восстановилась
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "\dt monitoring.*"
```

**Время выполнения**: ~10-30 секунд (вместо часов для полной базы)

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

-- Очистить тестовые данные
DELETE FROM monitoring.positions WHERE symbol = 'TESTUSDT';
```

**Критерий успеха**:
- ✅ Тест показывает "✅ TRIGGER WORKS"
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

-- Измерить время с триггером
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
-- Ожидаемое время: 1000-1500 ms (1.0-1.5 ms на UPDATE)
-- Приемлемо если < 2 ms на UPDATE
```

**Критерий успеха**:
- ✅ Время < 2000 ms для 1000 UPDATE
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

**Шаг 4.1: Создать бэкап продакшен схемы monitoring**

```bash
# ✅ ПРАВИЛЬНО: Бэкап ТОЛЬКО схемы monitoring
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema=monitoring \
  -F c -b -v \
  -f /tmp/monitoring_backup_prod_before_005_$(date +%Y%m%d_%H%M%S).backup

# Проверить размер бэкапа
ls -lh /tmp/monitoring_backup_prod_before_005_*.backup

# Проверить что бэкап валидный
pg_restore --list /tmp/monitoring_backup_prod_before_005_*.backup | head -20
```

**Время выполнения**: ~10-30 секунд

**Критерий успеха**:
- ✅ Файл бэкапа создан
- ✅ Размер бэкапа разумный (десятки МБ, не 0 байт)
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
[ ] Шаг 3.1: Создана тестовая копия ТОЛЬКО СХЕМЫ monitoring
[ ] Шаг 3.2: Миграция применена на тестовой БД
[ ] Шаг 3.3: Верификация триггеров пройдена
[ ] Шаг 3.4: Функциональное тестирование успешно
[ ] Шаг 3.5: Нагрузочное тестирование приемлемо
[ ] Шаг 3.6: Тестирование с ботом успешно

Применение на продакшен:
[ ] Шаг 4.1: Создан бэкап продакшен СХЕМЫ monitoring
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
# Экспортировать текущую структуру ТОЛЬКО таблиц EventLogger
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

**Шаг 1.4: Анализировать код event_logger.py**

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
# ✅ ПРАВИЛЬНО: Бэкап ТОЛЬКО схемы monitoring
pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema=monitoring \
  -F c -b -v \
  -f /tmp/monitoring_backup_before_004_$(date +%Y%m%d_%H%M%S).backup

# Проверить
ls -lh /tmp/monitoring_backup_before_004_*.backup
```

**Время выполнения**: ~10-30 секунд

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

Код метода приведён в приложении к этому документу.

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
```

**Изменение 3: Добавить новый метод _verify_tables()**

См. код в приложении.

---

#### ФАЗА 4: ТЕСТИРОВАНИЕ ИЗМЕНЕНИЙ КОДА (Оценка: 30 минут)

**КРИТИЧЕСКИ ВАЖНО**: НЕ применять на продакшен без тестирования!

**Шаг 4.1: Тестирование на тестовой базе С таблицами**

```bash
# Создать тестовую базу с ТОЛЬКО схемой monitoring
psql -h localhost -p 5433 -U elcrypto -c "CREATE DATABASE fox_crypto_test;"

# Восстановить ТОЛЬКО схему monitoring
pg_restore -h localhost -p 5433 -U elcrypto -d fox_crypto_test \
  --schema=monitoring \
  /tmp/monitoring_backup_before_004_*.backup

# Применить изменения в коде (на отдельной ветке git)
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Создать ветку для тестирования
git checkout -b fix/issue5-remove-dynamic-table-creation

# Применить изменения в core/event_logger.py
# (ПОКА НЕ ДЕЛАТЬ - ТОЛЬКО ПЛАН!)

# Запустить бота на тестовой базе
DB_NAME=fox_crypto_test python main.py

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
CRITICAL - EventLogger initialization failed
```

**Критерий успеха**:
- ✅ Бот НЕ запускается (выходит с ошибкой)
- ✅ Ошибка понятная и содержит инструкции по исправлению
- ✅ Не создаются таблицы автоматически

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
# 4. Добавить новый метод _verify_tables() (см. код в приложении)
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
INFO - EventLogger wrote 2 events to DB
```

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
[ ] Шаг 2.2: Создан бэкап СХЕМЫ monitoring перед применением
[ ] Шаг 2.3: Миграция 004 применена на продакшен
[ ] Шаг 2.4: Верификация применения миграции 004

Изменение кода:
[ ] Шаг 3.1: Создан новый метод _verify_tables()
[ ] Шаг 3.2: Определён план изменений

Тестирование:
[ ] Шаг 4.1: Тест на базе С таблицами (успешно)
[ ] Шаг 4.2: Негативный тест на пустой базе (ошибка ожидаемая)

Применение на продакшен:
[ ] Шаг 5.1: Создан бэкап кода (git checkpoint)
[ ] Шаг 5.2: Изменения применены в event_logger.py
[ ] Шаг 5.3: Создан git коммит с изменениями
[ ] Шаг 5.4: Бот остановлен
[ ] Шаг 5.5: Изменения развёрнуты
[ ] Шаг 5.6: Бот запущен успешно
[ ] Шаг 5.7: Верификация работы (30 минут)
[ ] Шаг 5.8: Изменения смержены в main

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
  Утро:  Проблема #5 - Фазы 5 (Применение на продакшен)
  Вечер: Финальная верификация обеих проблем
```

---

## ПЛАН ОТКАТА (ROLLBACK PLAN)

### Откат проблемы #4 (Триггеры updated_at)

**Сценарий**: Триггеры вызывают проблемы, нужно откатить.

**Шаг 1: Удалить триггеры**

```sql
BEGIN;

DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;
DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;
DROP TRIGGER IF EXISTS update_orders_updated_at ON monitoring.orders;
DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;
DROP FUNCTION IF EXISTS public.update_updated_at_column();
ALTER TABLE monitoring.protection_events DROP COLUMN IF EXISTS updated_at;

COMMIT;
```

**Восстановление из бэкапа схемы monitoring** (если необходимо):

```bash
# Восстановить ТОЛЬКО схему monitoring
pg_restore -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --clean --schema=monitoring \
  /tmp/monitoring_backup_prod_before_005_*.backup
```

**Время восстановления**: ~10-30 секунд (не часы!)

---

### Откат проблемы #5 (Динамическое создание таблиц)

**Шаг 1: Откатить изменения кода в git**

```bash
# Переключиться на чекпоинт ДО изменений
git checkout checkpoint-before-issue5-fix

# Или откатить коммит
git revert <commit-hash-of-issue5-fix>
```

**Шаг 2: Перезапустить бота**

```bash
# Остановить бота
kill <PID>

# Запустить со старым кодом
python main.py
```

---

## ЧЕК-ЛИСТЫ ВЕРИФИКАЦИИ

### Финальный чек-лист ПРОБЛЕМЫ #4

```
ДО ПРИМЕНЕНИЯ:
[ ] Создан бэкап продакшен СХЕМЫ monitoring (~10-30 сек)
[ ] Миграция 005 протестирована на тестовой базе
[ ] Функциональное тестирование пройдено
[ ] Нагрузочное тестирование приемлемо

ПОСЛЕ ПРИМЕНЕНИЯ:
[ ] Миграция 005 применена без ошибок
[ ] 4 триггера созданы
[ ] updated_at обновляется автоматически при UPDATE
[ ] Нет ошибок в логах (первые 24 часа)
[ ] Производительность приемлемая

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
[ ] Создан бэкап кода (git checkpoint)
[ ] Изменения протестированы на тестовой базе
[ ] Код-ревью завершён

ПОСЛЕ ПРИМЕНЕНИЯ:
[ ] Метод _create_tables() удалён из event_logger.py
[ ] Метод _verify_tables() добавлен
[ ] Бот запущен успешно
[ ] Лог показывает "table verification passed"
[ ] EventLogger пишет события в базу

КРИТЕРИЙ УСПЕХА:
✅ Таблицы создаются ТОЛЬКО миграцией
✅ Код только проверяет существование таблиц
✅ Понятная ошибка если миграция не применена
✅ Бот работает стабильно без изменений функциональности
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
| **#5 ИТОГО** | | **~1.5 часа** |
| | | |
| **ОБЩЕЕ ВРЕМЯ** | | **~3 часа** |

**ВАЖНО**: Бэкапы ТОЛЬКО схемы monitoring занимают секунды, не часы!

---

### Сравнение подходов к бэкапу

| Параметр | Полная база | ТОЛЬКО схема monitoring |
|----------|-------------|------------------------|
| Размер бэкапа | ~сотни ГБ | ~десятки МБ |
| Время создания | ~часы | **~10-30 секунд** ✅ |
| Время восстановления | ~часы | **~10-30 секунд** ✅ |
| Риск переполнения диска | Высокий | Нет |
| Удобство тестирования | Низкое | **Высокое** ✅ |

---

## ЗАКЛЮЧЕНИЕ

Этот план обеспечивает:

✅ **Безопасность**: Бэкапы ТОЛЬКО схемы monitoring (быстро и безопасно)
✅ **Эффективность**: Операции занимают секунды, не часы
✅ **Прозрачность**: Детальные шаги с ожидаемыми результатами
✅ **Верифицируемость**: Чек-листы и критерии успеха
✅ **Документированность**: Подробное описание каждого изменения
✅ **Обратимость**: Чёткие инструкции по откату

**КЛЮЧЕВОЕ УЛУЧШЕНИЕ**: Работаем ТОЛЬКО со схемой monitoring - быстрее в 100+ раз!

---

**Дата создания плана**: 2025-10-14 (v2.0 - оптимизированы бэкапы)
**Статус**: ✅ ПЛАН ГОТОВ К РЕВЬЮ
**Готовность к применению**: ⏸️ ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ

---

## ПРИЛОЖЕНИЕ: SQL КОД МИГРАЦИИ 005

```sql
-- =====================================================
-- Migration 005: Add updated_at Auto-Update Triggers
-- =====================================================
-- (Полный SQL код см. в оригинальном плане SAFE_FIX_PLAN_ISSUES_4_5.md)
```

## ПРИЛОЖЕНИЕ: КОД МЕТОДА _verify_tables()

```python
async def _verify_tables(self):
    """
    Verify that EventLogger tables exist in database.

    Tables MUST be created by migration 004_create_event_logger_tables.sql
    This method does NOT create tables - it only verifies their existence.

    Raises:
        RuntimeError: If any required table is missing
    """
    # (Полный код метода см. в оригинальном плане SAFE_FIX_PLAN_ISSUES_4_5.md)
```
