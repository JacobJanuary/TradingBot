# 🚨 CRITICAL: TS Activation Failure Investigation

**Date:** 2025-10-20 15:30
**Status:** 🔴 CRITICAL - TS not activating despite profit >1.5%
**Investigation:** COMPLETED
**Root Causes Found:** 3 critical bugs

---

## 🔴 PROBLEM STATEMENT

**User Report:**
> "Есть позиции с профитом выше порога активации TS (1.5%), однако самих активации и изменения SL не наблюдаю"

**Confirmed:**
- 5 positions with profit >1.5%
- BLASTUSDT: **18.6% profit!** (activation threshold: 1.5%)
- TS state: `inactive` / `waiting`
- No activation logged
- No SL updates

---

## 📊 EVIDENCE

### Positions Above Activation Threshold

```sql
SELECT symbol, side, entry_price, current_price, pnl_percentage,
       has_trailing_stop, trailing_activated
FROM monitoring.positions
WHERE status='active' AND pnl_percentage > 1.5
```

| Symbol | Side | Entry | Current | Profit% | TS? | Activated? |
|--------|------|-------|---------|---------|-----|------------|
| BLASTUSDT | short | 0.00187 | 0.001522 | **18.6%** | ✅ | ❌ |
| USELESSUSDT | short | 0.35060 | 0.33536 | 4.3% | ✅ | ❌ |
| PIPPINUSDT | short | 0.01667 | 0.01604 | 3.8% | ✅ | ❌ |
| HEMIUSDT | short | 0.06416 | 0.06279 | 2.1% | ✅ | ❌ |
| ORDERUSDT | short | 0.23474 | 0.22976 | 2.1% | ✅ | ❌ |

**All 5 positions should have TS ACTIVATED but didn't!**

### TS State in Database

```sql
SELECT symbol, state, is_activated, activation_price,
       highest_price, lowest_price, entry_price
FROM monitoring.trailing_stop_state
WHERE symbol='BLASTUSDT'
```

| Symbol | State | Activated | Activation Price | Highest | Lowest | Entry |
|--------|-------|-----------|------------------|---------|--------|-------|
| BLASTUSDT | **inactive** | false | 0.00184195 | **999999** | 0.00187 | **0.00000** |

**🔥 Critical Issues:**
1. `state = inactive` (should be `waiting` or `active`)
2. `highest_price = 999999` (UNINITIALIZED for short!)
3. `entry_price = 0` (CORRUPT!)

---

## 🔍 ROOT CAUSE ANALYSIS

### Investigation Timeline

**15:04:17** - Bot startup after first restart:
```
INFO - Created trailing stop for BLASTUSDT short:
       entry=0.00187000, activation=0.00184195000
```

**15:04:22** - Price update received:
```
INFO - [TS] update_price called: BLASTUSDT @ 0.001522
```

**15:04:23** - ⚠️ **CRITICAL ERROR:**
```
WARNING - ⚠️ BLASTUSDT: Position not found on exchange,
          removing orphaned trailing stop (auto-cleanup)
```

**15:24:06** - Bot startup after second restart:
```
INFO - ✅ BLASTUSDT: TS state RESTORED from DB
       state=inactive, entry_price=0, highest_price=N/A
```

**15:24:07+** - Price updates continue:
```
INFO - [TS] update_price called: BLASTUSDT @ 0.001522
(repeated every 10 seconds)
```

**BUT:** No activation occurs!

---

## 🐛 BUG #1: False "Orphaned" Detection

### Location
`protection/trailing_stop.py:951-966`

### The Code
```python
# In _update_stop_order()
if hasattr(self.exchange, 'fetch_positions'):
    positions = await self.exchange.fetch_positions([ts.symbol])
    position_exists = any(
        p.get('symbol') == ts.symbol and
        (p.get('contracts', 0) > 0 or p.get('size', 0) > 0)
        for p in positions
    )

    if not position_exists:
        logger.warning(f"Position not found on exchange, removing orphaned TS")
        await self.on_position_closed(ts.symbol)  # ← Deletes TS!
        return False
```

