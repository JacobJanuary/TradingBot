# 🔴 FORENSIC INVESTIGATION: Binance Mark Price Updates Stopped
**Дата расследования**: 2025-10-25
**Статус**: КРИТИЧЕСКИЙ БАГ НАЙДЕН
**Воздействие**: Trailing Stop НЕ работает для 6 из 7 позиций Binance

---

## 📊 Симптомы проблемы

### Жалоба пользователя
> "На Binance открыто 6 позиций. TS для них не обновляет цены уже несколько минут. Сперва активность у некоторых символов была, но затем она пропала совсем."

### Наблюдаемое поведение
- **Позиций на Binance**: 7 (ZBTUSDT, ZRXUSDT, SFPUSDT, ALICEUSDT, WOOUSDT, REZUSDT, KAITOUSDT)
- **Получают обновления**: 1 (только KAITOUSDT)
- **НЕ получают обновления**: 6 (все остальные)
- **Длительность проблемы**: ~4 минуты (с 23:21:07)

---

## 🔍 Timeline расследования

### Фаза 1: Нормальная работа (22:51 - 23:21)

#### 22:51:37 - Первая позиция
```
22:51:37 - ✅ [MARK] Subscribed to ZBTUSDT
22:51:42 - ✅ Added ZBTUSDT to tracked positions (total: 1)
```

#### 22:51:51 - Вторая позиция
```
22:51:51 - ✅ [MARK] Subscribed to ZRXUSDT
22:51:56 - ✅ Added ZRXUSDT to tracked positions (total: 2)
```

#### 22:52:07 - Третья позиция
```
22:52:07 - ✅ [MARK] Subscribed to SFPUSDT
22:52:11 - ✅ Added SFPUSDT to tracked positions (total: 3)
```

#### 22:52:19 - Четвёртая позиция
```
22:52:19 - ✅ [MARK] Subscribed to ALICEUSDT
22:52:23 - ✅ Added ALICEUSDT to tracked positions (total: 4)
```

#### 22:52:29 - Пятая позиция
```
22:52:29 - ✅ [MARK] Subscribed to WOOUSDT
22:52:33 - ✅ Added WOOUSDT to tracked positions (total: 5)
```

#### 23:05:13 - Шестая позиция
```
23:05:13 - ✅ [MARK] Subscribed to REZUSDT
23:05:19 - ✅ Added REZUSDT to tracked positions (total: 6)
```

#### 23:19:10 - Седьмая позиция
```
23:19:10 - ✅ [MARK] Subscribed to KAITOUSDT
23:19:15 - ✅ Added KAITOUSDT to tracked positions (total: 7)
```

**✅ Все 7 позиций подписаны и получают обновления**

---

### Фаза 2: Переподключения (22:46 - 23:21)

#### История переподключений Mark Price stream:
```
22:46:13 - [MARK] Reconnecting in 5s...
22:57:30 - [MARK] Reconnecting in 5s...
23:08:18 - [MARK] Reconnecting in 5s...
23:21:07 - [MARK] Reconnecting in 5s...  ← ПОСЛЕДНЕЕ переподключение
```

**Критически важно**: После каждого переподключения WebSocket сбрасывается.

---

### Фаза 3: КРИТИЧЕСКИЙ момент (23:21:07)

#### 23:21:07 - Mark Price stream отключился
```
23:21:07,467 - [MARK] Reconnecting in 5s...
```

**Что происходило ДО отключения:**
```
23:21:01 - position.update: KAITOUSDT, mark_price=1.16060000
23:21:02 - position.update: KAITOUSDT, mark_price=1.16070000
23:21:03 - position.update: KAITOUSDT, mark_price=1.16040539
23:21:04 - position.update: KAITOUSDT, mark_price=1.16090000
23:21:05 - position.update: KAITOUSDT, mark_price=1.16100000
23:21:06 - position.update: KAITOUSDT, mark_price=1.16060000
23:21:07 - position.update: KAITOUSDT, mark_price=1.16075647
```

Только KAITOUSDT получал обновления (последний подписанный символ).

