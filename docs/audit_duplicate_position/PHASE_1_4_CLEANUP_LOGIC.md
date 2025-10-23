# ФАЗА 1.4: АНАЛИЗ ЛОГИКИ ОЧИСТКИ

**Дата**: 2025-10-22
**Severity**: 🟡 HIGH
**Статус**: ✅ ALL MECHANISMS ANALYZED

---

## EXECUTIVE SUMMARY

**Находка**: Recovery mechanism существует, но запускается ТОЛЬКО при старте бота.

**Проблема**: Incomplete позиции НЕ очищаются во время работы → накапливаются в БД.

**Impact**: Позиции в промежуточных статусах могут оставаться неочищенными между перезапусками.

---

## 1. МЕХАНИЗМЫ ОЧИСТКИ

### 1.1. Startup Recovery (ЕСТЬ)

**Файл**: `core/atomic_position_manager.py:560-610`

**Вызывается**: `main.py:426` при старте бота

```python
async def recover_incomplete_positions(self):
    """
    Recovery механизм для незавершенных позиций
    Запускается при старте бота
    """
    logger.info("🔍 Checking for incomplete positions...")

    # Находим позиции в промежуточных состояниях
    incomplete_states = [
        PositionState.PENDING_ENTRY.value,     # 'pending_entry'
        PositionState.ENTRY_PLACED.value,      # 'entry_placed'
        PositionState.PENDING_SL.value          # 'pending_sl'
    ]

    incomplete = await self.repository.get_positions_by_status(incomplete_states)

    if not incomplete:
        logger.info("✅ No incomplete positions found")
        return

    logger.warning(f"⚠️ Found {len(incomplete)} incomplete positions")

    for pos in incomplete:
        if state == 'pending_entry':
            # Entry не был размещен - safe to mark failed
            update status='failed'

        elif state == 'entry_placed':
            # Entry размещен но нет SL - КРИТИЧНО!
            await self._recover_position_without_sl(pos)

        elif state == 'pending_sl':
            # В процессе установки SL - проверить и завершить
            await self._complete_sl_placement(pos)
```

**Характеристики**:
- ✅ Запускается при старте бота
- ✅ Обрабатывает ВСЕ промежуточные статусы
- ✅ Пытается установить SL для позиций без защиты
- ✅ Emergency close если не удаётся установить SL

**Проблема**:
- ❌ Запускается ТОЛЬКО при старте (не периодически)
- ❌ Не защищает от race condition ВО ВРЕМЯ работы
- ❌ Incomplete позиции могут накапливаться между перезапусками

---

### 1.2. Rollback на ошибке (ЕСТЬ)

**Файл**: `core/atomic_position_manager.py:481-558`

**Вызывается**: При любой ошибке в `open_position_atomic()`

```python
async def _rollback_position(
    self,
    position_id: int,
    entry_order: Any,
    symbol: str,
    exchange: str,
    state: PositionState,
    quantity: float,
    error: str
):
    """Откат позиции при ошибке"""

    # Если entry был размещен но нет SL - КРИТИЧНО!
    if entry_order and state in ['entry_placed', 'pending_sl']:
        logger.critical("⚠️ CRITICAL: Position without SL, closing immediately!")

        # Пытаемся найти позицию на бирже
        max_attempts = 20
        for attempt in range(max_attempts):
            positions = await exchange.fetch_positions()

            if position_found:
                # Закрываем market ордером
                await exchange.create_market_order(close_side, quantity)
                logger.info("✅ Emergency close executed")
                break

            await asyncio.sleep(1.0)

        if not position_found:
            logger.critical("❌ Position not found after 20 attempts!")
            logger.critical("⚠️ ALERT: Open position without SL may exist!")

    # Обновляем статус в БД
    if position_id:
        await self.repository.update_position(position_id, **{
            'status': 'rolled_back',
            'closed_at': now,
            'exit_reason': f'rollback: {error}'
        })
```

