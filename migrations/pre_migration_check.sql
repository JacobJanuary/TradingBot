-- =====================================================================
-- PRE-MIGRATION CHECK: Current state verification
-- =====================================================================
-- Date: 2025-10-24
-- Purpose: Document current state BEFORE migration
--
-- Run this script before starting migration to:
--   1. Document current database state
--   2. Verify expected problems exist
--   3. Get baseline counts for data integrity verification
-- =====================================================================

\echo '======================================================================='
\echo 'PRE-MIGRATION STATE CHECK'
\echo '======================================================================='
\echo ''

-- =====================================================================
-- 1. Database timezone (ожидаем: Europe/Moscow)
-- =====================================================================
\echo '1. Current Database Timezone:'
\echo '----------------------------'
SHOW timezone;

DO $$
DECLARE
    current_tz TEXT;
BEGIN
    SHOW timezone INTO current_tz;
    IF current_tz = 'Europe/Moscow' THEN
        RAISE NOTICE '✓ Expected timezone: Europe/Moscow (UTC+3)';
    ELSE
        RAISE WARNING '⚠️  Unexpected timezone: % (expected Europe/Moscow)', current_tz;
    END IF;
END $$;
\echo ''

-- =====================================================================
-- 2. Aged tables location (ожидаем: в public, должны быть в monitoring)
-- =====================================================================
\echo '2. Aged Tables Location (Expected: public, Should be: monitoring):'
\echo '-----------------------------------------------------------------'
SELECT
    table_schema,
    table_name,
    CASE
        WHEN table_schema = 'public' THEN '❌ WRONG (in public)'
        WHEN table_schema = 'monitoring' THEN '✓ CORRECT (in monitoring)'
        ELSE '? Unexpected schema'
    END as status
FROM information_schema.tables
WHERE table_name IN ('aged_positions', 'aged_monitoring_events')
ORDER BY table_schema, table_name;
\echo ''

-- =====================================================================
-- 3. Data counts для верификации после миграции
-- =====================================================================
\echo '3. Current Data Counts (for post-migration verification):'
\echo '--------------------------------------------------------'
DO $$
DECLARE
    pos_count INTEGER := 0;
    events_count INTEGER := 0;
    total_pos INTEGER;
    open_pos INTEGER;
BEGIN
    -- Check aged_positions (может быть в public или monitoring)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'aged_positions') THEN
        SELECT COUNT(*) INTO pos_count FROM public.aged_positions;
        RAISE NOTICE 'public.aged_positions: % records', pos_count;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'aged_positions') THEN
        SELECT COUNT(*) INTO pos_count FROM monitoring.aged_positions;
        RAISE NOTICE 'monitoring.aged_positions: % records', pos_count;
    END IF;

    IF pos_count = 0 THEN
        RAISE WARNING 'aged_positions: NOT FOUND in any schema!';
    END IF;

    -- Check aged_monitoring_events
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'aged_monitoring_events') THEN
        SELECT COUNT(*) INTO events_count FROM public.aged_monitoring_events;
        RAISE NOTICE 'public.aged_monitoring_events: % records', events_count;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'aged_monitoring_events') THEN
        SELECT COUNT(*) INTO events_count FROM monitoring.aged_monitoring_events;
        RAISE NOTICE 'monitoring.aged_monitoring_events: % records', events_count;
    END IF;

    IF events_count = 0 THEN
        RAISE WARNING 'aged_monitoring_events: NOT FOUND in any schema!';
    END IF;

    -- Check main positions table
    SELECT COUNT(*) INTO total_pos FROM monitoring.positions;
    SELECT COUNT(*) INTO open_pos FROM monitoring.positions WHERE status = 'OPEN';
    RAISE NOTICE 'monitoring.positions: % total (% open)', total_pos, open_pos;
END $$;
\echo ''

-- =====================================================================
-- 4. Timestamp types audit (ожидаем: timestamp without time zone)
-- =====================================================================
\echo '4. Timestamp Column Types (Expected: "timestamp without time zone"):'
\echo '-------------------------------------------------------------------'
SELECT
    table_schema,
    table_name,
    COUNT(*) as timestamp_columns,
    MAX(data_type) as data_type
FROM information_schema.columns
WHERE table_schema IN ('monitoring', 'trading', 'fas')
  AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                      'executed_at', 'timestamp', 'acknowledged_at',
                      'last_update', 'last_error_at', 'received_at', 'processed_at')
GROUP BY table_schema, table_name, data_type
ORDER BY table_schema, table_name;
\echo ''

