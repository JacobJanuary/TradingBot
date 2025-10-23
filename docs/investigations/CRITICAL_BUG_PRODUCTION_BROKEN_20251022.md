# 🚨 КРИТИЧЕСКАЯ ОШИБКА: Production Полностью Сломан
## Дата: 2025-10-22 00:50
## Severity: P0 - КРИТИЧНО (PRODUCTION DOWN!)

---

## 📊 EXECUTIVE SUMMARY

**КРИТИЧЕСКАЯ ОШИБКА**: Последний коммит `3e01d78` + `ae73a19` сломали обработку сигналов.

**Статус**: 🔴 **PRODUCTION DOWN**

**Ошибки**:
1. ❌ **TypeError**: `'<' not supported between instances of 'str' and 'float'` (line 1600)
2. ❌ **UnboundLocalError**: `SymbolUnavailableError` not defined (line 1391)

**Impact**: **ВСЕ сигналы failing!**

---

## 🔴 ОШИБКА #1: TypeError в _calculate_position_size

### Stack Trace:
```
File "/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py", line 1600, in _calculate_position_size
    if formatted_qty < min_amount:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: '<' not supported between instances of 'str' and 'float'
```

### Root Cause:

**Файл**: `core/position_manager.py:1597-1600`

**Проблемный код** (commit `ae73a19` - precision fix):
```python
# Line 1597
formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)

# Line 1600 - BUG!
if formatted_qty < min_amount:  # formatted_qty is STRING, min_amount is FLOAT!
```

**Причина**:
- `exchange.amount_to_precision()` возвращает **STRING** (например: "0.5")
- `min_amount` это **FLOAT** (например: 0.1)
- Python 3 не позволяет сравнивать str < float → **TypeError**

**Откуда**: Commit `ae73a19` добавил re-validation после precision, но НЕ конвертировал formatted_qty в float!

---

## 🔴 ОШИБКА #2: UnboundLocalError для SymbolUnavailableError

### Stack Trace:
```
File "/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py", line 1391, in open_position
    except SymbolUnavailableError as e:
           ^^^^^^^^^^^^^^^^^^^^^^
UnboundLocalError: cannot access local variable 'SymbolUnavailableError' where it is not associated with a value
```

### Root Cause:

**Файл**: `core/position_manager.py:1000, 1391`

**Проблема**: Import внутри try, except снаружи!

```python
# Line 999-1000: Import ВНУТРИ try block
try:
    from core.atomic_position_manager import AtomicPositionManager, SymbolUnavailableError, MinimumOrderLimitError
    # ... atomic code ...

# Line 1108: except ВНУТРИ этого try - OK
except SymbolUnavailableError as e:
    # This works - в области видимости

# Line 1391: except СНАРУЖИ try - FAIL!
except SymbolUnavailableError as e:  # ERROR: not in scope!
```

**Причина**:
- `SymbolUnavailableError` импортирован на line 1000 ВНУТРИ try block
- Line 1391 except находится СНАРУЖИ этого try
- Python scoping: переменная вне области видимости
- Когда происходит exception (TypeError на line 1600), код пытается поймать его на line 1391
- Но `SymbolUnavailableError` не определен в этой области → **UnboundLocalError**

**Откуда**: Существовавшая проблема, но проявилась когда TypeError начал происходить из-за Ошибки #1

---

## 🎯 ПОСЛЕДОВАТЕЛЬНОСТЬ СОБЫТИЙ

1. **Signal поступает** (BULLAUSDT)
2. **open_position() вызывается**
3. **_calculate_position_size() выполняется**
4. **Line 1597**: `formatted_qty = exchange.amount_to_precision(...)` → возвращает STRING "123.45"
5. **Line 1600**: `if formatted_qty < min_amount:` → **TypeError** (str vs float)
6. **Exception propagates** вверх к open_position
7. **Line 1391**: `except SymbolUnavailableError` пытается поймать
8. **UnboundLocalError**: SymbolUnavailableError не в области видимости
9. **Exception propagates** дальше
10. **Signal fails** ❌