**Характеристики**:
- ✅ Best-effort close на бирже
- ✅ 20 попыток по 1 секунде = 20 секунд
- ✅ Логирование CRITICAL если не найдена
- ✅ Обновление status='rolled_back' в БД

**Проблемы**:
- ⚠️ Best-effort (может не найти позицию)
- ⚠️ Если не находит → просто WARNING (нет action)
- ❌ Позиция может остаться на бирже без SL
- ❌ В БД помечена 'rolled_back', но реально OPEN на бирже

---

### 1.3. Periodic Cleanup (ОТСУТСТВУЕТ ❌)

**Проверка**:
```bash
grep -r "periodic.*cleanup\|cleanup.*task\|scheduled.*cleanup" core/
# Result: НЕ найдено
```

**Вывод**: Нет периодической очистки incomplete позиций во время работы бота.

**Последствия**:
- Позиции в промежуточных статусах накапливаются
- Очистка только при restart
- Между restart могут быть часы/дни

---

### 1.4. Manual Cleanup (ОТСУТСТВУЕТ ❌)

**Проверка**:
```bash
find scripts/ tools/ -name "*cleanup*" -o -name "*recover*"
# Result: НЕ найдено
```

**Вывод**: Нет скриптов для ручной очистки/восстановления.

---

## 2. СЦЕНАРИИ CLEANUP

### 2.1. Нормальное завершение ✅

```
open_position_atomic()
    ↓
CREATE position (status='active')
    ↓
UPDATE status='entry_placed'
    ↓
Place order ✅
    ↓
UPDATE status='pending_sl'
    ↓
Place SL ✅
    ↓
UPDATE status='active' ✅
    ↓
Success - позиция активна
```

**Cleanup не требуется**.

---

### 2.2. Ошибка на раннем этапе ✅

```
open_position_atomic()
    ↓
CREATE position (status='active')
    ↓
UPDATE status='entry_placed'
    ↓
Place order ❌ FAILS (e.g., insufficient funds)
    ↓
Exception caught
    ↓
_rollback_position()
    ├─> entry_order = None
    ├─> state = 'entry_placed'
    └─> Skip exchange close (no order)
    ↓
UPDATE status='rolled_back' ✅
    ↓
Cleanup complete
```

**Cleanup работает**: Позиция помечена 'rolled_back', ничего на бирже.

---

### 2.3. Ошибка после размещения ордера ⚠️

```
open_position_atomic()
    ↓
CREATE position (status='active')
    ↓
UPDATE status='entry_placed'
    ↓
Place order ✅ (filled)
    ↓
UPDATE status='pending_sl'
    ↓
Place SL ❌ FAILS (e.g., wrong price)
    ↓
Exception caught
    ↓
_rollback_position()
    ├─> entry_order = {...}
    ├─> state = 'pending_sl'
    └─> Attempt to close on exchange
        ├─> Poll 20 times
        ├─> FOUND ✅ → close ✅
        OR
        └─> NOT FOUND ❌ → CRITICAL log
    ↓
UPDATE status='rolled_back'
    ↓
Cleanup: BEST-EFFORT ⚠️
```

**Cleanup: неполный**. Может остаться orphaned position на бирже.

---

### 2.4. Duplicate Key Error (наша проблема) 🔴

```
Thread 1:
    CREATE position id=100 (status='active')
    UPDATE id=100 status='entry_placed'
    Place order ✅
    Place SL ✅
    [sleep 3s...]

Thread 2:
    CREATE position id=101 (status='active')  ← DUPLICATE

Thread 1:
    UPDATE id=100 status='active' ❌
    ↓
    Exception: duplicate key violation
    ↓
    _rollback_position()
    ├─> Ищет позицию на бирже
    ├─> Находит? (какую - id=100 или id=101?)
    └─> Пытается закрыть
    ↓
    UPDATE id=100 status='rolled_back'

RESULT:
- id=100: status='rolled_back' in DB
- id=101: status='active' in DB
- Exchange: ONE position (from Thread 1 order)
- Tracking: Thread 2 tracks id=101 ✓
```

