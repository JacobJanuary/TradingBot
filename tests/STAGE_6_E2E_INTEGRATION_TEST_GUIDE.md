# Stage 6: E2E Integration Test Guide

**Date:** 2025-10-09
**Duration:** ~3 hours active testing
**Objective:** Verify all Phases 0-4 work together in real testnet environment

---

## 📋 PRE-TEST CHECKLIST

### ✅ Environment Prerequisites

- [ ] PostgreSQL testnet DB ready (fox_crypto_test on port 5433)
- [ ] Testnet API keys configured (.env.testnet)
- [ ] Health check passes (14/18 PASS baseline)
- [ ] Git branch: fix/critical-position-sync-bug (current)
- [ ] No other bot instances running

**Verify:**
```bash
# Check no bot is running
ps aux | grep main.py | grep -v grep

# If running, kill it
pkill -f main.py

# Verify DB accessible
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "SELECT COUNT(*) FROM monitoring.positions;"
```

---

## 🚀 TEST SETUP (10 minutes)

### Step 1: Backup Current .env

```bash
# Backup current .env
cp .env .env.mainnet.backup

# Use testnet configuration
cp .env.testnet .env

# Verify testnet mode
grep "TESTNET" .env
# Should show:
# BINANCE_TESTNET=true
# BYBIT_TESTNET=true
```

### Step 2: Prepare Monitoring Terminals

You'll need **3 terminal windows** side-by-side:

**Terminal 1: Bot Logs**
```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot
tail -f logs/trading_bot.log
```

**Terminal 2: Database Monitor**
```bash
# Create monitoring script
cat > /tmp/monitor_positions.sh <<'EOF'
#!/bin/bash
while true; do
    clear
    date
    echo "=== Latest 5 Positions ==="
    psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "
        SELECT
            id,
            symbol,
            side,
            status,
            ROUND(entry_price::numeric, 2) as entry,
            ROUND(current_price::numeric, 2) as current,
            ROUND(unrealized_pnl::numeric, 2) as pnl,
            has_stop_loss as sl,
            created_at
        FROM monitoring.positions
        ORDER BY id DESC
        LIMIT 5;
    "
    echo ""
    echo "=== Position Count by Status ==="
    psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "
        SELECT status, COUNT(*)
        FROM monitoring.positions
        GROUP BY status;
    "
    sleep 5
done
EOF

chmod +x /tmp/monitor_positions.sh
/tmp/monitor_positions.sh
```

**Terminal 3: System Resources**
```bash
# Monitor CPU, Memory, Process
while true; do
    clear
    date
    echo "=== Bot Process ==="
    ps aux | grep -E "python.*main.py" | grep -v grep
    echo ""
    echo "=== Memory Usage ==="
    ps aux | grep -E "python.*main.py" | grep -v grep | awk '{print "Memory: " $4 "% (" $6 " KB)"}'
    echo ""
    echo "=== Open Files ==="
    lsof -p $(pgrep -f "python.*main.py") 2>/dev/null | wc -l || echo "Bot not running"
    sleep 10
done
```

---

## 🎬 TEST EXECUTION

### Phase 1: Bot Startup (15 minutes)

#### 1.1 Start Bot

```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Start in shadow mode (safer for first test)
python3 main.py --mode shadow

# Or production mode if confident:
# python3 main.py --mode production
```

**Expected Output in Terminal 1 (Logs):**
```
Trading Bot initializing in shadow mode
Configuration loaded from .env file ONLY
Environment: development
Binance configured: testnet=True
Bybit configured: testnet=True
✅ Exchange Manager initialized with 2 exchanges
✅ WebSocket connections established
✅ Signal processor started
🟢 TRADING BOT RUNNING IN SHADOW MODE
```

#### 1.2 Verify Startup (Checklist)

- [ ] Bot starts without errors
- [ ] Logs show "testnet=True" for exchanges
- [ ] WebSocket connections established
- [ ] No exceptions in logs
- [ ] Health check passes (check logs for "Health check: OK")
- [ ] Database connection working (no "DB connection failed")

**If any fail:** Stop bot (Ctrl+C), check logs, fix issue, restart

---

### Phase 2: Position Opening (30-60 minutes)

#### 2.1 Wait for Signal

**Shadow Mode:**
- Bot receives signals but doesn't execute trades
- You'll see logs like: "Shadow mode: Would open position for BTCUSDT"

**Production Mode:**
- Bot will automatically open positions when signals arrive
- You'll see: "Opening position for BTCUSDT long..."

**Monitor Terminal 1 for:**
```
Signal received: symbol=BTCUSDT, side=long, exchange=bybit
Validating signal...
✅ Signal validated
Acquiring position lock: bybit_BTCUSDT
✅ Lock acquired
Opening position...
```

#### 2.2 Manual Signal Trigger (Optional)

If no signals arrive naturally, you can **manually insert** a test signal into DB:

