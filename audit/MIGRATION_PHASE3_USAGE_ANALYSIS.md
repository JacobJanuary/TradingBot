# PHASE 3 USAGE ANALYSIS - Call Sites & Data Flow

**Date**: 2025-10-31
**Target**: core/stop_loss_manager.py
**Analysis Scope**: All call sites, parameter sources, data flow
**Status**: ✅ COMPLETE

---

## 📊 EXECUTIVE SUMMARY

**Call Sites Found**: 2 primary (4 total StopLossManager instantiations)
**Parameter Types**: Mixed (Decimal from Phase 1, float from calculations)
**Float Conversions to Remove**: 1 explicit `float()`
**Decimal Conversions to Add**: 1 `to_decimal()`
**Critical Finding**: position parameter is PositionState (Decimal) ✅

---

## 🔍 METHOD SIGNATURES ANALYSIS

### Public API Methods

#### 1. set_stop_loss() - Line 157

**Current Signature**:
```python
async def set_stop_loss(
    self,
    symbol: str,
    side: str,
    amount: float,        # ← Change to Decimal
    stop_price: float     # ← Change to Decimal
) -> Dict:
```

**Usage Frequency**: 2 direct calls, 1 internal call
**Call Sites**:
- position_manager.py:2139 (via set_stop_loss)
- stop_loss_manager.py:281 (internal from verify_and_fix_missing_sl)
- stop_loss_manager.py:884 (via set_stop_loss_unified wrapper)

**Parameter Sources**:
- `amount`: PositionState.quantity (Decimal) → currently wrapped in float()
- `stop_price`: _calculate_stop_loss() returns float, Decimal calculations

---

#### 2. verify_and_fix_missing_sl() - Line 229

**Current Signature**:
```python
async def verify_and_fix_missing_sl(
    self,
    position,             # PositionState or Position
    stop_price: float,    # ← Change to Decimal
    max_retries: int = 3
):
```

**Usage Frequency**: 1 call
**Call Sites**:
- position_manager.py:3356 (from check_positions_protection)

**Parameter Sources**:
- `position`: self.positions[symbol] → PositionState (Decimal fields)
- `stop_price`: Decimal from calculate_stop_loss()

**Internal Usage**:
- Calls set_stop_loss() with `amount=float(position.quantity)` ← **REMOVE**

---

#### 3. has_stop_loss() - Line 43

**Current Signature**:
```python
async def has_stop_loss(
    self,
    symbol: str,
    position_side: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
```

**Usage Frequency**: 4 calls
**Parameters**: No float parameters ✅
**Action**: **NO CHANGE NEEDED**

---

### Private Methods

#### 4. _set_bybit_stop_loss() - Line 327

**Current Signature**:
```python
async def _set_bybit_stop_loss(
    self,
    symbol: str,
    stop_price: float     # ← Change to Decimal
) -> Dict:
```

**Usage**: Internal only (called from set_stop_loss)
**Action**: Change signature, keep float() before exchange API

---

#### 5. _set_generic_stop_loss() - Line 443

**Current Signature**:
```python
async def _set_generic_stop_loss(
    self,
    symbol: str,
    side: str,
    amount: float,        # ← Change to Decimal
    stop_price: float     # ← Change to Decimal
) -> Dict:
```

**Usage**: Internal only (called from set_stop_loss)
**Internal Behavior**:
- Line 462: `stop_price_decimal = Decimal(str(stop_price))` ← **REMOVE**
- Already uses Decimal for calculations ✅

---

#### 6. _validate_existing_sl() - Line 715

**Current Signature**:
```python
def _validate_existing_sl(
    self,
    existing_sl_price: float,      # ← Change to Decimal
    target_sl_price: float,        # ← Change to Decimal
    side: str,
    tolerance_percent: float = 5.0 # ← Change to Decimal
) -> tuple:
```

**Usage**: Internal (called from set_stop_loss)
**Action**: Change all float parameters to Decimal

---

#### 7. _cancel_existing_sl() - Line 800

**Current Signature**:
```python
async def _cancel_existing_sl(
    self,
    symbol: str,
    sl_price: float       # ← Change to Decimal
):
```

**Usage**: Internal (called from set_stop_loss)
**Action**: Change signature, update float() usage in body

---

### Helper Function

#### 8. set_stop_loss_unified() - Line 861

