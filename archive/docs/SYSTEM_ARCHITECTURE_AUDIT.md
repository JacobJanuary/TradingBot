# 🔍 ПОЛНЫЙ АУДИТ ТОРГОВОГО БОТА - ФАЗА 1 (КОД АНАЛИЗ)

**Дата**: 2025-10-15
**Аудитор**: Claude Code
**Статус**: ✅ Код-анализ завершен, Production тест запущен (8 часов)

---

## EXECUTIVE SUMMARY

### Архитектура Системы
Современный асинхронный торговый бот на Python с:
- **WebSocket** для real-time сигналов и цен
- **PostgreSQL** для persistence
- **Множественные защитные слои** (Trailing Stop, Protection Guard, Zombie Cleaner, Age Manager)
- **Биржи**: Binance, Bybit (testnet + mainnet)
- **Режимы**: production, shadow, backtest

### Критичность
**🔴 ВЫСОКАЯ** - система управляет реальными деньгами

### Текущий Статус
- ✅ Бот запущен (PID: 8903)
- ✅ TESTNET режим (безопасно)
- ✅ Production monitor активен (PID: 9018)
- ✅ 5 активных позиций с trailing stop
- 🕐 8-часовой тест начат: 07:49 UTC

---

## МОДУЛЬ 1: WebSocket Сигналы и Цены

### Расположение
- `websocket/signal_client.py` - клиент для сигналов
- `core/signal_processor_websocket.py` - обработка волн
- `websocket/binance_stream.py` / `bybit_stream.py` - price streams
- `websocket/adaptive_stream.py` - для testnet

### Архитектура

```
Signal Server (ws://10.8.0.1:8765)
         ↓
SignalWebSocketClient (signal_client.py)
         ↓ [RAW signals]
SignalAdapter (signal_adapter.py)
         ↓ [ADAPTED signals]
WebSocketSignalProcessor (signal_processor_websocket.py)
         ↓
Wave Monitoring Loop → PositionManager
```

### Логика Работы

**1. Подключение к серверу**
- URL: `ws://10.8.0.1:8765` (из .env)
- Аутентификация по токену
- Auto-reconnect с экспоненциальной задержкой
- Ping/pong heartbeat каждые 20 секунд

**2. Получение сигналов**
- Сервер отправляет type='signals' с массивом
- Клиент складывает в buffer (макс. 100 сигналов)
- **PROTECTIVE SORT**: сортировка по score_week DESC

**3. Мониторинг волн** ⚠️ КРИТИЧНАЯ ЛОГИКА
```python
WAVE_CHECK_MINUTES = [5, 20, 35, 50]  # Проверка на этих минутах

Mapping timestamp → wave:
- Текущая минута 0-15  → ищем волну :45 (предыдущего часа)
- Текущая минута 16-30 → ищем волну :00
- Текущая минута 31-45 → ищем волну :15
- Текущая минута 46-59 → ищем волну :30

Пример: 07:20 → ждем сигналы с timestamp 07:00
```

**4. Обработка волны**
- Ждет до 240 секунд появления сигналов с нужным timestamp
- Извлекает из buffer, адаптирует формат
- Валидирует через pydantic
- Фильтрует стоп-лист символов
- Открывает max 5 позиций (+50% buffer = 7 сигналов проверяется)

### Логирование

**КРИТИЧНЫЕ события для мониторинга:**
```python
✓ "WebSocket connected to [source]"
✓ "📡 Received X RAW signals from WebSocket"
✓ "🔍 Looking for wave with timestamp: YYYY-MM-DD HH:MM"
✓ "🌊 Wave detected! Processing X signals"
✓ "✅ Wave X complete: Y positions opened"
⚠️ "WebSocket disconnected, reconnecting..."
❌ "Error handling WebSocket signals"
```

### Обнаруженные Проблемы

**✅ НЕТ КРИТИЧНЫХ ПРОБЛЕМ**

Сильные стороны:
- Defensive programming (protective sort, buffer)
- Атомарная защита от дубликатов волн
- Proper error handling с logging
- Graceful reconnection

Потенциальные улучшения:
- Добавить метрику "время с последнего сигнала"
- Alert если WebSocket отключен >5 минут

---

