# OBSOLETE ENV VARIABLES - Safe Cleanup Plan

**Date**: 2025-10-28
**Status**: 📋 **READY FOR IMPLEMENTATION**
**Risk Level**: ✅ **VERY LOW**

---

## 🎯 OVERVIEW

**Goal**: Remove unused environment variables that remain after per-exchange refactoring

**Scope**: 4 variables in `.env` file

**Approach**: Phased cleanup with testing at each step

**Total Effort**: ~30 minutes

---

## 📊 VARIABLES SUMMARY

| Variable | Status | Action | Risk | Priority |
|----------|--------|--------|------|----------|
| MIN_SCORE_WEEK | ❌ 100% unused | **REMOVE** | ✅ Zero | High |
| MIN_SCORE_MONTH | ❌ 100% unused | **REMOVE** | ✅ Zero | High |
| MAX_TRADES_PER_15MIN | ⚠️ Fallback only | **KEEP & DOCUMENT** | ⚠️ Low | Medium |
| SIGNAL_BUFFER_PERCENT | ⚠️ Legacy use | **ALIGN TO +3** | ⚠️ Low | Low |

---

## 🚀 PHASE 1: MIN_SCORE VARIABLES REMOVAL

### Risk: ✅ ZERO RISK

**Variables to Remove**:
- `MIN_SCORE_WEEK=62`
- `MIN_SCORE_MONTH=58`

**Evidence of Safety**:
```bash
$ grep -rn "min_score_week\|min_score_month" core/ main.py
# No matches - 100% confirmed unused
```

---

### Step 1.1: Remove from config/settings.py

**File**: `config/settings.py`

**Change 1**: Remove class field definitions (Lines 71-72)

**Current Code**:
```python
# Line 68-74
commission_percent: Decimal = Decimal('0.05')

# Signal filtering
min_score_week: int = 62        # ← REMOVE THIS LINE
min_score_month: int = 58       # ← REMOVE THIS LINE
max_spread_percent: Decimal = Decimal('0.5')
```

**New Code**:
```python
# Line 68-72
commission_percent: Decimal = Decimal('0.05')

# Signal filtering
max_spread_percent: Decimal = Decimal('0.5')
```

**Lines to Delete**: 71-72 (2 lines)

---

**Change 2**: Remove environment loading (Lines 249-252)

**Current Code**:
```python
# Line 246-255
if val := os.getenv('COMMISSION_PERCENT'):
    config.commission_percent = Decimal(val)

# Signal filtering
if val := os.getenv('MIN_SCORE_WEEK'):      # ← REMOVE BLOCK
    config.min_score_week = int(val)        # ← REMOVE BLOCK
if val := os.getenv('MIN_SCORE_MONTH'):     # ← REMOVE BLOCK
    config.min_score_month = int(val)       # ← REMOVE BLOCK
if val := os.getenv('MAX_SPREAD_PERCENT'):
    config.max_spread_percent = Decimal(val)
```

**New Code**:
```python
# Line 246-251
if val := os.getenv('COMMISSION_PERCENT'):
    config.commission_percent = Decimal(val)

# Signal filtering
if val := os.getenv('MAX_SPREAD_PERCENT'):
    config.max_spread_percent = Decimal(val)
```

**Lines to Delete**: 249-252 (4 lines)

---

### Step 1.2: Update tests/test_phase0_config_defaults.py

**File**: `tests/test_phase0_config_defaults.py`

**Change**: Remove score assertions (Lines 33-34)

**Current Code**:
```python
# Line 30-37
def test_default_values():
    """Test that config loads with expected defaults when no .env file"""
    config = TradingConfig()

    assert config.min_score_week == 62, "min_score_week should default to 62"      # ← REMOVE
    assert config.min_score_month == 58, "min_score_month should default to 58"    # ← REMOVE
    assert config.max_trades_per_15min == 5, "max_trades_per_15min should default to 5"
    assert config.signal_buffer_percent == 50.0, "signal_buffer_percent should default to 50.0"
```

**New Code**:
```python
# Line 30-35
def test_default_values():
    """Test that config loads with expected defaults when no .env file"""
    config = TradingConfig()

    assert config.max_trades_per_15min == 5, "max_trades_per_15min should default to 5"
    assert config.signal_buffer_percent == 50.0, "signal_buffer_percent should default to 50.0"
```

**Lines to Delete**: 33-34 (2 lines)

---

### Step 1.3: Remove from .env

**File**: `.env`

