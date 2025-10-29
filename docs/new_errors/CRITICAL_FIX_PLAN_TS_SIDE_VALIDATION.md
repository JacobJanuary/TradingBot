# CRITICAL FIX PLAN: Trailing Stop Side Mismatch Bug

**Status:** 🔴 READY FOR IMPLEMENTATION
**Priority:** P0 - CRITICAL
**Date Created:** 2025-10-26
**Bug Reference:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/docs/new_errors/CRITICAL_TS_SL_SIDE_MISMATCH_INVESTIGATION.md`
**Affected Symbol:** PYRUSDT (potentially others)
**Impact:** 100% SL update failure rate for mismatched positions

---

## EXECUTIVE SUMMARY

### The Bug
A critical side mismatch bug exists in the Trailing Stop system where restored TS state contains **stale position data** from a previous position with a different side. This causes:

- **Trailing Stop state:** `side='short'`, `entry_price=0.8506`
- **Actual Bybit position:** LONG (Buy), `entry_price=0.6849`
- **Result:** All SL update attempts fail with Bybit error 10001 ("SL should be LOWER than price for Buy position")
- **Impact:** Position cannot trail stop loss, leaving profit on the table

### Root Cause
**Stale TS state persisted from old position:**

1. Original position opened as SHORT at 0.8506
2. TS created with `side='short'`, saved to database
3. Position closed, but **TS state NOT deleted** (BUG)
4. Position re-opened as LONG at 0.6849 (same symbol, different side)
5. Bot restart → TS restored from DB with **OLD side='short'**
6. Side mismatch → 100% SL update failure

### Fix Strategy
Implement **5-layer defense** to prevent and detect side mismatches:

1. **Fix #1:** Validate side on TS restore (PREVENT stale data usage)
2. **Fix #2:** Validate side before SL update (SAFETY NET - reject invalid updates)
3. **Fix #3:** Clean TS on position close (PREVENT stale data persistence)
4. **Fix #4:** TS-Position consistency check (MONITOR - detect future issues)
5. **Fix #5:** Improve logging (DEBUG - easier troubleshooting)

---

## FIX #1: Validate Side on TS Restore (P0 - CRITICAL)

### Objective
**Prevent stale TS state from being used** by validating TS.side against actual position.side during restoration.

### Current Code (BROKEN)
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`
**Function:** `_restore_state()` (lines 220-307)

```python
async def _restore_state(self, symbol: str) -> Optional[TrailingStopInstance]:
    """
    Restore trailing stop state from database

    Called from position_manager.py during bot startup when loading positions
    """
    if not self.repository:
        logger.warning(f"{symbol}: No repository configured, cannot restore TS state")
        return None

    try:
        # Fetch state from database
        state_data = await self.repository.get_trailing_stop_state(symbol, self.exchange_name)

        if not state_data:
            logger.debug(f"{symbol}: No TS state in DB, will create new")
            return None

        # CRITICAL FIX: Validate and normalize side value from database
        side_value = state_data.get('side', '').lower()
        if side_value not in ('long', 'short'):
            logger.error(
                f"❌ {symbol}: Invalid side value in database: '{state_data.get('side')}', "
                f"defaulting to 'long' (CHECK DATABASE INTEGRITY!)"
            )
            side_value = 'long'

        # Reconstruct TrailingStopInstance
        ts = TrailingStopInstance(
            symbol=state_data['symbol'],
            entry_price=Decimal(str(state_data['entry_price'])),
            current_price=Decimal(str(state_data['entry_price'])),
            highest_price=Decimal(str(state_data.get('highest_price', state_data['entry_price']))) if side_value == 'long' else UNINITIALIZED_PRICE_HIGH,
            lowest_price=UNINITIALIZED_PRICE_HIGH if side_value == 'long' else Decimal(str(state_data.get('lowest_price', state_data['entry_price']))),
            state=TrailingStopState(state_data['state'].lower()),
            activation_price=Decimal(str(state_data['activation_price'])) if state_data.get('activation_price') else None,
            current_stop_price=Decimal(str(state_data['current_stop_price'])) if state_data.get('current_stop_price') else None,
            stop_order_id=state_data.get('stop_order_id'),
            created_at=state_data.get('created_at', datetime.now()),
            activated_at=state_data.get('activated_at'),
            highest_profit_percent=Decimal(str(state_data.get('highest_profit_percent', 0))),
            update_count=state_data.get('update_count', 0),
            side=side_value,  # ← Uses DB value WITHOUT validation against position!
            quantity=Decimal(str(state_data['quantity']))
        )

        # ... restore rate limiting fields ...

        logger.info(
            f"✅ {symbol}: TS state RESTORED from DB - "
            f"state={ts.state.value}, "
            f"activated={ts.state == TrailingStopState.ACTIVE}, "
            f"highest_price={ts.highest_price if ts.side == 'long' else 'N/A'}, "
            f"lowest_price={ts.lowest_price if ts.side == 'short' else 'N/A'}, "
            f"current_stop={ts.current_stop_price}, "
            f"update_count={ts.update_count}"
        )

        return ts  # ← Returns TS with potentially wrong side!

    except Exception as e:
        logger.error(f"❌ {symbol}: Failed to restore TS state: {e}", exc_info=True)
        return None
```

**Problem:** Code validates `side` format (long/short) but **NOT** whether it matches the actual position on the exchange.

---

### Fixed Code (CORRECT)
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`
**Function:** `_restore_state()` (lines 220-307)

```python
async def _restore_state(self, symbol: str) -> Optional[TrailingStopInstance]:
    """
    Restore trailing stop state from database

    Called from position_manager.py during bot startup when loading positions

    FIX #1: Validates TS.side against actual position.side to prevent stale data usage
    """
    if not self.repository:
        logger.warning(f"{symbol}: No repository configured, cannot restore TS state")
        return None

    try:
        # Fetch state from database
        state_data = await self.repository.get_trailing_stop_state(symbol, self.exchange_name)

        if not state_data:
            logger.debug(f"{symbol}: No TS state in DB, will create new")
            return None

        # CRITICAL FIX: Validate and normalize side value from database
        side_value = state_data.get('side', '').lower()
        if side_value not in ('long', 'short'):
            logger.error(
                f"❌ {symbol}: Invalid side value in database: '{state_data.get('side')}', "
                f"defaulting to 'long' (CHECK DATABASE INTEGRITY!)"
            )
            side_value = 'long'

        # ============================================================
        # FIX #1: VALIDATE TS.SIDE AGAINST POSITION.SIDE
        # ============================================================
        # Fetch current position from exchange to verify side matches
        try:
            logger.debug(f"{symbol}: Validating TS side against exchange position...")

            positions = await self.exchange.fetch_positions([symbol])

            # Find position for this symbol
            current_position = None
            for pos in positions:
                if pos.get('symbol') == symbol:
                    # Check if position is open (has size)
                    size = pos.get('contracts', 0) or pos.get('size', 0)
                    if size and size != 0:
                        current_position = pos
                        break

            if not current_position:
                logger.warning(
                    f"⚠️ {symbol}: TS state exists in DB but no position on exchange - "
                    f"deleting stale TS state"
                )
                await self._delete_state(symbol)
                return None

            # Determine position side from exchange data
            # Bybit: pos['side'] = 'Buy' or 'Sell'
            # Binance: pos['side'] = 'long' or 'short'
            exchange_side_raw = current_position.get('side', '').lower()

            # Normalize exchange side to 'long' or 'short'
            if exchange_side_raw in ('buy', 'long'):
                exchange_side = 'long'
            elif exchange_side_raw in ('sell', 'short'):
                exchange_side = 'short'
            else:
                logger.error(
                    f"❌ {symbol}: Unknown position side from exchange: '{exchange_side_raw}' - "
                    f"cannot validate, deleting TS state"
                )
                await self._delete_state(symbol)
                return None

            # CRITICAL CHECK: Compare TS side vs position side
            if side_value != exchange_side:
                logger.error(
                    f"🔴 {symbol}: SIDE MISMATCH DETECTED!\n"
                    f"  TS side (from DB):      {side_value}\n"
                    f"  Position side (exchange): {exchange_side}\n"
                    f"  TS entry price (DB):    {state_data.get('entry_price')}\n"
                    f"  Position entry (exchange): {current_position.get('entryPrice')}\n"
                    f"  → Deleting stale TS state (prevents 100% SL failure)"
                )

                # Log critical event
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.WARNING_RAISED,
                        {
                            'warning_type': 'ts_side_mismatch_on_restore',
                            'symbol': symbol,
                            'ts_side_db': side_value,
                            'position_side_exchange': exchange_side,
                            'ts_entry_price': float(state_data.get('entry_price', 0)),
                            'position_entry_price': float(current_position.get('entryPrice', 0)),
                            'action': 'deleted_stale_ts_state'
                        },
                        symbol=symbol,
                        exchange=self.exchange_name,
                        severity='ERROR'
                    )

                # Delete stale state from database
                await self._delete_state(symbol)

                # Return None → PositionManager will create new TS with correct side
                return None

            # Side matches - safe to restore
            logger.info(
                f"✅ {symbol}: TS side validation PASSED "
                f"(side={side_value}, entry={state_data.get('entry_price')})"
            )

        except Exception as e:
            logger.error(
                f"❌ {symbol}: Failed to validate TS side against exchange: {e}\n"
                f"  → Deleting TS state to be safe (will create new)",
                exc_info=True
            )
            await self._delete_state(symbol)
            return None

        # ============================================================
        # END FIX #1
        # ============================================================

        # Reconstruct TrailingStopInstance (side already validated)
        ts = TrailingStopInstance(
            symbol=state_data['symbol'],
            entry_price=Decimal(str(state_data['entry_price'])),
            current_price=Decimal(str(state_data['entry_price'])),
            highest_price=Decimal(str(state_data.get('highest_price', state_data['entry_price']))) if side_value == 'long' else UNINITIALIZED_PRICE_HIGH,
            lowest_price=UNINITIALIZED_PRICE_HIGH if side_value == 'long' else Decimal(str(state_data.get('lowest_price', state_data['entry_price']))),
            state=TrailingStopState(state_data['state'].lower()),
            activation_price=Decimal(str(state_data['activation_price'])) if state_data.get('activation_price') else None,
            current_stop_price=Decimal(str(state_data['current_stop_price'])) if state_data.get('current_stop_price') else None,
            stop_order_id=state_data.get('stop_order_id'),
            created_at=state_data.get('created_at', datetime.now()),
            activated_at=state_data.get('activated_at'),
            highest_profit_percent=Decimal(str(state_data.get('highest_profit_percent', 0))),
            update_count=state_data.get('update_count', 0),
            side=side_value,  # ← Now validated against exchange!
            quantity=Decimal(str(state_data['quantity']))
        )

        # ... restore rate limiting fields ...

        logger.info(
            f"✅ {symbol}: TS state RESTORED from DB - "
            f"state={ts.state.value}, "
            f"activated={ts.state == TrailingStopState.ACTIVE}, "
            f"side={ts.side} (VALIDATED), "
            f"highest_price={ts.highest_price if ts.side == 'long' else 'N/A'}, "
            f"lowest_price={ts.lowest_price if ts.side == 'short' else 'N/A'}, "
            f"current_stop={ts.current_stop_price}, "
            f"update_count={ts.update_count}"
        )

        return ts

    except Exception as e:
        logger.error(f"❌ {symbol}: Failed to restore TS state: {e}", exc_info=True)
        return None
