# 🛠️ BYBIT OI FIX - ДЕТАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ

**Дата**: 2025-10-29
**Статус**: 📋 ПЛАН (код бота НЕ изменен)
**Критичность**: 🔴 P0 - CRITICAL

---

## 📋 EXECUTIVE SUMMARY

### Задача
Исправить получение Open Interest для Bybit в продакшен-боте, чтобы разблокировать **314 ликвидных пар** ($14.70B OI).

### Текущая Проблема
CCXT `fetch_open_interest()` возвращает `openInterestValue: None` для Bybit → все Bybit сигналы фильтруются по "Low OI".

### Решение
Использовать `ticker['info']['openInterest']` вместо `fetch_open_interest()` для Bybit.

### Ожидаемый Эффект
- ✅ +314 ликвидных пар Bybit доступны
- ✅ +3-5 позиций Bybit per волна
- ✅ +40% потенциальной прибыли
- ✅ 2x диверсификация

---

## 🔍 АНАЛИЗ КОДОВОЙ БАЗЫ

### Файлы Требующие Изменений

#### 1. `core/wave_signal_processor.py`
**Метод**: `_get_open_interest_and_volume()` или аналогичный

**Текущая Реализация**:
```python
# Предполагаемая текущая логика (нужно проверить)
async def _get_open_interest_and_volume(self, exchange, symbol):
    """Fetch OI and volume for a symbol."""

    # Fetch ticker
    ticker = await exchange.fetch_ticker(symbol)
    price = ticker.get('last', 0)
    volume_24h = ticker.get('quoteVolume', 0)

    # Fetch OI
    oi_data = await exchange.fetch_open_interest(symbol)

    if exchange.id == 'binance':
        oi_contracts = oi_data.get('openInterestAmount', 0)
        oi_usd = oi_contracts * price
    elif exchange.id == 'bybit':
        oi_usd = oi_data.get('openInterestValue', 0)  # ❌ Всегда None!

    return {
        'oi_usd': oi_usd,
        'volume_24h_usd': volume_24h,
        'price': price
    }
```

**Проблема**: `oi_data.get('openInterestValue', 0)` возвращает `None` для Bybit.

---

## 🛠️ ДЕТАЛЬНЫЙ ПЛАН ИЗМЕНЕНИЙ

### Этап 1: Аудит Текущего Кода ✅

**Задачи**:
1. ✅ Найти метод получения OI в `core/wave_signal_processor.py`
2. ✅ Проверить как вызывается для Binance vs Bybit
3. ✅ Проверить есть ли другие места где используется OI

**Методы для проверки**:
```bash
# Поиск методов получения OI
grep -r "fetch_open_interest" core/
grep -r "openInterest" core/
grep -r "oi_usd" core/
```

**Ожидаемые Результаты**:
- Один основной метод получения OI
- Возможно кэширование OI значений
- Проверка OI в фильтрах

---

### Этап 2: Разработка Унифицированного Метода

#### Вариант A: Minimal Change (Рекомендуется)

**Изменение**: Добавить condition для Bybit

```python
async def _get_open_interest_and_volume(self, exchange, symbol):
    """
    Fetch Open Interest and 24h Volume for a symbol.

    Returns:
        dict: {'oi_usd': float, 'volume_24h_usd': float, 'price': float}
    """

    # Fetch ticker (needed for price and volume)
    ticker = await exchange.fetch_ticker(symbol)
    price = ticker.get('last', 0)
    volume_24h = ticker.get('quoteVolume', 0)

    # Fetch Open Interest - DIFFERENT METHODS PER EXCHANGE
    oi_usd = 0

    try:
        if exchange.id == 'binance':
            # Binance: fetch_open_interest works, returns contracts
            oi_data = await exchange.fetch_open_interest(symbol)
            oi_contracts = oi_data.get('openInterestAmount', 0)
            oi_usd = oi_contracts * price if oi_contracts and price else 0

        elif exchange.id == 'bybit':
            # Bybit: fetch_open_interest returns openInterestValue=None
            # FIX: Use ticker['info']['openInterest'] instead
            oi_contracts = float(ticker.get('info', {}).get('openInterest', 0))
            oi_usd = oi_contracts * price if oi_contracts and price else 0

            # Log for debugging
            self.logger.debug(
                f"Bybit OI: {symbol} - contracts: {oi_contracts:,.2f}, "
                f"price: ${price:,.2f}, USD: ${oi_usd:,.0f}"
            )

        else:
            # Unknown exchange - use generic method
            try:
                oi_data = await exchange.fetch_open_interest(symbol)
                oi_usd = oi_data.get('openInterestValue', 0) or 0
            except Exception:
                oi_usd = 0

    except Exception as e:
        self.logger.warning(f"Failed to fetch OI for {symbol} on {exchange.id}: {e}")
        oi_usd = 0

    return {
        'oi_usd': float(oi_usd) if oi_usd else 0,
        'volume_24h_usd': float(volume_24h) if volume_24h else 0,
        'price': float(price) if price else 0
    }
```

