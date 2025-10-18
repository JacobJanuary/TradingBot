-- POST-TEST COMPREHENSIVE ANALYSIS
-- Run this after 8-hour production test to get complete picture
-- Usage: psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -f post_test_analysis.sql

\echo '================================================================================'
\echo 'POST-TEST COMPREHENSIVE ANALYSIS'
\echo '================================================================================'
\echo ''

-- Set timezone for consistent timestamps
SET timezone = 'UTC';

\echo '================================================================================'
\echo '1. POSITIONS SUMMARY'
\echo '================================================================================'
\echo ''

SELECT
    'Total positions opened (8h)' as metric,
    COUNT(*) as value
FROM monitoring.positions
WHERE opened_at > NOW() - INTERVAL '8 hours'

UNION ALL

SELECT
    'Total positions closed (8h)' as metric,
    COUNT(*) as value
FROM monitoring.positions
WHERE closed_at > NOW() - INTERVAL '8 hours'

UNION ALL

SELECT
    'Currently active' as metric,
    COUNT(*) as value
FROM monitoring.positions
WHERE status IN ('active', 'trailing')

UNION ALL

SELECT
    'Positions without SL (ever)' as metric,
    COUNT(DISTINCT position_id) as value
FROM monitoring.events
WHERE event_type = 'sl_missing'
  AND created_at > NOW() - INTERVAL '8 hours';

\echo ''
\echo 'By Exchange:'
\echo ''

SELECT
    exchange,
    status,
    COUNT(*) as count
FROM monitoring.positions
WHERE opened_at > NOW() - INTERVAL '8 hours'
GROUP BY exchange, status
ORDER BY exchange, status;

\echo ''
\echo '================================================================================'
\echo '2. STOP LOSS ANALYSIS'
\echo '================================================================================'
\echo ''

SELECT
    COALESCE(event_data->>'exchange', exchange, 'unknown') as exchange,
    COUNT(*) FILTER (WHERE event_type = 'stop_loss_set') as sl_set,
    COUNT(*) FILTER (WHERE event_type = 'stop_loss_updated') as sl_updated,
    COUNT(*) FILTER (WHERE event_type = 'stop_loss_triggered') as sl_triggered,
    COUNT(*) FILTER (WHERE event_type = 'sl_missing') as sl_missing
FROM monitoring.events
WHERE (event_type LIKE '%stop_loss%' OR event_type = 'sl_missing')
  AND created_at > NOW() - INTERVAL '8 hours'
GROUP BY COALESCE(event_data->>'exchange', exchange, 'unknown');

\echo ''
\echo 'Positions with missing SL (detailed):'
\echo ''

SELECT
    p.id,
    p.symbol,
    p.exchange,
    p.opened_at,
    e.created_at as sl_missing_detected,
    EXTRACT(EPOCH FROM (e.created_at - p.opened_at)) as seconds_without_sl
FROM monitoring.events e
INNER JOIN monitoring.positions p ON e.position_id = p.id
WHERE e.event_type = 'sl_missing'
  AND e.created_at > NOW() - INTERVAL '8 hours'
ORDER BY seconds_without_sl DESC
LIMIT 20;

\echo ''
\echo '================================================================================'
\echo '3. TRAILING STOP ANALYSIS'
\echo '================================================================================'
\echo ''

WITH ts_stats AS (
    SELECT
        'TS Activations' as metric,
        COUNT(*) as value
    FROM monitoring.events
    WHERE event_type = 'trailing_stop_activated'
      AND created_at > NOW() - INTERVAL '8 hours'

    UNION ALL

    SELECT
        'TS Updates' as metric,
        COUNT(*) as value
    FROM monitoring.events
    WHERE event_type = 'trailing_stop_updated'
      AND created_at > NOW() - INTERVAL '8 hours'
)
SELECT * FROM ts_stats;

\echo ''
\echo 'Avg updates per activated position:'
\echo ''

SELECT
    ROUND(AVG(update_count), 2) as avg_updates_per_position,
    MAX(update_count) as max_updates,
    MIN(update_count) as min_updates
FROM (
    SELECT
        position_id,
        COUNT(*) as update_count
    FROM monitoring.events
    WHERE event_type = 'trailing_stop_updated'
      AND created_at > NOW() - INTERVAL '8 hours'
    GROUP BY position_id
) sub;

\echo ''
\echo 'Positions with excessive TS updates (>20):'
\echo ''

SELECT
    p.symbol,
    p.exchange,
    COUNT(*) as update_count,
    MIN(e.created_at) as first_update,
    MAX(e.created_at) as last_update,
    EXTRACT(EPOCH FROM (MAX(e.created_at) - MIN(e.created_at)))/60 as duration_minutes,
    ROUND(COUNT(*) / NULLIF(EXTRACT(EPOCH FROM (MAX(e.created_at) - MIN(e.created_at)))/60, 0), 2) as updates_per_minute
