-- Migration: Cleanup for fresh start
-- Date: 2025-10-08
-- Purpose: Clear all tables for fresh test

-- Disable triggers temporarily
SET session_replication_role = replica;

-- Clear positions (CASCADE will clear protection_events)
TRUNCATE monitoring.positions CASCADE;

-- Clear trades
TRUNCATE monitoring.trades CASCADE;

-- Clear processed_signals (if exists in monitoring)
TRUNCATE monitoring.processed_signals;

-- Clear protection_events explicitly
TRUNCATE monitoring.protection_events;

-- Clear daily_stats if exists
TRUNCATE monitoring.daily_stats;

-- Re-enable triggers
SET session_replication_role = DEFAULT;

-- Reset sequences
ALTER SEQUENCE monitoring.positions_id_seq RESTART WITH 1;
ALTER SEQUENCE monitoring.trades_id_seq RESTART WITH 1;
ALTER SEQUENCE monitoring.processed_signals_id_seq RESTART WITH 1;

-- Verify cleanup
SELECT 
    'monitoring.positions' AS table_name, 
    COUNT(*) AS records 
FROM monitoring.positions
UNION ALL
SELECT 
    'monitoring.trades', 
    COUNT(*) 
FROM monitoring.trades
UNION ALL
SELECT 
    'monitoring.processed_signals', 
    COUNT(*) 
FROM monitoring.processed_signals
UNION ALL
SELECT 
    'monitoring.protection_events', 
    COUNT(*) 
FROM monitoring.protection_events;
