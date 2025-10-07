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
import asyncio

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
        
        # 🔒 CRITICAL: Per-symbol locks to prevent race conditions
        self._sl_locks: Dict[str, asyncio.Lock] = {}
        self._sl_locks_lock = asyncio.Lock()  # Meta-lock for safe lock creation

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
        # 🔒 CRITICAL: Acquire symbol-specific lock to prevent race conditions
        async with self._sl_locks_lock:
            if symbol not in self._sl_locks:
                self._sl_locks[symbol] = asyncio.Lock()
            symbol_lock = self._sl_locks[symbol]
        
        async with symbol_lock:
            self.logger.info(f"🔒 [StopLossManager] Acquired lock for {symbol}")
            
            try:
                # ШАГ 1: Проверить что SL еще не установлен
                has_sl, existing_sl = await self.has_stop_loss(symbol)

                if has_sl:
                    self.logger.info(
                        f"⚠️ Stop Loss already exists at {existing_sl}, skipping"
                    )
                    self.logger.debug(f"🔓 [StopLossManager] Released lock for {symbol} (already exists)")
                    return {
                        'status': 'already_exists',
                        'stopPrice': existing_sl,
                        'reason': 'Stop Loss already set'
                    }

                # ШАГ 2: Установка через ExchangeManager
                # Используем проверенную логику из core/exchange_manager.py
                if self.exchange_name == 'bybit':
                    result = await self._set_bybit_stop_loss(symbol, stop_price)
                else:
                    result = await self._set_generic_stop_loss(symbol, side, amount, stop_price)
                
                self.logger.debug(f"🔓 [StopLossManager] Released lock for {symbol} (created)")
                return result

            except Exception as e:
                self.logger.error(f"Failed to set Stop Loss for {symbol}: {e}")
                self.logger.debug(f"🔓 [StopLossManager] Released lock for {symbol} (error)")
                raise

    async def _set_bybit_stop_loss(self, symbol: str, stop_price: float) -> Dict:
        """
        Установка Stop Loss для Bybit через position-attached method.

        Источник: core/exchange_manager.py:create_stop_loss_order (Bybit секция)
        """
        try:
            # CRITICAL FIX: Convert DB format (BTCUSDT) to CCXT format (BTC/USDT:USDT)
            # Symbol from DB is in format 'BTCUSDT', but CCXT expects 'BTC/USDT:USDT'
            ccxt_symbol = symbol
            if '/' not in symbol:  # Database format
                # Convert BTCUSDT -> BTC/USDT:USDT for Bybit
                if symbol.endswith('USDT'):
                    base = symbol[:-4]  # Remove 'USDT'
                    ccxt_symbol = f"{base}/USDT:USDT"

            # ШАГ 1: Получить позицию для positionIdx
            positions = await self.exchange.fetch_positions(
                symbols=[ccxt_symbol],
                params={'category': 'linear'}
            )

            position_idx = 0
            position_found = False

            for pos in positions:
                if pos['symbol'] == ccxt_symbol and float(pos.get('contracts', 0)) > 0:
                    position_idx = int(pos.get('info', {}).get('positionIdx', 0))
                    position_found = True
                    break

            if not position_found:
                raise ValueError(f"No open position found for {symbol} (checked as {ccxt_symbol})")

            # ШАГ 2: Форматирование для Bybit API
            bybit_symbol = ccxt_symbol.replace('/', '').replace(':USDT', '')
            sl_price_formatted = self.exchange.price_to_precision(ccxt_symbol, stop_price)

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

            # CRITICAL FIX: Convert retCode to int for comparison
            if isinstance(ret_code, str):
                ret_code = int(ret_code)

            self.logger.debug(f"Bybit API response: retCode={ret_code} (type={type(ret_code)}), retMsg={ret_msg}")

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
        """
        try:
            # Используем стандартный CCXT метод
            order = await self.exchange.create_order(
                symbol=symbol,
                type='stop_market',
                side=side,
                amount=amount,
                price=None,  # Market order при срабатывании
                params={
                    'stopPrice': stop_price,
                    'reduceOnly': True
                }
            )

            self.logger.info(f"✅ Stop Loss order created: {order['id']}")

            return {
                'status': 'created',
                'stopPrice': stop_price,
                'orderId': order['id'],
                'info': order
            }

        except Exception as e:
            self.logger.error(f"Failed to create stop order: {e}")
            raise

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