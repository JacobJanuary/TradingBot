# ФИНАЛЬНЫЙ АНАЛИЗ: Root Cause найден

**Дата:** 2025-11-09
**Статус:** 🔴 ROOT CAUSE IDENTIFIED

---

## 🎯 ROOT CAUSE

### Проблема: Mark Price WebSocket теряет 85% подписок при переподключении

**Доказательства из логов:**

```
2025-11-09 05:34:52 - 🔄 [MARK] Restoring 47 subscriptions (47 confirmed + 0 pending)...
2025-11-09 05:34:52 - ⚠️ [MARK] 41 subscriptions not restored
```

**Статистика:**
- Пытается восстановить: 47 подписок
- Успешно восстановлено: 6 подписок (13%)
- **НЕ восстановлено: 41 подписка (87%)**

### Цикл проблемы:

1. Mark Price WebSocket переподключается каждые ~10 минут
2. При переподключении вызывается `_restore_subscriptions()`
3. Пытается восстановить все подписки из `self.subscribed_symbols`
4. **85% подписок FAIL при восстановлении**
5. Позиции остаются БЕЗ подписки на mark price
6. WebSocket НЕ отправляет обновления цены
7. Trailing Stop НЕ РАБОТАЕТ
8. Aged Position механизм обнаруживает проблему спустя 3+ часа
9. Пытается переподписаться - FAIL (timeout 15s)
10. Позиция удаляется из мониторинга

---

## 📊 ДАННЫЕ

### Подписки НЕ восстановленные при reconnect 05:34:52:

```
ALCHUSDT, ATAUSDT, MEMEUSDT, DUSKUSDT, ENJUSDT, MOVEUSDT, MAVUSDT,
ILVUSDT, SSVUSDT, B2USDT, USUALUSDT, ZETAUSDT, TLMUSDT, KSMUSDT,
EPICUSDT, DYMUSDT, TIAUSDT, FUSDT, ACEUSDT, EGLDUSDT, XAIUSDT,
PUNDIXUSDT, ZBTUSDT, LSKUSDT, FLUXUSDT, FLMUSDT, SOMIUSDT, JASMYUSDT,
SUSHIUSDT, DOLOUSDT, NEARUSDT, NMRUSDT, SANDUSDT, CHZUSDT, YFIUSDT,
RLCUSDT, DAMUSDT, BLUAIUSDT, TANSSIUSDT, SYNUSDT, 1000FLOKIUSDT
```

**Всего: 41 символ**

### BERAUSDT хронология:

```
05:32:30 - ✅ [MARK] Subscribed to ILVUSDT (последняя успешная подписка)
05:32:36 - ✅ Position #430 for BERAUSDT opened
05:32:39 - ✅ Added BERAUSDT to tracked positions
05:32-05:34 - ❌ НЕТ логов о подписке BERAUSDT на mark price
05:34:52 - 🔄 [MARK] Reconnect, пытается восстановить 47 подписок
05:34:52 - ❌ 41 подписка НЕ восстановлена (BERAUSDT среди них)
...
08:33+ - ⚠️ Aged Position механизм обнаруживает проблему
```

---

## 🐛 АНАЛИЗ КОДА

### 1. Процесс подписки (websocket/binance_hybrid_stream.py)

**При открытии позиции:**

```python
# Line 535-536
self.positions[symbol] = {...}
await self._request_mark_subscription(symbol, subscribe=True)
```

**_request_mark_subscription:**

```python
# Line 725-731
async def _request_mark_subscription(self, symbol: str, subscribe: bool = True):
    if subscribe:
        self.pending_subscriptions.add(symbol)  # Добавить в pending
        logger.debug(f"[MARK] Marked {symbol} for subscription (pending)")
    await self.subscription_queue.put((symbol, subscribe))  # В очередь
```

**_subscription_manager (обработчик очереди):**

```python
# Line 700-718
async def _subscription_manager(self):
    while self.running:
        symbol, subscribe = await self.subscription_queue.get()

        # ⚠️ ПРОБЛЕМА: Проверка подключения
        if self.mark_connected and self.mark_ws and not self.mark_ws.closed:
            if subscribe:
                await self._subscribe_mark_price(symbol)
        # ❌ ЕСЛИ НЕ ПОДКЛЮЧЕН - ЗАПРОС ПРОПУСКАЕТСЯ!
```

**_subscribe_mark_price:**

```python
# Line 733-758
async def _subscribe_mark_price(self, symbol: str):
    if symbol in self.subscribed_symbols:
        return  # Уже подписан

    stream_name = f"{symbol.lower()}@markPrice@1s"

    message = {
        "method": "SUBSCRIBE",
        "params": [stream_name],
        "id": self.next_request_id
    }

    await self.mark_ws.send_str(json.dumps(message))

    self.subscribed_symbols.add(symbol)
    self.pending_subscriptions.discard(symbol)  # Очистить pending
```

### 2. Процесс восстановления при reconnect

**_restore_subscriptions:**

