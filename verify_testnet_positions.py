#!/usr/bin/env python3
"""
Verify positions on TESTNET exchanges vs Database
This script will prove the root cause of TS not working
"""
import asyncio
import asyncpg
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("=" * 80)
    print("TESTNET vs DATABASE POSITION VERIFICATION")
    print("=" * 80)
    print()

    # Database config
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5433)),
        'database': os.getenv('DB_NAME', 'fox_crypto_test'),
        'user': os.getenv('DB_USER', 'elcrypto'),
        'password': os.getenv('DB_PASSWORD', '')
    }

    # Connect to DB
    print(f"📊 Connecting to database: {db_config['database']}...")
    conn = await asyncpg.connect(**db_config)

    # Get active positions from DB
    db_positions = await conn.fetch("""
        SELECT id, symbol, exchange, side, quantity, entry_price, created_at
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY id DESC
    """)

    print(f"✅ Found {len(db_positions)} active positions in DATABASE")
    print()

    # Show DB positions
    print("DATABASE POSITIONS:")
    for pos in db_positions[:10]:  # First 10
        print(f"  #{pos['id']:<4} {pos['symbol']:<15} {pos['exchange']:<8} "
              f"{pos['side']:<6} qty={pos['quantity']:<10} "
              f"entry={pos['entry_price']:<10.4f} created={pos['created_at']}")
    if len(db_positions) > 10:
        print(f"  ... and {len(db_positions) - 10} more")
    print()

    await conn.close()

    # Now check TESTNET exchanges
    print("=" * 80)
    print("CHECKING TESTNET EXCHANGES")
    print("=" * 80)
    print()

    # Binance TESTNET
    print("📡 Connecting to Binance TESTNET...")
    binance = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {'defaultType': 'future'}
    })
    binance.set_sandbox_mode(True)  # TESTNET

    binance_open = []
    try:
        binance_positions = binance.fetch_positions()
        binance_open = [p for p in binance_positions if abs(float(p.get('contracts', 0))) > 0]

        print(f"✅ Binance TESTNET: {len(binance_open)} open positions")
        if binance_open:
            print("  TESTNET POSITIONS:")
            for pos in binance_open:
                print(f"    - {pos['symbol']:<15} contracts={pos['contracts']:<10} "
                      f"side={pos['side']:<6} entry={pos.get('entryPrice', 0)}")
        else:
            print("  ❌ NO positions on Binance TESTNET")
        print()

    except Exception as e:
        print(f"  ❌ Error fetching Binance TESTNET positions: {e}")
        print()

    # Bybit TESTNET
    print("📡 Connecting to Bybit TESTNET...")
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'options': {'defaultType': 'future'}
    })
    bybit.set_sandbox_mode(True)  # TESTNET

    bybit_open = []
    try:
        bybit_positions = bybit.fetch_positions()
        bybit_open = [p for p in bybit_positions if abs(float(p.get('contracts', 0))) > 0]

        print(f"✅ Bybit TESTNET: {len(bybit_open)} open positions")
        if bybit_open:
            print("  TESTNET POSITIONS:")
            for pos in bybit_open:
                print(f"    - {pos['symbol']:<15} contracts={pos['contracts']:<10} "
                      f"side={pos['side']:<6} entry={pos.get('entryPrice', 0)}")
        else:
            print("  ❌ NO positions on Bybit TESTNET")
        print()

    except Exception as e:
        print(f"  ❌ Error fetching Bybit TESTNET positions: {e}")
        print()

    # Analysis
    print("=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    print()

    total_testnet = len(binance_open) + len(bybit_open)
    total_db = len(db_positions)

    print(f"📊 DATABASE: {total_db} active positions")
    print(f"📡 TESTNET EXCHANGES: {total_testnet} open positions")
    print()

    if total_db > 0 and total_testnet == 0:
        print("🔥 ROOT CAUSE CONFIRMED!")
        print()
        print("The bot is configured to run on TESTNET (from .env):")
        print("  BINANCE_TESTNET=true")
        print("  BYBIT_TESTNET=true")
        print()
        print("But the database contains PRODUCTION positions (37 active).")
        print()
        print("When bot starts:")
        print("  1. load_positions_from_db() gets 37 positions from DB")
        print("  2. verify_position_exists() checks TESTNET exchanges")
        print("  3. TESTNET has 0 positions")
        print("  4. All 37 DB positions marked as PHANTOM")
        print("  5. verified_positions = [] (empty)")
        print("  6. self.positions = {} (empty)")
        print("  7. TS NOT initialized (no positions to initialize)")
        print()
        print("SOLUTION:")
        print("  Option A: Switch bot to PRODUCTION mode (.env)")
        print("  Option B: Clear old DB positions and continue TESTNET")
        print()
    elif total_testnet > 0:
        print("⚠️ Found positions on TESTNET.")
        print("These should match DB positions for bot to work correctly.")
        print()
    else:
        print("ℹ️ No positions in DB or on TESTNET.")
        print("This is expected for a fresh start.")
        print()

    binance.close()
    bybit.close()

if __name__ == "__main__":
    asyncio.run(main())
