#!/usr/bin/env python3
"""
Advanced backtesting system for trading strategies with realistic simulation
"""

import asyncio
import argparse
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal, getcontext
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from pathlib import Path
import json
from loguru import logger
import ccxt

# Set decimal precision for accurate calculations
getcontext().prec = 28


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    strategy_name: str
    exchange: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    leverage: float = 1.0
    maker_fee: Decimal = Decimal('0.0002')  # 0.02%
    taker_fee: Decimal = Decimal('0.0004')  # 0.04%
    slippage_pct: Decimal = Decimal('0.0005')  # 0.05%
    position_size_pct: Decimal = Decimal('0.1')  # 10% per position
    max_positions: int = 5
    stop_loss_pct: Decimal = Decimal('2.0')  # 2%
    take_profit_pct: Decimal = Decimal('5.0')  # 5%
    use_trailing_stop: bool = True
    trailing_stop_pct: Decimal = Decimal('1.0')  # 1%
    risk_per_trade: Decimal = Decimal('0.01')  # 1% risk per trade


@dataclass
class BacktestPosition:
    """Position in backtest"""
    id: str
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: Decimal
    entry_time: datetime
    size: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    trailing_stop: Optional[Decimal] = None
    highest_price: Optional[Decimal] = None
    lowest_price: Optional[Decimal] = None
    exit_price: Optional[Decimal] = None
    exit_time: Optional[datetime] = None
    pnl: Decimal = Decimal('0')
    pnl_percentage: Decimal = Decimal('0')
    fees: Decimal = Decimal('0')
    status: str = 'open'  # open, closed, liquidated


@dataclass
class BacktestResults:
    """Backtesting results"""
    config: BacktestConfig
    positions: List[BacktestPosition]
    
    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    
    # P&L metrics
    gross_profit: Decimal = Decimal('0')
    gross_loss: Decimal = Decimal('0')
    net_profit: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')
    
    # Risk metrics
    max_drawdown: Decimal = Decimal('0')
    max_drawdown_pct: float = 0
    profit_factor: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    
    # Trade statistics
    avg_win: Decimal = Decimal('0')
    avg_loss: Decimal = Decimal('0')
    largest_win: Decimal = Decimal('0')
    largest_loss: Decimal = Decimal('0')
    avg_trade_duration: timedelta = timedelta()
    
    # Final metrics
    final_balance: Decimal = Decimal('0')
    roi: float = 0
    annual_return: float = 0
    
    # Time series data
    equity_curve: List[Tuple[datetime, Decimal]] = field(default_factory=list)
    drawdown_curve: List[Tuple[datetime, Decimal]] = field(default_factory=list)


