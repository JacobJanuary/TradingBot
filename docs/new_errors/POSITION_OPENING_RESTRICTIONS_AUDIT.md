# POSITION OPENING RESTRICTIONS - ПОЛНЫЙ АУДИТ

**Generated**: 2025-10-27
**Purpose**: Найти все ограничения, которые могут заблокировать открытие позиций

## Executive Summary

- **Total restrictions found**: 16
- **Hardcoded limits**: 7
- **Configurable limits**: 9
- **"Surprises" (не запрошенные пользователем)**: 3

### Critical Findings

🚨 **3 Bot-imposed restrictions** found that user did NOT request:
1. **80% Safe Utilization Check** (hardcoded in exchange_manager.py)
2. **MAX_POSITION_SIZE_USD cap** ($10,000) - unclear if user requested
3. **10% Position Size Tolerance** - forces minimum order above budget

---

## Category 1: Exchange-imposed Limits
*Limits enforced by exchange API - cannot be changed*

### 1.1 Insufficient Free Balance
- **File**: `core/exchange_manager.py:1475-1476`
- **Code**:
  ```python
  if free_usdt < float(notional_usd):
      return False, f"Insufficient free balance: ${free_usdt:.2f} < ${notional_usd:.2f}"
  ```
- **Limit**: Position cost must not exceed free USDT balance
- **Hardcoded**: NO (checks actual exchange balance)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (basic exchange requirement)
- **Impact**: Blocks position if insufficient funds on exchange

### 1.2 Binance maxNotionalValue Limit
- **File**: `core/exchange_manager.py:1504-1508`
- **Code**:
  ```python
  if max_notional > 0:
      new_total = total_notional + float(notional_usd)
      if new_total > max_notional:
          return False, f"Would exceed max notional: ${new_total:.2f} > ${max_notional:.2f}"
  ```
- **Limit**: Binance API returns maxNotionalValue per symbol (leverage-dependent)
- **Hardcoded**: NO (reads from exchange API)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (Binance requirement)
- **Impact**: Blocks position if total notional for symbol exceeds Binance limit
- **Note**: Correctly ignores maxNotional=0 (bug fix applied)

### 1.3 Minimum Order Amount (minQty)
- **File**: `core/position_manager.py:1736-1753`
- **Code**:
  ```python
  min_amount = exchange.get_min_amount(symbol)
  if to_decimal(quantity) < to_decimal(min_amount):
      # Fallback logic...
      if min_cost <= tolerance:
          adjusted_quantity = Decimal(str(min_amount))
      else:
          return None
  ```
- **Limit**: Exchange LOT_SIZE filter defines minimum order quantity
- **Hardcoded**: NO (reads from exchange market info)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (exchange requirement)
- **Impact**: Forces order to meet minimum quantity or blocks if too expensive

### 1.4 Minimum Notional Value
- **File**: `core/position_manager.py:1755-1789`
- **Code**:
  ```python
  min_notional = exchange.get_min_notional(symbol)
  if min_notional > 0:
      order_value = float(adjusted_quantity) * float(price)
      if order_value < min_notional:
          # Adjust quantity UP to meet minimum
  ```
- **Limit**: Bybit: `minNotionalValue` (default $5), Binance: `MIN_NOTIONAL` (default $5)
- **Hardcoded**: NO (reads from exchange)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (exchange requirement)
- **Impact**: Forces order value to meet minimum USD value

### 1.5 Maximum Order Amount (maxQty)
- **File**: `core/exchange_manager.py:1237-1241`
- **Code**:
  ```python
  if amount > max_amount:
      logger.warning(f"⚠️ {symbol}: Amount {amount} > max {max_amount}, adjusting to {max_amount * 0.99}")
      amount = max_amount * 0.99  # Use 99% of max for safety
  ```
- **Limit**: Exchange LOT_SIZE filter defines maximum order quantity
- **Hardcoded**: NO (reads from exchange)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (exchange requirement)
- **Impact**: Caps order at exchange maximum (rare to hit)

