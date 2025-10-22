# CASE #2 & #3: Quick Analysis
## Position Not Found & Price Precision Errors

**Date**: 2025-10-22
**Status**: Related to CASE #1

---

## CASE #2: Positions "Not Found" After Opening

### Summary
4 positions (WAVESUSDT, FLRUSDT, CAMPUSDT, ESUSDT) reported as "not found" after order execution.

### Evidence
```
19:35:24 - ❌ Position WAVESUSDT not found after 10 attempts!
19:35:24 - ⚠️ ALERT: Open position without SL may exist on exchange!

19:35:36 - ❌ Position FLRUSDT not found after 10 attempts!
19:36:07 - ❌ Position CAMPUSDT not found after 10 attempts!
19:50:30 - ❌ Position ESUSDT not found after 10 attempts!
```

### Root Cause
**Position creation rollback due to SL placement failure**

From tracebacks:
```python
File: core/atomic_position_manager.py:397
AtomicPositionError: Failed to place stop-loss after 3 attempts:
    bybit price of WAVES/USDT must be greater than minimum price precision of 0.01

File: core/atomic_position_manager.py:330
AtomicPositionError: Position not found after order - order may have failed.
Order status: closed
```

### Analysis

**Scenario 1: SL Precision Error (WAVESUSDT, GIGAUSDT)**
1. Market order placed → Position opens
2. Try to set SL → **Price precision error**
3. SL placement fails 3 times
4. Atomic operation rolls back
5. Tries to close position
6. Position already closed by exchange (stop-out or immediate loss)
7. Reports "position not found"

**Scenario 2: Order Closed Immediately (FLRUSDT, CAMPUSDT, ESUSDT)**
1. Market order placed
2. Order fills but position closes IMMEDIATELY
   - Possible reasons:
     - Insufficient margin
     - Immediate stop-out due to volatility
     - Liquidation
     - Order filled at limit and hit SL instantly
3. Bot checks for position → "closed" status
4. Reports "position not found"

### Impact
- Signal execution failures
- Uncertainty about actual exchange state
- Possible orphaned orders
- Wasted gas/fees

### Fix Required
1. **Better error detection**:
   - Distinguish between "never opened" and "opened then closed"
   - Check order fill status
   - Query exchange history

2. **Handle precision errors BEFORE placing order**:
   - Validate SL price precision before order
   - Round to exchange requirements
   - Skip position if SL can't be set

3. **Improve rollback logic**:
   - Verify position actually exists before trying to close
   - Handle "already closed" gracefully
   - Log order fill details

---

## CASE #3: Price Precision Errors

### Summary
Multiple symbols rejected due to SL price below minimum precision.

### Evidence
```
WAVES:  "price must be greater than minimum price precision of 0.01"
GIGA:   "price must be greater than minimum price precision of 0.000001"
ALEO:   "price must be greater than minimum price precision of 0.0001"
```

### Root Cause Analysis

**Location**: `stop_loss_manager.py:341`

```python
sl_price_formatted = self.exchange.price_to_precision(symbol, stop_price)
```

**Problem**: Calculated SL price violates exchange minimum precision

**Example (WAVES)**:
```
Entry price:    1.00
SL percent:     2%
Calculated SL:  0.98
Min precision:  0.01
Result:         ✅ Valid (0.98 > 0.01)

BUT if price calculation has issue:
Calculated SL:  0.0098 (wrong calculation)
Min precision:  0.01
Result:         ❌ Invalid (0.0098 < 0.01)
```

### Connection to CASE #1

This is **downstream effect** of symbol mismatch bug!

**Scenario**:
1. Wrong symbol used → wrong price fetched
2. SL calculated from wrong price
3. Result: Invalid SL price that violates precision
4. OR: SL becomes very small number due to calculation error

**Example**:
```
If fetch_ticker returns price = 0 (error)
SL = 0 * 0.98 = 0
0 < 0.01 precision → REJECTED
```

### Fix Required

1. **Pre-validation** (before sending to exchange):
```python
def validate_sl_price(symbol: str, sl_price: float, exchange) -> bool:
    """Validate SL meets exchange requirements"""
    market = exchange.market(symbol)
    min_price = market['limits']['price']['min']

    if sl_price < min_price:
        logger.error(f"SL {sl_price} < minimum {min_price} for {symbol}")
        return False

    return True
```

2. **Fallback strategy**:
```python
if sl_price < min_precision:
    # Use minimum valid price
    sl_price = min_precision * 1.5  # Add buffer
    logger.warning(f"SL adjusted to minimum: {sl_price}")
```

3. **Skip position if SL impossible**:
```python
if not validate_sl_price(symbol, sl_price, exchange):
    logger.error(f"Cannot set valid SL for {symbol}. Skipping position.")
    # Don't open position if we can't protect it
    raise InvalidStopLossError()
```

---

## Common Thread: CASE #1 is the Root

All these issues stem from **CASE #1: Symbol Mismatch**:

```
Symbol Mismatch (CASE #1)
    ↓
Wrong Price Fetched
    ↓
    ├→ Invalid SL Calculation → Position without SL (CASE #1)
    ├→ Price Precision Errors (CASE #3)
    └→ Position Rollback → "Not Found" (CASE #2)
```

**Fix Priority**:
1. **CASE #1** (P0) - Fixes symbol mismatch
2. **CASE #3** (P1) - Adds precision validation as safety net
3. **CASE #2** (P1) - Improves rollback handling

---

## Testing Requirements

### For CASE #2
```python
# test_case_02_position_rollback.py

async def test_position_not_found_after_close():
    """Test rollback when position closes immediately"""
    # Mock: Order fills but position closes instantly
    # Verify: Bot handles gracefully
    # Verify: No false "position without SL" alerts
```

### For CASE #3
```python
# test_case_03_price_precision.py

def test_sl_precision_validation():
    """Test SL price meets minimum precision"""
    symbols = ['WAVESUSDT', 'GIGAUSDT', 'ALEOUSDT']

    for symbol in symbols:
        min_precision = get_min_precision(symbol)
        sl_price = calculate_sl(...)

        assert sl_price >= min_precision
```

---

## Quick Fixes Summary

### CASE #2: Position Not Found
```python
# atomic_position_manager.py

async def _verify_position_exists(self, symbol: str):
    """Check if position actually exists before rollback"""
    positions = await self.exchange.fetch_positions([symbol])

    for pos in positions:
        if pos['contracts'] > 0:
            return True

    # Position doesn't exist - nothing to rollback
    logger.info(f"Position {symbol} not found - may have closed immediately")
    return False
```

### CASE #3: Price Precision
```python
# stop_loss_manager.py

def _validate_price_precision(self, symbol: str, price: float) -> float:
    """Ensure price meets exchange minimum precision"""
    market = self.exchange.market(symbol)
    min_price = market['limits']['price']['min']

    if price < min_price:
        logger.error(
            f"Price {price} below minimum {min_price} for {symbol}. "
            f"Cannot set SL - skipping position."
        )
        raise PricePrecisionError(f"Price {price} < minimum {min_price}")

    return price
```

---

**Status**: Analysis complete, ready for fixes
**Next**: Implement fixes from CASE #1 first (root cause)
