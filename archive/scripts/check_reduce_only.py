#!/usr/bin/env python3
"""
Quick script to check reduceOnly parameter in open orders
"""
import asyncio
import sys
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.exchange_manager import ExchangeManager

async def main():
    print("🔍 Checking reduceOnly parameter in open SL orders...\n")

    exchange_mgr = ExchangeManager()
    await exchange_mgr.initialize()

    binance = exchange_mgr.exchanges['binance']

    # Get all open orders
    orders = await binance.fetch_open_orders()

    print(f"📊 Found {len(orders)} open orders on Binance testnet\n")

    sl_count = 0
    reduce_only_count = 0

    for order in orders:
        if order['type'] in ['STOP_MARKET', 'STOP', 'stop_market']:
            sl_count += 1
            symbol = order['symbol']
            order_id = order['id']
            reduce_only = order.get('reduceOnly', False)

            status_icon = "✅" if reduce_only else "❌"
            print(f"{status_icon} {symbol:20} | Order: {order_id:12} | reduceOnly: {reduce_only}")

            if reduce_only:
                reduce_only_count += 1

    print(f"\n📊 SUMMARY:")
    print(f"   Total SL orders: {sl_count}")
    print(f"   With reduceOnly=True: {reduce_only_count}")
    print(f"   Without reduceOnly: {sl_count - reduce_only_count}")

    if sl_count > 0 and reduce_only_count == sl_count:
        print(f"\n✅ ✅ ✅ ALL STOP-LOSS ORDERS HAVE reduceOnly=True! ✅ ✅ ✅")
    elif reduce_only_count > 0:
        print(f"\n⚠️  PARTIAL: {reduce_only_count}/{sl_count} have reduceOnly")
    else:
        print(f"\n❌ CRITICAL: NO Stop-Loss orders have reduceOnly!")

    await binance.close()

if __name__ == "__main__":
    asyncio.run(main())
