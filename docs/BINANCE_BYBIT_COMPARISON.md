# Binance vs Bybit Futures - Technical Comparison for Data Fetching

## Executive Summary

Both exchanges support all required data methods through CCXT. Main differences are in rate limits, symbol format, and data granularity.

| Aspect | Binance | Bybit | Winner |
|--------|---------|-------|--------|
| **Rate Limit** | 1200 weight/min | 120 req/min | Binance |
| **Symbol Format** | BTCUSDT | BTC/USDT:USDT | Binance |
| **OI History Granularity** | 4h | 1h | Bybit |
| **API Stability** | Excellent | Good | Binance |
| **Documentation** | Excellent | Good | Binance |
| **OHLCV Availability** | Same | Same | Tie |

---

## Detailed Comparison

### 1. API Rate Limits

#### Binance Futures
```
Weight-based system:
- 1200 weight per minute
- fetch_ohlcv: 1 weight
- fetch_open_interest: 1 weight
- fetch_open_interest_history: 10 weight
- fetch_ticker: 1 weight

Example: You can make 1200 ohlcv requests per minute
```

**Practical Impact:**
- Very generous for most use cases
- Can fetch 1000 candles per symbol easily
- Safe to fetch multiple symbols in parallel

#### Bybit
```
Rate-based system:
- 120 requests per minute (standard limit)
- All methods count as 1 request
- Higher-tier accounts get more

Example: You can make 120 total requests per minute
```

**Practical Impact:**
- Much tighter limit
- Must batch requests carefully
- Parallel requests risky without delays
- Need to optimize request patterns

#### Verdict: **Binance wins for data fetching**

---

### 2. Symbol Format

#### Binance Futures
```
Format: BTCUSDT (no separators)

Examples:
- BTC/USDT:USDT → BTCUSDT
- ETH/USDT:USDT → ETHUSDT
- SOL/USDT:USDT → SOLUSDT

Code:
symbol = 'BTCUSDT'
await exchange.fetch_ohlcv(symbol, '1h')
```

#### Bybit Futures
```
Format: BTC/USDT:USDT (with slashes and settlement)

Examples:
- BTCUSDT → BTC/USDT:USDT
- ETHUSDT → ETH/USDT:USDT
- SOLUSDT → SOL/USDT:USDT

Code:
symbol = 'BTC/USDT:USDT'
await exchange.fetch_ohlcv(symbol, '1h')
```

#### Conversion Function
```python
def normalize_symbol_for_exchange(db_symbol: str, exchange: str) -> str:
    """Convert database format to exchange format"""
    if exchange.lower() == 'bybit':
        base = db_symbol[:-4]  # Remove 'USDT'
        return f"{base}/USDT:USDT"
    return db_symbol  # Binance uses format as-is

# Examples:
normalize_symbol_for_exchange('BTCUSDT', 'binance')  # 'BTCUSDT'
normalize_symbol_for_exchange('BTCUSDT', 'bybit')    # 'BTC/USDT:USDT'
```

#### Verdict: **Binance wins for simplicity**

---

### 3. OHLCV Data Availability

#### Binance Futures
```
Supported Timeframes:
1s, 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M

Max candles per request: 1000
Data retention: Indefinite (years of history)
Consistency: Excellent
```

#### Bybit Futures
```
Supported Timeframes:
1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M

Max candles per request: 1000
Data retention: Indefinite (years of history)
Consistency: Good

Notable: No 1s timeframe
```

#### Safe Choice
```python
# Use timeframes available on BOTH:
'1m', '5m', '15m', '30m', '1h'

# Avoid for compatibility:
'1s' (Binance only)
```

#### Verdict: **Tie** (both have good OHLCV data)

---

### 4. Open Interest Data

