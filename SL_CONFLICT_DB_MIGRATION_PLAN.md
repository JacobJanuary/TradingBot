# 🗄️ ПЛАН МИГРАЦИИ БД: SL CONFLICT FIXES

**Дата:** 2025-10-13 07:30
**Статус:** ПЛАН (БЕЗ ИЗМЕНЕНИЙ)
**Приоритет:** 🔴 КРИТИЧЕСКИЙ
**Branch:** fix/sl-manager-conflicts

---

## 📋 EXECUTIVE SUMMARY

**Проблема:** Код для SL conflict fixes реализован, но миграция БД НЕ ВЫПОЛНЕНА.

**Отсутствуют поля:**
1. `ts_last_update_time` (timestamp) - Solution #3
2. `sl_managed_by` (varchar) - Solution #1

**Последствия:**
- ❌ Fallback protection НЕ РАБОТАЕТ (нет ts_last_update_time)
- ❌ Ownership tracking работает ЧАСТИЧНО (нет sl_managed_by)
- ⚠️ Код пытается записать в несуществующие поля → потенциальные ошибки

**Решение:** Выполнить миграцию для добавления 2 полей в таблицу `monitoring.positions`

---

## 🎯 ЦЕЛЬ МИГРАЦИИ

Добавить недостающие поля в таблицу `monitoring.positions` для полной поддержки SL conflict fixes.

### Поля для добавления:

**1. ts_last_update_time**
- **Тип:** `TIMESTAMP WITHOUT TIME ZONE`
- **Nullable:** `YES` (NULL)
- **Default:** `NULL`
- **Назначение:** Отслеживание последнего обновления TS для fallback protection
- **Используется в:** Solution #3 (core/position_manager.py:1193, 1598)

**2. sl_managed_by**
- **Тип:** `VARCHAR(20)`
- **Nullable:** `YES` (NULL)
- **Default:** `NULL`
- **Допустимые значения:** 'protection', 'trailing_stop', NULL
- **Назначение:** Явное указание владельца SL (ownership tracking)
- **Используется в:** Solution #1 (core/position_manager.py:115, 1644)

---

## 📊 ТЕКУЩЕЕ СОСТОЯНИЕ

### Существующие TS поля в БД:

| Поле | Тип | Nullable | Default | Статус |
|------|-----|----------|---------|--------|
| has_trailing_stop | boolean | YES | false | ✅ Существует |
| trailing_activated | boolean | YES | false | ✅ Существует |

### Недостающие TS поля:

| Поле | Тип | Nullable | Default | Статус |
|------|-----|----------|---------|--------|
| ts_last_update_time | timestamp | YES | NULL | ❌ Отсутствует |
| sl_managed_by | varchar(20) | YES | NULL | ❌ Отсутствует |

### Статистика позиций:

- **Всего позиций:** 54
- **Активных позиций:** 11
- **has_trailing_stop=true:** 24
- **trailing_activated=true:** 0

---

## 🔧 ПЛАН МИГРАЦИИ

### OPTION A: Простая миграция (рекомендуется)

**Характеристики:**
- ✅ Быстро (~1 секунда)
- ✅ Безопасно (только ADD COLUMN)
- ✅ Не требует downtime
- ✅ Совместимо с существующими данными
- ✅ Откат простой (DROP COLUMN)

**Шаги:** 4 шага
**Время:** ~5 минут
**Риск:** 🟢 Низкий

---

### OPTION B: Миграция с валидацией и индексами

**Характеристики:**
- ✅ Включает проверки типов данных
- ✅ Добавляет индексы для производительности
- ✅ Добавляет CHECK constraints
- ⚠️ Медленнее (~5-10 секунд)
- ⚠️ Более сложный откат

**Шаги:** 7 шагов
**Время:** ~15 минут
**Риск:** 🟡 Средний

---

## 📝 ДЕТАЛЬНЫЙ ПЛАН: OPTION A (РЕКОМЕНДУЕТСЯ)

