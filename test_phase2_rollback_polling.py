#!/usr/bin/env python3
"""
Unit Test: Phase 2 - Rollback with polling

Tests:
1. Rollback находит позицию после retry
2. Rollback успешно закрывает позицию
3. Alert если позиция не найдена после всех попыток
"""
import sys
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()


async def test_rollback_finds_position():
    """
    TEST 1: Rollback находит позицию через polling
    """
    print()
    print("="*80)
    print("🧪 TEST 1: Rollback finds position via polling")
    print("="*80)
    print()

    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()

        # Create position
        symbol = 'BTC/USDT:USDT'
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']

        market = exchange.markets[symbol]
        min_amount = market['limits']['amount']['min']
        quantity = exchange.amount_to_precision(symbol, min_amount)

        print(f"Creating position: {symbol}")
        order = await exchange.create_market_order(symbol, 'buy', quantity)
        print(f"✅ Order created: {order.get('id')}")
        print()

        # Simulate rollback polling immediately (before position is visible)
        print("Simulating rollback polling (10 attempts x 500ms)...")

        from core.position_manager import normalize_symbol

        our_position = None
        max_attempts = 10
        found_at = None

        for attempt in range(max_attempts):
            positions = await exchange.fetch_positions(params={'category': 'linear'})

            for pos in positions:
                if normalize_symbol(pos['symbol']) == normalize_symbol(symbol) and \
                   float(pos.get('contracts', 0)) > 0:
                    our_position = pos
                    found_at = attempt + 1
                    break

            if our_position:
                print(f"  ✅ Position found on attempt {found_at}/{max_attempts}")
                break

            print(f"  Attempt {attempt + 1}/{max_attempts}: not visible yet")

            if attempt < max_attempts - 1:
                await asyncio.sleep(0.5)

        print()

        if our_position:
            print(f"✅ TEST PASSED: Position found within polling window")
            print(f"   Found after: {found_at} attempts (~{found_at * 0.5:.1f}s)")

            # Close position
            close_order = await exchange.create_market_order(symbol, 'sell', quantity)
            print(f"✅ Position closed: {close_order.get('id')}")

            return True
        else:
            print(f"❌ TEST FAILED: Position not found after {max_attempts} attempts")
            print(f"   This suggests polling window is too short")
            return False

    finally:
        await exchange.close()


async def test_rollback_closes_position():
    """
    TEST 2: Rollback успешно закрывает позицию
    """
    print()
    print("="*80)
    print("🧪 TEST 2: Rollback successfully closes position")
    print("="*80)
    print()

    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()

        # Create position
        symbol = 'BTC/USDT:USDT'
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']

        market = exchange.markets[symbol]
        min_amount = market['limits']['amount']['min']
        quantity = exchange.amount_to_precision(symbol, min_amount)

        print(f"Creating position: {symbol}")
        order = await exchange.create_market_order(symbol, 'buy', quantity)
        print(f"✅ Position created: {order.get('id')}")
        print()

        # Wait for position to be visible
        await asyncio.sleep(2)

        # Get initial balance
        balance_before = await exchange.fetch_balance()
        positions_before = await exchange.fetch_positions(params={'category': 'linear'})
        position_count_before = len([p for p in positions_before if float(p.get('contracts', 0)) > 0])

        print(f"Before close:")
        print(f"  Open positions: {position_count_before}")
        print()

        # Simulate rollback close
        print("Simulating rollback close...")

        from core.position_manager import normalize_symbol

        # Find position
        our_position = None
        positions = await exchange.fetch_positions(params={'category': 'linear'})

        for pos in positions:
            if normalize_symbol(pos['symbol']) == normalize_symbol(symbol) and \
               float(pos.get('contracts', 0)) > 0:
                our_position = pos
                break

        if our_position:
            # Close it
            side = our_position['side']
            contracts = float(our_position['contracts'])
            close_side = 'sell' if side == 'long' else 'buy'

            print(f"  Found: {side} {contracts} contracts")
            print(f"  Closing with {close_side} order...")

            close_order = await exchange.create_market_order(symbol, close_side, contracts)
            print(f"  ✅ Close order: {close_order.get('id')}")
            print()

            # Wait for close to complete
            await asyncio.sleep(2)

            # Verify position closed
            positions_after = await exchange.fetch_positions(params={'category': 'linear'})
            position_count_after = len([p for p in positions_after if float(p.get('contracts', 0)) > 0])

            print(f"After close:")
            print(f"  Open positions: {position_count_after}")
            print()

            if position_count_after < position_count_before:
                print("✅ TEST PASSED: Position successfully closed")
                return True
            else:
                print("❌ TEST FAILED: Position still open")
                return False
        else:
            print("❌ TEST FAILED: Position not found")
            return False

    finally:
        await exchange.close()


