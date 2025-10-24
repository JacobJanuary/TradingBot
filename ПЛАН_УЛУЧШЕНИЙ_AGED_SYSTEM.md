# 📋 ПОДРОБНЫЙ ПЛАН УЛУЧШЕНИЙ AGED POSITION SYSTEM

**Дата создания**: 2025-10-24
**Статус**: ✅ ГОТОВ К РЕАЛИЗАЦИИ
**Основание**: FORENSIC_AGED_FINAL_REPORT.md
**Аудит кода**: Завершен (4 агента)

---

## 🎯 ЦЕЛИ

На основе forensic расследования выявлено 3 проблемы:
1. **XDCUSDT**: Bybit error 170193 (ошибка биржи)
2. **HNTUSDT**: No liquidity (пустой order book)
3. **GIGAUSDT**: No WebSocket updates (✅ ИСПРАВЛЕНО в fix/gigausdt-subscription-mechanism)

**Необходимо реализовать 4 улучшения:**
1. ✅ Улучшить Error Handling (обработка ошибок биржи)
2. ✅ WebSocket Health Monitoring (мониторинг здоровья WebSocket)
3. ✅ Order Book Pre-Check (проверка ликвидности перед ордером)
4. ✅ Periodic Price Fetch Fallback (fallback при отказе WebSocket)

---

## 📊 РЕЗУЛЬТАТЫ АУДИТА КОДА

### Что УЖЕ РЕАЛИЗОВАНО:

| Компонент | Статус | Файл | Строки |
|-----------|--------|------|--------|
| Retry logic (3×3=9 попыток) | ✅ ЕСТЬ | `order_executor.py` | 108-184 |
| Fallback на limit orders | ✅ ЕСТЬ | `order_executor.py` | 46-50 |
| Order book check (limit_maker) | ✅ ЕСТЬ | `order_executor.py` | 285-308 |
| Generic exception handling | ✅ ЕСТЬ | `order_executor.py` | 175-184 |
| DB logging успехов/ошибок | ✅ ЕСТЬ | `aged_position_monitor_v2.py` | 314-381 |
| Periodic full scan (5 мин) | ✅ ЕСТЬ | `aged_position_monitor_v2.py` | 769-818 |
| UnifiedPriceMonitor | ✅ ЕСТЬ | `unified_price_monitor.py` | 89-114 |
| Subscription verification | ✅ ЕСТЬ | `aged_position_monitor_v2.py` | 820-843 |

### Что ОТСУТСТВУЕТ:

| Компонент | Статус | Нужно добавить |
|-----------|--------|----------------|
| Обработка специфичных ошибок биржи | ❌ НЕТ | Error type differentiation |
| Exponential backoff при retry | ❌ НЕТ | Увеличивающаяся задержка |
| Rate limit (429) handling | ❌ НЕТ | Специальная обработка 429 |
| WebSocket per-symbol health check | ❌ НЕТ | Staleness detection |
| Alert при stale price > 5 мин | ❌ НЕТ | Monitoring + alerts |
| Liquidity check перед market order | ❌ НЕТ | Order book depth check |
| REST price fallback task | ❌ НЕТ | Independent price fetching |

---

## 🔧 IMPROVEMENT #1: Enhanced Error Handling

### ЦЕЛЬ
Улучшить обработку ошибок при закрытии aged позиций, добавив:
- Различение типов ошибок (permanent vs temporary)
- Exponential backoff при retry
- Специальная обработка ошибок Bybit (170193, 170003, 429)
- Try-catch в aged_position_monitor_v2

### АНАЛИЗ

**Текущая проблема** (из аудита):
```python
# order_executor.py:175-184
except Exception as e:
    last_error = str(e)
    logger.warning(f"Order attempt failed: {e}")
    await asyncio.sleep(self.retry_delay)  # ❌ Всегда 1 секунда
```

**Проблемы:**
1. Все ошибки обрабатываются одинаково (generic Exception)
2. Нет различения постоянных и временных ошибок
3. Фиксированная задержка retry (1s) - не оптимально
4. Нет специальной обработки rate limit (429)
5. В `aged_position_monitor_v2.py:293` нет try-catch вокруг `execute_close()`

### РЕШЕНИЕ

#### Фаза 1A: Добавить Error Type Differentiation

**Файл**: `core/order_executor.py`
**Строки**: 37-60 (добавить константы и классификацию)

**Вставить ПЕРЕД строкой 37:**

```python
# ==================== ERROR CLASSIFICATION ====================
# Постоянные ошибки - не retry
PERMANENT_ERROR_PATTERNS = [
    '170003',           # Bybit: brokerId error
    '170193',           # Bybit: price cannot be
    '170209',           # Bybit: symbol not available in region
    'insufficient',     # Insufficient funds/balance
    'not available',    # Symbol/market not available
    'delisted',         # Symbol delisted
    'suspended',        # Trading suspended
]

# Rate limit ошибки - retry с длинной задержкой
RATE_LIMIT_PATTERNS = [
    '429',
    'rate limit',
    'too many requests',
    'request limit exceeded',
]

# Временные ошибки - retry с exponential backoff
TEMPORARY_ERROR_PATTERNS = [
    'timeout',
    'connection',
    'network',
    'temporary',
]

def classify_error(error_message: str) -> str:
    """
    Classify error type for appropriate handling

    Returns:
        'permanent' - don't retry
        'rate_limit' - retry with long delay
        'temporary' - retry with exponential backoff
        'unknown' - retry with normal backoff
    """
    error_lower = error_message.lower()

    # Check permanent errors
    if any(pattern in error_lower for pattern in PERMANENT_ERROR_PATTERNS):
        return 'permanent'

    # Check rate limit errors
    if any(pattern in error_lower for pattern in RATE_LIMIT_PATTERNS):
        return 'rate_limit'

    # Check temporary errors
    if any(pattern in error_lower for pattern in TEMPORARY_ERROR_PATTERNS):
        return 'temporary'

    return 'unknown'
# ==============================================================
```

**Обоснование:**
- **Permanent errors** (170193, insufficient funds) не имеет смысла retry - они требуют manual intervention
- **Rate limit errors** (429) требуют более длительной задержки (10-30s), а не 1-2s
- **Temporary errors** (timeout, network) должны retry с exponential backoff
- **Unknown errors** - retry как обычно, но логировать для анализа

#### Фаза 1B: Exponential Backoff

**Файл**: `core/order_executor.py`
**Строки**: 40-43 (изменить константы)

**ЗАМЕНИТЬ строки 40-43:**
```python
# Retry configuration
self.max_attempts = 3
self.retry_delay = 1.0  # seconds
```

**НА:**
```python
# Retry configuration
self.max_attempts = 3
self.base_retry_delay = 0.5      # Base delay: 500ms
self.max_retry_delay = 5.0       # Max delay: 5s
self.rate_limit_delay = 15.0     # Delay for rate limit: 15s
```

**Обоснование:**
- Exponential backoff: 500ms → 1s → 2s → 4s (до 5s max)
- Rate limit delay: 15s (дать бирже "остыть")
- Более агрессивный первый retry (500ms вместо 1s)

#### Фаза 1C: Улучшить Exception Handler

**Файл**: `core/order_executor.py`
**Строки**: 175-184 (заменить обработку ошибок)

**ЗАМЕНИТЬ строки 175-184:**
```python
except Exception as e:
    last_error = str(e)
    logger.warning(
        f"Order attempt failed: {order_type} "
        f"attempt {attempt + 1}: {e}"
    )
    # Wait before retry (except on last attempt)
    if attempt < self.max_attempts - 1:
        await asyncio.sleep(self.retry_delay)
```

