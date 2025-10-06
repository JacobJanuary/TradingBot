-- Migration: Add missing fields to monitoring.positions table
-- Date: 2025-10-03
-- Purpose: Add fields required by repository queries that were missing from schema

-- Add missing fields to monitoring.positions table
-- Using IF NOT EXISTS for PostgreSQL 9.6+

-- Add leverage field (used by WebSocket streams and synchronizer)
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS leverage DECIMAL(10, 2) DEFAULT 1.0;

-- Add stop_loss field (alias for stop_loss_price)
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS stop_loss DECIMAL(20, 8);

-- Add take_profit field (alias for take_profit_price)
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS take_profit DECIMAL(20, 8);

-- Add pnl field (alias for unrealized_pnl)
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS pnl DECIMAL(20, 8);

-- Add pnl_percentage field
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS pnl_percentage DECIMAL(10, 4);

-- Add trailing_activated field
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS trailing_activated BOOLEAN DEFAULT FALSE;

-- Add created_at field (alias for opened_at)
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- Update existing records to sync alias fields with their primary counterparts
UPDATE monitoring.positions SET
    stop_loss = COALESCE(stop_loss, stop_loss_price),
    take_profit = COALESCE(take_profit, take_profit_price),
    pnl = COALESCE(pnl, unrealized_pnl, 0),
    created_at = COALESCE(created_at, opened_at, NOW())
WHERE stop_loss IS NULL OR take_profit IS NULL OR pnl IS NULL OR created_at IS NULL;

-- Add indexes for performance on new fields
CREATE INDEX IF NOT EXISTS idx_positions_leverage ON monitoring.positions(leverage);

CREATE INDEX IF NOT EXISTS idx_positions_trailing_activated ON monitoring.positions(trailing_activated);

CREATE INDEX IF NOT EXISTS idx_positions_created_at ON monitoring.positions(created_at DESC);