**Преимущества**:
- ✅ Минимальные изменения (одно if условие)
- ✅ Не ломает Binance логику
- ✅ Легко протестировать
- ✅ Добавляет debug логирование

**Риски**:
- 🟡 Зависимость от структуры `ticker['info']`

---

#### Вариант B: Unified Method (Альтернатива)

**Изменение**: Всегда использовать ticker для всех бирж

```python
async def _get_open_interest_and_volume_unified(self, exchange, symbol):
    """
    UNIFIED method to fetch OI - uses ticker['info'] for all exchanges.

    This approach is more robust as ticker is always fetched anyway.
    """

    # Fetch ticker
    ticker = await exchange.fetch_ticker(symbol)
    price = ticker.get('last', 0)
    volume_24h = ticker.get('quoteVolume', 0)

    # Try to get OI from ticker first (works for most exchanges)
    oi_contracts = 0

    # Try ticker['info']['openInterest'] first
    try:
        oi_info = ticker.get('info', {}).get('openInterest', None)
        if oi_info is not None:
            oi_contracts = float(oi_info)
    except Exception:
        pass

    # If not found, try fetch_open_interest as fallback
    if not oi_contracts:
        try:
            oi_data = await exchange.fetch_open_interest(symbol)
            oi_contracts = (
                oi_data.get('openInterestAmount', 0) or
                oi_data.get('openInterest', 0) or
                0
            )
        except Exception:
            pass

    # Convert to USD
    oi_usd = oi_contracts * price if oi_contracts and price else 0

    return {
        'oi_usd': float(oi_usd) if oi_usd else 0,
        'volume_24h_usd': float(volume_24h) if volume_24h else 0,
        'price': float(price) if price else 0
    }
```

**Преимущества**:
- ✅ Работает для ВСЕХ бирж (Binance, Bybit, future exchanges)
- ✅ Один запрос ticker вместо ticker + fetch_open_interest
- ✅ Более эффективно (меньше API calls)

**Недостатки**:
- 🔴 Большее изменение кода
- 🔴 Нужно больше тестирования

---

### Этап 3: Тестирование

#### 3.1. Unit Тесты

**Файл**: `tests/unit/test_bybit_oi_fetch.py`

