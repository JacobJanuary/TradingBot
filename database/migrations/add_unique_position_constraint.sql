-- Migration: Add unique constraint to prevent duplicate open positions
-- Date: 2025-10-07
-- Purpose: Prevent race conditions by enforcing database-level uniqueness

-- Add unique partial index ONLY to monitoring schema (where bot works)
CREATE UNIQUE INDEX IF NOT EXISTS unique_open_position_per_symbol_exchange_monitoring
ON monitoring.positions (symbol, exchange) 
WHERE status = 'open';

-- Verify the constraint
SELECT 
    schemaname,
    tablename,
    indexname
FROM pg_indexes
WHERE indexname = 'unique_open_position_per_symbol_exchange_monitoring';