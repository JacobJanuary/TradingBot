# 🔴 КРИТИЧЕСКИЙ БАГ: TS Callback Percent = 0 при активации

**Date**: 2025-10-28 07:18
**Severity**: 🔴 **CRITICAL** - SL устанавливается равным текущей цене!
**Impact**: Trailing Stop НЕ РАБОТАЕТ - нет защиты от отката цены

---

## ⚡ EXECUTIVE SUMMARY

**Проблема**: При активации Trailing Stop, SL устанавливается равным текущей цене вместо того чтобы быть ниже на callback_percent

**Симптомы**:
```
HNTUSDT:
  Current Price: 2.304
  Proposed SL:   2.304  ← РАВНЫ! Должен быть ниже на 0.5%
  Callback %:    0.0    ← НОЛЬ вместо 0.5!
```

**Ожидаемое поведение**:
```
SL = highest_price * (1 - callback_percent / 100)
SL = 2.304 * (1 - 0.5 / 100)
SL = 2.304 * 0.995
SL = 2.29248
```

**Фактическое поведение**:
```
SL = highest_price * (1 - 0 / 100)
SL = 2.304 * 1.0
SL = 2.304  ← WRONG!
```

**Результат**: SL = текущая цена → позиция НЕ защищена от отката!

---

## 🔬 FORENSIC ANALYSIS

### Logs Evidence

```
2025-10-28 06:47:46 - ERROR - 🔴 HNTUSDT: SL VALIDATION FAILED
  Side:          long
  Current Price: 2.30400000
  Proposed SL:   2.30400000  ← PROBLEM!
  Error:         LONG position requires SL < current_price

2025-10-28 06:47:46 - INFO - ✅ HNTUSDT: TS ACTIVATED
  side=long, price=2.30400000, sl=2.30400000  ← SL = price!

2025-10-28 06:47:46 - trailing_stop_activated:
  'distance_percent': 0.0  ← ZERO!
```

### Database Investigation

**Position table** (`monitoring.positions`):
```sql
SELECT trailing_activation_percent, trailing_callback_percent
FROM monitoring.positions
WHERE symbol = 'HNTUSDT';

Result:
  trailing_activation_percent: 2.0000  ✅ CORRECT
  trailing_callback_percent:   0.5000  ✅ CORRECT
```

**Params table** (`monitoring.params`):
```sql
SELECT trailing_distance_filter
FROM monitoring.params
WHERE exchange_id = 2;

Result:
  trailing_distance_filter: 0.5000%  ✅ CORRECT
```

**TS State table** (`monitoring.trailing_stop_state`):
```sql
SELECT activation_percent, callback_percent
FROM monitoring.trailing_stop_state
WHERE symbol = 'HNTUSDT';

Result:
  activation_percent: 0.0000  ❌ WRONG! (Should be 2.0)
  callback_percent:   0.0000  ❌ WRONG! (Should be 0.5)
```

---

## 🎯 ROOT CAUSE

### Problem Location

**File**: `protection/trailing_stop.py`

**Function**: `_restore_state()` (lines 373-394)

### The Bug

При восстановлении Trailing Stop из БД после рестарта, `activation_percent` и `callback_percent` **НЕ передаются** в конструктор `TrailingStopInstance`!

**Code Analysis**:

```python
# Line 373-394: _restore_state()

ts = TrailingStopInstance(
    symbol=state_data['symbol'],
    entry_price=Decimal(str(state_data['entry_price'])),
    current_price=Decimal(str(state_data['entry_price'])),
    highest_price=...,
    lowest_price=...,
    state=...,
    activation_price=...,
    current_stop_price=...,
    stop_order_id=...,
    created_at=...,
    activated_at=...,
    highest_profit_percent=...,
    update_count=...,
    side=side_value,
    quantity=Decimal(str(state_data['quantity']))
    # ← MISSING: activation_percent=...
    # ← MISSING: callback_percent=...
)
```

**TrailingStopInstance defaults**:
```python
# Line 101-102
activation_percent: Decimal = Decimal('0')  # ← Default = 0!
callback_percent: Decimal = Decimal('0')    # ← Default = 0!
```

**Result**: При восстановлении, activation_percent и callback_percent остаются = 0!

---

## 📊 TIMELINE OF EVENTS

