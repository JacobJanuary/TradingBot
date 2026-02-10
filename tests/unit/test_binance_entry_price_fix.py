"""
Unit tests for Binance Entry Price Fix

Tests verify:
1. newOrderRespType='FULL' is set for Binance market orders
2. entry_price in database is updated with execution price
3. Execution price is correctly extracted from response
"""

import asyncio
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from core.atomic_position_manager import AtomicPositionManager
from core.exchange_response_adapter import ExchangeResponseAdapter


def _setup_repository():
    """Create a properly mocked repository with pool.acquire context manager."""
    repository = AsyncMock()
    
    # Mock pool.acquire() async context manager
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)  # No duplicate positions
    mock_conn.execute = AsyncMock()
    
    @asynccontextmanager
    async def mock_acquire():
        yield mock_conn
    
    repository.pool = MagicMock()
    repository.pool.acquire = mock_acquire
    
    repository.create_position = AsyncMock(return_value=1)
    repository.update_position = AsyncMock()
    repository.create_order = AsyncMock()
    repository.create_trade = AsyncMock()
    repository.get_position = AsyncMock(return_value=None)
    
    return repository


class MockOrder:
    """Mock CCXT Order object that supports both attribute and dict access."""

    def __init__(self, data: dict):
        self._data = data
        for k, v in data.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def keys(self):
        return self._data.keys()


def _make_request(signal_id, symbol, exchange, side, entry_price):
    """Create a mock PositionRequest object."""
    req = MagicMock()
    req.signal_id = signal_id
    req.symbol = symbol
    req.exchange = exchange
    req.side = side
    req.entry_price = entry_price
    return req


def _make_config(stop_loss_percent=2.0, trailing_activation=1.0, trailing_callback=0.5,
                 auto_set_leverage=True, leverage=10):
    """Create a mock TradingConfig object."""
    cfg = MagicMock()
    cfg.stop_loss_percent = stop_loss_percent
    cfg.trailing_activation_percent = trailing_activation
    cfg.trailing_callback_percent = trailing_callback
    cfg.auto_set_leverage = auto_set_leverage
    cfg.leverage = leverage
    return cfg


def _make_binance_order(order_id, symbol, side, amount, filled, avg_price, info=None):
    """Create a MockOrder mimicking a CCXT Binance order response."""
    data = {
        'id': order_id,
        'symbol': symbol,
        'status': 'FILLED',
        'side': side,
        'type': 'market',
        'amount': amount,
        'filled': filled,
        'price': avg_price,
        'average': avg_price,
        'info': info or {
            'avgPrice': str(avg_price),
            'status': 'FILLED',
            'executedQty': str(filled),
            'origQty': str(amount),
            'side': side.upper(),
            'symbol': symbol,
        }
    }
    return MockOrder(data)


@pytest.mark.asyncio
async def test_binance_market_order_uses_full_response_type():
    """Verify Binance market orders use newOrderRespType=FULL"""

    repository = _setup_repository()
    exchange_instance = AsyncMock()

    # Raw order returned by create_market_order (pre-fetch, may have status=NEW)
    raw_order = _make_binance_order(
        '12345', 'BTCUSDT', 'buy', 0.001, 0.001, 50123.45,
        info={
            'avgPrice': '50123.45',
            'status': 'FILLED',
            'executedQty': '0.001',
            'origQty': '0.001',
            'side': 'BUY',
            'symbol': 'BTCUSDT',
            'fills': [
                {'price': '50123.45', 'qty': '0.001', 'commission': '0.05', 'commissionAsset': 'USDT'}
            ]
        }
    )

    # fetch_order returns fully filled order
    fetched_order = _make_binance_order('12345', 'BTCUSDT', 'buy', 0.001, 0.001, 50123.45)

    exchange_instance.create_market_order = AsyncMock(return_value=raw_order)
    exchange_instance.fetch_order = AsyncMock(return_value=fetched_order)
    exchange_instance.fetch_positions = AsyncMock(return_value=[])
    exchange_instance.set_leverage = AsyncMock(return_value=True)

    exchange_manager = {'binance': exchange_instance}

    stop_loss_manager = AsyncMock()
    stop_loss_manager.set_stop_loss = AsyncMock(
        return_value={'status': 'created', 'orderId': '67890', 'stopPrice': 49120.00}
    )

    config = _make_config()
    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager,
        config=config
    )

    request = _make_request(123, 'BTCUSDT', 'binance', 'buy', 50120.00)

    result = await manager.open_position_atomic(
        request=request,
        quantity=0.001,
        exchange_manager=exchange_manager
    )

    # Verify newOrderRespType=FULL was passed
    call_args = exchange_instance.create_market_order.call_args
    assert call_args is not None, "create_market_order was not called"
    params = call_args.kwargs.get('params', {})
    assert params.get('newOrderRespType') == 'FULL', f"Expected FULL, got {params.get('newOrderRespType')}"

    # Verify result contains execution price
    assert result is not None, "Result should not be None"


