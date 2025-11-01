# 🧪 DECIMAL MIGRATION - PHASE 2: Testing Plan

**Date**: 2025-10-31
**Phase**: 2 of 4
**Target**: `protection/trailing_stop.py` + `core/position_manager.py`
**Test Strategy**: 3-Level Verification (same as Phase 1)
**Prerequisites**: ✅ Phase 1 Complete (PositionState uses Decimal)

---

## ⚠️ CRITICAL: Testing Philosophy

### User Requirements (from Phase 1):
> "ПОСЛЕ КАЖДОЙ ФАЗЫ 3 ПРОВЕРКИ РАЗНЫМИ МЕТОДАМИ"
> "КРИТИЧЕСКИ ВАЖНО - СДЕЛАТЬ СРАЗУ БЕЗ ОШИБОК"

### Our Approach:
1. **Level 1: Syntax & Type Checking** - Catch compile-time errors
2. **Level 2: Unit & Integration Tests** - Verify behavior unchanged
3. **Level 3: Manual Verification** - Human review of critical paths

**ALL THREE levels must PASS before proceeding to Phase 3!**

---

## 📋 PRE-EXECUTION CHECKLIST

### Before making ANY changes:

- [ ] **Verify Phase 1 Complete**:
  ```bash
  git log -1 --oneline  # Should show Phase 1 commit
  grep "quantity: Decimal" core/position_manager.py  # Verify Phase 1 changes
  ```

- [ ] **Backup created**:
  ```bash
  cp protection/trailing_stop.py protection/trailing_stop.py.BACKUP_PHASE2_$(date +%Y%m%d_%H%M%S)
  # position_manager.py backup not needed (already on git)
  ```

- [ ] **Git branch verified**:
  ```bash
  git branch  # Should show: * feature/decimal-migration-phase1
  git status  # Ensure position_manager.py from Phase 1 is committed
  ```

- [ ] **Baseline tests**:
  ```bash
  python -m py_compile protection/trailing_stop.py
  python -m mypy protection/trailing_stop.py 2>&1 | tail -5
  python -c "from protection.trailing_stop import SmartTrailingStopManager; print('✅ Import OK')"
  ```

- [ ] **Document baseline metrics**:
  - MyPy errors before: ~287 total, ~43 in trailing_stop.py
  - Expected after: ~270 total (-15 to -20 errors)

---

## 🔍 LEVEL 1: Syntax & Type Checking

**Goal**: Catch ALL compile-time errors before runtime testing
**Time**: ~5-7 minutes
**Must pass**: 100% - ZERO failures allowed

### 1.1 Python Syntax Validation

```bash
# Test 1: Syntax check trailing_stop.py
python -m py_compile protection/trailing_stop.py
```

**Expected result**: No output (success)
**If fails**: Syntax error in changes - MUST FIX before proceeding

```bash
# Test 2: Syntax check position_manager.py
python -m py_compile core/position_manager.py
```

**Expected result**: No output (success)

---

### 1.2 Import Verification

```bash
# Test 3: Import TrailingStop module
python -c "from protection.trailing_stop import SmartTrailingStopManager, TrailingStopInstance, TrailingStopConfig"
```

**Expected result**: No output (success)
**If fails**: Import error - check Decimal import exists

```bash
# Test 4: Import position_manager module
python -c "from core.position_manager import PositionManager, PositionState"
```

**Expected result**: No output (success)

---

### 1.3 MyPy Type Checking

```bash
# Test 5: Type check trailing_stop.py
python -m mypy protection/trailing_stop.py --show-error-codes --no-implicit-optional 2>&1 | tail -15
```

**Expected results**:
- ✅ REDUCED errors (from ~43 → ~20-25 in trailing_stop.py)
- ✅ NO errors in changed method signatures (lines 489-491, 606, 1447)
- ✅ NO errors in method bodies (lines 528-533, 621)

**Specific reductions expected**:
- Lines 489-491: `float` → `Decimal` parameter warnings GONE ✓
- Line 606: `float` → `Decimal` parameter warning GONE ✓
- Line 1447: `float` → `Decimal` parameter warning GONE ✓
- Line 621: `Decimal(str(...))` unnecessary warning GONE ✓

```bash
# Test 6: Type check position_manager.py
python -m mypy core/position_manager.py --show-error-codes --no-implicit-optional 2>&1 | grep "trailing" | head -10
```

**Expected results**:
- ✅ NO warnings about passing Decimal to float parameters
- ✅ Lines 614-615: No warnings (float() removed)
- ✅ Lines 901-902: No warnings (to_decimal() added)
- ✅ Line 1301: No warnings (to_decimal() instead of float())

