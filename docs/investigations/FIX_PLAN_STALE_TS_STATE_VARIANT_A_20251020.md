# ДЕТАЛЬНЫЙ ПЛАН ИСПРАВЛЕНИЯ: Удаление TS state при закрытии позиций (Вариант A)

**Дата**: 2025-10-20
**Приоритет**: P0 - КРИТИЧНО
**Стратегия**: Вариант A - Удалять запись при закрытии позиции

---

## EXECUTIVE SUMMARY

### Проблема
При закрытии позиций запись в `trailing_stop_state` **НЕ ВСЕГДА удаляется**, что приводит к накоплению устаревших данных в БД.

### Найденные баги
1. ✅ **Метод удаления существует и работает**: `_delete_state()` → `repository.delete_trailing_stop_state()`
2. ❌ **НЕ вызывается** в сценарии phantom cleanup (`aged_position_manager.py:332`)
3. ⚠️ **Потенциально не вызывается** в неиспользуемом коде (`position_manager.py:2802`)
4. ✅ **Вызывается корректно** при обычном закрытии через `position_manager.close_position()`

### Масштаб проблемы
- **29 устаревших записей** в БД (по состоянию на 2025-10-20)
- Все записи от **phantom positions** (позиции закрытые вручную/автоматически на бирже)
- Обычное закрытие через бота **работает корректно** ✅

---

## ДЕТАЛЬНЫЙ АНАЛИЗ КОДА

### ✅ ЧТО РАБОТАЕТ:

#### 1. Обычное закрытие позиции

**Файл**: `core/position_manager.py:1962-2060`

**Код**:
```python
async def close_position(self, symbol: str, reason: str = 'manual'):
    """Close position and update records"""
    # ... код закрытия ...

    # Clean up tracking
    del self.positions[symbol]  # Строка 2052

    # Clean up trailing stop
    trailing_manager = self.trailing_managers.get(position.exchange)  # Строка 2057
    if trailing_manager:
        await trailing_manager.on_position_closed(symbol, realized_pnl)  # Строка 2059 ✅
```

**Статус**: ✅ **РАБОТАЕТ КОРРЕКТНО**

**Путь вызовов**:
1. `position_manager.close_position()`
2. → `trailing_manager.on_position_closed()`
3. → `del self.trailing_stops[symbol]` (строка 1142)
4. → `await self._delete_state(symbol)` (строка 1145)
5. → `repository.delete_trailing_stop_state()` (строка 312)
6. → `DELETE FROM monitoring.trailing_stop_state WHERE symbol=$1 AND exchange=$2` (repository.py:937)

**Тестирование**:
- ✅ Протестировано на AIAUSDT (закрыта 21:22:14)
- ✅ Запись в БД удалена
- ✅ Логи: "Position AIAUSDT closed, trailing stop removed"

---

#### 2. Закрытие через market order

**Файл**: `core/aged_position_manager.py:211-226`

**Код**:
```python
if order:
    # FIX: Notify trailing stop manager of position closure
    if hasattr(self.position_manager, 'trailing_managers'):
        # ...
        await trailing_manager.on_position_closed(original_symbol, realized_pnl=None)  # Строка 223 ✅
```

**Статус**: ✅ **РАБОТАЕТ КОРРЕКТНО**

**Сценарий**: Aged position закрывается market ордером

**Путь вызовов**: Аналогичен пункту 1

---

### ❌ ЧТО НЕ РАБОТАЕТ:

#### 1. Phantom cleanup в aged_position_manager

**Файл**: `core/aged_position_manager.py:318-333`

**Проблемный код**:
```python
# CRITICAL: Verify position exists on exchange before any operations
position_exists = await self.position_manager.verify_position_exists(symbol, position.exchange)
if not position_exists:
    logger.warning(f"🗑️ Position {symbol} not found on {position.exchange} - marking as phantom")
    # Position doesn't exist on exchange - close it in database
    await self.position_manager.repository.close_position(
        position.id,
        close_price=position.current_price or position.entry_price,
        pnl=0,
        pnl_percentage=0,
        reason='PHANTOM_AGED'
    )
    # Remove from position manager's memory
    if symbol in self.position_manager.positions:
        del self.position_manager.positions[symbol]  # Строка 332
    return  # ❌ НЕТ ВЫЗОВА on_position_closed!
```

