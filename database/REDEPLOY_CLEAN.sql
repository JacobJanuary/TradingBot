-- ============================================================================
-- CLEAN REDEPLOY SCRIPT
-- ============================================================================
-- Purpose: Drop all existing structures and deploy fresh schema
-- WARNING: This will DELETE ALL DATA in monitoring schema!
-- Use only if you need to recreate the schema from scratch
-- ============================================================================

-- ============================================================================
-- STEP 1: DROP EXISTING SCHEMA (CASCADE removes all objects)
-- ============================================================================

DO $$
BEGIN
    -- Drop monitoring schema if exists
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE NOTICE 'Dropping existing monitoring schema...';
        DROP SCHEMA monitoring CASCADE;
        RAISE NOTICE '✅ Monitoring schema dropped';
    ELSE
        RAISE NOTICE 'ℹ️  Monitoring schema does not exist, skipping drop';
    END IF;

    -- Drop FAS schema if exists (legacy cleanup)
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'fas') THEN
        RAISE NOTICE 'Dropping legacy FAS schema...';
        DROP SCHEMA fas CASCADE;
        RAISE NOTICE '✅ FAS schema dropped';
    ELSE
        RAISE NOTICE 'ℹ️  FAS schema does not exist, skipping drop';
    END IF;
END $$;

-- ============================================================================
-- STEP 2: DROP ORPHANED FUNCTIONS (if any exist)
-- ============================================================================

DO $$
DECLARE
    func_record RECORD;
BEGIN
    -- Drop update_updated_at_column function if exists
    FOR func_record IN
        SELECT n.nspname as schema, p.proname as function
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE p.proname = 'update_updated_at_column'
    LOOP
        EXECUTE format('DROP FUNCTION IF EXISTS %I.%I() CASCADE',
                      func_record.schema, func_record.function);
        RAISE NOTICE '✅ Dropped function %.%', func_record.schema, func_record.function;
    END LOOP;
END $$;

-- ============================================================================
-- STEP 3: VERIFY CLEANUP
-- ============================================================================

DO $$
DECLARE
    monitoring_tables INTEGER;
    fas_tables INTEGER;
BEGIN
    -- Check if any monitoring tables remain
    SELECT COUNT(*) INTO monitoring_tables
    FROM pg_tables
    WHERE schemaname = 'monitoring';

    -- Check if any fas tables remain
    SELECT COUNT(*) INTO fas_tables
    FROM pg_tables
    WHERE schemaname = 'fas';

    RAISE NOTICE '========================================';
    RAISE NOTICE 'CLEANUP VERIFICATION';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Monitoring tables remaining: %', monitoring_tables;
    RAISE NOTICE 'FAS tables remaining: %', fas_tables;

    IF monitoring_tables = 0 AND fas_tables = 0 THEN
        RAISE NOTICE '✅ Cleanup successful - ready for fresh deployment';
    ELSE
        RAISE WARNING '⚠️  Some tables may still exist';
    END IF;
    RAISE NOTICE '========================================';
END $$;

-- ============================================================================
-- STEP 4: DEPLOY FRESH SCHEMA
-- ============================================================================

\echo ''
\echo '🚀 Starting fresh schema deployment...'
\echo ''

\i database/DEPLOY_SCHEMA.sql

-- ============================================================================
-- STEP 5: FINAL VERIFICATION
-- ============================================================================

\echo ''
\echo '=========================================='
\echo 'FINAL VERIFICATION'
\echo '=========================================='

SELECT
    '✅ Schema: ' || schemaname as verification,
    COUNT(*) as table_count
FROM pg_tables
WHERE schemaname = 'monitoring'
GROUP BY schemaname;

SELECT
    '✅ Total indexes: ' || COUNT(*)::text as verification
FROM pg_indexes
WHERE schemaname = 'monitoring';

SELECT
    '✅ Total triggers: ' || COUNT(*)::text as verification
FROM information_schema.triggers
WHERE trigger_schema = 'monitoring';

\echo ''
\echo '=========================================='
\echo '🎉 REDEPLOY COMPLETE!'
\echo '=========================================='
\echo ''
