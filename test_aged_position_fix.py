#!/usr/bin/env python3
"""
Test script for Aged Position Manager fix
Tests market type detection and proper parameter handling for Bybit spot vs swap
"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()


async def test_market_type_detection():
    """Test detecting market type from symbol"""

    print("=" * 70)
    print("TEST: Market Type Detection")
    print("=" * 70)

    # Initialize Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
        }
    })

    # Enable testnet
    if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
        bybit.set_sandbox_mode(True)
        print("✅ Testnet mode enabled")

    try:
        # Load markets
        await bybit.load_markets()

        # Test symbols
        test_symbols = [
            'XDC/USDT',        # SPOT
            'XDC/USDT:USDT',   # SWAP (linear)
            'BTC/USDT:USDT',   # SWAP
            'ETH/USDT',        # SPOT (if exists)
        ]

        for symbol in test_symbols:
            if symbol in bybit.markets:
                market = bybit.markets[symbol]
                print(f"\n📊 {symbol}")
                print(f"  Type: {market['type']}")
                print(f"  Spot: {market['spot']}")
                print(f"  Swap: {market['swap']}")
                print(f"  Linear: {market.get('linear', 'N/A')}")
                print(f"  Contract: {market.get('contract', False)}")

                # Determine if spot or futures
                is_spot = market['spot']
                is_futures = market['swap'] or market.get('future', False)

                print(f"  → Classification: {'SPOT' if is_spot else 'FUTURES/SWAP'}")

                # Show correct params
                if is_spot:
                    print(f"  → Params: {{}} (no reduceOnly/positionIdx for spot)")
                else:
                    print(f"  → Params: {{'reduceOnly': True, 'positionIdx': 0}}")
            else:
                print(f"\n❌ {symbol} not found in markets")

    finally:
        await bybit.close()


async def test_order_creation_dry_run():
    """Test order creation parameters (dry run - no actual orders)"""

    print("\n" + "=" * 70)
    print("TEST: Order Parameter Construction")
    print("=" * 70)

    # Initialize Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
    })

    if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
        bybit.set_sandbox_mode(True)

    try:
        await bybit.load_markets()

        # Test scenarios
        scenarios = [
            {
                'symbol': 'XDC/USDT',  # SPOT
                'type': 'market',
                'side': 'buy',
                'amount': 100,
                'description': 'Close SPOT short position'
            },
            {
                'symbol': 'XDC/USDT:USDT',  # SWAP
                'type': 'market',
                'side': 'buy',
                'amount': 100,
                'description': 'Close SWAP short position'
            },
        ]

        for scenario in scenarios:
            symbol = scenario['symbol']

            if symbol not in bybit.markets:
                print(f"\n❌ {symbol} not in markets, skipping")
                continue

            market = bybit.markets[symbol]
            is_spot = market['spot']

            print(f"\n📝 Scenario: {scenario['description']}")
            print(f"  Symbol: {symbol}")
            print(f"  Market type: {'SPOT' if is_spot else 'FUTURES'}")

            # Build params based on market type
            params = {}

            if not is_spot:
                # Only for futures/swap
                params['reduceOnly'] = True
                params['positionIdx'] = 0

            print(f"  Params: {params}")
            print(f"  ✅ Would create order with:")
            print(f"     symbol={symbol}")
            print(f"     type={scenario['type']}")
            print(f"     side={scenario['side']}")
            print(f"     amount={scenario['amount']}")
            print(f"     params={params}")

            # Validate params don't have issues
            if is_spot and ('reduceOnly' in params or 'positionIdx' in params):
                print(f"  ❌ ERROR: SPOT market should not have reduceOnly/positionIdx!")
            elif not is_spot and 'reduceOnly' not in params:
                print(f"  ⚠️  WARNING: FUTURES market should have reduceOnly!")
            else:
                print(f"  ✅ Parameters are correct for market type")

    finally:
        await bybit.close()


async def test_symbol_normalization():
    """Test how to handle normalized symbols from database"""

    print("\n" + "=" * 70)
    print("TEST: Symbol Normalization & Market Resolution")
    print("=" * 70)

    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
    })

    if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
        bybit.set_sandbox_mode(True)

    try:
        await bybit.load_markets()

        # Normalized symbol from database
        normalized_symbol = 'XDCUSDT'

        print(f"\n📌 Database symbol: {normalized_symbol}")
        print(f"  Need to find matching market...")

        # Find matching markets
        matching_markets = []
        for market_symbol, market in bybit.markets.items():
            # Check if this market matches normalized symbol
            base_quote = market['base'] + market['quote']
            if base_quote == normalized_symbol:
                matching_markets.append((market_symbol, market))

        print(f"\n  Found {len(matching_markets)} matching markets:")
        for market_symbol, market in matching_markets:
            print(f"    - {market_symbol} ({market['type']})")

        # Problem: How to know which one was used?
        print(f"\n❓ PROBLEM: Cannot determine if original position was SPOT or SWAP")
        print(f"  from normalized symbol '{normalized_symbol}' alone!")

        print(f"\n💡 SOLUTIONS:")
        print(f"  1. Add 'market_type' field to positions table")
        print(f"  2. Store full CCXT symbol format (e.g., 'XDC/USDT:USDT')")
        print(f"  3. Default to FUTURES if multiple markets exist")
        print(f"  4. Query exchange to check if position exists on futures")

        # Solution 4: Check actual positions
        print(f"\n🔍 Solution 4: Check exchange positions...")

        try:
            # Fetch positions (futures only)
            positions = await bybit.fetch_positions(params={'category': 'linear'})

            xdc_positions = [p for p in positions if 'XDC' in p['symbol']]

            if xdc_positions:
                print(f"  ✅ Found XDC position on FUTURES:")
                for pos in xdc_positions:
                    print(f"     {pos['symbol']}: {pos['side']} {pos['contracts']}")
                print(f"  → Use FUTURES params (reduceOnly, positionIdx)")
            else:
                print(f"  ❌ No XDC position on FUTURES")
                print(f"  → Might be SPOT, use empty params")

        except Exception as e:
            print(f"  ⚠️  Could not fetch positions: {e}")

    finally:
        await bybit.close()


async def test_proposed_fix():
    """Test the proposed fix logic"""

    print("\n" + "=" * 70)
    print("TEST: Proposed Fix - get_market_params()")
    print("=" * 70)

    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
    })

    if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
        bybit.set_sandbox_mode(True)

    try:
        await bybit.load_markets()

        def get_market_params(exchange: ccxt.Exchange, symbol: str) -> dict:
            """
            Get correct params for market order based on market type

            Args:
                exchange: CCXT exchange instance
                symbol: Trading symbol (CCXT format e.g., 'XDC/USDT:USDT')

            Returns:
                dict with appropriate params for the market type
            """
            params = {}

            if symbol not in exchange.markets:
                # Symbol not found, try to guess
                # For Bybit, if symbol doesn't have :USDT suffix, might be spot
                if exchange.id == 'bybit':
                    if ':' not in symbol:
                        # Likely SPOT, no special params
                        print(f"  → Symbol '{symbol}' has no ':' - assuming SPOT")
                        return params
                    else:
                        # Has ':' suffix - likely futures/swap
                        print(f"  → Symbol '{symbol}' has ':' - assuming FUTURES")
                        params['reduceOnly'] = True
                        params['positionIdx'] = 0
                        return params

            market = exchange.markets[symbol]
            is_spot = market['spot']

            if not is_spot:
                # Futures/Swap - add reduce params
                if exchange.id == 'bybit':
                    params['reduceOnly'] = True
                    params['positionIdx'] = 0
                elif exchange.id == 'binance':
                    params['reduceOnly'] = True

            return params

        # Test the function
        test_cases = [
            'XDC/USDT',        # SPOT
            'XDC/USDT:USDT',   # SWAP
            'BTC/USDT:USDT',   # SWAP
        ]

        for symbol in test_cases:
            print(f"\n📝 Testing: {symbol}")
            params = get_market_params(bybit, symbol)
            print(f"  Result params: {params}")

            if symbol in bybit.markets:
                market = bybit.markets[symbol]
                expected_has_params = not market['spot']
                actual_has_params = len(params) > 0

                if expected_has_params == actual_has_params:
                    print(f"  ✅ CORRECT")
                else:
                    print(f"  ❌ WRONG - expected params: {expected_has_params}, got: {actual_has_params}")

    finally:
        await bybit.close()


async def main():
    """Run all tests"""

    print("\n" + "="*70)
    print(" AGED POSITION MANAGER FIX - TEST SUITE")
    print("="*70)
    print("\nTesting Bybit market type detection and parameter handling")
    print("Environment: TESTNET" if os.getenv('BYBIT_TESTNET') == 'true' else "PRODUCTION")
    print("="*70)

    try:
        await test_market_type_detection()
        await test_order_creation_dry_run()
        await test_symbol_normalization()
        await test_proposed_fix()

        print("\n" + "="*70)
        print(" TEST SUITE COMPLETE")
        print("="*70)

        print("\n📋 CONCLUSIONS:")
        print("  1. Bybit has both SPOT and SWAP markets for same coins")
        print("  2. reduceOnly/positionIdx only valid for SWAP/FUTURES")
        print("  3. Must detect market type before creating close order")
        print("  4. Symbol format with ':USDT' indicates SWAP/FUTURES")
        print("  5. Symbol without ':' is SPOT")

        print("\n✅ RECOMMENDED FIX:")
        print("  Add market type detection in aged_position_manager.py:")
        print("  - Check if symbol contains ':' for initial guess")
        print("  - Use exchange.markets[symbol] if available")
        print("  - Only add reduceOnly/positionIdx for non-SPOT markets")

    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
