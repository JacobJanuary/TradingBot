#!/usr/bin/env python3
"""Check HNT using RAW API response without CCXT filtering"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt
import json

async def check_raw():
    load_dotenv()

    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })

    bybit.set_sandbox_mode(True)

    try:
        print("="*80)
        print("RAW API CHECK - NO CCXT FILTERING")
        print("="*80)

        # Method 1: Get ALL positions with settleCoin
        print("\n1. All positions with settleCoin=USDT")
        result = await bybit.private_get_v5_position_list({
            'category': 'linear',
            'settleCoin': 'USDT'
        })

        if result.get('result'):
            all_positions = result['result'].get('list', [])
            print(f"   Total positions returned: {len(all_positions)}")

            # Find HNT
            for pos in all_positions:
                if 'HNT' in pos.get('symbol', '').upper():
                    print(f"\n   ✅ FOUND HNTUSDT:")
                    print(f"   Full raw data:")
                    print(json.dumps(pos, indent=6))

                    size = pos.get('size', '')
                    print(f"\n   Size analysis:")
                    print(f"   - size field: '{size}' (type: {type(size).__name__})")
                    print(f"   - size as float: {float(size) if size else 0}")
                    print(f"   - size > 0: {float(size) > 0 if size else False}")

        # Method 2: Get SPECIFIC symbol
        print("\n\n2. Specific HNTUSDT query")
        result2 = await bybit.private_get_v5_position_list({
            'category': 'linear',
            'symbol': 'HNTUSDT'
        })

        if result2.get('result'):
            positions = result2['result'].get('list', [])
            print(f"   Positions for HNTUSDT: {len(positions)}")

            if positions:
                pos = positions[0]
                print(f"\n   Full raw data:")
                print(json.dumps(pos, indent=6))

        # Method 3: Compare with CCXT parsed
        print("\n\n3. CCXT parsed positions (for comparison)")
        ccxt_positions = await bybit.fetch_positions(params={'category': 'linear'})

        hnt_in_ccxt = None
        for p in ccxt_positions:
            if 'HNT' in p['symbol'].upper():
                hnt_in_ccxt = p
                break

        if hnt_in_ccxt:
            print(f"   ✅ CCXT includes HNT:")
            print(f"   contracts: {hnt_in_ccxt.get('contracts')}")
            print(f"   side: {hnt_in_ccxt.get('side')}")
        else:
            print(f"   ❌ CCXT does NOT include HNT in parsed results")
            print(f"   This means CCXT is filtering it out (likely due to size=0)")

        # Method 4: Check if there are positions with size like "59.88"
        print("\n\n4. Looking for ANY position with size containing '59'")
        result3 = await bybit.private_get_v5_position_list({
            'category': 'linear',
            'settleCoin': 'USDT'
        })

        if result3.get('result'):
            all_pos = result3['result'].get('list', [])
            for pos in all_pos:
                size = str(pos.get('size', ''))
                if '59' in size or '60' in size:
                    print(f"\n   Found position with size ~59-60:")
                    print(f"   Symbol: {pos.get('symbol')}")
                    print(f"   Size: {size}")
                    print(f"   Side: {pos.get('side')}")
                    print(f"   AvgPrice: {pos.get('avgPrice')}")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_raw())
