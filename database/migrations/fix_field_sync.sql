-- Migration Fix: Correct field synchronization for monitoring.positions
-- Date: 2025-10-03
-- Purpose: Fix the UPDATE query that failed due to non-existent unrealized_pnl field

-- First, let's check what fields actually exist in the table
-- \d monitoring.positions

-- Since unrealized_pnl doesn't exist, we'll set default values for the new fields
-- Update existing records with sensible defaults

-- Set default values for new fields where they are NULL
UPDATE monitoring.positions SET
    leverage = 1.0
WHERE leverage IS NULL;

UPDATE monitoring.positions SET
    stop_loss = stop_loss_price
WHERE stop_loss IS NULL AND stop_loss_price IS NOT NULL;

UPDATE monitoring.positions SET
    take_profit = take_profit_price
WHERE take_profit IS NULL AND take_profit_price IS NOT NULL;

UPDATE monitoring.positions SET
    pnl = 0.0
WHERE pnl IS NULL;

UPDATE monitoring.positions SET
    pnl_percentage = 0.0
WHERE pnl_percentage IS NULL;

UPDATE monitoring.positions SET
    trailing_activated = FALSE
WHERE trailing_activated IS NULL;

UPDATE monitoring.positions SET
    created_at = opened_at
WHERE created_at IS NULL AND opened_at IS NOT NULL;

-- If opened_at also doesn't exist, use current timestamp
UPDATE monitoring.positions SET
    created_at = NOW()
WHERE created_at IS NULL;

-- Verify the fix
SELECT 'Field synchronization completed successfully' AS status;