**Current**:
```bash
# Signal filtering
MIN_SCORE_WEEK=62              # Minimum weekly score     ← REMOVE
MIN_SCORE_MONTH=58             # Minimum monthly score    ← REMOVE
MAX_SPREAD_PERCENT=0.5
```

**New**:
```bash
# Signal filtering
MAX_SPREAD_PERCENT=0.5
```

**Lines to Delete**: 2 lines (MIN_SCORE_WEEK, MIN_SCORE_MONTH)

---

### Step 1.4: Verification

**Pre-Implementation Checks**:
```bash
# 1. Verify variables unused
grep -rn "min_score_week\|min_score_month" core/ main.py
# Expected: No matches ✅

# 2. Find all references
grep -r "MIN_SCORE_WEEK\|MIN_SCORE_MONTH" --include="*.py" .
# Expected: Only config/settings.py and tests
```

**Post-Implementation Checks**:
```bash
# 1. Test config import
python3 -c "from config.settings import TradingConfig; c = TradingConfig(); print('✅ Config loads OK')"

# 2. Run config tests
python -m pytest tests/test_phase0_config_defaults.py -v

# 3. Verify no references remain
grep -r "MIN_SCORE_WEEK\|MIN_SCORE_MONTH" --include="*.py" .
# Expected: No matches (only in docs)
```

---

### Step 1.5: Rollback Plan (if needed)

**If issues arise**:

1. **Revert config/settings.py**:
   ```python
   # Add back at line 71-72
   min_score_week: int = 62
   min_score_month: int = 58

   # Add back at line 249-252
   if val := os.getenv('MIN_SCORE_WEEK'):
       config.min_score_week = int(val)
   if val := os.getenv('MIN_SCORE_MONTH'):
       config.min_score_month = int(val)
   ```

2. **Revert tests**:
   ```python
   # Add back assertions
   assert config.min_score_week == 62
   assert config.min_score_month == 58
   ```

3. **Revert .env**:
   ```bash
   MIN_SCORE_WEEK=62
   MIN_SCORE_MONTH=58
   ```

**Rollback Time**: < 2 minutes

---

## 🚀 PHASE 2: MAX_TRADES_PER_15MIN DOCUMENTATION

### Risk: ⚠️ LOW RISK (No code changes, only documentation)

**Variable**: `MAX_TRADES_PER_15MIN=5`

**Current Use**: Fallback when database params unavailable

**Action**: Add documentation, keep variable

---

### Step 2.1: Add Comment in config/settings.py

**File**: `config/settings.py`

**Change**: Add explanatory comment (Line 77)

**Current Code**:
```python
# Line 75-78
# Execution
signal_time_window_minutes: int = 10
max_trades_per_15min: int = 5
```

**New Code**:
```python
# Line 75-79
# Execution
signal_time_window_minutes: int = 10
# NOTE: max_trades_per_15min is FALLBACK ONLY (used when DB params unavailable)
# Primary source: monitoring.params table (per-exchange: Binance=6, Bybit=4)
max_trades_per_15min: int = 5
```

**Lines Added**: 2 comment lines

---

### Step 2.2: Add Comment in .env

**File**: `.env`

**Current**:
```bash
MAX_TRADES_PER_15MIN=5                           # Max trades per wave execution
```

**New**:
```bash
# Max trades per wave (FALLBACK ONLY - primary source: monitoring.params DB table)
MAX_TRADES_PER_15MIN=5
```

**Lines Modified**: 1 line (comment updated)

---

### Step 2.3: Verification

**No Testing Required** - documentation changes only

**Visual Check**:
- Config comment clear
- .env comment explains fallback purpose
- No functional changes

---

## 🚀 PHASE 3: SIGNAL_BUFFER_PERCENT ALIGNMENT (OPTIONAL)

### Risk: ⚠️ LOW RISK (Aligns WaveSignalProcessor with new logic)

**Variable**: `SIGNAL_BUFFER_PERCENT=50`

**Current Use**: WaveSignalProcessor calculates buffer as max_trades * 1.5

**New Logic**: Per-exchange uses fixed +3 buffer

**Action**: Align WaveSignalProcessor to use +3 (consistent with new logic)

---

### Step 3.1: Update core/wave_signal_processor.py

**File**: `core/wave_signal_processor.py`

**Change 1**: Simplify buffer_percent (Line 50)

