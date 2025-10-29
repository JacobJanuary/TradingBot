# OBSOLETE ENV VARIABLES - Deep Investigation & Cleanup Plan

**Date**: 2025-10-28
**Issue**: Unused environment variables remain after per-exchange refactoring
**Status**: 🔍 **INVESTIGATION COMPLETE**

---

## 🎯 EXECUTIVE SUMMARY

**Problem**: 4 environment variables defined in `.env` are no longer used after per-exchange wave processing refactoring

**Obsolete Variables**:
1. `MIN_SCORE_WEEK=62` - **100% unused**
2. `MIN_SCORE_MONTH=58` - **100% unused**
3. `MAX_TRADES_PER_15MIN=5` - **Partially used** (fallback only)
4. `SIGNAL_BUFFER_PERCENT=50` - **Legacy usage** (old WaveSignalProcessor only)

**Impact**: **LOW** - No functionality issues, but creates confusion for configuration

**Action Required**: Safe cleanup of obsolete variables

---

## 📊 DETAILED ANALYSIS

### Variable 1: MIN_SCORE_WEEK

**Definition**: Minimum weekly score for signal filtering
**Default Value**: 62
**Current Status**: ❌ **COMPLETELY UNUSED**

#### Where Defined

**File**: `config/settings.py`
**Lines**: 71, 250

```python
# Line 71: Class definition
min_score_week: int = 62

# Line 250: Environment loading
if val := os.getenv('MIN_SCORE_WEEK'):
    config.min_score_week = int(val)
```

#### Where Used

**Production Code**: ❌ **NOT USED**
```bash
$ grep -rn "min_score_week" --include="*.py" core/ main.py
# No results
```

**Tests**: ✅ Used in tests
- `tests/test_phase0_config_defaults.py:33` - Checks default value

**Documentation**: Found in 8 files (historical references only)

#### Historical Context

**Previous Use**: Signal filtering based on weekly score
**Replaced By**: Per-exchange parameters from database (monitoring.params)
**Migration Date**: ~2025-10-27 (per-exchange refactoring)

---

### Variable 2: MIN_SCORE_MONTH

**Definition**: Minimum monthly score for signal filtering
**Default Value**: 58
**Current Status**: ❌ **COMPLETELY UNUSED**

#### Where Defined

**File**: `config/settings.py`
**Lines**: 72, 252

```python
# Line 72: Class definition
min_score_month: int = 58

# Line 252: Environment loading
if val := os.getenv('MIN_SCORE_MONTH'):
    config.min_score_month = int(val)
```

#### Where Used

**Production Code**: ❌ **NOT USED**
```bash
$ grep -rn "min_score_month" --include="*.py" core/ main.py
# No results
```

**Tests**: ✅ Used in tests
- `tests/test_phase0_config_defaults.py:34` - Checks default value

**Documentation**: Found in historical docs only

#### Historical Context

**Previous Use**: Signal filtering based on monthly score
**Replaced By**: Per-exchange parameters from database
**Migration Date**: ~2025-10-27

---

### Variable 3: MAX_TRADES_PER_15MIN

**Definition**: Maximum trades per wave (15 min interval)
**Default Value**: 5
**Current Status**: ⚠️ **PARTIALLY USED** (fallback only)

#### Where Defined

**File**: `config/settings.py`
**Lines**: 77, 257-258, 263

```python
# Line 77: Class definition
max_trades_per_15min: int = 5

# Line 257-258: Environment loading
if val := os.getenv('MAX_TRADES_PER_15MIN'):
    config.max_trades_per_15min = int(val)

# Line 263: Logging
logger.info(f"Wave limits: max_trades={config.max_trades_per_15min}, buffer={...}")
```

#### Where Used

**Production Code**: ⚠️ **LIMITED USE**

1. **WaveSignalProcessor** (`core/wave_signal_processor.py:49`):
   ```python
   self.max_trades_per_wave = int(getattr(config, 'max_trades_per_15min', 10))
   ```
   - Used to initialize `max_trades_per_wave`
   - This value is then used as **fallback**

2. **SignalProcessorWebSocket** (`core/signal_processor_websocket.py:591, 683`):
   ```python
   # Line 591: Fallback when DB params fail
   'max_trades_filter': self.wave_processor.max_trades_per_wave,

   # Line 683: Config fallback
   config_fallback = self.wave_processor.max_trades_per_wave
   ```

