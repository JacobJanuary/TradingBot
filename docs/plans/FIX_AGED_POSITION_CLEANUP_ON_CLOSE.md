# FIX PLAN: Aged Position Cleanup on Close

**Дата**: 2025-10-27
**Priority**: CRITICAL
**Complexity**: LOW (5 lines)
**Risk**: LOW (defensive implementation)

---

## 📊 PROBLEM STATEMENT

**Issue**: Closed positions remain in aged monitoring, causing continuous resubscription errors

**Symptoms**:
```
❌ FAILED to resubscribe OMUSDT after 3 attempts! MANUAL INTERVENTION REQUIRED
❌ FAILED to resubscribe 1000TAGUSDT after 3 attempts! MANUAL INTERVENTION REQUIRED
```

**Root Cause**: `position_manager.close_position()` does NOT call `aged_adapter.remove_aged_position()`

**Impact**:
- 360+ error messages/hour per closed aged position
- Log pollution
- False alarms
- Resource waste

---

## 🎯 FIX OBJECTIVE

Add aged position cleanup to `close_position()` method, mirroring existing trailing stop cleanup.

---

## 📝 DETAILED FIX

### File: `core/position_manager.py`

**Location**: Lines 2414-2435 (after trailing stop cleanup)

### Change:

#### Before (MISSING CLEANUP):
```python
# Clean up trailing stop
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)

    # Log trailing stop removal
    if position.has_trailing_stop:
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.TRAILING_STOP_REMOVED,
                # ... rest of event logging
            )

logger.info(
    f"Position closed: {symbol} {reason} "
    f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
)
```

#### After (WITH CLEANUP):
```python
# Clean up trailing stop
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)

    # Log trailing stop removal
    if position.has_trailing_stop:
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.TRAILING_STOP_REMOVED,
                # ... rest of event logging
            )

# ✅ FIX: Clean up aged position monitoring
if self.unified_protection:
    aged_adapter = self.unified_protection.get('aged_adapter')
    if aged_adapter and symbol in aged_adapter.monitoring_positions:
        await aged_adapter.remove_aged_position(symbol)
        logger.debug(f"Removed {symbol} from aged monitoring on closure")

logger.info(
    f"Position closed: {symbol} {reason} "
    f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
)
```

### Code to Add:

```python
# ✅ FIX: Clean up aged position monitoring
if self.unified_protection:
    aged_adapter = self.unified_protection.get('aged_adapter')
    if aged_adapter and symbol in aged_adapter.monitoring_positions:
        await aged_adapter.remove_aged_position(symbol)
        logger.debug(f"Removed {symbol} from aged monitoring on closure")
```

**Insert after**: Line 2435 (after trailing stop event logging)
**Insert before**: Line 2437 (before final logger.info)

**Lines added**: 5
**Complexity**: LOW

---

## 🔍 WHY THIS FIX WORKS

### 1. **Defensive Checks**:
```python
if self.unified_protection:  # ← Only if feature enabled
    aged_adapter = self.unified_protection.get('aged_adapter')  # ← Safe get
    if aged_adapter and symbol in aged_adapter.monitoring_positions:  # ← Check exists
        await aged_adapter.remove_aged_position(symbol)
```

**Safety**:
- ✅ Won't break if unified_protection disabled
- ✅ Won't error if aged_adapter missing
- ✅ Won't error if position not monitored
- ✅ Idempotent (safe to call multiple times)

### 2. **Symmetry with Existing Code**:

**Pattern already used for trailing stop**:
```python
if trailing_manager:
    await trailing_manager.on_position_closed(...)
```

**Same pattern for aged monitoring**:
```python
if aged_adapter:
    await aged_adapter.remove_aged_position(...)
```

### 3. **Leverages Existing Method**:

**Method exists**: `core/protection_adapters.py:133-138`
```python
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""
    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')
        del self.monitoring_positions[symbol]
```

**Already tested and working** (used in resubscription logic)

---

## ✅ VERIFICATION PLAN

### Test 1: Immediate Verification

**After code change:**
```bash
# Restart bot
# Wait for next position closure
tail -f logs/trading_bot.log | grep "Removed.*from aged monitoring"
```

**Expected output when position closes:**
```
DEBUG - Removed SYMBOLUSDT from aged monitoring on closure
```