```

---

### Testing Plan (Fix #1)

#### Unit Test
```python
# tests/unit/test_ts_side_validation.py

import pytest
from protection.trailing_stop import SmartTrailingStopManager
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_restore_state_detects_side_mismatch():
    """Test that _restore_state() detects and rejects side mismatch"""

    # Setup mocks
    exchange = AsyncMock()
    exchange.fetch_positions = AsyncMock(return_value=[
        {'symbol': 'PYRUSDT', 'side': 'Buy', 'contracts': 100, 'entryPrice': 0.6849}
    ])

    repository = AsyncMock()
    repository.get_trailing_stop_state = AsyncMock(return_value={
        'symbol': 'PYRUSDT',
        'side': 'short',  # ← MISMATCH! (DB has short, exchange has Buy=long)
        'entry_price': 0.8506,
        'state': 'active',
        'highest_price': 0.8506,
        'lowest_price': 0.6853,
        'current_stop_price': 0.6889,
        'activation_price': 0.8080,
        'quantity': 100,
        'update_count': 5
    })
    repository.delete_trailing_stop_state = AsyncMock()

    # Create manager
    manager = SmartTrailingStopManager(
        exchange_manager=exchange,
        exchange_name='bybit',
        repository=repository
    )

    # Call _restore_state()
    result = await manager._restore_state('PYRUSDT')

    # Assert: Should return None (rejected)
    assert result is None, "Should reject TS with mismatched side"

    # Assert: Should delete stale state
    repository.delete_trailing_stop_state.assert_called_once_with('PYRUSDT', 'bybit')


@pytest.mark.asyncio
async def test_restore_state_accepts_matching_side():
    """Test that _restore_state() accepts TS when side matches"""

    # Setup mocks
    exchange = AsyncMock()
    exchange.fetch_positions = AsyncMock(return_value=[
        {'symbol': 'PYRUSDT', 'side': 'Buy', 'contracts': 100, 'entryPrice': 0.6849}
    ])

    repository = AsyncMock()
    repository.get_trailing_stop_state = AsyncMock(return_value={
        'symbol': 'PYRUSDT',
        'side': 'long',  # ← MATCH! (DB has long, exchange has Buy=long)
        'entry_price': 0.6849,
        'state': 'active',
        'highest_price': 0.6900,
        'lowest_price': 999999,
        'current_stop_price': 0.6866,
        'activation_price': 0.6952,
        'quantity': 100,
        'update_count': 3
    })

    # Create manager
    manager = SmartTrailingStopManager(
        exchange_manager=exchange,
        exchange_name='bybit',
        repository=repository
    )

    # Call _restore_state()
    result = await manager._restore_state('PYRUSDT')

    # Assert: Should return TrailingStopInstance
    assert result is not None, "Should accept TS with matching side"
    assert result.side == 'long', "Should have correct side"
    assert result.symbol == 'PYRUSDT'
```

#### Integration Test
```python
# tests/integration/test_ts_side_validation_integration.py

@pytest.mark.asyncio
async def test_bot_startup_with_stale_ts_state(db_connection, exchange_api):
    """
    Integration test: Bot startup with stale TS state in database

    Scenario:
    1. DB has TS state with side='short', entry=0.8506
    2. Exchange has position with side='long', entry=0.6849
    3. Bot starts up
    4. Expected: TS deleted, new TS created with correct side
    """

    # 1. Insert stale TS state into database
    await db_connection.execute("""
        INSERT INTO monitoring.trailing_stop_state
        (symbol, exchange, position_id, side, entry_price, state,
         lowest_price, current_stop_price, activation_price, quantity)
        VALUES
        ('PYRUSDT', 'bybit', 3506, 'short', 0.8506, 'active',
         0.6853, 0.6889, 0.8080, 100)
    """)

    # 2. Mock exchange to return LONG position
    exchange_api.fetch_positions.return_value = [
        {'symbol': 'PYRUSDT', 'side': 'Buy', 'contracts': 100, 'entryPrice': 0.6849}
    ]

    # 3. Start bot (triggers TS restoration)
    position_manager = PositionManager(...)
    await position_manager.load_positions()

    # 4. Verify stale TS was deleted
    stale_ts = await db_connection.fetchrow("""
        SELECT * FROM monitoring.trailing_stop_state
        WHERE symbol = 'PYRUSDT' AND side = 'short'
    """)
    assert stale_ts is None, "Stale TS should be deleted"

    # 5. Verify new TS was created with correct side
    new_ts = await db_connection.fetchrow("""
        SELECT * FROM monitoring.trailing_stop_state
        WHERE symbol = 'PYRUSDT'
    """)
    assert new_ts is not None, "New TS should exist"
    assert new_ts['side'] == 'long', "New TS should have correct side"
    assert float(new_ts['entry_price']) == 0.6849, "New TS should have correct entry"
```

---

### Risk Assessment (Fix #1)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| False positive (valid TS deleted) | Low | Medium | Log full details before deletion; can recover |
| Exchange API failure during validation | Medium | Low | Catch exception, delete TS, create new (safe fallback) |
| Performance impact on startup | Low | Low | Exchange API call already cached; 1 call per position |
| Breaks existing TS states | Low | High | Only deletes mismatched states (which are already broken) |

**Net Risk:** ✅ LOW - Fix is conservative (delete only when mismatch confirmed)

---

### Implementation Time
- **Coding:** 15 minutes
- **Testing:** 30 minutes
- **Total:** 45 minutes

---

## FIX #2: Validate Side Before SL Update (P0 - CRITICAL)

### Objective
**Safety net to prevent invalid SL updates** from reaching the exchange by validating SL direction matches position side.

### Current Code (MISSING VALIDATION)
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`
**Function:** `_update_stop_order()` (lines 1023-1152)