**Usage Pattern**:
```
Config Value (5) → WaveSignalProcessor.max_trades_per_wave → Fallback when DB params = NULL
```

**Actual Usage in Production**:
- **Primary Source**: `monitoring.params` database table (per-exchange)
- **Fallback**: Only if DB query fails or returns NULL
- **Frequency**: Rare (DB should always have params)

---

### Variable 4: SIGNAL_BUFFER_PERCENT

**Definition**: Buffer percentage for signal selection (old logic)
**Default Value**: 50.0
**Current Status**: ⚠️ **LEGACY USAGE** (old WaveSignalProcessor only)

#### Where Defined

**File**: `config/settings.py`
**Lines**: 80, 259-260, 263

```python
# Line 80: Class definition
signal_buffer_percent: float = 50.0

# Line 259-260: Environment loading
if val := os.getenv('SIGNAL_BUFFER_PERCENT'):
    config.signal_buffer_percent = float(val)

# Line 263: Logging
logger.info(f"... buffer={getattr(config, 'signal_buffer_percent', 33)}%")
```

#### Where Used

**Production Code**: ⚠️ **OLD LOGIC ONLY**

1. **WaveSignalProcessor** (`core/wave_signal_processor.py:50, 54`):
   ```python
   # Line 50: Load config
   self.buffer_percent = float(getattr(config, 'signal_buffer_percent', 33))

   # Line 54: Calculate buffer
   self.buffer_size = int(self.max_trades_per_wave * (1 + self.buffer_percent / 100))
   ```

**Example**:
- max_trades = 5
- buffer_percent = 50%
- buffer_size = 5 * (1 + 50/100) = 5 * 1.5 = 7.5 → 7

**New Logic (Per-Exchange)**:
```python
# core/signal_processor_websocket.py:621, 642, 661, 705, 718
buffer_size = max_trades + 3  # Fixed +3 buffer (NOT percentage!)
```

**Comparison**:

| max_trades | Old Buffer (50%) | New Buffer (+3) | Difference |
|------------|------------------|-----------------|------------|
| 4 | 6 (4*1.5) | 7 (4+3) | +1 |
| 5 | 7 (5*1.5) | 8 (5+3) | +1 |
| 6 | 9 (6*1.5) | 9 (6+3) | 0 |
| 10 | 15 (10*1.5) | 13 (10+3) | -2 |

**Current Production Behavior**:
- **New logic**: Fixed +3 buffer (lines 621, 642, 661, 705, 718)
- **Old logic**: Only used by WaveSignalProcessor for duplicate checking
- **Impact**: WaveSignalProcessor.buffer_size is calculated but **NOT used** for per-exchange selection

---

## 🔍 USAGE MAPPING

### Complete Call Chain

```
┌─────────────────────────────────────────────────┐
│           Per-Exchange Processing               │
│        (NEW LOGIC - Production Active)          │
└─────────────────────────────────────────────────┘
                     │
                     ↓
    core/signal_processor_websocket.py
                     │
    Step 1: Get params per exchange (lines 677-731)
                     │
         ┌───────────┴───────────┐
         │                       │
         ↓                       ↓
    From Database           From Config (Fallback)
  monitoring.params         config.max_trades_per_15min
  (exchange_id=1,2)              ↓
         │                  max_trades = 5 (default)
         │                       │
         ↓                       ↓
  max_trades = 6 (Binance)    buffer_size = max_trades + 3
  max_trades = 4 (Bybit)           ↓
         │                    8 signals selected
         ↓
  buffer_size = max_trades + 3
         │
         ↓
  9 signals (Binance)
  7 signals (Bybit)
         │
         ↓
    Step 2: Validate signals (lines 940-943)
         │
         ↓
┌─────────────────────────────────────────────────┐
│          WaveSignalProcessor                    │
│        (OLD LOGIC - Validation Only)            │
└─────────────────────────────────────────────────┘
         │
    process_wave_signals()
         │
    Uses buffer_size = max_trades * 1.5  ← OLD
    (Calculated but NOT used for selection)
         │
    Only for: Duplicate checking
         │
         ↓
    Returns: successful, failed, skipped signals
```

---

## 🚨 RISK ASSESSMENT

### Risk: Removing Variables

**Overall Risk**: **VERY LOW**

#### MIN_SCORE_WEEK, MIN_SCORE_MONTH

