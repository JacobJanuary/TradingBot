-- VERIFICATION QUERY: Current Event Logging Coverage
-- Purpose: Verify which events are actually being logged to database
-- Run this to understand current state before implementing improvements

-- =====================================================
-- 1. CHECK IF EVENTS TABLE EXISTS AND HAS DATA
-- =====================================================
SELECT
    'events' as table_name,
    COUNT(*) as total_records,
    MIN(created_at) as oldest_event,
    MAX(created_at) as newest_event,
    COUNT(DISTINCT event_type) as unique_event_types
FROM monitoring.events;

-- =====================================================
-- 2. EVENT TYPE DISTRIBUTION (LAST 24 HOURS)
-- =====================================================
SELECT
    event_type,
    COUNT(*) as count,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(DISTINCT position_id) as unique_positions,
    MIN(created_at) as first_occurrence,
    MAX(created_at) as last_occurrence,
    ROUND(AVG(EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER (PARTITION BY event_type ORDER BY created_at)))), 2) as avg_interval_seconds
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type
ORDER BY count DESC;

-- =====================================================
-- 3. SEVERITY BREAKDOWN (LAST 24 HOURS)
-- =====================================================
SELECT
    severity,
    COUNT(*) as count,
    COUNT(DISTINCT event_type) as unique_event_types,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY severity
ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'ERROR' THEN 2
        WHEN 'WARNING' THEN 3
        WHEN 'INFO' THEN 4
        ELSE 5
    END;

-- =====================================================
-- 4. CRITICAL/ERROR EVENTS (LAST 24 HOURS)
-- =====================================================
SELECT
    event_type,
    severity,
    COUNT(*) as count,
    ARRAY_AGG(DISTINCT symbol) FILTER (WHERE symbol IS NOT NULL) as affected_symbols,
    MAX(created_at) as last_occurrence
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND severity IN ('CRITICAL', 'ERROR')
GROUP BY event_type, severity
ORDER BY count DESC, last_occurrence DESC;

-- =====================================================
-- 5. EVENTS BY COMPONENT (ESTIMATED)
-- =====================================================
-- Note: This is estimated based on event_type patterns
SELECT
    CASE
        WHEN event_type LIKE 'position_%' THEN 'atomic_position_manager'
        WHEN event_type LIKE 'order_%' THEN 'order_management'
        WHEN event_type LIKE 'stop_loss_%' THEN 'stop_loss_manager'
        WHEN event_type LIKE 'bot_%' THEN 'main'
        WHEN event_type LIKE 'sync_%' THEN 'position_synchronizer'
        WHEN event_type LIKE 'transaction_%' THEN 'database'
        ELSE 'unknown'
    END as component,
    COUNT(*) as event_count,
    COUNT(DISTINCT event_type) as unique_event_types,
    ARRAY_AGG(DISTINCT event_type ORDER BY event_type) as event_types
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY component
ORDER BY event_count DESC;

-- =====================================================
-- 6. MISSING CRITICAL EVENTS CHECK
-- =====================================================
-- Check if critical events from audit are present in last 24h

WITH expected_critical_events AS (
    SELECT unnest(ARRAY[
        'wave_detected',
        'wave_completed',
        'trailing_stop_activated',
        'trailing_stop_updated',
        'phantom_position_closed',
        'zombie_orders_detected',
        'risk_limits_exceeded',
        'position_duplicate_prevented'
    ]) as event_type
),
actual_events AS (
    SELECT DISTINCT event_type
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
)
SELECT
    e.event_type,
    CASE
        WHEN a.event_type IS NOT NULL THEN '✅ Present'
        ELSE '❌ Missing'
    END as status,
    COALESCE(
        (SELECT COUNT(*) FROM monitoring.events
         WHERE event_type = e.event_type
         AND created_at > NOW() - INTERVAL '24 hours'),
        0
    ) as count_24h
FROM expected_critical_events e
LEFT JOIN actual_events a ON e.event_type = a.event_type
ORDER BY status, e.event_type;

-- =====================================================
-- 7. EVENT COVERAGE BY EXCHANGE
-- =====================================================
SELECT
    exchange,
    COUNT(*) as total_events,
    COUNT(DISTINCT event_type) as unique_event_types,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(DISTINCT position_id) FILTER (WHERE position_id IS NOT NULL) as unique_positions
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND exchange IS NOT NULL
GROUP BY exchange
ORDER BY total_events DESC;

-- =====================================================
-- 8. POSITION LIFECYCLE TRACKING
-- =====================================================
-- Check if we can track complete position lifecycle
SELECT
    position_id,
    symbol,
    exchange,
    MIN(created_at) FILTER (WHERE event_type LIKE '%created%' OR event_type LIKE '%opened%') as position_created,
    MAX(created_at) FILTER (WHERE event_type LIKE '%closed%') as position_closed,
    COUNT(DISTINCT event_type) as event_count,
    ARRAY_AGG(DISTINCT event_type ORDER BY event_type) as lifecycle_events
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND position_id IS NOT NULL
GROUP BY position_id, symbol, exchange
HAVING COUNT(*) > 1
ORDER BY MIN(created_at) DESC
LIMIT 10;

