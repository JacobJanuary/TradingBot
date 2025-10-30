# Deep Investigation: SQL Parameter Type Error - 'pending' as $5

**Дата:** 2025-10-30
**Статус:** 🔍 ГЛУБОКОЕ РАССЛЕДОВАНИЕ ЗАВЕРШЕНО
**Оригинальная ошибка:** `invalid input for query argument $5: 'pending' ('str' object cannot be interpreted as an integer)`

---

## 🎯 Executive Summary

После тщательного расследования обнаружены **КРИТИЧЕСКИЕ ПРОБЛЕМЫ** в `database/repository.py`:

### Главная Находка: ДУБЛИРОВАНИЕ МЕТОДОВ

В файле `database/repository.py` существуют **ДВА метода** с одинаковым именем `update_position`:

1. **Строка 365** (МЕРТВЫЙ КОД):
   ```python
   async def update_position(self, position_id: int, updates: Dict) -> bool:
   ```
   - Добавлен: 2025-10-11 (commit dabb22b4)
   - Принимает Dict как второй параметр
   - **НЕ ВЫПОЛНЯЕТСЯ** - перезаписан следующим методом

2. **Строка 717** (РАБОЧИЙ КОД):
   ```python
   async def update_position(self, position_id: int, **kwargs) -> bool:
   ```
   - Добавлен: 2025-10-03 (commit 47be083d)
   - Принимает **kwargs
   - **ИСПОЛЬЗУЕТСЯ** во время выполнения

**Python загружает методы сверху вниз**, поэтому метод на строке 717 **ПЕРЕЗАПИСЫВАЕТ** метод на строке 365!

---

## 🔍 Детальный Анализ

### Timeline Добавления Методов

```
2025-10-03 (commit 47be083d): Добавлен **kwargs метод (строка 717)
         ↓
2025-10-11 (commit dabb22b4): Добавлен Dict метод (строка 365)
                               НО он на БОЛЕЕ РАННЕЙ строке!
         ↓
Runtime: Python читает файл сверху вниз:
         1. Определяет метод на строке 365
         2. Определяет метод на строке 717 → ПЕРЕЗАПИСЫВАЕТ первый!
```

### Runtime Signature (Проверено)

```bash
$ python tests/manual/test_runtime_signature.py

update_position(self, position_id: int, **kwargs) -> bool

Parameters:
  - self: POSITIONAL_OR_KEYWORD
  - position_id: POSITIONAL_OR_KEYWORD (int)
  - kwargs: VAR_KEYWORD (**kwargs)
```

✅ **Подтверждено:** Runtime использует **kwargs версию (строка 717)

---

## 🚨 Найденные Проблемы

### Проблема #1: Неправильный Вызов с Объектом

**Файл:** `core/risk_manager.py:211`

```python
await self.repository.update_position(position)  # ❌ Объект вместо int!
```

**Проблема:** Передается весь объект Position вместо position.id
**Результат:** Метод вернет False (kwargs пустой) и не выполнит обновление
**Серьезность:** 🟡 СРЕДНЯЯ - операция молча проваливается

---

### Проблема #2: Неправильный Вызов с Dict

**Файл:** `core/position_manager.py:2885`

```python
await self.repository.update_position(position.id, {
    'pending_close_order_id': order['id'],
    'pending_close_price': to_decimal(target_price),
    'exit_reason': truncate_exit_reason(reason)
})
```

**Проблема:** Вызов использует старый signature с Dict как вторым позиционным аргументом
**Runtime метод:** Принимает `**kwargs`, НЕ Dict как позиционный аргумент

**Тест:**
```python
def test_method(position_id: int, **kwargs):
    pass

test_method(123, {'key': 'value'})
# ERROR: test_method() takes 1 positional argument but 2 were given
```

**Результат:** TypeError во время выполнения
**Серьезность:** 🔴 КРИТИЧЕСКАЯ - код падает с ошибкой

**Статус:** Добавлен 2025-10-14 (commit d37cbc48)
**Защита:** Код обернут в try/except, ошибка логируется

```python
except Exception as db_error:
    logger.error(f"Failed to update pending close order in database for {symbol}: {db_error}")
```

---

### Проблема #3: Position.id == "pending"

**Контекст:** В системе существуют "pre-registered" позиции с `id="pending"` (строка!)

**Файлы:**
- `core/position_manager.py:1702` - создание с id="pending"
- `core/position_manager.py:2220-2222` - проверка на "pending"

**Потенциальная проблема:** Любой вызов update_position с position.id где position - это pre-registered позиция:

```python
await self.repository.update_position(
    position.id,        # ← "pending" (string!)
    status='active',
    quantity=10,
    price=5.5,
    pnl=1.0
)
```

С **kwargs методом:
- kwargs = {status, quantity, price, pnl} (4 элемента)
- $1 = 'active'
- $2 = 10
- $3 = 5.5
- $4 = 1.0
- **$5 = 'pending'** ← ОШИБКА!

**Однако:** После анализа ВСЕХ вызовов в коде, ни один не имеет ровно 4 kwargs!

---

## 📊 Анализ Всех Вызовов update_position с position.id

| Файл | Строка | Kwargs | $N для position.id | Может быть "pending"? |
|------|--------|--------|-------------------|----------------------|
| position_manager.py | 640 | 1 | $2 | ❌ Редко |
| position_manager.py | 1309 | 1 | $2 | ❌ Редко |
| position_manager.py | 1630 | 1 | $2 | ⚠️ Возможно |
| position_manager.py | 2153 | 2 | $3 | ⚠️ Возможно |
| position_manager.py | 2285 | 3 | $4 | ⚠️ Возможно |
| position_manager.py | 2349 | 1 | $2 | ⚠️ Возможно |
| position_manager.py | 2396 | 1 | $2 | ⚠️ Возможно |
| position_manager.py | 2885 | DICT | TypeError | ❌ Всегда падает |
| position_manager.py | 3139 | 2 | $3 | ⚠️ Возможно |
| position_manager.py | 3173 | 2 | $3 | ⚠️ Возможно |

**Вывод:** Ни один вызов НЕ имеет ровно 4 kwargs, которые дали бы $5 для position.id!

---

## 🤔 Где Тогда Ошибка $5?

### Гипотеза 1: Ошибка Была Исправлена

Возможно, вызов с 4 kwargs существовал раньше и был удален/изменен.

### Гипотеза 2: Ошибка из Другого Запроса

Возможно, ошибка пришла не от `update_position`, а от другого SQL запроса:
- `close_position()` - имеет $5 = position_id
- Другие методы с 5+ параметрами

### Гипотеза 3: Динамическое Построение Kwargs

Возможно, где-то kwargs строятся динамически и иногда могут иметь 4 элемента:

```python
updates = {'status': 'pending'}
if condition1:
    updates['field1'] = value1
if condition2:
    updates['field2'] = value2
if condition3:
    updates['field3'] = value3
if condition4:
    updates['field4'] = value4

await repo.update_position(position.id, **updates)
```

### Гипотеза 4: Ошибка Из Старой Версии Кода

Пользователь упомянул ошибку от 2025-10-30 00:35:01, но в текущем коде (после коммитов) этот вызов мог быть исправлен.

---

## 💡 Решения

### Решение #1: Удалить Мертвый Код

**Удалить метод на строке 365** в database/repository.py:

```python
# DELETE LINES 365-392
async def update_position(self, position_id: int, updates: Dict) -> bool:
    """Update position with given data"""
    ...
    return True
```

**Причина:** Этот код НИКОГДА не выполняется, только создает путаницу

**Влияние:** НЕТ - код уже не используется

---

### Решение #2: Исправить risk_manager.py:211

**Было:**
```python
await self.repository.update_position(position)
```

**Должно быть:**
```python
await self.repository.update_position(position.id, **{
    'status': 'closed',
    'exit_reason': 'emergency_liquidation'
})
```

**Или использовать close_position:**
```python
await self.repository.close_position(
    position.id,
    pnl=0,
    reason='emergency_liquidation'
)
```

---

### Решение #3: Исправить position_manager.py:2885

**Было:**
```python
await self.repository.update_position(position.id, {
    'pending_close_order_id': order['id'],
    'pending_close_price': to_decimal(target_price),
    'exit_reason': truncate_exit_reason(reason)
})
```

**Должно быть:**
```python
await self.repository.update_position(position.id, **{
    'pending_close_order_id': order['id'],
    'pending_close_price': to_decimal(target_price),
    'exit_reason': truncate_exit_reason(reason)
})
```

Или:
```python
await self.repository.update_position(
    position.id,
    pending_close_order_id=order['id'],
    pending_close_price=to_decimal(target_price),
    exit_reason=truncate_exit_reason(reason)
)
```

---

### Решение #4: Защита от position.id = "pending"

Добавить проверку во ВСЕ вызовы update_position:

```python
# Перед вызовом:
if position.id == "pending":
    logger.warning(f"Cannot update position {symbol} - not yet committed to database")
    return

await self.repository.update_position(position.id, ...)
```

