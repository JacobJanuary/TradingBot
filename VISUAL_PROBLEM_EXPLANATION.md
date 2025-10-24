# 🎯 ВИЗУАЛИЗАЦИЯ ПРОБЛЕМЫ

## FLOW ДО ФИКСА (❌ ОШИБКА)

```
position.id = 2745 (int)
    ↓
getattr(position, 'id', symbol)
    ↓
position_id = 2745 (int)  ← НЕТ str()!
    ↓
AgedPositionTarget(
    ...
    position_id=2745  ← int попадает в dataclass
)
    ↓
target.position_id = 2745 (int)  ← dataclass НЕ валидирует!
    ↓
create_aged_monitoring_event(
    aged_position_id=target.position_id  ← передается int
)
    ↓
SQL: INSERT INTO aged_monitoring_events (aged_position_id, ...) VALUES ($1, ...)
    ↓
asyncpg: $1 = 2745 (int)
    ↓
Таблица: aged_position_id VARCHAR(255) NOT NULL
    ↓
❌ ERROR: invalid input for query argument $1: 2745 (expected str, got int)
```

## FLOW ПОСЛЕ ФИКСА (✅ РАБОТАЕТ)

```
position.id = 2745 (int)
    ↓
str(getattr(position, 'id', symbol))  ← ✅ ДОБАВЛЕН str()!
    ↓
position_id = "2745" (str)
    ↓
AgedPositionTarget(
    ...
    position_id="2745"  ← str попадает в dataclass
)
    ↓
target.position_id = "2745" (str)  ← ✅ КОРРЕКТНЫЙ ТИП!
    ↓
create_aged_monitoring_event(
    aged_position_id=target.position_id  ← передается str
)
    ↓
SQL: INSERT INTO aged_monitoring_events (aged_position_id, ...) VALUES ($1, ...)
    ↓
asyncpg: $1 = "2745" (str)
    ↓
Таблица: aged_position_id VARCHAR(255) NOT NULL
    ↓
✅ SUCCESS: Запись создана
```

## ПОЧЕМУ ПРОБЛЕМА НЕ ВЫЯВИЛАСЬ РАНЬШЕ?

```python
@dataclass
class AgedPositionTarget:
    position_id: str  # ← Это ТОЛЬКО аннотация, НЕ проверка!
```

**Python dataclass НЕ валидирует типы:**
```python
target = AgedPositionTarget(position_id=2745)  # int
# ✅ Работает! НЕТ ошибки!

print(type(target.position_id))  # <class 'int'>
# ⚠️ position_id аннотирован как str, но содержит int!
```

**Ошибка проявляется только при взаимодействии с asyncpg:**
```python
await conn.execute("INSERT ... VALUES ($1)", target.position_id)
# ❌ asyncpg: "expected str, got int"
```

## ПОЧЕМУ 1 СТРОКА ФИКСИТ 4 ВЫЗОВА?

**ПРОБЛЕМА В ИСТОЧНИКЕ:**
```python
# aged_position_monitor_v2.py:157
position_id=getattr(position, 'id', symbol)  # ← int попадает сюда
```

**4 ВЫЗОВА ИСПОЛЬЗУЮТ ЭТО ЗНАЧЕНИЕ:**
```python
# Вызов 1 (строка 254)
create_aged_monitoring_event(aged_position_id=target.position_id)

# Вызов 2 (строка 347)
create_aged_monitoring_event(aged_position_id=target.position_id)

# Вызов 3 (строка 372)
create_aged_monitoring_event(aged_position_id=target.position_id)

# Вызов 4 (строка 484)
create_aged_monitoring_event(aged_position_id=target.position_id)
```

**РЕШЕНИЕ:**
Исправить 1 раз в ИСТОЧНИКЕ → все 4 вызова получат str автоматически!

```python
# aged_position_monitor_v2.py:157
position_id=str(getattr(position, 'id', symbol))  # ← ✅ ФИК
```

## СВЯЗЬ С ПРЕДЫДУЩИМИ ФИКСАМИ

**ТА ЖЕ ПРОБЛЕМА:**
```
position.id = int (2745)
База = VARCHAR(255)
asyncpg = требует str
```

**ПРЕДЫДУЩИЕ ФИКСЫ:**
```python
# ФИК 1 (коммит 0989488): create_aged_position
await self.repository.create_aged_position(
    position_id=str(target.position_id),  # ← добавлен str()
    ...
)

# ФИК 2 (коммит c74489a): mark_aged_position_closed
await self.repository.mark_aged_position_closed(
    position_id=str(target.position_id),  # ← добавлен str()
    ...
)
```

**НОВЫЙ ФИК (строка 157):**
```python
# Исправить В ИСТОЧНИКЕ
position_id=str(getattr(position, 'id', symbol))  # ← str() ЗДЕСЬ!

# Тогда ВСЕ вызовы автоматически получат str:
# - create_aged_position (уже есть str(), но станет избыточным)
# - mark_aged_position_closed (уже есть str(), но станет избыточным)
# - create_aged_monitoring_event (4 вызова) - БУДУТ РАБОТАТЬ!
```

## ИТОГО

**ПРОБЛЕМА:** 1 место (создание target)
**ВЛИЯНИЕ:** 4 вызова create_aged_monitoring_event
**РЕШЕНИЕ:** 1 строка кода (добавить str())
**РЕЗУЛЬТАТ:** Все 4 вызова работают ✅
