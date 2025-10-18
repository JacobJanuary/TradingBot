# 🚀 QUICK START CHEATSHEET - 8-Hour Production Audit

## PRE-FLIGHT CHECK (2 minutes)

```bash
# 1. Database OK?
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "SELECT COUNT(*) FROM monitoring.positions;"

# 2. Testnet mode? (should be true)
grep TESTNET .env

# 3. Disk space? (need >500MB)
df -h .

# 4. Copy observation template
cp hourly_observations_template.md hourly_observations.md
```

---

## START AUDIT (2 terminals)

### Terminal 1 - Bot
```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot
python main.py 2>&1 | tee monitoring_logs/bot_$(date +%Y%m%d_%H%M%S).log
```

### Terminal 2 - Monitor (wait 30 sec after Terminal 1)
```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot
sleep 30
python bot_monitor.py --duration 8
```

---

## HOURLY CHECKS (Terminal 3)

```bash
# Every hour, run this block:

# 1. Bot alive?
ps aux | grep "main.py" | grep -v grep

# 2. Current positions
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT exchange, status, COUNT(*) as count
FROM monitoring.positions
WHERE status IN ('active', 'trailing')
GROUP BY exchange, status;"

# 3. Recent errors
tail -50 monitoring_logs/bot_*.log | grep -i "error\|critical"

# 4. Record in hourly_observations.md
```

---

## AFTER 8 HOURS - ANALYSIS

```bash
# 1. Database analysis (5 min)
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto \
  -f post_test_analysis.sql > analysis_db.txt

# 2. Log analysis (2 min)
BOT_LOG=$(ls -t monitoring_logs/bot_*.log | head -1)
python log_analyzer.py $BOT_LOG --json > analysis_logs.txt

# 3. Review reports
cat monitoring_report_*.json | python -m json.tool

# 4. Check snapshots
wc -l monitoring_snapshots_*.jsonl  # Should be ~480 lines (8h × 60min)
```

---

## TROUBLESHOOTING

### Bot crashed?
```bash
# Check error
tail -100 monitoring_logs/bot_*.log

# Restart (append to same log)
python main.py 2>&1 | tee -a monitoring_logs/bot_*.log
```

### Monitor crashed?
```bash
# Check remaining hours
ELAPSED_HOURS=X  # How many hours passed
REMAINING=$((8 - ELAPSED_HOURS))

# Restart for remaining time
python bot_monitor.py --duration $REMAINING
```

### Database slow?
```bash
# Check connections
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT COUNT(*) FROM pg_stat_activity WHERE datname = 'fox_crypto';"

# Kill idle connections if > 20
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'fox_crypto' AND state = 'idle';"
```

---

## KEY FILES LOCATION

```
📁 TradingBot/
├── 🤖 bot_monitor.py           # Real-time monitoring
├── 📊 log_analyzer.py          # Log analysis tool
├── 🗄️ post_test_analysis.sql   # Database queries
├── 📖 START_8HOUR_AUDIT.md     # Full documentation
├── 📝 hourly_observations.md   # YOUR NOTES (fill this)
├── 📁 monitoring_logs/
│   └── bot_YYYYMMDD_HHMMSS.log
├── 📄 monitoring_snapshots_YYYYMMDD.jsonl
├── 📄 monitoring_report_YYYYMMDD_HHMMSS.json
├── 📄 analysis_db.txt
└── 📄 analysis_logs.txt
```

---

## MONITORING OUTPUT EXPLAINED

```
🔹 CURRENT STATE
  Total Positions: 7        ← Active positions NOW
  Unprotected: 0            ← 🚨 ALERT if >0

🔹 LAST MINUTE
  New Positions: 2          ← Just opened
  Prices Updated: 7         ← Should match total positions
  TS Activated: 1           ← Trailing stop turned on
  SL Updates (TS): 3        ← SL moved up by trailing

🔹 LAST 10 MINUTES
  Positions Opened: 5       ← Total opened in 10 min
  Avg Positions: 6.5        ← Average concurrent

🔹 ALL TIME
  Total Opened: 24          ← Since audit start
  Total Errors: 1           ← 🚨 Should be low
```

---

## ALERT SEVERITY

- 🚨 **CRITICAL**: Stop and investigate NOW
  - Positions without SL
  - Emergency closes

- ⚠️ **WARNING**: Monitor closely
  - High API errors (>5/min)
  - WebSocket reconnects
  - High position rate (>15/min)

- ℹ️ **INFO**: Normal operation
  - Aged positions (>3h)
  - Regular updates

---

## QUICK SQL CHECKS

```sql
-- Active positions by exchange
SELECT exchange, COUNT(*) FROM monitoring.positions
WHERE status IN ('active','trailing') GROUP BY exchange;

-- Recent errors (last 10 min)
SELECT event_type, COUNT(*) FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '10 minutes'
  AND event_type LIKE '%error%'
GROUP BY event_type;

-- Trailing stop states
SELECT state, COUNT(*) FROM monitoring.trailing_stop_state
GROUP BY state;

-- Positions without SL
SELECT COUNT(*) FROM monitoring.positions
WHERE status IN ('active','trailing') AND has_stop_loss = false;
```

---

## SUCCESS CHECKLIST

- [ ] Ran for full 8 hours
- [ ] No gaps in monitoring (480 snapshots)
- [ ] Hourly observations recorded
- [ ] Database analysis completed
- [ ] Log analysis completed
- [ ] All reports generated
- [ ] Zero CRITICAL alerts (or documented)

---

## NEXT STEPS

1. Read `analysis_db.txt` - look for HIGH counts in errors
2. Read `analysis_logs.txt` - identify error patterns
3. Review `hourly_observations.md` - your notes
4. Fill `AUDIT_REPORT_TEMPLATE.md` with findings
5. Prioritize fixes: IMMEDIATE → HIGH → MEDIUM → LOW
6. Create GitHub issues for each fix
7. Fix IMMEDIATE issues before next run

---

## ONE-LINER COMMANDS

```bash
# Start audit (copy-paste in 2 terminals)
# Terminal 1:
python main.py 2>&1 | tee monitoring_logs/bot_$(date +%Y%m%d_%H%M%S).log

# Terminal 2 (30 sec later):
sleep 30 && python bot_monitor.py --duration 8

# Post-audit analysis (copy-paste after 8h):
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -f post_test_analysis.sql > analysis_db.txt && \
python log_analyzer.py $(ls -t monitoring_logs/bot_*.log | head -1) --json > analysis_logs.txt && \
echo "✅ Analysis complete! Check analysis_db.txt and analysis_logs.txt"
```

---

**🎯 READY? Start with Terminal 1, then Terminal 2!**

Good luck! 🚀
