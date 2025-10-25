# 🔴 CRITICAL BUG: Bybit Public WebSocket не получает обновления цены

**Дата**: 2025-10-25 23:45
**Статус**: 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА
**Приоритет**: P0 - Блокирует Trailing Stop

---

## 📊 Симптомы

### Что происходит:
- ✅ Private WebSocket **работает** (получены уведомления о срабатывании SL)
- ❌ Public WebSocket **НЕ работает** (НЕТ обновлений mark_price)
- ❌ Trailing Stop **НЕ работает** (нет price updates)
- ❌ 15 позиций Bybit **без защиты**

### Логи показывают:
```
23:42:26 - ✅ [PUBLIC] Connected
23:42:29 - 📊 Loaded 7 positions from database
         - ❌ НЕТ логов подписок на тикеры!
         - ❌ НЕТ логов "[PUBLIC] Subscribed to..."
         - ❌ НЕТ обновлений mark_price
```

---

## 🔍 Root Cause Analysis

### Архитектура Bybit Hybrid Stream

Система использует **REACTIVE** подход:

```
Private WS получает position update
    ↓
Вызывается _on_position_update()
    ↓
Вызывается _request_ticker_subscription()
    ↓
Добавляется в subscription_queue
    ↓
_subscription_manager обрабатывает
    ↓
Вызывается _subscribe_ticker()
    ↓
Отправляется subscribe message в Public WS
    ↓
subscribed_tickers.add(symbol)
```

### Проблема

**При старте бота**:

1. **15:44:02.395** - Bybit Hybrid WebSocket стартует
2. **15:44:02.409** - Public WS подключается
3. **15:44:02.409** - Вызывается `_restore_ticker_subscriptions()`
4. **ПРОБЛЕМА**: `subscribed_tickers` **ПУСТОЙ**!
   ```python
   async def _restore_ticker_subscriptions(self):
       if not self.subscribed_tickers:  # ← TRUE!
           return  # ← ВЫХОДИТ БЕЗ ВОССТАНОВЛЕНИЯ
   ```
5. **15:44:10.510** - Позиции загружаются из БД (ПОСЛЕ подключения WS)
6. **15:44:10.510+** - Private WS подключается и...
7. **ПРОБЛЕМА**: Private WS **НЕ ОТПРАВЛЯЕТ snapshot** если позиции не изменяются!
8. **Результат**: `_on_position_update()` **НЕ ВЫЗЫВАЕТСЯ**
9. **Результат**: `_subscribe_ticker()` **НЕ ВЫЗЫВАЕТСЯ**
10. **Результат**: **НЕТ ПОДПИСОК НА ТИКЕРЫ**

---

## 🧬 Timeline - Хронология событий

### Startup Sequence (из логов):

```
15:44:02.395  🚀 Starting Bybit Hybrid WebSocket...
              ✅ Bybit Hybrid WebSocket started

15:44:02.404  🔐 [PRIVATE] Connecting...
15:44:02.409  🌐 [PUBLIC] Connecting...

15:44:03.353  ✅ [PRIVATE] Connected
15:44:03.354  [PRIVATE] Authentication sent
15:44:03.354  [PRIVATE] Subscribed to position topic

15:44:03.359  ✅ [PUBLIC] Connected
              ⚠️ _restore_ticker_subscriptions() вызван
              ⚠️ subscribed_tickers пустой → вышел без действий

15:44:03.591  ✅ [PRIVATE] Authenticated
15:44:03.591  ✅ [PRIVATE] Subscription confirmed

              ⚠️ Private WS НЕ отправил position snapshot!
              ⚠️ _on_position_update() НЕ вызвался!

15:44:10.510  📊 Loaded 15 positions from database
              💰 Total exposure: $280.58

              ⚠️ НО WebSocket УЖЕ подключен и НЕ знает о позициях!
```

### Runtime Behavior:

```
Позиции загружены в PositionManager: ✅
Позиции НЕ известны Bybit Hybrid Stream: ❌
subscribed_tickers остаётся пустым: ❌
Public WS подключен но НЕТ подписок: ❌
mark_price updates НЕ приходят: ❌
Trailing Stop НЕ может обновлять: ❌
```

---

## 🎯 Проблема в коде

### websocket/bybit_hybrid_stream.py:277-321

```python
async def _on_position_update(self, positions: list):
    """
    Handle position lifecycle updates

    Triggers:
    - Position opened (size > 0) → Subscribe to ticker
    - Position closed (size = 0) → Unsubscribe from ticker
    - Position modified → Update position data
    """
    for pos in positions:
        symbol = pos.get('symbol')
        size = float(pos.get('size', 0))

        logger.info(f"📊 [PRIVATE] Position update: {symbol} size={size}")

        if size > 0:
            # Position active - store and subscribe to ticker
            self.positions[symbol] = {...}

            # Request ticker subscription
            await self._request_ticker_subscription(symbol, subscribe=True)
            # ↑ ПРОБЛЕМА: Вызывается ТОЛЬКО при получении position update!
```

### Проблема:

**Реактивный подход**: Подписки создаются ТОЛЬКО когда Private WS отправляет position update.

**НО**: При старте бота Private WS **МОЖЕТ НЕ ОТПРАВИТЬ** snapshot если:
- Позиции не изменяются
- WebSocket только что подключился
- Нет новых событий

**Результат**: Позиции существуют в БД и на бирже, но Bybit Hybrid Stream **НЕ ЗНАЕТ** о них!

---

## 📐 Архитектурная проблема

### Текущая архитектура (BROKEN):

```
┌─────────────────┐
│   main.py       │
├─────────────────┤
│ 1. Start WS     │ ← WebSocket стартует
│ 2. Load from DB │ ← Позиции загружаются ПОЗЖЕ
└────────┬────────┘
         │
         ↓
┌────────────────────────┐
│  Bybit Hybrid Stream   │
├────────────────────────┤
│ Private WS: position   │ ← Ждёт updates от биржи
│ Public WS: tickers     │ ← НЕТ подписок!
│                        │
│ subscribed_tickers: [] │ ← ПУСТОЙ!
└────────────────────────┘
```

### Что нужно (FIX):

```
┌─────────────────┐
│   main.py       │
├─────────────────┤
│ 1. Start WS     │
│ 2. Load from DB │
│ 3. Sync WS ←──────┐  ← Новый шаг!
└─────────────────┘  │
                     │
                     ↓
┌────────────────────────┐
│  Bybit Hybrid Stream   │
├────────────────────────┤
│ + sync_positions()     │ ← Новый метод!
│   - Принимает список   │
│   - Подписывается на   │
│     каждый символ      │
└────────────────────────┘
```

---

## 💡 Решение

### Требуется добавить:

#### 1. Новый public метод в `BybitHybridStream`

```python
async def sync_positions(self, positions: list):
    """
    Sync existing positions with WebSocket subscriptions

    Called after loading positions from DB to ensure
    Public WS subscribes to all active positions

    Args:
        positions: List of position dicts with 'symbol' key
    """
    if not positions:
        return

    logger.info(f"🔄 Syncing {len(positions)} positions with WebSocket...")

    for position in positions:
        symbol = position.get('symbol')
        if not symbol:
            continue

        # Store position data
        self.positions[symbol] = {
            'symbol': symbol,
            'side': position.get('side'),
            'size': str(position.get('quantity', 0)),
            'entry_price': str(position.get('entry_price', 0)),
            'mark_price': str(position.get('current_price', 0)),
        }

        # Request ticker subscription
        await self._request_ticker_subscription(symbol, subscribe=True)

    logger.info(f"✅ Synced {len(positions)} positions")
```

#### 2. Вызов в `main.py` после загрузки позиций

