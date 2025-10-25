"""
Atomic Position Manager - гарантирует атомарность создания позиций со stop-loss

CRITICAL: Этот модуль обеспечивает атомарность операций Entry+SL
Все позиции ДОЛЖНЫ иметь stop-loss или быть немедленно закрыты

⚠️ DO NOT MODIFY без полного понимания последствий!
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from enum import Enum
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from utils.datetime_helpers import now_utc, ensure_utc
from decimal import Decimal
import uuid
from database.transactional_repository import TransactionalRepository
from core.event_logger import EventLogger, EventType, log_event
from core.exchange_response_adapter import ExchangeResponseAdapter

logger = logging.getLogger(__name__)


def truncate_exit_reason(reason: str, max_length: int = 450) -> str:
    """
    Безопасное усечение exit_reason до максимальной длины

    Args:
        reason: Причина выхода/ошибки
        max_length: Максимальная длина (default: 450 для varchar(500) с запасом)

    Returns:
        Усечённая строка с индикатором усечения если необходимо
    """
    if len(reason) <= max_length:
        return reason

    # Усекаем с добавлением индикатора
    truncate_marker = "...[truncated]"
    available_length = max_length - len(truncate_marker)
    return reason[:available_length] + truncate_marker


class PositionState(Enum):
    """
    Состояния позиции для обеспечения атомарности

    Flow: PENDING_ENTRY -> ENTRY_PLACED -> PENDING_SL -> ACTIVE
    При любой ошибке: -> FAILED или ROLLED_BACK
    """
    PENDING_ENTRY = "pending_entry"  # Подготовка к размещению entry
    ENTRY_PLACED = "entry_placed"    # Entry размещен, ожидание SL
    PENDING_SL = "pending_sl"        # Размещение SL
    ACTIVE = "active"                # Позиция активна с защитой
    FAILED = "failed"                # Не удалось создать
    ROLLED_BACK = "rolled_back"      # Откачена из-за ошибки SL


class AtomicPositionError(Exception):
    """Исключение при нарушении атомарности"""
    pass


class SymbolUnavailableError(Exception):
    """Исключение когда символ недоступен для торговли (делистинг, только закрытие и т.д.)"""
    pass


class MinimumOrderLimitError(Exception):
    """Исключение когда количество контрактов не соответствует минимальным требованиям биржи"""
    pass


class AtomicPositionManager:
    """
    Менеджер атомарного создания позиций

    Гарантирует:
    1. Позиция ВСЕГДА создается со stop-loss
    2. При ошибке SL позиция откатывается
    3. Recovery для незавершенных операций
    """

    def __init__(self, repository, exchange_manager, stop_loss_manager, position_manager=None, config=None):
        self.repository = repository
        self.exchange_manager = exchange_manager
        self.stop_loss_manager = stop_loss_manager
        self.position_manager = position_manager  # NEW
        self.config = config  # RESTORED 2025-10-25: for leverage control
        self.active_operations = {}  # Track ongoing operations

    @asynccontextmanager
    async def atomic_operation(self, operation_id: str):
        """
        Контекстный менеджер для атомарных операций

        Обеспечивает:
        - Отслеживание операции
        - Автоматический rollback при ошибках
        - Логирование всех этапов
        """
        self.active_operations[operation_id] = {
            'started_at': datetime.utcnow(),  # FIX: Use offset-naive datetime for consistency
            'status': 'in_progress'
        }

        try:
            logger.info(f"🔄 Starting atomic operation: {operation_id}")
            yield operation_id

            self.active_operations[operation_id]['status'] = 'completed'
            logger.info(f"✅ Atomic operation completed: {operation_id}")

        except Exception as e:
            logger.error(f"❌ Atomic operation failed: {operation_id} - {e}")
            self.active_operations[operation_id]['status'] = 'failed'
            self.active_operations[operation_id]['error'] = str(e)

            # Rollback will be handled by caller
            raise

        finally:
            # Cleanup after delay
            asyncio.create_task(self._cleanup_operation_record(operation_id))

    async def _cleanup_operation_record(self, operation_id: str):
        """Cleanup operation record after 5 minutes"""
        await asyncio.sleep(300)
        if operation_id in self.active_operations:
            del self.active_operations[operation_id]

    async def _safe_activate_position(
        self,
        position_id: int,
        symbol: str,
        exchange: str,
        **update_fields
    ) -> bool:
        """
        Safely activate position with duplicate detection (Layer 3 defense).

        This is a defensive safety net that checks for duplicate active positions
        before updating status to 'active'. If a duplicate is detected, the position
        is rolled back instead of causing a duplicate key violation.

        Added as part of duplicate position race condition fix (2025-10-23).
        See docs/audit_duplicate_position/ for full analysis.

        Args:
            position_id: ID of position to activate
            symbol: Trading symbol
            exchange: Exchange name
            **update_fields: Additional fields to update (stop_loss_price, etc.)

        Returns:
            True if activated successfully
            False if duplicate detected (caller should rollback)
        """
        try:
            # Defensive check: is there already an active position?
            async with self.repository.pool.acquire() as conn:
                existing_active = await conn.fetchrow("""
                    SELECT id, created_at FROM monitoring.positions
                    WHERE symbol = $1 AND exchange = $2
                      AND status = 'active'
                      AND id != $3
                """, symbol, exchange, position_id)

                if existing_active:
                    logger.error(
                        f"🔴 DUPLICATE ACTIVE POSITION DETECTED!\n"
                        f"   Cannot activate position #{position_id} ({symbol} on {exchange}).\n"
                        f"   Position #{existing_active['id']} is already active "
                        f"(created {existing_active['created_at']}).\n"
                        f"   This indicates a race condition occurred despite Layer 1&2 defenses.\n"
                        f"   Position #{position_id} will NOT be updated to prevent duplicate key error."
                    )
                    return False

            # Safe to activate - no duplicate detected
            update_fields['status'] = PositionState.ACTIVE.value
            await self.repository.update_position(position_id, **update_fields)

            logger.info(f"✅ Position #{position_id} successfully activated")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to activate position #{position_id}: {e}")
            return False

    async def open_position_atomic(
        self,
        signal_id: int,
        symbol: str,
        exchange: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_loss_percent: float  # FIX: Changed from stop_loss_price to stop_loss_percent
    ) -> Optional[Dict[str, Any]]:
        """
        Атомарное создание позиции с гарантированным stop-loss

        Args:
            signal_id: ID сигнала
            symbol: Торговый символ
            exchange: Название биржи
            side: 'buy' или 'sell'
            quantity: Размер позиции
            entry_price: Цена входа (сигнальная, может отличаться от execution)
            stop_loss_percent: Процент stop-loss (будет пересчитан от execution price)

        Returns:
            Dict с информацией о позиции или None при ошибке

        Raises:
            AtomicPositionError: При нарушении атомарности
        """
        operation_id = f"pos_{symbol}_{now_utc().timestamp()}"

        position_id = None
        entry_order = None
        sl_order = None
        state = PositionState.PENDING_ENTRY

        async with self.atomic_operation(operation_id):
            try:
                # Step 1: Создание записи позиции в состоянии PENDING_ENTRY
                logger.info(f"📝 Creating position record for {symbol}")
                position_data = {
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': 'long' if side.lower() == 'buy' else 'short',
                    'quantity': quantity,
                    'entry_price': entry_price
                }

                position_id = await self.repository.create_position(position_data)
                logger.info(f"✅ Position record created: ID={position_id}")

                # Step 2: Размещение entry ордера
                logger.info(f"📊 Placing entry order for {symbol}")
                state = PositionState.ENTRY_PLACED

                # FIX: exchange_manager is a dict, not an object with get_exchange method
                exchange_instance = self.exchange_manager.get(exchange)
                if not exchange_instance:
                    raise AtomicPositionError(f"Exchange {exchange} not available")

                # RESTORED 2025-10-25: Set leverage before opening position
                if self.config and self.config.auto_set_leverage:
                    leverage = self.config.leverage
                    logger.info(f"🎚️ Setting {leverage}x leverage for {symbol}")
                    leverage_set = await exchange_instance.set_leverage(symbol, leverage)
                    if not leverage_set:
                        logger.warning(
                            f"⚠️ Could not set leverage for {symbol}, "
                            f"using exchange default"
                        )
                        # Continue anyway - leverage might already be set correctly

                # Prepare params for exchange-specific requirements
                params = {}
                if exchange == 'bybit':
                    params['positionIdx'] = 0  # One-way mode (required by Bybit V5 API)
                elif exchange == 'binance':
                    # CRITICAL FIX: Request FULL response to get avgPrice and fills
                    # Default newOrderRespType=ACK returns avgPrice="0.00000"
                    # NOTE: FULL returns immediately with status='NEW', executedQty='0'
                    # We fetch order afterwards to get actual filled status and avgPrice
                    params['newOrderRespType'] = 'FULL'
                    logger.debug(f"Setting newOrderRespType=FULL for Binance market order")

                raw_order = await exchange_instance.create_market_order(
                    symbol, side, quantity, params=params if params else None
                )

                # Pre-register position for WebSocket updates (fix race condition)
                if hasattr(self, 'position_manager') and self.position_manager:
                    await self.position_manager.pre_register_position(symbol, exchange)
                    logger.info(f"✅ Pre-registered {symbol} for immediate WebSocket tracking")

                # Check if order was created
                if raw_order is None:
                    raise AtomicPositionError(f"Failed to create order for {symbol}: order returned None")

                # FIX: Check Bybit retCode IMMEDIATELY to catch errors before SL attempt
                # Bybit returns retCode != 0 for all errors (e.g., 10001 = minimum size)
                if exchange == 'bybit' and raw_order:
                    order_info = raw_order.info
                    ret_code = order_info.get('retCode', 0)

                    if ret_code != 0:
                        ret_msg = order_info.get('retMsg', 'Unknown error')

                        # Minimum size error (retCode 10001)
                        if ret_code == 10001 or 'minimum limit' in ret_msg.lower():
                            logger.warning(f"⚠️ Order size for {symbol} doesn't meet exchange requirements: {ret_msg}")
                            raise MinimumOrderLimitError(f"Order size for {symbol} below minimum limit on {exchange}: {ret_msg}")

                        # Other Bybit errors
                        logger.error(f"❌ Bybit order failed for {symbol}: retCode={ret_code}, {ret_msg}")
                        raise AtomicPositionError(f"Bybit order creation failed: {ret_msg}")

                # CRITICAL FIX: For Binance with FULL response type,
                # market orders return status='NEW' immediately before execution.
                # Fetch order to get actual filled status and avgPrice.
                if exchange == 'binance' and raw_order and raw_order.id:
                    order_id = raw_order.id
                    try:
                        # Brief wait for market order to execute
                        await asyncio.sleep(0.1)

                        # Fetch actual order status
                        fetched_order = await exchange_instance.fetch_order(order_id, symbol)

                        if fetched_order:
                            logger.info(
                                f"✅ Fetched Binance order status: "
                                f"id={order_id}, status={fetched_order.status}, "
                                f"filled={fetched_order.filled}/{fetched_order.amount}, "
                                f"avgPrice={fetched_order.price}"
                            )

                            # Use fetched order data (has correct status and avgPrice)
                            raw_order = fetched_order
                        else:
                            logger.warning(f"⚠️ Fetch order returned None for {order_id}")

                    except Exception as e:
                        logger.warning(
                            f"⚠️ Failed to fetch order {order_id} status, "
                            f"using create response: {e}"
                        )
                        # Fallback: use original create_order response

                # Normalize order response
                entry_order = ExchangeResponseAdapter.normalize_order(raw_order, exchange)

                # Check if normalization succeeded
                if entry_order is None:
                    raise AtomicPositionError(f"Failed to normalize order for {symbol}")

                if not ExchangeResponseAdapter.is_order_filled(entry_order):
                    raise AtomicPositionError(f"Entry order failed: {entry_order.status}")

                logger.info(f"✅ Entry order placed: {entry_order.id}")

                # Update position with entry details
                # Extract execution price from normalized order
                exec_price = ExchangeResponseAdapter.extract_execution_price(entry_order)

                # DIAGNOSTIC: Log price comparison for monitoring
                if exec_price and exec_price > 0:
                    diff_pct = ((exec_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                    logger.info(
                        f"💰 Entry Price - Signal: ${entry_price:.8f}, "
                        f"Execution: ${exec_price:.8f}, "
                        f"Diff: {diff_pct:.4f}%"
                    )
                else:
                    logger.info(
                        f"💰 Entry Price - Signal: ${entry_price:.8f}, "
                        f"Execution: N/A (will use fallback)"
                    )

                # FIX: Bybit API v5 does not return avgPrice in create_order response
                # Use fetch_positions to get actual execution price (fetch_order has 500 limit)
                if exchange == 'bybit' and (not exec_price or exec_price == 0):
                    logger.info(f"📊 Fetching position for {symbol} to get execution price")
                    try:
                        # Use fetch_positions instead of fetch_order (Bybit V5 best practice)
                        positions = await exchange_instance.fetch_positions(
                            symbols=[symbol],
                            params={'category': 'linear'}
                        )

                        # Find our position
                        for pos in positions:
                            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                                exec_price = float(pos.get('entryPrice', 0))
                                if exec_price > 0:
                                    logger.info(f"✅ Got execution price from position: {exec_price}")
                                    break

                        if not exec_price or exec_price == 0:
                            # Fallback to signal entry price if position not found
                            logger.warning(f"⚠️ Could not get execution price from position, using signal price")
                            exec_price = entry_price

                    except Exception as e:
                        logger.error(f"❌ Failed to fetch position for execution price: {e}")
                        # Fallback: use signal entry price
                        exec_price = entry_price

                # BINANCE FALLBACK: If avgPrice still 0, fetch position for execution price
                elif exchange == 'binance' and (not exec_price or exec_price == 0):
                    logger.info(f"📊 Binance: avgPrice not in response, fetching position for {symbol}")
                    try:
                        # Small delay to ensure position is updated on exchange
                        await asyncio.sleep(1.0)

                        # Fetch positions to get actual entry price
                        positions = await exchange_instance.fetch_positions([symbol])

                        # Find our position
                        for pos in positions:
                            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                                exec_price = float(pos.get('entryPrice', 0))
                                if exec_price > 0:
                                    logger.info(f"✅ Got execution price from Binance position: ${exec_price:.8f}")
                                    break

                        # If still no execution price, use signal price as fallback
                        if not exec_price or exec_price == 0:
                            logger.warning(
                                f"⚠️ Could not get execution price from Binance position for {symbol}, "
                                f"using signal price: ${entry_price:.8f}"
                            )
                            exec_price = entry_price

                    except Exception as e:
                        logger.error(f"❌ Failed to fetch Binance position for execution price: {e}")
                        # Fallback to signal price
                        exec_price = entry_price

                # CRITICAL FIX: Recalculate SL from REAL execution price
                # Signal price may differ significantly from execution price
                from utils.decimal_utils import calculate_stop_loss, to_decimal

                position_side_for_sl = 'long' if side.lower() == 'buy' else 'short'
                stop_loss_price = calculate_stop_loss(
                    to_decimal(exec_price),  # Use REAL execution price, not signal price
                    position_side_for_sl,
                    to_decimal(stop_loss_percent)
                )

                logger.info(f"🛡️ SL calculated from exec_price ${exec_price}: ${stop_loss_price} ({stop_loss_percent}%)")

                # CRITICAL FIX: Update BOTH entry_price and current_price with execution price
                # entry_price should reflect ACTUAL fill price from exchange, not signal price
                # This fixes PnL calculations and historical analysis
                await self.repository.update_position(position_id, **{
                    'entry_price': exec_price,      # ← NEW: Set actual execution price
                    'current_price': exec_price,     # Keep existing behavior (will be updated by WebSocket)
                    'status': state.value,
                    'exchange_order_id': entry_order.id
                })

                logger.debug(
                    f"📝 Updated position #{position_id} with execution price: ${exec_price:.8f} "
                    f"(signal was ${entry_price:.8f})"
                )

                # Log entry order to database for audit trail
                logger.info(f"🔍 About to log entry order for {symbol}")
                try:
                    await self.repository.create_order({
                        'position_id': str(position_id),
                        'exchange': exchange,
                        'symbol': symbol,
                        'order_id': entry_order.id,
                        'client_order_id': getattr(entry_order, 'clientOrderId', None),
                        'type': 'MARKET',
                        'side': side,
                        'size': quantity,
                        'price': exec_price or entry_price,
                        'status': 'FILLED',
                        'filled': quantity,
                        'remaining': 0,
                        'fee': getattr(entry_order, 'fee', 0),
                        'fee_currency': getattr(entry_order, 'feeCurrency', 'USDT')
                    })
                    logger.info(f"📝 Entry order logged to database")
                except Exception as e:
                    logger.error(f"❌ Failed to log entry order to DB: {e}")

                # Log entry trade to database (executed trade)
                logger.info(f"🔍 About to log entry trade for {symbol}")
                try:
                    await self.repository.create_trade({
                        'signal_id': signal_id,
                        'symbol': symbol,
                        'exchange': exchange,
                        'side': side,
                        'order_type': 'MARKET',
                        'quantity': quantity,
                        'price': exec_price or entry_price,
                        'executed_qty': quantity,
                        'average_price': exec_price or entry_price,
                        'order_id': entry_order.id,
                        'client_order_id': getattr(entry_order, 'clientOrderId', None),
                        'status': 'FILLED',
                        'fee': getattr(entry_order, 'fee', 0),
                        'fee_currency': getattr(entry_order, 'feeCurrency', 'USDT')
                    })
                    logger.info(f"📝 Entry trade logged to database")
                except Exception as e:
                    logger.error(f"❌ Failed to log entry trade to DB: {e}")

                # FIX: Verify position exists on exchange before SL placement
                # Add 3s delay for order settlement (increased from 1s - Error #2 fix)
                logger.debug(f"Waiting 3s for position settlement on {exchange}...")
                await asyncio.sleep(3.0)

                # Verify position actually exists
                try:
                    positions = await exchange_instance.fetch_positions([symbol])
                    active_position = next(
                        (p for p in positions if p.get('contracts', 0) > 0 or p.get('size', 0) > 0),
                        None
                    )

                    if not active_position:
                        logger.error(
                            f"❌ Position not found for {symbol} after order. "
                            f"Order status: {entry_order.status}, filled: {entry_order.filled}"
                        )
                        raise AtomicPositionError(
                            f"Position not found after order - order may have failed. "
                            f"Order status: {entry_order.status}"
                        )

                    logger.debug(f"✅ Position verified for {symbol}: {active_position.get('contracts', 0)} contracts")

                except Exception as e:
                    # If position verification fails, log warning but continue
                    # (exchange might have different position reporting)
                    if isinstance(e, AtomicPositionError):
                        raise  # Re-raise our own errors
                    logger.warning(f"⚠️ Could not verify position for {symbol}: {e}")

                # Step 3: Размещение stop-loss с retry
                logger.info(f"🛡️ Placing stop-loss for {symbol} at {stop_loss_price}")
                state = PositionState.PENDING_SL

                sl_placed = False
                max_retries = 3

                for attempt in range(max_retries):
                    try:
                        # Используем StopLossManager для идемпотентной установки SL
                        sl_result = await self.stop_loss_manager.set_stop_loss(
                            symbol=symbol,
                            side='sell' if side.lower() == 'buy' else 'buy',
                            amount=quantity,
                            stop_price=stop_loss_price
                        )

                        if sl_result and sl_result.get('status') in ['created', 'already_exists']:
                            sl_placed = True
                            sl_order = sl_result
                            logger.info(f"✅ Stop-loss placed successfully")

                            # Log SL order to database (but not trade - only when executed)
                            try:
                                sl_side = 'sell' if side.lower() == 'buy' else 'buy'
                                await self.repository.create_order({
                                    'position_id': str(position_id),
                                    'exchange': exchange,
                                    'symbol': symbol,
                                    'order_id': sl_result.get('orderId'),
                                    'client_order_id': sl_result.get('clientOrderId'),
                                    'type': sl_result.get('orderType', 'STOP_MARKET'),
                                    'side': sl_side,
                                    'size': quantity,
                                    'price': stop_loss_price,
                                    'status': 'NEW',
                                    'filled': 0,
                                    'remaining': quantity,
                                    'fee': 0,
                                    'fee_currency': 'USDT'
                                })
                                logger.info(f"📝 Stop-loss order logged to database")
                            except Exception as e:
                                logger.error(f"❌ Failed to log SL order to DB: {e}")

                            break

                    except Exception as e:
                        logger.warning(f"⚠️ SL attempt {attempt + 1}/{max_retries} failed: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            # Final attempt failed - MUST rollback
                            raise AtomicPositionError(
                                f"Failed to place stop-loss after {max_retries} attempts: {e}"
                            )

                if not sl_placed:
                    raise AtomicPositionError("Stop-loss placement failed")

                # Step 4: Активация позиции с defensive check (Layer 3 defense)
                activation_successful = await self._safe_activate_position(
                    position_id=position_id,
                    symbol=symbol,
                    exchange=exchange,
                    stop_loss_price=stop_loss_price
                )

                if not activation_successful:
                    # Duplicate detected by Layer 3 - trigger rollback
                    raise AtomicPositionError(
                        f"Duplicate active position detected for {symbol} on {exchange}. "
                        f"This should not happen with Layer 1&2 in place - investigate!"
                    )

                state = PositionState.ACTIVE
                logger.info(f"🎉 Position {symbol} is ACTIVE with protection")

                return {
                    'position_id': position_id,
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': position_data['side'],
                    'quantity': quantity,
                    'entry_price': exec_price,  # ← FIXED: Return actual execution price
                    'signal_price': entry_price,  # ← NEW: Keep signal price for reference
                    'stop_loss_price': stop_loss_price,
                    'state': state.value,
                    'entry_order': entry_order.raw_data,  # Return raw data for compatibility
                    'sl_order': sl_order
                }

            except Exception as e:
                error_str = str(e)

                # Check for Binance "Invalid symbol status" error
                if "code\":-4140" in error_str or "Invalid symbol status" in error_str:
                    logger.warning(f"⚠️ Symbol {symbol} is unavailable for trading (delisted or reduce-only): {e}")

                    # Clean up: Delete position from DB if it was created
                    if position_id:
                        try:
                            await self.repository.update_position(position_id, **{
                                'status': 'canceled',
                                'exit_reason': truncate_exit_reason('Symbol unavailable for trading')
                            })
                        except:
                            pass  # Ignore cleanup errors

                    # Raise specific exception for unavailable symbols
                    raise SymbolUnavailableError(f"Symbol {symbol} unavailable for trading on {exchange}")

                # Check for Bybit "minimum limit" error
                if "retCode\":10001" in error_str or "exceeds minimum limit" in error_str:
                    logger.warning(f"⚠️ Order size for {symbol} doesn't meet exchange requirements: {e}")

                    # CRITICAL FIX: Call rollback to close orphan position on exchange
                    # Without this, position may remain open without SL protection
                    await self._rollback_position(
                        position_id=position_id,
                        entry_order=entry_order,
                        symbol=symbol,
                        exchange=exchange,
                        state=state,
                        quantity=quantity,
                        error=error_str
                    )

                    # Raise specific exception for minimum limit
                    raise MinimumOrderLimitError(f"Order size for {symbol} below minimum limit on {exchange}")

                logger.error(f"❌ Atomic position creation failed: {e}")

                # CRITICAL: Rollback logic for other errors
                await self._rollback_position(
                    position_id=position_id,
                    entry_order=entry_order,
                    symbol=symbol,
                    exchange=exchange,
                    state=state,
                    quantity=quantity,  # CRITICAL FIX: pass quantity for proper close
                    error=str(e)
                )

                raise AtomicPositionError(f"Position creation rolled back: {e}")

    async def _rollback_position(
        self,
        position_id: Optional[int],
        entry_order: Optional[Any],
        symbol: str,
        exchange: str,
        state: PositionState,
        quantity: float,  # CRITICAL FIX: needed for proper position close on rollback
        error: str
    ):
        """
        Откат позиции при ошибке

        CRITICAL: Обеспечивает что не остается позиций без защиты
        """
        logger.warning(f"🔄 Rolling back position for {symbol}, state={state.value}")

        try:
            # Если entry был размещен но нет SL - КРИТИЧНО!
            if entry_order and state in [PositionState.ENTRY_PLACED, PositionState.PENDING_SL]:
                logger.critical(f"⚠️ CRITICAL: Position without SL detected, closing immediately!")

                # Немедленное закрытие позиции
                # FIX: exchange_manager is a dict, not an object with get_exchange method
                exchange_instance = self.exchange_manager.get(exchange)
                if exchange_instance:
                    try:
                        # CRITICAL FIX: Poll for position visibility before closing
                        # Race condition: position may not be visible immediately
                        from core.position_manager import normalize_symbol

                        our_position = None
                        max_attempts = 20  # Increased from 10 (Error #2 fix)

                        for attempt in range(max_attempts):
                            positions = await exchange_instance.exchange.fetch_positions(
                                params={'category': 'linear'}
                            )

                            for pos in positions:
                                if normalize_symbol(pos['symbol']) == normalize_symbol(symbol) and \
                                   float(pos.get('contracts', 0)) > 0:
                                    our_position = pos
                                    break

                            if our_position:
                                logger.info(f"✅ Position found on attempt {attempt + 1}/{max_attempts}")
                                break

                            if attempt < max_attempts - 1:
                                await asyncio.sleep(1.0)  # Poll every 1s (increased from 0.5s - Error #2 fix)

                        if our_position:
                            # Закрываем market ордером
                            close_side = 'sell' if entry_order.side == 'buy' else 'buy'
                            close_order = await exchange_instance.create_market_order(
                                symbol, close_side, quantity
                            )
                            logger.info(f"✅ Emergency close executed: {close_order.id}")
                        else:
                            logger.critical(f"❌ Position {symbol} not found after {max_attempts} attempts!")
                            logger.critical(f"⚠️ ALERT: Open position without SL may exist on exchange!")
                    except Exception as close_error:
                        logger.critical(f"❌ FAILED to close unprotected position: {close_error}")
                        # TODO: Send alert to administrator

            # Обновляем статус в БД
            if position_id:
                # FIX: update_position expects **kwargs, not dict as second argument
                # FIX: Truncate error to fit varchar(500) limit
                await self.repository.update_position(position_id, **{
                    'status': PositionState.ROLLED_BACK.value,
                    'closed_at': datetime.utcnow(),  # FIX: Use offset-naive datetime for database compatibility
                    'exit_reason': truncate_exit_reason(f'rollback: {error}')
                })

        except Exception as rollback_error:
            logger.critical(f"❌ Rollback failed: {rollback_error}")

    async def recover_incomplete_positions(self):
        """
        Recovery механизм для незавершенных позиций

        Запускается при старте бота для обработки позиций,
        которые были прерваны во время создания
        """
        logger.info("🔍 Checking for incomplete positions...")

        # Находим позиции в промежуточных состояниях
        incomplete_states = [
            PositionState.PENDING_ENTRY.value,
            PositionState.ENTRY_PLACED.value,
            PositionState.PENDING_SL.value
        ]

        incomplete = await self.repository.get_positions_by_status(incomplete_states)

        if not incomplete:
            logger.info("✅ No incomplete positions found")
            return

        logger.warning(f"⚠️ Found {len(incomplete)} incomplete positions")

        for pos in incomplete:
            try:
                symbol = pos['symbol']
                state = pos['status']

                logger.info(f"🔧 Recovering position {symbol} in state {state}")

                if state == PositionState.PENDING_ENTRY.value:
                    # Entry не был размещен - безопасно пометить как failed
                    # FIX: update_position expects **kwargs, not dict as second argument
                    await self.repository.update_position(pos['id'], **{
                        'status': PositionState.FAILED.value,
                        'exit_reason': truncate_exit_reason('incomplete: entry not placed')
                    })

                elif state == PositionState.ENTRY_PLACED.value:
                    # Entry размещен но нет SL - КРИТИЧНО!
                    await self._recover_position_without_sl(pos)

                elif state == PositionState.PENDING_SL.value:
                    # В процессе установки SL - проверить и завершить
                    await self._complete_sl_placement(pos)

                logger.info(f"✅ Recovered position {symbol}")

            except Exception as e:
                logger.error(f"❌ Failed to recover position {pos['id']}: {e}")

    async def _recover_position_without_sl(self, position: Dict):
        """Восстановление позиции без stop-loss"""
        symbol = position['symbol']

        logger.warning(f"🚨 Recovering position without SL: {symbol}")

        # Пытаемся установить SL
        try:
            sl_result = await self.stop_loss_manager.set_stop_loss(
                symbol=symbol,
                side='sell' if position['side'] == 'long' else 'buy',
                amount=position['quantity'],
                stop_price=position.get('planned_sl_price',
                          self._calculate_default_sl(position['entry_price'], position['side']))
            )

            if sl_result and sl_result.get('status') in ['created', 'already_exists']:
                # FIX: Use only columns that exist in database schema
                await self.repository.update_position(position['id'], **{
                    'stop_loss_price': sl_result.get('stopPrice'),  # Setting this indicates SL is active
                    'status': PositionState.ACTIVE.value
                })
                logger.info(f"✅ SL restored for {symbol}")
            else:
                # Не удалось восстановить SL - закрываем позицию
                await self._emergency_close_position(position)

        except Exception as e:
            logger.error(f"Failed to recover SL: {e}")
            await self._emergency_close_position(position)

    async def _complete_sl_placement(self, position: Dict):
        """Завершение размещения SL"""
        # Check if SL already exists
        has_sl = await self.stop_loss_manager.has_stop_loss(position['symbol'])

        if has_sl[0]:
            # SL уже установлен
            # FIX: Use only columns that exist in database schema
            await self.repository.update_position(position['id'], **{
                'stop_loss_price': has_sl[1],  # Setting this indicates SL is active
                'status': PositionState.ACTIVE.value
            })
        else:
            # Пытаемся установить SL
            await self._recover_position_without_sl(position)

    async def _emergency_close_position(self, position: Dict):
        """Экстренное закрытие позиции без защиты"""
        logger.critical(f"🚨 EMERGENCY CLOSE for {position['symbol']}")

        try:
            # FIX: exchange_manager is a dict, not an object with get_exchange method
            exchange = self.exchange_manager.get(position['exchange'])
            if exchange:
                close_side = 'sell' if position['side'] == 'long' else 'buy'
                close_order = await exchange.create_market_order(
                    position['symbol'], close_side, position['quantity']
                )

                # FIX: Use only columns that exist in database schema
                await self.repository.update_position(position['id'], **{
                    'status': 'closed',
                    'closed_at': datetime.utcnow(),  # FIX: Use offset-naive datetime for database compatibility
                    'exit_reason': truncate_exit_reason('emergency: no stop loss'),
                    'current_price': close_order.price if close_order else None  # Use current_price instead of exit_price
                })

                logger.info(f"✅ Emergency close completed")
        except Exception as e:
            logger.critical(f"❌ Emergency close failed: {e}")
            # TODO: Send critical alert

    def _calculate_default_sl(self, entry_price: float, side: str, percent: float = 2.0) -> float:
        """Расчет дефолтного stop-loss"""
        if side == 'long':
            return entry_price * (1 - percent / 100)
        else:
            return entry_price * (1 + percent / 100)