## МОДУЛЬ 2: Размещение Позиций и SL

### Расположение
- `core/position_manager.py` (главный модуль, 144k строк!)
- `core/stop_loss_manager.py`
- `core/atomic_position_manager.py`

### Архитектура

```
PositionRequest → PositionManager.open_position()
                       ↓
          [Atomic Transaction Start]
                       ↓
    1. Validate (balance, symbol, duplicates)
    2. Calculate position size (risk-based)
    3. Place Entry Order (market/limit)
    4. Wait for fill (asyncio.wait_for)
    5. Calculate SL price (based on side)
    6. Place SL Order (STOP_MARKET)
    7. Save to DB (repository.create_position)
    8. Emit event (position.opened)
                       ↓
          [Atomic Transaction End]
```

### Логика Размещения SL

**Для Long позиций:**
```python
entry_price = 100.0
sl_distance_percent = 1.0  # из config
sl_price = entry_price * (1 - sl_distance_percent / 100)
# sl_price = 100.0 * 0.99 = 99.0
```

**Для Short позиций:**
```python
entry_price = 100.0
sl_distance_percent = 1.0
sl_price = entry_price * (1 + sl_distance_percent / 100)
# sl_price = 100.0 * 1.01 = 101.0
```

**Тип ордера:**
- Binance: `STOP_MARKET` with `reduceOnly=True`
- Bybit: `STOP_MARKET` with `positionIdx=0`, `reduceOnly=True`

### Размер Позиции

```python
# Базовый расчет
account_balance = 10000.0  # USDT
risk_per_trade_percent = 1.0  # 1% риска
risk_amount = account_balance * (risk_per_trade_percent / 100)
# risk_amount = 100 USDT

sl_distance_percent = 1.0
position_size_usd = risk_amount / (sl_distance_percent / 100)
# position_size_usd = 100 / 0.01 = 10000 USDT

# С учетом leverage
leverage = 10
position_size_contracts = position_size_usd / current_price * leverage
```

### Обработка Ошибок

**Проверки перед открытием:**
1. ✅ Symbol exists and tradable
2. ✅ Duplicate check (по symbol+exchange)
3. ✅ Balance sufficiency
4. ✅ Min notional (минимальный размер сделки)
5. ✅ Precision (количество знаков после запятой)

**Восстановление при сбоях:**
- Если entry прошел, SL failed → `recover_incomplete_positions()`
- Проверка при старте бота
- Auto-retry для временных ошибок

### Логирование

**КРИТИЧНЫЕ события:**
```python
✓ "Opening position: SYMBOL SIDE SIZE at PRICE"
✓ "Entry order filled: ORDER_ID"
✓ "SL placed: ORDER_ID at PRICE"
✓ "✅ Position created successfully: POSITION_ID"
❌ "Error placing entry: ERROR"
❌ "Error placing SL: ERROR"
⚠️ "Position entry filled but SL failed - recovery needed"
```

### Обнаруженные Проблемы

**🟢 СИСТЕМА ROBUST**

Сильные стороны:
- Атомарные транзакции
- Recovery mechanism
- Extensive validation
- Event logging для аудита

Рекомендации:
- Добавить timeout alert если SL не размещен >30 сек
- Метрика: % позиций без SL за последний час

---

## МОДУЛЬ 3: Smart Trailing Stop

### Расположение
- `protection/trailing_stop.py` (831 строк)

### Архитектура

```
SmartTrailingStopManager
         ↓
TrailingStopInstance (per position)
    • State Machine: INACTIVE → WAITING → ACTIVE → TRIGGERED
    • Tracks: highest_price (long) / lowest_price (short)
         ↓
WebSocket price update → update_price()
         ↓
State checks → _check_activation() / _update_trailing_stop()
         ↓
_update_stop_order() → Exchange API
```

### Логика Активации

**Параметры:**
```python
activation_percent = 1.5%  # Прибыль для активации
callback_percent = 0.5%    # Дистанция trailing
```

