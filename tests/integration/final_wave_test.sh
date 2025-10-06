#!/bin/bash
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 FINAL WAVE TEST - Waiting for 17:18 UTC..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏰ Current time: $(date -u '+%H:%M:%S') UTC"
echo ""

# Wait until 17:18
while true; do
    MINUTE=$(date -u '+%M')
    SECOND=$(date -u '+%S')
    
    if [[ "$MINUTE" == "18" ]]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🌊 WAVE 17:18 DETECTED!"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        break
    fi
    
    # Show countdown every 30 seconds
    if [[ "$SECOND" == "00" ]] || [[ "$SECOND" == "30" ]]; then
        echo "⏳ $(date -u '+%H:%M:%S') - Waiting for wave..."
    fi
    
    sleep 5
done

# Wait for processing (60 seconds)
echo "⏳ Waiting 60 seconds for signal processing..."
sleep 60

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 BOT ACTIVITY:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
tail -100 tests/integration/bot_test.log | grep -E "17:18|17:19|wave|signal.*fetched|Opening position|stop.loss|Error" | tail -50

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 OPEN POSITIONS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto -c "
SELECT 
    symbol, 
    exchange, 
    side, 
    quantity,
    entry_price,
    has_stop_loss,
    status,
    opened_at AT TIME ZONE 'UTC' as opened_at_utc
FROM monitoring.positions 
WHERE status = 'open'
ORDER BY opened_at DESC 
LIMIT 20;
" 2>/dev/null || echo "❌ Could not query positions"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 SIGNAL PROCESSOR STATS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
tail -50 tests/integration/bot_test.log | grep -E "signals.*filtered|signals.*processed|Wave signals" | tail -10

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ TEST COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
