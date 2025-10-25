"""
Unit tests for Binance Entry Price Fix

Tests verify:
1. newOrderRespType='FULL' is set for Binance market orders
2. entry_price in database is updated with execution price
3. Execution price is correctly extracted from response
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.atomic_position_manager import AtomicPositionManager
from core.exchange_response_adapter import ExchangeResponseAdapter


@pytest.mark.asyncio
async def test_binance_market_order_uses_full_response_type():
    """Verify Binance market orders use newOrderRespType=FULL"""

    # Setup mocks
    repository = AsyncMock()
    exchange_manager = {
        'binance': AsyncMock()
    }

    # Mock order response with avgPrice (as returned by FULL response type)
    exchange_manager['binance'].create_market_order = AsyncMock(
        return_value={
            'id': '12345',
            'symbol': 'BTCUSDT',
            'status': 'FILLED',
            'average': 50123.45,
            'filled': 0.001,
            'side': 'buy',
            'amount': 0.001,
            'price': 0,
            'info': {
                'avgPrice': '50123.45',
                'status': 'FILLED',
                'executedQty': '0.001',
                'fills': [
                    {
                        'price': '50123.45',
                        'qty': '0.001',
                        'commission': '0.05012345',
                        'commissionAsset': 'USDT'
                    }
                ]
            }
        }
    )

    exchange_manager['binance'].fetch_positions = AsyncMock(return_value=[])
    exchange_manager['binance'].set_leverage = AsyncMock(return_value=True)

    stop_loss_manager = AsyncMock()
    stop_loss_manager.set_stop_loss = AsyncMock(
        return_value={
            'status': 'created',
            'orderId': '67890',
            'stopPrice': 49120.00
        }
    )

    # Create manager
    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager
    )

    # Mock repository methods
    repository.create_position = AsyncMock(return_value=1)
    repository.update_position = AsyncMock()
    repository.create_order = AsyncMock()
    repository.create_trade = AsyncMock()

    # Execute
    result = await manager.open_position_atomic(
        signal_id=123,
        symbol='BTCUSDT',
        exchange='binance',
        side='buy',
        quantity=0.001,
        entry_price=50120.00,  # Signal price
        stop_loss_percent=2.0
    )

    # Verify newOrderRespType=FULL was passed
    call_args = exchange_manager['binance'].create_market_order.call_args

    assert call_args is not None, "create_market_order was not called"

    # Check kwargs for params
    params = call_args.kwargs.get('params', {})

    assert 'newOrderRespType' in params, "newOrderRespType not in params"
    assert params['newOrderRespType'] == 'FULL', f"Expected FULL, got {params['newOrderRespType']}"

    # Verify execution price was extracted and returned
    assert result is not None, "Result should not be None"
    assert result['entry_price'] == 50123.45, f"Expected exec price 50123.45, got {result['entry_price']}"
    assert result['signal_price'] == 50120.00, f"Expected signal price 50120.00, got {result.get('signal_price')}"

    # Verify database was updated with execution price
    # Find the update_position call
    update_calls = repository.update_position.call_args_list
    assert len(update_calls) > 0, "update_position was not called"

    # Check the update call (should be the first one)
    update_kwargs = update_calls[0].kwargs

    assert 'entry_price' in update_kwargs, "entry_price not updated in database"
    assert update_kwargs['entry_price'] == 50123.45, \
        f"Expected DB entry_price=50123.45, got {update_kwargs['entry_price']}"


@pytest.mark.asyncio
async def test_binance_entry_price_updated_in_database():
    """Verify entry_price field in database is updated with execution price"""

    # Setup mocks
    repository = AsyncMock()
    exchange_manager = {
        'binance': AsyncMock()
    }

    # Mock order with different signal vs execution price
    signal_price = 100.00
    exec_price = 100.15  # 0.15% slippage

    exchange_manager['binance'].create_market_order = AsyncMock(
        return_value={
            'id': 'order123',
            'symbol': 'ETHUSDT',
            'status': 'FILLED',
            'average': exec_price,
            'filled': 0.01,
            'side': 'buy',
            'amount': 0.01,
            'price': 0,
            'info': {
                'avgPrice': str(exec_price),
                'status': 'FILLED'
            }
        }
    )

    exchange_manager['binance'].fetch_positions = AsyncMock(return_value=[])
    exchange_manager['binance'].set_leverage = AsyncMock(return_value=True)

    stop_loss_manager = AsyncMock()
    stop_loss_manager.set_stop_loss = AsyncMock(
        return_value={'status': 'created', 'orderId': 'sl123'}
    )

    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager
    )

    repository.create_position = AsyncMock(return_value=999)
    repository.update_position = AsyncMock()
    repository.create_order = AsyncMock()
    repository.create_trade = AsyncMock()

    # Execute
    result = await manager.open_position_atomic(
        signal_id=456,
        symbol='ETHUSDT',
        exchange='binance',
        side='buy',
        quantity=0.01,
        entry_price=signal_price,
        stop_loss_percent=2.0
    )

    # Verify update_position was called with exec_price
    update_calls = repository.update_position.call_args_list
    assert len(update_calls) > 0

    update_kwargs = update_calls[0].kwargs

    # Check both entry_price and current_price were updated
    assert update_kwargs.get('entry_price') == exec_price, \
        f"entry_price should be {exec_price}, got {update_kwargs.get('entry_price')}"
    assert update_kwargs.get('current_price') == exec_price, \
        f"current_price should be {exec_price}, got {update_kwargs.get('current_price')}"


@pytest.mark.asyncio
async def test_binance_fallback_when_avgprice_zero():
    """Test Binance fallback fetches position when avgPrice is 0"""

    # Setup mocks
    repository = AsyncMock()
    exchange_manager = {
        'binance': AsyncMock()
    }

    # Mock order response WITHOUT avgPrice (returns 0)
    exchange_manager['binance'].create_market_order = AsyncMock(
        return_value={
            'id': 'order456',
            'symbol': 'ADAUSDT',
            'status': 'FILLED',
            'average': 0,  # avgPrice not available
            'filled': 10,
            'side': 'buy',
            'amount': 10,
            'price': 0,
            'info': {
                'avgPrice': '0.00000',  # Binance returns 0 string
                'status': 'FILLED'
            }
        }
    )

    # Mock fetch_positions to return actual entry price
    exchange_manager['binance'].fetch_positions = AsyncMock(
        return_value=[
            {
                'symbol': 'ADAUSDT',
                'contracts': 10,
                'entryPrice': 0.5234,  # Actual execution price from position
                'side': 'long'
            }
        ]
    )
    exchange_manager['binance'].set_leverage = AsyncMock(return_value=True)

    stop_loss_manager = AsyncMock()
    stop_loss_manager.set_stop_loss = AsyncMock(
        return_value={'status': 'created', 'orderId': 'sl456'}
    )

    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager
    )

    repository.create_position = AsyncMock(return_value=777)
    repository.update_position = AsyncMock()
    repository.create_order = AsyncMock()
    repository.create_trade = AsyncMock()

    # Execute
    result = await manager.open_position_atomic(
        signal_id=789,
        symbol='ADAUSDT',
        exchange='binance',
        side='buy',
        quantity=10,
        entry_price=0.52,  # Signal price
        stop_loss_percent=2.0
    )

    # Verify fetch_positions was called (fallback triggered)
    exchange_manager['binance'].fetch_positions.assert_called_once()

    # Verify execution price from position was used
    update_calls = repository.update_position.call_args_list
    update_kwargs = update_calls[0].kwargs

    assert update_kwargs.get('entry_price') == 0.5234, \
        f"Should use entryPrice from position, got {update_kwargs.get('entry_price')}"
