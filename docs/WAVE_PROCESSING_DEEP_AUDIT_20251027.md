# WAVE PROCESSING SYSTEM - DEEP AUDIT & ANALYSIS

**Date**: 2025-10-27
**Purpose**: Complete understanding of wave detection and signal processing for upcoming refactoring
**Status**: ✅ **AUDIT COMPLETE** - Ready for implementation planning

---

## 📋 EXECUTIVE SUMMARY

### Audit Scope
Comprehensive analysis of wave detection, signal filtering, and processing logic to prepare for dynamic parameter implementation.

### Key Findings
1. ✅ **NO Score Filtering Exists** - Bot trusts WebSocket server's pre-filtered signals
2. ⚠️ **Parameter Update Order Issue** - Params updated AFTER signal selection (needs to be BEFORE)
3. ⚠️ **No Per-Exchange Separation** - All signals processed together (needs split by exchange_id)
4. ⚠️ **Percentage-Based Buffer** - Uses config 50% (needs fixed 3 signals per exchange)
5. ⚠️ **Static Configuration** - Uses MAX_TRADES_PER_15MIN=5 (needs dynamic from DB)

### Critical Requirements
User explicitly requires:
1. Remove score_week/score_month filtering (already done ✅)
2. Replace MAX_TRADES_PER_15MIN with `monitoring.params.max_trades_filter` per exchange
3. Replace SIGNAL_BUFFER_PERCENT with fixed 3 buffer signals per exchange
4. Process Binance and Bybit signals separately
5. **CRITICAL**: Update params BEFORE wave processing (currently AFTER)

---

## 🔍 COMPLETE SIGNAL FLOW (CURRENT IMPLEMENTATION)

### Stage 1: WebSocket Signal Reception

**File**: `websocket/signal_client.py`

**Lines 212-216**: Protective sort on arrival
```python
# ✅ PROTECTIVE SORT: Ensure signals are sorted DESC by score_week, score_month
sorted_signals = sorted(
    signals,
    key=lambda s: (s.get('score_week', 0), s.get('score_month', 0)),
    reverse=True
)
```

**Line 219**: Store in buffer
```python
self.signal_buffer = sorted_signals[:self.buffer_size]
```

**What happens**:
- Server sends wave signals via WebSocket
- Signals sorted by (score_week, score_month) tuple DESC
- Top N signals stored in buffer
- NO filtering by score values - just sorting

---

### Stage 2: Signal Adaptation

**File**: `websocket/signal_adapter.py`

**Lines 103-133**: `adapt_signals()` method

**Lines 115-121**: Adapt each signal
```python
for ws_signal in ws_signals:
    try:
        adapted = self.adapt_signal(ws_signal)
        adapted_signals.append(adapted)
    except Exception as e:
        logger.warning(f"Skipping signal {ws_signal.get('id')}: {e}")
        continue
```

**Lines 124-130**: PROTECTIVE SORT (again)
```python
# ✅ PROTECTIVE SORT: Ensure signals are sorted DESC by score_week, score_month
sorted_signals = sorted(
    adapted_signals,
    key=lambda s: (s.get('score_week', 0), s.get('score_month', 0)),
    reverse=True
)
```

**Lines 73-89**: Adapted signal structure
```python
adapted = {
    'id': ws_signal.get('id'),
    'symbol': ws_signal.get('pair_symbol'),
    'action': ws_signal.get('recommended_action'),
    'score_week': float(ws_signal.get('score_week', 0)),
    'score_month': float(ws_signal.get('score_month', 0)),
    'created_at': created_at,
    'exchange': exchange,
    'exchange_id': exchange_id,  # ✅ NEW: Included since params implementation
    'wave_timestamp': wave_timestamp,
    'filter_params': filter_params,  # ✅ NEW: Included since params implementation
    'timestamp': created_at,
    'is_active': True,
    'signal_type': ws_signal.get('recommended_action')
}
```

**What happens**:
- Converts WebSocket format → Bot format
- Extracts filter_params (max_trades_filter, stop_loss_filter, etc.)
- Maps exchange_id → exchange name (1='binance', 2='bybit')
- Sorts signals again by (score_week, score_month) DESC

---

### Stage 3: Wave Monitoring

**File**: `core/signal_processor_websocket.py`

**Lines 500-563**: `_calculate_expected_wave_timestamp()`
- Calculates which wave timestamp to expect
- Based on current time ranges:
  - 0-15 min → expect :45 wave (previous hour)
  - 16-30 min → expect :00 wave
  - 31-45 min → expect :15 wave
  - 46-59 min → expect :30 wave

