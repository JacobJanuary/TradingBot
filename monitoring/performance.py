"""
Performance tracking and analytics for trading bot
"""

import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from loguru import logger

from database.repository import Repository
from database.models import Position, Trade


@dataclass
class PerformanceMetrics:
    """Trading performance metrics"""
    total_pnl: Decimal
    total_pnl_percentage: Decimal
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: Decimal
    max_drawdown_percentage: float
    avg_win: Decimal
    avg_loss: Decimal
    best_trade: Decimal
    worst_trade: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_duration: timedelta
    total_fees: Decimal
    net_pnl: Decimal
    net_profit: Decimal  # Alias for net_pnl
    gross_profit: Decimal
    gross_loss: Decimal
    largest_win: Decimal  # Alias for best_trade
    largest_loss: Decimal  # Alias for worst_trade
    roi: float
    expectancy: Decimal
    recovery_factor: float
    calmar_ratio: float


@dataclass
class DailyPerformance:
    """Daily performance summary"""
    date: date
    pnl: Decimal
    trades: int
    win_rate: float
    volume: Decimal
    fees: Decimal
    positions_opened: int
    positions_closed: int
    max_drawdown: Decimal


@dataclass
class PositionAnalysis:
    """Detailed position analysis"""
    position_id: str
    symbol: str
    side: str
    entry_price: Decimal
    exit_price: Optional[Decimal]
    size: Decimal
    pnl: Decimal
    pnl_percentage: Decimal
    duration: timedelta
    max_profit: Decimal
    max_loss: Decimal
    fees: Decimal
    risk_reward_ratio: float
    mae: Decimal  # Maximum Adverse Excursion
    mfe: Decimal  # Maximum Favorable Excursion


