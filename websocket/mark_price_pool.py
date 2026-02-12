"""
MarkPriceConnectionPool — URL-based WebSocket connection pool for Binance Mark Prices

Architecture (from Expert Panel 2026-02-12):
  - All streams defined in URL at connection time (Combined Stream endpoint)
  - Max 200 streams per connection (Binance limit)
  - Max 3 connections (Binance IP limit recommendation)
  - Automatic reconnect with exponential backoff + jitter
  - Built-in heartbeat zombie detection (60s timeout)
  - Uses `websockets` library (context manager for clean lifecycle)

Replaces the dynamic SUBSCRIBE/UNSUBSCRIBE mechanism in BinanceHybridStream
that was the root cause of subscription state inconsistencies.

Date: 2026-02-12
"""

import asyncio
import logging
import random
import time
from typing import Callable, Set, List, Optional, Dict

try:
    import orjson
    def _json_loads(s): return orjson.loads(s)
except ImportError:
    import json
    _json_loads = json.loads

logger = logging.getLogger(__name__)


# Binance limits
MAX_STREAMS_PER_CONNECTION = 200
MAX_CONNECTIONS = 3
BASE_WS_URL = "wss://fstream.binance.com/stream"


class MarkPriceConnection:
    """
    Single WebSocket connection to Binance Combined Stream endpoint.
    
    Manages up to 200 streams via URL parameter.
    Uses `websockets` library for clean connection lifecycle.
    """

    def __init__(
        self,
        connection_id: int,
        streams: List[str],
        callback: Callable,
        frequency: str = "1s",
    ):
        """
        Args:
            connection_id: Unique ID for logging
            streams: List of stream names (e.g., ['btcusdt@markPrice@1s', ...])
            callback: Async callback(data: dict) for each markPriceUpdate
            frequency: Mark price frequency ('1s' or '3s')
        """
        self.connection_id = connection_id
        self.streams = streams
        self.callback = callback
        self.frequency = frequency

        # Connection state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._reconnect_count = 0
        self._last_message_time = 0.0
        self._messages_received = 0

        # Build URL with all streams
        self._url = self._build_url()

    def _build_url(self) -> str:
        """Build combined stream URL with all streams as query params"""
        streams_param = "/".join(self.streams)
        url = f"{BASE_WS_URL}?streams={streams_param}"
        logger.debug(
            f"[WS-{self.connection_id}] Built URL with {len(self.streams)} streams "
            f"({len(url)} chars)"
        )
        return url

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def symbols(self) -> Set[str]:
        """Extract symbol names from stream names"""
        result = set()
        for stream in self.streams:
            # 'btcusdt@markPrice@1s' → 'BTCUSDT'
            parts = stream.split('@')
            if parts:
                result.add(parts[0].upper())
        return result

    async def start(self):
        """Start connection in background task"""
        self._running = True
        self._task = asyncio.create_task(self._run_forever())
        logger.info(
            f"[WS-{self.connection_id}] Started with {len(self.streams)} streams"
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
            f"[WS-{self.connection_id}] Stopped "
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
                logger.info(
                    f"🌐 [WS-{self.connection_id}] Connecting "
                    f"({len(self.streams)} streams)..."
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
                        f"✅ [WS-{self.connection_id}] Connected "
                        f"({len(self.streams)} streams)"
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
                                # Combined stream format: {"stream": "...", "data": {...}}
                                if "data" in data:
                                    await self.callback(data["data"])
                                else:
                                    # Might be a direct message
                                    await self.callback(data)
                            except Exception as e:
                                logger.error(
                                    f"[WS-{self.connection_id}] "
                                    f"Message processing error: {e}"
                                )
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                logger.info(f"[WS-{self.connection_id}] Cancelled")
                break

            except Exception as e:
                logger.error(
                    f"❌ [WS-{self.connection_id}] Connection error: {e}"
                )

            finally:
                self._connected = False

            if not self._running:
                break

            # Reconnect with exponential backoff + jitter
            delay = self._get_reconnect_delay()
            self._reconnect_count += 1
            logger.info(
                f"🔄 [WS-{self.connection_id}] Reconnecting in {delay:.1f}s "
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
                        f"💔 [WS-{self.connection_id}] Frozen connection! "
                        f"No messages for {silence:.1f}s. Forcing close..."
                    )
                    await ws.close()
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"[WS-{self.connection_id}] Heartbeat error: {e}"
                )

    def _get_reconnect_delay(self) -> float:
        """Exponential backoff with jitter. Max 60s."""
        base = min(1.0 * (2 ** self._reconnect_count), 60.0)
        jitter = base * 0.25 * (2 * random.random() - 1)
        return base + jitter

    def get_status(self) -> Dict:
        return {
            'connection_id': self.connection_id,
            'connected': self._connected,
            'streams_count': len(self.streams),
            'messages_received': self._messages_received,
            'reconnect_count': self._reconnect_count,
            'symbols': sorted(self.symbols),
        }


class MarkPriceConnectionPool:
    """
    Connection pool for Binance Mark Price streams.
    
    Manages multiple MarkPriceConnection instances, distributing streams
    across connections respecting Binance limits (200 streams/conn, max 3 conns).
    
    Usage:
        pool = MarkPriceConnectionPool(on_price_update=my_callback)
        await pool.set_symbols({'BTCUSDT', 'ETHUSDT', ...})
        # ... later when positions change ...
        await pool.set_symbols({'BTCUSDT', 'ETHUSDT', 'SOLUSDT', ...})
        # ... cleanup ...
        await pool.stop()
    """

    def __init__(
        self,
        on_price_update: Callable,
        max_streams_per_connection: int = MAX_STREAMS_PER_CONNECTION,
        max_connections: int = MAX_CONNECTIONS,
        frequency: str = "1s",
    ):
        """
        Args:
            on_price_update: Async callback(data: dict) for each markPriceUpdate
            max_streams_per_connection: Max streams per WS connection (default: 200)
            max_connections: Max total WS connections (default: 3)
            frequency: Mark price update frequency ('1s' or '3s')
        """
        self.on_price_update = on_price_update
        self.max_streams = max_streams_per_connection
        self.max_connections = max_connections
        self.frequency = frequency

        self._connections: List[MarkPriceConnection] = []
        self._current_symbols: Set[str] = set()
        self._rebuild_lock = asyncio.Lock()

        # Debounce: coalesce rapid symbol changes into single rebuild
        self._debounce_task: Optional[asyncio.Task] = None
        self._debounce_delay: float = 0.5  # 500ms coalesce window
        self._pending_symbols: Optional[Set[str]] = None

    @property
    def connected(self) -> bool:
        """True if at least one connection is active"""
        return any(c.connected for c in self._connections)

    @property
    def all_connected(self) -> bool:
        """True if all connections are active"""
        return all(c.connected for c in self._connections) and len(self._connections) > 0

    @property
    def symbols(self) -> Set[str]:
        """Currently subscribed symbols"""
        return self._current_symbols.copy()

    async def set_symbols(self, symbols: Set[str]):
        """
        Set the complete list of symbols to subscribe to (DEBOUNCED).
        
        Coalesces rapid changes within 500ms window into single rebuild.
        For immediate rebuild (batch operations), use set_symbols_immediate().
        
        Args:
            symbols: Set of raw Binance symbols (e.g., 'BTCUSDT')
        """
        if symbols == self._current_symbols and self._pending_symbols is None:
            return

        self._pending_symbols = symbols.copy()

        # Cancel existing debounce timer
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        # Start new debounce timer
        self._debounce_task = asyncio.create_task(self._debounced_rebuild())

    async def _debounced_rebuild(self):
        """Wait for debounce window, then rebuild once."""
        try:
            await asyncio.sleep(self._debounce_delay)
        except asyncio.CancelledError:
            return  # New set_symbols() call will restart the timer

        async with self._rebuild_lock:
            if self._pending_symbols is None:
                return

            symbols = self._pending_symbols
            self._pending_symbols = None

            added = symbols - self._current_symbols
            removed = self._current_symbols - symbols
            if added:
                logger.info(f"➕ [POOL] Adding streams: {added}")
            if removed:
                logger.info(f"➖ [POOL] Removing streams: {removed}")

            self._current_symbols = symbols.copy()
            await self._rebuild_connections()

    async def set_symbols_immediate(self, symbols: Set[str]):
        """
        Force immediate rebuild (bypass debounce).
        
        Used for batch operations where all symbols are known upfront.
        """
        if symbols == self._current_symbols:
            return

        # Cancel any pending debounce
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            self._pending_symbols = None

        async with self._rebuild_lock:
            added = symbols - self._current_symbols
            removed = self._current_symbols - symbols
            if added:
                logger.info(f"➕ [POOL] Adding streams: {added}")
            if removed:
                logger.info(f"➖ [POOL] Removing streams: {removed}")

            self._current_symbols = symbols.copy()
            await self._rebuild_connections()

    async def add_symbol(self, symbol: str):
        """Add a single symbol (debounced)"""
        if symbol not in self._current_symbols:
            pending = self._pending_symbols or self._current_symbols
            await self.set_symbols(pending | {symbol})

    async def remove_symbol(self, symbol: str):
        """Remove a single symbol (debounced)"""
        pending = self._pending_symbols or self._current_symbols
        if symbol in pending:
            await self.set_symbols(pending - {symbol})

    async def stop(self):
        """Stop all connections"""
        # Cancel debounce timer
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            self._pending_symbols = None

        logger.info(f"🛑 [POOL] Stopping {len(self._connections)} connections...")
        for conn in self._connections:
            await conn.stop()
        self._connections.clear()
        self._current_symbols.clear()
        logger.info("✅ [POOL] All connections stopped")

    async def _rebuild_connections(self):
        """
        Rebuild all connections with optimal stream distribution.
        
        Strategy:
        1. Stop all existing connections
        2. Distribute streams across new connections (max 200/conn)
        3. Start new connections in parallel
        
        The brief disconnect (~1-2s) is acceptable because:
        - REST fallback covers the gap (Fix 1.3 preserves prices)
        - This only happens when positions are opened/closed
        """
        # Build stream list
        streams = [
            f"{s.lower()}@markPrice@{self.frequency}"
            for s in sorted(self._current_symbols)
        ]

        if not streams:
            # No symbols — stop everything
            for conn in self._connections:
                await conn.stop()
            self._connections.clear()
            logger.info("[POOL] No symbols to subscribe — all connections stopped")
            return

        # Check limits
        total_streams = len(streams)
        needed_connections = (total_streams + self.max_streams - 1) // self.max_streams

        if needed_connections > self.max_connections:
            logger.error(
                f"❌ [POOL] Need {needed_connections} connections for "
                f"{total_streams} streams, but max is {self.max_connections}! "
                f"Max supported symbols: {self.max_streams * self.max_connections}"
            )
            # Truncate to fit within limits
            max_symbols = self.max_streams * self.max_connections
            streams = streams[:max_symbols]
            needed_connections = self.max_connections

        # Stop old connections
        for conn in self._connections:
            await conn.stop()
        self._connections.clear()

        # Create new connections with distributed streams
        logger.info(
            f"🔄 [POOL] Rebuilding: {total_streams} streams "
            f"across {needed_connections} connections"
        )

        for i in range(0, len(streams), self.max_streams):
            chunk = streams[i:i + self.max_streams]
            conn = MarkPriceConnection(
                connection_id=len(self._connections),
                streams=chunk,
                callback=self.on_price_update,
                frequency=self.frequency,
            )
            self._connections.append(conn)

        # Start all connections in parallel
        await asyncio.gather(
            *(conn.start() for conn in self._connections)
        )

        logger.info(
            f"✅ [POOL] Rebuild complete: {len(self._connections)} connections, "
            f"{total_streams} total streams"
        )

    def get_status(self) -> Dict:
        """Get pool status for monitoring"""
        return {
            'total_connections': len(self._connections),
            'connected_count': sum(1 for c in self._connections if c.connected),
            'total_symbols': len(self._current_symbols),
            'connections': [c.get_status() for c in self._connections],
        }
