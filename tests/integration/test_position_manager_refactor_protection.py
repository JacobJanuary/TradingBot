"""
Integration tests for PositionManager
 
These tests protect against regression during refactoring.
MUST PASS before and after refactoring!

Test scenarios:
1. Open position flow (full cycle)
2. Close position flow
3. Zombie cleanup
4. Position synchronization
5. Stop loss management
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal
from datetime import datetime

from core.position_manager import PositionManager, PositionRequest, PositionState
from config.settings import TradingConfig


@pytest.fixture
def mock_dependencies():
    """Mock all dependencies for PositionManager"""
    return {
        'repository': AsyncMock(),
        'exchanges': {'binance': AsyncMock(), 'bybit': AsyncMock()},
        'event_router': AsyncMock(),
        'trailing_stop_manager': AsyncMock(),
        'config': TradingConfig(
            MAX_POSITION_SIZE_USD=1000.0,
            DEFAULT_STOP_LOSS_PERCENT=2.0,
            MAX_OPEN_POSITIONS=5,
            MAX_POSITION_AGE_HOURS=72
        )
    }


@pytest.fixture
def position_manager(mock_dependencies):
    """Create PositionManager with mocked dependencies"""
    manager = PositionManager(
        repository=mock_dependencies['repository'],
        exchanges=mock_dependencies['exchanges'],
        event_router=mock_dependencies['event_router'],
        trailing_stop_manager=mock_dependencies['trailing_stop_manager'],
        config=mock_dependencies['config']
    )
    return manager


class TestPositionOpeningFlow:
    """Test position opening flow - MUST WORK after refactoring"""
    
    @pytest.mark.asyncio
    async def test_open_position_success(self, position_manager, mock_dependencies):
        """Test successful position opening"""
        # Setup
        request = PositionRequest(
            signal_id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='BUY',
            entry_price=Decimal('50000.0')
        )
        
        # Mock responses
        mock_dependencies['repository'].acquire_position_lock.return_value = True
        mock_dependencies['repository'].has_open_position.return_value = False
        mock_dependencies['repository'].get_open_positions_count.return_value = 0
        mock_dependencies['repository'].get_total_balance.return_value = {'total': Decimal('10000')}
        
        exchange = mock_dependencies['exchanges']['binance']
        exchange.create_market_order.return_value = Mock(
            id='order123',
            symbol='BTC/USDT',
            side='buy',
            amount=Decimal('0.02'),
            price=Decimal('50000'),
            filled=Decimal('0.02'),
            status='closed'
        )
        exchange.create_stop_market_order.return_value = Mock(id='sl123')
        
        mock_dependencies['repository'].create_position.return_value = 1
        
        # Execute
        position = await position_manager.open_position(request)
        
        # Verify
        assert position is not None
        assert position.symbol == 'BTC/USDT'
        assert position.side in ['long', 'short']
        assert position.quantity > 0
        
        # Verify calls
        exchange.create_market_order.assert_called_once()
        mock_dependencies['repository'].create_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_open_position_duplicate_prevention(self, position_manager, mock_dependencies):
        """Test that duplicate positions are prevented"""
        request = PositionRequest(
            signal_id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='BUY',
            entry_price=Decimal('50000.0')
        )
        
        # Mock: position already exists
        mock_dependencies['repository'].has_open_position.return_value = True
        
        # Execute
        position = await position_manager.open_position(request)
        
        # Verify: position NOT created
        assert position is None
        mock_dependencies['exchanges']['binance'].create_market_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_open_position_db_lock_prevents_race_condition(self, position_manager, mock_dependencies):
        """Test that DB lock prevents race conditions"""
        request = PositionRequest(
            signal_id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='BUY',
            entry_price=Decimal('50000.0')
        )
        
        # Mock: lock NOT acquired (another instance processing)
        mock_dependencies['repository'].acquire_position_lock.return_value = False
        
        # Execute
        position = await position_manager.open_position(request)
        
        # Verify: position NOT created
        assert position is None
        mock_dependencies['exchanges']['binance'].create_market_order.assert_not_called()


class TestPositionClosingFlow:
    """Test position closing flow - MUST WORK after refactoring"""
    
    @pytest.mark.asyncio
    async def test_close_position_success(self, position_manager, mock_dependencies):
        """Test successful position closing"""
        # Setup existing position
        position = PositionState(
            id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='long',
            quantity=0.02,
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=20.0,
            opened_at=datetime.now()
        )
        position_manager.positions['BTC/USDT'] = position
        
        # Mock close order
        exchange = mock_dependencies['exchanges']['binance']
        exchange.create_market_order.return_value = Mock(
            id='close_order',
            status='closed',
            filled=Decimal('0.02')
        )
        
        mock_dependencies['repository'].close_position.return_value = True
        
        # Execute
        result = await position_manager.close_position('BTC/USDT', reason='test')
        
        # Verify
        assert result is True
        assert 'BTC/USDT' not in position_manager.positions
        exchange.create_market_order.assert_called_once()
        mock_dependencies['repository'].close_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_nonexistent_position(self, position_manager, mock_dependencies):
        """Test closing nonexistent position"""
        # Execute
        result = await position_manager.close_position('BTC/USDT', reason='test')
        
        # Verify: graceful handling
        assert result is False
        mock_dependencies['exchanges']['binance'].create_market_order.assert_not_called()


class TestZombieCleanup:
    """Test zombie order cleanup - MUST WORK after refactoring"""
    
    @pytest.mark.asyncio
    async def test_zombie_cleanup_basic(self, position_manager, mock_dependencies):
        """Test basic zombie cleanup"""
        # Setup: exchange has open orders but no positions in DB
        exchange = mock_dependencies['exchanges']['binance']
        exchange.fetch_open_orders.return_value = [
            {'id': 'order1', 'symbol': 'BTC/USDT', 'type': 'limit', 'side': 'buy'},
            {'id': 'order2', 'symbol': 'ETH/USDT', 'type': 'limit', 'side': 'sell'}
        ]
        
        mock_dependencies['repository'].get_active_positions.return_value = []  # No positions
        
        # Execute
        await position_manager.cleanup_zombie_orders()
        
        # Verify: orders should be cancelled
        assert exchange.cancel_order.call_count > 0
    
    @pytest.mark.asyncio
    async def test_handle_real_zombies(self, position_manager, mock_dependencies):
        """Test handling of real zombie positions"""
        # Setup: DB has positions that don't exist on exchange
        mock_dependencies['repository'].get_active_positions.return_value = [
            {
                'id': 1,
                'symbol': 'BTC/USDT',
                'exchange': 'binance',
                'side': 'long',
                'quantity': 0.02
            }
        ]
        
        exchange = mock_dependencies['exchanges']['binance']
        exchange.fetch_positions.return_value = []  # No positions on exchange
        
        # Execute
        await position_manager.handle_real_zombies()
        
        # Verify: position should be closed in DB
        mock_dependencies['repository'].close_position.assert_called()


class TestPositionSynchronization:
    """Test position synchronization - MUST WORK after refactoring"""
    
    @pytest.mark.asyncio
    async def test_sync_with_exchange(self, position_manager, mock_dependencies):
        """Test synchronization with exchange"""
        # Setup
        exchange = mock_dependencies['exchanges']['binance']
        exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC/USDT',
                'contracts': 0.02,
                'side': 'long',
                'entryPrice': 50000,
                'unrealizedPnl': 20
            }
        ]
        
        mock_dependencies['repository'].get_active_positions.return_value = []
        mock_dependencies['repository'].create_position.return_value = 1
        
        # Execute
        await position_manager.sync_exchange_positions('binance')
        
        # Verify: position created
        mock_dependencies['repository'].create_position.assert_called_once()


class TestStopLossManagement:
    """Test stop loss management - MUST WORK after refactoring"""
    
    @pytest.mark.asyncio
    async def test_stop_loss_set_on_open(self, position_manager, mock_dependencies):
        """Test that stop loss is set when opening position"""
        request = PositionRequest(
            signal_id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='BUY',
            entry_price=Decimal('50000.0'),
            stop_loss_percent=2.0
        )
        
        # Mock successful order
        mock_dependencies['repository'].acquire_position_lock.return_value = True
        mock_dependencies['repository'].has_open_position.return_value = False
        mock_dependencies['repository'].get_open_positions_count.return_value = 0
        mock_dependencies['repository'].get_total_balance.return_value = {'total': Decimal('10000')}
        
        exchange = mock_dependencies['exchanges']['binance']
        exchange.create_market_order.return_value = Mock(
            id='order123',
            filled=Decimal('0.02'),
            price=Decimal('50000'),
            status='closed'
        )
        exchange.create_stop_market_order.return_value = Mock(id='sl123')
        
        mock_dependencies['repository'].create_position.return_value = 1
        
        # Execute
        position = await position_manager.open_position(request)
        
        # Verify: stop loss order created
        exchange.create_stop_market_order.assert_called_once()


class TestRiskValidation:
    """Test risk validation - MUST WORK after refactoring"""
    
    @pytest.mark.asyncio
    async def test_max_positions_limit(self, position_manager, mock_dependencies):
        """Test that max positions limit is enforced"""
        request = PositionRequest(
            signal_id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='BUY',
            entry_price=Decimal('50000.0')
        )
        
        # Mock: already at max positions
        mock_dependencies['repository'].get_open_positions_count.return_value = 5
        mock_dependencies['repository'].acquire_position_lock.return_value = True
        mock_dependencies['repository'].has_open_position.return_value = False
        
        # Execute
        position = await position_manager.open_position(request)
        
        # Verify: position NOT created
        assert position is None
        mock_dependencies['exchanges']['binance'].create_market_order.assert_not_called()


class TestStatistics:
    """Test statistics gathering - MUST WORK after refactoring"""
    
    def test_get_statistics(self, position_manager):
        """Test statistics gathering"""
        # Add some test positions
        position_manager.positions['BTC/USDT'] = PositionState(
            id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='long',
            quantity=0.02,
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=20.0,
            opened_at=datetime.now()
        )
        
        # Execute
        stats = position_manager.get_statistics()
        
        # Verify
        assert 'total_positions' in stats
        assert stats['total_positions'] == 1
        assert 'open_positions' in stats


# Regression test marker
pytestmark = pytest.mark.regression

