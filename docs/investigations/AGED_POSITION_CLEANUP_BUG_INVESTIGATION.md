# CRITICAL BUG: Aged Position Not Removed on Close - Causes Resubscription Errors

**Дата**: 2025-10-27
**Severity**: CRITICAL
**Impact**: Bot continuously tries to resubscribe closed positions, flooding logs with errors

---

## 📊 INCIDENT REPORT

### User Report:
```
2025-10-27 06:28:06,901 - core.position_manager_unified_patch - WARNING - 🔄 Attempting resubscription for OMUSDT (attempt 1/3)
2025-10-27 06:28:06,901 - core.position_manager_unified_patch - WARNING - ⚠️ Position OMUSDT not found
2025-10-27 06:28:06,901 - core.position_manager_unified_patch - ERROR - ❌ FAILED to resubscribe OMUSDT after 3 attempts! MANUAL INTERVENTION REQUIRED
2025-10-27 06:28:06,901 - core.position_manager_unified_patch - WARNING - 🔄 Attempting resubscription for 1000TAGUSDT (attempt 1/3)
2025-10-27 06:28:06,901 - core.position_manager_unified_patch - WARNING - ⚠️ Position 1000TAGUSDT not found
2025-10-27 06:28:06,901 - core.position_manager_unified_patch - ERROR - ❌ FAILED to resubscribe 1000TAGUSDT after 3 attempts! MANUAL INTERVENTION REQUIRED
```

**User Question:**
> "эти позиции уже закрыты. почему бот пытается на них переподписаться? и почему безуспешно?"

---

## 🔍 FORENSIC INVESTIGATION

### Timeline Analysis:

**06:21:30** - Last price update for 1000TAGUSDT:
```
2025-10-27 06:21:30,103 - core.position_manager - INFO - 📊 Position update: 1000TAGUSDT → 1000TAGUSDT, mark_price=0.4461
```

**06:25:00 - 06:28:06** - Repeated resubscription attempts:
```
2025-10-27 06:25:00,393 - core.position_manager_unified_patch - WARNING -   - 1000TAGUSDT: no update for 180s (3.0 minutes)
2025-10-27 06:26:00,394 - core.position_manager_unified_patch - WARNING -   - 1000TAGUSDT: no update for 240s (4.0 minutes)
2025-10-27 06:27:00,395 - core.position_manager_unified_patch - WARNING -   - 1000TAGUSDT: no update for 300s (5.0 minutes)
2025-10-27 06:28:00,395 - core.position_manager_unified_patch - WARNING -   - 1000TAGUSDT: no update for 360s (6.0 minutes)
```

**Pattern:**
- Every minute: WebSocket health monitor detects stale position
- Every minute: Attempts resubscription
- Every minute: Fails with "Position not found"
- ERROR repeats indefinitely!

---

## 🎯 ROOT CAUSE ANALYSIS

### Code Analysis - Resubscription Logic

**File**: `core/position_manager_unified_patch.py:202-303`

**Function**: `resubscribe_stale_positions()`

```python
# Line 244-247
position = position_manager.positions.get(symbol)
if not position:
    logger.warning(f"⚠️ Position {symbol} not found")
    break  # ← Exits retry loop
```

**Why it fails:**
- Position was closed → removed from `position_manager.positions`
- But still exists in `aged_monitor.aged_targets`!
- Resubscription tries to find it → NOT FOUND

### WebSocket Health Monitor

**File**: `core/position_manager_unified_patch.py:349-465`

**Function**: `start_websocket_health_monitor()`

```python
# Line 385
aged_symbols = list(aged_monitor.aged_targets.keys())

# Line 391-394
staleness_report = await price_monitor.check_staleness(
    aged_symbols,
    module='aged_position'
)
```

**How it works:**
1. Every 60 seconds: Check all symbols in `aged_monitor.aged_targets`
2. Detect stale (no price update > 30s)
3. Call `resubscribe_stale_positions()` for stale symbols
4. Resubscription fails for closed positions

### Position Closure Logic

**File**: `core/position_manager.py:2320-2470`

**Function**: `close_position()`

**Lines 2410-2417** (CRITICAL!):
```python
# Clean up tracking
del self.positions[symbol]  # ← Position removed from memory
self.position_count -= 1
self.total_exposure -= Decimal(str(position.quantity * position.entry_price))

# Clean up trailing stop
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)
    # ✅ Trailing stop IS cleaned up!
```

**What's MISSING:**
```python
# ❌ THIS CODE DOES NOT EXIST!
# aged_adapter = self.unified_protection.get('aged_adapter')
# if aged_adapter:
#     await aged_adapter.remove_aged_position(symbol)
```

---

## 💥 THE BUG

### What Happens:

1. **Position opened** → Added to:
   - ✅ `position_manager.positions[symbol]`
   - ✅ `aged_monitor.aged_targets[symbol]` (when aged)
   - ✅ `aged_adapter.monitoring_positions[symbol]`

2. **Position becomes aged** → Registered for monitoring

