#!/usr/bin/env python3
"""
Quick script to open FILUSDT LONG position
$2 with 10x leverage = $20 exposure
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

async def main():
    import ccxt.async_support as ccxt
    
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    exchange = ccxt.binanceusdm({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    symbol = 'FIL/USDT:USDT'
    leverage = 10
    size_usdt = 20  # $20 with 10x = $2 margin
    
    try:
        # Set leverage
        await exchange.set_leverage(leverage, symbol)
        print(f"✅ Leverage set to {leverage}x")
        
        # Get current price
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']
        print(f"📊 Current price: ${price}")
        
        # Calculate quantity
        qty = size_usdt / price
        qty = round(qty, 1)  # FIL precision
        print(f"📦 Quantity: {qty} FIL (${qty * price:.2f})")
        
        # Open LONG position
        order = await exchange.create_market_order(symbol, 'buy', qty)
        print(f"✅ Position opened!")
        print(f"   Order ID: {order['id']}")
        print(f"   Filled: {order.get('filled', qty)} @ ${order.get('average', price):.4f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(main())
