# Bot Monitoring & Audit System

Comprehensive production-level monitoring and auditing system for the trading bot.

---

## 📁 Files Overview

### 🛠️ Monitoring Tools

| File | Purpose | Usage |
|------|---------|-------|
| `bot_monitor.py` | Real-time monitoring script | `python bot_monitor.py --duration 8` |
| `log_analyzer.py` | Log file analysis tool | `python log_analyzer.py <logfile> --json` |
| `post_test_analysis.sql` | Post-audit database queries | `psql ... -f post_test_analysis.sql` |

### 📖 Documentation

| File | Purpose |
|------|---------|
| `START_8HOUR_AUDIT.md` | Complete audit guide with detailed instructions |
| `QUICK_START_CHEATSHEET.md` | Quick reference for starting/running audit |
| `MONITORING_README.md` | This file - overview of monitoring system |
| `AUDIT_REPORT_TEMPLATE.md` | Template for final audit report |
| `hourly_observations_template.md` | Template for manual hourly notes |

### 📊 Generated Files (during audit)

| File Pattern | Content |
|-------------|---------|
| `monitoring_snapshots_YYYYMMDD.jsonl` | Minute-by-minute metrics (JSONL format) |
| `monitoring_report_YYYYMMDD_HHMMSS.json` | Final monitoring summary (JSON) |
| `monitoring_logs/bot_*.log` | Complete bot execution log |
| `hourly_observations.md` | Your manual observations (copy from template) |
| `analysis_db.txt` | Database analysis results |
| `analysis_logs.txt` | Log analysis results |

---

## 🚀 Quick Start

### Step 1: Pre-flight Check (30 seconds)

```bash
# Verify database
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "SELECT 1;"

# Verify configuration (should show true for testnet)
grep TESTNET .env

# Copy observation template
cp hourly_observations_template.md hourly_observations.md
```

### Step 2: Start Audit (2 terminals)

**Terminal 1 - Bot:**
```bash
python main.py 2>&1 | tee monitoring_logs/bot_$(date +%Y%m%d_%H%M%S).log
```

**Terminal 2 - Monitoring (wait 30 sec):**
```bash
sleep 30 && python bot_monitor.py --duration 8
```

### Step 3: Hourly Checks (Terminal 3)

Every hour, run the SQL checks from `QUICK_START_CHEATSHEET.md` and update `hourly_observations.md`.

### Step 4: Post-Audit Analysis

```bash
# Database analysis
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto \
  -f post_test_analysis.sql > analysis_db.txt

# Log analysis
python log_analyzer.py monitoring_logs/bot_*.log --json > analysis_logs.txt
```

### Step 5: Create Audit Report

Fill in `AUDIT_REPORT_TEMPLATE.md` using data from:
- `analysis_db.txt`
- `analysis_logs.txt`
- `monitoring_report_*.json`
- `hourly_observations.md`

---

## 📊 Monitoring Script Details

### bot_monitor.py

**Purpose:** Real-time monitoring with minute-by-minute metrics collection.

**Features:**
- Connects to PostgreSQL database
- Collects 16 different metrics every 60 seconds
- Detects anomalies and generates alerts
- Saves snapshots to JSONL file
- Generates final summary report
- Runs for configurable duration

**Metrics Collected:**

1. **Position Metrics:**
   - Total positions (by exchange)
   - Unprotected positions (no SL)
   - New positions opened

2. **Activity Metrics:**
   - Price updates count
   - Trailing stop activations
   - SL updates with active TS
   - Positions closed on exchange

3. **Problem Metrics:**
   - Aged positions (>3 hours)
   - Zombie orders cleaned
   - Emergency closes
   - API errors
   - WebSocket reconnects

**Alerts:**
- 🚨 **CRITICAL:** Unprotected positions, emergency closes
- ⚠️ **WARNING:** High error rates, no price updates, WS reconnects
- ℹ️ **INFO:** Aged positions

**Usage:**

```bash
# Full 8-hour audit
python bot_monitor.py --duration 8

# Test mode (5 minutes)
python bot_monitor.py --test

# Custom duration
python bot_monitor.py --duration 2  # 2 hours
```

**Output Files:**
- `monitoring_snapshots_YYYYMMDD.jsonl` - One line per minute
- `monitoring_report_YYYYMMDD_HHMMSS.json` - Final summary

---

## 📝 Log Analyzer Details

### log_analyzer.py

**Purpose:** Parse and analyze bot log files for comprehensive insights.

**Features:**
- Parses Python logging format
- Categorizes by severity (ERROR, WARNING, CRITICAL)
- Analyzes position lifecycle
- Examines stop-loss operations
- Studies trailing stop behavior
- Checks WebSocket health
- Identifies timing issues
- Generates text and JSON reports

**Analysis Sections:**

