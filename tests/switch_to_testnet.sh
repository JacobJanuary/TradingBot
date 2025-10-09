#!/bin/bash
# Switch to testnet configuration
# Usage: ./tests/switch_to_testnet.sh

set -e

echo "🔄 Switching to TESTNET configuration..."

# Backup current .env
if [ -f .env ]; then
    echo "📦 Backing up current .env to .env.mainnet.backup"
    cp .env .env.mainnet.backup
fi

# Copy testnet config
if [ ! -f .env.testnet ]; then
    echo "❌ ERROR: .env.testnet not found!"
    exit 1
fi

echo "📋 Copying .env.testnet to .env"
cp .env.testnet .env

# Verify testnet mode
echo ""
echo "✅ Switched to TESTNET"
echo ""
echo "Verification:"
grep -E "BINANCE_TESTNET|BYBIT_TESTNET|DB_NAME" .env || true

echo ""
echo "⚠️  REMINDER:"
echo "   - This is TESTNET mode"
echo "   - Database: fox_crypto_test (port 5433)"
echo "   - Exchange: Testnet API keys"
echo ""
echo "To switch back to mainnet:"
echo "   ./tests/switch_to_mainnet.sh"
