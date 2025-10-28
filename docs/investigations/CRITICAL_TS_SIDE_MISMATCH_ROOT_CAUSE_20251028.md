# 🔴 CRITICAL: Trailing Stop Side Mismatch - Root Cause Investigation

**Date**: 2025-10-28 06:00+
**Priority**: 🔴 P0 - CRITICAL
**Status**: ✅ ROOT CAUSE IDENTIFIED
**Type**: Deep Research (NO CODE CHANGES)

---

## ⚡ EXECUTIVE SUMMARY

### The Problem

При перезапуске бота возникает ошибка:
```
ERROR - 🔴 POWRUSDT: SIDE MISMATCH DETECTED!
  TS side (from DB):      short
  Position side (exchange): long
  TS entry price (DB):    0.11630000
  Position entry (exchange): 0.1185
  → Deleting stale TS state (prevents 100% SL failure)
```

### Root Cause Discovery

**НАЙДЕНО**: Critical bug в `database/repository.py:1055-1072`

**Проблема**: `save_trailing_stop_state()` использует `ON CONFLICT (symbol, exchange) DO UPDATE` который **НЕ обновляет** критические поля:
- ❌ `side` - НЕ обновляется
- ❌ `entry_price` - НЕ обновляется
- ❌ `quantity` - НЕ обновляется
- ❌ `activation_percent` - НЕ обновляется
- ❌ `callback_percent` - НЕ обновляется

**Result**: При быстром переоткрытии позиции (SHORT → LONG) в БД остается STALE state со старым `side` но новым `position_id`.

### Impact

**Frequency**: Происходит при каждом быстром переоткрытии позиции с другим side
**Severity**: 🟡 MEDIUM - Бот обнаруживает и исправляет, но создает log noise
**Risk**: ⚠️ Потенциальный риск если SIDE MISMATCH detection не сработает

---

## 🔬 DEEP INVESTIGATION

### Timeline of Discovery

**Investigation Duration**: ~45 minutes
**Tools Used**: Grep, Read, Code analysis, DB schema review
**Methods**: Lifecycle analysis, race condition analysis, SQL query forensics

### Step 1: Code Analysis - Cleanup Logic ✅

**File**: `protection/trailing_stop.py:1411-1423`

```python
async def on_position_closed(self, symbol: str, realized_pnl: float = None):
    """Handle position closure

    FIX #3: Always clean database state, even if TS not in memory
    """
    if symbol not in self.trailing_stops:
        # TS not in memory, but might exist in DB (orphaned state)
        # FIX #3: Clean database anyway to prevent stale states
        logger.debug(f"{symbol}: Position closed but no TS in memory, checking DB...")
        delete_success = await self._delete_state(symbol)
        if delete_success:
            logger.info(f"✅ {symbol}: Cleaned orphaned TS state from database on position close")
        return
```

**Finding**: ✅ Cleanup logic EXISTS and is CORRECT

**File**: `core/aged_position_manager.py:336`

```python
await trailing_manager.on_position_closed(symbol, realized_pnl=None)
```

**Finding**: ✅ Cleanup IS called for phantom positions

**Conclusion**: Cleanup logic is working correctly. Problem must be elsewhere.

---

### Step 2: Database Schema Analysis ✅

**File**: `database/repository.py:1142-1164`

```python
async def delete_trailing_stop_state(self, symbol: str, exchange: str) -> bool:
    query = """
        DELETE FROM monitoring.trailing_stop_state
        WHERE symbol = $1 AND exchange = $2
    """
```

**Finding**: DELETE uses `WHERE symbol = $1 AND exchange = $2`

**Table Constraint**: `UNIQUE (symbol, exchange)` - Only ONE record per (symbol, exchange) pair

**Conclusion**: DELETE is correct, but UNIQUE constraint means UPSERT behavior on INSERT.

---

### Step 3: UPSERT Analysis - ROOT CAUSE FOUND! 🔥

**File**: `database/repository.py:1027-1107`

