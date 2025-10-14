-- =====================================================
-- Migration 005: Add updated_at Auto-Update Triggers
-- =====================================================
-- Date: 2025-10-14
-- Purpose: Automatically update updated_at column on UPDATE
-- Dependencies: Tables positions, trades, protection_events must exist
-- Safety: Only adds triggers, does NOT modify existing data
-- Impact: Minimal - triggers add ~0.1ms overhead per UPDATE
-- =====================================================

BEGIN;

-- =====================================================
-- PRE-CHECKS
-- =====================================================

DO $$
BEGIN
    -- Verify monitoring schema exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE EXCEPTION 'Schema monitoring does not exist';
    END IF;

    -- Verify target tables exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'positions') THEN
        RAISE EXCEPTION 'Table monitoring.positions does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'trades') THEN
        RAISE EXCEPTION 'Table monitoring.trades does not exist';
    END IF;

    -- Note: protection_events is optional, may not exist in all environments
    -- IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'protection_events') THEN
    --     RAISE WARNING 'Table monitoring.protection_events does not exist, skipping';
    -- END IF;

    -- Verify updated_at columns exist (or can be added)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = 'positions' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'Column monitoring.positions.updated_at does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'monitoring' AND table_name = 'trades' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'Column monitoring.trades.updated_at does not exist';
    END IF;

    RAISE NOTICE 'Pre-checks passed';
END $$;

-- =====================================================
-- STEP 1: Ensure trigger function exists
-- =====================================================
-- Note: Function may already exist in public schema
-- Using CREATE OR REPLACE to ensure it's available

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION public.update_updated_at_column() IS
    'Trigger function to automatically set updated_at = NOW() on UPDATE. Used by multiple triggers in monitoring schema.';

-- =====================================================
-- STEP 2: Add updated_at column to protection_events (if table exists)
-- =====================================================
-- This table needs updated_at column first

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'protection_events') THEN
        ALTER TABLE monitoring.protection_events
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

        EXECUTE 'COMMENT ON COLUMN monitoring.protection_events.updated_at IS ''Auto-updated timestamp of last row modification''';
        RAISE NOTICE 'Added updated_at column to protection_events';
    ELSE
        RAISE NOTICE 'Table protection_events does not exist, skipping';
    END IF;
END $$;

-- =====================================================
-- STEP 3: Create triggers for each table
-- =====================================================

-- Trigger for positions table
DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON monitoring.positions
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_positions_updated_at ON monitoring.positions IS
    'Auto-updates updated_at column on any UPDATE';

-- Trigger for trades table
DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;

CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON monitoring.trades
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_trades_updated_at ON monitoring.trades IS
    'Auto-updates updated_at column on any UPDATE';

-- Trigger for protection_events table (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'protection_events') THEN
        DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;

        CREATE TRIGGER update_protection_events_updated_at
            BEFORE UPDATE ON monitoring.protection_events
            FOR EACH ROW
            EXECUTE FUNCTION public.update_updated_at_column();

        EXECUTE 'COMMENT ON TRIGGER update_protection_events_updated_at ON monitoring.protection_events IS ''Auto-updates updated_at column on any UPDATE''';
        RAISE NOTICE 'Created trigger for protection_events';
    ELSE
        RAISE NOTICE 'Table protection_events does not exist, skipping trigger creation';
    END IF;
END $$;

-- =====================================================
-- POST-MIGRATION VERIFICATION
-- =====================================================

DO $$
DECLARE
    trigger_count INTEGER;
    has_protection_events BOOLEAN;
    expected_count INTEGER;
BEGIN
    -- Check if protection_events table exists
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'protection_events'
    ) INTO has_protection_events;

    -- Expected trigger count: 2 (positions, trades) + 1 (protection_events if exists)
    expected_count := 2;
    IF has_protection_events THEN
        expected_count := 3;
    END IF;

    -- Count created triggers
    SELECT COUNT(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_schema = 'monitoring'
    AND trigger_name IN (
        'update_positions_updated_at',
        'update_trades_updated_at',
        'update_protection_events_updated_at'
    );

    IF trigger_count != expected_count THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Expected % triggers, found %', expected_count, trigger_count;
    END IF;

    -- Verify function exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.routines
        WHERE routine_schema = 'public'
        AND routine_name = 'update_updated_at_column'
    ) THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Trigger function not created';
    END IF;

    -- Success message
    RAISE NOTICE '✅ Migration 005 completed successfully!';
    RAISE NOTICE '   - Trigger function: public.update_updated_at_column()';
    RAISE NOTICE '   - Triggers created: %', trigger_count;
    RAISE NOTICE '     * monitoring.positions';
    RAISE NOTICE '     * monitoring.trades';
    IF has_protection_events THEN
        RAISE NOTICE '     * monitoring.protection_events';
        RAISE NOTICE '   - Column added: protection_events.updated_at';
    END IF;
END $$;

COMMIT;

-- =====================================================
-- ROLLBACK INSTRUCTIONS
-- =====================================================
-- If you need to rollback this migration, run:
--
-- BEGIN;
-- DROP TRIGGER IF EXISTS update_positions_updated_at ON monitoring.positions;
-- DROP TRIGGER IF EXISTS update_trades_updated_at ON monitoring.trades;
-- DROP TRIGGER IF EXISTS update_protection_events_updated_at ON monitoring.protection_events;
-- DROP FUNCTION IF EXISTS public.update_updated_at_column();
-- ALTER TABLE monitoring.protection_events DROP COLUMN IF EXISTS updated_at;
-- COMMIT;
--
-- WARNING: This will stop automatic updated_at updates!
-- =====================================================
