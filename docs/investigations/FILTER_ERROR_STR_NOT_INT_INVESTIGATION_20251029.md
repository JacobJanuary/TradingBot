# FILTER ERROR INVESTIGATION: 'str' object cannot be interpreted as an integer
**Date**: 2025-10-29 07:15
**Error**: `'str' object cannot be interpreted as an integer`
**Context**: "Error applying new filters to 10000SATSUSDT"
**Status**: 🔍 INVESTIGATION IN PROGRESS

---

## EXECUTIVE SUMMARY

**Error Message**: "'str' object cannot be interpreted as an integer"
**Location**: `core/wave_signal_processor.py:499` (exception handler)
**Symbol**: 10000SATSUSDT
**When**: During filter application (OI, Volume, or Price Change filters)

**Hypothesis**: String value passed where integer expected in one of:
1. `limit` parameter in `fetch_ohlcv()`
2. Array indexing (`candle[index]` where index is string)
3. `range()` function with string argument
4. `int()` conversion of string field

---

## ERROR LOCATION

### Exception Handler (Line 498-500):
```python
except Exception as e:
    logger.warning(f"Error applying new filters to {symbol}: {e}")
    # Don't filter on error - graceful degradation
```

**Context**: This try-except wraps ALL three filters (lines 376-497):
- Filter 1: Open Interest >= 1M USDT
- Filter 2: 1h Volume >= 50k USDT
- Filter 3: Price Change <= 4%

**Problem**: We don't know WHICH filter failed!

---

## CODE ANALYSIS

### Filter Block Structure (Lines 375-500):

```python
if signal_timestamp_str and direction:
    try:
        # Parse timestamp
        signal_timestamp = datetime.fromisoformat(signal_timestamp_str.replace('+00', '+00:00'))

        # Filter 1: Open Interest
        if getattr(self.config, 'signal_filter_oi_enabled', True):
            oi_usdt = await self._fetch_open_interest_usdt(...)
            # ... check logic

        # Filter 2: 1h Volume
        if getattr(self.config, 'signal_filter_volume_enabled', True):
            volume_1h_usdt = await self._fetch_1h_volume_usdt(...)
            # ... check logic

        # Filter 3: Price Change
        if getattr(self.config, 'signal_filter_price_change_enabled', True):
            price_at_signal, price_5min_before = await self._fetch_price_5min_before(...)
            # ... check logic

    except Exception as e:
        logger.warning(f"Error applying new filters to {symbol}: {e}")  # ← HERE
```

---

## SUSPECT LOCATIONS

### Suspect #1: `_fetch_1h_volume_usdt` - Array Indexing

**File**: `core/wave_signal_processor.py:716-719`

```python
candle = ohlcv[0]
# [timestamp, open, high, low, close, volume]
base_volume = candle[5]  # ← SUSPECT: If candle is dict, this fails!
close_price = candle[4]  # ← SUSPECT: If candle is dict, this fails!
```

**Hypothesis**: CCXT returns candle as **dict** instead of **list** for some symbols/exchanges.

**Evidence**:
- Symbol "10000SATSUSDT" has unusual name (starts with digits)
- Some CCXT implementations return dicts: `{'timestamp': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}`
- Trying to do `candle[5]` on dict uses string key `5` → error!

**Probability**: HIGH (70%)

---

### Suspect #2: `_fetch_price_5min_before` - Same Issue

**File**: `core/wave_signal_processor.py:762-763, 781-782`

```python
closest_signal = min(ohlcv_signal, key=lambda x: abs(x[0] - ts_signal_ms))
price_at_signal = closest_signal[4]  # ← SUSPECT: If dict, this fails!

closest_before = min(ohlcv_before, key=lambda x: abs(x[0] - ts_5min_before_ms))
price_5min_before = closest_before[4]  # ← SUSPECT: If dict, this fails!
```

**Same Issue**: If CCXT returns dicts, indexing with integers fails.

**Probability**: HIGH (70%)

---

### Suspect #3: `limit` Parameter Type Error

**File**: Various `fetch_ohlcv()` calls

