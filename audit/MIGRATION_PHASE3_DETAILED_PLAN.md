# PHASE 3 DETAILED PLAN - StopLossManager Decimal Migration

**Date**: 2025-10-31
**Target**: core/stop_loss_manager.py (883 lines)
**Approach**: Full Migration (Option A)
**Complexity**: 🔴 HIGH (database layer involved)
**Estimated Time**: 3-4 hours

---

## 🎯 OBJECTIVE

Migrate StopLossManager to accept `Decimal` parameters for `amount` and `stop_price`,
eliminating precision loss at the call site level while maintaining Float conversion
at the exchange API boundary.

---

## ⚠️ CRITICAL CONTEXT

### Database Reality
```python
# database/models.py - Position class (SQLAlchemy ORM)
class Position(Base):
    quantity = Column(Float)           # ❌ Float in database
    entry_price = Column(Float)        # ❌ Float in database
    stop_loss_price = Column(Float)    # ❌ Float in database
```

**Key Understanding**: Database will ALWAYS be Float. This migration preserves
Decimal precision in the call chain (PositionState → StopLossManager) but
Float conversion still occurs when writing to database or calling exchange API.

### Phase 1+2 Integration
- Phase 1: PositionState uses Decimal ✅
- Phase 2: TrailingStopManager uses Decimal ✅
- Phase 3: StopLossManager uses Decimal ← **THIS PHASE**
- Database/Exchange: Always Float (architectural boundary)

---

## 📋 CHANGES SUMMARY

| Category | Count | Description |
|----------|-------|-------------|
| Method Signatures | 5 | Public + private methods |
| Parameters Changed | 9 | amount, stop_price parameters |
| Internal Conversions | 2 | Decimal(str(...)) to remove |
| Call Sites | 2 | position_manager.py |
| Helper Functions | 1 | set_stop_loss_unified |

---

## 🔧 DETAILED CHANGES

### File: core/stop_loss_manager.py

---

#### **Change 1: set_stop_loss method signature** (lines 157-163)

**BEFORE**:
```python
async def set_stop_loss(
    self,
    symbol: str,
    side: str,
    amount: float,
    stop_price: float
) -> Dict:
```

**AFTER**:
```python
async def set_stop_loss(
    self,
    symbol: str,
    side: str,
    amount: Decimal,
    stop_price: Decimal
) -> Dict:
```

**Justification**:
- Primary public API of StopLossManager
- Called from position_manager with PositionState.quantity (Decimal)
- stop_price comes from Decimal calculations

**Impact**: Call sites must pass Decimal (already are or can easily convert)

---

#### **Change 2: Remove float() conversions in set_stop_loss** (lines 188-189, 214)

**BEFORE** (line 188-189):
```python
is_valid, reason = self._validate_existing_sl(
    existing_sl_price=float(existing_sl),
    target_sl_price=float(stop_price),
    side=side,
    tolerance_percent=5.0
)
```

**AFTER**:
```python
is_valid, reason = self._validate_existing_sl(
    existing_sl_price=to_decimal(existing_sl),
    target_sl_price=stop_price,  # Already Decimal from param
    side=side,
    tolerance_percent=5.0
)
```

**BEFORE** (line 214):
```python
await self._cancel_existing_sl(symbol, float(existing_sl))
```

**AFTER**:
```python
await self._cancel_existing_sl(symbol, to_decimal(existing_sl))
```

**Justification**: existing_sl comes from has_stop_loss (string), convert to Decimal
**Note**: _validate_existing_sl and _cancel_existing_sl signatures also change (see below)

---

#### **Change 3: verify_and_fix_missing_sl method signature** (line 232)

**BEFORE**:
```python
async def verify_and_fix_missing_sl(
    self,
    position,
    stop_price: float,
    max_retries: int = 3
):
```

**AFTER**:
```python
async def verify_and_fix_missing_sl(
    self,
    position,
    stop_price: Decimal,
    max_retries: int = 3
):
```

**Justification**: stop_price comes from Decimal calculations in position_manager

---

#### **Change 4: Remove float() conversion in verify_and_fix_missing_sl** (line 284)

**BEFORE**:
```python
result = await self.set_stop_loss(
    symbol=symbol,
    side=order_side,
    amount=float(position.quantity),  # ❌ Explicit conversion
    stop_price=stop_price
)
```

**AFTER**:
```python
result = await self.set_stop_loss(
    symbol=symbol,
    side=order_side,
    amount=position.quantity,  # ✅ Pass Decimal directly
    stop_price=stop_price
)
```

