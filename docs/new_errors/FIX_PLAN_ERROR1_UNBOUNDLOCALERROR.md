# FIX PLAN: UnboundLocalError in Trailing Stop

## DATE: 2025-10-26
## PRIORITY: 🔴 HIGH (Fix Immediately)
## STATUS: Ready for Implementation

---

## PROBLEM SUMMARY

**Error:** `cannot access local variable 'profit_percent' where it is not associated with a value`

**File:** `protection/trailing_stop.py`
**Lines:** 440-463
**Function:** `update_price()`

**Frequency:** 4 occurrences in 1 hour
**Severity:** HIGH (crashes trailing stop callbacks, disrupts peak save logging)

---

## ROOT CAUSE

Variable `profit_percent` is used on line 455 **BEFORE** it's defined on line 463.

**Code Flow:**
```python
# Line 440: Start of if block
if peak_updated and ts.state == TrailingStopState.ACTIVE:
    # ...
    if should_save:
        # ...
        logger.info(
            f"profit: {profit_percent:.2f}% | "  # ← Line 455: ERROR!
        )

# Line 463: profit_percent defined HERE (too late!)
profit_percent = self._calculate_profit_percent(ts)
```

**Trigger Condition:**
- Trailing stop is ACTIVE
- Peak price updated (highest for long, lowest for short)
- `should_save == True` (peak save threshold met)

---

## SOLUTION

### Variant A: MINIMAL FIX (RECOMMENDED)

Move `profit_percent` calculation to line 440 (before if block).

#### Changes Required

**File:** `protection/trailing_stop.py`

**Line 440-466** - Current Code:
```python
# NEW: Save peak to database if needed (only for ACTIVE TS)
if peak_updated and ts.state == TrailingStopState.ACTIVE:
    current_peak = ts.highest_price if ts.side == 'long' else ts.lowest_price
    should_save, skip_reason = self._should_save_peak(ts, current_peak)

    if should_save:
        # Update tracking fields BEFORE saving
        ts.last_peak_save_time = datetime.now()
        ts.last_saved_peak_price = current_peak

        # Save to database
        await self._save_state(ts)

        # trailing_stop.py:465 - изменить с debug на info
        logger.info(  # было: logger.debug
            f"[TS] {symbol} @ {ts.current_price:.4f} | "
            f"profit: {profit_percent:.2f}% | "
            f"activation: {ts.activation_price:.4f} | "
            f"state: {ts.state.name}"
        )
    else:
        logger.debug(f"⏭️  {symbol}: Peak save SKIPPED - {skip_reason}")

# Calculate current profit
profit_percent = self._calculate_profit_percent(ts)
if profit_percent > ts.highest_profit_percent:
    ts.highest_profit_percent = profit_percent
```

**Line 440-466** - Fixed Code:
```python
# CRITICAL FIX: Calculate profit_percent BEFORE using it in logging
profit_percent = self._calculate_profit_percent(ts)

# Update highest profit if needed
if profit_percent > ts.highest_profit_percent:
    ts.highest_profit_percent = profit_percent

# NEW: Save peak to database if needed (only for ACTIVE TS)
if peak_updated and ts.state == TrailingStopState.ACTIVE:
    current_peak = ts.highest_price if ts.side == 'long' else ts.lowest_price
    should_save, skip_reason = self._should_save_peak(ts, current_peak)

    if should_save:
        # Update tracking fields BEFORE saving
        ts.last_peak_save_time = datetime.now()
        ts.last_saved_peak_price = current_peak

        # Save to database
        await self._save_state(ts)

        # trailing_stop.py:465 - изменить с debug на info
        logger.info(  # было: logger.debug
            f"[TS] {symbol} @ {ts.current_price:.4f} | "
            f"profit: {profit_percent:.2f}% | "  # ✅ NOW DEFINED!
            f"activation: {ts.activation_price:.4f} | "
            f"state: {ts.state.name}"
        )
    else:
        logger.debug(f"⏭️  {symbol}: Peak save SKIPPED - {skip_reason}")
```

**Summary of Changes:**
1. Move lines 463-465 to line 440 (before if block)
2. Remove duplicate calculation
3. Keep rest of logic identical

**Lines Changed:** 3 lines moved
**New Lines Added:** 0
**Risk Level:** VERY LOW

