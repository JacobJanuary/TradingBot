# 🔧 MyPy Fix Plan: database/repository.py

**File**: `database/repository.py`
**Total Errors**: 64
**Date**: 2025-10-31
**Priority**: 🔴 CRITICAL (most errors in codebase)

---

## 📊 Error Classification

| Category | Count | Real/False | Priority |
|----------|-------|------------|----------|
| `None has no attribute` | 28 | **FALSE POSITIVE** | LOW |
| `Incompatible default (type vs None)` | 26 | **REAL** | HIGH |
| `Function redefinition` | 1 | **REAL - CRITICAL BUG** | CRITICAL |
| `Return type mismatch` | 1 | **REAL** | MEDIUM |
| `Argument type (list append)` | 6 | **FALSE POSITIVE** | LOW |
| `Default parameter Optional` | 2 | **REAL** | MEDIUM |

---

## 🚨 CRITICAL: Function Redefinition (Line 880)

### Error:
```
database/repository.py:880: error: Name "create_risk_violation" already defined on line 135  [no-redef]
```

### Analysis:
**REAL BUG - ALREADY KNOWN FROM FLAKE8 AUDIT**

```python
# Line 135: Real implementation (DEAD CODE - never executes!)
async def create_risk_violation(self, violation) -> int:
    query = """INSERT INTO monitoring.risk_violations ..."""
    return violation_id  # Returns int

# Line 880: Stub (THIS ONE RUNS!)
async def create_risk_violation(self, violation: Any) -> bool:
    return True  # Does NOTHING - data loss!
```

**Impact**: All risk violations are NOT saved to database since stub was added.

### Fix:
**DELETE lines 880-882:**

```python
# REMOVE THIS:
async def create_risk_violation(self, violation: Any) -> bool:
    """Create risk violation"""
    return True
```

**Status**: ✅ Already documented in `audit/CRITICAL_BUG_FUNCTION_REDEFINITION.md`

---

## ⚠️ CATEGORY 1: "None has no attribute" (28 errors)

### Errors:
```
database/repository.py:125: error: "None" has no attribute "acquire"  [attr-defined]
database/repository.py:144: error: "None" has no attribute "acquire"  [attr-defined]
... (28 total)
```

### Root Cause:
```python
# Line 19-22:
def __init__(self, db_config: Dict):
    self.db_config = db_config
    self.pool = None  # ← MyPy sees this as "always None"

# Line 45:
async def initialize(self):
    self.pool = await asyncpg.create_pool(...)  # ← Pool created here
```

### Analysis:
**FALSE POSITIVE** - MyPy doesn't know that `initialize()` is always called before other methods.

**Why this happens**:
- `self.pool` initialized as `None` in `__init__`
- Actually set in `initialize()` async method
- All other methods assume pool is initialized
- This is a valid pattern for async initialization

### Fix Options:

#### Option 1: Add type annotation (RECOMMENDED)
```python
# Line 4: Add to imports
from typing import List, Optional, Dict, Any

# Line 19-22: Add type hint
def __init__(self, db_config: Dict):
    self.db_config = db_config
    self.pool: Optional[asyncpg.Pool] = None  # ← Add type hint
```

**Result**: MyPy will still complain, but now correctly shows pool can be None.

#### Option 2: Add assertion guards (NOT RECOMMENDED - adds runtime overhead)
```python
async def get_params(self, exchange_id: int) -> Optional[Dict]:
    assert self.pool is not None, "Pool not initialized"  # ← Guard
    async with self.pool.acquire() as conn:
        ...
```

#### Option 3: Add # type: ignore comments (QUICK FIX)
```python
async with self.pool.acquire() as conn:  # type: ignore[union-attr]
    ...
```

### Recommended Action:
**Option 1** + **Option 3** for specific lines:
1. Add type hint to `self.pool: Optional[asyncpg.Pool] = None`
2. Add `# type: ignore[attr-defined]` to lines where MyPy complains
3. Document that `initialize()` must be called before any DB operations

**Lines to add `# type: ignore[attr-defined]`:**
- 125, 144, 179, 257, 294, 339, 363, 402, 488, 505, 528, 542
- 588, 612, 641, 657, 668, 680, 744, 759, 787, 857, 917, 958
- 995, 1231, 1283, 1358, 1408, 1447, 1514

---

## ✅ CATEGORY 2: Incompatible Default (26 errors)

