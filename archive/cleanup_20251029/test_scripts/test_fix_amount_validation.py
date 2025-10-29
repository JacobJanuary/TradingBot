#!/usr/bin/env python3
"""
TEST SCRIPT: FIX #2 - Amount Validation Reordering

Tests the proposed solution for TAOUSDT precision error:
- Check minimum BEFORE calling amount_to_precision()
- Apply fallback logic to RAW quantity
- THEN format with amount_to_precision()

CRITICAL: This is TESTING ONLY - NO CODE CHANGES!
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
import math

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager


def proposed_calculate_position_size_fixed(exchange, symbol: str, price: float, size_usd: float) -> dict:
    """
    PROPOSED SOLUTION: Fixed position size calculation

    This simulates the fix we want to implement.

    OLD FLOW (BROKEN):
    1. quantity = size_usd / price
    2. formatted_qty = amount_to_precision(quantity)  ← DIES HERE
    3. if formatted_qty < min: fallback  ← NEVER REACHED

    NEW FLOW (FIXED):
    1. quantity = size_usd / price
    2. min_amount = get_min_amount()  ← CHECK FIRST
    3. if quantity < min: adjust quantity  ← BEFORE formatting
    4. formatted_qty = amount_to_precision(adjusted)  ← SAFE

    Returns:
        {
            'success': bool,
            'quantity': float or None,
            'flow': str,  # 'normal', 'fallback', 'reject'
            'error': str or None,
            'details': dict
        }
    """
    result = {
        'success': False,
        'quantity': None,
        'flow': 'unknown',
        'error': None,
        'details': {}
    }

    try:
        # Step 1: Calculate raw quantity
        raw_quantity = size_usd / price
        result['details']['raw_quantity'] = raw_quantity
        result['details']['size_usd'] = size_usd
        result['details']['price'] = price

        # Step 2: Get minimum amount (using our fixed get_min_amount)
        min_amount = exchange.get_min_amount(symbol)
        result['details']['min_amount'] = min_amount

        # Step 3: Check if raw quantity meets minimum BEFORE formatting
        adjusted_quantity = raw_quantity

        if raw_quantity < min_amount:
            # Fallback logic
            min_cost = min_amount * price
            tolerance = size_usd * 1.1  # 10% over budget

            result['details']['min_cost'] = min_cost
            result['details']['tolerance'] = tolerance

            if min_cost <= tolerance:
                # Use minimum
                adjusted_quantity = min_amount
                result['flow'] = 'fallback'
                result['details']['adjusted_to'] = min_amount
            else:
                # Reject - too expensive
                result['flow'] = 'reject'
                result['error'] = f"Minimum ${min_cost:.2f} exceeds tolerance ${tolerance:.2f}"
                return result
        else:
            result['flow'] = 'normal'

        result['details']['adjusted_quantity'] = adjusted_quantity

        # Step 4: NOW format with amount_to_precision (should be safe!)
        try:
            formatted_qty = exchange.amount_to_precision(symbol, adjusted_quantity)
            result['quantity'] = float(formatted_qty)
            result['success'] = True
            result['details']['formatted_qty'] = formatted_qty
        except Exception as e:
            result['error'] = f"amount_to_precision failed: {e}"
            result['details']['formatting_error'] = str(e)

        return result

    except Exception as e:
        result['error'] = f"Unexpected error: {e}"
        return result


async def test_amount_validation():
    """
    Test the proposed amount validation solution
    """
    print("=" * 100)
    print("TEST: FIX #2 - Amount Validation Reordering")
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

    # Test cases
    test_cases = [
        {
            'symbol': 'TAOUSDT',
            'size_usd': 200,
            'description': 'Original failure case',
            'expected_flow': 'fallback',  # Should use minimum
        },
        {
            'symbol': 'AAVEUSDT',
            'size_usd': 200,
            'description': 'Previously fixed case',
            'expected_flow': 'fallback',
        },
        {
            'symbol': 'BTCUSDT',
            'size_usd': 200,
            'description': 'Normal case (high price)',
            'expected_flow': 'normal',
        },
        {
            'symbol': 'DOGEUSDT',
            'size_usd': 200,
            'description': 'Normal case (low price)',
            'expected_flow': 'normal',
        },
        {
            'symbol': 'ETHUSDT',
            'size_usd': 50,
            'description': 'Small position',
            'expected_flow': 'normal',
        },
    ]

    results = []

    for test in test_cases:
        symbol = test['symbol']
        print(f"Testing: {symbol}")
        print(f"Description: {test['description']}")
        print(f"Expected flow: {test['expected_flow']}")
        print()

        # Get current price
        ticker = await em.fetch_ticker(symbol)
        price = ticker['last']

        # Test OLD flow (current broken implementation)
        print(f"  OLD FLOW (current implementation):")
        raw_quantity = test['size_usd'] / price
        print(f"    Raw quantity: {raw_quantity:.6f}")

        old_success = False
        old_error = None
        try:
            formatted = em.exchange.amount_to_precision(em.find_exchange_symbol(symbol), raw_quantity)
            print(f"    ✅ amount_to_precision: {formatted}")
            old_success = True
        except Exception as e:
            print(f"    ❌ amount_to_precision FAILED: {e}")
            old_error = str(e)

        print()

        # Test NEW flow (proposed fix)
        print(f"  NEW FLOW (proposed fix):")
        new_result = proposed_calculate_position_size_fixed(em, symbol, price, test['size_usd'])

        print(f"    Flow: {new_result['flow']}")
        print(f"    Success: {new_result['success']}")

        if new_result['success']:
            print(f"    ✅ Final quantity: {new_result['quantity']}")
            print(f"    Details:")
            for key, value in new_result['details'].items():
                if isinstance(value, float):
                    print(f"      {key}: {value:.6f}")
                else:
                    print(f"      {key}: {value}")
        else:
            print(f"    ❌ Error: {new_result['error']}")

        # Compare flows
        print()
        print(f"  COMPARISON:")
        print(f"    Old flow: {'✅ PASS' if old_success else '❌ FAIL'}")
        print(f"    New flow: {'✅ PASS' if new_result['success'] else '❌ FAIL'}")

        if not old_success and new_result['success']:
            print(f"    🎯 FIX WORKS! Old failed, new succeeds!")
        elif old_success and new_result['success']:
            print(f"    ✅ Both work (no regression)")
        elif not old_success and not new_result['success']:
            print(f"    ⚠️ Both fail (expected for reject cases)")
        else:
            print(f"    ❌ REGRESSION! Old worked, new fails!")

        print()
        print("-" * 100)
        print()

        results.append({
            'symbol': symbol,
            'size_usd': test['size_usd'],
            'expected_flow': test['expected_flow'],
            'old_success': old_success,
            'old_error': old_error,
            'new_result': new_result
        })

    await em.close()

    # Summary
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()

    print(f"{'Symbol':<15} {'Size':<10} {'Expected':<12} {'Old':<8} {'New':<8} {'Flow':<12} {'Status':<15}")
    print("-" * 100)

    for r in results:
        symbol = r['symbol']
        size = f"${r['size_usd']}"
        expected = r['expected_flow']
        old = '✅' if r['old_success'] else '❌'
        new = '✅' if r['new_result']['success'] else '❌'
        flow = r['new_result']['flow']

        if not r['old_success'] and r['new_result']['success']:
            status = 'FIXED! 🎯'
        elif r['old_success'] and r['new_result']['success']:
            status = 'No regression ✅'
        elif not r['old_success'] and not r['new_result']['success']:
            status = 'Both fail (OK)'
        else:
            status = 'REGRESSION! ❌'

        print(f"{symbol:<15} {size:<10} {expected:<12} {old:<8} {new:<8} {flow:<12} {status:<15}")

    print()
    print("=" * 100)
    print("CONCLUSION")
    print("=" * 100)
    print()

    # Check if all expected failures are fixed
    fixes = [r for r in results if not r['old_success'] and r['new_result']['success']]
    regressions = [r for r in results if r['old_success'] and not r['new_result']['success']]

    print(f"Fixed cases: {len(fixes)}")
    if fixes:
        for r in fixes:
            print(f"  - {r['symbol']}: {r['old_error']}")
    print()

    print(f"Regressions: {len(regressions)}")
    if regressions:
        print("  ❌ WARNING: Fix introduces regressions!")
        for r in regressions:
            print(f"  - {r['symbol']}: {r['new_result']['error']}")
    else:
        print("  ✅ No regressions detected")
    print()

    print("The proposed fix:")
    print("1. ✅ Checks minimum BEFORE amount_to_precision()")
    print("2. ✅ Applies fallback to RAW quantity")
    print("3. ✅ Formats adjusted quantity safely")
    print("4. ✅ Prevents CCXT from throwing errors prematurely")
    print()

    print("Implementation location:")
    print("- core/position_manager.py:1518-1533")
    print("- Reorder lines 1519 and 1522")
    print("- Move fallback logic before formatting")
    print()

    print("Code change:")
    print("  # OLD:")
    print("  formatted_qty = exchange.amount_to_precision(symbol, quantity)  # Line 1519")
    print("  min_amount = exchange.get_min_amount(symbol)  # Line 1522")
    print("  if formatted_qty < min_amount: fallback  # Line 1523")
    print()
    print("  # NEW:")
    print("  min_amount = exchange.get_min_amount(symbol)  # CHECK FIRST")
    print("  adjusted_qty = quantity")
    print("  if quantity < min_amount:")
    print("      adjusted_qty = apply_fallback(quantity, min_amount, price, size_usd)")
    print("  formatted_qty = exchange.amount_to_precision(symbol, adjusted_qty)  # SAFE")
    print()


async def main():
    print("\n" * 2)
    print("🧪" * 50)
    print("TEST: FIX #2 - Amount Validation Reordering")
    print("🧪" * 50)
    print()
    print("This script tests the PROPOSED solution for TAOUSDT precision error")
    print()
    print("⚠️  IMPORTANT: This is TESTING ONLY - NO CODE WILL BE CHANGED")
    print()
    input("Press Enter to start tests...")
    print()

    await test_amount_validation()

    print("\n" * 2)
    print("=" * 100)
    print("TEST COMPLETE")
    print("=" * 100)
    print()


if __name__ == '__main__':
    asyncio.run(main())
