"""
AggTradesPerSymbolPool — Per-symbol WebSocket connections for Binance AggTrades

Architecture:
  - One WebSocket connection per subscribed symbol
  - URL: wss://fstream.binance.com/ws/{symbol}@aggTrade
  - Adding/removing a symbol has ZERO impact on other symbols
  - Auto-reconnect with exponential backoff + jitter per connection
  - Built-in heartbeat zombie detection (60s timeout)
  - Same public API as BinanceAggTradesStream (drop-in replacement)

Replaces BinanceAggTradesStream which used a single combined WebSocket
with JSON SUBSCRIBE/UNSUBSCRIBE. If that one WS died, ALL symbols
lost data simultaneously — a silent failure for critical delta filter.

Date: 2026-02-17
"""

import asyncio
import logging
import random
import time
from typing import Dict, Callable, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import deque
from decimal import Decimal

from utils.symbol_helpers import normalize_symbol

try:
    import orjson
    def _json_loads(s): return orjson.loads(s)
except ImportError:
    import json
    _json_loads = json.loads

logger = logging.getLogger(__name__)


# Binance limits
BASE_WS_URL = "wss://fstream.binance.com/ws"
MAX_CONNECTIONS_PER_IP = 300  # Binance futures WS limit


# ═══════════════════════════════════════════════════════════════
# Data structures (moved from binance_aggtrades_stream.py)
# ═══════════════════════════════════════════════════════════════

@dataclass
class TradeData:
    """Single aggregated trade"""
    timestamp: float  # Unix timestamp in seconds
    price: Decimal
    quantity: Decimal
    is_buyer_maker: bool  # True = sell initiated, False = buy initiated

    @property
    def side(self) -> str:
        """Returns 'buy' if buyer initiated, 'sell' if seller initiated"""
        return 'sell' if self.is_buyer_maker else 'buy'

    @property
    def volume_usdt(self) -> Decimal:
        """Trade volume in USDT"""
        return self.price * self.quantity


@dataclass
class SymbolDeltaState:
    """Delta calculation state for a symbol"""
    trades: deque = field(default_factory=lambda: deque(maxlen=10000))  # Last 10k trades
    last_update: float = 0.0

    # Rolling stats
    rolling_delta: Decimal = Decimal('0')
    avg_delta: Decimal = Decimal('0')  # Historical average for comparison

    # Large trade tracking (>$10k USDT)
    large_buy_count: int = 0
    large_sell_count: int = 0


# ═══════════════════════════════════════════════════════════════
# Per-symbol WebSocket connection
# ═══════════════════════════════════════════════════════════════