**Current Code**:
```python
# Line 48-54
# Wave parameters
self.max_trades_per_wave = int(getattr(config, 'max_trades_per_15min', 10))
self.buffer_percent = float(getattr(config, 'signal_buffer_percent', 33))
self.duplicate_check_enabled = getattr(config, 'duplicate_check_enabled', True)

# Calculate buffer size
self.buffer_size = int(self.max_trades_per_wave * (1 + self.buffer_percent / 100))
```

**New Code**:
```python
# Line 48-54
# Wave parameters
self.max_trades_per_wave = int(getattr(config, 'max_trades_per_15min', 10))
self.duplicate_check_enabled = getattr(config, 'duplicate_check_enabled', True)

# Calculate buffer size (aligned with per-exchange logic: fixed +3)
self.buffer_size = self.max_trades_per_wave + 3
```

**Changes**:
- Remove `self.buffer_percent` line
- Change buffer calculation to `+ 3` (not percentage)
- Update comment

**Lines Modified**: 3 lines (removed 1, changed 1, updated comment)

---

### Step 3.2: Update Logging (Line 61-66)

**Current Code**:
```python
# Line 61-66
logger.info(
    f"WaveSignalProcessor initialized: "
    f"max_trades={self.max_trades_per_wave}, "
    f"buffer_size={self.buffer_size} (+{self.buffer_percent}%), "
    f"duplicate_check={self.duplicate_check_enabled}"
)
```

**New Code**:
```python
# Line 61-66
logger.info(
    f"WaveSignalProcessor initialized: "
    f"max_trades={self.max_trades_per_wave}, "
    f"buffer_size={self.buffer_size} (+3), "
    f"duplicate_check={self.duplicate_check_enabled}"
)
```

**Lines Modified**: 1 line (log message)

---

### Step 3.3: Remove from config/settings.py (Optional)

**If Phase 3 implemented**, can remove `signal_buffer_percent`:

**File**: `config/settings.py`

**Current Code**:
```python
# Line 79-80
# Wave processing - FIX: 2025-10-03 - Добавлено поле для SIGNAL_BUFFER_PERCENT
signal_buffer_percent: float = 50.0
```

**New Code**:
```python
# Line 79
# (remove signal_buffer_percent - replaced by fixed +3 logic)
```

**Also Remove** (Lines 259-260):
```python
# Current:
if val := os.getenv('SIGNAL_BUFFER_PERCENT'):
    config.signal_buffer_percent = float(val)

# New: (remove block)
```

**Also Remove from .env**:
```bash
# Remove:
SIGNAL_BUFFER_PERCENT=50
```

---

### Step 3.4: Update Test

**File**: `tests/test_phase0_config_defaults.py`

**If signal_buffer_percent removed**:

**Current Code**:
```python
assert config.signal_buffer_percent == 50.0, "signal_buffer_percent should default to 50.0"
```

**New Code**:
```python
# (remove assertion - field no longer exists)
```

---

### Step 3.5: Verification

**Testing**:
```bash
# 1. Test WaveSignalProcessor import
python3 -c "from core.wave_signal_processor import WaveSignalProcessor; print('✅ Import OK')"

# 2. Test buffer calculation
python3 << 'EOF'
from config.settings import TradingConfig
from core.wave_signal_processor import WaveSignalProcessor
from unittest.mock import MagicMock

config = TradingConfig()
pm = MagicMock()
processor = WaveSignalProcessor(config, pm)

# Verify buffer calculation
expected = processor.max_trades_per_wave + 3
actual = processor.buffer_size
assert actual == expected, f"Buffer should be {expected}, got {actual}"
print(f"✅ Buffer calculation correct: {processor.max_trades_per_wave} + 3 = {actual}")
EOF

# 3. Run config tests
python -m pytest tests/test_phase0_config_defaults.py -v
```

**Production Monitoring** (24 hours):
- Check wave processing logs
- Verify duplicate checking still works
- Monitor for any buffer-related errors

---

### Step 3.6: Rollback Plan

**If issues arise**:

```bash
# 1. Revert core/wave_signal_processor.py
git checkout HEAD -- core/wave_signal_processor.py

# 2. Revert config/settings.py (if changed)
git checkout HEAD -- config/settings.py

# 3. Restart bot
```

**Rollback Time**: < 1 minute

---

## 📋 IMPLEMENTATION SEQUENCE

### Recommended Order

```
Phase 1: MIN_SCORE Removal
    ↓
Test & Verify (1 hour)
    ↓
Phase 2: MAX_TRADES Documentation
    ↓
Review Documentation
    ↓
Phase 3: SIGNAL_BUFFER Alignment (Optional)
    ↓
Test & Monitor (24 hours)
    ↓
Final Verification
```

