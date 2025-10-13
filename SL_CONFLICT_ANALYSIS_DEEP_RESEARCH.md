# 🔬 STOP LOSS CONFLICT ANALYSIS: Deep Research

**Дата:** 2025-10-13 02:25
**Статус:** ТОЛЬКО АНАЛИЗ - БЕЗ ИЗМЕНЕНИЙ КОДА
**Вопрос:** Как взаимодействуют Protection Manager и TS Manager при управлении SL?

---

## 📋 EXECUTIVE SUMMARY

**КРИТИЧЕСКАЯ НАХОДКА:** Protection Manager и TS Manager используют **РАЗНЫЕ МЕТОДЫ** установки Stop Loss:

1. **Protection Manager (core/stop_loss_manager.py):**
   - Использует **position-attached SL** через `/v5/position/trading-stop` API
   - SL привязан к позиции, не создает отдельный ордер
   - Проверяет `pos.info.stopLoss` для verification

2. **TS Manager (protection/trailing_stop.py):**
   - Использует **conditional stop orders** через `create_stop_loss_order()`
   - Создает отдельные STOP_MARKET ордера
   - Сохраняет `stop_order_id` для tracking

**РЕЗУЛЬТАТ:** Потенциальные конфликты и дублирование SL.

---

## 🏗️ ЧАСТЬ 1: ARCHITECTURE OVERVIEW

### 1.1 Два независимых SL менеджера

```
┌─────────────────────────────────────────────────────────────┐
│                    POSITION MANAGER                          │
│                                                              │
│  ┌──────────────────────┐    ┌─────────────────────────┐   │
│  │  Protection Manager  │    │   Trailing Stop Manager │   │
│  │ (check_positions_    │    │ (SmartTrailingStopMgr)  │   │
│  │  protection)         │    │                         │   │
│  └──────────────────────┘    └─────────────────────────┘   │
│           │                            │                     │
│           ▼                            ▼                     │
│  ┌──────────────────────┐    ┌─────────────────────────┐   │
│  │ StopLossManager      │    │  _place_stop_order()    │   │
│  │  (core/stop_loss_    │    │  _update_stop_order()   │   │
│  │   manager.py)        │    │                         │   │
│  └──────────────────────┘    └─────────────────────────┘   │
│           │                            │                     │
└───────────┼────────────────────────────┼─────────────────────┘
            │                            │
            ▼                            ▼
   ┌────────────────────────────────────────────────────┐
   │           EXCHANGE MANAGER API                     │
   │                                                     │
   │  ┌──────────────────┐    ┌─────────────────────┐  │
   │  │ _set_bybit_sl()  │    │ create_stop_loss_   │  │
   │  │ (position-       │    │ order()             │  │
   │  │  attached)       │    │ (conditional order) │  │
   │  └──────────────────┘    └─────────────────────┘  │
   └────────────────────────────────────────────────────┘
            │                            │
            ▼                            ▼
   ┌────────────────────────────────────────────────────┐
   │              BYBIT API v5                          │
   │                                                     │
   │  /v5/position/trading-stop    /v5/order/create    │
   │  (position-attached SL)       (conditional order)  │
   └────────────────────────────────────────────────────┘
```

---

## 🔄 ЧАСТЬ 2: PROTECTION MANAGER - DETAILED ANALYSIS

### 2.1 Файлы и классы

**Файл:** `core/stop_loss_manager.py` (664 строк)

**Класс:** `StopLossManager`

**Назначение:** "Единый источник истины для всей логики Stop Loss в системе"

### 2.2 Метод установки SL

**Method:** `set_stop_loss()` (lines 141-212)

**Алгоритм:**

```python
async def set_stop_loss(self, symbol, side, amount, stop_price) -> Dict:
    # ШАГ 1: Проверить существующий SL
    has_sl, existing_sl = await self.has_stop_loss(symbol)

    if has_sl:
        # Validate existing SL
        is_valid, reason = self._validate_existing_sl(...)

        if is_valid:
            return {'status': 'already_exists', 'stopPrice': existing_sl}
        else:
            # Cancel invalid SL and create new one
            await self._cancel_existing_sl(symbol, float(existing_sl))

    # ШАГ 2: Установка через ExchangeManager
    if self.exchange_name == 'bybit':
        return await self._set_bybit_stop_loss(symbol, stop_price)  # ← BYBIT
    else:
        return await self._set_generic_stop_loss(...)  # ← BINANCE
```

