# ⚡ QUICK SUMMARY: Errors After Migration

**Date**: 2025-10-28
**Total Errors**: 19
**Real Bugs**: 2
**False Positives**: 15
**Expected**: 2

---

## 🔴 2 REAL BUGS FOUND (Need Fixing)

### Bug #1: Minimum Order Size Not Enforced 🔴 HIGH PRIORITY

**What Happened**:
- BSVUSDT: Bot tried to open $4.51 position, but Binance requires minimum $5
- YFIUSDT: Same issue
- Positions failed to open

**Why**:
```
Target: $6.00 USD
After rounding: 0.2 quantity
Actual notional: 0.2 * $22.55 = $4.51 USD ← BELOW $5 minimum!
Binance: REJECTED
```

**Impact**:
- 2 trade opportunities lost
- Not critical (atomic rollback worked correctly)
- But wastes signals

**Fix Required**:
- Add minimum notional check after quantity rounding
- Either increase quantity to meet minimum OR skip position with warning
- File: `core/position_manager.py`

---

### Bug #2: Bybit API Category Parameter Error 🟡 MEDIUM PRIORITY

**What Happened**:
- When verifying positions on Bybit, API call fails
- Error: "category only support linear or option"
- Happens for BEAMUSDT, HNTUSDT

**Why**:
- Bybit API requires `category: 'linear'` parameter
- Bot doesn't provide it
- Position verification fails (but trading continues!)

**Impact**:
- ⚠️ Warning logged
- ✅ Stop-loss still placed successfully
- ⚠️ Position not verified (small risk)

**Fix Required**:
- Add `category: 'linear'` parameter to Bybit API calls
- File: `core/atomic_position_manager.py`

---

## ✅ 15 FALSE POSITIVES (Not Real Errors)

### "Leverage Not Modified" (12+ times)

**What It Looks Like**:
```
ERROR - bybit {"retCode":110043,"retMsg":"leverage not modified"}
INFO - ✅ Leverage already at 1x for ZBCNUSDT on bybit
```

**Why This Happens**:
- Bybit returns ERROR if leverage is already at target value
- This is normal Bybit behavior
- Bot handles it correctly

**Fix**: Optional cosmetic (change ERROR to INFO)

---

## ⚠️ 2 EXPECTED WARNINGS (Working As Designed)

### Side Mismatch on Startup (IOTAUSDT, TNSRUSDT)

**What It Looks Like**:
```
ERROR - IOTAUSDT: SIDE MISMATCH DETECTED!
  TS side (from DB): short
  Position side (exchange): long
INFO - ✅ IOTAUSDT: TS CREATED - side=long
```

**Why This Happens**:
- Old position was SHORT, now new position is LONG
- Stale TS state in DB (from previous position)
- Bot correctly deletes old TS and creates new one

**Fix**: None needed - working as designed

---

## 🎯 VERDICT

**Migration Status**: ✅ **SUCCESS** - Migration is working correctly!

**Evidence**:
- Trailing params ARE being loaded from DB ✅
- Positions ARE saving trailing params ✅
- Per-exchange params working ✅
- Atomic operations working ✅

**Bugs Found**:
- 2 pre-existing bugs (not related to migration)
- 1 HIGH priority (min order size)
- 1 MEDIUM priority (bybit API)

**Recommendation**:
1. ✅ Migration is STABLE - can continue running
2. 🔴 Fix Bug #1 (min order size) - HIGH priority
3. 🟡 Fix Bug #2 (bybit API) - MEDIUM priority
4. 🟢 Cosmetic fix for false positives - LOW priority

---

## 📋 FULL DETAILS

See: `docs/investigations/ERRORS_AFTER_MIGRATION_DEEP_INVESTIGATION_20251028.md`
- Complete tracebacks
- Root cause analysis
- Detailed fix plans
- Pseudocode examples