**Current Signature**:
```python
async def set_stop_loss_unified(
    exchange,
    exchange_name: str,
    symbol: str,
    side: str,
    amount: float,        # ← Change to Decimal
    stop_price: float     # ← Change to Decimal
) -> Dict:
```

**Usage**: Backward compatibility wrapper
**Action**: Change signature to match set_stop_loss

---

## 📍 CALL SITE DETAILED ANALYSIS

### Call Site 1: position_manager.py:2139-2144

**Context**: _set_stop_loss() method in PositionManager

**Location**: Line 2139-2144
```python
result = await sl_manager.set_stop_loss(
    symbol=position.symbol,
    side=order_side,
    amount=float(position.quantity),  # ❌ Line 2142
    stop_price=stop_price
)
```

**Analysis**:
- **Method**: _set_stop_loss (internal method)
- **position**: PositionState from function parameter (line 2101)
- **position.quantity**: Decimal (Phase 1)
- **stop_price**: float parameter from caller

**Data Flow**:
```
PositionManager._set_stop_loss(position: PositionState, stop_price: float)
    ↓
position.quantity (Decimal)
    ↓ float() ❌ CONVERSION
    ↓
StopLossManager.set_stop_loss(amount: float)
```

**Change Required**:
```python
# BEFORE:
amount=float(position.quantity),
stop_price=stop_price

# AFTER:
amount=position.quantity,  # ✅ Pass Decimal directly
stop_price=to_decimal(stop_price)  # ✅ Convert float to Decimal
```

**Justification**:
- position is PositionState (Decimal quantity)
- stop_price comes from float parameter, needs conversion

**Risk**: 🟢 LOW - PositionState always has Decimal quantity

---

### Call Site 2: position_manager.py:3356-3360

**Context**: check_positions_protection() method in PositionManager

**Location**: Line 3356-3360
```python
success, order_id = await sl_manager.verify_and_fix_missing_sl(
    position=position,
    stop_price=stop_loss_price,
    max_retries=3
)
```

**Analysis**:
- **Method**: check_positions_protection (monitoring loop)
- **position**: self.positions[symbol] → PositionState (line 3102)
- **stop_loss_price**: Decimal from calculate_stop_loss() (line 3321)

**Data Flow Trace**:
```python
# Line 3102:
position = self.positions[symbol]  # PositionState

# Line 3321-3325:
stop_loss_price = calculate_stop_loss(
    entry_price=Decimal(str(base_price)),
    side=position.side,
    stop_loss_percent=Decimal(str(stop_loss_percent))
)
# Returns: Decimal

# Line 3356:
await sl_manager.verify_and_fix_missing_sl(
    position=position,           # PositionState
    stop_price=stop_loss_price,  # Decimal
    max_retries=3
)
```

**Change Required**: **NONE** ✅

**Current Code is CORRECT**:
- position: PositionState ✅
- stop_loss_price: Decimal ✅

**Verification**:
```python
# calculate_stop_loss() from utils/position_helpers.py:
def calculate_stop_loss(
    entry_price: Decimal,
    side: str,
    stop_loss_percent: Decimal
) -> Decimal:
    # Returns Decimal
```

**Risk**: 🟢 NONE - Already correct!

---

### Internal Call Site 3: stop_loss_manager.py:281-286

**Context**: verify_and_fix_missing_sl calls set_stop_loss

**Location**: Line 281-286
```python
result = await self.set_stop_loss(
    symbol=symbol,
    side=order_side,
    amount=float(position.quantity),  # ❌ Line 284
    stop_price=stop_price
)
```

**Analysis**:
- **position**: Parameter to verify_and_fix_missing_sl
- **Could be**: PositionState (Decimal) OR Position (Float)
- **stop_price**: Parameter (Decimal after Phase 3)

**Current Issue**:
```python
amount=float(position.quantity)  # ❌ Explicit conversion
```

**Problem**: Assumes position.quantity might not be float-compatible

**Change Required**:
```python
# BEFORE:
amount=float(position.quantity),

# AFTER:
amount=to_decimal(position.quantity),  # ✅ Handles both Float and Decimal
```

**Justification**:
- to_decimal() accepts both float and Decimal
- Safer than assuming type
- Works for PositionState (Decimal) AND Position (Float)

**Risk**: 🟢 LOW - to_decimal() is robust

---

## 🌊 DATA FLOW ANALYSIS