### 2.3 Bybit: Position-Attached SL

**Method:** `_set_bybit_stop_loss()` (lines 312-372)

**КРИТИЧЕСКИЙ КОД:**

```python
async def _set_bybit_stop_loss(self, symbol: str, stop_price: float) -> Dict:
    # Format for Bybit API
    bybit_symbol = symbol.replace('/', '').replace(':USDT', '')
    sl_price_formatted = self.exchange.price_to_precision(symbol, stop_price)

    # ============================================================
    # POSITION-ATTACHED STOP LOSS (Bybit trading-stop API)
    # ============================================================
    params = {
        'category': 'linear',
        'symbol': bybit_symbol,
        'stopLoss': str(sl_price_formatted),  # ← ПОЗИЦИОННЫЙ SL!
        'positionIdx': 0,
        'slTriggerBy': 'LastPrice',
        'tpslMode': 'Full'
    }

    result = await self.exchange.private_post_v5_position_trading_stop(params)

    ret_code = int(result.get('retCode', 1))
    ret_msg = result.get('retMsg', 'Unknown error')

    if ret_code == 0:
        # Success
        return {
            'status': 'created',
            'stopPrice': sl_price_formatted,
            'method': 'position_attached',  # ← НЕ ОРДЕР!
            'api_endpoint': '/v5/position/trading-stop'
        }
    elif ret_code == 10001:
        # Position not found
        raise ValueError(f"No open position found for {symbol}")
    else:
        raise Exception(f"Failed to set stop loss: {ret_msg}")
```

**ЧТО ПРОИСХОДИТ:**
- **НЕ создается** отдельный ордер
- SL **привязывается** к существующей позиции
- Хранится в `position.info.stopLoss`
- **НЕ расходует** дополнительный margin
- **НЕ имеет** отдельного order_id

### 2.4 Проверка наличия SL

**Method:** `has_stop_loss()` (lines 41-139)

**Алгоритм для Bybit:**

```python
async def has_stop_loss(self, symbol: str) -> Tuple[bool, Optional[str]]:
    # ============================================================
    # ПРИОРИТЕТ 1: Position-attached SL (для Bybit)
    # ============================================================
    if self.exchange_name == 'bybit':
        positions = await self.exchange.fetch_positions(params={'category': 'linear'})

        for pos in positions:
            if normalize_symbol(pos['symbol']) == normalized_symbol:
                # КРИТИЧНО: Проверяем position.info.stopLoss
                stop_loss = pos.get('info', {}).get('stopLoss', '0')

                # Bybit возвращает '0' если нет SL, или реальную цену если есть
                if stop_loss and stop_loss not in ['0', '0.00', '', None]:
                    return True, stop_loss  # ← НАЙДЕН ПОЗИЦИОННЫЙ SL

    # ============================================================
    # ПРИОРИТЕТ 2: Conditional stop orders (для всех бирж)
    # ============================================================
    orders = await self.exchange.fetch_open_orders(symbol, ...)

    for order in orders:
        if self._is_stop_loss_order(order):
            sl_price = self._extract_stop_price(order)
            return True, str(sl_price)  # ← НАЙДЕН CONDITIONAL SL

    # Нет Stop Loss
    return False, None
```

**ВАЖНО:** Проверяет **ОБА** типа SL:
1. Position-attached (`pos.info.stopLoss`) - ПРИОРИТЕТ 1
2. Conditional orders (`fetch_open_orders`) - ПРИОРИТЕТ 2

### 2.5 Вызов из Position Manager

**Location:** `core/position_manager.py:1520-1650`

**Method:** `check_positions_protection()`

**Алгоритм:**

