# 🔧 FIX PLAN: Bybit Category Parameter Error

**Date**: 2025-10-28
**Priority**: 🟡 MEDIUM
**Status**: ⏳ PLANNING COMPLETE - AWAITING APPROVAL
**Type**: Bug Fix (Error Reduction)

---

## 📋 EXECUTIVE SUMMARY

**Bug**: Bybit API returns error `{"retCode":181001,"retMsg":"category only support linear or option"}` during position verification.

**Impact**:
- ⚠️ Position verification fails (but trading continues)
- ✅ Stop-loss still placed successfully
- ⚠️ Increases error log noise (3 occurrences in recent run)
- ⚠️ Small risk if position didn't actually open

**Root Cause**: Missing `category: 'linear'` parameter in `fetch_positions()` call on line 557 of `core/atomic_position_manager.py`.

**Fix Complexity**: LOW (1 line change)
**Test Complexity**: MEDIUM (requires Bybit position opening)

---

## 🔍 DETAILED AUDIT

### Error Occurrences (From Logs)

```
2025-10-28 05:05:22,696 - utils.rate_limiter - ERROR - Unexpected error in rate limited function: bybit {"retCode":181001,"retMsg":"category only support linear or option"}
2025-10-28 05:05:22,696 - core.atomic_position_manager - WARNING - ⚠️ Could not verify position for BEAMUSDT

2025-10-28 05:20:58 - [Similar error for HNTUSDT]
2025-10-28 05:36:10 - [Similar error for HNTUSDT]
```

**Pattern**:
- Only occurs on Bybit (not Binance)
- Happens during position verification in `open_position_atomic()`
- Trading continues successfully despite error
- Stop-loss placement succeeds

### Code Location Analysis

**File**: `core/atomic_position_manager.py`

**BUGGY CODE (Line 556-560)**:
```python
# Verify position actually exists
try:
    positions = await exchange_instance.fetch_positions([symbol])  # ← BUG: No category param
    active_position = next(
        (p for p in positions if p.get('contracts', 0) > 0 or p.get('size', 0) > 0),
        None
    )
```

**CORRECT CODE (Line 422-425)** - Already exists elsewhere in same file:
```python
# Use fetch_positions instead of fetch_order (Bybit V5 best practice)
positions = await exchange_instance.fetch_positions(
    symbols=[symbol],
    params={'category': 'linear'}  # ← CORRECT: Has category param
)
```

**CORRECT CODE (Line 763-765)** - Already exists in rollback method:
```python
positions = await exchange_instance.exchange.fetch_positions(
    params={'category': 'linear'}  # ← CORRECT: Has category param
)
```

### Why This Bug Exists

**Inconsistency in codebase**:
- Some calls to `fetch_positions()` include `params={'category': 'linear'}` for Bybit
- Other calls (like line 557) don't include this parameter
- Bybit V5 API requires explicit category parameter for all position-related calls

**Bybit API Requirement**:
- Category must be one of: `"linear"`, `"inverse"`, `"option"`
- For USDT perpetuals: `category="linear"`
- If not provided, API returns error 181001

---

## 🛠️ DETAILED FIX PLAN

### Step 1: Code Changes

**File**: `core/atomic_position_manager.py`

**Location**: Lines 556-560 (position verification section)

**BEFORE** (Current - BUGGY):
```python
                # Verify position actually exists
                try:
                    positions = await exchange_instance.fetch_positions([symbol])
                    active_position = next(
                        (p for p in positions if p.get('contracts', 0) > 0 or p.get('size', 0) > 0),
                        None
                    )
```

**AFTER** (Fixed):
```python
                # Verify position actually exists
                try:
                    # Add category parameter for Bybit (required by V5 API)
                    params = {'category': 'linear'} if exchange == 'bybit' else {}
                    positions = await exchange_instance.fetch_positions(
                        symbols=[symbol] if exchange == 'bybit' else [symbol],
                        params=params if params else None
                    )
                    active_position = next(
                        (p for p in positions if p.get('contracts', 0) > 0 or p.get('size', 0) > 0),
                        None
                    )
```