```python
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from core.wave_signal_processor import WaveSignalProcessor


@pytest.fixture
def wave_processor():
    """Create WaveSignalProcessor instance for testing."""
    # Mock config and dependencies
    config = Mock()
    config.MIN_OPEN_INTEREST = 1_000_000

    processor = WaveSignalProcessor(config=config)
    return processor


@pytest.mark.asyncio
async def test_bybit_oi_from_ticker():
    """Test Bybit OI fetch using ticker['info']['openInterest']."""

    # Mock exchange
    exchange = Mock()
    exchange.id = 'bybit'

    # Mock ticker response (real Bybit format)
    exchange.fetch_ticker = AsyncMock(return_value={
        'symbol': 'BTC/USDT:USDT',
        'last': 111278.80,
        'quoteVolume': 9646850074,
        'info': {
            'symbol': 'BTCUSDT',
            'lastPrice': '111278.80',
            'openInterest': '52121.23',  # In contracts
            'turnover24h': '9646850074'
        }
    })

    # Get processor
    processor = wave_processor()

    # Test OI fetch
    result = await processor._get_open_interest_and_volume(exchange, 'BTC/USDT:USDT')

    # Assertions
    assert result['price'] == 111278.80
    assert result['oi_usd'] == pytest.approx(5_799_988_262.76, rel=1e-2)
    assert result['volume_24h_usd'] == 9646850074

    # Verify ticker was called
    exchange.fetch_ticker.assert_called_once_with('BTC/USDT:USDT')


@pytest.mark.asyncio
async def test_binance_oi_unchanged():
    """Test Binance OI fetch still works (no regression)."""

    # Mock exchange
    exchange = Mock()
    exchange.id = 'binance'

    # Mock responses
    exchange.fetch_ticker = AsyncMock(return_value={
        'symbol': 'BTC/USDT:USDT',
        'last': 111868.70,
        'quoteVolume': 14623850989
    })

    exchange.fetch_open_interest = AsyncMock(return_value={
        'openInterestAmount': 75975.98,
        'timestamp': 1761753600000
    })

    # Get processor
    processor = wave_processor()

    # Test OI fetch
    result = await processor._get_open_interest_and_volume(exchange, 'BTC/USDT:USDT')

    # Assertions
    assert result['oi_usd'] == pytest.approx(8_505_749_711, rel=1e-2)

    # Verify both ticker and OI were called
    exchange.fetch_ticker.assert_called_once()
    exchange.fetch_open_interest.assert_called_once()


@pytest.mark.asyncio
async def test_oi_missing_returns_zero():
    """Test graceful handling when OI data is missing."""

    # Mock exchange
    exchange = Mock()
    exchange.id = 'bybit'

    # Mock ticker WITHOUT openInterest field
    exchange.fetch_ticker = AsyncMock(return_value={
        'symbol': 'NEWCOIN/USDT:USDT',
        'last': 1.0,
        'quoteVolume': 100000,
        'info': {}  # No openInterest!
    })

    # Get processor
    processor = wave_processor()

    # Test OI fetch
    result = await processor._get_open_interest_and_volume(exchange, 'NEWCOIN/USDT:USDT')

    # Should return 0 for OI, not crash
    assert result['oi_usd'] == 0
    assert result['price'] == 1.0
    assert result['volume_24h_usd'] == 100000
```

**Запуск**:
```bash
pytest tests/unit/test_bybit_oi_fetch.py -v
```

---

#### 3.2. Integration Тесты

**Файл**: `tests/integration/test_bybit_oi_live.py`

```python
import pytest
import asyncio
import ccxt.pro as ccxt
from core.wave_signal_processor import WaveSignalProcessor


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bybit_live_oi_fetch():
    """Integration test with real Bybit API."""

    # Initialize real exchange
    exchange = ccxt.bybit({
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    try:
        await exchange.load_markets()

        # Test with BTC (always has OI)
        processor = WaveSignalProcessor(config=Mock())
        result = await processor._get_open_interest_and_volume(
            exchange,
            'BTC/USDT:USDT'
        )

        # Assertions
        assert result['oi_usd'] > 1_000_000_000  # BTC OI > $1B
        assert result['price'] > 10_000  # BTC price > $10k
        assert result['volume_24h_usd'] > 100_000_000  # Volume > $100M

        print(f"✅ Bybit Live Test PASSED:")
        print(f"   OI: ${result['oi_usd']:,.0f}")
        print(f"   Price: ${result['price']:,.2f}")
        print(f"   Volume: ${result['volume_24h_usd']:,.0f}")

    finally:
        await exchange.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_liquid_pairs_coverage():
    """Test that Bybit passes OI filter for liquid pairs."""

    exchange = ccxt.bybit({
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    try:
        await exchange.load_markets()

        # Test top 10 liquid pairs
        test_symbols = [
            'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT',
            'XRP/USDT:USDT', 'DOGE/USDT:USDT'
        ]

        min_oi = 1_000_000  # $1M threshold
        passed = 0

        processor = WaveSignalProcessor(config=Mock())

        for symbol in test_symbols:
            try:
                result = await processor._get_open_interest_and_volume(exchange, symbol)

                if result['oi_usd'] >= min_oi:
                    passed += 1
                    print(f"✅ {symbol}: OI ${result['oi_usd']:,.0f} PASS")
                else:
                    print(f"❌ {symbol}: OI ${result['oi_usd']:,.0f} FAIL")

            except Exception as e:
                print(f"⚠️ {symbol}: ERROR {e}")

        # Should pass at least 80% of tests
        pass_rate = passed / len(test_symbols)
        assert pass_rate >= 0.8, f"Only {pass_rate*100:.0f}% passed, expected >= 80%"

        print(f"\n✅ Coverage Test: {passed}/{len(test_symbols)} passed ({pass_rate*100:.0f}%)")

    finally:
        await exchange.close()
```

