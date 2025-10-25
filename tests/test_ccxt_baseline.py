#!/usr/bin/env python3
"""
Baseline test for CCXT behavior
Run BEFORE upgrade to document current behavior
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import ccxt.async_support as ccxt
from config.settings import config

async def test_ccxt_version():
    print(f"CCXT Version: {ccxt.__version__}")

async def test_bybit_balance():
    """Test Bybit balance fetch"""
    bybit_config = config.get_exchange_config('bybit')
    exchange = ccxt.bybit({
        'apiKey': bybit_config.api_key,
        'secret': bybit_config.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED',
            'brokerId': ''
        }
    })

    try:
        # Test 1: fetch_balance
        balance = await exchange.fetch_balance()
        free_balance = balance.get('USDT', {}).get('free', 0) or 0
        print(f"✅ fetch_balance: USDT free = ${free_balance:.2f}")

        # Test 2: Direct API call
        response = await exchange.privateGetV5AccountWalletBalance({
            'accountType': 'UNIFIED',
            'coin': 'USDT'
        })
        result = response.get('result', {})
        accounts = result.get('list', [])
        if accounts:
            coins = accounts[0].get('coin', [])
            for coin in coins:
                if coin.get('coin') == 'USDT':
                    wallet = float(coin.get('walletBalance', 0))
                    locked = float(coin.get('locked', 0))
                    print(f"✅ Direct API: USDT walletBalance = ${wallet:.2f}, locked = ${locked:.2f}")

        # Test 3: Symbol format
        await exchange.load_markets()
        if 'BLAST/USDT:USDT' in exchange.markets:
            print(f"✅ Symbol format: 'BLAST/USDT:USDT' exists")
        else:
            print(f"❌ Symbol format: 'BLAST/USDT:USDT' NOT found")

    finally:
        await exchange.close()

async def test_binance_precision():
    """Test Binance precision methods"""
    binance_config = config.get_exchange_config('binance')
    exchange = ccxt.binance({
        'apiKey': binance_config.api_key,
        'secret': binance_config.api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    try:
        await exchange.load_markets()

        # Test precision
        price = exchange.price_to_precision('BTC/USDT', 50123.456789)
        amount = exchange.amount_to_precision('BTC/USDT', 0.123456789)

        print(f"✅ Binance precision: price={price}, amount={amount}")

    finally:
        await exchange.close()

async def main():
    print("=" * 60)
    print("CCXT BASELINE TEST")
    print("=" * 60)

    await test_ccxt_version()
    await test_bybit_balance()
    await test_binance_precision()

    print("=" * 60)
    print("Baseline complete. Save this output for comparison.")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(main())
