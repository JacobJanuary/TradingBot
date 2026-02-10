"""
Binance AggTrades WebSocket Stream for Delta Calculation

Provides real-time aggregated trade data for calculating:
- Rolling delta (buy_volume - sell_volume)
- Large trade detection (whale activity)
- Volume momentum indicators

Used by trailing_stop.py for intelligent exit decisions.

Date: 2026-01-02
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Callable, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import deque
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)


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
    

class BinanceAggTradesStream:
    """
    WebSocket stream for Binance Futures Aggregated Trades
    
    Features:
    - Dynamic subscription management (per symbol)
    - Rolling delta calculation with configurable window
    - Large trade detection for whale activity
    - Automatic reconnection with subscription restore
    
    Integration:
    - Called from trailing_stop.py for exit decisions
    - Subscribed when position opens, unsubscribed when closes
    """
    
    # Large trade threshold in USDT
    LARGE_TRADE_THRESHOLD = Decimal('10000')
    
    def __init__(self, testnet: bool = False):
        """
        Initialize AggTrades WebSocket
        
        Args:
            testnet: Use testnet endpoints
        """
        self.testnet = testnet
        
        # URLs
        if testnet:
            self.ws_url = "wss://stream.binance.vision/ws"
        else:
            self.ws_url = "wss://fstream.binance.com/ws"
        
        # WebSocket state
        self.ws = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.connected = False
        
        # Subscription management
        self.subscribed_symbols: Set[str] = set()
        self.pending_subscriptions: Set[str] = set()
        self.subscription_queue: asyncio.Queue = asyncio.Queue()
        self.next_request_id = 1
        
        # Delta state per symbol
        self.delta_states: Dict[str, SymbolDeltaState] = {}
        
        # Tasks
        self.stream_task = None
        self.subscription_task = None
        
        # Reference counting for subscriptions (L-1: initialized here, not via hasattr)
        self._subscription_refcount: Dict[str, int] = {}
        
        # External trade handlers (FIX N-5: proper callback instead of monkey-patch)
        self._trade_handlers: list = []
        
        logger.info(f"BinanceAggTradesStream initialized (testnet={testnet})")
    
    async def start(self):
        """Start WebSocket stream"""
        if self.running:
            logger.warning("AggTradesStream already running")
            return
        
        self.running = True
        
        logger.info("🚀 Starting Binance AggTrades WebSocket...")
        
        self.stream_task = asyncio.create_task(self._run_stream())
        self.subscription_task = asyncio.create_task(self._subscription_manager())
        
        logger.info("✅ Binance AggTrades WebSocket started")
    
    async def stop(self):
        """Stop WebSocket stream"""
        if not self.running:
            return
        
        logger.info("⏹️ Stopping Binance AggTrades WebSocket...")
        
        self.running = False
        
        # Close WebSocket
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        # Close session
        if self.session and not self.session.closed:
            await self.session.close()
        
        # Cancel tasks
        for task in [self.stream_task, self.subscription_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("✅ Binance AggTrades WebSocket stopped")
    
    async def subscribe(self, symbol: str):
        """
        Subscribe to aggTrades for a symbol.
        Reference-counted: multiple subscribers to same symbol are tracked.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
        """
        symbol = symbol.upper()
        
        self._subscription_refcount[symbol] = self._subscription_refcount.get(symbol, 0) + 1
        
        if symbol in self.subscribed_symbols:
            logger.debug(f"[AGGTRADES] Already subscribed to {symbol} (refcount={self._subscription_refcount[symbol]})")
            return
        
        # Initialize delta state
        if symbol not in self.delta_states:
            self.delta_states[symbol] = SymbolDeltaState()
        
        # Add to pending
        self.pending_subscriptions.add(symbol)
        
        # Queue subscription request
        await self.subscription_queue.put(('subscribe', symbol))
        
        logger.info(f"📥 [AGGTRADES] Subscription requested: {symbol} (refcount={self._subscription_refcount[symbol]})")
    
    async def unsubscribe(self, symbol: str):
        """
        Unsubscribe from aggTrades for a symbol.
        Reference-counted: only actually unsubscribes when last subscriber leaves.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
        """
        symbol = symbol.upper()
        
        count = self._subscription_refcount.get(symbol, 0)
        if count > 1:
            self._subscription_refcount[symbol] = count - 1
            logger.debug(f"[AGGTRADES] Decremented refcount for {symbol} to {count - 1}, keeping subscription")
            return
        
        # Last subscriber — actually unsubscribe
        self._subscription_refcount.pop(symbol, None)
        
        if symbol not in self.subscribed_symbols:
            self.pending_subscriptions.discard(symbol)
            return
        
        # Queue unsubscription request
        await self.subscription_queue.put(('unsubscribe', symbol))
        
        logger.info(f"📤 [AGGTRADES] Unsubscription requested: {symbol} (last subscriber)")
    
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
        symbol = symbol.upper()
        
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
        symbol = symbol.upper()
        
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
        symbol = symbol.upper()
        
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
        symbol = symbol.upper()
        
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
    
    # ==================== INTERNAL METHODS ====================
    
    async def _run_stream(self):
        """Main WebSocket loop with reconnection"""
        reconnect_delay = 5
        
        while self.running:
            try:
                logger.info("🔌 [AGGTRADES] Connecting to WebSocket...")
                
                # Create session if needed
                if not self.session or self.session.closed:
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    self.session = aiohttp.ClientSession(timeout=timeout)
                
                # Connect
                self.ws = await self.session.ws_connect(
                    self.ws_url,
                    heartbeat=20,
                    autoping=True
                )
                
                self.connected = True
                reconnect_delay = 5
                
                logger.info("✅ [AGGTRADES] WebSocket connected")
                
                # Restore subscriptions
                await self._restore_subscriptions()
                
                # Message loop
                async for msg in self.ws:
                    if not self.running:
                        break
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            await self._handle_message(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"[AGGTRADES] JSON decode error: {e}")
                        except Exception as e:
                            logger.error(f"[AGGTRADES] Message handling error: {e}")
                    
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("[AGGTRADES] WebSocket closed by server")
                        break
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("[AGGTRADES] WebSocket error")
                        break
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [AGGTRADES] Connection error: {e}")
            
            finally:
                self.connected = False
                
                if self.running:
                    logger.info(f"[AGGTRADES] Reconnecting in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 60)
    
    async def _handle_message(self, data: Dict):
        """Handle incoming aggTrade message"""
        # Check for combined stream format
        if 'stream' in data:
            stream = data.get('stream', '')
            data = data.get('data', {})
        
        event_type = data.get('e')
        
        if event_type == 'aggTrade':
            await self._on_agg_trade(data)
        elif 'result' in data:
            # Subscription response
            request_id = data.get('id')
            if data.get('result') is None:
                logger.debug(f"[AGGTRADES] Subscription confirmed (id={request_id})")
    
    async def _on_agg_trade(self, data: Dict):
        """
        Handle aggTrade event
        
        Payload:
        {
            "e": "aggTrade",
            "E": 1672515782136,    // Event time
            "s": "BTCUSDT",        // Symbol
            "a": 164585123,        // Aggregate trade ID
            "p": "23000.50",       // Price
            "q": "0.015",          // Quantity
            "f": 123456,           // First trade ID
            "l": 123458,           // Last trade ID
            "T": 1672515782120,    // Trade time
            "m": true              // Is buyer the maker?
        }
        """
        symbol = data.get('s', '').upper()
        
        if symbol not in self.delta_states:
            return
        
        state = self.delta_states[symbol]
        
        # Create trade record
        trade = TradeData(
            timestamp=data.get('T', 0) / 1000,  # Convert to seconds
            price=Decimal(str(data.get('p', '0'))),
            quantity=Decimal(str(data.get('q', '0'))),
            is_buyer_maker=data.get('m', False)
        )
        
        # Add to deque (auto-removes oldest if maxlen exceeded)
        state.trades.append(trade)
        state.last_update = asyncio.get_event_loop().time()

        # Notify registered trade handlers (FIX N-5)
        for handler in self._trade_handlers:
            try:
                handler(data)
            except Exception as e:
                logger.debug(f"Trade handler error: {e}")
    
    async def _subscription_manager(self):
        """Process subscription requests from queue"""
        logger.info("📋 [AGGTRADES] Subscription manager started")
        
        while self.running:
            try:
                # Wait for subscription request
                action, symbol = await asyncio.wait_for(
                    self.subscription_queue.get(),
                    timeout=5.0
                )
                
                if not self.connected:
                    # Not connected - will be processed on reconnect
                    if action == 'subscribe':
                        self.pending_subscriptions.add(symbol)
                    continue
                
                if action == 'subscribe':
                    await self._send_subscription(symbol, subscribe=True)
                elif action == 'unsubscribe':
                    await self._send_subscription(symbol, subscribe=False)
            
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AGGTRADES] Subscription manager error: {e}")
                await asyncio.sleep(1)
    
    async def _send_subscription(self, symbol: str, subscribe: bool = True):
        """Send subscription/unsubscription request to WebSocket"""
        if not self.ws or self.ws.closed:
            logger.warning(f"[AGGTRADES] Cannot send subscription - not connected")
            return
        
        stream_name = f"{symbol.lower()}@aggTrade"
        method = "SUBSCRIBE" if subscribe else "UNSUBSCRIBE"
        
        request = {
            "method": method,
            "params": [stream_name],
            "id": self.next_request_id
        }
        self.next_request_id += 1
        
        try:
            await self.ws.send_str(json.dumps(request))
            
            if subscribe:
                self.subscribed_symbols.add(symbol)
                self.pending_subscriptions.discard(symbol)
                logger.info(f"✅ [AGGTRADES] Subscribed to {symbol}")
            else:
                self.subscribed_symbols.discard(symbol)
                logger.info(f"✅ [AGGTRADES] Unsubscribed from {symbol}")
        
        except Exception as e:
            logger.error(f"❌ [AGGTRADES] Failed to {method} {symbol}: {e}")
            if subscribe:
                self.pending_subscriptions.add(symbol)
    
    async def _restore_subscriptions(self):
        """Restore subscriptions after reconnect"""
        # Combine pending and previously subscribed
        symbols_to_restore = self.pending_subscriptions | self.subscribed_symbols
        
        if not symbols_to_restore:
            return
        
        logger.info(f"🔄 [AGGTRADES] Restoring {len(symbols_to_restore)} subscriptions...")
        
        # Clear and rebuild
        self.subscribed_symbols.clear()
        
        for symbol in symbols_to_restore:
            await self._send_subscription(symbol, subscribe=True)
            await asyncio.sleep(0.1)  # Rate limiting
        
        logger.info(f"✅ [AGGTRADES] Restored {len(self.subscribed_symbols)} subscriptions")
