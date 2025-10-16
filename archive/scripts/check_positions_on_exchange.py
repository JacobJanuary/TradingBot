#!/usr/bin/env python3
"""Check if positions from wave exist on exchanges"""
import asyncio
import sys
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from exchange.binance_exchange import BinanceExchange
from exchange.bybit_exchange import BybitExchange
from config.settings import Config

async def check_positions():
    """Check positions on exchanges"""
    cfg = Config()

    # Get Binance config
    binance_cfg = None
    bybit_cfg = None
    for ex in cfg.exchanges:
        if ex.name == 'binance':
            binance_cfg = ex
        elif ex.name == 'bybit':
            bybit_cfg = ex

    results = []

    # Check Binance
    if binance_cfg:
        print("🔍 Checking Binance positions...")
        exchange = BinanceExchange(binance_cfg)
        await exchange.initialize()

        positions = await exchange.get_positions()

        print(f"📊 Total Binance positions: {len(positions)}")

        symbols = ['VANAUSDT', 'ROSEUSDT', 'LQTYUSDT', 'ACEUSDT', 'MUSDT']
        for symbol in symbols:
            pos = next((p for p in positions if p.get('symbol') == symbol), None)
            if pos:
                size = pos.get('contracts', 0)
                side = pos.get('side', 'N/A')
                print(f"  ✅ {symbol}: size={size}, side={side}")
                results.append(f"{symbol} exists on Binance")
            else:
                print(f"  ❌ {symbol}: NOT FOUND")

        await exchange.close()

    # Check Bybit
    if bybit_cfg:
        print("\n🔍 Checking Bybit positions...")
        exchange = BybitExchange(bybit_cfg)
        await exchange.initialize()

        positions = await exchange.get_positions()

        print(f"📊 Total Bybit positions: {len(positions)}")

        symbols = ['ELXUSDT']
        for symbol in symbols:
            pos = next((p for p in positions if p.get('symbol') == symbol), None)
            if pos:
                size = pos.get('contracts', 0)
                side = pos.get('side', 'N/A')
                print(f"  ✅ {symbol}: size={size}, side={side}")
                results.append(f"{symbol} exists on Bybit")
            else:
                print(f"  ❌ {symbol}: NOT FOUND")

        await exchange.close()

    return results

if __name__ == "__main__":
    asyncio.run(check_positions())