### Pre-Migration Checklist

**1. Проверка окружения:**
- [ ] Бот остановлен (pkill -f "python.*main.py")
- [ ] База данных доступна (проверка подключения)
- [ ] Права доступа достаточны (ALTER TABLE)
- [ ] Достаточно места на диске (проверка df -h)

**2. Backup:**
- [ ] Создан backup БД (pg_dump)
- [ ] Backup сохранен в безопасное место
- [ ] Backup проверен (можно восстановить)

**3. Git:**
- [ ] Текущие изменения закоммичены
- [ ] Branch: fix/sl-manager-conflicts
- [ ] Checkpoint commit создан

---

### STEP 1: CREATE BACKUP

**Цель:** Создать полный backup БД перед миграцией

**Команда:**
```bash
PGPASSWORD='LohNeMamont@!21' pg_dump \
  -h localhost \
  -p 5433 \
  -U elcrypto \
  -d fox_crypto_test \
  -F c \
  -b \
  -v \
  -f backup_before_sl_migration_$(date +%Y%m%d_%H%M%S).backup
```

**Альтернатива (SQL dump):**
```bash
PGPASSWORD='LohNeMamont@!21' pg_dump \
  -h localhost \
  -p 5433 \
  -U elcrypto \
  -d fox_crypto_test \
  > backup_before_sl_migration_$(date +%Y%m%d_%H%M%S).sql
```

**Проверка:**
```bash
# Проверить размер backup
ls -lh backup_before_sl_migration_*.backup

# Должен быть > 0 bytes, обычно несколько MB
```

**Время:** ~10 секунд

**Успех если:**
- ✅ Файл создан
- ✅ Размер > 0 bytes
- ✅ Нет ошибок в выводе

---

### STEP 2: ADD ts_last_update_time COLUMN

**Цель:** Добавить поле для отслеживания health TS Manager

**SQL:**
```sql
ALTER TABLE monitoring.positions
ADD COLUMN ts_last_update_time TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL;
```

**Команда через psql:**
```bash
PGPASSWORD='LohNeMamont@!21' psql \
  -h localhost \
  -p 5433 \
  -U elcrypto \
  -d fox_crypto_test \
  -c "ALTER TABLE monitoring.positions ADD COLUMN ts_last_update_time TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL;"
```

**Команда через Python:**
```python
# В файле: add_ts_last_update_time.py
await conn.execute("""
    ALTER TABLE monitoring.positions
    ADD COLUMN ts_last_update_time TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL
""")
```

**Проверка:**
```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name = 'ts_last_update_time';
```

**Ожидаемый результат:**
```
column_name          | data_type                   | is_nullable | column_default
---------------------+-----------------------------+-------------+---------------
ts_last_update_time  | timestamp without time zone | YES         | NULL
```

**Время:** ~1 секунда

**Успех если:**
- ✅ Поле создано
- ✅ Тип: timestamp without time zone
- ✅ Nullable: YES
- ✅ Default: NULL
- ✅ Нет ошибок

**Git commit:**
```bash
git add -A
git commit -m "🗄️ Add ts_last_update_time field for TS health tracking

- Add TIMESTAMP field to monitoring.positions
- Used for fallback protection (Solution #3)
- Default NULL for existing positions"
```

---

### STEP 3: ADD sl_managed_by COLUMN

**Цель:** Добавить поле для ownership tracking SL

**SQL:**
```sql
ALTER TABLE monitoring.positions
ADD COLUMN sl_managed_by VARCHAR(20) DEFAULT NULL;
```

**Команда через psql:**
```bash
PGPASSWORD='LohNeMamont@!21' psql \
  -h localhost \
  -p 5433 \
  -U elcrypto \
  -d fox_crypto_test \
  -c "ALTER TABLE monitoring.positions ADD COLUMN sl_managed_by VARCHAR(20) DEFAULT NULL;"
```

