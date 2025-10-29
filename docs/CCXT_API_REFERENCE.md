# CCXT API Reference for Binance & Bybit Futures

## Quick Reference

### Data You Need → Method to Use

| Data Needed | CCXT Method | Timeframe | Notes |
|------------|-------------|-----------|-------|
| Price at specific timestamp | `fetch_ohlcv()` | 1m, 5m, 1h | Round timestamp down to candle |
| 1h volume in USDT | `fetch_ohlcv()` | 1h | `volume * close_price` |
| 1h high/low after signal | `fetch_ohlcv()` | 1h | Fetch next hour's candle |
| Current open interest USDT | `fetch_open_interest()` | Real-time | Direct USDT value |
| Historical open interest | `fetch_open_interest_history()` | 4h (Binance) / 1h (Bybit) | Limited to 3 months |
| 24h volume USDT | `fetch_ohlcv()` | 1h | Sum 24 candles × close price |

---

## Complete API Reference

### 1. fetch_ohlcv() - Fetch OHLC Candles

```python
ohlcv = await exchange.fetch_ohlcv(
    symbol,              # str: 'BTCUSDT' (Binance) or 'BTC/USDT:USDT' (Bybit)
    timeframe='1h',      # str: '1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', etc
    since=None,          # int or None: milliseconds since epoch, or None for recent
    limit=None           # int or None: max candles to return (1000 max)
)
```

**Returns:**
```python
[
    [timestamp_ms, open, high, low, close, volume],
    [timestamp_ms, open, high, low, close, volume],
    ...
]
```

**Example:**
```python
candles = await exchange.fetch_ohlcv('BTCUSDT', '1h', limit=10)
# Returns 10 most recent 1-hour candles

for ts_ms, o, h, l, c, v in candles:
    dt = datetime.fromtimestamp(ts_ms / 1000)  # CRITICAL: divide by 1000!
    print(f"{dt}: Open={o}, High={h}, Low={l}, Close={c}, Volume={v}")
```

**Since Parameter Examples:**
```python
# Fetch candles from specific time
target_time = datetime(2025, 10, 25, 14, 0, tzinfo=timezone.utc)
since_ms = int(target_time.timestamp() * 1000)
candles = await exchange.fetch_ohlcv('BTCUSDT', '1h', since=since_ms, limit=50)

# CRITICAL: Returns candles starting from BEFORE your 'since' time
# First candle might be at 13:00 even if you request since 14:00
```

**Rate Limits:**
- Binance: 1 weight per request
- Bybit: 1 standard request
- Limit: 1000 candles per request

---

### 2. fetch_open_interest() - Current Open Interest

```python
oi = await exchange.fetch_open_interest(
    symbol='BTCUSDT'     # str: trading pair
)
```

**Returns:**
```python
{
    'symbol': 'BTCUSDT',
    'openInterest': 1234567890.50,  # USDT notional value
    'timestamp': 1698234567890,     # milliseconds
    'info': {...}                   # Raw exchange data
}
```

**Example:**
```python
oi_data = await exchange.fetch_open_interest('BTCUSDT')
print(f"Open Interest: ${oi_data['openInterest']:,.2f} USDT")
# Output: Open Interest: $1,234,567,890.50 USDT
```

**Rate Limits:**
- Binance: 1 weight
- Bybit: 1 standard request
- **No historical data**, returns current value only

---

### 3. fetch_open_interest_history() - Historical Open Interest

```python
oi_history = await exchange.fetch_open_interest_history(
    symbol='BTCUSDT',            # str: trading pair
    timeframe='4h',              # str: '4h' (Binance), '1h' (Bybit)
    since=1698234567890,         # int: milliseconds, or None for recent
    limit=100                    # int: max data points (varies by exchange)
)
```

**Returns:**
```python
[
    {
        'symbol': 'BTCUSDT',
        'openInterest': 1234567890.50,
        'timestamp': 1698234567890,
        'info': {...}
    },
    {
        'symbol': 'BTCUSDT',
        'openInterest': 1234512345.00,
        'timestamp': 1698220167890,
        'info': {...}
    },
    ...
]
```

**Example:**
```python
# Get 7 days of open interest history
since_ms = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
oi_history = await exchange.fetch_open_interest_history(
    'BTCUSDT',
    timeframe='4h',
    since=since_ms,
    limit=100
)

for oi_data in oi_history:
    dt = datetime.fromtimestamp(oi_data['timestamp'] / 1000)
    print(f"{dt}: OI={oi_data['openInterest']:,.0f} USDT")
```

**Rate Limits:**
- Binance: 10 weight per request ⚠️ EXPENSIVE!
- Bybit: Higher cost
- Use sparingly!