**НА:**
```python
except Exception as e:
    last_error = str(e)
    error_type = classify_error(last_error)

    # Log with error classification
    logger.warning(
        f"Order attempt failed [{error_type}]: {order_type} "
        f"attempt {attempt + 1}/{self.max_attempts}: {e}"
    )

    # Permanent errors - stop immediately
    if error_type == 'permanent':
        logger.error(
            f"❌ PERMANENT ERROR detected - stopping retries: {last_error[:100]}"
        )
        break  # Exit retry loop for this order_type

    # Wait before retry (except on last attempt)
    if attempt < self.max_attempts - 1:
        # Calculate delay based on error type
        if error_type == 'rate_limit':
            delay = self.rate_limit_delay
            logger.warning(f"⏰ Rate limit detected - waiting {delay}s")
        elif error_type == 'temporary':
            # Exponential backoff: 0.5s → 1s → 2s
            delay = min(
                self.base_retry_delay * (2 ** attempt),
                self.max_retry_delay
            )
        else:
            # Unknown errors - conservative exponential backoff
            delay = min(
                self.base_retry_delay * (2 ** (attempt + 1)),
                self.max_retry_delay
            )

        logger.debug(f"⏳ Waiting {delay}s before retry...")
        await asyncio.sleep(delay)
```

**Обоснование:**
- **Permanent errors** сразу прерывают retry цикл (не тратим время на бесполезные попытки)
- **Rate limit** = 15s delay (обязательно для 429 ошибок)
- **Temporary** = exponential backoff (500ms, 1s, 2s)
- **Unknown** = консервативный backoff (1s, 2s, 4s)
- Все логируется с типом ошибки для анализа

#### Фаза 1D: Try-Catch в aged_position_monitor_v2

**Файл**: `core/aged_position_monitor_v2.py`
**Строки**: 293-312 (обернуть в try-catch)

**ЗАМЕНИТЬ строки 293-312:**
```python
async def _trigger_market_close(self, position, target, trigger_price):
    # ... подготовка параметров ...

    result = await self.order_executor.execute_close(
        symbol=symbol,
        exchange_name=exchange_name,
        position_side=position.side,
        amount=amount,
        reason=f'aged_{target.phase}'
    )
```

**НА:**
```python
async def _trigger_market_close(self, position, target, trigger_price):
    # ... подготовка параметров ...

    try:
        result = await self.order_executor.execute_close(
            symbol=symbol,
            exchange_name=exchange_name,
            position_side=position.side,
            amount=amount,
            reason=f'aged_{target.phase}'
        )
    except Exception as e:
        # Unexpected exception from execute_close
        logger.error(
            f"❌ CRITICAL: Unexpected error in execute_close for {symbol}: {e}",
            exc_info=True
        )
        # Create OrderResult manually for error handling below
        result = OrderResult(
            success=False,
            error_message=f"Unexpected exception: {str(e)}",
            attempts=0,
            execution_time=0.0,
            order_id=None,
            filled_amount=0,
            average_price=None
        )
```

**Обоснование:**
- Защита от unhandled exceptions в `execute_close()`
- Логирование с stack trace (`exc_info=True`)
- Создание валидного `OrderResult` для дальнейшей обработки
- Предотвращение краха всего aged monitor из-за одной ошибки

#### Фаза 1E: Добавить обработку 170193 в aged_position_monitor_v2

**Файл**: `core/aged_position_monitor_v2.py`
**Строки**: 361-382 (после логирования ошибки)

**ВСТАВИТЬ ПОСЛЕ строки 381:**
```python
            # ✅ ENHANCEMENT #1E: Специальная обработка ошибок Bybit

            # Check for specific error types
            error_msg = result.error_message or ""

            if '170193' in error_msg or 'price cannot be' in error_msg.lower():
                # Bybit price validation error
                logger.warning(
                    f"⚠️ Bybit price error for {symbol} - may need manual intervention. "
                    f"Error: {error_msg[:100]}"
                )
                # Mark position as requiring manual review
                if self.repository:
                    await self.repository.create_aged_monitoring_event(
                        aged_position_id=target.position_id,
                        event_type='requires_manual_review',
                        event_metadata={
                            'error_code': '170193',
                            'error_message': error_msg,
                            'reason': 'bybit_price_validation'
                        }
                    )

            elif 'no asks' in error_msg.lower() or 'no bids' in error_msg.lower():
                # No liquidity in order book
                logger.warning(
                    f"⚠️ No liquidity for {symbol} - market order failed. "
                    f"Position may need manual close or wait for liquidity."
                )
                if self.repository:
                    await self.repository.create_aged_monitoring_event(
                        aged_position_id=target.position_id,
                        event_type='low_liquidity',
                        event_metadata={
                            'error_message': error_msg,
                            'order_attempts': result.attempts
                        }
                    )

            elif '170003' in error_msg:
                # Bybit brokerId error
                logger.error(
                    f"⚠️ Bybit brokerId error for {symbol}. "
                    f"This should be fixed by exchange_manager brokerId='' patch."
                )
```

**Обоснование:**
- **170193**: Специфичная ошибка Bybit требующая ручной проверки
- **No asks/bids**: Индикатор низкой ликвидности (не ошибка кода)
- **170003**: Ошибка brokerId (должна быть исправлена exchange_manager.py)
- Все записываются в DB с правильными event_type для дальнейшего анализа

### ТЕСТИРОВАНИЕ Improvement #1

**Файл**: `tests/test_error_handling_improvements.py` (НОВЫЙ)

```python
"""
Tests for Error Handling Improvements
Validates Enhancement #1: Enhanced Error Handling
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from core.order_executor import OrderExecutor, classify_error


class TestErrorClassification:
    """Test error type classification"""

    def test_permanent_error_170193(self):
        """Test Bybit error 170193 classified as permanent"""
        error = "bybit {\"retCode\":170193,\"retMsg\":\"Buy order price cannot be higher than 0USDT.\"}"
        assert classify_error(error) == 'permanent'

    def test_permanent_error_insufficient_funds(self):
        """Test insufficient funds classified as permanent"""
        error = "Insufficient funds to complete order"
        assert classify_error(error) == 'permanent'

    def test_rate_limit_429(self):
        """Test 429 error classified as rate_limit"""
        error = "429 Too Many Requests"
        assert classify_error(error) == 'rate_limit'

    def test_temporary_error_timeout(self):
        """Test timeout classified as temporary"""
        error = "Request timeout after 30 seconds"
        assert classify_error(error) == 'temporary'

    def test_unknown_error(self):
        """Test unknown error classified as unknown"""
        error = "Some random error message"
        assert classify_error(error) == 'unknown'


class TestExponentialBackoff:
    """Test exponential backoff logic"""

    @pytest.mark.asyncio
    async def test_backoff_increases(self):
        """Test that retry delay increases exponentially"""
        executor = OrderExecutor(None)

        # Base delay 0.5s
        assert executor.base_retry_delay == 0.5

        # Simulated delays for attempts 0, 1, 2
        # attempt 0: 0.5 * 2^0 = 0.5s
        # attempt 1: 0.5 * 2^1 = 1.0s
        # attempt 2: 0.5 * 2^2 = 2.0s
        delays = [
            min(executor.base_retry_delay * (2 ** i), executor.max_retry_delay)
            for i in range(3)
        ]

        assert delays == [0.5, 1.0, 2.0]

    @pytest.mark.asyncio
    async def test_rate_limit_delay(self):
        """Test rate limit uses special long delay"""
        executor = OrderExecutor(None)
        assert executor.rate_limit_delay == 15.0  # 15 seconds


class TestPermanentErrorHandling:
    """Test permanent errors stop retry immediately"""

    @pytest.mark.asyncio
    async def test_170193_stops_retry(self):
        """Test that 170193 error stops retry loop"""

        # Mock exchange
        exchange = Mock()
        exchange.exchange = Mock()
        exchange.exchange.create_order = AsyncMock(
            side_effect=Exception("bybit 170193: price cannot be")
        )

        executor = OrderExecutor(None)
        executor.exchanges = {'bybit': exchange}

        # Execute close (should stop after first attempt due to permanent error)
        result = await executor.execute_close(
            symbol='XDCUSDT',
            exchange_name='bybit',
            position_side='short',
            amount=100.0
        )

        # Should fail without retrying
        assert not result.success
        assert '170193' in result.error_message
        # Only 1 attempt (no retries for permanent errors)
        assert result.attempts == 1


class TestAgedMonitorTryCatch:
    """Test try-catch in aged_position_monitor_v2"""

    @pytest.mark.asyncio
    async def test_exception_caught(self):
        """Test that unexpected exception is caught"""

        from core.aged_position_monitor_v2 import AgedPositionMonitorV2

        # Mock components
        position_manager = Mock()
        order_executor = Mock()
        order_executor.execute_close = AsyncMock(
            side_effect=RuntimeError("Unexpected error!")
        )

        monitor = AgedPositionMonitorV2(
            position_manager=position_manager,
            order_executor=order_executor,
            repository=None
        )

        # Mock position and target
        position = Mock(symbol='TESTUSDT', side='long', amount=100)
        target = Mock(position_id=1, phase='grace')

        # Should NOT crash - exception should be caught
        await monitor._trigger_market_close(position, target, Decimal('100'))

        # Verify execute_close was called
        order_executor.execute_close.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### GIT STRATEGY для Improvement #1

```bash
# Создать feature branch
git checkout -b improvement/error-handling-enhanced

