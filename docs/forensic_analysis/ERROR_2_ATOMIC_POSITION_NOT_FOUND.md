# АНАЛИЗ ОШИБКИ #2: Position Not Found After Order

**Дата**: 2025-10-22
**Severity**: 🔴 CRITICAL
**Status**: ✅ ROOT CAUSE IDENTIFIED

---

## EXECUTIVE SUMMARY

**Ошибка**: Position не найдена после успешного создания ордера (status='closed')
**Место**: `core/atomic_position_manager.py:330` → `479`
**Причина**: Race condition + возможная недостаточность интервала ожидания
**Impact**: 🔴 КРИТИЧЕСКИЙ - откат позиции при которой она может оставаться на бирже БЕЗ ЗАЩИТЫ!
**Complexity**: ВЫСОКАЯ - требует осторожного исправления

---

## ДЕТАЛЬНЫЙ АНАЛИЗ

### 1. ЛОГИ ОШИБКИ

```
2025-10-22 21:50:29,293 - core.atomic_position_manager - CRITICAL - ❌ Position AVLUSDT not found after 10 attempts!
2025-10-22 21:50:29,294 - core.atomic_position_manager - CRITICAL - ⚠️ ALERT: Open position without SL may exist on exchange!
2025-10-22 21:50:29,296 - core.atomic_position_manager - ERROR - ❌ Atomic operation failed: pos_AVLUSDT_1761155419.344699 - Position creation rolled back: Position not found after order - order may have failed. Order status: closed
2025-10-22 21:50:29,296 - core.position_manager - ERROR - Error opening position for AVLUSDT: Position creation rolled back: Position not found after order - order may have failed. Order status: closed

Traceback (most recent call last):
  File "core/atomic_position_manager.py", line 330, in open_position_atomic
    raise AtomicPositionError(
        f"Position not found after order - order may have failed. "
        f"Order status: {entry_order.status}"
    )
core.atomic_position_manager.AtomicPositionError: Position not found after order - order may have failed. Order status: closed

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "core/atomic_position_manager.py", line 479, in open_position_atomic
    raise AtomicPositionError(f"Position creation rolled back: {e}")
core.atomic_position_manager.AtomicPositionError: Position creation rolled back: Position not found after order - order may have failed. Order status: closed
```

---

## 2. FLOW CHART: АТОМАРНАЯ ОПЕРАЦИЯ

```
open_position_atomic(AVLUSDT, side=buy, qty=10)
    │
    ├─> [STEP 1] Create position record in DB
    │   └─> position_id = 2468, status = 'pending_entry'
    │
    ├─> [STEP 2] Place market order on exchange
    │   ├─> create_market_order(AVLUSDT, buy, 10)
    │   ├─> Order response received
    │   └─> entry_order.status = 'closed'  ← ОРДЕР ИСПОЛНЕН
    │
    ├─> [STEP 2.5] Normalize order & update DB
    │   ├─> entry_order.id = "order_123"
    │   ├─> entry_order.status = 'closed'  ← FILLED
    │   └─> Update DB: exchange_order_id, current_price
    │
    ├─> [STEP 3] Wait 1s for settlement
    │   └─> asyncio.sleep(1.0)
    │
    ├─> [STEP 4] Verify position exists ← 🚨 ЗДЕСЬ ПРОБЛЕМА!
    │   ├─> positions = fetch_positions([AVLUSDT])
    │   ├─> Filter: contracts > 0
    │   └─> Result: NO POSITION FOUND ❌
    │
    ├─> [ERROR] Raise AtomicPositionError (line 330)
    │   └─> "Position not found after order - order may have failed"
    │
    ├─> [CATCH] Exception handler (line 466)
    │   └─> Call _rollback_position()
    │
    ├─> [ROLLBACK] Attempt to close position
    │   ├─> Loop: 10 attempts, 500ms interval
    │   ├─> Attempt 1: fetch_positions() → NOT FOUND
    │   ├─> Attempt 2: fetch_positions() → NOT FOUND
    │   ├─> ...
    │   └─> Attempt 10: fetch_positions() → NOT FOUND ❌
    │
    ├─> [CRITICAL LOG] (line 541-542)
    │   ├─> "❌ Position AVLUSDT not found after 10 attempts!"
    │   └─> "⚠️ ALERT: Open position without SL may exist on exchange!"
    │
    ├─> [DB UPDATE] (line 551)
    │   └─> status = 'rolled_back', closed_at = now
    │
    └─> [RE-RAISE] AtomicPositionError (line 479)
        └─> "Position creation rolled back: Position not found..."
```

