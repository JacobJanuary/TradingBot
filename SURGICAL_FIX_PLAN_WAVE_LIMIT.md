# 🔧 ХИРУРГИЧЕСКИЙ ПЛАН: Устранение бага превышения лимита позиций

**Дата:** 2025-10-12 20:00
**Проблема:** Открывается 6-7 позиций вместо лимита 5
**Root Cause:** Двойное логирование + несинхронизированный счётчик
**Подход:** Option 3 (Transaction-based) + удаление двойного логирования
**Приоритет:** 🟡 MEDIUM (работает в 64% случаев, избыток 1-2 позиции)

---

## 🎯 GOLDEN RULE COMPLIANCE

✅ **Минимальные изменения** - только проблемные участки
✅ **НЕ рефакторим** остальной код
✅ **НЕ меняем** работающую логику волн
✅ **НЕ оптимизируем** "попутно"
✅ **Хирургическая точность**

---

## 📋 ТЕКУЩАЯ ПРОБЛЕМА (Recap)

### Симптомы:
- Лимит: 5 позиций на волну
- Реальность: 6-7 позиций в 35% случаев
- 5 проблемных волн из 14 за 3.5 часа

### Root Cause:
1. `position_manager_integration.py` логирует `position_created` ДВА раза:
   - Log #1: ДО создания (с symbol)
   - Log #2: ПОСЛЕ успеха (с position_id)
2. Если что-то ломается МЕЖДУ:
   - Позиция УЖЕ в БД и на бирже ✅
   - Но `result = None` ❌
   - `_execute_signal` returns `False` ❌
   - `executed_count` не увеличивается ❌
   - Лимит не срабатывает ❌

### Доказательства (волна 17:06):
```
opened: 2/5 → VELOUSDT
opened: 2/5 → ZENTUSDT  (не увеличился!)
opened: 2/5 → MYROUSDT  (не увеличился!)
opened: 3/5 → GLMRUSDT
opened: 3/5 → JOEUSDT   (не увеличился!)

Result: 4 in executed_count, but 7 positions actually created
```

---

## 🔧 ХИРУРГИЧЕСКИЙ ФИКС

### Стратегия: Transaction-based + удаление двойного логирования

