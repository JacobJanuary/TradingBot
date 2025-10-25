# 🛠️ Bybit Public WebSocket Fix - Implementation Plan

**Дата**: 2025-10-25 23:50
**Проблема**: Public WebSocket не подписывается на позиции при старте бота
**Решение**: Добавить метод `sync_positions()` для проактивной инициализации подписок

---

## 📋 План реализации

### Шаг 1: Добавить метод `sync_positions()` в Bybit Hybrid Stream

**Файл**: `websocket/bybit_hybrid_stream.py`

**Где добавить**: После метода `stop()` (после строки ~162)

**Код для добавления**:

```python
    async def sync_positions(self, positions: list):
        """
        Sync existing positions with WebSocket subscriptions

        Called after loading positions from DB to ensure
        Public WS subscribes to all active positions.

        This fixes the cold start problem where positions exist
        but Private WS doesn't send snapshot, so Public WS never
        subscribes to tickers.

        Args:
            positions: List of position dicts with 'symbol' key
        """
        if not positions:
            logger.debug("No positions to sync")
            return

        logger.info(f"🔄 Syncing {len(positions)} positions with WebSocket...")

        synced = 0
        for position in positions:
            symbol = position.get('symbol')
            if not symbol:
                logger.warning(f"Position missing symbol: {position}")
                continue

            try:
                # Store position data (minimal set for ticker subscription)
                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': position.get('side', 'Buy'),
                    'size': str(position.get('quantity', 0)),
                    'entry_price': str(position.get('entry_price', 0)),
                    'mark_price': str(position.get('current_price', 0)),
                }

                # Request ticker subscription
                await self._request_ticker_subscription(symbol, subscribe=True)
                synced += 1

                # Small delay to avoid overwhelming the connection
                if synced < len(positions):
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to sync position {symbol}: {e}")

        logger.info(f"✅ Synced {synced}/{len(positions)} positions with WebSocket")
```

**Важно**:
- Метод должен быть **public** (без underscore)
- Добавляется после `stop()` для логичного порядка
- Использует существующий `_request_ticker_subscription()` для подписок

---

### Шаг 2: Вызвать `sync_positions()` в main.py

**Файл**: `main.py`

**Где добавить**: После `await self.position_manager.load_positions_from_db()` (после строки ~294)

**Найти этот блок**:

```python
            # Load existing positions from database
            logger.info("Loading positions from database...")
            await self.position_manager.load_positions_from_db()
```

**Добавить СРАЗУ после него**:

```python
            # Load existing positions from database
            logger.info("Loading positions from database...")
            await self.position_manager.load_positions_from_db()

            # CRITICAL FIX: Sync positions with Bybit Hybrid WebSocket
            # Private WS may not send position snapshot on startup,
            # so we need to explicitly subscribe to tickers for existing positions
            bybit_ws = self.websockets.get('bybit_hybrid')
            if bybit_ws:
                # Get active Bybit positions
                bybit_positions = [
                    p for p in self.position_manager.positions.values()
                    if p.get('exchange') == 'bybit' and p.get('status') == 'active'
                ]

                if bybit_positions:
                    logger.info(f"🔄 Syncing {len(bybit_positions)} Bybit positions with WebSocket...")
                    try:
                        await bybit_ws.sync_positions(bybit_positions)
                        logger.info(f"✅ Bybit WebSocket synced with {len(bybit_positions)} positions")
                    except Exception as e:
                        logger.error(f"Failed to sync Bybit positions: {e}")
                else:
                    logger.info("No active Bybit positions to sync")
```

**Важно**:
- Проверяем что `bybit_ws` существует
- Фильтруем только Bybit позиции со статусом 'active'
- Обрабатываем ошибки gracefully
- Добавляем логирование для диагностики

---

## 🧪 Тесты

### Unit Test 1: test_sync_positions_empty

**Файл**: `tests/unit/test_bybit_hybrid_sync.py` (новый файл)

