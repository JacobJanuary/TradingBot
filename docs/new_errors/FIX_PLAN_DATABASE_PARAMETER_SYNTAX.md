# 🔧 FIX PLAN: Database Parameter Syntax Error (asyncpg)

**Priority:** 🟡 P2 - HIGH (doesn't block trading but breaks aged monitoring)
**File:** `database/repository.py`
**Function:** `update_aged_position()` (lines 1134-1195)
**Estimated Time:** 15 minutes
**Risk:** VERY LOW (straightforward syntax conversion)

---

## 📋 PROBLEM SUMMARY

**ERROR:** `update_aged_position()` uses psycopg2 parameter syntax `%(name)s` with asyncpg which requires `$1, $2` syntax.

**Current Error:**
```
Connection.fetchval() got an unexpected keyword argument 'position_id'
```

**Impact:**
- ❌ Aged position updates FAIL
- ❌ State persistence BROKEN
- ❌ Phase transitions NOT saved
- ✅ Trading continues (error isolated)

**Introduced in:** Commit 3348a50 (Database Schema Fix)

---

## 🎯 SOLUTION STRATEGY

**Convert from psycopg2 to asyncpg syntax:**

**FROM (psycopg2):**
```python
query = "WHERE position_id = %(position_id)s"
result = await conn.fetchval(query, **params)  # ❌ Named parameters
```

**TO (asyncpg):**
```python
query = "WHERE position_id = $1"
result = await conn.fetchval(query, position_id_value)  # ✅ Positional parameters
```

**Challenge:** Dynamic query building (variable number of parameters based on which fields are updated)

**Solution:** Build positional parameter list dynamically

---

## 🔧 IMPLEMENTATION PLAN

### Current Code (BROKEN)

**Lines 1134-1195:**
```python
async def update_aged_position(
    self,
    position_id: str,
    phase: str = None,
    target_price: Decimal = None,
    hours_aged: float = None,
    loss_tolerance: Decimal = None
) -> bool:
    """Update aged position fields"""

    if not any([phase, target_price, hours_aged, loss_tolerance]):
        logger.warning(f"No fields to update for position {position_id}")
        return False

    fields = ['updated_at = NOW()']
    params = {'position_id': position_id}  # ❌ Dict for named params

    if phase is not None:
        fields.append('phase = %(phase)s')  # ❌ Named placeholder
        params['phase'] = phase

    if target_price is not None:
        fields.append('target_price = %(target_price)s')  # ❌ Named placeholder
        params['target_price'] = target_price

    if hours_aged is not None:
        fields.append('hours_aged = %(hours_aged)s')  # ❌ Named placeholder
        params['hours_aged'] = hours_aged

    if loss_tolerance is not None:
        fields.append('loss_tolerance = %(loss_tolerance)s')  # ❌ Named placeholder
        params['loss_tolerance'] = loss_tolerance

    query = f"""
        UPDATE monitoring.aged_positions
        SET {', '.join(fields)}
        WHERE position_id = %(position_id)s  # ❌ Named placeholder
        RETURNING id
    """

    async with self.pool.acquire() as conn:
        try:
            result = await conn.fetchval(query, **params)  # ❌ Named params unpacking
            if result:
                logger.info(f"Updated aged position {position_id}: {', '.join(params.keys())}")
                return True
            else:
                logger.warning(f"Aged position for position_id {position_id} not found")
                return False
        except Exception as e:
            logger.error(f"Failed to update aged position: {e}")
            return False
```

---

### Fixed Code (CORRECT)

**Lines 1134-1195:**
```python
async def update_aged_position(
    self,
    position_id: str,
    phase: str = None,
    target_price: Decimal = None,
    hours_aged: float = None,
    loss_tolerance: Decimal = None
) -> bool:
    """Update aged position fields

    Args:
        position_id: Position ID (matches position_id column, not aged position id)
        phase: New phase (e.g., 'grace', 'progressive', 'stale')
        target_price: Updated target price
        hours_aged: Current age in hours
        loss_tolerance: Loss tolerance as decimal (e.g., 0.015 for 1.5%)

    Returns:
        True if updated successfully, False otherwise
    """
    if not any([phase, target_price, hours_aged, loss_tolerance]):
        logger.warning(f"No fields to update for position {position_id}")
        return False

    # Build SET clause and parameter list dynamically
    set_fields = ['updated_at = NOW()']
    params = []  # ✅ List for positional params
    param_idx = 1  # asyncpg uses $1, $2, $3, ...

    # Track parameter names for logging
    param_names = []

    if phase is not None:
        set_fields.append(f'phase = ${param_idx}')  # ✅ Positional placeholder
        params.append(phase)
        param_names.append('phase')
        param_idx += 1

    if target_price is not None:
        set_fields.append(f'target_price = ${param_idx}')  # ✅ Positional placeholder
        params.append(target_price)
        param_names.append('target_price')
        param_idx += 1

    if hours_aged is not None:
        set_fields.append(f'hours_aged = ${param_idx}')  # ✅ Positional placeholder
        params.append(hours_aged)
        param_names.append('hours_aged')
        param_idx += 1

    if loss_tolerance is not None:
        set_fields.append(f'loss_tolerance = ${param_idx}')  # ✅ Positional placeholder
        params.append(loss_tolerance)
        param_names.append('loss_tolerance')
        param_idx += 1

    # position_id is the last parameter (for WHERE clause)
    params.append(str(position_id))
    param_names.append('position_id')

    query = f"""
        UPDATE monitoring.aged_positions
        SET {', '.join(set_fields)}
        WHERE position_id = ${param_idx}  # ✅ Positional placeholder
        RETURNING id
    """

    async with self.pool.acquire() as conn:
        try:
            result = await conn.fetchval(query, *params)  # ✅ Positional params unpacking
            if result:
                logger.info(f"Updated aged position {position_id}: {', '.join(param_names)}")
                return True
            else:
                logger.warning(f"Aged position for position_id {position_id} not found")
                return False
        except Exception as e:
            logger.error(f"Failed to update aged position: {e}")
            return False
```

---

## 📝 CHANGES SUMMARY

### What Changes

**1. Parameter Storage:**
```python
# BEFORE
params = {'position_id': position_id}  # Dict

# AFTER
params = []  # List
param_names = []  # For logging
```

**2. Placeholder Syntax:**
```python
# BEFORE
fields.append('phase = %(phase)s')

# AFTER
set_fields.append(f'phase = ${param_idx}')
```

**3. Parameter Tracking:**
```python
# BEFORE
params['phase'] = phase

# AFTER
params.append(phase)
param_names.append('phase')
param_idx += 1
```

**4. WHERE Clause:**
```python
# BEFORE
WHERE position_id = %(position_id)s

# AFTER
WHERE position_id = ${param_idx}  # param_idx is incremented for each field
```

**5. fetchval Call:**
```python
# BEFORE
result = await conn.fetchval(query, **params)

# AFTER
result = await conn.fetchval(query, *params)
```

**6. Logging:**
```python
# BEFORE
logger.info(f"Updated aged position {position_id}: {', '.join(params.keys())}")

# AFTER
logger.info(f"Updated aged position {position_id}: {', '.join(param_names)}")
```

---

## 🧪 TESTING EXAMPLES

### Example 1: Update Phase Only

**Call:**
```python
await repository.update_aged_position(
    position_id='2532',
    phase='progressive'
)
```

**Generated Query:**
```sql
UPDATE monitoring.aged_positions
SET updated_at = NOW(), phase = $1
WHERE position_id = $2
RETURNING id
```

**Parameters:** `['progressive', '2532']`

---

### Example 2: Update Multiple Fields

**Call:**
```python
await repository.update_aged_position(
    position_id='2532',
    phase='progressive',
    target_price=Decimal('1.5'),
    hours_aged=22,
    loss_tolerance=Decimal('0.015')
)
```

**Generated Query:**
```sql
UPDATE monitoring.aged_positions
SET updated_at = NOW(), phase = $1, target_price = $2, hours_aged = $3, loss_tolerance = $4
WHERE position_id = $5
RETURNING id
```

**Parameters:** `['progressive', Decimal('1.5'), 22, Decimal('0.015'), '2532']`

---

### Example 3: Update Target Price Only

**Call:**
```python
await repository.update_aged_position(
    position_id='2544',
    target_price=Decimal('2.1')
)
```

**Generated Query:**
```sql
UPDATE monitoring.aged_positions
SET updated_at = NOW(), target_price = $1
WHERE position_id = $2
RETURNING id
```

**Parameters:** `[Decimal('2.1'), '2544']`

---

## ✅ VERIFICATION CHECKLIST

### Code Changes

- [ ] `params = []` (list instead of dict)
- [ ] `param_names = []` added for logging
- [ ] `param_idx = 1` counter added
- [ ] All placeholders use `${param_idx}` syntax
- [ ] `param_idx += 1` after each field
- [ ] WHERE clause uses `${param_idx}`
- [ ] `fetchval(query, *params)` uses positional unpacking
- [ ] Logging uses `param_names` instead of `params.keys()`
- [ ] Python syntax valid

### Logic Verification

- [ ] Updated fields added to query dynamically
- [ ] position_id always last parameter
- [ ] param_idx increments correctly
- [ ] No gaps in parameter numbering ($1, $2, $3, ...)
- [ ] All parameter values added to list
- [ ] Parameter names tracked for logging

---

## 🧪 TESTING PLAN

### Test 1: Database Update Works

**Setup:**
```sql
-- Verify record exists
SELECT * FROM monitoring.aged_positions WHERE position_id = '2532';
```

**Test:**
```python
# Update phase
success = await repository.update_aged_position(
    position_id='2532',
    phase='emergency'
)
assert success == True
```

**Verify:**
```sql
SELECT phase, updated_at FROM monitoring.aged_positions WHERE position_id = '2532';
-- Expected: phase = 'emergency', updated_at = recent timestamp
```

**Expected Log:**
```
INFO - Updated aged position 2532: phase, position_id
```

---

### Test 2: Multiple Field Update

**Test:**
```python
success = await repository.update_aged_position(
    position_id='2532',
    phase='progressive',
    target_price=Decimal('1.8'),
    hours_aged=25,
    loss_tolerance=Decimal('0.02')
)
assert success == True
```

**Verify:**
```sql
SELECT phase, target_price, hours_aged, loss_tolerance, updated_at
FROM monitoring.aged_positions
WHERE position_id = '2532';
-- Expected: all fields updated with new values
```

**Expected Log:**
```
INFO - Updated aged position 2532: phase, target_price, hours_aged, loss_tolerance, position_id
```

---

### Test 3: Position Not Found

**Test:**
```python
success = await repository.update_aged_position(
    position_id='99999',  # Non-existent
    phase='grace'
)
assert success == False
```

**Expected Log:**
```
WARNING - Aged position for position_id 99999 not found
```

---

### Test 4: No Fields to Update

**Test:**
```python
success = await repository.update_aged_position(
    position_id='2532'
    # No optional fields provided
)
assert success == False
```

**Expected Log:**
```
WARNING - No fields to update for position 2532
```

---

### Test 5: State Persistence (Integration)

**Test:**
```python
# 1. Create aged position via aged_position_monitor
# 2. Trigger phase transition
# 3. Verify database updated
# 4. Restart bot
# 5. Verify state recovered correctly
```

**Expected:** Phase transition saved and recovered after restart

---

## 🚀 DEPLOYMENT PLAN

### Pre-Deployment

- [ ] Read current code (lines 1134-1195)
- [ ] Verify exact function structure
- [ ] Plan replacement strategy

### Deployment

- [ ] Replace entire function (lines 1134-1195)
- [ ] Verify syntax: `python3 -m py_compile database/repository.py`
- [ ] Git commit with detailed message
- [ ] Push to origin/main

### Post-Deployment

- [ ] Monitor logs for aged position updates
- [ ] Run Test 1 (database update)
- [ ] Run Test 2 (multiple fields)
- [ ] Verify state persistence works
- [ ] Check aged position recovery on restart

---

## 🔄 ROLLBACK PLAN

### If Issues Occur

**Option 1: Git Revert**
```bash
git revert HEAD
git push origin main
# Returns to error state (but error is isolated, bot continues)
```

**Option 2: Quick Disable**
```python
# Temporarily disable aged position updates
if True:  # Quick disable flag
    logger.warning(f"Aged position updates temporarily disabled")
    return False
```

**Safety:** Rollback safe - aged monitoring works in memory, DB updates optional

---

## 📊 EXPECTED RESULTS

### Before Fix

**Logs:**
```
ERROR - Failed to update aged position: Connection.fetchval() got an unexpected keyword argument 'position_id'
```

**Database:**
```sql
SELECT updated_at FROM monitoring.aged_positions WHERE position_id = '2532';
-- updated_at: 2025-10-23 19:13:51  (OLD, not updating)
```

**Impact:** State not persisted, lost on restart

---

### After Fix

**Logs:**
```
INFO - Updated aged position 2532: phase, target_price, position_id
```

**Database:**
```sql
SELECT updated_at FROM monitoring.aged_positions WHERE position_id = '2532';
-- updated_at: 2025-10-26 16:45:00  (RECENT, updating correctly)
```

**Impact:** State persisted, recoverable on restart

---

### Metrics

| Metric | Before | After |
|--------|--------|-------|
| Update errors | 100% | 0% |
| State persistence | BROKEN | WORKING |
| Recovery on restart | FAILS | WORKS |
| Database updates | FAIL | SUCCESS |

---

## 🔐 RISK ASSESSMENT

### Implementation Risk: VERY LOW 🟢

**Why:**
- Simple syntax conversion
- asyncpg is well-documented standard
- Pattern used elsewhere in codebase (lines 492, 1269)
- Logic unchanged, only syntax
- Error is isolated (doesn't crash bot)

### Testing Risk: LOW 🟢

**Why:**
- Easy to test (database query)
- Observable result (updated_at timestamp)
- Can verify with SQL queries
- No trading impact if wrong

### Deployment Risk: VERY LOW 🟢

**Why:**
- No trading functionality affected
- Aged monitoring optional feature
- Error already occurring (can't get worse)
- Rollback simple and safe

---

## 🎯 SUCCESS CRITERIA

### Implementation Success

✅ **Code:**
- params is list (not dict)
- Placeholders use $1, $2, $3
- fetchval uses *params
- Syntax valid
- Git committed and pushed

### Runtime Success

✅ **Logs:**
- "Updated aged position X" messages (not errors)
- Parameter names logged correctly
- No "unexpected keyword argument" errors

✅ **Database:**
- updated_at timestamps recent
- Phase transitions saved
- State persistence works
- Recovery on restart works

---

## 📚 REFERENCE: asyncpg vs psycopg2

### psycopg2 (WRONG for our use case)

```python
# Named parameters
query = "SELECT * FROM table WHERE id = %(id)s AND name = %(name)s"
cursor.execute(query, {'id': 123, 'name': 'test'})
```

### asyncpg (CORRECT for our use case)

```python
# Positional parameters
query = "SELECT * FROM table WHERE id = $1 AND name = $2"
result = await conn.fetchval(query, 123, 'test')
```

### Our Codebase Examples

**Correct usage (line 492):**
```python
query = "WHERE symbol = $1 AND exchange = $2"
result = await conn.fetchval(query, symbol, exchange)  # ✅
```

**Correct usage (line 1269):**
```python
query = "WHERE position_id = $1"
result = await conn.fetchval(query, str(position_id))  # ✅
```

**Broken usage (line 1186):**
```python
query = "WHERE position_id = %(position_id)s"
result = await conn.fetchval(query, **params)  # ❌
```

---

**Plan Status:** ✅ READY FOR IMPLEMENTATION
**Created by:** Claude Code
**Date:** 2025-10-26 16:42:00
**Priority:** 🟡 P2 - HIGH
**Estimated Time:** 15 minutes
**Risk:** VERY LOW 🟢
