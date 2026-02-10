-- Migration: Add signal_stop_loss_percent column
-- Date: 2025-12-10
-- Purpose: Store signal-specific SL percentage to preserve signal optimization
-- Related: Option 2 implementation - fix Protection Manager overwriting signal params

BEGIN;

-- Add column for signal-specific stop loss percentage
ALTER TABLE monitoring.positions 
ADD COLUMN signal_stop_loss_percent NUMERIC(10,4);

-- Add comment for documentation
COMMENT ON COLUMN monitoring.positions.signal_stop_loss_percent IS 
'Signal-specific stop loss percentage. If set, takes priority over database/env defaults. Preserves signal optimization. NULL means use database/env defaults.';

-- Create index for analytics and filtering
CREATE INDEX idx_positions_signal_sl_percent 
ON monitoring.positions(signal_stop_loss_percent) 
WHERE signal_stop_loss_percent IS NOT NULL;

COMMIT;

-- Verification query
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_schema = 'monitoring' 
--   AND table_name = 'positions' 
--   AND column_name = 'signal_stop_loss_percent';
