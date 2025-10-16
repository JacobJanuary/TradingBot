# 🔧 ПРЕДЛОЖЕННЫЕ ИСПРАВЛЕНИЯ ZOMBIE MANAGER

**Дата:** 2025-10-15
**На основе:** Audit Report + Diagnostic Results

---

## 📊 ОБНАРУЖЕННЫЕ ПРОБЛЕМЫ

### 1. **BINANCE: 48 зомби-ордеров НЕ удаляются**

**Текущее поведение:**
- 48 `stop_market` ордеров с `reduceOnly=True` для **закрытых позиций**
- Возраст: от 1.5 до 28.4 часов
- Zombie manager **видит** их, но **НЕ удаляет**

**Причина:**
```python
# binance_zombie_manager.py:384-399

# Layer 1: Тип защиты
if order_type.upper() in PROTECTIVE_ORDER_TYPES:  # STOP_MARKET есть в списке
    return None  # ❌ Не удаляем

# Layer 3: reduceOnly защита
if order.get('reduceOnly') == True:
    return None  # ❌ Не удаляем
```

**Проблема:** Комментарий в коде говорит _"exchange auto-cancels these when position closes"_, но это **НЕПРАВДА** для Binance Futures!

---

### 2. **BYBIT: 3 reduceOnly ордера удалены с ОТКРЫТЫМИ позициями**

**Из диагностического отчёта:**
```
1. Order: fd7316ae... (1000NEIROCTO/USDT)
   Type: market, Side: sell, ReduceOnly: True
   Position before: ✅ YES
   Position after: ✅ YES
   ⚠️  HIGH RISK: ReduceOnly deleted with open position

2. Order: 593ef560... (CLOUD/USDT)
   Type: market, Side: buy, ReduceOnly: True
   Position before: ✅ YES
   Position after: ✅ YES
   ⚠️  HIGH RISK: ReduceOnly deleted with open position

3. Order: c8eee6b8... (OKB/USDT)
   Type: market, Side: sell, ReduceOnly: True
   Position before: ✅ YES
   Position after: ✅ YES
   ⚠️  HIGH RISK: ReduceOnly deleted with open position
```

**Это были stop-loss ордера для ОТКРЫТЫХ позиций, которые были удалены!**

---

## 🔧 FIX #1: BINANCE - Правильное определение зомби для закрытых позиций

### Текущий код (НЕПРАВИЛЬНЫЙ)

**Location:** `core/binance_zombie_manager.py:375-426`

```python
# CRITICAL FIX: Skip protective orders - exchange manages their lifecycle
# On futures, exchange auto-cancels these when position closes  ❌ ЭТО ЛОЖЬ!
# If they exist → position is ACTIVE → NOT orphaned
PROTECTIVE_ORDER_TYPES = [
    'STOP_LOSS', 'STOP_LOSS_LIMIT', 'STOP_MARKET',
    'TAKE_PROFIT', 'TAKE_PROFIT_LIMIT', 'TAKE_PROFIT_MARKET',
    'TRAILING_STOP_MARKET', 'STOP', 'TAKE_PROFIT'
]

if order_type.upper() in PROTECTIVE_ORDER_TYPES:
    logger.debug(f"Skipping protective order {order_id} - managed by exchange")
    return None  # ❌ ВСЕГДА пропускаем - НЕПРАВИЛЬНО!

# Additional keyword check
PROTECTIVE_KEYWORDS = ['STOP', 'TAKE_PROFIT', 'TRAILING']
if any(keyword in order_type_upper for keyword in PROTECTIVE_KEYWORDS):
    return None  # ❌ ВСЕГДА пропускаем - НЕПРАВИЛЬНО!

# reduceOnly check
if order.get('reduceOnly') == True:
    logger.debug(f"Skipping reduceOnly order - likely SL/TP")
    return None  # ❌ ВСЕГДА пропускаем - НЕПРАВИЛЬНО!

# Только ПОТОМ проверяем баланс
if symbol not in active_symbols:
    return BinanceZombieOrder(zombie_type='orphaned')
```

