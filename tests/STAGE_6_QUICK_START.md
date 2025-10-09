# Stage 6 E2E Test - Quick Start Guide

**Objective:** Test full position lifecycle on testnet (~3 hours)

---

## 🚀 QUICK START (5 minutes setup)

### Step 1: Switch to Testnet

```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Switch to testnet configuration
./tests/switch_to_testnet.sh
```

**Verify testnet mode:**
```bash
grep TESTNET .env
# Should show:
# BINANCE_TESTNET=true
# BYBIT_TESTNET=true
```

---

### Step 2: Open 3 Terminals

**Terminal 1: Start Bot**
```bash
# Shadow mode (safe, bot receives signals but doesn't trade)
./tests/start_testnet_bot.sh shadow

# OR Production mode (bot will actually trade on testnet)
./tests/start_testnet_bot.sh production
```

**Terminal 2: Monitor Positions**
```bash
./tests/monitor_positions.sh
```

**Terminal 3: Watch Logs**
```bash
tail -f logs/trading_bot.log
```

---

### Step 3: Observe Bot Operation

**What to look for:**

✅ **Bot starts without errors**
- Check Terminal 1 for "🟢 TRADING BOT RUNNING"
- Check Terminal 3 for no ERROR messages

✅ **Testnet mode confirmed**
- Logs show "testnet=True" for exchanges
- Terminal 2 connects to fox_crypto_test database

✅ **WebSocket connections established**
- Logs show "✅ WebSocket connections established"
- No connection errors

---

### Step 4: Wait for Position

**Shadow Mode:**
- Bot logs: "Shadow mode: Would open position for BTCUSDT"
- No actual trade executed
- Can still verify signal processing logic

**Production Mode:**
- Bot automatically opens positions when signals arrive
- Watch Terminal 2 for new position appearing
- Watch Terminal 3 for "Opening position..." logs

**If no signals arrive after 30 min:**
See "Manual Signal Trigger" in full guide (STAGE_6_E2E_INTEGRATION_TEST_GUIDE.md)

---

### Step 5: Verify Position Opened

**Terminal 2 should show:**
```
id | symbol  | side | status | entry  | current | pnl | sl | created
───┼─────────┼──────┼────────┼────────┼─────────┼─────┼────┼─────────
123| BTCUSDT | long | open   | 50000  | 50123   | +2.5| t  | 12:34:56
```

**Key checks:**
- ✅ Status = 'open'
- ✅ sl (has_stop_loss) = 't' (true)
- ✅ pnl updates in real-time

**Terminal 3 should show:**
```
✅ Position opened: id=123, symbol=BTCUSDT
✅ Stop loss set: price=49000.00
✅ Trailing stop initialized
Lock released: bybit_BTCUSDT
```

---

### Step 6: Monitor Position

**Let it run for 30-60 minutes**

Watch for:
- ✅ Price updates (current column changes in Terminal 2)
- ✅ PnL changes as price moves
- ✅ Trailing stop adjustments (if price moves favorably)
- ✅ No errors in Terminal 3

---

### Step 7: Wait for Close

**Position will close automatically when:**
- Stop loss triggers (price moves against position)
- Take profit hit (if configured)
- Position aged out (after MAX_POSITION_AGE_HOURS)

**OR manually close:**
```sql
# In another terminal
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test

# Find position ID
SELECT id, symbol FROM monitoring.positions WHERE status='open' ORDER BY id DESC LIMIT 1;

# Trigger close
UPDATE monitoring.positions
SET status='pending_close'
WHERE id = <position_id>;
```

---

### Step 8: Verify Position Closed

**Terminal 2 should show:**
```
id | symbol  | side | status | entry | exit  | pnl    | sl | closed
───┼─────────┼──────┼────────┼───────┼───────┼────────┼────┼─────────
123| BTCUSDT | long | closed | 50000 | 50456 | +91.56 | t  | 13:45:21
```