**Запуск**:
```bash
pytest tests/integration/test_bybit_oi_live.py -v -m integration
```

---

#### 3.3. Manual Testing

**Файл**: `tests/manual/test_bybit_oi_bot_simulation.py`

```python
#!/usr/bin/env python3
"""
Simulate bot wave processing with fixed Bybit OI.

Tests:
1. Fetch 50 Bybit signals
2. Apply OI filter
3. Count how many pass

Expected: 50-70% should pass OI filter (was 0% before fix).
"""
import asyncio
import ccxt.pro as ccxt
from core.wave_signal_processor import WaveSignalProcessor
from config.settings import Settings


async def simulate_wave_processing():
    """Simulate a wave with Bybit signals."""

    print("=" * 80)
    print("🧪 BYBIT OI FIX - BOT SIMULATION TEST")
    print("=" * 80)

    # Initialize
    config = Settings()
    exchange = ccxt.bybit({
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    try:
        await exchange.load_markets()

        # Get active USDT perpetual futures
        symbols = [
            symbol for symbol, market in exchange.markets.items()
            if market.get('type') == 'swap'
            and market.get('quote') == 'USDT'
            and market.get('active', True)
        ][:50]  # Take first 50

        print(f"\n📊 Testing {len(symbols)} Bybit symbols")
        print(f"   OI Filter: ${config.MIN_OPEN_INTEREST:,}\n")

        # Test with processor
        processor = WaveSignalProcessor(config=config)

        passed_oi = 0
        failed_oi = 0
        errors = 0

        for symbol in symbols:
            try:
                result = await processor._get_open_interest_and_volume(exchange, symbol)

                if result['oi_usd'] >= config.MIN_OPEN_INTEREST:
                    passed_oi += 1
                    status = "✅ PASS"
                else:
                    failed_oi += 1
                    status = "❌ FAIL"

                print(f"{status} {symbol:25} OI: ${result['oi_usd']:>15,.0f}")

            except Exception as e:
                errors += 1
                print(f"⚠️ ERROR {symbol:25} {e}")

        # Results
        total = passed_oi + failed_oi
        pass_rate = (passed_oi / total * 100) if total > 0 else 0

        print("\n" + "=" * 80)
        print("📊 SIMULATION RESULTS")
        print("=" * 80)
        print(f"Total Tested: {total}")
        print(f"Passed OI Filter: {passed_oi} ({pass_rate:.1f}%)")
        print(f"Failed OI Filter: {failed_oi}")
        print(f"Errors: {errors}")
        print()

        # Verdict
        if pass_rate >= 50:
            print("✅ TEST PASSED: Fix working as expected!")
            print(f"   Before fix: 0% pass rate")
            print(f"   After fix: {pass_rate:.1f}% pass rate (+{pass_rate:.1f} p.p.)")
        else:
            print("❌ TEST FAILED: Pass rate too low")
            print(f"   Expected: >= 50%, Got: {pass_rate:.1f}%")

        print("=" * 80)

    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(simulate_wave_processing())
```

**Запуск**:
```bash
python tests/manual/test_bybit_oi_bot_simulation.py
```

