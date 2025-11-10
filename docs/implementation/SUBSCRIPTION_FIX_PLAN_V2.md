# ПЛАН ИСПРАВЛЕНИЯ ПОДПИСОК WEBSOCKET V2

**Дата:** 2025-11-09
**Статус:** DRAFT - на основе реального тестирования
**Предыдущая попытка:** V1 - FAILED (event loop blocking)

---

## 🎯 ЦЕЛЬ

Исправить проблему silent fails при периодических переподключениях WebSocket, НЕ блокируя event loop и не нарушая работу ping/pong.

---

## 📊 ИСХОДНЫЕ ДАННЫЕ

### Результаты тестирования (interval=120s)
- **Baseline** (без верификации): 100% success, 0 silent fails
- **Event-based** (неблокирующая верификация): 100% success, 0 silent fails, БЫСТРЕЕ
- **Optimistic** (15s polling): 28% success, WebSocket закрывается

### Ключевые находки
1. ✅ Silent fails НЕ воспроизводятся при коротких интервалах (120s)
2. ⚠️  Проблема проявляется при длительной работе WebSocket (600s в боте)
3. ❌ Polling loops блокируют event loop и приводят к закрытию WebSocket
4. ✅ Event-based verification работает отлично и БЫСТРЕЕ baseline

---

## 🚧 СТРАТЕГИЯ

### Подход: Гибридный (Консервативный + Улучшения)

**Фаза 1: Дополнительное исследование** ⚠️
СНАЧАЛА понять root cause проблемы в production.

**Фаза 2: Event-based verification** (если проблема подтвердится)
Внедрить неблокирующую верификацию подписок.

**Фаза 3: Мониторинг и метрики**
Добавить visibility в работу подписок.

---

## 📋 ФАЗА 1: ДОПОЛНИТЕЛЬНОЕ ИССЛЕДОВАНИЕ

### Цель
Понять КОГДА и ПОЧ ЕМУ возникают silent fails в production.

### Задачи

#### 1.1 Анализ исторических логов
```bash
# Проверить логи бота за последние дни
grep "SILENT FAIL\|Restore success rate\|subscription" logs/*.log

# Вопросы:
- Когда началась проблема?
- Есть ли паттерн (время суток, день недели)?
- Связано ли с количеством позиций?
- Происходит ли на первом переподключении или позже?
```

#### 1.2 Тест с реальным интервалом (600s)
Создать тест с interval=600s (10 минут) для воспроизведения проблемы:

```python
# test_reconnection_600s.py
tester = BaselineReconnectionTester(
    symbols=BOT_SYMBOLS,
    reconnect_interval=600  # РЕАЛЬНЫЙ интервал как в боте
)
await tester.run(num_cycles=10)  # ~100 минут теста
```

**Критерий успеха:** Воспроизвести silent fails при 600s интервале.

#### 1.3 Проверка Binance API лимитов
Изучить документацию и community reports:
- Rate limits на SUBSCRIBE/UNSUBSCRIBE
- Максимальное время жизни WebSocket
- Поведение при reconnect

**Документация:** https://binance-docs.github.io/apidocs/futures/en/#websocket-market-streams

---

## 📋 ФАЗА 2: EVENT-BASED VERIFICATION

### Предусловия
- ✅ Проблема воспроизведена в тестах с interval=600s
- ✅ Понят root cause
- ✅ Event-based подход подтверждён как решение

### Архитектура

#### 2.1 Новые компоненты

```python
class SubscriptionVerifier:
    """Неблокирующая верификация подписок"""

    def __init__(self):
        self.verification_events: Dict[str, asyncio.Event] = {}
        self.last_data_time: Dict[str, float] = {}

    async def verify_subscription(
        self,
        symbol: str,
        timeout: float = 10.0
    ) -> bool:
        """
        Ждет РЕАЛЬНЫХ данных от символа (неблокирующе)

        Returns:
            True если данные получены
            False если timeout
        """
        # Создать Event для символа
        event = asyncio.Event()
        self.verification_events[symbol] = event

        try:
            # Ждать Event (НЕ блокирует!)
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self.verification_events.pop(symbol, None)

    def on_data_received(self, symbol: str):
        """Вызывается message_handler при получении данных"""
        self.last_data_time[symbol] = asyncio.get_event_loop().time()

        # Установить Event если кто-то ждёт
        if symbol in self.verification_events:
            self.verification_events[symbol].set()
```

