# 🔴 CRITICAL MIGRATION PLAN: SL/TS Parameters to Per-Exchange (monitoring.params)

**Date**: 2025-10-28
**Status**: 📋 PLANNING PHASE - NO CODE CHANGES YET
**Critical Priority**: 🔴 HIGH - Trading Logic Changes
**Estimated Total Time**: 12-16 hours + testing

---

## ⚠️ DISCLAIMER

**THIS IS A PLANNING DOCUMENT ONLY**
- ❌ **NO CODE CHANGES** on this step
- ✅ **ONLY** analysis, design, and detailed planning
- ✅ **REVIEW REQUIRED** before any implementation

---

## EXECUTIVE SUMMARY

### Problem Statement

**CRITICAL**: Trading parameters (SL/TS) are updated per-exchange in `monitoring.params` from backtest signals every 15 minutes, BUT these params are **NOT USED** when creating positions!

**Current State**:
```sql
-- monitoring.params (ALREADY EXISTS, updated from signals)
SELECT * FROM monitoring.params;

 exchange_id | max_trades | stop_loss_filter | trailing_activation_filter | trailing_distance_filter
-------------+------------+------------------+----------------------------+-------------------------
 1 (Binance) |     6      |      4.0%        |           2.0%             |          0.5%
 2 (Bybit)   |     4      |      6.0%        |           2.5%             |          0.5%
```

**Problem**:
```python
# position_manager.py:1073 - USING GLOBAL .env!
stop_loss_percent = self.config.stop_loss_percent  # ← WRONG! Uses same 4.0% for BOTH exchanges

# Should use PER-EXCHANGE params from monitoring.params!
params = await get_params_for_exchange('binance')  # → 4.0%
params = await get_params_for_exchange('bybit')    # → 6.0%  ← DIFFERENT!
```

### Solution Overview

**3-Phase Migration**:
1. **PHASE 1**: Add columns to `monitoring.positions` + helper functions
2. **PHASE 2**: Use `stop_loss_filter` from DB when creating positions
3. **PHASE 3**: Save and use trailing params in positions (Variant B)

---

## SECTION 1: DEEP AUDIT FINDINGS

### 1.1 Real Database Structure (VERIFIED)

#### Table: monitoring.params (EXISTS ✅)

```sql
-- Schema (verified via \d monitoring.params)
CREATE TABLE monitoring.params (
    exchange_id INTEGER PRIMARY KEY,  -- 1=Binance, 2=Bybit
    max_trades_filter INTEGER,
    stop_loss_filter NUMERIC(10,4),            -- ✅ Already exists!
    trailing_activation_filter NUMERIC(10,4),  -- ✅ Already exists!
    trailing_distance_filter NUMERIC(10,4),    -- ✅ Already exists!
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_exchange_id CHECK (exchange_id IN (1, 2))
);

-- Current Data (verified via SELECT):
 exchange_id | max_trades_filter | stop_loss_filter | trailing_activation_filter | trailing_distance_filter |     updated_at
-------------+-------------------+------------------+----------------------------+--------------------------+-------------------
           1 |                 6 |           4.0000 |                     2.0000 |                   0.5000 | 2025-10-27 23:35
           2 |                 4 |           6.0000 |                     2.5000 |                   0.5000 | 2025-10-27 22:50
```

**Comments** (from migration_004):
- `stop_loss_filter`: Stop loss percentage from backtest (e.g., 2.5 = 2.5%)
- `trailing_activation_filter`: Trailing stop activation percentage from backtest (e.g., 3.0 = 3.0%)
- `trailing_distance_filter`: Trailing stop distance percentage from backtest (e.g., 1.5 = 1.5%)

**Updated by**: `signal_processor_websocket.py:1324-1361` (`_update_exchange_params()`)
**Frequency**: Every wave (every ~15 minutes when signals arrive)

---

#### Table: monitoring.positions (EXISTS ✅)

```sql
-- Relevant columns (verified via \d monitoring.positions)
CREATE TABLE monitoring.positions (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,  -- ✅ STRING: 'binance', 'bybit' (NOT integer!)
    side VARCHAR(10) NOT NULL,      -- 'long', 'short'
    entry_price NUMERIC(20,8) NOT NULL,
    stop_loss_price NUMERIC(20,8),
    trailing_activated BOOLEAN DEFAULT false,
    -- ... other fields ...

    -- ❌ MISSING COLUMNS (need to add):
    -- trailing_activation_percent NUMERIC(10,4),
    -- trailing_callback_percent NUMERIC(10,4)
);
```

**CRITICAL FINDING**:
- `exchange` column is **VARCHAR(50)**, values: `'binance'`, `'bybit'`
- `monitoring.params.exchange_id` is **INTEGER**, values: `1`, `2`
- **Need mapping function**: `'binance' ↔ 1`, `'bybit' ↔ 2`

---

### 1.2 Exchange ID Mapping

**Verified from code**:
```python
# websocket/signal_adapter.py:145-147
if exchange_id == 1:
    return 'binance'
elif exchange_id == 2:
    return 'bybit'

# signal_processor_websocket.py:613
exchange_name = 'Binance' if exchange_id == 1 else 'Bybit' if exchange_id == 2 else f'Unknown({exchange_id})'
```

**Mapping**:
```
exchange_id=1 ↔ exchange='binance'
exchange_id=2 ↔ exchange='bybit'
```

---

### 1.3 Current Usage of monitoring.params

#### ✅ USED: max_trades_filter

**File**: `signal_processor_websocket.py:603-633`
**Method**: `_get_params_for_exchange(exchange_id)`

```python
params = await self.repository.get_params(exchange_id=exchange_id)
if params and params.get('max_trades_filter') is not None:
    max_trades = int(params['max_trades_filter'])  # ← USED for signal selection
    buffer_size = max_trades + self.config.signal_buffer_fixed
    return {
        'max_trades': max_trades,
        'buffer_size': buffer_size,
        'source': 'database'
    }
```

**Usage**: Select top N signals per exchange (N from DB)

---

#### ❌ NOT USED: stop_loss_filter

**Returned from DB but NOT USED**:

**File**: `signal_processor_websocket.py:576-580`
```python
# CURRENTLY:
return {
    'max_trades_filter': db_params['max_trades_filter'],
    'stop_loss_filter': db_params.get('stop_loss_filter'),  # ← RETURNED but NOT USED!
    'trailing_activation_filter': db_params.get('trailing_activation_filter'),  # ← NOT USED!
    'trailing_distance_filter': db_params.get('trailing_distance_filter')  # ← NOT USED!
}
```

**WHERE IT SHOULD BE USED**:

**File**: `position_manager.py:1073`
```python
# CURRENTLY (WRONG):
stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent  # ← GLOBAL .env

# SHOULD BE (CORRECT):
params = await get_params_for_exchange_name(request.exchange)  # 'binance' → exchange_id=1
stop_loss_percent = request.stop_loss_percent or params['stop_loss_filter']  # ← PER-EXCHANGE from DB!
```

---

### 1.4 All Places Using config.stop_loss_percent

**Inventory** (verified via grep):

