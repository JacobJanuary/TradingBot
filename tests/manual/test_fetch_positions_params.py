#!/usr/bin/env python3
"""
BYBIT FETCH_POSITIONS PARAMS DIAGNOSTIC
========================================

Date: 2025-10-29 05:15
Critical Finding: Код использует params={'category': 'linear'}, но CCXT требует params={'subType': 'linear'}

Этот тест проверяет:
1. fetch_positions БЕЗ params
2. fetch_positions С params={'category': 'linear'} (текущий код - НЕПРАВИЛЬНО?)
3. fetch_positions С params={'subType': 'linear'} (правильный по CCXT docs)

NO ORDER CREATION - только читаем существующие позиции!
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
    """Test fetch_positions with different params"""

    # Setup
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

    if not api_key or not api_secret:
        print("❌ BYBIT_API_KEY and BYBIT_API_SECRET must be set")
        return

    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
        }
    })

    if testnet:
        exchange.set_sandbox_mode(True)
        print("⚠️  Using TESTNET")
    else:
        print("✅ Using MAINNET (real account)")

    print()
    print("=" * 80)
    print("BYBIT fetch_positions PARAMS TEST")
    print("=" * 80)
    print()

    results = {}

    try:
        # TEST 1: БЕЗ params (как в test script - работает)
        print("TEST 1: fetch_positions() WITHOUT params")
        print("-" * 80)
        print("CALL: exchange.fetch_positions()")
        print()

        try:
            positions_1 = await exchange.fetch_positions()
            non_zero_1 = [p for p in positions_1 if float(p.get('contracts', 0)) != 0]

            print(f"✅ Result: {len(positions_1)} total, {len(non_zero_1)} non-zero positions")
            print()

            if non_zero_1:
                print("Non-zero positions:")
                for pos in non_zero_1:
                    symbol = pos.get('symbol', 'N/A')
                    contracts = pos.get('contracts', 0)
                    side = pos.get('side', 'N/A')
                    print(f"  - {symbol}: {contracts} contracts, {side}")
                print()

            results['test1_no_params'] = {
                'status': 'success',
                'total_positions': len(positions_1),
                'non_zero_positions': len(non_zero_1),
                'symbols': [p.get('symbol') for p in non_zero_1]
            }

        except Exception as e:
            print(f"❌ FAILED: {e}")
            print()
            results['test1_no_params'] = {
                'status': 'failed',
                'error': str(e)
            }

        # TEST 2: С params={'category': 'linear'} (текущий production код)
        print("TEST 2: fetch_positions() WITH params={'category': 'linear'}")
        print("-" * 80)
        print("CALL: exchange.fetch_positions(params={'category': 'linear'})")
        print()

        try:
            positions_2 = await exchange.fetch_positions(params={'category': 'linear'})
            non_zero_2 = [p for p in positions_2 if float(p.get('contracts', 0)) != 0]

            print(f"✅ Result: {len(positions_2)} total, {len(non_zero_2)} non-zero positions")
            print()

            if non_zero_2:
                print("Non-zero positions:")
                for pos in non_zero_2:
                    symbol = pos.get('symbol', 'N/A')
                    contracts = pos.get('contracts', 0)
                    side = pos.get('side', 'N/A')
                    print(f"  - {symbol}: {contracts} contracts, {side}")
                print()

            results['test2_category_linear'] = {
                'status': 'success',
                'total_positions': len(positions_2),
                'non_zero_positions': len(non_zero_2),
                'symbols': [p.get('symbol') for p in non_zero_2]
            }

        except Exception as e:
            print(f"❌ FAILED: {e}")
            print()
            results['test2_category_linear'] = {
                'status': 'failed',
                'error': str(e)
            }

        # TEST 3: С params={'subType': 'linear'} (правильный по CCXT docs)
        print("TEST 3: fetch_positions() WITH params={'subType': 'linear'}")
        print("-" * 80)
        print("CALL: exchange.fetch_positions(params={'subType': 'linear'})")
        print()

        try:
            positions_3 = await exchange.fetch_positions(params={'subType': 'linear'})
            non_zero_3 = [p for p in positions_3 if float(p.get('contracts', 0)) != 0]

            print(f"✅ Result: {len(positions_3)} total, {len(non_zero_3)} non-zero positions")
            print()

            if non_zero_3:
                print("Non-zero positions:")
                for pos in non_zero_3:
                    symbol = pos.get('symbol', 'N/A')
                    contracts = pos.get('contracts', 0)
                    side = pos.get('side', 'N/A')
                    print(f"  - {symbol}: {contracts} contracts, {side}")
                print()

            results['test3_subtype_linear'] = {
                'status': 'success',
                'total_positions': len(positions_3),
                'non_zero_positions': len(non_zero_3),
                'symbols': [p.get('symbol') for p in non_zero_3]
            }

        except Exception as e:
            print(f"❌ FAILED: {e}")
            print()
            results['test3_subtype_linear'] = {
                'status': 'failed',
                'error': str(e)
            }

        # TEST 4: С symbols параметром + category (как в production)
        if non_zero_1:
            test_symbol = non_zero_1[0].get('info', {}).get('symbol', non_zero_1[0].get('symbol'))

            print(f"TEST 4: fetch_positions(symbols=['{test_symbol}'], params={{'category': 'linear'}})")
            print("-" * 80)
            print(f"CALL: exchange.fetch_positions(symbols=['{test_symbol}'], params={{'category': 'linear'}})")
            print()

            try:
                positions_4 = await exchange.fetch_positions(
                    symbols=[test_symbol],
                    params={'category': 'linear'}
                )
                non_zero_4 = [p for p in positions_4 if float(p.get('contracts', 0)) != 0]

                print(f"✅ Result: {len(positions_4)} total, {len(non_zero_4)} non-zero positions")
                print()

                if non_zero_4:
                    print("Non-zero positions:")
                    for pos in non_zero_4:
                        symbol = pos.get('symbol', 'N/A')
                        contracts = pos.get('contracts', 0)
                        side = pos.get('side', 'N/A')
                        print(f"  - {symbol}: {contracts} contracts, {side}")
                    print()

                results['test4_symbols_with_category'] = {
                    'status': 'success',
                    'test_symbol': test_symbol,
                    'total_positions': len(positions_4),
                    'non_zero_positions': len(non_zero_4),
                    'found': len(non_zero_4) > 0
                }

            except Exception as e:
                print(f"❌ FAILED: {e}")
                print()
                results['test4_symbols_with_category'] = {
                    'status': 'failed',
                    'test_symbol': test_symbol,
                    'error': str(e)
                }

            # TEST 5: С symbols параметром + subType (правильный вариант)
            print(f"TEST 5: fetch_positions(symbols=['{test_symbol}'], params={{'subType': 'linear'}})")
            print("-" * 80)
            print(f"CALL: exchange.fetch_positions(symbols=['{test_symbol}'], params={{'subType': 'linear'}})")
            print()

            try:
                positions_5 = await exchange.fetch_positions(
                    symbols=[test_symbol],
                    params={'subType': 'linear'}
                )
                non_zero_5 = [p for p in positions_5 if float(p.get('contracts', 0)) != 0]

                print(f"✅ Result: {len(positions_5)} total, {len(non_zero_5)} non-zero positions")
                print()

                if non_zero_5:
                    print("Non-zero positions:")
                    for pos in non_zero_5:
                        symbol = pos.get('symbol', 'N/A')
                        contracts = pos.get('contracts', 0)
                        side = pos.get('side', 'N/A')
                        print(f"  - {symbol}: {contracts} contracts, {side}")
                    print()

                results['test5_symbols_with_subtype'] = {
                    'status': 'success',
                    'test_symbol': test_symbol,
                    'total_positions': len(positions_5),
                    'non_zero_positions': len(non_zero_5),
                    'found': len(non_zero_5) > 0
                }

            except Exception as e:
                print(f"❌ FAILED: {e}")
                print()
                results['test5_symbols_with_subtype'] = {
                    'status': 'failed',
                    'test_symbol': test_symbol,
                    'error': str(e)
                }

        # SUMMARY
        print()
        print("=" * 80)
        print("SUMMARY & VERDICT")
        print("=" * 80)
        print()

        print("Results:")
        print(json.dumps(results, indent=2, default=str))
        print()

        # Analysis
        print("ANALYSIS:")
        print("-" * 80)

        test1_count = results.get('test1_no_params', {}).get('non_zero_positions', 0)
        test2_count = results.get('test2_category_linear', {}).get('non_zero_positions', 0)
        test3_count = results.get('test3_subtype_linear', {}).get('non_zero_positions', 0)

        print(f"Test 1 (no params):            {test1_count} positions")
        print(f"Test 2 (category='linear'):    {test2_count} positions")
        print(f"Test 3 (subType='linear'):     {test3_count} positions")
        print()

        if test1_count > 0 and test2_count == 0:
            print("❌ CRITICAL BUG CONFIRMED!")
            print("   params={'category': 'linear'} BREAKS fetch_positions!")
            print("   This is WHY production code can't find positions!")
            print()
        elif test1_count == test2_count == test3_count:
            print("✅ All methods return same results")
            print("   params={'category': 'linear'} works fine")
            print()

        if 'test4_symbols_with_category' in results:
            test4_found = results['test4_symbols_with_category'].get('found', False)
            test5_found = results.get('test5_symbols_with_subtype', {}).get('found', False)

            print(f"Test 4 (symbols + category):   {'FOUND' if test4_found else 'NOT FOUND'}")
            print(f"Test 5 (symbols + subType):    {'FOUND' if test5_found else 'NOT FOUND'}")
            print()

            if not test4_found and test5_found:
                print("❌ SMOKING GUN!")
                print("   symbols + category='linear' = NOT FOUND")
                print("   symbols + subType='linear' = FOUND")
                print("   FIX: Change 'category' to 'subType' in production code!")
                print()

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_results_fetch_positions_params_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"📁 Results saved to: {filename}")
        print()

    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(main())