FROM monitoring.events e
INNER JOIN monitoring.positions p ON e.position_id = p.id
WHERE e.event_type = 'trailing_stop_updated'
  AND e.created_at > NOW() - INTERVAL '8 hours'
GROUP BY p.id, p.symbol, p.exchange
HAVING COUNT(*) > 20
ORDER BY update_count DESC
LIMIT 20;

\echo ''
\echo '================================================================================'
\echo '4. ERRORS AND ISSUES'
\echo '================================================================================'
\echo ''

SELECT
    event_type,
    COUNT(*) as count
FROM monitoring.events
WHERE (event_type LIKE '%error%'
       OR event_type LIKE '%failed%'
       OR event_type IN ('emergency_close', 'rollback', 'zombie_detected'))
  AND created_at > NOW() - INTERVAL '8 hours'
GROUP BY event_type
ORDER BY count DESC;

\echo ''
\echo 'Errors by exchange:'
\echo ''

SELECT
    COALESCE(event_data->>'exchange', 'unknown') as exchange,
    COALESCE(event_data->>'error_type', event_type) as error_type,
    COUNT(*) as count,
    MIN(created_at) as first_occurrence,
    MAX(created_at) as last_occurrence
FROM monitoring.events
WHERE event_type LIKE '%error%'
  AND created_at > NOW() - INTERVAL '8 hours'
GROUP BY exchange, error_type
ORDER BY count DESC
LIMIT 20;

\echo ''
\echo '================================================================================'
\echo '5. PERFORMANCE METRICS'
\echo '================================================================================'
\echo ''

SELECT
    event_type,
    COUNT(*) as operations,
    ROUND(AVG((event_data->>'duration_ms')::float), 2) as avg_ms,
    ROUND(MAX((event_data->>'duration_ms')::float), 2) as max_ms,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (event_data->>'duration_ms')::float), 2) as median_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY (event_data->>'duration_ms')::float), 2) as p95_ms,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY (event_data->>'duration_ms')::float), 2) as p99_ms
FROM monitoring.events
WHERE event_data->>'duration_ms' IS NOT NULL
  AND created_at > NOW() - INTERVAL '8 hours'
GROUP BY event_type
ORDER BY avg_ms DESC;

\echo ''
\echo '================================================================================'
\echo '6. AGED POSITIONS'
\echo '================================================================================'
\echo ''

SELECT
    id,
    symbol,
    exchange,
    opened_at,
    ROUND(EXTRACT(EPOCH FROM (NOW() - opened_at))/3600, 2) as hours_open,
    status,
    ROUND(pnl_usdt::numeric, 2) as pnl_usdt,
    ROUND(pnl_percent::numeric, 2) as pnl_percent
FROM monitoring.positions
WHERE opened_at < NOW() - INTERVAL '3 hours'
  AND (status IN ('active', 'trailing') OR closed_at > NOW() - INTERVAL '8 hours')
ORDER BY hours_open DESC
LIMIT 20;

\echo ''
\echo '================================================================================'
\echo '7. ZOMBIE ORDERS'
\echo '================================================================================'
\echo ''

SELECT
    COALESCE(event_data->>'exchange', 'unknown') as exchange,
    COALESCE(event_data->>'reason', 'unknown') as reason,
    COUNT(*) as count
FROM monitoring.events
WHERE event_type = 'zombie_cleaned'
  AND created_at > NOW() - INTERVAL '8 hours'
GROUP BY exchange, reason
ORDER BY count DESC;

\echo ''
\echo '================================================================================'
\echo '8. PNL SUMMARY'
\echo '================================================================================'
\echo ''

SELECT
    exchange,
    COUNT(*) as positions_closed,
    COUNT(*) FILTER (WHERE pnl_usdt > 0) as winners,
    COUNT(*) FILTER (WHERE pnl_usdt < 0) as losers,
    COUNT(*) FILTER (WHERE pnl_usdt = 0) as breakeven,
    ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_usdt > 0) / NULLIF(COUNT(*), 0), 2) as win_rate_pct,
    ROUND(SUM(pnl_usdt)::numeric, 2) as total_pnl_usdt,
    ROUND(AVG(pnl_usdt)::numeric, 2) as avg_pnl_usdt,
    ROUND(MAX(pnl_usdt)::numeric, 2) as max_profit,
    ROUND(MIN(pnl_usdt)::numeric, 2) as max_loss,
    ROUND(AVG(pnl_percent)::numeric, 2) as avg_pnl_pct
FROM monitoring.positions
WHERE closed_at > NOW() - INTERVAL '8 hours'
GROUP BY exchange

UNION ALL

