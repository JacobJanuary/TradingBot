# Fix Plan: update_position Method Issues

**Дата:** 2025-10-30
**Статус:** 📋 ГОТОВ К РЕАЛИЗАЦИИ
**Приоритет:** 🔴 ВЫСОКИЙ

---

## 🎯 Цель

Исправить критические проблемы с методом `update_position` в `database/repository.py`:

1. Удалить мертвый код (дублирующий метод)
2. Исправить неправильные вызовы метода
3. Добавить валидацию для предотвращения ошибок

---

## 📊 Обнаруженные Проблемы

### Проблема #1: Дублирование Методов
- **Файл:** database/repository.py
- **Строки:** 365 (мертвый) и 717 (рабочий)
- **Серьезность:** 🟡 СРЕДНЯЯ (создает путаницу)

### Проблема #2: Неправильный Вызов (Объект)
- **Файл:** core/risk_manager.py:211
- **Проблема:** Передается объект вместо ID
- **Серьезность:** 🟡 СРЕДНЯЯ (операция молча проваливается)

### Проблема #3: Неправильный Вызов (Dict)
- **Файл:** core/position_manager.py:2885
- **Проблема:** Dict как позиционный аргумент
- **Серьезность:** 🔴 КРИТИЧЕСКАЯ (TypeError)

### Проблема #4: Отсутствие Валидации
- **Файл:** database/repository.py:717
- **Проблема:** Нет проверки типа position_id
- **Серьезность:** 🔴 КРИТИЧЕСКАЯ (может получить string "pending")

---

## 🔧 Решения

### Fix #1: Удалить Мертвый Код

**Файл:** `database/repository.py`
**Действие:** Удалить строки 365-392

```python
# ❌ DELETE THIS METHOD (lines 365-392):
async def update_position(self, position_id: int, updates: Dict) -> bool:
    """Update position with given data"""
    import logging
    logger = logging.getLogger(__name__)

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

    logger.info(f"[REPO] update_position(id={position_id}, updates={updates})")
    async with self.pool.acquire() as conn:
        result = await conn.execute(query, *values)
        logger.info(f"[REPO] Query result: {result}")
        return True
```

**Причина:** Этот метод ПЕРЕЗАПИСАН методом на строке 717 и никогда не выполняется

---

### Fix #2: Исправить risk_manager.py:211

**Файл:** `core/risk_manager.py`
**Строка:** 211

**Было:**
```python
for position in positions:
    try:
        # This would actually close the position
        # For now, just mark as closed
        position.status = 'closed'
        position.exit_reason = 'emergency_liquidation'
        await self.repository.update_position(position)  # ❌ WRONG!
        closed += 1
    except Exception as e:
        logger.error(f"Failed to close position {position.id}: {e}")
```

**Должно быть (Вариант A - Использовать close_position):**
```python
for position in positions:
    try:
        # Close position properly
        await self.repository.close_position(
            position.id,
            pnl=0,  # Unknown PNL in emergency
            reason='emergency_liquidation'
        )
        closed += 1
    except Exception as e:
        logger.error(f"Failed to close position {position.id}: {e}")
```

**Или (Вариант B - Исправить вызов update_position):**
```python
for position in positions:
    try:
        # Mark as closed in database
        await self.repository.update_position(position.id, **{
            'status': 'closed',
            'exit_reason': 'emergency_liquidation',
            'closed_at': datetime.now(timezone.utc)
        })
        closed += 1
    except Exception as e:
        logger.error(f"Failed to close position {position.id}: {e}")
```

**Рекомендация:** Использовать Вариант A (close_position) - более явный и правильный метод

---

### Fix #3: Исправить position_manager.py:2885

**Файл:** `core/position_manager.py`
**Строка:** 2885-2889

**Было:**
```python
try:
    # Import truncate helper from atomic_position_manager
    from core.atomic_position_manager import truncate_exit_reason

    await self.repository.update_position(position.id, {  # ❌ WRONG!
        'pending_close_order_id': order['id'],
        'pending_close_price': to_decimal(target_price),
        'exit_reason': truncate_exit_reason(reason)
    })
except Exception as db_error:
    logger.error(f"Failed to update pending close order in database for {symbol}: {db_error}")
```

**Должно быть (Вариант A - Unpack dict):**
```python
try:
    from core.atomic_position_manager import truncate_exit_reason

    await self.repository.update_position(position.id, **{  # ✅ ADD **
        'pending_close_order_id': order['id'],
        'pending_close_price': to_decimal(target_price),
        'exit_reason': truncate_exit_reason(reason)
    })
except Exception as db_error:
    logger.error(f"Failed to update pending close order in database for {symbol}: {db_error}")
```

