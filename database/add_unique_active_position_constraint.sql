-- Migration: Add UNIQUE constraint for active positions
-- Purpose: Prevent duplicate active positions at database level
-- Date: 2025-10-17
-- Related: DUPLICATE_POS_FINAL_001

-- ============================================================================
-- FIX 3.1: Add UNIQUE Constraint
-- ============================================================================

-- This creates a partial unique index that only applies to active positions
-- Multiple closed/rolled_back positions for same symbol are allowed
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_position
ON monitoring.positions (symbol, exchange)
WHERE status = 'active';

-- Verify the constraint was created
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'monitoring'
        AND tablename = 'positions'
        AND indexname = 'idx_unique_active_position'
    ) THEN
        RAISE NOTICE '✅ UNIQUE constraint created successfully';
    ELSE
        RAISE EXCEPTION '❌ UNIQUE constraint creation failed';
    END IF;
END $$;

-- Test constraint (optional - uncomment to test)
-- This should succeed if no duplicates exist
-- DO $$
-- DECLARE
--     duplicate_count INTEGER;
-- BEGIN
--     SELECT COUNT(*) INTO duplicate_count
--     FROM (
--         SELECT symbol, exchange, COUNT(*) as cnt
--         FROM monitoring.positions
--         WHERE status = 'active'
--         GROUP BY symbol, exchange
--         HAVING COUNT(*) > 1
--     ) duplicates;
--
--     IF duplicate_count > 0 THEN
--         RAISE WARNING '⚠️  Found % duplicate active positions - need cleanup first!', duplicate_count;
--     ELSE
--         RAISE NOTICE '✅ No duplicate active positions found';
--     END IF;
-- END $$;
