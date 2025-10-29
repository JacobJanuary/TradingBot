#!/usr/bin/env python3
"""
CCXT filter_by_array INVESTIGATION
===================================

Date: 2025-10-29 05:45
Purpose: Understand how CCXT filters positions by symbols

Test Plan:
1. Open test position
2. Call fetch_positions with RAW format symbol
3. Print EXACT response length BEFORE and AFTER filtering (if we can see it)
4. Call with unified format symbol
5. Compare

Expected: Raw format gets filtered out by CCXT
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Load environment
load_dotenv()

# Import after path setup
import ccxt.async_support as ccxt


async def main():
    """Investigate CCXT filtering"""

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

    # Use PRCL as test (similar to production failure)
    test_raw_symbol = 'PRCLUSDT'  # Raw format (like production)
    test_unified_symbol = 'PRCL/USDT:USDT'  # Unified format (fix)
    test_amount = 148.0  # Same as production failure

    try:
        # Set leverage
        try:
            await exchange.set_leverage(1, test_unified_symbol)
        except:
            pass

        print("=" * 80)
        print("Creating test position...")
        print("=" * 80)
        print()

        # Create order
        order = await exchange.create_market_order(
            test_unified_symbol,
            'sell',
            test_amount
        )

        print(f"✅ Order created: {order['id']}")
        print()

        # Wait
        print("⏳ Waiting 2 seconds...")
        await asyncio.sleep(2)
        print()

        # TEST 1: Call with RAW symbol (production code)
        print("=" * 80)
        print(f"TEST 1: fetch_positions(symbols=['{test_raw_symbol}'])")
        print("=" * 80)
        print()

        positions_raw = await exchange.fetch_positions(
            symbols=[test_raw_symbol]
        )

        print(f"Result: {len(positions_raw)} positions returned")
        print()

        if positions_raw:
            print("✅ Positions found!")
            for pos in positions_raw:
                print(f"   symbol: {pos.get('symbol')}")
                print(f"   contracts: {pos.get('contracts')}")
                print(f"   info['symbol']: {pos.get('info', {}).get('symbol')}")
            print()
        else:
            print("❌ NO positions returned (EMPTY LIST)")
            print("   This means CCXT filtered it out!")
            print()

        # TEST 2: Call with UNIFIED symbol (fix)
        print("=" * 80)
        print(f"TEST 2: fetch_positions(symbols=['{test_unified_symbol}'])")
        print("=" * 80)
        print()

        positions_unified = await exchange.fetch_positions(
            symbols=[test_unified_symbol]
        )

        print(f"Result: {len(positions_unified)} positions returned")
        print()

        if positions_unified:
            print("✅ Positions found!")
            for pos in positions_unified:
                print(f"   symbol: {pos.get('symbol')}")
                print(f"   contracts: {pos.get('contracts')}")
                print(f"   info['symbol']: {pos.get('info', {}).get('symbol')}")
            print()
        else:
            print("❌ NO positions returned (EMPTY LIST)")
            print()

        # TEST 3: Call WITHOUT symbols (no filtering)
        print("=" * 80)
        print("TEST 3: fetch_positions() - NO symbols filter")
        print("=" * 80)
        print()

        positions_all = await exchange.fetch_positions()

        non_zero = [p for p in positions_all if float(p.get('contracts', 0)) != 0]

        print(f"Result: {len(positions_all)} total, {len(non_zero)} non-zero")
        print()

        if non_zero:
            print("Non-zero positions:")
            for pos in non_zero:
                print(f"   symbol: {pos.get('symbol')}")
                print(f"   info['symbol']: {pos.get('info', {}).get('symbol')}")
                print(f"   contracts: {pos.get('contracts')}")
            print()

        # Close position
        print("Closing position...")
        await exchange.create_market_order(test_unified_symbol, 'buy', test_amount, params={'reduce_only': True})
        print("✅ Position closed")
        print()

        # VERDICT
        print("=" * 80)
        print("VERDICT")
        print("=" * 80)
        print()

        found_raw = len(positions_raw) > 0
        found_unified = len(positions_unified) > 0
        found_all = len([p for p in non_zero if p.get('info', {}).get('symbol') == test_raw_symbol]) > 0

        print(f"Raw format ('{test_raw_symbol}'):     {'✅ FOUND' if found_raw else '❌ NOT FOUND'}")
        print(f"Unified format ('{test_unified_symbol}'): {'✅ FOUND' if found_unified else '❌ NOT FOUND'}")
        print(f"No filter (position exists):            {'✅ EXISTS' if found_all else '❌ MISSING'}")
        print()

        if not found_raw and found_unified and found_all:
            print("🎯 ROOT CAUSE CONFIRMED!")
            print()
            print("   ❌ Raw format gets FILTERED OUT by CCXT")
            print("   ✅ Unified format works")
            print("   ✅ Position EXISTS on exchange")
            print()
            print("   CCXT's filter_by_array() filters by 'symbol' field,")
            print("   which uses UNIFIED format ('PRCL/USDT:USDT'),")
            print("   NOT raw format ('PRCLUSDT')!")
            print()
            print("   FIX: Convert symbol to unified format before fetch_positions!")
            print()
        elif found_raw:
            print("⚠️  UNEXPECTED: Raw format found position!")
            print("   Need deeper investigation")
            print()

        # Save results
        results = {
            'test_raw_symbol': test_raw_symbol,
            'test_unified_symbol': test_unified_symbol,
            'found_with_raw': found_raw,
            'found_with_unified': found_unified,
            'position_exists': found_all,
            'raw_result_count': len(positions_raw),
            'unified_result_count': len(positions_unified)
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_results_filter_investigation_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"📁 Results saved to: {filename}")

    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(main())