```python
"""
Unit tests for Bybit Hybrid Stream position sync
Tests sync_positions() method for cold start scenarios
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from websocket.bybit_hybrid_stream import BybitHybridStream


class TestPositionSync:
    """Test position synchronization on startup"""

    @pytest.mark.asyncio
    async def test_sync_positions_empty(self):
        """Test sync with no positions"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Should not raise error with empty list
        await stream.sync_positions([])

        # No subscriptions should be created
        assert len(stream.positions) == 0
        assert len(stream.subscribed_tickers) == 0

    @pytest.mark.asyncio
    async def test_sync_positions_single(self):
        """Test sync with one position"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription request
        stream._request_ticker_subscription = AsyncMock()

        # Sync one position
        positions = [
            {'symbol': 'BTCUSDT', 'side': 'Buy', 'quantity': 1.0, 'entry_price': 50000}
        ]
        await stream.sync_positions(positions)

        # Verify subscription requested
        stream._request_ticker_subscription.assert_called_once_with('BTCUSDT', subscribe=True)

        # Verify position stored
        assert 'BTCUSDT' in stream.positions
        assert stream.positions['BTCUSDT']['symbol'] == 'BTCUSDT'

    @pytest.mark.asyncio
    async def test_sync_positions_multiple(self):
        """Test sync with multiple positions"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription request
        stream._request_ticker_subscription = AsyncMock()

        # Sync 5 positions
        positions = [
            {'symbol': f'SYM{i}USDT', 'side': 'Buy', 'quantity': 1.0, 'entry_price': 100}
            for i in range(5)
        ]
        await stream.sync_positions(positions)

        # Verify all subscriptions requested
        assert stream._request_ticker_subscription.call_count == 5

        # Verify all positions stored
        assert len(stream.positions) == 5
        for i in range(5):
            assert f'SYM{i}USDT' in stream.positions

    @pytest.mark.asyncio
    async def test_sync_positions_missing_symbol(self):
        """Test sync handles positions without symbol gracefully"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription request
        stream._request_ticker_subscription = AsyncMock()

        # Sync with one invalid position
        positions = [
            {'side': 'Buy', 'quantity': 1.0},  # Missing symbol!
            {'symbol': 'ETHUSDT', 'side': 'Buy', 'quantity': 2.0}
        ]
        await stream.sync_positions(positions)

        # Should only subscribe to valid position
        stream._request_ticker_subscription.assert_called_once_with('ETHUSDT', subscribe=True)
        assert len(stream.positions) == 1
        assert 'ETHUSDT' in stream.positions

    @pytest.mark.asyncio
    async def test_sync_positions_subscription_error(self):
        """Test sync handles subscription errors gracefully"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription to fail on second position
        call_count = 0
        async def mock_request_sub(symbol, subscribe):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Connection error")

        stream._request_ticker_subscription = mock_request_sub

        # Sync 3 positions
        positions = [
            {'symbol': 'SYM1USDT', 'side': 'Buy', 'quantity': 1.0},
            {'symbol': 'SYM2USDT', 'side': 'Buy', 'quantity': 1.0},
            {'symbol': 'SYM3USDT', 'side': 'Buy', 'quantity': 1.0}
        ]

        # Should not raise
        await stream.sync_positions(positions)

        # Should have attempted all 3
        assert call_count == 3

        # All positions should be stored (subscription failure doesn't prevent storage)
        assert len(stream.positions) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

---

### Manual Test: Startup Sync

**Файл**: `tests/manual/test_bybit_startup_sync.py` (новый файл)

```python
"""
Manual test to verify position sync on startup

Prerequisites:
- Active Bybit positions on exchange
- Bot stopped

Test:
1. Start bot
2. Verify Public WS subscribes to all positions
3. Verify mark_price updates flow

Usage:
    python tests/manual/test_bybit_startup_sync.py
"""

