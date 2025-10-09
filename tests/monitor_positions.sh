#!/bin/bash
# Monitor testnet positions in real-time
# Usage: ./tests/monitor_positions.sh

# Configuration
DB_HOST="localhost"
DB_PORT="5433"
DB_NAME="fox_crypto_test"
DB_USER="elcrypto"
export PGPASSWORD="LohNeMamont@!21"

echo "🔍 Monitoring testnet positions (Ctrl+C to stop)"
echo "Database: $DB_NAME on port $DB_PORT"
echo "Refresh: every 5 seconds"
echo ""

while true; do
    clear
    echo "════════════════════════════════════════════════════════════════"
    date
    echo "════════════════════════════════════════════════════════════════"

    echo ""
    echo "📊 Latest 5 Positions:"
    echo "────────────────────────────────────────────────────────────────"

    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
        SELECT
            id,
            symbol,
            side,
            status,
            ROUND(entry_price::numeric, 2) as entry,
            ROUND(COALESCE(current_price, entry_price)::numeric, 2) as current,
            ROUND(COALESCE(unrealized_pnl, 0)::numeric, 2) as pnl,
            has_stop_loss as sl,
            TO_CHAR(created_at, 'HH24:MI:SS') as created
        FROM monitoring.positions
        ORDER BY id DESC
        LIMIT 5;
    " 2>/dev/null || echo "❌ Database connection failed"

    echo ""
    echo "📈 Position Summary:"
    echo "────────────────────────────────────────────────────────────────"

    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
        SELECT
            status,
            COUNT(*) as count,
            ROUND(SUM(COALESCE(unrealized_pnl, 0))::numeric, 2) as total_pnl
        FROM monitoring.positions
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY status
        ORDER BY
            CASE status
                WHEN 'open' THEN 1
                WHEN 'pending_close' THEN 2
                WHEN 'closed' THEN 3
                ELSE 4
            END;
    " 2>/dev/null || echo "❌ Database connection failed"

    echo ""
    echo "⏰ Recent Activity (last hour):"
    echo "────────────────────────────────────────────────────────────────"

    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
        SELECT
            id,
            symbol,
            side,
            status,
            ROUND(COALESCE(realized_pnl, unrealized_pnl, 0)::numeric, 2) as pnl,
            TO_CHAR(created_at, 'HH24:MI:SS') as time
        FROM monitoring.positions
        WHERE created_at > NOW() - INTERVAL '1 hour'
        ORDER BY id DESC
        LIMIT 10;
    " 2>/dev/null || echo "❌ No recent positions"

    echo ""
    echo "Press Ctrl+C to stop monitoring"

    sleep 5
done
