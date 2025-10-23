# 🔴 БАГ В КОДЕ: Binance Error -2021 "Order would immediately trigger" после перезапуска бота

**Дата**: 2025-10-22 06:44
**Статус**: ✅ РАССЛЕДОВАНО - Найден баг в коде
**Приоритет**: P1 - HIGH (не критично, но требует исправления)
**Влияние**: Trailing stop fail при перезапуске бота если цена упала

---

## 📋 EXECUTIVE SUMMARY

**Ошибка**: `binance {"code":-2021,"msg":"Order would immediately trigger."}`

**Вывод**: Это **БАГ В КОДЕ**, НЕ проблема testnet!

**Root Cause**: Trailing Stop Manager восстанавливает state из БД после перезапуска бота с устаревшим `current_stop_price`, рассчитанным при более высокой цене. Если цена упала, stop price оказывается ВЫШЕ рыночной цены для LONG позиции → биржа отклоняет как invalid order.

**Fix Required**: Добавить валидацию `current_stop_price` относительно текущей рыночной цены после восстановления state из БД.

---

## 🔍 ДЕТАЛЬНЫЙ АНАЛИЗ

### 1. Контекст ошибки

**Из логов** (2025-10-22 06:44:20):
```
06:44:19 - Position update: APTUSDT mark_price=3.2334
06:44:20 - 🗑️  Cancelled SL order 51401792... (stopPrice=3.1766)
06:44:20 - ⚠️  APTUSDT: Position not found on exchange, using DB fallback (quantity=61.0)
06:44:20 - ❌ Binance error -2021: "Order would immediately trigger"
06:44:20 - Trailing stop updated: old=3.28895187, new=3.28895187365, current_price=3.2334
```

**Позиция**: APTUSDT
- **Side**: LONG (buy)
- **Entry price**: $3.2414 (opened 02:05:53)
- **Initial stop**: $3.176572
- **Trailing activated**: 05:11:34
- **Highest price reached**: $3.30547927 (at 06:15:21)
- **Current stop (from DB)**: $3.28895187 (calculated from highest: 3.305 * (1 - 0.5%) = 3.289)
- **Market price at error**: $3.2334
- **Stop being placed**: $3.28895187

**SMOKING GUN**:
```
Stop price:   $3.289
Market price: $3.233
For LONG:     Stop MUST be BELOW market
Result:       $3.289 > $3.233 → INVALID! ❌
```

---

### 2. Timeline событий

#### PHASE 1: Normal operation (02:05 - 06:15)

```
02:05:53 - Position APTUSDT opened at $3.2414
           Initial SL: $3.176572 (2% below entry)

05:11:34 - Trailing stop ACTIVATED
           Price reached activation level (~$3.27+)

06:15:21 - Price reached HIGHEST: $3.30547927
           TS calculated new stop: $3.28895187 (0.5% below highest)
           TS state saved to DB:
             - highest_price: 3.30547927
             - current_stop_price: 3.28895187
```

#### PHASE 2: Price drops (06:15 - 06:44)

```
06:15:21 - Price at highest: $3.305
           ...
06:44:19 - Price dropped to: $3.2334 (down 2.2%)
           TS state still in DB with stop=$3.289
```

#### PHASE 3: Bot restart (~06:44)

```
06:44:14 - Bot RESTARTED
           TS state RESTORED from DB:
             - highest_price: 3.30547927 ✅
             - current_stop_price: 3.28895187 ⚠️  (STALE! Calculated at old price)

06:44:19 - Position update received: mark_price=3.2334

06:44:20 - TS calls _update_stop_order()
           Cancelled old SL: stopPrice=3.1766 (initial protection SL)
           Tries to create NEW SL: stopPrice=3.289

06:44:20 - ERROR -2021: "Order would immediately trigger"
           Reason: Stop ($3.289) > Market ($3.233) for LONG
```

---

### 3. Root Cause Analysis

#### Что произошло