**Команда через Python:**
```python
# В файле: add_sl_managed_by.py
await conn.execute("""
    ALTER TABLE monitoring.positions
    ADD COLUMN sl_managed_by VARCHAR(20) DEFAULT NULL
""")
```

**Проверка:**
```sql
SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name = 'sl_managed_by';
```

**Ожидаемый результат:**
```
column_name   | data_type         | character_maximum_length | is_nullable | column_default
--------------+-------------------+--------------------------+-------------+---------------
sl_managed_by | character varying | 20                       | YES         | NULL
```

**Время:** ~1 секунда

**Успех если:**
- ✅ Поле создано
- ✅ Тип: varchar(20)
- ✅ Nullable: YES
- ✅ Default: NULL
- ✅ Нет ошибок

**Git commit:**
```bash
git add -A
git commit -m "🗄️ Add sl_managed_by field for SL ownership tracking

- Add VARCHAR(20) field to monitoring.positions
- Used for ownership tracking (Solution #1)
- Values: 'protection', 'trailing_stop', NULL
- Default NULL for existing positions"
```

---

### STEP 4: VERIFY MIGRATION

**Цель:** Проверить, что все поля созданы корректно

**SQL проверка:**
```sql
-- Проверка структуры
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name IN ('ts_last_update_time', 'sl_managed_by')
ORDER BY column_name;
```

**Команда через Python:**
```python
# В файле: verify_migration.py
columns = await conn.fetch("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = 'monitoring'
      AND table_name = 'positions'
      AND column_name IN ('ts_last_update_time', 'sl_managed_by')
    ORDER BY column_name
""")

for col in columns:
    print(f"✅ {col['column_name']}: {col['data_type']}")
```

**Проверка данных:**
```sql
-- Проверить что NULL для существующих позиций
SELECT
    COUNT(*) as total,
    COUNT(ts_last_update_time) as has_ts_time,
    COUNT(sl_managed_by) as has_sl_managed
FROM monitoring.positions;
```

**Ожидаемый результат:**
```
total | has_ts_time | has_sl_managed
------+-------------+---------------
54    | 0           | 0
```
(Все NULL для существующих 54 позиций)

**Проверка количества полей:**
```sql
SELECT COUNT(*) as total_columns
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions';
```

**Ожидаемый результат:**
```
total_columns
-------------
41
```
(Было 39, стало 41 = +2 поля)

**Время:** ~5 секунд

**Успех если:**
- ✅ Оба поля существуют
- ✅ Типы данных корректны
- ✅ Все NULL для существующих позиций
- ✅ Всего 41 поле в таблице (было 39)
- ✅ Нет ошибок

**Git commit:**
```bash
git add -A
git commit -m "✅ Verify SL conflict DB migration completed

- Verified ts_last_update_time field
- Verified sl_managed_by field
- All existing positions have NULL values
- Total columns: 41 (was 39)"
```

---

### STEP 5: TEST MIGRATION (OPTIONAL)

**Цель:** Протестировать, что код может записывать в новые поля

**Тестовый SQL:**
```sql
-- Создать тестовую позицию
INSERT INTO monitoring.positions (
    symbol, exchange, side, quantity, entry_price, status,
    has_trailing_stop, trailing_activated,
    ts_last_update_time, sl_managed_by
) VALUES (
    'TEST_MIGRATION', 'binance', 'long', 1.0, 100.0, 'active',
    true, false,
    NOW(), 'trailing_stop'
) RETURNING id, symbol, ts_last_update_time, sl_managed_by;
```

**Проверка записи:**
```sql
SELECT id, symbol, ts_last_update_time, sl_managed_by
FROM monitoring.positions
WHERE symbol = 'TEST_MIGRATION';
```

**Ожидаемый результат:**
```
id  | symbol          | ts_last_update_time      | sl_managed_by
----+-----------------+--------------------------+---------------
XXX | TEST_MIGRATION  | 2025-10-13 07:30:00.123  | trailing_stop
```