import asyncio
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_startup_sync():
    """Test position sync on startup"""

    logger.info("=" * 80)
    logger.info("🧪 BYBIT STARTUP SYNC TEST")
    logger.info("=" * 80)

    # Check logs for expected messages
    logger.info("\n📋 After starting the bot, check logs for:")
    logger.info("  1. ✅ [PUBLIC] Connected")
    logger.info("  2. 🔄 Syncing X positions with WebSocket...")
    logger.info("  3. ✅ [PUBLIC] Subscribed to SYMBOL (for each position)")
    logger.info("  4. ✅ Synced X positions with WebSocket")
    logger.info("  5. 💰 [PUBLIC] Price update: SYMBOL @ $X.XX")

    logger.info("\n📝 Manual verification steps:")
    logger.info("  1. Stop the bot: pkill -f 'python main.py'")
    logger.info("  2. Start the bot: python main.py")
    logger.info("  3. Watch logs: tail -f logs/trading_bot.log | grep -E '(PUBLIC|Syncing|Synced)'")
    logger.info("  4. Verify all active Bybit positions get subscriptions")
    logger.info("  5. Wait 5 seconds, verify mark_price updates flowing")

    logger.info("\n🎯 Success criteria:")
    logger.info("  - All active positions subscribed on startup")
    logger.info("  - Mark price updates arrive within 5 seconds")
    logger.info("  - No errors in subscription process")

    logger.info("\n" + "=" * 80)


if __name__ == '__main__':
    asyncio.run(test_startup_sync())
```

---

## 🔍 Проверка правильности изменений

### Шаг 1: Проверить что метод добавлен корректно

```bash
# Проверить что метод существует
grep -n "async def sync_positions" websocket/bybit_hybrid_stream.py

# Должен вернуть номер строки, например:
# 164:    async def sync_positions(self, positions: list):
```

### Шаг 2: Проверить что вызов добавлен в main.py

```bash
# Проверить что sync вызывается
grep -n "sync_positions" main.py

# Должен вернуть строку с вызовом, например:
# 310:                        await bybit_ws.sync_positions(bybit_positions)
```

### Шаг 3: Запустить unit tests

```bash
pytest tests/unit/test_bybit_hybrid_sync.py -v
```

**Ожидаемый результат**:
```
test_sync_positions_empty PASSED
test_sync_positions_single PASSED
test_sync_positions_multiple PASSED
test_sync_positions_missing_symbol PASSED
test_sync_positions_subscription_error PASSED
```

---

## 📦 Git Commits

### Commit 1: Основное исправление

```bash
git add websocket/bybit_hybrid_stream.py main.py
git commit -m "fix(bybit): add sync_positions() for cold start subscriptions

Problem: Public WebSocket doesn't subscribe to tickers on startup
because Private WS may not send position snapshot immediately.

Solution:
- Add sync_positions() method to BybitHybridStream
- Call it from main.py after loading positions from DB
- Explicitly subscribe to tickers for all active Bybit positions

This ensures mark_price updates flow immediately on startup,
enabling Trailing Stop protection for all positions.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Commit 2: Тесты

```bash
git add tests/unit/test_bybit_hybrid_sync.py tests/manual/test_bybit_startup_sync.py
git commit -m "test(bybit): add sync_positions() tests

- 5 unit tests for position sync on startup
- Manual test guide for verification
- Tests cover: empty, single, multiple, errors

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Commit 3: Документация

```bash
git add FORENSIC_BYBIT_PUBLIC_WS_BUG.md BYBIT_PUBLIC_WS_FIX_PLAN.md
git commit -m "docs: forensic investigation - Bybit Public WS bug

Root cause: Reactive subscription model doesn't handle cold starts
Solution: Proactive sync_positions() on startup

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 🚀 Deployment Steps

### Pre-deployment:

1. **Остановить бота**:
   ```bash
   pkill -f "python main.py"
   ps aux | grep "python main.py"  # Verify stopped
   ```

2. **Проверить текущее состояние**:
   ```bash
   # Check active Bybit positions in DB
   PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "
   SELECT symbol, exchange, status, quantity, current_price, updated_at
   FROM monitoring.positions
   WHERE exchange = 'bybit' AND status = 'active'
   ORDER BY symbol;
   "
   ```

