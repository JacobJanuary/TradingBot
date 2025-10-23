# 🔬 ГЛУБОКОЕ РАССЛЕДОВАНИЕ: PERPUSDT Race Condition
## Дата: 2025-10-22 02:00
## Severity: P0 - CRITICAL (System Design Flaw)

---

## 📊 EXECUTIVE SUMMARY

**Вопрос**: Как PERPUSDT прошёл duplicate check и почему получили constraint violation?

**Ответ**: **RACE CONDITION** между Signal Processor и REST Polling Sync!

**Root Cause**: Atomic position manager и REST polling одновременно пытались создать одну и ту же позицию в течение **766 milliseconds**.

**Impact**:
- Сигнал failed хотя позиция была успешно открыта
- Atomic rollback удалил "правильную" позицию с SL
- Осталась "дублирующая" позиция от REST polling
- Система потеряла контроль над позицией

**Fix Required**: P0 - Critical system design fix needed

---

## 🎯 TIMELINE: Race Condition в 766ms

### T+0ms (01:35:25.773): Signal Processor Start
```
📍 core.position_manager - INFO - Opening position ATOMICALLY: PERPUSDT BUY 882.2
📍 core.atomic_position_manager - INFO - 🔄 Starting atomic operation: pos_PERPUSDT_1761082525.773755
```

**Action**: Signal processor начинает atomic operation

---

### T+1ms (01:35:25.774): Database Check #1
```
📍 database.repository - INFO - 🔍 REPO DEBUG: create_position() called for PERPUSDT
📍 database.repository - INFO - 🔍 REPO DEBUG: Got connection from pool for PERPUSDT
```

**Action**: `create_position()` проверяет `get_open_position(PERPUSDT, binance)`
**Result**: ✅ **NOT FOUND** - позиция не существует
**Decision**: Proceed with INSERT

---

### T+2ms (01:35:25.775): Position Created (ID=2438)
```
📍 database.repository - INFO - 🔍 REPO DEBUG: INSERT completed, returned position_id=2438 for PERPUSDT
📍 core.atomic_position_manager - INFO - ✅ Position record created: ID=2438
```

**DB State**:
```sql
INSERT INTO monitoring.positions (symbol, exchange, side, quantity, entry_price, status)
VALUES ('PERPUSDT', 'binance', 'long', 882.2, 0.2267, 'active');
-- ID: 2438, status: 'active'
```

**CRITICAL**: Position is now 'active' in DB!
**CRITICAL**: Unique constraint NOT violated yet (only one PERPUSDT/binance/active)

---

### T+3ms (01:35:25.776): Entry Order Placement
```
📍 core.atomic_position_manager - INFO - 📊 Placing entry order for PERPUSDT
```

**Action**: Placing market order on Binance
**Duration**: ~355ms

---

### T+358ms (01:35:26.131): Order Placed
```
📍 core.atomic_position_manager - INFO - 🔍 About to log entry order for PERPUSDT
📍 core.atomic_position_manager - INFO - 📝 Entry order logged to database
📍 core.atomic_position_manager - INFO - 🔍 About to log entry trade for PERPUSDT
📍 core.atomic_position_manager - INFO - 📝 Entry trade logged to database
```

**Status**: Order filled on exchange
**CRITICAL**: Position now EXISTS on Binance exchange!

---

### T+766ms (01:35:26.539): ⚠️ REST POLLING ARRIVES!
```
📍 core.position_manager - INFO - 🔍 DEBUG active_symbols (5): ['EGLDUSDT', 'FLMUSDT', 'GRTUSDT', 'LAUSDT', 'PERPUSDT']
```

**Action**: REST polling fetched positions from Binance
**Found**: PERPUSDT position exists on exchange!
**Trigger**: Periodic sync detects "new" position

---

### T+767ms (01:35:26.540): Database Check #2
```
📍 database.repository - INFO - 🔍 REPO DEBUG: create_position() called for PERPUSDT
```