-- =====================================================
-- 9. PERFORMANCE METRICS
-- =====================================================
-- Check logging performance and any issues
SELECT
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as events_logged,
    COUNT(DISTINCT event_type) as unique_types,
    ROUND(AVG(LENGTH(event_data::text)), 0) as avg_data_size_bytes,
    COUNT(*) FILTER (WHERE severity IN ('ERROR', 'CRITICAL')) as error_count
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour DESC;

-- =====================================================
-- 10. CORRELATION ANALYSIS
-- =====================================================
-- Check if correlation_id is being used properly
SELECT
    COUNT(DISTINCT correlation_id) as unique_correlations,
    COUNT(*) FILTER (WHERE correlation_id IS NOT NULL) as events_with_correlation,
    COUNT(*) FILTER (WHERE correlation_id IS NULL) as events_without_correlation,
    ROUND(100.0 * COUNT(*) FILTER (WHERE correlation_id IS NOT NULL) / COUNT(*), 2) as correlation_coverage_percent
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Example of correlated events (atomic operations)
SELECT
    correlation_id,
    COUNT(*) as related_events,
    ARRAY_AGG(event_type ORDER BY created_at) as event_sequence,
    MIN(created_at) as operation_start,
    MAX(created_at) as operation_end,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) as duration_seconds
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND correlation_id IS NOT NULL
GROUP BY correlation_id
HAVING COUNT(*) > 1
ORDER BY operation_start DESC
LIMIT 10;

-- =====================================================
-- 11. GAPS IN EVENT STREAM
-- =====================================================
-- Detect periods with no events (potential issues)
WITH event_times AS (
    SELECT
        created_at,
        LAG(created_at) OVER (ORDER BY created_at) as prev_event_time
    FROM monitoring.events
    WHERE created_at > NOW() - INTERVAL '24 hours'
),
gaps AS (
    SELECT
        prev_event_time,
        created_at,
        EXTRACT(EPOCH FROM (created_at - prev_event_time)) as gap_seconds
    FROM event_times
    WHERE prev_event_time IS NOT NULL
      AND EXTRACT(EPOCH FROM (created_at - prev_event_time)) > 300  -- 5+ minute gaps
)
SELECT
    prev_event_time as gap_start,
    created_at as gap_end,
    ROUND(gap_seconds / 60, 2) as gap_duration_minutes,
    'Potential issue or bot downtime' as note
FROM gaps
ORDER BY gap_seconds DESC
LIMIT 10;

-- =====================================================
-- 12. SUMMARY REPORT
-- =====================================================
SELECT
    'Total Events (24h)' as metric,
    COUNT(*)::text as value
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'

UNION ALL

SELECT
    'Unique Event Types',
    COUNT(DISTINCT event_type)::text
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'

UNION ALL

SELECT
    'Unique Symbols',
    COUNT(DISTINCT symbol)::text
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND symbol IS NOT NULL

UNION ALL

SELECT
    'Unique Positions Tracked',
    COUNT(DISTINCT position_id)::text
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND position_id IS NOT NULL

UNION ALL

SELECT
    'Error Rate',
    ROUND(100.0 * COUNT(*) FILTER (WHERE severity IN ('ERROR', 'CRITICAL')) / COUNT(*), 2)::text || '%'
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours'

UNION ALL

SELECT
    'Avg Events per Hour',
    ROUND(COUNT(*)::numeric / 24, 0)::text
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '24 hours';

-- =====================================================
-- INTERPRETATION GUIDE
-- =====================================================
/*
EXPECTED RESULTS BEFORE FULL IMPLEMENTATION:
- Query 1: Should show events table exists with some data
- Query 2: Should show mainly position_* and bot_* events (atomic path only)
- Query 3: Mostly INFO severity (high ERROR/CRITICAL rate is bad)
- Query 4: Should be minimal (atomic path has good error handling)
- Query 5: Should show 'atomic_position_manager' and 'main' only
- Query 6: Should show MANY missing critical events (❌ Missing)
- Query 7: Should show events from configured exchanges
- Query 8: Should show some complete lifecycles (atomic path)
- Query 9: Should show consistent logging with no gaps
- Query 10: Should show correlation usage in atomic operations
- Query 11: Should show NO large gaps (bot running continuously)
- Query 12: Summary should show low diversity of event types

EXPECTED RESULTS AFTER FULL IMPLEMENTATION:
- Query 2: Should show 30+ unique event types
- Query 5: Should show 6-8 components logging events
- Query 6: Should show ✅ Present for most critical events
- Query 8: Should show rich lifecycle with 10+ events per position
- Query 10: Should show high correlation coverage (>80%)
- Query 12: Should show 150-200+ unique event types

TROUBLESHOOTING:
- No events at all: EventLogger not initialized in main.py
- Only position_* events: Other components not instrumented yet
- Large gaps in Query 11: Bot crashed or stopped
- High error rate in Query 3: System issues, investigate errors
- Low correlation coverage: Need to add correlation_id to more operations
*/