**Или (Вариант B - Keyword arguments):**
```python
try:
    from core.atomic_position_manager import truncate_exit_reason

    await self.repository.update_position(
        position.id,
        pending_close_order_id=order['id'],
        pending_close_price=to_decimal(target_price),
        exit_reason=truncate_exit_reason(reason)
    )
except Exception as db_error:
    logger.error(f"Failed to update pending close order in database for {symbol}: {db_error}")
```

**Рекомендация:** Использовать Вариант A (добавить `**`) - минимальное изменение

---

### Fix #4: Добавить Валидацию в update_position

**Файл:** `database/repository.py`
**Строка:** 717-753

**Было:**
```python
async def update_position(self, position_id: int, **kwargs) -> bool:
    """
    Update position with arbitrary fields

    Args:
        position_id: Position ID to update
        **kwargs: Field names and values to update

    Returns:
        bool: True if update successful

    Example:
        await repo.update_position(123, current_price=50.5, pnl=10.0)
    """
    if not kwargs:
        return False

    # Build dynamic UPDATE query
    set_clauses = []
    values = []
    param_count = 1

    for key, value in kwargs.items():
        set_clauses.append(f"{key} = ${param_count}")
        values.append(value)
        param_count += 1

    query = f"""
        UPDATE monitoring.positions
        SET {', '.join(set_clauses)}, updated_at = NOW()
        WHERE id = ${param_count}
    """
    values.append(position_id)

    async with self.pool.acquire() as conn:
        result = await conn.execute(query, *values)
        return True
```

**Должно быть:**
```python
async def update_position(self, position_id: int, **kwargs) -> bool:
    """
    Update position with arbitrary fields

    Args:
        position_id: Position ID to update (must be integer)
        **kwargs: Field names and values to update

    Returns:
        bool: True if update successful, False if validation fails

    Example:
        await repo.update_position(123, current_price=50.5, pnl=10.0)

    Raises:
        ValueError: If position_id is not an integer
    """
    # ✅ VALIDATION: Check position_id type
    if not isinstance(position_id, int):
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"❌ CRITICAL: update_position called with invalid position_id type! "
            f"Expected int, got {type(position_id).__name__} (value: {position_id})"
        )
        return False

    if not kwargs:
        return False

    # Build dynamic UPDATE query
    set_clauses = []
    values = []
    param_count = 1

    for key, value in kwargs.items():
        set_clauses.append(f"{key} = ${param_count}")
        values.append(value)
        param_count += 1

    query = f"""
        UPDATE monitoring.positions
        SET {', '.join(set_clauses)}, updated_at = NOW()
        WHERE id = ${param_count}
    """
    values.append(position_id)

    async with self.pool.acquire() as conn:
        result = await conn.execute(query, *values)
        return True
```

**Изменения:**
1. Добавлена проверка типа position_id
2. Обновлен docstring
3. Добавлено логирование ошибки валидации

---

## 🧪 Тесты

### Test 1: Валидация Типа position_id

```python
# File: tests/unit/test_repository_validation.py

import pytest
from database.repository import Repository


@pytest.mark.asyncio
async def test_update_position_rejects_string_id(mock_pool):
    """Test that update_position rejects string position_id"""
    repo = Repository(mock_pool)

    # Should return False for string ID
    result = await repo.update_position(
        "pending",  # String instead of int
        status='active'
    )

    assert result is False, "Should reject string position_id"


@pytest.mark.asyncio
async def test_update_position_rejects_dict_as_positional(mock_pool):
    """Test that passing dict as second positional arg raises TypeError"""
    repo = Repository(mock_pool)

    with pytest.raises(TypeError, match="takes.*positional argument"):
        await repo.update_position(123, {'status': 'active'})


@pytest.mark.asyncio
async def test_update_position_accepts_kwargs(mock_pool):
    """Test that update_position works with proper kwargs"""
    repo = Repository(mock_pool)

    # Should work
    result = await repo.update_position(
        123,
        status='active',
        current_price=50.5
    )

    assert result is True
```

### Test 2: Risk Manager Fix

```python
# File: tests/unit/test_risk_manager_fix.py

import pytest
from core.risk_manager import RiskManager


@pytest.mark.asyncio
async def test_emergency_close_uses_close_position(mock_repository):
    """Test that emergency close uses close_position method"""
    risk_manager = RiskManager(mock_repository, ...)

    # Mock positions
    mock_repository.get_active_positions.return_value = [
        MockPosition(id=123, symbol='BTCUSDT')
    ]

    # Execute emergency close
    result = await risk_manager.emergency_close('test_reason')

    # Verify close_position was called, not update_position
    mock_repository.close_position.assert_called_once()
    mock_repository.update_position.assert_not_called()

    assert result['positions_closed'] == 1
```

### Test 3: Position Manager Fix

