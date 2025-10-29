# HYBRID WEBSOCKET - CODE EXAMPLES
**Parent Doc**: HYBRID_WEBSOCKET_IMPLEMENTATION_PLAN.md
**Purpose**: Complete code examples for implementation

---

## Complete Implementation: bybit_hybrid_stream.py

```python
"""
Bybit Hybrid WebSocket Stream
Combines private (position lifecycle) and public (mark price) streams

Architecture:
- Private WS: Position lifecycle events → manage ticker subscriptions
- Public WS: Mark price updates → combine with position data
- Hybrid Processor: Merge both streams → emit unified events

Author: Trading Bot Team
Date: 2025-10-25
"""

import asyncio
import aiohttp
import json
import hmac
import hashlib
import time
import logging
from typing import Dict, Optional, Callable, Set
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class StreamType(Enum):
    """WebSocket stream types"""
    PRIVATE = "private"
    PUBLIC = "public"


class BybitHybridStream:
    """
    Hybrid WebSocket stream for Bybit
    Manages both private (position) and public (ticker) streams
    """

    def __init__(self, api_key: str, api_secret: str,
                 event_handler: Optional[Callable] = None,
                 testnet: bool = False):
        """
        Initialize hybrid stream

        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            event_handler: Callback for events
            testnet: Use testnet (default: mainnet)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.event_handler = event_handler
        self.testnet = testnet

        # WebSocket URLs
        if testnet:
            self.private_ws_url = "wss://stream-testnet.bybit.com/v5/private?max_active_time=180s"
            self.public_ws_url = "wss://stream-testnet.bybit.com/v5/public/linear"
        else:
            self.private_ws_url = "wss://stream.bybit.com/v5/private?max_active_time=180s"
            self.public_ws_url = "wss://stream.bybit.com/v5/public/linear"

        # WebSocket connections
        self.private_ws = None
        self.public_ws = None
        self.private_session = None
        self.public_session = None

        # Connection state
        self.running = False
        self.connected_private = False
        self.connected_public = False

        # Tasks
        self.private_task = None
        self.public_task = None
        self.heartbeat_task = None
        self.processor_task = None

        # Hybrid state
        self.positions = {}  # {symbol: position_data}
        self.mark_prices = {}  # {symbol: latest_mark_price}
        self.subscribed_tickers: Set[str] = set()  # Active ticker subscriptions
        self.pending_subscriptions = asyncio.Queue()  # Queue for sub/unsub requests

        # Heartbeat configuration (Bybit requires ping every 20s)
        self.heartbeat_interval = 20
        self.last_ping_time = {
            StreamType.PRIVATE: datetime.now(),
            StreamType.PUBLIC: datetime.now()
        }
        self.last_pong_time = {
            StreamType.PRIVATE: datetime.now(),
            StreamType.PUBLIC: datetime.now()
        }

        # Statistics
        self.stats = {
            'position_updates': 0,
            'ticker_updates': 0,
            'combined_events': 0,
            'subscriptions': 0,
            'unsubscriptions': 0,
            'reconnections': 0
        }

        # Event queue for combined events
        self.event_queue = asyncio.Queue()

        logger.info(f"BybitHybridStream initialized ({'testnet' if testnet else 'mainnet'})")

    async def start(self):
        """Start both WebSocket streams"""
        if self.running:
            logger.warning("BybitHybridStream already running")
            return

        self.running = True
        logger.info("Starting BybitHybridStream...")

        # Start both streams concurrently
        self.private_task = asyncio.create_task(self._run_private_stream())
        self.public_task = asyncio.create_task(self._run_public_stream())
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self.processor_task = asyncio.create_task(self._process_events())

        logger.info("✅ BybitHybridStream started")

    async def stop(self):
        """Stop all WebSocket streams gracefully"""
        logger.info("Stopping BybitHybridStream...")
        self.running = False

        # Cancel tasks
        for task in [self.private_task, self.public_task,
                     self.heartbeat_task, self.processor_task]:
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

        logger.info("✅ BybitHybridStream stopped")

    # ============== PRIVATE WEBSOCKET ==============

    async def _run_private_stream(self):
        """Run private WebSocket for position updates"""
        while self.running:
            try:
                await self._connect_private()
                await self._private_message_loop()
            except Exception as e:
                logger.error(f"Private stream error: {e}")
                self.connected_private = False
                self.stats['reconnections'] += 1
                await asyncio.sleep(5)

    async def _connect_private(self):
        """Connect to private WebSocket"""
        if self.connected_private:
            return

        logger.info(f"🔐 Connecting to private WebSocket: {self.private_ws_url}")

        # Create session
        if not self.private_session or self.private_session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.private_session = aiohttp.ClientSession(timeout=timeout)

        # Connect
        self.private_ws = await self.private_session.ws_connect(
            self.private_ws_url,
            heartbeat=None,  # Custom heartbeat
            autoping=False
        )

        self.connected_private = True
        self.last_pong_time[StreamType.PRIVATE] = datetime.now()

        logger.info("✅ Private WebSocket connected")

        # Authenticate
        await self._authenticate_private()

        # Subscribe to position topic
        await self._subscribe_private_channels()

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

        await self.private_ws.send_json(auth_msg)
        logger.info("🔐 Private authentication sent")

    async def _subscribe_private_channels(self):
        """Subscribe to private channels"""
        subscribe_msg = {
            "op": "subscribe",
            "args": ["position"]
        }

        await self.private_ws.send_json(subscribe_msg)
        logger.info("✅ Subscribed to position channel")

    async def _private_message_loop(self):
        """Receive and process private messages"""
        async for msg in self.private_ws:
            if not self.running:
                break

            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self._process_private_message(data)

            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("Private WebSocket closed")
                self.connected_private = False
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"Private WebSocket error: {msg.data}")
                self.connected_private = False
                break

    async def _process_private_message(self, data: Dict):
        """Process private WebSocket message"""
        op = data.get('op')

        # Authentication response
        if op == 'auth':
            if data.get('success'):
                logger.info("✅ Private authentication successful")
            else:
                logger.error(f"❌ Private authentication failed: {data}")

        # Subscription response
        elif op == 'subscribe':
            if data.get('success'):
                logger.info(f"✅ Private subscription successful")
            else:
                logger.error(f"❌ Private subscription failed: {data}")

        # Pong response
        elif op == 'pong':
            self.last_pong_time[StreamType.PRIVATE] = datetime.now()

        # Position update
        elif 'topic' in data and data['topic'] == 'position':
            await self._on_position_update(data.get('data', []))

    async def _on_position_update(self, positions: list):
        """
        Handle position update from private WebSocket

        Triggers:
        - Position opened/closed/modified
        - SL/TP updated
        - Size changed
        """
        self.stats['position_updates'] += 1

        for pos in positions:
            symbol = pos['symbol']
            size = float(pos.get('size', 0))

            logger.info(f"📊 Position update: {symbol}, size={size}")

            if size > 0:
                # Position active
                position_data = {
                    'symbol': symbol,
                    'side': pos.get('side'),
                    'size': size,
                    'entry_price': float(pos.get('avgPrice', 0)),
                    'mark_price': float(pos.get('markPrice', 0)),
                    'unrealized_pnl': float(pos.get('unrealisedPnl', 0)),
                    'leverage': float(pos.get('leverage', 1)),
                    'position_status': pos.get('positionStatus', 'Normal'),
                    'stop_loss': float(pos.get('stopLoss', 0)),
                    'take_profit': float(pos.get('takeProfit', 0))
                }

                # Store position
                old_data = self.positions.get(symbol)
                self.positions[symbol] = position_data

                # Subscribe to ticker if new position
                if not old_data:
                    await self._request_ticker_subscription(symbol, subscribe=True)

                # Use cached mark price if available
                if symbol in self.mark_prices:
                    position_data['mark_price'] = self.mark_prices[symbol]

                # Emit event
                await self._emit_combined_event(symbol, position_data)

            else:
                # Position closed
                if symbol in self.positions:
                    logger.info(f"📍 Position closed: {symbol}")
                    del self.positions[symbol]

                    # Unsubscribe from ticker
                    await self._request_ticker_subscription(symbol, subscribe=False)

                    # Emit closure event
                    await self._emit_combined_event(symbol, {
                        'symbol': symbol,
                        'size': 0,
                        'status': 'closed'
                    })

    # ============== PUBLIC WEBSOCKET ==============

    async def _run_public_stream(self):
        """Run public WebSocket for ticker updates"""
        while self.running:
            try:
                await self._connect_public()
                await self._public_message_loop()
            except Exception as e:
                logger.error(f"Public stream error: {e}")
                self.connected_public = False
                await asyncio.sleep(5)

    async def _connect_public(self):
        """Connect to public WebSocket"""
        if self.connected_public:
            return

        logger.info(f"🌐 Connecting to public WebSocket: {self.public_ws_url}")

        # Create session
        if not self.public_session or self.public_session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.public_session = aiohttp.ClientSession(timeout=timeout)

        # Connect
        self.public_ws = await self.public_session.ws_connect(
            self.public_ws_url,
            heartbeat=None,
            autoping=False
        )

        self.connected_public = True
        self.last_pong_time[StreamType.PUBLIC] = datetime.now()

        logger.info("✅ Public WebSocket connected")

        # Restore ticker subscriptions for active positions
        await self._restore_ticker_subscriptions()

    async def _restore_ticker_subscriptions(self):
        """Restore ticker subscriptions after reconnection"""
        if not self.positions:
            logger.info("No active positions to restore ticker subscriptions")
            return

        symbols = list(self.positions.keys())
        logger.info(f"Restoring ticker subscriptions for {len(symbols)} positions")

        for symbol in symbols:
            await self._subscribe_ticker(symbol)

    async def _public_message_loop(self):
        """Receive and process public messages"""
        async for msg in self.public_ws:
            if not self.running:
                break

            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self._process_public_message(data)

            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("Public WebSocket closed")
                self.connected_public = False
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"Public WebSocket error: {msg.data}")
                self.connected_public = False
                break

    async def _process_public_message(self, data: Dict):
        """Process public WebSocket message"""
        op = data.get('op')

        # Subscription response
        if op == 'subscribe':
            if data.get('success'):
                logger.debug(f"✅ Public subscription successful")
            else:
                logger.error(f"❌ Public subscription failed: {data}")

        # Pong response
        elif op == 'pong':
            self.last_pong_time[StreamType.PUBLIC] = datetime.now()

        # Ticker update
        elif 'topic' in data and data['topic'].startswith('tickers.'):
            await self._on_ticker_update(data.get('data', {}))

    async def _on_ticker_update(self, ticker_data: Dict):
        """
        Handle ticker update from public WebSocket

        Update frequency: ~100ms for derivatives
        """
        self.stats['ticker_updates'] += 1

        symbol = ticker_data.get('symbol')
        mark_price = float(ticker_data.get('markPrice', 0))

        if not symbol or not mark_price:
            return

        # Update cache
        old_price = self.mark_prices.get(symbol)
        self.mark_prices[symbol] = mark_price

        # If we have position for this symbol, emit combined event
        if symbol in self.positions:
            position_data = self.positions[symbol].copy()
            position_data['mark_price'] = mark_price

            # Only emit if price changed (avoid spam)
            if old_price is None or abs(mark_price - old_price) > 0:
                await self._emit_combined_event(symbol, position_data)

    # ============== SUBSCRIPTION MANAGEMENT ==============

    async def _request_ticker_subscription(self, symbol: str, subscribe: bool):
        """Request ticker subscription/unsubscription"""
        await self.pending_subscriptions.put({
            'symbol': symbol,
            'subscribe': subscribe
        })

    async def _subscribe_ticker(self, symbol: str):
        """Subscribe to ticker for symbol"""
        if not self.connected_public:
            logger.warning(f"Cannot subscribe to {symbol}: public WS not connected")
            return

        if symbol in self.subscribed_tickers:
            logger.debug(f"Already subscribed to ticker: {symbol}")
            return

        subscribe_msg = {
            "op": "subscribe",
            "args": [f"tickers.{symbol}"]
        }

        await self.public_ws.send_json(subscribe_msg)
        self.subscribed_tickers.add(symbol)
        self.stats['subscriptions'] += 1

        logger.info(f"✅ Subscribed to ticker: {symbol}")

    async def _unsubscribe_ticker(self, symbol: str):
        """Unsubscribe from ticker for symbol"""
        if not self.connected_public:
            return

        if symbol not in self.subscribed_tickers:
            return

        unsubscribe_msg = {
            "op": "unsubscribe",
            "args": [f"tickers.{symbol}"]
        }

        await self.public_ws.send_json(unsubscribe_msg)
        self.subscribed_tickers.discard(symbol)
        self.stats['unsubscriptions'] += 1

        logger.info(f"❌ Unsubscribed from ticker: {symbol}")

    async def _process_subscription_requests(self):
        """Process pending subscription requests"""
        while self.running:
            try:
                request = await asyncio.wait_for(
                    self.pending_subscriptions.get(),
                    timeout=1.0
                )

                symbol = request['symbol']
                subscribe = request['subscribe']

                if subscribe:
                    await self._subscribe_ticker(symbol)
                else:
                    await self._unsubscribe_ticker(symbol)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Subscription processing error: {e}")

    # ============== EVENT PROCESSING ==============

    async def _emit_combined_event(self, symbol: str, data: Dict):
        """Emit combined event to event queue"""
        event = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'data': data
        }
        await self.event_queue.put(event)

    async def _process_events(self):
        """Process event queue and emit to handler"""
        while self.running:
            try:
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )

                self.stats['combined_events'] += 1

                # Emit to handler if set
                if self.event_handler:
                    await self.event_handler('position_update', {
                        'exchange': 'bybit',
                        'data': event['data']
                    })

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event processing error: {e}")

    # ============== HEARTBEAT ==============

    async def _heartbeat_loop(self):
        """Send ping to both WebSockets every 20 seconds"""
        while self.running:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                # Ping private WS
                if self.connected_private and self.private_ws:
                    await self.private_ws.send_json({"op": "ping"})
                    self.last_ping_time[StreamType.PRIVATE] = datetime.now()

                # Ping public WS
                if self.connected_public and self.public_ws:
                    await self.public_ws.send_json({"op": "ping"})
                    self.last_ping_time[StreamType.PUBLIC] = datetime.now()

                # Check for missing pongs (heartbeat timeout)
                await self._check_heartbeat_health()

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    async def _check_heartbeat_health(self):
        """Check if pongs are received within timeout"""
        now = datetime.now()
        timeout = timedelta(seconds=90)  # 90s timeout

        # Check private WS
        if self.connected_private:
            time_since_pong = now - self.last_pong_time[StreamType.PRIVATE]
            if time_since_pong > timeout:
                logger.warning(f"Private WS heartbeat timeout ({time_since_pong.seconds}s)")
                self.connected_private = False
                if self.private_ws:
                    await self.private_ws.close()

        # Check public WS
        if self.connected_public:
            time_since_pong = now - self.last_pong_time[StreamType.PUBLIC]
            if time_since_pong > timeout:
                logger.warning(f"Public WS heartbeat timeout ({time_since_pong.seconds}s)")
                self.connected_public = False
                if self.public_ws:
                    await self.public_ws.close()

    # ============== STATISTICS ==============

    def get_stats(self) -> Dict:
        """Get stream statistics"""
        return {
            **self.stats,
            'connected_private': self.connected_private,
            'connected_public': self.connected_public,
            'active_positions': len(self.positions),
            'subscribed_tickers': len(self.subscribed_tickers),
            'cached_prices': len(self.mark_prices)
        }

    def get_status(self) -> Dict:
        """Get detailed status"""
        return {
            'running': self.running,
            'private': {
                'connected': self.connected_private,
                'last_pong': self.last_pong_time[StreamType.PRIVATE].isoformat()
            },
            'public': {
                'connected': self.connected_public,
                'last_pong': self.last_pong_time[StreamType.PUBLIC].isoformat()
            },
            'positions': list(self.positions.keys()),
            'subscribed_tickers': list(self.subscribed_tickers),
            'stats': self.get_stats()
        }
```

