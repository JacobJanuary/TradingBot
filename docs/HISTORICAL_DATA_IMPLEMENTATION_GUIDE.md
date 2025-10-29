# Historical Data Implementation Guide

## Quick Reference: Getting Data from CCXT

### Most Important: OHLCV Data

#### 1. Recent Price at Timestamp
```python
# Get the 1h candle that contains your signal timestamp
async def get_price_at_signal(exchange_mgr, symbol: str, signal_dt: datetime) -> float:
    """Get closing price of the 1h candle containing signal_dt"""
    # Round down to hour
    candle_start = signal_dt.replace(minute=0, second=0, microsecond=0)
    since_ms = int(candle_start.timestamp() * 1000)

    candles = await exchange_mgr.fetch_ohlcv(symbol, '1h', limit=1)
    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        return c  # Closing price
    return None
```

#### 2. 1h Volume in USDT
```python
# CRITICAL: CCXT returns volume in BASE ASSET, multiply by price!
async def get_1h_volume_usdt(exchange_mgr, symbol: str, target_dt: datetime) -> float:
    """
    Get 1h volume in USDT

    Returns:
        float: Volume in USDT for the 1h candle
    """
    candles = await exchange_mgr.fetch_ohlcv(symbol, '1h', limit=1)
    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        # v = volume in base asset (e.g., BTC)
        # c = closing price (USDT)
        # volume_usdt = base_volume * close_price
        return v * c
    return 0.0
```

#### 3. 1h High and Low After Signal
```python
async def get_1h_high_low_after(exchange_mgr, symbol: str, signal_dt: datetime) -> Dict:
    """
    Get high and low for the hour AFTER the signal

    If signal at 14:30, this returns the 15:00 candle's H/L
    """
    # Get next hour's candle
    signal_hour = signal_dt.replace(minute=0, second=0, microsecond=0)
    next_hour = signal_hour + timedelta(hours=1)
    since_ms = int(next_hour.timestamp() * 1000)

    candles = await exchange_mgr.fetch_ohlcv(symbol, '1h', since=since_ms, limit=1)
    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        return {
            'timestamp': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            'high': h,
            'low': l,
        }
    return None
```

---

## Binance vs Bybit: Key Differences

### Symbol Format (MUST HANDLE!)
```python
# Your database stores: BTCUSDT
# Binance needs: BTCUSDT
# Bybit needs: BTC/USDT:USDT

def normalize_to_exchange_format(symbol: str, exchange_name: str) -> str:
    if exchange_name.lower() == 'bybit':
        base = symbol[:-4]  # Remove 'USDT'
        return f"{base}/USDT:USDT"
    return symbol  # Binance uses format as-is
```

### API Response Format
Both return the same via CCXT:
```python
[timestamp_ms, open, high, low, close, volume]
```

### Rate Limits
- **Binance:** 1200 weight/min (ohlcv = 1 weight, open_interest_history = 10 weights)
- **Bybit:** 120 requests/min (much tighter!)

Use ExchangeManager's built-in rate limiter!

---

## Example: Complete Signal Processing with Historical Data

```python
from core.exchange_manager import ExchangeManager
from datetime import datetime, timezone, timedelta

async def process_signal_with_historical_context(
    exchange_manager: ExchangeManager,
    symbol: str,
    signal_timestamp: datetime
) -> Dict:
    """
    Process trading signal with historical market context

    Returns:
        {
            'symbol': str,
            'signal_timestamp': datetime,
            'entry_price': float,  # Price at signal time
            'entry_hour_volume_usdt': float,
            'next_hour_high': float,
            'next_hour_low': float,
            'open_interest_usdt': float,
            'signal_confidence_data': {...}
        }
    """

    # Step 1: Get the price at signal time
    # Round down to nearest hour
    hour_of_signal = signal_timestamp.replace(minute=0, second=0, microsecond=0)
    since_ms = int(hour_of_signal.timestamp() * 1000)

    # Fetch the 1h candle containing the signal
    candles = await exchange_manager.fetch_ohlcv(
        symbol,
        '1h',
        since=since_ms,
        limit=1
    )

    if not candles:
        logger.error(f"Failed to fetch OHLCV for {symbol}")
        return None

    ts_ms, o, h, l, c, v = candles[0]

    entry_price = c  # Use closing price of the signal hour
    volume_usdt = v * c  # Convert to USDT

    # Step 2: Get next hour's high/low for comparison
    next_hour = hour_of_signal + timedelta(hours=1)
    next_since_ms = int(next_hour.timestamp() * 1000)

    next_candles = await exchange_manager.fetch_ohlcv(
        symbol,
        '1h',
        since=next_since_ms,
        limit=1
    )

    next_high = None
    next_low = None
    if next_candles:
        _, _, next_h, next_l, _, _ = next_candles[0]
        next_high = next_h
        next_low = next_l

    # Step 3: Get current open interest (optional, but useful)
    try:
        oi_data = await exchange_manager.fetch_open_interest_usdt(symbol)
        open_interest = oi_data['open_interest_usdt']
    except Exception as e:
        logger.warning(f"Failed to fetch open interest: {e}")
        open_interest = None

    return {
        'symbol': symbol,
        'signal_timestamp': signal_timestamp,
        'signal_hour': hour_of_signal,
        'entry_price': entry_price,
        'entry_hour_volume_usdt': volume_usdt,
        'entry_hour_high': h,
        'entry_hour_low': l,
        'next_hour_high': next_high,
        'next_hour_low': next_low,
        'open_interest_usdt': open_interest,
        'data_quality': {
            'has_ohlcv': True,
            'has_next_candle': next_candles is not None,
            'has_open_interest': open_interest is not None,
        }
    }
```