---

### 1.4 Decimal Usage Check

```bash
# Test 7: Verify Decimal import exists
grep -n "^from decimal import Decimal" protection/trailing_stop.py
```

**Expected result**: Line 13 shows Decimal import
**If fails**: Import missing - MUST ADD

```bash
# Test 8: Verify method signatures updated
grep -n "entry_price: Decimal\|quantity: Decimal\|price: Decimal\|realized_pnl: Optional\[Decimal\]" protection/trailing_stop.py
```

**Expected result**: Lines 489, 490, 606, 1447 show Decimal types

---

### 1.5 No Unnecessary Conversions

```bash
# Test 9: Verify Decimal(str(...)) removed from method bodies
grep -n "Decimal(str(entry_price))\|Decimal(str(quantity))\|Decimal(str(price))" protection/trailing_stop.py
```

**Expected result**: NO MATCHES (all removed)
**If matches found**: Conversion not removed - MUST REMOVE

```bash
# Test 10: Verify float() removed from position_manager.py call sites
grep -n "614\|615\|1301" core/position_manager.py | grep "float("
```

**Expected result**: NO MATCHES (all removed/replaced)

---

## 🧪 LEVEL 2: Unit & Integration Tests

**Goal**: Verify behavior unchanged after migration
**Time**: ~15-20 minutes
**Must pass**: 100% - ZERO new failures allowed

### 2.1 Trailing Stop Creation Test

**Create test script** `tests/test_phase2_decimal.py`:

```python
"""Test Phase 2 Decimal migration for TrailingStop"""
import asyncio
from decimal import Decimal
from protection.trailing_stop import SmartTrailingStopManager, TrailingStopConfig
from datetime import datetime

async def test_trailing_stop_creation():
    """Verify create_trailing_stop accepts Decimal"""

    config = TrailingStopConfig(
        activation_percent=Decimal('1.5'),
        callback_percent=Decimal('0.5')
    )

    # Mock exchange and repository (minimal)
    class MockExchange:
        pass

    class MockRepository:
        async def save_trailing_stop_state(self, *args, **kwargs):
            return True

    manager = SmartTrailingStopManager(
        exchange=MockExchange(),
        exchange_name="test",
        repository=MockRepository(),
        config=config
    )

    # Test 1: Create with Decimal parameters
    ts = await manager.create_trailing_stop(
        symbol="BTCUSDT",
        side="long",
        entry_price=Decimal('50000.00'),    # ✅ Decimal parameter
        quantity=Decimal('1.234'),          # ✅ Decimal parameter
        initial_stop=Decimal('49000.00')    # ✅ Decimal parameter
    )

    # Test 2: Verify types
    assert isinstance(ts.entry_price, Decimal), "entry_price must be Decimal"
    assert isinstance(ts.quantity, Decimal), "quantity must be Decimal"
    assert isinstance(ts.current_price, Decimal), "current_price must be Decimal"

    # Test 3: Verify precision
    assert str(ts.entry_price) == '50000.00', f"Precision lost: {ts.entry_price}"
    assert str(ts.quantity) == '1.234', f"Precision lost: {ts.quantity}"

    print("✅ Trailing stop creation test PASSED")

if __name__ == "__main__":
    asyncio.run(test_trailing_stop_creation())
```

**Run test**:
```bash
python tests/test_phase2_decimal.py
```

**Expected result**: ✅ All tests PASSED
**If fails**: Type conversion error - CRITICAL BUG

---

### 2.2 Price Update Test

```python
"""Test update_price with Decimal"""
async def test_price_update():
    """Verify update_price accepts Decimal"""

    # ... (setup manager as above) ...

    # Create trailing stop
    ts = await manager.create_trailing_stop(
        symbol="BTCUSDT",
        side="long",
        entry_price=Decimal('50000.00'),
        quantity=Decimal('1.0')
    )

    # Test: Update with Decimal price
    result = await manager.update_price("BTCUSDT", Decimal('51000.00'))

    # Verify internal price is Decimal
    updated_ts = manager.trailing_stops["BTCUSDT"]
    assert isinstance(updated_ts.current_price, Decimal), "current_price must be Decimal"
    assert str(updated_ts.current_price) == '51000.00', f"Precision lost: {updated_ts.current_price}"

    print("✅ Price update test PASSED")
```

**Run test**:
```bash
python -c "from tests.test_phase2_decimal import test_price_update; import asyncio; asyncio.run(test_price_update())"
```