class PerformanceTracker:
    """
    Comprehensive performance tracking and analysis
    
    Features:
    - Real-time P&L tracking
    - Historical performance analysis
    - Risk-adjusted returns calculation
    - Trade analytics
    - Performance attribution
    """
    
    def __init__(self,
                 repository: Repository,
                 config: Dict[str, Any]):
        
        self.repository = repository
        self.config = config
        
        # Performance calculation parameters
        self.risk_free_rate = config.get('risk_free_rate', 0.02)  # 2% annual
        self.calculation_period = config.get('calculation_period', 30)  # days
        self.min_trades_for_stats = config.get('min_trades_for_stats', 20)
        
        # Cached metrics
        self.current_metrics: Optional[PerformanceMetrics] = None
        self.daily_performance: Dict[date, DailyPerformance] = {}
        self.position_analysis: Dict[str, PositionAnalysis] = {}
        
        # Real-time tracking
        self.session_pnl = Decimal('0')
        self.session_trades = 0
        self.session_start = datetime.now(timezone.utc)
        
        # Performance history
        self.equity_curve: List[Tuple[datetime, Decimal]] = []
        self.drawdown_series: List[Tuple[datetime, Decimal]] = []
        
        # Update intervals
        self.metrics_update_interval = 60  # seconds
        self.last_metrics_update = datetime.min.replace(tzinfo=timezone.utc)
        
        logger.info("PerformanceTracker initialized")
    
    async def update_metrics(self, force: bool = False) -> PerformanceMetrics:
        """Update performance metrics"""
        
        now = datetime.now(timezone.utc)
        
        # Check if update needed
        if not force and self.current_metrics:
            if (now - self.last_metrics_update).seconds < self.metrics_update_interval:
                return self.current_metrics
        
        try:
            # Get all closed positions for period
            since = now - timedelta(days=self.calculation_period)
            positions = await self.repository.get_closed_positions_since(since)
            
            if not positions:
                return self._empty_metrics()
            
            # Calculate metrics
            metrics = await self._calculate_metrics(positions)
            
            # Cache results
            self.current_metrics = metrics
            self.last_metrics_update = now
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to update performance metrics: {e}")
            return self._empty_metrics()
    
    async def _calculate_metrics(self, positions: List[Position]) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics"""
        
        # Basic calculations
        total_pnl = Decimal(str(sum(p.realized_pnl or 0 for p in positions)))
        total_fees = Decimal(str(sum(p.fees or 0 for p in positions)))
        net_pnl = total_pnl - total_fees
        
        # Win/Loss statistics
        winning_trades = [p for p in positions if p.realized_pnl and p.realized_pnl > 0]
        losing_trades = [p for p in positions if p.realized_pnl and p.realized_pnl <= 0]
        
        win_rate = Decimal(str(len(winning_trades))) / Decimal(str(len(positions))) if positions else Decimal('0')
        
        # Average trade calculations
        avg_win = (Decimal(str(sum(p.realized_pnl for p in winning_trades))) / Decimal(str(len(winning_trades)))) \
                 if winning_trades else Decimal('0')
        avg_loss = (Decimal(str(sum(abs(p.realized_pnl) for p in losing_trades))) / Decimal(str(len(losing_trades)))) \
                  if losing_trades else Decimal('0')
        
        # Profit factor
        gross_profit = Decimal(str(sum(p.realized_pnl for p in winning_trades))) if winning_trades else Decimal('0')
        gross_loss = Decimal(str(sum(abs(p.realized_pnl) for p in losing_trades))) if losing_trades else Decimal('0')
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0
        
        # Best and worst trades
        best_trade = Decimal(str(max((float(p.realized_pnl or 0) for p in positions), default=0)))
        worst_trade = Decimal(str(min((float(p.realized_pnl or 0) for p in positions), default=0)))
        
        # Duration analysis
        durations = []
        for p in positions:
            if p.closed_at:
                duration = p.closed_at - p.opened_at
                durations.append(duration)
        
        avg_duration = (sum(durations, timedelta()) / len(durations)) if durations else timedelta()
        
        # Calculate returns for ratios
        returns = await self._calculate_returns(positions)
        
        # Risk-adjusted metrics
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        sortino_ratio = self._calculate_sortino_ratio(returns)
        
        # Drawdown analysis
        equity_curve = await self._build_equity_curve(positions)
        max_dd, max_dd_pct = self._calculate_max_drawdown(equity_curve)
        
        # Calculate expectancy
        expectancy = (win_rate * avg_win) - ((Decimal('1') - win_rate) * avg_loss)
        
        # ROI calculation
        initial_capital = await self._get_initial_capital()
        roi = float((net_pnl / initial_capital) * 100) if initial_capital > 0 else 0
        
        # Recovery factor
        recovery_factor = float(net_pnl / max_dd) if max_dd > 0 else 0.0
        
        # Calmar ratio (annual return / max drawdown)
        days_traded = (positions[-1].closed_at - positions[0].opened_at).days if len(positions) > 1 else 1
        annual_return = (net_pnl / initial_capital) * Decimal(str(365 / days_traded)) if initial_capital > 0 and days_traded > 0 else Decimal('0')
        calmar_ratio = float(annual_return / Decimal(str(max_dd_pct))) if max_dd_pct > 0 else 0.0
        
        # Calculate total P&L percentage
        total_pnl_percentage = (total_pnl / initial_capital * Decimal('100')) if initial_capital > 0 else Decimal('0')
        
        return PerformanceMetrics(
            total_pnl=total_pnl,
            total_pnl_percentage=total_pnl_percentage,
            win_rate=float(win_rate * Decimal('100')),
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_dd,
            max_drawdown_percentage=max_dd_pct,
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade=best_trade,
            worst_trade=worst_trade,
            total_trades=len(positions),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            avg_trade_duration=avg_duration,
            total_fees=total_fees,
            net_pnl=net_pnl,
            net_profit=net_pnl,  # Alias
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            largest_win=best_trade,  # Alias
            largest_loss=worst_trade,  # Alias
            roi=roi,
            expectancy=expectancy,
            recovery_factor=recovery_factor,
            calmar_ratio=calmar_ratio
        )
    
    async def _calculate_returns(self, positions: List[Position]) -> List[float]:
        """Calculate returns series for risk metrics"""
        
        returns = []
        
        for p in positions:
            if p.realized_pnl and p.entry_price and hasattr(p, 'quantity'):
                # Calculate return percentage
                capital_used = abs(Decimal(str(p.entry_price)) * Decimal(str(p.quantity)))
                if capital_used > 0:
                    return_pct = float(Decimal(str(p.realized_pnl)) / capital_used)
                    returns.append(return_pct)
        
        return returns
    
    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio"""
        
        if len(returns) < self.min_trades_for_stats:
            return 0
        
        returns_array = np.array(returns)
        
        # Calculate average and standard deviation
        avg_return = np.mean(returns_array)
        std_return = np.std(returns_array)
        
        if std_return == 0:
            return 0
        
        # Annualize (assuming daily returns)
        annual_return = avg_return * 252
        annual_std = std_return * np.sqrt(252)
        
        # Sharpe ratio
        sharpe = (annual_return - self.risk_free_rate) / annual_std
        
        return float(sharpe)
    
    # Alias for compatibility
    _calculate_sharpe = _calculate_sharpe_ratio
    
    def _calculate_sortino_ratio(self, returns: List[float]) -> float:
        """Calculate Sortino ratio (uses downside deviation)"""
        
        if len(returns) < self.min_trades_for_stats:
            return 0
        
        returns_array = np.array(returns)
        
        # Calculate average return
        avg_return = np.mean(returns_array)
        
        # Calculate downside deviation
        downside_returns = returns_array[returns_array < 0]
        if len(downside_returns) == 0:
            return float('inf')  # No downside
        
        downside_std = np.std(downside_returns)
        
        if downside_std == 0:
            return 0
        
        # Annualize
        annual_return = avg_return * 252
        annual_downside_std = downside_std * np.sqrt(252)
        
        # Sortino ratio
        sortino = (annual_return - self.risk_free_rate) / annual_downside_std
        
        return float(sortino)
    
    # Alias for compatibility
    _calculate_sortino = _calculate_sortino_ratio
    
    async def _build_equity_curve(self, positions: List[Position]) -> List[Tuple[datetime, Decimal]]:
        """Build equity curve from positions"""
        
        initial_capital = await self._get_initial_capital()
        equity = initial_capital
        curve = [(self.session_start, equity)]
        
        # Sort positions by close time
        sorted_positions = sorted(positions, key=lambda p: p.closed_at or datetime.max.replace(tzinfo=timezone.utc))
        
        for position in sorted_positions:
            if position.closed_at and position.realized_pnl:
                equity += Decimal(str(position.realized_pnl))
                # Convert Column[datetime] to datetime if needed
                if hasattr(position.closed_at, '__class__') and 'Column' not in str(type(position.closed_at)):
                    closed_at_dt = position.closed_at
                else:
                    closed_at_dt = datetime.fromisoformat(str(position.closed_at)) if isinstance(position.closed_at, str) else position.closed_at
                curve.append((closed_at_dt, equity))
        
        self.equity_curve = curve
        return curve
    
    def _calculate_max_drawdown(self, equity_curve: List[Tuple[datetime, Decimal]]) -> Tuple[Decimal, float]:
        """Calculate maximum drawdown from equity curve"""
        
        if len(equity_curve) < 2:
            return Decimal('0'), 0
        
        peak = equity_curve[0][1]
        max_dd = Decimal('0')
        max_dd_pct = 0
        
        for timestamp, equity in equity_curve:
            if equity > peak:
                peak = equity
            
            drawdown = peak - equity
            drawdown_pct = float(drawdown / peak * 100) if peak > 0 else 0
            
            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_pct = float(drawdown_pct)
            
            # Track drawdown series
            self.drawdown_series.append((timestamp, drawdown))
        
        return max_dd, max_dd_pct
    
    async def _get_initial_capital(self) -> Decimal:
        """Get initial trading capital"""
        
        # This should be fetched from configuration or database
        return Decimal(str(self.config.get('initial_capital', 10000)))
    
    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics object"""
        
        return PerformanceMetrics(
            total_pnl=Decimal('0'),
            total_pnl_percentage=Decimal('0'),
            win_rate=0,
            profit_factor=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            max_drawdown=Decimal('0'),
            max_drawdown_percentage=0,
            avg_win=Decimal('0'),
            avg_loss=Decimal('0'),
            best_trade=Decimal('0'),
            worst_trade=Decimal('0'),
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_trade_duration=timedelta(),
            total_fees=Decimal('0'),
            net_pnl=Decimal('0'),
            roi=0,
            expectancy=Decimal('0'),
            recovery_factor=0,
            calmar_ratio=0,
            net_profit=Decimal('0'),
            gross_profit=Decimal('0'),
            gross_loss=Decimal('0'),
            largest_win=Decimal('0'),
            largest_loss=Decimal('0')
        )
    
    async def get_daily_performance(self, 
                                   start_date: date,
                                   end_date: date) -> List[DailyPerformance]:
        """Get daily performance for date range"""
        
        daily_stats = []
        current_date = start_date
        
        while current_date <= end_date:
            # Get positions closed on this date
            positions = await self.repository.get_positions_by_date(current_date)
            
            if positions:
                # Calculate daily metrics
                daily_pnl = sum(p.realized_pnl for p in positions if p.realized_pnl)
                daily_fees = sum(p.fees for p in positions if p.fees)
                daily_volume = sum(abs(p.quantity * p.entry_price) for p in positions)
                
                wins = [p for p in positions if p.realized_pnl and p.realized_pnl > 0]
                win_rate = (len(wins) / len(positions)) * 100 if positions else 0
                
                # Count opened vs closed
                opened = len([p for p in positions if p.opened_at.date() == current_date])
                closed = len([p for p in positions if p.closed_at and p.closed_at.date() == current_date])
                
                # Daily drawdown
                equity_start = await self._get_equity_at_date(current_date)
                equity_end = equity_start + daily_pnl
                daily_dd = max(Decimal('0'), equity_start - equity_end)
                
                daily_perf = DailyPerformance(
                    date=current_date,
                    pnl=daily_pnl,
                    trades=len(positions),
                    win_rate=win_rate,
                    volume=daily_volume,
                    fees=daily_fees,
                    positions_opened=opened,
                    positions_closed=closed,
                    max_drawdown=daily_dd
                )
                
                daily_stats.append(daily_perf)
                self.daily_performance[current_date] = daily_perf
            
            current_date += timedelta(days=1)
        
        return daily_stats
    
    async def _get_equity_at_date(self, target_date: date) -> Decimal:
        """Get account equity at specific date"""
        
        initial = await self._get_initial_capital()
        
        # Sum all P&L up to this date
        positions = await self.repository.get_closed_positions_before(target_date)
        total_pnl = sum(p.realized_pnl for p in positions if p.realized_pnl)
        
        return initial + total_pnl
    
    async def analyze_position(self, position: Position) -> PositionAnalysis:
        """Perform detailed analysis of a single position"""
        
        try:
            # Get price history during position
            price_history = await self._get_position_price_history(position)
            
            # Calculate MAE/MFE
            mae, mfe = self._calculate_mae_mfe(position, price_history)
            
            # Calculate risk-reward
            if position.stop_loss_price:
                risk = abs(position.entry_price - position.stop_loss_price)
                reward = abs(position.exit_price - position.entry_price) if position.exit_price else 0
                rr_ratio = float(reward / risk) if risk > 0 else 0
            else:
                rr_ratio = 0
            
            # Calculate max profit/loss during position
            if position.side == 'long':
                max_profit = (max(price_history) - position.entry_price) * position.quantity
                max_loss = (position.entry_price - min(price_history)) * position.quantity
            else:
                max_profit = (position.entry_price - min(price_history)) * abs(position.quantity)
                max_loss = (max(price_history) - position.entry_price) * abs(position.quantity)
            
            analysis = PositionAnalysis(
                position_id=str(position.id),
                symbol=str(position.symbol),
                side=str(position.side),
                entry_price=Decimal(str(position.entry_price)),
                exit_price=Decimal(str(position.exit_price)) if position.exit_price else None,
                size=Decimal(str(position.quantity)),
                pnl=Decimal(str(position.realized_pnl)) if position.realized_pnl else Decimal('0'),
                pnl_percentage=(Decimal(str(position.realized_pnl)) / (Decimal(str(position.entry_price)) * abs(Decimal(str(position.quantity)))) * 100)
                              if position.realized_pnl else Decimal('0'),
                duration=position.closed_at - position.opened_at if position.closed_at else timedelta(),
                max_profit=Decimal(str(max_profit)),
                max_loss=Decimal(str(max_loss)),
                fees=Decimal(str(position.fees)) if position.fees else Decimal('0'),
                risk_reward_ratio=rr_ratio,
                mae=mae,
                mfe=mfe
            )
            
            # Cache analysis
            self.position_analysis[str(position.id)] = analysis
            
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to analyze position {position.id}: {e}")
            raise
    
    async def _get_position_price_history(self, position: Position) -> List[Decimal]:
        """Get price history during position lifetime"""
        
        # This should fetch actual price data
        # For now, returning mock data
        return [Decimal(str(position.entry_price))]
    
    def _calculate_mae_mfe(self, 
                          position: Position,
                          price_history: List[Decimal]) -> Tuple[Decimal, Decimal]:
        """Calculate Maximum Adverse/Favorable Excursion"""
        
        if not price_history:
            return Decimal('0'), Decimal('0')
        
        entry = position.entry_price
        
        if position.side == 'long':
            mae = entry - min(price_history)
            mfe = max(price_history) - entry
        else:
            mae = max(price_history) - entry
            mfe = entry - min(price_history)
        
        mae_decimal = Decimal(str(mae)) if not isinstance(mae, Decimal) else mae
        mfe_decimal = Decimal(str(mfe)) if not isinstance(mfe, Decimal) else mfe
        return max(Decimal('0'), mae_decimal), max(Decimal('0'), mfe_decimal)
    
    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        
        metrics = await self.update_metrics()
        
        return {
            'overview': {
                'total_pnl': float(metrics.total_pnl),
                'total_pnl_percentage': float(metrics.total_pnl_percentage),
                'net_pnl': float(metrics.net_pnl),
                'roi': metrics.roi,
                'total_trades': metrics.total_trades
            },
            'statistics': {
                'win_rate': metrics.win_rate,
                'profit_factor': metrics.profit_factor,
                'expectancy': float(metrics.expectancy),
                'avg_win': float(metrics.avg_win),
                'avg_loss': float(metrics.avg_loss),
                'best_trade': float(metrics.best_trade),
                'worst_trade': float(metrics.worst_trade)
            },
            'risk_metrics': {
                'sharpe_ratio': metrics.sharpe_ratio,
                'sortino_ratio': metrics.sortino_ratio,
                'max_drawdown': float(metrics.max_drawdown),
                'max_drawdown_percentage': metrics.max_drawdown_percentage,
                'recovery_factor': metrics.recovery_factor,
                'calmar_ratio': metrics.calmar_ratio
            },
            'session': {
                'session_pnl': float(self.session_pnl),
                'session_trades': self.session_trades,
                'session_duration': str(datetime.now(timezone.utc) - self.session_start)
            }
        }
    
    def record_trade(self, position: Position):
        """Record completed trade for session tracking"""
        
        if position.realized_pnl:
            self.session_pnl += Decimal(str(position.realized_pnl))
            self.session_trades += 1
    
    async def export_performance_report(self, filepath: str):
        """Export detailed performance report to file"""
        
        try:
            metrics = await self.update_metrics()
            daily = await self.get_daily_performance(
                date.today() - timedelta(days=30),
                date.today()
            )
            
            # Create report data
            report = {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'period': f"{self.calculation_period} days",
                'metrics': metrics.__dict__,
                'daily_performance': [d.__dict__ for d in daily],
                'equity_curve': [(t.isoformat(), float(v)) for t, v in self.equity_curve]
            }
            
            # Save to file (could be JSON, CSV, etc.)
            import json
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            logger.info(f"Performance report exported to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to export performance report: {e}")