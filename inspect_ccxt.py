
import ccxt.pro as ccxt
import sys
import asyncio

async def inspect():
    print(f"CCXT Version: {ccxt.__version__}")
    try:
        # Use CCXT Pro (Async)
        exchange = ccxt.binance({'options': {'defaultType': 'future'}})
        print("Exchange initialized (CCXT PRO / ASYNC). Searching for 'algo' methods...")
    
    algo_methods = [m for m in dir(exchange) if 'algo' in m.lower()]
    found = False
    
    for m in algo_methods:
        # Check if it looks like the one we want
        print(f"  - {m}")
        found = True
        
    if not found:
        print("NO ALGO METHODS FOUND matching 'algo'")
        
    # Also check specific variants we tried
    variants = [
        'fapiPrivatePostAlgoOrder',
        'fapiprivate_post_algoorder',
        'fapiPrivateGetOpenAlgoOrders',
        'fapiprivate_get_openalgoorders'
    ]
    print("\nVerifying specific variants:")
    for v in variants:
        has = hasattr(exchange, v)
        print(f"  {v}: {has}")

    await exchange.close()

if __name__ == '__main__':
    try:
        asyncio.run(inspect())
    except Exception as e:
        print(f"Error inspecting exchange: {e}")
