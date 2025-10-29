# AGED POSITION + TRAILING STOP CONFLICT - AUDIT REPORT
**Date**: 2025-10-26 23:39 UTC
**Priority**: P0 - CRITICAL
**Status**: 🔴 ACTIVE BUG
**Affected Symbol**: IDEXUSDT (and potentially others)

---

## Executive Summary

**CRITICAL BUG FOUND**: Aged positions with active trailing stops are SKIPPED from aged position monitoring, preventing breakeven closes for old profitable positions.

**Impact**: Positions that are 6+ hours old and profitable are NOT closed at breakeven because trailing_activated=True causes them to be skipped.

**Root Cause**: Line 1065-1067 in `core/aged_position_monitor_v2.py:periodic_full_scan()`

---

## Problem Statement

User reported: **IDEXUSDT opened 6+ hours ago, currently profitable, but NOT closing at breakeven**

Expected behavior:
- Position aged > 6 hours
- Position profitable (breakeven or above)
- Should close immediately at market price

Actual behavior:
- Position NOT monitored by aged position system
- Waiting for trailing stop to trigger (may never happen if price doesn't move enough)

---

## Investigation Timeline

### 1. Periodic Scan Frequency ✅
**Question**: How often are aged positions checked?

**Finding**:
- Periodic scan runs every 5 minutes (interval configured correctly)
- Last successful scan: 21:10:36
- Bot restarted at: 21:40:12, 22:47:58
- **NO scans after restart** (different issue - sleep before first scan)

**Code Location**:
- `core/position_manager_unified_patch.py:148-183`
- Line 169: `await asyncio.sleep(interval_minutes * 60)` - BEFORE first call

**Impact**: First scan after restart delayed by 5 minutes

---

### 2. Trailing Stop Status ✅
**Question**: Does IDEXUSDT have trailing stop active?

**Finding**: YES
```
2025-10-26 23:35:40 - TS symbols in memory: [...'IDEXUSDT'...]
```

IDEXUSDT is in trailing stop manager, meaning `trailing_activated=True`

---

### 3. Aged Position Skip Logic 🔴
**Question**: Why isn't IDEXUSDT detected as aged position?

**Finding**: CRITICAL BUG FOUND

**File**: `core/aged_position_monitor_v2.py`
**Function**: `periodic_full_scan()`
**Lines**: 1065-1067

```python
# Skip if trailing stop is active
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    continue  # ❌ BUG: This skips ALL positions with trailing stop!
```

**Impact**:
- ANY position with `trailing_activated=True` is SKIPPED from aged monitoring
- Even if position is 6+ hours old and profitable
- Even if position should close at breakeven per aged logic

---

### 4. Breakeven Close Logic ✅
**Question**: Does the close logic work when position IS monitored?

**Finding**: YES, logic is correct

**File**: `core/aged_position_monitor_v2.py`
**Function**: `check_price_target()`
**Lines**: 419-422

```python
if pnl_percent > Decimal('0'):
    # Profitable - close immediately
    should_close = True
    logger.info(f"💰 {symbol} profitable at {pnl_percent:.2f}% - triggering close")
```

**Conclusion**: The close logic works correctly IF position is added to aged monitoring. Problem is positions with trailing stops are never added.

---

## Root Cause Analysis

### The Conflict

**Trailing Stop Manager**:
- Activates when position becomes profitable
- Sets `trailing_activated=True`
- Manages trailing stop orders
- May take a long time to trigger (or never trigger if price consolidates)

**Aged Position Manager**:
- Monitors positions older than 6 hours
- Should close profitable aged positions at breakeven IMMEDIATELY
- **BUG**: Skips positions with `trailing_activated=True`

### The Logic Error

Original intent (presumably):
- "Don't add aged monitoring if trailing stop will handle it"

Reality:
- Trailing stop may NEVER trigger (price consolidation, low volatility)
- Position stays open indefinitely even if 6+ hours old and profitable
- User expectation: Close at breakeven after 6 hours (regardless of trailing stop)

---

## Evidence: IDEXUSDT Case

### Facts:
1. ✅ IDEXUSDT opened 6+ hours ago (before 17:39 UTC, now 23:39 UTC)
2. ✅ IDEXUSDT currently profitable (user confirmed "в плюсе")
3. ✅ IDEXUSDT has trailing_activated=True (in TS symbols list)
4. ❌ IDEXUSDT NOT in aged monitoring (no logs)
5. ❌ IDEXUSDT NOT closing at breakeven

### Timeline:
- **6+ hours ago**: Position opened
- **~1-2 hours ago**: Became profitable, trailing_activated=True
- **Since then**: Skipped by periodic_full_scan() due to trailing_activated check
- **Current**: Still open, waiting for trailing stop (may never trigger)

---

## Impact Assessment

### Severity: P0 - CRITICAL

**Affected Positions**:
- ALL positions that:
  1. Are 6+ hours old
  2. Have trailing_activated=True
  3. Are profitable

**Current State**:
- IDEXUSDT (confirmed)
- Potentially: BROCCOLIUSDT, AIOZUSDT, RAYDIUMUSDT, PYRUSDT, SHIB1000USDT, WAVESUSDT
  (all in TS symbols list, need to check age)

**Financial Impact**:
- Positions stay open longer than intended
- Increased market risk
- Potential losses if price reverses
- User frustration (expected behavior not working)

---

## Related Issues

### Issue 1: Periodic Scan Doesn't Run After Restart
**File**: `core/position_manager_unified_patch.py:169`
**Problem**: `await asyncio.sleep(300)` BEFORE first scan
**Impact**: 5-minute delay before first aged detection after restart
**Fix**: Call scan immediately, then sleep

### Issue 2: No Logs for Successful Scans
**Problem**: Only logs when aged positions detected
**Impact**: Hard to verify scan is running
**Suggestion**: Log "Scanned X positions, 0 aged detected" even when nothing found

---

## Proposed Solutions

### Option 1: Remove Trailing Stop Skip (RECOMMENDED)
**Change**: Remove lines 1065-1067
**Rationale**:
- Aged logic should be independent of trailing stop
- If position is 6+ hours old and profitable, close at breakeven
- Trailing stop is a "nice to have" optimization, not a requirement

**Risk**: LOW
- Aged close takes precedence over trailing stop
- User gets expected behavior (breakeven close after 6 hours)

### Option 2: Modified Skip Logic
**Change**: Only skip if trailing stop is ACTIVE and position is NOT aged
**Rationale**: Allow trailing stop to work for young positions, but aged logic wins for old positions

```python
# Skip if trailing stop is active AND position not yet aged
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    if age_hours <= self.max_age_hours:
        continue  # Let trailing stop handle young positions
    # else: position is aged, continue to aged logic
```

**Risk**: MEDIUM
- More complex logic
- Still prioritizes aged close for old positions

### Option 3: Add Special "Aged + TS" Phase
**Change**: Create special monitoring phase for aged positions with trailing stops
**Rationale**: Track separately, apply different close logic

**Risk**: HIGH
- Significant refactoring
- Complex state management
- Unclear benefit over Option 1

---

## Recommended Fix

**OPTION 1: Remove Trailing Stop Skip**

**File**: `core/aged_position_monitor_v2.py`
**Function**: `periodic_full_scan()`
**Lines to REMOVE**: 1065-1067

```python
# REMOVE THESE LINES:
# Skip if trailing stop is active
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    continue
```

**Rationale**:
1. **User expectation**: "Close at breakeven after 6 hours" - NO exceptions
2. **Simplicity**: Remove conflicting logic
3. **Safety**: Aged logic is more conservative (closes at breakeven vs waiting for better price)
4. **Independence**: Aged module should work regardless of trailing stop state

**Testing**:
1. Remove lines 1065-1067
2. Wait for next periodic scan (or trigger manually)
3. Verify IDEXUSDT added to aged monitoring
4. Verify IDEXUSDT closes at next profitable price update

---

## Additional Fixes Needed

### Fix 1: Immediate Scan After Restart
**File**: `core/position_manager_unified_patch.py`
**Lines**: 167-170

**Current**:
```python
while True:
    try:
        await asyncio.sleep(interval_minutes * 60)  # Sleep BEFORE scan
        await aged_monitor.periodic_full_scan()
```

**Proposed**:
```python
while True:
    try:
        await aged_monitor.periodic_full_scan()  # Scan FIRST
        await asyncio.sleep(interval_minutes * 60)  # Then sleep
```

**Impact**: Aged positions detected immediately after restart instead of 5-minute delay

### Fix 2: Always Log Scan Results
**File**: `core/aged_position_monitor_v2.py`
**Lines**: 1085-1089

**Current**: Only logs if `detected_count > 0`
**Proposed**: Always log scan results for monitoring

```python
logger.info(
    f"🔍 Periodic aged scan complete: scanned {scanned_count} positions, "
    f"detected {detected_count} new aged position(s)"
)
```

---

## Conclusion

**Root Cause**: Lines 1065-1067 skip positions with `trailing_activated=True`, preventing aged monitoring for old profitable positions.

**Fix**: Remove lines 1065-1067 (3 lines)

**Estimated Time**: 5 minutes to fix, 10 minutes to test

**Risk**: LOW (removes conflicting logic, restores expected behavior)

**Next Step**: Apply fix and monitor IDEXUSDT behavior

---

**Audit Completed**: 2025-10-26 23:39 UTC
**Auditor**: Claude Code
**Approval Required**: User confirmation to apply fix
