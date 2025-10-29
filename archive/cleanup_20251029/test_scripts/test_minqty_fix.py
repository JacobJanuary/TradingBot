#!/usr/bin/env python3
"""
Test Script: MinQty Fix Validation

Tests the fix for AAVEUSDT minimum amount error:
- Verifies get_min_amount() returns real Binance minQty (not stepSize)
- Verifies fallback logic works for amounts below minimum
- Tests on multiple symbols to ensure nothing broke
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager


TEST_SYMBOLS = [
    'AAVEUSDT',   # Original problem: high minQty
    'BTCUSDT',    # Very high price
    'ETHUSDT',    # High price
    'ADAUSDT',    # Low price, normal minQty
]


async def main():
    print("=" * 100)
    print("MINQTY FIX VALIDATION TEST")
    print("=" * 100)
    print()

    config = Config()
    binance_config = config.get_exchange_config('binance')

    if not binance_config:
        print("❌ Binance not configured")
        return

    config_dict = {
        'api_key': binance_config.api_key,
        'api_secret': binance_config.api_secret,
        'testnet': binance_config.testnet,
        'rate_limit': binance_config.rate_limit
    }

    em = ExchangeManager('binance', config_dict)
    await em.initialize()

    print(f"✅ Connected to Binance {'TESTNET' if binance_config.testnet else 'MAINNET'}")
    print()

    results = []

    for symbol in TEST_SYMBOLS:
        print("=" * 100)
        print(f"Testing: {symbol}")
        print("=" * 100)

        exchange_symbol = em.find_exchange_symbol(symbol)
        if not exchange_symbol:
            print(f"❌ Symbol not found: {symbol}")
            print()
            continue

        market = em.markets.get(exchange_symbol)
        if not market:
            print(f"❌ Market data not available: {symbol}")
            print()
            continue

        ticker = await em.fetch_ticker(symbol)
        if not ticker:
            print(f"❌ Ticker not available: {symbol}")
            print()
            continue

        price = ticker.get('last') or ticker.get('close', 0)

        # Get raw Binance data
        info = market.get('info', {})
        filters = info.get('filters', [])

        raw_min_qty = None
        raw_step_size = None

        for f in filters:
            if f.get('filterType') == 'LOT_SIZE':
                raw_min_qty = float(f.get('minQty', 0))
                raw_step_size = float(f.get('stepSize', 0))
                break

        # Get CCXT parsed value
        ccxt_min = market.get('limits', {}).get('amount', {}).get('min', 0)

        # Get our method result
        our_min = em.get_min_amount(symbol)

        print(f"📊 Price: ${price:.2f}")
        print()
        print(f"📏 Minimum Amounts:")
        print(f"   Binance raw minQty:    {raw_min_qty}")
        print(f"   Binance raw stepSize:  {raw_step_size}")
        print(f"   CCXT limits.amount.min: {ccxt_min}")
        print(f"   Our get_min_amount():   {our_min}")
        print()

        # Check if fix is working
        if raw_min_qty and our_min == raw_min_qty:
            print(f"✅ FIX WORKING: get_min_amount() returns real minQty")
        elif raw_min_qty and our_min != raw_min_qty:
            print(f"❌ FIX FAILED: get_min_amount() returns {our_min}, expected {raw_min_qty}")
        else:
            print(f"⚠️  No LOT_SIZE filter found")

        print()

        # Test position calculation with $200
        position_size = 200.0
        raw_qty = position_size / price

        # Simulate ROUND_DOWN
        import math
        precision = market['precision']['amount']
        step = 10 ** -precision
        rounded = math.floor(raw_qty / step) * step

        print(f"🧮 Position Calculation ($200 USD):")
        print(f"   Raw quantity:      {raw_qty:.6f}")
        print(f"   Rounded (ROUND_DOWN): {rounded:.6f}")
        print(f"   Minimum required:  {our_min}")
        print()

        if rounded >= our_min:
            print(f"✅ PASS: {rounded} >= {our_min}")
            result = "pass"
        else:
            # Check fallback
            min_cost = our_min * price
            tolerance = position_size * 1.1

            print(f"⚠️  BELOW MINIMUM: {rounded} < {our_min}")
            print(f"   Fallback check:")
            print(f"     Min cost: ${min_cost:.2f}")
            print(f"     Tolerance: ${tolerance:.2f}")

            if min_cost <= tolerance:
                print(f"   ✅ FALLBACK OK: Will use minimum {our_min}")
                result = "fallback"
            else:
                print(f"   ❌ FALLBACK REJECT: Too expensive")
                result = "reject"

        print()

        results.append({
            'symbol': symbol,
            'price': price,
            'raw_min_qty': raw_min_qty,
            'ccxt_min': ccxt_min,
            'our_min': our_min,
            'fix_working': (raw_min_qty and our_min == raw_min_qty),
            'result': result
        })

    await em.close()

    # Summary
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()

    print(f"{'Symbol':<12} {'Price':<10} {'Raw minQty':<12} {'CCXT Min':<12} {'Our Min':<12} {'Fix':<8} {'Result':<12}")
    print("-" * 100)

    for r in results:
        symbol = r['symbol']
        price = r['price']
        raw_min = r['raw_min_qty'] or 0
        ccxt_min = r['ccxt_min']
        our_min = r['our_min']
        fix = '✅' if r['fix_working'] else '❌'
        result = r['result']

        print(f"{symbol:<12} ${price:<9.2f} {raw_min:<12} {ccxt_min:<12} {our_min:<12} {fix:<8} {result:<12}")

    print()
    print("=" * 100)
    print("RESULTS")
    print("=" * 100)
    print()

    # Check AAVEUSDT
    aave = next((r for r in results if r['symbol'] == 'AAVEUSDT'), None)
    if aave:
        print("🎯 AAVEUSDT (Original Problem):")
        if aave['fix_working']:
            print(f"   ✅ FIX VERIFIED: get_min_amount() returns {aave['our_min']} (real minQty)")
        else:
            print(f"   ❌ FIX FAILED: get_min_amount() returns {aave['our_min']}, expected {aave['raw_min_qty']}")

        if aave['result'] in ['pass', 'fallback']:
            print(f"   ✅ POSITION CREATION: {aave['result'].upper()}")
        else:
            print(f"   ❌ POSITION REJECTED")
        print()

    # Check for regressions
    broken = [r for r in results if not r['fix_working']]
    if broken:
        print(f"⚠️  WARNING: {len(broken)} symbols not using real minQty:")
        for r in broken:
            print(f"   - {r['symbol']}: returns {r['our_min']}, expected {r['raw_min_qty']}")
        print()
    else:
        print("✅ All symbols using real minQty from Binance API")
        print()

    print("=" * 100)


if __name__ == '__main__':
    asyncio.run(main())
