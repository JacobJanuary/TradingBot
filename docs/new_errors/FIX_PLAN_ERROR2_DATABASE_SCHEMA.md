# FIX PLAN: Database Schema Mismatch - position_opened_at

## DATE: 2025-10-26
## PRIORITY: 🟡 MEDIUM (Fix in Next Deployment)
## STATUS: Ready for Implementation

---

## PROBLEM SUMMARY

**Error:** `Failed to get active aged positions: column ap.position_opened_at does not exist`

**File:** `database/repository.py`
**Function:** `get_active_aged_positions()` (line 1093)
**Line:** 1111

**Frequency:** Every restart (100% reproducible)
**Severity:** MEDIUM (aged position recovery fails on startup)

---

## ROOT CAUSE

SQL query references column `ap.position_opened_at` which **doesn't exist** in table `monitoring.aged_positions`.

**Table Schema (Actual):**
```sql
Table "monitoring.aged_positions"
     Column     |           Type
----------------+--------------------------
 id             | integer
 position_id    | character varying(255)
 symbol         | character varying(50)
 exchange       | character varying(50)
 entry_price    | numeric(20,8)
 target_price   | numeric(20,8)
 phase          | character varying(50)
 hours_aged     | integer
 loss_tolerance | numeric(10,4)
 created_at     | timestamp with time zone  ← Use this!
 updated_at     | timestamp with time zone

NO column: position_opened_at
```

**Query (Broken):**
```sql
SELECT
    ap.*,
    EXTRACT(EPOCH FROM (NOW() - ap.position_opened_at)) / 3600 as current_age_hours,
    --                          ^^^^^^^^^^^^^^^^^^^^^ Doesn't exist!
    EXTRACT(EPOCH FROM (NOW() - ap.detected_at)) / 3600 as hours_since_detection
FROM monitoring.aged_positions ap
```

---

## INVESTIGATION

### Question 1: Should we use `created_at`?

**Answer:** Need to verify semantics

**Options:**
1. **Use `created_at`** - When aged position was detected/created
2. **Add `position_opened_at`** - Add missing column to table
3. **Use linked position's `opened_at`** - Join with monitoring.positions

**Recommendation:** Check aged position semantics

Let's check if `detected_at` column exists:
```bash
psql -d fox_crypto -c "\d monitoring.aged_positions"
```

**Result:** Column `detected_at` also doesn't exist in current schema!

### Question 2: What columns do exist for timestamps?

From schema inspection:
- ✅ `created_at` - exists
- ✅ `updated_at` - exists
- ❌ `position_opened_at` - doesn't exist
- ❌ `detected_at` - doesn't exist (but query tries to use it!)

### Question 3: Is this old schema vs new code?

**Hypothesis:** Code was written for newer schema, but database has old schema.

**Evidence:**
- Query references TWO missing columns: `position_opened_at` AND `detected_at`
- Table only has `created_at` and `updated_at`

---

## SOLUTION

### Variant A: USE created_at (QUICK FIX - RECOMMENDED)

Replace missing columns with available `created_at`.

**Assumption:** `created_at` represents when position was first opened/detected as aged.

#### Changes Required

**File:** `database/repository.py`
**Lines:** 1111-1112

**BEFORE:**
```python
query = """
    SELECT
        ap.*,
        EXTRACT(EPOCH FROM (NOW() - ap.position_opened_at)) / 3600 as current_age_hours,
        EXTRACT(EPOCH FROM (NOW() - ap.detected_at)) / 3600 as hours_since_detection
    FROM monitoring.aged_positions ap
    WHERE ap.status = ANY($1)
        AND ap.closed_at IS NULL
    ORDER BY ap.detected_at DESC
"""
```