#### 23:21:12 - Mark Price stream переподключился
```
23:21:12,468 - 🌐 [MARK] Connecting...
23:21:13,448 - ✅ [MARK] Connected
```

#### 23:21:13+ - ПРОБЛЕМА: Нет повторных подписок!
```
[НЕТ ЛОГОВ]
✗ Нет "Subscribed to ZBTUSDT"
✗ Нет "Subscribed to ZRXUSDT"
✗ Нет "Subscribed to SFPUSDT"
✗ Нет "Subscribed to ALICEUSDT"
✗ Нет "Subscribed to WOOUSDT"
✗ Нет "Subscribed to REZUSDT"
✗ Нет "Subscribed to KAITOUSDT"
```

**❌ После переподключения подписки НЕ были восстановлены!**

---

### Фаза 4: Последствия (23:21+ до сейчас)

#### Позиции в БД (проверка в 23:26:32):
```sql
  symbol   | current_price | seconds_since_update
-----------+---------------+----------------------
 KAITOUSDT |    1.16075647 |            85.607374  ← ~86 секунд назад
 REZUSDT   |    0.01041000 |            85.975045  ← ~86 секунд назад
 WOOUSDT   |    0.04145000 |            86.347748  ← ~86 секунд назад
 ALICEUSDT |    0.33043725 |            86.724610  ← ~86 секунд назад
 SFPUSDT   |    0.38195154 |            87.087771  ← ~87 секунд назад
 ZRXUSDT   |    0.19740000 |            87.458001  ← ~87 секунд назад
 ZBTUSDT   |    0.27110000 |            87.833999  ← ~88 секунд назад
```

**Все позиции "замороженные" в последней цене перед 23:21:07!**

#### Trailing Stop Manager:
```
TS symbols in memory: ['ZBTUSDT', 'ZRXUSDT', 'SFPUSDT', 'ALICEUSDT', 'WOOUSDT', 'REZUSDT', 'KAITOUSDT']
```

**TS Manager ждёт обновлений, но они не приходят!**

---

## 🐛 Root Cause Analysis

### Найденная проблема в коде

**Файл**: `websocket/binance_hybrid_stream.py`
**Метод**: `async def _run_mark_stream()` (строки 383-446)

#### Проблемный код:
```python
async def _run_mark_stream(self):
    """Run Mark Price Stream (combined stream for all subscribed symbols)"""
    reconnect_delay = 5

    while self.running:
        try:
            # Binance combined streams use /stream endpoint
            url = f"{self.mark_ws_url}/stream"

            logger.info("🌐 [MARK] Connecting...")

            # Create session if needed
            if not self.mark_session or self.mark_session.closed:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                self.mark_session = aiohttp.ClientSession(timeout=timeout)

            # Connect
            self.mark_ws = await self.mark_session.ws_connect(
                url,
                heartbeat=None,
                autoping=False,
                autoclose=False
            )

            self.mark_connected = True
            logger.info("✅ [MARK] Connected")

            # Reset reconnect delay
            reconnect_delay = 5

            # ❌ ПРОБЛЕМА: НЕТ ВОССТАНОВЛЕНИЯ ПОДПИСОК!
            # После переподключения подписки не восстанавливаются

            # Receive loop
            async for msg in self.mark_ws:
                # ... обработка сообщений
```

### Почему это критично

1. **WebSocket - stateless соединение**: После переподключения сервер "забывает" все подписки
2. **subscribed_symbols хранит список**: Список есть в памяти, но не отправляется на сервер
3. **subscription_queue не автоматически повторяет**: Очередь обрабатывает только новые запросы

### Сравнение с working Bybit implementation

Нужно проверить как Bybit Hybrid восстанавливает подписки после reconnect.

---

## 💥 Воздействие на систему

### Критические последствия:

1. **Trailing Stop НЕ работает**
   - TS Manager не получает обновления mark_price
   - Stop Loss не обновляется
   - Позиции не защищены от потерь

2. **Aged Position Monitor НЕ работает**
   - Использует current_price для расчётов
   - "Замороженная" цена даёт неправильный PnL
   - Может закрыть позиции по неверным данным

