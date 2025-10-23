"""
Order Executor for Aged Positions - Robust order execution with retry logic
Part of Aged Position Manager V2
"""

import asyncio
import logging
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result of order execution attempt"""
    success: bool
    order_id: Optional[str]
    order_type: str  # 'market', 'limit', 'limit_maker'
    price: Optional[Decimal]
    executed_amount: Optional[Decimal]
    error_message: Optional[str]
    attempts: int
    execution_time: float


class OrderExecutor:
    """
    Robust order executor with retry logic and fallback mechanisms
    Tries multiple order types in sequence until success
    """

    # ==================== ERROR CLASSIFICATION ====================
    # Постоянные ошибки - не retry
    PERMANENT_ERROR_PATTERNS = [
        '170003',           # Bybit: brokerId error
        '170193',           # Bybit: price cannot be
        '170209',           # Bybit: symbol not available in region
        'insufficient',     # Insufficient funds/balance
        'not available',    # Symbol/market not available
        'delisted',         # Symbol delisted
        'suspended',        # Trading suspended
    ]

    # Rate limit ошибки - retry с длинной задержкой
    RATE_LIMIT_PATTERNS = [
        '429',
        'rate limit',
        'too many requests',
        'request limit exceeded',
    ]

    # Временные ошибки - retry с exponential backoff
    TEMPORARY_ERROR_PATTERNS = [
        'timeout',
        'connection',
        'network',
        'temporary',
    ]

    @staticmethod
    def classify_error(error_message: str) -> str:
        """
        Classify error type for appropriate handling

        Returns:
            'permanent' - don't retry
            'rate_limit' - retry with long delay
            'temporary' - retry with exponential backoff
            'unknown' - retry with normal backoff
        """
        error_lower = error_message.lower()

        # Check permanent errors
        if any(pattern in error_lower for pattern in OrderExecutor.PERMANENT_ERROR_PATTERNS):
            return 'permanent'

        # Check rate limit errors
        if any(pattern in error_lower for pattern in OrderExecutor.RATE_LIMIT_PATTERNS):
            return 'rate_limit'

        # Check temporary errors
        if any(pattern in error_lower for pattern in OrderExecutor.TEMPORARY_ERROR_PATTERNS):
            return 'temporary'

        return 'unknown'
    # ==============================================================

    def __init__(self, exchange_managers, repository=None):
        self.exchanges = exchange_managers
        self.repository = repository

        # Configuration
        self.max_attempts = 3
        self.base_retry_delay = 0.5      # Base delay: 500ms
        self.max_retry_delay = 5.0       # Max delay: 5s
        self.rate_limit_delay = 15.0     # Delay for rate limit: 15s
        self.slippage_percent = Decimal('0.1')  # 0.1% slippage for limit orders

        # Order type priority sequence
        self.order_sequence = [
            'market',        # Try market order first (fastest)
            'limit_aggressive',  # Limit with slippage (likely to fill)
            'limit_maker'    # Limit as maker (best price but may not fill)
        ]

        # Statistics
        self.stats = {
            'total_executions': 0,
            'successful_market': 0,
            'successful_limit': 0,
            'failed_executions': 0,
            'retries_needed': 0
        }

    async def execute_close(
        self,
        symbol: str,
        exchange_name: str,
        position_side: str,
        amount: float,
        reason: str = 'aged_close'
    ) -> OrderResult:
        """
        Execute position close with robust retry logic

        Args:
            symbol: Trading pair symbol
            exchange_name: Exchange name (binance, bybit)
            position_side: Position side (long, short)
            amount: Amount to close
            reason: Reason for closing

        Returns:
            OrderResult with execution details
        """

        start_time = time.time()
        self.stats['total_executions'] += 1

        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            error_msg = f"Exchange {exchange_name} not found"
            logger.error(error_msg)
            return OrderResult(
                success=False,
                order_id=None,
                order_type='none',
                price=None,
                executed_amount=None,
                error_message=error_msg,
                attempts=0,
                execution_time=time.time() - start_time
            )

        # Determine close side (opposite of position)
        close_side = 'sell' if position_side in ['long', 'buy'] else 'buy'

        # Try each order type in sequence
        total_attempts = 0
        last_error = None

        for order_type in self.order_sequence:
            for attempt in range(self.max_attempts):
                total_attempts += 1

                try:
                    logger.info(
                        f"📤 Executing {order_type} close for {symbol}: "
                        f"attempt {attempt + 1}/{self.max_attempts}"
                    )

                    # Execute based on order type
                    if order_type == 'market':
                        result = await self._execute_market_order(
                            exchange, symbol, close_side, amount
                        )
                    elif order_type == 'limit_aggressive':
                        result = await self._execute_limit_aggressive(
                            exchange, symbol, close_side, amount
                        )
                    elif order_type == 'limit_maker':
                        result = await self._execute_limit_maker(
                            exchange, symbol, close_side, amount
                        )
                    else:
                        continue

                    # Check if successful
                    if result and result.get('id'):
                        execution_time = time.time() - start_time

                        # Update statistics
                        if order_type == 'market':
                            self.stats['successful_market'] += 1
                        else:
                            self.stats['successful_limit'] += 1

                        if total_attempts > 1:
                            self.stats['retries_needed'] += 1

                        logger.info(
                            f"✅ Order executed successfully: "
                            f"id={result['id']}, type={order_type}, "
                            f"attempts={total_attempts}, time={execution_time:.2f}s"
                        )

                        # Log to database if available
                        if self.repository and reason.startswith('aged_'):
                            await self._log_order_execution(
                                symbol, result['id'], order_type,
                                total_attempts, execution_time, reason
                            )

                        # Safely convert price and amount to Decimal
                        price_value = result.get('price')
                        amount_value = result.get('amount')

                        return OrderResult(
                            success=True,
                            order_id=result['id'],
                            order_type=order_type,
                            price=Decimal(str(price_value)) if price_value else Decimal('0'),
                            executed_amount=Decimal(str(amount_value)) if amount_value else Decimal(str(amount)),
                            error_message=None,
                            attempts=total_attempts,
                            execution_time=execution_time
                        )

                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        f"Order attempt failed: {order_type} "
                        f"attempt {attempt + 1}: {e}"
                    )

                    # Wait before retry (except on last attempt)
                    if attempt < self.max_attempts - 1:
                        await asyncio.sleep(self.retry_delay)

        # All attempts failed
        self.stats['failed_executions'] += 1
        execution_time = time.time() - start_time

        logger.error(
            f"❌ Failed to execute order after {total_attempts} attempts: "
            f"{last_error}"
        )

        return OrderResult(
            success=False,
            order_id=None,
            order_type='failed',
            price=None,
            executed_amount=None,
            error_message=last_error,
            attempts=total_attempts,
            execution_time=execution_time
        )

    async def _execute_market_order(
        self,
        exchange,
        symbol: str,
        side: str,
        amount: float
    ) -> Dict:
        """Execute market order"""

        params = {'reduceOnly': True}

        # Exchange-specific parameters
        if exchange.exchange.id == 'binance':
            params['type'] = 'MARKET'

        return await exchange.exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=amount,
            params=params
        )

    async def _execute_limit_aggressive(
        self,
        exchange,
        symbol: str,
        side: str,
        amount: float
    ) -> Dict:
        """Execute limit order with aggressive pricing for quick fill"""

        # Get current market price
        ticker = await exchange.exchange.fetch_ticker(symbol)
        current_price = Decimal(str(ticker['last']))

        # Validate ticker price
        if current_price <= 0:
            raise Exception(f"Invalid ticker price for {symbol}: {current_price}")

        # Calculate aggressive price (with slippage)
        if side == 'buy':
            # For buy, use higher price
            limit_price = current_price * (Decimal('1') + self.slippage_percent / Decimal('100'))
        else:
            # For sell, use lower price
            limit_price = current_price * (Decimal('1') - self.slippage_percent / Decimal('100'))

        # Round to exchange precision
        limit_price = self._round_price(limit_price, symbol)

        params = {
            'reduceOnly': True,
            'timeInForce': 'IOC'  # Immediate or Cancel
        }

        logger.debug(
            f"Limit aggressive: {side} {amount} @ {limit_price} "
            f"(market: {current_price})"
        )

        return await exchange.exchange.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=float(limit_price),
            params=params
        )

    async def _execute_limit_maker(
        self,
        exchange,
        symbol: str,
        side: str,
        amount: float
    ) -> Dict:
        """Execute limit order as maker (post-only)"""

        # Get order book for best price
        order_book = await exchange.exchange.fetch_order_book(symbol, limit=5)

        # Check if order book is valid
        if not order_book:
            raise Exception("Order book is empty")

        # Use best bid/ask for maker order
        if side == 'buy':
            # Check bids exist and are valid
            if not order_book.get('bids') or len(order_book['bids']) == 0:
                raise Exception("No bids in order book")
            if len(order_book['bids'][0]) < 1:
                raise Exception("Invalid bid format")
            # Place at top of bid
            limit_price = Decimal(str(order_book['bids'][0][0]))
        else:
            # Check asks exist and are valid
            if not order_book.get('asks') or len(order_book['asks']) == 0:
                raise Exception("No asks in order book")
            if len(order_book['asks'][0]) < 1:
                raise Exception("Invalid ask format")
            # Place at top of ask
            limit_price = Decimal(str(order_book['asks'][0][0]))

        # Validate price is positive
        if limit_price <= 0:
            raise Exception(f"Invalid price from order book: {limit_price}")

        params = {
            'reduceOnly': True,
            'postOnly': True  # Maker only
        }

        if exchange.exchange.id == 'bybit':
            params['timeInForce'] = 'PostOnly'
        elif exchange.exchange.id == 'binance':
            params['timeInForce'] = 'GTX'  # Good Till Crossing (Post-Only)

        logger.debug(
            f"Limit maker: {side} {amount} @ {limit_price}"
        )

        return await exchange.exchange.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=float(limit_price),
            params=params
        )

    def _round_price(self, price: Decimal, symbol: str) -> Decimal:
        """Round price to appropriate precision for symbol"""

        # Determine precision based on price magnitude
        if price >= Decimal('1000'):
            # For prices > 1000 - 2 decimal places
            return price.quantize(Decimal('0.01'))
        elif price >= Decimal('100'):
            # For prices 100-1000 - 3 decimal places
            return price.quantize(Decimal('0.001'))
        elif price >= Decimal('10'):
            # For prices 10-100 - 4 decimal places
            return price.quantize(Decimal('0.0001'))
        elif price >= Decimal('1'):
            # For prices 1-10 - 5 decimal places
            return price.quantize(Decimal('0.00001'))
        elif price >= Decimal('0.1'):
            # For prices 0.1-1 - 6 decimal places
            return price.quantize(Decimal('0.000001'))
        elif price >= Decimal('0.01'):
            # For prices 0.01-0.1 - 7 decimal places
            return price.quantize(Decimal('0.0000001'))
        else:
            # For prices < 0.01 - 8 decimal places (max precision)
            return price.quantize(Decimal('0.00000001'))

    async def _log_order_execution(
        self,
        symbol: str,
        order_id: str,
        order_type: str,
        attempts: int,
        execution_time: float,
        reason: str
    ):
        """Log order execution to database"""

        if not self.repository:
            return

        try:
            await self.repository.create_aged_monitoring_event(
                aged_position_id=symbol,  # Use symbol as ID for now
                event_type='order_executed',
                event_metadata={
                    'order_id': order_id,
                    'order_type': order_type,
                    'attempts': attempts,
                    'execution_time': execution_time,
                    'reason': reason
                }
            )
        except Exception as e:
            logger.error(f"Failed to log order execution: {e}")

    async def cancel_open_orders(self, symbol: str, exchange_name: str) -> int:
        """
        Cancel all open orders for symbol
        Used for cleanup before placing new orders
        """

        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return 0

        try:
            # Fetch open orders
            open_orders = await exchange.exchange.fetch_open_orders(symbol)

            if not open_orders:
                return 0

            cancelled_count = 0
            for order in open_orders:
                try:
                    await exchange.exchange.cancel_order(order['id'], symbol)
                    cancelled_count += 1
                    logger.info(f"Cancelled order {order['id']} for {symbol}")
                except Exception as e:
                    logger.warning(f"Failed to cancel order {order['id']}: {e}")

            return cancelled_count

        except Exception as e:
            logger.error(f"Failed to fetch/cancel open orders: {e}")
            return 0

    def get_stats(self) -> Dict:
        """Get execution statistics"""

        success_rate = 0
        if self.stats['total_executions'] > 0:
            success_rate = (
                (self.stats['successful_market'] + self.stats['successful_limit']) /
                self.stats['total_executions'] * 100
            )

        return {
            'total_executions': self.stats['total_executions'],
            'successful_market': self.stats['successful_market'],
            'successful_limit': self.stats['successful_limit'],
            'failed_executions': self.stats['failed_executions'],
            'retries_needed': self.stats['retries_needed'],
            'success_rate': f"{success_rate:.1f}%"
        }

    async def test_connectivity(self, exchange_name: str) -> bool:
        """Test exchange connectivity before execution"""

        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return False

        try:
            # Simple connectivity test
            await exchange.exchange.fetch_time()
            return True
        except Exception as e:
            logger.error(f"Exchange connectivity test failed: {e}")
            return False