### Test 2: No Resubscription Errors

**After position closes:**
```bash
# Wait 2 minutes (past stale threshold)
tail -f logs/trading_bot.log | grep "resubscribe.*SYMBOL"
```

**Expected**: NO resubscription attempts for closed symbol

### Test 3: Memory Verification

**Check internal state** (if accessible):
```python
# Symbol should NOT be in:
aged_monitor.aged_targets  # Should be empty for closed position
aged_adapter.monitoring_positions  # Should be empty for closed position
position_manager.positions  # Should be empty for closed position (already working)
```

### Test 4: Aged Monitoring Still Works

**For OPEN aged positions:**
```bash
tail -f logs/trading_bot.log | grep "aged.*position"
```

**Expected**:
- ✅ Open aged positions still monitored
- ✅ Price updates received
- ✅ Targets checked
- ✅ No errors

---

## 🚨 RISK ANALYSIS

### Risk 1: Breaking Aged Monitoring

**Description**: Fix might break aged position monitoring for open positions

**Likelihood**: VERY LOW

**Mitigation**:
- Defensive checks (only removes if exists)
- Mirrors existing trailing stop pattern (proven stable)
- Uses existing tested method

**Test**: Verify aged monitoring works for open positions

### Risk 2: Remove Called Twice

**Description**: Position might be removed twice (race condition)

**Likelihood**: LOW

**Mitigation**:
- `remove_aged_position()` checks existence before deletion
- Idempotent operation (safe to call multiple times)

**Code evidence**:
```python
if symbol in self.monitoring_positions:  # ← Protects against double removal
    await self.price_monitor.unsubscribe(symbol, 'aged_position')
    del self.monitoring_positions[symbol]
```

### Risk 3: unified_protection None

**Description**: unified_protection might not be initialized

**Likelihood**: LOW (already used elsewhere in code)

**Mitigation**:
```python
if self.unified_protection:  # ← Explicit None check
```

**Test**: Verify works when USE_UNIFIED_PROTECTION=false

---

## 📋 IMPLEMENTATION CHECKLIST

### Pre-Implementation:
- [x] Investigation complete
- [x] Root cause identified
- [x] Fix designed
- [x] Verification plan created
- [ ] User approval obtained

### Implementation:
- [ ] Open `core/position_manager.py`
- [ ] Navigate to line 2435 (after trailing stop event logging)
- [ ] Add 5-line cleanup code block
- [ ] Save file
- [ ] Restart bot

### Post-Implementation:
- [ ] Test 1: Verify debug log on position close
- [ ] Test 2: No resubscription errors (2 min wait)
- [ ] Test 3: Aged monitoring works for open positions
- [ ] Monitor logs for 24 hours
- [ ] Verify success criteria met

---

## 🎯 SUCCESS CRITERIA

Fix is successful if **ALL** criteria met:

1. ✅ **Cleanup logged**: `"Removed X from aged monitoring on closure"` appears in logs
2. ✅ **No resubscription errors**: No "Position not found" for closed positions
3. ✅ **Memory clean**: Closed positions not in aged_targets or monitoring_positions
4. ✅ **Aged monitoring works**: Open aged positions still monitored correctly
5. ✅ **No new errors**: No regressions introduced
6. ✅ **24h stability**: Bot runs without issues for 24 hours

---

## 🔧 EXACT CODE CHANGE

### Location:
```
File: core/position_manager.py
Method: close_position()
Lines: After 2435, before 2437
```

### Insert this block:

```python
                # ✅ FIX: Clean up aged position monitoring
                if self.unified_protection:
                    aged_adapter = self.unified_protection.get('aged_adapter')
                    if aged_adapter and symbol in aged_adapter.monitoring_positions:
                        await aged_adapter.remove_aged_position(symbol)
                        logger.debug(f"Removed {symbol} from aged monitoring on closure")
```

### Context (for accurate placement):

```python
                    # Log trailing stop removal
                    if position.has_trailing_stop:
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.TRAILING_STOP_REMOVED,
                                {
                                    'symbol': symbol,
                                    'position_id': position.id,
                                    'reason': 'position_closed',
                                    'realized_pnl': float(realized_pnl)
                                },
                                position_id=position.id,
                                symbol=symbol,
                                exchange=position.exchange,
                                severity='INFO'
                            )

                # ← INSERT NEW CODE HERE ←

                logger.info(
                    f"Position closed: {symbol} {reason} "
                    f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
                )
```

