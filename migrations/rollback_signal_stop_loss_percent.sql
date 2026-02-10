-- Rollback: Remove signal_stop_loss_percent column
-- Date: 2025-12-10
-- Purpose: Rollback migration if needed

BEGIN;

-- Drop index
DROP INDEX IF EXISTS monitoring.idx_positions_signal_sl_percent;

-- Drop column
ALTER TABLE monitoring.positions 
DROP COLUMN IF EXISTS signal_stop_loss_percent;

COMMIT;

-- Verification query
-- SELECT column_name 
-- FROM information_schema.columns 
-- WHERE table_schema = 'monitoring' 
--   AND table_name = 'positions' 
--   AND column_name = 'signal_stop_loss_percent';
-- Expected: 0 rows
