# ПОДРОБНЫЙ ПЛАН ВНЕДРЕНИЯ: Health Check Improvements

**Дата создания:** 2025-11-10
**Статус:** Ready for Implementation
**Приоритет:** CRITICAL
**Estimated Time:** 4-6 hours

---

## 📋 EXECUTIVE SUMMARY

**Проблема:** Текущий health check не обнаруживает silent fails (subscription активна, но данные не приходят)

**Решение:** 4 улучшения для обнаружения и автоматического восстановления silent fails

**Ожидаемый результат:**
- Silent fail detection: 0s → 60s (вместо никогда)
- Автоматическое восстановление
- Нет блокировки event loop
- Защита от frozen WebSocket

---

## 🎯 УЛУЧШЕНИЯ

### УЛУЧШЕНИЕ #1: Timestamp Tracking для Data Freshness
**Приоритет:** CRITICAL
**Сложность:** LOW
**Risk Level:** 🟢 LOW

### УЛУЧШЕНИЕ #2: Enhanced Health Check с проверкой данных
**Приоритет:** CRITICAL
**Сложность:** MEDIUM
**Risk Level:** 🟡 MEDIUM

### УЛУЧШЕНИЕ #3: Non-blocking Warmup
**Приоритет:** HIGH
**Сложность:** MEDIUM
**Risk Level:** 🟢 LOW

### УЛУЧШЕНИЕ #4: WebSocket Heartbeat Monitoring
**Приоритет:** MEDIUM
**Сложность:** LOW
**Risk Level:** 🟢 LOW

---

## 🔍 ФАЗА 0: PRE-IMPLEMENTATION ANALYSIS

### 0.1. Анализ текущего состояния

**Текущие структуры данных:**
```python
# websocket/binance_hybrid_stream.py:82
self.mark_prices: Dict[str, str] = {}  # {symbol: latest_mark_price}
```

**Проблема:** Нет timestamp! Не можем определить когда были последние данные.

**Текущие использования mark_prices:**
- Line 533: `'mark_price': self.mark_prices.get(symbol, '0')`
- Line 656: `self.mark_prices[symbol] = mark_price`
- Line 795: `self.mark_prices.clear()`
- Line 888: `initial_count = len(self.mark_prices.get(symbol, ""))`
- Line 958: `if symbol in self.mark_prices`
- Line 1073: `'mark_prices': list(self.mark_prices.keys())`

**Анализ безопасности:** Все использования работают с ключом symbol → безопасно добавить новый ключ `{symbol}_timestamp`

---

## 📦 ФАЗА 1: УЛУЧШЕНИЕ #1 - Timestamp Tracking

### 1.1. Обоснование

**Проблема:**
```python
# Текущий код
self.mark_prices['BTCUSDT'] = '50000.00'  # Когда получили? Неизвестно!
```

**Решение:**
```python
# Новый код
self.mark_prices['BTCUSDT'] = '50000.00'
self.mark_prices['BTCUSDT_timestamp'] = time.time()  # Знаем КОГДА!
```

**Зачем:**
- Обнаружение silent fails (нет данных >60s)
- Метрики latency
- Debugging

### 1.2. Изменения в коде

#### Изменение 1.1: Добавить timestamp tracking в _on_mark_price_update

**Файл:** `websocket/binance_hybrid_stream.py`
**Строки:** 647-697
**Действие:** MODIFY

**ТЕКУЩИЙ КОД:**
```python
async def _on_mark_price_update(self, data: Dict):
    """Handle mark price update"""
    symbol = data.get('s')
    mark_price = data.get('p')

    if not symbol or not mark_price:
        return

    # Update mark price cache
    self.mark_prices[symbol] = mark_price  # ← Line 656

    # If we have position data, emit combined event
    if symbol in self.positions:
        # ... rest of the code
```

**НОВЫЙ КОД:**
```python
async def _on_mark_price_update(self, data: Dict):
    """Handle mark price update"""
    symbol = data.get('s')
    mark_price = data.get('p')

    if not symbol or not mark_price:
        return

    # Update mark price cache WITH timestamp
    self.mark_prices[symbol] = mark_price
    self.mark_prices[f"{symbol}_timestamp"] = asyncio.get_event_loop().time()  # ← NEW!

    # If we have position data, emit combined event
    if symbol in self.positions:
        # ... rest of the code
```

