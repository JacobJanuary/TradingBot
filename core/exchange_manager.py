"""
Unified Exchange Manager using CCXT
Based on implementations from:
- https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/exchange/exchange.py
- https://github.com/jesse-ai/jesse/blob/master/jesse/exchanges/
"""
import ccxt.async_support as ccxt
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
import asyncio
from datetime import datetime
import time

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Order execution result"""
    id: str
    symbol: str
    side: str
    type: str
    amount: float
    price: float
    filled: float
    remaining: float
    status: str
    timestamp: datetime
    info: Dict


class ExchangeManager:
    """
    Unified exchange interface using CCXT
    Inspired by Freqtrade's exchange implementation
    """

    # Rate limit configuration per exchange
    RATE_LIMITS = {
        'binance': {
            'orders': 50,  # per second
            'weight': 1200  # per minute
        },
        'bybit': {
            'orders': 10,  # per second
            'weight': 120  # per minute
        }
    }

    def __init__(self, exchange_name: str, config: Dict):
        """Initialize exchange with configuration"""
        self.name = exchange_name.lower()
        self.config = config

        # Initialize CCXT exchange
        exchange_class = getattr(ccxt, self.name)

        # Exchange-specific options
        exchange_options = {
            'apiKey': config.get('api_key'),
            'secret': config.get('api_secret'),
            'enableRateLimit': config.get('rate_limit', True),
            'options': {
                'defaultType': 'future',  # Use futures by default
                'adjustForTimeDifference': True,
                'recvWindow': 10000,
            }
        }
        
        # Add exchange-specific settings
        if self.name == 'binance':
            exchange_options['options']['fetchPositions'] = 'positionRisk'
        elif self.name == 'bybit':
            # CRITICAL: Bybit V5 API requires UNIFIED account
            exchange_options['options']['accountType'] = 'UNIFIED'
            exchange_options['options']['defaultType'] = 'future'  # For perpetual futures
            
        self.exchange = exchange_class(exchange_options)

        # Set testnet if configured
        if config.get('testnet'):
            if self.name == 'binance':
                self.exchange.set_sandbox_mode(True)
            elif self.name == 'bybit':
                # Use proper testnet configuration for Bybit
                self.exchange.urls['api'] = {
                    'public': 'https://api-testnet.bybit.com',
                    'private': 'https://api-testnet.bybit.com'
                }
                self.exchange.hostname = 'api-testnet.bybit.com'
                
                # Ensure UNIFIED account settings are applied
                self.exchange.options['accountType'] = 'UNIFIED'
                self.exchange.options['defaultType'] = 'future'
                
                logger.info(f"Bybit testnet configured with UNIFIED account settings")

        # Market information cache
        self.markets = {}
        self.tickers = {}
        self.positions = {}
        self._last_ticker_update = {}

        # Rate limiting
        self._request_weight = 0
        self._weight_reset_time = time.time() + 60

        logger.info(f"Exchange {self.name} initialized {'(TESTNET)' if config.get('testnet') else ''}")

    async def initialize(self):
        """Load markets and validate connection"""
        try:
            # Load markets
            self.markets = await self.exchange.load_markets()
            logger.info(f"Loaded {len(self.markets)} markets from {self.name}")

            # Test connection
            await self.exchange.fetch_balance()
            logger.info(f"Connection to {self.name} verified")

            return True
        except Exception as e:
            logger.error(f"Failed to initialize {self.name}: {e}")
            raise

    async def close(self):
        """Close exchange connection"""
        await self.exchange.close()

    # ============== Market Data ==============

    async def fetch_ticker(self, symbol: str, use_cache: bool = True) -> Dict:
        """
        Fetch ticker with optional caching
        Cache expires after 1 second for real-time data
        """
        if use_cache and symbol in self._last_ticker_update:
            if time.time() - self._last_ticker_update[symbol] < 1:
                return self.tickers.get(symbol)

        ticker = await self.exchange.fetch_ticker(symbol)
        self.tickers[symbol] = ticker
        self._last_ticker_update[symbol] = time.time()

        return ticker

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict:
        """Fetch order book"""
        return await self.exchange.fetch_order_book(symbol, limit)

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List:
        """Fetch OHLCV candles"""
        return await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    # ============== Account Information ==============

    async def fetch_balance(self) -> Dict:
        """Fetch account balance"""
        balance = await self.exchange.fetch_balance()
        return balance

    async def fetch_positions(self, symbols: List[str] = None) -> List[Dict]:
        """
        Fetch open positions
        Returns standardized position format
        """
        positions = await self.exchange.fetch_positions(symbols)

        # Standardize position format
        standardized = []
        for pos in positions:
            if pos['contracts'] > 0:  # Only include open positions
                standardized.append({
                    'symbol': pos['symbol'],
                    'side': pos['side'],  # 'long' or 'short'
                    'contracts': pos['contracts'],
                    'contractSize': pos['contractSize'],
                    'unrealizedPnl': pos['unrealizedPnl'],
                    'percentage': pos['percentage'],
                    'markPrice': pos['markPrice'],
                    'entryPrice': pos['info'].get('entryPrice') or pos['info'].get('avgPrice'),
                    'timestamp': pos['timestamp'],
                    'info': pos['info']  # Original exchange data
                })

        self.positions = {p['symbol']: p for p in standardized}
        return standardized

    # ============== Order Management ==============

    async def create_market_order(self, symbol: str, side: str, amount: float) -> OrderResult:
        """
        Create market order with automatic formatting
        """
        try:
            # CCXT automatically handles formatting
            order = await self.exchange.create_market_order(
                symbol=symbol,
                side=side.lower(),
                amount=amount
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Market order failed for {symbol}: {e}")
            raise

    async def create_limit_order(self, symbol: str, side: str, amount: float, price: float) -> OrderResult:
        """Create limit order"""
        try:
            order = await self.exchange.create_limit_order(
                symbol=symbol,
                side=side.lower(),
                amount=amount,
                price=price
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Limit order failed for {symbol}: {e}")
            raise

    async def create_stop_loss_order(self, symbol: str, side: str, amount: float,
                                     stop_price: float, reduce_only: bool = True) -> OrderResult:
        """
        Create stop loss order
        Handles exchange-specific implementations
        """
        params = {'stopPrice': stop_price}

        if reduce_only:
            params['reduceOnly'] = True

        # Exchange-specific handling
        if self.name == 'binance':
            params['type'] = 'STOP_MARKET'
        elif self.name == 'bybit':
            params['stopOrderType'] = 'Stop'

        try:
            order = await self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=amount,
                price=None,
                params=params
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Stop loss order failed for {symbol}: {e}")
            raise

    async def create_trailing_stop_order(self, symbol: str, side: str, amount: float,
                                         activation_price: float, callback_rate: float) -> OrderResult:
        """
        Create trailing stop order
        Note: Implementation varies significantly between exchanges
        """
        params = {}

        if self.name == 'binance':
            # Binance trailing stop
            params = {
                'type': 'TRAILING_STOP_MARKET',
                'activationPrice': activation_price,
                'callbackRate': callback_rate  # Percentage
            }
        elif self.name == 'bybit':
            # Bybit trailing stop
            trailing_distance = activation_price * (callback_rate / 100)
            params = {
                'stopOrderType': 'TrailingStop',
                'trailingStop': trailing_distance,
                'activePrice': activation_price
            }

        try:
            order = await self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=amount,
                price=None,
                params=params
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Trailing stop order failed for {symbol}: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order"""
        try:
            result = await self.exchange.cancel_order(order_id, symbol)
            return result.get('status') == 'canceled'
        except ccxt.OrderNotFound:
            logger.warning(f"Order {order_id} not found")
            return False
        except ccxt.BaseError as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise

    async def cancel_all_orders(self, symbol: str = None) -> int:
        """Cancel all open orders"""
        try:
            if self.exchange.has['cancelAllOrders']:
                result = await self.exchange.cancel_all_orders(symbol)
                return len(result)
            else:
                # Fallback: fetch and cancel individually
                orders = await self.exchange.fetch_open_orders(symbol)
                count = 0
                for order in orders:
                    if await self.cancel_order(order['id'], order['symbol']):
                        count += 1
                return count
        except ccxt.BaseError as e:
            logger.error(f"Failed to cancel all orders: {e}")
            raise

    async def fetch_order(self, order_id: str, symbol: str) -> Optional[OrderResult]:
        """Fetch order details"""
        try:
            order = await self.exchange.fetch_order(order_id, symbol)
            return self._parse_order(order)
        except ccxt.OrderNotFound:
            return None
        except ccxt.BaseError as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            raise

    async def fetch_open_orders(self, symbol: str = None) -> List[OrderResult]:
        """Fetch open orders"""
        orders = await self.exchange.fetch_open_orders(symbol)
        return [self._parse_order(order) for order in orders]

    # ============== Position Management ==============

    async def close_position(self, symbol: str) -> bool:
        """
        Close position for symbol
        Creates a market order in opposite direction
        """
        positions = await self.fetch_positions([symbol])

        if not positions:
            logger.warning(f"No position found for {symbol}")
            return False

        position = positions[0]

        # Determine close side
        close_side = 'sell' if position['side'] == 'long' else 'buy'
        amount = position['contracts']

        try:
            # Cancel existing orders first
            await self.cancel_all_orders(symbol)

            # Create closing order
            order = await self.create_market_order(symbol, close_side, amount)

            if order.status == 'closed':
                logger.info(f"Position {symbol} closed successfully")
                return True
            else:
                logger.warning(f"Position close order not filled: {order.status}")
                return False

        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            raise

    # ============== Helper Methods ==============

    def _parse_order(self, order: Dict) -> OrderResult:
        """Parse CCXT order to standardized format"""
        return OrderResult(
            id=order['id'],
            symbol=order['symbol'],
            side=order['side'],
            type=order['type'],
            amount=order['amount'],
            price=order['price'] or 0,
            filled=order['filled'],
            remaining=order['remaining'],
            status=order['status'],
            timestamp=datetime.fromtimestamp(order['timestamp'] / 1000),
            info=order['info']
        )

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        """Format amount to exchange precision"""
        return self.exchange.amount_to_precision(symbol, amount)

    def price_to_precision(self, symbol: str, price: float) -> float:
        """Format price to exchange precision"""
        return self.exchange.price_to_precision(symbol, price)

    def get_min_amount(self, symbol: str) -> float:
        """Get minimum order amount for symbol"""
        market = self.markets.get(symbol)
        if market:
            return market['limits']['amount']['min']
        return 0.001  # Default

    def get_tick_size(self, symbol: str) -> float:
        """Get price tick size for symbol"""
        market = self.markets.get(symbol)
        if market:
            return market['precision']['price']
        return 0.01  # Default

    async def validate_order(self, symbol: str, side: str, amount: float, price: float = None) -> Tuple[bool, str]:
        """
        Validate order parameters before submission
        Returns (is_valid, error_message)
        """
        market = self.markets.get(symbol)
        if not market:
            return False, f"Market {symbol} not found"

        # Check if market is active
        if not market['active']:
            return False, f"Market {symbol} is not active"

        # Check minimum amount
        min_amount = market['limits']['amount']['min']
        if amount < min_amount:
            return False, f"Amount {amount} below minimum {min_amount}"

        # Check maximum amount
        max_amount = market['limits']['amount']['max']
        if max_amount and amount > max_amount:
            return False, f"Amount {amount} above maximum {max_amount}"

        # Check price limits if provided
        if price:
            min_price = market['limits']['price']['min']
            if min_price and price < min_price:
                return False, f"Price {price} below minimum {min_price}"

            max_price = market['limits']['price']['max']
            if max_price and price > max_price:
                return False, f"Price {price} above maximum {max_price}"

        return True, ""