```python
async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
    """
    Update stop order using atomic method when available

    NEW IMPLEMENTATION:
    - Bybit: Uses trading-stop endpoint (ATOMIC - no race condition)
    - Binance: Uses optimized cancel+create (minimal race window)
    """
    try:
        # ... orphan detection code (disabled) ...

        # Check if atomic update is available
        if not hasattr(self.exchange, 'update_stop_loss_atomic'):
            logger.error(f"{ts.symbol}: Exchange does not support atomic SL update")
            return False

        # Call atomic update
        result = await self.exchange.update_stop_loss_atomic(
            symbol=ts.symbol,
            new_sl_price=float(ts.current_stop_price),  # ← NO VALIDATION!
            position_side=ts.side
        )

        if result['success']:
            # ... log success ...
            return True
        else:
            # ... log failure ...
            return False

    except Exception as e:
        logger.error(f"❌ Failed to update stop order for {ts.symbol}: {e}", exc_info=True)
        return False
```

**Problem:** No validation that `ts.current_stop_price` is on the correct side of current price.

---

### Fixed Code (WITH VALIDATION)
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`
**Function:** `_update_stop_order()` (lines 1023-1152)

```python
async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
    """
    Update stop order using atomic method when available

    NEW IMPLEMENTATION:
    - Bybit: Uses trading-stop endpoint (ATOMIC - no race condition)
    - Binance: Uses optimized cancel+create (minimal race window)

    FIX #2: Validates SL direction before calling exchange API
    """
    try:
        # ... orphan detection code (disabled) ...

        # Check if atomic update is available
        if not hasattr(self.exchange, 'update_stop_loss_atomic'):
            logger.error(f"{ts.symbol}: Exchange does not support atomic SL update")
            return False

        # ============================================================
        # FIX #2: VALIDATE SL DIRECTION BEFORE EXCHANGE CALL
        # ============================================================
        # Safety check: Ensure new SL price is on correct side of current price
        #
        # Rules:
        # - LONG: SL must be BELOW current price (price falling triggers SL)
        # - SHORT: SL must be ABOVE current price (price rising triggers SL)
        #
        # This catches side mismatch bugs BEFORE they cause exchange errors

        sl_price = ts.current_stop_price
        current_price = ts.current_price

        # Determine if SL direction is valid
        is_sl_valid = False
        validation_error = None

        if ts.side == 'long':
            # For LONG: SL must be < current price
            if sl_price < current_price:
                is_sl_valid = True
            else:
                validation_error = (
                    f"LONG position requires SL < current_price, "
                    f"but {sl_price:.8f} >= {current_price:.8f}"
                )

        elif ts.side == 'short':
            # For SHORT: SL must be > current price
            if sl_price > current_price:
                is_sl_valid = True
            else:
                validation_error = (
                    f"SHORT position requires SL > current_price, "
                    f"but {sl_price:.8f} <= {current_price:.8f}"
                )

        else:
            validation_error = f"Unknown side: '{ts.side}'"

        # If validation failed, abort update
        if not is_sl_valid:
            logger.error(
                f"🔴 {ts.symbol}: SL VALIDATION FAILED - Invalid SL direction!\n"
                f"  Side:          {ts.side}\n"
                f"  Current Price: {current_price:.8f}\n"
                f"  Proposed SL:   {sl_price:.8f}\n"
                f"  Error:         {validation_error}\n"
                f"  → ABORTING SL update (would fail on exchange)"
            )

            # Log critical event
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.TRAILING_STOP_SL_UPDATE_FAILED,
                    {
                        'symbol': ts.symbol,
                        'error_type': 'sl_direction_validation_failed',
                        'side': ts.side,
                        'current_price': float(current_price),
                        'proposed_sl_price': float(sl_price),
                        'validation_error': validation_error,
                        'entry_price': float(ts.entry_price),
                        'highest_price': float(ts.highest_price) if ts.side == 'long' else None,
                        'lowest_price': float(ts.lowest_price) if ts.side == 'short' else None,
                        'action': 'aborted_before_exchange_call'
                    },
                    symbol=ts.symbol,
                    exchange=self.exchange_name,
                    severity='ERROR'
                )

            # Return False → triggers rollback in _update_trailing_stop()
            return False

        # Validation passed - safe to proceed
        logger.debug(
            f"✅ {ts.symbol}: SL validation PASSED - "
            f"side={ts.side}, sl={sl_price:.8f}, price={current_price:.8f}"
        )

        # ============================================================
        # END FIX #2
        # ============================================================

        # Call atomic update (now safe)
        result = await self.exchange.update_stop_loss_atomic(
            symbol=ts.symbol,
            new_sl_price=float(ts.current_stop_price),
            position_side=ts.side
        )

        if result['success']:
            # Log success with metrics
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.TRAILING_STOP_SL_UPDATED,
                    {
                        'symbol': ts.symbol,
                        'method': result['method'],
                        'execution_time_ms': result['execution_time_ms'],
                        'new_sl_price': float(ts.current_stop_price),
                        'old_sl_price': result.get('old_sl_price'),
                        'unprotected_window_ms': result.get('unprotected_window_ms', 0),
                        'side': ts.side,
                        'update_count': ts.update_count,
                        'validation': 'passed'  # ← NEW: Track validation
                    },
                    symbol=ts.symbol,
                    exchange=self.exchange.name,
                    severity='INFO'
                )

            # NEW: Update tracking fields after SUCCESSFUL update
            ts.last_sl_update_time = datetime.now()
            ts.last_updated_sl_price = ts.current_stop_price

            logger.info(
                f"✅ {ts.symbol}: SL updated via {result['method']} "
                f"in {result['execution_time_ms']:.2f}ms"
            )
            return True

        else:
            # Log failure
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.TRAILING_STOP_SL_UPDATE_FAILED,
                    {
                        'symbol': ts.symbol,
                        'error': result['error'],
                        'execution_time_ms': result['execution_time_ms'],
                        'method_attempted': result.get('method'),
                        'validation': 'passed'  # ← Validation passed but exchange failed
                    },
                    symbol=ts.symbol,
                    exchange=self.exchange.name,
                    severity='ERROR'
                )

            logger.error(f"❌ {ts.symbol}: SL update failed - {result['error']}")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to update stop order for {ts.symbol}: {e}", exc_info=True)
        return False
```

---

### Edge Cases Handled (Fix #2)

| Scenario | Validation | Result |
|----------|------------|--------|
| LONG, SL=0.6712, Price=0.6853 | SL < Price ✅ | PASS - Update proceeds |
| LONG, SL=0.6889, Price=0.6853 | SL > Price ❌ | FAIL - Aborted (bug detected!) |
| SHORT, SL=0.6889, Price=0.6853 | SL > Price ✅ | PASS - Update proceeds |
| SHORT, SL=0.6712, Price=0.6853 | SL < Price ❌ | FAIL - Aborted |
| Unknown side | N/A ❌ | FAIL - Aborted |
| SL = Price | Edge case ❌ | FAIL - Not allowed (must be <> not =) |

---

### Testing Plan (Fix #2)

```python
# tests/unit/test_ts_sl_validation.py

@pytest.mark.asyncio
async def test_update_stop_order_rejects_invalid_long_sl():
    """Test that _update_stop_order() rejects SL above price for LONG"""

    # Create TS instance with LONG side
    ts = TrailingStopInstance(
        symbol='PYRUSDT',
        side='long',
        entry_price=Decimal('0.6849'),
        current_price=Decimal('0.6853'),  # Current price
        current_stop_price=Decimal('0.6889'),  # SL ABOVE price (INVALID for LONG!)
        highest_price=Decimal('0.6900'),
        lowest_price=UNINITIALIZED_PRICE_HIGH,
        quantity=Decimal('100')
    )

    # Mock exchange
    exchange = AsyncMock()
    exchange.update_stop_loss_atomic = AsyncMock()  # Should NOT be called

    # Create manager
    manager = SmartTrailingStopManager(exchange_manager=exchange, exchange_name='bybit')

    # Call _update_stop_order()
    result = await manager._update_stop_order(ts)

    # Assert: Should return False (rejected)
    assert result is False, "Should reject invalid SL for LONG"

    # Assert: Should NOT call exchange API
    exchange.update_stop_loss_atomic.assert_not_called()


