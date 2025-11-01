# PHASE 4 - QUICK REFERENCE GUIDE

**Date**: 2025-10-31
**Status**: PLANNING COMPLETE - READY FOR EXECUTION
**Full Details**: See PHASE4_COMPREHENSIVE_DETAILED_PLAN.md

---

## 📊 AT A GLANCE

**Total Errors**: 114 Decimal/float type errors
**Total Files**: 11 files
**Total Time**: 8-12 hours (split over 2-3 days)
**Phases**: 4 (4A-Critical, 4B-Exchange, 4C-Monitoring, 4D-Utilities)

---

## 🎯 QUICK FILE INDEX

| File | Errors | Priority | Time | Phase |
|------|--------|----------|------|-------|
| core/position_manager.py | 35 | 🔴 CRITICAL | 2h | 4A |
| protection/trailing_stop.py | 19 | 🔴 CRITICAL | 1h | 4A |
| database/repository.py | 16 | 🔴 CRITICAL | 1h | 4A |
| core/exchange_manager.py | 12 | 🟡 HIGH | 1.5h | 4B |
| monitoring/performance.py | 11 | 🟡 MEDIUM | 2h | 4C |
| utils/decimal_utils.py | 4 | 🔴 CRITICAL | 5min | 4A |
| core/aged_position_manager.py | 3 | 🟡 HIGH | 30min | 4B |
| websocket/signal_adapter.py | 3 | 🟢 LOW | 15min | 4D |
| core/risk_manager.py | 2 | 🟢 LOW | 15min | 4D |
| core/zombie_manager.py | 1 | 🟢 LOW | 15min | 4D |
| core/protection_adapters.py | 1 | 🟢 LOW | 15min | 4D |

---

## 🔥 MOST CRITICAL FIXES (DO THESE FIRST)

### 1. utils/decimal_utils.py (5 minutes)

**Line 32**: Add `None` to Union type
```python
# BEFORE
def to_decimal(value: Union[str, int, float, Decimal], precision: int = 8) -> Decimal:

# AFTER
def to_decimal(value: Union[str, int, float, Decimal, None], precision: int = 8) -> Decimal:
```

**Impact**: Fixes 4 errors across codebase automatically

---

### 2. database/repository.py (45 minutes)

**Lines 546-550**: Add `Optional[]` to all None-default parameters
```python
# BEFORE
async def close_position(self, position_id: int,
                        close_price: float = None,
                        pnl: float = None,
                        pnl_percentage: float = None,
                        reason: str = None,
                        exit_data: Dict = None):

# AFTER
async def close_position(self, position_id: int,
                        close_price: Optional[float] = None,
                        pnl: Optional[float] = None,
                        pnl_percentage: Optional[float] = None,
                        reason: Optional[str] = None,
                        exit_data: Optional[Dict[Any, Any]] = None):
```

**Lines 1331, 1337, 1343**: Convert to string before appending
```python
# BEFORE
params.append(target_price)  # Decimal
params.append(hours_aged)    # float

# AFTER
params.append(str(target_price))
params.append(str(hours_aged))
```

**Impact**: Fixes 9 errors

---

### 3. core/position_manager.py (2 hours 15 minutes)

**Pattern A: Repository calls** (Lines 774-775, 2639-2641)
```python
# BEFORE
await self.repository.close_position(
    pos_state.id,
    pos_state.current_price or 0.0,  # Decimal
    pos_state.unrealized_pnl or 0.0  # Decimal
)

# AFTER
await self.repository.close_position(
    pos_state.id,
    float(pos_state.current_price) if pos_state.current_price else 0.0,
    float(pos_state.unrealized_pnl) if pos_state.unrealized_pnl else 0.0
)
```

**Pattern B: Variable declarations** (Lines 1171, 1179, 1501, 1509, etc.)
```python
# BEFORE
stop_loss_percent: float = request.stop_loss_percent  # Returns Decimal

# AFTER
stop_loss_percent: Decimal = to_decimal(request.stop_loss_percent)
```

**Pattern C: Find and fix method signatures**
```bash
# Find _set_stop_loss definition
grep -n "def _set_stop_loss" core/position_manager.py

# Change signature from float to Decimal
stop_price: float → stop_price: Decimal
```

**Impact**: Fixes 35 errors

---

### 4. protection/trailing_stop.py (1 hour 25 minutes)

**Pattern A: None checks before comparisons** (Lines 710, 712, 801, 813)
```python
# BEFORE
if ts.current_price >= ts.activation_price:  # activation_price: Decimal | None

# AFTER
if ts.activation_price is not None and ts.current_price >= ts.activation_price:
```

**Pattern B: None checks before float()** (Lines 847, 896, 931, etc.)
```python
# BEFORE
logger.info(f"Peak: {float(peak_price)}")  # peak_price: Decimal | None

# AFTER
logger.info(f"Peak: {float(peak_price) if peak_price is not None else 0.0}")
```

