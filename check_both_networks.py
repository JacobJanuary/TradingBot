#!/usr/bin/env python3
"""Check HNT on both testnet and mainnet"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def check_network(network_name, is_testnet):
    print("="*80)
    print(f"CHECKING {network_name}")
    print("="*80)

    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })

    bybit.set_sandbox_mode(is_testnet)

    try:
        # Get all positions
        positions = await bybit.fetch_positions(params={'category': 'linear'})

        print(f"\nTotal positions on {network_name}: {len(positions)}")

        # Look for HNT
        hnt_found = False
        for pos in positions:
            if 'HNT' in pos['symbol'].upper():
                hnt_found = True
                contracts = pos.get('contracts')
                print(f"\n✅ FOUND HNT on {network_name}:")
                print(f"   Symbol: {pos['symbol']}")
                print(f"   Contracts: {contracts}")
                print(f"   Side: {pos.get('side')}")
                print(f"   Entry: {pos.get('entryPrice')}")
                print(f"   Mark: {pos.get('markPrice')}")

                info = pos.get('info', {})
                print(f"   Raw size: {info.get('size')}")
                print(f"   Raw avgPrice: {info.get('avgPrice')}")

        if not hnt_found:
            # Try direct API call
            print(f"\n❌ No HNT in fetch_positions(), trying direct API...")

            result = await bybit.private_get_v5_position_list({
                'category': 'linear',
                'symbol': 'HNTUSDT'
            })

            if result.get('result'):
                pos_list = result['result'].get('list', [])
                if pos_list:
                    pos = pos_list[0]
                    size = pos.get('size', '0')
                    print(f"\nDirect API result:")
                    print(f"   Symbol: {pos.get('symbol')}")
                    print(f"   Size: {size}")
                    print(f"   AvgPrice: {pos.get('avgPrice')}")
                    print(f"   Side: {pos.get('side')}")

                    if float(size) > 0:
                        print(f"   ✅ Position EXISTS with size {size}")
                    else:
                        print(f"   ⭕ Size is 0 (closed position)")
                else:
                    print(f"   ❌ No HNTUSDT position found")

        await bybit.close()

    except Exception as e:
        print(f"ERROR on {network_name}: {e}")
        import traceback
        traceback.print_exc()

async def main():
    load_dotenv()

    print("\n" + "="*80)
    print("COMPARING TESTNET vs MAINNET")
    print("="*80)

    # Check testnet
    await check_network("TESTNET", True)

    print("\n")

    # Check mainnet
    await check_network("MAINNET", False)

    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)
    print("\nIf you see 59.88 HNT in web interface:")
    print("  1. Check which network the web UI is showing (testnet/mainnet)")
    print("  2. Our scripts are using TESTNET (BYBIT_TESTNET=true in .env)")
    print("  3. Position might be on MAINNET instead")
    print("\nTo fix:")
    print("  - If position is on MAINNET: set BYBIT_TESTNET=false in .env")
    print("  - If bot should work on TESTNET: ignore mainnet positions")

if __name__ == '__main__':
    asyncio.run(main())