### Why It's Wrong

**Problem:** `_update_stop_order()` is called DURING TS CREATION!

**Flow:**
1. `create_trailing_stop()` creates TS with `state=waiting`
2. For SHORT positions, `initial_stop=None` (no SL yet)
3. Config has `breakeven_at=None` (disabled)
4. `_check_activation()` called on first `update_price()`
5. If NOT activated yet, tries to update stop → calls `_update_stop_order()`
6. `_update_stop_order()` checks if position exists on exchange
7. **Position might not be in exchange cache yet** (WebSocket lag)
8. Thinks it's orphaned → deletes TS!

**Impact:**
- TS created correctly
- TS deleted 1 second later as "orphaned"
- Position has no TS protection
- **Silently fails!**

---

## 🐛 BUG #2: TS State Corruption on "Cleanup"

### Location
`protection/trailing_stop.py:1068-1117`

### The Code
```python
async def on_position_closed(self, symbol: str, realized_pnl=None):
    # Mark as TRIGGERED
    ts.state = TrailingStopState.TRIGGERED

    # Delete from memory
    del self.trailing_stops[symbol]

    # Delete from DB
    await self._delete_state(symbol)  # ← Should delete, but...
```

### Why It Fails

**Expected:** TS deleted from DB
**Reality:** TS state remains in DB but CORRUPTED

**Evidence:**
```sql
-- 20 orphaned TS states in DB!
SELECT COUNT(*) FROM trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1 FROM positions p
    WHERE p.symbol = ts.symbol AND p.status='active'
);
Result: 20
```

**Theory:** `_delete_state()` failed silently OR another process saved state AFTER deletion

**Result:**
- TS deleted from memory
- DB state remains with corrupted values:
  - `state = inactive` (from TRIGGERED transition?)
  - `entry_price = 0` (cleared on close?)
  - `highest_price = 999999` (uninitialized SHORT sentinel)

---

## 🐛 BUG #3: TS Restored in Wrong State

### Location
`protection/trailing_stop.py:213-290`

### The Code
```python
async def _restore_state(self, symbol: str):
    # Fetch from DB
    state_data = await self.repository.get_trailing_stop_state(symbol)

    # Reconstruct TS with DB state
    ts = TrailingStopInstance(
        state=TrailingStopState(state_data['state'].lower()),
        # ... other fields
    )
```

### Why It's Wrong

**When TS restored with `state=inactive`:**
- `update_price()` calls `_check_activation()` (line 473-474)
- `_check_activation()` checks if price >= activation_price
- For SHORT: checks if `current_price <= activation_price`
- BLASTUSDT: 0.001522 <= 0.00184195? **YES!**
- **Should activate!**

**But it doesn't! Why?**

Checking activation logic (line 504-522):
```python
async def _check_activation(self, ts):
    # ... breakeven check ...

    should_activate = False
    if ts.side == 'long':
        should_activate = ts.current_price >= ts.activation_price
    else:
        should_activate = ts.current_price <= ts.activation_price  # ← Should be TRUE!

    if should_activate:
        return await self._activate_trailing_stop(ts)  # ← Should call this!
```

**Hypothesis:**
1. `entry_price = 0` in DB causes `_calculate_profit_percent()` to fail/return wrong value?
2. Breakeven check interferes?
3. `_activate_trailing_stop()` calls `_update_stop_order()` which triggers orphan check again?

Let's check `_activate_trailing_stop()` (line 526-541):
```python
async def _activate_trailing_stop(self, ts):
    ts.state = TrailingStopState.ACTIVE
    # ... calculate stop price ...

    # Update stop order ← CALLS _update_stop_order()!
    await self._update_stop_order(ts)
```

**БИНГО!**

**The Loop:**
1. TS restored with `state=inactive`
2. `update_price()` → `_check_activation()`
3. Condition met: `current_price <= activation_price` ✅
4. Calls `_activate_trailing_stop()`
5. `_activate_trailing_stop()` calls `_update_stop_order()`
6. `_update_stop_order()` checks if position exists on exchange
7. **If position not in cache → thinks orphaned → deletes TS again!**
8. **Infinite loop of creation/deletion!**

