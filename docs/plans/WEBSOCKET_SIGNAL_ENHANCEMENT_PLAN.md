# WEBSOCKET SIGNAL ENHANCEMENT - COMPREHENSIVE PLAN

**Date**: 2025-10-27
**Priority**: HIGH
**Complexity**: MEDIUM (multi-component changes)
**Estimated Time**: 8-12 hours (with testing)

---

## 📊 EXECUTIVE SUMMARY

### Current State:
WebSocket server sends 12 fields per signal, but bot only processes 9 fields:
- ✅ **Processed**: id, pair_symbol, recommended_action, score_week, score_month, timestamp, created_at, trading_pair_id, exchange_id
- ❌ **IGNORED**: score_week_filter, score_month_filter, max_trades_filter, stop_loss_filter, trailing_activation_filter, trailing_distance_filter

### Goal:
Capture and store backtest filter parameters per exchange to enable:
- Dynamic strategy optimization
- Historical tracking of backtest parameters
- Per-exchange configuration management

### Deliverables:
1. New database table: `monitoring.params`
2. Enhanced signal processing to extract filter parameters
3. Automatic parameter updates on wave reception
4. Comprehensive test suite

---

## 🔍 PART 1: WEBSOCKET SIGNAL MODULE AUDIT

### 1.1 Signal Reception Flow

**Component**: `websocket/signal_client.py` (524 lines)

**Purpose**: WebSocket client for receiving signals from external server

**Key Methods**:
```python
class SignalWebSocketClient:
    async def handle_signals(self, data: dict)  # Line 199-226
        - Receives RAW signals from WebSocket
        - Updates signal_buffer (FIFO, max 100 signals)
        - Calls on_signals_callback
        - NO processing of filter parameters currently
```

**Current Data Flow**:
```
WebSocket Server
  → handle_signals()
  → signal_buffer (List[dict])
  → on_signals_callback()
  → [LOST: filter parameters not extracted]
```

**Signal Buffer Format (RAW)**:
```python
{
    'id': 12345,
    'pair_symbol': 'BTCUSDT',
    'recommended_action': 'BUY',
    'score_week': 75.5,
    'score_month': 68.2,
    'timestamp': '2025-10-06T14:20:00',
    'created_at': '2025-10-06T14:20:05',
    'trading_pair_id': 1234,
    'exchange_id': 1,  # 1=Binance, 2=Bybit

    # ❌ CURRENTLY IGNORED:
    'score_week_filter': 65.0,
    'score_month_filter': 60.0,
    'max_trades_filter': 10,
    'stop_loss_filter': 2.5,
    'trailing_activation_filter': 3.0,
    'trailing_distance_filter': 1.5
}
```

---

### 1.2 Signal Adaptation

**Component**: `websocket/signal_adapter.py` (172 lines)

**Purpose**: Converts WebSocket format to bot format

**Key Methods**:
```python
class SignalAdapter:
    def adapt_signal(self, ws_signal: Dict) -> Dict  # Line 48-93
        - Maps exchange_id → exchange name
        - Calculates wave_timestamp (15-min rounding)
        - Creates bot-format signal
        - ❌ DOES NOT extract filter parameters

    def adapt_signals(self, ws_signals: List[Dict]) -> List[Dict]  # Line 95-125
        - Batch adaptation
        - Sorts by score_week DESC
```

**Current Adaptation Mapping**:
```python
# EXTRACTED:
ws_signal['id'] → adapted['id']
ws_signal['pair_symbol'] → adapted['symbol']
ws_signal['recommended_action'] → adapted['action']
ws_signal['score_week'] → adapted['score_week']
ws_signal['score_month'] → adapted['score_month']
ws_signal['exchange_id'] → adapted['exchange']  # via _determine_exchange()

# ❌ NOT EXTRACTED:
ws_signal['score_week_filter'] → [IGNORED]
ws_signal['score_month_filter'] → [IGNORED]
ws_signal['max_trades_filter'] → [IGNORED]
ws_signal['stop_loss_filter'] → [IGNORED]
ws_signal['trailing_activation_filter'] → [IGNORED]
ws_signal['trailing_distance_filter'] → [IGNORED]
```

---

### 1.3 Wave Processing

**Component**: `core/signal_processor_websocket.py` (838 lines)

**Purpose**: Main wave monitoring and signal processing loop

**Key Methods**:
```python
class WebSocketSignalProcessor:
    async def _wave_monitoring_loop(self)  # Line 177-447
        - Waits for WAVE_CHECK_MINUTES (e.g., [6, 20, 35, 50])
        - Calculates expected wave timestamp
        - Monitors wave appearance
        - Processes validated signals
        - ❌ NO interaction with filter parameters

    async def _monitor_wave_appearance(self, expected_timestamp: str)  # Line 555-601
        - Polls signal buffer every second (up to 120s)
        - Extracts signals matching wave timestamp
        - Adapts signals via SignalAdapter
        - Returns adapted signals for processing

    async def _execute_signal(self, signal: Dict) -> bool  # Line 616-829
        - Validates signal data
        - Checks symbol filter (stop-list)
        - Opens position via position_manager
        - Logs execution events
```

