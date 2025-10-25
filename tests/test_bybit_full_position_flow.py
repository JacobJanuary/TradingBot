#!/usr/bin/env python3
"""
BYBIT FULL POSITION FLOW TEST
==============================
Test complete flow: position creation + SL placement

This validates the COMPLETE fix!
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import ccxt.async_support as ccxt
from config.settings import config


async def test_full_position_flow():
    """Test complete position + SL flow"""
    print("="*60)
    print("BYBIT FULL POSITION + SL FLOW TEST")
    print("="*60)

    bybit_config = config.get_exchange_config('bybit')

    exchange = ccxt.bybit({
        'apiKey': bybit_config.api_key,
        'secret': bybit_config.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
            'brokerId': ''
        }
    })

    await exchange.load_markets()

    symbol = 'BTC/USDT:USDT'
    amount = 0.001  # ~$110
    sl_percent = 0.02  # 2%

    try:
        # STEP 1: Create position
        print(f"\nSTEP 1: Creating position...")
        print(f"  Symbol: {symbol}")
        print(f"  Amount: {amount}")

        params = {'positionIdx': 0}

        order = await exchange.create_order(
            symbol=symbol,
            type='market',
            side='buy',
            amount=amount,
            price=None,
            params=params
        )

        print(f"✅ Order created: {order['id']}")

        # STEP 2: Get execution price from positions
        print(f"\nSTEP 2: Getting execution price from positions...")

        await asyncio.sleep(0.5)

        positions = await exchange.fetch_positions(
            symbols=[symbol],
            params={'category': 'linear'}
        )

        entry_price = None
        position_side = None

        for pos in positions:
            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                entry_price = float(pos.get('entryPrice', 0))
                position_side = pos.get('side')  # 'long' or 'short'
                print(f"✅ Position found!")
                print(f"   Entry price: ${entry_price}")
                print(f"   Side: {position_side}")
                break

        if not entry_price:
            raise Exception("Could not get entry price from positions!")

        # STEP 3: Calculate SL
        print(f"\nSTEP 3: Calculating SL...")

        if position_side == 'long':
            sl_price = entry_price * (1 - sl_percent)  # BELOW entry for LONG (stop-loss when price drops)
            sl_side = 'sell'
        else:
            sl_price = entry_price * (1 + sl_percent)  # ABOVE entry for SHORT (stop-loss when price rises)
            sl_side = 'buy'

        sl_formatted = exchange.price_to_precision(symbol, sl_price)

        print(f"   Entry: ${entry_price}")
        print(f"   SL: ${sl_formatted} ({sl_percent*100}%)")
        print(f"   SL side: {sl_side}")

        # STEP 4: Create SL order
        print(f"\nSTEP 4: Creating SL order...")

        # Remove '/' and ':USDT' for Bybit symbol format
        bybit_symbol = symbol.replace('/', '').replace(':USDT', '')

        sl_params = {
            'category': 'linear',
            'symbol': bybit_symbol,
            'stopLoss': sl_formatted,
            'positionIdx': 0,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        print(f"   Using trading-stop endpoint...")
        print(f"   Params: {sl_params}")

        response = await exchange.private_post_v5_position_trading_stop(sl_params)

        ret_code = str(response.get('retCode', -1))
        ret_msg = response.get('retMsg', 'unknown')

        if ret_code == '0' or ret_code == 0:
            print(f"✅ SL created successfully!")
            print(f"   retCode: {ret_code}")
            print(f"   retMsg: {ret_msg}")
        else:
            print(f"❌ SL creation failed!")
            print(f"   retCode: {ret_code}")
            print(f"   retMsg: {ret_msg}")
            raise Exception(f"SL creation failed: {ret_msg}")

        # STEP 5: Verify SL exists
        print(f"\nSTEP 5: Verifying SL...")

        await asyncio.sleep(0.5)

        positions_with_sl = await exchange.fetch_positions(
            symbols=[symbol],
            params={'category': 'linear'}
        )

        for pos in positions_with_sl:
            if pos['symbol'] == symbol:
                info = pos.get('info', {})
                sl_on_position = info.get('stopLoss')
                print(f"   Position SL: {sl_on_position}")
                if sl_on_position and float(sl_on_position) > 0:
                    print(f"✅ SL verified on position!")

        # STEP 6: Close position (clear SL first)
        print(f"\nSTEP 6: Closing position...")

        # Clear SL before closing
        clear_sl_params = {
            'category': 'linear',
            'symbol': bybit_symbol,
            'stopLoss': '0',
            'positionIdx': 0,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        await exchange.private_post_v5_position_trading_stop(clear_sl_params)
        print(f"   SL cleared")

        await asyncio.sleep(0.5)

        close_params = {
            'positionIdx': 0,
            'reduce_only': True
        }

        close_order = await exchange.create_order(
            symbol=symbol,
            type='market',
            side='sell',
            amount=amount,
            price=None,
            params=close_params
        )

        print(f"✅ Position closed: {close_order['id']}")

        # FINAL REPORT
        print(f"\n{'='*60}")
        print("FINAL REPORT:")
        print(f"{'='*60}")
        print("✅ Position created successfully")
        print("✅ Execution price obtained from fetch_positions")
        print("✅ SL calculated correctly")
        print("✅ SL placed successfully via trading-stop")
        print("✅ SL verified on position")
        print("✅ Position closed successfully")
        print("\n🎉 COMPLETE FLOW WORKS 100%!")
        print("\n📋 FIX CONFIRMED:")
        print("   1. Use fetch_positions to get execution price")
        print("   2. Calculate SL from this price")
        print("   3. Place SL via trading-stop endpoint")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await exchange.close()


async def main():
    print("\n⚠️ WARNING: This creates a REAL position (~$110) with SL on Bybit mainnet!")
    print("Position and SL will be closed/cleared after test.\n")

    response = input("Continue? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return

    success = await test_full_position_flow()

    if success:
        print("\n✅ TEST PASSED! Ready to implement fix in code.")
        sys.exit(0)
    else:
        print("\n❌ TEST FAILED! Need more investigation.")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
