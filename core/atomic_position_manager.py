"""
Atomic Position Manager - гарантирует атомарность создания позиций со stop-loss

CRITICAL: Этот модуль обеспечивает атомарность операций Entry+SL
Все позиции ДОЛЖНЫ иметь stop-loss или быть немедленно закрыты

⚠️ DO NOT MODIFY без полного понимания последствий!
"""
import asyncio
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from utils.datetime_helpers import now_utc, ensure_utc
from decimal import Decimal
import uuid
from database.transactional_repository import TransactionalRepository
from core.event_logger import EventLogger, EventType, log_event
from core.exchange_response_adapter import ExchangeResponseAdapter

if TYPE_CHECKING:
    from config.settings import TradingConfig

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

    def __init__(self, repository, exchange_manager, stop_loss_manager, position_manager=None, config: Optional['TradingConfig'] = None):
        """
        Initialize AtomicPositionManager

        Args:
            repository: Database repository
            exchange_manager: Exchange manager dict
            stop_loss_manager: Stop loss manager instance
            position_manager: Optional position manager reference
            config: Optional TradingConfig object (NOT Config!) for leverage and trailing stop fallback
        """
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

    async def _verify_position_exists_multi_source(
        self,
        exchange_instance,
        symbol: str,
        exchange: str,
        entry_order: Any,
        expected_quantity: float,
        timeout: float = 10.0
    ) -> bool:
        """
        Verify position exists using multiple data sources with retry logic.

        DIAGNOSTIC PATCH 2025-10-29:
        Added verbose logging (WARNING/ERROR level) to diagnose SOURCE 1 failures.
        This is TEMPORARY patch to capture exceptions that were invisible with DEBUG logging.

        Uses priority-based approach:
        1. Order filled status - MOST RELIABLE (PRIMARY)
        2. WebSocket position updates - SECONDARY
        3. REST API fetch_positions - FALLBACK

        Args:
            exchange_instance: Exchange connection
            symbol: Trading symbol
            exchange: Exchange name
            entry_order: The entry order that should have created position
            expected_quantity: Expected position size
            timeout: Max time to wait for verification (default 10s)

        Returns:
            True if position verified to exist
            False if position confirmed NOT to exist (order failed)

        Raises:
            AtomicPositionError if unable to verify after timeout
        """
        # FIX RC#1: Изменен приоритет verification sources
        # Order Status теперь ПРИОРИТЕТ 1 (самый надежный - ордер УЖЕ исполнен)
        logger.info(
            f"🔍 Multi-source position verification for {symbol}\n"
            f"  Expected quantity: {expected_quantity}\n"
            f"  Timeout: {timeout}s\n"
            f"  Order ID: {entry_order.id}\n"
            f"  Priority: 1=OrderStatus, 2=WebSocket, 3=RestAPI"
        )

        start_time = asyncio.get_event_loop().time()
        attempt = 0

        # Track which sources we've tried
        sources_tried = {
            'order_status': False,  # ПРИОРИТЕТ 1 (БЫЛО 2)
            'websocket': False,     # ПРИОРИТЕТ 2 (БЫЛО 1)
            'rest_api': False       # ПРИОРИТЕТ 3 (БЕЗ ИЗМЕНЕНИЙ)
        }

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            attempt += 1
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.debug(
                f"Verification attempt {attempt} for {symbol} "
                f"(elapsed: {elapsed:.1f}s / {timeout}s)"
            )

            # ============================================================
            # SOURCE 1 (PRIORITY 1): Order filled status
            # САМЫЙ НАДЕЖНЫЙ - ордер УЖЕ ИСПОЛНЕН в exchange
            # SKIP for Bybit: UUID order IDs cannot be queried via fetch_order (API v5 limitation)
            # ============================================================
            if not sources_tried['order_status']:
                try:
                    # DIAGNOSTIC PATCH 2025-10-29: Changed to WARNING for visibility
                    logger.warning(f"🔍 [SOURCE 1/3] Checking order status for {entry_order.id}")

                    # Refetch order to get latest status
                    # Small delay first only on first attempt
                    if attempt == 1:
                        await asyncio.sleep(0.5)

                    # DIAGNOSTIC PATCH 2025-10-29: Log BEFORE fetch_order call
                    logger.warning(f"🔄 [SOURCE 1] About to call fetch_order(id={entry_order.id}, symbol={symbol})")

                    order_status = await exchange_instance.fetch_order(entry_order.id, symbol)

                    # DIAGNOSTIC PATCH 2025-10-29: Log AFTER fetch_order call
                    logger.warning(f"✓ [SOURCE 1] fetch_order returned: {order_status is not None}")

                    if order_status:
                        # FIX 2025-10-29: order_status is OrderResult dataclass, not dict
                        # Must use attribute access, not .get()
                        filled = float(order_status.filled)
                        status = order_status.status

                        # DIAGNOSTIC PATCH 2025-10-29: Changed to INFO for visibility
                        logger.info(
                            f"📊 [SOURCE 1] Order status fetched: id={entry_order.id}, status={status}, filled={filled}"
                        )

                        if filled > 0:
                            logger.info(
                                f"✅ [SOURCE 1] Order status CONFIRMED position exists!\n"
                                f"  Order ID: {entry_order.id}\n"
                                f"  Status: {status}\n"
                                f"  Filled: {filled}\n"
                                f"  Expected: {expected_quantity}\n"
                                f"  Match: {'YES ✅' if abs(filled - expected_quantity) < 0.01 else 'PARTIAL ⚠️'}\n"
                                f"  Verification time: {elapsed:.2f}s"
                            )
                            return True  # SUCCESS!

                        elif status == 'closed' and filled == 0:
                            # Order closed but not filled = order FAILED
                            logger.error(
                                f"❌ [SOURCE 1] Order FAILED verification:\n"
                                f"  Status: closed\n"
                                f"  Filled: 0\n"
                                f"  This means order was rejected or cancelled!"
                            )
                            return False  # Confirmed: position does NOT exist

                    # Помечаем source как tried только после проверки
                    sources_tried['order_status'] = True

                except Exception as e:
                    # DIAGNOSTIC PATCH 2025-10-29: Changed to ERROR for visibility
                    # CRITICAL: This exception is WHY verification fails!
                    logger.error(
                        f"❌ [SOURCE 1] Order status check EXCEPTION:\n"
                        f"  Exception type: {type(e).__name__}\n"
                        f"  Exception message: {str(e)}\n"
                        f"  Order ID: {entry_order.id}\n"
                        f"  Symbol: {symbol}\n"
                        f"  Attempt: {attempt}\n"
                        f"  Elapsed: {elapsed:.2f}s",
                        exc_info=True  # Include stack trace
                    )
                    # НЕ помечаем как tried - будем retry в следующей итерации

            # ============================================================
            # SOURCE 2 (PRIORITY 2): WebSocket position updates
            # ВТОРИЧНЫЙ - может иметь delay в обновлении self.positions
            # ============================================================
            if self.position_manager and hasattr(self.position_manager, 'get_cached_position') and not sources_tried['websocket']:
                try:
                    logger.debug(f"🔍 [SOURCE 2/3] Checking WebSocket cache for {symbol}")

                    ws_position = self.position_manager.get_cached_position(symbol, exchange)

                    if ws_position:
                        ws_quantity = float(ws_position.get('quantity', 0))
                        ws_side = ws_position.get('side', '')

                        logger.debug(
                            f"📊 WebSocket position: symbol={symbol}, quantity={ws_quantity}, side={ws_side}"
                        )

                        if ws_quantity > 0:
                            # Проверяем соответствие quantity
                            quantity_diff = abs(ws_quantity - expected_quantity)

                            if quantity_diff <= 0.01:  # Допускаем погрешность 0.01
                                logger.info(
                                    f"✅ [SOURCE 2] WebSocket CONFIRMED position exists!\n"
                                    f"  Symbol: {symbol}\n"
                                    f"  Quantity: {ws_quantity} (expected: {expected_quantity})\n"
                                    f"  Side: {ws_side}\n"
                                    f"  Verification time: {elapsed:.2f}s"
                                )
                                sources_tried['websocket'] = True  # Mark as tried on success
                                return True  # SUCCESS!
                            else:
                                logger.warning(
                                    f"⚠️ [SOURCE 2] WebSocket quantity mismatch!\n"
                                    f"  Expected: {expected_quantity}\n"
                                    f"  Got: {ws_quantity}\n"
                                    f"  Difference: {quantity_diff}"
                                )
                                sources_tried['websocket'] = True  # Mark as tried on mismatch

                    # CRITICAL FIX 2025-10-29: DON'T mark as tried if ws_position == None
                    # This allows retry on next attempt when WebSocket data arrives
                    # Old code marked as tried here → prevented retries

                except AttributeError as e:
                    logger.debug(f"⚠️ [SOURCE 2] WebSocket not available: {e}")
                    sources_tried['websocket'] = True
                except Exception as e:
                    logger.debug(f"⚠️ [SOURCE 2] WebSocket check failed: {e}")
                    sources_tried['websocket'] = True

            # ============================================================
            # SOURCE 3 (PRIORITY 3): REST API fetch_positions
            # FALLBACK - может иметь cache delay
            # ============================================================
            if not sources_tried['rest_api'] or attempt % 3 == 0:  # Retry every 3 attempts
                try:
                    logger.debug(f"🔍 [SOURCE 3/3] Checking REST API positions for {symbol}")

                    # Fetch positions from REST API
                    positions = await exchange_instance.fetch_positions([symbol])

                    # Find our position
                    for pos in positions:
                        pos_symbol = pos.get('symbol', '')  # Unified format

                        contracts = float(pos.get('contracts', 0))

                        if pos_symbol == symbol and contracts > 0:
                            logger.info(
                                f"✅ [SOURCE 3] REST API CONFIRMED position exists!\n"
                                f"  Symbol: {symbol}\n"
                                f"  Contracts: {contracts}\n"
                                f"  Expected: {expected_quantity}\n"
                                f"  Match: {'YES ✅' if abs(contracts - expected_quantity) < 0.01 else 'NO ⚠️'}\n"
                                f"  Verification time: {elapsed:.2f}s"
                            )
                            return True

                    sources_tried['rest_api'] = True

                except Exception as e:
                    logger.debug(f"⚠️ [SOURCE 3] REST API check failed: {e}")
                    # Don't mark as tried - will retry

            # No source confirmed position yet - wait before retry
            wait_time = min(0.5 * (1.5 ** attempt), 2.0)  # Exponential backoff: 0.5s, 0.75s, 1.12s, 1.69s, 2s...
            await asyncio.sleep(wait_time)

        # Timeout reached without verification
        logger.critical(
            f"❌ Multi-source verification TIMEOUT for {symbol}:\n"
            f"  Duration: {timeout}s\n"
            f"  Attempts: {attempt}\n"
            f"  Sources tried:\n"
            f"    - WebSocket: {sources_tried['websocket']}\n"
            f"    - Order status: {sources_tried['order_status']}\n"
            f"    - REST API: {sources_tried['rest_api']}\n"
            f"  Order ID: {entry_order.id}\n"
            f"  Expected quantity: {expected_quantity}"
        )

        raise AtomicPositionError(
            f"Could not verify position for {symbol} after {timeout}s timeout using any source. "
            f"Order ID: {entry_order.id}, Expected quantity: {expected_quantity}. "
            f"This may indicate API issues or order rejection."
        )

    async def open_position_atomic(
        self,
        request: Any,  # PositionRequest
        quantity: float,
        exchange_manager: Dict[str, Any],
        trailing_activation_percent: Optional[float] = None,
        trailing_callback_percent: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Атомарное создание позиции с гарантированным stop-loss

        Args:
            request: Объект запроса позиции (PositionRequest)
            quantity: Размер позиции
            exchange_manager: Словарь менеджеров бирж
            trailing_activation_percent: Процент активации трейлинга (per-signal)
            trailing_callback_percent: Процент отката трейлинга (per-signal)

        Returns:
            Dict с информацией о позиции или None при ошибке

        Raises:
            AtomicPositionError: При нарушении атомарности
        """
        # Extract params from request
        signal_id = request.signal_id
        symbol = request.symbol
        exchange = request.exchange
        side = request.side
        entry_price = float(request.entry_price)
        
        # Strategy params override .env fallback (§5.1: use strategy.leverage)
        sp = getattr(request, 'strategy_params', None) or {}
        if self.config:
            stop_loss_percent = float(sp.get('stop_loss_percent', self.config.stop_loss_percent))
            trailing_activation_percent = float(sp.get('trailing_activation_percent', self.config.trailing_activation_percent))
            trailing_callback_percent = float(sp.get('trailing_callback_percent', self.config.trailing_callback_percent))
        else:
            stop_loss_percent = float(sp.get('stop_loss_percent', 4.0))
            trailing_activation_percent = float(sp.get('trailing_activation_percent', 2.0))
            trailing_callback_percent = float(sp.get('trailing_callback_percent', 0.5))
        
        source = "strategy_params" if sp else ".env"
        logger.info(f"Atomic params from {source}: SL={stop_loss_percent}%, TS_act={trailing_activation_percent}%, TS_cb={trailing_callback_percent}%")

        operation_id = f"pos_{symbol}_{now_utc().timestamp()}"

        position_id = None
        entry_order = None
        sl_order = None
        state = PositionState.PENDING_ENTRY

        async with self.atomic_operation(operation_id):
            try:
                # Step 1: Размещение entry ордера (MOVED UP - before position creation)
                logger.info(f"📊 Placing entry order for {symbol}")
                state = PositionState.ENTRY_PLACED

                # FIX: exchange_manager is a dict, not an object with get_exchange method
                exchange_instance = self.exchange_manager.get(exchange)
                if not exchange_instance:
                    raise AtomicPositionError(f"Exchange {exchange} not available")

                # §5.1: Set leverage — strategy_params override, .env fallback
                sp = getattr(request, 'strategy_params', None) or {}
                if sp.get('leverage') or (self.config and self.config.auto_set_leverage):
                    leverage = int(sp.get('leverage', self.config.leverage if self.config else 1))
                    logger.info(f"🎚️ Setting {leverage}x leverage for {symbol} (source={'strategy' if sp.get('leverage') else '.env'})")
                    leverage_set = await exchange_instance.set_leverage(symbol, leverage)
                    if not leverage_set:
                        logger.warning(
                            f"⚠️ Could not set leverage for {symbol}, "
                            f"using exchange default"
                        )
                        # Continue anyway - leverage might already be set correctly

                # Prepare params for exchange-specific requirements
                params = {}
                if exchange == 'binance':
                    # CRITICAL FIX: Request FULL response to get avgPrice and fills
                    # Default newOrderRespType=ACK returns avgPrice="0.00000"
                    # NOTE: FULL returns immediately with status='NEW', executedQty='0'
                    # We fetch order afterwards to get actual filled status and avgPrice
                    params['newOrderRespType'] = 'FULL'
                    logger.debug(f"Setting newOrderRespType=FULL for Binance market order")

                # FIX #1: Pre-register position BEFORE order execution (prevents race condition)
                # WebSocket updates arrive instantly (<1ms), must register before order
                if hasattr(self, 'position_manager') and self.position_manager:
                    await self.position_manager.pre_register_position(symbol, exchange)
                    logger.info(f"⚡ Pre-registered {symbol} for WebSocket tracking (BEFORE order)")

                raw_order = await exchange_instance.create_market_order(
                    symbol, side, quantity, params=params if params else None
                )

                # Check if order was created
                if raw_order is None:
                    raise AtomicPositionError(f"Failed to create order for {symbol}: order returned None")



                # CRITICAL FIX: Market orders need fetch for full data
                # - Binance: Returns status='NEW', need fetch for status='FILLED'
                # - Bybit: Returns minimal response (only orderId), need fetch for all fields
                # Fetch order to get complete data including side, status, filled, avgPrice
                if raw_order and raw_order.id:
                    order_id = raw_order.id

                    # FIX RC#2: Retry logic для fetch_order с exponential backoff
                    # Bybit API v5 имеет propagation delay - 0.5s недостаточно
                    max_retries = 5
                    fetched_order = None

                    retry_delay = 0.1

                    for attempt in range(1, max_retries + 1):
                        try:
                            await asyncio.sleep(retry_delay)
                            fetched_order = await exchange_instance.fetch_order(order_id, symbol)

                            if fetched_order:
                                logger.info(
                                    f"✅ Fetched {exchange} order on attempt {attempt}/{max_retries}: "
                                    f"id={order_id}, "
                                    f"side={fetched_order.side}, "
                                    f"status={fetched_order.status}, "
                                    f"filled={fetched_order.filled}/{fetched_order.amount}, "
                                    f"avgPrice={fetched_order.price}"
                                )
                                raw_order = fetched_order
                                break
                            else:
                                logger.warning(
                                    f"⚠️ Attempt {attempt}/{max_retries}: fetch_order returned None for {order_id}"
                                )
                                if attempt < max_retries:
                                    retry_delay *= 1.5

                        except Exception as e:
                            logger.warning(
                                f"⚠️ Attempt {attempt}/{max_retries}: fetch_order failed with error: {e}"
                            )
                            if attempt < max_retries:
                                retry_delay *= 1.5

                    if not fetched_order:
                        logger.error(
                            f"❌ CRITICAL: fetch_order returned None after {max_retries} attempts for {order_id}!\n"
                            f"  Exchange: {exchange}\n"
                            f"  Symbol: {symbol}\n"
                            f"  Will attempt to use create_order response (may be incomplete)."
                        )

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

                # BINANCE FALLBACK: If avgPrice still 0, fetch position for execution price
                if exchange == 'binance' and (not exec_price or exec_price == 0):
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

                # Step 2: Создание записи позиции с REAL execution price
                # Position created AFTER order execution to use real fill price
                logger.info(f"📝 Creating position record for {symbol} with exec price ${exec_price:.8f}")
                position_data = {
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': 'long' if side.lower() == 'buy' else 'short',
                    'quantity': quantity,
                    'entry_price': exec_price,  # ← FIXED: Use REAL execution price, not signal
                    'current_price': exec_price,
                    'status': state.value,
                    'exchange_order_id': entry_order.id,
                    'trailing_activation_percent': trailing_activation_percent,
                    'trailing_callback_percent': trailing_callback_percent,
                    'signal_id': signal_id,
                    'leverage': int(sp.get('leverage', self.config.leverage if self.config else 1)),
                }

                position_id = await self.repository.create_position(position_data)
                logger.info(f"✅ Position record created: ID={position_id} (entry=${exec_price:.8f})")

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

                # Step 2.5: Multi-source position verification
                try:
                    logger.info(f"🔍 Verifying position exists for {symbol}...")

                    position_exists = await self._verify_position_exists_multi_source(
                        exchange_instance=exchange_instance,
                        symbol=symbol,
                        exchange=exchange,
                        entry_order=entry_order,
                        expected_quantity=quantity,
                        timeout=10.0  # 10 second timeout (was 3s wait before)
                    )

                    if not position_exists:
                        # Confirmed: position does NOT exist (order failed/rejected)
                        raise AtomicPositionError(
                            f"Position verification failed for {symbol}. "
                            f"Order {entry_order.id} appears to have been rejected or cancelled. "
                            f"Cannot proceed with SL placement."
                        )

                    logger.info(f"✅ Position verified for {symbol}")

                except AtomicPositionError:
                    # Re-raise atomic errors (position verification failed)
                    raise
                except Exception as e:
                    # Unexpected error during verification
                    logger.error(f"❌ Unexpected error during position verification: {e}")
                    raise AtomicPositionError(f"Position verification error: {e}")

                # Step 3: Размещение stop-loss с retry
                logger.info(f"🛡️ Placing stop-loss for {symbol} at {stop_loss_price}")
                state = PositionState.PENDING_SL

                sl_placed = False
                max_retries = 3
                sl_created_in_operation = None  # NEW: Track SL from this operation

                for attempt in range(max_retries):
                    try:
                        # Используем StopLossManager для идемпотентной установки SL
                        sl_result = await self.stop_loss_manager.set_stop_loss(
                            symbol=symbol,
                            side='sell' if side.lower() == 'buy' else 'buy',
                            amount=quantity,
                            stop_price=stop_loss_price,
                            operation_id=operation_id,  # NEW: Pass operation ID
                            created_in_operation=sl_created_in_operation  # NEW: Pass created SL
                        )

                        if sl_result and sl_result.get('status') in ['created', 'already_exists', 'success']:
                            sl_placed = True
                            sl_order = sl_result
                            
                            # NEW: Track SL created in this operation
                            if sl_result.get('status') == 'created':
                                sl_created_in_operation = sl_result.get('algoId')
                                logger.info(f"📝 Tracked SL for operation: {sl_created_in_operation}")
                            
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
                        from utils.symbol_helpers import normalize_symbol

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
                            # CRITICAL FIX: Validate entry_order.side before calculating close_side
                            # entry_order.side should ALWAYS be 'buy' or 'sell' (enforced by FIX #1.2)
                            # But defensive check in case it somehow becomes invalid

                            if entry_order.side not in ('buy', 'sell'):
                                logger.critical(
                                    f"❌ CRITICAL: entry_order.side is INVALID: '{entry_order.side}' for {symbol}!\n"
                                    f"  This should NEVER happen (normalize_order should fail-fast).\n"
                                    f"  Cannot calculate close_side safely.\n"
                                    f"  Will use position.side from exchange as source of truth."
                                )

                                # FALLBACK: Use position side from exchange (most reliable source)
                                position_side = our_position.get('side', '').lower()

                                if position_side == 'long':
                                    close_side = 'sell'
                                    logger.critical(f"✅ Using position.side='long' → close_side='sell'")
                                elif position_side == 'short':
                                    close_side = 'buy'
                                    logger.critical(f"✅ Using position.side='short' → close_side='buy'")
                                else:
                                    # Even position.side is invalid - this is catastrophic!
                                    logger.critical(
                                        f"❌ CATASTROPHIC: Both entry_order.side and position.side are invalid!\n"
                                        f"  entry_order.side: '{entry_order.side}'\n"
                                        f"  position.side: '{position_side}'\n"
                                        f"  Cannot determine correct close_side.\n"
                                        f"  ABORTING ROLLBACK - position will remain open without SL!"
                                    )
                                    raise AtomicPositionError(
                                        f"Cannot rollback {symbol}: Both entry_order.side ('{entry_order.side}') "
                                        f"and position.side ('{position_side}') are invalid. "
                                        f"Cannot determine correct close direction!"
                                    )
                            else:
                                # Normal case: entry_order.side is valid
                                close_side = 'sell' if entry_order.side == 'buy' else 'buy'

                            # Log intended close order for audit
                            logger.critical(
                                f"📤 Rollback: Creating close order for {symbol}:\n"
                                f"  entry_order.side: '{entry_order.side}'\n"
                                f"  position.side: '{our_position.get('side')}'\n"
                                f"  close_side: '{close_side}'\n"
                                f"  quantity: {quantity}"
                            )

                            # Create close order
                            close_order = await exchange_instance.create_market_order(
                                symbol, close_side, quantity
                            )
                            logger.info(f"✅ Emergency close executed: {close_order.id}")

                            # CRITICAL FIX: Verify position was actually closed
                            logger.info(f"🔍 Verifying {symbol} position was closed by rollback...")

                            # Small delay for order execution
                            await asyncio.sleep(1.0)

                            # Multi-attempt verification (position should be 0 or not found)
                            verification_successful = False
                            max_verification_attempts = 10

                            for verify_attempt in range(max_verification_attempts):
                                try:
                                    # Check all available sources

                                    # Source 1: WebSocket
                                    if self.position_manager and hasattr(self.position_manager, 'get_cached_position'):
                                        try:
                                            ws_position = self.position_manager.get_cached_position(symbol, exchange)
                                            if not ws_position or float(ws_position.get('quantity', 0)) == 0:
                                                logger.info(
                                                    f"✅ [WebSocket] Confirmed {symbol} position closed "
                                                    f"(attempt {verify_attempt + 1})"
                                                )
                                                verification_successful = True
                                                break
                                        except Exception as e:
                                            logger.debug(f"WebSocket check failed: {e}")

                                    # Default fetch_order logic
                                    positions = await exchange_instance.fetch_positions([symbol])

                                    # Check if position still exists
                                    position_found = False
                                    for pos in positions:
                                        if pos['symbol'] == symbol or pos.get('info', {}).get('symbol') == symbol.replace('/', ''):
                                            contracts = float(pos.get('contracts', 0))
                                            if contracts > 0:
                                                position_found = True
                                                logger.warning(
                                                    f"⚠️ Position {symbol} still open: {contracts} contracts "
                                                    f"(attempt {verify_attempt + 1}/{max_verification_attempts})"
                                                )
                                                break

                                    if not position_found:
                                        logger.info(
                                            f"✅ [REST API] Confirmed {symbol} position closed "
                                            f"(attempt {verify_attempt + 1})"
                                        )
                                        verification_successful = True
                                        break

                                    # Still open - wait before retry
                                    if verify_attempt < max_verification_attempts - 1:
                                        await asyncio.sleep(1.0)

                                except Exception as e:
                                    logger.error(f"Error verifying position closure: {e}")
                                    if verify_attempt < max_verification_attempts - 1:
                                        await asyncio.sleep(1.0)

                            # Check verification result
                            if verification_successful:
                                logger.info(f"✅ VERIFIED: {symbol} position successfully closed by rollback")
                            else:
                                logger.critical(
                                    f"❌ CRITICAL: Could not verify {symbol} position was closed after rollback!\n"
                                    f"  Close order ID: {close_order.id}\n"
                                    f"  Verification attempts: {max_verification_attempts}\n"
                                    f"  Position may still be open on exchange!\n"
                                    f"  ⚠️ POTENTIAL ORPHANED POSITION - MANUAL VERIFICATION REQUIRED!"
                                )

                                # TODO: Send critical alert to administrator
                                # This is a serious issue that needs immediate attention
                        else:
                            logger.critical(f"❌ Position {symbol} not found after {max_attempts} attempts!")
                            logger.critical(f"⚠️ ALERT: Open position without SL may exist on exchange!")
                    except Exception as close_error:
                        logger.critical(f"❌ FAILED to close unprotected position: {close_error}")
                        # TODO: Send alert to administrator

            # CRITICAL FIX (December 11, 2025): Type Safety for position_id
            # Prevent TypeError: 'pending' ('str' object cannot be interpreted as an integer)
            # Issue: Pre-registered positions have position_id='pending' (string)
            # When rollback occurs before DB commit, we try to update with string ID
            # Solution: Check if position_id is a real integer before DB update
            if position_id and position_id != 'pending' and isinstance(position_id, int):
                logger.info(f"Updating database for position #{position_id} (rollback)")
                # FIX: update_position expects **kwargs, not dict as second argument
                # FIX: Truncate error to fit varchar(500) limit
                await self.repository.update_position(position_id, **{
                    'status': PositionState.ROLLED_BACK.value,
                    'closed_at': datetime.utcnow(),  # FIX: Use offset-naive datetime for database compatibility
                    'exit_reason': truncate_exit_reason(f'rollback: {error}')
                })
            elif position_id == 'pending':
                logger.warning(
                    f"{symbol}: Skipping database update - position not yet committed "
                    f"(position_id='pending'). Pre-registration will be cleaned up."
                )
                # Clean up pre-registration from memory
                if self.position_manager and symbol in self.position_manager.positions:
                    del self.position_manager.positions[symbol]
                    logger.info(f"Removed pre-registered position from memory: {symbol}")
            else:
                logger.warning(
                    f"{symbol}: No position_id available for database update "
                    f"(position_id={position_id})"
                )


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

            if sl_result and sl_result.get('status') in ['created', 'already_exists', 'success']:
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