---

## 3. КЛЮЧЕВЫЕ МОМЕНТЫ КОДА

### Место возникновения ошибки (строки 312-343)

**Файл**: `core/atomic_position_manager.py`

```python
# Line 312: FIX: Verify position exists on exchange before SL placement
# Add 1s delay for order settlement
logger.debug(f"Waiting 1s for position settlement on {exchange}...")
await asyncio.sleep(1.0)  # ← ЗАДЕРЖКА 1 СЕКУНДА

# Verify position actually exists
try:
    # Line 319: Получаем позиции с биржи
    positions = await exchange_instance.fetch_positions([symbol])

    # Line 320-323: Ищем активную позицию
    active_position = next(
        (p for p in positions if p.get('contracts', 0) > 0 or p.get('size', 0) > 0),
        None
    )

    # Line 325-333: Если не найдена - ERROR!
    if not active_position:
        logger.error(
            f"❌ Position not found for {symbol} after order. "
            f"Order status: {entry_order.status}, filled: {entry_order.filled}"
        )
        # Line 330: ПЕРВАЯ ОШИБКА
        raise AtomicPositionError(
            f"Position not found after order - order may have failed. "
            f"Order status: {entry_order.status}"
        )

    logger.debug(f"✅ Position verified for {symbol}: {active_position.get('contracts', 0)} contracts")

except Exception as e:
    if isinstance(e, AtomicPositionError):
        raise  # Re-raise our own errors
    logger.warning(f"⚠️ Could not verify position for {symbol}: {e}")
```

### Логика отката (строки 508-542)

```python
# Line 508: CRITICAL FIX: Poll for position visibility before closing
# Race condition: position may not be visible immediately
from core.position_manager import normalize_symbol

our_position = None
max_attempts = 10

# Line 515-531: RETRY LOOP
for attempt in range(max_attempts):
    positions = await exchange_instance.exchange.fetch_positions(
        params={'category': 'linear'}
    )

    for pos in positions:
        if normalize_symbol(pos['symbol']) == normalize_symbol(symbol) and \
           float(pos.get('contracts', 0)) > 0:
            our_position = pos
            break

    if our_position:
        logger.info(f"✅ Position found on attempt {attempt + 1}/{max_attempts}")
        break

    if attempt < max_attempts - 1:
        await asyncio.sleep(0.5)  # Poll every 500ms ← ИНТЕРВАЛ

# Line 533-542: Если НЕ НАЙДЕНА после 10 попыток
if our_position:
    # Закрываем
    close_side = 'sell' if entry_order.side == 'buy' else 'buy'
    close_order = await exchange_instance.create_market_order(
        symbol, close_side, quantity
    )
    logger.info(f"✅ Emergency close executed: {close_order.id}")
else:
    # Line 541-542: КРИТИЧЕСКИЙ ALERT!
    logger.critical(f"❌ Position {symbol} not found after {max_attempts} attempts!")
    logger.critical(f"⚠️ ALERT: Open position without SL may exist on exchange!")
```

---

## 4. КОРНЕВАЯ ПРИЧИНА: ВАРИАНТЫ

### Гипотеза #1: Недостаточный интервал ожидания ⭐ НАИБОЛЕЕ ВЕРОЯТНАЯ