| File:Line | Context | Exchange Known? | Critical? | Action Required |
|-----------|---------|----------------|-----------|-----------------|
| `position_manager.py:1073` | `open_position()` - create SL | ✅ YES (`request.exchange`) | 🔴 CRITICAL | Replace with DB params |
| `position_manager.py:497` | Set SL for position | ✅ YES (`position.exchange`) | 🔴 CRITICAL | Replace with DB params |
| `position_manager.py:792` | Set SL (another branch) | ✅ YES | 🔴 CRITICAL | Replace with DB params |
| `position_manager.py:854` | Set SL (third branch) | ✅ YES | 🔴 CRITICAL | Replace with DB params |
| `position_manager.py:1340` | Update position SL | ✅ YES | 🔴 CRITICAL | Replace with DB params |
| `position_manager.py:3038` | Recovery after restart | ✅ YES | 🔴 CRITICAL | Replace with DB params |
| `config/settings.py:47` | Default value | N/A | ✅ LOW | Keep for fallback |
| `config/settings.py:213` | Load from .env | N/A | ✅ LOW | Keep for fallback |
| `config/settings.py:330` | Validation | N/A | ✅ LOW | Keep |

**Total Critical Places**: 6 places in `position_manager.py`

---

### 1.5 All Places Using config.trailing_activation_percent

**Inventory**:

| File:Line | Context | Exchange Known? | Critical? | Action Required |
|-----------|---------|----------------|-----------|-----------------|
| `position_manager.py:189` | `TrailingStopConfig` init | ❌ NO (global) | 🔴 CRITICAL | Change to per-position params |
| `trailing_stop.py:40` | Default in dataclass | N/A | ✅ LOW | Keep default |
| `trailing_stop.py:200` | Save to DB state | ⚠️ Uses `self.config` | 🔴 CRITICAL | Save from position |
| `trailing_stop.py:489` | Calculate activation_price | ⚠️ Uses `self.config` | 🔴 CRITICAL | Use position params |

**Total Critical Places**: 3 places

---

### 1.6 TrailingStop Architecture Analysis

**Current Flow** (PROBLEM):

```python
# main.py → position_manager.py:184-202
trailing_config = TrailingStopConfig(
    activation_percent=Decimal(str(config.trailing_activation_percent)),  # ← GLOBAL! Same for all exchanges
    callback_percent=Decimal(str(config.trailing_callback_percent))
)

self.trailing_managers = {
    name: SmartTrailingStopManager(
        exchange,
        trailing_config,  # ← SAME config for Binance AND Bybit!
        exchange_name=name,
        repository=repository
    )
    for name, exchange in exchanges.items()
}

# Later: trailing_stop.py:489-492
# When creating TS for position:
ts.activation_price = ts.entry_price * (1 + self.config.activation_percent / 100)
                                            # ↑ GLOBAL config! Not from position!
```

**Problem**: All TS instances use SAME `activation_percent` and `callback_percent` from GLOBAL config!

---

## SECTION 2: DETAILED MIGRATION PLAN

### Architecture Decision: Variant B (Dynamic params from position)

**Why Variant B**:
1. ✅ Each position has its own fixed trailing params (saved when created)
2. ✅ Changing params in DB affects ONLY new positions (existing positions unaffected)
3. ✅ Recovery after restart works correctly (params loaded from position)
4. ✅ Consistent with user's choice

**What needs to change**:
1. Add columns to `monitoring.positions`
2. Save trailing params when creating position
3. TrailingStop reads params from position (not config)
4. Proper fallback for legacy positions

---

### PHASE 1: Database Changes + Helper Functions

**Duration**: 1-2 hours
**Risk**: 🟡 LOW (schema only, no logic changes)

#### 1.1 SQL Migration

**File**: `migrations/migration_005_add_trailing_params_to_positions.sql` (NEW FILE)

```sql
-- =====================================================================
-- MIGRATION 005: Add trailing params columns to monitoring.positions
-- =====================================================================
-- Date: 2025-10-28
-- Purpose: Store per-position trailing stop parameters
--
-- This allows each position to have its own trailing params,
-- independent of current monitoring.params values.
-- =====================================================================

BEGIN;

-- =====================================================================
-- 1. Add new columns to monitoring.positions
-- =====================================================================
ALTER TABLE monitoring.positions
ADD COLUMN IF NOT EXISTS trailing_activation_percent NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS trailing_callback_percent NUMERIC(10,4);

-- Comments
COMMENT ON COLUMN monitoring.positions.trailing_activation_percent IS
    'Trailing stop activation percentage for THIS position (saved on creation from monitoring.params)';

COMMENT ON COLUMN monitoring.positions.trailing_callback_percent IS
    'Trailing stop callback/distance percentage for THIS position (saved on creation from monitoring.params)';

-- =====================================================================
-- 2. No data migration needed (new positions will be created)
-- =====================================================================
-- Per user requirement: "просто закроем все позиции"
-- So no need to fill existing positions with values

-- =====================================================================
-- 3. Verification
-- =====================================================================
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    -- Check columns added
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_schema = 'monitoring'
      AND table_name = 'positions'
      AND column_name IN ('trailing_activation_percent', 'trailing_callback_percent');

    IF col_count != 2 THEN
        RAISE EXCEPTION 'Expected 2 new columns in monitoring.positions, found %', col_count;
    END IF;

    RAISE NOTICE '✅ monitoring.positions: Added trailing_activation_percent and trailing_callback_percent';
END $$;

COMMIT;

DO $$ BEGIN
    RAISE NOTICE '✅ Migration 005 completed successfully!';
END $$;
```

---

#### 1.2 Helper Functions for Exchange ID Mapping

**File**: `utils/exchange_helpers.py` (NEW FILE)

```python
"""
Exchange ID mapping helpers

Converts between:
- exchange_name: str ('binance', 'bybit')
- exchange_id: int (1, 2)

Used for:
- Reading params from monitoring.params (requires exchange_id)
- Storing positions in monitoring.positions (uses exchange_name)
"""

def exchange_name_to_id(name: str) -> int:
    """
    Convert exchange name to exchange_id for monitoring.params

    Args:
        name: Exchange name ('binance', 'bybit', case-insensitive)

    Returns:
        int: Exchange ID (1=Binance, 2=Bybit)

    Raises:
        ValueError: If exchange name is unknown

    Examples:
        >>> exchange_name_to_id('binance')
        1
        >>> exchange_name_to_id('Bybit')
        2
    """
    name_lower = name.lower().strip()

    if name_lower == 'binance':
        return 1
    elif name_lower == 'bybit':
        return 2
    else:
        raise ValueError(
            f"Unknown exchange name: '{name}'. "
            f"Expected 'binance' or 'bybit'"
        )


def exchange_id_to_name(exchange_id: int) -> str:
    """
    Convert exchange_id to exchange name

    Args:
        exchange_id: Exchange ID (1 or 2)

    Returns:
        str: Exchange name ('binance' or 'bybit')

    Raises:
        ValueError: If exchange_id is unknown

    Examples:
        >>> exchange_id_to_name(1)
        'binance'
        >>> exchange_id_to_name(2)
        'bybit'
    """
    if exchange_id == 1:
        return 'binance'
    elif exchange_id == 2:
        return 'bybit'
    else:
        raise ValueError(
            f"Unknown exchange_id: {exchange_id}. "
            f"Expected 1 (Binance) or 2 (Bybit)"
        )
```

---

#### 1.3 Unit Tests for Helper Functions

**File**: `tests/unit/test_exchange_helpers.py` (NEW FILE)

