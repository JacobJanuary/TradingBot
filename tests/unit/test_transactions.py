"""
Unit tests for database transactions
Tests that transactions properly commit on success and rollback on failure
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from database.repository import Repository


@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool"""
    pool = AsyncMock()
    return pool


@pytest.fixture
def repository(mock_pool):
    """Repository with mocked pool"""
    repo = Repository({'host': 'localhost', 'port': 5432, 'database': 'test', 'user': 'test', 'password': 'test'})
    repo.pool = mock_pool
    return repo


class TestTransactionContextManager:
    """Test Transaction context manager"""
    
    @pytest.mark.asyncio
    async def test_transaction_commits_on_success(self, repository, mock_pool):
        """Test that transaction commits when no exception occurs"""
        # Setup mocks
        mock_conn = AsyncMock()
        mock_transaction = AsyncMock()
        mock_pool.acquire.return_value = mock_conn
        mock_conn.transaction.return_value = mock_transaction
        
        # Use transaction
        async with repository.transaction() as conn:
            assert conn == mock_conn
            # No exception - should commit
        
        # Verify transaction was started and committed
        mock_transaction.start.assert_called_once()
        mock_transaction.commit.assert_called_once()
        mock_transaction.rollback.assert_not_called()
        mock_pool.release.assert_called_once_with(mock_conn)
    
    @pytest.mark.asyncio
    async def test_transaction_rollbacks_on_exception(self, repository, mock_pool):
        """Test that transaction rolls back when exception occurs"""
        # Setup mocks
        mock_conn = AsyncMock()
        mock_transaction = AsyncMock()
        mock_pool.acquire.return_value = mock_conn
        mock_conn.transaction.return_value = mock_transaction
        
        # Use transaction with exception
        with pytest.raises(ValueError):
            async with repository.transaction() as conn:
                raise ValueError("Test error")
        
        # Verify transaction was started and rolled back
        mock_transaction.start.assert_called_once()
        mock_transaction.rollback.assert_called_once()
        mock_transaction.commit.assert_not_called()
        mock_pool.release.assert_called_once_with(mock_conn)
    
    @pytest.mark.asyncio
    async def test_transaction_releases_connection_on_error(self, repository, mock_pool):
        """Test that connection is released even if commit/rollback fails"""
        # Setup mocks
        mock_conn = AsyncMock()
        mock_transaction = AsyncMock()
        mock_transaction.rollback.side_effect = Exception("Rollback error")
        mock_pool.acquire.return_value = mock_conn
        mock_conn.transaction.return_value = mock_transaction
        
        # Use transaction with exception
        with pytest.raises(ValueError):
            async with repository.transaction() as conn:
                raise ValueError("Test error")
        
        # Verify connection was still released despite rollback error
        mock_pool.release.assert_called_once_with(mock_conn)


class TestTransactionSupportInMethods:
    """Test that repository methods support transactions"""
    
    @pytest.mark.asyncio
    async def test_create_trade_with_connection(self, repository):
        """Test create_trade uses provided connection"""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 123
        
        trade_data = {
            'symbol': 'BTC/USDT',
            'exchange': 'binance',
            'side': 'buy',
            'quantity': 0.001,
            'price': 50000.0,
            'order_id': '12345',
            'status': 'FILLED'
        }
        
        trade_id = await repository.create_trade(trade_data, conn=mock_conn)
        
        assert trade_id == 123
        mock_conn.fetchval.assert_called_once()
        # Should NOT acquire from pool when conn is provided
        repository.pool.acquire.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_create_trade_without_connection(self, repository, mock_pool):
        """Test create_trade acquires connection when not provided"""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 123
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        trade_data = {
            'symbol': 'BTC/USDT',
            'exchange': 'binance',
            'side': 'buy',
            'quantity': 0.001,
            'price': 50000.0,
            'order_id': '12345',
            'status': 'FILLED'
        }
        
        trade_id = await repository.create_trade(trade_data)
        
        assert trade_id == 123
        mock_conn.fetchval.assert_called_once()
        # Should acquire from pool when conn is not provided
        mock_pool.acquire.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_position_with_connection(self, repository):
        """Test create_position uses provided connection"""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 456
        
        position_data = {
            'symbol': 'BTC/USDT',
            'exchange': 'binance',
            'side': 'long',
            'quantity': 0.001,
            'entry_price': 50000.0
        }
        
        position_id = await repository.create_position(position_data, conn=mock_conn)
        
        assert position_id == 456
        mock_conn.fetchval.assert_called_once()
        repository.pool.acquire.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_update_position_stop_loss_with_connection(self, repository):
        """Test update_position_stop_loss uses provided connection"""
        mock_conn = AsyncMock()
        
        await repository.update_position_stop_loss(
            position_id=456,
            stop_price=48000.0,
            order_id='sl_123',
            conn=mock_conn
        )
        
        mock_conn.execute.assert_called_once()
        repository.pool.acquire.assert_not_called()


class TestAtomicOperations:
    """Test atomic operations using transactions"""
    
    @pytest.mark.asyncio
    async def test_atomic_position_creation(self, repository, mock_pool):
        """Test that position creation is atomic"""
        # Setup mocks
        mock_conn = AsyncMock()
        mock_transaction = AsyncMock()
        mock_conn.transaction.return_value = mock_transaction
        mock_conn.fetchval.side_effect = [123, 456]  # trade_id, position_id
        mock_pool.acquire.return_value = mock_conn
        
        # Atomic operation
        async with repository.transaction() as conn:
            trade_id = await repository.create_trade({
                'symbol': 'BTC/USDT',
                'exchange': 'binance',
                'side': 'buy',
                'quantity': 0.001,
                'price': 50000.0,
                'order_id': '12345',
                'status': 'FILLED'
            }, conn=conn)
            
            position_id = await repository.create_position({
                'symbol': 'BTC/USDT',
                'exchange': 'binance',
                'side': 'long',
                'quantity': 0.001,
                'entry_price': 50000.0
            }, conn=conn)
        
        assert trade_id == 123
        assert position_id == 456
        # Both operations in same transaction
        assert mock_conn.fetchval.call_count == 2
        mock_transaction.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_atomic_rollback_on_second_operation_failure(self, repository, mock_pool):
        """Test that first operation is rolled back if second fails"""
        # Setup mocks
        mock_conn = AsyncMock()
        mock_transaction = AsyncMock()
        mock_conn.transaction.return_value = mock_transaction
        mock_conn.fetchval.side_effect = [123, Exception("Position creation failed")]
        mock_pool.acquire.return_value = mock_conn
        
        # Atomic operation with failure
        with pytest.raises(Exception):
            async with repository.transaction() as conn:
                trade_id = await repository.create_trade({
                    'symbol': 'BTC/USDT',
                    'exchange': 'binance',
                    'side': 'buy',
                    'quantity': 0.001,
                    'price': 50000.0,
                    'order_id': '12345',
                    'status': 'FILLED'
                }, conn=conn)
                
                # This will fail
                position_id = await repository.create_position({
                    'symbol': 'BTC/USDT',
                    'exchange': 'binance',
                    'side': 'long',
                    'quantity': 0.001,
                    'entry_price': 50000.0
                }, conn=conn)
        
        # Transaction should rollback
        mock_transaction.rollback.assert_called_once()
        mock_transaction.commit.assert_not_called()

