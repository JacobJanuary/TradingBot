-- Create schemas
CREATE SCHEMA IF NOT EXISTS fas;
CREATE SCHEMA IF NOT EXISTS monitoring;

-- FAS schema tables (for signal source)
CREATE TABLE IF NOT EXISTS fas.scoring_history (
    id SERIAL PRIMARY KEY,
    trading_pair_id INTEGER NOT NULL,
    pair_symbol VARCHAR(20) NOT NULL,
    exchange_id INTEGER NOT NULL,
    exchange_name VARCHAR(50) NOT NULL,
    score_week FLOAT,
    score_month FLOAT,
    recommended_action VARCHAR(10),
    patterns_details JSONB,
    combinations_details JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_processed BOOLEAN DEFAULT FALSE
);

-- Monitoring schema tables
CREATE TABLE IF NOT EXISTS monitoring.positions (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    stop_loss_price DECIMAL(20, 8),
    take_profit_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8),
    realized_pnl DECIMAL(20, 8),
    fees DECIMAL(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    exit_reason VARCHAR(100),
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),
    -- Additional fields needed by repository queries
    leverage DECIMAL(10, 2) DEFAULT 1.0,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    pnl_percentage DECIMAL(10, 4),
    trailing_activated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.orders (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(100),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(100),
    client_order_id VARCHAR(100),
    type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    size DECIMAL(20, 8),
    price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL,
    filled DECIMAL(20, 8) DEFAULT 0,
    remaining DECIMAL(20, 8),
    fee DECIMAL(20, 8),
    fee_currency VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.trades (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20),
    quantity DECIMAL(20, 8),
    price DECIMAL(20, 8),
    executed_qty DECIMAL(20, 8),
    average_price DECIMAL(20, 8),
    order_id VARCHAR(100),
    client_order_id VARCHAR(100),
    status VARCHAR(20),
    fee DECIMAL(20, 8),
    fee_currency VARCHAR(10),
    executed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.risk_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    position_id VARCHAR(100),
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.risk_violations (
    id SERIAL PRIMARY KEY,
    violation_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    message TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.performance_metrics (
    id SERIAL PRIMARY KEY,
    period VARCHAR(20) NOT NULL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    total_pnl DECIMAL(20, 8),
    win_rate DECIMAL(5, 2),
    profit_factor DECIMAL(10, 2),
    sharpe_ratio DECIMAL(10, 2),
    max_drawdown DECIMAL(20, 8),
    avg_win DECIMAL(20, 8),
    avg_loss DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_positions_status ON monitoring.positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON monitoring.positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON monitoring.positions(opened_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON monitoring.orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_position ON monitoring.orders(position_id);
CREATE INDEX IF NOT EXISTS idx_signals_processed ON fas.scoring_history(is_processed);
CREATE INDEX IF NOT EXISTS idx_signals_created ON fas.scoring_history(created_at);

-- Permissions (adjust user as needed)
GRANT ALL ON SCHEMA fas TO current_user;
GRANT ALL ON SCHEMA monitoring TO current_user;
GRANT ALL ON ALL TABLES IN SCHEMA fas TO current_user;
GRANT ALL ON ALL TABLES IN SCHEMA monitoring TO current_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA fas TO current_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA monitoring TO current_user;-- Migration: Expand exit_reason field and add audit fields
-- Purpose: Store complete error messages and improve debugging

-- For PostgreSQL:
ALTER TABLE monitoring.positions
ALTER COLUMN exit_reason TYPE TEXT;

-- Add audit fields for better tracking
ALTER TABLE monitoring.positions
ADD COLUMN IF NOT EXISTS error_details JSONB,
ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMP;

-- Create index for error analysis
CREATE INDEX IF NOT EXISTS idx_positions_exit_reason
ON monitoring.positions(exit_reason)
WHERE exit_reason IS NOT NULL;

-- For SQLite (requires table recreation):
-- SQLite doesn't support ALTER COLUMN, so we need to recreate
/*
-- Step 1: Create new table with updated schema
CREATE TABLE positions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL,
    stop_loss_price REAL,
    take_profit_price REAL,
    unrealized_pnl REAL,
    realized_pnl REAL,
    fees REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    exit_reason TEXT,  -- Changed from VARCHAR(100) to TEXT
    error_details TEXT,  -- JSON string for SQLite
    retry_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMP,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    leverage REAL DEFAULT 1.0,
    stop_loss REAL,
    take_profit REAL,
    pnl REAL,
    pnl_percentage REAL,
    trailing_activated BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Step 2: Copy data
INSERT INTO positions_new SELECT
    id, signal_id, symbol, exchange, side, quantity, entry_price,
    current_price, stop_loss_price, take_profit_price, unrealized_pnl,
    realized_pnl, fees, status, exit_reason,
    NULL, 0, NULL,  -- New fields with defaults
    opened_at, closed_at, updated_at, leverage, stop_loss,
    take_profit, pnl, pnl_percentage, trailing_activated, created_at
FROM positions;

-- Step 3: Drop old table and rename
DROP TABLE positions;
ALTER TABLE positions_new RENAME TO positions;

-- Step 4: Recreate indexes
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_exit_reason ON positions(exit_reason)
WHERE exit_reason IS NOT NULL;
*/-- Migration: 003_cleanup_fas_signals.sql
-- Purpose: Change signal_id from INTEGER to VARCHAR(100) to support WebSocket message IDs
-- Date: 2025-10-14
-- Context: fas.signals table already removed, only need to fix column types

BEGIN;

-- ============================================================
-- PHASE 1: PRE-FLIGHT VALIDATION
-- ============================================================

DO $$
BEGIN
    RAISE NOTICE 'Starting migration 003_cleanup_fas_signals...';
    RAISE NOTICE 'Timestamp: %', NOW();
END $$;

-- Verify monitoring schema exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE EXCEPTION 'Schema monitoring does not exist!';
    END IF;
    RAISE NOTICE '✓ Schema monitoring exists';
END $$;

-- ============================================================
-- PHASE 2: BACKUP CURRENT DATA
-- ============================================================

-- Create temporary backup table for positions
CREATE TABLE IF NOT EXISTS monitoring.positions_signal_id_backup AS
SELECT id, signal_id
FROM monitoring.positions
WHERE signal_id IS NOT NULL;

-- Create temporary backup table for trades
CREATE TABLE IF NOT EXISTS monitoring.trades_signal_id_backup AS
SELECT id, signal_id
FROM monitoring.trades
WHERE signal_id IS NOT NULL;

DO $$
BEGIN
    RAISE NOTICE '✓ Backed up % positions with signal_id',
        (SELECT COUNT(*) FROM monitoring.positions_signal_id_backup);
    RAISE NOTICE '✓ Backed up % trades with signal_id',
        (SELECT COUNT(*) FROM monitoring.trades_signal_id_backup);
END $$;

-- ============================================================
-- PHASE 3: ALTER COLUMN TYPES
-- ============================================================

-- Change positions.signal_id: INTEGER → VARCHAR(100)
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE VARCHAR(100) USING signal_id::TEXT;

-- Change trades.signal_id: INTEGER → VARCHAR(100)
ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE VARCHAR(100) USING signal_id::TEXT;

DO $$
BEGIN
    RAISE NOTICE '✓ Changed monitoring.positions.signal_id to VARCHAR(100)';
    RAISE NOTICE '✓ Changed monitoring.trades.signal_id to VARCHAR(100)';
END $$;

-- ============================================================
-- PHASE 4: UPDATE COMMENTS
-- ============================================================

COMMENT ON COLUMN monitoring.positions.signal_id IS
'WebSocket signal message ID (NOT a foreign key to fas.signals)';

COMMENT ON COLUMN monitoring.trades.signal_id IS
'WebSocket signal message ID (NOT a foreign key to fas.signals)';

DO $$
BEGIN
    RAISE NOTICE '✓ Updated column comments';
END $$;

-- ============================================================
-- PHASE 5: VERIFY DATA INTEGRITY
-- ============================================================

DO $$
DECLARE
    pos_count_before INTEGER;
    pos_count_after INTEGER;
    trades_count_before INTEGER;
    trades_count_after INTEGER;
BEGIN
    -- Check positions data integrity
    SELECT COUNT(*) INTO pos_count_before FROM monitoring.positions_signal_id_backup;
    SELECT COUNT(*) INTO pos_count_after FROM monitoring.positions WHERE signal_id IS NOT NULL;

    IF pos_count_before != pos_count_after THEN
        RAISE EXCEPTION 'Data integrity check FAILED for positions: before=%, after=%',
            pos_count_before, pos_count_after;
    END IF;

    -- Check trades data integrity
    SELECT COUNT(*) INTO trades_count_before FROM monitoring.trades_signal_id_backup;
    SELECT COUNT(*) INTO trades_count_after FROM monitoring.trades WHERE signal_id IS NOT NULL;

    IF trades_count_before != trades_count_after THEN
        RAISE EXCEPTION 'Data integrity check FAILED for trades: before=%, after=%',
            trades_count_before, trades_count_after;
    END IF;

    RAISE NOTICE '✓ Data integrity verified: positions=%, trades=%',
        pos_count_after, trades_count_after;
END $$;

-- ============================================================
-- PHASE 6: CLEANUP BACKUP TABLES (optional - keep for safety)
-- ============================================================

-- Uncomment to drop backup tables after verification
-- DROP TABLE IF EXISTS monitoring.positions_signal_id_backup;
-- DROP TABLE IF EXISTS monitoring.trades_signal_id_backup;

-- ============================================================
-- MIGRATION COMPLETE
-- ============================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Migration 003_cleanup_fas_signals COMPLETED';
    RAISE NOTICE 'Timestamp: %', NOW();
    RAISE NOTICE '========================================';
END $$;

COMMIT;

-- ============================================================
-- ROLLBACK SCRIPT (if needed)
-- ============================================================
/*
BEGIN;

-- Restore original INTEGER type
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE INTEGER USING signal_id::INTEGER;

ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE INTEGER USING signal_id::INTEGER;

-- Verify rollback
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'monitoring'
AND table_name IN ('positions', 'trades')
AND column_name = 'signal_id';

COMMIT;
*/
-- =====================================================
-- Migration 004: Create EventLogger Tables
-- =====================================================
-- Date: 2025-10-14
-- Purpose: Enable comprehensive event audit trail
-- Dependencies: Schema 'monitoring' must exist
-- Safety: Creates new tables, does NOT modify existing tables
-- =====================================================

BEGIN;

-- Pre-checks
DO $$
BEGIN
    -- Verify monitoring schema exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE EXCEPTION 'Schema monitoring does not exist';
    END IF;

    -- Verify events table does NOT already exist
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'events') THEN
        RAISE NOTICE 'Table monitoring.events already exists, skipping creation';
    END IF;

    -- Verify old performance_metrics exists (safety check)
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'performance_metrics') THEN
        RAISE WARNING 'Original monitoring.performance_metrics table not found';
    END IF;
END $$;

-- =====================================================
-- TABLE 1: monitoring.events (CRITICAL)
-- =====================================================
-- Purpose: Comprehensive audit trail for all bot operations
-- Expected load: ~240 events/hour, ~5,760 events/day
-- Retention: Should be rotated/archived after 30-90 days

CREATE TABLE IF NOT EXISTS monitoring.events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    correlation_id VARCHAR(100),
    position_id INTEGER,  -- Soft FK to monitoring.positions.id
    order_id VARCHAR(100),
    symbol VARCHAR(50),
    exchange VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'INFO',
    error_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_events_type ON monitoring.events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON monitoring.events (correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_position ON monitoring.events (position_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON monitoring.events (created_at DESC);

-- Additional useful indexes
CREATE INDEX IF NOT EXISTS idx_events_symbol ON monitoring.events (symbol) WHERE symbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_exchange ON monitoring.events (exchange) WHERE exchange IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_severity ON monitoring.events (severity);

-- Partial index for errors only (faster error queries)
CREATE INDEX IF NOT EXISTS idx_events_errors ON monitoring.events (created_at DESC)
    WHERE severity IN ('ERROR', 'CRITICAL');

-- Comment
COMMENT ON TABLE monitoring.events IS 'Event audit trail for all critical bot operations. Stores 69 event types across 7 components.';
COMMENT ON COLUMN monitoring.events.event_type IS 'Type from EventType enum (e.g., position_created, stop_loss_placed, wave_detected)';
COMMENT ON COLUMN monitoring.events.event_data IS 'JSONB payload with event-specific data';
COMMENT ON COLUMN monitoring.events.correlation_id IS 'Groups related events in atomic operations';
COMMENT ON COLUMN monitoring.events.position_id IS 'Soft FK to monitoring.positions.id (no constraint)';
COMMENT ON COLUMN monitoring.events.severity IS 'INFO, WARNING, ERROR, or CRITICAL';

-- =====================================================
-- TABLE 2: monitoring.transaction_log (LOW PRIORITY)
-- =====================================================
-- Purpose: Database transaction performance tracking
-- Expected load: Very low (not used in production yet)
-- Status: Reserved for future use

CREATE TABLE IF NOT EXISTS monitoring.transaction_log (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) UNIQUE,
    operation VARCHAR(100),
    status VARCHAR(20),  -- success, failed, pending
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    affected_rows INTEGER,
    error_message TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tx_log_id ON monitoring.transaction_log (transaction_id);
CREATE INDEX IF NOT EXISTS idx_tx_log_status ON monitoring.transaction_log (status);
CREATE INDEX IF NOT EXISTS idx_tx_log_started ON monitoring.transaction_log (started_at DESC);

-- Comment
COMMENT ON TABLE monitoring.transaction_log IS 'Database transaction performance tracking. Currently unused in production.';

-- =====================================================
-- TABLE 3: monitoring.event_performance_metrics (LOW PRIORITY)
-- =====================================================
-- Purpose: Real-time EventLogger performance metrics
-- Expected load: Very low (not used in production yet)
-- Status: Reserved for future use
--
-- NOTE: Original name was 'performance_metrics' but that name is already
--       used by trading statistics table (database/init.sql:109-123).
--       This table has been renamed to 'event_performance_metrics' to
--       avoid naming conflict.

CREATE TABLE IF NOT EXISTS monitoring.event_performance_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    metric_value DECIMAL(20, 8),
    tags JSONB,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_event_metrics_name ON monitoring.event_performance_metrics (metric_name);
CREATE INDEX IF NOT EXISTS idx_event_metrics_time ON monitoring.event_performance_metrics (recorded_at DESC);

-- Comment
COMMENT ON TABLE monitoring.event_performance_metrics IS 'Real-time EventLogger performance metrics. Currently unused in production.';
COMMENT ON COLUMN monitoring.event_performance_metrics.tags IS 'JSONB for flexible metric dimensions (e.g., {"exchange": "bybit"})';

-- =====================================================
-- POST-MIGRATION VERIFICATION
-- =====================================================

DO $$
DECLARE
    events_count INTEGER;
    tx_log_count INTEGER;
    metrics_count INTEGER;
    old_perf_count INTEGER;
BEGIN
    -- Verify tables created
    SELECT COUNT(*) INTO events_count
    FROM information_schema.tables
    WHERE table_schema = 'monitoring' AND table_name = 'events';

    SELECT COUNT(*) INTO tx_log_count
    FROM information_schema.tables
    WHERE table_schema = 'monitoring' AND table_name = 'transaction_log';

    SELECT COUNT(*) INTO metrics_count
    FROM information_schema.tables
    WHERE table_schema = 'monitoring' AND table_name = 'event_performance_metrics';

    IF events_count = 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: monitoring.events was not created';
    END IF;

    IF tx_log_count = 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: monitoring.transaction_log was not created';
    END IF;

    IF metrics_count = 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: monitoring.event_performance_metrics was not created';
    END IF;

    -- Verify old performance_metrics still has data
    SELECT COUNT(*) INTO old_perf_count
    FROM monitoring.performance_metrics;

    IF old_perf_count < 32 THEN
        RAISE WARNING 'ATTENTION: monitoring.performance_metrics has fewer records than expected (found %, expected >= 32)', old_perf_count;
    END IF;

    -- Success message
    RAISE NOTICE '✅ Migration 004 completed successfully!';
    RAISE NOTICE '   - monitoring.events: CREATED';
    RAISE NOTICE '   - monitoring.transaction_log: CREATED';
    RAISE NOTICE '   - monitoring.event_performance_metrics: CREATED';
    RAISE NOTICE '   - monitoring.performance_metrics: INTACT (% records)', old_perf_count;
END $$;

COMMIT;

-- =====================================================
-- ROLLBACK INSTRUCTIONS
-- =====================================================
-- If you need to rollback this migration, run:
--
-- BEGIN;
-- DROP TABLE IF EXISTS monitoring.events CASCADE;
-- DROP TABLE IF EXISTS monitoring.transaction_log CASCADE;
-- DROP TABLE IF EXISTS monitoring.event_performance_metrics CASCADE;
-- COMMIT;
--
-- WARNING: This will permanently delete all event audit data!
-- =====================================================
-- =====================================================
-- Migration 005: Add updated_at Auto-Update Triggers
-- =====================================================
-- Date: 2025-10-14
-- Purpose: Automatically update updated_at column on UPDATE
-- Dependencies: Tables positions, trades, protection_events must exist
-- Safety: Only adds triggers, does NOT modify existing data
-- Impact: Minimal - triggers add ~0.1ms overhead per UPDATE
-- =====================================================

BEGIN;

-- =====================================================
-- PRE-CHECKS
-- =====================================================

DO $$
BEGIN
    -- Verify monitoring schema exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE EXCEPTION 'Schema monitoring does not exist';
    END IF;

    -- Verify target tables exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'positions') THEN
        RAISE EXCEPTION 'Table monitoring.positions does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'trades') THEN
        RAISE EXCEPTION 'Table monitoring.trades does not exist';
    END IF;

    -- Note: protection_events is optional, may not exist in all environments
    -- IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'protection_events') THEN
    --     RAISE WARNING 'Table monitoring.protection_events does not exist, skipping';
    -- END IF;

    -- Verify updated_at columns exist (or can be added)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = 'positions' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'Column monitoring.positions.updated_at does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = 'trades' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'Column monitoring.trades.updated_at does not exist';
    END IF;

    RAISE NOTICE 'Pre-checks passed';
END $$;

-- =====================================================
-- STEP 1: Ensure trigger function exists
-- =====================================================
-- Note: Function may already exist in public schema
-- Using CREATE OR REPLACE to ensure it's available

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION public.update_updated_at_column() IS
    'Trigger function to automatically set updated_at = NOW() on UPDATE. Used by multiple triggers in monitoring schema.';

-- =====================================================
-- STEP 2: Add updated_at column to protection_events (if table exists)
-- =====================================================
-- This table needs updated_at column first

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'protection_events') THEN
        ALTER TABLE monitoring.protection_events
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

        EXECUTE 'COMMENT ON COLUMN monitoring.protection_events.updated_at IS ''Auto-updated timestamp of last row modification''';
        RAISE NOTICE 'Added updated_at column to protection_events';
    ELSE
        RAISE NOTICE 'Table protection_events does not exist, skipping';
    END IF;
END $$;

-- =====================================================
-- STEP 3: Create triggers for each table
-- =====================================================

-- Trigger for positions table
DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON monitoring.positions
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_positions_updated_at ON monitoring.positions IS
    'Auto-updates updated_at column on any UPDATE';

-- Trigger for trades table
DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;

CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON monitoring.trades
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_trades_updated_at ON monitoring.trades IS
    'Auto-updates updated_at column on any UPDATE';

-- Trigger for protection_events table (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'protection_events') THEN
        DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;

        CREATE TRIGGER update_protection_events_updated_at
            BEFORE UPDATE ON monitoring.protection_events
            FOR EACH ROW
            EXECUTE FUNCTION public.update_updated_at_column();

        EXECUTE 'COMMENT ON TRIGGER update_protection_events_updated_at ON monitoring.protection_events IS ''Auto-updates updated_at column on any UPDATE''';
        RAISE NOTICE 'Created trigger for protection_events';
    ELSE
        RAISE NOTICE 'Table protection_events does not exist, skipping trigger creation';
    END IF;
END $$;

-- =====================================================
-- POST-MIGRATION VERIFICATION
-- =====================================================

DO $$
DECLARE
    trigger_count INTEGER;
    has_protection_events BOOLEAN;
    expected_count INTEGER;
BEGIN
    -- Check if protection_events table exists
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'protection_events'
    ) INTO has_protection_events;

    -- Expected trigger count: 2 (positions, trades) + 1 (protection_events if exists)
    expected_count := 2;
    IF has_protection_events THEN
        expected_count := 3;
    END IF;

    -- Count created triggers
    SELECT COUNT(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_schema = 'monitoring'
    AND trigger_name IN (
        'update_positions_updated_at',
        'update_trades_updated_at',
        'update_protection_events_updated_at'
    );

    IF trigger_count != expected_count THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Expected % triggers, found %', expected_count, trigger_count;
    END IF;

    -- Verify function exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.routines
        WHERE routine_schema = 'public'
        AND routine_name = 'update_updated_at_column'
    ) THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Trigger function not created';
    END IF;

    -- Success message
    RAISE NOTICE '✅ Migration 005 completed successfully!';
    RAISE NOTICE '   - Trigger function: public.update_updated_at_column()';
    RAISE NOTICE '   - Triggers created: %', trigger_count;
    RAISE NOTICE '     * monitoring.positions';
    RAISE NOTICE '     * monitoring.trades';
    IF has_protection_events THEN
        RAISE NOTICE '     * monitoring.protection_events';
        RAISE NOTICE '   - Column added: protection_events.updated_at';
    END IF;
