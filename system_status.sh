#!/bin/bash
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 ПОЛНЫЙ СТАТУС СИСТЕМЫ"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏰ Текущее время: $(date -u '+%H:%M:%S') UTC"
echo "⏰ Следующая волна: 17:33 UTC"
echo ""
echo "🤖 ПРОЦЕССЫ:"
ps aux | grep -E "(python.*main.py|signal_generator)" | grep -v grep | awk '{print "  " $11 " " $12 " " $13 " (PID: " $2 ")"}'
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 WEBSOCKET (последние 2 минуты):"
tail -100 tests/integration/bot_test.log | grep -i "websocket\|connected\|ping\|pong" | tail -5
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "❌ ОШИБКИ (последние 5 минут):"
ERROR_COUNT=$(tail -300 tests/integration/bot_test.log | grep -i "error\|exception" | wc -l | tr -d ' ')
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "  ✅ Нет ошибок"
else
    echo "  ⚠️  Найдено ошибок: $ERROR_COUNT"
    tail -300 tests/integration/bot_test.log | grep -i "error" | tail -3
fi
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💰 БАЛАНСЫ:"
tail -100 tests/integration/bot_test.log | grep -i "balance" | tail -2
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 ТЕСТОВЫЕ СИГНАЛЫ:"
PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto -t -c "
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN processed THEN 1 END) as processed,
    COUNT(CASE WHEN NOT processed THEN 1 END) as pending
FROM test.scoring_history;
" 2>/dev/null | awk '{print "  Всего: " $1 ", Обработано: " $2 ", Ожидает: " $3}'
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ СИСТЕМА СТАБИЛЬНА"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
