#!/bin/bash
# Install Trading Bot systemd service

set -e

echo "🚀 Installing Trading Bot systemd service..."

# Check if running as non-root
if [ "$EUID" -eq 0 ]; then 
    echo "❌ Please run this script as a regular user (not root)"
    echo "   The script will use sudo when needed"
    exit 1
fi

# Check if service file exists
if [ ! -f "trading-bot.service" ]; then
    echo "❌ Error: trading-bot.service file not found"
    exit 1
fi

# Stop existing service if running
echo "📛 Stopping existing service (if running)..."
sudo systemctl stop trading-bot 2>/dev/null || true

# Copy service file to systemd directory
echo "📋 Copying service file to /etc/systemd/system/..."
sudo cp trading-bot.service /etc/systemd/system/trading-bot.service

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable service (auto-start on boot)
echo "✅ Enabling service to start on boot..."
sudo systemctl enable trading-bot

# Show service status
echo ""
echo "✅ Service installed successfully!"
echo ""
echo "Available commands:"
echo "  sudo systemctl start trading-bot     - Start the bot"
echo "  sudo systemctl stop trading-bot      - Stop the bot"
echo "  sudo systemctl restart trading-bot   - Restart the bot"
echo "  sudo systemctl status trading-bot    - Check status"
echo "  sudo journalctl -u trading-bot -f    - View live logs"
echo ""
echo "To start the bot now, run:"
echo "  sudo systemctl start trading-bot"
