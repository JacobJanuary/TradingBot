# 🔧 DETAILED FIX PLAN: TS Side Mismatch (Critical)

**Date**: 2025-10-28
**Priority**: 🔴 P0 - CRITICAL
**Status**: ⏳ PLANNING COMPLETE - AWAITING APPROVAL
**Type**: Bug Fix (Root Cause Fix)

---

## ⚡ EXECUTIVE SUMMARY

**Bug**: TS state side mismatch on fast position reopens
**Root Cause**: `save_trailing_stop_state()` ON CONFLICT DO UPDATE missing fields
**Fix**: Add 5 fields to DO UPDATE SET clause
**Risk**: 🟢 LOW
**Time**: 15 min code + 30 min testing

---

## 📋 STEP-BY-STEP IMPLEMENTATION

### STEP 1: Read Current Code ✅

**File**: `database/repository.py`
**Lines**: 1055-1072
**Purpose**: Confirm current state

**Command**:
```bash
# Verify current DO UPDATE SET clause
grep -A 20 "ON CONFLICT (symbol, exchange)" database/repository.py
```

**Expected**: Missing `side`, `entry_price`, `quantity`, `activation_percent`, `callback_percent`

---

### STEP 2: Apply Code Fix ✅

**File**: `database/repository.py`
**Location**: Lines 1055-1072

#### BEFORE (Current - Buggy):

```sql
ON CONFLICT (symbol, exchange)
DO UPDATE SET
    position_id = EXCLUDED.position_id,
    state = EXCLUDED.state,
    is_activated = EXCLUDED.is_activated,
    highest_price = EXCLUDED.highest_price,
    lowest_price = EXCLUDED.lowest_price,
    current_stop_price = EXCLUDED.current_stop_price,
    stop_order_id = EXCLUDED.stop_order_id,
    activation_price = EXCLUDED.activation_price,
    update_count = EXCLUDED.update_count,
    highest_profit_percent = EXCLUDED.highest_profit_percent,
    activated_at = COALESCE(monitoring.trailing_stop_state.activated_at, EXCLUDED.activated_at),
    last_update_time = EXCLUDED.last_update_time,
    last_sl_update_time = EXCLUDED.last_sl_update_time,
    last_updated_sl_price = EXCLUDED.last_updated_sl_price,
    last_peak_save_time = EXCLUDED.last_peak_save_time,
    last_saved_peak_price = EXCLUDED.last_saved_peak_price
```

#### AFTER (Fixed):

```sql
ON CONFLICT (symbol, exchange)
DO UPDATE SET
    position_id = EXCLUDED.position_id,
    state = EXCLUDED.state,
    is_activated = EXCLUDED.is_activated,
    highest_price = EXCLUDED.highest_price,
    lowest_price = EXCLUDED.lowest_price,
    current_stop_price = EXCLUDED.current_stop_price,
    stop_order_id = EXCLUDED.stop_order_id,
    activation_price = EXCLUDED.activation_price,
    update_count = EXCLUDED.update_count,
    highest_profit_percent = EXCLUDED.highest_profit_percent,
    activated_at = COALESCE(monitoring.trailing_stop_state.activated_at, EXCLUDED.activated_at),
    last_update_time = EXCLUDED.last_update_time,
    last_sl_update_time = EXCLUDED.last_sl_update_time,
    last_updated_sl_price = EXCLUDED.last_updated_sl_price,
    last_peak_save_time = EXCLUDED.last_peak_save_time,
    last_saved_peak_price = EXCLUDED.last_saved_peak_price,
    -- CRITICAL FIX: Update position-specific fields on conflict (prevents side mismatch)
    entry_price = EXCLUDED.entry_price,
    side = EXCLUDED.side,
    quantity = EXCLUDED.quantity,
    activation_percent = EXCLUDED.activation_percent,
    callback_percent = EXCLUDED.callback_percent
```

**Changes**:
- Added 5 lines at the end of DO UPDATE SET
- Added comment explaining fix