3. **Position Manager в "слепую" зону**
   - unrealized_pnl не обновляется
   - Невозможно принимать решения
   - Позиции "живут" с устаревшими данными

4. **Финансовые риски**
   - Без обновления Stop Loss позиции могут уйти глубже в минус
   - Trailing Stop не "тянет" стоп за ценой
   - Рынок может развернуться против позиций

### Затронутые позиции:
```
ZBTUSDT   - $5.95  (short, -0.22 USDT unrealized PnL)
ZRXUSDT   - $5.98  (short, -0.23 USDT unrealized PnL)
SFPUSDT   - $5.73  (short, -0.15 USDT unrealized PnL)
ALICEUSDT - $5.97  (short, -1.74 USDT unrealized PnL)
WOOUSDT   - $5.97  (short, 0.00 USDT unrealized PnL)
REZUSDT   - $6.00  (long,  0.00 USDT unrealized PnL)

Итого: ~$35.60 USD в зоне риска
```

---

## 🔧 Plan исправления

### Этап 1: Код-аудит (✅ COMPLETED)

- [x] Исследовать логи последнего запуска
- [x] Найти момент отказа (23:21:07)
- [x] Идентифицировать root cause (нет восстановления подписок)
- [x] Проверить состояние БД и позиций
- [x] Проверить TS Manager state

### Этап 2: Дизайн решения

#### Решение A: Resubscribe после reconnect (РЕКОМЕНДУЕТСЯ)

**Добавить восстановление подписок после переподключения:**

```python
async def _run_mark_stream(self):
    """Run Mark Price Stream (combined stream for all subscribed symbols)"""
    reconnect_delay = 5

    while self.running:
        try:
            # ... код подключения ...

            self.mark_connected = True
            logger.info("✅ [MARK] Connected")

            # ✅ FIX: Восстановить подписки после переподключения
            await self._restore_subscriptions()

            # Reset reconnect delay
            reconnect_delay = 5

            # Receive loop
            async for msg in self.mark_ws:
                # ... обработка сообщений
```

**Новый метод:**
```python
async def _restore_subscriptions(self):
    """Restore all subscriptions after reconnect"""
    if not self.subscribed_symbols:
        logger.debug("[MARK] No subscriptions to restore")
        return

    logger.info(f"🔄 [MARK] Restoring {len(self.subscribed_symbols)} subscriptions...")

    for symbol in list(self.subscribed_symbols):
        try:
            # Temporarily remove from set to allow resubscribe
            self.subscribed_symbols.discard(symbol)

            # Resubscribe
            await self._subscribe_mark_price(symbol)

            # Small delay to avoid rate limits
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Failed to restore subscription for {symbol}: {e}")

    logger.info(f"✅ [MARK] Restored {len(self.subscribed_symbols)} subscriptions")
```

**Преимущества:**
- ✅ Простое решение
- ✅ Не требует изменения архитектуры
- ✅ Гарантирует восстановление
- ✅ Логирование для мониторинга

**Риски:**
- ⚠️ Короткая задержка при переподключении (~0.7s для 7 символов)
- ⚠️ Нужно проверить rate limits Binance

#### Решение B: Keep-alive with ping (ДОПОЛНИТЕЛЬНО)

**Уменьшить частоту переподключений:**

```python
# В _run_mark_stream добавить heartbeat
self.mark_ws = await self.mark_session.ws_connect(
    url,
    heartbeat=20,  # Ping каждые 20 секунд
    autoping=True,  # Автоматический pong
    autoclose=False
)
```

**Преимущества:**
- ✅ Меньше переподключений
- ✅ Стабильнее соединение

**Но**:
- ❌ НЕ решает проблему восстановления
- ❌ Только уменьшает частоту

#### Решение C: Subscription state tracking (OVER-ENGINEERING)

Хранить состояние подписок в отдельном менеджере. **НЕ РЕКОМЕНДУЕТСЯ** для текущей проблемы.

---

### Этап 3: Реализация (РЕКОМЕНДУЕМЫЙ ПЛАН)

#### Шаг 3.1: Добавить метод _restore_subscriptions