**Удалить тестовую запись:**
```sql
DELETE FROM monitoring.positions
WHERE symbol = 'TEST_MIGRATION';
```

**Время:** ~10 секунд

**Успех если:**
- ✅ Запись создана
- ✅ ts_last_update_time записан
- ✅ sl_managed_by записан
- ✅ Тестовая запись удалена
- ✅ Нет ошибок

---

### STEP 6: PUSH TO GITHUB

**Цель:** Сохранить миграцию в Git

**Команды:**
```bash
# Проверить статус
git status

# Проверить коммиты
git log --oneline -5

# Push to GitHub
git push origin fix/sl-manager-conflicts
```

**Успех если:**
- ✅ 3 новых коммита (add ts_last_update_time, add sl_managed_by, verify)
- ✅ Push успешен
- ✅ Нет конфликтов

---

## 📝 ДЕТАЛЬНЫЙ ПЛАН: OPTION B (С ВАЛИДАЦИЕЙ)

### Дополнительные шаги к Option A:

**STEP 2B: ADD CHECK CONSTRAINT для sl_managed_by**

**SQL:**
```sql
ALTER TABLE monitoring.positions
ADD CONSTRAINT check_sl_managed_by_values
CHECK (sl_managed_by IS NULL OR sl_managed_by IN ('protection', 'trailing_stop'));
```

**Цель:** Гарантировать только допустимые значения

**STEP 3B: ADD INDEX для ts_last_update_time**

**SQL:**
```sql
CREATE INDEX idx_positions_ts_last_update
ON monitoring.positions(ts_last_update_time)
WHERE ts_last_update_time IS NOT NULL;
```

**Цель:** Ускорить queries для fallback protection

**STEP 4B: ADD INDEX для sl_managed_by**

**SQL:**
```sql
CREATE INDEX idx_positions_sl_managed_by
ON monitoring.positions(sl_managed_by)
WHERE sl_managed_by IS NOT NULL;
```

**Цель:** Ускорить queries по ownership

**STEP 5B: ADD COMMENT для документации**

**SQL:**
```sql
COMMENT ON COLUMN monitoring.positions.ts_last_update_time IS
'Last update timestamp from TS Manager for health tracking and fallback protection';

COMMENT ON COLUMN monitoring.positions.sl_managed_by IS
'SL ownership: "protection" (Protection Manager), "trailing_stop" (TS Manager), NULL (no explicit owner)';
```

**Цель:** Документировать назначение полей

---

## 🔄 ROLLBACK PROCEDURE

### Если миграция не удалась:

**OPTION 1: Откат через SQL (простой)**

```sql
-- Удалить поля
ALTER TABLE monitoring.positions DROP COLUMN ts_last_update_time;
ALTER TABLE monitoring.positions DROP COLUMN sl_managed_by;
```

**OPTION 2: Восстановить из backup (полный)**

```bash
# Остановить бот
pkill -f "python.*main.py"

# Восстановить базу
PGPASSWORD='LohNeMamont@!21' pg_restore \
  -h localhost \
  -p 5433 \
  -U elcrypto \
  -d fox_crypto_test \
  -c \
  backup_before_sl_migration_YYYYMMDD_HHMMSS.backup
```

**OPTION 3: Откат через Git + SQL**

```bash
# Git rollback
git reset --hard <commit_before_migration>

# SQL rollback
ALTER TABLE monitoring.positions DROP COLUMN IF EXISTS ts_last_update_time;
ALTER TABLE monitoring.positions DROP COLUMN IF EXISTS sl_managed_by;
```

---

## ✅ POST-MIGRATION CHECKLIST

**1. Структура БД:**
- [ ] Поле ts_last_update_time существует
- [ ] Поле sl_managed_by существует
- [ ] Всего 41 поле в таблице
- [ ] Все существующие позиции имеют NULL в новых полях

**2. Git:**
- [ ] 3 коммита созданы (add field 1, add field 2, verify)
- [ ] Pushed to GitHub
- [ ] Branch: fix/sl-manager-conflicts

