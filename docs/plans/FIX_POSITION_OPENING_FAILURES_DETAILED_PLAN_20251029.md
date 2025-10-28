# 🔴 ДЕТАЛЬНЫЙ ПЛАН УСТРАНЕНИЯ: Position Opening Failures

**Дата**: 2025-10-29
**Базовый документ**: `docs/investigations/POSITION_OPENING_FAILURE_ROOT_CAUSE_20251029.md`
**Статус**: ✅ ГОТОВ К РЕАЛИЗАЦИИ
**Критичность**: 🔴 CRITICAL - 67% failure rate в production

---

## 📋 Executive Summary

**Проблемы найдены**:
1. **RC#1 (VELVETUSDT/Binance)**: WebSocket НЕ синхронизирован с `self.positions` → verification timeout
2. **RC#2 (1000000BABYDOGEUSDT/Bybit)**: `fetch_order()` возвращает None из-за API lag → fallback на минимальный ответ без 'side'

**Решения**:
1. **Priority 1 (RC#2)**: Retry logic для `fetch_order()` с exponential backoff
2. **Priority 2 (RC#1)**: Изменение приоритета verification sources - Order Status становится PRIMARY

**Ожидаемый результат**: 100% success rate (10/10 тестов)

---

## 🎯 FIX #1: Bybit fetch_order Retry Logic (PRIORITY 1)

### Проблема

**Файл**: `core/atomic_position_manager.py:540-574`

**Текущее поведение**:
```python
# Wait для Bybit
wait_time = 0.5 if exchange == 'bybit' else 0.1
await asyncio.sleep(wait_time)

# Один вызов fetch_order
fetched_order = await exchange_instance.fetch_order(order_id, symbol)

if fetched_order:
    raw_order = fetched_order
else:
    logger.warning(f"⚠️ Fetch order returned None for {order_id}")
    # Fallback на минимальный create_order response БЕЗ 'side'
```

**Почему это fails**:
- Bybit API v5 имеет **propagation delay**
- 0.5s **НЕДОСТАТОЧНО** для появления ордера в системе
- Fallback на `create_order()` response БЕЗ поля 'side'
- `ExchangeResponseAdapter` выбрасывает `ValueError` (строка 119)

---

### Решение: Exponential Backoff Retry Logic

**Изменения в `core/atomic_position_manager.py:540-574`**:

```python
# BEFORE (строки 540-574)
if raw_order and raw_order.id:
    order_id = raw_order.id
    try:
        # Wait for order to be available in system
        wait_time = 0.5 if exchange == 'bybit' else 0.1
        await asyncio.sleep(wait_time)

        # Fetch complete order data
        fetched_order = await exchange_instance.fetch_order(order_id, symbol)

        if fetched_order:
            logger.info(f"✅ Fetched {exchange} order data: id={fetched_order.get('id')}, status={fetched_order.get('status')}, filled={fetched_order.get('filled')}/{fetched_order.get('amount')}")
            raw_order = fetched_order
        else:
            logger.warning(f"⚠️ Fetch order returned None for {order_id}")
            # Будет использован create_order response (может быть неполным)

    except Exception as e:
        logger.warning(f"⚠️ Failed to fetch order {order_id} status, using create response: {e}")
        # Будет использован create_order response

# AFTER (НОВЫЙ КОД С RETRY LOGIC)
if raw_order and raw_order.id:
    order_id = raw_order.id

    # FIX RC#2: Retry logic для fetch_order с exponential backoff
    # Bybit API v5 имеет propagation delay - 0.5s недостаточно
    max_retries = 5
    retry_delay = 0.5 if exchange == 'bybit' else 0.1

    fetched_order = None

    for attempt in range(1, max_retries + 1):
        try:
            # Wait before fetch attempt
            await asyncio.sleep(retry_delay)

            # Attempt to fetch complete order data
            fetched_order = await exchange_instance.fetch_order(order_id, symbol)

            if fetched_order:
                logger.info(
                    f"✅ Fetched {exchange} order on attempt {attempt}/{max_retries}: "
                    f"id={fetched_order.get('id')}, status={fetched_order.get('status')}, "
                    f"filled={fetched_order.get('filled')}/{fetched_order.get('amount')}, "
                    f"side={fetched_order.get('side')}"
                )
                raw_order = fetched_order
                break  # Success - exit retry loop
            else:
                logger.warning(
                    f"⚠️ Attempt {attempt}/{max_retries}: fetch_order returned None for {order_id}"
                )

                # Увеличиваем delay для следующей попытки (exponential backoff)
                if attempt < max_retries:
                    retry_delay *= 1.5  # 0.5s → 0.75s → 1.12s → 1.69s → 2.53s

        except Exception as e:
            logger.warning(
                f"⚠️ Attempt {attempt}/{max_retries}: fetch_order failed with error: {e}"
            )

            # Увеличиваем delay для следующей попытки
            if attempt < max_retries:
                retry_delay *= 1.5

    # После всех retries
    if not fetched_order:
        logger.error(
            f"❌ CRITICAL: fetch_order returned None after {max_retries} attempts for {order_id}!\n"
            f"  Exchange: {exchange}\n"
            f"  Symbol: {symbol}\n"
            f"  Total wait time: ~{sum([0.5 * (1.5 ** i) for i in range(max_retries)]):.2f}s\n"
            f"  Will attempt to use create_order response (may be incomplete).\n"
            f"  If this fails, position creation will rollback."
        )
        # Используем минимальный create_order response
        # ExchangeResponseAdapter может выбросить ValueError если нет 'side'
        # Это ПРАВИЛЬНОЕ поведение - лучше rollback чем создать позицию с unknown side
```

**Параметры retry logic**:
- **max_retries**: 5 попыток
- **initial_delay**: 0.5s для Bybit, 0.1s для Binance
- **backoff_factor**: 1.5 (exponential)
- **Total wait time**: ~7.7s (0.5s + 0.75s + 1.12s + 1.69s + 2.53s + execution time)

**Обоснование параметров**:
- 5 retries достаточно для Bybit API v5 propagation (обычно 1-3s)
- Exponential backoff предотвращает rate limiting
- Total ~7.7s МЕНЬШЕ чем verification timeout (10s)
- Для Binance начальный delay 0.1s (API быстрее)

---

### Тестирование FIX #1

**Test 1: Mock Bybit fetch_order to return None 3 times, then success**

```python
# tests/unit/test_bybit_fetch_order_retry.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.atomic_position_manager import AtomicPositionManager
from core.exchange_response_adapter import ExchangeResponseAdapter

@pytest.mark.asyncio
async def test_bybit_fetch_order_retry_success_on_attempt_4():
    """
    Test: fetch_order returns None 3 times, succeeds on 4th attempt
    Expected: Position created successfully with complete order data
    """

    # Mock exchange instance
    exchange_mock = AsyncMock()

    # Mock create_market_order to return minimal response (no 'side')
    minimal_order = {
        'id': 'test-order-123',
        'info': {'orderId': 'test-order-123'}
        # NO 'side', 'amount', 'filled' fields
    }
    exchange_mock.create_market_order.return_value = minimal_order

    # Mock fetch_order: None 3 times, then complete response
    complete_order = {
        'id': 'test-order-123',
        'status': 'closed',
        'side': 'buy',
        'amount': 100.0,
        'filled': 100.0,
        'average': 0.123,
        'symbol': 'TESTUSDT',
        'type': 'market',
        'info': {
            'orderId': 'test-order-123',
            'orderStatus': 'Filled',
            'side': 'Buy',
            'qty': '100',
            'cumExecQty': '100',
            'avgPrice': '0.123'
        }
    }

    exchange_mock.fetch_order = AsyncMock(
        side_effect=[None, None, None, complete_order]  # Fails 3 times, succeeds on 4th
    )

    # Mock other dependencies
    position_manager = MagicMock()
    position_manager.get_cached_position.return_value = None

    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager

    # Execute
    with patch('core.atomic_position_manager.ExchangeManager.get_instance') as exchange_getter:
        exchange_getter.return_value.get_exchange.return_value = exchange_mock

        # Should succeed on 4th attempt
        result = await apm.open_position_atomic(
            exchange='bybit',
            symbol='TESTUSDT',
            direction='buy',
            quantity=100.0,
            entry_price=0.123
        )

    # Assertions
    assert result is not None
    assert exchange_mock.fetch_order.call_count == 4  # Called 4 times
    assert result['side'] == 'buy'  # Has complete data
    assert result['filled'] == 100.0


@pytest.mark.asyncio
async def test_bybit_fetch_order_all_retries_fail():
    """
    Test: fetch_order returns None all 5 attempts
    Expected: Falls back to minimal response, ExchangeResponseAdapter raises ValueError
    """

    exchange_mock = AsyncMock()

    # Minimal response without 'side'
    minimal_order = {
        'id': 'test-order-456',
        'info': {'orderId': 'test-order-456'}
    }
    exchange_mock.create_market_order.return_value = minimal_order

    # All fetch_order attempts return None
    exchange_mock.fetch_order = AsyncMock(return_value=None)

    apm = AtomicPositionManager(db_pool=MagicMock())

    with patch('core.atomic_position_manager.ExchangeManager.get_instance') as exchange_getter:
        exchange_getter.return_value.get_exchange.return_value = exchange_mock

        # Should raise ValueError from ExchangeResponseAdapter
        with pytest.raises(ValueError, match="missing 'side' field"):
            await apm.open_position_atomic(
                exchange='bybit',
                symbol='TESTUSDT',
                direction='buy',
                quantity=100.0,
                entry_price=0.123
            )

    # Should have tried 5 times
    assert exchange_mock.fetch_order.call_count == 5
```

**Expected Test Results**:
- ✅ Test 1: PASS - Retry succeeds on 4th attempt
- ✅ Test 2: PASS - All retries fail, raises ValueError (expected)

---

## 🎯 FIX #2: Change Verification Source Priority (PRIORITY 2)

### Проблема

**Файл**: `core/atomic_position_manager.py:241-390`

**Текущее поведение**:
```
SOURCE 1 (PRIORITY 1): WebSocket position cache
SOURCE 2 (PRIORITY 2): Order status (fetch_order)
SOURCE 3 (PRIORITY 3): REST API (fetch_positions)
```

**Почему это fails (VELVETUSDT case)**:
1. WebSocket ПОЛУЧАЕТ events (mark_price updates)
2. НО позиция НЕ ДОБАВЛЯЕТСЯ в `self.positions`
3. `get_cached_position()` возвращает **None** (НЕ exception)
4. Source 1 помечается как tried
5. Source 2 **НЕ ВЫПОЛНЯЕТСЯ** (по непонятной причине - `sources_tried['order_status'] = False` в timeout)
6. Source 3 НЕ находит позицию
7. TIMEOUT через 10s

**Root Cause**: WebSocket НЕ НАДЕЖЕН для verification сразу после открытия позиции

---

### Решение: Order Status как PRIMARY Source

**Обоснование**:
- Order Status (fetch_order) - **САМЫЙ НАДЕЖНЫЙ** источник
- Если ордер исполнен (filled > 0), позиция **ГАРАНТИРОВАННО** создана
- WebSocket может иметь delay в обновлении `self.positions`
- REST API может иметь cache delay

**Изменения в `core/atomic_position_manager.py:241-390`**:

```python
# BEFORE: Текущий порядок sources
# SOURCE 1: WebSocket (PRIORITY 1)
# SOURCE 2: Order Status (PRIORITY 2)
# SOURCE 3: REST API (PRIORITY 3)

# AFTER: НОВЫЙ порядок sources (Order Status первым)
async def _verify_position_exists_multi_source(...):
    """
    FIX RC#1: Изменен приоритет verification sources

    НОВЫЙ ПОРЯДОК (от самого надежного к менее надежному):
    1. Order Status (fetch_order) - PRIMARY - ордер УЖЕ ИСПОЛНЕН
    2. WebSocket (get_cached_position) - SECONDARY - может иметь delay
    3. REST API (fetch_positions) - TERTIARY - fallback
    """

    sources_tried = {
        'order_status': False,  # ПРИОРИТЕТ 1 (БЫЛО 2)
        'websocket': False,     # ПРИОРИТЕТ 2 (БЫЛО 1)
        'rest_api': False       # ПРИОРИТЕТ 3 (БЕЗ ИЗМЕНЕНИЙ)
    }

    start_time = asyncio.get_event_loop().time()
    timeout = 10.0
    check_interval = 0.5

    logger.info(
        f"🔍 Multi-source position verification started (NEW PRIORITY ORDER)\n"
        f"  Symbol: {symbol}\n"
        f"  Exchange: {exchange}\n"
        f"  Expected quantity: {expected_quantity}\n"
        f"  Order ID: {entry_order.id if entry_order else 'N/A'}\n"
        f"  Priority: 1=OrderStatus, 2=WebSocket, 3=RestAPI"
    )

    while (asyncio.get_event_loop().time() - start_time) < timeout:

        # ============================================================
        # SOURCE 1 (PRIORITY 1): Order filled status
        # САМЫЙ НАДЕЖНЫЙ - ордер УЖЕ ИСПОЛНЕН в exchange
        # ============================================================
        if entry_order and not sources_tried['order_status']:
            try:
                logger.debug(f"🔍 [SOURCE 1/3] Checking order status for {entry_order.id}")

                # Fetch fresh order status
                order_status = await exchange_instance.fetch_order(entry_order.id, symbol)

                if order_status:
                    filled = float(order_status.get('filled', 0))
                    status = order_status.get('status', '')

                    logger.debug(
                        f"📊 Order status: id={entry_order.id}, status={status}, filled={filled}"
                    )

                    # Если ордер ИСПОЛНЕН - позиция ГАРАНТИРОВАННО создана
                    if filled > 0 and status in ['closed', 'filled']:
                        logger.info(
                            f"✅ [SOURCE 1] Order status CONFIRMED position exists!\n"
                            f"  Order ID: {entry_order.id}\n"
                            f"  Status: {status}\n"
                            f"  Filled: {filled}\n"
                            f"  Verification time: {asyncio.get_event_loop().time() - start_time:.2f}s"
                        )
                        return True  # SUCCESS!

                # Помечаем source как tried только после проверки
                sources_tried['order_status'] = True

            except Exception as e:
                logger.debug(f"⚠️ [SOURCE 1] Order status check failed: {e}")
                # НЕ помечаем как tried - будем retry в следующей итерации

        # ============================================================
        # SOURCE 2 (PRIORITY 2): WebSocket position updates
        # ВТОРИЧНЫЙ - может иметь delay в обновлении self.positions
        # ============================================================
        if self.position_manager and hasattr(self.position_manager, 'get_cached_position') and not sources_tried['websocket']:
            try:
                logger.debug(f"🔍 [SOURCE 2/3] Checking WebSocket cache for {symbol}")

                ws_position = self.position_manager.get_cached_position(symbol, exchange)

                if ws_position:
                    ws_quantity = float(ws_position.get('quantity', 0))
                    ws_side = ws_position.get('side', '')

                    logger.debug(
                        f"📊 WebSocket position: symbol={symbol}, quantity={ws_quantity}, side={ws_side}"
                    )

                    if ws_quantity > 0:
                        # Проверяем соответствие quantity
                        quantity_diff = abs(ws_quantity - expected_quantity)

                        if quantity_diff <= 0.01:  # Допускаем погрешность 0.01
                            logger.info(
                                f"✅ [SOURCE 2] WebSocket CONFIRMED position exists!\n"
                                f"  Symbol: {symbol}\n"
                                f"  Quantity: {ws_quantity} (expected: {expected_quantity})\n"
                                f"  Side: {ws_side}\n"
                                f"  Verification time: {asyncio.get_event_loop().time() - start_time:.2f}s"
                            )
                            return True  # SUCCESS!
                        else:
                            logger.warning(
                                f"⚠️ [SOURCE 2] WebSocket quantity mismatch!\n"
                                f"  Expected: {expected_quantity}\n"
                                f"  Got: {ws_quantity}\n"
                                f"  Difference: {quantity_diff}"
                            )

                # Помечаем source как tried
                sources_tried['websocket'] = True

            except AttributeError as e:
                logger.debug(f"⚠️ [SOURCE 2] WebSocket not available: {e}")
                sources_tried['websocket'] = True
            except Exception as e:
                logger.debug(f"⚠️ [SOURCE 2] WebSocket check failed: {e}")
                sources_tried['websocket'] = True

        # ============================================================
        # SOURCE 3 (PRIORITY 3): REST API fetch_positions
        # FALLBACK - может иметь cache delay
        # ============================================================
        if not sources_tried['rest_api']:
            try:
                logger.debug(f"🔍 [SOURCE 3/3] Checking REST API positions for {symbol}")

                # Fetch all open positions
                positions = await exchange_instance.fetch_positions([symbol])

                if positions:
                    # Find our position
                    for pos in positions:
                        pos_symbol = pos.get('symbol', '')
                        pos_contracts = float(pos.get('contracts', 0))

                        if pos_symbol == symbol and pos_contracts > 0:
                            logger.info(
                                f"✅ [SOURCE 3] REST API CONFIRMED position exists!\n"
                                f"  Symbol: {symbol}\n"
                                f"  Contracts: {pos_contracts}\n"
                                f"  Verification time: {asyncio.get_event_loop().time() - start_time:.2f}s"
                            )
                            return True  # SUCCESS!

                # Помечаем source как tried
                sources_tried['rest_api'] = True

            except Exception as e:
                logger.debug(f"⚠️ [SOURCE 3] REST API check failed: {e}")
                sources_tried['rest_api'] = True

        # Все sources tried?
        if all(sources_tried.values()):
            logger.warning(
                f"⚠️ All verification sources tried but position NOT found!\n"
                f"  This may indicate:\n"
                f"  1. Position not yet propagated to all systems (rare)\n"
                f"  2. Order executed but position closed immediately (very rare)\n"
                f"  3. System delay/lag\n"
                f"  Will continue checking until timeout..."
            )
            # Reset sources_tried для повторной проверки
            sources_tried = {k: False for k in sources_tried}

        # Wait before next check
        await asyncio.sleep(check_interval)

    # TIMEOUT - ни один source не подтвердил позицию
    logger.error(
        f"❌ Multi-source verification TIMEOUT after {timeout}s!\n"
        f"  Symbol: {symbol}\n"
        f"  Exchange: {exchange}\n"
        f"  Expected quantity: {expected_quantity}\n"
        f"  Sources tried:\n"
        f"    - Order status: {sources_tried['order_status']}\n"
        f"    - WebSocket: {sources_tried['websocket']}\n"
        f"    - REST API: {sources_tried['rest_api']}\n"
        f"  This is CRITICAL - position may exist but cannot be verified!"
    )

    return False
```

**Ключевые изменения**:
1. **Order Status теперь ПЕРВЫЙ source** (был второй)
2. **Более детальное логирование** каждого source
3. **Reset sources_tried** если все sources tried но позиция не найдена (retry)
4. **Улучшенные error messages** для диагностики

---

### Тестирование FIX #2

**Test 1: WebSocket delay, Order Status confirms immediately**

```python
# tests/unit/test_verification_priority_order_status_first.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.atomic_position_manager import AtomicPositionManager

@pytest.mark.asyncio
async def test_order_status_confirms_position_websocket_delayed():
    """
    Test: WebSocket has delay, Order Status confirms position immediately
    Expected: Verification succeeds via SOURCE 1 (Order Status)
    """

    # Mock exchange instance
    exchange_mock = AsyncMock()

    # Mock fetch_order to return filled order
    filled_order = {
        'id': 'order-789',
        'status': 'closed',
        'filled': 100.0,
        'side': 'buy'
    }
    exchange_mock.fetch_order.return_value = filled_order

    # Mock position_manager with WebSocket that returns None (delayed)
    position_manager_mock = MagicMock()
    position_manager_mock.get_cached_position.return_value = None  # WebSocket delay

    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager_mock

    # Execute verification
    with patch('core.atomic_position_manager.ExchangeManager.get_instance') as exchange_getter:
        exchange_getter.return_value.get_exchange.return_value = exchange_mock

        entry_order_mock = MagicMock()
        entry_order_mock.id = 'order-789'

        result = await apm._verify_position_exists_multi_source(
            symbol='TESTUSDT',
            exchange='binance',
            expected_quantity=100.0,
            entry_order=entry_order_mock,
            exchange_instance=exchange_mock
        )

    # Assertions
    assert result is True  # Verification succeeded
    assert exchange_mock.fetch_order.call_count >= 1  # Order Status called
    # WebSocket may or may not be called (depends on timing)


@pytest.mark.asyncio
async def test_all_sources_fail_timeout():
    """
    Test: All sources return None/fail
    Expected: Verification times out after 10s
    """

    exchange_mock = AsyncMock()
    exchange_mock.fetch_order.return_value = None  # Order Status returns None
    exchange_mock.fetch_positions.return_value = []  # REST API returns empty

    position_manager_mock = MagicMock()
    position_manager_mock.get_cached_position.return_value = None  # WebSocket returns None

    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager_mock

    import time
    start_time = time.time()

    with patch('core.atomic_position_manager.ExchangeManager.get_instance') as exchange_getter:
        exchange_getter.return_value.get_exchange.return_value = exchange_mock

        entry_order_mock = MagicMock()
        entry_order_mock.id = 'order-999'

        result = await apm._verify_position_exists_multi_source(
            symbol='TESTUSDT',
            exchange='binance',
            expected_quantity=100.0,
            entry_order=entry_order_mock,
            exchange_instance=exchange_mock
        )

    elapsed = time.time() - start_time

    # Assertions
    assert result is False  # Verification failed
    assert elapsed >= 10.0  # Timeout was 10s
    assert elapsed < 11.0  # Should not exceed timeout significantly
```

**Expected Test Results**:
- ✅ Test 1: PASS - Order Status confirms immediately (< 1s)
- ✅ Test 2: PASS - Timeout after 10s when all sources fail

---

## 🧪 Integration Tests (КРИТИЧНО - 10/10 Success Required)

**Файл**: `tests/integration/test_position_opening_full_cycle.py`

### Test Suite: 10 Position Opening Tests

```python
import pytest
from core.atomic_position_manager import AtomicPositionManager
from core.exchange_manager import ExchangeManager

@pytest.mark.asyncio
@pytest.mark.integration
class TestPositionOpeningFullCycle:
    """
    Integration tests для полного цикла открытия позиций
    ТРЕБОВАНИЕ: 10/10 тестов должны быть УСПЕШНЫ
    """

    async def test_01_binance_buy_market_order(self):
        """Test 1/10: Binance BUY market order"""
        apm = AtomicPositionManager(db_pool=get_db_pool())

        result = await apm.open_position_atomic(
            exchange='binance',
            symbol='BTCUSDT',  # Liquid pair
            direction='buy',
            quantity=0.001,    # Small quantity for test
            entry_price=None   # Market order
        )

        assert result is not None
        assert result['status'] == 'success'
        assert result['verified'] is True

    async def test_02_binance_sell_market_order(self):
        """Test 2/10: Binance SELL market order"""
        # Similar to test_01 but SELL
        pass

    async def test_03_bybit_buy_market_order(self):
        """Test 3/10: Bybit BUY market order"""
        apm = AtomicPositionManager(db_pool=get_db_pool())

        result = await apm.open_position_atomic(
            exchange='bybit',
            symbol='BTCUSDT',
            direction='buy',
            quantity=0.001,
            entry_price=None
        )

        assert result is not None
        assert result['status'] == 'success'
        assert result['verified'] is True
        # КРИТИЧНО: Проверяем что fetch_order retry сработал
        assert 'fetch_order_attempts' in result  # Новое поле для отслеживания

    async def test_04_bybit_sell_market_order(self):
        """Test 4/10: Bybit SELL market order"""
        pass

    async def test_05_binance_low_liquidity_pair(self):
        """Test 5/10: Binance с низколиквидным тикером"""
        # Тест на тикере с меньшей ликвидностью
        pass

    async def test_06_bybit_low_liquidity_pair(self):
        """Test 6/10: Bybit с низколиквидным тикером"""
        pass

    async def test_07_concurrent_binance_positions(self):
        """Test 7/10: Открытие 3 позиций одновременно на Binance"""
        # Проверяем race conditions
        pass

    async def test_08_concurrent_bybit_positions(self):
        """Test 8/10: Открытие 3 позиций одновременно на Bybit"""
        pass

    async def test_09_binance_with_stop_loss_verification(self):
        """Test 9/10: Binance с проверкой создания SL ордера"""
        pass

    async def test_10_bybit_with_stop_loss_verification(self):
        """Test 10/10: Bybit с проверкой создания SL ордера"""
        pass
```

**Команда запуска**:
```bash
pytest tests/integration/test_position_opening_full_cycle.py -v --asyncio-mode=auto
```

**Критерий успеха**: **10/10 PASSED** (100% success rate)

---

## 📊 Мониторинг после деплоя

### SQL Query для проверки failures

```sql
-- Проверка position opening failures в production
SELECT
    DATE(created_at) as date,
    event_type,
    COUNT(*) as count,
    JSON_AGG(
        JSON_BUILD_OBJECT(
            'symbol', event_data->>'symbol',
            'exchange', event_data->>'exchange',
            'error', event_data->>'error'
        )
    ) as details
FROM events
WHERE event_type IN ('position_error', 'signal_execution_failed', 'position_verification_timeout')
  AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY DATE(created_at), event_type
ORDER BY date DESC, count DESC;
```

### Логи для мониторинга

После деплоя должны **ИСЧЕЗНУТЬ** следующие логи:
```
❌ Multi-source verification TIMEOUT
⚠️ Fetch order returned None for {order_id}
❌ Order missing 'side' field
❌ Atomic position creation failed: Order missing 'side' field
```

Должны **ПОЯВИТЬСЯ** новые логи:
```
✅ Fetched bybit order on attempt 2/5: id=..., side=buy
✅ [SOURCE 1] Order status CONFIRMED position exists!
```

---

## 🚀 Deployment Plan

### Phase 1: Code Changes

1. **Изменить `core/atomic_position_manager.py`**:
   - Lines 540-574: Добавить retry logic для fetch_order
   - Lines 241-390: Изменить приоритет verification sources

2. **Добавить новое поле в результат**:
   - `fetch_order_attempts` (int) - количество попыток fetch_order

### Phase 2: Testing

1. **Unit Tests** (должны пройти 100%):
   ```bash
   pytest tests/unit/test_bybit_fetch_order_retry.py -v
   pytest tests/unit/test_verification_priority_order_status_first.py -v
   ```

2. **Integration Tests** (КРИТИЧНО - 10/10):
   ```bash
   pytest tests/integration/test_position_opening_full_cycle.py -v
   ```

### Phase 3: Staging Deployment

1. Deploy на staging окружение
2. Запустить 100 реальных сигналов
3. Проверить что 0 failures (100% success rate)
4. Мониторинг логов на наличие retry attempts

### Phase 4: Production Deployment

1. Deploy на production
2. **Canary deployment**: Сначала только 10% сигналов
3. Мониторинг первых 20 сигналов
4. Если 20/20 success → полный rollout
5. Если хотя бы 1 failure → ROLLBACK

### Rollback Plan

Если в production возникнут проблемы:
1. Откатить изменения в `atomic_position_manager.py`
2. Вернуть старую версию verification logic
3. Создать CRITICAL investigation для новой проблемы

---

## ✅ Критерии Успеха (Acceptance Criteria)

### Must Have (ОБЯЗАТЕЛЬНО)

1. ✅ **10/10 integration тестов PASSED** (100% success rate)
2. ✅ **0 логов "verification TIMEOUT"** в первых 100 production сигналах
3. ✅ **0 логов "fetch_order returned None"** после всех 5 retries
4. ✅ **0 логов "Order missing 'side' field"** в production

### Should Have (ЖЕЛАТЕЛЬНО)

1. ✅ **Среднее время verification < 2s** (было ~10s для failures)
2. ✅ **90%+ fetch_order успех на 1-й попытке** для Binance
3. ✅ **90%+ fetch_order успех на 1-3 попытках** для Bybit
4. ✅ **Логи retry attempts для анализа** Bybit API lag patterns

### Nice to Have (ХОРОШО БЫ)

1. ✅ **Метрики по retry attempts** (Grafana dashboard)
2. ✅ **Alerts если > 3 retries** для fetch_order
3. ✅ **Historical data по verification times**

---

## 📝 Заметки для Реализации

### Важные детали

1. **Exponential backoff НЕ БЛОКИРУЕТ** другие операции:
   - Используем `asyncio.sleep()` - асинхронный wait
   - Другие позиции могут открываться параллельно

2. **Total retry time (~7.7s) < verification timeout (10s)**:
   - Гарантирует что verification успеет проверить Order Status source

3. **ExchangeResponseAdapter.normalize_order() НЕ ИЗМЕНЯЕТСЯ**:
   - Его поведение (ValueError при отсутствии 'side') - ПРАВИЛЬНОЕ
   - Лучше rollback позиции чем создать с unknown side

4. **WebSocket position sync НЕ ФИКСИТСЯ**:
   - Изменение приоритета sources ОБХОДИТ эту проблему
   - WebSocket остается как SECONDARY source (backup)

### Потенциальные Edge Cases

1. **Что если Order Status тоже возвращает None?**
   - Маловероятно (ордер УЖЕ создан и исполнен)
   - Если происходит → WebSocket или REST API подхватят
   - Если все 3 sources fail → TIMEOUT (правильное поведение)

2. **Что если fetch_order возвращает order но без 'filled'?**
   - ExchangeResponseAdapter обработает (есть fallback на 'amount')
   - Verification проверит `status in ['closed', 'filled']`

3. **Что если Bybit API lag > 7.7s?**
   - Крайне маловероятно (обычно 1-3s)
   - Если происходит → WebSocket или REST API подхватят
   - Можно увеличить max_retries до 7 (total ~17s)

---

## 🎓 Lessons Learned

1. **Retry logic с exponential backoff** - стандартная практика для API с propagation delay
2. **Order Status - самый надежный source** для verification (ордер УЖЕ исполнен)
3. **WebSocket может иметь delay** - не полагаться на него для immediate verification
4. **Fail-fast лучше чем silent errors** - ExchangeResponseAdapter правильно выбрасывает ValueError

---

## 🔴 КРИТИЧНО: Что НЕ ДЕЛАТЬ

1. ❌ **НЕ УДАЛЯТЬ** ExchangeResponseAdapter validation для 'side' field
2. ❌ **НЕ УВЕЛИЧИВАТЬ** verification timeout > 10s (проблема не в этом)
3. ❌ **НЕ СОЗДАВАТЬ** позицию с unknown side (ломает rollback logic)
4. ❌ **НЕ ДЕПЛОИТЬ** в production без 10/10 integration тестов

---

**Статус плана**: ✅ ГОТОВ К РЕАЛИЗАЦИИ
**Next Step**: Создание unit tests и integration tests
**Требование перед реализацией**: 10/10 integration тестов должны пройти

---

**Автор**: Claude Code
**Дата**: 2025-10-29
**Базовый документ**: `docs/investigations/POSITION_OPENING_FAILURE_ROOT_CAUSE_20251029.md`