**Файл**: `websocket/binance_hybrid_stream.py`

**Где вставить**: После метода `_subscribe_mark_price()` (около строки 545)

**Код**:
```python
async def _restore_subscriptions(self):
    """Restore all mark price subscriptions after reconnect"""
    if not self.subscribed_symbols:
        logger.debug("[MARK] No subscriptions to restore")
        return

    symbols_to_restore = list(self.subscribed_symbols)
    logger.info(f"🔄 [MARK] Restoring {len(symbols_to_restore)} subscriptions...")

    # Clear subscribed set to allow resubscribe
    self.subscribed_symbols.clear()

    restored = 0
    for symbol in symbols_to_restore:
        try:
            await self._subscribe_mark_price(symbol)
            restored += 1

            # Small delay to avoid overwhelming the connection
            if restored < len(symbols_to_restore):
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"❌ [MARK] Failed to restore subscription for {symbol}: {e}")

    logger.info(f"✅ [MARK] Restored {restored}/{len(symbols_to_restore)} subscriptions")
```

#### Шаг 3.2: Вызвать _restore_subscriptions после переподключения

**Файл**: `websocket/binance_hybrid_stream.py`
**Метод**: `_run_mark_stream()`
**Строка**: ~408 (после `logger.info("✅ [MARK] Connected")`)

**Изменение**:
```python
# БЫЛО:
self.mark_connected = True
logger.info("✅ [MARK] Connected")

# Reset reconnect delay
reconnect_delay = 5

# СТАЛО:
self.mark_connected = True
logger.info("✅ [MARK] Connected")

# Restore subscriptions after reconnect
await self._restore_subscriptions()

# Reset reconnect delay
reconnect_delay = 5
```

#### Шаг 3.3: (Опционально) Добавить heartbeat

**Файл**: `websocket/binance_hybrid_stream.py`
**Метод**: `_run_mark_stream()`
**Строка**: ~400

**Изменение**:
```python
# БЫЛО:
self.mark_ws = await self.mark_session.ws_connect(
    url,
    heartbeat=None,
    autoping=False,
    autoclose=False
)

# СТАЛО (если хотим стабильнее соединение):
self.mark_ws = await self.mark_session.ws_connect(
    url,
    heartbeat=20,      # Ping каждые 20s
    autoping=True,     # Автоматический pong
    autoclose=False
)
```

---

### Этап 4: Тестирование

#### Тест 4.1: Unit test для _restore_subscriptions

**Файл**: Новый `tests/unit/test_binance_hybrid_reconnect.py`

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from websocket.binance_hybrid_stream import BinanceHybridStream


class TestReconnectLogic:
    """Test subscription restoration after reconnect"""

    @pytest.mark.asyncio
    async def test_restore_subscriptions_empty(self):
        """Test restoration with no subscriptions"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # No subscriptions
        stream.subscribed_symbols = set()

        # Should not raise error
        await stream._restore_subscriptions()

        assert len(stream.subscribed_symbols) == 0

    @pytest.mark.asyncio
    async def test_restore_subscriptions_single(self):
        """Test restoration with one subscription"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Mock subscribe method
        stream._subscribe_mark_price = AsyncMock()

        # Add one subscription
        stream.subscribed_symbols = {'BTCUSDT'}

        # Restore
        await stream._restore_subscriptions()

        # Verify resubscribed
        stream._subscribe_mark_price.assert_called_once_with('BTCUSDT')
        assert 'BTCUSDT' in stream.subscribed_symbols

    @pytest.mark.asyncio
    async def test_restore_subscriptions_multiple(self):
        """Test restoration with multiple subscriptions"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Mock subscribe method
        stream._subscribe_mark_price = AsyncMock()

        # Add multiple subscriptions
        symbols = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT'}
        stream.subscribed_symbols = symbols.copy()

        # Restore
        await stream._restore_subscriptions()

        # Verify all resubscribed
        assert stream._subscribe_mark_price.call_count == 3
        assert len(stream.subscribed_symbols) == 3

    @pytest.mark.asyncio
    async def test_restore_subscriptions_with_error(self):
        """Test restoration handles errors gracefully"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Mock subscribe method to fail on second symbol
        call_count = 0
        async def mock_subscribe(symbol):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Connection error")

        stream._subscribe_mark_price = mock_subscribe

        # Add multiple subscriptions
        stream.subscribed_symbols = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT'}

        # Restore (should not raise)
        await stream._restore_subscriptions()

        # Should have attempted all 3
        assert call_count == 3