```python
# Load existing positions from database
logger.info("Loading positions from database...")
await self.position_manager.load_positions_from_db()

# НОВЫЙ КОД: Sync positions with WebSocket
bybit_ws = self.websockets.get('bybit_hybrid')
if bybit_ws:
    # Get active Bybit positions
    bybit_positions = [
        p for p in self.position_manager.positions.values()
        if p.get('exchange') == 'bybit' and p.get('status') == 'active'
    ]

    if bybit_positions:
        logger.info(f"🔄 Syncing {len(bybit_positions)} Bybit positions with WebSocket...")
        await bybit_ws.sync_positions(bybit_positions)
```

---

## 🧪 План тестирования

### Unit Tests:

1. **test_sync_positions_empty**
   - Вызов с пустым списком
   - Не должен вызывать ошибок

2. **test_sync_positions_single**
   - Синхронизация 1 позиции
   - Проверка что подписка создана

3. **test_sync_positions_multiple**
   - Синхронизация 5+ позиций
   - Проверка всех подписок

4. **test_sync_positions_no_public_connection**
   - Вызов когда Public WS не подключен
   - Должен обработать gracefully

### Manual Test:

1. Создать 3 позиции на бирже
2. Остановить бота
3. Запустить бота
4. Проверить что Public WS подписался на все 3 символа
5. Проверить что mark_price updates приходят

---

## 📝 Implementation Checklist

### Код:
- [ ] Добавить `sync_positions()` в `bybit_hybrid_stream.py`
- [ ] Добавить вызов в `main.py` после `load_positions_from_db()`
- [ ] Добавить логирование для отладки

### Тесты:
- [ ] Unit tests (4 теста)
- [ ] Manual test (startup с существующими позициями)
- [ ] Проверить что не сломали существующую логику

### Git:
- [ ] Commit 1: Код исправления
- [ ] Commit 2: Тесты
- [ ] Commit 3: Документация

### Deploy:
- [ ] Остановить бота
- [ ] Применить исправление
- [ ] Запустить бота
- [ ] Проверить логи подписок
- [ ] Проверить что mark_price updates приходят

---

## 🎯 Success Criteria

После исправления логи должны показывать:

```
23:XX:XX - 🚀 Starting Bybit Hybrid WebSocket...
23:XX:XX - ✅ [PRIVATE] Connected
23:XX:XX - ✅ [PUBLIC] Connected
23:XX:XX - 📊 Loaded 15 positions from database
23:XX:XX - 🔄 Syncing 15 positions with WebSocket...    ← НОВЫЙ ЛОГ!
23:XX:XX - ✅ [PUBLIC] Subscribed to ONEUSDT              ← НОВЫЙ ЛОГ!
23:XX:XX - ✅ [PUBLIC] Subscribed to BABYUSDT             ← НОВЫЙ ЛОГ!
... (x15)
23:XX:XX - ✅ Synced 15 positions                         ← НОВЫЙ ЛОГ!
23:XX:XX - 💰 [PUBLIC] Price update: ONEUSDT @ $0.00662  ← РАБОТАЕТ!
23:XX:XX - 💰 [PUBLIC] Price update: BABYUSDT @ $0.032   ← РАБОТАЕТ!
```

---

## 🔴 Критичность

**Почему это P0**:
- 15 позиций Bybit **БЕЗ ЗАЩИТЫ** Trailing Stop
- $280.58 USD в зоне риска
- Private WS работает → видим SL срабатывания → значит биржа активна
- НО Public WS не работает → НЕТ mark_price → Trailing Stop НЕ обновляется
- Это может привести к **УПУЩЕННОЙ ПРИБЫЛИ** или **ИЗБЫТОЧНЫМ УБЫТКАМ**

---

**Prepared by**: Claude Code
**Investigation time**: 15 минут
**Lines analyzed**: 580+ строк кода
**Status**: Ready for implementation
