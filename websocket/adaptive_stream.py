#!/usr/bin/env python3
"""
Adaptive WebSocket stream that automatically switches between
testnet (public only) and mainnet (full private stream) modes
"""
import asyncio
import json
import logging
import os
import websockets
from typing import Dict, Optional, Any, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class StreamMode(Enum):
    """WebSocket stream modes"""
    TESTNET = "testnet"  # Public streams only
    MAINNET = "mainnet"  # Full private + public streams

class AdaptiveBinanceStream:
    """
    Adaptive WebSocket stream handler that works with both
    testnet (public only) and mainnet (full functionality)
    """
    
    def __init__(self, client: Any, is_testnet: bool = True):
        self.client = client
        self.is_testnet = is_testnet
        self.mode = StreamMode.TESTNET if is_testnet else StreamMode.MAINNET

        # Configure client options to suppress warnings
        if hasattr(client, 'options'):
            client.options['warnOnFetchOpenOrdersWithoutSymbol'] = False

        # State tracking
        self.positions = {}
        self.orders = {}
        self.prices = {}
        self.account_info = {}
        self.running = False
        self.connected = False  # Compatibility attribute
        self.active_symbols = set()  # Track symbols with positions for efficient order fetching

        # WebSocket connections
        self.public_ws = None
        self.private_ws = None
        self.listen_key = None

        # Callbacks
        self.callbacks = {
            'price_update': None,
            'position_update': None,
            'order_update': None,
            'account_update': None
        }

        # URLs based on mode
        if self.is_testnet:
            # For testnet, use production public stream (works better)
            self.public_ws_url = "wss://stream.binancefuture.com/ws"
            self.private_ws_url = None  # Not available on testnet
            logger.info("🔧 AdaptiveStream configured for TESTNET mode (public streams only)")
        else:
            # For mainnet, use full functionality
            self.public_ws_url = "wss://fstream.binance.com/ws"
            self.private_ws_url = "wss://fstream.binance.com/ws/"
            logger.info("🚀 AdaptiveStream configured for MAINNET mode (full functionality)")
    
    def set_callback(self, event_type: str, callback: Callable):
        """Set callback for specific event type"""
        if event_type in self.callbacks:
            self.callbacks[event_type] = callback
    
    async def start(self):
        """Start appropriate streams based on mode"""
        self.running = True
        
        if self.mode == StreamMode.TESTNET:
            await self._start_testnet_mode()
        else:
            await self._start_mainnet_mode()
    
    async def _start_testnet_mode(self):
        """
        Testnet mode: Public streams only + REST polling for private data
        """
        logger.info("Starting TESTNET mode with public streams + REST polling")
        
        # Start public price stream
        public_task = asyncio.create_task(self._run_public_stream())
        
        # Start REST polling for private data
        polling_task = asyncio.create_task(self._poll_private_data())
        
        # Wait for both tasks
        await asyncio.gather(public_task, polling_task)
    
    async def _start_mainnet_mode(self):
        """
        Mainnet mode: Full private + public WebSocket streams
        """
        logger.info("Starting MAINNET mode with full WebSocket functionality")
        
        # Create listen key for private stream
        await self._create_listen_key()
        
        # Start both streams
        public_task = asyncio.create_task(self._run_public_stream())
        private_task = asyncio.create_task(self._run_private_stream())
        
        # Keep listen key alive
        keepalive_task = asyncio.create_task(self._keepalive_listen_key())
        
        # Wait for all tasks
        await asyncio.gather(public_task, private_task, keepalive_task)
    
    async def _run_public_stream(self):
        """Run public price stream (works for both testnet and mainnet)"""
        while self.running:
            try:
                # Get active symbols from positions
                symbols = self._get_active_symbols()
                if not symbols:
                    symbols = ['btcusdt', 'ethusdt']  # Default symbols
                
                streams = [f"{symbol.lower()}@ticker" for symbol in symbols]
                
                async with websockets.connect(self.public_ws_url) as websocket:
                    self.public_ws = websocket
                    self.connected = True  # Mark as connected
                    logger.info(f"✅ Connected to public stream for {len(symbols)} symbols")
                    
                    # Subscribe to streams
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": streams,
                        "id": 1
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    
                    # Listen for updates
                    while self.running:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=30)
                            await self._process_public_message(json.loads(message))
                        except asyncio.TimeoutError:
                            await websocket.ping()
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                logger.error(f"Public stream error: {e}")
                await asyncio.sleep(5)
    
    async def _run_private_stream(self):
        """Run private user data stream (mainnet only)"""
        if not self.listen_key:
            logger.error("No listen key available for private stream")
            return
        
        while self.running:
            try:
                ws_url = f"{self.private_ws_url}{self.listen_key}"
                
                async with websockets.connect(ws_url) as websocket:
                    self.private_ws = websocket
                    logger.info("✅ Connected to private user data stream")
                    
                    while self.running:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=30)
                            await self._process_private_message(json.loads(message))
                        except asyncio.TimeoutError:
                            await websocket.ping()
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                logger.error(f"Private stream error: {e}")
                await asyncio.sleep(5)
    
    async def _poll_private_data(self):
        """Poll REST API for private data (testnet fallback)"""
        logger.info("Starting REST API polling for private data (testnet mode)")
        
        while self.running:
            try:
                # Fetch account data using ccxt methods
                balance = await self.client.fetch_balance()
                account_data = {
                    'B': [{'a': 'USDT', 'wb': balance.get('USDT', {}).get('total', 0)}]
                }
                await self._process_account_update(account_data)
                
                # Fetch positions using ccxt methods
                positions_raw = await self.client.fetch_positions()
                logger.info(f"📊 Fetched {len(positions_raw)} positions from exchange")

                positions = []
                self.active_symbols.clear()  # Reset active symbols

                for pos in positions_raw:
                    if pos['contracts'] > 0:
                        self.active_symbols.add(pos['symbol'])  # Track active symbols
                        positions.append({
                            'symbol': pos['symbol'],
                            'positionAmt': pos['contracts'],
                            'entryPrice': pos['markPrice'] or 0,
                            'unrealizedProfit': pos['unrealizedPnl'] or 0,
                            'markPrice': pos['markPrice'] or 0
                        })

                logger.info(f"📊 Processing {len(positions)} active positions (with contracts > 0)")
                await self._process_positions_update(positions)

                # Fetch open orders more efficiently
                try:
                    if self.active_symbols:
                        # Fetch orders for each active symbol (more efficient)
                        all_orders = []
                        for symbol in self.active_symbols:
                            try:
                                symbol_orders = await self.client.fetch_open_orders(symbol)
                                all_orders.extend(symbol_orders)
                            except Exception as e:
                                logger.debug(f"No orders for {symbol}: {e}")
                        await self._process_orders_update(all_orders)
                    else:
                        # No active positions, fetch all orders
                        orders = await self.client.fetch_open_orders()
                        await self._process_orders_update(orders)
                except Exception as e:
                    logger.debug(f"Order fetch error (non-critical): {e}")
                
                # Wait before next poll (adjust based on needs)
                await asyncio.sleep(5)  # Poll every 5 seconds
                
            except Exception as e:
                logger.error(f"REST polling error: {e}")
                await asyncio.sleep(10)
    
    async def _process_public_message(self, data: Dict):
        """Process public stream message"""
        if 'e' in data and data['e'] == '24hrTicker':
            symbol = data['s']
            price = float(data['c'])
            
            self.prices[symbol] = {
                'price': price,
                'bid': float(data.get('b', price)),
                'ask': float(data.get('a', price)),
                'volume': float(data.get('v', 0)),
                'timestamp': datetime.now()
            }
            
            # Trigger callback
            if self.callbacks['price_update']:
                await self.callbacks['price_update'](symbol, price)
    
    async def _process_private_message(self, data: Dict):
        """Process private stream message (mainnet only)"""
        event_type = data.get('e', '')
        
        if event_type == 'ACCOUNT_UPDATE':
            await self._process_account_update(data['a'])
        elif event_type == 'ORDER_TRADE_UPDATE':
            await self._process_order_update(data['o'])
    
    async def _process_account_update(self, data: Dict):
        """Process account update"""
        # Update account info
        if 'B' in data:  # Balances
            for balance in data['B']:
                asset = balance['a']
                if asset == 'USDT':
                    self.account_info['balance'] = float(balance['wb'])
        
        # Update positions
        if 'P' in data:  # Positions
            for pos in data['P']:
                symbol = pos['s']
                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': 'long' if float(pos['pa']) > 0 else 'short',
                    'quantity': abs(float(pos['pa'])),
                    'entry_price': float(pos['ep']),
                    'unrealized_pnl': float(pos['up']),
                    'margin_type': pos['mt']
                }
        
        # Trigger callback
        if self.callbacks['account_update']:
            await self.callbacks['account_update'](self.account_info)
    
    async def _process_positions_update(self, positions: list):
        """Process positions update from REST"""
        for pos in positions:
            if float(pos['positionAmt']) != 0:
                symbol = pos['symbol']
                self.positions[symbol] = {
                    'symbol': symbol,
                    'side': 'long' if float(pos['positionAmt']) > 0 else 'short',
                    'quantity': abs(float(pos['positionAmt'])),
                    'entry_price': float(pos['entryPrice']),
                    'unrealized_pnl': float(pos['unrealizedProfit']),
                    'mark_price': float(pos['markPrice'])
                }

        # Trigger callback
        logger.info(f"📊 Triggering position_update callback with {len(self.positions)} positions")
        if self.callbacks['position_update']:
            await self.callbacks['position_update'](self.positions)
        else:
            logger.warning("⚠️ position_update callback not set!")
    
    async def _process_orders_update(self, orders: list):
        """Process orders update from REST"""
        for order in orders:
            order_id = order['orderId']
            self.orders[order_id] = {
                'symbol': order['symbol'],
                'side': order['side'],
                'type': order['type'],
                'quantity': float(order['origQty']),
                'price': float(order['price']) if order['price'] else 0,
                'status': order['status']
            }
        
        # Trigger callback
        if self.callbacks['order_update']:
            await self.callbacks['order_update'](self.orders)
    
    async def _process_order_update(self, data: Dict):
        """Process order update from WebSocket"""
        order_id = data['i']
        self.orders[order_id] = {
            'symbol': data['s'],
            'side': data['S'],
            'type': data['o'],
            'quantity': float(data['q']),
            'price': float(data['p']),
            'status': data['X']
        }
        
        # Trigger callback
        if self.callbacks['order_update']:
            await self.callbacks['order_update'](data)
    
    async def _create_listen_key(self):
        """Create listen key for private stream (mainnet only)"""
        if self.is_testnet:
            return  # Skip for testnet
        
        try:
            response = await self.client.futures_stream_get_listen_key()
            self.listen_key = response['listenKey']
            logger.info("✅ Listen key created successfully")
        except Exception as e:
            logger.error(f"Failed to create listen key: {e}")
    
    async def _keepalive_listen_key(self):
        """Keep listen key alive (mainnet only)"""
        if self.is_testnet:
            return
        
        while self.running and self.listen_key:
            try:
                await asyncio.sleep(1800)  # Every 30 minutes
                await self.client.futures_stream_keepalive(self.listen_key)
                logger.debug("Listen key renewed")
            except Exception as e:
                logger.error(f"Failed to renew listen key: {e}")
                await self._create_listen_key()
    
    def _get_active_symbols(self) -> list:
        """Get list of active symbols from positions"""
        symbols = []
        for symbol in self.positions.keys():
            # Convert format: HOME/USDT:USDT -> homeusdt
            clean_symbol = symbol.lower().replace('/', '').replace(':', '')
            if 'usdt' in clean_symbol:
                symbols.append(clean_symbol)
        return symbols
    
    async def stop(self):
        """Stop all streams"""
        self.running = False
        
        if self.public_ws:
            await self.public_ws.close()
        
        if self.private_ws:
            await self.private_ws.close()
        
        if self.listen_key and not self.is_testnet:
            try:
                await self.client.futures_stream_close(self.listen_key)
            except Exception as e:
                logger.debug(f"Failed to close futures stream: {e}")
        
        logger.info("AdaptiveStream stopped")
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol"""
        symbol = symbol.upper().replace('/', '').replace(':', '')
        if symbol in self.prices:
            return self.prices[symbol]['price']
        return None
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position info for symbol"""
        return self.positions.get(symbol)
    
    def is_healthy(self) -> bool:
        """Check if stream is healthy"""
        if self.is_testnet:
            # For testnet, check if we have recent price updates
            if not self.prices:
                return False
            
            # Check if any price is recent (within last 10 seconds)
            now = datetime.now()
            for price_data in self.prices.values():
                if (now - price_data['timestamp']).total_seconds() < 10:
                    return True
            return False
        else:
            # For mainnet, check WebSocket connections
            return bool(self.public_ws and self.private_ws)