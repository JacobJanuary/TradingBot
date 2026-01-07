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
import logging
import os
import sys
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('test_position_sui')


async def main():
    print("=" * 70)
    print("TEST POSITION SCRIPT: SUIUSDT")
    print("=" * 70)
    print(f"Time: {datetime.now()}")
    print()
    
    try:
        from config.settings import config as settings
        from database.repository import Repository
        from core.exchange_manager import ExchangeManager
        from core.position_manager import PositionManager, PositionRequest
        from websocket.event_router import EventRouter
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    try:
        # 1. Validate settings
        print("[1] Validating settings...")
        if not settings.validate():
            raise Exception("Settings validation failed")
        print("✅ Settings validated")
        
        # 2. Initialize database
        print("[2] Initializing database...")
        db_config = {
            'host': settings.database.host,
            'port': settings.database.port,
            'database': settings.database.database,
            'user': settings.database.user,
            'password': settings.database.password,
        }
        repository = Repository(db_config)
        await repository.initialize()
        print("✅ Database initialized")
        
        # 3. Initialize event router
        event_router = EventRouter()
        
        # 4. Initialize exchange
        print("[3] Initializing exchange...")
        exchange_config = settings.exchanges['binance']
        exchange = ExchangeManager(
            'binance', 
            exchange_config.__dict__, 
            repository=repository, 
            position_manager=None
        )
        await exchange.initialize()
        print("✅ Exchange initialized")
        
        # 5. Initialize position manager
        print("[4] Initializing position manager...")
        position_manager = PositionManager(
            settings.trading,
            {'binance': exchange},
            repository,
            event_router
        )
        exchange.position_manager = position_manager
        print("✅ Position manager initialized")
        
        # 6. Open test position
        symbol = "SUIUSDT"
        leverage = 5
        position_size_usd = 10.0
        
        print()
        print(f"[5] Opening test position:")
        print(f"    Symbol: {symbol}")
        print(f"    Leverage: {leverage}x")
        print(f"    Size: ${position_size_usd}")
        
        # Set leverage
        success = await exchange.set_leverage(symbol, leverage)
        if not success:
            print("❌ Failed to set leverage")
            return
        print(f"    ✅ Leverage set to {leverage}x")
        
        # Get current price
        ticker = await exchange.fetch_ticker(symbol)
        if not ticker:
            print("❌ Failed to fetch ticker")
            return
        current_price = Decimal(str(ticker['last']))
        print(f"    Current price: ${current_price}")
        
        # Create position request
        print()
        print("[6] Creating position request...")
        req = PositionRequest(
            signal_id=9999,  # Test signal ID
            symbol=symbol,
            exchange='binance',
            side='BUY',
            entry_price=current_price,
            position_size_usd=position_size_usd
        )
        
        # Execute
        print("[7] Executing open_position...")
        result = await position_manager.open_position(req)
        
        if result:
            print()
            print("✅✅ POSITION OPENED SUCCESSFULLY! ✅✅")
            print(f"    Details: {result}")
        else:
            print("❌ Failed to open position")
        
        # Cleanup
        await exchange.close()
        await repository.pool.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Verification instructions
    print()
    print("=" * 70)
    print("VERIFICATION STEPS")
    print("=" * 70)
    print("""
1. Check logs for CRITICAL FIX:
   grep "Position cache populated" logs/trading_bot.log | tail -5
   
   Expected: "📊 [MARK] Position cache populated for SUIUSDT (ACCOUNT_UPDATE bypass)"

2. Check position updates (should appear within seconds):
   grep "SUIUSDT" logs/trading_bot.log | tail -20

3. If the log message appears, the fix is working!
   
4. Close position when done via exchange UI or wait for TS.
""")


if __name__ == "__main__":
    asyncio.run(main())
