# Historical Data Fetching with CCXT - Documentation Index

## Quick Summary

This documentation set provides comprehensive guidance on fetching historical market data from Binance and Bybit Futures using the CCXT library (v4.5.12).

### What You Can Get

✓ **Historical prices** at specific timestamps (BTCUSDT, etc)
✓ **Open interest in USDT** (current and historical)
✓ **1h volume in USDT**
✓ **1h high/low** after signal timestamp
✓ **24h market statistics**

### Supported Exchanges

- **Binance Futures** (BTCUSDT format)
- **Bybit Futures Linear** (BTC/USDT:USDT format)

---

## Documentation Files

### 1. **CCXT_HISTORICAL_DATA_RESEARCH.md** - Deep Research
**When to read:** Understanding the underlying concepts

**Contents:**
- Complete feature comparison (Binance vs Bybit)
- Detailed code examples for each data type
- Data format specifications
- Rate limit details
- Limitations and edge cases
- Test scripts

**Key Sections:**
- Section 1: Available Methods & Capabilities
- Section 2: OHLCV Data Format
- Section 3: Code Examples (basic to advanced)
- Section 4: Open Interest Data
- Section 5: Binance vs Bybit Differences

---

### 2. **CCXT_API_REFERENCE.md** - API Documentation
**When to read:** Looking up method signatures and parameters

**Contents:**
- Method signatures with all parameters
- Return value formats
- Timeframe reference
- Common patterns with code
- Exchange-specific configurations
- Error handling guide
- Performance checklist

**Key Methods:**
- `fetch_ohlcv()` - Get OHLC candles
- `fetch_open_interest()` - Current open interest
- `fetch_open_interest_history()` - Historical OI
- `fetch_ticker()` - Current price & 24h stats
- `fetch_trades()` - Individual trades

---

### 3. **HISTORICAL_DATA_IMPLEMENTATION_GUIDE.md** - Practical Implementation
**When to read:** Actually implementing the features

**Contents:**
- Quick copy-paste solutions
- ExchangeManager method additions
- Real-world examples
- Common patterns (24h stats, OI analysis)
- Testing guide
- Troubleshooting section

**Key Methods to Add:**
- `fetch_ohlcv_volume_usdt()` - OHLCV with USDT volume
- `fetch_open_interest_usdt()` - Current OI in USDT
- `fetch_candle_at_timestamp()` - Get candle at specific time

---

## Start Here Based on Your Goal

### Goal: "Get price at signal timestamp"
1. Read: CCXT_API_REFERENCE.md → Section 1 (fetch_ohlcv)
2. Copy: HISTORICAL_DATA_IMPLEMENTATION_GUIDE.md → "Pattern 1"
3. Implement: Add `fetch_candle_at_timestamp()` to ExchangeManager

### Goal: "Get 1h volume in USDT"
1. Read: CCXT_HISTORICAL_DATA_RESEARCH.md → Section 3.2
2. Understand: Volume is returned in BASE ASSET, must multiply by price
3. Copy: HISTORICAL_DATA_IMPLEMENTATION_GUIDE.md → Quick reference section
4. Implement: Add `fetch_ohlcv_volume_usdt()` to ExchangeManager

### Goal: "Get open interest data"
1. Read: CCXT_API_REFERENCE.md → Section 2 & 3
2. Understand: Current OI available realtime, historical only 4h intervals
3. Copy: HISTORICAL_DATA_IMPLEMENTATION_GUIDE.md → "Pattern 3"
4. Implement: Add `fetch_open_interest_usdt()` to ExchangeManager

### Goal: "Compare Binance vs Bybit"
1. Read: CCXT_HISTORICAL_DATA_RESEARCH.md → Section 5
2. Reference: CCXT_API_REFERENCE.md → Exchange-Specific Details

### Goal: "Debug rate limit issues"
1. Read: CCXT_API_REFERENCE.md → Performance Checklist
2. Reference: CCXT_HISTORICAL_DATA_RESEARCH.md → Section 6 (Rate Limits)

---

## Critical Points - DON'T FORGET!

### 1. Volume Unit Conversion
```python
# WRONG - This is BASE ASSET volume (e.g., BTC):
volume = candle[5]

# RIGHT - Convert to USDT:
volume_usdt = candle[5] * candle[4]  # volume * close_price
```

### 2. Timestamp Conversion
```python
# WRONG - This treats milliseconds as seconds:
dt = datetime.fromtimestamp(ts_ms)

# RIGHT - Divide by 1000:
dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
```

### 3. Symbol Format
```python
# Binance: Use as-is
symbol = 'BTCUSDT'

# Bybit: Need to add slashes
symbol = 'BTC/USDT:USDT'

# Use ExchangeManager.find_exchange_symbol() for conversion!
```