### Flow 1: Normal Stop Loss Creation

```
User Request
    ↓
PositionManager._set_stop_loss()
    ↓
position: PositionState (Decimal quantity)  ← Phase 1
    ↓
[Call Site 1] float(position.quantity) ❌ REMOVE
    ↓
StopLossManager.set_stop_loss(amount: float) ← Phase 3 change to Decimal
    ↓
_set_bybit_stop_loss() or _set_generic_stop_loss()
    ↓
float(amount) for exchange API ✅ KEEP (boundary)
    ↓
CCXT Exchange API (float)
```

**After Phase 3**:
```
PositionState (Decimal)
    ↓
[No conversion] ✅
    ↓
StopLossManager (Decimal)
    ↓
float() at API boundary ✅
    ↓
Exchange API (float)
```

---

### Flow 2: Missing SL Auto-Fix

```
Position Monitoring Loop
    ↓
check_positions_protection()
    ↓
position: self.positions[symbol] → PositionState
stop_loss_price: calculate_stop_loss() → Decimal
    ↓
[Call Site 2] ✅ Already passes Decimal
    ↓
StopLossManager.verify_and_fix_missing_sl(Decimal)
    ↓
[Internal Call Site 3] float(position.quantity) ❌ CHANGE to to_decimal()
    ↓
set_stop_loss(Decimal, Decimal)
    ↓
Exchange API
```

**After Phase 3**:
```
PositionState (Decimal)
    ↓
calculate_stop_loss() → Decimal
    ↓
verify_and_fix_missing_sl(Decimal) ✅
    ↓
to_decimal(position.quantity) ✅
    ↓
set_stop_loss(Decimal, Decimal) ✅
    ↓
Exchange API
```

---

## ⚠️ CRITICAL FINDINGS

### Finding 1: Mixed Position Types ⚠️

**Issue**: The `position` parameter could be either type:

| Type | Source | Fields |
|------|--------|--------|
| PositionState | self.positions[symbol] | Decimal |
| Position | Database query | Float |

**Current Code**:
```python
# Call Site 2 (line 3102):
position = self.positions[symbol]  # ← PositionState (Decimal)

# Call Site 3 internal (line 284):
amount=float(position.quantity)  # Works for both, but loses precision
```

**Solution**:
```python
# Use to_decimal() which handles both:
amount=to_decimal(position.quantity)

# to_decimal() implementation:
def to_decimal(value):
    if isinstance(value, Decimal):
        return value  # Already Decimal
    return Decimal(str(value))  # Convert float to Decimal
```

**Conclusion**: Use `to_decimal()` for safety! ✅

---

### Finding 2: stop_price Source Varies ⚠️

**Sources**:

| Call Site | Source | Type |
|-----------|--------|------|
| Call Site 1 (line 2143) | Function parameter | float |
| Call Site 2 (line 3358) | calculate_stop_loss() | Decimal |
| Call Site 3 (line 285) | Function parameter | Decimal (after change) |

**Implication**: Call Site 1 needs `to_decimal(stop_price)` conversion!

---

### Finding 3: No Database Position Usage Found ✅

**Verification**:
```bash
# Searched for database Position usage:
grep -n "Position(" core/position_manager.py | grep -v "PositionState"
# Result: No database Position instantiation in stop loss calls
```

**Conclusion**: All current call sites use PositionState (Decimal) ✅

**However**: Code should be defensive with `to_decimal()` for future-proofing

---

## 🔢 CONVERSION POINTS SUMMARY

### Conversions to REMOVE ❌

| Location | Line | Before | After |
|----------|------|--------|-------|
| position_manager.py | 2142 | `float(position.quantity)` | `position.quantity` |
| stop_loss_manager.py | 284 | `float(position.quantity)` | `to_decimal(position.quantity)` |
| stop_loss_manager.py | 462 | `Decimal(str(stop_price))` | `stop_price` |

**Total**: 3 conversions removed

---

### Conversions to ADD ✅

| Location | Line | Add |
|----------|------|-----|
| position_manager.py | 2143 | `to_decimal(stop_price)` |
| stop_loss_manager.py | 188 | `to_decimal(existing_sl)` |
| stop_loss_manager.py | 214 | `to_decimal(existing_sl)` |
| stop_loss_manager.py | 471 | `to_decimal(markPrice)` (cleanup) |
| stop_loss_manager.py | 475 | `to_decimal(ticker['last'])` (cleanup) |

