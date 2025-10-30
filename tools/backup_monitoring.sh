#!/bin/bash
#
# Backup only monitoring schema before migrations
# More efficient than full database backup
#

set -e

# Load environment
source .env

# Create backup directory
BACKUP_DIR="backups/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "📦 Creating backup of monitoring schema..."

# Backup ONLY monitoring schema (not entire database)
pg_dump $DATABASE_URL \
    --schema=monitoring \
    --no-owner \
    --no-privileges \
    --format=custom \
    --file="${BACKUP_DIR}/monitoring_${TIMESTAMP}.backup"

echo "✅ Backup created: ${BACKUP_DIR}/monitoring_${TIMESTAMP}.backup"

# Also create SQL format for easy inspection
pg_dump $DATABASE_URL \
    --schema=monitoring \
    --no-owner \
    --no-privileges \
    --format=plain \
    --file="${BACKUP_DIR}/monitoring_${TIMESTAMP}.sql"

echo "📄 SQL backup created: ${BACKUP_DIR}/monitoring_${TIMESTAMP}.sql"

# Show backup size
du -h ${BACKUP_DIR}/monitoring_${TIMESTAMP}.*

# Keep only last 7 days of backups
find backups -type f -name "*.backup" -mtime +7 -delete
find backups -type f -name "*.sql" -mtime +7 -delete

echo "✅ Backup complete!"
echo ""
echo "To restore if needed:"
echo "  pg_restore -d $DATABASE_URL --clean --schema=monitoring ${BACKUP_DIR}/monitoring_${TIMESTAMP}.backup"