DO $$
DECLARE
    wrong_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO wrong_count
    FROM information_schema.columns
    WHERE table_schema IN ('monitoring', 'trading', 'fas')
      AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                          'executed_at', 'timestamp', 'acknowledged_at',
                          'last_update', 'last_error_at', 'received_at', 'processed_at')
      AND data_type = 'timestamp without time zone';

    RAISE NOTICE 'Found % timestamp columns needing conversion', wrong_count;
END $$;
\echo ''

-- =====================================================================
-- 5. Sample timestamps (показываем текущие значения)
-- =====================================================================
\echo '5. Sample Timestamps from monitoring.positions:'
\echo '-----------------------------------------------'
SELECT
    id,
    symbol,
    opened_at,
    created_at,
    EXTRACT(EPOCH FROM (NOW() - opened_at)) / 3600 as calculated_age_hours
FROM monitoring.positions
WHERE status = 'OPEN'
ORDER BY opened_at DESC
LIMIT 5;
\echo ''

-- =====================================================================
-- 6. Проблемные позиции (старше 3 часов)
-- =====================================================================
\echo '6. Aged Positions (older than 3 hours):'
\echo '---------------------------------------'
SELECT
    id,
    symbol,
    exchange,
    side,
    entry_price,
    opened_at,
    EXTRACT(EPOCH FROM (NOW() - opened_at)) / 3600 as age_hours,
    status
FROM monitoring.positions
WHERE status = 'OPEN'
  AND EXTRACT(EPOCH FROM (NOW() - opened_at)) / 3600 > 3
ORDER BY opened_at;
\echo ''

DO $$
DECLARE
    aged_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO aged_count
    FROM monitoring.positions
    WHERE status = 'OPEN'
      AND EXTRACT(EPOCH FROM (NOW() - opened_at)) / 3600 > 3;

    IF aged_count > 0 THEN
        RAISE NOTICE 'Found % positions older than 3 hours', aged_count;
    ELSE
        RAISE NOTICE 'No aged positions found';
    END IF;
END $$;
\echo ''

-- =====================================================================
-- 7. Все схемы и таблицы
-- =====================================================================
\echo '7. All Tables by Schema:'
\echo '-----------------------'
SELECT
    table_schema,
    COUNT(*) as table_count
FROM information_schema.tables
WHERE table_schema IN ('monitoring', 'trading', 'fas', 'public')
GROUP BY table_schema
ORDER BY table_schema;
\echo ''

-- =====================================================================
-- 8. Summary: Expected problems
-- =====================================================================
\echo '======================================================================='
\echo 'PRE-MIGRATION SUMMARY - Expected Problems:'
\echo '======================================================================='
DO $$
DECLARE
    db_tz TEXT;
    aged_in_public INTEGER;
    wrong_timestamps INTEGER;
BEGIN
    SHOW timezone INTO db_tz;

    SELECT COUNT(*) INTO aged_in_public
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN ('aged_positions', 'aged_monitoring_events');

    SELECT COUNT(*) INTO wrong_timestamps
    FROM information_schema.columns
    WHERE table_schema IN ('monitoring', 'trading', 'fas')
      AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                          'executed_at', 'timestamp', 'acknowledged_at',
                          'last_update', 'last_error_at', 'received_at', 'processed_at')
      AND data_type = 'timestamp without time zone';

    RAISE NOTICE '======================================================================';
    RAISE NOTICE 'Database timezone: % (should be UTC)', db_tz;
    RAISE NOTICE 'Aged tables in public schema: % (should be 0, in monitoring)', aged_in_public;
    RAISE NOTICE 'Timestamp columns needing conversion: % → timestamptz', wrong_timestamps;
    RAISE NOTICE '======================================================================';
    RAISE NOTICE '';
    RAISE NOTICE '✓ Pre-migration check complete. Ready to start migration.';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Stop trading bot';
    RAISE NOTICE '  2. Run migration_001_move_aged_tables_to_monitoring.sql';
    RAISE NOTICE '  3. Run migration_002_convert_timestamps_to_utc.sql';
    RAISE NOTICE '  4. ALTER DATABASE fox_crypto SET timezone TO ''UTC'';';
    RAISE NOTICE '  5. Run migration_003_verify.sql';
    RAISE NOTICE '  6. Update bot code (models.py, repository.py, etc.)';
    RAISE NOTICE '  7. Start bot and monitor';
    RAISE NOTICE '======================================================================';
END $$;
