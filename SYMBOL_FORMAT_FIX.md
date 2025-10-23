# 🔧 FIX: Symbol Format Conversion for Freqtrade

## ❌ ПРОБЛЕМА

**Было:**
Bridge публиковал сигналы в Redis с ключами в формате WebSocket:
```
signal:APEUSDT
signal:LTCUSDT
signal:BTCUSDT
```

Freqtrade ожидает ключи в формате фьючерсных пар:
```
signal:APE/USDT:USDT
signal:LTC/USDT:USDT
signal:BTC/USDT:USDT
```

**Последствия:**
- Bridge корректно фильтровал и публиковал сигналы в Redis
- Freqtrade не находил сигналы из-за несовпадения формата ключей
- Позиции не открывались, несмотря на правильную работу фильтрации

**Пример из логов (2025-10-21 22:35):**
```log
Bridge:
INFO - 📊 Score filtering: 2/47 signals passed (score_week>=60.0, score_month>=60.0)
INFO - Publishing 2 signals to Redis...

Redis:
✓ Signals in Redis: 2
  • APEUSDT (BINANCE) - short
  • LTCUSDT (BINANCE) - short

Freqtrade:
❌ Позиции НЕ открылись (сигналы не найдены)
```

---

## ✅ РЕШЕНИЕ

**Добавлен метод конвертации формата символов:**

```python
def _convert_symbol_to_freqtrade_pair(self, symbol: str, exchange: str) -> str:
    """
    Convert symbol from WebSocket format to Freqtrade format

    WebSocket: APEUSDT, BTCUSDT
    Freqtrade Binance Futures: APE/USDT:USDT, BTC/USDT:USDT
    """
    if not symbol:
        return symbol

    # Already in Freqtrade format?
    if '/' in symbol and ':' in symbol:
        return symbol

    # Remove USDT suffix to get base currency
    if symbol.endswith('USDT'):
        base = symbol[:-4]  # Remove last 4 chars (USDT)
        # Format: BASE/USDT:USDT for futures
        return f"{base}/USDT:USDT"

    # If no USDT suffix, return as-is (edge case)
    logger.warning(f"Symbol {symbol} doesn't end with USDT, using as-is")
    return symbol
```

**Использование в `enrich_signal_for_redis()`:**

```python
def enrich_signal_for_redis(self, signal: Dict, wave_id: str, rank: int) -> Dict:
    # Convert symbol to Freqtrade pair format
    symbol = signal.get('symbol', '')
    exchange = signal.get('exchange', 'binance')
    freqtrade_pair = self._convert_symbol_to_freqtrade_pair(symbol, exchange)

    enriched = {
        # Core fields
        "pair": freqtrade_pair,  # ✅ Now uses converted format!
        "wave_id": wave_id,
        "direction": signal.get('wave_direction', 'unknown'),
        "rank": rank,
        # ... rest of fields
    }
```

---

## 📊 ПРИМЕР КОНВЕРТАЦИИ

### Входные данные (от WebSocket):
```json
{
  "symbol": "APEUSDT",
  "exchange": "binance",
  "wave_direction": "short"
}
```

### После конвертации:
```json
{
  "pair": "APE/USDT:USDT",  // ✅ Freqtrade format
  "exchange": "binance",
  "direction": "short"
}
```

### Redis ключ:
```
signal:APE/USDT:USDT  // ✅ Freqtrade найдёт этот сигнал!
```

---

## 🔍 ГДЕ ИЗМЕНЕНИЯ

**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/freqtrade_integration/bridge/wave_detector.py`

**Добавлен метод:** `_convert_symbol_to_freqtrade_pair()` (строки 415-445)

**Изменён метод:** `enrich_signal_for_redis()` (строки 471-478)

**Коммит:** 2025-10-21 - Added symbol format conversion WebSocket → Freqtrade

---

## 📋 ЛОГИРОВАНИЕ

При конвертации в логах Bridge появятся:

```log
DEBUG - Converting symbol: APEUSDT → APE/USDT:USDT (exchange: binance)
INFO - Publishing signal for APE/USDT:USDT to Redis...
```

При проблемах с форматом:

```log
WARNING - Symbol XYZABC doesn't end with USDT, using as-is
```

---

## ✅ ПРОВЕРКА РАБОТЫ

### После следующей волны (18:50 UTC):

**1. Проверить Bridge логи:**
```bash
tail -f /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/freqtrade_integration/bridge/bridge.log | grep -E "(Publishing|signal:)"
```

Ожидаем:
```
INFO - Publishing signal for APE/USDT:USDT to Redis...
INFO - Publishing signal for LTC/USDT:USDT to Redis...
```

**2. Проверить Redis ключи:**
```bash
redis-cli KEYS "signal:*"
```

Ожидаем:
```
signal:APE/USDT:USDT
signal:LTC/USDT:USDT
```

**3. Проверить Freqtrade логи:**
```bash
tail -f /Users/evgeniyyanvarskiy/PycharmProjects/FTBot/user_data/logs/freqtrade.binance.testnet.log | grep -E "(Processing signal|Opening)"
```

Ожидаем:
```
INFO - 📊 Processing signal for APE/USDT:USDT
INFO - ✅ Signal accepted (scores: week=61.8, month=77.3)
INFO - Opening short position for APE/USDT:USDT
```

---

## 🎯 ИТОГО

**До исправления:**
1. Bridge: `signal:APEUSDT` (WebSocket format)
2. Freqtrade: ищет `signal:APE/USDT:USDT` (Freqtrade format)
3. Результат: ❌ Сигнал НЕ найден

**После исправления:**
1. Bridge: `signal:APE/USDT:USDT` (Freqtrade format)
2. Freqtrade: ищет `signal:APE/USDT:USDT` (Freqtrade format)
3. Результат: ✅ Сигнал найден и обработан!

---

## 📍 ТЕКУЩИЙ СТАТУС

✅ **Исправление применено:** 2025-10-21 22:47
✅ **Bridge перезапущен:** PID обновлён
⏰ **Следующая волна:** 18:50 UTC (через ~2 минуты)
🔍 **Ожидаем:** Тестирование на реальных сигналах

---

**Дата:** 2025-10-21
**Автор:** Claude Code
**Статус:** ✅ ИСПРАВЛЕНО, ОЖИДАЕТ ТЕСТИРОВАНИЯ
