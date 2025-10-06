-- ============================================================================
-- REAL INTEGRATION TEST - Database Setup
-- ============================================================================
-- Creates test table for signal generation and processing
-- Date: 2025-10-04
-- ============================================================================

-- Create test schema if not exists
CREATE SCHEMA IF NOT EXISTS test;

-- Drop existing test table if exists
DROP TABLE IF EXISTS test.scoring_history CASCADE;

-- Create test scoring_history table (copy of fas.scoring_history structure)
CREATE TABLE test.scoring_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    wave_number INTEGER NOT NULL,
    score NUMERIC(10, 2) NOT NULL,
    
    -- Signal metadata
    signal_type VARCHAR(20) DEFAULT 'MOMENTUM',
    confidence NUMERIC(5, 2) DEFAULT 0.0,
    volume_24h NUMERIC(20, 2),
    price_change_24h NUMERIC(10, 4),
    
    -- Wave metadata
    wave_start TIMESTAMP NOT NULL,
    wave_end TIMESTAMP NOT NULL,
    
    -- Processing tracking
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    position_opened BOOLEAN DEFAULT FALSE,
    position_id INTEGER,
    
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT unique_signal UNIQUE (symbol, exchange, wave_number),
    CONSTRAINT score_range CHECK (score >= 0 AND score <= 100),
    CONSTRAINT confidence_range CHECK (confidence >= 0 AND confidence <= 100)
);

-- Create indexes for performance
CREATE INDEX idx_test_scoring_timestamp ON test.scoring_history(timestamp DESC);
CREATE INDEX idx_test_scoring_wave ON test.scoring_history(wave_number);
CREATE INDEX idx_test_scoring_processed ON test.scoring_history(processed, timestamp);
CREATE INDEX idx_test_scoring_symbol_exchange ON test.scoring_history(symbol, exchange);

-- Create view for unprocessed signals
CREATE OR REPLACE VIEW test.unprocessed_signals AS
SELECT 
    id,
    symbol,
    exchange,
    timeframe,
    timestamp,
    wave_number,
    score,
    signal_type,
    confidence,
    volume_24h,
    price_change_24h,
    wave_start,
    wave_end
FROM test.scoring_history
WHERE processed = FALSE
ORDER BY score DESC, timestamp DESC;

-- Create function to mark signal as processed
CREATE OR REPLACE FUNCTION test.mark_signal_processed(
    p_signal_id INTEGER,
    p_position_opened BOOLEAN DEFAULT FALSE,
    p_position_id INTEGER DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    UPDATE test.scoring_history
    SET 
        processed = TRUE,
        processed_at = CURRENT_TIMESTAMP,
        position_opened = p_position_opened,
        position_id = p_position_id
    WHERE id = p_signal_id;
END;
$$ LANGUAGE plpgsql;

-- Create function to get current wave number
CREATE OR REPLACE FUNCTION test.get_current_wave()
RETURNS INTEGER AS $$
DECLARE
    current_wave INTEGER;
BEGIN
    -- Wave number based on 15-minute intervals
    -- Starting from epoch: wave 1 = 2025-10-04 00:00:00
    SELECT FLOOR(EXTRACT(EPOCH FROM (NOW() - '2025-10-04 00:00:00'::timestamp)) / 900) + 1
    INTO current_wave;
    
    RETURN COALESCE(current_wave, 1);
END;
$$ LANGUAGE plpgsql;

-- Create function to get wave boundaries
CREATE OR REPLACE FUNCTION test.get_wave_boundaries(p_wave_number INTEGER)
RETURNS TABLE(wave_start TIMESTAMP, wave_end TIMESTAMP) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ('2025-10-04 00:00:00'::timestamp + ((p_wave_number - 1) * INTERVAL '15 minutes'))::timestamp AS wave_start,
        ('2025-10-04 00:00:00'::timestamp + (p_wave_number * INTERVAL '15 minutes'))::timestamp AS wave_end;
END;
$$ LANGUAGE plpgsql;

-- Create statistics view
CREATE OR REPLACE VIEW test.signal_statistics AS
SELECT 
    COUNT(*) as total_signals,
    COUNT(*) FILTER (WHERE processed = TRUE) as processed_signals,
    COUNT(*) FILTER (WHERE position_opened = TRUE) as positions_opened,
    COUNT(DISTINCT wave_number) as total_waves,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(*) FILTER (WHERE exchange = 'binance') as binance_signals,
    COUNT(*) FILTER (WHERE exchange = 'bybit') as bybit_signals,
    MIN(timestamp) as first_signal,
    MAX(timestamp) as last_signal,
    AVG(score) as avg_score
FROM test.scoring_history;

-- Grant permissions (adjust as needed)
-- GRANT ALL ON SCHEMA test TO trading_bot;
-- GRANT ALL ON ALL TABLES IN SCHEMA test TO trading_bot;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA test TO trading_bot;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA test TO trading_bot;

-- ============================================================================
-- Setup completed successfully
-- ============================================================================

-- Display setup info
DO $$
BEGIN
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
    RAISE NOTICE '✅ Test Database Setup Completed!';
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
    RAISE NOTICE 'Schema: test';
    RAISE NOTICE 'Table: test.scoring_history';
    RAISE NOTICE 'View: test.unprocessed_signals';
    RAISE NOTICE 'View: test.signal_statistics';
    RAISE NOTICE 'Functions:';
    RAISE NOTICE '  - test.mark_signal_processed()';
    RAISE NOTICE '  - test.get_current_wave()';
    RAISE NOTICE '  - test.get_wave_boundaries()';
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
    RAISE NOTICE 'Current wave: %', test.get_current_wave();
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
END $$;

