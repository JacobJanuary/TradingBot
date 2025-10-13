#!/usr/bin/env python3
"""Test CCXT cache for closed positions"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def test_cache():
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
        symbols_to_check = ['AGIUSDT', 'SCAUSDT', 'HNTUSDT']

        print("="*80)
        print("TESTING CCXT CACHE FOR CLOSED POSITIONS")
        print("="*80)

        positions = await bybit.fetch_positions(params={'category': 'linear'})

        print(f"\nTotal positions from fetch_positions: {len(positions)}\n")

        for symbol_check in symbols_to_check:
            print(f"{'='*80}")
            print(f"Checking: {symbol_check}")
            print("="*80)

            found = False
            for pos in positions:
                # Normalize symbol
                symbol = pos['symbol']
                if '/' in symbol:
                    normalized = symbol.split(':')[0].replace('/', '')
                else:
                    normalized = symbol

                if normalized == symbol_check:
                    found = True
                    contracts = float(pos.get('contracts') or 0)
                    info = pos.get('info', {})
                    size = float(info.get('size', 0))

                    print(f"\n✅ FOUND in CCXT response:")
                    print(f"  Symbol (CCXT): {symbol}")
                    print(f"  Normalized: {normalized}")
                    print(f"  Contracts (CCXT parsed): {contracts}")
                    print(f"  Size (raw Bybit API): {size}")

                    if contracts > 0 and size == 0:
                        print(f"\n  🚨 STALE CACHE DETECTED!")
                        print(f"    CCXT shows contracts={contracts}")
                        print(f"    But Bybit API shows size={size}")
                        print(f"    Position is CLOSED on exchange but cached in CCXT!")

                    elif contracts > 0 and size > 0:
                        print(f"\n  ✅ REAL ACTIVE POSITION")

                    elif contracts == 0 and size == 0:
                        print(f"\n  ✅ Correctly closed")

                    print(f"\n  Raw info keys: {list(info.keys())}")
                    break

            if not found:
                print(f"\n❌ NOT FOUND in CCXT response")
                print(f"  Position truly does not exist on exchange")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_cache())
