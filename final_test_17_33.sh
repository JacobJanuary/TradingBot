#!/bin/bash
echo "🎯 Ожидание волны 17:33 UTC..."
echo ""

# Wait until 17:33
while true; do
    MINUTE=$(date -u '+%M')
    if [[ "$MINUTE" == "33" ]]; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🌊 ВОЛНА 17:33 НАЧАЛАСЬ!"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        break
    fi
    echo "⏳ $(date -u '+%H:%M:%S') - ждем волну..."
    sleep 10
done

# Wait for processing
sleep 90

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 РЕЗУЛЬТАТЫ ОБРАБОТКИ ВОЛНЫ:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for signals fetched
SIGNALS_FETCHED=$(tail -150 tests/integration/bot_test.log | grep -i "signals fetched\|wave signals" | tail -1)
echo "Сигналы: $SIGNALS_FETCHED"
echo ""

# Check for errors
ERROR_COUNT=$(tail -150 tests/integration/bot_test.log | grep -i "error" | wc -l | tr -d ' ')
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "❌ Ошибки ($ERROR_COUNT):"
    tail -150 tests/integration/bot_test.log | grep -i "error" | tail -5
else
    echo "✅ Ошибок нет"
fi
echo ""

# Check positions
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 ОТКРЫТЫЕ ПОЗИЦИИ:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto -c "
SELECT symbol, exchange, side, quantity, entry_price, has_stop_loss
FROM monitoring.positions 
WHERE status = 'open' AND opened_at > NOW() - INTERVAL '5 minutes'
ORDER BY opened_at DESC;
" 2>/dev/null

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 АКТИВНОСТЬ БОТА (последние действия):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
tail -80 tests/integration/bot_test.log | grep -E "Opening|Closing|stop.loss|position.*created" | tail -10

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ТЕСТ ЗАВЕРШЕН"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
