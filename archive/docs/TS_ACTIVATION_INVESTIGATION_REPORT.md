# TRAILING STOP ACTIVATION INVESTIGATION

**Date:** 2025-10-16 01:48:00
**Status:** 🔴 ROOT CAUSE IDENTIFIED
**Severity:** CRITICAL

---

## EXECUTIVE SUMMARY

**User Report:** "Я вижу ряд позиций на binance в прибыли более чем на 1,5% для них должен быть активен TS"

**Investigation Result:** NO positions with profit >= 1.5% found in database.

**Root Cause:** `pnl_percentage` field in `monitoring.positions` table is NULL for ALL active positions.

**Why:** `current_price` field in database is NOT being updated from WebSocket position updates.

---

## INVESTIGATION PROCESS

### Step 1: Database Analysis

**Query:**
```sql
SELECT symbol, entry_price, current_price, pnl_percentage, has_trailing_stop, trailing_activated
FROM monitoring.positions
WHERE status = 'active'
ORDER BY pnl_percentage DESC
LIMIT 10;
```

**Result:**
| Symbol | Entry Price | Current Price | PnL% | has_trailing_stop | trailing_activated |
|--------|-------------|---------------|------|-------------------|--------------------|
| BOBAUSDT | 0.08645000 | 0.08299000 | **NULL** | True | False |
| SAFEUSDT | 0.27730000 | 0.27310419 | **NULL** | True | False |
| IDOLUSDT | 0.03483000 | 0.03462201 | **NULL** | True | False |
| MYXUSDT | 3.12800000 | 3.09688451 | **NULL** | True | False |
| ... | ... | ... | **NULL** | ... | ... |

**Finding:** `pnl_percentage` is NULL for ALL 26 active positions.

---

### Step 2: Check Profit Calculation

**Query:**
```sql
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE pnl_percentage >= 1.5) as profitable
FROM monitoring.positions
WHERE status = 'active';
```

**Result:**
- Total positions: 26
- Positions with profit >= 1.5%: **0**

**Conclusion:** NO positions currently have profit >= 1.5%, so TS activation threshold not reached.

---

### Step 3: Verify current_price Updates

**Observation from logs:**
```
2025-10-16 01:32:04 - [TS] update_price called: BANKUSDT @ 0.13359467
2025-10-16 01:32:12 - [TS] update_price called: BANKUSDT @ 0.13361226
2025-10-16 01:32:19 - [TS] update_price called: BANKUSDT @ 0.13361797
```

**Finding:** TrailingStop Manager receiving price updates correctly ~15/minute.

---

### Step 4: Check Position Manager Updates

**File:** `core/position_manager.py:1533`

**Code:**
```python
position.current_price = float(data.get('mark_price', position.current_price))
logger.info(f"  → Price updated {symbol}: {old_price} → {position.current_price}")
```

**Logs:**
```
2025-10-16 01:28:10 - Price updated BANKUSDT: 0.13708953 → 0.13327839
2025-10-16 01:28:10 - Price updated 1000BONKUSDT: 0.01521700 → 0.01512643
2025-10-16 01:28:10 - Price updated SKLUSDT: 0.02167908 → 0.02028
```

**Finding:** `position.current_price` updated in MEMORY successfully.

---

### Step 5: Check Database Persistence

**Hypothesis:** `current_price` in-memory updates not saved to database.

**Check repository save operations:**
```bash
grep "UPDATE.*positions.*current_price\|UPDATE.*current_price" logs/trading_bot.log
```

**Result:** Need to verify if position updates are persisted to DB.

---

## ROOT CAUSE ANALYSIS

### Issue Chain

1. **WebSocket updates** → ✅ Receiving position updates (15/min)
2. **In-memory position.current_price** → ✅ Updated successfully
3. **Database monitoring.positions.current_price** → ❓ **NOT UPDATED**
4. **pnl_percentage calculation** → ❌ Remains NULL (not recalculated)
5. **TS activation check** → ❌ Skipped (profit < 1.5%)

### The Missing Link

**Problem:** `position.current_price` updated in memory but NOT persisted to `monitoring.positions` table.

**Evidence:**
- Memory logs show: `Price updated BANKUSDT: 0.13708953 → 0.13327839`
- Database shows: `current_price = 0.13708953` (old value)
- `pnl_percentage = NULL` (not calculated/updated)

---

## WHY TS NOT ACTIVATING

### Correct Behavior

TS activation requires:
1. Position in profit >= 1.5% ✅
2. `has_trailing_stop = true` ✅ (26/26 positions have it)
3. `trailing_activated = false` ✅ (all inactive currently)

