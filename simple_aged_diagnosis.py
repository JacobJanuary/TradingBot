#!/usr/bin/env python3
"""
SIMPLIFIED FORENSIC AGED POSITION DIAGNOSTIC
Directly queries PostgreSQL and analyzes logs
"""

import asyncio
import asyncpg
from datetime import datetime
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

async def main():
    print("=" * 80)
    print("FORENSIC AGED POSITION DIAGNOSTIC")
    print("=" * 80)
    print()

    # Connect to PostgreSQL
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'fox_crypto'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD', '')
    )

    print("STEP 1: DATABASE ANALYSIS")
    print("-" * 80)

    # Query active positions
    query = """
        SELECT
            symbol,
            side,
            status,
            entry_price,
            current_price,
            pnl_percentage as pnl_percent,
            created_at,
            exchange,
            trailing_activated,
            EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600 as age_hours
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY created_at ASC
    """

    positions = await conn.fetch(query)
    print(f"Total active positions: {len(positions)}")
    print()

    # Categorize
    MAX_AGE_HOURS = 3
    aged_positions = [p for p in positions if p['age_hours'] > MAX_AGE_HOURS]
    young_positions = [p for p in positions if p['age_hours'] <= MAX_AGE_HOURS]

    print(f"🔴 AGED positions (> {MAX_AGE_HOURS}h): {len(aged_positions)}")
    print(f"✅ YOUNG positions (≤ {MAX_AGE_HOURS}h): {len(young_positions)}")
    print()

    if aged_positions:
        print("Aged positions in database:")
        print()
        print(f"{'Symbol':<15} {'Age':<8} {'PnL%':<8} {'TS':<5} {'Exchange':<10} {'Created'}")
        print("-" * 70)

        for p in aged_positions:
            age_str = f"{p['age_hours']:.1f}h"
            pnl_str = f"{p['pnl_percent']:.2f}%" if p['pnl_percent'] else "0.00%"
            ts = "YES" if p['trailing_activated'] else "NO"
            created = p['created_at'].strftime('%m-%d %H:%M')

            print(f"{p['symbol']:<15} {age_str:<8} {pnl_str:<8} {ts:<5} {p['exchange']:<10} {created}")
        print()

    # Check aged_positions table
    print()
    print("STEP 2: AGED TRACKING TABLE")
    print("-" * 80)

    try:
        aged_records = await conn.fetch("""
            SELECT symbol, phase, status, created_at
            FROM public.aged_positions
            WHERE status = 'active'
            ORDER BY created_at DESC
        """)

        print(f"Tracked in aged_positions table: {len(aged_records)}")

        if aged_records:
            tracked_symbols = {rec['symbol'] for rec in aged_records}
            print("Tracked symbols:", ", ".join(sorted(tracked_symbols)))
        print()
    except Exception as e:
        print(f"Could not query aged_positions: {e}")
        print()

    # Analyze logs
    print()
    print("STEP 3: LOG ANALYSIS")
    print("-" * 80)

    log_file = Path("logs/trading_bot.log")
    if log_file.exists():
        aged_detections = set()

        with open(log_file, 'r') as f:
            for line in f:
                # Look for aged position registration
                if "Aged position" in line and "registered" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "position" and i + 1 < len(parts):
                            symbol = parts[i + 1]
                            aged_detections.add(symbol)

                # Look for instant aged detection
                if "INSTANT AGED DETECTION" in line:
                    if ":" in line:
                        # Extract symbol after "DETECTION:"
                        symbol_part = line.split("DETECTION:")[1].split()[0]
                        aged_detections.add(symbol_part)

        print(f"Detected in logs: {len(aged_detections)} symbols")

        if aged_detections:
            print("Detected:", ", ".join(sorted(aged_detections)))
        print()

        # Compare
        db_aged_symbols = {p['symbol'] for p in aged_positions}
        missing_from_logs = db_aged_symbols - aged_detections

        if missing_from_logs:
            print(f"🔴 NOT DETECTED: {len(missing_from_logs)} positions")
            print()

            missing_positions = [p for p in aged_positions if p['symbol'] in missing_from_logs]

            print(f"{'Symbol':<15} {'Age':<8} {'TS Active':<12} {'Exchange':<10}")
            print("-" * 55)
            for p in missing_positions:
                age_str = f"{p['age_hours']:.1f}h"
                ts = "YES" if p['trailing_activated'] else "NO"
                print(f"{p['symbol']:<15} {age_str:<8} {ts:<12} {p['exchange']:<10}")
            print()

    # ROOT CAUSE ANALYSIS
    print()
    print("STEP 4: ROOT CAUSE ANALYSIS")
    print("=" * 80)
    print()

    if missing_from_logs:
        missing_positions = [p for p in aged_positions if p['symbol'] in missing_from_logs]

        # Check if all have TS active
        ts_active_count = sum(1 for p in missing_positions if p['trailing_activated'])
        ts_inactive_count = len(missing_positions) - ts_active_count

        print(f"Missing positions with TS ACTIVE: {ts_active_count}")
        print(f"Missing positions with TS INACTIVE: {ts_inactive_count}")
        print()

        if ts_active_count == len(missing_positions):
            print("✅ ROOT CAUSE FOUND!")
            print()
            print("ALL missing positions have Trailing Stop ACTIVE.")
            print()
            print("The aged detection code at position_manager.py:2121 explicitly")
            print("skips positions with active trailing stop:")
            print()
            print("```python")
            print("if not (hasattr(position, 'trailing_activated') and position.trailing_activated):")
            print("    # Only check aged if TS not active")
            print("    age_hours = self._calculate_position_age_hours(position)")
            print("    if age_hours > self.max_position_age_hours:")
            print("        # Add to aged monitoring")
            print("```")
            print()
            print("💡 IMPACT:")
            print("   Positions with active TS are NEVER checked for age,")
            print("   even if they are stuck for many hours.")
            print()
            print("💡 SOLUTION:")
            print("   Remove the trailing_activated filter OR add separate")
            print("   periodic check that runs independently of price updates.")
            print()

        # Check if created at same time
        creation_times = {}
        for p in missing_positions:
            created_min = p['created_at'].replace(second=0, microsecond=0)
            key = created_min.strftime('%Y-%m-%d %H:%M')
            if key not in creation_times:
                creation_times[key] = []
            creation_times[key].append(p['symbol'])

        if len(creation_times) == 1:
            print("📊 ADDITIONAL FINDING:")
            print()
            print(f"   All {len(missing_positions)} missing positions were created")
            print("   at the same time (batch creation):")
            for time_key, symbols in creation_times.items():
                print(f"   Time: {time_key}")
                print(f"   Count: {len(symbols)}")
            print()

    else:
        print("✅ No missing positions - aged detection working correctly")
        print()

    print("=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
