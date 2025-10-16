# Smart Trailing Stop Diagnostic - Quick Start Guide

## Overview

This guide explains how to run the comprehensive diagnostic monitoring for the Smart Trailing Stop module.

## Files Created

1. **`ts_diagnostic_monitor.py`** - Main monitoring script (850+ lines)
2. **`TRAILING_STOP_AUDIT_REPORT.md`** - Detailed static analysis findings
3. **`TRAILING_STOP_DIAGNOSTIC_GUIDE.md`** - This guide

## Prerequisites

- Trading bot installed and configured
- Database connection working
- Exchange API credentials configured
- Python 3.9+ with asyncio

## Running the Diagnostic

### Option 1: Full 15-Minute Session (Recommended)

```bash
# From project root directory
python ts_diagnostic_monitor.py --duration 15
```

### Option 2: Quick Test (5 minutes)

```bash
python ts_diagnostic_monitor.py --duration 5
```

### Option 3: Extended Session (30 minutes)

```bash
python ts_diagnostic_monitor.py --duration 30
```

## What the Monitor Does

The diagnostic monitor performs **5 concurrent monitoring tasks**:

### 1. Trailing Stop State Monitoring
- Detects TS instance creation
- Tracks state transitions (INACTIVE → ACTIVE)
- Records activations with timestamps
- Monitors `highest_price`/`lowest_price` changes
- Counts SL update events

**Output:** Real-time logs of TS state changes

### 2. Database State Monitoring
- Snapshots database every 30 seconds
- Records position count, TS flags, SL prices
- Tracks `has_trailing_stop`, `trailing_activated` fields
- Measures DB query performance

**Output:** Time-series data of DB state

### 3. Exchange Order Monitoring
- Checks actual SL orders on exchange every 60 seconds
- Counts stop orders per position
- Verifies order properties (reduceOnly, stopPrice)
- Detects orphan orders

**Output:** Time-series data of exchange state

### 4. Consistency Checking
- Compares TS state vs DB state every 2 minutes
- Detects orphan TS instances (TS exists, no DB position)
- Detects missing TS instances (DB position exists, no TS)
- Detects state mismatches (TS active, DB says not activated)
- Detects SL price mismatches (TS vs DB > 1% difference)

**Output:** List of consistency issues found

### 5. Real-time Progress Reporter
- Prints summary every minute
- Shows counts of TS instances, activations, issues
- Displays recent errors
- Shows elapsed/remaining time

**Output:** Console progress updates

## Understanding the Output

### Console Output

```
================================================================================
⏱️  Minute 5 of 15 (remaining: 10 min)
================================================================================
📊 TS Instances: 8
✅ Activations: 3
🔄 SL Updates: 12
🗄️  DB Snapshots: 10
🔄 Exchange Snapshots: 5
⚠️  Issues Found: 2
❌ Errors: 0

Recent Issues:
  - [MEDIUM] SL price mismatch: TS=51242.50, DB=51000.00 (0.47%)
  - [HIGH] DB position exists but no TS instance created

================================================================================
```

### Log File

Detailed logs saved to:
```
logs/ts_diagnostic_<timestamp>.log
```

Contains:
- All DEBUG level messages from TS module
- WebSocket events
- Database queries
- Exchange API calls
- Error stack traces

### JSON Report

Comprehensive report saved to:
```
ts_diagnostic_report_<timestamp>.json
```

Contains:
- Metadata (duration, timestamps)
- Summary statistics
- Full detailed stats (all snapshots, events)
- List of issues found
- Analysis results
- Recommendations

## Interpreting Results

### Healthy System

```json
{
  "summary": {
    "ts_instances_tracked": 10,
    "activations": 5,
    "issues_found": 0,
    "errors": 0
  },
  "recommendations": [
    "✅ No critical issues detected - TS module functioning normally"
  ]
}
```

### Issues Detected

#### Missing TS Instance

```
⚠️ ISSUE: DB position exists but no TS instance created
Severity: HIGH
```

**Meaning:** A position in the database doesn't have a corresponding TS instance in memory.

**Possible Causes:**
- `create_trailing_stop()` was never called for this position
- TS creation failed silently
- Symbol is filtered out

**Action:** Check position opening flow in `PositionManager`

#### State Mismatch

