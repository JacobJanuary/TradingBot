# PHASE 3 TESTING PLAN - 3-Level Verification Strategy

**Date**: 2025-10-31
**Target**: core/stop_loss_manager.py + core/position_manager.py
**Strategy**: Same proven 3-level approach from Phase 2
**Total Time**: ~45-57 minutes

---

## 📋 TESTING PHILOSOPHY

Following Phase 1+2 success, we use the same rigorous 3-level verification:

1. **Level 1: Automated** - Syntax, imports, type checking (fast, catches 80% of issues)
2. **Level 2: Manual Code Review** - Line-by-line verification (thorough, catches logic errors)
3. **Level 3: Documentation Cross-Check** - Ensure plan followed exactly (compliance)

**GOLDEN RULE**: All 3 levels must PASS before git commit!

---

## 🎯 SUCCESS CRITERIA

Phase 3 is **SUCCESSFUL** when:

- [ ] **Level 1**: All automated tests PASS
  - [ ] Python syntax valid (2 files)
  - [ ] Imports work
  - [ ] MyPy errors decreased (-10 to -15 expected)

- [ ] **Level 2**: Manual review COMPLETE
  - [ ] All 17 changes verified
  - [ ] No Decimal(str(stop_price)) at changed lines
  - [ ] float() only before exchange API
  - [ ] Integration with Phase 1 verified

- [ ] **Level 3**: Documentation check PASS
  - [ ] All changes match DETAILED_PLAN.md
  - [ ] No logic changes (GOLDEN RULE)
  - [ ] Execution log complete

**If ANY level fails**: Stop, fix issues, re-run ALL levels from Level 1

---

## 📊 LEVEL 1: SYNTAX & TYPE CHECKING (5-7 minutes)

### Objective
Catch syntax errors, import issues, and type mismatches automatically.

### Tests

#### Test 1.1: Python Syntax Validation (~1 min)

**Command**:
```bash
python3 -m py_compile /path/to/core/stop_loss_manager.py
python3 -m py_compile /path/to/core/position_manager.py
```

**Expected**: No output (success)

**If Fails**:
- Check for typos in changes
- Verify quote matching
- Check indentation (Python sensitive)

---

#### Test 1.2: Import Verification (~1 min)

**Command**:
```bash
python3 -c "from core.stop_loss_manager import StopLossManager; from core.position_manager import PositionManager; print('✓ Imports successful')"
```

**Expected**: `✓ Imports successful`

**If Fails**:
- Check for missing imports (e.g., `from decimal import Decimal`)
- Verify `to_decimal` helper is imported
- Check circular import issues

---

#### Test 1.3: MyPy Type Checking (~3-4 min)

**Command**:
```bash
python3 -m mypy /path/to/core/stop_loss_manager.py /path/to/core/position_manager.py --show-error-codes 2>&1 | tee mypy_phase3.log
```

**Baseline (before Phase 3)**: 276 errors (after Phase 2)

**Expected (after Phase 3)**: 260-266 errors (-10 to -16 improvement)

**Success Criteria**:
- Total errors decreased ✅
- No NEW errors in modified files ✅
- Errors resolved:
  - "Decimal passed to float parameter" warnings (-8 to -12)
  - "Incompatible default" warnings (-2 to -4)

**Error Count**:
```bash
# Count total errors:
python3 -m mypy /path/to/core/stop_loss_manager.py /path/to/core/position_manager.py 2>&1 | grep "Found .* error"
```

**If Fails**:
- Review error messages for new issues
- Check method signature consistency
- Verify Optional[Decimal] used correctly
- Check tolerance_percent type (should be Decimal)

---

#### Test 1.4: Decimal Usage Verification (~1 min)

**Check 1**: No Decimal(str(stop_price)) at changed lines
```bash
grep -n "Decimal(str(stop_price))" core/stop_loss_manager.py
# Expected: No matches (or not at line 462)
```

**Check 2**: No Decimal(str(amount)) conversions
```bash
grep -n "Decimal(str(amount))" core/stop_loss_manager.py
# Expected: No matches
```

**Check 3**: No explicit float(position.quantity) at call sites
```bash
grep -n "float(position.quantity)" core/position_manager.py
# Expected: No match at line 2142 (should be removed)
# May still appear elsewhere (OK if not in our call sites)
```

**Check 4**: Verify method signatures use Decimal
```bash
grep -A 3 "async def set_stop_loss" core/stop_loss_manager.py | grep "amount:"
# Expected: "amount: Decimal,"
```

---

### Level 1 Completion

**Time Taken**: _______ minutes (target: 5-7)