END $$;

COMMIT;

-- =====================================================
-- ROLLBACK INSTRUCTIONS
-- =====================================================
-- If you need to rollback this migration, run:
--
-- BEGIN;
-- DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;
-- DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;
-- DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;
-- DROP FUNCTION IF EXISTS public.update_updated_at_column();
-- ALTER TABLE monitoring.protection_events DROP COLUMN IF EXISTS updated_at;
-- COMMIT;
--
-- WARNING: This will stop automatic updated_at updates!
-- =====================================================
-- Migration 006: Create trailing_stop_state table
-- Purpose: Persist Trailing Stop state across bot restarts
-- Created: 2025-10-15

CREATE TABLE IF NOT EXISTS monitoring.trailing_stop_state (
    -- Primary key
    id BIGSERIAL PRIMARY KEY,

    -- Position reference
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    position_id BIGINT REFERENCES monitoring.positions(id) ON DELETE CASCADE,

    -- State tracking
    state VARCHAR(20) NOT NULL DEFAULT 'inactive',  -- 'inactive', 'waiting', 'active', 'triggered'
    is_activated BOOLEAN NOT NULL DEFAULT FALSE,

    -- Price tracking (CRITICAL for SL calculation)
    highest_price DECIMAL(20, 8),
    lowest_price DECIMAL(20, 8),
    current_stop_price DECIMAL(20, 8),

    -- Order tracking
    stop_order_id VARCHAR(100),

    -- Configuration (at time of creation)
    activation_price DECIMAL(20, 8),
    activation_percent DECIMAL(10, 4),
    callback_percent DECIMAL(10, 4),

    -- Entry tracking
    entry_price DECIMAL(20, 8) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'long' or 'short'
    quantity DECIMAL(20, 8) NOT NULL,

    -- Statistics
    update_count INTEGER DEFAULT 0,
    highest_profit_percent DECIMAL(10, 4) DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMP WITH TIME ZONE,
    last_update_time TIMESTAMP WITH TIME ZONE,
    last_sl_update_time TIMESTAMP WITH TIME ZONE,
    last_updated_sl_price DECIMAL(20, 8),

    -- Metadata
    metadata JSONB,

    -- Constraints
    CONSTRAINT unique_ts_per_symbol_exchange UNIQUE (symbol, exchange)
);

