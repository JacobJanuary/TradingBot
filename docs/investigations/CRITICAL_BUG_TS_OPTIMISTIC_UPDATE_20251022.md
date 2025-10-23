# 🔴 КРИТИЧЕСКИЙ БАГ: Trailing Stop Optimistic State Update приводит к DB-Exchange расхождению

**Дата**: 2025-10-22 06:44
**Статус**: ✅ РАССЛЕДОВАНО - Найден критический баг
**Приоритет**: P0 - КРИТИЧЕСКИЙ
**Влияние**: ВСЕ позиции с trailing stop, особенно на волатильных рынках

---

## 📋 EXECUTIVE SUMMARY

**Ошибка**: `binance {"code":-2021,"msg":"Order would immediately trigger."}`

**Вывод**: Это **КРИТИЧЕСКИЙ БАГ В КОДЕ** - Optimistic state update!

**Root Cause**:
Trailing Stop Manager обновляет `current_stop_price` в памяти и БД **ДО того** как биржа подтвердит успешное обновление SL. Если биржа отклоняет обновление (из-за волатильности цены), state в БД расходится с реальным SL на бирже.

**Consequence**:
- БД содержит новый stop (e.g., $3.290)
- Биржа имеет старый stop (e.g., $3.1766 initial protection)
- После restart бот пытается синхронизировать БД→Exchange
- ERROR -2021 если цена откатила ниже stop из БД

**Fix Required**:
Изменить с **OPTIMISTIC** на **PESSIMISTIC** update - обновлять state ТОЛЬКО после подтверждения биржи.

---

## 🔍 ДЕТАЛЬНЫЙ АНАЛИЗ

### 1. Симптомы проблемы

**Pattern в логах** (КЛЮЧЕВОЕ ДОКАЗАТЕЛЬСТВО):
```
06:11:47 - 📈 APTUSDT: SL moved - updated from 3.2825 to 3.2827 (+0.01%)
06:11:47 - ❌ APTUSDT: SL update failed - "Order would immediately trigger"

06:13:12 - 📈 APTUSDT: SL moved - updated from 3.2827 to 3.2832 (+0.02%)
06:13:12 - ❌ APTUSDT: SL update failed - "Order would immediately trigger"

06:14:49 - 📈 APTUSDT: SL moved - updated from 3.2871 to 3.2877 (+0.02%)
06:14:49 - ❌ APTUSDT: SL update failed - "Order would immediately trigger"

06:15:21 - 📈 APTUSDT: SL moved - updated from 3.2887 to 3.2890 (+0.01%)
06:15:21 - ❌ APTUSDT: SL update failed - "Order would immediately trigger"
```

**Smoking Gun**:
- Код логирует "SL moved" (успех) → потом ERROR!
- Это означает state обновлен **ДО** попытки обновления на бирже!

---

### 2. Timeline событий

#### PHASE 1: Normal operation (05:11 - 06:15)

```
05:11:34 - TS ACTIVATED at $3.2904, stop at $3.2739
           Initial protection SL on exchange: $3.1766

05:12:11 - Price rises → TS tries to update stop to $3.2740
           ✅ Updated in memory & DB
           ❌ FAILED on exchange (ERROR -2021)

05:55:44 - TS tries to update stop to $3.2745
           ✅ Updated in memory & DB
           ❌ FAILED on exchange (ERROR -2021)

... (десятки попыток) ...

06:15:21 - TS tries to update stop to $3.2890 (highest)
           ✅ Updated in memory & DB  ← БД содержит $3.289!
           ❌ FAILED on exchange       ← Биржа имеет $3.1766!
```

**Result after 1+ hour**:
- БД state: `current_stop_price = 3.2890`
- Exchange reality: SL order at $3.1766 (initial protection)
- **РАСХОЖДЕНИЕ**: БД ahead на ~3.4%!

#### PHASE 2: Price drops (06:15 - 06:44)

```
06:15:21 - Price at highest: $3.305
           ...
06:44:19 - Price dropped to: $3.2334 (down 2.2%)
```

#### PHASE 3: Bot restart (~06:44)

