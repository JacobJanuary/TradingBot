"""
Bybit WebSocket Stream Handler with improved reconnection
"""
import asyncio
import json
import logging
import hmac
import hashlib
import time
from typing import Dict, Optional, Callable
from datetime import datetime
from .improved_stream import ImprovedStream, ConnectionState

logger = logging.getLogger(__name__)


class BybitPrivateStream(ImprovedStream):
    """
    Bybit private WebSocket stream for account updates with improved reconnection
    """
    
    def __init__(self, config: Dict, api_key: str, api_secret: str, 
                 event_handler: Optional[Callable] = None):
        super().__init__("Bybit", config, event_handler)
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = config.get('testnet', False)
        
        # Base URLs for UNIFIED account with max_active_time parameter
        if self.testnet:
            self.ws_base = "wss://stream-testnet.bybit.com/v5/private?max_active_time=180s"
        else:
            self.ws_base = "wss://stream.bybit.com/v5/private?max_active_time=180s"

    async def _get_ws_url(self) -> str:
        """Get WebSocket URL for Bybit with extended connection time"""
        return self.ws_base
    
    async def _authenticate(self):
        """Authenticate WebSocket connection"""
        expires = int((time.time() + 10) * 1000)
        signature = self._generate_signature(expires)
        
        auth_message = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }
        
        await self.send_message(auth_message)
        logger.info("Bybit authentication message sent")
    
    def _generate_signature(self, expires: int) -> str:
        """Generate authentication signature"""
        param_str = f"GET/realtime{expires}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def _subscribe_channels(self):
        """Subscribe to private channels"""
        channels = [
            "position",
            "order",
            "execution",
            "wallet"
        ]
        
        subscribe_msg = {
            "op": "subscribe",
            "args": channels
        }
        
        await self.send_message(subscribe_msg)
        logger.info(f"Subscribed to Bybit channels: {channels}")
    
    async def _process_message(self, msg: Dict):
        """Process Bybit message"""
        op = msg.get('op')
        
        # Handle operation responses
        if op == 'auth':
            if msg.get('success'):
                logger.info("Bybit authentication successful")
            else:
                logger.error(f"Bybit authentication failed: {msg}")
                self.state = ConnectionState.FAILED
        
        elif op == 'subscribe':
            if msg.get('success'):
                logger.info(f"Subscription successful: {msg.get('req_id')}")
            else:
                logger.error(f"Subscription failed: {msg}")
        
        elif op == 'pong':
            self.last_pong = datetime.now()
        
        # Handle data updates
        elif 'topic' in msg:
            topic = msg['topic']
            data = msg.get('data', [])
            
            if topic == 'position':
                await self._process_position_update(data)
            elif topic == 'order':
                await self._process_order_update(data)
            elif topic == 'execution':
                await self._process_execution_update(data)
            elif topic == 'wallet':
                await self._process_wallet_update(data)
    
    async def _process_position_update(self, data: list):
        """Process position updates"""
        for position in data:
            try:
                # CRITICAL fields - must be present, fail if missing
                if 'symbol' not in position:
                    logger.error(f"Position update missing 'symbol' field: {position}")
                    continue
                if 'side' not in position:
                    logger.error(f"Position update missing 'side' field for {position.get('symbol')}: {position}")
                    continue
                if 'size' not in position:
                    logger.error(f"Position update missing 'size' field for {position.get('symbol')}: {position}")
                    continue

                position_data = {
                    'symbol': position['symbol'],
                    'side': position['side'],
                    'size': float(position['size']),
                    'position_value': float(position.get('positionValue', 0)),
                    'entry_price': float(position.get('avgPrice', 0)),
                    'mark_price': float(position.get('markPrice', 0)),
                    'unrealized_pnl': float(position.get('unrealisedPnl', 0)),
                    'realized_pnl': float(position.get('realisedPnl', 0)),
                    'leverage': float(position.get('leverage', 1)),
                    'position_status': position.get('positionStatus', 'Normal'),
                    'stop_loss': float(position.get('stopLoss', 0)),
                    'take_profit': float(position.get('takeProfit', 0))
                }

                if self.event_handler:
                    await self.event_handler('position_update', {
                        'exchange': 'bybit',
                        'data': position_data
                    })

                # Log important events
                if position_data['size'] == 0:
                    logger.info(f"Position closed: {position_data['symbol']}")
                elif position_data['unrealized_pnl'] < -100:
                    logger.warning(f"Large loss on {position_data['symbol']}: ${position_data['unrealized_pnl']:.2f}")
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing position update: {e}, data: {position}")
    
    async def _process_order_update(self, data: list):
        """Process order updates"""
        for order in data:
            try:
                # CRITICAL fields - must be present, fail if missing
                if 'symbol' not in order:
                    logger.error(f"Order update missing 'symbol' field: {order}")
                    continue
                if 'orderId' not in order:
                    logger.error(f"Order update missing 'orderId' field for {order.get('symbol')}: {order}")
                    continue
                if 'side' not in order:
                    logger.error(f"Order update missing 'side' field for {order.get('symbol')}: {order}")
                    continue
                if 'orderStatus' not in order:
                    logger.error(f"Order update missing 'orderStatus' field for {order.get('symbol')}: {order}")
                    continue

                order_data = {
                    'symbol': order['symbol'],
                    'order_id': order['orderId'],
                    'client_order_id': order.get('orderLinkId'),
                    'side': order['side'],
                    'order_type': order.get('orderType', 'Unknown'),
                    'price': float(order.get('price', 0)),
                    'quantity': float(order.get('qty', 0)),
                    'executed_qty': float(order.get('cumExecQty', 0)),
                    'status': order['orderStatus'],
                    'time_in_force': order.get('timeInForce'),
                    'reduce_only': order.get('reduceOnly', False),
                    'stop_order_type': order.get('stopOrderType'),
                    'trigger_price': float(order.get('triggerPrice', 0)),
                    'created_time': order.get('createdTime', '')
                }

                if self.event_handler:
                    await self.event_handler('order_update', {
                        'exchange': 'bybit',
                        'data': order_data
                    })

                # Log important events
                if order_data['status'] == 'New':
                    logger.info(f"New order: {order_data['symbol']} {order_data['side']} {order_data['order_type']}")
                elif order_data['status'] == 'Filled':
                    logger.info(f"Order filled: {order_data['symbol']} {order_data['side']}")

                    if order_data['stop_order_type']:
                        if 'StopLoss' in order_data['stop_order_type']:
                            logger.warning(f"⚠️ STOP LOSS TRIGGERED for {order_data['symbol']}")
                        elif 'TakeProfit' in order_data['stop_order_type']:
                            logger.info(f"✅ TAKE PROFIT TRIGGERED for {order_data['symbol']}")
                elif order_data['status'] == 'Cancelled':
                    logger.info(f"Order cancelled: {order_data['order_id']}")
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing order update: {e}, data: {order}")
    
    async def _process_execution_update(self, data: list):
        """Process trade execution updates"""
        for execution in data:
            exec_data = {
                'symbol': execution['symbol'],
                'order_id': execution['orderId'],
                'exec_id': execution['execId'],
                'side': execution['side'],
                'price': float(execution['execPrice']),
                'quantity': float(execution['execQty']),
                'fee': float(execution.get('execFee', 0)),
                'fee_rate': float(execution.get('feeRate', 0)),
                'exec_type': execution['execType'],
                'exec_time': execution['execTime']
            }
            
            if self.event_handler:
                await self.event_handler('execution', {
                    'exchange': 'bybit',
                    'data': exec_data
                })
    
    async def _process_wallet_update(self, data: list):
        """Process wallet balance updates"""
        for wallet in data:
            for coin in wallet.get('coin', []):
                balance_data = {
                    'coin': coin['coin'],
                    'equity': float(coin.get('equity', 0)),
                    'wallet_balance': float(coin.get('walletBalance', 0)),
                    'available_balance': float(coin.get('availableToWithdraw', 0)),
                    'unrealized_pnl': float(coin.get('unrealisedPnl', 0)),
                    'realized_pnl': float(coin.get('realisedPnl', 0)),
                    'cum_realized_pnl': float(coin.get('cumRealisedPnl', 0))
                }
                
                if self.event_handler:
                    await self.event_handler('balance_update', {
                        'exchange': 'bybit',
                        'data': balance_data
                    })
                
                # Log significant balance changes
                if abs(balance_data['realized_pnl']) > 10:
                    logger.info(f"PnL realized: {balance_data['coin']} ${balance_data['realized_pnl']:.2f}")


