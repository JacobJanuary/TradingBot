#!/usr/bin/env python3
"""Inspect raw Bybit order response in detail"""
import asyncio
import ccxt.async_support as ccxt
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def inspect():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    exchange.set_sandbox_mode(True)

    try:
        await exchange.load_markets()

        symbol = 'BTC/USDT:USDT'
        ticker = await exchange.fetch_ticker(symbol)
        last_price = ticker['last']

        market = exchange.markets[symbol]
        min_amount = market['limits']['amount']['min']
        test_quantity = exchange.amount_to_precision(symbol, min_amount)

        print(f"Creating market order for {symbol}...")
        order = await exchange.create_market_order(
            symbol=symbol,
            side='buy',
            amount=test_quantity
        )

        print("\n" + "="*80)
        print("COMPLETE ORDER RESPONSE")
        print("="*80)
        print(json.dumps(order, indent=2, default=str))

        print("\n" + "="*80)
        print("KEY ANALYSIS")
        print("="*80)
        print(f"order['status'] = {order.get('status')!r} (type: {type(order.get('status')).__name__})")
        print(f"order['info'] keys = {list(order.get('info', {}).keys())}")
        print(f"order['info']['orderStatus'] = {order.get('info', {}).get('orderStatus')!r}")

        # Wait a bit then fetch order
        print("\n" + "="*80)
        print("FETCHING ORDER AFTER CREATION")
        print("="*80)
        await asyncio.sleep(2)

        fetched = await exchange.fetch_order(order['id'], symbol)
        print(json.dumps(fetched, indent=2, default=str))

        print("\n" + "="*80)
        print("FETCHED ORDER ANALYSIS")
        print("="*80)
        print(f"fetched['status'] = {fetched.get('status')!r} (type: {type(fetched.get('status')).__name__})")
        print(f"fetched['info']['orderStatus'] = {fetched.get('info', {}).get('orderStatus')!r}")

    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(inspect())
