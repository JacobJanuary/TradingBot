-- Cleanup duplicate positions in database
-- ЭТАП 3: Remove duplicate position records
--
-- Strategy: Keep the most recently updated record for each (symbol, exchange) pair
-- and close the older duplicates

-- First, identify duplicates (for verification before running delete)
SELECT symbol, exchange, COUNT(*) as cnt,
       array_agg(id ORDER BY updated_at DESC) as position_ids
FROM monitoring.positions
WHERE status='active'
GROUP BY symbol, exchange
HAVING COUNT(*) > 1;

-- Close duplicate position records (keep most recent, close others)
WITH duplicates AS (
    SELECT id,
           symbol,
           exchange,
           updated_at,
           ROW_NUMBER() OVER (
               PARTITION BY symbol, exchange
               ORDER BY updated_at DESC
           ) as rn
    FROM monitoring.positions
    WHERE status='active'
)
UPDATE monitoring.positions
SET status = 'closed',
    exit_reason = 'duplicate_cleanup',
    closed_at = NOW()
WHERE id IN (
    SELECT id FROM duplicates WHERE rn > 1
);

-- Verify cleanup (should return 0 rows if successful)
SELECT symbol, exchange, COUNT(*) as cnt
FROM monitoring.positions
WHERE status='active'
GROUP BY symbol, exchange
HAVING COUNT(*) > 1;
