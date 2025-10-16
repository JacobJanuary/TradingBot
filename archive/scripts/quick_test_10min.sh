#!/bin/bash

echo "=== Age Detector 10-Minute Test ==="
echo "Start: $(cat test_start_time_v2.txt)"
echo "Interval: 2 minutes between Age Detector cycles"
echo ""

for i in {1..5}; do
    min=$((i * 2))
    echo "==================================================="
    echo "MINUTE $min - $(date '+%H:%M:%S')"
    echo "==================================================="

    # Wait 2 minutes (except first iteration - wait 2.5min to catch first cycle)
    if [ $i -eq 1 ]; then
        echo "Waiting 2.5 minutes for first Age Detector cycle..."
        sleep 150
    else
        echo "Waiting 2 minutes..."
        sleep 120
    fi

    echo ""
    echo "📊 METRICS (cumulative since test start):"
    echo "  Creating initial: $(tail -n 2000 logs/trading_bot.log | grep -c 'Creating limit exit order')"
    echo "  Order exists (from create_limit_exit_order): $(tail -n 2000 logs/trading_bot.log | grep -c 'Exit order already exists')"
    echo "  Updating order (from create_or_update): $(tail -n 2000 logs/trading_bot.log | grep -c 'Updating exit order')"
    echo "  Keeping existing (debug): $(tail -n 2000 logs/trading_bot.log | grep -c 'keeping existing')"
    echo ""

    echo "📝 Last 5 Age Detector events:"
    tail -n 300 logs/trading_bot.log | grep -E "(Processing aged position|Creating limit exit|Exit order already|Updating exit order|keeping existing)" | tail -5
    echo ""

    # Check for cycles
    cycles=$(tail -n 2000 logs/trading_bot.log | grep -c "Aged positions processed:")
    echo "🔄 Age Detector cycles completed: $cycles"
    if [ $cycles -ge 2 ]; then
        echo "✅ Multiple cycles detected - checking for duplicate prevention..."
    fi
    echo ""
done

echo "==================================================="
echo "TEST COMPLETE - $(date '+%H:%M:%S')"
echo "==================================================="
echo ""
echo "📈 FINAL ANALYSIS:"
python monitor_age_detector.py logs/trading_bot.log