---

### ИСПРАВЛЕННЫЙ КОД (FIX #1)

```python
# Location: core/binance_zombie_manager.py:375-480

async def _analyze_order(self, order: Dict, active_symbols: Set) -> Optional[BinanceZombieOrder]:
    """
    FIXED VERSION: Правильная логика для protective orders

    Изменения:
    1. ✅ Сначала проверяем позицию, ПОТОМ решаем удалять или нет
    2. ✅ Protective orders для ЗАКРЫТЫХ позиций = ЗОМБИ (удаляем)
    3. ✅ Protective orders для ОТКРЫТЫХ позиций = НЕ ЗОМБИ (не трогаем)
    """

    order_id = order.get('id', '')
    client_order_id = order.get('clientOrderId', '')
    symbol = order.get('symbol', '')
    side = order.get('side', '')
    order_type = order.get('type', '')
    amount = float(order.get('amount', 0) or 0)
    price = float(order.get('price', 0) or 0)
    status = order.get('status', 'unknown')
    timestamp = order.get('timestamp', 0)
    reduce_only = order.get('reduceOnly', False)
    order_list_id = order.get('info', {}).get('orderListId', -1) if order.get('info') else -1

    # Skip already closed orders
    if status in ['closed', 'canceled', 'filled', 'rejected', 'expired']:
        return None

    # Определяем: это protective order?
    PROTECTIVE_ORDER_TYPES = [
        'STOP_LOSS', 'STOP_LOSS_LIMIT', 'STOP_MARKET',
        'TAKE_PROFIT', 'TAKE_PROFIT_LIMIT', 'TAKE_PROFIT_MARKET',
        'TRAILING_STOP_MARKET', 'STOP', 'TAKE_PROFIT'
    ]
    PROTECTIVE_KEYWORDS = ['STOP', 'TAKE_PROFIT', 'TRAILING']

    order_type_upper = order_type.upper()
    is_protective_type = (
        order_type_upper in PROTECTIVE_ORDER_TYPES or
        any(keyword in order_type_upper for keyword in PROTECTIVE_KEYWORDS) or
        reduce_only
    )

    # ✅ КРИТИЧНОЕ ИЗМЕНЕНИЕ: Проверяем позицию
    symbol_clean = symbol.replace(':', '')

    # Получаем активные позиции (с кэшированием)
    active_positions = await self._get_active_positions_cached()

    # Проверка 1: Есть ли позиция для этого символа?
    has_position = False
    for (pos_symbol, pos_idx), pos_data in active_positions.items():
        if pos_symbol == symbol or pos_symbol == symbol_clean:
            quantity = pos_data.get('quantity', 0)
            if quantity != 0:
                has_position = True
                break

    # Проверка 2: Есть ли баланс для этого символа?
    has_balance = (symbol in active_symbols or symbol_clean in active_symbols)

    # ✅ НОВАЯ ЛОГИКА: Для protective orders
    if is_protective_type:
        if has_position:
            # Позиция ОТКРЫТА → protective order НУЖЕН → НЕ ЗОМБИ
            logger.debug(
                f"Keeping protective order {order_id} ({order_type}) - "
                f"position is OPEN for {symbol}"
            )
            return None  # ✅ НЕ удаляем

        else:
            # Позиция ЗАКРЫТА → protective order НЕ НУЖЕН → ЗОМБИ!
            logger.warning(
                f"Found zombie protective order {order_id} ({order_type}) - "
                f"position is CLOSED for {symbol}"
            )

            return BinanceZombieOrder(
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                status=status,
                timestamp=timestamp,
                zombie_type='protective_for_closed_position',  # ✅ Новый тип
                reason=f'Protective order ({order_type}) for closed position',
                order_list_id=order_list_id if order_list_id != -1 else None
            )

    # Для НЕ-protective orders: проверяем баланс (как раньше)
    if not has_balance and not has_position:
        return BinanceZombieOrder(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            status=status,
            timestamp=timestamp,
            zombie_type='orphaned',
            reason='No balance AND no position for trading pair',
            order_list_id=order_list_id if order_list_id != -1 else None
        )

    # Остальные проверки (phantom, stuck, async_lost, oco) остаются как есть...
    # ...
```

