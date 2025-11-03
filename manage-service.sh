#!/bin/bash
# Manage Trading Bot service

case "$1" in
    start)
        echo "🚀 Starting Trading Bot..."
        sudo systemctl start trading-bot
        echo "✅ Bot started"
        ;;
    stop)
        echo "🛑 Stopping Trading Bot..."
        sudo systemctl stop trading-bot
        echo "✅ Bot stopped"
        ;;
    restart)
        echo "🔄 Restarting Trading Bot..."
        sudo systemctl restart trading-bot
        echo "✅ Bot restarted"
        ;;
    status)
        sudo systemctl status trading-bot
        ;;
    logs)
        echo "📜 Showing live logs (Ctrl+C to exit)..."
        sudo journalctl -u trading-bot -f
        ;;
    logs-today)
        echo "📜 Showing today's logs..."
        sudo journalctl -u trading-bot --since today
        ;;
    enable)
        echo "✅ Enabling auto-start on boot..."
        sudo systemctl enable trading-bot
        echo "✅ Auto-start enabled"
        ;;
    disable)
        echo "❌ Disabling auto-start on boot..."
        sudo systemctl disable trading-bot
        echo "✅ Auto-start disabled"
        ;;
    uninstall)
        echo "🗑️  Uninstalling service..."
        sudo systemctl stop trading-bot 2>/dev/null || true
        sudo systemctl disable trading-bot 2>/dev/null || true
        sudo rm -f /etc/systemd/system/trading-bot.service
        sudo systemctl daemon-reload
        echo "✅ Service uninstalled"
        ;;
    *)
        echo "Trading Bot Service Manager"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|logs-today|enable|disable|uninstall}"
        echo ""
        echo "Commands:"
        echo "  start        - Start the bot"
        echo "  stop         - Stop the bot"
        echo "  restart      - Restart the bot"
        echo "  status       - Show service status"
        echo "  logs         - Show live logs (tail -f)"
        echo "  logs-today   - Show today's logs"
        echo "  enable       - Enable auto-start on boot"
        echo "  disable      - Disable auto-start on boot"
        echo "  uninstall    - Remove service completely"
        exit 1
        ;;
esac
