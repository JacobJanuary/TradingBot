# 🔍 RSRUSDT DUPLICATE INVESTIGATION - FULL REPORT

**Date:** 2025-10-18
**Case:** Position RSRUSDT id=1318 duplicate prevention mystery
**Status:** 🔴 ROOT CAUSE FOUND BUT NOT FULLY EXPLAINED

---

## 📋 EXECUTIVE SUMMARY

Position RSRUSDT (id=1318) exhibits anomalous behavior:
1. ✅ Created in DB at 14:07:13 with signal_id=4869992
2. ❌ **NEVER loaded into cache** `self.positions` (14:07-14:44)
3. ❌ **NOT loaded during bot restart** at 15:00:49 (despite status='active' in DB)
4. ✅ Restored to cache via periodic_sync at 15:10:09
5. ⚠️ Caused duplicate signal detection failure at 15:07:04

---

## 🎯 ROOT CAUSES IDENTIFIED

### PRIMARY ISSUE: Position Not Added to Cache After Creation

**Evidence:**
```
14:07:29 - Position update: RSR/USDT:USDT → RSRUSDT, mark_price=0.00618707
14:07:29 - → Skipped: RSRUSDT not in tracked positions
```

Position 1318 was created in DB but **NEVER added to `self.positions` cache**.

**Impact:**
- Price updates from exchange ignored
- Stop loss management failed
- Position invisible to wave_processor duplicate check

---

### SECONDARY ISSUE: Position Not Loaded During Startup

**Timeline:**
```
15:00:09 - Bot starts, calls load_positions_from_db()
15:00:09 - fetch_positions() from exchange → RSRUSDT NOT in response
15:00:30-49 - verify_position_exists() for 96 positions
15:00:49 - 📊 Loaded 96 positions from database
```

**Facts:**
- DB had 100 active positions (82 binance + 18 bybit)
- Only 96 loaded (4 missing)
- RSRUSDT was in DB with status='active'
- RSRUSDT has NO "✅ Verified" log
- RSRUSDT has NO "🗑️ PHANTOM detected" log
- RSRUSDT has NO "ERROR verifying position" log

**Contradiction:**
Position 1318 is currently `status='active'` in DB, meaning it was NOT closed as PHANTOM.
But it was also NOT verified and loaded.

**Possible explanations:**
1. `verify_position_exists()` returned TRUE (found on exchange) → should have loaded
2. `verify_position_exists()` returned FALSE (not found) → should have PHANTOM log
3. Exception occurred → should have ERROR log
4. Position was NOT in `get_open_positions()` result → BUT we confirmed it's in DB!

**MYSTERY: Why no logs for RSRUSDT during verification?**

---

### TERTIARY ISSUE: Signal_ID Not Saved

**Evidence:**
```sql
-- In monitoring.events:
signal_id: 4869992

-- In monitoring.positions:
signal_id: NULL
```

Bug in `create_position()` - signal_id not persisted to positions table.

---

## 📊 DETAILED TIMELINE

### Phase 1: Position Creation (14:07:13)

```
14:07:13.226 - Position 1318 created in DB
               - symbol: RSRUSDT
               - exchange: binance
               - signal_id: NULL (should be 4869992)
               - status: active

14:07:15.103 - Event logged: position_created
               - signal_id: 4869992 ✅

14:07:29.918 - First price update arrives
               → Skipped: RSRUSDT not in tracked positions ❌

14:07:43.386 - Event logged: position_updated
               - How? Position not in cache!
```

**ANOMALY:** Position updated in DB (see events table) but not in cache!

This suggests:
- Position WAS created on exchange
- Position WAS saved to DB
- Position was NOT added to `self.positions` cache
- Price updates from exchange saved to DB directly (via websocket?)
- But cache remained empty for this position

---

### Phase 2: Bot Running (14:07 - 14:44)

```
14:20:28.812 - trailing_stop_activated
14:24:50.150 - trailing_stop_updated (last update)
               - new_stop_price: 0.006127485

14:40:59.298 - Last position_updated event
14:44:46.165 - Last position_updated event (end of session)
```

Position actively traded, stop loss managed, BUT never in cache!

**Question:** How were trailing stops managed if position not in cache?

**Answer:** Likely through database-driven scheduled tasks or exchange sync, not through normal cache-based position management.

---

### Phase 3: Bot Downtime (14:44 - 15:00)

```
14:44 - Bot stopped
14:45-15:00 - Position likely closed on exchange (stop loss hit?)
15:00 - Bot restarted
```

No events during downtime (expected).

---

### Phase 4: Bot Restart & Loading (15:00)

```
15:00:02 - Bot starts
15:00:08 - synchronize_with_exchanges()
15:00:09 - fetch_positions() → RSRUSDT NOT in response ❌

15:00:09-49 - load_positions_from_db()
            - get_open_positions() returns 100 positions
            - verify_position_exists() called for each
            - RSRUSDT: ??? (NO LOGS) ???

15:00:49 - 📊 Loaded 96 positions from database
         - RSRUSDT NOT loaded ❌
         - No PHANTOM log ❌
         - No ERROR log ❌
```

**CRITICAL MYSTERY:** What happened to RSRUSDT during verification?

Possibilities:
1. **Never checked:** Position not in `get_open_positions()` result
   - BUT: SQL shows position in DB with status='active'

2. **Checked but exception:** try/except caught error
   - BUT: No ERROR log

3. **Checked and found:** verify_position_exists() returned TRUE
   - BUT: No "✅ Verified" log
   - AND: fetch_positions() showed it's NOT on exchange!

