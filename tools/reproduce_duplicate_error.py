#!/usr/bin/env python3
"""
Duplicate Position Error Reproduction Tool
Phase 2.2 of Duplicate Position Audit

ЦЕЛЬ: Воспроизвести race condition в контролируемых условиях

ВНИМАНИЕ: Этот скрипт может создавать реальные позиции на тестовых биржах!
          Используйте ТОЛЬКО с testnet или после подтверждения.

СЦЕНАРИИ:
1. Scenario A: Parallel Signals (2+ сигналов одновременно)
2. Scenario B: Signal + Sync (сигнал во время sync)
3. Scenario C: Retry after Rollback
4. Scenario D: Cleanup + Signal

ИСПОЛЬЗОВАНИЕ:
    # Dry-run (только логирование, без реальных действий)
    python tools/reproduce_duplicate_error.py --scenario B --dry-run

    # Stress test с параллельными потоками
    python tools/reproduce_duplicate_error.py --scenario A --threads 5 --duration 60

    # С подтверждением
    python tools/reproduce_duplicate_error.py --scenario B --confirm

ОПЦИИ:
    --scenario A|B|C|D  - Выбор сценария
    --threads N         - Количество параллельных потоков (default: 2)
    --duration SEC      - Длительность теста в секундах (default: 30)
    --symbol SYMBOL     - Символ для тестирования (default: TESTUSDT)
    --exchange EXCHANGE - Биржа (default: binance)
    --dry-run           - Dry-run mode (без реальных действий)
    --confirm           - Подтверждение для реальных операций

БЕЗОПАСНОСТЬ:
- По умолчанию используется dry-run mode
- Требует явного --confirm для реальных операций
- Рекомендуется testnet
- Все действия логируются
"""

import asyncio
import sys
import os
import argparse
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional
import asyncpg
import hashlib
from decimal import Decimal
from dotenv import load_dotenv

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()