**Insert Query** (lines 1037-1073):
```sql
INSERT INTO monitoring.trailing_stop_state (
    symbol, exchange, position_id, state, is_activated,
    highest_price, lowest_price, current_stop_price,
    stop_order_id, activation_price, activation_percent, callback_percent,
    entry_price, side, quantity, update_count, highest_profit_percent,
    activated_at, last_update_time, last_sl_update_time, last_updated_sl_price,
    last_peak_save_time, last_saved_peak_price,
    created_at
) VALUES (
    $1, $2, $3, $4, $5,
    $6, $7, $8,
    $9, $10, $11, $12,
    $13, $14, $15, $16, $17,
    $18, $19, $20, $21,
    $22, $23,
    COALESCE($24, NOW())
)
ON CONFLICT (symbol, exchange)
DO UPDATE SET
    position_id = EXCLUDED.position_id,          ← ✅ UPDATED
    state = EXCLUDED.state,                      ← ✅ UPDATED
    is_activated = EXCLUDED.is_activated,        ← ✅ UPDATED
    highest_price = EXCLUDED.highest_price,      ← ✅ UPDATED
    lowest_price = EXCLUDED.lowest_price,        ← ✅ UPDATED
    current_stop_price = EXCLUDED.current_stop_price,  ← ✅ UPDATED
    stop_order_id = EXCLUDED.stop_order_id,      ← ✅ UPDATED
    activation_price = EXCLUDED.activation_price,← ✅ UPDATED
    update_count = EXCLUDED.update_count,        ← ✅ UPDATED
    highest_profit_percent = EXCLUDED.highest_profit_percent,  ← ✅ UPDATED
    activated_at = COALESCE(...),                ← ✅ UPDATED
    last_update_time = EXCLUDED.last_update_time,← ✅ UPDATED
    last_sl_update_time = EXCLUDED.last_sl_update_time,  ← ✅ UPDATED
    last_updated_sl_price = EXCLUDED.last_updated_sl_price,  ← ✅ UPDATED
    last_peak_save_time = EXCLUDED.last_peak_save_time,  ← ✅ UPDATED
    last_saved_peak_price = EXCLUDED.last_saved_peak_price  ← ✅ UPDATED
```

**🔴 CRITICAL MISSING FIELDS IN DO UPDATE SET:**
```
entry_price = EXCLUDED.entry_price,              ← ❌ NOT UPDATED!
side = EXCLUDED.side,                            ← ❌ NOT UPDATED!
quantity = EXCLUDED.quantity,                    ← ❌ NOT UPDATED!
activation_percent = EXCLUDED.activation_percent, ← ❌ NOT UPDATED!
callback_percent = EXCLUDED.callback_percent      ← ❌ NOT UPDATED!
```

**WHY THIS IS CRITICAL:**

When a new position is created for existing (symbol, exchange) pair:
1. `INSERT` attempts to insert NEW values (including new side, entry_price)
2. `ON CONFLICT` triggers because (symbol, exchange) already exists
3. `DO UPDATE` updates SOME fields but **NOT side, entry_price, quantity**
4. Result: **MIXED STATE** - new position_id but old side/entry_price!

---

### Step 4: Race Condition Scenarios

#### Scenario 1: Fast Position Reopen (Most Common)

**Timeline**:
```
T0: SHORT POWRUSDT @ 0.11630000 (active)
T1: Price hits SL, position closes ON EXCHANGE
T2: WebSocket receives close event
T3: on_position_closed() called, starts async DELETE
T4: NEW SIGNAL arrives for POWRUSDT (LONG @ 0.1185)
T5: create_trailing_stop() called for LONG
T6: save_trailing_stop_state() called with side='long', entry=0.1185
T7: ON CONFLICT triggered (old record still exists)
T8: DO UPDATE executes - updates position_id, state, etc
T9: BUT! side='short', entry_price=0.11630000 NOT updated (MIXED STATE!)
T10: DELETE executes (may or may not succeed)
```

**Result**:
- If DELETE at T10 succeeds: TS state deleted, new one created on next update (OK)
- If DELETE at T10 fails: STALE state persists with side='short' but position is LONG ❌

