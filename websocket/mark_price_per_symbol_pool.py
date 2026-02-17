"""
MarkPricePerSymbolPool — Per-symbol WebSocket connections for Binance Mark Prices

Architecture:
  - One WebSocket connection per symbol
  - URL: wss://fstream.binance.com/ws/{symbol}@markPrice@{frequency}
  - Adding/removing a symbol has ZERO impact on other symbols
  - Auto-reconnect with exponential backoff + jitter per connection
  - Built-in heartbeat zombie detection (60s timeout)
  - Uses `websockets` library for clean connection lifecycle

Replaces MarkPriceConnectionPool which used URL-based combined streams
and required full reconnection on any symbol change (3-4s blackout).

Drop-in replacement: same public API (add_symbol, remove_symbol,
set_symbols, set_symbols_immediate, stop, connected, symbols, get_status).

Date: 2026-02-17
"""

import asyncio
import logging
import random
import time
from typing import Callable, Set, Optional, Dict

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


class PerSymbolConnection:
    """
    Single WebSocket connection for one symbol's mark price stream.

    URL: wss://fstream.binance.com/ws/{symbol}@markPrice@{frequency}

    Features:
    - Auto-reconnect with exponential backoff + jitter
    - Heartbeat monitoring (60s frozen detection)
    - Clean lifecycle via `websockets` context manager
    """

    def __init__(
        self,
        symbol: str,
        callback: Callable,
        frequency: str = "1s",
    ):
        """
        Args:
            symbol: Raw Binance symbol (e.g., 'BTCUSDT')
            callback: Async callback(data: dict) for each markPriceUpdate
            frequency: Mark price frequency ('1s' or '3s')
        """
        self.symbol = normalize_symbol(symbol)
        self.callback = callback
        self.frequency = frequency

        # Connection state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._reconnect_count = 0
        self._last_message_time = 0.0
        self._messages_received = 0

        # Build URL: single stream, no combined endpoint needed
        stream_name = f"{symbol.lower()}@markPrice@{frequency}"
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
            f"🌐 [WS-{self.symbol}] Starting per-symbol connection"
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
            f"⏹️ [WS-{self.symbol}] Stopped "
            f"(total messages: {self._messages_received})"
        )

    async def _run_forever(self):
        """
        Main connection loop with automatic reconnect.

        Uses `websockets` context manager for clean lifecycle:
        - Connection cleanup on any exit (normal, error, cancel)
        - Built-in ping/pong via ping_interval/ping_timeout
        """
        import websockets

        while self._running:
            try:
                logger.debug(
                    f"🌐 [WS-{self.symbol}] Connecting to {self._url}..."
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
                        f"✅ [WS-{self.symbol}] Connected"
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
                                # Single stream format: direct markPriceUpdate
                                # (no {"stream": ..., "data": ...} wrapper)
                                await self.callback(data)
                            except Exception as e:
                                logger.error(
                                    f"[WS-{self.symbol}] "
                                    f"Message processing error: {e}"
                                )
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                logger.debug(f"[WS-{self.symbol}] Cancelled")
                break

            except Exception as e:
                logger.warning(
                    f"❌ [WS-{self.symbol}] Connection error: {e}"
                )

            finally:
                self._connected = False

            if not self._running:
                break

            # Reconnect with exponential backoff + jitter
            delay = self._get_reconnect_delay()
            self._reconnect_count += 1
            logger.info(
                f"🔄 [WS-{self.symbol}] Reconnecting in {delay:.1f}s "
                f"(attempt {self._reconnect_count})..."
            )
            await asyncio.sleep(delay)

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
                        f"💔 [WS-{self.symbol}] Frozen! "
                        f"No messages for {silence:.1f}s. Forcing close..."
                    )
                    await ws.close()
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"[WS-{self.symbol}] Heartbeat error: {e}"
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
        }