---

## 🔍 ПОДРОБНЫЙ АНАЛИЗ

### Проблема #1: formatted_qty is STRING

**Code from commit `ae73a19`**:
```python
# core/position_manager.py:1597-1621
formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)

# FIX: Re-validate after precision formatting (amount_to_precision may truncate below minimum)
if formatted_qty < min_amount:  # ← BUG HERE!
    # Precision truncated below minimum - adjust UP to next valid step
    step_size = exchange.get_step_size(symbol)
    if step_size > 0:
        # Calculate steps needed to reach minimum
        steps_needed = int((min_amount - formatted_qty) / step_size) + 1  # ← BUG HERE too!
        adjusted_qty = formatted_qty + (steps_needed * step_size)  # ← And HERE!

        # Re-apply precision to ensure stepSize alignment
        formatted_qty = exchange.amount_to_precision(symbol, adjusted_qty)

        # Final check: if still below minimum after adjustment, cannot trade
        if formatted_qty < min_amount:  # ← BUG HERE!
```

**Все сравнения и арифметические операции со STRING!**

### Проблема #2: Import Scope

**Current structure**:
```python
async def open_position(self, request):
    try:
        # ... начало функции (line 800-998) ...

        try:  # ← INNER try (line 999)
            from core.atomic_position_manager import SymbolUnavailableError  # Line 1000
            # ... atomic code ...

        except SymbolUnavailableError as e:  # Line 1108 - IN SCOPE ✅
            # This works

        # ... non-atomic fallback code (line 1130-1388) ...

    # Line 1391 - OUTSIDE inner try!
    except SymbolUnavailableError as e:  # ← OUT OF SCOPE ❌
        # SymbolUnavailableError not defined here!
```

**Проблема**: Import на line 1000 только для INNER try block

---

## 📋 ПЛАН ИСПРАВЛЕНИЯ

### FIX #1: Конвертировать formatted_qty в float

**Файл**: `core/position_manager.py:1597-1621`

**MINIMAL FIX** (Golden Rule):

```python
# Line 1597: Apply precision
formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)

# FIX: Convert to float IMMEDIATELY after amount_to_precision
formatted_qty = float(formatted_qty)  # ← ADD THIS LINE

# Now all comparisons and arithmetic work
if formatted_qty < min_amount:
    step_size = exchange.get_step_size(symbol)
    if step_size > 0:
        steps_needed = int((min_amount - formatted_qty) / step_size) + 1
        adjusted_qty = formatted_qty + (steps_needed * step_size)
        formatted_qty = float(exchange.amount_to_precision(symbol, adjusted_qty))  # Convert here too
        if formatted_qty < min_amount:
            # ...
```

**Альтернатива** (если amount_to_precision может вернуть None):
```python
formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)
if formatted_qty is None:
    logger.error(f"{symbol}: amount_to_precision returned None")
    return None

formatted_qty = float(formatted_qty)  # Safe now
```

---

### FIX #2: Move import to module level OR fix scope

**Option A: Move import to TOP of file** (RECOMMENDED):

**Файл**: `core/position_manager.py:1-50`

```python
# Top of file imports
from core.atomic_position_manager import (
    AtomicPositionManager,
    SymbolUnavailableError,
    MinimumOrderLimitError
)
```

**Then REMOVE** line 1000 import.

**Pros**:
- Simple
- Clear scope
- Standard Python practice

**Cons**:
- Import даже если atomic не используется (minimal overhead)

---

**Option B: Define exceptions at module level** (if circular import):

If moving import causes circular import, catch generic Exception:

```python
# Line 1391
except Exception as e:
    # Check if it's SymbolUnavailableError by name
    if type(e).__name__ == 'SymbolUnavailableError':
        logger.warning(f"⚠️ Skipping {symbol}: {e}")
        return None
    elif type(e).__name__ == 'MinimumOrderLimitError':
        logger.warning(f"⚠️ Skipping {symbol}: {e}")
        return None
    else:
        raise  # Re-raise other exceptions
```

