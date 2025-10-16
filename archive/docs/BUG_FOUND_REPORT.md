# BUG FOUND - TRAILING STOP FAILURE ROOT CAUSE

**Date:** 2025-10-16 01:15:00
**Status:** 🎯 100% CONFIRMED - EXCEPTION CAUGHT
**Time to Find:** 10 minutes (as predicted in Option 1)

---

## EXECUTIVE SUMMARY

**Root Cause:** `TypeError: unsupported operand type(s) for -: 'float' and 'decimal.Decimal'`

**Location:** `core/position_manager.py`, lines 1546 and 1550

**Impact:** Exception silently raised in `_on_position_update()`, preventing execution of trailing stop logic.

**Confidence:** 100% - Exception caught in production logs with full traceback.

---

## EXCEPTION DETAILS

### Full Error Message

```
TypeError: unsupported operand type(s) for -: 'float' and 'decimal.Decimal'

Traceback (most recent call last):
  File "core/position_manager.py", line 1546, in _on_position_update
    (position.current_price - position.entry_price) / position.entry_price * 100
     ~~~~~~~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~
TypeError: unsupported operand type(s) for -: 'float' and 'decimal.Decimal'
```

### Affected Lines

**Line 1546 (LONG positions):**
```python
position.unrealized_pnl_percent = (
    (position.current_price - position.entry_price) / position.entry_price * 100
)
```

**Line 1550 (SHORT positions):**
```python
position.unrealized_pnl_percent = (
    (position.entry_price - position.current_price) / position.entry_price * 100
)
```

---

## ROOT CAUSE ANALYSIS

### Type Mismatch Origin

1. **Database Schema:**
   - `entry_price` stored as `numeric(20,8)` in PostgreSQL
   - `current_price` stored as `numeric(20,8)` in PostgreSQL

2. **Loading from Database (line 369):**
   ```python
   position_state = PositionState(
       entry_price=pos['entry_price'],  # ← Returns Decimal from psycopg2
       current_price=pos['current_price'] or pos['entry_price'],
   )
   ```
   PostgreSQL `numeric` type → Python `Decimal` via psycopg2

3. **WebSocket Update (line 1533):**
   ```python
   position.current_price = data.get('mark_price', position.current_price)
   ```
   WebSocket `mark_price` → Python `float`

4. **Result:**
   - `position.entry_price` = `Decimal` (from DB)
   - `position.current_price` = `float` (from WebSocket)
   - **Arithmetic between Decimal and float = TypeError**

---

## EVIDENCE

### Test Results

**Test Date:** 2025-10-16 01:12:46 - 01:13:09

**Exceptions Caught:** 20+ occurrences

**Affected Symbols:**
- BANKUSDT (float - Decimal)
- 1000BONKUSDT (Decimal - float)
- SKLUSDT (float - Decimal)
- TAKEUSDT (Decimal - float)
- SAFEUSDT (Decimal - float)

**Execution Stats:**
- ✅ EXEC_CHECK: 101 occurrences
- ❌ LOCK_CHECK: 0 occurrences (exception prevents reaching this line)
- ❌ update_price calls: 0

### Log Excerpts

```
2025-10-16 01:12:46,682 - ERROR - 🔴 CRITICAL EXCEPTION between EXEC_CHECK and LOCK_CHECK for BANKUSDT:
TypeError: unsupported operand type(s) for -: 'float' and 'decimal.Decimal'

2025-10-16 01:12:46,689 - ERROR - 🔴 CRITICAL EXCEPTION between EXEC_CHECK and LOCK_CHECK for 1000BONKUSDT:
TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'
```

---

## WHY EXCEPTION WAS SILENT BEFORE

### Event Router Behavior

**File:** `websocket/event_router.py`

**Code:**
```python
await asyncio.gather(*tasks, return_exceptions=True)
```

The `return_exceptions=True` parameter prevents exceptions from propagating, catching them silently. This is why:
- No crash logs appeared
- No traceback in logs
- Function execution simply stopped
- Trailing stop logic never executed

---

## FIX REQUIRED

### Option 1: Convert to Float at Assignment (SIMPLEST)

**File:** `core/position_manager.py`, line 1533

**Change:**
```python
# BEFORE:
position.current_price = data.get('mark_price', position.current_price)

# AFTER:
position.current_price = float(data.get('mark_price', position.current_price))
```

**Pros:** Minimal change, surgical fix
**Cons:** Loses precision (but acceptable for price display)

---

### Option 2: Convert to Decimal at Assignment

**File:** `core/position_manager.py`, line 1533

