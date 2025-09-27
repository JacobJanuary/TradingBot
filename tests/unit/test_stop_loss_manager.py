"""
Unit tests for Stop Loss Manager
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from protection.stop_loss_manager import (
    StopLossManager, StopLossType, StopLossLevel
)
from database.models import Position, StopLossConfig


class TestStopLossManager:
    """Test Stop Loss Manager functionality"""
    
    @pytest.fixture
    def stop_loss_manager(self, mock_exchange_manager, mock_repository):
        """Create StopLossManager instance"""
        config = {
            'default_stop_percentage': 2.0,
            'trailing_activation': 1.0,
            'trailing_distance': 0.5,
            'breakeven_trigger': 1.5,
            'use_atr_trailing': True,
            'atr_multiplier': 2.0,
            'partial_levels': [
                {'profit_pct': 1.0, 'close_pct': 25},
                {'profit_pct': 2.0, 'close_pct': 25}
            ]
        }
        
        return StopLossManager(
            exchange_manager=mock_exchange_manager,
            repository=mock_repository,
            config=config
        )
    
    @pytest.mark.asyncio
    async def test_create_fixed_stop(self, stop_loss_manager):
        """Test fixed stop loss creation"""
        
        # Long position
        stop = await stop_loss_manager._create_fixed_stop(
            symbol='BTC/USDT',
            side='long',
            entry_price=Decimal('50000'),
            quantity=Decimal('0.1'),
            stop_percentage=Decimal('2.0')
        )
        
        assert stop.type == StopLossType.FIXED
        assert stop.price == Decimal('49000')  # 2% below entry
        assert stop.quantity == Decimal('0.1')
        assert stop.is_active == True
        
        # Short position
        stop = await stop_loss_manager._create_fixed_stop(
            symbol='BTC/USDT',
            side='short',
            entry_price=Decimal('50000'),
            quantity=Decimal('0.1'),
            stop_percentage=Decimal('2.0')
        )
        
        assert stop.price == Decimal('51000')  # 2% above entry
    
    @pytest.mark.asyncio
    async def test_create_partial_stops(self, stop_loss_manager):
        """Test partial take profit levels creation"""
        
        levels = [
            {'profit_pct': 1.0, 'close_pct': 25},
            {'profit_pct': 2.0, 'close_pct': 25},
            {'profit_pct': 3.0, 'close_pct': 50}
        ]
        
        stops = await stop_loss_manager._create_partial_stops(
            symbol='BTC/USDT',
            side='long',
            entry_price=Decimal('50000'),
            quantity=Decimal('1.0'),
            levels=levels
        )
        
        assert len(stops) == 3
        
        # Check first level
        assert stops[0].type == StopLossType.PARTIAL
        assert stops[0].trigger_price == Decimal('50500')  # 1% profit
        assert stops[0].quantity == Decimal('0.25')  # 25% of position
        
        # Check second level
        assert stops[1].trigger_price == Decimal('51000')  # 2% profit
        assert stops[1].quantity == Decimal('0.25')
        
        # Check third level
        assert stops[2].trigger_price == Decimal('51500')  # 3% profit
        assert stops[2].quantity == Decimal('0.5')  # 50% of position
    
    @pytest.mark.asyncio
    async def test_setup_position_stops(self, stop_loss_manager, sample_position):
        """Test setting up stops for a new position"""
        
        # Mock exchange manager methods
        stop_loss_manager.exchange_manager.create_order = AsyncMock(
            return_value={'id': 'stop_order_123'}
        )
        
        stops = await stop_loss_manager.setup_position_stops(sample_position)
        
        # Should have created stops
        assert len(stops) > 0
        assert sample_position.id in stop_loss_manager.active_stops
        
        # Check that orders were placed
        stop_loss_manager.exchange_manager.create_order.assert_called()
    
    @pytest.mark.asyncio
    async def test_move_to_breakeven(self, stop_loss_manager, sample_position):
        """Test moving stop loss to breakeven"""
        
        # Setup initial stop
        stop = StopLossLevel(
            price=Decimal('49000'),
            quantity=Decimal('0.1'),
            type=StopLossType.FIXED,
            order_id='stop_123',
            is_active=True
        )
        
        stop_loss_manager.exchange_manager.cancel_order = AsyncMock()
        stop_loss_manager.exchange_manager.create_order = AsyncMock(
            return_value={'id': 'new_stop_123'}
        )
        
        # Move to breakeven
        result = await stop_loss_manager._move_to_breakeven(sample_position, stop)
        
        assert result == True
        # Stop should be at entry price plus commission
        assert stop.price > sample_position.entry_price
        assert stop.type == StopLossType.BREAKEVEN
        
        # Check that old order was cancelled and new one created
        stop_loss_manager.exchange_manager.cancel_order.assert_called_once()
        stop_loss_manager.exchange_manager.create_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_trailing_stop(self, stop_loss_manager, sample_position):
        """Test trailing stop update"""
        
        # Setup trailing stop
        stop = StopLossLevel(
            price=Decimal('49500'),
            quantity=Decimal('0.1'),
            type=StopLossType.TRAILING,
            trail_distance=Decimal('1.0'),
            order_id='trail_123',
            is_active=True
        )
        
        stop_loss_manager.exchange_manager.cancel_order = AsyncMock()
        stop_loss_manager.exchange_manager.create_order = AsyncMock(
            return_value={'id': 'new_trail_123'}
        )
        
        # Update with higher price (should move stop up)
        current_price = Decimal('51000')
        high_water = Decimal('51000')
        
        result = await stop_loss_manager._update_trailing_stop(
            sample_position, stop, current_price, high_water
        )
        
        assert result == True
        # Stop should have moved up
        assert stop.price > Decimal('49500')
        # Should be 1% below high water mark
        expected_stop = high_water * Decimal('0.99')
        assert abs(stop.price - expected_stop) < Decimal('1')
    
    @pytest.mark.asyncio
    async def test_calculate_atr_trail(self, stop_loss_manager):
        """Test ATR-based trailing distance calculation"""
        
        # Mock exchange data
        stop_loss_manager.exchange_manager.fetch_ohlcv = AsyncMock(
            return_value=[
                [0, 100, 105, 95, 102, 1000],
                [0, 102, 108, 100, 105, 1100],
                [0, 105, 110, 103, 108, 1200],
                # Add more candles for ATR calculation
            ] * 5
        )
        
        atr = await stop_loss_manager._calculate_atr_trail('BTC/USDT')
        
        # ATR should be calculated and cached
        assert atr > 0
        assert 'BTC/USDT' in stop_loss_manager.atr_cache
    
    @pytest.mark.asyncio
    async def test_emergency_stop_creation(self, stop_loss_manager, sample_position):
        """Test emergency stop creation when normal setup fails"""
        
        stop_loss_manager.exchange_manager.create_order = AsyncMock(
            return_value={'id': 'emergency_123'}
        )
        
        stops = await stop_loss_manager._create_emergency_stop(sample_position)
        
        assert len(stops) == 1
        assert stops[0].type == StopLossType.FIXED
        # Emergency stop should be wider
        assert stops[0].price <= Decimal(str(sample_position.entry_price)) * Decimal('0.96')
        assert stops[0].is_active == True
    
    @pytest.mark.asyncio
    async def test_cancel_position_stops(self, stop_loss_manager, sample_position):
        """Test cancelling all stops for a position"""
        
        # Add some active stops
        stop_loss_manager.active_stops[sample_position.id] = [
            StopLossLevel(
                price=Decimal('49000'),
                quantity=Decimal('0.1'),
                type=StopLossType.FIXED,
                order_id='stop_1',
                is_active=True
            ),
            StopLossLevel(
                price=Decimal('51000'),
                quantity=Decimal('0.05'),
                type=StopLossType.PARTIAL,
                order_id='stop_2',
                is_active=True
            )
        ]
        
        stop_loss_manager.exchange_manager.cancel_order = AsyncMock()
        
        cancelled = await stop_loss_manager.cancel_position_stops(sample_position.id)
        
        assert cancelled == 2
        assert sample_position.id not in stop_loss_manager.active_stops
        assert stop_loss_manager.exchange_manager.cancel_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_update_stops_with_profit(self, stop_loss_manager, sample_position):
        """Test updating stops when position is in profit"""
        
        # Setup position with stops
        stop = StopLossLevel(
            price=Decimal('49000'),
            quantity=Decimal('0.1'),
            type=StopLossType.FIXED,
            order_id='stop_123',
            is_active=True
        )
        
        stop_loss_manager.active_stops[sample_position.id] = [stop]
        stop_loss_manager.highest_prices[sample_position.id] = Decimal('51000')
        
        stop_loss_manager.exchange_manager.cancel_order = AsyncMock()
        stop_loss_manager.exchange_manager.create_order = AsyncMock(
            return_value={'id': 'new_stop'}
        )
        
        # Update with profitable position
        current_price = Decimal('51000')
        updates = await stop_loss_manager.update_stops(sample_position, current_price)
        
        assert updates['updated'] > 0
        # Should have moved to breakeven or tightened
        assert updates['moved_to_breakeven'] or updates['trailing_adjusted']
    
    # Note: _position_changed method doesn't exist in StopLossManager
    # This test was incorrectly placed and has been removed