```python
# File: tests/unit/test_position_manager_fix.py

import pytest
from core.position_manager import PositionManager


@pytest.mark.asyncio
async def test_pending_close_order_update_uses_kwargs(mock_repository):
    """Test that pending close order update uses **kwargs correctly"""
    pm = PositionManager(mock_repository, ...)

    # Mock position
    position = MockPosition(id=456, symbol='ETHUSDT')

    # This should NOT raise TypeError anymore
    await pm._update_pending_close_order(position, order_id='12345', price=100.5)

    # Verify update_position was called with correct kwargs
    mock_repository.update_position.assert_called_once()
    call_args = mock_repository.update_position.call_args

    # First arg should be position_id (int)
    assert call_args[0][0] == 456
    # Should have kwargs, not dict
    assert 'pending_close_order_id' in call_args[1]
```

---

## 📋 План Реализации

### Фаза 1: Подготовка (10 минут)

**Задачи:**
1. Создать feature branch: `fix/update-position-method-issues`
2. Создать backups файлов
3. Запустить текущие тесты (baseline)

**Команды:**
```bash
git checkout -b fix/update-position-method-issues
cp database/repository.py database/repository.py.backup_20251030
cp core/risk_manager.py core/risk_manager.py.backup_20251030
cp core/position_manager.py core/position_manager.py.backup_20251030

# Run current tests
pytest tests/ -v --tb=short
```

---

### Фаза 2: Fix #1 - Удалить Мертвый Код (5 минут)

**Задачи:**
1. Открыть database/repository.py
2. Удалить строки 365-392
3. Проверить syntax
4. Commit

**Команды:**
```bash
# Edit file to remove lines 365-392
# Then:
python -m py_compile database/repository.py

git add database/repository.py
git commit -m "refactor(repository): remove dead update_position(Dict) method

- Method at line 365 was overridden by method at line 717
- Only **kwargs version (line 717) is used at runtime
- Removing dead code to prevent confusion
- No functional impact - code was never executed"
```

---

### Фаза 3: Fix #2 - Исправить risk_manager.py (5 минут)

**Задачи:**
1. Открыть core/risk_manager.py
2. Заменить вызов update_position на close_position
3. Проверить imports
4. Commit

**Изменения:**
```python
# Line 211 - BEFORE:
await self.repository.update_position(position)

# Line 211 - AFTER:
await self.repository.close_position(
    position.id,
    pnl=0,
    reason='emergency_liquidation'
)
```

**Команды:**
```bash
# Edit file
# Then:
python -m py_compile core/risk_manager.py

git add core/risk_manager.py
git commit -m "fix(risk_manager): use close_position instead of update_position(object)

- emergency_close was passing entire position object to update_position
- This caused method to silently fail (returned False)
- Changed to use proper close_position method
- Fixes bug where emergency liquidation didn't close positions"
```

---

### Фаза 4: Fix #3 - Исправить position_manager.py (5 минут)

**Задачи:**
1. Открыть core/position_manager.py
2. Добавить `**` перед dict на строке 2885
3. Проверить syntax
4. Commit

**Изменения:**
```python
# Line 2885 - BEFORE:
await self.repository.update_position(position.id, {

# Line 2885 - AFTER:
await self.repository.update_position(position.id, **{
```

**Команды:**
```bash
# Edit file - ADD ** before {
# Then:
python -m py_compile core/position_manager.py

git add core/position_manager.py
git commit -m "fix(position_manager): unpack dict for update_position **kwargs

- update_position expects **kwargs, not dict as positional arg
- Was causing TypeError: 'takes 1 positional argument but 2 were given'
- Error was caught by try/except but operation failed silently
- Fixed by unpacking dict with ** operator (line 2885)"
```

---

### Фаза 5: Fix #4 - Добавить Валидацию (10 минут)

**Задачи:**
1. Открыть database/repository.py
2. Добавить проверку типа position_id
3. Обновить docstring
4. Проверить syntax
5. Commit

**Команды:**
```bash
# Edit file - add validation at start of method
# Then:
python -m py_compile database/repository.py

git add database/repository.py
git commit -m "fix(repository): add position_id type validation to update_position

- Positions can have id='pending' (string) before DB commit
- Calling update_position with string ID causes SQL error
- Added isinstance(position_id, int) check
- Returns False and logs error if validation fails
- Prevents 'str' object cannot be interpreted as an integer error"
```

---

### Фаза 6: Тесты (20 минут)

**Задачи:**
1. Создать test_repository_validation.py
2. Создать test_risk_manager_fix.py
3. Создать test_position_manager_fix.py
4. Запустить все тесты
5. Commit тестов