### Deployment:

3. **Применить изменения** (уже применены в коде):
   ```bash
   # Changes already in working directory
   git status  # Should show modified files
   ```

4. **Запустить тесты**:
   ```bash
   pytest tests/unit/test_bybit_hybrid_sync.py -v
   ```

5. **Запустить бота**:
   ```bash
   python main.py > /tmp/bot_startup.log 2>&1 &
   echo $!  # Note PID
   ```

### Post-deployment verification:

6. **Проверить startup логи**:
   ```bash
   tail -100 logs/trading_bot.log | grep -E "(Syncing|PUBLIC.*Subscribed|Synced)"
   ```

   **Ожидаемое**:
   ```
   23:XX:XX - 🔄 Syncing 15 positions with WebSocket...
   23:XX:XX - ✅ [PUBLIC] Subscribed to ONEUSDT
   23:XX:XX - ✅ [PUBLIC] Subscribed to BABYUSDT
   ... (x15)
   23:XX:XX - ✅ Synced 15 positions with WebSocket
   ```

7. **Проверить mark_price updates**:
   ```bash
   tail -f logs/trading_bot.log | grep "PUBLIC.*Price update"
   ```

   **Ожидаемое** (в течение 5 секунд):
   ```
   23:XX:XX - 💰 [PUBLIC] Price update: ONEUSDT @ $0.00662
   23:XX:XX - 💰 [PUBLIC] Price update: BABYUSDT @ $0.032
   ```

8. **Проверить Trailing Stop активность**:
   ```bash
   tail -f logs/trading_bot.log | grep "TS_DEBUG.*bybit"
   ```

   **Ожидаемое**: Регулярные обновления для позиций в профите

---

## 🎯 Success Criteria

### Обязательные:

- [x] Метод `sync_positions()` добавлен в `bybit_hybrid_stream.py`
- [x] Вызов добавлен в `main.py` после `load_positions_from_db()`
- [ ] 5/5 unit tests проходят
- [ ] При старте бота логи показывают "🔄 Syncing X positions..."
- [ ] При старте бота логи показывают "✅ [PUBLIC] Subscribed to..." для каждой позиции
- [ ] Mark price updates приходят в течение 5 секунд после старта
- [ ] Trailing Stop работает для всех позиций

### Дополнительные:

- [ ] Нет ошибок в логах при синхронизации
- [ ] При reconnect Public WS восстанавливает подписки (существующая логика)
- [ ] При открытии новой позиции подписка создаётся (существующая логика)
- [ ] При закрытии позиции подписка удаляется (существующая логика)

---

## 🔴 Rollback Plan

Если что-то пойдёт не так:

```bash
# 1. Остановить бота
pkill -f "python main.py"

# 2. Откатить изменения
git diff HEAD  # Review changes
git checkout -- websocket/bybit_hybrid_stream.py main.py

# 3. Перезапустить
python main.py
```

**Backup commit**: Текущий HEAD (перед изменениями)

---

## 📊 Метрики

| Метрика | Значение |
|---------|----------|
| Файлов изменено | 2 (core) + 2 (tests) |
| Строк кода добавлено | ~50 |
| Строк тестов добавлено | ~140 |
| Unit tests | 5 |
| Manual tests | 1 |
| Риск изменений | Низкий |
| Сложность | Средняя |
| Время реализации | ~30 минут |

---

## 🎓 Lessons Learned

### Проблема:
**Reactive architecture** не подходит для **stateful systems** где состояние может существовать до подключения к event stream.

### Решение:
При подключении к event-driven системе нужно:
1. Подключиться к stream
2. Загрузить существующее состояние
3. **Синхронизировать** stream с состоянием
4. Начать получать updates

### Применимо к:
- WebSocket subscriptions
- Event listeners
- Database change streams
- Message queues

---

**Status**: ✅ Ready for Implementation
**Next**: Implement according to plan
