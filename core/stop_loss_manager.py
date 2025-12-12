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
import asyncio
import ccxt
from core.event_logger import get_event_logger, EventType

logger = logging.getLogger(__name__)


class StopLossManager:
    """
    Централизованный менеджер Stop Loss операций.

    🎯 ЕДИНСТВЕННЫЙ источник истины для всех SL операций в системе.

    Основан на ПРОВЕРЕННОЙ логике из core/position_manager.py:1324
    """

    def __init__(self, exchange, exchange_name: str, position_manager=None):
        """
        Args:
            exchange: CCXT exchange instance
            exchange_name: Exchange name ('bybit', 'binance', etc.)
            position_manager: Optional PositionManager instance for TS detection
                             Required for TS-awareness. If None, TS detection disabled.
        """
        self.exchange = exchange
        self.exchange_name = exchange_name.lower()
        self.position_manager = position_manager  # NEW
        self.logger = logger

    async def has_stop_loss(self, symbol: str, position_side: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        ЕДИНСТВЕННАЯ функция проверки наличия Stop Loss.

        Args:
            symbol: CCXT unified symbol (e.g., 'BTC/USDT:USDT')
            position_side: Optional position side ('long' or 'short') for validation
                          If None, accepts any side (backward compatibility)

        Returns:
            Tuple[bool, Optional[str], Optional[str]]: (has_sl, sl_price, algo_id)

        Проверяет в следующем порядке:
        1. Binance: Algo orders ONLY (December 2025 migration)
        2. Bybit: Position-attached SL (через position.info.stopLoss)
        3. Others: Conditional stop orders (через fetch_open_orders)
        """
        try:
            self.logger.debug(f"Checking Stop Loss for {symbol} on {self.exchange_name}")

            # ============================================================
            # BINANCE: Check Algo orders ONLY (December 2025)
            # ============================================================
            if self.exchange_name == 'binance':
                try:
                    # Format symbol for Binance (remove slash and :USDT)
                    binance_symbol = symbol.replace('/', '').replace(':USDT', '')
                    
                    self.logger.debug(f"Checking Algo orders for {binance_symbol}")
                    
                    # Fetch Algo orders
                    algo_orders = await self.exchange.fapiPrivateGetOpenAlgoOrders({
                        'symbol': binance_symbol
                    })
                    
                    self.logger.debug(f"Found {len(algo_orders)} algo orders for {binance_symbol}")
                    
                    # Check for CONDITIONAL algo orders (Stop Loss)
                    for algo_order in algo_orders:
                        algo_type = algo_order.get('algoType')
                        algo_status = algo_order.get('algoStatus')
                        
                        # Only check active CONDITIONAL orders
                        if algo_type == 'CONDITIONAL' and algo_status in ['NEW', 'WORKING']:
                            # Validate order side matches position side (if provided)
                            if position_side:
                                order_side = algo_order.get('side', '').lower()
                                expected_side = 'sell' if position_side == 'long' else 'buy'
                                
                                if order_side != expected_side:
                                    self.logger.debug(
                                        f"Skip Algo order {algo_order.get('algoId')}: "
                                        f"wrong side ({order_side} vs {expected_side})"
                                    )
                                    continue  # Skip this order - wrong side
                            
                            # Found matching Algo SL
                            trigger_price = algo_order.get('triggerPrice')
                            algo_id = str(algo_order.get('algoId'))
                            
                            self.logger.info(
                                f"✅ {symbol} has Algo SL: algoId={algo_id} at {trigger_price}"
                            )
                            return True, trigger_price, algo_id
                    
                    # No Algo SL found
                    self.logger.debug(f"No Algo SL found for {symbol}")
                    return False, None, None
                    
                except Exception as e:
                    self.logger.error(f"Error checking Algo orders for {symbol}: {e}")
                    return False, None, None

            # ============================================================
            # ПРИОРИТЕТ 1: Position-attached Stop Loss (для Bybit)
            # ============================================================
            elif self.exchange_name == 'bybit':
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
                                return True, stop_loss, None
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
                        # NEW: Validate order side matches position side
                        if position_side:
                            order_side = order.get('side', '').lower()
                            expected_side = 'sell' if position_side == 'long' else 'buy'

                            if order_side != expected_side:
                                self.logger.debug(
                                    f"Skip SL order {order.get('id')}: wrong side "
                                    f"({order_side} for {position_side} position)"
                                )
                                continue  # Skip this order - wrong side

                        sl_price = self._extract_stop_price(order)
                        order_id = str(order.get('id'))
                        self.logger.info(
                            f"✅ Position {symbol} has Stop Loss order: {order_id} "
                            f"at {sl_price}"
                        )
                        return True, str(sl_price) if sl_price else None, order_id

            except Exception as e:
                self.logger.debug(f"Could not check stop orders for {symbol}: {e}")

            # Нет Stop Loss
            self.logger.debug(f"No Stop Loss found for {symbol}")
            return False, None, None

        except Exception as e:
            self.logger.error(f"Error checking Stop Loss for {symbol}: {e}")
            # В случае ошибки безопаснее вернуть False
            return False, None, None

    async def set_stop_loss(
        self,
        symbol: str,
        side: str,
        amount: Decimal,
        stop_price: Decimal,
        operation_id: Optional[str] = None,
        created_in_operation: Optional[str] = None
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
            has_sl, existing_sl, existing_algo_id = await self.has_stop_loss(symbol)

            # ✅ FIX #1.3: Check if TS is active before validating/cancelling
            ts_active = await self._is_trailing_stop_active(symbol)
            if ts_active:
                self.logger.info(
                    f"✅ {symbol}: TS active, skipping SL recreation to prevent TS cancellation"
                )
                return {
                    'status': 'ts_active',
                    'stopPrice': existing_sl,
                    'reason': 'Trailing Stop active, SL management deferred to TS'
                }

            if has_sl:
            # NEW FIX (Dec 11, 2025): Check if this SL was created in CURRENT operation
            # This prevents retry loop from detecting own SL as "existing from previous position"
                if created_in_operation and existing_algo_id and str(existing_algo_id) == str(created_in_operation):
                    self.logger.info(
                        f"✅ {symbol}: SL already created in THIS operation "
                        f"(algoId={created_in_operation}), reusing"
                    )
                    return {
                        'status': 'already_exists',
                        'algoId': created_in_operation,
                        'stopPrice': existing_sl
                    }
            
                # CRITICAL FIX: Validate existing SL before reusing
                # This prevents reusing old SL from previous positions with different entry prices
                from utils.decimal_utils import to_decimal
                is_valid, reason = self._validate_existing_sl(
                    existing_sl_price=to_decimal(existing_sl),
                    target_sl_price=stop_price,
                    side=side,
                    tolerance_percent=Decimal("5.0")
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
                    await self._cancel_existing_sl(symbol, to_decimal(existing_sl))

                    # Fall through to create new SL below

            # ШАГ 2: Установка через ExchangeManager
            # Используем проверенную логику из core/exchange_manager.py
            if self.exchange_name == 'bybit':
                return await self._set_bybit_stop_loss(symbol, stop_price)
            else:
                # DECEMBER 2025 MIGRATION: ALL Binance symbols now use Algo API
                # Old standard API returns error -4120 for all conditional orders
                # No need for fallback - directly use new Algo Order endpoint
                return await self._set_binance_stop_loss_algo(symbol, side, amount, stop_price)

        except Exception as e:
            self.logger.error(f"Failed to set Stop Loss for {symbol}: {e}")
            raise

    async def verify_and_fix_missing_sl(
        self,
        position,
        stop_price: Decimal,
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
                    from utils.decimal_utils import to_decimal
                    result = await self.set_stop_loss(
                        symbol=symbol,
                        side=order_side,
                        amount=to_decimal(position.quantity),
                        stop_price=stop_price
                    )

                    if result.get('status') == 'success':
                    # DECEMBER 2025: Algo API returns algoId and triggerPrice
                        algo_id = result.get('algoId')
                        trigger_price = result.get('triggerPrice', stop_price)
                        
                        self.logger.info(
                            f"✅ SL recreated for {symbol} at {trigger_price} "
                            f"(attempt {attempt + 1}/{max_retries}), algoId={algo_id}"
                        )
                        return True, str(algo_id) if algo_id else None

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

    async def _set_bybit_stop_loss(self, symbol: str, stop_price: Decimal) -> Dict:
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



    async def _set_binance_stop_loss_algo(
        self,
        symbol: str,
        side: str,
        amount: Decimal,
        stop_price: Decimal
    ) -> Dict:
        """
        Place stop-loss using NEW Binance Algo Order API (December 2025 migration).
        
        IMPORTANT: As of December 9, 2025, ALL conditional orders (STOP_MARKET, etc.)
        have been migrated to the Algo Service. The old /fapi/v1/order endpoint
        now returns error -4120 for these order types.
        
        New API Endpoint: POST /fapi/v1/algoOrder
        Documentation: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order
        
        Args:
            symbol: CCXT unified symbol (e.g., 'BTC/USDT:USDT')
            side: 'sell' for long, 'buy' for short
            amount: Position size
            stop_price: Stop loss trigger price
            
        Returns:
            Dict with algo order information including algoId
        """
        from decimal import Decimal
        
        # Format symbol (remove slash and :USDT suffix for Binance)
        binance_symbol = symbol.replace('/', '').replace(':USDT', '')
        
        # Format price with exchange precision
        final_stop_price = float(stop_price)
        final_stop_price = self.exchange.price_to_precision(symbol, final_stop_price)
        
        # CRITICAL: CCXT price_to_precision() uses symbol-specific precision from market data
        # - For JELLYJELLYUSDT: tickSize might be 0.00000001 (8 decimals)
        # - For BTCUSDT: tickSize might be 0.1 (1 decimal)
        # - Precision is NOT fixed - it varies by symbol!
        # 
        # CCXT reads this from exchangeInfo endpoint:
        # - PRICE_FILTER.tickSize for price precision
        # - LOT_SIZE.stepSize for amount precision
        #
        # DO NOT override with fixed decimal limit - trust CCXT!
        
        # Prepare Algo API parameters (NEW format for December 2025 migration)
        params = {
            'algoType': 'CONDITIONAL',  # Required for conditional orders
            'symbol': binance_symbol,
            'side': side.upper(),  # BUY or SELL
            'type': 'STOP_MARKET',  # Order type within algo
            'triggerPrice': str(final_stop_price),  # ← CCXT precision applied
            'quantity': str(float(amount)),  # ← Will be validated by exchange
            'reduceOnly': 'true',  # String, not boolean
            'workingType': 'CONTRACT_PRICE',  # Trigger based on contract price
            'priceProtect': 'FALSE',  # String, not boolean

            'timeInForce': 'GTC',  # Good Till Cancel
            'timestamp': self.exchange.milliseconds()  # Required
        }
        
        self.logger.info(
            f"📊 Creating Algo SL (NEW API) for {symbol}: trigger={final_stop_price}, "
            f"side={side}, qty={amount}"
        )
        
        try:
            # CRITICAL: Use NEW Algo Order endpoint (December 2025 migration)
            # Method: fapiPrivatePostAlgoOrder (verified in CCXT 4.5.26)
            response = await self.exchange.fapiPrivatePostAlgoOrder(params)
            
            # Extract algoId from response
            algo_id = response.get('algoId')
            
            if not algo_id:
                raise Exception(f"Algo API returned no algoId: {response}")
            
            self.logger.info(f"✅ Algo Stop Loss created: algoId={algo_id}")
            
            # PERFORMANCE OPTIMIZATION (December 10, 2025):
            # Removed verification sleep(2) + API call
            # - Saves ~2500ms per SL creation
            # - API response is reliable, no immediate verification needed
            # - Protection manager verifies SL in 60s monitoring loop
            # - If SL missing, it will be recreated automatically
            
            # Log event
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.STOP_LOSS_PLACED,
                    {
                        'symbol': symbol,
                        'exchange': self.exchange_name,
                        'trigger_price': float(final_stop_price),
                        'algo_id': algo_id,
                        'method': 'algo_conditional',
                        'side': side,
                        'api_version': 'v2_dec2025'
                    },
                    symbol=symbol,
                    exchange=self.exchange_name,
                    severity='INFO'
                )
            
            return {
                'status': 'success',
                'triggerPrice': float(final_stop_price),
                'algoId': algo_id,
                'method': 'algo_conditional',
                'info': response
            }
            
        except Exception as e:
            self.logger.error(f"Failed to create Algo SL for {symbol}: {e}")
            
            # Log error event
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.STOP_LOSS_ERROR,
                    {
                        'symbol': symbol,
                        'exchange': self.exchange_name,
                        'trigger_price': float(stop_price),
                        'error': str(e),
                        'method': 'algo_conditional'
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
        amount: Decimal,
        stop_price: Decimal
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
        stop_price_decimal = stop_price

        for attempt in range(max_retries):
            try:
                # STEP 1: Get current market price
                ticker = await self.exchange.fetch_ticker(symbol)

                # Use mark price for Binance Futures (critical for accuracy)
                from utils.decimal_utils import to_decimal
                if self.exchange_name == 'binance':
                    current_price = to_decimal(
                        ticker.get('info', {}).get('markPrice', ticker['last'])
                    )
                else:
                    current_price = to_decimal(ticker['last'])

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
                # CRITICAL VALIDATION: Build params with enforced reduceOnly
                params = {
                    'stopPrice': final_stop_price,
                    'reduceOnly': True  # ALWAYS True for futures SL
                }

                # Log for audit
                if self.exchange_name in ['binance', 'bybit']:
                    self.logger.info(f"✅ reduceOnly validated: {params.get('reduceOnly')} for {symbol}")

                order = await self.exchange.create_order(
                    symbol=symbol,
                    type='stop_market',
                    side=side,
                    amount=amount,
                    price=None,  # Market order при срабатывании
                    params=params
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
                        # Phase 3: Use config safety margin instead of hardcoded 0.995/1.005
                        from config.settings import config as global_config
                        safety_margin = global_config.safety.STOP_LOSS_SAFETY_MARGIN_PERCENT / Decimal('100')

                        if side == 'sell':
                            stop_price_decimal *= (Decimal('1') - safety_margin)  # 0.5% lower
                        else:
                            stop_price_decimal *= (Decimal('1') + safety_margin)  # 0.5% higher
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
            # DECEMBER 2025: For Binance Algo orders, triggerPrice is at top level
            if self.exchange_name == 'binance':
                trigger_price = order.get('triggerPrice')
                if trigger_price and trigger_price not in ['0', '0.00', '', None]:
                    return float(trigger_price)
            
            # For other exchanges: check various fields
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
        existing_sl_price: Decimal,
        target_sl_price: Decimal,
        side: str,
        tolerance_percent: Decimal = Decimal("5.0")
    ) -> tuple:
        """
        CRITICAL FIX: Validate if existing SL is acceptable for current position

        This prevents reusing old SL from previous positions that may have:
        - Wrong price (different entry price)
        - Wrong direction (opposite position type)

        For LONG:
            - SL should be BELOW entry (sell at lower price)
            - existing_sl >= target_sl = BAD (too close to entry)
            - existing_sl < target_sl = GOOD (further from entry)

        For SHORT:
            - SL should be ABOVE entry (buy at higher price)
            - existing_sl <= target_sl = BAD (too close to entry)
            - existing_sl > target_sl = GOOD (further from entry)

        Args:
            existing_sl_price: Price of existing SL on exchange
            target_sl_price: Desired SL price for new position
            side: 'sell' for LONG position, 'buy' for SHORT position
            tolerance_percent: Allow X% price difference (default: 5%)

        Returns:
            tuple: (is_valid: bool, reason: str)
        """
        # Calculate difference percentage
        diff_pct = abs(existing_sl_price - target_sl_price) / target_sl_price * Decimal("100")

        # Determine position side from order side
        # side='sell' means closing LONG position
        # side='buy' means closing SHORT position
        position_is_long = (side.lower() == 'sell')

        if position_is_long:
            # LONG position: SL should be BELOW entry (lower price)
            # Lower SL = better protection (further from entry)
            # Higher SL = worse protection (closer to entry)

            if existing_sl_price <= target_sl_price:
                # Existing SL is equal or better (lower = more conservative)
                if diff_pct <= tolerance_percent:
                    return True, f"Existing SL acceptable (within {tolerance_percent}%)"
                else:
                    # Too far below - likely from old position at lower entry price
                    return False, (
                        f"Existing SL is from old position (too low): {existing_sl_price} vs "
                        f"target {target_sl_price} (diff: {diff_pct:.2f}%)"
                    )
            else:
                # Existing SL is higher than target = worse protection (closer to entry)
                return False, (
                    f"Existing SL too close to entry: {existing_sl_price} vs "
                    f"target {target_sl_price} ({diff_pct:.2f}% difference)"
                )

        else:
            # SHORT position: SL should be ABOVE entry (higher price)
            # Higher SL = better protection (further from entry)
            # Lower SL = worse protection (closer to entry)

            if existing_sl_price >= target_sl_price:
                # Existing SL is equal or better (higher = more conservative)
                if diff_pct <= tolerance_percent:
                    return True, f"Existing SL acceptable (within {tolerance_percent}%)"
                else:
                    # Too far above - likely from old position at higher entry price
                    return False, (
                        f"Existing SL is from old position (too high): {existing_sl_price} vs "
                        f"target {target_sl_price} (diff: {diff_pct:.2f}%)"
                    )
            else:
                # Existing SL is lower than target = worse protection (closer to entry)
                return False, (
                    f"Existing SL too close to entry: {existing_sl_price} vs "
                    f"target {target_sl_price} ({diff_pct:.2f}% difference)"
                )

    async def _cancel_existing_sl(self, symbol: str, sl_price: Decimal):
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
                        from utils.decimal_utils import to_decimal
                        price_diff = abs(to_decimal(order_stop_price) - sl_price) / sl_price

                        if price_diff < 0.01:  # Within 1%
                            self.logger.info(f"Cancelling old SL order {order['id']} at {order_stop_price}")
                            await self.exchange.cancel_order(order['id'], symbol)
                            return

            self.logger.warning(f"No matching SL order found to cancel (price: {sl_price})")

        except Exception as e:
            self.logger.error(f"Error cancelling SL: {e}")
            raise

    async def _is_trailing_stop_active(self, symbol: str) -> bool:
        """
        Check if Trailing Stop is currently active for this symbol.

        This prevents stop_loss_manager from cancelling TS orders that may
        appear "invalid" when compared to permanent SL targets.

        Args:
            symbol: Trading symbol (CCXT unified format)

        Returns:
            bool: True if TS is active and managing this position's SL

        Detection logic:
            1. Check trailing_manager.trailing_stops dict (authoritative source)
            2. Fallback: Check position flags if trailing_manager not available
            3. Return False if position_manager not provided (conservative)

        Why this matters:
            TS orders have HIGHER stop prices than permanent SL (more aggressive).
            Without this check, stop_loss_manager thinks TS is "too close to entry"
            and cancels it, leaving position with only permanent SL protection.
        """
        # GUARD: If no position_manager provided, can't detect TS
        if not self.position_manager:
            self.logger.debug(
                f"TS detection disabled for {symbol}: no position_manager provided"
            )
            return False

        try:
            # METHOD 1: Check trailing_manager (AUTHORITATIVE)
            # trailing_managers is a dict: {exchange_name: SmartTrailingStopManager}
            trailing_manager = self.position_manager.trailing_managers.get(
                self.exchange_name
            )

            if trailing_manager:
                # Check if symbol in trailing_stops dict AND state is ACTIVE
                # trailing_stops is dict: {symbol: TrailingStopInstance}
                ts_instance = trailing_manager.trailing_stops.get(symbol)

                if ts_instance:
                    # Import TrailingStopState for comparison
                    from protection.trailing_stop import TrailingStopState

                    # Only consider TS active if state is ACTIVE
                    # States: INACTIVE, WAITING, ACTIVE, TRIGGERED
                    if ts_instance.state == TrailingStopState.ACTIVE:
                        self.logger.info(
                            f"✅ {symbol}: TS active in trailing_manager "
                            f"(state={ts_instance.state.value}, "
                            f"stop={ts_instance.current_stop_price})"
                        )
                        return True
                    else:
                        self.logger.debug(
                            f"{symbol}: TS exists but not active "
                            f"(state={ts_instance.state.value})"
                        )
                        return False

            # METHOD 2: Fallback - check position flags
            # This is less reliable but better than nothing
            position = self.position_manager.positions.get(symbol)

            if position:
                # Check both flags: has_trailing_stop AND trailing_activated
                if position.has_trailing_stop and position.trailing_activated:
                    self.logger.info(
                        f"✅ {symbol}: TS active (via position flags)"
                    )
                    return True
                else:
                    self.logger.debug(
                        f"{symbol}: TS not active "
                        f"(has_ts={position.has_trailing_stop}, "
                        f"activated={position.trailing_activated})"
                    )

            # No TS detected
            return False

        except Exception as e:
            # CRITICAL: Log error but return False (conservative)
            # Better to risk recreating SL than leaving position unprotected
            self.logger.error(
                f"Error detecting TS for {symbol}: {e}. "
                f"Assuming TS not active (conservative)"
            )
            return False


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
    amount: Decimal,
    stop_price: Decimal
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