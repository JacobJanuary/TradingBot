#!/usr/bin/env python3
"""
BYBIT positionIdx FIX VALIDATION TEST
======================================
Quick test to validate the positionIdx fix works

USAGE:
    python3 tests/test_bybit_positionidx_fix.py

This will create a MINIMAL BTC position (~$110) to validate the fix.
Position will be automatically closed after creation.
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import ccxt.async_support as ccxt
from config.settings import config

# Test configuration
TEST_SYMBOL = 'BTC/USDT:USDT'
TEST_AMOUNT = 0.001  # ~$110 at current BTC price
TEST_LEVERAGE = 1


async def test_bybit_position_creation():
    """Test creating a position with positionIdx parameter"""
    print("="*60)
    print("BYBIT positionIdx FIX VALIDATION TEST")
    print("="*60)

    bybit_config = config.get_exchange_config('bybit')

    exchange = ccxt.bybit({
        'apiKey': bybit_config.api_key,
        'secret': bybit_config.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
            'brokerId': ''
        }
    })

    try:
        await exchange.load_markets()

        # Get current price
        ticker = await exchange.fetch_ticker(TEST_SYMBOL)
        print(f"\n✅ Symbol: {TEST_SYMBOL}")
        print(f"✅ Current price: ${ticker['last']}")
        print(f"✅ Test amount: {TEST_AMOUNT} BTC")
        print(f"✅ Position value: ~${TEST_AMOUNT * ticker['last']:.2f}")

        # Test 1: Create order WITH positionIdx (should succeed)
        print(f"\n{'='*60}")
        print("TEST 1: Market order WITH positionIdx=0 (THE FIX)")
        print(f"{'='*60}")

        params = {'positionIdx': 0}  # One-way mode

        print(f"\nCreating BUY order...")
        print(f"  Symbol: {TEST_SYMBOL}")
        print(f"  Amount: {TEST_AMOUNT}")
        print(f"  Params: {params}")

        order = await exchange.create_order(
            symbol=TEST_SYMBOL,
            type='market',
            side='buy',
            amount=TEST_AMOUNT,
            price=None,
            params=params
        )

        print(f"\n✅ SUCCESS! Order created:")
        print(f"   Order ID: {order['id']}")
        print(f"   Status: {order['status']}")
        print(f"   Filled: {order['filled']}")
        print(f"   Average: {order.get('average', 'N/A')}")

        # Wait a bit for position to settle
        await asyncio.sleep(2)

        # Close position
        print(f"\n{'='*60}")
        print("CLEANUP: Closing test position")
        print(f"{'='*60}")

        close_params = {
            'positionIdx': 0,
            'reduce_only': True
        }

        close_order = await exchange.create_order(
            symbol=TEST_SYMBOL,
            type='market',
            side='sell',
            amount=TEST_AMOUNT,
            price=None,
            params=close_params
        )

        print(f"\n✅ Position closed successfully")
        print(f"   Close Order ID: {close_order['id']}")

        # Summary
        print(f"\n{'='*60}")
        print("TEST RESULT: ✅ SUCCESS")
        print(f"{'='*60}")
        print("\nThe fix works correctly!")
        print("- Market order created WITH positionIdx=0: ✅")
        print("- Position opened successfully: ✅")
        print("- Position closed successfully: ✅")
        print("\nReady to deploy to production!")

        return True

    except Exception as e:
        print(f"\n{'='*60}")
        print("TEST RESULT: ❌ FAILED")
        print(f"{'='*60}")
        print(f"\nError: {e}")

        import traceback
        traceback.print_exc()

        print("\n⚠️ Fix may need adjustment or there's another issue.")

        return False

    finally:
        await exchange.close()


async def main():
    print("\n⚠️ WARNING: This test will create a REAL position on Bybit mainnet!")
    print(f"Position size: ~$110 (0.001 BTC)")
    print(f"Position will be automatically closed after creation.\n")

    response = input("Continue? [y/N]: ")
    if response.lower() != 'y':
        print("Test cancelled.")
        return

    success = await test_bybit_position_creation()

    if success:
        print("\n🎉 FIX VALIDATED! Safe to deploy.")
        sys.exit(0)
    else:
        print("\n⚠️ FIX VALIDATION FAILED! Review before deploying.")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
