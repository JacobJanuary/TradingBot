#!/usr/bin/env python3
"""
Test wave detection logic and database queries
"""
import asyncio
import asyncpg
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


async def test_wave_detection():
    """Test wave detection and timestamp logic"""

    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5433)),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

    print("=" * 60)
    print("WAVE DETECTION TIMING TEST")
    print("=" * 60)

    # Test wave check minutes logic from environment
    wave_minutes_str = os.getenv('WAVE_CHECK_MINUTES', '4,18,33,48')
    wave_check_minutes = [int(m.strip()) for m in wave_minutes_str.split(',')]
    now = datetime.now()
    current_minute = now.minute

    print(f"\nCurrent time: {now.strftime('%H:%M:%S')}")
    print(f"Current minute: {current_minute}")

    # Find next check minute
    next_check_minute = None
    for check_minute in wave_check_minutes:
        if current_minute < check_minute:
            next_check_minute = check_minute
            break

    if next_check_minute is None:
        next_check_minute = wave_check_minutes[0]
        next_check_time = now.replace(minute=next_check_minute, second=0, microsecond=0)
        next_check_time += timedelta(hours=1)
    else:
        next_check_time = now.replace(minute=next_check_minute, second=0, microsecond=0)

    wait_seconds = (next_check_time - now).total_seconds()
    print(f"\nNext wave check at: {next_check_time.strftime('%H:%M')}")
    print(f"Wait time: {wait_seconds:.0f} seconds")

    # Test wave timestamp calculation
    print("\n" + "=" * 60)
    print("WAVE TIMESTAMP CALCULATION")
    print("=" * 60)

    test_times = [
        datetime.now().replace(hour=10, minute=4, second=0),
        datetime.now().replace(hour=10, minute=18, second=0),
        datetime.now().replace(hour=10, minute=33, second=0),
        datetime.now().replace(hour=10, minute=48, second=0),
    ]

    for test_time in test_times:
        current_minute = test_time.minute

        # Calculate expected wave timestamp
        if current_minute in [4, 5, 6]:
            wave_minute = 45
            wave_time = test_time.replace(minute=wave_minute, second=0, microsecond=0) - timedelta(hours=1)
        elif current_minute in [18, 19, 20]:
            wave_minute = 0
            wave_time = test_time.replace(minute=wave_minute, second=0, microsecond=0)
        elif current_minute in [33, 34, 35]:
            wave_minute = 15
            wave_time = test_time.replace(minute=wave_minute, second=0, microsecond=0)
        elif current_minute in [48, 49, 50]:
            wave_minute = 30
            wave_time = test_time.replace(minute=wave_minute, second=0, microsecond=0)
        else:
            wave_time = None

        if wave_time:
            print(f"\nCheck time: {test_time.strftime('%H:%M')} -> Wave timestamp: {wave_time.strftime('%H:%M')}")

    # Query database for recent signals grouped by timestamp
    print("\n" + "=" * 60)
    print("DATABASE WAVE ANALYSIS")
    print("=" * 60)

    query = """
        SELECT
            timestamp,
            COUNT(*) as signal_count,
            MIN(created_at) as first_created,
            MAX(created_at) as last_created,
            EXTRACT(EPOCH FROM (MAX(created_at) - timestamp)) / 60 as delay_minutes,
            MIN(score_week) as min_week,
            MAX(score_week) as max_week,
            MIN(score_month) as min_month,
            MAX(score_month) as max_month
        FROM fas.scoring_history
        WHERE created_at > NOW() - INTERVAL '3 hours'
            AND score_week >= 50
            AND score_month >= 50
            AND is_active = true
            AND recommended_action IN ('BUY', 'SELL', 'LONG', 'SHORT')
        GROUP BY timestamp
        ORDER BY timestamp DESC
        LIMIT 20;
    """

    results = await conn.fetch(query)

    if results:
        print(f"\nFound {len(results)} waves in last 3 hours:")
        for row in results:
            timestamp = row['timestamp']
            signal_count = row['signal_count']
            delay = row['delay_minutes']
            first_created = row['first_created']
            last_created = row['last_created']

            print(f"\n📊 Wave: {timestamp.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Signals: {signal_count}")
            print(f"   Delay: ~{delay:.1f} minutes after candle close")
            print(f"   First signal: {first_created.strftime('%H:%M:%S')}")
            print(f"   Last signal: {last_created.strftime('%H:%M:%S')}")
            print(f"   Scores: Week({row['min_week']:.0f}-{row['max_week']:.0f}), Month({row['min_month']:.0f}-{row['max_month']:.0f})")

            # Check when we should detect this wave
            wave_minute = timestamp.minute
            if wave_minute == 0:
                check_minute = 4
            elif wave_minute == 15:
                check_minute = 18 if timestamp.hour == first_created.hour else 19
            elif wave_minute == 30:
                check_minute = 33 if timestamp.hour == first_created.hour else 34
            elif wave_minute == 45:
                check_minute = 48 if timestamp.hour == first_created.hour else 49
            else:
                check_minute = "?"

            print(f"   ⏰ Should check at: :{check_minute:02d}")
    else:
        print("No signals found in last 3 hours")

    # Check current/upcoming wave
    print("\n" + "=" * 60)
    print("CURRENT/UPCOMING WAVE CHECK")
    print("=" * 60)

    # Calculate current 15-minute candle
    now = datetime.now()
    current_candle_minute = (now.minute // 15) * 15
    current_candle = now.replace(minute=current_candle_minute, second=0, microsecond=0)

    print(f"\nCurrent 15-min candle: {current_candle.strftime('%H:%M')}")

    # Check if signals exist for current candle
    check_query = """
        SELECT COUNT(*) as count
        FROM fas.scoring_history
        WHERE timestamp = $1
            AND score_week >= 50
            AND score_month >= 50
            AND is_active = true
            AND recommended_action IN ('BUY', 'SELL', 'LONG', 'SHORT');
    """

    result = await conn.fetchrow(check_query, current_candle)
    if result['count'] > 0:
        print(f"✅ {result['count']} signals available for current candle")
    else:
        print(f"⏳ No signals yet for current candle (will appear ~4 minutes after {current_candle.strftime('%H:%M')})")

    # Check previous candle
    prev_candle = current_candle - timedelta(minutes=15)
    result = await conn.fetchrow(check_query, prev_candle)
    if result['count'] > 0:
        print(f"📊 {result['count']} signals from previous candle ({prev_candle.strftime('%H:%M')})")

    await conn.close()

    print("\n" + "=" * 60)
    print("✅ Wave detection test complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_wave_detection())