**Обоснование:**
- ✅ Минимальное изменение (1 строка)
- ✅ Не меняет существующую логику
- ✅ asyncio.get_event_loop().time() - монотонные часы, защита от system time changes
- ✅ Ключ `{symbol}_timestamp` не конфликтует с symbol keys

**Тест безопасности:**
```python
# Проверка что не ломаем существующий код
assert 'BTCUSDT' in mark_prices  # ✅ Работает
assert 'BTCUSDT_timestamp' in mark_prices  # ✅ Новый ключ
assert mark_prices['BTCUSDT'] == '50000.00'  # ✅ Данные не изменились
```

#### Изменение 1.2: Добавить helper method для проверки freshness

**Файл:** `websocket/binance_hybrid_stream.py`
**Строка:** После line 1009 (после _verify_subscriptions_health)
**Действие:** INSERT NEW METHOD

**НОВЫЙ МЕТОД:**
```python
def _get_data_age(self, symbol: str) -> float:
    """
    Get age of last data update for symbol

    Args:
        symbol: Symbol to check

    Returns:
        float: Seconds since last update, or float('inf') if no data
    """
    timestamp_key = f"{symbol}_timestamp"

    if timestamp_key not in self.mark_prices:
        return float('inf')  # Never received data

    now = asyncio.get_event_loop().time()
    last_update = self.mark_prices[timestamp_key]

    return now - last_update
```

**Обоснование:**
- ✅ Encapsulation: логика проверки в одном месте
- ✅ Возвращает float('inf') если данных нет → легко проверять `if age > threshold`
- ✅ Используется в Улучшении #2

### 1.3. Тестирование Фазы 1

**Тест 1.1: Timestamp Recording**
```python
# tests/test_health_check_improvements.py
async def test_timestamp_recording():
    """Test that timestamps are recorded on data receipt"""
    # Setup
    stream = BinanceHybridStream(...)

    # Simulate mark price update
    await stream._on_mark_price_update({
        's': 'BTCUSDT',
        'p': '50000.00'
    })

    # Verify
    assert 'BTCUSDT' in stream.mark_prices
    assert 'BTCUSDT_timestamp' in stream.mark_prices
    assert isinstance(stream.mark_prices['BTCUSDT_timestamp'], float)

    # Verify age
    age = stream._get_data_age('BTCUSDT')
    assert age < 1.0  # Less than 1 second old
```

**Тест 1.2: Data Age Calculation**
```python
async def test_data_age_calculation():
    """Test data age calculation"""
    stream = BinanceHybridStream(...)

    # Symbol with data
    stream.mark_prices['ETHUSDT'] = '3000.00'
    stream.mark_prices['ETHUSDT_timestamp'] = asyncio.get_event_loop().time() - 30.0

    age = stream._get_data_age('ETHUSDT')
    assert 29.0 < age < 31.0  # ~30 seconds

    # Symbol without data
    age_no_data = stream._get_data_age('UNKNOWN')
    assert age_no_data == float('inf')
```

**Тест 1.3: Backward Compatibility**
```python
async def test_backward_compatibility():
    """Test that existing code still works"""
    stream = BinanceHybridStream(...)

    # Old usage patterns should still work
    stream.mark_prices['BTCUSDT'] = '50000.00'

    # These should NOT break
    assert 'BTCUSDT' in stream.mark_prices  # ✅
    price = stream.mark_prices.get('BTCUSDT', '0')  # ✅
    symbols = [k for k in stream.mark_prices.keys() if not k.endswith('_timestamp')]  # ✅
```

---

## 📦 ФАЗА 2: УЛУЧШЕНИЕ #2 - Enhanced Health Check

### 2.1. Обоснование

**Текущая проблема:**
```python
# binance_hybrid_stream.py:991-1009
async def _verify_subscriptions_health(self):
    # Проверяет только PRESENCE
    all_subscriptions = self.subscribed_symbols.union(self.pending_subscriptions)
    missing_subscriptions = set(self.positions.keys()) - all_subscriptions

    if missing_subscriptions:
        # Переподписываемся
```

**Проблема:** НЕ обнаруживает:
```
BTCUSDT in subscribed_symbols = True  ← Формально подписан
BTCUSDT получает данные = False       ← Реально не работает!
```

### 2.2. Изменения в коде

#### Изменение 2.1: Полная замена _verify_subscriptions_health

**Файл:** `websocket/binance_hybrid_stream.py`
**Строки:** 991-1009
**Действие:** REPLACE