**Pattern C: None checks before arithmetic** (Line 911)
```python
# BEFORE
distance = (current_price - peak_price) / peak_price * 100

# AFTER
if peak_price is not None and peak_price > 0:
    distance = (current_price - peak_price) / peak_price * 100
else:
    distance = Decimal('0')
```

**Impact**: Fixes 19 errors

---

## ⚡ QUICK COMMANDS

### Before Starting
```bash
# Backup everything
git checkout -b backup/phase4-$(date +%Y%m%d-%H%M%S)
git tag phase4-start-$(date +%Y%m%d-%H%M%S)

# Count current errors
mypy . --no-error-summary 2>&1 | grep -E "(Decimal|float)" | wc -l
# Expected: 114

# Save baseline
mypy . --no-error-summary 2>&1 | grep -E "(Decimal|float)" > /tmp/mypy_phase4_before.txt
```

### After Each File
```bash
# Check progress
mypy <file> --no-error-summary 2>&1 | grep -E "(Decimal|float)"

# Commit immediately
git add <file>
git commit -m "Phase 4X: Fix <file> Decimal/float types - Y errors fixed"
```

### After Each Phase
```bash
# Full MyPy check
mypy . --no-error-summary 2>&1 | grep -E "(Decimal|float)" | wc -l

# Run tests
pytest tests/test_phase4_decimal_migration.py -v
```

### Rollback if Needed
```bash
# Rollback one file
git checkout HEAD -- <file>

# Rollback entire phase
git reset --hard phase4-start-<timestamp>
```

---

## 📋 EXECUTION CHECKLIST

### Phase 4A: Critical Core (4 hours)
```
[ ] File 1: utils/decimal_utils.py (5 min)
    [ ] Line 32: Add None to Union type
    [ ] Test: to_decimal(None) == Decimal('0')
    [ ] Commit

[ ] File 2: database/repository.py (1 hour)
    [ ] Lines 546-550: Add Optional[] to close_position
    [ ] Lines 1295-1297: Add Optional[] to aged_params
    [ ] Lines 1375-1377: Add Optional[] to filter_params
    [ ] Line 1198: Add Optional[] to risk_params
    [ ] Lines 1331, 1337, 1343: str() conversions
    [ ] Lines 225, 231, 237: Fix list appends (review needed)
    [ ] Test: MyPy shows 0 errors in repository.py
    [ ] Commit

[ ] File 3: core/position_manager.py (2h 15min)
    [ ] Lines 774-775: Add float() conversions
    [ ] Lines 2639-2641: Add float() conversions
    [ ] Line 1542: Add float() conversion
    [ ] Find _set_stop_loss definition → change to Decimal
    [ ] Find _calculate_position_size → change to Decimal
    [ ] Lines 1171, 1179, etc.: Change variable types
    [ ] Lines 1970, 2025, 2026: Fix mixed arithmetic
    [ ] Line 2064: Change return type
    [ ] Test: MyPy shows 0 errors in position_manager.py
    [ ] Commit

[ ] File 4: protection/trailing_stop.py (1h 25min)
    [ ] Lines 710, 712, 801, 813, 1289, 1299: Add None checks
    [ ] Lines 847, 896, 931, 950, 1015, 1331, 1359, 1373: Add None checks
    [ ] Line 911: Add None check for arithmetic
    [ ] Line 825: Check before calling or change signature
    [ ] Lines 975, 1470: Fix mixed arithmetic
    [ ] Test: MyPy shows 0 errors in trailing_stop.py
    [ ] Commit

[ ] Testing Phase 4A
    [ ] MyPy: 114 → ≤44 errors (70 fixed)
    [ ] pytest tests/test_phase4_decimal_migration.py::TestPhase4ACore -v
    [ ] Tag: git tag phase4a-complete
```

### Phase 4B: Exchange Integration (2 hours)
```
[ ] File 5: core/exchange_manager.py (1.5h)
    [ ] Lines 414, 1562: Add Optional[] to signatures
    [ ] Lines 480, 640: Add to_decimal() conversions
    [ ] Lines 1006, 1050: Add int() conversions
    [ ] Line 1337: Add to_decimal() for OrderResult
    [ ] Lines 826, 833, 858, 1082, 1083: Fix dict values (review needed)
    [ ] Test: MyPy shows 0 errors in exchange_manager.py
    [ ] Commit

[ ] File 6: core/aged_position_manager.py (30min)
    [ ] Lines 437, 494, 517: Change return type to Decimal
    [ ] Check callers and update
    [ ] Test: MyPy shows 0 errors in aged_position_manager.py
    [ ] Commit

[ ] Testing Phase 4B
    [ ] MyPy: 44 → ≤29 errors (15 fixed)
    [ ] pytest tests/test_phase4_decimal_migration.py::TestPhase4BExchange -v
    [ ] Tag: git tag phase4b-complete
```