**Change:**
```python
# BEFORE:
position.current_price = data.get('mark_price', position.current_price)

# AFTER:
from decimal import Decimal
mark_price = data.get('mark_price', position.current_price)
position.current_price = Decimal(str(mark_price)) if mark_price else position.current_price
```

**Pros:** Preserves precision
**Cons:** Slightly more complex, requires import

---

### Option 3: Convert Both in Calculation (SAFEST)

**File:** `core/position_manager.py`, lines 1545-1551

**Change:**
```python
# BEFORE:
if position.side == 'long':
    position.unrealized_pnl_percent = (
        (position.current_price - position.entry_price) / position.entry_price * 100
    )
else:
    position.unrealized_pnl_percent = (
        (position.entry_price - position.current_price) / position.entry_price * 100
    )

# AFTER:
if position.side == 'long':
    position.unrealized_pnl_percent = (
        (float(position.current_price) - float(position.entry_price)) / float(position.entry_price) * 100
    )
else:
    position.unrealized_pnl_percent = (
        (float(position.entry_price) - float(position.current_price)) / float(position.entry_price) * 100
    )
```

**Pros:** Guarantees type safety at calculation point, no side effects elsewhere
**Cons:** Verbose

---

### Option 4: Fix PositionState Type Annotation (CORRECT BUT EXTENSIVE)

**File:** `core/position_manager.py`, line 104-105

**Change:**
```python
# BEFORE:
entry_price: float
current_price: float

# AFTER:
from decimal import Decimal
entry_price: Decimal
current_price: Decimal
```

**Pros:** Correct type annotation matching DB schema
**Cons:** May require changes throughout codebase where these fields are used

---

## RECOMMENDED FIX

**Use Option 1 (Convert to Float at Assignment)**

**Reasoning:**
1. ✅ Minimal change (1 line)
2. ✅ Surgical precision - fixes exact point of type mismatch
3. ✅ No impact on other code
4. ✅ WebSocket prices are already float, just preserving that
5. ✅ Follows "If it ain't broke, don't fix it" principle

**Implementation:**

```python
# File: core/position_manager.py
# Line: 1533

# OLD:
position.current_price = data.get('mark_price', position.current_price)

# NEW:
position.current_price = float(data.get('mark_price', position.current_price))
```

---

## VERIFICATION PLAN

After applying fix:

1. **Clear cache:**
   ```bash
   find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
   ```

2. **Start bot:**
   ```bash
   python main.py > bot_fix_test.log 2>&1 &
   ```

3. **Wait 60 seconds**

4. **Check logs:**
   ```bash
   # Should be 0 now:
   grep -c "🔴 CRITICAL EXCEPTION" logs/trading_bot.log

   # Should be > 0:
   grep -c "\[LOCK_CHECK\]" logs/trading_bot.log
   grep -c "update_price called" logs/trading_bot.log

   # Verify TS activation:
   psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c \
     "SELECT symbol, state, highest_price, entry_price
      FROM monitoring.trailing_stop_state
      WHERE symbol = 'BANKUSDT';"

   # highest_price should be > entry_price after 60s
   ```

---

## TIMELINE

| Time | Event |
|------|-------|
| 01:04:00 | DEEP_INVESTIGATION_REPORT completed - recommended Option 1 (exception handler) |
| 01:08:00 | Exception handler added to lines 1539-1557 |
| 01:12:00 | Bot started with exception handler |
| 01:13:00 | **20+ exceptions caught with full traceback** |
| 01:15:00 | Root cause identified: Decimal/float type mismatch |

**Total Time:** 11 minutes from start to diagnosis

---

## LESSONS LEARNED

1. **Exception handling critical for debugging:** Without try-except, issue would remain invisible due to `return_exceptions=True` in event router.

2. **Type consistency matters:** PostgreSQL numeric → Python Decimal, but WebSocket → float. Must ensure consistency at boundaries.

3. **Database types propagate:** psycopg2 automatically converts PostgreSQL numeric to Python Decimal - must account for this.

4. **Diagnostic logging pays off:** EXEC_CHECK/LOCK_CHECK pattern immediately narrowed problem to 16 lines.

---

## STATUS

✅ **Root cause identified with 100% certainty**
⏳ **Awaiting user approval to apply fix**
🎯 **Estimated fix time: 2 minutes**
🧪 **Estimated verification time: 3 minutes**

---

**Report Generated:** 2025-10-16 01:15:00
**Investigator:** Claude Code
**Next Step:** Apply recommended fix (Option 1) with user approval
