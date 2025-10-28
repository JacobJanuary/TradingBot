# 🔴 CRITICAL: SL/TS Parameters Migration Verification Guide

**Date**: 2025-10-28
**Purpose**: Verify that bot actually uses per-exchange params from monitoring.params
**Status**: Ready for Production Verification

---

## EXECUTIVE SUMMARY

After deploying PHASE 1, PHASE 2, and PHASE 3, you need to verify that:

1. ✅ Bot loads trailing params from `monitoring.params` (per-exchange)
2. ✅ Bot saves trailing params to `monitoring.positions` when creating positions
3. ✅ TrailingStop uses per-position params (not global .env config)
4. ✅ Binance and Bybit can have DIFFERENT trailing behavior

**How to verify**: Use the tools below + check logs

---

## SECTION 1: AUTOMATED VERIFICATION

### Tool 1: Database & State Checker

**Purpose**: Verify DB structure and current state

```bash
python tools/verify_params_migration.py
```

**What it checks**:
- ✅ `monitoring.params` contains per-exchange values
- ✅ `monitoring.positions` has trailing_activation_percent and trailing_callback_percent columns
- ✅ Active positions have saved trailing params
- ✅ `monitoring.trailing_stops` params match position params
- ✅ Shows .env config for comparison

**Expected output**:
```
📊 STEP 1: Checking monitoring.params (per-exchange parameters)
+----+-----------+------------+--------+------------------+-----------------+---------------------+
| ID | Exchange  | Max Trades | SL %   | TS Activation %  | TS Callback %   | Updated At          |
+====+===========+============+========+==================+=================+=====================+
| 1  | binance   | 6 trades   | 4.0%   | 2.0%             | 0.5%            | 2025-10-27 23:35:00 |
+----+-----------+------------+--------+------------------+-----------------+---------------------+
| 2  | bybit     | 4 trades   | 6.0%   | 2.5%             | 0.5%            | 2025-10-27 22:50:00 |
+----+-----------+------------+--------+------------------+-----------------+---------------------+

✅ CONFIRMED: Different SL% - Binance: 4.0% vs Bybit: 6.0%
✅ CONFIRMED: Different TS Activation% - Binance: 2.0% vs Bybit: 2.5%

📊 STEP 2: Checking monitoring.positions (saved trailing params)
✅ Columns exist: trailing_activation_percent, trailing_callback_percent

✅ Found 3 active position(s):

+----+-----------+-----------+------+--------------+--------------------+-------------------+-----------+
| ID | Symbol    | Exchange  | Side | Entry Price  | TS Activation %    | TS Callback %     | Status    |
+====+===========+===========+======+==============+====================+===================+===========+
| 45 | BTCUSDT   | binance   | long | 67891.23     | 2.0%               | 0.5%              | ✅        |
+----+-----------+-----------+------+--------------+--------------------+-------------------+-----------+
| 46 | ETHUSDT   | binance   | long | 3245.67      | 2.0%               | 0.5%              | ✅        |
+----+-----------+-----------+------+--------------+--------------------+-------------------+-----------+
| 47 | SOLUSDT   | bybit     | long | 142.50       | 2.5%               | 0.5%              | ✅        |
+----+-----------+-----------+------+--------------+--------------------+-------------------+-----------+

✅ Migration working - new positions save trailing params

📊 STEP 3: Checking monitoring.trailing_stops (TS state)
✅ Found 3 active trailing stop(s):

+----+-----------+--------+---------+------+----------+------------+--------------+--------+-------+-------------+
| ID | Symbol    | Exch   | State   | Side | Entry    | Activation | Current Stop | Act %  | CB %  | Param Match |
+====+===========+========+=========+======+==========+============+==============+========+=======+=============+
| 12 | BTCUSDT   | binance| waiting | long | 67891.23 | 69249.05   | 66912.71     | 2.0%   | 0.5%  | ✅ Match    |
+----+-----------+--------+---------+------+----------+------------+--------------+--------+-------+-------------+
| 13 | ETHUSDT   | binance| waiting | long | 3245.67  | 3310.58    | 3197.79      | 2.0%   | 0.5%  | ✅ Match    |
+----+-----------+--------+---------+------+----------+------------+--------------+--------+-------+-------------+
| 14 | SOLUSDT   | bybit  | waiting | long | 142.50   | 146.06     | 140.48       | 2.5%   | 0.5%  | ✅ Match    |
+----+-----------+--------+---------+------+----------+------------+--------------+--------+-------+-------------+

✅ All TS params match position params!
```

