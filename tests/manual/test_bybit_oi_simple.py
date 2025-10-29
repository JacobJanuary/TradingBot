#!/usr/bin/env python3
"""
Простой тест для верификации что Bybit OI fix работает.

Дата: 2025-10-29
"""

import asyncio
import ccxt.pro as ccxt

async def test_bybit_oi():
    """Простой тест Bybit OI через ticker."""

    print("=" * 80)
    print("🧪 ПРОСТОЙ ТЕСТ BYBIT OI")
    print("=" * 80)

    # Test symbols
    symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']

    # Create Bybit exchange
    exchange = ccxt.bybit()

    try:
        await exchange.load_markets()

        print("\n📊 Тестирование получения OI через ticker['info']['openInterest']")
        print("=" * 80)

        for symbol in symbols:
            print(f"\n🔍 {symbol}:")

            try:
                ticker = await exchange.fetch_ticker(symbol)
                price = ticker.get('last', 0)

                # Method из фикса: ticker['info']['openInterest']
                oi_contracts = float(ticker.get('info', {}).get('openInterest', 0))
                oi_usd = oi_contracts * price if oi_contracts and price else 0

                print(f"  💰 Price: ${price:,.2f}")
                print(f"  📦 OI (contracts): {oi_contracts:,.2f}")
                print(f"  💵 OI (USD): ${oi_usd:,.0f}")

                if oi_usd >= 1_000_000:
                    print(f"  ✅ OI >= $1M - PASS")
                else:
                    print(f"  ❌ OI < $1M - FAIL")

            except Exception as e:
                print(f"  ❌ Error: {e}")

        print("\n" + "=" * 80)
        print("✅ Тест завершен")
        print("=" * 80)

    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(test_bybit_oi())
