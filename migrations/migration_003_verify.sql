-- =====================================================================
-- MIGRATION 003: Verification queries
-- =====================================================================
-- Date: 2025-10-24
-- Purpose: Verify all migrations completed successfully
--
-- This script can be run multiple times to check migration status
-- =====================================================================

\echo '======================================================================='
\echo 'MIGRATION VERIFICATION REPORT'
\echo '======================================================================='
\echo ''

-- =====================================================================
-- 1. Проверка timezone базы данных
-- =====================================================================
\echo '1. Database Timezone:'
\echo '-------------------'
SHOW timezone;
\echo ''

-- =====================================================================
-- 2. Проверка схемы aged таблиц
-- =====================================================================
\echo '2. Aged Tables Schema Location:'
\echo '-------------------------------'
SELECT
    table_schema,
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE columns.table_name = tables.table_name AND columns.table_schema = tables.table_schema) as column_count
FROM information_schema.tables
WHERE table_name IN ('aged_positions', 'aged_monitoring_events')
ORDER BY table_schema, table_name;
\echo ''

-- Проверка что таблицы НЕ в public
DO $$
DECLARE
    public_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO public_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN ('aged_positions', 'aged_monitoring_events');

    IF public_count > 0 THEN
        RAISE WARNING '❌ Found % aged tables still in public schema!', public_count;
    ELSE
        RAISE NOTICE '✓ No aged tables in public schema';
    END IF;
END $$;
\echo ''

-- =====================================================================
-- 3. Проверка timestamp типов (должны быть timestamptz)
-- =====================================================================
\echo '3. Timestamp Column Types:'
\echo '-------------------------'
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    CASE
        WHEN data_type = 'timestamp with time zone' THEN '✓ OK'
        WHEN data_type = 'timestamp without time zone' THEN '❌ WRONG'
        ELSE '? UNKNOWN'
    END as status
FROM information_schema.columns
WHERE table_schema IN ('monitoring', 'trading', 'fas')
  AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                      'executed_at', 'timestamp', 'acknowledged_at',
                      'last_update', 'last_error_at', 'received_at', 'processed_at')
ORDER BY table_schema, table_name, column_name;
\echo ''

-- Подсчет неправильных типов
DO $$
DECLARE
    wrong_count INTEGER;
    correct_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO wrong_count
    FROM information_schema.columns
    WHERE table_schema IN ('monitoring', 'trading', 'fas')
      AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                          'executed_at', 'timestamp', 'acknowledged_at',
                          'last_update', 'last_error_at', 'received_at', 'processed_at')
      AND data_type = 'timestamp without time zone';

    SELECT COUNT(*) INTO correct_count
    FROM information_schema.columns
    WHERE table_schema IN ('monitoring', 'trading', 'fas')
      AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                          'executed_at', 'timestamp', 'acknowledged_at',
                          'last_update', 'last_error_at', 'received_at', 'processed_at')
      AND data_type = 'timestamp with time zone';

    RAISE NOTICE 'Timestamp columns: % correct (timestamptz), % wrong (timestamp)', correct_count, wrong_count;

    IF wrong_count > 0 THEN
        RAISE WARNING '❌ Migration incomplete: % columns still need conversion!', wrong_count;
    ELSE
        RAISE NOTICE '✓ All timestamp columns correctly converted to timestamptz';
    END IF;
END $$;
\echo ''

-- =====================================================================
-- 4. Проверка данных в aged таблицах
-- =====================================================================
\echo '4. Aged Tables Data Count:'
\echo '-------------------------'
DO $$
DECLARE
    pos_count INTEGER;
    events_count INTEGER;
BEGIN
    -- Пробуем найти таблицы в monitoring
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'aged_positions') THEN
        SELECT COUNT(*) INTO pos_count FROM monitoring.aged_positions;
        RAISE NOTICE 'monitoring.aged_positions: % records', pos_count;
    ELSE
        RAISE WARNING 'monitoring.aged_positions: TABLE NOT FOUND';
        pos_count := -1;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'aged_monitoring_events') THEN
        SELECT COUNT(*) INTO events_count FROM monitoring.aged_monitoring_events;
        RAISE NOTICE 'monitoring.aged_monitoring_events: % records', events_count;
    ELSE
        RAISE WARNING 'monitoring.aged_monitoring_events: TABLE NOT FOUND';
        events_count := -1;
    END IF;

    -- Проверяем public schema
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'aged_positions') THEN
        SELECT COUNT(*) INTO pos_count FROM public.aged_positions;
        RAISE WARNING 'public.aged_positions: % records (SHOULD BE IN MONITORING!)', pos_count;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'aged_monitoring_events') THEN
        SELECT COUNT(*) INTO events_count FROM public.aged_monitoring_events;
        RAISE WARNING 'public.aged_monitoring_events: % records (SHOULD BE IN MONITORING!)', events_count;
    END IF;
