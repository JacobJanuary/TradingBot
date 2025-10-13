#!/usr/bin/env python3
"""Check ALL positions on exchange"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def check_all():
    load_dotenv()

    # Connect to Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })

    # Set testnet
    bybit.set_sandbox_mode(True)

    try:
        print("="*80)
        print("ALL POSITIONS ON BYBIT")
        print("="*80)

        positions = await bybit.fetch_positions(params={'category': 'linear'})

        # Filter only active positions
        active_positions = [p for p in positions if float(p.get('contracts') or 0) > 0]

        print(f"\nTotal positions returned: {len(positions)}")
        print(f"Active positions (contracts > 0): {len(active_positions)}\n")

        for pos in active_positions:
            symbol = pos['symbol']
            contracts = float(pos.get('contracts') or 0)
            side = pos.get('side')
            mark_price = pos.get('markPrice')

            info = pos.get('info', {})
            size = info.get('size')
            avg_price = info.get('avgPrice')

            print(f"{symbol}:")
            print(f"  Contracts (CCXT): {contracts}")
            print(f"  Size (raw): {size}")
            print(f"  Side: {side}")
            print(f"  Avg Price: {avg_price}")
            print(f"  Mark Price: {mark_price}\n")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_all())
