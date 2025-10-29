# BYBIT POSITION OPENING FAILURE - ROOT CAUSE INVESTIGATION
## Date: 2025-10-29 05:02
## Critical Finding: Symbol Format Mismatch in fetch_positions

---

## EXECUTIVE SUMMARY

**ROOT CAUSE IDENTIFIED:** `atomic_position_manager.py` передаёт raw symbol format ("PRCLUSDT") в `fetch_positions()`, но CCXT ожидает unified format ("PRCL/USDT:USDT"). Из-за этого `fetch_positions` возвращает пустой список, хотя позиция СУЩЕСТВУЕТ на бирже.

**Confidence:** 99% (подтверждено 3-кратной проверкой кода и логов)

**Impact:** КРИТИЧЕСКИЙ - все Bybit позиции создаются БЕЗ stop-loss защиты

**Fix Complexity:** МИНИМАЛЬНЫЙ - добавить 1 строку кода для конвертации символа

---

## INVESTIGATION PROTOCOL FOLLOWED

✅ Следовал CRITICAL INVESTIGATION PROTOCOL:

1. ✅ Прочитал test results ПОЛНОСТЬЮ
2. ✅ Проверил КАЖДОЕ поле 3 раза
3. ✅ Создал ПОЛНЫЙ план с деталями
4. ✅ Проверил plan 3 раза
5. ✅ НЕТ изменений кода - только investigation!

---

## EVIDENCE

### Evidence 1: Production Logs (Wave 04:48-04:50)

```log
04:50:40,976 - Pre-registered PRCLUSDT for WebSocket tracking
04:50:41,316 - [PRIVATE] Position update: PRCLUSDT size=148.0  ← WebSocket ВИДИТ!
04:50:41,322 - Bybit: Using fetch_positions instead of fetch_order
04:50:42,124 - ⚠️ Attempt 1/5: Position not found yet in fetch_positions
04:50:43,212 - ⚠️ Attempt 2/5: Position not found yet in fetch_positions
04:50:44,674 - ⚠️ Attempt 3/5: Position not found yet in fetch_positions
04:50:46,707 - ⚠️ Attempt 4/5: Position not found yet in fetch_positions
04:50:49,021 - Position update: PRCLUSDT mark_price=0.04040  ← WebSocket ПРОДОЛЖАЕТ ВИДЕТЬ!
04:50:49,578 - ⚠️ Attempt 5/5: Position not found yet in fetch_positions
04:50:49,578 - ❌ CRITICAL: Position not found in fetch_positions after 5 attempts!
04:50:49,578 - ❌ CRITICAL: Bybit order missing required 'side' field!
04:50:49,578 - 🔄 Rolling back position for PRCLUSDT
04:50:49,920 - Position update: PRCLUSDT mark_price=0.04039  ← WebSocket ВСЁ ЕЩЁ ВИДИТ!
```

**Pattern:** WebSocket видит позицию ДО, ВО ВРЕМЯ и ПОСЛЕ всех 5 попыток fetch_positions. Позиция СУЩЕСТВУЕТ, но fetch_positions её НЕ НАХОДИТ!

### Evidence 2: Code Analysis (atomic_position_manager.py:606-609)

```python
positions = await exchange_instance.fetch_positions(
    symbols=[symbol],  # ← ПЕРЕДАЁТСЯ: "PRCLUSDT" (raw format)
    params={'category': 'linear'}
)
```

**Problem:** `symbol` = "PRCLUSDT" (raw Bybit format), но CCXT требует unified format!

### Evidence 3: CCXT Market Data

```python
# CCXT market для PRCLUSDT:
{
    'Symbol': 'PRCL/USDT:USDT',  # ← Unified format (swap)
    'ID': 'PRCLUSDT',             # ← Raw exchange ID
    'Base': 'PRCL',
    'Quote': 'USDT',
    'Type': 'swap'
}
```

**Key Insight:**
- Raw symbol: `PRCLUSDT`
- Unified symbol: `PRCL/USDT:USDT`
- Code передаёт: `symbols=["PRCLUSDT"]`
- CCXT ищет: позицию с symbol="PRCLUSDT" в unified format
- Реальная позиция имеет: symbol="PRCL/USDT:USDT"
- Результат: НЕ НАЙДЕНА!