---

### STEP 3: Create Unit Test ✅

**File**: `tests/unit/test_ts_side_mismatch_fix.py` (NEW)

```python
"""
Unit test for TS side mismatch fix

Tests that save_trailing_stop_state() correctly updates all fields
including side, entry_price, quantity on CONFLICT.

Regression test for CRITICAL bug found 2025-10-28.
See: docs/investigations/CRITICAL_TS_SIDE_MISMATCH_ROOT_CAUSE_20251028.md
"""
import pytest
import asyncpg
from decimal import Decimal
from database.repository import Repository
from config.settings import config


@pytest.mark.asyncio
async def test_save_trailing_stop_state_updates_side_on_conflict():
    """
    Test that ON CONFLICT DO UPDATE correctly updates side field

    Scenario: Fast position reopen (SHORT → LONG)
    Expected: side updated from 'short' to 'long'
    """
    # Setup
    pool = await asyncpg.create_pool(
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
        user=config.database.user,
        password=config.database.password,
        min_size=1,
        max_size=2
    )

    repo = Repository(pool)

    symbol = "TESTUSDT"
    exchange = "binance"

    try:
        # STEP 1: Create initial SHORT position TS state
        state_short = {
            'symbol': symbol,
            'exchange': exchange,
            'position_id': 1,
            'state': 'waiting',
            'is_activated': False,
            'highest_price': Decimal('100'),
            'lowest_price': Decimal('98'),
            'current_stop_price': Decimal('96'),
            'stop_order_id': 'order_123',
            'activation_price': Decimal('102'),
            'activation_percent': Decimal('2.0'),
            'callback_percent': Decimal('0.5'),
            'entry_price': Decimal('100'),
            'side': 'short',  # ← SHORT
            'quantity': Decimal('10'),
            'update_count': 0,
            'highest_profit_percent': Decimal('0'),
            'activated_at': None,
            'last_update_time': None,
            'last_sl_update_time': None,
            'last_updated_sl_price': None,
            'last_peak_save_time': None,
            'last_saved_peak_price': None,
            'created_at': None
        }

        result = await repo.save_trailing_stop_state(state_short)
        assert result is True, "Initial save should succeed"

        # Verify SHORT state saved
        db_state = await repo.get_trailing_stop_state(symbol, exchange)
        assert db_state is not None
        assert db_state['side'] == 'short'
        assert float(db_state['entry_price']) == 100.0
        assert db_state['position_id'] == 1

        # STEP 2: Save LONG position TS state (same symbol, exchange)
        # This triggers ON CONFLICT
        state_long = state_short.copy()
        state_long.update({
            'position_id': 2,  # ← NEW position
            'entry_price': Decimal('105'),  # ← NEW entry price
            'side': 'long',  # ← LONG (opposite side)
            'quantity': Decimal('15'),  # ← NEW quantity
            'activation_price': Decimal('107.1'),
            'activation_percent': Decimal('2.5'),  # ← NEW
            'callback_percent': Decimal('0.7'),  # ← NEW
        })

        result = await repo.save_trailing_stop_state(state_long)
        assert result is True, "Update on conflict should succeed"

        # STEP 3: Verify ALL fields updated (including side, entry_price, quantity)
        db_state = await repo.get_trailing_stop_state(symbol, exchange)
        assert db_state is not None

        # CRITICAL CHECKS:
        assert db_state['side'] == 'long', "❌ SIDE NOT UPDATED! Bug still exists!"
        assert float(db_state['entry_price']) == 105.0, "❌ ENTRY_PRICE NOT UPDATED!"
        assert float(db_state['quantity']) == 15.0, "❌ QUANTITY NOT UPDATED!"
        assert float(db_state['activation_percent']) == 2.5, "❌ ACTIVATION_PERCENT NOT UPDATED!"
        assert float(db_state['callback_percent']) == 0.7, "❌ CALLBACK_PERCENT NOT UPDATED!"

        # Other fields should also update
        assert db_state['position_id'] == 2, "position_id should update"

        print("✅ Test PASSED: All fields updated correctly on conflict")

    finally:
        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM monitoring.trailing_stop_state WHERE symbol = $1 AND exchange = $2",
                symbol, exchange
            )
        await pool.close()


@pytest.mark.asyncio
async def test_save_trailing_stop_state_same_side_update():
    """
    Test that ON CONFLICT DO UPDATE works for same-side reopens

    Scenario: LONG → LONG (update, not conflict)
    Expected: entry_price, quantity updated
    """
    # Setup
    pool = await asyncpg.create_pool(
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
        user=config.database.user,
        password=config.database.password,
        min_size=1,
        max_size=2
    )

    repo = Repository(pool)

    symbol = "TESTUSDT2"
    exchange = "bybit"

    try:
        # STEP 1: Create initial LONG position
        state_long_1 = {
            'symbol': symbol,
            'exchange': exchange,
            'position_id': 10,
            'state': 'waiting',
            'is_activated': False,
            'highest_price': Decimal('200'),
            'lowest_price': Decimal('198'),
            'current_stop_price': Decimal('196'),
            'stop_order_id': 'order_456',
            'activation_price': Decimal('204'),
            'activation_percent': Decimal('2.0'),
            'callback_percent': Decimal('0.5'),
            'entry_price': Decimal('200'),
            'side': 'long',
            'quantity': Decimal('5'),
            'update_count': 0,
            'highest_profit_percent': Decimal('0'),
            'activated_at': None,
            'last_update_time': None,
            'last_sl_update_time': None,
            'last_updated_sl_price': None,
            'last_peak_save_time': None,
            'last_saved_peak_price': None,
            'created_at': None
        }

        result = await repo.save_trailing_stop_state(state_long_1)
        assert result is True

        # STEP 2: Reopen LONG position (same side, different entry)
        state_long_2 = state_long_1.copy()
        state_long_2.update({
            'position_id': 11,
            'entry_price': Decimal('210'),  # ← NEW entry
            'quantity': Decimal('8'),  # ← NEW quantity
            'activation_price': Decimal('214.2'),
        })

        result = await repo.save_trailing_stop_state(state_long_2)
        assert result is True

        # STEP 3: Verify fields updated
        db_state = await repo.get_trailing_stop_state(symbol, exchange)
        assert db_state is not None
        assert db_state['side'] == 'long'
        assert float(db_state['entry_price']) == 210.0
        assert float(db_state['quantity']) == 8.0
        assert db_state['position_id'] == 11

        print("✅ Test PASSED: Same-side reopen updates correctly")

    finally:
        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM monitoring.trailing_stop_state WHERE symbol = $1 AND exchange = $2",
                symbol, exchange
            )
        await pool.close()


if __name__ == "__main__":
    import asyncio

    async def main():
        print("Running TS side mismatch fix tests...")
        await test_save_trailing_stop_state_updates_side_on_conflict()
        await test_save_trailing_stop_state_same_side_update()
        print("\\n✅ ALL TESTS PASSED")

    asyncio.run(main())
```