**Статус**: ❌ **НЕ РАБОТАЕТ**

**Что происходит**:
1. Позиция закрывается **вручную на бирже** (или по SL)
2. Aged manager обнаруживает что позиции нет
3. Помечает позицию как PHANTOM_AGED в БД
4. Удаляет из `self.positions`
5. **НО!** НЕ вызывает `on_position_closed()`
6. TS state **ОСТАЕТСЯ** в БД ❌

**Доказательство бага**:
- ✅ DRIFTUSDT закрыта 20:33:40 (reason=PHANTOM_AGED)
- ✅ Запись в БД positions.status=closed
- ❌ Запись в trailing_stop_state **ОСТАЛАСЬ**
- ✅ Лог: "Position DRIFTUSDT not found on binance - marking as phantom"
- ❌ НЕТ лога "trailing stop removed"

---

#### 2. Phantom cleanup в position_manager (неиспользуемый код)

**Файл**: `core/position_manager.py:2795-2832`

**Проблемный код**:
```python
for symbol in phantom_symbols:
    position = local_positions[symbol]
    logger.warning(f"Phantom position detected: {symbol}")

    try:
        # Remove from local cache
        if symbol in self.positions:
            del self.positions[symbol]  # Строка 2802 ❌ НЕТ ВЫЗОВА on_position_closed!

        # Update database - mark as closed
        await self.repository.update_position_status(
            position.id,
            'closed',
            notes='PHANTOM_CLEANUP'
        )
```

**Статус**: ⚠️ **ПОТЕНЦИАЛЬНО НЕ РАБОТАЕТ** (но код НЕ ВЫЗЫВАЕТСЯ)

**Проверка**:
```bash
grep "check_zombie_positions(" **/*.py
# Результат: No matches found
```

Этот метод `check_zombie_positions()` **НЕ вызывается** нигде в коде - старый неиспользуемый код.

---

## ПЛАН ИСПРАВЛЕНИЯ

### ЭТАП 1: ИСПРАВЛЕНИЕ БАГА В aged_position_manager.py

#### Изменения:

**Файл**: `core/aged_position_manager.py`
**Строки**: 318-333

**До (проблемный код)**:
```python
if not position_exists:
    logger.warning(f"🗑️ Position {symbol} not found on {position.exchange} - marking as phantom")
    # Position doesn't exist on exchange - close it in database
    await self.position_manager.repository.close_position(
        position.id,
        close_price=position.current_price or position.entry_price,
        pnl=0,
        pnl_percentage=0,
        reason='PHANTOM_AGED'
    )
    # Remove from position manager's memory
    if symbol in self.position_manager.positions:
        del self.position_manager.positions[symbol]
    return
```

**После (исправленный код)**:
```python
if not position_exists:
    logger.warning(f"🗑️ Position {symbol} not found on {position.exchange} - marking as phantom")

    # Close it in database
    await self.position_manager.repository.close_position(
        position.id,
        close_price=position.current_price or position.entry_price,
        pnl=0,
        pnl_percentage=0,
        reason='PHANTOM_AGED'
    )

    # NEW: Notify trailing stop manager of position closure
    # This ensures TS state is deleted from database
    if hasattr(self.position_manager, 'trailing_managers'):
        exchange_name = position.exchange
        if exchange_name in self.position_manager.trailing_managers:
            trailing_manager = self.position_manager.trailing_managers[exchange_name]
            try:
                await trailing_manager.on_position_closed(symbol, realized_pnl=None)
                logger.debug(f"Notified trailing stop manager of {symbol} phantom closure")
            except Exception as e:
                logger.warning(f"Failed to notify trailing manager for {symbol}: {e}")

    # Remove from position manager's memory
    if symbol in self.position_manager.positions:
        del self.position_manager.positions[symbol]
    return
```