**Risk**: ✅ **ZERO RISK**
- Not used anywhere in production code
- Only in tests (test needs update)
- No functionality depends on these

**Evidence**:
```bash
$ grep -rn "min_score_week\|min_score_month" core/ main.py
# No matches - 100% unused
```

---

#### MAX_TRADES_PER_15MIN

**Risk**: ⚠️ **LOW RISK** (fallback usage)

**Current Role**: Fallback when DB params unavailable

**Scenarios**:

1. **Normal Operation** (99% of time):
   - DB has params for exchange_id=1,2
   - Variable NOT used
   - No impact

2. **DB Failure** (rare):
   - DB query fails
   - Falls back to `config.max_trades_per_15min`
   - **Without this var**: Would use hardcoded default (10)

**Migration Path**:
- Replace with hardcoded default in code
- Or keep as config.py constant (not env var)

---

#### SIGNAL_BUFFER_PERCENT

**Risk**: ⚠️ **LOW RISK** (legacy logic)

**Current Role**:
- Used by WaveSignalProcessor.buffer_size
- But this buffer_size is **NOT used** for per-exchange selection
- Only affects internal WaveSignalProcessor logic (duplicate checking)

**Impact if Removed**:
- WaveSignalProcessor would use default (33%)
- No impact on per-exchange processing (uses fixed +3)
- Duplicate checking might behave slightly different

---

## 📋 CLEANUP PLAN

### Phase 1: MIN_SCORE Variables (SAFE)

**Variables to Remove**:
- `MIN_SCORE_WEEK`
- `MIN_SCORE_MONTH`

**Files to Modify**:
1. `config/settings.py` (4 lines)
2. `tests/test_phase0_config_defaults.py` (2 lines)
3. `.env` (2 lines)
4. `.env.clean` (2 lines, if exists)

**Steps**:
1. Remove from config class definition (lines 71-72)
2. Remove from env loading (lines 249-252)
3. Remove from test assertions
4. Remove from .env files
5. Add to documentation as "removed variables"

**Risk**: ✅ ZERO
**Rollback**: Simple (add back if needed)

---

### Phase 2: MAX_TRADES_PER_15MIN (CAREFUL)

**Variable to Remove/Replace**: `MAX_TRADES_PER_15MIN`

**Option A: Replace with Constant** (RECOMMENDED)
```python
# config/settings.py
class TradingConfig(BaseModel):
    # Remove from env-loaded fields
    # Add as constant
    MAX_TRADES_FALLBACK: int = 5  # Used when DB params unavailable
```

**Option B: Keep as Config Field** (SAFE)
```python
# Keep current implementation
# But document as "fallback only"
max_trades_per_15min: int = 5  # Fallback when DB params unavailable
```

**Recommendation**: **Option B** - Keep but document purpose

**Why**:
- Acts as safety fallback
- Allows runtime override if needed
- Minimal code change
- Zero risk

---

### Phase 3: SIGNAL_BUFFER_PERCENT (OPTIONAL)

**Variable**: `SIGNAL_BUFFER_PERCENT`

**Current Use**: Legacy WaveSignalProcessor only

**Options**:

**Option A: Remove and Use Default**
```python
# core/wave_signal_processor.py:50
# Before:
self.buffer_percent = float(getattr(config, 'signal_buffer_percent', 33))

# After:
self.buffer_percent = 33.0  # Fixed default (per-exchange uses +3)
```

**Option B: Keep for WaveSignalProcessor**
```python
# Keep as-is
# But document: "Used by WaveSignalProcessor duplicate checking only"
```

**Option C: Align with New Logic**
```python
# Change WaveSignalProcessor to also use +3
self.buffer_size = self.max_trades_per_wave + 3  # Align with per-exchange
```

**Recommendation**: **Option C** - Align WaveSignalProcessor with new logic

**Why**:
- Consistency across codebase
- Removes percentage calculation
- Simpler logic
- Matches per-exchange behavior

---

## 🧪 TESTING STRATEGY

### Pre-Cleanup Testing

**Verify Current State**:
```bash
# 1. Check score variables unused
grep -rn "min_score_week\|min_score_month" core/ main.py
# Expected: No matches

# 2. Check max_trades usage
grep -rn "max_trades_per_15min" core/
# Expected: Only in wave_signal_processor.py and signal_processor_websocket.py

# 3. Check buffer_percent usage
grep -rn "signal_buffer_percent" core/
# Expected: Only in wave_signal_processor.py
```

