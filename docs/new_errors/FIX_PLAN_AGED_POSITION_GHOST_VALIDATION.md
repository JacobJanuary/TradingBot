# FIX PLAN: Aged Position Ghost Validation
**Date**: 2025-10-26
**Priority**: P1 - HIGH
**Estimated Effort**: 3-4 hours
**Risk Level**: LOW
**Status**: 📋 READY FOR IMPLEMENTATION

---

## Problem Summary

Age модуль пытается закрыть позиции, которых уже нет на бирже, получая misleading ошибку "Insufficient balance" (Bybit error 170131). Это приводит к 26+ повторным попыткам в течение 40 минут.

**Root Cause**: Нет валидации существования позиции на бирже перед попыткой закрытия.

---

## Solution Overview

**Approach**: Добавить проверку позиции на бирже ПЕРЕД попыткой закрытия.

**Philosophy**: "Measure twice, cut once" - сначала проверяем, потом закрываем.

**Phases**:
1. Phase 1: Add position validation before close (CRITICAL)
2. Phase 2: Improve error handling for 170131 (IMPORTANT)
3. Phase 3: Add periodic aged position validation (NICE TO HAVE)

---

## PHASE 1: Position Validation Before Close

### 🎯 Objective

Перед попыткой закрытия aged позиции:
1. Проверить что позиция существует на бирже
2. Если НЕТ → пометить как "ghost position", закрыть в БД, НЕ пытаться закрыть на бирже
3. Если ЕСТЬ → проверить quantity совпадает, использовать exchange value

### 📝 Changes Required

#### Change 1: Add helper method `_validate_position_on_exchange()`

**File**: `core/aged_position_monitor_v2.py`
**Location**: After `__init__`, before existing methods (around line 100)
**Lines to add**: ~50

**Code**:
```python
async def _validate_position_on_exchange(self, position) -> tuple[bool, float, str]:
    """
    Validate position exists on exchange and get current quantity.

    Args:
        position: Position object from database

    Returns:
        tuple: (exists: bool, quantity: float, error_msg: str)
            exists=True if position found on exchange
            quantity=actual quantity from exchange (0 if not found)
            error_msg=error description if validation failed
    """
    symbol = position.symbol
    exchange_name = position.exchange

    try:
        # Get exchange manager
        exchange = self.position_manager.exchange_managers.get(exchange_name)
        if not exchange:
            error_msg = f"Exchange {exchange_name} not found in managers"
            logger.error(f"❌ {symbol}: {error_msg}")
            return (False, 0.0, error_msg)

        # Fetch positions from exchange
        try:
            positions = await exchange.exchange.fetch_positions([symbol])
        except Exception as fetch_error:
            # If fetch fails, log but don't block close attempt
            error_msg = f"Failed to fetch positions: {fetch_error}"
            logger.warning(f"⚠️ {symbol}: {error_msg}")
            # Return None to indicate "unknown" state
            return (None, 0.0, error_msg)

        # Find active position (non-zero contracts)
        active_position = None
        for p in positions:
            contracts = float(p.get('contracts', 0))
            if contracts != 0:
                active_position = p
                break

        if not active_position:
            # Position NOT found on exchange
            logger.warning(
                f"🔍 {symbol}: Position NOT FOUND on exchange "
                f"(DB shows {position.quantity}, but exchange shows 0)"
            )
            return (False, 0.0, "Position not found on exchange")

        # Position exists, get quantity
        exchange_qty = abs(float(active_position.get('contracts', 0)))
        db_qty = abs(float(position.quantity))

        # Check quantity mismatch
        qty_diff = abs(exchange_qty - db_qty)
        if qty_diff > 0.01:  # Allow 0.01 difference for rounding
            logger.warning(
                f"⚠️ {symbol}: Quantity MISMATCH detected!\n"
                f"   Exchange: {exchange_qty}\n"
                f"   Database: {db_qty}\n"
                f"   Difference: {qty_diff}\n"
                f"   → Will use EXCHANGE quantity for close"
            )
        else:
            logger.debug(
                f"✅ {symbol}: Position validated on exchange "
                f"(qty={exchange_qty})"
            )

        return (True, exchange_qty, "")

    except Exception as e:
        error_msg = f"Unexpected error during validation: {e}"
        logger.error(
            f"❌ {symbol}: {error_msg}",
            exc_info=True
        )
        # Return None to indicate "unknown" state
        return (None, 0.0, error_msg)
```

