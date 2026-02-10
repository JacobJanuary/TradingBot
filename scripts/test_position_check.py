#!/usr/bin/env python3
"""
Diagnostic script to test _is_position_already_open layers
Run from TradingBot root: python scripts/test_position_check.py
"""
import asyncio
import asyncpg
import os
from decimal import Decimal

# DB Config
DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'database': 'tradebot_db',
    'user': 'tradebot_user',
    'password': 'LohNeMamont@)11'
}

async def test_db_layer():
    """Test Layer 2: Database check (repository.get_open_position)"""
    print("\n=== LAYER 2: Database Check ===")
    
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # Exact query from repository.get_open_position
        query = """
            SELECT * FROM monitoring.positions
            WHERE symbol = $1 
                AND exchange = $2 
                AND status = 'active'
            LIMIT 1
        """
        
        row = await conn.fetchrow(query, 'CVXUSDT', 'binance')
        
        if row:
            print(f"✅ FOUND in DB: id={row['id']}, status={row['status']}")
            return True
        else:
            print("❌ NOT FOUND in DB")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False
    finally:
        await conn.close()

async def test_cache_layer():
    """Test Layer 1: Cache check (position_manager.positions)"""
    print("\n=== LAYER 1: Cache Check ===")
    print("⚠️ Cannot test without running bot process")
    print("This layer checks self.position_manager.positions dict")
    return None

async def test_exchange_layer():
    """Test Layer 3: Exchange API check"""
    print("\n=== LAYER 3: Exchange API Check ===")
    
    try:
        import ccxt.pro as ccxt
        
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            print("⚠️ BINANCE_API_KEY/SECRET not set, skipping")
            return None
        
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': False,
            'options': {'defaultType': 'future'}
        })
        
        positions = await exchange.fetch_positions()
        
        for pos in positions:
            if pos['symbol'] == 'CVXUSDT' or pos['symbol'] == 'CVX/USDT:USDT':
                amount = float(pos.get('contracts', 0) or pos.get('contractSize', 0))
                if amount != 0:
                    print(f"✅ FOUND on Exchange: {pos['symbol']}, amount={amount}")
                    await exchange.close()
                    return True
        
        print("❌ NOT FOUND on Exchange (no position size)")
        await exchange.close()
        return False
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

async def main():
    print("=" * 60)
    print("TESTING _is_position_already_open LAYERS")
    print("=" * 60)
    
    db_result = await test_db_layer()
    cache_result = await test_cache_layer()
    # exchange_result = await test_exchange_layer()  # Commented - needs API keys
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Layer 1 (Cache):    {'SKIPPED' if cache_result is None else ('✅ PASS' if cache_result else '❌ FAIL')}")
    print(f"Layer 2 (Database): {'✅ PASS' if db_result else '❌ FAIL'}")
    # print(f"Layer 3 (Exchange): {'SKIPPED' if exchange_result is None else ('✅ PASS' if exchange_result else '❌ FAIL')}")
    
    if db_result:
        print("\n⚠️ DB finds position, but spam continues!")
        print("This means either:")
        print("1. ReentryManager.repository is NOT SET (check main.py)")
        print("2. Exception in _is_position_already_open is caught silently")
        print("3. Signal in-memory still has status='active' (restart bot)")

if __name__ == "__main__":
    asyncio.run(main())