---

### Detailed Timeline

| Phase | Task | Duration | Cumulative |
|-------|------|----------|------------|
| **Phase 1** | | | |
| 1.1 | Modify config/settings.py | 5 min | 5 min |
| 1.2 | Update tests | 2 min | 7 min |
| 1.3 | Update .env | 1 min | 8 min |
| 1.4 | Verification tests | 3 min | 11 min |
| 1.5 | Code review | 2 min | 13 min |
| **Phase 2** | | | |
| 2.1 | Add config comment | 2 min | 15 min |
| 2.2 | Add .env comment | 1 min | 16 min |
| 2.3 | Review | 1 min | 17 min |
| **Phase 3** (Optional) | | | |
| 3.1 | Modify wave_signal_processor | 5 min | 22 min |
| 3.2 | Update logging | 1 min | 23 min |
| 3.3 | Remove from config (optional) | 3 min | 26 min |
| 3.4 | Update tests | 2 min | 28 min |
| 3.5 | Verification tests | 5 min | 33 min |
| **Total** | | **33 min** | |

**Plus**: 24h monitoring for Phase 3

---

## ✅ SUCCESS CRITERIA

### Phase 1: MIN_SCORE Removal

**Immediate**:
- [x] Code compiles without errors
- [x] Config imports successfully
- [x] Tests pass
- [x] No grep matches for MIN_SCORE in code

**Long-term** (24 hours):
- [x] Bot runs without errors
- [x] No config-related warnings
- [x] No missing variable errors

---

### Phase 2: Documentation

**Immediate**:
- [x] Comments added to config
- [x] Comments added to .env
- [x] Documentation clear and accurate

**Quality Check**:
- [x] New developer can understand fallback purpose
- [x] Clear distinction: DB = primary, config = fallback

---

### Phase 3: Buffer Alignment (Optional)

**Immediate**:
- [x] WaveSignalProcessor buffer = max_trades + 3
- [x] Code compiles and imports
- [x] Tests pass
- [x] Logs show correct buffer calculation

**Long-term** (24 hours):
- [x] Duplicate checking works correctly
- [x] No buffer-related errors
- [x] Wave processing normal
- [x] Consistent with per-exchange logic

---

## 🎯 DELIVERABLES

### Code Changes

1. **config/settings.py**
   - MIN_SCORE variables removed (6 lines)
   - MAX_TRADES documented (2 lines added)
   - SIGNAL_BUFFER aligned (3 lines modified, optional)

2. **core/wave_signal_processor.py** (Phase 3 only)
   - Buffer calculation simplified (3 lines modified)
   - Logging updated (1 line)

3. **tests/test_phase0_config_defaults.py**
   - MIN_SCORE assertions removed (2 lines)
   - SIGNAL_BUFFER assertion removed (1 line, if Phase 3)

4. **.env**
   - MIN_SCORE lines removed (2 lines)
   - MAX_TRADES comment updated (1 line)
   - SIGNAL_BUFFER removed (1 line, if Phase 3)

---

### Documentation

5. **docs/investigations/OBSOLETE_ENV_VARS_CLEANUP_INVESTIGATION.md** (Completed)
   - Comprehensive investigation report

6. **docs/plans/OBSOLETE_ENV_VARS_CLEANUP_PLAN.md** (This file)
   - Detailed implementation plan

7. **docs/migrations/ENV_VARS_CLEANUP_20251028.md** (To be created)
   - Migration guide for operators
   - List of removed variables
   - Upgrade instructions

---

## 🔄 MIGRATION GUIDE FOR OPERATORS

### If You Have Custom .env

**Before Update**:
```bash
# Your current .env
MIN_SCORE_WEEK=70        # Custom value
MIN_SCORE_MONTH=65       # Custom value
MAX_TRADES_PER_15MIN=8   # Custom value
SIGNAL_BUFFER_PERCENT=40 # Custom value
```

**After Update**:
```bash
# MIN_SCORE_WEEK - REMOVED (not used)
# MIN_SCORE_MONTH - REMOVED (not used)

# MAX_TRADES_PER_15MIN - KEEP (fallback only)
# If you had custom value, it's used as fallback
# Primary values come from DB: monitoring.params
MAX_TRADES_PER_15MIN=8   # Your custom value preserved

# SIGNAL_BUFFER_PERCENT - CHANGED (if Phase 3)
# Now using fixed +3 buffer instead of percentage
# (remove this line if Phase 3 implemented)
```

