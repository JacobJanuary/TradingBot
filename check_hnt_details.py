#!/usr/bin/env python3
"""Check HNT position full details"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def check_details():
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
        print("HNTUSDT FULL POSITION DETAILS")
        print("="*80)

        # Direct API call with full details
        result = await bybit.private_get_v5_position_list({
            'category': 'linear',
            'symbol': 'HNTUSDT'
        })

        if result.get('result'):
            positions = result['result'].get('list', [])

            if positions:
                pos = positions[0]
                print(f"\n📊 Position Data:")
                print(f"  symbol: {pos.get('symbol')}")
                print(f"  side: {pos.get('side')}")
                print(f"  size: {pos.get('size')}")
                print(f"  avgPrice: {pos.get('avgPrice')}")
                print(f"  entryPrice: {pos.get('entryPrice')}")
                print(f"  markPrice: {pos.get('markPrice')}")
                print(f"  liqPrice: {pos.get('liqPrice')}")
                print(f"  bustPrice: {pos.get('bustPrice')}")
                print(f"  positionValue: {pos.get('positionValue')}")
                print(f"  leverage: {pos.get('leverage')}")
                print(f"  unrealisedPnl: {pos.get('unrealisedPnl')}")
                print(f"  cumRealisedPnl: {pos.get('cumRealisedPnl')}")
                print(f"  stopLoss: {pos.get('stopLoss')}")
                print(f"  takeProfit: {pos.get('takeProfit')}")
                print(f"  trailingStop: {pos.get('trailingStop')}")
                print(f"  positionStatus: {pos.get('positionStatus')}")
                print(f"  createdTime: {pos.get('createdTime')}")
                print(f"  updatedTime: {pos.get('updatedTime')}")

                print(f"\n🔍 Analysis:")
                size = float(pos.get('size', 0))
                avg_price = float(pos.get('avgPrice', 0))
                mark_price = float(pos.get('markPrice', 0))

                if size == 0:
                    print(f"  ⭕ Position is CLOSED (size = 0)")
                    print(f"  But Bybit still keeps the record")
                    print(f"  avgPrice = {avg_price} (was entry price)")
                    print(f"  markPrice = {mark_price} (current market)")
                else:
                    print(f"  ✅ Position is OPEN with size {size}")

                # Check if there's a stop loss
                stop_loss = pos.get('stopLoss', '')
                if stop_loss and stop_loss != '0' and stop_loss != '':
                    print(f"\n  🛡️ Stop Loss EXISTS: {stop_loss}")
                else:
                    print(f"\n  ⚠️ NO Stop Loss set")

                # Explain the error
                print(f"\n💡 Why the error occurs:")
                print(f"  When you try to set SL for a CLOSED position (size=0):")
                print(f"  Bybit validates SL against markPrice (base_price)")
                print(f"  ")
                print(f"  Your SL calculation:")
                print(f"    entry_price (from DB): 1.77273200")
                print(f"    SL = 1.77273200 * 0.98 = 1.7373")
                print(f"  ")
                print(f"  Bybit sees:")
                print(f"    Position size: 0 (CLOSED)")
                print(f"    markPrice (base_price): {mark_price}")
                print(f"    Your SL request: 1.74")
                print(f"  ")
                print(f"  For LONG: SL must be < base_price")
                print(f"    1.74 > {mark_price} → REJECTED")
                print(f"  ")
                print(f"  Even though position is closed, Bybit still validates!")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_details())