**Expected result**: ✅ Price update test PASSED

---

### 2.3 Position Close Test

```python
"""Test on_position_closed with Decimal realized_pnl"""
async def test_position_closed():
    """Verify on_position_closed accepts Decimal"""

    # ... (setup manager and create TS as above) ...

    # Test 1: Close with None (should work)
    await manager.on_position_closed("BTCUSDT", realized_pnl=None)

    # Recreate for second test
    await manager.create_trailing_stop(
        symbol="BTCUSDT",
        side="long",
        entry_price=Decimal('50000.00'),
        quantity=Decimal('1.0')
    )

    # Test 2: Close with Decimal realized_pnl
    await manager.on_position_closed("BTCUSDT", realized_pnl=Decimal('1000.00'))

    print("✅ Position close test PASSED")
```

**Expected result**: ✅ Position close test PASSED

---

### 2.4 Integration Test - Full Flow

```python
"""Test full flow: create → update → close"""
async def test_full_flow():
    """Verify entire flow with Decimal"""

    # 1. Create position (Decimal)
    ts = await manager.create_trailing_stop(
        symbol="BTCUSDT",
        side="long",
        entry_price=Decimal('50000.00'),
        quantity=Decimal('1.234')
    )

    # 2. Update price multiple times (Decimal)
    await manager.update_price("BTCUSDT", Decimal('50500.00'))
    await manager.update_price("BTCUSDT", Decimal('51000.00'))
    await manager.update_price("BTCUSDT", Decimal('51500.00'))

    # 3. Verify precision maintained
    ts_after = manager.trailing_stops["BTCUSDT"]
    assert isinstance(ts_after.current_price, Decimal)
    assert str(ts_after.current_price) == '51500.00'

    # 4. Close position (Decimal)
    realized_pnl = (Decimal('51500.00') - Decimal('50000.00')) * Decimal('1.234')
    await manager.on_position_closed("BTCUSDT", realized_pnl=realized_pnl)

    print(f"✅ Full flow test PASSED (realized PnL: {realized_pnl})")
```

**Expected result**: ✅ Full flow test PASSED (realized PnL: 1851.00)

---

### 2.5 Database Round-Trip Test (Optional)

**If test database available**:

```python
"""Test DB save/restore with Decimal"""
async def test_db_roundtrip():
    """Verify Decimal precision in DB round-trip"""

    # Requires real Repository with DB connection
    # Skip if no test DB

    # 1. Create TS with precise Decimal
    ts = await manager.create_trailing_stop(
        symbol="TESTUSDT",
        side="long",
        entry_price=Decimal('50123.45678901'),  # High precision
        quantity=Decimal('1.23456789')
    )

    # 2. Save to DB (should happen automatically)
    # 3. Restore from DB
    restored_ts = await manager._restore_state("TESTUSDT")

    # 4. Verify precision preserved
    assert str(restored_ts.entry_price) == '50123.45678901', "DB precision lost!"
    assert str(restored_ts.quantity) == '1.23456789', "DB precision lost!"

    print("✅ DB round-trip test PASSED - precision preserved")
```

---

## 🔍 LEVEL 3: Manual Verification

**Goal**: Human review of critical code paths
**Time**: ~30-40 minutes
**Must verify**: All critical paths reviewed

### 3.1 Method Signature Verification

#### 3.1.1 create_trailing_stop (Lines 486-492)

```bash
sed -n '486,492p' protection/trailing_stop.py
```

**Verify**:
- [ ] `entry_price: Decimal` (not float)
- [ ] `quantity: Decimal` (not float)
- [ ] `initial_stop: Optional[Decimal]` (not float)
- [ ] All other parameters unchanged

---

#### 3.1.2 update_price (Line 606)

```bash
sed -n '606p' protection/trailing_stop.py
```

**Verify**:
- [ ] `price: Decimal` (not float)

---

#### 3.1.3 on_position_closed (Line 1447)

```bash
sed -n '1447p' protection/trailing_stop.py
```

**Verify**:
- [ ] `realized_pnl: Optional[Decimal] = None` (not float)

---

### 3.2 Internal Conversion Verification

#### 3.2.1 create_trailing_stop Body (Lines 526-535)

```bash
sed -n '526,535p' protection/trailing_stop.py
```

**Verify**: NO `Decimal(str(...))` conversions for:
- [ ] entry_price - direct assignment
- [ ] quantity - direct assignment
- [ ] highest_price - uses entry_price directly
- [ ] lowest_price - uses entry_price directly