---

## 🎓 FOLLOW-UP IMPROVEMENTS (Optional)

### 1. Also Remove from aged_monitor.aged_targets

**Currently**: `remove_aged_position()` only removes from `monitoring_positions`

**Enhancement**:
```python
# In protection_adapters.py:133-138
async def remove_aged_position(self, symbol: str):
    """Remove position from aged monitoring"""
    if symbol in self.monitoring_positions:
        await self.price_monitor.unsubscribe(symbol, 'aged_position')
        del self.monitoring_positions[symbol]

        # ✅ ENHANCEMENT: Also remove from aged_monitor
        if self.aged_monitor and symbol in self.aged_monitor.aged_targets:
            del self.aged_monitor.aged_targets[symbol]
```

**Benefit**: More thorough cleanup
**Risk**: LOW (defensive checks)
**Priority**: MEDIUM (not critical for fix)

### 2. Periodic Cleanup Task

**Add background task** to clean stale entries:
```python
async def periodic_aged_cleanup():
    while True:
        await asyncio.sleep(3600)  # Every hour

        for symbol in list(aged_monitor.aged_targets.keys()):
            if symbol not in position_manager.positions:
                # Stale entry
                await aged_adapter.remove_aged_position(symbol)
                logger.warning(f"Cleaned up stale aged entry: {symbol}")
```

**Benefit**: Defensive fallback
**Risk**: LOW
**Priority**: LOW (primary fix should prevent need)

### 3. Add Cleanup to Other Closure Paths

**Check these methods** also close positions:
- `_handle_stop_loss_hit()`
- `_handle_take_profit_hit()`
- `handle_aged_position_close()`

**Action**: Verify they all call `close_position()` (and thus get cleanup)

---

## 🚀 DEPLOYMENT STEPS

### Step 1: Code Change (5 minutes)
```bash
# 1. Navigate to code
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# 2. Open file
# Edit core/position_manager.py

# 3. Find line 2435
# Add cleanup code block

# 4. Save
```

### Step 2: Restart Bot (2 minutes)
```bash
# Stop current bot
pkill -f "python main.py"

# Start bot
python main.py &

# Monitor startup
tail -f logs/trading_bot.log
```

### Step 3: Verification (2-24 hours)
```bash
# Immediate: Watch for position closures
tail -f logs/trading_bot.log | grep "Removed.*from aged monitoring"

# 2 minutes after closure: Verify no resubscription errors
tail -f logs/trading_bot.log | grep "resubscribe\|FAILED"

# 24 hours: Long-term stability
# Check logs daily for any issues
```

---

## 📊 EXPECTED OUTCOMES

### Before Fix:
```
Position Closes:
- Removed from positions ✅
- Trailing stop cleaned ✅
- Aged monitoring NOT cleaned ❌

Every 60 seconds after:
- WebSocket health check detects stale
- Attempts resubscription
- ERROR: "Position not found"
- Floods logs with errors

Accumulation:
- 2 closed aged positions
- 360 errors/hour
- 8,640 errors/day
```

### After Fix:
```
Position Closes:
- Removed from positions ✅
- Trailing stop cleaned ✅
- Aged monitoring cleaned ✅ (NEW!)
- Debug log: "Removed X from aged monitoring" ✅

Every 60 seconds after:
- WebSocket health check runs
- Only checks OPEN aged positions
- No errors
- Clean logs ✅

Result:
- Zero stale resubscription errors
- Clean memory state
- Happy logs
```

---

## ✅ FINAL CHECKLIST

Before marking complete:

- [ ] Code change implemented
- [ ] Bot restarted
- [ ] First position closed after fix
- [ ] Debug log confirmed: "Removed X from aged monitoring"
- [ ] 2 min wait passed
- [ ] No resubscription errors for closed position
- [ ] Aged monitoring still works for open positions
- [ ] 24 hours stability verified
- [ ] Success criteria all met
- [ ] Investigation document updated with results

---

**STATUS**: ⏳ **READY FOR IMPLEMENTATION**

Готов реализовывать fix. Все детали расписаны. Жду команды пользователя! 🔧

---

**End of Plan**
