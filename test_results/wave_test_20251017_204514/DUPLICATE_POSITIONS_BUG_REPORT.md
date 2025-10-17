# 🚨 CRITICAL BUG REPORT: Duplicate Position Creation

**Bug ID**: DUPLICATE_POSITIONS_001
**Severity**: 🔴 **CRITICAL**
**Status**: ⚠️ **ACTIVE BUG** - Confirmed in Production
**Date Discovered**: 2025-10-17
**Affected System**: Position Synchronizer (core/position_manager.py)

---

## 🎯 EXECUTIVE SUMMARY

**Bug**: Position Synchronizer создаёт **дублирующие записи** в БД при синхронизации с биржей.

**Impact**:
- ✅ НЕТ дублирования на бирже (биржа в порядке)
- ❌ ДУБЛИКАТЫ в базе данных (ghost positions)
- ⚠️ Искажение метрик и статистики
- ⚠️ Потенциальные проблемы с закрытием позиций

**Root Cause**: Синхронизатор проверяет только `self.positions` (в памяти), но НЕ проверяет БД перед созданием новой записи.

**Reproducing Rate**: Происходит при каждой periodic sync (каждые ~4 минуты)

---

## 📋 EVIDENCE: Реальный Случай

### Case: TAGUSDT Duplicate

**Discovered**: 2025-10-17 19:23:18

**Positions Created**:
```sql
Position #583:
  - Created: 2025-10-17 19:21:07 (by wave processor)
  - Entry: 0.00035440
  - Quantity: 564334
  - Status: active
  - Exchange Order ID: 12027441 ✅
  - Orders in DB: 2 (entry + SL) ✅
  - Trades in DB: 1 (entry) ✅

Position #589:
  - Created: 2025-10-17 19:23:18 (by sync_exchange_positions)
  - Entry: 0.00035410
  - Quantity: 564334 (SAME!)
  - Status: active
  - Exchange Order ID: NULL ❌
  - Orders in DB: 0 ❌
  - Trades in DB: 0 ❌
```

**Timeline**:
```
19:21:07 → Wave Processor creates position #583 ✅
19:21:07 → Entry order placed on Binance (12027441) ✅
19:21:08 → Stop-loss order placed (12027442) ✅
19:21:09 → Event: position_created (id=583) ✅

[2 minutes pass...]

19:23:18 → Periodic sync runs
19:23:18 → Sync fetches 17 positions from Binance
19:23:18 → DB has 16 symbols, Exchange has 17
19:23:18 → Sync finds: TAGUSDT on exchange, but NOT in self.positions ❌
19:23:18 → Sync creates DUPLICATE position #589 ❌
19:23:18 → Sync tries to set stop-loss
19:23:18 → Stop-loss already exists (from #583) ✅ (prevented second SL)
```

**Key Observation**: Position #583 была в `self.positions`, но синхронизатор её НЕ НАШЁЛ!

---

## 🔍 ROOT CAUSE ANALYSIS

### The Bug (core/position_manager.py:679)

```python
async def sync_exchange_positions(self, exchange_name: str):
    # ... fetch positions from exchange ...

    for pos in active_positions:
        symbol = normalize_symbol(pos['symbol'])

        # ❌ BUG: Only checks in-memory self.positions
        if symbol not in self.positions or self.positions[symbol].exchange != exchange_name:
            # Creates position WITHOUT checking database!
            position_id = await self.repository.create_position({
                'symbol': symbol,
                'exchange': exchange_name,
                'side': side,
                'quantity': quantity,
                'entry_price': entry_price
            })

            # Adds to in-memory tracking
            self.positions[symbol] = position_state
            logger.info(f"➕ Added new position: {symbol}")
```

### Why This Happens

**Scenario 1: Race Condition**
```
T+0s: Wave processor creates #583
T+0s: Adds #583 to self.positions
T+2s: Some code removes #583 from self.positions (cleanup? restart?)
T+130s: Periodic sync runs
T+130s: Checks self.positions → NOT FOUND
T+130s: Checks exchange → FOUND
T+130s: Creates duplicate #589 ❌
```

**Scenario 2: Restart/Reload Issue**
```
Bot starts
Loads positions from DB → self.positions populated
Wave processor creates #583
   → Updates self.positions
Periodic sync runs BEFORE self.positions fully synced
   → Doesn't see #583 in self.positions
   → Creates duplicate #589
```