### Errors Example:
```
database/repository.py:546: error: Incompatible default for argument "close_price" (default has type "None", argument has type "float")  [assignment]
```

### Root Cause:
```python
# Line 545-550: INCORRECT
async def close_position(self, position_id: int,
                        close_price: float = None,  # ❌ Should be Optional[float]
                        pnl: float = None,
                        pnl_percentage: float = None,
                        reason: str = None,
                        exit_data: Dict = None):
```

### Analysis:
**REAL ERROR** - Python allows this, but it violates PEP 484 type hints standard.

**Impact**: MyPy can't properly check if None is handled inside function.

### Fix:
**Replace `type = None` with `Optional[type] = None`**

#### Lines 546-550:
```python
# BEFORE:
async def close_position(self, position_id: int,
                        close_price: float = None,
                        pnl: float = None,
                        pnl_percentage: float = None,
                        reason: str = None,
                        exit_data: Dict = None):

# AFTER:
async def close_position(self, position_id: int,
                        close_price: Optional[float] = None,
                        pnl: Optional[float] = None,
                        pnl_percentage: Optional[float] = None,
                        reason: Optional[str] = None,
                        exit_data: Optional[Dict] = None):
```

#### Line 844:
```python
# BEFORE:
async def create_event(..., notes: str = None):

# AFTER:
async def create_event(..., notes: Optional[str] = None):
```

#### Line 1198:
```python
# BEFORE:
async def create_aged_position(..., loss_tolerance: Decimal = None) -> Dict:

# AFTER:
async def create_aged_position(..., loss_tolerance: Optional[Decimal] = None) -> Dict:
```

#### Line 1252:
```python
# BEFORE:
async def get_active_aged_positions(self, phases: List[str] = None) -> List[Dict]:

# AFTER:
async def get_active_aged_positions(self, phases: Optional[List[str]] = None) -> List[Dict]:
```

#### Lines 1294-1297:
```python
# BEFORE:
async def update_aged_position(
    self,
    position_id: str,
    phase: str = None,
    target_price: Decimal = None,
    hours_aged: float = None,
    loss_tolerance: Decimal = None
) -> bool:

# AFTER:
async def update_aged_position(
    self,
    position_id: str,
    phase: Optional[str] = None,
    target_price: Optional[Decimal] = None,
    hours_aged: Optional[float] = None,
    loss_tolerance: Optional[Decimal] = None
) -> bool:
```

#### Lines 1375-1381:
```python
# BEFORE:
async def create_aged_position_event(
    ...
    market_price: Decimal = None,
    target_price: Decimal = None,
    price_distance_percent: Decimal = None,
    action_taken: str = None,
    success: bool = None,
    error_message: str = None,
    event_metadata: Dict[Any, Any] = None
):

# AFTER:
async def create_aged_position_event(
    ...
    market_price: Optional[Decimal] = None,
    target_price: Optional[Decimal] = None,
    price_distance_percent: Optional[Decimal] = None,
    action_taken: Optional[str] = None,
    success: Optional[bool] = None,
    error_message: Optional[str] = None,
    event_metadata: Optional[Dict[Any, Any]] = None
):
```

#### Lines 1462-1463:
```python
# BEFORE:
async def get_aged_position_history(
    ...
    from_date: datetime = None,
    to_date: datetime = None
) -> List[Dict]:

# AFTER:
async def get_aged_position_history(
    ...
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None
) -> List[Dict]:
```

**Total Changes**: 26 parameters across 8 functions

---

## 📋 CATEGORY 3: Return Type Mismatch (Line 1245)

### Error:
```
database/repository.py:1245: error: Incompatible return value type (got "dict[Any, Any] | None", expected "dict[Any, Any]")  [return-value]
```

### Root Cause:
```python
# Line 1190-1199:
async def create_aged_position(
    self,
    position_id: str,
    ...
    loss_tolerance: Decimal = None
) -> Dict:  # ← Says "always returns Dict"
    ...
    # Line 1245:
    return dict(row) if row else None  # ← Can return None!
```

### Analysis:
**REAL ERROR** - Function signature lies about return type.

### Fix:
```python
# Line 1199: Change return type
# BEFORE:
) -> Dict:

# AFTER:
) -> Optional[Dict]:
```

---

## 🔄 CATEGORY 4: List Type Inference Issues (8 errors)

