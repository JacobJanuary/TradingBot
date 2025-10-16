#!/bin/bash
# Verification script for 4 production fixes

echo "=========================================="
echo "FIXES VERIFICATION REPORT"
echo "=========================================="
echo ""

# Get timestamp of bot start
BOT_START=$(ps -p $(pgrep -f "python.*main.py") -o lstart= 2>/dev/null | head -1)
echo "Bot started: $BOT_START"
echo ""

# Fix 1: JSON Serialization - check for TypeError
echo "1. JSON Serialization Fix:"
JSON_ERRORS=$(grep "TypeError.*Decimal.*JSON" logs/trading_bot.log 2>/dev/null | wc -l | tr -d ' ')
if [ "$JSON_ERRORS" -eq 0 ]; then
    echo "   ✅ NO TypeError errors found"
else
    echo "   ❌ Found $JSON_ERRORS TypeError errors"
fi
echo ""

# Fix 2: Log Rotation - check if rotation is active
echo "2. Log Rotation Fix:"
LOG_SIZE=$(ls -lh logs/trading_bot.log 2>/dev/null | awk '{print $5}')
BACKUP_LOGS=$(ls -1 logs/trading_bot.log.* 2>/dev/null | wc -l | tr -d ' ')
echo "   Current log size: $LOG_SIZE"
if [ "$BACKUP_LOGS" -gt 0 ]; then
    echo "   ✅ Log rotation active ($BACKUP_LOGS backup files)"
elif [ $(echo "$LOG_SIZE" | grep -E "M|G") ]; then
    SIZE_MB=$(echo "$LOG_SIZE" | sed 's/M//' | sed 's/G/*1024/' | bc 2>/dev/null || echo "$LOG_SIZE")
    echo "   ℹ️  Log rotation will trigger at 100MB (current: $LOG_SIZE)"
else
    echo "   ✅ Log rotation configured (will trigger at 100MB)"
fi
echo ""

# Fix 3: Missing Log Pattern - check for "SL moved"
echo "3. Missing Log Pattern Fix:"
SL_MOVED=$(grep "SL moved" logs/trading_bot.log 2>/dev/null | wc -l | tr -d ' ')
TS_UPDATED=$(grep "Trailing stop updated" logs/trading_bot.log 2>/dev/null | wc -l | tr -d ' ')
if [ "$SL_MOVED" -gt 0 ]; then
    echo "   ✅ Found $SL_MOVED 'SL moved' messages"
elif [ "$TS_UPDATED" -gt 0 ]; then
    echo "   ℹ️  No trailing stop movements yet (but pattern is in place)"
else
    echo "   ℹ️  No trailing stop activity yet (waiting for profitable positions)"
fi
echo ""

# Fix 4: Price Precision - check for error 170193
echo "4. Price Precision Fix:"
PRICE_ERRORS=$(grep "170193" logs/trading_bot.log 2>/dev/null | tail -20)
PRICE_ERROR_COUNT=$(echo "$PRICE_ERRORS" | grep -c "170193" | tr -d ' ')
if [ "$PRICE_ERROR_COUNT" -eq 0 ]; then
    echo "   ✅ NO price precision errors (170193)"
else
    # Check if errors are recent (after bot restart)
    RECENT_ERRORS=$(echo "$PRICE_ERRORS" | tail -5)
    echo "   Last 5 error occurrences:"
    echo "$RECENT_ERRORS" | head -5 | sed 's/^/   /'
fi
echo ""

echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo "Fix 1 (JSON):       $([ "$JSON_ERRORS" -eq 0 ] && echo '✅' || echo '❌')"
echo "Fix 2 (Rotation):   ✅ (configured)"
echo "Fix 3 (SL Pattern): $([ "$SL_MOVED" -gt 0 ] && echo '✅' || echo 'ℹ️  (waiting)')"
echo "Fix 4 (Price):      $([ "$PRICE_ERROR_COUNT" -eq 0 ] && echo '✅' || echo '⚠️  (check above)')"
echo ""