class AggTradePerSymbolConnection:
    """
    Single WebSocket connection for one symbol's aggTrade stream.

    URL: wss://fstream.binance.com/ws/{symbol}@aggTrade

    Features:
    - Auto-reconnect with exponential backoff + jitter
    - Heartbeat monitoring (60s frozen detection)
    - Clean lifecycle via `websockets` context manager
    - Feeds raw trade data to delta state and trade handlers
    """

    def __init__(
        self,
        symbol: str,
        delta_state: SymbolDeltaState,
        trade_handlers: list,
    ):
        """
        Args:
            symbol: Raw Binance symbol (e.g., 'BTCUSDT')
            delta_state: Shared SymbolDeltaState for this symbol
            trade_handlers: List of callbacks for raw trade data
        """
        self.symbol = normalize_symbol(symbol)
        self.delta_state = delta_state
        self._trade_handlers = trade_handlers

        # Connection state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._reconnect_count = 0
        self._last_message_time = 0.0
        self._messages_received = 0

        # Build URL
        stream_name = f"{self.symbol.lower()}@aggTrade"
        self._url = f"{BASE_WS_URL}/{stream_name}"

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self):
        """Start connection in background task"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_forever())
        logger.info(
            f"🌐 [AGG-{self.symbol}] Starting per-symbol aggTrade connection"
        )

    async def stop(self):
        """Stop connection gracefully"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        logger.info(
            f"⏹️ [AGG-{self.symbol}] Stopped "
            f"(total messages: {self._messages_received})"
        )

    async def _run_forever(self):
        """
        Main connection loop with automatic reconnect.

        Uses `websockets` context manager for clean lifecycle.
        """
        import websockets

        while self._running:
            try:
                logger.debug(
                    f"🌐 [AGG-{self.symbol}] Connecting to {self._url}..."
                )

                async with websockets.connect(
                    self._url,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=10,
                    max_size=2**20,  # 1MB max message
                ) as ws:
                    self._connected = True
                    self._reconnect_count = 0
                    self._last_message_time = time.monotonic()
                    logger.info(
                        f"✅ [AGG-{self.symbol}] Connected"
                    )

                    # Heartbeat monitor task
                    heartbeat_task = asyncio.create_task(
                        self._heartbeat_monitor(ws)
                    )

                    try:
                        async for message in ws:
                            if not self._running:
                                break

                            self._last_message_time = time.monotonic()
                            self._messages_received += 1

                            try:
                                data = _json_loads(message)
                                self._process_trade(data)
                            except Exception as e:
                                logger.error(
                                    f"[AGG-{self.symbol}] "
                                    f"Message processing error: {e}"
                                )
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                logger.debug(f"[AGG-{self.symbol}] Cancelled")
                break

            except Exception as e:
                logger.warning(
                    f"❌ [AGG-{self.symbol}] Connection error: {e}"
                )

            finally:
                self._connected = False

            if not self._running:
                break

            # Reconnect with exponential backoff + jitter
            delay = self._get_reconnect_delay()
            self._reconnect_count += 1
            logger.info(
                f"🔄 [AGG-{self.symbol}] Reconnecting in {delay:.1f}s "
                f"(attempt {self._reconnect_count})..."
            )
            await asyncio.sleep(delay)

    def _process_trade(self, data: dict):
        """
        Process aggTrade message: update delta state + notify handlers.

        Payload:
        {
            "e": "aggTrade",
            "s": "BTCUSDT",
            "p": "23000.50",
            "q": "0.015",
            "T": 1672515782120,
            "m": true
        }
        """
        event_type = data.get('e')
        if event_type != 'aggTrade':
            return

        # Update delta state
        trade = TradeData(
            timestamp=data.get('T', 0) / 1000,  # Convert to seconds
            price=Decimal(str(data.get('p', '0'))),
            quantity=Decimal(str(data.get('q', '0'))),
            is_buyer_maker=data.get('m', False)
        )

        self.delta_state.trades.append(trade)
        self.delta_state.last_update = asyncio.get_event_loop().time()

        # Notify registered trade handlers (for bar_aggregator feed)
        for handler in self._trade_handlers:
            try:
                handler(data)
            except Exception as e:
                logger.debug(f"Trade handler error: {e}")

    async def _heartbeat_monitor(self, ws):
        """
        Detect frozen connections (connected but no data flowing).

        If no message received for 60s, force-close the WebSocket.
        The outer loop will automatically reconnect.
        """
        TIMEOUT = 60.0
        CHECK_INTERVAL = 15.0

        while self._running:
            try:
                await asyncio.sleep(CHECK_INTERVAL)

                if not self._running:
                    break

                silence = time.monotonic() - self._last_message_time
                if silence > TIMEOUT:
                    logger.warning(
                        f"💔 [AGG-{self.symbol}] Frozen! "
                        f"No messages for {silence:.1f}s. Forcing close..."
                    )
                    await ws.close()
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"[AGG-{self.symbol}] Heartbeat error: {e}"
                )

    def _get_reconnect_delay(self) -> float:
        """Exponential backoff with jitter. Max 60s."""
        base = min(1.0 * (2 ** self._reconnect_count), 60.0)
        jitter = base * 0.25 * (2 * random.random() - 1)
        return max(0.5, base + jitter)

    def get_status(self) -> Dict:
        return {
            'symbol': self.symbol,
            'connected': self._connected,
            'messages_received': self._messages_received,
            'reconnect_count': self._reconnect_count,
            'trades_in_buffer': len(self.delta_state.trades),
        }


# ═══════════════════════════════════════════════════════════════
# Pool — manages per-symbol connections
# ═══════════════════════════════════════════════════════════════