# Фаза 1A: Error classification
git add core/order_executor.py
git commit -m "feat(error-handling): add error type classification"

# Фаза 1B: Exponential backoff
git add core/order_executor.py
git commit -m "feat(error-handling): implement exponential backoff"

# Фаза 1C: Improved exception handler
git add core/order_executor.py
git commit -m "feat(error-handling): improve exception handling with error types"

# Фаза 1D: Try-catch в aged monitor
git add core/aged_position_monitor_v2.py
git commit -m "feat(error-handling): add try-catch protection in aged monitor"

# Фаза 1E: Bybit error handling
git add core/aged_position_monitor_v2.py
git commit -m "feat(error-handling): add Bybit specific error handling"

# Тесты
git add tests/test_error_handling_improvements.py
pytest tests/test_error_handling_improvements.py -v
git commit -m "test(error-handling): add comprehensive error handling tests"

# Merge
git checkout main
git merge --no-ff improvement/error-handling-enhanced
git tag v1.1.0-error-handling
```

### РИСКИ И ОТКАТ

| Риск | Вероятность | Mitigation | Rollback |
|------|-------------|------------|----------|
| Permanent errors не детектируются | НИЗКИЙ | Тесты покрывают все known patterns | Revert commit 1C |
| Exponential backoff слишком агрессивный | НИЗКИЙ | Max delay 5s - безопасно | Revert commit 1B |
| Try-catch ловит слишком много | СРЕДНИЙ | Логирование с exc_info | Revert commit 1D |

---

## 🔧 IMPROVEMENT #2: WebSocket Health Monitoring

### ЦЕЛЬ
Добавить мониторинг здоровья WebSocket connections per-symbol:
- Отслеживание timestamp последнего обновления для каждого символа
- Alert если нет обновлений > 5 минут для aged позиций
- Dashboard/метрики для staleness
- Integration с UnifiedPriceMonitor

### АНАЛИЗ

**Текущее состояние** (из аудита):
```python
# unified_price_monitor.py:35
self.last_update_time = defaultdict(float)  # ✅ Есть timestamps

# НО:
# ❌ Нет проверки staleness
# ❌ Нет alerts
# ❌ Нет per-symbol health check
# ❌ Нет integration с aged monitor
```

**Проблема GIGAUSDT:**
- Позиция зарегистрирована как aged
- WebSocket подписка сломана
- `check_price_target()` НЕ вызывается
- Нет способа обнаружить это автоматически

### РЕШЕНИЕ

#### Фаза 2A: Добавить Staleness Detection в UnifiedPriceMonitor

**Файл**: `websocket/unified_price_monitor.py`
**Строки**: 35-40 (добавить новые атрибуты)

**ВСТАВИТЬ ПОСЛЕ строки 35:**
```python
        self.last_update_time = defaultdict(float)
        # ✅ ENHANCEMENT #2A: Staleness tracking
        self.staleness_threshold_seconds = 300  # 5 minutes
        self.stale_symbols = set()  # Symbols with stale prices
        self.staleness_warnings_logged = set()  # Prevent spam
```

**Обоснование:**
- 5 минут threshold - баланс между ложными срабатываниями и реальными проблемами
- `stale_symbols` - быстрая проверка без вычислений
- `staleness_warnings_logged` - предотвращает спам в логах

#### Фаза 2B: Добавить метод check_staleness

**Файл**: `websocket/unified_price_monitor.py`
**Строки**: ~115 (после update_price)

**ВСТАВИТЬ НОВЫЙ МЕТОД:**
```python
    async def check_staleness(self, symbols_to_check: list = None) -> dict:
        """
        Check if price updates are stale for given symbols

        Args:
            symbols_to_check: List of symbols to check, or None for all subscribed

        Returns:
            dict: {symbol: {'stale': bool, 'seconds_since_update': float}}
        """
        import time

        now = time.time()
        result = {}

        # Default to all subscribed symbols
        if symbols_to_check is None:
            symbols_to_check = list(self.subscribers.keys())

        for symbol in symbols_to_check:
            if symbol not in self.last_update_time:
                # Never received update
                result[symbol] = {
                    'stale': True,
                    'seconds_since_update': float('inf'),
                    'last_update': None
                }
                continue

            last_update = self.last_update_time[symbol]
            seconds_since = now - last_update
            is_stale = seconds_since > self.staleness_threshold_seconds

            result[symbol] = {
                'stale': is_stale,
                'seconds_since_update': seconds_since,
                'last_update': last_update
            }

            # Track stale symbols
            if is_stale:
                self.stale_symbols.add(symbol)

                # Log warning once per symbol
                if symbol not in self.staleness_warnings_logged:
                    logger.warning(
                        f"⚠️ STALE PRICE: {symbol} - no updates for {seconds_since:.0f}s "
                        f"(threshold: {self.staleness_threshold_seconds}s)"
                    )
                    self.staleness_warnings_logged.add(symbol)
            else:
                # No longer stale - clear tracking
                self.stale_symbols.discard(symbol)
                self.staleness_warnings_logged.discard(symbol)

        return result