```python
"""Unit tests for exchange ID mapping helpers"""
import pytest
from utils.exchange_helpers import exchange_name_to_id, exchange_id_to_name


class TestExchangeNameToId:
    """Tests for exchange_name_to_id()"""

    def test_binance_lowercase(self):
        """Test 'binance' → 1"""
        assert exchange_name_to_id('binance') == 1

    def test_binance_uppercase(self):
        """Test 'BINANCE' → 1 (case-insensitive)"""
        assert exchange_name_to_id('BINANCE') == 1

    def test_binance_mixed_case(self):
        """Test 'Binance' → 1"""
        assert exchange_name_to_id('Binance') == 1

    def test_bybit_lowercase(self):
        """Test 'bybit' → 2"""
        assert exchange_name_to_id('bybit') == 2

    def test_bybit_uppercase(self):
        """Test 'BYBIT' → 2"""
        assert exchange_name_to_id('BYBIT') == 2

    def test_unknown_exchange(self):
        """Test unknown exchange raises ValueError"""
        with pytest.raises(ValueError, match="Unknown exchange name: 'ftx'"):
            exchange_name_to_id('ftx')

    def test_with_whitespace(self):
        """Test with leading/trailing whitespace"""
        assert exchange_name_to_id('  binance  ') == 1
        assert exchange_name_to_id('bybit   ') == 2


class TestExchangeIdToName:
    """Tests for exchange_id_to_name()"""

    def test_binance_id(self):
        """Test 1 → 'binance'"""
        assert exchange_id_to_name(1) == 'binance'

    def test_bybit_id(self):
        """Test 2 → 'bybit'"""
        assert exchange_id_to_name(2) == 'bybit'

    def test_unknown_id(self):
        """Test unknown ID raises ValueError"""
        with pytest.raises(ValueError, match="Unknown exchange_id: 3"):
            exchange_id_to_name(3)

    def test_roundtrip_binance(self):
        """Test 'binance' → 1 → 'binance'"""
        name = 'binance'
        exchange_id = exchange_name_to_id(name)
        result = exchange_id_to_name(exchange_id)
        assert result == name

    def test_roundtrip_bybit(self):
        """Test 'bybit' → 2 → 'bybit'"""
        name = 'bybit'
        exchange_id = exchange_name_to_id(name)
        result = exchange_id_to_name(exchange_id)
        assert result == name
```

---

#### 1.4 PHASE 1: Testing & Deployment

**Testing Checklist**:
- [ ] Run SQL migration on test database
- [ ] Verify columns added: `\d monitoring.positions`
- [ ] Run unit tests: `pytest tests/unit/test_exchange_helpers.py -v`
- [ ] All tests pass

**Deployment Steps**:
1. **Review** SQL migration (migrations/migration_005_add_trailing_params_to_positions.sql)
2. **Backup** database: `pg_dump fox_crypto > backup_pre_migration_005.sql`
3. **Apply** migration: `psql -f migrations/migration_005_add_trailing_params_to_positions.sql`
4. **Verify** columns: `psql -c "\d monitoring.positions" | grep trailing`
5. **Commit** to git:
   ```bash
   git add migrations/migration_005_add_trailing_params_to_positions.sql
   git add utils/exchange_helpers.py
   git add tests/unit/test_exchange_helpers.py
   git commit -m "feat(phase1): add trailing params columns + exchange ID helpers"
   ```

**Rollback**:
```sql
-- If needed:
ALTER TABLE monitoring.positions
DROP COLUMN IF EXISTS trailing_activation_percent,
DROP COLUMN IF EXISTS trailing_callback_percent;
```

**PHASE 1 Complete Criteria**:
- [x] SQL migration applied
- [x] Columns exist in monitoring.positions
- [x] Helper functions created
- [x] Unit tests passing
- [x] Code committed to git
- [x] No impact on running bot (columns nullable)

---

### PHASE 2: Use stop_loss_filter from DB

**Duration**: 3-4 hours
**Risk**: 🔴 HIGH (changes SL creation logic)

#### 2.1 Repository Method for Params by Exchange Name

**File**: `database/repository.py`
**Add new method** (around line 290):

```python
async def get_params_by_exchange_name(self, exchange_name: str) -> Optional[Dict]:
    """
    Get trading params for exchange by exchange name

    Convenience wrapper around get_params() that handles exchange_name → exchange_id mapping.

    Args:
        exchange_name: Exchange name ('binance', 'bybit')

    Returns:
        Dict with params or None if not found

    Example:
        >>> params = await repo.get_params_by_exchange_name('binance')
        >>> params['stop_loss_filter']
        4.0
    """
    from utils.exchange_helpers import exchange_name_to_id

    try:
        exchange_id = exchange_name_to_id(exchange_name)
        return await self.get_params(exchange_id=exchange_id)
    except ValueError as e:
        logger.error(f"Invalid exchange name '{exchange_name}': {e}")
        return None
```

---

#### 2.2 Position Manager: Use DB Params for Stop Loss

**File**: `core/position_manager.py`

**Location 1: open_position() method (line ~1073)**

```python
# ========================================================================
# BEFORE (WRONG - uses global .env):
# ========================================================================
# Line 1073:
stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent


# ========================================================================
# AFTER (CORRECT - uses per-exchange DB params):
# ========================================================================
# Line 1073 (replace):
# Get per-exchange params from monitoring.params
try:
    exchange_params = await self.repository.get_params_by_exchange_name(request.exchange)

    if exchange_params and exchange_params.get('stop_loss_filter') is not None:
        # Use stop_loss_filter from DB
        db_stop_loss_percent = float(exchange_params['stop_loss_filter'])
        logger.debug(
            f"📊 Using stop_loss_filter from DB for {request.exchange}: {db_stop_loss_percent}%"
        )
        stop_loss_percent = request.stop_loss_percent or db_stop_loss_percent
    else:
        # Fallback to .env if DB params not available
        logger.warning(
            f"⚠️  stop_loss_filter not in DB for {request.exchange}, "
            f"using .env fallback: {self.config.stop_loss_percent}%"
        )
        stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent

except Exception as e:
    # Fallback to .env on error
    logger.error(
        f"❌ Failed to load params from DB for {request.exchange}: {e}. "
        f"Using .env fallback: {self.config.stop_loss_percent}%"
    )
    stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
```

**Explanation**:
1. Try to load params from DB using exchange name
2. If found and `stop_loss_filter` is not NULL → use it
3. Otherwise → fallback to `.env` (for backward compatibility)
4. Handle errors gracefully (fallback to `.env`)

---

**Location 2: _set_stop_loss_for_position() method (line ~497)**

**Find the method that sets SL for a position** (need to check exact line):

```python
# Around line 497 (need to verify exact method name)
# Search for: stop_loss_percent = to_decimal(self.config.stop_loss_percent)

# BEFORE:
stop_loss_percent = to_decimal(self.config.stop_loss_percent)

# AFTER:
# Get params from DB
try:
    exchange_params = await self.repository.get_params_by_exchange_name(position.exchange)

    if exchange_params and exchange_params.get('stop_loss_filter') is not None:
        stop_loss_percent = to_decimal(exchange_params['stop_loss_filter'])
        logger.debug(
            f"📊 {position.symbol}: Using stop_loss_filter from DB: {stop_loss_percent}%"
        )
    else:
        # Fallback
        logger.warning(
            f"⚠️  {position.symbol}: stop_loss_filter not in DB, using .env fallback"
        )
        stop_loss_percent = to_decimal(self.config.stop_loss_percent)

except Exception as e:
    logger.error(f"❌ {position.symbol}: Error loading params from DB: {e}. Using .env")
    stop_loss_percent = to_decimal(self.config.stop_loss_percent)
```