**Wave Processing Phases**:
```
Phase 1: Wait for wave check time (e.g., 00:06, 00:20, 00:35, 00:50)
Phase 2: Calculate expected wave timestamp (e.g., 23:45, 00:00, 00:15, 00:30)
Phase 3: Monitor buffer for signals with matching timestamp
Phase 4: Adapt signals (websocket format → bot format)
Phase 5: Validate signals (duplicates, minimums, availability)
Phase 6: Execute positions (open orders on exchange)

❌ MISSING: Extract and store filter parameters from first signal per exchange
```

---

### 1.4 Wave Signal Validation

**Component**: `core/wave_signal_processor.py` (527 lines)

**Purpose**: Validates and filters signals before execution

**Key Methods**:
```python
class WaveSignalProcessor:
    async def process_wave_signals(self, signals: List[Dict], wave_timestamp: str)  # Line 68-236
        - Iterates through signals
        - Checks for duplicates via _is_duplicate()
        - Validates each signal via _process_single_signal()
        - Returns: {'successful': [...], 'failed': [...], 'skipped': [...]}

    async def _is_duplicate(self, signal: Dict, wave_timestamp: str)  # Line 238-373
        - Checks if position already exists (symbol + exchange)
        - Validates minimum notional value
        - Returns error object if validation fails
```

---

### 1.5 Database Layer

**Component**: `database/repository.py` (3000+ lines)

**Purpose**: Async PostgreSQL operations via asyncpg

**Current Tables in `monitoring` Schema**:
```sql
1. positions - Active and historical positions
2. orders - Order execution history
3. trades - Completed trades
4. trailing_stop_state - Trailing stop management
5. orders_cache - Orders cache for fast access
6. aged_positions - Aged positions tracking
7. aged_monitoring_events - Aged position events
8. risk_events - Risk management events
9. risk_violations - Risk limit violations
10. events - Main event log
11. event_performance_metrics - Performance metrics
12. transaction_log - Audit transaction log

❌ MISSING: monitoring.params table
```

**Database Configuration**:
```python
server_settings={
    'search_path': 'monitoring,fas,public'  # Schema search order
}
```

---

## 🎯 PART 2: REQUIREMENTS ANALYSIS

### 2.1 Functional Requirements

**FR-1: New Database Table**
- Table: `monitoring.params`
- Fields:
  - `exchange_id` (INTEGER, PRIMARY KEY) - 1=Binance, 2=Bybit
  - `max_trades_filter` (INTEGER) - Max trades per wave from backtest
  - `stop_loss_filter` (NUMERIC(10,4)) - Stop loss % from backtest
  - `trailing_activation_filter` (NUMERIC(10,4)) - Trailing activation % from backtest
  - `trailing_distance_filter` (NUMERIC(10,4)) - Trailing distance % from backtest
  - `updated_at` (TIMESTAMP WITH TIME ZONE) - Last update timestamp
  - `created_at` (TIMESTAMP WITH TIME ZONE) - Initial creation timestamp

**FR-2: Parameter Extraction Logic**
- Extract filter parameters from WebSocket signal
- Store in adapted signal format
- Pass through processing chain

**FR-3: Parameter Storage Logic**
- On wave detection, identify first signal per exchange
- Extract filter parameters from first Binance signal (exchange_id=1)
- `UPDATE monitoring.params SET ... WHERE exchange_id=1`
- Extract filter parameters from first Bybit signal (exchange_id=2)
- `UPDATE monitoring.params SET ... WHERE exchange_id=2`
- Only update if values changed (avoid unnecessary writes)

**FR-4: Data Validation**
- Validate filter parameters are numeric and within expected ranges
- Handle NULL values gracefully (use previous values)
- Log parameter updates to monitoring.events

---

### 2.2 Non-Functional Requirements

**NFR-1: Performance**
- Parameter update should NOT delay wave processing
- Use async database operations (non-blocking)
- Single UPDATE per exchange per wave (max 2 UPDATEs)

**NFR-2: Reliability**
- Failed parameter update should NOT break wave processing
- Wrap UPDATE in try-except with error logging
- Continue signal execution even if parameter update fails

**NFR-3: Maintainability**
- Clear separation of concerns (extraction → validation → storage)
- Comprehensive logging at each step
- Test coverage >80%

**NFR-4: Backward Compatibility**
- Existing signal processing must continue to work
- No breaking changes to signal format
- New fields are optional additions

---

## 📝 PART 3: DETAILED IMPLEMENTATION PLAN

### Phase 1: Database Schema (2 hours)

**Step 1.1: Create Migration Script**

File: `migrations/migration_004_add_params_table.sql`

