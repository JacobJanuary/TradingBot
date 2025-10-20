"""
Diagnostic script to investigate TS creation timeout root cause

CRITICAL P0 INVESTIGATION - DO NOT MODIFY PRODUCTION CODE

This script measures:
1. get_open_positions() timing with varying position counts
2. save_trailing_stop_state() timing
3. DB connection pool metrics
4. Alternative approach: direct position_id lookup
5. Concurrent TS creation performance

Goal: Find 100% root cause with data
"""
import asyncio
import time
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import statistics

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.repository import Repository
from config.settings import config

# Test data
TEST_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
    'MATICUSDT', 'LINKUSDT', 'UNIUSDT', 'LTCUSDT', 'AVAXUSDT'
]


async def measure_get_open_positions(repo: Repository, runs: int = 10):
    """Measure get_open_positions() performance"""
    print("\n" + "="*80)
    print("TEST 1: Measuring get_open_positions() timing")
    print("="*80)

    timings = []
    position_counts = []

    for i in range(runs):
        start = time.perf_counter()
        positions = await repo.get_open_positions()
        elapsed_ms = (time.perf_counter() - start) * 1000

        timings.append(elapsed_ms)
        position_counts.append(len(positions))

        print(f"Run {i+1}/{runs}: {elapsed_ms:.2f}ms, positions: {len(positions)}")
        await asyncio.sleep(0.1)  # Small delay between runs

    print(f"\n📊 Statistics:")
    print(f"  Positions count: {position_counts[0]} (avg: {statistics.mean(position_counts):.1f})")
    print(f"  Min time: {min(timings):.2f}ms")
    print(f"  Max time: {max(timings):.2f}ms")
    print(f"  Avg time: {statistics.mean(timings):.2f}ms")
    print(f"  Median time: {statistics.median(timings):.2f}ms")
    print(f"  Std dev: {statistics.stdev(timings):.2f}ms" if len(timings) > 1 else "")

    return {
        'avg_time_ms': statistics.mean(timings),
        'position_count': position_counts[0]
    }