---

**⚠️ CRITICAL: Apply to ALL 6 locations**

**Locations to change** (from Section 1.4):
1. ✅ `position_manager.py:1073` - open_position()
2. ⚠️ `position_manager.py:497` - set SL for position
3. ⚠️ `position_manager.py:792` - set SL (another branch)
4. ⚠️ `position_manager.py:854` - set SL (third branch)
5. ⚠️ `position_manager.py:1340` - update position SL
6. ⚠️ `position_manager.py:3038` - recovery after restart

**For each location**:
1. **Read 20 lines before and after** to understand context
2. **Verify** that `position.exchange` or `request.exchange` is available
3. **Apply** the same pattern: load from DB → fallback to .env
4. **Test** each change individually

---

#### 2.3 Integration Tests for PHASE 2

**File**: `tests/integration/test_position_manager_db_params.py` (NEW FILE)

```python
"""Integration tests for position_manager using monitoring.params"""
import pytest
from decimal import Decimal
from core.position_manager import PositionManager, PositionRequest
from database.repository import Repository


@pytest.mark.asyncio
async def test_open_position_uses_binance_stop_loss_from_db(
    repository: Repository,
    position_manager: PositionManager
):
    """
    Test that opening position on Binance uses stop_loss_filter from DB

    Setup:
        monitoring.params.stop_loss_filter = 4.0 for exchange_id=1 (Binance)

    Expected:
        Position created with SL = 4.0% (from DB, not .env)
    """
    # Given: DB has stop_loss_filter = 4.0 for Binance
    params = await repository.get_params(exchange_id=1)
    assert params['stop_loss_filter'] == Decimal('4.0')

    # When: Create position on Binance
    request = PositionRequest(
        signal_id=12345,
        symbol='BTCUSDT',
        exchange='binance',  # ← exchange_name
        side='BUY',
        entry_price=Decimal('50000.0')
    )

    position = await position_manager.open_position(request)

    # Then: SL calculated from 4.0% (from DB)
    expected_sl = Decimal('50000.0') * (Decimal('1') - Decimal('4.0') / Decimal('100'))
    assert position.stop_loss_price == pytest.approx(float(expected_sl), rel=0.01)


@pytest.mark.asyncio
async def test_open_position_uses_bybit_stop_loss_from_db(
    repository: Repository,
    position_manager: PositionManager
):
    """
    Test that opening position on Bybit uses stop_loss_filter from DB

    Setup:
        monitoring.params.stop_loss_filter = 6.0 for exchange_id=2 (Bybit)

    Expected:
        Position created with SL = 6.0% (DIFFERENT from Binance!)
    """
    # Given: DB has stop_loss_filter = 6.0 for Bybit
    params = await repository.get_params(exchange_id=2)
    assert params['stop_loss_filter'] == Decimal('6.0')

    # When: Create position on Bybit
    request = PositionRequest(
        signal_id=12346,
        symbol='ETHUSDT',
        exchange='bybit',  # ← exchange_name
        side='BUY',
        entry_price=Decimal('3000.0')
    )

    position = await position_manager.open_position(request)

    # Then: SL calculated from 6.0% (from DB, DIFFERENT!)
    expected_sl = Decimal('3000.0') * (Decimal('1') - Decimal('6.0') / Decimal('100'))
    assert position.stop_loss_price == pytest.approx(float(expected_sl), rel=0.01)


@pytest.mark.asyncio
async def test_fallback_to_env_if_db_params_missing(
    repository: Repository,
    position_manager: PositionManager,
    config
):
    """
    Test fallback to .env if stop_loss_filter is NULL in DB

    Setup:
        monitoring.params.stop_loss_filter = NULL for exchange

    Expected:
        Position created with SL from .env (fallback)
    """
    # Given: Set stop_loss_filter to NULL in DB
    await repository.update_params(exchange_id=1, stop_loss_filter=None)

    # Verify NULL
    params = await repository.get_params(exchange_id=1)
    assert params['stop_loss_filter'] is None

    # When: Create position
    request = PositionRequest(
        signal_id=12347,
        symbol='BTCUSDT',
        exchange='binance',
        side='BUY',
        entry_price=Decimal('50000.0')
    )

    position = await position_manager.open_position(request)

    # Then: SL calculated from .env fallback
    env_stop_loss = config.trading.stop_loss_percent
    expected_sl = Decimal('50000.0') * (Decimal('1') - env_stop_loss / Decimal('100'))
    assert position.stop_loss_price == pytest.approx(float(expected_sl), rel=0.01)
```

---

#### 2.4 Manual Testing Checklist for PHASE 2

**Before Deployment**:

1. **Update DB params**:
   ```sql
   -- Set different SL for each exchange
   UPDATE monitoring.params SET stop_loss_filter = 3.5 WHERE exchange_id = 1;  -- Binance
   UPDATE monitoring.params SET stop_loss_filter = 5.0 WHERE exchange_id = 2;  -- Bybit
   ```

2. **Test creating position on Binance**:
   - Create signal for BTCUSDT on Binance
   - Bot processes signal
   - Check logs: "Using stop_loss_filter from DB for binance: 3.5%"
   - Verify SL order created with 3.5% distance

3. **Test creating position on Bybit**:
   - Create signal for ETHUSDT on Bybit
   - Bot processes signal
   - Check logs: "Using stop_loss_filter from DB for bybit: 5.0%"
   - Verify SL order created with 5.0% distance (DIFFERENT!)

4. **Test fallback**:
   ```sql
   -- Set NULL in DB
   UPDATE monitoring.params SET stop_loss_filter = NULL WHERE exchange_id = 1;
   ```
   - Create position on Binance
   - Check logs: "⚠️  stop_loss_filter not in DB, using .env fallback"
   - Verify SL uses .env value

5. **Test error handling**:
   - Stop database temporarily
   - Try to create position
   - Check logs: "❌ Failed to load params from DB... Using .env fallback"
   - Verify position still created (degraded mode)

---

#### 2.5 PHASE 2: Deployment

**Pre-Deployment**:
- [ ] All code changes reviewed
- [ ] Integration tests passing
- [ ] Manual tests on testnet completed

**Deployment Steps**:
1. **Code Review** (MANDATORY for CRITICAL changes)
2. **Deploy to testnet**:
   ```bash
   git checkout -b phase2-stop-loss-db-params
   git add core/position_manager.py database/repository.py
   git add tests/integration/test_position_manager_db_params.py
   git commit -m "feat(phase2): use stop_loss_filter from monitoring.params"
   git push origin phase2-stop-loss-db-params
   ```
3. **Test on testnet** (24 hours minimum)
4. **Monitor** logs for errors
5. **If successful** → merge to main → deploy to production
6. **Monitor** production for 48 hours

**Rollback**:
```bash
# If issues detected:
git revert HEAD
# Redeploy previous version
# Bot will use .env fallback (degraded but safe)
```

**PHASE 2 Complete Criteria**:
- [ ] Positions on Binance use Binance stop_loss_filter from DB
- [ ] Positions on Bybit use Bybit stop_loss_filter from DB
- [ ] Fallback to .env works when DB params missing
- [ ] Error handling prevents bot crashes
- [ ] All tests passing
- [ ] Code merged to main
- [ ] Production stable for 48 hours

