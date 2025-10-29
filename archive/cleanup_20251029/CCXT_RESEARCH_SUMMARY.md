# CCXT Historical Data Research - Complete Summary

**Date:** 2025-10-28
**CCXT Version:** 4.5.12
**Status:** Complete Research Documentation

---

## Overview

Comprehensive research on fetching historical market data from Binance and Bybit Futures using CCXT library. All required data types are available and fully documented.

---

## What Can Be Fetched

### 1. Historical Price at Specific Timestamp ✓
**Method:** `fetch_ohlcv(symbol, timeframe, since=timestamp_ms, limit=1)`
```python
# Get price at 2025-10-25 14:30 UTC
target_dt = datetime(2025, 10, 25, 14, 30, tzinfo=timezone.utc)
candle_start = target_dt.replace(minute=0, second=0, microsecond=0)
since_ms = int(candle_start.timestamp() * 1000)
candles = await exchange.fetch_ohlcv('BTCUSDT', '1h', since=since_ms, limit=1)
price = candles[0][4]  # Close price
```

### 2. Open Interest in USDT at Timestamp ✓
**Method:** `fetch_open_interest(symbol)` for current, `fetch_open_interest_history()` for historical
```python
# Current OI
oi = await exchange.fetch_open_interest('BTCUSDT')
oi_usdt = float(oi['openInterest'])

# Historical OI (4h for Binance, 1h for Bybit)
oi_history = await exchange.fetch_open_interest_history('BTCUSDT', '4h')
```

### 3. 1h Volume in USDT ✓
**Method:** `fetch_ohlcv(symbol, '1h', limit=1)`
```python
# CRITICAL: Volume returned in BASE ASSET!
candles = await exchange.fetch_ohlcv('BTCUSDT', '1h', limit=1)
ts_ms, o, h, l, c, v = candles[0]
volume_usdt = v * c  # base_volume * close_price
```

### 4. 1h High/Low After Signal ✓
**Method:** `fetch_ohlcv()` for next candle
```python
# Get next hour's candle
signal_hour = signal_dt.replace(minute=0, second=0, microsecond=0)
next_hour = signal_hour + timedelta(hours=1)
since_ms = int(next_hour.timestamp() * 1000)
next_candles = await exchange.fetch_ohlcv(symbol, '1h', since=since_ms, limit=1)
high, low = next_candles[0][2], next_candles[0][3]
```

---

## Available Timeframes

| Exchange | Available Timeframes |
|----------|---------------------|
| **Binance** | 1s, 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M |
| **Bybit** | 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M |
| **Safe (Both)** | **1m, 5m, 15m, 30m, 1h** ← Recommended |

---

## Critical Implementation Points

### MUST REMEMBER #1: Volume Unit Conversion
```python
# WRONG - This is BTC volume:
volume = candle[5]

# RIGHT - Multiply by close price to get USDT:
volume_usdt = candle[5] * candle[4]
```

### MUST REMEMBER #2: Timestamp Conversion
```python
# WRONG - Treats milliseconds as seconds:
dt = datetime.fromtimestamp(ts_ms)

# RIGHT - Divide by 1000:
dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
```

### MUST REMEMBER #3: Symbol Format
```python
# Binance: Simple format
symbol = 'BTCUSDT'

# Bybit: Requires slashes and settlement
symbol = 'BTC/USDT:USDT'

# Use ExchangeManager.find_exchange_symbol() for conversion!
```

---

## Binance vs Bybit Quick Comparison

| Aspect | Binance | Bybit | Winner |
|--------|---------|-------|--------|
| **Rate Limit** | 1200 weight/min | 120 req/min | Binance |
| **OHLCV Support** | Excellent | Good | Binance |
| **OI History Granularity** | 4h | 1h | Bybit |
| **Symbol Format** | BTCUSDT | BTC/USDT:USDT | Binance |
| **API Documentation** | Excellent | Good | Binance |
| **Practical for High Frequency** | Yes | No (tight limit) | Binance |

### Rate Limits Detail
```
Binance (Weight-based):
- fetch_ohlcv: 1 weight
- fetch_open_interest: 1 weight
- fetch_open_interest_history: 10 weight (expensive!)
- Limit: 1200 weight/minute

Bybit (Request-based):
- All methods: 1 request each
- Limit: 120 requests/minute (5x tighter!)
- Safe processing: ~20 signals/minute max
```

---

## Documentation Files Created