**Limitations:**
- Binance: 4h intervals only, last 3 months
- Bybit: 1h intervals, last 3 months
- Data is sparse (not available for all symbols)

---

### 4. fetch_ticker() - Current Price & 24h Stats

```python
ticker = await exchange.fetch_ticker(
    symbol='BTCUSDT'     # str: trading pair
)
```

**Returns:**
```python
{
    'symbol': 'BTCUSDT',
    'last': 45000.50,           # Current price
    'open': 44000.00,           # 24h open
    'high': 46000.00,           # 24h high
    'low': 43000.00,            # 24h low
    'bid': 45000.25,            # Best bid
    'ask': 45000.75,            # Best ask
    'close': 45000.50,          # Last close
    'baseVolume': 123.45,       # 24h volume (base asset)
    'quoteVolume': 5550000.00,  # 24h volume (USDT)
    'timestamp': 1698234567890,
    'info': {...}               # Raw exchange data
}
```

**Example:**
```python
ticker = await exchange.fetch_ticker('BTCUSDT')
print(f"Last: ${ticker['last']:.2f}")
print(f"High: ${ticker['high']:.2f}")
print(f"Low: ${ticker['low']:.2f}")
print(f"24h Volume: ${ticker['quoteVolume']:,.0f} USDT")
```

**Rate Limits:**
- Binance: 1 weight
- Bybit: 1 standard request

---

### 5. fetch_trades() - Recent Trades

```python
trades = await exchange.fetch_trades(
    symbol='BTCUSDT',    # str: trading pair
    since=1698234567890, # int: milliseconds, or None for recent
    limit=1000           # int: max trades (varies by exchange)
)
```

**Returns:**
```python
[
    {
        'id': '12345678',
        'timestamp': 1698234567890,
        'datetime': '2025-10-25T14:30:00Z',
        'symbol': 'BTCUSDT',
        'type': None,
        'side': 'buy',          # 'buy' or 'sell'
        'price': 45000.50,      # Price in USDT
        'amount': 1.234,        # Amount in BTC
        'cost': 55506.18,       # Price × Amount
        'info': {...}
    },
    ...
]
```

**Note:** For accurate volume calculation by time period, you would need to sum individual trades. This is slow (100+ API calls for 1h), so use OHLCV instead!

**Rate Limits:**
- Binance: 1 weight
- Bybit: 1 standard request

---

## Timeframe Values

### Supported Values

**Binance Futures:**
```python
'1s', '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'
```

**Bybit Futures:**
```python
'1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w', '1M'
```

**Recommended (both exchanges):**
```python
'1m', '5m', '15m', '30m', '1h'  # Safe choices for both exchanges
```

### Timeframe to Minutes Conversion

```python
TIMEFRAME_MINUTES = {
    '1s': 1/60,
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
    '2h': 120,
    '4h': 240,
    '6h': 360,
    '8h': 480,
    '12h': 720,
    '1d': 1440,
    '3d': 4320,
    '1w': 10080,
    '1M': 43200,
}
```

---

## Common Patterns

### Pattern 1: Timestamp Rounding

```python
def round_timestamp_down_to_candle(dt: datetime, timeframe: str) -> datetime:
    """Round datetime down to the start of a candle"""
    timeframe_minutes = {
        '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60,
    }

    minutes = timeframe_minutes.get(timeframe, 60)

    # Round down minutes
    rounded_minute = (dt.minute // minutes) * minutes
    rounded_dt = dt.replace(minute=rounded_minute, second=0, microsecond=0)

    return rounded_dt

# Example
signal_time = datetime(2025, 10, 25, 14, 35, 45, tzinfo=timezone.utc)
candle_start = round_timestamp_down_to_candle(signal_time, '1h')
# Result: 2025-10-25 14:00:00 UTC
```

### Pattern 2: Timestamp to Milliseconds

```python
# To milliseconds (for 'since' parameter)
dt = datetime(2025, 10, 25, 14, 0, tzinfo=timezone.utc)
since_ms = int(dt.timestamp() * 1000)
# Result: 1698238800000

# From milliseconds (CCXT return value)
ts_ms = 1698238800000
dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
# Result: 2025-10-25 14:00:00 UTC+00:00
```

### Pattern 3: Calculate Candle Duration

```python
def get_candle_duration_seconds(timeframe: str) -> int:
    """Get duration of a candle in seconds"""
    timeframe_seconds = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '30m': 1800,
        '1h': 3600,
        '4h': 14400,
        '1d': 86400,
    }
    return timeframe_seconds.get(timeframe, 3600)
```