### 4. Rate Limits
- Binance: 1200 weight/minute (generous)
- Bybit: 120 requests/minute (tight!)
- Use `exchange_manager.rate_limiter` to avoid errors
- `fetch_open_interest_history()` costs 10 weights on Binance

### 5. Timeframe Support
Both exchanges support `1m`, `5m`, `1h` - use these for compatibility
- Binance also has `1s`, `3m`, `30m`, `2h`, etc
- Bybit doesn't have `1s` or `3m`

---

## Quick Implementation Checklist

- [ ] Read CCXT_API_REFERENCE.md
- [ ] Understand the 3 critical points above
- [ ] Add `fetch_ohlcv_volume_usdt()` to ExchangeManager
- [ ] Add `fetch_open_interest_usdt()` to ExchangeManager
- [ ] Add `fetch_candle_at_timestamp()` to ExchangeManager
- [ ] Test with both Binance and Bybit
- [ ] Handle symbol format conversion
- [ ] Use rate_limiter for all calls
- [ ] Add error handling for network/rate limit errors

---

## Code Template - Getting Started

```python
# In core/exchange_manager.py

async def fetch_ohlcv_volume_usdt(self, symbol: str, timeframe: str = '1h', limit: int = 100):
    """Fetch OHLCV with volume in USDT"""
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

async def fetch_open_interest_usdt(self, symbol: str):
    """Fetch current open interest in USDT"""
    oi_data = await self.rate_limiter.execute_request(
        self.exchange.fetch_open_interest, symbol
    )
    return {
        'symbol': oi_data['symbol'],
        'open_interest_usdt': float(oi_data['openInterest']),
        'timestamp': datetime.fromtimestamp(oi_data['timestamp'] / 1000, tz=timezone.utc),
    }
```

---

## Testing Your Implementation

```python
#!/usr/bin/env python3
"""Minimal test for new methods"""

import asyncio
from core.exchange_manager import ExchangeManager
from config.settings import config
from datetime import datetime, timezone, timedelta

async def test():
    # Initialize Binance
    exchange = ExchangeManager('binance', config.exchanges['binance'])
    await exchange.initialize()

    symbol = 'BTCUSDT'

    # Test 1: Volume in USDT
    candles = await exchange.fetch_ohlcv_volume_usdt(symbol, '1h', limit=3)
    print("✓ fetch_ohlcv_volume_usdt works")
    for c in candles:
        print(f"  {c['timestamp']}: {c['volume_usdt']:,.0f} USDT")

    # Test 2: Open Interest
    oi = await exchange.fetch_open_interest_usdt(symbol)
    print(f"✓ fetch_open_interest_usdt works: {oi['open_interest_usdt']:,.0f} USDT")

    # Test 3: Candle at timestamp
    target = datetime.now(timezone.utc) - timedelta(hours=2)
    candle = await exchange.fetch_candle_at_timestamp(symbol, target)
    if candle:
        print(f"✓ fetch_candle_at_timestamp works: {candle['close']}")

    await exchange.close()

if __name__ == '__main__':
    asyncio.run(test())
```

---

## Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `InvalidSymbol` | Wrong symbol format | Use `find_exchange_symbol()` |
| Very small volume | Forgot to multiply by price | `volume_base * close_price` |
| Timestamp mismatch | Using seconds instead of ms | Divide by 1000 |
| Rate limited | Too many requests | Use rate_limiter, add delays |
| `openInterest: 0` | Symbol not on exchange | Check symbol availability |
| Symbol not found (Bybit) | Using Binance format | Convert to `BTC/USDT:USDT` |

---

## Next Steps

1. **Review** the three documentation files
2. **Implement** the helper methods in ExchangeManager
3. **Test** with both Binance and Bybit
4. **Integrate** into your signal processing pipeline
5. **Monitor** API usage and rate limits

---

## Key Files in Project

- Implementation location: `/core/exchange_manager.py`
- Config location: `/config/settings.py`
- Tests location: `/tests/unit/test_*.py`
- Current OHLCV usage: `/protection/stop_loss_manager.py`, `/protection/position_guard.py`

---

## Version Info

- **CCXT Version:** 4.5.12 (see requirements.txt)
- **Python:** 3.10+
- **Binance API:** Futures (USD-M Perpetuals)
- **Bybit API:** V5, Linear Perpetuals
- **Documentation Date:** 2025-10-28

---

## Further Reading

- CCXT Official Docs: https://docs.ccxt.com/
- Binance API: https://binance-docs.github.io/apidocs/futures/en/
- Bybit API: https://bybit-exchange.github.io/docs/v5/intro

