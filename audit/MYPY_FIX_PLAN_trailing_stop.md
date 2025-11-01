# 🔧 MyPy Fix Plan: protection/trailing_stop.py

**File**: `protection/trailing_stop.py`
**Total Errors**: 43
**Date**: 2025-10-31
**Priority**: 🔴 HIGH (third most errors)

---

## 📊 Error Classification

| Category | Count | Real/False | Priority |
|----------|-------|------------|----------|
| **`Decimal \| None` operations** | 25 | **REAL - MISSING None CHECKS** | CRITICAL |
| **Incompatible defaults (Optional)** | 2 | **REAL** | HIGH |
| **Need type annotation** | 1 | **REAL** | MEDIUM |
| **`Decimal` / `float` operations** | 8 | **REAL - TYPE MISMATCH** | HIGH |
| **`object + int`** | 2 | **REAL - MISSING TYPE HINT** | MEDIUM |
| **Other** | 5 | **REAL** | MEDIUM |

---

## 🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА: Operations with `Decimal | None` (25 ошибок)

### Root Cause:
**Код выполняет арифметические операции и сравнения с `Decimal | None` БЕЗ проверки на None!**

### Примеры:

```python
# Line 710:
if some_decimal_value >= None:  # ❌ Can't compare Decimal with None!

# Line 712:
if some_decimal_value <= None:  # ❌

# Line 801:
if price > None:  # ❌

# Line 911:
result = some_value / None  # ❌ Division by None!
result = some_value - None  # ❌ Subtraction with None!

# Line 975:
result = some_decimal / some_float  # ❌ Decimal / float unsupported

# Lines 847, 896, 931, 950, 1015:
float(some_decimal_or_none)  # ❌ Can't convert None to float!
```

### Analysis:
**REAL BUGS** - Эти ошибки указывают на отсутствие None-проверок перед операциями.

**Impact**: Если в production попадет None - RuntimeError, падение бота!

### Fix Strategy:

#### Option 1: Add None checks (DEFENSIVE)
```python
# BEFORE (Line 710):
if current_price >= self.entry_price:
    ...

# AFTER:
if self.entry_price is not None and current_price >= self.entry_price:
    ...

# BEFORE (Line 911):
percent_distance = (current_price - self.peak_price) / self.peak_price

# AFTER:
if self.peak_price is not None and self.peak_price != 0:
    percent_distance = (current_price - self.peak_price) / self.peak_price
else:
    percent_distance = Decimal(0)

# BEFORE (Line 847):
float(self.peak_price)

# AFTER:
float(self.peak_price) if self.peak_price is not None else 0.0
```

#### Option 2: Initialize with non-None defaults (PROACTIVE)
```python
# If these values should NEVER be None, initialize them:
class TrailingStop:
    def __init__(self, ...):
        self.entry_price = entry_price  # Already not None from __init__
        self.peak_price = entry_price  # Initialize with entry, not None
        assert self.peak_price is not None, "peak_price must be set"
```

#### Option 3: Use assertions (FAIL-FAST)
```python
# At the start of methods that assume non-None:
def _update_trailing_stop(self, ...):
    assert self.entry_price is not None, "entry_price not set"
    assert self.peak_price is not None, "peak_price not set"
    # Now MyPy knows they're not None
    ...
```

### Recommended: **COMBINATION of Option 1 + 2**
1. Initialize all Decimal fields with non-None values where possible
2. Add None checks before operations where None is valid
3. Add assertions where None should never happen (programming error)

---

## ✅ CATEGORY 2: Incompatible Defaults (2 errors)

### Errors:
```
protection/trailing_stop.py:111: error: Incompatible default for argument "config" (default has type "None", argument has type "TrailingStopConfig")  [assignment]
protection/trailing_stop.py:111: error: Incompatible default for argument "exchange_name" (default has type "None", argument has type "str")  [assignment]
```

