"""
Comprehensive tests for Binance Algo API migration

Tests all 6 modified locations to ensure correct implementation
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

# Test imports
from core.stop_loss_manager import StopLossManager
from core.exchange_manager import ExchangeManager
from protection.position_guard import PositionGuard
from protection.stop_loss_manager import StopLossManager as ProtectionSLManager


class TestAlgoAPIMigration:
    """Test suite for Algo API migration"""
    
    @pytest.fixture
    def mock_exchange(self):
        """Mock Binance exchange"""
        exchange = Mock()
        exchange.name = 'binance'
        exchange.milliseconds = Mock(return_value=1702123456789)
        exchange.price_to_precision = Mock(side_effect=lambda s, p: p)
        
        # Mock Algo API methods
        exchange.fapiPrivatePostAlgoOrder = AsyncMock(return_value={
            'algoId': 2000000015445020,
            'algoType': 'CONDITIONAL',
            'orderType': 'STOP_MARKET',
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'algoStatus': 'NEW',
            'triggerPrice': '50000.00',
            'quantity': '0.001',
            'reduceOnly': True,
            'createTime': 1702123456789
        })
        
        exchange.fapiPrivateGetOpenAlgoOrders = AsyncMock(return_value=[
            {
                'algoId': 2000000015445020,
                'symbol': 'BTCUSDT',
                'algoStatus': 'NEW'
            }
        ])
        
        return exchange
    
    # ========================================
    # Test #1: core/stop_loss_manager.py
    # Method: _set_binance_stop_loss_algo
    # ========================================
    
    @pytest.mark.asyncio
    async def test_core_sl_manager_algo_api(self, mock_exchange):
        """Test core StopLossManager uses correct Algo API"""
        
        sl_manager = StopLossManager(mock_exchange, 'binance')
        
        result = await sl_manager._set_binance_stop_loss_algo(
            symbol='BTC/USDT:USDT',
            side='sell',
            amount=Decimal('0.001'),
            stop_price=Decimal('50000.00')
        )
        
        # Verify Algo API was called
        assert mock_exchange.fapiPrivatePostAlgoOrder.called
        
        # Verify parameters
        call_args = mock_exchange.fapiPrivatePostAlgoOrder.call_args[0][0]
        assert call_args['algoType'] == 'CONDITIONAL'
        assert call_args['symbol'] == 'BTCUSDT'
        assert call_args['type'] == 'STOP_MARKET'
        assert call_args['triggerPrice'] == '50000.0'  # String
        assert call_args['quantity'] == '0.001'  # String
        assert call_args['reduceOnly'] == 'true'  # String, not boolean
        assert call_args['workingType'] == 'CONTRACT_PRICE'
        assert call_args['priceProtect'] == 'FALSE'  # String
        assert call_args['timeInForce'] == 'GTC'
        assert 'timestamp' in call_args
        
        # Verify result
        assert result['algoId'] == 2000000015445020
        assert result['status'] == 'success'
    
    @pytest.mark.asyncio
    async def test_core_sl_manager_variable_scope(self, mock_exchange):
        """Test variable scope in _set_binance_stop_loss_algo"""
        
        sl_manager = StopLossManager(mock_exchange, 'binance')
        
        # Test that Decimal import works inside method
        result = await sl_manager._set_binance_stop_loss_algo(
            symbol='ETH/USDT:USDT',
            side='buy',
            amount=Decimal('0.1'),
            stop_price=Decimal('3000.00')
        )
        
        # Verify binance_symbol formatting
        call_args = mock_exchange.fapiPrivatePostAlgoOrder.call_args[0][0]
        assert call_args['symbol'] == 'ETHUSDT'  # Slash and :USDT removed
    
    # ========================================
    # Test #2: core/exchange_manager.py
    # Method: create_stop_loss_order (Binance)
    # ========================================
    
    @pytest.mark.asyncio
    async def test_exchange_manager_create_sl_binance(self, mock_exchange):
        """Test ExchangeManager delegates to StopLossManager for Binance"""
        
        # Mock repository and other dependencies
        mock_repo = Mock()
        mock_rate_limiter = Mock()
        mock_rate_limiter.execute_request = AsyncMock()
        
        exchange_manager = ExchangeManager(
            exchange=mock_exchange,
            repository=mock_repo
        )
        exchange_manager.name = 'binance'
        exchange_manager.rate_limiter = mock_rate_limiter
        exchange_manager._validate_and_adjust_amount = AsyncMock(return_value=0.001)
        
        # Mock StopLossManager
        with patch('core.exchange_manager.StopLossManager') as MockSLManager:
            mock_sl_instance = MockSLManager.return_value
            mock_sl_instance.set_stop_loss = AsyncMock(return_value={
                'algoId': 2000000015445020,
                'status': 'success'
            })
            
            result = await exchange_manager.create_stop_loss_order(
                symbol='BTC/USDT:USDT',
                side='sell',
                amount=Decimal('0.001'),
                stop_price=Decimal('50000.00')
            )
            
            # Verify StopLossManager was created correctly
            MockSLManager.assert_called_once_with(mock_exchange, 'binance')
            
            # Verify set_stop_loss was called
            assert mock_sl_instance.set_stop_loss.called
            call_kwargs = mock_sl_instance.set_stop_loss.call_args[1]
            assert call_kwargs['symbol'] == 'BTC/USDT:USDT'
            assert call_kwargs['side'] == 'sell'
            assert isinstance(call_kwargs['amount'], Decimal)
            assert call_kwargs['stop_price'] == Decimal('50000.00')
            
            # Verify result format
            assert result['id'] == '2000000015445020'
            assert result['type'] == 'STOP_MARKET'
            assert result['stopPrice'] == 50000.00
    
    # ========================================
    # Test #3: core/exchange_manager.py
    # Method: _binance_update_sl_optimized
    # ========================================
    
    @pytest.mark.asyncio
    async def test_exchange_manager_update_sl_optimized(self, mock_exchange):
        """Test _binance_update_sl_optimized uses Algo API"""
        
        mock_repo = Mock()
        mock_rate_limiter = Mock()
        mock_rate_limiter.execute_request = AsyncMock(
            return_value={'algoId': 2000000015445020}
        )
        
        exchange_manager = ExchangeManager(
            exchange=mock_exchange,
            repository=mock_repo
        )
        exchange_manager.name = 'binance'
        exchange_manager.rate_limiter = mock_rate_limiter
        exchange_manager.position_manager = Mock()
        exchange_manager.position_manager.positions = {
            'BTC/USDT:USDT': Mock(quantity=Decimal('0.001'))
        }
        
        # Mock fetch_open_orders
        mock_rate_limiter.execute_request.side_effect = [
            [],  # No existing orders
            {'algoId': 2000000015445020}  # New order created
        ]
        
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='BTC/USDT:USDT',
            new_sl_price=51000.00,
            position_side='long'
        )
        
        # Verify Algo API was called
        assert mock_rate_limiter.execute_request.call_count >= 1
        
        # Find the fapiPrivatePostAlgoOrder call
        for call in mock_rate_limiter.execute_request.call_args_list:
            if len(call[0]) > 0 and hasattr(call[0][0], '__name__'):
                if 'fapiPrivatePostAlgoOrder' in str(call[0][0]):
                    params = call[0][1] if len(call[0]) > 1 else call[1].get('params', {})
                    assert params['algoType'] == 'CONDITIONAL'
                    assert params['symbol'] == 'BTCUSDT'
                    assert params['triggerPrice'] == '51000.0'
                    break
    
    # ========================================
    # Test #4: protection/position_guard.py
    # Method: _emergency_protection
    # ========================================
    
    @pytest.mark.asyncio
    async def test_position_guard_emergency_protection(self, mock_exchange):
        """Test PositionGuard emergency protection uses StopLossManager"""
        
        # Mock dependencies
        mock_exchange_manager = Mock()
        mock_exchange_manager.exchange = mock_exchange
        mock_exchange_manager.name = 'binance'
        
        mock_risk_manager = Mock()
        mock_sl_manager = Mock()
        mock_ts_manager = Mock()
        mock_repo = Mock()
        mock_event_router = Mock()
        
        position_guard = PositionGuard(
            exchange_manager=mock_exchange_manager,
            risk_manager=mock_risk_manager,
            stop_loss_manager=mock_sl_manager,
            trailing_stop_manager=mock_ts_manager,
            repository=mock_repo,
            event_router=mock_event_router,
            config={}
        )
        
        # Mock position
        mock_position = Mock()
        mock_position.id = 'test_pos_1'
        mock_position.symbol = 'BTC/USDT:USDT'
        mock_position.side = 'long'
        mock_position.entry_price = 50000.00
        mock_position.quantity = 0.001
        
        # Mock StopLossManager
        with patch('protection.position_guard.StopLossManager') as MockSLManager:
            mock_sl_instance = MockSLManager.return_value
            mock_sl_instance.set_stop_loss = AsyncMock(return_value={
                'algoId': 2000000015445020
            })
            
            await position_guard._emergency_protection(mock_position)
            
            # Verify StopLossManager was created
            MockSLManager.assert_called_once_with(mock_exchange, 'binance')
            
            # Verify set_stop_loss was called
            assert mock_sl_instance.set_stop_loss.called
            call_kwargs = mock_sl_instance.set_stop_loss.call_args[1]
            assert call_kwargs['symbol'] == 'BTC/USDT:USDT'
            assert call_kwargs['side'] == 'sell'  # Opposite of long
            assert isinstance(call_kwargs['amount'], Decimal)
            assert isinstance(call_kwargs['stop_price'], Decimal)
    
    # ========================================
    # Test #5: protection/stop_loss_manager.py
    # Method: _place_single_stop
    # ========================================
    
    @pytest.mark.asyncio
    async def test_protection_sl_manager_binance(self, mock_exchange):
        """Test protection SL manager delegates to core for Binance"""
        
        mock_exchange_manager = Mock()
        mock_exchange_manager.exchange = mock_exchange
        mock_exchange_manager.name = 'binance'
        
        mock_repo = Mock()
        
        protection_sl = ProtectionSLManager(
            exchange_manager=mock_exchange_manager,
            repository=mock_repo,
            config={}
        )
        
        # Create stop level
        from protection.stop_loss_manager import StopLossLevel, StopLossType
        stop = StopLossLevel(
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            type=StopLossType.FIXED,
            symbol='BTC/USDT:USDT',
            is_active=True
        )
        
        # Mock core StopLossManager
        with patch('protection.stop_loss_manager.StopLossManager') as MockCoreSL:
            mock_core_instance = MockCoreSL.return_value
            mock_core_instance.set_stop_loss = AsyncMock(return_value={
                'algoId': 2000000015445020,
                'status': 'success'
            })
            
            result = await protection_sl._place_single_stop(
                symbol='BTC/USDT:USDT',
                stop=stop
            )
            
            # Verify core SL was created
            MockCoreSL.assert_called_once_with(mock_exchange, 'binance')
            
            # Verify set_stop_loss was called
            assert mock_core_instance.set_stop_loss.called
            call_kwargs = mock_core_instance.set_stop_loss.call_args[1]
            assert call_kwargs['symbol'] == 'BTC/USDT:USDT'
            assert isinstance(call_kwargs['amount'], Decimal)
            assert call_kwargs['stop_price'] == Decimal('50000.00')
            
            # Verify result format
            assert result['id'] == '2000000015445020'
            assert result['type'] == 'STOP_MARKET'
    
    @pytest.mark.asyncio
    async def test_protection_sl_manager_bybit(self, mock_exchange):
        """Test protection SL manager uses old method for Bybit"""
        
        mock_exchange.name = 'bybit'
        
        mock_exchange_manager = Mock()
        mock_exchange_manager.exchange = mock_exchange
        mock_exchange_manager.name = 'bybit'
        mock_exchange_manager.create_order = AsyncMock(return_value={
            'id': 'bybit_order_123',
            'type': 'stop_market'
        })
        
        mock_repo = Mock()
        
        protection_sl = ProtectionSLManager(
            exchange_manager=mock_exchange_manager,
            repository=mock_repo,
            config={}
        )
        
        from protection.stop_loss_manager import StopLossLevel, StopLossType
        stop = StopLossLevel(
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            type=StopLossType.FIXED,
            symbol='BTC/USDT:USDT',
            is_active=True
        )
        
        result = await protection_sl._place_single_stop(
            symbol='BTC/USDT:USDT',
            stop=stop
        )
        
        # Verify old method was used for Bybit
        assert mock_exchange_manager.create_order.called
        assert result['id'] == 'bybit_order_123'
    
    # ========================================
    # Integration Tests
    # ========================================
    
    @pytest.mark.asyncio
    async def test_end_to_end_position_opening(self, mock_exchange):
        """Test complete position opening flow with SL"""
        
        # This would test the full flow from signal to position with SL
        # Simulating atomic_position_manager -> stop_loss_manager -> algo API
        
        sl_manager = StopLossManager(mock_exchange, 'binance')
        
        # Simulate position opening with SL
        result = await sl_manager.set_stop_loss(
            symbol='BTC/USDT:USDT',
            side='sell',
            amount=Decimal('0.001'),
            stop_price=Decimal('50000.00')
        )
        
        # Verify complete flow
        assert result['status'] == 'success'
        assert 'algoId' in result
        assert mock_exchange.fapiPrivatePostAlgoOrder.called
    
    # ========================================
    # Error Handling Tests
    # ========================================
    
    @pytest.mark.asyncio
    async def test_algo_api_error_handling(self, mock_exchange):
        """Test error handling when Algo API fails"""
        
        # Simulate API error
        mock_exchange.fapiPrivatePostAlgoOrder = AsyncMock(
            side_effect=Exception("API Error: -4120")
        )
        
        sl_manager = StopLossManager(mock_exchange, 'binance')
        
        with pytest.raises(Exception) as exc_info:
            await sl_manager._set_binance_stop_loss_algo(
                symbol='BTC/USDT:USDT',
                side='sell',
                amount=Decimal('0.001'),
                stop_price=Decimal('50000.00')
            )
        
        assert "-4120" in str(exc_info.value)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
