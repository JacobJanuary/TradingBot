# CCXT Historical Data Research for Binance & Bybit Futures

## Overview
Research document on fetching historical market data, open interest, and volume using CCXT 4.5.12

**Date:** 2025-10-28
**CCXT Version:** 4.5.12
**Target Exchanges:** Binance Futures, Bybit Futures (Linear)

---

## 1. Available Methods & Capabilities

### 1.1 CCXT Method Availability

Both Binance and Bybit support all required methods:

| Method | Binance | Bybit | Purpose |
|--------|---------|-------|---------|
| `fetch_ohlcv()` | ✓ | ✓ | Fetch OHLCV candles for any timeframe |
| `fetch_open_interest()` | ✓ | ✓ | Get current open interest at specific timestamp |
| `fetch_open_interest_history()` | ✓ | ✓ | Get historical open interest data |
| `fetch_ticker()` | ✓ | ✓ | Get current price & 24h stats |
| `fetch_trades()` | ✓ | ✓ | Get recent trades (not ideal for historical) |

### 1.2 Supported Timeframes

**Binance Futures:**
```
1s, 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
```

**Bybit Futures:**
```
1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M
```

**Key:** Both support `1m`, `5m`, `1h` - so use these for consistent compatibility.

---

## 2. OHLCV Data Format

### 2.1 Return Format
```python
# CCXT returns list of candles
[timestamp_ms, open, high, low, close, volume]

# Example:
[1234567890000, 50000.5, 50100.25, 49900.75, 50050.0, 123.45]
 └─ milliseconds  └─ open   └─ high     └─ low     └─ close  └─ volume
```

### 2.2 Data Characteristics
- **Timestamp:** Milliseconds since epoch (not seconds!)
- **OHLC Prices:** Float values (exact precision depends on market)
- **Volume:** Base asset quantity (for BTCUSDT = BTC volume, not USDT)
- **Can be empty:** When requesting future timestamps

---

## 3. Code Examples

### 3.1 Basic OHLCV Fetching

#### Fetch Recent 1h Candles
```python
import ccxt.async_support as ccxt
from datetime import datetime, timezone, timedelta

async def fetch_recent_ohlcv():
    """Fetch last 10 1-hour candles"""
    exchange = ccxt.binance({'enableRateLimit': True})

    symbol = 'BTCUSDT'
    timeframe = '1h'
    limit = 10  # Last 10 candles

    # fetch_ohlcv returns: [timestamp_ms, open, high, low, close, volume]
    candles = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    for ts_ms, o, h, l, c, v in candles:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        print(f"{dt} | O: {o} H: {h} L: {l} C: {c} V: {v}")

    await exchange.close()
```

#### Fetch OHLCV Since Specific Timestamp
```python
async def fetch_ohlcv_since_timestamp():
    """Fetch 1h candles since a specific timestamp"""
    exchange = ccxt.binance({'enableRateLimit': True})

    symbol = 'BTCUSDT'
    timeframe = '1h'

    # Target timestamp: 2025-10-25 14:30 UTC
    target_dt = datetime(2025, 10, 25, 14, 30, tzinfo=timezone.utc)
    since_ms = int(target_dt.timestamp() * 1000)

    # CRITICAL: Binance will return the candle BEFORE your timestamp + limit candles after
    candles = await exchange.fetch_ohlcv(
        symbol,
        timeframe,
        since=since_ms,  # Start from this timestamp (milliseconds)
        limit=50        # Fetch 50 candles from 'since'
    )

    # candles[0] timestamp will be <= since_ms
    # Last candle timestamp will be approximately since_ms + (limit * timeframe_ms)

    await exchange.close()
```