class AggTradesPerSymbolPool:
    """
    Pool of per-symbol WebSocket connections for Binance AggTrades.

    Drop-in replacement for BinanceAggTradesStream.
    Each symbol gets its own WebSocket connection, so a failure
    in one symbol's stream has ZERO impact on other symbols.

    API (identical to BinanceAggTradesStream):
        pool = AggTradesPerSymbolPool(testnet=False)
        await pool.start()
        await pool.subscribe('BTCUSDT')
        delta = pool.get_rolling_delta('BTCUSDT', 20)
        await pool.unsubscribe('BTCUSDT')
        await pool.stop()
    """

    # Large trade threshold in USDT
    LARGE_TRADE_THRESHOLD = Decimal('10000')

    def __init__(self, testnet: bool = False):
        """
        Args:
            testnet: Use testnet endpoints (not supported for per-symbol)
        """
        self.testnet = testnet

        # Per-symbol connections
        self._connections: Dict[str, AggTradePerSymbolConnection] = {}
        self._lock = asyncio.Lock()

        # Delta state per symbol
        self.delta_states: Dict[str, SymbolDeltaState] = {}

        # Reference counting for subscriptions
        self._subscription_refcount: Dict[str, int] = {}

        # External trade handlers (for bar_aggregator feed via main.py)
        self._trade_handlers: list = []

        # Compat: replicate subscribed_symbols set for health checks
        self.subscribed_symbols: Set[str] = set()

        # State
        self.running = False
        self.connected = False  # Compat: always True when running

        logger.info(f"AggTradesPerSymbolPool initialized (testnet={testnet})")

    async def start(self):
        """Start the pool (no WS connections yet — they start on subscribe)"""
        if self.running:
            logger.warning("AggTradesPerSymbolPool already running")
            return
        self.running = True
        self.connected = True
        logger.info("🚀 AggTradesPerSymbolPool started (per-symbol mode)")

    async def stop(self):
        """Stop all connections"""
        if not self.running:
            return

        logger.info("⏹️ Stopping AggTradesPerSymbolPool...")

        self.running = False
        self.connected = False

        async with self._lock:
            stop_tasks = [conn.stop() for conn in self._connections.values()]
            if stop_tasks:
                await asyncio.gather(*stop_tasks)
            self._connections.clear()
            self.subscribed_symbols.clear()
            self._subscription_refcount.clear()

        logger.info("✅ AggTradesPerSymbolPool stopped")

    # ────────────────── Subscribe / Unsubscribe ──────────────────

    async def subscribe(self, symbol: str):
        """
        Subscribe to aggTrades for a symbol.
        Reference-counted: multiple subscribers to same symbol are tracked.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
        """
        symbol = normalize_symbol(symbol).upper()

        self._subscription_refcount[symbol] = self._subscription_refcount.get(symbol, 0) + 1

        if symbol in self._connections:
            logger.debug(
                f"[AGG-POOL] Already subscribed to {symbol} "
                f"(refcount={self._subscription_refcount[symbol]})"
            )
            return

        # Initialize delta state
        if symbol not in self.delta_states:
            self.delta_states[symbol] = SymbolDeltaState()

        # Create per-symbol connection
        async with self._lock:
            if len(self._connections) >= MAX_CONNECTIONS_PER_IP:
                logger.error(
                    f"❌ [AGG-POOL] Cannot subscribe to {symbol}: "
                    f"at Binance limit ({MAX_CONNECTIONS_PER_IP} connections)"
                )
                return

            conn = AggTradePerSymbolConnection(
                symbol=symbol,
                delta_state=self.delta_states[symbol],
                trade_handlers=self._trade_handlers,
            )
            self._connections[symbol] = conn
            self.subscribed_symbols.add(symbol)
            await conn.start()

        logger.info(
            f"📥 [AGG-POOL] Subscribed to {symbol} "
            f"(refcount={self._subscription_refcount[symbol]}, "
            f"total: {len(self._connections)} connections)"
        )

    async def unsubscribe(self, symbol: str):
        """
        Unsubscribe from aggTrades for a symbol.
        Reference-counted: only actually disconnects when last subscriber leaves.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
        """
        symbol = normalize_symbol(symbol).upper()

        count = self._subscription_refcount.get(symbol, 0)
        if count > 1:
            self._subscription_refcount[symbol] = count - 1
            logger.debug(
                f"[AGG-POOL] Decremented refcount for {symbol} to {count - 1}, "
                f"keeping connection"
            )
            return

        # Last subscriber — actually disconnect
        self._subscription_refcount.pop(symbol, None)

        async with self._lock:
            conn = self._connections.pop(symbol, None)
            if conn:
                await conn.stop()
                self.subscribed_symbols.discard(symbol)
                logger.info(
                    f"📤 [AGG-POOL] Unsubscribed from {symbol} "
                    f"(last subscriber, total: {len(self._connections)} connections)"
                )

    # ────────────────── Delta Calculations ──────────────────

    def get_rolling_delta(self, symbol: str, window_sec: int = 20) -> Decimal:
        """
        Get rolling delta for symbol over time window

        Delta = sum(buy_volume) - sum(sell_volume) in USDT

        Args:
            symbol: Trading symbol
            window_sec: Rolling window in seconds (default: 20)

        Returns:
            Decimal: Positive = buying pressure, Negative = selling pressure
        """
        symbol = normalize_symbol(symbol).upper()

        state = self.delta_states.get(symbol)
        if not state or not state.trades:
            return Decimal('0')

        current_time = asyncio.get_event_loop().time()
        cutoff = current_time - window_sec

        buy_volume = Decimal('0')
        sell_volume = Decimal('0')

        for trade in state.trades:
            if trade.timestamp >= cutoff:
                if trade.side == 'buy':
                    buy_volume += trade.volume_usdt
                else:
                    sell_volume += trade.volume_usdt

        delta = buy_volume - sell_volume
        state.rolling_delta = delta

        return delta

    def get_avg_delta(self, symbol: str, samples: int = 100) -> Decimal:
        """
        Get average absolute delta over recent samples

        Used as baseline for threshold comparison

        Args:
            symbol: Trading symbol
            samples: Number of delta samples to average

        Returns:
            Decimal: Average absolute delta (always positive)
        """
        symbol = normalize_symbol(symbol).upper()

        state = self.delta_states.get(symbol)
        if not state or not state.trades:
            return Decimal('1')  # Return 1 to avoid division by zero

        # Calculate delta for each 1-second bucket
        current_time = asyncio.get_event_loop().time()
        bucket_deltas = []

        for i in range(samples):
            bucket_start = current_time - (i + 1)
            bucket_end = current_time - i

            bucket_buy = Decimal('0')
            bucket_sell = Decimal('0')

            for trade in state.trades:
                if bucket_start <= trade.timestamp < bucket_end:
                    if trade.side == 'buy':
                        bucket_buy += trade.volume_usdt
                    else:
                        bucket_sell += trade.volume_usdt

            bucket_deltas.append(abs(bucket_buy - bucket_sell))

        if not bucket_deltas:
            return Decimal('1')

        avg = sum(bucket_deltas) / len(bucket_deltas)
        state.avg_delta = avg

        return avg

    def get_large_trade_counts(self, symbol: str, window_sec: int = 60) -> Tuple[int, int]:
        """
        Get large trade counts in recent window

        Large trade = trade > LARGE_TRADE_THRESHOLD (default $10k)

        Args:
            symbol: Trading symbol
            window_sec: Window in seconds

        Returns:
            Tuple[int, int]: (large_buy_count, large_sell_count)
        """
        symbol = normalize_symbol(symbol).upper()

        state = self.delta_states.get(symbol)
        if not state or not state.trades:
            return (0, 0)

        current_time = asyncio.get_event_loop().time()
        cutoff = current_time - window_sec

        large_buys = 0
        large_sells = 0

        for trade in state.trades:
            if trade.timestamp >= cutoff:
                if trade.volume_usdt >= self.LARGE_TRADE_THRESHOLD:
                    if trade.side == 'buy':
                        large_buys += 1
                    else:
                        large_sells += 1

        state.large_buy_count = large_buys
        state.large_sell_count = large_sells

        return (large_buys, large_sells)

    def get_stats(self, symbol: str) -> Dict:
        """
        Get comprehensive delta stats for symbol

        Args:
            symbol: Trading symbol

        Returns:
            Dict with delta statistics
        """
        symbol = normalize_symbol(symbol).upper()

        state = self.delta_states.get(symbol)
        if not state:
            return {}

        rolling_delta = self.get_rolling_delta(symbol, 20)
        avg_delta = self.get_avg_delta(symbol, 100)
        large_buys, large_sells = self.get_large_trade_counts(symbol, 60)

        return {
            'symbol': symbol,
            'rolling_delta_20s': float(rolling_delta),
            'avg_delta_100s': float(avg_delta),
            'delta_ratio': float(rolling_delta / avg_delta) if avg_delta > 0 else 0,
            'large_buys_60s': large_buys,
            'large_sells_60s': large_sells,
            'trade_count': len(state.trades),
            'last_update': state.last_update
        }

    # ────────────────── Pool Status ──────────────────

    def get_pool_status(self) -> Dict:
        """Get pool status for monitoring"""
        return {
            'total_connections': len(self._connections),
            'connected_count': sum(
                1 for c in self._connections.values() if c.connected
            ),
            'subscribed_symbols': list(self.subscribed_symbols),
            'connections': [
                c.get_status() for c in self._connections.values()
            ],
        }
