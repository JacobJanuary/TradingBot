"""
Unit tests for Position Synchronizer bug fixes

Tests the 3-phase fix:
1. Stricter filtering (check raw positionAmt/size)
2. Extract and save exchange_order_id
3. Validation (reject positions without order_id)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.position_synchronizer import PositionSynchronizer, normalize_symbol


@pytest.fixture
def mock_repository():
    """Mock repository for testing"""
    repo = MagicMock()
    repo.pool = MagicMock()
    repo.pool.acquire = AsyncMock()
    repo.get_open_positions = AsyncMock(return_value=[])
    repo.open_position = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def mock_exchanges():
    """Mock exchanges for testing"""
    return {
        'binance': MagicMock(),
        'bybit': MagicMock()
    }


@pytest.fixture
def synchronizer(mock_repository, mock_exchanges):
    """Create synchronizer instance"""
    return PositionSynchronizer(mock_repository, mock_exchanges)


class TestStricterFiltering:
    """Test Phase 1: Stricter filtering in _fetch_exchange_positions()"""

    @pytest.mark.asyncio
    async def test_filter_binance_stale_positions(self, synchronizer):
        """Should filter Binance positions with positionAmt=0 even if contracts>0"""

        mock_exchange = MagicMock()

        # Simulate stale CCXT data: contracts>0 but positionAmt=0
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.5,  # CCXT cached value
                'info': {
                    'positionAmt': '0',  # Real exchange value
                    'symbol': 'BTCUSDT'
                }
            }
        ])

        result = await synchronizer._fetch_exchange_positions(mock_exchange, 'binance')

        # Should filter out stale position
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_filter_bybit_stale_positions(self, synchronizer):
        """Should filter Bybit positions with size=0 even if contracts>0"""

        mock_exchange = MagicMock()

        # Simulate stale CCXT data: contracts>0 but size=0
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'ETH/USDT:USDT',
                'contracts': 10,  # CCXT cached value
                'info': {
                    'size': '0',  # Real exchange value
                    'symbol': 'ETHUSDT'
                }
            }
        ])

        result = await synchronizer._fetch_exchange_positions(mock_exchange, 'bybit')

        # Should filter out stale position
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_accept_real_binance_positions(self, synchronizer):
        """Should accept Binance positions with positionAmt>0"""

        mock_exchange = MagicMock()

        # Real position with matching values
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.5,
                'info': {
                    'positionAmt': '0.5',  # Matches contracts
                    'symbol': 'BTCUSDT',
                    'positionId': '12345'
                }
            }
        ])

        result = await synchronizer._fetch_exchange_positions(mock_exchange, 'binance')

        # Should accept real position
        assert len(result) == 1
        assert result[0]['symbol'] == 'BTC/USDT:USDT'

    @pytest.mark.asyncio
    async def test_accept_real_bybit_positions(self, synchronizer):
        """Should accept Bybit positions with size>0"""

        mock_exchange = MagicMock()

        # Real position with matching values
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'ETH/USDT:USDT',
                'contracts': 10,
                'info': {
                    'size': '10',  # Matches contracts
                    'symbol': 'ETHUSDT',
                    'orderId': '67890'
                }
            }
        ])

        result = await synchronizer._fetch_exchange_positions(mock_exchange, 'bybit')

        # Should accept real position
        assert len(result) == 1
        assert result[0]['symbol'] == 'ETH/USDT:USDT'


class TestExchangeOrderIdExtraction:
    """Test Phase 2: Extract and save exchange_order_id"""

    @pytest.mark.asyncio
    async def test_extract_binance_order_id(self, synchronizer, mock_repository):
        """Should extract positionId from Binance info and pass it to open_position"""

        exchange_position = {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.5,
            'side': 'long',
            'markPrice': 50000,
            'info': {
                'positionId': '12345',
                'avgPrice': '50000',
                'positionAmt': '0.5'
            }
        }

        await synchronizer._add_missing_position('binance', exchange_position)

        # Verify open_position was called with exchange_order_id
        mock_repository.open_position.assert_called_once()
        call_args = mock_repository.open_position.call_args[0][0]

        assert 'exchange_order_id' in call_args
        assert call_args['exchange_order_id'] == '12345'

    @pytest.mark.asyncio
    async def test_extract_bybit_order_id(self, synchronizer, mock_repository):
        """Should extract orderId from Bybit info and pass it to open_position"""

        exchange_position = {
            'symbol': 'ETH/USDT:USDT',
            'contracts': 10,
            'side': 'long',
            'markPrice': 3000,
            'info': {
                'orderId': '67890',
                'avgPrice': '3000',
                'size': '10'
            }
        }

        await synchronizer._add_missing_position('bybit', exchange_position)

        # Verify open_position was called with exchange_order_id
        mock_repository.open_position.assert_called_once()
        call_args = mock_repository.open_position.call_args[0][0]

        assert 'exchange_order_id' in call_args
        assert call_args['exchange_order_id'] == '67890'


class TestValidation:
    """Test Phase 3: Validation — positions without order_id get synthetic IDs"""

    @pytest.mark.asyncio
    async def test_position_without_order_id_gets_synthetic_id(self, synchronizer, mock_repository):
        """Position without exchange_order_id should still be added with synthetic ID"""

        exchange_position = {
            'symbol': 'XRP/USDT:USDT',
            'contracts': 100,
            'side': 'long',
            'markPrice': 0.5,
            'info': {
                'avgPrice': '0.5',
                'positionAmt': '100'
                # No positionId or orderId
            }
        }

        result = await synchronizer._add_missing_position('binance', exchange_position)

        # Position should be created with synthetic order ID
        assert result is True
        mock_repository.open_position.assert_called_once()
        call_args = mock_repository.open_position.call_args[0][0]
        assert call_args['exchange_order_id'].startswith('MANUAL_BINANCE_')

    @pytest.mark.asyncio
    async def test_position_empty_info_gets_synthetic_id(self, synchronizer, mock_repository):
        """Position with empty info should still be added with synthetic ID"""

        exchange_position = {
            'symbol': 'ADA/USDT:USDT',
            'contracts': 500,
            'side': 'long',
            'markPrice': 0.4,
            'info': {}  # Empty info
        }

        result = await synchronizer._add_missing_position('binance', exchange_position)

        # Position should be created with synthetic order ID
        assert result is True
        mock_repository.open_position.assert_called_once()
        call_args = mock_repository.open_position.call_args[0][0]
        assert call_args['exchange_order_id'].startswith('MANUAL_BINANCE_')


class TestSymbolNormalization:
    """Test symbol normalization helper"""

    def test_normalize_exchange_format(self):
        """Should normalize exchange format to database format"""
        assert normalize_symbol('HIGH/USDT:USDT') == 'HIGHUSDT'
        assert normalize_symbol('BTC/USDT:USDT') == 'BTCUSDT'
        assert normalize_symbol('ETH/USDT:USDT') == 'ETHUSDT'

    def test_normalize_already_normalized(self):
        """Should leave already normalized symbols unchanged"""
        assert normalize_symbol('BTCUSDT') == 'BTCUSDT'
        assert normalize_symbol('ETHUSDT') == 'ETHUSDT'


class TestIntegrationScenarios:
    """Integration-style tests for complete workflows"""

    @pytest.mark.asyncio
    async def test_sync_filters_all_stale_positions(self, synchronizer, mock_repository):
        """Full sync should filter all stale positions and add none"""

        mock_exchange = MagicMock()

        # All positions are stale (contracts>0 but positionAmt=0)
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.5,
                'info': {'positionAmt': '0'}
            },
            {
                'symbol': 'ETH/USDT:USDT',
                'contracts': 10,
                'info': {'positionAmt': '0'}
            }
        ])

        result = await synchronizer.synchronize_exchange('binance', mock_exchange)

        # No positions should be added (all filtered as stale)
        assert len(result['added_missing']) == 0
        mock_repository.open_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_adds_all_non_stale_positions(self, synchronizer, mock_repository):
        """Full sync should add all positions that pass stale filter (including those with synthetic IDs)"""

        mock_exchange = MagicMock()

        # Mix of real and no-order-id positions (both non-stale)
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            # Position with order_id
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.5,
                'info': {
                    'positionAmt': '0.5',
                    'positionId': '12345',
                    'avgPrice': '50000'
                },
                'markPrice': 50000
            },
            # Position without order_id (will get synthetic ID)
            {
                'symbol': 'ETH/USDT:USDT',
                'contracts': 10,
                'info': {
                    'positionAmt': '10',
                    'avgPrice': '3000'
                },
                'markPrice': 3000
            }
        ])

        result = await synchronizer.synchronize_exchange('binance', mock_exchange)

        # Both positions should be added (second one with synthetic ID)
        assert len(result['added_missing']) == 2
        assert 'BTCUSDT' in result['added_missing']
        assert 'ETHUSDT' in result['added_missing']
        assert mock_repository.open_position.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