```sql
-- Connect to DB
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test

-- Insert test signal
INSERT INTO monitoring.signals (
    symbol, side, exchange, entry_price, score_week, score_month, created_at
) VALUES (
    'BTCUSDT', 'long', 'bybit', 50000.00, 75.0, 75.0, NOW()
);

-- Verify
SELECT * FROM monitoring.signals ORDER BY id DESC LIMIT 1;
```

**Note:** WebSocket signals are primary. This is backup method.

#### 2.3 Verify Position Opening

**In Terminal 2 (Database Monitor):**
- New row appears in positions table
- status = 'open'
- symbol, side, entry_price filled
- has_stop_loss = true ✅ (Phase 3.2 verification)
- created_at = recent timestamp

**In Terminal 1 (Logs):**
```
✅ Position opened: id=123, symbol=BTCUSDT, entry=50000.00
✅ Stop loss set: price=49000.00 (2.0%)
✅ Trailing stop initialized
Position saved to database
Event emitted: position_opened
Lock released: bybit_BTCUSDT
```

**Checklist:**
- [ ] Position appears in DB
- [ ] Status = 'open'
- [ ] Stop loss is set (has_stop_loss=true)
- [ ] Trailing stop initialized (check logs)
- [ ] No errors in logs
- [ ] Lock released (no "Lock still held" warnings)

---

### Phase 3: Position Monitoring (60 minutes)

#### 3.1 Real-time Updates

**Watch Terminal 2:**
- current_price updates every few seconds
- unrealized_pnl changes as price moves
- Position status remains 'open'

**Watch Terminal 1:**
- WebSocket price updates: "Price update: BTCUSDT = 50123.45"
- Trailing stop adjustments (if price moves favorably)
- No error messages

#### 3.2 Verify WebSocket Updates (Phase 4.1 - KeyError Protection)

**Expected:** No KeyError exceptions in logs, even if malformed messages arrive

**Monitor for:**
- ✅ "Price update received" (normal operation)
- ✅ "Missing required field: symbol" (Phase 4.1 protection working)
- ❌ NO "KeyError: 'symbol'" crashes

#### 3.3 Verify Phase 4.3 - Division by Zero Safety

If exchange returns price=0, bot should handle gracefully:

**Expected Log:**
```
⚠️ Invalid price (0) received for BTCUSDT, skipping update
```

**NOT:**
```
❌ ZeroDivisionError: division by zero
```

---

### Phase 4: Position Closing (30 minutes)

#### 4.1 Trigger Close

**Option A: Wait for Stop Loss**
- Let price move against position
- Stop loss automatically triggers
- Position closes

**Option B: Manual Close**

```sql
-- Find open position
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test

SELECT id, symbol, side FROM monitoring.positions WHERE status='open' ORDER BY id DESC LIMIT 1;

-- Update position to trigger close (simulate aged position)
UPDATE monitoring.positions
SET created_at = NOW() - INTERVAL '4 hours'
WHERE id = <position_id>;

-- Or manually update status (emergency test)
UPDATE monitoring.positions
SET status='pending_close'
WHERE id = <position_id>;
```

Then wait for aged position manager to process it.

#### 4.2 Verify Position Close

**In Terminal 2:**
- status changes: 'open' → 'pending_close' → 'closed'
- exit_price filled
- realized_pnl calculated
- closed_at timestamp set

**In Terminal 1:**
```
Closing position: id=123, symbol=BTCUSDT
Cancelling stop loss order...
✅ Stop loss cancelled
Executing close order...
✅ Position closed: exit=50456.78, pnl=+91.56 USD
Position status updated: closed
Event emitted: position_closed
```

**Checklist:**
- [ ] Position status = 'closed'
- [ ] exit_price set
- [ ] realized_pnl calculated (positive or negative)
- [ ] Stop loss cancelled (check logs)
- [ ] No errors
- [ ] Events emitted

---

### Phase 5: Compensating Transactions Test (Optional, 15 minutes)

**Goal:** Verify Phase 3.2 compensating transactions work

#### 5.1 Simulate Stop Loss Failure

**This is ADVANCED - Skip if not comfortable**

Temporarily disconnect network or kill exchange connection to simulate SL creation failure:

```bash
# In another terminal
# Kill network to exchange (requires sudo)
# sudo pfctl -d  # Disable firewall temporarily

# Or: Mock the SL creation to fail (requires code modification)
```

**Expected:** If SL creation fails, position should be closed immediately on exchange (compensating transaction)

**Logs should show:**
```
⚠️ Stop loss creation failed for position 123
🔄 Executing compensating transaction: closing position on exchange
✅ Compensating transaction complete: position closed
```

**Skip this if too risky - we have unit tests for this.**

---

## 📊 SUCCESS CRITERIA

### ✅ Mandatory Checks

- [ ] **Bot Startup:** No errors, testnet mode confirmed
- [ ] **Position Opening:** Position created in DB with all fields
- [ ] **Stop Loss:** has_stop_loss=true, no SL errors
- [ ] **Real-time Updates:** current_price updates via WebSocket
- [ ] **Lock Management:** Locks acquired and released (7 cleanup points working)
- [ ] **Position Closing:** Status updated, realized_pnl calculated
- [ ] **No Crashes:** Bot runs for full test duration without exceptions
- [ ] **No KeyErrors:** Phase 4.1 protection works (check logs for graceful handling)
- [ ] **No ZeroDivisionError:** Phase 4.3 protection works
- [ ] **Database Integrity:** All positions have valid data
- [ ] **Memory Stable:** Memory usage doesn't grow significantly (check Terminal 3)

