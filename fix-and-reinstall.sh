#!/bin/bash
# Fix service to use venv Python and reinstall

set -e

echo "🔧 Fixing Trading Bot service to use venv Python..."
echo ""

# Stop service
echo "🛑 Stopping service..."
sudo systemctl stop trading-bot 2>/dev/null || true

# Copy updated service file
echo "📋 Copying updated service file..."
sudo cp /home/elcrypto/TradingBot/trading-bot.service /etc/systemd/system/trading-bot.service

# Reload systemd
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Reset failed state
echo "🔄 Resetting failed state..."
sudo systemctl reset-failed trading-bot 2>/dev/null || true

# Start service
echo "🚀 Starting service..."
sudo systemctl start trading-bot

# Wait a bit
sleep 2

echo ""
echo "✅ Service reinstalled!"
echo ""
echo "📊 Checking status..."
sudo systemctl status trading-bot --no-pager -l

echo ""
echo "To view logs:"
echo "  ./manage-service.sh logs"
