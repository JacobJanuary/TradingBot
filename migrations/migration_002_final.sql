-- =====================================================================
-- MIGRATION 002: Convert all timestamps to UTC (timestamptz)
-- =====================================================================
-- Based on actual database schema - 18 columns in 10 tables
-- =====================================================================

BEGIN;

-- 1. monitoring.positions (5 columns)
ALTER TABLE monitoring.positions
    ALTER COLUMN opened_at TYPE timestamptz USING opened_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN closed_at TYPE timestamptz USING closed_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN last_error_at TYPE timestamptz USING last_error_at AT TIME ZONE 'Europe/Moscow';

-- 2. monitoring.trades (2 columns)
ALTER TABLE monitoring.trades
    ALTER COLUMN executed_at TYPE timestamptz USING executed_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow';

-- 3. monitoring.orders (2 columns)
ALTER TABLE monitoring.orders
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow';

-- 4. monitoring.aged_positions (2 columns)
ALTER TABLE monitoring.aged_positions
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow';

-- 5. monitoring.aged_monitoring_events (1 column)
ALTER TABLE monitoring.aged_monitoring_events
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow';

-- 6. monitoring.risk_events (1 column)
ALTER TABLE monitoring.risk_events
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow';

-- 7. monitoring.risk_violations (1 column - named "timestamp", not created_at)
ALTER TABLE monitoring.risk_violations
    ALTER COLUMN timestamp TYPE timestamptz USING timestamp AT TIME ZONE 'Europe/Moscow';

-- 8. monitoring.orders_cache (1 column)
ALTER TABLE monitoring.orders_cache
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow';

-- 9. monitoring.performance_metrics (1 column)
ALTER TABLE monitoring.performance_metrics
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow';

-- 10. fas.scoring_history (2 columns)
ALTER TABLE fas.scoring_history
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN processed_at TYPE timestamptz USING processed_at AT TIME ZONE 'Europe/Moscow';

-- Update DEFAULT values for created_at/opened_at columns
ALTER TABLE monitoring.positions
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN opened_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.orders
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.orders_cache
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.aged_positions
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.aged_monitoring_events
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.risk_events
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.risk_violations
    ALTER COLUMN timestamp SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.performance_metrics
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE fas.scoring_history
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- Verification
DO $$
DECLARE
    wrong_types_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO wrong_types_count
    FROM information_schema.columns
    WHERE table_schema IN ('monitoring', 'trading', 'fas')
      AND column_name IN ('created_at', 'updated_at', 'opened_at', 'closed_at',
                          'executed_at', 'timestamp', 'acknowledged_at',
                          'last_update', 'last_error_at', 'received_at', 'processed_at')
      AND data_type = 'timestamp without time zone';

    IF wrong_types_count > 0 THEN
        RAISE EXCEPTION 'Found % columns still using "timestamp without time zone"!',
                        wrong_types_count;
    END IF;

    RAISE NOTICE '✓ Verification passed: All 18 timestamp columns converted to timestamptz';
END $$;

COMMIT;

DO $$ BEGIN
    RAISE NOTICE '==============================================================';
    RAISE NOTICE 'Migration 002 completed successfully!';
    RAISE NOTICE 'Converted 18 timestamp columns → timestamptz in 10 tables';
    RAISE NOTICE '==============================================================';
    RAISE NOTICE '';
    RAISE NOTICE '⚠️  NEXT STEP: Run separately:';
    RAISE NOTICE '   ALTER DATABASE fox_crypto SET timezone TO ''UTC'';';
END $$;
