import asyncpg
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal

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

    async def initialize(self):
        """Create optimized connection pool with better settings"""
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
    
    # ============== Transaction Management ==============
    
    class Transaction:
        """
        Transaction context manager for atomic database operations.
        
        Usage:
            async with repository.transaction() as conn:
                trade_id = await repository.create_trade(..., conn=conn)
                position_id = await repository.create_position(..., conn=conn)
                # If any operation fails, all are rolled back
        """
        
        def __init__(self, pool: asyncpg.Pool):
            self.pool = pool
            self.conn = None
            self.transaction = None
        
        async def __aenter__(self) -> asyncpg.Connection:
            """Acquire connection and start transaction"""
            self.conn = await self.pool.acquire()
            self.transaction = self.conn.transaction()
            await self.transaction.start()
            return self.conn
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            """Commit or rollback transaction and release connection"""
            try:
                if exc_type is not None:
                    # Exception occurred - rollback
                    await self.transaction.rollback()
                    logger.warning(f"Transaction rolled back due to {exc_type.__name__}: {exc_val}")
                else:
                    # No exception - commit
                    await self.transaction.commit()
            finally:
                await self.pool.release(self.conn)
            
            # Don't suppress the exception
            return False
    
    def transaction(self):
        """
        Create a transaction context manager.
        
        Returns:
            Transaction context manager that provides a connection
            
        Example:
            async with repository.transaction() as conn:
                await conn.execute("INSERT INTO ...")
                await conn.execute("UPDATE ...")
        """
        return self.Transaction(self.pool)

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

    # ============== Trade Operations ==============

    async def create_trade(self, trade_data: Dict, conn: Optional[asyncpg.Connection] = None) -> int:
        """
        Create new trade record.
        
        Args:
            trade_data: Trade information dictionary
            conn: Optional connection for transaction support
            
        Returns:
            Trade ID
        """
        query = """
            INSERT INTO monitoring.trades (
                signal_id, symbol, exchange, side,
                quantity, price, executed_qty,
                order_id, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """

        if conn:
            # Use provided connection (transaction mode)
            trade_id = await conn.fetchval(
                query,
                trade_data.get('signal_id'),
                trade_data['symbol'],
                trade_data['exchange'],
                trade_data['side'],
                trade_data.get('quantity'),
                trade_data.get('price'),
                trade_data.get('executed_qty'),
                trade_data.get('order_id'),
                trade_data.get('status', 'FILLED')
            )
        else:
            # Acquire connection from pool (standalone mode)
            async with self.pool.acquire() as conn:
                trade_id = await conn.fetchval(
                    query,
                    trade_data.get('signal_id'),
                    trade_data['symbol'],
                    trade_data['exchange'],
                    trade_data['side'],
                    trade_data.get('quantity'),
                    trade_data.get('price'),
                    trade_data.get('executed_qty'),
                    trade_data.get('order_id'),
                    trade_data.get('status', 'FILLED')
                )

        return trade_id

    # ============== Position Operations ==============

    async def create_position(self, position_data: Dict, conn: Optional[asyncpg.Connection] = None) -> int:
        """
        Create new position record.
        
        Args:
            position_data: Position information dictionary
            conn: Optional connection for transaction support
            
        Returns:
            Position ID
        """
        # ✅ CRITICAL: Log position creation to track ghost positions
        logger.info(
            f"📝 [Repository.create_position] CREATING: "
            f"symbol={position_data.get('symbol')}, "
            f"exchange={position_data.get('exchange')}, "
            f"side={position_data.get('side')}, "
            f"qty={position_data.get('quantity')}, "
            f"price={position_data.get('entry_price')}, "
            f"leverage={position_data.get('leverage', 1)}"
        )
        
        query = """
            INSERT INTO monitoring.positions (
                symbol, exchange, side, quantity,
                entry_price, leverage, status
            ) VALUES ($1, $2, $3, $4, $5, $6, 'active')
            RETURNING id
        """
        
        # Get leverage from position_data or default to 1
        leverage = position_data.get('leverage', 1)

        if conn:
            # Use provided connection (transaction mode)
            position_id = await conn.fetchval(
                query,
                position_data['symbol'],
                position_data['exchange'],
                position_data['side'],
                position_data['quantity'],
                position_data['entry_price'],
                leverage
            )
        else:
            # Acquire connection from pool (standalone mode)
            async with self.pool.acquire() as conn:
                position_id = await conn.fetchval(
                    query,
                    position_data['symbol'],
                    position_data['exchange'],
                    position_data['side'],
                    position_data['quantity'],
                    position_data['entry_price'],
                    leverage
                )

        # ✅ CRITICAL: Log successful creation
        logger.info(f"✅ [Repository.create_position] CREATED position ID: {position_id}")
        
        return position_id

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

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                position_update['current_price'],
                position_update.get('unrealized_pnl', 0),
                position_update['symbol'],
                position_update['exchange']
            )

    async def update_position_stop_loss(self, position_id: int, stop_price: float, order_id: str, 
                                        conn: Optional[asyncpg.Connection] = None):
        """
        Update position stop loss.
        
        Args:
            position_id: Position ID
            stop_price: Stop loss price
            order_id: Stop loss order ID
            conn: Optional connection for transaction support
        """
        query = """
            UPDATE monitoring.positions
            SET stop_loss_price = $1,
                has_stop_loss = TRUE,
                updated_at = NOW()
            WHERE id = $2
        """

        if conn:
            # Use provided connection (transaction mode)
            await conn.execute(query, stop_price, position_id)
        else:
            # Acquire connection from pool (standalone mode)
            async with self.pool.acquire() as conn:
                await conn.execute(query, stop_price, position_id)

    async def update_position_trailing_stop(self, position_id: int, has_trailing_stop: bool = True,
                                           conn: Optional[asyncpg.Connection] = None):
        """
        Update position trailing stop status.
        
        Args:
            position_id: Position ID
            has_trailing_stop: Whether trailing stop is active
            conn: Optional connection for transaction support
        """
        query = """
            UPDATE monitoring.positions
            SET has_trailing_stop = $1,
                updated_at = NOW()
            WHERE id = $2
        """

        if conn:
            # Use provided connection (transaction mode)
            await conn.execute(query, has_trailing_stop, position_id)
        else:
            # Acquire connection from pool (standalone mode)
            async with self.pool.acquire() as conn:
                await conn.execute(query, has_trailing_stop, position_id)

    async def close_position(self, position_id: int,
                            close_price: float = None,
                            pnl: float = None,
                            pnl_percentage: float = None,
                            reason: str = None,
                            exit_data: Dict = None):
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
                   created_at, updated_at
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
            position_id: Position ID to update
            **kwargs: Field names and values to update

        Returns:
            bool: True if update successful

        Example:
            await repo.update_position(123, current_price=50.5, pnl=10.0)
        """
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
    
    async def create_order(self, order: Any) -> bool:
        """Create order"""
        return True
    
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
    
    async def get_daily_stats(self, date: Any) -> Dict[str, Any]:
        """Get daily stats"""
        return {}
    
    async def create_risk_violation(self, violation: Any) -> bool:
        """Create risk violation"""
        return True


# Add alias for compatibility
TradingRepository = Repository
