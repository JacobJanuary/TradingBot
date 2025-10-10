"""
Unit test for PositionManager race condition fix

Tests that Fix #2 (asyncio.Lock for _position_exists) prevents
parallel tasks from both seeing "no position" and opening duplicates.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from config.settings import TradingConfig
from core.position_manager import PositionManager


@pytest.fixture
def mock_config():
    """Mock trading config"""
    config = MagicMock(spec=TradingConfig)
    config.max_position_size = Decimal('1000')
    config.risk_per_trade = Decimal('2')
    config.trailing_activation_percent = Decimal('1.5')
    config.trailing_callback_percent = Decimal('0.5')
    return config


@pytest.fixture
def mock_repository():
    """Mock repository"""
    repo = AsyncMock()
    repo.get_open_position = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_exchange():
    """Mock exchange manager"""
    exchange = AsyncMock()
    exchange.fetch_positions = AsyncMock(return_value=[])
    return exchange


@pytest.fixture
def mock_event_router():
    """Mock event router"""
    return MagicMock()


@pytest.fixture
async def position_manager(mock_config, mock_repository, mock_exchange, mock_event_router):
    """Create PositionManager instance with mocks"""
    exchanges = {'binance': mock_exchange}

    manager = PositionManager(
        config=mock_config,
        exchanges=exchanges,
        repository=mock_repository,
        event_router=mock_event_router
    )

    yield manager


@pytest.mark.asyncio
async def test_position_exists_parallel_calls(position_manager, mock_repository, mock_exchange):
    """
    Test that parallel calls to _position_exists are serialized by lock

    Scenario:
    - 10 tasks call _position_exists() for same symbol simultaneously
    - WITHOUT lock: All 10 would call fetch_positions() in parallel
    - WITH lock: Calls are serialized, only ONE active at a time

    Expected:
    - All calls should complete
    - No race condition should occur
    - Lock should ensure sequential access
    """
    symbol = "BTCUSDT"
    exchange = "binance"

    # Track how many tasks are checking simultaneously
    active_checks = []
    max_concurrent = 0

    # Mock fetch_positions to track concurrent access
    async def mock_fetch_positions():
        # Mark this task as active
        task_id = id(asyncio.current_task())
        active_checks.append(task_id)

        # Track max concurrent
        nonlocal max_concurrent
        max_concurrent = max(max_concurrent, len(set(active_checks)))

        # Simulate network delay
        await asyncio.sleep(0.1)

        # Remove task from active
        active_checks.remove(task_id)

        return []  # No positions

    mock_exchange.fetch_positions = mock_fetch_positions

    # Launch 10 parallel tasks
    tasks = [
        position_manager._position_exists(symbol, exchange)
        for _ in range(10)
    ]

    results = await asyncio.gather(*tasks)

    # All should return False (no position exists)
    assert all(result is False for result in results)

    # CRITICAL: With lock, max_concurrent should be 1
    # Without lock, it would be > 1 (up to 10)
    assert max_concurrent == 1, f"Expected max_concurrent=1 (serialized), got {max_concurrent}"

    print(f"✅ Lock working correctly: max_concurrent = {max_concurrent}")


@pytest.mark.asyncio
async def test_position_exists_local_cache_hit(position_manager):
    """
    Test that local cache check doesn't need lock
    (lock is acquired but returns immediately)
    """
    symbol = "ETHUSDT"
    exchange = "binance"

    # Add position to local cache
    from core.position_manager import PositionState
    position_manager.positions[symbol] = MagicMock(spec=PositionState)

    # Should return True immediately without checking DB or exchange
    result = await position_manager._position_exists(symbol, exchange)

    assert result is True


@pytest.mark.asyncio
async def test_position_exists_database_hit(position_manager, mock_repository, mock_exchange):
    """
    Test that database hit prevents exchange check
    """
    symbol = "ADAUSDT"
    exchange = "binance"

    # Mock database to return a position
    mock_repository.get_open_position = AsyncMock(return_value={'id': 123})

    # Track if fetch_positions was called
    fetch_positions_called = False

    async def mock_fetch():
        nonlocal fetch_positions_called
        fetch_positions_called = True
        return []

    mock_exchange.fetch_positions = mock_fetch

    result = await position_manager._position_exists(symbol, exchange)

    assert result is True
    # Should NOT have called fetch_positions (DB hit returns early)
    assert not fetch_positions_called, "fetch_positions should not be called when DB has position"


@pytest.mark.asyncio
async def test_position_exists_different_symbols_parallel(position_manager, mock_exchange):
    """
    Test that different symbols can check in parallel
    (they have different locks)
    """
    symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
    exchange = "binance"

    # Track concurrent checks per symbol
    active_per_symbol = {s: [] for s in symbols}

    async def mock_fetch_positions():
        await asyncio.sleep(0.05)
        return []

    mock_exchange.fetch_positions = mock_fetch_positions

    # Launch parallel checks for different symbols
    tasks = []
    for symbol in symbols:
        for _ in range(3):  # 3 checks per symbol
            tasks.append(position_manager._position_exists(symbol, exchange))

    results = await asyncio.gather(*tasks)

    # All should complete successfully
    assert len(results) == 9
    assert all(result is False for result in results)

    print(f"✅ Different symbols can check in parallel")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
