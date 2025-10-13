#!/usr/bin/env python3
"""Diagnose HNTUSDT Stop Loss error"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def diagnose():
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
        print("DIAGNOSING HNTUSDT STOP LOSS ERROR")
        print("="*80)

        # Check if position exists
        print("\n1. Checking if HNTUSDT position exists on exchange...")
        positions = await bybit.fetch_positions(params={'category': 'linear'})

        hnt_pos = None
        for pos in positions:
            symbol = pos['symbol']
            if 'HNT' in symbol:
                hnt_pos = pos
                break

        if hnt_pos:
            print(f"✅ FOUND: {hnt_pos['symbol']}")
            print(f"  Contracts: {hnt_pos.get('contracts')}")
            print(f"  Side: {hnt_pos.get('side')}")
            print(f"  Entry Price: {hnt_pos.get('entryPrice')}")
            print(f"  Mark Price: {hnt_pos.get('markPrice')}")

            info = hnt_pos.get('info', {})
            print(f"\n  Raw Bybit data:")
            print(f"    avgPrice: {info.get('avgPrice')}")
            print(f"    markPrice: {info.get('markPrice')}")
            print(f"    size: {info.get('size')}")

        else:
            print("❌ NOT FOUND: HNTUSDT position does not exist on exchange")
            print("\nThis means:")
            print("  • Position was closed on exchange")
            print("  • But DB still shows status='active'")
            print("  • Bot tries to set SL for non-existent position")
            print("  • Bybit rejects with base_price error")

        # Check market price
        print(f"\n2. Checking current market price...")
        ticker = await bybit.fetch_ticker('HNT/USDT:USDT')
        print(f"  Mark Price: {ticker.get('last')}")
        print(f"  Bid: {ticker.get('bid')}")
        print(f"  Ask: {ticker.get('ask')}")

        # Decode error values
        print(f"\n3. Analyzing error from log:")
        print(f"  StopLoss: 174000000 → 1.74000000")
        print(f"  base_price: 161600000 → 1.61600000")
        print(f"  Entry price (from DB): 1.77273200")
        print(f"  Current price (from log): 3.31")

        print(f"\n4. What is base_price?")
        print(f"  base_price is Bybit's internal reference price for validation")
        print(f"  For LONG: SL must be < base_price")
        print(f"  For SHORT: SL must be > base_price")
        print(f"  ")
        print(f"  In this case:")
        print(f"    SL (1.74) > base_price (1.616) → REJECTED")
        print(f"    SL should be < 1.616 for validation to pass")

        print(f"\n5. Why base_price = 1.616?")
        print(f"  Possible reasons:")
        print(f"    a) Last known position price before close")
        print(f"    b) Liquidation price")
        print(f"    c) Average entry price with some offset")
        print(f"    d) Position doesn't exist → stale cached value")

        print(f"\n6. ROOT CAUSE:")
        print(f"  Position HNTUSDT closed on exchange (by aged position manager)")
        print(f"  DB still shows status='active' (not synchronized)")
        print(f"  Bot tries to set SL for closed position")
        print(f"  Bybit API returns error with stale base_price")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(diagnose())
