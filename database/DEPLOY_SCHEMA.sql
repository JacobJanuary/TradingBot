-- ============================================================================
-- TRADING BOT - COMPLETE DATABASE SCHEMA (FROM PRODUCTION)
-- ============================================================================
-- Version: 3.0
-- Date: 2025-10-17
-- Description: Full database schema extracted from production database
-- Includes: 1 schema, 10 tables, 37 indexes, 2 triggers, 1 foreign key
-- ============================================================================

-- ============================================================================
-- SECTION 1: SCHEMA
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS monitoring;

COMMENT ON SCHEMA monitoring IS 'Trading bot monitoring, positions, and state management';

-- ============================================================================
-- SECTION 2: TABLES
-- ============================================================================

-- 2.1 POSITIONS TABLE
CREATE TABLE IF NOT EXISTS monitoring.positions (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    entry_price NUMERIC(20, 8) NOT NULL,
    current_price NUMERIC(20, 8),
    stop_loss_price NUMERIC(20, 8),
    take_profit_price NUMERIC(20, 8),
    unrealized_pnl NUMERIC(20, 8),
    realized_pnl NUMERIC(20, 8),
    fees NUMERIC(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    exit_reason TEXT,
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Additional fields for compatibility
    leverage NUMERIC(10, 2) DEFAULT 1.0,
    stop_loss NUMERIC(20, 8),
    take_profit NUMERIC(20, 8),
    pnl NUMERIC(20, 8),
    pnl_percentage NUMERIC(10, 4),
    trailing_activated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),

    -- Error tracking and retry logic
    error_details JSONB,
    retry_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMP,

    -- Stop loss and trailing stop flags
    has_trailing_stop BOOLEAN DEFAULT FALSE,
    has_stop_loss BOOLEAN DEFAULT FALSE,

    -- Exchange order tracking
    exchange_order_id VARCHAR(100)
);

