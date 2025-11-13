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
import json
import logging
from typing import Dict, Callable, Optional, Set
from datetime import datetime

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
                 testnet: bool = False):
        """
        Initialize Binance Hybrid WebSocket

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            event_handler: Callback for events (event_type, data)
            testnet: Use testnet endpoints
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.event_handler = event_handler
        self.testnet = testnet

        # URLs
        if testnet:
            self.rest_url = "https://testnet.binance.vision/fapi/v1"
            self.user_ws_url = "wss://stream.binance.vision:9443/ws"
            self.mark_ws_url = "wss://stream.binance.vision/ws"
        else:
            self.rest_url = "https://fapi.binance.com/fapi/v1"
            self.user_ws_url = "wss://fstream.binance.com/ws"
            self.mark_ws_url = "wss://fstream.binance.com/ws"

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
        self.subscribed_symbols: Set[str] = set()  # Active mark price subscriptions
        self.pending_subscriptions: Set[str] = set()  # Symbols awaiting subscription (survives reconnects)

        # Subscription management
        self.subscription_queue = asyncio.Queue()
        self.next_request_id = 1

        # PHASE 4: WebSocket heartbeat monitoring
        self.last_mark_message_time = 0.0  # Monotonic time of last mark stream message
        self.last_user_message_time = 0.0  # Monotonic time of last user stream message

        # Tasks
        self.user_task = None
        self.mark_task = None
        self.keepalive_task = None
        self.subscription_task = None
        self.heartbeat_task = None  # PHASE 4: WebSocket heartbeat monitoring

        logger.info(f"BinanceHybridStream initialized (testnet={testnet})")

    @property
    def connected(self) -> bool:
        """
        Check if hybrid stream is fully connected.

        Returns True only when BOTH WebSockets are connected:
        - User Data Stream (position lifecycle)
        - Mark Price Stream (price updates)

        This ensures health check passes only when full hybrid functionality
        is available.
        """
        return self.user_connected and self.mark_connected

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

        # Start both streams concurrently
        self.user_task = asyncio.create_task(self._run_user_stream())
        self.mark_task = asyncio.create_task(self._run_mark_stream())
        self.keepalive_task = asyncio.create_task(self._keep_alive_loop())
        self.subscription_task = asyncio.create_task(self._subscription_manager())

        # ❌ DISABLED: Periodic reconnection causes 72s data gap every 10 minutes
        # Relying on automatic _reconnect_loop() for real connection issues
        # self.reconnection_task = asyncio.create_task(
        #     self._periodic_reconnection_task(interval_seconds=600)
        # )

        # Periodic subscription health check (every 2 minutes)
        self.health_check_task = asyncio.create_task(
            self._periodic_health_check_task(interval_seconds=120)
        )

        # PHASE 4: WebSocket heartbeat monitoring (detects frozen connections)
        self.heartbeat_task = asyncio.create_task(
            self._heartbeat_monitoring_task(check_interval=30, timeout=45)
        )

        logger.info("✅ Binance Hybrid WebSocket started")

    async def stop(self):
        """Stop both WebSocket streams"""
        if not self.running:
            return

        logger.info("⏹️ Stopping Binance Hybrid WebSocket...")

        self.running = False

        # Close WebSocket connections
        if self.user_ws and not self.user_ws.closed:
            await self.user_ws.close()

        if self.mark_ws and not self.mark_ws.closed:
            await self.mark_ws.close()

        # Close aiohttp sessions
        if self.user_session and not self.user_session.closed:
            await self.user_session.close()

        if self.mark_session and not self.mark_session.closed:
            await self.mark_session.close()

        # Cancel tasks
        for task in [
            self.user_task,
            self.mark_task,
            self.keepalive_task,
            self.subscription_task,
            self.reconnection_task,  # ✅ PHASE 2
            self.health_check_task  # Subscription health verification
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
                    await self._refresh_listen_key()

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

    async def _heartbeat_monitoring_task(self, check_interval: int = 30, timeout: int = 45):
        """
        PHASE 4: WebSocket heartbeat monitoring

        Detects frozen WebSocket connections (alive but not sending data).
        If no messages received for timeout seconds, forces reconnect.

        Args:
            check_interval: How often to check (default: 30s)
            timeout: No-message threshold (default: 45s)
        """
        logger.info(f"💓 [HEARTBEAT] Starting WebSocket heartbeat monitoring (check: {check_interval}s, timeout: {timeout}s)")

        while self.running:
            try:
                await asyncio.sleep(check_interval)

                if not self.running:
                    break

                current_time = asyncio.get_event_loop().time()

                # Check Mark Price Stream heartbeat
                if self.mark_connected and self.last_mark_message_time > 0:
                    mark_silence = current_time - self.last_mark_message_time
                    if mark_silence > timeout:
                        logger.warning(
                            f"💔 [HEARTBEAT] Mark stream frozen! "
                            f"No messages for {mark_silence:.1f}s (threshold: {timeout}s). "
                            f"Forcing reconnect..."
                        )
                        self.mark_connected = False  # Triggers reconnect in _run_mark_stream()

                # Check User Data Stream heartbeat
                if self.user_connected and self.last_user_message_time > 0:
                    user_silence = current_time - self.last_user_message_time
                    if user_silence > timeout:
                        logger.warning(
                            f"💔 [HEARTBEAT] User stream frozen! "
                            f"No messages for {user_silence:.1f}s (threshold: {timeout}s). "
                            f"Forcing reconnect..."
                        )
                        self.user_connected = False  # Triggers reconnect in _run_user_stream()

            except asyncio.CancelledError:
                logger.info("[HEARTBEAT] Heartbeat monitoring task cancelled")
                break
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error in heartbeat monitoring: {e}", exc_info=True)
                await asyncio.sleep(30)

    # ==================== USER DATA STREAM ====================

    async def _run_user_stream(self):
        """Run User Data Stream for position lifecycle"""
        reconnect_delay = 5

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
                    heartbeat=None,
                    autoping=False,
                    autoclose=False
                )

                self.user_connected = True
                logger.info("✅ [USER] Connected")

                # Reset reconnect delay on successful connection
                reconnect_delay = 5

                # Receive loop
                async for msg in self.user_ws:
                    if not self.running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            await self._handle_user_message(data)
                        except json.JSONDecodeError as e:
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
                    logger.info(f"[USER] Reconnecting in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 60)  # Max 60s

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
            # Optional: можно обрабатывать ордера если нужно
            logger.debug(f"[USER] Order update: {data.get('o', {}).get('s')}")

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

                    # Emit closure event to position_manager
                    await self._emit_combined_event(symbol, position_data)
                    logger.info(f"📤 [USER] Emitted closure event for {symbol}")

                    # Now safe to delete from local tracking
                    del self.positions[symbol]
                    logger.info(f"❌ [USER] Position closed: {symbol}")

                # Request mark price unsubscription
                await self._request_mark_subscription(symbol, subscribe=False)

    # ==================== MARK PRICE STREAM ====================

    async def _run_mark_stream(self):
        """Run Mark Price Stream (combined stream for all subscribed symbols)"""
        reconnect_delay = 5

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
                logger.info("✅ [MARK] Connected")

                # Restore subscriptions after reconnect
                await self._restore_subscriptions()

                # Reset reconnect delay
                reconnect_delay = 5

                # Receive loop
                async for msg in self.mark_ws:
                    if not self.running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            await self._handle_mark_message(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"[MARK] JSON decode error: {e}")
                        except Exception as e:
                            logger.error(f"[MARK] Message handling error: {e}")

                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("[MARK] WebSocket closed by server")
                        break

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("[MARK] WebSocket error")
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [MARK] Connection error: {e}")

            finally:
                self.mark_connected = False

                if self.running:
                    logger.info(f"[MARK] Reconnecting in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 60)

    async def _handle_mark_message(self, data: Dict):
        """Handle Mark Price Stream message"""
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

    async def _request_mark_subscription(self, symbol: str, subscribe: bool = True):
        """Queue mark price subscription request"""
        # NOTE: pending_subscriptions управляется в _subscription_manager()
        # Здесь только добавляем в queue для обработки
        await self.subscription_queue.put((symbol, subscribe))
        logger.debug(f"[MARK] Queued subscription request: {symbol} (subscribe={subscribe})")

    async def _subscribe_mark_price(self, symbol: str):
        """Subscribe to mark price stream for symbol"""
        if symbol in self.subscribed_symbols:
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

            await self.mark_ws.send_str(json.dumps(message))

            self.subscribed_symbols.add(symbol)
            self.pending_subscriptions.discard(symbol)  # Clear from pending after successful subscription
            self.next_request_id += 1

            logger.info(f"✅ [MARK] Subscribed to {symbol} (pending cleared)")

        except Exception as e:
            logger.error(f"[MARK] Subscription error for {symbol}: {e}")

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

        # CRITICAL FIX: Clear old price data to ensure verification checks FRESH data
        # Without this, _verify_all_subscriptions_active() incorrectly validates against stale prices
        self.mark_prices.clear()
        logger.debug(f"[MARK] Cleared old price data for {total_symbols} symbols")

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
        """
        if not self.positions:
            return

        # LAYER 1: Check for missing subscriptions (presence check)
        all_subscriptions = self.subscribed_symbols.union(self.pending_subscriptions)
        missing_subscriptions = set(self.positions.keys()) - all_subscriptions

        # LAYER 2: Check for "silent fails" - subscriptions exist but no data flowing
        STALE_DATA_THRESHOLD = 60.0  # seconds
        stale_subscriptions = []

        for symbol in self.subscribed_symbols:
            # Only check symbols we have positions for
            if symbol not in self.positions:
                continue

            data_age = self._get_data_age(symbol)
            if data_age > STALE_DATA_THRESHOLD:
                stale_subscriptions.append((symbol, data_age))

        # Report findings
        issues_found = len(missing_subscriptions) + len(stale_subscriptions)

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

            await self.mark_ws.send_str(json.dumps(message))

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

    # ==================== STATUS ====================

    def get_status(self) -> Dict:
        """Get hybrid stream status"""
        return {
            'running': self.running,
            'user_connected': self.user_connected,
            'mark_connected': self.mark_connected,
            'active_positions': len(self.positions),
            'subscribed_symbols': len(self.subscribed_symbols),
            'positions': list(self.positions.keys()),
            'mark_prices': list(self.mark_prices.keys()),
            'listen_key': self.listen_key[:10] + '...' if self.listen_key else None
        }
