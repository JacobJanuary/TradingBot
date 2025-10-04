#!/usr/bin/env python3
"""Debug fetch_positions output"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import json

load_dotenv()

async def debug_positions():
    """Debug what fetch_positions returns"""

    binance = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    })

    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'options': {
            'testnet': True,
            'defaultType': 'linear'
        }
    })

    try:
        print("=" * 80)
        print("DEBUG: fetch_positions() OUTPUT")
        print("=" * 80)

        # Binance
        print("\nBINANCE positions:")
        binance_positions = await binance.fetch_positions()
        print(f"Total returned: {len(binance_positions)}")

        for i, pos in enumerate(binance_positions[:3]):  # First 3
            print(f"\nPosition {i}:")
            print(f"  Type: {type(pos)}")
            print(f"  Symbol: {pos.get('symbol')}")
            print(f"  Contracts: {pos.get('contracts')}")
            print(f"  Has 'quantity': {'quantity' in pos}")
            print(f"  Has 'qty': {'qty' in pos}")
            print(f"  Has 'size': {'size' in pos}")

            # Check if it's an object with attributes
            if hasattr(pos, 'quantity'):
                print(f"  pos.quantity (attr): {pos.quantity}")
            if hasattr(pos, 'qty'):
                print(f"  pos.qty (attr): {pos.qty}")
            if hasattr(pos, 'size'):
                print(f"  pos.size (attr): {pos.size}")

            print(f"  All keys: {list(pos.keys())[:10]}...")  # First 10 keys

            # Check contracts value
            contracts = pos.get('contracts')
            if contracts:
                print(f"  Contracts value: {contracts}, type: {type(contracts)}")
                print(f"  Contracts > 0: {float(contracts) > 0}")

        # Count active
        active = [p for p in binance_positions if float(p.get('contracts', 0)) > 0]
        print(f"\nActive positions (contracts > 0): {len(active)}")
        for p in active:
            print(f"  - {p['symbol']}: {p['contracts']} contracts")

        # Bybit
        print("\n" + "=" * 80)
        print("BYBIT positions:")
        bybit_positions = await bybit.fetch_positions()
        print(f"Total returned: {len(bybit_positions)}")

        for i, pos in enumerate(bybit_positions[:3]):  # First 3
            print(f"\nPosition {i}:")
            print(f"  Type: {type(pos)}")
            print(f"  Symbol: {pos.get('symbol')}")
            print(f"  Contracts: {pos.get('contracts')}")
            print(f"  Has 'quantity': {'quantity' in pos}")
            print(f"  Has 'qty': {'qty' in pos}")
            print(f"  Has 'size': {'size' in pos}")

            if hasattr(pos, 'quantity'):
                print(f"  pos.quantity (attr): {pos.quantity}")
            if hasattr(pos, 'qty'):
                print(f"  pos.qty (attr): {pos.qty}")
            if hasattr(pos, 'size'):
                print(f"  pos.size (attr): {pos.size}")

            print(f"  All keys: {list(pos.keys())[:10]}...")

        # Count active
        active = [p for p in bybit_positions if float(p.get('contracts', 0)) > 0]
        print(f"\nActive positions (contracts > 0): {len(active)}")
        for p in active:
            print(f"  - {p['symbol']}: {p['contracts']} contracts")

    finally:
        await binance.close()
        await bybit.close()

if __name__ == "__main__":
    asyncio.run(debug_positions())