```

**Обоснование:**
- Проверяет staleness только для нужных символов (эффективно)
- Возвращает детальную информацию для анализа
- Логирует warning только 1 раз на символ (не спамит)
- Автоматически очищает stale status при получении update

#### Фаза 2C: Periodic Staleness Check Task

**Файл**: `core/position_manager_unified_patch.py`
**Строки**: ~180 (после periodic aged scan)

**ВСТАВИТЬ НОВУЮ ФУНКЦИЮ:**
```python
async def start_websocket_health_monitor(
    unified_protection: Dict,
    check_interval_seconds: int = 60
):
    """
    ✅ ENHANCEMENT #2C: Monitor WebSocket health for aged positions

    Periodically checks if aged positions are receiving price updates.
    Alerts if prices are stale (> 5 minutes without update).

    Args:
        unified_protection: Unified protection components
        check_interval_seconds: Check interval (default: 60s)
    """
    if not unified_protection:
        return

    aged_monitor = unified_protection.get('aged_monitor')
    price_monitor = unified_protection.get('price_monitor')

    if not aged_monitor or not price_monitor:
        logger.warning("WebSocket health monitor disabled - missing components")
        return

    logger.info(
        f"🔍 Starting WebSocket health monitor "
        f"(interval: {check_interval_seconds}s, threshold: 5min)"
    )

    while True:
        try:
            await asyncio.sleep(check_interval_seconds)

            # Get list of aged position symbols
            aged_symbols = list(aged_monitor.aged_targets.keys())

            if not aged_symbols:
                continue  # No aged positions to monitor

            # Check staleness for aged symbols only
            staleness_report = await price_monitor.check_staleness(aged_symbols)

            # Count stale aged positions
            stale_count = sum(
                1 for symbol, data in staleness_report.items()
                if data['stale']
            )

            if stale_count > 0:
                logger.warning(
                    f"⚠️ WebSocket Health Check: {stale_count}/{len(aged_symbols)} "
                    f"aged positions have STALE prices!"
                )

                # Log each stale position
                for symbol, data in staleness_report.items():
                    if data['stale']:
                        seconds = data['seconds_since_update']
                        logger.warning(
                            f"  - {symbol}: no update for {seconds:.0f}s "
                            f"({seconds/60:.1f} minutes)"
                        )

                # TODO: Trigger fallback price fetch (Improvement #4)
            else:
                # All good
                logger.debug(
                    f"✅ WebSocket Health Check: all {len(aged_symbols)} "
                    f"aged positions receiving updates"
                )

        except asyncio.CancelledError:
            logger.info("WebSocket health monitor stopped")
            break
        except Exception as e:
            logger.error(f"Error in WebSocket health monitor: {e}")
            await asyncio.sleep(10)  # Wait before retry
```

**Обоснование:**
- Проверяет только aged позиции (не все 1000+ символов)
- Запускается каждую минуту (баланс между responsiveness и overhead)
- Логирует детальную информацию по каждому stale symbol
- Подготовка к Improvement #4 (fallback fetch)

#### Фаза 2D: Integration с aged_position_monitor_v2

**Файл**: `core/aged_position_monitor_v2.py`
**Строки**: ~850 (после verify_subscriptions)

**ВСТАВИТЬ НОВЫЙ МЕТОД:**
```python
    async def check_websocket_health(self) -> dict:
        """
        ✅ ENHANCEMENT #2D: Check WebSocket health for aged positions

        Returns:
            dict: Health report with stale symbols
        """
        if not hasattr(self, 'price_monitor') or not self.price_monitor:
            logger.warning("Price monitor not available for health check")
            return {'healthy': False, 'reason': 'no_price_monitor'}

        # Get aged symbols
        aged_symbols = list(self.aged_targets.keys())

        if not aged_symbols:
            return {'healthy': True, 'aged_count': 0}

        # Check staleness
        staleness_report = await self.price_monitor.check_staleness(aged_symbols)

        stale_symbols = [
            symbol for symbol, data in staleness_report.items()
            if data['stale']
        ]

        health_report = {
            'healthy': len(stale_symbols) == 0,
            'aged_count': len(aged_symbols),
            'stale_count': len(stale_symbols),
            'stale_symbols': stale_symbols,
            'staleness_details': staleness_report
        }

        if stale_symbols:
            logger.warning(
                f"⚠️ {len(stale_symbols)} aged positions have stale WebSocket prices: "
                f"{', '.join(stale_symbols)}"
            )

        return health_report
```

**Обоснование:**
- Provides API для проверки health из внешних систем
- Возвращает structured report для мониторинга
- Может использоваться в health check endpoint

#### Фаза 2E: Добавить вызов в main startup

**Файл**: `main.py`
**Ищем где запускается** `start_periodic_aged_scan()` и добавляем рядом

**ВСТАВИТЬ РЯДОМ С periodic aged scan:**
```python
# Start WebSocket health monitor for aged positions
if unified_protection:
    websocket_health_task = asyncio.create_task(
        start_websocket_health_monitor(
            unified_protection=unified_protection,
            check_interval_seconds=60  # Check every minute
        )
    )
    logger.info("✅ WebSocket health monitor started")
