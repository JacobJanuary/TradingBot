# Binance Stop Loss Update Behavior

## Overview

Binance does NOT support atomic stop loss updates for STOP_MARKET orders.
The only way to update SL is via **cancel + create** approach.

## Implementation

File: `core/exchange_manager.py`
Method: `_binance_update_sl_optimized()`

### Update Sequence

```
1. Fetch all open orders for symbol
2. Find ALL STOP_MARKET orders with reduceOnly=True
3. Cancel ALL found SL orders (handles orphans)
4. Create new STOP_MARKET order with new stopPrice
```

### Race Condition Window

**Unprotected window:** Time between cancel completion and create completion

- **Typical duration:** 100-500ms
- **Alert threshold:** 500ms (configurable in config.trading.trailing_alert_if_unprotected_window_ms)
- **Risk:** If price hits old SL during window, position is unprotected

### Orphan Order Handling

**Problem:** Multiple rapid SL updates can create orphan orders:
- Update 1: Cancel order A, create order B
- Update 2: Cancel order B, create order C
- If update 1 cancel fails, both B and C exist → orphan

**Solution (as of 2025-10-15):** Find and cancel ALL SL orders before creating new one

**Code (lines 756-812):**
```python
# Find ALL existing SL orders
sl_orders = []
for order in orders:
    if (order_type == 'STOP_MARKET' and
        order_side == expected_side and
        reduce_only):
        sl_orders.append(order)

# Cancel ALL orders
if len(sl_orders) > 1:
    logger.warning(f"Found {len(sl_orders)} SL orders - orphan detected!")

for sl_order in sl_orders:
    await self.exchange.cancel_order(sl_order['id'], symbol)
```

## Testing

### Manual Test

1. Open position on Binance
2. Update SL 3 times rapidly (< 5 seconds between updates)
3. Check open orders: `exchange.fetch_open_orders(symbol)`
4. Expected: Exactly 1 STOP_MARKET order
5. If > 1 order: Orphan detected

### Automated Test

Run: `python tests/test_binance_sl_updates.py`

Expected output:
```
TEST 1: Updating SL to 50000.0...
✅ SL updated: binance_cancel_create_optimized, 342.15ms
   Cancelled 1 order(s)

TEST 2: Updating SL to 50100.0...
✅ SL updated: binance_cancel_create_optimized, 298.47ms
   Cancelled 1 order(s)

TEST 3: Updating SL to 50200.0...
✅ SL updated: binance_cancel_create_optimized, 315.82ms
   Cancelled 1 order(s)

VERIFICATION: Checking for orphan SL orders...
Found 1 SL order(s):
  - Order 12345678...: stopPrice=50200.0
✅ TEST PASSED: Exactly 1 SL order (no orphans)
```

## Comparison with Bybit

| Feature | Binance | Bybit |
|---------|---------|-------|
| Atomic Update | ❌ No | ✅ Yes |
| Method | Cancel + Create | trading-stop endpoint |
| Unprotected Window | 100-500ms | 0ms |
| Orphan Risk | Medium (mitigated) | None |
| Implementation | `_binance_update_sl_optimized()` | `_bybit_update_sl_atomic()` |

## Recommendations

1. **Prefer Bybit** for Trailing Stop when possible (truly atomic)
2. **Monitor unprotected window** duration on Binance
3. **Alert if > 500ms** (indicates exchange latency issues)
4. **Test orphan handling** regularly with rapid SL updates
5. **Consider rate limiting** to avoid rapid updates (already implemented: 60s min interval)

## Configuration

File: `config/settings.py`

```python
# Trailing Stop SL Update settings
trailing_min_update_interval_seconds: int = 60  # Min 60s between updates
trailing_min_improvement_percent: Decimal = Decimal('0.1')  # Min 0.1% improvement
trailing_alert_if_unprotected_window_ms: int = 500  # Alert if > 500ms
```

## Related Files

- `core/exchange_manager.py:739-835` - Binance implementation
- `core/exchange_manager.py:670-737` - Bybit implementation
- `protection/trailing_stop.py:590-646` - Rate limiting logic
- `tests/test_binance_sl_updates.py` - Integration test

## Changelog

**2025-10-15:** Fixed orphan order handling
- Changed from canceling FIRST SL order to canceling ALL SL orders
- Added warning if multiple orders detected
- Added per-order logging with stopPrice
- Continue canceling even if one cancel fails
