"""
Binance WebSocket Stream Handler with improved reconnection
"""
import asyncio
import json
import logging
import hmac
import hashlib
from typing import Dict, Optional, Callable
from datetime import datetime
from .improved_stream import ImprovedStream

logger = logging.getLogger(__name__)


class BinancePrivateStream(ImprovedStream):
    """
    Binance private WebSocket stream for account updates with improved reconnection
    """
    
    def __init__(self, config: Dict, api_key: str, api_secret: str, 
                 event_handler: Optional[Callable] = None):
        super().__init__("Binance", config, event_handler)
        self.api_key = api_key
        self.api_secret = api_secret
        self.listen_key = None
        self.listen_key_task = None
        self.testnet = config.get('testnet', False)
        
        # Base URLs
        if self.testnet:
            self.rest_url = "https://testnet.binance.vision/api/v3"
            self.ws_base = "wss://testnet.binance.vision/ws"
        else:
            self.rest_url = "https://api.binance.com/api/v3"
            self.ws_base = "wss://stream.binance.com:9443/ws"

    async def _create_listen_key(self):
        """Create listen key for user data stream"""
        try:
            import aiohttp
            headers = {'X-MBX-APIKEY': self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.rest_url}/listenKey", headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.listen_key = data.get('listenKey')
                        logger.info("Listen key created")
                    else:
                        logger.error(f"Failed to create listen key: {response.status}")
        except Exception as e:
            logger.error(f"Error creating listen key: {e}")
    
    async def _get_ws_url(self) -> str:
        """Get WebSocket URL with listen key"""
        if not self.listen_key:
            await self._create_listen_key()
        if self.listen_key:
            return f"{self.ws_base}/{self.listen_key}"
        return ""

    async def _fetch_initial_state(self):
        """Fetch initial account state"""
        try:
            # Get account info
            account = await self.client.futures_account()
            self.account_info = {
                'totalWalletBalance': float(account['totalWalletBalance']),
                'totalUnrealizedProfit': float(account['totalUnrealizedProfit']),
                'totalMarginBalance': float(account['totalMarginBalance']),
                'availableBalance': float(account['availableBalance']),
            }

            # Get positions
            positions = await self.client.futures_position_information()
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    self.positions[pos['symbol']] = self._parse_position(pos)

            # Get open orders
            orders = await self.client.futures_get_open_orders()
            for order in orders:
                self.open_orders[order['orderId']] = self._parse_order(order)

            logger.info(f"Initial state: {len(self.positions)} positions, {len(self.open_orders)} orders")

        except Exception as e:
            logger.error(f"Failed to fetch initial state: {e}")


    async def _authenticate(self):
        """Authentication handled by python-binance"""
        pass

    async def _subscribe_channels(self):
        """Subscribe handled by python-binance"""
        pass

    async def connect(self):
        """Connect to Binance user data stream"""
        if not self.client:
            await self.initialize()

        try:
            # Start user data stream
            self.user_stream = self.socket_manager.futures_user_socket()

            # Start listen key refresh task
            self.listen_key_task = asyncio.create_task(self._keep_alive_listen_key())

            # Start receiving messages
            async with self.user_stream as stream:
                self.connected = True
                await self._emit_event(StreamEvent.CONNECTED, {})

                while not self.should_stop:
                    msg = await stream.recv()
                    if msg:
                        await self._process_message(msg)

        except Exception as e:
            logger.error(f"Binance stream error: {e}")
            self.connected = False
            await self._emit_event(StreamEvent.ERROR, {'error': str(e)})
        finally:
            self.connected = False
            if self.listen_key_task:
                self.listen_key_task.cancel()

    async def _keep_alive_listen_key(self):
        """Keep listen key alive by pinging every 30 minutes"""
        while not self.should_stop:
            try:
                await asyncio.sleep(1800)  # 30 minutes
                await self.client.futures_ping()
                logger.debug("Listen key refreshed")
            except Exception as e:
                logger.error(f"Failed to refresh listen key: {e}")

    async def _process_message(self, msg: Dict):
        """Process user data stream message"""
        try:
            event_type = msg.get('e')

            if event_type == 'ACCOUNT_UPDATE':
                await self._handle_account_update(msg)
            elif event_type == 'ORDER_TRADE_UPDATE':
                await self._handle_order_update(msg)
            elif event_type == 'listenKeyExpired':
                logger.warning("Listen key expired, reconnecting")
                self.connected = False
            elif event_type == 'MARGIN_CALL':
                await self._handle_margin_call(msg)
            else:
                logger.debug(f"Unknown event type: {event_type}")

        except Exception as e:
            logger.error(f"Error processing Binance message: {e}")

    async def _handle_account_update(self, msg: Dict):
        """
        Handle account update event
        Includes position updates and balance changes
        """
        data = msg.get('a', {})

        # Update balances
        for balance in data.get('B', []):
            if balance['a'] == 'USDT':
                self.account_info['availableBalance'] = float(balance['wb'])
                self.account_info['walletBalance'] = float(balance['cw'])

                await self._emit_event(StreamEvent.BALANCE_UPDATE, {
                    'asset': 'USDT',
                    'wallet_balance': float(balance['cw']),
                    'available_balance': float(balance['wb']),
                    'timestamp': msg.get('T')
                })

        # Update positions
        for position in data.get('P', []):
            symbol = position['s']
            position_data = {
                'symbol': symbol,
                'side': 'LONG' if float(position['pa']) > 0 else 'SHORT',
                'position_amount': abs(float(position['pa'])),
                'entry_price': float(position['ep']),
                'mark_price': float(position.get('mp', 0)),
                'unrealized_pnl': float(position['up']),
                'realized_pnl': float(position.get('rp', 0)),
                'margin_type': position.get('mt'),
                'isolated_wallet': float(position.get('iw', 0)),
                'position_side': position.get('ps'),
                'timestamp': msg.get('T')
            }

            # Check if position opened/closed
            old_position = self.positions.get(symbol)

            if float(position['pa']) == 0:
                # Position closed
                if old_position:
                    del self.positions[symbol]
                    position_data['event'] = 'CLOSED'
                    logger.info(f"Position {symbol} closed")
            else:
                # Position opened or updated
                if not old_position:
                    position_data['event'] = 'OPENED'
                    logger.info(f"Position {symbol} opened: {position_data['side']}")
                else:
                    position_data['event'] = 'UPDATED'

                    # Check for significant PnL changes
                    pnl_change = position_data['unrealized_pnl'] - old_position.get('unrealized_pnl', 0)
                    if abs(pnl_change) > 1:  # More than $1 change
                        logger.info(f"Position {symbol} PnL change: ${pnl_change:.2f}")

                self.positions[symbol] = position_data

            # Emit position update event
            await self._emit_event(StreamEvent.POSITION_UPDATE, position_data)

    async def _handle_order_update(self, msg: Dict):
        """Handle order update event"""
        order_data = msg.get('o', {})

        order_info = {
            'symbol': order_data['s'],
            'order_id': order_data['i'],
            'client_order_id': order_data.get('c'),
            'side': order_data['S'],
            'type': order_data['o'],
            'time_in_force': order_data.get('f'),
            'quantity': float(order_data['q']),
            'price': float(order_data.get('p', 0)),
            'stop_price': float(order_data.get('sp', 0)),
            'execution_type': order_data['x'],
            'status': order_data['X'],
            'reject_reason': order_data.get('r'),
            'filled_quantity': float(order_data.get('z', 0)),
            'last_filled_quantity': float(order_data.get('l', 0)),
            'average_price': float(order_data.get('ap', 0)),
            'commission': float(order_data.get('n', 0)),
            'commission_asset': order_data.get('N'),
            'timestamp': order_data['T'],
            'is_reduce_only': order_data.get('R', False),
            'is_close_position': order_data.get('cp', False),
            'activation_price': float(order_data.get('AP', 0)),
            'callback_rate': float(order_data.get('cr', 0)),
            'realized_profit': float(order_data.get('rp', 0))
        }

        # Log important order events
        if order_info['status'] == 'NEW':
            logger.info(f"New order placed: {order_info['symbol']} {order_info['side']} {order_info['type']}")
        elif order_info['status'] == 'FILLED':
            logger.info(f"Order filled: {order_info['symbol']} {order_info['side']} @ {order_info['average_price']}")

            # Check if it's a stop loss that triggered
            if order_info['type'] in ['STOP_MARKET', 'STOP']:
                logger.warning(f"⚠️ STOP LOSS TRIGGERED for {order_info['symbol']}")

            # Check if it's a take profit
            elif order_info['type'] == 'TAKE_PROFIT_MARKET':
                logger.info(f"✅ TAKE PROFIT TRIGGERED for {order_info['symbol']}")

        elif order_info['status'] == 'CANCELED':
            logger.info(f"Order cancelled: {order_info['order_id']}")
        elif order_info['status'] == 'EXPIRED':
            logger.warning(f"Order expired: {order_info['order_id']}")
        elif order_info['status'] == 'REJECTED':
            logger.error(f"Order rejected: {order_info['reject_reason']}")

        # Update local order tracking
        if order_info['status'] in ['FILLED', 'CANCELED', 'EXPIRED', 'REJECTED']:
            self.open_orders.pop(order_info['order_id'], None)
        else:
            self.open_orders[order_info['order_id']] = order_info

        # Emit order update event
        await self._emit_event(StreamEvent.ORDER_UPDATE, order_info)

    async def _handle_margin_call(self, msg: Dict):
        """Handle margin call event"""
        logger.critical("⚠️ MARGIN CALL RECEIVED!")

        margin_call_info = {
            'positions': msg.get('p', []),
            'timestamp': msg.get('T')
        }

        await self._emit_event(StreamEvent.MARGIN_CALL, margin_call_info)

    def _parse_position(self, pos: Dict) -> Dict:
        """Parse position from API format"""
        return {
            'symbol': pos['symbol'],
            'side': 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT',
            'position_amount': abs(float(pos['positionAmt'])),
            'entry_price': float(pos['entryPrice']),
            'mark_price': float(pos['markPrice']),
            'unrealized_pnl': float(pos['unRealizedProfit']),
            'leverage': int(pos['leverage']),
            'margin_type': pos['marginType'],
            'isolated_margin': float(pos.get('isolatedMargin', 0)),
            'is_auto_add_margin': pos.get('isAutoAddMargin', False),
            'position_side': pos['positionSide']
        }

    def _parse_order(self, order: Dict) -> Dict:
        """Parse order from API format"""
        return {
            'order_id': order['orderId'],
            'client_order_id': order.get('clientOrderId'),
            'symbol': order['symbol'],
            'side': order['side'],
            'type': order['type'],
            'quantity': float(order['origQty']),
            'price': float(order.get('price', 0)),
            'stop_price': float(order.get('stopPrice', 0)),
            'status': order['status'],
            'time_in_force': order.get('timeInForce'),
            'reduce_only': order.get('reduceOnly', False),
            'close_position': order.get('closePosition', False)
        }

    async def disconnect(self):
        """Disconnect from Binance stream"""
        await super().disconnect()

        if self.listen_key_task:
            self.listen_key_task.cancel()

        if self.client:
            await self.client.close_connection()

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position for symbol"""
        return self.positions.get(symbol)

    def get_all_positions(self) -> Dict:
        """Get all positions"""
        return self.positions.copy()

    def get_open_orders(self, symbol: str = None) -> Dict:
        """Get open orders"""
        if symbol:
            return {k: v for k, v in self.open_orders.items() if v['symbol'] == symbol}
        return self.open_orders.copy()