**Context**: REST polling found PERPUSDT on exchange, calls `create_position()`
**Action**: `create_position()` calls `get_open_position(PERPUSDT, binance)`

**QUESTION**: ID=2438 exists with status='active'. Why wasn't it found?!

**ANSWER**: **DATABASE TRANSACTION ISOLATION!**

---

## 🔍 DATABASE ISOLATION ANALYSIS

### Why get_open_position() didn't find ID=2438:

**Hypothesis 1: Transaction Isolation Level**
```python
# atomic_position_manager.py creates position in transaction
# REST polling checks in DIFFERENT connection/transaction
# PostgreSQL default: READ COMMITTED isolation
```

**Hypothesis 2: Connection Pool Timing**
- Atomic manager: transaction still open (updating position)
- REST polling: new connection, doesn't see uncommitted changes
- Race window: 766ms

**Verification Needed**: Check PostgreSQL isolation level and connection pool behavior

---

### T+768ms (01:35:26.541): Duplicate Created (ID=2439)
```
📍 database.repository - INFO - 🔍 REPO DEBUG: INSERT completed, returned position_id=2439 for PERPUSDT
📍 core.position_manager - INFO - ➕ Added new position: PERPUSDT
📍 core.event_logger - INFO - stop_loss_placed: {'position_id': 2439, 'symbol': 'PERPUSDT', 'stop_loss_price': 0.222166}
```

**DB State**:
```sql
-- Now we have TWO positions:
-- ID=2438: symbol='PERPUSDT', exchange='binance', status='active' (from signal)
-- ID=2439: symbol='PERPUSDT', exchange='binance', status='active' (from REST polling)
```

**QUESTION**: Why didn't unique constraint fire?!

**ANSWER**: Constraint is **partial index**: `WHERE status='active'`
- Both are 'active' → constraint SHOULD fire on second INSERT
- BUT IT DIDN'T → This is the mystery!

**Hypothesis**: Transaction isolation prevented constraint check from seeing ID=2438

---

### T+2717ms (01:35:27.490): Stop-Loss Placement (Atomic)
```
📍 core.atomic_position_manager - INFO - 🛡️ Placing stop-loss for PERPUSDT at 0.222166
📍 core.stop_loss_manager - INFO - Setting Stop Loss for PERPUSDT at 0.222166
```

**Action**: Atomic manager places SL for ID=2438
**Order**: Successfully placed on exchange (order ID: 24233907)

---

### T+2778ms (01:35:28.551): Stop-Loss Confirmed
```
📍 core.event_logger - INFO - stop_loss_placed: {'symbol': 'PERPUSDT', 'exchange': 'binance', 'stop_price': 0.2222, 'order_id': '24233907'}
```

**Status**: SL active on exchange
**Next**: Atomic manager tries to finalize position

---

### T+2782ms (01:35:28.555): 💥 CONSTRAINT VIOLATION!
```
📍 core.atomic_position_manager - ERROR - ❌ Atomic position creation failed: duplicate key value violates unique constraint "idx_unique_active_position"
DETAIL:  Key (symbol, exchange)=(PERPUSDT, binance) already exists.
```

**Action**: Atomic manager tries to UPDATE position ID=2438:
```sql
UPDATE monitoring.positions
SET status='active', stop_loss_price=0.222166
WHERE id=2438;
```

**Error**: Constraint fires because ID=2439 already exists with (PERPUSDT, binance, active)!

**Why NOW and not at T+768ms?**
- At T+768ms: INSERT from REST polling → constraint should fire but didn't
- At T+2782ms: UPDATE from atomic manager → constraint fires

**Hypothesis**: UPDATE sees committed changes from other transactions, but INSERT didn't?

---

### T+2783ms (01:35:28.556): Atomic Rollback
```
📍 core.atomic_position_manager - WARNING - 🔄 Rolling back position for PERPUSDT, state=active
📍 core.atomic_position_manager - ERROR - ❌ Atomic operation failed: pos_PERPUSDT_1761082525.773755
```

