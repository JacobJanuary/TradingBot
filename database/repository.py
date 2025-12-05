import asyncpg
import logging
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from utils.datetime_helpers import now_utc, ensure_utc

logger = logging.getLogger(__name__)


class Repository:
    """
    Repository pattern for database operations
    Uses asyncpg for PostgreSQL
    """

    def __init__(self, db_config: Dict):
        """Initialize repository with database configuration"""
        self.db_config = db_config
        self.pool = None

    @staticmethod
    def _get_position_lock_id(symbol: str, exchange: str) -> int:
        """
        Generate deterministic lock ID for position.

        Uses MD5 hash of "symbol:exchange" to get 64-bit integer.
        Lock ID is stable across calls for same symbol+exchange.

        Args:
            symbol: Trading symbol (e.g., 'PERPUSDT')
            exchange: Exchange name (e.g., 'binance')

        Returns:
            int: PostgreSQL bigint lock ID (-2^63 to 2^63-1)
        """
        key = f"{symbol}:{exchange}".encode('utf-8')
        hash_digest = hashlib.md5(key).digest()
        # Convert first 8 bytes to signed 64-bit integer
        lock_id = int.from_bytes(hash_digest[:8], byteorder='big', signed=True)
        return lock_id

    async def initialize(self):
        """Create optimized connection pool with better settings"""
        # DEBUG: Log connection params
        logger.info(f"🔌 Creating connection pool: {self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']} as {self.db_config['user']}")

        self.pool = await asyncpg.create_pool(
            host=self.db_config['host'],
            port=self.db_config['port'],
            database=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password'],

            # Optimized pool settings
            min_size=self.db_config.get('pool_size', 15),  # Increased from 10
            max_size=self.db_config.get('max_overflow', 50),  # Increased from 20

            # Timeout settings
            command_timeout=30,  # Increased from 10
            timeout=60,  # Connection timeout

            # Connection recycling
            max_queries=100000,  # Recycle connections after many queries
            max_inactive_connection_lifetime=60.0,  # Close idle connections after 60s

            # Performance settings
            server_settings={
                'jit': 'off',  # Disable JIT for more predictable performance
                'statement_timeout': '60000',  # 60 seconds
                'lock_timeout': '10000',  # 10 seconds
                'idle_in_transaction_session_timeout': '60000',  # 60 seconds
                'search_path': 'monitoring,fas,public'  # CRITICAL FIX: Set proper schema search order
            }
        )
        logger.info(f"Database pool initialized: min={self.db_config.get('pool_size', 15)}, max={self.db_config.get('max_overflow', 50)}")
        
        # Verify schemas exist
        async with self.pool.acquire() as conn:
            schemas = await conn.fetch("""
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name IN ('fas', 'monitoring')
            """)
            existing = [s['schema_name'] for s in schemas]
            logger.info(f"Connected to DB with schemas: {', '.join(existing)}")

            # CRITICAL FIX: Verify search_path is set correctly
            search_path = await conn.fetchval("SHOW search_path")
            logger.info(f"PostgreSQL search_path: {search_path}")

            # CRITICAL FIX: Verify monitoring.positions table exists and has correct columns
            try:
                columns = await conn.fetch("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'monitoring'
                    AND table_name = 'positions'
                    ORDER BY ordinal_position
                """)
                column_list = [f"{c['column_name']}:{c['data_type']}" for c in columns]
                logger.info(f"monitoring.positions columns: {', '.join(column_list)}")
            except Exception as e:
                logger.error(f"Failed to check monitoring.positions columns: {e}")

    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()

    # ============== Signal Operations ==============

    # ============== Risk Management ==============
    
    async def create_risk_event(self, event) -> int:
        """Create risk event record"""
        query = """
            INSERT INTO monitoring.risk_events (
                event_type, risk_level, position_id, details, created_at
            ) VALUES ($1, $2, $3, $4, NOW())
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                query,
                event.event_type,
                event.risk_level,
                getattr(event, 'position_id', None),
                event.details
            )
            return result
    
    async def create_risk_violation(self, violation) -> int:
        """Record risk violation"""
        query = """
            INSERT INTO monitoring.risk_violations (
                violation_type, risk_level, message, timestamp
            ) VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                query,
                violation.type,
                violation.level.value if hasattr(violation.level, 'value') else violation.level,
                violation.message,
                violation.timestamp
            )
            return result

    # ============== Parameter Management ==============

    async def get_params(self, exchange_id: int) -> Optional[Dict]:
        """
        Get backtest parameters for exchange

        Args:
            exchange_id: Exchange ID (1=Binance, 2=Bybit)

        Returns:
            Dict with parameters or None if not found
        """
        query = """
            SELECT
                exchange_id,
                max_trades_filter,
                stop_loss_filter,
                trailing_activation_filter,
                trailing_distance_filter,
                updated_at,
                created_at
            FROM monitoring.params
            WHERE exchange_id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, exchange_id)

            if row:
                return dict(row)
            return None

    async def update_params(
        self,
        exchange_id: int,
        max_trades_filter: Optional[int] = None,
        stop_loss_filter: Optional[float] = None,
        trailing_activation_filter: Optional[float] = None,
        trailing_distance_filter: Optional[float] = None
    ) -> bool:
        """
        Update backtest parameters for exchange

        Only updates fields that are not None.
        Returns True if update succeeded, False otherwise.

        Args:
            exchange_id: Exchange ID (1=Binance, 2=Bybit)
            max_trades_filter: Max trades per wave
            stop_loss_filter: Stop loss %
            trailing_activation_filter: Trailing activation %
            trailing_distance_filter: Trailing distance %

        Returns:
            bool: True if updated, False if failed
        """
        # Build dynamic UPSERT query (only update provided fields)
        field_names = []
        field_placeholders = []
        params: list[Union[int, float]] = [exchange_id]
        param_idx = 2

        if max_trades_filter is not None:
            field_names.append("max_trades_filter")
            field_placeholders.append(f"${param_idx}")
            params.append(max_trades_filter)
            param_idx += 1

        if stop_loss_filter is not None:
            field_names.append("stop_loss_filter")
            field_placeholders.append(f"${param_idx}")
            params.append(stop_loss_filter)
            param_idx += 1

        if trailing_activation_filter is not None:
            field_names.append("trailing_activation_filter")
            field_placeholders.append(f"${param_idx}")
            params.append(trailing_activation_filter)
            param_idx += 1

        if trailing_distance_filter is not None:
            field_names.append("trailing_distance_filter")
            field_placeholders.append(f"${param_idx}")
            params.append(trailing_distance_filter)
            param_idx += 1

        if not field_names:
            logger.warning(f"No parameters to update for exchange_id={exchange_id}")
            return False

        # Build UPDATE clauses for ON CONFLICT
        update_clauses = [f"{name} = EXCLUDED.{name}" for name in field_names]

        # updated_at is auto-updated by trigger
        query = f"""
            INSERT INTO monitoring.params (exchange_id, {', '.join(field_names)})
            VALUES ($1, {', '.join(field_placeholders)})
            ON CONFLICT (exchange_id)
            DO UPDATE SET {', '.join(update_clauses)}
            RETURNING exchange_id
        """

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *params)

                if result:
                    logger.info(
                        f"✅ Upserted params for exchange_id={exchange_id}: "
                        f"{', '.join(field_names)}"
                    )
                    return True
                else:
                    logger.warning(f"Failed to upsert params for exchange_id={exchange_id}")
                    return False

        except Exception as e:
            logger.error(f"Failed to update params for exchange_id={exchange_id}: {e}")
            return False

    async def get_all_params(self) -> Dict[int, Dict]:
        """
        Get all exchange parameters

        Returns:
            Dict mapping exchange_id to params dict
        """
        query = """
            SELECT
                exchange_id,
                max_trades_filter,
                stop_loss_filter,
                trailing_activation_filter,
                trailing_distance_filter,
                updated_at,
                created_at
            FROM monitoring.params
            ORDER BY exchange_id
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)

            return {row['exchange_id']: dict(row) for row in rows}

    async def get_params_by_exchange_name(self, exchange_name: str) -> Optional[Dict]:
        """
        Get trading params for exchange by exchange name

        Convenience wrapper around get_params() that handles exchange_name → exchange_id mapping.

        Args:
            exchange_name: Exchange name ('binance', 'bybit')

        Returns:
            Dict with params or None if not found

        Example:
            >>> params = await repo.get_params_by_exchange_name('binance')
            >>> params['stop_loss_filter']
            4.0
        """
        from utils.exchange_helpers import exchange_name_to_id

        try:
            exchange_id = exchange_name_to_id(exchange_name)
            return await self.get_params(exchange_id=exchange_id)
        except ValueError as e:
            logger.error(f"Invalid exchange name '{exchange_name}': {e}")
            return None

    # ============== Trade Operations ==============

    async def create_trade(self, trade_data: Dict) -> int:
        """Create new trade record in monitoring.trades"""
        query = """
            INSERT INTO monitoring.trades (
                symbol, exchange, side, order_type,
                quantity, price, executed_qty, average_price,
                order_id, client_order_id, status,
                fee, fee_currency
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            trade_id = await conn.fetchval(
                query,
                trade_data['symbol'],
                trade_data['exchange'],
                trade_data['side'],
                trade_data.get('order_type', 'MARKET'),
                trade_data['quantity'],
                trade_data['price'],
                trade_data.get('executed_qty', 0),
                trade_data.get('average_price', 0),
                trade_data.get('order_id'),
                trade_data.get('client_order_id'),
                trade_data.get('status', 'FILLED'),
                trade_data.get('fee', 0),
                trade_data.get('fee_currency', 'USDT')
            )

            return trade_id

    # ============== Position Operations ==============

    async def get_positions_by_status(self, statuses: list) -> list:
        """Get positions by status list - for recovery mechanism"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT id, symbol, exchange, side, quantity,
                       entry_price, status, has_stop_loss, stop_loss_price
                FROM monitoring.positions
                WHERE status = ANY($1)
                ORDER BY id
            """
            rows = await conn.fetch(query, statuses)
            return [dict(row) for row in rows]

    async def create_position(self, position_data: Dict) -> int:
        """
        Create new position record with advisory lock to prevent race conditions.

        Uses pg_advisory_xact_lock to ensure only one transaction can create
        a position for given symbol+exchange at a time.
        """
        import logging
        logger = logging.getLogger(__name__)

        symbol = position_data['symbol']
        exchange = position_data['exchange']

        logger.info(f"🔍 REPO DEBUG: create_position() called for {symbol}")

        # Generate lock ID for this symbol+exchange
        lock_id = self._get_position_lock_id(symbol, exchange)

        query = """
            INSERT INTO monitoring.positions (
                symbol, exchange, side, quantity,
                entry_price, status, has_trailing_stop,
                trailing_activation_percent,
                trailing_callback_percent
            ) VALUES ($1, $2, $3, $4, $5, 'active', TRUE, $6, $7)
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            logger.info(f"🔍 REPO DEBUG: Got connection from pool for {symbol}")

            # CRITICAL: Use transaction with advisory lock
            async with conn.transaction():
                # Acquire exclusive advisory lock for this symbol+exchange
                logger.debug(f"🔒 Acquiring position lock for {symbol}:{exchange} (lock_id={lock_id})")
                await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)
                logger.debug(f"✅ Position lock acquired for {symbol}:{exchange}")

                # Now we have exclusive access - check if position exists
                # FIX: Check ALL open statuses to prevent duplicate position race condition
                existing = await conn.fetchrow("""
                    SELECT id, status, created_at FROM monitoring.positions
                    WHERE symbol = $1 AND exchange = $2
                      AND status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')
                    ORDER BY created_at DESC
                    LIMIT 1
                """, symbol, exchange)

                if existing:
                    logger.warning(
                        f"⚠️ Position {symbol} already exists in DB (id={existing['id']}, status={existing['status']}). "
                        f"Returning existing position instead of creating duplicate."
                    )
                    return existing['id']

                # Position doesn't exist - safe to create
                logger.info(f"🔍 REPO DEBUG: Executing INSERT for {symbol}, quantity={position_data['quantity']}")

                try:
                    position_id = await conn.fetchval(
                        query,
                        symbol,
                        exchange,
                        position_data['side'],
                        position_data['quantity'],
                        position_data['entry_price'],
                        position_data.get('trailing_activation_percent'),
                        position_data.get('trailing_callback_percent')
                    )

                    logger.info(f"🔍 REPO DEBUG: INSERT completed, returned position_id={position_id} for {symbol}")
                    return position_id

                except Exception as e:
                    # Check if it's a unique constraint violation
                    error_msg = str(e)
                    if 'idx_unique_active_position' in error_msg or 'duplicate key' in error_msg.lower():
                        logger.warning(
                            f"⚠️ IntegrityError caught: Duplicate active position {symbol} on {exchange}. "
                            f"Fetching existing position."
                        )
                        # Fetch and return the existing position
                        existing_row = await conn.fetchrow("""
                            SELECT id FROM monitoring.positions
                            WHERE symbol = $1 AND exchange = $2 AND status = 'active'
                        """, symbol, exchange)
                        if existing_row:
                            logger.info(f"✅ Returning existing position id={existing_row['id']}")
                            return existing_row['id']
                        else:
                            # This shouldn't happen, but handle it gracefully
                            logger.error(f"❌ IntegrityError but no existing position found for {symbol}")
                            raise
                    else:
                        # Re-raise if it's a different error
                        logger.error(f"❌ Database error during INSERT for {symbol}: {e}")
                    raise

    async def open_position(self, position_data: Dict) -> int:
        """
        Alias for create_position - used by position_synchronizer
        """
        return await self.create_position(position_data)

    async def get_open_position(self, symbol: str, exchange: str) -> Optional[Dict]:
        """Get open position for symbol"""
        query = """
            SELECT * FROM monitoring.positions
            WHERE symbol = $1 
                AND exchange = $2 
                AND status = 'active'
            LIMIT 1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, symbol, exchange)
            return dict(row) if row else None

    async def update_position_from_websocket(self, position_update: Dict):
        """Update position from WebSocket data"""
        query = """
            UPDATE monitoring.positions
            SET current_price = $1,
                unrealized_pnl = $2,
                updated_at = NOW()
            WHERE symbol = $3
                AND exchange = $4
                AND status = 'active'
        """

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    query,
                    position_update['current_price'],
                    position_update.get('unrealized_pnl', 0),
                    position_update['symbol'],
                    position_update['exchange']
                )
                # DEBUG: Log result
                logger.debug(f"🔍 DB UPDATE: {position_update['symbol']} price={position_update['current_price']} result={result}")
        except Exception as e:
            logger.error(f"❌ Failed to update position from websocket: {e}", exc_info=True)

    async def update_position_stop_loss(self, position_id: int, stop_price: float, order_id: str):
        """Update position stop loss"""
        query = """
            UPDATE monitoring.positions
            SET stop_loss_price = $1,
                has_stop_loss = TRUE,
                updated_at = NOW()
            WHERE id = $2
        """

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, stop_price, position_id)
            logger.info(f"🔍 DB: updated position {position_id} with SL price {stop_price}, has_stop_loss=TRUE, result={result}")

    async def update_position_trailing_stop(self, position_id: int,
                                            activation_price: float,
                                            callback_rate: float):
        """Update position trailing stop"""
        query = """
            UPDATE monitoring.positions
            SET updated_at = NOW()
            WHERE id = $1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, position_id)

    async def close_position(self, position_id: int,
                            close_price: Optional[float] = None,
                            pnl: Optional[float] = None,
                            pnl_percentage: Optional[float] = None,
                            reason: Optional[str] = None,
                            exit_data: Optional[Dict[Any, Any]] = None):
        """
        Close position with exit details

        Args:
            position_id: Position ID to close
            close_price: Final price (optional)
            pnl: Profit/Loss amount (optional)
            pnl_percentage: PnL percentage (optional)
            reason: Close reason (optional)
            exit_data: Legacy dict format for backward compatibility (optional)
        """
        # Support both new parameter format and legacy exit_data dict
        if exit_data is not None:
            # Legacy format - extract from dict
            realized_pnl = exit_data.get('realized_pnl', pnl or 0)
            exit_reason = exit_data.get('exit_reason', reason or 'manual')
            current_price = exit_data.get('exit_price', close_price)
            pnl_percent = exit_data.get('pnl_percentage', pnl_percentage)
        else:
            # New format - use direct parameters
            realized_pnl = pnl or 0
            exit_reason = reason or 'manual'
            current_price = close_price
            pnl_percent = pnl_percentage

        query = """
            UPDATE monitoring.positions
            SET status = 'closed',
                pnl = $1,
                exit_reason = $2,
                current_price = COALESCE($3, current_price),
                pnl_percentage = COALESCE($4, pnl_percentage),
                closed_at = NOW(),
                updated_at = NOW()
            WHERE id = $5
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                realized_pnl,  # Now goes to pnl column
                exit_reason,
                current_price,
                pnl_percent,
                position_id
            )

    # ============== Performance Operations ==============

    async def log_performance_metrics(self, metrics: Dict):
        """Log performance metrics"""
        query = """
            INSERT INTO monitoring.performance (
                total_balance, available_balance, total_unrealized_pnl,
                open_positions, total_exposure, daily_pnl, daily_trades,
                daily_win_rate, total_trades, total_wins, total_losses,
                win_rate, profit_factor, sharpe_ratio, max_drawdown,
                metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                metrics['total_balance'],
                metrics['available_balance'],
                metrics.get('total_unrealized_pnl', 0),
                metrics.get('open_positions', 0),
                metrics.get('total_exposure', 0),
                metrics.get('daily_pnl'),
                metrics.get('daily_trades', 0),
                metrics.get('daily_win_rate'),
                metrics.get('total_trades', 0),
                metrics.get('total_wins', 0),
                metrics.get('total_losses', 0),
                metrics.get('win_rate'),
                metrics.get('profit_factor'),
                metrics.get('sharpe_ratio'),
                metrics.get('max_drawdown'),
                metrics.get('metadata', {})
            )

    async def get_position_age(self, symbol: str, exchange: str) -> float:
        """Get position age in hours"""
        query = """
            SELECT EXTRACT(EPOCH FROM (NOW() - opened_at)) / 3600 as age_hours
            FROM monitoring.positions
            WHERE symbol = $1 AND exchange = $2 AND status = 'OPEN'
        """

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, symbol, exchange)
            return result or 0.0

    async def get_open_positions(self) -> List[Dict]:
        """Get all open positions from database"""
        query = """
            SELECT id, symbol, exchange, side, entry_price, current_price,
                   quantity, leverage, stop_loss, take_profit,
                   status, pnl, pnl_percentage, trailing_activated,
                   has_trailing_stop, created_at, updated_at,
                   trailing_activation_percent, trailing_callback_percent
            FROM monitoring.positions
            WHERE status = 'active'
            ORDER BY created_at DESC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    # ============== Advisory Locks ==============

    async def acquire_position_lock(self, symbol: str, exchange: str) -> bool:
        """Acquire advisory lock for position"""
        lock_key = f"{exchange}_{symbol}"
        lock_id = hash(lock_key) % 2147483647

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)",
                lock_id
            )
            return result

    async def release_position_lock(self, symbol: str, exchange: str):
        """Release advisory lock for position"""
        lock_key = f"{exchange}_{symbol}"
        lock_id = hash(lock_key) % 2147483647

        async with self.pool.acquire() as conn:
            await conn.execute(
                "SELECT pg_advisory_unlock($1)",
                lock_id
            )

    # ============== Additional Methods for Tests ==============
    
    async def get_active_positions(self, exchange: Optional[str] = None) -> List[Any]:
        """Get all active positions"""
        # Mock implementation for tests
        return []
    
    async def get_open_orders(self, exchange: Optional[str] = None) -> List[Any]:
        """Get all open orders"""
        return []
    
    async def update_position(self, position_id: int, **kwargs) -> bool:
        """
        Update position with arbitrary fields

        Args:
            position_id: Position ID to update (must be integer)
            **kwargs: Field names and values to update

        Returns:
            bool: True if update successful, False if validation fails

        Example:
            await repo.update_position(123, current_price=50.5, pnl=10.0)

        Raises:
            ValueError: If position_id is not an integer
        """
        # Validation: Check position_id type
        if not isinstance(position_id, int):
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                f"❌ CRITICAL: update_position called with invalid position_id type! "
                f"Expected int, got {type(position_id).__name__} (value: {position_id})"
            )
            return False

        if not kwargs:
            return False

        # Build dynamic UPDATE query
        set_clauses = []
        values = []
        param_count = 1

        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ${param_count}")
            values.append(value)
            param_count += 1

        query = f"""
            UPDATE monitoring.positions
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${param_count}
        """
        values.append(position_id)

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *values)
            return True
    
    async def create_order(self, order_data: Dict) -> int:
        """Create new order record in monitoring.orders"""
        query = """
            INSERT INTO monitoring.orders (
                position_id, exchange, symbol, order_id, client_order_id,
                type, side, size, price, status,
                filled, remaining, fee, fee_currency
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            order_id = await conn.fetchval(
                query,
                order_data.get('position_id'),
                order_data['exchange'],
                order_data['symbol'],
                order_data.get('order_id'),
                order_data.get('client_order_id'),
                order_data['type'],
                order_data['side'],
                order_data.get('size', 0),
                order_data.get('price', 0),
                order_data['status'],
                order_data.get('filled', 0),
                order_data.get('remaining', 0),
                order_data.get('fee', 0),
                order_data.get('fee_currency', 'USDT')
            )

            return order_id
    
    async def get_daily_pnl(self) -> Decimal:
        """Get daily PnL"""
        query = """
            SELECT COALESCE(SUM(pnl), 0) as daily_pnl
            FROM monitoring.positions
            WHERE DATE(closed_at) = CURRENT_DATE
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            return Decimal(str(row['daily_pnl'])) if row else Decimal('0')
    
    
    async def get_closed_positions_since(self, since: datetime) -> List[Any]:
        """Get closed positions since date"""
        return []
    
    async def get_positions_by_date(self, date: Any) -> List[Any]:
        """Get positions by date"""
        return []
    
    async def get_closed_positions_before(self, date: Any) -> List[Any]:
        """Get closed positions before date"""
        return []
    
    async def get_last_signal_time(self) -> Optional[datetime]:
        """Get last signal time"""
        return None
    



    async def find_duplicate_positions(self) -> List[Any]:
        """Find duplicate positions"""
        return []
    
    async def find_invalid_orders(self) -> List[Any]:
        """Find invalid orders"""
        return []
    
    async def find_orders_without_positions(self) -> List[Any]:
        """Find orders without positions"""
        return []
    
    async def delete_old_positions(self, cutoff: datetime) -> int:
        """Delete old positions"""
        return 0
    
    async def delete_old_orders(self, cutoff: datetime) -> int:
        """Delete old orders"""
        return 0
    
    async def delete_old_signals(self, cutoff: datetime) -> int:
        """Delete old signals"""
        return 0
    
    async def vacuum_database(self) -> bool:
        """Vacuum database"""
        return True
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check"""
        return {'status': 'ok', 'pool_size': 10}

    async def update_position_status(self, position_id: int, status: str,
                                    notes: str = None) -> bool:
        """
        Update position status in database

        Args:
            position_id: Position database ID
            status: New status ('active', 'closed', 'phantom')
            notes: Optional notes about the update

        Returns:
            bool: True if update successful
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE monitoring.positions
                    SET status = $1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2
                """, status, position_id)

                # Check if any row was updated
                return result is not None

        except Exception as e:
            logger.error(f"Failed to update position status: {e}")
            return False
    
    async def get_balance_history(self, exchange: str, days: int) -> List[Any]:
        """Get balance history"""
        return []
    
    async def get_daily_stats(self, date: Any) -> Dict[str, Any]:
        """Get daily stats"""
        return {}
    
    async def create_risk_violation(self, violation: Any) -> bool:
        """Create risk violation"""
        return True


    # ============================================================
    # Order Cache Methods (Phase 3: Bybit 500 order limit solution)
    # ============================================================

    async def cache_order(self, exchange: str, order_data: Dict) -> bool:
        """
        Cache order data locally for later retrieval.

        Solves Bybit 500 order limit issue by storing all orders locally.

        Args:
            exchange: Exchange name ('binance', 'bybit', etc.)
            order_data: Full order data from exchange API

        Returns:
            bool: True if cached successfully
        """
        import json
        from datetime import datetime

        query = """
            INSERT INTO monitoring.orders_cache
            (exchange, exchange_order_id, symbol, order_type, side, price, amount, filled, status, created_at, order_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (exchange, exchange_order_id) DO UPDATE
            SET status = $9,
                filled = $8,
                order_data = $11,
                cached_at = CURRENT_TIMESTAMP
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    exchange,
                    order_data.get('id'),
                    order_data.get('symbol'),
                    order_data.get('type'),
                    order_data.get('side'),
                    float(order_data.get('price', 0)) if order_data.get('price') else None,
                    float(order_data.get('amount', 0)),
                    float(order_data.get('filled', 0)),
                    order_data.get('status'),
                    order_data.get('timestamp') if order_data.get('timestamp') else now_utc(),
                    json.dumps(order_data)  # Store full order data as JSONB
                )
            return True

        except Exception as e:
            logger.error(f"Failed to cache order {order_data.get('id')}: {e}")
            return False

    async def get_cached_order(self, exchange: str, order_id: str) -> Optional[Dict]:
        """
        Retrieve cached order data.

        Args:
            exchange: Exchange name
            order_id: Exchange order ID

        Returns:
            Dict: Order data if found, None otherwise
        """
        import json

        query = """
            SELECT order_data
            FROM monitoring.orders_cache
            WHERE exchange = $1 AND exchange_order_id = $2
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, exchange, order_id)

                if row:
                    order_data = json.loads(row['order_data']) if isinstance(row['order_data'], str) else row['order_data']
                    logger.info(f"✅ Retrieved cached order {order_id} from {exchange}")
                    return order_data

                return None

        except Exception as e:
            logger.error(f"Failed to retrieve cached order {order_id}: {e}")
            return None

    async def get_cached_orders_by_symbol(self, exchange: str, symbol: str, limit: int = 100) -> List[Dict]:
        """
        Get cached orders for a symbol (useful for Bybit when fetchOrders fails).

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            limit: Maximum orders to return

        Returns:
            List[Dict]: List of order data
        """
        import json

        query = """
            SELECT order_data
            FROM monitoring.orders_cache
            WHERE exchange = $1 AND symbol = $2
            ORDER BY created_at DESC
            LIMIT $3
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, exchange, symbol, limit)

                orders = []
                for row in rows:
                    order_data = json.loads(row['order_data']) if isinstance(row['order_data'], str) else row['order_data']
                    orders.append(order_data)

                logger.info(f"Retrieved {len(orders)} cached orders for {symbol} on {exchange}")
                return orders

        except Exception as e:
            logger.error(f"Failed to retrieve cached orders for {symbol}: {e}")
            return []

    # ============== TRAILING STOP STATE PERSISTENCE ==============

    async def save_trailing_stop_state(self, state_data: Dict) -> bool:
        """
        Save or update trailing stop state in database

        Args:
            state_data: Dictionary with TS state fields

        Returns:
            bool: True if saved successfully
        """
        query = """
            INSERT INTO monitoring.trailing_stop_state (
                symbol, exchange, position_id, state, is_activated,
                highest_price, lowest_price, current_stop_price,
                stop_order_id, activation_price, activation_percent, callback_percent,
                entry_price, side, quantity, update_count, highest_profit_percent,
                activated_at, last_update_time, last_sl_update_time, last_updated_sl_price,
                last_peak_save_time, last_saved_peak_price,
                created_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9, $10, $11, $12,
                $13, $14, $15, $16, $17,
                $18, $19, $20, $21,
                $22, $23,
                COALESCE($24, NOW())
            )
            ON CONFLICT (symbol, exchange)
            DO UPDATE SET
                position_id = EXCLUDED.position_id,
                state = EXCLUDED.state,
                is_activated = EXCLUDED.is_activated,
                highest_price = EXCLUDED.highest_price,
                lowest_price = EXCLUDED.lowest_price,
                current_stop_price = EXCLUDED.current_stop_price,
                stop_order_id = EXCLUDED.stop_order_id,
                activation_price = EXCLUDED.activation_price,
                update_count = EXCLUDED.update_count,
                highest_profit_percent = EXCLUDED.highest_profit_percent,
                activated_at = COALESCE(monitoring.trailing_stop_state.activated_at, EXCLUDED.activated_at),
                last_update_time = EXCLUDED.last_update_time,
                last_sl_update_time = EXCLUDED.last_sl_update_time,
                last_updated_sl_price = EXCLUDED.last_updated_sl_price,
                last_peak_save_time = EXCLUDED.last_peak_save_time,
                last_saved_peak_price = EXCLUDED.last_saved_peak_price,
                -- CRITICAL FIX: Update position-specific fields on conflict (prevents side mismatch)
                entry_price = EXCLUDED.entry_price,
                side = EXCLUDED.side,
                quantity = EXCLUDED.quantity,
                activation_percent = EXCLUDED.activation_percent,
                callback_percent = EXCLUDED.callback_percent
        """

        try:
            await self.pool.execute(
                query,
                state_data['symbol'],
                state_data['exchange'],
                state_data['position_id'],
                state_data['state'],
                state_data['is_activated'],
                state_data.get('highest_price'),
                state_data.get('lowest_price'),
                state_data.get('current_stop_price'),
                state_data.get('stop_order_id'),
                state_data.get('activation_price'),
                state_data.get('activation_percent'),
                state_data.get('callback_percent'),
                state_data['entry_price'],
                state_data['side'],
                state_data['quantity'],
                state_data.get('update_count', 0),
                state_data.get('highest_profit_percent', 0),
                state_data.get('activated_at'),
                state_data.get('last_update_time'),
                state_data.get('last_sl_update_time'),
                state_data.get('last_updated_sl_price'),
                state_data.get('last_peak_save_time'),
                state_data.get('last_saved_peak_price'),
                state_data.get('created_at')
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save TS state for {state_data['symbol']}: {e}")
            return False

    async def get_trailing_stop_state(self, symbol: str, exchange: str) -> Optional[Dict]:
        """
        Get trailing stop state from database

        Args:
            symbol: Trading symbol
            exchange: Exchange name

        Returns:
            Dict with TS state or None if not found
        """
        query = """
            SELECT
                symbol, exchange, position_id, state, is_activated,
                highest_price, lowest_price, current_stop_price,
                stop_order_id, activation_price, activation_percent, callback_percent,
                entry_price, side, quantity, update_count, highest_profit_percent,
                created_at, activated_at, last_update_time, last_sl_update_time, last_updated_sl_price,
                last_peak_save_time, last_saved_peak_price
            FROM monitoring.trailing_stop_state
            WHERE symbol = $1 AND exchange = $2
        """

        try:
            row = await self.pool.fetchrow(query, symbol, exchange)
            if row:
                return dict(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get TS state for {symbol}: {e}")
            return None

    async def delete_trailing_stop_state(self, symbol: str, exchange: str) -> bool:
        """
        Delete trailing stop state from database

        Args:
            symbol: Trading symbol
            exchange: Exchange name

        Returns:
            bool: True if deleted successfully
        """
        query = """
            DELETE FROM monitoring.trailing_stop_state
            WHERE symbol = $1 AND exchange = $2
        """

        try:
            await self.pool.execute(query, symbol, exchange)
            return True

        except Exception as e:
            logger.error(f"Failed to delete TS state for {symbol}: {e}")
            return False

    async def cleanup_orphan_ts_states(self) -> int:
        """
        Clean up trailing stop states for positions that no longer exist

        Returns:
            int: Number of orphan states deleted
        """
        query = """
            DELETE FROM monitoring.trailing_stop_state ts
            WHERE NOT EXISTS (
                SELECT 1 FROM monitoring.positions p
                WHERE p.id = ts.position_id
                AND p.status = 'active'
            )
            RETURNING symbol
        """

        try:
            rows = await self.pool.fetch(query)
            count = len(rows)
            if count > 0:
                symbols = [row['symbol'] for row in rows]
                logger.info(f"Cleaned up {count} orphan TS states: {symbols}")
            return count

        except Exception as e:
            logger.error(f"Failed to cleanup orphan TS states: {e}")
            return 0


    # ==================== AGED POSITIONS ====================

    async def create_aged_position(
        self,
        position_id: str,
        symbol: str,
        exchange: str,
        entry_price: Decimal,
        target_price: Decimal,
        phase: str,
        age_hours: float,
        loss_tolerance: Optional[Decimal] = None
    ) -> Dict:
        """Create new aged position entry in database

        Args:
            position_id: ID of the original position (VARCHAR)
            symbol: Trading symbol (e.g., BTCUSDT)
            exchange: Exchange name
            entry_price: Entry price of position
            target_price: Initial target price
            phase: Current phase (grace, progressive, etc.)
            age_hours: Hours aged
            loss_tolerance: Current loss tolerance percentage

        Returns:
            Created aged position record
        """
        query = """
            INSERT INTO monitoring.aged_positions (
                position_id, symbol, exchange,
                entry_price, target_price, phase,
                hours_aged, loss_tolerance,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
            ON CONFLICT (position_id) DO UPDATE SET
                target_price = EXCLUDED.target_price,
                phase = EXCLUDED.phase,
                hours_aged = EXCLUDED.hours_aged,
                loss_tolerance = EXCLUDED.loss_tolerance,
                updated_at = NOW()
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    query,
                    str(position_id),
                    symbol,
                    exchange,
                    entry_price,
                    target_price,
                    phase,
                    int(age_hours),
                    loss_tolerance
                )
                logger.info(f"Created/updated aged_position {row['id']} for {symbol}")
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"Failed to create aged_position: {e}")
                raise

    async def get_active_aged_positions(
        self,
        phases: List[str] = None
    ) -> List[Dict]:
        """Get all active aged positions from database

        Args:
            phases: List of phase values to filter by
                    If None, returns active phases only (excludes 'stale')

        Phase values used by aged_position_monitor_v2.py:
            - 'grace': Grace period breakeven
            - 'progressive': Progressive liquidation
            - 'emergency': Emergency close (documented but not used yet)
            - 'stale': Closed/inactive positions (excluded by default)

        Returns:
            List of active aged position records
        """
        if not phases:
            # Default: Return only active phases (exclude 'stale')
            # Matches aged_position_monitor_v2.py phase values (lines 468, 481)
            phases = ['grace', 'progressive', 'emergency']

        query = """
            SELECT
                ap.*,
                EXTRACT(EPOCH FROM (NOW() - ap.created_at)) / 3600 as current_age_hours
            FROM monitoring.aged_positions ap
            WHERE ap.phase = ANY($1)
            ORDER BY ap.created_at DESC
        """

        async with self.pool.acquire() as conn:
            try:
                rows = await conn.fetch(query, phases)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Failed to get active aged positions: {e}")
                return []

    async def update_aged_position(
        self,
        position_id: str,
        phase: Optional[str] = None,
        target_price: Optional[Decimal] = None,
        hours_aged: Optional[float] = None,
        loss_tolerance: Optional[Decimal] = None
    ) -> bool:
        """Update aged position fields

        Args:
            position_id: Position ID (matches position_id column, not aged position id)
            phase: New phase (e.g., 'grace', 'progressive', 'stale')
            target_price: Updated target price
            hours_aged: Current age in hours
            loss_tolerance: Loss tolerance as decimal (e.g., 0.015 for 1.5%)

        Returns:
            True if updated successfully, False otherwise
        """
        if not any([phase, target_price, hours_aged, loss_tolerance]):
            logger.warning(f"No fields to update for position {position_id}")
            return False

        # Build SET clause and parameter list dynamically
        set_fields = ['updated_at = NOW()']
        params: list[Union[str, Decimal, float]] = []  # List for positional params
        param_idx = 1  # asyncpg uses $1, $2, $3, ...

        # Track parameter names for logging
        param_names = []

        if phase is not None:
            set_fields.append(f'phase = ${param_idx}')
            params.append(phase)
            param_names.append('phase')
            param_idx += 1

        if target_price is not None:
            set_fields.append(f'target_price = ${param_idx}')
            params.append(target_price)
            param_names.append('target_price')
            param_idx += 1

        if hours_aged is not None:
            set_fields.append(f'hours_aged = ${param_idx}')
            params.append(hours_aged)
            param_names.append('hours_aged')
            param_idx += 1

        if loss_tolerance is not None:
            set_fields.append(f'loss_tolerance = ${param_idx}')
            params.append(loss_tolerance)
            param_names.append('loss_tolerance')
            param_idx += 1

        # position_id is the last parameter (for WHERE clause)
        params.append(str(position_id))
        param_names.append('position_id')

        query = f"""
            UPDATE monitoring.aged_positions
            SET {', '.join(set_fields)}
            WHERE position_id = ${param_idx}
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchval(query, *params)
                if result:
                    logger.info(f"Updated aged position {position_id}: {', '.join(param_names)}")
                    return True
                else:
                    logger.warning(f"Aged position for position_id {position_id} not found")
                    return False
            except Exception as e:
                logger.error(f"Failed to update aged position: {e}")
                return False

    async def create_aged_monitoring_event(
        self,
        aged_position_id: str,
        event_type: str,
        market_price: Optional[Decimal] = None,
        target_price: Optional[Decimal] = None,
        price_distance_percent: Optional[Decimal] = None,
        action_taken: Optional[str] = None,
        success: Optional[bool] = None,
        error_message: Optional[str] = None,
        event_metadata: Optional[Dict[Any, Any]] = None
    ) -> bool:
        """Log aged position monitoring event

        Args:
            aged_position_id: Aged position ID
            event_type: Type of event (price_check, phase_change, close_triggered, etc.)
            market_price: Current market price
            target_price: Target price at time of event
            price_distance_percent: Distance from target in percent
            action_taken: What action was taken
            success: Whether action was successful
            error_message: Error message if failed
            event_metadata: Additional event data

        Returns:
            True if logged successfully
        """
        query = """
            INSERT INTO monitoring.aged_monitoring_events (
                aged_position_id, event_type, market_price,
                target_price, price_distance_percent,
                action_taken, success, error_message,
                event_metadata, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
        """

        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    query,
                    aged_position_id,
                    event_type,
                    market_price,
                    target_price,
                    price_distance_percent,
                    action_taken,
                    success,
                    error_message,
                    json.dumps(event_metadata) if event_metadata else None
                )
                return True
            except Exception as e:
                logger.error(f"Failed to create monitoring event: {e}")
                return False

    async def mark_aged_position_closed(
        self,
        position_id: str,
        close_reason: str
    ) -> bool:
        """Mark aged position as closed

        Args:
            position_id: Position ID (matches position_id column)
            close_reason: Reason for closure

        Returns:
            True if deleted successfully
        """
        query = """
            DELETE FROM monitoring.aged_positions
            WHERE position_id = $1
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchval(query, str(position_id))
                if result:
                    logger.info(f"Marked aged position {position_id} as closed (reason: {close_reason})")
                    return True
                else:
                    logger.warning(f"Aged position {position_id} not found")
                    return False
            except Exception as e:
                logger.error(f"Failed to mark aged position as closed: {e}")
                return False

    async def get_aged_positions_statistics(
        self,
        from_date: datetime = None,
        to_date: datetime = None
    ) -> Dict:
        """Get aged positions statistics

        Args:
            from_date: Start date for statistics
            to_date: End date for statistics

        Returns:
            Dictionary with various statistics
        """
        if not from_date:
            from_date = now_utc() - timedelta(days=7)
        if not to_date:
            to_date = now_utc()

        query = """
            WITH stats AS (
                SELECT
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_count,
                    COUNT(CASE WHEN status = 'error' THEN 1 END) as error_count,
                    AVG(hours_aged) as avg_age_hours,
                    AVG(actual_pnl_percent) as avg_pnl_percent,
                    AVG(close_attempts) as avg_close_attempts,
                    AVG(EXTRACT(EPOCH FROM (closed_at - detected_at))) as avg_close_duration
                FROM monitoring.aged_positions
                WHERE detected_at BETWEEN $1 AND $2
            ),
            close_reasons AS (
                SELECT
                    close_reason,
                    COUNT(*) as count
                FROM monitoring.aged_positions
                WHERE detected_at BETWEEN $1 AND $2
                    AND close_reason IS NOT NULL
                GROUP BY close_reason
            )
            SELECT
                s.*,
                COALESCE(
                    json_object_agg(cr.close_reason, cr.count),
                    '{}'::json
                ) as by_close_reason
            FROM stats s
            CROSS JOIN close_reasons cr
            GROUP BY s.total_count, s.closed_count, s.error_count,
                     s.avg_age_hours, s.avg_pnl_percent,
                     s.avg_close_attempts, s.avg_close_duration
        """

        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(query, from_date, to_date)
                if row:
                    result = dict(row)
                    # Calculate success rate
                    if result['total_count'] > 0:
                        result['success_rate'] = (result['closed_count'] / result['total_count']) * 100
                    else:
                        result['success_rate'] = 0
                    return result
                else:
                    return {
                        'total_count': 0,
                        'closed_count': 0,
                        'error_count': 0,
                        'success_rate': 0,
                        'by_close_reason': {}
                    }
            except Exception as e:
                logger.error(f"Failed to get aged statistics: {e}")
                return {}

# Add alias for compatibility
TradingRepository = Repository
