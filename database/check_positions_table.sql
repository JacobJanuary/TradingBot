-- Check current state of monitoring.positions table
-- Date: 2025-10-03

-- 1. Show table structure
SELECT 'TABLE STRUCTURE:' as info;
\d monitoring.positions

-- 2. Check if all required fields exist
SELECT 'FIELD EXISTENCE CHECK:' as info;
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name IN ('leverage', 'stop_loss', 'take_profit', 'pnl', 'pnl_percentage', 'trailing_activated', 'created_at')
ORDER BY column_name;

-- 3. Count total columns
SELECT 'COLUMN COUNT:' as info;
SELECT COUNT(*) as total_columns
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions';

-- 4. Show sample data to verify fields are accessible
SELECT 'SAMPLE DATA:' as info;
SELECT
    id, symbol, exchange, side, quantity, leverage,
    stop_loss, take_profit, pnl, pnl_percentage,
    trailing_activated, created_at, status
FROM monitoring.positions
LIMIT 3;

-- 5. Check indexes
SELECT 'INDEXES:' as info;
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'positions'
  AND schemaname = 'monitoring'
  AND indexname LIKE '%leverage%'
   OR indexname LIKE '%trailing%'
   OR indexname LIKE '%created_at%';

-- 6. Final verification - try the problematic query
SELECT 'QUERY TEST:' as info;
SELECT
    id, symbol, exchange, side, entry_price, current_price,
    quantity, leverage, stop_loss, take_profit,
    status, pnl, pnl_percentage, trailing_activated,
    created_at, updated_at
FROM monitoring.positions
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 1;