-- =====================================================================
-- MIGRATION 002: Convert all timestamps to UTC (timestamptz)
-- =====================================================================
-- Date: 2025-10-24
-- Purpose: Convert all timestamp columns to timestamptz and set DB timezone to UTC
--
-- Current state:
--   - Database timezone: Europe/Moscow (UTC+3)
--   - 11 tables with "timestamp without time zone" columns (21 total columns)
--
-- Target state:
--   - Database timezone: UTC
--   - All timestamps as "timestamp with time zone" (timestamptz)
--   - Existing data converted: Moscow time → UTC time
--
-- ВАЖНО: Выполнять когда бот остановлен!
-- =====================================================================

-- Начало транзакции
BEGIN;

-- =====================================================================
-- 1. Backup текущей timezone и проверка
-- =====================================================================
DO $$
DECLARE
    current_tz TEXT;
BEGIN
    SHOW timezone INTO current_tz;
    RAISE NOTICE 'Current database timezone: %', current_tz;

    IF current_tz != 'Europe/Moscow' THEN
        RAISE WARNING 'Expected timezone "Europe/Moscow", got "%"', current_tz;
    END IF;
END $$;

-- =====================================================================
-- 2. Конвертация monitoring.positions (6 timestamp columns)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.positions...';

ALTER TABLE monitoring.positions
    ALTER COLUMN opened_at TYPE timestamptz USING opened_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN closed_at TYPE timestamptz USING closed_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN last_error_at TYPE timestamptz USING last_error_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN last_update TYPE timestamptz USING last_update AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.positions converted';

-- =====================================================================
-- 3. Конвертация monitoring.trades (2 timestamp columns)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.trades...';

ALTER TABLE monitoring.trades
    ALTER COLUMN executed_at TYPE timestamptz USING executed_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.trades converted';

-- =====================================================================
-- 4. Конвертация monitoring.orders (2 timestamp columns)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.orders...';

ALTER TABLE monitoring.orders
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.orders converted';

-- =====================================================================
-- 5. Конвертация monitoring.aged_positions (2 timestamp columns)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.aged_positions...';

ALTER TABLE monitoring.aged_positions
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.aged_positions converted';

-- =====================================================================
-- 6. Конвертация monitoring.aged_monitoring_events (1 timestamp column)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.aged_monitoring_events...';

ALTER TABLE monitoring.aged_monitoring_events
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.aged_monitoring_events converted';

-- =====================================================================
-- 7. Конвертация monitoring.risk_events (1 timestamp column)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.risk_events...';

ALTER TABLE monitoring.risk_events
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.risk_events converted';

-- =====================================================================
-- 8. Конвертация monitoring.alerts (2 timestamp columns)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.alerts...';

ALTER TABLE monitoring.alerts
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN acknowledged_at TYPE timestamptz USING acknowledged_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.alerts converted';

-- =====================================================================
-- 9. Конвертация monitoring.performance (1 timestamp column)
-- =====================================================================
RAISE NOTICE 'Converting monitoring.performance...';

ALTER TABLE monitoring.performance
    ALTER COLUMN timestamp TYPE timestamptz USING timestamp AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ monitoring.performance converted';

-- =====================================================================
-- 10. Конвертация trading.stop_loss_configs (2 timestamp columns)
-- =====================================================================
RAISE NOTICE 'Converting trading.stop_loss_configs...';

ALTER TABLE trading.stop_loss_configs
    ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ trading.stop_loss_configs converted';

-- =====================================================================
-- 11. Конвертация fas.signals (2 timestamp columns)
-- =====================================================================
RAISE NOTICE 'Converting fas.signals...';

ALTER TABLE fas.signals
    ALTER COLUMN received_at TYPE timestamptz USING received_at AT TIME ZONE 'Europe/Moscow',
    ALTER COLUMN processed_at TYPE timestamptz USING processed_at AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ fas.signals converted';

-- =====================================================================
-- 12. Конвертация fas.candles (1 timestamp column)
-- =====================================================================
RAISE NOTICE 'Converting fas.candles...';

ALTER TABLE fas.candles
    ALTER COLUMN timestamp TYPE timestamptz USING timestamp AT TIME ZONE 'Europe/Moscow';

RAISE NOTICE '✓ fas.candles converted';

-- =====================================================================
-- 13. Обновление DEFAULT значений для created_at/updated_at
-- =====================================================================
RAISE NOTICE 'Updating DEFAULT values to use CURRENT_TIMESTAMP...';

-- monitoring.positions
ALTER TABLE monitoring.positions
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN opened_at SET DEFAULT CURRENT_TIMESTAMP;

-- monitoring.trades (created_at уже есть default func.now())
-- monitoring.orders
ALTER TABLE monitoring.orders
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- monitoring.aged_positions
ALTER TABLE monitoring.aged_positions
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- monitoring.aged_monitoring_events
ALTER TABLE monitoring.aged_monitoring_events
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- monitoring.risk_events
ALTER TABLE monitoring.risk_events
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- monitoring.alerts
ALTER TABLE monitoring.alerts
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- monitoring.performance
ALTER TABLE monitoring.performance
    ALTER COLUMN timestamp SET DEFAULT CURRENT_TIMESTAMP;

-- trading.stop_loss_configs
ALTER TABLE trading.stop_loss_configs
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

-- fas.signals
ALTER TABLE fas.signals
    ALTER COLUMN received_at SET DEFAULT CURRENT_TIMESTAMP;

RAISE NOTICE '✓ DEFAULT values updated';

-- =====================================================================
-- 14. Верификация конвертации
-- =====================================================================
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

-- Коммит транзакции
COMMIT;

RAISE NOTICE '==============================================================';
RAISE NOTICE 'Migration 002 completed successfully!';
RAISE NOTICE 'All 21 timestamp columns converted: timestamp → timestamptz';
RAISE NOTICE 'Existing data converted from Europe/Moscow to UTC';
RAISE NOTICE '==============================================================';

-- =====================================================================
-- 15. Изменение timezone базы данных на UTC
-- =====================================================================
-- ВАЖНО: Эта команда не может быть выполнена внутри транзакции!
-- Выполните её отдельно после успешного завершения миграции:
--
-- ALTER DATABASE fox_crypto SET timezone TO 'UTC';
--
-- Затем переподключитесь к базе данных для применения изменений.
-- =====================================================================

\echo '⚠️  IMPORTANT: After this migration, run separately:'
\echo '⚠️  ALTER DATABASE fox_crypto SET timezone TO ''UTC'';'
\echo '⚠️  Then reconnect to the database.'