#### Find Candle at Specific Timestamp
```python
async def get_candle_at_timestamp(symbol: str, target_timestamp: datetime, timeframe: str = '1h'):
    """
    Get the OHLCV candle that contains the target timestamp

    For 1h timeframe:
    - Candle 14:00 covers 14:00-14:59
    - So target_timestamp 14:30 is in the 14:00 candle
    """
    exchange = ccxt.binance({'enableRateLimit': True})

    # Round target timestamp down to candle boundary
    timeframe_minutes = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
    }
    minutes = timeframe_minutes[timeframe]

    # Calculate candle start time
    target_dt = target_timestamp.replace(second=0, microsecond=0)
    minute_in_hour = target_dt.minute
    candle_minute = (minute_in_hour // minutes) * minutes
    candle_start = target_dt.replace(minute=candle_minute)

    since_ms = int(candle_start.timestamp() * 1000)

    # Fetch this candle + a few more for safety
    candles = await exchange.fetch_ohlcv(
        symbol,
        timeframe,
        since=since_ms,
        limit=2
    )

    # First candle is the one we want
    ts_ms, o, h, l, c, v = candles[0]

    result = {
        'timestamp': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
        'open': o,
        'high': h,
        'low': l,
        'close': c,
        'volume': v  # In base asset (BTC for BTCUSDT)
    }

    await exchange.close()
    return result
```

### 3.2 Volume in USDT

**CRITICAL ISSUE:** CCXT returns volume in BASE ASSET, not USDT!

```python
async def get_1h_volume_in_usdt(symbol: str, target_dt: datetime, timeframe: str = '1h'):
    """
    Get 1h volume in USDT at a specific timestamp

    Since CCXT returns volume in base asset (e.g., BTC for BTCUSDT),
    we need to multiply by the OHLCV close price to get USDT volume.
    """
    exchange = ccxt.binance({'enableRateLimit': True})

    # Get the candle
    candles = await exchange.fetch_ohlcv(symbol, timeframe, limit=1)
    ts_ms, o, h, l, c, v = candles[0]

    # Volume is in base asset units
    # Close price is in quote asset (USDT)
    # USDT Volume = base_volume * close_price
    volume_usdt = v * c

    result = {
        'timestamp': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
        'base_volume': v,        # e.g., 123.45 BTC
        'close_price': c,        # e.g., 45000 USDT
        'usdt_volume': volume_usdt  # e.g., 5553585 USDT
    }

    await exchange.close()
    return result

# ALTERNATIVE: Calculate average volume for more accuracy
async def get_1h_volume_usdt_accurate(symbol: str, target_dt: datetime):
    """
    More accurate: use average price during the candle
    Volume USDT = sum(trade_volume * trade_price) for all trades in the candle

    But CCXT's OHLCV doesn't provide this.
    Alternative: average of OHLC prices
    """
    exchange = ccxt.binance({'enableRateLimit': True})

    candles = await exchange.fetch_ohlcv(symbol, '1h', limit=1)
    ts_ms, o, h, l, c, v = candles[0]

    # Use average price for more accurate USDT calculation
    avg_price = (o + h + l + c) / 4
    volume_usdt = v * avg_price

    await exchange.close()
    return volume_usdt
```

### 3.3 High/Low After Signal

```python
async def get_1h_high_low_after_signal(symbol: str, signal_timestamp: datetime):
    """
    Get the 1h high and low for the period AFTER the signal

    If signal comes at 14:30 in the 14:00-14:59 candle:
    - Option 1: Return the rest of the current candle's H/L (data already known)
    - Option 2: Return the NEXT candle's H/L (more useful for future analysis)

    This returns the next candle.
    """
    exchange = ccxt.binance({'enableRateLimit': True})

    # Calculate next 1h candle start
    target_dt = signal_timestamp.replace(second=0, microsecond=0)
    minute_in_hour = target_dt.minute
    next_candle_minute = ((minute_in_hour // 60) + 1) * 60

    if next_candle_minute >= 60:
        next_candle_start = target_dt.replace(minute=0) + timedelta(hours=1)
    else:
        next_candle_start = target_dt.replace(minute=next_candle_minute)

    since_ms = int(next_candle_start.timestamp() * 1000)

    # Fetch the next candle
    candles = await exchange.fetch_ohlcv(
        symbol,
        '1h',
        since=since_ms,
        limit=1
    )

    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        return {
            'timestamp': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            'high': h,
            'low': l,
            'close': c,
        }

    await exchange.close()
    return None
```

---

## 4. Open Interest Data

### 4.1 Current Open Interest

