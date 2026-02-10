#!/usr/bin/env python3
"""
Verify SL Status - Synchronous version
Checks actual Algo SL orders on Binance Futures
"""
import os
import sys
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import ccxt

def verify_sl():
    load_dotenv()
    
    # 1. Initialize Exchange
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'}
    })
    
    print("🔌 Connecting to Binance...")
    exchange.load_markets()
    
    # 2. Get Open Positions
    print("📈 Fetching Open Positions...")
    positions = exchange.fetch_positions()
    active_positions = [p for p in positions if float(p['contracts']) > 0]
    
    print(f"🧐 Found {len(active_positions)} active positions.\n")
    
    # 3. Check each position for Algo SL
    for pos in active_positions:
        symbol = pos['symbol']
        side = pos['side']
        amount = pos['contracts']
        entry_price = pos['entryPrice']
        
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"🔍 Checking {symbol} ({side} {amount} @ {entry_price})")
        
        # Get Algo Orders directly from Binance API
        clean_symbol = symbol.replace('/', '').replace(':USDT', '')
        
        try:
            algo_orders = exchange.fapiPrivateGetOpenAlgoOrders({'symbol': clean_symbol})
            
            if algo_orders:
                print(f"   ✅ Found {len(algo_orders)} Algo orders:")
                for order in algo_orders:
                    algo_id = order.get('algoId')
                    algo_type = order.get('algoType')
                    algo_status = order.get('algoStatus')
                    trigger_price = order.get('triggerPrice')
                    order_side = order.get('side')
                    qty = order.get('quantity')
                    
                    print(f"      - algoId={algo_id}")
                    print(f"        Type: {algo_type}, Status: {algo_status}")
                    print(f"        Side: {order_side}, Trigger: {trigger_price}, Qty: {qty}")
            else:
                print(f"   ❌ NO Algo orders found!")
                
        except Exception as e:
            print(f"   ⚠️ Error fetching Algo orders: {e}")
        
        # Also check regular open orders
        try:
            open_orders = exchange.fetch_open_orders(symbol)
            if open_orders:
                print(f"   📋 Regular open orders: {len(open_orders)}")
                for order in open_orders:
                    print(f"      - ID: {order['id']}, Type: {order['type']}, Side: {order['side']}")
            else:
                print(f"   📋 No regular open orders")
        except Exception as e:
            print(f"   ⚠️ Error fetching regular orders: {e}")

    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✅ Verification complete!")

if __name__ == "__main__":
    verify_sl()