class MarkPricePerSymbolPool:
    """
    Pool of per-symbol WebSocket connections for Binance Mark Prices.

    Drop-in replacement for MarkPriceConnectionPool.
    Each symbol gets its own WebSocket connection, so adding/removing
    a symbol has ZERO impact on other symbols' data flow.

    API (identical to MarkPriceConnectionPool):
        pool = MarkPricePerSymbolPool(on_price_update=my_callback)
        await pool.add_symbol('BTCUSDT')     # starts 1 new WS
        await pool.remove_symbol('BTCUSDT')  # stops only that WS
        await pool.set_symbols({'BTC', 'ETH'})  # diff-based update
        await pool.stop()                    # stop all
    """

    def __init__(
        self,
        on_price_update: Callable,
        max_streams_per_connection: int = 200,  # Ignored, kept for API compat
        max_connections: int = 3,                # Ignored, kept for API compat
        frequency: str = "1s",
    ):
        """
        Args:
            on_price_update: Async callback(data: dict) for each markPriceUpdate
            max_streams_per_connection: IGNORED (API compatibility)
            max_connections: IGNORED (API compatibility)
            frequency: Mark price update frequency ('1s' or '3s')
        """
        self.on_price_update = on_price_update
        self.frequency = frequency

        self._connections: Dict[str, PerSymbolConnection] = {}
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """True if at least one connection is active"""
        return any(c.connected for c in self._connections.values())

    @property
    def all_connected(self) -> bool:
        """True if all connections are active"""
        return (
            all(c.connected for c in self._connections.values())
            and len(self._connections) > 0
        )

    @property
    def symbols(self) -> Set[str]:
        """Currently tracked symbols"""
        return set(self._connections.keys())

    async def add_symbol(self, symbol: str):
        """
        Add a single symbol — starts one new WS connection.

        Zero impact on existing connections.
        """
        symbol = normalize_symbol(symbol)
        async with self._lock:
            if symbol in self._connections:
                logger.debug(f"[POOL] {symbol} already tracked, skipping")
                return

            if len(self._connections) >= MAX_CONNECTIONS_PER_IP:
                logger.error(
                    f"❌ [POOL] Cannot add {symbol}: at Binance limit "
                    f"({MAX_CONNECTIONS_PER_IP} connections)"
                )
                return

            conn = PerSymbolConnection(
                symbol=symbol,
                callback=self.on_price_update,
                frequency=self.frequency,
            )
            self._connections[symbol] = conn
            await conn.start()
            logger.info(
                f"➕ [POOL] Added {symbol} "
                f"(total: {len(self._connections)} connections)"
            )

    async def remove_symbol(self, symbol: str):
        """
        Remove a single symbol — stops only that WS connection.

        Zero impact on other connections.
        """
        symbol = normalize_symbol(symbol)
        async with self._lock:
            conn = self._connections.pop(symbol, None)
            if conn:
                await conn.stop()
                logger.info(
                    f"➖ [POOL] Removed {symbol} "
                    f"(total: {len(self._connections)} connections)"
                )
            else:
                logger.debug(f"[POOL] {symbol} not tracked, nothing to remove")

    async def set_symbols(self, symbols: Set[str]):
        """
        Set the complete list of symbols to subscribe to.

        Diff-based: only starts/stops connections that changed.
        No debounce needed — per-symbol operations are instant.

        Args:
            symbols: Set of raw Binance symbols (e.g., 'BTCUSDT')
        """
        symbols = {normalize_symbol(s) for s in symbols}
        async with self._lock:
            current = set(self._connections.keys())

            if symbols == current:
                return

            added = symbols - current
            removed = current - symbols

            if added:
                logger.info(f"➕ [POOL] Adding: {added}")
            if removed:
                logger.info(f"➖ [POOL] Removing: {removed}")

            # Stop removed connections
            stop_tasks = []
            for symbol in removed:
                conn = self._connections.pop(symbol, None)
                if conn:
                    stop_tasks.append(conn.stop())
            if stop_tasks:
                await asyncio.gather(*stop_tasks)

            # Start new connections
            for symbol in added:
                if len(self._connections) >= MAX_CONNECTIONS_PER_IP:
                    logger.error(
                        f"❌ [POOL] Cannot add {symbol}: at Binance limit"
                    )
                    break

                conn = PerSymbolConnection(
                    symbol=symbol,
                    callback=self.on_price_update,
                    frequency=self.frequency,
                )
                self._connections[symbol] = conn
                await conn.start()

            logger.info(
                f"✅ [POOL] Set complete: {len(self._connections)} connections"
            )

    async def set_symbols_immediate(self, symbols: Set[str]):
        """
        Same as set_symbols — no debounce needed in per-symbol architecture.

        Kept for API compatibility with MarkPriceConnectionPool.
        """
        await self.set_symbols(symbols)

    async def stop(self):
        """Stop all connections"""
        async with self._lock:
            logger.info(
                f"🛑 [POOL] Stopping {len(self._connections)} connections..."
            )
            stop_tasks = [conn.stop() for conn in self._connections.values()]
            if stop_tasks:
                await asyncio.gather(*stop_tasks)
            self._connections.clear()
            logger.info("✅ [POOL] All connections stopped")

    def get_status(self) -> Dict:
        """Get pool status for monitoring"""
        return {
            'total_connections': len(self._connections),
            'connected_count': sum(
                1 for c in self._connections.values() if c.connected
            ),
            'total_symbols': len(self._connections),
            'connections': [
                c.get_status() for c in self._connections.values()
            ],
        }