**Check**:
```python
# Line 710
limit=1  # ✅ Integer literal - OK

# Line 755
limit=10  # ✅ Integer literal - OK

# Line 775
limit=10  # ✅ Integer literal - OK
```

**Verdict**: All `limit` parameters are hardcoded integers - NOT THE PROBLEM.

**Probability**: LOW (5%)

---

### Suspect #4: `since` Parameter Type Error

**Check**:
```python
# Line 703
ts_ms = int(hour_start.timestamp() * 1000)  # ✅ Explicitly int()

# Line 750
ts_signal_ms = int(signal_timestamp.timestamp() * 1000)  # ✅ Explicitly int()

# Line 768
ts_5min_before_ms = int(ts_5min_before.timestamp() * 1000)  # ✅ Explicitly int()
```

**Verdict**: All `since` parameters explicitly converted to `int()` - NOT THE PROBLEM.

**Probability**: LOW (5%)

---

### Suspect #5: `find_exchange_symbol()` Returns Wrong Type

**File**: Calls to `exchange_manager.find_exchange_symbol(symbol)`

**Lines**:
- 707: `exchange_manager.find_exchange_symbol(symbol)`
- 747: `exchange_symbol = exchange_manager.find_exchange_symbol(symbol)`

**Check**: Does `find_exchange_symbol()` return string or something else?

**Expected**: Returns string (e.g., "10000SATS/USDT:USDT")

**Hypothesis**: For symbols starting with digits, might return unexpected type?

**Probability**: LOW (10%)

---

## ROOT CAUSE HYPOTHESIS

**MOST LIKELY**: CCXT returns OHLCV candles as **dicts** instead of **lists** for certain symbols/exchanges.

### Evidence Supporting This:

1. **Symbol Name**: "10000SATSUSDT" - starts with digits, unusual format
2. **Error Type**: "'str' object cannot be interpreted as an integer" - classic dict indexing error
3. **Code Pattern**: Multiple uses of `candle[4]`, `candle[5]` (numeric indexing)
4. **CCXT Behavior**: Some CCXT implementations return dicts for compatibility

### What Happens:

```python
# Expected (list):
candle = [1730188800000, 0.0001234, 0.0001250, 0.0001220, 0.0001240, 1234567.89]
close_price = candle[4]  # ✅ Works! → 0.0001240

# Actual (dict for some symbols):
candle = {
    'timestamp': 1730188800000,
    'open': 0.0001234,
    'high': 0.0001250,
    'low': 0.0001220,
    'close': 0.0001240,
    'volume': 1234567.89
}
close_price = candle[4]  # ❌ ERROR! Tries to use integer 4 as dict key
# Python error: "'str' object cannot be interpreted as an integer"
# Because dict keys are strings, but we're passing int
```

---

## TESTING HYPOTHESIS

### Test Script (DO NOT RUN YET - PLAN ONLY):

```python
"""
Test if CCXT returns dict vs list for 10000SATSUSDT
"""
import asyncio
import ccxt.async_support as ccxt
import os

async def test_ohlcv_format():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
    })

    try:
        # Test problematic symbol
        symbol = '10000SATS/USDT:USDT'

        ohlcv = await exchange.fetch_ohlcv(
            symbol,
            timeframe='1h',
            limit=1
        )

        print(f"OHLCV for {symbol}:")
        print(f"Type: {type(ohlcv)}")
        print(f"Length: {len(ohlcv)}")

        if ohlcv:
            candle = ohlcv[0]
            print(f"\nFirst candle type: {type(candle)}")
            print(f"First candle: {candle}")

            if isinstance(candle, list):
                print("\n✅ Candle is LIST (expected)")
                print(f"  close_price = candle[4] = {candle[4]}")
            elif isinstance(candle, dict):
                print("\n❌ Candle is DICT (problem!)")
                print(f"  Keys: {list(candle.keys())}")
                print(f"  close_price = candle['close'] = {candle.get('close')}")

                # Try numeric indexing (will fail)
                try:
                    value = candle[4]
                    print(f"  candle[4] works: {value}")
                except Exception as e:
                    print(f"  candle[4] FAILS: {e}")

    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(test_ohlcv_format())
```

---

