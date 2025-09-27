"""
Base WebSocket Stream Handler
Based on:
- https://github.com/sammchardy/python-binance/blob/master/binance/streams.py
- https://github.com/hummingbot/hummingbot/blob/master/hummingbot/core/data_type/
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Callable, Optional, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class StreamEvent(Enum):
    """WebSocket event types"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"

    # Market events
    TICKER = "ticker"
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    KLINE = "kline"

    # Account events
    POSITION_UPDATE = "position_update"
    ORDER_UPDATE = "order_update"
    BALANCE_UPDATE = "balance_update"
    MARGIN_CALL = "margin_call"


class BaseStream(ABC):
    """
    Abstract base class for WebSocket streams
    Implements reconnection logic and error handling
    """

    def __init__(self,
                 name: str,
                 config: Dict,
                 event_handler: Optional[Callable] = None):
        """
        Initialize stream handler

        Args:
            name: Exchange name
            config: WebSocket configuration
            event_handler: Callback for events
        """
        self.name = name
        self.config = config
        self.event_handler = event_handler

        # Connection state
        self.connected = False
        self.connecting = False
        self.should_stop = False

        # WebSocket connection
        self.ws = None
        self.ping_task = None
        self.receive_task = None

        # Reconnection settings
        self.reconnect_delay = config.get('ws_reconnect_delay', 5)
        self.max_reconnect_attempts = config.get('ws_max_reconnect_attempts', 10)
        self.reconnect_count = 0

        # Heartbeat settings
        self.heartbeat_interval = config.get('ws_heartbeat_interval', 30)
        self.last_heartbeat = datetime.now()
        self.heartbeat_timeout = config.get('ws_timeout', 60)

        # Event callbacks
        self.event_callbacks = {}

        # Statistics
        self.stats = {
            'messages_received': 0,
            'errors': 0,
            'reconnections': 0,
            'last_message': None
        }

        logger.info(f"{self.name} WebSocket stream initialized")

    @abstractmethod
    async def _get_ws_url(self) -> str:
        """Get WebSocket URL for connection"""
        pass

    @abstractmethod
    async def _authenticate(self):
        """Authenticate WebSocket connection if needed"""
        pass

    @abstractmethod
    async def _subscribe_channels(self):
        """Subscribe to required channels"""
        pass

    @abstractmethod
    async def _process_message(self, msg: Dict):
        """Process incoming message"""
        pass

    async def connect(self):
        """Establish WebSocket connection with retry logic"""
        if self.connected or self.connecting:
            logger.warning(f"{self.name} already connected or connecting")
            return

        self.connecting = True
        self.should_stop = False

        while not self.should_stop and self.reconnect_count < self.max_reconnect_attempts:
            try:
                await self._connect_ws()

                # Reset reconnect count on successful connection
                self.reconnect_count = 0

                # Start tasks
                self.ping_task = asyncio.create_task(self._ping_loop())
                self.receive_task = asyncio.create_task(self._receive_loop())

                # Wait for tasks
                await asyncio.gather(self.ping_task, self.receive_task)

            except Exception as e:
                logger.error(f"{self.name} WebSocket error: {e}")
                self.stats['errors'] += 1

                if not self.should_stop:
                    self.reconnect_count += 1
                    delay = min(self.reconnect_delay * (2 ** self.reconnect_count), 60)
                    logger.info(f"Reconnecting in {delay} seconds (attempt {self.reconnect_count})")
                    await asyncio.sleep(delay)
                    self.stats['reconnections'] += 1

        self.connecting = False

        if self.reconnect_count >= self.max_reconnect_attempts:
            logger.error(f"{self.name} max reconnection attempts reached")
            await self._emit_event(StreamEvent.ERROR, {
                'error': 'Max reconnection attempts reached'
            })

    async def _connect_ws(self):
        """Establish WebSocket connection"""
        import aiohttp

        ws_url = await self._get_ws_url()
        logger.info(f"Connecting to {self.name} WebSocket: {ws_url}")

        # Create session and connect
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(ws_url, heartbeat=self.heartbeat_interval)

        self.connected = True
        self.last_heartbeat = datetime.now()

        logger.info(f"{self.name} WebSocket connected")

        # Authenticate if needed
        await self._authenticate()

        # Subscribe to channels
        await self._subscribe_channels()

        # Emit connected event
        await self._emit_event(StreamEvent.CONNECTED, {})

    async def disconnect(self):
        """Disconnect WebSocket"""
        logger.info(f"Disconnecting {self.name} WebSocket")

        self.should_stop = True
        self.connected = False

        # Cancel tasks
        if self.ping_task:
            self.ping_task.cancel()
        if self.receive_task:
            self.receive_task.cancel()

        # Close WebSocket
        if self.ws:
            await self.ws.close()

        # Close session
        if hasattr(self, 'session'):
            await self.session.close()

        # Emit disconnected event
        await self._emit_event(StreamEvent.DISCONNECTED, {})

        logger.info(f"{self.name} WebSocket disconnected")

    async def _receive_loop(self):
        """Main loop for receiving messages"""
        async for msg in self.ws:
            if self.should_stop:
                break

            self.last_heartbeat = datetime.now()
            self.stats['messages_received'] += 1
            self.stats['last_message'] = datetime.now()

            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = msg.json()
                    await self._process_message(data)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    self.stats['errors'] += 1

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {msg.data}")
                self.stats['errors'] += 1
                break

            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("WebSocket closed by server")
                break

    async def _ping_loop(self):
        """Send periodic ping to keep connection alive"""
        while not self.should_stop and self.connected:
            try:
                # Check if connection is stale
                time_since_heartbeat = (datetime.now() - self.last_heartbeat).seconds

                if time_since_heartbeat > self.heartbeat_timeout:
                    logger.warning(f"{self.name} connection stale, reconnecting")
                    self.connected = False
                    break

                # Send ping
                await self._send_ping()

                # Wait for next ping
                await asyncio.sleep(self.heartbeat_interval)

            except Exception as e:
                logger.error(f"Ping error: {e}")
                break

    async def _send_ping(self):
        """Send ping message"""
        if self.ws and not self.ws.closed:
            await self.ws.ping()

    async def send_message(self, message: Dict):
        """Send message through WebSocket"""
        if self.ws and not self.ws.closed:
            await self.ws.send_json(message)
        else:
            logger.warning(f"Cannot send message, {self.name} not connected")

    # ============== Event System ==============

    def on(self, event: StreamEvent, callback: Callable):
        """Register event callback"""
        if event not in self.event_callbacks:
            self.event_callbacks[event] = []
        self.event_callbacks[event].append(callback)

    async def _emit_event(self, event: StreamEvent, data: Dict):
        """Emit event to all registered callbacks"""
        # Call specific callbacks
        if event in self.event_callbacks:
            for callback in self.event_callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")

        # Call general event handler
        if self.event_handler:
            try:
                await self.event_handler(event, data)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")

    def get_stats(self) -> Dict:
        """Get stream statistics"""
        return {
            **self.stats,
            'connected': self.connected,
            'reconnect_count': self.reconnect_count,
            'uptime': (datetime.now() - self.last_heartbeat).seconds if self.connected else 0
        }