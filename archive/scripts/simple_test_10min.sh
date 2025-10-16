#!/bin/bash

echo "=== AGE DETECTOR FIX - 10 MINUTE TEST ==="
echo "Start: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Bot PID: 99448"
echo "Check interval: every 2.5 minutes"
echo ""

# Wait for first cycle and check
for check in {1..4}; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "CHECK #$check at $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Wait 2.5 minutes
    if [ $check -eq 1 ]; then
        echo "⏳ Waiting 2.5 min for first Age Detector cycle..."
        sleep 150
    else
        echo "⏳ Waiting 2.5 min..."
        sleep 150
    fi

    echo ""
    echo "📊 METRICS (since bot restart):"
    tail -n 5000 logs/trading_bot.log | grep -c "Aged positions processed" | xargs echo "  Age Detector cycles:"
    tail -n 5000 logs/trading_bot.log | grep -c "Creating limit exit order" | xargs echo "  Orders created:"
    tail -n 5000 logs/trading_bot.log | grep -c "Exit order already exists" | xargs echo "  Duplicates prevented:"
    tail -n 5000 logs/trading_bot.log | grep -c "Updating exit order.*diff" | xargs echo "  Orders updated:"

    echo ""
    echo "📝 Last Age Detector cycle:"
    tail -n 1000 logs/trading_bot.log | grep "Aged positions processed" | tail -1

    echo ""
    echo "🔍 Last 3 aged position events:"
    tail -n 500 logs/trading_bot.log | grep -E "(Processing aged position|Creating limit exit|Updating exit order)" | tail -3
    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST COMPLETE at $(date '+%H:%M:%S')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎯 RUNNING FULL ANALYSIS..."
python monitor_age_detector.py logs/trading_bot.log