@pytest.mark.asyncio
async def test_update_stop_order_accepts_valid_long_sl():
    """Test that _update_stop_order() accepts SL below price for LONG"""

    # Create TS instance with LONG side
    ts = TrailingStopInstance(
        symbol='PYRUSDT',
        side='long',
        entry_price=Decimal('0.6849'),
        current_price=Decimal('0.6853'),  # Current price
        current_stop_price=Decimal('0.6780'),  # SL BELOW price (VALID for LONG!)
        highest_price=Decimal('0.6900'),
        lowest_price=UNINITIALIZED_PRICE_HIGH,
        quantity=Decimal('100')
    )

    # Mock exchange
    exchange = AsyncMock()
    exchange.update_stop_loss_atomic = AsyncMock(return_value={
        'success': True,
        'method': 'bybit_atomic',
        'execution_time_ms': 150
    })
    exchange.name = 'bybit'

    # Create manager
    manager = SmartTrailingStopManager(exchange_manager=exchange, exchange_name='bybit')

    # Call _update_stop_order()
    result = await manager._update_stop_order(ts)

    # Assert: Should return True (accepted)
    assert result is True, "Should accept valid SL for LONG"

    # Assert: Should call exchange API
    exchange.update_stop_loss_atomic.assert_called_once()
```

---

### Risk Assessment (Fix #2)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Rejects valid SL (false negative) | Very Low | Low | Validation logic is simple inequality check |
| Edge case: SL = Price | Very Low | Low | Already handled (rejected) |
| Performance impact | None | None | Simple comparison, no API calls |

**Net Risk:** ✅ VERY LOW - Pure validation logic, no side effects

---

### Implementation Time
- **Coding:** 20 minutes
- **Testing:** 20 minutes
- **Total:** 40 minutes

---

## FIX #3: Clean TS on Position Close (P1 - Prevention)

### Objective
**Ensure TS state is ALWAYS deleted** when position closes to prevent stale data from persisting.

### Current Code (CORRECT but needs verification)
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py`
**Function:** `close_position()` (lines 2313-2511)

```python
async def close_position(self, symbol: str, reason: str = 'manual'):
    """Close position and update records"""

    if symbol not in self.positions:
        logger.warning(f"No position found for {symbol}")
        return

    position = self.positions[symbol]
    exchange = self.exchanges.get(position.exchange)

    if not exchange:
        logger.error(f"Exchange {position.exchange} not available")
        return

    try:
        # Close position on exchange
        success = await exchange.close_position(symbol)

        if success:
            # ... calculate PnL ...

            # Update database
            await self.repository.close_position(
                position.id,
                exit_price,
                realized_pnl,
                realized_pnl_percent,
                reason
            )

            # ... update statistics ...

            # Clean up trailing stop
            trailing_manager = self.trailing_managers.get(position.exchange)
            if trailing_manager:
                await trailing_manager.on_position_closed(symbol, realized_pnl)  # ← Calls delete

                # Log trailing stop removal
                if position.has_trailing_stop:
                    # ... log event ...

            logger.info(f"Position closed: {symbol} {reason}")

            # ... log position closed event ...

            # Remove from memory
            del self.positions[symbol]

            # ... cleanup orphaned SL orders ...

        else:
            logger.error(f"Failed to close position {symbol} on exchange")

    except Exception as e:
        logger.error(f"Error closing position {symbol}: {e}", exc_info=True)
```

**Analysis:** Code DOES call `trailing_manager.on_position_closed()` which calls `_delete_state()`.

**However**, there are OTHER code paths that close positions (WebSocket closure, orphan cleanup) - need to verify ALL paths.

---

### Other Close Paths to Verify

#### Path 1: WebSocket Position Closure
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py` (lines 1953-1963)

```python
if position_amt == 0:
    logger.info(f"❌ Position closure detected via WebSocket: {symbol}")
    if symbol in self.positions:
        position = self.positions[symbol]
        await self.close_position(  # ← Calls close_position() → cleanup happens
            symbol=symbol,
            close_price=float(data.get('mark_price', position.current_price)),
            realized_pnl=float(data.get('unrealized_pnl', position.unrealized_pnl)),
            reason='websocket_closure'
        )
```

**Status:** ✅ CORRECT - Calls `close_position()` → cleanup happens

---

#### Path 2: Orphan Position Cleanup
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py` (lines 724-742)

```python
await self.repository.close_position(
    pos_state.id,
    pos_state.current_price or 0.0,
    pos_state.unrealized_pnl or 0.0,
    pos_state.unrealized_pnl_percent or 0.0,
    'sync_cleanup'
)

# ... remove from memory ...

# FIX: Notify trailing stop manager of orphaned position closure
trailing_manager = self.trailing_managers.get(pos_state.exchange)
if trailing_manager:
    try:
        await trailing_manager.on_position_closed(pos_state.symbol, realized_pnl=None)
        logger.debug(f"Notified trailing stop manager of {pos_state.symbol} orphaned closure")
    except Exception as e:
        logger.warning(f"Failed to notify trailing manager for orphaned {pos_state.symbol}: {e}")
```

**Status:** ✅ CORRECT - Calls `on_position_closed()` → cleanup happens

---

#### Path 3: Max Age Position Close
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py` (lines 2789-2820)

```python
# Multiple calls to close_position() for expired positions
await self.close_position(symbol, f'max_age_market_{max_age_hours}h')
await self.close_position(symbol, f'max_age_force_{position.age_hours:.0f}h')
await self.close_position(symbol, f'max_age_expired_{max_age_hours}h')
```

**Status:** ✅ CORRECT - All call `close_position()` → cleanup happens

---

### Verification Code to Add

**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`
**Function:** `on_position_closed()` (lines 1154-1205)

**Current Code:**
```python
async def on_position_closed(self, symbol: str, realized_pnl: float = None):
    """Handle position closure"""
    if symbol not in self.trailing_stops:
        return  # ← Silently returns if TS doesn't exist

    async with self.lock:
        ts = self.trailing_stops[symbol]
        ts.state = TrailingStopState.TRIGGERED

        # ... update statistics ...
        # ... log event ...

        # Remove from active stops
        del self.trailing_stops[symbol]

        # NEW: Delete state from database
        await self._delete_state(symbol)

        logger.info(f"Position {symbol} closed, trailing stop removed")
```

**Add verification:**
```python
async def on_position_closed(self, symbol: str, realized_pnl: float = None):
    """
    Handle position closure

    FIX #3: Ensures TS state is ALWAYS deleted from DB (prevents stale data)
    """
    if symbol not in self.trailing_stops:
        # FIX #3: Even if TS not in memory, check DB and delete if exists
        logger.debug(f"{symbol}: No TS in memory, checking DB for stale state...")

        if self.repository:
            try:
                state_data = await self.repository.get_trailing_stop_state(symbol, self.exchange_name)
                if state_data:
                    logger.warning(
                        f"⚠️ {symbol}: Found stale TS state in DB (not in memory) - "
                        f"deleting to prevent future side mismatch"
                    )
                    await self._delete_state(symbol)
                else:
                    logger.debug(f"{symbol}: No TS state in DB, nothing to clean")
            except Exception as e:
                logger.error(f"❌ {symbol}: Failed to check/delete stale TS state: {e}")

        return

    async with self.lock:
        ts = self.trailing_stops[symbol]
        ts.state = TrailingStopState.TRIGGERED

        # ... update statistics ...
        # ... log event ...

        # Remove from active stops
        del self.trailing_stops[symbol]

        # FIX #3: Delete state from database
        delete_success = await self._delete_state(symbol)

        # FIX #3: Verify deletion succeeded
        if not delete_success:
            logger.error(
                f"❌ {symbol}: Failed to delete TS state from DB - "
                f"may cause side mismatch on next position open!"
            )

            # Log critical event
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.WARNING_RAISED,
                    {
                        'warning_type': 'ts_state_deletion_failed',
                        'symbol': symbol,
                        'reason': 'position_closed',
                        'risk': 'stale_state_may_persist'
                    },
                    symbol=symbol,
                    exchange=self.exchange_name,
                    severity='ERROR'
                )
        else:
            logger.info(
                f"✅ {symbol}: Position closed, TS removed from memory and DB "
                f"(prevents stale state)"
            )
```