**ТЕКУЩИЙ КОД:**
```python
async def _verify_subscriptions_health(self):
    """Verify all open positions have active or pending subscriptions"""
    if not self.positions:
        return

    # Check all open positions
    all_subscriptions = self.subscribed_symbols.union(self.pending_subscriptions)
    missing_subscriptions = set(self.positions.keys()) - all_subscriptions

    if missing_subscriptions:
        logger.warning(f"⚠️ [MARK] Found {len(missing_subscriptions)} positions without subscriptions: {missing_subscriptions}")

        # Request subscriptions for missing symbols
        for symbol in missing_subscriptions:
            logger.info(f"🔄 [MARK] Resubscribing to {symbol} (subscription lost)")
            await self._request_mark_subscription(symbol, subscribe=True)
    else:
        logger.debug(f"✅ [MARK] Subscription health OK: {len(self.positions)} positions, "
                    f"{len(self.subscribed_symbols)} subscribed, {len(self.pending_subscriptions)} pending")
```

**НОВЫЙ КОД:**
```python
async def _verify_subscriptions_health(self):
    """
    Enhanced subscription health check

    Verifies:
    1. All positions have subscriptions (presence check)
    2. All subscriptions receive ACTUAL data (freshness check)

    Auto-recovery:
    - Missing subscriptions → Subscribe
    - Silent fails (no data) → Resubscribe
    """
    if not self.positions:
        return

    # STEP 1: Check subscription PRESENCE
    all_subscriptions = self.subscribed_symbols.union(self.pending_subscriptions)
    missing_subscriptions = set(self.positions.keys()) - all_subscriptions

    # STEP 2: Check data FRESHNESS for subscribed symbols
    stale_subscriptions = set()

    for symbol in self.positions.keys():
        # Skip if already marked as missing
        if symbol in missing_subscriptions:
            continue

        # Check data age
        data_age = self._get_data_age(symbol)

        # Threshold: 60 seconds without data = silent fail
        if data_age > 60.0:
            stale_subscriptions.add(symbol)
            logger.warning(
                f"⚠️ [MARK] SILENT FAIL detected: {symbol} - "
                f"no data for {int(data_age)}s (subscribed={symbol in self.subscribed_symbols})"
            )

    # STEP 3: Recovery actions
    total_issues = len(missing_subscriptions) + len(stale_subscriptions)

    if total_issues > 0:
        logger.warning(
            f"⚠️ [MARK] Health check found {total_issues} issues: "
            f"{len(missing_subscriptions)} missing, {len(stale_subscriptions)} stale"
        )

        # Recover missing subscriptions
        for symbol in missing_subscriptions:
            logger.info(f"🔄 [MARK] Subscribing to {symbol} (missing)")
            await self._request_mark_subscription(symbol, subscribe=True)

        # Recover stale subscriptions
        for symbol in stale_subscriptions:
            # Remove from subscribed (it's broken!)
            self.subscribed_symbols.discard(symbol)

            logger.info(f"🔄 [MARK] Resubscribing to {symbol} (silent fail)")
            await self._request_mark_subscription(symbol, subscribe=True)
    else:
        # All healthy - log summary
        logger.debug(
            f"✅ [MARK] Health check OK: {len(self.positions)} positions, "
            f"{len(self.subscribed_symbols)} subscribed, "
            f"{len(self.pending_subscriptions)} pending"
        )
```

**Обоснование изменений:**

1. **STEP 1: Сохраняем существующую логику** (line 8-10)
   - ✅ Backward compatible
   - ✅ Проверка presence остается

2. **STEP 2: Добавляем проверку freshness** (line 12-27)
   - ✅ Обнаруживает silent fails
   - ✅ Threshold 60s - баланс между чувствительностью и ложными срабатываниями
   - ✅ Пропускаем уже missing subscriptions (не дублируем работу)

3. **STEP 3: Улучшенное recovery** (line 29-57)
   - ✅ Логирование с деталями (missing vs stale)
   - ✅ Для stale: сначала discard из subscribed_symbols (очистка состояния)
   - ✅ Затем resubscribe

**Анализ безопасности:**

❓ **Вопрос:** Может ли это вызвать лишние resubscriptions?
✅ **Ответ:** Нет. Resubscribe только если:
   - Symbol in positions (активная позиция)
   - Нет данных >60s (реальная проблема)

❓ **Вопрос:** Может ли threshold 60s быть слишком коротким?
✅ **Ответ:** Нет. Binance отправляет данные каждую секунду (@1s). 60s = 59 пропущенных updates → очевидная проблема.

