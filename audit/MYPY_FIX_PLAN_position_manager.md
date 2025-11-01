# 🔧 MyPy Fix Plan: core/position_manager.py

**File**: `core/position_manager.py`
**Total Errors**: 55
**Date**: 2025-10-31
**Priority**: 🔴 HIGH (second most errors)

---

## 📊 Error Classification

| Category | Count | Real/False | Priority |
|----------|-------|------------|----------|
| **Decimal ↔ float mismatch** | 20 | **REAL - DESIGN ISSUE** | CRITICAL |
| **Need type annotation** | 3 | **REAL** | MEDIUM |
| **Incompatible assignment** | 10 | **REAL** | HIGH |
| **Argument type mismatch** | 18 | **REAL** | HIGH |
| **Other** | 4 | **REAL** | MEDIUM |

---

## 🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА: Decimal ↔ float несоответствие (20 ошибок)

### Анализ Root Cause:

**Проект использует СМЕШАННЫЕ типы для денежных значений:**

#### Decimal используется в:
- `calculate_stop_loss()` → возвращает `Decimal`
- `calculate_position_size()` → возвращает `Decimal`
- `PositionState` поля: `quantity`, `entry_price`, `current_price` → ожидают `float`
- Database operations → некоторые принимают `Decimal`

#### float используется в:
- `_set_stop_loss(stop_price: float)` → ожидает `float`
- `SmartTrailingStopManager` → ожидает `float`
- `PositionState` → многие поля `float`

### Примеры ошибок:

```python
# Line 856: Decimal → float
stop_loss_price = calculate_stop_loss(...)  # Returns Decimal
await self._set_stop_loss(exchange, position_state, stop_loss_price)  # Expects float ❌

# Line 858: Decimal → float assignment
position_state.stop_loss_price = stop_loss_price  # stop_loss_price: float | None ❌

# Line 903: Decimal → float
await self.ts_manager.create_trailing_stop(
    ...
    initial_stop=stop_loss_price  # Decimal, expects float | None ❌
)

# Lines 1417-1419: Decimal → float in PositionState
PositionState(
    quantity=quantity,  # Decimal, expects float ❌
    entry_price=entry_price,  # Decimal, expects float ❌
    current_price=current_price  # Decimal, expects float ❌
)
```

### Решения:

#### Вариант 1: Конвертировать Decimal → float (БЫСТРОЕ РЕШЕНИЕ)
```python
# Everywhere we pass Decimal to function expecting float:
await self._set_stop_loss(exchange, position_state, float(stop_loss_price))
position_state.stop_loss_price = float(stop_loss_price)
```

**Pros**: Быстро, минимальные изменения
**Cons**: Теряется точность Decimal

#### Вариант 2: Изменить сигнатуры на Decimal (ПРАВИЛЬНОЕ РЕШЕНИЕ)
```python
# Change all method signatures to accept Decimal:
async def _set_stop_loss(self, exchange: ExchangeManager, position: PositionState,
                        stop_price: Decimal) -> bool:  # ← Changed to Decimal

# Change PositionState fields:
@dataclass
class PositionState:
    quantity: Decimal  # ← Changed from float
    entry_price: Decimal  # ← Changed from float
    current_price: Decimal  # ← Changed from float
    stop_loss_price: Optional[Decimal] = None  # ← Changed from float
```

**Pros**: Сохраняется точность расчетов
**Cons**: Большие изменения, нужно проверить совместимость с внешними API

#### Вариант 3: Union[Decimal, float] (КОМПРОМИСС)
```python
async def _set_stop_loss(self, exchange: ExchangeManager, position: PositionState,
                        stop_price: Union[Decimal, float]) -> bool:
```

**Pros**: Принимает оба типа
**Cons**: Нужна внутренняя конвертация

### Рекомендация:

**ВАРИАНТ 2** - Перевести ВСЕ денежные значения на Decimal:

1. ✅ Изменить `PositionState` dataclass (lines ~120-165)
2. ✅ Изменить `_set_stop_loss` signature (line 2102)
3. ✅ Изменить `SmartTrailingStopManager` signatures
4. ✅ Добавить helper: `def ensure_decimal(val: Union[Decimal, float]) -> Decimal`
5. ✅ Пройти по всем 20 ошибкам и исправить

**Затраты времени**: 2-3 часа
**Риск**: MEDIUM (нужно тщательное тестирование)
**Польза**: Устраняет источник багов с точностью

---

## ✅ CATEGORY 2: Need Type Annotation (3 errors)

### Errors:
```
core/position_manager.py:224: error: Need type annotation for "pending_updates"  [var-annotated]
core/position_manager.py:250: error: Need type annotation for "positions_without_sl_time"  [var-annotated]
core/position_manager.py:253: error: Need type annotation for "protected_order_ids"  [var-annotated]
```

### Fix:

#### Line 224:
```python
# BEFORE:
pending_updates = {}

# AFTER:
pending_updates: Dict[str, Any] = {}
```

#### Line 250:
```python
# BEFORE:
positions_without_sl_time = {}

# AFTER:
positions_without_sl_time: Dict[str, PositionState] = {}
```

#### Line 253:
```python
# BEFORE:
protected_order_ids = set()

# AFTER:
protected_order_ids: Set[str] = set()
```

---

## ⚠️ CATEGORY 3: Incompatible Assignment (10 errors)

### Example Error:
```
core/position_manager.py:160: error: Incompatible types in assignment (expression has type "None", variable has type "datetime")  [assignment]
```

### Fix:

#### Line 160 (PositionState dataclass):
```python
# BEFORE:
opened_at: datetime = None

# AFTER:
opened_at: Optional[datetime] = None
```

#### Lines 858, 942, 1519:
```python
# BEFORE:
position_state.stop_loss_price = stop_loss_price  # stop_loss_price is Decimal

# AFTER (if using Variant 1 - float conversion):
position_state.stop_loss_price = float(stop_loss_price)

# OR (if using Variant 2 - Decimal everywhere):
# Change PositionState.stop_loss_price to Optional[Decimal]
```

#### Lines 1171, 1179, 1501, 1509:
```python
# These are similar Decimal → float assignment issues
# Fix depends on chosen strategy (Variant 1, 2, or 3 above)
```

---

## 📋 CATEGORY 4: Argument Type Mismatch (18 errors)

Most of these are related to Decimal ↔ float mismatch discussed in Category 1.

### Additional Specific Fixes:

#### Line 339:
```
error: Argument 1 to "normalize_symbol" has incompatible type "Any | None"; expected "str"
```

```python
# Need to check/assert symbol is not None before calling:
if symbol:
    normalized = normalize_symbol(symbol)
```

#### Line 786:
```
error: Argument "realized_pnl" to "on_position_closed" has incompatible type "None"; expected "float"
```

```python
# BEFORE:
await self.ts_manager.on_position_closed(..., realized_pnl=None)

# AFTER:
await self.ts_manager.on_position_closed(..., realized_pnl=0.0)
# OR change on_position_closed signature to accept Optional[float]
```

#### Line 1413:
```
error: Argument "id" to "PositionState" has incompatible type "None"; expected "int"
```

```python
# BEFORE:
PositionState(id=None, ...)

# AFTER:
# Either change PositionState.id to Optional[int], or
# Generate temporary ID: PositionState(id=-1, ...)
```

#### Line 1702:
```
error: Argument "id" to "PositionState" has incompatible type "str"; expected "int"
```

```python
# BEFORE:
PositionState(id=position_id_str, ...)

# AFTER:
PositionState(id=int(position_id_str), ...)  # If position_id_str is numeric string
# OR change PositionState.id to Union[int, str]
```

#### Line 1658:
```
error: Unsupported operand types for + ("object" and "int")
```

Need to see code context - likely missing type annotation causing MyPy to infer `object`.

---

## 📝 SUMMARY: Recommended Action Plan

### Phase 1: IMMEDIATE (Quick Fixes - 1 hour)
1. ✅ Fix 3 type annotations (lines 224, 250, 253)
2. ✅ Fix `opened_at: Optional[datetime]` (line 160)
3. ✅ Fix None → 0.0 for realized_pnl (line 786)
4. ✅ Add symbol check before normalize_symbol (line 339)

### Phase 2: DESIGN DECISION (1-2 hours)
**Decide on Decimal vs float strategy:**
- Option A: Convert all Decimal to float (quick, loses precision)
- Option B: Convert all to Decimal (correct, more work)
- Option C: Use Union[Decimal, float] (compromise)

### Phase 3: IMPLEMENT CHOSEN STRATEGY (2-3 hours)
- Apply chosen strategy to all 20 Decimal ↔ float errors
- Update method signatures
- Update dataclass definitions
- Add conversion helpers if needed

### Phase 4: TEST (1 hour)
- Run all tests
- Verify no regressions
- Check precision in calculations

---

## 🎯 Expected Results

**Before fixes**: 55 errors
**After Phase 1**: ~45 errors (quick fixes)
**After Phase 2+3**: ~5 errors (remaining edge cases)
**After Phase 4**: 0 errors ✅

---

## ⚠️ CRITICAL RECOMMENDATION

**DO NOT apply quick float() conversions everywhere!**

This file handles MONEY. Precision matters. Use Decimal throughout:
- Entry prices
- Stop loss prices
- Quantity calculations
- PnL calculations

**Recommended**: Invest 3 hours to do it right (Variant 2) rather than 1 hour for quick hacks.

---

**Generated**: 2025-10-31
**Next File**: protection/trailing_stop.py (43 errors)