### ⭐ Optional Checks

- [ ] Multiple positions opened/closed successfully
- [ ] Trailing stop adjusts as price moves favorably
- [ ] Aged position manager closes old positions
- [ ] Compensating transactions executed (if triggered)
- [ ] All events emitted correctly

---

## 🔍 VERIFICATION QUERIES

### After Test Completion

```sql
-- Connect to DB
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test

-- Check all positions from test
SELECT
    id,
    symbol,
    side,
    status,
    entry_price,
    exit_price,
    realized_pnl,
    has_stop_loss,
    created_at,
    closed_at
FROM monitoring.positions
WHERE created_at > NOW() - INTERVAL '4 hours'
ORDER BY id DESC;

-- Verify stop losses were created
SELECT COUNT(*) as positions_with_sl
FROM monitoring.positions
WHERE has_stop_loss = true
  AND created_at > NOW() - INTERVAL '4 hours';

-- Check for any errors
SELECT COUNT(*) as error_count
FROM monitoring.positions
WHERE status = 'error'
  AND created_at > NOW() - INTERVAL '4 hours';

-- Verify all positions closed cleanly
SELECT status, COUNT(*)
FROM monitoring.positions
WHERE created_at > NOW() - INTERVAL '4 hours'
GROUP BY status;
```

**Expected Results:**
- At least 1 position with status='closed' or 'open'
- All positions have has_stop_loss=true
- 0 positions with status='error'
- All closed positions have exit_price and realized_pnl

---

## 🚨 FAILURE SCENARIOS

### If Bot Crashes

1. **Check logs:** `tail -100 logs/trading_bot.log`
2. **Identify exception:** Look for last ERROR/CRITICAL message
3. **Check open positions:** Any stuck in 'open' state?
4. **Clean up:**
   ```sql
   -- Mark stuck positions as error
   UPDATE monitoring.positions
   SET status='error', error_message='Bot crashed during test'
   WHERE status='open' AND created_at < NOW() - INTERVAL '1 hour';
   ```
5. **Document issue** in STAGE_6_RESULTS.md
6. **Fix and re-run**

### If Position Opens But No SL

**This is CRITICAL failure (Phase 3.2 regression)**

1. Check logs for SL creation errors
2. Verify stop_loss_manager is working
3. Check exchange API responses
4. **DO NOT PROCEED TO MAINNET** until fixed

### If KeyError Occurs

**This indicates Phase 4.1 regression**

1. Find KeyError in logs
2. Identify which field caused it
3. Verify dict access safety was applied
4. Fix and re-test

---

## 🧹 POST-TEST CLEANUP

### After Successful Test

```bash
# Stop bot
Ctrl+C

# Restore mainnet .env
cp .env.mainnet.backup .env

# Verify
grep "TESTNET" .env
# Should show:
# BINANCE_TESTNET=false
# BYBIT_TESTNET=false

# Optional: Clean testnet DB
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "
    DELETE FROM monitoring.positions WHERE created_at > NOW() - INTERVAL '4 hours';
    DELETE FROM monitoring.signals WHERE created_at > NOW() - INTERVAL '4 hours';
"
```

---

## 📝 RESULTS DOCUMENTATION

Create **PHASE_5_STAGE_6_RESULTS.md** with:

### Template

```markdown
# Stage 6 E2E Integration Test Results

**Date:** [DATE]
**Duration:** [HOURS]
**Tester:** [NAME]

## Test Summary

- ✅/❌ Bot Startup
- ✅/❌ Position Opening
- ✅/❌ Stop Loss Creation
- ✅/❌ Real-time Updates
- ✅/❌ Position Closing
- ✅/❌ No Crashes

## Positions Tested

| ID | Symbol | Side | Status | Entry | Exit | PnL | SL Set | Duration |
|----|--------|------|--------|-------|------|-----|--------|----------|
| 123 | BTCUSDT | long | closed | 50000 | 50456 | +91.56 | ✅ | 45min |

## Issues Found

[List any issues, errors, or unexpected behavior]

## Verdict

✅ PASS - All critical functionality working
❌ FAIL - [Describe critical issues]

## Recommendation

[Proceed to mainnet / Fix issues / Extended testing]
```

---

## 🎯 NEXT STEPS

**After Stage 6 PASS:**
- **Option A:** Stage 7 - Stress Tests (concurrent positions, reconnection)
- **Option B:** Stage 8 - 24h Monitoring (long-term stability)
- **Option C:** Phase 6 - Mainnet Deployment Preparation

**After Stage 6 FAIL:**
- Fix identified issues
- Re-run Stage 6
- Consider extended testing

---

**Guide Version:** 1.0
**Created:** 2025-10-09
**Last Updated:** 2025-10-09
