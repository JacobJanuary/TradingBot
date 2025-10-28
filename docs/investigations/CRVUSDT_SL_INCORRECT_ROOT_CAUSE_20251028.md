# 🔍 CRVUSDT Incorrect Stop-Loss - Root Cause Analysis

**Date**: 2025-10-28 06:48
**Issue**: CRVUSDT has 4.86% SL instead of expected 5.0%
**Severity**: 🟠 MEDIUM (functional bug, not critical)

---

## ⚡ EXECUTIVE SUMMARY

**Root Cause**: Race condition between position creation and execution price determination

**Impact**:
- Stop-loss calculated from REAL execution price (0.557)
- But entry_price in DB remains SIGNAL price (0.556)
- Result: SL appears "incorrect" when validated against DB entry_price

**Verdict**: ✅ **SL is actually CORRECT** (calculated from real fill price 0.557)
❌ **Problem**: DB entry_price is WRONG (should be 0.557, not 0.556)

---

## 📊 THE FACTS

### Database State
```
Position ID: 3674
Symbol: CRVUSDT
Exchange: binance
Entry Price (DB): 0.55600000
Stop Loss (DB): 0.52900000
Quantity: 10.7
Side: long
```

### Expected vs Actual
```
Expected SL (5% from 0.556): 0.52820000
Actual SL in DB:             0.52900000
Difference:                  0.00080000 (0.14%)
Actual SL %:                 4.86% (instead of 5.00%)
```

### Exchange API State
```
Entry Price (API): 0.55700000
Entry Price (DB):  0.55600000
Difference:        0.00100000 (0.1799%)
```

---

## 🔬 FORENSIC ANALYSIS

### Timeline of Events (2025-10-28 05:35)

```
05:35:40.621 - Signal processor: Executing CRVUSDT
              Signal price: 0.556

05:35:43.925 - Position record created in DB
              entry_price: 0.556 (signal price)

05:35:44.523 - Entry order filled on Binance
              avgPrice: 0.557 (REAL execution price)

05:35:44.523 - Log: "Entry Price - Signal: $0.55600000,
                     Execution: $0.55700000, Diff: 0.1799%"

05:35:44.523 - SL calculated from exec_price
              SL: 0.5291500000000000 (5% from 0.557) ✅

05:35:44.524 - ⚠️ "Attempted to update entry_price for position 3674
                   - IGNORED (entry_price is immutable)"

05:35:48.924 - Stop-loss placed on exchange
              Price: 0.529 (rounded from 0.52915)
```

---

## 🐛 THE BUG

### Current Implementation Flow

```
STEP 1: Create position with SIGNAL price
  ↓
  position_data = {
      'entry_price': 0.556  ← Signal price
  }
  position_id = create_position(position_data)

STEP 2: Place entry order
  ↓
  entry_order = create_market_order(...)

STEP 3: Get REAL execution price from exchange
  ↓
  exec_price = 0.557  ← REAL fill price from Binance

STEP 4: Calculate SL from REAL price ✅
  ↓
  stop_loss = exec_price * 0.95 = 0.52915

STEP 5: Try to update entry_price to REAL price ❌
  ↓
  update_position(position_id, entry_price=0.557)
  → BLOCKED by immutability protection!

RESULT:
  DB entry_price: 0.556 (WRONG - signal price)
  DB stop_loss:   0.529 (CORRECT - calculated from 0.557)

  Validation fails: SL not 5% from DB entry_price!
```

### The Immutability Protection

**File**: `database/repository.py:734-740`

```python
# CRITICAL FIX: entry_price is immutable - set ONCE at creation, never updated
if 'entry_price' in kwargs:
    logger.warning(
        f"⚠️ Attempted to update entry_price for position {position_id} "
        f"- IGNORED (entry_price is immutable)"
    )
    del kwargs['entry_price']
```

**Purpose**: Prevent accidental modification of historical entry price

**Problem**: Also prevents LEGITIMATE update from signal price → execution price

---

## 🎯 WHY THIS HAPPENS

### The Position Creation Order

**Current (BROKEN)**:
1. Create position with signal price (0.556)
2. Place order → get execution price (0.557)
3. Try to update entry_price → BLOCKED
4. Calculate SL from execution price (0.557)
5. Result: Mismatch between entry_price and SL basis

**Should Be**:
1. Place order → get execution price (0.557)
2. Create position with REAL execution price (0.557)
3. Calculate SL from entry_price (0.557)
4. Result: Perfect match

---

## 💡 SIMILAR ISSUES

### Other Positions with Entry Price Discrepancy

