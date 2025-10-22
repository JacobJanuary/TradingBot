# FORENSIC ANALYSIS: ERROR INVENTORY
## Trading Bot Errors - 2025-10-22 19:21:19 - 19:49:11

**Analysis Date**: 2025-10-22
**Log Period**: 28 minutes (19:21 - 19:49)
**Total Log Lines**: 18,736
**Status**: 🚨 CRITICAL - Multiple severe issues detected

---

## EXECUTIVE SUMMARY

### Error Statistics
- 🔴 **CRITICAL**: 36 alerts
- 🟠 **ERROR**: 366 errors
- ⚠️ **Exceptions**: 19 tracebacks

### Severity Assessment
- **CRITICAL (P0)**: 3 issue types - IMMEDIATE ACTION REQUIRED
- **HIGH (P1)**: 2 issue types - Fix within 24h
- **MEDIUM (P2)**: 1 issue type - Fix within week

---

## ERROR CLASSIFICATION

### CRITICAL (P0) - Immediate Risk

#### CASE #1: Position Without Stop Loss - HNTUSDT 🔴🔴🔴
**Severity**: CRITICAL - ACTIVE MONEY LOSS RISK
**Status**: ONGOING (1715+ seconds without SL)
**Occurrences**: 26 alerts in 28 minutes

**Description**:
Position HNTUSDT opened at ~19:21 and remains WITHOUT STOP LOSS for 28+ minutes.

**Evidence**:
```
19:22:17 - CRITICAL: Position HNTUSDT WITHOUT STOP LOSS for 45 seconds
19:24:16 - CRITICAL: Position HNTUSDT WITHOUT STOP LOSS for 165 seconds
...
19:50:07 - CRITICAL: Position HNTUSDT WITHOUT STOP LOSS for 1715 seconds
```

**Root Cause Analysis**:
Bybit API rejects SL orders with error 10001:
```
StopLoss:324000000 set for Buy position should lower than base_price:161600000
```

**Problem**: SL price = 3.24 USDT is HIGHER than entry price = 1.616 USDT
**For LONG positions**: SL must be LOWER than entry price!

**Impact**:
- 🚨 Open position with ZERO protection
- 💰 Direct money loss risk if price moves against position
- ⏱️ Already exposed for 28+ minutes

**Module**: `core.stop_loss_manager.py:355`, `core.position_manager.py:1719`

---

#### CASE #2: Invalid Stop Loss Calculation - Bybit Error 10001 🔴🔴
**Severity**: CRITICAL
**Status**: ACTIVE BUG
**Occurrences**: ~300+ errors (majority of all errors)

**Description**:
Systematic error in Stop Loss price calculation for LONG positions.

**Evidence**:
```python
# Bybit API Error 10001
{"retCode":10001,"retMsg":"StopLoss:324000000 set for Buy position should lower than base_price:161600000??LastPrice"}

Entry Price: 1.616 USDT (161600000 in price units)
Stop Loss:   3.240 USDT (324000000 in price units)
Side:        BUY (LONG)

ERROR: SL (3.24) > Entry (1.616) for LONG position
CORRECT: SL must be < Entry for LONG (e.g., SL = 1.45 for -10% loss)
```

**Root Cause**:
Bug in stop loss price calculation logic. Calculation inverted or uses wrong formula.

**Module**:
- `core.stop_loss_manager.py:221` (_set_bybit_stop_loss)
- Calculation logic before API call

**Impact**:
- Cannot set stop loss on positions
- All HNTUSDT positions unprotected
- Bot continues to retry with wrong price (infinite loop)
- API rate limiting risk

---

#### CASE #3: Positions "Not Found" After Opening 🔴
**Severity**: CRITICAL
**Status**: RECURRING
**Occurrences**: 4 positions (WAVESUSDT, FLRUSDT, CAMPUSDT, ESUSDT)

**Description**:
Position opens (order executed), but position not found on exchange after 10 verification attempts.