---

## Integration with main.py

```python
# File: main.py
# Location: Lines 218-254 (replace current Bybit setup)

elif name == 'bybit':
    # Check if we're on testnet
    is_testnet = config.testnet

    if is_testnet:
        # Use adaptive stream for testnet (REST polling)
        logger.info("🔧 Using AdaptiveStream for Bybit testnet")
        from websocket.adaptive_stream import AdaptiveBybitStream

        exchange = self.exchanges.get(name)
        if exchange:
            stream = AdaptiveBybitStream(exchange, is_testnet=True)

            async def on_position_update(positions):
                if positions:
                    logger.info(f"📊 REST polling (Bybit): received {len(positions)} position updates")
                for symbol, pos_data in positions.items():
                    await self._handle_stream_event('position.update', pos_data)

            stream.set_callback('position_update', on_position_update)

            asyncio.create_task(stream.start())
            self.websockets[name] = stream
            logger.info(f"✅ {name.capitalize()} AdaptiveStream ready (testnet)")
    else:
        # ========== NEW: Use Hybrid WebSocket for mainnet ==========
        logger.info("🚀 Using HybridStream for Bybit mainnet")
        from websocket.bybit_hybrid_stream import BybitHybridStream

        api_key = os.getenv('BYBIT_API_KEY')
        api_secret = os.getenv('BYBIT_API_SECRET')

        if api_key and api_secret:
            try:
                hybrid_stream = BybitHybridStream(
                    api_key=api_key,
                    api_secret=api_secret,
                    event_handler=self._handle_stream_event,
                    testnet=False
                )
                await hybrid_stream.start()
                self.websockets[f'{name}_hybrid'] = hybrid_stream
                logger.info(f"✅ {name.capitalize()} Hybrid WebSocket ready (mainnet)")

                # Log initial status
                status = hybrid_stream.get_status()
                logger.info(f"📊 Hybrid Stream Status: {status}")

            except Exception as e:
                logger.error(f"Failed to start Bybit hybrid stream: {e}")
                logger.info("Falling back to REST polling")
                # Fallback to REST polling if hybrid fails
                # ... (use AdaptiveBybitStream as fallback)
        else:
            logger.warning("⚠️ Bybit API credentials missing, cannot use hybrid stream")
```

