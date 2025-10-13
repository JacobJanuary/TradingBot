#!/usr/bin/env python3
"""
Check positions table in detail
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5433)),
        'database': os.getenv('DB_NAME', 'fox_crypto_test'),
        'user': os.getenv('DB_USER', 'elcrypto'),
        'password': os.getenv('DB_PASSWORD', '')
    }

    conn = await asyncpg.connect(**config)

    print("=" * 80)
    print("POSITIONS TABLE ANALYSIS")
    print("=" * 80)
    print()

    # Total positions
    total = await conn.fetchval("SELECT COUNT(*) FROM monitoring.positions")
    print(f"📊 Total positions: {total}")
    print()

    # By status
    print("Status breakdown:")
    statuses = await conn.fetch("""
        SELECT status, COUNT(*) as count
        FROM monitoring.positions
        GROUP BY status
        ORDER BY count DESC
    """)
    for s in statuses:
        print(f"  - {s['status']:<15} {s['count']:>3} positions")
    print()

    # By exchange
    print("Exchange breakdown:")
    exchanges = await conn.fetch("""
        SELECT exchange, COUNT(*) as count
        FROM monitoring.positions
        GROUP BY exchange
        ORDER BY count DESC
    """)
    for e in exchanges:
        print(f"  - {e['exchange']:<15} {e['count']:>3} positions")
    print()

    # Check has_trailing_stop column
    print("Trailing Stop status:")
    try:
        ts_stats = await conn.fetch("""
            SELECT
                has_trailing_stop,
                trailing_activated,
                COUNT(*) as count
            FROM monitoring.positions
            GROUP BY has_trailing_stop, trailing_activated
            ORDER BY count DESC
        """)
        for ts in ts_stats:
            has_ts = "YES" if ts['has_trailing_stop'] else "NO"
            activated = "YES" if ts['trailing_activated'] else "NO"
            print(f"  - has_trailing_stop={has_ts}, trailing_activated={activated}: {ts['count']} positions")
    except Exception as e:
        print(f"  ❌ Error checking trailing_stop columns: {e}")
    print()

    # Recent positions
    print("📝 Last 10 positions (all statuses):")
    recent = await conn.fetch("""
        SELECT
            id, symbol, exchange, side, status,
            has_stop_loss, stop_loss_price,
            has_trailing_stop, trailing_activated,
            created_at, closed_at
        FROM monitoring.positions
        ORDER BY id DESC
        LIMIT 10
    """)
    for pos in recent:
        sl_status = f"SL={pos['stop_loss_price']:.4f}" if pos['has_stop_loss'] and pos['stop_loss_price'] else "NO_SL"
        ts_status = f"TS={'ACT' if pos['trailing_activated'] else 'INIT'}" if pos['has_trailing_stop'] else "NO_TS"
        closed_info = f" → closed {pos['closed_at']}" if pos['closed_at'] else ""

        print(f"  #{pos['id']:<4} {pos['symbol']:<15} {pos['exchange']:<8} "
              f"{pos['side']:<6} {pos['status']:<8} {sl_status:<20} {ts_status:<10} "
              f"created {pos['created_at']}{closed_info}")
    print()

    # Check if has_stop_loss is TRUE for any
    sl_true = await conn.fetchval("""
        SELECT COUNT(*) FROM monitoring.positions WHERE has_stop_loss = TRUE
    """)
    print(f"Positions with has_stop_loss=TRUE: {sl_true}")

    # Check if has_trailing_stop is TRUE for any
    ts_true = await conn.fetchval("""
        SELECT COUNT(*) FROM monitoring.positions WHERE has_trailing_stop = TRUE
    """)
    print(f"Positions with has_trailing_stop=TRUE: {ts_true}")
    print()

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
