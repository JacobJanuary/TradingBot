#!/usr/bin/env python3
"""Check available Bybit symbol formats"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def check_symbols():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()

        # Look for our test symbols
        test_bases = ['BTC', 'ETH', 'SOL', 'DOGE', 'AVAX', 'LINK', 'UNI', 'CHEEMS', 'VR', 'ALU']

        print("Looking for symbols with these bases:", test_bases)
        print()

        for base in test_bases:
            matching = [s for s in exchange.markets.keys() if base in s]
            if matching:
                print(f"{base}: {matching[:3]}")  # Show first 3 matches

        print()
        print("Sample linear perpetual symbols:")
        linear_symbols = [s for s in list(exchange.markets.keys())[:20] if '/USDT:USDT' in s]
        for s in linear_symbols[:10]:
            print(f"  {s}")

    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(check_symbols())
