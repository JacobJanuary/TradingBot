#!/usr/bin/env python3
"""
Test Position Script: Opens a small test position on SUIUSDT

PURPOSE: Verify that the CRITICAL FIX (commit 2e16a6c) works:
- Position opens via REST API
- subscribe_symbol() is called with position_data
- self.positions is populated immediately (ACCOUNT_UPDATE bypass)
- Mark price updates trigger position events
- TS sees and monitors the position

VERIFICATION:
1. Run this script after deploying the fix
2. Check logs for: "📊 [MARK] Position cache populated for SUIUSDT (ACCOUNT_UPDATE bypass)"
3. Verify position updates appear immediately (no restart needed)

Run on server: python scripts/test_position_suiusdt.py
"""

import asyncio
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime


async def main():
    print("=" * 70)
    print("TEST POSITION SCRIPT: SUIUSDT")
    print("=" * 70)
    print(f"Time: {datetime.now()}")
    print()
    
    # Import after path setup
    try:
        from config.settings import Settings
        from core.exchange_manager import ExchangeManager
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Run from project root with: python scripts/test_position_suiusdt.py")
        return
    
    settings = Settings()
    
    # Get Binance config
    binance_config = settings.exchanges.get('binance')
    if not binance_config:
        print("❌ No binance config found in settings")
        return
    
    print("[1] Initializing exchange manager...")
    exchange_manager = ExchangeManager()
    await exchange_manager.initialize()
    
    exchange = exchange_manager.exchanges.get('binance')
    if not exchange:
        print("❌ Binance exchange not initialized")
        return
    
    print("✅ Exchange initialized")
    
    # Symbol and parameters
    symbol = "SUI/USDT:USDT"
    leverage = 5
    position_size_usdt = 10  # Small test position: $10
    
    print()
    print(f"[2] Opening test position:")
    print(f"    Symbol: {symbol}")
    print(f"    Leverage: {leverage}x")
    print(f"    Size: ${position_size_usdt}")
    print()
    
    try:
        # Get current price
        ticker = await exchange.fetch_ticker(symbol)
        current_price = float(ticker['last'])
        print(f"    Current price: ${current_price:.4f}")
        
        # Calculate quantity
        quantity = position_size_usdt / current_price
        quantity = float(exchange.amount_to_precision(symbol, quantity))
        print(f"    Quantity: {quantity}")
        
        # Set leverage
        await exchange.set_leverage(leverage, symbol)
        print(f"    ✅ Leverage set to {leverage}x")
        
        # Place market order
        print()
        print("[3] Placing MARKET BUY order...")
        order = await exchange.create_market_order(
            symbol=symbol,
            side='buy',
            amount=quantity
        )
        
        print(f"    ✅ Order placed: {order['id']}")
        print(f"    Status: {order['status']}")
        print(f"    Filled: {order.get('filled', 0)}")
        print(f"    Avg Price: ${order.get('average', 0):.4f}")
        
    except Exception as e:
        print(f"❌ Error opening position: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        await exchange_manager.close()
    
    # Verification instructions
    print()
    print("=" * 70)
    print("VERIFICATION STEPS")
    print("=" * 70)
    print("""
1. Check logs for CRITICAL FIX verification:
   grep "Position cache populated" logs/trading_bot.log | tail -5
   
   Expected: "📊 [MARK] Position cache populated for SUIUSDT (ACCOUNT_UPDATE bypass)"

2. Check for position updates (should appear within seconds):
   grep "SUIUSDT" logs/trading_bot.log | tail -20
   
   Look for: "📊 Position update: SUIUSDT" or "[TS_DEBUG]"

3. Check TS is monitoring:
   grep "TS.*SUIUSDT" logs/trading_bot.log | tail -10

4. If all checks pass, the fix is working!

5. To close the test position, use manual close or wait for TS.
""")


if __name__ == "__main__":
    asyncio.run(main())
