"""
Unit tests for Position Guard
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from protection.position_guard import (
    PositionGuard, RiskLevel, ProtectionAction, PositionHealth
)
from database.models import Position


class TestPositionGuard:
    """Test Position Guard functionality"""
    
    @pytest.fixture
    def position_guard(self, mock_exchange_manager, mock_risk_manager, mock_repository):
        """Create PositionGuard instance"""
        
        # Mock other dependencies
        mock_stop_loss_manager = Mock()
        mock_trailing_stop_manager = Mock()
        mock_event_router = Mock()
        
        config = {
            'max_drawdown_pct': 5.0,
            'critical_loss_pct': 3.0,
            'max_position_hours': 48,
            'volatility_threshold': 2.0,
            'correlation_threshold': 0.7
        }
        
        return PositionGuard(
            exchange_manager=mock_exchange_manager,
            risk_manager=mock_risk_manager,
            stop_loss_manager=mock_stop_loss_manager,
            trailing_stop_manager=mock_trailing_stop_manager,
            repository=mock_repository,
            event_router=mock_event_router,
            config=config
        )
    
    @pytest.mark.asyncio
    async def test_calculate_position_health(self, position_guard, sample_position):
        """Test position health calculation"""
        
        # Mock exchange data
        position_guard.exchange_manager.fetch_ticker = AsyncMock(
            return_value={'last': 51000}
        )
        position_guard.exchange_manager.fetch_ohlcv = AsyncMock(
            return_value=[[0, 50000, 50100, 49900, 50050, 100]] * 20
        )
        position_guard.exchange_manager.fetch_order_book = AsyncMock(
            return_value={
                'bids': [[50999, 1.0]],
                'asks': [[51001, 1.0]]
            }
        )
        
        # Set position peak
        position_guard.position_peaks[sample_position.id] = Decimal('50000')
        
        # Calculate health
        health = await position_guard._calculate_position_health(
            sample_position,
            current_price=Decimal('51000')
        )
        
        assert isinstance(health, PositionHealth)
        assert health.position_id == sample_position.id
        assert health.health_score >= 0 and health.health_score <= 100
        assert health.risk_level in RiskLevel
        assert health.unrealized_pnl == (Decimal('51000') - Decimal('50000')) * Decimal('0.1')
        assert health.pnl_percentage == Decimal('2.0')
    
    def test_score_pnl(self, position_guard):
        """Test PnL scoring"""
        
        # Positive PnL
        assert position_guard._score_pnl(Decimal('5')) == 100
        assert position_guard._score_pnl(Decimal('2')) == 80
        assert position_guard._score_pnl(Decimal('0')) == 60
        
        # Negative PnL
        assert position_guard._score_pnl(Decimal('-1')) == 50
        assert position_guard._score_pnl(Decimal('-3')) < 40
        assert position_guard._score_pnl(Decimal('-5')) <= 20
    
    def test_score_drawdown(self, position_guard):
        """Test drawdown scoring"""
        
        assert position_guard._score_drawdown(Decimal('0')) == 100
        assert position_guard._score_drawdown(Decimal('0.5')) == 100
        assert position_guard._score_drawdown(Decimal('1')) == 90
        assert position_guard._score_drawdown(Decimal('3')) == 50
        assert position_guard._score_drawdown(Decimal('5')) == 30
        assert position_guard._score_drawdown(Decimal('10')) < 30
    
    def test_determine_risk_level(self, position_guard):
        """Test risk level determination"""
        
        # Emergency level
        risk = position_guard._determine_risk_level(
            health_score=15,
            pnl_pct=Decimal('-4'),
            drawdown_pct=Decimal('6')
        )
        assert risk == RiskLevel.EMERGENCY
        
        # Critical level
        risk = position_guard._determine_risk_level(
            health_score=25,
            pnl_pct=Decimal('-2.5'),
            drawdown_pct=Decimal('4')
        )
        assert risk == RiskLevel.CRITICAL
        
        # High risk
        risk = position_guard._determine_risk_level(
            health_score=45,
            pnl_pct=Decimal('-1'),
            drawdown_pct=Decimal('2.5')
        )
        assert risk == RiskLevel.HIGH
        
        # Low risk
        risk = position_guard._determine_risk_level(
            health_score=85,
            pnl_pct=Decimal('2'),
            drawdown_pct=Decimal('0.5')
        )
        assert risk == RiskLevel.LOW
    
    def test_recommend_actions(self, position_guard):
        """Test protection action recommendations"""
        
        # Emergency actions
        actions = position_guard._recommend_actions(
            RiskLevel.EMERGENCY,
            {'volatility': 30},
            Decimal('-5')
        )
        assert ProtectionAction.EMERGENCY_EXIT in actions
        
        # Critical actions
        actions = position_guard._recommend_actions(
            RiskLevel.CRITICAL,
            {'volatility': 50},
            Decimal('-3')
        )
        assert ProtectionAction.FULL_CLOSE in actions
        
        # High risk actions
        actions = position_guard._recommend_actions(
            RiskLevel.HIGH,
            {'volatility': 60},
            Decimal('-1')
        )
        assert ProtectionAction.PARTIAL_CLOSE in actions
        assert ProtectionAction.ADJUST_STOP in actions
        
        # Low risk actions
        actions = position_guard._recommend_actions(
            RiskLevel.LOW,
            {'volatility': 80},
            Decimal('2')
        )
        assert ProtectionAction.MONITOR in actions
    
    @pytest.mark.asyncio
    async def test_start_protection(self, position_guard, sample_position):
        """Test starting position protection"""
        
        # Mock health calculation
        position_guard._calculate_position_health = AsyncMock(
            return_value=PositionHealth(
                position_id=sample_position.id,
                symbol=sample_position.symbol,
                health_score=75,
                risk_level=RiskLevel.LOW,
                unrealized_pnl=Decimal('100'),
                pnl_percentage=Decimal('2'),
                time_in_position=timedelta(hours=1),
                volatility_score=1.0,
                liquidity_score=80,
                drawdown=Decimal('0.5'),
                max_drawdown=Decimal('5')
            )
        )
        
        position_guard._setup_initial_protection = AsyncMock()
        
        await position_guard.start_protection(sample_position)
        
        assert sample_position.id in position_guard.monitored_positions
        assert sample_position.id in position_guard.position_health
        assert sample_position.id in position_guard.position_peaks
        
        position_guard._setup_initial_protection.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_emergency_exit_position(self, position_guard, sample_position):
        """Test emergency position exit"""
        
        position_guard.monitored_positions[sample_position.id] = sample_position
        position_guard.stop_loss_manager.cancel_position_stops = AsyncMock()
        position_guard.exchange_manager.close_position = AsyncMock(return_value=True)
        position_guard.repository.create_risk_event = AsyncMock()
        
        await position_guard._emergency_exit_position(sample_position)
        
        # Should cancel stops and close position
        position_guard.stop_loss_manager.cancel_position_stops.assert_called_once()
        position_guard.exchange_manager.close_position.assert_called_once_with(
            sample_position.symbol,
            sample_position.side,
            abs(sample_position.quantity)
        )
        
        # Should create risk event
        position_guard.repository.create_risk_event.assert_called_once()
        
        # Stats should be updated
        assert position_guard.protection_stats['emergency_exits'] == 1
    
    @pytest.mark.asyncio
    async def test_partial_close_position(self, position_guard, sample_position):
        """Test partial position closing"""
        
        position_guard.exchange_manager.close_position = AsyncMock(return_value=True)
        
        close_ratio = Decimal('0.5')
        await position_guard._partial_close_position(sample_position, close_ratio)
        
        # Should close 50% of position
        position_guard.exchange_manager.close_position.assert_called_once()
        
        # Check the arguments passed
        call_args = position_guard.exchange_manager.close_position.call_args[0]
        assert call_args[0] == sample_position.symbol
        assert call_args[1] == sample_position.side
        # Check close size is approximately correct (50% of 0.1 = 0.05)
        assert abs(float(call_args[2]) - 0.05) < 0.001
        
        # Position size should be updated
        assert sample_position.quantity == 0.05  # 50% of 0.1
    
    @pytest.mark.asyncio
    async def test_check_critical_conditions(self, position_guard, sample_position):
        """Test critical condition checking"""
        
        position_guard.exchange_manager.fetch_ticker = AsyncMock(
            return_value={'percentage': 15}  # 15% daily change
        )
        position_guard._emergency_exit_position = AsyncMock()
        position_guard._tighten_protection = AsyncMock()
        
        # Test with critical loss
        current_price = Decimal('48000')  # 4% loss
        await position_guard._check_critical_conditions(sample_position, current_price)
        
        # Should trigger emergency exit
        position_guard._emergency_exit_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tighten_protection(self, position_guard, sample_position):
        """Test protection tightening"""
        
        position_guard.position_peaks[sample_position.id] = Decimal('51000')
        position_guard.stop_loss_manager.update_stops = AsyncMock()
        position_guard.risk_manager.max_position_size = Decimal('1.0')
        position_guard._partial_close_position = AsyncMock()
        
        await position_guard._tighten_protection(sample_position)
        
        # Should update stops
        position_guard.stop_loss_manager.update_stops.assert_called_once()
        
        # Should not reduce position (size is small)
        position_guard._partial_close_position.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_position_update(self, position_guard, sample_position):
        """Test handling position update from WebSocket"""
        
        position_guard.monitored_positions[sample_position.id] = sample_position
        
        update_data = {
            'position_id': sample_position.id,
            'quantity': 0.2,
            'unrealized_pnl': 150
        }
        
        await position_guard._handle_position_update(update_data)
        
        # Position should be updated
        assert sample_position.quantity == 0.2
        assert sample_position.unrealized_pnl == 150
    
    @pytest.mark.asyncio
    async def test_handle_price_update(self, position_guard, sample_position):
        """Test handling price update"""
        
        position_guard.monitored_positions[sample_position.id] = sample_position
        position_guard.position_peaks[sample_position.id] = Decimal('50000')
        
        price_data = {
            'symbol': sample_position.symbol,
            'price': '52000'
        }
        
        await position_guard._handle_price_update(price_data)
        
        # Peak should be updated for long position
        assert position_guard.position_peaks[sample_position.id] == Decimal('52000')
    
    @pytest.mark.asyncio
    async def test_get_protection_status(self, position_guard, sample_position):
        """Test getting protection system status"""
        
        position_guard.monitored_positions[sample_position.id] = sample_position
        position_guard.position_health[sample_position.id] = PositionHealth(
            position_id=sample_position.id,
            symbol=sample_position.symbol,
            health_score=75,
            risk_level=RiskLevel.MEDIUM,
            unrealized_pnl=Decimal('100'),
            pnl_percentage=Decimal('2'),
            time_in_position=timedelta(hours=1),
            volatility_score=1.0,
            liquidity_score=80,
            drawdown=Decimal('0.5'),
            max_drawdown=Decimal('5')
        )
        position_guard.frozen_positions.add('frozen_123')
        
        status = await position_guard.get_protection_status()
        
        assert status['monitored_positions'] == 1
        assert status['emergency_mode'] == False
        assert 'frozen_123' in status['frozen_positions']
        assert sample_position.id in status['health_summary']
        assert status['health_summary'][sample_position.id]['health_score'] == 75
        assert status['health_summary'][sample_position.id]['risk_level'] == 'medium'