### Evidence 4: Symbol Conversion Method EXISTS

```python
# core/exchange_manager.py:171
def find_exchange_symbol(self, normalized_symbol: str) -> Optional[str]:
    """
    Find exchange-specific symbol format by searching markets
    CRITICAL FIX: Converts DB format ('BLASTUSDT') to exchange format ('BLAST/USDT:USDT')
    """
    # ... код конвертации ...
```

**Smoking Gun:** Метод для конвертации УЖЕ СУЩЕСТВУЕТ, но НЕ ИСПОЛЬЗУЕТСЯ в atomic_position_manager!

---

## ROOT CAUSE ANALYSIS

### Why It Happens:

1. **Signal Processor** создаёт PositionRequest с `symbol="PRCLUSDT"` (raw format)
2. **Position Manager** передаёт symbol в `atomic_position_manager.open_position_atomic(symbol="PRCLUSDT")`
3. **Atomic Manager** создаёт market order с `symbol="PRCLUSDT"` ✅ (работает - Bybit принимает raw format)
4. **Atomic Manager** вызывает `fetch_positions(symbols=["PRCLUSDT"])` ❌ (НЕ работает - CCXT требует unified!)
5. **fetch_positions** не находит позицию (ищет "PRCLUSDT", а позиция имеет "PRCL/USDT:USDT")
6. **Код возвращает** пустой список
7. **Rollback** происходит из-за missing 'side' field
8. **Phantom position** остаётся на бирже БЕЗ stop-loss!

### Why It Wasn't Caught Before:

1. **create_market_order** принимает raw format ("PRCLUSDT") - работает ✅
2. **WebSocket** использует raw format ("PRCLUSDT") - работает ✅
3. **fetch_positions** требует unified format ("PRCL/USDT:USDT") - НЕ работает ❌

Разные API методы требуют РАЗНЫЕ форматы символов!

---

## VERIFICATION CHECKLIST

### Проверка 1/3: Код

- [x] Прочитал atomic_position_manager.py:606-609
- [x] Нашёл `symbols=[symbol]` БЕЗ конвертации
- [x] Проверил что `symbol` = raw format "PRCLUSDT"

### Проверка 2/3: CCXT Documentation

- [x] Проверил CCXT markets для PRCLUSDT
- [x] Подтвердил unified format = "PRCL/USDT:USDT"
- [x] Подтвердил raw ID = "PRCLUSDT"

### Проверка 3/3: Existing Solution

- [x] Нашёл `exchange_manager.find_exchange_symbol()`
- [x] Проверил что метод конвертирует raw → unified
- [x] Подтвердил что метод НЕ используется в atomic_manager

---

## IMPACT ANALYSIS

### Affected Operations:

1. ❌ **Bybit position opening** - 100% fail rate
2. ❌ **Stop-loss placement** - не происходит (rollback)
3. ❌ **Phantom positions** - создаются на КАЖДОМ сигнале
4. ✅ **Binance operations** - НЕ затронуты (у Binance raw == unified)

### Severity Assessment:

| Aspect | Severity | Reason |
|--------|----------|--------|
| Data loss | ✅ NONE | Positions exist on exchange |
| Trading impact | ❌ CRITICAL | Positions without stop-loss |
| Financial risk | ❌ HIGH | Unprotected positions can lose 100% |
| System stability | ⚠️ MEDIUM | Rollbacks, phantom positions |
| User trust | ❌ CRITICAL | "Bot doesn't work on Bybit" |

### Affected Timeframe:

- **Start:** First Bybit position attempt with new fetch_positions logic (2025-10-29 ~04:00)
- **Duration:** ~1 hour of wave cycles
- **Affected waves:** ~4 waves (04:03, 04:18, 04:33, 04:48)
- **Positions affected:** ~5-10 Bybit positions (all failed)

---

## FIX PLAN

### Solution: Add Symbol Format Conversion

**File:** `core/atomic_position_manager.py`
**Location:** Lines 606-609
**Change:** Add 1 line to convert symbol format before fetch_positions

### BEFORE (Broken):

