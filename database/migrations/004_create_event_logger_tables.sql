-- =====================================================
-- Migration 004: Create EventLogger Tables
-- =====================================================
-- Date: 2025-10-14
-- Purpose: Enable comprehensive event audit trail
-- Dependencies: Schema 'monitoring' must exist
-- Safety: Creates new tables, does NOT modify existing tables
-- =====================================================

BEGIN;

-- Pre-checks
DO $$
BEGIN
    -- Verify monitoring schema exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'monitoring') THEN
        RAISE EXCEPTION 'Schema monitoring does not exist';
    END IF;

    -- Verify events table does NOT already exist
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'events') THEN
        RAISE NOTICE 'Table monitoring.events already exists, skipping creation';
    END IF;

    -- Verify old performance_metrics exists (safety check)
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'performance_metrics') THEN
        RAISE WARNING 'Original monitoring.performance_metrics table not found';
    END IF;
END $$;

-- =====================================================
-- TABLE 1: monitoring.events (CRITICAL)
-- =====================================================
-- Purpose: Comprehensive audit trail for all bot operations
-- Expected load: ~240 events/hour, ~5,760 events/day
-- Retention: Should be rotated/archived after 30-90 days

CREATE TABLE IF NOT EXISTS monitoring.events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    correlation_id VARCHAR(100),
    position_id INTEGER,  -- Soft FK to monitoring.positions.id
    order_id VARCHAR(100),
    symbol VARCHAR(50),
    exchange VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'INFO',
    error_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_events_type ON monitoring.events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON monitoring.events (correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_position ON monitoring.events (position_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON monitoring.events (created_at DESC);

-- Additional useful indexes
CREATE INDEX IF NOT EXISTS idx_events_symbol ON monitoring.events (symbol) WHERE symbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_exchange ON monitoring.events (exchange) WHERE exchange IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_severity ON monitoring.events (severity);

-- Partial index for errors only (faster error queries)
CREATE INDEX IF NOT EXISTS idx_events_errors ON monitoring.events (created_at DESC)
    WHERE severity IN ('ERROR', 'CRITICAL');

-- Comment
COMMENT ON TABLE monitoring.events IS 'Event audit trail for all critical bot operations. Stores 69 event types across 7 components.';
COMMENT ON COLUMN monitoring.events.event_type IS 'Type from EventType enum (e.g., position_created, stop_loss_placed, wave_detected)';
COMMENT ON COLUMN monitoring.events.event_data IS 'JSONB payload with event-specific data';
COMMENT ON COLUMN monitoring.events.correlation_id IS 'Groups related events in atomic operations';
COMMENT ON COLUMN monitoring.events.position_id IS 'Soft FK to monitoring.positions.id (no constraint)';
COMMENT ON COLUMN monitoring.events.severity IS 'INFO, WARNING, ERROR, or CRITICAL';

-- =====================================================
-- TABLE 2: monitoring.transaction_log (LOW PRIORITY)
-- =====================================================
-- Purpose: Database transaction performance tracking
-- Expected load: Very low (not used in production yet)
-- Status: Reserved for future use

CREATE TABLE IF NOT EXISTS monitoring.transaction_log (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) UNIQUE,
    operation VARCHAR(100),
    status VARCHAR(20),  -- success, failed, pending
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    affected_rows INTEGER,
    error_message TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tx_log_id ON monitoring.transaction_log (transaction_id);
CREATE INDEX IF NOT EXISTS idx_tx_log_status ON monitoring.transaction_log (status);
CREATE INDEX IF NOT EXISTS idx_tx_log_started ON monitoring.transaction_log (started_at DESC);

-- Comment
COMMENT ON TABLE monitoring.transaction_log IS 'Database transaction performance tracking. Currently unused in production.';

-- =====================================================
-- TABLE 3: monitoring.event_performance_metrics (LOW PRIORITY)
-- =====================================================
-- Purpose: Real-time EventLogger performance metrics
-- Expected load: Very low (not used in production yet)
-- Status: Reserved for future use
--
-- NOTE: Original name was 'performance_metrics' but that name is already
--       used by trading statistics table (database/init.sql:109-123).
--       This table has been renamed to 'event_performance_metrics' to
--       avoid naming conflict.

CREATE TABLE IF NOT EXISTS monitoring.event_performance_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    metric_value DECIMAL(20, 8),
    tags JSONB,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_event_metrics_name ON monitoring.event_performance_metrics (metric_name);
CREATE INDEX IF NOT EXISTS idx_event_metrics_time ON monitoring.event_performance_metrics (recorded_at DESC);

-- Comment
COMMENT ON TABLE monitoring.event_performance_metrics IS 'Real-time EventLogger performance metrics. Currently unused in production.';
COMMENT ON COLUMN monitoring.event_performance_metrics.tags IS 'JSONB for flexible metric dimensions (e.g., {"exchange": "bybit"})';

-- =====================================================
-- POST-MIGRATION VERIFICATION
-- =====================================================

DO $$
DECLARE
    events_count INTEGER;
    tx_log_count INTEGER;
    metrics_count INTEGER;
    old_perf_count INTEGER;
BEGIN
    -- Verify tables created
    SELECT COUNT(*) INTO events_count
    FROM information_schema.tables
    WHERE table_schema = 'monitoring' AND table_name = 'events';

    SELECT COUNT(*) INTO tx_log_count
    FROM information_schema.tables
    WHERE table_schema = 'monitoring' AND table_name = 'transaction_log';

    SELECT COUNT(*) INTO metrics_count
    FROM information_schema.tables
    WHERE table_schema = 'monitoring' AND table_name = 'event_performance_metrics';

    IF events_count = 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: monitoring.events was not created';
    END IF;

    IF tx_log_count = 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: monitoring.transaction_log was not created';
    END IF;

    IF metrics_count = 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: monitoring.event_performance_metrics was not created';
    END IF;

    -- Verify old performance_metrics still has data
    SELECT COUNT(*) INTO old_perf_count
    FROM monitoring.performance_metrics;

    IF old_perf_count < 32 THEN
        RAISE WARNING 'ATTENTION: monitoring.performance_metrics has fewer records than expected (found %, expected >= 32)', old_perf_count;
    END IF;

    -- Success message
    RAISE NOTICE '✅ Migration 004 completed successfully!';
    RAISE NOTICE '   - monitoring.events: CREATED';
    RAISE NOTICE '   - monitoring.transaction_log: CREATED';
    RAISE NOTICE '   - monitoring.event_performance_metrics: CREATED';
    RAISE NOTICE '   - monitoring.performance_metrics: INTACT (% records)', old_perf_count;
END $$;

COMMIT;

-- =====================================================
-- ROLLBACK INSTRUCTIONS
-- =====================================================
-- If you need to rollback this migration, run:
--
-- BEGIN;
-- DROP TABLE IF EXISTS monitoring.events CASCADE;
-- DROP TABLE IF EXISTS monitoring.transaction_log CASCADE;
-- DROP TABLE IF EXISTS monitoring.event_performance_metrics CASCADE;
-- COMMIT;
--
-- WARNING: This will permanently delete all event audit data!
-- =====================================================