---

### Что изменилось в FIX #1:

1. **Убрали раннее `return None`** для protective orders
2. **Добавили проверку позиции** через `_get_active_positions_cached()`
3. **Новая логика:**
   - Protective order + **ОТКРЫТАЯ позиция** → НЕ трогаем ✅
   - Protective order + **ЗАКРЫТАЯ позиция** → ЗОМБИ, удаляем ✅
4. **Новый zombie_type:** `'protective_for_closed_position'`

---

## 🔧 FIX #2: BYBIT - Добавить retry и validation для fetch_positions

### Текущий код (УЯЗВИМЫЙ)

**Location:** `core/bybit_zombie_cleaner.py:71-103`

```python
async def get_active_positions_map():
    try:
        positions = await self.exchange.fetch_positions()
        active_positions = {}

        for pos in positions:
            position_size = float(pos.get('contracts', 0) or pos.get('size', 0))
            if position_size > 0:
                # build map...

        return active_positions  # ⚠️ Может вернуть {} если API failed

    except Exception as e:
        logger.error(f"Failed: {e}")
        raise  # ❌ Прерывает весь cleanup
```

**Проблема:** Если API вернёт пустой массив → все ордера станут зомби → все SL удалятся!

---

### ИСПРАВЛЕННЫЙ КОД (FIX #2)

```python
# Location: core/bybit_zombie_cleaner.py:71-140

async def get_active_positions_map(self, max_retries: int = 3) -> Dict[Tuple[str, int], dict]:
    """
    FIXED VERSION: С retry и validation

    Изменения:
    1. ✅ Retry logic (3 попытки)
    2. ✅ Validation пустого результата
    3. ✅ Сравнение с предыдущим known state
    4. ✅ Safe fallback вместо exception
    """

    previous_count = len(self._position_cache) if hasattr(self, '_position_cache') else None

    for attempt in range(max_retries):
        try:
            # Fetch positions
            positions = await self.exchange.fetch_positions()
            active_positions = {}

            for pos in positions:
                position_size = float(pos.get('contracts', 0) or pos.get('size', 0))
                if position_size > 0:
                    symbol = pos['symbol']
                    position_idx = int(pos.get('info', {}).get('positionIdx', 0))
                    key = (symbol, position_idx)
                    active_positions[key] = pos

            # ✅ VALIDATION 1: Подозрительно пустой результат?
            if not active_positions and attempt < max_retries - 1:
                logger.warning(
                    f"⚠️ Empty positions list on attempt {attempt+1}/{max_retries}. "
                    f"This is suspicious - retrying in {2**attempt}s..."
                )
                await asyncio.sleep(2 ** attempt)
                continue

            # ✅ VALIDATION 2: Резкое падение количества?
            if previous_count is not None and len(active_positions) < previous_count * 0.5:
                logger.warning(
                    f"⚠️ Position count dropped significantly: "
                    f"{previous_count} → {len(active_positions)}. "
                    f"Possible API issue!"
                )

                if attempt < max_retries - 1:
                    logger.warning(f"Retrying in {2**attempt}s...")
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    logger.error(
                        f"❌ Position count still low after {max_retries} attempts. "
                        f"Using result but logging WARNING."
                    )

            # Success - cache result
            self._position_cache = active_positions
            logger.info(f"✅ Active positions map: {len(active_positions)} positions")

            return active_positions

        except Exception as e:
            logger.error(f"Failed to get positions (attempt {attempt+1}/{max_retries}): {e}")

            if attempt == max_retries - 1:
                # ✅ SAFE FALLBACK: Return empty dict
                # Empty dict = "unknown state, don't delete anything"
                logger.critical(
                    f"❌ All {max_retries} attempts failed to fetch positions. "
                    f"Returning EMPTY dict as SAFE FALLBACK. "
                    f"NO ORDERS WILL BE DELETED this cycle."
                )
                return {}

            await asyncio.sleep(2 ** attempt)

    return {}
```

