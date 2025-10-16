-- ============================================================================
-- TRADING BOT - COMPLETE DATABASE SCHEMA
-- ============================================================================
-- Version: 2.0
-- Date: 2025-10-17
-- Description: Full database schema for deploying on new server
-- Includes: schemas, tables, indexes, triggers, constraints, comments
-- Note: FAS schema removed (not used in current system)
-- ============================================================================

-- ============================================================================
-- SECTION 1: SCHEMA
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS monitoring;

COMMENT ON SCHEMA monitoring IS 'Trading bot monitoring, positions, and state management';

-- ============================================================================
-- SECTION 2: POSITIONS TABLE
-- ============================================================================

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
    
    -- Additional fields for compatibility
    leverage DECIMAL(10, 2) DEFAULT 1.0,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    pnl_percentage DECIMAL(10, 4),
    trailing_activated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Exchange order tracking
    exchange_order_id VARCHAR(100),
    exchange_stop_order_id VARCHAR(100),
    exchange_tp_order_id VARCHAR(100)
);

-- Indexes for positions
CREATE INDEX idx_positions_symbol ON monitoring.positions(symbol);
CREATE INDEX idx_positions_exchange ON monitoring.positions(exchange);
CREATE INDEX idx_positions_status ON monitoring.positions(status);
CREATE INDEX idx_positions_signal_id ON monitoring.positions(signal_id);
CREATE INDEX idx_positions_opened_at ON monitoring.positions(opened_at DESC);
CREATE INDEX idx_positions_closed_at ON monitoring.positions(closed_at DESC);
CREATE INDEX idx_positions_symbol_status ON monitoring.positions(symbol, status);
CREATE INDEX idx_positions_exchange_order_id ON monitoring.positions(exchange_order_id);

COMMENT ON TABLE monitoring.positions IS 'Trading positions with full lifecycle tracking';
COMMENT ON COLUMN monitoring.positions.exchange_order_id IS 'Exchange order ID for the entry order';
COMMENT ON COLUMN monitoring.positions.exchange_stop_order_id IS 'Exchange order ID for stop-loss order';
COMMENT ON COLUMN monitoring.positions.exchange_tp_order_id IS 'Exchange order ID for take-profit order';

-- ============================================================================
-- SECTION 3: ORDERS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS monitoring.orders (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES monitoring.positions(id),
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL,
    exchange_order_id VARCHAR(100),
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    average_price DECIMAL(20, 8),
    fee DECIMAL(20, 8) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    filled_at TIMESTAMP
);

CREATE INDEX idx_orders_position_id ON monitoring.orders(position_id);
CREATE INDEX idx_orders_symbol ON monitoring.orders(symbol);
CREATE INDEX idx_orders_exchange_order_id ON monitoring.orders(exchange_order_id);
CREATE INDEX idx_orders_status ON monitoring.orders(status);
CREATE INDEX idx_orders_created_at ON monitoring.orders(created_at DESC);

COMMENT ON TABLE monitoring.orders IS 'All orders (market, limit, stop-loss, take-profit)';