**Обоснование изменений**:
1. Добавлен вызов `trailing_manager.on_position_closed()` ПЕРЕД удалением из памяти
2. Использован тот же паттерн что и в строках 211-226 (market order cleanup)
3. Обернут в try-except для предотвращения падения всего процесса
4. Добавлен debug лог для отслеживания

---

### ЭТАП 2: CLEANUP POSITION_MANAGER.PY (опционально)

**Файл**: `core/position_manager.py`
**Строки**: 2747-2850

**Действие**: Удалить неиспользуемый метод `check_zombie_positions()` или добавить вызов `on_position_closed()` на строке 2802.

**Рекомендация**: **УДАЛИТЬ** целиком, т.к.:
1. Метод нигде не вызывается
2. Функционал дублирует aged_position_manager
3. Упрощает кодовую базу

**Альтернатива**: Если метод планируется использовать, добавить вызов on_position_closed аналогично ЭТАПУ 1.

---

### ЭТАП 3: CLEANUP УСТАРЕВШИХ ЗАПИСЕЙ В PROD БД

#### SQL скрипт для очистки:

**Файл**: `database/migrations/008_cleanup_stale_ts_states.sql`

```sql
-- Migration: Cleanup stale TS states for closed positions
-- Date: 2025-10-20
-- Removes trailing_stop_state records where position is closed or doesn't exist

BEGIN;

-- Log before cleanup
DO $$
DECLARE
    stale_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO stale_count
    FROM monitoring.trailing_stop_state ts
    LEFT JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange AND p.status = 'active'
    WHERE p.id IS NULL;

    RAISE NOTICE 'Found % stale TS state records to cleanup', stale_count;
END $$;

-- Delete stale TS states
DELETE FROM monitoring.trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1
    FROM monitoring.positions p
    WHERE p.symbol = ts.symbol
      AND p.exchange = ts.exchange
      AND p.status = 'active'
);

-- Log after cleanup
DO $$
DECLARE
    remaining INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining FROM monitoring.trailing_stop_state;
    RAISE NOTICE 'Remaining TS state records: %', remaining;
END $$;

COMMIT;
```

**Запуск**:
```bash
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -f database/migrations/008_cleanup_stale_ts_states.sql
```

**Ожидаемый результат**:
- Удалит 29 устаревших записей
- Останутся только записи для активных позиций

---

### ЭТАП 4: ДОБАВЛЕНИЕ АВТОМАТИЧЕСКОГО CLEANUP (опционально)

#### Периодическая очистка orphan TS states

**Файл**: `database/repository.py`
**Метод**: `cleanup_orphan_ts_states()` (строка 949)

**Код уже СУЩЕСТВУЕТ!**
```python
async def cleanup_orphan_ts_states(self) -> int:
    """
    Clean up trailing stop states for positions that no longer exist

    Returns:
        int: Number of orphan states deleted
    """
    query = """
        DELETE FROM monitoring.trailing_stop_state ts
        WHERE NOT EXISTS (
            SELECT 1 FROM monitoring.positions p
            WHERE p.symbol = ts.symbol
              AND p.exchange = ts.exchange
              AND p.status = 'active'
        )
    """

    try:
        result = await self.pool.execute(query)
        # Parse DELETE result: "DELETE N"
        deleted_count = int(result.split()[-1]) if result else 0
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} orphan TS states")
        return deleted_count
    except Exception as e:
        logger.error(f"Failed to cleanup orphan TS states: {e}")
        return 0
```

**Нужно добавить**: Периодический вызов в main loop

**Файл**: `main.py`

**Добавить в startup после восстановления позиций**:
```python
# After loading positions
logger.info("Cleaning up orphan TS states...")
orphan_count = await repository.cleanup_orphan_ts_states()
logger.info(f"✅ Cleaned up {orphan_count} orphan TS states")
```

**И/или добавить в периодический task**:
```python
# В main loop каждые 1 час
async def periodic_cleanup():
    while True:
        await asyncio.sleep(3600)  # 1 hour
        try:
            orphan_count = await repository.cleanup_orphan_ts_states()
            if orphan_count > 0:
                logger.info(f"Periodic cleanup: removed {orphan_count} orphan TS states")
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")
```

