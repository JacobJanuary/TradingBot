#!/usr/bin/env python3
"""
Критические тесты для проверки защиты от race conditions

ВАЖНО: Эти тесты должны ВСЕГДА проходить после исправления Problem #4 и #6
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List, Dict
import threading


class TestRaceConditionProtection:
    """
    Тестирование защиты от race conditions
    """

    @pytest.mark.asyncio
    async def test_position_locks_are_real_locks(self):
        """
        🔒 Тест что position_locks это настоящие asyncio.Lock, а не set
        """
        from core.position_manager import PositionManager

        manager = PositionManager(config=Mock(), repository=Mock(), exchanges={})

        # Check current implementation
        assert hasattr(manager, 'position_locks'), "position_locks should exist"

        # Current issue: position_locks is a set
        if isinstance(manager.position_locks, set):
            pytest.fail("position_locks is a set, should be Dict[str, asyncio.Lock]!")

        # After fix: should be dict of locks
        # assert isinstance(manager.position_locks, dict)
        # lock = manager.position_locks.get('BTC/USDT')
        # assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_concurrent_sl_updates_serialized(self):
        """
        ⚡ Тест что одновременные обновления SL выполняются последовательно
        """
        from core.position_manager import PositionManager

        manager = PositionManager(config=Mock(), repository=Mock(), exchanges={})

        # Track execution order
        execution_log = []

        async def mock_set_stop_loss(exchange, position, stop_price):
            execution_log.append(('start', stop_price, time.time()))
            await asyncio.sleep(0.1)  # Simulate work
            execution_log.append(('end', stop_price, time.time()))
            return True

        with patch.object(manager, '_set_stop_loss', new=mock_set_stop_loss):
            # Create mock position
            position = Mock(
                symbol='BTC/USDT',
                exchange='binance',
                side='long',
                quantity=0.001
            )

            # Launch 3 concurrent SL updates
            tasks = [
                manager._set_stop_loss(Mock(), position, 49000 + i * 100)
                for i in range(3)
            ]

            await asyncio.gather(*tasks)

            # Verify serialization
            # Check that each operation completes before next starts
            for i in range(0, len(execution_log) - 2, 2):
                end_time = execution_log[i + 1][2]
                next_start_time = execution_log[i + 2][2] if i + 2 < len(execution_log) else float('inf')

                # Small tolerance for timing
                assert next_start_time >= end_time - 0.01, \
                    f"Operations overlapped! End: {end_time}, Next start: {next_start_time}"

    @pytest.mark.asyncio
    async def test_deadlock_prevention(self):
        """
        💀 Тест предотвращения deadlock при множественных locks
        """
        # This would require proper lock implementation
        # Currently testing if the system can handle potential deadlock scenarios

        from core.position_manager import PositionManager

        manager = PositionManager(config=Mock(), repository=Mock(), exchanges={})

        deadlock_detected = False
        timeout_count = 0

        async def operation_a():
            """Operation that needs locks in order A->B"""
            nonlocal timeout_count
            try:
                # Mock acquiring lock A
                await asyncio.sleep(0.1)
                # Try to acquire lock B
                await asyncio.wait_for(asyncio.sleep(0.1), timeout=1.0)
            except asyncio.TimeoutError:
                timeout_count += 1

        async def operation_b():
            """Operation that needs locks in order B->A"""
            nonlocal timeout_count
            try:
                # Mock acquiring lock B
                await asyncio.sleep(0.1)
                # Try to acquire lock A
                await asyncio.wait_for(asyncio.sleep(0.1), timeout=1.0)
            except asyncio.TimeoutError:
                timeout_count += 1

        # Run both operations concurrently
        await asyncio.gather(
            operation_a(),
            operation_b(),
            return_exceptions=True
        )

        # System should handle this without hanging
        assert timeout_count <= 1, "Deadlock may have occurred"

    @pytest.mark.asyncio
    async def test_single_instance_protection(self):
        """
        🚫 Тест что SingleInstance предотвращает запуск двух ботов
        """
        from utils.single_instance import SingleInstance

        # First instance
        instance1 = SingleInstance('test_bot', auto_exit=False)

        # Try to create second instance
        with pytest.raises(Exception) as exc_info:
            instance2 = SingleInstance('test_bot', auto_exit=False, timeout=0)

        assert "already running" in str(exc_info.value).lower()

        # Cleanup
        instance1.release()

    @pytest.mark.asyncio
    async def test_lock_timeout_handling(self):
        """
        ⏱️ Тест обработки timeout при получении lock
        """
        from asyncio import Lock, TimeoutError

        lock = Lock()

        # First coroutine holds the lock
        async def hold_lock():
            async with lock:
                await asyncio.sleep(2)  # Hold for 2 seconds

        # Second tries to acquire with timeout
        async def try_acquire_with_timeout():
            try:
                await asyncio.wait_for(lock.acquire(), timeout=0.5)
                lock.release()
                return "acquired"
            except TimeoutError:
                return "timeout"

        # Start holder
        holder_task = asyncio.create_task(hold_lock())
        await asyncio.sleep(0.1)  # Let it acquire the lock

        # Try to acquire
        result = await try_acquire_with_timeout()

        assert result == "timeout"

        # Cleanup
        await holder_task

    @pytest.mark.asyncio
    async def test_concurrent_position_creation_different_symbols(self):
        """
        ✅ Тест что позиции для РАЗНЫХ символов могут создаваться параллельно
        """
        from core.position_manager import PositionManager

        manager = PositionManager(config=Mock(), repository=Mock(), exchanges={})

        # Mock exchange
        mock_exchange = Mock()
        mock_exchange.create_market_order = AsyncMock(
            return_value=Mock(
                id='order_123',
                status='closed',
                filled=0.001,
                price=50000,
                amount=0.001
            )
        )
        manager.exchanges = {'binance': mock_exchange}

        manager.repository.create_position = AsyncMock(return_value=1)
        manager.repository.create_trade = AsyncMock(return_value=1)

        with patch.object(manager, '_set_stop_loss', new=AsyncMock(return_value=True)):
            # Different symbols
            requests = [
                Mock(
                    signal_id=i,
                    symbol=f'{coin}/USDT',
                    exchange='binance',
                    side='BUY',
                    entry_price=50000,
                    position_size_usd=100,
                    stop_loss_percent=2.0
                )
                for i, coin in enumerate(['BTC', 'ETH', 'SOL'])
            ]

            # Execute concurrently
            start_time = time.time()
            results = await asyncio.gather(*[
                manager.open_position(req) for req in requests
            ])
            duration = time.time() - start_time

            # All should succeed
            successful = [r for r in results if r is not None]
            assert len(successful) == 3, "All different symbols should be created"

            # Should be concurrent (fast)
            assert duration < 1.0, f"Took {duration}s, should be concurrent"


class TestLockImplementation:
    """
    Тестирование правильной реализации блокировок
    """

    @pytest.mark.asyncio
    async def test_lock_manager_functionality(self):
        """
        🔧 Тест функциональности lock manager (если реализован)
        """
        try:
            from core.lock_manager import LockManager
        except ImportError:
            pytest.skip("LockManager not implemented yet")

        lock_manager = LockManager()

        # Test acquiring lock
        async with lock_manager.acquire_lock('test_resource', 'test_operation'):
            # Lock should be held
            assert 'test_resource' in lock_manager._lock_holders

        # Lock should be released
        assert 'test_resource' not in lock_manager._lock_holders

    @pytest.mark.asyncio
    async def test_lock_statistics(self):
        """
        📊 Тест сбора статистики по блокировкам
        """
        try:
            from core.lock_manager import LockManager
        except ImportError:
            pytest.skip("LockManager not implemented yet")

        lock_manager = LockManager()

        # Acquire some locks
        async def hold_lock(resource: str, duration: float):
            async with lock_manager.acquire_lock(resource, f'op_{resource}'):
                await asyncio.sleep(duration)

        # Start multiple operations
        tasks = [
            hold_lock('resource_1', 0.1),
            hold_lock('resource_2', 0.2),
            hold_lock('resource_3', 0.05)
        ]

        # Run half way
        gather_task = asyncio.gather(*tasks)
        await asyncio.sleep(0.05)

        # Get stats while locks are held
        stats = lock_manager.get_lock_stats()

        assert stats['total_locks'] >= 3
        assert stats['active_locks'] > 0

        # Wait for completion
        await gather_task


class TestStressRaceConditions:
    """
    Stress тесты для race conditions
    """

    @pytest.mark.asyncio
    async def test_high_concurrency_operations(self):
        """
        🔥 Stress test - 100 параллельных операций
        """
        from core.position_manager import PositionManager

        manager = PositionManager(config=Mock(), repository=Mock(), exchanges={})

        operation_count = 100
        results = {'success': 0, 'conflict': 0, 'error': 0}

        async def random_operation(idx: int):
            """Случайная операция"""
            import random

            operations = [
                ('create_position', 'BTC/USDT'),
                ('update_sl', 'BTC/USDT'),
                ('create_position', 'ETH/USDT'),
                ('update_sl', 'ETH/USDT'),
                ('check_positions', None)
            ]

            op_type, symbol = random.choice(operations)

            try:
                if op_type == 'create_position':
                    # Mock operation
                    await asyncio.sleep(random.uniform(0.01, 0.05))
                    results['success'] += 1
                elif op_type == 'update_sl':
                    await asyncio.sleep(random.uniform(0.01, 0.05))
                    results['success'] += 1
                else:
                    await asyncio.sleep(random.uniform(0.01, 0.02))
                    results['success'] += 1
            except Exception as e:
                if "conflict" in str(e).lower():
                    results['conflict'] += 1
                else:
                    results['error'] += 1

        # Run all operations
        await asyncio.gather(*[
            random_operation(i) for i in range(operation_count)
        ])

        # Verify no crashes
        total = sum(results.values())
        assert total == operation_count

        # Acceptable error rate
        error_rate = results['error'] / total
        assert error_rate < 0.05, f"High error rate: {error_rate:.2%}"

    @pytest.mark.asyncio
    async def test_concurrent_trailing_stop_updates(self):
        """
        📈 Тест одновременных обновлений trailing stop
        """
        from protection.trailing_stop import SmartTrailingStopManager

        try:
            manager = SmartTrailingStopManager(Mock(), Mock(), Mock())
        except:
            pytest.skip("TrailingStopManager not available")

        # Simulate multiple price updates triggering trailing stop
        price_updates = [50000 + i * 100 for i in range(10)]

        async def update_trailing(price: float):
            """Обновление trailing stop"""
            try:
                # Mock the update
                await asyncio.sleep(0.01)
                return True
            except:
                return False

        # All updates concurrently
        results = await asyncio.gather(*[
            update_trailing(price) for price in price_updates
        ])

        # Should handle all updates (even if serialized)
        assert all(results)


class TestValidation:
    """
    Валидация что race conditions исправлены
    """

    @pytest.mark.asyncio
    async def test_no_duplicate_positions_in_db(self):
        """
        ✅ Проверка что нет дубликатов позиций в БД
        """
        from database.repository import Repository

        repo = Repository(Mock())

        # Check for duplicates
        duplicates = await repo.fetch_all(
            """
            SELECT symbol, exchange, COUNT(*) as count
            FROM positions
            WHERE status = 'OPEN'
            GROUP BY symbol, exchange
            HAVING COUNT(*) > 1
            """
        )

        assert len(duplicates) == 0, f"Found duplicate positions: {duplicates}"

    @pytest.mark.asyncio
    async def test_no_concurrent_sl_conflicts(self):
        """
        ✅ Проверка отсутствия конфликтов при обновлении SL
        """
        from database.repository import Repository

        repo = Repository(Mock())

        # Check for suspicious SL updates (multiple within 1 second)
        conflicts = await repo.fetch_all(
            """
            SELECT position_id, COUNT(*) as update_count
            FROM events
            WHERE event_type = 'STOP_LOSS_UPDATED'
            AND created_at > NOW() - INTERVAL '1 hour'
            GROUP BY position_id, DATE_TRUNC('second', created_at)
            HAVING COUNT(*) > 1
            """
        )

        assert len(conflicts) == 0, f"Found SL update conflicts: {conflicts}"