```python
async def check_positions_protection(self):
    """
    Periodically check and fix positions without stop loss.
    Runs every ~150 seconds (sync_interval).
    """
    unprotected_positions = []

    # Check all positions
    for symbol in list(self.positions.keys()):
        position = self.positions[symbol]
        exchange = self.exchanges.get(position.exchange)

        # Use StopLossManager for SL check
        sl_manager = StopLossManager(exchange.exchange, position.exchange)
        has_sl_on_exchange, sl_price = await sl_manager.has_stop_loss(symbol)

        # Update position state
        position.has_stop_loss = has_sl_on_exchange

        if has_sl_on_exchange and sl_price:
            position.stop_loss_price = sl_price
            # Sync DB
            await self.repository.update_position(
                position.id,
                has_stop_loss=True,
                stop_loss_price=sl_price
            )

        if not has_sl_on_exchange:
            unprotected_positions.append(position)

            # Alert if missing > 30 seconds
            if time_without_sl > 30:
                logger.critical(f"🚨 Position {symbol} WITHOUT STOP LOSS for {time_without_sl}s!")

    # Set SL for unprotected positions
    if unprotected_positions:
        for position in unprotected_positions:
            # Calculate SL price
            stop_loss_price = calculate_stop_loss(...)

            # Set SL using StopLossManager
            if await self._set_stop_loss(exchange, position, stop_loss_price):
                position.has_stop_loss = True
                position.stop_loss_price = stop_loss_price
```

**Периодичность:** Каждые ~150 секунд (2.5 минуты)

**Действия:**
1. Проверяет все позиции на наличие SL
2. Для позиций без SL → устанавливает position-attached SL
3. Синхронизирует состояние с БД

---

## 🎯 ЧАСТЬ 3: TRAILING STOP MANAGER - DETAILED ANALYSIS

### 3.1 Файлы и классы

**Файл:** `protection/trailing_stop.py` (458 строк)

**Класс:** `SmartTrailingStopManager`

**Назначение:** "Advanced trailing stop manager with WebSocket integration"

### 3.2 Метод размещения SL ордера

**Method:** `_place_stop_order()` (lines 359-382)

**КРИТИЧЕСКИЙ КОД:**

```python
async def _place_stop_order(self, ts: TrailingStopInstance) -> bool:
    """Place initial stop order on exchange"""
    try:
        # Cancel existing stop order if any
        if ts.stop_order_id:
            await self.exchange.cancel_order(ts.stop_order_id, ts.symbol)

        # Determine order side (opposite of position)
        order_side = 'sell' if ts.side == 'long' else 'buy'

        # ============================================================
        # CONDITIONAL STOP ORDER (через create_stop_loss_order)
        # ============================================================
        order = await self.exchange.create_stop_loss_order(
            symbol=ts.symbol,
            side=order_side,
            amount=float(ts.quantity),
            stop_price=float(ts.current_stop_price)
        )

        ts.stop_order_id = order.id  # ← СОХРАНЯЕМ ORDER_ID!
        return True

    except Exception as e:
        logger.error(f"Failed to place stop order for {ts.symbol}: {e}")
        return False
```

**ЧТО ПРОИСХОДИТ:**
- **СОЗДАЕТ** отдельный ордер через `create_stop_loss_order()`
- Получает `order_id` и сохраняет в `ts.stop_order_id`
- Ордер **не привязан** к позиции напрямую
- Ордер **может быть отменен** через `cancel_order(order_id)`

### 3.3 Exchange Manager: create_stop_loss_order()

**Location:** `core/exchange_manager.py:448-530`

**Алгоритм для Bybit:**

