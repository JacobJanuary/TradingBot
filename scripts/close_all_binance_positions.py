import asyncio
import os
import sys
from decimal import Decimal
from typing import List, Dict
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# Add project root to path
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
        print("Connected to Binance.\n")

        # Fetch positions
        print("Fetching open positions...")
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

        # Display positions with numbers
        print(f"\n{'#':<4} {'Symbol':<15} {'Side':<8} {'Size':<15} {'Entry':<12} {'Mark':<12} {'PnL (USDT)':<12} {'PnL %':<10}")
        print("-" * 100)
        
        for i, pos in enumerate(open_positions, 1):
            symbol = pos['symbol']
            side = pos['side'].upper()
            size = pos['contracts']
            entry_price = float(pos.get('entryPrice', 0))
            mark_price = float(pos.get('markPrice', 0))
            pnl = float(pos.get('unrealizedPnl', 0))
            pnl_pct = float(pos.get('percentage', 0))
            
            # Color coding for PnL
            pnl_str = f"${pnl:+.2f}"
            pnl_pct_str = f"{pnl_pct:+.2f}%"
            
            print(f"{i:<4} {symbol:<15} {side:<8} {size:<15} {entry_price:<12.6f} {mark_price:<12.6f} {pnl_str:<12} {pnl_pct_str:<10}")

        print("-" * 100)
        print(f"\nTotal positions: {len(open_positions)}")
        print("\nOptions:")
        print("  Enter position number (1-{}) to close specific position".format(len(open_positions)))
        print("  Enter 'all' to close ALL positions")
        print("  Enter 'q' or press Enter to quit")
        
        choice = input("\nEnter your choice: ").strip().lower()
        
        if not choice or choice == 'q':
            print("Operation cancelled.")
            await exchange.close()
            return
        
        positions_to_close = []
        
        if choice == 'all':
            confirm = input(f"\n⚠️  Are you sure you want to CLOSE ALL {len(open_positions)} positions? (yes/no): ")
            if confirm.lower() != 'yes':
                print("Operation cancelled.")
                await exchange.close()
                return
            positions_to_close = open_positions
        else:
            try:
                pos_num = int(choice)
                if 1 <= pos_num <= len(open_positions):
                    selected_pos = open_positions[pos_num - 1]
                    confirm = input(f"\nClose {selected_pos['symbol']} ({selected_pos['side']} {selected_pos['contracts']})? (yes/no): ")
                    if confirm.lower() != 'yes':
                        print("Operation cancelled.")
                        await exchange.close()
                        return
                    positions_to_close = [selected_pos]
                else:
                    print(f"Invalid number. Must be between 1 and {len(open_positions)}")
                    await exchange.close()
                    return
            except ValueError:
                print("Invalid input. Enter a number, 'all', or 'q'.")
                await exchange.close()
                return

        # Close selected positions
        print("\nClosing positions...")
        
        for pos in positions_to_close:
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

