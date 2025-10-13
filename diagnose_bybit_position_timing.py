#!/usr/bin/env python3
"""
DIAGNOSTIC: Bybit Position Visibility Timing

Проверяет как быстро позиция становится видна через fetch_positions после create_order
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


async def test_position_timing():
    """
    Test how long it takes for position to be visible after market order
    """
    print()
    print("="*80)
    print("🔬 DIAGNOSTIC: Bybit Position Visibility Timing")
    print("="*80)
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

        # Use a liquid symbol
        symbol = 'BTC/USDT:USDT'

        # Get current price
        ticker = await exchange.fetch_ticker(symbol)
        last_price = ticker['last']

        market = exchange.markets[symbol]
        min_amount = market['limits']['amount']['min']
        test_quantity = exchange.amount_to_precision(symbol, min_amount)

        print(f"Test symbol: {symbol}")
        print(f"Current price: ${last_price}")
        print(f"Order quantity: {test_quantity}")
        print()

        # Create market order
        print("="*80)
        print("STEP 1: Creating market order...")
        print("="*80)

        t0 = datetime.now()
        order = await exchange.create_market_order(
            symbol=symbol,
            side='buy',
            amount=test_quantity
        )
        t1 = datetime.now()

        print(f"✅ Order created: {order.get('id')}")
        print(f"⏱️  Time: {(t1 - t0).total_seconds():.3f}s")
        print()

        # Try to fetch positions immediately
        print("="*80)
        print("STEP 2: Checking position visibility")
        print("="*80)
        print()

        max_attempts = 10
        position_found = False
        found_at_attempt = None

        for attempt in range(1, max_attempts + 1):
            t_check = datetime.now()
            elapsed = (t_check - t0).total_seconds()

            print(f"Attempt {attempt}/{max_attempts} (t+{elapsed:.3f}s):", end=" ")

            positions = await exchange.fetch_positions(params={'category': 'linear'})

            # Check if our position is there
            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    print(f"✅ FOUND!")
                    print(f"  Position: {pos['side']} {pos['contracts']} @ {pos['entryPrice']}")
                    print(f"  Has stopLoss: {pos['info'].get('stopLoss', 'N/A')}")
                    position_found = True
                    found_at_attempt = attempt
                    break

            if position_found:
                break

            print("❌ Not visible yet")

            if attempt < max_attempts:
                await asyncio.sleep(0.5)  # 500ms between checks

        print()
        print("="*80)
        print("STEP 3: Analysis")
        print("="*80)
        print()

        if position_found:
            print(f"✅ Position became visible after {found_at_attempt} attempt(s)")
            print(f"⏱️  Time from order creation: ~{found_at_attempt * 0.5:.1f}s")
            print()
            print("📊 TIMING ANALYSIS:")
            print(f"  - Order creation: immediate")
            print(f"  - Position visibility: {found_at_attempt * 0.5:.1f}s delay")
            print()
            print("⚠️  PROBLEM IDENTIFIED:")
            print("  - atomic_position_manager tries to set SL immediately")
            print("  - Position not yet visible → 'No open position found'")
            print("  - Protection manager waits for position sync → succeeds")
        else:
            print("❌ Position never became visible!")
            print(f"⏱️  Checked for {max_attempts * 0.5:.1f}s")

        # Now try to set stop loss
        if position_found:
            print()
            print("="*80)
            print("STEP 4: Testing Stop Loss placement")
            print("="*80)
            print()

            # Get the actual position
            positions = await exchange.fetch_positions(params={'category': 'linear'})
            our_pos = None
            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    our_pos = pos
                    break

            if our_pos:
                entry_price = float(our_pos['entryPrice'])
                side = our_pos['side']

                # Calculate SL (2% from entry)
                if side == 'long':
                    sl_price = entry_price * 0.98
                else:
                    sl_price = entry_price * 1.02

                sl_price = exchange.price_to_precision(symbol, sl_price)

                print(f"Setting SL: {side} @ entry ${entry_price} → SL ${sl_price}")

                # Format for Bybit API
                bybit_symbol = symbol.replace('/', '').replace(':USDT', '')
                position_idx = int(our_pos['info'].get('positionIdx', 0))

                params = {
                    'category': 'linear',
                    'symbol': bybit_symbol,
                    'stopLoss': str(sl_price),
                    'positionIdx': position_idx,
                    'slTriggerBy': 'LastPrice',
                    'tpslMode': 'Full'
                }

                result = await exchange.private_post_v5_position_trading_stop(params)

                ret_code = int(result.get('retCode', 1))
                ret_msg = result.get('retMsg', 'Unknown')

                if ret_code == 0:
                    print(f"✅ Stop Loss set successfully")
                else:
                    print(f"❌ Stop Loss failed: retCode={ret_code}, msg={ret_msg}")

        # Cleanup - close position
        print()
        print("="*80)
        print("CLEANUP: Closing test position")
        print("="*80)

        if position_found and our_pos:
            close_side = 'sell' if side == 'long' else 'buy'
            close_order = await exchange.create_market_order(
                symbol=symbol,
                side=close_side,
                amount=float(our_pos['contracts'])
            )
            print(f"✅ Position closed: {close_order.get('id')}")

    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(test_position_timing())