```python
async def create_stop_loss_order(self, symbol, side, amount, stop_price, reduce_only=True):
    """
    Create stop loss order for futures
    """
    if self.name == 'bybit':
        # ============================================================
        # CRITICAL: Use position-attached stop loss (trading-stop API)
        # ============================================================
        # This prevents "Insufficient balance" error

        # Get position info
        positions = await self.exchange.fetch_positions(
            symbols=[symbol],
            params={'category': 'linear'}
        )
        position_idx = 0  # Default for one-way mode

        for pos in positions:
            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                position_idx = int(pos.get('info', {}).get('positionIdx', 0))
                break

        # Format symbol
        bybit_symbol = symbol.replace('/', '').replace(':USDT', '')
        stop_loss_price = self.exchange.price_to_precision(symbol, float(stop_price))

        # ============================================================
        # ИСПОЛЬЗУЕТ ТОЖЕ POSITION-ATTACHED API!
        # ============================================================
        params = {
            'category': 'linear',
            'symbol': bybit_symbol,
            'stopLoss': str(stop_loss_price),
            'positionIdx': position_idx,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        # Use trading-stop endpoint (same as Protection Manager!)
        result = await self.rate_limiter.execute_request(
            self.exchange.private_post_v5_position_trading_stop,
            params
        )

        # Process result
        if result.get('retCode') == 0:
            return OrderResult(
                id=f"sl_{bybit_symbol}_{int(time.time())}",  # ← SYNTHETIC ID!
                symbol=symbol,
                type='stop_loss',
                side=side,
                ...
            )

    elif self.name == 'binance':
        # ============================================================
        # BINANCE: Creates actual conditional STOP_MARKET order
        # ============================================================
        order = await self.exchange.create_order(
            symbol=symbol,
            type='STOP_MARKET',  # ← ОТДЕЛЬНЫЙ ОРДЕР!
            side=side.lower(),
            amount=amount,
            price=None,
            params={
                'stopPrice': float(stop_price),
                'reduceOnly': reduce_only,
                'workingType': 'CONTRACT_PRICE'
            }
        )

        return OrderResult(
            id=order['id'],  # ← REAL ORDER ID!
            ...
        )
```

**КРИТИЧЕСКАЯ НАХОДКА:**

### 🚨 BYBIT: ОБА менеджера используют ОДИН И ТОТ ЖЕ API!

**Protection Manager:**
```python
# core/stop_loss_manager.py:340
await self.exchange.private_post_v5_position_trading_stop(params)
```

**TS Manager (через ExchangeManager):**
```python
# core/exchange_manager.py:499-505
await self.exchange.private_post_v5_position_trading_stop(params)
```

**ОБА используют:** `/v5/position/trading-stop` (position-attached SL)

---

## ⚠️ ЧАСТЬ 4: КОНФЛИКТЫ И ПРОБЛЕМЫ

### 4.1 Конфликт #1: Перезапись SL

**Сценарий:**

```
t=0s:  Protection Manager устанавливает SL на $50,000
       → pos.info.stopLoss = "50000"

t=2s:  Price moves to $50,750 (+1.5%)
       → TS Manager активируется

t=2s:  TS Manager пытается установить trailing SL на $50,496
       → Вызывает exchange.create_stop_loss_order()
       → ExchangeManager.create_stop_loss_order() (Bybit)
       → private_post_v5_position_trading_stop()
       → pos.info.stopLoss = "50496"  ← ПЕРЕЗАПИСЫВАЕТ!

Результат: SL от Protection Manager УДАЛЕН, остался только TS SL
```

**Проблема:**
- Protection Manager думает, что SL = $50,000
- Реально SL = $50,496 (установлен TS Manager)
- При проверке `check_positions_protection()` найдет SL и решит что всё ОК
- Но SL управляется теперь TS Manager, не Protection Manager

### 4.2 Конфликт #2: Дублирование проверок

**Protection Manager:**
- Проверяет SL каждые 150 секунд
- Вызывает `has_stop_loss()` → проверяет `pos.info.stopLoss`
- Если нет SL → устанавливает через `set_stop_loss()`

**TS Manager:**
- Обновляет SL при каждом price update (каждую секунду)
- Вызывает `_update_stop_order()` → cancel old + place new
- Place new → `create_stop_loss_order()` → `trading-stop` API

**Проблема:**
- TS Manager обновляет SL → `pos.info.stopLoss` меняется
- Protection Manager видит SL и думает что всё ОК
- Но не знает, что SL управляется TS Manager

### 4.3 Конфликт #3: Synthetic Order ID

**TS Manager сохраняет:**
```python
ts.stop_order_id = order.id  # Synthetic ID: "sl_BTCUSDT_1697123456"
```