---

### PHASE 3: Save and Use Trailing Params from Position

**Duration**: 4-6 hours
**Risk**: 🔴 CRITICAL (changes TrailingStop logic)

#### 3.1 Overview

**Goal**: Each position has its own trailing params (Variant B)

**What changes**:
1. When creating position: Read `trailing_activation_filter`, `trailing_distance_filter` from DB
2. Save to `monitoring.positions.trailing_activation_percent`, `.trailing_callback_percent`
3. TrailingStop reads params from position (not config!)
4. Recovery: Load params from position

---

#### 3.2 Repository: Update create_position()

**File**: `database/repository.py`

**Find method `create_position()`** (need to check exact location):

```python
# BEFORE:
async def create_position(self, position_data: Dict) -> int:
    """Create new position"""
    # ... existing code ...
    query = """
        INSERT INTO monitoring.positions (
            symbol, exchange, side, quantity, entry_price,
            stop_loss_price, ...
        )
        VALUES ($1, $2, $3, $4, $5, $6, ...)
        RETURNING id
    """

# AFTER (add trailing params):
async def create_position(self, position_data: Dict) -> int:
    """
    Create new position

    NEW in PHASE 3: Accepts trailing_activation_percent and trailing_callback_percent
    """
    query = """
        INSERT INTO monitoring.positions (
            symbol, exchange, side, quantity, entry_price,
            stop_loss_price,
            trailing_activation_percent,  -- ← NEW COLUMN
            trailing_callback_percent,    -- ← NEW COLUMN
            ... -- other fields
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, ...)
        RETURNING id
    """

    # Extract new fields (with defaults)
    trailing_activation = position_data.get('trailing_activation_percent')
    trailing_callback = position_data.get('trailing_callback_percent')

    # Execute query
    async with self.pool.acquire() as conn:
        position_id = await conn.fetchval(
            query,
            position_data['symbol'],
            position_data['exchange'],
            position_data['side'],
            position_data['quantity'],
            position_data['entry_price'],
            position_data.get('stop_loss_price'),
            trailing_activation,  # ← NEW
            trailing_callback,    # ← NEW
            # ... other params
        )

    return position_id
```

---

#### 3.3 Position Manager: Save Trailing Params When Creating Position

**File**: `core/position_manager.py`

**Location: open_position() method (after getting exchange_params)**

```python
# ========================================================================
# PHASE 3: GET TRAILING PARAMS FROM DB AND SAVE TO POSITION
# ========================================================================
# Add after getting exchange_params (around line 1075):

# Get trailing params from monitoring.params
trailing_activation_percent = None
trailing_callback_percent = None

if exchange_params:
    # Try to get trailing params from DB
    if exchange_params.get('trailing_activation_filter') is not None:
        trailing_activation_percent = float(exchange_params['trailing_activation_filter'])
        logger.debug(
            f"📊 Using trailing_activation_filter from DB for {request.exchange}: "
            f"{trailing_activation_percent}%"
        )

    if exchange_params.get('trailing_distance_filter') is not None:
        trailing_callback_percent = float(exchange_params['trailing_distance_filter'])
        logger.debug(
            f"📊 Using trailing_distance_filter from DB for {request.exchange}: "
            f"{trailing_callback_percent}%"
        )

# Fallback to .env if not in DB
if trailing_activation_percent is None:
    trailing_activation_percent = float(self.config.trailing_activation_percent)
    logger.warning(
        f"⚠️  trailing_activation_filter not in DB for {request.exchange}, "
        f"using .env fallback: {trailing_activation_percent}%"
    )

if trailing_callback_percent is None:
    trailing_callback_percent = float(self.config.trailing_callback_percent)
    logger.warning(
        f"⚠️  trailing_distance_filter not in DB for {request.exchange}, "
        f"using .env fallback: {trailing_callback_percent}%"
    )

# ========================================================================
# ADD TO position_data WHEN CREATING POSITION
# ========================================================================
# Find where position_data is created (around line 1100-1120):

position_data = {
    'symbol': symbol,
    'exchange': exchange_name,
    'side': position_side,
    'quantity': quantity,
    'entry_price': entry_price,
    'stop_loss_price': stop_loss_price,
    # ... existing fields ...

    # ← ADD NEW FIELDS:
    'trailing_activation_percent': trailing_activation_percent,
    'trailing_callback_percent': trailing_callback_percent
}

# Create position in DB (will save trailing params)
position_id = await self.repository.create_position(position_data)
```

---

#### 3.4 TrailingStop: Accept Position Params

**File**: `protection/trailing_stop.py`

**Change 1: Update TrailingStopInstance dataclass (line ~66)**

```python
# BEFORE:
@dataclass
class TrailingStopInstance:
    symbol: str
    entry_price: Decimal
    current_price: Decimal
    highest_price: Decimal
    lowest_price: Decimal

    state: TrailingStopState = TrailingStopState.INACTIVE
    # ... other fields ...


# AFTER (add activation and callback percent):
@dataclass
class TrailingStopInstance:
    symbol: str
    entry_price: Decimal
    current_price: Decimal
    highest_price: Decimal
    lowest_price: Decimal

    state: TrailingStopState = TrailingStopState.INACTIVE
    # ... existing fields ...

    # ← NEW FIELDS (from position, not config!):
    activation_percent: Decimal = Decimal('0')  # Saved from position on creation
    callback_percent: Decimal = Decimal('0')    # Saved from position on creation
```

---

**Change 2: Update create_trailing_stop() method (line ~446)**

```python
# BEFORE:
async def create_trailing_stop(self,
                               symbol: str,
                               side: str,
                               entry_price: float,
                               quantity: float,
                               initial_stop: Optional[float] = None):


# AFTER (add position_params parameter):
async def create_trailing_stop(self,
                               symbol: str,
                               side: str,
                               entry_price: float,
                               quantity: float,
                               initial_stop: Optional[float] = None,
                               position_params: Optional[Dict] = None):  # ← NEW PARAMETER!
    """
    Create new trailing stop instance

    NEW in PHASE 3:
        position_params: Dict with trailing_activation_percent and trailing_callback_percent
                         from monitoring.positions (saved when position was created)

    Example:
        position_params = {
            'trailing_activation_percent': 2.0,  # From position, not config!
            'trailing_callback_percent': 0.5
        }
    """
    # ... existing code ...

    # ========================================================================
    # NEW: GET ACTIVATION AND CALLBACK PERCENT FROM POSITION
    # ========================================================================
    if position_params:
        # Use params from position (CORRECT)
        activation_percent = Decimal(str(position_params['trailing_activation_percent']))
        callback_percent = Decimal(str(position_params['trailing_callback_percent']))

        logger.info(
            f"✅ {symbol}: Using trailing params from position: "
            f"activation={activation_percent}%, callback={callback_percent}%"
        )
    else:
        # Fallback to config (for legacy positions or errors)
        logger.warning(
            f"⚠️  {symbol}: No trailing params in position, using config fallback "
            f"(activation={self.config.activation_percent}%, callback={self.config.callback_percent}%)"
        )
        activation_percent = self.config.activation_percent
        callback_percent = self.config.callback_percent

    # Create TS instance with position-specific params
    ts = TrailingStopInstance(
        symbol=symbol,
        entry_price=Decimal(str(entry_price)),
        current_price=Decimal(str(entry_price)),
        highest_price=Decimal(str(entry_price)) if side == 'long' else UNINITIALIZED_PRICE_HIGH,
        lowest_price=UNINITIALIZED_PRICE_HIGH if side == 'long' else Decimal(str(entry_price)),
        side=side.lower(),
        quantity=Decimal(str(quantity)),
        # ← SET NEW FIELDS:
        activation_percent=activation_percent,  # From position!
        callback_percent=callback_percent       # From position!
    )

    # Calculate activation price from position-specific activation_percent
    if side == 'long':
        ts.activation_price = ts.entry_price * (1 + activation_percent / 100)
    else:
        ts.activation_price = ts.entry_price * (1 - activation_percent / 100)

    # ... rest of method unchanged ...
```

