# Phase 4: MEDIUM Priority Issues - Design Document

**Status:** 🔄 IN DESIGN
**Priority:** 🟡 MEDIUM - Code quality & maintainability
**Risk:** 🟢 LOW - Non-critical improvements
**Effort:** ~5 hours

---

## 🎯 ПРОБЛЕМА

После завершения критических и высокоприоритетных исправлений (Phases 0-3), остаются **102 MEDIUM priority** проблемы из аудита. Эти проблемы не критичны для работы системы, но влияют на:
- Поддерживаемость кода
- Отказоустойчивость
- Соответствие best practices

---

## 📊 АНАЛИЗ MEDIUM ПРОБЛЕМ

### Из аудита (102 MEDIUM):

| Категория | Количество | Примеры |
|-----------|-----------|---------|
| Type Safety | 40 | Dict access, optional handling |
| Code Complexity | 20 | Magic numbers, long methods |
| Math Safety | 15 | Division checks, boundary conditions |
| Dict Access | 20 | Direct [] instead of .get() |
| Security | 5 | Logging, validation |
| Exception Handling | 12 | Specific exception types |

### Уже исправлено в Phases 0-3:

- ✅ Type Safety: 22 unsafe float() → safe_decimal() (Phase 2.3)
- ✅ Code Complexity: open_position() refactored 393→62 lines (Phase 3.2)
- ✅ Exception Handling: 4 bare except fixed (Phase 3.1)
- ✅ Security: Fixed salt, SQL injection whitelist (Phase 1)

**Осталось для Phase 4:** ~40-50 MEDIUM issues

---

## ✅ РЕШЕНИЕ: 4 Focused Sub-Phases

### Phase 4.1: Dict Access Safety (10 HIGH-RISK cases)
**Effort:** 1-1.5 hours
**Priority:** HIGH within MEDIUM

**Problem:** Direct dict access `dict['key']` raises KeyError if key missing.

**Scope:** Focus on **WebSocket handlers** and **exchange responses** where:
- Data comes from external sources (exchange API, WebSocket)
- Missing keys would crash critical flows
- Silent failures are acceptable (use default/skip)

**NOT in scope:**
- Internal data structures we control
- Config dictionaries that MUST have keys (fail fast is good)
- Database results (schema-controlled)

**Target files (prioritized by risk):**
1. `core/position_manager.py` - WebSocket position updates
2. `websocket/binance_stream.py` - Market data parsing
3. `websocket/bybit_stream.py` - Market data parsing
4. `core/wave_signal_processor.py` - Signal parsing
5. `core/signal_processor_websocket.py` - Signal parsing

**Example Fix:**
```python
# BEFORE (KeyError risk)
mark_price = float(data['markPrice'])
funding = data['fundingRate']

# AFTER (Safe)
mark_price = float(data.get('markPrice', 0))
funding = data.get('fundingRate', 0)
# OR if critical:
if 'markPrice' not in data:
    logger.error(f"Missing markPrice in data: {data}")
    return None
mark_price = float(data['markPrice'])
```

### Phase 4.2: Magic Numbers → Named Constants (15 cases)
**Effort:** 1 hour
**Priority:** MEDIUM

**Problem:** Hardcoded numbers reduce readability and maintainability.

**Scope:** Extract commonly used magic numbers to module-level constants.

**Target categories:**
1. **Time intervals** - 60, 300, 3600, 86400 seconds
2. **Retry limits** - 3, 5, 10 attempts
3. **Percentage thresholds** - 0.1, 0.5, 2.0
4. **Buffer sizes** - 100, 1000 items

**Example Fix:**
```python
# BEFORE
await asyncio.sleep(60)  # What is 60?
if pnl_pct > 0.1:  # 10%?
for attempt in range(3):  # Why 3?

# AFTER (at module top)
HEALTH_CHECK_INTERVAL_SEC = 60
MIN_PNL_ALERT_PERCENT = 0.1  # 10%
MAX_RETRY_ATTEMPTS = 3

# Usage
await asyncio.sleep(HEALTH_CHECK_INTERVAL_SEC)
if pnl_pct > MIN_PNL_ALERT_PERCENT:
for attempt in range(MAX_RETRY_ATTEMPTS):
```