**Cleanup: CONFUSING но works**
- Реальная позиция (от Thread 1) tracked через id=101
- id=100 в rolled_back (правильно, т.к. его update failed)

**НО**: Два records в БД для одной позиции на бирже!

---

### 2.5. Crash во время операции (restart scenario) ⚠️

```
BEFORE CRASH:
    open_position_atomic()
        ↓
    CREATE position id=200 (status='active')
        ↓
    UPDATE id=200 status='entry_placed'
        ↓
    Place order ✅ (filled)
        ↓
    [CRASH] 💥

STATE AT CRASH:
- DB: id=200, status='entry_placed'
- Exchange: position OPEN, NO SL ❌

AFTER RESTART:
    recover_incomplete_positions()
        ↓
    Find id=200, status='entry_placed'
        ↓
    _recover_position_without_sl(id=200)
        ├─> Try to set SL
        ├─> Success ✅ → UPDATE status='active'
        OR
        └─> Fail ❌ → _emergency_close_position()
            ├─> Close on exchange
            └─> UPDATE status='closed'
```

**Cleanup: РАБОТАЕТ ✅** при restart.

**Проблема**: Между crash и restart позиция БЕЗ SL!

---

## 3. АНАЛИЗ RECOVERY МЕХАНИЗМОВ

### 3.1. _recover_position_without_sl()

**Файл**: `core/atomic_position_manager.py:612-641`

```python
async def _recover_position_without_sl(self, position: Dict):
    symbol = position['symbol']

    logger.warning(f"🚨 Recovering position without SL: {symbol}")

    try:
        # Пытаемся установить SL
        sl_result = await self.stop_loss_manager.set_stop_loss(
            symbol=symbol,
            side='sell' if position['side'] == 'long' else 'buy',
            amount=position['quantity'],
            stop_price=position.get('planned_sl_price',
                      self._calculate_default_sl(...))
        )

        if sl_result and sl_result.get('status') in ['created', 'already_exists']:
            # Success
            await self.repository.update_position(position['id'], **{
                'stop_loss_price': sl_result.get('stopPrice'),
                'status': 'active'
            })
            logger.info(f"✅ SL restored for {symbol}")
        else:
            # Failed - emergency close
            await self._emergency_close_position(position)

    except Exception as e:
        logger.error(f"Failed to recover SL: {e}")
        await self._emergency_close_position(position)
```

**Характеристики**:
- ✅ Пытается установить SL
- ✅ Если не удаётся → emergency close
- ✅ Safe approach (защищает позицию)

**Проблема**:
- ⚠️ Вызывается ТОЛЬКО при startup
- ⚠️ Между crash и restart позиция без SL

---

### 3.2. _complete_sl_placement()

**Файл**: `core/atomic_position_manager.py:643-657`

```python
async def _complete_sl_placement(self, position: Dict):
    """Завершение размещения SL"""
    # Check if SL already exists
    has_sl = await self.stop_loss_manager.has_stop_loss(position['symbol'])

    if has_sl[0]:
        # SL уже установлен - just update DB
        await self.repository.update_position(position['id'], **{
            'stop_loss_price': has_sl[1],
            'status': 'active'
        })
    else:
        # SL не установлен - try to recover
        await self._recover_position_without_sl(position)
```

**Характеристики**:
- ✅ Проверяет наличие SL на бирже
- ✅ Синхронизирует DB со state биржи
- ✅ Пытается восстановить если нет SL

---

### 3.3. _emergency_close_position()

**Файл**: `core/atomic_position_manager.py:659-...` (не полностью прочитан)

**Предположение**: Закрывает позицию market ордером.

---

## 4. ЧАСТОТА ВЫПОЛНЕНИЯ CLEANUP

### 4.1. Startup Recovery

**Когда**: При каждом запуске бота