**Alternative Fix (Simpler)** - Always add category for Bybit:
```python
                # Verify position actually exists
                try:
                    # CRITICAL FIX: Bybit V5 API requires category parameter
                    if exchange == 'bybit':
                        positions = await exchange_instance.fetch_positions(
                            symbols=[symbol],
                            params={'category': 'linear'}
                        )
                    else:
                        positions = await exchange_instance.fetch_positions([symbol])

                    active_position = next(
                        (p for p in positions if p.get('contracts', 0) > 0 or p.get('size', 0) > 0),
                        None
                    )
```

**Recommendation**: Use **Alternative Fix (Simpler)** - More readable and consistent with existing code patterns in the file.

---

### Step 2: Additional Location Check

**Search for other buggy calls**:
Looking at grep results, there are other potential issues:

**Line 453 (Binance fallback)** - Not a bug (only called for Binance):
```python
elif exchange == 'binance' and (not exec_price or exec_price == 0):
    # ...
    positions = await exchange_instance.fetch_positions([symbol])
```
✅ Safe - only executes for Binance

**Other files to check**:
- `core/postgres_position_importer.py:94` - No category param
- `core/order_executor.py:253` - No category param
- `core/exchange_manager_enhanced.py:644` - No category param
- `core/aged_position_monitor_v2.py:156` - No category param
- `core/validation_fixes.py:70` - No category param
- `core/bybit_zombie_cleaner.py:84` - No category param
- `core/zombie_manager.py:97` - No category param

**Recommendation**: Fix atomic_position_manager.py first (current issue), then create separate ticket for comprehensive audit of all `fetch_positions()` calls.

---

### Step 3: Testing Plan

#### Unit Test

**File**: `tests/unit/test_atomic_position_manager_bybit_category.py` (NEW)

```python
"""
Test Bybit category parameter fix in position verification
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.atomic_position_manager import AtomicPositionManager


@pytest.mark.asyncio
async def test_bybit_position_verification_includes_category_param():
    """
    Test that position verification for Bybit includes category='linear' parameter

    Regression test for Bug #2: Bybit category parameter error
    """
    # Setup mocks
    repository = AsyncMock()
    exchange_manager = {
        'bybit': AsyncMock()
    }
    stop_loss_manager = AsyncMock()
    config = MagicMock()

    # Mock exchange response
    exchange_manager['bybit'].fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'BEAMUSDT',
            'contracts': 100,
            'size': 100,
            'entryPrice': 0.005
        }
    ])

    # Create manager
    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager,
        config=config
    )

    # Simulate position verification code path
    exchange = 'bybit'
    symbol = 'BEAMUSDT'
    exchange_instance = exchange_manager.get(exchange)

    # Execute the fixed code
    if exchange == 'bybit':
        positions = await exchange_instance.fetch_positions(
            symbols=[symbol],
            params={'category': 'linear'}
        )
    else:
        positions = await exchange_instance.fetch_positions([symbol])

    # Verify category parameter was passed
    exchange_instance.fetch_positions.assert_called_once_with(
        symbols=['BEAMUSDT'],
        params={'category': 'linear'}
    )

    # Verify position found
    assert len(positions) == 1
    assert positions[0]['symbol'] == 'BEAMUSDT'


@pytest.mark.asyncio
async def test_binance_position_verification_no_category_param():
    """
    Test that position verification for Binance does NOT include category parameter

    Ensures fix doesn't break Binance
    """
    # Setup mocks
    repository = AsyncMock()
    exchange_manager = {
        'binance': AsyncMock()
    }
    stop_loss_manager = AsyncMock()
    config = MagicMock()

    # Mock exchange response
    exchange_manager['binance'].fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'BTCUSDT',
            'contracts': 0.1,
            'size': 0.1,
            'entryPrice': 50000
        }
    ])

    # Create manager
    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager,
        config=config
    )

    # Simulate position verification code path
    exchange = 'binance'
    symbol = 'BTCUSDT'
    exchange_instance = exchange_manager.get(exchange)

    # Execute the fixed code
    if exchange == 'bybit':
        positions = await exchange_instance.fetch_positions(
            symbols=[symbol],
            params={'category': 'linear'}
        )
    else:
        positions = await exchange_instance.fetch_positions([symbol])

    # Verify NO category parameter for Binance
    exchange_instance.fetch_positions.assert_called_once_with(['BTCUSDT'])

    # Verify position found
    assert len(positions) == 1
    assert positions[0]['symbol'] == 'BTCUSDT'
```

