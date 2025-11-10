# Manual Test Plan: Orphaned Position Cleanup Fix

## Date: 2025-11-10
## Priority: P0 - CRITICAL
## Fix: Added aged adapter cleanup to orphaned position handling

---

## Pre-conditions
- Bot running with unified protection enabled
- At least one open position (preferably aged 3+ hours)
- Access to bot logs (logs/trading_bot.log)
- Access to exchange account

---

## Test Case 1: Normal Orphaned Position Cleanup

### Objective
Verify that orphaned positions are cleaned up completely, including aged monitoring.

### Prerequisites
- Bot running in production/staging
- Unified protection enabled
- At least one open position

### Test Steps

1. **Identify Active Position**
   ```bash
   # Check current positions
   grep "Active positions" logs/trading_bot.log | tail -1
   # Pick a position symbol (e.g., TESTUSDT)
   ```

2. **Manually Close Position on Exchange**
   - Go to exchange web interface (Binance/Bybit)
   - Close the position manually (outside the bot)
   - Record the close time

3. **Wait for Sync Detection**
   - Wait for next `sync_with_exchange()` cycle (usually 60 seconds)
   - Monitor logs for orphaned detection

4. **Verify Cleanup Logs**
   ```bash
   # Should see this log message
   tail -f logs/trading_bot.log | grep "Closed orphaned position.*with full cleanup"
   ```

### Expected Results

✅ **Should See:**
```
INFO - Closed orphaned position: TESTUSDT (with full cleanup)
```

❌ **Should NOT See:**
```
ERROR - Failed to resubscribe TESTUSDT after 3 attempts
WARNING - Attempting resubscription for TESTUSDT
```

### Verification Commands

```bash
# 1. Check for cleanup log
grep "TESTUSDT.*with full cleanup" logs/trading_bot.log

# 2. Verify NO resubscription errors (wait 5 minutes)
tail -300 logs/trading_bot.log | grep "TESTUSDT" | grep -i "resubscr"
# Should return NOTHING

# 3. Check aged_targets cleanup (if possible via debug endpoint)
# aged_monitor.aged_targets should NOT contain TESTUSDT
```

### Success Criteria

- ✅ Position removed from `self.positions`
- ✅ Position removed from `aged_monitor.aged_targets`
- ✅ Position removed from `aged_adapter.monitoring_positions`
- ✅ NO "FAILED to resubscribe" errors for this symbol
- ✅ NO "Attempting resubscription" warnings for this symbol
- ✅ WebSocket health monitor does not try to resubscribe

---

## Test Case 2: Multiple Orphaned Positions

### Objective
Verify cleanup works correctly for multiple orphaned positions simultaneously.

### Test Steps

1. **Open Multiple Positions**
   - Open 3 positions on exchange

2. **Close All on Exchange**
   - Manually close all 3 positions on exchange web interface

3. **Wait for Sync**
   - Wait for next sync cycle (60 seconds)

4. **Verify All Cleaned**
   ```bash
   grep "Closed orphaned position.*with full cleanup" logs/trading_bot.log | tail -5
   ```

### Expected Results

All 3 positions should be cleaned up completely:
```
INFO - Closed orphaned position: SYMBOL1 (with full cleanup)
INFO - Closed orphaned position: SYMBOL2 (with full cleanup)
INFO - Closed orphaned position: SYMBOL3 (with full cleanup)
```

### Success Criteria

- ✅ All positions cleaned from `aged_targets`
- ✅ All positions cleaned from `monitoring_positions`
- ✅ NO resubscription errors for ANY of the symbols

---

## Test Case 3: Aged Position Cleanup

### Objective
Verify cleanup works correctly for positions that are actually aged.

### Prerequisites
- Position must be open for 3+ hours (aged)

### Test Steps

1. **Wait for Position to Age**
   - Let position run for 3+ hours
   - Verify position is in aged monitoring:
   ```bash
   grep "Position.*became aged" logs/trading_bot.log | grep SYMBOL
   ```

2. **Close Position on Exchange**
   - Manually close the aged position

3. **Wait for Cleanup**
   - Wait for sync cycle

