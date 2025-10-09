#!/usr/bin/env python3
"""
Monitor Signal Waves and Position Opening
Waits for signal waves at 06, 20, 35, 50 minutes of each hour
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime, timedelta
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5433)),
    'database': os.getenv('DB_NAME', 'fox_crypto_test'),
    'user': os.getenv('DB_USER', 'elcrypto'),
    'password': os.getenv('DB_PASSWORD')
}

WAVE_MINUTES = [6, 20, 35, 50]

def get_next_wave_time():
    """Calculate next expected wave time"""
    now = datetime.now()
    current_minute = now.minute

    # Find next wave minute
    for wave_min in WAVE_MINUTES:
        if current_minute < wave_min:
            next_wave = now.replace(minute=wave_min, second=0, microsecond=0)
            return next_wave

    # No more waves this hour, get first wave of next hour
    next_hour = now.replace(hour=now.hour, minute=0, second=0, microsecond=0) + timedelta(hours=1)
    next_wave = next_hour.replace(minute=WAVE_MINUTES[0])
    return next_wave


def format_time_until(target_time):
    """Format time remaining until target"""
    now = datetime.now()
    delta = target_time - now

    if delta.total_seconds() < 0:
        return "NOW (or delayed 1-3 min)"

    minutes = int(delta.total_seconds() // 60)
    seconds = int(delta.total_seconds() % 60)

    if minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


async def get_recent_positions(conn, since_minutes=5):
    """Get positions created in last N minutes"""
    query = """
    SELECT
        id, symbol, side, exchange, status,
        has_stop_loss, stop_loss_price,
        entry_price, created_at
    FROM monitoring.positions
    WHERE created_at > NOW() - INTERVAL '%s minutes'
    ORDER BY id DESC
    """

    rows = await conn.fetch(query.replace('%s', str(since_minutes)))
    return [dict(row) for row in rows]


async def get_position_stats(conn, since_minutes=5):
    """Get statistics for recent positions"""
    query = """
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN has_stop_loss THEN 1 END) as with_sl,
        COUNT(CASE WHEN status='open' THEN 1 END) as open_count,
        COUNT(CASE WHEN status='closed' THEN 1 END) as closed_count,
        COUNT(CASE WHEN status='error' THEN 1 END) as error_count,
        ARRAY_AGG(DISTINCT exchange) as exchanges
    FROM monitoring.positions
    WHERE created_at > NOW() - INTERVAL '%s minutes'
    """

    row = await conn.fetchrow(query.replace('%s', str(since_minutes)))
    return dict(row) if row else {}


async def monitor_wave(conn, wave_time, timeout_minutes=10):
    """Monitor for positions after wave time"""
    print(f"\n{'='*80}")
    print(f"🌊 MONITORING WAVE: {wave_time.strftime('%H:%M')}")
    print(f"{'='*80}")
    print(f"Wave detection window: {wave_time.strftime('%H:%M')} - {(wave_time + timedelta(minutes=4)).strftime('%H:%M')}")
    print(f"Position monitoring: Until {(wave_time + timedelta(minutes=timeout_minutes)).strftime('%H:%M')}")
    print()

    # Wait until wave time (plus small buffer for delays)
    wait_until = wave_time - timedelta(seconds=30)
    now = datetime.now()

    if now < wait_until:
        wait_seconds = (wait_until - now).total_seconds()
        print(f"⏰ Waiting {format_time_until(wait_until)} until wave detection...")
        await asyncio.sleep(wait_seconds)

    print(f"✅ Wave detection window started!")
    print()

    # Track positions from before wave
    positions_before = await get_recent_positions(conn, since_minutes=60)
    ids_before = {p['id'] for p in positions_before}

    # Monitor for new positions
    start_time = datetime.now()
    timeout = wave_time + timedelta(minutes=timeout_minutes)
    new_positions = []
    last_count = 0

    while datetime.now() < timeout:
        # Check for new positions
        all_positions = await get_recent_positions(conn, since_minutes=15)
        new_positions = [p for p in all_positions if p['id'] not in ids_before]

        if len(new_positions) > last_count:
            # New position detected!
            for pos in new_positions[last_count:]:
                sl_status = "✅ YES" if pos['has_stop_loss'] else "❌ NO"
                print(f"\n🆕 Position #{pos['id']}: {pos['exchange'].upper()} {pos['symbol']} {pos['side'].upper()}")
                print(f"   Status: {pos['status']} | SL: {sl_status}")
                if pos['has_stop_loss']:
                    print(f"   Entry: {pos['entry_price']} | SL: {pos['stop_loss_price']}")
                print(f"   Created: {pos['created_at'].strftime('%H:%M:%S')}")

            last_count = len(new_positions)

        # Show status
        elapsed = datetime.now() - start_time
        remaining = timeout - datetime.now()

        print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
              f"Wave +{int(elapsed.total_seconds()//60)}m | "
              f"New positions: {len(new_positions)} | "
              f"Timeout: {int(remaining.total_seconds()//60)}m {int(remaining.total_seconds()%60)}s  ",
              end='', flush=True)

        await asyncio.sleep(5)

    print("\n")

    # Final summary
    stats = await get_position_stats(conn, since_minutes=15)

    print(f"\n{'='*80}")
    print(f"📊 WAVE RESULTS: {wave_time.strftime('%H:%M')}")
    print(f"{'='*80}")

    if new_positions:
        print(f"✅ Detected {len(new_positions)} new positions")
        print(f"   - With Stop Loss: {stats.get('with_sl', 0)}/{stats.get('total', 0)}")
        print(f"   - Status Open: {stats.get('open_count', 0)}")
        print(f"   - Status Closed: {stats.get('closed_count', 0)}")
        print(f"   - Status Error: {stats.get('error_count', 0)}")

        if stats.get('exchanges'):
            exchanges = [e for e in stats['exchanges'] if e]
            print(f"   - Exchanges: {', '.join(exchanges)}")

        print("\nRecent Positions:")
        for pos in new_positions[:10]:  # Show max 10
            sl_emoji = "✅" if pos['has_stop_loss'] else "❌"
            print(f"  {sl_emoji} #{pos['id']}: {pos['symbol']} {pos['side']} - {pos['status']}")
    else:
        print("⚠️  No new positions detected")
        print(f"   Possible reasons:")
        print(f"   - No signals from WebSocket server")
        print(f"   - Bot not processing signals")
        print(f"   - All signals filtered (stoplist, whitelist)")

    print(f"{'='*80}\n")

    return new_positions


async def main():
    """Main monitoring loop"""
    print("=" * 80)
    print("🌊 SIGNAL WAVE MONITOR")
    print("=" * 80)
    print(f"Wave schedule: {', '.join([f'{m:02d}' for m in WAVE_MINUTES])} minutes past each hour")
    print(f"Expected delay: 0-3 minutes after scheduled time")
    print(f"Database: {DB_CONFIG['database']} on port {DB_CONFIG['port']}")
    print("=" * 80)
    print()

    # Connect to database
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return 1

    # Current status
    now = datetime.now()
    print(f"Current time: {now.strftime('%H:%M:%S')}")

    next_wave = get_next_wave_time()
    print(f"Next wave: {next_wave.strftime('%H:%M')} (in {format_time_until(next_wave)})")
    print()

    try:
        # Monitor 3 consecutive waves
        for i in range(3):
            wave_time = get_next_wave_time()

            # Monitor this wave
            new_positions = await monitor_wave(conn, wave_time, timeout_minutes=10)

            # If we got positions, consider test successful
            if new_positions:
                print(f"✅ Wave test successful! Detected {len(new_positions)} positions.")

                # Check if all have stop loss
                with_sl = sum(1 for p in new_positions if p['has_stop_loss'])
                sl_rate = with_sl / len(new_positions) * 100 if new_positions else 0

                if sl_rate >= 95:
                    print(f"✅ Stop Loss rate: {sl_rate:.1f}% (≥95%) - PASS")
                    break
                elif sl_rate >= 80:
                    print(f"⚠️  Stop Loss rate: {sl_rate:.1f}% (80-95%) - ACCEPTABLE")
                    break
                else:
                    print(f"❌ Stop Loss rate: {sl_rate:.1f}% (<80%) - FAIL")
                    print("   Continuing to next wave...")
            else:
                print(f"⚠️  No positions in wave {i+1}/3. Continuing to next wave...")

            # Wait a bit before next wave
            await asyncio.sleep(60)

        # Final summary
        print("\n" + "=" * 80)
        print("📊 FINAL SUMMARY")
        print("=" * 80)

        # Get all positions from test session
        all_positions = await get_recent_positions(conn, since_minutes=60)
        all_stats = await get_position_stats(conn, since_minutes=60)

        print(f"Total positions: {all_stats.get('total', 0)}")
        print(f"With Stop Loss: {all_stats.get('with_sl', 0)}/{all_stats.get('total', 0)}")

        if all_stats.get('total', 0) > 0:
            sl_rate = all_stats.get('with_sl', 0) / all_stats['total'] * 100

            if sl_rate >= 95:
                print(f"\n✅ TEST PASSED: {sl_rate:.1f}% Stop Loss coverage")
                return 0
            elif sl_rate >= 80:
                print(f"\n⚠️  TEST ACCEPTABLE: {sl_rate:.1f}% Stop Loss coverage")
                return 0
            else:
                print(f"\n❌ TEST FAILED: {sl_rate:.1f}% Stop Loss coverage (target: ≥95%)")
                return 1
        else:
            print("\n⚠️  NO POSITIONS DETECTED")
            print("Possible reasons:")
            print("  - No signals from WebSocket server")
            print("  - Bot not connected to signal source")
            return 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring interrupted by user")
        return 130

    finally:
        await conn.close()


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