```
06:44:14 - Bot RESTARTED
           TS state RESTORED from DB:
             current_stop_price: 3.2890  ← From DB (optimistic)

06:44:19 - Position update: mark_price=3.2334

06:44:20 - TS tries to sync DB→Exchange:
           1. Cancel old SL: stopPrice=3.1766 (initial protection) ✅
           2. Create new SL: stopPrice=3.2890 ❌

06:44:20 - ERROR -2021: "Order would immediately trigger"
           Reason: Stop ($3.289) > Market ($3.233) for LONG
```

---

### 3. Root Cause Analysis

#### Проблемный код

**File**: `protection/trailing_stop.py`
**Method**: `_update_trailing_stop()`
**Lines**: 640-690

```python
async def _update_trailing_stop(self, ts: TrailingStopInstance) -> Optional[Dict]:
    """Update trailing stop if price moved favorably"""

    # Calculate new stop
    distance = self._get_trailing_distance(ts)

    if ts.side == 'long':
        potential_stop = ts.highest_price * (1 - distance / 100)

        if potential_stop > ts.current_stop_price:
            new_stop_price = potential_stop
    # ...

    if new_stop_price:
        old_stop = ts.current_stop_price

        # ❌ БАГ #1: OPTIMISTIC UPDATE - State modified BEFORE exchange confirms!
        # LINE 641-643:
        ts.current_stop_price = new_stop_price  # ← Updated immediately!
        ts.last_stop_update = datetime.now()
        ts.update_count += 1

        # ❌ БАГ #2: Lock held during exchange API call (can fail!)
        # LINE 650-652:
        async with self.sl_update_locks[ts.symbol]:
            await self._update_stop_order(ts)  # ← CAN FAIL with ERROR -2021!

        # ❌ БАГ #3: Log success BEFORE checking if exchange succeeded!
        # LINE 655-658:
        logger.info(
            f"📈 {ts.symbol}: SL moved - Trailing stop updated from {old_stop:.4f} "
            f"to {new_stop_price:.4f} (+{improvement:.2f}%)"
        )  # ← Logs even if exchange failed!

        # ❌ БАГ #4: Save to database even if exchange update failed!
        # LINE 681:
        await self._save_state(ts)  # ← Saves optimistic state to DB!

        return {
            'action': 'updated',
            'symbol': ts.symbol,
            'old_stop': float(old_stop),
            'new_stop': float(new_stop_price),
            'improvement_percent': float(improvement)
        }

    return None
```

#### Почему это происходит

**На волатильном рынке**:

1. **T0**: Price = $3.305, TS calculates stop = $3.290
2. **T1** (0.1s later): TS updates `ts.current_stop_price = 3.290` in memory
3. **T2** (0.5s later): TS calls `_update_stop_order()` → Binance API
4. **T3** (1.0s later): Price dropped to $3.285 (volatility!)
5. **T4** (1.1s later): Binance receives request: "create SL at $3.290"
6. **T5** (1.1s later): Binance checks: $3.290 > $3.285 (current market) → **INVALID**
7. **T6** (1.1s later): Binance returns ERROR -2021
8. **T7** (1.2s later): TS receives error, but **state already modified**!
9. **T8** (1.3s later): TS saves state to DB with stop=$3.290 (wrong!)

**Result**: DB contains stop=$3.290, Exchange has stop=$3.1766 (old)

---

### 4. Доказательства

#### Evidence #1: Success log before error

```
06:14:49 - INFO - 📈 APTUSDT: SL moved - updated from 3.2871 to 3.2877 (+0.02%)
06:14:49 - ERROR - ❌ APTUSDT: SL update failed - "Order would immediately trigger"
```

**Analysis**: Impossible to log "SL moved" if exchange rejected! Must be optimistic update.

#### Evidence #2: Exchange has old SL after restart

```
06:44:20 - 🗑️  Cancelled SL order 51401792... (stopPrice=3.1766)
```

**Analysis**: After 1+ hour of "successful" TS updates in logs, exchange STILL has initial protection SL! Proves updates never succeeded on exchange.

#### Evidence #3: DB has new SL after restart

```
06:44:14 - ✅ APTUSDT: TS state RESTORED from DB
           current_stop=3.28895187  ← Last "successful" update from 06:15:21
```