❓ **Вопрос:** Может ли это создать race condition?
✅ **Ответ:** Нет.
   - subscribed_symbols.discard() безопасно (idempotent)
   - _request_mark_subscription() добавляет в queue (thread-safe)

### 2.3. Тестирование Фазы 2

**Тест 2.1: Silent Fail Detection**
```python
async def test_silent_fail_detection():
    """Test detection of silent fails"""
    stream = BinanceHybridStream(...)

    # Setup: Position with stale data
    stream.positions['BTCUSDT'] = {'entry_price': '50000'}
    stream.subscribed_symbols.add('BTCUSDT')

    # Simulate old data (61 seconds ago)
    stream.mark_prices['BTCUSDT'] = '50000.00'
    stream.mark_prices['BTCUSDT_timestamp'] = asyncio.get_event_loop().time() - 61.0

    # Run health check
    await stream._verify_subscriptions_health()

    # Verify: should detect and resubscribe
    assert 'BTCUSDT' not in stream.subscribed_symbols  # Removed
    # Check that resubscribe was queued
    assert not stream.subscription_queue.empty()
```

**Тест 2.2: Healthy Subscriptions**
```python
async def test_healthy_subscriptions():
    """Test that healthy subscriptions are not touched"""
    stream = BinanceHybridStream(...)

    # Setup: Position with fresh data
    stream.positions['ETHUSDT'] = {'entry_price': '3000'}
    stream.subscribed_symbols.add('ETHUSDT')
    stream.mark_prices['ETHUSDT'] = '3000.00'
    stream.mark_prices['ETHUSDT_timestamp'] = asyncio.get_event_loop().time() - 5.0  # 5s ago

    # Run health check
    await stream._verify_subscriptions_health()

    # Verify: should remain unchanged
    assert 'ETHUSDT' in stream.subscribed_symbols
    assert stream.subscription_queue.empty()  # No resubscribe
```

**Тест 2.3: Mixed Scenarios**
```python
async def test_mixed_scenarios():
    """Test mixed healthy/missing/stale subscriptions"""
    stream = BinanceHybridStream(...)

    # 3 positions
    stream.positions = {
        'BTCUSDT': {},  # Healthy
        'ETHUSDT': {},  # Missing subscription
        'BNBUSDT': {}   # Stale (silent fail)
    }

    # BTCUSDT: healthy
    stream.subscribed_symbols.add('BTCUSDT')
    stream.mark_prices['BTCUSDT_timestamp'] = asyncio.get_event_loop().time()

    # ETHUSDT: missing (no subscription)

    # BNBUSDT: stale
    stream.subscribed_symbols.add('BNBUSDT')
    stream.mark_prices['BNBUSDT_timestamp'] = asyncio.get_event_loop().time() - 70.0

    # Run health check
    await stream._verify_subscriptions_health()

    # Verify
    assert 'BTCUSDT' in stream.subscribed_symbols  # Untouched
    assert 'BNBUSDT' not in stream.subscribed_symbols  # Removed (stale)
    # 2 resubscriptions queued (ETHUSDT + BNBUSDT)
    assert stream.subscription_queue.qsize() == 2
```

---

## 📦 ФАЗА 3: УЛУЧШЕНИЕ #3 - Non-blocking Warmup

### 3.1. Обоснование

**Текущая проблема:**
```python
# binance_hybrid_stream.py:816-819
if restored > 0:
    logger.info(f"⏳ [MARK] Warmup period: waiting 90s...")
    await asyncio.sleep(90.0)  # ← БЛОКИРУЕТ event loop на 90 секунд!
```

**Сценарий проблемы:**
```
T+0s:   Reconnect started
T+0s:   Восстановление 5 подписок
T+0s:   Warmup start → await asyncio.sleep(90)
T+30s:  Новая позиция открылась → subscription request в queue
T+30s:  Subscription manager НЕ может обработать (ждет warmup!)
T+90s:  Warmup complete, теперь обрабатывается новая подписка
        → ЗАДЕРЖКА 60 СЕКУНД для новой позиции!
```

### 3.2. Изменения в коде

#### Изменение 3.1: Сделать warmup неблокирующим

**Файл:** `websocket/binance_hybrid_stream.py`
**Строки:** 815-846
**Действие:** MODIFY

