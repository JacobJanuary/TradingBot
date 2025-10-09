#!/bin/bash
# Emergency restore script
#
# Restores system from backup created in Phase 0.2
#
# Usage:
#   bash tools/emergency/restore_from_backup.sh

set -e  # Exit on error

echo "🚨 EMERGENCY RESTORE"
echo "===================="
echo ""

# Find latest backup
LATEST_BACKUP=$(ls -t backup_monitoring_*.sql 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup found!"
    echo "   Looking for: backup_monitoring_*.sql"
    exit 1
fi

echo "Found backup: $LATEST_BACKUP"
BACKUP_SIZE=$(ls -lh "$LATEST_BACKUP" | awk '{print $5}')
echo "Size: $BACKUP_SIZE"
echo ""

read -p "Restore from this backup? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

echo ""
echo "🛑 STEP 1: Stopping bot..."
pkill -f "python main.py" || true
sleep 2
echo "✅ Bot stopped"

echo ""
echo "🗄️  STEP 2: Restoring database..."
echo "   WARNING: This will DROP and recreate monitoring schema!"
read -p "Continue? (yes/no): " CONFIRM2

if [ "$CONFIRM2" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

# Drop and restore monitoring schema
PGPASSWORD="LohNeMamont@!21" psql -h localhost -p 5433 -U elcrypto -d fox_crypto << SQL
DROP SCHEMA IF EXISTS monitoring CASCADE;
SQL

echo "   Schema dropped, restoring from backup..."

PGPASSWORD="LohNeMamont@!21" psql -h localhost -p 5433 -U elcrypto -d fox_crypto < "$LATEST_BACKUP"

echo "✅ Database restored"

echo ""
echo "📝 STEP 3: Restoring .env..."
LATEST_ENV=$(ls -t .env.backup_* 2>/dev/null | head -1)
if [ -n "$LATEST_ENV" ]; then
    cp "$LATEST_ENV" .env
    echo "✅ .env restored from: $LATEST_ENV"
else
    echo "⚠️  No .env backup found - skipping"
fi

echo ""
echo "🔄 STEP 4: Restoring code from git..."
echo "   Current commit: $(git rev-parse --short HEAD)"
echo "   Snapshot commit (from git log):"
git log --oneline | grep "SNAPSHOT" | head -1

read -p "Reset to snapshot commit? (yes/no): " CONFIRM3

if [ "$CONFIRM3" == "yes" ]; then
    SNAPSHOT_COMMIT=$(git log --oneline | grep "SNAPSHOT" | head -1 | awk '{print $1}')
    git reset --hard "$SNAPSHOT_COMMIT"
    echo "✅ Code restored to snapshot"
else
    echo "⚠️  Code NOT restored - keeping current version"
fi

echo ""
echo "=" 80
echo "✅ RESTORE COMPLETE"
echo "="*80
echo ""
echo "Next steps:"
echo "  1. Run health check: python tests/integration/health_check_after_fix.py"
echo "  2. Review what happened: git log -5"
echo "  3. Check system: python main.py --dry-run"
echo ""
echo "If problems persist:"
echo "  - Check logs: tail -100 logs/trading_bot.log"
echo "  - Verify database: psql commands"
echo "  - Contact support"