**Пример для LONG:**
```
Entry: $100
Activation price: $100 * 1.015 = $101.50

Цена достигла $101.50:
→ TS ACTIVATED
→ SL = $101.50 * 0.995 = $100.99 (0.5% ниже текущей)

Цена поднялась до $105:
→ highest_price = $105
→ NEW SL = $105 * 0.995 = $104.475

Цена упала до $104.50:
→ SL НЕ ДВИГАЕТСЯ (не новый максимум)
→ Остается $104.475

Цена касается $104.475:
→ SL TRIGGERED → Position closed
```

### Rate Limiting ⚠️ НОВАЯ ФИЧА

**Защита от избыточных обновлений:**
```python
# Rule 1: Min 60s между обновлениями
if (now - last_sl_update_time) < 60 seconds:
    SKIP update

# Rule 2: Min 0.1% improvement
if improvement < 0.1%:
    SKIP update

# EMERGENCY OVERRIDE: если improvement >= 1.0%
→ BYPASS ALL LIMITS (защита прибыли!)
```

### Atomic SL Update

**Bybit:**
```python
# Использует trading-stop endpoint (АТОМАРНО!)
POST /v5/position/trading-stop
{
    "symbol": "BTCUSDT",
    "stopLoss": "99500.0",
    "positionIdx": 0
}
# НЕТ race condition! SL обновляется мгновенно
```

**Binance:**
```python
# Cancel + Create (минимальное окно уязвимости)
1. cancel_order(old_sl_id)  # ~50ms
2. create_order(new_sl)     # ~50ms
# Unprotected window: ~100ms (логируется)
```

### Логирование

**КРИТИЧНЫЕ события:**
```python
✓ "Created trailing stop for SYMBOL SIDE: entry=X, activation=Y"
✓ "✅ SYMBOL: Trailing stop ACTIVATED at PRICE"
✓ "📈 SYMBOL: Trailing stop updated from X to Y (+Z%)"
✓ "✅ SYMBOL: SL updated via METHOD in Xms"
⚠️ "⚠️ SYMBOL: Large unprotected window! Xms > Yms threshold"
❌ "❌ SYMBOL: SL update failed - ERROR"
⏭️ "SYMBOL: SL update SKIPPED - rate_limit/improvement_too_small"
```

### Обнаруженные Проблемы

**🟢 ОТЛИЧНО СПРОЕКТИРОВАНО**

Сильные стороны:
- Freqtrade-inspired rate limiting
- Emergency override для больших движений
- Атомарность для Bybit
- Детальный logging с метриками

Минорные улучшения:
- Можно добавить alert если unprotected_window > 500ms слишком часто
- Dashboard для визуализации активных TS

---

## МОДУЛЬ 4: Protection Guard (Защита от незащищенных позиций)

### Расположение
- `protection/position_guard.py` (836 строк)
- `core/position_manager.py::check_positions_protection()` (строка 493)

### Архитектура

```
Periodic Check (каждые 5 минут)
         ↓
position_manager.check_positions_protection()
         ↓
For each active position:
    1. Verify position exists on exchange
    2. Check for SL order
    3. If NO SL → Place emergency SL
         ↓
Event: POSITION_PROTECTION_ADDED
```

### Логика Проверки

**Критерии "незащищенной" позиции:**
1. Position exists on exchange (contracts > 0)
2. NO active SL order (STOP_MARKET with reduceOnly)

**Восстановление:**
```python
# Calculate emergency SL
if side == 'long':
    emergency_sl = entry_price * 0.97  # -3%
else:
    emergency_sl = entry_price * 1.03  # +3%

# Place SL
create_stop_loss_order(
    symbol=symbol,
    side='sell' if long else 'buy',
    amount=position_size,
    stop_price=emergency_sl,
    params={'reduceOnly': True}
)
```

### Health Score System

**Компоненты (в position_guard.py):**
```python
health_score = (
    pnl_score * 0.3 +
    drawdown_score * 0.2 +
    volatility_score * 0.2 +
    time_score * 0.15 +
    liquidity_score * 0.15
)

Risk Level:
- 80-100: LOW
- 50-80:  MEDIUM
- 30-50:  HIGH
- 0-30:   CRITICAL
```

### Логирование

**КРИТИЧНЫЕ события:**
```python
✓ "🔍 Protection check: X positions, Y protected, Z unprotected"
✓ "🛡️ Adding SL for unprotected position: SYMBOL"
✓ "✅ Emergency SL placed: SYMBOL at PRICE"
❌ "Failed to add protection for SYMBOL: ERROR"
```

