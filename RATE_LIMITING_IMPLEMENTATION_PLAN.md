# План внедрения Rate Limiting и Conditional Updates для Trailing Stop
## Критически важно: ТОЛЬКО ПЛАНИРОВАНИЕ - БЕЗ ИЗМЕНЕНИЙ КОДА

**Дата:** 2025-10-14
**Статус:** Ожидает одобрения
**Связанные файлы:**
- `protection/trailing_stop.py`
- `config/settings.py` (уже обновлен)

---

## 🎯 Цель

Внедрить rate limiting и conditional updates для обновлений SL в Trailing Stop, чтобы:
1. ✅ Предотвратить слишком частые API calls (min 60s между обновлениями)
2. ✅ Пропускать микро-изменения (min 0.1% улучшение)
3. ✅ Алертить при больших unprotected windows (> 500ms для Binance)

---

## 📋 Текущее состояние кода

### Проблема #1: Отсутствует rate limiting
**Файл:** `protection/trailing_stop.py:340-404`
**Метод:** `_update_trailing_stop()`

**Текущий код (строки 361-368):**
```python
if new_stop_price:
    old_stop = ts.current_stop_price
    ts.current_stop_price = new_stop_price
    ts.last_stop_update = datetime.now()
    ts.update_count += 1

    # Update stop order on exchange
    await self._update_stop_order(ts)  # <-- ВЫЗЫВАЕТСЯ ВСЕГДА БЕЗ ПРОВЕРОК!
```

**Проблема:**
- `_update_stop_order()` вызывается **СРАЗУ** после расчета `new_stop_price`
- **НЕТ проверки** времени последнего обновления
- **НЕТ проверки** минимального улучшения
- Может обновлять SL каждые 2-5 секунд при волатильности

**Последствия:**
- 10-20 API calls в минуту при высокой волатильности
- Для Binance: 10-20 "незащищенных окон" по 359ms = до 7 секунд БЕЗ защиты в минуту
- Риск rate limit от биржи

---

### Проблема #2: TrailingStopInstance не хранит нужные данные

**Файл:** `protection/trailing_stop.py:55-81`
**Класс:** `TrailingStopInstance`

**Текущие поля (строки 67-68):**
```python
current_stop_price: Optional[Decimal] = None
last_stop_update: Optional[datetime] = None  # <-- ЕСТЬ! Но НЕ используется для rate limiting
```

**Что отсутствует:**
- ❌ `last_sl_update_time` - время последнего **успешного** обновления на бирже
- ❌ `last_updated_sl_price` - последняя **успешно обновленная** цена SL

**Почему важно:**
- `last_stop_update` обновляется **ДО** вызова `_update_stop_order()`
- Если `_update_stop_order()` **УПАДЁТ**, мы потеряем информацию о реальном времени последнего обновления
- Нужно хранить время **ПОСЛЕ** успешного обновления

---

### Проблема #3: Нет alerting для больших unprotected windows

**Файл:** `protection/trailing_stop.py:549-619`
**Метод:** `_update_stop_order()`

**Текущий код (строки 570-595):**
```python
if result['success']:
    # Log success with metrics
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.TRAILING_STOP_SL_UPDATED,
            {
                'symbol': ts.symbol,
                'method': result['method'],
                'execution_time_ms': result['execution_time_ms'],
                'new_sl_price': float(ts.current_stop_price),
                'old_sl_price': result.get('old_sl_price'),
                'unprotected_window_ms': result.get('unprotected_window_ms', 0),  # <-- Логируем
                'side': ts.side,
                'update_count': ts.update_count
            },
            symbol=ts.symbol,
            exchange=self.exchange.name,
            severity='INFO'
        )
```

**Проблема:**
- `unprotected_window_ms` логируется в EventLogger
- **НЕТ проверки** порога из `config.trading.trailing_alert_if_unprotected_window_ms`
- **НЕТ алертов** если окно > 500ms (для Binance это проблема)

