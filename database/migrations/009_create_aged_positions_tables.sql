-- Migration 009: Create aged positions tracking tables
-- Purpose: Track lifecycle of aged positions with WebSocket-based monitoring
-- Created: 2025-10-23
-- Author: AI Assistant

-- =====================================================
-- MAIN TABLE: aged_positions
-- =====================================================

CREATE TABLE IF NOT EXISTS monitoring.aged_positions (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Position reference
    position_id BIGINT NOT NULL REFERENCES monitoring.positions(id) ON DELETE CASCADE,

    -- Position snapshot at detection time
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'long', 'short', 'buy', 'sell'
    entry_price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,

    -- Time tracking
    position_opened_at TIMESTAMP WITH TIME ZONE NOT NULL,  -- When position was originally opened
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL,         -- When marked as aged
    grace_started_at TIMESTAMP WITH TIME ZONE,             -- When grace period started
    progressive_started_at TIMESTAMP WITH TIME ZONE,       -- When progressive liquidation started
    closed_at TIMESTAMP WITH TIME ZONE,                    -- When successfully closed

    -- State management
    status VARCHAR(30) NOT NULL DEFAULT 'detected',
    -- Possible values:
    -- 'detected' - Just identified as aged
    -- 'grace_pending' - Waiting to enter grace period
    -- 'grace_active' - In grace period, trying breakeven
    -- 'progressive_active' - In progressive liquidation
    -- 'closed' - Successfully closed
    -- 'error' - Error during processing
    -- 'skipped' - Skipped (e.g., trailing stop active)

    -- Price targets
    target_price DECIMAL(20, 8),                          -- Current target price
    breakeven_price DECIMAL(20, 8),                       -- Calculated breakeven (entry + commission)
    current_loss_tolerance_percent DECIMAL(5, 2) DEFAULT 0,  -- Current acceptable loss %

    -- Monitoring parameters
    last_price_check TIMESTAMP WITH TIME ZONE,            -- Last time price was checked
    last_checked_price DECIMAL(20, 8),                    -- Last checked market price

    -- Attempt tracking
    close_attempts INTEGER DEFAULT 0,                     -- Number of close attempts
    last_close_attempt TIMESTAMP WITH TIME ZONE,          -- Last close attempt time
    last_error_message TEXT,                              -- Last error if any

    -- Phase metrics
    hours_aged DECIMAL(10, 2),                           -- Total hours since MAX_POSITION_AGE
    hours_in_grace DECIMAL(10, 2) DEFAULT 0,             -- Hours spent in grace period
    hours_in_progressive DECIMAL(10, 2) DEFAULT 0,       -- Hours in progressive liquidation

    -- Close results
    close_price DECIMAL(20, 8),                          -- Actual close price
    close_order_id VARCHAR(255),                         -- Exchange order ID
    actual_pnl DECIMAL(20, 8),                          -- Actual PnL amount
    actual_pnl_percent DECIMAL(10, 4),                   -- Actual PnL percentage
    close_reason VARCHAR(50),                            -- Reason for close
    -- Possible values:
    -- 'profitable' - Closed in profit
    -- 'breakeven' - Closed at breakeven
    -- 'loss_acceptable' - Closed with acceptable loss
    -- 'max_loss' - Closed at maximum loss
    -- 'emergency' - Emergency market close
    -- 'manual' - Manual intervention

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Configuration snapshot (at detection time)
    config JSONB,  -- Store configuration like grace_period, loss_step, etc.

    -- Constraints
    CONSTRAINT aged_positions_position_id_unique UNIQUE (position_id),
    CONSTRAINT aged_positions_status_check CHECK (
        status IN ('detected', 'grace_pending', 'grace_active',
                  'progressive_active', 'closed', 'error', 'skipped')
    )
);

-- Indexes for performance
CREATE INDEX idx_aged_positions_status ON monitoring.aged_positions(status);
CREATE INDEX idx_aged_positions_symbol ON monitoring.aged_positions(symbol);
CREATE INDEX idx_aged_positions_exchange ON monitoring.aged_positions(exchange);
CREATE INDEX idx_aged_positions_detected_at ON monitoring.aged_positions(detected_at DESC);
CREATE INDEX idx_aged_positions_closed_at ON monitoring.aged_positions(closed_at DESC);
CREATE INDEX idx_aged_positions_status_symbol ON monitoring.aged_positions(status, symbol);