**Key Design Decisions**:
- Returns tuple `(exists, quantity, error_msg)`
- `exists=None` means "unknown" (validation failed, proceed with caution)
- `exists=False` means "confirmed not found" (don't attempt close)
- `exists=True` means "confirmed exists" (safe to close)
- Quantity from exchange takes precedence over DB

---

#### Change 2: Add helper method `_mark_position_as_ghost()`

**File**: `core/aged_position_monitor_v2.py`
**Location**: After `_validate_position_on_exchange()`
**Lines to add**: ~40

**Code**:
```python
async def _mark_position_as_ghost(self, position, reason: str = "ghost_detected_aged_close"):
    """
    Mark position as closed in database (ghost position cleanup).

    Args:
        position: Position object from database
        reason: Reason for ghost detection
    """
    symbol = position.symbol

    try:
        # Close position in database
        await self.repository.close_position(
            position_id=position.id,
            exit_price=position.entry_price,  # Use entry as exit (unknown actual)
            exit_reason=reason,
            realized_pnl=Decimal('0')  # Unknown actual PnL
        )

        logger.info(
            f"✅ {symbol}: Ghost position closed in database\n"
            f"   Position ID: {position.id}\n"
            f"   Entry price: {position.entry_price}\n"
            f"   Reason: {reason}"
        )

        # Update statistics
        if hasattr(self, 'stats'):
            if 'ghost_positions_detected' not in self.stats:
                self.stats['ghost_positions_detected'] = 0
            self.stats['ghost_positions_detected'] += 1

        # Remove from aged_targets if present
        if symbol in self.aged_targets:
            del self.aged_targets[symbol]
            logger.debug(f"🗑️ {symbol}: Removed from aged_targets")

        # Emit event
        await self.event_logger.log_event(
            'aged_ghost_position_detected',
            {
                'symbol': symbol,
                'exchange': position.exchange,
                'position_id': position.id,
                'entry_price': float(position.entry_price),
                'quantity': float(position.quantity),
                'reason': reason
            }
        )

    except Exception as e:
        logger.error(
            f"❌ {symbol}: Failed to mark ghost position in database: {e}",
            exc_info=True
        )
        raise  # Re-raise to caller
```

**Key Design Decisions**:
- Uses `exit_price = entry_price` (actual exit price unknown)
- Uses `realized_pnl = 0` (actual PnL unknown)
- Updates statistics for monitoring
- Emits event for tracking
- Removes from aged_targets to stop monitoring

---

#### Change 3: Modify `_trigger_market_close()` to use validation

**File**: `core/aged_position_monitor_v2.py`
**Function**: `_trigger_market_close()`
**Location**: Lines 300-360 (approximately)
**Lines to modify**: ~20 (surgical changes)

**Current code** (lines 300-320):
```python
async def _trigger_market_close(self, position, target, trigger_price):
    """Execute robust close order for aged position using OrderExecutor"""

    symbol = position.symbol
    exchange_name = position.exchange
    amount = abs(float(position.quantity))

    logger.info(
        f"📤 Triggering robust close for aged {symbol}: "
        f"amount={amount}, phase={target.phase}"
    )

    # Use OrderExecutor for robust execution
    try:
        result = await self.order_executor.execute_close(
            symbol=symbol,
            exchange_name=exchange_name,
            position_side=position.side,
            amount=amount,
            reason=f'aged_{target.phase}'
        )
```

**New code**:
```python
async def _trigger_market_close(self, position, target, trigger_price):
    """Execute robust close order for aged position using OrderExecutor"""

    symbol = position.symbol
    exchange_name = position.exchange

    logger.info(
        f"📤 Triggering robust close for aged {symbol}: "
        f"phase={target.phase}"
    )

    # === NEW: VALIDATE POSITION EXISTS ON EXCHANGE ===
    exists, exchange_qty, error_msg = await self._validate_position_on_exchange(position)

    if exists is False:
        # Position confirmed NOT FOUND on exchange - GHOST POSITION
        logger.warning(
            f"⚠️ {symbol}: GHOST POSITION detected! "
            f"Position exists in DB but NOT on exchange. "
            f"Marking as closed in database (no exchange close needed)."
        )

        try:
            await self._mark_position_as_ghost(position, "ghost_detected_aged_close")

            # Update statistics
            self.stats['ghost_positions_handled'] = self.stats.get('ghost_positions_handled', 0) + 1

            logger.info(
                f"✅ {symbol}: Ghost position handled successfully "
                f"(closed in DB, no exchange action taken)"
            )

            # Remove from monitoring
            if symbol in self.aged_targets:
                del self.aged_targets[symbol]

            return  # EXIT - don't attempt close on exchange

        except Exception as ghost_error:
            logger.error(
                f"❌ {symbol}: Failed to handle ghost position: {ghost_error}",
                exc_info=True
            )
            # Continue to attempt close (fallback behavior)

    elif exists is None:
        # Validation FAILED (API error, timeout, etc.)
        logger.warning(
            f"⚠️ {symbol}: Position validation FAILED: {error_msg}\n"
            f"   → Proceeding with close attempt using DB values (fallback mode)"
        )
        amount = abs(float(position.quantity))

    else:
        # Position EXISTS on exchange (exists=True)
        logger.info(
            f"✅ {symbol}: Position validated on exchange (qty={exchange_qty})"
        )
        amount = exchange_qty

    # === END NEW CODE ===

    # Continue with original close logic
    try:
        result = await self.order_executor.execute_close(
            symbol=symbol,
            exchange_name=exchange_name,
            position_side=position.side,
            amount=amount,  # Now uses validated exchange quantity
            reason=f'aged_{target.phase}'
        )
```

**Key Design Decisions**:
- Three outcomes: `False` (ghost), `None` (unknown), `True` (exists)
- Ghost positions: mark as closed in DB, EXIT early (no exchange close)
- Unknown state: proceed with DB values (fallback, logged as warning)
- Valid positions: use exchange quantity
- Minimal changes to existing flow (surgical precision)

---

#### Change 4: Add statistics tracking

**File**: `core/aged_position_monitor_v2.py`
**Function**: `__init__()`
**Location**: Lines 40-70 (approximately, in stats initialization)

**Add to stats dictionary**:
```python
self.stats = {
    'total_aged': 0,
    'grace_closes': 0,
    'progressive_closes': 0,
    'market_closes_triggered': 0,
    'failed_closes': 0,
    # NEW stats:
    'ghost_positions_detected': 0,        # Total ghosts found
    'ghost_positions_handled': 0,         # Successfully handled ghosts
    'position_validation_failures': 0,    # Validation API failures
    'quantity_mismatches': 0,             # DB vs Exchange qty differences
}
```

**Update stats in validation code**:
```python
# In _validate_position_on_exchange():
if qty_diff > 0.01:
    self.stats['quantity_mismatches'] = self.stats.get('quantity_mismatches', 0) + 1

# In _validate_position_on_exchange() when validation fails:
if exists is None:
    self.stats['position_validation_failures'] = self.stats.get('position_validation_failures', 0) + 1
```

---

### ✅ Summary of Phase 1 Changes

**Files Modified**: 1
- `core/aged_position_monitor_v2.py` (~120 lines added, ~20 lines modified)

**New Methods**: 2
- `_validate_position_on_exchange()` - Validates position exists on exchange
- `_mark_position_as_ghost()` - Marks ghost position as closed in DB

**Modified Methods**: 1
- `_trigger_market_close()` - Adds validation before close attempt

**Statistics Added**: 4
- `ghost_positions_detected`
- `ghost_positions_handled`
- `position_validation_failures`
- `quantity_mismatches`

**Total Lines**: ~140 new, ~20 modified

---

## PHASE 2: Improve Error Handling for 170131

### 🎯 Objective

Улучшить обработку ошибки Bybit 170131 ("Insufficient balance") чтобы различать:
1. Реальную проблему баланса
2. Попытку закрыть несуществующую позицию

### 📝 Changes Required

#### Change 1: Add error classification in `order_executor.py`

**File**: `core/order_executor.py`
**Function**: `execute_close()`
**Location**: Lines 220-250 (approximately, in exception handling)

**Current error handling**:
```python
except Exception as e:
    error_msg = str(e)
    last_error = error_msg

    # Check if permanent error
    if self._is_permanent_error(error_msg):
        logger.error(f"❌ PERMANENT ERROR detected - stopping retries: {error_msg[:200]}")
        break
```

**Enhanced error handling**:
```python
except Exception as e:
    error_msg = str(e)
    last_error = error_msg

    # === NEW: Special handling for "Insufficient balance" error ===
    if '170131' in error_msg or 'Insufficient balance' in error_msg.lower():
        logger.warning(
            f"⚠️ {symbol}: Received 'Insufficient balance' error (170131). "
            f"This might indicate position doesn't exist on exchange."
        )

        # Try to verify if position exists
        try:
            positions = await exchange.exchange.fetch_positions([symbol])
            active_position = next(
                (p for p in positions if float(p.get('contracts', 0)) != 0),
                None
            )

            if not active_position:
                # CONFIRMED: Position doesn't exist
                logger.error(
                    f"❌ {symbol}: CONFIRMED - Position NOT FOUND on exchange!\n"
                    f"   Error 170131 was actually 'position not found', not balance issue.\n"
                    f"   Cannot close non-existent position."
                )

                # Return special result
                return OrderResult(
                    success=False,
                    order_id=None,
                    order_type='validation_failed',
                    price=None,
                    executed_amount=Decimal('0'),
                    error_message="Position not found on exchange (170131 detected as ghost)",
                    error_code="POSITION_NOT_FOUND",
                    attempts=total_attempts,
                    execution_time=time.time() - start_time
                )
            else:
                # Position EXISTS - this is REAL balance issue
                logger.error(
                    f"❌ {symbol}: CONFIRMED - Real insufficient balance issue!\n"
                    f"   Position exists (qty={float(active_position.get('contracts', 0))})\n"
                    f"   but account balance insufficient for this operation.\n"
                    f"   This is a CRITICAL issue requiring manual investigation."
                )

        except Exception as verify_error:
            logger.warning(
                f"⚠️ {symbol}: Could not verify position existence: {verify_error}\n"
                f"   Treating 170131 as permanent error (stopping retries)"
            )
    # === END NEW CODE ===

    # Check if permanent error
    if self._is_permanent_error(error_msg):
        logger.error(f"❌ PERMANENT ERROR detected - stopping retries: {error_msg[:200]}")
        break
```

**Key Design Decisions**:
- Detects error 170131 or "Insufficient balance" text
- Proactively verifies position existence
- If NOT found → returns special error code `POSITION_NOT_FOUND`
- If FOUND → logs as CRITICAL (real balance issue)
- If verification fails → treats as permanent error (safe default)

---

#### Change 2: Add new error code to OrderResult

**File**: `core/order_executor.py`
**Class**: `OrderResult` (dataclass)
**Location**: Lines 20-40 (approximately)

**Add new field**:
```python
@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str]
    order_type: str
    price: Optional[Decimal]
    executed_amount: Optional[Decimal]
    error_message: Optional[str]
    error_code: Optional[str] = None  # NEW: e.g., "POSITION_NOT_FOUND", "INSUFFICIENT_BALANCE"
    attempts: int = 0
    execution_time: float = 0.0
```

---

### ✅ Summary of Phase 2 Changes

**Files Modified**: 1
- `core/order_executor.py` (~40 lines added, ~5 lines modified)

**New Fields**: 1
- `OrderResult.error_code` - Structured error classification

**Enhanced Error Handling**: 1
- Better classification of 170131 errors

**Total Lines**: ~45 new/modified

---

## PHASE 3: Periodic Aged Position Validation

### 🎯 Objective

Добавить фоновую задачу, которая периодически проверяет все aged позиции на существование на бирже (каждые 5 минут). Это предотвратит накопление ghost positions и обнаружит их быстрее, чем sync_cleanup.

### 📝 Changes Required

#### Change 1: Add periodic validation task

**File**: `core/aged_position_monitor_v2.py`
**Function**: NEW `_periodic_position_validation_task()`
**Location**: After other helper methods, before `start()`

**Code**:
```python
async def _periodic_position_validation_task(self):
    """
    Background task: Periodically validate aged positions exist on exchange.
    Runs every 5 minutes.
    """
    logger.info("🔄 Starting periodic aged position validation task (interval: 5 min)")

    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes

            # Get current aged positions
            aged_symbols = list(self.aged_targets.keys())

            if not aged_symbols:
                logger.debug("No aged positions to validate")
                continue

            logger.info(
                f"🔍 Running periodic validation for {len(aged_symbols)} aged positions"
            )

            ghosts_detected = 0
            validation_errors = 0

            for symbol in aged_symbols:
                try:
                    # Get position from position_manager
                    position = self.position_manager.positions.get(symbol)
                    if not position:
                        logger.debug(f"⚠️ {symbol}: Not found in position_manager (already closed?)")
                        # Remove from aged_targets
                        if symbol in self.aged_targets:
                            del self.aged_targets[symbol]
                        continue

                    # Validate position on exchange
                    exists, exchange_qty, error_msg = await self._validate_position_on_exchange(position)

                    if exists is False:
                        # GHOST DETECTED
                        logger.warning(
                            f"🔍 Periodic validation: GHOST POSITION detected for {symbol}!\n"
                            f"   Aged position exists in DB but NOT on exchange.\n"
                            f"   Cleaning up immediately."
                        )

                        await self._mark_position_as_ghost(
                            position,
                            reason="ghost_detected_periodic_validation"
                        )

                        ghosts_detected += 1

                    elif exists is None:
                        # Validation failed
                        logger.debug(
                            f"⚠️ {symbol}: Periodic validation failed: {error_msg}"
                        )
                        validation_errors += 1

                    else:
                        # Position valid
                        logger.debug(f"✅ {symbol}: Validated (qty={exchange_qty})")

                except Exception as symbol_error:
                    logger.error(
                        f"❌ {symbol}: Error during periodic validation: {symbol_error}",
                        exc_info=True
                    )
                    validation_errors += 1

            # Log summary
            if ghosts_detected > 0 or validation_errors > 0:
                logger.info(
                    f"🔍 Periodic validation complete: "
                    f"{len(aged_symbols)} checked, "
                    f"{ghosts_detected} ghosts detected, "
                    f"{validation_errors} validation errors"
                )

        except Exception as e:
            logger.error(
                f"❌ Error in periodic aged position validation task: {e}",
                exc_info=True
            )
            # Continue running despite errors
```

---

#### Change 2: Start periodic validation task

**File**: `core/aged_position_monitor_v2.py`
**Function**: `start()`
**Location**: Lines 150-180 (approximately)

**Current code**:
```python
async def start(self):
    """Start the aged position monitor"""
    logger.info("🔄 Starting AgedPositionMonitor...")

    # Start periodic scan task
    self.scan_task = asyncio.create_task(self._periodic_scan())

    logger.info("✅ AgedPositionMonitor started")
```

**New code**:
```python
async def start(self):
    """Start the aged position monitor"""
    logger.info("🔄 Starting AgedPositionMonitor...")

    # Start periodic scan task
    self.scan_task = asyncio.create_task(self._periodic_scan())

    # NEW: Start periodic validation task
    self.validation_task = asyncio.create_task(self._periodic_position_validation_task())

    logger.info("✅ AgedPositionMonitor started (scan + validation tasks)")
```

---

#### Change 3: Stop periodic validation task

**File**: `core/aged_position_monitor_v2.py`
**Function**: `stop()`
**Location**: After `start()`

**Current code**:
```python
async def stop(self):
    """Stop the aged position monitor"""
    if self.scan_task:
        self.scan_task.cancel()
        try:
            await self.scan_task
        except asyncio.CancelledError:
            pass

    logger.info("✅ AgedPositionMonitor stopped")
```

**New code**:
```python
async def stop(self):
    """Stop the aged position monitor"""
    if self.scan_task:
        self.scan_task.cancel()
        try:
            await self.scan_task
        except asyncio.CancelledError:
            pass

    # NEW: Stop validation task
    if hasattr(self, 'validation_task') and self.validation_task:
        self.validation_task.cancel()
        try:
            await self.validation_task
        except asyncio.CancelledError:
            pass

    logger.info("✅ AgedPositionMonitor stopped (all tasks cancelled)")
```

---

### ✅ Summary of Phase 3 Changes

**Files Modified**: 1
- `core/aged_position_monitor_v2.py` (~80 lines added, ~10 lines modified)

**New Methods**: 1
- `_periodic_position_validation_task()` - Background validation task

**Modified Methods**: 2
- `start()` - Starts validation task
- `stop()` - Stops validation task

**Total Lines**: ~90 new/modified

---

## Testing Plan

### Test Suite 1: Ghost Position Detection

#### Test 1.1: Ghost Position Before Close
**Setup**:
1. Open position TESTUSDT on Bybit (10 contracts)
2. Close it manually via Bybit UI
3. Wait for aged position trigger

**Expected**:
- `_validate_position_on_exchange()` returns `(False, 0.0, "Position not found")`
- Ghost detected, marked in DB
- NO close attempt on exchange
- Log: "GHOST POSITION detected! ... Marking as closed in database"
- Statistics: `ghost_positions_detected += 1`

**Pass Criteria**:
- ✅ No error 170131 in logs
- ✅ Position closed in DB with reason="ghost_detected_aged_close"
- ✅ NO exchange API close calls
- ✅ Stats updated correctly

---

#### Test 1.2: Quantity Mismatch (Partial Close)
**Setup**:
1. Open position TESTUSDT (100 contracts)
2. Manually close 50 contracts via UI
3. Trigger aged close

**Expected**:
- Validation detects mismatch: DB=100, Exchange=50
- Log: "Quantity MISMATCH detected! ... Will use EXCHANGE quantity"
- Close attempts with amount=50 (not 100)
- Statistics: `quantity_mismatches += 1`

**Pass Criteria**:
- ✅ Uses exchange quantity (50) for close
- ✅ Close succeeds with correct amount
- ✅ Mismatch logged
- ✅ Stats updated

---

#### Test 1.3: Validation API Failure
**Setup**:
1. Mock `fetch_positions()` to raise exception
2. Trigger aged close

**Expected**:
- Validation returns `(None, 0.0, "Failed to fetch...")`
- Log: "Position validation FAILED: ... Proceeding with DB values (fallback)"
- Close attempts with DB quantity
- Statistics: `position_validation_failures += 1`

**Pass Criteria**:
- ✅ Doesn't crash
- ✅ Falls back to DB values
- ✅ Attempts close (may fail, but logged correctly)
- ✅ Stats updated

---

#### Test 1.4: Normal Aged Close (Happy Path)
**Setup**:
1. Open aged position
2. Let it age naturally
3. Trigger aged close

**Expected**:
- Validation confirms position exists
- Log: "Position validated on exchange (qty=...)"
- Close proceeds normally
- NO additional delays

**Pass Criteria**:
- ✅ Works same as before fix
- ✅ No performance degradation
- ✅ Close succeeds

---

### Test Suite 2: Error 170131 Handling (Phase 2)

#### Test 2.1: Error 170131 for Ghost Position
**Setup**:
1. Force aged close to fail with error 170131
2. Ensure position doesn't exist on exchange

**Expected**:
- Enhanced error handler detects 170131
- Verification confirms position not found
- Returns `OrderResult` with `error_code="POSITION_NOT_FOUND"`
- Log: "CONFIRMED - Position NOT FOUND on exchange!"

**Pass Criteria**:
- ✅ Error code correctly identified
- ✅ Position verified as non-existent
- ✅ No retries after confirmation
- ✅ Clear log message

---

#### Test 2.2: Error 170131 for Real Balance Issue
**Setup**:
1. Reduce Bybit balance to insufficient level
2. Trigger aged close for existing position

**Expected**:
- Enhanced error handler detects 170131
- Verification confirms position DOES exist
- Log: "CONFIRMED - Real insufficient balance issue! ... CRITICAL"
- Stops retries (permanent error)

**Pass Criteria**:
- ✅ Distinguishes real balance issue
- ✅ Logs as CRITICAL
- ✅ No false "ghost" detection

---

### Test Suite 3: Periodic Validation (Phase 3)

#### Test 3.1: Periodic Ghost Detection
**Setup**:
1. Open 3 aged positions
2. Close 1 manually via UI
3. Wait 5+ minutes

**Expected**:
- Validation task runs every 5 min
- Detects closed position as ghost
- Marks as closed in DB
- Removes from aged_targets
- Log: "Periodic validation: GHOST POSITION detected!"

**Pass Criteria**:
- ✅ Ghost detected within 5 minutes
- ✅ Cleaned up automatically
- ✅ Other 2 positions unaffected
- ✅ Stats: `ghost_positions_detected += 1`

---

#### Test 3.2: Multiple Ghosts Detection
**Setup**:
1. Open 5 aged positions
2. Close 3 manually via UI
3. Wait for periodic validation

**Expected**:
- Validation detects all 3 ghosts
- All marked as closed
- Log: "3 ghosts detected"
- Stats: `ghost_positions_detected += 3`

**Pass Criteria**:
- ✅ All ghosts detected in single pass
- ✅ All cleaned up
- ✅ 2 valid positions remain

---

#### Test 3.3: Validation Task Resilience
**Setup**:
1. Mock API to fail intermittently
2. Let validation task run

**Expected**:
- Task continues despite errors
- Logs errors but doesn't crash
- Continues on next interval

**Pass Criteria**:
- ✅ Task doesn't crash
- ✅ Errors logged
- ✅ Next validation attempt succeeds

---

### Test Suite 4: Integration Tests

#### Test 4.1: Full Workflow with Ghost
**Setup**:
1. Open position
2. Close manually
3. Wait for age trigger

**Expected**:
- Age monitor triggers close
- Phase 1 validation detects ghost
- Position closed in DB
- NO exchange API call
- Removed from monitoring

**Pass Criteria**:
- ✅ End-to-end works
- ✅ No 170131 errors
- ✅ Clean logs

---

#### Test 4.2: Full Workflow with Mismatch
**Setup**:
1. Open 100 contracts
2. Close 50 manually
3. Age trigger

**Expected**:
- Validation detects mismatch
- Uses 50 for close
- Close succeeds
- Position fully closed

**Pass Criteria**:
- ✅ Correct quantity used
- ✅ Close successful
- ✅ DB updated correctly

---

#### Test 4.3: Performance Test
**Setup**:
1. 10 aged positions
2. All valid (exist on exchange)
3. Trigger multiple closes

**Expected**:
- Validation adds <500ms per close
- No significant performance impact
- All closes succeed

**Pass Criteria**:
- ✅ Validation overhead <500ms
- ✅ No timeouts
- ✅ All closes successful

---

## Implementation Order

### Step 1: Phase 1 - Core Validation (Day 1)
**Time**: 2 hours

1. Create branch: `fix/aged-position-ghost-validation`
2. Add `_validate_position_on_exchange()` method
3. Add `_mark_position_as_ghost()` method
4. Modify `_trigger_market_close()` to use validation
5. Add statistics tracking
6. Run Test Suite 1 (Ghost Detection Tests)

**Acceptance Criteria**:
- ✅ All Test Suite 1 tests pass
- ✅ No regressions in normal flow
- ✅ Ghost positions handled correctly

---

### Step 2: Phase 2 - Error Handling (Day 1-2)
**Time**: 1 hour

1. Add `error_code` field to `OrderResult`
2. Enhance 170131 error handling in `execute_close()`
3. Run Test Suite 2 (Error Handling Tests)

**Acceptance Criteria**:
- ✅ All Test Suite 2 tests pass
- ✅ 170131 errors correctly classified
- ✅ Real vs ghost balance issues distinguished

---

### Step 3: Phase 3 - Periodic Validation (Day 2)
**Time**: 1 hour

1. Add `_periodic_position_validation_task()` method
2. Modify `start()` and `stop()` methods
3. Run Test Suite 3 (Periodic Validation Tests)

**Acceptance Criteria**:
- ✅ All Test Suite 3 tests pass
- ✅ Validation task runs continuously
- ✅ Ghosts detected proactively

---

### Step 4: Integration Testing (Day 2)
**Time**: 1 hour

1. Run full Test Suite 4 (Integration Tests)
2. Performance testing
3. Log analysis
4. Documentation review

**Acceptance Criteria**:
- ✅ All integration tests pass
- ✅ Performance acceptable
- ✅ Logs clear and helpful
- ✅ Documentation complete

---

### Step 5: Code Review & Merge (Day 2-3)
**Time**: 30 minutes

1. Self-review code
2. Run ALL tests again
3. Check for any breaking changes
4. Create commit with detailed message
5. Push to origin

**Acceptance Criteria**:
- ✅ Code follows project style
- ✅ No breaking changes
- ✅ Tests comprehensive
- ✅ Commit message clear

---

## Rollback Plan

### If Critical Issue Discovered

**Scenario 1**: Validation causes close failures
- **Action**: Revert Phase 1 changes
- **Command**: `git revert <commit-hash>`
- **Fallback**: System reverts to original behavior (no validation)

**Scenario 2**: Performance degradation
- **Action**: Disable periodic validation (Phase 3)
- **Command**: Comment out `validation_task` creation in `start()`
- **Fallback**: Manual validation only (Phase 1 + 2 remain active)

**Scenario 3**: API rate limiting issues
- **Action**: Increase validation interval
- **Change**: `await asyncio.sleep(300)` → `await asyncio.sleep(600)` (10 min)

---

## Monitoring & Alerting

### Metrics to Monitor

**Existing Prometheus metrics** (add to):
```python
# In aged_position_monitor_v2.py
aged_ghost_positions_total = Counter('aged_ghost_positions_total', 'Total ghost positions detected')
aged_position_validation_failures_total = Counter('aged_position_validation_failures_total', 'Position validation API failures')
aged_quantity_mismatches_total = Counter('aged_quantity_mismatches_total', 'Position quantity mismatches detected')
aged_close_validation_duration_seconds = Histogram('aged_close_validation_duration_seconds', 'Time spent validating position before close')
```

**Stats to track** (in `self.stats`):
- `ghost_positions_detected`
- `ghost_positions_handled`
- `position_validation_failures`
- `quantity_mismatches`

---

### Log Patterns to Watch

**Success patterns**:
```
"Position validated on exchange"
"Ghost position handled successfully"
"Periodic validation complete"
```

**Warning patterns**:
```
"GHOST POSITION detected"
"Quantity MISMATCH detected"
"Position validation FAILED"
```

**Critical patterns** (should NOT appear after fix):
```
"170131.*Insufficient balance"  # Should be caught by Phase 2
"Failed to close aged position after 3 attempts.*170131"  # Should be prevented by Phase 1
```

---

### Alerts

**Alert 1: Ghost Positions Accumulating**
```yaml
- alert: AgedGhostPositionsDetected
  expr: increase(aged_ghost_positions_total[1h]) > 5
  severity: warning
  message: "More than 5 ghost positions detected in last hour"
```

**Alert 2: Validation Failures**
```yaml
- alert: AgedPositionValidationFailures
  expr: increase(aged_position_validation_failures_total[15m]) > 10
  severity: critical
  message: "High rate of position validation failures"
```

**Alert 3: Quantity Mismatches**
```yaml
- alert: AgedQuantityMismatches
  expr: increase(aged_quantity_mismatches_total[1h]) > 3
  severity: warning
  message: "Frequent position quantity mismatches detected"
```

---

## Risk Assessment

### Implementation Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Validation adds latency | Medium | Low | Async, timeout, fallback to DB |
| API rate limiting | Low | Medium | Cache, 5min interval, graceful handling |
| False ghost detection | Low | High | Careful validation logic, logs |
| Missed real balance issues | Very Low | High | Phase 2 distinguishes real vs ghost |
| Breaking change | Very Low | Critical | Comprehensive tests, no API changes |

### Runtime Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Exchange API down | Low | Medium | Fallback to DB values, log warning |
| WebSocket lag | Medium | Low | Periodic validation (Phase 3) catches |
| Database sync issues | Low | Medium | Stats tracking, monitoring |

---

## Success Criteria

### Functional Requirements

✅ **FR1**: Ghost positions detected before close attempt
✅ **FR2**: No 170131 errors for ghost positions
✅ **FR3**: Quantity mismatches handled correctly
✅ **FR4**: Real balance issues distinguished from ghosts
✅ **FR5**: Periodic validation runs reliably

### Non-Functional Requirements

✅ **NFR1**: Validation adds <500ms latency
✅ **NFR2**: No increase in API rate limit errors
✅ **NFR3**: Clear, actionable log messages
✅ **NFR4**: Comprehensive statistics tracking
✅ **NFR5**: No breaking changes to existing API

### Business Requirements

✅ **BR1**: Eliminates misleading error logs
✅ **BR2**: Improves operational efficiency
✅ **BR3**: Prevents wasted API calls
✅ **BR4**: Enhances monitoring visibility
✅ **BR5**: Reduces manual intervention needs

---

## Post-Implementation Review

### After 24 Hours

**Check**:
1. Stats: `ghost_positions_detected` count
2. Logs: No 170131 errors for aged closes
3. Metrics: Validation duration
4. Alerts: Any triggered?

**Success**: If ghost_positions_detected > 0 AND no 170131 errors

---

### After 7 Days

**Check**:
1. Total ghosts detected
2. Validation failure rate
3. Quantity mismatch frequency
4. User feedback

**Action**: Adjust validation interval if needed

---

## Documentation Updates

### Files to Update

1. **README.md** (if exists):
   - Add section on ghost position handling

2. **CHANGELOG.md**:
```markdown
## [Unreleased]

### Added
- Position validation before aged position close attempts
- Ghost position detection and automatic cleanup
- Enhanced error 170131 handling (distinguishes ghost vs real balance)
- Periodic validation task for aged positions (5 min interval)

### Fixed
- Issue where aged position monitor attempted to close non-existent positions
- Misleading "Insufficient balance" errors for already-closed positions
- Delay in detecting closed positions (reduced from 40+ min to <5 min)

### Changed
- Age monitor now validates position exists on exchange before close attempt
- Uses exchange quantity instead of DB quantity for closes (more accurate)
```

3. **API Documentation** (if exists):
   - Document new `error_code` field in `OrderResult`
   - Document new statistics fields

---

## Conclusion

**Total Effort**: 3-4 hours (implementation) + 1 hour (testing) = 4-5 hours

**Risk Level**: LOW (defensive changes, comprehensive fallbacks)

**Impact**: HIGH (eliminates major operational issue)

**Ready to Proceed**: ✅ YES

**Next Step**: Begin implementation Phase 1

---

**Plan Author**: Claude Code
**Plan Date**: 2025-10-26
**Plan Status**: ✅ APPROVED - Ready for implementation