#### 2.2 Модификация BinanceHybridStream

##### Добавить tracking
```python
# websocket/binance_hybrid_stream.py

class BinanceHybridStream:
    def __init__(self, ...):
        # ... existing code ...

        # Subscription verification (NEW)
        self.verifier = SubscriptionVerifier()
```

##### Модифицировать _on_mark_price_update
```python
def _on_mark_price_update(self, message: dict):
    """Handle mark price updates"""
    symbol = message.get('s')

    # ... existing position update code ...

    # Notify verifier about data arrival (NEW)
    self.verifier.on_data_received(symbol)
```

##### Модифицировать _subscribe_mark_price
```python
async def _subscribe_mark_price(self, symbol: str) -> bool:
    """
    Subscribe with EVENT-BASED verification (NON-BLOCKING)

    Returns:
        True if subscription successful AND data received
        False otherwise
    """
    stream_name = f"{symbol.lower()}@markPrice@1s"
    request_id = self.next_request_id
    self.next_request_id += 1

    subscribe_msg = {
        "method": "SUBSCRIBE",
        "params": [stream_name],
        "id": request_id
    }

    try:
        # Send SUBSCRIBE
        await self.mark_ws.send_str(json.dumps(subscribe_msg))
        self.logger.debug(f"[MARK] Sent SUBSCRIBE for {symbol} (id={request_id})")

        # Wait for REAL DATA (event-based, NON-BLOCKING!)
        verified = await self.verifier.verify_subscription(
            symbol,
            timeout=10.0  # 10 seconds (not 15!)
        )

        if verified:
            self.subscribed_symbols.add(symbol)
            self.logger.info(f"✅ [MARK] Verified {symbol} (data received)")
            return True
        else:
            self.logger.warning(
                f"⚠️  [MARK] Timeout for {symbol} - no data after 10s"
            )
            self.pending_subscriptions.add(symbol)
            return False

    except Exception as e:
        self.logger.error(f"❌ [MARK] Failed to subscribe {symbol}: {e}")
        return False
```

##### Модифицировать _restore_subscriptions
```python
async def _restore_subscriptions(self):
    """
    Restore subscriptions with PARALLEL verification

    This doesn't block event loop because verify_subscription
    uses asyncio.Event.wait() internally
    """
    symbols_to_restore = list(self.subscribed_symbols) + \
                        list(self.pending_subscriptions)

    if not symbols_to_restore:
        return

    self.logger.info(
        f"🔄 [MARK] Restoring {len(symbols_to_restore)} subscriptions..."
    )

    # Clear old state
    self.subscribed_symbols.clear()

    # Subscribe to all in parallel (with small stagger)
    tasks = []
    for i, symbol in enumerate(symbols_to_restore):
        # Small delay to avoid burst
        delay = i * 0.1
        task = self._subscribe_with_delay(symbol, delay)
        tasks.append((symbol, task))

    # Wait for all
    results = {}
    for symbol, task in tasks:
        try:
            success = await task
            results[symbol] = success
        except Exception as e:
            self.logger.error(f"[MARK] Error restoring {symbol}: {e}")
            results[symbol] = False

    # Stats
    successful = sum(1 for v in results.values() if v)
    failed = len(results) - successful

    self.logger.info(
        f"✅ [MARK] Restored {successful}/{len(results)} subscriptions"
    )

    if failed > 0:
        self.logger.warning(f"⚠️  [MARK] {failed} subscriptions failed")

        # Retry failed ones (ONE attempt)
        failed_symbols = [s for s, ok in results.items() if not ok]
        await self._retry_subscriptions(failed_symbols)

async def _subscribe_with_delay(self, symbol: str, delay: float) -> bool:
    """Helper: subscribe with initial delay"""
    if delay > 0:
        await asyncio.sleep(delay)
    return await self._subscribe_mark_price(symbol)

async def _retry_subscriptions(self, symbols: List[str]):
    """Retry failed subscriptions (one attempt)"""
    if not symbols:
        return

    self.logger.info(f"🔄 [MARK] Retrying {len(symbols)} failed subscriptions...")

    for symbol in symbols:
        success = await self._subscribe_mark_price(symbol)
        if not success:
            self.logger.error(f"❌ [MARK] Permanent fail: {symbol}")
        await asyncio.sleep(0.2)  # Small delay between retries
```