### 4.1 Current Open Interest
```python
# Both return same format:
{
    'symbol': 'BTCUSDT',
    'openInterest': 1234567890.50,  # USDT
    'timestamp': 1698234567890      # milliseconds
}

# Same interface for both:
oi = await exchange.fetch_open_interest('BTCUSDT')  # or 'BTC/USDT:USDT' for Bybit
```

**Availability:** Real-time, instant response
**Accuracy:** Real-time current value

### 4.2 Historical Open Interest
```
Binance Futures:
- Timeframe: 4h ONLY (not 1h)
- Data points: Up to 720 per request
- Retention: ~3 months
- Cost: 10 weight per request (expensive!)

Bybit Futures:
- Timeframe: 1h (better granularity!)
- Data points: Similar to Binance
- Retention: ~3 months
- Cost: Standard rate limit
```

#### Code Example
```python
from datetime import datetime, timezone, timedelta

# Binance: 4h data
since_ms = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
oi_history = await binance.fetch_open_interest_history(
    'BTCUSDT',
    '4h',  # Only option
    since=since_ms,
    limit=100
)

# Bybit: 1h data (better!)
oi_history = await bybit.fetch_open_interest_history(
    'BTC/USDT:USDT',
    '1h',  # Better granularity
    since=since_ms,
    limit=100
)
```

#### Verdict: **Bybit wins for OI history** (1h vs 4h)

---

### 5. Data Accuracy & Consistency

#### Binance
```
Strengths:
✓ Most reliable exchange
✓ Best API documentation
✓ Stable prices and data
✓ Lowest slippage

Weaknesses:
✗ Higher fees (maker 0.04%, taker 0.04%)
```

#### Bybit
```
Strengths:
✓ Good data quality
✓ Better OI history granularity (1h vs 4h)
✓ Slightly lower fees

Weaknesses:
✗ Tighter rate limits
✗ Less detailed documentation
```

#### Verdict: **Binance** (for consistency and API quality)

---

### 6. Practical Performance

### 6.1 Fetching 100 Days of 1h Data
```python
# 100 days × 24 hours = 2400 candles
# Max per request: 1000 → 3 requests needed

Binance:
- API calls: 3
- Weight cost: 3 × 1 = 3 weight
- Time: ~3 seconds
- Rate limit impact: 0.25% of 1200

Bybit:
- API calls: 3
- Rate limit impact: 2.5% of 120 (3.5× more expensive!)
- Time: ~3 seconds with delays
- Practical limit: ~35 symbols per minute max
```

### 6.2 Real-time Signal Processing
```python
# Process incoming signal:
1. Fetch current price (1 call)
2. Fetch current OI (1 call)
3. Fetch next hour's H/L (1 call)
4. Total: 3 calls

Binance: 3 weight (safe)
Bybit: 3/120 = 2.5% of rate limit

With 10 signals/minute:
Binance: 30 weight = 2.5% of 1200 ✓ Safe
Bybit: 30/120 = 25% of limit ⚠️ Getting tight

With 50 signals/minute:
Binance: 150 weight = 12.5% of 1200 ✓ Still OK
Bybit: 150/120 = 125% ✗ EXCEEDS LIMIT!
```

#### Verdict: **Binance** (for high-frequency processing)

---

### 7. Feature Support Matrix

| Feature | Binance | Bybit | Notes |
|---------|---------|-------|-------|
| `fetch_ohlcv` | ✓ | ✓ | Both excellent |
| `fetch_ticker` | ✓ | ✓ | Real-time |
| `fetch_open_interest` | ✓ | ✓ | Current value |
| `fetch_open_interest_history` | ✓ (4h) | ✓ (1h) | Different granularity |
| `fetch_trades` | ✓ | ✓ | For volume detail |
| `fetch_positions` | ✓ | ✓ | Requires auth |
| `create_order` | ✓ | ✓ | Requires auth |
| Symbol flexibility | ✓ | ✗ | Strict format on Bybit |

---

## Implementation Recommendation

### Best Strategy: Multi-Exchange Support