**Results**:
- [ ] Test 1.1 PASS (Python syntax)
- [ ] Test 1.2 PASS (Imports)
- [ ] Test 1.3 PASS (MyPy)
- [ ] Test 1.4 PASS (Decimal usage)

**MyPy Error Count**:
- Before Phase 3: 276 errors
- After Phase 3: ______ errors
- Improvement: ______ errors (target: -10 to -16)

**If ANY test fails**: Fix issues before proceeding to Level 2

---

## 🔍 LEVEL 2: MANUAL CODE REVIEW (30-40 minutes)

### Objective
Line-by-line verification that all changes are correct and follow GOLDEN RULE.

### Review Checklist

#### Section 1: Method Signatures (5 min)

**Verify each method signature changed correctly**:

- [ ] **set_stop_loss (line 161-162)**
  ```python
  amount: Decimal,    # ✅ Was float
  stop_price: Decimal # ✅ Was float
  ```

- [ ] **verify_and_fix_missing_sl (line 232)**
  ```python
  stop_price: Decimal # ✅ Was float
  ```

- [ ] **_set_bybit_stop_loss (line 327)**
  ```python
  stop_price: Decimal # ✅ Was float
  ```

- [ ] **_set_generic_stop_loss (line 447-448)**
  ```python
  amount: Decimal,    # ✅ Was float
  stop_price: Decimal # ✅ Was float
  ```

- [ ] **_validate_existing_sl (line 717-720)**
  ```python
  existing_sl_price: Decimal,      # ✅ Was float
  target_sl_price: Decimal,        # ✅ Was float
  tolerance_percent: Decimal = Decimal("5.0")  # ✅ Was float
  ```

- [ ] **_cancel_existing_sl (line 800)**
  ```python
  sl_price: Decimal  # ✅ Was float
  ```

- [ ] **set_stop_loss_unified (line 866-867)**
  ```python
  amount: Decimal,    # ✅ Was float
  stop_price: Decimal # ✅ Was float
  ```

**Total**: 7 method signatures ✅

---

#### Section 2: Internal Conversions Removed (5 min)

**Verify Decimal(str(...)) removed**:

- [ ] **Line 462** (stop_loss_manager.py)
  ```python
  # BEFORE: stop_price_decimal = Decimal(str(stop_price))
  # AFTER:  stop_price_decimal = stop_price
  ```

- [ ] **Line 471-475** (stop_loss_manager.py)
  ```python
  # BEFORE: current_price = Decimal(str(ticker.get(...)))
  # AFTER:  current_price = to_decimal(ticker.get(...))
  ```

**Total**: 2 conversions removed ✅

---

#### Section 3: Call Sites Fixed (10 min)

**Verify call site changes**:

- [ ] **Call Site 1: position_manager.py line 2142-2143**
  ```python
  # BEFORE:
  amount=float(position.quantity),
  stop_price=stop_price

  # AFTER:
  amount=position.quantity,
  stop_price=to_decimal(stop_price)
  ```
  - Check: position is PositionState ✅
  - Check: to_decimal imported ✅

- [ ] **Call Site 2: position_manager.py line 3358**
  ```python
  # NO CHANGE (already correct):
  stop_price=stop_loss_price  # Already Decimal
  ```
  - Verify: stop_loss_price comes from calculate_stop_loss() (Decimal) ✅

- [ ] **Internal Call Site: stop_loss_manager.py line 284**
  ```python
  # BEFORE:
  amount=float(position.quantity),

  # AFTER:
  amount=to_decimal(position.quantity),
  ```
  - Check: Handles both Position (Float) and PositionState (Decimal) ✅

**Total**: 3 call sites (2 changes, 1 verification) ✅

---

#### Section 4: Float Conversions Preserved (5 min)

**Verify float() kept for exchange API boundary**:

- [ ] **Line 374** (stop_loss_manager.py)
  ```python
  'stop_price': float(sl_price_formatted),  # ✅ Event logger
  ```

- [ ] **Line 385** (stop_loss_manager.py)
  ```python
  'stopPrice': float(sl_price_formatted),  # ✅ Bybit API
  ```

- [ ] **Line 396** (stop_loss_manager.py)
  ```python
  'stopPrice': float(sl_price_formatted),  # ✅ Bybit API
  ```

- [ ] **Line 411** (stop_loss_manager.py)
  ```python
  'stop_price': float(sl_price_formatted),  # ✅ Event logger
  ```

- [ ] **Line 508** (stop_loss_manager.py)
  ```python
  final_stop_price = float(stop_price_decimal)  # ✅ Before precision call
  ```

