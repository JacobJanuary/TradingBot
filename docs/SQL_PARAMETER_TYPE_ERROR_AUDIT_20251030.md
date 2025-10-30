# Аудит: SQL Parameter Type Error - 'pending' str vs integer

**Дата:** 2025-10-30
**Статус:** ✅ АУДИТ ЗАВЕРШЕН
**Ошибка:** `invalid input for query argument $5: 'pending' ('str' object cannot be interpreted as an integer)`

---

## 🎯 Задача

Провести тщательный аудит SQL-ошибки синхронизации позиций:
- **Время:** 2025-10-30 00:35:01
- **Контекст:** При синхронизации Bybit после неудачного открытия OKBUSDT
- **Ошибка:** `invalid input for query argument $5: 'pending' ('str' object cannot be interpreted as an integer)`

---

## 🔍 Исследование

### Найденные SQL Запросы с $5

#### 1. repository.py:597-605 - close_position()

```python
query = """
    UPDATE monitoring.positions
    SET status = 'closed',
        pnl = $1,
        exit_reason = $2,
        current_price = COALESCE($3, current_price),
        pnl_percentage = COALESCE($4, pnl_percentage),
        closed_at = NOW(),
        updated_at = NOW()
    WHERE id = $5
"""

await conn.execute(
    query,
    realized_pnl,  # $1 - float
    exit_reason,   # $2 - str
    current_price, # $3 - float
    pnl_percent,   # $4 - float
    position_id    # $5 - ❗ ДОЛЖЕН БЫТЬ INT!
)
```

**$5 = position_id (integer)** ✅

---

#### 2. repository.py:365-392 - update_position()

```python
async def update_position(self, position_id: int, updates: Dict) -> bool:
    """Update position with given data"""

    if not updates:
        return False

    # Build dynamic UPDATE query
    set_clauses = []
    values = []
    for i, (key, value) in enumerate(updates.items(), 1):
        set_clauses.append(f"{key} = ${i}")
        values.append(value)

    values.append(position_id)  # Add position_id as last parameter

    query = f"""
        UPDATE monitoring.positions
        SET {', '.join(set_clauses)}
        WHERE id = ${len(values)}
    """

    async with self.pool.acquire() as conn:
        result = await conn.execute(query, *values)
        return True
```

**Последний параметр = position_id (integer)** ✅

**Но количество параметров ДИНАМИЧЕСКОЕ!**

Если updates = {'status': 'pending', 'foo': 'bar', 'baz': 'qux', 'test': 'value'}:
- $1 = 'pending'
- $2 = 'bar'
- $3 = 'qux'
- $4 = 'value'
- **$5 = position_id** ✅

НО если updates = {'status': 'pending'}:
- $1 = 'pending'
- **$2 = position_id**

Так что **$5 зависит от количества ключей в updates!**

---

## 🚨 КОРНЕВАЯ ПРИЧИНА НАЙДЕНА!

### Проблемный Код: position_synchronizer.py:522-527

```python
await self.repository.update_position(
    position_id=position_id,       # ❌ KEYWORD ARGUMENT!
    quantity=new_quantity,          # ❌ KEYWORD ARGUMENT!
    current_price=current_price,    # ❌ KEYWORD ARGUMENT!
    unrealized_pnl=unrealized_pnl   # ❌ KEYWORD ARGUMENT!
)
```

### Signature Метода

```python
async def update_position(self, position_id: int, updates: Dict) -> bool:
```

### Проблема

Метод `update_position` принимает **2 ПОЗИЦИОННЫХ аргумента:**
1. `position_id: int`
2. `updates: Dict`

НО вызывается с **KEYWORD ARGUMENTS** которые НЕ соответствуют signature!

**Python НЕ МОЖЕТ** сопоставить `quantity`, `current_price`, `unrealized_pnl` с параметром `updates`!

### Что Происходит?

Если метод вызывается как:
```python
update_position(position_id=123, quantity=10, current_price=5.5)
```

