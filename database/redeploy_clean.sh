#!/bin/bash
# ============================================================================
# CLEAN REDEPLOY SCRIPT
# ============================================================================
# Purpose: Completely remove old schema and deploy fresh one
# WARNING: THIS WILL DELETE ALL DATA!
# ============================================================================

set -e  # Exit on any error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DB_NAME="${1:-fox_crypto}"
DB_USER="${2:-evgeniyyanvarskiy}"
DB_HOST="${3:-localhost}"
DB_PORT="${4:-5432}"

echo -e "${RED}⚠️  WARNING: DESTRUCTIVE OPERATION ⚠️${NC}"
echo -e "${RED}════════════════════════════════════${NC}"
echo ""
echo "This script will:"
echo "  1. DROP the entire 'monitoring' schema (all tables, data, indexes, triggers)"
echo "  2. DROP the legacy 'fas' schema if it exists"
echo "  3. Deploy fresh schema from DEPLOY_SCHEMA.sql"
echo ""
echo -e "${YELLOW}Database: $DB_NAME${NC}"
echo -e "${YELLOW}Host: $DB_HOST:$DB_PORT${NC}"
echo -e "${YELLOW}User: $DB_USER${NC}"
echo ""
echo -e "${RED}ALL DATA WILL BE LOST!${NC}"
echo ""
read -p "Are you ABSOLUTELY sure? Type 'YES' to continue: " CONFIRM

if [ "$CONFIRM" != "YES" ]; then
    echo -e "${YELLOW}❌ Aborted by user${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}════════════════════════════════════${NC}"
echo -e "${BLUE}Starting clean redeploy...${NC}"
echo -e "${BLUE}════════════════════════════════════${NC}"
echo ""

# Execute the SQL script
if [ -z "$PGPASSWORD" ]; then
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f database/REDEPLOY_CLEAN.sql
else
    PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f database/REDEPLOY_CLEAN.sql
fi

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}════════════════════════════════════${NC}"
    echo -e "${GREEN}🎉 SUCCESS!${NC}"
    echo -e "${GREEN}════════════════════════════════════${NC}"
    echo ""
    echo "Database schema has been completely redeployed."
    echo ""
    echo "Next steps:"
    echo "  1. Restart your trading bot"
    echo "  2. Verify bot can connect to database"
    echo "  3. Monitor for any issues"
    echo ""
else
    echo -e "${RED}════════════════════════════════════${NC}"
    echo -e "${RED}❌ FAILED!${NC}"
    echo -e "${RED}════════════════════════════════════${NC}"
    echo ""
    echo "Redeploy failed with exit code: $EXIT_CODE"
    echo "Please check the error messages above."
    echo ""
    exit $EXIT_CODE
fi
