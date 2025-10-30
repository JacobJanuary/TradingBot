# 🔴 КРИТИЧЕСКИЙ АУДИТ: Проблема monitoring.params

**Дата:** 2025-10-30
**Статус:** КРИТИЧЕСКАЯ ОШИБКА - параметры фильтров никогда не сохраняются в БД
**Влияние:** Бот всегда использует дефолтные параметры из .env, игнорируя параметры из сигналов

---

## 📋 EXECUTIVE SUMMARY

**Проблема:** Таблица `monitoring.params` пуста с момента создания. Бот пытается обновить параметры при каждой волне, но операция ВСЕГДА терпит неудачу из-за отсутствия начальных записей.

**Root Cause:** Метод `repository.update_params()` использует только `UPDATE` запрос и **НЕ создает записи**, если они не существуют. В коде **отсутствует** логика инициализации (INSERT) или UPSERT.

**Последствия:**
- ❌ Бот игнорирует динамические параметры фильтров из сигналов
- ❌ Всегда использует fallback значения из .env (max_trades=5, stop_loss=4%, etc.)
- ❌ Невозможно управлять параметрами через сигналы от бэктестера
- ❌ В логах постоянно: "No row found for exchange_id=1/2"

---

## 🔍 ДЕТАЛЬНЫЙ АНАЛИЗ

### 1. Состояние таблицы БД

```sql
tradingbot_db=# SELECT * FROM monitoring.params;
 exchange_id | max_trades_filter | stop_loss_filter | trailing_activation_filter | trailing_distance_filter | updated_at | created_at
-------------+-------------------+------------------+----------------------------+--------------------------+------------+------------
(0 rows)
```

**Вердикт:** ✅ Таблица создана корректно, но **ПУСТА**

### 2. Структура таблицы

```sql
Table "monitoring.params"
           Column           |           Type           | Nullable |      Default
----------------------------+--------------------------+----------+-------------------
 exchange_id                | integer                  | NOT NULL |
 max_trades_filter          | integer                  | NULL     |
 stop_loss_filter           | numeric(10,4)            | NULL     |
 trailing_activation_filter | numeric(10,4)            | NULL     |
 trailing_distance_filter   | numeric(10,4)            | NULL     |
 updated_at                 | timestamp with time zone | NULL     | CURRENT_TIMESTAMP
 created_at                 | timestamp with time zone | NULL     | CURRENT_TIMESTAMP

PRIMARY KEY: exchange_id
CONSTRAINT: exchange_id IN (1, 2)  -- 1=Binance, 2=Bybit
```

**Вердикт:** ✅ Структура правильная

### 3. Анализ кода: signal_processor_websocket.py

**Метод:** `_update_exchange_params()` (строка 1292)

**Алгоритм:**
1. Группирует сигналы по `exchange_id`
2. Берет **первый сигнал** от каждой биржи
3. Извлекает `filter_params` из сигнала
4. Вызывает `repository.update_params(exchange_id, **filter_params)`

**Пример из логов:**
```
2025-10-30 12:49:03,107 - 📊 Updating params for exchange_id=1 from signal #6756119:
  {'max_trades_filter': 3, 'stop_loss_filter': 4.0, 'trailing_activation_filter': 2.0, 'trailing_distance_filter': 0.5}
```

**Вердикт:** ✅ Логика правильная - бот **пытается** обновить параметры

### 4. Анализ кода: database/repository.py

**Метод:** `update_params()` (строка 186)

**Проблема #1: Только UPDATE, нет INSERT**

```python
query = f"""
    UPDATE monitoring.params
    SET {', '.join(updates)}
    WHERE exchange_id = $1
    RETURNING exchange_id
"""

result = await conn.fetchval(query, *params)

if result:
    return True
else:
    logger.warning(f"No row found for exchange_id={exchange_id}")
    return False  # ← ВСЕГДА возвращает False для пустой таблицы!
```

**Проблема #2: Нет метода `create_params()` или `insert_params()`**

```bash
$ grep -n "def.*params" database/repository.py
156:    async def get_params(self, exchange_id: int) -> Optional[Dict]:
186:    async def update_params(...)
265:    async def get_all_params(self) -> Dict[int, Dict]:
290:    async def get_params_by_exchange_name(...)

# НЕТ: create_params, insert_params, upsert_params
```