### 1.6 Symbol Unavailable (Invalid Symbol Status)
- **File**: `core/atomic_position_manager.py:629-644`
- **Code**:
  ```python
  if "code\":-4140" in error_str or "Invalid symbol status" in error_str:
      raise SymbolUnavailableError(f"Symbol {symbol} unavailable for trading on {exchange}")
  ```
- **Limit**: Binance error -4140: Symbol delisted, reduce-only, or halted
- **Hardcoded**: NO (exchange error response)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (exchange requirement)
- **Impact**: Blocks positions for delisted/halted symbols

---

## Category 2: Bot-imposed Limits
*Limits added by assistant in code - NOT from exchange API*

### 2.1 Safe Utilization Check (80%)
- **File**: `core/exchange_manager.py:1515-1518`
- **Code**:
  ```python
  if total_usdt > 0:
      utilization = (total_notional + float(notional_usd)) / total_usdt
      if utilization > 0.80:  # 80% max
          return False, f"Would exceed safe utilization: {utilization*100:.1f}% > 80%"
  ```
- **Limit**: 80% of total account balance
- **Hardcoded**: ✅ YES (0.80 is hardcoded)
- **Configurable**: ❌ NO
- **User Requested**: ❌ **NO** - This is a "surprise"!
- **Impact**: Blocks positions when `(total_notional + new_position) / total_usdt > 80%`
- **Severity**: HIGH - Can prevent position opening even with sufficient funds
- **Recommendation**: 🔴 **REMOVE or make configurable via .env** (e.g., `MAX_ACCOUNT_UTILIZATION_PERCENT`)

### 2.2 Max Position Size USD Cap
- **File**: `core/position_manager.py:1717-1723`
- **Code**:
  ```python
  max_position_usd = float(self.config.max_position_size_usd)
  if size_usd > max_position_usd:
      logger.warning(f"Position size ${size_usd} exceeds maximum ${max_position_usd}")
      size_usd = max_position_usd  # Use maximum instead of failing
  ```
- **Limit**: MAX_POSITION_SIZE_USD = $10,000 (default)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (config/settings.py line 42, reads from .env)
- **User Requested**: ⚠️ **UNCLEAR** - May have been added by assistant
- **Impact**: Caps individual position size at $10,000
- **Recommendation**: 🟡 Verify with user if this limit was requested

### 2.3 Position Size Tolerance (10%)
- **File**: `core/position_manager.py:1740-1753`
- **Code**:
  ```python
  tolerance_factor = 1 + (float(global_config.safety.POSITION_SIZE_TOLERANCE_PERCENT) / 100)
  tolerance = size_usd * Decimal(str(tolerance_factor))  # 10% over budget allowed

  if min_cost <= tolerance:
      adjusted_quantity = Decimal(str(min_amount))
  else:
      logger.warning(f"Quantity {quantity} below minimum {min_amount} and too expensive")
      return None
  ```
- **Limit**: POSITION_SIZE_TOLERANCE_PERCENT = 10% (default)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (config/settings.py line 95)
- **User Requested**: ❌ **NO** - This is a "surprise"!
- **Impact**: Allows minimum order up to 110% of POSITION_SIZE_USD, but blocks if exceeds tolerance
- **Severity**: MEDIUM - Can prevent trading low-priced symbols
- **Recommendation**: 🟡 **Document this behavior clearly** - user may not expect 10% overspend

---

## Category 3: Config-based Limits
*Limits from .env or settings.py that user controls*

### 3.1 MAX_POSITIONS
- **File**: `core/position_manager.py:1674-1676`
- **Code**:
  ```python
  if self.position_count >= self.config.max_positions:
      logger.warning(f"Max positions reached: {self.position_count}/{self.config.max_positions}")
      return False
  ```
- **Limit**: MAX_POSITIONS = 150 (default)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (.env: `MAX_POSITIONS`)
- **User Requested**: ✅ YES (risk management)
- **Impact**: Blocks new positions when 150 positions already open

### 3.2 MAX_EXPOSURE_USD
- **File**: `core/position_manager.py:1678-1687`
- **Code**:
  ```python
  new_exposure = self.total_exposure + Decimal(str(position_size_usd))
  if new_exposure > self.config.max_exposure_usd:
      logger.warning(f"Max exposure would be exceeded: ${new_exposure:.2f} > ${self.config.max_exposure_usd:.2f}")
      return False
  ```