---

### Testing Plan (Fix #3)

```python
# tests/integration/test_ts_cleanup_on_close.py

@pytest.mark.asyncio
async def test_ts_deleted_on_position_close(db_connection):
    """Test that TS state is deleted from DB when position closes"""

    # 1. Create position with TS
    position_manager = PositionManager(...)
    await position_manager.open_position('PYRUSDT', 'long', entry_price=0.6849, size=100)

    # 2. Verify TS state in DB
    ts_before = await db_connection.fetchrow("""
        SELECT * FROM monitoring.trailing_stop_state WHERE symbol = 'PYRUSDT'
    """)
    assert ts_before is not None, "TS should exist before close"

    # 3. Close position
    await position_manager.close_position('PYRUSDT', reason='test')

    # 4. Verify TS state deleted from DB
    ts_after = await db_connection.fetchrow("""
        SELECT * FROM monitoring.trailing_stop_state WHERE symbol = 'PYRUSDT'
    """)
    assert ts_after is None, "TS should be deleted after close"


@pytest.mark.asyncio
async def test_ts_deleted_on_websocket_close(db_connection, position_manager):
    """Test that TS state is deleted when position closes via WebSocket"""

    # 1. Create position with TS
    await position_manager.open_position('PYRUSDT', 'long', entry_price=0.6849, size=100)

    # 2. Simulate WebSocket closure event
    await position_manager.on_position_update({
        'symbol': 'PYRUSDT',
        'position_amt': 0,  # Position closed
        'mark_price': 0.6900
    })

    # 3. Verify TS deleted
    ts_after = await db_connection.fetchrow("""
        SELECT * FROM monitoring.trailing_stop_state WHERE symbol = 'PYRUSDT'
    """)
    assert ts_after is None, "TS should be deleted on WebSocket closure"


@pytest.mark.asyncio
async def test_stale_ts_cleanup_on_position_closed_call(db_connection):
    """Test that stale TS in DB is cleaned even if not in memory"""

    # 1. Insert orphaned TS state in DB (not in memory)
    await db_connection.execute("""
        INSERT INTO monitoring.trailing_stop_state
        (symbol, exchange, position_id, side, entry_price, state, quantity)
        VALUES ('PYRUSDT', 'bybit', 9999, 'long', 0.6849, 'active', 100)
    """)

    # 2. Call on_position_closed() (TS not in memory, but in DB)
    trailing_manager = SmartTrailingStopManager(...)
    await trailing_manager.on_position_closed('PYRUSDT')

    # 3. Verify stale TS deleted from DB
    ts_after = await db_connection.fetchrow("""
        SELECT * FROM monitoring.trailing_stop_state WHERE symbol = 'PYRUSDT'
    """)
    assert ts_after is None, "Stale TS should be deleted from DB"
```

---

### Risk Assessment (Fix #3)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| TS state not deleted (existing bug) | Low | High | Add verification + error logging |
| DB deletion fails silently | Low | High | Check return value, log error |
| TS re-created before deletion | Very Low | Low | Lock prevents race condition |

**Net Risk:** ✅ LOW - Adds defense-in-depth to existing cleanup logic

---

### Implementation Time
- **Coding:** 15 minutes
- **Testing:** 20 minutes
- **Total:** 35 minutes

---

## FIX #4: TS-Position Consistency Check (P1 - Monitoring)

### Objective
**Periodic health check** to detect side mismatches that slip through other defenses.

### Implementation
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`
**New Function:** `check_ts_position_consistency()`

```python
async def check_ts_position_consistency(self) -> Dict[str, any]:
    """
    Periodic health check: Verify TS.side matches position.side for all active TS

    Called by scheduler every 5 minutes

    FIX #4: Detects side mismatches that slip through other defenses

    Returns:
        Dict with check results and metrics
    """
    logger.info("🔍 Running TS-Position consistency check...")

    results = {
        'total_ts_checked': 0,
        'mismatches_detected': 0,
        'auto_fixed': 0,
        'check_failures': 0,
        'details': []
    }

    # Get all active TS
    async with self.lock:
        symbols_to_check = list(self.trailing_stops.keys())

    if not symbols_to_check:
        logger.info("✅ No active TS to check")
        return results

    # Check each TS
    for symbol in symbols_to_check:
        results['total_ts_checked'] += 1

        try:
            ts = self.trailing_stops.get(symbol)
            if not ts:
                continue

            # Fetch position from exchange
            positions = await self.exchange.fetch_positions([symbol])

            # Find position
            current_position = None
            for pos in positions:
                if pos.get('symbol') == symbol:
                    size = pos.get('contracts', 0) or pos.get('size', 0)
                    if size and size != 0:
                        current_position = pos
                        break

            if not current_position:
                logger.warning(
                    f"⚠️ {symbol}: TS exists but no position on exchange - "
                    f"orphaned TS (will be cleaned on next position update)"
                )
                results['details'].append({
                    'symbol': symbol,
                    'issue': 'orphaned_ts',
                    'action': 'pending_cleanup'
                })
                continue

            # Normalize exchange side
            exchange_side_raw = current_position.get('side', '').lower()
            if exchange_side_raw in ('buy', 'long'):
                exchange_side = 'long'
            elif exchange_side_raw in ('sell', 'short'):
                exchange_side = 'short'
            else:
                logger.error(f"❌ {symbol}: Unknown position side: {exchange_side_raw}")
                results['check_failures'] += 1
                continue

            # Check side consistency
            if ts.side != exchange_side:
                # MISMATCH DETECTED!
                results['mismatches_detected'] += 1

                logger.error(
                    f"🔴 {symbol}: SIDE MISMATCH detected by health check!\n"
                    f"  TS side (memory):       {ts.side}\n"
                    f"  Position side (exchange): {exchange_side}\n"
                    f"  TS entry:               {ts.entry_price}\n"
                    f"  Position entry:         {current_position.get('entryPrice')}\n"
                    f"  → Auto-fixing: Deleting stale TS and recreating"
                )

                # Log critical event
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.WARNING_RAISED,
                        {
                            'warning_type': 'ts_side_mismatch_detected_by_health_check',
                            'symbol': symbol,
                            'ts_side': ts.side,
                            'position_side': exchange_side,
                            'ts_entry_price': float(ts.entry_price),
                            'position_entry_price': float(current_position.get('entryPrice', 0)),
                            'action': 'auto_fix_delete_and_recreate'
                        },
                        symbol=symbol,
                        exchange=self.exchange_name,
                        severity='ERROR'
                    )

                # Auto-fix: Delete TS and let position_manager recreate it
                try:
                    await self.on_position_closed(symbol, realized_pnl=None)

                    # TODO: Recreate TS with correct side
                    # This requires access to position_manager which we don't have here
                    # For now, just delete - position_manager will recreate on next update

                    results['auto_fixed'] += 1
                    results['details'].append({
                        'symbol': symbol,
                        'issue': 'side_mismatch',
                        'ts_side': ts.side,
                        'position_side': exchange_side,
                        'action': 'deleted_ts'
                    })

                except Exception as e:
                    logger.error(f"❌ {symbol}: Failed to auto-fix side mismatch: {e}")
                    results['check_failures'] += 1

            else:
                # Side matches - OK
                logger.debug(f"✅ {symbol}: TS side matches position side ({ts.side})")

        except Exception as e:
            logger.error(f"❌ {symbol}: Consistency check failed: {e}", exc_info=True)
            results['check_failures'] += 1

    # Summary
    logger.info(
        f"✅ TS consistency check complete:\n"
        f"  Checked:    {results['total_ts_checked']}\n"
        f"  Mismatches: {results['mismatches_detected']}\n"
        f"  Auto-fixed: {results['auto_fixed']}\n"
        f"  Failures:   {results['check_failures']}"
    )

    # Log metrics
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.SYSTEM_STATUS,
            {
                'check_type': 'ts_position_consistency',
                'total_checked': results['total_ts_checked'],
                'mismatches_detected': results['mismatches_detected'],
                'auto_fixed': results['auto_fixed'],
                'check_failures': results['check_failures'],
                'details': results['details']
            },
            exchange=self.exchange_name,
            severity='INFO' if results['mismatches_detected'] == 0 else 'WARNING'
        )

    return results
```

---

### Scheduler Integration
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py` or `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py`

