#!/bin/bash
# Safe bot stop script

LOCK_FILE="/var/folders/pb/fz5jyb914bl60s5lpb_yhnc40000gn/T/trading_bot.lock"

echo "🛑 Stopping Trading Bot..."

# Find all bot processes
BOT_PIDS=$(pgrep -f "python.*main.py.*production")

if [ -z "$BOT_PIDS" ]; then
    echo "ℹ️  No bot processes found"

    # Clean up lock file anyway
    if [ -f "$LOCK_FILE" ]; then
        echo "🧹 Removing orphaned lock file..."
        rm -f "$LOCK_FILE"
    fi
    exit 0
fi

echo "Found bot processes: $BOT_PIDS"

# Send SIGTERM for graceful shutdown
for PID in $BOT_PIDS; do
    echo "Sending SIGTERM to PID $PID..."
    kill $PID
done

# Wait for graceful shutdown
echo "Waiting for graceful shutdown (max 10 seconds)..."
for i in {1..10}; do
    sleep 1
    REMAINING=$(pgrep -f "python.*main.py.*production" | wc -l | tr -d ' ')
    if [ "$REMAINING" -eq 0 ]; then
        echo "✅ All bots stopped gracefully"
        break
    fi
    echo "  Still running: $REMAINING processes..."
done

# Force kill if still running
REMAINING_PIDS=$(pgrep -f "python.*main.py.*production")
if [ -n "$REMAINING_PIDS" ]; then
    echo "⚠️  Force killing remaining processes..."
    for PID in $REMAINING_PIDS; do
        kill -9 $PID
    done
    sleep 1
fi

# Final check
if pgrep -f "python.*main.py.*production" > /dev/null; then
    echo "❌ Some processes still running!"
    ps aux | grep "python.*main.py.*production" | grep -v grep
    exit 1
else
    echo "✅ All bot processes stopped"
fi

# Clean up lock file
if [ -f "$LOCK_FILE" ]; then
    echo "🧹 Removing lock file..."
    rm -f "$LOCK_FILE"
fi

echo "✅ Bot stopped successfully"