---

## 🔧 Решение: Детальный план изменений

### ═══════════════════════════════════════════════════════════════
### ШАГ 1: Обновить TrailingStopInstance (добавить поля)
### ═══════════════════════════════════════════════════════════════

**Файл:** `protection/trailing_stop.py`
**Место:** Класс `TrailingStopInstance` (строки 55-81)

#### 1.1 Добавить новые поля

**После строки 67 (`last_stop_update: Optional[datetime] = None`):**

```python
# SL Update tracking (for rate limiting)
last_sl_update_time: Optional[datetime] = None  # Last SUCCESSFUL SL update on exchange
last_updated_sl_price: Optional[Decimal] = None  # Last SUCCESSFULLY updated SL price on exchange
```

**Назначение:**
- `last_sl_update_time` - хранит время **ПОСЛЕ** успешного вызова `_update_stop_order()`
- `last_updated_sl_price` - хранит цену SL **ПОСЛЕ** успешного обновления на бирже
- Используются для rate limiting и conditional updates

**Важно:**
- ⚠️ `last_stop_update` (существующее) - обновляется **ДО** вызова API (строка 364)
- ⚠️ `last_sl_update_time` (новое) - обновляется **ПОСЛЕ** успешного API call
- Это **РАЗНЫЕ** вещи!

---

### ═══════════════════════════════════════════════════════════════
### ШАГ 2: Добавить метод _should_update_stop_loss()
### ═══════════════════════════════════════════════════════════════

**Файл:** `protection/trailing_stop.py`
**Место:** Добавить **ПЕРЕД** методом `_update_stop_order()` (перед строкой 549)

#### 2.1 Создать новый метод

**Новый метод (вставить после строки 548, перед `async def _update_stop_order()`):**

```python
def _should_update_stop_loss(self, ts: TrailingStopInstance,
                              new_stop_price: Decimal,
                              old_stop_price: Decimal) -> tuple[bool, Optional[str]]:
    """
    Check if SL should be updated based on rate limiting and conditional update rules

    Implements Freqtrade-inspired rate limiting with emergency override:
    Rule 0: Emergency override - ALWAYS update if improvement >= 1.0% (bypass all limits)
    Rule 1: Rate limiting - Min 60s interval between updates
    Rule 2: Conditional update - Min 0.1% improvement

    Args:
        ts: TrailingStopInstance
        new_stop_price: Proposed new SL price
        old_stop_price: Current SL price

    Returns:
        (should_update: bool, skip_reason: Optional[str])
        - (True, None) if update should proceed
        - (False, "reason") if update should be skipped
    """
    from config.settings import config

    # Calculate improvement first (needed for all rules)
    improvement_percent = abs(
        (new_stop_price - old_stop_price) / old_stop_price * 100
    )

    # Rule 0: EMERGENCY OVERRIDE - Always update if improvement is very large
    # This prevents losing profit during fast price movements
    EMERGENCY_THRESHOLD = 1.0  # 1.0% = 10x normal min_improvement

    if improvement_percent >= EMERGENCY_THRESHOLD:
        logger.info(
            f"⚡ {ts.symbol}: Emergency SL update due to large movement "
            f"({improvement_percent:.2f}% >= {EMERGENCY_THRESHOLD}%) - bypassing rate limit"
        )
        return (True, None)  # Skip all other checks - update immediately!

    # Rule 1: Rate limiting - check time since last SUCCESSFUL update
    if ts.last_sl_update_time:
        elapsed_seconds = (datetime.now() - ts.last_sl_update_time).total_seconds()
        min_interval = config.trading.trailing_min_update_interval_seconds

        if elapsed_seconds < min_interval:
            remaining = min_interval - elapsed_seconds
            return (False, f"rate_limit: {elapsed_seconds:.1f}s elapsed, need {min_interval}s (wait {remaining:.1f}s)")

    # Rule 2: Conditional update - check minimum improvement
    if ts.last_updated_sl_price:
        min_improvement = float(config.trading.trailing_min_improvement_percent)

        if improvement_percent < min_improvement:
            return (False, f"improvement_too_small: {improvement_percent:.3f}% < {min_improvement}%")

    # All checks passed
    return (True, None)
```

