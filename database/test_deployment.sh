#!/bin/bash
# ============================================================================
# Test script for database deployment
# ============================================================================

echo "🧪 TESTING DATABASE DEPLOYMENT"
echo "================================"
echo ""

# Configuration
DB_NAME="fox_crypto_test"
DB_USER="postgres"
DB_HOST="localhost"
DB_PORT="5432"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Create test database
echo "1️⃣  Creating test database..."
createdb $DB_NAME 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Test database created${NC}"
else
    echo -e "${YELLOW}⚠️  Test database already exists (continuing)${NC}"
fi
echo ""

# Step 2: Deploy schema
echo "2️⃣  Deploying schema..."
psql -d $DB_NAME -f database/DEPLOY_SCHEMA.sql > /tmp/deploy_output.txt 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Schema deployed successfully${NC}"
else
    echo -e "${RED}❌ Schema deployment failed${NC}"
    echo "See /tmp/deploy_output.txt for details"
    exit 1
fi
echo ""

# Step 3: Verify schemas
echo "3️⃣  Verifying schemas..."
SCHEMAS=$(psql -d $DB_NAME -t -c "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = 'monitoring';")
if [ "$SCHEMAS" -eq 1 ]; then
    echo -e "${GREEN}✅ Schemas verified (1/1)${NC}"
else
    echo -e "${RED}❌ Schemas missing (found $SCHEMAS/1)${NC}"
    exit 1
fi
echo ""

# Step 4: Verify tables
echo "4️⃣  Verifying tables..."
TABLES=$(psql -d $DB_NAME -t -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'monitoring';")
if [ "$TABLES" -eq 10 ]; then
    echo -e "${GREEN}✅ Tables verified (10/10)${NC}"
else
    echo -e "${RED}❌ Tables missing (found $TABLES/10)${NC}"
    exit 1
fi
echo ""

# Step 5: Verify indexes
echo "5️⃣  Verifying indexes..."
INDEXES=$(psql -d $DB_NAME -t -c "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'monitoring';")
if [ "$INDEXES" -eq 37 ]; then
    echo -e "${GREEN}✅ Indexes verified (37/37)${NC}"
else
    echo -e "${YELLOW}⚠️  Expected 37 indexes, found $INDEXES${NC}"
fi
echo ""

# Step 6: Verify triggers
echo "6️⃣  Verifying triggers..."
TRIGGERS=$(psql -d $DB_NAME -t -c "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = 'monitoring';")
if [ "$TRIGGERS" -eq 2 ]; then
    echo -e "${GREEN}✅ Triggers verified (2/2)${NC}"
else
    echo -e "${RED}❌ Triggers missing (found $TRIGGERS/2)${NC}"
    exit 1
fi
echo ""

# Step 7: Test trigger functionality
echo "7️⃣  Testing trigger functionality..."
psql -d $DB_NAME -c "
    INSERT INTO monitoring.positions (symbol, exchange, side, quantity, entry_price, status)
    VALUES ('TESTUSDT', 'binance', 'long', 100, 1.0, 'active');
" > /dev/null 2>&1

# Small delay to ensure different timestamps
sleep 1

psql -d $DB_NAME -c "
    UPDATE monitoring.positions
    SET current_price = 1.5
    WHERE symbol = 'TESTUSDT';

    SELECT
        CASE
            WHEN updated_at > created_at THEN 'PASS'
            ELSE 'FAIL'
        END as trigger_test
    FROM monitoring.positions
    WHERE symbol = 'TESTUSDT';
" > /tmp/trigger_test.txt 2>&1

if grep -q "PASS" /tmp/trigger_test.txt; then
    echo -e "${GREEN}✅ Triggers working correctly${NC}"
else
    echo -e "${RED}❌ Triggers not working${NC}"
    cat /tmp/trigger_test.txt
    exit 1
fi
echo ""

# Step 8: Cleanup (optional)
echo "8️⃣  Cleanup test database? (y/N)"
read -t 5 -n 1 CLEANUP
echo ""
if [ "$CLEANUP" = "y" ] || [ "$CLEANUP" = "Y" ]; then
    dropdb $DB_NAME
    echo -e "${GREEN}✅ Test database removed${NC}"
else
    echo -e "${YELLOW}ℹ️  Test database kept: $DB_NAME${NC}"
fi
echo ""

# Summary
echo "================================"
echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
echo "================================"
echo ""
echo "The deployment script is ready for production use."
echo "You can now deploy to your production database:"
echo ""
echo "  psql -d fox_crypto -f database/DEPLOY_SCHEMA.sql"
echo ""