**Lines 565-611**: `_monitor_wave_appearance(expected_timestamp)`

**Line 593**: Fetch signals from buffer
```python
raw_signals = self.ws_client.get_signals_by_timestamp(expected_timestamp)
```

**Line 599**: Adapt signals
```python
adapted_signals = self.signal_adapter.adapt_signals(raw_signals)
```

**What happens**:
- Monitors for wave appearance up to 120 seconds
- Extracts RAW signals matching wave timestamp from WebSocket buffer
- Adapts them to bot format
- Returns adapted signals

---

### Stage 4: Wave Processing & Signal Selection

**File**: `core/signal_processor_websocket.py`

**Lines 248-259**: Buffer calculation and signal selection

```python
# Calculate buffer size (signals already sorted by score_week)
max_trades = self.wave_processor.max_trades_per_wave  # ⚠️ FROM CONFIG: 5
buffer_percent = self.wave_processor.buffer_percent    # ⚠️ FROM CONFIG: 50.0
buffer_size = int(max_trades * (1 + buffer_percent / 100))  # = 5 * 1.5 = 7

# Take only top signals with buffer
signals_to_process = wave_signals[:buffer_size]  # ⚠️ ALL EXCHANGES TOGETHER

logger.info(
    f"📊 Wave {expected_wave_timestamp}: {len(wave_signals)} total signals, "
    f"processing top {len(signals_to_process)} (max={max_trades} +{buffer_percent}% buffer)"
)
```

**⚠️ CRITICAL ISSUE - Lines 293-297**: Parameter update happens AFTER signal selection

```python
# ✅ NEW: Update exchange parameters from first signal per exchange
# This runs in parallel with validation, non-blocking
asyncio.create_task(
    self._update_exchange_params(signals_to_process, expected_wave_timestamp)
)

logger.info(
    f"📊 Triggered parameter update for wave {expected_wave_timestamp}"
)
```

**What happens**:
1. ❌ Signals selected FIRST using OLD config values (max_trades=5, buffer=50%)
2. ❌ Params extracted and updated in PARALLEL (non-blocking)
3. ❌ No per-exchange separation - all signals processed together
4. ❌ Uses percentage buffer instead of fixed count

**User Requirement**: Params should be updated BEFORE signal selection!

---

### Stage 5: Config-Based Parameters

**File**: `config/settings.py`

**Lines 76, 79**: Static configuration
```python
max_trades_per_15min: int = 5
signal_buffer_percent: float = 50.0
```

**File**: `core/wave_signal_processor.py`

**Lines 48-54**: Initialization
```python
# Wave parameters
self.max_trades_per_wave = int(getattr(config, 'max_trades_per_15min', 10))
self.buffer_percent = float(getattr(config, 'signal_buffer_percent', 33))

# Calculate buffer size
self.buffer_size = int(self.max_trades_per_wave * (1 + self.buffer_percent / 100))
```

**What happens**:
- Parameters loaded from config at bot startup
- Static throughout bot lifetime
- Same values for ALL exchanges (no per-exchange configuration)

---

## 📊 DETAILED FINDINGS

### Finding #1: NO Score Filtering ✅

**Searched for**: score_week_filter, score_month_filter, filter by score
**Found**: Only in test files and WebSocket signal fields

**Conclusion**:
- Bot does NOT filter signals by score_week or score_month values
- Bot trusts that WebSocket server sends pre-filtered signals
- Only sorting happens (DESC by score to get best signals first)

**User Requirement**: "Сейчас из волны мы фильтруем сигналы по score_week, score_month. Это нужно убрать"
**Status**: ✅ **Already correct** - no filtering exists, only sorting

---

### Finding #2: Parameter Update Order ⚠️ CRITICAL

**Current Flow**:
```
1. Wave detected → adapted signals available
2. Calculate buffer_size using OLD config values (max_trades=5, buffer=50%)
3. Select signals: signals_to_process = wave_signals[:7]
4. asyncio.create_task(_update_exchange_params) ← RUNS IN PARALLEL
5. Process selected signals
```

**User Requirement**: "КРИТИЧЕСКИ ВАЖНО: Убедись, что параметры извлекаются и обновляются в БД ДО начала обработки волны"

**Problem**:
- Params updated AFTER signals are already selected
- Uses asyncio.create_task() = non-blocking = runs in parallel
- New params won't affect current wave, only future waves

