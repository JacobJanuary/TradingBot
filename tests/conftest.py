"""
Pytest configuration and shared fixtures for all tests
"""

import pytest
import asyncio
from typing import Dict, Any, AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, MagicMock
import tempfile
import os

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Position, Order, Trade
from core.exchange_manager import ExchangeManager
from core.risk_manager import RiskManager


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config() -> Dict[str, Any]:
    """Test configuration"""
    return {
        'exchanges': {
            'binance': {
                'api_key': 'test_api_key',
                'api_secret': 'test_api_secret',
                'testnet': True
            },
            'bybit': {
                'api_key': 'test_api_key',
                'api_secret': 'test_api_secret',
                'testnet': True
            }
        },
        'database': {
            'url': 'postgresql://test:test@localhost/test_trading',
            'pool_size': 5,
            'echo': False
        },
        'risk': {
            'max_position_size': 10000,
            'max_daily_loss': 1000,
            'max_open_positions': 5,
            'default_stop_loss': 2.0
        },
        'monitoring': {
            'metrics_port': 8001,
            'health_check_interval': 30
        }
    }


@pytest.fixture
def mock_exchange() -> AsyncMock:
    """Mock exchange for testing"""
    exchange = AsyncMock()
    
    # Mock common exchange methods
    exchange.fetch_ticker = AsyncMock(return_value={
        'symbol': 'BTC/USDT',
        'last': 50000.0,
        'bid': 49999.0,
        'ask': 50001.0,
        'volume': 1000.0
    })
    
    exchange.fetch_balance = AsyncMock(return_value={
        'USDT': {'free': 10000.0, 'used': 0.0, 'total': 10000.0},
        'BTC': {'free': 0.5, 'used': 0.0, 'total': 0.5}
    })
    
    exchange.fetch_order_book = AsyncMock(return_value={
        'bids': [[49999.0, 1.0], [49998.0, 2.0]],
        'asks': [[50001.0, 1.0], [50002.0, 2.0]]
    })
    
    exchange.create_order = AsyncMock(return_value={
        'id': 'test_order_123',
        'symbol': 'BTC/USDT',
        'type': 'limit',
        'side': 'buy',
        'price': 49999.0,
        'amount': 0.1,
        'status': 'open'
    })
    
    exchange.cancel_order = AsyncMock(return_value={'id': 'test_order_123', 'status': 'canceled'})
    
    exchange.fetch_ohlcv = AsyncMock(return_value=[
        [1234567890000, 50000, 50100, 49900, 50050, 100],
        [1234567891000, 50050, 50150, 49950, 50100, 110],
        [1234567892000, 50100, 50200, 50000, 50150, 120]
    ])
    
    return exchange


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock repository for testing"""
    repo = AsyncMock()
    
    # Mock repository methods
    repo.get_active_positions = AsyncMock(return_value=[])
    repo.get_open_orders = AsyncMock(return_value=[])
    repo.create_position = AsyncMock(return_value=True)
    repo.update_position = AsyncMock(return_value=True)
    repo.create_order = AsyncMock(return_value=True)

    return repo


@pytest.fixture
def sample_position() -> Position:
    """Sample position for testing"""
    return Position(
        id=1,  # Integer primary key
        trade_id=1,
        exchange='binance',
        symbol='BTC/USDT',
        side='long',
        quantity=0.1,
        entry_price=50000.0,
        status='OPEN',
        opened_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_order() -> Order:
    """Sample order for testing"""
    return Order(
        id='order_456',
        position_id='pos_123',
        exchange='binance',
        symbol='BTC/USDT',
        type='limit',
        side='buy',
        price=49999.0,
        size=0.1,
        status='open',
        created_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_signal() -> dict:
    """Sample signal for testing (WebSocket format)"""
    return {
        'id': 'sig_789',
        'source': 'strategy_1',
        'symbol': 'BTC/USDT',
        'action': 'open_long',
        'strength': 0.8,
        'entry_price': 50000,
        'stop_loss': 49000,
        'take_profit': 51000,
        'created_at': datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
async def mock_websocket():
    """Mock WebSocket connection"""
    ws = AsyncMock()
    
    ws.connect = AsyncMock()
    ws.disconnect = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(return_value={
        'e': 'trade',
        's': 'BTCUSDT',
        'p': '50000.00',
        'q': '0.1'
    })
    
    return ws


@pytest.fixture
def mock_exchange_manager(mock_exchange, mock_repository) -> ExchangeManager:
    """Mock exchange manager"""
    manager = Mock(spec=ExchangeManager)
    manager.exchanges = {'binance': mock_exchange, 'bybit': mock_exchange}
    manager.repository = mock_repository
    manager.initialize = AsyncMock()
    manager.create_order = AsyncMock(return_value={'id': 'test_order'})
    manager.cancel_order = AsyncMock(return_value=True)
    manager.close_position = AsyncMock(return_value=True)
    
    return manager


@pytest.fixture
def mock_risk_manager(test_config) -> RiskManager:
    """Mock risk manager"""
    manager = Mock(spec=RiskManager)
    manager.config = test_config['risk']
    manager.check_position_limit = Mock(return_value=True)
    manager.check_daily_loss_limit = Mock(return_value=True)
    manager.calculate_position_size = Mock(return_value=Decimal('0.1'))
    manager.validate_order = Mock(return_value=True)
    
    return manager


@pytest.fixture
def temp_db():
    """Temporary SQLite database for testing"""
    import sqlalchemy
    from sqlalchemy.orm import sessionmaker
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    engine = sqlalchemy.create_engine(f'sqlite:///{db_path}')
    
    # Create tables
    from database.models import Base
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    
    yield {
        'engine': engine,
        'session': Session,
        'path': db_path
    }
    
    # Cleanup
    engine.dispose()
    os.unlink(db_path)


@pytest.fixture
async def mock_metrics_collector():
    """Mock metrics collector"""
    collector = AsyncMock()
    collector.record_position_opened = Mock()
    collector.record_position_closed = Mock()
    collector.record_order_placed = Mock()
    collector.record_error = Mock()
    collector.update_price = Mock()
    
    return collector


@pytest.fixture
def mock_logger():
    """Mock logger for testing"""
    logger = Mock()
    logger.info = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.debug = Mock()
    
    return logger