**Описание логики:**

**Rule 0: Emergency Override (НОВОЕ!)**
- **ВСЕГДА** обновляем если improvement >= 1.0%
- Bypass rate limiting и min improvement
- Защищает от потери прибыли при быстрых движениях цены
- Логирует: `⚡ Emergency SL update due to large movement (1.54% >= 1.0%)`

**Сценарий применения Rule 0:**
```
10:00:00 - SL updated to 1.450
10:00:15 - Price spike! New SL = 1.465 (improvement 1.03%)
          → EMERGENCY UPDATE (bypassing 60s rate limit) ✅
```

**Rule 1: Rate Limiting**
- Проверяет `ts.last_sl_update_time` (время последнего **УСПЕШНОГО** обновления)
- Если прошло < 60s → SKIP update (unless Rule 0 triggered)
- Возвращает `(False, "rate_limit: 35.2s elapsed, need 60s (wait 24.8s)")`

**Rule 2: Conditional Update (Min Improvement)**
- Проверяет `ts.last_updated_sl_price` (последняя **УСПЕШНО** обновленная цена)
- Рассчитывает improvement_percent
- Если improvement < 0.1% → SKIP update
- Возвращает `(False, "improvement_too_small: 0.05% < 0.1%")`

**Return values:**
- `(True, None)` - обновление разрешено
- `(False, "reason")` - обновление пропущено, логируем причину

**Decision tree:**
```
improvement >= 1.0%?
  YES → UPDATE immediately (Rule 0) ⚡
  NO  → elapsed < 60s?
          YES → SKIP (Rule 1) ⏭️
          NO  → improvement < 0.1%?
                  YES → SKIP (Rule 2) ⏭️
                  NO  → UPDATE (all checks passed) ✅
```

---

### ═══════════════════════════════════════════════════════════════
### ШАГ 3: Обновить метод _update_trailing_stop()
### ═══════════════════════════════════════════════════════════════

**Файл:** `protection/trailing_stop.py`
**Метод:** `_update_trailing_stop()` (строки 340-404)

#### 3.1 Добавить проверку ПЕРЕД обновлением

**Место:** После строки 365 (`ts.update_count += 1`), **ПЕРЕД** строкой 367 (`await self._update_stop_order(ts)`)

**Новый код (вставить между строками 365 и 367):**

```python
            ts.update_count += 1

            # NEW: Check rate limiting and conditional update rules
            should_update, skip_reason = self._should_update_stop_loss(ts, new_stop_price, old_stop)

            if not should_update:
                # Skip update - log reason
                logger.debug(
                    f"⏭️  {ts.symbol}: SL update SKIPPED - {skip_reason} "
                    f"(new_stop={new_stop_price:.4f})"
                )

                # Log skip event (optional - для статистики)
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_UPDATED,  # Same event type but with skip_reason
                        {
                            'symbol': ts.symbol,
                            'action': 'skipped',
                            'skip_reason': skip_reason,
                            'proposed_new_stop': float(new_stop_price),
                            'current_stop': float(old_stop),
                            'update_count': ts.update_count
                        },
                        symbol=ts.symbol,
                        exchange=self.exchange_name,
                        severity='DEBUG'
                    )

                # IMPORTANT: Revert changes since we're not updating
                ts.current_stop_price = old_stop  # Restore old price
                ts.last_stop_update = None  # Clear update timestamp
                ts.update_count -= 1  # Revert counter

                return None  # Return None to indicate no action taken

            # Update stop order on exchange
            await self._update_stop_order(ts)
```

**Что делает:**

1. **Проверка через `_should_update_stop_loss()`**
   - Если `should_update=False` → пропускаем обновление