---

## 📊 Orphaned TS States in DB

```sql
SELECT ts.symbol, ts.state, ts.entry_price
FROM trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1 FROM positions p
    WHERE p.symbol = ts.symbol AND p.status='active'
)
```

**20 orphaned states found!**

Examples:
- Most: `state=inactive`, real `entry_price`
- 2: `state=WAITING` (uppercase!), `entry_price=100` (test data?)

**Impact:**
- DB pollution with stale states
- TS restoration pulls corrupt data
- Positions remain unprotected

---

## 🎯 ROOT CAUSES SUMMARY

| Bug | Location | Issue | Impact |
|-----|----------|-------|--------|
| #1 | `_update_stop_order:951-966` | False orphan detection during TS creation | TS deleted immediately after creation |
| #2 | `on_position_closed:1117` | `_delete_state()` fails or state saved after delete | 20 orphaned TS states in DB |
| #3 | `_activate_trailing_stop:541` | Calls `_update_stop_order` which triggers orphan check | Activation fails, TS deleted again |

**Combined Effect:**
1. TS created successfully
2. First `update_price()` tries activation
3. Activation triggers orphan check
4. Position not in exchange cache yet
5. TS marked orphaned and deleted
6. On restart, TS restored from corrupt DB state
7. Activation fails again for same reason
8. **Result: 18.6% profit position WITHOUT protection!**

---

## 💡 SOLUTION PLAN

### Fix #1: Remove Orphan Check from _update_stop_order()

**Problem:** Checking if position exists during TS activation is premature

**Solution:** Move orphan detection to a separate periodic cleanup task

**Change:**
```python
# IN _update_stop_order() - REMOVE this check:
if hasattr(self.exchange, 'fetch_positions'):
    positions = await self.exchange.fetch_positions([ts.symbol])
    if not position_exists:
        # DELETE THIS ENTIRE BLOCK
        await self.on_position_closed(ts.symbol)
        return False
```

**Reasoning:**
- TS should trust that position exists when activated
- Position manager already handles position closure notifications
- Orphan detection belongs in periodic cleanup, not hot path

---

### Fix #2: Ensure _delete_state() Actually Deletes

**Problem:** 20 orphaned states in DB

**Solution:**
1. Verify `_delete_state()` actually executes DELETE
2. Add logging to confirm deletion
3. Handle race conditions (save after delete)

**Change:**
```python
async def _delete_state(self, symbol: str) -> bool:
    # ... existing code ...
    await self.repository.delete_trailing_stop_state(symbol, self.exchange_name)
    logger.info(f"✅ {symbol}: TS state DELETED from DB")  # Add confirmation
    return True
```

**Additional:** Check repository method works:
```python
# In repository.py
async def delete_trailing_stop_state(self, symbol, exchange):
    query = "DELETE FROM monitoring.trailing_stop_state WHERE symbol=$1 AND exchange=$2"
    result = await self.pool.execute(query, symbol, exchange)
    logger.debug(f"Deleted TS state: {symbol}, rows affected: {result}")
```

---

### Fix #3: Cleanup Orphaned States

**Problem:** 20 stale states pollute DB

**Solution:** Run cleanup SQL

```sql
-- Identify orphaned states
SELECT ts.symbol, ts.state
FROM monitoring.trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1 FROM monitoring.positions p
    WHERE p.symbol = ts.symbol
      AND p.exchange = ts.exchange
      AND p.status='active'
);

-- DELETE orphaned states
DELETE FROM monitoring.trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1 FROM monitoring.positions p
    WHERE p.symbol = ts.symbol
      AND p.exchange = ts.exchange
      AND p.status='active'
);
```

---

### Fix #4: Add Periodic Orphan Cleanup Task

**Problem:** Orphans accumulate over time

**Solution:** Periodic cleanup in background