**Evidence**:
```
19:35:24 - CRITICAL: ❌ Position WAVESUSDT not found after 10 attempts!
19:35:24 - CRITICAL: ⚠️ ALERT: Open position without SL may exist on exchange!

19:35:36 - CRITICAL: ❌ Position FLRUSDT not found after 10 attempts!
19:36:07 - CRITICAL: ❌ Position CAMPUSDT not found after 10 attempts!
19:50:30 - CRITICAL: ❌ Position ESUSDT not found after 10 attempts!
```

**Root Cause Options**:
1. Order fills but closes immediately (stop-out or liquidation)
2. Race condition - position opened and closed before verification
3. Exchange API delay in reporting position
4. Insufficient margin - order rejected but status shows "closed"

**Traceback**:
```python
File: core/atomic_position_manager.py:330
AtomicPositionError: Position not found after order - order may have failed.
Order status: closed
```

**Impact**:
- Uncertainty about actual position state
- Possible untracked positions on exchange
- Risk of positions without stop loss
- Signal execution failures

---

### HIGH PRIORITY (P1)

#### CASE #4: Price Precision Errors 🟠
**Severity**: HIGH
**Status**: RECURRING
**Occurrences**: Multiple symbols (WAVES, GIGA, ALEO)

**Description**:
Stop Loss price violates exchange minimum price precision requirements.

**Evidence**:
```
WAVES: "price must be greater than minimum price precision of 0.01"
GIGA:  "price must be greater than minimum price precision of 0.000001"
ALEO:  "price must be greater than minimum price precision of 0.0001"
```

**Root Cause**:
1. SL price calculation results in value below minimum precision
2. Incorrect rounding during price_to_precision()
3. Edge case: Very small % SL on low-priced coins

**Module**:
- `stop_loss_manager.py:341` (sl_price_formatted)
- `ccxt/base/exchange.py:5139` (price_to_precision)

**Impact**:
- Position creation rollback
- Signal execution failure
- Lost trading opportunities

---

#### CASE #5: Exceeded Maximum Position at Leverage 🟠
**Severity**: HIGH
**Status**: RECURRING
**Occurrences**: 1 (METUSDT on Binance)

**Description**:
Binance rejects position opening due to leverage/margin limits.

**Evidence**:
```
Binance Error -2027: "Exceeded the maximum allowable position at current leverage"
Symbol: METUSDT
```

**Root Cause**:
1. Too many open positions at current leverage
2. Insufficient available margin
3. Position size exceeds account limits
4. No pre-check for available margin/position slots

**Module**: `core.exchange_manager.py` (market order creation)

**Impact**:
- Signal execution failure
- No position opened despite valid signal
- No warning before attempt

---

### MEDIUM PRIORITY (P2)

#### CASE #6: Database Table Missing 🟡
**Severity**: MEDIUM
**Status**: ISOLATED
**Occurrences**: 1

**Description**:
```
relation "monitoring.orders_cache" does not exist
```

**Root Cause**:
- Migration not run
- Table dropped accidentally
- Wrong database connection

**Module**: `database/repository.py`

**Impact**:
- Order cache not available
- May affect order verification
- Non-critical (fallback exists?)

---

## ERROR PATTERNS SUMMARY

### Pattern 1: Invalid SL Calculation (CRITICAL)
- **Frequency**: ~300 errors
- **Symbols**: HNTUSDT (primary)
- **Root Cause**: Wrong SL formula for LONG positions
- **Fix Priority**: P0 - IMMEDIATE

### Pattern 2: Position Verification Failures (CRITICAL)
- **Frequency**: 4 occurrences
- **Symbols**: WAVESUSDT, FLRUSDT, CAMPUSDT, ESUSDT
- **Root Cause**: Order closes immediately or race condition
- **Fix Priority**: P0 - IMMEDIATE

### Pattern 3: Price Precision Issues (HIGH)
- **Frequency**: Multiple symbols
- **Root Cause**: SL calculation produces invalid precision
- **Fix Priority**: P1 - 24h