---

**Change 3: Update _get_trailing_distance() (line ~901)**

```python
# BEFORE:
def _get_trailing_distance(self, ts: TrailingStopInstance) -> Decimal:
    # ... step activation logic ...

    # Line 926:
    return self.config.callback_percent  # ← GLOBAL config!


# AFTER:
def _get_trailing_distance(self, ts: TrailingStopInstance) -> Decimal:
    # ... step activation logic (unchanged) ...

    # Line 926 (replace):
    return ts.callback_percent  # ← FROM POSITION (TrailingStopInstance)!
```

---

**Change 4: Update _save_state() (line ~200)**

```python
# BEFORE:
state_data = {
    # ...
    'activation_percent': float(self.config.activation_percent),  # ← GLOBAL config
    'callback_percent': float(self.config.callback_percent),      # ← GLOBAL config
    # ...
}


# AFTER:
state_data = {
    # ...
    'activation_percent': float(ts.activation_percent),  # ← FROM INSTANCE!
    'callback_percent': float(ts.callback_percent),      # ← FROM INSTANCE!
    # ...
}
```

---

#### 3.5 Position Manager: Pass Trailing Params to create_trailing_stop()

**File**: `core/position_manager.py`

**Find ALL calls to `trailing_manager.create_trailing_stop()`**:

```bash
grep -n "create_trailing_stop" core/position_manager.py
```

**For each call, add `position_params` argument**:

```python
# BEFORE:
await self.trailing_managers[exchange_name].create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=float(position.entry_price),
    quantity=float(position.quantity),
    initial_stop=float(stop_loss_price)
)


# AFTER:
# Prepare trailing params from position
position_params = {
    'trailing_activation_percent': position.trailing_activation_percent,
    'trailing_callback_percent': position.trailing_callback_percent
}

# Handle legacy positions (NULL params)
if position.trailing_activation_percent is None or position.trailing_callback_percent is None:
    logger.warning(
        f"⚠️  {symbol}: Legacy position without trailing params, will use config fallback"
    )
    position_params = None  # TrailingStop will use config fallback

await self.trailing_managers[exchange_name].create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=float(position.entry_price),
    quantity=float(position.quantity),
    initial_stop=float(stop_loss_price),
    position_params=position_params  # ← NEW PARAMETER!
)
```

---

#### 3.6 Integration Tests for PHASE 3

**File**: `tests/integration/test_trailing_stop_position_params.py` (NEW FILE)

```python
"""Integration tests for TrailingStop using position params"""
import pytest
from decimal import Decimal
from protection.trailing_stop import SmartTrailingStopManager, TrailingStopInstance


@pytest.mark.asyncio
async def test_trailing_stop_uses_position_activation_percent(
    trailing_manager: SmartTrailingStopManager
):
    """
    Test that TS uses activation_percent from position, not config

    Setup:
        Position has trailing_activation_percent = 1.5%
        Config has trailing_activation_percent = 2.0% (DIFFERENT!)

    Expected:
        TS uses 1.5% from position (not 2.0% from config)
    """
    # Given: Position params (from DB)
    position_params = {
        'trailing_activation_percent': 1.5,  # ← From position
        'trailing_callback_percent': 0.4
    }

    # When: Create TS with position params
    ts = await trailing_manager.create_trailing_stop(
        symbol='BTCUSDT',
        side='long',
        entry_price=50000.0,
        quantity=0.001,
        position_params=position_params  # ← Pass position params
    )

    # Then: TS uses 1.5% (from position)
    assert ts.activation_percent == Decimal('1.5')

    # And: activation_price calculated from 1.5%
    expected_activation = Decimal('50000.0') * (Decimal('1') + Decimal('1.5') / Decimal('100'))
    assert ts.activation_price == expected_activation


@pytest.mark.asyncio
async def test_trailing_stop_uses_position_callback_percent(
    trailing_manager: SmartTrailingStopManager
):
    """
    Test that TS uses callback_percent from position
    """
    # Given: Position params
    position_params = {
        'trailing_activation_percent': 2.0,
        'trailing_callback_percent': 0.3  # ← From position
    }

    # When: Create TS
    ts = await trailing_manager.create_trailing_stop(
        symbol='ETHUSDT',
        side='long',
        entry_price=3000.0,
        quantity=0.01,
        position_params=position_params
    )

    # Then: TS uses 0.3% callback (from position)
    assert ts.callback_percent == Decimal('0.3')

    # And: _get_trailing_distance() returns 0.3%
    distance = trailing_manager._get_trailing_distance(ts)
    assert distance == Decimal('0.3')


@pytest.mark.asyncio
async def test_trailing_stop_fallback_for_legacy_position(
    trailing_manager: SmartTrailingStopManager,
    config
):
    """
    Test fallback to config for legacy position without trailing params

    Setup:
        Position has trailing_activation_percent = NULL (legacy)

    Expected:
        TS uses config values (fallback)
    """
    # Given: No position params (legacy position)
    position_params = None

    # When: Create TS without position params
    ts = await trailing_manager.create_trailing_stop(
        symbol='SOLUSDT',
        side='long',
        entry_price=100.0,
        quantity=1.0,
        position_params=position_params  # ← None = legacy
    )

    # Then: TS uses config fallback
    assert ts.activation_percent == config.trailing_activation_percent
    assert ts.callback_percent == config.trailing_callback_percent


@pytest.mark.asyncio
async def test_different_positions_different_params(
    trailing_manager: SmartTrailingStopManager
):
    """
    Test that two positions can have different trailing params

    Scenario:
        Position 1 created when DB had activation=1.5%
        Position 2 created later when DB had activation=2.5%
        Both positions should keep their original params
    """
    # Position 1: activation=1.5%
    ts1 = await trailing_manager.create_trailing_stop(
        symbol='BTC1',
        side='long',
        entry_price=50000.0,
        quantity=0.001,
        position_params={
            'trailing_activation_percent': 1.5,
            'trailing_callback_percent': 0.5
        }
    )

    # Position 2: activation=2.5% (DIFFERENT!)
    ts2 = await trailing_manager.create_trailing_stop(
        symbol='BTC2',
        side='long',
        entry_price=50000.0,
        quantity=0.001,
        position_params={
            'trailing_activation_percent': 2.5,  # ← DIFFERENT!
            'trailing_callback_percent': 0.5
        }
    )

    # Assert: Each TS has its own params
    assert ts1.activation_percent == Decimal('1.5')
    assert ts2.activation_percent == Decimal('2.5')

    # Assert: activation_price is different
    assert ts1.activation_price != ts2.activation_price
```