**AFTER:**
```python
query = """
    SELECT
        ap.*,
        -- CRITICAL FIX: Use created_at instead of missing position_opened_at column
        EXTRACT(EPOCH FROM (NOW() - ap.created_at)) / 3600 as current_age_hours,
        -- CRITICAL FIX: Use created_at instead of missing detected_at column
        EXTRACT(EPOCH FROM (NOW() - ap.created_at)) / 3600 as hours_since_detection
    FROM monitoring.aged_positions ap
    WHERE ap.status = ANY($1)
        AND ap.closed_at IS NULL
    -- CRITICAL FIX: Use created_at for ordering instead of detected_at
    ORDER BY ap.created_at DESC
"""
```

**Changes:**
1. Line 1111: `ap.position_opened_at` → `ap.created_at`
2. Line 1112: `ap.detected_at` → `ap.created_at`
3. Line 1116: `ORDER BY ap.detected_at` → `ORDER BY ap.created_at`

**Risk Level:** LOW (semantic change, but better than failing)

---

### Variant B: ADD MISSING COLUMNS (PROPER FIX - Future Enhancement)

Add missing columns to database schema.

**Migration SQL:**
```sql
-- Add missing columns to monitoring.aged_positions
ALTER TABLE monitoring.aged_positions
ADD COLUMN IF NOT EXISTS position_opened_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS detected_at TIMESTAMP WITH TIME ZONE;

-- Backfill with created_at values
UPDATE monitoring.aged_positions
SET position_opened_at = created_at,
    detected_at = created_at
WHERE position_opened_at IS NULL
   OR detected_at IS NULL;

-- Add NOT NULL constraints after backfill
ALTER TABLE monitoring.aged_positions
ALTER COLUMN position_opened_at SET NOT NULL,
ALTER COLUMN detected_at SET NOT NULL;

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_aged_positions_position_opened
    ON monitoring.aged_positions (position_opened_at);

CREATE INDEX IF NOT EXISTS idx_aged_positions_detected
    ON monitoring.aged_positions (detected_at);
```

**Pros:**
- ✅ Proper schema (code matches database)
- ✅ Semantic clarity (separate timestamps)
- ✅ Better for future features

**Cons:**
- ⏱️ Requires migration
- ⏱️ Need to update insert/update code
- ⏱️ More complex

**Recommendation:** Use Variant A now, consider Variant B later

---

## TESTING PLAN

### Direct SQL Test

**Before Fix:**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT
    ap.*,
    EXTRACT(EPOCH FROM (NOW() - ap.position_opened_at)) / 3600 as current_age_hours
FROM monitoring.aged_positions ap
LIMIT 1;
"
```

**Expected:** Error: column "position_opened_at" does not exist

**After Fix:**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT
    ap.*,
    EXTRACT(EPOCH FROM (NOW() - ap.created_at)) / 3600 as current_age_hours
FROM monitoring.aged_positions ap
LIMIT 1;
"
```

**Expected:** Query succeeds, returns rows

---

### Integration Test

**Test Procedure:**

1. **Restart bot with fix**
   ```bash
   python main.py --mode production > logs/trading_bot.log 2>&1 &
   ```

2. **Check logs for error**
   ```bash
   grep "Failed to get active aged positions" logs/trading_bot.log
   ```

   **Expected:** NO errors

3. **Check aged position recovery**
   ```bash
   grep "aged positions restored" logs/trading_bot.log
   ```

   **Expected:** "Recovery complete: X aged positions restored" (where X >= 0)

4. **Verify query runs**
   ```bash
   tail -100 logs/trading_bot.log | grep -E "(aged|position.*recovery)"
   ```

   **Expected:** Successful recovery log messages

---

## DEPLOYMENT PLAN

### Step 1: Verify Current Schema

```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "\d monitoring.aged_positions"
```

**Check:**
- ✅ `created_at` exists
- ❌ `position_opened_at` doesn't exist
- ❌ `detected_at` doesn't exist

### Step 2: Test SQL Query (Before Fix)

```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT
    ap.*,
    EXTRACT(EPOCH FROM (NOW() - ap.position_opened_at)) / 3600 as current_age_hours
FROM monitoring.aged_positions ap
LIMIT 1;
"
```

