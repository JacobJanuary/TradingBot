"""
Unit tests for Risk Manager
"""

import pytest
from unittest.mock import Mock, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone

from core.risk_manager import RiskManager, RiskViolation, RiskLevel
from database.models import Position, Order


class TestRiskManager:
    """Test Risk Manager functionality"""
    
    @pytest.fixture
    def risk_manager(self, mock_repository):
        """Create RiskManager instance"""
        config = {
            'max_position_size': 10000,
            'max_daily_loss': 1000,
            'max_open_positions': 5,
            'max_leverage': 10,
            'max_correlation': 0.7,
            'default_stop_loss': 2.0,
            'risk_per_trade': 1.0
        }
        
        return RiskManager(
            repository=mock_repository,
            config=config
        )
    
    @pytest.mark.asyncio
    async def test_check_position_limit(self, risk_manager, mock_repository):
        """Test position limit checking"""
        
        # No positions - should pass
        mock_repository.get_active_positions.return_value = []
        result = await risk_manager.check_position_limit('binance')
        assert result == True
        
        # At limit - should fail
        positions = [Mock() for _ in range(5)]
        mock_repository.get_active_positions.return_value = positions
        result = await risk_manager.check_position_limit('binance')
        assert result == False
        
        # Below limit - should pass
        positions = [Mock() for _ in range(3)]
        mock_repository.get_active_positions.return_value = positions
        result = await risk_manager.check_position_limit('binance')
        assert result == True
    
    @pytest.mark.asyncio
    async def test_check_daily_loss_limit(self, risk_manager, mock_repository):
        """Test daily loss limit checking"""
        
        # Mock daily PnL
        mock_repository.get_daily_pnl.return_value = Decimal('-500')
        
        # Within limit - should pass
        result = await risk_manager.check_daily_loss_limit()
        assert result == True
        
        # At limit - should fail
        mock_repository.get_daily_pnl.return_value = Decimal('-1000')
        result = await risk_manager.check_daily_loss_limit()
        assert result == False
        
        # Over limit - should fail
        mock_repository.get_daily_pnl.return_value = Decimal('-1500')
        result = await risk_manager.check_daily_loss_limit()
        assert result == False
    
    @pytest.mark.asyncio
    async def test_calculate_position_size(self, risk_manager):
        """Test position size calculation"""
        
        # Basic calculation
        size = await risk_manager.calculate_position_size(
            symbol='BTC/USDT',
            price=Decimal('50000'),
            stop_loss=Decimal('49000'),
            account_balance=Decimal('10000')
        )
        
        # Size should be based on risk per trade (1%)
        # Risk = 100 USDT, Stop distance = 1000 USDT
        # Position size = 100 / 1000 = 0.1 BTC
        assert size == Decimal('0.1')
        
        # With leverage
        size = await risk_manager.calculate_position_size(
            symbol='BTC/USDT',
            price=Decimal('50000'),
            stop_loss=Decimal('49000'),
            account_balance=Decimal('10000'),
            leverage=5
        )
        
        # With 5x leverage, can take larger position
        assert size > Decimal('0.1')
    
    @pytest.mark.asyncio
    async def test_validate_order(self, risk_manager, sample_order):
        """Test order validation"""
        
        # Valid order
        result = await risk_manager.validate_order(sample_order)
        assert result == True
        
        # Order too large
        sample_order.size = Decimal('1000')  # Very large
        sample_order.price = Decimal('50000')
        result = await risk_manager.validate_order(sample_order)
        assert result == False
    
    @pytest.mark.asyncio
    async def test_check_leverage(self, risk_manager):
        """Test leverage checking"""
        
        # Within limit
        result = await risk_manager.check_leverage(5)
        assert result == True
        
        # At limit
        result = await risk_manager.check_leverage(10)
        assert result == True
        
        # Over limit
        result = await risk_manager.check_leverage(20)
        assert result == False
    
    @pytest.mark.asyncio
    async def test_calculate_portfolio_risk(self, risk_manager, mock_repository):
        """Test portfolio risk calculation"""
        
        positions = [
            Position(
                id='pos1',
                symbol='BTC/USDT',
                side='long',
                quantity=Decimal('0.1'),
                entry_price=Decimal('50000'),
                unrealized_pnl=Decimal('100')
            ),
            Position(
                id='pos2',
                symbol='ETH/USDT',
                side='long',
                quantity=Decimal('1'),
                entry_price=Decimal('3000'),
                unrealized_pnl=Decimal('-50')
            )
        ]
        
        mock_repository.get_active_positions.return_value = positions
        
        risk_metrics = await risk_manager.calculate_portfolio_risk()
        
        assert 'total_exposure' in risk_metrics
        assert 'position_count' in risk_metrics
        assert 'unrealized_pnl' in risk_metrics
        assert 'risk_score' in risk_metrics
        
        # Check calculations
        assert risk_metrics['total_exposure'] == Decimal('8000')  # 0.1*50000 + 1*3000
        assert risk_metrics['position_count'] == 2
        assert risk_metrics['unrealized_pnl'] == Decimal('50')  # 100 - 50
    
    @pytest.mark.asyncio
    async def test_emergency_liquidation(self, risk_manager, mock_repository, sample_position):
        """Test emergency liquidation trigger"""
        
        mock_repository.get_active_positions.return_value = [sample_position]
        
        # Mock repository for liquidation
        mock_repository.update_position = AsyncMock(return_value=True)
        
        # Trigger emergency liquidation
        result = await risk_manager.emergency_liquidation('Critical loss detected')
        
        # Should update all positions
        mock_repository.update_position.assert_called()
        assert result['positions_closed'] == 1
    
    def test_risk_level_classification(self, risk_manager):
        """Test risk level classification"""
        
        # Low risk
        level = risk_manager.classify_risk_level(risk_score=20)
        assert level == RiskLevel.LOW
        
        # Medium risk
        level = risk_manager.classify_risk_level(risk_score=50)
        assert level == RiskLevel.MEDIUM
        
        # High risk
        level = risk_manager.classify_risk_level(risk_score=75)
        assert level == RiskLevel.HIGH
        
        # Critical risk
        level = risk_manager.classify_risk_level(risk_score=90)
        assert level == RiskLevel.CRITICAL
    
    @pytest.mark.asyncio
    async def test_check_correlation_risk(self, risk_manager):
        """Test correlation risk checking"""
        
        positions = [
            {'symbol': 'BTC/USDT', 'side': 'long'},
            {'symbol': 'ETH/USDT', 'side': 'long'},
            {'symbol': 'BNB/USDT', 'side': 'long'}
        ]
        
        # High correlation (all crypto longs)
        correlation = await risk_manager.check_correlation_risk(positions)
        assert correlation > 0.5  # Should detect high correlation
        
        # Mixed positions
        positions = [
            {'symbol': 'BTC/USDT', 'side': 'long'},
            {'symbol': 'ETH/USDT', 'side': 'short'}
        ]
        
        correlation = await risk_manager.check_correlation_risk(positions)
        assert correlation < 0.5  # Lower correlation
    
    @pytest.mark.asyncio
    async def test_validate_stop_loss(self, risk_manager):
        """Test stop loss validation"""
        
        # Valid stop loss for long
        result = await risk_manager.validate_stop_loss(
            side='long',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('49000')
        )
        assert result == True
        
        # Invalid stop loss for long (above entry)
        result = await risk_manager.validate_stop_loss(
            side='long',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('51000')
        )
        assert result == False
        
        # Valid stop loss for short
        result = await risk_manager.validate_stop_loss(
            side='short',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('51000')
        )
        assert result == True
        
        # Invalid stop loss for short (below entry)
        result = await risk_manager.validate_stop_loss(
            side='short',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('49000')
        )
        assert result == False
    
    @pytest.mark.asyncio
    async def test_record_risk_violation(self, risk_manager, mock_repository):
        """Test recording risk violations"""
        
        mock_repository.create_risk_violation = AsyncMock()
        
        violation = RiskViolation(
            type='position_limit',
            level=RiskLevel.HIGH,
            message='Position limit exceeded',
            timestamp=datetime.now(timezone.utc)
        )
        
        await risk_manager.record_risk_violation(violation)
        
        # Should record in database
        mock_repository.create_risk_violation.assert_called_once()
        
        # Should track in memory
        assert len(risk_manager.violations) == 1
        assert risk_manager.violations[0].type == 'position_limit'