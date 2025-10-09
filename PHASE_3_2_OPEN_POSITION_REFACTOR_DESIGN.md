# Phase 3.2: open_position() Refactoring Design

**Status:** 🔄 IN DESIGN
**Priority:** 🟡 HIGH - Code maintainability
**Risk:** ⚠️ MEDIUM - Core trading logic
**Current Size:** 393 lines (505-895)

---

## 🎯 ПРОБЛЕМА

### Текущее состояние:
```python
async def open_position(self, request: PositionRequest) -> Optional[PositionState]:
    """393 lines of complex logic with multiple responsibilities"""

    # 1. Lock acquisition (40 lines)
    # 2. Validation (60 lines)
    # 3. Position sizing (40 lines)
    # 4. Order execution (80 lines)
    # 5. Stop loss (40 lines)
    # 6. Database save (80 lines)
    # 7. Cleanup (20 lines)
```

**Проблемы:**
- ❌ Too long - сложно понять и maintain
- ❌ Multiple responsibilities - нарушает Single Responsibility Principle
- ❌ Сложно тестировать отдельные части
- ❌ Высокая cyclomatic complexity

---

## ✅ РЕШЕНИЕ: Разбить на 6 Helper Methods

### Архитектура:

```python
async def open_position(self, request: PositionRequest) -> Optional[PositionState]:
    """
    Main orchestrator - координирует workflow

    CRITICAL: Не меняем внешний интерфейс!
    """

    # 1. Lock acquisition + duplicate checks
    lock_info = await self._validate_signal_and_locks(request)
    if not lock_info.can_proceed:
        return None

    try:
        # 2. Market + Risk validation
        validation = await self._validate_market_and_risk(request, lock_info.exchange)
        if not validation.passed:
            return None

        # 3. Prepare order parameters
        order_params = await self._prepare_order_params(
            request, lock_info.exchange, validation.market_info
        )
        if not order_params:
            return None

        # 4. Execute and verify order
        order = await self._execute_and_verify_order(
            lock_info.exchange, request, order_params
        )
        if not order:
            return None

        # 5. Create position + set stop loss
        position = await self._create_position_with_sl(
            request, order, order_params
        )
        if not position:
            await self._compensate_failed_sl(lock_info.exchange, position, order)
            return None

        # 6. Save to DB + trailing stop + tracking
        await self._save_position_to_db(
            position, lock_info.exchange, order
        )

        return position

    except Exception as e:
        logger.error(f"Error opening position: {e}", exc_info=True)
        return None

    finally:
        # Cleanup locks
        await lock_info.release()
```

---

## 📋 HELPER METHODS DESIGN

### 1. _validate_signal_and_locks()

**Purpose:** Acquire locks and check duplicates

**Lines:** 536-600 (~64 lines)

**Input:** `request: PositionRequest`

**Output:** `LockInfo` dataclass:
```python
@dataclass
class LockInfo:
    can_proceed: bool
    lock_key: str
    position_lock: asyncio.Lock
    db_lock_acquired: bool
    exchange: ExchangeManager
    reason: Optional[str] = None  # Why can't proceed

    async def release(self):
        """Release all acquired locks"""
        if self.db_lock_acquired:
            await repository.release_position_lock(...)
        position_locks.discard(self.lock_key)
```

**Logic:**
- Acquire asyncio lock (with meta-lock)
- Check in-memory cache
- Check DB for existing position
- Acquire PostgreSQL advisory lock
- Get exchange instance
- Check position doesn't exist

**Error Handling:**
- Return `LockInfo(can_proceed=False, reason="...")` on any failure
- No exceptions thrown (handled internally)

---

### 2. _validate_market_and_risk()

**Purpose:** Validate market availability and risk limits

**Lines:** 602-633 (~31 lines)

**Input:** `request: PositionRequest, exchange: ExchangeManager`

**Output:** `ValidationResult` dataclass:
```python
@dataclass
class ValidationResult:
    passed: bool
    market_info: Optional[Dict]
    reason: Optional[str] = None
```

**Logic:**
- Check risk limits
- Validate symbol exists on exchange
- Check market is active
- Get market_info for later use

**Error Handling:**
- Return `ValidationResult(passed=False, reason="...")` on failure
- No exceptions thrown

---

### 3. _prepare_order_params()

**Purpose:** Calculate position size, validate balance, set leverage

**Lines:** 634-670 (~36 lines)

**Input:** `request: PositionRequest, exchange: ExchangeManager, market_info: Dict`

**Output:** `OrderParams` dataclass:
```python
@dataclass
class OrderParams:
    quantity: Decimal
    leverage: int
    position_size_usd: Decimal
    stop_loss_percent: Decimal

    @property
    def is_valid(self) -> bool:
        return self.quantity > 0
```

**Logic:**
- Calculate position size
- Check available balance
- Validate spread (log only)
- Calculate and set leverage

**Error Handling:**
- Return None on failure
- Log warnings/errors

---

### 4. _execute_and_verify_order()

**Purpose:** Execute market order and verify fill

**Lines:** 671-756 (~85 lines)

**Input:** `exchange: ExchangeManager, request: PositionRequest, params: OrderParams`

**Output:** `Order` object or None

**Logic:**
- Final check: position doesn't exist on exchange
- Convert side (long -> buy, short -> sell)
- Execute market order
- Verify order is filled (with retry)
- Validate order object

**Error Handling:**
- Return None on failure
- Log detailed errors
- Use compensating transactions if needed

---

### 5. _create_position_with_sl()

**Purpose:** Create position state and set stop loss

**Lines:** 757-791 (~34 lines)

**Input:** `request: PositionRequest, order: Order, params: OrderParams`