---

### Post-Cleanup Testing

**Phase 1 Tests** (MIN_SCORE removed):
```bash
# 1. Run config tests
python -m pytest tests/test_phase0_config_defaults.py -v

# 2. Import config
python -c "from config.settings import TradingConfig; c = TradingConfig(); print('OK')"

# 3. Check no references remain
grep -r "MIN_SCORE_WEEK\|MIN_SCORE_MONTH" --include="*.py" .
```

**Phase 2 Tests** (MAX_TRADES modified):
```bash
# 1. Test fallback logic
# (Create test: DB params = NULL, verify fallback used)

# 2. Test normal operation
# (Create test: DB params exist, verify DB values used)

# 3. Run integration tests
python -m pytest tests/ -k wave
```

**Phase 3 Tests** (BUFFER_PERCENT modified):
```bash
# 1. Test WaveSignalProcessor buffer calculation
# (Verify buffer_size = max_trades + 3)

# 2. Test duplicate checking
# (Ensure duplicate detection still works)

# 3. Monitor production
# (Check wave processing logs for 24 hours)
```

---

## 📁 FILES TO MODIFY

### Code Files

1. **config/settings.py**
   - Remove MIN_SCORE_WEEK definition (line 71)
   - Remove MIN_SCORE_MONTH definition (line 72)
   - Remove MIN_SCORE_WEEK loading (lines 249-250)
   - Remove MIN_SCORE_MONTH loading (lines 251-252)
   - Optional: Document MAX_TRADES_PER_15MIN as fallback
   - Optional: Modify SIGNAL_BUFFER_PERCENT usage

2. **core/wave_signal_processor.py** (Optional - Phase 3)
   - Line 50: Change buffer_percent calculation
   - Line 54: Change to `self.buffer_size = self.max_trades_per_wave + 3`

3. **tests/test_phase0_config_defaults.py**
   - Remove MIN_SCORE_WEEK assertion (line 33)
   - Remove MIN_SCORE_MONTH assertion (line 34)
   - Optional: Update MAX_TRADES_PER_15MIN assertion (line 35)
   - Optional: Update SIGNAL_BUFFER_PERCENT assertion (line 36)

---

### Configuration Files

4. **.env**
   - Remove `MIN_SCORE_WEEK=62`
   - Remove `MIN_SCORE_MONTH=58`
   - Optional: Add comment to MAX_TRADES_PER_15MIN
   - Optional: Add comment to SIGNAL_BUFFER_PERCENT

5. **.env.clean** (if exists)
   - Same as .env

---

### Documentation Files

6. **Create Migration Doc**:
   - `docs/migrations/ENV_VARS_CLEANUP_20251028.md`
   - List removed variables
   - Explain why removed
   - Provide migration guide

7. **Update**: `.env.example` (if exists)
   - Remove obsolete variables
   - Add comments for remaining

---

## 🔄 ROLLBACK PLAN

### If Cleanup Causes Issues

**Phase 1 Rollback** (MIN_SCORE):
```bash
# Add back to config/settings.py
# Line 71-72:
min_score_week: int = 62
min_score_month: int = 58

# Line 249-252:
if val := os.getenv('MIN_SCORE_WEEK'):
    config.min_score_week = int(val)
if val := os.getenv('MIN_SCORE_MONTH'):
    config.min_score_month = int(val)

# Add back to .env
MIN_SCORE_WEEK=62
MIN_SCORE_MONTH=58
```

**Rollback Time**: < 2 minutes

---

### Phase 2/3 Rollback

```bash
# 1. Revert git commit
git revert <commit-hash>

# 2. Restart bot
```

---

## ✅ RECOMMENDED CLEANUP SEQUENCE

### Step 1: Investigation ✅ (COMPLETE)
- [x] Identify unused variables
- [x] Map usage in codebase
- [x] Assess risk
- [x] Create cleanup plan

### Step 2: Phase 1 Cleanup (MIN_SCORE - SAFE)
- [ ] Remove MIN_SCORE_WEEK from code
- [ ] Remove MIN_SCORE_MONTH from code
- [ ] Update tests
- [ ] Remove from .env
- [ ] Test imports
- [ ] Verify no runtime errors

### Step 3: Phase 2 Decision (MAX_TRADES)
- [ ] **RECOMMEND**: Keep as fallback, add documentation
- [ ] OR: Convert to constant
- [ ] Update documentation
- [ ] Add inline comments