**Expected code**:
```python
ts = TrailingStopInstance(
    symbol=symbol,
    entry_price=entry_price,                    # ✅ No Decimal(str(...))
    current_price=entry_price,                  # ✅ No Decimal(str(...))
    highest_price=entry_price if side == 'long' else UNINITIALIZED_PRICE_HIGH,
    lowest_price=UNINITIALIZED_PRICE_HIGH if side == 'long' else entry_price,
    side=side.lower(),
    quantity=quantity,                          # ✅ No Decimal(str(...))
    ...
)
```

---

#### 3.2.2 update_price Body (Line 621)

```bash
sed -n '621p' protection/trailing_stop.py
```

**Verify**:
- [ ] `ts.current_price = price` (NOT `Decimal(str(price))`)

---

### 3.3 Call Site Verification in position_manager.py

#### 3.3.1 _restore_state dict (Lines 614-615)

```bash
sed -n '611,616p' core/position_manager.py
```

**Verify**: NO `float()` conversions:
```python
position_dict = {
    'symbol': symbol,
    'side': position.side,
    'size': safe_get_attr(...),                 # ✅ No float()
    'entryPrice': position.entry_price          # ✅ No float()
}
```

---

#### 3.3.2 Exchange Sync (Lines 901-902)

```bash
sed -n '898,904p' core/position_manager.py
```

**Verify**: `to_decimal()` conversions PRESENT:
```python
await trailing_manager.create_trailing_stop(
    symbol=symbol,
    side=side,
    entry_price=to_decimal(entry_price),        # ✅ Has to_decimal()
    quantity=to_decimal(quantity),              # ✅ Has to_decimal()
    initial_stop=stop_loss_price
)
```

---

#### 3.3.3 Atomic Creation (Line 1301)

```bash
sed -n '1296,1302p' core/position_manager.py
```

**Verify**: `to_decimal()` instead of `float()`:
```python
initial_stop=to_decimal(atomic_result['stop_loss_price'])  # ✅ to_decimal(), NOT float()
```

---

### 3.4 Database Save Verification (Optional)

#### 3.4.1 _save_state Method (Lines 199-216)

```bash
sed -n '199,216p' protection/trailing_stop.py
```

**If DB cleanup applied**, verify NO `float()` conversions:
```python
state_data = {
    'entry_price': ts.entry_price,              # ✅ No float()
    'current_price': ts.current_price,          # ✅ No float()
    'quantity': ts.quantity,                    # ✅ No float()
    ...
}
```

**If DB cleanup NOT applied**, verify `float()` present (OK for Phase 2):
```python
state_data = {
    'entry_price': float(ts.entry_price),       # ⚠️ Still has float() - OK
    ...
}
```

---

### 3.5 Docstring Verification

#### 3.5.1 _restore_state Docstring (Line 239)

```bash
sed -n '239p' protection/trailing_stop.py
```

**Verify**: Documentation updated to Decimal:
```python
"""Format: {'symbol': str, 'side': str, 'size': Decimal, 'entryPrice': Decimal}"""
```

---

## ✅ FINAL VERIFICATION CHECKLIST

### Before declaring Phase 2 COMPLETE:

#### Level 1: Syntax ✓
- [ ] Python syntax check PASSED (both files)
- [ ] Import check PASSED (both modules)
- [ ] MyPy error count DECREASED (-15 to -20 errors)
- [ ] Decimal import present in trailing_stop.py
- [ ] Method signatures correct (3 methods, 5 parameters)
- [ ] No unnecessary `Decimal(str(...))` conversions

#### Level 2: Tests ✓
- [ ] Trailing stop creation test PASSED
- [ ] Price update test PASSED
- [ ] Position close test PASSED
- [ ] Full flow integration test PASSED
- [ ] Database round-trip test PASSED (if applicable)

#### Level 3: Manual ✓
- [ ] Method signatures reviewed (lines 489-492, 606, 1447)
- [ ] Internal conversions removed (lines 528-535, 621)
- [ ] Call sites fixed in position_manager.py (lines 614-615, 901-902, 1301)
- [ ] Database save verified (lines 199-216)
- [ ] Docstring updated (line 239)

---

## 🚨 ROLLBACK PROCEDURE

**If ANY test fails**:

### Immediate Rollback:

```bash
# Restore trailing_stop.py backup
cp protection/trailing_stop.py.BACKUP_PHASE2_* protection/trailing_stop.py

# Restore position_manager.py from git (Phase 1 state)
git checkout core/position_manager.py
git add core/position_manager.py
git commit -m "revert: rollback Phase 2 position_manager.py changes"

# Verify restoration
git diff protection/trailing_stop.py  # Should show no changes
python -m py_compile protection/trailing_stop.py
```

