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
from decimal import Decimal
import uuid
from database.transactional_repository import TransactionalRepository
from core.event_logger import EventLogger, EventType, log_event
from core.exchange_response_adapter import ExchangeResponseAdapter

logger = logging.getLogger(__name__)


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


class AtomicPositionManager:
    """
    Менеджер атомарного создания позиций

    Гарантирует:
    1. Позиция ВСЕГДА создается со stop-loss
    2. При ошибке SL позиция откатывается
    3. Recovery для незавершенных операций
    """

    def __init__(self, repository, exchange_manager, stop_loss_manager):
        self.repository = repository
        self.exchange_manager = exchange_manager
        self.stop_loss_manager = stop_loss_manager
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

    async def open_position_atomic(
        self,
        signal_id: int,
        symbol: str,
        exchange: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_loss_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Атомарное создание позиции с гарантированным stop-loss

        Args:
            signal_id: ID сигнала
            symbol: Торговый символ
            exchange: Название биржи
            side: 'buy' или 'sell'
            quantity: Размер позиции
            entry_price: Цена входа
            stop_loss_price: Уровень stop-loss

        Returns:
            Dict с информацией о позиции или None при ошибке

        Raises:
            AtomicPositionError: При нарушении атомарности
        """
        operation_id = f"pos_{symbol}_{datetime.now().timestamp()}"

        position_id = None
        entry_order = None
        sl_order = None
        state = PositionState.PENDING_ENTRY

        async with self.atomic_operation(operation_id):
            try:
                # Step 1: Создание записи позиции в состоянии PENDING_ENTRY
                logger.info(f"📝 Creating position record for {symbol}")
                position_data = {
                    'signal_id': signal_id,
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': 'long' if side.lower() == 'buy' else 'short',
                    'quantity': quantity,
                    'entry_price': entry_price,
                    'status': state.value,
                    'operation_id': operation_id
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

                raw_order = await exchange_instance.create_market_order(
                    symbol, side, quantity
                )

                # Normalize order response
                entry_order = ExchangeResponseAdapter.normalize_order(raw_order, exchange)

                if not ExchangeResponseAdapter.is_order_filled(entry_order):
                    raise AtomicPositionError(f"Entry order failed: {entry_order.status}")

                logger.info(f"✅ Entry order placed: {entry_order.id}")

                # Update position with entry details
                # Extract execution price from normalized order
                exec_price = ExchangeResponseAdapter.extract_execution_price(entry_order)

                # FIX: Use only columns that exist in database schema
                await self.repository.update_position(position_id, **{
                    'entry_price': exec_price,  # Update existing entry_price field
                    'status': state.value,
                    'exchange_order_id': entry_order.id  # Track order ID
                })

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

                # Step 4: Активация позиции
                state = PositionState.ACTIVE
                # FIX: Use only columns that exist in database schema
                await self.repository.update_position(position_id, **{
                    'stop_loss_price': stop_loss_price,  # Setting this indicates SL is active
                    'status': state.value
                })

                logger.info(f"🎉 Position {symbol} is ACTIVE with protection")

                return {
                    'position_id': position_id,
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': position_data['side'],
                    'quantity': quantity,
                    'entry_price': exec_price,  # Use extracted execution price
                    'stop_loss_price': stop_loss_price,
                    'state': state.value,
                    'entry_order': entry_order.raw_data,  # Return raw data for compatibility
                    'sl_order': sl_order
                }

            except Exception as e:
                # Check for Binance "Invalid symbol status" error
                error_str = str(e)
                if "code\":-4140" in error_str or "Invalid symbol status" in error_str:
                    logger.warning(f"⚠️ Symbol {symbol} is unavailable for trading (delisted or reduce-only): {e}")

                    # Clean up: Delete position from DB if it was created
                    if position_id:
                        try:
                            await self.repository.update_position(position_id, **{
                                'status': 'canceled',
                                'exit_reason': 'Symbol unavailable for trading'
                            })
                        except:
                            pass  # Ignore cleanup errors

                    # Raise specific exception for unavailable symbols
                    raise SymbolUnavailableError(f"Symbol {symbol} unavailable for trading on {exchange}")

                logger.error(f"❌ Atomic position creation failed: {e}")

                # CRITICAL: Rollback logic for other errors
                await self._rollback_position(
                    position_id=position_id,
                    entry_order=entry_order,
                    symbol=symbol,
                    exchange=exchange,
                    state=state,
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
                        # Закрываем market ордером
                        # entry_order теперь NormalizedOrder
                        close_side = 'sell' if entry_order.side == 'buy' else 'buy'
                        close_order = await exchange_instance.create_market_order(
                            symbol, close_side, entry_order.filled
                        )
                        logger.info(f"✅ Emergency close executed: {close_order.id}")
                    except Exception as close_error:
                        logger.critical(f"❌ FAILED to close unprotected position: {close_error}")
                        # TODO: Send alert to administrator

            # Обновляем статус в БД
            if position_id:
                # FIX: update_position expects **kwargs, not dict as second argument
                await self.repository.update_position(position_id, **{
                    'status': PositionState.ROLLED_BACK.value,
                    'closed_at': datetime.utcnow(),  # FIX: Use offset-naive datetime for database compatibility
                    'exit_reason': f'rollback: {error}'
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
                        'exit_reason': 'incomplete: entry not placed'
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
                    'exit_reason': 'emergency: no stop loss',
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