**3. Backup:**
- [ ] Backup создан
- [ ] Backup проверен
- [ ] Backup сохранен

**4. Документация:**
- [ ] План миграции создан
- [ ] Результат миграции задокументирован

---

## 🧪 VERIFICATION QUERIES

### Проверка структуры:

```sql
-- Все TS поля
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name IN (
    'has_trailing_stop',
    'trailing_activated',
    'ts_last_update_time',
    'sl_managed_by'
  )
ORDER BY column_name;
```

### Проверка данных:

```sql
-- Статистика по новым полям
SELECT
    COUNT(*) as total_positions,
    COUNT(ts_last_update_time) as has_ts_time,
    COUNT(sl_managed_by) as has_sl_managed,
    COUNT(CASE WHEN ts_last_update_time IS NOT NULL THEN 1 END) as ts_time_not_null,
    COUNT(CASE WHEN sl_managed_by IS NOT NULL THEN 1 END) as sl_managed_not_null
FROM monitoring.positions;
```

### Проверка активных позиций:

```sql
-- Активные позиции с TS полями
SELECT
    symbol,
    exchange,
    status,
    has_trailing_stop,
    trailing_activated,
    ts_last_update_time,
    sl_managed_by,
    created_at
FROM monitoring.positions
WHERE status = 'active'
ORDER BY created_at DESC;
```

---

## 📈 EXPECTED RESULTS

### После миграции:

**Структура таблицы:**
- ✅ 41 поле (было 39, +2)
- ✅ ts_last_update_time: timestamp, nullable
- ✅ sl_managed_by: varchar(20), nullable

**Данные:**
- ✅ Все 54 существующие позиции: ts_last_update_time = NULL
- ✅ Все 54 существующие позиции: sl_managed_by = NULL
- ✅ Нет потери данных
- ✅ Все существующие поля без изменений

**Код:**
- ✅ Может записывать в ts_last_update_time
- ✅ Может записывать в sl_managed_by
- ✅ Fallback protection ЗАРАБОТАЕТ при следующем запуске
- ✅ Ownership tracking ПОЛНОСТЬЮ РАБОТАЕТ

---

## ⏱️ TIMELINE

### Option A (Simple):
- **STEP 1:** Backup (10 секунд)
- **STEP 2:** Add ts_last_update_time (1 секунда)
- **STEP 3:** Add sl_managed_by (1 секунда)
- **STEP 4:** Verify migration (5 секунд)
- **STEP 5:** Test migration (10 секунд, optional)
- **STEP 6:** Git commit & push (10 секунд)

**Итого:** ~5 минут (с тестами), ~2 минуты (без тестов)

### Option B (With validation):
- Option A + 4 дополнительных шага
- **Итого:** ~15 минут

---

## 🚨 RISKS & MITIGATION

### Risk #1: Миграция не применится

**Вероятность:** 🟢 Низкая
**Последствия:** Средние (бот не запустится)

**Причины:**
- Недостаточно прав ALTER TABLE
- Блокировка таблицы другим процессом
- Синтаксическая ошибка в SQL

**Mitigation:**
- ✅ Остановить бот перед миграцией
- ✅ Проверить права доступа
- ✅ Использовать проверенный SQL
- ✅ Backup перед миграцией

**Откат:** Восстановить из backup

---

### Risk #2: Код не работает с новыми полями

**Вероятность:** 🟢 Очень низкая
**Последствия:** Средние (ошибки при записи)

**Причины:**
- Несоответствие типов данных
- Код пытается записать невалидные значения

**Mitigation:**
- ✅ Типы данных соответствуют коду
- ✅ Nullable = YES (нет NOT NULL constraints)
- ✅ Тестирование после миграции

**Откат:** Удалить поля через DROP COLUMN

---

### Risk #3: Потеря данных

**Вероятность:** 🟢 Очень низкая
**Последствия:** 🔴 Критические

**Причины:**
- Ошибка при миграции
- Случайный DROP TABLE
- Corrupted backup

