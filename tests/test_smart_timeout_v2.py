"""
Smart Timeout v2.0 Tests

Tests all code paths:
1. Normal TIMEOUT when score < threshold
2. Extension mode entry when score >= threshold
3. TIMEOUT_BREAKEVEN when PnL >= 0 during extension
4. TIMEOUT_FLOOR when PnL hits floor during extension
5. TIMEOUT_WEAK when score drops below threshold during recheck
6. TIMEOUT_HARDCAP when max extensions reached
7. Extension renewal when still strong after 30min
8. Profitable timeout (no extension)
9. Near-liquidation timeout (no extension)
10. Indicator computation (RSI, vol z-score, momentum, extremes)
11. Strength score computation (scoring + veto)
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from core.bar_aggregator import BarAggregator, OneSecondBar
from core.composite_strategy import (
    StrategyParams, DerivedConstants,
    SMART_TIMEOUT_THRESHOLD, SMART_TIMEOUT_EXTENSION_SEC,
    SMART_TIMEOUT_MAX_EXTENSIONS, SMART_TIMEOUT_RECHECK_SEC,
)
from core.signal_lifecycle import (
    SignalLifecycle, SignalLifecycleManager, SignalState,
)
from core.pnl_calculator import calculate_pnl_from_entry


# ==============================================================================
# Helpers
# ==============================================================================

def make_strategy(sl_pct=3.0, leverage=10, max_position_hours=6, delta_window=60):
    return StrategyParams(
        sl_pct=sl_pct,
        leverage=leverage,
        max_position_hours=max_position_hours,
        delta_window=delta_window,
    )


def make_lifecycle(
    entry_price=100.0,
    position_age_sec=21600,   # 6h = timeout
    strategy=None,
    in_extension=False,
    extensions_used=0,
    bar_count=200,
    bar_delta=0.0,            # delta for each bar
):
    """Create a SignalLifecycle with a BarAggregator pre-filled with bars."""
    if strategy is None:
        strategy = make_strategy()
    derived = DerivedConstants.from_params(strategy)

    lc = SignalLifecycle(
        signal_id=1,
        symbol='TESTUSDT',
        exchange='binance',
        strategy=strategy,
        derived=derived,
        state=SignalState.IN_POSITION,
        in_position=True,
        entry_price=entry_price,
        max_price=entry_price,
        trade_count=1,
        signal_start_ts=1000000,
    )

    # Set position timing
    now = int(time.time())
    lc.position_entry_ts = now - position_age_sec

    # Extension mode
    lc.in_extension_mode = in_extension
    lc.timeout_extensions_used = extensions_used
    if in_extension:
        lc.extension_start_ts = now - 60  # Started 60s ago
        lc.last_strength_check_ts = now - 60

    # Create BarAggregator with pre-filled bars
    agg = BarAggregator('TESTUSDT', max_bars=4000)
    base_ts = now - bar_count
    for i in range(bar_count):
        bar = OneSecondBar(
            ts=base_ts + i,
            price=entry_price,  # Flat price by default
            delta=bar_delta,
            large_buy_count=0,
            large_sell_count=0,
        )
        agg.bars.append(bar)
        agg.cumsum_delta.append(agg.cumsum_delta[-1] + bar.delta)
        agg.cumsum_abs_delta.append(agg.cumsum_abs_delta[-1] + abs(bar.delta))

    lc.bar_aggregator = agg
    return lc


def make_bar(price, ts=None, delta=0.0, large_buys=0, large_sells=0):
    """Create a OneSecondBar for testing."""
    return OneSecondBar(
        ts=ts or int(time.time()),
        price=price,
        delta=delta,
        large_buy_count=large_buys,
        large_sell_count=large_sells,
    )


def make_manager():
    """Create a SignalLifecycleManager with mocked dependencies."""
    mgr = SignalLifecycleManager.__new__(SignalLifecycleManager)
    mgr.composite_strategy = MagicMock()
    mgr.position_manager = None
    mgr.repository = None
    mgr.aggtrades_stream = None
    mgr.active = {}
    mgr.total_positions_opened = 0
    mgr.total_positions_closed = 0
    # Mock _close_position to track calls
    mgr._close_position = AsyncMock()
    mgr._cancel_exchange_sl = AsyncMock()
    return mgr


# ==============================================================================
# Test: BarAggregator Indicator Methods
# ==============================================================================

class TestBarAggregatorIndicators:
    """Tests for new indicator computation methods."""

    def test_compute_rsi_no_data(self):
        """RSI returns 50 (neutral) when not enough data."""
        agg = BarAggregator('TEST')
        assert agg.compute_rsi() == 50.0

    def test_compute_rsi_all_gains(self):
        """RSI = 100 when price only went up."""
        agg = BarAggregator('TEST', max_bars=1000)
        for i in range(900):
            bar = OneSecondBar(ts=i, price=100.0 + i * 0.01, delta=0, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(0)
            agg.cumsum_abs_delta.append(0)
        assert agg.compute_rsi() == 100.0

    def test_compute_rsi_all_losses(self):
        """RSI near 0 when price only went down."""
        agg = BarAggregator('TEST', max_bars=1000)
        for i in range(900):
            bar = OneSecondBar(ts=i, price=100.0 - i * 0.01, delta=0, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(0)
            agg.cumsum_abs_delta.append(0)
        rsi = agg.compute_rsi()
        assert rsi < 5.0, f"RSI should be near 0 for all-down, got {rsi}"

    def test_compute_rsi_mixed(self):
        """RSI should be between 0 and 100 for mixed price action."""
        agg = BarAggregator('TEST', max_bars=1000)
        for i in range(900):
            # Oscillating price
            price = 100.0 + (1.0 if i % 3 == 0 else -0.5)
            bar = OneSecondBar(ts=i, price=price, delta=0, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(0)
            agg.cumsum_abs_delta.append(0)
        rsi = agg.compute_rsi()
        assert 10 < rsi < 90, f"RSI should be mid-range, got {rsi}"

    def test_compute_volume_zscore_no_data(self):
        """Returns 0 when not enough data."""
        agg = BarAggregator('TEST')
        assert agg.compute_volume_zscore() == 0.0

    def test_compute_volume_zscore_spike(self):
        """High z-score when recent volume spikes."""
        agg = BarAggregator('TEST', max_bars=4000)
        # Normal volume for most of the hour
        for i in range(3540):
            bar = OneSecondBar(ts=i, price=100, delta=10, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(agg.cumsum_delta[-1] + 10)
            agg.cumsum_abs_delta.append(agg.cumsum_abs_delta[-1] + 10)
        # Spike in last 60 seconds
        for i in range(60):
            bar = OneSecondBar(ts=3540 + i, price=100, delta=100, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(agg.cumsum_delta[-1] + 100)
            agg.cumsum_abs_delta.append(agg.cumsum_abs_delta[-1] + 100)
        zscore = agg.compute_volume_zscore()
        assert zscore > 2.0, f"Z-score should be > 2 for volume spike, got {zscore}"

    def test_compute_pair_momentum_no_data(self):
        """Returns 0 when not enough data."""
        agg = BarAggregator('TEST')
        assert agg.compute_pair_momentum(60) == 0.0

    def test_compute_pair_momentum_pump(self):
        """Positive momentum for price increase."""
        agg = BarAggregator('TEST', max_bars=1000)
        for i in range(200):
            bar = OneSecondBar(ts=i, price=100 + i * 0.1, delta=0, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(0)
            agg.cumsum_abs_delta.append(0)
        momentum = agg.compute_pair_momentum(100)
        assert momentum > 0, f"Momentum should be positive, got {momentum}"

    def test_compute_pair_momentum_dump(self):
        """Negative momentum for price decrease."""
        agg = BarAggregator('TEST', max_bars=1000)
        for i in range(200):
            bar = OneSecondBar(ts=i, price=100 - i * 0.05, delta=0, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(0)
            agg.cumsum_abs_delta.append(0)
        momentum = agg.compute_pair_momentum(100)
        assert momentum < 0, f"Momentum should be negative, got {momentum}"

    def test_compute_extremes_at_low(self):
        """Near-low when price at bottom of range."""
        agg = BarAggregator('TEST', max_bars=4000)
        # Price went from 100 to 110 and back to 101
        for i in range(1000):
            if i < 500:
                price = 100 + i * 0.02  # Up to 110
            else:
                price = 110 - (i - 500) * 0.018  # Down to ~101
            bar = OneSecondBar(ts=i, price=price, delta=0, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(0)
            agg.cumsum_abs_delta.append(0)
        extremes = agg.compute_extremes(1000)
        assert extremes['near_low'], f"Should be near low, position={extremes['position']:.2f}"
        assert not extremes['near_high']

    def test_compute_extremes_at_high(self):
        """Near-high when price at top of range."""
        agg = BarAggregator('TEST', max_bars=4000)
        for i in range(1000):
            price = 100 + i * 0.01  # Steady climb to 110
            bar = OneSecondBar(ts=i, price=price, delta=0, large_buy_count=0, large_sell_count=0)
            agg.bars.append(bar)
            agg.cumsum_delta.append(0)
            agg.cumsum_abs_delta.append(0)
        extremes = agg.compute_extremes(1000)
        assert extremes['near_high']
        assert not extremes['near_low']


# ==============================================================================
# Test: Smart Timeout Decision Logic
# ==============================================================================

class TestSmartTimeoutDecision:
    """Tests for _check_timeout decision branches."""

    @pytest.mark.asyncio
    async def test_not_timed_out_returns_false(self):
        """Position not yet at timeout → returns False, no close."""
        mgr = make_manager()
        lc = make_lifecycle(position_age_sec=3600)  # 1h < 6h timeout
        bar = make_bar(price=100.0, ts=int(time.time()))

        result = await mgr._check_timeout(lc, bar)

        assert result is False
        mgr._close_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_profitable_timeout_closes_immediately(self):
        """Profitable position at timeout → TIMEOUT close, no extension."""
        mgr = make_manager()
        lc = make_lifecycle(entry_price=100.0, position_age_sec=21600)
        bar = make_bar(price=101.0, ts=int(time.time()))  # +1% profit

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        mgr._close_position.assert_called_once()
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT"  # reason
        assert not lc.in_extension_mode

    @pytest.mark.asyncio
    async def test_near_liquidation_closes_immediately(self):
        """Near liquidation at timeout → LIQ+TIMEOUT, no extension."""
        mgr = make_manager()
        strategy = make_strategy(leverage=10)  # liq threshold = 10%
        lc = make_lifecycle(entry_price=100.0, position_age_sec=21600, strategy=strategy)
        bar = make_bar(price=89.0, ts=int(time.time()))  # -11% > -10% threshold

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "LIQ+TIMEOUT"
        assert not lc.in_extension_mode

    @pytest.mark.asyncio
    async def test_deep_loss_closes_at_floor(self):
        """Loss deeper than SL×0.8 → TIMEOUT, no extension."""
        mgr = make_manager()
        strategy = make_strategy(sl_pct=3.0)
        lc = make_lifecycle(entry_price=100.0, position_age_sec=21600, strategy=strategy)
        # pnl_floor = -(3.0 * 0.8) = -2.4%. Need price change ≤ -2.4%
        bar = make_bar(price=97.5, ts=int(time.time()))  # -2.5%

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT"
        assert not lc.in_extension_mode

    @pytest.mark.asyncio
    async def test_recoverable_loss_low_score_closes(self):
        """Recoverable loss but score < threshold → TIMEOUT."""
        mgr = make_manager()
        strategy = make_strategy(sl_pct=3.0)
        lc = make_lifecycle(
            entry_price=100.0,
            position_age_sec=21600,
            strategy=strategy,
            bar_delta=-10.0,  # Negative delta → no +3 points
        )
        bar = make_bar(price=99.5, ts=int(time.time()))  # -0.5% (recoverable)

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT"
        assert not lc.in_extension_mode

    @pytest.mark.asyncio
    async def test_recoverable_loss_high_score_extends(self):
        """Recoverable loss with strong score → enters extension mode."""
        mgr = make_manager()
        strategy = make_strategy(sl_pct=3.0)

        # Need score >= 5. Create bars with:
        # - Positive delta → +3 pts
        # - Large buys > sells → +2 pts
        # Total = 5 ✅
        lc = make_lifecycle(
            entry_price=100.0,
            position_age_sec=21600,
            strategy=strategy,
            bar_delta=50.0,
        )
        # Add large buy counts to recent bars
        for b in list(lc.bar_aggregator.bars)[-60:]:
            b.large_buy_count = 3
            b.large_sell_count = 1

        bar = make_bar(price=99.5, ts=int(time.time()))  # -0.5%

        result = await mgr._check_timeout(lc, bar)

        assert result is False  # NOT closed
        assert lc.in_extension_mode is True
        assert lc.timeout_extensions_used == 1
        mgr._close_position.assert_not_called()


# ==============================================================================
# Test: Extension Mode (per-second monitoring)
# ==============================================================================

class TestExtensionMode:
    """Tests for _check_timeout_extension behavior."""

    @pytest.mark.asyncio
    async def test_breakeven_closes_immediately(self):
        """PnL >= 0 during extension → TIMEOUT_BREAKEVEN."""
        mgr = make_manager()
        lc = make_lifecycle(entry_price=100.0, in_extension=True, extensions_used=1)
        bar = make_bar(price=100.1, ts=int(time.time()))  # PnL > 0

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT_BREAKEVEN"

    @pytest.mark.asyncio
    async def test_exact_breakeven_closes(self):
        """PnL == 0 (exact entry price) → TIMEOUT_BREAKEVEN."""
        mgr = make_manager()
        lc = make_lifecycle(entry_price=100.0, in_extension=True, extensions_used=1)
        bar = make_bar(price=100.0, ts=int(time.time()))

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT_BREAKEVEN"

    @pytest.mark.asyncio
    async def test_floor_hit_closes(self):
        """PnL below floor during extension → TIMEOUT_FLOOR."""
        mgr = make_manager()
        strategy = make_strategy(sl_pct=3.0)  # floor = -2.4%
        lc = make_lifecycle(
            entry_price=100.0,
            in_extension=True,
            extensions_used=1,
            strategy=strategy,
        )
        bar = make_bar(price=97.5, ts=int(time.time()))  # -2.5% < -2.4% floor

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT_FLOOR"

    @pytest.mark.asyncio
    async def test_waiting_continues(self):
        """PnL still negative but not floored, no recheck due → continue waiting."""
        mgr = make_manager()
        now = int(time.time())
        lc = make_lifecycle(
            entry_price=100.0,
            in_extension=True,
            extensions_used=1,
            bar_delta=50.0,
        )
        lc.extension_start_ts = now - 60  # Started 60s ago (< 30min)
        lc.last_strength_check_ts = now - 60  # Checked 60s ago (< 5min)
        bar = make_bar(price=99.8, ts=now)  # -0.2% (still in loss)

        result = await mgr._check_timeout(lc, bar)

        assert result is False  # Continue waiting
        mgr._close_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_strength_recheck_triggers_weak(self):
        """Score drops below threshold on 5min recheck → TIMEOUT_WEAK."""
        mgr = make_manager()
        now = int(time.time())
        lc = make_lifecycle(
            entry_price=100.0,
            in_extension=True,
            extensions_used=1,
            bar_delta=-10.0,  # Negative delta → score = 0
        )
        lc.extension_start_ts = now - 200  # Started 200s ago
        lc.last_strength_check_ts = now - 301  # Last check > 300s ago → triggers recheck
        bar = make_bar(price=99.8, ts=now)

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT_WEAK"

    @pytest.mark.asyncio
    async def test_hardcap_after_max_extensions(self):
        """Max extensions reached + period expired → TIMEOUT_HARDCAP."""
        mgr = make_manager()
        now = int(time.time())
        lc = make_lifecycle(
            entry_price=100.0,
            in_extension=True,
            extensions_used=SMART_TIMEOUT_MAX_EXTENSIONS,  # 3
        )
        lc.extension_start_ts = now - (SMART_TIMEOUT_EXTENSION_SEC + 1)  # Expired
        lc.last_strength_check_ts = now - 10
        bar = make_bar(price=99.8, ts=now)

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT_HARDCAP"

    @pytest.mark.asyncio
    async def test_extension_renewal_with_score(self):
        """Extension expired but score still strong → renew."""
        mgr = make_manager()
        now = int(time.time())
        lc = make_lifecycle(
            entry_price=100.0,
            in_extension=True,
            extensions_used=1,
            bar_delta=50.0,  # Strong positive delta
        )
        # Add large buy counts for +2 score
        for b in list(lc.bar_aggregator.bars)[-60:]:
            b.large_buy_count = 3
            b.large_sell_count = 1

        lc.extension_start_ts = now - (SMART_TIMEOUT_EXTENSION_SEC + 1)  # Expired
        lc.last_strength_check_ts = now - 10
        bar = make_bar(price=99.8, ts=now)

        result = await mgr._check_timeout(lc, bar)

        assert result is False  # Not closed — renewed
        assert lc.timeout_extensions_used == 2  # Incremented
        mgr._close_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_extension_expired_low_score_closes(self):
        """Extension expired and score too low → TIMEOUT_EXTENDED."""
        mgr = make_manager()
        now = int(time.time())
        lc = make_lifecycle(
            entry_price=100.0,
            in_extension=True,
            extensions_used=1,
            bar_delta=-10.0,  # Weak
        )
        lc.extension_start_ts = now - (SMART_TIMEOUT_EXTENSION_SEC + 1)
        lc.last_strength_check_ts = now - 10
        bar = make_bar(price=99.8, ts=now)

        result = await mgr._check_timeout(lc, bar)

        assert result is True
        call_args = mgr._close_position.call_args
        assert call_args[0][1] == "TIMEOUT_EXTENDED"


# ==============================================================================
# Test: Strength Score Computation
# ==============================================================================

class TestStrengthScore:
    """Tests for _compute_strength_score."""

    def test_no_bar_aggregator_returns_zero(self):
        """No BarAggregator → score = 0."""
        mgr = make_manager()
        lc = make_lifecycle()
        lc.bar_aggregator = None
        bar = make_bar(price=100)

        score = mgr._compute_strength_score(lc, bar)
        assert score == 0

    def test_insufficient_bars_returns_zero(self):
        """Less than 100 bars → score = 0."""
        mgr = make_manager()
        lc = make_lifecycle(bar_count=50)
        bar = make_bar(price=100)

        score = mgr._compute_strength_score(lc, bar)
        assert score == 0

    def test_positive_delta_gives_3_points(self):
        """Positive rolling delta → +3."""
        mgr = make_manager()
        lc = make_lifecycle(bar_delta=50.0, bar_count=200)
        bar = make_bar(price=100)

        score = mgr._compute_strength_score(lc, bar)
        assert score >= 3  # At least delta pts

    def test_negative_delta_no_delta_points(self):
        """Negative rolling delta → 0 from delta."""
        mgr = make_manager()
        lc = make_lifecycle(bar_delta=-50.0, bar_count=200)
        bar = make_bar(price=100)

        score = mgr._compute_strength_score(lc, bar)
        assert score < 3  # No delta bonus

    def test_rsi_overbought_veto(self):
        """RSI > 70 → veto → score = 0."""
        mgr = make_manager()
        # Create bars where price only goes up → RSI near 100
        lc = make_lifecycle(bar_count=900, bar_delta=50.0)
        agg = lc.bar_aggregator
        for i, bar in enumerate(agg.bars):
            bar.price = 100 + i * 0.1  # Steady climb
        bar = make_bar(price=100 + 900 * 0.1)

        score = mgr._compute_strength_score(lc, bar)
        assert score == 0, f"Should be vetoed, got score={score}"

    def test_full_score_all_conditions(self):
        """All conditions met → score >= 5."""
        mgr = make_manager()
        lc = make_lifecycle(bar_count=1000, bar_delta=50.0)
        agg = lc.bar_aggregator

        # Make price drop for low RSI + near-low extremes + dump momentum
        for i, bar in enumerate(agg.bars):
            if i < 500:
                bar.price = 100.0
            else:
                bar.price = 100.0 - (i - 500) * 0.01  # Slow drop
            bar.large_buy_count = 2 if i > 940 else 0
            bar.large_sell_count = 1 if i > 940 else 0

        bar = make_bar(price=agg.bars[-1].price)
        score = mgr._compute_strength_score(lc, bar)
        assert score >= 5, f"Expected score >= 5, got {score}"


# ==============================================================================
# Test: State Reset
# ==============================================================================

class TestStateReset:
    """Tests that extension state is properly reset."""

    def test_default_extension_fields(self):
        """New lifecycle has extension fields at defaults."""
        strategy = make_strategy()
        derived = DerivedConstants.from_params(strategy)
        lc = SignalLifecycle(
            signal_id=1, symbol='TEST', exchange='binance',
            strategy=strategy, derived=derived,
        )
        assert lc.in_extension_mode is False
        assert lc.timeout_extensions_used == 0
        assert lc.extension_start_ts == 0
        assert lc.last_strength_check_ts == 0
