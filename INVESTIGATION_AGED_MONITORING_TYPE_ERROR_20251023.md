# 🔍 РАССЛЕДОВАНИЕ: Type Error в create_aged_monitoring_event

## Дата: 2025-10-23 23:18
## Статус: INVESTIGATION COMPLETED - PLAN READY

---

# 📊 ОШИБКА

```
2025-10-23 23:16:48,122 - database.repository - ERROR - Failed to create monitoring event: invalid input for query argument $1: 2745 (expected str, got int)
```

---

# 🔎 ГЛУБОКОЕ РАССЛЕДОВАНИЕ

## НАЙДЕННАЯ ПРОБЛЕМА: Type Mismatch - int вместо str

### Факты:

1. **Метод `create_aged_monitoring_event`** ожидает `aged_position_id: str`
2. **Таблица `aged_monitoring_events`** требует `aged_position_id VARCHAR(255)`
3. **Вызовы передают** `target.position_id` без конвертации в str
4. **Источник int**: `position.id` возвращает int (например, 2745)
5. **AgedPositionTarget dataclass** определяет `position_id: str`, но НЕ валидирует тип при создании

---

## ДЕТАЛЬНЫЙ АНАЛИЗ

### 1. Метод create_aged_monitoring_event

**Файл:** database/repository.py:1196-1250

**Сигнатура:**
```python
async def create_aged_monitoring_event(
    self,
    aged_position_id: str,  # ← ТРЕБУЕТ строку
    event_type: str,
    market_price: Decimal = None,
    target_price: Decimal = None,
    price_distance_percent: Decimal = None,
    action_taken: str = None,
    success: bool = None,
    error_message: str = None,
    event_metadata: Dict = None
) -> bool:
```

**SQL запрос (строки 1224-1230):**
```sql
INSERT INTO aged_monitoring_events (
    aged_position_id, event_type, market_price,
    target_price, price_distance_percent,
    action_taken, success, error_message,
    event_metadata, created_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
```

**Проблема:**
- `$1` - это `aged_position_id`
- asyncpg получает int (2745), но ожидает str
- Ошибка: "invalid input for query argument $1: 2745 (expected str, got int)"

---

### 2. Структура таблицы aged_monitoring_events

**Файл:** database/migrations/008_create_aged_tables.sql:22-34

```sql
CREATE TABLE IF NOT EXISTS aged_monitoring_events (
    id SERIAL PRIMARY KEY,
    aged_position_id VARCHAR(255) NOT NULL,  -- ← ТРЕБУЕТ строку!
    event_type VARCHAR(50) NOT NULL,
    market_price DECIMAL(20, 8),
    target_price DECIMAL(20, 8),
    price_distance_percent DECIMAL(10, 4),
    action_taken VARCHAR(100),
    success BOOLEAN,
    error_message TEXT,
    event_metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Ожидаемый тип:** VARCHAR(255) - СТРОКА

---

### 3. Вызовы метода с ошибкой

**Файл:** core/aged_position_monitor_v2.py

#### Вызов 1: price_check event (строка 253-258)
```python
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,  # ❌ int вместо str
    event_type='price_check',
    market_price=current_price,
    target_price=target.target_price,
    price_distance_percent=abs((current_price - target.target_price) / target.target_price * Decimal('100')),
)
```

#### Вызов 2: closed event (строка 346-355)
```python
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,  # ❌ int вместо str
    event_type='closed',
    event_metadata={
        'order_id': result.order_id,
        'order_type': result.order_type,
        'price': result.price,
        'executed_quantity': result.executed_quantity
    }
)
```

#### Вызов 3: close_failed event (строка 371-378)
```python
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,  # ❌ int вместо str
    event_type='close_failed',
    event_metadata={
        'error': result.error_message,
        'attempts': result.attempts,
        'trigger_price': trigger_price
    }
)
```

#### Вызов 4: phase_change event (строка 483-491)
```python
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,  # ❌ int вместо str
    event_type='phase_change',
    event_metadata={
        'old_phase': old_phase,
        'new_phase': new_phase,
        'hours_aged': self.aged_targets[symbol].hours_aged,
        'loss_tolerance': str(self.aged_targets[symbol].loss_tolerance)
    }
)
```

**ВСЕГО: 4 вызова с ошибкой**

---

### 4. Источник проблемы: Создание AgedPositionTarget

**Файл:** core/aged_position_monitor_v2.py

#### Определение dataclass (строки 40-49)
```python
@dataclass
class AgedPositionTarget:
    """Simple target tracking for aged position"""
    symbol: str
    entry_price: Decimal
    target_price: Decimal
    phase: str  # 'grace', 'progressive', 'emergency'
    loss_tolerance: Decimal
    hours_aged: float
    position_id: str  # ← ОПРЕДЕЛЕН КАК str
