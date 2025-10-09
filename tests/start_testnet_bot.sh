#!/bin/bash
# Quick start bot in testnet mode
# Usage: ./tests/start_testnet_bot.sh [mode]
#   mode: shadow (default) or production

set -e

MODE="${1:-shadow}"

echo "🚀 Starting Trading Bot in TESTNET mode"
echo "Mode: $MODE"
echo ""

# Check if already running
if pgrep -f "python.*main.py" > /dev/null; then
    echo "⚠️  WARNING: Bot is already running!"
    echo ""
    ps aux | grep -E "python.*main.py" | grep -v grep
    echo ""
    read -p "Kill existing bot and continue? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔪 Killing existing bot..."
        pkill -f "python.*main.py" || true
        sleep 2
    else
        echo "❌ Aborted"
        exit 1
    fi
fi

# Verify testnet config
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found!"
    echo "Run: ./tests/switch_to_testnet.sh first"
    exit 1
fi

# Check for testnet indicators
if ! grep -q "TESTNET=true" .env; then
    echo "⚠️  WARNING: .env does not appear to be testnet configuration!"
    echo ""
    grep -E "TESTNET|DB_NAME" .env || true
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted"
        echo "Run: ./tests/switch_to_testnet.sh to switch to testnet"
        exit 1
    fi
fi

# Validate mode
if [[ ! "$MODE" =~ ^(shadow|production|backtest)$ ]]; then
    echo "❌ ERROR: Invalid mode '$MODE'"
    echo "Valid modes: shadow, production, backtest"
    exit 1
fi

echo ""
echo "✅ Pre-flight checks passed"
echo ""
echo "Starting bot with:"
echo "  Mode: $MODE"
echo "  Config: .env (testnet)"
echo "  Logs: logs/trading_bot.log"
echo ""
echo "To monitor:"
echo "  Terminal 1: tail -f logs/trading_bot.log"
echo "  Terminal 2: ./tests/monitor_positions.sh"
echo "  Terminal 3: ps aux | grep python"
echo ""
echo "Starting in 3 seconds... (Ctrl+C to cancel)"
sleep 3

# Start bot
echo "🎬 Starting bot..."
python3 main.py --mode "$MODE"