**Analysis**: DB contains stop=$3.289, proving state was saved even though exchange updates failed.

#### Evidence #4: Method structure proves optimistic update

Looking at code structure (lines 640-690):
```
Line 641: ts.current_stop_price = new_stop_price  ← State updated
Line 650: await self._update_stop_order(ts)       ← Exchange API (can fail)
Line 656: logger.info("SL moved")                 ← Log success
Line 681: await self._save_state(ts)              ← Save to DB
```

**NO ERROR HANDLING** between lines 641-681! State modified regardless of exchange result.

---

### 5. Влияние и критичность

#### Severity: P0 - КРИТИЧЕСКИЙ

**Почему P0**:
- ✅ Affects **ALL** positions with active trailing stop
- ✅ Creates **SILENT** DB-Exchange divergence (user thinks SL is protected)
- ✅ On volatile markets, **EVERY** TS update can fail while appearing successful
- ✅ Position can be at risk if true SL is far from believed SL
- ✅ Systematic problem (not edge case)

#### Frequency

**Very High**: Происходит каждый раз когда:
1. TS пытается обновить SL на бирже
2. Price moved (even slightly) between calculation and API execution
3. Binance latency causes price to change during API call

**From logs**: ~20 failed updates in 1 hour for APTUSDT alone!

#### Impact

**Critical consequences**:
1. **False sense of security**: Logs say "SL moved", but it didn't
2. **Risk exposure**: Position protected by OLD SL (much lower), not NEW SL
3. **DB corruption**: All TS state in DB is unreliable
4. **Restart failures**: Every restart causes ERROR -2021 spam
5. **Silent failures**: No alert to user that protection is compromised

**Example risk**:
- User sees in DB: SL at $3.29 (1% below market $3.33)
- Reality on exchange: SL at $3.17 (5% below market!)
- If price drops to $3.20: User expects SL to trigger, but it doesn't
- Potential loss: Extra 3% drawdown

---

## ✅ РЕШЕНИЕ

### Fix #1: PESSIMISTIC Update Pattern (REQUIRED)

**File**: `protection/trailing_stop.py`
**Method**: `_update_trailing_stop()`
**Lines**: 640-690

**Change from OPTIMISTIC to PESSIMISTIC**:

```python
async def _update_trailing_stop(self, ts: TrailingStopInstance) -> Optional[Dict]:
    """Update trailing stop if price moved favorably"""

    # ... calculation logic stays same ...

    if new_stop_price:
        old_stop = ts.current_stop_price

        # NEW APPROACH: Check rate limiting FIRST (before ANY state change)
        should_update, skip_reason = self._should_update_stop_loss(ts, new_stop_price, old_stop)

        if not should_update:
            logger.debug(f"⏭️  {ts.symbol}: SL update SKIPPED - {skip_reason}")
            return None

        # ✅ FIX: DO NOT modify state yet! Keep old values.
        # Store proposed new values temporarily
        proposed_stop = new_stop_price
        proposed_time = datetime.now()

        # ✅ FIX: Update on exchange FIRST (while state unchanged)
        # Get or create lock for this symbol
        if ts.symbol not in self.sl_update_locks:
            self.sl_update_locks[ts.symbol] = asyncio.Lock()

        # Acquire symbol-specific lock before exchange update
        async with self.sl_update_locks[ts.symbol]:
            # Temporarily set new stop for _update_stop_order() to use
            ts.current_stop_price = proposed_stop

            # Try to update stop order on exchange
            update_success = await self._update_stop_order(ts)

            # ✅ FIX: ROLLBACK if exchange update failed!
            if not update_success:
                # Restore old stop price
                ts.current_stop_price = old_stop

                logger.error(
                    f"❌ {ts.symbol}: SL update FAILED on exchange, "
                    f"state rolled back (keeping old stop {old_stop:.4f})"
                )

                # DO NOT save to DB, DO NOT log success
                return None

        # ✅ FIX: Only commit state changes if exchange succeeded
        ts.last_stop_update = proposed_time
        ts.update_count += 1

        # Update tracking fields for rate limiting
        ts.last_sl_update_time = datetime.now()
        ts.last_updated_sl_price = proposed_stop

        # Calculate improvement
        improvement = abs((proposed_stop - old_stop) / old_stop * 100)

        # ✅ NOW we can log success (exchange confirmed)
        logger.info(
            f"📈 {ts.symbol}: SL moved - Trailing stop updated from {old_stop:.4f} "
            f"to {proposed_stop:.4f} (+{improvement:.2f}%)"
        )

        # Log trailing stop update
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.TRAILING_STOP_UPDATED,
                {
                    'symbol': ts.symbol,
                    'old_stop': float(old_stop),
                    'new_stop': float(proposed_stop),
                    'improvement_percent': float(improvement),
                    'current_price': float(ts.current_price),
                    'highest_price': float(ts.highest_price) if ts.side == 'long' else None,
                    'lowest_price': float(ts.lowest_price) if ts.side == 'short' else None,
                    'update_count': ts.update_count
                },
                symbol=ts.symbol,
                exchange=self.exchange_name,
                severity='INFO'
            )

        # ✅ FIX: Save to database ONLY after exchange confirmed success
        await self._save_state(ts)

        return {
            'action': 'updated',
            'symbol': ts.symbol,
            'old_stop': float(old_stop),
            'new_stop': float(proposed_stop),
            'improvement_percent': float(improvement)
        }

    return None
```