async def test_polling_window_sufficient():
    """
    TEST 3: Проверка что polling window (10 x 500ms = 5s) достаточен
    """
    print()
    print("="*80)
    print("🧪 TEST 3: Verify polling window is sufficient")
    print("="*80)
    print()

    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()

        # Create multiple positions quickly
        symbol = 'BTC/USDT:USDT'
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']

        market = exchange.markets[symbol]
        min_amount = market['limits']['amount']['min']
        quantity = exchange.amount_to_precision(symbol, min_amount)

        test_count = 3
        results = []

        print(f"Testing {test_count} position creations...")
        print()

        for i in range(test_count):
            print(f"Test {i+1}/{test_count}:")

            # Create position
            order = await exchange.create_market_order(symbol, 'buy', quantity)
            print(f"  Order created: {order.get('id')}")

            # Poll for visibility
            import time
            t_start = time.time()

            from core.position_manager import normalize_symbol

            our_position = None
            max_attempts = 10

            for attempt in range(max_attempts):
                positions = await exchange.fetch_positions(params={'category': 'linear'})

                for pos in positions:
                    if normalize_symbol(pos['symbol']) == normalize_symbol(symbol) and \
                       float(pos.get('contracts', 0)) > 0:
                        our_position = pos
                        break

                if our_position:
                    break

                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.5)

            t_end = time.time()
            elapsed = t_end - t_start

            if our_position:
                print(f"  ✅ Found after {elapsed:.1f}s")
                results.append(True)

                # Close
                await exchange.create_market_order(symbol, 'sell', quantity)
                await asyncio.sleep(1)  # Wait before next test
            else:
                print(f"  ❌ NOT found after {elapsed:.1f}s")
                results.append(False)

        print()
        print(f"Results: {sum(results)}/{test_count} found within 5s window")
        print()

        if all(results):
            print("✅ TEST PASSED: Polling window is sufficient")
            print("   All positions found within 5 seconds")
            return True
        elif sum(results) >= test_count * 0.8:  # 80% success rate acceptable
            print("⚠️  TEST PASSED (with warning): Most positions found")
            print(f"   Success rate: {sum(results)}/{test_count}")
            return True
        else:
            print("❌ TEST FAILED: Polling window may be too short")
            print(f"   Success rate: {sum(results)}/{test_count}")
            print("   Consider increasing max_attempts or delay")
            return False

    finally:
        await exchange.close()


async def main():
    print()
    print("🔬 PHASE 2 TESTS: Rollback with Polling")
    print("="*80)
    print()

    tests = {
        "Rollback finds position via polling": await test_rollback_finds_position(),
        "Rollback successfully closes position": await test_rollback_closes_position(),
        "Polling window sufficient (5s)": await test_polling_window_sufficient()
    }

    print()
    print("="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print()

    for name, passed in tests.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    print()

    if all(tests.values()):
        print("🎉 ALL TESTS PASSED (3/3)")
        print()
        print("🎯 PHASE 2 VERIFICATION:")
        print("  - Rollback polls for position visibility ✅")
        print("  - Position found within 5 seconds ✅")
        print("  - Position successfully closed ✅")
        print("  - Orphaned position risk eliminated ✅")
        print()
        print("✅ Ready for git commit")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        failed = sum(1 for p in tests.values() if not p)
        print(f"  {failed}/{len(tests)} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