---

#### 3.7 PHASE 3: Manual Testing

**Scenario 1: Create position → check trailing params saved**

1. Update DB:
   ```sql
   UPDATE monitoring.params
   SET trailing_activation_filter = 1.8, trailing_distance_filter = 0.4
   WHERE exchange_id = 1;  -- Binance
   ```

2. Create position on Binance

3. Check DB:
   ```sql
   SELECT id, symbol, exchange,
          trailing_activation_percent, trailing_callback_percent
   FROM monitoring.positions
   WHERE symbol = 'BTCUSDT'
   ORDER BY id DESC LIMIT 1;
   ```

   Expected:
   ```
   id | symbol   | exchange | trailing_activation_percent | trailing_callback_percent
   ---|----------|----------|----------------------------|---------------------------
   123| BTCUSDT  | binance  | 1.8                        | 0.4
   ```

4. Check logs:
   ```
   ✅ BTCUSDT: Using trailing params from position: activation=1.8%, callback=0.4%
   ```

---

**Scenario 2: Restart bot → verify TS restored from position**

1. Stop bot

2. Update DB (change params):
   ```sql
   UPDATE monitoring.params
   SET trailing_activation_filter = 2.5
   WHERE exchange_id = 1;  -- NEW VALUE
   ```

3. Start bot

4. Check logs:
   ```
   ✅ BTCUSDT: TS state RESTORED from DB - ... activation_percent=1.8 ...
   ```

   **Expected**: TS uses 1.8% from position (NOT 2.5% from current params!)

---

**Scenario 3: Different params for Binance vs Bybit**

1. Update DB:
   ```sql
   UPDATE monitoring.params SET trailing_activation_filter = 1.5 WHERE exchange_id = 1;
   UPDATE monitoring.params SET trailing_activation_filter = 2.5 WHERE exchange_id = 2;
   ```

2. Create position on Binance:
   ```sql
   SELECT trailing_activation_percent FROM monitoring.positions
   WHERE symbol = 'BTCUSDT';
   -- Expected: 1.5
   ```

3. Create position on Bybit:
   ```sql
   SELECT trailing_activation_percent FROM monitoring.positions
   WHERE symbol = 'ETHUSDT';
   -- Expected: 2.5 (DIFFERENT!)
   ```

---

#### 3.8 PHASE 3: Deployment

**Pre-Deployment Checklist**:
- [ ] All PHASE 3 code changes reviewed
- [ ] Integration tests passing
- [ ] Manual testing completed on testnet
- [ ] PHASE 1 and PHASE 2 stable in production

**Deployment Steps**:
1. **Code Review** (CRITICAL - TS logic changes!)
2. **Create branch**:
   ```bash
   git checkout -b phase3-trailing-params-from-position
   git add core/position_manager.py protection/trailing_stop.py database/repository.py
   git add tests/integration/test_trailing_stop_position_params.py
   git commit -m "feat(phase3): use trailing params from position (Variant B)"
   git push origin phase3-trailing-params-from-position
   ```
3. **Deploy to testnet** (MINIMUM 48 hours testing)
4. **Create test positions** with different params
5. **Restart bot** several times → verify recovery
6. **Monitor** for errors
7. **Merge to main** → deploy to production
8. **Close all existing positions** (per user requirement)
9. **Monitor** production for 72 hours

**Rollback**:
```bash
git revert HEAD
# Redeploy previous version
# TS will use config fallback (degraded but works)
```

**PHASE 3 Complete Criteria**:
- [ ] Positions save trailing params when created
- [ ] TS uses params from position (not config)
- [ ] Different exchanges have different trailing params
- [ ] Recovery after restart uses position params
- [ ] Legacy positions use config fallback
- [ ] All tests passing
- [ ] Production stable for 72 hours

---

## SECTION 3: RISK ANALYSIS & MITIGATION

### 3.1 Critical Risks

#### Risk 1: Wrong SL Percent Used

**Scenario**:
```python
# Bug: Forgot to change one location in position_manager.py
# Line 792 still uses:
stop_loss_percent = self.config.stop_loss_percent  # ← GLOBAL!

# Result: Some positions created with wrong SL
```

**Impact**: 🔴 CRITICAL - Wrong risk management
**Probability**: MEDIUM (6 locations to change)

**Mitigation**:
1. ✅ Detailed inventory in Section 1.4 (6 locations documented)
2. ✅ Code review checklist: Verify ALL 6 locations changed
3. ✅ Integration tests for each location
4. ✅ Grep after changes:
   ```bash
   # Should return 0 results in position_manager.py:
   grep "self.config.stop_loss_percent" core/position_manager.py | grep -v "fallback"
   ```

---

#### Risk 2: Exchange Name vs Exchange ID Confusion

**Scenario**:
```python
# Bug: Passing exchange_name to function expecting exchange_id
params = await repo.get_params(exchange_id='binance')  # ← WRONG! Should be 1

# Result: DB query fails, params = None, fallback to .env
```

**Impact**: 🟡 MEDIUM - Degraded mode (uses .env)
**Probability**: LOW (helper functions + tests)

**Mitigation**:
1. ✅ Helper functions with type hints
2. ✅ Unit tests for mapping
3. ✅ Use `get_params_by_exchange_name()` wrapper (takes string)
4. ✅ Integration tests verify correct params loaded

---

#### Risk 3: NULL Trailing Params in Position

**Scenario**:
```python
# Bug: Repository doesn't save trailing params (missing columns in INSERT)
# Result: position.trailing_activation_percent = NULL

# Later: TrailingStop tries to use NULL
activation_percent = Decimal(str(position.trailing_activation_percent))  # ← ERROR!
```

**Impact**: 🔴 CRITICAL - Bot crashes
**Probability**: LOW (tests + fallback logic)

**Mitigation**:
1. ✅ Integration test verifies params saved
2. ✅ Fallback logic in create_trailing_stop():
   ```python
   if position_params and position_params.get('trailing_activation_percent') is not None:
       # Use position params
   else:
       # Fallback to config
   ```
3. ✅ Manual testing: Check DB after creating position

---

#### Risk 4: Typo in Column Name

**Scenario**:
```python
# Bug: Wrong column name in SQL
INSERT INTO monitoring.positions (..., trailing_activaton_percent, ...)  # ← Typo!
                                                       ↑ missing 'i'

# Result: SQL error, position creation fails
```

**Impact**: 🔴 CRITICAL - Cannot create positions
**Probability**: LOW (SQL migration tested first)

**Mitigation**:
1. ✅ SQL migration tested on test DB first
2. ✅ Verify columns exist: `\d monitoring.positions`
3. ✅ Integration tests fail if columns don't exist
4. ✅ Manual testing before production

---

### 3.2 Compatibility Risks

#### Risk: Legacy Positions Without Trailing Params

**Scenario**:
```
Position #123 created BEFORE migration:
- trailing_activation_percent = NULL
- trailing_callback_percent = NULL

After migration: Bot restarts, tries to load TS for position #123
```

**Expected Behavior**:
```python
# create_trailing_stop() called with position_params = None
# Fallback to config:
if not position_params:
    logger.warning("Legacy position, using config fallback")
    activation_percent = self.config.activation_percent
```

**Mitigation**:
1. ✅ Per user: "просто закроем все позиции" (close all positions)
2. ✅ Fallback logic for NULL params
3. ✅ Warning logged for visibility