### Step 1: Position Created (01:36:05)
```
- Position created with correct params from DB
- trailing_activation_percent: 2.0%
- trailing_callback_percent: 0.5%
```

### Step 2: TS Created (01:36:12)
```python
# create_trailing_stop() called
activation_percent = position_params['trailing_activation_percent']  # 2.0
callback_percent = position_params['trailing_callback_percent']      # 0.5

ts = TrailingStopInstance(
    ...
    activation_percent=activation_percent,  # ← CORRECT: 2.0
    callback_percent=callback_percent       # ← CORRECT: 0.5
)
```

### Step 3: TS First Save to DB (01:36:12)
```python
# _save_state() called
state_data = {
    'activation_percent': float(ts.activation_percent),  # 2.0
    'callback_percent': float(ts.callback_percent),      # 0.5
    ...
}
```

**БД получает правильные значения! ✅**

### Step 4: Bot Restart (Time Unknown)

Bot restarted → TS restored from DB

### Step 5: TS Restore from DB (After Restart)
```python
# _restore_state() called
# state_data from DB contains:
#   activation_percent: 2.0  ← Available in DB!
#   callback_percent: 0.5    ← Available in DB!

ts = TrailingStopInstance(
    ...
    # BUG: activation_percent NOT passed!
    # BUG: callback_percent NOT passed!
)

# Result: ts.activation_percent = 0 (default)
#         ts.callback_percent = 0 (default)
```

### Step 6: TS Re-saved to DB (After Restore)
```python
# _save_state() called again
state_data = {
    'activation_percent': float(ts.activation_percent),  # 0 now!
    'callback_percent': float(ts.callback_percent),      # 0 now!
    ...
}
```

**БД перезаписана с НУЛЯМИ! ❌**

### Step 7: TS Activation (06:47:46)
```python
# Price reached activation threshold
# Calculate SL with callback_percent = 0

if side == 'long':
    new_sl = highest_price * (1 - callback_percent / 100)
    new_sl = 2.304 * (1 - 0 / 100)
    new_sl = 2.304  ← WRONG!
```

**SL validation fails**: SL >= current_price for long position!

---

## 🐛 THE BUG IN DETAIL

### Where callback_percent is Used

**File**: `protection/trailing_stop.py`

**Function**: `_calculate_new_stop()` (likely around line 600-700)

```python
def _calculate_new_stop(self, ts: TrailingStopInstance, current_price: Decimal) -> Decimal:
    if ts.side == 'long':
        # For long: SL = highest_price - callback%
        new_sl = ts.highest_price * (1 - ts.callback_percent / 100)
    else:
        # For short: SL = lowest_price + callback%
        new_sl = ts.lowest_price * (1 + ts.callback_percent / 100)

    return new_sl
```

**When ts.callback_percent = 0**:
```python
new_sl = ts.highest_price * (1 - 0 / 100)
new_sl = ts.highest_price * 1.0
new_sl = ts.highest_price  ← NO OFFSET!
```

**Result**: SL at exact highest price → validation fails → TS broken!

---

## 💥 IMPACT ASSESSMENT

### Severity: 🔴 CRITICAL

**Why Critical**:
1. **No Protection**: SL = current_price means no protection from price reversal
2. **TS Not Working**: Trailing Stop completely broken after bot restart
3. **Silent Failure**: TS "activated" but SL update fails validation
4. **All Positions Affected**: Every position with TS after restart has this bug

### Financial Impact

**If price reverses after TS activation**:
```
Entry:   2.258
Peak:    2.304 (TS activated here)
SL:      2.304 (WRONG - should be 2.29248)

Price drops to 2.29:
  - Expected: Position still open (SL at 2.29248)
  - Actual: Position CLOSED at 2.304 (initial SL, no TS protection!)

Loss: NO trailing benefit gained!
```

**Estimated Impact**:
- TS activation triggers but provides NO protection
- Position falls back to initial SL (if any)
- Lost opportunity to lock in profits

---

## 🔧 ROOT CAUSE SUMMARY

### The Chain of Failures

1. **Missing Parameters in Constructor**
   - `_restore_state()` doesn't pass `activation_percent` and `callback_percent`
   - TrailingStopInstance created with defaults (0)

2. **DB Overwritten with Zeros**
   - Next `_save_state()` call saves 0 values to DB
   - Original correct values lost