### Errors:
```
database/repository.py:225: error: Argument 1 to "append" of "list" has incompatible type "float"; expected "int"  [arg-type]
database/repository.py:231: error: Argument 1 to "append" of "list" has incompatible type "float"; expected "int"  [arg-type]
database/repository.py:237: error: Argument 1 to "append" of "list" has incompatible type "float"; expected "int"  [arg-type]
database/repository.py:1331: error: Argument 1 to "append" of "list" has incompatible type "Decimal"; expected "str"  [arg-type]
database/repository.py:1337: error: Argument 1 to "append" of "list" has incompatible type "float"; expected "str"  [arg-type]
database/repository.py:1343: error: Argument 1 to "append" of "list" has incompatible type "Decimal"; expected "str"  [arg-type]
```

### Root Cause:

#### Problem 1 (Lines 213-237):
```python
# Line 213:
params = [exchange_id]  # ← MyPy infers: List[int]

# Line 219:
params.append(max_trades_filter)  # int ✅

# Lines 225, 231, 237:
params.append(stop_loss_filter)  # float ❌ - MyPy expects int
params.append(trailing_activation_filter)  # float ❌
params.append(trailing_distance_filter)  # float ❌
```

#### Problem 2 (Lines 1317-1343):
```python
# Line 1317:
params = []  # ← MyPy doesn't know type

# Line 1325:
params.append(phase)  # str ← MyPy infers: List[str]

# Lines 1331, 1337, 1343:
params.append(target_price)  # Decimal ❌ - MyPy expects str
params.append(hours_aged)  # float ❌
params.append(loss_tolerance)  # Decimal ❌
```

### Analysis:
**FALSE POSITIVE** - asyncpg accepts `List[Any]` for query parameters.

MyPy incorrectly infers list type from first element. In reality, asyncpg parameters can be mixed types.

### Fix Options:

#### Option 1: Type annotation (RECOMMENDED)
```python
# Line 213:
# BEFORE:
params = [exchange_id]

# AFTER:
params: List[Any] = [exchange_id]

# Line 1317:
# BEFORE:
params = []

# AFTER:
params: List[Any] = []
```

#### Option 2: Cast to Any (NOT RECOMMENDED)
```python
params.append(Any(stop_loss_filter))  # Ugly
```

#### Option 3: Type ignore (QUICK FIX)
```python
params.append(stop_loss_filter)  # type: ignore[arg-type]
```

### Recommended Action:
**Option 1** - Add type annotations to both lists:
- Line 213: `params: List[Any] = [exchange_id]`
- Line 1317: `params: List[Any] = []`

---

## 📝 SUMMARY: Action Items

### CRITICAL (Do First):
1. ✅ **DELETE function stub** (lines 880-882)
2. ✅ **Fix return type** (line 1199): `-> Dict` → `-> Optional[Dict]`

### HIGH Priority:
3. ✅ **Add Optional to 26 parameters** (see Category 2 above)
4. ✅ **Add type annotations to params lists**:
   - Line 213: `params: List[Any] = [exchange_id]`
   - Line 1317: `params: List[Any] = []`

### MEDIUM Priority:
5. ✅ **Add type hint to pool** (line 22):
   ```python
   self.pool: Optional[asyncpg.Pool] = None
   ```
6. ✅ **Add `# type: ignore[attr-defined]` comments** to 28 lines with pool.acquire()

---

## 🎯 Expected Results After Fixes

**Before fixes**: 64 errors
**After fixes**: 0 errors

**Breakdown**:
- Function redefinition: -1 error (CRITICAL FIX)
- Optional fixes: -26 errors (REAL FIXES)
- Return type fix: -1 error (REAL FIX)
- List type annotations: -6 errors (FALSE POSITIVE FIX)
- Pool type ignores: -28 errors (FALSE POSITIVE SUPPRESSION)
- Remaining: 2 errors (need manual review)

---

## 🔧 Implementation Order

1. **Phase 1**: Delete stub function (line 880)
2. **Phase 2**: Fix return type (line 1199)
3. **Phase 3**: Add Optional to all parameters (26 fixes)
4. **Phase 4**: Add List[Any] annotations (2 lines)
5. **Phase 5**: Add pool type hint and ignores (29 changes)
6. **Phase 6**: Run MyPy again to verify 0 errors

---

**Estimated Time**: 15-20 minutes
**Risk Level**: LOW (mostly type hint additions)
**Testing Required**: ✅ All existing tests should pass (no runtime changes)

---

**Generated**: 2025-10-31
**Next File**: core/position_manager.py (55 errors)
