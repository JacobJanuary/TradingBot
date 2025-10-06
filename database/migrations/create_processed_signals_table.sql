-- Migration: Create processed_signals table
-- Date: 2025-09-30
-- Purpose: Track processed trading signals to avoid duplicates

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS trading_bot;

-- Create the processed_signals table
CREATE TABLE IF NOT EXISTS trading_bot.processed_signals (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(255) UNIQUE NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL,
    score_week DECIMAL(10, 2),
    score_month DECIMAL(10, 2),
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    result VARCHAR(50),
    position_id INTEGER,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_action CHECK (action IN ('BUY', 'SELL', 'LONG', 'SHORT', 'CLOSE'))
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_processed_signals_symbol
    ON trading_bot.processed_signals(symbol);

CREATE INDEX IF NOT EXISTS idx_processed_signals_created_at
    ON trading_bot.processed_signals(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_processed_signals_signal_id
    ON trading_bot.processed_signals(signal_id);

-- Add composite index for duplicate checking
CREATE INDEX IF NOT EXISTS idx_processed_signals_symbol_action_created
    ON trading_bot.processed_signals(symbol, action, created_at DESC);

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE trading_bot.processed_signals TO CURRENT_USER;
GRANT USAGE, SELECT ON SEQUENCE trading_bot.processed_signals_id_seq TO CURRENT_USER;

-- Add comment
COMMENT ON TABLE trading_bot.processed_signals IS 'Tracks all processed trading signals to prevent duplicate processing';
COMMENT ON COLUMN trading_bot.processed_signals.signal_id IS 'Unique identifier from signal source';
COMMENT ON COLUMN trading_bot.processed_signals.result IS 'Processing result: success, skipped, failed, etc';

-- Verify table creation
SELECT 'Table created successfully' AS status
WHERE EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema = 'trading_bot'
    AND table_name = 'processed_signals'
);