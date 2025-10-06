#!/bin/bash
# Wave Monitor - Real-time bot activity tracking

BOT_LOG="tests/integration/bot_test.log"
SIGNAL_LOG="tests/integration/signal_generator.log"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 WAVE MONITOR - Waiting for next wave..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏰ Current time: $(date -u '+%H:%M:%S') UTC"
echo "⏰ Next wave at: XX:03 or XX:18 or XX:33 or XX:48"
echo ""
echo "📊 Monitoring logs..."
echo ""

# Get initial line counts
INITIAL_BOT_LINES=$(wc -l < "$BOT_LOG" 2>/dev/null || echo 0)

# Wait for wave (monitoring every 30 seconds)
for i in {1..25}; do
    sleep 30
    NOW=$(date -u '+%H:%M')
    MINUTE=$(date -u '+%M')
    
    # Check if it's wave time (3, 18, 33, 48 minutes)
    if [[ "$MINUTE" == "03" ]] || [[ "$MINUTE" == "18" ]] || [[ "$MINUTE" == "33" ]] || [[ "$MINUTE" == "48" ]]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🌊 WAVE DETECTED at $NOW UTC!"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Wait for processing
        sleep 45
        
        echo ""
        echo "📊 BOT ACTIVITY (last 60 lines):"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        tail -60 "$BOT_LOG" | grep -E "wave|signal|position|order|TEST|Opening|Closing" | tail -40
        
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "📈 POSITIONS CHECK:"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto -c "SELECT symbol, exchange, side, status FROM monitoring.positions ORDER BY opened_at DESC LIMIT 10;" 2>/dev/null || echo "❌ Could not query positions"
        
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "✅ WAVE PROCESSING COMPLETE"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        break
    else
        # Show waiting status every 2 minutes
        if [[ $((i % 4)) == 0 ]]; then
            CURRENT_LINES=$(wc -l < "$BOT_LOG" 2>/dev/null || echo 0)
            NEW_LINES=$((CURRENT_LINES - INITIAL_BOT_LINES))
            echo "⏳ $NOW UTC - Waiting for wave... (bot activity: +$NEW_LINES lines)"
        fi
    fi
done
