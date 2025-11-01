# 🧪 DECIMAL MIGRATION - PHASE 1: Testing Plan

**Date**: 2025-10-31
**Phase**: 1 of 4
**Target**: `core/position_manager.py` - PositionState dataclass
**Test Strategy**: 3-Level Verification (as required)

---

## ⚠️ CRITICAL: Testing Philosophy

### User Requirements:
> "ПОСЛЕ КАЖДОЙ ФАЗЫ 3 ПРОВЕРКИ РАЗНЫМИ МЕТОДАМИ"
> "КРИТИЧЕСКИ ВАЖНО - СДЕЛАТЬ СРАЗУ БЕЗ ОШИБОК"

### Our Approach:
1. **Level 1: Syntax & Type Checking** - Catch compile-time errors
2. **Level 2: Unit & Integration Tests** - Verify behavior unchanged
3. **Level 3: Manual Verification** - Human review of critical paths

**ALL THREE levels must PASS before proceeding to next phase!**

---

## 📋 PRE-EXECUTION CHECKLIST

### Before making ANY changes:

- [ ] **Backup created**:
  ```bash
  cp core/position_manager.py core/position_manager.py.BACKUP_$(date +%Y%m%d_%H%M%S)
  ```

- [ ] **Git branch created**:
  ```bash
  git checkout -b feature/decimal-migration-phase1
  git status  # Ensure clean working directory
  ```

- [ ] **Baseline tests PASS**:
  ```bash
  pytest tests/ -v --tb=short
  python -m mypy core/position_manager.py
  python -m flake8 core/position_manager.py
  ```

- [ ] **Document baseline metrics**:
  - Current MyPy errors: 55 in position_manager.py
  - Current test failures: 0 (should be 0!)
  - Current warnings: (document count)

---

## 🔍 LEVEL 1: Syntax & Type Checking

**Goal**: Catch ALL compile-time errors before runtime testing
**Time**: ~5 minutes
**Must pass**: 100% - ZERO failures allowed

### 1.1 Python Syntax Validation

```bash
# Test 1: Syntax check
python -m py_compile core/position_manager.py
```

**Expected result**: No output (success)
**If fails**: Syntax error in changes - MUST FIX before proceeding

---

### 1.2 Import Verification

```bash
# Test 2: Import check
python -c "from core.position_manager import PositionManager, PositionState"
```

**Expected result**: No output (success)
**If fails**: Import error (missing Decimal import?) - MUST FIX

---

### 1.3 MyPy Type Checking

```bash
# Test 3: Type checking (full strictness)
python -m mypy core/position_manager.py --show-error-codes --no-implicit-optional
```

**Expected results**:
- ✅ REDUCED errors (from 55 → ~35-40)
- ✅ NO NEW errors related to our changes
- ✅ Specific reductions expected:
  - Lines 815-820: Decimal→float errors SHOULD REMAIN (justified)
  - Lines 2270-2274: float() in percentage calc - CORRECT
  - Line 165: `opened_at: Optional[datetime]` - FIXED ✓

**If fails**: New type errors introduced - MUST INVESTIGATE

**Verification checklist**:
- [ ] Error count decreased (not increased)
- [ ] No errors in dataclass definition (lines 135-165)
- [ ] No errors in 6 creation sites (lines 414, 810, 1701, etc.)
- [ ] float() conversions properly typed

---

### 1.4 Decimal Import Check

```bash
# Test 4: Verify Decimal imported
grep -n "^from decimal import Decimal" core/position_manager.py
```

**Expected result**: Line number showing import
**If fails**: Forgot to add import - MUST ADD

---

### 1.5 Dataclass Definition Check

```bash
# Test 5: Verify dataclass fields changed
grep -A 15 "class PositionState:" core/position_manager.py | grep "quantity\|entry_price\|current_price\|unrealized_pnl\|stop_loss_price"
```

**Expected output**:
```python
quantity: Decimal
entry_price: Decimal
current_price: Decimal
unrealized_pnl: Decimal
stop_loss_price: Optional[Decimal] = None
```

