-- Migration: Fix unique index to prevent duplicate position race condition
-- Date: 2025-10-23
-- Issue: Duplicate key violation for idx_unique_active_position
--
-- Problem: Current index only covers status='active', creating a vulnerability
-- window when position is in intermediate states (entry_placed, pending_sl).
-- During this window, another thread can create a duplicate.
--
-- Solution: Extend index to cover ALL open position states.
--
-- Evidence: APTUSDT incident (2025-10-22 21:50:40-45) - 3.76s race condition
-- Root cause: Partial index WHERE status='active'
--
-- Related: Phase 1-4 audit docs in docs/audit_duplicate_position/

BEGIN;

-- Drop old partial index (only covered status='active')
DROP INDEX IF EXISTS monitoring.idx_unique_active_position;

-- Create new partial index covering ALL open position states
-- This prevents duplicates during the entire position lifecycle
CREATE UNIQUE INDEX idx_unique_active_position
ON monitoring.positions (symbol, exchange)
WHERE status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry');

-- Verify: check for any existing violations before committing
DO $$
DECLARE
    violation_count INTEGER;
    violation_details RECORD;
BEGIN
    -- Count violations
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT symbol, exchange, COUNT(*) as cnt
        FROM monitoring.positions
        WHERE status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')
        GROUP BY symbol, exchange
        HAVING COUNT(*) > 1
    ) violations;

    IF violation_count > 0 THEN
        -- Show details of violations
        RAISE NOTICE 'Found % violation(s):', violation_count;

        FOR violation_details IN
            SELECT symbol, exchange, COUNT(*) as cnt,
                   ARRAY_AGG(id ORDER BY created_at) as position_ids
            FROM monitoring.positions
            WHERE status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')
            GROUP BY symbol, exchange
            HAVING COUNT(*) > 1
        LOOP
            RAISE NOTICE '  - %:% has % positions: %',
                violation_details.symbol,
                violation_details.exchange,
                violation_details.cnt,
                violation_details.position_ids;
        END LOOP;

        RAISE EXCEPTION 'Cannot create index: % existing violation(s) found. Clean up duplicates first.', violation_count;
    END IF;

    RAISE NOTICE 'Verification passed: no violations found';
END $$;

COMMIT;

-- Verification query (run after migration)
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'positions' AND indexname = 'idx_unique_active_position';