**ТЕКУЩИЙ КОД:**
```python
# PHASE 2: WARMUP PERIOD (90 seconds)
if restored > 0:
    logger.info(f"⏳ [MARK] Warmup period: waiting 90s for data to start flowing...")
    await asyncio.sleep(90.0)  # ← BLOCKS!
    logger.info(f"✅ [MARK] Warmup complete")

    # PHASE 3: VERIFICATION (background, non-blocking)
    logger.info(f"🔍 [MARK] Verifying subscriptions in background...")

    # Start verification in background (don't block)
    async def background_verify():
        try:
            result = await self._verify_all_subscriptions_active(timeout=60.0)
            # ... logging ...
        except Exception as e:
            logger.error(f"❌ [MARK] Background verification error: {e}")

    # Run in background, don't await
    asyncio.create_task(background_verify())
```

**НОВЫЙ КОД:**
```python
# PHASE 2 + 3: WARMUP AND VERIFICATION (non-blocking)
if restored > 0:
    logger.info(
        f"⏳ [MARK] Starting non-blocking warmup (90s) and verification "
        f"for {restored} subscriptions..."
    )

    # Run warmup + verification in background task
    async def warmup_and_verify():
        """
        Non-blocking warmup and verification

        This runs in background, allowing new subscriptions to be processed
        immediately without waiting for warmup to complete.
        """
        try:
            # WARMUP: Wait for data to start flowing
            logger.debug("[MARK] Warmup: sleeping 90s...")
            await asyncio.sleep(90.0)
            logger.info("✅ [MARK] Warmup complete")

            # VERIFICATION: Check subscription health
            logger.info("🔍 [MARK] Verifying subscriptions...")
            result = await self._verify_all_subscriptions_active(timeout=60.0)

            if result['success_rate'] < 90:
                logger.warning(
                    f"⚠️ [MARK] Low verification rate: {result['success_rate']:.1f}%\n"
                    f"   Verified: {len(result['verified'])}\n"
                    f"   Failed: {len(result['failed'])}\n"
                    f"   Failed symbols: {result['failed']}"
                )
            else:
                logger.info(
                    f"✅ [MARK] Subscription health: {result['success_rate']:.1f}% "
                    f"({len(result['verified'])}/{result['total']})"
                )
        except Exception as e:
            logger.error(f"❌ [MARK] Warmup/verification error: {e}", exc_info=True)

    # Launch in background, don't await
    asyncio.create_task(warmup_and_verify())
    logger.debug("[MARK] Warmup task launched in background, continuing...")
```

**Обоснование изменений:**

1. **Объединение warmup + verification в одну задачу** (line 8-40)
   - ✅ Единая логика
   - ✅ Упрощенный error handling

2. **asyncio.create_task() вместо await** (line 43)
   - ✅ НЕ блокирует
   - ✅ Новые подписки обрабатываются сразу

3. **Детальное логирование** (line 15-36)
   - ✅ Видим progress warmup
   - ✅ Видим результаты verification

**Анализ безопасности:**

❓ **Вопрос:** Безопасно ли не ждать завершения warmup?
✅ **Ответ:** Да. Warmup не влияет на:
   - Subscription manager (работает параллельно)
   - Новые подписки (обрабатываются сразу)
   - Существующие данные (продолжают поступать)

❓ **Вопрос:** Может ли background task "потеряться"?
✅ **Ответ:** Нет. asyncio.create_task() регистрирует task в event loop. Task будет выполнен.

❓ **Вопрос:** Что если происходит новый reconnect во время warmup?
✅ **Ответ:** Старый warmup task продолжит работу (не вредит). Новый reconnect создаст новый warmup task.

### 3.3. Тестирование Фазы 3

**Тест 3.1: Non-blocking Warmup**
```python
async def test_non_blocking_warmup():
    """Test that warmup doesn't block subscription processing"""
    stream = BinanceHybridStream(...)

    # Simulate reconnect with warmup
    await stream._restore_subscriptions()  # Launches background warmup

    # Immediately add new subscription (should NOT block)
    start_time = asyncio.get_event_loop().time()
    await stream._request_mark_subscription('NEWUSDT', subscribe=True)
    elapsed = asyncio.get_event_loop().time() - start_time

    # Verify: should be instant (< 1s), NOT 90s
    assert elapsed < 1.0, f"Subscription took {elapsed}s, expected <1s"
```