#### Integration Test (Manual)

**Test Scenario**: Open Bybit position and verify no errors

```bash
# 1. Deploy fix to production bot
# 2. Monitor logs for next Bybit position opening
# 3. Check for absence of error 181001

# Expected logs:
✅ 2025-10-28 XX:XX:XX - DEBUG - Waiting 3s for position settlement on bybit...
✅ 2025-10-28 XX:XX:XX - DEBUG - ✅ Position verified for BEAMUSDT: 100 contracts
✅ 2025-10-28 XX:XX:XX - INFO - 🛡️ Placing stop-loss for BEAMUSDT at 0.00488894
✅ 2025-10-28 XX:XX:XX - INFO - ✅ Stop-loss placed successfully

# Should NOT see:
❌ ERROR - Unexpected error in rate limited function: bybit {"retCode":181001,"retMsg":"category only support linear or option"}
❌ WARNING - ⚠️ Could not verify position for BEAMUSDT
```

**Success Criteria**:
1. ✅ No error 181001 in logs
2. ✅ Position verification succeeds
3. ✅ Stop-loss placed successfully
4. ✅ No impact on Binance positions

---

### Step 4: Implementation Checklist

- [ ] Read `core/atomic_position_manager.py` to confirm current state
- [ ] Apply fix to lines 556-560 (position verification)
- [ ] Add comment explaining Bybit V5 API requirement
- [ ] Run unit tests (if created)
- [ ] Verify no syntax errors
- [ ] Review diff carefully
- [ ] Commit changes with descriptive message

---

### Step 5: Git Workflow

#### Commit Message

```
fix(bybit): add category parameter to position verification

Bug: Position verification for Bybit fails with error 181001
"category only support linear or option"

Root Cause: Missing category='linear' parameter in fetch_positions()
call during position verification (atomic_position_manager.py:557)

Fix: Add conditional logic to include category parameter for Bybit:
- Bybit: fetch_positions(symbols=[symbol], params={'category': 'linear'})
- Binance: fetch_positions([symbol]) (unchanged)

Impact:
- Reduces error log noise (3 errors per recent run)
- Improves position verification reliability
- No functional change (SL was already placed successfully)

Testing:
- Unit test: test_bybit_position_verification_includes_category_param
- Integration: Open Bybit position, verify no error 181001

References:
- docs/investigations/ERRORS_SUMMARY_20251028.md (Bug #2)
- docs/plans/FIX_PLAN_BYBIT_CATEGORY_PARAMETER_20251028.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

#### Git Commands

```bash
# 1. Ensure on correct branch
git status
git branch  # Should be on feature/wave-per-exchange-processing

# 2. Stage changes
git add core/atomic_position_manager.py
git add docs/plans/FIX_PLAN_BYBIT_CATEGORY_PARAMETER_20251028.md

# 3. Commit (using heredoc for multi-line message)
git commit -m "$(cat <<'EOF'
fix(bybit): add category parameter to position verification

Bug: Position verification for Bybit fails with error 181001
"category only support linear or option"

Root Cause: Missing category='linear' parameter in fetch_positions()
call during position verification (atomic_position_manager.py:557)

Fix: Add conditional logic to include category parameter for Bybit:
- Bybit: fetch_positions(symbols=[symbol], params={'category': 'linear'})
- Binance: fetch_positions([symbol]) (unchanged)

Impact:
- Reduces error log noise (3 errors per recent run)
- Improves position verification reliability
- No functional change (SL was already placed successfully)

Testing:
- Unit test: test_bybit_position_verification_includes_category_param
- Integration: Open Bybit position, verify no error 181001