### Fix:
```python
# Line 111: BEFORE
async def some_method(self, config: TrailingStopConfig = None, exchange_name: str = None):
    ...

# AFTER:
async def some_method(self, config: Optional[TrailingStopConfig] = None, exchange_name: Optional[str] = None):
    ...
```

---

## 📋 CATEGORY 3: Need Type Annotation (1 error)

### Error:
```
protection/trailing_stop.py:133: error: Need type annotation for "sl_update_locks"  [var-annotated]
```

### Fix:
```python
# Line 133: BEFORE
sl_update_locks = {}

# AFTER:
sl_update_locks: Dict[str, asyncio.Lock] = {}
```

---

## ⚠️ CATEGORY 4: Decimal / float Operations (8 errors)

### Example (Line 975):
```
error: Unsupported operand types for / ("Decimal" and "float")
```

### Root Cause:
```python
result = some_decimal / some_float  # Decimal doesn't support direct division with float
```

### Fix:
```python
# Option A: Convert float to Decimal
result = some_decimal / Decimal(str(some_float))

# Option B: Convert Decimal to float
result = float(some_decimal) / some_float

# Option C: Ensure both are Decimal
result = some_decimal / Decimal(str(some_float))
```

**Recommended**: **Option A** (keep Decimal precision)

---

## 🔧 CATEGORY 5: object + int (2 errors)

### Errors:
```
protection/trailing_stop.py:602: error: Unsupported operand types for + ("object" and "int")  [operator]
protection/trailing_stop.py:732: error: Unsupported operand types for + ("object" and "int")  [operator]
```

### Root Cause:
MyPy inferred type as `object` because variable lacks type annotation.

### Fix:
Need to see code context, but likely:
```python
# BEFORE:
some_var = get_value()  # MyPy infers 'object'
result = some_var + 1  # Error!

# AFTER:
some_var: int = get_value()  # Explicit type
result = some_var + 1  # OK
```

---

## 📝 SUMMARY: Recommended Action Plan

### Phase 1: CRITICAL - Add None Checks (2-3 hours)

**Fix all 25 `Decimal | None` operations:**

1. ✅ Identify all fields that can be None:
   - `entry_price`, `peak_price`, `current_sl`, etc.

2. ✅ For each operation with these fields, add None check:
   ```python
   # Lines 710, 712, 801, 813, 1289, 1299:
   if field is not None and field > some_value:
       ...

   # Lines 911 (division/subtraction):
   if field is not None and field != 0:
       result = other / field

   # Lines 847, 896, 931, 950, 1015 (float conversion):
   float(field) if field is not None else 0.0
   ```

3. ✅ Add assertions where None should never happen:
   ```python
   assert self.entry_price is not None, "entry_price must be initialized"
   ```

### Phase 2: HIGH - Fix Type Issues (1 hour)

1. ✅ Add `Optional[]` to parameters (line 111) - 2 fixes
2. ✅ Add type annotation to `sl_update_locks` (line 133) - 1 fix
3. ✅ Fix `Decimal / float` operations (line 975 + 7 more) - 8 fixes
4. ✅ Add type hints for `object + int` errors (lines 602, 732) - 2 fixes

### Phase 3: TEST (30 min)

- Run all tests
- Verify trailing stop logic still works
- Check for any None-related crashes

---

## 🎯 Expected Results

**Before fixes**: 43 errors
**After Phase 1**: ~15 errors (None checks added)
**After Phase 2**: 0 errors ✅

---

## ⚠️ CRITICAL WARNINGS

1. **This file handles REAL MONEY trailing stops** - test thoroughly!
2. **None checks are NOT optional** - missing check = potential crash in production
3. **Decimal precision matters** - don't blindly convert to float

---

## 🔍 Investigation Needed

Lines 602 and 732: Need to examine code context to identify:
- What variable has type `object`?
- Why did MyPy infer `object` instead of proper type?
- Add explicit type annotation

---

**Generated**: 2025-10-31
**Next File**: protection/position_guard.py (36 errors)