**Вердикт:** ❌ **КЛЮЧЕВАЯ ПРОБЛЕМА** - нет логики создания начальных записей

### 5. Анализ миграций

**Файл:** `database/migrations/001_init_schema.sql`

```sql
CREATE TABLE monitoring.params (...);
-- НЕТ INSERT INTO monitoring.params ...
```

**Вердикт:** ❌ Миграция создает пустую таблицу без начальных данных

### 6. Анализ логов первого запуска

**Первая волна:** 2025-10-30 07:19:03 (волна 07:00)

```
07:19:03,091 - 📊 Step 1: Updating exchange params from wave 2025-10-30T07:00:00+00:00
07:19:03,091 - 📊 Updating params for exchange_id=2 from signal #6720206:
                {'max_trades_filter': 2, 'stop_loss_filter': 6.0, ...}
07:19:03,092 - database.repository - WARNING - No row found for exchange_id=2
07:19:03,092 - ⚠️ Failed to update params for exchange_id=2 at wave 2025-10-30T07:00:00+00:00
07:19:03,092 - ✅ Exchange params updated successfully  ← ЛОЖНЫЙ SUCCESS!
07:19:03,093 - ⚠️ Binance: max_trades_filter is NULL in DB, using config fallback=5
07:19:03,094 - ⚠️ Bybit: max_trades_filter is NULL in DB, using config fallback=5
```

**Вердикт:** ❌ С самого первого запуска параметры не сохраняются

### 7. Последствия в текущей работе

**Пример последней волны (12:30, обработана 12:49):**

```
Попытка обновления:
  • exchange_id=1 (Binance): max_trades=3, stop_loss=4.0%, trailing_activation=2.0%, trailing_distance=0.5%
  • exchange_id=2 (Bybit):   max_trades=2, stop_loss=6.0%, trailing_activation=2.0%, trailing_distance=0.5%

Результат:
  ❌ No row found for exchange_id=1
  ❌ No row found for exchange_id=2

Фактически использовано (из .env):
  • Binance: max_trades=5, stop_loss=4.0%  ← НЕПРАВИЛЬНО (должно быть 3)
  • Bybit:   max_trades=5, stop_loss=6.0%  ← НЕПРАВИЛЬНО (должно быть 2)
```

---

## 🎯 ПЛАН ИСПРАВЛЕНИЯ

### Вариант 1: UPSERT в repository (РЕКОМЕНДУЕТСЯ)

**Что:** Изменить `update_params()` на использование PostgreSQL UPSERT

**Код:**
```python
async def update_params(self, exchange_id: int, ...) -> bool:
    # Build updates...

    query = f"""
        INSERT INTO monitoring.params (exchange_id, {', '.join(field_names)})
        VALUES ($1, {', '.join(f'${i}' for i in range(2, len(params)+1))})
        ON CONFLICT (exchange_id)
        DO UPDATE SET {', '.join(updates)}
        RETURNING exchange_id
    """
```

**Преимущества:**
- ✅ Одна операция (атомарная)
- ✅ Работает для пустой и заполненной таблицы
- ✅ Не нужно изменять логику в signal_processor

**Файлы для изменения:**
- `database/repository.py:186` - метод `update_params()`

---

### Вариант 2: Отдельный метод create_params + проверка

**Что:** Добавить метод `create_params()` и проверять существование записи

**Код:**
```python
async def create_params(self, exchange_id: int) -> bool:
    """Create initial params row if not exists"""
    query = """
        INSERT INTO monitoring.params (exchange_id)
        VALUES ($1)
        ON CONFLICT (exchange_id) DO NOTHING
        RETURNING exchange_id
    """
    # ...

async def ensure_params_exist(self, exchange_id: int):
    """Ensure params row exists before update"""
    exists = await self.get_params(exchange_id)
    if not exists:
        await self.create_params(exchange_id)
```

**Преимущества:**
- ✅ Разделение ответственности (create vs update)
- ✅ Более явная логика

**Недостатки:**
- ❌ Две операции (не атомарно)
- ❌ Race condition возможен

**Файлы для изменения:**
- `database/repository.py` - добавить `create_params()`, `ensure_params_exist()`
- `core/signal_processor_websocket.py:1366` - вызвать `ensure_params_exist()` перед `update_params()`

---

### Вариант 3: Инициализация при старте

**Что:** Создать начальные записи при запуске бота в `main.py`

