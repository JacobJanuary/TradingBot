-- =====================================================================
-- MIGRATION 005: Add trailing params columns to monitoring.positions
-- =====================================================================
-- Date: 2025-10-28
-- Purpose: Store per-position trailing stop parameters
--
-- This allows each position to have its own trailing params,
-- independent of current monitoring.params values.
-- =====================================================================

BEGIN;

-- =====================================================================
-- 1. Add new columns to monitoring.positions
-- =====================================================================
ALTER TABLE monitoring.positions
ADD COLUMN IF NOT EXISTS trailing_activation_percent NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS trailing_callback_percent NUMERIC(10,4);

-- Comments
COMMENT ON COLUMN monitoring.positions.trailing_activation_percent IS
    'Trailing stop activation percentage for THIS position (saved on creation from monitoring.params)';

COMMENT ON COLUMN monitoring.positions.trailing_callback_percent IS
    'Trailing stop callback/distance percentage for THIS position (saved on creation from monitoring.params)';

-- =====================================================================
-- 2. No data migration needed (new positions will be created)
-- =====================================================================
-- Per user requirement: "просто закроем все позиции"
-- So no need to fill existing positions with values

-- =====================================================================
-- 3. Verification
-- =====================================================================
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    -- Check columns added
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_schema = 'monitoring'
      AND table_name = 'positions'
      AND column_name IN ('trailing_activation_percent', 'trailing_callback_percent');

    IF col_count != 2 THEN
        RAISE EXCEPTION 'Expected 2 new columns in monitoring.positions, found %', col_count;
    END IF;

    RAISE NOTICE '✅ monitoring.positions: Added trailing_activation_percent and trailing_callback_percent';
END $$;

COMMIT;

DO $$ BEGIN
    RAISE NOTICE '✅ Migration 005 completed successfully!';
END $$;