**Key changes**:
1. **Line 641-643**: Moved AFTER exchange update
2. **Rollback logic**: If exchange fails, restore old state
3. **Success log**: Only after exchange confirms
4. **DB save**: Only after exchange confirms

### Fix #2: Make _update_stop_order() return success status

**File**: `protection/trailing_stop.py`
**Method**: `_update_stop_order()`
**Lines**: 965-1094

**Change return type from `bool` to actually check result**:

```python
async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
    """Update stop order using atomic method when available"""
    try:
        # ... existing code ...

        # Call atomic update
        result = await self.exchange.update_stop_loss_atomic(
            symbol=ts.symbol,
            new_sl_price=float(ts.current_stop_price),
            position_side=ts.side
        )

        if result['success']:
            # ✅ SUCCESS - return True
            logger.info(f"✅ {ts.symbol}: SL updated via {result['method']} ...")
            return True  # ← CRITICAL: Must return True
        else:
            # ❌ FAILED - return False
            logger.error(f"❌ {ts.symbol}: SL update failed - {result['error']}")
            return False  # ← CRITICAL: Must return False

    except Exception as e:
        logger.error(f"❌ Failed to update stop order for {ts.symbol}: {e}", exc_info=True)
        return False  # ← CRITICAL: Exception = failure
```

**Key change**: Actually return False on failure (currently always returns result of event logging!)

---

## 🧪 TESTING PLAN

### Test 1: Normal operation (price rises, no volatility)

**Setup**:
1. Open LONG position
2. Activate TS
3. Price steadily rises (no drops)

**Expected (after fix)**:
- TS updates stop on exchange ✅
- TS updates state in memory ✅
- TS saves to DB ✅
- Logs show "SL moved" ✅
- No errors

### Test 2: Volatile market (price drops during update)

**Setup**:
1. Open LONG position
2. Activate TS at $100
3. Price jumps to $105 → TS calculates stop=$104.475
4. **Simulate**: Price drops to $104.40 BEFORE TS API call completes
5. Binance rejects: stop=$104.475 > market=$104.40

**Expected (after fix)**:
- TS tries to update exchange ❌ FAILS
- TS **rolls back** state (keeps old stop)
- TS logs ERROR (not "SL moved")
- TS does NOT save to DB
- **No DB-Exchange divergence**

**Current behavior (bug)**:
- TS updates state ✅
- TS tries exchange ❌ FAILS
- TS logs "SL moved" (wrong!)
- TS saves to DB with wrong stop
- **DB-Exchange divergence created**

### Test 3: Bot restart after failed updates

**Setup**:
1. Run Test 2 (create DB-Exchange divergence)
2. Restart bot

**Expected (after fix)**:
- Since DB and Exchange are in sync (no divergence)
- Restart should be clean
- No ERROR -2021

