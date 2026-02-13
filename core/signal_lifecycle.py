"""
Signal Lifecycle Manager — Per-Signal State Machine

Implements TRADING_BOT_ALGORITHM_SPEC.md:
- §2: Strategy matching (CompositeStrategy)
- §4: Entry logic (open position with matched params)
- §6: Per-second monitoring (timeout, liquidation, SL, trailing stop)
- §7: Re-entry logic (cooldown, window, drop%, delta confirmation)
- §8: PnL calculation on close

Each signal creates an independent SignalLifecycle with its own BarAggregator.
The on_bar() callback runs the spec's priority-ordered checks every second.

Date: 2026-02-09
"""

import asyncio
import logging
import time
import aiohttp
from datetime import datetime
from core.event_logger import get_event_logger, EventType
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any, Callable, List

from core.composite_strategy import (
    CompositeStrategy, StrategyParams, DerivedConstants,
    SMART_TIMEOUT_THRESHOLD, SMART_TIMEOUT_EXTENSION_SEC,
    SMART_TIMEOUT_MAX_EXTENSIONS, SMART_TIMEOUT_RECHECK_SEC,
    SMART_TIMEOUT_RSI_OVERSOLD, SMART_TIMEOUT_RSI_OVERBOUGHT,
    SMART_TIMEOUT_VOL_ZSCORE_MIN, SMART_TIMEOUT_PAIR_DUMP_PCT,
)
from core.bar_aggregator import BarAggregator, OneSecondBar
from core.pnl_calculator import (
    calculate_pnl_from_entry,
    calculate_drawdown_from_max,
    calculate_realized_pnl,
    get_liquidation_threshold,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# State Machine
# ==============================================================================

class SignalState(Enum):
    """Per-signal lifecycle states (§5)"""
    WAITING_DATA = "waiting_data"       # Loading lookback bars
    IN_POSITION = "in_position"         # Position open, monitoring
    REENTRY_WAIT = "reentry_wait"       # Exited, watching for re-entry
    FINALIZED = "finalized"             # Lifecycle complete


@dataclass
class TradeRecord:
    """Record of a single entry/exit cycle"""
    trade_idx: int
    entry_price: float
    exit_price: float
    entry_ts: int
    exit_ts: int
    reason: str
    pnl_pct: float
    is_reentry: bool = False


@dataclass 
class SignalLifecycle:
    """Complete lifecycle state for one signal (§5)"""
    signal_id: int
    symbol: str
    exchange: str
    strategy: StrategyParams
    derived: DerivedConstants

    # State machine
    state: SignalState = SignalState.WAITING_DATA

    # Signal-level timing
    signal_start_ts: int = 0            # When signal was received

    # Position tracking
    entry_price: float = 0.0
    max_price: float = 0.0              # Highest price since entry (for drawdown)
    position_entry_ts: int = 0          # When current position was opened
    in_position: bool = False
    _closing: bool = False              # Guard: lifecycle-initiated close in progress
    trade_count: int = 0                # Total entries (incl. re-entries)

    # Re-entry tracking
    last_exit_ts: int = 0
    last_exit_price: float = 0.0
    last_exit_reason: str = ""

    # Concurrency guard (H-3: prevents double-processing from concurrent bar tasks)
    _processing: bool = False

    # Trailing stop tracking
    ts_activated: bool = False          # Has trailing stop been activated?

    # Trade history
    trades: list = field(default_factory=list)

    # Per-signal bar aggregator
    bar_aggregator: Optional[BarAggregator] = None

    # Cumulative P&L
    cumulative_pnl: float = 0.0

    # Signal metadata for DB tracking
    total_score: float = 0.0

    # Position ID for DB linkage
    position_id: Optional[int] = None

    # Diagnostic logging throttle
    _last_reentry_log_ts: int = 0

    # Smart Timeout v2.0 — extension mode tracking (2026-02-12)
    in_extension_mode: bool = False
    timeout_extensions_used: int = 0
    extension_start_ts: int = 0
    last_strength_check_ts: int = 0


# ==============================================================================
# Lifecycle Manager
# ==============================================================================

class SignalLifecycleManager:
    """
    Manages all active signal lifecycles.
    
    Integration:
    - Receives signals from signal_processor_websocket.py
    - Uses CompositeStrategy for rule matching
    - Uses BarAggregator for delta calculations
    - Delegates position open/close to position_manager
    - Self-contained monitoring via on_bar() callbacks
    
    Usage:
        manager = SignalLifecycleManager(
            composite_strategy=cs,
            position_manager=pm,
            aggtrades_stream=ats,
        )
        await manager.start()
        # Signal received:
        await manager.on_signal_received(signal_data)
    """

    def __init__(
        self,
        composite_strategy: CompositeStrategy,
        position_manager,                    # PositionManager instance
        aggtrades_stream=None,               # BinanceAggTradesStream instance
        exchange_manager=None,               # For REST lookback loading
        repository=None,                     # For lifecycle persistence (§4.1)
        max_concurrent_signals: int = 10,
        bar_buffer_size: int = 4000,
    ):
        self.composite_strategy = composite_strategy
        self.position_manager = position_manager
        self.aggtrades_stream = aggtrades_stream
        self.exchange_manager = exchange_manager
        self.repository = repository
        self.max_concurrent_signals = max_concurrent_signals
        self.bar_buffer_size = bar_buffer_size

        # Active lifecycles: symbol → SignalLifecycle
        self.active: Dict[str, SignalLifecycle] = {}

        # Stats
        self.total_signals_received = 0
        self.total_signals_matched = 0
        self.total_positions_opened = 0
        self.total_positions_closed = 0

        # Running state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the lifecycle manager."""
        self._running = True
        # §12.3: Start 1s tick timer for empty bar generation
        self._tick_task = asyncio.create_task(self._tick_loop())

        # §4.1: Restore active lifecycles from DB after restart
        restored = await self.restore_from_db()

        logger.info(
            f"✅ SignalLifecycleManager started: "
            f"strategy v{self.composite_strategy.version}, "
            f"max_concurrent={self.max_concurrent_signals}, "
            f"bar_buffer={self.bar_buffer_size}, "
            f"restored={restored}"
        )

    async def stop(self):
        """Stop the lifecycle manager. Active positions remain open."""
        self._running = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        if hasattr(self, '_tick_task') and self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
        logger.info(
            f"SignalLifecycleManager stopped. "
            f"Active lifecycles: {len(self.active)}"
        )

    async def _tick_loop(self):
        """
        §12.3: Periodic 1s tick for all active lifecycles.
        
        Ensures empty bars are generated and timeout checks happen
        even when no trades arrive for a symbol.
        """
        while self._running:
            try:
                await asyncio.sleep(1.0)
                for symbol, lc in list(self.active.items()):
                    if lc.state in (SignalState.IN_POSITION, SignalState.REENTRY_WAIT):
                        if lc.bar_aggregator:
                            lc.bar_aggregator.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tick loop error: {e}", exc_info=True)

    # ========================================================================
    # Signal Entry (§2 + §4)
    # ========================================================================

    async def on_signal_received(self, signal: dict, matched_params: 'StrategyParams' = None) -> bool:
        """
        Process incoming signal: match strategy → open position.
        
        Args:
            signal: Normalized signal dict with keys:
                symbol, total_score, rsi, volume_zscore, oi_delta_pct,
                exchange, signal_id
                
        Returns:
            True if lifecycle created, False if rejected
        """
        self.total_signals_received += 1
        symbol = signal.get('symbol', '')
        score = float(signal.get('total_score', 0))
        rsi = float(signal.get('rsi', 0))
        vol_zscore = float(signal.get('volume_zscore', signal.get('vol_zscore', 0)))
        oi_delta = float(signal.get('oi_delta_pct', signal.get('oi_delta', 0)))
        exchange = signal.get('exchange', 'binance')
        signal_id = signal.get('signal_id', signal.get('id', 0))

        # 1. Check capacity
        if len(self.active) >= self.max_concurrent_signals:
            logger.warning(
                f"Max concurrent signals reached ({self.max_concurrent_signals}), "
                f"rejecting {symbol} score={score}"
            )
            return False

        # 2. Check if already tracking this symbol
        if symbol in self.active:
            lc = self.active[symbol]
            logger.info(
                f"Already tracking {symbol} (state={lc.state.value}), "
                f"skipping duplicate signal"
            )
            return False

        # 3. Check if position already exists via position_manager
        if self.position_manager and await self.position_manager.has_open_position(symbol, exchange):
            logger.info(f"Position already exists for {symbol} on {exchange}, skipping")
            return False

        # 4. Match signal to strategy rule (§2.2: all filters)
        if matched_params is not None:
            params = matched_params
        else:
            params = self.composite_strategy.match_signal(
                score, rsi=rsi, vol_zscore=vol_zscore, oi_delta=oi_delta
            )
        if params is None:
            logger.debug(f"Signal {symbol} score={score} did not match any strategy rule")
            return False

        self.total_signals_matched += 1
        derived = DerivedConstants.from_params(params)

        # 5. Create bar aggregator
        bar_agg = BarAggregator(symbol, max_bars=self.bar_buffer_size)

        # 6. Create lifecycle
        # §5.1: signal_start_ts = signal's entry_time, not current time
        entry_time = signal.get('entry_time', signal.get('timestamp', int(time.time())))
        # FIX: signal_adapter returns 'timestamp' as datetime.datetime — convert to epoch int
        if isinstance(entry_time, datetime):
            entry_time = int(entry_time.timestamp())
        lc = SignalLifecycle(
            signal_id=signal_id or 0,
            symbol=symbol,
            exchange=exchange,
            strategy=params,
            derived=derived,
            state=SignalState.WAITING_DATA,
            signal_start_ts=int(entry_time),
            bar_aggregator=bar_agg,
            total_score=score,
        )

        self.active[symbol] = lc

        # 6b. Open initial position ASAP (before lookback — minimise slippage)
        signal_price = float(signal.get('price', signal.get('current_price', 0)))
        success = await self._open_position(lc, is_reentry=False, signal_price=signal_price)
        if not success:
            logger.error(f"Failed to open initial position for {symbol}, removing lifecycle")
            event_logger = get_event_logger()
            if event_logger:
                asyncio.create_task(event_logger.log_event(
                    EventType.POSITION_CREATION_FAILED,
                    {'symbol': symbol, 'error': 'initial_position_open_failed', 'score': score, 'context': 'lifecycle_init'},
                    symbol=symbol, severity='ERROR'
                ))
            await self._cleanup_lifecycle(lc)
            return False

        # State already set inside _open_position() before DB persist

        # 7. Subscribe to aggTrades for this symbol
        if self.aggtrades_stream:
            await self.aggtrades_stream.subscribe(symbol)
            logger.info(f"Subscribed to aggTrades for {symbol}")

        # 7b. Load historical lookback bars (§1.2, §9.4)
        lookback_count = max(params.delta_window, 100)
        try:
            loaded = await self._load_lookback_bars(lc, lookback_count)
            logger.info(f"Loaded {loaded} lookback bars for {symbol} (requested {lookback_count}s)")
        except Exception as e:
            logger.warning(f"Failed to load lookback for {symbol}: {e}, continuing without history")

        # 8. Set bar callback → our monitoring loop
        bar_agg.on_bar_callback = lambda bar, s=symbol: asyncio.create_task(
            self._on_bar_safe(s, bar)
        )

        logger.info(
            f"🚀 Signal lifecycle created: {symbol} "
            f"rule=[{self.composite_strategy.get_rule_for_score(score).score_range}] "
            f"leverage={params.leverage}x SL={params.sl_pct}% "
            f"TS act={params.base_activation}%/cb={params.base_callback}%"
        )
        return True

    # ========================================================================
    # Per-Second Monitoring Loop (§6)
    # ========================================================================

    async def _on_bar_safe(self, symbol: str, bar: OneSecondBar):
        """Safe wrapper for on_bar — catches exceptions."""
        try:
            await self.on_bar(symbol, bar)
        except Exception as e:
            logger.error(f"Error in on_bar for {symbol}: {e}", exc_info=True)
            event_logger = get_event_logger()
            if event_logger:
                asyncio.create_task(event_logger.log_event(
                    EventType.ERROR_OCCURRED,
                    {'symbol': symbol, 'error': str(e), 'context': 'on_bar'},
                    symbol=symbol, severity='ERROR'
                ))

    async def on_bar(self, symbol: str, bar: OneSecondBar):
        """
        Per-second monitoring callback (§6).
        
        Called by BarAggregator when a new 1s bar completes.
        Priority-ordered checks:
        1. TIMEOUT
        2. LIQUIDATION  
        3. STOP-LOSS
        4. TRAILING STOP (activation + callback + delta momentum)
        5. RE-ENTRY (if not in position)
        """
        lc = self.active.get(symbol)
        if not lc or lc.state == SignalState.FINALIZED:
            return

        # H-3: Skip if another bar is already being processed for this lifecycle
        if lc._processing:
            return

        # H-4: Skip if lifecycle is still loading data
        if lc.state == SignalState.WAITING_DATA:
            return

        lc._processing = True
        try:
            await self._on_bar_inner(lc, symbol, bar)
        finally:
            lc._processing = False

    async def _on_bar_inner(self, lc: SignalLifecycle, symbol: str, bar: OneSecondBar):
        """Inner bar processing logic, guarded by _processing flag."""

        if lc.state == SignalState.IN_POSITION:
            # Update max price
            if bar.price > lc.max_price:
                lc.max_price = bar.price

            # Priority-ordered exit checks (§6)
            # NOTE: _check_stop_loss REMOVED — exchange Algo SL handles SL.
            # NOTE: _check_liquidation REMOVED — exchange auto-liquidates.
            # Both caused race condition: two SELLs → phantom SHORT.
            # Exchange closures arrive via on_position_closed_externally().
            if await self._check_timeout(lc, bar):
                return
            if await self._check_trailing_stop(lc, bar):
                return

        elif lc.state == SignalState.REENTRY_WAIT:
            # §7.1: Track max_price upward during re-entry wait
            # so that drop% is calculated from the actual peak
            if bar.price > lc.max_price:
                lc.max_price = bar.price

            # Check if re-entry window expired FIRST
            if self._is_reentry_expired(lc, bar.ts):
                logger.info(
                    f"⏰ Re-entry window expired for {symbol} "
                    f"({lc.derived.max_reentry_seconds}s from signal_start)"
                )
                await self._finalize_lifecycle(lc, "reentry_window_expired")
                return

            # Check re-entry conditions
            await self._check_reentry(lc, bar)

    # ========================================================================
    # Exit Checks (§6.2–6.6)
    # ========================================================================

    async def _check_timeout(self, lc: SignalLifecycle, bar: OneSecondBar) -> bool:
        """
        Check position timeout (§6.2) with Smart Timeout v2.0.
        
        Original behavior: close if elapsed >= max_position_seconds.
        v2.0 addition: if in loss but recoverable, compute strength score.
        If score >= threshold → enter extension mode with per-second
        breakeven monitoring.
        """
        # ── EXTENSION MODE: per-second PnL monitoring ──
        if lc.in_extension_mode:
            return await self._check_timeout_extension(lc, bar)

        # ── NORMAL: original timeout check ──
        elapsed = bar.ts - lc.position_entry_ts
        if elapsed < lc.derived.max_position_seconds:
            return False

        pnl_from_entry = calculate_pnl_from_entry(lc.entry_price, bar.price)
        liq_threshold = get_liquidation_threshold(lc.strategy.leverage)

        # Safety first: near-liquidation → always close
        if pnl_from_entry <= -liq_threshold:
            reason = "LIQ+TIMEOUT"
            pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
            logger.info(
                f"⏰ TIMEOUT {lc.symbol}: {elapsed}s >= {lc.derived.max_position_seconds}s, "
                f"pnl={pnl:.2f}% reason={reason}"
            )
            await self._close_position(lc, reason, pnl, bar.price)
            return True

        # Profitable → close immediately (lock profit)
        if pnl_from_entry > 0:
            reason = "TIMEOUT"
            pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
            logger.info(
                f"⏰ TIMEOUT {lc.symbol}: {elapsed}s >= {lc.derived.max_position_seconds}s, "
                f"pnl={pnl:.2f}% reason={reason}"
            )
            await self._close_position(lc, reason, pnl, bar.price)
            return True

        # In loss — check if too deep for extension
        pnl_floor = -(lc.strategy.sl_pct * 0.8)
        if pnl_from_entry <= pnl_floor:
            reason = "TIMEOUT"
            pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
            logger.info(
                f"⏰ TIMEOUT {lc.symbol}: {elapsed}s, "
                f"pnl={pnl:.2f}% too deep (floor={pnl_floor:.2f}%), closing"
            )
            await self._close_position(lc, reason, pnl, bar.price)
            return True

        # In loss but recoverable — check market strength
        score = self._compute_strength_score(lc, bar)
        if score >= SMART_TIMEOUT_THRESHOLD:
            # ENTER EXTENSION MODE — monitor PnL every second
            lc.in_extension_mode = True
            lc.timeout_extensions_used = 1
            lc.extension_start_ts = bar.ts
            lc.last_strength_check_ts = bar.ts
            pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, "TIMEOUT")
            logger.info(
                f"⏳ Smart Timeout EXTEND {lc.symbol}: "
                f"score={score}/10 pnl={pnl:.2f}% "
                f"(extension #1, waiting for breakeven)"
            )
            return False  # Don't close — continue monitoring

        # No strength → standard timeout close
        reason = "TIMEOUT"
        pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
        logger.info(
            f"⏰ TIMEOUT {lc.symbol}: {elapsed}s >= {lc.derived.max_position_seconds}s, "
            f"pnl={pnl:.2f}% score={score}/10 (below threshold={SMART_TIMEOUT_THRESHOLD})"
        )
        await self._close_position(lc, reason, pnl, bar.price)
        return True

    async def _check_timeout_extension(self, lc: SignalLifecycle, bar: OneSecondBar) -> bool:
        """
        Smart Timeout v2.0: Per-second monitoring during extension mode.
        
        Priority order:
        1. PnL >= 0%         → TIMEOUT_BREAKEVEN (every second)
        2. PnL <= floor       → TIMEOUT_FLOOR (every second)
        3. Score < threshold  → TIMEOUT_WEAK (every 5min)
        4. Extension expired  → Renew or TIMEOUT_HARDCAP (every 30min)
        """
        pnl_from_entry = calculate_pnl_from_entry(lc.entry_price, bar.price)
        pnl_floor = -(lc.strategy.sl_pct * 0.8)

        # Priority 1: BREAKEVEN — check every second!
        if pnl_from_entry >= 0:
            reason = "TIMEOUT_BREAKEVEN"
            pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
            logger.info(
                f"💰 BREAKEVEN {lc.symbol}: pnl={pnl:.2f}% "
                f"after {lc.timeout_extensions_used} extension(s)"
            )
            await self._close_position(lc, reason, pnl, bar.price)
            return True

        # Priority 2: PnL floor hit
        if pnl_from_entry <= pnl_floor:
            reason = "TIMEOUT_FLOOR"
            pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
            logger.info(
                f"🔴 FLOOR HIT {lc.symbol}: pnl={pnl:.2f}% <= floor={pnl_floor:.2f}%"
            )
            await self._close_position(lc, reason, pnl, bar.price)
            return True

        # Priority 3: Strength recheck (every 5min)
        time_since_check = bar.ts - lc.last_strength_check_ts
        if time_since_check >= SMART_TIMEOUT_RECHECK_SEC:
            score = self._compute_strength_score(lc, bar)
            lc.last_strength_check_ts = bar.ts
            if score < SMART_TIMEOUT_THRESHOLD:
                reason = "TIMEOUT_WEAK"
                pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
                logger.info(
                    f"🟡 STRENGTH LOST {lc.symbol}: score={score}/10 "
                    f"< {SMART_TIMEOUT_THRESHOLD}, pnl={pnl:.2f}%"
                )
                await self._close_position(lc, reason, pnl, bar.price)
                return True
            logger.info(
                f"📊 Strength OK {lc.symbol}: score={score}/10, "
                f"pnl_entry={pnl_from_entry:.3f}%, continuing"
            )

        # Priority 4: Extension period expired (30min)
        ext_elapsed = bar.ts - lc.extension_start_ts
        if ext_elapsed >= SMART_TIMEOUT_EXTENSION_SEC:
            if lc.timeout_extensions_used >= SMART_TIMEOUT_MAX_EXTENSIONS:
                reason = "TIMEOUT_HARDCAP"
                pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
                logger.info(
                    f"🔴 HARD CAP {lc.symbol}: {lc.timeout_extensions_used} extensions used, "
                    f"pnl={pnl:.2f}%"
                )
                await self._close_position(lc, reason, pnl, bar.price)
                return True

            # Try to renew extension
            score = self._compute_strength_score(lc, bar)
            if score >= SMART_TIMEOUT_THRESHOLD:
                lc.timeout_extensions_used += 1
                lc.extension_start_ts = bar.ts
                lc.last_strength_check_ts = bar.ts
                pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, "TIMEOUT")
                logger.info(
                    f"⏳ Extension RENEWED {lc.symbol}: "
                    f"#{lc.timeout_extensions_used}/{SMART_TIMEOUT_MAX_EXTENSIONS} "
                    f"score={score}/10 pnl={pnl:.2f}%"
                )
                return False  # Continue monitoring
            else:
                reason = "TIMEOUT_EXTENDED"
                pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
                logger.info(
                    f"⏰ Extension EXPIRED {lc.symbol}: "
                    f"score={score}/10 < {SMART_TIMEOUT_THRESHOLD}, pnl={pnl:.2f}%"
                )
                await self._close_position(lc, reason, pnl, bar.price)
                return True

        return False  # Continue waiting for breakeven

    def _compute_strength_score(self, lc: SignalLifecycle, bar: OneSecondBar) -> int:
        """
        Smart Timeout v2.0: Compute market strength score for timeout extension.
        
        Score 0-10. Uses ONLY data from BarAggregator (0 API calls).
        
        Scoring:
            +3: Delta > 0 (net buy pressure)
            +2: Large buys >= sells × 1.2 (institutional flow)
            +2: RSI(14min) < 30 (oversold)
            +1: Volume Z-score > 2.0 with delta > 0 (capitulation buy)
            +1: Price near 1h low (< 15th percentile)
            +1: Pair 15min change < -2% (recent dump = reversal potential)
        
        Veto (score → 0):
            - RSI(14min) > 70 (overbought)
        """
        agg = lc.bar_aggregator
        if not agg or agg.bar_count < 100:
            return 0  # Not enough data → default to timeout

        score = 0

        # Tier 1: Instant flow
        rolling_delta = agg.get_rolling_delta(min(lc.strategy.delta_window, 60))
        if rolling_delta > 0:
            score += 3

        # Large trades: use 60s window from bars
        recent_bars = list(agg.bars)[-60:] if agg.bar_count >= 60 else list(agg.bars)
        large_buys = sum(b.large_buy_count for b in recent_bars)
        large_sells = sum(b.large_sell_count for b in recent_bars)
        if large_buys >= large_sells * 1.2 and large_buys > 0:
            score += 2

        # Tier 2: Pair context indicators
        rsi = agg.compute_rsi()

        # Veto: overbought
        if rsi > SMART_TIMEOUT_RSI_OVERBOUGHT:
            logger.info(
                f"🚫 Strength VETO {lc.symbol}: RSI={rsi:.1f} > {SMART_TIMEOUT_RSI_OVERBOUGHT}"
            )
            return 0

        if rsi < SMART_TIMEOUT_RSI_OVERSOLD:
            score += 2

        vol_zscore = agg.compute_volume_zscore()
        if vol_zscore > SMART_TIMEOUT_VOL_ZSCORE_MIN and rolling_delta > 0:
            score += 1

        extremes = agg.compute_extremes()
        if extremes['near_low']:
            score += 1

        momentum_15m = agg.compute_pair_momentum(900)
        if momentum_15m < SMART_TIMEOUT_PAIR_DUMP_PCT:
            score += 1

        logger.info(
            f"📊 Strength {lc.symbol}: score={score}/10 "
            f"[delta={'✅' if rolling_delta > 0 else '❌'}({rolling_delta:.0f}) "
            f"large_trades={large_buys}B/{large_sells}S "
            f"RSI={rsi:.1f} vol_z={vol_zscore:.1f} "
            f"extremes={extremes['position']:.2f} mom15m={momentum_15m:.2f}%]"
        )
        return score

    async def _check_liquidation(self, lc: SignalLifecycle, bar: OneSecondBar) -> bool:
        """
        Check liquidation (§6.4).
        
        Close if: pnl_from_entry <= -(100 / leverage)
        PnL: -100% (no commission — total loss)
        """
        pnl_from_entry = calculate_pnl_from_entry(lc.entry_price, bar.price)
        liq_threshold = get_liquidation_threshold(lc.strategy.leverage)

        if pnl_from_entry > -liq_threshold:
            return False

        logger.warning(
            f"💥 LIQUIDATION {lc.symbol}: pnl_from_entry={pnl_from_entry:.3f}% "
            f"≤ -{liq_threshold:.1f}%"
        )
        await self._close_position(lc, "LIQUIDATED", -100.0, bar.price)
        return True

    async def _check_stop_loss(self, lc: SignalLifecycle, bar: OneSecondBar) -> bool:
        """
        Check stop-loss (§6.3).
        
        Close if: pnl_from_entry <= -sl_pct
        PnL: leveraged, clamped, minus commission
        """
        pnl_from_entry = calculate_pnl_from_entry(lc.entry_price, bar.price)
        
        if pnl_from_entry > -lc.strategy.sl_pct:
            return False

        pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, "SL")

        logger.info(
            f"🛑 STOP-LOSS {lc.symbol}: pnl_from_entry={pnl_from_entry:.3f}% "
            f"≤ -{lc.strategy.sl_pct}%, realized={pnl:.2f}%"
        )
        await self._close_position(lc, "SL", pnl, bar.price)
        return True

    async def _check_trailing_stop(self, lc: SignalLifecycle, bar: OneSecondBar) -> bool:
        """
        Check trailing stop — 3 conditions must ALL be true (§6.5).
        
        Condition A (Activation):
            pnl_from_entry >= base_activation%
            
        Condition B (Callback):
            drawdown_from_max >= base_callback%
            
        Condition C (Delta Momentum — §6.6):
            rolling_delta(delta_window) < avg_abs_delta(100) * threshold_mult
        """
        pnl_from_entry = calculate_pnl_from_entry(lc.entry_price, bar.price)
        
        # Condition A: Activation
        # §6.5: activation is a LATCH — once activated, stays activated
        if not lc.ts_activated:
            if pnl_from_entry < lc.strategy.base_activation:
                return False
            lc.ts_activated = True
            logger.info(
                f"📈 Trailing stop ACTIVATED for {lc.symbol}: "
                f"pnl={pnl_from_entry:.2f}% >= {lc.strategy.base_activation}%"
            )

        # Condition B: Callback (drawdown from peak)
        drawdown = calculate_drawdown_from_max(lc.max_price, bar.price)
        if drawdown < lc.strategy.base_callback:
            if lc.ts_activated:
                logger.debug(
                    f"TS {lc.symbol}: drawdown={drawdown:.2f}% < {lc.strategy.base_callback}% "
                    f"(pnl={pnl_from_entry:.2f}%, peak={lc.max_price})"
                )
            return False

        # Condition C: Delta momentum filter (§6.6, threshold_mult reactivated 2026-02-13)
        # EXIT only when selling pressure exceeds normal noise by threshold_mult
        # threshold = avg_abs_delta(100) × threshold_mult
        # EXIT when rolling_delta < -threshold (significant selling)
        if lc.bar_aggregator:
            rolling_delta = lc.bar_aggregator.get_rolling_delta(lc.strategy.delta_window)
            avg_abs = lc.bar_aggregator.get_avg_abs_delta(100)
            threshold = avg_abs * lc.strategy.threshold_mult

            if rolling_delta > -threshold:
                logger.info(
                    f"⏳ TS HELD {lc.symbol}: B✅ drawdown={drawdown:.2f}%, "
                    f"C❌ delta={rolling_delta:.0f} > -{threshold:.0f} "
                    f"(need selling > {threshold:.0f}, avg={avg_abs:.0f}×{lc.strategy.threshold_mult})"
                )
                return False

            # rolling_delta < -threshold → significant selling pressure confirmed
            logger.info(
                f"📊 Delta filter PASSED for {lc.symbol}: "
                f"delta={rolling_delta:.0f} < -{threshold:.0f} "
                f"(avg={avg_abs:.0f}×{lc.strategy.threshold_mult})"
            )

        # All 3 conditions met → trigger trailing stop
        pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, "TRAILING")
        logger.info(
            f"🎯 TRAILING STOP {lc.symbol}: "
            f"pnl_entry={pnl_from_entry:.2f}%, drawdown={drawdown:.2f}%, "
            f"realized={pnl:.2f}%"
        )
        await self._close_position(lc, "TRAILING", pnl, bar.price)
        return True

    # ========================================================================
    # Re-entry Logic (§7)
    # ========================================================================

    async def _check_reentry(self, lc: SignalLifecycle, bar: OneSecondBar) -> bool:
        """
        Check re-entry conditions (§7.1) — strictly per spec.
        
        4 conditions must ALL be true:
        1. Cooldown: elapsed since exit >= base_cooldown
        2. Drop: price dropped base_reentry_drop% from max_price
        3. Delta: current bar delta > 0  (§7.1)
        4. Large trades: rolling 60s large_buy_count > large_sell_count (§7.1)
        
        Large trade threshold is dynamically calibrated per-symbol using
        P90 of accumulated trade volumes (calibrated once after cooldown).
        Condition 4 uses 60s rolling window to capture institutional order flow.
        """
        elapsed_since_exit = bar.ts - lc.last_exit_ts

        # Calibrate dynamic large trade threshold once after cooldown passes
        if (lc.bar_aggregator and
            not lc.bar_aggregator._threshold_calibrated and
            elapsed_since_exit >= lc.strategy.base_cooldown):
            lc.bar_aggregator.calibrate_dynamic_threshold()

        # Calculate all conditions for diagnostic logging
        cooldown_ok = elapsed_since_exit >= lc.strategy.base_cooldown
        drop_pct = (lc.max_price - bar.price) / lc.max_price * 100 if lc.max_price > 0 else 0
        drop_ok = lc.max_price > 0 and drop_pct >= lc.strategy.base_reentry_drop
        # Condition 3: Rolling delta momentum (threshold_mult reactivated 2026-02-13)
        # Reentry requires sustained buying pressure over delta_window
        # exceeding avg noise × threshold_mult
        if lc.bar_aggregator and lc.bar_aggregator.bar_count >= 100:
            rolling_delta = lc.bar_aggregator.get_rolling_delta(lc.strategy.delta_window)
            avg_abs = lc.bar_aggregator.get_avg_abs_delta(100)
            delta_threshold = avg_abs * lc.strategy.threshold_mult
            delta_ok = rolling_delta > delta_threshold
        else:
            delta_ok = bar.delta > 0  # fallback when not enough data

        # Condition 4: 60s rolling window for large trades
        LARGE_TRADE_WINDOW = 60  # seconds
        rolling_buys = 0
        rolling_sells = 0
        if lc.bar_aggregator and lc.bar_aggregator.bars:
            recent_bars = list(lc.bar_aggregator.bars)[-LARGE_TRADE_WINDOW:]
            rolling_buys = sum(b.large_buy_count for b in recent_bars)
            rolling_sells = sum(b.large_sell_count for b in recent_bars)
        large_ok = rolling_buys >= 3 and rolling_buys >= rolling_sells * 1.5

        # Remaining window time
        window_remaining = (lc.signal_start_ts + lc.derived.max_reentry_seconds) - bar.ts

        # Current threshold for diagnostics
        threshold = lc.bar_aggregator.large_trade_threshold if lc.bar_aggregator else 10000

        # Periodic diagnostic log (every 60s)
        if bar.ts - lc._last_reentry_log_ts >= 60:
            lc._last_reentry_log_ts = bar.ts
            # Get rolling delta info for diagnostic log
            r_delta = lc.bar_aggregator.get_rolling_delta(lc.strategy.delta_window) if lc.bar_aggregator and lc.bar_aggregator.bar_count >= 100 else bar.delta
            r_avg = lc.bar_aggregator.get_avg_abs_delta(100) if lc.bar_aggregator and lc.bar_aggregator.bar_count >= 100 else 0
            r_thr = r_avg * lc.strategy.threshold_mult
            logger.info(
                f"📊 REENTRY CHECK {lc.symbol}: "
                f"cooldown={elapsed_since_exit}/{lc.strategy.base_cooldown}s {'✅' if cooldown_ok else '❌'}, "
                f"drop={drop_pct:.1f}/{lc.strategy.base_reentry_drop}% {'✅' if drop_ok else '❌'}, "
                f"delta={r_delta:.0f}/thr={r_thr:.0f}(avg={r_avg:.0f}×{lc.strategy.threshold_mult}) {'✅' if delta_ok else '❌'}, "
                f"large_buys={rolling_buys}/sells={rolling_sells}(60s) {'✅' if large_ok else '❌'}, "
                f"threshold=${threshold:.0f}, "
                f"window_remaining={window_remaining}s ({window_remaining//3600}h{(window_remaining%3600)//60}m)"
            )

        # 1. Cooldown check
        if not cooldown_ok:
            return False

        # 2. Drop check — price must have dropped from MAX_PRICE (§7.1)
        if not drop_ok:
            return False

        # 3. Delta momentum — rolling delta must exceed avg×threshold_mult (§7.1)
        if not delta_ok:
            return False

        # 4. Large trades — 60s rolling window
        if not large_ok:
            return False

        # All conditions met → re-enter
        # Get delta values for success log
        re_delta = lc.bar_aggregator.get_rolling_delta(lc.strategy.delta_window) if lc.bar_aggregator and lc.bar_aggregator.bar_count >= 100 else bar.delta
        re_avg = lc.bar_aggregator.get_avg_abs_delta(100) if lc.bar_aggregator and lc.bar_aggregator.bar_count >= 100 else 0
        re_thr = re_avg * lc.strategy.threshold_mult
        logger.info(
            f"🔄 RE-ENTRY triggered for {lc.symbol}: "
            f"cooldown={elapsed_since_exit}s, "
            f"drop={drop_pct:.2f}% >= {lc.strategy.base_reentry_drop}%, "
            f"rolling_delta={re_delta:.0f} > thr={re_thr:.0f}, "
            f"large_buys={rolling_buys}/sells={rolling_sells}(60s), "
            f"threshold=${threshold:.0f}"
        )

        success = await self._open_position(lc, is_reentry=True)
        if success:
            # State already set inside _open_position() before DB persist
            lc.last_exit_ts = 0  # §10: reset on re-entry
            return True
        return False

    def _is_reentry_expired(self, lc: SignalLifecycle, current_ts: int) -> bool:
        """Check if re-entry window has expired (§7.1).
        
        Window is measured from signal_start_ts (first entry),
        NOT from last_exit_ts.
        """
        elapsed = current_ts - lc.signal_start_ts
        return elapsed >= lc.derived.max_reentry_seconds

    async def _load_lookback_bars(self, lc: SignalLifecycle, lookback_sec: int) -> int:
        """
        Load historical 1s bars via Binance REST aggTrades API (§1.2, §9.4).
        
        Fetches recent trades and aggregates into 1-second bars for
        accurate delta calculations from the first monitoring tick.
        
        Args:
            lc: SignalLifecycle with bar_aggregator to populate
            lookback_sec: How many seconds of history to load
            
        Returns:
            Number of bars loaded
        """
        if not lc.bar_aggregator:
            return 0

        symbol = lc.symbol.upper()
        
        # Binance Futures aggTrades REST endpoint
        base_url = "https://fapi.binance.com"
        url = f"{base_url}/fapi/v1/aggTrades"
        
        end_time = int(time.time() * 1000)
        # Limit lookback to 1 hour max to avoid excessive API calls
        effective_lookback = min(lookback_sec, 3600)
        start_time = end_time - (effective_lookback * 1000)
        
        all_trades = []
        current_start = start_time
        max_pages = 20  # FIX C3-1: 20 × 1000 trades (covers active symbols)
        
        try:
            async with aiohttp.ClientSession() as session:
                for page in range(max_pages):
                    params = {
                        'symbol': symbol,
                        'startTime': current_start,
                        'endTime': end_time,
                        'limit': 1000,
                    }
                    
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            logger.warning(f"Lookback API error {resp.status} for {symbol}")
                            break
                        
                        trades = await resp.json()
                        
                    if not trades:
                        break
                    
                    all_trades.extend(trades)
                    
                    # Paginate: next page starts after last trade
                    last_trade_time = trades[-1].get('T', 0)
                    current_start = last_trade_time + 1
                    
                    if current_start >= end_time or len(trades) < 1000:
                        break
                    
                    await asyncio.sleep(0.1)  # Rate limiting
                    
        except Exception as e:
            logger.warning(f"Lookback fetch error for {symbol}: {e}")
            
        if not all_trades:
            return 0
        
        # Aggregate trades into 1-second bars
        # FIX B2-1: Use dynamic threshold from aggregator instead of hardcoded $10K
        large_threshold = lc.bar_aggregator.large_trade_threshold if lc.bar_aggregator else 10_000
        bars_by_second: Dict[int, dict] = {}
        
        for trade in all_trades:
            ts_sec = int(trade.get('T', 0) / 1000)
            price = float(trade.get('p', 0))
            qty = float(trade.get('q', 0))
            is_buyer_maker = trade.get('m', False)
            volume_usd = price * qty
            
            if ts_sec not in bars_by_second:
                bars_by_second[ts_sec] = {
                    'price': price,
                    'delta': 0.0,
                    'large_buy': 0,
                    'large_sell': 0,
                }
            
            bar_data = bars_by_second[ts_sec]
            bar_data['price'] = price  # Last price = close
            
            if is_buyer_maker:
                bar_data['delta'] -= volume_usd
                if volume_usd >= large_threshold:
                    bar_data['large_sell'] += 1
            else:
                bar_data['delta'] += volume_usd
                if volume_usd >= large_threshold:
                    bar_data['large_buy'] += 1
        
        # Sort by timestamp and add to aggregator
        sorted_seconds = sorted(bars_by_second.keys())
        for ts_sec in sorted_seconds:
            bar_data = bars_by_second[ts_sec]
            bar = OneSecondBar(
                ts=ts_sec,
                price=bar_data['price'],
                delta=bar_data['delta'],
                large_buy_count=bar_data['large_buy'],
                large_sell_count=bar_data['large_sell'],
            )
            lc.bar_aggregator.add_historical_bar(bar)
        
        return len(sorted_seconds)

    # ========================================================================
    # Position Open / Close (§4, §8)
    # ========================================================================

    async def _open_position(self, lc: SignalLifecycle, is_reentry: bool = False, signal_price: float = 0.0) -> bool:
        """
        Open position via position_manager (§4).
        
        Always LONG (per spec decision).
        Sets leverage and SL from strategy params.
        
        Args:
            lc: Signal lifecycle
            is_reentry: True if this is a re-entry trade
            signal_price: Fallback price from signal if bar aggregator is empty
        """
        if not self.position_manager:
            logger.error(f"No position_manager set, cannot open position for {lc.symbol}")
            return False

        try:
            from core.position_manager import PositionRequest
            from decimal import Decimal

            # Get current price (prefer bar aggregator, fallback to signal_price, then exchange ticker)
            current_price = 0.0
            if lc.bar_aggregator and lc.bar_aggregator.bar_count > 0:
                current_price = lc.bar_aggregator.get_latest_bar().price
            
            if current_price <= 0:
                current_price = signal_price
            
            # FIX: fallback to exchange ticker if signal has no price (mirrors legacy pipeline)
            if current_price <= 0 and self.position_manager:
                try:
                    exchange_mgr = self.position_manager.exchanges.get(lc.exchange)
                    if exchange_mgr:
                        ticker = await exchange_mgr.fetch_ticker(lc.symbol)
                        fetched = ticker.get('last') or ticker.get('close')
                        if fetched and float(fetched) > 0:
                            current_price = float(fetched)
                            logger.info(f"Fetched market price for {lc.symbol}: {current_price}")
                        else:
                            logger.warning(f"fetch_ticker returned no valid price for {lc.symbol}: {ticker}")
                    else:
                        logger.warning(f"Exchange '{lc.exchange}' not in position_manager.exchanges")
                except Exception as e:
                    logger.warning(f"Error fetching market price for {lc.symbol}: {e}")

            if current_price <= 0:
                logger.error(f"No valid price for {lc.symbol}, cannot open position")
                return False

            request = PositionRequest(
                signal_id=lc.signal_id,
                symbol=lc.symbol,
                exchange=lc.exchange,
                side='BUY',  # Always LONG per spec
                entry_price=Decimal(str(current_price)),
                lifecycle_managed=True,  # §6.6: lifecycle manages TS, skip legacy
            )

            # Store strategy params for position_manager to use
            # These override the global config values
            request.strategy_params = {
                'leverage': lc.strategy.leverage,
                'stop_loss_percent': lc.strategy.sl_pct,
                'trailing_activation_percent': lc.strategy.base_activation,
                'trailing_callback_percent': lc.strategy.base_callback,
                'total_score': lc.total_score,
            }

            result = await self.position_manager.open_position(request)

            if result and not isinstance(result, dict):
                # PositionState returned = success
                lc.entry_price = float(result.entry_price)
                lc.max_price = lc.entry_price
                lc.position_entry_ts = int(time.time())
                lc.state = SignalState.IN_POSITION  # FIX: set BEFORE persist (was after)
                lc.in_position = True
                lc.trade_count += 1
                lc.ts_activated = False
                # Reset Smart Timeout v2.0 extension state
                lc.in_extension_mode = False
                lc.timeout_extensions_used = 0
                lc.extension_start_ts = 0
                lc.last_strength_check_ts = 0
                lc.position_id = int(result.id) if result.id and str(result.id) != 'pending' else None

                prefix = "RE-ENTRY" if is_reentry else "ENTRY"
                logger.info(
                    f"✅ {prefix} {lc.symbol}: price={lc.entry_price}, "
                    f"leverage={lc.strategy.leverage}x, "
                    f"SL={lc.strategy.sl_pct}%, "
                    f"trade #{lc.trade_count}"
                )
                self.total_positions_opened += 1

                # Persist state to DB (§4.1)
                await self._persist_lifecycle(lc)

                return True
            else:
                error_msg = result.get('error', 'unknown') if isinstance(result, dict) else 'null_result'
                logger.warning(f"Position open failed for {lc.symbol}: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Exception opening position for {lc.symbol}: {e}", exc_info=True)
            event_logger = get_event_logger()
            if event_logger:
                asyncio.create_task(event_logger.log_event(
                    EventType.POSITION_CREATION_FAILED,
                    {'symbol': lc.symbol, 'error': str(e), 'context': 'open_position', 'is_reentry': 'unknown'},
                    symbol=lc.symbol, severity='ERROR'
                ))
            return False

    async def _cancel_exchange_sl(self, lc: SignalLifecycle):
        """
        Cancel exchange Algo SL order before lifecycle-initiated market close.
        
        CRITICAL: Without this, both lifecycle SL and exchange Algo SL can fire
        within 1s, and the second SELL opens a phantom SHORT position.
        """
        try:
            exchange_name = lc.exchange or 'binance'
            exchange = self.position_manager.exchanges.get(exchange_name)
            if not exchange:
                logger.warning(f"No exchange found for {lc.symbol}, skipping SL cancel")
                return

            ex = exchange.exchange  # CCXT instance
            binance_symbol = lc.symbol.replace('/', '').replace(':USDT', '')

            # Step 1: Cancel regular STOP_MARKET orders via fetch_open_orders
            try:
                orders = await ex.fetch_open_orders(lc.symbol)
                expected_side = 'sell'  # We're long, SL is sell
                for order in orders:
                    order_type = order.get('type', '').upper()
                    order_side = order.get('side', '').lower()
                    reduce_only = order.get('reduceOnly', False)
                    if (order_type == 'STOP_MARKET' and
                        order_side == expected_side and
                        reduce_only):
                        try:
                            await ex.cancel_order(order['id'], lc.symbol)
                            logger.info(f"✅ Cancelled SL order {order['id'][:8]}... for {lc.symbol}")
                        except Exception as e:
                            logger.warning(f"Failed to cancel SL order {order['id']}: {e}")
            except Exception as e:
                logger.warning(f"Failed to fetch open orders for {lc.symbol}: {e}")

            # Step 2: Cancel Algo orders via Algo API
            # (This is the CRITICAL path — Algo SL orders are NOT visible in regular orders)
            try:
                algo_res = await ex.fapiPrivateGetOpenAlgoOrders({
                    'symbol': binance_symbol,
                    'algo_type': 'STOP_MARKET'
                })

                algo_orders = []
                if isinstance(algo_res, dict) and 'orders' in algo_res:
                    algo_orders = algo_res['orders']
                elif isinstance(algo_res, list):
                    algo_orders = algo_res

                for ao in algo_orders:
                    algo_id = ao.get('algoId')
                    try:
                        await ex.fapiPrivateDeleteAlgoOrder({
                            'symbol': binance_symbol,
                            'algoId': algo_id
                        })
                        logger.info(f"✅ Cancelled Algo SL for {lc.symbol}: algoId={algo_id}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel Algo SL {algo_id} for {lc.symbol}: {e}")

                if algo_orders:
                    logger.info(f"🗑️ Cancelled {len(algo_orders)} Algo SL order(s) for {lc.symbol}")

            except Exception as e:
                logger.warning(f"⚠️ Failed to check/cancel Algo Orders for {lc.symbol}: {e}")

        except Exception as e:
            logger.error(f"Error cancelling exchange SL for {lc.symbol}: {e}")
            # Don't raise — we still want to try closing the position

    async def _close_position(
        self,
        lc: SignalLifecycle,
        reason: str,
        pnl: float,
        exit_price: float,
    ):
        """
        Close position and update lifecycle state (§8).
        
        After close:
        - If re-entry is possible → REENTRY_WAIT
        - If re-entry window expired or trade_count too high → FINALIZED
        """
        # Record trade
        trade = TradeRecord(
            trade_idx=lc.trade_count,
            entry_price=lc.entry_price,
            exit_price=exit_price,
            entry_ts=lc.position_entry_ts,
            exit_ts=int(time.time()),
            reason=reason,
            pnl_pct=pnl,
            is_reentry=lc.trade_count > 1,
        )
        lc.trades.append(trade)
        lc.cumulative_pnl += pnl

        logger.info(
            f"📊 CLOSED {lc.symbol}: reason={reason}, pnl={pnl:.2f}%, "
            f"cumulative={lc.cumulative_pnl:.2f}%, trade #{lc.trade_count}"
        )

        # Close via position_manager
        if self.position_manager:
            try:
                # CRITICAL: Cancel exchange Algo SL BEFORE market close to prevent
                # race condition (both lifecycle SL and exchange SL firing → phantom SHORT)
                await self._cancel_exchange_sl(lc)

                # Guard: prevent WS closure from double-processing during await
                lc._closing = True

                # §8: Don't pass realized_pnl — PM calculates from entry/exit prices in USD
                # Our pnl is leveraged %, PM expects USD — let PM do the math
                await self.position_manager.close_position(
                    symbol=lc.symbol,
                    reason=f"lifecycle_{reason.lower()}",
                    close_price=exit_price,
                )
            except Exception as e:
                logger.error(f"Error closing position for {lc.symbol}: {e}")
                event_logger = get_event_logger()
                lc._closing = False  # Reset on error so external close can proceed
                if event_logger:
                    asyncio.create_task(event_logger.log_event(
                        EventType.POSITION_ERROR,
                        {'symbol': lc.symbol, 'error': str(e), 'context': 'close_position', 'reason': reason},
                        symbol=lc.symbol, severity='ERROR'
                    ))

        # Update lifecycle state
        lc.in_position = False
        lc.last_exit_ts = int(time.time())
        lc.last_exit_price = exit_price
        lc.last_exit_reason = reason

        # §10: max_price reset ONLY on TRAILING exit for re-entry drop% tracking
        # On SL exit, max_price stays at peak — spec doesn't reset it
        if reason == "TRAILING":
            lc.max_price = exit_price

        self.total_positions_closed += 1

        # Decide next state (§6.7)
        # Don't re-enter after liquidation — finalize immediately
        # TIMEOUT allows re-entry (user decision 2026-02-10)
        if reason in ("LIQUIDATED", "LIQ+TIMEOUT"):
            await self._finalize_lifecycle(lc, f"closed_{reason.lower()}")
        elif self._is_reentry_expired(lc, int(time.time())):
            await self._finalize_lifecycle(lc, "reentry_window_expired")
        else:
            lc.state = SignalState.REENTRY_WAIT
            logger.info(
                f"🔄 {lc.symbol} → REENTRY_WAIT: "
                f"cooldown={lc.strategy.base_cooldown}s, "
                f"drop_needed={lc.strategy.base_reentry_drop}%, "
                f"window={lc.derived.max_reentry_seconds}s"
            )
            # Persist state to DB (§4.1)
            await self._persist_lifecycle(lc)

    async def on_position_closed_externally(self, symbol: str, exit_price: float, reason: str = "EXCHANGE_SL"):
        """
        Handle position closed externally (exchange SL trigger, manual close, etc.)
        
        Called by PositionManager when it detects a WebSocket closure for a symbol
        that has an active lifecycle. This prevents the lifecycle from trying to
        close an already-closed position on its next on_bar tick.
        
        Args:
            symbol: Symbol that was closed (e.g. "ACEUSDT")
            exit_price: Actual fill price from the exchange
            reason: Closure reason (default: "EXCHANGE_SL")
        """
        lc = self.active.get(symbol)
        if not lc:
            return

        # Guard: lifecycle-initiated close is already in progress
        # (e.g. TIMEOUT sent SELL → WS ACCOUNT_UPDATE arrived during await)
        if lc._closing:
            logger.info(
                f"ℹ️ Skipping external close for {symbol}: "
                f"lifecycle close already in progress"
            )
            return
        
        if lc.state != SignalState.IN_POSITION:
            # If in REENTRY_WAIT and another close arrives (e.g. phantom SHORT
            # closed manually, or duplicate exchange event), reset cooldown
            # so we don't immediately re-enter
            if lc.state == SignalState.REENTRY_WAIT:
                lc.last_exit_ts = int(time.time())
                logger.info(
                    f"🔄 External close for {symbol} in REENTRY_WAIT — "
                    f"cooldown reset to {lc.strategy.base_cooldown}s"
                )
                await self._persist_lifecycle(lc)
            else:
                logger.info(f"ℹ️ External close for {symbol} but state={lc.state.value}, ignoring")
            return
        
        # Calculate PnL using the actual fill price
        pnl_from_entry = calculate_pnl_from_entry(lc.entry_price, exit_price)
        pnl = calculate_realized_pnl(pnl_from_entry, lc.strategy.leverage, reason)
        
        logger.info(
            f"🔔 EXTERNAL CLOSE {lc.symbol}: reason={reason}, "
            f"fill_price={exit_price}, pnl_from_entry={pnl_from_entry:.3f}%, "
            f"realized={pnl:.2f}%"
        )
        
        # Record trade (same as _close_position but skip PM.close_position call)
        trade = TradeRecord(
            trade_idx=lc.trade_count,
            entry_price=lc.entry_price,
            exit_price=exit_price,
            entry_ts=lc.position_entry_ts,
            exit_ts=int(time.time()),
            reason=reason,
            pnl_pct=pnl,
            is_reentry=lc.trade_count > 1,
        )
        lc.trades.append(trade)
        lc.cumulative_pnl += pnl

        logger.info(
            f"📊 CLOSED {lc.symbol}: reason={reason}, pnl={pnl:.2f}%, "
            f"cumulative={lc.cumulative_pnl:.2f}%, trade #{lc.trade_count}"
        )

        # Update lifecycle state (skip PM.close_position — already closed!)
        lc.in_position = False
        lc.last_exit_ts = int(time.time())
        lc.last_exit_price = exit_price
        lc.last_exit_reason = reason

        if reason == "TRAILING":
            lc.max_price = exit_price

        self.total_positions_closed += 1

        # Decide next state (§6.7)
        if reason in ("LIQUIDATED", "LIQ+TIMEOUT"):
            await self._finalize_lifecycle(lc, f"closed_{reason.lower()}")
        elif self._is_reentry_expired(lc, int(time.time())):
            await self._finalize_lifecycle(lc, "reentry_window_expired")
        else:
            lc.state = SignalState.REENTRY_WAIT
            logger.info(
                f"🔄 {lc.symbol} → REENTRY_WAIT: "
                f"cooldown={lc.strategy.base_cooldown}s, "
                f"drop_needed={lc.strategy.base_reentry_drop}%, "
                f"window={lc.derived.max_reentry_seconds}s"
            )
            await self._persist_lifecycle(lc)

    # ========================================================================
    # Lifecycle Cleanup
    # ========================================================================

    async def _finalize_lifecycle(self, lc: SignalLifecycle, reason: str):
        """Finalize and clean up a signal lifecycle."""
        lc.state = SignalState.FINALIZED

        # SAFETY NET: If position is still open on exchange, close it before cleanup
        # This handles edge cases like state desynchronization after bot restart
        if lc.in_position and self.position_manager:
            logger.warning(
                f"⚠️ FINALIZE {lc.symbol}: position still OPEN! "
                f"reason={reason}, closing before cleanup..."
            )
            try:
                # Cancel Algo SL first to prevent phantom SHORT
                await self._cancel_exchange_sl(lc)

                # Get current price for PnL calculation
                current_price = 0.0
                if lc.bar_aggregator and lc.bar_aggregator.bar_count > 0:
                    current_price = lc.bar_aggregator.get_latest_bar().price
                if current_price <= 0:
                    current_price = lc.entry_price  # fallback

                await self.position_manager.close_position(
                    symbol=lc.symbol,
                    reason=f"lifecycle_finalize_{reason}",
                    close_price=current_price,
                )
                lc.in_position = False
                logger.info(f"✅ {lc.symbol}: Position closed during finalize")
            except Exception as e:
                logger.error(f"❌ Failed to close {lc.symbol} during finalize: {e}")

        trades_summary = ", ".join(
            f"#{t.trade_idx}:{t.reason}={t.pnl_pct:.1f}%" for t in lc.trades
        ) or "no trades"

        logger.info(
            f"🏁 FINALIZED {lc.symbol}: reason={reason}, "
            f"trades={lc.trade_count}, cumPnL={lc.cumulative_pnl:.2f}%, "
            f"history=[{trades_summary}]"
        )

        await self._cleanup_lifecycle(lc)

    async def _cleanup_lifecycle(self, lc: SignalLifecycle):
        """Remove lifecycle from active tracking, unsubscribe streams, delete from DB."""
        # Delete from DB (§4.1)
        await self._delete_lifecycle_db(lc)

        # Unsubscribe from aggTrades
        if self.aggtrades_stream:
            await self.aggtrades_stream.unsubscribe(lc.symbol)

        # Remove from active
        self.active.pop(lc.symbol, None)

    # ========================================================================
    # External Interface
    # ========================================================================

    def route_trade(self, symbol: str, price: float, qty: float,
                    is_buyer_maker: bool, trade_time_ms: int = 0):
        """
        Route an aggTrade to the appropriate bar aggregator.
        
        Called by BinanceAggTradesStream for symbols with active lifecycles.
        """
        lc = self.active.get(symbol)
        if lc and lc.bar_aggregator:
            lc.bar_aggregator.on_trade(price, qty, is_buyer_maker, trade_time_ms)

    def has_active_lifecycle(self, symbol: str) -> bool:
        """Check if symbol has an active lifecycle."""
        lc = self.active.get(symbol)
        return lc is not None and lc.state != SignalState.FINALIZED

    def get_lifecycle(self, symbol: str) -> Optional[SignalLifecycle]:
        """Get lifecycle for symbol."""
        return self.active.get(symbol)

    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        return {
            'active_lifecycles': len(self.active),
            'total_signals_received': self.total_signals_received,
            'total_signals_matched': self.total_signals_matched,
            'total_positions_opened': self.total_positions_opened,
            'total_positions_closed': self.total_positions_closed,
            'symbols': list(self.active.keys()),
            'states': {
                s: lc.state.value 
                for s, lc in self.active.items()
            },
        }

    # ========================================================================
    # Persistence (§4.1)
    # ========================================================================

    def _lifecycle_to_dict(self, lc: SignalLifecycle) -> dict:
        """Serialize lifecycle state for DB storage."""
        return {
            'symbol': lc.symbol,
            'exchange': lc.exchange,
            'signal_id': lc.signal_id,
            'state': lc.state.value,
            'strategy_params': {
                'leverage': lc.strategy.leverage,
                'sl_pct': lc.strategy.sl_pct,
                'base_activation': lc.strategy.base_activation,
                'base_callback': lc.strategy.base_callback,
                'base_cooldown': lc.strategy.base_cooldown,
                'base_reentry_drop': lc.strategy.base_reentry_drop,
                'delta_window': lc.strategy.delta_window,
                'threshold_mult': lc.strategy.threshold_mult,
                'max_reentry_hours': lc.strategy.max_reentry_hours,
                'max_position_hours': lc.strategy.max_position_hours,
            },
            'signal_start_ts': lc.signal_start_ts,
            'entry_price': lc.entry_price,
            'max_price': lc.max_price,
            'position_entry_ts': lc.position_entry_ts,
            'in_position': lc.in_position,
            'trade_count': lc.trade_count,
            'total_score': lc.total_score,
            'last_exit_ts': lc.last_exit_ts,
            'last_exit_price': lc.last_exit_price,
            'last_exit_reason': lc.last_exit_reason,
            'ts_activated': lc.ts_activated,
            'cumulative_pnl': lc.cumulative_pnl,
            'position_id': lc.position_id,
            # Smart Timeout v2.0
            'in_extension_mode': lc.in_extension_mode,
            'timeout_extensions_used': lc.timeout_extensions_used,
            'extension_start_ts': lc.extension_start_ts,
            'last_strength_check_ts': lc.last_strength_check_ts,
            'trades': [
                {
                    'trade_idx': t.trade_idx,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'entry_ts': t.entry_ts,
                    'exit_ts': t.exit_ts,
                    'reason': t.reason,
                    'pnl_pct': t.pnl_pct,
                    'is_reentry': t.is_reentry,
                }
                for t in lc.trades
            ],
        }

    async def _persist_lifecycle(self, lc: SignalLifecycle):
        """Save lifecycle state to DB."""
        if not self.repository:
            return
        try:
            data = self._lifecycle_to_dict(lc)
            await self.repository.save_lifecycle(data)
        except Exception as e:
            logger.error(f"Failed to persist lifecycle for {lc.symbol}: {e}")

    async def _delete_lifecycle_db(self, lc: SignalLifecycle):
        """Delete lifecycle from DB on finalization."""
        if not self.repository:
            return
        try:
            await self.repository.delete_lifecycle(lc.symbol, lc.exchange)
        except Exception as e:
            logger.error(f"Failed to delete lifecycle for {lc.symbol}: {e}")

    async def restore_from_db(self):
        """
        Restore active lifecycles from DB after restart (§4.1).
        
        Reconstructs SignalLifecycle objects, creates bar aggregators,
        re-subscribes to aggTrades, and loads lookback history.
        """
        if not self.repository:
            logger.info("No repository configured — skipping lifecycle restore")
            return 0

        try:
            rows = await self.repository.get_active_lifecycles()
        except Exception as e:
            logger.error(f"Failed to load lifecycles from DB: {e}")
            return 0

        if not rows:
            logger.info("No active lifecycles to restore")
            return 0

        restored = 0
        for row in rows:
            try:
                symbol = row['symbol']
                exchange = row['exchange']
                sp = row.get('strategy_params', {})

                # Reconstruct StrategyParams (FIX N-4: include max_reentry/position_hours)
                # FIX B3-1: Defaults aligned with StrategyParams class defaults
                params = StrategyParams(
                    leverage=sp.get('leverage', 10),
                    sl_pct=sp.get('sl_pct', 3.0),
                    base_activation=sp.get('base_activation', 10.0),
                    base_callback=sp.get('base_callback', 3.0),
                    base_cooldown=sp.get('base_cooldown', 300),
                    base_reentry_drop=sp.get('base_reentry_drop', 5.0),
                    delta_window=sp.get('delta_window', 3600),
                    threshold_mult=sp.get('threshold_mult', 1.0),
                    max_reentry_hours=sp.get('max_reentry_hours', 4),
                    max_position_hours=sp.get('max_position_hours', 24),
                )
                derived = DerivedConstants.from_params(params)

                # Create bar aggregator (FIX C-1: correct constructor params)
                bar_agg = BarAggregator(symbol, max_bars=self.bar_buffer_size)

                # Reconstruct trade records
                trade_records = [
                    TradeRecord(**t) for t in row.get('trades', [])
                ]

                state_str = row.get('state', 'in_position')
                state = SignalState(state_str)

                lc = SignalLifecycle(
                    signal_id=row.get('signal_id', 0),
                    symbol=symbol,
                    exchange=exchange,
                    strategy=params,
                    derived=derived,
                    state=state,
                    signal_start_ts=row.get('signal_start_ts', 0),
                    entry_price=float(row.get('entry_price', 0)),
                    max_price=float(row.get('max_price', 0)),
                    position_entry_ts=row.get('position_entry_ts', 0),
                    in_position=row.get('in_position', False),
                    trade_count=row.get('trade_count', 0),
                    last_exit_ts=row.get('last_exit_ts', 0),
                    last_exit_price=float(row.get('last_exit_price', 0)),
                    last_exit_reason=row.get('last_exit_reason', ''),
                    ts_activated=row.get('ts_activated', False),
                    trades=trade_records,
                    bar_aggregator=bar_agg,
                    cumulative_pnl=float(row.get('cumulative_pnl', 0)),
                    total_score=float(row.get('total_score', 0)),
                )

                self.active[symbol] = lc

                # Re-subscribe to aggTrades
                if self.aggtrades_stream:
                    await self.aggtrades_stream.subscribe(symbol)

                # Load lookback bars
                lookback_count = max(params.delta_window, 100)
                try:
                    loaded = await self._load_lookback_bars(lc, lookback_count)
                    logger.info(f"Restored {symbol}: loaded {loaded} lookback bars")
                except Exception as e:
                    logger.warning(f"Lookback failed for restored {symbol}: {e}")

                # Set bar callback
                bar_agg.on_bar_callback = lambda bar, s=symbol: asyncio.create_task(
                    self._on_bar_safe(s, bar)
                )

                # CRITICAL: Cross-check ALL non-IN_POSITION states with exchange
                # Fix waiting_data/reentry_wait by checking actual exchange state
                if state != SignalState.IN_POSITION and self.position_manager:
                    try:
                        has_pos = await self.position_manager.has_open_position(
                            symbol, exchange
                        )
                        if has_pos:
                            logger.warning(
                                f"⚠️ {symbol}: DB says {state_str} but exchange "
                                f"has OPEN position! Forcing state=IN_POSITION"
                            )
                            lc.state = SignalState.IN_POSITION
                            lc.in_position = True
                            state_str = "in_position (force-corrected)"
                            # Persist corrected state so next restart doesn't
                            # need force-correction again
                            await self._persist_lifecycle(lc)
                        elif state == SignalState.WAITING_DATA:
                            # No exchange position + waiting_data → should be REENTRY_WAIT
                            logger.warning(
                                f"⚠️ {symbol}: DB says waiting_data, no exchange position. "
                                f"Forcing state=REENTRY_WAIT so re-entry logic runs"
                            )
                            lc.state = SignalState.REENTRY_WAIT
                            lc.in_position = False
                            state_str = "reentry_wait (force-corrected from waiting_data)"
                            await self._persist_lifecycle(lc)
                    except Exception as e:
                        logger.warning(
                            f"Failed to cross-check {symbol} with exchange: {e}"
                        )

                restored += 1
                logger.info(
                    f"♻️ Restored lifecycle {symbol}: state={state_str}, "
                    f"trades={lc.trade_count}, pnl={lc.cumulative_pnl:.2f}%"
                )

            except Exception as e:
                logger.error(f"Failed to restore lifecycle for {row.get('symbol', '?')}: {e}", exc_info=True)

        logger.info(f"✅ Restored {restored}/{len(rows)} lifecycles from DB")
        return restored