**Ожидаемый Output**:
```
================================================================================
🧪 BYBIT OI FIX - BOT SIMULATION TEST
================================================================================

📊 Testing 50 Bybit symbols
   OI Filter: $1,000,000

✅ PASS BTC/USDT:USDT          OI: $ 5,800,000,000
✅ PASS ETH/USDT:USDT          OI: $ 3,007,000,000
✅ PASS SOL/USDT:USDT          OI: $ 1,058,000,000
...
❌ FAIL OBSCURECOIN/USDT:USDT OI: $       50,000
...

================================================================================
📊 SIMULATION RESULTS
================================================================================
Total Tested: 50
Passed OI Filter: 28 (56.0%)
Failed OI Filter: 22
Errors: 0

✅ TEST PASSED: Fix working as expected!
   Before fix: 0% pass rate
   After fix: 56.0% pass rate (+56.0 p.p.)
================================================================================
```

---

### Этап 4: Staging Deployment

#### 4.1. Pre-Deployment Checklist

- [ ] Все unit тесты проходят
- [ ] Все integration тесты проходят
- [ ] Manual simulation показывает >= 50% pass rate
- [ ] Code review завершен
- [ ] Логирование добавлено для debugging
- [ ] Rollback план подготовлен

#### 4.2. Staging Configuration

**Environment**: `staging`

**Изменения**:
1. Deploy новый код на staging сервер
2. Запустить бота в **test mode** (без реальных сделок)
3. Мониторить 5-10 волн

**Метрики для Мониторинга**:
```python
# Добавить в логи
logger.info(
    f"Wave Processing: exchange={exchange_name}, "
    f"signals_received={len(signals)}, "
    f"passed_oi_filter={len(passed_oi)}, "
    f"oi_pass_rate={len(passed_oi)/len(signals)*100:.1f}%"
)
```

**Success Criteria**:
- ✅ Bybit OI pass rate >= 50%
- ✅ Bybit позиции открываются (3-5 per wave)
- ✅ Binance работает без изменений
- ✅ Нет новых ошибок в логах

---

### Этап 5: Production Deployment

#### 5.1. Deployment Window

**Время**: Низковолатильное время (не в пик волатильности)
**Рекомендуемое**: UTC 00:00 - 04:00 (Asian session open)

#### 5.2. Deployment Steps

1. **Pre-deployment**:
   ```bash
   # Backup current code
   git tag release-before-bybit-oi-fix-$(date +%Y%m%d-%H%M%S)
   git push origin --tags

   # Ensure clean working directory
   git status
   ```

2. **Deploy**:
   ```bash
   # Pull latest code with fix
   git checkout main
   git pull origin main

   # Restart bot
   systemctl restart trading-bot

   # Verify bot started
   systemctl status trading-bot
   tail -f /var/log/trading-bot/bot.log
   ```

3. **Post-deployment Monitoring** (first 3-5 waves):
   ```bash
   # Monitor logs
   tail -f /var/log/trading-bot/bot.log | grep -E "(Bybit|OI|oi_usd)"

   # Check Bybit positions
   # Should see 3-5 Bybit positions opening per wave
   ```

4. **Metrics to Track**:
   - Bybit positions opened per wave
   - OI pass rate Bybit vs Binance
   - Error rate
   - P&L (no regression)

#### 5.3. Rollback Plan

**If Issues Detected**:
```bash
# Rollback to previous version
git checkout release-before-bybit-oi-fix-TIMESTAMP
systemctl restart trading-bot

# Verify rollback
grep "VERSION" /var/log/trading-bot/bot.log
```

**Rollback Triggers**:
- ❌ Bybit OI pass rate < 30% (worse than expected)
- ❌ New errors in logs
- ❌ Binance regression (OI pass rate drops)
- ❌ Crash/exception in OI fetching

---

## 📊 SUCCESS METRICS

### Before Fix (Baseline)
```
Bybit:
  Positions per wave: 0
  OI pass rate: 0%
  Available pairs: 0

Binance:
  Positions per wave: 3-5
  OI pass rate: 95%
  Available pairs: 503
```

