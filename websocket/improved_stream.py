"""
Improved WebSocket Stream Handler with better reconnection logic
"""
import asyncio
import aiohttp
import logging
from abc import ABC, abstractmethod
from typing import Dict, Callable, Optional
from datetime import datetime, timedelta
import json
from enum import Enum

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class ImprovedStream(ABC):
    """
    Improved WebSocket stream with robust reconnection
    """

    def __init__(self, name: str, config: Dict, event_handler: Optional[Callable] = None):
        self.name = name
        self.config = config
        self.event_handler = event_handler
        
        # Connection state
        self.state = ConnectionState.DISCONNECTED
        self.connected = False  # Add connected attribute for compatibility
        self.ws = None
        self.session = None
        self.should_stop = False
        
        # Tasks
        self.receive_task = None
        self.heartbeat_task = None
        self.monitor_task = None
        
        # Reconnection settings
        self.reconnect_delay_base = config.get('ws_reconnect_delay', 5)
        self.reconnect_delay_max = config.get('ws_reconnect_delay_max', 60)
        self.max_reconnect_attempts = config.get('ws_max_reconnect_attempts', -1)  # -1 = infinite
        self.reconnect_count = 0
        self.last_reconnect_attempt = None
        
        # Heartbeat settings - CRITICAL FIX: Bybit requires ping every 20s!
        # Check if this is for Bybit
        is_bybit = 'bybit' in name.lower()

        if is_bybit:
            # CRITICAL: Bybit REQUIRES ping every 20 seconds, ignore config
            self.heartbeat_interval = 20  # HARDCODED for Bybit
            self.heartbeat_timeout = 90   # Extended for testnet latency
            logger.info(f"🔧 Bybit detected: forcing heartbeat_interval=20s")
        else:
            # Other exchanges can use config
            self.heartbeat_interval = config.get('ws_heartbeat_interval', 30)
            self.heartbeat_timeout = config.get('ws_heartbeat_timeout', 60)
        self.last_heartbeat = datetime.now()
        self.last_pong = datetime.now()
        self.last_ping_time = datetime.now()  # Track ping time for RTT calculation
        
        # Connection health
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        
        # Statistics
        self.stats = {
            'connected_at': None,
            'disconnected_at': None,
            'messages_received': 0,
            'messages_sent': 0,
            'errors': 0,
            'reconnections': 0,
            'uptime_seconds': 0
        }
        
        logger.info(f"{self.name} WebSocket handler initialized")
    
    @abstractmethod
    async def _get_ws_url(self) -> str:
        """Get WebSocket URL"""
        pass
    
    @abstractmethod
    async def _authenticate(self):
        """Authenticate connection"""
        pass
    
    @abstractmethod
    async def _subscribe_channels(self):
        """Subscribe to channels"""
        pass
    
    @abstractmethod
    async def _process_message(self, msg: Dict):
        """Process incoming message"""
        pass
    
    async def start(self):
        """Start WebSocket connection with monitoring"""
        if self.state != ConnectionState.DISCONNECTED:
            logger.warning(f"{self.name} already started (state: {self.state})")
            return
        
        self.should_stop = False
        
        # Start connection monitor
        self.monitor_task = asyncio.create_task(self._connection_monitor())
        
        logger.info(f"{self.name} WebSocket started")
    
    async def stop(self):
        """Stop WebSocket connection gracefully"""
        logger.info(f"Stopping {self.name} WebSocket...")
        
        self.should_stop = True
        self.state = ConnectionState.DISCONNECTED
        self.connected = False  # CRITICAL FIX: Sync connected attribute with state
        
        # Cancel all tasks
        tasks = [self.receive_task, self.heartbeat_task, self.monitor_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close WebSocket
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        # Close session
        if self.session and not self.session.closed:
            await self.session.close()
        
        self.stats['disconnected_at'] = datetime.now()
        
        logger.info(f"{self.name} WebSocket stopped")
    
    async def _connection_monitor(self):
        """Monitor and maintain connection"""
        while not self.should_stop:
            try:
                if self.state == ConnectionState.DISCONNECTED:
                    await self._connect()
                
                elif self.state == ConnectionState.FAILED:
                    # Wait before retry
                    delay = self._get_reconnect_delay()
                    logger.info(f"Waiting {delay}s before reconnect attempt {self.reconnect_count + 1}")
                    await asyncio.sleep(delay)
                    
                    if self.max_reconnect_attempts == -1 or self.reconnect_count < self.max_reconnect_attempts:
                        await self._connect()
                    else:
                        logger.error(f"{self.name} max reconnection attempts reached")
                        self.should_stop = True
                
                elif self.state == ConnectionState.CONNECTED:
                    # Check connection health
                    if not await self._check_connection_health():
                        logger.warning(f"{self.name} connection unhealthy, reconnecting...")
                        await self._reconnect()
                
                # Small delay to prevent busy loop
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
                await asyncio.sleep(5)
    
    async def _connect(self):
        """Establish WebSocket connection"""
        if self.state == ConnectionState.CONNECTING:
            return
        
        self.state = ConnectionState.CONNECTING
        self.last_reconnect_attempt = datetime.now()
        
        try:
            # Create session if needed
            if not self.session or self.session.closed:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                self.session = aiohttp.ClientSession(timeout=timeout)
            
            # Get URL and connect
            ws_url = await self._get_ws_url()
            logger.info(f"Connecting to {self.name}: {ws_url}")
            
            self.ws = await self.session.ws_connect(
                ws_url,
                heartbeat=None,  # Disable built-in heartbeat as we use custom ping
                autoping=False,  # CRITICAL: Disable auto ping - we send custom JSON ping
                autoclose=False
            )
            
            # Connection successful
            self.state = ConnectionState.CONNECTED
            self.connected = True  # CRITICAL FIX: Sync connected attribute with state
            self.reconnect_count = 0
            self.consecutive_errors = 0
            self.last_heartbeat = datetime.now()
            self.last_pong = datetime.now()
            self.stats['connected_at'] = datetime.now()
            
            logger.info(f"{self.name} WebSocket connected")
            
            # Authenticate and subscribe
            await self._authenticate()
            await self._subscribe_channels()
            
            # Start tasks
            self.receive_task = asyncio.create_task(self._receive_loop())
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Notify connection
            if self.event_handler:
                await self.event_handler('connected', {'exchange': self.name})
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.state = ConnectionState.FAILED
            self.connected = False
            self.reconnect_count += 1
            
            # Clean up
            if self.ws:
                await self.ws.close()
            if self.session and not self.should_stop:
                await self.session.close()
                self.session = None
    
    async def _reconnect(self):
        """Reconnect WebSocket - CRITICAL FIX: Immediate reconnection"""
        if self.state == ConnectionState.RECONNECTING:
            logger.warning(f"Already reconnecting {self.name}")
            return

        logger.critical(f"🔄 IMMEDIATE RECONNECT initiated for {self.name}")

        self.state = ConnectionState.RECONNECTING
        self.stats['reconnections'] += 1

        # Cancel current tasks immediately
        tasks_to_cancel = []
        if self.receive_task and not self.receive_task.done():
            tasks_to_cancel.append(self.receive_task)
        if self.heartbeat_task and not self.heartbeat_task.done():
            tasks_to_cancel.append(self.heartbeat_task)

        for task in tasks_to_cancel:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Force close current connection
        if self.ws:
            try:
                await asyncio.wait_for(self.ws.close(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.error("WebSocket close timeout - forcing closure")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
            finally:
                self.ws = None

        # Reset state for immediate reconnection
        self.state = ConnectionState.DISCONNECTED
        self.connected = False  # CRITICAL FIX: Sync connected attribute with state
        self.last_pong = datetime.now()  # Reset pong timer
        self.last_heartbeat = datetime.now()  # Reset heartbeat timer
        self.consecutive_errors = 0  # Reset error counter

        logger.info(f"✅ {self.name} ready for reconnection")
    
    async def _receive_loop(self):
        """Receive and process messages"""
        try:
            async for msg in self.ws:
                if self.should_stop:
                    break
                
                self.last_heartbeat = datetime.now()
                self.stats['messages_received'] += 1
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)

                        # ENHANCED: Handle various pong formats from Bybit
                        if self._is_custom_pong(data):
                            pong_time = datetime.now()
                            self.last_pong = pong_time

                            # Calculate RTT (Round Trip Time)
                            if hasattr(self, 'last_ping_time'):
                                rtt = (pong_time - self.last_ping_time).total_seconds()
                                logger.info(f"✅ [{self.name}] Custom pong received at {pong_time.strftime('%H:%M:%S')} (RTT: {rtt:.2f}s)")
                            else:
                                logger.info(f"✅ [{self.name}] Custom pong received at {pong_time.strftime('%H:%M:%S')}")

                            logger.debug(f"Pong data: {data}")
                            continue
                        
                        # Process message
                        await self._process_message(data)
                        self.consecutive_errors = 0
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON: {e}")
                        self.consecutive_errors += 1
                    except Exception as e:
                        logger.error(f"Message processing error: {e}")
                        self.consecutive_errors += 1
                        self.stats['errors'] += 1
                        
                        if self.consecutive_errors >= self.max_consecutive_errors:
                            logger.error("Too many consecutive errors, reconnecting...")
                            break
                
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    self.stats['errors'] += 1
                    break
                
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info(f"WebSocket closed: {msg.data}")
                    break
                
                elif msg.type == aiohttp.WSMsgType.PONG:
                    self.last_pong = datetime.now()
        
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
        finally:
            # Trigger reconnection
            if not self.should_stop:
                self.state = ConnectionState.DISCONNECTED
                self.connected = False  # CRITICAL FIX: Sync connected attribute with state
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat/ping - FIXED for Bybit custom ping"""
        while not self.should_stop and self.state == ConnectionState.CONNECTED:
            try:
                # Send custom ping for Bybit (text message, not frame ping)
                if self.ws and not self.ws.closed:
                    ping_time = datetime.now()

                    # CRITICAL FIX: Send custom ping as JSON text message for Bybit
                    custom_ping = {"op": "ping"}
                    await self.ws.send_str(json.dumps(custom_ping))

                    self.last_ping_time = ping_time  # Track ping time for RTT calculation
                    self.stats['messages_sent'] += 1
                    logger.info(f"📤 [{self.name}] Custom ping sent at {ping_time.strftime('%H:%M:%S')}: {custom_ping}")

                await asyncio.sleep(self.heartbeat_interval)

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
    
    async def _check_connection_health(self) -> bool:
        """Check if connection is healthy"""
        if not self.ws or self.ws.closed:
            return False
        
        # Check last heartbeat
        time_since_heartbeat = (datetime.now() - self.last_heartbeat).total_seconds()
        if time_since_heartbeat > self.heartbeat_timeout:
            logger.warning(f"No heartbeat for {time_since_heartbeat:.0f}s")
            return False
        
        # Check last pong - CRITICAL FIX: Force reconnect if no pong
        time_since_pong = (datetime.now() - self.last_pong).total_seconds()

        # IMMEDIATE reconnect if no pong for 120 seconds
        if time_since_pong > 120:
            logger.critical(f"🔴 CRITICAL: No pong for {time_since_pong:.0f}s - FORCE RECONNECT!")
            return False  # This will trigger immediate reconnection

        # Warning if no pong for 2x heartbeat timeout
        if time_since_pong > self.heartbeat_timeout * 2:
            logger.warning(f"⚠️ No pong response for {time_since_pong:.0f}s - connection degraded")
            return False
        
        # Check error rate
        if self.consecutive_errors >= self.max_consecutive_errors:
            logger.warning(f"Too many errors: {self.consecutive_errors}")
            return False
        
        return True
    
    def _is_custom_pong(self, message: Dict) -> bool:
        """Check if message is a custom pong from Bybit - COMPREHENSIVE CHECK"""
        if not isinstance(message, dict):
            return False

        # Check various pong formats used by Bybit
        return (
            message.get("op") == "pong" or
            message.get("ret_msg") == "pong" or
            message.get("type") == "pong" or
            message.get("e") == "pong" or
            (message.get("success") == True and message.get("op") in ["ping", "pong"]) or
            (message.get("op") == "ping" and message.get("success") == True)  # Bybit sometimes returns success for ping
        )

    def _get_reconnect_delay(self) -> int:
        """Calculate exponential backoff delay"""
        delay = min(
            self.reconnect_delay_base * (2 ** min(self.reconnect_count, 5)),
            self.reconnect_delay_max
        )
        return delay
    
    async def send_message(self, message: Dict):
        """Send message to WebSocket"""
        if self.state != ConnectionState.CONNECTED or not self.ws:
            logger.warning(f"Cannot send message, not connected (state: {self.state})")
            return False
        
        try:
            await self.ws.send_str(json.dumps(message))
            self.stats['messages_sent'] += 1
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    def _limit_cache(self, cache: Dict, max_size: int = None) -> None:
        """
        Simple cache limiter - removes oldest entries when size exceeded

        Args:
            cache: Dictionary to limit
            max_size: Maximum size (uses self.max_cache_size if not provided)
        """
        if max_size is None:
            max_size = getattr(self, 'max_cache_size', 100)

        while len(cache) > max_size:
            # Remove oldest entry (FIFO)
            oldest_key = next(iter(cache))
            del cache[oldest_key]

    def get_stats(self) -> Dict:
        """Get connection statistics"""
        stats = self.stats.copy()

        if self.stats['connected_at']:
            if self.state == ConnectionState.CONNECTED:
                uptime = (datetime.now() - self.stats['connected_at']).total_seconds()
            elif self.stats['disconnected_at']:
                uptime = (self.stats['disconnected_at'] - self.stats['connected_at']).total_seconds()
            else:
                uptime = 0
            stats['uptime_seconds'] = uptime

        stats['state'] = self.state.value
        stats['reconnect_count'] = self.reconnect_count

        return stats