2. **Логирование SKIP**
   - DEBUG лог: `⏭️  BTCUSDT: SL update SKIPPED - rate_limit: 35.2s elapsed, need 60s`
   - EventLogger: сохраняем событие с `action='skipped'` и `skip_reason`

3. **Revert изменений**
   - **КРИТИЧЕСКИ ВАЖНО!** Откатываем изменения, которые уже были сделаны:
     - `ts.current_stop_price = old_stop` (restore)
     - `ts.last_stop_update = None` (clear)
     - `ts.update_count -= 1` (revert)
   - Это гарантирует, что состояние `ts` не изменилось

4. **Return None**
   - Возвращаем `None` чтобы показать что никаких действий не было

#### 3.2 ВАЖНО: Почему revert?

**Проблема:**
```python
# Строки 361-365 - УЖЕ ИЗМЕНИЛИ состояние ts
old_stop = ts.current_stop_price
ts.current_stop_price = new_stop_price  # <-- ИЗМЕНЕНО
ts.last_stop_update = datetime.now()    # <-- ИЗМЕНЕНО
ts.update_count += 1                    # <-- ИЗМЕНЕНО
```

Если мы **НЕ** откатим изменения при SKIP:
- `ts.current_stop_price` будет содержать "новую" цену, которая **НЕ** была обновлена на бирже
- На следующей итерации расчет improvement будет **НЕПРАВИЛЬНЫМ**
- Возникнет рассинхронизация между локальным состоянием и биржей

**Решение:**
- При SKIP откатываем **ВСЕ** изменения
- Оставляем `ts` в том же состоянии что было до вызова

---

### ═══════════════════════════════════════════════════════════════
### ШАГ 4: Обновить метод _update_stop_order()
### ═══════════════════════════════════════════════════════════════

**Файл:** `protection/trailing_stop.py`
**Метод:** `_update_stop_order()` (строки 549-619)

#### 4.1 Обновить `ts` после успешного обновления

**Место:** После строки 589 (внутри `if result['success']:` блока), **ПЕРЕД** строкой 591 (`logger.info(...)`)

**Новый код (вставить между строками 589 и 591):**

```python
                )

                # NEW: Update tracking fields after SUCCESSFUL update
                ts.last_sl_update_time = datetime.now()  # Record time of successful update
                ts.last_updated_sl_price = ts.current_stop_price  # Record successfully updated price

                logger.info(
```

**Что делает:**
- Сохраняет время **ПОСЛЕ** успешного обновления на бирже
- Сохраняет цену SL которая **РЕАЛЬНО** была установлена
- Эти данные используются в `_should_update_stop_loss()` для rate limiting

#### 4.2 Добавить alerting для больших unprotected windows

**Место:** После строки 589, **ПОСЛЕ** обновления tracking fields

**Новый код (вставить после обновления tracking fields):**

```python
                ts.last_sl_update_time = datetime.now()
                ts.last_updated_sl_price = ts.current_stop_price

                # NEW: Alert if unprotected window is too large (Binance)
                from config.settings import config
                unprotected_window_ms = result.get('unprotected_window_ms', 0)
                alert_threshold = config.trading.trailing_alert_if_unprotected_window_ms

                if unprotected_window_ms > alert_threshold:
                    logger.warning(
                        f"⚠️  {ts.symbol}: Large unprotected window detected! "
                        f"{unprotected_window_ms:.1f}ms > {alert_threshold}ms threshold "
                        f"(exchange: {self.exchange.name}, method: {result['method']})"
                    )

                    # Log high-severity alert
                    if event_logger:
                        await event_logger.log_event(
                            EventType.WARNING_RAISED,
                            {
                                'symbol': ts.symbol,
                                'warning_type': 'large_unprotected_window',
                                'unprotected_window_ms': unprotected_window_ms,
                                'threshold_ms': alert_threshold,
                                'exchange': self.exchange.name,
                                'method': result['method']
                            },
                            symbol=ts.symbol,
                            exchange=self.exchange.name,
                            severity='WARNING'
                        )

                logger.info(
```

