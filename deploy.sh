#!/bin/bash
#
# Trading Bot PostgreSQL Deployment Script
# Applies all fixes and starts services
#

set -e  # Exit on error

echo "======================================"
echo "🚀 TRADING BOT DEPLOYMENT"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ️ $1${NC}"; }

# Check prerequisites
print_info "Checking prerequisites..."

if [ ! -f .env ]; then
    print_error ".env file not found!"
    exit 1
fi

source .env

# Test PostgreSQL connection
print_info "Testing PostgreSQL connection..."
python -c "
import asyncpg
import asyncio
import os
async def test():
    try:
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        await conn.close()
        print('PostgreSQL connection OK')
    except Exception as e:
        print(f'PostgreSQL connection failed: {e}')
        exit(1)
asyncio.run(test())
" || exit 1

print_success "PostgreSQL connection verified"

# Step 0: Analyze schema changes
print_info "Analyzing schema changes..."
python database/check_schema_changes.py || {
    print_error "Schema analysis failed"
    exit 1
}

# Ask for confirmation
read -p "Do you want to proceed with these changes? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Deployment cancelled"
    exit 0
fi

# Backup ONLY monitoring schema (not entire database)
print_info "Creating backup of monitoring schema..."
chmod +x database/backup_monitoring.sh
./database/backup_monitoring.sh || {
    print_error "Backup failed"
    exit 1
}
print_success "Monitoring schema backed up"

# Step 1: Apply database schema
print_info "Applying database schema..."
python database/apply_schema.py || {
    print_error "Schema application failed"
    print_info "Run rollback: pg_restore -d \$DATABASE_URL --clean --schema=monitoring backups/*/monitoring_*.backup"
    exit 1
}
print_success "Database schema applied"

# Step 2: Run migrations
print_info "Running database migrations..."
python database/migrations/apply_migrations.py || {
    print_error "Migrations failed"
    print_info "Run rollback: pg_restore -d \$DATABASE_URL --clean --schema=monitoring backups/*/monitoring_*.backup"
    exit 1
}
print_success "Migrations completed"

# Step 3: Run tests
print_info "Running tests..."

# Database schema tests
pytest tests/test_database_schema.py -v || {
    print_error "Database schema tests failed"
    exit 1
}

# Exchange adapter tests
pytest tests/test_exchange_adapter.py -v || {
    print_error "Exchange adapter tests failed"
    exit 1
}

# Integration tests
pytest tests/test_full_integration.py -v || {
    print_error "Integration tests failed"
    exit 1
}

print_success "All tests passed"

# Step 4: Initial position sync
print_info "Running initial position synchronization..."
python core/postgres_position_importer.py || {
    print_error "Position import failed"
    exit 1
}
print_success "Positions synchronized"

# Step 5: Check for critical issues
print_info "Checking for critical issues..."
python -c "
import asyncpg
import asyncio
import os

async def check():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute('SET search_path TO monitoring')

    # Check positions without SL
    no_sl = await conn.fetch('''
        SELECT symbol, exchange FROM monitoring.positions
        WHERE status = 'active' AND stop_loss_price IS NULL
    ''')

    if no_sl:
        print(f'⚠️  WARNING: {len(no_sl)} positions without stop-loss!')
        for pos in no_sl:
            print(f'   - {pos[\"exchange\"]}: {pos[\"symbol\"]}')
    else:
        print('✅ All positions have stop-loss')

    # Check active positions count
    count = await conn.fetchval('''
        SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active'
    ''')
    print(f'📊 Active positions: {count}')

    await conn.close()

asyncio.run(check())
"

# Step 6: Setup systemd service (optional)
if [ "$1" == "--install-service" ]; then
    print_info "Installing systemd service..."

    # Copy service file
    sudo cp deploy/position-sync.service /etc/systemd/system/

    # Reload systemd
    sudo systemctl daemon-reload

    # Enable and start service
    sudo systemctl enable position-sync.service
    sudo systemctl start position-sync.service

    # Check status
    sudo systemctl status position-sync.service --no-pager

    print_success "Service installed and started"
fi

# Step 7: Create cron job for backup sync (optional)
if [ "$1" == "--setup-cron" ]; then
    print_info "Setting up cron job..."

    # Add cron job for hourly sync
    (crontab -l 2>/dev/null; echo "0 * * * * cd $(pwd) && python core/postgres_position_importer.py >> logs/sync.log 2>&1") | crontab -

    print_success "Cron job created for hourly sync"
fi

echo ""
echo "======================================"
print_success "DEPLOYMENT COMPLETE!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Start the main trading bot: python main.py"
echo "2. Start sync service: python services/position_sync_service.py"
echo "3. Monitor logs: tail -f logs/trading_bot.log"
echo ""
echo "Optional:"
echo "  ./deploy.sh --install-service  # Install systemd service"
echo "  ./deploy.sh --setup-cron       # Setup hourly cron backup"
echo ""