**Normal operation** (до перезапуска):
1. TS активирован при цене $3.27+
2. Цена выросла до $3.305 (highest)
3. TS рассчитал stop = $3.289 (0.5% ниже highest)
4. TS сохранил state в БД
5. Цена упала до $3.233 (рыночное движение вниз)
6. TS НЕ обновлял stop (trailing stop только повышает SL при росте, не понижает при падении)

**После перезапуска** (баг):
1. TS восстановил state из БД: `current_stop_price=3.289`
2. Текущая рыночная цена: $3.233
3. TS попытался синхронизировать SL на бирже
4. Попытка создать stop at $3.289 при market $3.233 → INVALID для LONG

#### Код с проблемой

**File**: `protection/trailing_stop.py`
**Lines**: 220-294 (`_restore_state()` method)

```python
async def _restore_state(self, symbol: str) -> Optional[TrailingStopInstance]:
    """Restore trailing stop state from database"""
    # ...

    # Reconstruct TrailingStopInstance
    ts = TrailingStopInstance(
        symbol=state_data['symbol'],
        entry_price=Decimal(str(state_data['entry_price'])),
        current_price=Decimal(str(state_data['entry_price'])),  # ⚠️ Set to entry_price on restore
        highest_price=Decimal(str(state_data.get('highest_price', ...))),
        # ...
        current_stop_price=Decimal(str(state_data['current_stop_price'])),  # ❌ RESTORED WITHOUT VALIDATION!
        # ...
    )

    # ❌ NO VALIDATION if current_stop_price is valid relative to current market price!
    return ts
```

**Lines**: 965-1011 (`_update_stop_order()` method)

```python
async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
    """Update stop order using atomic method when available"""
    try:
        # ❌ NO VALIDATION if ts.current_stop_price is valid before calling exchange API!

        # Call atomic update
        result = await self.exchange.update_stop_loss_atomic(
            symbol=ts.symbol,
            new_sl_price=float(ts.current_stop_price),  # ← Uses STALE value from DB!
            position_side=ts.side
        )
```

#### Почему это баг

**Проблема**: `_restore_state()` восстанавливает все поля из БД без проверки что `current_stop_price` все еще валиден относительно текущей рыночной цены.

**Expected behavior**:
- После восстановления state проверить:
  - For LONG: `current_stop_price < current_market_price`
  - For SHORT: `current_stop_price > current_market_price`
- Если invalid → НЕ пытаться сразу обновлять SL на бирже
- Подождать первого вызова `update_price()` который пересчитает stop

**Current behavior (WRONG)**:
1. Restore state with `current_stop_price=3.289` (stale)
2. Immediately call `_update_stop_order()` to sync SL on exchange
3. Exchange rejects → Error -2021

---

### 4. Почему это НЕ проблема testnet?

Это **БАГ В КОДЕ**, потому что:

1. **Логическая ошибка**: Код восстанавливает устаревшее значение без валидации
2. **Биржа права**: Exchange correctly rejects invalid order (stop > market for long)
3. **Воспроизводимо**: Будет происходить на production при тех же условиях:
   - Bot restart
   - Price dropped since last TS state save
   - TS tries to sync SL before `update_price()` is called

4. **Race condition**: При нормальной работе (без перезапуска) TS обновляет stop через `update_price()`, где есть логика проверки что stop двигается только в благоприятном направлении. При перезапуске эта логика пропускается.

---

### 5. Доказательства из логов

**TS state restored from DB:**
```
06:44:14 - ✅ APTUSDT: TS state RESTORED from DB
           state=active
           highest_price=3.30547927  ← Highest reached before restart
           current_stop=3.28895187   ← Calculated from old highest
           update_count=...
```

**Position not found warning:**
```
06:44:20 - ⚠️  APTUSDT: Position not found on exchange, using DB fallback
           (quantity=61.0, timing issue after restart)
```

**Error:**
```
06:44:20 - ❌ APTUSDT: SL update failed
           binance {"code":-2021,"msg":"Order would immediately trigger."}
```

**TS update log (showing stale stop):**
```
06:44:20 - 📈 APTUSDT: SL moved
           Trailing stop updated from 3.28895187 to 3.28895187365 (+0.02%)
           current_price=3.2334  ← Current market price BELOW stop!
```