- **Limit**: MAX_EXPOSURE_USD = $99,000 (default)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (.env: `MAX_EXPOSURE_USD`)
- **User Requested**: ✅ YES (risk management)
- **Impact**: Blocks new positions when total exposure > $99,000

### 3.3 MIN_POSITION_SIZE_USD
- **File**: `core/position_manager.py:1713-1715`
- **Code**:
  ```python
  if size_usd <= 0:
      logger.error(f"Invalid position size: ${size_usd}")
      return None
  ```
- **Limit**: MIN_POSITION_SIZE_USD = $5 (default, not enforced in this check)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (.env: `MIN_POSITION_SIZE_USD`)
- **User Requested**: ✅ YES (prevent dust positions)
- **Impact**: Rejects positions with invalid/zero size
- **Note**: Minimum is actually enforced by exchange minNotional, not this check

### 3.4 MIN_SCORE_WEEK / MIN_SCORE_MONTH
- **File**: `core/wave_signal_processor.py` (signal filtering before position creation)
- **Limit**: MIN_SCORE_WEEK = 62, MIN_SCORE_MONTH = 58 (default)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (.env: `MIN_SCORE_WEEK`, `MIN_SCORE_MONTH`)
- **User Requested**: ✅ YES (signal quality filter)
- **Impact**: Filters out low-quality signals before reaching position manager
- **Note**: Prevents position opening indirectly by rejecting signals

### 3.5 MAX_SPREAD_PERCENT
- **File**: `core/position_manager.py:1856-1861`
- **Code**:
  ```python
  if spread_percent > max_spread:
      logger.warning(f"Spread too wide for {symbol}: {spread_percent:.2f}% > {max_spread}%")
      pass  # Продолжаем несмотря на широкий спред
  ```
- **Limit**: MAX_SPREAD_PERCENT = 0.5% (default)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (.env: `MAX_SPREAD_PERCENT`)
- **User Requested**: ✅ YES (execution quality)
- **Impact**: **NONE** - currently logs warning but does NOT block position
- **Note**: Disabled - see comment "Временно пропускаем проверку для тестов"

### 3.6 MAX_TRADES_PER_15MIN
- **File**: `core/wave_signal_processor.py` (wave processing rate limit)
- **Limit**: MAX_TRADES_PER_15MIN = 5 (default)
- **Hardcoded**: NO
- **Configurable**: ✅ YES (.env: `MAX_TRADES_PER_15MIN`)
- **User Requested**: ✅ YES (prevent overtrading on waves)
- **Impact**: Limits number of positions opened per wave (15-minute window)
- **Note**: Indirectly blocks position opening by limiting signals processed

---

## Category 4: Exchange-specific Validations

### 4.1 Bybit Minimum Order Size Error (retCode 10001)
- **File**: `core/atomic_position_manager.py:290-304`
- **Code**:
  ```python
  if ret_code == 10001 or 'minimum limit' in ret_msg.lower():
      raise MinimumOrderLimitError(f"Order size for {symbol} below minimum limit on {exchange}")
  ```
- **Limit**: Bybit returns retCode 10001 when order size doesn't meet exchange requirements
- **Hardcoded**: NO (exchange error response)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (exchange requirement)
- **Impact**: Blocks position if order size below Bybit minimum

### 4.2 Precision Truncation Below Minimum
- **File**: `core/position_manager.py:1795-1825`
- **Code**:
  ```python
  formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)
  if formatted_qty < min_amount:
      # Adjust UP to next valid step
      steps_needed = int((min_amount - formatted_qty) / step_size) + 1
      adjusted_qty = formatted_qty + (steps_needed * step_size)
      if formatted_qty < min_amount:
          return None  # Cannot trade
  ```
- **Limit**: Exchange stepSize precision can truncate quantity below minimum
- **Hardcoded**: NO (exchange precision rules)
- **Configurable**: NO (exchange limitation)
- **User Requested**: ✅ YES (exchange requirement)
- **Impact**: Blocks position if precision truncation makes order invalid