END $$;
\echo ''

-- =====================================================================
-- 5. Проверка sample timestamps (должны быть UTC)
-- =====================================================================
\echo '5. Sample Timestamps (should be UTC):'
\echo '------------------------------------'
SELECT
    'monitoring.positions' as table_name,
    id,
    symbol,
    opened_at,
    EXTRACT(TIMEZONE FROM opened_at) / 3600 as tz_offset_hours
FROM monitoring.positions
WHERE opened_at IS NOT NULL
ORDER BY opened_at DESC
LIMIT 3;
\echo ''

-- =====================================================================
-- 6. Проверка текущих открытых позиций
-- =====================================================================
\echo '6. Current Open Positions:'
\echo '-------------------------'
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
ORDER BY opened_at;
\echo ''

-- =====================================================================
-- 7. Проверка DEFAULT значений для timestamp колонок
-- =====================================================================
\echo '7. Timestamp Columns DEFAULT Values:'
\echo '-----------------------------------'
SELECT
    table_schema,
    table_name,
    column_name,
    column_default,
    CASE
        WHEN column_default IS NULL THEN '⚠️  No default'
        WHEN column_default LIKE '%now()%' OR column_default LIKE '%CURRENT_TIMESTAMP%' THEN '✓ Has default'
        ELSE '? Unknown: ' || column_default
    END as status
FROM information_schema.columns
WHERE table_schema IN ('monitoring', 'trading', 'fas')
  AND column_name IN ('created_at', 'updated_at', 'opened_at', 'timestamp', 'received_at')
ORDER BY table_schema, table_name, column_name;
\echo ''

-- =====================================================================
-- 8. Final Summary
-- =====================================================================
\echo '======================================================================='
\echo 'FINAL SUMMARY:'
\echo '======================================================================='
DO $$
DECLARE
    db_tz TEXT;
    aged_in_public INTEGER;
    wrong_timestamps INTEGER;
    pos_count INTEGER;
    events_count INTEGER;
    all_ok BOOLEAN := TRUE;
BEGIN
    -- 1. Check timezone
    SHOW timezone INTO db_tz;
    IF db_tz != 'UTC' THEN
        RAISE WARNING '❌ Database timezone is "%" (should be UTC)', db_tz;
        all_ok := FALSE;
    ELSE
        RAISE NOTICE '✓ Database timezone: UTC';
    END IF;

    -- 2. Check aged tables schema
    SELECT COUNT(*) INTO aged_in_public
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN ('aged_positions', 'aged_monitoring_events');

    IF aged_in_public > 0 THEN
        RAISE WARNING '❌ % aged tables still in public schema', aged_in_public;
        all_ok := FALSE;
    ELSE
        RAISE NOTICE '✓ All aged tables in monitoring schema';
    END IF;

    -- 3. Check timestamp types
    SELECT COUNT(*) INTO wrong_timestamps
    FROM information_schema.columns
    WHERE table_schema IN ('monitoring', 'trading', 'fas')
      AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                          'executed_at', 'timestamp', 'acknowledged_at',
                          'last_update', 'last_error_at', 'received_at', 'processed_at')
      AND data_type = 'timestamp without time zone';

    IF wrong_timestamps > 0 THEN
        RAISE WARNING '❌ % timestamp columns not converted to timestamptz', wrong_timestamps;
        all_ok := FALSE;
    ELSE
        RAISE NOTICE '✓ All timestamp columns are timestamptz';
    END IF;

    -- 4. Check data integrity
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'aged_positions') THEN
        SELECT COUNT(*) INTO pos_count FROM monitoring.aged_positions;
        RAISE NOTICE '✓ monitoring.aged_positions: % records', pos_count;
    ELSE
        RAISE WARNING '❌ monitoring.aged_positions not found';
        all_ok := FALSE;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'aged_monitoring_events') THEN
        SELECT COUNT(*) INTO events_count FROM monitoring.aged_monitoring_events;
        RAISE NOTICE '✓ monitoring.aged_monitoring_events: % records', events_count;
    ELSE
        RAISE WARNING '❌ monitoring.aged_monitoring_events not found';
        all_ok := FALSE;
    END IF;

    -- Final verdict
    RAISE NOTICE '=======================================================================';
    IF all_ok THEN
        RAISE NOTICE '✅ ALL MIGRATIONS COMPLETED SUCCESSFULLY!';
    ELSE
        RAISE WARNING '⚠️  MIGRATION INCOMPLETE - Please review warnings above';
    END IF;
    RAISE NOTICE '=======================================================================';
END $$;