- [ ] **Line 546, 558** (stop_loss_manager.py)
  ```python
  'stop_price': float(final_stop_price),  # ✅ Event logger
  'stopPrice': float(final_stop_price),   # ✅ Create order
  ```

**Verification**: float() appears ONLY before:
- exchange.create_order() ✅
- exchange.price_to_precision() ✅
- event_logger.log_event() ✅

**Total**: 7 float() calls preserved correctly ✅

---

#### Section 5: Additional Changes (5 min)

- [ ] **Line 188-189** (stop_loss_manager.py)
  ```python
  # BEFORE:
  existing_sl_price=float(existing_sl),
  target_sl_price=float(stop_price),

  # AFTER:
  existing_sl_price=to_decimal(existing_sl),
  target_sl_price=stop_price,  # Already Decimal
  ```

- [ ] **Line 214** (stop_loss_manager.py)
  ```python
  # BEFORE:
  await self._cancel_existing_sl(symbol, float(existing_sl))

  # AFTER:
  await self._cancel_existing_sl(symbol, to_decimal(existing_sl))
  ```

- [ ] **Line 749** (stop_loss_manager.py)
  ```python
  # BEFORE:
  diff_pct = abs(existing_sl_price - target_sl_price) / target_sl_price * 100

  # AFTER:
  diff_pct = abs(existing_sl_price - target_sl_price) / target_sl_price * Decimal("100")
  ```

- [ ] **Line 826** (stop_loss_manager.py)
  ```python
  # BEFORE:
  price_diff = abs(float(order_stop_price) - float(sl_price)) / float(sl_price)

  # AFTER:
  price_diff = abs(to_decimal(order_stop_price) - sl_price) / sl_price
  ```

**Total**: 4 additional changes ✅

---

### Level 2 Completion

**Time Taken**: _______ minutes (target: 30-40)

**Results**:
- [ ] Section 1 COMPLETE (7 method signatures)
- [ ] Section 2 COMPLETE (2 conversions removed)
- [ ] Section 3 COMPLETE (3 call sites)
- [ ] Section 4 COMPLETE (7 float() preserved)
- [ ] Section 5 COMPLETE (4 additional changes)

**Total Changes Verified**: 17 / 17 ✅

**GOLDEN RULE Check**:
- [ ] NO logic changes (only types)
- [ ] NO refactoring
- [ ] NO optimizations
- [ ] NO new features

**If ANY issue found**: Document in execution log, fix, re-run Level 1

---

## 📝 LEVEL 3: DOCUMENTATION CROSS-CHECK (10 minutes)

### Objective
Ensure execution matches plan exactly, nothing forgotten.

### Verification

#### Check 1: All Planned Changes Made (5 min)

**Compare against MIGRATION_PHASE3_DETAILED_PLAN.md**:

- [ ] Change 1: set_stop_loss signature ✅
- [ ] Change 2: Remove float() in set_stop_loss ✅
- [ ] Change 3: verify_and_fix_missing_sl signature ✅
- [ ] Change 4: Remove float() in verify_and_fix_missing_sl ✅
- [ ] Change 5: _set_bybit_stop_loss signature ✅
- [ ] Change 6: Keep float() for exchange API (verified) ✅
- [ ] Change 7: _set_generic_stop_loss signature ✅
- [ ] Change 8: Remove Decimal(str(stop_price)) ✅
- [ ] Change 9: Use to_decimal() for ticker data ✅
- [ ] Change 10: Keep float() for exchange API (verified) ✅
- [ ] Change 11: _validate_existing_sl signature ✅
- [ ] Change 12: Update calculation ✅
- [ ] Change 13: _cancel_existing_sl signature ✅
- [ ] Change 14: Update float() conversion ✅
- [ ] Change 15: set_stop_loss_unified signature ✅
- [ ] Change 16: Remove float() at call site 1 ✅
- [ ] Change 17: Verify call site 2 (no change needed) ✅

**Total**: 17 / 17 changes accounted for ✅

---

#### Check 2: No Extra Changes (2 min)

**Verify ONLY planned changes made**:

```bash
# Show all changes:
git diff core/stop_loss_manager.py core/position_manager.py | grep "^[\+\-]" | grep -v "^[\+\-][\+\-][\+\-]"
```

**Review each line**:
- [ ] All changes are in DETAILED_PLAN? ✅
- [ ] No surprise refactoring? ✅
- [ ] No logic changes? ✅

---

#### Check 3: Integration Verification (3 min)

**Phase 1 Integration**:
- [ ] PositionState.quantity used as Decimal ✅
- [ ] No float() wrapping PositionState fields ✅

**Phase 2 Integration**:
- [ ] StopLossManager follows same pattern as TrailingStopManager ✅
- [ ] float() only at boundaries ✅