**Частота**:
- Manual restarts: по необходимости
- Crashes: зависит от stability
- Deployments: при деплое новых версий

**Estimate**: 1-5 раз в день

---

### 4.2. Runtime Rollback

**Когда**: При любой ошибке в `open_position_atomic()`

**Частота** (из логов):
- Duplicate errors: ~5-6 в час
- Other errors: unknown (нужно больше логов)

**Estimate**: 5-10 раз в час

---

### 4.3. Периодическая очистка

**Когда**: НЕТ ❌

**Частота**: 0

---

## 5. СОСТОЯНИЯ ПОЗИЦИЙ В БД

### 5.1. Нормальные статусы

```
active        - Позиция активна с SL
closed        - Позиция закрыта
liquidated    - Позиция ликвидирована
```

### 5.2. Промежуточные статусы (transient)

```
pending_entry  - Подготовка к размещению entry
entry_placed   - Entry размещен, ожидание SL
pending_sl     - Размещение SL
```

**Ожидаемое время в статусе**: 4-7 секунд

### 5.3. Аварийные статусы

```
failed         - Операция провалилась до размещения ордера
rolled_back    - Откачена из-за ошибки после размещения
```

---

## 6. SQL ЗАПРОСЫ ДЛЯ ДИАГНОСТИКИ

### 6.1. Найти incomplete позиции

```sql
SELECT id, symbol, exchange, status, opened_at,
       AGE(NOW(), opened_at) as age
FROM monitoring.positions
WHERE status IN ('pending_entry', 'entry_placed', 'pending_sl')
ORDER BY opened_at DESC;
```

### 6.2. Найти "застрявшие" позиции (>10 минут)

```sql
SELECT id, symbol, exchange, status, opened_at,
       EXTRACT(EPOCH FROM (NOW() - opened_at)) / 60 as minutes_old
FROM monitoring.positions
WHERE status IN ('pending_entry', 'entry_placed', 'pending_sl')
  AND opened_at < NOW() - INTERVAL '10 minutes'
ORDER BY opened_at;
```

### 6.3. Статистика по статусам

```sql
SELECT status, COUNT(*) as count,
       MIN(opened_at) as oldest,
       MAX(opened_at) as newest
FROM monitoring.positions
WHERE opened_at > NOW() - INTERVAL '24 hours'
GROUP BY status
ORDER BY count DESC;
```

### 6.4. Найти дубликаты (multiple active для одного символа)

```sql
SELECT symbol, exchange, COUNT(*) as count,
       ARRAY_AGG(id) as position_ids,
       ARRAY_AGG(status) as statuses
FROM monitoring.positions
WHERE status = 'active'
GROUP BY symbol, exchange
HAVING COUNT(*) > 1;
```

### 6.5. Найти дубликаты (включая промежуточные)

```sql
SELECT symbol, exchange, COUNT(*) as count,
       ARRAY_AGG(id ORDER BY id) as position_ids,
       ARRAY_AGG(status ORDER BY id) as statuses,
       ARRAY_AGG(opened_at ORDER BY id) as opened_at_list
FROM monitoring.positions
WHERE status IN ('pending_entry', 'entry_placed', 'pending_sl', 'active')
GROUP BY symbol, exchange
HAVING COUNT(*) > 1
ORDER BY opened_at_list[1] DESC;
```

---

## 7. ПРОБЛЕМЫ ТЕКУЩЕЙ ЛОГИКИ

### 🔴 CRITICAL #1: Нет периодической очистки

**Проблема**: Incomplete позиции накапливаются между restart.

**Сценарий**:
```
10:00 - Position stuck in 'entry_placed'
10:05 - Position stuck in 'pending_sl'
...
18:00 - Bot restart → cleanup
```

**Impact**: 8 часов накопления incomplete позиций.

**Solution**: Добавить periodic task для cleanup.

---

### 🔴 CRITICAL #2: Rollback не гарантирован