#### Scenario 2: Memory Cache Stale (Less Common)

**Timeline**:
```
T0: SHORT POWRUSDT active, TS in memory
T1: Position closes on exchange (manual or external SL)
T2: WebSocket lag - bot doesn't know yet
T3: NEW SIGNAL for POWRUSDT LONG arrives
T4: create_trailing_stop() called
T5: Checks: if symbol in self.trailing_stops (line 473)
T6: OLD SHORT TS still in memory!
T7: Returns EXISTING TS instance (SHORT)
T8: No new TS created
T9: update_price() called, saves OLD state
T10: UPSERT with old side='short' but new position
```

**Result**: TS state has side='short' but position is LONG ❌

#### Scenario 3: Cleanup Delay + Quick Reopen

**Timeline**:
```
T0: SHORT position closes
T1: on_position_closed() queued (event loop busy)
T2: LONG position created immediately
T3: save_trailing_stop_state() with side='long'
T4: ON CONFLICT - old record exists
T5: DO UPDATE - side NOT updated (still 'short')
T6: on_position_closed() finally executes
T7: DELETE removes record
T8: But damage done - logs show side mismatch
```

**Result**: State deleted but error logged (recovers but noisy)

---

### Step 5: Why This Wasn't Caught Before

**Historical Context**:

From `docs/investigations/FIX_PLAN_STALE_TS_STATE_VARIANT_A_20251020.md`:
- Fix was implemented on 2025-10-20
- Fixed phantom cleanup in aged_position_manager
- Added `on_position_closed()` calls

**Why Fix Didn't Solve Problem**:
- Cleanup IS called correctly ✅
- DELETE IS executed ✅
- BUT! **DO UPDATE SET missing fields** was not discovered ❌

**Why NOT Caught in Testing**:
- Single position tests: OK (first INSERT, no conflict)
- Slow reopens: OK (DELETE completes before new INSERT)
- Fast reopens: ❌ CONFLICT triggers, bug manifests

**Why Appears on Restart**:
- Normal operation: TS in memory corrects itself
- Restart: Loads STALE state from DB
- SIDE MISMATCH detection catches it

---

## 📊 EVIDENCE AND VERIFICATION

### Code Evidence

**File**: `database/repository.py:1055-1072`
**Lines**: Verified ON CONFLICT DO UPDATE SET
**Missing**: `side`, `entry_price`, `quantity`, `activation_percent`, `callback_percent`

**File**: `protection/trailing_stop.py:1411-1423`
**Lines**: Verified cleanup logic CORRECT

**File**: `protection/trailing_stop.py:471-475`
**Lines**: Verified memory check EXISTS

### Log Evidence

**From User**:
```
2025-10-28 06:00:19,576 - protection.trailing_stop - ERROR - 🔴 POWRUSDT: SIDE MISMATCH DETECTED!
  TS side (from DB):      short
  Position side (exchange): long
  TS entry price (DB):    0.11630000
  Position entry (exchange): 0.1185
```

**Analysis**:
- OLD entry: 0.11630000 (SHORT position)
- NEW entry: 0.1185 (LONG position)
- Price gap: ~2% (reasonable for fast reopen)
- Side: SHORT → LONG (opposite direction)

**Conclusion**: Confirms fast position reopen scenario

---

## 🎯 ROOT CAUSE STATEMENT

**Primary Cause**: `save_trailing_stop_state()` ON CONFLICT DO UPDATE SET missing critical fields

**Secondary Cause**: Race condition between position close cleanup and new position creation

**Tertiary Cause**: UNIQUE (symbol, exchange) constraint causes UPSERT behavior instead of failing

**Combined Effect**: Fast position reopens with opposite side leave STALE TS state in DB with MIXED values (new position_id, old side/entry_price)

---

## 🔧 FIX STRATEGY

### Option A: Fix DO UPDATE SET (RECOMMENDED) ✅

**Approach**: Add missing fields to DO UPDATE SET clause