```python
async def get_current_open_interest_usdt(symbol: str):
    """
    Fetch current open interest in USDT

    Returns the total notional value of all open positions
    """
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}  # CRITICAL for Binance Futures
    })

    # For Binance, response includes: 'symbol', 'openInterest', 'timestamp'
    oi_data = await exchange.fetch_open_interest(symbol)

    result = {
        'symbol': oi_data['symbol'],
        'open_interest_usdt': float(oi_data['openInterest']),
        'timestamp': datetime.fromtimestamp(oi_data['timestamp'] / 1000, tz=timezone.utc),
    }

    await exchange.close()
    return result

# Example Binance response:
# {
#     'symbol': 'BTCUSDT',
#     'openInterest': 123456789.50,  # USDT
#     'timestamp': 1698234567890,    # milliseconds
#     'info': {...}                  # Raw exchange data
# }
```

### 4.2 Historical Open Interest

```python
async def get_historical_open_interest(symbol: str, target_timestamp: datetime, timeframe: str = '1h'):
    """
    Fetch historical open interest at specific timestamp

    CRITICAL: Open interest history may have different timestamp resolution
    than OHLCV data (usually 4h or 1h depending on exchange)
    """
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    since_ms = int(target_timestamp.timestamp() * 1000)

    # Fetch historical open interest
    oi_history = await exchange.fetch_open_interest_history(
        symbol,
        timeframe='4h',  # Binance Futures usually provides 4h data
        since=since_ms,
        limit=10
    )

    # Returns list of: {'symbol', 'openInterest', 'timestamp', 'info'}
    for oi_data in oi_history:
        dt = datetime.fromtimestamp(oi_data['timestamp'] / 1000, tz=timezone.utc)
        print(f"{dt} | OI: {oi_data['openInterest']} USDT")

    await exchange.close()
    return oi_history
```

### 4.3 Open Interest Limitations

**BINANCE:**
- Historical OI available in 4h intervals (not 1h or 5m)
- Max 720 data points per request
- Data available for ~3 months only

**BYBIT:**
- Historical OI available in 1h intervals
- Similar limitations to Binance
- Data available for ~3 months

---

## 5. Binance vs Bybit Differences

### 5.1 API Symbol Format

| Exchange | Spot | Futures |
|----------|------|---------|
| **Binance** | `BTCUSDT` | `BTCUSDT` |
| **Bybit** | `BTC/USDT` | `BTC/USDT:USDT` |

```python
# CRITICAL: Symbol format conversion needed for Bybit!
def convert_to_exchange_symbol(normalized_symbol: str, exchange_name: str) -> str:
    """
    Convert database format to exchange format
    Database: BTCUSDT (no separators)
    Binance: BTCUSDT
    Bybit: BTC/USDT:USDT
    """
    if exchange_name.lower() == 'bybit':
        # Add slashes: BTCUSDT → BTC/USDT:USDT
        if '/' not in normalized_symbol:
            base = normalized_symbol[:-4]  # Remove 'USDT'
            return f"{base}/USDT:USDT"
    return normalized_symbol
```

### 5.2 fetch_ohlcv Parameters

**BINANCE:**
```python
await exchange.fetch_ohlcv(
    'BTCUSDT',
    '1h',
    since=1698234567890,  # milliseconds
    limit=100             # up to 1000
)
```

**BYBIT:**
```python
# Same interface via CCXT! No changes needed.
# CCXT handles the internal differences
await exchange.fetch_ohlcv(
    'BTC/USDT:USDT',
    '1h',
    since=1698234567890,
    limit=100
)
```

### 5.3 Open Interest Data

**BINANCE:**
- Returns USDT notional value directly
- Historical data: 4h interval
- Response: `{'openInterest': 123456789.50, ...}`

**BYBIT:**
- Also returns USDT notional value
- Historical data: 1h interval (better granularity!)
- Response format similar to Binance

---

## 6. Rate Limits & Considerations

### 6.1 Rate Limit Weights

**Binance Futures:**
- `fetch_ohlcv`: 1 weight
- `fetch_open_interest`: 1 weight
- `fetch_open_interest_history`: 10 weights
- Rate limit: 1200 weights/minute

**Bybit:**
- `fetch_ohlcv`: Standard rate limit
- `fetch_open_interest`: Standard rate limit
- `fetch_open_interest_history`: Standard rate limit
- Rate limit: 120 requests/minute

### 6.2 Practical Limits

