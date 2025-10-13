#!/usr/bin/env python3
"""Проверка баланса на testnet и production"""

import asyncio
import ccxt.async_support as ccxt
from config.settings import Config

async def check_balance():
    config = Config()
    bybit_config = config.exchanges.get('bybit')

    if not bybit_config:
        print("❌ Bybit not configured")
        return

    print(f"Configured testnet: {bybit_config.testnet}")
    print()

    # Check configured instance
    exchange = ccxt.bybit({
        'apiKey': bybit_config.api_key,
        'secret': bybit_config.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': bybit_config.testnet
        }
    })

    try:
        balance = await exchange.fetch_balance()
        usdt = balance.get('USDT', {})

        print(f"Balance on {'TESTNET' if bybit_config.testnet else 'PRODUCTION'}:")
        print(f"  Free: {usdt.get('free', 0)}")
        print(f"  Used: {usdt.get('used', 0)}")
        print(f"  Total: {usdt.get('total', 0)}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(check_balance())