4. **Checked and not found:** verify_position_exists() returned FALSE
   - SHOULD: Have "🗑️ PHANTOM" log
   - SHOULD: Position closed in DB
   - BUT: No PHANTOM log, position still active!

---

### Phase 5: Wave Processing (15:07:04)

```
15:07:04.327 - wave_signal_processor: Processing signal 5/7: RSRUSDT
15:07:04.327 - has_open_position('RSRUSDT', 'binance')
15:07:04.327 - _position_exists('RSRUSDT', 'binance')
15:07:04.327 -    Step 1/3: Checking cache... ❌ Not in cache
15:07:04.328 -    Step 2/3: Checking database... ❌ Not in DB ⚠️
15:07:04.329 -    Step 3/3: Checking exchange API... (checked)
15:07:04.721 -    _position_exists() returned: False
15:07:04.721 - ✅ Signal 5 (RSRUSDT) processed successfully
```

**Why "Not in DB"?**

Position 1318 exists in DB with status='active'!

This suggests DB query in `_position_exists()` didn't find it.

---

### Phase 6: Signal Execution (15:07:13)

```
15:07:13.155 - signal_processor_websocket: Executing signal #4869992
15:07:13.508 - _position_exists('RSRUSDT', 'binance')
15:07:13.508 -    Step 1/3: Checking cache... ❌ Not in cache
15:07:13.509 -    Step 2/3: Checking database... ✅ Found in DB: position_id=1318
15:07:13.509 - WARNING - Position already exists
15:07:13.510 - position_duplicate_prevented
```

**9 seconds later, FOUND in DB!**

Same query, different result!

---

### Phase 7: Periodic Sync Recovery (15:10:09)

```
15:10:08.974 - fetch_positions() → RSRUSDT in response ✅
15:10:09.000 - ♻️ Restored existing position from DB: RSRUSDT (id=1318)
```

Position appeared on exchange between 15:00:09 and 15:10:08!

**Hypothesis:** Position was RE-OPENED on exchange (how? by whom?)

---

## 🔬 TECHNICAL ANALYSIS

### Database State Check

```sql
-- Position 1318 current state:
id: 1318
symbol: RSRUSDT
exchange: binance
status: active ✅
opened_at: 2025-10-18 14:07:13.226387
closed_at: NULL
signal_id: NULL ⚠️
stop_loss_price: 0.00622600
```

### Cache State

```
15:00:49 - Loaded symbols (96): [list excludes RSRUSDT]
15:10:09 - Restored: RSRUSDT added to cache
```

### Exchange State

```
15:00:09 - fetch_positions(): RSRUSDT NOT present ❌
15:10:08 - fetch_positions(): RSRUSDT present ✅
```

**Position disappeared then reappeared on exchange!**

---

## 🎯 KEY QUESTIONS REMAINING

### Q1: Why was position 1318 NOT added to cache after creation?

**Location:** core/position_manager.py - create_position() or open_position()

**Need to investigate:** Does create_position() add to self.positions?

### Q2: Why was position 1318 NOT loaded during bot restart?

**Location:** core/position_manager.py:320-360 - load_positions_from_db()

**Need to investigate:**
- Was position in `get_open_positions()` result?
- Was verify_position_exists() called for it?
- If called, what did it return?
- Why no logs?

### Q3: Why did DB query return different results 9 seconds apart?

```
15:07:04.328 - Step 2/3: Checking database... ❌ Not in DB
15:07:13.509 - Step 2/3: Checking database... ✅ Found in DB: position_id=1318
```

**Possible causes:**
- Transaction isolation level
- Concurrent DB write
- Query timeout
- Connection pool issue
- Query logic bug

### Q4: How did position reappear on exchange?

```
15:00:09 - NOT on exchange
15:10:08 - ON exchange
```

**Possible causes:**
- Position never actually closed (fetch_positions() bug?)
- Position manually reopened (by whom?)
- Bot reopened it somehow (no logs suggest this)
- Exchange testnet glitch

---

## 💡 RECOMMENDATIONS

### Immediate Actions

1. **Add comprehensive logging to create_position()**
   - Log when position added to cache
   - Log if position NOT added (and why)

2. **Add comprehensive logging to load_positions_from_db()**
   - Log ALL positions from DB (count)
   - Log ALL positions verified
   - Log ALL positions skipped (with reason)
   - Current gap: 100 in DB, 96 loaded, 4 missing - WHERE ARE LOGS?

3. **Fix signal_id not saving**
   - Update create_position() to save signal_id to positions table

### Investigation Actions

1. **Review create_position() code**
   - Ensure positions added to self.positions
   - Add error handling
   - Add rollback on failure

2. **Review load_positions_from_db() code**
   - Find why 4 positions not logged
   - Add logging for EVERY position processed
   - Add logging for exceptions in try/except

3. **Review _position_exists() DB query**
   - Check for race conditions
   - Check transaction isolation
   - Add query logging

### Testing Actions

1. **Reproduce position not loaded scenario**
   - Create position
   - Restart bot
   - Verify logs show verification attempt

2. **Test DB query consistency**
   - Call `get_open_position()` twice rapidly
   - Verify same results

---

## 📝 FILES TO INVESTIGATE

1. `core/position_manager.py:271-316` - verify_position_exists()
2. `core/position_manager.py:320-360` - load_positions_from_db()
3. `core/position_manager.py` - create_position() / open_position()
4. `database/repository.py:448-462` - get_open_positions()
5. `database/repository.py` - get_open_position() (singular)

---

**Investigation Status:** 🔴 CRITICAL ISSUE FOUND, NEEDS CODE REVIEW

**Next Step:** Review create_position() and load_positions_from_db() source code

**Created:** 2025-10-18 by Claude Code
**Priority:** 🔴 CRITICAL
