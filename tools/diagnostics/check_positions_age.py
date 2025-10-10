#!/usr/bin/env python3
"""Check positions age and status in database and on exchange"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
import ccxt.async_support as ccxt
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def check_positions():
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port=5433,
        user='elcrypto',
        password='LohNeMamont@!21',
        database='fox_crypto'
    )

    # Exchange connection (Bybit)
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': True
        }
    })

    try:
        print("=" * 80)
        print("POSITION AGE AND STATUS ANALYSIS")
        print("=" * 80)

        current_time = datetime.now(timezone.utc)
        print(f"\nCurrent UTC time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"MAX_POSITION_AGE_HOURS = 1 (positions older than 1 hour should be closed)")

        # Get positions from exchange
        print("\n" + "="*80)
        print("BYBIT EXCHANGE POSITIONS:")
        print("="*80)

        exchange_positions = await exchange.fetch_positions()
        active_positions = [p for p in exchange_positions if p['contracts'] > 0]

        print(f"\nFound {len(active_positions)} active positions on Bybit:")
        for pos in active_positions:
            symbol = pos['symbol']
            # Bybit doesn't provide position open time directly, we'll check orders
            print(f"\n{symbol}:")
            print(f"  Side: {pos['side']}")
            print(f"  Quantity: {pos['contracts']}")
            print(f"  Entry Price: {pos.get('markPrice', 'N/A')}")

            # Try to get position creation time from closed orders (the opening order)
            try:
                closed_orders = await exchange.fetch_closed_orders(symbol, limit=100)
                # Find the order that opened this position
                for order in closed_orders:
                    if order.get('filled', 0) == pos['contracts'] and order.get('status') == 'closed':
                        order_time = order.get('datetime', 'Unknown')
                        if order_time != 'Unknown':
                            order_dt = datetime.fromisoformat(order_time.replace('Z', '+00:00'))
                            age_hours = (current_time - order_dt).total_seconds() / 3600
                            print(f"  Opened at: {order_time}")
                            print(f"  Age: {age_hours:.2f} hours")
                            if age_hours > 1:
                                print(f"  ⚠️ EXPIRED (> 1 hour old)")
                            break
            except Exception as e:
                print(f"  Could not determine age: {e}")

        # Get positions from database
        print("\n" + "="*80)
        print("DATABASE POSITIONS:")
        print("="*80)

        # Query positions from database (monitoring schema)
        db_positions = await conn.fetch("""
            SELECT
                symbol,
                side,
                quantity,
                open_time,
                NOW() AT TIME ZONE 'UTC' as now_utc,
                EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - open_time))/3600 as age_hours,
                status,
                stop_loss
            FROM monitoring.positions
            WHERE status = 'open'
            ORDER BY open_time
        """)

        if not db_positions:
            print("\n⚠️ No open positions found in database!")
            print("This confirms the issue: positions on exchange but NOT in database")
        else:
            print(f"\nFound {len(db_positions)} open positions in database:")
            for pos in db_positions:
                print(f"\n{pos['symbol']}:")
                print(f"  Side: {pos['side']}")
                print(f"  Quantity: {pos['quantity']}")
                print(f"  Open Time: {pos['open_time']}")
                print(f"  Age: {pos['age_hours']:.2f} hours")
                print(f"  Stop Loss: {pos['stop_loss']}")
                if pos['age_hours'] > 1:
                    print(f"  ⚠️ EXPIRED (> 1 hour old)")

        # Compare exchange vs database
        print("\n" + "="*80)
        print("COMPARISON:")
        print("="*80)
        print(f"Positions on Bybit: {len(active_positions)}")
        print(f"Positions in Database: {len(db_positions) if db_positions else 0}")

        if len(active_positions) > (len(db_positions) if db_positions else 0):
            print("\n❌ CRITICAL: More positions on exchange than in database!")
            print("This means database saves are failing!")

        # Check why expired position detection isn't working
        print("\n" + "="*80)
        print("EXPIRED POSITION DETECTION ANALYSIS:")
        print("="*80)

        print("\nChecking position_manager.py logic for expired positions...")
        print("Looking for check_expired_positions or similar methods...")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(check_positions())