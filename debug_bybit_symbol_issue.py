#!/usr/bin/env python3
"""
Debug Bybit symbol format issue
"""
import asyncio
import ccxt.pro as ccxt
import os
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Initialize Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'testnet': True,
        'options': {
            'defaultType': 'linear',
            'defaultSettle': 'USDT'
        }
    })

    try:
        # Fetch positions
        positions = await bybit.fetch_positions()
        print(f"\n✅ Found {len(positions)} positions on Bybit testnet:")

        for pos in positions:
            if pos['contracts'] > 0:
                print(f"\n📊 Position details:")
                print(f"  Symbol from exchange: {pos['symbol']}")
                print(f"  Info symbol: {pos.get('info', {}).get('symbol', 'N/A')}")
                print(f"  Contracts: {pos['contracts']}")
                print(f"  Side: {pos['side']}")

                # Try different symbol formats
                symbols_to_try = [
                    pos['symbol'],  # Original: ETHBTC/USDT:USDT
                    pos['symbol'].replace('/', '').replace(':', ''),  # ETHBTCUSDTUSDT
                    pos['symbol'].split('/')[0] + 'USDT',  # ETHBTCUSDT
                    pos['symbol'].split(':')[0].replace('/', ''),  # ETHBTCUSDT
                    pos.get('info', {}).get('symbol', ''),  # Raw from API
                ]

                print(f"\n  Testing symbol formats:")
                for sym in symbols_to_try:
                    if sym:
                        print(f"    - Trying: {sym}")
                        try:
                            # Try to fetch open orders with this symbol
                            orders = await bybit.fetch_open_orders(sym)
                            print(f"      ✅ SUCCESS! Format works: {sym}")
                            print(f"      Found {len(orders)} open orders")

                            # Check if position exists with this symbol
                            pos_check = await bybit.fetch_positions([sym])
                            if pos_check and pos_check[0]['contracts'] > 0:
                                print(f"      ✅ Position found with this symbol!")

                        except Exception as e:
                            print(f"      ❌ Failed: {str(e)[:50]}")

        # Also check what the raw API returns
        print("\n\n🔍 Raw API response for positions:")
        raw_positions = await bybit.privateGetV5PositionList({'category': 'linear', 'settleCoin': 'USDT'})
        if raw_positions['result']['list']:
            for pos in raw_positions['result']['list'][:2]:  # Show first 2
                print(f"\n  Raw position:")
                print(f"    symbol: {pos.get('symbol')}")
                print(f"    side: {pos.get('side')}")
                print(f"    size: {pos.get('size')}")

    finally:
        await bybit.close()

if __name__ == "__main__":
    asyncio.run(main())