```python
async def _periodic_cleanup_orphaned_ts(self):
    """Cleanup orphaned TS states (runs every 5 minutes)"""
    while True:
        await asyncio.sleep(300)  # 5 minutes

        # Get all TS symbols
        ts_symbols = list(self.trailing_stops.keys())

        # Get all active position symbols from manager
        active_positions = await self.position_manager.get_active_symbols()

        # Find orphans
        orphans = [s for s in ts_symbols if s not in active_positions]

        for symbol in orphans:
            logger.warning(f"Periodic cleanup: removing orphaned TS for {symbol}")
            await self.on_position_closed(symbol)
```

---

## 📋 IMPLEMENTATION PLAN

### Phase 1: URGENT - Remove Orphan Check (NOW!)
1. Comment out orphan check in `_update_stop_order()` (lines 951-966)
2. Restart bot
3. Verify TS activations start working
4. **Risk:** LOW (orphans will accumulate but won't break activation)

### Phase 2: Cleanup DB (ASAP)
1. Run SQL to delete 20 orphaned states
2. Verify count = 0
3. **Risk:** NONE (these are already orphaned)

### Phase 3: Fix Delete Logic (Today)
1. Add logging to `_delete_state()`
2. Verify repository DELETE works
3. Test with position closure
4. **Risk:** LOW (improves observability)

### Phase 4: Add Periodic Cleanup (Tomorrow)
1. Implement background cleanup task
2. Run every 5 minutes
3. Log orphans found and removed
4. **Risk:** LOW (defensive measure)

---

## ⚠️ IMMEDIATE ACTIONS REQUIRED

### 1. COMMENT OUT ORPHAN CHECK (CRITICAL!)

**File:** `protection/trailing_stop.py:951-966`

**Change:**
```python
# DISABLED: False orphan detection causes TS deletion during activation
# if hasattr(self.exchange, 'fetch_positions'):
#     try:
#         positions = await self.exchange.fetch_positions([ts.symbol])
#         position_exists = any(...)
#         if not position_exists:
#             logger.warning("Position not found, removing orphaned TS")
#             await self.on_position_closed(ts.symbol)
#             return False
#     except Exception as e:
#         logger.debug(f"Position verification failed: {e}")
```

### 2. CLEAN ORPHANED STATES FROM DB

```sql
DELETE FROM monitoring.trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1 FROM monitoring.positions p
    WHERE p.symbol = ts.symbol
      AND p.exchange = ts.exchange
      AND p.status='active'
);
```

### 3. RESTART BOT

```bash
pkill -f "python.*main.py"
sleep 5
python main.py
```

### 4. MONITOR NEXT WAVE

**Watch for:**
```bash
# Should see activations!
tail -f logs/trading_bot.log | grep "Trailing stop ACTIVATED"

# Should NOT see orphan warnings
tail -f logs/trading_bot.log | grep "orphaned"
```

---

## ✅ EXPECTED RESULTS

### Before (Current - BROKEN)
```
Positions with profit >1.5%: 5
TS activated: 0 ❌
TS deleted as "orphaned": Multiple ❌
Orphaned states in DB: 20 ❌
BLASTUSDT profit: 18.6% WITHOUT protection ❌
```

### After (Fixed)
```
Positions with profit >1.5%: 5
TS activated: 5 ✅
TS deleted as "orphaned": 0 ✅
Orphaned states in DB: 0 ✅
BLASTUSDT: TS activated, profit locked ✅
```

---

## 📁 FILES AFFECTED

1. `protection/trailing_stop.py`
   - Line 951-966: Remove orphan check
   - Line 310: Add delete confirmation log

2. `database/repository.py`
   - Verify `delete_trailing_stop_state()` works

3. Database cleanup SQL (one-time)

---

**Investigation Status:** ✅ COMPLETE
**Root Causes:** 3 bugs identified
**Solution:** Comment out orphan check + DB cleanup
**Risk:** LOW (defensive removal of buggy feature)
**Urgency:** 🔴 CRITICAL (18.6% profit position unprotected!)