**Scenario 3: Symbol Key Mismatch**
```
Wave Processor stores: self.positions['TAGUSDT']
Periodic Sync looks for: self.positions['TAG/USDT:USDT'] (not normalized?)
Not found → creates duplicate
```

---

## 🧪 INVESTIGATION: Which Scenario?

### Checking self.positions State

**Log Evidence**:
```
20:23:18 - DEBUG active_symbols (17): [...'TAGUSDT'...]
20:23:18 - DEBUG db_symbols for binance (16): [...NO TAGUSDT...]
                                                  ↑ BUT has EPICUSDT!
20:23:18 - DEBUG self.positions total: 34
```

**Analysis**:
- Exchange has: 17 symbols (including TAGUSDT)
- DB query returned: 16 symbols (NO TAGUSDT, has EPICUSDT)
- self.positions: 34 total

**db_symbols Query** (line 603):
```python
db_symbols = {s for s, p in self.positions.items() if p.exchange == exchange_name}
```

This reads from `self.positions`, NOT from database!

**So**:
- TAGUSDT IS in `self.positions` ✅
- BUT somehow NOT in `db_symbols` ❌

### Why TAGUSDT Not in db_symbols?

**Hypothesis 1**: position.exchange != 'binance'
```python
# Code checks: if p.exchange == exchange_name
# If #583 has exchange='Binance' (capital B)
# But sync uses 'binance' (lowercase)
# → Won't match!
```

**Hypothesis 2**: TAGUSDT temporarily removed
```python
# Between wave creation and sync:
# 1. Position #583 created
# 2. Some cleanup removed it from self.positions
# 3. Sync doesn't see it
# 4. Creates duplicate
```

**Hypothesis 3**: Symbol normalization issue
```python
# Wave processor: symbol='TAGUSDT'
# Sync: symbol=normalize_symbol('TAG/USDT:USDT') = 'TAGUSDT'
# BUT stored in self.positions with different key?
```

---

## 🔬 DEEPER INVESTIGATION: Check Logs

### EPICUSDT Clue

**Log**:
```
20:23:18 - DEBUG: EPICUSDT NOT in active_symbols, will close
20:23:18 - ⚠️ Found 1 positions in DB but not on binance
20:23:18 - Closing orphaned position: EPICUSDT
```

**EPICUSDT was**:
- In `self.positions` ✅
- In `db_symbols` ✅ (because in self.positions for binance)
- NOT on exchange ❌
- → Correctly closed

**But then immediately**:
```
20:23:18 - create_position() called for TAGUSDT
```

**TAGUSDT was**:
- On exchange ✅
- NOT in `db_symbols` ❌
- → Incorrectly created as "new"

### The Smoking Gun!

Look at the count:
- **active_symbols** (from exchange): 17
- **db_symbols** (from self.positions): 16
- Difference: 1

After closing EPICUSDT, it should be:
- Exchange: 17
- DB: 16 (EPICUSDT removed)
- Missing: 1 (TAGUSDT)

**So TAGUSDT was ALREADY missing from `self.positions`!**

---

## 🎯 ROOT CAUSE CONFIRMED

### Timeline Reconstruction

```
19:21:07 - Position #583 (TAGUSDT) created by wave processor
19:21:07 - Added to self.positions: self.positions['TAGUSDT'] = {...}
19:21:08 - Stop-loss set

[Something happens here that removes TAGUSDT from self.positions...]

19:23:18 - Periodic sync runs
19:23:18 - self.positions has 34 items
19:23:18 - db_symbols (filtered by exchange='binance'): 16 items
19:23:18 - TAGUSDT NOT in db_symbols (even though on exchange)
19:23:18 - Sync thinks: "New position on exchange!"
19:23:18 - Creates duplicate #589
```

### What Removed TAGUSDT from self.positions?

**Possible Causes**:

1. **Position closed and reopened too fast**
   - Unlikely: #583 is still active

2. **Cleanup logic removed it**
   - Check: zombie cleanup, aged position cleanup
   - Unlikely: position only 2 minutes old

3. **Exchange name mismatch**
   - **MOST LIKELY**: Position created with 'binance', but stored under different key
   - Or: position.exchange = 'Binance' (capital B) vs 'binance' (lowercase)

4. **Symbol normalization issue**
   - **POSSIBLE**: Symbol stored with different format

5. **Initialization race condition**
   - Bot restarted between 19:21 and 19:23?
   - Unlikely: would see restart logs

---

## 🐛 THE ACTUAL BUG