class DuplicateErrorReproducer:
    """Воспроизведение race condition для duplicate позиций"""

    def __init__(self, scenario: str, threads: int, duration: int,
                 symbol: str, exchange: str, dry_run: bool):
        self.scenario = scenario
        self.threads = threads
        self.duration = duration
        self.symbol = symbol
        self.exchange = exchange
        self.dry_run = dry_run

        # Результаты
        self.attempts = []
        self.successes = 0
        self.duplicates = 0
        self.errors = []

        # DB pool
        self.pool = None

    async def initialize(self):
        """Инициализация DB connection pool"""
        print("🔌 Initializing database connection pool...")

        self.pool = await asyncpg.create_pool(
            host='localhost',
            port=5433,
            user='elcrypto',
            password='LohNeMamont@!21',
            database='fox_crypto',
            min_size=5,
            max_size=20,  # Имитация production
            command_timeout=60
        )
        print(f"✅ Pool created: min=5, max=20 connections")

    async def cleanup(self):
        """Закрытие pool"""
        if self.pool:
            await self.pool.close()

    # ========================================================================
    # HELPERS - DB Operations
    # ========================================================================

    @staticmethod
    def _get_position_lock_id(symbol: str, exchange: str) -> int:
        """
        Генерация lock ID - копия из repository.py

        ВАЖНО: Использует ту же логику, что и production код
        """
        key = f"{symbol}:{exchange}".encode('utf-8')
        hash_digest = hashlib.md5(key).digest()
        lock_id = int.from_bytes(hash_digest[:8], byteorder='big', signed=True)
        return lock_id

    async def simulate_create_position(self, thread_id: int, attempt: int,
                                      delay_after_create: float = 0.0) -> Dict:
        """
        Имитация create_position() с возможностью задержки

        КОПИРУЕТ логику из database/repository.py:230-293

        Args:
            thread_id: ID потока
            attempt: Номер попытки
            delay_after_create: Задержка после INSERT перед COMMIT (для тестов)

        Returns:
            dict с результатом операции
        """
        result = {
            'thread_id': thread_id,
            'attempt': attempt,
            'success': False,
            'position_id': None,
            'error': None,
            'timing': {}
        }

        start_time = time.time()

        try:
            lock_id = self._get_position_lock_id(self.symbol, self.exchange)

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Timing: acquire lock
                    t_lock_start = time.time()
                    await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)
                    result['timing']['lock_acquired'] = time.time() - t_lock_start

                    # Timing: check existing
                    t_check_start = time.time()
                    existing = await conn.fetchrow("""
                        SELECT id FROM monitoring.positions
                        WHERE symbol = $1 AND exchange = $2 AND status = 'active'
                    """, self.symbol, self.exchange)
                    result['timing']['check_existing'] = time.time() - t_check_start

                    if existing:
                        result['position_id'] = existing['id']
                        result['existing'] = True
                        result['success'] = True
                        print(f"  [{thread_id}.{attempt}] Found existing position #{existing['id']}")
                        return result

                    # Timing: insert
                    t_insert_start = time.time()

                    if self.dry_run:
                        # Dry-run: только логирование
                        result['position_id'] = -1  # Fake ID
                        result['success'] = True
                        result['dry_run'] = True
                        print(f"  [{thread_id}.{attempt}] DRY-RUN: Would create position")
                    else:
                        # Реальный INSERT
                        position_id = await conn.fetchval("""
                            INSERT INTO monitoring.positions
                            (symbol, exchange, side, quantity, entry_price, status, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
                            RETURNING id
                        """, self.symbol, self.exchange, 'LONG', Decimal('0.01'),
                            Decimal('1.0'), 'active')

                        result['position_id'] = position_id
                        result['success'] = True
                        print(f"  [{thread_id}.{attempt}] ✅ Created position #{position_id}")

                    result['timing']['insert'] = time.time() - t_insert_start

                    # Опциональная задержка перед COMMIT (для тестирования race)
                    if delay_after_create > 0:
                        await asyncio.sleep(delay_after_create)
                        result['timing']['artificial_delay'] = delay_after_create

                # Transaction committed, lock released

        except asyncpg.exceptions.UniqueViolationError as e:
            # ЭТО ТО, ЧТО МЫ ХОТИМ ВОСПРОИЗВЕСТИ!
            result['error'] = 'UniqueViolationError'
            result['error_detail'] = str(e)
            print(f"  [{thread_id}.{attempt}] ❌ UniqueViolationError: {e}")
            self.duplicates += 1

        except Exception as e:
            result['error'] = type(e).__name__
            result['error_detail'] = str(e)
            print(f"  [{thread_id}.{attempt}] ❌ Error: {e}")

        result['timing']['total'] = time.time() - start_time
        return result

    async def simulate_update_position(self, position_id: int, status: str,
                                      thread_id: int) -> bool:
        """
        Имитация update_position() - AUTOCOMMIT, NO LOCK

        КОПИРУЕТ логику из database/repository.py:545-589
        """
        if self.dry_run:
            print(f"  [{thread_id}] DRY-RUN: Would update position #{position_id} to status={status}")
            return True

        try:
            async with self.pool.acquire() as conn:
                # NO TRANSACTION - autocommit
                await conn.execute("""
                    UPDATE monitoring.positions
                    SET status = $1, updated_at = NOW()
                    WHERE id = $2
                """, status, position_id)
            print(f"  [{thread_id}] Updated position #{position_id} → {status}")
            return True

        except Exception as e:
            print(f"  [{thread_id}] ❌ Update failed: {e}")
            return False

    # ========================================================================
    # SCENARIO A: Parallel Signals
    # ========================================================================

    async def run_scenario_a(self):
        """
        SCENARIO A: Параллельные сигналы

        Ситуация:
        - Несколько WebSocket потоков получают сигнал ОДНОВРЕМЕННО
        - Все пытаются создать позицию для одного символа

        Вероятность: LOW (редко бывает несколько одинаковых сигналов)

        Тест:
        - Запустить N потоков одновременно
        - Каждый вызывает create_position()
        - Измерить, сколько получили UniqueViolationError
        """
        print(f"\n{'='*80}")
        print(f"SCENARIO A: Parallel Signals ({self.threads} threads)")
        print(f"{'='*80}\n")

        print(f"Launching {self.threads} concurrent create_position() calls...")
        print()

        start_time = time.time()

        # Запуск N потоков ОДНОВРЕМЕННО
        tasks = [
            self.simulate_create_position(thread_id=i, attempt=1)
            for i in range(self.threads)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        duration = time.time() - start_time

        # Анализ результатов
        successful = [r for r in results if isinstance(r, dict) and r['success']]
        duplicates = [r for r in results if isinstance(r, dict) and r.get('error') == 'UniqueViolationError']
        other_errors = [r for r in results if isinstance(r, dict) and r.get('error') and r['error'] != 'UniqueViolationError']

        print(f"\n{'='*80}")
        print("RESULTS:")
        print(f"{'='*80}")
        print(f"Total threads:        {self.threads}")
        print(f"Successful creates:   {len(successful)}")
        print(f"Duplicate errors:     {len(duplicates)}")
        print(f"Other errors:         {len(other_errors)}")
        print(f"Duration:             {duration:.3f}s")
        print()

        if duplicates:
            print(f"🔴 REPRODUCED! Got {len(duplicates)} UniqueViolationError(s)")
            for dup in duplicates:
                print(f"  Thread {dup['thread_id']}: {dup['error_detail']}")
        else:
            print(f"⚠️  No duplicates reproduced. Advisory lock prevented race condition.")

        # Timing analysis
        if successful:
            print(f"\nTiming analysis (successful creates):")
            avg_lock = sum(r['timing'].get('lock_acquired', 0) for r in successful) / len(successful)
            avg_check = sum(r['timing'].get('check_existing', 0) for r in successful) / len(successful)
            avg_insert = sum(r['timing'].get('insert', 0) for r in successful) / len(successful)
            print(f"  Avg lock time:    {avg_lock*1000:.1f}ms")
            print(f"  Avg check time:   {avg_check*1000:.1f}ms")
            print(f"  Avg insert time:  {avg_insert*1000:.1f}ms")

        self.attempts.extend(results)

    # ========================================================================
    # SCENARIO B: Signal + Sync (MAIN SCENARIO)
    # ========================================================================

    async def run_scenario_b(self):
        """
        SCENARIO B: Signal + Sync (PRIMARY SUSPECT)

        Ситуация:
        - Thread 1 (Signal): CREATE → UPDATE(entry_placed) → sleep(3) → UPDATE(active)
        - Thread 2 (Sync): CREATE во время sleep

        Проблема:
        - После UPDATE(entry_placed) позиция выходит из индекса
        - Sync не видит её (WHERE status='active')
        - Sync создает дубликат

        Вероятность: HIGH (подтверждено логами)
        """
        print(f"\n{'='*80}")
        print(f"SCENARIO B: Signal + Sync (Race Condition)")
        print(f"{'='*80}\n")

        print("Thread 1: Simulating Signal handler...")
        print("Thread 2: Simulating Sync during sleep window...")
        print()

        # Thread 1: Signal flow
        async def signal_flow():
            print("[Signal] Starting position creation flow...")

            # Step 1: CREATE (status='active')
            result = await self.simulate_create_position(thread_id=1, attempt=1)
            if not result['success']:
                print("[Signal] ❌ Failed to create position")
                return result

            position_id = result['position_id']

            # Step 2: UPDATE to 'entry_placed' (EXIT INDEX)
            await asyncio.sleep(0.5)  # Simulate order placement
            await self.simulate_update_position(position_id, 'entry_placed', thread_id=1)
            print("[Signal] Position NOW OUT OF INDEX (status='entry_placed')")

            # Step 3: Sleep 3 seconds (VULNERABILITY WINDOW)
            print("[Signal] Sleeping 3 seconds (waiting for order settlement)...")
            await asyncio.sleep(3.0)

            # Step 4: UPDATE back to 'active' (TRY TO ENTER INDEX)
            print("[Signal] Trying to update back to 'active'...")
            try:
                if self.dry_run:
                    print("[Signal] DRY-RUN: Would update to 'active'")
                else:
                    async with self.pool.acquire() as conn:
                        await conn.execute("""
                            UPDATE monitoring.positions
                            SET status = $1, updated_at = NOW()
                            WHERE id = $2
                        """, 'active', position_id)
                    print(f"[Signal] ✅ Updated to 'active'")

            except asyncpg.exceptions.UniqueViolationError as e:
                print(f"[Signal] ❌ UniqueViolationError on UPDATE: {e}")
                result['error'] = 'UniqueViolationError'
                result['error_detail'] = str(e)
                self.duplicates += 1

            return result

        # Thread 2: Sync flow (запускается во время sleep)
        async def sync_flow():
            # Подождать, пока Signal выполнит UPDATE → entry_placed
            await asyncio.sleep(1.5)

            print("[Sync] Waking up, checking positions...")
            print("[Sync] Attempting to create position (Signal is in sleep)...")

            result = await self.simulate_create_position(thread_id=2, attempt=1)
            return result

        # Запуск обоих потоков параллельно
        start_time = time.time()
        signal_result, sync_result = await asyncio.gather(signal_flow(), sync_flow())
        duration = time.time() - start_time

        # Анализ
        print(f"\n{'='*80}")
        print("RESULTS:")
        print(f"{'='*80}")
        print(f"Duration: {duration:.3f}s")
        print()

        print("Signal thread:")
        if signal_result.get('error'):
            print(f"  ❌ Error: {signal_result['error']}")
            print(f"  Detail: {signal_result.get('error_detail', '')}")
        else:
            print(f"  ✅ Position #{signal_result.get('position_id')}")

        print("\nSync thread:")
        if sync_result.get('error'):
            print(f"  ❌ Error: {sync_result['error']}")
            print(f"  Detail: {sync_result.get('error_detail', '')}")
        else:
            print(f"  ✅ Position #{sync_result.get('position_id')}")

        print()
        if self.duplicates > 0:
            print(f"🔴 RACE CONDITION REPRODUCED! {self.duplicates} duplicate error(s)")
        else:
            print("⚠️  Race condition NOT reproduced in this run")

        self.attempts.extend([signal_result, sync_result])

    # ========================================================================
    # SCENARIO C: Retry after Rollback
    # ========================================================================

    async def run_scenario_c(self):
        """
        SCENARIO C: Retry after Rollback

        Ситуация:
        - Thread 1: CREATE → error → rollback
        - Thread 2: CREATE во время rollback
        - Thread 1: Retry CREATE

        Вероятность: MEDIUM
        """
        print(f"\n{'='*80}")
        print(f"SCENARIO C: Retry after Rollback")
        print(f"{'='*80}\n")

        # TODO: Implement if needed
        print("⚠️  This scenario requires more complex setup")
        print("    (simulating rollback and retry logic)")
        print("    Not implemented in this version")

    # ========================================================================
    # SCENARIO D: Cleanup + Signal
    # ========================================================================

    async def run_scenario_d(self):
        """
        SCENARIO D: Cleanup + Signal

        Ситуация:
        - Cleanup script пытается восстановить incomplete позицию
        - Signal создает новую позицию для того же символа

        Вероятность: LOW-MEDIUM
        """
        print(f"\n{'='*80}")
        print(f"SCENARIO D: Cleanup + Signal")
        print(f"{'='*80}\n")

        # TODO: Implement if needed
        print("⚠️  This scenario requires cleanup script simulation")
        print("    Not implemented in this version")

    # ========================================================================
    # STRESS TEST
    # ========================================================================

    async def run_stress_test(self):
        """
        Stress test: многопоточная нагрузка в течение N секунд

        Цель: измерить частоту race condition при высокой нагрузке
        """
        print(f"\n{'='*80}")
        print(f"STRESS TEST: {self.threads} threads × {self.duration}s")
        print(f"{'='*80}\n")

        start_time = time.time()
        attempt_counter = 0

        async def worker(worker_id: int):
            """Worker поток: создает позиции в цикле"""
            nonlocal attempt_counter
            local_attempts = 0

            while (time.time() - start_time) < self.duration:
                attempt_counter += 1
                local_attempts += 1

                result = await self.simulate_create_position(
                    thread_id=worker_id,
                    attempt=local_attempts
                )

                self.attempts.append(result)

                if result['success']:
                    self.successes += 1

                # Cleanup: удалить созданную позицию (для следующей итерации)
                if not self.dry_run and result.get('position_id'):
                    await self.cleanup_position(result['position_id'])

                # Small delay между попытками
                await asyncio.sleep(0.1)

            print(f"  Worker {worker_id}: {local_attempts} attempts")

        # Запуск workers
        print(f"Launching {self.threads} worker threads...")
        workers = [worker(i) for i in range(self.threads)]
        await asyncio.gather(*workers)

        duration = time.time() - start_time

        # Статистика
        print(f"\n{'='*80}")
        print("STRESS TEST RESULTS:")
        print(f"{'='*80}")
        print(f"Duration:          {duration:.1f}s")
        print(f"Total attempts:    {len(self.attempts)}")
        print(f"Successful:        {self.successes}")
        print(f"Duplicate errors:  {self.duplicates}")
        print(f"Error rate:        {self.duplicates/len(self.attempts)*100:.2f}%")
        print()

        if self.duplicates > 0:
            print(f"🔴 Reproduced {self.duplicates} duplicate error(s) under load")
            print(f"   Frequency: {self.duplicates / duration:.2f} errors/second")

    async def cleanup_position(self, position_id: int):
        """Удалить тестовую позицию"""
        if self.dry_run or position_id < 0:
            return

        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM monitoring.positions WHERE id = $1
                """, position_id)
        except Exception:
            pass  # Ignore cleanup errors

    # ========================================================================
    # MAIN RUNNER
    # ========================================================================

    async def run(self):
        """Запуск выбранного сценария"""
        try:
            await self.initialize()

            if self.scenario == 'A':
                await self.run_scenario_a()
            elif self.scenario == 'B':
                await self.run_scenario_b()
            elif self.scenario == 'C':
                await self.run_scenario_c()
            elif self.scenario == 'D':
                await self.run_scenario_d()
            elif self.scenario == 'stress':
                await self.run_stress_test()
            else:
                print(f"❌ Unknown scenario: {self.scenario}")
                return

        finally:
            await self.cleanup()


async def main():
    parser = argparse.ArgumentParser(
        description='Reproduce duplicate position errors',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--scenario', choices=['A', 'B', 'C', 'D', 'stress'],
                       default='B', help='Scenario to run (default: B)')
    parser.add_argument('--threads', type=int, default=2,
                       help='Number of parallel threads (default: 2)')
    parser.add_argument('--duration', type=int, default=30,
                       help='Duration for stress test in seconds (default: 30)')
    parser.add_argument('--symbol', type=str, default='TESTUSDT',
                       help='Symbol for testing (default: TESTUSDT)')
    parser.add_argument('--exchange', type=str, default='binance',
                       help='Exchange name (default: binance)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Dry-run mode (no real operations)')
    parser.add_argument('--confirm', action='store_true',
                       help='Confirm real operations (required if not dry-run)')

    args = parser.parse_args()

    # Safety check
    if not args.dry_run and not args.confirm:
        print("❌ ERROR: Real operations require --confirm flag")
        print("   Use --dry-run for safe testing")
        return 1

    print("="*80)
    print("DUPLICATE ERROR REPRODUCTION TOOL")
    print("="*80)
    print(f"Scenario:  {args.scenario}")
    print(f"Threads:   {args.threads}")
    print(f"Symbol:    {args.symbol}")
    print(f"Exchange:  {args.exchange}")
    print(f"Mode:      {'DRY-RUN' if args.dry_run else 'REAL OPERATIONS ⚠️'}")
    print()

    if not args.dry_run:
        print("⚠️  WARNING: This will create REAL positions in the database!")
        print("   Press Ctrl+C to cancel, or wait 5 seconds to continue...")
        await asyncio.sleep(5)
        print()

    reproducer = DuplicateErrorReproducer(
        scenario=args.scenario,
        threads=args.threads,
        duration=args.duration,
        symbol=args.symbol,
        exchange=args.exchange,
        dry_run=args.dry_run
    )

    try:
        await reproducer.run()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        return 1
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