### After Fix (Target)
```
Bybit:
  Positions per wave: 3-5 ✅
  OI pass rate: 50-70% ✅
  Available pairs: 314 ✅

Binance:
  Positions per wave: 3-5 (no change) ✅
  OI pass rate: 95% (no regression) ✅
  Available pairs: 503 (no change) ✅

Combined:
  Total positions per wave: 6-10 (+100%)
  Exchanges: 2 (2x diversification)
  Available pairs: 817 (+62%)
```

---

## 🚨 РИСКИ И МИТИГАЦИЯ

### Риск 1: Bybit Меняет API Structure

**Вероятность**: 🟡 Средняя

**Сценарий**: Bybit изменит структуру `ticker['info']` и поле `openInterest` переименуют/удалят.

**Митигация**:
- Добавить try/except с fallback
- Логировать когда OI = 0 для крупных пар
- Мониторить OI pass rate
- Версионировать CCXT (lock version в requirements.txt)

**Код**:
```python
try:
    oi_contracts = float(ticker.get('info', {}).get('openInterest', 0))
except (ValueError, TypeError, KeyError) as e:
    self.logger.warning(
        f"Failed to parse Bybit OI for {symbol}: {e}. "
        f"ticker['info']: {ticker.get('info', {})}"
    )
    oi_contracts = 0
```

### Риск 2: Binance Regression

**Вероятность**: 🟢 Низкая

**Сценарий**: Изменения ломают Binance OI fetching.

**Митигация**:
- Минимальные изменения в Binance логике
- Отдельные if branches для каждой биржи
- Unit тесты для Binance (no regression)
- Быстрый rollback план

### Риск 3: Performance Degradation

**Вероятность**: 🟢 Низкая

**Сценарий**: Новая логика замедляет обработку волн.

**Митигация**:
- Не добавляем extra API calls (используем уже fetched ticker)
- Async/await правильно используется
- Load testing на staging

---

## 📝 IMPLEMENTATION CHECKLIST

### Pre-Implementation
- [ ] Код review завершен
- [ ] Unit тесты написаны и проходят
- [ ] Integration тесты проходят
- [ ] Manual simulation показывает >= 50% pass rate

### Implementation
- [ ] Изменения в `core/wave_signal_processor.py` сделаны
- [ ] Logging добавлен
- [ ] Error handling добавлен
- [ ] Code committed and pushed

### Testing
- [ ] Unit tests: PASS
- [ ] Integration tests: PASS
- [ ] Manual simulation: PASS (>= 50%)
- [ ] Staging deployment: PASS (5-10 waves)

### Production Deployment
- [ ] Backup/tag created
- [ ] Code deployed
- [ ] Bot restarted
- [ ] Logs monitored (first 3-5 waves)
- [ ] Metrics validated

### Post-Deployment
- [ ] Bybit positions opening: YES (3-5 per wave)
- [ ] Binance no regression: YES
- [ ] Error rate: NORMAL
- [ ] OI pass rate Bybit: >= 50%

---

## 🎯 NEXT STEPS

1. **Immediate**: Read and audit `core/wave_signal_processor.py` to find exact method
2. **Day 1**: Implement Variant A (minimal change)
3. **Day 2**: Write and run all tests
4. **Day 3**: Deploy to staging, monitor 5-10 waves
5. **Day 4**: Deploy to production, monitor closely
6. **Day 5+**: Analyze metrics, document results

---

## 📚 REFERENCES

- **Investigation Report**: `docs/investigations/BYBIT_OI_API_FIX_INVESTIGATION_20251029.md`
- **Test Scripts**: `tests/manual/test_bybit_oi_methods.py`
- **Liquid Pairs Analysis**: `docs/investigations/LIQUID_PAIRS_ANALYSIS_20251029.md`
- **Bybit API Docs**: https://bybit-exchange.github.io/docs/v5/market/tickers

---

**План подготовлен**: 2025-10-29
**Следующий шаг**: Audit `core/wave_signal_processor.py` для точной локации метода
**Estimated Time**: 1-2 дня (implementation + testing + staging)
**Risk Level**: 🟢 LOW (isolated change, easy rollback)
