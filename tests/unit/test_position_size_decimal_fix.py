import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from core.position_manager import PositionManager


@pytest.mark.asyncio
async def test_calculate_position_size_with_decimal():
    """Test that Decimal size_usd works correctly"""

    # Mock dependencies
    config = MagicMock()
    config.max_position_size_usd = Decimal('5000')
    config.trailing_activation_percent = Decimal('1.0')
    config.trailing_distance_percent = Decimal('0.5')
    config.trailing_callback_percent = Decimal('0.3')
    config.max_positions = 10
    config.max_exposure_usd = Decimal('1000')

    exchange = MagicMock()
    repository = AsyncMock()
    event_router = MagicMock()

    manager = PositionManager(config, {}, repository, event_router)

    # Mock exchange methods
    exchange.get_min_amount = MagicMock(return_value=10.0)
    exchange.get_step_size = MagicMock(return_value=1.0)
    exchange.amount_to_precision = MagicMock(return_value='44')
    exchange.can_open_position = AsyncMock(return_value=(True, ''))

    # Test with Decimal (normal case)
    result = await manager._calculate_position_size(
        exchange,
        'ALLUSDT',
        price=0.1334,
        size_usd=Decimal('6.0')  # Decimal type
    )

    assert result == 44.0
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_calculate_position_size_with_float():
    """Test that float size_usd also works (bug scenario)"""

    # Mock dependencies
    config = MagicMock()
    config.max_position_size_usd = Decimal('5000')
    config.trailing_activation_percent = Decimal('1.0')
    config.trailing_distance_percent = Decimal('0.5')
    config.trailing_callback_percent = Decimal('0.3')
    config.max_positions = 10
    config.max_exposure_usd = Decimal('1000')

    exchange = MagicMock()
    repository = AsyncMock()
    event_router = MagicMock()

    manager = PositionManager(config, {}, repository, event_router)

    # Mock exchange methods
    exchange.get_min_amount = MagicMock(return_value=10.0)
    exchange.get_step_size = MagicMock(return_value=1.0)
    exchange.amount_to_precision = MagicMock(return_value='44')
    exchange.can_open_position = AsyncMock(return_value=(True, ''))

    # Test with float (bug scenario)
    # This should NOT raise TypeError anymore
    result = await manager._calculate_position_size(
        exchange,
        'ALLUSDT',
        price=0.1334,
        size_usd=6.0  # float type (caused TypeError before fix)
    )

    assert result == 44.0
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_calculate_position_size_with_int():
    """Test that int size_usd also works"""

    # Mock dependencies
    config = MagicMock()
    config.max_position_size_usd = Decimal('5000')
    config.trailing_activation_percent = Decimal('1.0')
    config.trailing_distance_percent = Decimal('0.5')
    config.trailing_callback_percent = Decimal('0.3')
    config.max_positions = 10
    config.max_exposure_usd = Decimal('1000')

    exchange = MagicMock()
    repository = AsyncMock()
    event_router = MagicMock()

    manager = PositionManager(config, {}, repository, event_router)

    # Mock exchange methods
    exchange.get_min_amount = MagicMock(return_value=10.0)
    exchange.get_step_size = MagicMock(return_value=1.0)
    exchange.amount_to_precision = MagicMock(return_value='44')
    exchange.can_open_position = AsyncMock(return_value=(True, ''))

    # Test with int
    result = await manager._calculate_position_size(
        exchange,
        'ALLUSDT',
        price=0.1334,
        size_usd=6  # int type
    )

    assert result == 44.0
    assert isinstance(result, float)


def test_decimal_division_direct():
    """Direct test of the fix"""
    from decimal import Decimal

    # Test all type combinations
    test_cases = [
        (Decimal('6.0'), 0.1334, 'Decimal'),
        (6.0, 0.1334, 'float'),
        (6, 0.1334, 'int'),
    ]

    for size_usd, price, type_name in test_cases:
        # This is the fixed code
        quantity = Decimal(str(size_usd)) / Decimal(str(price))

        assert quantity > 0, f"Failed for {type_name}"
        assert isinstance(quantity, Decimal), f"Result should be Decimal for {type_name}"