---

## TESTING PLAN

### Unit Test

**Create:** `tests/unit/test_trailing_stop_profit_percent_fix.py`

```python
"""
Unit test for profit_percent UnboundLocalError fix
"""
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from protection.trailing_stop import SmartTrailingStopManager, TrailingStopInstance, TrailingStopState


@pytest.mark.asyncio
async def test_profit_percent_available_in_peak_save_logging():
    """
    Test that profit_percent is calculated before being used in logging

    Reproduces the UnboundLocalError bug scenario:
    - Trailing stop is ACTIVE
    - Peak is updated
    - should_save returns True
    - Logging uses profit_percent
    """

    # Setup
    config = MagicMock()
    config.activation_percent = Decimal('2')
    config.callback_percent = Decimal('0.5')

    repository = AsyncMock()
    event_router = MagicMock()

    manager = SmartTrailingStopManager(
        exchange_name='binance',
        config=config,
        repository=repository,
        event_router=event_router
    )

    # Create trailing stop instance in ACTIVE state
    ts = TrailingStopInstance(
        symbol='TESTUSDT',
        entry_price=Decimal('100'),
        current_price=Decimal('102'),  # 2% profit
        highest_price=Decimal('102'),
        lowest_price=Decimal('100'),
        state=TrailingStopState.ACTIVE,
        activation_price=Decimal('102'),
        current_stop_price=Decimal('101'),
        stop_order_id='test_order_123',
        created_at=datetime.now(),
        activated_at=datetime.now(),
        highest_profit_percent=Decimal('0'),
        update_count=0,
        side='long',
        quantity=Decimal('10')
    )

    # Add to manager
    manager.positions['TESTUSDT'] = ts

    # Mock _should_save_peak to return True (trigger the logging path)
    with patch.object(manager, '_should_save_peak', return_value=(True, None)):
        # Mock _save_state to avoid DB calls
        with patch.object(manager, '_save_state', new=AsyncMock()):
            # This should NOT raise UnboundLocalError
            result = await manager.update_price('TESTUSDT', 103.0)

    # Verify profit_percent was calculated
    assert ts.highest_profit_percent > Decimal('0')
    assert ts.highest_profit_percent == Decimal('3')  # (103-100)/100 * 100 = 3%

    # Verify peak was updated
    assert ts.highest_price == Decimal('103')


@pytest.mark.asyncio
async def test_profit_percent_calculated_even_when_peak_not_saved():
    """
    Test that profit_percent is always calculated, even when peak save is skipped
    """

    config = MagicMock()
    config.activation_percent = Decimal('2')
    config.callback_percent = Decimal('0.5')

    repository = AsyncMock()
    event_router = MagicMock()

    manager = SmartTrailingStopManager(
        exchange_name='binance',
        config=config,
        repository=repository,
        event_router=event_router
    )

    ts = TrailingStopInstance(
        symbol='TESTUSDT',
        entry_price=Decimal('100'),
        current_price=Decimal('101'),
        highest_price=Decimal('101'),
        lowest_price=Decimal('100'),
        state=TrailingStopState.ACTIVE,
        activation_price=Decimal('102'),
        current_stop_price=Decimal('100.5'),
        stop_order_id='test_order_123',
        created_at=datetime.now(),
        activated_at=datetime.now(),
        highest_profit_percent=Decimal('0'),
        update_count=0,
        side='long',
        quantity=Decimal('10')
    )

    manager.positions['TESTUSDT'] = ts

    # Mock _should_save_peak to return False (skip save path)
    with patch.object(manager, '_should_save_peak', return_value=(False, 'test skip reason')):
        result = await manager.update_price('TESTUSDT', 102.0)

    # Verify profit_percent was still calculated
    assert ts.highest_profit_percent == Decimal('2')  # (102-100)/100 * 100 = 2%
```

**Run:**
```bash
python -m pytest tests/unit/test_trailing_stop_profit_percent_fix.py -v
```

**Expected:** All tests PASS

---

### Integration Test

**Manual Test Procedure:**

1. **Start bot with fix deployed**
   ```bash
   python main.py --mode production > logs/trading_bot.log 2>&1 &
   ```

2. **Wait for trailing stop to activate**
   - Monitor logs for trailing stop activation
   - Wait for peak update