---

## 📋 ФАЗА 3: МОНИТОРИНГ И МЕТРИКИ

### 3.1 Метрики подписок

Добавить tracking:
```python
class SubscriptionMetrics:
    """Track subscription health"""

    def __init__(self):
        self.total_attempts = 0
        self.total_successes = 0
        self.total_failures = 0
        self.total_retries = 0

        # Per-symbol metrics
        self.symbol_failures: Dict[str, int] = defaultdict(int)
        self.last_success_time: Dict[str, float] = {}

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 100.0
        return (self.total_successes / self.total_attempts) * 100

    def record_attempt(self, symbol: str, success: bool):
        self.total_attempts += 1
        if success:
            self.total_successes += 1
            self.last_success_time[symbol] = time.time()
        else:
            self.total_failures += 1
            self.symbol_failures[symbol] += 1
```

### 3.2 Health Check

Улучшить `_verify_subscriptions_health()`:
```python
async def _verify_subscriptions_health(self):
    """
    Check subscription health and alert on problems

    NEW: Check REAL data arrival, not just presence in sets
    """
    current_time = asyncio.get_event_loop().time()
    stale_threshold = 60.0  # 60 seconds

    stale_subscriptions = []

    for symbol in self.subscribed_symbols:
        last_update = self.verifier.last_data_time.get(symbol, 0)
        if current_time - last_update > stale_threshold:
            stale_subscriptions.append(symbol)

    if stale_subscriptions:
        self.logger.warning(
            f"⚠️  [MARK] {len(stale_subscriptions)} stale subscriptions "
            f"(>60s without data): {stale_subscriptions}"
        )

        # Alert via Telegram
        await self.alert_manager.send_alert(
            level="warning",
            message=f"🚨 {len(stale_subscriptions)} WebSocket "
                   f"subscriptions stale!\n{stale_subscriptions[:5]}"
        )

        # Auto-resubscribe
        await self._retry_subscriptions(stale_subscriptions)
```

### 3.3 Dashboard Metrics

Добавить в логи/телеграм:
```python
def log_subscription_stats(self):
    """Log subscription statistics"""
    metrics = self.subscription_metrics

    self.logger.info(f"""
📊 Subscription Statistics:
   Total attempts: {metrics.total_attempts}
   Successes: {metrics.total_successes}
   Failures: {metrics.total_failures}
   Retries: {metrics.total_retries}
   Success rate: {metrics.success_rate:.1f}%

   Problem symbols: {[s for s, count in metrics.symbol_failures.items() if count > 3]}
    """)
```

---

## 🔧 ГИТ WORKFLOW

### Ветки
```bash
# Исследование
feature/subscription-investigation-600s

# Реализация (после подтверждения)
feature/event-based-verification-v2
```

### Коммиты (при реализации Фазы 2)

**Phase 0: Подготовка**
```bash
git checkout -b feature/event-based-verification-v2

# Add tracking infrastructure
git add websocket/binance_hybrid_stream.py
git commit -m "feat(ws): add SubscriptionVerifier for non-blocking verification"
```

