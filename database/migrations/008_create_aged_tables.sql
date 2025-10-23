-- Migration: Create aged positions tracking tables
-- Date: 2025-10-23
-- Purpose: Support Aged Position Manager V2

-- Table for tracking aged positions
CREATE TABLE IF NOT EXISTS aged_positions (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    target_price DECIMAL(20, 8) NOT NULL,
    phase VARCHAR(50) NOT NULL,
    hours_aged INTEGER NOT NULL,
    loss_tolerance DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(position_id)
);

-- Table for aged position monitoring events
CREATE TABLE IF NOT EXISTS aged_monitoring_events (
    id SERIAL PRIMARY KEY,
    aged_position_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    market_price DECIMAL(20, 8),
    target_price DECIMAL(20, 8),
    price_distance_percent DECIMAL(10, 4),
    action_taken VARCHAR(100),
    success BOOLEAN,
    error_message TEXT,
    event_metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_aged_positions_symbol ON aged_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_aged_positions_created ON aged_positions(created_at);
CREATE INDEX IF NOT EXISTS idx_aged_monitoring_position ON aged_monitoring_events(aged_position_id);
CREATE INDEX IF NOT EXISTS idx_aged_monitoring_created ON aged_monitoring_events(created_at);
CREATE INDEX IF NOT EXISTS idx_aged_monitoring_type ON aged_monitoring_events(event_type);

-- Grant permissions (adjust user as needed)
GRANT ALL PRIVILEGES ON aged_positions TO evgeniyyanvarskiy;
GRANT ALL PRIVILEGES ON aged_monitoring_events TO evgeniyyanvarskiy;
GRANT USAGE, SELECT ON SEQUENCE aged_positions_id_seq TO evgeniyyanvarskiy;
GRANT USAGE, SELECT ON SEQUENCE aged_monitoring_events_id_seq TO evgeniyyanvarskiy;