**Pros**:
- ✅ Fixes root cause directly
- ✅ Simple 5-line change
- ✅ No race conditions
- ✅ Works for all scenarios

**Cons**:
- ⚠️ Need to test UPSERT behavior

**Implementation**:
```sql
ON CONFLICT (symbol, exchange)
DO UPDATE SET
    position_id = EXCLUDED.position_id,
    state = EXCLUDED.state,
    is_activated = EXCLUDED.is_activated,
    -- ... existing fields ...
    entry_price = EXCLUDED.entry_price,          ← ADD
    side = EXCLUDED.side,                        ← ADD
    quantity = EXCLUDED.quantity,                ← ADD
    activation_percent = EXCLUDED.activation_percent,  ← ADD
    callback_percent = EXCLUDED.callback_percent  ← ADD
```

**Risk**: 🟢 LOW

---

### Option B: Delete Before Create

**Approach**: Explicitly DELETE before creating new TS for same symbol

**Pros**:
- ✅ Prevents UPSERT
- ✅ Clean slate for new position

**Cons**:
- ❌ Adds DELETE overhead
- ❌ Doesn't fix root cause
- ❌ Race condition still possible

**Implementation**:
```python
async def create_trailing_stop(...):
    # STEP 0: Delete old state if exists
    await self._delete_state(symbol)

    # STEP 1: Quick check if already exists
    async with self.lock:
        if symbol in self.trailing_stops:
            ...
```

**Risk**: 🟡 MEDIUM (performance impact)

---

### Option C: Add Position ID to UNIQUE Constraint

**Approach**: Change UNIQUE constraint to (symbol, exchange, position_id)

**Pros**:
- ✅ Allows multiple TS states per symbol
- ✅ Prevents UPSERT conflicts

**Cons**:
- ❌ **MAJOR SCHEMA CHANGE**
- ❌ **BREAKING CHANGE** - requires migration
- ❌ May break cleanup logic
- ❌ Orphan states accumulate

**Risk**: 🔴 HIGH (not recommended)

---

### Option D: Lock Around Create + Save

**Approach**: Hold lock during entire create+save operation

**Pros**:
- ✅ Prevents race conditions

**Cons**:
- ❌ Performance impact (granular locking disabled)
- ❌ Doesn't fix DO UPDATE SET bug
- ❌ Wave execution timeouts return

**Risk**: 🔴 HIGH (performance regression)

---

## ✅ RECOMMENDED FIX

**Choose**: **Option A - Fix DO UPDATE SET** ✅

**Reasoning**:
1. Fixes root cause directly
2. Simple, surgical change
3. Low risk, high impact
4. No performance regression
5. Works for all scenarios

**Implementation Priority**: 🔴 P0 - CRITICAL

**Estimated Time**: 15 minutes (code) + 30 minutes (testing)

---

## 📋 DETAILED FIX PLAN

### Phase 1: Code Change ✅

**File**: `database/repository.py`
**Lines**: 1055-1072
**Change**: Add 5 missing fields to DO UPDATE SET

**Before**:
```sql
ON CONFLICT (symbol, exchange)
DO UPDATE SET
    position_id = EXCLUDED.position_id,
    state = EXCLUDED.state,
    ...
    last_saved_peak_price = EXCLUDED.last_saved_peak_price
```

**After**:
```sql
ON CONFLICT (symbol, exchange)
DO UPDATE SET
    position_id = EXCLUDED.position_id,
    state = EXCLUDED.state,
    ...
    last_saved_peak_price = EXCLUDED.last_saved_peak_price,
    -- CRITICAL FIX: Update position-specific fields on conflict
    entry_price = EXCLUDED.entry_price,
    side = EXCLUDED.side,
    quantity = EXCLUDED.quantity,
    activation_percent = EXCLUDED.activation_percent,
    callback_percent = EXCLUDED.callback_percent
```

### Phase 2: Testing Strategy