```
⚠️ ISSUE: TS is ACTIVE but DB shows trailing_activated=False
Severity: MEDIUM
```

**Meaning:** TS in-memory state doesn't match DB state.

**Possible Causes:**
- DB update failed after TS activation
- Race condition during update
- DB field not being updated

**Action:** Check DB update calls after TS state changes

#### SL Price Mismatch

```
⚠️ ISSUE: SL price mismatch: TS=51242.50, DB=51000.00 (0.47%)
Severity: MEDIUM
```

**Meaning:** Stop loss price in TS memory differs from DB.

**Possible Causes:**
- DB update lag
- TS updated SL but DB write pending
- Normal delay (if < 1% difference)

**Action:** If > 1% difference, investigate DB update logic

#### Orphan TS Instance

```
⚠️ ISSUE: TS instance exists for BTCUSDT but no DB position found
Severity: HIGH
```

**Meaning:** TS exists in memory but position not in DB.

**Possible Causes:**
- Position was closed but TS not cleaned up
- DB delete succeeded but TS cleanup failed
- Memory leak

**Action:** Check `on_position_closed()` cleanup logic

## Common Scenarios

### Scenario 1: No Activations During Monitoring

**Observation:** `activations: 0` after 15 minutes

**Possible Reasons:**
1. No positions opened during monitoring
2. Positions not reaching activation threshold (1.5% profit by default)
3. Market is flat/sideways
4. Activation logic has a bug

**What to Check:**
- Are there open positions? Check DB snapshots
- Are prices moving? Check WebSocket events
- What's the profit% of positions? Calculate manually

### Scenario 2: Many SL Updates

**Observation:** `sl_updates: 50+` in 15 minutes

**Analysis:**
- Normal if price is moving fast and erratically
- Concerning if rate limiting not working

**What to Check:**
- Check log for "rate_limit" skip reasons
- Should see many "SKIPPED" messages if working correctly
- If not skipping, rate limiting may be broken

### Scenario 3: Errors Appearing

**Observation:** `errors: 5+`

**Action:**
1. Check recent errors in console output
2. Review full log file for stack traces
3. Common errors:
   - Exchange API timeout → Network issue
   - Database connection lost → DB issue
   - "Symbol not found" → TS initialization issue

## Performance Benchmarks

### Expected Performance

**Database Queries:**
- Frequency: Every 30 seconds
- Duration: < 100ms (local), < 500ms (remote)
- Alert if: > 1000ms consistently

**Exchange API Calls:**
- Frequency: Every 60 seconds
- Duration: < 500ms (typical)
- Alert if: > 2000ms or frequent timeouts

**TS Update Processing:**
- Frequency: On every price update (1-5s)
- Duration: < 10ms (memory-only)
- Alert if: > 100ms

## Troubleshooting

### Monitor Won't Start

**Error:** `Database connection failed`

**Fix:** Check `.env` file for correct DB credentials

---

**Error:** `No exchanges available`

**Fix:** Verify API keys in `.env`, check `enabled` flag in settings

---

**Error:** `Import error: No module named 'protection'`

**Fix:** Run from project root directory

### Monitor Crashes During Run

**Error:** `asyncio.TimeoutError`

**Fix:** Increase timeout in exchange manager, check network

---

**Error:** `Database deadlock`

**Fix:** Reduce monitoring frequency, check for other DB-heavy processes

---

**Error:** `Memory error`

**Fix:** Reduce monitoring duration, increase system RAM

### No Data Collected

**Symptom:** After 15 minutes, `ts_instances_tracked: 0`

**Possible Causes:**
1. No open positions during monitoring
2. TS managers not initialized
3. Monitoring tasks crashed silently

**Fix:**
1. Check log file for errors
2. Verify positions exist: `await repository.get_open_positions()`
3. Add manual position if needed for testing

## Manual Testing

### Create Test Position (if needed)

```bash
# Open a small position manually via exchange
# Then run monitor to see if TS is created
```

### Simulate Price Movement

For testnet testing:
1. Use volatile pairs (e.g., DOGEUSDT)
2. Monitor during active market hours
3. Consider using larger activation threshold for faster testing

### Verify TS Activation