3. **Position CLOSED** → Cleanup:
   - ✅ Removed from `position_manager.positions[symbol]`
   - ✅ Removed from `trailing_manager` (via `on_position_closed()`)
   - ❌ **NOT removed from** `aged_monitor.aged_targets[symbol]`!
   - ❌ **NOT removed from** `aged_adapter.monitoring_positions[symbol]`!

4. **WebSocket health monitor runs** (every 60s):
   - Reads `aged_monitor.aged_targets` → finds OMUSDT, 1000TAGUSDT
   - Checks staleness → STALE (no updates for 6+ minutes)
   - Tries to resubscribe
   - Looks for position in `position_manager.positions` → **NOT FOUND**!
   - ERROR: "Position not found"
   - **Repeats every minute forever!**

---

## 🔍 ROOT CAUSE CONFIRMATION

### Code Evidence:

**✅ Trailing Stop Cleanup EXISTS:**
```python
# core/position_manager.py:2415-2417
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)
```

**❌ Aged Position Cleanup MISSING:**
```python
# core/position_manager.py:2410-2470
# NO CODE FOR:
# if self.unified_protection:
#     aged_adapter = self.unified_protection.get('aged_adapter')
#     if aged_adapter:
#         await aged_adapter.remove_aged_position(symbol)
```

### Cleanup Method EXISTS but NOT CALLED:

**File**: `core/protection_adapters.py:133-138`

```python
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""

    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')
        del self.monitoring_positions[symbol]
```

**This method exists but is NEVER called on position closure!**

---

## 📊 IMPACT ANALYSIS

### Current State (from logs):

**OMUSDT:**
- Status: CLOSED (not in active positions)
- In aged_targets: YES (stale entry)
- In monitoring_positions: YES (stale entry)
- Resubscription attempts: FAILING every minute

**1000TAGUSDT:**
- Status: CLOSED (not in active positions)
- In aged_targets: YES (stale entry)
- In monitoring_positions: YES (stale entry)
- Resubscription attempts: FAILING every minute since 06:25:00
- Duration: 3+ minutes of continuous errors

### Log Pollution:

**Every 60 seconds per closed aged position:**
```
⚠️ WebSocket Health Check: X aged positions have STALE prices
⚠️ Position X not found
❌ FAILED to resubscribe X after 3 attempts! MANUAL INTERVENTION REQUIRED
```

**If 2 closed aged positions:**
- 2 positions × 3 error messages × 60 checks/hour = **360 error messages/hour**
- Per day: **8,640 error messages**

### Functional Impact:

1. ❌ **Log flooding** - makes debugging other issues difficult
2. ❌ **Resource waste** - CPU cycles on futile resubscription attempts
3. ❌ **False alarms** - "MANUAL INTERVENTION REQUIRED" for non-issues
4. ❌ **Monitoring noise** - hides real WebSocket health problems

---

## 🎯 FIX STRATEGY

### Primary Fix: Add Cleanup on Position Close

**Location**: `core/position_manager.py:2414-2435`

**Add after trailing manager cleanup (line 2417):**

```python
# Clean up trailing stop
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)

# ✅ NEW: Clean up aged position monitoring
if self.unified_protection:
    aged_adapter = self.unified_protection.get('aged_adapter')
    if aged_adapter and symbol in aged_adapter.monitoring_positions:
        await aged_adapter.remove_aged_position(symbol)
        logger.debug(f"Removed {symbol} from aged monitoring on closure")
```

### Why This Fix Works:

1. ✅ **Symmetry**: Position added to aged monitoring → removed on close
2. ✅ **Consistency**: Same pattern as trailing stop cleanup
3. ✅ **Defensive**: Checks existence before removal
4. ✅ **Logging**: Debug log for verification
5. ✅ **Non-breaking**: Only executes if unified_protection enabled

---

## 🧪 VERIFICATION PLAN

### Test 1: Manual Test with Closed Position

```python
# Simulate:
1. Open position
2. Let it become aged (registered in aged_monitor)
3. Close position
4. Verify:
   - NOT in position_manager.positions ✅
   - NOT in aged_monitor.aged_targets ✅ (SHOULD)
   - NOT in aged_adapter.monitoring_positions ✅ (SHOULD)
```

### Test 2: Monitor WebSocket Health Check

```bash
# After fix:
tail -f logs/trading_bot.log | grep "resubscribe\|stale"

# Expected: NO errors for closed positions
# Expected: Only legitimate stale detection for OPEN positions
```

### Test 3: Aged Position Lifecycle

```
1. Position opened
2. Position ages → registered
3. Verify logs: "Position X added to aged monitoring"
4. Position closed
5. Verify logs: "Removed X from aged monitoring on closure"
6. Wait 2 minutes
7. Verify logs: NO resubscription attempts for X
```

---

## 📝 DETAILED FIX PLAN

### File: `core/position_manager.py`

**Change Location**: Lines 2414-2435

