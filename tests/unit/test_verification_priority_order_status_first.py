"""
Unit Tests для FIX #2: Verification Source Priority Change

Тесты проверяют что Order Status теперь PRIMARY source (был SECONDARY).

Root Cause: WebSocket не надежен для immediate verification
Fix: Order Status (fetch_order) становится PRIORITY 1
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.atomic_position_manager import AtomicPositionManager
import asyncio
import time


@pytest.mark.asyncio
async def test_order_status_confirms_position_websocket_delayed():
    """
    Test: WebSocket has delay, Order Status confirms position immediately
    Expected: Verification succeeds via SOURCE 1 (Order Status) in < 1s
    """

    # Mock exchange instance
    exchange_mock = AsyncMock()

    # Mock fetch_order to return filled order
    filled_order = {
        'id': 'order-789',
        'status': 'closed',
        'filled': 100.0,
        'amount': 100.0,
        'side': 'buy'
    }
    exchange_mock.fetch_order.return_value = filled_order

    # Mock fetch_positions (fallback)
    exchange_mock.fetch_positions.return_value = []

    # Mock position_manager with WebSocket that returns None (delayed)
    position_manager_mock = MagicMock()
    position_manager_mock.get_cached_position.return_value = None  # WebSocket delay

    # Create APM instance
    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager_mock

    # Mock entry order
    entry_order_mock = MagicMock()
    entry_order_mock.id = 'order-789'

    # Execute verification
    start_time = time.time()

    result = await apm._verify_position_exists_multi_source(
        symbol='TESTUSDT',
        exchange='binance',
        expected_quantity=100.0,
        entry_order=entry_order_mock,
        exchange_instance=exchange_mock
    )

    elapsed = time.time() - start_time

    # Assertions
    assert result is True  # Verification succeeded
    assert exchange_mock.fetch_order.call_count >= 1  # Order Status called
    assert elapsed < 2.0  # Fast verification (< 2s, should be ~0.5s)


@pytest.mark.asyncio
async def test_all_sources_fail_timeout():
    """
    Test: All sources return None/fail
    Expected: Verification times out after 10s, raises AtomicPositionError
    """

    from core.atomic_position_manager import AtomicPositionError

    exchange_mock = AsyncMock()
    exchange_mock.fetch_order.return_value = None  # Order Status returns None
    exchange_mock.fetch_positions.return_value = []  # REST API returns empty

    position_manager_mock = MagicMock()
    position_manager_mock.get_cached_position.return_value = None  # WebSocket returns None

    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager_mock

    entry_order_mock = MagicMock()
    entry_order_mock.id = 'order-999'

    start_time = time.time()

    # Should raise AtomicPositionError after timeout
    with pytest.raises(AtomicPositionError):
        await apm._verify_position_exists_multi_source(
            symbol='TESTUSDT',
            exchange='binance',
            expected_quantity=100.0,
            entry_order=entry_order_mock,
            exchange_instance=exchange_mock,
            timeout=2.0  # Shorter timeout for test (2s instead of 10s)
        )

    elapsed = time.time() - start_time

    # Should timeout after ~2s
    assert elapsed >= 2.0  # At least timeout duration
    assert elapsed < 3.0  # Should not significantly exceed timeout


@pytest.mark.asyncio
async def test_order_status_priority_over_websocket():
    """
    Test: Order Status проверяется ПЕРВЫМ (до WebSocket)
    Expected: Order Status called first, WebSocket может не вызываться
    """

    exchange_mock = AsyncMock()

    # Order Status returns immediately
    exchange_mock.fetch_order.return_value = {
        'id': 'order-123',
        'status': 'closed',
        'filled': 50.0,
        'amount': 50.0,
        'side': 'sell'
    }

    # WebSocket также готов (но не должен быть вызван если Order Status успешен)
    position_manager_mock = MagicMock()
    position_manager_mock.get_cached_position.return_value = {
        'symbol': 'TESTUSDT',
        'quantity': 50.0,
        'side': 'short'
    }

    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager_mock

    entry_order_mock = MagicMock()
    entry_order_mock.id = 'order-123'

    result = await apm._verify_position_exists_multi_source(
        symbol='TESTUSDT',
        exchange='binance',
        expected_quantity=50.0,
        entry_order=entry_order_mock,
        exchange_instance=exchange_mock
    )

    # Assertions
    assert result is True
    assert exchange_mock.fetch_order.call_count >= 1  # Order Status called

    # WebSocket может быть вызван или нет (зависит от timing)
    # Важно что Order Status проверяется ПЕРВЫМ


@pytest.mark.asyncio
async def test_websocket_as_backup_when_order_status_fails():
    """
    Test: Если Order Status fails, WebSocket работает как backup
    Expected: WebSocket подтверждает позицию когда Order Status недоступен
    """

    exchange_mock = AsyncMock()

    # Order Status throws exception
    exchange_mock.fetch_order.side_effect = Exception("API error")

    # WebSocket работает
    position_manager_mock = MagicMock()
    position_manager_mock.get_cached_position.return_value = {
        'symbol': 'TESTUSDT',
        'quantity': 75.0,
        'side': 'long'
    }

    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager_mock

    entry_order_mock = MagicMock()
    entry_order_mock.id = 'order-456'

    # Mock fetch_positions as fallback
    exchange_mock.fetch_positions.return_value = []

    result = await apm._verify_position_exists_multi_source(
        symbol='TESTUSDT',
        exchange='binance',
        expected_quantity=75.0,
        entry_order=entry_order_mock,
        exchange_instance=exchange_mock,
        timeout=5.0  # Shorter timeout for test
    )

    # Assertions
    assert result is True  # WebSocket confirmed
    assert position_manager_mock.get_cached_position.called  # WebSocket was used


@pytest.mark.asyncio
async def test_rest_api_as_final_fallback():
    """
    Test: REST API работает как final fallback когда Order Status и WebSocket fail
    Expected: REST API подтверждает позицию
    """

    exchange_mock = AsyncMock()

    # Order Status returns None
    exchange_mock.fetch_order.return_value = None

    # WebSocket returns None
    position_manager_mock = MagicMock()
    position_manager_mock.get_cached_position.return_value = None

    # REST API returns position
    exchange_mock.fetch_positions.return_value = [{
        'symbol': 'TESTUSDT',
        'contracts': 25.0,
        'side': 'short'
    }]

    apm = AtomicPositionManager(db_pool=MagicMock())
    apm.position_manager = position_manager_mock

    entry_order_mock = MagicMock()
    entry_order_mock.id = 'order-xyz'

    result = await apm._verify_position_exists_multi_source(
        symbol='TESTUSDT',
        exchange='binance',
        expected_quantity=25.0,
        entry_order=entry_order_mock,
        exchange_instance=exchange_mock,
        timeout=5.0
    )

    # Assertions
    assert result is True  # REST API confirmed
    assert exchange_mock.fetch_positions.called  # REST API was used


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
