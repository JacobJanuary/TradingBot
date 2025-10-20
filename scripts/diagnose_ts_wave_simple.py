"""
Simplified diagnostic: Measure concurrent TS creation during wave processing

FOCUS: Why does create_trailing_stop() timeout during wave?
"""
import asyncio
import time
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.repository import Repository
from config.settings import config
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def simulate_create_trailing_stop(repo: Repository, symbol: str, exchange: str):
    """
    Simulate what happens in trailing_manager.create_trailing_stop()
    Focus on the _save_state() bottleneck
    """
    start_total = time.perf_counter()

    # STEP 1: Get ALL open positions (current bottleneck?)
    step1_start = time.perf_counter()
    positions = await repo.get_open_positions()
    step1_ms = (time.perf_counter() - step1_start) * 1000

    # STEP 2: Find position_id (O(N) search)
    step2_start = time.perf_counter()
    position_id = None
    for pos in positions:
        if pos['symbol'] == symbol and pos.get('exchange', 'binance') == exchange:
            position_id = pos['id']
            break
    step2_ms = (time.perf_counter() - step2_start) * 1000

    if not position_id:
        logger.error(f"Position not found for {symbol}")
        return None

    # STEP 3: Save TS state to DB
    step3_start = time.perf_counter()

    # Build state_data dict as done in trailing_stop.py
    state_data = {
        'symbol': symbol,
        'exchange': exchange,
        'position_id': position_id,
        'state': 'WAITING',
        'is_activated': False,
        'highest_price': Decimal('100.0'),
        'lowest_price': None,
        'current_stop_price': None,
        'stop_order_id': None,
        'activation_price': Decimal('101.5'),
        'activation_percent': Decimal('1.5'),
        'callback_percent': Decimal('0.5'),
        'entry_price': Decimal('100.0'),
        'side': 'LONG',
        'quantity': Decimal('10.0'),
        'update_count': 0,
        'highest_profit_percent': Decimal('0.0'),
        'activated_at': None,
        'last_update_time': datetime.now(timezone.utc),
        'last_sl_update_time': None,
        'last_updated_sl_price': None,
        'last_peak_save_time': datetime.now(timezone.utc),
        'last_saved_peak_price': Decimal('100.0'),
        'created_at': datetime.now(timezone.utc)
    }

    success = await repo.save_trailing_stop_state(state_data)
    step3_ms = (time.perf_counter() - step3_start) * 1000

    total_ms = (time.perf_counter() - start_total) * 1000

    return {
        'symbol': symbol,
        'step1_get_positions_ms': step1_ms,
        'step1_position_count': len(positions),
        'step2_find_ms': step2_ms,
        'step3_save_ms': step3_ms,
        'total_ms': total_ms,
        'success': success
    }


async def test_sequential(repo: Repository, count: int = 5):
    """Test sequential TS creation (baseline)"""
    print("\n" + "="*80)
    print(f"TEST 1: Sequential TS creation ({count} positions)")
    print("="*80)

    positions = await repo.get_open_positions()
    test_positions = positions[:count]

    results = []
    start_total = time.perf_counter()

    for pos in test_positions:
        result = await simulate_create_trailing_stop(
            repo,
            pos['symbol'],
            pos.get('exchange', 'binance')
        )
        if result:
            results.append(result)
            print(f"  {result['symbol']:<15} Total: {result['total_ms']:>6.1f}ms (get:{result['step1_get_positions_ms']:>5.1f}ms, save:{result['step3_save_ms']:>5.1f}ms)")

    total_wall_clock_ms = (time.perf_counter() - start_total) * 1000

    print(f"\n📊 Sequential Results:")
    print(f"  Wall clock time: {total_wall_clock_ms:.1f}ms")
    print(f"  Average per TS: {sum(r['total_ms'] for r in results) / len(results):.1f}ms")

    return results


