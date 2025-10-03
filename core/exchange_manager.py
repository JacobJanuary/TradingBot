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
from datetime import datetime, timezone
import time
from utils.crypto_manager import decrypt_env_value
from utils.decimal_utils import to_decimal
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Order execution result"""
    id: str
    symbol: str
    side: str
    type: str
    amount: Decimal
    price: Decimal
    filled: Decimal
    remaining: Decimal
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

        # Decrypt API credentials if encrypted
        api_key = config.get('api_key')
        api_secret = config.get('api_secret')
        
        # If the keys start with 'ENC:', decrypt them
        if api_key and api_key.startswith('ENC:'):
            api_key = decrypt_env_value(f'{self.name.upper()}_API_KEY') or api_key
        if api_secret and api_secret.startswith('ENC:'):
            api_secret = decrypt_env_value(f'{self.name.upper()}_API_SECRET') or api_secret

        # Exchange-specific options
        exchange_options = {
            'apiKey': api_key,
            'secret': api_secret,
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

        # Initialize rate limiter
        self.rate_limiter = get_rate_limiter(self.name)

        logger.info(f"Exchange {self.name} initialized {'(TESTNET)' if config.get('testnet') else ''}")

    async def initialize(self):
        """Load markets and validate connection"""
        try:
            # Load markets with rate limiting
            self.markets = await self.rate_limiter.execute_request(
                self.exchange.load_markets
            )
            logger.info(f"Loaded {len(self.markets)} markets from {self.name}")

            # Test connection with rate limiting
            await self.rate_limiter.execute_request(
                self.exchange.fetch_balance
            )
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

        ticker = await self.rate_limiter.execute_request(
            self.exchange.fetch_ticker, symbol
        )
        self.tickers[symbol] = ticker
        self._last_ticker_update[symbol] = time.time()

        return ticker

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict:
        """Fetch order book with rate limiting"""
        return await self.rate_limiter.execute_request(
            self.exchange.fetch_order_book, symbol, limit
        )

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List:
        """Fetch OHLCV candles with rate limiting"""
        return await self.rate_limiter.execute_request(
            self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit
        )

    # ============== Account Information ==============

    async def fetch_balance(self) -> Dict:
        """Fetch account balance with rate limiting"""
        balance = await self.rate_limiter.execute_request(
            self.exchange.fetch_balance
        )
        return balance

    async def fetch_positions(self, symbols: List[str] = None) -> List[Dict]:
        """
        Fetch open positions
        Returns standardized position format
        """
        positions = await self.rate_limiter.execute_request(
            self.exchange.fetch_positions, symbols
        )

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

    async def create_order(self, symbol: str, type: str, side: str, amount: float,
                          price: float = None, params: Dict = None) -> Dict:
        """
        Universal order creation method - REQUIRED for aged_position_manager

        Args:
            symbol: Trading pair symbol
            type: Order type ('market', 'limit', 'stop_market')
            side: Order side ('buy' or 'sell')
            amount: Order amount
            price: Order price (for limit orders)
            params: Additional exchange-specific parameters

        Returns:
            Order dictionary from exchange
        """
        try:
            # Use rate limiter for order creation
            order = await self.rate_limiter.execute_request(
                self.exchange.create_order,
                symbol=symbol,
                type=type,
                side=side.lower(),
                amount=amount,
                price=price,
                params=params or {}
            )

            logger.info(f"✅ Created {type} order for {symbol}: {side} {amount} @ {price or 'market'}")
            return order

        except ccxt.InsufficientFunds as e:
            logger.error(f"Insufficient funds for {symbol}: {e}")
            raise
        except ccxt.InvalidOrder as e:
            logger.error(f"Invalid order parameters for {symbol}: {e}")
            raise
        except ccxt.BaseError as e:
            logger.error(f"Order creation failed for {symbol}: {e}")
            raise

    async def create_market_order(self, symbol: str, side: str, amount: Decimal, params: Dict = None) -> OrderResult:
        """
        Create market order with automatic formatting and params support

        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Order amount
            params: Additional parameters (e.g., {'reduceOnly': True})
        """
        try:
            # Check and adjust amount to exchange limits
            amount = await self._validate_and_adjust_amount(symbol, float(amount))

            # Create market order with rate limiting
            order = await self.rate_limiter.execute_request(
                self.exchange.create_market_order,
                symbol=symbol,
                side=side.lower(),
                amount=amount,
                params=params or {}
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Market order failed for {symbol}: {e}")
            raise

    async def create_limit_order(self, symbol: str, side: str, amount: Decimal, price: Decimal) -> OrderResult:
        """Create limit order"""
        try:
            order = await self.rate_limiter.execute_request(
                self.exchange.create_limit_order,
                symbol=symbol,
                side=side.lower(),
                amount=float(amount),
                price=float(price)
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Limit order failed for {symbol}: {e}")
            raise

    async def create_stop_loss_order_split(self, symbol: str, side: str, amount: Decimal,
                                           stop_price: Decimal, reduce_only: bool = True):
        """
        Create stop loss order with automatic splitting for large quantities
        Handles Binance max quantity error -4005
        """
        try:
            # Get symbol limits
            market = self.exchange.market(symbol)
            max_quantity = market.get('limits', {}).get('amount', {}).get('max', float('inf'))

            # Check if we need to split
            if float(amount) > max_quantity:
                logger.warning(f"⚠️ {symbol} quantity {amount} exceeds max {max_quantity}, splitting order")

                # Calculate chunks
                chunk_size = max_quantity * 0.99  # 99% of max for safety
                chunks = []
                remaining = float(amount)

                while remaining > 0:
                    chunk = min(chunk_size, remaining)
                    chunks.append(chunk)
                    remaining -= chunk

                logger.info(f"📦 Splitting {symbol} SL into {len(chunks)} orders")

                # Create multiple orders
                order_results = []
                for i, chunk_amount in enumerate(chunks, 1):
                    try:
                        logger.info(f"Creating SL chunk {i}/{len(chunks)}: {chunk_amount} @ {stop_price}")
                        result = await self.create_stop_loss_order(
                            symbol, side, Decimal(str(chunk_amount)), stop_price, reduce_only
                        )
                        order_results.append(result)

                        # Small delay to avoid rate limits
                        if i < len(chunks):
                            await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.error(f"Failed to create SL chunk {i}: {e}")
                        # Continue with other chunks even if one fails
                        continue

                if not order_results:
                    raise Exception("Failed to create any stop loss chunks")

                logger.info(f"✅ Created {len(order_results)}/{len(chunks)} SL orders for {symbol}")
                return order_results  # Return list of orders

            else:
                # Normal single order
                return await self.create_stop_loss_order(symbol, side, amount, stop_price, reduce_only)

        except Exception as e:
            logger.error(f"Stop loss order split failed for {symbol}: {e}")
            raise

    async def create_stop_loss_order(self, symbol: str, side: str, amount: Decimal,
                                     stop_price: Decimal, reduce_only: bool = True) -> OrderResult:
        """
        Create stop loss order for futures
        Based on freqtrade and ccxt documentation for Binance futures
        """
        try:
            # CRITICAL: Validate and adjust amount to prevent Binance error -4005
            amount = await self._validate_and_adjust_amount(symbol, float(amount))

            # Binance futures stop loss implementation
            if self.name == 'binance':
                # For Binance futures, use STOP_MARKET order type
                order = await self.rate_limiter.execute_request(
                    self.exchange.create_order,
                    symbol=symbol,
                    type='STOP_MARKET',  # Correct type for Binance futures stop loss
                    side=side.lower(),
                    amount=amount,
                    price=None,  # No price needed for STOP_MARKET
                    params={
                        'stopPrice': float(stop_price),
                        'reduceOnly': reduce_only,  # Only reduce existing position
                        'workingType': 'CONTRACT_PRICE'  # Use last price as trigger
                    }
                )
            elif self.name == 'bybit':
                # Bybit V5 implementation - use market order with stop trigger
                # Determine trigger direction based on position side
                # For short positions (stop loss above entry), trigger when price goes up (ascending)
                # For long positions (stop loss below entry), trigger when price goes down (descending)
                trigger_direction = 'ascending' if side.lower() == 'buy' else 'descending'

                order = await self.rate_limiter.execute_request(
                    self.exchange.create_order,
                    symbol=symbol,
                    type='market',  # Use market order type for Bybit V5
                    side=side.lower(),
                    amount=float(amount),
                    price=None,
                    params={
                        'stopPrice': float(stop_price),  # V5 API uses stopPrice
                        'triggerPrice': float(stop_price),
                        'reduceOnly': reduce_only,
                        'triggerBy': 'LastPrice',
                        'triggerDirection': trigger_direction,
                        'orderFilter': 'StopOrder'  # Specify this is a stop order
                    }
                )
            else:
                # Generic implementation
                order = await self.rate_limiter.execute_request(
                    self.exchange.create_order,
                    symbol=symbol,
                    type='stop_market',
                    side=side.lower(),
                    amount=float(amount),
                    price=None,
                    params={
                        'stopPrice': float(stop_price),
                        'reduceOnly': reduce_only
                    }
                )

            logger.info(f"✅ Stop loss created for {symbol} at {stop_price}")
            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Stop loss order failed for {symbol}: {e}")
            raise

    async def create_trailing_stop_order(self, symbol: str, side: str, amount: Decimal,
                                         activation_price: Decimal, callback_rate: Decimal) -> OrderResult:
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

    async def _validate_and_adjust_amount(self, symbol: str, amount: float) -> float:
        """
        Validate and adjust amount according to exchange limits
        Prevents Binance error -4005: Quantity greater than max quantity
        """
        try:
            # Load market data if not cached
            if symbol not in self.markets:
                await self.exchange.load_markets()

            market = self.markets.get(symbol)
            if not market:
                logger.warning(f"Market info not found for {symbol}, using original amount")
                return amount

            # Get limits
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
            max_amount = market.get('limits', {}).get('amount', {}).get('max', float('inf'))
            amount_precision = market.get('precision', {}).get('amount', 8)

            # Check max amount (Binance error -4005)
            if amount > max_amount:
                logger.warning(f"⚠️ {symbol}: Amount {amount} > max {max_amount}, adjusting to {max_amount * 0.99}")
                amount = max_amount * 0.99  # Use 99% of max for safety

            # Check min amount
            if amount < min_amount:
                logger.error(f"❌ {symbol}: Amount {amount} < min {min_amount}")
                raise ValueError(f"Amount too small: {amount} < {min_amount}")

            # Round to correct precision (with safe precision limits)
            from decimal import Decimal, ROUND_DOWN, InvalidOperation

            # Limit precision to safe range to prevent decimal.InvalidOperation
            safe_precision = max(0, min(int(amount_precision), 18))
            if safe_precision != amount_precision:
                logger.debug(f"Limited precision from {amount_precision} to {safe_precision} for {symbol}")

            try:
                step_size = 10 ** -safe_precision
                amount_decimal = Decimal(str(amount))
                step_decimal = Decimal(str(step_size))
                amount = float(amount_decimal.quantize(step_decimal, rounding=ROUND_DOWN))
            except (InvalidOperation, OverflowError) as e:
                # Fallback to simple rounding if decimal operations fail
                logger.debug(f"Decimal operation failed for {symbol}, using simple rounding: {e}")
                amount = round(amount, safe_precision)

            logger.debug(f"✅ {symbol}: Amount validated: {amount}")
            return amount

        except Exception as e:
            logger.error(f"Failed to validate amount for {symbol}: {e}")
            return amount  # Return original if validation fails

    def _parse_order(self, order: Dict) -> OrderResult:
        """Parse CCXT order to standardized format"""
        # Handle None timestamp (common for stop orders that haven't triggered yet)
        if order.get('timestamp'):
            timestamp = datetime.fromtimestamp(order['timestamp'] / 1000)
        else:
            timestamp = datetime.now(timezone.utc)

        return OrderResult(
            id=order['id'],
            symbol=order['symbol'],
            side=order['side'],
            type=order['type'],
            amount=order['amount'],
            price=order['price'] or 0,
            filled=order.get('filled', 0),
            remaining=order.get('remaining', order['amount']),
            status=order['status'],
            timestamp=timestamp,
            info=order['info']
        )

    def amount_to_precision(self, symbol: str, amount: Decimal) -> Decimal:
        """Format amount to exchange precision"""
        return self.exchange.amount_to_precision(symbol, amount)

    def price_to_precision(self, symbol: str, price: Decimal) -> Decimal:
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

    async def validate_order(self, symbol: str, side: str, amount: Decimal, price: Decimal = None) -> Tuple[bool, str]:
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