---

### 6. Влияние и критичность

#### Severity: P1 - HIGH (не P0)

**Почему не P0**:
- Позиция все еще защищена initial protection SL ($3.1766)
- Ошибка не приводит к потере позиции
- Происходит только при перезапуске бота

**Но все равно HIGH потому что**:
- Trailing stop не обновляется на бирже
- Error spam в логах
- Позиция теряет trailing protection до следующего движения цены вверх

#### Frequency

Ошибка происходит ТОЛЬКО когда:
1. Bot перезапускается (restart/crash)
2. Position has active trailing stop
3. Price has moved DOWN (unfavorably) since last TS state save to DB
4. TS tries to sync SL before `update_price()` corrects the stop

**Estimate**: ~10-20% restarts (когда цена упала между сохранением state и рестартом)

#### Impact

**Affected positions**: Any position with active trailing stop during bot restart in unfavorable market movement

**Consequences**:
- ✅ Position still has initial protection SL (not completely unprotected)
- ❌ Trailing stop fails to update on exchange
- ❌ Error spam every TS update attempt
- ❌ Position loses trailing protection benefit until price moves up again

**Current workaround**: Position eventually recovers when price moves back up above stop level, then TS can update normally.

---

## ✅ РЕШЕНИЕ

### Fix #1: Add validation in _restore_state() (RECOMMENDED)

**File**: `protection/trailing_stop.py`
**Method**: `_restore_state()`
**Line**: After line 264 (after reconstructing TrailingStopInstance)

**Add**:
```python
# NEW: Validate that restored current_stop_price is still valid
# If price moved unfavorably since last save, skip immediate SL sync
# Let update_price() handle SL update on first price update
if ts.current_stop_price:
    # Fetch current market price
    try:
        ticker = await self.exchange.exchange.fetch_ticker(symbol)
        current_market_price = Decimal(str(ticker['last']))

        # Check if stop is valid relative to market
        stop_valid = False
        if ts.side == 'long':
            stop_valid = ts.current_stop_price < current_market_price
        else:  # short
            stop_valid = ts.current_stop_price > current_market_price

        if not stop_valid:
            logger.warning(
                f"⚠️  {symbol}: Restored stop price ${ts.current_stop_price} is INVALID "
                f"(market=${current_market_price}, side={ts.side}). "
                f"Skipping immediate SL sync, will recalculate on price update."
            )
            # Mark that we should NOT try to update SL immediately
            # Option A: Set a flag
            ts._skip_immediate_sl_update = True
            # Option B: Clear stop order ID so _update_stop_order() won't run
            # ts.stop_order_id = None
    except Exception as e:
        logger.warning(f"Could not validate restored stop for {symbol}: {e}")
```

**Then in _update_stop_order()** (line ~1000):
```python
async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
    """Update stop order using atomic method when available"""
    try:
        # NEW: Check if we should skip immediate update after restore
        if getattr(ts, '_skip_immediate_sl_update', False):
            logger.debug(f"{ts.symbol}: Skipping SL update (stale stop from DB restore)")
            ts._skip_immediate_sl_update = False  # Clear flag
            return True  # Pretend success, will update on next price movement

        # ... rest of method
```

### Fix #2: Simpler - Clear stop_order_id on restore (ALTERNATIVE)

**File**: `protection/trailing_stop.py`
**Line**: 257 (in _restore_state())

**Change**:
```python
# OLD:
stop_order_id=state_data.get('stop_order_id'),

# NEW:
stop_order_id=None,  # Always clear on restore, will be recreated on next update
```

**Pros**: Simpler, less code
**Cons**: SL won't be synced until next price movement (acceptable for most cases)

---

## 🧪 TESTING PLAN

### Test Scenario 1: Restore with stale stop

**Setup**:
1. Open LONG position
2. Activate trailing stop
3. Price rises to $100 (highest)
4. TS calculates stop = $99.5 (0.5% below)
5. Save state to DB
6. Price drops to $98 (market movement)
7. **Restart bot**

