#!/bin/bash

# Test monitoring script for 10 minutes
START_TIME=$(cat test_start_time.txt)
echo "=== Age Detector Fix - 10 Minute Test ==="
echo "Start time: $START_TIME"
echo "Bot PID: 98558"
echo ""

# Function to check logs
check_logs() {
    local minute=$1
    echo "=== Check at minute $minute ==="
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # Count key log messages
    echo "📊 Order Activity (last 2 minutes):"
    tail -n 1000 logs/trading_bot.log | grep -i "aged\|exit order" | tail -20
    echo ""

    # Count specific patterns
    echo "📈 Metrics:"
    echo "  Creating initial exit order: $(tail -n 1000 logs/trading_bot.log | grep -c 'Creating initial exit order')"
    echo "  Exit order already exists: $(tail -n 1000 logs/trading_bot.log | grep -c 'Exit order already exists')"
    echo "  Updating exit order: $(tail -n 1000 logs/trading_bot.log | grep -c 'Updating exit order')"
    echo ""
}

# Monitor for 10 minutes with checks every 2 minutes
for i in {1..5}; do
    minutes=$((i * 2))
    sleep 120  # Wait 2 minutes
    check_logs $minutes
done

echo "=== Test Complete ==="
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "Running full analysis with monitor_age_detector.py..."
python monitor_age_detector.py logs/trading_bot.log