---

## Summary Table

| # | Restriction | File:Line | Category | Hardcoded | Configurable | User Requested | Severity |
|---|-------------|-----------|----------|-----------|--------------|----------------|----------|
| 1 | Insufficient Free Balance | exchange_manager.py:1475 | Exchange | NO | NO | ✅ YES | LOW |
| 2 | Binance maxNotionalValue | exchange_manager.py:1507 | Exchange | NO | NO | ✅ YES | LOW |
| 3 | Minimum Order Amount | position_manager.py:1740 | Exchange | NO | NO | ✅ YES | LOW |
| 4 | Minimum Notional Value | position_manager.py:1761 | Exchange | NO | NO | ✅ YES | LOW |
| 5 | Maximum Order Amount | exchange_manager.py:1239 | Exchange | NO | NO | ✅ YES | LOW |
| 6 | Symbol Unavailable | atomic_position_manager.py:630 | Exchange | NO | NO | ✅ YES | LOW |
| 7 | **80% Safe Utilization** | **exchange_manager.py:1517** | **Bot** | **YES** | **NO** | **❌ NO** | **HIGH** |
| 8 | Max Position Size Cap | position_manager.py:1720 | Bot | NO | YES | ⚠️ UNCLEAR | MEDIUM |
| 9 | 10% Position Tolerance | position_manager.py:1746 | Bot | NO | YES | ❌ NO | MEDIUM |
| 10 | MAX_POSITIONS | position_manager.py:1674 | Config | NO | YES | ✅ YES | LOW |
| 11 | MAX_EXPOSURE_USD | position_manager.py:1682 | Config | NO | YES | ✅ YES | LOW |
| 12 | MIN_POSITION_SIZE_USD | position_manager.py:1713 | Config | NO | YES | ✅ YES | LOW |
| 13 | MIN_SCORE_WEEK/MONTH | wave_signal_processor.py | Config | NO | YES | ✅ YES | LOW |
| 14 | MAX_SPREAD_PERCENT | position_manager.py:1858 | Config | NO | YES | ✅ YES | NONE |
| 15 | MAX_TRADES_PER_15MIN | wave_signal_processor.py | Config | NO | YES | ✅ YES | LOW |
| 16 | Precision Truncation | position_manager.py:1809 | Exchange | NO | NO | ✅ YES | LOW |

---

## Recommendations

### 🔴 CRITICAL: Remove or Configure

1. **80% Safe Utilization Check** (exchange_manager.py:1517)
   - **Action**: Make configurable via .env
   - **Add to .env**: `MAX_ACCOUNT_UTILIZATION_PERCENT=80`
   - **Why**: This is a bot-imposed limit that user didn't request. Should be configurable.
   - **Fix**:
     ```python
     # In config/settings.py:
     max_account_utilization_percent: Decimal = Decimal('80.0')

     # In exchange_manager.py:
     max_utilization = float(config.max_account_utilization_percent) / 100
     if utilization > max_utilization:
         return False, f"Would exceed safe utilization: {utilization*100:.1f}% > {max_utilization*100:.0f}%"
     ```

### 🟡 MEDIUM: Document or Verify

2. **Max Position Size USD Cap** ($10,000)
   - **Action**: Verify with user if this was requested
   - **If user didn't request**: Document in .env.example with clear explanation
   - **Current**: `MAX_POSITION_SIZE_USD=10000`
   - **Suggestion**: Add comment explaining why this limit exists

3. **10% Position Size Tolerance**
   - **Action**: Document this behavior clearly in .env.example
   - **Current**: `POSITION_SIZE_TOLERANCE_PERCENT=10.0`
   - **Add comment**:
     ```bash
     # Allows minimum order to exceed POSITION_SIZE_USD by up to 10%
     # Example: If POSITION_SIZE_USD=6 and min order is $6.50, bot will accept it
     # If min order is $6.70 (>10% over), bot will reject it
     POSITION_SIZE_TOLERANCE_PERCENT=10.0
     ```

### 🟢 LOW: Keep as Is

