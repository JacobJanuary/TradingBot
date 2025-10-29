#!/usr/bin/env python3
"""
Test Bybit API v5 balance fetching for UNIFIED trading account
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt.async_support as ccxt
import os as os_module

async def main():
    print("=" * 80)
    print("BYBIT API v5 UNIFIED ACCOUNT BALANCE TEST")
    print("=" * 80)

    # Get API keys from environment
    api_key = os_module.getenv('BYBIT_API_KEY')
    api_secret = os_module.getenv('BYBIT_API_SECRET')
    testnet = os_module.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

    if not api_key or not api_secret:
        print("❌ BYBIT_API_KEY or BYBIT_API_SECRET not found in environment!")
        return

    print(f"\n📊 Bybit Configuration:")
    print(f"   Testnet: {testnet}")
    print(f"   API Key (first 4): {api_key[:4]}...")

    # Create Bybit exchange instance
    bybit = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
        }
    })

    # Set testnet if configured
    if testnet:
        bybit.urls['api'] = {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com'
        }
        bybit.hostname = 'api-testnet.bybit.com'
        print(f"   Using TESTNET: {bybit.hostname}")

    try:
        print("\n" + "=" * 80)
        print("TEST 1: Standard CCXT fetchBalance()")
        print("=" * 80)

        balance = await bybit.fetch_balance()
        usdt = balance.get('USDT', {})

        print(f"\n💰 USDT Balance (standard method):")
        print(f"   Free:  {usdt.get('free', 0)}")
        print(f"   Used:  {usdt.get('used', 0)}")
        print(f"   Total: {usdt.get('total', 0)}")

        print("\n" + "=" * 80)
        print("TEST 2: fetchBalance with type='future'")
        print("=" * 80)

        balance2 = await bybit.fetch_balance({'type': 'future'})
        usdt2 = balance2.get('USDT', {})

        print(f"\n💰 USDT Balance (type=future):")
        print(f"   Free:  {usdt2.get('free', 0)}")
        print(f"   Used:  {usdt2.get('used', 0)}")
        print(f"   Total: {usdt2.get('total', 0)}")

        print("\n" + "=" * 80)
        print("TEST 3: Direct API call - GET /v5/account/wallet-balance")
        print("=" * 80)

        # Try direct API call with coin parameter
        try:
            response = await bybit.privateGetV5AccountWalletBalance({
                'accountType': 'UNIFIED',
                'coin': 'USDT'
            })

            print(f"\n📊 Direct API Response:")
            print(f"   retCode: {response.get('retCode')}")
            print(f"   retMsg: {response.get('retMsg')}")

            result = response.get('result', {})
            accounts = result.get('list', [])

            if accounts:
                account = accounts[0]
                print(f"\n💰 Account Info:")
                print(f"   Account Type: {account.get('accountType')}")
                print(f"   Total Equity: {account.get('totalEquity', 0)}")
                print(f"   Total Wallet Balance: {account.get('totalWalletBalance', 0)}")
                print(f"   Total Available Balance: {account.get('totalAvailableBalance', 0)}")

                coins = account.get('coin', [])
                print(f"\n💰 Coins in account ({len(coins)}):")
                for coin_data in coins:
                    coin = coin_data.get('coin')
                    equity = float(coin_data.get('equity', 0))
                    available = float(coin_data.get('availableToWithdraw', 0))
                    wallet_balance = float(coin_data.get('walletBalance', 0))

                    if equity > 0 or available > 0 or wallet_balance > 0:
                        print(f"   {coin}:")
                        print(f"      Wallet Balance: {wallet_balance}")
                        print(f"      Available: {available}")
                        print(f"      Equity: {equity}")
        except Exception as e:
            print(f"❌ Direct API call failed: {e}")

        print("\n" + "=" * 80)
        print("TEST 4: Check account type (unified vs contract)")
        print("=" * 80)

        # Check if unified account is enabled
        try:
            info = await bybit.privateGetV5UserQueryApi()
            print(f"\n📊 Account Info:")
            print(f"   Response: {info}")

            result = info.get('result', {})
            print(f"   Unified Margin Account: {result.get('unifiedMarginStatus', 'unknown')}")
            print(f"   Account Type: {result.get('accountType', 'unknown')}")
        except Exception as e:
            print(f"⚠️  Account info check failed: {e}")

        print("\n" + "=" * 80)
        print("TEST 5: Fetch positions to verify")
        print("=" * 80)

        try:
            positions = await bybit.fetch_positions()
            active = [p for p in positions if float(p.get('contracts', 0)) > 0]

            print(f"\n📊 Positions:")
            print(f"   Total: {len(positions)}")
            print(f"   Active: {len(active)}")

            if active:
                print(f"\n   Active positions:")
                for p in active[:5]:
                    print(f"      {p.get('symbol')}: {p.get('contracts')} contracts")
        except Exception as e:
            print(f"❌ Fetch positions failed: {e}")

    finally:
        await bybit.close()
        print("\n✅ Tests complete")

if __name__ == '__main__':
    asyncio.run(main())