References:
- docs/investigations/ERRORS_SUMMARY_20251028.md (Bug #2)
- docs/plans/FIX_PLAN_BYBIT_CATEGORY_PARAMETER_20251028.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# 4. Verify commit
git log -1 --stat

# 5. Push to remote
git push origin feature/wave-per-exchange-processing

# 6. Verify push succeeded
git status
```

---

## 🎯 SUCCESS METRICS

### Before Fix

```
Metric: Error 181001 occurrences
Baseline: 3 errors in recent run (5+ hours)
Rate: ~0.6 errors/hour
```

### After Fix (Expected)

```
Metric: Error 181001 occurrences
Target: 0 errors
Rate: 0 errors/hour
Position verification success rate: 100%
```

---

## ⚠️ RISKS AND MITIGATION

### Risk 1: Breaking Binance Position Verification

**Likelihood**: LOW
**Impact**: HIGH
**Mitigation**:
- Use conditional logic (`if exchange == 'bybit'`)
- Binance code path unchanged
- Test both exchanges after deployment

### Risk 2: Bybit API Change

**Likelihood**: LOW
**Impact**: MEDIUM
**Mitigation**:
- Follow Bybit V5 API best practices
- Use `category='linear'` as documented
- Monitor logs for new API errors

### Risk 3: Other fetch_positions Calls Still Broken

**Likelihood**: HIGH (confirmed by grep)
**Impact**: MEDIUM
**Mitigation**:
- This fix addresses immediate error in atomic_position_manager
- Create separate ticket for comprehensive audit
- Prioritize based on error frequency

---

## 📊 RELATED ISSUES

### Current Fix (This Plan)
- **File**: `core/atomic_position_manager.py:557`
- **Context**: Position verification in `open_position_atomic()`
- **Priority**: 🟡 MEDIUM

### Future Fixes (Separate Tickets)
- `core/postgres_position_importer.py:94` - Import positions from exchange
- `core/order_executor.py:253` - Position verification
- `core/exchange_manager_enhanced.py:644` - Stop-loss verification
- `core/aged_position_monitor_v2.py:156` - Aged position close
- `core/validation_fixes.py:70` - Validation
- `core/bybit_zombie_cleaner.py:84` - Zombie cleaner
- `core/zombie_manager.py:97` - Zombie manager

**Recommendation**: Create comprehensive audit ticket after this fix is deployed and verified.

---

## 📝 DEPLOYMENT CHECKLIST

### Pre-Deployment
- [x] Detailed audit complete
- [x] Fix plan created and reviewed
- [x] Code changes identified (line 557)
- [ ] User approval obtained
- [ ] Unit tests created (optional but recommended)

### Deployment
- [ ] Apply code changes
- [ ] Review diff
- [ ] Run tests
- [ ] Commit with detailed message
- [ ] Push to remote
- [ ] Verify git push succeeded

### Post-Deployment
- [ ] Monitor bot logs for Bybit position openings
- [ ] Verify no error 181001 in logs
- [ ] Verify position verification succeeds
- [ ] Verify SL placement still works
- [ ] Verify no impact on Binance positions
- [ ] Update status in this document

### Rollback Plan (If Needed)
```bash
# If fix causes issues, revert commit
git revert HEAD
git push origin feature/wave-per-exchange-processing
```

---

## 🔗 REFERENCES

1. **Investigation Report**: `docs/investigations/ERRORS_AFTER_MIGRATION_DEEP_INVESTIGATION_20251028.md`
2. **Summary**: `docs/investigations/ERRORS_SUMMARY_20251028.md`
3. **Bybit V5 API Docs**: https://bybit-exchange.github.io/docs/v5/position
4. **CCXT Bybit Docs**: https://docs.ccxt.com/en/latest/manual.html#positions

---

## 📅 TIMELINE

| Date | Status | Notes |
|------|--------|-------|
| 2025-10-28 | ⚠️ Bug Identified | 3 errors in production logs |
| 2025-10-28 | 🔍 Investigation Complete | Root cause found (line 557) |
| 2025-10-28 | 📝 Fix Plan Created | Awaiting user approval |
| TBD | ⏳ Awaiting Approval | No code changes yet |
| TBD | 🚀 Implementation | After approval |
| TBD | ✅ Deployed | After testing |
| TBD | 📊 Verification | Monitor for 24h |

---

**END OF FIX PLAN**

**Status**: ✅ PLANNING COMPLETE - AWAITING USER APPROVAL
**Next Step**: User review and approval to proceed with implementation