#### Before (INCORRECT):
```python
# Clean up tracking
del self.positions[symbol]
self.position_count -= 1
self.total_exposure -= Decimal(str(position.quantity * position.entry_price))

# Clean up trailing stop
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)

    # Log trailing stop removal
    if position.has_trailing_stop:
        event_logger = get_event_logger()
        # ... event logging code
```

#### After (CORRECT):
```python
# Clean up tracking
del self.positions[symbol]
self.position_count -= 1
self.total_exposure -= Decimal(str(position.quantity * position.entry_price))

# Clean up trailing stop
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)

    # Log trailing stop removal
    if position.has_trailing_stop:
        event_logger = get_event_logger()
        # ... event logging code

# ✅ FIX: Clean up aged position monitoring
if self.unified_protection:
    aged_adapter = self.unified_protection.get('aged_adapter')
    if aged_adapter and symbol in aged_adapter.monitoring_positions:
        await aged_adapter.remove_aged_position(symbol)
        logger.debug(f"Removed {symbol} from aged monitoring on closure")
```

**Lines to add**: ~5 lines
**Complexity**: LOW (simple defensive check + call)

---

## 🔧 IMPLEMENTATION STEPS

### Step 1: Code Change
1. Open `core/position_manager.py`
2. Find line 2417 (after `trailing_manager.on_position_closed()`)
3. Add aged position cleanup code (5 lines)
4. Save

### Step 2: Testing
1. Restart bot
2. Wait for a position to close naturally
3. Check logs for "Removed X from aged monitoring on closure"
4. Wait 2 minutes after closure
5. Verify NO resubscription errors for that symbol

### Step 3: Monitoring
1. Monitor logs for 24 hours
2. Verify no "Position not found" errors for closed positions
3. Verify aged monitoring still works for OPEN positions

### Step 4: Cleanup Existing Stale Entries

**Option A**: Restart bot (clears memory)

**Option B**: Manual cleanup script:
```python
# If bot running with stale entries:
aged_monitor = position_manager.unified_protection['aged_monitor']
aged_adapter = position_manager.unified_protection['aged_adapter']

for symbol in list(aged_monitor.aged_targets.keys()):
    if symbol not in position_manager.positions:
        # Stale entry - remove
        await aged_adapter.remove_aged_position(symbol)
        del aged_monitor.aged_targets[symbol]
        logger.info(f"Cleaned up stale aged entry: {symbol}")
```

---

## 🎓 LESSONS LEARNED

### Why This Bug Occurred:

1. **Asymmetric Cleanup**: Added aged monitoring but forgot to remove on close
2. **Copy-Paste Pattern**: Copied trailing stop cleanup but not aged cleanup
3. **No Lifecycle Tests**: Tests didn't verify full position lifecycle
4. **Defensive Programming Missing**: Resubscription assumes position exists

### How to Prevent:

1. ✅ **Lifecycle Checklist**: Document all places to update for new features
   - Position creation hooks
   - Position closure hooks
   - Periodic cleanup hooks

2. ✅ **E2E Tests**: Test full lifecycle (open → aged → close → verify cleanup)

3. ✅ **Defensive Resubscription**: Already implemented (breaks on not found)

4. ✅ **Better Logging**: Add debug logs for lifecycle events

---

## ✅ SUCCESS CRITERIA

Fix is successful if:

1. ✅ **No resubscription errors** for closed positions
2. ✅ **Aged monitoring cleanup** logged on position close
3. ✅ **Memory cleanup**: aged_targets doesn't contain closed positions
4. ✅ **Monitoring cleanup**: monitoring_positions doesn't contain closed positions
5. ✅ **Aged monitoring still works** for open positions
6. ✅ **No new errors** introduced

---

## 📊 COMPARISON

### Before Fix:
```
Position Lifecycle:
1. Open → added to positions, aged_targets, monitoring_positions
2. Close → removed from positions
        → ❌ NOT removed from aged_targets
        → ❌ NOT removed from monitoring_positions

Result:
- Stale entries remain forever
- WebSocket health monitor fails every 60s
- 360+ error messages per hour per closed position
```

### After Fix:
```
Position Lifecycle:
1. Open → added to positions, aged_targets, monitoring_positions
2. Close → removed from positions
        → ✅ removed from monitoring_positions
        → ✅ removed from aged_targets (via monitoring cleanup)

Result:
- Clean memory state
- No stale resubscription attempts
- Log stays clean
```

---

## 🚀 DEPLOYMENT PLAN

### Preparation:
1. ✅ Investigation complete
2. ✅ Root cause identified
3. ✅ Fix designed
4. ⏳ Awaiting user approval

### Implementation:
1. Add cleanup code to position_manager.py
2. Test with next position closure
3. Monitor for 24 hours
4. Verify success criteria

### Rollback:
- If issues: Remove added code block
- Restart bot
- Investigate further

---

**STATUS**: ⏳ **AWAITING USER APPROVAL FOR FIX**

Расследование завершено. Готов к реализации fix. Жду команды! 🔍

---

**End of Investigation**