```python
# Use both exchanges' strengths:

# 1. For most signals → Use Binance (better rate limits)
if exchange_name == 'binance':
    # Fetch everything from Binance
    candles = await exchange.fetch_ohlcv(symbol, '1h', limit=100)
    oi = await exchange.fetch_open_interest(symbol)
    ticker = await exchange.fetch_ticker(symbol)

# 2. For OI analysis → Use Bybit (1h granularity)
if exchange_name == 'bybit' and need_oi_history:
    # Bybit has better 1h OI history
    oi_history = await exchange.fetch_open_interest_history(
        symbol, '1h', limit=168  # 7 days × 24h
    )

# 3. Fall back to Binance if Bybit rate limited
try:
    await bybit_exchange.fetch_ohlcv(symbol, '1h')
except ccxt.RateLimitExceeded:
    await binance_exchange.fetch_ohlcv(symbol, '1h')
```

---

## Decision Tree

```
START: Need to fetch historical data

├─ Need OHLCV (prices, volumes)?
│  └─ Use BINANCE (better rate limits)
│     └─ fetch_ohlcv(symbol, timeframe, limit=1000)
│
├─ Need current open interest?
│  └─ Use either exchange
│     └─ fetch_open_interest(symbol)
│
├─ Need historical open interest?
│  ├─ Binance: 4h intervals
│  └─ Bybit: 1h intervals ← Better granularity!
│
├─ High-frequency processing (>50 sig/min)?
│  └─ Use BINANCE (generous rate limits)
│
├─ Low-frequency processing (<10 sig/min)?
│  └─ Either exchange is fine
│     ├─ Binance: More reliable
│     └─ Bybit: More features
│
└─ Multi-exchange setup?
   └─ Use both:
      ├─ Primary: Binance
      └─ Fallback: Bybit
```

---

## Rate Limit Simulation

### Scenario: 30 signals per minute

```
Binance:
- 30 signals × 3 API calls = 90 API calls/min
- 90 calls × 1 weight = 90 weight/min
- Usage: 90/1200 = 7.5% of limit ✓ Comfortable

Bybit:
- 30 signals × 3 API calls = 90 API calls/min
- 90 calls × 1 request = 90 req/min
- Usage: 90/120 = 75% of limit ⚠️ Risky
- Remaining: Only 30 calls for other operations
```

**Conclusion:** Bybit is impractical for >20 signals/minute without premium tier.

---

## Cost Analysis

### API Call Costs (Weight/Request)

```
                  Binance    Bybit     (lower is better)
fetch_ohlcv       1          1         Tie
fetch_ticker      1          1         Tie
fetch_oi          1          1         Tie
fetch_oi_history  10         1         Bybit wins! ← Significant
fetch_trades      1          1         Tie
```

**Note:** Bybit's 1h open interest history is 10x cheaper than doing it manually with other methods.

---

## Conclusion

### Use Binance for:
- Real-time signal processing (>10 signals/minute)
- High-frequency data fetching
- OHLCV candles
- Primary trading signals
- Reliable baseline

### Use Bybit for:
- High-resolution open interest analysis (1h vs 4h)
- Lower-frequency processing (<10 signals/minute)
- Fallback/arbitrage analysis
- Optional advanced features

### Recommended Setup:
```python
# Main exchange for signals
primary = ExchangeManager('binance', config.exchanges['binance'])

# Optional: Secondary for OI analysis
secondary = ExchangeManager('bybit', config.exchanges['bybit'])

# Usage:
signal_data = await primary.fetch_ohlcv(symbol, '1h')  # Binance
oi_data = await secondary.fetch_open_interest_history(symbol, '1h')  # Bybit
```

---

## References

- Binance Futures API: https://binance-docs.github.io/apidocs/futures/en/
- Bybit V5 API: https://bybit-exchange.github.io/docs/v5/intro
- CCXT Library: https://github.com/ccxt/ccxt

