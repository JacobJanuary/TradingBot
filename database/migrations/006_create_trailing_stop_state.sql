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
