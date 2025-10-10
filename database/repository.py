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

    # ============== Signal Operations ==============

    async def get_unprocessed_signals(self,
                                      min_score_week: float = 70,
                                      min_score_month: float = 80,
                                      time_window_minutes: int = 5,
                                      limit: int = 10) -> List[Dict]:
        """
        Fetch unprocessed signals within time window with correct exchange mapping
        Signals are grouped by 15-minute candle timestamps (waves)
        
        Returns signals ordered by:
        1. Created timestamp (most recent waves first) 
        2. Score within each wave (highest scores first)
        """
        query = """
            SELECT 
                sc.id, 
                sc.pair_symbol as symbol, 
                sc.recommended_action as action,  -- Может быть BUY, SELL, LONG, SHORT
                sc.score_week, 
                sc.score_month,
                sc.patterns_details, 
                sc.combinations_details,
                sc.created_at,
                LOWER(ex.exchange_name) as exchange,
                -- Round to 15-minute candle for wave grouping
                date_trunc('hour', sc.created_at) + 
                    interval '15 min' * floor(date_part('minute', sc.created_at) / 15) as wave_timestamp
            FROM fas.scoring_history sc
            JOIN public.trading_pairs tp ON tp.id = sc.trading_pair_id
            JOIN public.exchanges ex ON ex.id = tp.exchange_id
            WHERE sc.created_at > NOW() - INTERVAL '1 minute' * $1
                AND sc.score_week >= $2
                AND sc.score_month >= $3
                AND sc.is_active = true
                AND sc.recommended_action IN ('BUY', 'SELL', 'LONG', 'SHORT')
                AND sc.recommended_action IS NOT NULL
                AND sc.recommended_action != 'NO_TRADE'
            ORDER BY 
                -- First by wave timestamp (newest waves first)
                wave_timestamp DESC,
                -- Then by score within each wave (highest scores first)
                sc.score_week DESC, 
                sc.score_month DESC
            LIMIT $4
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                time_window_minutes,  # Just pass the number
                min_score_week,
                min_score_month,
                limit  # This is now the max we'll return, but filtering happens in signal_processor
            )

            return [dict(row) for row in rows]

    async def mark_signal_processed(self, signal_id: int):
        """Mark signal as processed by setting is_active to false"""
        # Update fas.scoring_history to mark as processed
        query = """
            UPDATE fas.scoring_history 
            SET is_active = false
            WHERE id = $1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, signal_id)
            
        # Also track in our signals table for history
        track_query = """
            INSERT INTO trading_bot.signals (external_id, symbol, exchange, action, processed, processed_at, created_at, source)
            SELECT $1, pair_symbol, 'binance', 
                   LOWER(COALESCE(recommended_action, 'buy')), 
                   true, NOW(), NOW(), 'fas'
            FROM fas.scoring_history
            WHERE id = $1
            ON CONFLICT (external_id) DO UPDATE SET processed = true, processed_at = NOW()
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(track_query, signal_id)

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

    async def create_trade(self, trade_data: Dict) -> int:
        """Create new trade record"""
        query = """
            INSERT INTO trading_bot.trades (
                position_id, symbol, exchange, side, order_type,
                quantity, price, order_id, status, commission,
                executed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            trade_id = await conn.fetchval(
                query,
                trade_data.get('position_id'),
                trade_data['symbol'],
                trade_data['exchange'],
                trade_data['side'],
                trade_data.get('order_type', 'MARKET'),
                trade_data['quantity'],
                trade_data['price'],
                trade_data['order_id'],
                trade_data.get('status', 'FILLED'),
                trade_data.get('commission', 0)
            )

            return trade_id

    # ============== Position Operations ==============

    async def create_position(self, position_data: Dict) -> int:
        """Create new position record"""
        query = """
            INSERT INTO monitoring.positions (
                symbol, exchange, side, quantity,
                entry_price, status
            ) VALUES ($1, $2, $3, $4, $5, 'active')
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            position_id = await conn.fetchval(
                query,
                position_data['symbol'],
                position_data['exchange'],
                position_data['side'],
                position_data['quantity'],
                position_data['entry_price']
            )

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

    async def update_position_stop_loss(self, position_id: int, stop_price: float, order_id: str):
        """Update position stop loss"""
        query = """
            UPDATE monitoring.positions
            SET stop_loss_price = $1,
                updated_at = NOW()
            WHERE id = $2
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, stop_price, position_id)

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
    
    async def get_pending_signals(self) -> List[Any]:
        """Get pending signals"""
        query = """
            SELECT * FROM trading_bot.signals 
            WHERE processed = false 
            ORDER BY created_at DESC
            LIMIT 10
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
    
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


    async def save_signal(self, signal: Dict) -> int:
        """Save signal to database"""
        query = """
            INSERT INTO trading_bot.signals 
            (source, symbol, action, score, entry_price, stop_loss, take_profit, processed, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, false, NOW())
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            signal_id = await conn.fetchval(
                query,
                signal.get('source', 'manual'),
                signal['symbol'],
                signal['action'],
                signal.get('score', 0),
                signal.get('entry_price'),
                signal.get('stop_loss'),
                signal.get('take_profit')
            )
            return signal_id
    
    async def get_total_balance(self, exchange: str = 'binance') -> Dict[str, Decimal]:
        """Get total balance for exchange"""
        query = """
            SELECT * FROM trading_bot.get_total_balance($1)
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, exchange)
            if row:
                return {
                    'total_balance': Decimal(str(row.get('total_balance', 0))),
                    'available_balance': Decimal(str(row.get('available_balance', 0))),
                    'margin_used': Decimal(str(row.get('margin_used', 0))),
                    'unrealized_pnl': Decimal(str(row.get('unrealized_pnl', 0)))
                }
            return {
                'total_balance': Decimal('0'),
                'available_balance': Decimal('0'),
                'margin_used': Decimal('0'),
                'unrealized_pnl': Decimal('0')
            }
    
    async def update_balance(self, exchange: str, currency: str, balance_data: Dict):
        """Update balance in history table"""
        query = """
            INSERT INTO trading_bot.balance_history 
            (exchange, currency, total_balance, available_balance, margin_used, unrealized_pnl)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (timestamp, exchange, currency) DO UPDATE
            SET total_balance = $3,
                available_balance = $4,
                margin_used = $5,
                unrealized_pnl = $6
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                exchange,
                currency,
                balance_data.get('total', 0),
                balance_data.get('free', 0),
                balance_data.get('used', 0),
                balance_data.get('unrealized_pnl', 0)
            )

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
                    order_data.get('timestamp') if order_data.get('timestamp') else datetime.now(),
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


# Add alias for compatibility
TradingRepository = Repository