**RED FLAGS**:
- ❌ "No data in monitoring.params" - DB not populated
- ❌ "Columns not found" - PHASE 1 migration not applied
- ❌ "TS with mismatched params: 3" - CRITICAL BUG!
- ⚠️  "Positions without params (legacy): 10" - Expected if old positions exist

---

### Tool 2: Real-time TS Activation Monitor

**Purpose**: Watch trailing stops activate in real-time

```bash
python tools/monitor_ts_activations.py
```

**What it shows**:
- 🔴 Live updates every 5 seconds
- 🔴 Current price vs activation price
- 🔴 Distance to activation (%)
- 🔴 **WHERE ACTIVATION % COMES FROM** (DB vs .env)

**Expected output**:
```
================================================================================
🔴 TRAILING STOP ACTIVATION MONITOR - 2025-10-28 15:30:45
================================================================================

📊 Exchange: BINANCE
   DB Params: activation=2.0%, callback=0.5%

+----------+------+---------------+------------------+-----------------+-----------------------+-------------+-----------+--------------+
| Symbol   | Side | Current Price | Activation Price | Distance        | Activation % Source   | Callback %  | State     | Current Stop |
+==========+======+===============+==================+=================+=======================+=============+===========+==============+
| BTCUSDT  | LONG | 67891.23      | 69249.05         | ⚪ 2.00%        | ✅ DB (2.0%)          | 0.5%        | ⏳ waiting| 66912.71     |
+----------+------+---------------+------------------+-----------------+-----------------------+-------------+-----------+--------------+
| ETHUSDT  | LONG | 3298.45       | 3310.58          | 🟡 0.37%        | ✅ DB (2.0%)          | 0.5%        | ⏳ waiting| 3197.79      |
+----------+------+---------------+------------------+-----------------+-----------------------+-------------+-----------+--------------+

📊 Exchange: BYBIT
   DB Params: activation=2.5%, callback=0.5%

+----------+------+---------------+------------------+-----------------+-----------------------+-------------+-----------+--------------+
| Symbol   | Side | Current Price | Activation Price | Distance        | Activation % Source   | Callback %  | State     | Current Stop |
+==========+======+===============+==================+=================+=======================+=============+===========+==============+
| SOLUSDT  | LONG | 145.80        | 146.06           | 🔥 0.18% (CLOSE!)| ✅ DB (2.5%)         | 0.5%        | ⏳ waiting| 140.48       |
+----------+------+---------------+------------------+-----------------+-----------------------+-------------+-----------+--------------+

📊 Total Active TS: 3

Legend:
  ✅ DB (X%) - Activation % loaded from monitoring.params (CORRECT)
  📌 Position (X%) - Activation % saved in position (per-position params)
  ⚠️  Config (X%) - Activation % from .env fallback (SHOULD BE RARE!)
```

**What to look for**:
- ✅ "✅ DB (2.0%)" - **CORRECT!** Using params from monitoring.params
- ✅ "📌 Position (2.0%)" - **OK!** Using per-position params (Variant B)
- ❌ "⚠️  Config (3.0%)" - **BAD!** Using .env fallback (migration failed!)

**Note**: Different exchanges should show different activation %:
- Binance: 2.0% (from monitoring.params exchange_id=1)
- Bybit: 2.5% (from monitoring.params exchange_id=2)

---

## SECTION 2: LOG VERIFICATION

### Step 1: Check Position Opening Logs

**When**: Bot opens new position

**Command**:
```bash
tail -f logs/bot.log | grep "📊 Using trailing"
```

**Expected output** (when opening Binance position):
```
2025-10-28 15:30:45 [INFO] 📊 Using trailing_activation_filter from DB for binance: 2.0%
2025-10-28 15:30:45 [INFO] 📊 Using trailing_distance_filter from DB for binance: 0.5%
```

**Expected output** (when opening Bybit position):
```
2025-10-28 15:30:50 [INFO] 📊 Using trailing_activation_filter from DB for bybit: 2.5%
2025-10-28 15:30:50 [INFO] 📊 Using trailing_distance_filter from DB for bybit: 0.5%
```

**RED FLAG** (migration failed):
```
2025-10-28 15:30:45 [WARNING] ⚠️  trailing_activation_filter not in DB for binance, using .env fallback: 3.0%
```

