#!/bin/bash
#
# ТЕСТ #2: Глубокий анализ логов - поиск точного места потери подписки
#

echo "=============================================================================="
echo "ТЕСТ #2: ГЛУБОКИЙ АНАЛИЗ ЛОГОВ - ПОИСК МЕСТА ПОТЕРИ ПОДПИСКИ"
echo "=============================================================================="
echo ""

# 1. Анализ MARK stream reconnections
echo "📊 1. АНАЛИЗ MARK STREAM RECONNECTIONS"
echo "------------------------------------------------------------------------------"
echo "Количество reconnect за последние 24 часа:"
grep -h "\[MARK\] Connected" logs/trading_bot.log* 2>/dev/null | wc -l
echo ""

echo "Детали последних 10 reconnect:"
grep -h "\[MARK\] Connected" logs/trading_bot.log* 2>/dev/null | tail -10
echo ""

# 2. Анализ restore subscriptions
echo "📊 2. АНАЛИЗ RESTORE SUBSCRIPTIONS"
echo "------------------------------------------------------------------------------"
echo "Попытки восстановления подписок:"
grep -h "Restoring.*subscriptions" logs/trading_bot.log* 2>/dev/null | tail -10
echo ""

echo "Результаты восстановления (failures):"
grep -h "subscriptions not restored" logs/trading_bot.log* 2>/dev/null | tail -10
echo ""

# 3. Анализ конкретных символов
echo "📊 3. АНАЛИЗ ПРОБЛЕМНЫХ СИМВОЛОВ (BERAUSDT, CGPTUSDT)"
echo "------------------------------------------------------------------------------"

for SYMBOL in BERAUSDT CGPTUSDT; do
    echo ""
    echo "=== $SYMBOL ==="
    echo ""
    
    # Когда открыта
    echo "Открытие позиции:"
    grep -h "Position.*$SYMBOL opened\|opened.*$SYMBOL" logs/trading_bot.log* 2>/dev/null | head -3
    echo ""
    
    # Подписка на mark price
    echo "Подписка на mark price:"
    grep -h "\[MARK\].*$SYMBOL\|$SYMBOL.*[Ss]ubscri" logs/trading_bot.log* 2>/dev/null | head -5
    echo ""
    
    # Position updates
    echo "Position updates (первые и последние 3):"
    echo "Первые 3:"
    grep -h "Position update.*$SYMBOL" logs/trading_bot.log* 2>/dev/null | head -3
    echo "Последние 3:"
    grep -h "Position update.*$SYMBOL" logs/trading_bot.log* 2>/dev/null | tail -3
    echo ""
    
    # Aged position attempts
    echo "Aged Position механизм:"
    grep -h "Aged position $SYMBOL\|$SYMBOL.*subscription verification" logs/trading_bot.log* 2>/dev/null | tail -5
    echo ""
done

# 4. Статистика по subscription manager
echo "📊 4. SUBSCRIPTION MANAGER - СТАТИСТИКА ОШИБОК"
echo "------------------------------------------------------------------------------"
echo "Ошибки подписки:"
grep -h "Subscription error\|Failed to.*subscri" logs/trading_bot.log* 2>/dev/null | wc -l
echo ""
if grep -h "Subscription error\|Failed to.*subscri" logs/trading_bot.log* 2>/dev/null | head -5 | grep -q .; then
    echo "Примеры ошибок:"
    grep -h "Subscription error\|Failed to.*subscri" logs/trading_bot.log* 2>/dev/null | head -5
    echo ""
fi

# 5. Анализ timing - когда позиции открываются vs когда reconnect
echo "📊 5. TIMING ANALYSIS - Reconnect vs Position Opening"
echo "------------------------------------------------------------------------------"
echo "Последние 5 MARK reconnect с временем:"
grep -h "\[MARK\] Connected" logs/trading_bot.log.6 2>/dev/null | tail -5 | cut -d' ' -f1-2
echo ""
echo "Позиции открытые между reconnect (log.6):"
# Find BERAUSDT opening
echo "BERAUSDT открыта:"
grep -h "BERAUSDT opened" logs/trading_bot.log.6 2>/dev/null | cut -d' ' -f1-2
echo ""

# 6. Проверка очереди subscription_queue
echo "📊 6. SUBSCRIPTION QUEUE - ЛОГИРОВАНИЕ"
echo "------------------------------------------------------------------------------"
echo "Упоминания subscription queue:"
grep -h "subscription_queue\|subscription.*queue" logs/trading_bot.log* 2>/dev/null | wc -l
echo ""

# 7. WebSocket send failures
echo "📊 7. WEBSOCKET SEND FAILURES"
echo "------------------------------------------------------------------------------"
echo "Ошибки отправки через WebSocket:"
grep -h "send_str.*error\|WebSocket.*send.*fail\|mark_ws.*closed" logs/trading_bot.log* 2>/dev/null | wc -l
if grep -h "send_str.*error\|WebSocket.*send.*fail\|mark_ws.*closed" logs/trading_bot.log* 2>/dev/null | head -3 | grep -q .; then
    echo "Примеры:"
    grep -h "send_str.*error\|WebSocket.*send.*fail\|mark_ws.*closed" logs/trading_bot.log* 2>/dev/null | head -3
fi
echo ""

echo "=============================================================================="
echo "ВЫВОДЫ"
echo "=============================================================================="
echo ""

# Calculate restore success rate from last 10 restores
echo "Статистика восстановления подписок (последние попытки):"
grep -h "Restoring.*subscriptions\|subscriptions not restored" logs/trading_bot.log* 2>/dev/null | tail -20 | \
    awk '
    /Restoring.*subscriptions/ {
        match($0, /Restoring ([0-9]+) subscriptions/, arr);
        total = arr[1];
    }
    /not restored/ {
        match($0, /([0-9]+) subscriptions not restored/, arr);
        failed = arr[1];
        success = total - failed;
        success_rate = (success / total) * 100;
        printf "  Попытка: %d подписок, успех: %d, fail: %d (%.1f%% success)\n", total, success, failed, success_rate;
    }
    '
echo ""

