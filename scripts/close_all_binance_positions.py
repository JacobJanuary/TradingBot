import asyncio
import os
import sys
from decimal import Decimal
from typing import List, Dict
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# Add project root to path to allow importing if needed, 
# though we try to keep this standalone.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    # Load environment variables
    load_dotenv(override=True)
    
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        print("Error: BINANCE_API_KEY or BINANCE_API_SECRET not found in .env")
        return

    print("Initializing Binance Futures connection...")
    
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'fetchPositions': 'positionRisk',
        }
    })

    # Check for testnet
    if os.getenv('BINANCE_TESTNET', 'false').lower() == 'true':
        print("Using Binance TESTNET")
        exchange.set_sandbox_mode(True)

    try:
        # Verify connection
        await exchange.load_markets()
        print("Connected to Binance.")

        # Fetch positions
        print("Fetching open positions...")
        # We fetch all positions and filter locally
        positions = await exchange.fetch_positions()
        
        open_positions = []
        for pos in positions:
            # Check for open positions (contracts > 0)
            if pos['contracts'] and float(pos['contracts']) > 0:
                open_positions.append(pos)

        if not open_positions:
            print("No open positions found.")
            await exchange.close()
            return

        print(f"\nFound {len(open_positions)} open positions:")
        print(f"{'Symbol':<15} {'Side':<10} {'Size':<15} {'PnL (USDT)':<15}")
        print("-" * 60)
        
        for pos in open_positions:
            symbol = pos['symbol']
            side = pos['side']
            size = pos['contracts']
            pnl = pos['unrealizedPnl']
            print(f"{symbol:<15} {side:<10} {size:<15} {pnl:<15}")

        print("-" * 60)
        confirm = input(f"\nAre you sure you want to CLOSE ALL {len(open_positions)} positions at MARKET price? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Operation cancelled.")
            await exchange.close()
            return

        print("\nClosing positions...")
        
        for pos in open_positions:
            symbol = pos['symbol']
            side = pos['side']
            amount = pos['contracts']
            
            # Determine close side
            close_side = 'sell' if side == 'long' else 'buy'
            
            try:
                print(f"Closing {symbol} ({side} {amount})...")
                order = await exchange.create_market_order(
                    symbol=symbol,
                    side=close_side,
                    amount=amount,
                    params={'reduceOnly': True}
                )
                print(f"✅ Closed {symbol}: Order ID {order['id']}")
            except Exception as e:
                print(f"❌ Failed to close {symbol}: {e}")

        print("\nDone.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