#### Test 1: Fast Position Reopen
```python
# Scenario: SHORT → LONG quick reopen
1. Create SHORT position for TESTUSDT
2. Close position (triggers cleanup)
3. IMMEDIATELY create LONG position for TESTUSDT
4. Verify DB: side='long', entry_price=new
5. Restart bot
6. Verify: NO SIDE MISMATCH error
```

#### Test 2: Same Side Reopen
```python
# Scenario: LONG → LONG (update existing)
1. Create LONG position for TESTUSDT
2. Close position
3. Create LONG position for TESTUSDT (same side)
4. Verify DB: entry_price=new
5. Restart bot
6. Verify: NO SIDE MISMATCH error
```

#### Test 3: Normal Operation
```python
# Scenario: Regular TS updates
1. Create LONG position
2. Update price multiple times
3. Verify DB: all fields updated correctly
4. No performance regression
```

### Phase 3: Deployment

**Steps**:
1. Apply code change to repository.py
2. Run syntax validation
3. Run unit tests (if exist)
4. Deploy to production
5. Monitor logs for SIDE MISMATCH errors
6. Verify frequency reduces to ZERO

**Rollback Plan**:
```bash
# If issues occur, revert commit
git revert HEAD
git push origin main
```

### Phase 4: Verification

**Metrics to Track**:
- SIDE MISMATCH error frequency
- TS state correctness on restart
- Position reopen scenarios
- Performance (no regression)

**Success Criteria**:
- ✅ Zero SIDE MISMATCH errors
- ✅ All TS states have correct side
- ✅ No performance regression
- ✅ No new errors introduced

---

## 🔍 ADDITIONAL FINDINGS

### Related Issues Found

1. **Cleanup is CORRECT** ✅
   - on_position_closed() works
   - Delete is called properly
   - aged_position_manager calls cleanup

2. **Memory Check is CORRECT** ✅
   - create_trailing_stop() checks if exists
   - Returns existing instance
   - Prevents duplicate creation

3. **UPSERT Behavior Intentional**
   - ON CONFLICT designed for updates
   - Intended for price/state updates
   - **BUT** not designed for position replacement

### Lessons Learned

1. **UPSERT clauses need ALL fields**
   - ON CONFLICT DO UPDATE should update ALL updatable fields
   - Or explicitly exclude static fields
   - Document which fields are immutable

2. **Fast reopens are COMMON**
   - SL hits, new signal arrives immediately
   - Manual close, quick reopen
   - Need to handle cleanly

3. **Memory vs DB sync is critical**
   - Memory has current state
   - DB persists state
   - Must stay synchronized

---

## 📚 REFERENCES

1. **Previous Investigation**: `docs/investigations/FIX_PLAN_STALE_TS_STATE_VARIANT_A_20251020.md`
   - Fixed cleanup logic
   - Added on_position_closed() calls
   - Did NOT find DO UPDATE bug

2. **Implementation Report**: `docs/investigations/IMPLEMENTATION_REPORT_INITIAL_SL_CLEANUP_20251020.md`
   - Confirmed cleanup working
   - Tested phantom positions
   - Did NOT test fast reopens

3. **Error Summary**: `docs/investigations/ERRORS_SUMMARY_20251028.md`
   - Side mismatch classified as "expected"
   - Assumed stale state cleanup issue
   - Did NOT investigate DO UPDATE

---

## ✅ CONCLUSION

**Root Cause**: `save_trailing_stop_state()` ON CONFLICT DO UPDATE SET missing critical fields (side, entry_price, quantity, activation_percent, callback_percent)

**Impact**: Fast position reopens leave STALE TS state in DB

**Fix**: Add 5 missing fields to DO UPDATE SET clause

**Priority**: 🔴 P0 - CRITICAL

**Risk**: 🟢 LOW

**Effort**: 15 minutes code + 30 minutes testing

**Status**: ✅ READY FOR IMPLEMENTATION (awaiting approval)

---

**END OF INVESTIGATION**

**Investigator**: Claude Code
**Date**: 2025-10-28
**Duration**: 45 minutes
**Result**: ROOT CAUSE IDENTIFIED ✅