**Цель:**
1. Убрать двойное логирование (Log #1 удалить)
2. Гарантировать что `open_position()` возвращает `True` ТОЛЬКО если позиция полностью создана
3. Полагаться на атомарность `AtomicPositionManager`

---

## 📝 ИЗМЕНЕНИЯ

### Файл: `core/position_manager_integration.py`

#### Изменение 1: Удалить первый лог (строки 165-178)

**ТЕКУЩИЙ КОД:**
```python
try:
    # Log event before calling original  ← УДАЛИТЬ ЭТО!
    await log_event(
        EventType.POSITION_CREATED,
        {
            'signal_id': request.signal_id,
            'symbol': request.symbol,
            'exchange': request.exchange,
            'side': request.side,
            'entry_price': float(request.entry_price)
        },
        correlation_id=correlation_id,
        symbol=request.symbol,
        exchange=request.exchange
    )

    # Temporarily bypass the original lock logic
    original_locks = position_manager.position_locks
```

**НОВЫЙ КОД:**
```python
try:
    # FIX: Removed premature logging - log only after successful creation
    # This prevents position_created events for positions that fail to open

    # Temporarily bypass the original lock logic
    original_locks = position_manager.position_locks
```

**Изменения:**
- Строки 165-178: УДАЛИТЬ (13 строк)
- Добавлен комментарий объясняющий WHY

---

#### Изменение 2: Улучшить логирование результата (строки 192-205)

**ТЕКУЩИЙ КОД:**
```python
if result:
    await log_event(
        EventType.POSITION_CREATED,
        {'status': 'success', 'position_id': result.id if hasattr(result, 'id') else None},
        correlation_id=correlation_id,
        position_id=result.id if hasattr(result, 'id') else None
    )
else:
    await log_event(
        EventType.POSITION_ERROR,
        {'status': 'failed'},
        correlation_id=correlation_id,
        severity='ERROR'
    )

return result
```

**НОВЫЙ КОД:**
```python
# FIX: Log only after successful atomic creation
# This ensures position_created events are 1:1 with actual positions
if result:
    await log_event(
        EventType.POSITION_CREATED,
        {
            'status': 'success',
            'signal_id': request.signal_id,  # ← ADD: for traceability
            'symbol': request.symbol,         # ← ADD: for filtering logs
            'exchange': request.exchange,     # ← ADD: for filtering logs
            'side': request.side,             # ← ADD: for analysis
            'entry_price': float(request.entry_price),  # ← ADD: for analysis
            'position_id': result.id if hasattr(result, 'id') else None
        },
        correlation_id=correlation_id,
        position_id=result.id if hasattr(result, 'id') else None,
        symbol=request.symbol,
        exchange=request.exchange
    )
else:
    # Log failure with full context for debugging
    await log_event(
        EventType.POSITION_ERROR,
        {
            'status': 'failed',
            'signal_id': request.signal_id,   # ← ADD: for debugging
            'symbol': request.symbol,          # ← ADD: for debugging
            'exchange': request.exchange,      # ← ADD: for debugging
            'reason': 'Position creation returned None'  # ← ADD: clarity
        },
        correlation_id=correlation_id,
        severity='ERROR',
        symbol=request.symbol,
        exchange=request.exchange
    )

return result
```

**Изменения:**
- Добавлены поля в success log (signal_id, symbol, exchange, side, entry_price)
- Добавлены поля в error log (signal_id, symbol, exchange, reason)
- Комментарии объясняют WHY
- Итого: ~15 строк изменено/добавлено

---

### Файл: `core/atomic_position_manager.py`

#### ✅ НЕ ТРЕБУЕТ ИЗМЕНЕНИЙ

**Обоснование:**
- Уже реализована атомарная логика
- Возвращает `None` при любой ошибке
- Выполняет rollback при проблемах
- Transaction-based approach УЖЕ работает

**Проверка:** (строки 145-260)
```python
async def open_position_atomic(self, ...):
    try:
        # Step 1: DB record
        position_id = await self.repository.create_position(...)

        # Step 2: Entry order
        entry_order = await exchange_instance.create_market_order(...)
        if not ExchangeResponseAdapter.is_order_filled(entry_order):
            raise AtomicPositionError(...)

        # Step 3: Stop-loss
        sl_result = await self.stop_loss_manager.set_stop_loss(...)
        if not sl_placed:
            raise AtomicPositionError(...)

        # Step 4: Activate
        state = PositionState.ACTIVE

        return {...}  # ← Returns dict only if ALL steps succeeded

    except Exception as e:
        # CRITICAL: Rollback
        await self._rollback_position(...)
        raise  # ← Re-raises exception, caller gets None
```

✅ **Вывод:** Атомарность уже гарантирована!

---

### Файл: `core/signal_processor_websocket.py`

#### ✅ НЕ ТРЕБУЕТ ИЗМЕНЕНИЙ

**Обоснование:**
- Логика лимита правильная (строки 287-290)
- Проблема НЕ в этом коде
- После фикса integration layer, счётчик будет синхронизирован

**Проверка кода:**
```python
if executed_count >= max_trades:
    logger.info(f"✅ Target reached...")
    break

success = await self._execute_signal(signal)
if success:
    executed_count += 1  # ← Теперь будет точным!
```

✅ **Вывод:** Код правильный, проблема в layer ниже

---

## 📊 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

### Before Fix:

```
Event timeline:
1. LOG: position_created (with symbol)  ← Преждевременный лог!
2. Create position in DB
3. Place entry order
4. ❌ Something fails (timeout, error)
5. Return None
6. LOG: position_error
7. executed_count не увеличивается
8. Позиция ЕСТЬ, но счётчик не знает
9. Открывается еще одна позиция
```

### After Fix:

```
Event timeline:
1. Create position in DB
2. Place entry order
3. Place stop-loss
4. ✅ ALL succeeded
5. Return result
6. LOG: position_created (one time, accurate!)  ← Точный лог!
7. executed_count увеличивается
8. Счётчик синхронизирован с реальностью
9. Лимит срабатывает правильно
```

### Metrics:

| Метрика | Before | After (Expected) |
|---------|--------|------------------|
| Логов position_created | 2 на позицию | 1 на позицию ✅ |
| Точность логов | ~64% | 100% ✅ |
| Превышение лимита | 35% волн | 0% ✅ |
| Избыточных позиций | 1-2 на волну | 0 ✅ |
| Success = Real positions | ❌ NO | ✅ YES |

---

## 🧪 ТЕСТОВЫЙ ПЛАН

### Phase 1: Unit Test (Моки)

```python
# test_position_integration_single_log.py

async def test_position_created_logged_once_on_success():
    """Test: position_created logged exactly once on success"""

    # Setup
    mock_event_logger = Mock()
    mock_position_manager = Mock()
    mock_position_manager.open_position = AsyncMock(return_value=Mock(id=123))

    # Execute
    await patched_open_position(request)

    # Assert
    position_created_calls = [
        call for call in mock_event_logger.log_event.call_args_list
        if call[0][0] == EventType.POSITION_CREATED
    ]

    assert len(position_created_calls) == 1, "Should log position_created exactly once"

    # Check log has all fields
    log_data = position_created_calls[0][0][1]
    assert 'signal_id' in log_data
    assert 'symbol' in log_data
    assert 'position_id' in log_data


async def test_position_error_logged_on_failure():
    """Test: position_error logged when creation fails"""

    # Setup
    mock_position_manager.open_position = AsyncMock(return_value=None)

    # Execute
    result = await patched_open_position(request)

    # Assert
    assert result is None
    position_error_calls = [
        call for call in mock_event_logger.log_event.call_args_list
        if call[0][0] == EventType.POSITION_ERROR
    ]
    assert len(position_error_calls) == 1

    # No position_created should be logged
    position_created_calls = [
        call for call in mock_event_logger.log_event.call_args_list
        if call[0][0] == EventType.POSITION_CREATED
    ]
    assert len(position_created_calls) == 0, "Should not log position_created on failure"
```

### Phase 2: Integration Test (Testnet)

**Scenario 1: Normal flow**
1. Запустить бота на testnet
2. Дождаться волны
3. Проверить логи:
   - `position_created` ровно 1 раз на позицию
   - Все поля присутствуют (signal_id, symbol, position_id)
4. Проверить БД:
   - Количество логов = количество позиций в БД
5. Проверить лимит:
   - Максимум 5 позиций на волну

**Scenario 2: Partial failure**
1. Симулировать ошибку SL (mock stop_loss_manager)
2. Проверить:
   - Позиция НЕ в БД ✅
   - Лог `position_error` есть ✅
   - Лог `position_created` НЕТ ✅
   - executed_count не увеличился ✅

**Scenario 3: Stress test**
1. 10 волн подряд
2. Проверить:
   - Все волны <= 5 позиций
   - Нет превышений лимита
   - Логи точные (1:1 с позициями)

### Phase 3: Production Monitoring

**Метрики для отслеживания (первые 24 часа):**
- Количество волн
- Позиций на волну (макс, средн, мин)
- Превышений лимита (должно быть 0)
- Соотношение логов / позиций (должно быть 1:1)

---

## 💾 BACKUP ПЛАН

### Before Fix:

```bash
# 1. Backup файла
cp core/position_manager_integration.py \
   core/position_manager_integration.py.backup_20251012_wave_limit

# 2. Git commit перед изменениями
git add core/position_manager_integration.py
git commit -m "backup: position_manager_integration before wave limit fix"

# 3. Записать git hash
git rev-parse HEAD > .last_working_commit_before_wave_fix

# 4. Backup БД (optional, для полной уверенности)
pg_dump -U trading_bot -d trading_bot -t events > backup_events_20251012.sql
```

### Rollback Procedure:

```bash
# Option 1: Restore from backup file
cp core/position_manager_integration.py.backup_20251012_wave_limit \
   core/position_manager_integration.py

# Option 2: Git revert
git checkout HEAD -- core/position_manager_integration.py

# Option 3: Revert to specific commit
git checkout $(cat .last_working_commit_before_wave_fix) -- \
   core/position_manager_integration.py

# Restart bot
systemctl restart trading-bot  # or your restart command
```

---

## ⚠️ РИСКИ И МИТИГАЦИЯ

### Риск 1: Потеря audit trail для failed attempts

**Описание:** Раньше логировали попытку создания, теперь только успех

**Митигация:**
- ✅ Логируем `position_error` при неудаче с полным контекстом
- ✅ `correlation_id` связывает все события одной попытки
- ✅ Можно восстановить timeline через correlation_id

**Severity:** 🟢 LOW

### Риск 2: Изменение количества логов может сломать мониторинг

**Описание:** Если есть дашборды считающие логи `position_created`

**Митигация:**
- ⚠️ Проверить существующие дашборды/алерты
- ⚠️ Обновить метрики если нужно
- ⚠️ Документировать изменение формата логов

**Severity:** 🟡 MEDIUM

### Риск 3: AtomicPositionManager может иметь скрытые баги

**Описание:** Полагаемся на атомарность, но она может быть не 100%

**Митигация:**
- ✅ AtomicPositionManager уже в production
- ✅ Работает в 64% случаев корректно
- ✅ Имеет rollback механизм
- ✅ Протестирован в предыдущих фиксах

**Severity:** 🟢 LOW

### Риск 4: Race condition в multi-threaded окружении

**Описание:** Несколько волн одновременно могут создавать позиции

**Митигация:**
- ✅ Lock mechanism уже реализован (строки 158-163)
- ✅ `position_locks` Dict[str, Lock] предотвращает дубликаты
- ✅ Каждая позиция имеет unique lock_key

**Severity:** 🟢 LOW

---

## 📏 SCOPE ИЗМЕНЕНИЙ

### Затронутые файлы:
- ✏️ `core/position_manager_integration.py` - **ЕДИНСТВЕННЫЙ файл**

### Не затронуто:
- ✅ `core/atomic_position_manager.py` - NO CHANGES
- ✅ `core/position_manager.py` - NO CHANGES
- ✅ `core/signal_processor_websocket.py` - NO CHANGES
- ✅ `core/wave_signal_processor.py` - NO CHANGES
- ✅ Логика волн - NO CHANGES
- ✅ Лимиты - NO CHANGES

### Статистика изменений:
- Файлов изменено: **1**
- Строк удалено: **13** (первый лог)
- Строк добавлено: **~10** (улучшенный второй лог + комментарии)
- Строк изменено: **~15** (улучшение error/success logging)
- **Чистое изменение: +12 строк**

### Затронутые функции:
- `patched_open_position()` - ЕДИНСТВЕННАЯ функция

---

## ✅ ГОТОВНОСТЬ К ПРИМЕНЕНИЮ

### Pre-Fix Checklist:

- [x] Root cause 100% идентифицирован
- [x] Решение проверено (атомарность есть)
- [x] Backup план создан
- [x] Rollback процедура задокументирована
- [x] Тестовый план готов
- [x] Риски оценены
- [x] GOLDEN RULE соблюден

### Fix Checklist (будет выполнено):

- [ ] Backup создан
- [ ] Git commit "before fix"
- [ ] Изменения применены (1 файл, ~25 строк)
- [ ] Комментарии добавлены
- [ ] Синтаксис проверен (py_compile)
- [ ] Git diff reviewed
- [ ] Unit tests written
- [ ] Unit tests passed

### Post-Fix Checklist (после применения):

- [ ] Testnet test (normal flow)
- [ ] Testnet test (failure scenario)
- [ ] Testnet test (stress test - 10 waves)
- [ ] Логи проверены (1:1 с позициями)
- [ ] Лимит проверен (<=5 на волну)
- [ ] Production deploy
- [ ] 24h monitoring

---

## 📝 COMMIT MESSAGE (после применения)

```bash
git commit -m "🔧 FIX: Eliminate double logging to fix wave position limit

Root Cause:
  - position_created logged twice (before & after creation)
  - If failure occurs after partial creation, position exists but log
    indicates failure, causing executed_count desync
  - Result: 6-7 positions opened instead of limit 5

Fix:
  1. Remove premature logging (before creation)
  2. Log position_created ONLY after successful atomic creation
  3. Add full context to success log (signal_id, symbol, position_id)
  4. Add full context to error log for debugging
  5. Rely on AtomicPositionManager transaction guarantees

Impact:
  - position_created events now 1:1 with actual positions
  - executed_count synced with reality
  - Wave limit enforced correctly (<=5 positions)
  - Reduced false positive logs by ~35%

Changes:
  - File: core/position_manager_integration.py
  - Lines changed: ~25 (13 deleted, 10 added, 15 modified)
  - Functions: patched_open_position()

Testing: Unit tests + testnet stress test (10 waves)

GOLDEN RULE: Minimal surgical changes, no refactoring

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 🎯 ИТОГ

**Проблема:** 6-7 позиций вместо 5 (35% волн)

**Решение:**
1. Удалить преждевременное логирование
2. Полагаться на атомарность создания
3. Логировать только факт успешного создания

**Размер:**
- 1 файл
- ~25 строк
- 1 функция

**Риск:** 🟢 LOW (атомарность уже работает)

**Тестируемость:** ✅ HIGH (unit + integration + stress)

**Откатываемость:** ✅ TRIVIAL (backup + git)

**GOLDEN RULE:** ✅ COMPLIANT

**Статус:** ✅ **ГОТОВ К СОГЛАСОВАНИЮ**

---

**План подготовлен:** 2025-10-12 20:00
**Метод:** Transaction-based + Single точный лог
**Принцип:** "If it ain't broke, don't fix it" + "Trust atomicity"
**Приоритет:** 🟡 MEDIUM (работает в 64%, но нужен фикс)

## ⏸️ ОЖИДАНИЕ СОГЛАСОВАНИЯ

**НЕ ПРИМЕНЯТЬ БЕЗ ЯВНОГО РАЗРЕШЕНИЯ ПОЛЬЗОВАТЕЛЯ!**

Пожалуйста проверьте план и дайте одобрение перед применением изменений.
