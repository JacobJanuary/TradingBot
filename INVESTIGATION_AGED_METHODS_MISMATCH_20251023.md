# 🔍 РАССЛЕДОВАНИЕ: Несоответствие методов aged_positions

## Дата: 2025-10-23 22:40
## Статус: INVESTIGATION COMPLETED - PLAN READY

---

# 📊 НАЙДЕННЫЕ ПРОБЛЕМЫ

## КРИТИЧЕСКАЯ ПРОБЛЕМА: Несоответствие schema и таблиц

### Факты:
1. **repository.py работает с `monitoring.aged_positions`** - таблица НЕ СУЩЕСТВУЕТ
2. **База данных имеет `public.aged_positions`** - таблица СУЩЕСТВУЕТ (из миграции 008)
3. **Миграция 009** (`monitoring.aged_positions`) НИКОГДА НЕ ПРИМЕНЯЛАСЬ
4. **SQL в repository.py использует `%(name)s`** - НЕ РАБОТАЕТ с asyncpg (требует `$1, $2...`)

### Структура реальной таблицы (public.aged_positions):
```sql
CREATE TABLE aged_positions (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    entry_price NUMERIC NOT NULL,
    target_price NUMERIC NOT NULL,
    phase VARCHAR(50) NOT NULL,          -- ✅ ЕСТЬ
    hours_aged INTEGER NOT NULL,
    loss_tolerance NUMERIC,              -- ✅ ЕСТЬ
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(position_id)
);
```

---

## ERROR 1: `mark_aged_position_closed()` - unexpected keyword 'position_id'

### Расположение ошибки:
- **Вызов:** core/aged_position_monitor_v2.py:333-338
- **Метод:** database/repository.py:1267-1328

### Анализ вызова (строки 333-338):
```python
await self.repository.mark_aged_position_closed(
    position_id=target.position_id,  # ❌ ОШИБКА: параметр не существует
    order_id=result.order_id,        # ❌ ОШИБКА: должно быть close_order_id
    close_price=result.price,
    close_reason=f'aged_{target.phase}'
    # ❌ ОТСУТСТВУЮТ: actual_pnl, actual_pnl_percent
)
```

### Сигнатура метода (строки 1267-1276):
```python
async def mark_aged_position_closed(
    self,
    aged_id: str,              # ← Требует aged_id, НЕ position_id
    close_price: Decimal,
    close_order_id: str,       # ← Требует close_order_id, НЕ order_id
    actual_pnl: Decimal,       # ← ОБЯЗАТЕЛЬНЫЙ параметр
    actual_pnl_percent: Decimal, # ← ОБЯЗАТЕЛЬНЫЙ параметр
    close_reason: str,
    close_attempts: int = 1
) -> bool:
```

### SQL запрос (строки 1291-1305):
```sql
UPDATE monitoring.aged_positions  -- ❌ Таблица НЕ СУЩЕСТВУЕТ
SET
    status = 'closed',
    closed_at = NOW(),
    close_price = %(close_price)s,  -- ❌ Неправильный синтаксис для asyncpg
    ...
WHERE id = %(aged_id)s
```

### Проблемы:
1. ❌ **Вызов передает `position_id` вместо `aged_id`**
2. ❌ **Вызов передает `order_id` вместо `close_order_id`**
3. ❌ **Вызов НЕ передает `actual_pnl` и `actual_pnl_percent`**
4. ❌ **SQL работает с `monitoring.aged_positions` (не существует)**
5. ❌ **SQL использует `%(name)s` вместо `$1` (asyncpg не поддерживает)**
6. ❌ **Таблица public.aged_positions НЕ ИМЕЕТ колонок `status`, `closed_at`, `close_order_id`, `actual_pnl`, `actual_pnl_percent`, `close_attempts`**

---

## ERROR 2: `create_aged_position()` - unexpected keyword 'phase'

### Расположение ошибки:
- **Вызов:** core/aged_position_monitor_v2.py:177-186
- **Метод:** database/repository.py:1031-1104

### Анализ вызова (строки 177-186):
```python
await self.repository.create_aged_position(
    position_id=target.position_id,
    symbol=symbol,
    exchange=position.exchange,
    entry_price=target.entry_price,
    target_price=target_price,
    phase=phase,                    # ❌ Параметр не существует
    loss_tolerance=loss_tolerance,  # ❌ Параметр не существует
    age_hours=age_hours             # ❌ Параметр не существует
)
```

### Сигнатура метода (строки 1031-1044):
```python
async def create_aged_position(
    self,
    position_id: int,
    symbol: str,
    exchange: str,
    side: str,                      # ← ОТСУТСТВУЕТ в вызове
    entry_price: Decimal,
    quantity: Decimal,              # ← ОТСУТСТВУЕТ в вызове
    position_opened_at: datetime,   # ← ОТСУТСТВУЕТ в вызове
    detected_at: datetime,          # ← ОТСУТСТВУЕТ в вызове
    status: str,                    # ← ОТСУТСТВУЕТ в вызове
    target_price: Decimal,
    breakeven_price: Decimal,       # ← ОТСУТСТВУЕТ в вызове
    config: Dict                    # ← ОТСУТСТВУЕТ в вызове
) -> Dict:
```