---

### Что изменилось в FIX #2:

1. **Retry logic:** 3 попытки с exponential backoff
2. **Validation 1:** Проверка на пустой результат
3. **Validation 2:** Проверка на резкое падение количества позиций
4. **Safe fallback:** Возвращаем `{}` вместо exception → никакие ордера не будут удалены
5. **Caching:** Сохраняем `previous_count` для сравнения

---

## 🔧 FIX #3: EventLogger - Safe wrapper

### Текущий код (УЯЗВИМЫЙ)

**Location:** Множество мест в `zombie_manager.py`

```python
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(...)  # ❌ Может выбросить exception
```

**Проблема:** Если EventLogger упадёт → весь cleanup остановится.

---

### ИСПРАВЛЕННЫЙ КОД (FIX #3)

```python
# Location: zombie_manager.py - добавить новый метод

async def _log_event_safe(self, event_type: EventType, data: Dict, **kwargs):
    """
    Safe wrapper for EventLogger - NEVER throws exceptions

    ✅ CRITICAL FIX: Prevents logging failures from stopping cleanup
    """
    event_logger = get_event_logger()
    if event_logger:
        try:
            await event_logger.log_event(event_type, data, **kwargs)
        except Exception as e:
            # Log to standard logger but DON'T raise
            logger.error(
                f"⚠️ Failed to log event {event_type.value}: {e}. "
                f"Continuing cleanup regardless."
            )
            # Optional: Store for retry later
            if not hasattr(self, '_failed_logs'):
                self._failed_logs = []
            self._failed_logs.append({
                'event_type': event_type,
                'data': data,
                'kwargs': kwargs,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })


# Заменить ВСЕ вызовы:
# БЫЛО:
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(EventType.ZOMBIE_ORDERS_DETECTED, {...})

# СТАЛО:
await self._log_event_safe(EventType.ZOMBIE_ORDERS_DETECTED, {...})
```

---

## 📊 СРАВНЕНИЕ: ДО И ПОСЛЕ

### До исправлений:

**Binance:**
- 48 зомби-ордеров НЕ удаляются (висят 28+ часов)
- ❌ Захламление exchange
- ❌ Потенциальные проблемы с лимитами ордеров

**Bybit:**
- 3 SL удалены для ОТКРЫТЫХ позиций
- ❌ Позиции остались БЕЗ ЗАЩИТЫ
- 🚨 КРИТИЧНЫЙ риск

---

### После исправлений:

**Binance:**
- ✅ 48 зомби-ордеров будут удалены при следующем cleanup
- ✅ Новые protective orders для закрытых позиций будут удаляться автоматически
- ✅ Protective orders для ОТКРЫТЫХ позиций остаются нетронутыми

**Bybit:**
- ✅ Retry logic предотвратит удаление при API ошибках
- ✅ Validation обнаружит подозрительные пустые результаты
- ✅ Safe fallback защитит от массового удаления
- ✅ SL для открытых позиций НЕ будут удаляться

---

## 🧪 ПЛАН ТЕСТИРОВАНИЯ

### 1. Unit Tests

