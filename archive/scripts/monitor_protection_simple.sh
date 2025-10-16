#!/bin/bash

# Simple Protection Guard Monitor via logs
# Runs for 10 minutes and monitors bot_protection_test.log

echo "================================================================================"
echo "🔍 PROTECTION GUARD LIVE MONITORING (via logs)"
echo "Начало: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Длительность: 10 минут"
echo "================================================================================"
echo ""

START_TIME=$(date +%s)
END_TIME=$((START_TIME + 600))  # 10 minutes
ITERATION=0

while [ $(date +%s) -lt $END_TIME ]; do
    ITERATION=$((ITERATION + 1))
    ELAPSED=$(($(date +%s) - START_TIME))

    echo ""
    echo "================================================================================"
    echo "⏱️  ПРОВЕРКА #$ITERATION | Прошло: ${ELAPSED}с / 600с"
    echo "================================================================================"

    echo ""
    echo "📊 Статистика за последние 30 секунд:"

    # Get log lines from last 30 seconds
    LAST_LINES=$(tail -200 bot_protection_test.log | tail -100)

    # Count different events
    SL_CHECKS=$(echo "$LAST_LINES" | grep -c "has_stop_loss\|check.*stop" || true)
    SL_CREATED=$(echo "$LAST_LINES" | grep -c "Setting Stop Loss\|stop_loss_created" || true)
    SL_ERRORS=$(echo "$LAST_LINES" | grep -c "stop_loss_error\|Failed to set Stop Loss" || true)
    POSITIONS_CHECKED=$(echo "$LAST_LINES" | grep -c "position_check\|check_positions_protection" || true)

    echo "   SL проверок:              $SL_CHECKS"
    echo "   SL создается:             $SL_CREATED"
    echo "   Ошибок SL:                $SL_ERRORS"
    echo "   Позиций проверено:        $POSITIONS_CHECKED"

    echo ""
    echo "🎯 Последние важные события:"

    # Show last important log lines
    echo "$LAST_LINES" | grep -E "stop_loss|protection|Failed to set" | tail -5 | while read line; do
        # Extract timestamp and message
        timestamp=$(echo "$line" | awk '{print $1, $2}' | cut -d',' -f1)
        message=$(echo "$line" | cut -d'-' -f4-)
        echo "   [$timestamp] $message"
    done

    # Every 2 minutes (4 iterations), check positions status
    if [ $((ITERATION % 4)) -eq 0 ]; then
        echo ""
        echo "🔎 Проверка позиций БЕЗ SL (последние предупреждения):"
        WITHOUT_SL=$(echo "$LAST_LINES" | grep -i "without.*stop\|no stop loss" | tail -3)
        if [ -z "$WITHOUT_SL" ]; then
            echo "   ✅ Нет недавних предупреждений о позициях без SL"
        else
            echo "$WITHOUT_SL" | while read line; do
                echo "   ⚠️  $line"
            done
        fi
    fi

    # Wait 30 seconds
    if [ $(date +%s) -lt $END_TIME ]; then
        echo ""
        echo "⏳ Ожидание 30 секунд до следующей проверки..."
        sleep 30
    fi
done

echo ""
echo "================================================================================"
echo "✅ МОНИТОРИНГ ЗАВЕРШЕН"
echo "================================================================================"
echo ""
echo "📊 ИТОГОВАЯ СТАТИСТИКА (10 минут):"

# Get all logs from the monitoring period
ALL_LINES=$(tail -1000 bot_protection_test.log)

TOTAL_SL_CHECKS=$(echo "$ALL_LINES" | grep -c "has_stop_loss\|check.*stop" || true)
TOTAL_SL_CREATED=$(echo "$ALL_LINES" | grep -c "Setting Stop Loss\|stop_loss_created" || true)
TOTAL_SL_ERRORS=$(echo "$ALL_LINES" | grep -c "stop_loss_error\|Failed to set Stop Loss" || true)
TOTAL_POSITIONS=$(echo "$ALL_LINES" | grep -c "position_check\|check_positions_protection" || true)

echo "   SL проверок:              $TOTAL_SL_CHECKS"
echo "   SL создано:               $TOTAL_SL_CREATED"
echo "   Ошибок SL:                $TOTAL_SL_ERRORS"
echo "   Позиций проверено:        $TOTAL_POSITIONS"

echo ""
echo "================================================================================"
echo "Завершено: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================================"