```python
# In Python console
from protection.trailing_stop import SmartTrailingStopManager

# Check if TS exists
ts_manager = trailing_managers['binance']
print(ts_manager.trailing_stops.keys())

# Check specific TS state
ts = ts_manager.trailing_stops['BTCUSDT']
print(f"State: {ts.state.value}")
print(f"Activated: {ts.state.value == 'active'}")
print(f"Highest: {ts.highest_price}")
print(f"Current SL: {ts.current_stop_price}")
```

## Next Steps After Monitoring

### If Issues Found

1. Review `TRAILING_STOP_AUDIT_REPORT.md` for detailed analysis
2. Prioritize issues by severity (CRITICAL → HIGH → MEDIUM)
3. Create GitHub issues for each problem
4. Implement fixes following recommendations
5. Re-run diagnostic to verify fixes

### If No Issues Found

1. ✅ TS module is working correctly
2. Consider implementing database persistence anyway (recommended)
3. Add TS metrics to monitoring dashboard
4. Schedule periodic diagnostics (monthly)

## Advanced Usage

### Run Multiple Sessions

```bash
# Run 3 sessions of 15 minutes each, 1 hour apart
for i in {1..3}; do
    echo "Session $i starting..."
    python ts_diagnostic_monitor.py --duration 15
    echo "Session $i complete. Waiting 1 hour..."
    sleep 3600
done
```

### Combine with Live Trading

```bash
# Terminal 1: Run trading bot
python main.py

# Terminal 2: Run diagnostic (after bot starts)
sleep 60  # Wait for bot to initialize
python ts_diagnostic_monitor.py --duration 15
```

### Automated Daily Diagnostics

```bash
# Add to cron (daily at 2 AM)
0 2 * * * cd /path/to/TradingBot && python ts_diagnostic_monitor.py --duration 15 >> logs/daily_diagnostic.log 2>&1
```

## Support

If you encounter issues not covered in this guide:

1. Check full logs in `logs/ts_diagnostic_<timestamp>.log`
2. Review audit report: `TRAILING_STOP_AUDIT_REPORT.md`
3. Search codebase for similar error messages
4. Check exchange API status (downtime, maintenance)

## Appendix: Sample Output

### Successful Run

```
================================================================================
SMART TRAILING STOP DIAGNOSTIC MONITOR
================================================================================
Initializing database connection...
✅ Database connected
Initializing exchanges...
✅ Binance exchange ready
Initializing Trailing Stop Managers...
✅ TS Manager for binance initialized
================================================================================
✅ INITIALIZATION COMPLETE
================================================================================

================================================================================
Starting 15-minute monitoring session
Start time: 2025-10-15 14:30:00
================================================================================

🔍 Starting TS state monitoring...
🗄️  Starting database monitoring...
🔄 Starting exchange order monitoring...
🔍 Starting consistency checks...
📊 Starting progress reporter...

📊 Detected TS instance: BTCUSDT (long)
📊 Detected TS instance: ETHUSDT (long)
📊 Detected TS instance: SOLUSDT (short)

🔄 BTCUSDT: State changed to active
✅ BTCUSDT: TS ACTIVATED at $52150.0

📈 BTCUSDT: SL updated from $51000.00 to $51850.00 (+1.67%)

... (monitoring continues for 15 minutes) ...

================================================================================
Monitoring complete - Generating report...
================================================================================

✅ Full report saved to: ts_diagnostic_report_1697384400.json

================================================================================
📊 DIAGNOSTIC REPORT SUMMARY
================================================================================

TS Instances Tracked: 3
Activations: 1
SL Updates: 5
Issues Found: 0
Errors: 0

================================================================================
🔍 ANALYSIS
================================================================================

TS Functionality:
  - instances_created: 3
  - activations: 1
  - activation_rate: 0.33
  - symbols_with_ts: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

Performance:
  - total_db_queries: 30
  - avg_db_query_ms: 85.43
  - total_exchange_calls: 15
  - avg_exchange_call_ms: 342.18

Consistency:
  - orphan_ts_instances: 0
  - missing_ts_instances: 0
  - state_mismatches: 0
  - sl_price_mismatches: 0

================================================================================
💡 RECOMMENDATIONS
================================================================================

1. ✅ No critical issues detected - TS module functioning normally

================================================================================
```

---

**End of Guide**

*For detailed technical analysis, see `TRAILING_STOP_AUDIT_REPORT.md`*
