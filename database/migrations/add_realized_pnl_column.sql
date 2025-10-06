-- Migration: Add realized_pnl column to monitoring.positions table
-- Date: 2025-10-04
-- Purpose: Add realized_pnl column that is used by repository.close_position()
--          and other modules but may be missing from older database schemas

-- Add realized_pnl column (for closed positions' final P&L)
ALTER TABLE monitoring.positions 
ADD COLUMN IF NOT EXISTS realized_pnl DECIMAL(20, 8);

-- Sync existing data: copy pnl to realized_pnl for closed positions
UPDATE monitoring.positions SET realized_pnl = pnl
WHERE status = 'closed' AND realized_pnl IS NULL AND pnl IS NOT NULL;
