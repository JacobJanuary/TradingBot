#!/usr/bin/env python3
"""Close all positions on Binance and Bybit"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import sys

load_dotenv()

async def close_all_positions():
    exchanges = {}

    # Initialize exchanges
    print("Initializing exchanges...")

    # Bybit
    exchanges['bybit'] = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': True
        }
    })

    # Binance
    exchanges['binance'] = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    })

    total_closed = 0

    for exchange_name, exchange in exchanges.items():
        print(f"\n{'='*80}")
        print(f"Closing positions on {exchange_name.upper()}")
        print('='*80)

        try:
            # Get all positions
            positions = await exchange.fetch_positions()
            active_positions = [p for p in positions if p['contracts'] > 0]

            if not active_positions:
                print(f"No active positions on {exchange_name}")
                continue

            print(f"Found {len(active_positions)} active positions")

            for pos in active_positions:
                symbol = pos['symbol']
                side = pos['side']
                amount = pos['contracts']

                # Determine close side (opposite of position side)
                close_side = 'sell' if side == 'long' else 'buy'

                print(f"\nClosing {symbol}:")
                print(f"  Position: {side} {amount}")
                print(f"  Closing with: {close_side} order")

                try:
                    # Create market order to close position
                    if exchange_name == 'bybit':
                        order = await exchange.create_order(
                            symbol=symbol,
                            type='market',
                            side=close_side,
                            amount=amount,
                            params={'reduceOnly': True}
                        )
                    else:  # binance
                        order = await exchange.create_order(
                            symbol=symbol,
                            type='market',
                            side=close_side,
                            amount=amount,
                            params={'reduceOnly': True}
                        )

                    print(f"  ✅ Position closed. Order ID: {order['id']}")
                    total_closed += 1

                    # Small delay between orders
                    await asyncio.sleep(0.5)

                except Exception as e:
                    print(f"  ❌ Failed to close: {e}")

        except Exception as e:
            print(f"Error on {exchange_name}: {e}")
        finally:
            await exchange.close()

    print(f"\n{'='*80}")
    print(f"SUMMARY: Closed {total_closed} positions")
    print('='*80)

    return total_closed

if __name__ == "__main__":
    print("⚠️  WARNING: This will close ALL positions on both exchanges!")
    confirm = input("Are you sure? Type 'YES' to continue: ")

    if confirm != 'YES':
        print("Cancelled")
        sys.exit(0)

    closed = asyncio.run(close_all_positions())
    print(f"\n✅ Done. Closed {closed} positions total.")