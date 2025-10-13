# ПЛАН ВНЕДРЕНИЯ ОБНОВЛЕНИЯ КОЛИЧЕСТВА ПОЗИЦИЙ

**Дата**: 2025-10-13
**Статус**: РАССЛЕДОВАНИЕ ЗАВЕРШЕНО - ГОТОВ К ВНЕДРЕНИЮ
**Приоритет**: СРЕДНИЙ (функциональность работает, но БД показывает устаревшие данные)

---

## 🎯 РЕЗЮМЕ

**Результат глубокого исследования**: Метод `repository.update_position()` **ПОЛНОСТЬЮ ПОДДЕРЖИВАЕТ** обновление параметра `quantity`. Комментарий в коде о "schema issue" является **УСТАРЕВШИМ** и может быть проигнорирован.

**Рекомендация**: Можно **БЕЗОПАСНО** раскомментировать код обновления количества (строки 387-392 в `position_synchronizer.py`).

---

## 📋 ШАГ 1: ПРОВЕРКА СХЕМЫ РЕПОЗИТОРИЯ

### 1.1 Сигнатура Метода

Файл: `database/repository.py:459-492`

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
```

**✅ ВЫВОД**: Метод принимает `**kwargs` - может обновлять **ЛЮБЫЕ** поля, включая `quantity`.

---

### 1.2 Схема База Данных

Таблица: `monitoring.positions`

```sql
CREATE TABLE monitoring.positions (
    id SERIAL PRIMARY KEY,
    ...
    quantity NUMERIC NOT NULL,           -- ✅ Колонка существует
    entry_price DECIMAL(20, 8),          -- 🔒 Immutable (защищено в коде)
    current_price DECIMAL(20, 8),        -- ✅ Может обновляться
    unrealized_pnl DECIMAL(20, 8),       -- ✅ Может обновляться
    ...
);
```

**✅ ВЫВОД**: Колонка `quantity` существует, тип `NUMERIC`, `NOT NULL` - полностью поддерживает обновление.

---

### 1.3 Специальная Обработка entry_price

Файл: `database/repository.py:476-482`

```python
# CRITICAL FIX: entry_price is immutable - set ONCE at creation, never updated
if 'entry_price' in kwargs:
    logger.warning(f"⚠️ Attempted to update entry_price for position {position_id} - IGNORED")
    del kwargs['entry_price']
    if not kwargs:
        return False
```

**✅ ВЫВОД**:
- `entry_price` **защищена** от обновления (важно для расчета SL от исходной цены входа)
- `quantity` **НЕ защищена** - может свободно обновляться
- Это **преднамеренное** архитектурное решение

---

## 📊 ШАГ 2: АНАЛИЗ ИСПОЛЬЗОВАНИЯ В КОДЕ

### 2.1 Активное Использование update_position

Найдено **множество** вызовов по всему коду:

#### Пример 1: Обновление has_trailing_stop
`core/position_manager.py:425-428`
```python
await self.repository.update_position(
    position.id,
    has_trailing_stop=True
)
```

#### Пример 2: Обновление текущей цены и статуса
`core/atomic_position_manager.py:198-202`
```python
await self.repository.update_position(position_id, **{
    'current_price': exec_price,
    'status': state.value,
    'exchange_order_id': entry_order.id
})
```

#### Пример 3: Обновление trailing_activated
`core/position_manager.py:1226`
```python
await self.repository.update_position(position.id, trailing_activated=True)
```

**✅ ВЫВОД**: Метод **активно используется** во всем коде, обновляет различные поля - работает стабильно.

---

### 2.2 Закомментированный Код

Файл: `core/position_synchronizer.py:380-392`

```python
# For now, just log the discrepancy
# The update_position method in repository needs to be fixed for trading_bot schema
logger.warning(
    f"    ⚠️ Quantity mismatch detected but update skipped (schema issue). "
    f"Position ID {position_id} should be {new_quantity}"
)

