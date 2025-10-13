#!/usr/bin/env python3
"""
CRITICAL TEST: Fetch HNTUSDT ticker RIGHT NOW and see what price we get
"""

import asyncio
import ccxt.async_support as ccxt
import json
from datetime import datetime


async def test_live_ticker():
    """Test what fetch_ticker returns for HNTUSDT RIGHT NOW"""

    exchange = ccxt.bybit({
        'apiKey': 'JicrzNxY1jRPeSb5p9',
        'secret': 'DgvCFnkfTisRtAhRudMkbk8mIzEzDn66NKNd',
        'options': {
            'defaultType': 'swap',
        }
    })
    exchange.set_sandbox_mode(True)

    try:
        print("="*80)
        print(f"LIVE TEST at {datetime.now()}")
        print("="*80)

        # Test multiple times to see if price changes
        for i in range(3):
            print(f"\n--- Attempt {i+1} ---")

            ticker = await exchange.fetch_ticker('HNTUSDT')

            # Extract prices
            last = ticker.get('last')
            mark = ticker.get('mark')
            info_last = ticker.get('info', {}).get('lastPrice')
            info_mark = ticker.get('info', {}).get('markPrice')
            info_index = ticker.get('info', {}).get('indexPrice')

            print(f"ticker['last']:              {last}")
            print(f"ticker['mark']:              {mark}")
            print(f"ticker['info']['lastPrice']: {info_last}")
            print(f"ticker['info']['markPrice']: {info_mark}")
            print(f"ticker['info']['indexPrice']: {info_index}")

            # What bot's code would do
            bot_price = float(ticker.get('last') or ticker.get('mark') or 0)
            print(f"\n⚠️ Bot would use: {bot_price}")

            # What it SHOULD use
            if info_mark:
                correct_price = float(info_mark)
                print(f"✅ Should use (markPrice from info): {correct_price}")

                if bot_price != correct_price:
                    diff_pct = abs(bot_price - correct_price) / correct_price * 100
                    print(f"❌ ERROR: Bot price differs by {diff_pct:.2f}%!")

            await asyncio.sleep(2)

        # Also check position data
        print("\n" + "="*80)
        print("POSITION DATA FROM EXCHANGE:")
        print("="*80)

        positions = await exchange.fetch_positions(['HNTUSDT'])
        for pos in positions:
            if pos['contracts'] and float(pos['contracts']) > 0:
                print(f"Symbol:        {pos['symbol']}")
                print(f"Entry Price:   {pos.get('entryPrice')}")
                print(f"Mark Price:    {pos.get('markPrice')}")
                print(f"Contracts:     {pos.get('contracts')}")
                print(f"Side:          {pos.get('side')}")
                print(f"Unrealized PnL: {pos.get('unrealizedPnl')}")

                print("\nRaw info:")
                print(json.dumps(pos.get('info', {}), indent=2))

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(test_live_ticker())