If you see this, it means:
- ❌ monitoring.params is empty or NULL
- ❌ get_params_by_exchange_name() failed
- ❌ Bot is using .env config (OLD BEHAVIOR)

---

### Step 2: Check Trailing Stop Creation Logs

**When**: Bot creates trailing stop for position

**Command**:
```bash
tail -f logs/bot.log | grep "Using per-position trailing params"
```

**Expected output**:
```
2025-10-28 15:30:46 [DEBUG] 📊 BTCUSDT: Using per-position trailing params: activation=2.0%, callback=0.5%
2025-10-28 15:30:51 [DEBUG] 📊 SOLUSDT: Using per-position trailing params: activation=2.5%, callback=0.5%
```

**RED FLAG** (migration failed):
```
2025-10-28 15:30:46 [DEBUG] 📊 BTCUSDT: Using config trailing params (fallback): activation=3.0%, callback=1.0%
```

This means:
- ❌ Position didn't save trailing params
- ❌ create_trailing_stop() didn't receive position_params
- ❌ TS is using .env config (OLD BEHAVIOR)

---

### Step 3: Check Stop Loss Logs

**When**: Bot opens position with stop loss

**Command**:
```bash
tail -f logs/bot.log | grep "Using stop_loss_filter from DB"
```

**Expected output**:
```
2025-10-28 15:30:45 [DEBUG] 📊 Using stop_loss_filter from DB for binance: 4.0%
2025-10-28 15:30:50 [DEBUG] 📊 Using stop_loss_filter from DB for bybit: 6.0%
```

**RED FLAG**:
```
2025-10-28 15:30:45 [WARNING] ⚠️  stop_loss_filter not in DB for binance, using .env fallback: 5.0%
```

---

## SECTION 3: MANUAL SQL QUERIES

### Query 1: Check monitoring.params Current Values

```sql
SELECT
    exchange_id,
    CASE exchange_id
        WHEN 1 THEN 'binance'
        WHEN 2 THEN 'bybit'
    END as exchange_name,
    max_trades_filter,
    stop_loss_filter,
    trailing_activation_filter,
    trailing_distance_filter,
    updated_at
FROM monitoring.params
ORDER BY exchange_id;
```

**Expected**:
- ✅ 2 rows (binance and bybit)
- ✅ Different values for each exchange
- ✅ Recently updated (within last 24h)

---

### Query 2: Check Positions Save Trailing Params

```sql
SELECT
    id,
    symbol,
    exchange,
    trailing_activation_percent,
    trailing_callback_percent,
    created_at
FROM monitoring.positions
WHERE status = 'active'
  AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

**Expected**:
- ✅ All new positions have non-NULL trailing params
- ✅ Values match monitoring.params for that exchange

**RED FLAG**:
- ❌ trailing_activation_percent is NULL (save failed!)

---

### Query 3: Verify TS Uses Position Params

```sql
SELECT
    ts.symbol,
    ts.exchange,
    ts.activation_percent as ts_activation,
    ts.callback_percent as ts_callback,
    p.trailing_activation_percent as position_activation,
    p.trailing_callback_percent as position_callback,
    CASE
        WHEN ts.activation_percent = p.trailing_activation_percent THEN '✅ Match'
        ELSE '❌ MISMATCH!'
    END as status