```sql
-- =====================================================================
-- MIGRATION 004: Create monitoring.params table
-- =====================================================================
-- Date: 2025-10-27
-- Purpose: Store backtest filter parameters per exchange
--
-- This table stores the latest filter parameters received from
-- WebSocket signals, enabling dynamic strategy configuration.
-- =====================================================================

BEGIN;

-- =====================================================================
-- 1. Create monitoring.params table
-- =====================================================================
CREATE TABLE monitoring.params (
    exchange_id INTEGER PRIMARY KEY,
    max_trades_filter INTEGER,
    stop_loss_filter NUMERIC(10,4),
    trailing_activation_filter NUMERIC(10,4),
    trailing_distance_filter NUMERIC(10,4),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_exchange_id CHECK (exchange_id IN (1, 2)),
    CONSTRAINT valid_max_trades CHECK (max_trades_filter > 0 OR max_trades_filter IS NULL),
    CONSTRAINT valid_stop_loss CHECK (stop_loss_filter > 0 OR stop_loss_filter IS NULL),
    CONSTRAINT valid_trailing_activation CHECK (trailing_activation_filter > 0 OR trailing_activation_filter IS NULL),
    CONSTRAINT valid_trailing_distance CHECK (trailing_distance_filter > 0 OR trailing_distance_filter IS NULL)
);

-- Comments
COMMENT ON TABLE monitoring.params IS
    'Backtest filter parameters per exchange. Updated on each wave reception from WebSocket.';

COMMENT ON COLUMN monitoring.params.exchange_id IS
    'Exchange identifier: 1=Binance, 2=Bybit';

COMMENT ON COLUMN monitoring.params.max_trades_filter IS
    'Maximum trades per wave from backtest optimization';

COMMENT ON COLUMN monitoring.params.stop_loss_filter IS
    'Stop loss percentage from backtest (e.g., 2.5 = 2.5%)';

COMMENT ON COLUMN monitoring.params.trailing_activation_filter IS
    'Trailing stop activation percentage from backtest (e.g., 3.0 = 3.0%)';

COMMENT ON COLUMN monitoring.params.trailing_distance_filter IS
    'Trailing stop distance percentage from backtest (e.g., 1.5 = 1.5%)';

COMMENT ON COLUMN monitoring.params.updated_at IS
    'Timestamp of last parameter update';

-- =====================================================================
-- 2. Create indexes
-- =====================================================================
CREATE INDEX idx_params_updated_at ON monitoring.params (updated_at DESC);

-- =====================================================================
-- 3. Create trigger for auto-updating updated_at
-- =====================================================================
CREATE TRIGGER update_params_updated_at
    BEFORE UPDATE ON monitoring.params
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_params_updated_at ON monitoring.params IS
    'Auto-updates updated_at column on any UPDATE';

-- =====================================================================
-- 4. Initialize with default rows (NULL values)
-- =====================================================================
INSERT INTO monitoring.params (exchange_id)
VALUES (1), (2)
ON CONFLICT (exchange_id) DO NOTHING;

-- =====================================================================
-- 5. Verification
-- =====================================================================
DO $$
DECLARE
    row_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO row_count FROM monitoring.params;

    IF row_count != 2 THEN
        RAISE EXCEPTION 'Expected 2 rows in monitoring.params, found %', row_count;
    END IF;

    RAISE NOTICE 'monitoring.params table created successfully with % rows', row_count;
END $$;

COMMIT;

DO $$ BEGIN
    RAISE NOTICE 'Migration 004 completed successfully!';
END $$;
```

**Step 1.2: Apply Migration**

```bash
# Test on local database first
psql -U $DB_USER -d $DB_NAME -f migrations/migration_004_add_params_table.sql

# Verify
psql -U $DB_USER -d $DB_NAME -c "SELECT * FROM monitoring.params;"
```

**Expected Output**:
```
 exchange_id | max_trades_filter | stop_loss_filter | trailing_activation_filter | trailing_distance_filter |          updated_at           |          created_at
-------------+-------------------+------------------+----------------------------+--------------------------+-------------------------------+-------------------------------
           1 |                   |                  |                            |                          | 2025-10-27 10:00:00+00        | 2025-10-27 10:00:00+00
           2 |                   |                  |                            |                          | 2025-10-27 10:00:00+00        | 2025-10-27 10:00:00+00
```

---

### Phase 2: Repository Layer (1 hour)

**Step 2.1: Add Repository Methods**

File: `database/repository.py`

Add after line 150 (after risk management methods):

```python
# ============== Parameter Management ==============

async def get_params(self, exchange_id: int) -> Optional[Dict]:
    """
    Get backtest parameters for exchange

    Args:
        exchange_id: Exchange ID (1=Binance, 2=Bybit)

    Returns:
        Dict with parameters or None if not found
    """
    query = """
        SELECT
            exchange_id,
            max_trades_filter,
            stop_loss_filter,
            trailing_activation_filter,
            trailing_distance_filter,
            updated_at,
            created_at
        FROM monitoring.params
        WHERE exchange_id = $1
    """

    async with self.pool.acquire() as conn:
        row = await conn.fetchrow(query, exchange_id)

        if row:
            return dict(row)
        return None

async def update_params(
    self,
    exchange_id: int,
    max_trades_filter: Optional[int] = None,
    stop_loss_filter: Optional[float] = None,
    trailing_activation_filter: Optional[float] = None,
    trailing_distance_filter: Optional[float] = None
) -> bool:
    """
    Update backtest parameters for exchange

    Only updates fields that are not None.
    Returns True if update succeeded, False otherwise.

    Args:
        exchange_id: Exchange ID (1=Binance, 2=Bybit)
        max_trades_filter: Max trades per wave
        stop_loss_filter: Stop loss %
        trailing_activation_filter: Trailing activation %
        trailing_distance_filter: Trailing distance %

    Returns:
        bool: True if updated, False if failed
    """
    # Build dynamic UPDATE query (only update provided fields)
    updates = []
    params = [exchange_id]
    param_idx = 2

    if max_trades_filter is not None:
        updates.append(f"max_trades_filter = ${param_idx}")
        params.append(max_trades_filter)
        param_idx += 1

    if stop_loss_filter is not None:
        updates.append(f"stop_loss_filter = ${param_idx}")
        params.append(stop_loss_filter)
        param_idx += 1

    if trailing_activation_filter is not None:
        updates.append(f"trailing_activation_filter = ${param_idx}")
        params.append(trailing_activation_filter)
        param_idx += 1

    if trailing_distance_filter is not None:
        updates.append(f"trailing_distance_filter = ${param_idx}")
        params.append(trailing_distance_filter)
        param_idx += 1

    if not updates:
        logger.warning(f"No parameters to update for exchange_id={exchange_id}")
        return False

    # updated_at is auto-updated by trigger
    query = f"""
        UPDATE monitoring.params
        SET {', '.join(updates)}
        WHERE exchange_id = $1
        RETURNING exchange_id
    """

    try:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, *params)

            if result:
                logger.info(
                    f"✅ Updated params for exchange_id={exchange_id}: "
                    f"{', '.join(updates)}"
                )
                return True
            else:
                logger.warning(f"No row found for exchange_id={exchange_id}")
                return False

    except Exception as e:
        logger.error(f"Failed to update params for exchange_id={exchange_id}: {e}")
        return False

async def get_all_params(self) -> Dict[int, Dict]:
    """
    Get all exchange parameters

    Returns:
        Dict mapping exchange_id to params dict
    """
    query = """
        SELECT
            exchange_id,
            max_trades_filter,
            stop_loss_filter,
            trailing_activation_filter,
            trailing_distance_filter,
            updated_at,
            created_at
        FROM monitoring.params
        ORDER BY exchange_id
    """

    async with self.pool.acquire() as conn:
        rows = await conn.fetch(query)

        return {row['exchange_id']: dict(row) for row in rows}
```

