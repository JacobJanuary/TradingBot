-- =====================================================================
-- MIGRATION 002: Convert all timestamps to UTC (timestamptz)
-- =====================================================================
-- Simplified version without intermediate notices
-- =====================================================================

BEGIN;

-- 1. monitoring.positions (5 columns - last_update doesn't exist based on pre-check)
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

-- 7. monitoring.alerts (2 columns)
ALTER TABLE monitoring.alerts
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN acknowledged_at TYPE timestamptz USING acknowledged_at AT TIME ZONE 'Europe/Moscow';

-- 8. monitoring.performance_metrics (1 column based on pre-check, not "performance")
-- Check actual table name first
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'monitoring' AND table_name = 'performance_metrics') THEN
        EXECUTE 'ALTER TABLE monitoring.performance_metrics
                 ALTER COLUMN timestamp TYPE timestamptz USING timestamp AT TIME ZONE ''Europe/Moscow''';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'monitoring' AND table_name = 'performance') THEN
        EXECUTE 'ALTER TABLE monitoring.performance
                 ALTER COLUMN timestamp TYPE timestamptz USING timestamp AT TIME ZONE ''Europe/Moscow''';
    END IF;
END $$;

-- 9. trading.stop_loss_configs (2 columns - might not exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'trading' AND table_name = 'stop_loss_configs') THEN
        EXECUTE 'ALTER TABLE trading.stop_loss_configs
                 ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE ''Europe/Moscow'',
                 ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE ''Europe/Moscow''';
    END IF;
END $$;

-- 10. fas.signals (2 columns - might not exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'fas' AND table_name = 'signals') THEN
        EXECUTE 'ALTER TABLE fas.signals
                 ALTER COLUMN received_at TYPE timestamptz USING received_at AT TIME ZONE ''Europe/Moscow'',
                 ALTER COLUMN processed_at TYPE timestamptz USING processed_at AT TIME ZONE ''Europe/Moscow''';
    END IF;
END $$;

-- 11. fas.candles (1 column - might not exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'fas' AND table_name = 'candles') THEN
        EXECUTE 'ALTER TABLE fas.candles
                 ALTER COLUMN timestamp TYPE timestamptz USING timestamp AT TIME ZONE ''Europe/Moscow''';
    END IF;
END $$;

-- 12. Update DEFAULT values
ALTER TABLE monitoring.positions
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN opened_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.orders
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.aged_positions
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.aged_monitoring_events
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.risk_events
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE monitoring.alerts
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- 13. Verification
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

    RAISE NOTICE 'Verification: All timestamp columns converted to timestamptz ✓';
END $$;

COMMIT;

DO $$ BEGIN
    RAISE NOTICE '==============================================================';
    RAISE NOTICE 'Migration 002 completed successfully!';
    RAISE NOTICE 'All timestamp columns converted: timestamp → timestamptz';
    RAISE NOTICE '==============================================================';
    RAISE NOTICE '';
    RAISE NOTICE '⚠️  NEXT STEP: Run separately:';
    RAISE NOTICE '   ALTER DATABASE fox_crypto SET timezone TO ''UTC'';';
    RAISE NOTICE '   Then reconnect to the database.';
END $$;