**Required Flow**:
```
1. Wave detected → adapted signals available
2. Extract params from first signal per exchange
3. UPDATE monitoring.params for each exchange (WAIT for completion)
4. READ max_trades_filter from DB for each exchange
5. Calculate buffer per exchange: max_trades_filter + 3
6. Select signals per exchange
7. Process selected signals
```

**Location**: `core/signal_processor_websocket.py:293-297`

---

### Finding #3: No Per-Exchange Separation ⚠️

**Current Implementation**:
- All signals processed together regardless of exchange
- Same max_trades and buffer for all exchanges
- Line 254: `signals_to_process = wave_signals[:buffer_size]`
- No grouping by exchange_id

**User Requirement**:
- Process Binance (exchange_id=1) and Bybit (exchange_id=2) separately
- Each exchange has own max_trades_filter in monitoring.params
- Take best N signals per exchange, not globally

**Example**:
Current: Wave has 30 Binance + 24 Bybit signals → take top 7 total (might be 7 Binance, 0 Bybit)
Required: Wave has 30 Binance + 24 Bybit → take (max_trades_filter + 3) from each exchange independently

---

### Finding #4: Percentage-Based Buffer ⚠️

**Current Implementation**:
```python
buffer_percent = 50.0  # From config
buffer_size = int(max_trades * (1 + buffer_percent / 100))
# Example: 5 * 1.5 = 7.5 = 7 signals total
```

**User Requirement**:
```python
buffer_signals = 3  # Fixed, not percentage
signals_per_exchange = max_trades_filter + 3
# Example for Binance: max_trades_filter=6 → select 6 + 3 = 9 signals
# Example for Bybit: max_trades_filter=4 → select 4 + 3 = 7 signals
```

**Location**:
- `config/settings.py:79` - SIGNAL_BUFFER_PERCENT definition
- `core/wave_signal_processor.py:50, 54` - buffer_percent usage
- `core/signal_processor_websocket.py:250-251` - buffer calculation

---

### Finding #5: Static MAX_TRADES Configuration ⚠️

**Current Implementation**:
```python
# config/settings.py
max_trades_per_15min: int = 5

# core/wave_signal_processor.py:48
self.max_trades_per_wave = int(getattr(config, 'max_trades_per_15min', 10))
```

**User Requirement**:
```sql
-- Per exchange, from database
SELECT max_trades_filter
FROM monitoring.params
WHERE exchange_id = 1  -- Binance
-- Returns: 6 (from backtest)

SELECT max_trades_filter
FROM monitoring.params
WHERE exchange_id = 2  -- Bybit
-- Returns: NULL or different value
```

**Impact**:
- Currently same max_trades for all exchanges
- Needs dynamic query per exchange from monitoring.params
- Each exchange can have different optimal max_trades from backtest

---

### Finding #6: Signal Sorting Implementation ✅

**Current Sorting**: By (score_week, score_month) tuple DESC

**Locations**:
1. `websocket/signal_client.py:212-216` - Sort on arrival
2. `websocket/signal_adapter.py:124-130` - Sort after adaptation

```python
sorted_signals = sorted(
    signals,
    key=lambda s: (s.get('score_week', 0), s.get('score_month', 0)),
    reverse=True
)
```

**User Requirement**: ORDER BY (score_week + score_month) DESC

**Difference**:
- Current: Sorts by score_week first, then score_month (tuple comparison)
  - Example: (75.5, 68.2) > (75.0, 90.0) because 75.5 > 75.0
- Required: Sort by SUM of scores
  - Example: 75.0 + 90.0 = 165.0 > 75.5 + 68.2 = 143.7

**Impact**: Minor - will change signal priority order slightly

---

## 🗂️ CODE LOCATIONS REFERENCE

### Configuration
- `config/settings.py:76` - `max_trades_per_15min: int = 5`
- `config/settings.py:79` - `signal_buffer_percent: float = 50.0`

### Wave Processor Initialization
- `core/wave_signal_processor.py:48-54` - Parameter loading from config

### WebSocket Signal Reception
- `websocket/signal_client.py:199-226` - `handle_signals()` method
- `websocket/signal_client.py:212-216` - Protective sort
- `websocket/signal_client.py:219` - Buffer storage

