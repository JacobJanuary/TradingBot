#!/usr/bin/env python3
"""Check HNT position specifically"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def check_hnt():
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
        print("CHECKING HNTUSDT POSITION SPECIFICALLY")
        print("="*80)

        # Method 1: fetch_positions with all positions
        print("\n1. Method 1: fetch_positions()")
        positions = await bybit.fetch_positions(params={'category': 'linear'})

        print(f"   Total positions: {len(positions)}")

        # Look for HNT
        hnt_found = []
        for pos in positions:
            symbol = pos['symbol']
            if 'HNT' in symbol.upper():
                hnt_found.append(pos)

        if hnt_found:
            print(f"   ✅ Found {len(hnt_found)} HNT position(s):")
            for pos in hnt_found:
                print(f"\n   Symbol: {pos['symbol']}")
                print(f"   Contracts: {pos.get('contracts')}")
                print(f"   Side: {pos.get('side')}")
                print(f"   Entry Price: {pos.get('entryPrice')}")
                print(f"   Mark Price: {pos.get('markPrice')}")
                print(f"   Unrealized PnL: {pos.get('unrealizedPnl')}")

                info = pos.get('info', {})
                print(f"   Raw Bybit data:")
                print(f"     avgPrice: {info.get('avgPrice')}")
                print(f"     size: {info.get('size')}")
                print(f"     positionValue: {info.get('positionValue')}")
        else:
            print(f"   ❌ NO HNT positions found")

        # Method 2: fetch_positions specifically for HNTUSDT
        print("\n2. Method 2: fetch_positions(['HNT/USDT:USDT'])")
        try:
            hnt_specific = await bybit.fetch_positions(['HNT/USDT:USDT'])
            print(f"   Total: {len(hnt_specific)}")
            for pos in hnt_specific:
                contracts = float(pos.get('contracts', 0))
                print(f"   Symbol: {pos['symbol']}, Contracts: {contracts}, Side: {pos.get('side')}")
                if contracts > 0:
                    print(f"   ✅ ACTIVE position with {contracts} contracts")
                else:
                    print(f"   ⭕ Position exists but contracts = 0 (closed)")
        except Exception as e:
            print(f"   Error: {e}")

        # Method 3: Check ticker
        print("\n3. Method 3: Current market data")
        ticker = await bybit.fetch_ticker('HNT/USDT:USDT')
        print(f"   Last price: {ticker.get('last')}")
        print(f"   Mark price: {ticker.get('mark')}")
        print(f"   Bid: {ticker.get('bid')}")
        print(f"   Ask: {ticker.get('ask')}")

        # Method 4: Raw API call
        print("\n4. Method 4: Direct API call")
        result = await bybit.private_get_v5_position_list({
            'category': 'linear',
            'symbol': 'HNTUSDT'
        })

        if result.get('result'):
            positions_list = result['result'].get('list', [])
            print(f"   Positions returned: {len(positions_list)}")
            for pos in positions_list:
                print(f"   Symbol: {pos.get('symbol')}")
                print(f"   Size: {pos.get('size')}")
                print(f"   Side: {pos.get('side')}")
                print(f"   AvgPrice: {pos.get('avgPrice')}")
                print(f"   MarkPrice: {pos.get('markPrice')}")

                size = float(pos.get('size', 0))
                if size > 0:
                    print(f"   ✅ Position ACTIVE with size {size}")
                else:
                    print(f"   ⭕ Position closed (size = 0)")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_hnt())
