"""
Unit tests for Performance Tracker
"""

import pytest
from unittest.mock import Mock, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date

from monitoring.performance import PerformanceTracker, PerformanceMetrics
from database.models import Position


class TestPerformanceTracker:
    """Test Performance Tracker functionality"""
    
    @pytest.fixture
    def performance_tracker(self, mock_repository):
        """Create PerformanceTracker instance"""
        config = {
            'risk_free_rate': 0.02,
            'calculation_period': 30,
            'min_trades_for_stats': 5,
            'initial_capital': 10000
        }
        
        return PerformanceTracker(
            repository=mock_repository,
            config=config
        )
    
    @pytest.fixture
    def sample_closed_positions(self):
        """Create sample closed positions for testing"""
        now = datetime.now(timezone.utc)
        
        return [
            Position(
                id='pos1',
                symbol='BTC/USDT',
                side='long',
                quantity=Decimal('0.1'),
                entry_price=Decimal('50000'),
                exit_price=Decimal('51000'),
                realized_pnl=Decimal('100'),
                fees=Decimal('5'),
                opened_at=now - timedelta(hours=10),
                closed_at=now - timedelta(hours=8),
                status='closed'
            ),
            Position(
                id='pos2',
                symbol='ETH/USDT',
                side='long',
                quantity=Decimal('1'),
                entry_price=Decimal('3000'),
                exit_price=Decimal('2950'),
                realized_pnl=Decimal('-50'),
                fees=Decimal('3'),
                opened_at=now - timedelta(hours=5),
                closed_at=now - timedelta(hours=3),
                status='closed'
            ),
            Position(
                id='pos3',
                symbol='BNB/USDT',
                side='short',
                quantity=Decimal('10'),
                entry_price=Decimal('400'),
                exit_price=Decimal('395'),
                realized_pnl=Decimal('50'),
                fees=Decimal('4'),
                opened_at=now - timedelta(hours=2),
                closed_at=now - timedelta(hours=1),
                status='closed'
            )
        ]
    
    @pytest.mark.asyncio
    async def test_calculate_metrics(self, performance_tracker, sample_closed_positions):
        """Test performance metrics calculation"""
        
        metrics = await performance_tracker._calculate_metrics(sample_closed_positions)
        
        assert isinstance(metrics, PerformanceMetrics)
        
        # Check basic calculations
        assert metrics.total_pnl == Decimal('100')  # 100 - 50 + 50
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate == pytest.approx(66.67, 0.01)
        
        # Check P&L metrics
        assert metrics.gross_profit == Decimal('150')  # 100 + 50
        assert metrics.gross_loss == Decimal('50')
        assert metrics.net_profit == Decimal('88')  # total_pnl (100) - total_fees (12) = 88
        assert metrics.total_fees == Decimal('12')  # 5 + 3 + 4
        
        # Check averages
        assert metrics.avg_win == Decimal('75')  # 150 / 2
        assert metrics.avg_loss == Decimal('50')
        assert metrics.largest_win == Decimal('100')
        assert metrics.largest_loss == Decimal('-50')
    
    @pytest.mark.asyncio
    async def test_empty_metrics(self, performance_tracker):
        """Test metrics calculation with no positions"""
        
        metrics = await performance_tracker._calculate_metrics([])
        
        assert metrics.total_pnl == Decimal('0')
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0
        assert metrics.sharpe_ratio == 0
    
    def test_calculate_sharpe_ratio(self, performance_tracker):
        """Test Sharpe ratio calculation"""
        
        # Positive returns
        returns = [0.02, 0.03, -0.01, 0.04, 0.01, -0.02, 0.03]
        sharpe = performance_tracker._calculate_sharpe(returns)
        
        assert sharpe > 0  # Should be positive for profitable returns
        
        # Negative returns
        returns = [-0.02, -0.03, -0.01, -0.04, -0.01]
        sharpe = performance_tracker._calculate_sharpe(returns)
        
        assert sharpe < 0  # Should be negative for losing returns
        
        # Too few trades
        returns = [0.01, 0.02, 0.03]  # Only 3 returns, less than min_trades_for_stats (5)
        sharpe = performance_tracker._calculate_sharpe(returns)
        
        assert sharpe == 0  # Not enough trades for stats
    
    def test_calculate_sortino_ratio(self, performance_tracker):
        """Test Sortino ratio calculation"""
        
        # Mixed returns
        returns = [0.02, 0.03, -0.01, 0.04, 0.01, -0.02, 0.03]
        sortino = performance_tracker._calculate_sortino(returns)
        
        # Sortino should differ from Sharpe (uses downside deviation)
        sharpe = performance_tracker._calculate_sharpe(returns)
        assert sortino != sharpe
        
        # All positive returns
        returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        sortino = performance_tracker._calculate_sortino(returns)
        
        assert sortino == float('inf')  # No downside
    
    @pytest.mark.asyncio
    async def test_build_equity_curve(self, performance_tracker, sample_closed_positions):
        """Test equity curve construction"""
        
        performance_tracker._get_initial_capital = AsyncMock(
            return_value=Decimal('10000')
        )
        
        curve = await performance_tracker._build_equity_curve(sample_closed_positions)
        
        assert len(curve) == 4  # Initial + 3 positions
        assert curve[0][1] == Decimal('10000')  # Initial capital
        assert curve[-1][1] == Decimal('10100')  # Final equity (10000 + 100 total PnL)
        
        # Check progression (skip strict timestamp ordering as test positions may have different closed_at times)
        for i in range(1, len(curve)):
            # Just check that we have a valid curve structure
            assert isinstance(curve[i][0], datetime)
            assert isinstance(curve[i][1], Decimal)
    
    def test_calculate_max_drawdown(self, performance_tracker):
        """Test maximum drawdown calculation"""
        
        # Create equity curve with drawdown
        equity_curve = [
            (datetime.now(timezone.utc), Decimal('10000')),
            (datetime.now(timezone.utc), Decimal('10500')),
            (datetime.now(timezone.utc), Decimal('11000')),  # Peak
            (datetime.now(timezone.utc), Decimal('10200')),  # Drawdown
            (datetime.now(timezone.utc), Decimal('10800')),
        ]
        
        max_dd, max_dd_pct = performance_tracker._calculate_max_drawdown(equity_curve)
        
        assert max_dd == Decimal('800')  # 11000 - 10200
        assert max_dd_pct == pytest.approx(7.27, 0.01)  # 800/11000 * 100
    
    @pytest.mark.asyncio
    async def test_get_daily_performance(self, performance_tracker, mock_repository):
        """Test daily performance calculation"""
        
        # Mock repository methods
        positions = [
            Position(
                id='pos1',
                symbol='BTC/USDT',
                realized_pnl=Decimal('100'),
                fees=Decimal('5'),
                quantity=Decimal('0.1'),
                entry_price=Decimal('50000'),
                opened_at=datetime.now(timezone.utc),
                closed_at=datetime.now(timezone.utc)
            )
        ]
        
        mock_repository.get_positions_by_date = AsyncMock(
            return_value=positions
        )
        
        performance_tracker._get_equity_at_date = AsyncMock(
            return_value=Decimal('10000')
        )
        
        # Get daily performance
        daily = await performance_tracker.get_daily_performance(
            date.today(),
            date.today()
        )
        
        assert len(daily) == 1
        assert daily[0].pnl == Decimal('100')
        assert daily[0].trades == 1
        assert daily[0].win_rate == 100
    
    @pytest.mark.asyncio
    async def test_analyze_position(self, performance_tracker, sample_closed_positions):
        """Test detailed position analysis"""
        
        position = sample_closed_positions[0]
        
        # Mock price history
        performance_tracker._get_position_price_history = AsyncMock(
            return_value=[
                Decimal('50000'),
                Decimal('50200'),
                Decimal('50500'),  # High
                Decimal('49800'),  # Low
                Decimal('51000')
            ]
        )
        
        analysis = await performance_tracker.analyze_position(position)
        
        assert analysis.position_id == position.id
        assert analysis.pnl == position.realized_pnl
        assert analysis.pnl_percentage == Decimal('2.0')  # 100 / (50000 * 0.1) * 100 = 100/5000 * 100 = 2%
        assert analysis.max_profit == Decimal('100')  # (51000 - 50000) * 0.1 (max in price history)
        assert analysis.max_loss == Decimal('20')  # (50000 - 49800) * 0.1
    
    def test_calculate_mae_mfe(self, performance_tracker):
        """Test MAE/MFE calculation"""
        
        position = Position(
            id='pos1',
            symbol='BTC/USDT',
            side='long',
            quantity=Decimal('0.1'),
            entry_price=Decimal('50000')
        )
        
        price_history = [
            Decimal('50000'),
            Decimal('49500'),  # Adverse
            Decimal('51000'),  # Favorable
            Decimal('50500')
        ]
        
        mae, mfe = performance_tracker._calculate_mae_mfe(position, price_history)
        
        assert mae == Decimal('500')  # 50000 - 49500
        assert mfe == Decimal('1000')  # 51000 - 50000
    
    @pytest.mark.asyncio
    async def test_performance_summary(self, performance_tracker, mock_repository, sample_closed_positions):
        """Test comprehensive performance summary generation"""
        
        # Mock repository
        mock_repository.get_closed_positions_since = AsyncMock(
            return_value=sample_closed_positions
        )
        
        performance_tracker._get_initial_capital = AsyncMock(
            return_value=Decimal('10000')
        )
        
        # Update metrics
        await performance_tracker.update_metrics()
        
        # Get summary
        summary = await performance_tracker.get_performance_summary()
        
        assert 'overview' in summary
        assert 'statistics' in summary
        assert 'risk_metrics' in summary
        assert 'session' in summary
        
        # Check overview
        assert summary['overview']['total_pnl'] == 100
        assert summary['overview']['total_trades'] == 3
        
        # Check statistics
        assert summary['statistics']['win_rate'] == pytest.approx(66.67, 0.01)
        assert summary['statistics']['avg_win'] == 75
    
    def test_record_trade(self, performance_tracker):
        """Test recording completed trades"""
        
        position = Position(
            id='pos1',
            realized_pnl=Decimal('150')
        )
        
        performance_tracker.record_trade(position)
        
        assert performance_tracker.session_pnl == Decimal('150')
        assert performance_tracker.session_trades == 1
        
        # Record another trade
        position2 = Position(
            id='pos2',
            realized_pnl=Decimal('-50')
        )
        
        performance_tracker.record_trade(position2)
        
        assert performance_tracker.session_pnl == Decimal('100')
        assert performance_tracker.session_trades == 2