**Output:** `Tuple[Optional[PositionState], Optional[str]]` (position, sl_order_id)

**Logic:**
- Create PositionState object
- Calculate stop loss price
- Set stop loss on exchange
- Update position with SL info

**Error Handling:**
- Return (None, None) if SL fails
- Caller must execute compensating transaction
- Log errors

---

### 6. _save_position_to_db()

**Purpose:** Save to DB, initialize trailing stop, update tracking

**Lines:** 793-876 (~83 lines)

**Input:** `position: PositionState, exchange: ExchangeManager, order: Order`

**Output:** None (modifies position.id in place)

**Logic:**
- Create trade record
- Create position record
- Update position with SL status
- Initialize trailing stop
- Update internal tracking
- Invalidate balance cache
- Emit position_opened event

**Error Handling:**
- Raises exception on DB save failure
- Caller must execute compensating transaction

---

## 🧪 ТЕСТИРОВАНИЕ

### Strategy: Incremental Refactoring

**Step 1:** Create helper method stubs
- All helpers return mock data
- open_position() calls helpers but ignores results
- ✅ Ensure no regressions (tests still pass)

**Step 2:** Migrate logic method by method
- Move logic for _validate_signal_and_locks()
- Test open_position() still works
- Repeat for each helper

**Step 3:** Remove old code from open_position()
- Replace duplicated logic with helper calls
- Test extensively

**Step 4:** Final testing
- Unit tests for each helper
- Integration tests for open_position()
- Testnet testing

---

## 🚨 CRITICAL SAFEGUARDS

### 1. NO EXTERNAL INTERFACE CHANGES
```python
# ✅ GOOD: Same signature
async def open_position(self, request: PositionRequest) -> Optional[PositionState]:

# ❌ BAD: Changed signature
async def open_position(self, request: PositionRequest, extra_param: bool) -> Optional[PositionState]:
```

### 2. PRESERVE ALL LOCKING LOGIC
- MUST keep asyncio locks
- MUST keep PostgreSQL advisory locks
- MUST maintain lock order (prevent deadlocks)

### 3. PRESERVE COMPENSATING TRANSACTIONS
- _compensate_failed_sl()
- _compensate_failed_db_save()
- Must be called in same conditions

### 4. PRESERVE LOGGING
- Keep all logger.info/warning/error calls
- Maintain log message format (for monitoring)

### 5. PRESERVE EVENT EMISSION
- position_opened event
- Must be emitted at same point in workflow

---

## 📋 IMPLEMENTATION CHECKLIST

### Phase 1: Design & Preparation
- [x] Create design document
- [ ] Review with stakeholder
- [ ] Create dataclasses (LockInfo, ValidationResult, OrderParams)

### Phase 2: Create Helper Stubs
- [ ] _validate_signal_and_locks() - stub
- [ ] _validate_market_and_risk() - stub
- [ ] _prepare_order_params() - stub
- [ ] _execute_and_verify_order() - stub
- [ ] _create_position_with_sl() - stub
- [ ] _save_position_to_db() - stub
- [ ] Syntax check PASS
- [ ] Tests still pass (stubs don't break anything)

### Phase 3: Migrate Logic (one at a time)
- [ ] Migrate _validate_signal_and_locks()
  - [ ] Move logic from open_position
  - [ ] Update open_position to use helper
  - [ ] Test PASS
- [ ] Migrate _validate_market_and_risk()
  - [ ] Move logic
  - [ ] Update open_position
  - [ ] Test PASS
- [ ] Migrate _prepare_order_params()
  - [ ] Move logic
  - [ ] Update open_position
  - [ ] Test PASS
- [ ] Migrate _execute_and_verify_order()
  - [ ] Move logic
  - [ ] Update open_position
  - [ ] Test PASS
- [ ] Migrate _create_position_with_sl()
  - [ ] Move logic
  - [ ] Update open_position
  - [ ] Test PASS
- [ ] Migrate _save_position_to_db()
  - [ ] Move logic
  - [ ] Update open_position
  - [ ] Test PASS

### Phase 4: Cleanup & Testing
- [ ] Remove old duplicated code
- [ ] Add docstrings to all helpers
- [ ] Add type hints
- [ ] Unit tests for each helper
- [ ] Integration test for open_position()
- [ ] Health check PASS
- [ ] Testnet testing

### Phase 5: Final Review
- [ ] Code review
- [ ] Verify no regressions
- [ ] Verify logs are same
- [ ] Verify events are same
- [ ] Performance check (no slowdown)

---

## ⏱️ ESTIMATED TIME

**Phase 1:** 30 minutes (design)
**Phase 2:** 1 hour (stubs + dataclasses)
**Phase 3:** 3-4 hours (migrate logic incrementally)
**Phase 4:** 1-2 hours (cleanup + tests)
**Phase 5:** 1 hour (review)

**Total:** 6-8 hours

---

## 🎯 SUCCESS CRITERIA

- ✅ open_position() reduced from 393 lines to ~100 lines
- ✅ Each helper < 100 lines
- ✅ All tests pass
- ✅ No regressions in production behavior
- ✅ Same logging output
- ✅ Same event emission
- ✅ Code is more maintainable

---

## 🚦 GO/NO-GO DECISION

**Proceed if:**
- ✅ Design approved
- ✅ Have 6-8 hours available
- ✅ Can test on testnet
- ✅ No urgent production issues

**Defer if:**
- ❌ Not enough time
- ❌ Production issues ongoing
- ❌ Testnet unavailable

---

**Дата:** 2025-10-09
**Статус:** 🔄 AWAITING APPROVAL
**Approver:** User