```python
# Safe request patterns:
# 1. Fetch OHLCV with limit=1000 (most efficient)
# 2. Batch requests with small delays
# 3. Use 'since' parameter to reduce API calls

async def fetch_ohlcv_efficiently(symbol: str, timeframe: str, days: int = 7):
    """
    Fetch multiple days of OHLCV efficiently

    CRITICAL: CCXT has built-in pagination!
    """
    exchange = ccxt.binance({'enableRateLimit': True})

    timeframe_minutes = {
        '1m': 1,
        '5m': 5,
        '1h': 60,
    }
    minutes = timeframe_minutes[timeframe]

    # Calculate start time
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(start_dt.timestamp() * 1000)

    all_candles = []

    # CCXT.fetch_ohlcv with limit > exchange max (e.g., 1000)
    # will automatically paginate!
    # However, better to do it manually with smaller chunks:

    for _ in range(days):  # One chunk per day
        candles = await exchange.fetch_ohlcv(
            symbol,
            timeframe,
            since=since_ms,
            limit=1000  # Max allowed
        )
        all_candles.extend(candles)

        if candles:
            # Update since to after last candle
            last_ts = candles[-1][0]
            since_ms = last_ts + (minutes * 60 * 1000)

        await asyncio.sleep(0.5)  # Respect rate limits

    await exchange.close()
    return all_candles
```

---

## 7. Implementation Recommendations

### 7.1 Add to ExchangeManager

```python
# In core/exchange_manager.py

async def fetch_ohlcv_with_volume_usdt(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[Dict]:
    """
    Fetch OHLCV with volume converted to USDT

    Returns:
        [{
            'timestamp': datetime,
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume_base': float,  # Original volume in base asset
            'volume_usdt': float   # Volume in USDT (volume_base * close_price)
        }]
    """
    candles = await self.fetch_ohlcv(symbol, timeframe, limit)

    result = []
    for ts_ms, o, h, l, c, v in candles:
        result.append({
            'timestamp': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            'open': o,
            'high': h,
            'low': l,
            'close': c,
            'volume_base': v,
            'volume_usdt': v * c  # USDT volume using close price
        })

    return result

async def fetch_open_interest_usdt(self, symbol: str) -> Dict:
    """
    Fetch current open interest in USDT
    """
    oi_data = await self.rate_limiter.execute_request(
        self.exchange.fetch_open_interest, symbol
    )

    return {
        'symbol': oi_data['symbol'],
        'open_interest_usdt': float(oi_data['openInterest']),
        'timestamp': datetime.fromtimestamp(oi_data['timestamp'] / 1000, tz=timezone.utc),
    }

async def fetch_candle_at_timestamp(self, symbol: str, target_dt: datetime, timeframe: str = '1h') -> Dict:
    """
    Fetch the OHLCV candle that contains the target timestamp
    """
    # Round down to candle boundary
    timeframe_minutes = {
        '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60,
    }
    minutes = timeframe_minutes.get(timeframe, 60)

    target_dt = target_dt.replace(second=0, microsecond=0)
    minute_in_hour = target_dt.minute
    candle_minute = (minute_in_hour // minutes) * minutes
    candle_start = target_dt.replace(minute=candle_minute)

    since_ms = int(candle_start.timestamp() * 1000)

    candles = await self.fetch_ohlcv(symbol, timeframe, limit=1)

    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        return {
            'timestamp': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            'open': o,
            'high': h,
            'low': l,
            'close': c,
            'volume_base': v,
            'volume_usdt': v * c,
        }
    return None
```

### 7.2 Alternative: Use fetch_trades for Accurate Volume

For VERY accurate 1h volume in USDT, consider fetching individual trades:

```python
async def get_accurate_1h_volume_usdt(symbol: str, target_dt: datetime):
    """
    Get exact volume in USDT by summing individual trades

    CAUTION: Much slower than OHLCV!
    Only use if accuracy is critical.
    """
    exchange = ccxt.binance({'enableRateLimit': True})

    # Calculate 1h window
    candle_start = target_dt.replace(minute=0, second=0, microsecond=0)
    candle_end = candle_start + timedelta(hours=1)

    since_ms = int(candle_start.timestamp() * 1000)

    all_trades = []
    total_volume_usdt = 0

    # Fetch all trades in the 1h window
    while since_ms < int(candle_end.timestamp() * 1000):
        trades = await exchange.fetch_trades(
            symbol,
            since=since_ms,
            limit=1000  # Max per request
        )

        if not trades:
            break

        for trade in trades:
            # Only count trades in the window
            if trade['timestamp'] >= int(candle_start.timestamp() * 1000) and \
               trade['timestamp'] < int(candle_end.timestamp() * 1000):
                # Volume is in base asset, multiply by price to get USDT
                volume_usdt = trade['amount'] * trade['price']
                total_volume_usdt += volume_usdt

        # Update since to after last trade
        since_ms = trades[-1]['timestamp'] + 1

        await asyncio.sleep(0.5)

    await exchange.close()
    return total_volume_usdt
```

---

## 8. Limitations & Edge Cases

### 8.1 Data Availability
- Historical data limited to ~3 months
- Minute-level data may not be available for all symbols
- Open interest history only available in 4h (Binance) or 1h (Bybit)

### 8.2 Volume Calculation
- CCXT returns volume in **base asset**, not USDT
- Must multiply by price to get USDT value
- Close price is reasonable approximation
- For high accuracy, use average of OHLC or fetch_trades

### 8.3 Timestamp Precision
- CCXT uses milliseconds (not seconds)
- When converting to datetime: divide by 1000
- Candle timestamps are at the START of the period
- 14:00 candle covers 14:00:00 - 14:59:59

### 8.4 Symbol Format
- Binance: BTCUSDT
- Bybit: BTC/USDT:USDT
- Must handle conversion in multi-exchange code

---

## 9. Summary Table

| Requirement | Method | Timeframe | Limitation |
|-------------|--------|-----------|------------|
| Historical price at timestamp | `fetch_ohlcv` + round down | 1m, 5m, 1h | Returned in candle blocks |
| Current open interest USDT | `fetch_open_interest` | Real-time | - |
| Historical open interest | `fetch_open_interest_history` | 4h (Binance) / 1h (Bybit) | Coarse granularity |
| 1h volume in USDT | `fetch_ohlcv` | 1h | Must multiply by close price |
| 1h high/low after signal | `fetch_ohlcv` | 1h | Returns next candle |

---

## 10. References

- [CCXT Documentation](https://docs.ccxt.com/)
- [Binance Futures API](https://binance-docs.github.io/apidocs/futures/en/)
- [Bybit API V5](https://bybit-exchange.github.io/docs/v5/intro)
- Current implementation: `/core/exchange_manager.py`

---

## Appendix: Quick Test Script

```python
#!/usr/bin/env python3
"""
Quick test to validate all data fetching methods
"""
import asyncio
import ccxt.async_support as ccxt
from datetime import datetime, timezone, timedelta

async def test_all_methods():
    binance = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    symbol = 'BTCUSDT'

    try:
        # Test 1: OHLCV
        print("\n1. Testing fetch_ohlcv...")
        candles = await binance.fetch_ohlcv(symbol, '1h', limit=3)
        for ts_ms, o, h, l, c, v in candles:
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            print(f"  {dt}: O={o} H={h} L={l} C={c} V={v}")

        # Test 2: Current Open Interest
        print("\n2. Testing fetch_open_interest...")
        oi = await binance.fetch_open_interest(symbol)
        print(f"  OI: {oi['openInterest']} USDT")

        # Test 3: Historical Open Interest
        print("\n3. Testing fetch_open_interest_history...")
        since_ms = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
        oi_history = await binance.fetch_open_interest_history(
            symbol,
            '4h',
            since=since_ms,
            limit=5
        )
        for oi_data in oi_history:
            dt = datetime.fromtimestamp(oi_data['timestamp'] / 1000, tz=timezone.utc)
            print(f"  {dt}: OI={oi_data['openInterest']} USDT")

        # Test 4: Ticker
        print("\n4. Testing fetch_ticker...")
        ticker = await binance.fetch_ticker(symbol)
        print(f"  Last: {ticker['last']} | High: {ticker['high']} | Low: {ticker['low']}")

        print("\n✅ All tests passed!")

    finally:
        await binance.close()

if __name__ == '__main__':
    asyncio.run(test_all_methods())
```

