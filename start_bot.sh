#!/bin/bash
# Safe bot startup script

LOCK_FILE="/var/folders/pb/fz5jyb914bl60s5lpb_yhnc40000gn/T/trading_bot.lock"
LOG_DIR="logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "🤖 Starting Trading Bot..."

# Check if bot is already running
if pgrep -f "python.*main.py.*production" > /dev/null; then
    echo "⚠️  Bot already running!"
    echo "Current bot processes:"
    ps aux | grep "python.*main.py.*production" | grep -v grep
    echo ""
    read -p "Do you want to restart the bot? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi

    echo "🛑 Stopping current bot..."
    pkill -f "python.*main.py.*production"
    sleep 3

    # Force kill if still running
    if pgrep -f "python.*main.py.*production" > /dev/null; then
        echo "⚠️  Force killing..."
        pkill -9 -f "python.*main.py.*production"
        sleep 2
    fi
fi

# Clean up lock file
if [ -f "$LOCK_FILE" ]; then
    echo "🧹 Removing old lock file..."
    rm -f "$LOCK_FILE"
fi

# Create logs directory if not exists
mkdir -p "$LOG_DIR"

# Start bot
echo "🚀 Starting bot..."
python main.py --mode production > "$LOG_DIR/production_bot_$TIMESTAMP.log" 2>&1 &
BOT_PID=$!

# Wait a moment and check if started successfully
sleep 3

if ps -p $BOT_PID > /dev/null; then
    echo "✅ Bot started successfully!"
    echo "   PID: $BOT_PID"
    echo "   Log: $LOG_DIR/production_bot_$TIMESTAMP.log"
    echo ""
    echo "Commands:"
    echo "  - Check status: ps -p $BOT_PID"
    echo "  - View logs: tail -f $LOG_DIR/production_bot_$TIMESTAMP.log"
    echo "  - Stop bot: kill $BOT_PID"
else
    echo "❌ Failed to start bot!"
    echo "Check logs: $LOG_DIR/production_bot_$TIMESTAMP.log"
    exit 1
fi