**Phase 1: Core verification**
```bash
# Update _on_mark_price_update
git add websocket/binance_hybrid_stream.py
git commit -m "feat(ws): track data arrival in verifier"

# Update _subscribe_mark_price
git add websocket/binance_hybrid_stream.py
git commit -m "feat(ws): implement event-based subscription verification"
```

**Phase 2: Restore logic**
```bash
# Update _restore_subscriptions
git add websocket/binance_hybrid_stream.py
git commit -m "feat(ws): parallel subscription restore with retry"
```

**Phase 3: Metrics**
```bash
# Add metrics
git add websocket/binance_hybrid_stream.py
git commit -m "feat(ws): add subscription health metrics and monitoring"
```

---

## ✅ КРИТЕРИИ УСПЕХА

### Фаза 1 (Исследование)
- [ ] Проанализированы исторические логи бота
- [ ] Создан тест с interval=600s
- [ ] Проблема воспроизведена или опровергнута
- [ ] Понят root cause

### Фаза 2 (Реализация)
- [ ] Event-based verification реализован
- [ ] Все тесты проходят (unit + integration)
- [ ] Тест с interval=600s показывает >95% success rate
- [ ] Event loop НЕ блокируется (проверено profiling)
- [ ] WebSocket НЕ закрывается (проверено длительным тестом)

### Фаза 3 (Production)
- [ ] Развёрнуто в production
- [ ] Мониторинг показывает >95% success rate
- [ ] Нет позиций без обновления цен
- [ ] Trailing Stop работает для всех позиций
- [ ] Нет ошибок "Cannot write to closing transport"

---

## ⚠️  РИСКИ И MITIGATION

### Риск 1: Проблема не в методе подписки
**Вероятность:** Средняя
**Impact:** Высокий
**Mitigation:** Фаза 1 - сначала исследование, потом реализация

### Риск 2: Event-based тоже не поможет при 600s
**Вероятность:** Низкая
**Impact:** Средний
**Mitigation:** Длительные тесты перед production deployment

### Риск 3: Binance API лимиты
**Вероятность:** Средняя
**Impact:** Высокий
**Mitigation:** Рассмотреть Combined Stream API как fallback

---

## 🔄 АЛЬТЕРНАТИВНЫЕ ПОДХОДЫ

### Если Event-based не поможет

#### Option A: Combined Stream API
```python
# Один WebSocket для всех символов - нет SUBSCRIBE операций
streams = [f"{s.lower()}@markPrice@1s" for s in symbols]
url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
```

**Pros:**
- Нет проблем с подписками
- Более стабильное соединение

**Cons:**
- Нужна переработка архитектуры
- Сложнее динамически добавлять символы

#### Option B: Separate WebSocket Manager per Symbol
**Pros:**
- Полная изоляция
- Легче отлаживать

**Cons:**
- Много соединений (лимиты Binance?)
- Больше overhead

#### Option C: Уменьшить интервал переподключения
```python
# Вместо 600s использовать 300s (5 минут)
RECONNECT_INTERVAL = 300
```

**Pros:**
- Меньше шанс silent fails (если проблема в длительности)

**Cons:**
- Больше overhead
- Больше риск rate limits

---

## 📚 ССЫЛКИ

- [Тестовые скрипты](/tests/investigation/test_reconnection_*.py)
- [Анализ результатов](/docs/RECONNECTION_TESTING_ANALYSIS.md)
- [Failure Report V1](/CRITICAL_VERIFICATION_FAILURE_REPORT.md)
- [Binance Futures WebSocket](https://binance-docs.github.io/apidocs/futures/en/#websocket-market-streams)

---

## 🎯 NEXT STEPS

1. **Сейчас:** Анализ исторических логов бота
2. **Сегодня:** Создать и запустить тест с interval=600s
3. **После результатов:** Принять решение о реализации Фазы 2
4. **Если подтвердится:** Реализовать Event-based verification
5. **Production:** Постепенный rollout с мониторингом