**Что делает:**

1. **Проверяет unprotected_window_ms**
   - Получает из `result` (возвращается из `update_stop_loss_atomic()`)
   - Для Bybit: обычно 0ms (атомарная операция)
   - Для Binance: 200-600ms (cancel+create)

2. **Сравнивает с порогом**
   - Порог из `config.trading.trailing_alert_if_unprotected_window_ms` (по умолчанию 500ms)
   - Если > 500ms → алерт

3. **Логирует WARNING**
   - logger.warning: `⚠️  BTCUSDT: Large unprotected window detected! 650.3ms > 500ms`
   - EventLogger: `WARNING_RAISED` с деталями

**Зачем это важно:**
- Для Binance cancel+create окно может быть > 500ms
- Это значит что позиция БЕЗ защиты > 0.5 секунды
- При flash crash это может быть критично
- Алерт помогает понять когда это происходит

---

### ═══════════════════════════════════════════════════════════════
### ШАГ 5: Добавить конфигурацию в .env (опционально)
### ═══════════════════════════════════════════════════════════════

**Файл:** `.env`

#### 5.1 Добавить новые параметры (если нужно переопределить дефолты)

**Добавить в конец `.env`:**

```bash
# Trailing Stop SL Update Rate Limiting (Freqtrade-inspired)
TRAILING_MIN_UPDATE_INTERVAL_SECONDS=60  # Min 60s between SL updates
TRAILING_MIN_IMPROVEMENT_PERCENT=0.1     # Update only if improvement >= 0.1%
TRAILING_ALERT_IF_UNPROTECTED_WINDOW_MS=500  # Alert if unprotected window > 500ms
```

**ВАЖНО:**
- Это **ОПЦИОНАЛЬНО** - дефолтные значения уже прописаны в `config/settings.py`
- Добавлять в `.env` только если нужно изменить дефолты
- Например, для более агрессивного trailing можно установить `TRAILING_MIN_UPDATE_INTERVAL_SECONDS=30`

---

## 📊 Ожидаемый результат

### До изменений (текущее поведение):

```
10:00:00 - Price: 1.500 → SL updated to 1.450 (API call)
10:00:15 - Price: 1.505 → SL updated to 1.455 (API call)
10:00:30 - Price: 1.510 → SL updated to 1.460 (API call)
10:00:45 - Price: 1.515 → SL updated to 1.465 (API call)
10:01:00 - Price: 1.520 → SL updated to 1.470 (API call)

Итого: 5 API calls за 1 минуту
Для Binance: 5 × 359ms = 1.795 секунды БЕЗ защиты
```

### После изменений (с rate limiting + emergency override):

**Сценарий #1: Нормальный рост (медленный):**
```
10:00:00 - Price: 1.500 → SL updated to 1.450 (API call ✅)
10:00:15 - Price: 1.505 → SKIPPED: rate_limit (15s < 60s, improvement 0.34%)
10:00:30 - Price: 1.510 → SKIPPED: rate_limit (30s < 60s, improvement 0.69%)
10:00:45 - Price: 1.515 → SKIPPED: rate_limit (45s < 60s, improvement 1.03%)
10:01:00 - Price: 1.520 → SL updated to 1.470 (API call ✅, 60s passed)

Итого: 2 API calls за 1 минуту (уменьшение на 60%)
Для Binance: 2 × 359ms = 718ms БЕЗ защиты (уменьшение на 60%)
```