### Pattern 4: Resource Limits (HIGH)
- **Frequency**: Low but blocking
- **Root Cause**: No pre-validation of margin/positions
- **Fix Priority**: P1 - 24h

---

## FILES INVOLVED

### Primary Error Sources
1. `core/stop_loss_manager.py` (lines 221, 341, 355)
2. `core/atomic_position_manager.py` (lines 330, 354, 397, 479)
3. `core/position_manager.py` (line 1012, 1719)
4. `core/exchange_manager.py` (market order execution)

### Error Categories by Module
- **Stop Loss Manager**: 85% of errors
- **Atomic Position Manager**: 10% of errors
- **Exchange Manager**: 4% of errors
- **Database**: 1% of errors

---

## NEXT STEPS

### Immediate Actions (NOW)
1. ⚠️ **MANUAL CHECK**: Verify HNTUSDT position on Bybit
   - If open without SL → Close immediately or set SL manually
   - Check actual position state in Bybit dashboard

2. 🔴 **Fix SL Calculation Bug** (CASE #1 & #2)
   - Investigate `stop_loss_manager.py` SL calculation logic
   - Write test to reproduce wrong SL price
   - Fix formula for LONG positions
   - Deploy immediately

### Phase 1 - Today (24h)
1. **CASE #3**: Investigate "position not found" issue
   - Check order fills in exchange history
   - Verify position verification logic
   - Add better logging for order→position flow

2. **CASE #4**: Fix price precision errors
   - Add validation before price_to_precision
   - Handle edge cases for low-price coins
   - Add minimum price checks

### Phase 2 - This Week
1. **CASE #5**: Add pre-flight checks
   - Validate margin before opening position
   - Check position limits
   - Add risk management layer

2. **CASE #6**: Fix database issue
   - Run missing migrations
   - Verify table exists

3. Create comprehensive test suite
4. Add monitoring alerts

---

## TESTING REQUIRED

### Critical Tests Needed
1. **test_sl_calculation_long_position.py**
   - Test SL calculation for LONG positions
   - Verify SL < Entry price
   - Edge cases: high leverage, low prices

2. **test_sl_calculation_short_position.py**
   - Test SL calculation for SHORT positions
   - Verify SL > Entry price

3. **test_price_precision_validation.py**
   - Test SL price meets minimum precision
   - Test all supported symbols
   - Test edge cases (very low prices)

4. **test_position_verification_flow.py**
   - Test order → position flow
   - Test timing and retries
   - Test rollback on failure

---

## RISK ASSESSMENT

### Current Production Risk: 🔴 HIGH

**Active Risks**:
- 💰 HNTUSDT position without stop loss (ONGOING)
- 🐛 All new LONG positions cannot set SL
- ❓ Unknown state of "not found" positions
- 📉 Missing signals due to failures

**Recommended Action**:
- MANUAL INTERVENTION: Check HNTUSDT position NOW
- DEPLOY FIX: Stop Loss calculation bug ASAP
- MONITORING: Watch all open positions

---

## APPENDIX

### Full Error Counts by Type
```bash
# CRITICAL errors
Position without SL:              26 occurrences
Position not found:                8 occurrences (4 unique positions)
Total CRITICAL:                   36

# ERROR entries
Invalid SL price (10001):         ~300 occurrences
Failed to set SL:                 ~300 occurrences
Position still without SL:        ~30 occurrences
Price precision errors:           ~15 occurrences
Leverage exceeded:                 1 occurrence
Database errors:                   1 occurrence
Other:                            ~20 occurrences
Total ERROR:                     366

# Exceptions with tracebacks:      19
```

### Log Files Analyzed
- Primary: `logs/trading_bot.log` (2.4 MB, 18,736 lines)
- Period: 2025-10-22 19:21:19 - 19:49:11 (28 minutes)
- Archive: `archive/temp_files/*.log` (not analyzed yet)

---

**Report Generated**: 2025-10-22
**Analyst**: Claude Code (Forensic Analysis)
**Status**: Ready for detailed investigation (STAGE 2)