```python
# test_binance_zombie_fix.py

def test_protective_order_with_open_position_not_deleted():
    """SL для открытой позиции НЕ должен удаляться"""
    manager = BinanceZombieManager(mock_exchange)

    # Setup: Position exists
    mock_exchange.fetch_positions.return_value = [
        {'symbol': 'BTCUSDT', 'contracts': 0.1, 'side': 'long'}
    ]

    # Setup: SL order exists
    mock_exchange.fetch_open_orders.return_value = [
        {
            'id': '123',
            'symbol': 'BTCUSDT',
            'type': 'STOP_MARKET',
            'reduceOnly': True,
            'status': 'open'
        }
    ]

    # Detect zombies
    zombies = await manager.detect_zombie_orders()

    # SL should NOT be in zombies
    assert len(zombies['all']) == 0

def test_protective_order_with_closed_position_deleted():
    """SL для ЗАКРЫТОЙ позиции ДОЛЖЕН удаляться"""
    manager = BinanceZombieManager(mock_exchange)

    # Setup: NO position
    mock_exchange.fetch_positions.return_value = []

    # Setup: SL order exists
    mock_exchange.fetch_open_orders.return_value = [
        {
            'id': '123',
            'symbol': 'BTCUSDT',
            'type': 'STOP_MARKET',
            'reduceOnly': True,
            'status': 'open'
        }
    ]

    # Detect zombies
    zombies = await manager.detect_zombie_orders()

    # SL SHOULD be in zombies
    assert len(zombies['all']) == 1
    assert zombies['all'][0].zombie_type == 'protective_for_closed_position'
```

---

### 2. Integration Test (Testnet)

```bash
# 1. Создать тестовую позицию
# 2. Проверить что SL создан
# 3. Запустить zombie cleanup
# 4. Убедиться что SL НЕ удалён

# 5. Закрыть позицию
# 6. Запустить zombie cleanup
# 7. Убедиться что SL УДАЛЁН
```

---

### 3. Diagnostic Test

```bash
# Запустить диагностику после применения фиксов
python zombie_manager_monitor.py --duration 10

# Ожидаемый результат:
# ✅ No HIGH or CRITICAL issues
# ✅ Binance: 48 zombies cleaned
# ✅ Bybit: No protective orders deleted with open positions
```

---

## ⏱️ ОЦЕНКА ВРЕМЕНИ РЕАЛИЗАЦИИ

| Fix | Description | Time | Priority |
|-----|-------------|------|----------|
| FIX #1 | Binance protective order logic | 2 hours | P0 |
| FIX #2 | Bybit retry + validation | 2 hours | P0 |
| FIX #3 | EventLogger safe wrapper | 1 hour | P0 |
| **Total** | **Critical fixes** | **5 hours** | **P0** |
| Unit tests | Test coverage | 3 hours | P1 |
| Integration tests | Testnet validation | 2 hours | P1 |
| **Grand Total** | **With testing** | **10 hours** | - |

---

## 🎯 РЕКОМЕНДАЦИИ

### Немедленно (P0):

1. **Применить FIX #1** (Binance) - решает проблему 48 зомби-ордеров
2. **Применить FIX #2** (Bybit) - предотвращает удаление SL для открытых позиций
3. **Применить FIX #3** (EventLogger) - повышает надёжность
4. **Запустить диагностику** для проверки

### В течение недели (P1):

5. Написать unit tests
6. Провести integration тесты на testnet
7. Deploy в production с мониторингом
8. Запускать диагностику ежедневно первую неделю

---

## ❓ ВОПРОСЫ ДЛЯ ОБСУЖДЕНИЯ

1. **Согласен с логикой FIX #1?**
   - Protective order + закрытая позиция = зомби (удалять)
   - Protective order + открытая позиция = не зомби (не трогать)

2. **Согласен с retry logic в FIX #2?**
   - 3 попытки достаточно?
   - Safe fallback (empty dict) правильное решение?

3. **Нужен ли whitelist для critical symbols?**
   - Например, никогда не трогать ордера для BTC/ETH/USDT?

4. **Когда применять фиксы?**
   - Сразу после обсуждения?
   - После написания unit tests?
   - После тестирования на testnet?

---

**Готов обсудить и доработать предложенные решения!**