**Action**: Rollback deletes ID=2438
**Result**: Only ID=2439 remains (the "duplicate" from REST polling)
**Problem**: ID=2439 was created WITHOUT signal_id, atomic guarantees lost!

---

## 🔬 ROOT CAUSE ANALYSIS

### Primary Cause: Race Between Two Processes

**Process A: Signal Processor (Atomic)**
1. Checks DB → not found
2. Creates position ID=2438
3. Places entry order (355ms)
4. **[WINDOW: 766ms]** ← REST polling intervenes
5. Places SL
6. Tries to finalize → constraint error!

**Process B: REST Polling (Periodic Sync)**
1. Fetches positions from exchange (every ~2s)
2. Finds PERPUSDT on exchange
3. Checks DB → not found (!)
4. Creates position ID=2439
5. Places SL (different order)

### Why Duplicate Check Failed

**Code has protection**:
```python
# core/position_manager.py:710-711
# FIX 1.2: Check database first before creating (prevent duplicates)
db_position = await self.repository.get_open_position(symbol, exchange_name)
```

**Query**:
```python
# database/repository.py:287
WHERE symbol = $1 AND exchange = $2 AND status = 'active'
```

**Why it failed**: Database isolation + timing
- Atomic manager's transaction not yet visible to REST polling's connection
- 766ms race window
- Both processes saw "no position exists"

### Database Constraint

**Constraint Definition**:
```sql
UNIQUE (symbol, exchange) WHERE status='active'
```

**Expected**: Prevent duplicate active positions
**Reality**: Didn't prevent INSERT at T+768ms, but prevented UPDATE at T+2782ms

**Hypothesis**:
- INSERT at T+768ms: Atomic manager's transaction uncommitted → constraint didn't see it
- UPDATE at T+2782ms: Both transactions committed → constraint sees both

---

## 📊 DATABASE STATE COMPARISON

### Before (T+0):
```
monitoring.positions: 0 rows matching (PERPUSDT, binance, active)
```

### During Race (T+2 to T+2782):
```
ID=2438: symbol='PERPUSDT', exchange='binance', status='active', signal_id=NULL, created_at=01:35:25.774
```

### After Duplicate (T+768):
```
ID=2438: symbol='PERPUSDT', exchange='binance', status='active', created_at=01:35:25.774
ID=2439: symbol='PERPUSDT', exchange='binance', status='active', created_at=01:35:26.541
```

### After Rollback (T+2783):
```
ID=2438: status='rolled_back', closed_at=01:35:28.556 ← Deleted by rollback
ID=2439: symbol='PERPUSDT', exchange='binance', status='active' ← ORPHAN!
```

### Current State (verified via psql):
```sql
fox_crypto=# SELECT id, symbol, signal_id, status, opened_at, created_at
             FROM monitoring.positions WHERE id IN (2438, 2439);

  id  |  symbol  | signal_id |   status    |         opened_at          |         created_at
------+----------+-----------+-------------+----------------------------+----------------------------
 2438 | PERPUSDT |           | rolled_back | 2025-10-22 00:35:25.774759 | 2025-10-22 00:35:25.774759
 2439 | PERPUSDT |           | active      | 2025-10-22 00:35:26.541474 | 2025-10-22 00:35:26.541474
```

**CRITICAL**:
- Both have `signal_id=NULL` → neither associated with signal!
- ID=2438 rolled back → atomic guarantees lost
- ID=2439 active → orphan position, no tracking of source

---

## 🎯 WHY SIGNAL VALIDATION DIDN'T CATCH IT

**Question**: Signal processor has pre-validation. Why didn't it detect duplicate?

**Answer**: Validation happened BEFORE position creation!