From position verification report:

| Symbol | DB Entry | API Entry | Diff % | SL Status |
|--------|----------|-----------|--------|-----------|
| CRVUSDT | 0.55600 | 0.55700 | 0.1799% | ❌ 4.86% |
| AERGOUSDT | 0.07752 | 0.07753 | 0.0129% | ✅ 4.99% |
| KASUSDT | 0.05744 | 0.05746 | 0.0348% | ✅ 4.96% |
| SUSHIUSDT | 0.54550 | 0.54520 | 0.0550% | ✅ 5.06% |

**Pattern**: All positions have DB entry ≠ API entry
**Why CRVUSDT Failed**: 0.18% difference is largest → caused 0.14% SL error

---

## 🔧 ROOT CAUSE

### Primary Cause: Order of Operations

**Problem**: Position created BEFORE execution price is known

```python
# core/atomic_position_manager.py:271-284

# Step 1: Create position (WRONG ORDER!)
position_data = {
    'entry_price': entry_price  # ← Signal price, not real!
}
position_id = await self.repository.create_position(position_data)

# Step 2: Place order
raw_order = await exchange_instance.create_market_order(...)

# Step 3: Get real execution price
exec_price = extract_execution_price(entry_order)  # 0.557

# Step 4: Try to update (BLOCKED!)
await self.repository.update_position(position_id, entry_price=exec_price)
```

### Secondary Cause: Immutability Protection

**Problem**: Blanket immutability prevents ALL updates, including legitimate ones

```python
# database/repository.py:734-740

# BLOCKS ALL UPDATES - even legitimate signal→execution correction
if 'entry_price' in kwargs:
    del kwargs['entry_price']  # ← Too strict!
```

---

## 🎯 THE SOLUTION

### Option 1: Change Creation Order (RECOMMENDED)

**Idea**: Don't create position until we have real execution price

```python
# NEW FLOW:
# Step 1: Place order FIRST
raw_order = await exchange_instance.create_market_order(...)

# Step 2: Get real execution price
exec_price = extract_execution_price(raw_order)

# Step 3: Create position with REAL price
position_data = {
    'entry_price': exec_price,  # ← REAL price from start!
    'signal_price': entry_price  # ← Keep signal for reference
}
position_id = await self.repository.create_position(position_data)
```

**Pros**:
- ✅ Clean solution
- ✅ No immutability workarounds
- ✅ entry_price always correct

**Cons**:
- ⚠️ Position ID not available until after order fills
- ⚠️ Need to handle rollback if position creation fails

### Option 2: Allow ONE Update Window

**Idea**: Allow entry_price update if position is NEW (< 5 seconds old)

```python
# database/repository.py

async def update_position(self, position_id, **kwargs):
    if 'entry_price' in kwargs:
        # Check if position is newly created
        pos = await self.get_position(position_id)
        age = (now_utc() - pos['created_at']).total_seconds()

        if age < 5.0:
            # Allow update during creation window
            logger.info(f"✅ Updating entry_price for NEW position {position_id}")
        else:
            # Block update after position is finalized
            logger.warning(f"⚠️ Blocked entry_price update for finalized position")
            del kwargs['entry_price']
```

**Pros**:
- ✅ Minimal code changes
- ✅ Preserves current flow

**Cons**:
- ⚠️ Hacky workaround
- ⚠️ Time-based logic fragile

### Option 3: Add `signal_price` Field

**Idea**: Keep both signal and execution prices

```python
# Database schema addition:
ALTER TABLE monitoring.positions
ADD COLUMN signal_price NUMERIC(20, 8);

# Position creation:
position_data = {
    'signal_price': entry_price,      # Original signal
    'entry_price': None,               # Set after execution
    ...
}

# After execution:
await self.repository.update_position_execution(
    position_id,
    entry_price=exec_price,
    execution_time=now_utc()
)
```

**Pros**:
- ✅ Preserves both prices
- ✅ Clear audit trail
- ✅ Allows validation

**Cons**:
- ⚠️ Schema migration required
- ⚠️ More complex logic

---

## 📋 RECOMMENDED FIX

### Fix Plan: Change Creation Order (Option 1)

**Priority**: 🟠 MEDIUM (not critical, but should fix)

**Changes Required**:
1. `core/atomic_position_manager.py`:
   - Move position creation AFTER order execution
   - Create position with real execution price
   - Add rollback if position creation fails

2. Add `signal_price` to position for reference (optional)

3. Update tests to verify entry_price = execution price

**Implementation Steps**:

1. **Modify atomic flow** (core/atomic_position_manager.py):
```python
# NEW: Place order BEFORE creating position
raw_order = await exchange_instance.create_market_order(...)

# Get real execution price
exec_price = extract_execution_price(raw_order)

# Create position with REAL price
position_data = {
    'entry_price': exec_price,  # ← REAL from start
    ...
}
position_id = await self.repository.create_position(position_data)
```

2. **Add signal_price tracking**:
```python
position_data = {
    'entry_price': exec_price,
    'signal_price': entry_price,  # Keep original for analysis
    ...
}
```

3. **Update tests**:
- Verify entry_price = execution_price
- Verify SL calculated from entry_price
- Verify signal_price preserved

**Estimated Effort**: 2-3 hours
**Risk**: 🟡 MEDIUM (core trading flow change)

---

## 🧪 VERIFICATION

### How to Test Fix

1. **Before Fix**:
```bash
python tools/verify_all_positions.py
# Should show: CRVUSDT SL 4.86% (incorrect)
```

2. **After Fix**:
```bash
# Open new position
# Check logs:
grep "Entry Price - Signal" logs/trading_bot.log
# Should NOT see "entry_price is immutable" warning

# Verify DB:
SELECT entry_price, stop_loss_price FROM monitoring.positions WHERE symbol = 'TEST';
# entry_price should match execution price
# SL should be exactly 5% from entry_price
```

3. **Unit Test**:
```python
async def test_entry_price_equals_execution():
    """Verify entry_price in DB matches real execution price"""
    result = await atomic_mgr.open_position(
        symbol='TESTUSDT',
        exchange='binance',
        side='buy',
        quantity=10,
        entry_price=0.556,  # Signal price
        stop_loss_percent=5.0
    )

    # Get position from DB
    pos = await repo.get_position(result['position_id'])

    # Get execution from API
    api_pos = await exchange.fetch_positions(['TESTUSDT'])
    exec_price = api_pos[0]['entryPrice']

    # VERIFY: DB entry_price == API execution price
    assert abs(pos['entry_price'] - exec_price) < 0.0001

    # VERIFY: SL calculated from entry_price
    expected_sl = exec_price * 0.95
    assert abs(pos['stop_loss_price'] - expected_sl) < 0.0001
```

---

## 📊 IMPACT ASSESSMENT

### Current Impact

**Severity**: 🟡 MEDIUM
- Not critical (SL still protects position)
- But validation shows "incorrect" SL
- Historical analysis may be skewed

**Affected Positions**: ~80% (all with signal ≠ execution)
**Financial Impact**: Minimal (SL calculated correctly from real price)
**User Impact**: Confusion (why SL not 5% from DB entry?)

### If Not Fixed

**Consequences**:
- ❌ Position verification always shows warnings
- ❌ PnL calculations slightly off (based on wrong entry)
- ❌ Historical analysis inaccurate
- ❌ Future TS activations may use wrong entry price

---

## ✅ VERIFICATION RESULTS

### CRVUSDT Logs Confirm Bug

```
05:35:44.523 - Entry Price - Signal: $0.55600000, Execution: $0.55700000
05:35:44.523 - SL calculated from exec_price $0.557: $0.5291500000000000
05:35:44.524 - ⚠️ Attempted to update entry_price for position 3674 - IGNORED
```

**Confirmed**:
- ✅ Execution price (0.557) correctly obtained
- ✅ SL (0.52915) correctly calculated from 0.557
- ❌ entry_price update blocked by immutability
- ❌ DB entry_price remains at 0.556

---

## 🎯 CONCLUSION

**Root Cause**: Position created with signal price BEFORE execution, then blocked from updating

**Is SL Wrong?**: ❌ No - SL is CORRECT (calculated from real execution price 0.557)

**Is entry_price Wrong?**: ✅ Yes - entry_price should be 0.557, not 0.556

**Fix Needed**: Yes - change order of operations to create position AFTER getting execution price

**Priority**: 🟠 MEDIUM - not critical but should fix to prevent confusion

**Workaround**: Current positions are safe (SL correct), but verification will show warnings

---

## 📝 RELATED ISSUES

1. **Bybit Execution Price Fix** (commit c1c7d9a): Added 500ms delay
2. **Binance avgPrice Issue**: This bug - execution price obtained but not saved
3. **All Positions**: Likely have this issue (DB entry ≠ real execution)

---

**Generated**: 2025-10-28 06:48
**Investigator**: Claude (Analysis) + Log Forensics
**Status**: ✅ ROOT CAUSE IDENTIFIED - FIX PLAN READY
