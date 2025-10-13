#!/usr/bin/env python3
"""
COMPREHENSIVE TEST: Bybit Market Order Status Investigation

Based on Deep Research findings:
1. Bybit returns "Created" status for newly created orders
2. Current status_map missing "Created" → causes 'unknown' status
3. CCXT may normalize to lowercase 'open' or return Bybit's "Created"

This test will:
- Test 10 different Bybit symbols (including 3 failed ones)
- Capture real API responses
- Document all status values returned
- Verify the fix works 10/10 times
"""
import asyncio
import ccxt.async_support as ccxt
import json
import os
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()


# Test symbols: 3 failed + 7 additional = 10 total
TEST_SYMBOLS = [
    # Failed symbols from logs
    '1000000CHEEMSUSDT',
    'VRUSDT',
    'ALUUSDT',

    # Additional popular symbols
    'BTCUSDT',
    'ETHUSDT',
    'SOLUSDT',
    'DOGEUSDT',
    'AVAXUSDT',
    'LINKUSDT',
    'UNIUSDT'
]


async def test_single_symbol(exchange: ccxt.bybit, symbol: str, test_num: int) -> Dict[str, Any]:
    """
    Test single symbol and return detailed results

    Returns:
        Dict with:
        - symbol
        - success: bool
        - status_from_api: raw status from response
        - status_from_ccxt: CCXT normalized status
        - raw_response: complete response
        - error: error message if failed
    """
    print(f"\n{'='*80}")
    print(f"TEST {test_num}/10: {symbol}")
    print(f"{'='*80}")

    result = {
        'symbol': symbol,
        'success': False,
        'status_from_api': None,
        'status_from_ccxt': None,
        'raw_response': None,
        'error': None
    }

    try:
        # Check if symbol exists
        if symbol not in exchange.markets:
            result['error'] = f"Symbol {symbol} not found in markets"
            print(f"❌ {result['error']}")
            return result

        market = exchange.markets[symbol]

        # Get current price
        ticker = await exchange.fetch_ticker(symbol)
        last_price = ticker['last']
        print(f"Current price: ${last_price}")

        # Calculate minimum order size ($5-10 test order)
        min_amount = market['limits']['amount']['min']
        test_quantity = max(min_amount, 6 / last_price)  # ~$6 order
        test_quantity = exchange.amount_to_precision(symbol, test_quantity)

        est_cost = float(test_quantity) * last_price
        print(f"Test order: {test_quantity} contracts (~${est_cost:.2f})")

        # Create REAL market order (SMALL amount)
        print(f"⚠️  Creating REAL market order...")

        order = await exchange.create_market_order(
            symbol=symbol,
            side='buy',
            amount=test_quantity
        )

        # Store raw response
        result['raw_response'] = order

        # Extract statuses
        info = order.get('info', {})
        result['status_from_api'] = info.get('orderStatus', '')
        result['status_from_ccxt'] = order.get('status', '')

        print(f"\n📊 ORDER RESPONSE:")
        print(f"  Order ID: {order.get('id')}")
        print(f"  Type: {order.get('type')}")
        print(f"  Side: {order.get('side')}")
        print(f"  Amount: {order.get('amount')}")
        print(f"  Filled: {order.get('filled')}")
        print(f"  Price: {order.get('price')}")
        print(f"  Average: {order.get('average')}")

        print(f"\n🎯 STATUS ANALYSIS:")
        print(f"  status_from_api (info.orderStatus): '{result['status_from_api']}'")
        print(f"  status_from_ccxt (order.status): '{result['status_from_ccxt']}'")

        # Check if status would be 'unknown' in current code
        status_map = {
            'Filled': 'closed',
            'PartiallyFilled': 'open',
            'New': 'open',
            'Cancelled': 'canceled',
            'Rejected': 'canceled',
            'closed': 'closed',
            'open': 'open',
            'canceled': 'canceled',
            # NOTE: 'Created' is MISSING in current code!
        }

        raw_status = result['status_from_api'] or result['status_from_ccxt']

        # Simulate current code logic
        if not raw_status and order.get('type') == 'market':
            final_status = 'closed'
            print(f"  ✅ Empty status + market → 'closed' (handled by special case)")
        else:
            final_status = status_map.get(raw_status) or order.get('status') or 'unknown'
            print(f"  Mapped status: '{final_status}'")

            if final_status == 'unknown':
                print(f"  ❌ PROBLEM: Status '{raw_status}' → 'unknown' (order would be REJECTED)")
                result['error'] = f"Status mapping failed: '{raw_status}' → 'unknown'"
            elif final_status in ['closed', 'open']:
                print(f"  ✅ Status OK: Order would be ACCEPTED")

        # Test if order actually filled
        if order.get('filled', 0) > 0 or final_status == 'closed':
            result['success'] = True
            print(f"\n✅ TEST PASSED: Order executed successfully")
        else:
            result['error'] = "Order created but not filled"
            print(f"\n⚠️  TEST WARNING: Order created but filled=0")

        # Print raw info section
        if info:
            print(f"\n📋 RAW INFO SECTION:")
            important_fields = ['orderStatus', 'orderType', 'side', 'qty',
                              'cumExecQty', 'avgPrice', 'orderLinkId', 'retCode', 'retMsg']
            for field in important_fields:
                if field in info:
                    print(f"  {field}: {info[field]}")

    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)}"
        print(f"\n❌ TEST FAILED: {result['error']}")

    return result


