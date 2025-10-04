#!/usr/bin/env python3
"""Расследование удаления позиций - проверка состояния на биржах"""

import asyncio
import ccxt.async_support as ccxt
import os
from database.repository import Repository
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

async def check_exchange_positions():
    """Проверяем реальное состояние позиций на биржах"""

    print("=" * 80)
    print("INVESTIGATION: POSITION DELETION ISSUE")
    print("=" * 80)

    # Initialize exchanges
    binance = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    })

    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'options': {
            'testnet': True,
            'defaultType': 'linear'
        }
    })

    try:
        # Check Binance positions
        print("\n📊 BINANCE POSITIONS (via API):")
        print("-" * 80)
        binance_positions = await binance.fetch_positions()
        binance_open = [p for p in binance_positions if float(p.get('contracts', 0)) != 0]

        if binance_open:
            for pos in binance_open:
                print(f"  ✅ {pos['symbol']}: {pos['side']} {pos['contracts']} @ {pos['entryPrice']}")
                print(f"     Info: {pos.get('info', {})}")
        else:
            print("  ❌ NO OPEN POSITIONS FOUND")

        # Check Bybit positions
        print("\n📊 BYBIT POSITIONS (via API):")
        print("-" * 80)
        bybit_positions = await bybit.fetch_positions()
        bybit_open = [p for p in bybit_positions if float(p.get('contracts', 0)) != 0]

        if bybit_open:
            for pos in bybit_open:
                print(f"  ✅ {pos['symbol']}: {pos['side']} {pos['contracts']} @ {pos['entryPrice']}")
                print(f"     Info: {pos.get('info', {})}")
        else:
            print("  ❌ NO OPEN POSITIONS FOUND")

        # Check database
        print("\n📊 DATABASE POSITIONS:")
        print("-" * 80)

        repo = Repository()
        await repo.initialize()

        db_positions = await repo.get_open_positions()

        if db_positions:
            for pos in db_positions:
                print(f"  DB: {pos.symbol} ({pos.exchange}): {pos.side} {pos.quantity}")
                print(f"      ID: {pos.id}, Status: {pos.status}")
        else:
            print("  ❌ NO POSITIONS IN DATABASE")

        await repo.close()

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print("=" * 80)
        print(f"Binance API: {len(binance_open)} open positions")
        print(f"Bybit API: {len(bybit_open)} open positions")
        print(f"Database: {len(db_positions) if db_positions else 0} positions")

        if binance_open or bybit_open:
            print("\n⚠️ POSITIONS EXIST ON EXCHANGES!")
            print("\nBinance positions on exchange:")
            for p in binance_open:
                print(f"  - {p['symbol']}: {p['side']} {p['contracts']}")
            print("\nBybit positions on exchange:")
            for p in bybit_open:
                print(f"  - {p['symbol']}: {p['side']} {p['contracts']}")

    finally:
        await binance.close()
        await bybit.close()

if __name__ == "__main__":
    asyncio.run(check_exchange_positions())