**Expected:** Error (confirms bug exists)

### Step 3: Code Changes

Edit `database/repository.py` line 1111-1116:

```python
# Change:
ap.position_opened_at → ap.created_at
ap.detected_at → ap.created_at (2 places)
```

### Step 4: Syntax Check

```bash
python3 -m py_compile database/repository.py
```

**Expected:** No errors

### Step 5: Test SQL Query (After Fix)

```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT
    ap.*,
    EXTRACT(EPOCH FROM (NOW() - ap.created_at)) / 3600 as current_age_hours,
    EXTRACT(EPOCH FROM (NOW() - ap.created_at)) / 3600 as hours_since_detection
FROM monitoring.aged_positions ap
WHERE ap.status = ANY(ARRAY['detected', 'monitoring'])
  AND ap.closed_at IS NULL
ORDER BY ap.created_at DESC;
"
```

**Expected:** Query succeeds

### Step 6: Git Commit

```bash
git add database/repository.py
git commit -m "fix(database): Use created_at instead of missing position_opened_at column

PROBLEM:
- get_active_aged_positions() query fails on startup
- References column 'ap.position_opened_at' which doesn't exist
- Also references 'ap.detected_at' which doesn't exist
- Occurred every restart (100% reproducible)

ROOT CAUSE:
- Code written for newer schema, but database has old schema
- Table monitoring.aged_positions only has: created_at, updated_at
- Missing columns: position_opened_at, detected_at

SOLUTION:
- Replace ap.position_opened_at with ap.created_at
- Replace ap.detected_at with ap.created_at (2 occurrences)
- Semantic assumption: created_at = when position was first detected as aged

IMPACT:
- Fixes: Aged position recovery on startup
- Risk: LOW (better than failing query)
- Note: May need proper migration later to add missing columns

FIXES: Database error 'column ap.position_opened_at does not exist'
"
```

### Step 7: Deploy (Restart Bot)

```bash
# Stop bot
ps aux | grep "python.*main.py.*production"
kill <PID>

# Start bot with fix
python main.py --mode production > logs/trading_bot.log 2>&1 &

# Monitor startup
tail -f logs/trading_bot.log | head -100
```

### Step 8: Verify Fix

**Check logs:**
```bash
# Should NOT see this error anymore
grep "Failed to get active aged positions" logs/trading_bot.log

# Should see successful recovery
grep "aged positions restored" logs/trading_bot.log
```

**Expected:**
- ❌ NO "Failed to get active aged positions" errors
- ✅ "Recovery complete: X aged positions restored"

---

## ROLLBACK PLAN

If fix causes issues:

### Step 1: Revert Git

```bash
git log --oneline | head -5
git revert <commit-hash>
```

### Step 2: Restart Bot

```bash
kill <PID>
python main.py --mode production > logs/trading_bot.log 2>&1 &
```

---

## SUCCESS CRITERIA

### ✅ Fix Successful If:

1. SQL query runs without errors
2. Bot starts without database errors
3. Aged position recovery succeeds (no errors in logs)
4. No "column does not exist" errors

### ❌ Rollback If:

1. New database errors appear
2. Aged position logic breaks
3. Performance issues

---

## FOLLOW-UP ACTIONS

### Future Enhancement: Add Missing Columns

**When:** After validating Variant A works correctly

**Steps:**
1. Create migration script (see Variant B)
2. Test migration on dev/staging
3. Update insert/update code to use new columns
4. Deploy migration + code update
5. Revert SQL query to use proper columns

---

## NOTES

- **Semantic Change:** Using `created_at` instead of `position_opened_at` may have different meaning
- **Need Verification:** Confirm `created_at` is correct semantic equivalent
- **Future Work:** Consider adding proper columns via migration
- **Risk:** LOW (better than crashing, but may need refinement)

**Ready for implementation:** ✅ YES (Variant A)
**Future consideration:** ⏱️ Variant B (proper schema migration)
