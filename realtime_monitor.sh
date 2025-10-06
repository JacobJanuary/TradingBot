#!/bin/bash

BOT_LOG="tests/integration/bot_test.log"
WAVE_TIME="17:48"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 REAL-TIME MONITOR - ФИНАЛЬНЫЙ ТЕСТ"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏰ Текущее время: $(date -u '+%H:%M:%S') UTC"
echo "⏰ Целевая волна: $WAVE_TIME UTC"
echo "⏳ Ожидание: ~$((48 - $(date -u '+%M'))) минут"
echo ""
echo "✅ БОТ: $(ps aux | grep 'python.*main.py' | grep -v grep | awk '{print "PID " $2}')"
echo "✅ GENERATOR: $(ps aux | grep 'signal_generator' | grep -v grep | awk '{print "PID " $2}')"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏳ Мониторинг активности каждые 30 секунд..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

INITIAL_LINES=$(wc -l < "$BOT_LOG")

# Monitor until wave time
while true; do
    CURRENT_TIME=$(date -u '+%H:%M')
    MINUTE=$(date -u '+%M')
    SECOND=$(date -u '+%S')
    
    # Show activity every 30 seconds
    if [[ "$SECOND" == "00" ]] || [[ "$SECOND" == "30" ]]; then
        CURRENT_LINES=$(wc -l < "$BOT_LOG")
        NEW_LINES=$((CURRENT_LINES - INITIAL_LINES))
        
        # Check for errors
        RECENT_ERRORS=$(tail -50 "$BOT_LOG" | grep -i "error" | wc -l | tr -d ' ')
        
        ERROR_INDICATOR="✅"
        if [ "$RECENT_ERRORS" -gt 0 ]; then
            ERROR_INDICATOR="⚠️ $RECENT_ERRORS errors"
        fi
        
        echo "$CURRENT_TIME UTC | Activity: +$NEW_LINES lines | $ERROR_INDICATOR"
    fi
    
    # Check if wave time reached
    if [[ "$MINUTE" == "48" ]]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🌊 ВОЛНА $WAVE_TIME НАЧАЛАСЬ!"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        break
    fi
    
    sleep 5
done

# Wait for processing
echo "⏳ Ожидание обработки (90 секунд)..."
sleep 90

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 РЕЗУЛЬТАТЫ ОБРАБОТКИ:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check signal processing
echo "🔍 Обработка сигналов:"
tail -150 "$BOT_LOG" | grep -E "wave.*17:30|signals.*fetch|filtered.*signal|Opening position" | tail -10
echo ""

# Check for errors
ERROR_COUNT=$(tail -150 "$BOT_LOG" | grep -i "error" | wc -l | tr -d ' ')
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "❌ ОШИБКИ ($ERROR_COUNT):"
    tail -150 "$BOT_LOG" | grep -i "error" | tail -5
    echo ""
else
    echo "✅ Ошибок нет"
    echo ""
fi

# Check positions in database
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 ОТКРЫТЫЕ ПОЗИЦИИ:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto -c "
SELECT 
    symbol, 
    exchange, 
    side, 
    ROUND(quantity::numeric, 4) as qty,
    ROUND(entry_price::numeric, 2) as entry,
    has_stop_loss as sl,
    TO_CHAR(opened_at AT TIME ZONE 'UTC', 'HH24:MI:SS') as opened_utc
FROM monitoring.positions 
WHERE status = 'open' AND opened_at > NOW() - INTERVAL '10 minutes'
ORDER BY opened_at DESC 
LIMIT 10;
" 2>/dev/null

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 СТАТИСТИКА СИГНАЛОВ:"
PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto -t -c "
SELECT 
    'Всего: ' || COUNT(*) || ' | Обработано: ' || SUM(CASE WHEN processed THEN 1 ELSE 0 END) || ' | Ожидает: ' || SUM(CASE WHEN NOT processed THEN 1 ELSE 0 END)
FROM test.scoring_history;
" 2>/dev/null

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 ТЕСТ ЗАВЕРШЕН!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
