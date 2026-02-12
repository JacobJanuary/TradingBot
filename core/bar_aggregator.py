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

# Default large trade threshold (fallback before dynamic calibration)
LARGE_TRADE_THRESHOLD_USD = 10_000

# Dynamic threshold settings
DYNAMIC_THRESHOLD_PERCENTILE = 90   # P90 = top 10% of trades are "large"
DYNAMIC_MIN_SAMPLES = 500           # Min trades before calibration
TRADE_VOLUME_BUFFER_SIZE = 10_000   # Rolling buffer of trade volumes


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

        # Dynamic large trade threshold (per-symbol)
        self.large_trade_threshold: float = LARGE_TRADE_THRESHOLD_USD
        self._trade_volumes: Deque[float] = deque(maxlen=TRADE_VOLUME_BUFFER_SIZE)
        self._threshold_calibrated: bool = False

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

        # Store individual trade volume for dynamic threshold calibration
        self._trade_volumes.append(volume_usd)

        if is_buyer_maker:
            # Buyer is maker → trade initiated by seller → sell volume
            self._current_delta -= volume_usd
            if volume_usd >= self.large_trade_threshold:
                self._current_large_sell += 1
        else:
            # Seller is maker → trade initiated by buyer → buy volume
            self._current_delta += volume_usd
            if volume_usd >= self.large_trade_threshold:
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

    def calibrate_dynamic_threshold(self, percentile: float = DYNAMIC_THRESHOLD_PERCENTILE) -> float:
        """
        Compute and apply a dynamic 'large trade' threshold from recent trade volumes.
        
        Uses the P90 (or specified percentile) of accumulated trade volumes.
        Trades above this threshold are considered "large" for re-entry analysis.
        
        Args:
            percentile: Percentile cutoff (default: 90 = top 10% are "large")
            
        Returns:
            The new threshold value in USD
        """
        n = len(self._trade_volumes)
        if n < DYNAMIC_MIN_SAMPLES:
            logger.info(
                f"📏 {self.symbol}: Not enough trades for calibration "
                f"({n}/{DYNAMIC_MIN_SAMPLES}), keeping threshold=${self.large_trade_threshold:.0f}"
            )
            return self.large_trade_threshold

        sorted_volumes = sorted(self._trade_volumes)
        idx = int(n * percentile / 100)
        idx = min(idx, n - 1)
        new_threshold = sorted_volumes[idx]

        # Ensure minimum threshold of $50 to avoid noise
        new_threshold = max(new_threshold, 50.0)

        old_threshold = self.large_trade_threshold
        self.large_trade_threshold = new_threshold
        self._threshold_calibrated = True

        logger.info(
            f"📏 {self.symbol}: Dynamic threshold calibrated: "
            f"${old_threshold:.0f} → ${new_threshold:.0f} "
            f"(P{percentile:.0f} of {n} trades)"
        )
        return new_threshold

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

    # ==================================================================
    # Smart Timeout v2.0 — Indicator Methods (2026-02-12)
    # ==================================================================

    def compute_rsi(self, period: int = 840) -> float:
        """
        RSI from 1-second bars.

        Default period=840 = 14 minutes (14 × 60 seconds).
        Uses standard Wilder RSI formula.

        Returns:
            RSI value 0-100, or 50.0 (neutral) if insufficient data.
        """
        n = len(self.bars)
        if n < period + 1:
            return 50.0  # Neutral — not enough data

        gains = 0.0
        losses = 0.0
        for i in range(n - period, n):
            change = self.bars[i].price - self.bars[i - 1].price
            if change > 0:
                gains += change
            else:
                losses -= change  # Make positive

        avg_gain = gains / period
        avg_loss = losses / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def compute_volume_zscore(self, window: int = 3600, recent_window: int = 60) -> float:
        """
        Volume Z-score: current minute volume vs rolling hourly average.

        Uses |delta| as volume proxy (buy+sell pressure magnitude).

        Args:
            window: Full lookback for mean/std (default 3600s = 1h)
            recent_window: Recent period to compare (default 60s = 1min)

        Returns:
            Z-score (positive = above average volume). 0.0 if insufficient data.
        """
        n = len(self.bars)
        if n < window:
            return 0.0

        volumes = [abs(self.bars[i].delta) for i in range(n - window, n)]
        recent_avg = sum(volumes[-recent_window:]) / recent_window
        mean = sum(volumes) / len(volumes)

        variance = sum((v - mean) ** 2 for v in volumes) / len(volumes)
        std = variance ** 0.5

        if std == 0:
            return 0.0
        return (recent_avg - mean) / std

    def compute_pair_momentum(self, window_sec: int) -> float:
        """
        Price change percentage over window.

        Args:
            window_sec: Lookback window in seconds

        Returns:
            Price change as percentage (e.g., -2.5 = -2.5% drop). 0.0 if insufficient data.
        """
        n = len(self.bars)
        if n < window_sec or window_sec <= 0:
            return 0.0
        old_price = self.bars[n - window_sec].price
        if old_price <= 0:
            return 0.0
        return ((self.bars[-1].price - old_price) / old_price) * 100.0

    def compute_extremes(self, window_sec: int = 3600) -> dict:
        """
        Position of current price relative to hour high/low.

        Returns:
            dict with:
                'position': 0.0 (at low) to 1.0 (at high)
                'near_low': True if within bottom 15%
                'near_high': True if within top 15%
        """
        n = len(self.bars)
        actual_window = min(window_sec, n)
        if actual_window < 10:
            return {'position': 0.5, 'near_low': False, 'near_high': False}

        prices = [self.bars[n - actual_window + i].price for i in range(actual_window)]
        low = min(prices)
        high = max(prices)
        rng = high - low

        if rng == 0:
            return {'position': 0.5, 'near_low': False, 'near_high': False}

        pos = (self.bars[-1].price - low) / rng
        return {'position': pos, 'near_low': pos < 0.15, 'near_high': pos > 0.85}