3. **SL Calculation Broken**
   - `callback_percent = 0` → no offset applied
   - SL = highest_price exactly
   - Validation fails (SL >= current_price for long)

4. **Silent Failure**
   - TS logs "activated" but SL update aborted
   - No visible error to user
   - Position unprotected

---

## ✅ THE FIX (Plan Only - NO CODE CHANGES YET)

### Fix #1: Restore activation_percent and callback_percent

**File**: `protection/trailing_stop.py`
**Function**: `_restore_state()` (line ~373)

**Add Missing Parameters**:
```python
ts = TrailingStopInstance(
    symbol=state_data['symbol'],
    entry_price=Decimal(str(state_data['entry_price'])),
    ...
    side=side_value,
    quantity=Decimal(str(state_data['quantity'])),
    # FIX: Add missing parameters
    activation_percent=Decimal(str(state_data.get('activation_percent', 0))),
    callback_percent=Decimal(str(state_data.get('callback_percent', 0)))
)
```

### Fix #2: Fallback to Position Data if DB Has Zeros

**Better Fix with Fallback**:
```python
# Read from TS state first
activation_pct = Decimal(str(state_data.get('activation_percent', 0)))
callback_pct = Decimal(str(state_data.get('callback_percent', 0)))

# If zeros in DB (bug), fallback to position table
if activation_pct == 0 or callback_pct == 0:
    if position_data:
        activation_pct = Decimal(str(position_data.get('trailing_activation_percent', 2.0)))
        callback_pct = Decimal(str(position_data.get('trailing_callback_percent', 0.5)))
        logger.warning(
            f"{symbol}: TS state has zero activation/callback, "
            f"using position data: {activation_pct}%/{callback_pct}%"
        )

ts = TrailingStopInstance(
    ...
    activation_percent=activation_pct,
    callback_percent=callback_pct
)
```

---

## 🧪 TESTING PLAN

### Test 1: Verify Fix with Current Position

1. Fix code (add activation_percent/callback_percent to constructor)
2. Restart bot
3. Check TS state restored correctly:
```python
assert ts.activation_percent == 2.0
assert ts.callback_percent == 0.5
```

### Test 2: Verify SL Calculation

1. Trigger TS activation
2. Check proposed SL:
```python
expected_sl = highest_price * 0.995  # For callback=0.5%
assert abs(proposed_sl - expected_sl) < 0.01
assert proposed_sl < current_price  # For long
```

### Test 3: Verify DB Persistence

1. Check TS state in DB after fix:
```sql
SELECT activation_percent, callback_percent
FROM monitoring.trailing_stop_state
WHERE symbol = 'HNTUSDT';

Expected:
  activation_percent: 2.0000
  callback_percent: 0.5000
```

---

## 📋 VERIFICATION CHECKLIST

Before deploying fix:
- [ ] Code review: _restore_state() modified correctly
- [ ] Test: activation_percent and callback_percent restored
- [ ] Test: SL calculation correct (includes callback offset)
- [ ] Test: SL validation passes
- [ ] Test: DB updated with correct values
- [ ] Verify: No side effects on create_trailing_stop()

After deploying fix:
- [ ] Monitor logs for "TS ACTIVATED" events
- [ ] Verify: proposed_sl < current_price for long
- [ ] Verify: proposed_sl > current_price for short
- [ ] Check: distance_percent in logs = 0.5 (not 0)
- [ ] Confirm: No more "SL VALIDATION FAILED" errors

---

## 🎯 PRIORITY

**CRITICAL** - Fix immediately!

**Why**:
- TS completely broken after bot restart
- All positions lose TS protection
- Silent failure (no obvious error)
- Financial impact (lost profit protection)

**Recommended Action**:
1. Fix code NOW (add 2 lines)
2. Restart bot
3. Manually fix affected positions in DB (set correct callback_percent)
4. Monitor next TS activation

---

## 🔗 RELATED FILES

1. **Bug Location**: `protection/trailing_stop.py:373-394`
2. **DB Schema**: `monitoring.trailing_stop_state` table
3. **Tests**: Need to create regression test

---

**Generated**: 2025-10-28 07:18
**Investigator**: Claude (Deep Analysis)
**Status**: ✅ ROOT CAUSE CONFIRMED - FIX PLAN READY
**Priority**: 🔴 CRITICAL - IMMEDIATE ACTION REQUIRED