```

#### Тест 4.2: Integration test - симуляция reconnect

**Файл**: `tests/integration/test_binance_hybrid_reconnect.py`

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from websocket.binance_hybrid_stream import BinanceHybridStream


@pytest.mark.asyncio
async def test_reconnect_restores_subscriptions():
    """Test that subscriptions are restored after reconnect"""
    stream = BinanceHybridStream("key", "secret", testnet=True)

    subscribed_symbols = []

    # Mock _subscribe_mark_price to track calls
    async def mock_subscribe(symbol):
        subscribed_symbols.append(symbol)
        stream.subscribed_symbols.add(symbol)

    stream._subscribe_mark_price = mock_subscribe

    # Simulate initial subscriptions
    await stream._request_mark_subscription('BTCUSDT', subscribe=True)
    await stream._request_mark_subscription('ETHUSDT', subscribe=True)
    await asyncio.sleep(0.2)  # Wait for subscription_manager

    assert len(stream.subscribed_symbols) == 2
    initial_count = len(subscribed_symbols)

    # Simulate reconnect
    await stream._restore_subscriptions()

    # Verify resubscribed
    assert len(subscribed_symbols) == initial_count + 2
    assert 'BTCUSDT' in stream.subscribed_symbols
    assert 'ETHUSDT' in stream.subscribed_symbols
```

#### Тест 4.3: Manual test - реальное переподключение

**Файл**: `tests/manual/test_binance_hybrid_reconnect.py`

```python
"""
Manual test to verify reconnection logic
Artificially closes Mark WS and verifies restoration

Usage:
    BINANCE_API_KEY=xxx BINANCE_API_SECRET=yyy python tests/manual/test_binance_hybrid_reconnect.py
"""

import asyncio
import os
import logging
from websocket.binance_hybrid_stream import BinanceHybridStream

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_reconnect():
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        logger.error("Credentials required")
        return

    events = []

    async def handler(event_type, data):
        events.append((event_type, data))
        logger.info(f"Event: {event_type} | {data.get('symbol')} | {data.get('mark_price')}")

    stream = BinanceHybridStream(api_key, api_secret, handler, testnet=False)

    # Start
    await stream.start()
    await asyncio.sleep(5)

    logger.info("=" * 80)
    logger.info("Phase 1: Initial subscriptions (simulating positions)")
    logger.info("=" * 80)

    # Simulate position opens (trigger subscriptions)
    stream.positions['BTCUSDT'] = {'symbol': 'BTCUSDT', 'side': 'LONG'}
    await stream._request_mark_subscription('BTCUSDT', subscribe=True)
    await asyncio.sleep(2)

    stream.positions['ETHUSDT'] = {'symbol': 'ETHUSDT', 'side': 'LONG'}
    await stream._request_mark_subscription('ETHUSDT', subscribe=True)
    await asyncio.sleep(2)

    logger.info(f"Subscribed symbols: {stream.subscribed_symbols}")
    logger.info(f"Events received: {len(events)}")

    initial_event_count = len(events)

    logger.info("=" * 80)
    logger.info("Phase 2: Force reconnect (close Mark WebSocket)")
    logger.info("=" * 80)

    # Force close Mark WS to simulate reconnect
    if stream.mark_ws:
        await stream.mark_ws.close()
        logger.info("✅ Closed Mark WebSocket")

    # Wait for automatic reconnect
    await asyncio.sleep(10)

    logger.info(f"Mark connected: {stream.mark_connected}")
    logger.info(f"Subscribed symbols after reconnect: {stream.subscribed_symbols}")

    logger.info("=" * 80)
    logger.info("Phase 3: Verify events are flowing again")
    logger.info("=" * 80)

    # Wait for events
    await asyncio.sleep(10)

    new_events = len(events) - initial_event_count
    logger.info(f"New events after reconnect: {new_events}")

    # Stop
    await stream.stop()

    # Summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total events: {len(events)}")
    logger.info(f"Events after reconnect: {new_events}")

    if new_events > 0:
        logger.info("✅ TEST PASSED - Events flowing after reconnect")
    else:
        logger.error("❌ TEST FAILED - No events after reconnect")


if __name__ == '__main__':
    asyncio.run(test_reconnect())
```

