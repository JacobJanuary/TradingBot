-- Migration 007: Add peak persistence tracking fields to trailing_stop_state
-- Purpose: Track when peak prices were last saved for better recovery
-- Created: 2025-10-20

-- Add new columns
ALTER TABLE monitoring.trailing_stop_state
ADD COLUMN IF NOT EXISTS last_peak_save_time TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS last_saved_peak_price DECIMAL(20, 8);

-- Add comments
COMMENT ON COLUMN monitoring.trailing_stop_state.last_peak_save_time
IS 'Last time peak price was saved to database (for batching)';

COMMENT ON COLUMN monitoring.trailing_stop_state.last_saved_peak_price
IS 'Last saved peak price value (for improvement-based saving)';

-- Create index for performance (optional)
CREATE INDEX IF NOT EXISTS idx_ts_state_peak_save_time
ON monitoring.trailing_stop_state(last_peak_save_time DESC);