**Justification**: position is PositionState with Decimal quantity (Phase 1)

**CRITICAL NOTE**: position parameter could be database Position (Float) OR PositionState (Decimal).
We need to handle both:
```python
# Safe conversion that handles both types
amount=to_decimal(position.quantity) if not isinstance(position.quantity, Decimal) else position.quantity
```

**Actually simpler**: Just use `to_decimal(position.quantity)` which accepts both!

**SIMPLIFIED AFTER**:
```python
result = await self.set_stop_loss(
    symbol=symbol,
    side=order_side,
    amount=to_decimal(position.quantity),  # ✅ Handles both Float and Decimal
    stop_price=stop_price
)
```

---

#### **Change 5: _set_bybit_stop_loss method signature** (line 327)

**BEFORE**:
```python
async def _set_bybit_stop_loss(self, symbol: str, stop_price: float) -> Dict:
```

**AFTER**:
```python
async def _set_bybit_stop_loss(self, symbol: str, stop_price: Decimal) -> Dict:
```

**Justification**: Called from set_stop_loss with Decimal stop_price

---

#### **Change 6: Update float() usage in _set_bybit_stop_loss** (lines 374, 385, 396, 411)

**Context**: These float() calls are for exchange API and logging - **KEEP THEM**

Lines 374, 385, 396, 411:
```python
'stop_price': float(sl_price_formatted),
'stopPrice': float(sl_price_formatted),
```

**Action**: **NO CHANGE** - These are converting to Float for exchange API (correct boundary)

**Note**: sl_price_formatted comes from:
```python
sl_price_formatted = self.exchange.price_to_precision(symbol, stop_price)
```

This already returns float-compatible value, but explicit float() ensures correct type for API.

---

#### **Change 7: _set_generic_stop_loss method signature** (lines 443-448)

**BEFORE**:
```python
async def _set_generic_stop_loss(
    self,
    symbol: str,
    side: str,
    amount: float,
    stop_price: float
) -> Dict:
```

**AFTER**:
```python
async def _set_generic_stop_loss(
    self,
    symbol: str,
    side: str,
    amount: Decimal,
    stop_price: Decimal
) -> Dict:
```

**Justification**: Called from set_stop_loss with Decimal parameters

---

#### **Change 8: Remove Decimal(str(stop_price)) conversion** (line 462)

**BEFORE**:
```python
max_retries = 3
stop_price_decimal = Decimal(str(stop_price))

for attempt in range(max_retries):
```

**AFTER**:
```python
max_retries = 3
stop_price_decimal = stop_price  # Already Decimal from parameter

for attempt in range(max_retries):
```

**Justification**: Parameter is now Decimal, no conversion needed

---

#### **Change 9: Remove Decimal(str(...)) in price fetching** (lines 471-475)

**BEFORE**:
```python
if self.exchange_name == 'binance':
    current_price = Decimal(
        str(ticker.get('info', {}).get('markPrice', ticker['last']))
    )
else:
    current_price = Decimal(str(ticker['last']))
```

**AFTER**:
```python
if self.exchange_name == 'binance':
    current_price = to_decimal(
        ticker.get('info', {}).get('markPrice', ticker['last'])
    )
else:
    current_price = to_decimal(ticker['last'])
```

**Justification**: Use to_decimal() helper for cleaner conversion
**Note**: This is NOT a removal, but a cleanup - using helper instead of Decimal(str(...))

---

#### **Change 10: Keep float conversion for exchange API** (line 508)

**Context**:
```python
final_stop_price = float(stop_price_decimal)
final_stop_price = self.exchange.price_to_precision(symbol, final_stop_price)
```

**Action**: **NO CHANGE** - This is correct! We convert to float before calling exchange API
(exchange boundary)

---

#### **Change 11: _validate_existing_sl method signature** (lines 715-721)

**BEFORE**:
```python
def _validate_existing_sl(
    self,
    existing_sl_price: float,
    target_sl_price: float,
    side: str,
    tolerance_percent: float = 5.0
) -> tuple:
```

**AFTER**:
```python
def _validate_existing_sl(
    self,
    existing_sl_price: Decimal,
    target_sl_price: Decimal,
    side: str,
    tolerance_percent: Decimal = Decimal("5.0")
) -> tuple:
```

**Justification**: Receives Decimal parameters from set_stop_loss
**Note**: tolerance_percent changed to Decimal for precise calculations