@pytest.mark.asyncio
async def test_binance_entry_price_updated_in_database():
    """Verify entry_price in database is updated with execution price"""

    repository = _setup_repository()
    exchange_instance = AsyncMock()

    signal_price = 100.00
    exec_price = 100.15

    raw_order = _make_binance_order('order123', 'ETHUSDT', 'buy', 0.01, 0.01, exec_price)
    fetched_order = _make_binance_order('order123', 'ETHUSDT', 'buy', 0.01, 0.01, exec_price)

    exchange_instance.create_market_order = AsyncMock(return_value=raw_order)
    exchange_instance.fetch_order = AsyncMock(return_value=fetched_order)
    exchange_instance.fetch_positions = AsyncMock(return_value=[])
    exchange_instance.set_leverage = AsyncMock(return_value=True)

    exchange_manager = {'binance': exchange_instance}

    stop_loss_manager = AsyncMock()
    stop_loss_manager.set_stop_loss = AsyncMock(
        return_value={'status': 'created', 'orderId': 'sl123'}
    )

    config = _make_config()
    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager,
        config=config
    )

    request = _make_request(456, 'ETHUSDT', 'binance', 'buy', signal_price)

    result = await manager.open_position_atomic(
        request=request,
        quantity=0.01,
        exchange_manager=exchange_manager
    )

    # Verify position was created with execution price (not signal price)
    create_calls = repository.create_position.call_args_list
    assert len(create_calls) > 0, "create_position was not called"
    pos_data = create_calls[0][0][0] if create_calls[0][0] else create_calls[0].kwargs
    assert pos_data.get('entry_price') == exec_price, \
        f"entry_price should be exec_price {exec_price}, got {pos_data.get('entry_price')}"


@pytest.mark.asyncio
async def test_binance_fallback_when_avgprice_zero():
    """Test Binance fallback fetches position when avgPrice is 0"""

    repository = _setup_repository()
    exchange_instance = AsyncMock()

    # Order response with avgPrice=0
    raw_order = _make_binance_order('order456', 'ADAUSDT', 'buy', 10, 10, 0,
        info={
            'avgPrice': '0.00000',
            'status': 'FILLED',
            'executedQty': '10',
            'origQty': '10',
            'side': 'BUY',
            'symbol': 'ADAUSDT',
        }
    )
    fetched_order = _make_binance_order('order456', 'ADAUSDT', 'buy', 10, 10, 0,
        info={
            'avgPrice': '0.00000',
            'status': 'FILLED',
            'executedQty': '10',
            'origQty': '10',
            'side': 'BUY',
            'symbol': 'ADAUSDT',
        }
    )

    exchange_instance.create_market_order = AsyncMock(return_value=raw_order)
    exchange_instance.fetch_order = AsyncMock(return_value=fetched_order)
    # Fallback: fetch_positions returns entry price
    exchange_instance.fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'ADAUSDT',
            'contracts': 10,
            'entryPrice': 0.5234,
            'side': 'long'
        }
    ])
    exchange_instance.set_leverage = AsyncMock(return_value=True)

    exchange_manager = {'binance': exchange_instance}

    stop_loss_manager = AsyncMock()
    stop_loss_manager.set_stop_loss = AsyncMock(
        return_value={'status': 'created', 'orderId': 'sl456'}
    )

    config = _make_config()
    manager = AtomicPositionManager(
        repository=repository,
        exchange_manager=exchange_manager,
        stop_loss_manager=stop_loss_manager,
        config=config
    )

    request = _make_request(789, 'ADAUSDT', 'binance', 'buy', 0.52)

    result = await manager.open_position_atomic(
        request=request,
        quantity=10,
        exchange_manager=exchange_manager
    )

    # Verify fetch_positions was called (fallback triggered)
    exchange_instance.fetch_positions.assert_called()

    # Verify position was created with entryPrice from position
    create_calls = repository.create_position.call_args_list
    assert len(create_calls) > 0
    pos_data = create_calls[0][0][0] if create_calls[0][0] else create_calls[0].kwargs
    assert pos_data.get('entry_price') == 0.5234, \
        f"Should use entryPrice from position, got {pos_data.get('entry_price')}"