---

### STEP 4: Run Tests ✅

**Command**:
```bash
# Run unit test
python tests/unit/test_ts_side_mismatch_fix.py

# Expected output:
# Running TS side mismatch fix tests...
# ✅ Test PASSED: All fields updated correctly on conflict
# ✅ Test PASSED: Same-side reopen updates correctly
#
# ✅ ALL TESTS PASSED
```

**Success Criteria**:
- ✅ No assertion errors
- ✅ "All fields updated correctly" message
- ✅ Both tests pass

---

### STEP 5: Git Commit ✅

#### Commit Message:

```
fix(critical): update all TS fields on conflict (fixes side mismatch)

Bug: TS side mismatch on fast position reopens (SHORT → LONG)
Root Cause: save_trailing_stop_state() ON CONFLICT DO UPDATE SET
missing critical fields (side, entry_price, quantity, activation_percent,
callback_percent)

Impact: Fast position reopens left STALE TS state in DB with MIXED values:
- New position_id ✅
- Old side ❌
- Old entry_price ❌

Result: On bot restart, SIDE MISMATCH detected and corrected, but
creates log noise and indicates data corruption.

Fix: Add 5 missing fields to DO UPDATE SET clause:
- entry_price = EXCLUDED.entry_price
- side = EXCLUDED.side
- quantity = EXCLUDED.quantity
- activation_percent = EXCLUDED.activation_percent
- callback_percent = EXCLUDED.callback_percent

Testing:
- Unit test: test_save_trailing_stop_state_updates_side_on_conflict
- Manual test: Fast position reopen (SHORT → LONG)
- Verification: DB has correct side, entry_price after reopen

Risk: LOW (surgical fix, adds fields to existing UPSERT)
Impact: HIGH (eliminates SIDE MISMATCH errors on restart)

References:
- docs/investigations/CRITICAL_TS_SIDE_MISMATCH_ROOT_CAUSE_20251028.md
- docs/plans/FIX_TS_SIDE_MISMATCH_CRITICAL_20251028.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

#### Git Commands:

```bash
# 1. Stage changes
git add database/repository.py
git add tests/unit/test_ts_side_mismatch_fix.py
git add docs/investigations/CRITICAL_TS_SIDE_MISMATCH_ROOT_CAUSE_20251028.md
git add docs/investigations/CRITICAL_TS_SIDE_MISMATCH_SUMMARY_20251028.md
git add docs/plans/FIX_TS_SIDE_MISMATCH_CRITICAL_20251028.md