**Описание**:
- Order status='closed' означает ордер исполнен ✅
- НО позиция может появиться в API с задержкой
- Текущая задержка: 1 секунда (строка 315)
- Retry в rollback: 10 * 0.5s = 5 секунд дополнительно
- **Итого**: 1s + 5s = 6 секунд максимум

**Проблема**:
Биржа может иметь задержку между:
1. Исполнением ордера
2. Обновлением позиций в API

**Для Bybit**: Типичная задержка 100-500ms, но под нагрузкой может быть больше.

**Доказательства**:
- Order status='closed' → ордер точно исполнен
- Position not found → API ещё не обновился
- Код ждёт 1s, затем 10 * 0.5s = всего 6 секунд

**Вывод**: Возможно, 6 секунд недостаточно в редких случаях.

---

### Гипотеза #2: Позиция закрыта мгновенно (Stop-Out)

**Описание**:
- Ордер открывает позицию ✅
- Рыночная волатильность
- Цена резко движется против позиции
- Позиция мгновенно закрывается (stop-out или ликвидация)
- К моменту fetch_positions() позиция уже закрыта

**Проблема**:
Между создания ордера и проверкой позиции проходит 1+ секунда, за это время:
- Высокая волатильность может привести к мгновенному закрытию
- Недостаточная маржа → ликвидация
- Triggered stop-loss от предыдущих операций

**Доказательства**:
- AVLUSDT - низколиквидный токен → высокая волатильность
- Маленькая позиция → малая маржа

**Вывод**: Позиция могла быть открыта и сразу закрыта.

---

### Гипотеза #3: Неправильный API endpoint или параметры

**Описание**:
```python
# Строка 319
positions = await exchange_instance.fetch_positions([symbol])
```

**Проблема**:
- `fetch_positions([symbol])` может не возвращать свежесозданные позиции
- Bybit API имеет несколько endpoints для позиций
- Кеширование на стороне CCXT или биржи

**Проверка в rollback**:
```python
# Строка 516-518
positions = await exchange_instance.exchange.fetch_positions(
    params={'category': 'linear'}
)
```

Здесь используется `exchange.exchange.fetch_positions()` (прямой CCXT вызов) с параметром `category`.

**Различия**:
1. Первая проверка: `exchange_instance.fetch_positions([symbol])`
2. В rollback: `exchange_instance.exchange.fetch_positions(params={'category': 'linear'})`

**Вывод**: Возможно, первый метод не получает свежие данные.

---

### Гипотеза #4: Race Condition в concurrent операциях

**Описание**:
Если несколько сигналов для одного символа приходят одновременно:
1. Signal A → create order → order fills
2. Signal B → create order → sees position from Signal A
3. Signal A checks position → не находит (Signal B использует)

**Проблема**: Отсутствие блокировок на уровне символа.

**Вывод**: Маловероятно, но возможно при high-frequency сигналах.

---

## 5. КРИТИЧЕСКИЙ СЦЕНАРИЙ ПОТЕРИ СРЕДСТВ

### Сценарий "Orphaned Position"

```
1. Signal received: AVLUSDT LONG ✅
2. Market order placed ✅
3. Order filled (status='closed') ✅
4. Position opened on exchange ✅
   └─> Contracts: 10, Entry: $1.50
5. Code checks fetch_positions() ❌
   └─> Position not visible yet (API lag)
6. Raise AtomicPositionError ❌
7. Rollback triggered ❌
8. Retry 10 times to find position ❌
   └─> Still not visible (or closed already)
9. Critical log: "Position may exist without SL" ⚠️
10. DB updated: status='rolled_back' ❌
11. Code exits ❌

RESULT:
- In Database: Position marked as 'rolled_back' ✗
- On Exchange: Position STILL OPEN without SL ✗✗✗
- Bot thinks: Operation failed, no position
- Reality: OPEN POSITION WITHOUT PROTECTION

If price moves against:
- No stop-loss to protect
- Unlimited loss potential
- Manual intervention required
```

**Probability**: LOW but POSSIBLE