**Pros**:
- Avoids circular import
- Works without importing

**Cons**:
- Ugly
- Less type-safe

---

**Option C: Import at function level but BEFORE all try blocks**:

```python
async def open_position(self, request):
    # Import at start of function
    from core.atomic_position_manager import SymbolUnavailableError, MinimumOrderLimitError

    try:
        # ... all code ...
    except SymbolUnavailableError as e:  # Now in scope ✅
        # ...
```

**Pros**:
- Lazy import (only when function called)
- Proper scope

**Cons**:
- Import on every call (small overhead)

---

## 🎯 RECOMMENDED FIX

### Step 1: Fix TypeError (IMMEDIATE - P0)

**File**: `core/position_manager.py:1597`

**Add ONE line**:
```python
formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)
formatted_qty = float(formatted_qty)  # ← ADD THIS
```

**And line 1609**:
```python
formatted_qty = exchange.amount_to_precision(symbol, adjusted_qty)
formatted_qty = float(formatted_qty)  # ← ADD THIS
```

### Step 2: Fix UnboundLocalError (IMMEDIATE - P0)

**File**: `core/position_manager.py:1-50`

**Add import at TOP**:
```python
from core.atomic_position_manager import (
    AtomicPositionManager,
    SymbolUnavailableError,
    MinimumOrderLimitError
)
```

**Remove line 1000**:
```python
# DELETE THIS LINE:
# from core.atomic_position_manager import AtomicPositionManager, SymbolUnavailableError, MinimumOrderLimitError
```

---

## ⚠️ РИСКИ

### Риск #1: Circular Import

If moving imports to top causes circular import:
- Use Option B (exception name checking)
- OR use Option C (function-level import)

### Риск #2: amount_to_precision returns None

If `amount_to_precision` can return None:
- Add None check before float()
- Return None early

### Риск #3: amount_to_precision returns invalid string

If returns non-numeric string:
- Wrap in try-except ValueError
- Log error and return None

---

## 🧪 TESTING

### Test #1: Verify float conversion

```python
# In _calculate_position_size
formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)
logger.debug(f"formatted_qty type: {type(formatted_qty)}, value: {formatted_qty}")
formatted_qty = float(formatted_qty)
logger.debug(f"After float: type: {type(formatted_qty)}, value: {formatted_qty}")
```

### Test #2: Verify exception catching

```python
# Trigger SymbolUnavailableError
# Check that it's caught correctly at line 1391
```

---

## 📊 CHECKLIST

### Immediate (P0 - PRODUCTION DOWN!):
- [ ] Fix #1: Add `float()` conversion for formatted_qty
- [ ] Fix #2: Move imports to top of file OR fix scope
- [ ] Test: Send test signal to verify it works
- [ ] Deploy: Push to production ASAP
- [ ] Monitor: Check logs for other errors

### Post-Fix (P1):
- [ ] Review all `amount_to_precision` calls in codebase
- [ ] Add type hints to clarify return types
- [ ] Add unit tests for this code path
- [ ] Document `amount_to_precision` return type

---

## 📝 SUMMARY

**Problem**: Two critical bugs introduced in recent commits

**Bug #1**: `formatted_qty` is STRING, compared to FLOAT → TypeError
**Bug #2**: `SymbolUnavailableError` imported inside try, caught outside → UnboundLocalError

**Impact**: **ALL signals failing** - PRODUCTION DOWN

**Fix**:
1. Add `float()` conversion (2 lines)
2. Move imports to top (remove 1 line, add 1 import block)

**Time to fix**: 5 minutes

**Risk**: Low (minimal changes)

---

**Status**: 🔴 **CRITICAL - NEEDS IMMEDIATE FIX**

**Created**: 2025-10-22 01:00
**Priority**: P0
**Assignee**: URGENT