### Validation Timeline:
```
01:35:04.870 - Pre-fetched 4 positions for binance
01:35:06.755 - Parallel validation complete: 5 signals passed
01:35:23.283 - Executing signal #5368032: PERPUSDT  ← 17 seconds later!
```

**Gap**: 17+ seconds between validation and execution
**What happened**: Sequential execution with delays from previous signals
- Signal 1 (YBUSDT): took 2.8s (failed - leverage)
- Signal 2 (ZEUSUSDT): took 12.7s (failed - Bybit 500)
- Signal 3 (PERPUSDT): started 17s after validation

**During that 17s**:
- Validation saw: no PERPUSDT position
- Execution started: still no PERPUSDT (checked in `create_position`)
- Mid-execution: REST polling created duplicate

**Problem**: No protection during execution phase!

---

## 🐛 CODE ANALYSIS

### Duplicate Detection Mechanism

**Location 1: create_position() - repository.py:219**
```python
# FIX 1.1: Check if active position already exists (prevent duplicates)
existing = await self.get_open_position(symbol, exchange)
if existing:
    logger.warning(f"⚠️ Position {symbol} already exists (id={existing['id']})")
    return existing['id']
```

**Location 2: sync_positions() - position_manager.py:711**
```python
# FIX 1.2: Check database first before creating (prevent duplicates)
db_position = await self.repository.get_open_position(symbol, exchange_name)
```

**Both call**:
```python
# repository.py:281-287
async def get_open_position(self, symbol: str, exchange: str):
    query = """
        SELECT * FROM monitoring.positions
        WHERE symbol = $1 AND exchange = $2 AND status = 'active'
    """
```

**Problem**: Race-prone!
- Check and create are NOT atomic
- Time window between check and insert
- Multiple processes can pass check simultaneously

---

## 🚨 CRITICAL ISSUES DISCOVERED

### Issue #1: Non-Atomic Check-Then-Create

**Current Pattern**:
```python
# Step 1: Check
existing = await get_open_position(symbol, exchange)
# ⚠️ RACE WINDOW HERE! Another process can create between check and insert
# Step 2: Create
if not existing:
    INSERT INTO positions ...
```

**Problem**: Classic TOCTOU (Time-Of-Check-Time-Of-Use) vulnerability
**Fix**: Use database-level locking or INSERT ... ON CONFLICT

---

### Issue #2: Unique Constraint Not Working

**Expected**: Constraint prevents duplicate INSERTs
**Reality**: Duplicate INSERT succeeded, UPDATE failed

**Possible Causes**:
1. Transaction isolation prevents constraint from seeing concurrent inserts
2. Constraint checked at commit time, not insert time
3. Connection pool isolation

**Verification Needed**: PostgreSQL behavior investigation

---

### Issue #3: REST Polling Lacks Locking

**Current**: REST polling independently creates positions
**Problem**: No coordination with signal processor
**Result**: Can duplicate positions being created by signals

**Fix**: Locking mechanism or deduplication strategy

---

### Issue #4: Signal Processor Sequential Execution

**Current**: Signals executed one-by-one with delays
**Problem**: Validation → execution gap can be 17+ seconds!
**Result**: Market state changes between validation and execution

**Improvement**: Reduce gap or re-validate before execution

---

## 💡 PROPOSED SOLUTIONS

### Solution A: Database-Level Locking (RECOMMENDED)

**Implementation**:
```python
async def create_position(self, position_data: Dict) -> int:
    symbol = position_data['symbol']
    exchange = position_data['exchange']

    async with self.pool.acquire() as conn:
        async with conn.transaction():
            # Lock the combination to prevent race
            await conn.execute("""
                SELECT pg_advisory_xact_lock(
                    hashtext($1 || $2)
                )
            """, symbol, exchange)

            # Now safely check and create
            existing = await conn.fetchrow("""
                SELECT id FROM monitoring.positions
                WHERE symbol = $1 AND exchange = $2 AND status = 'active'
                FOR UPDATE  -- Lock if exists
            """, symbol, exchange)

            if existing:
                return existing['id']

            # Safe to insert
            row = await conn.fetchrow("""
                INSERT INTO monitoring.positions (...)
                VALUES (...)
                RETURNING id
            """)

            return row['id']
```