### Step 4: Phase 3 Decision (SIGNAL_BUFFER - OPTIONAL)
- [ ] **RECOMMEND**: Align WaveSignalProcessor with +3 logic
- [ ] OR: Keep current behavior
- [ ] Test duplicate checking
- [ ] Monitor 24 hours

### Step 5: Documentation
- [ ] Create migration doc
- [ ] Update README
- [ ] Update .env.example
- [ ] Add to changelog

---

## 📊 SUMMARY TABLE

| Variable | Status | Used In Production | Recommendation | Risk |
|----------|--------|-------------------|----------------|------|
| MIN_SCORE_WEEK | ❌ Unused | No | **REMOVE** | ✅ Zero |
| MIN_SCORE_MONTH | ❌ Unused | No | **REMOVE** | ✅ Zero |
| MAX_TRADES_PER_15MIN | ⚠️ Fallback Only | Rare (DB fail) | **KEEP & DOCUMENT** | ⚠️ Low |
| SIGNAL_BUFFER_PERCENT | ⚠️ Legacy Only | WaveSignalProcessor | **ALIGN TO +3** | ⚠️ Low |

---

## 🎯 FINAL RECOMMENDATIONS

### Immediate Actions (Low Risk)

1. ✅ **Remove MIN_SCORE Variables**
   - Zero production impact
   - Clean up configuration
   - Update tests

2. ✅ **Document MAX_TRADES_PER_15MIN**
   - Add comment: "Fallback when DB params unavailable"
   - Keep in .env for safety
   - No code changes needed

3. ⏳ **Defer SIGNAL_BUFFER Decision**
   - Current behavior works
   - Can align to +3 later
   - Monitor WaveSignalProcessor usage

---

### Future Improvements (Optional)

1. **Consolidate Fallback Logic**
   - Create ConfigDefaults class
   - Centralize all fallback values
   - Improve documentation

2. **Monitoring.params as Single Source**
   - Ensure DB params always populated
   - Remove need for config fallbacks
   - Simplify code

3. **Remove WaveSignalProcessor Dependency**
   - Inline duplicate checking into per-exchange logic
   - Remove separate class
   - Single code path

---

## 📝 IMPLEMENTATION CHECKLIST

### Phase 1: MIN_SCORE Removal

**Code Changes**:
- [ ] Remove from `config/settings.py` (lines 71-72, 249-252)
- [ ] Update `tests/test_phase0_config_defaults.py` (lines 33-34)
- [ ] Remove from `.env`
- [ ] Verify with `grep -r "MIN_SCORE"`

**Testing**:
- [ ] Run `pytest tests/test_phase0_config_defaults.py`
- [ ] Import config: `python -c "from config.settings import TradingConfig"`
- [ ] Verify no errors in logs

**Documentation**:
- [ ] Create migration doc
- [ ] Update changelog
- [ ] Add to "removed variables" list

---

### Phase 2: MAX_TRADES Documentation

**Code Changes**:
- [ ] Add inline comment in `config/settings.py:77`
- [ ] Add comment in `.env`

**Documentation**:
- [ ] Explain fallback purpose
- [ ] Document when it's used
- [ ] Note: Primary source is DB

---

### Phase 3: SIGNAL_BUFFER Alignment (Optional)

**Code Changes**:
- [ ] Modify `core/wave_signal_processor.py:50`
- [ ] Change to `self.buffer_percent = 3` or remove
- [ ] Modify `core/wave_signal_processor.py:54`
- [ ] Change to `self.buffer_size = self.max_trades_per_wave + 3`

**Testing**:
- [ ] Test duplicate checking
- [ ] Monitor wave processing
- [ ] Compare before/after behavior

---

## ✅ CONCLUSION

**Investigation Status**: ✅ **COMPLETE**

**Findings**:
1. MIN_SCORE variables: 100% unused, safe to remove
2. MAX_TRADES_PER_15MIN: Fallback only, keep with documentation
3. SIGNAL_BUFFER_PERCENT: Legacy logic, can align to +3

**Ready for Implementation**: ✅ **YES** (Phase 1)

**Risk Level**: ✅ **VERY LOW**

---

**Investigation completed**: 2025-10-28
**Investigator**: Claude Code
**Next Step**: Implement Phase 1 cleanup (MIN_SCORE removal)

---

**End of Investigation Report**
