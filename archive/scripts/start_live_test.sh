#!/bin/bash
# Скрипт для быстрого запуска LIVE тестирования Wave Detector

set -e  # Exit on error

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  WAVE DETECTOR LIVE TEST - PREPARATION                       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ШАГ 1: Проверка что находимся в правильной директории
if [ ! -f "main.py" ]; then
    echo -e "${RED}❌ Ошибка: main.py не найден. Запустите скрипт из корня проекта${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Корректная директория проекта${NC}"

# ШАГ 2: Остановка существующего бота
echo ""
echo "🛑 ШАГ 1: Остановка существующего бота..."
pkill -f "python.*main.py" 2>/dev/null && echo -e "${YELLOW}   Бот остановлен${NC}" || echo -e "${GREEN}   Бот не запущен${NC}"
sleep 2

# Проверка что процесс остановлен
RUNNING_PROCESSES=$(ps aux | grep -v grep | grep "python.*main.py" | wc -l)
if [ "$RUNNING_PROCESSES" -gt 0 ]; then
    echo -e "${RED}❌ Бот все еще запущен! Остановите вручную и повторите${NC}"
    exit 1
fi

# ШАГ 3: Очистка кэша Python
echo ""
echo "🧹 ШАГ 2: Очистка кэша Python..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
echo -e "${GREEN}✅ Кэш очищен${NC}"

# ШАГ 4: Проверка конфигурации
echo ""
echo "⚙️  ШАГ 3: Проверка конфигурации..."

# Проверка TESTNET
BINANCE_TESTNET=$(grep "BINANCE_TESTNET" .env | cut -d'=' -f2)
BYBIT_TESTNET=$(grep "BYBIT_TESTNET" .env | cut -d'=' -f2)

if [ "$BINANCE_TESTNET" == "true" ] && [ "$BYBIT_TESTNET" == "true" ]; then
    echo -e "${GREEN}✅ Testnet mode активен (безопасно)${NC}"
else
    echo -e "${RED}⚠️  WARNING: Не все биржи в testnet mode!${NC}"
    echo "   BINANCE_TESTNET=$BINANCE_TESTNET"
    echo "   BYBIT_TESTNET=$BYBIT_TESTNET"
    echo ""
    read -p "Продолжить тестирование? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Тестирование отменено"
        exit 0
    fi
fi

# Показать ключевые параметры
POSITION_SIZE=$(grep "POSITION_SIZE_USD" .env | cut -d'=' -f2)
MAX_TRADES=$(grep "MAX_TRADES_PER_15MIN" .env | cut -d'=' -f2)
WAVE_MINUTES=$(grep "WAVE_CHECK_MINUTES" .env | cut -d'=' -f2)

echo ""
echo "📊 Конфигурация теста:"
echo "   Размер позиции: $POSITION_SIZE USD"
echo "   Макс позиций за волну: $MAX_TRADES"
echo "   Проверка волн: $WAVE_MINUTES минуты часа"
echo ""

# ШАГ 5: Финальное подтверждение
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  ГОТОВ К ЗАПУСКУ                                             ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "Диагностика запустит бота в PRODUCTION MODE на 15+ минут"
echo "Будет создан детальный отчет с проверкой reduceOnly параметра"
echo ""
read -p "Начать тестирование? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Тестирование отменено"
    exit 0
fi

# ШАГ 6: Запуск диагностики
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  ЗАПУСК LIVE ДИАГНОСТИКИ                                     ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "⏰ Тестирование начато: $(date '+%H:%M:%S')"
echo "⏱️  Примерное время завершения: $(date -v+17M '+%H:%M:%S' 2>/dev/null || date -d '+17 minutes' '+%H:%M:%S' 2>/dev/null || echo '~17 минут')"
echo ""
echo "📝 Логи сохраняются в: wave_detector_live_diagnostic.log"
echo "💡 Для прерывания нажмите Ctrl+C"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Запуск диагностического скрипта
python monitor_wave_detector_live.py

# ШАГ 7: Завершение
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  ТЕСТИРОВАНИЕ ЗАВЕРШЕНО                                      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "📄 Результаты доступны в:"
echo "   - wave_detector_live_diagnostic.log (детальные логи)"
echo "   - Консольный отчет выше ↑"
echo ""
echo -e "${GREEN}✅ Диагностика завершена${NC}"
