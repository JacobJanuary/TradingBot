# Database Migrations

This directory contains SQL migration scripts for the Trading Bot database.

## Quick Start

### Create Database

```bash
# Create database
createdb fox_crypto

# Run migrations
psql -U yourusername -d fox_crypto -f database/migrations/001_init_schema.sql
```

### Or use Python script

```bash
python database/migrations/apply_migrations.py
```

## Migration Files

### 001_init_schema.sql
**Updated**: 2025-10-29

Complete database schema initialization including:

#### Schemas
- `monitoring` - Main operational schema

#### Tables (14 total)

**monitoring schema:**
1. `positions` - Active and historical positions
2. `orders` - Order execution history
3. `trades` - Completed trades
4. `trailing_stop_state` - Trailing stop management (with FK to positions)
5. `orders_cache` - Orders cache for fast access
6. `aged_positions` - Aged positions tracking
7. `aged_monitoring_events` - Aged position events
8. `risk_events` - Risk management events
9. `risk_violations` - Risk limit violations
10. `events` - Main event log (69 event types)
11. `event_performance_metrics` - Performance metrics
12. `transaction_log` - Audit transaction log
13. `performance_metrics` - Performance tracking
14. `params` - Backtest filter parameters per exchange

#### Functions
- `normalize_trailing_stop_side()` - Auto-lowercase side column
- `update_updated_at_column()` - Auto-update timestamps

#### Triggers
- `normalize_side_trigger` - On trailing_stop_state (BEFORE INSERT/UPDATE)
- `update_params_updated_at` - On params (BEFORE UPDATE)
- `update_positions_updated_at` - On positions (BEFORE UPDATE)
- `update_trades_updated_at` - On trades (BEFORE UPDATE)

#### Foreign Keys
- `trailing_stop_state.position_id` → `positions.id` (ON DELETE CASCADE)

#### Indexes (35+)
Optimized indexes for:
- Time-based queries (created_at, updated_at DESC)
- Symbol lookups
- Exchange filtering
- Status filtering
- Correlation ID tracking
- Performance metrics
- Unique constraints

## Environment Variables

Set these in `.env` before running migrations:

```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fox_crypto
DB_USER=yourusername
DB_PASSWORD=yourpassword
```

## Verification

After running migrations, verify the schema:

```bash
# List all schemas
psql -U yourusername -d fox_crypto -c "\dn"

# List all tables
psql -U yourusername -d fox_crypto -c "\dt monitoring.*"

# Verify indexes
psql -U yourusername -d fox_crypto -c "\di monitoring.*"
```

## Schema Updates

The migration file is automatically generated from the production database schema.

To update the migration with current database structure:

```bash
# Export current schema
pg_dump -h localhost -U yourusername -d fox_crypto --schema-only --no-owner --no-privileges > /tmp/current_schema.sql

# Review and update 001_init_schema.sql manually
```

## Production Deployment

```bash
# On production server:

# 1. Create database
createdb fox_crypto

# 2. Create user (if needed)
createuser -P trading_user

# 3. Grant permissions
psql -c "GRANT ALL PRIVILEGES ON DATABASE fox_crypto TO trading_user;"

# 4. Run migration
psql -U trading_user -d fox_crypto -f database/migrations/001_init_schema.sql

# 5. Verify
psql -U trading_user -d fox_crypto -c "SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'monitoring' ORDER BY tablename;"
```

## Troubleshooting

### Permission Denied

```bash
psql -c "ALTER DATABASE fox_crypto OWNER TO trading_user;"
psql -d fox_crypto -c "ALTER SCHEMA monitoring OWNER TO trading_user;"
```

### Schema Already Exists

The migration uses `CREATE SCHEMA IF NOT EXISTS` and `CREATE OR REPLACE FUNCTION`, so it's safe to re-run.

To start fresh:

```bash
dropdb fox_crypto
createdb fox_crypto
psql -U trading_user -d fox_crypto -f database/migrations/001_init_schema.sql
```

## Notes

- Migration file is idempotent (safe to re-run)
- Uses `IF NOT EXISTS` for schemas
- Uses `CREATE OR REPLACE` for functions
- All timestamps use `timestamp with time zone`
- Numeric precision: (20,8) for prices/amounts
- JSONB for flexible data storage
- Comments on tables, columns, triggers for documentation
