-- Migration 007: Add exchange_order_id to positions table
-- Date: 2025-10-16
-- Purpose: Fix atomic position creation by adding missing column

-- Add exchange_order_id column for tracking exchange order IDs
ALTER TABLE monitoring.positions
ADD COLUMN IF NOT EXISTS exchange_order_id VARCHAR(100);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_positions_exchange_order
ON monitoring.positions(exchange_order_id);

-- Add comment
COMMENT ON COLUMN monitoring.positions.exchange_order_id IS
'Exchange-side order ID for the entry order (used in atomic position management)';