# TODO: Fix repository.update_position to use trading_bot.positions schema
# await self.repository.update_position(
#     position_id=position_id,
#     quantity=new_quantity,
#     current_price=current_price,
#     pnl=unrealized_pnl
# )
```

**❌ ПРОБЛЕМА**: Комментарий "needs to be fixed for trading_bot schema" **УСТАРЕЛ**

**✅ ФАКТ**:
- Схема `monitoring.positions` (не `trading_bot.positions`) используется во всем проекте
- Метод `update_position` **УЖЕ** поддерживает обновление всех этих полей
- Комментарий, вероятно, был добавлен во время миграции схем и не обновлен

---

## 🔍 ШАГ 3: ПРИЧИНА ПРОБЛЕМЫ

### 3.1 Что Происходит Сейчас

1. **Aged Position Manager** создает лимитные ордера для постепенного выхода из позиций
2. Ордера **частично исполняются** на бирже (partial fill)
3. **Реальное** количество на бирже уменьшается (например, 4160.0 → 3160.0)
4. **В БД** остается старое значение (4160.0), потому что обновление закомментировано
5. Расхождение накапливается до полного закрытия позиции

### 3.2 Примеры Расхождений

| Symbol | DB Quantity | Exchange Quantity | Difference | % Diff |
|--------|-------------|-------------------|------------|---------|
| AGIUSDT | 4160.0 | 3160.0 | 1000.0 | 24.0% |
| SCAUSDT | 2136.9 | 2036.0 | 100.9 | 4.7% |
| HNTUSDT | 60.0 | 59.88 | 0.12 | 0.2% |

**Источник**: `QUANTITY_MISMATCH_INVESTIGATION.md`

---

### 3.3 Почему Это Не Критично (Но Нежелательно)

**НЕ критично потому что**:
- Позиции в итоге полностью закрываются
- Биржа является источником истины для Stop-Loss
- Aged Position Manager работает корректно
- Нет финансовых потерь

**Нежелательно потому что**:
- БД показывает устаревшие данные
- Мониторинг может быть неточным
- Логи могут вводить в заблуждение
- Нарушается принцип "БД отражает реальность"

---

## ✅ ШАГ 4: ПЛАН БЕЗОПАСНОЙ РЕАЛИЗАЦИИ

### 4.1 Изменения в Коде

**Файл**: `core/position_synchronizer.py`

**Строки для изменения**: 380-392

**ЧТО СДЕЛАТЬ**:

1. **Удалить устаревший комментарий** (строки 380, 386)
2. **Раскомментировать** вызов `update_position` (строки 387-392)
3. **Исправить параметр**: `pnl` → `unrealized_pnl` (соответствие схеме БД)

**БЫЛО**:
```python
# For now, just log the discrepancy
# The update_position method in repository needs to be fixed for trading_bot schema
logger.warning(
    f"    ⚠️ Quantity mismatch detected but update skipped (schema issue). "
    f"Position ID {position_id} should be {new_quantity}"
)

# TODO: Fix repository.update_position to use trading_bot.positions schema
# await self.repository.update_position(
#     position_id=position_id,
#     quantity=new_quantity,
#     current_price=current_price,
#     pnl=unrealized_pnl
# )
```

**СТАНЕТ**:
```python
# Update quantity to match exchange
logger.info(
    f"    📊 Updating quantity for position {position_id}: {new_quantity}"
)

await self.repository.update_position(
    position_id=position_id,
    quantity=new_quantity,
    current_price=current_price,
    unrealized_pnl=unrealized_pnl  # ← ИСПРАВЛЕНО: pnl → unrealized_pnl
)
```

---

### 4.2 Проверка Параметров

Файл: `core/position_synchronizer.py:369-395`

Анализ метода `_update_position_quantity`:

```python
async def _update_position_quantity(self, position_id: int, new_quantity: float, exchange_position: Dict):
    """Update position quantity in database to match exchange"""
```

**Параметры, доступные в методе**:
- ✅ `position_id` - есть в сигнатуре
- ✅ `new_quantity` - есть в сигнатуре
- ❓ `current_price` - НЕТ в сигнатуре
- ❓ `unrealized_pnl` - НЕТ в сигнатуре

**ПРОБЛЕМА**: Метод пытается обновить `current_price` и `unrealized_pnl`, но они **не передаются** в параметрах!

---

### 4.3 Где Вызывается Метод

Файл: `core/position_synchronizer.py:295-298`

```python
if abs(db_quantity - exchange_quantity) >= 0.01:
    logger.warning(f"    ⚠️ Quantity mismatch: DB={db_quantity}, Exchange={exchange_quantity}")
    await self._update_position_quantity(
        position_id=db_position['id'],
        new_quantity=exchange_quantity,
        exchange_position=exchange_position  # ← Dict с полными данными биржи
    )