**Current behavior (bug)**:
- DB has stop=$104.475
- Exchange has stop=$100 (old)
- Restart tries to sync → ERROR -2021

---

## 📊 МОНИТОРИНГ

### Before fix deployment

```bash
# Count how many "SL moved" logs are followed by ERROR
grep -A 1 "SL moved" logs/trading_bot.log | grep -c "ERROR.*2021"

# Expected: HIGH number (proves optimistic updates)
```

### After fix deployment

```bash
# Should be ZERO "SL moved" followed by ERROR
grep -A 1 "SL moved" logs/trading_bot.log | grep -c "ERROR.*2021"

# Expected: 0
```

### Monitor rollbacks

```bash
# New log line added by fix
grep "state rolled back" logs/trading_bot.log

# Shows how often exchange updates fail (good to know!)
```

---

## 🚨 КРИТИЧНОСТЬ

### P0 - КРИТИЧЕСКИЙ

**Сравнение с другими багами**:

1. **Trailing stop wrong initial_stop (P0)** - Fixed today
   - Impact: Wrong SL from position open
   - Affected: All new positions
   - Visibility: Obvious (large errors)

2. **THIS BUG (P0)** - **WORSE!**
   - Impact: **SILENT** DB-Exchange divergence
   - Affected: **ALL** active TS positions on volatile markets
   - Visibility: **HIDDEN** (logs show success, but it's not!)
   - Risk: False sense of security, actual SL much lower than believed
   - Duration: Can persist for hours/days until restart

### Почему это самый опасный баг

1. **Silent failure**: User thinks SL is at $3.29, reality is $3.17
2. **Systematic**: Happens constantly on every volatile price movement
3. **Compounding**: Each failed update makes divergence worse
4. **Delayed detection**: Only discovered on bot restart
5. **Risk multiplier**: Can lead to unexpected large losses

---

## 📝 NEXT STEPS

### Immediate (URGENT):

1. ✅ **INVESTIGATION COMPLETE**: Root cause found
2. ⚠️ **CRITICAL FIX**: Implement pessimistic update pattern (Fix #1 + Fix #2)
3. ⚠️ **TEST**: Test all 3 scenarios (normal, volatile, restart)
4. ⚠️ **DEPLOY**: Apply fix ASAP
5. ⚠️ **VERIFY**: Monitor logs for rollback events

### Post-deployment:

1. Check all positions: Verify DB stop matches Exchange stop
2. Manual sync if needed: For positions with divergence
3. Add alert: If rollback happens frequently (market too volatile for TS)

---

## 🔗 RELATED

- Investigation started: 2025-10-22 06:44
- Related position: APTUSDT (LONG, entry $3.2414)
- Related files:
  - `protection/trailing_stop.py:640-690` (_update_trailing_stop) ⚠️ **PRIMARY BUG**
  - `protection/trailing_stop.py:965-1094` (_update_stop_order) ⚠️ **SECONDARY BUG**
  - `core/exchange_manager.py:834-975` (_binance_update_sl_optimized)
- Related commits:
  - e25f868 (fix: trailing stop initial_stop) - different bug, already fixed

---

## 📝 FINAL VERDICT

**ВОПРОС ПОЛЬЗОВАТЕЛЯ**: "это проблема тестнета или баг в коде?"

**ОТВЕТ**: ✅ **КРИТИЧЕСКИЙ БАГ В КОДЕ!**

**Root Cause**:
Trailing Stop Manager использует **OPTIMISTIC UPDATE** pattern - обновляет state в памяти и БД **ДО того** как биржа подтвердит успешное обновление SL. На волатильных рынках это приводит к silent DB-Exchange divergence.

**Fix Required**:
Изменить на **PESSIMISTIC UPDATE** pattern:
1. Попытаться обновить на бирже
2. **ТОЛЬКО если успешно** → обновить state и сохранить в БД
3. **Если failed** → rollback state, не сохранять в БД

**Priority**: P0 - КРИТИЧЕСКИЙ (даже опаснее чем предыдущий баг, потому что SILENT!)

**Estimated Fix Time**: 1 час (изменения простые, но critical)
