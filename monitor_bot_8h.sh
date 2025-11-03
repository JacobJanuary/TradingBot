#!/bin/bash

# 8-Hour Bot Monitoring Script
# Reports every 10 minutes (48 cycles total)

LOGFILE="logs/trading_bot.log"
REPORT_FILE="monitoring_report_8h.log"
INTERVAL=600  # 10 minutes
CYCLES=48     # 8 hours = 48 * 10 minutes
DB_USER="tradingbot"
DB_NAME="tradingbot_db"
DB_HOST="localhost"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "🔍 Starting 8-hour monitoring at $(date)" | tee -a "$REPORT_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

START_TIME=$(date +%s)

for ((cycle=1; cycle<=CYCLES; cycle++)); do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    ELAPSED_MIN=$((ELAPSED / 60))

    echo "" | tee -a "$REPORT_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$REPORT_FILE"
    echo "📊 CYCLE $cycle/48 - Time: $(date '+%Y-%m-%d %H:%M:%S') - Elapsed: ${ELAPSED_MIN}m" | tee -a "$REPORT_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$REPORT_FILE"

    # Get timestamp for last 10 minutes
    SINCE_TIME=$(date -d '10 minutes ago' '+%Y-%m-%d %H:%M')

    # 1. Check for ERRORS
    echo "" | tee -a "$REPORT_FILE"
    echo "❌ ERRORS (last 10 min):" | tee -a "$REPORT_FILE"
    ERROR_COUNT=$(grep -i "ERROR" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -1000 | wc -l)

    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "   Found $ERROR_COUNT errors:" | tee -a "$REPORT_FILE"
        grep -i "ERROR" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -10 | sed 's/^/   /' | tee -a "$REPORT_FILE"
    else
        echo "   ✅ No errors" | tee -a "$REPORT_FILE"
    fi

    # 2. Check for WARNINGS
    echo "" | tee -a "$REPORT_FILE"
    echo "⚠️  WARNINGS (last 10 min):" | tee -a "$REPORT_FILE"
    WARNING_COUNT=$(grep -i "WARNING" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -1000 | wc -l)

    if [ "$WARNING_COUNT" -gt 0 ]; then
        echo "   Found $WARNING_COUNT warnings:" | tee -a "$REPORT_FILE"
        grep -i "WARNING" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -5 | sed 's/^/   /' | tee -a "$REPORT_FILE"
    else
        echo "   ✅ No warnings" | tee -a "$REPORT_FILE"
    fi

    # 3. Check for Position Openings
    echo "" | tee -a "$REPORT_FILE"
    echo "📈 POSITION OPENINGS (last 10 min):" | tee -a "$REPORT_FILE"
    POSITION_OPENS=$(grep -i "position opened\|opening position" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -10 | wc -l)

    if [ "$POSITION_OPENS" -gt 0 ]; then
        echo "   ✅ $POSITION_OPENS positions opened:" | tee -a "$REPORT_FILE"
        grep -i "position opened\|opening position" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -5 | sed 's/^/   /' | tee -a "$REPORT_FILE"
    else
        echo "   ℹ️  No new positions" | tee -a "$REPORT_FILE"
    fi

    # 4. Check for TS Activations
    echo "" | tee -a "$REPORT_FILE"
    echo "🎯 TRAILING STOP ACTIVATIONS (last 10 min):" | tee -a "$REPORT_FILE"
    TS_ACTIVATIONS=$(grep -i "TS ACTIVATED\|trailing stop activated" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -10 | wc -l)

    if [ "$TS_ACTIVATIONS" -gt 0 ]; then
        echo "   ✅ $TS_ACTIVATIONS TS activated:" | tee -a "$REPORT_FILE"
        grep -i "TS ACTIVATED\|trailing stop activated" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -10 | sed 's/^/   /' | tee -a "$REPORT_FILE"
    else
        echo "   ℹ️  No TS activations" | tee -a "$REPORT_FILE"
    fi

    # 5. Check for TS Updates
    echo "" | tee -a "$REPORT_FILE"
    echo "🔄 TRAILING STOP UPDATES (last 10 min):" | tee -a "$REPORT_FILE"
    TS_UPDATES=$(grep -i "trailing_stop_updated" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -10 | wc -l)

    if [ "$TS_UPDATES" -gt 0 ]; then
        echo "   ✅ $TS_UPDATES TS updates" | tee -a "$REPORT_FILE"
    else
        echo "   ℹ️  No TS updates" | tee -a "$REPORT_FILE"
    fi

    # 6. Check for Aged Position Cleanup
    echo "" | tee -a "$REPORT_FILE"
    echo "🧹 AGED POSITION CLEANUP (last 10 min):" | tee -a "$REPORT_FILE"
    AGED_CLEANUP=$(grep -i "aged position\|cleaning aged\|removed aged" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -10 | wc -l)

    if [ "$AGED_CLEANUP" -gt 0 ]; then
        echo "   ✅ $AGED_CLEANUP aged positions processed:" | tee -a "$REPORT_FILE"
        grep -i "aged position\|cleaning aged\|removed aged" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -5 | sed 's/^/   /' | tee -a "$REPORT_FILE"
    else
        echo "   ℹ️  No aged position cleanup" | tee -a "$REPORT_FILE"
    fi

    # 7. Check for Price Updates
    echo "" | tee -a "$REPORT_FILE"
    echo "💹 PRICE UPDATES (last 10 min):" | tee -a "$REPORT_FILE"
    PRICE_UPDATES=$(grep -i "price update\|updated price" "$LOGFILE" | grep "$(date '+%Y-%m-%d')" | tail -100 | wc -l)
    echo "   ℹ️  $PRICE_UPDATES price updates received" | tee -a "$REPORT_FILE"

    # 8. Database Stats
    echo "" | tee -a "$REPORT_FILE"
    echo "📊 DATABASE STATS:" | tee -a "$REPORT_FILE"

    # Active positions
    ACTIVE_POS=$(PGPASSWORD='' psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM monitoring.positions WHERE status='active';" 2>/dev/null | tr -d ' ')
    echo "   Active positions: $ACTIVE_POS" | tee -a "$REPORT_FILE"

    # Active TS
    ACTIVE_TS=$(PGPASSWORD='' psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM monitoring.trailing_stop_state WHERE state='active';" 2>/dev/null | tr -d ' ')
    echo "   Active TS: $ACTIVE_TS" | tee -a "$REPORT_FILE"

    # Total TS
    TOTAL_TS=$(PGPASSWORD='' psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM monitoring.trailing_stop_state;" 2>/dev/null | tr -d ' ')
    echo "   Total TS: $TOTAL_TS" | tee -a "$REPORT_FILE"

    # 9. Bot Health Check
    echo "" | tee -a "$REPORT_FILE"
    echo "🏥 BOT HEALTH:" | tee -a "$REPORT_FILE"

    BOT_PID=$(pgrep -f "python.*main.py" | head -1)
    if [ -n "$BOT_PID" ]; then
        echo "   ✅ Bot is running (PID: $BOT_PID)" | tee -a "$REPORT_FILE"

        # CPU and Memory usage
        CPU_USAGE=$(ps -p "$BOT_PID" -o %cpu --no-headers | tr -d ' ')
        MEM_USAGE=$(ps -p "$BOT_PID" -o %mem --no-headers | tr -d ' ')
        echo "   CPU: ${CPU_USAGE}% | Memory: ${MEM_USAGE}%" | tee -a "$REPORT_FILE"
    else
        echo "   ❌ Bot is NOT running!" | tee -a "$REPORT_FILE"
    fi

    # 10. Summary
    echo "" | tee -a "$REPORT_FILE"
    echo "📝 SUMMARY:" | tee -a "$REPORT_FILE"

    if [ "$ERROR_COUNT" -eq 0 ] && [ "$WARNING_COUNT" -lt 5 ] && [ -n "$BOT_PID" ]; then
        echo "   ✅ All systems operational" | tee -a "$REPORT_FILE"
    elif [ "$ERROR_COUNT" -gt 0 ]; then
        echo "   ⚠️  Errors detected - review required" | tee -a "$REPORT_FILE"
    elif [ -z "$BOT_PID" ]; then
        echo "   ❌ CRITICAL: Bot is down!" | tee -a "$REPORT_FILE"
    else
        echo "   ⚠️  Minor issues detected" | tee -a "$REPORT_FILE"
    fi

    # Wait 10 minutes before next cycle (except on last cycle)
    if [ "$cycle" -lt "$CYCLES" ]; then
        echo "" | tee -a "$REPORT_FILE"
        echo "⏳ Waiting 10 minutes until next check..." | tee -a "$REPORT_FILE"
        sleep "$INTERVAL"
    fi
done

echo "" | tee -a "$REPORT_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$REPORT_FILE"
echo "🏁 8-hour monitoring completed at $(date)" | tee -a "$REPORT_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$REPORT_FILE"