**NOT extracting:**
- Mathematical constants (0, 1, 2 for simple operations)
- One-time use values
- Values that are self-documenting (e.g., `range(100)` in a loop)

### Phase 4.3: Division by Zero Safety (5 HIGH-RISK cases)
**Effort:** 0.5 hour
**Priority:** HIGH within MEDIUM

**Problem:** Division without zero checks can crash.

**Scope:** Add zero checks ONLY where:
- Divisor comes from external data (exchange, user input)
- Division result is critical for trading decisions
- Silent failure is acceptable (use default)

**Target patterns:**
```python
# Pattern 1: PnL calculation
pnl_percent = (exit - entry) / entry  # entry could be 0!

# Pattern 2: Average calculation
avg = total / count  # count could be 0!

# Pattern 3: Ratio calculation
ratio = volume_24h / volume_1h  # denominator could be 0!
```

**Fix Strategy:**
```python
# Strategy 1: Early return
if entry == 0:
    logger.warning("Entry price is zero, cannot calculate PnL%")
    return None
pnl_percent = (exit - entry) / entry

# Strategy 2: Default value
count = max(count, 1)  # Ensure never zero
avg = total / count

# Strategy 3: Safe division helper (if used >3 times)
def safe_divide(numerator: Decimal, denominator: Decimal,
                default: Decimal = Decimal('0')) -> Decimal:
    """Safe division with zero check."""
    if denominator == 0:
        return default
    return numerator / denominator
```

### Phase 4.4: Code Documentation (20 cases)
**Effort:** 2 hours
**Priority:** LOW within MEDIUM

**Problem:** Critical helper methods lack docstrings.

**Scope:** Add docstrings ONLY for:
- Public methods (no underscore prefix)
- Helper methods used in multiple places
- Complex logic that needs explanation

**NOT documenting:**
- One-liner methods
- Self-explanatory getters/setters
- Private methods with obvious purpose

**Target files:**
1. Helper methods in `core/position_manager.py` (the 6 we just created!)
2. Utility functions in `utils/*.py`
3. Public API methods in managers

**Format (Google Style):**
```python
def calculate_position_size(
    balance: Decimal,
    risk_percent: Decimal,
    stop_loss_distance: Decimal
) -> Decimal:
    """
    Calculate position size based on risk management rules.

    Uses fixed-percentage risk model: risk same $ amount per trade.
    Formula: position_size = (balance * risk%) / stop_loss_distance

    Args:
        balance: Available balance in USDT
        risk_percent: Risk per trade (e.g., 0.01 = 1%)
        stop_loss_distance: Distance to stop loss in price %

    Returns:
        Position size in base currency units

    Raises:
        ValueError: If stop_loss_distance is zero

    Example:
        >>> calculate_position_size(Decimal('1000'), Decimal('0.01'), Decimal('0.02'))
        Decimal('500')  # Risk $10 (1% of $1000) with 2% stop = $500 position
    """
    if stop_loss_distance == 0:
        raise ValueError("Stop loss distance cannot be zero")

    risk_amount = balance * risk_percent
    return risk_amount / stop_loss_distance
```

---

## 📋 IMPLEMENTATION PLAN

### Phase 4.1: Dict Access Safety (1-1.5 hours)

**Step 1: Analyze WebSocket handlers (15 min)**
- [ ] Grep for `data\['` in WebSocket files
- [ ] Identify 10 highest-risk cases
- [ ] Document current behavior

**Step 2: Implement fixes (45 min)**
- [ ] Fix position_manager.py WebSocket handler
- [ ] Fix binance_stream.py market data parsing
- [ ] Fix bybit_stream.py market data parsing
- [ ] Fix wave_signal_processor.py
- [ ] Fix signal_processor_websocket.py

**Step 3: Test (15 min)**
- [ ] Syntax check
- [ ] Health check PASS
- [ ] Git commit

### Phase 4.2: Magic Numbers (1 hour)