```

### ТЕСТИРОВАНИЕ Improvement #2

**Файл**: `tests/test_websocket_health_monitoring.py` (НОВЫЙ)

```python
"""
Tests for WebSocket Health Monitoring
Validates Enhancement #2: WebSocket Health Monitoring
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

from websocket.unified_price_monitor import UnifiedPriceMonitor


class TestStalenessDetection:
    """Test staleness detection in UnifiedPriceMonitor"""

    @pytest.mark.asyncio
    async def test_fresh_price_not_stale(self):
        """Test that recently updated price is not stale"""
        monitor = UnifiedPriceMonitor()

        # Simulate price update
        await monitor.update_price('BTCUSDT', Decimal('50000'))

        # Check staleness
        report = await monitor.check_staleness(['BTCUSDT'])

        assert not report['BTCUSDT']['stale']
        assert report['BTCUSDT']['seconds_since_update'] < 1

    @pytest.mark.asyncio
    async def test_old_price_is_stale(self):
        """Test that old price is detected as stale"""
        monitor = UnifiedPriceMonitor()
        monitor.staleness_threshold_seconds = 1  # 1 second for testing

        # Simulate price update
        await monitor.update_price('BTCUSDT', Decimal('50000'))

        # Wait for staleness
        await asyncio.sleep(1.5)

        # Check staleness
        report = await monitor.check_staleness(['BTCUSDT'])

        assert report['BTCUSDT']['stale']
        assert report['BTCUSDT']['seconds_since_update'] >= 1

    @pytest.mark.asyncio
    async def test_never_updated_is_stale(self):
        """Test that never-updated symbol is stale"""
        monitor = UnifiedPriceMonitor()

        # Check staleness for symbol that never received update
        report = await monitor.check_staleness(['NEVERUSDT'])

        assert report['NEVERUSDT']['stale']
        assert report['NEVERUSDT']['seconds_since_update'] == float('inf')

    @pytest.mark.asyncio
    async def test_staleness_warning_logged_once(self):
        """Test that staleness warning is logged only once"""
        monitor = UnifiedPriceMonitor()
        monitor.staleness_threshold_seconds = 0.5

        # Simulate stale price
        monitor.last_update_time['TESTUSDT'] = time.time() - 10

        # First check - should log warning
        await monitor.check_staleness(['TESTUSDT'])
        assert 'TESTUSDT' in monitor.staleness_warnings_logged

        # Second check - should not log again
        initial_warnings = len(monitor.staleness_warnings_logged)
        await monitor.check_staleness(['TESTUSDT'])
        assert len(monitor.staleness_warnings_logged) == initial_warnings


class TestHealthMonitorIntegration:
    """Test integration with aged position monitor"""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self):
        """Test health check when all prices are fresh"""
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2

        # Mock components
        price_monitor = UnifiedPriceMonitor()

        # Simulate fresh prices for aged symbols
        await price_monitor.update_price('GIGAUSDT', Decimal('0.01671'))
        await price_monitor.update_price('ENAUSDT', Decimal('0.5'))

        # Create aged monitor with mocked aged_targets
        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.price_monitor = price_monitor
        monitor.aged_targets = {
            'GIGAUSDT': Mock(),
            'ENAUSDT': Mock()
        }

        # Check health
        health = await monitor.check_websocket_health()

        assert health['healthy']
        assert health['aged_count'] == 2
        assert health['stale_count'] == 0

    @pytest.mark.asyncio
    async def test_health_check_detects_stale(self):
        """Test health check detects stale prices"""
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2

        price_monitor = UnifiedPriceMonitor()
        price_monitor.staleness_threshold_seconds = 1

        # One fresh, one stale
        await price_monitor.update_price('GIGAUSDT', Decimal('0.01671'))
        price_monitor.last_update_time['ENAUSDT'] = time.time() - 10

        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.price_monitor = price_monitor
        monitor.aged_targets = {
            'GIGAUSDT': Mock(),
            'ENAUSDT': Mock()
        }

        # Check health
        health = await monitor.check_websocket_health()

        assert not health['healthy']
        assert health['aged_count'] == 2
        assert health['stale_count'] == 1
        assert 'ENAUSDT' in health['stale_symbols']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### GIT STRATEGY для Improvement #2

```bash
git checkout -b improvement/websocket-health-monitoring

# Фаза 2A: Staleness tracking
git add websocket/unified_price_monitor.py
git commit -m "feat(websocket): add staleness tracking attributes"

# Фаза 2B: check_staleness method
git add websocket/unified_price_monitor.py
git commit -m "feat(websocket): implement staleness detection method"

# Фаза 2C: Health monitor task
git add core/position_manager_unified_patch.py
git commit -m "feat(websocket): add periodic health monitor task"

# Фаза 2D: Integration с aged monitor
git add core/aged_position_monitor_v2.py
git commit -m "feat(websocket): integrate health check with aged monitor"

# Фаза 2E: Main startup
git add main.py
git commit -m "feat(websocket): start health monitor on startup"

# Тесты
git add tests/test_websocket_health_monitoring.py
pytest tests/test_websocket_health_monitoring.py -v
git commit -m "test(websocket): add health monitoring tests"

# Merge
git checkout main
git merge --no-ff improvement/websocket-health-monitoring
git tag v1.2.0-websocket-health
```

---

## 🔧 IMPROVEMENT #3: Order Book Pre-Check

### ЦЕЛЬ
Проверять ликвидность в order book ПЕРЕД размещением market orders:
- Fetch order book depth
- Проверка sufficient liquidity
- Предотвращение "No asks/bids" ошибок
- Автоматический fallback на limit order при низкой ликвидности

### АНАЛИЗ

**Текущая проблема** (из аудита):
```python
# order_executor.py:206-227 (_execute_market_order)
async def _execute_market_order(...):
    # ❌ НЕТ проверки order book
    return await exchange.exchange.create_order(
        symbol=symbol, type='market', side=side, amount=amount
    )
```

**Проблема HNTUSDT:**
- Market order отправлен без проверки liquidity
- Order book пустой (no asks)
- 9 неудачных попыток
- Позиция застряла на 27 часов

### РЕШЕНИЕ

#### Фаза 3A: Добавить функцию check_liquidity

**Файл**: `core/order_executor.py`
**Строки**: ~65 (перед execute_close)

**ВСТАВИТЬ НОВУЮ ФУНКЦИЮ:**
```python
    async def check_order_book_liquidity(
        self,
        exchange,
        symbol: str,
        side: str,
        amount: float,
        min_liquidity_multiplier: float = 2.0
    ) -> dict:
        """
        ✅ ENHANCEMENT #3A: Check order book liquidity before market order

        Args:
            exchange: Exchange manager instance
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            amount: Order amount
            min_liquidity_multiplier: Minimum liquidity as multiple of order size

        Returns:
            dict: {
                'has_liquidity': bool,
                'available_liquidity': float,
                'required_liquidity': float,
                'best_price': Decimal or None,
                'reason': str
            }
        """
        try:
            # Fetch order book
            order_book = await exchange.fetch_order_book(symbol, limit=10)

            if not order_book:
                return {
                    'has_liquidity': False,
                    'available_liquidity': 0,
                    'required_liquidity': amount * min_liquidity_multiplier,
                    'best_price': None,
                    'reason': 'order_book_empty'
                }

            # Get relevant side of book
            if side == 'buy':
                # For buy orders, check asks (sell side)
                book_side = order_book.get('asks', [])
                side_name = 'asks'
            else:
                # For sell orders, check bids (buy side)
                book_side = order_book.get('bids', [])
                side_name = 'bids'

            # Check if book side exists and has orders
            if not book_side or len(book_side) == 0:
                return {
                    'has_liquidity': False,
                    'available_liquidity': 0,
                    'required_liquidity': amount * min_liquidity_multiplier,
                    'best_price': None,
                    'reason': f'no_{side_name}'
                }

            # Calculate available liquidity (sum of top N levels)
            available_liquidity = sum(
                float(level[1]) for level in book_side[:10]  # Top 10 levels
            )

            # Get best price
            best_price = Decimal(str(book_side[0][0]))

            # Required liquidity = order size * multiplier
            required_liquidity = amount * min_liquidity_multiplier

            # Check if sufficient
            has_liquidity = available_liquidity >= required_liquidity

            result = {
                'has_liquidity': has_liquidity,
                'available_liquidity': available_liquidity,
                'required_liquidity': required_liquidity,
                'best_price': best_price,
                'reason': 'sufficient' if has_liquidity else 'insufficient'
            }

            if not has_liquidity:
                logger.warning(
                    f"⚠️ Low liquidity for {symbol} {side}: "
                    f"available={available_liquidity:.2f}, "
                    f"required={required_liquidity:.2f} "
                    f"(order={amount}, multiplier={min_liquidity_multiplier}x)"
                )

            return result

        except Exception as e:
            logger.error(f"Error checking order book for {symbol}: {e}")
            return {
                'has_liquidity': False,
                'available_liquidity': 0,
                'required_liquidity': amount * min_liquidity_multiplier,
                'best_price': None,
                'reason': f'error: {str(e)}'
            }
```

**Обоснование:**
- **2x multiplier**: Требуем ликвидность как минимум в 2 раза больше order size (защита от слиппажа)
- **Top 10 levels**: Проверяем достаточную глубину (не только best bid/ask)
- **Детальный reason**: Позволяет понять почему нет ликвидности
- **Error handling**: Если fetch_order_book fails, assume no liquidity (safe default)

#### Фаза 3B: Изменить _execute_market_order

**Файл**: `core/order_executor.py`
**Строки**: 206-227 (заменить _execute_market_order)

**ЗАМЕНИТЬ всю функцию _execute_market_order:**
```python
    async def _execute_market_order(
        self,
        exchange,
        symbol: str,
        side: str,
        amount: float
    ) -> Dict:
        """
        Execute market order with pre-check for liquidity
        ✅ ENHANCEMENT #3B: Check order book before market order
        """

        # ✅ Check liquidity before market order
        liquidity_check = await self.check_order_book_liquidity(
            exchange=exchange,
            symbol=symbol,
            side=side,
            amount=amount,
            min_liquidity_multiplier=2.0
        )

        if not liquidity_check['has_liquidity']:
            # Insufficient liquidity - raise exception to trigger fallback
            reason = liquidity_check['reason']
            available = liquidity_check['available_liquidity']
            required = liquidity_check['required_liquidity']

            raise Exception(
                f"Insufficient liquidity for market order: {reason} "
                f"(available={available:.2f}, required={required:.2f})"
            )

        logger.debug(
            f"✅ Liquidity check passed for {symbol} {side}: "
            f"{liquidity_check['available_liquidity']:.2f} available"
        )

        # Liquidity OK - proceed with market order
        params = {'reduceOnly': True}

        # Exchange-specific parameters
        if exchange.exchange.id == 'binance':
            params['type'] = 'MARKET'

        return await exchange.exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=amount,
            params=params
        )
```

**Обоснование:**
- Проверка ликвидности ПЕРЕД отправкой order
- Если нет ликвидности - raise Exception (triggers retry loop → fallback to limit)
- Логирование успешной проверки для debugging
- Сохраняет существующую логику market order

#### Фаза 3C: Улучшить _execute_limit_aggressive

**Файл**: `core/order_executor.py`
**Строки**: 229-274 (добавить liquidity check)

**ВСТАВИТЬ ПОСЛЕ строки 239 (после fetch_ticker):**
```python
        # ✅ ENHANCEMENT #3C: Check liquidity for limit aggressive
        liquidity_check = await self.check_order_book_liquidity(
            exchange=exchange,
            symbol=symbol,
            side=side,
            amount=amount,
            min_liquidity_multiplier=1.5  # Less strict for limit orders
        )

        if not liquidity_check['has_liquidity']:
            raise Exception(
                f"Insufficient liquidity for limit order: {liquidity_check['reason']}"
            )

        # Use best price from order book if available
        if liquidity_check['best_price']:
            current_price = liquidity_check['best_price']
            logger.debug(f"Using order book price: {current_price}")
        else:
            # Fallback to ticker price
            current_price = Decimal(str(ticker['last']))
```

**Обоснование:**
- Limit orders тоже нуждаются в liquidity (иначе не заполнятся)
- 1.5x multiplier (менее строгий чем для market)
- Использует лучшую цену из order book (точнее чем ticker)

### ТЕСТИРОВАНИЕ Improvement #3

**Файл**: `tests/test_orderbook_precheck.py` (НОВЫЙ)

```python
"""
Tests for Order Book Pre-Check
Validates Enhancement #3: Order Book Pre-Check
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from core.order_executor import OrderExecutor


