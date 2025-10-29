# DIAGNOSTIC PATCH - SOURCE 1 Exception Visibility
## Date: 2025-10-29
## Purpose: Capture invisible exceptions in verification loop

---

## WHAT THIS PATCH DOES

**TEMPORARY diagnostic patch** to make SOURCE 1 (Order Status) exceptions VISIBLE.

### Problem
- SOURCE 1 exceptions logged as `logger.debug()`
- Production uses `LOG_LEVEL=INFO`
- Exceptions are **COMPLETELY INVISIBLE**
- Cannot diagnose why verification fails

### Solution
Changed logging levels in SOURCE 1 only:
- `logger.debug()` → `logger.warning()` (execution flow)
- `logger.debug()` → `logger.error()` (exceptions)
- Added `exc_info=True` for full stack traces

---

## CHANGES MADE

### File: `core/atomic_position_manager.py`

**Location: `_verify_position_exists_multi_source()` function, SOURCE 1 block**

### Change #1: Function docstring (Line 204-211)
```python
DIAGNOSTIC PATCH 2025-10-29:
Added verbose logging (WARNING/ERROR level) to diagnose SOURCE 1 failures.
This is TEMPORARY patch to capture exceptions that were invisible with DEBUG logging.

Uses priority-based approach:
1. Order filled status - MOST RELIABLE (PRIMARY)  ← Updated docstring
2. WebSocket position updates - SECONDARY
3. REST API fetch_positions - FALLBACK
```

### Change #2: Start of SOURCE 1 check (Line 258-259)
```python
# DIAGNOSTIC PATCH 2025-10-29: Changed to WARNING for visibility
logger.warning(f"🔍 [SOURCE 1/3] Checking order status for {entry_order.id}")
```

**Was:** `logger.debug(...)`
**Now:** `logger.warning(...)`

### Change #3: Before fetch_order call (Line 266-267)
```python
# DIAGNOSTIC PATCH 2025-10-29: Log BEFORE fetch_order call
logger.warning(f"🔄 [SOURCE 1] About to call fetch_order(id={entry_order.id}, symbol={symbol})")
```

**Was:** (no log)
**Now:** `logger.warning(...)` - Shows we're about to make API call

### Change #4: After fetch_order call (Line 271-272)
```python
# DIAGNOSTIC PATCH 2025-10-29: Log AFTER fetch_order call
logger.warning(f"✓ [SOURCE 1] fetch_order returned: {order_status is not None}")
```

**Was:** (no log)
**Now:** `logger.warning(...)` - Shows API call succeeded/failed

### Change #5: Order status result (Line 278-280)
```python
# DIAGNOSTIC PATCH 2025-10-29: Changed to INFO for visibility
logger.info(
    f"📊 [SOURCE 1] Order status fetched: id={entry_order.id}, status={status}, filled={filled}"
)
```

**Was:** `logger.debug(...)`
**Now:** `logger.info(...)`

### Change #6: EXCEPTION HANDLER (Line 305-314) ⭐ MOST CRITICAL
```python
except Exception as e:
    # DIAGNOSTIC PATCH 2025-10-29: Changed to ERROR for visibility
    # CRITICAL: This exception is WHY verification fails!
    logger.error(
        f"❌ [SOURCE 1] Order status check EXCEPTION:\n"
        f"  Exception type: {type(e).__name__}\n"
        f"  Exception message: {str(e)}\n"
        f"  Order ID: {entry_order.id}\n"
        f"  Symbol: {symbol}\n"
        f"  Attempt: {attempt}\n"
        f"  Elapsed: {elapsed:.2f}s",
        exc_info=True  # Include full stack trace
    )
    # НЕ помечаем как tried - будем retry в следующей итерации
```

**Was:** `logger.debug(f"⚠️ [SOURCE 1] failed: {e}")`
**Now:**
- `logger.error(...)` with detailed exception info
- `exc_info=True` for full stack trace
- Shows exception type, message, order ID, symbol, attempt, elapsed time

---

## WHAT WE'LL SEE IN LOGS NOW

### If SOURCE 1 executes without exception:
```
WARNING - 🔍 [SOURCE 1/3] Checking order status for 1020563016
WARNING - 🔄 [SOURCE 1] About to call fetch_order(id=1020563016, symbol=DEGENUSDT)
WARNING - ✓ [SOURCE 1] fetch_order returned: True
INFO    - 📊 [SOURCE 1] Order status fetched: id=1020563016, status=closed, filled=2925.0
INFO    - ✅ [SOURCE 1] Order status CONFIRMED position exists!
```

### If SOURCE 1 throws exception (EXPECTED):
```
WARNING - 🔍 [SOURCE 1/3] Checking order status for 1020563016
WARNING - 🔄 [SOURCE 1] About to call fetch_order(id=1020563016, symbol=DEGENUSDT)
ERROR   - ❌ [SOURCE 1] Order status check EXCEPTION:
  Exception type: RateLimitExceeded (or NetworkError, or ...)
  Exception message: binance {"code":-1003,"msg":"Too many requests"}
  Order ID: 1020563016
  Symbol: DEGENUSDT
  Attempt: 1
  Elapsed: 0.52s
Traceback (most recent call last):
  [FULL STACK TRACE]
```