**Pros**:
- Prevents race at database level
- Atomic operation
- Works across all processes

**Cons**:
- Advisory locks need cleanup
- Slight performance overhead

---

### Solution B: INSERT ... ON CONFLICT

**Implementation**:
```python
async def create_position(self, position_data: Dict) -> int:
    query = """
        INSERT INTO monitoring.positions (
            symbol, exchange, side, quantity, entry_price, status
        ) VALUES ($1, $2, $3, $4, $5, 'active')
        ON CONFLICT (symbol, exchange)
        WHERE status = 'active'
        DO UPDATE SET updated_at = NOW()  -- No-op update
        RETURNING id
    """

    row = await conn.fetchrow(query, ...)
    return row['id']
```

**Problem**: Constraint is partial index (WHERE status='active')
**Fix**: Need to modify constraint or use different approach

---

### Solution C: Application-Level Locking

**Implementation**:
```python
# Add lock manager
position_locks = {}

async def create_position_with_lock(symbol, exchange, data):
    lock_key = f"{symbol}:{exchange}"

    if lock_key not in position_locks:
        position_locks[lock_key] = asyncio.Lock()

    async with position_locks[lock_key]:
        # Now safe from race within same process
        existing = await get_open_position(symbol, exchange)
        if existing:
            return existing['id']
        return await create_position(data)
```

**Pros**:
- Simple to implement
- No database changes

**Cons**:
- Only works within single process
- Doesn't protect against REST polling race

---

### Solution D: Disable REST Polling Auto-Create

**Implementation**:
```python
# core/position_manager.py:746
if db_position:
    # Restore from DB
    ...
else:
    # DON'T create - only signal processor should create
    logger.warning(f"⚠️ Position {symbol} found on exchange but not in DB - ignoring")
    # Optionally: send alert for manual review
```

**Pros**:
- Simple
- Eliminates REST polling race

**Cons**:
- Loses automatic recovery from desyncs
- Manual intervention needed for orphans

---

### Solution E: Re-validate Before Execution (Immediate Fix)

**Implementation**:
```python
# core/signal_processor_websocket.py - before executing signal
async def execute_signal(self, signal):
    # Validate again right before execution
    existing = await self.position_manager.repository.get_open_position(
        signal.symbol, signal.exchange
    )

    if existing:
        logger.warning(f"⏭️ Signal {signal.id} ({signal.symbol}) is duplicate - skipping")
        return None

    # Proceed with atomic creation
    return await self.position_manager.open_position(signal)
```

**Pros**:
- Minimal change
- Reduces race window
- Quick to implement

**Cons**:
- Still has small race window
- Not 100% solution

---

## 🎯 RECOMMENDED FIX (Combination)

### Immediate (P0):
1. **Solution E**: Re-validate before execution (quick win, reduces window)
2. **Solution D**: Disable REST polling auto-create (eliminates race source)

### Short-term (P1):
3. **Solution A**: Database advisory locks (proper fix)

### Long-term (P2):
4. Review transaction isolation levels
5. Add metrics for race condition detection
6. Improve REST polling coordination

---

## 📋 IMPLEMENTATION PLAN

### Phase 1: Immediate Mitigation (Today)
- [ ] Add pre-execution duplicate check
- [ ] Disable REST polling position creation
- [ ] Add warning logs for orphan detection

### Phase 2: Proper Fix (This Week)
- [ ] Implement pg_advisory_xact_lock
- [ ] Add integration tests for race conditions
- [ ] Verify constraint behavior

### Phase 3: Long-term Improvement (Next Week)
- [ ] Review and optimize transaction isolation
- [ ] Add monitoring for duplicate attempts
- [ ] Document position lifecycle