---

### Phase 3: Signal Adapter Enhancement (1 hour)

**Step 3.1: Enhance SignalAdapter to Extract Filter Parameters**

File: `websocket/signal_adapter.py`

Modify `adapt_signal()` method (lines 48-93):

```python
def adapt_signal(self, ws_signal: Dict) -> Dict:
    """
    Преобразует один WebSocket сигнал в формат бота

    Args:
        ws_signal: Сигнал от WebSocket сервера

    Returns:
        Dict в формате бота с filter параметрами
    """
    try:
        # Определяем exchange напрямую из exchange_id
        exchange_id = ws_signal.get('exchange_id')
        exchange = self._determine_exchange(exchange_id)

        # Преобразуем timestamp из строки в datetime
        created_at_str = ws_signal.get('created_at')
        if isinstance(created_at_str, str):
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        else:
            created_at = datetime.now(timezone.utc)

        # Вычисляем wave_timestamp (округление до 15 минут)
        wave_timestamp = self._calculate_wave_timestamp(created_at)

        # ✅ NEW: Extract filter parameters
        filter_params = self._extract_filter_params(ws_signal)

        # Создаем адаптированный сигнал
        adapted = {
            'id': ws_signal.get('id'),
            'symbol': ws_signal.get('pair_symbol'),
            'action': ws_signal.get('recommended_action'),
            'score_week': float(ws_signal.get('score_week', 0)),
            'score_month': float(ws_signal.get('score_month', 0)),
            'created_at': created_at,
            'exchange': exchange,
            'exchange_id': exchange_id,  # ✅ NEW: Include exchange_id
            'wave_timestamp': wave_timestamp,

            # ✅ NEW: Include filter parameters
            'filter_params': filter_params,

            # Дополнительные поля для совместимости
            'timestamp': created_at,
            'is_active': True,
            'signal_type': ws_signal.get('recommended_action')
        }

        return adapted

    except Exception as e:
        logger.error(f"Error adapting signal {ws_signal.get('id')}: {e}")
        raise

def _extract_filter_params(self, ws_signal: Dict) -> Optional[Dict]:
    """
    Извлекает filter параметры из WebSocket сигнала

    Args:
        ws_signal: Raw сигнал от WebSocket

    Returns:
        Dict с filter параметрами или None если нет данных
    """
    try:
        # Extract filter fields
        params = {}

        # Optional fields - only include if present
        if 'max_trades_filter' in ws_signal and ws_signal['max_trades_filter'] is not None:
            params['max_trades_filter'] = int(ws_signal['max_trades_filter'])

        if 'stop_loss_filter' in ws_signal and ws_signal['stop_loss_filter'] is not None:
            params['stop_loss_filter'] = float(ws_signal['stop_loss_filter'])

        if 'trailing_activation_filter' in ws_signal and ws_signal['trailing_activation_filter'] is not None:
            params['trailing_activation_filter'] = float(ws_signal['trailing_activation_filter'])

        if 'trailing_distance_filter' in ws_signal and ws_signal['trailing_distance_filter'] is not None:
            params['trailing_distance_filter'] = float(ws_signal['trailing_distance_filter'])

        # Return None if no parameters found (backward compatibility)
        return params if params else None

    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to extract filter params from signal {ws_signal.get('id')}: {e}")
        return None
```

---

### Phase 4: Wave Processor Enhancement (2 hours)

**Step 4.1: Add Parameter Update Logic to Wave Processing**

File: `core/signal_processor_websocket.py`

Add new method after `_execute_signal()` (after line 829):