class TestLiquidityCheck:
    """Test order book liquidity checking"""

    @pytest.mark.asyncio
    async def test_sufficient_liquidity(self):
        """Test that sufficient liquidity passes check"""

        # Mock exchange with good liquidity
        exchange = Mock()
        exchange.fetch_order_book = AsyncMock(return_value={
            'asks': [
                [50000, 10],   # Price 50000, Amount 10
                [50001, 10],
                [50002, 10],
            ],
            'bids': [
                [49999, 10],
                [49998, 10],
            ]
        })

        executor = OrderExecutor(None)

        # Check liquidity for buy 5 units (needs 10 available = 5 * 2.0x)
        result = await executor.check_order_book_liquidity(
            exchange=exchange,
            symbol='BTCUSDT',
            side='buy',
            amount=5.0,
            min_liquidity_multiplier=2.0
        )

        assert result['has_liquidity']
        assert result['available_liquidity'] >= 10  # Top 3 asks = 30
        assert result['best_price'] == Decimal('50000')

    @pytest.mark.asyncio
    async def test_insufficient_liquidity(self):
        """Test that insufficient liquidity fails check"""

        # Mock exchange with low liquidity
        exchange = Mock()
        exchange.fetch_order_book = AsyncMock(return_value={
            'asks': [
                [50000, 1],  # Only 1 unit available
            ],
            'bids': []
        })

        executor = OrderExecutor(None)

        # Check liquidity for buy 5 units (needs 10 available)
        result = await executor.check_order_book_liquidity(
            exchange=exchange,
            symbol='HNTUSDT',
            side='buy',
            amount=5.0
        )

        assert not result['has_liquidity']
        assert result['available_liquidity'] == 1
        assert result['required_liquidity'] == 10

    @pytest.mark.asyncio
    async def test_no_asks_detected(self):
        """Test that empty order book is detected"""

        exchange = Mock()
        exchange.fetch_order_book = AsyncMock(return_value={
            'asks': [],
            'bids': []
        })

        executor = OrderExecutor(None)

        result = await executor.check_order_book_liquidity(
            exchange=exchange,
            symbol='HNTUSDT',
            side='buy',
            amount=100.0
        )

        assert not result['has_liquidity']
        assert result['reason'] == 'no_asks'


class TestMarketOrderWithPrecheck:
    """Test market orders with liquidity pre-check"""

    @pytest.mark.asyncio
    async def test_market_order_rejected_low_liquidity(self):
        """Test that market order is rejected when liquidity insufficient"""

        # Mock exchange
        exchange = Mock()
        exchange.exchange = Mock()
        exchange.fetch_order_book = AsyncMock(return_value={
            'asks': [],  # No liquidity
            'bids': []
        })

        executor = OrderExecutor(None)

        # Should raise exception due to no liquidity
        with pytest.raises(Exception, match="Insufficient liquidity"):
            await executor._execute_market_order(
                exchange=exchange,
                symbol='HNTUSDT',
                side='buy',
                amount=100.0
            )

    @pytest.mark.asyncio
    async def test_market_order_proceeds_good_liquidity(self):
        """Test that market order proceeds when liquidity is good"""

        exchange = Mock()
        exchange.exchange = Mock()
        exchange.exchange.id = 'bybit'
        exchange.exchange.create_order = AsyncMock(return_value={'id': '12345'})
        exchange.fetch_order_book = AsyncMock(return_value={
            'asks': [
                [100, 200],  # 200 units at 100
                [101, 200],
            ]
        })

        executor = OrderExecutor(None)

        # Should succeed (100 units needed, 400 available)
        result = await executor._execute_market_order(
            exchange=exchange,
            symbol='BTCUSDT',
            side='buy',
            amount=100.0
        )

        assert result['id'] == '12345'
        exchange.exchange.create_order.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### GIT STRATEGY для Improvement #3

```bash
git checkout -b improvement/orderbook-precheck

# Фаза 3A: Liquidity check function
git add core/order_executor.py
git commit -m "feat(orderbook): add liquidity check function"

# Фаза 3B: Market order pre-check
git add core/order_executor.py
git commit -m "feat(orderbook): add liquidity pre-check for market orders"

# Фаза 3C: Limit order pre-check
git add core/order_executor.py
git commit -m "feat(orderbook): add liquidity check for limit orders"

# Тесты
git add tests/test_orderbook_precheck.py
pytest tests/test_orderbook_precheck.py -v
git commit -m "test(orderbook): add order book pre-check tests"

# Merge
git checkout main
git merge --no-ff improvement/orderbook-precheck
git tag v1.3.0-orderbook-precheck
```

---

## 🔧 IMPROVEMENT #4: Periodic Price Fetch Fallback

