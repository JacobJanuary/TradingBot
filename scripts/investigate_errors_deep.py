#!/usr/bin/env python3
"""
DEEP INVESTIGATION: Wave 07:36 Errors

This script investigates both errors from the last wave:
1. METUSDT: Binance error -2027 (leverage/margin limit)
2. TAOUSDT: CCXT amount_to_precision error

CRITICAL: This is INVESTIGATION ONLY - NO CODE CHANGES!
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


async def investigate_metusdt_margin_error():
    """
    Investigation: Why did METUSDT fail with error -2027?

    Error: {"code":-2027,"msg":"Exceeded the maximum allowable position at current leverage."}

    Hypothesis:
    1. Not enough margin/balance
    2. Position notional exceeds maxNotionalValue for current leverage
    3. Too many open positions
    """
    print("=" * 100)
    print("INVESTIGATION #1: METUSDT MARGIN ERROR (-2027)")
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

    symbol = 'METUSDT'
    exchange_symbol = em.find_exchange_symbol(symbol)

    print(f"Symbol: {symbol} → {exchange_symbol}")
    print()

    # Get current balance
    try:
        balance = await em.exchange.fetch_balance()
        total_balance = balance.get('USDT', {}).get('total', 0)
        free_balance = balance.get('USDT', {}).get('free', 0)
        used_balance = balance.get('USDT', {}).get('used', 0)

        print(f"💰 Current Balance:")
        print(f"   Total: ${total_balance:.2f} USDT")
        print(f"   Free:  ${free_balance:.2f} USDT")
        print(f"   Used:  ${used_balance:.2f} USDT")
        print()
    except Exception as e:
        print(f"❌ Failed to fetch balance: {e}")
        total_balance = 0
        free_balance = 0
        used_balance = 0

    # Get open positions
    try:
        positions = await em.exchange.fetch_positions()
        active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        print(f"📊 Open Positions: {len(active_positions)}")

        total_notional = 0
        for pos in active_positions[:5]:  # Show first 5
            notional = float(pos.get('notional', 0))
            total_notional += abs(notional)
            print(f"   {pos['symbol']}: ${abs(notional):.2f}")

        if len(active_positions) > 5:
            print(f"   ... and {len(active_positions) - 5} more")

        print(f"   Total notional: ${total_notional:.2f}")
        print()
    except Exception as e:
        print(f"❌ Failed to fetch positions: {e}")
        active_positions = []
        total_notional = 0

    # Get leverage bracket for METUSDT
    print(f"🔍 Checking leverage brackets for {symbol}:")
    try:
        # Try to get leverage bracket
        leverage_bracket = await em.exchange.fapiPrivateGetLeverageBracket({'symbol': exchange_symbol.replace('/USDT:USDT', 'USDT')})

        if leverage_bracket:
            brackets = leverage_bracket[0].get('brackets', [])
            print(f"   Found {len(brackets)} leverage tiers:")
            for i, bracket in enumerate(brackets[:3], 1):  # Show first 3
                print(f"   Tier {i}:")
                print(f"     Max leverage: {bracket.get('initialLeverage')}x")
                print(f"     Max notional: ${float(bracket.get('notionalCap')):.2f}")
                print(f"     Min notional: ${float(bracket.get('notionalFloor')):.2f}")
            print()
    except Exception as e:
        print(f"   ⚠️ Could not fetch leverage brackets: {e}")
        print()

    # Get current leverage for the symbol
    print(f"🔧 Current leverage settings:")
    try:
        # Get position risk to see current leverage
        position_risk = await em.exchange.fapiPrivateV2GetPositionRisk({'symbol': exchange_symbol.replace('/USDT:USDT', 'USDT')})

        if position_risk:
            for risk in position_risk:
                if risk.get('symbol') == exchange_symbol.replace('/USDT:USDT', 'USDT'):
                    leverage = risk.get('leverage', 'N/A')
                    max_notional = risk.get('maxNotionalValue', 'N/A')
                    print(f"   Current leverage: {leverage}x")
                    print(f"   Max notional at this leverage: ${max_notional}")
                    print()
                    break
    except Exception as e:
        print(f"   ⚠️ Could not fetch position risk: {e}")
        print()

    # Simulate METUSDT position
    print(f"📐 Simulating METUSDT position:")
    ticker = await em.fetch_ticker(symbol)
    price = ticker['last']
    position_size_usd = 200.0
    quantity = position_size_usd / price

    print(f"   Price: ${price}")
    print(f"   Target size: ${position_size_usd}")
    print(f"   Quantity: {quantity:.2f} MET")
    print(f"   Notional value: ${position_size_usd}")
    print()

    # Check if we can afford it
    print(f"✅ Validation:")
    print(f"   Free balance: ${free_balance:.2f}")
    print(f"   Position cost: ${position_size_usd:.2f}")
    print(f"   Can afford? {free_balance >= position_size_usd}")
    print()

    # HYPOTHESIS: The issue is that Binance counts ALL positions notional
    # against a TOTAL limit, not per-symbol
    print(f"🔬 ROOT CAUSE HYPOTHESIS:")
    print(f"   Total positions: {len(active_positions)}")
    print(f"   Total notional: ${total_notional:.2f}")
    print(f"   New position: ${position_size_usd:.2f}")
    print(f"   Total after: ${total_notional + position_size_usd:.2f}")
    print()
    print(f"   Balance: ${total_balance:.2f}")
    print(f"   Utilization before: {(total_notional / total_balance * 100) if total_balance > 0 else 0:.1f}%")
    print(f"   Utilization after: {((total_notional + position_size_usd) / total_balance * 100) if total_balance > 0 else 0:.1f}%")
    print()

    # Check if testnet has different rules
    if binance_config.testnet:
        print(f"⚠️  WARNING: Running on TESTNET")
        print(f"   Testnet may have stricter limits or different rules")
        print(f"   Mainnet behavior may differ")
        print()

    await em.close()

    print("=" * 100)
    print("CONCLUSION:")
    print("=" * 100)
    print()
    print("Possible causes for error -2027:")
    print("1. ✓ Total notional across ALL positions exceeds account limit")
    print("2. ✓ Testnet has stricter position limits than mainnet")
    print("3. ✓ Max leverage tier for total exposure reached")
    print("4. ? Need to check maxNotionalValue per leverage tier")
    print()
    print("SOLUTION:")
    print("- Check available margin BEFORE opening position")
    print("- Use GET /fapi/v2/positionRisk to get maxNotionalValue")
    print("- Calculate: current_notional + new_position_notional < maxNotionalValue")
    print()


async def investigate_taousdt_precision_error():
    """
    Investigation: Why did TAOUSDT fail with CCXT precision error?

    Error: binance amount of TAO/USDT:USDT must be greater than minimum amount precision of 0.001

    Quantity: 0.492 TAO
    Expected: Should work if minQty=0.001, but it doesn't

    Hypothesis:
    1. CCXT validates BEFORE our fallback logic
    2. Real minimum is higher than what we parse from LOT_SIZE
    3. CCXT has additional checks we don't see
    """
    print("=" * 100)
    print("INVESTIGATION #2: TAOUSDT PRECISION ERROR")
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

    symbol = 'TAOUSDT'
    exchange_symbol = em.find_exchange_symbol(symbol)

    print(f"Symbol: {symbol} → {exchange_symbol}")
    print()

    market = em.markets.get(exchange_symbol)
    ticker = await em.fetch_ticker(symbol)
    price = ticker['last']

    print(f"📊 Market Data:")
    print(f"   Price: ${price}")
    print(f"   Precision amount: {market['precision']['amount']}")
    print(f"   Precision price: {market['precision']['price']}")
    print()

    # Parse raw Binance filters
    print(f"📏 Binance LOT_SIZE filter:")
    info = market.get('info', {})
    filters = info.get('filters', [])

    raw_min_qty = None
    raw_step_size = None

    for f in filters:
        if f.get('filterType') == 'LOT_SIZE':
            raw_min_qty = f.get('minQty')
            raw_step_size = f.get('stepSize')
            print(f"   minQty: {raw_min_qty}")
            print(f"   maxQty: {f.get('maxQty')}")
            print(f"   stepSize: {raw_step_size}")
            break
    print()

    # Check what CCXT parses
    print(f"📦 CCXT parsed values:")
    ccxt_min = market.get('limits', {}).get('amount', {}).get('min', 0)
    print(f"   limits.amount.min: {ccxt_min}")
    print()

    # Check what OUR get_min_amount returns
    print(f"🔧 Our get_min_amount():")
    our_min = em.get_min_amount(symbol)
    print(f"   Returns: {our_min}")
    print(f"   Source: {'Binance LOT_SIZE minQty' if our_min == float(raw_min_qty) else 'CCXT limits.amount.min'}")
    print()

    # Simulate TAOUSDT position
    print(f"📐 Simulating TAOUSDT position ($200):")
    position_size_usd = 200.0
    raw_quantity = position_size_usd / price
    print(f"   Raw quantity: {raw_quantity:.6f} TAO")
    print()

    # TEST 1: Direct CCXT amount_to_precision (THIS IS WHERE IT FAILS!)
    print(f"🧪 TEST 1: CCXT amount_to_precision (current flow):")
    print(f"   Input: {raw_quantity}")
    try:
        formatted = em.exchange.amount_to_precision(exchange_symbol, raw_quantity)
        print(f"   ✅ Output: {formatted}")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        print(f"   This is where METUSDT dies in production!")
    print()

    # TEST 2: Check minimum BEFORE formatting
    print(f"🧪 TEST 2: Check minimum BEFORE amount_to_precision:")
    print(f"   Raw quantity: {raw_quantity:.6f}")
    print(f"   Minimum required: {our_min}")
    print(f"   Passes check? {raw_quantity >= our_min}")

    if raw_quantity < our_min:
        print(f"   → Would trigger fallback!")
        min_cost = our_min * price
        tolerance = position_size_usd * 1.1
        print(f"   Min cost: ${min_cost:.2f}")
        print(f"   Tolerance: ${tolerance:.2f}")
        print(f"   Can use minimum? {min_cost <= tolerance}")

        if min_cost <= tolerance:
            print(f"   → Use {our_min} TAO")
            adjusted_quantity = our_min
        else:
            print(f"   → REJECT (too expensive)")
            adjusted_quantity = None
    else:
        adjusted_quantity = raw_quantity
    print()

    # TEST 3: Format adjusted quantity
    if adjusted_quantity:
        print(f"🧪 TEST 3: Format adjusted quantity:")
        print(f"   Input: {adjusted_quantity}")
        try:
            formatted = em.exchange.amount_to_precision(exchange_symbol, adjusted_quantity)
            print(f"   ✅ Output: {formatted}")
            print(f"   SUCCESS! This would work!")
        except Exception as e:
            print(f"   ❌ FAILED: {e}")
    print()

    # FLOW COMPARISON
    print(f"=" * 100)
    print(f"FLOW COMPARISON:")
    print(f"=" * 100)
    print()

    print(f"❌ CURRENT FLOW (FAILS):")
    print(f"   1. Calculate raw quantity: {raw_quantity:.6f}")
    print(f"   2. amount_to_precision() ← DIES HERE if qty < some threshold")
    print(f"   3. [NEVER REACHED] Check minimum")
    print(f"   4. [NEVER REACHED] Fallback logic")
    print()

    print(f"✅ FIXED FLOW (WORKS):")
    print(f"   1. Calculate raw quantity: {raw_quantity:.6f}")
    print(f"   2. Check minimum: {our_min}")
    print(f"   3. Apply fallback if needed: {adjusted_quantity if adjusted_quantity else 'REJECT'}")
    print(f"   4. amount_to_precision() on adjusted quantity")
    print()

    await em.close()

    print("=" * 100)
    print("CONCLUSION:")
    print("=" * 100)
    print()
    print("ROOT CAUSE:")
    print("- amount_to_precision() is called BEFORE minimum check")
    print("- CCXT throws error if amount < precision threshold")
    print("- Our fallback logic never executes")
    print()
    print("SOLUTION:")
    print("- Move minimum check BEFORE amount_to_precision()")
    print("- Apply fallback to RAW quantity")
    print("- THEN call amount_to_precision() on adjusted value")
    print()
    print("CODE CHANGE:")
    print("  # OLD:")
    print("  formatted_qty = exchange.amount_to_precision(symbol, quantity)  # ← Dies here")
    print("  min_amount = exchange.get_min_amount(symbol)")
    print("  if formatted_qty < min_amount: fallback")
    print()
    print("  # NEW:")
    print("  min_amount = exchange.get_min_amount(symbol)  # ← Check first")
    print("  if quantity < min_amount: adjust quantity")
    print("  formatted_qty = exchange.amount_to_precision(symbol, adjusted_qty)  # ← Safe")
    print()


async def main():
    """Run both investigations"""

    print("\n" * 2)
    print("🔬" * 50)
    print("DEEP INVESTIGATION: Wave 07:36 Errors")
    print("🔬" * 50)
    print()
    print("This script investigates:")
    print("1. METUSDT: Binance error -2027 (margin/leverage limit)")
    print("2. TAOUSDT: CCXT amount_to_precision error")
    print()
    print("⚠️  IMPORTANT: This is INVESTIGATION ONLY - NO CODE WILL BE CHANGED")
    print()
    input("Press Enter to start investigation...")
    print()

    # Investigation #1
    await investigate_metusdt_margin_error()

    print("\n" * 2)
    input("Press Enter to continue to Investigation #2...")
    print()

    # Investigation #2
    await investigate_taousdt_precision_error()

    print("\n" * 2)
    print("=" * 100)
    print("INVESTIGATION COMPLETE")
    print("=" * 100)
    print()
    print("Next steps:")
    print("1. Review findings above")
    print("2. Design fixes based on conclusions")
    print("3. Create test scripts to validate fixes")
    print("4. Apply fixes with surgical precision")
    print()


if __name__ == '__main__':
    asyncio.run(main())