class BybitMarketStream(ImprovedStream):
    """
    Bybit public WebSocket stream for market data
    """
    
    def __init__(self, config: Dict, symbols: list, 
                 event_handler: Optional[Callable] = None):
        super().__init__("BybitMarket", config, event_handler)
        self.symbols = symbols
        self.testnet = config.get('testnet', False)
        
        # Base URL
        if self.testnet:
            self.ws_base = "wss://stream-testnet.bybit.com/v5/public/linear"
        else:
            self.ws_base = "wss://stream.bybit.com/v5/public/linear"
    
    async def _get_ws_url(self) -> str:
        """Get WebSocket URL for market data"""
        return self.ws_base
    
    async def _authenticate(self):
        """No authentication needed for public streams"""
        pass
    
    async def _subscribe_channels(self):
        """Subscribe to market data channels"""
        channels = []
        
        for symbol in self.symbols[:10]:  # Limit to 10 symbols
            channels.extend([
                f"orderbook.50.{symbol}",
                f"publicTrade.{symbol}",
                f"tickers.{symbol}"
            ])
        
        subscribe_msg = {
            "op": "subscribe",
            "args": channels
        }
        
        await self.send_message(subscribe_msg)
        logger.info(f"Subscribed to {len(channels)} Bybit market channels")
    
    async def _process_message(self, msg: Dict):
        """Process market data message"""
        if 'topic' in msg:
            topic = msg['topic']
            data = msg.get('data')
            
            if 'orderbook' in topic:
                await self._process_orderbook(topic, data)
            elif 'publicTrade' in topic:
                await self._process_trades(topic, data)
            elif 'tickers' in topic:
                await self._process_ticker(topic, data)
    
    async def _process_orderbook(self, topic: str, data: Dict):
        """Process order book data"""
        symbol = topic.split('.')[-1]
        
        orderbook_data = {
            'symbol': symbol,
            'bids': [[float(b[0]), float(b[1])] for b in data.get('b', [])[:5]],
            'asks': [[float(a[0]), float(a[1])] for a in data.get('a', [])[:5]],
            'timestamp': data.get('u')
        }
        
        if self.event_handler:
            await self.event_handler('orderbook', {
                'exchange': 'bybit',
                'data': orderbook_data
            })
    
    async def _process_trades(self, topic: str, data: list):
        """Process public trade data"""
        symbol = topic.split('.')[-1]
        
        for trade in data:
            trade_data = {
                'symbol': symbol,
                'price': float(trade['p']),
                'quantity': float(trade['v']),
                'side': trade['S'],
                'trade_id': trade['i'],
                'timestamp': trade['T']
            }
            
            if self.event_handler:
                await self.event_handler('trade', {
                    'exchange': 'bybit',
                    'data': trade_data
                })
    
    async def _process_ticker(self, topic: str, data: Dict):
        """Process ticker data"""
        ticker_data = {
            'symbol': data['symbol'],
            'last_price': float(data.get('lastPrice', 0)),
            'bid_price': float(data.get('bid1Price', 0)),
            'ask_price': float(data.get('ask1Price', 0)),
            'volume_24h': float(data.get('volume24h', 0)),
            'turnover_24h': float(data.get('turnover24h', 0)),
            'price_24h_pcnt': float(data.get('price24hPcnt', 0)),
            'high_24h': float(data.get('highPrice24h', 0)),
            'low_24h': float(data.get('lowPrice24h', 0))
        }
        
        if self.event_handler:
            await self.event_handler('ticker', {
                'exchange': 'bybit',
                'data': ticker_data
            })