SELECT
    'TOTAL' as exchange,
    COUNT(*),
    COUNT(*) FILTER (WHERE pnl_usdt > 0),
    COUNT(*) FILTER (WHERE pnl_usdt < 0),
    COUNT(*) FILTER (WHERE pnl_usdt = 0),
    ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_usdt > 0) / NULLIF(COUNT(*), 0), 2),
    ROUND(SUM(pnl_usdt)::numeric, 2),
    ROUND(AVG(pnl_usdt)::numeric, 2),
    ROUND(MAX(pnl_usdt)::numeric, 2),
    ROUND(MIN(pnl_usdt)::numeric, 2),
    ROUND(AVG(pnl_percent)::numeric, 2)
FROM monitoring.positions
WHERE closed_at > NOW() - INTERVAL '8 hours';

\echo ''
\echo '================================================================================'
\echo '9. WEBSOCKET HEALTH'
\echo '================================================================================'
\echo ''

SELECT
    event_type,
    COUNT(*) as count
FROM monitoring.events
WHERE (event_type LIKE '%websocket%' OR event_type LIKE '%ws_%')
  AND created_at > NOW() - INTERVAL '8 hours'
GROUP BY event_type
ORDER BY count DESC;

\echo ''
\echo '================================================================================'
\echo '10. RACE CONDITIONS DETECTION'
\echo '================================================================================'
\echo ''
\echo 'Operations within 1 second on same position:'
\echo ''

WITH concurrent_ops AS (
    SELECT
        position_id,
        event_type,
        timestamp,
        LAG(event_type) OVER (PARTITION BY position_id ORDER BY created_at) as prev_event,
        LAG(timestamp) OVER (PARTITION BY position_id ORDER BY created_at) as prev_timestamp,
        timestamp - LAG(timestamp) OVER (PARTITION BY position_id ORDER BY created_at) as time_diff
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '8 hours'
)
SELECT
    position_id,
    prev_event,
    event_type,
    prev_timestamp,
    timestamp,
    EXTRACT(EPOCH FROM time_diff) as seconds_between
FROM concurrent_ops
WHERE EXTRACT(EPOCH FROM time_diff) < 1
  AND prev_event IS NOT NULL
ORDER BY seconds_between
LIMIT 30;

\echo ''
\echo '================================================================================'
\echo '11. HOURLY ACTIVITY DISTRIBUTION'
\echo '================================================================================'
\echo ''

SELECT
    DATE_TRUNC('hour', opened_at) as hour,
    COUNT(*) as positions_opened,
    COUNT(*) FILTER (WHERE has_stop_loss = false) as without_sl
FROM monitoring.positions
WHERE opened_at > NOW() - INTERVAL '8 hours'
GROUP BY DATE_TRUNC('hour', opened_at)
ORDER BY hour;

\echo ''
\echo '================================================================================'
\echo '12. CRITICAL EVENTS TIMELINE'
\echo '================================================================================'
\echo ''

SELECT
    timestamp,
    event_type,
    position_id,
    COALESCE(event_data->>'exchange', 'unknown') as exchange,
    COALESCE(event_data->>'symbol', 'unknown') as symbol,
    details
FROM monitoring.events
WHERE event_type IN (
    'emergency_close',
    'rollback',
    'sl_missing',
    'zombie_detected',
    'api_error',
    'websocket_disconnected'
)
  AND created_at > NOW() - INTERVAL '8 hours'
ORDER BY created_at DESC
LIMIT 50;

\echo ''
\echo '================================================================================'
\echo '13. POSITION LIFECYCLE DETAILS (Sample)'
\echo '================================================================================'
\echo ''
\echo 'Complete event history for 5 random positions:'
\echo ''

WITH sample_positions AS (
    SELECT id
    FROM monitoring.positions
    WHERE opened_at > NOW() - INTERVAL '8 hours'
    ORDER BY RANDOM()
    LIMIT 5
)
SELECT
    e.position_id,
    p.symbol,
    p.exchange,
    e.created_at,
    e.event_type,
    e.event_data
FROM monitoring.events e
INNER JOIN monitoring.positions p ON e.position_id = p.id
INNER JOIN sample_positions sp ON e.position_id = sp.id
WHERE e.created_at > NOW() - INTERVAL '8 hours'
ORDER BY e.position_id, e.created_at;

\echo ''
\echo '================================================================================'
\echo '14. DATABASE HEALTH'
\echo '================================================================================'
\echo ''

SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    n_tup_ins as rows_inserted,
    n_tup_upd as rows_updated,
    n_tup_del as rows_deleted
FROM pg_stat_user_tables
WHERE schemaname = 'monitoring'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

\echo ''
\echo '================================================================================'
\echo 'ANALYSIS COMPLETE'
\echo '================================================================================'
\echo ''
\echo 'Next steps:'
\echo '1. Review all sections above'
\echo '2. Investigate any anomalies or high error counts'
\echo '3. Analyze race conditions if any found'
\echo '4. Check PnL performance'
\echo '5. Review aged positions and zombie orders'
\echo ''
\echo 'Save this output for audit report creation'
\echo '================================================================================'
