-- Migration: Cleanup stale trailing stop states
-- Date: 2025-10-20
-- Purpose: Remove TS states for positions that no longer exist
--
-- Background:
-- Found 29 stale TS state records from positions that were closed via
-- phantom cleanup but did not trigger on_position_closed() callback.
-- This migration removes those orphaned records.
--
-- This is a ONE-TIME cleanup migration. Future orphaned records will
-- be prevented by the code fix in aged_position_manager.py.

BEGIN;

-- Step 1: Identify and log stale records (for audit trail)
-- Stale = TS state exists but position doesn't exist OR position is closed
CREATE TEMP TABLE stale_ts_states AS
SELECT
    ts.symbol,
    ts.exchange,
    ts.entry_price AS ts_entry_price,
    p.entry_price AS pos_entry_price,
    p.status AS pos_status,
    ts.last_update_time AS ts_last_update_time
FROM monitoring.trailing_stop_state ts
LEFT JOIN monitoring.positions p
    ON ts.symbol = p.symbol
    AND ts.exchange = p.exchange
WHERE
    p.id IS NULL  -- Position doesn't exist
    OR p.status IN ('closed', 'canceled', 'expired');  -- Position is not active

-- Step 2: Log count of stale records
DO $$
DECLARE
    stale_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO stale_count FROM stale_ts_states;
    RAISE NOTICE 'Found % stale TS state records to cleanup', stale_count;
END $$;

-- Step 3: Delete stale TS states
DELETE FROM monitoring.trailing_stop_state ts
WHERE EXISTS (
    SELECT 1 FROM stale_ts_states s
    WHERE s.symbol = ts.symbol
    AND s.exchange = ts.exchange
);

-- Step 4: Delete TS states with mismatched entry prices
-- These are from old positions that were closed and reopened
DELETE FROM monitoring.trailing_stop_state ts
USING monitoring.positions p
WHERE ts.symbol = p.symbol
  AND ts.exchange = p.exchange
  AND p.status = 'active'
  AND ABS(ts.entry_price - p.entry_price) > 0.00001;

-- Step 5: Log cleanup results
DO $$
DECLARE
    mismatched_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO mismatched_count FROM stale_ts_states;
    RAISE NOTICE 'Deleted % TS states with mismatched entry prices', mismatched_count;
END $$;

-- Step 6: Final verification
DO $$
DECLARE
    remaining_orphans INTEGER;
    remaining_mismatches INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining_orphans
    FROM monitoring.trailing_stop_state ts
    LEFT JOIN monitoring.positions p
        ON ts.symbol = p.symbol
        AND ts.exchange = p.exchange
    WHERE p.id IS NULL OR p.status IN ('closed', 'canceled', 'expired');

    SELECT COUNT(*) INTO remaining_mismatches
    FROM monitoring.trailing_stop_state ts
    INNER JOIN monitoring.positions p
        ON ts.symbol = p.symbol
        AND ts.exchange = p.exchange
    WHERE p.status = 'active'
      AND ABS(ts.entry_price - p.entry_price) > 0.00001;

    IF remaining_orphans > 0 OR remaining_mismatches > 0 THEN
        RAISE WARNING 'Still have % orphaned and % mismatched TS states', remaining_orphans, remaining_mismatches;
    ELSE
        RAISE NOTICE 'All stale TS states cleaned up successfully';
    END IF;
END $$;

COMMIT;

-- Validation query (run after migration):
-- SELECT COUNT(*) as orphaned_count
-- FROM monitoring.trailing_stop_state ts
-- LEFT JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange
-- WHERE p.id IS NULL OR p.status = 'CLOSED';
-- Expected result: 0
