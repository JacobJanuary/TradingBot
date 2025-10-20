"""
CRITICAL DIAGNOSTIC: Test if TrailingManager.lock is causing serialization

THEORY: async with self.lock in create_trailing_stop() forces sequential execution
        even when called concurrently during wave processing

This would explain 10s+ timeouts:
- 5 positions created during wave
- Each waits for lock
- Total time = sum(individual times)
"""
import asyncio
import time
from decimal import Decimal
from datetime import datetime

class MockLockTest:
    """Simulate TrailingManager with lock"""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.counter = 0

    async def simulate_create_ts_with_lock(self, symbol: str, delay_ms: float):
        """Simulate create_trailing_stop() WITH lock (current implementation)"""
        start = time.perf_counter()

        async with self.lock:  # THIS IS THE PROBLEM!
            # Simulate work inside lock
            await asyncio.sleep(delay_ms / 1000)
            self.counter += 1

        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            'symbol': symbol,
            'elapsed_ms': elapsed_ms,
            'delay_ms': delay_ms
        }

    async def simulate_create_ts_without_lock(self, symbol: str, delay_ms: float):
        """Simulate create_trailing_stop() WITHOUT lock (proposed fix)"""
        start = time.perf_counter()

        # Work done without global lock (only lock specific symbol if needed)
        await asyncio.sleep(delay_ms / 1000)
        self.counter += 1

        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            'symbol': symbol,
            'elapsed_ms': elapsed_ms,
            'delay_ms': delay_ms
        }


async def test_with_lock(count: int = 5, delay_per_ts_ms: float = 2000):
    """Test concurrent TS creation WITH global lock"""
    print("\n" + "="*80)
    print(f"TEST 1: Concurrent TS creation WITH lock ({count} positions)")
    print(f"Each TS takes {delay_per_ts_ms}ms to create")
    print("="*80)

    manager = MockLockTest()

    start_total = time.perf_counter()

    # Create concurrently (like during wave)
    tasks = [
        manager.simulate_create_ts_with_lock(f"SYMBOL{i}USDT", delay_per_ts_ms)
        for i in range(count)
    ]
    results = await asyncio.gather(*tasks)

    total_wall_clock_ms = (time.perf_counter() - start_total) * 1000

    print(f"\n📊 Results:")
    for r in results:
        print(f"  {r['symbol']:<15} Elapsed: {r['elapsed_ms']:>7.1f}ms (work: {r['delay_ms']:.1f}ms)")

    print(f"\n📊 Summary:")
    print(f"  Wall clock time: {total_wall_clock_ms:.1f}ms")
    print(f"  Expected (if parallel): {delay_per_ts_ms:.1f}ms")
    print(f"  Expected (if serial): {delay_per_ts_ms * count:.1f}ms")
    print(f"  Slowdown: {total_wall_clock_ms / delay_per_ts_ms:.1f}x")

    if total_wall_clock_ms > delay_per_ts_ms * count * 0.9:
        print(f"\n  ❌ SERIALIZATION DETECTED: Operations ran sequentially due to lock!")
    else:
        print(f"\n  ✅ Operations ran in parallel")

    return total_wall_clock_ms


async def test_without_lock(count: int = 5, delay_per_ts_ms: float = 2000):
    """Test concurrent TS creation WITHOUT global lock"""
    print("\n" + "="*80)
    print(f"TEST 2: Concurrent TS creation WITHOUT lock ({count} positions)")
    print(f"Each TS takes {delay_per_ts_ms}ms to create")
    print("="*80)

    manager = MockLockTest()

    start_total = time.perf_counter()

    # Create concurrently (like during wave)
    tasks = [
        manager.simulate_create_ts_without_lock(f"SYMBOL{i}USDT", delay_per_ts_ms)
        for i in range(count)
    ]
    results = await asyncio.gather(*tasks)

    total_wall_clock_ms = (time.perf_counter() - start_total) * 1000

    print(f"\n📊 Results:")
    for r in results:
        print(f"  {r['symbol']:<15} Elapsed: {r['elapsed_ms']:>7.1f}ms (work: {r['delay_ms']:.1f}ms)")

    print(f"\n📊 Summary:")
    print(f"  Wall clock time: {total_wall_clock_ms:.1f}ms")
    print(f"  Expected (if parallel): {delay_per_ts_ms:.1f}ms")
    print(f"  Expected (if serial): {delay_per_ts_ms * count:.1f}ms")
    print(f"  Speedup vs serial: {(delay_per_ts_ms * count) / total_wall_clock_ms:.1f}x")

    if total_wall_clock_ms < delay_per_ts_ms * 1.5:
        print(f"\n  ✅ TRUE PARALLELISM: All operations ran concurrently!")
    else:
        print(f"\n  ⚠️ Some serialization detected")

    return total_wall_clock_ms


async def test_realistic_wave_scenario():
    """
    Test realistic wave scenario:
    - 5 signals in wave
    - Each position takes 2000ms to create TS (based on timeout setting)
    """
    print("\n" + "="*80)
    print("🔥 REALISTIC WAVE SCENARIO")
    print("="*80)
    print("Simulating wave with 5 positions")
    print("Each TS creation takes 2000ms (realistic for slow DB/network)")
    print("="*80)

    with_lock_time = await test_with_lock(count=5, delay_per_ts_ms=2000)
    without_lock_time = await test_without_lock(count=5, delay_per_ts_ms=2000)

    print("\n" + "="*80)
    print("🎯 WAVE SCENARIO COMPARISON")
    print("="*80)
    print(f"WITH lock (current): {with_lock_time:.1f}ms")
    print(f"WITHOUT lock (proposed): {without_lock_time:.1f}ms")
    print(f"Improvement: {with_lock_time / without_lock_time:.1f}x faster")

    timeout_threshold = 10000  # 10s
    if with_lock_time > timeout_threshold:
        print(f"\n❌ WITH LOCK: Would trigger timeout ({with_lock_time:.1f}ms > {timeout_threshold}ms)")
    else:
        print(f"\n✅ WITH LOCK: Below timeout threshold")

    if without_lock_time > timeout_threshold:
        print(f"❌ WITHOUT LOCK: Would still timeout ({without_lock_time:.1f}ms > {timeout_threshold}ms)")
    else:
        print(f"✅ WITHOUT LOCK: Below timeout threshold")


async def main():
    print("🔍 TS Lock Contention Diagnostic")
    print("="*80)
    print("Testing if global lock in create_trailing_stop() causes serialization")
    print("="*80)

    # First, quick test with minimal delay
    print("\n--- Quick Test (100ms per TS) ---")
    await test_with_lock(count=5, delay_per_ts_ms=100)
    await test_without_lock(count=5, delay_per_ts_ms=100)

    # Now realistic scenario
    await test_realistic_wave_scenario()

    print("\n" + "="*80)
    print("💡 CONCLUSION")
    print("="*80)
    print("If WITH lock time ≈ (delay × count), then lock causes SERIALIZATION")
    print("This means concurrent TS creation during wave becomes SEQUENTIAL")
    print("With 5 positions × 2s each = 10s total → TIMEOUT!")
    print("="*80)


if __name__ == '__main__':
    asyncio.run(main())