### Обнаруженные Проблемы

**🟡 РАБОТАЕТ, НО МОЖНО УЛУЧШИТЬ**

Текущее состояние:
- ✅ Базовая защита работает
- ⚠️ position_guard.py не интегрирован в main.py (код есть, но не используется!)

Рекомендации:
1. **ИНТЕГРИРОВАТЬ** PositionGuard в main loop
2. Добавить alert если найдено >0 unprotected
3. Уменьшить интервал проверки с 5 мин до 1 мин для критичных ситуаций

---

## МОДУЛЬ 5: Zombie Order Detector

### Расположение
- `core/zombie_manager.py` (725 строк)
- `core/binance_zombie_manager.py` (Binance-specific)
- `core/bybit_zombie_cleaner.py` (Bybit-specific)

### Архитектура

```
Periodic Sync (position_manager.start_periodic_sync())
    Interval: 300s default (авто-adjust на основе количества zombies)
         ↓
EnhancedZombieOrderManager.cleanup_zombie_orders()
         ↓
1. detect_zombie_orders()
    - Fetch active positions (cached 30s)
    - Fetch all open orders (paginated)
    - Analyze each order
         ↓
2. Group zombies by type:
    - Regular orders
    - Conditional orders
    - TP/SL orders
         ↓
3. Cancel orders:
    - _cancel_order_safe() with retry
    - _clear_tpsl_orders() (Bybit direct API)
    - _cancel_all_orders_for_symbol() (aggressive)
```

### Критерии Zombie Order

**1. Order для символа без позиции:**
```python
if symbol not in active_symbols:
    if order.reduceOnly or order.closeOnTrigger:
        → ZOMBIE (reduce-only order без позиции)
```

**2. Wrong positionIdx (hedge mode):**
```python
if positionIdx != active_position.positionIdx:
    → ZOMBIE (ордер для неправильного direction)
```

**3. TP/SL для несуществующей позиции:**
```python
if stopOrderType in ['TakeProfit', 'StopLoss']:
    if no position:
        → ZOMBIE
```

### Cleanup Modes

**Normal mode (dry_run=False):**
- Проверка каждые 5 минут
- Cancel regular orders individually
- Retry 3 times
- Rate limiting 200ms между cancel

**Aggressive mode:**
```python
if zombie_count > (threshold * 2):
    # Aggressive cleanup triggered!
    for symbol in problematic_symbols:
        cancel_all_orders(symbol)  # Nuclear option
        cancel_all_stop_orders(symbol)
```

### Auto-Adjustment

```python
# Adaptive interval based on zombie count
if zombie_count > aggressive_threshold:
    sync_interval = 60  # Проверка каждую минуту!
elif zombie_count > alert_threshold:
    sync_interval = 180  # Каждые 3 минуты
else:
    sync_interval = 300  # Каждые 5 минут
```

### Логирование

**КРИТИЧНЫЕ события:**
```python
✓ "🔍 Checking X orders against Y active positions"
✓ "🧟 Detected Z zombie orders"
✓ "✅ Cancelled zombie order ORDER_ID for SYMBOL"
✓ "🧹 Cleanup complete: X/Y cancelled, Z failed"
⚠️ "🚨 ZOMBIE ORDER ALERT: X zombies detected! Threshold: Y"
🔥 "Aggressive cleanup for symbols: [LIST]"
```

### Обнаруженные Проблемы

**🟢 ОТЛИЧНАЯ РЕАЛИЗАЦИЯ**

Сильные стороны:
- Comprehensive detection criteria
- Safe cancellation with retry
- Adaptive intervals
- Bybit-specific TP/SL handling (trading-stop API)
- Pagination для >50 ордеров

Минорное:
- Можно добавить dashboard для visual tracking

---

## МОДУЛЬ 6: Aged Position Manager

### Расположение
- `core/aged_position_manager.py` (469 строк)

### Архитектура

```
Periodic Check (main.py monitor_loop, каждые 5 минут)
         ↓
AgedPositionManager.check_and_process_aged_positions()
         ↓
For each position:
    Calculate age = now - opened_at
    if age > MAX_POSITION_AGE_HOURS (3h):
        → process_aged_position()
```

