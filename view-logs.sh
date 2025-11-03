#!/bin/bash
# Простой просмотр логов бота

echo "🔍 Выберите, какие логи посмотреть:"
echo ""
echo "1. Живые логи бота (обновляются в реальном времени)"
echo "2. Последние 50 строк логов"
echo "3. Последние 100 строк логов"
echo "4. Логи с ошибками"
echo "5. Логи systemd (journalctl)"
echo "6. Все файлы логов"
echo ""
read -p "Выберите (1-6): " choice

case $choice in
    1)
        echo "📜 Живые логи (Ctrl+C для выхода)..."
        tail -f logs/trading_bot.log
        ;;
    2)
        echo "📜 Последние 50 строк:"
        tail -n 50 logs/trading_bot.log
        ;;
    3)
        echo "📜 Последние 100 строк:"
        tail -n 100 logs/trading_bot.log
        ;;
    4)
        echo "📜 Логи с ошибками (ERROR/CRITICAL):"
        grep -E "(ERROR|CRITICAL)" logs/trading_bot.log | tail -n 50
        ;;
    5)
        echo "📜 Systemd логи (требует sudo):"
        sudo journalctl -u trading-bot -n 50 --no-pager
        ;;
    6)
        echo "📂 Список всех файлов логов:"
        ls -lh logs/*.log
        echo ""
        echo "Просмотр:"
        echo "  trading_bot.log - основной лог бота"
        echo "  systemd-error.log - stderr сервиса"
        echo "  systemd-output.log - stdout сервиса"
        ;;
    *)
        echo "❌ Неверный выбор"
        exit 1
        ;;
esac
