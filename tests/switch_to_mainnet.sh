#!/bin/bash
# Switch back to mainnet configuration
# Usage: ./tests/switch_to_mainnet.sh

set -e

echo "🔄 Switching to MAINNET configuration..."

# Check if backup exists
if [ ! -f .env.mainnet.backup ]; then
    echo "⚠️  WARNING: .env.mainnet.backup not found!"
    echo "   Creating mainnet config from template..."

    # If no backup, assume we need to create mainnet config
    if [ -f .env.testnet ]; then
        cp .env.testnet .env
        echo "❌ ERROR: Please manually configure .env for mainnet"
        echo "   Set BINANCE_TESTNET=false and BYBIT_TESTNET=false"
        echo "   Set DB_NAME=fox_crypto (port 5432)"
        exit 1
    fi
fi

# Restore from backup
echo "📋 Restoring .env from .env.mainnet.backup"
cp .env.mainnet.backup .env

# Verify mainnet mode
echo ""
echo "✅ Switched to MAINNET"
echo ""
echo "Verification:"
grep -E "BINANCE_TESTNET|BYBIT_TESTNET|DB_NAME" .env || true

echo ""
echo "⚠️  REMINDER:"
echo "   - This is MAINNET mode"
echo "   - Database: fox_crypto (port 5432)"
echo "   - Exchange: Production API keys"
echo "   - USE WITH CAUTION!"