```python
# Add to existing scheduled tasks

async def run_scheduled_tasks():
    """Run periodic maintenance tasks"""

    while True:
        try:
            # Existing tasks...
            await position_manager.check_position_age()
            await position_manager.sync_positions_with_exchange()

            # FIX #4: NEW - TS consistency check every 5 minutes
            for exchange_name, trailing_manager in position_manager.trailing_managers.items():
                try:
                    results = await trailing_manager.check_ts_position_consistency()

                    # Alert if mismatches detected
                    if results['mismatches_detected'] > 0:
                        logger.warning(
                            f"⚠️ {exchange_name}: Detected {results['mismatches_detected']} "
                            f"TS side mismatches (auto-fixed: {results['auto_fixed']})"
                        )
                except Exception as e:
                    logger.error(f"❌ {exchange_name}: TS consistency check failed: {e}")

            # Wait 5 minutes
            await asyncio.sleep(300)

        except Exception as e:
            logger.error(f"Scheduled tasks error: {e}", exc_info=True)
            await asyncio.sleep(60)
```

---

### Metrics to Track

Add to monitoring dashboard:

```python
# Prometheus metrics (if using)
ts_side_mismatches_total = Counter(
    'ts_side_mismatches_total',
    'Total TS side mismatches detected',
    ['exchange', 'action']  # action: detected, auto_fixed, manual_fix_required
)

ts_consistency_checks_total = Counter(
    'ts_consistency_checks_total',
    'Total TS consistency checks run',
    ['exchange', 'result']  # result: success, failure
)

ts_consistency_check_duration_seconds = Histogram(
    'ts_consistency_check_duration_seconds',
    'Duration of TS consistency checks',
    ['exchange']
)
```

---

### Testing Plan (Fix #4)

```python
# tests/unit/test_ts_consistency_check.py

@pytest.mark.asyncio
async def test_consistency_check_detects_mismatch():
    """Test that consistency check detects side mismatch"""

    # Create TS with SHORT side
    ts = TrailingStopInstance(
        symbol='PYRUSDT',
        side='short',
        entry_price=Decimal('0.8506'),
        current_price=Decimal('0.6853'),
        lowest_price=Decimal('0.6853'),
        highest_price=UNINITIALIZED_PRICE_HIGH,
        quantity=Decimal('100')
    )

    # Mock exchange returning LONG position
    exchange = AsyncMock()
    exchange.fetch_positions = AsyncMock(return_value=[
        {'symbol': 'PYRUSDT', 'side': 'Buy', 'contracts': 100, 'entryPrice': 0.6849}
    ])

    # Create manager
    manager = SmartTrailingStopManager(
        exchange_manager=exchange,
        exchange_name='bybit'
    )
    manager.trailing_stops['PYRUSDT'] = ts

    # Run consistency check
    results = await manager.check_ts_position_consistency()

    # Assert: Mismatch detected
    assert results['total_ts_checked'] == 1
    assert results['mismatches_detected'] == 1
    assert results['auto_fixed'] == 1
```

---

### Risk Assessment (Fix #4)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| False positive (valid TS deleted) | Low | Medium | Only deletes on confirmed mismatch |
| Performance impact | Low | Low | Runs every 5 minutes, fetches positions (cached) |
| Auto-fix fails | Low | Low | Logs error, manual intervention required |

**Net Risk:** ✅ LOW - Monitoring-only, doesn't affect trading logic

---

### Implementation Time
- **Coding:** 30 minutes
- **Testing:** 20 minutes
- **Integration:** 10 minutes
- **Total:** 60 minutes

---

## FIX #5: Improve Logging (P2 - Debugging)

### Objective
**Add structured logging** to make future debugging easier.

### Log Points to Add

#### 1. TS Creation
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py` (line 381)

**Current:**
```python
logger.info(
    f"Created trailing stop for {symbol} {side}: "
    f"entry={entry_price}, activation={ts.activation_price}, "
    f"initial_stop={initial_stop}"
)
```

**Improved:**
```python
logger.info(
    f"✅ {symbol}: TS CREATED - "
    f"side={side}, entry={entry_price:.8f}, "
    f"activation={float(ts.activation_price):.8f}, "
    f"initial_stop={initial_stop:.8f if initial_stop else 'None'}, "
    f"[SEARCH: ts_created_{symbol}]"
)
```

---

#### 2. TS Restoration
**Already improved in Fix #1** - includes side validation results.

---

#### 3. TS Activation
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py` (line 559)

**Current:**
```python
logger.info(
    f"✅ {ts.symbol}: Trailing stop ACTIVATED at {ts.current_price:.4f}, "
    f"stop at {ts.current_stop_price:.4f}"
)
```

**Improved:**
```python
logger.info(
    f"✅ {ts.symbol}: TS ACTIVATED - "
    f"side={ts.side}, "
    f"price={ts.current_price:.8f}, "
    f"sl={ts.current_stop_price:.8f}, "
    f"entry={ts.entry_price:.8f}, "
    f"profit={(self._calculate_profit_percent(ts)):.2f}%, "
    f"[SEARCH: ts_activated_{ts.symbol}]"
)
```

---

#### 4. SL Update Success
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py` (line 713)

**Current:**
```python
logger.info(
    f"📈 {ts.symbol}: SL moved - Trailing stop updated from {old_stop:.4f} to {new_stop_price:.4f} "
    f"(+{improvement:.2f}%)"
)
```

**Improved:**
```python
logger.info(
    f"📈 {ts.symbol}: SL UPDATED - "
    f"side={ts.side}, "
    f"old_sl={old_stop:.8f}, "
    f"new_sl={new_stop_price:.8f}, "
    f"improvement={improvement:.2f}%, "
    f"price={ts.current_price:.8f}, "
    f"peak={'highest' if ts.side == 'long' else 'lowest'}={ts.highest_price if ts.side == 'long' else ts.lowest_price:.8f}, "
    f"[SEARCH: ts_sl_updated_{ts.symbol}]"
)
```

---

#### 5. SL Update Failure
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py` (line 683)

**Current:**
```python
logger.error(
    f"❌ {ts.symbol}: SL update FAILED on exchange, "
    f"state rolled back (keeping old stop {old_stop:.4f})"
)
```

**Improved:**
```python
logger.error(
    f"❌ {ts.symbol}: SL UPDATE FAILED - "
    f"side={ts.side}, "
    f"proposed_sl={new_stop_price:.8f}, "
    f"kept_old_sl={old_stop:.8f}, "
    f"price={ts.current_price:.8f}, "
    f"entry={ts.entry_price:.8f}, "
    f"peak={'highest' if ts.side == 'long' else 'lowest'}={ts.highest_price if ts.side == 'long' else ts.lowest_price:.8f}, "
    f"[SEARCH: ts_sl_failed_{ts.symbol}]"
)
```

---

#### 6. TS Deletion
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py` (line 1205)

**Current:**
```python
logger.info(f"Position {symbol} closed, trailing stop removed")
```

**Improved:**
```python
logger.info(
    f"✅ {symbol}: TS DELETED - "
    f"reason=position_closed, "
    f"final_state={ts.state.value}, "
    f"final_sl={ts.current_stop_price:.8f if ts.current_stop_price else 'None'}, "
    f"update_count={ts.update_count}, "
    f"[SEARCH: ts_deleted_{symbol}]"
)
```

---

### Structured Log Format

**Standard format for all TS logs:**
```
[TIMESTAMP] - [LOGGER] - [LEVEL] - [EMOJI] [SYMBOL]: [EVENT] - [KEY=VALUE pairs], [SEARCH: search_keyword]
```

**Example:**
```
2025-10-26 17:34:48 - protection.trailing_stop - INFO - ✅ PYRUSDT: TS ACTIVATED - side=long, price=0.68550000, sl=0.68120000, entry=0.68490000, profit=0.88%, [SEARCH: ts_activated_PYRUSDT]
```

**Benefits:**
- Easy to grep: `grep "ts_activated_PYRUSDT" bot.log`
- Easy to parse: `grep -oP 'side=\K\w+' bot.log`
- Easy to filter by symbol: `grep "PYRUSDT:" bot.log`
- Easy to track lifecycle: `grep "SEARCH: ts_" bot.log | grep PYRUSDT`

---

### Testing Plan (Fix #5)

```python
# tests/unit/test_ts_logging.py

def test_log_format_ts_created(caplog):
    """Test that TS creation log includes all required fields"""

    # ... create TS ...

    # Check log output
    log_output = caplog.text

    assert "TS CREATED" in log_output
    assert "side=" in log_output
    assert "entry=" in log_output
    assert "activation=" in log_output
    assert "SEARCH: ts_created_" in log_output