**Позже пытается отменить:**
```python
await self.exchange.cancel_order(ts.stop_order_id, ts.symbol)
# Пытается отменить "sl_BTCUSDT_1697123456"
# НО такого ордера НЕТ (position-attached SL не имеет order_id)!
```

**Проблема:**
- `cancel_order()` не найдет ордер (synthetic ID)
- Может вызвать ошибку или просто вернуть False
- SL останется на позиции даже после попытки отмены

### 4.4 Конфликт #4: Racing Updates

**Сценарий:**

```
t=0s:   Protection Manager: set SL = $50,000
t=2s:   TS Manager: update SL = $50,496
t=150s: Protection Manager check → видит SL = $50,496 → OK
t=152s: TS Manager: update SL = $50,745
t=153s: Protection Manager: set SL = $50,000  ← ПЕРЕЗАПИСЫВАЕТ TRAILING!
```

**Почему происходит:**
- Protection Manager не знает о существовании TS Manager
- Если `has_stop_loss()` вернет `False` (по какой-то причине)
- Protection Manager установит фиксированный SL
- Перезапишет trailing SL

---

## 🔍 ЧАСТЬ 5: РЕАЛЬНОЕ СОСТОЯНИЕ (Текущее)

### 5.1 Что происходит СЕЙЧАС

**Факты:**

1. **TS Manager НЕ АКТИВЕН** (из предыдущего отчета)
   - `has_trailing_stop = False` для всех позиций
   - TS instances НЕ создаются
   - `update_price()` НЕ вызывается

2. **Protection Manager АКТИВЕН**
   - Проверяет SL каждые 150 секунд
   - Устанавливает position-attached SL
   - Использует `/v5/position/trading-stop` API

3. **Конфликтов НЕТ** (потому что TS Manager неактивен)
   - Только Protection Manager управляет SL
   - Никакой конкуренции за обновление SL
   - SL фиксированный, не trailing

### 5.2 Что БУДЕТ, если включить TS

**После исправления `has_trailing_stop = False`:**

1. TS Manager начнет создавать instances
2. При активации (profit >= 1.5%):
   - `_activate_trailing_stop()` вызовет `_update_stop_order()`
   - Вызовет `exchange.create_stop_loss_order()`
   - Установит trailing SL через `/v5/position/trading-stop`
   - **ПЕРЕЗАПИШЕТ** SL от Protection Manager

3. При каждом price update (каждую секунду):
   - TS Manager будет обновлять SL
   - Protection Manager продолжит проверять SL каждые 150 секунд
   - **КОНФЛИКТ**: оба пытаются управлять одним и тем же `pos.info.stopLoss`

---

## 💡 ЧАСТЬ 6: КООРДИНАЦИЯ И РЕШЕНИЯ

### 6.1 Текущая координация (отсутствует)

**НЕТ механизмов координации:**
- ❌ Protection Manager не знает о TS Manager
- ❌ TS Manager не знает о Protection Manager
- ❌ Нет проверки "кто владеет SL"
- ❌ Нет флага "SL managed by TS"
- ❌ Нет mutual exclusion

### 6.2 Решение #1: Ownership Flag (рекомендуется)

**Добавить флаг в PositionState:**

```python
@dataclass
class PositionState:
    ...
    has_stop_loss: bool = False
    stop_loss_price: Optional[float] = None

    # NEW: SL ownership tracking
    sl_managed_by: Optional[str] = None  # 'protection' or 'trailing_stop'
    sl_last_updated_by: Optional[str] = None
    sl_last_update_time: Optional[datetime] = None
```

**Логика:**

```python
# Protection Manager
async def check_positions_protection(self):
    for position in positions:
        has_sl, sl_price = await sl_manager.has_stop_loss(symbol)

        if has_sl:
            # Check ownership
            if position.sl_managed_by == 'trailing_stop':
                # TS Manager owns SL - DON'T TOUCH!
                logger.debug(f"SL for {symbol} managed by TS, skipping protection check")
                continue

            # Protection Manager owns SL - verify and update if needed
            position.sl_managed_by = 'protection'
            ...

# TS Manager
async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
    # Mark as TS-managed
    position = self.position_manager.positions.get(ts.symbol)
    if position:
        position.sl_managed_by = 'trailing_stop'
        position.sl_last_updated_by = 'trailing_stop'
        position.sl_last_update_time = datetime.now()

    # Update SL
    await self.exchange.create_stop_loss_order(...)
```

