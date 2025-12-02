"""
Smart Entry Hunter - Intelligent Entry Point Monitoring

Implements Fire & Forget pattern for finding optimal entry points based on:
- VWAP Bands (Volume Weighted Average Price ± 2 StdDev)
- MFI (Money Flow Index)
- Volume analysis

Scenarios:
1. Momentum Breakout: Price > VWAP Upper + Volume spike + MFI > 50
2. Mean Reversion: Price at VWAP/Lower + MFI > 30 + Reversal pattern
"""
import asyncio
import logging
import os
from typing import Dict, Optional, Set
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# HUNTER REGISTRY - Tracks active monitoring tasks
# ============================================================

@dataclass
class HunterTask:
    """Represents an active Hunter monitoring task"""
    symbol: str
    exchange: str
    direction: str
    task: asyncio.Task
    started_at: datetime
    signal_id: Optional[int] = None
    
    def age_seconds(self) -> float:
        """Get task age in seconds"""
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()


class HunterRegistry:
    """
    Registry for tracking active Hunter tasks
    
    Features:
    - Limit concurrent hunters (MAX_CONCURRENT_HUNTERS)
    - Auto-cleanup completed tasks
    - Statistics tracking
    """
    
    def __init__(self, max_concurrent: int = 30):
        self.max_concurrent = max_concurrent
        self.active_hunters: Dict[str, HunterTask] = {}  # key: f"{exchange}_{symbol}"
        self.completed_count = 0
        self.timeout_count = 0
        self.entered_count = 0
        self.error_count = 0
        self._lock = asyncio.Lock()
    
    async def register(self, hunter_task: HunterTask) -> bool:
        """
        Register new Hunter task
        
        Returns:
            True if registered, False if limit reached
        """
        async with self._lock:
            # Cleanup completed tasks first
            await self._cleanup_completed()
            
            # Check limit
            if len(self.active_hunters) >= self.max_concurrent:
                logger.warning(
                    f"Hunter limit reached ({self.max_concurrent}). "
                    f"Cannot start new hunter for {hunter_task.symbol}"
                )
                return False
            
            key = f"{hunter_task.exchange}_{hunter_task.symbol}"
            
            # Check duplicate
            if key in self.active_hunters:
                logger.warning(f"Hunter already active for {hunter_task.symbol}")
                return False
            
            self.active_hunters[key] = hunter_task
            logger.info(
                f"🎯 Hunter registered: {hunter_task.symbol} "
                f"({len(self.active_hunters)}/{self.max_concurrent})"
            )
            return True
    
    async def unregister(self, exchange: str, symbol: str, result: str):
        """
        Unregister completed Hunter task
        
        Args:
            result: 'entered', 'timeout', 'error', 'cancelled'
        """
        async with self._lock:
            key = f"{exchange}_{symbol}"
            if key in self.active_hunters:
                del self.active_hunters[key]
                
                # Update stats
                if result == 'entered':
                    self.entered_count += 1
                elif result == 'timeout':
                    self.timeout_count += 1
                elif result == 'error':
                    self.error_count += 1
                
                self.completed_count += 1
                
                logger.info(
                    f"🏁 Hunter completed: {symbol} ({result}) "
                    f"- Active: {len(self.active_hunters)}/{self.max_concurrent}"
                )
    
    async def _cleanup_completed(self):
        """Remove completed tasks from registry"""
        to_remove = []
        for key, hunter in self.active_hunters.items():
            if hunter.task.done():
                to_remove.append(key)
        
        for key in to_remove:
            del self.active_hunters[key]
    
    def get_stats(self) -> Dict:
        """Get registry statistics"""
        return {
            'active_hunters': len(self.active_hunters),
            'max_concurrent': self.max_concurrent,
            'completed_total': self.completed_count,
            'entered': self.entered_count,
            'timeout': self.timeout_count,
            'errors': self.error_count
        }
    
    def get_active_symbols(self) -> Set[str]:
        """Get set of symbols currently being monitored"""
        return {hunter.symbol for hunter in self.active_hunters.values()}


# Global registry instance
_hunter_registry: Optional[HunterRegistry] = None


def get_hunter_registry() -> HunterRegistry:
    """Get or create global Hunter registry"""
    global _hunter_registry
    if _hunter_registry is None:
        max_concurrent = int(os.getenv('MAX_CONCURRENT_HUNTERS', '30'))
        _hunter_registry = HunterRegistry(max_concurrent=max_concurrent)
    return _hunter_registry


# ============================================================
# FIRE & FORGET LAUNCHER
# ============================================================

