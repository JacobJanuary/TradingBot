-- Migration: 003_cleanup_fas_signals.sql
-- Purpose: Change signal_id from INTEGER to VARCHAR(100) to support WebSocket message IDs
-- Date: 2025-10-14
-- Context: fas.signals table already removed, only need to fix column types

BEGIN;

-- ============================================================
-- PHASE 1: PRE-FLIGHT VALIDATION
-- ============================================================

DO $$
BEGIN
    RAISE NOTICE 'Starting migration 003_cleanup_fas_signals...';
    RAISE NOTICE 'Timestamp: %', NOW();
END $$;

-- Verify monitoring schema exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE EXCEPTION 'Schema monitoring does not exist!';
    END IF;
    RAISE NOTICE '✓ Schema monitoring exists';
END $$;

-- ============================================================
-- PHASE 2: BACKUP CURRENT DATA
-- ============================================================

-- Create temporary backup table for positions
CREATE TABLE IF NOT EXISTS monitoring.positions_signal_id_backup AS
SELECT id, signal_id
FROM monitoring.positions
WHERE signal_id IS NOT NULL;

-- Create temporary backup table for trades
CREATE TABLE IF NOT EXISTS monitoring.trades_signal_id_backup AS
SELECT id, signal_id
FROM monitoring.trades
WHERE signal_id IS NOT NULL;

DO $$
BEGIN
    RAISE NOTICE '✓ Backed up % positions with signal_id',
        (SELECT COUNT(*) FROM monitoring.positions_signal_id_backup);
    RAISE NOTICE '✓ Backed up % trades with signal_id',
        (SELECT COUNT(*) FROM monitoring.trades_signal_id_backup);
END $$;

-- ============================================================
-- PHASE 3: ALTER COLUMN TYPES
-- ============================================================

-- Change positions.signal_id: INTEGER → VARCHAR(100)
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE VARCHAR(100) USING signal_id::TEXT;

-- Change trades.signal_id: INTEGER → VARCHAR(100)
ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE VARCHAR(100) USING signal_id::TEXT;

DO $$
BEGIN
    RAISE NOTICE '✓ Changed monitoring.positions.signal_id to VARCHAR(100)';
    RAISE NOTICE '✓ Changed monitoring.trades.signal_id to VARCHAR(100)';
END $$;

-- ============================================================
-- PHASE 4: UPDATE COMMENTS
-- ============================================================

COMMENT ON COLUMN monitoring.positions.signal_id IS
'WebSocket signal message ID (NOT a foreign key to fas.signals)';

COMMENT ON COLUMN monitoring.trades.signal_id IS
'WebSocket signal message ID (NOT a foreign key to fas.signals)';

DO $$
BEGIN
    RAISE NOTICE '✓ Updated column comments';
END $$;

-- ============================================================
-- PHASE 5: VERIFY DATA INTEGRITY
-- ============================================================

DO $$
DECLARE
    pos_count_before INTEGER;
    pos_count_after INTEGER;
    trades_count_before INTEGER;
    trades_count_after INTEGER;
BEGIN
    -- Check positions data integrity
    SELECT COUNT(*) INTO pos_count_before FROM monitoring.positions_signal_id_backup;
    SELECT COUNT(*) INTO pos_count_after FROM monitoring.positions WHERE signal_id IS NOT NULL;

    IF pos_count_before != pos_count_after THEN
        RAISE EXCEPTION 'Data integrity check FAILED for positions: before=%, after=%',
            pos_count_before, pos_count_after;
    END IF;

    -- Check trades data integrity
    SELECT COUNT(*) INTO trades_count_before FROM monitoring.trades_signal_id_backup;
    SELECT COUNT(*) INTO trades_count_after FROM monitoring.trades WHERE signal_id IS NOT NULL;

    IF trades_count_before != trades_count_after THEN
        RAISE EXCEPTION 'Data integrity check FAILED for trades: before=%, after=%',
            trades_count_before, trades_count_after;
    END IF;

    RAISE NOTICE '✓ Data integrity verified: positions=%, trades=%',
        pos_count_after, trades_count_after;
END $$;

-- ============================================================
-- PHASE 6: CLEANUP BACKUP TABLES (optional - keep for safety)
-- ============================================================

-- Uncomment to drop backup tables after verification
-- DROP TABLE IF EXISTS monitoring.positions_signal_id_backup;
-- DROP TABLE IF EXISTS monitoring.trades_signal_id_backup;

-- ============================================================
-- MIGRATION COMPLETE
-- ============================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Migration 003_cleanup_fas_signals COMPLETED';
    RAISE NOTICE 'Timestamp: %', NOW();
    RAISE NOTICE '========================================';
END $$;

COMMIT;

-- ============================================================
-- ROLLBACK SCRIPT (if needed)
-- ============================================================
/*
BEGIN;

-- Restore original INTEGER type
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE INTEGER USING signal_id::INTEGER;

ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE INTEGER USING signal_id::INTEGER;

-- Verify rollback
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'monitoring'
AND table_name IN ('positions', 'trades')
AND column_name = 'signal_id';

COMMIT;
*/
