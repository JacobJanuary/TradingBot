#!/usr/bin/env python3
"""Emergency close all positions and orders"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def emergency_close():
    print("🚨 EMERGENCY CLOSE - Closing all positions and orders")
    print("="*80)

    # Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': True
        }
    })

    try:
        # 1. Close all positions
        print("\n📈 Closing positions on Bybit...")
        positions = await bybit.fetch_positions()
        active = [p for p in positions if p['contracts'] > 0]

        for pos in active:
            symbol = pos['symbol']
            side = pos['side']
            amount = pos['contracts']
            close_side = 'sell' if side == 'long' else 'buy'

            try:
                print(f"  Closing {symbol}: {side} {amount}")
                await bybit.create_order(
                    symbol=symbol,
                    type='market',
                    side=close_side,
                    amount=amount,
                    params={'reduceOnly': True}
                )
                print(f"    ✅ Closed")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"    ❌ Failed: {e}")

        # 2. Cancel all orders
        print("\n📋 Cancelling all orders...")
        orders = await bybit.fetch_open_orders()

        for order in orders:
            try:
                print(f"  Cancelling order for {order['symbol']}")
                await bybit.cancel_order(order['id'], order['symbol'])
                print(f"    ✅ Cancelled")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"    ❌ Failed: {e}")

        print("\n✅ Emergency close complete on Bybit")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bybit.close()

    # Binance
    binance = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    })

    try:
        print("\n📈 Checking positions on Binance...")
        positions = await binance.fetch_positions()
        active = [p for p in positions if p['contracts'] > 0]

        if active:
            for pos in active:
                symbol = pos['symbol']
                side = pos['side']
                amount = pos['contracts']
                close_side = 'sell' if side == 'long' else 'buy'

                try:
                    print(f"  Closing {symbol}: {side} {amount}")
                    await binance.create_order(
                        symbol=symbol,
                        type='market',
                        side=close_side,
                        amount=amount,
                        params={'reduceOnly': True}
                    )
                    print(f"    ✅ Closed")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"    ❌ Failed: {e}")
        else:
            print("  No active positions on Binance")

    except Exception as e:
        print(f"❌ Error on Binance: {e}")
    finally:
        await binance.close()

    print("\n" + "="*80)
    print("🏁 Emergency close procedure completed")

if __name__ == "__main__":
    asyncio.run(emergency_close())