async def measure_direct_lookup(repo: Repository, symbol: str, exchange: str, runs: int = 10):
    """Measure direct position lookup by symbol+exchange"""
    print("\n" + "="*80)
    print("TEST 2: Measuring direct position lookup (alternative approach)")
    print("="*80)

    # First, get a real position to test with
    positions = await repo.get_open_positions()
    if not positions:
        print("❌ No active positions to test with")
        return None

    test_pos = positions[0]
    symbol = test_pos['symbol']
    exchange = test_pos['exchange']

    print(f"Testing lookup for: {symbol} on {exchange}")

    timings = []

    for i in range(runs):
        start = time.perf_counter()

        # Simulate direct SQL query (what we SHOULD do instead)
        async with repo.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT id, symbol, exchange, side, entry_price, current_price,
                       quantity, leverage, stop_loss, take_profit,
                       status, pnl, pnl_percentage, trailing_activated,
                       has_trailing_stop, created_at, updated_at
                FROM monitoring.positions
                WHERE symbol = $1 AND exchange = $2 AND status = 'active'
                LIMIT 1
            """, symbol, exchange)

        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)

        print(f"Run {i+1}/{runs}: {elapsed_ms:.2f}ms, found: {result is not None}")
        await asyncio.sleep(0.1)

    print(f"\n📊 Statistics:")
    print(f"  Min time: {min(timings):.2f}ms")
    print(f"  Max time: {max(timings):.2f}ms")
    print(f"  Avg time: {statistics.mean(timings):.2f}ms")
    print(f"  Median time: {statistics.median(timings):.2f}ms")
    print(f"  Std dev: {statistics.stdev(timings):.2f}ms" if len(timings) > 1 else "")

    return {
        'avg_time_ms': statistics.mean(timings)
    }


async def measure_save_trailing_stop(repo: Repository, runs: int = 5):
    """Measure save_trailing_stop_state() performance"""
    print("\n" + "="*80)
    print("TEST 3: Measuring save_trailing_stop_state() timing")
    print("="*80)

    # Get a real position to create TS for
    positions = await repo.get_open_positions()
    if not positions:
        print("❌ No active positions to test with")
        return None

    test_pos = positions[0]

    timings = []

    for i in range(runs):
        start = time.perf_counter()

        # Create test TS state
        await repo.save_trailing_stop_state(
            position_id=test_pos['id'],
            symbol=test_pos['symbol'],
            exchange='bybit',  # Assuming exchange
            side=test_pos['side'],
            state='WAITING',
            activation_price=test_pos['entry_price'] * Decimal('1.015'),
            peak_price=test_pos['entry_price'],
            trailing_stop_price=None,
            callback_percent=Decimal('0.5'),
            last_update=datetime.now(timezone.utc),
            last_peak_save_time=datetime.now(timezone.utc),
            last_saved_peak_price=test_pos['entry_price']
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)

        print(f"Run {i+1}/{runs}: {elapsed_ms:.2f}ms")
        await asyncio.sleep(0.2)

    print(f"\n📊 Statistics:")
    print(f"  Min time: {min(timings):.2f}ms")
    print(f"  Max time: {max(timings):.2f}ms")
    print(f"  Avg time: {statistics.mean(timings):.2f}ms")
    print(f"  Median time: {statistics.median(timings):.2f}ms")

    return {
        'avg_time_ms': statistics.mean(timings)
    }


async def check_db_pool_metrics(repo: Repository):
    """Check DB connection pool status"""
    print("\n" + "="*80)
    print("TEST 4: DB Connection Pool Metrics")
    print("="*80)

    pool = repo.pool

    print(f"📊 Pool Configuration:")
    print(f"  Min size: {pool.get_min_size()}")
    print(f"  Max size: {pool.get_max_size()}")
    print(f"  Current size: {pool.get_size()}")
    print(f"  Free connections: {pool.get_idle_size()}")

    # Test concurrent connection acquisition
    print(f"\n🔄 Testing concurrent connection acquisition...")

    async def acquire_and_hold(duration: float):
        async with pool.acquire() as conn:
            await asyncio.sleep(duration)

    start = time.perf_counter()
    # Simulate 10 concurrent TS creations
    tasks = [acquire_and_hold(0.1) for _ in range(10)]
    await asyncio.gather(*tasks)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"  10 concurrent acquisitions: {elapsed_ms:.2f}ms")
    print(f"  Pool size after: {pool.get_size()}")
    print(f"  Free after: {pool.get_idle_size()}")

    return {
        'pool_size': pool.get_size(),
        'pool_max': pool.get_max_size(),
        'concurrent_10_time_ms': elapsed_ms
    }


async def simulate_wave_ts_creation(repo: Repository, position_count: int = 5):
    """Simulate creating TS for multiple positions concurrently (like during wave)"""
    print("\n" + "="*80)
    print(f"TEST 5: Simulating {position_count} concurrent TS creations (wave scenario)")
    print("="*80)

    positions = await repo.get_open_positions()
    if len(positions) < position_count:
        print(f"⚠️ Only {len(positions)} positions available, need {position_count}")
        position_count = len(positions)

    test_positions = positions[:position_count]

    async def create_ts_for_position(pos):
        """Simulate full TS creation flow"""
        start = time.perf_counter()

        # Step 1: get_open_positions (current bottleneck)
        step1_start = time.perf_counter()
        all_positions = await repo.get_open_positions()
        step1_ms = (time.perf_counter() - step1_start) * 1000

        # Step 2: Find position (O(N) search)
        step2_start = time.perf_counter()
        position_id = None
        for p in all_positions:
            if p['symbol'] == pos['symbol'] and p['exchange'] == pos.get('exchange', 'bybit'):
                position_id = p['id']
                break
        step2_ms = (time.perf_counter() - step2_start) * 1000

        # Step 3: Save TS state
        step3_start = time.perf_counter()
        if position_id:
            await repo.save_trailing_stop_state(
                position_id=position_id,
                symbol=pos['symbol'],
                exchange=pos.get('exchange', 'bybit'),
                side=pos['side'],
                state='WAITING',
                activation_price=pos['entry_price'] * Decimal('1.015'),
                peak_price=pos['entry_price'],
                trailing_stop_price=None,
                callback_percent=Decimal('0.5'),
                last_update=datetime.now(timezone.utc),
                last_peak_save_time=datetime.now(timezone.utc),
                last_saved_peak_price=pos['entry_price']
            )
        step3_ms = (time.perf_counter() - step3_start) * 1000

        total_ms = (time.perf_counter() - start) * 1000

        return {
            'symbol': pos['symbol'],
            'step1_get_positions_ms': step1_ms,
            'step2_find_position_ms': step2_ms,
            'step3_save_state_ms': step3_ms,
            'total_ms': total_ms
        }

    # Run concurrently (like during wave processing)
    start = time.perf_counter()
    results = await asyncio.gather(*[create_ts_for_position(pos) for pos in test_positions])
    total_elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\n📊 Results for {position_count} concurrent TS creations:")
    print(f"\n{'Symbol':<15} {'Get Pos':<10} {'Find':<10} {'Save':<10} {'Total':<10}")
    print("-" * 65)

    for r in results:
        print(f"{r['symbol']:<15} {r['step1_get_positions_ms']:>8.1f}ms {r['step2_find_position_ms']:>8.1f}ms {r['step3_save_state_ms']:>8.1f}ms {r['total_ms']:>8.1f}ms")

    # Statistics
    step1_times = [r['step1_get_positions_ms'] for r in results]
    step2_times = [r['step2_find_position_ms'] for r in results]
    step3_times = [r['step3_save_state_ms'] for r in results]
    total_times = [r['total_ms'] for r in results]

    print(f"\n📊 Aggregated Statistics:")
    print(f"  Step 1 (get_open_positions):")
    print(f"    Avg: {statistics.mean(step1_times):.1f}ms, Max: {max(step1_times):.1f}ms")
    print(f"  Step 2 (find position O(N)):")
    print(f"    Avg: {statistics.mean(step2_times):.1f}ms, Max: {max(step2_times):.1f}ms")
    print(f"  Step 3 (save_trailing_stop_state):")
    print(f"    Avg: {statistics.mean(step3_times):.1f}ms, Max: {max(step3_times):.1f}ms")
    print(f"  Total per TS:")
    print(f"    Avg: {statistics.mean(total_times):.1f}ms, Max: {max(total_times):.1f}ms")
    print(f"\n  Wall clock time (concurrent): {total_elapsed_ms:.1f}ms")
    print(f"  Sum of all TS creations: {sum(total_times):.1f}ms")

    return {
        'avg_step1_ms': statistics.mean(step1_times),
        'avg_step2_ms': statistics.mean(step2_times),
        'avg_step3_ms': statistics.mean(step3_times),
        'avg_total_ms': statistics.mean(total_times),
        'max_total_ms': max(total_times),
        'wall_clock_ms': total_elapsed_ms,
        'position_count': position_count
    }


async def main():
    print("🔍 TS Creation Timeout - Deep Diagnostic Analysis")
    print("=" * 80)
    print("Purpose: Find 100% root cause of 10+ second timeouts")
    print("=" * 80)

    # Initialize repository
    db_config = {
        'host': config.database.host,
        'port': config.database.port,
        'database': config.database.database,
        'user': config.database.user,
        'password': config.database.password,
        'pool_size': config.database.pool_size,
        'max_overflow': config.database.max_overflow
    }
    repo = Repository(db_config)

    try:
        await repo.initialize()
        print("✅ Connected to database")

        # Run all tests
        test1_result = await measure_get_open_positions(repo, runs=10)
        test2_result = await measure_direct_lookup(repo, 'BTCUSDT', 'bybit', runs=10)
        test3_result = await measure_save_trailing_stop(repo, runs=5)
        test4_result = await check_db_pool_metrics(repo)
        test5_result = await simulate_wave_ts_creation(repo, position_count=5)

        # Final analysis
        print("\n" + "="*80)
        print("🎯 FINAL ANALYSIS")
        print("="*80)

        if test1_result and test2_result:
            slowdown = test1_result['avg_time_ms'] / test2_result['avg_time_ms']
            print(f"\n⚠️ BOTTLENECK IDENTIFIED:")
            print(f"  get_open_positions() (current): {test1_result['avg_time_ms']:.2f}ms")
            print(f"  Direct lookup (alternative): {test2_result['avg_time_ms']:.2f}ms")
            print(f"  Slowdown factor: {slowdown:.1f}x")
            print(f"  With {test1_result['position_count']} positions in DB")

        if test5_result:
            print(f"\n🔥 WAVE SCENARIO (5 concurrent TS creations):")
            print(f"  Step 1 (get_open_positions) avg: {test5_result['avg_step1_ms']:.1f}ms")
            print(f"  Step 3 (save_state) avg: {test5_result['avg_step3_ms']:.1f}ms")
            print(f"  Total per TS avg: {test5_result['avg_total_ms']:.1f}ms")
            print(f"  Max TS creation time: {test5_result['max_total_ms']:.1f}ms")

            if test5_result['max_total_ms'] > 10000:
                print(f"\n  ❌ TIMEOUT CONFIRMED: Max time {test5_result['max_total_ms']:.1f}ms > 10000ms threshold")
            else:
                print(f"\n  ⚠️ Below timeout threshold, but may timeout with more concurrent operations")

        print("\n" + "="*80)
        print("💡 CONCLUSION")
        print("="*80)
        print("ROOT CAUSE: get_open_positions() fetches ALL positions for each TS creation")
        print("IMPACT: O(N) complexity - time increases linearly with position count")
        print("SOLUTION: Use direct SQL lookup by symbol+exchange (O(1) with index)")
        print("="*80)

    finally:
        await repo.close()
        print("\n✅ Disconnected from database")


if __name__ == '__main__':
    asyncio.run(main())