**Код:**
```python
async def initialize_params(repository):
    """Ensure monitoring.params has entries for all exchanges"""
    for exchange_id in [1, 2]:  # Binance, Bybit
        exists = await repository.get_params(exchange_id)
        if not exists:
            await repository.create_params(exchange_id)
            logger.info(f"✅ Created initial params for exchange_id={exchange_id}")
```

**Преимущества:**
- ✅ Выполняется один раз при старте
- ✅ Явная инициализация

**Недостатки:**
- ❌ Не решает проблему, если таблица очистится
- ❌ Требует добавление метода `create_params()`

**Файлы для изменения:**
- `database/repository.py` - добавить `create_params()`
- `main.py` - добавить вызов `initialize_params()` после инициализации БД

---

### Вариант 4: SQL миграция (дополнение)

**Что:** Добавить миграцию для вставки начальных данных

**Файл:** `database/migrations/002_init_params.sql`
```sql
-- Create initial params rows for both exchanges
INSERT INTO monitoring.params (exchange_id)
VALUES (1), (2)
ON CONFLICT (exchange_id) DO NOTHING;
```

**Преимущества:**
- ✅ Гарантирует начальные данные при развертывании
- ✅ Идемпотентная операция

**Недостатки:**
- ❌ Не решает проблему логики update (все равно нужен UPSERT)

**Файлы для изменения:**
- Создать `database/migrations/002_init_params.sql`

---

## 🏆 РЕКОМЕНДОВАННОЕ РЕШЕНИЕ

### Комбинация Варианта 1 + Варианта 4

**Шаг 1:** Изменить `repository.update_params()` на UPSERT
- Файл: `database/repository.py:186`
- Изменение: Заменить `UPDATE ... WHERE` на `INSERT ... ON CONFLICT UPDATE`

**Шаг 2:** Создать миграцию для существующих установок
- Файл: `database/migrations/002_init_params.sql`
- SQL: `INSERT INTO monitoring.params (exchange_id) VALUES (1), (2) ON CONFLICT DO NOTHING`

**Шаг 3:** Применить миграцию на продакшене
```bash
psql -h localhost -U tradingbot -d tradingbot_db -f database/migrations/002_init_params.sql
```

---

## 📊 ВЛИЯНИЕ ИСПРАВЛЕНИЯ

### До исправления:
- ❌ Параметры никогда не сохраняются
- ❌ Всегда используется max_trades=5 (вместо 2-3 из сигналов)
- ❌ Игнорируются stop_loss параметры из сигналов
- ❌ Невозможно динамически управлять фильтрами

### После исправления:
- ✅ Параметры сохраняются при каждой волне
- ✅ max_trades корректно берется из сигналов (2-3 вместо 5)
- ✅ stop_loss берется из сигналов (4.0-6.0% вместо дефолта)
- ✅ Возможность A/B тестирования параметров через бэктестер
- ✅ Разные настройки для Binance и Bybit

---

## ⚠️ РИСКИ БЕЗ ИСПРАВЛЕНИЯ

1. **Неправильное управление позициями:**
   - Бот открывает 5 позиций вместо 2-3 → превышение риска

2. **Игнорирование результатов бэктеста:**
   - Оптимизированные параметры не применяются

3. **Невозможность управления:**
   - Нельзя изменить параметры без перезапуска бота

4. **Расхождение с документацией:**
   - Система должна брать параметры из сигналов, но не делает этого

---

## 📝 NEXT STEPS

1. ✅ **Аудит завершен** - проблема полностью документирована
2. ⏳ **Ожидание одобрения** - выбор варианта решения
3. ⏳ **Имплементация** - изменение кода
4. ⏳ **Тестирование** - проверка на dev окружении
5. ⏳ **Деплой** - применение на продакшене
6. ⏳ **Верификация** - проверка логов после исправления

---

## 🔗 СВЯЗАННЫЕ ФАЙЛЫ

**Требуют изменения:**
- `database/repository.py:186` - метод `update_params()`

**Требуют создания:**
- `database/migrations/002_init_params.sql` - начальные данные

**Для справки:**
- `core/signal_processor_websocket.py:1292` - вызов update_params
- `database/migrations/001_init_schema.sql` - создание таблицы

---

**Отчет подготовлен:** Claude Code
**Дата:** 2025-10-30 13:15 UTC