### Investigation:

1. **Document the failure**:
   - Which test failed?
   - Error message?
   - Expected vs actual?

2. **Analyze root cause**:
   - Syntax error? (Level 1)
   - Type error? (Level 1)
   - Behavior change? (Level 2)
   - Integration issue? (Level 2 or 3)

3. **Fix in DETAILED_PLAN.md**:
   - Update plan with correction
   - Re-review all changes
   - Re-execute testing plan

**DO NOT PROCEED** until all tests pass!

---

## 📊 SUCCESS CRITERIA

### Phase 2 is COMPLETE when:

1. ✅ **All Level 1 tests PASS** (syntax, types, imports, MyPy)
2. ✅ **All Level 2 tests PASS** (creation, update, close, integration)
3. ✅ **All Level 3 verifications COMPLETE** (manual review of all changes)
4. ✅ **Zero new bugs introduced**
5. ✅ **Zero precision loss in trailing stop operations**
6. ✅ **MyPy error count decreased** (not increased)
7. ✅ **Call sites work correctly** (position_manager → trailing_stop)

### Ready for:
- ✅ Git commit with detailed message
- ✅ Code review (if team)
- ✅ Begin Phase 3 planning (StopLossManager) or merge to main

---

## 📝 EXECUTION LOG TEMPLATE

**Use this to document your testing session**:

```markdown
# Phase 2 Execution Log

**Date**: 2025-10-31
**Executor**: [Your Name]
**Start Time**: [HH:MM]

## Changes Made:
- [ ] trailing_stop.py method signatures updated (3 methods)
- [ ] trailing_stop.py internal conversions removed (6 lines)
- [ ] position_manager.py call sites fixed (5 lines)
- [ ] Docstring updated (1 line)
- [ ] Optional: DB save float() removed (10-15 lines)

## Level 1 Results:
- Syntax check (trailing_stop.py): ✅ PASS / ❌ FAIL - [details]
- Syntax check (position_manager.py): ✅ PASS / ❌ FAIL - [details]
- Import check: ✅ PASS / ❌ FAIL - [details]
- MyPy before: 287 errors
- MyPy after: XX errors (decreased: YES/NO)
- Decimal conversions removed: ✅ YES / ❌ NO

## Level 2 Results:
- TS creation test: ✅ PASS / ❌ FAIL - [precision: X.XXXXXXXX]
- Price update test: ✅ PASS / ❌ FAIL
- Position close test: ✅ PASS / ❌ FAIL
- Full flow test: ✅ PASS / ❌ FAIL
- DB round-trip test: ✅ PASS / ❌ FAIL / ⏭️ SKIPPED

## Level 3 Results:
- Method signatures review: ✅ COMPLETE
- Internal conversions review: ✅ COMPLETE
- Call sites review: ✅ COMPLETE (3 locations)
- Database save review: ✅ COMPLETE
- Docstring review: ✅ COMPLETE

## Issues Found:
[List any issues or notes]

## Final Decision:
- [ ] ✅ Phase 2 COMPLETE - Ready to commit
- [ ] ❌ Phase 2 INCOMPLETE - Rollback and fix
- [ ] ⏸️ Phase 2 PAUSED - Need clarification

**End Time**: [HH:MM]
**Duration**: [XX minutes]
```

---

## 📊 METRICS TARGETS

| Metric | Target | How to Verify |
|--------|--------|---------------|
| MyPy errors | -15 to -20 | Before/after comparison |
| Precision loss | 0 | Decimal tests |
| Breaking changes | 0 | All tests pass |
| Logic changes | 0 | Code review |
| Refactoring | 0 | Diff inspection |
| Files modified | 2 | git status |
| Lines changed | 13-28 | git diff --stat |

---

## 🔗 RELATED DOCUMENTS

- **Phase 2 Detailed Plan**: `MIGRATION_PHASE2_DETAILED_PLAN.md`
- **Phase 2 Usage Analysis**: `MIGRATION_PHASE2_USAGE_ANALYSIS.md`
- **Phase 1 Testing Plan**: `MIGRATION_PHASE1_TESTING_PLAN.md` (reference)
- **Phase 1 Execution Log**: `MIGRATION_PHASE1_EXECUTION_LOG.md` (precedent)

---

**Generated**: 2025-10-31
**Status**: ✅ READY FOR EXECUTION
**Next Step**: Execute Phase 2 changes following DETAILED_PLAN.md
**Estimated Duration**: 1-1.5 hours (including testing)