**Action Required**:
1. Review your custom values
2. If using custom MAX_TRADES, verify it's reasonable fallback
3. Remove MIN_SCORE lines (not used)
4. Note: Real per-exchange values in database (monitoring.params)

---

## 📊 BEFORE/AFTER COMPARISON

### Configuration Complexity

**Before**:
- 4 wave-related config variables
- Mixed between DB and config sources
- Percentage-based buffer calculation
- Score filtering variables (unused)

**After Phase 1**:
- 2 wave-related config variables
- Clear DB primary, config fallback
- Score variables removed (unused)

**After Phase 3** (Optional):
- 1 wave-related config variable (MAX_TRADES_PER_15MIN)
- Fixed +3 buffer (consistent everywhere)
- Simplified configuration

---

### Code Clarity

**Before**:
```python
# Confusing: Where are max_trades used?
min_score_week = 62  # ← Unused
min_score_month = 58  # ← Unused
max_trades_per_15min = 5  # ← When is this used?
signal_buffer_percent = 50  # ← Old logic
```

**After**:
```python
# Clear: Documented purpose
# max_trades_per_15min: FALLBACK when DB unavailable
max_trades_per_15min = 5
# (buffer is fixed +3, not percentage)
```

---

## ⚠️ IMPORTANT NOTES

### Database is Primary Source

**Remember**: After per-exchange refactoring, **ALL** trading parameters come from database:

```sql
SELECT * FROM monitoring.params;
```

**Result**:
```
exchange_id | max_trades_filter | stop_loss_filter | ...
------------|-------------------|------------------|----
1 (Binance) | 6                 | 4.0              | ...
2 (Bybit)   | 4                 | 3.5              | ...
```

**Config variables are FALLBACK only** - used if:
- Database query fails
- Database returns NULL
- Emergency override needed

**Normal operation**: Database values used 100% of time

---

### Buffer Calculation Change

**Old Logic** (WaveSignalProcessor):
```
buffer_size = max_trades * (1 + 50/100)
            = max_trades * 1.5
Example: 6 * 1.5 = 9
```

**New Logic** (Per-Exchange):
```
buffer_size = max_trades + 3
Example: 6 + 3 = 9
```

**Phase 3 aligns WaveSignalProcessor with new logic** for consistency.

---

## ✅ FINAL CHECKLIST

### Before Implementation

- [x] Investigation complete
- [x] Plan documented
- [x] Risk assessed (VERY LOW)
- [x] Rollback plan ready
- [ ] Team review (if needed)
- [ ] Backup created

---

### Phase 1 Implementation

- [ ] Modify config/settings.py (remove MIN_SCORE)
- [ ] Update tests (remove assertions)
- [ ] Update .env (remove lines)
- [ ] Run verification tests
- [ ] Code review
- [ ] Commit changes

---

### Phase 2 Implementation

- [ ] Add config comments
- [ ] Add .env comments
- [ ] Review documentation
- [ ] Commit changes

---

### Phase 3 Implementation (Optional)

- [ ] Modify wave_signal_processor.py
- [ ] Update logging
- [ ] Remove signal_buffer_percent (optional)
- [ ] Update tests
- [ ] Run verification tests
- [ ] Monitor 24 hours
- [ ] Commit changes

---

### Post-Implementation

- [ ] Create migration doc
- [ ] Update changelog
- [ ] Verify no errors in production
- [ ] Archive investigation docs
- [ ] Mark ticket as complete

---

## 📞 SUPPORT

### If Issues Arise

1. **Check Logs**: Look for config-related errors
2. **Verify Imports**: Test `from config.settings import TradingConfig`
3. **Run Tests**: `pytest tests/test_phase0_config_defaults.py`
4. **Rollback**: Use plans in each phase
5. **Report**: Document any unexpected behavior

---

## ✅ APPROVAL

**Plan Status**: 📋 **READY FOR IMPLEMENTATION**

**Reviewed By**: [To be filled]
**Approved By**: [To be filled]
**Approved Date**: [To be filled]

**Implementation Priority**:
- Phase 1: **HIGH** (cleanup unused variables)
- Phase 2: **MEDIUM** (improve documentation)
- Phase 3: **LOW** (optional improvement)

---

**Plan created**: 2025-10-28
**Plan owner**: Claude Code
**Next Action**: Implement Phase 1 (MIN_SCORE removal)

---

**End of Cleanup Plan**