**Mitigation:**
- ✅ Только ADD COLUMN (не DROP, не MODIFY)
- ✅ Backup перед миграцией
- ✅ Проверка backup после создания
- ✅ НЕ использовать DROP или TRUNCATE

**Откат:** Восстановить из backup

---

### Risk #4: Downtime

**Вероятность:** 🟢 Низкая
**Последствия:** Низкие (несколько минут)

**Причины:**
- Долгая миграция (блокировка таблицы)
- Проблемы при откате

**Mitigation:**
- ✅ ADD COLUMN очень быстрый (~1 секунда)
- ✅ Не требует rewrite таблицы
- ✅ Бот остановлен заранее

**Откат:** N/A (миграция быстрая)

---

## 📚 REFERENCES

### Связанные документы:

1. **SL_CONFLICT_FIXES_IMPLEMENTATION_REPORT.md**
   - Solution #1: Ownership Flag (sl_managed_by)
   - Solution #3: Fallback Protection (ts_last_update_time)

2. **SL_CONFLICT_DEEP_RESEARCH_VERIFIED.md**
   - Анализ проблем SL конфликтов
   - Обоснование необходимости полей

3. **database/schema.sql** (если существует)
   - Текущая схема БД

### Код использующий новые поля:

**ts_last_update_time:**
- `core/position_manager.py:1193` - запись timestamp
- `core/position_manager.py:1598-1644` - fallback logic

**sl_managed_by:**
- `core/position_manager.py:115` - определение в PositionState
- `core/position_manager.py:1644` - установка при fallback

---

## 🎯 SUCCESS CRITERIA

Миграция считается успешной если:

1. ✅ Оба поля созданы в БД
2. ✅ Типы данных корректны
3. ✅ Существующие данные не потеряны
4. ✅ Тестовая запись успешна
5. ✅ Git коммиты созданы
6. ✅ Pushed to GitHub
7. ✅ Backup создан и проверен
8. ✅ Нет ошибок в логах
9. ✅ Бот может запуститься после миграции
10. ✅ Код может записывать в новые поля

---

## 📞 NEXT STEPS

### После успешной миграции:

**1. Restart Bot:**
```bash
# Запустить бота
python main.py &

# Следить за логами
tail -f logs/trading_bot.log
```

**2. Monitor Logs:**
```bash
# Проверить что fallback logic работает
tail -f logs/trading_bot.log | grep -E "ts_last_update_time|sl_managed_by|TS Manager inactive"
```

**3. Verify Data:**
```sql
-- Проверить что новые позиции имеют ts_last_update_time
SELECT symbol, ts_last_update_time, sl_managed_by
FROM monitoring.positions
WHERE status = 'active'
  AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

**4. Testing:**
- Дождаться открытия новой позиции
- Дождаться активации TS
- Проверить что ts_last_update_time обновляется
- Проверить что fallback НЕ срабатывает ложно

**5. Production Deployment:**
- Если все работает → merge to main
- Create release tag
- Deploy to production

---

## 🛠️ TOOLS & SCRIPTS

### Скрипты для миграции:

**1. create_migration.py**
- Автоматическое выполнение миграции
- Проверка перед применением
- Откат при ошибке

**2. verify_migration.py**
- Проверка структуры БД
- Проверка данных
- Генерация отчета

**3. test_migration.py**
- Тестовая запись/чтение
- Проверка constraints
- Проверка индексов

---

## 🎉 CONCLUSION

**Миграция:** Простая и безопасная

**Риски:** 🟢 Минимальные

**Время:** ~5 минут

**Откат:** Простой (DROP COLUMN или restore backup)

**Рекомендация:** Использовать Option A (Simple Migration)

**Следующий шаг:** Получить одобрение пользователя и выполнить миграцию

---

**Автор:** Claude Code
**Дата:** 2025-10-13 07:30
**Версия:** 1.0
**Статус:** ПЛАН (ожидает одобрения)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
