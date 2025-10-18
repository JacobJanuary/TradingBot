# 8-HOUR PRODUCTION AUDIT - STARTUP GUIDE

**Environment:** Testnet (Safe for testing)
**Duration:** 8 hours
**Goal:** Comprehensive production-level audit to identify all bugs, issues, and improvements

---

## ✅ PRE-FLIGHT CHECKLIST

### 1. System Verification

```bash
# Verify PostgreSQL is running
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "SELECT COUNT(*) FROM monitoring.positions;"

# Should return a count (e.g., 704)
```

### 2. Configuration Verification

```bash
# Verify testnet mode (SAFE)
grep TESTNET .env

# Should show:
# BINANCE_TESTNET=true
# BYBIT_TESTNET=true
```

### 3. Clean Logs Directory

```bash
# Ensure monitoring_logs directory exists
ls -la monitoring_logs/

# Check disk space (need ~500MB free)
df -h .
```

### 4. Test Monitoring Scripts

```bash
# Test monitoring script (5-minute test run)
python bot_monitor.py --test

# Should connect to DB and start collecting metrics
# Press Ctrl+C after 1-2 minutes to verify it works
```

---

## 🚀 STARTING THE 8-HOUR AUDIT

### Terminal Setup

You'll need **TWO terminal windows**:

#### TERMINAL 1 - BOT

```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Start the bot with logging
python main.py 2>&1 | tee monitoring_logs/bot_$(date +%Y%m%d_%H%M%S).log
```

**Wait 30 seconds** for bot initialization before starting Terminal 2.

#### TERMINAL 2 - MONITORING

```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Wait for bot to initialize (30 seconds)
sleep 30

# Start 8-hour monitoring
python bot_monitor.py --duration 8
```

---

## 📊 WHAT TO EXPECT

### Monitoring Output

Every 60 seconds you'll see:

```
================================================================================
📊 BOT MONITORING - 2025-10-18 12:34:56
================================================================================

🔹 CURRENT STATE
  Total Positions:     7
    ├─ Binance:        3
    └─ Bybit:          4
  🚨 Unprotected:      0

🔹 LAST MINUTE
  New Positions:       2
    ├─ Binance:        1
    └─ Bybit:          1
  Prices Updated:      7
  TS Activated:        1
  SL Updates (TS):     3
  Aged Detected:       0
  Closed on Exchange:  0

🔹 LAST 10 MINUTES
  Positions Opened:    5
  Positions Closed:    3
  TS Activations:      2
  SL Updates:          8
  Avg Positions:       6.5
  Avg Unprotected:     0.0

🔹 ALL TIME (since start)
  Total Opened:        24
  Total Closed:        17
  Total TS Act:        8
  Total Aged:          2
  Total Zombies:       0
  Total Errors:        1
================================================================================

⏳ Iteration 45 complete. Remaining: 7h 15m 0s
```

### Alerts to Watch For

**🚨 CRITICAL Alerts:**
- Positions without SL
- Emergency closes
- High error rates

**⚠️ WARNING Alerts:**
- High position opening rate (>15/min)
- High API errors (>5/min)
- No price updates despite active positions
- WebSocket reconnections

---

## 📝 HOURLY MANUAL CHECKS

Every hour, run these checks in a **THIRD terminal**:

### Hourly Checklist Commands

```bash
# 1. Check bot is still running
ps aux | grep "main.py" | grep -v grep

# 2. Check open positions
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT
    exchange, status, COUNT(*) as count,
    COUNT(*) FILTER (WHERE has_stop_loss = false) as no_sl
FROM monitoring.positions
WHERE status IN ('active', 'trailing')
GROUP BY exchange, status;
"

# 3. Check recent errors
tail -50 monitoring_logs/bot_*.log | grep -i "error\|critical"

# 4. Check trailing stop states
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT state, COUNT(*) as count
FROM monitoring.trailing_stop_state
GROUP BY state;
"

# 5. Check database connections
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT COUNT(*) as connections,
       COUNT(*) FILTER (WHERE state = 'active') as active
FROM pg_stat_activity
WHERE datname = 'fox_crypto';
"
```

### Record Observations

Create a file `hourly_observations.md` and record findings:

```markdown
# Hour 1 (HH:MM - HH:MM)

## Observations
- Total positions: X
- New opened: Y
- Trailing stops activated: Z

## Anomalies
- [None / describe any issues]

## Notes
- [Any interesting behavior]

---
```

---

## 🛑 STOPPING THE AUDIT

### Normal Shutdown (after 8 hours)

1. **Monitoring script** will auto-stop and generate `monitoring_report_*.json`
2. **Bot terminal**: Press `Ctrl+C` to gracefully stop the bot
3. Wait for all positions to close (or check with SQL query)

### Emergency Stop

If you need to stop early:

1. Press `Ctrl+C` in Terminal 2 (monitoring)
2. Press `Ctrl+C` in Terminal 1 (bot)
3. Data will be saved automatically

---

## 📊 POST-TEST ANALYSIS

After the 8-hour test completes, run comprehensive analysis:

### Step 1: Database Analysis

```bash
# Run comprehensive SQL analysis
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -f post_test_analysis.sql > analysis_db.txt

# Review the output
less analysis_db.txt
```

### Step 2: Log Analysis

```bash
# Find your bot log file
ls -lh monitoring_logs/

# Analyze the logs
python log_analyzer.py monitoring_logs/bot_YYYYMMDD_HHMMSS.log > analysis_logs.txt

# Optionally save JSON report
python log_analyzer.py monitoring_logs/bot_YYYYMMDD_HHMMSS.log --json
```

### Step 3: Review Monitoring Data

```bash
# Check monitoring snapshots
ls -lh monitoring_snapshots_*.jsonl

# Check final monitoring report
cat monitoring_report_*.json | jq '.'
```

---

## 🔍 FILES GENERATED

After the audit you'll have:

1. **Real-time monitoring:**
   - `monitoring_snapshots_YYYYMMDD.jsonl` - Minute-by-minute metrics
   - `monitoring_report_YYYYMMDD_HHMMSS.json` - Summary report

2. **Bot logs:**
   - `monitoring_logs/bot_YYYYMMDD_HHMMSS.log` - Complete bot log

3. **Analysis outputs:**
   - `analysis_db.txt` - Database analysis results
   - `analysis_logs.txt` - Log parsing results
   - `log_analysis_*.json` - JSON format log analysis

4. **Manual observations:**
   - `hourly_observations.md` - Your hourly notes

---

## 🚨 TROUBLESHOOTING

### Monitoring script crashes

```bash
# Check the error
tail -20 monitoring_snapshots_*.jsonl

# Restart monitoring (it will resume)
python bot_monitor.py --duration <remaining_hours>
```

### Bot stops unexpectedly

```bash
# Check last error in log
tail -100 monitoring_logs/bot_*.log

# Restart bot
python main.py 2>&1 | tee -a monitoring_logs/bot_*.log
```

### Database connection issues

```bash
# Test connection
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "SELECT 1;"

# Check connections
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT * FROM pg_stat_activity WHERE datname = 'fox_crypto';
"
```

### High CPU/Memory usage

```bash
# Check resource usage
top -pid $(pgrep -f main.py)
top -pid $(pgrep -f bot_monitor.py)

# If critical, reduce monitoring interval in bot_monitor.py
# Line 426: await asyncio.sleep(60)  # Change to 120 for 2-minute intervals
```

---

## 📋 EXPECTED OUTCOMES

### Success Criteria

✅ **Complete 8 hours of monitoring** without gaps
✅ **All metrics collected** every minute
✅ **All anomalies documented** with timestamps
✅ **Final reports generated** successfully
✅ **Database analysis completed** without errors

### What You'll Discover

This audit will reveal:

1. **Critical bugs:**
   - Positions without stop-loss
   - Race conditions
   - API error patterns

2. **Performance issues:**
   - Slow operations
   - Excessive updates
   - Database bottlenecks

3. **Logic problems:**
   - Trailing stop behavior
   - Position lifecycle issues
   - Synchronization gaps

4. **Edge cases:**
   - Aged positions
   - Zombie orders
   - WebSocket stability

---

## 🎯 NEXT STEPS AFTER AUDIT

Once analysis is complete:

1. **Prioritize issues** (Critical → High → Medium → Low)
2. **Create detailed bug reports** with evidence
3. **Propose fixes** for each issue
4. **Update documentation** with findings
5. **Plan improvements** based on data

---

## ⚡ QUICK START COMMANDS

**Copy-paste this to start the audit:**

```bash
# Terminal 1 - Bot
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot && python main.py 2>&1 | tee monitoring_logs/bot_$(date +%Y%m%d_%H%M%S).log

# Terminal 2 - Monitoring (wait 30 seconds after Terminal 1)
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot && sleep 30 && python bot_monitor.py --duration 8
```

**After 8 hours, run analysis:**

```bash
# Database analysis
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -f post_test_analysis.sql > analysis_db.txt

# Log analysis (replace YYYYMMDD_HHMMSS with actual filename)
python log_analyzer.py monitoring_logs/bot_YYYYMMDD_HHMMSS.log --json > analysis_logs.txt
```

---

## 📞 SUPPORT

If you encounter any issues:

1. Check this guide's troubleshooting section
2. Review log files for specific errors
3. Ensure database and bot are both running
4. Verify sufficient disk space and memory

---

**Ready to start? Follow the "STARTING THE 8-HOUR AUDIT" section above!**

Good luck with the audit! 🚀