-- Partial indexes for active positions
CREATE INDEX idx_aged_positions_active ON monitoring.aged_positions(symbol, exchange)
    WHERE status NOT IN ('closed', 'error', 'skipped');

-- =====================================================
-- HISTORY TABLE: aged_positions_history
-- =====================================================

CREATE TABLE IF NOT EXISTS monitoring.aged_positions_history (
    -- Primary key
    id BIGSERIAL PRIMARY KEY,

    -- Reference to main table
    aged_position_id UUID NOT NULL REFERENCES monitoring.aged_positions(id) ON DELETE CASCADE,

    -- State transition
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,

    -- Snapshot at transition time
    current_market_price DECIMAL(20, 8),
    target_price DECIMAL(20, 8),
    loss_tolerance_percent DECIMAL(5, 2),
    pnl_percent DECIMAL(10, 4),

    -- Transition details
    transition_reason VARCHAR(255),
    transition_metadata JSONB,

    -- Timing
    transitioned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    hours_in_previous_state DECIMAL(10, 2)
);

-- Indexes
CREATE INDEX idx_aged_history_aged_position_id ON monitoring.aged_positions_history(aged_position_id);
CREATE INDEX idx_aged_history_transitioned_at ON monitoring.aged_positions_history(transitioned_at DESC);

-- =====================================================
-- MONITORING TABLE: aged_positions_monitoring
-- =====================================================
-- Tracks real-time monitoring activities