# 2. Commit with detailed message
git commit -m "$(cat <<'EOF'
fix(critical): update all TS fields on conflict (fixes side mismatch)

Bug: TS side mismatch on fast position reopens (SHORT → LONG)
Root Cause: save_trailing_stop_state() ON CONFLICT DO UPDATE SET
missing critical fields (side, entry_price, quantity, activation_percent,
callback_percent)

Impact: Fast position reopens left STALE TS state in DB with MIXED values:
- New position_id ✅
- Old side ❌
- Old entry_price ❌

Result: On bot restart, SIDE MISMATCH detected and corrected, but
creates log noise and indicates data corruption.

Fix: Add 5 missing fields to DO UPDATE SET clause:
- entry_price = EXCLUDED.entry_price
- side = EXCLUDED.side
- quantity = EXCLUDED.quantity
- activation_percent = EXCLUDED.activation_percent
- callback_percent = EXCLUDED.callback_percent

Testing:
- Unit test: test_save_trailing_stop_state_updates_side_on_conflict
- Manual test: Fast position reopen (SHORT → LONG)
- Verification: DB has correct side, entry_price after reopen

Risk: LOW (surgical fix, adds fields to existing UPSERT)
Impact: HIGH (eliminates SIDE MISMATCH errors on restart)

References:
- docs/investigations/CRITICAL_TS_SIDE_MISMATCH_ROOT_CAUSE_20251028.md
- docs/plans/FIX_TS_SIDE_MISMATCH_CRITICAL_20251028.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# 3. Verify commit
git log -1 --stat

# 4. Push to remote
git push origin main
```

---

### STEP 6: Verify Deployment ✅

#### Manual Verification:

```bash
# 1. Monitor logs for SIDE MISMATCH errors
docker logs -f trading_bot | grep "SIDE MISMATCH"

# Expected: Zero errors after fix

# 2. Check DB for correct TS state
psql -h localhost -U <user> -d trading_bot -c "
SELECT symbol, exchange, side, entry_price, position_id, created_at
FROM monitoring.trailing_stop_state
ORDER BY created_at DESC
LIMIT 10;
"

# Expected: All sides match current positions