def launch_hunter(signal: Dict, exchange_manager, position_manager=None) -> Optional[asyncio.Task]:
    """
    Launch Smart Entry Hunter task (Fire & Forget)
    
    Args:
        signal: Signal dict with symbol, exchange, direction
        exchange_manager: Exchange manager instance for API calls
        position_manager: Position manager for opening positions (optional for testing)
    
    Returns:
        asyncio.Task if launched, None if limit reached
    """
    symbol = signal.get('symbol')
    exchange = signal.get('exchange', 'binance')
    direction = signal.get('recommended_action') or signal.get('signal_type', 'BUY')
    
    # Create async task
    task = asyncio.create_task(
        monitor_entry_conditions(
            signal=signal,
            exchange_manager=exchange_manager,
            position_manager=position_manager
        )
    )
    
    # Create Hunter task record
    hunter_task = HunterTask(
        symbol=symbol,
        exchange=exchange,
        direction=direction,
        task=task,
        started_at=datetime.now(timezone.utc),
        signal_id=signal.get('id')
    )
    
    # Register with registry
    registry = get_hunter_registry()
    
    # Schedule registration (async operation)
    async def _register():
        success = await registry.register(hunter_task)
        if not success:
            task.cancel()
            logger.error(f"Failed to register hunter for {symbol} - limit reached")
    
    asyncio.create_task(_register())
    
    # Add completion callback
    task.add_done_callback(lambda t: _on_hunter_complete(t, exchange, symbol))
    
    logger.info(f"🎯 Hunter launched for {symbol} ({direction})")
    return task


def _on_hunter_complete(task: asyncio.Task, exchange: str, symbol: str):
    """Callback when Hunter task completes"""
    try:
        result_dict = task.result()
        result = result_dict.get('status', 'error')
        
        # Unregister from registry
        registry = get_hunter_registry()
        asyncio.create_task(registry.unregister(exchange, symbol, result))
        
        logger.info(f"🏁 Hunter completed for {symbol}: {result}")
    except asyncio.CancelledError:
        logger.info(f"Hunter cancelled for {symbol}")
        registry = get_hunter_registry()
        asyncio.create_task(registry.unregister(exchange, symbol, 'cancelled'))
    except Exception as e:
        logger.error(f"Hunter error for {symbol}: {e}", exc_info=True)
        registry = get_hunter_registry()
        asyncio.create_task(registry.unregister(exchange, symbol, 'error'))


# ============================================================
# MAIN HUNTER LOGIC
# ============================================================

async def monitor_entry_conditions(
    signal: Dict,
    exchange_manager,
    position_manager=None
) -> Dict:
    """
    Monitor ideal entry point for up to 30 minutes
    
    Logic:
    1. Loop every 3-5 seconds
    2. Fetch last 50x 1m candles
    3. Calculate VWAP Bands + MFI + Volume
    4. Check scenarios:
       - Momentum Breakout
       - Mean Reversion
    5. If criteria met → open position (if position_manager provided)
    6. Timeout: 30 minutes
    
    Returns:
        Dict with status: 'entered'|'timeout'|'error'
    """
    symbol = signal.get('symbol')
    exchange = signal.get('exchange', 'binance')
    direction = signal.get('recommended_action') or signal.get('signal_type', 'BUY')
    
    start_time = datetime.now(timezone.utc)
    timeout_minutes = int(os.getenv('SMART_ENTRY_TIMEOUT_MINUTES', '30'))
    timeout_duration = timedelta(minutes=timeout_minutes)
    check_interval = int(os.getenv('SMART_ENTRY_CHECK_INTERVAL_SECONDS', '4'))
    
    logger.info(f"🎯 Smart Entry Hunter monitoring {symbol} ({direction}) for {timeout_minutes}min")
    
    # Track initial price
    initial_price = None
    
    try:
        iteration = 0
        while True:
            iteration += 1
            
            # Check timeout
            elapsed = datetime.now(timezone.utc) - start_time
            if elapsed > timeout_duration:
                logger.info(f"⏱️ Hunter timeout for {symbol} ({timeout_minutes} min)")
                return {
                    'status': 'timeout',
                    'symbol': symbol,
                    'iterations': iteration,
                    'initial_price': initial_price
                }
            
            # 1. Fetch 1m candles (last 50)
            candles = await _fetch_candles_safely(
                exchange_manager, symbol, timeframe='1m', limit=50
            )
            if not candles or len(candles) < 30:
                logger.debug(f"Insufficient candles for {symbol}, retrying...")
                await asyncio.sleep(check_interval)
                continue
            
            # 2. Convert to DataFrame
            df = _candles_to_df(candles)
            
            # 3. Calculate indicators
            indicators = _calculate_indicators(df)
            if not indicators:
                logger.debug(f"Indicator calculation failed for {symbol}, retrying...")
                await asyncio.sleep(check_interval)
                continue
            
            # Store initial price on first successful iteration
            if initial_price is None:
                initial_price = indicators['current_price']
                logger.info(
                    f"📍 {symbol} initial price: ${initial_price:.6f} "
                    f"(starting monitoring)"
                )
            
            # 4. Check entry scenarios
            should_enter, reason = _check_entry_criteria(indicators, direction)
            
            if should_enter:
                entry_price = indicators['current_price']
                elapsed_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                logger.info(f"✅ Entry criteria met for {symbol}: {reason}")
                
                # Open position if position_manager provided
                if position_manager:
                    from core.position_manager import PositionRequest
                    from decimal import Decimal
                    
                    request = PositionRequest(
                        signal_id=signal.get('id'),
                        symbol=symbol,
                        exchange=exchange,
                        side=direction,
                        entry_price=Decimal(str(entry_price))
                    )
                    
                    result = await position_manager.open_position(request)
                    
                    if result:
                        logger.info(f"🚀 Position opened for {symbol}")
                        return {
                            'status': 'entered',
                            'symbol': symbol,
                            'reason': reason,
                            'entry_price': entry_price,
                            'initial_price': initial_price,
                            'price_change_pct': ((entry_price - initial_price) / initial_price * 100) if initial_price else 0,
                            'elapsed_seconds': elapsed_seconds,
                            'iterations': iteration
                        }
                    else:
                        # Check if it failed because position already exists
                        logger.warning(f"⚠️ Failed to open position for {symbol} (likely duplicate)")
                        return {
                            'status': 'skipped_duplicate',
                            'symbol': symbol,
                            'reason': 'position_already_exists',
                            'initial_price': initial_price,
                            'iterations': iteration
                        }
                else:
                    # Test mode: just return success
                    return {
                        'status': 'entered',
                        'symbol': symbol,
                        'reason': reason,
                        'entry_price': entry_price,
                        'initial_price': initial_price,
                        'price_change_pct': ((entry_price - initial_price) / initial_price * 100) if initial_price else 0,
                        'elapsed_seconds': elapsed_seconds,
                        'iterations': iteration,
                        'test_mode': True
                    }
            
            # Wait before next check
            await asyncio.sleep(check_interval)
            
    except asyncio.CancelledError:
        logger.info(f"Hunter task cancelled for {symbol}")
        return {'status': 'cancelled', 'symbol': symbol}
    except Exception as e:
        logger.error(f"Hunter error for {symbol}: {e}", exc_info=True)
        return {'status': 'error', 'symbol': symbol, 'error': str(e)}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