**Тест 3.2: Warmup Task Completion**
```python
async def test_warmup_task_completion():
    """Test that warmup task completes successfully"""
    stream = BinanceHybridStream(...)

    # Track warmup completion
    warmup_completed = False

    # Monkey-patch to detect completion
    original_verify = stream._verify_all_subscriptions_active
    async def tracked_verify(*args, **kwargs):
        nonlocal warmup_completed
        result = await original_verify(*args, **kwargs)
        warmup_completed = True
        return result
    stream._verify_all_subscriptions_active = tracked_verify

    # Start warmup
    await stream._restore_subscriptions()

    # Wait for warmup + verification to complete
    await asyncio.sleep(155)  # 90s warmup + 60s verify + buffer

    # Verify completion
    assert warmup_completed, "Warmup task did not complete"
```

---

## 📦 ФАЗА 4: УЛУЧШЕНИЕ #4 - WebSocket Heartbeat Monitoring

### 4.1. Обоснование

**Проблема:** WebSocket может "зависнуть"
```
WebSocket connection = OPEN
TCP connection = ALIVE
НО: данные НЕ поступают (frozen stream)
```

**Текущая защита:**
```python
# binance_hybrid_stream.py:582-583
heartbeat=20,   # aiohttp отправляет ping каждые 20s
autoping=True   # Автоматический pong на ping от сервера
```

**НО:** Это проверяет только TCP connection, НЕ application-level stream!

### 4.2. Изменения в коде

#### Изменение 4.1: Добавить tracking последних сообщений

**Файл:** `websocket/binance_hybrid_stream.py`
**Строка:** После line 88 (после subscription_queue)
**Действие:** INSERT

**ТЕКУЩИЙ КОД:**
```python
# Subscription management
self.subscription_queue = asyncio.Queue()
self.next_request_id = 1

# Tasks
self.user_task = None
```

**НОВЫЙ КОД:**
```python
# Subscription management
self.subscription_queue = asyncio.Queue()
self.next_request_id = 1

# Heartbeat monitoring
self.last_mark_message_time = 0.0  # Timestamp of last message from mark stream
self.last_user_message_time = 0.0  # Timestamp of last message from user stream

# Tasks
self.user_task = None
```

**Обоснование:**
- ✅ Трекаем ВСЕ сообщения (не только price updates)
- ✅ Раздельно для mark и user streams

#### Изменение 4.2: Обновлять timestamp при получении сообщений

**Файл:** `websocket/binance_hybrid_stream.py`
**Строка:** 631 (начало _handle_mark_message)
**Действие:** MODIFY

**ТЕКУЩИЙ КОД:**
```python
async def _handle_mark_message(self, data: Dict):
    """Handle Mark Price Stream message"""
    # Handle subscription responses
    if 'result' in data and 'id' in data:
        # ...
```

**НОВЫЙ КОД:**
```python
async def _handle_mark_message(self, data: Dict):
    """Handle Mark Price Stream message"""
    # Update heartbeat timestamp
    self.last_mark_message_time = asyncio.get_event_loop().time()

    # Handle subscription responses
    if 'result' in data and 'id' in data:
        # ...
```

**Аналогично для user stream:**

**Файл:** `websocket/binance_hybrid_stream.py`
**Строка:** 488 (начало _handle_user_message)
**Действие:** MODIFY

**НОВЫЙ КОД:**
```python
async def _handle_user_message(self, data: Dict):
    """Handle User Data Stream message"""
    # Update heartbeat timestamp
    self.last_user_message_time = asyncio.get_event_loop().time()

    event_type = data.get('e')
    # ...
```

#### Изменение 4.3: Добавить heartbeat monitoring task

**Файл:** `websocket/binance_hybrid_stream.py`
**Строка:** После line 420 (после _periodic_health_check_task)
**Действие:** INSERT NEW METHOD