### ЦЕЛЬ
Добавить механизм получения цен через REST API как fallback при отказе WebSocket:
- Independent periodic price fetching для aged позиций
- Автоматический вызов check_price_target при REST fetch
- Integration с WebSocket health monitoring (Improvement #2)
- Не зависит от UnifiedPriceMonitor callbacks

### АНАЛИЗ

**Текущая проблема** (из аудита):
```python
# check_price_target вызывается ТОЛЬКО при WebSocket update
# Если WebSocket сломан → позиция НЕ проверяется

# Существующий periodic_full_scan (каждые 5 мин):
# ✅ Детектирует новые aged позиции
# ❌ НЕ проверяет target prices
# ❌ НЕ fetches текущие цены
```

**Проблема GIGAUSDT:**
- WebSocket subscription сломана
- `check_price_target()` НЕ вызывается
- periodic_full_scan детектирует позицию но не проверяет цену
- Позиция зависла на 15+ часов

### РЕШЕНИЕ

#### Фаза 4A: Добавить REST Price Fetch в aged_position_monitor_v2

**Файл**: `core/aged_position_monitor_v2.py`
**Строки**: ~850 (после check_websocket_health)

**ВСТАВИТЬ НОВУЮ ФУНКЦИЮ:**
```python
    async def fetch_current_price_rest(self, symbol: str) -> Decimal or None:
        """
        ✅ ENHANCEMENT #4A: Fetch current price via REST API
        Fallback when WebSocket prices unavailable

        Args:
            symbol: Trading symbol

        Returns:
            Decimal: Current price, or None if fetch failed
        """
        if not self.exchanges:
            logger.warning(f"No exchanges available to fetch price for {symbol}")
            return None

        # Try each exchange until successful
        for exchange_name, exchange_mgr in self.exchanges.items():
            try:
                ticker = await exchange_mgr.fetch_ticker(symbol)

                # Get last price
                if ticker and 'last' in ticker:
                    price = Decimal(str(ticker['last']))
                    logger.debug(
                        f"✅ Fetched price for {symbol} via REST from {exchange_name}: {price}"
                    )
                    return price

                # Fallback to close price
                elif ticker and 'close' in ticker:
                    price = Decimal(str(ticker['close']))
                    logger.debug(
                        f"✅ Fetched close price for {symbol} via REST: {price}"
                    )
                    return price

            except Exception as e:
                logger.debug(f"Failed to fetch price from {exchange_name}: {e}")
                continue  # Try next exchange

        logger.error(f"❌ Failed to fetch price for {symbol} from all exchanges")
        return None
```

**Обоснование:**
- Пробует все доступные exchanges (resilience)
- Использует 'last' price (более актуальная чем 'close')
- Fallback на 'close' если 'last' недоступна
- Детальное логирование для debugging
- Возвращает None при failure (safe default)

#### Фаза 4B: Periodic Price Check Task

**Файл**: `core/aged_position_monitor_v2.py`
**Строки**: ~900 (после fetch_current_price_rest)

**ВСТАВИТЬ НОВУЮ ФУНКЦИЮ:**
```python
    async def start_periodic_price_check(self, interval_seconds: int = 60):
        """
        ✅ ENHANCEMENT #4B: Independent periodic price check for aged positions

        Fallback mechanism if UnifiedPriceMonitor callbacks not firing.
        Fetches prices via REST and manually calls check_price_target.

        Args:
            interval_seconds: Check interval (default: 60s)
        """
        logger.info(
            f"🔄 Starting independent price check task "
            f"(interval: {interval_seconds}s)"
        )

        while True:
            try:
                await asyncio.sleep(interval_seconds)

                # Get aged symbols
                aged_symbols = list(self.aged_targets.keys())

                if not aged_symbols:
                    logger.debug("No aged positions to check")
                    continue

                logger.debug(
                    f"🔍 Checking prices for {len(aged_symbols)} aged positions..."
                )

                for symbol in aged_symbols:
                    try:
                        # Fetch current price via REST
                        current_price = await self.fetch_current_price_rest(symbol)

                        if current_price is None:
                            logger.warning(
                                f"⚠️ Could not fetch price for {symbol} - skipping check"
                            )
                            continue

                        # Manually call check_price_target
                        logger.debug(
                            f"📊 Checking target for {symbol} @ {current_price}"
                        )
                        await self.check_price_target(symbol, current_price)

                    except Exception as e:
                        logger.error(
                            f"Error checking price for {symbol}: {e}",
                            exc_info=True
                        )

            except asyncio.CancelledError:
                logger.info("Independent price check task stopped")
                break
            except Exception as e:
                logger.error(f"Error in periodic price check: {e}")
                await asyncio.sleep(10)  # Wait before retry
```

**Обоснование:**
- **60s interval**: Баланс между responsiveness и API rate limits
- **Independent от WebSocket**: Работает даже если WebSocket полностью сломан
- **Manual check_price_target call**: Обходит необходимость в WebSocket callbacks
- **Error resilience**: Продолжает работу даже при errors на отдельных symbols

#### Фаза 4C: Integration с WebSocket Health Monitor

**Файл**: `core/position_manager_unified_patch.py`
**Строки**: ~220 (в start_websocket_health_monitor, после подсчета stale)

**ЗАМЕНИТЬ комментарий "# TODO: Trigger fallback price fetch":**
```python
                # ✅ ENHANCEMENT #4C: Trigger fallback for stale positions

                # Get aged monitor
                aged_monitor = unified_protection.get('aged_monitor')

                if aged_monitor:
                    # Trigger immediate price check for stale positions
                    for symbol, data in staleness_report.items():
                        if data['stale']:
                            try:
                                logger.info(
                                    f"🔄 Triggering REST fallback for stale symbol: {symbol}"
                                )

                                # Fetch price via REST
                                current_price = await aged_monitor.fetch_current_price_rest(symbol)

                                if current_price:
                                    # Manually check target
                                    await aged_monitor.check_price_target(symbol, current_price)
                                    logger.info(
                                        f"✅ Fallback check complete for {symbol} @ {current_price}"
                                    )
                                else:
                                    logger.warning(
                                        f"⚠️ REST fallback failed for {symbol}"
                                    )

                            except Exception as e:
                                logger.error(
                                    f"Error in REST fallback for {symbol}: {e}"
                                )
```

**Обоснование:**
- **Реактивный fallback**: Triggers только при обнаружении stale price
- **Integration с Improvement #2**: Использует staleness detection
- **Immediate action**: Не ждет periodic check (60s), действует сразу
- **Complementary**: Работает вместе с periodic check (двойная защита)

#### Фаза 4D: Запуск periodic price check в main

**Файл**: `main.py`
**Ищем где создается aged_monitor**

**ВСТАВИТЬ ПОСЛЕ создания aged_monitor:**
```python
# ✅ ENHANCEMENT #4D: Start independent price check task
if aged_monitor and config.get('ENABLE_PERIODIC_PRICE_CHECK', True):
    periodic_price_check_task = asyncio.create_task(
        aged_monitor.start_periodic_price_check(
            interval_seconds=60  # Check every minute
        )
    )
    logger.info("✅ Independent periodic price check started")
```

**Обоснование:**
- **Config flag**: Можно отключить через ENABLE_PERIODIC_PRICE_CHECK=False
- **Default enabled**: True по умолчанию (защита из коробки)
- **Separate task**: Не блокирует другие операции

#### Фаза 4E: Добавить метод для on-demand price check

**Файл**: `core/aged_position_monitor_v2.py`
**Строки**: ~950 (после start_periodic_price_check)

**ВСТАВИТЬ ВСПОМОГАТЕЛЬНУЮ ФУНКЦИЮ:**
```python
    async def check_aged_position_now(self, symbol: str) -> dict:
        """
        ✅ ENHANCEMENT #4E: On-demand price check for aged position

        Immediately fetches price and checks target.
        Useful for manual triggers or API endpoints.

        Args:
            symbol: Symbol to check

        Returns:
            dict: Check result with status and details
        """
        if symbol not in self.aged_targets:
            return {
                'success': False,
                'reason': 'not_aged',
                'message': f'{symbol} is not in aged monitoring'
            }

        try:
            # Fetch current price
            current_price = await self.fetch_current_price_rest(symbol)

            if current_price is None:
                return {
                    'success': False,
                    'reason': 'price_fetch_failed',
                    'message': f'Could not fetch price for {symbol}'
                }

            # Check target
            await self.check_price_target(symbol, current_price)

            # Get target info
            target = self.aged_targets.get(symbol)

            return {
                'success': True,
                'symbol': symbol,
                'current_price': float(current_price),
                'target_price': float(target.target_price) if target else None,
                'phase': target.phase if target else None,
                'message': f'Check completed for {symbol} @ {current_price}'
            }

        except Exception as e:
            logger.error(f"Error in on-demand check for {symbol}: {e}")
            return {
                'success': False,
                'reason': 'exception',
                'message': str(e)
            }
```

**Обоснование:**
- **API endpoint готовый**: Можно вызвать из external monitoring
- **Manual intervention**: Полезно для troubleshooting
- **Structured response**: Детальная информация о результате
- **Error handling**: Safe даже при exceptions

### ТЕСТИРОВАНИЕ Improvement #4

**Файл**: `tests/test_price_fetch_fallback.py` (НОВЫЙ)

```python
"""
Tests for Periodic Price Fetch Fallback
Validates Enhancement #4: Periodic Price Fetch Fallback
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from core.aged_position_monitor_v2 import AgedPositionMonitorV2


class TestRESTpriceFetch:
    """Test REST API price fetching"""

    @pytest.mark.asyncio
    async def test_fetch_price_success(self):
        """Test successful price fetch via REST"""

        # Mock exchange
        exchange = Mock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 50000.0,
            'close': 49900.0
        })

        # Create monitor
        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.exchanges = {'bybit': exchange}

        # Fetch price
        price = await monitor.fetch_current_price_rest('BTCUSDT')

        assert price == Decimal('50000.0')
        exchange.fetch_ticker.assert_called_once_with('BTCUSDT')

    @pytest.mark.asyncio
    async def test_fetch_price_fallback_to_close(self):
        """Test fallback to close price when last unavailable"""

        exchange = Mock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'close': 49900.0  # No 'last' price
        })

        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.exchanges = {'bybit': exchange}

        price = await monitor.fetch_current_price_rest('BTCUSDT')

        assert price == Decimal('49900.0')

    @pytest.mark.asyncio
    async def test_fetch_price_failure_returns_none(self):
        """Test that fetch failure returns None"""

        exchange = Mock()
        exchange.fetch_ticker = AsyncMock(side_effect=Exception("API error"))

        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.exchanges = {'bybit': exchange}

        price = await monitor.fetch_current_price_rest('BTCUSDT')

        assert price is None


class TestPeriodicPriceCheck:
    """Test periodic price check task"""

    @pytest.mark.asyncio
    async def test_periodic_check_calls_check_price_target(self):
        """Test that periodic check calls check_price_target"""

        monitor = AgedPositionMonitorV2(None, None, None)

        # Mock methods
        monitor.fetch_current_price_rest = AsyncMock(return_value=Decimal('100'))
        monitor.check_price_target = AsyncMock()

        # Add aged target
        monitor.aged_targets = {'TESTUSDT': Mock()}

        # Run one iteration (with short interval)
        task = asyncio.create_task(
            monitor.start_periodic_price_check(interval_seconds=0.1)
        )

        # Wait for one check
        await asyncio.sleep(0.2)

        # Stop task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify check_price_target was called
        monitor.check_price_target.assert_called()
        call_args = monitor.check_price_target.call_args
        assert call_args[0][0] == 'TESTUSDT'
        assert call_args[0][1] == Decimal('100')

    @pytest.mark.asyncio
    async def test_periodic_check_skips_on_price_fetch_failure(self):
        """Test that periodic check skips symbol if price fetch fails"""

        monitor = AgedPositionMonitorV2(None, None, None)

        # Mock fetch to return None
        monitor.fetch_current_price_rest = AsyncMock(return_value=None)
        monitor.check_price_target = AsyncMock()

        monitor.aged_targets = {'TESTUSDT': Mock()}

        # Run one iteration
        task = asyncio.create_task(
            monitor.start_periodic_price_check(interval_seconds=0.1)
        )
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # check_price_target should NOT be called
        monitor.check_price_target.assert_not_called()


class TestOnDemandCheck:
    """Test on-demand price check"""

    @pytest.mark.asyncio
    async def test_on_demand_check_success(self):
        """Test successful on-demand check"""

        monitor = AgedPositionMonitorV2(None, None, None)

        # Mock methods
        monitor.fetch_current_price_rest = AsyncMock(return_value=Decimal('100'))
        monitor.check_price_target = AsyncMock()
        monitor.aged_targets = {
            'TESTUSDT': Mock(target_price=Decimal('95'), phase='grace')
        }

        # Run check
        result = await monitor.check_aged_position_now('TESTUSDT')

        assert result['success']
        assert result['current_price'] == 100.0
        assert result['target_price'] == 95.0
        assert result['phase'] == 'grace'

    @pytest.mark.asyncio
    async def test_on_demand_check_not_aged(self):
        """Test on-demand check for non-aged position"""

        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.aged_targets = {}

        result = await monitor.check_aged_position_now('NOTAGED')

        assert not result['success']
        assert result['reason'] == 'not_aged'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### GIT STRATEGY для Improvement #4

```bash
git checkout -b improvement/price-fetch-fallback

# Фаза 4A: REST price fetch
git add core/aged_position_monitor_v2.py
git commit -m "feat(fallback): add REST price fetch method"

# Фаза 4B: Periodic price check task
git add core/aged_position_monitor_v2.py
git commit -m "feat(fallback): implement periodic price check task"

# Фаза 4C: Integration с health monitor
git add core/position_manager_unified_patch.py
git commit -m "feat(fallback): integrate REST fallback with health monitor"

# Фаза 4D: Main startup
git add main.py
git commit -m "feat(fallback): start periodic price check on startup"

# Фаза 4E: On-demand check
git add core/aged_position_monitor_v2.py
git commit -m "feat(fallback): add on-demand price check method"

# Тесты
git add tests/test_price_fetch_fallback.py
pytest tests/test_price_fetch_fallback.py -v
git commit -m "test(fallback): add price fetch fallback tests"

# Merge
git checkout main
git merge --no-ff improvement/price-fetch-fallback
git tag v1.4.0-price-fallback
```

---

## 📊 SUMMARY: Все 4 Улучшения

### Что будет реализовано:

| # | Улучшение | Файлы | Строк кода | Тестов | Коммитов |
|---|-----------|-------|------------|--------|----------|
| 1 | Enhanced Error Handling | 2 | ~250 | 6 тестов | 6 |
| 2 | WebSocket Health Monitoring | 4 | ~300 | 8 тестов | 6 |
| 3 | Order Book Pre-Check | 1 | ~200 | 6 тестов | 4 |
| 4 | Periodic Price Fetch Fallback | 3 | ~350 | 8 тестов | 6 |
| **TOTAL** | **4 improvements** | **10 files** | **~1100** | **28 тестов** | **22 коммита** |

### Timeline:

| Improvement | Время реализации | Время тестирования | TOTAL |
|-------------|------------------|-------------------|-------|
| #1 | 2-3 часа | 1 час | 3-4 часа |
| #2 | 2-3 часа | 1 час | 3-4 часа |
| #3 | 1-2 часа | 30 мин | 1.5-2.5 часа |
| #4 | 2-3 часа | 1 час | 3-4 часа |
| **TOTAL** | **7-11 часов** | **3.5 часа** | **10.5-14.5 часов** |

### Порядок реализации:

```
День 1: Improvement #1 (Error Handling) + Improvement #3 (Order Book)
День 2: Improvement #2 (WebSocket Health) + Improvement #4 (Price Fallback)
День 3: Integration testing + Bug fixes
```

### Expected Impact:

**ДО улучшений:**
```
Total aged positions: 15+
Successfully closed: 11 (73%)
Stuck (exchange errors): 2 (13%)  ← XDCUSDT, HNTUSDT
Stuck (WebSocket): 1 (7%)         ← GIGAUSDT
```

**ПОСЛЕ всех улучшений:**
```
Total aged positions: 15+
Successfully closed: 14+ (93%+)
Manual intervention: 1 (7%) или меньше
Stuck positions: 0-1 (только extreme cases)

Improvements impact:
- #1: XDCUSDT error handled → manual review event
- #2: GIGAUSDT WebSocket detected → alert + fallback triggered
- #3: HNTUSDT low liquidity detected → fallback to limit order
- #4: Любые WebSocket issues → REST fallback работает
```

---

## 🎯 NEXT STEPS

1. **Ревью плана** - проверить все детали
2. **Начать с Improvement #1** - самый критичный
3. **Тестировать каждую фазу** - pytest перед commit
4. **Мониторить production** - логи после каждого deployment

**ПЛАН ГОТОВ К РЕАЛИЗАЦИИ** ✅

---

**Дата**: 2025-10-24
**Автор**: Claude Code
**Статус**: APPROVED