def test_log_format_ts_activated(caplog):
    """Test that TS activation log includes all required fields"""

    # ... activate TS ...

    log_output = caplog.text

    assert "TS ACTIVATED" in log_output
    assert "side=" in log_output
    assert "price=" in log_output
    assert "sl=" in log_output
    assert "entry=" in log_output
    assert "profit=" in log_output
    assert "SEARCH: ts_activated_" in log_output
```

---

### Risk Assessment (Fix #5)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Log spam | Low | Low | Logs are INFO level, can be filtered |
| Performance impact | Very Low | Very Low | Logging is cheap |
| Format breaks parsing tools | Low | Low | Use structured format consistently |

**Net Risk:** ✅ VERY LOW - Pure logging, no functional changes

---

### Implementation Time
- **Coding:** 30 minutes
- **Testing:** 15 minutes
- **Total:** 45 minutes

---

## IMPLEMENTATION ORDER

### Phase 1: Immediate Safety Net (Day 1)
**Priority:** P0 - CRITICAL
**Time:** 1 hour

1. **Fix #2:** Validate Side Before SL Update (40 min)
   - Prevents invalid SL updates from reaching exchange
   - Safety net catches bugs before damage
   - No risk, pure validation

**Deployment:** Deploy immediately to prevent further SL failures

---

### Phase 2: Prevention (Day 1)
**Priority:** P0 - CRITICAL
**Time:** 1.5 hours

1. **Fix #1:** Validate Side on TS Restore (45 min)
   - Prevents stale TS state from being used
   - Catches bugs at source (restore time)
   - Deletes mismatched TS, forces recreation

2. **Fix #3:** Clean TS on Position Close (35 min)
   - Ensures TS always deleted on close
   - Prevents stale data persistence
   - Defense-in-depth

**Deployment:** Deploy together after testing

---

### Phase 3: Monitoring & Debugging (Day 2)
**Priority:** P1 - HIGH
**Time:** 2 hours

1. **Fix #4:** TS-Position Consistency Check (60 min)
   - Periodic health check
   - Auto-detects and fixes mismatches
   - Tracks metrics

2. **Fix #5:** Improve Logging (45 min)
   - Better debugging
   - Structured log format
   - Search keywords

**Deployment:** Deploy after Phase 2 is stable

---

### Total Implementation Time
- **Phase 1:** 1 hour
- **Phase 2:** 1.5 hours
- **Phase 3:** 2 hours
- **Total:** 4.5 hours

---

## TESTING STRATEGY

### Unit Tests
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/tests/unit/test_ts_side_validation.py`