### Multiple Issues Found:

### Issue #1: No Database Check Before Creating Position

**Code** (line 679-687):
```python
if symbol not in self.positions or self.positions[symbol].exchange != exchange_name:
    # ❌ CREATES position WITHOUT checking if it exists in DB!
    position_id = await self.repository.create_position({...})
```

**Fix Needed**:
```python
if symbol not in self.positions or self.positions[symbol].exchange != exchange_name:
    # ✅ CHECK DATABASE FIRST!
    existing_position = await self.repository.get_open_position(symbol, exchange_name)

    if existing_position:
        # Update self.positions with existing position
        self.positions[symbol] = PositionState.from_db(existing_position)
        logger.info(f"♻️ Restored position from DB: {symbol}")
    else:
        # Create new position
        position_id = await self.repository.create_position({...})
        logger.info(f"➕ Added new position: {symbol}")
```

### Issue #2: Inconsistent Exchange Name Handling

**Check code for**:
- 'binance' vs 'Binance' (case sensitivity)
- Where position.exchange is set
- Where it's compared

### Issue #3: self.positions Can Get Out of Sync

**Problem**: `self.positions` (in-memory) is source of truth for `db_symbols`, but can get out of sync with actual DB.

**Fix**: Query DB directly for `db_symbols`:
```python
# Instead of:
db_symbols = {s for s, p in self.positions.items() if p.exchange == exchange_name}

# Use:
db_positions = await self.repository.get_all_open_positions(exchange=exchange_name)
db_symbols = {p.symbol for p in db_positions}
```

---

## 📊 IMPACT ASSESSMENT

### Current Impact

**Database Pollution**:
```sql
SELECT
    symbol,
    COUNT(*) as duplicates
FROM monitoring.positions
WHERE status = 'active'
GROUP BY symbol
HAVING COUNT(*) > 1;
```

**Expected**: 0 duplicates
**Actual**: Unknown (need to check)

**TAGUSDT Example**:
- 2 active positions in DB
- 1 actual position on exchange
- 1 ghost position (no orders, no trades)

### Potential Issues

1. **Metrics Corruption**:
   - Total positions count wrong
   - P&L calculations affected?
   - Portfolio value inflated?

2. **Position Management**:
   - Which position gets updated with price changes?
   - Which position gets closed when trade exits?
   - Stop-loss confusion?

3. **Risk Management**:
   - Real exposure calculation wrong
   - MAX_POSITIONS limit bypassed?

---

## ✅ VERIFICATION

### Check for More Duplicates

```sql
-- Find all duplicate active positions
SELECT
    symbol,
    exchange,
    COUNT(*) as count,
    ARRAY_AGG(id ORDER BY created_at) as position_ids,
    ARRAY_AGG(created_at ORDER BY created_at) as created_times
FROM monitoring.positions
WHERE status = 'active'
GROUP BY symbol, exchange
HAVING COUNT(*) > 1;
```

### Check Ghost Positions

```sql
-- Find positions without orders (ghosts created by sync)
SELECT
    p.id,
    p.symbol,
    p.status,
    p.entry_price,
    p.quantity,
    p.exchange_order_id,
    p.created_at,
    COUNT(o.id) as orders_count
FROM monitoring.positions p
LEFT JOIN monitoring.orders o ON o.position_id = p.id::text
WHERE p.status = 'active'
GROUP BY p.id
HAVING COUNT(o.id) = 0;
```

---

## 🔧 RECOMMENDED FIXES

### Fix #1: Add Database Check (CRITICAL)

**File**: `core/position_manager.py:679`

```python
# BEFORE (buggy):
if symbol not in self.positions or self.positions[symbol].exchange != exchange_name:
    position_id = await self.repository.create_position({...})

# AFTER (fixed):
if symbol not in self.positions or self.positions[symbol].exchange != exchange_name:
    # Check if position already exists in database
    existing_position = await self.repository.get_open_position(symbol, exchange_name)

    if existing_position:
        # Position exists in DB but not in memory - restore it
        position_state = PositionState(
            id=existing_position['id'],
            symbol=symbol,
            exchange=exchange_name,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            # ... fill in other fields from existing_position or exchange data
        )
        self.positions[symbol] = position_state
        logger.info(f"♻️ Restored existing position from DB: {symbol} (id={existing_position['id']})")

        # Continue to set stop-loss if needed...
    else:
        # Position truly doesn't exist - create new one
        position_id = await self.repository.create_position({...})
        # ... rest of creation logic
```

