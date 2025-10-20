#!/usr/bin/env python3
"""
TEST SCRIPT: FIX #1 - Margin/Leverage Validation

Tests the proposed solution for METUSDT error -2027:
- Check available margin BEFORE opening position
- Validate against maxNotionalValue from position risk API
- Ensure we don't exceed account limits

CRITICAL: This is TESTING ONLY - NO CODE CHANGES!
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


async def proposed_can_open_position(exchange: ExchangeManager, symbol: str, notional_usd: float) -> dict:
    """
    PROPOSED SOLUTION: Check if we can open a position

    This simulates the fix we want to implement.

    Returns:
        {
            'can_open': bool,
            'reason': str,
            'available_margin': float,
            'current_notional': float,
            'max_notional': float,
            'would_exceed': bool
        }
    """
    result = {
        'can_open': False,
        'reason': 'Unknown',
        'available_margin': 0.0,
        'current_notional': 0.0,
        'max_notional': 0.0,
        'would_exceed': False,
        'total_positions': 0,
        'free_balance': 0.0
    }

    try:
        # Step 1: Get balance
        balance = await exchange.exchange.fetch_balance()
        free_usdt = balance.get('USDT', {}).get('free', 0)
        total_usdt = balance.get('USDT', {}).get('total', 0)

        result['free_balance'] = free_usdt
        result['available_margin'] = free_usdt

        # Simple check: do we have enough free balance?
        if free_usdt < notional_usd:
            result['reason'] = f"Insufficient free balance: ${free_usdt:.2f} < ${notional_usd:.2f}"
            return result

        # Step 2: Get current positions and total notional
        positions = await exchange.exchange.fetch_positions()
        active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        total_notional = sum(abs(float(p.get('notional', 0))) for p in active_positions)

        result['current_notional'] = total_notional
        result['total_positions'] = len(active_positions)

        # Step 3: Try to get maxNotionalValue for the account
        # This is the CRITICAL check that prevents error -2027
        try:
            exchange_symbol = exchange.find_exchange_symbol(symbol)
            symbol_clean = exchange_symbol.replace('/USDT:USDT', 'USDT')

            # Get position risk which includes maxNotionalValue
            position_risk = await exchange.exchange.fapiPrivateV2GetPositionRisk({'symbol': symbol_clean})

            max_notional = None
            for risk in position_risk:
                if risk.get('symbol') == symbol_clean:
                    max_notional_str = risk.get('maxNotionalValue', '0')
                    max_notional = float(max_notional_str) if max_notional_str != 'INF' else float('inf')
                    leverage = int(risk.get('leverage', 1))
                    break

            if max_notional is not None and max_notional != float('inf'):
                result['max_notional'] = max_notional

                # Check if new position would exceed max notional
                new_total = total_notional + notional_usd

                if new_total > max_notional:
                    result['would_exceed'] = True
                    result['reason'] = f"Would exceed max notional: ${new_total:.2f} > ${max_notional:.2f}"
                    return result
        except Exception as e:
            # If we can't get maxNotionalValue, log warning but don't block
            print(f"   ⚠️ Could not fetch maxNotionalValue: {e}")
            print(f"   Proceeding with basic balance check only")

        # Step 4: Conservative check - ensure we don't use too much of total balance
        utilization_after = (total_notional + notional_usd) / total_usdt if total_usdt > 0 else 0

        MAX_UTILIZATION = 0.80  # Don't use more than 80% of total balance

        if utilization_after > MAX_UTILIZATION:
            result['reason'] = f"Would exceed safe utilization: {utilization_after*100:.1f}% > {MAX_UTILIZATION*100:.1f}%"
            return result

        # All checks passed!
        result['can_open'] = True
        result['reason'] = "All checks passed"
        return result

    except Exception as e:
        result['reason'] = f"Error during validation: {e}"
        return result


async def test_margin_validation():
    """
    Test the proposed margin validation solution
    """
    print("=" * 100)
    print("TEST: FIX #1 - Margin/Leverage Validation")
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

    # Test symbols that failed and some that should work
    test_cases = [
        {'symbol': 'METUSDT', 'size_usd': 200, 'should_fail': True, 'reason': 'This failed in production'},
        {'symbol': 'GASUSDT', 'size_usd': 200, 'should_fail': False, 'reason': 'This worked in production'},
        {'symbol': 'BTCUSDT', 'size_usd': 200, 'should_fail': False, 'reason': 'Should work'},
        {'symbol': 'ETHUSDT', 'size_usd': 500, 'should_fail': None, 'reason': 'Larger position'},
        {'symbol': 'ADAUSDT', 'size_usd': 100, 'should_fail': False, 'reason': 'Smaller position'},
    ]

    results = []

    for test in test_cases:
        print(f"Testing: {test['symbol']} (${test['size_usd']} USD)")
        print(f"Expected: {'FAIL' if test['should_fail'] else 'PASS' if test['should_fail'] is False else 'UNKNOWN'}")

        validation = await proposed_can_open_position(em, test['symbol'], test['size_usd'])

        print(f"Result: {'✅ CAN OPEN' if validation['can_open'] else '❌ CANNOT OPEN'}")
        print(f"Reason: {validation['reason']}")
        print(f"Details:")
        print(f"  Free balance: ${validation['free_balance']:.2f}")
        print(f"  Current notional: ${validation['current_notional']:.2f}")
        print(f"  Total positions: {validation['total_positions']}")

        if validation['max_notional'] > 0:
            print(f"  Max notional: ${validation['max_notional']:.2f}")
            new_total = validation['current_notional'] + test['size_usd']
            print(f"  After new position: ${new_total:.2f}")
            print(f"  Would exceed? {validation['would_exceed']}")

        # Verify expectations
        if test['should_fail'] is not None:
            expected = not test['should_fail']  # should_fail=True means can_open=False
            actual = validation['can_open']

            if expected == actual:
                print(f"  ✅ MATCHES EXPECTATION")
            else:
                print(f"  ❌ UNEXPECTED RESULT!")
                print(f"     Expected can_open={expected}, got {actual}")

        print()

        results.append({
            'symbol': test['symbol'],
            'size_usd': test['size_usd'],
            'expected_fail': test['should_fail'],
            'validation': validation
        })

    await em.close()

    # Summary
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()

    print(f"{'Symbol':<15} {'Size':<10} {'Expected':<12} {'Result':<15} {'Match':<8}")
    print("-" * 100)

    for r in results:
        symbol = r['symbol']
        size = f"${r['size_usd']}"
        expected = 'FAIL' if r['expected_fail'] else 'PASS' if r['expected_fail'] is False else 'UNKNOWN'
        result = 'CAN OPEN' if r['validation']['can_open'] else 'CANNOT OPEN'

        if r['expected_fail'] is not None:
            expected_can_open = not r['expected_fail']
            actual_can_open = r['validation']['can_open']
            match = '✅' if expected_can_open == actual_can_open else '❌'
        else:
            match = '?'

        print(f"{symbol:<15} {size:<10} {expected:<12} {result:<15} {match:<8}")

    print()
    print("=" * 100)
    print("CONCLUSION")
    print("=" * 100)
    print()

    print("The proposed fix includes:")
    print("1. ✅ Check free balance")
    print("2. ✅ Get current total notional from all positions")
    print("3. ✅ Query maxNotionalValue from position risk API")
    print("4. ✅ Validate: current_notional + new_position <= maxNotionalValue")
    print("5. ✅ Conservative utilization limit (80% of total balance)")
    print()

    print("This fix would prevent error -2027 by:")
    print("- Rejecting position BEFORE sending to Binance")
    print("- Providing clear error message to user")
    print("- Not wasting atomic operation rollback")
    print()

    print("Implementation location:")
    print("- core/position_manager.py: _calculate_position_size()")
    print("- Add validation before returning formatted_qty")
    print("- Or create new method: exchange.can_open_position()")
    print()


async def main():
    print("\n" * 2)
    print("🧪" * 50)
    print("TEST: FIX #1 - Margin/Leverage Validation")
    print("🧪" * 50)
    print()
    print("This script tests the PROPOSED solution for METUSDT error -2027")
    print()
    print("⚠️  IMPORTANT: This is TESTING ONLY - NO CODE WILL BE CHANGED")
    print()
    input("Press Enter to start tests...")
    print()

    await test_margin_validation()

    print("\n" * 2)
    print("=" * 100)
    print("TEST COMPLETE")
    print("=" * 100)
    print()


if __name__ == '__main__':
    asyncio.run(main())
