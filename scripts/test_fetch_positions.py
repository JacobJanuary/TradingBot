#!/usr/bin/env python3
"""
Test script to check if fetch_positions returns correct data for specific symbols
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange_manager import ExchangeManager
from config.settings import config as settings


async def test_fetch_positions():
    """Test fetch_positions for symbols with errors"""

    test_symbols = ['PIPPINUSDT', 'ORDERUSDT', 'SSVUSDT']

    print("=" * 80)
    print("TESTING fetch_positions() FOR SYMBOLS WITH position_not_found ERRORS")
    print("=" * 80)

    exchange_mgr = ExchangeManager(settings)

    # Initialize exchanges
    binance_config = next((ex for ex in settings.EXCHANGES if ex['name'] == 'binance'), None)
    if not binance_config:
        print("❌ Binance config not found")
        return

    await exchange_mgr.initialize_exchange(binance_config)
    binance_exchange = exchange_mgr.get_exchange('binance')

    print(f"\n🔍 Testing fetch_positions() for {len(test_symbols)} symbols")
    print("-" * 80)

    for symbol in test_symbols:
        print(f"\n📊 Symbol: {symbol}")
        print(f"   Calling: fetch_positions(['{symbol}'])")

        try:
            positions = await binance_exchange.fetch_positions([symbol])

            print(f"   Result: {len(positions)} position(s) returned")

            if not positions:
                print(f"   ⚠️  EMPTY RESULT - No positions found!")
                continue

            for pos in positions:
                contracts = float(pos.get('contracts', 0))
                size = float(pos.get('size', 0))
                print(f"   Position: symbol={pos.get('symbol')}, contracts={contracts}, size={size}")

                if contracts > 0 or size > 0:
                    print(f"   ✅ Position FOUND with size > 0")
                else:
                    print(f"   ⚠️  Position found but contracts=0 and size=0")

        except Exception as e:
            print(f"   ❌ ERROR: {e}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(test_fetch_positions())