4. **Verify Complete Cleanup**
   ```bash
   # Should see cleanup
   grep "SYMBOL.*with full cleanup" logs/trading_bot.log

   # Should NOT see resubscription
   tail -100 logs/trading_bot.log | grep "SYMBOL" | grep "resubscr"
   ```

### Success Criteria

- ✅ Aged position cleanup executed
- ✅ NO zombie subscription remains
- ✅ NO resubscription attempts after cleanup

---

## Test Case 4: Existing Zombie Positions (VELVETUSDT, VFYUSDT)

### Objective
Verify that existing zombie positions are NOT loaded after bot restart.

### Test Steps

1. **Record Current Zombies**
   ```bash
   # Before restart, check for resubscription errors
   grep -c "FAILED to resubscribe.*VELVETUSDT" logs/trading_bot.log
   grep -c "FAILED to resubscribe.*VFYUSDT" logs/trading_bot.log
   ```

2. **Restart Bot**
   - Stop bot
   - Start bot
   - Wait for initialization

3. **Monitor for 10 Minutes**
   ```bash
   # Watch for resubscription errors
   tail -f logs/trading_bot.log | grep -E "VELVETUSDT|VFYUSDT"
   ```

### Expected Results

After restart with fix:
- ❌ NO "FAILED to resubscribe" for VELVETUSDT
- ❌ NO "FAILED to resubscribe" for VFYUSDT
- ❌ NO "Attempting resubscription" warnings

### Success Criteria

- ✅ Old zombie positions NOT loaded into aged_targets
- ✅ NO resubscription attempts for old zombies
- ✅ Clean logs without spam

---

## Test Case 5: Long-Term Monitoring (24 hours)

### Objective
Verify fix works correctly over extended period.

### Test Steps

1. **Baseline Count**
   ```bash
   # Count resubscription errors before fix
   grep -c "FAILED to resubscribe" logs/trading_bot.log
   ```

2. **Monitor for 24 Hours**
   - Let bot run for 24 hours
   - Record any orphaned position cleanups

3. **Final Count**
   ```bash
   # Count resubscription errors after fix
   grep -c "FAILED to resubscribe" logs/trading_bot.log
   ```

### Success Criteria

- ✅ ZERO new "FAILED to resubscribe" errors
- ✅ All orphaned positions cleaned properly
- ✅ NO increase in error count

---

## Rollback Procedure

If tests fail or critical issues found:

```bash
# 1. Stop bot
systemctl stop trading_bot  # or your stop command

# 2. Restore backup
cp core/position_manager.py.backup_orphaned_fix_20251110_113054 core/position_manager.py

# 3. Restart bot
systemctl start trading_bot

# 4. Verify rollback
tail -f logs/trading_bot.log
```

---

## Monitoring Commands

### Check for Cleanup Logs
```bash
grep "with full cleanup" logs/trading_bot.log | wc -l
```

### Check for Resubscription Errors
```bash
grep "FAILED to resubscribe" logs/trading_bot.log | wc -l
```

### Monitor Real-Time
```bash
tail -f logs/trading_bot.log | grep -E "orphaned|resubscr|cleanup"
```

### Find Orphaned Cleanups
```bash
grep "Closed orphaned position.*with full cleanup" logs/trading_bot.log
```

---

## Success Metrics

| Metric | Before Fix | After Fix | Status |
|--------|-----------|-----------|--------|
| Resubscription Errors (24h) | 414+ | 0 | ✅ |
| Orphaned Cleanup Success | Partial | Complete | ✅ |
| Zombie Positions | 2+ | 0 | ✅ |
| Log Spam (errors/hour) | 360+ | 0 | ✅ |

---

## Notes

- All tests assume bot is running with unified protection enabled
- Tests should be performed in staging first if available
- Monitor logs for at least 5 minutes after each orphaned cleanup
- Keep backup file until all tests pass successfully

---

## Test Execution Record

| Test Case | Date | Tester | Result | Notes |
|-----------|------|--------|--------|-------|
| TC1: Normal Orphaned | | | | |
| TC2: Multiple Orphaned | | | | |
| TC3: Aged Position | | | | |
| TC4: Existing Zombies | | | | |
| TC5: 24h Monitoring | | | | |

---

## Sign-off

**Tested by**: _______________
**Date**: _______________
**Result**: PASS / FAIL
**Notes**: _______________
