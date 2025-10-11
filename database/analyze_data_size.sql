-- Analyze size of monitoring schema data
-- Run: psql $DATABASE_URL < database/analyze_data_size.sql

\echo '================================================'
\echo '📊 MONITORING SCHEMA SIZE ANALYSIS'
\echo '================================================'

-- Total schema size
SELECT
    'monitoring' as schema_name,
    pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))::bigint) as total_size,
    COUNT(DISTINCT tablename) as table_count
FROM pg_tables
WHERE schemaname = 'monitoring'
GROUP BY schemaname;

\echo ''
\echo '📋 TABLE SIZES:'
\echo '---------------'

-- Size per table
SELECT
    schemaname||'.'||tablename AS table_full_name,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS index_size
FROM pg_tables
WHERE schemaname = 'monitoring'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

\echo ''
\echo '📊 ROW COUNTS:'
\echo '--------------'

-- Row counts
SELECT 'monitoring.positions' as table_name, COUNT(*) as row_count FROM monitoring.positions
UNION ALL
SELECT 'monitoring.orders', COUNT(*) FROM monitoring.orders
UNION ALL
SELECT 'monitoring.trades', COUNT(*) FROM monitoring.trades
UNION ALL
SELECT 'monitoring.risk_events', COUNT(*) FROM monitoring.risk_events
UNION ALL
SELECT 'monitoring.performance_metrics', COUNT(*) FROM monitoring.performance_metrics
ORDER BY row_count DESC;

\echo ''
\echo '🔍 POSITIONS BREAKDOWN:'
\echo '----------------------'

-- Positions status breakdown
SELECT
    status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
FROM monitoring.positions
GROUP BY status
ORDER BY count DESC;

\echo ''
\echo '⚠️ DATA QUALITY ISSUES:'
\echo '-----------------------'

-- Check for data issues
SELECT
    'Positions without stop-loss' as issue,
    COUNT(*) as count
FROM monitoring.positions
WHERE status = 'active' AND stop_loss_price IS NULL
UNION ALL
SELECT
    'Positions with truncated exit_reason',
    COUNT(*)
FROM monitoring.positions
WHERE LENGTH(exit_reason) = 100  -- Exactly at limit = likely truncated
UNION ALL
SELECT
    'Positions not synced in >1 hour',
    COUNT(*)
FROM monitoring.positions
WHERE status = 'active'
    AND last_sync_at < NOW() - INTERVAL '1 hour'
ORDER BY count DESC;

\echo ''
\echo '💾 BACKUP ESTIMATES:'
\echo '-------------------'

-- Backup size estimate
SELECT
    'Compressed backup size' as metric,
    pg_size_pretty((SUM(pg_total_relation_size(schemaname||'.'||tablename)) * 0.2)::bigint) as estimate
FROM pg_tables
WHERE schemaname = 'monitoring'
UNION ALL
SELECT
    'Backup time estimate',
    CASE
        WHEN SUM(pg_total_relation_size(schemaname||'.'||tablename)) < 10485760 THEN '< 1 second'
        WHEN SUM(pg_total_relation_size(schemaname||'.'||tablename)) < 104857600 THEN '1-5 seconds'
        WHEN SUM(pg_total_relation_size(schemaname||'.'||tablename)) < 1073741824 THEN '5-30 seconds'
        ELSE '> 30 seconds'
    END
FROM pg_tables
WHERE schemaname = 'monitoring';

\echo ''
\echo '================================================'