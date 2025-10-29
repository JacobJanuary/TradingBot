#!/usr/bin/env python3
"""
Deep Research: AAVEUSDT Precision Problem

Reproduce exact CCXT behavior to understand the error
"""
import asyncio
import sys
from pathlib import Path
import math
from decimal import Decimal, ROUND_DOWN

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager


async def main():
    print("=" * 100)
    print("DEEP RESEARCH: AAVEUSDT Precision Error")
    print("=" * 100)
    print()

    config = Config()
    binance_config = config.get_exchange_config('binance')

    config_dict = {
        'api_key': binance_config.api_key,
        'api_secret': binance_config.api_secret,
        'testnet': binance_config.testnet,
        'rate_limit': binance_config.rate_limit
    }

    em = ExchangeManager('binance', config_dict)
    await em.initialize()

    symbol = 'AAVEUSDT'
    exchange_symbol = em.find_exchange_symbol(symbol)

    print(f"Symbol: {symbol} → {exchange_symbol}")
    print()

    market = em.markets.get(exchange_symbol)
    ticker = await em.fetch_ticker(symbol)
    price = ticker['last']

    print("=" * 100)
    print("MARKET DATA")
    print("=" * 100)
    print()

    print(f"Price: ${price}")
    print()

    print("Limits:")
    print(f"  amount.min: {market['limits']['amount']['min']}")
    print(f"  amount.max: {market['limits']['amount']['max']}")
    print(f"  cost.min: {market['limits']['cost']['min']}")
    print()

    print("Precision:")
    print(f"  amount: {market['precision']['amount']}")
    print(f"  price: {market['precision']['price']}")
    print()

    print("RAW Binance Filters:")
    filters = market.get('info', {}).get('filters', [])
    for f in filters:
        if f.get('filterType') == 'LOT_SIZE':
            print(f"  LOT_SIZE:")
            print(f"    minQty: {f.get('minQty')}")
            print(f"    maxQty: {f.get('maxQty')}")
            print(f"    stepSize: {f.get('stepSize')}")
        elif f.get('filterType') == 'MIN_NOTIONAL':
            print(f"  MIN_NOTIONAL:")
            print(f"    minNotional: {f.get('minNotional')}")
    print()

    print("=" * 100)
    print("CALCULATION SIMULATION")
    print("=" * 100)
    print()

    position_size_usd = 200.0
    raw_qty = position_size_usd / price

    print(f"Position size: ${position_size_usd}")
    print(f"Raw quantity: {raw_qty}")
    print()

    # Simulate different rounding approaches
    precision = market['precision']['amount']
    step = 10 ** -precision

    print(f"Precision: {precision} decimals")
    print(f"Step size: {step}")
    print()

    # Approach 1: ROUND_DOWN (current)
    rounded_down = math.floor(raw_qty / step) * step
    print(f"Approach 1 - ROUND_DOWN:")
    print(f"  Result: {rounded_down}")
    print(f"  Check: {rounded_down} >= {market['limits']['amount']['min']} ? {rounded_down >= market['limits']['amount']['min']}")
    print()

    # Approach 2: ROUND_HALF_UP
    rounded_half_up = round(raw_qty / step) * step
    print(f"Approach 2 - ROUND_HALF_UP:")
    print(f"  Result: {rounded_half_up}")
    print(f"  Check: {rounded_half_up} >= {market['limits']['amount']['min']} ? {rounded_half_up >= market['limits']['amount']['min']}")
    print()

    # Approach 3: Use minimum if too low
    min_qty = market['limits']['amount']['min']
    if rounded_down < min_qty:
        adjusted = min_qty
        adjusted_cost = adjusted * price
        print(f"Approach 3 - Fallback to minimum:")
        print(f"  Rounded: {rounded_down} < min {min_qty}")
        print(f"  Adjusted to: {adjusted}")
        print(f"  Cost: ${adjusted_cost:.2f}")
        print(f"  Over budget: ${adjusted_cost - position_size_usd:.2f} ({(adjusted_cost/position_size_usd - 1)*100:.1f}%)")
        print()
    else:
        print(f"Approach 3 - No adjustment needed")
        print()

    # Test CCXT amount_to_precision
    print("=" * 100)
    print("CCXT amount_to_precision TEST")
    print("=" * 100)
    print()

    try:
        ccxt_formatted = em.exchange.amount_to_precision(exchange_symbol, raw_qty)
        print(f"✅ CCXT formatted: {ccxt_formatted}")
    except Exception as e:
        print(f"❌ CCXT error: {e}")

    print()

    # Try with minimum
    try:
        ccxt_min = em.exchange.amount_to_precision(exchange_symbol, min_qty)
        print(f"✅ CCXT formatted (min): {ccxt_min}")
    except Exception as e:
        print(f"❌ CCXT error (min): {e}")

    print()

    # Try with rounded_down
    try:
        ccxt_rounded = em.exchange.amount_to_precision(exchange_symbol, rounded_down)
        print(f"✅ CCXT formatted (rounded): {ccxt_rounded}")
    except Exception as e:
        print(f"❌ CCXT error (rounded): {e}")

    print()

    print("=" * 100)
    print("FINDINGS")
    print("=" * 100)
    print()

    print("The error message says:")
    print("  'amount must be greater than minimum amount precision of 0.1'")
    print()
    print("This could mean:")
    print("  1. Amount < stepSize (0.9 is not properly aligned with 0.1 step)")
    print("  2. Amount < minQty (but minQty IS 0.1 according to data)")
    print("  3. CCXT internal validation is stricter than market data suggests")
    print()

    # Check if 0.9 is valid with step 0.1
    is_valid_step = (rounded_down % step) == 0
    print(f"Is 0.9 aligned with step 0.1? {is_valid_step}")
    print(f"  0.9 % 0.1 = {rounded_down % step}")
    print()

    await em.close()

    print("=" * 100)
    print("CONCLUSION")
    print("=" * 100)
    print()
    print("Need to check:")
    print("  1. What is the REAL minQty on MAINNET Binance for AAVEUSDT?")
    print("  2. Is testnet data different from mainnet?")
    print("  3. Does CCXT have additional validation we're not seeing?")
    print()


if __name__ == '__main__':
    asyncio.run(main())
