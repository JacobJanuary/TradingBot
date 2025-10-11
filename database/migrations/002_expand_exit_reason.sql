-- Migration: Expand exit_reason field and add audit fields
-- Purpose: Store complete error messages and improve debugging

-- For PostgreSQL:
ALTER TABLE monitoring.positions
ALTER COLUMN exit_reason TYPE TEXT;

-- Add audit fields for better tracking
ALTER TABLE monitoring.positions
ADD COLUMN IF NOT EXISTS error_details JSONB,
ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMP;

-- Create index for error analysis
CREATE INDEX IF NOT EXISTS idx_positions_exit_reason
ON monitoring.positions(exit_reason)
WHERE exit_reason IS NOT NULL;

-- For SQLite (requires table recreation):
-- SQLite doesn't support ALTER COLUMN, so we need to recreate
/*
-- Step 1: Create new table with updated schema
CREATE TABLE positions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL,
    stop_loss_price REAL,
    take_profit_price REAL,
    unrealized_pnl REAL,
    realized_pnl REAL,
    fees REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    exit_reason TEXT,  -- Changed from VARCHAR(100) to TEXT
    error_details TEXT,  -- JSON string for SQLite
    retry_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMP,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    leverage REAL DEFAULT 1.0,
    stop_loss REAL,
    take_profit REAL,
    pnl REAL,
    pnl_percentage REAL,
    trailing_activated BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Step 2: Copy data
INSERT INTO positions_new SELECT
    id, signal_id, symbol, exchange, side, quantity, entry_price,
    current_price, stop_loss_price, take_profit_price, unrealized_pnl,
    realized_pnl, fees, status, exit_reason,
    NULL, 0, NULL,  -- New fields with defaults
    opened_at, closed_at, updated_at, leverage, stop_loss,
    take_profit, pnl, pnl_percentage, trailing_activated, created_at
FROM positions;

-- Step 3: Drop old table and rename
DROP TABLE positions;
ALTER TABLE positions_new RENAME TO positions;

-- Step 4: Recreate indexes
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_exit_reason ON positions(exit_reason)
WHERE exit_reason IS NOT NULL;
*/