**Verify**:
- [ ] All 5 money fields use Decimal
- [ ] unrealized_pnl_percent remains float (percentage!)
- [ ] age_hours remains float (time!)
- [ ] Optional[Decimal] for stop_loss_price

---

## 🧪 LEVEL 2: Unit & Integration Tests

**Goal**: Verify behavior unchanged after migration
**Time**: ~15-20 minutes
**Must pass**: 100% - ZERO new failures allowed

### 2.1 Full Test Suite

```bash
# Test 6: Run all tests
pytest tests/ -v --tb=short -x
```

**Expected result**: All tests PASS (same as baseline)
**If fails**: Behavior changed - MUST INVESTIGATE

**Pay special attention to**:
- Position creation tests
- Database interaction tests
- Stop loss tests
- Trailing stop tests
- PnL calculation tests

---

### 2.2 Position Manager Specific Tests

```bash
# Test 7: Run position_manager tests only
pytest tests/ -k "position_manager" -v --tb=short
```

**Expected result**: 100% pass
**If fails**: Core functionality broken

---

### 2.3 Database Integration Tests

```bash
# Test 8: Database round-trip (Decimal → DB → Decimal)
pytest tests/ -k "database or repository" -v --tb=short
```

**Critical verification**:
- [ ] PositionState with Decimal values saves to DB
- [ ] Values retrieved from DB are Decimal (not float!)
- [ ] No precision loss in round-trip
- [ ] asyncpg correctly handles Decimal→numeric

**If fails**: Database integration broken - CRITICAL BUG

---

### 2.4 Precision Preservation Test

**Create manual test script** `tests/test_decimal_precision.py`:

```python
"""Test Decimal precision preservation after Phase 1 migration"""
import asyncio
from decimal import Decimal
from core.position_manager import PositionState
from datetime import datetime

async def test_position_state_precision():
    """Verify PositionState preserves Decimal precision"""

    # Test 1: Create PositionState with precise Decimal
    position = PositionState(
        id=1,
        symbol="BTCUSDT",
        exchange="bybit",
        side="long",
        quantity=Decimal('1.23456789'),
        entry_price=Decimal('50123.45678901'),
        current_price=Decimal('50456.78901234'),
        unrealized_pnl=Decimal('333.33333333'),
        unrealized_pnl_percent=0.66,  # float - correct!
        stop_loss_price=Decimal('49120.98765432'),
        opened_at=datetime.utcnow(),
        age_hours=2.5
    )

    # Test 2: Verify types
    assert isinstance(position.quantity, Decimal), "quantity must be Decimal"
    assert isinstance(position.entry_price, Decimal), "entry_price must be Decimal"
    assert isinstance(position.current_price, Decimal), "current_price must be Decimal"
    assert isinstance(position.unrealized_pnl, Decimal), "unrealized_pnl must be Decimal"
    assert isinstance(position.stop_loss_price, Decimal), "stop_loss_price must be Decimal"

    # Test 3: Verify precision preserved
    assert str(position.entry_price) == '50123.45678901', f"Precision lost: {position.entry_price}"
    assert str(position.quantity) == '1.23456789', f"Precision lost: {position.quantity}"

    # Test 4: Verify float fields remain float
    assert isinstance(position.unrealized_pnl_percent, float), "percentage must be float"
    assert isinstance(position.age_hours, float), "age_hours must be float"

    print("✅ All precision tests PASSED")

if __name__ == "__main__":
    asyncio.run(test_position_state_precision())
```

**Run test**:
```bash
python tests/test_decimal_precision.py
```

**Expected result**: ✅ All precision tests PASSED
**If fails**: Type conversion error or precision loss - CRITICAL BUG

---

### 2.5 Float Conversion Safety Test

**Verify float() conversions work correctly**:

```python
"""Test that required float() conversions work after migration"""
import asyncio
from decimal import Decimal
from core.position_manager import PositionState

def test_float_conversions():
    """Verify float() conversions for external APIs"""

    position = PositionState(
        id=1, symbol="BTCUSDT", exchange="bybit", side="long",
        quantity=Decimal('1.234'), entry_price=Decimal('50000.00'),
        current_price=Decimal('51000.00'), unrealized_pnl=Decimal('1234.00'),
        unrealized_pnl_percent=2.46, stop_loss_price=Decimal('49000.00'),
        opened_at=None, age_hours=0
    )

    # Test float() conversions (required for external APIs)
    assert float(position.quantity) == 1.234
    assert float(position.entry_price) == 50000.00
    assert isinstance(float(position.current_price), float)

    # Test JSON serialization (event logging)
    import json
    from core.event_logger import DecimalEncoder

    event_data = {
        'entry_price': float(position.entry_price),  # Explicit conversion
        'quantity': float(position.quantity)
    }
    json_str = json.dumps(event_data, cls=DecimalEncoder)
    assert '"entry_price": 50000.0' in json_str

    print("✅ Float conversion tests PASSED")

if __name__ == "__main__":
    test_float_conversions()
```

**Run test**:
```bash
python tests/test_float_conversions.py
```

**Expected result**: ✅ Float conversion tests PASSED

---

## 🔍 LEVEL 3: Manual Verification

**Goal**: Human review of critical code paths
**Time**: ~30-40 minutes
**Must verify**: All critical paths reviewed

### 3.1 Code Review Checklist

#### 3.1.1 Dataclass Definition (lines 135-165)

- [ ] **Line 135-165**: Verify dataclass structure
  ```bash
  sed -n '135,165p' core/position_manager.py
  ```

  **Verify**:
  - [ ] `from decimal import Decimal` at top of file
  - [ ] `quantity: Decimal` (not float)
  - [ ] `entry_price: Decimal` (not float)
  - [ ] `current_price: Decimal` (not float)
  - [ ] `unrealized_pnl: Decimal` (not float)
  - [ ] `unrealized_pnl_percent: float` (CORRECT - percentage!)
  - [ ] `stop_loss_price: Optional[Decimal] = None` (not float)
  - [ ] `opened_at: Optional[datetime] = None` (MyPy error fixed)
  - [ ] `age_hours: float = 0` (CORRECT - time!)

---

#### 3.1.2 Creation Site 1: Line 414-420

```bash
sed -n '410,425p' core/position_manager.py
```

**Verify**:
- [ ] `quantity=` uses Decimal (no float() conversion)
- [ ] `entry_price=` uses Decimal (no float() conversion)
- [ ] `current_price=` uses Decimal (no float() conversion)
- [ ] `unrealized_pnl=Decimal('0')` (not 0.0)

**Expected pattern**:
```python
position_state = PositionState(
    # ... other fields ...
    quantity=to_decimal(position.quantity),  # or direct Decimal
    entry_price=to_decimal(position.entry_price),
    current_price=to_decimal(position.current_price),
    unrealized_pnl=Decimal('0'),  # NOT 0.0
    # ...
)
```

---

#### 3.1.3 Creation Site 2: Line 810-820

```bash
sed -n '805,825p' core/position_manager.py
```

**Verify**:
- [ ] **REMOVED** `float()` conversions from DB data
- [ ] DB data passed directly (already Decimal from asyncpg)

**Before (WRONG)**:
```python
quantity=float(position.quantity),  # ❌ PRECISION LOSS
entry_price=float(position.entry_price),  # ❌ PRECISION LOSS
```

**After (CORRECT)**:
```python
quantity=to_decimal(position.quantity),  # ✅ or direct pass
entry_price=to_decimal(position.entry_price),  # ✅ or direct pass
```

---

#### 3.1.4 Creation Site 6: Line 1701 (Database Load)

```bash
sed -n '1695,1710p' core/position_manager.py
```

**CRITICAL VERIFICATION**:
- [ ] **REMOVED** `float()` conversions from DB values
- [ ] DB dict values passed DIRECTLY (asyncpg returns Decimal)

**Before (BUG!)**:
```python
quantity=float(pos['quantity']),        # ❌ DB returns Decimal, converting to float LOSES precision!
entry_price=float(pos['entry_price']),  # ❌ LOSES precision
```

**After (CORRECT)**:
```python
quantity=pos['quantity'],        # ✅ DB returns Decimal, keep it!
entry_price=pos['entry_price'],  # ✅ Keep Decimal
```

**This is THE MOST CRITICAL fix** - prevents precision loss from database!