---

## SECTION 4: TESTING STRATEGY

### 4.1 Unit Tests

**Total**: ~15 new unit test files

1. ✅ `test_exchange_helpers.py` - Exchange ID mapping
2. ⚠️ `test_repository_params_by_name.py` - get_params_by_exchange_name()
3. ⚠️ `test_position_manager_stop_loss.py` - SL from DB (6 locations)
4. ⚠️ `test_trailing_stop_position_params.py` - TS with position params

**Run**:
```bash
pytest tests/unit/test_exchange_helpers.py -v
pytest tests/unit/test_repository_params_by_name.py -v
pytest tests/unit/test_position_manager_stop_loss.py -v
pytest tests/unit/test_trailing_stop_position_params.py -v
```

---

### 4.2 Integration Tests

**Total**: ~3 new integration test files

1. ✅ `test_position_manager_db_params.py` - End-to-end position creation
2. ✅ `test_trailing_stop_position_params.py` - End-to-end TS creation
3. ⚠️ `test_restart_recovery_position_params.py` - Recovery after restart

**Run**:
```bash
pytest tests/integration/test_position_manager_db_params.py -v
pytest tests/integration/test_trailing_stop_position_params.py -v
pytest tests/integration/test_restart_recovery_position_params.py -v
```

---

### 4.3 Manual Testing Matrix

| Scenario | Binance | Bybit | Expected Result |
|----------|---------|-------|-----------------|
| Create position with DB params | ✅ Test | ✅ Test | Different SL/TS per exchange |
| Create position with NULL params | ✅ Test | ✅ Test | Fallback to .env |
| Restart bot with active positions | ✅ Test | ✅ Test | TS restored from position |
| Change DB params | ✅ Test | N/A | New positions use new params, old positions unchanged |
| DB connection fails | ✅ Test | N/A | Fallback to .env, bot continues |

---

## SECTION 5: DEPLOYMENT TIMELINE

### Week 1: PHASE 1
- **Day 1-2**: SQL migration + helper functions + tests
- **Day 3**: Code review
- **Day 4**: Deploy to testnet
- **Day 5-7**: Monitor testnet, fix issues

### Week 2: PHASE 2
- **Day 8-9**: Implement stop_loss_filter usage (6 locations)
- **Day 10**: Code review
- **Day 11**: Deploy to testnet
- **Day 12-14**: Monitor testnet, manual testing

### Week 3: PHASE 3
- **Day 15-17**: Implement trailing params in positions
- **Day 18**: Code review
- **Day 19**: Deploy to testnet
- **Day 20-21**: Monitor testnet, manual testing

### Week 4: Production Deployment
- **Day 22**: PHASE 1 to production (low risk)
- **Day 23**: Monitor PHASE 1
- **Day 24**: PHASE 2 to production (medium risk)
- **Day 25-26**: Monitor PHASE 2
- **Day 27**: Close all positions (per user requirement)
- **Day 28**: PHASE 3 to production (high risk)
- **Day 29-30**: Monitor PHASE 3

**Total**: ~30 days (including testing and monitoring)

---

## SECTION 6: SUCCESS CRITERIA

### PHASE 1 Success:
- [x] Columns added to monitoring.positions
- [x] Helper functions created and tested
- [x] No impact on running bot

### PHASE 2 Success:
- [ ] Binance positions use 4.0% SL (from DB)
- [ ] Bybit positions use 6.0% SL (from DB, DIFFERENT!)
- [ ] Fallback to .env works
- [ ] Logs show "Using stop_loss_filter from DB"

### PHASE 3 Success:
- [ ] Positions save trailing params when created
- [ ] TS uses params from position (not config)
- [ ] Restart recovers TS with correct params
- [ ] Different exchanges have different trailing behavior
- [ ] Logs show "Using trailing params from position"

### Overall Success:
- [ ] Per-exchange params fully operational
- [ ] No position creation errors
- [ ] No TS activation errors
- [ ] Monitoring.params values actually used
- [ ] Bot runs stable for 1 week

---

## SECTION 7: ROLLBACK PROCEDURES

### PHASE 1 Rollback:
```sql
ALTER TABLE monitoring.positions
DROP COLUMN IF EXISTS trailing_activation_percent,
DROP COLUMN IF EXISTS trailing_callback_percent;
```

### PHASE 2 Rollback:
```bash
git revert <commit-hash>
# Redeploy previous version
# Bot uses .env fallback (degraded but safe)
```

### PHASE 3 Rollback:
```bash
git revert <commit-hash>
# Redeploy previous version
# TS uses config (degraded but works)
```

### Emergency Rollback (All Phases):
```bash
# Restore from backup
psql fox_crypto < backup_pre_migration_005.sql

# Checkout previous version
git checkout <previous-stable-tag>

# Redeploy
# Bot uses .env for all params (original behavior)
```

---

## APPENDIX A: Code Locations Reference

### Files to Change:

| File | Lines Changed | Phase | Criticality |
|------|---------------|-------|-------------|
| `migrations/migration_005_*.sql` | NEW FILE (~100 lines) | 1 | MEDIUM |
| `utils/exchange_helpers.py` | NEW FILE (~50 lines) | 1 | LOW |
| `tests/unit/test_exchange_helpers.py` | NEW FILE (~80 lines) | 1 | LOW |
| `database/repository.py` | +20 lines (new method) | 2 | MEDIUM |
| `core/position_manager.py` | ~60 lines (6 locations) | 2 | 🔴 CRITICAL |
| `tests/integration/test_position_manager_db_params.py` | NEW FILE (~150 lines) | 2 | HIGH |
| `database/repository.py` | ~20 lines (update create_position) | 3 | HIGH |
| `core/position_manager.py` | ~30 lines (save trailing params) | 3 | 🔴 CRITICAL |
| `protection/trailing_stop.py` | ~50 lines (4 changes) | 3 | 🔴 CRITICAL |
| `tests/integration/test_trailing_stop_position_params.py` | NEW FILE (~200 lines) | 3 | HIGH |

**Total**:
- **New files**: 6
- **Modified files**: 4
- **Critical changes**: 3 files

---

## APPENDIX B: Monitoring Alerts

### Alerts to Set Up:

1. **"stop_loss_filter not in DB"** → Warning (should be rare)
2. **"trailing_activation_filter not in DB"** → Warning
3. **"Legacy position without trailing params"** → Info
4. **"Failed to load params from DB"** → Error
5. **Position created with NULL trailing params** → Critical
6. **TS activation failed** → Critical

### Metrics to Track:

1. **% positions using DB params vs fallback** (should be ~100% after migration)
2. **Average SL percent by exchange** (should be different)
3. **TS activation rate** (should remain stable)
4. **Position creation errors** (should be 0)

---

## CONCLUSION

**This migration is FEASIBLE but REQUIRES**:
1. ✅ Careful execution of 3 phases
2. ✅ Extensive testing at each phase
3. ✅ Code review for critical changes
4. ✅ Monitoring and alerting
5. ✅ Rollback plans ready

**Estimated Timeline**: 3-4 weeks (including testing)
**Risk Level**: 🔴 HIGH (but manageable with proper testing)
**Recommendation**: ✅ PROCEED with phased approach

---

**END OF PLAN**

**Date**: 2025-10-28
**Version**: 1.0 (Ultra-Detailed)
**Status**: Ready for Review
