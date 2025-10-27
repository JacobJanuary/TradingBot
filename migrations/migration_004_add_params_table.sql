-- =====================================================================
-- MIGRATION 004: Create monitoring.params table
-- =====================================================================
-- Date: 2025-10-27
-- Purpose: Store backtest filter parameters per exchange
--
-- This table stores the latest filter parameters received from
-- WebSocket signals, enabling dynamic strategy configuration.
-- =====================================================================

BEGIN;

-- =====================================================================
-- 1. Create monitoring.params table
-- =====================================================================
CREATE TABLE monitoring.params (
    exchange_id INTEGER PRIMARY KEY,
    max_trades_filter INTEGER,
    stop_loss_filter NUMERIC(10,4),
    trailing_activation_filter NUMERIC(10,4),
    trailing_distance_filter NUMERIC(10,4),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_exchange_id CHECK (exchange_id IN (1, 2)),
    CONSTRAINT valid_max_trades CHECK (max_trades_filter > 0 OR max_trades_filter IS NULL),
    CONSTRAINT valid_stop_loss CHECK (stop_loss_filter > 0 OR stop_loss_filter IS NULL),
    CONSTRAINT valid_trailing_activation CHECK (trailing_activation_filter > 0 OR trailing_activation_filter IS NULL),
    CONSTRAINT valid_trailing_distance CHECK (trailing_distance_filter > 0 OR trailing_distance_filter IS NULL)
);

-- Comments
COMMENT ON TABLE monitoring.params IS
    'Backtest filter parameters per exchange. Updated on each wave reception from WebSocket.';

COMMENT ON COLUMN monitoring.params.exchange_id IS
    'Exchange identifier: 1=Binance, 2=Bybit';

COMMENT ON COLUMN monitoring.params.max_trades_filter IS
    'Maximum trades per wave from backtest optimization';

COMMENT ON COLUMN monitoring.params.stop_loss_filter IS
    'Stop loss percentage from backtest (e.g., 2.5 = 2.5%)';

COMMENT ON COLUMN monitoring.params.trailing_activation_filter IS
    'Trailing stop activation percentage from backtest (e.g., 3.0 = 3.0%)';

COMMENT ON COLUMN monitoring.params.trailing_distance_filter IS
    'Trailing stop distance percentage from backtest (e.g., 1.5 = 1.5%)';

COMMENT ON COLUMN monitoring.params.updated_at IS
    'Timestamp of last parameter update';

-- =====================================================================
-- 2. Create indexes
-- =====================================================================
CREATE INDEX idx_params_updated_at ON monitoring.params (updated_at DESC);

-- =====================================================================
-- 3. Create trigger for auto-updating updated_at
-- =====================================================================
CREATE TRIGGER update_params_updated_at
    BEFORE UPDATE ON monitoring.params
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TRIGGER update_params_updated_at ON monitoring.params IS
    'Auto-updates updated_at column on any UPDATE';

-- =====================================================================
-- 4. Initialize with default rows (NULL values)
-- =====================================================================
INSERT INTO monitoring.params (exchange_id)
VALUES (1), (2)
ON CONFLICT (exchange_id) DO NOTHING;

-- =====================================================================
-- 5. Verification
-- =====================================================================
DO $$
DECLARE
    row_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO row_count FROM monitoring.params;

    IF row_count != 2 THEN
        RAISE EXCEPTION 'Expected 2 rows in monitoring.params, found %', row_count;
    END IF;

    RAISE NOTICE 'monitoring.params table created successfully with % rows', row_count;
END $$;

COMMIT;

DO $$ BEGIN
    RAISE NOTICE 'Migration 004 completed successfully!';
END $$;
