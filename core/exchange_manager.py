"""
Unified Exchange Manager using CCXT
Based on implementations from:
- https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/exchange/exchange.py
- https://github.com/jesse-ai/jesse/blob/master/jesse/exchanges/
"""
import ccxt.async_support as ccxt
import logging
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    # Import only for type hints, avoid circular import at runtime
    from core.position_manager import PositionManager
from dataclasses import dataclass
import asyncio
from datetime import datetime, timezone
import time
from utils.crypto_manager import decrypt_env_value
from utils.decimal_utils import to_decimal
from utils.rate_limiter import get_rate_limiter
from utils.datetime_helpers import now_utc, ensure_utc
from config.settings import config

logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format for consistent comparison
    Converts exchange format 'HIGH/USDT:USDT' to database format 'HIGHUSDT'

    Args:
        symbol: Symbol in any format

    Returns:
        Normalized symbol (e.g., 'BLASTUSDT')
    """
    if '/' in symbol and ':' in symbol:
        # Exchange format: 'HIGH/USDT:USDT' -> 'HIGHUSDT'
        base_quote = symbol.split(':')[0]  # 'HIGH/USDT'
        return base_quote.replace('/', '')  # 'HIGHUSDT'
    return symbol


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

    def __init__(self, exchange_name: str, config: Dict, repository=None, position_manager: Optional['PositionManager'] = None):
        """
        Initialize exchange with configuration

        Args:
            exchange_name: Exchange name (e.g., 'binance', 'bybit')
            config: Exchange configuration dict
            repository: Optional TradingRepository for DB operations
            position_manager: Optional PositionManager instance for real-time position data
                             Required for accurate position lookup during SL updates.
                             If None, falls back to self.positions (fetch_positions cache).
        """
        self.name = exchange_name.lower()
        self.config = config
        self.repository = repository  # Optional: for order caching (Phase 3)
        self.position_manager = position_manager  # NEW: For real-time position lookup

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
            exchange_options['options']['defaultType'] = 'future'  # Changed from 'unified' to fix KeyError
            exchange_options['options']['brokerId'] = ''  # Disable CCXT default brokerId to fix Error 170003

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

    def find_exchange_symbol(self, normalized_symbol: str) -> Optional[str]:
        """
        Find exchange-specific symbol format by searching markets
        CRITICAL FIX: Converts DB format ('BLASTUSDT') to exchange format ('BLAST/USDT:USDT')

        Args:
            normalized_symbol: Database format symbol (e.g., 'BLASTUSDT')

        Returns:
            Exchange format symbol (e.g., 'BLAST/USDT:USDT') or None if not found

        Examples:
            Binance: 'BTCUSDT' → 'BTCUSDT' (exact match)
            Bybit: 'BLASTUSDT' → 'BLAST/USDT:USDT' (format conversion)
        """
        # Try exact match first (for exchanges that use simple format like Binance)
        if normalized_symbol in self.markets:
            return normalized_symbol

        # Search for matching symbol in all markets
        # This handles format conversion: 'BLASTUSDT' → 'BLAST/USDT:USDT'
        for market_symbol in self.markets.keys():
            if normalize_symbol(market_symbol) == normalized_symbol:
                logger.debug(f"Symbol format conversion: {normalized_symbol} → {market_symbol} ({self.name})")
                return market_symbol

        # Symbol not found on this exchange
        logger.warning(f"Symbol {normalized_symbol} not found in {len(self.markets)} markets on {self.name}")
        return None

    # ============== Market Data ==============

    async def fetch_ticker(self, symbol: str, use_cache: bool = True) -> Dict:
        """
        Fetch ticker with optional caching
        Cache expires after 1 second for real-time data
        """
        if use_cache and symbol in self._last_ticker_update:
            if time.time() - self._last_ticker_update[symbol] < 1:
                return self.tickers.get(symbol)

        # MINIMAL FIX: Handle Bybit 'unified' KeyError for non-existent symbols
        try:
            ticker = await self.rate_limiter.execute_request(
                self.exchange.fetch_ticker, symbol
            )
        except KeyError as e:
            if "'unified'" in str(e) and self.name == 'bybit':
                # Symbol doesn't exist on Bybit - return None instead of crashing
                logger.debug(f"Symbol {symbol} not found on Bybit (unified error)")
                return None
            raise  # Re-raise other KeyErrors

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

    async def _get_free_balance_usdt(self) -> float:
        """
        Get free USDT balance for this exchange

        For Bybit UNIFIED accounts, uses direct API call.
        For other exchanges, uses standard fetch_balance().

        Returns:
            Free USDT balance as float
        """
        if self.name == 'bybit':
            try:
                response = await self.exchange.privateGetV5AccountWalletBalance({
                    'accountType': 'UNIFIED',
                    'coin': 'USDT'
                })
                result = response.get('result', {})
                accounts = result.get('list', [])
                if accounts:
                    account = accounts[0]

                    # FIX: For UNIFIED accounts, must account for margin used in positions
                    # totalAvailableBalance often returns empty string ""
                    # Correct formula: walletBalance - totalPositionIM
                    coins = account.get('coin', [])
                    for coin_data in coins:
                        if coin_data.get('coin') == 'USDT':
                            wallet_balance = float(coin_data.get('walletBalance', 0) or 0)
                            total_position_im = float(coin_data.get('totalPositionIM', 0) or 0)

                            # Free balance = wallet - margin used in positions
                            free_balance = wallet_balance - total_position_im

                            logger.debug(
                                f"Bybit USDT: wallet={wallet_balance:.2f}, "
                                f"positionIM={total_position_im:.2f}, "
                                f"free={free_balance:.2f}"
                            )
                            return free_balance

                    logger.warning("No USDT found in Bybit coin list")
                    return 0.0
                else:
                    logger.warning("No Bybit account data, returning 0")
                    return 0.0
            except Exception as e:
                logger.warning(f"Bybit balance fetch failed, fallback: {e}")
                balance = await self.exchange.fetch_balance()
                return float(balance.get('USDT', {}).get('free', 0) or 0)
        else:
            balance = await self.exchange.fetch_balance()
            return float(balance.get('USDT', {}).get('free', 0) or 0)

    async def _get_total_balance_usdt(self) -> float:
        """
        Get total USDT balance for this exchange

        For Bybit UNIFIED accounts, uses direct API call.
        For other exchanges, uses standard fetch_balance().

        Returns:
            Total USDT balance as float
        """
        if self.name == 'bybit':
            try:
                response = await self.exchange.privateGetV5AccountWalletBalance({
                    'accountType': 'UNIFIED',
                    'coin': 'USDT'
                })
                result = response.get('result', {})
                accounts = result.get('list', [])
                if accounts:
                    account = accounts[0]
                    return float(account.get('totalWalletBalance', 0))
                else:
                    logger.warning("No Bybit account data, returning 0")
                    return 0.0
            except Exception as e:
                logger.warning(f"Bybit balance fetch failed, fallback: {e}")
                balance = await self.exchange.fetch_balance()
                return float(balance.get('USDT', {}).get('total', 0) or 0)
        else:
            balance = await self.exchange.fetch_balance()
            return float(balance.get('USDT', {}).get('total', 0) or 0)

    async def fetch_balance(self) -> Dict:
        """Fetch account balance with rate limiting"""
        balance = await self.rate_limiter.execute_request(
            self.exchange.fetch_balance
        )

        # FIX: Patch Bybit UNIFIED balance (free=None issue)
        if self.name == 'bybit':
            usdt = balance.get('USDT', {})
            if usdt.get('free') is None and usdt.get('total', 0) > 0:
                try:
                    free_usdt = await self._get_free_balance_usdt()
                    total_usdt = await self._get_total_balance_usdt()
                    balance['USDT']['free'] = free_usdt
                    balance['USDT']['used'] = total_usdt - free_usdt
                    balance['USDT']['total'] = total_usdt
                except Exception as e:
                    logger.warning(f"Failed to patch Bybit balance: {e}")

        return balance

    async def fetch_positions(self, symbols: List[str] = None, params: Dict = None) -> List[Dict]:
        """
        Fetch open positions
        Returns standardized position format

        CRITICAL FIX 2025-10-29: Convert symbols to exchange format (unified) before CCXT
        Example: "DBRUSDT" (raw) → "DBR/USDT:USDT" (unified)
        Without conversion, CCXT filter_by_array filters out positions!

        Args:
            symbols: List of symbols to fetch (optional)
            params: Additional parameters (e.g., {'category': 'linear'} for Bybit)
        """
        # FIX: Convert raw symbols to exchange format (same pattern as set_leverage)
        converted_symbols = None
        if symbols:
            converted_symbols = []
            for symbol in symbols:
                exchange_symbol = self.find_exchange_symbol(symbol)
                if exchange_symbol:
                    converted_symbols.append(exchange_symbol)
                    logger.debug(
                        f"Symbol conversion for fetch_positions: {symbol} → {exchange_symbol}"
                    )
                else:
                    # Fallback: use original symbol if conversion fails
                    converted_symbols.append(symbol)
                    logger.warning(
                        f"⚠️  Could not convert symbol {symbol} to exchange format, using as-is. "
                        f"This may cause fetch_positions to return empty list!"
                    )

        # CRITICAL FIX: Support params for Bybit category='linear'
        if params:
            positions = await self.rate_limiter.execute_request(
                self.exchange.fetch_positions, converted_symbols, params
            )
        else:
            positions = await self.rate_limiter.execute_request(
                self.exchange.fetch_positions, converted_symbols
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
                          price: Optional[float] = None, params: Optional[Dict] = None) -> Dict:
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
            # CRITICAL FIX: Convert symbol to exchange-specific format before API call
            # DB stores 'BLASTUSDT', but Bybit needs 'BLAST/USDT:USDT'
            exchange_symbol = self.find_exchange_symbol(symbol)

            if not exchange_symbol:
                error_msg = f"Symbol {symbol} not available on {self.name}"
                logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)

            # Use rate limiter for order creation with converted symbol
            order = await self.rate_limiter.execute_request(
                self.exchange.create_order,
                symbol=exchange_symbol,  # ✅ Use exchange-specific format
                type=type,
                side=side.lower(),
                amount=amount,
                price=price,
                params=params or {}
            )

            logger.info(f"✅ Created {type} order for {symbol}: {side} {amount} @ {price or 'market'}")

            # Cache order locally (Phase 3: Bybit 500 order limit solution)
            if self.repository:
                await self.repository.cache_order(self.name, order)

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
            validated_amount = await self._validate_and_adjust_amount(symbol, float(amount))

            # CRITICAL FIX: Convert symbol to exchange-specific format
            exchange_symbol = self.find_exchange_symbol(symbol)
            if not exchange_symbol:
                raise ValueError(f"Symbol {symbol} not available on {self.name}")

            # Create market order with rate limiting
            order = await self.rate_limiter.execute_request(
                self.exchange.create_market_order,
                symbol=exchange_symbol,  # ✅ Use exchange-specific format
                side=side.lower(),
                amount=validated_amount,
                params=params or {}
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Market order failed for {symbol}: {e}")
            raise

    async def create_limit_order(self, symbol: str, side: str, amount: Decimal, price: Decimal) -> OrderResult:
        """Create limit order"""
        try:
            # CRITICAL FIX: Convert symbol to exchange-specific format
            exchange_symbol = self.find_exchange_symbol(symbol)
            if not exchange_symbol:
                raise ValueError(f"Symbol {symbol} not available on {self.name}")

            order = await self.rate_limiter.execute_request(
                self.exchange.create_limit_order,
                symbol=exchange_symbol,  # ✅ Use exchange-specific format
                side=side.lower(),
                amount=float(amount),
                price=float(price)
            )

            return self._parse_order(order)
        except ccxt.BaseError as e:
            logger.error(f"Limit order failed for {symbol}: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a trading pair

        CRITICAL: Must be called BEFORE opening position!
        For Bybit: automatically adds params={'category': 'linear'}

        Args:
            symbol: Trading symbol (exchange format)
            leverage: Leverage multiplier (e.g., 10 for 10x)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert to exchange format if needed
            exchange_symbol = self.find_exchange_symbol(symbol)
            if not exchange_symbol:
                logger.error(f"Symbol {symbol} not found on {self.name}")
                return False

            # Bybit requires 'category' parameter
            if self.name.lower() == 'bybit':
                await self.rate_limiter.execute_request(
                    self.exchange.set_leverage,
                    leverage=leverage,
                    symbol=exchange_symbol,
                    params={'category': 'linear'}
                )
            else:
                # Binance and others
                await self.rate_limiter.execute_request(
                    self.exchange.set_leverage,
                    leverage=leverage,
                    symbol=exchange_symbol
                )

            logger.info(f"✅ Leverage set to {leverage}x for {symbol} on {self.name}")
            return True

        except Exception as e:
            # Bybit specific: error 110043 means "leverage not modified" (already at requested value)
            error_str = str(e)
            if self.name.lower() == 'bybit' and '"retCode":110043' in error_str:
                logger.info(f"✅ Leverage already at {leverage}x for {symbol} on {self.name}")
                return True

            logger.error(f"❌ Failed to set leverage for {symbol}: {e}")
            return False

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
        
        DECEMBER 2025 MIGRATION:
        - Binance: Uses StopLossManager (Algo API)
        - Bybit: Uses position-attached SL
        - Others: Uses generic CCXT
        """
        try:
            # CRITICAL: Validate and adjust amount to prevent Binance error -4005
            validated_amount = await self._validate_and_adjust_amount(symbol, float(amount))

            # Binance futures stop loss implementation
            if self.name == 'binance':
                # DECEMBER 2025 MIGRATION: Use StopLossManager for Algo API
                # Old create_order with type='STOP_MARKET' returns error -4120
                from core.stop_loss_manager import StopLossManager
                sl_manager = StopLossManager(self.exchange, self.name)
                
                result = await sl_manager.set_stop_loss(
                    symbol=symbol,
                    side=side,
                    amount=Decimal(str(validated_amount)),
                    stop_price=stop_price
                )
                
                # Convert to OrderResult format for compatibility
                order = {
                    'id': str(result.get('algoId', 'algo_order')),
                    'symbol': symbol,
                    'type': 'STOP_MARKET',
                    'side': side,
                    'price': float(stop_price),
                    'stopPrice': float(stop_price),
                    'amount': validated_amount,
                    'filled': 0.0,
                    'remaining': validated_amount,
                    'status': 'open',
                    'timestamp': None,
                    'info': result
                }
                
            elif self.name == 'bybit':
                # CRITICAL FIX: Use position-attached stop loss instead of conditional order
                # This prevents "Insufficient balance" error as it doesn't require margin
                # Source: https://bybit-exchange.github.io/docs/v5/position/trading-stop

                # Get position info to determine positionIdx
                # CRITICAL FIX: Must pass category='linear' for Bybit
                positions = await self.exchange.fetch_positions(
                    symbols=[symbol],
                    params={'category': 'linear'}
                )
                position_idx = 0  # Default for one-way mode

                for pos in positions:
                    if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                        position_idx = int(pos.get('info', {}).get('positionIdx', 0))
                        break

                # Format symbol for Bybit API (remove / and :USDT)
                bybit_symbol = symbol.replace('/', '').replace(':USDT', '')

                # Format stop loss price with proper precision
                stop_loss_price = self.exchange.price_to_precision(symbol, float(stop_price))

                # Use trading-stop endpoint for position-attached SL
                params = {
                    'category': 'linear',
                    'symbol': bybit_symbol,
                    'stopLoss': stop_loss_price,
                    'positionIdx': position_idx,
                    'slTriggerBy': 'LastPrice',  # Use last price as trigger
                    'tpslMode': 'Full'  # Full position stop loss
                }

                # Make direct API call to set trading stop
                try:
                    result = await self.rate_limiter.execute_request(
                        self.exchange.private_post_v5_position_trading_stop,
                        params
                    )

                    logger.info(f"✅ Stop Loss set via trading-stop: {stop_loss_price}")

                except ccxt.ExchangeError as e:
                    # Check if error is "not modified" (34040) - means SL already set with same price
                    if '"retCode":34040' in str(e) and '"retMsg":"not modified"' in str(e):
                        logger.info(f"✅ Stop Loss already set at {stop_loss_price} (not modified)")
                        # Create a fake success result
                        result = {'retCode': 0, 'retMsg': 'OK (already set)'}
                    else:
                        # Re-raise other errors
                        raise

                # Return in OrderResult format for compatibility
                order = {
                    'id': f'sl_position_{bybit_symbol}',
                    'symbol': symbol,
                    'type': 'stop_loss_position',  # Mark as position-attached SL
                    'side': side,
                    'price': float(stop_loss_price),  # CRITICAL FIX: Add missing 'price' field
                    'stopPrice': float(stop_loss_price),
                    'amount': float(amount),
                    'filled': 0.0,
                    'remaining': float(amount),
                    'status': 'open',
                    'timestamp': None,
                    'info': result
                }
            else:
                # Generic implementation - use unified CCXT API
                order = await self.rate_limiter.execute_request(
                    self.exchange.create_order,
                    symbol=symbol,
                    type='stop_market',
                    side=side.lower(),
                    amount=float(amount),
                    price=None,
                    params={
                        'stopLossPrice': float(stop_price),  # Unified CCXT parameter
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

    # ============== TRAILING STOP ATOMIC UPDATE ==============

    async def update_stop_loss_atomic(self, symbol: str, new_sl_price: float,
                                       position_side: str = 'long') -> dict:
        """
        Update stop loss atomically (exchange-specific implementation)

        Bybit: Uses trading-stop endpoint (ATOMIC - no race condition)
        Binance: Uses optimized cancel+create (minimal race window)

        Args:
            symbol: Trading symbol
            new_sl_price: New stop loss price
            position_side: 'long' or 'short'

        Returns:
            dict with success, execution_time_ms, method_used
        """
        start_time = now_utc()

        result: Dict[str, Any] = {
            'success': False,
            'method': None,
            'execution_time_ms': 0,
            'error': None,
            'old_sl_price': None,
            'new_sl_price': new_sl_price
        }

        try:
            if self.name == 'bybit':
                # BYBIT: ATOMIC update via trading-stop
                result['method'] = 'bybit_trading_stop_atomic'
                update_result = await self._bybit_update_sl_atomic(symbol, new_sl_price, position_side)
                result['success'] = update_result['success']
                result['error'] = update_result.get('error')

            elif self.name == 'binance':
                # BINANCE: Optimized cancel+create
                result['method'] = 'binance_cancel_create_optimized'
                update_result = await self._binance_update_sl_optimized(symbol, new_sl_price, position_side)
                result['success'] = update_result['success']
                result['error'] = update_result.get('error')
                result['unprotected_window_ms'] = update_result.get('unprotected_window_ms', 0)

            else:
                raise NotImplementedError(f"Atomic SL update not implemented for {self.name}")

            execution_time = (now_utc() - start_time).total_seconds() * 1000
            result['execution_time_ms'] = execution_time

            if result['success']:
                logger.info(
                    f"✅ SL update complete: {symbol} @ {new_sl_price} "
                    f"({result['method']}, {execution_time:.2f}ms)"
                )
            else:
                logger.error(f"❌ SL update failed: {symbol} - {result['error']}")

            return result

        except Exception as e:
            execution_time = (now_utc() - start_time).total_seconds() * 1000
            result['execution_time_ms'] = execution_time
            result['error'] = str(e)
            logger.error(f"❌ SL update failed: {e}", exc_info=True)
            return result

    async def _bybit_update_sl_atomic(self, symbol: str, new_sl_price: float,
                                       position_side: str) -> dict:
        """
        Bybit-specific ATOMIC SL update using trading-stop endpoint

        CRITICAL: This is ATOMIC - no cancel+create race condition!
        """
        result = {'success': False, 'error': None}

        try:
            # Get position to determine positionIdx
            positions = await self.fetch_positions(
                symbols=[symbol],
                params={'category': 'linear'}
            )

            position_idx = 0  # Default: One-Way mode
            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    position_idx = int(pos.get('info', {}).get('positionIdx', 0))
                    break

            # Format symbol for Bybit API (remove / and :USDT)
            bybit_symbol = symbol.replace('/', '').replace(':USDT', '')

            # Format price with proper precision
            sl_price_formatted = self.exchange.price_to_precision(symbol, new_sl_price)

            # ЗАЩИТНАЯ ВАЛИДАЦИЯ (после строки 791)
            # Validate SL for SHORT positions before sending to exchange
            if position_side in ['short', 'sell']:
                try:
                    ticker = await self.exchange.fetch_ticker(symbol)
                    current_market_price = float(ticker['last'])

                    if new_sl_price <= current_market_price:
                        logger.warning(
                            f"⚠️ SHORT {symbol}: Attempted SL {new_sl_price:.8f} <= market {current_market_price:.8f}, "
                            f"skipping to avoid exchange rejection"
                        )
                        result['success'] = False
                        result['error'] = f"Invalid SL for SHORT: {new_sl_price:.8f} must be > {current_market_price:.8f}"
                        return result
                except Exception as e:
                    logger.error(f"Failed to validate SHORT SL: {e}")
                    # Continue anyway if validation fails

            # ATOMIC update via trading-stop endpoint
            params = {
                'category': 'linear',
                'symbol': bybit_symbol,
                'stopLoss': sl_price_formatted,
                'positionIdx': position_idx,
                'slTriggerBy': 'LastPrice',
                'tpslMode': 'Full'
            }

            logger.info(f"🔄 Bybit ATOMIC SL update: {bybit_symbol} @ {sl_price_formatted}")

            response = await self.rate_limiter.execute_request(
                self.exchange.private_post_v5_position_trading_stop,
                params
            )

            # Check response - CRITICAL: retCode is STRING "0", not int 0
            ret_code = str(response.get('retCode', -1))
            ret_msg = response.get('retMsg', 'unknown')

            if ret_code == '0' or ret_code == 0:
                result['success'] = True
                logger.info(f"✅ Bybit SL updated atomically to {sl_price_formatted}")

            elif ret_code == '34040' and 'not modified' in ret_msg.lower():
                # Special case: SL already at this price (not an error)
                result['success'] = True
                logger.info(f"✅ Bybit SL already at {sl_price_formatted} (not modified)")

            else:
                result['error'] = f"retCode={ret_code}, retMsg={ret_msg}"
                logger.error(f"❌ Bybit SL update failed: {result['error']}")

            return result

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Bybit atomic SL update failed: {e}", exc_info=True)
            return result

    async def _binance_update_sl_optimized(self, symbol: str, new_sl_price: float,
                                            position_side: str) -> dict:
        """
        Binance-specific OPTIMIZED cancel+create for SL update

        CRITICAL: Minimizes race condition window but cannot eliminate it
        Binance does NOT support atomic SL updates for STOP_MARKET orders
        """
        result = {
            'success': False,
            'error': None,
            'cancel_time_ms': 0,
            'create_time_ms': 0,
            'unprotected_window_ms': 0
        }

        try:
            # Find ALL existing SL orders (handle orphans)
            orders = await self.rate_limiter.execute_request(
                self.exchange.fetch_open_orders, symbol
            )

            sl_orders = []  # Changed from sl_order to sl_orders
            expected_side = 'sell' if position_side == 'long' else 'buy'

            for order in orders:
                order_type = order.get('type', '').upper()
                order_side = order.get('side', '').lower()
                reduce_only = order.get('reduceOnly', False)

                if (order_type == 'STOP_MARKET' and
                    order_side == expected_side and
                    reduce_only):
                    sl_orders.append(order)  # Collect ALL SL orders

            unprotected_start = now_utc()
            total_cancel_time = 0

            # Step 1: Cancel ALL old SL orders (handle orphans)
            if sl_orders:
                if len(sl_orders) > 1:
                    logger.warning(
                        f"⚠️  Found {len(sl_orders)} SL orders for {symbol} - "
                        f"possible orphan orders! Canceling all..."
                    )

                for sl_order in sl_orders:
                    cancel_start = now_utc()

                    try:
                        await self.rate_limiter.execute_request(
                            self.exchange.cancel_order,
                            sl_order['id'], symbol
                        )

                        cancel_duration = (now_utc() - cancel_start).total_seconds() * 1000
                        total_cancel_time += int(cancel_duration)

                        logger.info(
                            f"🗑️  Cancelled SL order {sl_order['id'][:8]}... "
                            f"(stopPrice={sl_order.get('stopPrice', 'N/A')}) "
                            f"in {cancel_duration:.2f}ms"
                        )

                    except Exception as e:
                        logger.error(f"Failed to cancel SL order {sl_order['id']}: {e}")
                        # Continue canceling other orders even if one fails

                result['cancel_time_ms'] = total_cancel_time
                result['orders_cancelled'] = len(sl_orders)

                logger.info(
                    f"🗑️  Cancelled {len(sl_orders)} SL order(s) in {total_cancel_time:.2f}ms total"
                )

            # Step 1.1: CANCEL open ALGO orders (Fix -4045 Error)
            # Since we now use Algo API for creation, we MUST cancel them via Algo API
            try:
                # Format symbol for Binance
                algo_symbol = symbol.replace('/', '').replace(':USDT', '')

                # Fetch (no rate limiter wrapper needed for direct call typically, but safer)
                algo_res = await self.exchange.fapiPrivateGetOpenAlgoOrders({
                    'symbol': algo_symbol,
                    'algo_type': 'STOP_MARKET'
                })

                algo_orders = []
                if isinstance(algo_res, dict) and 'orders' in algo_res:
                    algo_orders = algo_res['orders']
                elif isinstance(algo_res, list):
                    algo_orders = algo_res

                if algo_orders:
                    logger.info(f"🔍 Found {len(algo_orders)} existing Algo SL orders to cancel")
                    
                    for ao in algo_orders:
                        try:
                            cancel_start = now_utc()
                            await self.exchange.fapiPrivateDeleteAlgoOrder({
                                'symbol': algo_symbol,
                                'algoId': ao['algoId']
                            })
                            cancel_duration = (now_utc() - cancel_start).total_seconds() * 1000
                            logger.info(f"🗑️  Cancelled Algo Order {ao['algoId']} in {cancel_duration:.2f}ms")
                            result['cancel_time_ms'] += int(cancel_duration)
                            result['orders_cancelled'] += 1
                        except Exception as e:
                            logger.warning(f"Failed to cancel Algo Order {ao.get('algoId')}: {e}")

            except Exception as e:
                # Don't fail the whole update if algo fetch fails (e.g. permission or network)
                # But log warning as this is critical for preventing -4045
                logger.warning(f"⚠️ Failed to check/cancel Algo Orders: {e}") 


            # Step 2: Create new SL IMMEDIATELY (NO SLEEP!)
            create_start = now_utc()

            # ============================================================
            # FIX: Robust Position Lookup with 3-Tier Fallback + Retry
            # ============================================================
            # Issue: Temporary API glitches cause fetch_positions() to return []
            #        even when position exists and is in WebSocket cache
            #
            # Solution:
            #  1. PRIMARY: Use WebSocket cache (most up-to-date, instant)
            #  2. SECONDARY: Fetch from exchange with retry (2 attempts, 200ms delay)
            #  3. TERTIARY: Database fallback (last resort for restart scenarios)
            #  4. ABORT: If all fail - do NOT proceed (prevents unprotected positions)

            amount: float = 0.0
            lookup_method: str = "unknown"

            # ============================================================
            # PRIORITY 1: Position Manager Cache (Real-time WebSocket)
            # ============================================================
            # FIX 2025-11-10: Use position_manager.positions instead of self.positions
            #
            # Rationale:
            #   - self.positions is ONLY updated when fetch_positions() is explicitly called
            #   - position_manager.positions is updated in REAL-TIME via WebSocket events
            #   - This fix resolves SOONUSDT issue where position was NOT in self.positions
            #     causing database fallback with stale data
            #
            # Data format difference:
            #   - self.positions[symbol] = Dict with 'contracts' key (float)
            #   - position_manager.positions[symbol] = PositionState object with .quantity (Decimal)
            #
            # Investigation: tests/investigation/SOONUSDT_ROOT_CAUSE_FINAL.md

            if self.position_manager and symbol in self.position_manager.positions:
                position_state = self.position_manager.positions[symbol]

                # PositionState.quantity is Decimal, convert to float for amount
                cached_contracts = float(position_state.quantity)

                if cached_contracts > 0:
                    amount = cached_contracts
                    lookup_method = "position_manager_cache"
                    logger.debug(
                        f"✅ {symbol}: Using position_manager cache: {amount} contracts "
                        f"(real-time WebSocket data, most reliable)"
                    )
                else:
                    # Position Manager shows quantity=0 → position closed
                    # This is THE TRUTH - WebSocket updated position_manager in real-time
                    # ABORT immediately to prevent creating SL for closed position
                    logger.warning(
                        f"⚠️  {symbol}: Position Manager (real-time) shows quantity=0 (position closed). "
                        f"ABORTING SL update to prevent orphaned order."
                    )
                    result['success'] = False
                    result['error'] = 'position_closed_realtime'
                    result['message'] = (
                        f"Position Manager (real-time WebSocket) indicates {symbol} position closed (quantity=0). "
                        f"SL update aborted."
                    )
                    return result

            # ============================================================
            # PRIORITY 2: Exchange API with Retry
            # ============================================================
            # Only if cache miss (e.g., bot just started, position not yet cached)
            # Retry protects against temporary API glitches

            if amount == 0:
                max_retries = 2
                retry_delay_ms = 200

                for attempt in range(1, max_retries + 1):
                    try:
                        logger.debug(
                            f"🔍 {symbol}: Fetching position from exchange "
                            f"(attempt {attempt}/{max_retries})"
                        )

                        positions = await self.fetch_positions([symbol])

                        for pos in positions:
                            if pos['symbol'] == symbol:
                                pos_contracts = float(pos.get('contracts', 0))
                                if pos_contracts > 0:
                                    amount = pos_contracts
                                    lookup_method = f"exchange_api_attempt_{attempt}"
                                    logger.info(
                                        f"✅ {symbol}: Position found via exchange API "
                                        f"(attempt {attempt}, size: {amount})"
                                    )
                                    break

                        # Success - break retry loop
                        if amount > 0:
                            break

                        # No position found - retry if not last attempt
                        if attempt < max_retries:
                            logger.warning(
                                f"⚠️  {symbol}: Position not found in exchange response "
                                f"(attempt {attempt}/{max_retries}), retrying in {retry_delay_ms}ms..."
                            )
                            await asyncio.sleep(retry_delay_ms / 1000.0)
                        else:
                            logger.warning(
                                f"⚠️  {symbol}: Position not found in exchange after "
                                f"{max_retries} attempts"
                            )

                    except Exception as e:
                        logger.error(
                            f"❌ {symbol}: Exchange API error on attempt {attempt}: {e}"
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(retry_delay_ms / 1000.0)

            # ============================================================
            # PRIORITY 3: Database Fallback
            # ============================================================
            # Only use DB if both cache AND API failed
            # This handles restart scenarios where WebSocket not yet connected
            # FIX 2025-11-10: Only use DB if symbol NOT in position_manager
            #      If symbol IS in position_manager, we already handled it in Priority 1
            #      (either got quantity or detected quantity=0 and aborted)
            #
            # Condition logic:
            #   - If position_manager=None → use DB (backward compatibility, scripts)
            #   - If symbol not in position_manager.positions → use DB (bot restart)
            #   - If symbol in position_manager.positions → DO NOT use DB (already handled)

            if amount == 0 and self.repository and (
                not self.position_manager or
                symbol not in self.position_manager.positions
            ):
                try:
                    logger.warning(
                        f"⚠️  {symbol}: Cache and API lookup failed, trying database fallback..."
                    )

                    db_position = await self.repository.get_open_position(symbol, self.name)

                    if db_position and db_position.get('status') == 'active':
                        db_quantity = float(db_position.get('quantity', 0))
                        if db_quantity > 0:
                            amount = db_quantity
                            lookup_method = "database_fallback"
                            logger.warning(
                                f"⚠️  {symbol}: Using database fallback "
                                f"(quantity={amount}, possible API delay or bot restart)"
                            )

                except Exception as e:
                    logger.error(f"❌ {symbol}: Database fallback error: {e}")

            # ============================================================
            # ABORT if Position Not Found
            # ============================================================
            # CRITICAL: Do NOT proceed if position truly doesn't exist
            # Prevents creating orphaned SL orders for closed positions

            if amount == 0:
                logger.error(
                    f"❌ {symbol}: Position not found after 3-tier lookup:\n"
                    f"  1. WebSocket cache: NOT FOUND\n"
                    f"  2. Exchange API (2 attempts): NOT FOUND\n"
                    f"  3. Database fallback: NOT FOUND\n"
                    f"  → ABORTING SL update (position likely closed or never existed)"
                )
                result['success'] = False
                result['error'] = 'position_not_found_abort'
                result['lookup_attempts'] = {
                    'cache_checked': symbol in self.positions,
                    'api_attempts': 2,
                    'database_checked': self.repository is not None
                }
                result['message'] = (
                    f"Position {symbol} not found after exhaustive lookup. "
                    f"SL update aborted to prevent orphaned orders."
                )
                return result

            # ============================================================
            # SUCCESS: Position Found
            # ============================================================
            # Log lookup method for debugging

            logger.info(
                f"✅ {symbol}: Position size confirmed: {amount} contracts "
                f"(lookup_method: {lookup_method})"
            )

            close_side = 'SELL' if position_side == 'long' else 'BUY'

            # DECEMBER 2025 MIGRATION: Use NEW Algo Order API
            # Old create_order with type='STOP_MARKET' returns error -4120
            # Format symbol for Binance (remove / and :USDT)
            binance_symbol = symbol.replace('/', '').replace(':USDT', '')

            # FIX (Dec 11, 2025): Format price and quantity to precision
            # This fixes error -1111 for assets with high precision (e.g. RSRUSDT)
            sl_price_formatted = self.price_to_precision(symbol, new_sl_price)
            amount_formatted = self.amount_to_precision(symbol, amount)
            
            params = {
                'algoType': 'CONDITIONAL',
                'symbol': binance_symbol,
                'side': close_side,
                'type': 'STOP_MARKET',
                'triggerPrice': str(sl_price_formatted),
                'quantity': str(amount_formatted),
                'reduceOnly': 'true',
                'workingType': 'CONTRACT_PRICE',
                'priceProtect': 'FALSE',
                'timeInForce': 'GTC',
                'timestamp': self.exchange.milliseconds()
            }

            new_order = await self.rate_limiter.execute_request(
                self.exchange.fapiPrivatePostAlgoOrder,
                params
            )

            result['create_time_ms'] = int((now_utc() - create_start).total_seconds() * 1000)
            result['unprotected_window_ms'] = int((now_utc() - unprotected_start).total_seconds() * 1000)

            result['success'] = True

            logger.info(
                f"✅ Binance SL updated: cancel={result['cancel_time_ms']:.2f}ms, "
                f"create={result['create_time_ms']:.2f}ms, "
                f"unprotected={result['unprotected_window_ms']:.2f}ms"
            )

            return result

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Binance optimized SL update failed: {e}", exc_info=True)
            return result

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order"""
        try:
            result = await self.exchange.cancel_order(order_id, symbol)
            return result.get('status') == 'canceled'
        except ccxt.OrderNotFound:
            # Order not found is expected (already filled/cancelled/expired) - not an error
            logger.info(f"Order {order_id} not found (likely filled/cancelled)")
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
        """
        Fetch order details with cache fallback

        For Bybit: Falls back to cache if 500 order limit error occurs
        """
        try:
            order = await self.exchange.fetch_order(order_id, symbol)
            return self._parse_order(order)
        except ccxt.OrderNotFound:
            return None
        except ccxt.BaseError as e:
            error_msg = str(e).lower()

            # Check for Bybit 500 order limit error
            if self.name == 'bybit' and '500' in error_msg and ('order' in error_msg or 'limit' in error_msg):
                logger.warning(
                    f"⚠️ Bybit 500 order limit reached for {order_id}, "
                    f"trying cache fallback..."
                )

                # Try to get from cache
                if self.repository:
                    cached_order = await self.repository.get_cached_order(self.name, order_id)
                    if cached_order:
                        logger.info(f"✅ Retrieved order {order_id} from cache")
                        return self._parse_order(cached_order)

                logger.warning(f"Order {order_id} not found in cache either")
                return None

            logger.error(f"Failed to fetch order {order_id}: {e}")
            raise

    async def fetch_open_orders(self, symbol: str = None, params: Dict = None) -> List[OrderResult]:
        """
        Fetch open orders

        Args:
            symbol: Symbol to filter (optional)
            params: Additional parameters (e.g., {'category': 'linear', 'orderFilter': 'StopOrder'} for Bybit)
        """
        # CRITICAL FIX: Support params for Bybit category='linear' and orderFilter
        if params:
            orders = await self.exchange.fetch_open_orders(symbol, params)
        else:
            orders = await self.exchange.fetch_open_orders(symbol)
        return [self._parse_order(order) for order in orders]

    # ============== Position Management ==============

    async def close_position(self, symbol: str) -> bool:
        """
        Close position for symbol
        Creates a market order in opposite direction
        """
        # CRITICAL FIX: Same issue - use fetch_positions() without [symbol]
        all_positions = await self.fetch_positions()

        # Find position using exact symbol match first, then normalized comparison
        position = None
        for pos in all_positions:
            if pos.get('symbol') == symbol:
                position = pos
                break

        # If not found with exact match, try normalized comparison
        if not position:
            from core.position_manager import normalize_symbol
            normalized_symbol = normalize_symbol(symbol)
            for pos in all_positions:
                if normalize_symbol(pos.get('symbol')) == normalized_symbol:
                    position = pos
                    break

        if not position:
            logger.warning(f"No position found for {symbol}")
            return False

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

            # CRITICAL FIX: Convert symbol to exchange-specific format
            # DB stores 'BLASTUSDT', Bybit needs 'BLAST/USDT:USDT'
            exchange_symbol = self.find_exchange_symbol(symbol)

            if not exchange_symbol:
                logger.error(f"❌ Symbol {symbol} not available on exchange {self.name}")
                logger.error(f"   Available exchanges may have different symbol listings")
                raise ValueError(
                    f"Symbol {symbol} not available on {self.name}. "
                    f"This symbol may only be available on other exchanges."
                )

            # Use exchange_symbol for market info lookup
            market = self.markets.get(exchange_symbol)
            if not market:
                # This should never happen after find_exchange_symbol succeeds
                logger.error(f"❌ Market info not found for {exchange_symbol} after symbol conversion")
                raise ValueError(f"Market info unavailable for {symbol}")

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

            # CRITICAL FIX: Handle both precision types (decimal places vs step size)
            # CCXT can return either:
            # 1. int/high float (decimal places): precision['amount'] = 3 or 8.0
            # 2. float < 1.0 (step size): precision['amount'] = 0.001
            #
            # Bug: int(0.001) = 0 → step_size = 10**-0 = 1.0 → quantize(0.021, 1.0) = 0.0
            # Fix: Check if precision is already step size (float < 1.0) and use directly

            if isinstance(amount_precision, float) and amount_precision < 1.0:
                # Precision is already step size (e.g., 0.001 for ZECUSDT)
                step_size = amount_precision
                logger.debug(f"{symbol}: Using step size precision: {step_size}")
            else:
                # Precision is decimal places (e.g., 3 or 8)
                safe_precision = max(0, min(int(amount_precision), 18))
                if safe_precision != amount_precision:
                    logger.debug(f"Limited precision from {amount_precision} to {safe_precision} for {symbol}")
                step_size = 10 ** -safe_precision
                logger.debug(f"{symbol}: Using decimal places precision: {safe_precision} → step_size: {step_size}")

            try:
                amount_decimal = Decimal(str(amount))
                step_decimal = Decimal(str(step_size))
                amount = float(amount_decimal.quantize(step_decimal, rounding=ROUND_DOWN))
            except (InvalidOperation, OverflowError) as e:
                # Fallback to simple rounding if decimal operations fail
                logger.debug(f"Decimal operation failed for {symbol}, using simple rounding: {e}")
                # Use safe fallback based on precision type
                if isinstance(amount_precision, float) and amount_precision < 1.0:
                    # For step size, just return original amount (already validated)
                    amount = amount
                else:
                    safe_precision = max(0, min(int(amount_precision), 18))
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
            amount=to_decimal(order['amount']),
            price=to_decimal(order['price'] or 0),
            filled=to_decimal(order.get('filled', 0)),
            remaining=to_decimal(order.get('remaining', order['amount'])),
            status=order['status'],
            timestamp=timestamp,
            info=order['info']
        )

    def amount_to_precision(self, symbol: str, amount: Decimal) -> Decimal:
        """Format amount to exchange precision"""
        # CRITICAL FIX: Convert symbol to exchange-specific format
        exchange_symbol = self.find_exchange_symbol(symbol)
        if not exchange_symbol:
            logger.warning(f"Symbol {symbol} not found, using original for precision")
            exchange_symbol = symbol
        return self.exchange.amount_to_precision(exchange_symbol, amount)

    def price_to_precision(self, symbol: str, price: Decimal) -> Decimal:
        """Format price to exchange precision"""
        # CRITICAL FIX: Convert symbol to exchange-specific format
        exchange_symbol = self.find_exchange_symbol(symbol)
        if not exchange_symbol:
            logger.warning(f"Symbol {symbol} not found, using original for precision")
            exchange_symbol = symbol
        return self.exchange.price_to_precision(exchange_symbol, price)

    def get_min_amount(self, symbol: str) -> float:
        """Get minimum order amount for symbol"""
        # CRITICAL FIX: Convert symbol to exchange-specific format
        exchange_symbol = self.find_exchange_symbol(symbol) or symbol
        market = self.markets.get(exchange_symbol)
        if not market:
            return 0.001  # Default

        # For Binance: parse REAL minQty from LOT_SIZE filter (not CCXT parsed value)
        # CCXT sometimes returns stepSize instead of minQty in limits.amount.min
        if self.name == 'binance':
            info = market.get('info', {})
            filters = info.get('filters', [])

            for f in filters:
                if f.get('filterType') == 'LOT_SIZE':
                    min_qty = f.get('minQty')
                    if min_qty:
                        try:
                            min_qty_float = float(min_qty)
                            # Validate min_qty is positive
                            if min_qty_float <= 0:
                                logger.warning(f"{symbol}: Invalid minQty={min_qty_float} from exchange, using default 0.001")
                                return 0.001
                            return min_qty_float
                        except (ValueError, TypeError):
                            pass

        # Fallback to CCXT parsed value for other exchanges
        min_from_ccxt = market.get('limits', {}).get('amount', {}).get('min', 0.001)

        # Validate CCXT value too
        if min_from_ccxt <= 0:
            logger.warning(f"{symbol}: Invalid min_amount={min_from_ccxt} from CCXT, using default 0.001")
            return 0.001

        return min_from_ccxt

    def get_min_notional(self, symbol: str) -> float:
        """
        Get minimum notional value (order cost) for symbol

        Bybit: Uses minNotionalValue from lotSizeFilter
        Binance: Uses MIN_NOTIONAL filter
        Other: Returns 0 (no minimum)

        Returns:
            Minimum order value in quote currency (USDT)
        """
        exchange_symbol = self.find_exchange_symbol(symbol) or symbol
        market = self.markets.get(exchange_symbol)
        if not market:
            return 0  # No minimum

        # BYBIT: Read minNotionalValue from API info
        if self.name == 'bybit':
            info = market.get('info', {})
            lot_size_filter = info.get('lotSizeFilter', {})
            min_notional = lot_size_filter.get('minNotionalValue')

            if min_notional:
                try:
                    min_notional_float = float(min_notional)
                    if min_notional_float > 0:
                        return min_notional_float
                except (ValueError, TypeError):
                    logger.warning(f"{symbol}: Invalid minNotionalValue from Bybit API")

            # Default for Bybit USDT perpetuals
            return 5.0

        # BINANCE: Read MIN_NOTIONAL filter
        elif self.name == 'binance':
            info = market.get('info', {})
            filters = info.get('filters', [])

            for f in filters:
                if f.get('filterType') == 'MIN_NOTIONAL':
                    min_notional = f.get('minNotional') or f.get('notional')
                    if min_notional:
                        try:
                            return float(min_notional)
                        except (ValueError, TypeError):
                            pass

            # Binance futures default
            return 5.0

        # Other exchanges: no minimum cost
        return 0

    def get_tick_size(self, symbol: str) -> float:
        """Get price tick size for symbol"""
        # CRITICAL FIX: Convert symbol to exchange-specific format
        exchange_symbol = self.find_exchange_symbol(symbol) or symbol
        market = self.markets.get(exchange_symbol)
        if market:
            return market['precision']['price']
        return 0.01  # Default

    def get_step_size(self, symbol: str) -> float:
        """Get step size (amount precision) for symbol from LOT_SIZE filter"""
        exchange_symbol = self.find_exchange_symbol(symbol) or symbol
        market = self.markets.get(exchange_symbol)
        if not market:
            return 0.001  # Default

        # For Binance: parse stepSize from LOT_SIZE filter
        if self.name == 'binance':
            info = market.get('info', {})
            filters = info.get('filters', [])
            for f in filters:
                if f.get('filterType') == 'LOT_SIZE':
                    step_size = f.get('stepSize')
                    if step_size:
                        try:
                            return float(step_size)
                        except (ValueError, TypeError):
                            pass

        # Fallback to CCXT precision for other exchanges
        precision = market.get('precision', {}).get('amount')
        if precision:
            return precision
        return 0.001  # Default

    async def can_open_position(self, symbol: str, notional_usd: float, preloaded_positions: Optional[List] = None) -> Tuple[bool, str]:
        """
        Check if we can open a new position without exceeding limits

        Args:
            symbol: Trading symbol
            notional_usd: Position size in USD
            preloaded_positions: Optional pre-fetched positions list (for parallel validation)

        Returns:
            (can_open, reason)
        """
        try:
            # Step 1: Check free balance (account for leverage)
            free_usdt = await self._get_free_balance_usdt()
            total_usdt = await self._get_total_balance_usdt()
            
            # Get leverage from config
            leverage = float(config.trading.leverage)
            required_margin = float(notional_usd) / leverage

            if free_usdt < required_margin:
                return False, f"Insufficient free balance: ${free_usdt:.2f} < ${required_margin:.2f} (notional=${notional_usd:.2f}, leverage={leverage}x)"

            # Step 1.5: Check minimum active balance (reserve after opening position)
            remaining_balance = free_usdt - required_margin
            min_active_balance = float(config.safety.MINIMUM_ACTIVE_BALANCE_USD)

            if remaining_balance < min_active_balance:
                return False, (
                    f"Insufficient free balance on {self.name}: "
                    f"Opening ${notional_usd:.2f} position (margin=${required_margin:.2f}, leverage={leverage}x) would leave ${remaining_balance:.2f}, "
                    f"minimum required: ${min_active_balance:.2f}"
                )

            # Step 2: Get total current notional
            if preloaded_positions is not None:
                positions = preloaded_positions
            else:
                positions = await self.exchange.fetch_positions()
            total_notional = sum(abs(float(p.get('notional', 0)))
                                for p in positions if float(p.get('contracts', 0)) > 0)

            # Step 3: Check maxNotionalValue (Binance specific)
            if self.name == 'binance':
                try:
                    exchange_symbol = self.find_exchange_symbol(symbol)
                    symbol_clean = exchange_symbol.replace('/USDT:USDT', 'USDT')

                    position_risk = await self.exchange.fapiPrivateV2GetPositionRisk({
                        'symbol': symbol_clean
                    })

                    for risk in position_risk:
                        if risk.get('symbol') == symbol_clean:
                            max_notional_str = risk.get('maxNotionalValue', 'INF')
                            if max_notional_str != 'INF':
                                max_notional = float(max_notional_str)

                                # FIX BUG #2: Ignore maxNotional = 0 (means "no personal limit set")
                                # Binance returns "0" for symbols without open positions, not as a $0 limit
                                if max_notional > 0:
                                    new_total = total_notional + float(notional_usd)

                                    if new_total > max_notional:
                                        return False, f"Would exceed max notional: ${new_total:.2f} > ${max_notional:.2f}"
                            break
                except Exception as e:
                    # Log warning but don't block
                    logger.warning(f"Could not check maxNotionalValue for {symbol}: {e}")

            return True, "OK"

        except Exception as e:
            logger.error(f"Error checking if can open position for {symbol}: {e}")
            return False, f"Validation error: {e}"

    async def validate_order(self, symbol: str, side: str, amount: Decimal, price: Optional[Decimal] = None) -> Tuple[bool, str]:
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