### SQL запрос (строки 1066-1079):
```sql
INSERT INTO monitoring.aged_positions (  -- ❌ Таблица НЕ СУЩЕСТВУЕТ
    position_id, symbol, exchange, side,
    entry_price, quantity, position_opened_at,
    detected_at, status, target_price,
    breakeven_price, config, hours_aged,
    current_phase, current_loss_tolerance_percent  -- ❌ Колонки НЕ СУЩЕСТВУЮТ
) VALUES (
    %(position_id)s, %(symbol)s, ...  -- ❌ Неправильный синтаксис для asyncpg
    ...
)
```

### Проблемы:
1. ❌ **Вызов передает `phase`, `loss_tolerance`, `age_hours` - метод их НЕ принимает**
2. ❌ **Вызов НЕ передает 7 ОБЯЗАТЕЛЬНЫХ параметров:**
   - `side`
   - `quantity`
   - `position_opened_at`
   - `detected_at`
   - `status`
   - `breakeven_price`
   - `config`
3. ❌ **SQL работает с `monitoring.aged_positions` (не существует)**
4. ❌ **SQL пытается вставить в колонки `current_phase`, `current_loss_tolerance_percent`, `hours_aged` (НЕ существуют в миграции 009)**
5. ❌ **SQL использует `%(name)s` вместо `$1` (asyncpg не поддерживает)**
6. ❌ **Реальная таблица `public.aged_positions` имеет ДРУГУЮ структуру**

---

# 🎯 КОРНЕВАЯ ПРИЧИНА

**repository.py написан для миграции 009 (`monitoring.aged_positions`), но:**
1. Миграция 009 НИКОГДА НЕ применялась
2. База использует миграцию 008 (`public.aged_positions`)
3. Структуры таблиц РАДИКАЛЬНО различаются
4. SQL синтаксис несовместим с asyncpg

---

# ✅ РЕШЕНИЕ

## Вариант A: Использовать public.aged_positions (РЕКОМЕНДУЕТСЯ)

### Обоснование:
- ✅ Таблица уже существует и работает
- ✅ Структура проще и соответствует aged_position_monitor_v2.py
- ✅ Не требует миграции и изменений базы
- ✅ Меньше изменений кода

### План действий:

#### ФИК СС 1: Переписать `create_aged_position` под public.aged_positions

**Файл:** database/repository.py:1031-1104

**Новая сигнатура:**
```python
async def create_aged_position(
    self,
    position_id: str,           # VARCHAR(255), not int
    symbol: str,
    exchange: str,
    entry_price: Decimal,
    target_price: Decimal,
    phase: str,                 # grace, progressive, etc.
    age_hours: float,           # renamed from hours_aged
    loss_tolerance: Decimal = None
) -> Dict:
```

**Новый SQL (asyncpg-compatible):**
```python
query = """
    INSERT INTO aged_positions (
        position_id, symbol, exchange,
        entry_price, target_price, phase,
        hours_aged, loss_tolerance,
        created_at, updated_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
    ON CONFLICT (position_id) DO UPDATE SET
        target_price = EXCLUDED.target_price,
        phase = EXCLUDED.phase,
        hours_aged = EXCLUDED.hours_aged,
        loss_tolerance = EXCLUDED.loss_tolerance,
        updated_at = NOW()
    RETURNING *
"""

async with self.pool.acquire() as conn:
    try:
        row = await conn.fetchrow(
            query,
            str(position_id),
            symbol,
            exchange,
            entry_price,
            target_price,
            phase,
            int(age_hours),  # Convert to integer
            loss_tolerance
        )
        logger.info(f"Created/updated aged_position {row['id']} for {symbol}")
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to create aged_position: {e}")
        raise
```

#### ФИК 2: Переписать `mark_aged_position_closed` под public.aged_positions

**Файл:** database/repository.py:1267-1328

**Проблема:** Таблица `public.aged_positions` НЕ ИМЕЕТ колонок для closed positions!

**Решение:** Просто УДАЛИТЬ запись из aged_positions при закрытии (или добавить флаг)

**Новая сигнатура:**
```python
async def mark_aged_position_closed(
    self,
    position_id: str,           # Changed from aged_id
    close_reason: str
) -> bool:
```

**Новый SQL:**
```python
query = """
    DELETE FROM aged_positions
    WHERE position_id = $1
    RETURNING id
"""

async with self.pool.acquire() as conn:
    try:
        result = await conn.fetchval(query, str(position_id))
        if result:
            logger.info(f"Marked aged position {position_id} as closed (reason: {close_reason})")
            return True
        else:
            logger.warning(f"Aged position {position_id} not found")
            return False
    except Exception as e:
        logger.error(f"Failed to mark aged position as closed: {e}")
        return False
```

#### ФИК 3: Исправить вызовы в aged_position_monitor_v2.py