-- Indexes for performance
CREATE INDEX idx_ts_state_symbol ON monitoring.trailing_stop_state(symbol);
CREATE INDEX idx_ts_state_exchange ON monitoring.trailing_stop_state(exchange);
CREATE INDEX idx_ts_state_position_id ON monitoring.trailing_stop_state(position_id);
CREATE INDEX idx_ts_state_activated ON monitoring.trailing_stop_state(is_activated);
CREATE INDEX idx_ts_state_created_at ON monitoring.trailing_stop_state(created_at DESC);

-- Comments
COMMENT ON TABLE monitoring.trailing_stop_state IS 'Persistent storage for Trailing Stop state across bot restarts';
COMMENT ON COLUMN monitoring.trailing_stop_state.highest_price IS 'Highest price reached (for long positions) - CRITICAL for SL calculation';
COMMENT ON COLUMN monitoring.trailing_stop_state.lowest_price IS 'Lowest price reached (for short positions) - CRITICAL for SL calculation';
COMMENT ON COLUMN monitoring.trailing_stop_state.current_stop_price IS 'Current calculated stop loss price';
COMMENT ON COLUMN monitoring.trailing_stop_state.last_sl_update_time IS 'Last successful SL update on exchange (for rate limiting)';
COMMENT ON COLUMN monitoring.trailing_stop_state.last_updated_sl_price IS 'Last successfully updated SL price on exchange (for rate limiting)';