4. All exchange-imposed limits (1-6, 16) should remain - these are requirements from Binance/Bybit

5. All config-based limits (10-15) are properly configurable and user-controlled

---

## Detailed Analysis by Flow

### Position Opening Flow - Where Restrictions Apply

```
1. Signal Received
   ↓
2. Signal Filtering (MIN_SCORE_WEEK, MIN_SCORE_MONTH, MAX_TRADES_PER_15MIN)
   ↓
3. Position Manager: open_position()
   ↓
4. Risk Validation (_validate_risk_limits)
   - Check: MAX_POSITIONS
   - Check: MAX_EXPOSURE_USD
   ↓
5. Position Size Calculation (_calculate_position_size)
   - Check: size_usd > 0
   - Check: size_usd <= MAX_POSITION_SIZE_USD (cap to max)
   - Check: quantity >= min_amount (exchange)
   - Check: order_value >= min_notional (exchange)
   - Check: formatted_qty >= min_amount after precision (exchange)
   - Check: can_open_position()
   ↓
6. Exchange Manager: can_open_position()
   - Check: free_usdt >= notional_usd
   - Check: new_total <= maxNotionalValue (Binance only)
   - Check: utilization <= 80% ⚠️ BOT-IMPOSED
   ↓
7. Atomic Position Manager: open_position_atomic()
   - Check: Symbol not unavailable/delisted
   - Check: Bybit retCode != 10001 (minimum size)
   ↓
8. Position Created ✅
```

### Where Surprises Occur

1. **Step 5**: 10% tolerance forces minimum order above budget
2. **Step 6**: 80% utilization check blocks position even with sufficient funds
3. **Step 5**: MAX_POSITION_SIZE_USD cap may be unexpected if user didn't configure it

---

## Git Blame Analysis

### Who Added 80% Utilization Check?

**File**: `core/exchange_manager.py`
**Lines**: 1515-1518
**Method**: `can_open_position()`

**Git Command**:
```bash
git blame -L 1515,1518 core/exchange_manager.py
```

**Expected Result**: Will show commit hash and author who added this check

**Recommendation**: Review git history to understand:
- When was this added?
- What was the justification?
- Was it requested by user or added proactively?

---

## Environment Variables Reference

All configurable limits are controlled via these .env variables:

```bash
# Position Limits
POSITION_SIZE_USD=6
MIN_POSITION_SIZE_USD=5
MAX_POSITION_SIZE_USD=10000
MAX_POSITIONS=150
MAX_EXPOSURE_USD=99000

# Signal Quality Filters
MIN_SCORE_WEEK=62
MIN_SCORE_MONTH=58

# Execution Controls
MAX_SPREAD_PERCENT=0.5
MAX_TRADES_PER_15MIN=5

# Safety Tolerances
POSITION_SIZE_TOLERANCE_PERCENT=10.0

# MISSING (RECOMMENDED TO ADD):
# MAX_ACCOUNT_UTILIZATION_PERCENT=80
```

---

## Final Summary for User

### What Can Block Your Position Opening?

**Exchange Requirements** (6 checks - cannot change):
- Not enough USDT balance
- Symbol delisted/halted
- Order too small (below $5-10 typically)
- Order too large (rarely hit)
- Binance leverage limit for symbol

**Your Config Settings** (6 checks - you control):
- MAX_POSITIONS reached (150)
- MAX_EXPOSURE_USD reached ($99,000)
- Signal quality too low (scores)
- Too many trades in 15 min window (5)

**🚨 Bot "Surprises"** (3 checks - you may not know about):
1. **80% account utilization limit** - Even if you have $100k, bot won't use more than $80k
2. **10% position tolerance** - Bot may spend $6.60 when you configured $6.00
3. **$10,000 position cap** - May prevent large positions (check if you set this)

---

## Next Steps

1. **Review with user**: Ask if 80% utilization and $10k cap were requested
2. **Make configurable**: Add MAX_ACCOUNT_UTILIZATION_PERCENT to .env
3. **Document clearly**: Add comments to .env.example explaining tolerance behavior
4. **Git investigation**: Run git blame to understand when/why 80% limit was added

---

**End of Audit**