**Файл:** core/aged_position_monitor_v2.py

**Вызов create_aged_position (строка 177):**
```python
# ТЕКУЩИЙ (НЕПРАВИЛЬНЫЙ):
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

# ИСПРАВЛЕННЫЙ (уже соответствует новой сигнатуре):
await self.repository.create_aged_position(
    position_id=str(target.position_id),  # Ensure string
    symbol=symbol,
    exchange=position.exchange,
    entry_price=target.entry_price,
    target_price=target_price,
    phase=phase,
    age_hours=age_hours,
    loss_tolerance=loss_tolerance
)
```

**Вызов mark_aged_position_closed (строка 333):**
```python
# ТЕКУЩИЙ (НЕПРАВИЛЬНЫЙ):
await self.repository.mark_aged_position_closed(
    position_id=target.position_id,
    order_id=result.order_id,
    close_price=result.price,
    close_reason=f'aged_{target.phase}'
)

# ИСПРАВЛЕННЫЙ:
await self.repository.mark_aged_position_closed(
    position_id=str(target.position_id),
    close_reason=f'aged_{target.phase}'
)
```

---

## Вариант B: Применить миграцию 009 и исправить методы (НЕ РЕКОМЕНДУЕТСЯ)

### Проблемы:
- ❌ Требует применения миграции 009
- ❌ Создаст дубликаты данных (public.aged_positions + monitoring.aged_positions)
- ❌ Требует больше изменений кода
- ❌ Более сложная структура

---

# 🧪 ТЕСТЫ ДЛЯ ВАЛИДАЦИИ

## Тест 1: Проверка сигнатуры create_aged_position

```python
import inspect
from database.repository import Repository

# Check signature
sig = inspect.signature(Repository.create_aged_position)
params = sig.parameters

# Expected parameters
expected = ['self', 'position_id', 'symbol', 'exchange', 'entry_price',
            'target_price', 'phase', 'age_hours', 'loss_tolerance']

actual = list(params.keys())
assert actual == expected, f"Signature mismatch: {actual} != {expected}"

# Check SQL uses positional parameters
import ast
source = inspect.getsource(Repository.create_aged_position)
assert '$1' in source and '$2' in source, "SQL should use $1, $2... parameters"
assert '%(name)s' not in source, "SQL should NOT use %(name)s parameters"
```

## Тест 2: Проверка сигнатуры mark_aged_position_closed

```python
import inspect
from database.repository import Repository

sig = inspect.signature(Repository.mark_aged_position_closed)
params = sig.parameters

# Expected parameters
expected = ['self', 'position_id', 'close_reason']

actual = list(params.keys())
assert actual == expected, f"Signature mismatch: {actual} != {expected}"
```

## Тест 3: Проверка вызовов в aged_position_monitor_v2.py

```python
import inspect
from core.aged_position_monitor_v2 import AgedPositionMonitorV2

source = inspect.getsource(AgedPositionMonitorV2.add_aged_position)

# Check create_aged_position call has correct parameters
assert 'position_id=' in source
assert 'symbol=' in source
assert 'exchange=' in source
assert 'phase=' in source
assert 'age_hours=' in source
```

---

# 📋 ЧЕКЛИСТ ПЕРЕД ПРИМЕНЕНИЕМ

- [ ] Создать бэкапы:
  ```bash
  cp database/repository.py database/repository.py.backup_aged_fix_$(date +%Y%m%d_%H%M%S)
  cp core/aged_position_monitor_v2.py core/aged_position_monitor_v2.py.backup_aged_fix_$(date +%Y%m%d_%H%M%S)
  ```

- [ ] Проверить текущую структуру таблицы:
  ```sql
  SELECT column_name, data_type
  FROM information_schema.columns
  WHERE table_name = 'aged_positions' AND table_schema = 'public';
  ```

- [ ] Проверить текущие данные:
  ```sql
  SELECT COUNT(*) FROM aged_positions;
  SELECT * FROM aged_positions LIMIT 5;
  ```

---

# ⚠️ РИСКИ И МИТИГАЦИЯ

## Риск 1: Потеря данных о закрытых позициях
- **Проблема:** DELETE удаляет записи навсегда
- **Митигация:**
  - Логировать в aged_monitoring_events перед удалением
  - Или добавить колонку `status` в public.aged_positions

## Риск 2: Несовместимость с будущей миграцией 009
- **Проблема:** Если позже применим миграцию 009
- **Митигация:**
  - Документировать что используем миграцию 008
  - Создать план миграции с 008 на 009 при необходимости

---

# 🎯 ПРИОРИТЕТ

**КРИТИЧЕСКИЙ** - Блокирует работу aged_position_monitor_v2

**Влияние:**
- Невозможно отслеживать aged позиции в базе
- Невозможно закрыть aged позиции
- Накапливаются необработанные позиции

**Рекомендуемое время исправления:** НЕМЕДЛЕННО

---

**Автор:** AI Assistant
**Дата:** 2025-10-23 22:40
**Версия:** 1.0 FINAL