**Сценарий #2: Быстрый рост (emergency override):**
```
10:00:00 - Price: 1.500 → SL updated to 1.450 (API call ✅)
10:00:15 - Price: 1.505 → SKIPPED: rate_limit (15s < 60s, improvement 0.34%)
10:00:30 - Price: 1.510 → SKIPPED: rate_limit (30s < 60s, improvement 0.69%)
10:00:35 - Price: 1.530 → ⚡ EMERGENCY UPDATE! (improvement 1.38% >= 1.0%) ✅
                          SL updated to 1.480 (bypassing rate limit!)
10:00:50 - Price: 1.540 → SKIPPED: rate_limit (15s since emergency update)
10:01:35 - Price: 1.545 → SL updated to 1.495 (API call ✅, 60s passed)

Итого: 3 API calls за 1 минуту (1 normal + 1 emergency + 1 normal)
Emergency override сработал → не потеряли прибыль! ✅
```

### Метрики улучшения:

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| **API calls/min** | 5-10 | 1-2 | **80%** ↓ |
| **Unprotected windows (Binance)** | 1.8s-3.6s/min | 0.4s-0.7s/min | **80%** ↓ |
| **Risk of rate limit** | Высокий | Низкий | ✅ |
| **Race condition duration** | Высокая | Минимальная | ✅ |

---

## ⚠️ Риски и ограничения

### Риск #1: Delayed SL updates при быстром росте цены ✅ РЕШЕНО!
**Сценарий:**
- Цена резко растет: 1.50 → 1.55 → 1.60 за 30 секунд
- SL обновлен в 10:00:00 на 1.45
- Следующее обновление только в 10:01:00 (rate limit)
- За это время цена могла подняться значительно выше

**Решение - Emergency Override (Rule 0):**
- ✅ **Если improvement >= 1.0% → BYPASS rate limit!**
- ✅ При резком росте цены SL обновится немедленно
- ✅ Защищает от потери прибыли при быстрых движениях
- ✅ Emergency threshold настраивается (hardcoded 1.0% или через config)

**Пример работы:**
```
10:00:00 - SL = 1.450
10:00:15 - Price spike → SL should be 1.465 (improvement 1.03%)
          ⚡ EMERGENCY OVERRIDE → SL updated immediately (bypass 60s limit)
```

### Риск #2: Rate limit может быть слишком консервативным ✅ РЕШЕНО!
**Сценарий:**
- Высоковолатильная монета (PEPE, SHIB)
- Цена меняется на ±5% каждые 10 секунд
- Rate limit 60s может быть слишком большим

**Решение - Emergency Override (Rule 0):**
- ✅ **Emergency threshold = 1.0% автоматически обрабатывает высокую волатильность**
- ✅ При движении > 1.0% SL обновится независимо от rate limit
- ✅ Для низковолатильных монет rate limit работает → экономим API calls
- ✅ Для высоковолатильных монет emergency override срабатывает → не теряем прибыль

### Риск #3: Revert логика может вызвать баги
**Сценарий:**
- При SKIP мы откатываем `ts.current_stop_price`, `ts.last_stop_update`, `ts.update_count`
- Если где-то еще в коде ссылка на эти поля, может возникнуть рассинхронизация

**Решение:**
- ✅ Проверил код - эти поля используются **ТОЛЬКО** внутри `_update_trailing_stop()`
- ✅ После `return None` никаких дальнейших действий с `ts` не происходит
- ✅ Следующая итерация получит правильное состояние

---

## ✅ Критерии успеха

### Функциональные критерии:
1. ✅ SL обновляется не чаще чем раз в 60s (rate limiting работает)
2. ✅ Emergency override срабатывает при improvement >= 1.0% (bypass rate limit)
3. ✅ SL обновляется только при улучшении >= 0.1% (conditional update работает)
4. ✅ Алерты генерируются при unprotected_window > 500ms
4. ✅ Логи содержат информацию о пропущенных обновлениях (SKIP events)
5. ✅ EventLogger содержит метрики rate limiting

### Метрики производительности:
1. ✅ API calls снижены на 60-80%
2. ✅ Unprotected windows (Binance) снижены на 60-80%
3. ✅ Нет ошибок rate limit от бирж
4. ✅ Trailing stop продолжает работать корректно

