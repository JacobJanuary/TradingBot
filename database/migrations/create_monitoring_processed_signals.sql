-- Migration: Create monitoring.processed_signals
-- Date: 2025-10-08
-- Purpose: Move processed_signals from trading_bot to monitoring schema

-- Create the table
CREATE TABLE IF NOT EXISTS monitoring.processed_signals (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(255) UNIQUE NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL,
    score_week NUMERIC(10,2),
    score_month NUMERIC(10,2),
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    result VARCHAR(50),
    position_id INTEGER,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_action CHECK (action IN ('BUY', 'SELL', 'LONG', 'SHORT', 'CLOSE'))
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_processed_signals_created_at
    ON monitoring.processed_signals(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_processed_signals_signal_id
    ON monitoring.processed_signals(signal_id);

CREATE INDEX IF NOT EXISTS idx_processed_signals_symbol
    ON monitoring.processed_signals(symbol);

-- Add composite index for duplicate checking
CREATE INDEX IF NOT EXISTS idx_processed_signals_symbol_action_created
    ON monitoring.processed_signals(symbol, action, created_at DESC);

-- Add comment
COMMENT ON TABLE monitoring.processed_signals IS 'Tracks all processed trading signals to prevent duplicate processing';
COMMENT ON COLUMN monitoring.processed_signals.signal_id IS 'Unique identifier from signal source';
COMMENT ON COLUMN monitoring.processed_signals.result IS 'Processing result: success, skipped, failed, etc';

-- Copy existing data from trading_bot.processed_signals if it exists
INSERT INTO monitoring.processed_signals 
    (signal_id, symbol, action, score_week, score_month, processed_at, result, position_id, error_message, created_at)
SELECT 
    signal_id, symbol, action, score_week, score_month, processed_at, result, position_id, error_message, created_at
FROM trading_bot.processed_signals
WHERE NOT EXISTS (
    SELECT 1 FROM monitoring.processed_signals mps 
    WHERE mps.signal_id = trading_bot.processed_signals.signal_id
)
ON CONFLICT (signal_id) DO NOTHING;

-- Verify table creation
SELECT 
    'monitoring.processed_signals created successfully' AS status,
    COUNT(*) AS records_count
FROM monitoring.processed_signals;
