#!/usr/bin/env python3
"""
Test script to debug Bybit 'unified' KeyError issue
This will help identify the exact problem with market data access
"""
import asyncio
import ccxt.async_support as ccxt
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')

async def test_bybit_connection():
    print("=" * 60)
    print("BYBIT 'UNIFIED' ERROR INVESTIGATION")
    print("=" * 60)

    # Get credentials from environment
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    if not api_key or not api_secret:
        print("❌ Missing BYBIT_API_KEY or BYBIT_API_SECRET in .env")
        return

    print(f"✅ API credentials loaded")
    print(f"   CCXT Version: {ccxt.__version__}")

    # Test different configurations
    configs = [
        {
            "name": "Config 1: Basic (no defaultType)",
            "options": {}
        },
        {
            "name": "Config 2: With defaultType='future'",
            "options": {
                'defaultType': 'future'
            }
        },
        {
            "name": "Config 3: With defaultType='unified' (current bot config)",
            "options": {
                'defaultType': 'unified',
                'accountType': 'UNIFIED'
            }
        },
        {
            "name": "Config 4: With defaultType='linear'",
            "options": {
                'defaultType': 'linear'
            }
        },
        {
            "name": "Config 5: With defaultType='swap'",
            "options": {
                'defaultType': 'swap'
            }
        }
    ]

    for config in configs:
        print(f"\n📊 Testing {config['name']}")
        print("-" * 40)

        try:
            # Create exchange instance
            exchange = ccxt.bybit({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': config['options']
            })

            # Use testnet
            exchange.set_sandbox_mode(True)

            print(f"✅ Exchange initialized")
            print(f"   Options: {exchange.options}")

            # Load markets
            print(f"⏳ Loading markets...")
            markets = await exchange.load_markets()
            print(f"✅ Markets loaded: {len(markets)} markets found")

            # Test symbol 'IDEXUSDT' which is causing errors
            test_symbols = ['IDEXUSDT', 'BTCUSDT', 'ETHUSDT']

            for symbol in test_symbols:
                print(f"\n   Testing symbol: {symbol}")

                # Check if symbol exists
                if symbol in exchange.markets:
                    market = exchange.markets[symbol]
                    print(f"   ✅ Market found:")
                    print(f"      Type: {market.get('type')}")
                    print(f"      Active: {market.get('active')}")
                    print(f"      Linear: {market.get('linear')}")
                    print(f"      Settle: {market.get('settle')}")

                    # Test problematic function: price_to_precision
                    try:
                        price = 0.02246
                        formatted_price = exchange.price_to_precision(symbol, price)
                        print(f"   ✅ price_to_precision works: {price} -> {formatted_price}")
                    except KeyError as e:
                        print(f"   ❌ price_to_precision failed with KeyError: {e}")
                        print(f"      Market keys: {list(market.keys())[:10]}...")
                        if 'unified' in market:
                            print(f"      'unified' value: {market['unified']}")
                        else:
                            print(f"      ⚠️  'unified' key NOT in market!")
                    except Exception as e:
                        print(f"   ❌ price_to_precision failed: {type(e).__name__}: {e}")

                    # Test fetch ticker
                    try:
                        ticker = await exchange.fetch_ticker(symbol)
                        print(f"   ✅ Ticker fetched: bid={ticker['bid']}, ask={ticker['ask']}")
                    except Exception as e:
                        print(f"   ❌ fetch_ticker failed: {type(e).__name__}: {e}")

                else:
                    print(f"   ⚠️  Symbol not found in markets")

            await exchange.close()

        except Exception as e:
            print(f"❌ Config failed: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print("INVESTIGATION COMPLETE")
    print("=" * 60)

async def test_market_structure():
    """Deep dive into market structure to understand the problem"""
    print("\n" + "=" * 60)
    print("MARKET STRUCTURE DEEP DIVE")
    print("=" * 60)

    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear'  # Use a working type
        }
    })

    exchange.set_sandbox_mode(True)

    print("Loading markets...")
    markets = await exchange.load_markets()

    # Find IDEXUSDT
    if 'IDEXUSDT' in markets:
        market = markets['IDEXUSDT']
        print(f"\n📋 IDEXUSDT Market Structure:")
        print(f"{'=' * 40}")

        # Print all keys
        for key in sorted(market.keys()):
            value = market[key]
            if isinstance(value, (str, int, float, bool, type(None))):
                print(f"   {key}: {value}")
            elif isinstance(value, dict) and len(str(value)) < 100:
                print(f"   {key}: {value}")
            else:
                print(f"   {key}: <{type(value).__name__}>")

        print(f"\n🔍 Looking for 'unified' key:")
        if 'unified' in market:
            print(f"   ✅ Found 'unified': {market['unified']}")
        else:
            print(f"   ❌ 'unified' key NOT FOUND in market!")

        # Check what defaultType values are available
        print(f"\n🔍 Checking market types:")
        type_keys = ['spot', 'margin', 'swap', 'future', 'option', 'linear', 'inverse', 'unified']
        for key in type_keys:
            if key in market:
                print(f"   {key}: {market[key]}")
    else:
        print("IDEXUSDT not found in markets!")

    await exchange.close()

async def main():
    await test_bybit_connection()
    await test_market_structure()

if __name__ == "__main__":
    asyncio.run(main())