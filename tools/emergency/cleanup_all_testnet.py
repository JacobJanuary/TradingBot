#!/usr/bin/env python3
"""
Emergency cleanup script - closes all positions and cancels all orders
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

async def cleanup_exchange(exchange_name, api_key, api_secret):
    """Cleanup single exchange"""
    print(f"\n{'='*60}")
    print(f"🧹 Cleaning up {exchange_name.upper()}")
    print(f"{'='*60}")
    
    try:
        if exchange_name == 'binance':
            exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {'defaultType': 'future'},
                'enableRateLimit': True
            })
            exchange.set_sandbox_mode(True)
            
        elif exchange_name == 'bybit':
            exchange = ccxt.bybit({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {'defaultType': 'future'},
                'enableRateLimit': True
            })
            exchange.set_sandbox_mode(True)
        
        # Fetch positions
        print("\n📊 Positions:")
        if exchange_name == 'binance':
            positions = await exchange.fetch_positions()
        else:
            positions = await exchange.fetch_positions(params={'category': 'linear'})
        
        active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]
        
        if not active_positions:
            print("  No active positions")
        else:
            print(f"  Found {len(active_positions)} active positions")
            
            # Close each position
            for pos in active_positions:
                symbol = pos['symbol']
                side = pos['side']
                contracts = float(pos['contracts'])
                
                print(f"\n  Closing {symbol} ({side}, {contracts} contracts)...")
                
                try:
                    close_side = 'sell' if side == 'long' else 'buy'
                    params = {'reduceOnly': True}
                    if exchange_name == 'bybit':
                        params['category'] = 'linear'
                    
                    order = await exchange.create_market_order(
                        symbol=symbol,
                        side=close_side,
                        amount=contracts,
                        params=params
                    )
                    print(f"  ✅ Closed successfully: {order['id']}")
                except Exception as e:
                    print(f"  ❌ Failed to close: {e}")
        
        # Cancel orders
        print("\n📋 Orders:")
        try:
            if exchange_name == 'binance':
                orders = await exchange.fetch_open_orders()
            else:
                orders = await exchange.fetch_open_orders(params={'category': 'linear'})
            
            if not orders:
                print("  No open orders")
            else:
                print(f"  Found {len(orders)} open orders")
                
                for order in orders:
                    print(f"\n  Canceling {order['symbol']} - {order['id']}...")
                    try:
                        params = {}
                        if exchange_name == 'bybit':
                            params['category'] = 'linear'
                        
                        await exchange.cancel_order(order['id'], order['symbol'], params)
                        print(f"  ✅ Canceled successfully")
                    except Exception as e:
                        print(f"  ❌ Failed to cancel: {e}")
        except Exception as e:
            print(f"  ❌ Failed to fetch orders: {e}")
        
        await exchange.close()
        print(f"\n✅ {exchange_name.upper()} cleanup complete")
        
    except Exception as e:
        print(f"\n❌ {exchange_name.upper()} cleanup failed: {e}")
        import traceback
        traceback.print_exc()

async def main():
    print("\n" + "="*60)
    print("🧹 TESTNET EMERGENCY CLEANUP")
    print("="*60)
    print("\nThis script will:")
    print("  1. Close ALL open positions")
    print("  2. Cancel ALL open orders")
    print("  3. On both Binance and Bybit testnets")
    
    # Get API keys from environment
    binance_key = os.getenv('BINANCE_API_KEY')
    binance_secret = os.getenv('BINANCE_API_SECRET')
    bybit_key = os.getenv('BYBIT_API_KEY')
    bybit_secret = os.getenv('BYBIT_API_SECRET')
    
    if not all([binance_key, binance_secret, bybit_key, bybit_secret]):
        print("\n❌ ERROR: API keys not found in environment!")
        print("Please set BINANCE_API_KEY, BINANCE_API_SECRET, BYBIT_API_KEY, BYBIT_API_SECRET")
        return
    
    # Cleanup both exchanges
    await cleanup_exchange('binance', binance_key, binance_secret)
    await cleanup_exchange('bybit', bybit_key, bybit_secret)
    
    print("\n" + "="*60)
    print("✅ CLEANUP COMPLETE")
    print("="*60)

if __name__ == '__main__':
    asyncio.run(main())