### Pattern 4: Volume to USDT Conversion

```python
# CRITICAL: CCXT returns volume in BASE ASSET
async def get_volume_usdt(exchange, symbol: str, timeframe: str) -> float:
    """Get volume in USDT"""
    candles = await exchange.fetch_ohlcv(symbol, timeframe, limit=1)
    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        # v = volume in base asset (BTC for BTCUSDT)
        # c = close price (USDT for BTCUSDT)
        return v * c
    return 0.0
```

---

## Exchange-Specific Details

### Binance Futures

**Characteristics:**
- Symbol format: `BTCUSDT` (no slashes)
- Timeframes: 1s, 1m, 3m, 5m, 15m, 30m, 1h, ...
- OHLCV limit: 1000 per request
- Rate limit: 1200 weight/minute
- Open interest history: 4h intervals only

**Exchange Specification:**
```python
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',  # CRITICAL for futures data
    }
})
```

**Known Issues:**
- None specific to data fetching
- Rate limits are generous

### Bybit Futures

**Characteristics:**
- Symbol format: `BTC/USDT:USDT` (with slashes and settlement)
- Timeframes: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M
- OHLCV limit: 1000 per request
- Rate limit: 120 requests/minute (MUCH tighter!)
- Open interest history: 1h intervals

**Exchange Specification:**
```python
exchange = ccxt.bybit({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'accountType': 'UNIFIED',  # CRITICAL for unified account
    }
})
```

**Known Issues:**
- Tighter rate limits (120/min vs Binance's 1200/min)
- Symbol format with `/` and `:USDT:USDT`
- May require explicit `category='linear'` in some methods

**Symbol Conversion:**
```python
def to_bybit_symbol(normalized: str) -> str:
    """Convert BTCUSDT → BTC/USDT:USDT"""
    base = normalized[:-4]  # Remove 'USDT'
    return f"{base}/USDT:USDT"

# Example
symbol = to_bybit_symbol('BTCUSDT')  # 'BTC/USDT:USDT'
```

---

## Error Handling

### Common Errors

```python
import ccxt

try:
    candles = await exchange.fetch_ohlcv('BTCUSDT', '1h')
except ccxt.NetworkError as e:
    print(f"Network error: {e}")
except ccxt.ExchangeNotAvailable as e:
    print(f"Exchange maintenance: {e}")
except ccxt.RateLimitExceeded as e:
    print(f"Rate limited, retry after: {e}")
except ccxt.InvalidSymbol as e:
    print(f"Symbol not found: {e}")
except ccxt.BaseError as e:
    print(f"CCXT error: {e}")
```

---

## Performance Checklist

- [ ] Use `limit=1000` to fetch maximum candles per request
- [ ] Use `since` parameter to avoid fetching old data
- [ ] Add `await asyncio.sleep(0.5)` between Bybit requests
- [ ] Cache ticker data (changes slowly)
- [ ] Batch requests: don't fetch one symbol at a time
- [ ] Use ExchangeManager's rate limiter
- [ ] Don't use `fetch_trades()` for volume (use OHLCV instead)
- [ ] Store historical data locally to reduce API calls

---

## Testing

### Minimal Test Script

```python
#!/usr/bin/env python3
import asyncio
import ccxt.async_support as ccxt
from datetime import datetime, timezone, timedelta

async def test():
    binance = ccxt.binance({'enableRateLimit': True})
    symbol = 'BTCUSDT'

    # Test 1: Recent candles
    print("1. Recent candles:")
    candles = await binance.fetch_ohlcv(symbol, '1h', limit=3)
    for ts_ms, o, h, l, c, v in candles:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        print(f"  {dt}: Close=${c:.2f}, Volume={v*c:,.0f} USDT")

    # Test 2: Open interest
    print("\n2. Open interest:")
    oi = await binance.fetch_open_interest(symbol)
    print(f"  Current OI: ${oi['openInterest']:,.0f} USDT")

    # Test 3: Ticker
    print("\n3. Ticker:")
    ticker = await binance.fetch_ticker(symbol)
    print(f"  Last: ${ticker['last']:.2f}")
    print(f"  24h Volume: ${ticker['quoteVolume']:,.0f} USDT")

    await binance.close()

asyncio.run(test())
```

---

## References

- [CCXT GitHub](https://github.com/ccxt/ccxt)
- [CCXT Docs - fetch_ohlcv](https://docs.ccxt.com/en/latest/manual/README.html#ohlcv)
- [Binance Futures API Docs](https://binance-docs.github.io/apidocs/futures/en/)
- [Bybit V5 API Docs](https://bybit-exchange.github.io/docs/v5/intro)