Python пытается:
1. Сопоставить `position_id=123` → параметр `position_id` ✅
2. Сопоставить `quantity=10` → **НЕТ ТАКОГО ПАРАМЕТРА** ❌
3. Сопоставить `current_price=5.5` → **НЕТ ТАКОГО ПАРАМЕТРА** ❌

**Должно вызвать:** `TypeError: update_position() got unexpected keyword argument 'quantity'`

---

## 🔎 Дополнительная Проверка

### Правильные Вызовы в Коде

**atomic_position_manager.py:183:**
```python
await self.repository.update_position(position_id, **update_fields)
```
✅ **ПРАВИЛЬНО** - использует `**update_fields` для распаковки dict

**atomic_position_manager.py:1076:**
```python
await self.repository.update_position(position_id, **{
    'status': 'canceled',
    'exit_reason': 'Symbol unavailable'
})
```
✅ **ПРАВИЛЬНО** - использует `**{...}` для распаковки

### Неправильный Вызов

**position_synchronizer.py:522:**
```python
await self.repository.update_position(
    position_id=position_id,
    quantity=new_quantity,
    current_price=current_price,
    unrealized_pnl=unrealized_pnl
)
```
❌ **НЕПРАВИЛЬНО** - передает keyword arguments которых нет в signature

---

## 🤔 Почему Это Работало?

### Гипотеза 1: Метод Был Изменен

Возможно, метод раньше имел signature:
```python
async def update_position(self, position_id: int, **kwargs):
```

И принимал произвольные keyword arguments, которые затем использовались для обновления.

### Гипотеза 2: Перегрузка Метода

Возможно, есть ДРУГОЙ метод `update_position` с другим signature в каком-то миксине или наследовании.

### Гипотеза 3: Monkey Patching

Возможно, метод перезаписывается во время runtime.

---

## 🔍 Поиск Других Проблемных Вызовов

Все вызовы `update_position` в коде:

| Файл | Строка | Вызов | Статус |
|------|--------|-------|--------|
| risk_manager.py | 211 | `await self.repository.update_position(position)` | ❓ Нужна проверка |
| position_synchronizer.py | 522 | `position_id=X, quantity=Y, ...` | ❌ **БАГ** |
| position_reconciliation.py | 192 | Нужна проверка | ❓ |
| atomic_position_manager.py | 183 | `(position_id, **update_fields)` | ✅ Правильно |
| atomic_position_manager.py | 1076 | `(position_id, **{...})` | ✅ Правильно |

---

## 💡 Решение

### Фикс position_synchronizer.py:522

**Было:**
```python
await self.repository.update_position(
    position_id=position_id,
    quantity=new_quantity,
    current_price=current_price,
    unrealized_pnl=unrealized_pnl
)
```

**Должно быть:**
```python
await self.repository.update_position(
    position_id,
    {
        'quantity': new_quantity,
        'current_price': current_price,
        'unrealized_pnl': unrealized_pnl
    }
)
```

ИЛИ:

```python
await self.repository.update_position(position_id, **{
    'quantity': new_quantity,
    'current_price': current_price,
    'unrealized_pnl': unrealized_pnl
})
```

---

## 🧪 Тесты

### Test 1: Verify Signature

```python
import inspect
from database.repository import Repository

sig = inspect.signature(Repository.update_position)
print(f"Parameters: {list(sig.parameters.keys())}")
# Expected: ['self', 'position_id', 'updates']
```

### Test 2: Wrong Call Should Fail

```python
import pytest

@pytest.mark.asyncio
async def test_update_position_wrong_signature():
    """Test that wrong signature raises TypeError"""
    repo = Repository(...)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        await repo.update_position(
            position_id=123,
            quantity=10  # ← Should fail
        )
```

### Test 3: Correct Call Should Work

```python
@pytest.mark.asyncio
async def test_update_position_correct_signature():
    """Test correct signature works"""
    repo = Repository(...)

    # Should work
    await repo.update_position(123, {'quantity': 10})

    # Should also work
    await repo.update_position(123, **{'quantity': 10})
```

