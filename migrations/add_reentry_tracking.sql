-- Migration: Add reentry tracking table
-- Date: 2026-01-02
-- Description: Adds table for tracking reentry signals after trailing stop exits

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Reentry signals table
CREATE TABLE IF NOT EXISTS monitoring.reentry_signals (
    id SERIAL PRIMARY KEY,
    
    -- Signal reference
    signal_id INTEGER,  -- Can reference web.signal_analysis if needed
    
    -- Position info
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'long' or 'short'
    
    -- Entry tracking
    original_entry_price NUMERIC(20,8) NOT NULL,
    original_entry_time TIMESTAMPTZ NOT NULL,
    
    -- Exit tracking
    last_exit_price NUMERIC(20,8) NOT NULL,
    last_exit_time TIMESTAMPTZ NOT NULL,
    last_exit_reason VARCHAR(50),  -- 'trailing_stop', 'stop_loss', etc.
    
    -- Reentry tracking
    reentry_count INTEGER DEFAULT 0,
    max_reentries INTEGER DEFAULT 5,
    
    -- Price tracking after exit
    max_price_after_exit NUMERIC(20,8),
    min_price_after_exit NUMERIC(20,8),
    
    -- Config
    cooldown_sec INTEGER DEFAULT 300,
    drop_percent NUMERIC(5,2) DEFAULT 5.0,
    
    -- Lifecycle
    expires_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) DEFAULT 'active',  -- active, reentered, expired, max_reached
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_reentry_active 
    ON monitoring.reentry_signals(symbol, status) 
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_reentry_expires 
    ON monitoring.reentry_signals(expires_at) 
    WHERE status = 'active';

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION monitoring.update_reentry_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reentry_updated_at ON monitoring.reentry_signals;
CREATE TRIGGER reentry_updated_at
    BEFORE UPDATE ON monitoring.reentry_signals
    FOR EACH ROW
    EXECUTE FUNCTION monitoring.update_reentry_updated_at();

-- Add comment
COMMENT ON TABLE monitoring.reentry_signals IS 
    'Tracks reentry opportunities after trailing stop exits for Delta Reversal strategy';
