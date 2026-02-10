"""
1-Second Bar Aggregator for Delta Calculations

Aggregates raw aggTrade data into 1-second bars with:
- Close price
- Delta (buy_volume - sell_volume)
- Large trade counts (>$10k)

Maintains cumulative sum arrays for O(1) rolling calculations.

Based on: TRADING_BOT_ALGORITHM_SPEC.md §1.3, §9
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Deque, Callable

logger = logging.getLogger(__name__)

# Large trade threshold in USD
LARGE_TRADE_THRESHOLD_USD = 10_000


@dataclass
class OneSecondBar:
    """Single 1-second aggregated bar (§1.3)"""
    ts: int                 # Unix epoch seconds
    price: float            # Close price for this second
    delta: float            # buy_volume - sell_volume (ALL trades, in USDT)
    large_buy_count: int    # Number of buy trades > $10k
    large_sell_count: int   # Number of sell trades > $10k


class BarAggregator:
    """
    Per-symbol 1-second bar aggregator with cumulative sums.
    
    Aggregates raw trade events into 1s bars and maintains
    cumulative sum arrays for efficient rolling calculations.
    
    Usage:
        agg = BarAggregator("BTCUSDT", max_bars=4000)
        # Feed trades as they arrive:
        agg.on_trade(price=50000, qty=0.1, is_buyer_maker=False)
        # Each second, flush the bar:
        bar = agg.flush_bar()
        # Query rolling metrics:
        rolling_delta = agg.get_rolling_delta(window_sec=3600)
        avg_abs = agg.get_avg_abs_delta(lookback=100)
    """

    def __init__(self, symbol: str, max_bars: int = 4000):
        """
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            max_bars: Max bars to retain (must cover max(delta_window) + 100)
        """
        self.symbol = symbol
        self.max_bars = max_bars

        # Completed bars
        self.bars: Deque[OneSecondBar] = deque(maxlen=max_bars)

        # Cumulative sums for O(1) rolling calculations
        # Index 0 = sum before first bar, index i = sum including bar i-1
        self.cumsum_delta: Deque[float] = deque(maxlen=max_bars + 1)
        self.cumsum_abs_delta: Deque[float] = deque(maxlen=max_bars + 1)

        # Initialize cumsum with zero baseline
        self.cumsum_delta.append(0.0)
        self.cumsum_abs_delta.append(0.0)

        # Current (incomplete) bar accumulator
        self._current_ts: int = 0
        self._current_price: float = 0.0
        self._current_delta: float = 0.0
        self._current_large_buy: int = 0
        self._current_large_sell: int = 0
        self._has_trades: bool = False

        # Callback when new bar is completed
        self.on_bar_callback: Optional[Callable] = None

    def on_trade(self, price: float, qty: float, is_buyer_maker: bool, trade_time_ms: int = 0):
        """
        Process a single aggTrade.
        
        Auto-flushes bar when second boundary is crossed.
        
        Args:
            price: Trade price
            qty: Trade quantity (in base asset)
            is_buyer_maker: True if buyer is maker (= seller-initiated trade)
            trade_time_ms: Trade timestamp in milliseconds (optional, uses wall clock if 0)
        """
        ts_sec = int(trade_time_ms / 1000) if trade_time_ms > 0 else int(time.time())

        # Detect second boundary → flush previous bar
        if self._has_trades and ts_sec != self._current_ts:
            self._flush_current_bar()

        # Start new bar if needed
        if not self._has_trades:
            self._current_ts = ts_sec
            self._has_trades = True

        # Accumulate trade data
        volume_usd = price * qty
        self._current_price = price  # last price = close

        if is_buyer_maker:
            # Buyer is maker → trade initiated by seller → sell volume
            self._current_delta -= volume_usd
            if volume_usd >= LARGE_TRADE_THRESHOLD_USD:
                self._current_large_sell += 1
        else:
            # Seller is maker → trade initiated by buyer → buy volume
            self._current_delta += volume_usd
            if volume_usd >= LARGE_TRADE_THRESHOLD_USD:
                self._current_large_buy += 1

    def flush_bar(self) -> Optional[OneSecondBar]:
        """
        Force-flush the current bar (called externally on timer).
        Returns the completed bar, or None if no trades accumulated.
        """
        if self._has_trades:
            return self._flush_current_bar()
        return None

    def _flush_current_bar(self) -> OneSecondBar:
        """Internal: close current bar, append to buffer, update cumsums."""
        bar = OneSecondBar(
            ts=self._current_ts,
            price=self._current_price,
            delta=self._current_delta,
            large_buy_count=self._current_large_buy,
            large_sell_count=self._current_large_sell,
        )

        self.bars.append(bar)

        # Update cumulative sums
        prev_delta = self.cumsum_delta[-1]
        prev_abs = self.cumsum_abs_delta[-1]
        self.cumsum_delta.append(prev_delta + bar.delta)
        self.cumsum_abs_delta.append(prev_abs + abs(bar.delta))

        # Reset accumulator
        self._current_ts = 0
        self._current_price = 0.0
        self._current_delta = 0.0
        self._current_large_buy = 0
        self._current_large_sell = 0
        self._has_trades = False

        # Notify callback
        if self.on_bar_callback:
            self.on_bar_callback(bar)

        return bar

    def tick(self) -> Optional[OneSecondBar]:
        """
        Called every second by lifecycle timer (§12.3).
        
        If trades arrived, flushes normally.
        If no trades but we have history, creates empty bar 
        with last known price and delta=0.
        
        Returns:
            Completed bar (real or empty), or None if no history exists
        """
        if self._has_trades:
            return self._flush_current_bar()
        elif self.bars:
            # §12.3: Empty bar with last known price
            last = self.bars[-1]
            bar = OneSecondBar(
                ts=int(time.time()),
                price=last.price,
                delta=0.0,
                large_buy_count=0,
                large_sell_count=0,
            )
            self.bars.append(bar)

            # Update cumulative sums (delta=0, abs_delta=0)
            self.cumsum_delta.append(self.cumsum_delta[-1])
            self.cumsum_abs_delta.append(self.cumsum_abs_delta[-1])

            # Notify callback
            if self.on_bar_callback:
                self.on_bar_callback(bar)

            return bar
        return None

    def add_historical_bar(self, bar: OneSecondBar):
        """
        Add a pre-computed historical bar (for lookback initialization).
        
        Called when loading history via REST API before live monitoring.
        """
        self.bars.append(bar)
        prev_delta = self.cumsum_delta[-1]
        prev_abs = self.cumsum_abs_delta[-1]
        self.cumsum_delta.append(prev_delta + bar.delta)
        self.cumsum_abs_delta.append(prev_abs + abs(bar.delta))

    def get_rolling_delta(self, window_sec: int) -> float:
        """
        Sum of delta over last window_sec bars (§9.2).
        
        Uses cumulative sum for O(1) calculation:
        rolling_delta = cumsum[now] - cumsum[now - window]
        
        Args:
            window_sec: Window size in seconds
            
        Returns:
            Rolling delta (positive = buying pressure)
        """
        n = len(self.bars)
        if n == 0:
            return 0.0

        # Clamp window to available data
        effective_window = min(window_sec, n)

        # cumsum has n+1 elements (0..n)
        # bars[n-1] corresponds to cumsum[n]
        return self.cumsum_delta[-1] - self.cumsum_delta[-(effective_window + 1)]

    def get_avg_abs_delta(self, lookback: int = 100) -> float:
        """
        Average |delta| over last lookback bars (§9.3).
        
        Uses cumulative sum for O(1) calculation:
        avg = (cumsum_abs[now] - cumsum_abs[now - lookback]) / lookback
        
        Args:
            lookback: Number of bars to average over
            
        Returns:
            Average absolute delta
        """
        n = len(self.bars)
        if n == 0:
            return 0.0

        effective_lookback = min(lookback, n)
        total = self.cumsum_abs_delta[-1] - self.cumsum_abs_delta[-(effective_lookback + 1)]
        return total / effective_lookback

    def get_latest_bar(self) -> Optional[OneSecondBar]:
        """Get the most recently completed bar."""
        return self.bars[-1] if self.bars else None

    @property
    def bar_count(self) -> int:
        """Number of completed bars in buffer."""
        return len(self.bars)

    @property
    def ready_for_trading(self) -> bool:
        """Whether we have enough data for delta calculations."""
        return len(self.bars) >= 100  # Minimum for avg_abs_delta