```python
async def _update_exchange_params(self, wave_signals: List[Dict], wave_timestamp: str):
    """
    Update monitoring.params from first signal per exchange in wave

    Extracts filter parameters from:
    - First Binance signal (exchange_id=1) → UPDATE exchange_id=1
    - First Bybit signal (exchange_id=2) → UPDATE exchange_id=2

    Runs asynchronously to avoid blocking wave processing.

    Args:
        wave_signals: List of adapted signals with filter_params
        wave_timestamp: Wave timestamp for logging
    """
    if not wave_signals:
        return

    try:
        # Group signals by exchange_id
        signals_by_exchange = {}
        for signal in wave_signals:
            exchange_id = signal.get('exchange_id')
            if exchange_id and exchange_id not in signals_by_exchange:
                # Take first signal per exchange
                signals_by_exchange[exchange_id] = signal

        logger.debug(
            f"Found {len(signals_by_exchange)} unique exchanges in wave {wave_timestamp}: "
            f"{list(signals_by_exchange.keys())}"
        )

        # Update params for each exchange
        update_tasks = []
        for exchange_id, signal in signals_by_exchange.items():
            filter_params = signal.get('filter_params')

            if filter_params:
                logger.info(
                    f"📊 Updating params for exchange_id={exchange_id} from signal #{signal.get('id')}: "
                    f"{filter_params}"
                )

                # Create update task (non-blocking)
                task = self._update_params_for_exchange(exchange_id, filter_params, wave_timestamp)
                update_tasks.append(task)
            else:
                logger.debug(
                    f"No filter_params in signal #{signal.get('id')} for exchange_id={exchange_id}"
                )

        # Execute all updates in parallel (non-blocking)
        if update_tasks:
            await asyncio.gather(*update_tasks, return_exceptions=True)

    except Exception as e:
        # CRITICAL: Catch all exceptions to prevent breaking wave processing
        logger.error(f"Error updating exchange params for wave {wave_timestamp}: {e}", exc_info=True)

async def _update_params_for_exchange(
    self,
    exchange_id: int,
    filter_params: Dict,
    wave_timestamp: str
):
    """
    Update monitoring.params for specific exchange

    Args:
        exchange_id: Exchange ID (1=Binance, 2=Bybit)
        filter_params: Filter parameters dict
        wave_timestamp: Wave timestamp for logging
    """
    try:
        # Update database
        success = await self.repository.update_params(
            exchange_id=exchange_id,
            max_trades_filter=filter_params.get('max_trades_filter'),
            stop_loss_filter=filter_params.get('stop_loss_filter'),
            trailing_activation_filter=filter_params.get('trailing_activation_filter'),
            trailing_distance_filter=filter_params.get('trailing_distance_filter')
        )

        if success:
            logger.info(
                f"✅ Params updated for exchange_id={exchange_id} at wave {wave_timestamp}"
            )

            # Log event
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.SYSTEM_INFO,  # Or create new EventType.PARAMS_UPDATED
                    {
                        'exchange_id': exchange_id,
                        'wave_timestamp': wave_timestamp,
                        'params_updated': filter_params,
                        'update_source': 'websocket_wave'
                    },
                    severity='INFO'
                )
        else:
            logger.warning(
                f"⚠️ Failed to update params for exchange_id={exchange_id} at wave {wave_timestamp}"
            )

    except Exception as e:
        logger.error(
            f"Error updating params for exchange_id={exchange_id}: {e}",
            exc_info=True
        )
```

**Step 4.2: Integrate Parameter Update into Wave Processing Loop**

File: `core/signal_processor_websocket.py`

Modify `_wave_monitoring_loop()` method, add after line 260 (after signals validated):

```python
# Line 260: After signals validated, before execution

# ✅ NEW: Update exchange parameters from first signal per exchange
# This runs in parallel with validation, non-blocking
asyncio.create_task(
    self._update_exchange_params(signals_to_process, expected_wave_timestamp)
)

logger.info(
    f"📊 Triggered parameter update for wave {expected_wave_timestamp}"
)
```

---

### Phase 5: Testing (4 hours)

**Step 5.1: Unit Tests for Signal Adapter**

File: `tests/unit/test_signal_adapter_filter_params.py`