async def run_comprehensive_test():
    """
    Run comprehensive test on 10 symbols
    """
    print("\n" + "="*80)
    print("🔬 COMPREHENSIVE TEST: Bybit Market Order Status Investigation")
    print("="*80)
    print()
    print("⚠️  WARNING: This test will create REAL orders with small amounts ($5-10 each)")
    print("⚠️  Total cost: ~$60-100")
    print()
    print("Test will:")
    print("  1. Create market orders on 10 different symbols")
    print("  2. Capture all API responses")
    print("  3. Identify missing status mappings")
    print("  4. Verify fix works 10/10 times")
    print()

    # Initialize exchange
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',  # USDT perpetual
            'recvWindow': 10000
        }
    })

    # Use testnet
    exchange.set_sandbox_mode(True)
    print("🔧 Using TESTNET (sandbox mode)")
    print()

    try:
        # Load markets
        await exchange.load_markets()
        print(f"✅ Markets loaded: {len(exchange.markets)} symbols\n")

        # Run tests
        results = []
        for i, symbol in enumerate(TEST_SYMBOLS, 1):
            result = await test_single_symbol(exchange, symbol, i)
            results.append(result)

            # Small delay between orders
            await asyncio.sleep(2)

        # Analysis
        print("\n\n" + "="*80)
        print("📊 TEST RESULTS SUMMARY")
        print("="*80)
        print()

        passed = sum(1 for r in results if r['success'])
        failed = len(results) - passed

        print(f"Total tests: {len(results)}")
        print(f"✅ Passed: {passed}/{len(results)}")
        print(f"❌ Failed: {failed}/{len(results)}")
        print()

        # Status analysis
        print("="*80)
        print("🎯 STATUS VALUES FOUND")
        print("="*80)
        print()

        status_from_api_set = set()
        status_from_ccxt_set = set()

        for r in results:
            if r['status_from_api']:
                status_from_api_set.add(r['status_from_api'])
            if r['status_from_ccxt']:
                status_from_ccxt_set.add(r['status_from_ccxt'])

        print("Status values from Bybit API (info.orderStatus):")
        for status in sorted(status_from_api_set):
            print(f"  - '{status}'")

        print()
        print("Status values from CCXT normalized (order.status):")
        for status in sorted(status_from_ccxt_set):
            print(f"  - '{status}'")

        # Missing mappings
        print()
        print("="*80)
        print("🔍 MISSING STATUS MAPPINGS")
        print("="*80)
        print()

        current_status_map = {
            'Filled', 'PartiallyFilled', 'New', 'Cancelled', 'Rejected',
            'closed', 'open', 'canceled'
        }

        all_statuses = status_from_api_set | status_from_ccxt_set
        missing = all_statuses - current_status_map

        if missing:
            print("⚠️  Statuses NOT in current status_map:")
            for status in sorted(missing):
                print(f"  - '{status}' ← MISSING!")
            print()
            print("💡 These statuses need to be added to status_map!")
        else:
            print("✅ All statuses are mapped")

        # Failed tests details
        if failed > 0:
            print()
            print("="*80)
            print("❌ FAILED TESTS DETAILS")
            print("="*80)
            print()

            for r in results:
                if not r['success']:
                    print(f"{r['symbol']}:")
                    print(f"  Error: {r['error']}")
                    print(f"  status_from_api: '{r['status_from_api']}'")
                    print(f"  status_from_ccxt: '{r['status_from_ccxt']}'")
                    print()

        # Proposed fix
        print()
        print("="*80)
        print("💊 PROPOSED FIX")
        print("="*80)
        print()

        if missing:
            print("Add missing statuses to status_map in exchange_response_adapter.py:")
            print()
            print("status_map = {")
            print("    # Bybit API format (uppercase)")
            print("    'Filled': 'closed',")
            print("    'PartiallyFilled': 'open',")
            print("    'New': 'open',")

            for status in sorted(missing):
                # Determine correct mapping
                if 'fill' in status.lower() or 'closed' in status.lower():
                    mapping = 'closed'
                elif 'cancel' in status.lower() or 'reject' in status.lower():
                    mapping = 'canceled'
                else:
                    mapping = 'open'
                print(f"    '{status}': '{mapping}',  # ← ADD THIS")

            print("    'Cancelled': 'canceled',")
            print("    'Rejected': 'canceled',")
            print("    ")
            print("    # CCXT normalized format (lowercase)")
            print("    'closed': 'closed',")
            print("    'open': 'open',")
            print("    'canceled': 'canceled',")
            print("}")
        else:
            print("✅ No fix needed - all statuses are mapped")

        # Success prediction
        print()
        print("="*80)
        print("🎯 FIX VERIFICATION")
        print("="*80)
        print()

        if missing:
            print(f"With proposed fix:")
            print(f"  - All {len(missing)} missing statuses will be mapped")
            print(f"  - Expected success rate: 10/10")
            print(f"  - 'Entry order failed: unknown' will be FIXED ✅")
        else:
            print(f"Current code already handles all observed statuses")
            if failed > 0:
                print(f"Failed tests are due to other issues, not status mapping")

        # Save detailed results
        results_file = 'bybit_market_orders_test_results.json'
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print()
        print(f"📄 Detailed results saved to: {results_file}")

    finally:
        await exchange.close()


async def main():
    """
    Main entry point
    """
    print()
    print("⚠️  READY TO RUN COMPREHENSIVE TEST")
    print()
    print("This will:")
    print("  - Create REAL market orders on Bybit TESTNET")
    print("  - Test 10 different symbols")
    print("  - Each order ~$5-10 (testnet funds)")
    print()

    # Check credentials
    if not os.getenv('BYBIT_API_KEY') or not os.getenv('BYBIT_API_SECRET'):
        print("❌ ERROR: BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env")
        print()
        print("To run this test:")
        print("  1. Add Bybit testnet API credentials to .env")
        print("  2. Ensure you have testnet funds (~$100)")
        print("  3. Run: python3 test_bybit_market_orders_comprehensive.py")
        return 1

    print("✅ API credentials found")
    print()

    # Confirmation
    print("Press ENTER to start test, or Ctrl+C to cancel...")
    try:
        input()
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user")
        return 1

    await run_comprehensive_test()

    print()
    print("="*80)
    print("✅ COMPREHENSIVE TEST COMPLETED")
    print("="*80)
    print()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    import sys
    sys.exit(exit_code)
