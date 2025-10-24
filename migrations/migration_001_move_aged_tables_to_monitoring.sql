-- =====================================================================
-- MIGRATION 001: Move aged_* tables from public to monitoring schema
-- =====================================================================
-- Date: 2025-10-24
-- Purpose: Move aged_positions and aged_monitoring_events tables
--          from public schema to monitoring schema
--
-- Tables affected:
--   - public.aged_positions (2 records) → monitoring.aged_positions
--   - public.aged_monitoring_events (61,571 records) → monitoring.aged_monitoring_events
--
-- ВАЖНО: Выполнять когда бот остановлен!
-- =====================================================================

-- Начало транзакции
BEGIN;

-- =====================================================================
-- 1. Проверка существования таблиц в public
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'aged_positions'
    ) THEN
        RAISE EXCEPTION 'Table public.aged_positions does not exist!';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'aged_monitoring_events'
    ) THEN
        RAISE EXCEPTION 'Table public.aged_monitoring_events does not exist!';
    END IF;

    RAISE NOTICE 'Pre-check: Both tables exist in public schema';
END $$;

-- =====================================================================
-- 2. Backup counts для верификации
-- =====================================================================
DO $$
DECLARE
    pos_count INTEGER;
    events_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO pos_count FROM public.aged_positions;
    SELECT COUNT(*) INTO events_count FROM public.aged_monitoring_events;

    RAISE NOTICE 'Backup counts - aged_positions: %, aged_monitoring_events: %',
                 pos_count, events_count;
END $$;

-- =====================================================================
-- 3. Перенос aged_positions: public → monitoring
-- =====================================================================
ALTER TABLE public.aged_positions
    SET SCHEMA monitoring;

DO $$ BEGIN RAISE NOTICE 'Moved aged_positions to monitoring schema'; END $$;

-- =====================================================================
-- 4. Перенос aged_monitoring_events: public → monitoring
-- =====================================================================
ALTER TABLE public.aged_monitoring_events
    SET SCHEMA monitoring;

DO $$ BEGIN RAISE NOTICE 'Moved aged_monitoring_events to monitoring schema'; END $$;

-- =====================================================================
-- 5. Верификация после переноса
-- =====================================================================
DO $$
DECLARE
    pos_count INTEGER;
    events_count INTEGER;
    public_pos_exists BOOLEAN;
    public_events_exists BOOLEAN;
BEGIN
    -- Проверяем что таблицы больше нет в public
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'aged_positions'
    ) INTO public_pos_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'aged_monitoring_events'
    ) INTO public_events_exists;

    IF public_pos_exists OR public_events_exists THEN
        RAISE EXCEPTION 'Tables still exist in public schema!';
    END IF;

    -- Проверяем что таблицы появились в monitoring
    SELECT COUNT(*) INTO pos_count FROM monitoring.aged_positions;
    SELECT COUNT(*) INTO events_count FROM monitoring.aged_monitoring_events;

    RAISE NOTICE 'Verification - monitoring.aged_positions: % records', pos_count;
    RAISE NOTICE 'Verification - monitoring.aged_monitoring_events: % records', events_count;

    IF pos_count = 0 AND events_count = 0 THEN
        RAISE WARNING 'Both tables are empty - this is unexpected!';
    END IF;
END $$;

-- =====================================================================
-- 6. Обновление комментариев
-- =====================================================================
COMMENT ON TABLE monitoring.aged_positions IS
    'Aged positions tracking - moved from public schema on 2025-10-24';

COMMENT ON TABLE monitoring.aged_monitoring_events IS
    'Aged position monitoring events - moved from public schema on 2025-10-24';

-- Коммит транзакции
COMMIT;

DO $$ BEGIN
    RAISE NOTICE 'Migration 001 completed successfully!';
    RAISE NOTICE 'Tables moved: public.aged_* → monitoring.aged_*';
END $$;