---

## Adding Methods to ExchangeManager

### Method 1: Fetch Volume in USDT
```python
# Add to core/exchange_manager.py

async def fetch_ohlcv_volume_usdt(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[Dict]:
    """
    Fetch OHLCV with volume in USDT instead of base asset

    Args:
        symbol: Trading pair
        timeframe: '1m', '5m', '1h', etc
        limit: Number of candles to fetch

    Returns:
        List of dicts with keys: timestamp, open, high, low, close, volume_base, volume_usdt
    """
    candles = await self.fetch_ohlcv(symbol, timeframe, limit=limit)

    result = []
    for ts_ms, o, h, l, c, v in candles:
        result.append({
            'timestamp': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            'open': o,
            'high': h,
            'low': l,
            'close': c,
            'volume_base': v,
            'volume_usdt': v * c,  # CRITICAL: multiply by close price
        })

    return result
```

### Method 2: Fetch Open Interest in USDT
```python
async def fetch_open_interest_usdt(self, symbol: str) -> Dict:
    """
    Fetch current open interest in USDT

    Returns:
        {
            'symbol': str,
            'open_interest_usdt': float,
            'timestamp': datetime
        }
    """
    oi_data = await self.rate_limiter.execute_request(
        self.exchange.fetch_open_interest, symbol
    )

    return {
        'symbol': oi_data['symbol'],
        'open_interest_usdt': float(oi_data['openInterest']),
        'timestamp': datetime.fromtimestamp(oi_data['timestamp'] / 1000, tz=timezone.utc),
    }
```

### Method 3: Fetch Candle at Specific Timestamp
```python
async def fetch_candle_at_timestamp(self, symbol: str, target_dt: datetime, timeframe: str = '1h') -> Dict:
    """
    Fetch the OHLCV candle that contains the target timestamp

    For 1h timeframe:
    - Input: 2025-10-25 14:30
    - Output: 2025-10-25 14:00 candle (covers 14:00-14:59)

    Args:
        symbol: Trading pair
        target_dt: Target datetime (in UTC)
        timeframe: '1m', '5m', '1h', etc

    Returns:
        {
            'timestamp': datetime,
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume_base': float,
            'volume_usdt': float,
        }
    """
    # Map timeframe to minutes
    timeframe_minutes = {
        '1s': 1/60,
        '1m': 1,
        '3m': 3,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
    }

    minutes = timeframe_minutes.get(timeframe, 60)

    # Round down to candle boundary
    target_dt = target_dt.replace(second=0, microsecond=0)
    minute_in_hour = target_dt.minute
    candle_minute = int((minute_in_hour // minutes) * minutes)
    candle_start = target_dt.replace(minute=candle_minute)

    since_ms = int(candle_start.timestamp() * 1000)

    # Fetch the candle
    candles = await self.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=1)

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

---

## Common Patterns

### Pattern 1: Fetch Multiple Days of Data
```python
async def fetch_multiple_days_ohlcv(
    exchange_manager: ExchangeManager,
    symbol: str,
    days: int = 7,
    timeframe: str = '1h'
) -> List[Dict]:
    """Fetch N days of OHLCV data efficiently"""

    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    all_candles = []

    current_dt = start_dt
    while current_dt < datetime.now(timezone.utc):
        candles = await exchange_manager.fetch_ohlcv_volume_usdt(
            symbol,
            timeframe=timeframe,
            limit=100
        )
        all_candles.extend(candles)

        if candles:
            # Move to after last candle
            last_ts = candles[-1]['timestamp']
            if timeframe == '1h':
                current_dt = last_ts + timedelta(hours=1)
            else:
                current_dt = last_ts + timedelta(minutes=5)

        await asyncio.sleep(0.5)  # Rate limit

    return all_candles
