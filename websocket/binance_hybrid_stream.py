"""
Binance Hybrid WebSocket Stream
Combines User Data Stream (position lifecycle) + Mark Price Stream (real-time prices)

Architecture:
- User Data Stream: ACCOUNT_UPDATE for position open/close/modify
- Mark Price Stream: markPriceUpdate for real-time mark prices (1s)
- Event Combining: Merge position data + mark price → unified events

Date: 2025-10-25
"""

import asyncio
import aiohttp
import logging
import random
from typing import Dict, Callable, Optional, Set
from datetime import datetime

try:
    import orjson
    def _json_loads(s): return orjson.loads(s)
    def _json_dumps(obj): return orjson.dumps(obj).decode()
except ImportError:
    import json
    _json_loads = json.loads
    _json_dumps = json.dumps

from websocket.mark_price_pool import MarkPriceConnectionPool
from websocket.symbol_state import SymbolStateManager, SymbolState

logger = logging.getLogger(__name__)


class BinanceHybridStream:
    """
    Hybrid WebSocket stream for Binance Futures

    Manages TWO WebSocket connections:
    1. User Data Stream → Position lifecycle (open/close/modify)
    2. Mark Price Stream → Mark price updates (1-3s frequency)

    Combines both streams to emit unified position.update events with:
    - Position data (size, side, entry price) from User Data Stream
    - Real-time mark price from Mark Price Stream
    """

    def __init__(self,
                 api_key: str,
                 api_secret: str,
                 event_handler: Optional[Callable] = None,
                 position_fetch_callback: Optional[Callable] = None,
                 reentry_price_callback: Optional[Callable] = None,  # NEW 2026-01-03
                 exchange_manager=None,  # For REST price fallback
                 testnet: bool = False):
        """
        Initialize Binance Hybrid WebSocket

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            event_handler: Callback for events (event_type, data)
            reentry_price_callback: Callback for ALL mark price updates (for reentry signals)
            exchange_manager: ExchangeManager instance for REST price fallback
            testnet: Use testnet endpoints
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.event_handler = event_handler
        self.position_fetch_callback = position_fetch_callback
        self.exchange_manager = exchange_manager  # For REST price fallback
        self.reentry_price_callback = reentry_price_callback  # NEW 2026-01-03
        self.testnet = testnet

        # URLs
        if testnet:
            self.rest_url = "https://testnet.binance.vision/fapi/v1"
            self.user_ws_url = "wss://stream.binance.vision:9443/ws"
            self.mark_ws_url = "wss://stream.binance.vision/ws"
        else:
            self.rest_url = "https://fapi.binance.com/fapi/v1"
            self.user_ws_url = "wss://fstream.binance.com/ws"
            self.mark_ws_url = "wss://fstream.binance.com/ws"  # Dynamic SUBSCRIBE endpoint

        # Listen key management
        self.listen_key = None
        self.listen_key_expires = None

        # WebSocket connections and sessions
        self.user_ws = None
        self.mark_ws = None
        self.user_session = None  # aiohttp.ClientSession for user stream
        self.mark_session = None  # aiohttp.ClientSession for mark stream

        # Connection state
        self.user_connected = False
        self.mark_connected = False
        self.running = False

        # Hybrid state
        self.positions: Dict[str, Dict] = {}  # {symbol: position_data}
        self.mark_prices: Dict[str, str] = {}  # {symbol: latest_mark_price}

        # ==================== NEW ARCHITECTURE (Expert Panel 2026-02-12) ====================
        # MarkPriceConnectionPool: URL-based combined streams, replaces dynamic SUBSCRIBE
        self.mark_price_pool = MarkPriceConnectionPool(
            on_price_update=self._on_pool_price_update,
            frequency="1s",
        )
        # SymbolStateManager: single source of truth, replaces 4 overlapping sets
        self.symbol_state = SymbolStateManager(stale_threshold=3.0)

        # Legacy state (kept for backward compatibility during transition)
        # These are now populated FROM SymbolStateManager
        self.subscribed_symbols: Set[str] = set()  # Mirror of symbol_state.subscribed_symbols
        self.pending_subscriptions: Set[str] = set()  # Mirror of symbol_state.pending_symbols
        self.subscription_queue = asyncio.Queue()  # Still used by _subscription_manager
        self.next_request_id = 1

        # PHASE 4: WebSocket heartbeat monitoring
        self.last_mark_message_time = 0.0  # Monotonic time of last mark stream message
        self.last_user_message_time = 0.0  # Monotonic time of last user stream message

        # NEW: Position manager reference for health check
        self.position_manager = None  # Set via set_position_manager()

        # Tasks
        self.user_task = None
        self.mark_task = None  # Legacy: kept but now managed by pool
        self.keepalive_task = None
        self.subscription_task = None
        self.reconnection_task = None
        self.health_check_task = None
        self.heartbeat_task = None
        self.pending_processor_task = None
        self.rest_fallback_task = None

        # FIX: Cache fill prices from ORDER_TRADE_UPDATE for accurate exit price
        self.last_fill_prices: Dict[str, float] = {}  # {symbol: last_fill_price}

        # REST fallback metrics
        self.rest_fallback_count = 0
        self.rest_fallback_active = set()  # Symbols currently being polled via REST

        logger.info(f"BinanceHybridStream initialized (testnet={testnet}, pool=ON, state_machine=ON)")

    @property
    def connected(self) -> bool:
        """
        Check if hybrid stream is fully connected.

        Returns True only when BOTH streams are connected:
        - User Data Stream (position lifecycle)
        - Mark Price Pool (price updates via URL-based connections)
        """
        return self.user_connected and self.mark_price_pool.connected

    async def start(self):
        """Start both WebSocket streams"""
        if self.running:
            logger.warning("BinanceHybridStream already running")
            return

        self.running = True

        logger.info("🚀 Starting Binance Hybrid WebSocket...")

        # Create listen key first
        await self._create_listen_key()

        if not self.listen_key:
            logger.error("Failed to create listen key, cannot start")
            self.running = False
            return

        # Start User Data Stream (unchanged)
        self.user_task = asyncio.create_task(self._run_user_stream())
        self.keepalive_task = asyncio.create_task(self._keep_alive_loop())

        # ==================== NEW: Pool-based Mark Price Stream ====================
        # The MarkPriceConnectionPool replaces:
        #   - self.mark_task (_run_mark_stream)
        #   - self.subscription_task (_subscription_manager)
        #   - self.pending_processor_task (_process_pending_subscriptions_task)
        #   - self.reconnection_task (_periodic_reconnection_task)
        # Pool handles its own connections, reconnects, and heartbeats internally.
        # Symbols are added/removed via pool.set_symbols() when positions change.
        # =========================================================================

        # Legacy mark stream task — replaced by pool, kept as None
        # self.mark_task = asyncio.create_task(self._run_mark_stream())
        # self.subscription_task = asyncio.create_task(self._subscription_manager())
        # self.pending_processor_task = asyncio.create_task(
        #     self._process_pending_subscriptions_task(check_interval=120)
        # )

        # Periodic subscription health check (monitors SymbolStateManager)
        self.health_check_task = asyncio.create_task(
            self._periodic_health_check_task(interval_seconds=120)
        )

        # PHASE 4: WebSocket heartbeat monitoring (now only monitors User Stream;
        # Mark stream heartbeat is handled by pool connections internally)
        self.heartbeat_task = asyncio.create_task(
            self._heartbeat_monitoring_task(check_interval=30, mark_timeout=45, user_timeout=300)
        )

        # REST price fallback: polls via API when WS data is stale >3s
        self.rest_fallback_task = asyncio.create_task(
            self._rest_price_fallback_task()
        )

        # Initialize pool with any existing position symbols
        if self.positions:
            initial_symbols = {self._normalize_symbol(s) for s in self.positions.keys()}
            await self.mark_price_pool.set_symbols(initial_symbols)
            logger.info(f"📊 [POOL] Initialized with {len(initial_symbols)} symbols from existing positions")

        logger.info("✅ Binance Hybrid WebSocket started (pool-based mark stream)")

    async def stop(self):
        """Stop both WebSocket streams"""
        if not self.running:
            return

        logger.info("⏹️ Stopping Binance Hybrid WebSocket...")

        self.running = False

        # Stop mark price pool (handles all mark stream connections)
        await self.mark_price_pool.stop()

        # Close User WebSocket connection
        if self.user_ws and not self.user_ws.closed:
            await self.user_ws.close()

        # Close aiohttp sessions (User stream only; mark stream uses websockets via pool)
        if self.user_session and not self.user_session.closed:
            await self.user_session.close()

        # Legacy mark session cleanup (may exist from before pool migration)
        if self.mark_session and not self.mark_session.closed:
            await self.mark_session.close()

        # Cancel remaining tasks
        for task in [
            self.user_task,
            self.keepalive_task,
            self.health_check_task,
            self.heartbeat_task,
            self.rest_fallback_task,
            # Legacy tasks (should be None but safe to check)
            self.mark_task,
            self.subscription_task,
            self.reconnection_task,
            self.pending_processor_task,
        ]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Delete listen key
        if self.listen_key:
            await self._delete_listen_key()

        logger.info("✅ Binance Hybrid WebSocket stopped")

    def set_position_manager(self, position_manager):
        """Set position manager reference for health check"""
        self.position_manager = position_manager
        logger.info("✅ Position manager reference set for WebSocket health check")

    def set_reentry_callback(self, callback: Callable):
        """Set callback for ALL mark price updates (for reentry signals)"""
        self.reentry_price_callback = callback
        logger.info("✅ Reentry price callback set for WebSocket mark updates")

    async def sync_positions(self, positions: list):
        """
        Sync existing positions with WebSocket subscriptions

        Called after loading positions from DB to ensure
        Mark WS subscribes to all active positions.

        This fixes the cold start problem where positions exist
        but User WS doesn't send snapshot, so Mark WS never
        subscribes to tickers.

        Args:
            positions: List of position dicts with 'symbol' key
        """
        if not positions:
            logger.debug("No positions to sync")
            return

        logger.info(f"🔄 [MARK] Syncing {len(positions)} positions with WebSocket...")

        synced = 0
        for position in positions:
            symbol = position.get('symbol')
            if not symbol:
                logger.warning(f"Position missing symbol: {position}")
                continue

            try:
                # Store position data (minimal set for mark price subscription)
                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': position.get('side', 'LONG'),
                    'size': str(position.get('quantity', 0)),
                    'entry_price': str(position.get('entry_price', 0)),
                    'mark_price': str(position.get('current_price', 0)),
                }

                # Request mark price subscription
                await self._request_mark_subscription(symbol, subscribe=True)
                synced += 1

                # Small delay to avoid overwhelming the connection
                if synced < len(positions):
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to sync position {symbol}: {e}")

        logger.info(f"✅ [MARK] Synced {synced}/{len(positions)} positions with WebSocket")

    # ==================== LISTEN KEY MANAGEMENT ====================

    async def _create_listen_key(self):
        """Create listen key for User Data Stream"""
        try:
            headers = {'X-MBX-APIKEY': self.api_key}

            async with aiohttp.ClientSession() as session:
                url = f"{self.rest_url}/listenKey"
                async with session.post(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.listen_key = data['listenKey']
                        self.listen_key_expires = datetime.now()
                        logger.info(f"🔑 Listen key created: {self.listen_key[:10]}...")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"Failed to create listen key: {response.status} - {text}")
                        return False
        except Exception as e:
            logger.error(f"Error creating listen key: {e}")
            return False

    async def _refresh_listen_key(self):
        """Refresh listen key to keep it alive"""
        try:
            headers = {'X-MBX-APIKEY': self.api_key}

            async with aiohttp.ClientSession() as session:
                url = f"{self.rest_url}/listenKey"
                async with session.put(url, headers=headers) as response:
                    if response.status == 200:
                        self.listen_key_expires = datetime.now()
                        logger.info("🔑 Listen key refreshed")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"Failed to refresh listen key: {response.status} - {text}")
                        return False
        except Exception as e:
            logger.error(f"Error refreshing listen key: {e}")
            return False

    async def _delete_listen_key(self):
        """Delete listen key"""
        try:
            headers = {'X-MBX-APIKEY': self.api_key}

            async with aiohttp.ClientSession() as session:
                url = f"{self.rest_url}/listenKey"
                async with session.delete(url, headers=headers) as response:
                    if response.status == 200:
                        logger.info("🔑 Listen key deleted")
                        return True
                    else:
                        logger.error(f"Failed to delete listen key: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error deleting listen key: {e}")
            return False

    async def _keep_alive_loop(self):
        """Keep listen key alive by refreshing every 30 minutes"""
        logger.info("🔄 ListenKey keepalive loop started")
        while self.running:
            try:
                # Refresh every 30 minutes (Binance requirement)
                await asyncio.sleep(1800)  # 30 minutes

                logger.info("⏰ 30 minutes elapsed - refreshing listenKey...")
                if self.running and self.listen_key:
                    success = await self._refresh_listen_key()
                    if not success:
                        logger.warning("⚠️ Listen key refresh failed, recreating...")
                        await self._delete_listen_key()
                        created = await self._create_listen_key()
                        if created:
                            logger.info("🔑 Listen key recreated, restarting User stream...")
                            await self._restart_user_stream()
                        else:
                            logger.error("❌ Failed to recreate listen key!")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Keep alive error: {e}")

    async def _periodic_reconnection_task(self, interval_seconds: int = 600):
        """
        ✅ PHASE 2: Periodic prophylactic reconnection for Binance

        Reconnects mark price WebSocket every N seconds.
        User Data Stream uses listen key keepalive instead.

        Args:
            interval_seconds: Reconnection interval (default: 600s = 10min)
        """
        logger.info(
            f"🔄 [MARK] Starting periodic reconnection task (interval: {interval_seconds}s)"
        )

        while self.running:
            try:
                await asyncio.sleep(interval_seconds)

                if not self.running:
                    break

                # Only reconnect if we have active positions
                if not self.positions:
                    logger.debug("[MARK] No active positions, skipping reconnection")
                    continue

                logger.info(
                    f"🔄 [MARK] Periodic reconnection triggered "
                    f"({len(self.positions)} active positions)"
                )

                # Store current subscribed symbols
                symbols_backup = list(self.subscribed_symbols)

                # Gracefully close mark WebSocket
                if self.mark_ws and not self.mark_ws.closed:
                    logger.info("📤 [MARK] Closing WebSocket for reconnection...")
                    await self.mark_ws.close()
                    self.mark_connected = False

                # Wait for reconnection
                await asyncio.sleep(2)

                # Wait for reconnection to complete
                max_wait = 30
                waited = 0
                while not self.mark_connected and waited < max_wait:
                    await asyncio.sleep(1)
                    waited += 1

                if self.mark_connected:
                    logger.info("✅ [MARK] Periodic reconnection successful")

                    # Verify all subscriptions restored
                    missing = set(symbols_backup) - self.subscribed_symbols
                    if missing:
                        logger.warning(
                            f"⚠️ [MARK] {len(missing)} subscriptions not restored: {missing}"
                        )
                        # Trigger manual restore
                        for symbol in missing:
                            await self._request_mark_subscription(symbol, subscribe=True)
                else:
                    logger.error("❌ [MARK] Periodic reconnection failed - timeout")

            except asyncio.CancelledError:
                logger.info("[MARK] Periodic reconnection task cancelled")
                break
            except Exception as e:
                logger.error(f"[MARK] Error in periodic reconnection: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _periodic_health_check_task(self, interval_seconds: int = 120):
        """
        Periodic subscription health verification

        Checks every N seconds that all open positions have active or pending subscriptions.
        Recovers any subscriptions that were lost due to race conditions.

        Args:
            interval_seconds: Check interval (default: 120s = 2min)
        """
        logger.info(f"🏥 [MARK] Starting subscription health check task (interval: {interval_seconds}s)")

        while self.running:
            try:
                await asyncio.sleep(interval_seconds)

                if not self.running:
                    break

                # Run health verification
                await self._verify_subscriptions_health()

            except asyncio.CancelledError:
                logger.info("[MARK] Subscription health check task cancelled")
                break
            except Exception as e:
                logger.error(f"[MARK] Error in health check task: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _heartbeat_monitoring_task(self, check_interval: int = 30, mark_timeout: int = 45, user_timeout: int = 300, idle_stream_threshold: int = 120):
        """
        PHASE 4: WebSocket heartbeat monitoring

        Detects:
        1. Frozen WebSocket connections (alive but not sending data)
        2. Idle mark streams (0 subscriptions for extended period)
        3. ✅ FIX #6.2: Stuck "Connecting" state and dead tasks

        Args:
            check_interval: How often to check (default: 30s)
            mark_timeout: No-message threshold for Mark Stream (default: 45s)
            user_timeout: No-message threshold for User Stream (default: 300s)
            idle_stream_threshold: Threshold for stale data detection (default: 120s)
        """
        logger.info(f"💓 [HEARTBEAT] Starting WebSocket heartbeat monitoring (check: {check_interval}s, mark_timeout: {mark_timeout}s, user_timeout: {user_timeout}s)")

        # ✅ FIX #2.1: Track idle stream threshold
        IDLE_THRESHOLD = 300  # 5 minutes allowed without messages if 0 subscriptions
        
        # ✅ FIX #6.2: Track connection attempts
        last_connected_check = asyncio.get_event_loop().time()

        while self.running:
            try:
                await asyncio.sleep(check_interval)

                if not self.running:
                    break

                current_time = asyncio.get_event_loop().time()

                # --- CHECK 1: Mark Price Stream ---
                
                # A. Check if task is dead (crashed/exited)
                if self.mark_task and self.mark_task.done():
                    try:
                        exc = self.mark_task.exception()
                        logger.error(f"💀 [HEARTBEAT] Mark stream task DIED! Exception: {exc}")
                    except Exception:
                        logger.error("💀 [HEARTBEAT] Mark stream task DIED (no exception)")
                    
                    await self._restart_mark_stream()
                    last_connected_check = current_time # Reset timer
                    continue

                # B. Check if stuck in "Connecting" state
                if not self.mark_connected:
                    time_disconnected = current_time - last_connected_check
                    if time_disconnected > 60.0: # 60s grace period for connection
                        logger.error(f"🔒 [HEARTBEAT] Mark stream stuck in CONNECTING for {time_disconnected:.1f}s. Forcing restart...")
                        await self._restart_mark_stream()
                        last_connected_check = current_time
                    continue
                else:
                    last_connected_check = current_time # Reset when connected

                # C. Check for frozen connection (connected but no data)
                mark_silence = current_time - self.last_mark_message_time
                
                # If we have subscriptions, we MUST receive data
                has_subscriptions = len(self.subscribed_symbols) > 0 or len(self.pending_subscriptions) > 0
                
                effective_timeout = mark_timeout if has_subscriptions else IDLE_THRESHOLD

                if mark_silence > effective_timeout:
                    if has_subscriptions:
                        logger.warning(
                            f"💔 [HEARTBEAT] Mark stream frozen! "
                            f"No messages for {mark_silence:.1f}s (threshold: {mark_timeout}s). "
                            f"Forcing reconnect..."
                        )
                        self.mark_connected = False
                        # Force-close WS to break async for loop (fas_smart pattern)
                        if self.mark_ws:
                            try:
                                await self.mark_ws.close()
                            except Exception:
                                pass
                # ✅ FIX #2.3: Track last price data update (not just any message)
                # This detects subscription failure (connected, subscriptions sent, but no data)
                if self.mark_connected and len(self.subscribed_symbols) > 0:
                    # Check when we last received actual price data
                    newest_price_time = 0.0
                    for symbol in self.subscribed_symbols:
                        price_age = self._get_data_age(symbol)
                        if price_age > 0:  # Has data
                            price_time = current_time - price_age
                            newest_price_time = max(newest_price_time, price_time)

                    if newest_price_time > 0:
                        data_silence = current_time - newest_price_time
                        if data_silence > idle_stream_threshold:
                            logger.error(
                                f"🚨 [HEARTBEAT] STALE DATA DETECTED! "
                                f"Mark stream connected, {len(self.subscribed_symbols)} subscriptions, "
                                f"but no fresh price data for {data_silence:.1f}s. "
                                f"Forcing reconnect..."
                            )
                            self.mark_connected = False
                            # Force-close WS to break async for loop
                            if self.mark_ws:
                                try:
                                    await self.mark_ws.close()
                                except Exception:
                                    pass

                # --- CHECK 2: User Data Stream ---
                
                # A. Check if User task is dead (crashed/exited)
                if self.user_task and self.user_task.done():
                    try:
                        exc = self.user_task.exception()
                        logger.error(f"💀 [HEARTBEAT] User stream task DIED! Exception: {exc}")
                    except Exception:
                        logger.error("💀 [HEARTBEAT] User stream task DIED (no exception)")
                    
                    await self._restart_user_stream()
                    continue
                
                # B. Check if User stream stuck in "Connecting" state
                # (Note: User stream doesn't track last_connected_check separately, 
                #  but frozen detection below handles stuck connections)
                
                # C. Check for frozen User connection (connected but no data)
                if self.user_connected and self.last_user_message_time > 0:
                    user_silence = current_time - self.last_user_message_time
                    # User Stream is mostly silent, so we use a much larger timeout (e.g. 5 mins)
                    # and rely on aiohttp heartbeat for connection health
                    if user_silence > user_timeout:
                        logger.warning(
                            f"💔 [HEARTBEAT] User stream frozen! "
                            f"No messages for {user_silence:.1f}s (threshold: {user_timeout}s). "
                            f"Forcing restart..."
                        )
                        # ✅ FIX: Active restart instead of just setting flag!
                        await self._restart_user_stream()

            except asyncio.CancelledError:
                logger.info("[HEARTBEAT] Heartbeat monitoring task cancelled")
                break
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error in heartbeat monitoring: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _process_pending_subscriptions_task(self, check_interval: int = 120):
        """
        ✅ FIX #3: Periodic pending processor

        Periodically checks and processes pending subscriptions.
        This handles edge cases where FIX #1/#2 might miss pending symbols.

        Args:
            check_interval: How often to check pending (default: 120s = 2 minutes)
        """
        logger.info(f"⏰ [PENDING] Starting periodic pending processor (check: {check_interval}s)")

        while self.running:
            try:
                await asyncio.sleep(check_interval)

                if not self.running:
                    break

                # ✅ FIX #3.1: Check if there are pending subscriptions
                num_pending = len(self.pending_subscriptions)

                if num_pending == 0:
                    # No pending subscriptions - nothing to do
                    logger.debug("[PENDING] No pending subscriptions to process")
                    continue

                # ✅ FIX #3.2: Only process if stream is connected
                if not self.mark_connected:
                    logger.warning(
                        f"⏳ [PENDING] Mark stream disconnected, "
                        f"deferring {num_pending} pending subscriptions until reconnect"
                    )
                    continue

                # ✅ FIX #3.3: Attempt to process pending subscriptions
                logger.info(
                    f"🔄 [PENDING] Processing {num_pending} pending subscriptions "
                    f"(periodic check)"
                )

                try:
                    # FIX 2026-01-11: Don't use _restore_subscriptions() here!
                    # It clears ALL subscriptions and forces a full reconnect/resubscribe cycle.
                    # Instead, iterate and subscribe individually only for pending items.
                    pending_list = list(self.pending_subscriptions)
                    
                    for symbol in pending_list:
                        logger.info(f"🔄 [PENDING] Retry subscribing to {symbol}")
                        await self._subscribe_mark_price(symbol)
                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.2)

                    logger.info(
                        f"✅ [PENDING] Processed {num_pending} pending subscriptions "
                        f"(remaining: {len(self.pending_subscriptions)})"
                    )
                except Exception as e:
                    logger.error(
                        f"❌ [PENDING] Failed to process pending subscriptions: {e}",
                        exc_info=True
                    )
                    # Continue running despite errors

            except asyncio.CancelledError:
                logger.info("[PENDING] Pending processor task cancelled")
                break
            except Exception as e:
                logger.error(f"[PENDING] Error in pending processor: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying on error

    # ==================== USER DATA STREAM ====================

    async def _run_user_stream(self):
        """Run User Data Stream for position lifecycle"""
        reconnect_count = 0

        while self.running:
            try:
                url = f"{self.user_ws_url}/{self.listen_key}"

                logger.info("🔐 [USER] Connecting...")

                # Create session if needed
                if not self.user_session or self.user_session.closed:
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    self.user_session = aiohttp.ClientSession(timeout=timeout)

                # Connect
                self.user_ws = await self.user_session.ws_connect(
                    url,
                    heartbeat=30.0,  # Send PING every 30s to keep connection alive
                    autoping=True,   # Automatically reply to server PINGs (and handle PONGs)
                    autoclose=False
                )

                self.user_connected = True
                reconnect_count = 0  # Reset on successful connection
                logger.info("✅ [USER] Connected")

                # ✅ FIX: Sync state with snapshot on reconnect
                # This handles positions opened while disconnected
                await self._sync_state_with_snapshot()

                # Receive loop
                async for msg in self.user_ws:
                    if not self.running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = _json_loads(msg.data)
                            await self._handle_user_message(data)
                        except (ValueError, Exception) as e:
                            logger.error(f"[USER] JSON decode error: {e}")
                        except Exception as e:
                            logger.error(f"[USER] Message handling error: {e}")

                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("[USER] WebSocket closed by server")
                        break

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("[USER] WebSocket error")
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [USER] Connection error: {e}")

            finally:
                self.user_connected = False

                if self.running:
                    reconnect_count += 1
                    delay = min(1.0 * (2 ** (reconnect_count - 1)), 60.0)
                    jitter = delay * 0.25 * (2 * random.random() - 1)
                    actual_delay = delay + jitter
                    logger.info(f"[USER] Reconnecting in {actual_delay:.1f}s (attempt {reconnect_count})...")
                    await asyncio.sleep(actual_delay)

    async def _handle_user_message(self, data: Dict):
        """Handle User Data Stream message"""
        # PHASE 4: Update heartbeat timestamp
        self.last_user_message_time = asyncio.get_event_loop().time()

        event_type = data.get('e')

        if event_type == 'ACCOUNT_UPDATE':
            await self._on_account_update(data)
        elif event_type == 'listenKeyExpired':
            logger.warning("[USER] Listen key expired, reconnecting...")
            self.user_connected = False
            # Recreate listen key
            await self._create_listen_key()
        elif event_type == 'ORDER_TRADE_UPDATE':
            await self._handle_order_update(data)

    async def _on_account_update(self, data: Dict):
        """
        Handle ACCOUNT_UPDATE event with position updates

        Triggers:
        - Position opened (size > 0) → Subscribe to mark price
        - Position closed (size = 0) → Unsubscribe
        - Position modified → Update position data
        """
        account_data = data.get('a', {})
        positions = account_data.get('P', [])

        for pos in positions:
            symbol = pos.get('s')
            position_amt = float(pos.get('pa', 0))

            logger.info(f"📊 [USER] Position update: {symbol} amount={position_amt}")

            if position_amt != 0:
                # Position active - store and subscribe to mark price
                side = 'LONG' if position_amt > 0 else 'SHORT'

                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': side,
                    'size': str(abs(position_amt)),
                    'entry_price': pos.get('ep', '0'),
                    'unrealized_pnl': pos.get('up', '0'),
                    'margin_type': pos.get('mt', 'cross'),
                    'position_side': pos.get('ps', 'BOTH'),
                    'mark_price': self.mark_prices.get(symbol, '0')  # Use cached if available
                }

                # Request mark price subscription
                await self._request_mark_subscription(symbol, subscribe=True)

                # Emit initial event
                await self._emit_combined_event(symbol, self.positions[symbol])

            else:
                # Position closed - remove and unsubscribe
                if symbol in self.positions:
                    # CRITICAL FIX: Emit closure event BEFORE deleting position
                    position_data = self.positions[symbol].copy()
                    position_data['size'] = '0'
                    position_data['position_amt'] = 0

                    # FIX #2: Use cached fill price from ORDER_TRADE_UPDATE instead of mark_price
                    if symbol in self.last_fill_prices:
                        fill_price = self.last_fill_prices.pop(symbol)
                        position_data['fill_price'] = str(fill_price)
                        logger.info(f"💰 [USER] Using fill price for {symbol} exit: ${fill_price}")

                    # Emit closure event to position_manager
                    await self._emit_combined_event(symbol, position_data)
                    logger.info(f"📤 [USER] Emitted closure event for {symbol}")

                    # Now safe to delete from local tracking
                    del self.positions[symbol]
                    logger.info(f"❌ [USER] Position closed: {symbol}")

                # Request mark price unsubscription
                await self._request_mark_subscription(symbol, subscribe=False)

    async def _handle_order_update(self, data: Dict):
        """
        Handle ORDER_TRADE_UPDATE event from User Data Stream.

        Parses order fields, logs important state transitions (SL/TP triggers),
        and emits 'order.update' event via event_handler for consumers.

        Ported from websocket/binance_stream.py:_handle_order_update
        """
        order_data = data.get('o', {})
        if not order_data:
            return

        order_info = {
            'symbol': order_data.get('s', ''),
            'order_id': order_data.get('i'),
            'client_order_id': order_data.get('c'),
            'side': order_data.get('S', ''),
            'type': order_data.get('o', ''),
            'time_in_force': order_data.get('f'),
            'quantity': float(order_data.get('q', 0)),
            'price': float(order_data.get('p', 0)),
            'stop_price': float(order_data.get('sp', 0)),
            'execution_type': order_data.get('x', ''),
            'status': order_data.get('X', ''),
            'reject_reason': order_data.get('r'),
            'filled_quantity': float(order_data.get('z', 0)),
            'last_filled_quantity': float(order_data.get('l', 0)),
            'average_price': float(order_data.get('ap', 0)),
            'commission': float(order_data.get('n', 0)),
            'commission_asset': order_data.get('N'),
            'timestamp': order_data.get('T'),
            'is_reduce_only': order_data.get('R', False),
            'is_close_position': order_data.get('cp', False),
            'activation_price': float(order_data.get('AP', 0)),
            'callback_rate': float(order_data.get('cr', 0)),
            'realized_profit': float(order_data.get('rp', 0)),
        }

        symbol = order_info['symbol']
        status = order_info['status']
        order_type = order_info['type']

        # Log important order events
        if status == 'NEW':
            logger.info(
                f"[ORDER] New: {symbol} {order_info['side']} {order_type}"
            )
        elif status == 'FILLED':
            logger.info(
                f"[ORDER] Filled: {symbol} {order_info['side']} "
                f"@ {order_info['average_price']}"
            )

            # FIX #2: Cache fill price for accurate exit price recording
            if order_info['average_price'] > 0:
                self.last_fill_prices[symbol] = order_info['average_price']
                logger.info(f"💰 [ORDER] Cached fill price for {symbol}: ${order_info['average_price']}")

            # Detect SL/TP triggers
            if order_type in ('STOP_MARKET', 'STOP'):
                logger.warning(
                    f"⚠️ STOP LOSS TRIGGERED: {symbol} "
                    f"{order_info['side']} @ {order_info['average_price']}"
                )
            elif order_type == 'TAKE_PROFIT_MARKET':
                logger.info(
                    f"✅ TAKE PROFIT TRIGGERED: {symbol} "
                    f"{order_info['side']} @ {order_info['average_price']}"
                )
        elif status == 'CANCELED':
            logger.info(f"[ORDER] Cancelled: {symbol} #{order_info['order_id']}")
        elif status == 'EXPIRED':
            logger.warning(f"[ORDER] Expired: {symbol} #{order_info['order_id']}")
        elif status == 'REJECTED':
            logger.error(
                f"[ORDER] Rejected: {symbol} #{order_info['order_id']} "
                f"reason={order_info['reject_reason']}"
            )

        # Emit order update event for consumers
        if self.event_handler:
            try:
                await self.event_handler('order.update', order_info)
            except Exception as e:
                logger.error(f"Order event emission error: {e}")

    async def _sync_state_with_snapshot(self):
        """
        Sync internal state with position snapshot from exchange.
        
        Called on (re)connection to detect positions opened while disconnected.
        """
        if not self.position_fetch_callback:
            logger.warning("⚠️ [USER] No position_fetch_callback configured - skipping snapshot sync")
            return

        try:
            logger.info("🔄 [USER] Syncing state with snapshot...")
            
            # Fetch active positions via callback (REST API)
            # Expected format: List of dicts with 'symbol', 'positionAmt'/'contracts', etc.
            positions = await self.position_fetch_callback()
            
            if not positions:
                logger.info("✅ [USER] Snapshot sync: No active positions")
                return

            synced_count = 0
            for pos in positions:
                symbol = pos.get('symbol')
                if not symbol:
                    continue
                    
                # Normalize data
                # Binance 'positionAmt', Bybit 'size'/'contracts'
                amount = float(pos.get('positionAmt') or pos.get('contracts') or pos.get('size') or 0)
                
                if amount == 0:
                    continue
                    
                # Update internal state
                side = 'LONG' if amount > 0 else 'SHORT'
                
                # Store position data
                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': side,
                    'size': str(abs(amount)),
                    'entry_price': str(pos.get('entryPrice') or pos.get('avgPrice') or 0),
                    'unrealized_pnl': str(pos.get('unrealizedProfit') or pos.get('unrealizedPnl') or 0),
                    'mark_price': self.mark_prices.get(symbol, '0')
                }
                
                # Ensure mark price subscription is active
                entry = self.symbol_state.get_entry(symbol)
                if not entry or entry.state not in (SymbolState.SUBSCRIBED, SymbolState.SUBSCRIBING):
                    logger.info(f"➕ [USER] Found missing subscription for {symbol} in snapshot")
                    await self._request_mark_subscription(symbol, subscribe=True)
                
                synced_count += 1
                
            logger.info(f"✅ [USER] Snapshot sync complete: {synced_count} positions synced")
            
        except Exception as e:
            logger.error(f"❌ [USER] Snapshot sync failed: {e}")

    # ==================== MARK PRICE STREAM ====================

    async def _run_mark_stream(self):
        """Run Mark Price Stream (combined stream for all subscribed symbols)"""
        reconnect_count = 0

        while self.running:
            try:
                # Binance combined streams use /stream endpoint
                url = f"{self.mark_ws_url}/stream"

                logger.info("🌐 [MARK] Connecting...")

                # Create session if needed
                if not self.mark_session or self.mark_session.closed:
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    self.mark_session = aiohttp.ClientSession(timeout=timeout)

                # Connect
                self.mark_ws = await self.mark_session.ws_connect(
                    url,
                    heartbeat=20,
                    autoping=True,
                    autoclose=False
                )

                self.mark_connected = True
                reconnect_count = 0  # Reset on successful connection
                logger.info("✅ [MARK] Connected")

                # Restore subscriptions after reconnect
                await self._restore_subscriptions()

                async for msg in self.mark_ws:
                    if not self.running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = _json_loads(msg.data)
                            await self._handle_mark_message(data)
                        except (ValueError, Exception) as e:
                            logger.error(f"[MARK] JSON decode error: {e}")
                        except Exception as e:
                            logger.error(f"[MARK] Message handling error: {e}")

                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("[MARK] WebSocket closed by server")
                        break

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("[MARK] WebSocket error")
                        break

            except asyncio.TimeoutError:
                logger.error("❌ [MARK] Connection timed out (handshake > 15s)")
                # Loop will retry automatically
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [MARK] Connection error: {e}")

            finally:
                self.mark_connected = False

                if self.running:
                    reconnect_count += 1
                    delay = min(1.0 * (2 ** (reconnect_count - 1)), 60.0)
                    jitter = delay * 0.25 * (2 * random.random() - 1)
                    actual_delay = delay + jitter
                    logger.info(f"[MARK] Reconnecting in {actual_delay:.1f}s (attempt {reconnect_count})...")
                    await asyncio.sleep(actual_delay)

    async def _restart_mark_stream(self):
        """
        ✅ FIX #6.3: Explicit task restart
        
        Cleanly cancels the old task and starts a new one.
        Used when the task is stuck or crashed.
        """
        logger.warning("🔄 [MARK] Forcing restart of Mark Price Stream task...")
        
        # 1. Cancel existing task
        if self.mark_task and not self.mark_task.done():
            self.mark_task.cancel()
            try:
                await self.mark_task
            except asyncio.CancelledError:
                pass
                
        # 2. Close existing socket/session if open
        if self.mark_ws and not self.mark_ws.closed:
            await self.mark_ws.close()
            
        # 3. Start new task
        self.mark_task = asyncio.create_task(self._run_mark_stream())
        logger.info("✅ [MARK] Mark Price Stream task restarted")

    async def _restart_user_stream(self):
        """
        ✅ Force restart of User Data Stream task
        
        Mirrors _restart_mark_stream() logic for User stream.
        Called when heartbeat detects frozen connection.
        """
        logger.warning("🔄 [USER] Forcing restart of User Data Stream task...")
        
        # 0. Reset heartbeat state BEFORE restart to prevent re-triggering
        self.user_connected = False
        self.last_user_message_time = 0.0
        
        # 1. Cancel existing task
        if self.user_task and not self.user_task.done():
            self.user_task.cancel()
            try:
                await self.user_task
            except asyncio.CancelledError:
                pass
        
        # 2. Close existing socket/session if open
        if self.user_ws and not self.user_ws.closed:
            await self.user_ws.close()
        
        # 3. Refresh listen key (may have expired during freeze)
        await self._create_listen_key()
        
        # 4. Start new task
        self.user_task = asyncio.create_task(self._run_user_stream())
        logger.info("✅ [USER] User Data Stream task restarted")

    # ==================== POOL CALLBACK BRIDGE ====================

    async def _on_pool_price_update(self, data: Dict):
        """
        Callback from MarkPriceConnectionPool.
        
        Bridges the pool's raw markPriceUpdate data into the existing
        pipeline (_on_mark_price_update, reentry callbacks, etc.).
        
        This is the ONLY entry point for mark price data in the new architecture.
        """
        # Update legacy heartbeat timestamp (used by _heartbeat_monitoring_task)
        self.last_mark_message_time = asyncio.get_event_loop().time()
        
        # Route to the existing handler
        event_type = data.get('e')
        if event_type == 'markPriceUpdate':
            symbol = data.get('s')
            price = data.get('p')
            
            # Update SymbolStateManager
            if symbol and price:
                self.symbol_state.record_ws_update(symbol, price)
                # Sync legacy sets for backward compatibility
                self.subscribed_symbols = self.symbol_state.subscribed_symbols
                self.pending_subscriptions = self.symbol_state.pending_symbols
                # Update legacy mark_connected flag
                self.mark_connected = True

            await self._on_mark_price_update(data)

    async def _handle_mark_message(self, data: Dict):
        """
        Handle Mark Price Stream message (LEGACY — kept for backward compatibility).
        
        In the new architecture, mark data flows through _on_pool_price_update().
        This method is only used if the old _run_mark_stream() is still active.
        """
        # PHASE 4: Update heartbeat timestamp
        self.last_mark_message_time = asyncio.get_event_loop().time()

        # Handle subscription responses
        if 'result' in data and 'id' in data:
            if data['result'] is None:
                logger.debug(f"[MARK] Subscription confirmed: ID {data['id']}")
            else:
                logger.warning(f"[MARK] Subscription response: {data}")
            return

        # Handle mark price updates
        event_type = data.get('e')

        if event_type == 'markPriceUpdate':
            await self._on_mark_price_update(data)

    async def _on_mark_price_update(self, data: Dict):
        """Handle mark price update"""
        symbol = data.get('s')
        mark_price = data.get('p')

        if not symbol or not mark_price:
            return

        # Update mark price cache
        self.mark_prices[symbol] = mark_price
        # PHASE 1: Track timestamp for data freshness monitoring
        self.mark_prices[f"{symbol}_timestamp"] = asyncio.get_event_loop().time()
        
        # CRITICAL FIX 2026-01-03: Forward ALL mark prices to reentry monitoring
        # This ensures closed positions (reentry signals) receive price updates
        if self.reentry_price_callback:
            try:
                await self.reentry_price_callback(symbol, mark_price)
            except Exception as e:
                logger.warning(f"Reentry price callback error for {symbol}: {e}")

        # If we have position data, emit combined event
        if symbol in self.positions:
            position_data = self.positions[symbol].copy()
            position_data['mark_price'] = mark_price

            # ========== Calculate unrealized_pnl ==========
            try:
                entry_price = float(position_data.get('entry_price', 0))
                size = float(position_data.get('size', 0))
                side = position_data.get('side', 'LONG')
                mark_price_float = float(mark_price)

                if entry_price > 0 and size > 0:
                    if side == 'LONG':
                        unrealized_pnl = (mark_price_float - entry_price) * size
                    else:  # SHORT
                        unrealized_pnl = (entry_price - mark_price_float) * size

                    position_data['unrealized_pnl'] = str(unrealized_pnl)

                    logger.debug(
                        f"💰 [MARK] {symbol} PnL recalculated: "
                        f"${unrealized_pnl:.4f} (entry={entry_price}, mark={mark_price_float}, size={size})"
                    )
                else:
                    position_data['unrealized_pnl'] = '0'

            except (ValueError, TypeError) as e:
                logger.error(f"Failed to calculate unrealized_pnl for {symbol}: {e}")
                position_data['unrealized_pnl'] = '0'
            # ==============================================

            # Update position cache
            self.positions[symbol]['mark_price'] = mark_price
            self.positions[symbol]['unrealized_pnl'] = position_data['unrealized_pnl']

            # Emit combined event
            await self._emit_combined_event(symbol, position_data)

            logger.debug(f"💰 [MARK] Price update: {symbol} @ ${mark_price}")

    # ==================== SUBSCRIPTION MANAGEMENT ====================

    async def _subscription_manager(self):
        """Background task to manage mark price subscriptions"""
        while self.running:
            try:
                # Get subscription request from queue (with timeout)
                try:
                    symbol, subscribe = await asyncio.wait_for(
                        self.subscription_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # ✅ FIX #1.1: ВСЕГДА добавляем подписки в pending для отложенной обработки
                if subscribe:
                    if symbol not in self.pending_subscriptions:
                        self.pending_subscriptions.add(symbol)
                        logger.debug(f"[MARK] Added {symbol} to pending subscriptions (total pending: {len(self.pending_subscriptions)})")

                # ✅ FIX #1.2: Попытка подписаться немедленно (если stream активен)
                if self.mark_connected and self.mark_ws and not self.mark_ws.closed:
                    if subscribe:
                        await self._subscribe_mark_price(symbol)
                    else:
                        await self._unsubscribe_mark_price(symbol)
                else:
                    # ✅ FIX #1.3: Логирование отложенных подписок для диагностики
                    if subscribe:
                        logger.warning(
                            f"⏳ [MARK] Stream disconnected, {symbol} subscription deferred "
                            f"(pending: {len(self.pending_subscriptions)} symbols). "
                            f"Will retry after reconnect."
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MARK] Subscription manager error: {e}", exc_info=True)

    async def subscribe_symbol(self, symbol: str, position_data: dict = None):
        """
        Public method to subscribe to mark price stream for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT' or 'BTC/USDT:USDT')
            position_data: Optional dict with position info (side, quantity, entry_price)
                          If provided, populates self.positions to handle ACCOUNT_UPDATE delays
        """
        # Normalize symbol first
        normalized_symbol = self._normalize_symbol(symbol)
        
        # CRITICAL FIX: Populate self.positions if data provided and not already present
        # This ensures mark price updates trigger combined events even if ACCOUNT_UPDATE is delayed
        if position_data and normalized_symbol not in self.positions:
            self.positions[normalized_symbol] = {
                'symbol': normalized_symbol,
                'side': position_data.get('side', 'LONG'),
                'size': str(position_data.get('quantity', 0)),
                'entry_price': str(position_data.get('entry_price', 0)),
                'mark_price': self.mark_prices.get(normalized_symbol, '0'),
                'unrealized_pnl': '0'
            }
            logger.info(f"📊 [MARK] Position cache populated for {normalized_symbol} (ACCOUNT_UPDATE bypass)")
        
        await self._request_mark_subscription(symbol)

    async def _request_mark_subscription(self, symbol: str, subscribe: bool = True):
        """
        Request mark price subscription/unsubscription via connection pool.
        
        NEW ARCHITECTURE: Routes through MarkPriceConnectionPool.add_symbol/remove_symbol
        and SymbolStateManager instead of the old subscription queue.
        """
        # Normalize symbol to ensure consistency (handle unified symbols)
        symbol = self._normalize_symbol(symbol)
        
        if subscribe:
            # Add to state manager
            self.symbol_state.add(symbol)
            self.symbol_state.mark_subscribing(symbol)
            
            # Add to pool (triggers URL rebuild if needed)
            await self.mark_price_pool.add_symbol(symbol)
            
            logger.debug(f"[POOL] Subscription added: {symbol}")
        else:
            # Remove from state manager
            self.symbol_state.remove(symbol)
            
            # Remove from pool
            await self.mark_price_pool.remove_symbol(symbol)
            
            logger.debug(f"[POOL] Subscription removed: {symbol}")
        
        # Sync legacy sets
        self.subscribed_symbols = self.symbol_state.subscribed_symbols
        self.pending_subscriptions = self.symbol_state.pending_symbols

    async def _subscribe_mark_price(self, symbol: str):
        """Subscribe to mark price stream for symbol"""
        if symbol in self.subscribed_symbols:
            # Already subscribed — clear from pending to prevent infinite retry loop
            self.pending_subscriptions.discard(symbol)
            logger.debug(f"[MARK] Already subscribed to {symbol}")
            return

        try:
            # Binance format: btcusdt@markPrice@1s
            stream_name = f"{symbol.lower()}@markPrice@1s"

            message = {
                "method": "SUBSCRIBE",
                "params": [stream_name],
                "id": self.next_request_id
            }

            # Add timeout to prevent hanging on send
            await asyncio.wait_for(
                self.mark_ws.send_str(_json_dumps(message)),
                timeout=5.0
            )

            self.subscribed_symbols.add(symbol)
            self.pending_subscriptions.discard(symbol)  # Clear from pending after successful subscription
            self.next_request_id += 1

            # Initialize timestamp so REST fallback doesn't report bogus WS gaps
            ts_key = f"{symbol}_timestamp"
            if ts_key not in self.mark_prices:
                self.mark_prices[ts_key] = asyncio.get_event_loop().time()

            logger.info(f"✅ [MARK] Subscribed to {symbol} (pending cleared)")

        except Exception as e:
            logger.error(f"[MARK] Subscription error for {symbol}: {e}")

    def _normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol to Binance raw format
        e.g. 'BTC/USDT:USDT' -> 'BTCUSDT'
        """
        from utils.symbol_helpers import normalize_symbol
        return normalize_symbol(symbol)

    async def _restore_subscriptions(self):
        """
        Restore all mark price subscriptions after reconnect

        HYBRID APPROACH (based on test results):
        1. First 30 symbols: OPTIMISTIC (no verification, fast)
        2. Remaining symbols: OPTIMISTIC (все быстро)
        3. 60s warmup period (let data start flowing)
        4. Verification of all subscriptions (background, non-blocking)

        This approach prevents event loop blocking while ensuring
        subscriptions are actually working.
        """
        # Combine confirmed and pending subscriptions
        all_symbols = self.subscribed_symbols.union(self.pending_subscriptions)

        if not all_symbols:
            logger.debug("[MARK] No subscriptions to restore")
            return

        symbols_to_restore = list(all_symbols)
        total_symbols = len(symbols_to_restore)

        logger.info(
            f"🔄 [MARK] Restoring {total_symbols} subscriptions "
            f"({len(self.subscribed_symbols)} confirmed + {len(self.pending_subscriptions)} pending)..."
        )

        # Clear both sets to allow resubscribe
        self.subscribed_symbols.clear()
        self.pending_subscriptions.clear()

        # FIX 1.3: Don't destroy price data on reconnect! Mark timestamps as stale.
        # Trailing stops and REST fallback need SOME price to work with during 90s warmup.
        # Fresh WS data will overwrite stale values once streams resume.
        for key in list(self.mark_prices.keys()):
            if key.endswith('_timestamp'):
                self.mark_prices[key] = 0  # Mark as stale — REST fallback will kick in
        logger.debug(f"[MARK] Marked {total_symbols} symbols as stale (prices preserved)")

        # PHASE 1: OPTIMISTIC SUBSCRIPTIONS (all symbols, fast)
        logger.info(f"📤 [MARK] Sending {total_symbols} OPTIMISTIC subscriptions...")
        restored = 0
        for symbol in symbols_to_restore:
            try:
                success = await self._verify_subscription_optimistic(symbol)
                if success:
                    restored += 1

                # Small delay to avoid overwhelming the connection
                if restored < total_symbols:
                    await asyncio.sleep(0.2)

            except Exception as e:
                logger.error(f"❌ [MARK] Failed to restore subscription for {symbol}: {e}")

        logger.info(f"✅ [MARK] Sent {restored}/{total_symbols} subscription requests")

        # PHASE 3: NON-BLOCKING WARMUP AND VERIFICATION
        # Run warmup + verification in background to avoid blocking new subscriptions
        if restored > 0:
            logger.info(f"⏳ [MARK] Starting non-blocking warmup (90s) and verification...")

            async def warmup_and_verify():
                """Combined warmup and verification in background task"""
                try:
                    # WARMUP: Wait for data to start flowing (90s due to observed 72s delay)
                    await asyncio.sleep(90.0)
                    logger.info(f"✅ [MARK] Warmup complete, starting verification...")

                    # VERIFICATION: Check that subscriptions are working
                    result = await self._verify_all_subscriptions_active(timeout=60.0)

                    if result['success_rate'] < 90:
                        logger.warning(
                            f"⚠️ [MARK] Low verification rate: {result['success_rate']:.1f}%\n"
                            f"   Verified: {len(result['verified'])}\n"
                            f"   Failed: {len(result['failed'])}\n"
                            f"   Failed symbols: {result['failed']}"
                        )
                    else:
                        logger.info(
                            f"✅ [MARK] Subscription health: {result['success_rate']:.1f}% "
                            f"({len(result['verified'])}/{result['total']})"
                        )
                except Exception as e:
                    logger.error(f"❌ [MARK] Background verification error: {e}")

            # Run in background, don't await (allows new subscriptions during warmup)
            asyncio.create_task(warmup_and_verify())

    async def _verify_subscription_optimistic(self, symbol: str) -> bool:
        """
        Subscribe WITHOUT verification (optimistic approach)

        Used for initial subscriptions during reconnect to avoid blocking.
        Data will start flowing after 20-60 seconds warmup period.
        Health check will verify data receipt later.

        Args:
            symbol: Symbol to subscribe to

        Returns:
            bool: True if subscription request sent successfully
        """
        try:
            await self._subscribe_mark_price(symbol)
            logger.info(f"📤 [MARK] OPTIMISTIC subscribe: {symbol}")
            return True
        except Exception as e:
            logger.error(f"❌ [MARK] Failed optimistic subscribe {symbol}: {e}")
            return False

    async def _verify_subscription_event_based(self, symbol: str, timeout: float = 10.0) -> bool:
        """
        Subscribe with EVENT-BASED verification (NON-BLOCKING!)

        Waits for actual markPriceUpdate event to confirm subscription is working.
        Uses asyncio.Event for non-blocking wait.

        Args:
            symbol: Symbol to subscribe to
            timeout: Seconds to wait for first price update

        Returns:
            bool: True if verified (data received), False if timeout
        """
        # Create event for this subscription
        verification_event = asyncio.Event()

        # Store current price count to detect new data
        initial_count = len(self.mark_prices.get(symbol, ""))

        # Helper to check for new data
        def check_new_data():
            return symbol in self.mark_prices and len(self.mark_prices[symbol]) > initial_count

        try:
            # Send subscription request
            await self._subscribe_mark_price(symbol)
            start_time = asyncio.get_event_loop().time()

            # Wait for data with timeout
            deadline = start_time + timeout
            while asyncio.get_event_loop().time() < deadline:
                if check_new_data():
                    elapsed = asyncio.get_event_loop().time() - start_time
                    logger.info(f"✅ [MARK] VERIFIED: {symbol} (data in {elapsed:.1f}s)")
                    return True

                await asyncio.sleep(0.5)  # Check every 500ms

            # Timeout - no data received
            logger.warning(f"🚨 [MARK] SILENT FAIL: {symbol} (timeout {timeout}s)")
            return False

        except Exception as e:
            logger.error(f"❌ [MARK] Verification error {symbol}: {e}")
            return False

    async def _verify_all_subscriptions_active(self, timeout: float = 60.0) -> dict:
        """
        Verify that ALL subscriptions are receiving data after reconnect

        NON-BLOCKING: Waits for data from all symbols in parallel.
        Used after _restore_subscriptions() to ensure no silent fails.

        Args:
            timeout: Maximum seconds to wait for all subscriptions

        Returns:
            dict: {
                'verified': set of verified symbols,
                'failed': set of symbols without data,
                'total': total symbols checked,
                'success_rate': percentage verified
            }
        """
        if not self.subscribed_symbols and not self.pending_subscriptions:
            logger.debug("[MARK] No subscriptions to verify")
            return {
                'verified': set(),
                'failed': set(),
                'total': 0,
                'success_rate': 100.0
            }

        all_symbols = self.subscribed_symbols.union(self.pending_subscriptions)
        total_symbols = len(all_symbols)

        logger.info(f"🔍 [MARK] Verifying {total_symbols} subscriptions (timeout: {timeout}s)...")

        # Track which symbols have received data
        verified_symbols = set()
        start_time = asyncio.get_event_loop().time()
        deadline = start_time + timeout

        # Wait for data from all symbols
        while asyncio.get_event_loop().time() < deadline:
            # Check which symbols have data
            for symbol in all_symbols:
                if symbol in self.mark_prices and symbol not in verified_symbols:
                    verified_symbols.add(symbol)
                    logger.debug(f"✓ [MARK] {symbol} verified ({len(verified_symbols)}/{total_symbols})")

            # All verified?
            if len(verified_symbols) == total_symbols:
                elapsed = asyncio.get_event_loop().time() - start_time
                logger.info(f"✅ [MARK] ALL {total_symbols} subscriptions verified in {elapsed:.1f}s")
                return {
                    'verified': verified_symbols,
                    'failed': set(),
                    'total': total_symbols,
                    'success_rate': 100.0
                }

            await asyncio.sleep(1.0)  # Check every second

        # Timeout - some symbols didn't receive data
        failed_symbols = all_symbols - verified_symbols
        success_rate = (len(verified_symbols) / total_symbols) * 100 if total_symbols > 0 else 0

        logger.warning(
            f"⚠️ [MARK] Verification timeout: {len(verified_symbols)}/{total_symbols} verified ({success_rate:.1f}%)\n"
            f"   Failed: {failed_symbols}"
        )

        return {
            'verified': verified_symbols,
            'failed': failed_symbols,
            'total': total_symbols,
            'success_rate': success_rate
        }

    async def _verify_subscriptions_health(self):
        """
        PHASE 2: Enhanced health check - verify all open positions have active subscriptions
        AND are receiving fresh data (not silent fails)
        
        PHASE 3 (NEW): Check position manager for stale positions
        """
        if not self.positions:
            return

        # LAYER 1: Check for missing subscriptions (presence check)
        # FIX: Normalize position keys to match subscribed_symbols format (Binance raw)
        all_subscriptions = self.subscribed_symbols.union(self.pending_subscriptions)
        
        # Build mapping: normalized_key -> original_key for reverse lookup
        position_normalized = {self._normalize_symbol(s): s for s in self.positions.keys()}
        normalized_position_keys = set(position_normalized.keys())
        
        missing_normalized = normalized_position_keys - all_subscriptions
        # Convert back to original format for logging
        missing_subscriptions = {position_normalized[n] for n in missing_normalized}

        # DEBUG: Log if we found missing subscriptions (specifically for HYPERUSDT diagnosis)
        if missing_subscriptions:
            logger.info(f"🔍 [DEBUG-HYPER] Missing: {missing_subscriptions}")
            logger.info(f"   Normalized keys: {sorted(list(normalized_position_keys))}")
            logger.info(f"   All Subscriptions: {sorted(list(all_subscriptions))}")

        # LAYER 2: Check for "silent fails"  - subscriptions exist but no data flowing
        STALE_DATA_THRESHOLD = 60.0  # seconds
        stale_subscriptions = []

        for symbol in self.subscribed_symbols:
            # FIX: Check if normalized symbol has a position (not raw key)
            if symbol not in normalized_position_keys:
                continue

            data_age = self._get_data_age(symbol)
            if data_age > STALE_DATA_THRESHOLD:
                stale_subscriptions.append((symbol, data_age))

        # LAYER 3: NEW - Check position manager for positions without recent price updates
        # This catches positions that exist in bot memory but aren't receiving WebSocket updates
        POSITION_STALE_THRESHOLD = 120.0  # 2 minutes without price update
        stale_positions = []
        
        if self.position_manager:
            from datetime import datetime
            now = datetime.now()
            
            for symbol, position in self.position_manager.positions.items():
                # Skip if position just created (no last_price_update yet)
                if not position.last_price_update:
                    # Set initial timestamp
                    position.last_price_update = now
                    continue
                
                time_since_update = (now - position.last_price_update).total_seconds()
                
                if time_since_update > POSITION_STALE_THRESHOLD:
                    stale_positions.append((symbol, time_since_update))

        # Report findings
        issues_found = len(missing_subscriptions) + len(stale_subscriptions) + len(stale_positions)

        if missing_subscriptions:
            logger.warning(f"⚠️ [MARK] Found {len(missing_subscriptions)} positions WITHOUT subscriptions: {missing_subscriptions}")

            # Request subscriptions for missing symbols
            for symbol in missing_subscriptions:
                logger.info(f"🔄 [MARK] Resubscribing to {symbol} (subscription lost)")
                await self._request_mark_subscription(symbol, subscribe=True)

        if stale_subscriptions:
            logger.warning(f"🔇 [MARK] Found {len(stale_subscriptions)} SILENT FAILS (subscribed but no data):")
            for symbol, age in stale_subscriptions:
                logger.warning(f"   - {symbol}: no data for {age:.1f}s (threshold: {STALE_DATA_THRESHOLD}s)")

            # Auto-recovery: discard stale subscription and resubscribe
            for symbol, age in stale_subscriptions:
                logger.info(f"🔄 [MARK] Auto-recovery: discarding stale subscription for {symbol}")

                # Remove from subscribed set (forces fresh subscription)
                self.subscribed_symbols.discard(symbol)

                # Clear stale price data
                if symbol in self.mark_prices:
                    del self.mark_prices[symbol]
                timestamp_key = f"{symbol}_timestamp"
                if timestamp_key in self.mark_prices:
                    del self.mark_prices[timestamp_key]

                # Request fresh subscription
                logger.info(f"🔄 [MARK] Requesting fresh subscription for {symbol}")
                await self._request_mark_subscription(symbol, subscribe=True)
        
        # NEW: Handle stale positions (LAYER 3)
        if stale_positions:
            logger.warning(f"🔴 [HEALTH] Found {len(stale_positions)} STALE POSITIONS (no price update):")
            for symbol, time_stale in stale_positions:
                logger.warning(f"   - {symbol}: no price update for {time_stale:.0f}s (threshold: {POSITION_STALE_THRESHOLD}s)")
            
            # Auto-recovery: re-subscribe to stale positions
            for symbol, time_stale in stale_positions:
                logger.warning(
                    f"🔴 {symbol}: STALE SUBSCRIPTION detected! "
                    f"No price update for {time_stale:.0f}s. "
                    f"Re-subscribing..."
                )
                
                # CRITICAL FIX: Remove from subscribed_symbols BEFORE re-subscribe
                # Without this, _subscribe_mark_price() will see symbol already subscribed and skip!
                self.subscribed_symbols.discard(symbol)
                
                # Clear stale price data
                if symbol in self.mark_prices:
                    del self.mark_prices[symbol]
                timestamp_key = f"{symbol}_timestamp"
                if timestamp_key in self.mark_prices:
                    del self.mark_prices[timestamp_key]
                
                # Re-subscribe (this will go through subscription queue)
                await self._request_mark_subscription(symbol, subscribe=True)
                
                # Reset timestamp to avoid immediate re-trigger
                if self.position_manager and symbol in self.position_manager.positions:
                    self.position_manager.positions[symbol].last_price_update = now

        if issues_found == 0:
            logger.debug(f"✅ [MARK] Subscription health OK: {len(self.positions)} positions, "
                        f"{len(self.subscribed_symbols)} subscribed, {len(self.pending_subscriptions)} pending")

    def _get_data_age(self, symbol: str) -> float:
        """
        Get the age of the last data update for a symbol in seconds.

        Returns:
            float: Seconds since last update, or float('inf') if no data received yet
        """
        timestamp_key = f"{symbol}_timestamp"
        if timestamp_key not in self.mark_prices:
            return float('inf')

        last_update_time = self.mark_prices[timestamp_key]
        current_time = asyncio.get_event_loop().time()
        return current_time - last_update_time

    async def _unsubscribe_mark_price(self, symbol: str):
        """Unsubscribe from mark price stream"""
        if symbol not in self.subscribed_symbols:
            logger.debug(f"[MARK] Not subscribed to {symbol}")
            return

        try:
            stream_name = f"{symbol.lower()}@markPrice@1s"

            message = {
                "method": "UNSUBSCRIBE",
                "params": [stream_name],
                "id": self.next_request_id
            }

            await self.mark_ws.send_str(_json_dumps(message))

            self.subscribed_symbols.discard(symbol)
            self.next_request_id += 1

            logger.info(f"✅ [MARK] Unsubscribed from {symbol}")

        except Exception as e:
            logger.error(f"[MARK] Unsubscription error for {symbol}: {e}")

    # ==================== EVENT EMISSION ====================

    async def _emit_combined_event(self, symbol: str, position_data: Dict):
        """
        Emit combined position event

        Format compatible with Position Manager:
        {
            'symbol': str,
            'mark_price': str,
            'side': str,
            'size': str,
            'entry_price': str,
            'unrealized_pnl': str,
            ...
        }
        """
        if not self.event_handler:
            return

        try:
            # Emit event in format expected by Position Manager
            await self.event_handler('position.update', position_data)
        except Exception as e:
            logger.error(f"Event emission error: {e}")

    # ==================== REST PRICE FALLBACK ====================

    async def _rest_price_fallback_task(self):
        """
        REST API price fallback when WebSocket data is stale.

        If no price update received for a subscribed symbol with an active position
        for >3 seconds, polls via CCXT fetch_ticker every 1 second until WS resumes.

        This ensures trailing stops and stop-losses are never blind.
        """
        STALE_THRESHOLD = 3.0  # Seconds without WS data before REST kicks in
        POLL_INTERVAL = 1.0    # REST poll frequency

        logger.info("🔄 [REST FALLBACK] Task started (threshold=3s, poll=1s)")

        while self.running:
            try:
                await asyncio.sleep(POLL_INTERVAL)

                if not self.running:
                    break

                now = asyncio.get_event_loop().time()

                # Only poll symbols that have active positions
                symbols_to_poll = []
                for symbol in list(self.subscribed_symbols):
                    if symbol not in self.positions:
                        continue

                    ts_key = f"{symbol}_timestamp"
                    last_update = self.mark_prices.get(ts_key, 0)
                    gap = now - last_update

                    if gap > STALE_THRESHOLD:
                        symbols_to_poll.append((symbol, gap))

                if not symbols_to_poll:
                    # All symbols have fresh data — clear active set
                    if self.rest_fallback_active:
                        logger.info(
                            f"✅ [REST FALLBACK] WS resumed for all symbols. "
                            f"Stopping REST polling for: {self.rest_fallback_active}"
                        )
                        self.rest_fallback_active.clear()
                    continue

                # Poll stale symbols via REST
                for symbol, gap in symbols_to_poll:
                    try:
                        price = await self._fetch_price_rest(symbol)
                        if price:
                            self.rest_fallback_count += 1
                            self.rest_fallback_active.add(symbol)

                            # Update mark price cache with REST data
                            self.mark_prices[symbol] = str(price)
                            self.mark_prices[f"{symbol}_timestamp"] = now

                            # Distribute through normal pipeline
                            await self._on_mark_price_update({
                                's': symbol,
                                'p': str(price)
                            })

                            logger.warning(
                                f"🔄 [REST FALLBACK] {symbol} @ ${price:.4f} "
                                f"(WS gap: {gap:.1f}s, total REST calls: {self.rest_fallback_count})"
                            )
                    except Exception as e:
                        logger.error(f"[REST FALLBACK] Error fetching {symbol}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[REST FALLBACK] Task error: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("[REST FALLBACK] Task stopped")

    async def _fetch_price_rest(self, symbol: str) -> Optional[float]:
        """
        Fetch current mark price via CCXT REST API.

        Uses exchange_manager.fetch_ticker() if available,
        falls back to direct aiohttp request to Binance fapi.

        Args:
            symbol: Raw symbol (e.g. 'BTCUSDT')

        Returns:
            float price or None on error
        """
        # Method 1: Via exchange_manager (CCXT)
        if self.exchange_manager:
            try:
                # Convert raw symbol to CCXT format
                ccxt_symbol = symbol.replace('USDT', '/USDT:USDT')
                ticker = await self.exchange_manager.fetch_ticker(ccxt_symbol)
                if ticker and 'last' in ticker:
                    return float(ticker['last'])
            except Exception as e:
                logger.debug(f"[REST FALLBACK] CCXT fetch_ticker failed for {symbol}: {e}")

        # Method 2: Direct REST (fallback if no exchange_manager)
        try:
            url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get('price', 0))
        except Exception as e:
            logger.debug(f"[REST FALLBACK] Direct REST failed for {symbol}: {e}")

        return None

    # ==================== STATUS ====================

    def get_status(self) -> Dict:
        """Get hybrid stream status"""
        pool_status = self.mark_price_pool.get_status()
        state_status = self.symbol_state.get_status()
        
        return {
            'running': self.running,
            'user_connected': self.user_connected,
            'mark_connected': self.mark_price_pool.connected,
            'active_positions': len(self.positions),
            'subscribed_symbols': state_status.get('subscribed', 0),
            'positions': list(self.positions.keys()),
            'mark_prices': list(self.mark_prices.keys()),
            'listen_key': self.listen_key[:10] + '...' if self.listen_key else None,
            'rest_fallback_count': self.rest_fallback_count,
            'rest_fallback_active': list(self.rest_fallback_active),
            # NEW: Pool and state machine status
            'pool': pool_status,
            'symbol_state': state_status,
        }
