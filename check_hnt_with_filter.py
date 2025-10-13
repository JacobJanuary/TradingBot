#!/usr/bin/env python3
"""Check HNT with different filters"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def check_hnt():
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
        print("CHECKING HNTUSDT WITH ALL POSSIBLE METHODS")
        print("="*80)

        # Method 1: fetch_positions with settleCoin filter
        print("\n1. Method 1: fetch_positions() with settleCoin=USDT")
        try:
            positions = await bybit.fetch_positions(params={
                'category': 'linear',
                'settleCoin': 'USDT'
            })
            print(f"   Total positions: {len(positions)}")

            for pos in positions:
                if 'HNT' in pos['symbol'].upper():
                    print(f"\n   ✅ FOUND HNT:")
                    print(f"   Symbol: {pos['symbol']}")
                    print(f"   Contracts: {pos.get('contracts')}")
                    print(f"   Side: {pos.get('side')}")
                    print(f"   Entry: {pos.get('entryPrice')}")
                    print(f"   Mark: {pos.get('markPrice')}")

                    info = pos.get('info', {})
                    print(f"   Raw size: {info.get('size')}")
                    print(f"   Raw avgPrice: {info.get('avgPrice')}")
        except Exception as e:
            print(f"   Error: {e}")

        # Method 2: Direct API without filters
        print("\n2. Method 2: Direct API - ALL positions")
        try:
            result = await bybit.private_get_v5_position_list({
                'category': 'linear'
            })

            if result.get('result'):
                all_positions = result['result'].get('list', [])
                print(f"   Total from API: {len(all_positions)}")

                for pos in all_positions:
                    if 'HNT' in pos.get('symbol', '').upper():
                        print(f"\n   ✅ FOUND HNT in raw API:")
                        print(f"   Symbol: {pos.get('symbol')}")
                        print(f"   Size: {pos.get('size')}")
                        print(f"   Side: {pos.get('side')}")
                        print(f"   AvgPrice: {pos.get('avgPrice')}")
                        print(f"   MarkPrice: {pos.get('markPrice')}")
                        print(f"   PositionValue: {pos.get('positionValue')}")
                        print(f"   UnrealisedPnl: {pos.get('unrealisedPnl')}")
                        print(f"   Leverage: {pos.get('leverage')}")
        except Exception as e:
            print(f"   Error: {e}")

        # Method 3: Fetch ALL positions and filter manually
        print("\n3. Method 3: fetch_positions() - filter manually")
        try:
            all_pos = await bybit.fetch_positions()
            print(f"   Total fetched: {len(all_pos)}")

            hnt_positions = [p for p in all_pos if 'HNT' in p['symbol'].upper()]

            if hnt_positions:
                print(f"   Found {len(hnt_positions)} HNT position(s):")
                for pos in hnt_positions:
                    contracts = pos.get('contracts')
                    print(f"\n   Symbol: {pos['symbol']}")
                    print(f"   Contracts: {contracts} (type: {type(contracts)})")
                    print(f"   Side: {pos.get('side')}")
                    print(f"   Entry: {pos.get('entryPrice')}")
                    print(f"   Mark: {pos.get('markPrice')}")

                    # Check if CCXT is filtering out
                    if contracts == 0 or contracts is None:
                        print(f"   ⚠️ CCXT might be filtering this out due to contracts=0")
            else:
                print(f"   ❌ No HNT found")
        except Exception as e:
            print(f"   Error: {e}")

        # Method 4: Check with different category
        print("\n4. Method 4: Try with category='linear' explicitly")
        try:
            result = await bybit.private_get_v5_position_list({
                'category': 'linear',
                'symbol': 'HNTUSDT',
                'settleCoin': 'USDT'
            })

            if result.get('result'):
                positions = result['result'].get('list', [])
                print(f"   Positions for HNTUSDT: {len(positions)}")

                for pos in positions:
                    print(f"\n   Symbol: {pos.get('symbol')}")
                    print(f"   Size: {pos.get('size')} (type: {type(pos.get('size'))})")
                    print(f"   Side: '{pos.get('side')}'")
                    print(f"   AvgPrice: {pos.get('avgPrice')}")

                    size_str = pos.get('size', '0')
                    size_float = float(size_str) if size_str else 0

                    print(f"\n   Analysis:")
                    print(f"   Size as string: '{size_str}'")
                    print(f"   Size as float: {size_float}")

                    if size_float > 0:
                        print(f"   ✅ ACTIVE POSITION with {size_float} contracts")
                    else:
                        print(f"   ⭕ Size is 0 or empty")
        except Exception as e:
            print(f"   Error: {e}")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_hnt())