```python
# Line 760-790
async def _restore_subscriptions(self):
    all_symbols = self.subscribed_symbols.union(self.pending_subscriptions)

    if not all_symbols:
        return

    symbols_to_restore = list(all_symbols)
    logger.info(f"🔄 [MARK] Restoring {len(symbols_to_restore)} subscriptions...")

    # ⚠️ ПРОБЛЕМА: Очищаем оба набора ПЕРЕД восстановлением
    self.subscribed_symbols.clear()
    self.pending_subscriptions.clear()

    restored = 0
    for symbol in symbols_to_restore:
        try:
            await self._subscribe_mark_price(symbol)
            restored += 1

            # Задержка 0.1s между подписками
            if restored < len(symbols_to_restore):
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"❌ [MARK] Failed to restore subscription for {symbol}: {e}")

    logger.info(f"✅ [MARK] Restored {restored}/{len(symbols_to_restore)} subscriptions")

    # ❌ ПРОБЛЕМА: Если символ не восстановлен - он ПОТЕРЯН навсегда!
    # НЕТ логики для возврата в pending_subscriptions
```

---

## 💥 НАЙДЕННЫЕ БАГИ

### БАГ #1: Потеря подписок при disconnected mark_ws

**Место:** `_subscription_manager()` line 714

**Проблема:**
```python
if self.mark_connected and self.mark_ws and not self.mark_ws.closed:
    await self._subscribe_mark_price(symbol)
# ❌ ELSE - запрос из очереди пропускается навсегда!
```

**Последствия:**
- Если Mark WS временно отключен (reconnecting)
- Новые позиции открываются
- Запросы подписки в очередь
- Обработчик ПРОПУСКАЕТ запросы
- Символы остаются в `pending_subscriptions`
- НО реальной подписки НЕТ

**Fix:**
- Если не подключен → вернуть запрос в очередь
- ИЛИ: `pending_subscriptions` должны обрабатываться после reconnect автоматически

### БАГ #2: Массовая потеря подписок при restore

**Место:** `_restore_subscriptions()` line 773-790

**Проблема:**
1. Очищает `subscribed_symbols` и `pending_subscriptions` ПЕРЕД восстановлением
2. Пытается восстановить все символы
3. **85% символов FAIL (неизвестная причина)**
4. НЕТ механизма возврата failed символов в pending
5. Символы ПОТЕРЯНЫ навсегда

**Возможные причины FAIL:**
- Лимит количества подписок Binance?
- Слишком быстрая отправка (0.1s delay недостаточно)?
- WebSocket не полностью готов?
- Ошибки в send_str не логируются?

**Последствия:**
- Каждые 10 минут (reconnect) теряется 85% подписок
- Позиции остаются без мониторинга
- Trailing Stop не работает

### БАГ #3: Отсутствие error handling при _subscribe_mark_price

**Место:** `_subscribe_mark_price()` line 757-758

```python
except Exception as e:
    logger.error(f"[MARK] Subscription error for {symbol}: {e}")
    # ❌ НЕТ возврата в pending_subscriptions!
```

**Проблема:**
- Если подписка failed → только лог ошибки
- Символ НЕ возвращается в pending
- НЕТ retry механизма

---

## 🔬 ПОЧЕМУ 85% ПОДПИСОК НЕ ВОССТАНАВЛИВАЮТСЯ?

### Гипотезы:

### Гипотеза #1: Binance API лимит одновременных подписок

Binance может ограничивать:
- Max 200-300 подписок на одно соединение?
- Max 10-20 подписок в секунду?

**Проверка:** Нужно найти документацию Binance WebSocket limits

### Гипотеза #2: WebSocket не готов принимать подписки

```python
await self.mark_ws.send_str(json.dumps(message))
```

Возможно:
- WebSocket подключен (mark_connected=True)
- НО еще не готов принимать данные
- send_str() выполняется, но данные теряются
- Нет подтверждения от Binance

**Fix:** Ждать response от Binance после SUBSCRIBE

### Гипотеза #3: Race condition при массовой подписке

```python
for symbol in symbols_to_restore:
    await self._subscribe_mark_price(symbol)
    await asyncio.sleep(0.1)  # 100ms delay
```

Если 47 символов × 100ms = 4.7 секунды массовой отправки:
- Возможно перегрузка WebSocket
- Возможно timeout на стороне Binance
- Некоторые SUBSCRIBE теряются

**Fix:** Увеличить delay, batch подписки

### Гипотеза #4: Отсутствие проверки ответа от Binance

Binance WebSocket должен отвечать на SUBSCRIBE:
```json
{
  "result": null,
  "id": 1
}
```

**Проблема:** Код НЕ ПРОВЕРЯЕТ ответ!

```python
await self.mark_ws.send_str(json.dumps(message))
self.subscribed_symbols.add(symbol)  # ❌ Считаем успешным БЕЗ проверки ответа!
```

**Fix:** Ждать ответ от Binance, только после success добавлять в subscribed_symbols

---

## 📋 СЛЕДУЮЩИЕ ШАГИ (ИССЛЕДОВАНИЕ)

