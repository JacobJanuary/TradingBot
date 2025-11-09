"""
Bybit Hybrid WebSocket Stream
Combines private WebSocket (position lifecycle) + public WebSocket (mark price updates)

This solves the problem where Bybit private position WebSocket is EVENT-DRIVEN
(only updates on trades), not periodic. Public ticker WebSocket provides 100ms
mark price updates for real-time position tracking.

Architecture:
- Private WS (position topic) → Position open/close/modify → Manage ticker subscriptions
- Public WS (tickers topic) → 100ms mark price updates → Combine with position data
- Hybrid Event Processor → Emit unified position.update events

Date: 2025-10-25
"""

import asyncio
import aiohttp
import json
import hmac
import hashlib
import time
import logging
from typing import Dict, Callable, Optional, Set
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class BybitHybridStream:
    """
    Hybrid WebSocket stream for Bybit mainnet

    Manages TWO WebSocket connections:
    1. Private WS → Position lifecycle (open/close/modify)
    2. Public WS → Mark price updates (100ms frequency)

    Combines both streams to emit unified position.update events with:
    - Position data (size, side, entry price) from private WS
    - Real-time mark price from public WS
    """

    def __init__(self,
                 api_key: str,
                 api_secret: str,
                 event_handler: Optional[Callable] = None,
                 testnet: bool = False):
        """
        Initialize Bybit Hybrid WebSocket

        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            event_handler: Callback for events (event_type, data)
            testnet: Use testnet endpoints
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.event_handler = event_handler
        self.testnet = testnet

        # WebSocket URLs
        if testnet:
            self.private_ws_url = "wss://stream-testnet.bybit.com/v5/private"
            self.public_ws_url = "wss://stream-testnet.bybit.com/v5/public/linear"
        else:
            self.private_ws_url = "wss://stream.bybit.com/v5/private"
            self.public_ws_url = "wss://stream.bybit.com/v5/public/linear"

        # WebSocket connections
        self.private_ws = None
        self.public_ws = None
        self.private_session = None
        self.public_session = None

        # Connection state
        self.private_connected = False
        self.public_connected = False
        self.running = False

        # Hybrid state
        self.positions: Dict[str, Dict] = {}  # {symbol: position_data}
        self.mark_prices: Dict[str, str] = {}  # {symbol: latest_mark_price}
        self.subscribed_tickers: Set[str] = set()  # Active ticker subscriptions
        self.pending_subscriptions: Set[str] = set()  # Symbols awaiting subscription (survives reconnects)

        # Subscription management
        self.subscription_queue = asyncio.Queue()
        self.subscription_task = None

        # Tasks
        self.private_task = None
        self.public_task = None
        self.heartbeat_task = None
        self.health_check_task = None

        # Heartbeat settings (Bybit requires 20s)
        self.heartbeat_interval = 20
        self.last_private_ping = datetime.now()
        self.last_public_ping = datetime.now()

        logger.info(f"BybitHybridStream initialized (testnet={testnet})")

    @property
    def connected(self) -> bool:
        """
        Check if hybrid stream is fully connected.

        Returns True only when BOTH WebSockets are connected:
        - Private WS (position lifecycle)
        - Public WS (price updates)

        This ensures health check passes only when full hybrid functionality
        is available.
        """
        return self.private_connected and self.public_connected

    async def start(self):
        """Start both WebSocket streams"""
        if self.running:
            logger.warning("BybitHybridStream already running")
            return

        self.running = True

        logger.info("🚀 Starting Bybit Hybrid WebSocket...")

        # Start both streams concurrently
        self.private_task = asyncio.create_task(self._run_private_stream())
        self.public_task = asyncio.create_task(self._run_public_stream())
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self.subscription_task = asyncio.create_task(self._subscription_manager())

        # ✅ PHASE 2: Periodic reconnection (every 10 minutes)
        self.reconnection_task = asyncio.create_task(
            self._periodic_reconnection_task(interval_seconds=600)
        )

        # Periodic subscription health check (every 2 minutes)
        self.health_check_task = asyncio.create_task(
            self._periodic_health_check_task(interval_seconds=120)
        )

        logger.info("✅ Bybit Hybrid WebSocket started")

    async def stop(self):
        """Stop both WebSocket streams"""
        logger.info("⏹️ Stopping Bybit Hybrid WebSocket...")

        self.running = False

        # Cancel tasks
        for task in [
            self.private_task,
            self.public_task,
            self.heartbeat_task,
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

        # Close WebSockets
        if self.private_ws and not self.private_ws.closed:
            await self.private_ws.close()
        if self.public_ws and not self.public_ws.closed:
            await self.public_ws.close()

        # Close sessions
        if self.private_session and not self.private_session.closed:
            await self.private_session.close()
        if self.public_session and not self.public_session.closed:
            await self.public_session.close()

        logger.info("✅ Bybit Hybrid WebSocket stopped")

    async def sync_positions(self, positions: list):
        """
        Sync existing positions with WebSocket subscriptions

        Called after loading positions from DB to ensure
        Public WS subscribes to all active positions.

        This fixes the cold start problem where positions exist
        but Private WS doesn't send snapshot, so Public WS never
        subscribes to tickers.

        Args:
            positions: List of position dicts with 'symbol' key
        """
        if not positions:
            logger.debug("No positions to sync")
            return

        logger.info(f"🔄 Syncing {len(positions)} positions with WebSocket...")

        synced = 0
        for position in positions:
            symbol = position.get('symbol')
            if not symbol:
                logger.warning(f"Position missing symbol: {position}")
                continue

            try:
                # Store position data (minimal set for ticker subscription)
                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': position.get('side', 'Buy'),
                    'size': str(position.get('quantity', 0)),
                    'entry_price': str(position.get('entry_price', 0)),
                    'mark_price': str(position.get('current_price', 0)),
                }

                # Request ticker subscription
                await self._request_ticker_subscription(symbol, subscribe=True)
                synced += 1

                # Small delay to avoid overwhelming the connection
                if synced < len(positions):
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to sync position {symbol}: {e}")

        logger.info(f"✅ Synced {synced}/{len(positions)} positions with WebSocket")

    # ==================== PRIVATE WEBSOCKET ====================

    async def _run_private_stream(self):
        """Run private WebSocket for position lifecycle"""
        while self.running:
            try:
                logger.info("🔐 [PRIVATE] Connecting...")

                # Create session
                if not self.private_session or self.private_session.closed:
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    self.private_session = aiohttp.ClientSession(timeout=timeout)

                # Connect
                self.private_ws = await self.private_session.ws_connect(
                    self.private_ws_url,
                    heartbeat=None,
                    autoping=False,
                    autoclose=False
                )

                self.private_connected = True
                logger.info("✅ [PRIVATE] Connected")

                # Authenticate
                await self._authenticate_private()

                # Subscribe to position topic
                await self._subscribe_private_channels()

                # Receive loop
                async for msg in self.private_ws:
                    if not self.running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            await self._process_private_message(data)
                        except Exception as e:
                            logger.error(f"[PRIVATE] Message processing error: {e}")

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"[PRIVATE] WebSocket error: {msg.data}")
                        break

                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info(f"[PRIVATE] WebSocket closed")
                        break

            except Exception as e:
                logger.error(f"[PRIVATE] Stream error: {e}")
            finally:
                self.private_connected = False
                logger.info("[PRIVATE] Disconnected")

                if self.running:
                    logger.info("[PRIVATE] Reconnecting in 5s...")
                    await asyncio.sleep(5)

    async def _authenticate_private(self):
        """Authenticate private WebSocket"""
        expires = int((time.time() + 10) * 1000)
        signature_payload = f"GET/realtime{expires}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            signature_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        auth_msg = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }

        await self.private_ws.send_str(json.dumps(auth_msg))
        logger.info("[PRIVATE] Authentication sent")

    async def _subscribe_private_channels(self):
        """Subscribe to private channels"""
        subscribe_msg = {
            "op": "subscribe",
            "args": ["position"]
        }

        await self.private_ws.send_str(json.dumps(subscribe_msg))
        logger.info("[PRIVATE] Subscribed to position topic")

    async def _process_private_message(self, data: Dict):
        """Process private WebSocket message"""
        op = data.get('op')

        # Handle operation responses
        if op == 'auth':
            if data.get('success'):
                logger.info("✅ [PRIVATE] Authenticated")
            else:
                logger.error(f"❌ [PRIVATE] Authentication failed: {data}")

        elif op == 'subscribe':
            if data.get('success'):
                logger.info(f"✅ [PRIVATE] Subscription confirmed")
            else:
                logger.error(f"❌ [PRIVATE] Subscription failed: {data}")

        elif op == 'pong':
            logger.debug("[PRIVATE] Pong received")

        # Handle position updates
        elif 'topic' in data and data['topic'] == 'position':
            positions = data.get('data', [])
            await self._on_position_update(positions)

    async def _on_position_update(self, positions: list):
        """
        Handle position lifecycle updates

        Triggers:
        - Position opened (size > 0) → Subscribe to ticker
        - Position closed (size = 0) → Unsubscribe from ticker
        - Position modified → Update position data
        """
        for pos in positions:
            symbol = pos.get('symbol')
            size = float(pos.get('size', 0))

            logger.info(f"📊 [PRIVATE] Position update: {symbol} size={size}")

            if size > 0:
                # Position active - store and subscribe to ticker
                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': pos.get('side'),
                    'size': str(size),
                    'entry_price': pos.get('avgPrice', '0'),
                    'mark_price': pos.get('markPrice', '0'),
                    'unrealized_pnl': pos.get('unrealisedPnl', '0'),
                    'leverage': pos.get('leverage', '1'),
                    'stop_loss': pos.get('stopLoss', '0'),
                    'take_profit': pos.get('takeProfit', '0'),
                    'position_value': pos.get('positionValue', '0')
                }

                # Request ticker subscription
                await self._request_ticker_subscription(symbol, subscribe=True)

                # Emit initial event with current mark price
                await self._emit_combined_event(symbol, self.positions[symbol])

            else:
                # Position closed - remove and unsubscribe
                if symbol in self.positions:
                    # CRITICAL FIX: Emit closure event BEFORE deleting position
                    # This ensures position_manager is notified and can clean up properly
                    position_data = self.positions[symbol].copy()
                    position_data['size'] = '0'
                    position_data['position_amt'] = 0  # Required for position_manager closure detection

                    # Emit closure event to position_manager
                    await self._emit_combined_event(symbol, position_data)
                    logger.info(f"📤 [PRIVATE] Emitted closure event for {symbol}")

                    # Now safe to delete from local tracking
                    del self.positions[symbol]
                    logger.info(f"✅ [PRIVATE] Position closed: {symbol}")

                # Request ticker unsubscription
                await self._request_ticker_subscription(symbol, subscribe=False)

    # ==================== PUBLIC WEBSOCKET ====================

    async def _run_public_stream(self):
        """Run public WebSocket for ticker updates"""
        while self.running:
            try:
                logger.info("🌐 [PUBLIC] Connecting...")

                # Create session
                if not self.public_session or self.public_session.closed:
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    self.public_session = aiohttp.ClientSession(timeout=timeout)

                # Connect
                self.public_ws = await self.public_session.ws_connect(
                    self.public_ws_url,
                    heartbeat=None,
                    autoping=False,
                    autoclose=False
                )

                self.public_connected = True
                logger.info("✅ [PUBLIC] Connected")

                # Restore ticker subscriptions if any
                await self._restore_ticker_subscriptions()

                # Receive loop
                async for msg in self.public_ws:
                    if not self.running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            await self._process_public_message(data)
                        except Exception as e:
                            logger.error(f"[PUBLIC] Message processing error: {e}")

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"[PUBLIC] WebSocket error: {msg.data}")
                        break

                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info(f"[PUBLIC] WebSocket closed")
                        break

            except Exception as e:
                logger.error(f"[PUBLIC] Stream error: {e}")
            finally:
                self.public_connected = False
                logger.info("[PUBLIC] Disconnected")

                if self.running:
                    logger.info("[PUBLIC] Reconnecting in 5s...")
                    await asyncio.sleep(5)

    async def _process_public_message(self, data: Dict):
        """Process public WebSocket message"""
        op = data.get('op')

        # Handle operation responses
        if op == 'subscribe':
            if data.get('success'):
                logger.debug(f"[PUBLIC] Subscription confirmed")
            else:
                logger.error(f"[PUBLIC] Subscription failed: {data}")

        elif op == 'pong':
            logger.debug("[PUBLIC] Pong received")

        # Handle ticker updates
        elif 'topic' in data and data['topic'].startswith('tickers.'):
            ticker_data = data.get('data', {})
            await self._on_ticker_update(ticker_data)

    async def _on_ticker_update(self, ticker_data: Dict):
        """
        Handle ticker updates (100ms frequency)

        Combines ticker data with position data and emits unified event
        """
        symbol = ticker_data.get('symbol')
        mark_price = ticker_data.get('markPrice')

        if not symbol or not mark_price:
            return

        # Update mark price cache
        self.mark_prices[symbol] = mark_price

        # If we have position data, emit combined event
        if symbol in self.positions:
            position_data = self.positions[symbol].copy()
            position_data['mark_price'] = mark_price

            # Update position cache
            self.positions[symbol]['mark_price'] = mark_price

            # Emit combined event
            await self._emit_combined_event(symbol, position_data)

            logger.debug(f"💰 [PUBLIC] Price update: {symbol} @ ${mark_price}")

    # ==================== SUBSCRIPTION MANAGEMENT ====================

    async def _subscription_manager(self):
        """Background task to manage ticker subscriptions"""
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

                # Process subscription
                if subscribe:
                    await self._subscribe_ticker(symbol)
                else:
                    await self._unsubscribe_ticker(symbol)

            except Exception as e:
                logger.error(f"Subscription manager error: {e}")
                await asyncio.sleep(1)

    async def _request_ticker_subscription(self, symbol: str, subscribe: bool):
        """Request ticker subscription/unsubscription (queued)"""
        if subscribe:
            # Mark subscription intent immediately (survives reconnects)
            self.pending_subscriptions.add(symbol)
            logger.debug(f"[PUBLIC] Marked {symbol} for subscription (pending)")

        try:
            await self.subscription_queue.put((symbol, subscribe))
        except Exception as e:
            logger.error(f"Failed to queue subscription request: {e}")

    async def _subscribe_ticker(self, symbol: str):
        """Subscribe to ticker topic"""
        if not self.public_connected or not self.public_ws:
            logger.warning(f"[PUBLIC] Cannot subscribe {symbol} - not connected")
            return

        if symbol in self.subscribed_tickers:
            logger.debug(f"[PUBLIC] Already subscribed to {symbol}")
            return

        topic = f"tickers.{symbol}"
        msg = {
            "op": "subscribe",
            "args": [topic]
        }

        try:
            await self.public_ws.send_str(json.dumps(msg))
            self.subscribed_tickers.add(symbol)
            self.pending_subscriptions.discard(symbol)  # Clear from pending after successful subscription
            logger.info(f"✅ [PUBLIC] Subscribed to {symbol} (pending cleared)")
        except Exception as e:
            logger.error(f"[PUBLIC] Failed to subscribe {symbol}: {e}")

    async def _unsubscribe_ticker(self, symbol: str):
        """Unsubscribe from ticker topic"""
        if not self.public_connected or not self.public_ws:
            logger.warning(f"[PUBLIC] Cannot unsubscribe {symbol} - not connected")
            return

        if symbol not in self.subscribed_tickers:
            logger.debug(f"[PUBLIC] Not subscribed to {symbol}")
            return

        topic = f"tickers.{symbol}"
        msg = {
            "op": "unsubscribe",
            "args": [topic]
        }

        try:
            await self.public_ws.send_str(json.dumps(msg))
            self.subscribed_tickers.remove(symbol)
            logger.info(f"✅ [PUBLIC] Unsubscribed from {symbol}")
        except Exception as e:
            logger.error(f"[PUBLIC] Failed to unsubscribe {symbol}: {e}")

    async def _restore_ticker_subscriptions(self):
        """
        Restore ticker subscriptions after reconnection

        HYBRID APPROACH (based on test results):
        1. First 30 symbols: OPTIMISTIC (no verification, fast)
        2. Remaining symbols: OPTIMISTIC (все быстро)
        3. 60s warmup period (let data start flowing)
        4. Verification of all subscriptions (background, non-blocking)

        This approach prevents event loop blocking while ensuring
        subscriptions are actually working.
        """
        # Combine confirmed and pending subscriptions
        all_symbols = self.subscribed_tickers.union(self.pending_subscriptions)

        if not all_symbols:
            logger.debug("[PUBLIC] No subscriptions to restore")
            return

        symbols_to_restore = list(all_symbols)
        total_symbols = len(symbols_to_restore)

        logger.info(
            f"🔄 [PUBLIC] Restoring {total_symbols} ticker subscriptions "
            f"({len(self.subscribed_tickers)} confirmed + {len(self.pending_subscriptions)} pending)..."
        )

        # Clear both sets to allow resubscribe
        self.subscribed_tickers.clear()
        self.pending_subscriptions.clear()

        # CRITICAL FIX: Clear old price data to ensure verification checks FRESH data
        # Without this, _verify_all_subscriptions_active() incorrectly validates against stale prices
        self.ticker_prices.clear()
        logger.debug(f"[PUBLIC] Cleared old price data for {total_symbols} symbols")

        # PHASE 1: OPTIMISTIC SUBSCRIPTIONS (all symbols, fast)
        logger.info(f"📤 [PUBLIC] Sending {total_symbols} OPTIMISTIC subscriptions...")
        restored = 0
        for symbol in symbols_to_restore:
            try:
                success = await self._verify_subscription_optimistic(symbol)
                if success:
                    restored += 1

                # Small delay to avoid overwhelming connection
                if restored < total_symbols:
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"❌ [PUBLIC] Failed to restore subscription for {symbol}: {e}")

        logger.info(f"✅ [PUBLIC] Sent {restored}/{total_symbols} subscription requests")

        # PHASE 2: WARMUP PERIOD (90 seconds - increased from 60s due to observed 72s delay)
        if restored > 0:
            logger.info(f"⏳ [PUBLIC] Warmup period: waiting 90s for data to start flowing...")
            await asyncio.sleep(90.0)
            logger.info(f"✅ [PUBLIC] Warmup complete")

            # PHASE 3: VERIFICATION (background, non-blocking)
            logger.info(f"🔍 [PUBLIC] Verifying subscriptions in background...")

            # Start verification in background (don't block)
            async def background_verify():
                try:
                    result = await self._verify_all_subscriptions_active(timeout=60.0)

                    if result['success_rate'] < 90:
                        logger.warning(
                            f"⚠️ [PUBLIC] Low verification rate: {result['success_rate']:.1f}%\n"
                            f"   Verified: {len(result['verified'])}\n"
                            f"   Failed: {len(result['failed'])}\n"
                            f"   Failed symbols: {result['failed']}"
                        )
                    else:
                        logger.info(
                            f"✅ [PUBLIC] Subscription health: {result['success_rate']:.1f}% "
                            f"({len(result['verified'])}/{result['total']})"
                        )
                except Exception as e:
                    logger.error(f"❌ [PUBLIC] Background verification error: {e}")

            # Run in background, don't await
            asyncio.create_task(background_verify())

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
            topic = f"tickers.{symbol}"
            msg = {
                "op": "subscribe",
                "args": [topic]
            }
            await self.public_ws.send_str(json.dumps(msg))
            self.subscribed_tickers.add(symbol)
            logger.info(f"📤 [PUBLIC] OPTIMISTIC subscribe: {symbol}")
            return True
        except Exception as e:
            logger.error(f"❌ [PUBLIC] Failed optimistic subscribe {symbol}: {e}")
            return False

    async def _verify_subscription_event_based(self, symbol: str, timeout: float = 10.0) -> bool:
        """
        Subscribe with EVENT-BASED verification (NON-BLOCKING!)

        Waits for actual ticker update event to confirm subscription is working.
        Uses asyncio.Event for non-blocking wait.

        Args:
            symbol: Symbol to subscribe to
            timeout: Seconds to wait for first price update

        Returns:
            bool: True if verified (data received), False if timeout
        """
        # Store current price count to detect new data
        initial_count = len(self.mark_prices.get(symbol, ""))

        # Helper to check for new data
        def check_new_data():
            return symbol in self.mark_prices and len(self.mark_prices[symbol]) > initial_count

        try:
            # Send subscription request
            topic = f"tickers.{symbol}"
            msg = {
                "op": "subscribe",
                "args": [topic]
            }
            await self.public_ws.send_str(json.dumps(msg))
            self.subscribed_tickers.add(symbol)
            start_time = asyncio.get_event_loop().time()

            # Wait for data with timeout
            deadline = start_time + timeout
            while asyncio.get_event_loop().time() < deadline:
                if check_new_data():
                    elapsed = asyncio.get_event_loop().time() - start_time
                    logger.info(f"✅ [PUBLIC] VERIFIED: {symbol} (data in {elapsed:.1f}s)")
                    return True

                await asyncio.sleep(0.5)  # Check every 500ms

            # Timeout - no data received
            logger.warning(f"🚨 [PUBLIC] SILENT FAIL: {symbol} (timeout {timeout}s)")
            return False

        except Exception as e:
            logger.error(f"❌ [PUBLIC] Verification error {symbol}: {e}")
            return False

    async def _verify_all_subscriptions_active(self, timeout: float = 60.0) -> dict:
        """
        Verify that ALL subscriptions are receiving data after reconnect

        NON-BLOCKING: Waits for data from all symbols in parallel.
        Used after _restore_ticker_subscriptions() to ensure no silent fails.

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
        if not self.subscribed_tickers and not self.pending_subscriptions:
            logger.debug("[PUBLIC] No subscriptions to verify")
            return {
                'verified': set(),
                'failed': set(),
                'total': 0,
                'success_rate': 100.0
            }

        all_symbols = self.subscribed_tickers.union(self.pending_subscriptions)
        total_symbols = len(all_symbols)

        logger.info(f"🔍 [PUBLIC] Verifying {total_symbols} subscriptions (timeout: {timeout}s)...")

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
                    logger.debug(f"✓ [PUBLIC] {symbol} verified ({len(verified_symbols)}/{total_symbols})")

            # All verified?
            if len(verified_symbols) == total_symbols:
                elapsed = asyncio.get_event_loop().time() - start_time
                logger.info(f"✅ [PUBLIC] ALL {total_symbols} subscriptions verified in {elapsed:.1f}s")
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
            f"⚠️ [PUBLIC] Verification timeout: {len(verified_symbols)}/{total_symbols} verified ({success_rate:.1f}%)\n"
            f"   Failed: {failed_symbols}"
        )

        return {
            'verified': verified_symbols,
            'failed': failed_symbols,
            'total': total_symbols,
            'success_rate': success_rate
        }

    # ==================== EVENT EMISSION ====================

    async def _emit_combined_event(self, symbol: str, position_data: Dict):
        """
        Emit unified position.update event

        Event format matches existing Position Manager expectations:
        {
            'symbol': str,
            'side': str,
            'size': float,
            'entry_price': float,
            'mark_price': float,  ← Real-time from public WS
            'unrealized_pnl': float,
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

    # ==================== HEARTBEAT ====================

    async def _heartbeat_loop(self):
        """Send periodic ping to both WebSockets (20s interval for Bybit)"""
        while self.running:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                # Ping private WebSocket
                if self.private_connected and self.private_ws and not self.private_ws.closed:
                    try:
                        await self.private_ws.send_str(json.dumps({"op": "ping"}))
                        self.last_private_ping = datetime.now()
                        logger.debug(f"📤 [PRIVATE] Ping sent at {self.last_private_ping.strftime('%H:%M:%S')}")
                    except Exception as e:
                        logger.error(f"[PRIVATE] Ping failed: {e}")

                # Ping public WebSocket
                if self.public_connected and self.public_ws and not self.public_ws.closed:
                    try:
                        await self.public_ws.send_str(json.dumps({"op": "ping"}))
                        self.last_public_ping = datetime.now()
                        logger.debug(f"📤 [PUBLIC] Ping sent at {self.last_public_ping.strftime('%H:%M:%S')}")
                    except Exception as e:
                        logger.error(f"[PUBLIC] Ping failed: {e}")

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    async def _periodic_reconnection_task(self, interval_seconds: int = 600):
        """
        ✅ PHASE 2: Periodic prophylactic reconnection

        Reconnects WebSocket every N seconds to ensure fresh connection state.
        Industry best practice for reliable trading bots.

        Args:
            interval_seconds: Reconnection interval (default: 600s = 10min)
        """
        logger.info(
            f"🔄 Starting periodic reconnection task (interval: {interval_seconds}s)"
        )

        while self.running:
            try:
                await asyncio.sleep(interval_seconds)

                if not self.running:
                    break

                # Only reconnect if we have active positions
                if not self.positions:
                    logger.debug("No active positions, skipping periodic reconnection")
                    continue

                logger.info(
                    f"🔄 Periodic reconnection triggered "
                    f"({len(self.positions)} active positions)"
                )

                # Store current subscribed tickers
                tickers_backup = list(self.subscribed_tickers)

                # Gracefully close public WebSocket (ticker stream)
                if self.public_ws and not self.public_ws.closed:
                    logger.info("📤 Closing public WebSocket for reconnection...")
                    await self.public_ws.close()
                    self.public_connected = False

                # Wait for reconnection
                await asyncio.sleep(2)

                # Connection will auto-reconnect via _run_public_stream
                # Wait for reconnection to complete
                max_wait = 30  # 30 seconds max
                waited = 0
                while not self.public_connected and waited < max_wait:
                    await asyncio.sleep(1)
                    waited += 1

                if self.public_connected:
                    logger.info("✅ Periodic reconnection successful")

                    # Verify all subscriptions restored
                    missing = set(tickers_backup) - self.subscribed_tickers
                    if missing:
                        logger.warning(
                            f"⚠️ {len(missing)} subscriptions not restored: {missing}"
                        )
                        # Trigger manual restore
                        for symbol in missing:
                            await self._request_ticker_subscription(symbol, subscribe=True)
                else:
                    logger.error("❌ Periodic reconnection failed - timeout")

            except asyncio.CancelledError:
                logger.info("Periodic reconnection task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic reconnection: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retry

    async def _periodic_health_check_task(self, interval_seconds: int = 120):
        """
        Periodic subscription health verification

        Checks every N seconds that all open positions have active or pending subscriptions.
        Recovers any subscriptions that were lost due to race conditions.

        Args:
            interval_seconds: Check interval (default: 120s = 2min)
        """
        logger.info(f"🏥 [PUBLIC] Starting subscription health check task (interval: {interval_seconds}s)")

        while self.running:
            try:
                await asyncio.sleep(interval_seconds)

                if not self.running:
                    break

                # Run health verification
                await self._verify_subscriptions_health()

            except asyncio.CancelledError:
                logger.info("[PUBLIC] Subscription health check task cancelled")
                break
            except Exception as e:
                logger.error(f"[PUBLIC] Error in health check task: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _verify_subscriptions_health(self):
        """Verify all open positions have active or pending subscriptions"""
        if not self.positions:
            return

        # Check all open positions
        all_subscriptions = self.subscribed_tickers.union(self.pending_subscriptions)
        missing_subscriptions = set(self.positions.keys()) - all_subscriptions

        if missing_subscriptions:
            logger.warning(f"⚠️ [PUBLIC] Found {len(missing_subscriptions)} positions without subscriptions: {missing_subscriptions}")

            # Request subscriptions for missing symbols
            for symbol in missing_subscriptions:
                logger.info(f"🔄 [PUBLIC] Resubscribing to {symbol} (subscription lost)")
                await self._request_ticker_subscription(symbol, subscribe=True)
        else:
            logger.debug(f"✅ [PUBLIC] Subscription health OK: {len(self.positions)} positions, "
                        f"{len(self.subscribed_tickers)} subscribed, {len(self.pending_subscriptions)} pending")

    # ==================== STATUS ====================

    def get_status(self) -> Dict:
        """Get hybrid stream status"""
        return {
            'running': self.running,
            'private_connected': self.private_connected,
            'public_connected': self.public_connected,
            'active_positions': len(self.positions),
            'subscribed_tickers': len(self.subscribed_tickers),
            'positions': list(self.positions.keys()),
            'tickers': list(self.subscribed_tickers)
        }