```

#### Создание target с int (строка 150-158) - ❌ ПРОБЛЕМА ЗДЕСЬ
```python
target = AgedPositionTarget(
    symbol=symbol,
    entry_price=Decimal(str(position.entry_price)),
    target_price=target_price,
    phase=phase,
    loss_tolerance=loss_tolerance,
    hours_aged=age_hours,
    position_id=getattr(position, 'id', symbol)  # ❌ position.id возвращает int!
)
```

**КОРНЕВАЯ ПРИЧИНА:**
- `position.id` возвращает **int** (например, 2745)
- Python dataclass НЕ валидирует типы по умолчанию
- `position_id: str` - это только аннотация, НЕ принудительное ограничение
- Поэтому int присваивается без ошибки
- НО позже при передаче в asyncpg - ошибка!

#### Создание target из БД (строка 557-565) - ✅ КОРРЕКТНО
```python
target = AgedPositionTarget(
    symbol=db_record['symbol'],
    entry_price=Decimal(str(db_record['entry_price'])),
    target_price=Decimal(str(db_record['target_price'])),
    phase=db_record['phase'],
    loss_tolerance=Decimal(str(db_record['loss_tolerance'])),
    hours_aged=float(db_record.get('age_hours', 0)),
    position_id=db_record['position_id']  # ✅ Из БД уже str (VARCHAR)
)
```

---

## 🎯 КОРНЕВАЯ ПРИЧИНА

**`position.id` возвращает int, НЕ конвертируется в str при создании AgedPositionTarget**

**Влияние:**
1. ❌ `target.position_id` содержит int вместо str
2. ❌ Все 4 вызова `create_aged_monitoring_event` передают int
3. ❌ asyncpg отклоняет int для VARCHAR(255) колонки
4. ❌ Monitoring events НЕ записываются в базу

---

# ✅ РЕШЕНИЕ

## ВАРИАНТ A: Исправить создание AgedPositionTarget (РЕКОМЕНДУЕТСЯ)

### Обоснование:
- ✅ Исправляет проблему в источнике (1 место)
- ✅ Гарантирует что position_id всегда str
- ✅ Соответствует dataclass аннотации
- ✅ Не требует изменения 4 вызовов

### План действий:

#### ФИК: Конвертировать position.id в str при создании

**Файл:** core/aged_position_monitor_v2.py:157

**ТЕКУЩИЙ КОД (НЕПРАВИЛЬНЫЙ):**
```python
position_id=getattr(position, 'id', symbol)
```

**ИСПРАВЛЕННЫЙ КОД:**
```python
position_id=str(getattr(position, 'id', symbol))
```

**Обоснование:**
- `str()` конвертирует int → str
- Если position.id = 2745 (int) → "2745" (str)
- Если fallback на symbol → symbol уже str
- Безопасно для обоих случаев

---

## ВАРИАНТ B: Исправить все 4 вызова (НЕ РЕКОМЕНДУЕТСЯ)

### Проблемы:
- ❌ Требует изменения в 4 местах
- ❌ Оставляет несоответствие типа в dataclass
- ❌ Может привести к проблемам в будущем

### План:
Изменить все 4 вызова:
```python
aged_position_id=str(target.position_id)
```

---

# 🧪 ТЕСТЫ ДЛЯ ВАЛИДАЦИИ

## Тест 1: Проверка создания AgedPositionTarget

```python
import inspect
from core.aged_position_monitor_v2 import AgedPositionMonitorV2