**Команды:**
```bash
# Create test files (see Tests section above)

# Run tests
pytest tests/unit/test_repository_validation.py -v
pytest tests/unit/test_risk_manager_fix.py -v
pytest tests/unit/test_position_manager_fix.py -v

# Run all tests
pytest tests/ -v

git add tests/
git commit -m "test: add tests for update_position fixes

- Test position_id type validation
- Test risk_manager uses close_position
- Test position_manager unpacks dict correctly
- All tests passing"
```

---

### Фаза 7: Интеграционное Тестирование (15 минут)

**Задачи:**
1. Запустить бота на dev окружении
2. Проверить логи на ошибки
3. Протестировать сценарии:
   - Emergency liquidation
   - Pending close order update
   - Pre-registered position updates
4. Убедиться что нет новых ошибок

**Команды:**
```bash
# Start bot in test mode
python bot.py --test-mode

# Monitor logs
tail -f logs/bot_$(date +%Y%m%d).log | grep -i "update_position\|error\|critical"

# Stop bot
# Check no errors related to our changes
```

---

### Фаза 8: Финализация (10 минут)

**Задачи:**
1. Code review с собой
2. Проверить все коммиты
3. Обновить документацию
4. Merge в main

**Команды:**
```bash
# Review all changes
git log --oneline origin/main..HEAD
git diff origin/main..HEAD

# Update initial audit report
# Add note that issues were fixed

# Push to remote
git push origin fix/update-position-method-issues

# Switch to main and merge
git checkout main
git merge fix/update-position-method-issues
git push origin main
```

---

## ⚠️ Риски и Митигация

### Риск #1: Удаление Метода Сломает Старый Код

**Вероятность:** 🟢 НИЗКАЯ
**Причина:** Метод уже не используется runtime
**Митигация:** Проверить все импорты и вызовы

### Риск #2: close_position Работает По-Другому

**Вероятность:** 🟡 СРЕДНЯЯ
**Причина:** Может иметь другую логику чем update_position
**Митигация:**
- Проверить код close_position
- Убедиться что он делает то же самое
- Добавить тесты

### Риск #3: Валидация Блокирует Легитимные Вызовы

**Вероятность:** 🟢 НИЗКАЯ
**Причина:** position_id ВСЕГДА должен быть int
**Митигация:**
- Логировать все отклоненные вызовы
- Мониторить логи после deploy
- Быть готовым откатить если нужно

### Риск #4: Интеграционные Проблемы

**Вероятность:** 🟡 СРЕДНЯЯ
**Причина:** Изменения затрагивают core модули
**Митигация:**
- Тщательное тестирование на dev
- Постепенный deploy (dev → staging → prod)
- Готовый rollback план

---

## 🎯 Критерии Успеха

### Must Have (Обязательно)

- [ ] Удален мертвый код (строка 365)
- [ ] Исправлен risk_manager.py:211
- [ ] Исправлен position_manager.py:2885
- [ ] Добавлена валидация position_id
- [ ] Все тесты проходят
- [ ] Нет новых ошибок в логах

### Should Have (Желательно)

- [ ] 100% code coverage для новых тестов
- [ ] Документация обновлена
- [ ] Code review пройден
- [ ] Нет регрессий в production

### Nice to Have (Бонус)

- [ ] Автоматическая миграция старых вызовов
- [ ] Линтер для проверки типа position_id
- [ ] Метрики для отслеживания отклоненных вызовов

---

## 📊 Оценка Времени

| Фаза | Задачи | Время |
|------|--------|-------|
| Фаза 1 | Подготовка | 10 мин |
| Фаза 2 | Удалить мертвый код | 5 мин |
| Фаза 3 | Исправить risk_manager | 5 мин |
| Фаза 4 | Исправить position_manager | 5 мин |
| Фаза 5 | Добавить валидацию | 10 мин |
| Фаза 6 | Тесты | 20 мин |
| Фаза 7 | Интеграционное тестирование | 15 мин |
| Фаза 8 | Финализация | 10 мин |
| **ИТОГО** | | **1 час 20 минут** |

---

## ✅ Checklist Перед Началом

- [ ] Прочитан и понят весь план
- [ ] Создан feature branch
- [ ] Созданы backups всех файлов
- [ ] Запущены baseline тесты
- [ ] Есть доступ к dev окружению
- [ ] Готов rollback план (backups сохранены)

---

## ✅ Checklist После Завершения

- [ ] Все фиксы реализованы
- [ ] Все тесты проходят
- [ ] Нет новых ошибок в логах
- [ ] Code review завершен
- [ ] Документация обновлена
- [ ] Изменения смержены в main
- [ ] Production monitoring настроен

---

**Статус:** 📋 **ГОТОВ К РЕАЛИЗАЦИИ**

**Recommended Start:** После завершения текущего цикла тестирования

**Owner:** TBD

**Reviewer:** TBD