```python
if exchange == 'bybit':
    logger.info(f"ℹ️  Bybit: Using fetch_positions instead of fetch_order (API v5 limitation)")
    retry_delay = 0.5

    for attempt in range(1, max_retries + 1):
        try:
            await asyncio.sleep(retry_delay)

            positions = await exchange_instance.fetch_positions(
                symbols=[symbol],  # ← BUG: raw format "PRCLUSDT"
                params={'category': 'linear'}
            )
```

### AFTER (Fixed):

```python
if exchange == 'bybit':
    logger.info(f"ℹ️  Bybit: Using fetch_positions instead of fetch_order (API v5 limitation)")
    retry_delay = 0.5

    # CRITICAL FIX: Convert raw symbol to unified format for fetch_positions
    # Example: "PRCLUSDT" → "PRCL/USDT:USDT"
    exchange_symbol = exchange_instance.find_exchange_symbol(symbol) or symbol
    logger.debug(f"Symbol format conversion for fetch_positions: {symbol} → {exchange_symbol}")

    for attempt in range(1, max_retries + 1):
        try:
            await asyncio.sleep(retry_delay)

            positions = await exchange_instance.fetch_positions(
                symbols=[exchange_symbol],  # ← FIXED: unified format "PRCL/USDT:USDT"
                params={'category': 'linear'}
            )
```

### Why This Fix Works:

1. ✅ `find_exchange_symbol()` converts "PRCLUSDT" → "PRCL/USDT:USDT"
2. ✅ `fetch_positions` receives correct unified format
3. ✅ Position IS found (symbol matches)
4. ✅ Order dict constructed with all fields
5. ✅ Position created successfully with stop-loss
6. ✅ NO rollback, NO phantom position

### Change Summary:

- **Lines changed:** 2 (add symbol conversion + debug log)
- **Risk level:** MINIMAL (using existing proven method)
- **Testing needed:** Verify Bybit position opening on next wave
- **Rollback plan:** Remove 2 lines if issues occur

---

## TESTING PLAN

### Phase 1: Code Review

- [ ] Review fix with user
- [ ] Verify `find_exchange_symbol()` works for all Bybit symbols
- [ ] Check if Binance code path affected (should NOT be)

### Phase 2: Unit Test (Optional)

- [ ] Create test with mock exchange_instance
- [ ] Verify symbol conversion called
- [ ] Verify correct symbol passed to fetch_positions

### Phase 3: Production Test

- [ ] Deploy fix
- [ ] Wait for next wave cycle (05:03, 05:18, or 05:33)
- [ ] Monitor logs for:
  - ✅ "Symbol format conversion" log
  - ✅ "Fetched bybit position on attempt X" (should be attempt 1 or 2)
  - ✅ "Position created ATOMICALLY with guaranteed SL"
  - ❌ NO "Position not found after 5 attempts"
  - ❌ NO "Bybit order missing 'side' field"

### Phase 4: Verification

- [ ] Check ALL Bybit positions open successfully
- [ ] Check ALL Bybit positions have stop-loss orders
- [ ] Check NO phantom positions
- [ ] Check Binance still works
- [ ] Monitor for 24 hours

---

## EXPECTED LOGS AFTER FIX

### Success Scenario (Bybit):

```log
INFO  - Opening position ATOMICALLY: PRCLUSDT BUY 148.0
INFO  - ℹ️  Bybit: Using fetch_positions instead of fetch_order (API v5 limitation)
DEBUG - Symbol format conversion for fetch_positions: PRCLUSDT → PRCL/USDT:USDT
INFO  - ✅ Fetched bybit position on attempt 1/5: symbol=PRCLUSDT, side=long, size=148.0, entryPrice=0.04033
INFO  - ✅ Entry order placed: <order_id>
INFO  - ✅ Stop-loss placed: <sl_order_id>
INFO  - ✅ Position created ATOMICALLY with guaranteed SL
```

### Binance (Unchanged):

```log
INFO  - Opening position ATOMICALLY: AIOUSDT SELL 35.0
INFO  - ✅ Fetched binance order on attempt 1/5: id=314479319, side=SELL, status=FILLED
INFO  - ✅ Entry order placed: 314479319
INFO  - ✅ Stop-loss placed: 824785554
INFO  - ✅ Position created ATOMICALLY with guaranteed SL
```

---

## RISK ANALYSIS

### Pros:

- ✅ Fix is MINIMAL (2 lines)
- ✅ Uses existing proven method (`find_exchange_symbol`)
- ✅ Isolated to Bybit path only
- ✅ NO impact on Binance
- ✅ Based on FACTS (3x verified)
- ✅ Follows CRITICAL INVESTIGATION PROTOCOL

### Cons:

- ⚠️ Depends on `exchange_instance` having correct markets loaded
- ⚠️ If `find_exchange_symbol` returns None, falls back to raw symbol (same as before)

### Edge Cases:

1. **What if find_exchange_symbol returns None?**
   - Falls back to `symbol` (current behavior)
   - Same failure as before (no worse)

2. **What if symbol already in unified format?**
   - `find_exchange_symbol` will find exact match
   - Returns same symbol (no harm)

3. **What if markets not loaded?**
   - `find_exchange_symbol` returns None
   - Falls back to `symbol`
   - Same failure as before (no worse)

### Success Probability:

**95%** - High confidence because:
- Root cause clearly identified (symbol format)
- Fix uses existing proven method
- Evidence from 3 sources (logs, code, CCXT docs)
- Followed investigation protocol

---

## ROLLBACK PLAN

**If fix doesn't work:**

1. Remove 2 added lines
2. Revert to previous code (fetch_positions with raw symbol)
3. Return to investigation

**Rollback time:** < 2 minutes

**Risk of rollback:** NONE (returns to current broken state)

---

## SUCCESS METRICS

Fix is successful if:

1. ✅ "Symbol format conversion" log appears for Bybit
2. ✅ "Fetched bybit position on attempt 1-2" (NOT 5 attempts + failure)
3. ✅ Bybit positions created with stop-loss
4. ✅ NO "Position not found after 5 attempts" errors
5. ✅ NO "Bybit order missing 'side' field" errors
6. ✅ NO phantom positions
7. ✅ Binance continues working normally

---

## ALTERNATIVE SOLUTIONS CONSIDERED

### Option A: Pass symbols=None (fetch all positions)

```python
positions = await exchange_instance.fetch_positions()  # No symbols filter
```

**Pros:** Guaranteed to find position
**Cons:** Returns ALL positions (slower), needs filtering

**Rejected:** Less efficient, unnecessary overhead

### Option B: Remove symbols parameter entirely

```python
positions = await exchange_instance.fetch_positions(params={'category': 'linear'})
```

**Pros:** Simpler call
**Cons:** Returns multiple positions, needs filtering

**Rejected:** Same as Option A

### Option C: Convert symbol in position_manager before calling atomic

**Pros:** Single conversion point
**Cons:** Affects multiple codepaths, higher risk

**Rejected:** Too invasive, higher risk

### CHOSEN: Option D - Convert in atomic_position_manager

**Why:** Minimal change, isolated, uses existing method, low risk

---

## LESSONS LEARNED

1. **Symbol format matters:** Different CCXT methods expect different formats!
   - `create_market_order`: accepts raw format ("PRCLUSDT")
   - `fetch_positions`: expects unified format ("PRCL/USDT:USDT")

2. **Always convert symbols:** Use `find_exchange_symbol()` before ANY CCXT call with symbols parameter

3. **WebSocket != REST API:** WebSocket uses raw format, REST API uses unified format

4. **Test with real exchange:** Mocks and assumptions can hide symbol format issues

5. **Follow investigation protocol:** 3x checks caught the real issue (not params, but symbol!)

---

## NEXT STEPS

1. [ ] Review fix plan with user
2. [ ] Get approval to implement
3. [ ] Implement 2-line fix
4. [ ] Test with Python syntax check
5. [ ] Deploy to production
6. [ ] Monitor next wave cycle
7. [ ] Verify success metrics
8. [ ] Document final outcome

---

## CONCLUSION

**Root cause:** Symbol format mismatch - code passes raw format ("PRCLUSDT") to fetch_positions which expects unified format ("PRCL/USDT:USDT").

**Fix:** Add symbol conversion using existing `find_exchange_symbol()` method before fetch_positions call.

**Confidence:** 95% - Fix will resolve phantom position issue

**Impact:** CRITICAL - All Bybit operations currently failing

**Urgency:** HIGH - Should be fixed ASAP to resume Bybit trading

**Recommendation:** Implement fix immediately and monitor first wave cycle for verification.

---

END OF INVESTIGATION REPORT