FROM monitoring.trailing_stops ts
JOIN monitoring.positions p ON ts.position_id = p.id
WHERE ts.state IN ('waiting', 'active');
```

**Expected**:
- ✅ All rows show "✅ Match"

**RED FLAG**:
- ❌ Any row shows "❌ MISMATCH!" (critical bug!)

---

## SECTION 4: TEST SCENARIO CHECKLIST

### Scenario 1: Open Binance Position

**Steps**:
1. Wait for signal for Binance
2. Open position
3. Check logs immediately

**Verification**:
```bash
# Should see:
tail -n 50 logs/bot.log | grep "📊 Using trailing_activation_filter from DB for binance"
tail -n 50 logs/bot.log | grep "Using per-position trailing params"
```

**Expected**:
- ✅ Logs show "from DB for binance: 2.0%"
- ✅ Position created in monitoring.positions with trailing_activation_percent=2.0
- ✅ TS created with activation_percent=2.0

---

### Scenario 2: Open Bybit Position

**Steps**:
1. Wait for signal for Bybit
2. Open position
3. Check logs immediately

**Verification**:
```bash
tail -n 50 logs/bot.log | grep "📊 Using trailing_activation_filter from DB for bybit"
```

**Expected**:
- ✅ Logs show "from DB for bybit: 2.5%" (DIFFERENT from Binance!)
- ✅ Position created with trailing_activation_percent=2.5
- ✅ TS created with activation_percent=2.5

---

### Scenario 3: Restart Bot (Recovery Test)

**Purpose**: Verify TS recovery uses position params

**Steps**:
1. Ensure 1-2 positions open with TS
2. Restart bot (`systemctl restart trading_bot`)
3. Check logs for TS restoration

**Verification**:
```bash
tail -f logs/bot.log | grep "TS RESTORED\|Using per-position trailing params"
```

**Expected**:
- ✅ TS restored with correct activation_percent from position
- ✅ Logs show "Using per-position trailing params"

**RED FLAG**:
- ❌ TS restored with different activation_percent
- ❌ Logs show "Using config trailing params (fallback)"

---

## SECTION 5: SUCCESS CRITERIA

### ✅ Migration is SUCCESSFUL if:

1. **Database**:
   - [x] `monitoring.params` has 2 rows (binance, bybit) with DIFFERENT values
   - [x] `monitoring.positions` has columns: trailing_activation_percent, trailing_callback_percent
   - [x] New positions have non-NULL trailing params

2. **Logs**:
   - [x] See "📊 Using trailing_activation_filter from DB" (not "using .env fallback")
   - [x] See "📊 Using per-position trailing params" (not "config trailing params")
   - [x] Binance shows 2.0%, Bybit shows 2.5% (DIFFERENT!)

3. **Behavior**:
   - [x] `python tools/verify_params_migration.py` → all checks pass
   - [x] `python tools/monitor_ts_activations.py` → shows "✅ DB (X%)" for all positions
   - [x] Restart bot → TS restored with correct params

4. **Production**:
   - [x] No errors in logs related to params
   - [x] Positions open successfully
   - [x] TS activates at correct levels
   - [x] Bot stable for 72 hours

---

### ❌ Migration FAILED if:

1. **Logs show**:
   - ❌ "⚠️  trailing_activation_filter not in DB, using .env fallback"
   - ❌ "📊 Using config trailing params (fallback)"
   - ❌ Same activation % for both Binance and Bybit

2. **Database shows**:
   - ❌ `monitoring.params` is empty or NULL
   - ❌ New positions have NULL trailing params
   - ❌ TS params don't match position params

3. **Monitoring tool shows**:
   - ❌ "⚠️  Config (3.0%)" instead of "✅ DB (2.0%)"
   - ❌ Verification script reports "VERIFICATION FAILED"

---

## SECTION 6: TROUBLESHOOTING

### Problem 1: "trailing_activation_filter not in DB" in logs

**Cause**: monitoring.params is empty or NULL

**Fix**:
1. Check monitoring.params:
   ```sql
   SELECT * FROM monitoring.params;
   ```
2. If empty, wait for next wave signal (bot updates params every 15 min)
3. Or manually insert:
   ```sql
   INSERT INTO monitoring.params (exchange_id, trailing_activation_filter, trailing_distance_filter)
   VALUES (1, 2.0, 0.5), (2, 2.5, 0.5)
   ON CONFLICT (exchange_id) DO UPDATE SET
       trailing_activation_filter = EXCLUDED.trailing_activation_filter,
       trailing_distance_filter = EXCLUDED.trailing_distance_filter;
   ```

---

### Problem 2: New positions have NULL trailing params

**Cause**: repository.create_position() not saving params

**Fix**:
1. Check code at database/repository.py:~400
2. Verify INSERT query includes trailing_activation_percent and trailing_callback_percent
3. Check position_manager.py:~1420 passes params to create_position()

---

### Problem 3: TS uses "config fallback" instead of "per-position params"

**Cause**: create_trailing_stop() not receiving position_params

**Fix**:
1. Check code at position_manager.py where create_trailing_stop() is called
2. Verify position_params dict is passed
3. Check protection/trailing_stop.py:478 handles position_params correctly

---

## CONCLUSION

**After running all verification steps above, you should have confidence that**:

✅ Bot loads per-exchange params from monitoring.params
✅ Bot saves trailing params to positions
✅ TrailingStop uses per-position params
✅ Binance and Bybit have different behavior
✅ Migration is SUCCESSFUL

**If any step fails, refer to Troubleshooting section above.**

---

**END OF VERIFICATION GUIDE**

**Date**: 2025-10-28
**Version**: 1.0