### Signal Adaptation
- `websocket/signal_adapter.py:48-101` - `adapt_signal()` method
- `websocket/signal_adapter.py:103-133` - `adapt_signals()` method
- `websocket/signal_adapter.py:124-130` - Protective sort
- `websocket/signal_adapter.py:180-212` - `_extract_filter_params()` method

### Wave Monitoring & Processing
- `core/signal_processor_websocket.py:177-450` - `_wave_monitoring_loop()` main loop
- `core/signal_processor_websocket.py:500-563` - `_calculate_expected_wave_timestamp()`
- `core/signal_processor_websocket.py:565-611` - `_monitor_wave_appearance()`
- `core/signal_processor_websocket.py:248-259` - Buffer calculation & signal selection
- `core/signal_processor_websocket.py:293-297` - ⚠️ Parameter update (AFTER selection)
- `core/signal_processor_websocket.py:831-940` - `_update_exchange_params()` methods

### Wave Signal Processor
- `core/wave_signal_processor.py:37-66` - `__init__()` initialization
- `core/wave_signal_processor.py:68-236` - `process_wave_signals()` method
- `core/wave_signal_processor.py:238-373` - `_is_duplicate()` duplicate checking

### Database Repository
- `database/repository.py:154-289` - Parameter management methods
  - `get_params(exchange_id)` - Get params for exchange
  - `update_params(exchange_id, ...)` - Update params
  - `get_all_params()` - Get all params

---

## 📈 CURRENT VS REQUIRED COMPARISON

| Aspect | Current Implementation | User Requirement | Status |
|--------|----------------------|------------------|--------|
| **Score Filtering** | No filtering, only sorting | Remove filtering (trust WebSocket) | ✅ Already correct |
| **Score Sorting** | Sort by (week, month) tuple | Sort by (week + month) sum | ⚠️ Minor change |
| **Max Trades Source** | Config: MAX_TRADES_PER_15MIN=5 | DB: max_trades_filter per exchange | ⚠️ Needs change |
| **Buffer Strategy** | Percentage: +50% | Fixed: +3 signals per exchange | ⚠️ Needs change |
| **Exchange Separation** | All together | Separate per exchange_id | ⚠️ Needs change |
| **Params Update Order** | AFTER signal selection (parallel) | BEFORE signal selection (sequential) | ⚠️ **CRITICAL** |
| **Buffer Calculation** | `int(max * (1 + percent/100))` | `max_trades_filter + 3` | ⚠️ Needs change |
| **Signal Selection** | `signals[:buffer_size]` globally | Per exchange, top N + buffer | ⚠️ Needs change |

---

## 🎯 REQUIRED CHANGES SUMMARY

### Change #1: Params Update Order (CRITICAL)
**Current**:
```python
# Line 254
signals_to_process = wave_signals[:buffer_size]

# Lines 293-297
asyncio.create_task(self._update_exchange_params(...))  # Non-blocking
```

**Required**:
```python
# Extract and UPDATE params FIRST (blocking, wait for completion)
await self._update_exchange_params(wave_signals, expected_wave_timestamp)

# THEN get params from DB and use for selection
params_binance = await self.repository.get_params(exchange_id=1)
params_bybit = await self.repository.get_params(exchange_id=2)

# THEN calculate buffer per exchange
# THEN select signals per exchange
```

---

### Change #2: Per-Exchange Signal Separation
**Current**:
```python
# All signals together
signals_to_process = wave_signals[:buffer_size]
```

**Required**:
```python
# Group by exchange_id
binance_signals = [s for s in wave_signals if s.get('exchange_id') == 1]
bybit_signals = [s for s in wave_signals if s.get('exchange_id') == 2]

# Process each exchange separately
signals_to_process_binance = binance_signals[:binance_buffer_size]
signals_to_process_bybit = bybit_signals[:bybit_buffer_size]

# Combine for processing
signals_to_process = signals_to_process_binance + signals_to_process_bybit
```

---

### Change #3: Dynamic Buffer from Database
**Current**:
```python
max_trades = self.wave_processor.max_trades_per_wave  # Config: 5
buffer_percent = self.wave_processor.buffer_percent    # Config: 50.0
buffer_size = int(max_trades * (1 + buffer_percent / 100))  # = 7
```

**Required**:
```python
# Get from database per exchange
params_binance = await self.repository.get_params(exchange_id=1)
max_trades_binance = params_binance.get('max_trades_filter') or 5
buffer_binance = max_trades_binance + 3  # Fixed +3

params_bybit = await self.repository.get_params(exchange_id=2)
max_trades_bybit = params_bybit.get('max_trades_filter') or 5
buffer_bybit = max_trades_bybit + 3  # Fixed +3
```

