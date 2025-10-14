"""
Единый источник истины для всей логики Stop Loss в системе.

Этот модуль содержит:
- Проверку наличия SL
- Установку SL
- Верификацию SL
- Все SL-related операции

Все остальные модули ДОЛЖНЫ использовать ТОЛЬКО этот модуль.

Основан на ПРОВЕРЕННОЙ логике из core/position_manager.py (работает в production).
"""

import logging
from typing import Optional, Dict, Tuple, List
from decimal import Decimal
import ccxt
from core.event_logger import get_event_logger, EventType

logger = logging.getLogger(__name__)


class StopLossManager:
    """
    Централизованный менеджер Stop Loss операций.

    🎯 ЕДИНСТВЕННЫЙ источник истины для всех SL операций в системе.

    Основан на ПРОВЕРЕННОЙ логике из core/position_manager.py:1324
    """

    def __init__(self, exchange, exchange_name: str):
        """
        Args:
            exchange: CCXT exchange instance
            exchange_name: Exchange name ('bybit', 'binance', etc.)
        """
        self.exchange = exchange
        self.exchange_name = exchange_name.lower()
        self.logger = logger

    async def has_stop_loss(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        ЕДИНСТВЕННАЯ функция проверки наличия Stop Loss.

        Args:
            symbol: CCXT unified symbol (e.g., 'BTC/USDT:USDT')

        Returns:
            Tuple[bool, Optional[str]]: (has_sl, sl_price)

        Проверяет в следующем порядке:
        1. Position-attached SL (для Bybit через position.info.stopLoss) - ПРИОРИТЕТ 1
        2. Conditional stop orders (через fetch_open_orders) - ПРИОРИТЕТ 2

        Источник логики: core/position_manager.py:1324 (ПРОВЕРЕН в production)
        """
        try:
            self.logger.debug(f"Checking Stop Loss for {symbol} on {self.exchange_name}")

            # ============================================================
            # ПРИОРИТЕТ 1: Position-attached Stop Loss (для Bybit)
            # ============================================================
            if self.exchange_name == 'bybit':
                try:
                    # CRITICAL FIX: Import normalize_symbol for symbol comparison
                    from core.position_manager import normalize_symbol

                    # КРИТИЧНО: Fetch ALL positions since symbol format may not match
                    positions = await self.exchange.fetch_positions(
                        params={'category': 'linear'}
                    )

                    normalized_symbol = normalize_symbol(symbol)

                    for pos in positions:
                        if normalize_symbol(pos['symbol']) == normalized_symbol and float(pos.get('contracts', 0)) > 0:
                            # КРИТИЧНО: Проверяем position.info.stopLoss
                            # Источник: core/position_manager.py:1324
                            stop_loss = pos.get('info', {}).get('stopLoss', '0')

                            self.logger.debug(
                                f"Bybit position {symbol}: stopLoss='{stop_loss}' "
                                f"(type: {type(stop_loss)})"
                            )

                            # КРИТИЧНО: Проверяем все варианты "нет SL"
                            # Bybit возвращает '0' если нет SL, или реальную цену если есть
                            if stop_loss and stop_loss not in ['0', '0.00', '', None]:
                                self.logger.info(
                                    f"✅ Position {symbol} has Stop Loss: {stop_loss}"
                                )
                                return True, stop_loss
                            else:
                                self.logger.debug(
                                    f"No position-attached SL for {symbol} "
                                    f"(stopLoss='{stop_loss}')"
                                )

                except Exception as e:
                    self.logger.debug(f"Could not check Bybit position SL: {e}")

            # ============================================================
            # ПРИОРИТЕТ 2: Conditional stop orders (для всех бирж)
            # ============================================================
            try:
                # Получить stop orders
                if self.exchange_name == 'bybit':
                    # КРИТИЧНО: Для Bybit добавляем category='linear'
                    orders = await self.exchange.fetch_open_orders(
                        symbol,
                        params={
                            'category': 'linear',
                            'orderFilter': 'StopOrder'
                        }
                    )
                else:
                    orders = await self.exchange.fetch_open_orders(symbol)

                # Проверить есть ли stop loss orders
                for order in orders:
                    if self._is_stop_loss_order(order):
                        sl_price = self._extract_stop_price(order)
                        self.logger.info(
                            f"✅ Position {symbol} has Stop Loss order: {order.get('id')} "
                            f"at {sl_price}"
                        )
                        return True, str(sl_price) if sl_price else None

            except Exception as e:
                self.logger.debug(f"Could not check stop orders for {symbol}: {e}")

            # Нет Stop Loss
            self.logger.debug(f"No Stop Loss found for {symbol}")
            return False, None

        except Exception as e:
            self.logger.error(f"Error checking Stop Loss for {symbol}: {e}")
            # В случае ошибки безопаснее вернуть False
            return False, None

    async def set_stop_loss(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float
    ) -> Dict:
        """
        ЕДИНСТВЕННАЯ функция установки Stop Loss.

        Args:
            symbol: CCXT unified symbol
            side: 'sell' для long, 'buy' для short
            amount: размер позиции
            stop_price: цена Stop Loss

        Returns:
            Dict: информация об установленном SL

        Источник логики: core/exchange_manager.py:create_stop_loss_order (ПРОВЕРЕН)
        """
        self.logger.info(f"Setting Stop Loss for {symbol} at {stop_price}")

        try:
            # ШАГ 1: Проверить что SL еще не установлен
            has_sl, existing_sl = await self.has_stop_loss(symbol)

            if has_sl:
                # CRITICAL FIX: Validate existing SL before reusing
                # This prevents reusing old SL from previous positions with different entry prices
                is_valid, reason = self._validate_existing_sl(
                    existing_sl_price=float(existing_sl),
                    target_sl_price=float(stop_price),
                    side=side,
                    tolerance_percent=5.0
                )

                if is_valid:
                    # Existing SL is valid and can be reused
                    self.logger.info(
                        f"✅ Stop Loss already exists at {existing_sl} and is valid ({reason}), skipping"
                    )
                    return {
                        'status': 'already_exists',
                        'stopPrice': existing_sl,
                        'reason': 'Stop Loss already set and validated'
                    }
                else:
                    # Existing SL is invalid (wrong price from previous position)
                    self.logger.warning(
                        f"⚠️ Stop Loss exists at {existing_sl} but is INVALID: {reason}"
                    )
                    self.logger.info(
                        f"🔄 Cancelling old SL and creating new one at {stop_price}"
                    )

                    # Cancel the invalid SL
                    await self._cancel_existing_sl(symbol, float(existing_sl))

                    # Fall through to create new SL below

            # ШАГ 2: Установка через ExchangeManager
            # Используем проверенную логику из core/exchange_manager.py
            if self.exchange_name == 'bybit':
                return await self._set_bybit_stop_loss(symbol, stop_price)
            else:
                return await self._set_generic_stop_loss(symbol, side, amount, stop_price)

        except Exception as e:
            self.logger.error(f"Failed to set Stop Loss for {symbol}: {e}")
            raise

    async def verify_and_fix_missing_sl(
        self,
        position,
        stop_price: float,
        max_retries: int = 3
    ):
        """
        Verify Stop Loss exists on exchange and recreate if missing.

        This method fixes the "Missing SL" warnings by:
        1. Checking if position still exists on exchange
        2. Verifying SL is present
        3. Auto-recreating SL if missing (with retries)

        Args:
            position: Position object with symbol, exchange, side, size
            stop_price: Calculated stop loss price
            max_retries: Maximum recreation attempts (default: 3)

        Returns:
            tuple: (success: bool, order_id: str or None)
                - (True, order_id) if SL created
                - (True, None) if SL already exists
                - (False, None) if position closed or failed

        Usage:
            Called from position_manager monitoring loop every 60 seconds
        """
        symbol = position.symbol

        try:
            # STEP 1: Check if Stop Loss exists
            has_sl, existing_sl = await self.has_stop_loss(symbol)

            if has_sl:
                self.logger.debug(f"✅ SL verified for {symbol}: {existing_sl}")
                return True, None  # CRITICAL FIX: Return tuple

            # STEP 2: SL missing - attempt to recreate
            self.logger.warning(
                f"🔧 Stop Loss missing for {symbol}, attempting to recreate..."
            )

            # Determine order side based on position side
            if position.side in ['long', 'buy']:
                order_side = 'sell'  # Close long with sell
            else:
                order_side = 'buy'  # Close short with buy

            # STEP 3: Retry SL creation
            for attempt in range(max_retries):
                try:
                    result = await self.set_stop_loss(
                        symbol=symbol,
                        side=order_side,
                        amount=float(position.quantity),
                        stop_price=stop_price
                    )

                    if result['status'] in ['created', 'already_exists']:
                        # CRITICAL FIX: Return order_id for whitelist protection
                        order_id = result.get('orderId') or result.get('info', {}).get('id')
                        self.logger.info(
                            f"✅ SL recreated for {symbol} at {result['stopPrice']} "
                            f"(attempt {attempt + 1}/{max_retries}), order_id={order_id}"
                        )
                        return True, order_id

                except Exception as e:
                    error_msg = str(e).lower()

                    # Handle common errors
                    if 'position' in error_msg and ('not found' in error_msg or 'closed' in error_msg):
                        self.logger.info(
                            f"Position {symbol} closed during SL recreation, skipping"
                        )
                        return False, None  # CRITICAL FIX: Return tuple

                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"⚠️ Failed to recreate SL (attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        # Wait before retry (exponential backoff)
                        import asyncio
                        await asyncio.sleep(2 ** attempt)
                        continue
                    else:
                        self.logger.error(
                            f"❌ Failed to recreate SL after {max_retries} attempts: {e}"
                        )
                        return False, None  # CRITICAL FIX: Return tuple

            return False, None  # CRITICAL FIX: Return tuple

        except Exception as e:
            self.logger.error(f"Error in verify_and_fix_missing_sl for {symbol}: {e}")
            return False, None  # CRITICAL FIX: Return tuple

    async def _set_bybit_stop_loss(self, symbol: str, stop_price: float) -> Dict:
        """
        Установка Stop Loss для Bybit через position-attached method.

        Источник: core/exchange_manager.py:create_stop_loss_order (Bybit секция)
        """
        try:
            # CRITICAL FIX: Direct SL placement without fetch_positions
            # Race condition fix: Bybit position may not be visible via fetch_positions
            # immediately after order creation. Let Bybit API validate position existence.
            # If position doesn't exist, Bybit returns retCode=10001

            # Format for Bybit API (no fetch_positions needed)
            bybit_symbol = symbol.replace('/', '').replace(':USDT', '')
            sl_price_formatted = self.exchange.price_to_precision(symbol, stop_price)

            # Set SL via trading_stop (position-attached)
            params = {
                'category': 'linear',
                'symbol': bybit_symbol,
                'stopLoss': str(sl_price_formatted),
                'positionIdx': 0,  # One-way mode (default)
                'slTriggerBy': 'LastPrice',
                'tpslMode': 'Full'
            }

            self.logger.debug(f"Bybit set_trading_stop params: {params}")

            result = await self.exchange.private_post_v5_position_trading_stop(params)

            # Обработка результата
            # CRITICAL FIX: Convert retCode to int (Bybit API returns string "0", not number 0)
            ret_code = int(result.get('retCode', 1))
            ret_msg = result.get('retMsg', 'Unknown error')

            if ret_code == 0:
                # Успех
                self.logger.info(f"✅ Stop Loss set successfully at {sl_price_formatted}")

                # Log SL placement
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.STOP_LOSS_PLACED,
                        {
                            'symbol': symbol,
                            'exchange': self.exchange_name,
                            'stop_price': float(sl_price_formatted),
                            'method': 'position_attached',
                            'trigger_by': 'LastPrice'
                        },
                        symbol=symbol,
                        exchange=self.exchange_name,
                        severity='INFO'
                    )

                return {
                    'status': 'created',
                    'stopPrice': float(sl_price_formatted),
                    'info': result
                }
            elif ret_code == 10001:
                # Position not found (race condition - position not visible yet)
                raise ValueError(f"No open position found for {symbol}")
            elif ret_code == 34040 and 'not modified' in ret_msg:
                # SL уже установлен на правильной цене
                self.logger.info(f"✅ Stop Loss already set at {stop_price} (not modified)")
                return {
                    'status': 'already_exists',
                    'stopPrice': float(sl_price_formatted),
                    'info': result
                }
            else:
                # Ошибка
                error_message = f"Bybit API error {ret_code}: {ret_msg}"

                # Log SL error
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.STOP_LOSS_ERROR,
                        {
                            'symbol': symbol,
                            'exchange': self.exchange_name,
                            'stop_price': float(sl_price_formatted),
                            'error': error_message,
                            'ret_code': ret_code
                        },
                        symbol=symbol,
                        exchange=self.exchange_name,
                        severity='ERROR'
                    )

                raise Exception(error_message)

        except Exception as e:
            self.logger.error(f"Failed to set Bybit Stop Loss: {e}")

            # Log SL error (if not already logged)
            if 'Bybit API error' not in str(e):
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.STOP_LOSS_ERROR,
                        {
                            'symbol': symbol,
                            'exchange': self.exchange_name,
                            'error': str(e)
                        },
                        symbol=symbol,
                        exchange=self.exchange_name,
                        severity='ERROR'
                    )

            raise

    async def _set_generic_stop_loss(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float
    ) -> Dict:
        """
        Установка Stop Loss для других бирж через conditional orders.

        Enhanced with:
        - Current price validation (fixes Error -2021)
        - Mark price support for Binance Futures
        - Retry logic with progressive adjustment
        - 0.1% safety buffer
        """
        from decimal import Decimal, ROUND_DOWN, ROUND_UP

        max_retries = 3
        stop_price_decimal = Decimal(str(stop_price))

        for attempt in range(max_retries):
            try:
                # STEP 1: Get current market price
                ticker = await self.exchange.fetch_ticker(symbol)

                # Use mark price for Binance Futures (critical for accuracy)
                if self.exchange_name == 'binance':
                    current_price = Decimal(
                        str(ticker.get('info', {}).get('markPrice', ticker['last']))
                    )
                else:
                    current_price = Decimal(str(ticker['last']))

                # STEP 2: Validate and adjust stop price with safety buffer
                min_buffer_pct = Decimal('0.1')  # 0.1% minimum distance

                # Calculate required stop price bounds
                if side == 'sell':  # LONG position
                    # Stop must be < current price (sell to close)
                    max_allowed_stop = current_price * (Decimal('1') - min_buffer_pct / Decimal('100'))

                    if stop_price_decimal >= max_allowed_stop:
                        # Adjust down with buffer
                        adjusted_stop = max_allowed_stop * Decimal('0.999')  # Additional 0.1% buffer
                        self.logger.warning(
                            f"⚠️ Adjusting SL down: {stop_price} → {adjusted_stop} "
                            f"(current: {current_price}, attempt {attempt + 1}/{max_retries})"
                        )
                        stop_price_decimal = adjusted_stop

                else:  # SHORT position
                    # Stop must be > current price (buy to close)
                    min_allowed_stop = current_price * (Decimal('1') + min_buffer_pct / Decimal('100'))

                    if stop_price_decimal <= min_allowed_stop:
                        # Adjust up with buffer
                        adjusted_stop = min_allowed_stop * Decimal('1.001')  # Additional 0.1% buffer
                        self.logger.warning(
                            f"⚠️ Adjusting SL up: {stop_price} → {adjusted_stop} "
                            f"(current: {current_price}, attempt {attempt + 1}/{max_retries})"
                        )
                        stop_price_decimal = adjusted_stop

                # Format price with exchange precision
                final_stop_price = float(stop_price_decimal)
                final_stop_price = self.exchange.price_to_precision(symbol, final_stop_price)

                self.logger.info(
                    f"📊 Creating SL for {symbol}: stop={final_stop_price}, "
                    f"current={current_price}, side={side}"
                )

                # STEP 3: Create order with validated price
                order = await self.exchange.create_order(
                    symbol=symbol,
                    type='stop_market',
                    side=side,
                    amount=amount,
                    price=None,  # Market order при срабатывании
                    params={
                        'stopPrice': final_stop_price,
                        'reduceOnly': True
                    }
                )

                self.logger.info(f"✅ Stop Loss order created: {order['id']}")

                # Log SL placement
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.STOP_LOSS_PLACED,
                        {
                            'symbol': symbol,
                            'exchange': self.exchange_name,
                            'stop_price': float(final_stop_price),
                            'order_id': order['id'],
                            'method': 'stop_market',
                            'side': side
                        },
                        symbol=symbol,
                        exchange=self.exchange_name,
                        severity='INFO'
                    )

                return {
                    'status': 'created',
                    'stopPrice': float(final_stop_price),
                    'orderId': order['id'],
                    'info': order
                }

            except Exception as e:
                error_msg = str(e).lower()

                # Check for Error -2021 (would immediately trigger)
                if '-2021' in error_msg or 'immediately trigger' in error_msg:
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"⚠️ Error -2021 on attempt {attempt + 1}, "
                            f"retrying with adjusted price..."
                        )
                        # Aggressive adjustment for next attempt
                        if side == 'sell':
                            stop_price_decimal *= Decimal('0.995')  # 0.5% lower
                        else:
                            stop_price_decimal *= Decimal('1.005')  # 0.5% higher
                        continue
                    else:
                        self.logger.error(
                            f"❌ Failed to create SL after {max_retries} attempts: {e}"
                        )

                        # Log SL error
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.STOP_LOSS_ERROR,
                                {
                                    'symbol': symbol,
                                    'exchange': self.exchange_name,
                                    'stop_price': stop_price,
                                    'error': str(e),
                                    'attempts': max_retries
                                },
                                symbol=symbol,
                                exchange=self.exchange_name,
                                severity='ERROR'
                            )

                        raise
                else:
                    # Other error - don't retry
                    self.logger.error(f"Failed to create stop order: {e}")

                    # Log SL error
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.STOP_LOSS_ERROR,
                            {
                                'symbol': symbol,
                                'exchange': self.exchange_name,
                                'stop_price': stop_price,
                                'error': str(e)
                            },
                            symbol=symbol,
                            exchange=self.exchange_name,
                            severity='ERROR'
                        )

                    raise

        # Should not reach here
        final_error = f"Failed to create SL after {max_retries} retries"

        # Log SL error
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.STOP_LOSS_ERROR,
                {
                    'symbol': symbol,
                    'exchange': self.exchange_name,
                    'stop_price': stop_price,
                    'error': final_error,
                    'attempts': max_retries
                },
                symbol=symbol,
                exchange=self.exchange_name,
                severity='ERROR'
            )

        raise Exception(final_error)

    def _is_stop_loss_order(self, order: Dict) -> bool:
        """
        Определяет является ли ордер Stop Loss.

        КРИТИЧНО: НЕ путать с обычными limit exit ордерами!

        Источник: core/position_manager.py + core/order_utils.py
        """
        try:
            # Получить данные ордера
            info = order.get('info', {})
            order_type = order.get('type', '')
            reduce_only = order.get('reduceOnly', False)

            # ПРИОРИТЕТ 1: stopOrderType (Bybit)
            stop_order_type = info.get('stopOrderType', '')
            if stop_order_type and stop_order_type not in ['', 'UNKNOWN']:
                # Проверяем что это именно Stop Loss, а не Take Profit
                if any(keyword in stop_order_type.lower() for keyword in ['stop', 'sl']):
                    return True

            # ПРИОРИТЕТ 2: type содержит 'stop'
            if 'stop' in order_type.lower() and reduce_only:
                return True

            # ПРИОРИТЕТ 3: есть triggerPrice и reduceOnly
            trigger_price = order.get('triggerPrice') or info.get('triggerPrice')
            stop_price = order.get('stopPrice') or info.get('stopPrice')

            if (trigger_price or stop_price) and reduce_only:
                return True

            return False

        except Exception as e:
            self.logger.debug(f"Error checking if order is stop loss: {e}")
            return False

    def _extract_stop_price(self, order: Dict) -> Optional[float]:
        """Извлекает цену Stop Loss из ордера"""
        try:
            # Попробовать разные поля
            price_fields = [
                'stopPrice',
                'triggerPrice',
                ('info', 'stopPrice'),
                ('info', 'triggerPrice'),
                ('info', 'stopLoss')
            ]

            for field in price_fields:
                if isinstance(field, tuple):
                    value = order.get(field[0], {}).get(field[1])
                else:
                    value = order.get(field)

                if value and value not in ['0', '0.00', '', None]:
                    return float(value)

            return None

        except Exception as e:
            self.logger.debug(f"Error extracting stop price: {e}")
            return None

    def _validate_existing_sl(
        self,
        existing_sl_price: float,
        target_sl_price: float,
        side: str,
        tolerance_percent: float = 5.0
    ) -> tuple:
        """
        CRITICAL FIX: Validate if existing SL is acceptable for current position

        This prevents reusing old SL from previous positions that may have:
        - Wrong price (different entry price)
        - Wrong direction (opposite position type)

        Args:
            existing_sl_price: Price of existing SL on exchange
            target_sl_price: Desired SL price for new position
            side: 'sell' for LONG position, 'buy' for SHORT position
            tolerance_percent: Allow X% price difference (default: 5%)

        Returns:
            tuple: (is_valid: bool, reason: str)

        Validation rules:
        1. Price difference must be within tolerance
        2. Price ratio should be reasonable (0.5x - 2.0x)
        """
        # Rule 1: Check price difference
        price_diff_percent = abs(existing_sl_price - target_sl_price) / target_sl_price * 100

        if price_diff_percent > tolerance_percent:
            return False, f"Price differs by {price_diff_percent:.2f}% (> {tolerance_percent}%)"

        # Rule 2: Check price ratio (prevents reusing SL from vastly different price range)
        ratio = existing_sl_price / target_sl_price
        if ratio < 0.5 or ratio > 2.0:
            return False, f"Price ratio {ratio:.2f} outside reasonable range (0.5-2.0)"

        return True, "SL is valid and can be reused"

    async def _cancel_existing_sl(self, symbol: str, sl_price: float):
        """
        CRITICAL FIX: Cancel existing (invalid) SL order

        Args:
            symbol: Trading symbol
            sl_price: SL price to help identify order

        Raises:
            Exception if cancellation fails
        """
        try:
            # Fetch open orders
            open_orders = await self.exchange.fetch_open_orders(symbol)

            # Find and cancel stop orders matching the price
            for order in open_orders:
                order_type = order.get('type', '').lower()
                is_stop = 'stop' in order_type or order_type in ['stop_market', 'stop_loss', 'stop_loss_limit']

                if is_stop:
                    # Check if this is the SL we want to cancel (match by price)
                    order_stop_price = order.get('stopPrice', order.get('price'))

                    if order_stop_price:
                        # Match by price (within 1% tolerance)
                        price_diff = abs(float(order_stop_price) - float(sl_price)) / float(sl_price)

                        if price_diff < 0.01:  # Within 1%
                            self.logger.info(f"Cancelling old SL order {order['id']} at {order_stop_price}")
                            await self.exchange.cancel_order(order['id'], symbol)
                            return

            self.logger.warning(f"No matching SL order found to cancel (price: {sl_price})")

        except Exception as e:
            self.logger.error(f"Error cancelling SL: {e}")
            raise


# ============================================================
# HELPER FUNCTIONS для обратной совместимости
# ============================================================

async def check_stop_loss_unified(exchange, exchange_name: str, symbol: str) -> bool:
    """
    Унифицированная функция проверки SL для использования в старых модулях.

    Args:
        exchange: CCXT exchange instance
        exchange_name: Exchange name
        symbol: Trading symbol

    Returns:
        bool: True если есть Stop Loss
    """
    manager = StopLossManager(exchange, exchange_name)
    has_sl, _ = await manager.has_stop_loss(symbol)
    return has_sl


async def set_stop_loss_unified(
    exchange,
    exchange_name: str,
    symbol: str,
    side: str,
    amount: float,
    stop_price: float
) -> Dict:
    """
    Унифицированная функция установки SL для использования в старых модулях.

    Args:
        exchange: CCXT exchange instance
        exchange_name: Exchange name
        symbol: Trading symbol
        side: Order side
        amount: Position size
        stop_price: Stop loss price

    Returns:
        Dict: Result of SL creation
    """
    manager = StopLossManager(exchange, exchange_name)
    return await manager.set_stop_loss(symbol, side, amount, stop_price)