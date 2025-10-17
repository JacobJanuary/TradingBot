#!/usr/bin/env python3
"""
Test script to find correct symbol format for Bybit
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv('.env')

async def test_bybit_symbols():
    print("=" * 60)
    print("BYBIT SYMBOL INVESTIGATION")
    print("=" * 60)

    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',  # Try swap type which is common for perpetuals
            'defaultSubType': 'linear'
        }
    })

    # Use testnet
    exchange.set_sandbox_mode(True)

    print("Loading markets...")
    markets = await exchange.load_markets()
    print(f"Total markets: {len(markets)}")

    # Search for our symbols in different formats
    search_symbols = ['IDEX', 'BTC', 'ETH', 'XDC']

    print("\n📋 Searching for symbols containing our tokens:")
    print("=" * 60)

    for search in search_symbols:
        print(f"\nSymbols containing '{search}':")
        found = []
        for symbol in markets.keys():
            if search in symbol.upper():
                market = markets[symbol]
                found.append({
                    'symbol': symbol,
                    'type': market.get('type'),
                    'active': market.get('active'),
                    'linear': market.get('linear'),
                    'settle': market.get('settle'),
                    'quote': market.get('quote')
                })

        # Sort and display
        found.sort(key=lambda x: x['symbol'])
        for item in found[:10]:  # Show first 10 matches
            status = "✅" if item['active'] else "❌"
            print(f"  {status} {item['symbol']:20} type={item['type']:6} linear={item['linear']} settle={item['settle']} quote={item['quote']}")

        if len(found) > 10:
            print(f"  ... and {len(found) - 10} more")

    # Now test actual working with proper symbol format
    print("\n" + "=" * 60)
    print("TESTING WITH PROPER SYMBOL FORMATS")
    print("=" * 60)

    # Common perpetual formats on Bybit
    test_formats = [
        'BTC/USDT:USDT',     # Linear perpetual
        'ETH/USDT:USDT',     # Linear perpetual
        'BTC/USD:BTC',       # Inverse perpetual
        'BTCUSDT',           # Direct format
        'BTC-USDT',          # Alternative format
        'BTCUSD',            # USD format
    ]

    for symbol_format in test_formats:
        print(f"\nTesting format: {symbol_format}")
        if symbol_format in markets:
            market = markets[symbol_format]
            print(f"  ✅ Found!")
            print(f"     Type: {market.get('type')}")
            print(f"     Active: {market.get('active')}")

            # Test price_to_precision which was causing the error
            try:
                price = 45000.25
                formatted = exchange.price_to_precision(symbol_format, price)
                print(f"  ✅ price_to_precision works: {price} -> {formatted}")

                # Check if 'unified' key exists
                if 'unified' in market:
                    print(f"     'unified' key exists: {market['unified']}")
                else:
                    print(f"     ⚠️ 'unified' key NOT in market")

            except KeyError as e:
                print(f"  ❌ KeyError: {e}")
            except Exception as e:
                print(f"  ❌ Error: {e}")
        else:
            print(f"  ❌ Not found")

    await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_bybit_symbols())