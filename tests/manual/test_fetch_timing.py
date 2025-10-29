#!/usr/bin/env python3
"""
BYBIT fetch_positions TIMING TEST
==================================

Date: 2025-10-29 05:30
Critical Hypothesis: fetch_positions has propagation delay

Test Plan:
1. Open position
2. Call fetch_positions IMMEDIATELY (0ms delay)
3. Call fetch_positions at 100ms, 200ms, 500ms, 1000ms, 2000ms
4. Record when position first appears

Expected: Position NOT in fetch_positions immediately, appears after delay
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Load environment
load_dotenv()

# Import after path setup
import ccxt.async_support as ccxt


async def main():
    """Test fetch_positions timing"""

    # Setup
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    print("✅ Using MAINNET")
    print()

    await exchange.load_markets()

    test_symbol = 'GIGA/USDT:USDT'
    test_amount = 950.0  # ~$6

    try:
        # Set leverage
        try:
            await exchange.set_leverage(1, test_symbol)
        except:
            pass  # Already set

        print("=" * 80)
        print("Creating market order...")
        print("=" * 80)
        print()

        # CREATE ORDER and record exact time
        order_start = time.time()
        order = await exchange.create_market_order(
            test_symbol,
            'sell',
            test_amount
        )
        order_end = time.time()

        order_id = order['id']
        order_duration = (order_end - order_start) * 1000  # ms

        print(f"✅ Order created: {order_id}")
        print(f"   Order creation took: {order_duration:.0f}ms")
        print()

        # Test at different delays
        delays = [0, 100, 200, 500, 1000, 1500, 2000, 3000]
        results = {}

        for delay_ms in delays:
            print(f"Testing fetch_positions after {delay_ms}ms delay...")

            # Wait for delay
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

            # Fetch positions
            fetch_start = time.time()
            positions = await exchange.fetch_positions(
                symbols=[test_symbol],
                params={'category': 'linear'}
            )
            fetch_end = time.time()

            fetch_duration = (fetch_end - fetch_start) * 1000  # ms
            total_time_since_order = (fetch_end - order_start) * 1000  # ms

            # Check if position found
            non_zero = [p for p in positions if float(p.get('contracts', 0)) > 0]
            found = len(non_zero) > 0

            print(f"   Result: {'✅ FOUND' if found else '❌ NOT FOUND'}")
            print(f"   Fetch took: {fetch_duration:.0f}ms")
            print(f"   Total time since order: {total_time_since_order:.0f}ms")
            print()

            results[f"delay_{delay_ms}ms"] = {
                'found': found,
                'fetch_duration_ms': fetch_duration,
                'total_time_since_order_ms': total_time_since_order,
                'position_count': len(non_zero)
            }

        # Close position
        print("Closing position...")
        await exchange.create_market_order(test_symbol, 'buy', test_amount, params={'reduce_only': True})
        print("✅ Position closed")
        print()

        # Analysis
        print("=" * 80)
        print("TIMING ANALYSIS")
        print("=" * 80)
        print()

        first_found = None
        for delay_ms in delays:
            key = f"delay_{delay_ms}ms"
            if results[key]['found'] and first_found is None:
                first_found = delay_ms

        if first_found is not None:
            print(f"✅ Position first appeared after: {first_found}ms delay")
            print()
            if first_found == 0:
                print("   VERDICT: Position available IMMEDIATELY")
                print("   Production code should find it - problem elsewhere!")
            else:
                print(f"   VERDICT: Position has {first_found}ms propagation delay")
                print(f"   Production code needs to wait at least {first_found}ms")
        else:
            print("❌ Position NEVER appeared in fetch_positions!")
            print("   Something is seriously wrong!")

        print()
        print("Full results:")
        print(json.dumps(results, indent=2))

        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_results_fetch_timing_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📁 Results saved to: {filename}")

    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(main())