**Expected behavior (after fix)**:
- TS restores state with stop=$99.5
- TS detects stop > market ($99.5 > $98)
- TS skips immediate SL sync
- TS waits for `update_price()` call
- On first price update, TS recalculates stop correctly

**Current behavior (bug)**:
- TS tries to place stop at $99.5
- ERROR -2021 "Order would immediately trigger"

### Test Scenario 2: Restore with valid stop

**Setup**:
1. Open LONG position
2. Activate trailing stop
3. Price rises to $100 (highest)
4. TS calculates stop = $99.5
5. Save state to DB
6. Price continues to $101 (still above stop)
7. **Restart bot**

**Expected behavior (should work)**:
- TS restores state with stop=$99.5
- TS detects stop < market ($99.5 < $101) ✅ Valid
- TS syncs SL on exchange successfully
- No error

---

## 📊 МОНИТОРИНГ

### Check if error still occurs

```bash
# After fix is deployed
grep "Order would immediately trigger" logs/trading_bot.log | grep -A 5 -B 5 "$(date +%Y-%m-%d)"
```

**Expected**: 0 errors for new restarts

### Monitor restart behavior

```bash
# Watch for TS state restoration during restart
grep "TS state RESTORED" logs/trading_bot.log | tail -20

# Check for validation warnings
grep "Restored stop price.*is INVALID" logs/trading_bot.log
```

---

## 🚨 КРИТИЧНОСТЬ

### P1 - HIGH

**Почему не P0**:
- ✅ Position still has initial protection SL (set at position open)
- ✅ Error is recoverable (TS works again when price moves favorably)
- ✅ Affects only positions during bot restart
- ✅ Not all restarts affected (only when price dropped)

**Но HIGH потому что**:
- ❌ Trailing stop protection lost temporarily
- ❌ Error spam in logs during restart
- ❌ User expects TS to work after restart
- ❌ Could lead to larger drawdown if price continues falling

### Comparison to previous bugs

1. **Trailing stop wrong initial_stop (P0)**: Fixed today (commit e25f868)
   - ALL new positions affected
   - Wrong SL from position open
   - More critical

2. **This bug (P1)**: Not yet fixed
   - Only positions during restart + unfavorable price movement
   - Initial SL still protects position
   - Less critical but still important

---

## 📝 NEXT STEPS

1. ✅ **INVESTIGATION COMPLETE**: Root cause found - bug in code
2. ⚠️ **CREATE FIX**: Implement Fix #1 or Fix #2
3. ⚠️ **TEST**: Test both scenarios (stale stop + valid stop)
4. ⚠️ **DEPLOY**: Apply fix and monitor
5. ⚠️ **VERIFY**: Ensure no more -2021 errors after bot restart

---

## 🔗 RELATED

- Investigation started: 2025-10-22 06:44
- Related position: APTUSDT (LONG, entry $3.2414)
- Related files:
  - `protection/trailing_stop.py:220-294` (_restore_state)
  - `protection/trailing_stop.py:965-1011` (_update_stop_order)
  - `core/exchange_manager.py:834-975` (_binance_update_sl_optimized)
- Related commits:
  - e25f868 (fix: trailing stop initial_stop) - different bug, already fixed

---

## 📝 FINAL VERDICT

**ВОПРОС ПОЛЬЗОВАТЕЛЯ**: "проведи глубокое расследование данной ошибки. найди ее истинную причину - это проблема тестнета или баг в коде?"

**ОТВЕТ**: ✅ **Это БАГ В КОДЕ, НЕ проблема testnet!**

**Root Cause**:
Trailing Stop Manager восстанавливает `current_stop_price` из БД после перезапуска бота без проверки что это значение все еще валидно относительно текущей рыночной цены. Если цена упала с момента последнего сохранения state, stop price может оказаться выше рыночной цены для LONG позиции, что невалидно.

**Fix Required**:
Добавить валидацию в `_restore_state()` чтобы проверить что `current_stop_price` корректен перед попыткой синхронизации SL на бирже. Если некорректен - пропустить немедленное обновление и подождать первого вызова `update_price()`.

**Priority**: P1 - HIGH (важно исправить, но не критично как предыдущий баг)