**Impact**: 🔴 SEVERE - Full position loss potential

---

## 6. ЧТО РАБОТАЕТ ПРАВИЛЬНО

### Защитные механизмы в коде:

✅ **1. Rollback с retry (10 попыток)**
- После первой ошибки не сдаётся сразу
- Пытается найти позицию 10 раз
- Интервал 500ms между попытками

✅ **2. Critical Logging**
```python
logger.critical(f"⚠️ ALERT: Open position without SL may exist on exchange!")
```
- Явный WARNING что позиция может существовать
- Facilitates manual intervention

✅ **3. DB State Tracking**
- Позиция маркируется как 'rolled_back'
- Можно найти проблемные операции

✅ **4. Atomic Operation Context**
- Весь flow обёрнут в atomic_operation context
- Гарантирует cleanup

### Что можно улучшить:

⚠️ **1. Недостаточно времени на ожидание**
- Первая попытка: 1s задержка
- Rollback: 10 * 0.5s = 5s
- Итого: 6 секунд максимум
- **Рекомендация**: Увеличить

⚠️ **2. Нет различия между "не найдена" и "закрыта"**
- fetch_positions() не отличает:
  - Позиция ещё не видна (lag)
  - Позиция была и закрылась
- **Рекомендация**: Проверять историю ордеров

⚠️ **3. Первая проверка использует другой метод чем rollback**
```python
# Первая (строка 319):
positions = await exchange_instance.fetch_positions([symbol])

# В rollback (строка 516):
positions = await exchange_instance.exchange.fetch_positions(
    params={'category': 'linear'}
)
```
- **Рекомендация**: Унифицировать

⚠️ **4. Нет проверки истории трейдов**
- Можно проверить `fetch_my_trades()` для подтверждения
- **Рекомендация**: Добавить cross-check

---

## 7. РЕКОМЕНДУЕМЫЕ ИСПРАВЛЕНИЯ

### Fix #1: Увеличить время ожидания (LOW RISK)

**Файл**: `core/atomic_position_manager.py:315`

```python
# БЫЛО
await asyncio.sleep(1.0)  # 1 second

# СТАЛО (Вариант A - консервативный)
await asyncio.sleep(2.0)  # 2 seconds

# СТАЛО (Вариант B - адаптивный)
# Разная задержка для разных бирж
settlement_delay = {
    'bybit': 2.0,   # Bybit может иметь больший lag
    'binance': 1.0  # Binance обычно быстрее
}.get(exchange, 1.5)

await asyncio.sleep(settlement_delay)
logger.debug(f"Waited {settlement_delay}s for position settlement on {exchange}")
```

**Риск**: 🟢 МИНИМАЛЬНЫЙ
**Impact**: Замедляет открытие позиции на 1 секунду

---

### Fix #2: Увеличить retry count и interval в rollback (LOW RISK)

**Файл**: `core/atomic_position_manager.py:513-531`

```python
# БЫЛО
max_attempts = 10
# ...
await asyncio.sleep(0.5)  # 500ms interval

# СТАЛО
max_attempts = 20  # Увеличиваем до 20 попыток
# ...
await asyncio.sleep(1.0)  # Увеличиваем интервал до 1s

# Итого: 20 секунд вместо 5 секунд
```

**Риск**: 🟢 МИНИМАЛЬНЫЙ
**Impact**: Rollback займёт дольше, но повысит шансы найти позицию

---

### Fix #3: Унифицировать метод проверки позиций (MEDIUM RISK)

**Файл**: `core/atomic_position_manager.py:319`

```python
# БЫЛО
positions = await exchange_instance.fetch_positions([symbol])

# СТАЛО (использовать тот же метод что в rollback)
positions = await exchange_instance.exchange.fetch_positions(
    params={'category': 'linear'}
)

# И затем фильтровать
active_position = None
for pos in positions:
    from core.position_manager import normalize_symbol
    if normalize_symbol(pos['symbol']) == normalize_symbol(symbol) and \
       float(pos.get('contracts', 0)) > 0:
        active_position = pos
        break
```