---

#### **Change 12: Update calculation in _validate_existing_sl** (line 749)

**BEFORE**:
```python
diff_pct = abs(existing_sl_price - target_sl_price) / target_sl_price * 100
```

**AFTER**:
```python
diff_pct = abs(existing_sl_price - target_sl_price) / target_sl_price * Decimal("100")
```

**Justification**: All Decimal arithmetic, keep precision

---

#### **Change 13: _cancel_existing_sl method signature** (line 800)

**BEFORE**:
```python
async def _cancel_existing_sl(self, symbol: str, sl_price: float):
```

**AFTER**:
```python
async def _cancel_existing_sl(self, symbol: str, sl_price: Decimal):
```

**Justification**: Receives Decimal from set_stop_loss

---

#### **Change 14: Update float conversions in _cancel_existing_sl** (line 826)

**BEFORE**:
```python
price_diff = abs(float(order_stop_price) - float(sl_price)) / float(sl_price)
```

**AFTER**:
```python
price_diff = abs(to_decimal(order_stop_price) - sl_price) / sl_price
```

**Justification**: Keep Decimal precision, sl_price already Decimal

---

#### **Change 15: set_stop_loss_unified helper function** (lines 861-868)

**BEFORE**:
```python
async def set_stop_loss_unified(
    exchange,
    exchange_name: str,
    symbol: str,
    side: str,
    amount: float,
    stop_price: float
) -> Dict:
```

**AFTER**:
```python
async def set_stop_loss_unified(
    exchange,
    exchange_name: str,
    symbol: str,
    side: str,
    amount: Decimal,
    stop_price: Decimal
) -> Dict:
```

**Justification**: Helper function signature must match StopLossManager.set_stop_loss

---

### File: core/position_manager.py

---

#### **Change 16: Remove float() at call site 1** (line 2142)

**BEFORE**:
```python
result = await sl_manager.set_stop_loss(
    symbol=position.symbol,
    side=order_side,
    amount=float(position.quantity),  # ❌ Explicit conversion
    stop_price=stop_price
)
```

**AFTER**:
```python
result = await sl_manager.set_stop_loss(
    symbol=position.symbol,
    side=order_side,
    amount=position.quantity,  # ✅ Pass Decimal directly
    stop_price=to_decimal(stop_price)  # Convert if needed
)
```

**Context**:
- position is PositionState (Decimal quantity)
- stop_price is float from _calculate_stop_loss()

**Justification**: Pass Decimal directly, convert stop_price from float

---

#### **Change 17: Convert stop_price at call site 2** (line 3358)

**BEFORE**:
```python
success, order_id = await sl_manager.verify_and_fix_missing_sl(
    position=position,
    stop_price=stop_loss_price,  # Decimal from calculation
    max_retries=3
)
```

**AFTER**:
```python
success, order_id = await sl_manager.verify_and_fix_missing_sl(
    position=position,
    stop_price=stop_loss_price,  # Already Decimal ✅
    max_retries=3
)
```

**Action**: **NO CHANGE** - stop_loss_price is already Decimal!

**Verification**: Line 3321-3325 shows:
```python
stop_loss_price = calculate_stop_loss(
    entry_price=Decimal(str(base_price)),
    side=position.side,
    stop_loss_percent=Decimal(str(stop_loss_percent))
)
# Returns Decimal
```

---

## 📊 CHANGES SUMMARY TABLE

| File | Changes | Lines Modified | Type |
|------|---------|----------------|------|
| core/stop_loss_manager.py | 15 | ~25-30 | Signatures + conversions |
| core/position_manager.py | 2 | 2 | Call sites |
| **TOTAL** | **17** | **~27-32** | **Types only** |

---

## 🎯 KEY PRINCIPLES

### 1. GOLDEN RULE: No Refactoring
- **ONLY** change types (float → Decimal)
- **ZERO** logic changes
- **ZERO** structural changes
- **ZERO** optimizations "while we're here"

### 2. Decimal Flow
```
PositionState (Decimal)
    ↓ (no conversion)
StopLossManager (Decimal)  ← Phase 3 ✅
    ↓ (float() before API)
Exchange API (float)
```

### 3. Database Boundary
```python
# Writing to database (acceptable Float conversion):
await repository.update_position(
    position_id,
    stop_loss_price=float(stop_price_decimal)  # ✅ Acceptable boundary
)
```

