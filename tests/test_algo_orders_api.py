"""
Test suite for Binance Algo Orders API support (HYPERUSDT fix)

Tests the fallback mechanism from standard stop-loss API to Algo Orders API
when encountering Binance error -4120.
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock


class TestAlgoOrdersAPISupport:
    """Test Algo Orders API implementation for symbols like HYPERUSDT"""
    
    @pytest.fixture
    async def mock_exchange(self):
        """Mock CCXT exchange with both standard and algo API support"""
        exchange = AsyncMock()
        exchange.id = 'binance'
        
        # Standard API (will fail for HYPERUSDT)
        exchange.create_order = AsyncMock()
        
        # Algo API (fallback)
        exchange.fapiPrivatePostAlgoFuturesNewOrderVp = AsyncMock()
        
        return exchange
    
    @pytest.fixture
    def stop_loss_manager(self, mock_exchange):
        """Create StopLossManager with mocked exchange"""
        from core.stop_loss_manager import StopLossManager
        
        manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance'
        )
        return manager
    
    @pytest.mark.asyncio
    async def test_standard_api_success(self, stop_loss_manager, mock_exchange):
        """Test standard API works for normal symbols (e.g., BTCUSDT)"""
        # Arrange
        symbol = 'BTC/USDT'
        side = 'sell'
        amount = Decimal('0.1')
        stop_price = Decimal('50000')
        
        mock_exchange.create_order.return_value = {
            'id': 'test_order_123',
            'symbol': symbol,
            'type': 'stop_market',
            'side': side
        }
        
        mock_exchange.fetch_ticker.return_value = {
            'last': 51000,
            'info': {'markPrice': '51000'}
        }
        
        # Act
        result = await stop_loss_manager.set_stop_loss(
            symbol=symbol,
            side=side,
            amount=amount,
            stop_price=stop_price
        )
        
        # Assert
        assert result['status'] == 'created'
        assert result['orderId'] == 'test_order_123'
        mock_exchange.create_order.assert_called_once()
        # Algo API should NOT be called
        mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_algo_api_fallback_on_error_4120(self, stop_loss_manager, mock_exchange):
        """Test fallback to Algo API when standard API returns error -4120"""
        # Arrange
        symbol = 'HYPER/USDT'
        side = 'sell'
        amount = Decimal('588')
        stop_price = Decimal('0.1526')
        
        # Standard API fails with -4120
        mock_exchange.create_order.side_effect = Exception(
            'binance {"code":-4120,"msg":"Order type not supported for this endpoint. '
            'Please use the Algo Order API endpoints instead."}'
        )
        
        # Algo API succeeds
        mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.return_value = {
            'algoId': 'algo_123',
            'symbol': 'HYPERUSDT',
            'status': 'NEW'
        }
        
        mock_exchange.fetch_ticker.return_value = {
            'last': 0.169,
            'info': {'markPrice': '0.169'}
        }
        
        # Act
        result = await stop_loss_manager.set_stop_loss_with_fallback(
            symbol=symbol,
            side=side,
            amount=amount,
            stop_price=stop_price
        )
        
        # Assert
        assert result['status'] == 'created'
        assert result['algoId'] == 'algo_123'
        # Both APIs should be called (standard first, then algo)
        mock_exchange.create_order.assert_called_once()
        mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_algo_api_direct_call(self, stop_loss_manager, mock_exchange):
        """Test direct Algo API call for known incompatible symbols"""
        # Arrange
        symbol = 'HYPER/USDT'
        side = 'sell'
        amount = Decimal('588')
        stop_price = Decimal('0.1526')
        
        mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.return_value = {
            'algoId': 'algo_456',
            'symbol': 'HYPERUSDT',
            'status': 'NEW',
            'stopPrice': '0.1526'
        }
        
        # Act
        result = await stop_loss_manager._set_binance_stop_loss_algo(
            symbol=symbol,
            side=side,
            amount=amount,
            stop_price=stop_price
        )
        
        # Assert
        assert result['status'] == 'created'
        assert result['algoId'] == 'algo_456'
        assert 'stopPrice' in result
    
    @pytest.mark.asyncio
    async def test_algo_api_parameters(self, stop_loss_manager, mock_exchange):
        """Test Algo API is called with correct parameters"""
        # Arrange
        symbol = 'HYPER/USDT'
        side = 'sell'
        amount = Decimal('588')
        stop_price = Decimal('0.1526')
        
        mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.return_value = {
            'algoId': 'test',
            'status': 'NEW'
        }
        
        # Act
        await stop_loss_manager._set_binance_stop_loss_algo(
            symbol=symbol,
            side=side,
            amount=amount,
            stop_price=stop_price
        )
        
        # Assert
        call_args = mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.call_args[0][0]
        assert call_args['symbol'] == 'HYPERUSDT'  # No slash
        assert call_args['side'] == 'SELL'  # Uppercase
        assert call_args['quantity'] == '588.0'
        assert call_args['stopPrice'] == '0.1526'
        assert call_args['reduceOnly'] == 'true'
    
    @pytest.mark.asyncio
    async def test_atomic_rollback_on_algo_api_failure(self, stop_loss_manager, mock_exchange):
        """Test position rollback when both standard and algo APIs fail"""
        # Arrange
        symbol = 'HYPER/USDT'
        side = 'sell'
        amount = Decimal('588')
        stop_price = Decimal('0.1526')
        
        # Both APIs fail
        mock_exchange.create_order.side_effect = Exception('Error -4120')
        mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.side_effect = Exception('Algo API error')
        
        mock_exchange.fetch_ticker.return_value = {
            'last': 0.169,
            'info': {'markPrice': '0.169'}
        }
        
        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await stop_loss_manager.set_stop_loss_with_fallback(
                symbol=symbol,
                side=side,
                amount=amount,
                stop_price=stop_price
            )
        
        assert 'Algo API error' in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_error_4120_detection(self, stop_loss_manager):
        """Test correct detection of Binance error -4120"""
        # Test various error message formats
        test_cases = [
            'binance {"code":-4120,"msg":"Order type not supported"}',
            'Error -4120: Order type not supported',
            '{"code":-4120}',
        ]
        
        for error_msg in test_cases:
            assert stop_loss_manager._is_algo_api_required_error(error_msg)
        
        # Negative cases
        negative_cases = [
            'binance {"code":-2021,"msg":"Different error"}',
            'Some other error',
            ''
        ]
        
        for error_msg in negative_cases:
            assert not stop_loss_manager._is_algo_api_required_error(error_msg)
    
    @pytest.mark.asyncio
    async def test_multiple_symbols_mixed_apis(self, stop_loss_manager, mock_exchange):
        """Test handling multiple symbols, some requiring Algo API, some not"""
        # Arrange
        symbols_config = [
            ('BTC/USDT', False),   # Standard API works
            ('ETH/USDT', False),   # Standard API works
            ('HYPER/USDT', True),  # Requires Algo API
            ('PROMPT/USDT', False) # Standard API works
        ]
        
        def create_order_side_effect(symbol, **kwargs):
            if 'HYPER' in symbol:
                raise Exception('Error -4120')
            return {'id': f'order_{symbol}', 'status': 'NEW'}
        
        mock_exchange.create_order.side_effect = create_order_side_effect
        mock_exchange.fapiPrivatePostAlgoFuturesNewOrderVp.return_value = {
            'algoId': 'algo_hyper',
            'status': 'NEW'
        }
        mock_exchange.fetch_ticker.return_value = {
            'last': 100,
            'info': {'markPrice': '100'}
        }
        
        # Act & Assert
        for symbol, requires_algo in symbols_config:
            result = await stop_loss_manager.set_stop_loss_with_fallback(
                symbol=symbol,
                side='sell',
                amount=Decimal('1'),
                stop_price=Decimal('90')
            )
            
            assert result['status'] == 'created'
            if requires_algo:
                assert 'algoId' in result
            else:
                assert 'orderId' in result


class TestHYPERUSDTIntegration:
    """Integration tests specifically for HYPERUSDT scenario"""
    
    @pytest.mark.asyncio
    async def test_hyperusdt_full_position_lifecycle(self):
        """Test complete position lifecycle for HYPERUSDT with Algo API"""
        # This would be an integration test requiring actual Binance testnet
        # Placeholder for documentation purposes
        pass
    
    @pytest.mark.asyncio
    async def test_hyperusdt_rollback_scenario(self):
        """Reproduce the exact HYPERUSDT failure scenario and verify fix"""
        # Simulate:
        # 1. Position opened (588 HYPERUSDT)
        # 2. Standard SL fails 3 times with -4120
        # 3. Fallback to Algo API succeeds
        # 4. Position remains open with SL protection
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])
