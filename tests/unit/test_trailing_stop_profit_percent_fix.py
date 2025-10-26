"""
Unit test for profit_percent UnboundLocalError fix
"""
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from protection.trailing_stop import SmartTrailingStopManager, TrailingStopInstance, TrailingStopState


@pytest.mark.asyncio
async def test_profit_percent_available_in_peak_save_logging():
    """
    Test that profit_percent is calculated before being used in logging

    Reproduces the UnboundLocalError bug scenario:
    - Trailing stop is ACTIVE
    - Peak is updated
    - should_save returns True
    - Logging uses profit_percent
    """

    # Setup
    config = MagicMock()
    config.activation_percent = Decimal('2')
    config.callback_percent = Decimal('0.5')
    config.use_atr = False
    config.atr_multiplier = Decimal('2.0')
    config.step_activation = False
    config.breakeven_at = None
    config.time_based_activation = False
    config.min_position_age_minutes = 10
    config.accelerate_on_momentum = False
    config.momentum_threshold = Decimal('0.1')

    repository = AsyncMock()
    exchange_manager = MagicMock()

    manager = SmartTrailingStopManager(
        exchange_manager=exchange_manager,
        config=config,
        exchange_name='binance',
        repository=repository
    )

    # Create trailing stop instance in ACTIVE state
    ts = TrailingStopInstance(
        symbol='TESTUSDT',
        entry_price=Decimal('100'),
        current_price=Decimal('102'),  # 2% profit
        highest_price=Decimal('102'),
        lowest_price=Decimal('100'),
        state=TrailingStopState.ACTIVE,
        activation_price=Decimal('102'),
        current_stop_price=Decimal('101'),
        stop_order_id='test_order_123',
        created_at=datetime.now(),
        activated_at=datetime.now(),
        highest_profit_percent=Decimal('0'),
        update_count=0,
        side='long',
        quantity=Decimal('10')
    )

    # Add to manager
    manager.positions['TESTUSDT'] = ts

    # Mock _should_save_peak to return True (trigger the logging path)
    with patch.object(manager, '_should_save_peak', return_value=(True, None)):
        # Mock _save_state to avoid DB calls
        with patch.object(manager, '_save_state', new=AsyncMock()):
            # This should NOT raise UnboundLocalError
            result = await manager.update_price('TESTUSDT', 103.0)

    # Verify profit_percent was calculated
    assert ts.highest_profit_percent > Decimal('0')
    assert ts.highest_profit_percent == Decimal('3')  # (103-100)/100 * 100 = 3%

    # Verify peak was updated
    assert ts.highest_price == Decimal('103')


@pytest.mark.asyncio
async def test_profit_percent_calculated_even_when_peak_not_saved():
    """
    Test that profit_percent is always calculated, even when peak save is skipped
    """

    config = MagicMock()
    config.activation_percent = Decimal('2')
    config.callback_percent = Decimal('0.5')
    config.use_atr = False
    config.atr_multiplier = Decimal('2.0')
    config.step_activation = False
    config.breakeven_at = None
    config.time_based_activation = False
    config.min_position_age_minutes = 10
    config.accelerate_on_momentum = False
    config.momentum_threshold = Decimal('0.1')

    repository = AsyncMock()
    exchange_manager = MagicMock()

    manager = SmartTrailingStopManager(
        exchange_manager=exchange_manager,
        config=config,
        exchange_name='binance',
        repository=repository
    )

    ts = TrailingStopInstance(
        symbol='TESTUSDT',
        entry_price=Decimal('100'),
        current_price=Decimal('101'),
        highest_price=Decimal('101'),
        lowest_price=Decimal('100'),
        state=TrailingStopState.ACTIVE,
        activation_price=Decimal('102'),
        current_stop_price=Decimal('100.5'),
        stop_order_id='test_order_123',
        created_at=datetime.now(),
        activated_at=datetime.now(),
        highest_profit_percent=Decimal('0'),
        update_count=0,
        side='long',
        quantity=Decimal('10')
    )

    manager.positions['TESTUSDT'] = ts

    # Mock _should_save_peak to return False (skip save path)
    with patch.object(manager, '_should_save_peak', return_value=(False, 'test skip reason')):
        result = await manager.update_price('TESTUSDT', 102.0)

    # Verify profit_percent was still calculated
    assert ts.highest_profit_percent == Decimal('2')  # (102-100)/100 * 100 = 2%


def test_decimal_division_direct():
    """Direct test of profit_percent calculation logic"""
    from decimal import Decimal

    # Test calculation logic
    entry_price = Decimal('100')
    current_price = Decimal('103')

    # This is how _calculate_profit_percent works
    profit_percent = ((current_price - entry_price) / entry_price) * 100

    assert profit_percent == Decimal('3')
    assert isinstance(profit_percent, Decimal)
