#!/usr/bin/env python3
"""
Проверка баланса Bybit testnet
"""
import asyncio
import ccxt.pro as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    # Initialize Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'testnet': True,
        'options': {
            'defaultType': 'linear',
            'defaultSettle': 'USDT'
        }
    })

    try:
        # Получаем баланс
        balance = await bybit.fetch_balance()

        print("=" * 60)
        print("BYBIT TESTNET BALANCE:")
        print("=" * 60)

        # Показываем все балансы
        if 'USDT' in balance:
            usdt = balance['USDT']
            print(f"\n💰 USDT Balance:")
            print(f"  Total: {usdt.get('total', 0)}")
            print(f"  Free: {usdt.get('free', 0)}")
            print(f"  Used: {usdt.get('used', 0)}")

        # Также проверим raw ответ
        print(f"\n📊 Raw balance info:")
        print(f"  Total assets: {balance.get('info', {}).get('result', {}).get('totalEquity', 'N/A')}")
        print(f"  Available balance: {balance.get('info', {}).get('result', {}).get('availableBalance', 'N/A')}")
        print(f"  Margin used: {balance.get('info', {}).get('result', {}).get('totalMarginBalance', 'N/A')}")

        # Проверим позиции для контекста
        positions = await bybit.fetch_positions()
        active_positions = [p for p in positions if p['contracts'] > 0]

        if active_positions:
            print(f"\n📈 Active Positions ({len(active_positions)}):")
            total_margin = 0
            for pos in active_positions:
                margin = float(pos.get('initialMargin', 0))
                total_margin += margin
                print(f"  - {pos['symbol']}: {pos['side']} {pos['contracts']} contracts")
                print(f"    Entry: ${pos['entryPrice']}, Margin: ${margin:.2f}")
            print(f"\n  Total margin in positions: ${total_margin:.2f}")

    finally:
        await bybit.close()

if __name__ == "__main__":
    asyncio.run(main())