**Step 1: Identify patterns (20 min)**
- [ ] Grep for common magic numbers
- [ ] Group by category (time, retry, thresholds)
- [ ] Select top 15 for extraction

**Step 2: Extract constants (30 min)**
- [ ] Create constants at module tops
- [ ] Replace magic numbers with constants
- [ ] Add comments explaining values

**Step 3: Test (10 min)**
- [ ] Syntax check
- [ ] Health check PASS
- [ ] Git commit

### Phase 4.3: Division Safety (30 min)

**Step 1: Find divisions (10 min)**
- [ ] Grep for `/` operator
- [ ] Filter to external data sources
- [ ] Identify 5 highest-risk

**Step 2: Add checks (15 min)**
- [ ] Add zero checks or safe_divide()
- [ ] Add logging for edge cases

**Step 3: Test (5 min)**
- [ ] Syntax check
- [ ] Health check PASS
- [ ] Git commit

### Phase 4.4: Documentation (2 hours)

**Step 1: Identify targets (30 min)**
- [ ] List all public methods missing docstrings
- [ ] Prioritize by complexity and usage
- [ ] Select top 20

**Step 2: Write docstrings (1.5 hours)**
- [ ] Document new helper methods from Phase 3.2
- [ ] Document utility functions
- [ ] Document public manager APIs

**Step 3: Review (15 min)**
- [ ] Check format consistency
- [ ] Verify examples work
- [ ] Git commit

---

## 🚨 CRITICAL GUIDELINES

### 1. NO FUNCTIONAL CHANGES
- ❌ Do NOT change logic
- ❌ Do NOT add new features
- ✅ Only add safety checks
- ✅ Only improve readability

### 2. PRESERVE BEHAVIOR
- Use `.get(key, default)` with same default as current behavior
- Add zero checks that return existing default/None
- Constants must have EXACT same values

### 3. MINIMAL SCOPE
- Focus on HIGH-RISK cases only
- Skip LOW-RISK improvements
- 80/20 rule: Fix 20% of issues that cause 80% of risk

### 4. TEST AFTER EACH SUB-PHASE
- Syntax check
- Health check
- Git commit
- Don't batch changes

---

## ⏱️ TIME ESTIMATE

| Phase | Estimate | Cumulative |
|-------|----------|-----------|
| 4.1 Dict Access | 1.5h | 1.5h |
| 4.2 Magic Numbers | 1h | 2.5h |
| 4.3 Division Safety | 0.5h | 3h |
| 4.4 Documentation | 2h | 5h |

**Total: 5 hours**

---

## 🎯 SUCCESS CRITERIA

- ✅ 10+ high-risk dict[] → .get() conversions
- ✅ 15+ magic numbers extracted to constants
- ✅ 5+ division safety checks added
- ✅ 20+ docstrings added (focus on Phase 3.2 helpers)
- ✅ Health check: 14/18 PASS (no regressions)
- ✅ No functional changes (behavior preserved)
- ✅ All changes tested and committed

---

## 🚦 GO/NO-GO DECISION

**Proceed if:**
- ✅ Phases 0-3 complete
- ✅ Health check stable (14/18 PASS)
- ✅ Have 5 hours available
- ✅ No production issues

**Defer if:**
- ❌ Phase 2.1 (emergency_liquidation) needs urgent implementation
- ❌ Phase 3.2 refactoring needs testnet verification first
- ❌ Production issues ongoing

---

**Дата:** 2025-10-09
**Статус:** 🔄 AWAITING APPROVAL
**Approver:** User

**Рекомендация:**
Given that Phase 3.2 refactoring is code-complete but untested on testnet, we have 2 options:

**Option A (Recommended):** Proceed with Phase 4 (low-risk improvements) while Phase 3.2 can be tested in parallel on testnet later.

**Option B:** Pause and test Phase 3.2 on testnet first before continuing with Phase 4.

Since Phase 4 is LOW RISK and doesn't change trading logic, **Option A is recommended** - we can continue improving code quality while deferring integration testing to a dedicated session.