class Backtester:
    """
    Advanced backtesting engine with realistic market simulation
    
    Features:
    - Realistic order execution with slippage
    - Multiple position management
    - Risk management rules
    - Transaction costs
    - Margin and liquidation
    - Performance analytics
    """
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.exchange = None
        
        # State management
        self.balance = config.initial_capital
        self.available_balance = config.initial_capital
        self.equity = config.initial_capital
        self.peak_equity = config.initial_capital
        
        # Positions
        self.positions: Dict[str, BacktestPosition] = {}
        self.closed_positions: List[BacktestPosition] = []
        self.position_counter = 0
        
        # Market data
        self.candles: pd.DataFrame = pd.DataFrame()
        self.current_candle = None
        self.current_index = 0
        
        # Performance tracking
        self.equity_curve = [(config.start_date, config.initial_capital)]
        self.trades_log = []
        
        logger.info(f"Backtester initialized for {config.symbol} on {config.exchange}")
    
    async def initialize(self):
        """Initialize exchange connection and load data"""
        
        try:
            # Initialize exchange
            exchange_class = getattr(ccxt, self.config.exchange)
            self.exchange = exchange_class({
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            
            # Load market data
            await self.load_historical_data()
            
            logger.info(f"Loaded {len(self.candles)} candles for backtesting")
            
        except Exception as e:
            logger.error(f"Failed to initialize backtester: {e}")
            raise
    
    async def load_historical_data(self):
        """Load historical OHLCV data"""
        
        try:
            logger.info(f"Loading data from {self.config.start_date} to {self.config.end_date}")
            
            all_candles = []
            since = int(self.config.start_date.timestamp() * 1000)
            end_timestamp = int(self.config.end_date.timestamp() * 1000)
            
            # Fetch data in chunks
            while since < end_timestamp:
                candles = self.exchange.fetch_ohlcv(
                    self.config.symbol,
                    timeframe=self.config.timeframe,
                    since=since,
                    limit=1000
                )
                
                if not candles:
                    break
                
                all_candles.extend(candles)
                since = candles[-1][0] + 1
                
                # Rate limit respect
                await asyncio.sleep(self.exchange.rateLimit / 1000)
            
            # Convert to DataFrame
            self.candles = pd.DataFrame(
                all_candles,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Convert timestamp to datetime
            self.candles['datetime'] = pd.to_datetime(self.candles['timestamp'], unit='ms')
            self.candles.set_index('datetime', inplace=True)
            
            # Convert to Decimal for precision
            for col in ['open', 'high', 'low', 'close', 'volume']:
                self.candles[col] = self.candles[col].apply(Decimal)
            
            # Add technical indicators
            self._calculate_indicators()
            
        except Exception as e:
            logger.error(f"Failed to load historical data: {e}")
            raise
    
    def _calculate_indicators(self):
        """Calculate technical indicators for strategy"""
        
        # Simple Moving Averages
        self.candles['sma_20'] = self.candles['close'].rolling(window=20).mean()
        self.candles['sma_50'] = self.candles['close'].rolling(window=50).mean()
        self.candles['sma_200'] = self.candles['close'].rolling(window=200).mean()
        
        # Exponential Moving Averages
        self.candles['ema_12'] = self.candles['close'].ewm(span=12).mean()
        self.candles['ema_26'] = self.candles['close'].ewm(span=26).mean()
        
        # MACD
        self.candles['macd'] = self.candles['ema_12'] - self.candles['ema_26']
        self.candles['macd_signal'] = self.candles['macd'].ewm(span=9).mean()
        self.candles['macd_histogram'] = self.candles['macd'] - self.candles['macd_signal']
        
        # RSI
        self.candles['rsi'] = self._calculate_rsi(self.candles['close'], 14)
        
        # Bollinger Bands
        self.candles['bb_middle'] = self.candles['close'].rolling(window=20).mean()
        bb_std = self.candles['close'].rolling(window=20).std()
        self.candles['bb_upper'] = self.candles['bb_middle'] + (bb_std * 2)
        self.candles['bb_lower'] = self.candles['bb_middle'] - (bb_std * 2)
        
        # ATR for volatility
        self.candles['atr'] = self._calculate_atr(14)
        
        # Volume indicators
        self.candles['volume_sma'] = self.candles['volume'].rolling(window=20).mean()
        self.candles['volume_ratio'] = self.candles['volume'] / self.candles['volume_sma']
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_atr(self, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        
        high = self.candles['high']
        low = self.candles['low']
        close = self.candles['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    async def run(self) -> BacktestResults:
        """Run the backtest"""
        
        logger.info("Starting backtest...")
        
        # Initialize results
        results = BacktestResults(config=self.config)
        
        # Iterate through each candle
        for idx in range(50, len(self.candles)):  # Start at 50 for indicators
            self.current_index = idx
            self.current_candle = self.candles.iloc[idx]
            
            # Update position tracking
            self._update_positions()
            
            # Check for signals
            signal = await self._generate_signal()
            
            # Execute trades based on signals
            if signal:
                await self._execute_signal(signal)
            
            # Check stop losses and take profits
            self._check_exits()
            
            # Update equity
            self._update_equity()
            
            # Record equity curve
            if idx % 10 == 0:  # Record every 10 candles
                results.equity_curve.append((
                    self.current_candle.name,
                    self.equity
                ))
        
        # Close all remaining positions
        self._close_all_positions()
        
        # Calculate final metrics
        results = self._calculate_results(results)
        
        logger.info(f"Backtest completed. Final balance: {results.final_balance:.2f}")
        
        return results
    
    async def _generate_signal(self) -> Optional[Dict[str, Any]]:
        """Generate trading signal based on strategy"""
        
        # Example strategy: Moving Average Crossover with RSI filter
        candle = self.current_candle
        prev_candle = self.candles.iloc[self.current_index - 1]
        
        # Check if we can open more positions
        if len(self.positions) >= self.config.max_positions:
            return None
        
        # Long signal: Fast MA crosses above Slow MA and RSI < 70
        if (prev_candle['ema_12'] <= prev_candle['ema_26'] and 
            candle['ema_12'] > candle['ema_26'] and
            candle['rsi'] < 70):
            
            return {
                'action': 'open_long',
                'price': candle['close'],
                'reason': 'EMA crossover bullish'
            }
        
        # Short signal: Fast MA crosses below Slow MA and RSI > 30
        if (prev_candle['ema_12'] >= prev_candle['ema_26'] and 
            candle['ema_12'] < candle['ema_26'] and
            candle['rsi'] > 30):
            
            return {
                'action': 'open_short',
                'price': candle['close'],
                'reason': 'EMA crossover bearish'
            }
        
        return None
    
    async def _execute_signal(self, signal: Dict[str, Any]):
        """Execute trading signal"""
        
        if signal['action'] == 'open_long':
            await self._open_position('long', signal['price'])
        elif signal['action'] == 'open_short':
            await self._open_position('short', signal['price'])
    
    async def _open_position(self, side: str, price: Decimal):
        """Open a new position"""
        
        # Calculate position size based on risk
        position_size = self._calculate_position_size(price)
        
        if position_size <= 0:
            return
        
        # Apply slippage
        if side == 'long':
            entry_price = price * (1 + self.config.slippage_pct / 100)
        else:
            entry_price = price * (1 - self.config.slippage_pct / 100)
        
        # Calculate fees
        fees = position_size * entry_price * self.config.taker_fee
        
        # Check if we have enough balance
        required_margin = (position_size * entry_price) / self.config.leverage
        if required_margin + fees > self.available_balance:
            logger.debug(f"Insufficient balance for position. Required: {required_margin:.2f}")
            return
        
        # Create position
        self.position_counter += 1
        position_id = f"BT_{self.position_counter:05d}"
        
        # Calculate stop loss and take profit
        if side == 'long':
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
        
        position = BacktestPosition(
            id=position_id,
            symbol=self.config.symbol,
            side=side,
            entry_price=entry_price,
            entry_time=self.current_candle.name,
            size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            fees=fees,
            highest_price=entry_price if side == 'long' else None,
            lowest_price=entry_price if side == 'short' else None
        )
        
        # Update balances
        self.available_balance -= (required_margin + fees)
        
        # Store position
        self.positions[position_id] = position
        
        # Log trade
        self.trades_log.append({
            'time': self.current_candle.name,
            'action': f'open_{side}',
            'price': float(entry_price),
            'size': float(position_size),
            'balance': float(self.balance)
        })
        
        logger.debug(f"Opened {side} position: {position_id} at {entry_price:.2f}")
    
    def _calculate_position_size(self, price: Decimal) -> Decimal:
        """Calculate position size based on risk management"""
        
        # Method 1: Fixed percentage of capital
        capital_risk = self.available_balance * self.config.position_size_pct
        
        # Method 2: Risk-based sizing (1R = 1% of capital)
        risk_amount = self.balance * self.config.risk_per_trade
        stop_distance = price * self.config.stop_loss_pct / 100
        risk_based_size = risk_amount / stop_distance
        
        # Use the smaller of the two
        position_size = min(capital_risk / price, risk_based_size)
        
        return position_size
    
    def _update_positions(self):
        """Update position tracking with current prices"""
        
        for position_id, position in self.positions.items():
            if position.side == 'long':
                # Track highest price for trailing stop
                if self.current_candle['high'] > position.highest_price:
                    position.highest_price = self.current_candle['high']
                    
                    # Update trailing stop if enabled
                    if self.config.use_trailing_stop:
                        trailing_stop = position.highest_price * (1 - self.config.trailing_stop_pct / 100)
                        if trailing_stop > position.stop_loss:
                            position.trailing_stop = trailing_stop
            
            else:  # short
                # Track lowest price for trailing stop
                if position.lowest_price is None or self.current_candle['low'] < position.lowest_price:
                    position.lowest_price = self.current_candle['low']
                    
                    # Update trailing stop if enabled
                    if self.config.use_trailing_stop:
                        trailing_stop = position.lowest_price * (1 + self.config.trailing_stop_pct / 100)
                        if position.trailing_stop is None or trailing_stop < position.trailing_stop:
                            position.trailing_stop = trailing_stop
    
    def _check_exits(self):
        """Check for position exits (SL, TP, trailing)"""
        
        positions_to_close = []
        
        for position_id, position in self.positions.items():
            close_price = None
            close_reason = None
            
            if position.side == 'long':
                # Check stop loss
                effective_stop = position.trailing_stop or position.stop_loss
                if self.current_candle['low'] <= effective_stop:
                    close_price = effective_stop
                    close_reason = 'stop_loss'
                
                # Check take profit
                elif self.current_candle['high'] >= position.take_profit:
                    close_price = position.take_profit
                    close_reason = 'take_profit'
            
            else:  # short
                # Check stop loss
                effective_stop = position.trailing_stop or position.stop_loss
                if self.current_candle['high'] >= effective_stop:
                    close_price = effective_stop
                    close_reason = 'stop_loss'
                
                # Check take profit
                elif self.current_candle['low'] <= position.take_profit:
                    close_price = position.take_profit
                    close_reason = 'take_profit'
            
            if close_price:
                positions_to_close.append((position_id, close_price, close_reason))
        
        # Close positions
        for position_id, price, reason in positions_to_close:
            self._close_position(position_id, price, reason)
    
    def _close_position(self, position_id: str, exit_price: Decimal, reason: str):
        """Close a position"""
        
        position = self.positions[position_id]
        
        # Apply slippage for stop losses
        if reason == 'stop_loss':
            if position.side == 'long':
                exit_price = exit_price * (1 - self.config.slippage_pct / 100)
            else:
                exit_price = exit_price * (1 + self.config.slippage_pct / 100)
        
        # Calculate P&L
        if position.side == 'long':
            pnl = (exit_price - position.entry_price) * position.size
        else:
            pnl = (position.entry_price - exit_price) * position.size
        
        # Calculate fees
        exit_fees = position.size * exit_price * self.config.taker_fee
        total_fees = position.fees + exit_fees
        
        # Net P&L
        net_pnl = pnl - total_fees
        pnl_percentage = (net_pnl / (position.entry_price * position.size)) * 100
        
        # Update position
        position.exit_price = exit_price
        position.exit_time = self.current_candle.name
        position.pnl = net_pnl
        position.pnl_percentage = pnl_percentage
        position.fees = total_fees
        position.status = 'closed'
        
        # Update balances
        margin_released = (position.size * position.entry_price) / self.config.leverage
        self.available_balance += margin_released + net_pnl
        self.balance += net_pnl
        
        # Move to closed positions
        self.closed_positions.append(position)
        del self.positions[position_id]
        
        # Log trade
        self.trades_log.append({
            'time': self.current_candle.name,
            'action': f'close_{position.side}',
            'price': float(exit_price),
            'pnl': float(net_pnl),
            'reason': reason,
            'balance': float(self.balance)
        })
        
        logger.debug(f"Closed {position.side} position: {position_id} at {exit_price:.2f}, "
                    f"PnL: {net_pnl:.2f} ({pnl_percentage:.2f}%), Reason: {reason}")
    
    def _close_all_positions(self):
        """Close all remaining positions at market"""
        
        for position_id in list(self.positions.keys()):
            self._close_position(
                position_id,
                self.current_candle['close'],
                'end_of_backtest'
            )
    
    def _update_equity(self):
        """Update current equity value"""
        
        # Calculate unrealized P&L
        unrealized_pnl = Decimal('0')
        
        for position in self.positions.values():
            if position.side == 'long':
                current_pnl = (self.current_candle['close'] - position.entry_price) * position.size
            else:
                current_pnl = (position.entry_price - self.current_candle['close']) * position.size
            
            unrealized_pnl += current_pnl
        
        # Update equity
        self.equity = self.balance + unrealized_pnl
        
        # Track peak for drawdown
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
    
    def _calculate_results(self, results: BacktestResults) -> BacktestResults:
        """Calculate final backtest metrics"""
        
        results.positions = self.closed_positions
        results.total_trades = len(self.closed_positions)
        
        if results.total_trades == 0:
            return results
        
        # Win/Loss statistics
        winning_trades = [p for p in self.closed_positions if p.pnl > 0]
        losing_trades = [p for p in self.closed_positions if p.pnl <= 0]
        
        results.winning_trades = len(winning_trades)
        results.losing_trades = len(losing_trades)
        results.win_rate = (results.winning_trades / results.total_trades) * 100 if results.total_trades > 0 else 0
        
        # P&L metrics
        results.gross_profit = sum(p.pnl for p in winning_trades)
        results.gross_loss = abs(sum(p.pnl for p in losing_trades))
        results.net_profit = results.gross_profit - results.gross_loss
        results.total_fees = sum(p.fees for p in self.closed_positions)
        
        # Average metrics
        results.avg_win = results.gross_profit / results.winning_trades if results.winning_trades > 0 else Decimal('0')
        results.avg_loss = results.gross_loss / results.losing_trades if results.losing_trades > 0 else Decimal('0')
        
        # Largest win/loss
        if winning_trades:
            results.largest_win = max(p.pnl for p in winning_trades)
        if losing_trades:
            results.largest_loss = min(p.pnl for p in losing_trades)
        
        # Trade duration
        durations = []
        for p in self.closed_positions:
            if p.exit_time:
                duration = p.exit_time - p.entry_time
                durations.append(duration)
        
        if durations:
            results.avg_trade_duration = sum(durations, timedelta()) / len(durations)
        
        # Calculate drawdown
        results.max_drawdown, results.max_drawdown_pct = self._calculate_max_drawdown(results.equity_curve)
        
        # Risk metrics
        if results.gross_loss > 0:
            results.profit_factor = float(results.gross_profit / results.gross_loss)
        
        # Calculate Sharpe ratio
        returns = [float(p.pnl_percentage) for p in self.closed_positions]
        if len(returns) > 1:
            results.sharpe_ratio = self._calculate_sharpe(returns)
            results.sortino_ratio = self._calculate_sortino(returns)
        
        # Calmar ratio
        if results.max_drawdown_pct > 0:
            annual_return = self._calculate_annual_return(results)
            results.calmar_ratio = annual_return / results.max_drawdown_pct
        
        # Final metrics
        results.final_balance = self.balance
        results.roi = float((self.balance - self.config.initial_capital) / self.config.initial_capital * 100)
        results.annual_return = self._calculate_annual_return(results)
        
        return results
    
    def _calculate_max_drawdown(self, equity_curve: List[Tuple[datetime, Decimal]]) -> Tuple[Decimal, float]:
        """Calculate maximum drawdown"""
        
        if not equity_curve:
            return Decimal('0'), 0
        
        peak = equity_curve[0][1]
        max_dd = Decimal('0')
        max_dd_pct = 0
        
        for _, equity in equity_curve:
            if equity > peak:
                peak = equity
            
            drawdown = peak - equity
            drawdown_pct = float(drawdown / peak * 100) if peak > 0 else 0
            
            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_pct = drawdown_pct
        
        return max_dd, max_dd_pct
    
    def _calculate_sharpe(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio"""
        
        if not returns:
            return 0
        
        returns_array = np.array(returns)
        avg_return = np.mean(returns_array)
        std_return = np.std(returns_array)
        
        if std_return == 0:
            return 0
        
        # Assuming daily returns, annualize
        sharpe = (avg_return - 0.02/252) / std_return * np.sqrt(252)
        
        return float(sharpe)
    
    def _calculate_sortino(self, returns: List[float]) -> float:
        """Calculate Sortino ratio"""
        
        if not returns:
            return 0
        
        returns_array = np.array(returns)
        avg_return = np.mean(returns_array)
        
        # Downside deviation
        downside_returns = returns_array[returns_array < 0]
        if len(downside_returns) == 0:
            return float('inf')
        
        downside_std = np.std(downside_returns)
        
        if downside_std == 0:
            return 0
        
        # Assuming daily returns, annualize
        sortino = (avg_return - 0.02/252) / downside_std * np.sqrt(252)
        
        return float(sortino)
    
    def _calculate_annual_return(self, results: BacktestResults) -> float:
        """Calculate annualized return"""
        
        if not self.closed_positions:
            return 0
        
        days = (self.config.end_date - self.config.start_date).days
        if days == 0:
            return 0
        
        total_return = float(results.roi / 100)
        annual_return = ((1 + total_return) ** (365 / days) - 1) * 100
        
        return annual_return
    
    def save_results(self, results: BacktestResults, filepath: str):
        """Save backtest results to file"""
        
        output = {
            'config': {
                'strategy': results.config.strategy_name,
                'exchange': results.config.exchange,
                'symbol': results.config.symbol,
                'timeframe': results.config.timeframe,
                'start_date': results.config.start_date.isoformat(),
                'end_date': results.config.end_date.isoformat(),
                'initial_capital': float(results.config.initial_capital)
            },
            'performance': {
                'total_trades': results.total_trades,
                'winning_trades': results.winning_trades,
                'losing_trades': results.losing_trades,
                'win_rate': results.win_rate,
                'profit_factor': results.profit_factor,
                'net_profit': float(results.net_profit),
                'roi': results.roi,
                'annual_return': results.annual_return
            },
            'risk_metrics': {
                'max_drawdown': float(results.max_drawdown),
                'max_drawdown_pct': results.max_drawdown_pct,
                'sharpe_ratio': results.sharpe_ratio,
                'sortino_ratio': results.sortino_ratio,
                'calmar_ratio': results.calmar_ratio
            },
            'trade_stats': {
                'avg_win': float(results.avg_win),
                'avg_loss': float(results.avg_loss),
                'largest_win': float(results.largest_win),
                'largest_loss': float(results.largest_loss),
                'avg_trade_duration': str(results.avg_trade_duration)
            },
            'trades': [
                {
                    'id': p.id,
                    'side': p.side,
                    'entry_price': float(p.entry_price),
                    'exit_price': float(p.exit_price) if p.exit_price else None,
                    'size': float(p.size),
                    'pnl': float(p.pnl),
                    'pnl_percentage': float(p.pnl_percentage),
                    'entry_time': p.entry_time.isoformat() if p.entry_time else None,
                    'exit_time': p.exit_time.isoformat() if p.exit_time else None
                }
                for p in results.positions
            ],
            'equity_curve': [
                {'time': t.isoformat(), 'equity': float(e)}
                for t, e in results.equity_curve
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"Results saved to {filepath}")
    
    def print_summary(self, results: BacktestResults):
        """Print backtest summary"""
        
        print("\n" + "="*60)
        print(" BACKTEST RESULTS SUMMARY")
        print("="*60)
        
        print(f"\nStrategy: {results.config.strategy_name}")
        print(f"Symbol: {results.config.symbol}")
        print(f"Period: {results.config.start_date.date()} to {results.config.end_date.date()}")
        
        print(f"\n--- Performance ---")
        print(f"Initial Capital: ${results.config.initial_capital:,.2f}")
        print(f"Final Balance: ${results.final_balance:,.2f}")
        print(f"Net Profit: ${results.net_profit:,.2f}")
        print(f"ROI: {results.roi:.2f}%")
        print(f"Annual Return: {results.annual_return:.2f}%")
        
        print(f"\n--- Trade Statistics ---")
        print(f"Total Trades: {results.total_trades}")
        print(f"Winning Trades: {results.winning_trades}")
        print(f"Losing Trades: {results.losing_trades}")
        print(f"Win Rate: {results.win_rate:.2f}%")
        print(f"Profit Factor: {results.profit_factor:.2f}")
        
        print(f"\n--- Risk Metrics ---")
        print(f"Max Drawdown: ${results.max_drawdown:.2f} ({results.max_drawdown_pct:.2f}%)")
        print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        print(f"Sortino Ratio: {results.sortino_ratio:.2f}")
        print(f"Calmar Ratio: {results.calmar_ratio:.2f}")
        
        print(f"\n--- Trade Analysis ---")
        print(f"Average Win: ${results.avg_win:.2f}")
        print(f"Average Loss: ${results.avg_loss:.2f}")
        print(f"Largest Win: ${results.largest_win:.2f}")
        print(f"Largest Loss: ${results.largest_loss:.2f}")
        print(f"Average Duration: {results.avg_trade_duration}")
        
        print(f"\n--- Costs ---")
        print(f"Total Fees: ${results.total_fees:.2f}")
        
        print("="*60)


async def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(description='Backtest trading strategy')
    parser.add_argument('--exchange', default='binance', help='Exchange name')
    parser.add_argument('--symbol', default='BTC/USDT', help='Trading symbol')
    parser.add_argument('--timeframe', default='1h', help='Candle timeframe')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=10000, help='Initial capital')
    parser.add_argument('--leverage', type=float, default=1.0, help='Leverage to use')
    parser.add_argument('--output', default='backtest_results.json', help='Output file')
    
    args = parser.parse_args()
    
    # Create configuration
    config = BacktestConfig(
        strategy_name="EMA_Crossover_RSI",
        exchange=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc),
        end_date=datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc),
        initial_capital=Decimal(str(args.capital)),
        leverage=args.leverage
    )
    
    # Create and run backtester
    backtester = Backtester(config)
    await backtester.initialize()
    results = await backtester.run()
    
    # Save and display results
    backtester.save_results(results, args.output)
    backtester.print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())