### If SOURCE 1 condition is False (NOT EXPECTED):
```
(no logs - means `if not sources_tried['order_status']:` was False)
```

---

## SAFETY ANALYSIS

### Changes made:
- ✅ ONLY logging level changes
- ✅ ZERO logic changes
- ✅ ZERO control flow changes
- ✅ No new code paths
- ✅ No API call changes

### Risk assessment:
- **Risk level:** MINIMAL
- **Impact:** Slightly more log volume (WARNING/ERROR vs DEBUG)
- **Benefit:** Full visibility into previously invisible exceptions
- **Reversibility:** 100% (just change logging back)

### Performance impact:
- Negligible (logging is fast)
- Only affects failing verification attempts
- No impact on successful verifications

---

## TESTING PLAN

### Step 1: Deploy patch
- Bot already running in production
- No restart needed (Python picks up changes on next import)
- Wait for next wave cycle (3min, 18min, 33min, 48min past hour)

### Step 2: Monitor logs
- Watch for next position opening
- Look for WARNING/ERROR logs from SOURCE 1
- Capture FULL exception details

### Step 3: Analysis
- Identify exception type (RateLimitExceeded? NetworkError? Other?)
- Check if exception is consistent across attempts
- Verify timing hypothesis (500ms between calls)

### Step 4: Based on findings
- Create REAL fix (not diagnostic)
- Add proper error handling
- Add retry logic or delay as needed

---

## EXPECTED TIMELINE

### Next wave: ~15 minutes (next :18 or :33 or :48)
- Bot will attempt to open positions
- Diagnostic logs will appear
- We'll capture real exception

### Analysis: ~5 minutes after wave
- Review logs
- Identify root cause
- Confirm/reject hypotheses

### Fix creation: ~30 minutes
- Create proper fix based on real exception
- Add tests with real API behavior
- Deploy and verify

---

## ROLLBACK PLAN

If patch causes issues (UNLIKELY):

```python
# Revert line 259
logger.debug(f"🔍 [SOURCE 1/3] Checking order status for {entry_order.id}")

# Revert lines 267, 272 (remove)

# Revert lines 278-280
logger.debug(f"📊 Order status: id={entry_order.id}, status={status}, filled={filled}")

# Revert lines 305-314
logger.debug(f"⚠️ [SOURCE 1] Order status check failed: {e}")
```

**Rollback time:** < 1 minute

---

## HYPOTHESIS TO CONFIRM

### Primary hypothesis: Rate Limiting
**Evidence needed:**
- Exception type: `ccxt.RateLimitExceeded`
- Exception message: mentions "rate limit" or "too many requests"
- Timing: 500ms after previous fetch_order call

**If confirmed:**
- Add delay between retry fetch and verification fetch
- Or: Use cached order data from retry logic
- Or: Skip SOURCE 1 if order already verified in retry

### Alternative hypothesis: Race Condition
**Evidence needed:**
- Exception type: `ccxt.OrderNotFound`
- Exception message: mentions "order not found"
- Timing: very short delay after order creation

**If confirmed:**
- Increase initial delay in SOURCE 1
- Add exponential backoff
- Make delay exchange-specific (Binance vs Bybit)

### Other scenarios
- Any other exception type will guide the fix
- Full stack trace will show exact failure point

---

## COMMIT INFO

**Branch:** feature/diagnostic-patch-source1-visibility
**Commit message:**
```
diagnostic(verification): add visibility for SOURCE 1 exceptions

TEMPORARY diagnostic patch to capture SOURCE 1 exceptions that were
invisible with DEBUG logging. Changes ONLY logging levels, no logic changes.

Changes:
- logger.debug → logger.warning (execution flow)
- logger.debug → logger.error (exceptions)
- Added exc_info=True for full stack traces
- Added before/after logs for fetch_order call

Purpose: Diagnose why verification fails with "Order status: False"
See: docs/investigations/VERIFICATION_SOURCE1_FAILURE_FORENSIC_20251029.md

Risk: MINIMAL (logging only)
Duration: TEMPORARY (until root cause found)
```

---

## SUCCESS CRITERIA

This diagnostic patch is SUCCESSFUL if:
1. ✅ We capture the ACTUAL exception type and message
2. ✅ We see the full execution flow of SOURCE 1
3. ✅ We can confirm or reject the rate limiting hypothesis
4. ✅ Bot continues operating normally (no crashes or hangs)

After success, this patch will be:
- ❌ REMOVED (it's temporary)
- ✅ REPLACED with proper fix
- ✅ Proper exception handling added
- ✅ Log levels returned to appropriate levels

---

END OF DIAGNOSTIC PATCH DOCUMENTATION