**НОВЫЙ МЕТОД:**
```python
async def _heartbeat_monitoring_task(self, interval_seconds: int = 30, timeout_seconds: int = 45):
    """
    Monitor WebSocket heartbeat

    Checks that we're receiving messages from WebSocket streams.
    If no messages for >timeout_seconds, forces reconnect.

    Args:
        interval_seconds: Check interval (default: 30s)
        timeout_seconds: Timeout threshold (default: 45s)
    """
    logger.info(
        f"💓 [HEARTBEAT] Starting heartbeat monitor "
        f"(interval: {interval_seconds}s, timeout: {timeout_seconds}s)"
    )

    while self.running:
        try:
            await asyncio.sleep(interval_seconds)

            if not self.running:
                break

            now = asyncio.get_event_loop().time()

            # Check mark stream
            if self.mark_connected:
                time_since_last = now - self.last_mark_message_time

                if self.last_mark_message_time > 0 and time_since_last > timeout_seconds:
                    logger.warning(
                        f"⚠️ [HEARTBEAT] Mark stream timeout: "
                        f"no messages for {int(time_since_last)}s. Forcing reconnect..."
                    )

                    # Force reconnect by closing WebSocket
                    if self.mark_ws and not self.mark_ws.closed:
                        await self.mark_ws.close()
                else:
                    logger.debug(
                        f"💓 [HEARTBEAT] Mark stream OK: "
                        f"last message {int(time_since_last)}s ago"
                    )

            # Check user stream
            if self.user_connected:
                time_since_last = now - self.last_user_message_time

                if self.last_user_message_time > 0 and time_since_last > timeout_seconds:
                    logger.warning(
                        f"⚠️ [HEARTBEAT] User stream timeout: "
                        f"no messages for {int(time_since_last)}s. Forcing reconnect..."
                    )

                    # Force reconnect
                    if self.user_ws and not self.user_ws.closed:
                        await self.user_ws.close()
                else:
                    logger.debug(
                        f"💓 [HEARTBEAT] User stream OK: "
                        f"last message {int(time_since_last)}s ago"
                    )

        except asyncio.CancelledError:
            logger.info("[HEARTBEAT] Heartbeat monitor cancelled")
            break
        except Exception as e:
            logger.error(f"[HEARTBEAT] Error in heartbeat monitor: {e}", exc_info=True)
            await asyncio.sleep(60)
```

**Обоснование:**

1. **Timeout 45s** (line 5)
   - Binance отправляет данные каждую 1s
   - 45s = 44 пропущенных updates → явная проблема
   - Больше чем TCP heartbeat (20s) → не конфликтует

2. **Проверка last_message_time > 0** (line 28, 47)
   - ✅ Защита от false positive сразу после старта
   - Первая проверка произойдет после получения хотя бы одного сообщения

3. **Forced reconnect через ws.close()** (line 36, 54)
   - ✅ Триггерит автоматический reconnect через _run_mark_stream finally block
   - ✅ Clean shutdown

#### Изменение 4.4: Запустить heartbeat monitor

**Файл:** `websocket/binance_hybrid_stream.py`
**Строка:** 145 (после health_check_task)
**Действие:** INSERT

**ТЕКУЩИЙ КОД:**
```python
# Periodic subscription health check (every 2 minutes)
self.health_check_task = asyncio.create_task(
    self._periodic_health_check_task(interval_seconds=120)
)

logger.info("✅ Binance Hybrid WebSocket started")
```

**НОВЫЙ КОД:**
```python
# Periodic subscription health check (every 2 minutes)
self.health_check_task = asyncio.create_task(
    self._periodic_health_check_task(interval_seconds=120)
)

# Heartbeat monitoring (every 30 seconds)
self.heartbeat_task = asyncio.create_task(
    self._heartbeat_monitoring_task(interval_seconds=30, timeout_seconds=45)
)

logger.info("✅ Binance Hybrid WebSocket started")
```

### 4.3. Тестирование Фазы 4

**Тест 4.1: Heartbeat Tracking**
```python
async def test_heartbeat_tracking():
    """Test that message timestamps are tracked"""
    stream = BinanceHybridStream(...)

    # Initial state
    assert stream.last_mark_message_time == 0.0

    # Simulate message
    await stream._handle_mark_message({'e': 'markPriceUpdate', 's': 'BTCUSDT', 'p': '50000'})

    # Verify timestamp updated
    assert stream.last_mark_message_time > 0
    now = asyncio.get_event_loop().time()
    assert now - stream.last_mark_message_time < 1.0  # Recent
```

**Тест 4.2: Timeout Detection**
```python
async def test_heartbeat_timeout_detection():
    """Test detection of frozen stream"""
    stream = BinanceHybridStream(...)

    # Setup: stream connected but frozen
    stream.mark_connected = True
    stream.last_mark_message_time = asyncio.get_event_loop().time() - 60.0  # 60s ago
    stream.mark_ws = MagicMock()  # Mock WebSocket

    # Run heartbeat check once
    await stream._heartbeat_monitoring_task(interval_seconds=1, timeout_seconds=45)

    # Verify: should have closed WebSocket
    stream.mark_ws.close.assert_called_once()
```