1. **Position Lifecycle**
   - Positions opened/closed
   - Top symbols traded
   - Opening rate

2. **Stop-Loss Operations**
   - SL set/updated/triggered
   - Missing SL detection
   - Update frequency

3. **Trailing Stop**
   - Activations and updates
   - Average updates per position
   - Update rate analysis

4. **WebSocket Health**
   - Connections/disconnections
   - Reconnection events
   - Uptime percentage

5. **Error Analysis**
   - Error types distribution
   - Error-prone modules
   - Sample error messages

6. **Timing Issues**
   - Timeout errors
   - Rate limiting
   - Slow operations

**Usage:**

```bash
# Text output
python log_analyzer.py monitoring_logs/bot_YYYYMMDD_HHMMSS.log

# Save to file
python log_analyzer.py monitoring_logs/bot_*.log > analysis_logs.txt

# JSON output
python log_analyzer.py monitoring_logs/bot_*.log --json

# Custom JSON output file
python log_analyzer.py monitoring_logs/bot_*.log --json --output my_analysis.json
```

---

## 🗄️ Database Analysis Details

### post_test_analysis.sql

**Purpose:** Comprehensive SQL-based analysis of monitoring database.

**Sections (14 total):**

1. **Positions Summary** - Overall statistics
2. **Stop Loss Analysis** - SL operations and issues
3. **Trailing Stop Analysis** - TS behavior and excessive updates
4. **Errors and Issues** - Error distribution by type and exchange
5. **Performance Metrics** - Latency analysis (avg, p95, p99)
6. **Aged Positions** - Long-running positions
7. **Zombie Orders** - Orphaned orders analysis
8. **PnL Summary** - Win rate and profitability
9. **WebSocket Health** - Connection events
10. **Race Conditions** - Concurrent operations detection
11. **Hourly Distribution** - Activity by hour
12. **Critical Events Timeline** - Emergency events
13. **Position Lifecycle** - Sample position history
14. **Database Health** - Table sizes and stats

**Usage:**

```bash
# Run and save output
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto \
  -f post_test_analysis.sql > analysis_db.txt

# View in pager
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto \
  -f post_test_analysis.sql | less

# Run specific section (edit SQL file to comment out others)
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto \
  -f post_test_analysis.sql
```

**Key Queries:**

```sql
-- Positions without SL
SELECT COUNT(*) FROM monitoring.events
WHERE event_type = 'sl_missing';

-- Excessive TS updates
SELECT position_id, COUNT(*) FROM monitoring.events
WHERE event_type = 'trailing_stop_updated'
GROUP BY position_id HAVING COUNT(*) > 20;

-- Recent errors
SELECT event_type, COUNT(*) FROM monitoring.events
WHERE event_type LIKE '%error%'
  AND created_at > NOW() - INTERVAL '8 hours'
GROUP BY event_type;
```

---

## 📈 Interpreting Results

### Good Indicators

✅ **Monitoring:**
- All 480 snapshots collected (8h × 60min)
- No gaps in data
- Zero CRITICAL alerts

✅ **Positions:**
- All positions have SL
- No emergency closes
- Reasonable aged position count (<5)

✅ **Performance:**
- API response time <500ms average
- SL update latency <200ms
- Zero timeout errors

✅ **Stability:**
- <5 WebSocket reconnects
- <10 API errors total
- Zero zombie orders

### Warning Signs

⚠️ **Monitoring:**
- Missing snapshots (gaps in data)
- Multiple CRITICAL alerts
- High WARNING alert count

⚠️ **Positions:**
- Positions without SL (ANY)
- Emergency closes (>0)
- Many aged positions (>10)

⚠️ **Performance:**
- API response >1000ms
- SL update >500ms
- Frequent timeouts (>10)

⚠️ **Stability:**
- Frequent WS reconnects (>20)
- High API errors (>50)
- Multiple zombie orders (>5)

---

## 🔍 Audit Report Creation

### Data Sources

1. **Quantitative Data:**
   - `monitoring_report_*.json` - Metrics summary
   - `analysis_db.txt` - Database queries
   - `analysis_logs.txt` - Log analysis

2. **Qualitative Data:**
   - `hourly_observations.md` - Your notes
   - Bot terminal output - Real-time behavior
   - Manual SQL queries - Deep dives

### Report Structure

Follow `AUDIT_REPORT_TEMPLATE.md`:

1. **Executive Summary** - High-level overview
2. **Detailed Findings** - Issue-by-issue analysis
3. **Statistics** - Numbers and tables
4. **Recommendations** - Prioritized fixes
5. **Appendices** - Raw data and queries

### Issue Documentation

For each issue found:

```markdown
#### Issue #X: [Descriptive Title]

**Severity:** 🔴 CRITICAL
**Frequency:** 15 occurrences
**Evidence:**
- monitoring_report.json: "emergency_closes": 15
- analysis_db.txt: Section 4, line 234
- Log: monitoring_logs/bot_*.log:1234

**Root Cause:**
[Analysis with code reference: file.py:123]

**Recommendation:**
[Specific fix with code example]

**Priority:** 🔥 IMMEDIATE
```

---

## 🛠️ Customization

### Adjust Monitoring Interval

Edit `bot_monitor.py`, line ~426:

```python
# Change from 60 to desired seconds
await asyncio.sleep(60)  # Change to 120 for 2-minute intervals
```

### Add Custom Metrics

In `bot_monitor.py`, add to `collect_minute_metrics()`:

```python
# Add your custom query
custom_query = """
    SELECT COUNT(*) FROM your_table WHERE condition
"""
custom_count = await self.db_pool.fetchval(custom_query) or 0

# Add to MinuteMetrics dataclass
# Add to return statement
```

### Modify Alert Thresholds

In `bot_monitor.py`, edit `check_anomalies()`:

```python
# Change from 15 to your threshold
if metrics.new_positions_opened > 15:  # Customize this
    alerts.append(...)
```

---

## 📞 Troubleshooting

### Script won't start

```bash
# Check Python version (need 3.9+)
python --version

# Install dependencies
pip install asyncpg

# Test database connection
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "SELECT 1;"
```

### Database errors

```bash
# Check table exists
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "\dt monitoring.*"

# Check column names match
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "\d monitoring.events"
```

### Log analyzer fails

```bash
# Check log file exists
ls -lh monitoring_logs/

# Check log format
head -5 monitoring_logs/bot_*.log

# Try with different encoding
python log_analyzer.py <logfile> 2>&1 | head -50
```

### High memory usage

```bash
# Monitor memory
watch -n 5 'ps aux | grep -E "python|bot_monitor"'

# Reduce history size in bot_monitor.py
# Line ~73: maxlen=600 -> maxlen=300  (reduce to 5h instead of 10h)
```

---

## 📚 Additional Resources

### Documentation Files

- `START_8HOUR_AUDIT.md` - Comprehensive guide
- `QUICK_START_CHEATSHEET.md` - Quick reference
- `AUDIT_REPORT_TEMPLATE.md` - Report structure

### Useful SQL Queries

See `post_test_analysis.sql` for examples:
- Position lifecycle tracking
- Error pattern analysis
- Performance metrics
- Race condition detection

### Log Patterns

Common patterns to search in logs:

```bash
# All errors
grep -i "error\|critical" monitoring_logs/bot_*.log

# SL operations
grep -i "stop.loss\|sl " monitoring_logs/bot_*.log

# Trailing stop
grep -i "trailing" monitoring_logs/bot_*.log

# WebSocket issues
grep -i "websocket\|ws " monitoring_logs/bot_*.log

# Position lifecycle
grep -i "position opened\|position closed" monitoring_logs/bot_*.log
```

---

## ✅ Pre-Audit Checklist

- [ ] PostgreSQL running and accessible
- [ ] Bot configured for testnet (SAFE)
- [ ] Disk space >500MB available
- [ ] `monitoring_logs/` directory exists
- [ ] Database tables exist (`monitoring.*`)
- [ ] Python 3.9+ installed
- [ ] `asyncpg` package installed
- [ ] `hourly_observations.md` copied from template
- [ ] Two terminal windows ready
- [ ] 8 hours of time allocated

---

## 📊 Success Metrics

### Completeness

- ✅ All 480 snapshots collected
- ✅ No gaps in monitoring
- ✅ Hourly observations recorded
- ✅ Final reports generated

### Quality

- ✅ Zero CRITICAL alerts (or all documented)
- ✅ All issues analyzed
- ✅ Root causes identified
- ✅ Fixes proposed

### Deliverables

- ✅ `analysis_db.txt` - Complete
- ✅ `analysis_logs.txt` - Complete
- ✅ `hourly_observations.md` - Filled
- ✅ Audit report - Created
- ✅ Fix priorities - Defined

---

## 🎯 Next Steps After Audit

1. **Review Results** (2 hours)
   - Read all analysis files
   - Note patterns and anomalies
   - Identify critical issues

2. **Create Report** (3 hours)
   - Fill `AUDIT_REPORT_TEMPLATE.md`
   - Document all findings
   - Prioritize fixes

3. **Plan Fixes** (1 hour)
   - Group by priority
   - Estimate effort
   - Assign tasks

4. **Implement Fixes** (varies)
   - Start with IMMEDIATE priority
   - Test each fix
   - Update documentation

5. **Re-Test** (8 hours)
   - Run another audit
   - Compare results
   - Verify improvements

---

**Created by:** Claude Code
**Date:** 2025-10-18
**Version:** 1.0

---

**Ready to start? Open `QUICK_START_CHEATSHEET.md` for immediate actions!**