-- ============================================================================
-- SECTION 4: TRADES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS monitoring.trades (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES monitoring.positions(id),
    order_id INTEGER REFERENCES monitoring.orders(id),
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(10),
    exchange_trade_id VARCHAR(100),
    executed_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_trades_position_id ON monitoring.trades(position_id);
CREATE INDEX idx_trades_order_id ON monitoring.trades(order_id);
CREATE INDEX idx_trades_symbol ON monitoring.trades(symbol);
CREATE INDEX idx_trades_exchange_trade_id ON monitoring.trades(exchange_trade_id);
CREATE INDEX idx_trades_executed_at ON monitoring.trades(executed_at DESC);

COMMENT ON TABLE monitoring.trades IS 'Individual trade executions (fills)';

-- ============================================================================
-- SECTION 5: EVENTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS monitoring.events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    position_id INTEGER,
    symbol VARCHAR(20),
    exchange VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'INFO',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_events_event_type ON monitoring.events(event_type);
CREATE INDEX idx_events_position_id ON monitoring.events(position_id);
CREATE INDEX idx_events_symbol ON monitoring.events(symbol);
CREATE INDEX idx_events_exchange ON monitoring.events(exchange);
CREATE INDEX idx_events_severity ON monitoring.events(severity);
CREATE INDEX idx_events_created_at ON monitoring.events(created_at DESC);
CREATE INDEX idx_events_type_created ON monitoring.events(event_type, created_at DESC);

COMMENT ON TABLE monitoring.events IS 'Event log for all significant bot activities';

-- ============================================================================
-- SECTION 6: TRAILING STOP STATE TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS monitoring.trailing_stop_state (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES monitoring.positions(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    
    -- Price tracking (CRITICAL for trailing stop calculation)
    entry_price DECIMAL(20, 8) NOT NULL,
    highest_price DECIMAL(20, 8) NOT NULL,
    lowest_price DECIMAL(20, 8) NOT NULL,
    current_stop_price DECIMAL(20, 8) NOT NULL,
    
    -- Configuration
    trailing_stop_percent DECIMAL(10, 4) NOT NULL,
    activation_percent DECIMAL(10, 4) NOT NULL,
    
    -- State management
    is_activated BOOLEAN DEFAULT FALSE,
    activation_price DECIMAL(20, 8),
    
    -- Update tracking (for rate limiting)
    update_count INTEGER DEFAULT 0,
    last_sl_update_time TIMESTAMP,
    last_updated_sl_price DECIMAL(20, 8),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Additional data
    metadata JSONB,
    
    -- Constraints
    CONSTRAINT unique_ts_per_symbol_exchange UNIQUE (symbol, exchange)
);

-- Indexes for trailing stop state
CREATE INDEX idx_ts_state_symbol ON monitoring.trailing_stop_state(symbol);
CREATE INDEX idx_ts_state_exchange ON monitoring.trailing_stop_state(exchange);
CREATE INDEX idx_ts_state_position_id ON monitoring.trailing_stop_state(position_id);
CREATE INDEX idx_ts_state_activated ON monitoring.trailing_stop_state(is_activated);
CREATE INDEX idx_ts_state_created_at ON monitoring.trailing_stop_state(created_at DESC);

COMMENT ON TABLE monitoring.trailing_stop_state IS 'Persistent trailing stop state across bot restarts';
COMMENT ON COLUMN monitoring.trailing_stop_state.highest_price IS 'Highest price reached (long) - CRITICAL for SL calculation';
COMMENT ON COLUMN monitoring.trailing_stop_state.lowest_price IS 'Lowest price reached (short) - CRITICAL for SL calculation';
COMMENT ON COLUMN monitoring.trailing_stop_state.current_stop_price IS 'Current calculated stop loss price';
COMMENT ON COLUMN monitoring.trailing_stop_state.last_sl_update_time IS 'Last successful SL update on exchange (rate limiting)';
COMMENT ON COLUMN monitoring.trailing_stop_state.last_updated_sl_price IS 'Last updated SL price on exchange (rate limiting)';

-- ============================================================================
-- SECTION 7: TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_positions_updated_at
    BEFORE UPDATE ON monitoring.positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_orders_updated_at
    BEFORE UPDATE ON monitoring.orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_ts_state_updated_at
    BEFORE UPDATE ON monitoring.trailing_stop_state
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON FUNCTION update_updated_at_column() IS 'Automatically updates updated_at timestamp on row modification';

-- ============================================================================
-- SECTION 8: PERFORMANCE & MAINTENANCE
-- ============================================================================

-- Vacuum and analyze for optimal performance
VACUUM ANALYZE monitoring.positions;
VACUUM ANALYZE monitoring.orders;
VACUUM ANALYZE monitoring.trades;
VACUUM ANALYZE monitoring.events;
VACUUM ANALYZE monitoring.trailing_stop_state;

-- ============================================================================
-- SECTION 9: PERMISSIONS (OPTIONAL - ADJUST AS NEEDED)
-- ============================================================================

-- Example: Grant permissions to trading bot user
-- GRANT USAGE ON SCHEMA monitoring TO trading_bot_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA monitoring TO trading_bot_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA monitoring TO trading_bot_user;

-- ============================================================================
-- DEPLOYMENT COMPLETE
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
BEGIN
    SELECT COUNT(*) INTO table_count 
    FROM pg_tables 
    WHERE schemaname = 'monitoring';
    
    SELECT COUNT(*) INTO index_count 
    FROM pg_indexes 
    WHERE schemaname = 'monitoring';
    
    RAISE NOTICE '========================================';
    RAISE NOTICE 'DEPLOYMENT SUMMARY';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Schemas created: 1 (monitoring)';
    RAISE NOTICE 'Tables created: %', table_count;
    RAISE NOTICE 'Indexes created: %', index_count;
    RAISE NOTICE 'Triggers created: 3 (auto-update timestamps)';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Database ready for trading bot!';
    RAISE NOTICE '========================================';
END $$;
