#!/usr/bin/env python3
"""
Check Bybit real balance
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import load_config
from core.exchange_manager import ExchangeManager

async def main():
    # Load config
    config = load_config()

    # Get Bybit config
    bybit_config = None
    for exch in config.exchanges:
        if exch['name'].lower() == 'bybit':
            bybit_config = exch
            break

    if not bybit_config:
        print("❌ Bybit exchange not found in config!")
        return

    # Create Bybit exchange
    print(f"🔗 Connecting to Bybit...")
    bybit = ExchangeManager('bybit', bybit_config)

    try:
        # Fetch balance
        print(f"\n📊 Fetching balance...")
        balance = await bybit.exchange.fetch_balance()

        usdt_balance = balance.get('USDT', {})
        free = float(usdt_balance.get('free', 0))
        used = float(usdt_balance.get('used', 0))
        total = float(usdt_balance.get('total', 0))

        print(f"\n💰 Bybit USDT Balance:")
        print(f"   Free:  ${free:.2f}")
        print(f"   Used:  ${used:.2f}")
        print(f"   Total: ${total:.2f}")

        # Fetch positions
        print(f"\n📊 Fetching positions...")
        positions = await bybit.exchange.fetch_positions()
        active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        print(f"\n📊 Bybit Positions:")
        print(f"   Total positions: {len(positions)}")
        print(f"   Active positions: {len(active_positions)}")

        if active_positions:
            print(f"\n   Active positions:")
            for p in active_positions:
                symbol = p.get('symbol')
                contracts = float(p.get('contracts', 0))
                notional = abs(float(p.get('notional', 0)))
                print(f"     - {symbol}: {contracts} contracts, notional=${notional:.2f}")

        # Total notional
        total_notional = sum(abs(float(p.get('notional', 0))) for p in positions if float(p.get('contracts', 0)) > 0)
        print(f"\n   Total notional: ${total_notional:.2f}")

        # Can we open $200 position?
        print(f"\n🔍 Can open $200 position?")
        if free >= 200:
            print(f"   ✅ YES - Free balance: ${free:.2f} >= $200.00")
        else:
            print(f"   ❌ NO - Free balance: ${free:.2f} < $200.00")
            print(f"   ⚠️  Need to transfer ${200 - free:.2f} to Bybit!")

    finally:
        await bybit.exchange.close()
        print(f"\n✅ Done")

if __name__ == '__main__':
    asyncio.run(main())