**Преимущества:**
- ✅ Явная координация
- ✅ Нет конфликтов
- ✅ Легко debug (видно кто управляет SL)
- ✅ Protection Manager может взять ownership обратно если TS закрывается

### 6.3 Решение #2: Disable Protection для TS-позиций

**Логика:**

```python
# Protection Manager
async def check_positions_protection(self):
    for position in positions:
        # Skip positions with active trailing stop
        if position.has_trailing_stop and position.trailing_activated:
            logger.debug(f"{position.symbol} has active TS, skipping protection")
            continue  # ← TS owns SL completely

        # Normal protection logic for non-TS positions
        ...
```

**Преимущества:**
- ✅ Простая реализация
- ✅ Минимальные изменения
- ✅ Четкое разделение ответственности

**Недостатки:**
- ❌ Если TS Manager fails → SL может остаться без monitoring
- ❌ Нет fallback protection

### 6.4 Решение #3: TS Manager координирует с Protection

**Логика:**

```python
# TS Manager checks Protection Manager before updating
async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
    # Get current SL from Protection Manager
    has_sl, current_sl = await self.protection_manager.has_stop_loss(ts.symbol)

    # Calculate new trailing SL
    new_sl = self._calculate_new_sl(ts)

    # Only update if new SL is better (ratchet mechanism)
    if self._is_better_sl(new_sl, current_sl, ts.side):
        # Update through Protection Manager (coordinated)
        await self.protection_manager.update_sl(ts.symbol, new_sl, managed_by='trailing_stop')

        logger.info(f"TS updated SL from {current_sl} to {new_sl}")
        return True

    return False
```

**Преимущества:**
- ✅ Полная координация
- ✅ Protection Manager всегда в курсе
- ✅ Single source of truth (Protection Manager)

**Недостатки:**
- ❌ Тесная связь (coupling)
- ❌ Больше изменений кода

---

## 📊 ЧАСТЬ 7: BINANCE vs BYBIT

### 7.1 Binance: Разные методы

**Protection Manager (Binance):**
```python
# НЕ используется position-attached SL
# Вместо этого создает STOP_MARKET ордер
order = await exchange.create_order(
    type='STOP_MARKET',  # ← Conditional order
    params={'stopPrice': stop_price, 'reduceOnly': True}
)
# Возвращает реальный order_id
```

**TS Manager (Binance):**
```python
# Тоже создает STOP_MARKET ордер
order = await exchange.create_stop_loss_order(...)
# Возвращает реальный order_id
```

**РЕЗУЛЬТАТ:**
- На Binance **РАЗНЫЕ** SL ордера!
- Protection Manager SL: order_id = "123456"
- TS Manager SL: order_id = "789012"
- **ДУБЛИРОВАНИЕ SL** - позиция будет закрыта дважды!

### 7.2 Bybit: Один метод, одно место

**Protection Manager (Bybit):**
```python
await exchange.private_post_v5_position_trading_stop(params)
# Устанавливает pos.info.stopLoss = "50000"
```

**TS Manager (Bybit):**
```python
await exchange.private_post_v5_position_trading_stop(params)
# ПЕРЕЗАПИСЫВАЕТ pos.info.stopLoss = "50496"
```

**РЕЗУЛЬТАТ:**
- На Bybit **ПЕРЕЗАПИСЬ** (не дублирование)
- Только один SL существует в `pos.info.stopLoss`
- Последний вызов API побеждает

---

## 🎯 ЧАСТЬ 8: RECOMMENDATIONS

### 8.1 Критические выводы

1. **Bybit: Перезапись SL** (не дублирование)
   - Protection Manager и TS Manager используют один API
   - Последний вызов перезаписывает SL
   - Нет явного конфликта, но потеря контроля

