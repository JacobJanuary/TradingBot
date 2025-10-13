#!/usr/bin/env python3
"""
AUTO-RUN VERSION: Bybit Market Order Status Investigation
Runs without user confirmation for automated testing
"""
import asyncio
import ccxt.async_support as ccxt
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Test symbols: 3 failed + 7 additional = 10 total
# Format: /USDT:USDT for Bybit linear perpetuals
TEST_SYMBOLS = [
    '1000000CHEEMS/USDT:USDT',  # Failed #1
    'VR/USDT:USDT',              # Failed #2
    'ALU/USDT:USDT',             # Failed #3
    'BTC/USDT:USDT',
    'ETH/USDT:USDT',
    'SOL/USDT:USDT',
    'DOGE/USDT:USDT',
    'AVAX/USDT:USDT',
    'LINK/USDT:USDT',
    'UNI/USDT:USDT'
]


async def test_single_symbol(exchange: ccxt.bybit, symbol: str, test_num: int):
    """Test single symbol and return results"""
    print(f"\n{'='*80}")
    print(f"TEST {test_num}/10: {symbol}")
    print(f"{'='*80}")

    result = {
        'symbol': symbol,
        'success': False,
        'status_from_api': None,
        'status_from_ccxt': None,
        'error': None
    }

    try:
        if symbol not in exchange.markets:
            result['error'] = f"Symbol not found"
            print(f"❌ {symbol} not in markets")
            return result

        # Get price and create small test order
        ticker = await exchange.fetch_ticker(symbol)
        last_price = ticker['last']
        print(f"Price: ${last_price}")

        market = exchange.markets[symbol]
        min_amount = market['limits']['amount']['min']
        test_quantity = max(min_amount, 6 / last_price)
        test_quantity = exchange.amount_to_precision(symbol, test_quantity)

        print(f"Creating market buy order: {test_quantity} contracts...")

        # Create market order
        order = await exchange.create_market_order(
            symbol=symbol,
            side='buy',
            amount=test_quantity
        )

        # Extract statuses
        info = order.get('info', {})
        result['status_from_api'] = info.get('orderStatus', '')
        result['status_from_ccxt'] = order.get('status', '')

        print(f"✅ Order created:")
        print(f"  ID: {order.get('id')}")
        print(f"  Status (API): '{result['status_from_api']}'")
        print(f"  Status (CCXT): '{result['status_from_ccxt']}'")
        print(f"  Filled: {order.get('filled')}/{order.get('amount')}")

        # Check if status would map to 'unknown'
        status_map = {
            'Filled': 'closed',
            'PartiallyFilled': 'open',
            'New': 'open',
            'Cancelled': 'canceled',
            'Rejected': 'canceled',
            'closed': 'closed',
            'open': 'open',
            'canceled': 'canceled',
        }

        raw_status = result['status_from_api'] or result['status_from_ccxt']

        if not raw_status and order.get('type') == 'market':
            final_status = 'closed'
            print(f"  → Mapped to: 'closed' (empty status special case)")
        else:
            final_status = status_map.get(raw_status, 'unknown')
            print(f"  → Mapped to: '{final_status}'")

            if final_status == 'unknown':
                print(f"  ⚠️  PROBLEM: '{raw_status}' not in status_map → 'unknown'")
                result['error'] = f"Status '{raw_status}' → 'unknown'"

        result['success'] = final_status != 'unknown'

    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)[:100]}"
        print(f"❌ Error: {result['error']}")

    return result


async def run_test():
    """Run test on all symbols"""
    print("\n" + "="*80)
    print("🔬 BYBIT MARKET ORDER STATUS TEST")
    print("="*80)
    print("Using: TESTNET (sandbox mode)")
    print()

    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',
            'recvWindow': 10000
        }
    })

    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()
        print(f"✅ Markets loaded: {len(exchange.markets)} symbols\n")

        results = []
        for i, symbol in enumerate(TEST_SYMBOLS, 1):
            result = await test_single_symbol(exchange, symbol, i)
            results.append(result)
            await asyncio.sleep(1)  # Rate limit

        # Summary
        print("\n\n" + "="*80)
        print("📊 RESULTS SUMMARY")
        print("="*80)
        print()

        passed = sum(1 for r in results if r['success'])
        failed = len(results) - passed

        print(f"Tests: {len(results)}")
        print(f"✅ Passed: {passed}/{len(results)}")
        print(f"❌ Failed: {failed}/{len(results)}")
        print()

        # Collect all statuses
        all_api_statuses = set()
        all_ccxt_statuses = set()

        for r in results:
            if r['status_from_api']:
                all_api_statuses.add(r['status_from_api'])
            if r['status_from_ccxt']:
                all_ccxt_statuses.add(r['status_from_ccxt'])

        print("="*80)
        print("🎯 FOUND STATUS VALUES")
        print("="*80)
        print()
        print("From Bybit API (info.orderStatus):")
        for s in sorted(all_api_statuses):
            print(f"  - '{s}'")

        print()
        print("From CCXT normalized (order.status):")
        for s in sorted(all_ccxt_statuses):
            print(f"  - '{s}'")

        # Check missing
        print()
        print("="*80)
        print("🔍 MISSING FROM status_map")
        print("="*80)
        print()

        current_map = {
            'Filled', 'PartiallyFilled', 'New', 'Cancelled', 'Rejected',
            'closed', 'open', 'canceled'
        }

        all_statuses = all_api_statuses | all_ccxt_statuses
        missing = all_statuses - current_map

        if missing:
            print("⚠️  These statuses are NOT mapped:")
            for s in sorted(missing):
                print(f"  - '{s}' ← ADD TO status_map")

            print()
            print("💊 PROPOSED FIX:")
            print()
            for s in sorted(missing):
                # Determine mapping
                if any(x in s.lower() for x in ['fill', 'closed', 'trigger']):
                    mapping = 'closed'
                elif any(x in s.lower() for x in ['cancel', 'reject']):
                    mapping = 'canceled'
                else:
                    mapping = 'open'
                print(f"  '{s}': '{mapping}',  # Add to status_map")
        else:
            print("✅ All statuses are mapped")

        # Failed details
        if failed > 0:
            print()
            print("="*80)
            print("❌ FAILED TESTS")
            print("="*80)
            print()
            for r in results:
                if not r['success']:
                    print(f"{r['symbol']}: {r['error']}")
                    print(f"  API status: '{r['status_from_api']}'")
                    print(f"  CCXT status: '{r['status_from_ccxt']}'")

        # Save results
        with open('bybit_test_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print()
        print("📄 Saved to: bybit_test_results.json")

        print()
        print("="*80)
        print(f"✅ TEST COMPLETED: {passed}/10 passed")
        print("="*80)

        return 0 if passed == len(results) else 1

    finally:
        await exchange.close()


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(run_test())
    sys.exit(exit_code)