**Обоснование**:
- Защита от будущих багов
- Автоматическое восстановление консистентности
- Минимальная нагрузка (раз в час)

---

## ТЕСТИРОВАНИЕ

### ТЕСТ 1: Phantom position cleanup

**Сценарий**:
1. Открыть позицию через бота
2. Дождаться создания TS state в БД
3. Закрыть позицию **вручную на бирже**
4. Дождаться aged_position_manager обнаружения phantom
5. Проверить БД

**Ожидаемый результат**:
- ✅ positions.status = 'closed'
- ✅ trailing_stop_state: запись **удалена**
- ✅ Лог: "Position {symbol} closed, trailing stop removed"

**Команда проверки**:
```bash
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT ts.symbol FROM monitoring.trailing_stop_state ts
LEFT JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange
WHERE p.status = 'closed' OR p.id IS NULL;
"
```

Должно вернуть 0 строк.

---

### ТЕСТ 2: Обычное закрытие через бота

**Сценарий**:
1. Открыть позицию
2. Закрыть через `position_manager.close_position()`
3. Проверить БД

**Ожидаемый результат**:
- ✅ Как и раньше - работает корректно
- ✅ TS state удаляется

---

### ТЕСТ 3: Market order closure

**Сценарий**:
1. Позиция достигает aged threshold
2. Aged manager закрывает market ордером
3. Проверить БД

**Ожидаемый результат**:
- ✅ Как и раньше - работает корректно
- ✅ TS state удаляется

---

### ТЕСТ 4: Миграция cleanup

**Сценарий**:
1. Запустить миграцию 008
2. Проверить количество удаленных записей
3. Проверить что активные TS остались

**Команды**:
```bash
# Before
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT COUNT(*) as stale FROM monitoring.trailing_stop_state ts
LEFT JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange AND p.status = 'active'
WHERE p.id IS NULL;
"

# Run migration
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -f database/migrations/008_cleanup_stale_ts_states.sql

# After - should be 0
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT COUNT(*) as stale FROM monitoring.trailing_stop_state ts
LEFT JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange AND p.status = 'active'
WHERE p.id IS NULL;
"

# Verify active TS still exist
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT COUNT(*) FROM monitoring.trailing_stop_state ts
JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange
WHERE p.status = 'active';
"
```

---

## ROLLOUT PLAN

### Шаг 1: ПОДГОТОВКА
- ✅ Создать backup БД
- ✅ Создать бэкап файлов перед изменениями
- ✅ Подготовить migration script
- ✅ Подготовить rollback plan

**Команды**:
```bash
# Backup DB
pg_dump -U evgeniyyanvarskiy fox_crypto > backup_before_ts_cleanup_fix_20251020.sql

# Backup code
cp core/aged_position_manager.py core/aged_position_manager.py.backup_before_ts_cleanup_fix
```

---

### Шаг 2: ПРИМЕНЕНИЕ ИЗМЕНЕНИЙ
1. ✅ Остановить бота
2. ✅ Применить изменения в `aged_position_manager.py` (ЭТАП 1)
3. ✅ (Опционально) Удалить `check_zombie_positions()` (ЭТАП 2)
4. ✅ Запустить migration script (ЭТАП 3)
5. ✅ Проверить БД - stale records = 0
6. ✅ (Опционально) Добавить periodic cleanup (ЭТАП 4)
7. ✅ Запустить бота

---

### Шаг 3: МОНИТОРИНГ
1. Проверить логи на наличие "Failed to notify trailing manager"
2. Через 1 час проверить БД на новые stale records
3. Закрыть позицию вручную на бирже - протестировать phantom cleanup
4. Проверить что TS state удалилась

**Команды мониторинга**:
```bash
# Check for errors
grep "Failed to notify trailing manager" logs/trading_bot.log

# Check for stale TS states
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT COUNT(*) as stale FROM monitoring.trailing_stop_state ts
LEFT JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange AND p.status = 'active'
WHERE p.id IS NULL;
"

# Should always be 0 after fix
```

---