### Безопасность:
1. ✅ Нет рассинхронизации между локальным состоянием и биржей
2. ✅ Revert логика работает корректно при SKIP
3. ✅ Нет потери защиты (SL всегда на бирже)

---

## 🔍 План тестирования

### Test #1: Rate limiting работает
**Сценарий:**
1. Открыть позицию на testnet
2. Активировать trailing stop
3. Симулировать быстрый рост цены (вручную изменить `ts.current_price`)
4. Проверить логи - должны быть SKIP events с "rate_limit"

**Ожидаемый результат:**
```
10:00:00 - ✅ SL updated to 1.450 (execution: 343ms)
10:00:15 - ⏭️  SL update SKIPPED - rate_limit: 15.0s elapsed, need 60s
10:00:30 - ⏭️  SL update SKIPPED - rate_limit: 30.0s elapsed, need 60s
10:01:00 - ✅ SL updated to 1.470 (execution: 337ms)
```

### Test #2: Min improvement работает
**Сценарий:**
1. После успешного обновления SL на 1.450
2. Цена меняется на 0.05% (микро-изменение)
3. Trailing stop пытается обновить SL на 1.45025 (improvement = 0.05%)
4. Проверить логи - должен быть SKIP event с "improvement_too_small"

**Ожидаемый результат:**
```
⏭️  SL update SKIPPED - improvement_too_small: 0.050% < 0.1%
```

### Test #3: Alerting работает (Binance)
**Сценарий:**
1. Открыть позицию на Binance testnet
2. Обновить SL через optimized cancel+create
3. Если unprotected_window > 500ms → должен быть WARNING

**Ожидаемый результат:**
```
⚠️  BTCUSDT: Large unprotected window detected! 650.3ms > 500ms threshold
```

### Test #4: Emergency override работает (НОВЫЙ!)
**Сценарий:**
1. Открыть позицию на testnet
2. Обновить SL в 10:00:00
3. Через 15s (10:00:15) симулировать резкий рост цены (improvement > 1.0%)
4. Проверить логи - должен быть ⚡ emergency override (НЕ rate_limit SKIP)

**Ожидаемый результат:**
```
10:00:00 - ✅ SL updated to 1.450 (execution: 343ms)
10:00:15 - ⚡ Emergency SL update due to large movement (1.38% >= 1.0%) - bypassing rate limit
          ✅ SL updated to 1.470 (execution: 337ms)
```

**Критерии успеха:**
- ✅ Rate limit (60s) был bypassed
- ✅ SL обновлен через 15s (не 60s)
- ✅ Лог содержит "Emergency SL update"
- ✅ Improvement >= 1.0%

### Test #5: Revert логика работает
**Сценарий:**
1. Пропустить обновление через rate_limit
2. Проверить `ts.current_stop_price` после SKIP
3. Должен быть равен **старой** цене (до попытки обновления)

**Ожидаемый результат:**
```python
# До попытки обновления
ts.current_stop_price = 1.450

# Попытка обновления (SKIPPED)
new_stop_price = 1.455  # Calculated but skipped

# После SKIP (revert)
ts.current_stop_price = 1.450  # ✅ Restored
```

---

## 📝 Чеклист внедрения

### Шаг 1: Обновить TrailingStopInstance
- [ ] Добавить `last_sl_update_time: Optional[datetime] = None`
- [ ] Добавить `last_updated_sl_price: Optional[Decimal] = None`
- [ ] Проверить что поля инициализируются как `None`

### Шаг 2: Добавить _should_update_stop_loss()
- [ ] Создать метод перед `_update_stop_order()` (строка 549)
- [ ] Реализовать Rule 0: Emergency override (improvement >= 1.0%)
- [ ] Реализовать Rule 1: Rate limiting check (60s interval)
- [ ] Реализовать Rule 2: Min improvement check (0.1%)
- [ ] Вернуть `(bool, Optional[str])` tuple
- [ ] Добавить импорт `from config.settings import config`

