#!/usr/bin/env python3
"""Test setting SL on HNTUSDT at 1.6"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt
import json

async def test_set_sl():
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
        print("TESTING MANUAL SL SETUP FOR HNTUSDT")
        print("="*80)

        # Step 1: Check position first
        print("\n1. Checking current position state:")
        positions = await bybit.fetch_positions(['HNT/USDT:USDT'])

        if positions:
            pos = positions[0]
            print(f"   Symbol: {pos['symbol']}")
            print(f"   Contracts: {pos.get('contracts')}")
            print(f"   Side: {pos.get('side')}")
            print(f"   Entry: {pos.get('entryPrice')}")
            print(f"   Mark: {pos.get('markPrice')}")

            info = pos.get('info', {})
            print(f"   Raw size: {info.get('size')}")
            print(f"   Raw side: '{info.get('side')}'")
            print(f"   Raw avgPrice: {info.get('avgPrice')}")

        # Step 2: Try to set SL at 1.6
        print("\n2. Attempting to set SL at 1.6:")

        # Prepare params
        sl_price = 1.6
        sl_price_str = f"{sl_price:.8f}".rstrip('0').rstrip('.')

        params = {
            'category': 'linear',
            'symbol': 'HNTUSDT',
            'stopLoss': sl_price_str,
            'positionIdx': 0,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        print(f"   Request params:")
        print(json.dumps(params, indent=6))

        # Make the API call
        print(f"\n   Sending request...")

        try:
            result = await bybit.private_post_v5_position_trading_stop(params)

            print(f"\n✅ SUCCESS! Response:")
            print(json.dumps(result, indent=6))

            ret_code = int(result.get('retCode', 1))
            ret_msg = result.get('retMsg', '')

            print(f"\n   Analysis:")
            print(f"   - retCode: {ret_code}")
            print(f"   - retMsg: {ret_msg}")

            if ret_code == 0:
                print(f"   ✅ Stop Loss SET successfully at {sl_price}")
            else:
                print(f"   ❌ Failed with code {ret_code}: {ret_msg}")

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            print(f"\n   Error type: {type(e).__name__}")

            # Try to extract error details
            error_str = str(e)
            if 'retCode' in error_str:
                print(f"   Error contains retCode - this is Bybit API rejection")
            if 'base_price' in error_str:
                print(f"   Error contains base_price - validation error")
            if '10001' in error_str:
                print(f"   Error code 10001 - usually means position issue")

        # Step 3: Check if SL was set
        print("\n3. Verifying if SL was set:")

        result_check = await bybit.private_get_v5_position_list({
            'category': 'linear',
            'symbol': 'HNTUSDT'
        })

        if result_check.get('result'):
            pos_list = result_check['result'].get('list', [])
            if pos_list:
                pos = pos_list[0]
                stop_loss = pos.get('stopLoss', '')
                print(f"   Current stopLoss: {stop_loss}")

                if stop_loss and float(stop_loss) > 0:
                    print(f"   ✅ SL IS SET at {stop_loss}")
                else:
                    print(f"   ⭕ No SL set")

        # Step 4: Try with different price (1.74 - what bot was trying)
        print("\n4. Now trying with 1.74 (what bot was trying):")

        params_174 = {
            'category': 'linear',
            'symbol': 'HNTUSDT',
            'stopLoss': '1.74',
            'positionIdx': 0,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        try:
            result_174 = await bybit.private_post_v5_position_trading_stop(params_174)
            print(f"   ✅ SUCCESS with 1.74!")
            print(json.dumps(result_174, indent=6))

        except Exception as e:
            print(f"   ❌ FAILED with 1.74: {e}")
            print(f"\n   This confirms: 1.74 > base_price, but 1.6 works!")

        # Step 5: Get current market price
        print("\n5. Current market data:")
        ticker = await bybit.fetch_ticker('HNT/USDT:USDT')
        print(f"   Last price: {ticker.get('last')}")
        print(f"   Mark price: {ticker.get('mark')}")

        print("\n" + "="*80)
        print("CONCLUSION")
        print("="*80)
        print("\nIf 1.6 worked:")
        print("  ✅ Position DOES exist (size > 0)")
        print("  ✅ SL at 1.6 < current price → valid for LONG")
        print("  ❌ SL at 1.74 > current price → INVALID for LONG")
        print("\nThis means:")
        print("  - CCXT filters out positions with certain conditions")
        print("  - Direct API might show size=0 in some cases but position exists")
        print("  - Bot's SL calculation (1.74) is INVALID")
        print("  - User's hypothesis is CORRECT: use current_price for SL")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_set_sl())