**Database Boundary**:
- [ ] Understand database will write Float (documented) ✅
- [ ] float() before repository.update_position() (if any) ✅

---

### Level 3 Completion

**Time Taken**: _______ minutes (target: 10)

**Results**:
- [ ] Check 1 PASS (All planned changes made)
- [ ] Check 2 PASS (No extra changes)
- [ ] Check 3 PASS (Integration verified)

---

## 📊 OVERALL TEST SUMMARY

### Execution Time

| Level | Target Time | Actual Time | Status |
|-------|-------------|-------------|--------|
| Level 1 | 5-7 min | _______ min | [ ] PASS |
| Level 2 | 30-40 min | _______ min | [ ] PASS |
| Level 3 | 10 min | _______ min | [ ] PASS |
| **Total** | **45-57 min** | **_______ min** | **[ ] PASS** |

---

### Test Results

**Level 1 - Automated**:
- Python Syntax: [ ] PASS / [ ] FAIL
- Imports: [ ] PASS / [ ] FAIL
- MyPy: [ ] PASS / [ ] FAIL (Errors: Before _____, After _____)
- Decimal Usage: [ ] PASS / [ ] FAIL

**Level 2 - Manual Review**:
- Method Signatures (7): [ ] COMPLETE
- Internal Conversions (2): [ ] COMPLETE
- Call Sites (3): [ ] COMPLETE
- Float Preserved (7): [ ] COMPLETE
- Additional Changes (4): [ ] COMPLETE
- GOLDEN RULE: [ ] FOLLOWED

**Level 3 - Documentation**:
- All Changes Made (17): [ ] VERIFIED
- No Extra Changes: [ ] VERIFIED
- Integration: [ ] VERIFIED

---

## ✅ FINAL CHECKLIST

Before creating git commit:

- [ ] **All 3 levels PASSED**
- [ ] **MyPy errors decreased** (target: -10 to -15)
- [ ] **No new issues introduced**
- [ ] **GOLDEN RULE followed** (no refactoring)
- [ ] **Backup created** (stop_loss_manager.py.BACKUP_PHASE3_[timestamp])
- [ ] **Execution log updated**

**If ALL checks PASS**: ✅ **PROCEED TO GIT COMMIT**

**If ANY check FAILS**: ❌ **FIX ISSUES, RE-RUN ALL LEVELS**

---

## 🔧 TROUBLESHOOTING

### Common Issues

**Issue 1: MyPy shows NEW errors**
```
Cause: Method signature inconsistency
Fix: Check all methods that call changed methods
     Verify Optional[Decimal] vs Decimal usage
```

**Issue 2: Import errors**
```
Cause: Missing to_decimal import
Fix: Add to imports: from utils.position_helpers import to_decimal
```

**Issue 3: Type mismatch in calculations**
```
Cause: Mixed Decimal and float in arithmetic
Fix: Ensure all operands are Decimal: Decimal("100") not 100
```

**Issue 4: Exchange API errors**
```
Cause: Passing Decimal to CCXT
Fix: Verify float() before all exchange.* calls
```

---

## 📝 EXECUTION LOG TEMPLATE

```markdown
# PHASE 3 EXECUTION LOG

## Pre-Execution
- Backup created: stop_loss_manager.py.BACKUP_PHASE3_[timestamp]
- Git branch: feature/decimal-migration-phase1
- Start time: [HH:MM]

## Level 1 Tests
- Syntax: PASS/FAIL
- Imports: PASS/FAIL
- MyPy: PASS/FAIL (Before: 276, After: ___)
- Decimal usage: PASS/FAIL

## Level 2 Review
- Method signatures: COMPLETE / INCOMPLETE
- Conversions: COMPLETE / INCOMPLETE
- Call sites: COMPLETE / INCOMPLETE
- GOLDEN RULE: FOLLOWED / VIOLATED

## Level 3 Verification
- All changes: VERIFIED / MISSING
- No extras: VERIFIED / FOUND
- Integration: VERIFIED / ISSUES

## Final Result
- Status: SUCCESS / FAILED
- Total time: ___ minutes
- Commit: [hash] / NOT CREATED

## Issues Encountered
[List any issues and how they were resolved]
```

---

**Generated**: 2025-10-31
**Status**: ✅ COMPLETE
**Testing Strategy**: 3-Level (Automated → Manual → Documentation)
**Total Time**: ~45-57 minutes
**Success Rate (Phase 1+2)**: 100% ✅

---

**NOTE**: This testing plan is based on proven methodology from Phase 1+2.
Both phases completed successfully using this exact 3-level approach!
