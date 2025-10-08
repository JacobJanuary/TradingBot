-- Migration: Fix unique constraint to use 'active' instead of 'open'
-- Date: 2025-10-08
-- Purpose: Constraint was checking status='open' but bot uses status='active'

-- Drop old constraint
DROP INDEX IF EXISTS unique_open_position_per_symbol_exchange_monitoring;

-- Create new constraint with correct status
CREATE UNIQUE INDEX unique_open_position_per_symbol_exchange_monitoring
ON monitoring.positions (symbol, exchange) 
WHERE status = 'active';

-- Verify the constraint
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE indexname = 'unique_open_position_per_symbol_exchange_monitoring';