### 1. Проверить логи ошибок при restore

Найти в логах:
```
❌ [MARK] Failed to restore subscription for
```

Какие ошибки возникают?

### 2. Проверить Binance WebSocket лимиты

- Документация Binance API
- Max subscriptions per connection
- Rate limits для SUBSCRIBE

### 3. Проверить код обработки WebSocket ответов

Ищем где обрабатываются response от Binance:
- Есть ли проверка `{"result": null, "id": X}`?
- Логируются ли ошибки от Binance?

### 4. Написать тест для проверки подписки

- Открыть позицию
- Проверить через N секунд - есть ли подписка?
- Проверить приходят ли mark price updates?

### 5. Проверить сколько позиций сейчас БЕЗ подписки

Запрос к БД:
- Все open positions
- Сколько из них в `subscribed_symbols`?
- Сколько в `pending_subscriptions`?
- Сколько НИГДЕ (потеряны)?

---

## 💊 ПРЕДЛАГАЕМЫЕ РЕШЕНИЯ (ПОСЛЕ ИССЛЕДОВАНИЯ)

### Fix #1: Retry mechanism для failed subscriptions

```python
async def _subscribe_mark_price(self, symbol: str):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await self.mark_ws.send_str(json.dumps(message))

            # ✅ WAIT for response from Binance
            response = await self._wait_for_subscribe_response(self.next_request_id, timeout=5)

            if response.get('result') is None:  # Success
                self.subscribed_symbols.add(symbol)
                self.pending_subscriptions.discard(symbol)
                return True

        except Exception as e:
            logger.warning(f"Subscribe attempt {attempt+1}/{max_retries} failed: {e}")
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

    # ❌ All retries failed
    logger.error(f"Failed to subscribe {symbol} after {max_retries} attempts")
    # Keep in pending for later retry
    return False
```

### Fix #2: Return failed subscriptions to pending

```python
async def _restore_subscriptions(self):
    all_symbols = self.subscribed_symbols.union(self.pending_subscriptions)

    # ✅ DON'T clear until we know results
    symbols_to_restore = list(all_symbols)

    restored = []
    failed = []

    for symbol in symbols_to_restore:
        success = await self._subscribe_mark_price(symbol)
        if success:
            restored.append(symbol)
        else:
            failed.append(symbol)

        await asyncio.sleep(0.2)  # Увеличен delay

    # ✅ Update sets AFTER restore attempt
    self.subscribed_symbols = set(restored)
    self.pending_subscriptions = set(failed)  # Keep failed for retry

    logger.info(f"✅ Restored {len(restored)}/{len(symbols_to_restore)}")
    if failed:
        logger.warning(f"⚠️ {len(failed)} subscriptions will retry: {failed}")
```

### Fix #3: Periodic health check with auto-repair

```python
async def _subscription_health_monitor(self):
    """Периодически проверять и чинить подписки"""
    while self.running:
        await asyncio.sleep(60)  # Каждую минуту

        # Все позиции должны быть подписаны
        missing = set(self.positions.keys()) - self.subscribed_symbols

        if missing:
            logger.warning(f"⚠️ Found {len(missing)} positions without subscription")

            for symbol in missing:
                logger.info(f"🔄 Auto-resubscribing {symbol}")
                await self._request_mark_subscription(symbol, subscribe=True)
```

### Fix #4: Batch subscriptions для reduce load

```python
async def _subscribe_batch(self, symbols: List[str], batch_size: int = 10):
    """Subscribe in batches to avoid overwhelming WebSocket"""

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]

        for symbol in batch:
            await self._subscribe_mark_price(symbol)
            await asyncio.sleep(0.05)  # Small delay within batch

        # Longer delay between batches
        await asyncio.sleep(2.0)

        logger.info(f"✅ Batch {i//batch_size + 1} done ({len(batch)} symbols)")
```

---

## 📝 ИТОГИ ИССЛЕДОВАНИЯ

### ✅ Подтверждено:

1. **Root cause найден:** Mark Price WebSocket теряет 85% подписок при reconnect
2. **Механизм проблемы:** Нет retry, нет проверки ответов, нет возврата failed в pending
3. **Последствия:** Позиции без цены → TS не работает → упущенная прибыль
4. **Масштаб:** 40+ позиций одновременно без мониторинга

### ❓ Требует дополнительного исследования:

1. Почему именно 85% fail? (лимиты Binance? race condition? timeout?)
2. Какие ошибки в логах при failed restore?
3. Есть ли проверка response от Binance?
4. Сколько сейчас позиций без подписки?

### 🎯 Следующие действия:

1. ✅ Отчет создан
2. ⏳ Проверить логи на ошибки restore
3. ⏳ Исследовать Binance API limits
4. ⏳ Написать дополнительные тесты
5. ⏳ **НЕ ТРОГАТЬ КОД** (по указанию пользователя)

---

**Отчет создан:** 2025-11-09 11:15 UTC
**Автор:** Claude Code
**Статус:** ROOT CAUSE IDENTIFIED, требуется дополнительное исследование перед fix