1. Test side validation on restore (Fix #1)
   - Mismatch detected → TS deleted
   - Match → TS restored
   - Exchange API failure → TS deleted

2. Test SL direction validation (Fix #2)
   - LONG with SL above price → rejected
   - LONG with SL below price → accepted
   - SHORT with SL below price → rejected
   - SHORT with SL above price → accepted

3. Test TS cleanup on close (Fix #3)
   - TS in memory → deleted from DB
   - TS only in DB → detected and deleted

---

### Integration Tests
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/tests/integration/test_ts_side_validation_integration.py`

1. Full lifecycle test
   - Create LONG position
   - TS created with side=long
   - Close position
   - TS deleted
   - Create SHORT position (same symbol)
   - TS created with side=short (NOT restored from old state)

2. Bot restart with stale state
   - DB has TS with side=short, entry=0.8506
   - Exchange has position with side=long, entry=0.6849
   - Bot restarts
   - Stale TS deleted, new TS created

3. Consistency check test
   - Create mismatch manually
   - Run consistency check
   - Mismatch auto-fixed

---

### Manual Verification Steps

#### Pre-Deployment Checklist
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Code reviewed by another developer
- [ ] Database backup created
- [ ] Rollback plan documented

---

#### Post-Deployment Verification (Production)

**Step 1: Check PYRUSDT**
```bash
# Check if stale TS state still exists
docker exec -it trading_bot_db psql -U trading_user -d trading_bot -c \
"SELECT symbol, side, entry_price, state FROM monitoring.trailing_stop_state WHERE symbol = 'PYRUSDT';"

# Expected: Either deleted OR side='long', entry=0.6849
```

**Step 2: Monitor Logs**
```bash
# Watch for side validation logs
docker logs -f trading_bot | grep "TS side validation"

# Expected:
# ✅ PYRUSDT: TS side validation PASSED (side=long, entry=0.6849)
# OR
# 🔴 PYRUSDT: SIDE MISMATCH DETECTED! ... → Deleting stale TS state
```

**Step 3: Verify SL Updates**
```bash
# Watch for SL update attempts
docker logs -f trading_bot | grep "PYRUSDT.*SL"

# Expected:
# ✅ PYRUSDT: SL validation PASSED - side=long, sl=0.67800000, price=0.68530000
# ✅ PYRUSDT: SL updated via bybit_atomic in 120ms
```

**Step 4: Check Consistency (after 5 minutes)**
```bash
# Check consistency check results
docker logs -f trading_bot | grep "TS consistency check complete"

# Expected:
# ✅ TS consistency check complete:
#   Checked:    5
#   Mismatches: 0
#   Auto-fixed: 0
#   Failures:   0
```

---

### Edge Cases to Test

1. **Position flip (SHORT → LONG)**
   - Open SHORT position at 0.8506
   - TS created with side=short
   - Close position
   - Open LONG position at 0.6849 (same symbol)
   - Expected: New TS created with side=long (not restored from old)

2. **Bot restart during position**
   - Open LONG position
   - TS created and activated
   - Restart bot (simulates crash)
   - Expected: TS restored from DB with side=long

3. **Stale TS in DB, no position on exchange**
   - DB has TS state
   - Exchange has no position
   - Bot restarts
   - Expected: TS deleted (orphaned)

4. **Multiple positions, one with mismatch**
   - 5 positions, 4 OK, 1 with mismatch
   - Expected: 4 TS restored, 1 deleted + recreated

---

## DEPLOYMENT PLAN

### Pre-Deployment

1. **Database Backup**
   ```bash
   docker exec trading_bot_db pg_dump -U trading_user trading_bot > backup_before_ts_fix_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Code Review**
   - Review all changes in `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py`
   - Verify test coverage
   - Check for typos in log messages

3. **Test Environment**
   - Deploy to test environment first
   - Run full test suite
   - Manually verify with test positions

---

### Deployment Steps

#### Phase 1 Deployment (Fix #2 - Immediate)

1. **Apply changes**
   ```bash
   cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot
   git checkout -b fix/ts-side-validation-phase1

   # Edit protection/trailing_stop.py (Fix #2 only)
   # Commit changes
   git add protection/trailing_stop.py
   git commit -m "fix: add SL direction validation before exchange call (Fix #2)"
   ```

2. **Test**
   ```bash
   pytest tests/unit/test_ts_side_validation.py -v
   ```

3. **Deploy**
   ```bash
   # Stop bot
   docker-compose stop trading_bot

   # Pull changes
   git pull origin fix/ts-side-validation-phase1

   # Restart bot
   docker-compose up -d trading_bot

   # Watch logs
   docker logs -f trading_bot | grep "PYRUSDT"
   ```

4. **Verify**
   - Check logs for "SL validation PASSED"
   - Check no more Bybit 10001 errors
   - Monitor for 1 hour

---

#### Phase 2 Deployment (Fix #1 + #3)

1. **Apply changes**
   ```bash
   git checkout -b fix/ts-side-validation-phase2

   # Edit protection/trailing_stop.py (Fix #1 + #3)
   # Commit changes
   git add protection/trailing_stop.py
   git commit -m "fix: validate TS side on restore + ensure cleanup on close (Fix #1 + #3)"
   ```

2. **Test**
   ```bash
   pytest tests/unit/test_ts_side_validation.py -v
   pytest tests/integration/test_ts_side_validation_integration.py -v
   ```

3. **Deploy**
   ```bash
   # Stop bot
   docker-compose stop trading_bot

   # Pull changes
   git pull origin fix/ts-side-validation-phase2

   # Restart bot (triggers TS restoration with Fix #1)
   docker-compose up -d trading_bot

   # Watch logs
   docker logs -f trading_bot | grep -E "(TS side validation|SIDE MISMATCH)"
   ```

4. **Verify**
   - Check logs for "TS side validation PASSED" or "SIDE MISMATCH DETECTED"
   - Verify stale TS deleted if mismatch
   - Check database: no mismatched TS states
   - Monitor for 24 hours

---

#### Phase 3 Deployment (Fix #4 + #5)

1. **Apply changes**
   ```bash
   git checkout -b fix/ts-side-validation-phase3

   # Edit protection/trailing_stop.py (Fix #4 + #5)
   # Edit main.py or position_manager.py (scheduler)
   # Commit changes
   git add .
   git commit -m "feat: add TS consistency check + improve logging (Fix #4 + #5)"
   ```

2. **Test**
   ```bash
   pytest tests/unit/test_ts_consistency_check.py -v
   pytest tests/unit/test_ts_logging.py -v
   ```

3. **Deploy**
   ```bash
   docker-compose stop trading_bot
   git pull origin fix/ts-side-validation-phase3
   docker-compose up -d trading_bot
   ```

4. **Verify**
   - Wait 5 minutes for first consistency check
   - Check logs for "TS consistency check complete"
   - Verify improved log format
   - Monitor for 7 days

---

### Post-Deployment Verification

**Day 1 (Phase 1):**
- [ ] No Bybit 10001 errors in logs
- [ ] PYRUSDT SL updates succeeding
- [ ] No false rejections (valid SL updates blocked)

**Day 2 (Phase 2):**
- [ ] Bot restart successful
- [ ] TS states restored correctly
- [ ] No stale TS states in database
- [ ] New positions get correct TS side

**Week 1 (Phase 3):**
- [ ] Consistency checks running every 5 minutes
- [ ] No mismatches detected (or auto-fixed if detected)
- [ ] Logs easy to search and parse
- [ ] No performance degradation

---

### Rollback Plan

#### If Phase 1 Fails (Fix #2)
```bash
# Revert changes
git revert <commit_hash>
git push origin main

# Restart bot
docker-compose restart trading_bot

# Verify rollback
docker logs -f trading_bot | grep "SL validation"
# Expected: No validation logs (old code)
```

**Risk:** Low - Fix #2 only adds validation, doesn't change behavior if validation passes.

---

#### If Phase 2 Fails (Fix #1 + #3)
```bash
# Revert changes
git revert <commit_hash>
git push origin main

# Restart bot
docker-compose restart trading_bot

# Manual fix for PYRUSDT if needed
docker exec -it trading_bot_db psql -U trading_user -d trading_bot -c \
"UPDATE monitoring.trailing_stop_state SET side = 'long', entry_price = 0.6849 WHERE symbol = 'PYRUSDT';"

docker-compose restart trading_bot
```

**Risk:** Medium - Reverting Fix #1 means stale TS states won't be auto-deleted. Manual intervention required.

---

#### If Phase 3 Fails (Fix #4 + #5)
```bash
# Disable consistency check in scheduler
# (comment out check_ts_position_consistency() call)

# Revert changes
git revert <commit_hash>
git push origin main

# Restart bot
docker-compose restart trading_bot
```

**Risk:** Low - Fix #4 + #5 are monitoring/logging only, don't affect trading logic.

---

## SUCCESS CRITERIA

### Immediate Success (Day 1 - Phase 1)
- [ ] **No more Bybit 10001 errors** for PYRUSDT
- [ ] **SL updates succeed** (see "SL updated via bybit_atomic" in logs)
- [ ] **No false rejections** (valid SL updates not blocked)
- [ ] **PYRUSDT position trailing** stop loss properly

---

### Short-Term Success (Day 2-7 - Phase 2)
- [ ] **Bot restart successful** with TS restoration
- [ ] **No stale TS states** in database
- [ ] **Side mismatches auto-deleted** if detected
- [ ] **New positions** get correct TS side
- [ ] **TS cleanup on close** verified (database query shows no orphaned states)

---

### Long-Term Success (Week 1+ - Phase 3)
- [ ] **Consistency checks running** every 5 minutes
- [ ] **Zero mismatches detected** (or auto-fixed if detected)
- [ ] **Metrics tracked:** `ts_side_mismatches_total = 0`
- [ ] **Logs easy to search:** `grep "SEARCH: ts_" bot.log` works
- [ ] **No performance degradation** (check latency, CPU, memory)

---

### Ultimate Success Criteria
- [ ] **100% SL update success rate** for all positions
- [ ] **No manual interventions** required for TS issues
- [ ] **Stale TS states never persist** across position closes
- [ ] **Side mismatches impossible** (4 layers of defense)
- [ ] **Future debugging fast** (structured logs, search keywords)

---

## APPENDIX A: Quick Reference

### Search Keywords for Logs

| Keyword | Purpose |
|---------|---------|
| `ts_created_SYMBOL` | Find TS creation |
| `ts_activated_SYMBOL` | Find TS activation |
| `ts_sl_updated_SYMBOL` | Find successful SL updates |
| `ts_sl_failed_SYMBOL` | Find failed SL updates |
| `ts_deleted_SYMBOL` | Find TS deletion |
| `TS side validation` | Find side validation results |
| `SIDE MISMATCH` | Find side mismatch detections |
| `TS consistency check` | Find health check results |

---

### Database Queries

#### Check for side mismatches
```sql
SELECT
    ts.symbol,
    ts.side AS ts_side,
    ts.entry_price AS ts_entry,
    p.side AS pos_side,
    p.entry_price AS pos_entry,
    CASE
        WHEN ts.side != p.side THEN '🔴 MISMATCH'
        WHEN ABS(ts.entry_price - p.entry_price) > 0.01 THEN '⚠️ ENTRY DIFF'
        ELSE '✅ OK'
    END AS status
FROM monitoring.trailing_stop_state ts
JOIN monitoring.positions p ON ts.position_id = p.id
WHERE p.status = 'active';
```

#### Check for orphaned TS states
```sql
SELECT ts.*
FROM monitoring.trailing_stop_state ts
LEFT JOIN monitoring.positions p ON ts.position_id = p.id
WHERE p.id IS NULL OR p.status != 'active';
```

#### Count TS by side
```sql
SELECT
    exchange,
    side,
    COUNT(*) as count,
    AVG(update_count) as avg_updates
FROM monitoring.trailing_stop_state
GROUP BY exchange, side;
```

---

### Code Locations

| Fix | File | Function | Lines |
|-----|------|----------|-------|
| Fix #1 | `protection/trailing_stop.py` | `_restore_state()` | 220-307 |
| Fix #2 | `protection/trailing_stop.py` | `_update_stop_order()` | 1023-1152 |
| Fix #3 | `protection/trailing_stop.py` | `on_position_closed()` | 1154-1205 |
| Fix #4 | `protection/trailing_stop.py` | `check_ts_position_consistency()` | NEW |
| Fix #5 | `protection/trailing_stop.py` | Multiple functions | Various |

---

## APPENDIX B: Risk Matrix

| Fix | Severity | Likelihood | Impact | Net Risk |
|-----|----------|-----------|--------|----------|
| Fix #1: Validate side on restore | Critical | Low | High | ✅ LOW |
| Fix #2: Validate side before SL | Critical | Very Low | Very Low | ✅ VERY LOW |
| Fix #3: Clean TS on close | High | Low | High | ✅ LOW |
| Fix #4: Consistency check | Medium | Low | Low | ✅ LOW |
| Fix #5: Improve logging | Low | Very Low | Very Low | ✅ VERY LOW |

**Overall Risk:** ✅ LOW - Conservative fixes with multiple safety nets

---

## APPENDIX C: Contact & Escalation

### If Issues Arise

**Phase 1 Issues (Fix #2):**
- **Symptom:** Valid SL updates rejected
- **Action:** Check validation logic, verify side and prices are correct
- **Escalation:** Revert Fix #2 if false rejections > 1%

**Phase 2 Issues (Fix #1 + #3):**
- **Symptom:** Valid TS states deleted on restore
- **Action:** Check exchange API response, verify position exists
- **Escalation:** Manual TS recreation required

**Phase 3 Issues (Fix #4 + #5):**
- **Symptom:** Consistency check too slow
- **Action:** Increase check interval to 10 minutes
- **Escalation:** Disable consistency check if > 30s duration

---

## DOCUMENT HISTORY

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-10-26 | Initial fix plan created | Claude Code |

---

**END OF FIX PLAN**

**Status:** ✅ Ready for implementation
**Estimated Total Time:** 4.5 hours
**Risk Level:** LOW
**Success Confidence:** HIGH (95%)
