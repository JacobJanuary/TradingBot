#!/usr/bin/env python3
"""Check if there are any open orders for HNTUSDT"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt
import json

async def check_orders():
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
        print("CHECKING OPEN ORDERS FOR HNTUSDT")
        print("="*80)

        # Method 1: fetch_open_orders for HNTUSDT
        print("\n1. Open orders for HNTUSDT:")
        try:
            orders = await bybit.fetch_open_orders('HNT/USDT:USDT')
            print(f"   Total open orders: {len(orders)}")

            if orders:
                for order in orders:
                    print(f"\n   Order:")
                    print(f"   - ID: {order.get('id')}")
                    print(f"   - Symbol: {order.get('symbol')}")
                    print(f"   - Type: {order.get('type')}")
                    print(f"   - Side: {order.get('side')}")
                    print(f"   - Amount: {order.get('amount')}")
                    print(f"   - Price: {order.get('price')}")
                    print(f"   - Status: {order.get('status')}")
            else:
                print(f"   ❌ No open orders")
        except Exception as e:
            print(f"   Error: {e}")

        # Method 2: All open orders
        print("\n2. All open orders (checking for HNT):")
        try:
            all_orders = await bybit.fetch_open_orders()
            print(f"   Total open orders (all symbols): {len(all_orders)}")

            hnt_orders = [o for o in all_orders if 'HNT' in o.get('symbol', '').upper()]

            if hnt_orders:
                print(f"   Found {len(hnt_orders)} HNT order(s):")
                for order in hnt_orders:
                    print(f"\n   Order:")
                    print(f"   - Symbol: {order.get('symbol')}")
                    print(f"   - Amount: {order.get('amount')}")
                    print(f"   - Price: {order.get('price')}")
                    print(f"   - Type: {order.get('type')}")
            else:
                print(f"   ❌ No HNT orders")
        except Exception as e:
            print(f"   Error: {e}")

        # Method 3: Check order history (recent)
        print("\n3. Recent order history for HNTUSDT:")
        try:
            # Get orders from last 7 days
            since = bybit.milliseconds() - (7 * 24 * 60 * 60 * 1000)
            orders = await bybit.fetch_orders('HNT/USDT:USDT', since=since, limit=50)

            print(f"   Total orders (last 7 days): {len(orders)}")

            # Look for orders with ~59.88 amount
            for order in orders:
                amount = order.get('amount', 0)
                if 59 <= float(amount) <= 60:
                    print(f"\n   Order with amount ~59-60:")
                    print(f"   - Amount: {amount}")
                    print(f"   - Type: {order.get('type')}")
                    print(f"   - Side: {order.get('side')}")
                    print(f"   - Status: {order.get('status')}")
                    print(f"   - Price: {order.get('price')}")
                    print(f"   - Timestamp: {order.get('datetime')}")
        except Exception as e:
            print(f"   Error: {e}")

        # Method 4: Direct API - get open orders
        print("\n4. Direct API - open orders:")
        try:
            result = await bybit.private_get_v5_order_realtime({
                'category': 'linear',
                'symbol': 'HNTUSDT'
            })

            if result.get('result'):
                orders = result['result'].get('list', [])
                print(f"   Open orders from API: {len(orders)}")

                if orders:
                    for order in orders:
                        print(f"\n   Raw order data:")
                        print(json.dumps(order, indent=6))
        except Exception as e:
            print(f"   Error: {e}")

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print("\nWhat we found:")
        print("  - Position size on exchange: 0 (closed)")
        print("  - Open orders checked above")
        print("\nIf you see 59.88 HNT in web UI:")
        print("  1. Try refreshing the web page (might be cache)")
        print("  2. Check if it's showing 'Position' or 'Order'")
        print("  3. Check if the timestamp matches")
        print("\nPosition was closed at: 2025-10-13 16:32:52 UTC")
        print("(updatedTime: 1760360772357 = 2025-10-13 16:32:52)")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_orders())