```

**✅ РЕШЕНИЕ**: Извлекать `current_price` и `unrealized_pnl` из `exchange_position` внутри метода.

---

### 4.4 ФИНАЛЬНЫЙ КОД

**Файл**: `core/position_synchronizer.py:369-410`

```python
async def _update_position_quantity(self, position_id: int, new_quantity: float, exchange_position: Dict):
    """Update position quantity in database to match exchange"""
    try:
        # Extract additional fields from exchange position
        current_price = exchange_position.get('markPrice')  # Current mark price
        unrealized_pnl = exchange_position.get('unrealizedPnl', 0)  # Unrealized PnL

        # Update quantity to match exchange
        logger.info(
            f"    📊 Updating quantity for position {position_id}: "
            f"{new_quantity} (price: {current_price}, PnL: {unrealized_pnl})"
        )

        await self.repository.update_position(
            position_id=position_id,
            quantity=new_quantity,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl
        )

        logger.info(f"    ✅ Position {position_id} quantity updated successfully")

    except Exception as e:
        logger.error(f"Failed to update position quantity: {e}")
        import traceback
        traceback.print_exc()
```

**ЧТО ИЗМЕНЕНО**:
1. ✅ Удален устаревший комментарий о "schema issue"
2. ✅ Раскомментирован вызов `update_position`
3. ✅ Добавлено извлечение `current_price` и `unrealized_pnl` из `exchange_position`
4. ✅ Исправлен параметр: `pnl` → `unrealized_pnl`
5. ✅ Улучшено логирование (info вместо warning, детали обновления)
6. ✅ Добавлена трассировка ошибок для диагностики

---

## 🧪 ШАГ 5: ПРОЦЕДУРА ТЕСТИРОВАНИЯ

### 5.1 Предварительная Проверка

```bash
# 1. Проверить текущее состояние позиций
python3 diagnose_quantity_mismatch.py
```

**Ожидаемый результат**: Расхождения в количестве для некоторых позиций

---

### 5.2 Ручной Тест Обновления

**Скрипт**: `test_manual_quantity_update.py`

```python
#!/usr/bin/env python3
"""Test manual quantity update"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os
from database.repository import Repository

async def test_manual_update():
    load_dotenv()

    # Connect to DB
    pool = await asyncpg.create_pool(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5433')),
        database=os.getenv('DB_NAME', 'fox_crypto_test'),
        user=os.getenv('DB_USER', 'elcrypto'),
        password=os.getenv('DB_PASSWORD'),
        min_size=1,
        max_size=5
    )

    repo = Repository(pool)

    try:
        # Find any active position
        async with pool.acquire() as conn:
            position = await conn.fetchrow("""
                SELECT id, symbol, quantity, current_price, unrealized_pnl
                FROM monitoring.positions
                WHERE status = 'active'
                LIMIT 1
            """)

        if not position:
            print("❌ No active positions found for testing")
            return

        print("="*80)
        print("TESTING MANUAL QUANTITY UPDATE")
        print("="*80)

        pos_id = position['id']
        old_qty = float(position['quantity'])
        old_price = float(position['current_price'] or 0)
        old_pnl = float(position['unrealized_pnl'] or 0)

        print(f"\n📊 Position BEFORE update:")
        print(f"  ID: {pos_id}")
        print(f"  Symbol: {position['symbol']}")
        print(f"  Quantity: {old_qty}")
        print(f"  Current Price: {old_price}")
        print(f"  Unrealized PnL: {old_pnl}")

        # Test update with new values
        new_qty = old_qty + 1.0  # Increase by 1 for testing
        new_price = old_price + 0.01  # Increase price slightly
        new_pnl = old_pnl + 0.5  # Increase PnL slightly

        print(f"\n🔄 Updating position...")

        result = await repo.update_position(
            position_id=pos_id,
            quantity=new_qty,
            current_price=new_price,
            unrealized_pnl=new_pnl
        )

        print(f"  Update result: {result}")

        # Verify update
        async with pool.acquire() as conn:
            updated = await conn.fetchrow("""
                SELECT quantity, current_price, unrealized_pnl
                FROM monitoring.positions
                WHERE id = $1
            """, pos_id)

        print(f"\n📊 Position AFTER update:")
        print(f"  Quantity: {float(updated['quantity'])}")
        print(f"  Current Price: {float(updated['current_price'] or 0)}")
        print(f"  Unrealized PnL: {float(updated['unrealized_pnl'] or 0)}")

        # Verify values
        success = True
        if abs(float(updated['quantity']) - new_qty) > 0.001:
            print(f"\n❌ FAIL: Quantity not updated correctly")
            success = False
        if abs(float(updated['current_price'] or 0) - new_price) > 0.001:
            print(f"\n❌ FAIL: Current price not updated correctly")
            success = False
        if abs(float(updated['unrealized_pnl'] or 0) - new_pnl) > 0.001:
            print(f"\n❌ FAIL: Unrealized PnL not updated correctly")
            success = False

        if success:
            print(f"\n✅ SUCCESS: All fields updated correctly")

        # Restore original values
        print(f"\n♻️  Restoring original values...")
        await repo.update_position(
            position_id=pos_id,
            quantity=old_qty,
            current_price=old_price,
            unrealized_pnl=old_pnl
        )
        print(f"  ✅ Restored")

    finally:
        await pool.close()

if __name__ == '__main__':
    asyncio.run(test_manual_update())
```

**Команда**:
```bash
python3 test_manual_quantity_update.py
```

**Ожидаемый результат**:
```
✅ SUCCESS: All fields updated correctly
```

---

### 5.3 Интеграционный Тест

После применения изменений в `position_synchronizer.py`:

```bash
# 1. Запустить бота
python3 main.py

# 2. В другом терминале мониторить логи
tail -f logs/trading_bot.log | grep "Updating quantity"

# 3. Дождаться срабатывания синхронизации (каждые 30-60 сек)

# 4. Проверить, что количество обновляется
python3 diagnose_quantity_mismatch.py
```

**Ожидаемый результат**:
- В логах появляются сообщения: `📊 Updating quantity for position ...`
- Расхождения между БД и биржей **исчезают** или **минимальны** (< 0.01)

---

### 5.4 Критерии Успеха

✅ **Тест пройден, если**:
1. Метод `update_position` успешно обновляет `quantity`
2. Обновляются также `current_price` и `unrealized_pnl`
3. `entry_price` **НЕ** изменяется (проверка immutability)
4. Нет ошибок в логах
5. Расхождения между БД и биржей < 0.01 (рабочая точность)

❌ **Тест провален, если**:
1. Возникают ошибки при вызове `update_position`
2. Поля не обновляются в БД
3. `entry_price` изменяется (нарушение immutability)
4. Бот падает с exception

---

## 🔒 ШАГ 6: ПЛАН ОТКАТА

### 6.1 Если Что-то Пошло Не Так

**ВАРИАНТ A**: Откат через Git

```bash
# Вернуть файл к текущей версии
git checkout HEAD -- core/position_synchronizer.py

# Перезапустить бота
systemctl restart trading_bot  # или ваш метод перезапуска
```

**ВАРИАНТ B**: Закомментировать код обратно

Просто снова закомментировать строки 387-392:

```python
# await self.repository.update_position(
#     position_id=position_id,
#     quantity=new_quantity,
#     current_price=current_price,
#     unrealized_pnl=unrealized_pnl
# )
```

---

### 6.2 Когда Откатывать

Откатывать ТОЛЬКО если:
1. ❌ Бот падает с ошибками БД
2. ❌ `entry_price` начинает изменяться
3. ❌ Количество обновляется **неправильно** (биржа показывает одно, БД - другое после обновления)
4. ❌ Критические ошибки в логах каждый раз при синхронизации

**НЕ откатывать** если:
- ⚠️ Единичная ошибка (может быть временная проблема сети)
- ⚠️ Предупреждения (warnings) в логах
- ⚠️ Небольшие расхождения < 0.01 (округление)

---

## 📊 ШАГ 7: РИСКИ И МИТИГАЦИЯ

### 7.1 Риски

| Риск | Вероятность | Воздействие | Митигация |
|------|-------------|-------------|-----------|
| Метод update_position не работает с quantity | ❌ ОЧЕНЬ НИЗКАЯ | 🔴 ВЫСОКОЕ | Предварительный ручной тест |
| Неправильные данные из exchange_position | ⚠️ СРЕДНЯЯ | 🟡 СРЕДНЕЕ | Валидация данных, обработка None |
| entry_price случайно обновляется | ❌ ОЧЕНЬ НИЗКАЯ | 🔴 КРИТИЧЕСКОЕ | Immutability уже защищена в коде |
| Производительность БД | ❌ НИЗКАЯ | 🟢 НИЗКОЕ | Обновление только при расхождении > 0.01 |
| Race condition при обновлении | ⚠️ СРЕДНЯЯ | 🟡 СРЕДНЕЕ | Уже есть locks в position_manager |

---

### 7.2 Дополнительная Защита

**Рекомендуется добавить валидацию** в метод `_update_position_quantity`:

```python
async def _update_position_quantity(self, position_id: int, new_quantity: float, exchange_position: Dict):
    """Update position quantity in database to match exchange"""
    try:
        # Validate new_quantity
        if new_quantity < 0:
            logger.error(f"❌ Invalid new_quantity: {new_quantity} (must be >= 0)")
            return

        # Extract additional fields from exchange position
        current_price = exchange_position.get('markPrice')
        unrealized_pnl = exchange_position.get('unrealizedPnl', 0)

        # Validate current_price
        if current_price is None or current_price <= 0:
            logger.warning(f"⚠️ Invalid current_price: {current_price}, skipping price update")
            current_price = None  # Don't update if invalid

        # Build update dict dynamically
        updates = {'quantity': new_quantity}
        if current_price is not None:
            updates['current_price'] = current_price
        if unrealized_pnl is not None:
            updates['unrealized_pnl'] = unrealized_pnl

        logger.info(
            f"    📊 Updating position {position_id}: {updates}"
        )

        await self.repository.update_position(
            position_id=position_id,
            **updates
        )

        logger.info(f"    ✅ Position {position_id} updated successfully")

    except Exception as e:
        logger.error(f"Failed to update position quantity: {e}")
        import traceback
        traceback.print_exc()
```

---

## 📝 РЕЗЮМЕ И РЕКОМЕНДАЦИИ

### ✅ Что Подтверждено

1. **Метод `repository.update_position()` ПОЛНОСТЬЮ ПОДДЕРЖИВАЕТ обновление quantity**
2. **Схема БД имеет колонку `quantity` типа NUMERIC**
3. **Метод активно используется в коде для обновления других полей**
4. **entry_price защищена от обновления (immutability)**
5. **Комментарий о "schema issue" УСТАРЕЛ**

---

### 🎯 Рекомендации

**РЕКОМЕНДУЕТСЯ**:
1. ✅ Раскомментировать код обновления quantity
2. ✅ Исправить параметр `pnl` → `unrealized_pnl`
3. ✅ Добавить извлечение данных из `exchange_position`
4. ✅ Добавить валидацию входных данных (защита от None/negative)
5. ✅ Провести ручной тест перед применением
6. ✅ Мониторить логи первые 24 часа после изменения

**НЕ ТРЕБУЕТСЯ**:
- ❌ Изменения в схеме БД
- ❌ Изменения в `repository.py`
- ❌ Миграции данных
- ❌ Изменения в других файлах

---

### 📅 Следующие Шаги

1. **СЕЙЧАС**: Создать и запустить `test_manual_quantity_update.py`
2. **ПОСЛЕ ТЕСТА**: Применить изменения в `position_synchronizer.py`
3. **ПОСЛЕ ПРИМЕНЕНИЯ**: Запустить бота и мониторить логи 24 часа
4. **ЧЕРЕЗ 24 ЧАСА**: Проверить статистику расхождений (должны быть < 0.01)

---

## 🔗 Связанные Документы

- `QUANTITY_MISMATCH_INVESTIGATION.md` - Детальное расследование проблемы
- `QUANTITY_MISMATCH_INVESTIGATION_RU.md` - Перевод на русский
- `core/position_synchronizer.py:369-410` - Метод для изменения
- `database/repository.py:459-492` - Метод update_position

---

**Подготовил**: Claude Code
**Дата**: 2025-10-13
**Статус**: ✅ ГОТОВО К ВНЕДРЕНИЮ
