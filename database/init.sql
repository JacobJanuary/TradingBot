-- Create schemas
CREATE SCHEMA IF NOT EXISTS fas;
CREATE SCHEMA IF NOT EXISTS monitoring;

-- FAS schema tables (for signal source)
CREATE TABLE IF NOT EXISTS fas.scoring_history (
    id SERIAL PRIMARY KEY,
    trading_pair_id INTEGER NOT NULL,
    pair_symbol VARCHAR(20) NOT NULL,
    exchange_id INTEGER NOT NULL,
    exchange_name VARCHAR(50) NOT NULL,
    score_week FLOAT,
    score_month FLOAT,
    recommended_action VARCHAR(10),
    patterns_details JSONB,
    combinations_details JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_processed BOOLEAN DEFAULT FALSE
);

-- Monitoring schema tables
CREATE TABLE IF NOT EXISTS monitoring.positions (
    id VARCHAR(100) PRIMARY KEY,
    signal_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    stop_loss_price DECIMAL(20, 8),
    take_profit_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8),
    realized_pnl DECIMAL(20, 8),
    fees DECIMAL(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    exit_reason VARCHAR(100),
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.orders (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(100),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(100),
    client_order_id VARCHAR(100),
    type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    size DECIMAL(20, 8),
    price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL,
    filled DECIMAL(20, 8) DEFAULT 0,
    remaining DECIMAL(20, 8),
    fee DECIMAL(20, 8),
    fee_currency VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.trades (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20),
    quantity DECIMAL(20, 8),
    price DECIMAL(20, 8),
    executed_qty DECIMAL(20, 8),
    average_price DECIMAL(20, 8),
    order_id VARCHAR(100),
    client_order_id VARCHAR(100),
    status VARCHAR(20),
    fee DECIMAL(20, 8),
    fee_currency VARCHAR(10),
    executed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.risk_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    position_id VARCHAR(100),
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.risk_violations (
    id SERIAL PRIMARY KEY,
    violation_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    message TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitoring.performance_metrics (
    id SERIAL PRIMARY KEY,
    period VARCHAR(20) NOT NULL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    total_pnl DECIMAL(20, 8),
    win_rate DECIMAL(5, 2),
    profit_factor DECIMAL(10, 2),
    sharpe_ratio DECIMAL(10, 2),
    max_drawdown DECIMAL(20, 8),
    avg_win DECIMAL(20, 8),
    avg_loss DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_positions_status ON monitoring.positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON monitoring.positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON monitoring.positions(opened_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON monitoring.orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_position ON monitoring.orders(position_id);
CREATE INDEX IF NOT EXISTS idx_signals_processed ON fas.scoring_history(is_processed);
CREATE INDEX IF NOT EXISTS idx_signals_created ON fas.scoring_history(created_at);

-- Permissions (adjust user as needed)
GRANT ALL ON SCHEMA fas TO current_user;
GRANT ALL ON SCHEMA monitoring TO current_user;
GRANT ALL ON ALL TABLES IN SCHEMA fas TO current_user;
GRANT ALL ON ALL TABLES IN SCHEMA monitoring TO current_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA fas TO current_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA monitoring TO current_user;