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

        # Subscription management
        self.subscription_queue = asyncio.Queue()
        self.next_request_id = 1

        # Tasks
        self.user_task = None
        self.mark_task = None
        self.keepalive_task = None
        self.subscription_task = None

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
        for task in [self.user_task, self.mark_task, self.keepalive_task, self.subscription_task]:
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
                        logger.debug("🔑 Listen key refreshed")
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
        while self.running:
            try:
                # Refresh every 30 minutes (Binance requirement)
                await asyncio.sleep(1800)  # 30 minutes

                if self.running and self.listen_key:
                    await self._refresh_listen_key()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Keep alive error: {e}")

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

        # If we have position data, emit combined event
        if symbol in self.positions:
            position_data = self.positions[symbol].copy()
            position_data['mark_price'] = mark_price

            # Update position cache
            self.positions[symbol]['mark_price'] = mark_price

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

                # Send subscription to WebSocket
                if self.mark_connected and self.mark_ws and not self.mark_ws.closed:
                    if subscribe:
                        await self._subscribe_mark_price(symbol)
                    else:
                        await self._unsubscribe_mark_price(symbol)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Subscription manager error: {e}")

    async def _request_mark_subscription(self, symbol: str, subscribe: bool = True):
        """Queue mark price subscription request"""
        await self.subscription_queue.put((symbol, subscribe))

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
            self.next_request_id += 1

            logger.info(f"✅ [MARK] Subscribed to {symbol}")

        except Exception as e:
            logger.error(f"[MARK] Subscription error for {symbol}: {e}")

    async def _restore_subscriptions(self):
        """Restore all mark price subscriptions after reconnect"""
        if not self.subscribed_symbols:
            logger.debug("[MARK] No subscriptions to restore")
            return

        symbols_to_restore = list(self.subscribed_symbols)
        logger.info(f"🔄 [MARK] Restoring {len(symbols_to_restore)} subscriptions...")

        # Clear subscribed set to allow resubscribe
        self.subscribed_symbols.clear()

        restored = 0
        for symbol in symbols_to_restore:
            try:
                await self._subscribe_mark_price(symbol)
                restored += 1

                # Small delay to avoid overwhelming the connection
                if restored < len(symbols_to_restore):
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"❌ [MARK] Failed to restore subscription for {symbol}: {e}")

        logger.info(f"✅ [MARK] Restored {restored}/{len(symbols_to_restore)} subscriptions")

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