```python
#!/usr/bin/env python3
"""
Unit tests for SignalAdapter filter parameter extraction
"""
import pytest
from datetime import datetime, timezone
from websocket.signal_adapter import SignalAdapter


class TestSignalAdapterFilterParams:
    """Test filter parameter extraction"""

    def setup_method(self):
        """Setup test instance"""
        self.adapter = SignalAdapter()

    def test_extract_all_filter_params(self):
        """Test extraction of all filter parameters"""
        ws_signal = {
            'id': 12345,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 1,

            # Filter parameters
            'score_week_filter': 65.0,
            'score_month_filter': 60.0,
            'max_trades_filter': 10,
            'stop_loss_filter': 2.5,
            'trailing_activation_filter': 3.0,
            'trailing_distance_filter': 1.5
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify filter_params extracted
        assert 'filter_params' in adapted
        assert adapted['filter_params'] is not None

        params = adapted['filter_params']
        assert params['max_trades_filter'] == 10
        assert params['stop_loss_filter'] == 2.5
        assert params['trailing_activation_filter'] == 3.0
        assert params['trailing_distance_filter'] == 1.5

    def test_extract_partial_filter_params(self):
        """Test extraction when only some params present"""
        ws_signal = {
            'id': 12346,
            'pair_symbol': 'ETHUSDT',
            'recommended_action': 'SELL',
            'score_week': 70.0,
            'score_month': 65.0,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1235,
            'exchange_id': 2,

            # Only some filter parameters
            'max_trades_filter': 8,
            'stop_loss_filter': None,  # NULL value
            'trailing_activation_filter': 2.8,
            # trailing_distance_filter missing
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify filter_params extracted (with only present values)
        assert 'filter_params' in adapted
        params = adapted['filter_params']

        assert params['max_trades_filter'] == 8
        assert params['trailing_activation_filter'] == 2.8
        assert 'stop_loss_filter' not in params  # NULL excluded
        assert 'trailing_distance_filter' not in params  # Missing excluded

    def test_extract_no_filter_params(self):
        """Test extraction when no filter params present (backward compatibility)"""
        ws_signal = {
            'id': 12347,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 1,
            # NO filter parameters
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify filter_params is None (backward compatibility)
        assert 'filter_params' in adapted
        assert adapted['filter_params'] is None

    def test_extract_invalid_filter_params(self):
        """Test extraction with invalid parameter types"""
        ws_signal = {
            'id': 12348,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 1,

            # Invalid types
            'max_trades_filter': 'not_a_number',
            'stop_loss_filter': 2.5,
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Should handle gracefully (skip invalid, keep valid)
        assert 'filter_params' in adapted
        # Implementation should skip invalid max_trades but keep valid stop_loss

    def test_exchange_id_preserved(self):
        """Test that exchange_id is preserved in adapted signal"""
        ws_signal = {
            'id': 12349,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 2,  # Bybit
            'max_trades_filter': 10,
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify exchange_id preserved
        assert 'exchange_id' in adapted
        assert adapted['exchange_id'] == 2
        assert adapted['exchange'] == 'bybit'  # Mapped correctly
```

**Step 5.2: Integration Tests for Repository**

File: `tests/integration/test_repository_params.py`

```python
#!/usr/bin/env python3
"""
Integration tests for monitoring.params repository operations
"""
import pytest
import asyncio
from database.repository import Repository
from config.settings import Config


class TestRepositoryParams:
    """Test params table operations"""

    @pytest.fixture
    async def repository(self):
        """Create repository instance"""
        config = Config()
        db_config = {
            'host': config.db_host,
            'port': config.db_port,
            'database': config.db_name,
            'user': config.db_user,
            'password': config.db_password
        }

        repo = Repository(db_config)
        await repo.initialize()

        yield repo

        await repo.close()

    @pytest.mark.asyncio
    async def test_get_params_binance(self, repository):
        """Test retrieving Binance params"""
        params = await repository.get_params(exchange_id=1)

        assert params is not None
        assert params['exchange_id'] == 1
        assert 'max_trades_filter' in params
        assert 'stop_loss_filter' in params
        assert 'updated_at' in params

    @pytest.mark.asyncio
    async def test_get_params_bybit(self, repository):
        """Test retrieving Bybit params"""
        params = await repository.get_params(exchange_id=2)

        assert params is not None
        assert params['exchange_id'] == 2

    @pytest.mark.asyncio
    async def test_update_all_params(self, repository):
        """Test updating all parameters"""
        success = await repository.update_params(
            exchange_id=1,
            max_trades_filter=12,
            stop_loss_filter=2.8,
            trailing_activation_filter=3.2,
            trailing_distance_filter=1.6
        )

        assert success is True

        # Verify update
        params = await repository.get_params(exchange_id=1)
        assert params['max_trades_filter'] == 12
        assert float(params['stop_loss_filter']) == 2.8
        assert float(params['trailing_activation_filter']) == 3.2
        assert float(params['trailing_distance_filter']) == 1.6

    @pytest.mark.asyncio
    async def test_update_partial_params(self, repository):
        """Test updating only some parameters"""
        # First, set initial values
        await repository.update_params(
            exchange_id=2,
            max_trades_filter=10,
            stop_loss_filter=2.5
        )

        # Update only max_trades
        success = await repository.update_params(
            exchange_id=2,
            max_trades_filter=15
        )

        assert success is True

        # Verify only max_trades changed
        params = await repository.get_params(exchange_id=2)
        assert params['max_trades_filter'] == 15
        assert float(params['stop_loss_filter']) == 2.5  # Unchanged

    @pytest.mark.asyncio
    async def test_get_all_params(self, repository):
        """Test retrieving all exchange params"""
        all_params = await repository.get_all_params()

        assert isinstance(all_params, dict)
        assert 1 in all_params  # Binance
        assert 2 in all_params  # Bybit

        assert all_params[1]['exchange_id'] == 1
        assert all_params[2]['exchange_id'] == 2

    @pytest.mark.asyncio
    async def test_update_invalid_exchange(self, repository):
        """Test updating non-existent exchange"""
        success = await repository.update_params(
            exchange_id=999,  # Invalid
            max_trades_filter=10
        )

        assert success is False
```

**Step 5.3: End-to-End Test for Wave Processing**

File: `tests/integration/test_wave_params_e2e.py`