**Terminal 3 should show:**
```
Closing position: id=123, symbol=BTCUSDT
✅ Stop loss cancelled
✅ Position closed: exit=50456.78, pnl=+91.56 USD
Event emitted: position_closed
```

---

## ✅ SUCCESS CRITERIA

**Test PASSES if:**
- [x] Bot starts without errors
- [x] Position opens with status='open'
- [x] Stop loss created (has_stop_loss=true)
- [x] Price updates in real-time
- [x] Position closes with status='closed'
- [x] realized_pnl calculated
- [x] No crashes or errors

**Test FAILS if:**
- [ ] Bot crashes
- [ ] Position opens without stop loss
- [ ] KeyError exceptions occur
- [ ] Price doesn't update
- [ ] Position stuck in 'open' state

---

## 🧹 CLEANUP

```bash
# Stop bot (in Terminal 1)
Ctrl+C

# Stop monitoring (in Terminal 2)
Ctrl+C

# Switch back to mainnet
./tests/switch_to_mainnet.sh

# Verify mainnet mode
grep TESTNET .env
# Should show:
# BINANCE_TESTNET=false
# BYBIT_TESTNET=false
```

---

## 📝 DOCUMENT RESULTS

Create **PHASE_5_STAGE_6_RESULTS.md** with:
- Test duration
- Positions opened/closed
- Issues found (if any)
- Overall verdict (PASS/FAIL)

**Template:**
```markdown
# Stage 6 E2E Test Results

**Date:** 2025-10-09
**Duration:** 2 hours
**Mode:** Production

## Summary
- ✅ Bot started successfully
- ✅ 2 positions opened
- ✅ All positions had stop loss
- ✅ 1 position closed via SL
- ✅ 1 position still open
- ✅ No errors

## Verdict
✅ PASS - All critical features working

## Next Steps
Proceed to Stage 8 (24h monitoring)
```

---

## 🆘 TROUBLESHOOTING

### Bot Won't Start

**Check:**
```bash
# Is another instance running?
ps aux | grep main.py

# Kill if needed
pkill -f main.py

# Check .env configuration
grep -E "DB_NAME|TESTNET" .env
```

### No Signals Arriving

**Options:**
1. Wait longer (signals may be sparse)
2. Use manual signal trigger (see full guide)
3. Check WebSocket connection in logs

### Database Connection Failed

**Check:**
```bash
# Is PostgreSQL running?
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "SELECT 1;"

# Password should be: LohNeMamont@!21
```

### Position Opens But No Stop Loss

**CRITICAL - DO NOT PROCEED**
- This is Phase 3.2 regression
- Check logs for SL creation errors
- Document issue in results
- Fix before continuing

---

## 📚 FULL DOCUMENTATION

For detailed testing procedures, see:
- **STAGE_6_E2E_INTEGRATION_TEST_GUIDE.md** - Complete test guide (15 pages)
- **PHASE_5_TESTNET_INTEGRATION_PLAN.md** - Overall test plan (8 stages)

---

## 🎯 WHAT'S BEING TESTED

This E2E test verifies **all 21 completed tasks** from Phases 0-4:

**Phase 1 (Security):**
- ✅ SQL injection protection (34-field whitelist)
- ✅ Random salt encryption
- ✅ Schema='monitoring'
- ✅ Rate limiters (25 API call wrappers)

**Phase 2 (Functionality):**
- ✅ safe_decimal() edge case handling
- ✅ float() → safe_decimal() replacements (22 calls)

**Phase 3 (Refactoring):**
- ✅ Bare except → specific exceptions (4 files)
- ✅ open_position() refactoring (393→88 lines)
- ✅ 6 helper methods
- ✅ 3 dataclasses
- ✅ 7 lock cleanup points
- ✅ 3 compensating transaction patterns

**Phase 4 (Safety):**
- ✅ KeyError protection (dict access safety)
- ✅ Division by zero protection
- ✅ Magic numbers → constants (8 constants)

**This is the FIRST TIME all changes run together in real environment!**

---

**Created:** 2025-10-09
**Version:** 1.0
