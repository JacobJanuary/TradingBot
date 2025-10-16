import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def check_xdc():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_TESTNET_API_KEY'),
        'secret': os.getenv('BYBIT_TESTNET_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })
    exchange.set_sandbox_mode(True)

    print("\n" + "="*60)
    print("CHECKING XDCUSDT TICKER ON BYBIT TESTNET")
    print("="*60)

    ticker = await exchange.fetch_ticker('XDCUSDT')
    print(f"\nTicker for XDCUSDT:")
    print(f"  last:   {ticker.get('last')}")
    print(f"  bid:    {ticker.get('bid')}")
    print(f"  ask:    {ticker.get('ask')}")
    print(f"  high:   {ticker.get('high')}")
    print(f"  low:    {ticker.get('low')}")
    print(f"  volume: {ticker.get('baseVolume')}")

    # Check market info
    await exchange.load_markets()
    market = exchange.markets.get('XDCUSDT')
    if market:
        print(f"\nMarket info:")
        print(f"  active: {market.get('active')}")
        print(f"  price precision: {market.get('precision', {}).get('price')}")
        print(f"  min price: {market.get('limits', {}).get('price', {}).get('min')}")

    await exchange.close()
    print("\n" + "="*60)

if __name__ == '__main__':
    asyncio.run(check_xdc())