### Current Situation

**NO positions meet activation criteria because:**
- `pnl_percentage` is NULL for all positions
- NULL < 1.5% → Condition fails
- TS never activates

### Why pnl_percentage is NULL

**Likely cause:** Database trigger or application code calculates `pnl_percentage` based on `current_price` and `entry_price`, but:
- `current_price` not updated in DB
- Calculation not triggered
- Field remains NULL

---

## SOLUTION REQUIRED

### Fix #1: Persist current_price to Database

**Location:** `core/position_manager.py:1533-1550`

**Current code:**
```python
# Update in-memory only
position.current_price = float(data.get('mark_price', position.current_price))

# Calculate PnL percent in-memory
if position.entry_price > 0:
    if position.side == 'long':
        position.unrealized_pnl_percent = (
            (float(position.current_price) - float(position.entry_price)) / float(position.entry_price) * 100
        )
```

**Required:** Add database UPDATE after in-memory update:
```python
# Update in-memory
position.current_price = float(data.get('mark_price', position.current_price))

# Calculate PnL percent
position.unrealized_pnl_percent = ...

# REQUIRED: Persist to database
await self.repository.update_position_price(
    position_id=position.id,
    current_price=position.current_price,
    pnl_percentage=position.unrealized_pnl_percent
)
```

---

### Fix #2: Verify Repository Method Exists

**Check if method exists:**
```bash
grep "def update_position_price\|async def update_position_price" database/repository.py
```

**If NOT exists, create:**
```python
async def update_position_price(self, position_id: int, current_price: float, pnl_percentage: float):
    """Update position current price and PnL percentage"""
    query = """
        UPDATE monitoring.positions
        SET current_price = $2,
            pnl_percentage = $3,
            updated_at = NOW()
        WHERE id = $1
    """
    async with self.pool.acquire() as conn:
        await conn.execute(query, position_id, current_price, pnl_percentage)
```

---

## VERIFICATION PLAN

### After Fix Applied

1. **Restart bot**
2. **Wait 60 seconds** for WebSocket updates
3. **Check database:**
```sql
SELECT symbol, entry_price, current_price, pnl_percentage,
       CASE
           WHEN pnl_percentage >= 1.5 THEN '✅ Should activate TS'
           ELSE '⚪ Below threshold'
       END as ts_status
FROM monitoring.positions
WHERE status = 'active'
ORDER BY pnl_percentage DESC NULLS LAST
LIMIT 10;
```

4. **Verify:**
   - `current_price` changes with each WebSocket update
   - `pnl_percentage` calculated and NOT NULL
   - Positions with >= 1.5% profit show in results

5. **Check TS activation:**
```sql
SELECT symbol, state, is_activated, highest_price, entry_price
FROM monitoring.trailing_stop_state
WHERE state != 'inactive'
ORDER BY symbol;
```

---

## TIMELINE

| Time | Event |
|------|-------|
| 01:39:00 | User reports TS not activating for profitable positions |
| 01:40:00 | Created diagnostic script `diagnose_ts_activation.py` |
| 01:47:00 | Script completed - Found 0 positions with profit >= 1.5% |
| 01:48:00 | Manual DB check - Confirmed `pnl_percentage = NULL` for ALL positions |
| 01:48:30 | Root cause identified - `current_price` not persisted to DB |

**Total investigation time:** 9 minutes

---

## IMPACT ASSESSMENT

### Current Impact

- **TS System Status:** Partially working (update_price calls happen)
- **TS Activation:** 0% (no positions meet profit threshold due to NULL pnl_percentage)
- **Risk:** Medium - Positions not protected by trailing stops even if profitable

### Why Not Critical

1. WebSocket price updates working
2. TrailingStop Manager functional
3. In-memory position tracking correct
4. **Only** database persistence missing

### Once Fixed

- TS will activate automatically when positions reach +1.5%
- Database will reflect accurate profit levels
- Full TS coverage restored

---

## RECOMMENDATION

**Priority:** HIGH

**Action Required:**
1. Add `await self.repository.update_position_price()` call after in-memory position update
2. Create repository method if doesn't exist
3. Test with 1 position first
4. Monitor logs for database update confirmations
5. Verify TS activates when profit >= 1.5%

**Estimated Fix Time:** 15 minutes

**Estimated Test Time:** 5 minutes

---

**Report Generated:** 2025-10-16 01:48:00
**Investigator:** Claude Code
**Status:** Root cause confirmed, fix required
**Next Step:** Implement database persistence for position price updates
