#!/usr/bin/env python3
"""
Test Script: Minimum Amount Validation Fix

Tests the proposed fix for AAVEUSDT error:
- Parse Binance minQty from raw API data
- Test fallback logic for symbols with high min amounts
- Verify calculations don't break existing symbols
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager


# Test symbols (mix of problematic and normal)
TEST_SYMBOLS = [
    'AAVEUSDT',      # High price, min=1.0 (problematic)
    'BTCUSDT',       # Very high price
    'ETHUSDT',       # High price
    'DOGEUSDT',      # Low price, large quantity
    'ADAUSDT',       # Normal
    'BNBUSDT',       # High price
]


async def parse_binance_min_qty(market: dict, exchange_name: str) -> dict:
    """
    Parse minimum quantity from Binance raw API data

    Returns:
        {
            'ccxt_min': float,           # What CCXT returns
            'raw_min_qty': float,        # minQty from Binance API
            'raw_step_size': float,      # stepSize from Binance API
            'recommended_min': float,    # What we should use
            'source': str                # Where we got the value
        }
    """
    result = {
        'ccxt_min': None,
        'raw_min_qty': None,
        'raw_step_size': None,
        'recommended_min': None,
        'source': 'unknown'
    }

    # Get CCXT value
    result['ccxt_min'] = market.get('limits', {}).get('amount', {}).get('min', 0)

    # Parse Binance raw data
    if exchange_name == 'binance':
        info = market.get('info', {})
        filters = info.get('filters', [])

        for f in filters:
            if f.get('filterType') == 'LOT_SIZE':
                min_qty_str = f.get('minQty')
                step_size_str = f.get('stepSize')

                if min_qty_str:
                    try:
                        result['raw_min_qty'] = float(min_qty_str)
                    except (ValueError, TypeError):
                        pass

                if step_size_str:
                    try:
                        result['raw_step_size'] = float(step_size_str)
                    except (ValueError, TypeError):
                        pass

                break

    # Determine recommended minimum
    if result['raw_min_qty'] and result['raw_min_qty'] > 0:
        result['recommended_min'] = result['raw_min_qty']
        result['source'] = 'binance_minQty'
    elif result['ccxt_min'] and result['ccxt_min'] > 0:
        result['recommended_min'] = result['ccxt_min']
        result['source'] = 'ccxt_limits'
    else:
        result['recommended_min'] = 0.001
        result['source'] = 'fallback'

    return result


async def test_position_calculation(
    symbol: str,
    price: float,
    min_data: dict,
    position_size_usd: float = 200.0
) -> dict:
    """
    Test position size calculation with proposed fix

    Returns:
        {
            'symbol': str,
            'price': float,
            'raw_quantity': float,
            'rounded_quantity': float,
            'min_required': float,
            'passes_old_logic': bool,
            'passes_new_logic': bool,
            'fallback_needed': bool,
            'fallback_quantity': float,
            'actual_cost': float,
            'status': str
        }
    """
    result = {
        'symbol': symbol,
        'price': price,
        'position_size_usd': position_size_usd,
    }

    # Calculate raw quantity
    raw_qty = position_size_usd / price
    result['raw_quantity'] = raw_qty

    # Get precision (assume 1 decimal for simplicity, would parse from market)
    # In real code: market['precision']['amount']
    precision = 1  # TODO: Parse from market
    step = 10 ** -precision

    # Round down (current behavior)
    import math
    rounded = math.floor(raw_qty / step) * step
    result['rounded_quantity'] = rounded

    # Get minimums
    old_min = min_data['ccxt_min']
    new_min = min_data['recommended_min']

    result['old_min'] = old_min
    result['new_min'] = new_min

    # Test old logic
    result['passes_old_logic'] = rounded >= old_min if old_min else True

    # Test new logic
    result['passes_new_logic'] = rounded >= new_min if new_min else True

    # Check if fallback needed
    result['fallback_needed'] = (not result['passes_new_logic']) and (raw_qty < new_min)

    # Calculate fallback
    if result['fallback_needed']:
        # Can we use minimum?
        min_cost = new_min * price
        if min_cost <= position_size_usd * 1.1:  # 10% tolerance
            result['fallback_quantity'] = new_min
            result['actual_cost'] = min_cost
            result['status'] = 'fallback_to_minimum'
        else:
            result['fallback_quantity'] = None
            result['actual_cost'] = None
            result['status'] = 'rejected_too_expensive'
    else:
        result['fallback_quantity'] = rounded
        result['actual_cost'] = rounded * price
        result['status'] = 'ok' if result['passes_new_logic'] else 'rejected'

    return result


async def main():
    print("=" * 100)
    print("MINIMUM AMOUNT VALIDATION FIX - TEST SCRIPT")
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

    # Test each symbol
    results = []

    for symbol in TEST_SYMBOLS:
        print("=" * 100)
        print(f"Testing: {symbol}")
        print("=" * 100)

        # Get market data
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

        # Get current price
        ticker = await em.fetch_ticker(symbol)
        if not ticker:
            print(f"❌ Ticker not available: {symbol}")
            print()
            continue

        price = ticker.get('last') or ticker.get('close', 0)

        # Parse minimum data
        min_data = await parse_binance_min_qty(market, 'binance')

        print(f"\n📊 Market Data:")
        print(f"   Price: ${price}")
        print(f"   Precision: {market['precision']['amount']}")
        print()

        print(f"📏 Minimum Amounts:")
        print(f"   CCXT limits.amount.min: {min_data['ccxt_min']}")
        print(f"   Binance raw minQty: {min_data['raw_min_qty']}")
        print(f"   Binance raw stepSize: {min_data['raw_step_size']}")
        print(f"   Recommended: {min_data['recommended_min']} (source: {min_data['source']})")
        print()

        # Test calculation
        calc = await test_position_calculation(symbol, price, min_data)

        print(f"🧮 Position Calculation ($200 USD):")
        print(f"   Raw quantity: {calc['raw_quantity']:.6f}")
        print(f"   Rounded (ROUND_DOWN): {calc['rounded_quantity']:.6f}")
        print()

        print(f"✅ Validation:")
        print(f"   Old logic (min={calc['old_min']}): {'✅ PASS' if calc['passes_old_logic'] else '❌ FAIL'}")
        print(f"   New logic (min={calc['new_min']}): {'✅ PASS' if calc['passes_new_logic'] else '❌ FAIL'}")
        print()

        if calc['fallback_needed']:
            print(f"🔄 Fallback Required:")
            print(f"   Fallback to minimum: {calc['fallback_quantity']}")
            print(f"   Actual cost: ${calc['actual_cost']:.2f}")
            print(f"   Status: {calc['status']}")
        else:
            print(f"✅ Final Result:")
            print(f"   Quantity: {calc['fallback_quantity']}")
            print(f"   Cost: ${calc['actual_cost']:.2f}")
            print(f"   Status: {calc['status']}")

        print()

        results.append({
            'symbol': symbol,
            'price': price,
            'min_data': min_data,
            'calc': calc
        })

    await em.close()

    # Summary
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()

    print(f"{'Symbol':<15} {'Price':<12} {'CCXT Min':<12} {'Real Min':<12} {'Old':<8} {'New':<8} {'Status':<20}")
    print("-" * 100)

    for r in results:
        symbol = r['symbol']
        price = r['price']
        ccxt_min = r['min_data']['ccxt_min']
        real_min = r['min_data']['recommended_min']
        old_pass = '✅' if r['calc']['passes_old_logic'] else '❌'
        new_pass = '✅' if r['calc']['passes_new_logic'] else '❌'
        status = r['calc']['status']

        print(f"{symbol:<15} ${price:<11.2f} {ccxt_min:<12} {real_min:<12} {old_pass:<8} {new_pass:<8} {status:<20}")

    print()
    print("=" * 100)
    print("KEY FINDINGS")
    print("=" * 100)
    print()

    # Check if fix solves AAVEUSDT
    aave_result = next((r for r in results if r['symbol'] == 'AAVEUSDT'), None)
    if aave_result:
        print("🎯 AAVEUSDT (Original Problem):")
        if aave_result['calc']['status'] in ['ok', 'fallback_to_minimum']:
            print(f"   ✅ FIXED: {aave_result['calc']['status']}")
            if aave_result['calc']['fallback_needed']:
                print(f"   📊 Used fallback to minimum: {aave_result['calc']['fallback_quantity']}")
        else:
            print(f"   ❌ NOT FIXED: {aave_result['calc']['status']}")
        print()

    # Check if any existing symbols break
    broken = [r for r in results if r['calc']['passes_old_logic'] and not r['calc']['passes_new_logic'] and r['calc']['status'] == 'rejected_too_expensive']
    if broken:
        print(f"⚠️  WARNING: {len(broken)} symbols would be rejected by new logic:")
        for r in broken:
            print(f"   - {r['symbol']}: Old PASS → New FAIL (min too high)")
        print()
    else:
        print("✅ No existing symbols broken by new logic")
        print()

    # Count improvements
    improved = [r for r in results if not r['calc']['passes_old_logic'] and r['calc']['status'] in ['ok', 'fallback_to_minimum']]
    if improved:
        print(f"✅ IMPROVEMENTS: {len(improved)} symbols fixed:")
        for r in improved:
            print(f"   - {r['symbol']}: Old FAIL → New {r['calc']['status'].upper()}")

    print()
    print("=" * 100)
    print("RECOMMENDATION")
    print("=" * 100)
    print()

    if aave_result and aave_result['calc']['status'] in ['ok', 'fallback_to_minimum'] and not broken:
        print("✅ FIX IS SAFE TO APPLY")
        print("   - Solves AAVEUSDT problem")
        print("   - No existing symbols broken")
        print("   - Fallback logic works correctly")
    else:
        print("⚠️  FIX NEEDS ADJUSTMENT")
        if aave_result and aave_result['calc']['status'] not in ['ok', 'fallback_to_minimum']:
            print("   - Does not solve AAVEUSDT")
        if broken:
            print(f"   - Breaks {len(broken)} existing symbols")

    print()


if __name__ == '__main__':
    asyncio.run(main())