---

## Event Handler Integration

```python
# File: main.py
# Method: _handle_stream_event

async def _handle_stream_event(self, event: str, data: Dict):
    """
    Handle WebSocket stream events

    Events from BybitHybridStream:
    - 'position_update' with data containing mark_price
    """
    # Route to event router
    await self.event_router.emit(event, data, source='websocket')

    # Log high-frequency events at debug level
    if event == 'position_update':
        symbol = data.get('data', {}).get('symbol')
        mark_price = data.get('data', {}).get('mark_price')
        logger.debug(f"Position update: {symbol} @ ${mark_price}")
```

---

## Position Manager Integration

**No changes needed!** Position Manager already handles `position.update` events:

```python
# File: core/position_manager.py
# Lines: 907-909

@self.event_router.on('position.update')
async def handle_position_update(data: Dict):
    await self._on_position_update(data)
```

The `_on_position_update` method will receive:
```python
{
    'exchange': 'bybit',
    'data': {
        'symbol': '1000NEIROCTOUSDT',
        'mark_price': 0.1950,
        'size': 30.0,
        'side': 'Sell',
        'entry_price': 0.1945,
        'unrealized_pnl': -0.15,
        ...
    }
}
```

And will update:
```python
position.current_price = float(data.get('mark_price', position.current_price))
```

Then notify Unified Protection → Trailing Stop

---

## Trailing Stop Integration

**No changes needed!** TS receives updates via Unified Protection:

```python
# File: protection/trailing_stop.py
# Method: update_price (line 407)

async def update_price(self, symbol: str, price: float) -> Optional[Dict]:
    """
    Update price and check trailing stop

    Called by Position Manager when price updates
    """
    instance = self.instances.get(symbol)
    if not instance:
        return None

    # Update current price
    instance.current_price = Decimal(str(price))

    # Update highest/lowest price
    if instance.side == 'long':
        if price > instance.highest_price:
            instance.highest_price = Decimal(str(price))
    else:
        if price < instance.lowest_price:
            instance.lowest_price = Decimal(str(price))

    # Check activation and update SL if needed
    result = await self._check_and_update(symbol, instance)

    return result
```

**With 100ms updates, TS will react much faster!**

---

Continue to HYBRID_WS_TESTING.md for test strategy...