# Get source code
source = inspect.getsource(AgedPositionMonitorV2.add_aged_position)

# Check that position_id is converted to str
assert 'str(getattr(position' in source, "position_id должен конвертироваться через str()"

# Check the exact line
assert 'position_id=str(getattr(position, \'id\'' in source or \
       'position_id = str(getattr(position, \'id\'' in source, \
       "position_id должен использовать str(getattr(...))"
```

## Тест 2: Проверка типа position_id в AgedPositionTarget

```python
from decimal import Decimal
from core.aged_position_monitor_v2 import AgedPositionTarget

# Create target with int (simulating position.id)
target = AgedPositionTarget(
    symbol='BTCUSDT',
    entry_price=Decimal('50000'),
    target_price=Decimal('49000'),
    phase='grace',
    loss_tolerance=Decimal('0.5'),
    hours_aged=2.5,
    position_id=str(2745)  # After fix: should be str
)

# Validate type
assert isinstance(target.position_id, str), "position_id должен быть str"
assert target.position_id == "2745", "position_id должен содержать '2745'"
```

## Тест 3: Интеграционный тест с create_aged_monitoring_event

```python
# Mock repository call
class MockRepo:
    async def create_aged_monitoring_event(self, aged_position_id, **kwargs):
        # Validate type
        assert isinstance(aged_position_id, str), \
            f"aged_position_id должен быть str, получен {type(aged_position_id)}"
        return True

# Test would verify that all 4 calls pass str, not int
```

---

# 📋 ЧЕКЛИСТ ПЕРЕД ПРИМЕНЕНИЕМ

- [ ] Создать бэкап:
  ```bash
  cp core/aged_position_monitor_v2.py core/aged_position_monitor_v2.py.backup_monitoring_fix_$(date +%Y%m%d_%H%M%S)
  ```

- [ ] Проверить все использования position_id:
  ```bash
  grep -n "position_id" core/aged_position_monitor_v2.py
  ```

- [ ] Убедиться что исправление НЕ сломает другие части:
  - create_aged_position call (строка 178) - уже использует str()
  - mark_aged_position_closed call (строка 334) - уже использует str()

---

# ⚠️ РИСКИ И МИТИГАЦИЯ

## Риск 1: Двойная конвертация
- **Проблема:** Если position.id уже str, то str(str) = str (безопасно)
- **Митигация:** str() идемпотентна, не создает проблем

## Риск 2: Fallback на symbol
- **Проблема:** Если getattr возвращает symbol (str), то str(symbol) = symbol
- **Митигация:** Безопасно, str() для str возвращает ту же строку

---

# 🎯 ПРИОРИТЕТ

**КРИТИЧЕСКИЙ** - Блокирует запись monitoring events

**Влияние:**
- Невозможно отслеживать события aged позиций
- Теряется важная информация для дебага
- Накапливаются необработанные ошибки

**Рекомендуемое время исправления:** НЕМЕДЛЕННО

---

# 📝 СВЯЗЬ С ПРЕДЫДУЩИМИ ФИКСАМИ

Это **ПРОДОЛЖЕНИЕ** проблемы из INVESTIGATION_AGED_METHODS_MISMATCH_20251023.md

**Предыдущие фиксы:**
- ✅ ФИК 1: create_aged_position - добавлен str() (строка 178)
- ✅ ФИК 2: mark_aged_position_closed - добавлен str() (строка 334)
- ❌ **НЕ ИСПРАВЛЕНО**: create_aged_monitoring_event (4 вызова)

**Та же корневая причина:**
- `position.id` возвращает int
- База требует VARCHAR(255)
- asyncpg требует str для $1 параметра

**Решение:**
Исправить в ИСТОЧНИКЕ (создание AgedPositionTarget), а не в 4 вызовах

---

**Автор:** AI Assistant
**Дата:** 2025-10-23 23:18
**Версия:** 1.0 FINAL
