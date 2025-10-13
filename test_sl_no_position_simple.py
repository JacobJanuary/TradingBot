#!/usr/bin/env python3
"""
Simple test: Can we set SL without position?
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()


async def main():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()

        # Check all positions
        print("Current positions:")
        positions = await exchange.fetch_positions(params={'category': 'linear'})
        open_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        for pos in open_positions:
            print(f"  {pos['symbol']}: {pos['side']} {pos['contracts']}")

        if not open_positions:
            print("  (none)")

        print()

        # Pick a symbol with NO position
        # Avoid symbols in open_positions
        test_symbol = 'ADAUSDT'  # Cardano
        has_position = any(p['symbol'].replace('/', '').replace(':USDT', '') == test_symbol
                          for p in open_positions)

        if has_position:
            print(f"⚠️  {test_symbol} has position, trying different symbol")
            test_symbol = 'DOTUSDT'  # Polkadot

        print(f"Test symbol: {test_symbol} (no position)")
        print()

        # Try to set SL
        print("Attempting to set SL without position...")

        params = {
            'category': 'linear',
            'symbol': test_symbol,
            'stopLoss': '1.00',
            'positionIdx': 0,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        result = await exchange.private_post_v5_position_trading_stop(params)

        ret_code = int(result.get('retCode', 1))
        ret_msg = result.get('retMsg', '')

        print(f"Result:")
        print(f"  retCode: {ret_code}")
        print(f"  retMsg: {ret_msg}")
        print()

        if ret_code == 0:
            print("❌ PROBLEM: SL was accepted without position!")
            print("   This means SL might create a standalone order")
            print("   Could potentially consume margin/USDT")
        else:
            print("✅ GOOD: SL was rejected (no position)")
            print("   SL is position-attached")
            print("   No margin consumed")

    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