CREATE TABLE IF NOT EXISTS monitoring.aged_positions_monitoring (
    -- Primary key
    id BIGSERIAL PRIMARY KEY,

    -- Reference
    aged_position_id UUID NOT NULL REFERENCES monitoring.aged_positions(id) ON DELETE CASCADE,

    -- Monitoring event
    event_type VARCHAR(50) NOT NULL,
    -- Values: 'price_check', 'close_triggered', 'close_executed', 'close_failed', 'phase_change'

    -- Price data
    market_price DECIMAL(20, 8),
    target_price DECIMAL(20, 8),
    price_distance_percent DECIMAL(10, 4),  -- How far from target

    -- Decision
    action_taken VARCHAR(50),
    -- Values: 'wait', 'trigger_close', 'update_target', 'skip'

    -- Result
    success BOOLEAN,
    error_message TEXT,

    -- Metadata
    event_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_aged_monitoring_aged_position_id ON monitoring.aged_positions_monitoring(aged_position_id);
CREATE INDEX idx_aged_monitoring_event_type ON monitoring.aged_positions_monitoring(event_type);
CREATE INDEX idx_aged_monitoring_created_at ON monitoring.aged_positions_monitoring(created_at DESC);

-- =====================================================
-- FUNCTIONS AND TRIGGERS
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION monitoring.update_aged_positions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for updated_at
CREATE TRIGGER aged_positions_updated_at_trigger
    BEFORE UPDATE ON monitoring.aged_positions
    FOR EACH ROW
    EXECUTE FUNCTION monitoring.update_aged_positions_updated_at();

-- Function to log state transitions
CREATE OR REPLACE FUNCTION monitoring.log_aged_position_state_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO monitoring.aged_positions_history (
            aged_position_id,
            from_status,
            to_status,
            current_market_price,
            target_price,
            loss_tolerance_percent,
            pnl_percent,
            hours_in_previous_state
        ) VALUES (
            NEW.id,
            OLD.status,
            NEW.status,
            NEW.last_checked_price,
            NEW.target_price,
            NEW.current_loss_tolerance_percent,
            NEW.actual_pnl_percent,
            EXTRACT(EPOCH FROM (NOW() - OLD.updated_at)) / 3600.0
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for state change logging
CREATE TRIGGER aged_positions_state_change_trigger
    AFTER UPDATE ON monitoring.aged_positions
    FOR EACH ROW
    EXECUTE FUNCTION monitoring.log_aged_position_state_change();

-- =====================================================
-- VIEWS
-- =====================================================

-- View for currently active aged positions
CREATE OR REPLACE VIEW monitoring.v_active_aged_positions AS
SELECT
    ap.*,
    p.current_price,
    p.mark_price,
    p.unrealized_pnl,
    p.unrealized_pnl_percent,
    p.trailing_activated,
    EXTRACT(EPOCH FROM (NOW() - ap.position_opened_at)) / 3600.0 as total_age_hours,
    EXTRACT(EPOCH FROM (NOW() - ap.detected_at)) / 3600.0 as hours_since_detection,
    CASE
        WHEN ap.side IN ('long', 'buy') THEN
            ((ap.last_checked_price - ap.entry_price) / ap.entry_price) * 100
        ELSE
            ((ap.entry_price - ap.last_checked_price) / ap.entry_price) * 100
    END as current_pnl_percent
FROM monitoring.aged_positions ap
JOIN monitoring.positions p ON ap.position_id = p.id
WHERE ap.status NOT IN ('closed', 'error', 'skipped')
    AND p.status = 'OPEN';

-- View for aged positions statistics
CREATE OR REPLACE VIEW monitoring.v_aged_positions_stats AS
SELECT
    status,
    COUNT(*) as count,
    AVG(hours_aged) as avg_hours_aged,
    AVG(hours_in_grace) as avg_hours_in_grace,
    AVG(hours_in_progressive) as avg_hours_in_progressive,
    AVG(close_attempts) as avg_close_attempts,
    AVG(actual_pnl_percent) FILTER (WHERE status = 'closed') as avg_close_pnl_percent,
    COUNT(*) FILTER (WHERE actual_pnl_percent > 0 AND status = 'closed') as profitable_closes,
    COUNT(*) FILTER (WHERE actual_pnl_percent <= 0 AND status = 'closed') as loss_closes
FROM monitoring.aged_positions
GROUP BY status;

-- =====================================================
-- COMMENTS
-- =====================================================

COMMENT ON TABLE monitoring.aged_positions IS 'Tracks lifecycle of aged positions for WebSocket-based monitoring and closure';
COMMENT ON TABLE monitoring.aged_positions_history IS 'Audit trail of state transitions for aged positions';
COMMENT ON TABLE monitoring.aged_positions_monitoring IS 'Real-time monitoring events and decisions';

COMMENT ON COLUMN monitoring.aged_positions.status IS 'Current state in aged position lifecycle';
COMMENT ON COLUMN monitoring.aged_positions.target_price IS 'Price at which position should be closed';
COMMENT ON COLUMN monitoring.aged_positions.current_loss_tolerance_percent IS 'Current acceptable loss percentage based on age';
COMMENT ON COLUMN monitoring.aged_positions.close_reason IS 'Reason why position was closed';

-- =====================================================
-- INITIAL DATA / CONFIGURATION
-- =====================================================

-- Insert default configuration (optional, can be managed by application)
INSERT INTO monitoring.system_config (key, value, description, created_at)
VALUES
    ('aged_positions.max_age_hours', '3', 'Hours after which position is considered aged', NOW()),
    ('aged_positions.grace_period_hours', '8', 'Grace period for breakeven attempts', NOW()),
    ('aged_positions.loss_step_percent', '0.5', 'Loss tolerance increase per hour', NOW()),
    ('aged_positions.max_loss_percent', '10.0', 'Maximum acceptable loss', NOW()),
    ('aged_positions.acceleration_factor', '1.2', 'Acceleration factor after 10 hours', NOW()),
    ('aged_positions.monitoring_enabled', 'true', 'Enable aged position monitoring', NOW())
ON CONFLICT (key) DO NOTHING;

-- =====================================================
-- ROLLBACK SCRIPT
-- =====================================================

/*
-- To rollback this migration, run:

DROP VIEW IF EXISTS monitoring.v_aged_positions_stats;
DROP VIEW IF EXISTS monitoring.v_active_aged_positions;

DROP TRIGGER IF EXISTS aged_positions_state_change_trigger ON monitoring.aged_positions;
DROP TRIGGER IF EXISTS aged_positions_updated_at_trigger ON monitoring.aged_positions;

DROP FUNCTION IF EXISTS monitoring.log_aged_position_state_change();
DROP FUNCTION IF EXISTS monitoring.update_aged_positions_updated_at();

DROP TABLE IF EXISTS monitoring.aged_positions_monitoring;
DROP TABLE IF EXISTS monitoring.aged_positions_history;
DROP TABLE IF EXISTS monitoring.aged_positions;

DELETE FROM monitoring.system_config
WHERE key LIKE 'aged_positions.%';

*/

-- =====================================================
-- END OF MIGRATION
-- =====================================================