-- Migration 002: Initialize monitoring.params with exchange records
-- Date: 2025-10-30
-- Purpose: Create initial rows for Binance (1) and Bybit (2) to enable UPSERT operations

-- Insert initial rows for both exchanges
-- All filter columns will be NULL initially (fallback to config)
INSERT INTO monitoring.params (exchange_id)
VALUES (1), (2)
ON CONFLICT (exchange_id) DO NOTHING;

-- Verify insertion
SELECT * FROM monitoring.params ORDER BY exchange_id;