```

### Pattern 2: Get Current Market Context
```python
async def get_market_context(
    exchange_manager: ExchangeManager,
    symbol: str
) -> Dict:
    """Get snapshot of current market conditions"""

    # Get last 24h of 1h candles
    candles = await exchange_manager.fetch_ohlcv_volume_usdt(symbol, '1h', limit=24)

    if not candles:
        return None

    # Calculate 24h stats
    closes = [c['close'] for c in candles]
    volumes = [c['volume_usdt'] for c in candles]

    return {
        'symbol': symbol,
        'current_price': closes[-1],
        'price_24h_high': max([c['high'] for c in candles]),
        'price_24h_low': min([c['low'] for c in candles]),
        'price_24h_change': closes[-1] - closes[0],
        'volume_24h_usdt': sum(volumes),
        'avg_hourly_volume_usdt': sum(volumes) / len(volumes),
        'volatility_24h': (max(closes) - min(closes)) / min(closes) * 100,
    }
```

### Pattern 3: Historical Open Interest Analysis
```python
async def analyze_oi_trend(
    exchange_manager: ExchangeManager,
    symbol: str,
    days: int = 7
) -> Dict:
    """Analyze open interest trend over N days"""

    try:
        # Get historical OI (note: Binance uses 4h, Bybit uses 1h)
        since_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

        oi_history = await exchange_manager.exchange.fetch_open_interest_history(
            symbol,
            '4h',
            since=since_ms,
            limit=100
        )

        if not oi_history:
            return None

        oi_values = [float(oi['openInterest']) for oi in oi_history]
        oi_timestamps = [
            datetime.fromtimestamp(oi['timestamp'] / 1000, tz=timezone.utc)
            for oi in oi_history
        ]

        return {
            'symbol': symbol,
            'current_oi_usdt': oi_values[-1],
            'oi_24h_ago': oi_values[-(24//4)] if len(oi_values) >= 6 else None,  # 6 candles = 24h
            'oi_trend': 'increasing' if oi_values[-1] > oi_values[0] else 'decreasing',
            'oi_min': min(oi_values),
            'oi_max': max(oi_values),
            'oi_avg': sum(oi_values) / len(oi_values),
            'oi_change_pct': ((oi_values[-1] - oi_values[0]) / oi_values[0] * 100) if oi_values[0] > 0 else 0,
        }

    except Exception as e:
        logger.error(f"Failed to analyze OI trend: {e}")
        return None
```

---

## Testing

### Test Script
```python
#!/usr/bin/env python3
"""Test historical data fetching"""

import asyncio
from datetime import datetime, timezone, timedelta
from core.exchange_manager import ExchangeManager
from config.settings import config

async def test_historical_data():
    # Initialize exchange
    exchange_config = config.exchanges['binance']
    exchange = ExchangeManager('binance', exchange_config)
    await exchange.initialize()

    symbol = 'BTCUSDT'
    signal_time = datetime.now(timezone.utc) - timedelta(hours=2)

    try:
        # Test 1: Price at signal time
        print("\n1. Testing price at signal time...")
        candle = await exchange.fetch_candle_at_timestamp(symbol, signal_time)
        if candle:
            print(f"  Price: {candle['close']}")

        # Test 2: Volume in USDT
        print("\n2. Testing 1h volume in USDT...")
        candles = await exchange.fetch_ohlcv_volume_usdt(symbol, '1h', limit=3)
        for c in candles:
            print(f"  {c['timestamp']}: {c['volume_usdt']:.2f} USDT")

        # Test 3: Open interest
        print("\n3. Testing open interest...")
        oi = await exchange.fetch_open_interest_usdt(symbol)
        print(f"  Current OI: {oi['open_interest_usdt']:.2f} USDT")

        print("\n✅ All tests passed!")

    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(test_historical_data())
```

---

## Troubleshooting

### Issue: "Symbol not found"
**Solution:** Convert symbol format for Bybit
```python
if exchange.name == 'bybit':
    symbol = 'BTC/USDT:USDT'  # Instead of 'BTCUSDT'
else:
    symbol = 'BTCUSDT'
```

### Issue: Volume is too small
**Solution:** You got volume in base asset, not USDT
```python
# WRONG:
volume = candle[5]  # This is in BTC

# RIGHT:
volume_usdt = candle[5] * candle[4]  # BTC * price = USDT
```

### Issue: Timestamp mismatch
**Solution:** Convert from milliseconds to seconds
```python
# WRONG:
dt = datetime.fromtimestamp(ts_ms)

# RIGHT:
dt = datetime.fromtimestamp(ts_ms / 1000)
```

### Issue: Rate limit errors
**Solution:** Use ExchangeManager's rate limiter
```python
# WRONG:
await exchange.fetch_ohlcv(symbol, '1h')

# RIGHT:
await exchange_manager.fetch_ohlcv(symbol, '1h')  # Built-in rate limiting
```

---

## Performance Tips

1. **Use `limit` parameter efficiently:** Fetch max amount (1000) per request
2. **Batch similar timeframes:** Group 1h requests together
3. **Cache open interest:** Changes slowly, update every 4h
4. **Use `since` parameter:** Start from known position, avoid re-fetching
5. **Add delays between requests:** `await asyncio.sleep(0.5)` for Bybit