### Фазы Ликвидации

**Параметры:**
```python
MAX_POSITION_AGE_HOURS = 3h         # Начало обработки
AGED_GRACE_PERIOD_HOURS = 8h        # Grace period
AGED_LOSS_STEP_PERCENT = 0.5% / hour
AGED_MAX_LOSS_PERCENT = 10%
AGED_ACCELERATION_FACTOR = 1.2x (после 10h progression)
```

**PHASE 1: GRACE PERIOD (3h - 11h)**
```python
hours_over_limit = age - 3  # 0-8h
target_price = breakeven + (2 * commission)

For LONG:
    entry = 100.0
    commission = 0.1%
    target = 100.0 * 1.002 = 100.20  # Breakeven + 0.2%

For SHORT:
    entry = 100.0
    target = 100.0 * 0.998 = 99.80
```

**PHASE 2: PROGRESSIVE LIQUIDATION (11h - 31h)**
```python
hours_after_grace = age - 3 - 8  # 0-20h
loss_percent = hours_after_grace * 0.5%  # Base loss

# Acceleration after 10h
if hours_after_grace > 10:
    extra_hours = hours_after_grace - 10
    acceleration = extra_hours * 0.5% * 0.2  # 20% acceleration
    loss_percent += acceleration

# Cap at 10%
loss_percent = min(loss_percent, 10.0)

For LONG at age=20h (9h after grace):
    loss = 9 * 0.5% = 4.5%
    target = 100.0 * 0.955 = 95.50

For LONG at age=30h (19h after grace):
    base = 19 * 0.5% = 9.5%
    acceleration = 9 * 0.5% * 0.2 = 0.9%
    total = min(9.5% + 0.9%, 10%) = 10%
    target = 100.0 * 0.90 = 90.00
```

**PHASE 3: EMERGENCY (>31h)**
```python
# Используется ТЕКУЩАЯ рыночная цена
target_price = current_market_price
# Ликвидация по любой цене!
```

### Механизм Обновления Ордера

**CRITICAL FIX: Одна лимитка на позицию**
```python
# Использует EnhancedExchangeManager.create_or_update_exit_order()
1. Fetch all open orders for symbol
2. Find existing exit limit order (reduceOnly=True, type=limit)
3. If exists AND price_diff < 0.5%:
    → SKIP update (не нужно)
4. If exists AND price_diff >= 0.5%:
    → Cancel old order
    → Sleep 200ms
    → Create new order with new price
5. If NOT exists:
    → Create new order

# Защита от дубликатов ордеров!
```

### Логирование

**КРИТИЧНЫЕ события:**
```python
✓ "⏰ Found aged position SYMBOL: age=Xh, pnl=Y USD"
✓ "📊 Processing Z aged positions"
✓ "📈 Processing aged position SYMBOL:"
    "  • Age: Xh total (Yh over limit)"
    "  • Phase: GRACE_PERIOD_BREAKEVEN / PROGRESSIVE / EMERGENCY"
    "  • Target: $X"
    "  • Loss tolerance: Y%"
✓ "✅ Placed limit order for SYMBOL: sell @ $X"
⚠️ "⛔ SYMBOL not available in this region - skipping"
❌ "Error processing aged position SYMBOL: ERROR"
```

### Обнаруженные Проблемы

**🟢 ЛОГИКА КОРРЕКТНА**

Сильные стороны:
- Progressive liquidation (не dump сразу)
- Grace period для breakeven попыток
- Geographic restriction handling
- ONE order per position (fixed)

Рекомендации:
- Dashboard для tracking aged positions
- Alert если позиция вошла в EMERGENCY phase

---

## МОДУЛЬ 7: Position Synchronizer

### Расположение
- `core/position_synchronizer.py` (не запущен в main.py в текущей конфигурации)
- Phantom position detection в `position_manager.py`

### Архитектура (Phantom Detection)

```
Periodic Sync (position_manager.periodic_sync)
         ↓
1. Fetch positions from exchange
2. Fetch positions from database
         ↓
3. Compare:
    exchange_positions - db_positions = MISSING (фантомы в DB)
    db_positions - exchange_positions = EXTRA (не на бирже)
         ↓
4. For PHANTOM (в DB но не на бирже):
    → Close in database with reason='PHANTOM'
    → Remove from memory
    → Log event
```

