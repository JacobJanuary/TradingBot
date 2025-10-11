"""
Transactional Repository - Обеспечивает атомарность операций через транзакции

CRITICAL: Этот модуль гарантирует consistency базы данных
⚠️ Все критические операции должны использовать транзакции!
"""
import asyncpg
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TransactionalRepository:
    """
    Расширение Repository с поддержкой транзакций

    Features:
    - ACID compliance через BEGIN/COMMIT/ROLLBACK
    - Nested transactions (savepoints)
    - Automatic rollback on error
    - Transaction logging
    """

    def __init__(self, repository):
        """
        Args:
            repository: Базовый Repository с pool
        """
        self.repository = repository
        self.pool = repository.pool
        self._transaction_count = 0
        self._active_transactions = {}

    @asynccontextmanager
    async def transaction(self, name: str = None):
        """
        Контекстный менеджер для транзакций

        Usage:
            async with repo.transaction("create_position"):
                await repo.insert_position(...)
                await repo.insert_order(...)
                # Commit происходит автоматически при успехе
                # Rollback при любом исключении
        """
        transaction_id = f"tx_{self._transaction_count}_{name or 'unnamed'}"
        self._transaction_count += 1

        conn = None
        trans = None

        try:
            # Получаем connection из pool
            conn = await self.pool.acquire()

            # Начинаем транзакцию
            trans = conn.transaction()
            await trans.start()

            self._active_transactions[transaction_id] = {
                'name': name,
                'started_at': datetime.now(timezone.utc),
                'connection': conn
            }

            logger.info(f"🔄 Transaction started: {transaction_id}")

            # Yield connection для использования
            yield conn

            # Commit если все успешно
            await trans.commit()
            logger.info(f"✅ Transaction committed: {transaction_id}")

        except Exception as e:
            # Rollback при ошибке
            if trans:
                try:
                    await trans.rollback()
                    logger.error(f"❌ Transaction rolled back: {transaction_id} - {e}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback {transaction_id}: {rollback_error}")
            raise

        finally:
            # Cleanup
            if transaction_id in self._active_transactions:
                del self._active_transactions[transaction_id]

            # Возвращаем connection в pool
            if conn:
                await self.pool.release(conn)

    @asynccontextmanager
    async def savepoint(self, conn: asyncpg.Connection, name: str):
        """
        Nested transaction через savepoint

        Usage:
            async with repo.transaction() as conn:
                # ... some operations ...
                async with repo.savepoint(conn, "critical_section"):
                    # ... critical operations ...
                    # Rollback только до savepoint при ошибке
        """
        sp_name = f"sp_{name}_{self._transaction_count}"

        try:
            # Create savepoint
            await conn.execute(f"SAVEPOINT {sp_name}")
            logger.debug(f"Savepoint created: {sp_name}")

            yield

            # Release savepoint on success
            await conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            logger.debug(f"Savepoint released: {sp_name}")

        except Exception as e:
            # Rollback to savepoint
            try:
                await conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                logger.warning(f"Rolled back to savepoint: {sp_name} - {e}")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback to {sp_name}: {rollback_error}")
            raise

    # Atomic operations с транзакциями

    async def create_position_with_orders_atomic(
        self,
        position_data: Dict[str, Any],
        entry_order_data: Dict[str, Any],
        stop_loss_order_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Атомарное создание позиции с ордерами

        Гарантирует:
        - Позиция создается вместе с ордерами
        - При ошибке откатывается все
        - Невозможна позиция без стоп-лосса
        """
        async with self.transaction("create_position_atomic") as conn:
            # Insert position
            position_query = """
                INSERT INTO positions (
                    signal_id, symbol, exchange, side, quantity,
                    entry_price, stop_loss_price, stop_loss_order_id,
                    has_stop_loss, status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
            """

            position_id = await conn.fetchval(
                position_query,
                position_data['signal_id'],
                position_data['symbol'],
                position_data['exchange'],
                position_data['side'],
                position_data['quantity'],
                position_data['entry_price'],
                position_data['stop_loss_price'],
                position_data.get('stop_loss_order_id'),
                True,  # has_stop_loss always True
                position_data.get('status', 'PENDING_ENTRY'),
                datetime.now(timezone.utc)
            )

            # Insert entry order
            entry_order_data['position_id'] = position_id
            await self._insert_order(conn, entry_order_data)

            # Insert stop-loss order
            stop_loss_order_data['position_id'] = position_id
            await self._insert_order(conn, stop_loss_order_data)

            logger.info(f"✅ Atomic position created: ID={position_id}")

            return {
                'position_id': position_id,
                'entry_order_id': entry_order_data.get('exchange_order_id'),
                'stop_loss_order_id': stop_loss_order_data.get('exchange_order_id')
            }

    async def update_position_status_atomic(
        self,
        position_id: int,
        new_status: str,
        updates: Dict[str, Any] = None
    ):
        """
        Атомарное обновление статуса позиции
        """
        async with self.transaction(f"update_position_{position_id}") as conn:
            # Update position
            query = """
                UPDATE positions
                SET status = $1, updated_at = $2
                WHERE id = $3
            """

            await conn.execute(
                query,
                new_status,
                datetime.now(timezone.utc),
                position_id
            )

            # Additional updates if provided
            if updates:
                for field, value in updates.items():
                    update_query = f"UPDATE positions SET {field} = $1 WHERE id = $2"
                    await conn.execute(update_query, value, position_id)

            logger.info(f"Position {position_id} status updated to {new_status}")

    async def _insert_order(self, conn: asyncpg.Connection, order_data: Dict[str, Any]):
        """Helper для вставки ордера в транзакции"""
        query = """
            INSERT INTO orders (
                position_id, exchange_order_id, symbol, exchange,
                side, order_type, quantity, price, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """

        await conn.execute(
            query,
            order_data['position_id'],
            order_data.get('exchange_order_id'),
            order_data['symbol'],
            order_data['exchange'],
            order_data['side'],
            order_data['order_type'],
            order_data['quantity'],
            order_data.get('price'),
            order_data.get('status', 'NEW'),
            datetime.now(timezone.utc)
        )

    def get_active_transaction_count(self) -> int:
        """Получить количество активных транзакций"""
        return len(self._active_transactions)

    def get_transaction_stats(self) -> Dict[str, Any]:
        """Статистика транзакций"""
        return {
            'total_transactions': self._transaction_count,
            'active_transactions': len(self._active_transactions),
            'active_details': [
                {
                    'id': tx_id,
                    'name': info['name'],
                    'duration': (datetime.now(timezone.utc) - info['started_at']).total_seconds()
                }
                for tx_id, info in self._active_transactions.items()
            ]
        }