**Total**: 5 conversions added (for safety/clarity)

---

### Conversions to KEEP ✅

**Exchange API Boundary** (keep float()):
- Line 374: `float(sl_price_formatted)` - Event logger
- Line 385: `float(sl_price_formatted)` - Bybit API
- Line 396: `float(sl_price_formatted)` - Bybit API
- Line 411: `float(sl_price_formatted)` - Event logger
- Line 508: `float(stop_price_decimal)` - Generic stop loss
- Line 546: `float(final_stop_price)` - Event logger
- Line 558: `float(final_stop_price)` - Create order

**Total**: 7 float() calls kept (correct boundaries!)

---

## 📋 DECISION MATRIX

### Should I change this float()?

| Context | Keep float()? | Reason |
|---------|---------------|--------|
| Before exchange.create_order() | ✅ YES | Exchange API expects float |
| Before exchange.fetch_ticker() | ✅ YES | Exchange API returns float |
| Before event_logger.log_event() | ✅ YES | Logging uses float |
| From position.quantity | ❌ NO | Use Decimal or to_decimal() |
| From stop_price parameter | ❌ NO | Use Decimal parameter |
| Decimal(str(...)) pattern | ❌ NO | Parameter already Decimal |

---

## 🎯 INTEGRATION WITH PHASE 1+2

### Phase 1 Integration ✅

**Phase 1 Changed**:
```python
@dataclass
class PositionState:
    quantity: Decimal        # Was float
    entry_price: Decimal     # Was float
    stop_loss_price: Decimal # Was float
```

**Phase 3 Benefits**:
- Call Site 1: position.quantity now Decimal (no float() needed)
- Call Site 2: position passed as-is (Decimal preserved)
- Internal: to_decimal() handles both types

---

### Phase 2 Integration ✅

**Phase 2 Changed**:
```python
# TrailingStopManager
async def create_trailing_stop(
    entry_price: Decimal,    # Was float
    quantity: Decimal,       # Was float
):
```

**Phase 3 Parallel**:
- Similar pattern: float → Decimal for parameters
- Similar risk: database still Float
- Similar solution: convert at boundaries

---

## 📊 USAGE STATISTICS

### By File

| File | Method Calls | Parameter Usage | Float() Count |
|------|--------------|-----------------|---------------|
| position_manager.py | 2 | 4 (amount, stop_price) | 1 to remove |
| stop_loss_manager.py | 1 internal | 2 (amount, stop_price) | 1 to remove |
| **Total** | **3** | **6 unique params** | **2 to remove** |

### By Parameter Type

| Parameter | Occurrences | Sources | Type After Phase 3 |
|-----------|-------------|---------|---------------------|
| amount | 3 | position.quantity | Decimal |
| stop_price | 3 | Varied (float/Decimal) | Decimal |
| tolerance_percent | 1 | Constant (5.0) | Decimal |
| sl_price | 2 | existing_sl (string) | Decimal |

---

## ✅ VERIFICATION CHECKLIST

Before Phase 3 execution:
- [x] All call sites identified (2 primary, 1 internal)
- [x] Parameter sources traced (PositionState, calculate_stop_loss)
- [x] float() conversions categorized (remove, add, keep)
- [x] Database Position vs PositionState clarified
- [x] Exchange API boundary identified
- [x] Integration with Phase 1+2 verified

---

## 🎯 FINAL RECOMMENDATIONS

### Recommendation 1: Use to_decimal() Defensively
Even though current code only uses PositionState, use `to_decimal()` for future safety:
```python
amount=to_decimal(position.quantity)  # Handles both Float and Decimal
```

### Recommendation 2: Keep Exchange Boundary Clear
ALWAYS use float() immediately before exchange API:
```python
final_stop_price = float(stop_price_decimal)
await exchange.create_order(..., stopPrice=final_stop_price)
```

### Recommendation 3: Document Database Limitation
Add comment in code:
```python
# NOTE: Database Position model uses Float columns (not migrated)
# Decimal → Float conversion happens at database write
```

---

**Generated**: 2025-10-31
**Status**: ✅ COMPLETE
**Call Sites Analyzed**: 3 (2 primary + 1 internal)
**Conversions Identified**: 2 remove, 5 add, 7 keep
**Risk Level**: 🟡 MEDIUM (mixed types handled with to_decimal())