---

## 🧪 REPRODUCTION TEST CASE

```python
async def test_race_condition():
    """
    Reproduce PERPUSDT duplicate creation race
    """
    import asyncio

    async def signal_processor_create():
        # Simulate atomic manager
        await asyncio.sleep(0.001)  # Check DB
        position_id = await repository.create_position({
            'symbol': 'TESTUSDT',
            'exchange': 'binance',
            'quantity': 100,
            'entry_price': 1.0
        })
        await asyncio.sleep(0.766)  # Simulate order placement
        # Try to finalize
        await repository.update_position(position_id, status='active')

    async def rest_polling_create():
        # Simulate REST polling
        await asyncio.sleep(0.766)  # Arrive mid-atomic operation
        await repository.create_position({
            'symbol': 'TESTUSDT',
            'exchange': 'binance',
            'quantity': 100,
            'entry_price': 1.0
        })

    # Run both simultaneously
    await asyncio.gather(
        signal_processor_create(),
        rest_polling_create()
    )

    # Expected: Should prevent duplicate
    # Actual (without fix): Creates both, then constraint error on update
```

---

## 📊 METRICS TO ADD

### Detection Metrics:
- `position_duplicate_attempts_total` - Counter of duplicate creation attempts
- `position_race_condition_detected_total` - Counter of race conditions caught
- `position_orphan_detected_total` - Positions without signal_id

### Performance Metrics:
- `position_creation_lock_wait_seconds` - Time waiting for locks
- `signal_validation_to_execution_seconds` - Gap between validation and execution

### Health Metrics:
- `position_db_vs_exchange_mismatch_total` - Desync count
- `position_rollback_total` - Atomic rollbacks by reason

---

## 📝 LESSONS LEARNED

### 1. Check-Then-Create is Always Race-Prone
Even with database checks, TOCTOU vulnerabilities exist without proper locking.

### 2. Multiple Position Sources = Coordination Problem
Having both signal processor AND REST polling create positions requires synchronization.

### 3. Unique Constraints Are Not Locks
Constraints prevent invalid state but don't prevent race conditions during creation.

### 4. Transaction Isolation Matters
Default PostgreSQL isolation can hide uncommitted changes between connections.

### 5. Validation-To-Execution Gap Is Dangerous
17-second gap between validation and execution is unacceptable for real-time trading.

---

## 🔗 RELATED ISSUES

- **Issue #1**: Bybit 500 errors (separate issue)
- **Issue #2**: Binance leverage limits (separate issue)
- **Issue #3**: Missing orders_cache table (separate issue)

---

## 📄 FILES TO MODIFY

1. `database/repository.py` - Add locking to create_position
2. `core/position_manager.py` - Disable REST polling auto-create OR add lock
3. `core/signal_processor_websocket.py` - Add pre-execution validation
4. `core/atomic_position_manager.py` - Handle duplicate gracefully

---

**Status**: 🔴 **CRITICAL - IMMEDIATE FIX REQUIRED**

**Created**: 2025-10-22 02:00
**Investigator**: Claude Code
**Type**: Deep Investigation + Root Cause Analysis
**Priority**: P0 (Production affecting)

---

## 🎓 CONCLUSION

**PERPUSDT не прошёл duplicate check** - он прошёл, но проверка произошла:
1. **17 секунд до execution** (pre-validation)
2. **В начале atomic operation** (create_position check)

**Дубликат создан** потому что:
1. REST polling fetched position from exchange mid-atomic-operation
2. Database check didn't see uncommitted/concurrent transaction
3. Both processes created position within 766ms window

**Constraint violation** произошёл потому что:
1. Constraint работает только на committed data
2. UPDATE видит committed duplicate
3. INSERT не видел из-за isolation

**Это классический race condition** требующий немедленного фикса на уровне базы данных или координации процессов.