---

### Этап 5: Deployment

#### 5.1 Pre-deployment checklist
- [ ] Код исправлен (`_restore_subscriptions` добавлен)
- [ ] Вызов в `_run_mark_stream` добавлен
- [ ] Unit tests пройдены
- [ ] Integration tests пройдены
- [ ] Manual reconnect test пройден
- [ ] Code review completed
- [ ] Git commit создан

#### 5.2 Deployment steps
1. Остановить бота
2. Применить изменения
3. Запустить manual reconnect test
4. Запустить бота
5. Мониторить логи 30 минут

#### 5.3 Rollback plan
- Backup: Текущий код сохранён в Git
- Rollback: `git revert HEAD`
- Restart bot

---

### Этап 6: Мониторинг после деплоя

#### Метрики для отслеживания:

1. **Mark Price reconnects**:
   ```bash
   grep "MARK.*Reconnecting" logs/trading_bot.log | tail -10
   ```

2. **Subscription restorations**:
   ```bash
   grep "Restoring.*subscriptions" logs/trading_bot.log | tail -10
   ```

3. **Position updates frequency**:
   ```sql
   SELECT symbol,
          COUNT(*) as updates,
          MAX(updated_at) as last_update,
          EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) as seconds_ago
   FROM monitoring.positions
   WHERE exchange = 'binance' AND status = 'active'
   GROUP BY symbol;
   ```

4. **Trailing Stop activity**:
   ```bash
   grep "TS_DEBUG.*binance" logs/trading_bot.log | tail -20
   ```

#### Ожидаемое поведение после фикса:

```
23:45:30 - [MARK] Reconnecting in 5s...
23:45:35 - 🌐 [MARK] Connecting...
23:45:36 - ✅ [MARK] Connected
23:45:36 - 🔄 [MARK] Restoring 7 subscriptions...
23:45:36 - ✅ [MARK] Subscribed to ZBTUSDT
23:45:36 - ✅ [MARK] Subscribed to ZRXUSDT
23:45:36 - ✅ [MARK] Subscribed to SFPUSDT
23:45:37 - ✅ [MARK] Subscribed to ALICEUSDT
23:45:37 - ✅ [MARK] Subscribed to WOOUSDT
23:45:37 - ✅ [MARK] Subscribed to REZUSDT
23:45:37 - ✅ [MARK] Subscribed to KAITOUSDT
23:45:37 - ✅ [MARK] Restored 7/7 subscriptions
23:45:38 - position.update: ZBTUSDT, mark_price=0.27120000
23:45:38 - position.update: ZRXUSDT, mark_price=0.19750000
```

---

## 📋 Summary

### Проблема
После переподключения Mark Price WebSocket, подписки не восстанавливаются автоматически, что приводит к остановке обновлений mark_price для всех позиций кроме одной.

### Root Cause
Метод `_run_mark_stream()` не содержит логики восстановления подписок после reconnect.

### Solution
Добавить метод `_restore_subscriptions()` и вызывать его после каждого успешного переподключения Mark Price stream.

### Impact
- 🔴 **КРИТИЧНО**: Без фикса Trailing Stop НЕ работает
- 🟡 **ВЫСОКИЙ РИСК**: Позиции не защищены
- 🟢 **РЕШАЕТСЯ**: Простое изменение кода

### Effort
- Development: 30 минут
- Testing: 1 час
- Deployment: 15 минут
- Total: ~2 часа

---

**Статус**: READY FOR IMPLEMENTATION
**Приоритет**: 🔴 КРИТИЧЕСКИЙ
**Assigned to**: Developer
**Deadline**: ASAP
