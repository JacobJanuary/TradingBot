# 🔧 DETAILED FIX PLAN: Database asyncpg Parameter Syntax

**Priority:** 🟡 P2 - HIGH
**File:** `database/repository.py`
**Functions:** 2 (update_aged_position, get_aged_positions_statistics)
**Estimated Time:** 20 minutes
**Risk:** LOW 🟢
**Investigation:** `DATABASE_ASYNCPG_PARAMETER_SYNTAX_DEEP_INVESTIGATION.md`

---

## 📋 EXECUTIVE SUMMARY

**Problem:** Two functions use psycopg2 parameter syntax `%(name)s` incompatible with asyncpg `$1, $2` syntax.

**Solution:** Convert to asyncpg positional parameter syntax.

**Functions to Fix:**
1. 🔴 `update_aged_position()` (lines 1134-1195) - **CRITICAL** (production code)
2. 🟢 `get_aged_positions_statistics()` (lines 1286-1365) - **LOW** (test code only)

**Deployment Strategy:** Fix both in one commit (they're related)

---

## 🎯 FIX #1: update_aged_position() - CRITICAL

### Function Overview

**Location:** `database/repository.py:1134-1195`
**Status:** ❌ BROKEN (100% failure rate)
**Usage:** Production (4 call sites in aged_position_monitor_v2.py)
**Complexity:** MEDIUM (dynamic query building)

### Current Code (BROKEN)

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

    # ❌ BROKEN: Dict for named parameters
    fields = ['updated_at = NOW()']
    params = {'position_id': position_id}

    if phase is not None:
        fields.append('phase = %(phase)s')  # ❌ psycopg2 syntax
        params['phase'] = phase

    if target_price is not None:
        fields.append('target_price = %(target_price)s')  # ❌ psycopg2 syntax
        params['target_price'] = target_price

    if hours_aged is not None:
        fields.append('hours_aged = %(hours_aged)s')  # ❌ psycopg2 syntax
        params['hours_aged'] = hours_aged

    if loss_tolerance is not None:
        fields.append('loss_tolerance = %(loss_tolerance)s')  # ❌ psycopg2 syntax
        params['loss_tolerance'] = loss_tolerance

    query = f"""
        UPDATE monitoring.aged_positions
        SET {', '.join(fields)}
        WHERE position_id = %(position_id)s  # ❌ psycopg2 syntax
        RETURNING id
    """

    async with self.pool.acquire() as conn:
        try:
            result = await conn.fetchval(query, **params)  # ❌ Named params
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

### Fixed Code (CORRECT)

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

    # ✅ FIXED: Build positional parameter list for asyncpg
    set_fields = ['updated_at = NOW()']
    params = []  # ✅ List for positional params
    param_names = []  # Track names for logging
    param_idx = 1  # asyncpg uses $1, $2, $3, ...

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

### Changes Summary

| Line | Change Type | Before | After |
|------|-------------|--------|-------|
| 1158 | Variable type | `fields = [...]` | `set_fields = [...]` |
| 1159 | Variable type | `params = {}` (dict) | `params = []` (list) |
| 1159 | Add tracking | - | `param_names = []` |
| 1159 | Add counter | - | `param_idx = 1` |
| 1162 | Placeholder | `'phase = %(phase)s'` | `f'phase = ${param_idx}'` |
| 1163 | Param add | `params['phase'] = phase` | `params.append(phase)` |
| 1163 | Track name | - | `param_names.append('phase')` |
| 1163 | Increment | - | `param_idx += 1` |
| 1166 | Placeholder | `'target_price = %(target_price)s'` | `f'target_price = ${param_idx}'` |
| 1167 | Param add | `params['target_price'] = target_price` | `params.append(target_price)` |
| 1167 | Track name | - | `param_names.append('target_price')` |
| 1167 | Increment | - | `param_idx += 1` |
| 1170 | Placeholder | `'hours_aged = %(hours_aged)s'` | `f'hours_aged = ${param_idx}'` |
| 1171 | Param add | `params['hours_aged'] = hours_aged` | `params.append(hours_aged)` |
| 1171 | Track name | - | `param_names.append('hours_aged')` |
| 1171 | Increment | - | `param_idx += 1` |
| 1174 | Placeholder | `'loss_tolerance = %(loss_tolerance)s'` | `f'loss_tolerance = ${param_idx}'` |
| 1175 | Param add | `params['loss_tolerance'] = loss_tolerance` | `params.append(loss_tolerance)` |
| 1175 | Track name | - | `param_names.append('loss_tolerance')` |
| 1175 | Increment | - | `param_idx += 1` |
| +4 | Add last param | - | `params.append(str(position_id))` |
| +4 | Track name | - | `param_names.append('position_id')` |
| 1179 | Query SET | `{', '.join(fields)}` | `{', '.join(set_fields)}` |
| 1180 | WHERE clause | `%(position_id)s` | `${param_idx}` |
| 1186 | fetchval call | `**params` | `*params` |
| 1188 | Logging | `params.keys()` | `param_names` |

**Total Changes:** ~30 lines modified/added

---

## 🎯 FIX #2: get_aged_positions_statistics() - LOW PRIORITY

### Function Overview

**Location:** `database/repository.py:1286-1365`
**Status:** ❌ BROKEN (but not used)
**Usage:** Test code ONLY (not called in production)
**Complexity:** LOW (only 2 fixed parameters)

### Current Code (BROKEN)

```python
async def get_aged_positions_statistics(
    self,
    from_date: datetime = None,
    to_date: datetime = None
) -> Dict:
    """Get aged positions statistics"""

    if not from_date:
        from_date = now_utc() - timedelta(days=7)
    if not to_date:
        to_date = now_utc()

    query = """
        WITH stats AS (
            SELECT
                COUNT(*) as total_count,
                ...
            FROM monitoring.aged_positions
            WHERE detected_at BETWEEN %(from_date)s AND %(to_date)s  # ❌ psycopg2
        ),
        close_reasons AS (
            SELECT
                close_reason,
                COUNT(*) as count
            FROM monitoring.aged_positions
            WHERE detected_at BETWEEN %(from_date)s AND %(to_date)s  # ❌ psycopg2
                AND close_reason IS NOT NULL
            GROUP BY close_reason
        )
        ...
    """

    params = {
        'from_date': from_date,
        'to_date': to_date
    }  # ❌ Dict

    async with self.pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, **params)  # ❌ Named params
            ...
```

### Fixed Code (CORRECT)

```python
async def get_aged_positions_statistics(
    self,
    from_date: datetime = None,
    to_date: datetime = None
) -> Dict:
    """Get aged positions statistics

    Args:
        from_date: Start date for statistics (default: 7 days ago)
        to_date: End date for statistics (default: now)

    Returns:
        Dictionary with various statistics
    """
    if not from_date:
        from_date = now_utc() - timedelta(days=7)
    if not to_date:
        to_date = now_utc()

    # ✅ FIXED: Use positional parameters for asyncpg
    query = """
        WITH stats AS (
            SELECT
                COUNT(*) as total_count,
                COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_count,
                COUNT(CASE WHEN status = 'error' THEN 1 END) as error_count,
                AVG(hours_aged) as avg_age_hours,
                AVG(actual_pnl_percent) as avg_pnl_percent,
                AVG(close_attempts) as avg_close_attempts,
                AVG(EXTRACT(EPOCH FROM (closed_at - detected_at))) as avg_close_duration
            FROM monitoring.aged_positions
            WHERE detected_at BETWEEN $1 AND $2  /* ✅ Positional params */
        ),
        close_reasons AS (
            SELECT
                close_reason,
                COUNT(*) as count
            FROM monitoring.aged_positions
            WHERE detected_at BETWEEN $1 AND $2  /* ✅ Positional params */
                AND close_reason IS NOT NULL
            GROUP BY close_reason
        )
        SELECT
            s.*,
            COALESCE(
                json_object_agg(cr.close_reason, cr.count),
                '{}'::json
            ) as by_close_reason
        FROM stats s
        CROSS JOIN close_reasons cr
        GROUP BY s.total_count, s.closed_count, s.error_count,
                 s.avg_age_hours, s.avg_pnl_percent,
                 s.avg_close_attempts, s.avg_close_duration
    """

    async with self.pool.acquire() as conn:
        try:
            # ✅ FIXED: Pass positional parameters
            row = await conn.fetchrow(query, from_date, to_date)
            if row:
                result = dict(row)
                # Calculate success rate
                if result['total_count'] > 0:
                    result['success_rate'] = (result['closed_count'] / result['total_count']) * 100
                else:
                    result['success_rate'] = 0
                return result
            else:
                return {
                    'total_count': 0,
                    'closed_count': 0,
                    'error_count': 0,
                    'success_rate': 0,
                    'by_close_reason': {}
                }
        except Exception as e:
            logger.error(f"Failed to get aged positions statistics: {e}")
            return {
                'total_count': 0,
                'error_count': 1,
                'by_close_reason': {}
            }
```

### Changes Summary

| Line | Change Type | Before | After |
|------|-------------|--------|-------|
| 1316 | Placeholder | `%(from_date)s` | `$1` |
| 1316 | Placeholder | `%(to_date)s` | `$2` |
| 1323 | Placeholder | `%(from_date)s` | `$1` |
| 1323 | Placeholder | `%(to_date)s` | `$2` |
| 1340-1343 | Remove | `params = {...}` | (deleted) |
| 1347 | fetchrow call | `**params` | `from_date, to_date` |

**Total Changes:** 6 lines modified, 4 lines removed

---

## 📝 IMPLEMENTATION STEPS

### Step 1: Read Current Code

```bash
# Read both functions to verify exact line numbers
read_file database/repository.py 1134:1195
read_file database/repository.py 1286:1365
```

### Step 2: Apply Fix #1 (update_aged_position)

**Method:** Replace entire function (lines 1134-1195)

**Verification:**
- Check syntax: `python3 -m py_compile database/repository.py`
- Verify positional parameter order
- Confirm parameter names tracked

### Step 3: Apply Fix #2 (get_aged_positions_statistics)

**Method:** Replace query and fetchrow call

**Verification:**
- Check syntax: `python3 -m py_compile database/repository.py`
- Verify parameter order ($1=from_date, $2=to_date)

### Step 4: Final Verification

```bash
# Search for remaining psycopg2-style parameters
grep -n "%(" database/repository.py
# Expected: No matches

# Search for **params usage
grep -n "\*\*params" database/repository.py
# Expected: No matches (or only in comments)
```

---

## 🧪 TESTING PLAN

### Test 1: Single Field Update

**Code:**
```python
success = await repository.update_aged_position(
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

**Expected Log:**
```
INFO - Updated aged position 2532: phase, position_id
```

### Test 2: Multiple Fields Update

**Code:**
```python
success = await repository.update_aged_position(
    position_id='2532',
    phase='progressive',
    target_price=Decimal('1.8'),
    hours_aged=25,
    loss_tolerance=Decimal('0.02')
)
```

**Generated Query:**
```sql
UPDATE monitoring.aged_positions
SET updated_at = NOW(), phase = $1, target_price = $2, hours_aged = $3, loss_tolerance = $4
WHERE position_id = $5
RETURNING id
```

**Parameters:** `['progressive', Decimal('1.8'), 25, Decimal('0.02'), '2532']`

**Expected Log:**
```
INFO - Updated aged position 2532: phase, target_price, hours_aged, loss_tolerance, position_id
```

### Test 3: Position Not Found

**Code:**
```python
success = await repository.update_aged_position(
    position_id='99999',
    phase='grace'
)
```

**Expected:**
- Return: `False`
- Log: `WARNING - Aged position for position_id 99999 not found`

### Test 4: No Fields Provided

**Code:**
```python
success = await repository.update_aged_position(
    position_id='2532'
)
```

**Expected:**
- Return: `False`
- Log: `WARNING - No fields to update for position 2532`

### Test 5: Database Verification

**Query:**
```sql
-- Before update
SELECT phase, target_price, updated_at
FROM monitoring.aged_positions
WHERE position_id = '2532';

-- Run update via bot

-- After update
SELECT phase, target_price, updated_at
FROM monitoring.aged_positions
WHERE position_id = '2532';
-- Verify: updated_at is recent, phase and target_price changed
```

### Test 6: End-to-End State Persistence

**Steps:**
1. Create aged position
2. Trigger phase transition (grace → progressive)
3. Verify database updated
4. Restart bot
5. Verify state recovered correctly

**Expected:** Phase preserved after restart

---

## ✅ VERIFICATION CHECKLIST

### Code Changes

- [ ] `update_aged_position()` uses positional params
- [ ] `get_aged_positions_statistics()` uses positional params
- [ ] No `%(name)s` syntax remains
- [ ] No `**params` unpacking remains
- [ ] Parameter order correct
- [ ] Logging uses param_names
- [ ] Python syntax valid

### Testing

- [ ] Single field update works
- [ ] Multiple field update works
- [ ] All fields update works
- [ ] Position not found handled
- [ ] No fields provided handled
- [ ] Database updated correctly
- [ ] State persistence works
- [ ] Recovery on restart works

### Deployment

- [ ] Git commit created
- [ ] Commit message detailed
- [ ] Pushed to origin/main
- [ ] Monitor logs after deployment
- [ ] Verify no errors
- [ ] Verify aged position updates

---

## 🚀 DEPLOYMENT PLAN

### Pre-Deployment

- [ ] Review both fixes
- [ ] Verify syntax
- [ ] Plan deployment time (after wave fix)

### Deployment

- [ ] Apply Fix #1 (update_aged_position)
- [ ] Apply Fix #2 (get_aged_positions_statistics)
- [ ] Verify: `python3 -m py_compile database/repository.py`
- [ ] Verify: `grep "%(" database/repository.py` returns nothing
- [ ] Git commit with detailed message
- [ ] Push to origin/main

### Post-Deployment

- [ ] Monitor logs for "Updated aged position"
- [ ] Verify no "unexpected keyword argument" errors
- [ ] Test single field update
- [ ] Test multiple field update
- [ ] Check database updated_at timestamps
- [ ] Verify state persistence works

---

## 🔄 ROLLBACK PLAN

### If Issues Occur

**Option 1: Git Revert**
```bash
git revert HEAD
git push origin main
# Returns to current (broken) state - safe fallback
```

**Option 2: Quick Disable**
```python
# At start of update_aged_position():
if True:  # Quick disable flag
    logger.warning("Aged position updates temporarily disabled")
    return False
```

**Safety:** Rollback safe - aged monitoring works in memory, DB optional

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
-- Result: 2025-10-23 19:13:51 (OLD, not updating)
```

**Behavior:** 100% failure rate, no state persistence

### After Fix

**Logs:**
```
INFO - Updated aged position 2532: phase, target_price, position_id
```

**Database:**
```sql
SELECT updated_at FROM monitoring.aged_positions WHERE position_id = '2532';
-- Result: 2025-10-26 17:00:00 (RECENT, updating correctly)
```

**Behavior:** 100% success rate, state persisted

### Metrics

| Metric | Before | After |
|--------|--------|-------|
| Update success rate | 0% | 100% |
| Errors per update | 1 | 0 |
| State persistence | BROKEN | WORKING |
| Recovery on restart | FAILS | WORKS |
| Database writes | FAIL | SUCCESS |

---

## 🎯 SUCCESS CRITERIA

### Implementation Success

✅ **Code:**
- Both functions use positional params
- No psycopg2 syntax remains
- Syntax valid
- Git committed and pushed

### Runtime Success

✅ **Logs:**
- "Updated aged position" messages
- No "unexpected keyword argument" errors
- Correct parameter names logged

✅ **Database:**
- updated_at timestamps recent
- Phase transitions saved
- State persistence works
- Recovery on restart works

---

**Plan Status:** ✅ READY FOR IMPLEMENTATION
**Created by:** Claude Code
**Date:** 2025-10-26 16:50:00
**Priority:** 🟡 P2 - HIGH
**Estimated Time:** 20 minutes
**Risk:** LOW 🟢