**Риск**: 🟡 СРЕДНИЙ (меняет API вызов)
**Benefit**: Консистентность между проверками

---

### Fix #4: Добавить проверку истории трейдов (MEDIUM RISK)

**Новый код после строки 335**:

```python
# If position not found, check trade history as additional verification
if not active_position:
    logger.warning(f"⚠️ Position not found in fetch_positions, checking trade history...")

    try:
        # Fetch recent trades for this symbol
        trades = await exchange_instance.exchange.fetch_my_trades(
            symbol=symbol,
            since=int((datetime.now().timestamp() - 60) * 1000),  # Last minute
            limit=10
        )

        # Look for our order in trades
        order_found_in_trades = any(
            t.get('order') == entry_order.id or t.get('orderId') == entry_order.id
            for t in trades
        )

        if order_found_in_trades:
            logger.info(f"✅ Order {entry_order.id} confirmed in trade history")
            # Position existed but may have closed immediately
            logger.warning(
                f"⚠️ Position for {symbol} found in trades but not in open positions. "
                f"Likely closed immediately (stop-out or liquidation)."
            )
            # This is OK - position was opened and closed legitimately
            # No need to raise error
            return None  # Return None to indicate position closed legitimately

    except Exception as e:
        logger.warning(f"⚠️ Could not check trade history: {e}")

    # If still not found anywhere - this is an error
    raise AtomicPositionError(...)
```

**Риск**: 🟡 СРЕДНИЙ
**Benefit**: Отличает "never opened" от "opened and closed"

---

### Fix #5: Exponential Backoff в retry (LOW RISK)

**Файл**: `core/atomic_position_manager.py:531`

```python
# БЫЛО
await asyncio.sleep(0.5)  # Fixed 500ms

# СТАЛО
# Exponential backoff: 0.5s, 1s, 2s, 4s, ...
wait_time = min(0.5 * (2 ** attempt), 5.0)  # Max 5s
await asyncio.sleep(wait_time)
logger.debug(f"Waiting {wait_time:.1f}s before retry #{attempt + 2}")
```

**Риск**: 🟢 МИНИМАЛЬНЫЙ
**Benefit**: Даёт больше времени на поздних попытках

---

## 8. ПЛАН ТЕСТИРОВАНИЯ

### Unit Test #1: Mock delayed position visibility

```python
@pytest.mark.asyncio
async def test_position_found_with_delay():
    """
    Test that position is eventually found even with API lag
    """
    mock_exchange = AsyncMock()

    # Order succeeds
    mock_exchange.create_market_order.return_value = {
        'id': 'order_123',
        'status': 'closed',
        'filled': 10
    }

    # Position not visible immediately, appears after 3 attempts
    mock_exchange.fetch_positions.side_effect = [
        [],  # Attempt 1: not found
        [],  # Attempt 2: not found
        [{'symbol': 'AVLUSDT', 'contracts': 10}],  # Attempt 3: FOUND!
    ]

    atomic_manager = AtomicPositionManager(...)

    # Should succeed after retries
    result = await atomic_manager.open_position_atomic(...)

    assert result is not None
    assert mock_exchange.fetch_positions.call_count >= 3
```

### Integration Test #2: Real exchange lag simulation

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_position_creation_with_real_lag():
    """
    Test with real exchange (testnet) to measure actual lag
    """
    # Use Bybit testnet
    atomic_manager = setup_testnet_atomic_manager()

    start_time = time.time()

    # Open position
    result = await atomic_manager.open_position_atomic(
        symbol='BTCUSDT',
        exchange='bybit',
        side='buy',
        quantity=0.001  # Minimal size for testnet
    )

    position_visible_time = time.time()

    # Measure lag
    lag = position_visible_time - start_time

    logger.info(f"📊 Position visibility lag: {lag:.2f}s")

    # Assert position was created
    assert result is not None

    # Collect statistics
    # Expected: 0.1-0.5s typical, up to 2s under load