### Шаг 3: Обновить _update_trailing_stop()
- [ ] Добавить вызов `_should_update_stop_loss()` после строки 365
- [ ] Реализовать SKIP логику (logger.debug, EventLogger)
- [ ] Реализовать revert логику (restore old values)
- [ ] Вернуть `None` при SKIP

### Шаг 4: Обновить _update_stop_order()
- [ ] Обновить `ts.last_sl_update_time` после успешного обновления
- [ ] Обновить `ts.last_updated_sl_price` после успешного обновления
- [ ] Добавить alerting для больших unprotected windows
- [ ] Залогировать WARNING при превышении порога

### Шаг 5: Тестирование
- [ ] Test #1: Rate limiting работает
- [ ] Test #2: Min improvement работает
- [ ] Test #3: Alerting работает (Binance unprotected window)
- [ ] Test #4: Emergency override работает (НОВЫЙ!)
- [ ] Test #5: Revert логика работает
- [ ] 24-hour monitoring на testnet

---

## 🚀 Финальные рекомендации

### Порядок внедрения:
1. ✅ **Шаг 1-4**: Внести изменения в код (строго по плану)
2. ✅ **Шаг 5**: Тестирование на testnet (4 теста)
3. ✅ **Monitoring**: 24-hour мониторинг на testnet
4. ✅ **Production**: Deploy если все тесты пройдены

### Rollback план:
Если что-то пошло не так:
1. Git revert изменений в `trailing_stop.py`
2. Убрать параметры из `.env` (если добавляли)
3. Restart бота
4. Trailing stop вернётся к работе без rate limiting

### Мониторинг после deploy:
```sql
-- Проверить эффективность rate limiting
SELECT
    DATE(created_at) as date,
    data->>'action' as action,
    COUNT(*) as count
FROM monitoring.events
WHERE event_type = 'trailing_stop_updated'
  AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY date, action
ORDER BY date DESC;

-- Результат должен показать:
-- action='updated': 50-100 (реальные обновления)
-- action='skipped': 200-500 (пропущенные обновления)
-- Ratio: 1:4 или 1:5 (80% пропущено = эффективность!)
```

---

## ✅ ЗАКЛЮЧЕНИЕ

**План готов к внедрению! (Обновлен с Emergency Override)**

**Что улучшится:**
- ✅ API calls снизятся на 60-80%
- ✅ Unprotected windows (Binance) снизятся на 60-80%
- ✅ **Emergency override защитит от потери прибыли при резких движениях**
- ✅ Alerting для больших окон (> 500ms)
- ✅ Статистика rate limiting в EventLogger

**Ключевая фича - Emergency Override (Rule 0):**
- ⚡ Если improvement >= 1.0% → **BYPASS всех лимитов**
- ⚡ Защита от проблемы "отставания SL" при быстрых движениях цены
- ⚡ Автоматическая адаптация к волатильности монеты
- ⚡ Best of both worlds: rate limiting + защита при резких скачках

**Риски:**
- ⚠️ Минимальные - все изменения локальны в `trailing_stop.py`
- ⚠️ Revert логика требует тщательной проверки
- ⚠️ Emergency override протестировать на быстрых движениях
- ⚠️ Тестирование на testnet обязательно

**Почему Вариант 3 оптимален:**
1. ✅ Решает проблему "отставания SL" при rate limiting
2. ✅ Сохраняет rate limiting для микро-изменений (экономия API)
3. ✅ Не требует настройки - работает out-of-the-box
4. ✅ Адаптивный - подстраивается под волатильность
5. ✅ Простая логика - легко тестировать и дебажить

**Следующий шаг:**
- ✅ Получить одобрение обновленного плана
- ✅ Приступить к внедрению Шаг 1-4
- ✅ Провести 5 тестов (включая Test #4 для emergency override)

**ОБНОВЛЕННЫЙ ПЛАН ГОТОВ - ОЖИДАЮ ОДОБРЕНИЯ!**