async def _fetch_candles_safely(exchange_manager, symbol: str, timeframe: str, limit: int):
    """Fetch candles with error handling"""
    try:
        # Find exchange-specific symbol format
        exchange_symbol = exchange_manager.find_exchange_symbol(symbol) or symbol
        
        candles = await exchange_manager.exchange.fetch_ohlcv(
            exchange_symbol,
            timeframe=timeframe,
            limit=limit
        )
        return candles
    except Exception as e:
        logger.warning(f"Failed to fetch candles for {symbol}: {e}")
        return None


def _candles_to_df(candles) -> pd.DataFrame:
    """Convert CCXT candles to pandas DataFrame with DatetimeIndex"""
    df = pd.DataFrame(
        candles,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    
    # Convert timestamp to datetime and set as index (required for pandas_ta)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    df = df.sort_index()  # Ensure ordered
    
    # Convert to float
    df = df.astype({
        'open': float,
        'high': float,
        'low': float,
        'close': float,
        'volume': float
    })
    return df


def _calculate_indicators(df: pd.DataFrame) -> Optional[Dict]:
    """
    Calculate VWAP Bands, MFI, Volume Average
    
    Uses pandas_ta library for technical indicators
    
    Returns:
        Dict with indicators or None if error
    """
    try:
        import pandas_ta as ta
        
        # VWAP (Volume Weighted Average Price)
        df['vwap'] = ta.vwap(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            volume=df['volume']
        )
        
        # VWAP Bands (VWAP ± 2 * StdDev over 20 periods)
        vwap_rolling = df['vwap'].rolling(window=20)
        vwap_std = vwap_rolling.std()
        df['vwap_upper'] = df['vwap'] + (2 * vwap_std)
        df['vwap_lower'] = df['vwap'] - (2 * vwap_std)
        
        # MFI (Money Flow Index, period 14)
        df['mfi'] = ta.mfi(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            volume=df['volume'],
            length=14
        )
        
        # Volume Average (SMA 20)
        df['volume_avg'] = df['volume'].rolling(window=20).mean()
        
        # Get latest values (handle NaN)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # Check for NaN values
        if pd.isna(latest['vwap']) or pd.isna(latest['mfi']):
            logger.debug("Indicators contain NaN values")
            return None
        
        return {
            'current_price': float(latest['close']),
            'vwap': float(latest['vwap']),
            'vwap_upper': float(latest['vwap_upper']) if not pd.isna(latest['vwap_upper']) else float(latest['vwap']),
            'vwap_lower': float(latest['vwap_lower']) if not pd.isna(latest['vwap_lower']) else float(latest['vwap']),
            'mfi': float(latest['mfi']),
            'volume': float(latest['volume']),
            'volume_avg': float(latest['volume_avg']) if not pd.isna(latest['volume_avg']) else float(latest['volume']),
            'close': float(latest['close']),
            'open': float(latest['open']),
            'prev_high': float(prev['high']),
            'prev_low': float(prev['low'])
        }
        
    except Exception as e:
        logger.error(f"Indicator calculation failed: {e}", exc_info=True)
        return None


def _check_entry_criteria(indicators: Dict, direction: str) -> tuple:
    """
    Check entry scenarios
    
    Returns:
        (should_enter: bool, reason: str)
    """
    price = indicators['current_price']
    vwap = indicators['vwap']
    vwap_upper = indicators['vwap_upper']
    vwap_lower = indicators['vwap_lower']
    mfi = indicators['mfi']
    volume = indicators['volume']
    volume_avg = indicators['volume_avg']
    close = indicators['close']
    open_price = indicators['open']
    prev_high = indicators['prev_high']
    
    # Get thresholds from env
    mfi_momentum_threshold = float(os.getenv('HUNTER_MFI_MOMENTUM_THRESHOLD', '50'))
    mfi_reversion_threshold = float(os.getenv('HUNTER_MFI_REVERSION_THRESHOLD', '30'))
    vwap_tolerance_pct = float(os.getenv('HUNTER_VWAP_TOLERANCE_PERCENT', '0.2'))
    volume_spike_multiplier = float(os.getenv('HUNTER_VOLUME_SPIKE_MULTIPLIER', '2.0'))
    
    if direction == 'BUY':
        # Scenario 1: Momentum Breakout
        if price > vwap_upper:
            if volume > (volume_spike_multiplier * volume_avg):
                if mfi > mfi_momentum_threshold:
                    return (
                        True,
                        f"Momentum Breakout: Price ${price:.4f} > VWAP Upper ${vwap_upper:.4f} "
                        f"+ Volume {volume:.0f} > {volume_spike_multiplier}x avg "
                        f"+ MFI {mfi:.1f} > {mfi_momentum_threshold}"
                    )
        
        # Scenario 2: Mean Reversion
        # Price touched VWAP (±tolerance%) or VWAP Lower Band
        vwap_tolerance = vwap * (vwap_tolerance_pct / 100)
        if abs(price - vwap) <= vwap_tolerance or price <= vwap_lower:
            if mfi > mfi_reversion_threshold:
                # Reversal pattern: Current candle green AND Close > Prev High
                if close > open_price and close > prev_high:
                    return (
                        True,
                        f"Mean Reversion: Price ${price:.4f} at VWAP ${vwap:.4f} "
                        f"+ MFI {mfi:.1f} > {mfi_reversion_threshold} "
                        f"+ Reversal (close > open & close > prev_high)"
                    )
    
    elif direction == 'SELL' or direction == 'SHORT':
        # Scenario 1: Momentum Breakdown (SHORT)
        # Price broke below VWAP Lower Band with volume spike
        if price < vwap_lower:
            if volume > (volume_spike_multiplier * volume_avg):
                # MFI should be low (selling pressure)
                if mfi < (100 - mfi_momentum_threshold):  # e.g., MFI < 50
                    return (
                        True,
                        f"Momentum Breakdown: Price ${price:.4f} < VWAP Lower ${vwap_lower:.4f} "
                        f"+ Volume {volume:.0f} > {volume_spike_multiplier}x avg "
                        f"+ MFI {mfi:.1f} < {100 - mfi_momentum_threshold}"
                    )
        
        # Scenario 2: Mean Reversion SHORT (from resistance)
        # Price touched VWAP (±tolerance%) or VWAP Upper Band
        vwap_tolerance = vwap * (vwap_tolerance_pct / 100)
        if abs(price - vwap) <= vwap_tolerance or price >= vwap_upper:
            # MFI should indicate not overbought (room to fall)
            if mfi < (100 - mfi_reversion_threshold):  # e.g., MFI < 70
                # Reversal pattern: Current candle red AND Close < Prev Low
                prev_low = indicators.get('prev_low', open_price)
                if close < open_price and close < prev_low:
                    return (
                        True,
                        f"Mean Reversion SHORT: Price ${price:.4f} at VWAP ${vwap:.4f} "
                        f"+ MFI {mfi:.1f} < {100 - mfi_reversion_threshold} "
                        f"+ Reversal (close < open & close < prev_low)"
                    )
    
    return (False, "")