---

### 3.2 Critical float() Conversion Review

#### 3.2.1 Event Logging (SAFE - keep float())

```bash
# Check event logging float() conversions
grep -n "float(position\." core/position_manager.py | grep -A 2 -B 2 "log_event"
```

**Verify**: float() conversions PRESENT and CORRECT
- [ ] Lines 563-564: Event logging - float() present ✓
- [ ] Lines 1466-1467: Event logging - float() present ✓

**Reason**: JSON serialization safety (explicit better than implicit)

---

#### 3.2.2 Stop Loss Manager API (SAFE - keep float())

```bash
# Check StopLossManager.set_stop_loss calls
grep -n -A 3 "sl_manager.set_stop_loss" core/position_manager.py
```

**Verify**: float() conversions PRESENT
- [ ] Line 2142: `amount=float(position.quantity)` - REQUIRED ✓

**Reason**: StopLossManager API requires float (will fix in Phase 2)

---

#### 3.2.3 Trailing Stop API (SAFE - keep float())

```bash
# Check trailing_manager._restore_state calls
grep -n -A 5 "_restore_state" core/position_manager.py
```

**Verify**: float() conversions PRESENT
- [ ] Lines 614-615: position_dict with float() - REQUIRED ✓

**Reason**: TrailingStopManager API requires float (will fix in Phase 2)

---

#### 3.2.4 Database Updates (CRITICAL - NO float()!)

```bash
# Check repository.update_position calls
grep -n -A 5 "repository.update_position\|repository.update_position_stop_loss" core/position_manager.py
```

**CRITICAL VERIFICATION**:
- [ ] Line 2287-2289: `update_position(current_price=position.current_price)` - NO float() ✓
- [ ] Line 574: `update_position_stop_loss(position.id, stop_loss_price)` - NO float() ✓

**Verify NO float() before database writes!**

**If float() found**: CRITICAL BUG - removes precision before saving!

---

### 3.3 Behavior Verification

#### 3.3.1 PnL Calculation (Manual Test)

```python
# Quick manual test
from decimal import Decimal
from core.position_manager import PositionState

p = PositionState(
    id=1, symbol="TEST", exchange="bybit", side="long",
    quantity=Decimal('1.0'),
    entry_price=Decimal('100.00'),
    current_price=Decimal('102.00'),
    unrealized_pnl=Decimal('2.00'),
    unrealized_pnl_percent=2.0,  # Calculated: (102-100)/100*100 = 2.0%
    stop_loss_price=None, opened_at=None, age_hours=0
)

# Verify Decimal arithmetic works
pnl = p.current_price - p.entry_price
assert pnl == Decimal('2.00'), f"Expected 2.00, got {pnl}"
print(f"✅ PnL calculation: {pnl}")
```

---

#### 3.3.2 Database Round-Trip (Manual Test)

**If you have test database access**:

```python
# Full round-trip test
import asyncio
from decimal import Decimal
from database.repository import Repository

async def test_db_roundtrip():
    repo = Repository()
    await repo.connect()

    # Save position with precise Decimal
    position_id = await repo.create_position(
        symbol="TESTUSDT",
        exchange="bybit",
        side="long",
        quantity=Decimal('1.23456789'),
        entry_price=Decimal('50123.45678901'),
        # ... other fields
    )

    # Load position
    position = await repo.get_position(position_id)

    # Verify precision preserved
    assert str(position['entry_price']) == '50123.45678901', "Precision lost!"
    assert str(position['quantity']) == '1.23456789', "Precision lost!"

    print(f"✅ Database round-trip: precision preserved")

    # Cleanup
    await repo.close_position(position_id)

asyncio.run(test_db_roundtrip())
```

---

## ✅ FINAL VERIFICATION CHECKLIST

### Before declaring Phase 1 COMPLETE:

#### Level 1: Syntax ✓
- [ ] Python syntax check PASSED
- [ ] Import check PASSED
- [ ] MyPy error count DECREASED (55 → ~35-40)
- [ ] Decimal import present
- [ ] Dataclass definition correct