## THE SOLUTION (PLAN ONLY - NO IMPLEMENTATION)

### Fix #1: Defensive OHLCV Parsing

**Location**: `_fetch_1h_volume_usdt` (lines 716-719)

**Current Code (BROKEN)**:
```python
candle = ohlcv[0]
# [timestamp, open, high, low, close, volume]
base_volume = candle[5]
close_price = candle[4]
```

**Fixed Code (DEFENSIVE)**:
```python
candle = ohlcv[0]

# Defensive: handle both list and dict formats
if isinstance(candle, dict):
    # Dict format (some CCXT implementations)
    close_price = candle.get('close', 0)
    base_volume = candle.get('volume', 0)
elif isinstance(candle, list):
    # List format (standard)
    # [timestamp, open, high, low, close, volume]
    close_price = candle[4]
    base_volume = candle[5]
else:
    logger.warning(f"Unexpected candle format for {symbol}: {type(candle)}")
    return None
```

---

### Fix #2: Same for `_fetch_price_5min_before`

**Location**: Lines 762-763, 781-782

**Current Code (BROKEN)**:
```python
closest_signal = min(ohlcv_signal, key=lambda x: abs(x[0] - ts_signal_ms))
price_at_signal = closest_signal[4]  # close price

closest_before = min(ohlcv_before, key=lambda x: abs(x[0] - ts_5min_before_ms))
price_5min_before = closest_before[4]  # close price
```

**Fixed Code (DEFENSIVE)**:
```python
# Helper function for safe candle access
def get_candle_field(candle, field_name, list_index):
    """
    Safely extract field from candle (handles both list and dict)

    Args:
        candle: OHLCV candle (list or dict)
        field_name: Field name if dict (e.g., 'close')
        list_index: Index if list (e.g., 4 for close)

    Returns:
        Field value or None
    """
    if isinstance(candle, dict):
        return candle.get(field_name)
    elif isinstance(candle, list) and len(candle) > list_index:
        return candle[list_index]
    return None

# Find closest candle (handle both dict and list for timestamp)
def get_timestamp(candle):
    if isinstance(candle, dict):
        return candle.get('timestamp', 0)
    elif isinstance(candle, list):
        return candle[0]
    return 0

closest_signal = min(ohlcv_signal, key=lambda x: abs(get_timestamp(x) - ts_signal_ms))
price_at_signal = get_candle_field(closest_signal, 'close', 4)

closest_before = min(ohlcv_before, key=lambda x: abs(get_timestamp(x) - ts_5min_before_ms))
price_5min_before = get_candle_field(closest_before, 'close', 4)
```

---

### Fix #3: Better Error Logging

**Location**: Line 499

**Current Code (NO CONTEXT)**:
```python
except Exception as e:
    logger.warning(f"Error applying new filters to {symbol}: {e}")
    # Don't filter on error - graceful degradation
```

**Fixed Code (WITH CONTEXT)**:
```python
except Exception as e:
    logger.error(
        f"❌ Error applying new filters to {symbol}:\n"
        f"  Exception: {type(e).__name__}\n"
        f"  Message: {str(e)}\n"
        f"  Exchange: {exchange}\n"
        f"  Direction: {direction}\n"
        f"  Timestamp: {signal_timestamp_str}",
        exc_info=True  # Include full traceback
    )
    # Don't filter on error - graceful degradation
```

**Why**: Helps identify WHICH filter failed and with WHAT data.

---

### Fix #4: Split Try-Except Per Filter

**Current**: One try-except wraps ALL 3 filters → can't tell which failed

**Better**: Separate exception handling per filter:

```python
# Filter 1: Open Interest
try:
    if getattr(self.config, 'signal_filter_oi_enabled', True):
        oi_usdt = await self._fetch_open_interest_usdt(...)
        if oi_usdt is not None and oi_usdt < min_oi:
            # ... filter logic
except Exception as e:
    logger.warning(f"Filter 1 (OI) failed for {symbol}: {e}")
    # Continue to next filter

# Filter 2: 1h Volume
try:
    if getattr(self.config, 'signal_filter_volume_enabled', True):
        volume_1h_usdt = await self._fetch_1h_volume_usdt(...)
        # ... filter logic
except Exception as e:
    logger.warning(f"Filter 2 (Volume) failed for {symbol}: {e}")
    # Continue to next filter

# Filter 3: Price Change
try:
    if getattr(self.config, 'signal_filter_price_change_enabled', True):
        price_at_signal, price_5min_before = await self._fetch_price_5min_before(...)
        # ... filter logic
except Exception as e:
    logger.warning(f"Filter 3 (Price Change) failed for {symbol}: {e}")
    # Continue
```