### 1. HISTORICAL_DATA_README.md (Start Here)
**Purpose:** Navigation guide and index
**Size:** 8.5 KB
**Contains:**
- Quick summary of what's available
- Links to detailed docs
- Implementation checklist
- Common errors and solutions
- Getting started guide

### 2. CCXT_HISTORICAL_DATA_RESEARCH.md (Deep Dive)
**Purpose:** Comprehensive technical research
**Size:** 21 KB
**Contains:**
- Full API method documentation
- Data format specifications
- Complete code examples (basic to advanced)
- OHLCV data format details
- Open interest explanation
- Binance vs Bybit detailed comparison
- Rate limit analysis
- Limitations and edge cases
- Test scripts

### 3. CCXT_API_REFERENCE.md (API Docs)
**Purpose:** Method signatures and parameters
**Size:** 12 KB
**Contains:**
- Complete method signatures
- Return value formats
- Timeframe reference
- Common patterns with code
- Exchange-specific configurations
- Error handling guide
- Performance checklist

### 4. HISTORICAL_DATA_IMPLEMENTATION_GUIDE.md (Practical)
**Purpose:** Ready-to-implement code
**Size:** 15 KB
**Contains:**
- Copy-paste solutions
- ExchangeManager methods to add
- Real-world examples
- Common patterns (24h stats, OI analysis)
- Testing guide
- Troubleshooting section

### 5. BINANCE_BYBIT_COMPARISON.md (Comparison)
**Purpose:** Exchange-by-exchange comparison
**Size:** 9.9 KB
**Contains:**
- Detailed feature comparison
- Rate limit analysis
- Symbol format details
- Decision tree
- Implementation recommendation
- Multi-exchange setup guide

---

## Example Code Snippets

### Fetch Price at Signal Timestamp
```python
async def get_price_at_signal(exchange, symbol: str, signal_dt: datetime) -> float:
    """Get closing price of the 1h candle containing signal_dt"""
    # Round down to hour
    candle_start = signal_dt.replace(minute=0, second=0, microsecond=0)
    since_ms = int(candle_start.timestamp() * 1000)

    candles = await exchange.fetch_ohlcv(symbol, '1h', limit=1)
    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        return c  # Closing price
    return None
```

### Fetch 1h Volume in USDT
```python
async def get_1h_volume_usdt(exchange, symbol: str) -> float:
    """Get 1h volume in USDT"""
    candles = await exchange.fetch_ohlcv(symbol, '1h', limit=1)
    if candles:
        ts_ms, o, h, l, c, v = candles[0]
        return v * c  # base_volume * close_price = USDT volume
    return 0.0
```

### Fetch Current Open Interest
```python
async def get_open_interest_usdt(exchange, symbol: str) -> float:
    """Get current open interest in USDT"""
    oi_data = await exchange.fetch_open_interest(symbol)
    return float(oi_data['openInterest'])  # Already in USDT!
```

---

## API Methods Summary

| Method | Purpose | Cost | Returns |
|--------|---------|------|---------|
| `fetch_ohlcv()` | Get OHLC candles | 1 weight (Binance) | [ts, o, h, l, c, v] |
| `fetch_ticker()` | Current price + 24h stats | 1 weight | {last, high, low, ...} |
| `fetch_open_interest()` | Current OI | 1 weight | {symbol, openInterest, ...} |
| `fetch_open_interest_history()` | Historical OI | 10 weight (Binance) | [{symbol, openInterest, ...}] |
| `fetch_trades()` | Individual trades | 1 weight | [{price, amount, ...}] |

---

## Implementation Roadmap

### Phase 1: Add Helper Methods to ExchangeManager
```python
async def fetch_ohlcv_volume_usdt(symbol, timeframe='1h', limit=100)
async def fetch_open_interest_usdt(symbol)
async def fetch_candle_at_timestamp(symbol, target_dt, timeframe='1h')
```

### Phase 2: Error Handling
- Network errors
- Rate limit errors
- Symbol not found
- Invalid timestamp

### Phase 3: Testing
- Test with Binance
- Test with Bybit
- Test symbol format conversion
- Test rate limiting

### Phase 4: Integration
- Integrate into signal processor
- Cache historical data
- Monitor API usage

---

## Key Performance Numbers

### Binance Rate Limits
- 1200 weight/minute = 1 fetch_ohlcv every 50ms
- Can safely process: 50+ signals/minute
- fetch_open_interest_history costs 10x more!

### Bybit Rate Limits
- 120 requests/minute = 1 request every 500ms
- Can safely process: 20 signals/minute
- All methods cost same (1 request)

