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
                    # КРИТИЧНО: Для Bybit ОБЯЗАТЕЛЬНО params={'category': 'linear'}
                    positions = await self.exchange.fetch_positions(
                        symbols=[symbol],
                        params={'category': 'linear'}
                    )

                    for pos in positions:
                        if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
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
                self.logger.info(
                    f"⚠️ Stop Loss already exists at {existing_sl}, skipping"
                )
                return {
                    'status': 'already_exists',
                    'stopPrice': existing_sl,
                    'reason': 'Stop Loss already set'
                }

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
    ) -> bool:
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
            bool: True if SL verified/created, False if position closed

        Usage:
            Called from position_manager monitoring loop every 60 seconds
        """
        symbol = position.symbol

        try:
            # STEP 1: Check if Stop Loss exists
            has_sl, existing_sl = await self.has_stop_loss(symbol)

            if has_sl:
                self.logger.debug(f"✅ SL verified for {symbol}: {existing_sl}")
                return True

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
                        amount=float(position.size),
                        stop_price=stop_price
                    )

                    if result['status'] in ['created', 'already_exists']:
                        self.logger.info(
                            f"✅ SL recreated for {symbol} at {result['stopPrice']} "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        return True

                except Exception as e:
                    error_msg = str(e).lower()

                    # Handle common errors
                    if 'position' in error_msg and ('not found' in error_msg or 'closed' in error_msg):
                        self.logger.info(
                            f"Position {symbol} closed during SL recreation, skipping"
                        )
                        return False

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
                        return False

            return False

        except Exception as e:
            self.logger.error(f"Error in verify_and_fix_missing_sl for {symbol}: {e}")
            return False

    async def _set_bybit_stop_loss(self, symbol: str, stop_price: float) -> Dict:
        """
        Установка Stop Loss для Bybit через position-attached method.

        Источник: core/exchange_manager.py:create_stop_loss_order (Bybit секция)
        """
        try:
            # ШАГ 1: Получить позицию для positionIdx
            positions = await self.exchange.fetch_positions(
                symbols=[symbol],
                params={'category': 'linear'}
            )

            position_idx = 0
            position_found = False

            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    position_idx = int(pos.get('info', {}).get('positionIdx', 0))
                    position_found = True
                    break

            if not position_found:
                raise ValueError(f"No open position found for {symbol}")

            # ШАГ 2: Форматирование для Bybit API
            bybit_symbol = symbol.replace('/', '').replace(':USDT', '')
            sl_price_formatted = self.exchange.price_to_precision(symbol, stop_price)

            # ШАГ 3: Установка через set_trading_stop (position-attached)
            params = {
                'category': 'linear',
                'symbol': bybit_symbol,
                'stopLoss': str(sl_price_formatted),
                'positionIdx': position_idx,
                'slTriggerBy': 'LastPrice',
                'tpslMode': 'Full'
            }

            self.logger.debug(f"Bybit set_trading_stop params: {params}")

            result = await self.exchange.private_post_v5_position_trading_stop(params)

            # Обработка результата
            ret_code = result.get('retCode', 1)
            ret_msg = result.get('retMsg', 'Unknown error')

            if ret_code == 0:
                # Успех
                self.logger.info(f"✅ Stop Loss set successfully at {sl_price_formatted}")
                return {
                    'status': 'created',
                    'stopPrice': float(sl_price_formatted),
                    'info': result
                }
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
                raise Exception(f"Bybit API error {ret_code}: {ret_msg}")

        except Exception as e:
            self.logger.error(f"Failed to set Bybit Stop Loss: {e}")
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
                        raise
                else:
                    # Other error - don't retry
                    self.logger.error(f"Failed to create stop order: {e}")
                    raise

        # Should not reach here
        raise Exception(f"Failed to create SL after {max_retries} retries")

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