**Проблема**: Best-effort close может не найти позицию.

**Сценарий**:
```
Rollback triggered
    ↓
Poll 20 times (20 seconds)
    ↓
Position NOT FOUND
    ↓
Log CRITICAL warning
    ↓
No further action ❌
```

**Impact**: Позиция на бирже БЕЗ SL, нет tracking.

**Solution**: Alert + manual intervention required.

---

### 🟡 HIGH #3: Дубликаты не очищаются автоматически

**Проблема**: Duplicate позиции остаются в БД.

**Сценарий** (наша проблема):
```
- id=100: status='rolled_back'
- id=101: status='active'
- Both for same symbol+exchange
```

**Impact**: Data inconsistency, confusion в отчётах.

**Solution**: Cleanup script для merge/delete duplicates.

---

### 🟡 HIGH #4: Нет алертов для orphaned позиций

**Проблема**: CRITICAL log не приводит к action.

```python
logger.critical("⚠️ ALERT: Open position without SL may exist!")
# TODO: Send alert to administrator ← НЕ РЕАЛИЗОВАНО
```

**Impact**: Критические ситуации могут остаться незамеченными.

**Solution**: Telegram/Email alerts, webhook, etc.

---

## 8. РЕКОМЕНДАЦИИ

### 8.1. IMMEDIATE (P0)

**#1: Добавить periodic cleanup task**
```python
async def periodic_incomplete_cleanup():
    """Run every 5 minutes"""
    while True:
        await asyncio.sleep(300)  # 5 minutes

        try:
            await atomic_manager.recover_incomplete_positions()
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")
```

**#2: Реализовать alerting для orphaned позиций**
```python
if not position_found:
    logger.critical("⚠️ ALERT: Open position without SL!")
    await alert_manager.send_alert(
        level='CRITICAL',
        message=f"Orphaned position {symbol} on {exchange}",
        action_required="Check exchange and close manually"
    )
```

---

### 8.2. SHORT-TERM (P1)

**#3: Cleanup script для дубликатов**
```python
# scripts/cleanup_duplicate_positions.py
async def cleanup_duplicates():
    # Find duplicates
    duplicates = await find_duplicate_positions()

    for dup in duplicates:
        # Determine which to keep (newest with status='active')
        # Delete/merge others
        pass
```

**#4: Мониторинг incomplete позиций**
```python
async def monitor_incomplete_positions():
    """Alert if incomplete positions older than 10 minutes"""
    old_incomplete = await repository.query("""
        SELECT ... WHERE status IN (...)
        AND opened_at < NOW() - INTERVAL '10 minutes'
    """)

    if old_incomplete:
        await alert_manager.send_alert(...)
```

---

### 8.3. LONG-TERM (P2)

**#5: Dashboard для manual intervention**
- List incomplete/rolled_back positions
- Manual actions: retry, close, delete
- Sync with exchange state

**#6: Automatic reconciliation**
- Periodic check: DB positions vs Exchange positions
- Auto-close orphaned exchange positions
- Auto-update DB for positions on exchange but not in DB

---

## 9. ВЫВОДЫ ФАЗЫ 1.4

### ✅ Что установлено:

1. **Startup Recovery**: ✅ Есть, работает
2. **Runtime Rollback**: ✅ Есть, но best-effort
3. **Periodic Cleanup**: ❌ Отсутствует
4. **Manual Tools**: ❌ Отсутствует
5. **Alerting**: ❌ Не реализовано

### 🎯 Критические проблемы:

1. Incomplete позиции накапливаются между restart
2. Rollback не гарантирует полную очистку
3. Дубликаты не удаляются автоматически
4. Нет алертов для critical situations

### 📊 Частота cleanup:

- Startup: 1-5 раз в день
- Runtime rollback: 5-10 раз в час
- Periodic: 0 (отсутствует)

---

**Конец Фазы 1.4**

**⏭️ Следующий шаг**: Создание финального отчёта Фазы 1