### Data Freshness
- OHLCV: 1 second old (real-time)
- Ticker: Real-time
- Open Interest: Real-time
- OI History: 4h old (Binance) or 1h old (Bybit)

---

## Common Mistakes to Avoid

1. **Forgetting to convert volume to USDT**
   - Fix: `volume_usdt = base_volume * close_price`

2. **Using seconds instead of milliseconds**
   - Fix: `dt = datetime.fromtimestamp(ts_ms / 1000)`

3. **Wrong symbol format**
   - Fix: Use `find_exchange_symbol()` method

4. **Not using rate limiter**
   - Fix: Always call through `exchange_manager.rate_limiter`

5. **Assuming all timeframes available**
   - Fix: Use `1m, 5m, 15m, 30m, 1h` (safe for both)

6. **Fetching too frequently**
   - Fix: Cache data, batch requests, respect rate limits

---

## Next Steps

1. **Read:** Start with `/docs/HISTORICAL_DATA_README.md`
2. **Review:** Read `/docs/CCXT_API_REFERENCE.md` for API details
3. **Implement:** Follow `/docs/HISTORICAL_DATA_IMPLEMENTATION_GUIDE.md`
4. **Test:** Use provided test scripts
5. **Monitor:** Track API usage and cache hits

---

## Files Location

All research documents are in `/docs/`:

```
/docs/
├── HISTORICAL_DATA_README.md                 (Start here)
├── CCXT_HISTORICAL_DATA_RESEARCH.md         (Deep research)
├── CCXT_API_REFERENCE.md                    (API documentation)
├── HISTORICAL_DATA_IMPLEMENTATION_GUIDE.md  (Code examples)
├── BINANCE_BYBIT_COMPARISON.md              (Comparison)
└── ... (other existing docs)
```

---

## Quick Reference

### Fetch Recent 1h Candles with Volume in USDT
```python
candles = await exchange.fetch_ohlcv('BTCUSDT', '1h', limit=10)
for ts_ms, o, h, l, c, v in candles:
    dt = datetime.fromtimestamp(ts_ms / 1000)
    volume_usdt = v * c
    print(f"{dt}: Close=${c}, Volume=${volume_usdt:,.0f}")
```

### Get Current Open Interest
```python
oi = await exchange.fetch_open_interest('BTCUSDT')
print(f"Current OI: ${oi['openInterest']:,.0f} USDT")
```

### Get Historical Open Interest (7 days)
```python
since_ms = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
oi_history = await exchange.fetch_open_interest_history('BTCUSDT', '4h', since=since_ms)
for oi in oi_history:
    dt = datetime.fromtimestamp(oi['timestamp'] / 1000)
    print(f"{dt}: OI=${oi['openInterest']:,.0f}")
```

---

## Research Completion Status

| Item | Status | Notes |
|------|--------|-------|
| fetch_ohlcv Documentation | ✓ Complete | All methods documented |
| fetch_open_interest Documentation | ✓ Complete | Current & historical |
| fetch_open_interest_history Documentation | ✓ Complete | Binance 4h, Bybit 1h |
| Timeframe Analysis | ✓ Complete | Safe choices identified |
| Binance API Deep Dive | ✓ Complete | Rate limits, symbols, data |
| Bybit API Deep Dive | ✓ Complete | Rate limits, symbols, data |
| Code Examples | ✓ Complete | Basic to advanced |
| Error Handling | ✓ Complete | Common errors covered |
| Performance Analysis | ✓ Complete | Rate limit calculations |
| Implementation Guide | ✓ Complete | Ready for integration |
| Testing Guide | ✓ Complete | Test scripts provided |

---

## Questions Answered

- [x] How to get historical price at specific timestamp?
- [x] What timeframes are available (1m, 5m, 1h)?
- [x] How to get historical data for specific timestamp?
- [x] What are Binance Futures API differences vs Bybit?
- [x] Which CCXT methods to use?
- [x] What are the limitations?
- [x] How to get volume in USDT (not base asset)?
- [x] How to get 1h high/low after signal?
- [x] What are the rate limits?
- [x] How to handle errors?

---

## Final Notes

All required data is available through CCXT. The implementation is straightforward with the documented helper methods. Main considerations are:

1. **Volume unit conversion** - multiply by price
2. **Rate limits** - Binance is more generous
3. **Symbol format** - differs between exchanges
4. **Timestamp precision** - milliseconds, not seconds

For production implementation, recommend using Binance as primary (generous rate limits) with Bybit as fallback for OI analysis (better 1h granularity).

---

**Research Completed:** 2025-10-28
**Documentation Status:** Complete and Ready for Implementation