### Шаг 4: ROLLBACK PLAN (если что-то пошло не так)

**Если бот не запускается**:
```bash
# Restore code
cp core/aged_position_manager.py.backup_before_ts_cleanup_fix core/aged_position_manager.py

# Restart
python main.py
```

**Если много orphan TS states**:
```bash
# Manual cleanup
PGPASSWORD='' psql -U evgeniyyanvarskiy -d fox_crypto -c "
DELETE FROM monitoring.trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1 FROM monitoring.positions p
    WHERE p.symbol = ts.symbol AND p.exchange = ts.exchange AND p.status = 'active'
);
"
```

---

## ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ (будущее)

### 1. Добавить constraint в БД

**Файл**: `database/migrations/009_add_ts_position_fk.sql`

```sql
-- Add foreign key constraint to ensure TS state references valid position
ALTER TABLE monitoring.trailing_stop_state
ADD COLUMN position_id INTEGER REFERENCES monitoring.positions(id) ON DELETE CASCADE;

-- Populate position_id for existing records
UPDATE monitoring.trailing_stop_state ts
SET position_id = p.id
FROM monitoring.positions p
WHERE ts.symbol = p.symbol AND ts.exchange = p.exchange AND p.status = 'active';

-- Make it NOT NULL after populating
ALTER TABLE monitoring.trailing_stop_state
ALTER COLUMN position_id SET NOT NULL;
```

**Эффект**: При удалении позиции TS state **автоматически удалится** (CASCADE).

**Недостаток**: Требует изменения schema, может сломать существующий код.

---

### 2. Добавить метрики для мониторинга

**Добавить в stats**:
```python
self.stats['orphan_ts_states'] = 0

# При periodic cleanup
self.stats['orphan_ts_states'] = orphan_count
```

**Добавить в health check**:
```python
orphan_count = await repository.count_orphan_ts_states()
if orphan_count > 10:
    health_status['warnings'].append(f"High orphan TS count: {orphan_count}")
```

---

## КРИТЕРИИ УСПЕХА

### Обязательные (must have):
- ✅ Нет stale TS states в БД
- ✅ При phantom cleanup вызывается on_position_closed
- ✅ Все тесты проходят
- ✅ Нет ошибок в логах

### Желательные (nice to have):
- ✅ Periodic cleanup работает
- ✅ Метрики orphan TS states = 0
- ✅ Код упрощен (удален check_zombie_positions)

---

## ПРИОРИТИЗАЦИЯ

### P0 - КРИТИЧНО (сделать сейчас):
1. ✅ ЭТАП 1: Исправить aged_position_manager.py
2. ✅ ЭТАП 3: Cleanup prod БД

### P1 - ВАЖНО (сделать в течение недели):
3. ✅ ЭТАП 2: Удалить неиспользуемый код
4. ✅ ЭТАП 4: Добавить periodic cleanup
5. ✅ Все тесты

### P2 - ЖЕЛАТЕЛЬНО (сделать позже):
6. ⏸️ Добавить FK constraint
7. ⏸️ Добавить метрики

---

## ЗАКЛЮЧЕНИЕ

### Корневая причина:
**aged_position_manager** при phantom cleanup НЕ вызывает `on_position_closed()`, что приводит к утечке записей TS state в БД.

### Решение:
Добавить вызов `trailing_manager.on_position_closed()` в phantom cleanup пути (строка 332 aged_position_manager.py).

### Объем изменений:
- **1 файл**: aged_position_manager.py
- **~15 строк кода**
- **1 migration script**
- **Время внедрения**: 30 минут

### Риски:
- ⚠️ **Низкий** - изменения локализованы
- ⚠️ **Тестируемо** - легко проверить вручную
- ⚠️ **Откатываемо** - простой rollback

### Следующие шаги:
1. ✅ Получить approval
2. 🔲 Создать бэкапы
3. 🔲 Применить исправления
4. 🔲 Тестирование
5. 🔲 Мониторинг

---

**Конец плана**
**Дата**: 2025-10-20
**Автор**: Claude (AI Assistant)
**Статус**: Готов к реализации