2. **Binance: Дублирование SL** (критическая проблема)
   - Создаются отдельные STOP_MARKET ордера
   - При срабатывании первого SL позиция закрывается
   - Второй SL останется висеть (orphan order)
   - Потенциальная утечка margin

3. **Нет координации**
   - Оба менеджера работают независимо
   - Нет mutual exclusion
   - Нет ownership tracking

### 8.2 Recommended Solution

**Приоритет 1: Implement Ownership Flag**

```python
# Add to PositionState
sl_managed_by: Optional[str] = None  # 'protection' or 'trailing_stop'

# Protection Manager skips TS-managed positions
if position.sl_managed_by == 'trailing_stop':
    continue

# TS Manager marks ownership
position.sl_managed_by = 'trailing_stop'
```

**Приоритет 2: TS Manager checks before update**

```python
# Only update if we own the SL
if position.sl_managed_by != 'trailing_stop':
    # Take ownership
    position.sl_managed_by = 'trailing_stop'

# Update SL
await self._update_stop_order(ts)
```

**Приоритет 3: Protection Manager fallback**

```python
# If TS Manager fails or inactive for > 5 minutes
if position.sl_managed_by == 'trailing_stop':
    last_update = position.sl_last_update_time
    if datetime.now() - last_update > timedelta(minutes=5):
        logger.warning(f"TS inactive for {symbol}, taking over protection")
        position.sl_managed_by = 'protection'
        # Verify and fix SL
        await self._verify_and_fix_sl(position)
```

### 8.3 Для Binance: Cancel old SL before creating new

```python
# TS Manager при активации
async def _activate_trailing_stop(self, ts: TrailingStopInstance):
    # Cancel Protection Manager SL first
    await self._cancel_protection_manager_sl(ts.symbol)

    # Then create TS SL
    await self._place_stop_order(ts)

    # Mark ownership
    position.sl_managed_by = 'trailing_stop'
```

---

## 📝 ЧАСТЬ 9: SUMMARY

### 9.1 Текущее состояние (без изменений)

| Компонент | Статус | Метод SL | API Endpoint |
|-----------|--------|----------|--------------|
| Protection Manager | ✅ Активен | Position-attached (Bybit) / STOP_MARKET (Binance) | `/v5/position/trading-stop` (Bybit) |
| TS Manager | ❌ Неактивен | Position-attached (Bybit) / STOP_MARKET (Binance) | `/v5/position/trading-stop` (Bybit) |
| Конфликты | ✅ Отсутствуют | N/A | N/A |

**Причина отсутствия конфликтов:** TS Manager не создает instances (has_trailing_stop=False)

### 9.2 Будущее состояние (после включения TS)

| Проблема | Bybit | Binance |
|----------|-------|---------|
| Дублирование SL | ❌ Нет (перезапись) | ✅ **ДА** (2 ордера) |
| Потеря контроля | ✅ **ДА** (перезапись) | ✅ **ДА** (конкуренция) |
| Orphan orders | ❌ Нет | ✅ **ДА** (второй SL висит) |
| Координация | ❌ **НЕТ** | ❌ **НЕТ** |

### 9.3 Критичность

**ВЫСОКАЯ для Binance** - дублирование SL может вызвать:
- Двойное закрытие позиции
- Orphan orders
- Margin leakage

**СРЕДНЯЯ для Bybit** - перезапись SL:
- Один SL всегда существует
- Но контроль теряется
- Protection Manager думает что SL = X, а реально = Y

---

## 🎯 КОНЕЦ ОТЧЕТА

**Статус:** Полный deep research анализ конфликтов завершен
**Изменения кода:** НЕ ВНЕСЕНЫ (только анализ)
**Следующие шаги:** Ожидание решения пользователя

---

**Вопросы для пользователя:**

1. Хотите ли включить TS Manager после устранения конфликтов?
2. Какое решение координации предпочитаете (Ownership Flag, Disable Protection, или Coordinated Updates)?
3. Нужно ли приоритизировать исправление для Binance (критическая проблема дублирования)?
4. Хотите ли добавить monitoring/alerting для конфликтов SL?