# 3. Force fast reopen scenario (if possible)
# - Close position manually on exchange
# - Wait for cleanup
# - Open new position immediately (opposite side)
# - Restart bot
# - Check logs: NO SIDE MISMATCH error
```

#### Success Metrics:

**Before Fix**:
- SIDE MISMATCH errors: ~1-5 per restart
- Frequency: Every fast reopen

**After Fix**:
- SIDE MISMATCH errors: **0** ✅
- Fast reopens: Clean (no errors)
- DB state: Always correct side

---

## 📊 TESTING CHECKLIST

### Pre-Deployment Tests

- [ ] Read current code (verify bug exists)
- [ ] Apply code fix
- [ ] Run unit test (`test_ts_side_mismatch_fix.py`)
- [ ] Verify test passes
- [ ] Review diff (only 5 lines added)

### Deployment

- [ ] Git add files
- [ ] Git commit with detailed message
- [ ] Git push to main
- [ ] Verify push succeeded

### Post-Deployment Verification

- [ ] Monitor logs for 24 hours
- [ ] Check SIDE MISMATCH error count (should be 0)
- [ ] Verify TS state correctness in DB
- [ ] Test fast position reopen scenario
- [ ] Confirm no performance regression

---

## ⚠️ ROLLBACK PLAN

If issues occur after deployment:

```bash
# 1. Revert commit
git revert HEAD

# 2. Push revert
git push origin main

# 3. Verify rollback
docker logs trading_bot | tail -100

# 4. Investigate issue
# Review error logs
# Check DB state
# Determine if fix caused issue or unrelated
```

**Rollback Risk**: 🟢 LOW (simple revert)

---

## 🎯 SUCCESS CRITERIA

**Must Have** ✅:
1. Zero SIDE MISMATCH errors on restart
2. All TS states have correct side
3. Fast reopens work correctly
4. No new errors introduced

**Nice to Have** 🟢:
1. Performance same or better
2. Code coverage > 80%
3. Documentation complete

---

## 📝 IMPLEMENTATION CHECKLIST

### Preparation
- [x] Root cause identified
- [x] Investigation report created
- [x] Fix plan reviewed

### Implementation (AWAITING APPROVAL)
- [ ] Apply code fix to `database/repository.py`
- [ ] Create unit test `tests/unit/test_ts_side_mismatch_fix.py`
- [ ] Run unit test (verify passes)
- [ ] Review diff

### Deployment
- [ ] Git add files
- [ ] Git commit
- [ ] Git push
- [ ] Monitor logs

### Verification
- [ ] Zero SIDE MISMATCH errors (24h)
- [ ] TS states correct in DB
- [ ] Fast reopens tested
- [ ] Mark as complete

---

## 🔗 REFERENCES

1. **Root Cause Investigation**: `docs/investigations/CRITICAL_TS_SIDE_MISMATCH_ROOT_CAUSE_20251028.md`
2. **Quick Summary**: `docs/investigations/CRITICAL_TS_SIDE_MISMATCH_SUMMARY_20251028.md`
3. **Previous Cleanup Fix**: `docs/investigations/FIX_PLAN_STALE_TS_STATE_VARIANT_A_20251020.md`

---

## 📅 TIMELINE

| Time | Action | Status |
|------|--------|--------|
| T0 | Investigation started | ✅ DONE |
| T+45min | Root cause identified | ✅ DONE |
| T+60min | Fix plan created | ✅ DONE |
| T+XX | User approval | ⏳ WAITING |
| T+XX | Implementation | ⏳ PENDING |
| T+XX | Testing | ⏳ PENDING |
| T+XX | Deployment | ⏳ PENDING |
| T+XX+24h | Verification complete | ⏳ PENDING |

---

**END OF FIX PLAN**

**Status**: ✅ PLANNING COMPLETE - AWAITING USER APPROVAL
**Next Step**: User reviews and approves implementation
**Risk**: 🟢 LOW
**Impact**: 🔴 HIGH (eliminates critical error)
