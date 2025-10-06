-- Migration: Add exit_reason column to positions table
-- Date: 2025-10-04
-- Purpose: Fix critical bug with position closing
-- Ref: CRITICAL_BUG_REPORT_20251004.md

-- Add exit_reason column if it doesn't exist
ALTER TABLE monitoring.positions
ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(50);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_positions_exit_reason
ON monitoring.positions(exit_reason);

-- Verify the column was added
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name = 'exit_reason';
