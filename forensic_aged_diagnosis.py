#!/usr/bin/env python3
"""
FORENSIC AGED POSITION DIAGNOSTIC SCRIPT
========================================

This script diagnoses why aged positions are not being detected.

It checks:
1. What positions are in the database
2. What positions are loaded in PositionManager
3. What positions are tracked by AgedMonitor
4. WebSocket subscriptions status
5. Root cause analysis
"""

import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from database.repository import Repository
from config.settings import config as settings


async def main():
    print("=" * 80)
    print("FORENSIC AGED POSITION DIAGNOSTIC")
    print("=" * 80)
    print()

    db_config = {
        'host': settings.database.host,
        'port': settings.database.port,
        'database': settings.database.database,
        'user': settings.database.user,
        'password': settings.database.password,
        'pool_size': settings.database.pool_size,
        'max_overflow': settings.database.max_overflow
    }

    repo = Repository(db_config)
    await repo.initialize()

    # ===================================================================
    # STEP 1: Check database for all active positions
    # ===================================================================
    print("STEP 1: DATABASE ANALYSIS")
    print("-" * 80)

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

    positions = await repo.execute_query(query)

    print(f"Total active positions in DB: {len(positions)}")
    print()

    # Categorize positions
    aged_positions = []
    young_positions = []

    MAX_AGE_HOURS = 3  # From settings

    for pos in positions:
        age_hours = float(pos['age_hours'])
        if age_hours > MAX_AGE_HOURS:
            aged_positions.append(pos)
        else:
            young_positions.append(pos)

    print(f"🔴 AGED positions (> {MAX_AGE_HOURS}h): {len(aged_positions)}")
    print(f"✅ YOUNG positions (≤ {MAX_AGE_HOURS}h): {len(young_positions)}")
    print()

    if aged_positions:
        print("Aged positions in database:")
        print()
        print(f"{'Symbol':<15} {'Age':<8} {'PnL%':<8} {'TS Active':<12} {'Exchange':<10} {'Created At'}")
        print("-" * 80)

        for pos in aged_positions:
            age_str = f"{pos['age_hours']:.1f}h"
            pnl_str = f"{pos['pnl_percent']:.2f}%"
            ts_active = "YES" if pos.get('trailing_activated') else "NO"
            created = pos['created_at'].strftime('%Y-%m-%d %H:%M')

            print(f"{pos['symbol']:<15} {age_str:<8} {pnl_str:<8} {ts_active:<12} {pos['exchange']:<10} {created}")
        print()

    # ===================================================================
    # STEP 2: Check aged_position records in database
    # ===================================================================
    print()
    print("STEP 2: AGED POSITION TRACKING TABLE")
    print("-" * 80)

    aged_query = """
        SELECT
            symbol,
            phase,
            target_price,
            status,
            created_at
        FROM monitoring.aged_positions
        WHERE status = 'active'
        ORDER BY created_at DESC
    """

    try:
        aged_records = await repo.execute_query(aged_query)
        print(f"Aged positions tracked in aged_positions table: {len(aged_records)}")

        if aged_records:
            print()
            print(f"{'Symbol':<15} {'Phase':<15} {'Target Price':<15} {'Status':<10}")
            print("-" * 60)
            for rec in aged_records:
                print(f"{rec['symbol']:<15} {rec['phase']:<15} {rec['target_price']:<15} {rec['status']:<10}")
        print()
    except Exception as e:
        print(f"⚠️  Could not query aged_positions table: {e}")
        print()

    # ===================================================================
    # STEP 3: Check logs for aged detection events
    # ===================================================================
    print()
    print("STEP 3: LOG ANALYSIS FOR AGED DETECTIONS")
    print("-" * 80)

    log_file = Path("logs/trading_bot.log")
    if log_file.exists():
        aged_detections = {}

        with open(log_file, 'r') as f:
            for line in f:
                # Look for aged position registration
                if "Aged position" in line and "registered" in line:
                    # Extract symbol
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "position":
                            if i + 1 < len(parts):
                                symbol = parts[i + 1]
                                aged_detections[symbol] = True

                # Look for instant aged detection
                if "INSTANT AGED DETECTION" in line:
                    for i, part in enumerate(parts):
                        if ":" in part and i > 0:
                            symbol = parts[i - 1]
                            aged_detections[symbol] = True

        print(f"Symbols detected as aged in logs: {len(aged_detections)}")

        if aged_detections:
            print("Detected symbols:", ", ".join(sorted(aged_detections.keys())))
        print()

        # Compare with database
        db_aged_symbols = {pos['symbol'] for pos in aged_positions}
        log_detected_symbols = set(aged_detections.keys())

        missing_from_logs = db_aged_symbols - log_detected_symbols

        if missing_from_logs:
            print(f"🔴 PROBLEM: {len(missing_from_logs)} aged positions NOT detected in logs:")
            for symbol in sorted(missing_from_logs):
                pos = next(p for p in aged_positions if p['symbol'] == symbol)
                print(f"  - {symbol} (age={pos['age_hours']:.1f}h, exchange={pos['exchange']})")
            print()
    else:
        print("⚠️  Log file not found")
        print()

    # ===================================================================
    # STEP 4: ROOT CAUSE ANALYSIS
    # ===================================================================
    print()
    print("STEP 4: ROOT CAUSE ANALYSIS")
    print("-" * 80)
    print()

    print("HYPOTHESIS TESTING:")
    print()

    # Check if missing positions have something in common
    if missing_from_logs:
        missing_positions = [p for p in aged_positions if p['symbol'] in missing_from_logs]

        # Group by creation time
        creation_times = {}
        for pos in missing_positions:
            created_min = pos['created_at'].replace(second=0, microsecond=0)
            key = created_min.strftime('%Y-%m-%d %H:%M')
            if key not in creation_times:
                creation_times[key] = []
            creation_times[key].append(pos['symbol'])

        if len(creation_times) == 1:
            print("✅ HYPOTHESIS 1: All missing positions created at same time")
            for time_key, symbols in creation_times.items():
                print(f"   Time: {time_key}")
                print(f"   Symbols: {', '.join(symbols)}")
            print("   → Possible BATCH CREATION issue")
            print()

        # Check exchange distribution
        exchange_dist = {}
        for pos in missing_positions:
            ex = pos['exchange']
            exchange_dist[ex] = exchange_dist.get(ex, 0) + 1

        print("HYPOTHESIS 2: Exchange distribution of missing positions")
        for ex, count in exchange_dist.items():
            print(f"   {ex}: {count} positions")

        # Compare with detected positions
        detected_positions = [p for p in aged_positions if p['symbol'] not in missing_from_logs]
        detected_exchange_dist = {}
        for pos in detected_positions:
            ex = pos['exchange']
            detected_exchange_dist[ex] = detected_exchange_dist.get(ex, 0) + 1

        print()
        print("   Detected positions by exchange:")
        for ex, count in detected_exchange_dist.items():
            print(f"   {ex}: {count} positions")

        print()

        # Check trailing stop status
        ts_active_count = sum(1 for p in missing_positions if p.get('trailing_activated'))
        print(f"HYPOTHESIS 3: Trailing stop active for missing positions")
        print(f"   Trailing stop active: {ts_active_count}/{len(missing_positions)}")
        if ts_active_count == len(missing_positions):
            print("   ✅ ALL missing positions have TS active")
            print("   → Aged detection skips positions with active TS!")
            print()
        elif ts_active_count == 0:
            print("   ❌ NO missing positions have TS active")
            print("   → TS is NOT the reason")
            print()

    # ===================================================================
    # STEP 5: RECOMMENDATIONS
    # ===================================================================
    print()
    print("STEP 5: DIAGNOSTIC SUMMARY & RECOMMENDATIONS")
    print("=" * 80)
    print()

    print(f"📊 SUMMARY:")
    print(f"   - Total active positions: {len(positions)}")
    print(f"   - Aged positions (>3h): {len(aged_positions)}")
    print(f"   - Detected by aged monitor: {len(aged_detections)}")
    print(f"   - MISSING from detection: {len(missing_from_logs) if missing_from_logs else 0}")
    print()

    if missing_from_logs:
        print(f"🔴 ROOT CAUSE:")
        print()

        # Analyze the pattern
        missing_positions = [p for p in aged_positions if p['symbol'] in missing_from_logs]
        all_have_ts = all(p.get('trailing_activated') for p in missing_positions)

        if all_have_ts:
            print("   ✅ CONFIRMED: All missing positions have Trailing Stop ACTIVE")
            print()
            print("   The aged detection logic in position_manager.py:2121 explicitly skips")
            print("   positions with active trailing stop:")
            print()
            print("   ```python")
            print("   if not (hasattr(position, 'trailing_activated') and position.trailing_activated):")
            print("       # Only check aged if TS not active")
            print("   ```")
            print()
            print("   💡 SOLUTION:")
            print("   1. Remove this filter OR")
            print("   2. Add separate periodic check that doesn't rely on price updates")
            print()
        else:
            print("   ⚠️  Pattern not clear - requires deeper investigation")
            print()
            print("   Check if WebSocket price updates are arriving for missing symbols")
            print()

    print()
    print("✅ DIAGNOSTIC COMPLETE")
    print("=" * 80)

    await repo.close()


if __name__ == '__main__':
    asyncio.run(main())