### Criteria for Phantom

```python
# Позиция в БД marked as "open"
db_position.status == 'open'

# НО на бирже её нет
symbol not in exchange_positions

# И это не новая позиция (>30 сек)
(now - position.opened_at) > 30 seconds

→ PHANTOM (возможно закрылась без уведомления)
```

### Логирование

**КРИТИЧНЫЕ события:**
```python
✓ "🔄 Syncing positions with exchange..."
✓ "🗑️ Phantom position detected: SYMBOL (in DB but not on exchange)"
✓ "✅ SYMBOL phantom position closed in database"
⚠️ "Position SYMBOL exists on exchange but not in database"
```

### Обнаруженные Проблемы

**🟡 РАБОТАЕТ, НО PASSIVE**

Текущее состояние:
- ✅ Phantom detection работает
- ⚠️ Срабатывает только при periodic sync (каждые 5 мин)

Рекомендации:
- Добавить WebSocket listener для ORDER_TRADE_UPDATE
- Real-time обнаружение закрытия позиций

---

## СИСТЕМА ЛОГИРОВАНИЯ

### Конфигурация

```python
# main.py:28-35
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trading_bot.log'),
        logging.StreamHandler()  # Also to console
    ]
)
```

### Event Logger (Audit Trail)

**Расположение:** `core/event_logger.py`

**Event Types:**
- BOT_STARTED / BOT_STOPPED
- WAVE_DETECTED / WAVE_COMPLETED
- SIGNAL_EXECUTED / SIGNAL_VALIDATION_FAILED
- POSITION_OPENED / POSITION_CLOSED
- TRAILING_STOP_ACTIVATED / TRAILING_STOP_UPDATED
- ZOMBIE_ORDERS_DETECTED / ZOMBIE_CLEANUP_COMPLETED
- HEALTH_CHECK_FAILED
- EMERGENCY_CLOSE_ALL_TRIGGERED

**Storage:** PostgreSQL table `monitoring.events`

### Log Rotation

**ISSUE:** Лог файл 928 MB!

**Рекомендация:**
```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'logs/trading_bot.log',
    maxBytes=100*1024*1024,  # 100 MB
    backupCount=10
)
```

---

## ГРАФ ВЗАИМОДЕЙСТВИЯ МОДУЛЕЙ

```
                    [MAIN.PY]
                        |
        +---------------+---------------+
        |               |               |
   [Database]    [Exchanges]    [EventRouter]
        |               |               |
        +-------+-------+-------+-------+
                |
    [PositionManager] ← центральный узел
                |
        +-------+-------+-------+-------+
        |       |       |       |       |
        |       |       |       |       |
    [Signal  [TS]  [Protect] [Zombie] [Aged]
   Processor]
        |
    [WebSocket]
   Signal Client
```

### Data Flow для ОТКРЫТИЯ позиции:

```
1. WebSocket Signal
    ↓
2. SignalProcessor (wave detection)
    ↓
3. PositionManager.open_position()
    ↓
4. ExchangeManager (place orders)
    ↓
5. Repository (save to DB)
    ↓
6. EventRouter.emit('position.opened')
    ↓
7. TrailingStopManager (create TS instance)
```

### Data Flow для ЗАЩИТЫ позиции:

```
1. WebSocket Price Update
    ↓
2. TrailingStopManager.update_price()
    ↓
3. Check activation / Update SL
    ↓
4. ExchangeManager.update_stop_loss_atomic()
    ↓
5. EventLogger (log update)

ПАРАЛЛЕЛЬНО:

1. Periodic Timer (5 min)
    ↓
2. PositionManager.check_positions_protection()
    ↓
3. If NO SL → Place emergency SL
```

---

## ПРОВЕРКА ОБРАБОТКИ ОШИБОК

### Exchange Errors

**Обрабатываемые:**
- `ccxt.NetworkError` → retry with exponential backoff
- `ccxt.ExchangeNotAvailable` → retry
- `ccxt.InsufficientFunds` → log + skip
- `ccxt.InvalidOrder` → log + skip
- Geographic restrictions (170209) → skip with 24h mark

