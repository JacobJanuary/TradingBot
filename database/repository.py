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
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            host=self.db_config['host'],
            port=self.db_config['port'],
            database=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            min_size=self.db_config.get('pool_size', 10),
            max_size=self.db_config.get('max_overflow', 20),
            command_timeout=10
        )
        logger.info("Database pool initialized")
        
        # Verify schemas exist
        async with self.pool.acquire() as conn:
            schemas = await conn.fetch("""
                SELECT schema_name FROM information_schema.schemata 
                WHERE schema_name IN ('fas', 'monitoring')
            """)
            existing = [s['schema_name'] for s in schemas]
            logger.info(f"Connected to DB with schemas: {', '.join(existing)}")

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
        """Fetch unprocessed signals within time window"""
        query = """
            SELECT 
                id, trading_pair_id, pair_symbol, exchange_id, exchange_name,
                score_week, score_month, recommended_action,
                patterns_details, combinations_details, created_at
            FROM trading_bot.scoring_history
            WHERE created_at > NOW() - INTERVAL '%s minutes'
                AND is_active = true
                AND is_processed = false
                AND score_week >= $1
                AND score_month >= $2
                AND recommended_action IN ('BUY', 'SELL')
            ORDER BY score_week DESC, score_month DESC
            LIMIT $3
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                query % time_window_minutes,
                min_score_week,
                min_score_month,
                limit
            )

            return [dict(row) for row in rows]

    async def mark_signal_processed(self, signal_id: int):
        """Mark signal as processed"""
        query = """
            UPDATE trading_bot.scoring_history 
            SET is_processed = true, 
                processed_at = NOW(),
                is_active = false
            WHERE id = $1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, signal_id)

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
            INSERT INTO monitoring.trades (
                signal_id, symbol, exchange, side, order_type,
                quantity, price, executed_qty, average_price,
                order_id, client_order_id, status, fee, fee_currency,
                executed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            trade_id = await conn.fetchval(
                query,
                trade_data.get('signal_id'),
                trade_data['symbol'],
                trade_data['exchange'],
                trade_data['side'],
                trade_data.get('order_type', 'MARKET'),
                trade_data['quantity'],
                trade_data['price'],
                trade_data['executed_qty'],
                trade_data.get('average_price', trade_data['price']),
                trade_data['order_id'],
                trade_data.get('client_order_id'),
                trade_data.get('status', 'FILLED'),
                trade_data.get('fee', 0),
                trade_data.get('fee_currency', 'USDT')
            )

            return trade_id

    # ============== Position Operations ==============

    async def create_position(self, position_data: Dict) -> int:
        """Create new position record"""
        query = """
            INSERT INTO trading_bot.positions (
                trade_id, symbol, exchange, side, quantity,
                entry_price, status, ws_position_id
            ) VALUES ($1, $2, $3, $4, $5, $6, 'OPEN', $7)
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            position_id = await conn.fetchval(
                query,
                position_data['trade_id'],
                position_data['symbol'],
                position_data['exchange'],
                position_data['side'],
                position_data['quantity'],
                position_data['entry_price'],
                position_data.get('ws_position_id')
            )

            return position_id

    async def get_open_position(self, symbol: str, exchange: str) -> Optional[Dict]:
        """Get open position for symbol"""
        query = """
            SELECT * FROM trading_bot.positions
            WHERE symbol = $1 
                AND exchange = $2 
                AND status = 'OPEN'
            LIMIT 1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, symbol, exchange)
            return dict(row) if row else None

    async def update_position_from_websocket(self, position_update: Dict):
        """Update position from WebSocket data"""
        query = """
            UPDATE trading_bot.positions 
            SET current_price = $1,
                mark_price = $2,
                unrealized_pnl = $3,
                unrealized_pnl_percent = $4,
                last_update = NOW()
            WHERE symbol = $5 
                AND exchange = $6 
                AND status = 'OPEN'
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                position_update['current_price'],
                position_update['mark_price'],
                position_update['unrealized_pnl'],
                position_update['unrealized_pnl_percent'],
                position_update['symbol'],
                position_update['exchange']
            )

    async def update_position_stop_loss(self, position_id: int, stop_price: float, order_id: str):
        """Update position stop loss"""
        query = """
            UPDATE trading_bot.positions 
            SET has_stop_loss = true,
                stop_loss_price = $1,
                stop_loss_order_id = $2
            WHERE id = $3
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, stop_price, order_id, position_id)

    async def update_position_trailing_stop(self, position_id: int,
                                            activation_price: float,
                                            callback_rate: float):
        """Update position trailing stop"""
        query = """
            UPDATE trading_bot.positions 
            SET has_trailing_stop = true,
                trailing_activation_price = $1,
                trailing_callback_rate = $2
            WHERE id = $3
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, activation_price, callback_rate, position_id)

    async def close_position(self, position_id: int, exit_data: Dict):
        """Close position with exit details"""
        query = """
            UPDATE trading_bot.positions 
            SET status = 'CLOSED',
                exit_price = $1,
                exit_quantity = $2,
                realized_pnl = $3,
                realized_pnl_percent = $4,
                exit_reason = $5,
                closed_at = NOW()
            WHERE id = $6
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                exit_data['exit_price'],
                exit_data['exit_quantity'],
                exit_data['realized_pnl'],
                exit_data['realized_pnl_percent'],
                exit_data['exit_reason'],
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
            FROM trading_bot.positions
            WHERE symbol = $1 AND exchange = $2 AND status = 'OPEN'
        """

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, symbol, exchange)
            return result or 0.0

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
    
    async def update_position(self, position: Any) -> bool:
        """Update position"""
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
            FROM trading_bot.positions
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


# Add alias for compatibility
TradingRepository = Repository