### Phase 4C: Monitoring (2 hours)
```
[ ] File 7: monitoring/performance.py (2h)
    [ ] Lines 504-513: Add Decimal(str()) conversions for SQLAlchemy
    [ ] Line 343: Add Decimal(str()) conversion
    [ ] Line 344: Fix data.append types
    [ ] Line 533: Convert metrics list
    [ ] Line 595: Add Decimal(str()) conversion
    [ ] Test: MyPy shows 0 errors in performance.py
    [ ] Commit

[ ] Testing Phase 4C
    [ ] MyPy: 29 → ≤18 errors (11 fixed)
    [ ] pytest tests/test_phase4_decimal_migration.py::TestPhase4CMonitoring -v
    [ ] Tag: git tag phase4c-complete
```

### Phase 4D: Utilities (1 hour)
```
[ ] File 8: websocket/signal_adapter.py (15min)
    [ ] Lines 199, 202, 205: Add int() conversions
    [ ] Commit

[ ] File 9: core/risk_manager.py (15min)
    [ ] Lines 142, 151: Add int() conversions
    [ ] Commit

[ ] File 10: core/zombie_manager.py (15min)
    [ ] Line 725: Fix type annotation (review needed)
    [ ] Commit

[ ] File 11: core/protection_adapters.py (15min)
    [ ] Line 172: Add int() conversion
    [ ] Commit

[ ] Testing Phase 4D
    [ ] MyPy: 18 → 0 errors (all fixed)
    [ ] pytest tests/test_phase4_decimal_migration.py::TestPhase4DUtilities -v
    [ ] Tag: git tag phase4d-complete
```

### Final Validation
```
[ ] MyPy full check
    [ ] mypy . --no-error-summary 2>&1 | grep -E "(Decimal|float)" | wc -l
    [ ] Expected: 0 errors

[ ] Integration tests
    [ ] pytest tests/integration/test_decimal_migration.py -v
    [ ] All tests pass

[ ] Documentation
    [ ] Update DECIMAL_MIGRATION.md
    [ ] Create PHASE4_SUMMARY.md
    [ ] Update developer guidelines

[ ] Git cleanup
    [ ] git tag phase4-complete
    [ ] Create PR or merge to main
```

---

## 🚨 COMMON PITFALLS

### ❌ DON'T
```python
# Don't assign Decimal to float variable
price: float = Decimal('50000.12345678')  # ❌ Type error

# Don't compare Decimal | None without check
if peak_price > current_price:  # ❌ peak_price might be None

# Don't call float() on None
logger.info(f"Price: {float(peak_price)}")  # ❌ If peak_price is None
```

### ✅ DO
```python
# Do use correct type annotation
price: Decimal = Decimal('50000.12345678')  # ✅

# Do check None before comparison
if peak_price is not None and peak_price > current_price:  # ✅

# Do check None before float()
logger.info(f"Price: {float(peak_price) if peak_price is not None else 0.0}")  # ✅

# Do convert Decimal to float at boundaries
await repository.close_position(
    close_price=float(decimal_price)  # ✅ Repository boundary
)
```

---

## 🎯 SUCCESS METRICS

| Phase | Before | After | Fixed | Time |
|-------|--------|-------|-------|------|
| 4A | 114 | 44 | 70 | 4h |
| 4B | 44 | 29 | 15 | 2h |
| 4C | 29 | 18 | 11 | 2h |
| 4D | 18 | 0 | 18 | 1h |
| **Total** | **114** | **0** | **114** | **9h** |

---

## 📞 HELP COMMANDS

### Find Error Details
```bash
# Get specific error context
mypy <file> --show-error-codes --show-column-numbers

# Get all errors for one file
mypy <file> --no-error-summary 2>&1

# Count remaining errors
mypy . --no-error-summary 2>&1 | grep -E "(Decimal|float)" | wc -l
```

### Find Method Definitions
```bash
# Find method signature
grep -n "def _set_stop_loss" core/position_manager.py

# Find all calls to method
grep -n "_set_stop_loss" core/position_manager.py

# Find variable usage
grep -n "stop_loss_percent" core/position_manager.py
```

### Quick Type Fixes
```bash
# Find all "float =" assignments that should be Decimal
grep -n ": float =" core/position_manager.py

# Find all "= None" parameters
grep -n "= None" database/repository.py
```

---

## 📚 REFERENCES

- **Full Plan**: audit/PHASE4_COMPREHENSIVE_DETAILED_PLAN.md
- **MyPy Report**: /tmp/mypy_type_errors.txt
- **Gap Analysis**: audit/MYPY_DECIMAL_MIGRATION_GAPS.md
- **Phase 3 Example**: audit/MIGRATION_PHASE3_DETAILED_PLAN.md

---

**Last Updated**: 2025-10-31
**Status**: ✅ READY FOR EXECUTION
**Next Step**: Get approval, then start Phase 4A