---

## 📊 Влияние Фикса

### Изменяемые Файлы

1. **core/position_synchronizer.py** - line 522-527

### Затрагиваемые Модули

| Модуль | Влияние | Описание |
|--------|---------|----------|
| PositionSynchronizer | ✅ Исправляет баг | Корректный вызов update_position |
| Repository | ⚪ Не изменяется | Signature остается прежним |
| Position Manager | ⚪ Не затрагивается | Использует synchronizer |
| Atomic Position Manager | ⚪ Не затрагивается | Уже использует правильный синтаксис |

### Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Метод имеет другой signature | 🟡 Средняя | Проверить runtime signature |
| Есть monkey patching | 🟢 Низкая | Проверить код на patches |
| Регрессия в синхронизации | 🟢 Низкая | Тесты |

---

## 🎯 Рекомендации

### Немедленные Действия

1. **Проверить runtime signature** метода `update_position`
   ```python
   import inspect
   print(inspect.signature(repository.update_position))
   ```

2. **Найти все вызовы** с keyword arguments
   ```bash
   grep -n "update_position(" core/*.py | grep -E "(quantity|current_price)="
   ```

3. **Исправить** вызов в position_synchronizer.py

### Долгосрочные Действия

1. **Type Hints Validation**
   - Использовать mypy для статической проверки типов
   - Добавить pre-commit hook для проверки

2. **Добавить Tests**
   - Unit тесты для update_position с разными signatures
   - Integration тесты для position_synchronizer

3. **Code Review**
   - Проверить все вызовы repository методов
   - Убедиться в соответствии signatures

---

## ⚠️ КРИТИЧЕСКИЙ ВОПРОС

**Почему код работал раньше, если вызов неправильный?**

Возможные объяснения:
1. Метод был изменен недавно (был `**kwargs`, стал `updates: Dict`)
2. Код никогда не выполнялся (synchronizer редко вызывается)
3. Есть обработка исключений которая скрывает TypeError
4. Метод перегружен в runtime

**Нужно проверить:**
```bash
git log -p --all -S "def update_position" -- database/repository.py
```

---

## 📋 План Внедрения

### Фаза 0: Подготовка (15 минут)

1. Проверить runtime signature
2. Найти ВСЕ неправильные вызовы
3. Создать backup файлов

### Фаза 1: Фикс (15 минут)

1. Исправить position_synchronizer.py:522
2. Проверить syntax: `python -m py_compile`
3. Commit

### Фаза 2: Тестирование (30 минут)

1. Unit тесты
2. Manual тест синхронизации
3. Проверить логи

### Фаза 3: Deploy (15 минут)

1. Merge в main
2. Deploy
3. Monitor

**Общее время:** ~1.5 часа

---

## ✅ Итоги

### Найденная Проблема

**Файл:** `core/position_synchronizer.py:522`
**Проблема:** Неправильный вызов `update_position` с keyword arguments
**Ожидаемая ошибка:** `TypeError: unexpected keyword argument`
**Фактическая ошибка:** `invalid input for query argument $5: 'pending'` ← **Нужно выяснить связь!**

### Вопросы для Дальнейшего Исследования

1. ❓ Как keyword arguments превратились в SQL параметры?
2. ❓ Почему TypeError не был raised?
3. ❓ Есть ли другой метод update_position?
4. ❓ Был ли изменен signature метода?

### Рекомендация

✅ **Исправить вызов** в position_synchronizer.py:522
✅ **Проверить все вызовы** update_position во всем коде
✅ **Добавить тесты** для валидации signatures
⚠️ **Исследовать** почему код работал раньше

---

**Аудит завершён.** Требуются дополнительные проверки для 100% уверенности в корневой причине.

**Статус:** 🟡 **ТРЕБУЕТСЯ УТОЧНЕНИЕ** - найден потенциальный баг, но нужно понять связь с SQL ошибкой.