### 4. Exchange API Boundary
```python
# Calling exchange (acceptable Float conversion):
final_stop_price = float(stop_price_decimal)
final_stop_price = self.exchange.price_to_precision(symbol, final_stop_price)
# ✅ Correct: convert to float before exchange API
```

---

## ⚠️ CRITICAL NOTES

### Note 1: Mixed Position Types
The `position` parameter in verify_and_fix_missing_sl could be:
- PositionState (Decimal fields) - from self.positions
- Position (Float fields) - from database query (not seen in current code but possible)

**Solution**: Use `to_decimal(position.quantity)` which handles both!

### Note 2: Database Stays Float
No amount of Decimal migration eliminates Float in database:
```python
# database/models.py
quantity = Column(Float)  # ❌ Will stay Float
```

This is acceptable! Database is storage layer, in-memory is computation layer.

### Note 3: MyPy Impact
Expected: -10 to -15 errors (similar to Phase 2)
- Eliminates "Decimal passed to float parameter" warnings
- May introduce new warnings where we need to add float() for exchange API

---

## 🧪 TESTING STRATEGY

Same 3-level approach as Phase 2:

### Level 1: Syntax & Type Checking (5-7 min)
1. Python syntax validation (2 files)
2. Import verification
3. MyPy type checking (expect -10 to -15 errors)
4. Verify no Decimal(str(stop_price)) at changed lines

### Level 2: Manual Verification (30-40 min)
1. Review all 15 changes in stop_loss_manager.py
2. Review 2 changes in position_manager.py
3. Verify float() only appears before exchange API calls
4. Verify to_decimal() used for CCXT data conversion
5. Check integration with Phase 1 (PositionState Decimal)

### Level 3: Documentation Review (10 min)
1. Verify all changes match plan
2. Check no logic changes (GOLDEN RULE)
3. Verify exchange API boundary preserved

**Total Testing Time**: ~45-57 minutes

---

## 🔄 ROLLBACK PLAN

**Backup File**: core/stop_loss_manager.py.BACKUP_PHASE3_[timestamp]
**Git Branch**: feature/decimal-migration-phase1 (same branch as Phase 1+2)
**Rollback**: `git revert <commit-hash>` or restore backup

---

## 📝 EXECUTION CHECKLIST

Before execution:
- [ ] Create backup of core/stop_loss_manager.py
- [ ] Verify git branch (feature/decimal-migration-phase1)
- [ ] Verify Phases 1+2 complete (commits b71da84, 3d79fd9)
- [ ] Import to_decimal helper available
- [ ] Review this plan one final time

During execution:
- [ ] Change 1: set_stop_loss signature (lines 161-162)
- [ ] Change 2: Remove float() in set_stop_loss (lines 188-189, 214)
- [ ] Change 3: verify_and_fix_missing_sl signature (line 232)
- [ ] Change 4: Remove float() in verify_and_fix_missing_sl (line 284)
- [ ] Change 5: _set_bybit_stop_loss signature (line 327)
- [ ] Change 6: Keep float() for exchange API (no change)
- [ ] Change 7: _set_generic_stop_loss signature (lines 447-448)
- [ ] Change 8: Remove Decimal(str(stop_price)) (line 462)
- [ ] Change 9: Use to_decimal() for ticker data (lines 471-475)
- [ ] Change 10: Keep float() for exchange API (no change)
- [ ] Change 11: _validate_existing_sl signature (lines 717-720)
- [ ] Change 12: Update calculation (line 749)
- [ ] Change 13: _cancel_existing_sl signature (line 800)
- [ ] Change 14: Update float() conversion (line 826)
- [ ] Change 15: set_stop_loss_unified signature (lines 866-867)
- [ ] Change 16: Remove float() at call site 1 (line 2142)
- [ ] Change 17: Verify call site 2 (line 3358 - already correct)

After execution:
- [ ] Run Level 1 tests (syntax, imports, MyPy)
- [ ] Run Level 2 tests (manual verification)
- [ ] Run Level 3 tests (documentation review)
- [ ] Create git commit with detailed message
- [ ] Update execution log

---

**READY FOR EXECUTION**: YES
**Estimated Time**: 3-4 hours (including testing)
**Risk Level**: 🔴 HIGH (but manageable with careful execution)

---

**Generated**: 2025-10-31
**Status**: ✅ PLANNING COMPLETE - READY FOR EXECUTION
**Next Step**: Create USAGE_ANALYSIS, TESTING_PLAN, and SUMMARY documents