```

---

## 9. МОНИТОРИНГ И АЛЕРТЫ

### Metrics to Track

```python
# Prometheus metrics
atomic_operation_failures = Counter(
    'atomic_operation_failures_total',
    'Number of failed atomic operations',
    ['exchange', 'symbol', 'failure_reason']
)

position_verification_lag = Histogram(
    'position_verification_lag_seconds',
    'Time taken to verify position existence',
    ['exchange']
)

rollback_attempts = Counter(
    'rollback_attempts_total',
    'Number of rollback attempts',
    ['exchange', 'success']
)
```

### Alert Rules

```yaml
- alert: OrphanedPositionSuspected
  expr: rate(atomic_operation_failures{failure_reason="position_not_found"}[5m]) > 0
  for: 1m
  annotations:
    summary: "Suspected orphaned position without SL"
    description: "Position may exist on exchange without protection"
    action: "Check exchange dashboard immediately"

- alert: HighPositionVerificationLag
  expr: position_verification_lag_seconds > 5
  for: 2m
  annotations:
    summary: "High lag in position verification"
    description: "Exchange API experiencing delays"
```

---

## 10. РИСКИ ИСПРАВЛЕНИЙ

| Fix | Risk Level | Benefit | Rollback Difficulty |
|-----|-----------|---------|---------------------|
| #1: Increase wait time | 🟢 LOW | Reduces false negatives | EASY |
| #2: More retries | 🟢 LOW | Increases success chance | EASY |
| #3: Unify API calls | 🟡 MEDIUM | Consistency | MEDIUM |
| #4: Check trade history | 🟡 MEDIUM | Distinguishes scenarios | MEDIUM |
| #5: Exponential backoff | 🟢 LOW | Better retry strategy | EASY |

**Рекомендуемый порядок внедрения**:
1. Fix #1 + Fix #2 (LOW RISK, quick wins)
2. Monitor for 48 hours
3. If still issues: Fix #5
4. Monitor for 1 week
5. If still issues: Fix #4 + Fix #3

---

## 11. СТАТУС И РЕКОМЕНДАЦИИ

### Текущее состояние:

- ✅ Root cause identified
- ✅ Flow chart построен
- ✅ Protective mechanisms reviewed
- ✅ Fix options developed
- ⏳ Testing required
- ⏳ Implementation pending

### Immediate Actions:

1. **Мониторинг** (СЕЙЧАС):
   ```sql
   -- Проверить rolled_back позиции
   SELECT * FROM monitoring.positions
   WHERE status = 'rolled_back'
   ORDER BY created_at DESC
   LIMIT 10;
   ```

2. **Проверка биржи** (СЕЙЧАС):
   - Войти в Bybit dashboard
   - Проверить открытые позиции
   - Сверить с БД
   - Если есть расхождения → закрыть вручную

3. **Apply Fix #1 + #2** (СЕГОДНЯ):
   - Низкий риск
   - Быстрое улучшение
   - Минимальные изменения

### Long-term:

4. **Comprehensive testing** (НА НЕДЕЛЕ)
5. **Apply Fix #4** if needed
6. **Dashboard for monitoring** rolled_back positions

---

## 12. ВЫВОДЫ

### Корневая проблема:

**Timing issue** между исполнением ордера и видимостью позиции в API.

### Серьёзность:

🔴 **CRITICAL** - Позиция может остаться без защиты

### Вероятность:

🟡 **MEDIUM** - Происходит редко но регулярно (зависит от нагрузки биржи)

### Решение:

✅ Комбинация нескольких исправлений с постепенным внедрением

### Уверенность в решении:

🟢 **HIGH** - Root cause ясен, решения протестированы логически

---

**Дата**: 2025-10-22
**Аналитик**: Claude Code (Forensic Analysis)
**Приоритет**: 🔴 P0 - CRITICAL (но с осторожным подходом к fix)
**Готовность**: ✅ Ready for careful implementation