**Benefit**: Clear identification of which filter fails.

---

## IMPLEMENTATION PLAN (DETAILED)

### Phase 1: Investigation (DO THIS FIRST - NO CODE CHANGES)

**Step 1.1**: Check git history for filter additions
```bash
git log --since="7 days ago" -p -- core/wave_signal_processor.py | grep -A 10 -B 10 "fetch_ohlcv"
```

**Step 1.2**: Check config values
```bash
grep -E "signal_filter.*enabled|signal_min_" config/settings.py
```

**Step 1.3**: Check error frequency
```bash
grep "Error applying new filters" logs/*.log | wc -l
grep "Error applying new filters" logs/*.log | grep -o "to [A-Z0-9]*USDT" | sort | uniq -c
```

**Step 1.4**: Run test script (AFTER user approval)
```bash
python tests/manual/test_ohlcv_format_10000SATS.py
```

### Phase 2: Implement Defensive Fixes (AFTER CONFIRMATION)

**Priority 1**: Fix `_fetch_1h_volume_usdt` (lines 716-719)
- Add isinstance() checks
- Handle both list and dict formats
- Add logging for unexpected formats

**Priority 2**: Fix `_fetch_price_5min_before` (lines 762-763, 781-782)
- Add helper function for safe access
- Handle both formats in lambda functions
- Add logging

**Priority 3**: Improve error logging (line 499)
- Add exception details
- Add context (exchange, direction, timestamp)
- Add full traceback (exc_info=True)

**Priority 4**: Split exception handling (lines 376-500)
- Separate try-except per filter
- Clear filter identification in logs
- Independent fallback per filter

### Phase 3: Testing

**Test 1**: Unit test for dict vs list handling
```python
def test_ohlcv_dict_format():
    """Test that _fetch_1h_volume_usdt handles dict candles"""
    # Mock exchange_manager to return dict format
    # Call _fetch_1h_volume_usdt
    # Assert: No exception, correct volume returned
```

**Test 2**: Integration test with 10000SATSUSDT
```python
async def test_filter_10000SATSUSDT():
    """Test filters work with problematic symbol"""
    # Create signal for 10000SATSUSDT
    # Run through filter pipeline
    # Assert: No "'str' object cannot be interpreted as an integer" error
```

**Test 3**: Verify all symbols
```bash
# Check if error fixed for all symbols
grep "Error applying new filters" logs/bot.log
# Should return NO results after fix
```

### Phase 4: Deployment

**Step 4.1**: Code review (3x)
- Logic correctness
- No regressions
- All edge cases handled

**Step 4.2**: Syntax validation
```bash
python -m py_compile core/wave_signal_processor.py
```

**Step 4.3**: Git commit
```bash
git add core/wave_signal_processor.py
git commit -m "fix(filters): handle CCXT dict format for OHLCV candles"
```

**Step 4.4**: Monitor next wave
- Check for error disappearance
- Verify filters still work
- Check no symbols incorrectly filtered

---

## RISK ANALYSIS

### Risks of Current Bug:

1. **Filter Bypass**: Filters silently fail → risky signals not filtered
2. **Hidden Failures**: No visibility into which filter/symbol fails
3. **Symbol-Specific**: May affect multiple symbols starting with digits
4. **Data Quality**: Bad data propagates to position opening

### Risks of Fix:

1. **Format Assumption**: Assumes dicts have 'close', 'volume' keys
2. **Performance**: `isinstance()` checks add minor overhead
3. **Testing**: Need to test with both list and dict formats
4. **Regression**: Could break if CCXT behavior changes

### Mitigation:

1. **Defensive Coding**: Handle both formats explicitly
2. **Logging**: Log unexpected formats for monitoring
3. **Fallback**: Return None on unknown format (graceful degradation)
4. **Testing**: Unit tests for both formats

---

## ALTERNATIVE SOLUTIONS

### Alternative 1: Force CCXT to Return Lists

**Approach**: Configure CCXT to always return list format

**Pros**: Centralized fix, no code changes needed
**Cons**: May not be possible, CCXT behavior varies by exchange

**Verdict**: NOT RECOMMENDED (not under our control)

---

### Alternative 2: Pre-convert All OHLCV to Standard Format

**Approach**: Create wrapper function that normalizes OHLCV format

```python
def normalize_ohlcv(ohlcv_data):
    """Convert CCXT OHLCV to standard list format"""
    result = []
    for candle in ohlcv_data:
        if isinstance(candle, dict):
            result.append([
                candle.get('timestamp', 0),
                candle.get('open', 0),
                candle.get('high', 0),
                candle.get('low', 0),
                candle.get('close', 0),
                candle.get('volume', 0)
            ])
        else:
            result.append(candle)
    return result
```

**Pros**: Single point of conversion, consistent format everywhere
**Cons**: Extra processing, need to wrap ALL fetch_ohlcv calls

**Verdict**: GOOD ALTERNATIVE (consider for Phase 2)

---

### Alternative 3: Use CCXT's Built-in Field Access

**Approach**: Use CCXT's standardized field names

```python
# Instead of:
close_price = candle[4]

# Use:
close_price = candle['close'] if isinstance(candle, dict) else candle[4]
```

**Pros**: Works with both formats
**Cons**: More verbose, need to check everywhere

**Verdict**: RECOMMENDED (this is essentially Fix #1)

---

## MONITORING & ALERTING

### Metrics to Track:

1. **Filter Error Rate**: Count of "Error applying new filters"
2. **Symbol-Specific Failures**: Which symbols trigger error
3. **Filter Success Rate**: % of signals that pass all filters
4. **OHLCV Format**: Log dict vs list frequency

### Alert Conditions:

1. ⚠️ Filter error rate > 1% of signals
2. ⚠️ Same symbol fails filters repeatedly
3. 🔴 ALL filters fail for a wave (critical)

---

## SUCCESS METRICS

Fix is successful if:

1. ✅ NO "Error applying new filters" errors in logs
2. ✅ 10000SATSUSDT filters work correctly
3. ✅ All symbols with digits in name work
4. ✅ Filter logic unchanged (same filtering behavior)
5. ✅ No performance degradation
6. ✅ Clear error logs if new format encountered

---

## NEXT STEPS

### Immediate (Investigation Phase):

1. [ ] Get user approval for investigation
2. [ ] Check git history for filter addition
3. [ ] Check error frequency in logs
4. [ ] Create test script for OHLCV format
5. [ ] Run test script on problematic symbol
6. [ ] Confirm hypothesis (dict vs list)

### After Confirmation (Implementation Phase):

1. [ ] Implement Fix #1 (_fetch_1h_volume_usdt)
2. [ ] Implement Fix #2 (_fetch_price_5min_before)
3. [ ] Implement Fix #3 (error logging)
4. [ ] Implement Fix #4 (split exception handling)
5. [ ] Code review 3x
6. [ ] Syntax validation
7. [ ] Unit tests
8. [ ] Integration tests
9. [ ] Git commit
10. [ ] Monitor next wave

---

## CONCLUSION

**Root Cause (Hypothesis)**: CCXT returns OHLCV candles as dicts for certain symbols (e.g., 10000SATSUSDT), code expects lists

**Impact**: HIGH - Filters fail silently, risky signals not filtered

**Fix Complexity**: LOW - Add isinstance() checks in 2 methods

**Confidence**: 70% - Need to confirm with test script

**Ready for Investigation**: ✅ YES (plan complete, waiting user approval)

**Ready for Implementation**: ❌ NO (need to confirm hypothesis first)

---

**STATUS**: 🔍 INVESTIGATION PLAN COMPLETE
**NEXT**: Get user approval for test script execution

---

END OF INVESTIGATION REPORT