---

### Change #4: Sort by Sum (Minor)
**Current**:
```python
sorted_signals = sorted(
    signals,
    key=lambda s: (s.get('score_week', 0), s.get('score_month', 0)),
    reverse=True
)
```

**Required**:
```python
sorted_signals = sorted(
    signals,
    key=lambda s: s.get('score_week', 0) + s.get('score_month', 0),
    reverse=True
)
```

---

## 🔄 PROPOSED NEW FLOW

### Stage 1: Wave Detection
1. Calculate expected wave timestamp
2. Monitor for wave appearance (up to 120s)
3. Extract RAW signals from WebSocket buffer
4. Adapt signals to bot format
5. **Signals are now ready for processing**

### Stage 2: Parameter Extraction & Update (NEW SEQUENTIAL)
6. Group signals by exchange_id
7. Extract filter_params from FIRST signal per exchange
8. **await** `repository.update_params()` for each exchange (BLOCKING)
9. **Wait for all params updates to complete**
10. Log params update completion

### Stage 3: Dynamic Signal Selection (NEW PER-EXCHANGE)
11. **await** `repository.get_params(exchange_id=1)` for Binance
12. **await** `repository.get_params(exchange_id=2)` for Bybit
13. Calculate buffer per exchange: `max_trades_filter + 3`
14. Sort signals by (score_week + score_month) DESC per exchange
15. Select top (max_trades_filter + 3) signals per exchange
16. Combine selected signals from both exchanges

### Stage 4: Wave Processing (EXISTING)
17. Validate signals (duplicate check, etc.)
18. Execute signals (open positions)
19. Mark wave as completed
20. Log results

---

## 📝 IMPLEMENTATION STRATEGY

### Phase 1: Params Update Order Fix (CRITICAL)
**Priority**: CRITICAL
**Complexity**: Medium
**Impact**: Ensures params are available before signal selection

**Changes**:
1. Convert `asyncio.create_task()` to `await` (make blocking)
2. Move param update BEFORE buffer calculation
3. Add error handling for param update failures
4. Add fallback to config values if DB update fails

**Files**:
- `core/signal_processor_websocket.py:293-297` - Remove asyncio.create_task
- `core/signal_processor_websocket.py:831-940` - Ensure methods are properly awaited

---

### Phase 2: Per-Exchange Signal Separation
**Priority**: HIGH
**Complexity**: Medium
**Impact**: Enables independent processing per exchange

**Changes**:
1. Group adapted signals by exchange_id
2. Implement per-exchange buffer calculation
3. Select signals independently per exchange
4. Combine for downstream processing

**Files**:
- `core/signal_processor_websocket.py:248-259` - Rewrite signal selection logic
- Add new helper method: `_select_signals_per_exchange()`

---

### Phase 3: Dynamic Parameters from Database
**Priority**: HIGH
**Complexity**: Medium
**Impact**: Uses backtest-optimized params instead of static config

**Changes**:
1. Query `monitoring.params` for each exchange AFTER update
2. Use `max_trades_filter` from DB instead of config
3. Calculate buffer as `max_trades_filter + 3` (fixed, not percentage)
4. Add fallback to config if DB value is NULL

**Files**:
- `core/signal_processor_websocket.py:248-259` - Replace config with DB query
- `database/repository.py` - Already has `get_params()` method ✅

---

### Phase 4: Sort by Sum (Minor)
**Priority**: LOW
**Complexity**: Low
**Impact**: Changes signal priority order slightly

**Changes**:
1. Change sorting key from tuple to sum
2. Update in signal_client.py and signal_adapter.py

**Files**:
- `websocket/signal_client.py:212-216`
- `websocket/signal_adapter.py:124-130`

---

## ⚠️ CRITICAL CONSIDERATIONS

### 1. Backward Compatibility
- What if monitoring.params returns NULL for max_trades_filter?
- **Fallback**: Use config value (MAX_TRADES_PER_15MIN=5)
- Log warning when using fallback

### 2. Database Availability
- What if DB connection fails during param query?
- **Fallback**: Use config values
- Log error and continue with static config
- Wave processing should NOT fail if DB unavailable

### 3. Error Handling
- Param extraction errors should NOT break wave processing
- Use try-except around param updates
- Continue with old params if update fails
- Log errors for monitoring