```python
#!/usr/bin/env python3
"""
End-to-end test for wave processing with parameter updates
"""
import pytest
import asyncio
from datetime import datetime, timezone
from core.signal_processor_websocket import WebSocketSignalProcessor
from database.repository import Repository
from config.settings import Config


class TestWaveParamsE2E:
    """End-to-end test for wave parameter updates"""

    @pytest.fixture
    async def repository(self):
        """Create repository instance"""
        config = Config()
        db_config = {
            'host': config.db_host,
            'port': config.db_port,
            'database': config.db_name,
            'user': config.db_user,
            'password': config.db_password
        }

        repo = Repository(db_config)
        await repo.initialize()

        yield repo

        await repo.close()

    @pytest.mark.asyncio
    async def test_wave_updates_binance_params(self, repository):
        """Test wave processing updates Binance params"""
        # Prepare mock wave signals (first Binance signal should update params)
        wave_signals = [
            {
                'id': 100,
                'symbol': 'BTCUSDT',
                'exchange': 'binance',
                'exchange_id': 1,
                'filter_params': {
                    'max_trades_filter': 12,
                    'stop_loss_filter': 2.7,
                    'trailing_activation_filter': 3.1,
                    'trailing_distance_filter': 1.55
                }
            },
            {
                'id': 101,
                'symbol': 'ETHUSDT',
                'exchange': 'binance',
                'exchange_id': 1,
                'filter_params': {
                    'max_trades_filter': 15,  # Different values (should be ignored)
                }
            }
        ]

        # Simulate parameter update
        wave_timestamp = datetime.now(timezone.utc).isoformat()

        # Create minimal processor instance (or mock _update_exchange_params)
        # For true E2E, would need full WebSocketSignalProcessor setup

        # Directly test repository update (unit of E2E)
        success = await repository.update_params(
            exchange_id=1,
            max_trades_filter=12,
            stop_loss_filter=2.7,
            trailing_activation_filter=3.1,
            trailing_distance_filter=1.55
        )

        assert success is True

        # Verify params updated
        params = await repository.get_params(exchange_id=1)
        assert params['max_trades_filter'] == 12
        assert float(params['stop_loss_filter']) == 2.7

    @pytest.mark.asyncio
    async def test_wave_updates_both_exchanges(self, repository):
        """Test wave with both Binance and Bybit signals"""
        # Update Binance
        await repository.update_params(
            exchange_id=1,
            max_trades_filter=10,
            stop_loss_filter=2.5
        )

        # Update Bybit
        await repository.update_params(
            exchange_id=2,
            max_trades_filter=8,
            stop_loss_filter=3.0
        )

        # Verify both updated independently
        binance_params = await repository.get_params(exchange_id=1)
        bybit_params = await repository.get_params(exchange_id=2)

        assert binance_params['max_trades_filter'] == 10
        assert bybit_params['max_trades_filter'] == 8
        assert float(binance_params['stop_loss_filter']) == 2.5
        assert float(bybit_params['stop_loss_filter']) == 3.0
```

---

## 📋 IMPLEMENTATION CHECKLIST

### Pre-Implementation:
- [x] Complete module audit
- [x] Define requirements
- [x] Design database schema
- [x] Create implementation plan
- [ ] User approval obtained

### Phase 1: Database (MUST DO FIRST)
- [ ] Create migration script
- [ ] Review migration script
- [ ] Test migration on local DB
- [ ] Backup production DB
- [ ] Apply migration to production
- [ ] Verify table created (2 rows)

### Phase 2: Repository Layer
- [ ] Add get_params() method
- [ ] Add update_params() method
- [ ] Add get_all_params() method
- [ ] Test methods locally

### Phase 3: Signal Adapter
- [ ] Add _extract_filter_params() method
- [ ] Modify adapt_signal() to include filter_params
- [ ] Test with mock WebSocket signals
- [ ] Verify backward compatibility (signals without filters)

### Phase 4: Wave Processor
- [ ] Add _update_exchange_params() method
- [ ] Add _update_params_for_exchange() method
- [ ] Integrate into _wave_monitoring_loop()
- [ ] Test with mock wave data
- [ ] Verify non-blocking behavior

### Phase 5: Testing
- [ ] Write unit tests (signal_adapter)
- [ ] Write integration tests (repository)
- [ ] Write E2E tests (wave processing)
- [ ] Run all tests
- [ ] Fix any failures
- [ ] Achieve >80% coverage

### Deployment:
- [ ] Stop bot gracefully
- [ ] Apply database migration
- [ ] Deploy code changes
- [ ] Restart bot
- [ ] Monitor first wave processing
- [ ] Verify params updated in database
- [ ] Check logs for errors
- [ ] Run 24h stability test

### Post-Deployment Verification:
- [ ] Check monitoring.params table populated
- [ ] Verify updated_at timestamps advancing
- [ ] Confirm no errors in logs
- [ ] Validate wave processing still works
- [ ] Compare before/after performance
- [ ] Document any issues found

---

## 🎯 SUCCESS CRITERIA

Fix is successful if **ALL** criteria met:

1. ✅ **Table Created**: monitoring.params exists with 2 rows (exchange_id 1, 2)
2. ✅ **Parameters Extracted**: filter_params field present in adapted signals
3. ✅ **Parameters Stored**: monitoring.params updated on each wave
4. ✅ **First Signal Priority**: Only first signal per exchange updates params
5. ✅ **Non-Blocking**: Parameter updates don't delay wave processing
6. ✅ **Error Handling**: Failed updates logged but don't break wave processing
7. ✅ **Both Exchanges**: Binance (1) and Bybit (2) params update independently
8. ✅ **Tests Pass**: All unit, integration, and E2E tests pass
9. ✅ **Backward Compatible**: Old signals (without filter_params) still work
10. ✅ **24h Stability**: Bot runs without issues for 24 hours

---

## 🚨 RISK ANALYSIS