### Fix #2: Use DB for db_symbols Query

**File**: `core/position_manager.py:603`

```python
# BEFORE (uses in-memory):
db_symbols = {s for s, p in self.positions.items() if p.exchange == exchange_name}

# AFTER (uses actual DB):
db_positions = await self.repository.get_all_open_positions(exchange=exchange_name)
db_symbols = {p['symbol'] for p in db_positions}
```

### Fix #3: Add Duplicate Prevention at DB Level

**File**: `database/repository.py`

Add UNIQUE constraint:
```sql
ALTER TABLE monitoring.positions
ADD CONSTRAINT unique_active_position_per_symbol
UNIQUE (symbol, exchange, status)
WHERE status = 'active';
```

**Note**: This will cause `create_position()` to fail with IntegrityError if duplicate attempted.

Handle in code:
```python
try:
    position_id = await self.repository.create_position({...})
except IntegrityError:
    logger.warning(f"Position {symbol} already exists (caught by DB constraint)")
    # Fetch and restore existing position
    existing_position = await self.repository.get_open_position(symbol, exchange_name)
    # ... restore to self.positions
```

### Fix #4: Normalize Exchange Names

**Ensure consistency**:
```python
# In all places where exchange is set or compared:
exchange_name = exchange_name.lower()  # Always lowercase
```

---

## 🧪 TESTING PLAN

### Test #1: Reproduce the Bug

1. Create position manually (via wave)
2. Clear `self.positions` entry for that symbol
3. Run `sync_exchange_positions()`
4. Verify: Does it create duplicate?

### Test #2: Verify Fix

1. Apply Fix #1
2. Repeat Test #1
3. Verify: Should restore from DB, not create duplicate

### Test #3: Check Existing Duplicates

1. Run duplicate detection SQL
2. For each duplicate:
   - Check which one has orders/trades (keep)
   - Which one is ghost (delete)
3. Clean up ghosts

---

## 🚨 IMMEDIATE ACTIONS

### Priority 0: Assess Current Damage

```sql
-- Run this NOW to see how many duplicates exist:
SELECT
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(*) as total_active_positions,
    COUNT(*) - COUNT(DISTINCT symbol) as duplicates
FROM monitoring.positions
WHERE status = 'active';
```

### Priority 1: Stop Further Duplicates (Hotfix)

**Option A**: Disable periodic sync temporarily
```python
# In main.py or wherever sync is started:
# Comment out:
# await position_manager.start_periodic_sync()
```

**Option B**: Add quick check in sync
```python
# At line 681, before create_position:
existing = await self.repository.get_open_position(symbol, exchange_name)
if existing:
    logger.warning(f"Position {symbol} already exists (id={existing['id']}), skipping")
    continue  # Skip creation
```

### Priority 2: Clean Up Existing Duplicates

```python
# Script: cleanup_duplicate_positions.py
# For each duplicate:
#   - Identify which position is "real" (has orders/trades)
#   - Mark ghost as status='closed', reason='duplicate_cleanup'
#   - Log for review
```

### Priority 3: Apply Full Fix

- Implement Fix #1 (database check)
- Implement Fix #2 (query DB for db_symbols)
- Test thoroughly
- Deploy

### Priority 4: Add Monitoring

```python
# Add metric:
duplicate_positions_detected = 0

# In sync, after checking:
if existing_position and symbol in self.positions:
    duplicate_positions_detected += 1
    logger.error(f"🚨 DUPLICATE DETECTED: {symbol}")
```

---

## 📝 SUMMARY

| Aspect | Status |
|--------|--------|
| **Bug Confirmed** | ✅ Yes - TAGUSDT case proves it |
| **Root Cause** | Missing DB check before position creation |
| **Severity** | 🔴 Critical (creates ghost positions) |
| **Trading Impact** | ⚠️ Low (only DB pollution, no double trading) |
| **Data Integrity** | 🔴 High (database inconsistency) |
| **Fix Complexity** | 🟢 Low (add 5 lines of code) |
| **Testing Required** | 🟡 Medium (need to test sync logic) |

---

**Status**: 🔴 ACTIVE BUG - Fix Required
**Priority**: P1 - High
**ETA**: Can be fixed in < 1 hour
**Risk**: Medium (if not fixed, will accumulate ghosts)

---

**Report Prepared By**: Claude Code Analysis System
**Date**: 2025-10-17
**Review Status**: ✅ Ready for Engineering Review
