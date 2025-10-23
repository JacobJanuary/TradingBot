-- Migration 010: Create orders cache table
-- Date: 2025-10-23
-- Purpose: Solve Bybit 500 orders limit issue by caching all orders locally

-- Create monitoring schema if not exists (idempotent)
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Create orders cache table
CREATE TABLE IF NOT EXISTS monitoring.orders_cache (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    exchange_order_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price DECIMAL(20, 8),
    amount DECIMAL(20, 8) NOT NULL,
    filled DECIMAL(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_data JSONB,

    CONSTRAINT unique_exchange_order UNIQUE (exchange, exchange_order_id)
);

-- Create indexes for query performance
CREATE INDEX IF NOT EXISTS idx_orders_cache_exchange_symbol
ON monitoring.orders_cache(exchange, symbol);

CREATE INDEX IF NOT EXISTS idx_orders_cache_created_at
ON monitoring.orders_cache(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_cache_order_id
ON monitoring.orders_cache(exchange_order_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON monitoring.orders_cache TO evgeniyyanvarskiy;
GRANT USAGE, SELECT ON SEQUENCE monitoring.orders_cache_id_seq TO evgeniyyanvarskiy;

-- Verification
DO $$
BEGIN
    RAISE NOTICE 'Migration 010 completed: orders_cache table created';
END $$;