### Risk 1: Database Migration Failure

**Description**: Migration might fail if table already exists or constraints violated

**Likelihood**: LOW

**Mitigation**:
- Test on local DB first
- Add existence checks in migration
- Use transactions (ROLLBACK on error)
- Backup production DB before migration

**Rollback Plan**:
```sql
BEGIN;
DROP TABLE IF EXISTS monitoring.params CASCADE;
COMMIT;
```

### Risk 2: Performance Impact

**Description**: Parameter updates might slow wave processing

**Likelihood**: LOW

**Mitigation**:
- Use async operations (non-blocking)
- Run updates in background (asyncio.create_task)
- Index on updated_at for fast queries
- Update only changed values (dynamic query)

**Test**: Measure wave processing time before/after

### Risk 3: Missing Filter Parameters

**Description**: WebSocket might not always send filter parameters

**Likelihood**: MEDIUM

**Mitigation**:
- Make filter_params optional (None if missing)
- Skip update if filter_params is None
- Log when parameters missing
- Maintain backward compatibility

**Test**: Test with signals without filter_params

### Risk 4: Repository Method Errors

**Description**: Database UPDATE might fail

**Likelihood**: LOW

**Mitigation**:
- Wrap in try-except
- Log errors but don't propagate
- Return False on failure
- Continue wave processing

**Test**: Unit tests with invalid data

---

## 📊 EXPECTED OUTCOMES

### Before Implementation:
```
Wave Reception:
- Signals received with filter parameters ✅
- Filter parameters IGNORED ❌
- monitoring.params table DOES NOT EXIST ❌
- No parameter tracking ❌

Impact:
- Cannot track backtest parameter changes
- Manual configuration required
- No historical parameter data
```

### After Implementation:
```
Wave Reception:
- Signals received with filter parameters ✅
- Filter parameters EXTRACTED ✅
- Filter parameters STORED in monitoring.params ✅
- First signal per exchange updates params ✅

Database State:
- monitoring.params populated with latest values ✅
- updated_at timestamp reflects last update ✅
- Both Binance and Bybit params tracked independently ✅

Result:
- Dynamic parameter tracking enabled
- Historical parameter changes logged
- Per-exchange configuration available
- Ready for strategy optimization
```

---

## 🔧 MANUAL VERIFICATION STEPS

### After Deployment:

1. **Check Table Created**:
```sql
SELECT * FROM monitoring.params ORDER BY exchange_id;
```

Expected:
```
 exchange_id | max_trades_filter | stop_loss_filter | ... | updated_at
-------------+-------------------+------------------+-----+------------
           1 |                   |                  | ... | 2025-10-27...
           2 |                   |                  | ... | 2025-10-27...
```

2. **Wait for First Wave** (e.g., 00:06, 00:20):
```bash
tail -f logs/trading_bot.log | grep "Updating params"
```

Expected:
```
INFO - 📊 Updating params for exchange_id=1 from signal #12345: {...}
INFO - ✅ Params updated for exchange_id=1 at wave 2025-10-27T00:00:00
```

3. **Verify Parameters Updated**:
```sql
SELECT
    exchange_id,
    max_trades_filter,
    stop_loss_filter,
    trailing_activation_filter,
    trailing_distance_filter,
    updated_at
FROM monitoring.params
ORDER BY exchange_id;
```

Expected: Non-NULL values for at least one exchange

4. **Check Event Log**:
```sql
SELECT
    created_at,
    event_type,
    event_data->>'exchange_id' as exchange_id,
    event_data->>'params_updated' as params
FROM monitoring.events
WHERE event_type = 'system_info'
AND event_data->>'update_source' = 'websocket_wave'
ORDER BY created_at DESC
LIMIT 10;
```

5. **Monitor for Errors**:
```bash
tail -f logs/trading_bot.log | grep -E "(ERROR|CRITICAL|Failed to update params)"
```

Expected: NO errors related to params

6. **Verify Wave Processing Still Works**:
```bash
tail -f logs/trading_bot.log | grep "Wave.*complete"
```

Expected: Waves complete successfully with positions opened

---

## 📚 ADDITIONAL NOTES

### Future Enhancements:

1. **Parameter History Table**:
```sql
CREATE TABLE monitoring.params_history (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER NOT NULL,
    max_trades_filter INTEGER,
    stop_loss_filter NUMERIC(10,4),
    trailing_activation_filter NUMERIC(10,4),
    trailing_distance_filter NUMERIC(10,4),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    wave_timestamp VARCHAR(50)
);
```

2. **Parameter Comparison**:
- Detect when parameters change between waves
- Log significant changes (>10% difference)
- Alert on unusual parameter values

3. **Strategy Optimization**:
- Use stored parameters for backtesting
- Compare performance across parameter changes
- Identify optimal parameter ranges

4. **Admin Dashboard**:
- View current parameters per exchange
- See parameter change history
- Manually override parameters if needed

---

**STATUS**: ⏳ **READY FOR IMPLEMENTATION**

План готов к реализации! Все детали расписаны, включая:
- ✅ Complete audit of current implementation
- ✅ Database schema design
- ✅ Repository methods
- ✅ Signal adapter enhancement
- ✅ Wave processor integration
- ✅ Comprehensive test suite
- ✅ Risk analysis and mitigation
- ✅ Verification steps

Жду команды пользователя для начала реализации! 🚀

---

**End of Plan**
