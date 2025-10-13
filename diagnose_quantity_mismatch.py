#!/usr/bin/env python3
"""Diagnose quantity mismatch between DB and Exchange"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt

async def diagnose():
    load_dotenv()

    # Connect to DB
    db_conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5433')),
        database=os.getenv('DB_NAME', 'fox_crypto_test'),
        user=os.getenv('DB_USER', 'elcrypto'),
        password=os.getenv('DB_PASSWORD')
    )

    # Connect to Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })

    # Set testnet
    bybit.set_sandbox_mode(True)

    try:
        symbols = ['AGIUSDT', 'SCAUSDT', 'HNTUSDT']

        print("="*80)
        print("QUANTITY MISMATCH DIAGNOSIS")
        print("="*80)

        for symbol in symbols:
            print(f"\n{'='*80}")
            print(f"{symbol}")
            print("="*80)

            # Get DB data
            db_pos = await db_conn.fetchrow("""
                SELECT
                    id,
                    quantity,
                    entry_price,
                    side,
                    created_at,
                    updated_at
                FROM monitoring.positions
                WHERE symbol = $1 AND status = 'active'
            """, symbol)

            if db_pos:
                print(f"\n📊 DB DATA:")
                print(f"  Position ID: {db_pos['id']}")
                print(f"  Quantity: {db_pos['quantity']}")
                print(f"  Entry Price: {db_pos['entry_price']}")
                print(f"  Side: {db_pos['side']}")
                print(f"  Created: {db_pos['created_at']}")
                print(f"  Updated: {db_pos['updated_at']}")

                if db_pos['updated_at'] != db_pos['created_at']:
                    diff = db_pos['updated_at'] - db_pos['created_at']
                    print(f"  ⚠️ MODIFIED: {diff} after creation")
            else:
                print(f"\n📊 DB DATA: Not found")
                continue

            # Get Exchange data
            print(f"\n📡 EXCHANGE DATA (Bybit):")
            positions = await bybit.fetch_positions(params={'category': 'linear'})

            # Find this symbol
            ex_pos = None
            for pos in positions:
                if pos['symbol'] == symbol or pos['symbol'].replace('/', '').replace(':USDT', 'USDT') == symbol:
                    ex_pos = pos
                    break

            if ex_pos:
                contracts = float(ex_pos.get('contracts') or 0)
                print(f"  Symbol: {ex_pos['symbol']}")
                print(f"  Contracts: {contracts}")
                print(f"  Side: {ex_pos.get('side')}")
                print(f"  Mark Price: {ex_pos.get('markPrice')}")
                print(f"  Leverage: {ex_pos.get('leverage')}")

                # Raw info
                info = ex_pos.get('info', {})
                print(f"\n  📋 Raw Exchange Data:")
                print(f"    size: {info.get('size')}")
                print(f"    positionValue: {info.get('positionValue')}")
                print(f"    avgPrice: {info.get('avgPrice')}")
                print(f"    unrealisedPnl: {info.get('unrealisedPnl')}")

                # Compare
                print(f"\n  📊 COMPARISON:")
                db_qty = float(db_pos['quantity'])
                diff = db_qty - contracts
                diff_pct = (diff / db_qty * 100) if db_qty > 0 else 0

                print(f"    DB Quantity: {db_qty}")
                print(f"    Exchange Quantity: {contracts}")
                print(f"    Difference: {diff} ({diff_pct:.2f}%)")

                if abs(diff) < 0.01:
                    print(f"    ✅ MATCH")
                elif abs(diff_pct) < 1:
                    print(f"    ⚠️ Small rounding error")
                else:
                    print(f"    ❌ SIGNIFICANT MISMATCH")

                    # Hypothesis
                    print(f"\n  🔍 POSSIBLE CAUSES:")
                    if diff > 0:
                        print(f"    • DB has MORE than exchange (partial close?)")
                        print(f"    • Limit order partially filled?")
                        print(f"    • Stop-loss partially triggered?")
                    else:
                        print(f"    • DB has LESS than exchange (averaging?)")
                        print(f"    • Position increased on exchange?")
            else:
                print(f"  ❌ NOT FOUND ON EXCHANGE")

        await bybit.close()

    finally:
        await db_conn.close()

if __name__ == '__main__':
    asyncio.run(diagnose())