#### Level 2: Tests ✓
- [ ] All existing tests PASS (100%)
- [ ] Position manager tests PASS
- [ ] Database integration tests PASS
- [ ] Precision preservation test PASSED
- [ ] Float conversion test PASSED

#### Level 3: Manual ✓
- [ ] Dataclass definition reviewed (lines 135-165)
- [ ] All 6 creation sites reviewed
- [ ] Event logging float() verified CORRECT
- [ ] Stop Loss API float() verified REQUIRED
- [ ] Trailing Stop API float() verified REQUIRED
- [ ] Database updates verified NO float()
- [ ] PnL calculation manually tested
- [ ] Database round-trip manually tested (if possible)

---

## 🚨 ROLLBACK PROCEDURE

**If ANY test fails**:

### Immediate Rollback:

```bash
# Restore backup
cp core/position_manager.py.BACKUP_* core/position_manager.py

# Verify restoration
git diff core/position_manager.py  # Should show changes reverted

# Run tests
pytest tests/ -v  # Should pass
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
   - Precision loss? (Level 2 or 3)

3. **Fix in DETAILED_PLAN.md**:
   - Update plan with correction
   - Re-review all changes
   - Re-execute testing plan

**DO NOT PROCEED** until all tests pass!

---

## 📊 SUCCESS CRITERIA

### Phase 1 is COMPLETE when:

1. ✅ **All Level 1 tests PASS** (syntax, types, imports)
2. ✅ **All Level 2 tests PASS** (unit, integration, precision)
3. ✅ **All Level 3 verifications COMPLETE** (manual review)
4. ✅ **Zero new bugs introduced**
5. ✅ **Zero precision loss in database operations**
6. ✅ **All external API calls properly converted to float**
7. ✅ **MyPy error count decreased** (not increased)

### Ready for:
- ✅ Git commit with detailed message
- ✅ Code review (if team)
- ✅ Merge to development branch
- ✅ Begin Phase 2 planning (TrailingStopManager)

---

## 📝 EXECUTION LOG TEMPLATE

**Use this to document your testing session**:

```markdown
# Phase 1 Execution Log

**Date**: 2025-10-31
**Executor**: [Your Name]
**Start Time**: [HH:MM]

## Changes Made:
- [ ] Dataclass definition updated (lines 135-165)
- [ ] Creation site 1 updated (line 414)
- [ ] Creation site 2 updated (line 810)
- [ ] Creation site 3 updated (line XXX)
- [ ] Creation site 4 updated (line XXX)
- [ ] Creation site 5 updated (line XXX)
- [ ] Creation site 6 updated (line 1701)

## Level 1 Results:
- Syntax check: ✅ PASS / ❌ FAIL - [details]
- Import check: ✅ PASS / ❌ FAIL - [details]
- MyPy before: 55 errors
- MyPy after: XX errors (decreased: YES/NO)
- Decimal import: ✅ PRESENT / ❌ MISSING

## Level 2 Results:
- All tests: ✅ XX/XX PASS / ❌ XX/XX FAIL
- Position manager tests: ✅ PASS / ❌ FAIL
- Database tests: ✅ PASS / ❌ FAIL
- Precision test: ✅ PASS / ❌ FAIL - [precision: X.XXXXXXXX]
- Float conversion test: ✅ PASS / ❌ FAIL

## Level 3 Results:
- Dataclass review: ✅ COMPLETE
- Creation sites review: ✅ COMPLETE (6/6)
- float() conversions review: ✅ COMPLETE
- Database updates review: ✅ SAFE (no float() before DB)
- Manual PnL test: ✅ PASS / ❌ FAIL
- Manual DB round-trip: ✅ PASS / ❌ FAIL / ⏭️ SKIPPED

## Issues Found:
[List any issues or notes]

## Final Decision:
- [ ] ✅ Phase 1 COMPLETE - Ready to commit
- [ ] ❌ Phase 1 INCOMPLETE - Rollback and fix
- [ ] ⏸️ Phase 1 PAUSED - Need clarification

**End Time**: [HH:MM]
**Duration**: [XX minutes]
```

---

**Generated**: 2025-10-31
**Next Step**: Execute Phase 1 changes (after user approval)
**Required**: User approval to begin code changes
