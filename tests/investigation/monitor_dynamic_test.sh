#!/bin/bash
# Monitor dynamic test progress

LOG_FILE="tests/investigation/results_dynamic.log"

echo "=================================="
echo "DYNAMIC TEST MONITOR"
echo "=================================="
echo ""

# Check if test is running
PID=$(pgrep -f "test_dynamic_subscriptions.py")
if [ -z "$PID" ]; then
    echo "❌ Test is not running!"
    echo ""
    echo "Final results:"
    tail -30 "$LOG_FILE"
    exit 1
fi

echo "✅ Test is running (PID: $PID)"
echo ""

# Show runtime
ELAPSED=$(ps -p $PID -o etime= | tr -d ' ')
echo "Runtime: $ELAPSED"
echo ""

# Show latest activity
echo "=== LATEST ACTIVITY (last 20 lines) ==="
tail -20 "$LOG_FILE"
echo ""

# Count operations
TOTAL_SUB=$(grep -c "SUBSCRIBE confirmed" "$LOG_FILE")
TOTAL_UNSUB=$(grep -c "UNSUBSCRIBE confirmed" "$LOG_FILE")
HEALTH_CHECKS=$(grep -c "HEALTH CHECK" "$LOG_FILE")
STATS=$(grep -c "5-MINUTE STATISTICS" "$LOG_FILE")

echo "==================================="
echo "STATISTICS"
echo "==================================="
echo "Total subscriptions: $TOTAL_SUB"
echo "Total unsubscriptions: $TOTAL_UNSUB"
echo "Health checks performed: $HEALTH_CHECKS"
echo "5-min stats: $STATS"
echo ""

# Show last health check
echo "=== LAST HEALTH CHECK ==="
grep -A 10 "HEALTH CHECK" "$LOG_FILE" | tail -12
echo ""

# Show any warnings/errors
WARNINGS=$(grep -c "WARNING\|SILENT FAIL" "$LOG_FILE")
if [ $WARNINGS -gt 0 ]; then
    echo "⚠️  WARNINGS/ISSUES FOUND: $WARNINGS"
    echo ""
    echo "=== WARNINGS ==="
    grep "WARNING\|SILENT FAIL\|Stale" "$LOG_FILE" | tail -10
fi

echo ""
echo "==================================="
echo "To watch live: tail -f $LOG_FILE"
echo "To stop test: kill $PID"
echo "==================================="