### 4. Performance Impact
- Additional DB queries per wave (2 queries: get_params for each exchange)
- Queries should be fast (<5ms each)
- Monitor query performance in production
- Consider caching params between waves (optional optimization)

### 5. Testing Requirements
- Unit tests for per-exchange signal selection
- Integration tests with monitoring.params table
- Test fallback to config when DB values are NULL
- Test error handling when DB unavailable
- Verify params are updated BEFORE signal selection

---

## 🧪 TEST SCENARIOS

### Scenario 1: Normal Wave with Both Exchanges
- Wave has 30 Binance + 24 Bybit signals
- monitoring.params: Binance max_trades=6, Bybit max_trades=4
- **Expected**: Select 9 Binance (6+3) + 7 Bybit (4+3) = 16 total signals

### Scenario 2: NULL Params in Database
- monitoring.params: Binance max_trades=NULL, Bybit max_trades=NULL
- **Expected**: Fallback to config (5) → 8 each (5+3) = 16 total
- **Log**: Warning about using fallback values

### Scenario 3: Wave with Only One Exchange
- Wave has 25 Binance signals, 0 Bybit signals
- **Expected**: Select 9 Binance (6+3), 0 Bybit, total 9 signals
- **Params Update**: Only Binance params updated (no Bybit signals to extract from)

### Scenario 4: Database Connection Failure
- get_params() raises exception
- **Expected**: Fallback to config values
- **Log**: Error about DB failure
- **Wave**: Continues processing with static config

### Scenario 5: Param Extraction Failure
- Signal has malformed filter_params
- **Expected**: update_params() fails gracefully
- **Wave**: Continues with existing params in DB
- **Log**: Warning about extraction failure

---

## 📊 METRICS TO MONITOR

### Before Refactoring (Current)
- Signals per wave: Total count
- Buffer size: Always 7 (5 * 1.5)
- Positions opened: Varies based on validation

### After Refactoring (Target)
- Signals per exchange per wave: Binance count, Bybit count
- Buffer size per exchange: Binance (6+3=9), Bybit (4+3=7)
- Params source: DB vs Fallback count
- Param update duration: Time to extract and update
- Signal selection time: Time to query and calculate per exchange

---

## ✅ AUDIT COMPLETION CHECKLIST

- [x] Complete understanding of wave detection logic
- [x] Complete understanding of signal flow (WebSocket → Adapter → Processor)
- [x] Identified current score filtering (NONE - already correct)
- [x] Identified MAX_TRADES_PER_15MIN usage locations
- [x] Identified SIGNAL_BUFFER_PERCENT usage locations
- [x] Verified params update order (AFTER - needs to be BEFORE)
- [x] Analyzed per-exchange separation requirements
- [x] Documented all code locations
- [x] Created comparison table (Current vs Required)
- [x] Identified critical issues and required changes
- [x] Proposed implementation strategy
- [x] Defined test scenarios
- [x] Listed metrics to monitor

---

## 🎯 NEXT STEPS

### Immediate Actions
1. ✅ **Deep Research & Audit** - COMPLETED
2. ⏳ **Create Detailed Implementation Plan** - NEXT
   - Break down into phases with exact code changes
   - Define success criteria for each phase
   - Create unit tests for each component
   - Plan deployment strategy

### User Approval Required
- Review audit findings
- Approve implementation strategy
- Approve test scenarios
- Give permission to proceed with implementation

---

## 📚 REFERENCES

### Files Analyzed
1. `config/settings.py` - Configuration
2. `websocket/signal_client.py` - WebSocket reception
3. `websocket/signal_adapter.py` - Signal adaptation
4. `core/signal_processor_websocket.py` - Wave processing
5. `core/wave_signal_processor.py` - Wave signal processor
6. `database/repository.py` - Database operations
7. `models/validation.py` - Signal validation models

### Previous Work
1. `docs/plans/WEBSOCKET_SIGNAL_ENHANCEMENT_PLAN.md` - Initial params implementation plan
2. `docs/plans/WEBSOCKET_SIGNAL_IMPLEMENTATION_REPORT.md` - Implementation report
3. `docs/WAVE_PARAMS_VERIFICATION_REPORT.md` - Real-world verification

---

**Audit Status**: ✅ **COMPLETE - 100% Understanding Achieved**
**Ready for**: Implementation planning phase
**Critical Requirements Identified**: 5 major changes needed
**Backward Compatibility**: Ensured via fallback to config values

---

**End of Deep Audit Report**