3. **Monitor logs for error**
   ```bash
   tail -f logs/trading_bot.log | grep -E "(profit_percent|UnboundLocalError|Error in trailing_stop callback)"
   ```

4. **Verify no UnboundLocalError occurs**
   - Should see normal peak save logging
   - Should NOT see "cannot access local variable 'profit_percent'"

5. **Check peak save logging works**
   ```bash
   grep "Peak save" logs/trading_bot.log | tail -10
   ```

---

## DEPLOYMENT PLAN

### Step 1: Code Review

**Review changes:**
```bash
# Show diff of changes
git diff protection/trailing_stop.py
```

**Expected:** Only lines 440-466 modified (moved profit_percent calculation)

### Step 2: Syntax Check

```bash
python3 -m py_compile protection/trailing_stop.py
```

**Expected:** No errors

### Step 3: Unit Tests

```bash
python -m pytest tests/unit/test_trailing_stop_profit_percent_fix.py -v
```

**Expected:** All tests PASS

### Step 4: Git Commit

```bash
git add protection/trailing_stop.py tests/unit/test_trailing_stop_profit_percent_fix.py
git commit -m "fix(trailing-stop): Calculate profit_percent before using in logging

PROBLEM:
- UnboundLocalError when logging peak save
- profit_percent used on line 455 but defined on line 463
- Occurred 4 times in 1 hour for BSUUSDT, SQDUSDT, OPENUSDT

ROOT CAUSE:
- Variable used before assignment in peak save logging path
- Only triggered when: peak_updated=True AND state=ACTIVE AND should_save=True

SOLUTION:
- Move profit_percent calculation from line 463 to line 440 (before if block)
- Ensures variable is defined before being used in logging
- No logic changes, just reordering

IMPACT:
- Fixes: UnboundLocalError in trailing stop callbacks
- Risk: VERY LOW (only moved variable definition earlier)
- Tested: Unit tests for both save and skip paths

FIXES: UnboundLocalError in websocket.unified_price_monitor callback
"
```

### Step 5: Deploy (Restart Bot)

```bash
# Check current bot process
ps aux | grep "python.*main.py.*production"

# Stop bot
kill <PID>

# Start bot with fix
python main.py --mode production > logs/trading_bot.log 2>&1 &

# Verify startup
tail -f logs/trading_bot.log | head -100
```

### Step 6: Monitor

**Monitor for 1 hour:**
```bash
# Watch for errors
tail -f logs/trading_bot.log | grep -E "(ERROR|profit_percent|UnboundLocalError)"

# Watch for peak saves (should work now)
tail -f logs/trading_bot.log | grep "Peak save"
```

**Success Criteria:**
- ✅ No UnboundLocalError in logs
- ✅ Peak save logging works correctly
- ✅ Trailing stops continue working normally
- ✅ profit_percent appears in peak save logs

---

## ROLLBACK PLAN

If fix causes issues:

### Step 1: Revert Git

```bash
git log --oneline | head -5  # Find commit hash
git revert <commit-hash>
```

### Step 2: Restart Bot

```bash
kill <PID>
python main.py --mode production > logs/trading_bot.log 2>&1 &
```

### Step 3: Investigate

- Review test failures
- Check error logs
- Update fix plan

---

## SUCCESS CRITERIA

### ✅ Fix Successful If:

1. Syntax check passes
2. Unit tests pass (both scenarios)
3. Bot starts without errors
4. No UnboundLocalError in logs for 1 hour
5. Peak save logging shows profit_percent correctly
6. Trailing stops continue working normally

### ❌ Rollback If:

1. Unit tests fail
2. New errors appear
3. Trailing stop behavior changes unexpectedly
4. Performance degradation observed

---

## ESTIMATED TIME

- **Code changes:** 2 minutes
- **Unit tests:** 10 minutes
- **Testing:** 5 minutes
- **Commit & deploy:** 3 minutes
- **Monitoring:** 60 minutes

**Total:** ~80 minutes (including monitoring)

---

## NOTES

- This is a **VERY SAFE** fix (just moving variable definition)
- No logic changes
- No refactoring
- Follows GOLDEN RULE: "If it ain't broke, don't fix it"
- Only fixes the specific bug

**Ready for implementation:** ✅ YES