**Retry Logic:**
```python
@async_retry(max_attempts=3, delay=1, backoff=2)
async def place_order(...):
    # Will retry 3 times: 0s, 1s, 2s, 4s
```

### Database Errors

**Обрабатываемые:**
- Connection lost → auto-reconnect (asyncpg pool)
- Deadlock → retry transaction
- Constraint violation → log + rollback

**Connection Pool:**
```python
min_size=10, max_size=20
# Auto-recovery on connection loss
```

### WebSocket Errors

**Обрабатываемые:**
- Disconnect → auto-reconnect
- Timeout → ping-pong check
- Auth failed → log + stop (requires manual fix)

**Reconnect Strategy:**
```python
if self.auto_reconnect:
    await asyncio.sleep(min(interval * attempts, 60))
    # Max 60s delay
```

### Critical Path Protection

**Позиция без SL:**
```
Entry filled → SL failed
    ↓
recover_incomplete_positions() at startup
    ↓
Try to place SL again
    ↓
If still fails → Manual intervention required
```

---

## ТЕСТОВАЯ КОНФИГУРАЦИЯ

### Environment
```bash
BINANCE_TESTNET=true
BYBIT_TESTNET=true
ENVIRONMENT=development
```

### Wave Parameters
```bash
WAVE_CHECK_MINUTES=5,20,35,50
WAVE_CHECK_DURATION_SECONDS=240
MAX_POSITION_AGE_HOURS=3
```

### Signal Server
```bash
SIGNAL_WS_URL=ws://10.8.0.1:8765
```

---

## КРИТИЧНЫЕ НАХОДКИ ДЛЯ PRODUCTION ТЕСТА

### ЧТО ПРОВЕРИТЬ:

1. **WebSocket стабильность**
   - Reconnects работают?
   - Сигналы приходят?
   - Price updates регулярные?

2. **Wave Detection**
   - Волны обнаруживаются в нужное время?
   - Mapping timestamp → wave правильный?
   - Дубликаты волн предотвращаются?

3. **Position Opening**
   - 100% coverage SL?
   - Entry → SL без разрыва?
   - Размер позиций корректный?

4. **Trailing Stop**
   - Активируется при достижении порога?
   - SL двигается при росте цены?
   - Rate limiting работает?
   - Unprotected window < 500ms?

5. **Protection Guard**
   - Обнаруживает unprotected positions?
   - Emergency SL размещается?
   - Проверки каждые 5 минут?

6. **Zombie Cleanup**
   - Zombie orders обнаруживаются?
   - Cleanup успешен?
   - Adaptive interval работает?

7. **Aged Positions**
   - Grace period → breakeven?
   - Progressive loss правильный?
   - ONE exit order per position?

### МЕТРИКИ УСПЕХА:

✅ **PASS если:**
- WebSocket uptime > 99%
- SL coverage = 100%
- Trailing stop activations > 0 (if profitable positions)
- Zero unprotected positions > 5 min
- Zombie cleanup success rate > 95%
- No phantom positions
- No critical errors

⚠️ **CONDITIONAL PASS если:**
- Minor issues но система восстанавливается
- Некоторые модули неактивны (нет aged позиций = нормально)

❌ **FAIL если:**
- SL coverage < 95%
- Критичные ошибки приводят к потере защиты
- WebSocket down > 10 минут
- Phantom positions не обнаруживаются

---

## NEXT STEPS

**Сейчас (07:50 UTC):**
- ✅ Бот запущен (PID 8903)
- ✅ Monitor активен (PID 9018)
- 🕐 8-hour test running

**Через 4 часа (11:50 UTC):**
- Проверить промежуточные результаты
- Анализировать первые волны

**Через 8 часов (15:50 UTC):**
- Остановить test
- Генерировать PRODUCTION_TEST_REPORT.md
- Создать FIX_PRIORITY.md

**Финал:**
- Сравнить CODE AUDIT vs PRODUCTION RESULTS
- Финальный отчет FINAL_AUDIT_REPORT.md

---

*Создано: 2025-10-15 07:50 UTC*
*Статус: ✅ ФАЗА 1 завершена, ФАЗА 3 в процессе*