-- 2.2 ORDERS TABLE
CREATE TABLE IF NOT EXISTS monitoring.orders (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(100),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(100),
    client_order_id VARCHAR(100),
    type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    size NUMERIC(20, 8),
    price NUMERIC(20, 8),
    status VARCHAR(20) NOT NULL,
    filled NUMERIC(20, 8) DEFAULT 0,
    remaining NUMERIC(20, 8),
    fee NUMERIC(20, 8),
    fee_currency VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2.3 TRADES TABLE
CREATE TABLE IF NOT EXISTS monitoring.trades (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20),
    quantity NUMERIC(20, 8),
    price NUMERIC(20, 8),
    executed_qty NUMERIC(20, 8),
    average_price NUMERIC(20, 8),
    order_id VARCHAR(100),
    client_order_id VARCHAR(100),
    status VARCHAR(20),
    fee NUMERIC(20, 8),
    fee_currency VARCHAR(10),
    executed_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2.4 EVENTS TABLE
CREATE TABLE IF NOT EXISTS monitoring.events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    correlation_id VARCHAR(100),
    position_id INTEGER,
    order_id VARCHAR(100),
    symbol VARCHAR(50),
    exchange VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'INFO',
    error_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2.5 TRAILING STOP STATE TABLE
CREATE TABLE IF NOT EXISTS monitoring.trailing_stop_state (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    position_id BIGINT,
    state VARCHAR(20) NOT NULL DEFAULT 'inactive',
    is_activated BOOLEAN NOT NULL DEFAULT FALSE,

    -- Price tracking (CRITICAL for trailing stop calculation)
    highest_price NUMERIC(20, 8),
    lowest_price NUMERIC(20, 8),
    current_stop_price NUMERIC(20, 8),
    stop_order_id VARCHAR(100),
    activation_price NUMERIC(20, 8),

    -- Configuration
    activation_percent NUMERIC(10, 4),
    callback_percent NUMERIC(10, 4),
    entry_price NUMERIC(20, 8) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,

    -- Update tracking (for rate limiting)
    update_count INTEGER DEFAULT 0,
    highest_profit_percent NUMERIC(10, 4) DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    last_update_time TIMESTAMPTZ,
    last_sl_update_time TIMESTAMPTZ,
    last_updated_sl_price NUMERIC(20, 8),

    -- Additional data
    metadata JSONB,

    -- Constraints
    CONSTRAINT unique_ts_per_symbol_exchange UNIQUE (symbol, exchange)
);

-- 2.6 PERFORMANCE METRICS TABLE
CREATE TABLE IF NOT EXISTS monitoring.performance_metrics (
    id SERIAL PRIMARY KEY,
    period VARCHAR(20) NOT NULL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    total_pnl NUMERIC(20, 8),
    win_rate NUMERIC(5, 2),
    profit_factor NUMERIC(10, 2),
    sharpe_ratio NUMERIC(10, 2),
    max_drawdown NUMERIC(20, 8),
    avg_win NUMERIC(20, 8),
    avg_loss NUMERIC(20, 8),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2.7 EVENT PERFORMANCE METRICS TABLE
CREATE TABLE IF NOT EXISTS monitoring.event_performance_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    metric_value NUMERIC(20, 8),
    tags JSONB,
    recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2.8 RISK EVENTS TABLE
CREATE TABLE IF NOT EXISTS monitoring.risk_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    position_id VARCHAR(100),
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2.9 RISK VIOLATIONS TABLE
CREATE TABLE IF NOT EXISTS monitoring.risk_violations (
    id SERIAL PRIMARY KEY,
    violation_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    message TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- 2.10 TRANSACTION LOG TABLE
CREATE TABLE IF NOT EXISTS monitoring.transaction_log (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) UNIQUE,
    operation VARCHAR(100),
    status VARCHAR(20),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    affected_rows INTEGER,
    error_message TEXT
);

-- ============================================================================
-- SECTION 3: INDEXES
-- ============================================================================

-- Positions indexes
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON monitoring.positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON monitoring.positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON monitoring.positions(opened_at);
CREATE INDEX IF NOT EXISTS idx_positions_exchange_order ON monitoring.positions(exchange_order_id);
CREATE INDEX IF NOT EXISTS idx_positions_exit_reason ON monitoring.positions(exit_reason) WHERE exit_reason IS NOT NULL;

-- Orders indexes
CREATE INDEX IF NOT EXISTS idx_orders_position ON monitoring.orders(position_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON monitoring.orders(status);

-- Trades indexes (primary key only)

-- Events indexes
CREATE INDEX IF NOT EXISTS idx_events_type ON monitoring.events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_position ON monitoring.events(position_id);
CREATE INDEX IF NOT EXISTS idx_events_symbol ON monitoring.events(symbol) WHERE symbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_exchange ON monitoring.events(exchange) WHERE exchange IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_severity ON monitoring.events(severity);
CREATE INDEX IF NOT EXISTS idx_events_created ON monitoring.events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON monitoring.events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_errors ON monitoring.events(created_at DESC) WHERE severity IN ('ERROR', 'CRITICAL');

-- Trailing stop state indexes
CREATE INDEX IF NOT EXISTS idx_ts_state_symbol ON monitoring.trailing_stop_state(symbol);
CREATE INDEX IF NOT EXISTS idx_ts_state_exchange ON monitoring.trailing_stop_state(exchange);
CREATE INDEX IF NOT EXISTS idx_ts_state_position_id ON monitoring.trailing_stop_state(position_id);
CREATE INDEX IF NOT EXISTS idx_ts_state_activated ON monitoring.trailing_stop_state(is_activated);
CREATE INDEX IF NOT EXISTS idx_ts_state_created_at ON monitoring.trailing_stop_state(created_at DESC);

-- Performance metrics indexes (primary key only)

-- Event performance metrics indexes
CREATE INDEX IF NOT EXISTS idx_event_metrics_name ON monitoring.event_performance_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_event_metrics_time ON monitoring.event_performance_metrics(recorded_at DESC);

-- Risk events indexes (primary key only)

-- Risk violations indexes (primary key only)

-- Transaction log indexes
CREATE INDEX IF NOT EXISTS idx_tx_log_id ON monitoring.transaction_log(transaction_id);
CREATE INDEX IF NOT EXISTS idx_tx_log_status ON monitoring.transaction_log(status);
CREATE INDEX IF NOT EXISTS idx_tx_log_started ON monitoring.transaction_log(started_at DESC);

-- ============================================================================
-- SECTION 4: FOREIGN KEYS
-- ============================================================================

-- Trailing stop state -> positions
ALTER TABLE monitoring.trailing_stop_state
    DROP CONSTRAINT IF EXISTS trailing_stop_state_position_id_fkey;

ALTER TABLE monitoring.trailing_stop_state
    ADD CONSTRAINT trailing_stop_state_position_id_fkey
    FOREIGN KEY (position_id)
    REFERENCES monitoring.positions(id)
    ON DELETE CASCADE;

-- ============================================================================
-- SECTION 5: TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Positions trigger
DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;
CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON monitoring.positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trades trigger
DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;
CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON monitoring.trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON FUNCTION update_updated_at_column() IS 'Automatically updates updated_at timestamp on row modification';

-- ============================================================================
-- SECTION 6: TABLE COMMENTS
-- ============================================================================

COMMENT ON TABLE monitoring.positions IS 'Trading positions with full lifecycle tracking';
COMMENT ON TABLE monitoring.orders IS 'All orders (market, limit, stop-loss, take-profit)';
COMMENT ON TABLE monitoring.trades IS 'Individual trade executions (fills)';
COMMENT ON TABLE monitoring.events IS 'Event log for all significant bot activities';
COMMENT ON TABLE monitoring.trailing_stop_state IS 'Persistent trailing stop state across bot restarts';
COMMENT ON TABLE monitoring.performance_metrics IS 'Trading performance metrics by period';
COMMENT ON TABLE monitoring.event_performance_metrics IS 'Event-based performance tracking';
COMMENT ON TABLE monitoring.risk_events IS 'Risk management events';
COMMENT ON TABLE monitoring.risk_violations IS 'Risk rule violations';
COMMENT ON TABLE monitoring.transaction_log IS 'Database transaction audit log';

-- ============================================================================
-- SECTION 7: PERFORMANCE & MAINTENANCE
-- ============================================================================

-- Vacuum and analyze for optimal performance
VACUUM ANALYZE monitoring.positions;
VACUUM ANALYZE monitoring.orders;
VACUUM ANALYZE monitoring.trades;
VACUUM ANALYZE monitoring.events;
VACUUM ANALYZE monitoring.trailing_stop_state;
VACUUM ANALYZE monitoring.performance_metrics;
VACUUM ANALYZE monitoring.event_performance_metrics;
VACUUM ANALYZE monitoring.risk_events;
VACUUM ANALYZE monitoring.risk_violations;
VACUUM ANALYZE monitoring.transaction_log;

-- ============================================================================
-- SECTION 8: DEPLOYMENT VERIFICATION
-- ============================================================================

-- Verify deployment
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'monitoring'
ORDER BY schemaname, tablename;

-- Display summary
DO $$
DECLARE
    table_count INTEGER;
    index_count INTEGER;
    trigger_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM pg_tables
    WHERE schemaname = 'monitoring';

    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE schemaname = 'monitoring';

    SELECT COUNT(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_schema = 'monitoring';

    RAISE NOTICE '========================================';
    RAISE NOTICE 'DEPLOYMENT SUMMARY';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Schemas created: 1 (monitoring)';
    RAISE NOTICE 'Tables created: %', table_count;
    RAISE NOTICE 'Indexes created: %', index_count;
    RAISE NOTICE 'Triggers created: %', trigger_count;
    RAISE NOTICE 'Foreign keys: 1 (trailing_stop_state -> positions)';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Database ready for trading bot!';
    RAISE NOTICE '========================================';
END $$;
