#!/usr/bin/env python3
"""
Test script to verify symbol format conversion for Bybit
Tests our normalize_symbol() and find_exchange_symbol() methods
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange_manager import normalize_symbol, ExchangeManager
from dotenv import load_dotenv

load_dotenv('.env')

async def test_symbol_conversion():
    print("=" * 60)
    print("SYMBOL FORMAT CONVERSION TEST")
    print("Testing normalize_symbol() and find_exchange_symbol()")
    print("=" * 60)

    # Test normalize_symbol function
    print("\n1. Testing normalize_symbol() function:")
    print("-" * 40)

    test_cases = [
        ('BTCUSDT', 'BTCUSDT'),           # DB format
        ('BTC/USDT', 'BTC/USDT'),         # Spot format
        ('BTC/USDT:USDT', 'BTCUSDT'),     # Perpetual format -> DB format
        ('IDEX/USDT:USDT', 'IDEXUSDT'),   # Perpetual format -> DB format
        ('XDC/USDT:USDT', 'XDCUSDT'),     # Perpetual format -> DB format
        ('1000SATS/USDT:USDT', '1000SATSUSDT'),  # With numbers
    ]

    for input_symbol, expected in test_cases:
        result = normalize_symbol(input_symbol)
        status = "✅" if result == expected else "❌"
        print(f"{status} normalize_symbol('{input_symbol}') = '{result}' (expected: '{expected}')")

    # Test with real exchange
    print("\n2. Testing ExchangeManager with Bybit:")
    print("-" * 40)

    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    if not api_key or not api_secret:
        print("❌ Missing BYBIT_API_KEY or BYBIT_API_SECRET in .env")
        return

    # Create exchange manager
    config = {
        'api_key': api_key,
        'api_secret': api_secret,
        'testnet': True
    }

    exchange = ExchangeManager('bybit', config)

    try:
        print("⏳ Loading markets...")
        await exchange.initialize()
        print(f"✅ Loaded {len(exchange.markets)} markets")

        # Test find_exchange_symbol
        print("\n3. Testing find_exchange_symbol() method:")
        print("-" * 40)

        # Symbols from signals (DB format)
        db_symbols = [
            'BTCUSDT',
            'ETHUSDT',
            'IDEXUSDT',
            'XDCUSDT',
            'SAROSUSDT',
            '1000SATSUSDT',
            'NODEUSDT',
            'ORBSUSDT',
            'GLMRUSDT',
            'OKBUSDT',
            'PYRUSDT',
            'RADUSDT',
            'SCAUSDT',
            'BOBAUSDT',
            'CLOUDUSDT',
            'OSMOUSDT',
            'ETHBTCUSDT',
            'AGIUSDT',
            'DOGUSDT',
            'HNTUSDT'
        ]

        print("\nConverting DB format → Exchange format:")
        success_count = 0
        failed_symbols = []

        for db_symbol in db_symbols:
            exchange_symbol = exchange.find_exchange_symbol(db_symbol)
            if exchange_symbol:
                print(f"✅ {db_symbol:15} → {exchange_symbol}")
                success_count += 1

                # Verify reverse conversion
                normalized = normalize_symbol(exchange_symbol)
                if normalized != db_symbol:
                    print(f"   ⚠️ Reverse check failed: {exchange_symbol} → {normalized} (expected {db_symbol})")
            else:
                print(f"❌ {db_symbol:15} → NOT FOUND")
                failed_symbols.append(db_symbol)

        print(f"\nResults: {success_count}/{len(db_symbols)} symbols found")

        if failed_symbols:
            print(f"\n⚠️ Failed symbols: {', '.join(failed_symbols)}")

            # Try to find similar symbols
            print("\n4. Searching for similar symbols:")
            print("-" * 40)

            for failed in failed_symbols:
                base = failed.replace('USDT', '')
                similar = []
                for market_symbol in exchange.markets.keys():
                    if base in market_symbol:
                        similar.append(market_symbol)

                if similar:
                    print(f"{failed}: Found similar → {', '.join(similar[:3])}")
                else:
                    print(f"{failed}: No similar symbols found")

        # Test critical symbols that were causing issues
        print("\n5. Testing critical symbols (from error reports):")
        print("-" * 40)

        critical_symbols = ['IDEXUSDT', 'XDCUSDT']

        for db_symbol in critical_symbols:
            exchange_symbol = exchange.find_exchange_symbol(db_symbol)
            if exchange_symbol:
                print(f"✅ {db_symbol} → {exchange_symbol}")

                # Try to get market info
                if exchange_symbol in exchange.markets:
                    market = exchange.markets[exchange_symbol]
                    print(f"   Market info:")
                    print(f"   - Type: {market.get('type')}")
                    print(f"   - Active: {market.get('active')}")
                    print(f"   - Linear: {market.get('linear')}")
                    print(f"   - Limits: min_amount={market.get('limits', {}).get('amount', {}).get('min')}")
            else:
                print(f"❌ {db_symbol} → NOT FOUND (This will cause order creation to fail!)")

    finally:
        await exchange.close()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_symbol_conversion())