---

## 🔗 ФАЗА 5: INTEGRATION И ФИНАЛЬНОЕ ТЕСТИРОВАНИЕ

### 5.1. Интеграционные тесты

**Тест 5.1: Full Recovery Flow**
```python
async def test_full_silent_fail_recovery():
    """
    End-to-end test: Silent fail → Detection → Recovery
    """
    stream = BinanceHybridStream(...)

    # 1. Setup: Position with working subscription
    stream.positions['BTCUSDT'] = {}
    stream.subscribed_symbols.add('BTCUSDT')
    stream.mark_prices['BTCUSDT_timestamp'] = asyncio.get_event_loop().time()

    # 2. Simulate silent fail: stop receiving data
    await asyncio.sleep(2)  # Advance time
    stream.mark_prices['BTCUSDT_timestamp'] = asyncio.get_event_loop().time() - 70.0

    # 3. Health check should detect and recover
    await stream._verify_subscriptions_health()

    # 4. Verify recovery
    assert 'BTCUSDT' not in stream.subscribed_symbols  # Removed from subscribed
    assert not stream.subscription_queue.empty()  # Resubscribe queued
```

**Тест 5.2: Performance Under Load**
```python
async def test_performance_under_load():
    """Test performance with many positions"""
    stream = BinanceHybridStream(...)

    # Setup: 100 positions
    for i in range(100):
        symbol = f"SYMBOL{i}USDT"
        stream.positions[symbol] = {}
        stream.subscribed_symbols.add(symbol)
        stream.mark_prices[f"{symbol}_timestamp"] = asyncio.get_event_loop().time()

    # Run health check
    start = asyncio.get_event_loop().time()
    await stream._verify_subscriptions_health()
    elapsed = asyncio.get_event_loop().time() - start

    # Should complete quickly (< 1s)
    assert elapsed < 1.0, f"Health check took {elapsed}s for 100 positions"
```

### 5.2. Checklist перед деплоем

- [ ] Все тесты Phase 1 passed
- [ ] Все тесты Phase 2 passed
- [ ] Все тесты Phase 3 passed
- [ ] Все тесты Phase 4 passed
- [ ] Интеграционные тесты passed
- [ ] Performance тесты passed
- [ ] Code review completed
- [ ] Документация обновлена
- [ ] Логи протестированы (не слишком verbose)
- [ ] Backward compatibility verified

---

## 📊 ROLLOUT PLAN

### Stage 1: Тестовая среда (1-2 дня)
- Deploy на testnet
- Мониторинг 24 часа
- Проверка логов
- Performance metrics

### Stage 2: Production (Soft Launch) (2-3 дня)
- Deploy в production
- Мониторинг каждые 2 часа первые 24 часа
- Готовность к rollback

### Stage 3: Production (Full Launch) (после 3 дней)
- Если нет issues → считаем stable
- Переход к обычному мониторингу

---

## 🚨 ROLLBACK PLAN

Если возникли проблемы:

### Quick Rollback (< 5 минут)
```bash
git checkout HEAD~1  # Вернуться на предыдущий коммит
sudo systemctl restart trading_bot
```

### Partial Rollback (отключить конкретное улучшение)

**Отключить #1 (Timestamp Tracking):**
- Закомментировать line: `self.mark_prices[f"{symbol}_timestamp"] = ...`

**Отключить #2 (Enhanced Health Check):**
- Вернуть старую версию `_verify_subscriptions_health`

**Отключить #3 (Non-blocking Warmup):**
- Вернуть `await asyncio.sleep(90)` вместо `asyncio.create_task`

**Отключить #4 (Heartbeat Monitor):**
- Закомментировать `self.heartbeat_task = asyncio.create_task(...)`

---

## 📈 SUCCESS METRICS

### Before improvements:
- Silent fail detection time: NEVER
- Manual intervention required: YES
- Health check coverage: 50% (только presence)

### After improvements:
- Silent fail detection time: 60-120s
- Manual intervention required: NO (auto-recovery)
- Health check coverage: 100% (presence + freshness + heartbeat)

---

## 📝 NOTES

1. **Координация с Bybit:** Аналогичные изменения нужны для `bybit_hybrid_stream.py`
2. **Мониторинг:** Добавить alerts в Grafana для silent fail events
3. **Документация:** Обновить INVESTIGATION_REPORTS с новыми механизмами

---

**READY FOR IMPLEMENTATION** ✅