async def test_concurrent(repo: Repository, count: int = 5):
    """Test concurrent TS creation (wave scenario)"""
    print("\n" + "="*80)
    print(f"TEST 2: Concurrent TS creation ({count} positions) - WAVE SIMULATION")
    print("="*80)

    positions = await repo.get_open_positions()
    test_positions = positions[:count]

    start_total = time.perf_counter()

    # Create all TS concurrently (like during wave processing)
    tasks = [
        simulate_create_trailing_stop(repo, pos['symbol'], pos.get('exchange', 'binance'))
        for pos in test_positions
    ]
    results = await asyncio.gather(*tasks)
    results = [r for r in results if r is not None]

    total_wall_clock_ms = (time.perf_counter() - start_total) * 1000

    print(f"\n📊 Results:")
    for r in results:
        print(f"  {r['symbol']:<15} Total: {r['total_ms']:>6.1f}ms (get:{r['step1_get_positions_ms']:>5.1f}ms @ {r['step1_position_count']} pos, save:{r['step3_save_ms']:>5.1f}ms)")

    print(f"\n📊 Concurrent Results:")
    print(f"  Wall clock time: {total_wall_clock_ms:.1f}ms")
    print(f"  Average per TS: {sum(r['total_ms'] for r in results) / len(results):.1f}ms")
    print(f"  Max TS time: {max(r['total_ms'] for r in results):.1f}ms")
    print(f"  Sum of all: {sum(r['total_ms'] for r in results):.1f}ms")

    # Check if any would timeout
    timeout_threshold_ms = 10000
    timeouts = [r for r in results if r['total_ms'] > timeout_threshold_ms]
    if timeouts:
        print(f"\n  ❌ TIMEOUT DETECTED: {len(timeouts)} TS creations exceeded 10s threshold")
        for r in timeouts:
            print(f"     {r['symbol']}: {r['total_ms']:.1f}ms")
    else:
        print(f"\n  ✅ No timeouts (max: {max(r['total_ms'] for r in results):.1f}ms < {timeout_threshold_ms}ms)")

    return results


async def test_db_lock_contention(repo: Repository):
    """Test if DB locks are causing slowdown"""
    print("\n" + "="*80)
    print("TEST 3: DB Lock Contention Check")
    print("="*80)

    # Query for active locks
    async with repo.pool.acquire() as conn:
        locks = await conn.fetch("""
            SELECT
                locktype,
                relation::regclass AS table_name,
                mode,
                granted,
                pid,
                query_start,
                state,
                wait_event_type,
                wait_event
            FROM pg_locks
            JOIN pg_stat_activity USING (pid)
            WHERE relation::regclass::text LIKE '%trailing_stop%'
               OR relation::regclass::text LIKE '%positions%'
            ORDER BY granted, query_start
        """)

        if locks:
            print(f"\n⚠️ Found {len(locks)} locks on TS/position tables:")
            for lock in locks:
                print(f"  {lock['table_name']}: {lock['mode']} (granted: {lock['granted']}, state: {lock['state']})")
        else:
            print("✅ No locks on TS/position tables")

    # Check for blocking queries
    async with repo.pool.acquire() as conn:
        blocking = await conn.fetch("""
            SELECT
                blocked_locks.pid AS blocked_pid,
                blocked_activity.usename AS blocked_user,
                blocking_locks.pid AS blocking_pid,
                blocking_activity.usename AS blocking_user,
                blocked_activity.query AS blocked_statement,
                blocking_activity.query AS blocking_statement
            FROM pg_catalog.pg_locks blocked_locks
            JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
            JOIN pg_catalog.pg_locks blocking_locks
                ON blocking_locks.locktype = blocked_locks.locktype
                AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
                AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
                AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
                AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
                AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
                AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
                AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
                AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
                AND blocking_locks.pid != blocked_locks.pid
            JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
            WHERE NOT blocked_locks.granted
        """)

        if blocking:
            print(f"\n❌ Found {len(blocking)} blocking queries!")
            for block in blocking:
                print(f"  Blocked PID {block['blocked_pid']}: {block['blocked_statement'][:100]}")
                print(f"  Blocking PID {block['blocking_pid']}: {block['blocking_statement'][:100]}")
        else:
            print("✅ No blocking queries detected")


async def main():
    print("🔍 TS Creation Timeout - Wave Simulation Diagnostic")
    print("="*80)

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
        logger.info("✅ Connected to database")

        # Run tests
        seq_results = await test_sequential(repo, count=5)
        conc_results = await test_concurrent(repo, count=5)
        await test_db_lock_contention(repo)

        # Final comparison
        print("\n" + "="*80)
        print("🎯 COMPARISON: Sequential vs Concurrent")
        print("="*80)

        if seq_results and conc_results:
            seq_avg = sum(r['total_ms'] for r in seq_results) / len(seq_results)
            conc_avg = sum(r['total_ms'] for r in conc_results) / len(conc_results)
            conc_max = max(r['total_ms'] for r in conc_results)

            print(f"Sequential avg time per TS: {seq_avg:.1f}ms")
            print(f"Concurrent avg time per TS: {conc_avg:.1f}ms")
            print(f"Concurrent max time: {conc_max:.1f}ms")

            if conc_avg > seq_avg * 1.5:
                print(f"\n⚠️ Concurrent is {conc_avg/seq_avg:.1f}x slower - DB contention likely!")
            else:
                print(f"\n✅ No significant concurrent slowdown ({conc_avg/seq_avg:.1f}x)")

    finally:
        await repo.close()
        logger.info("✅ Disconnected from database")


if __name__ == '__main__':
    asyncio.run(main())