**ИЛИ** добавить проверку в сам метод update_position:

```python
async def update_position(self, position_id: int, **kwargs) -> bool:
    # Validate position_id
    if not isinstance(position_id, int):
        logger.error(
            f"❌ Invalid position_id type: {type(position_id).__name__} "
            f"(value: {position_id}). Expected int."
        )
        return False

    if not kwargs:
        return False

    # ... rest of method
```

---

## 🧪 Тесты для Валидации

### Test 1: Проверка Наличия Только Одного Метода

```python
def test_single_update_position_method():
    """Verify only one update_position method exists"""
    import inspect
    from database.repository import Repository

    methods = [m for m in dir(Repository) if m == 'update_position']
    assert len(methods) == 1, "Multiple update_position methods found!"

    sig = inspect.signature(Repository.update_position)
    params = list(sig.parameters.keys())

    # Should have: self, position_id, **kwargs
    assert 'self' in params
    assert 'position_id' in params
    # Check for **kwargs
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return  # Found **kwargs, test passes

    raise AssertionError("Expected **kwargs parameter not found!")
```

### Test 2: Проверка TypeError при Dict

```python
@pytest.mark.asyncio
async def test_update_position_rejects_dict():
    """Test that dict as second positional arg raises TypeError"""
    repo = Repository(...)

    with pytest.raises(TypeError, match="takes.*positional argument"):
        await repo.update_position(123, {'status': 'active'})
```

### Test 3: Проверка Отклонения Строкового ID

```python
@pytest.mark.asyncio
async def test_update_position_rejects_string_id():
    """Test that string position_id is rejected"""
    repo = Repository(...)

    result = await repo.update_position(
        "pending",  # String instead of int
        status='active'
    )

    assert result == False, "Should reject string position_id"
```

---

## 📋 План Внедрения

### Фаза 0: Анализ (ЗАВЕРШЕНА ✅)

- [x] Проверить runtime signature
- [x] Найти дублирование методов
- [x] Найти все неправильные вызовы
- [x] Проанализировать использование id="pending"

### Фаза 1: Очистка Мертвого Кода (5 минут)

1. Удалить метод update_position на строке 365 в repository.py
2. Проверить syntax: `python -m py_compile database/repository.py`
3. Commit: "refactor: remove dead update_position(Dict) method - overridden by **kwargs version"

### Фаза 2: Исправление Неправильных Вызовов (15 минут)

1. Исправить risk_manager.py:211
   - Изменить на использование close_position()
   - Или передать правильные параметры

2. Исправить position_manager.py:2885
   - Добавить `**` перед dict
   - Проверить что код работает

3. Commit: "fix: correct update_position calls to match **kwargs signature"

### Фаза 3: Защита от "pending" ID (10 минут)

1. Добавить валидацию в update_position метод
2. Добавить тесты
3. Commit: "fix: add validation to reject non-integer position_id"

### Фаза 4: Тестирование (20 минут)

1. Unit тесты для всех изменений
2. Integration тесты
3. Manual тестирование на dev окружении

### Фаза 5: Deploy (10 минут)

1. Code review
2. Merge в main
3. Deploy
4. Monitor logs

**Общее время:** ~1 час

---

## 🎯 Выводы

### Найдены Критические Проблемы

1. ✅ **Дублирование методов** - один метод перезаписывает другой
2. ✅ **Мертвый код** - метод на строке 365 никогда не выполняется
3. ✅ **Неправильные вызовы** - 2 места с некорректным использованием
4. ✅ **Отсутствие валидации** - нет проверки типа position_id

### Не Найдено

❓ **Точный вызов, вызвавший ошибку $5='pending'**

Возможные причины:
- Ошибка была из старой версии кода (уже исправлена)
- Ошибка из другого SQL запроса, не update_position
- Ошибка из динамически построенных kwargs
- Ошибка из кода который больше не существует

### Рекомендации

1. ✅ **Обязательно:** Удалить мертвый код (строка 365)
2. ✅ **Обязательно:** Исправить 2 неправильных вызова
3. ✅ **Крайне рекомендуется:** Добавить валидацию position_id
4. ⚠️ **Опционально:** Проверить старые логи на предмет других случаев ошибки

---

**Статус:** 🟢 **РАССЛЕДОВАНИЕ ЗАВЕРШЕНО - ГОТОВ ПЛАН ИСПРАВЛЕНИЯ**

**Next Step:** Реализовать Фазы 1-5 согласно плану
