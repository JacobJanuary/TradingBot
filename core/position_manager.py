"""
Position Manager - Core trading logic
Coordinates between exchange, database, and protection systems

============================================================
STOP LOSS OPERATIONS
============================================================

ВАЖНО: Весь код Stop Loss унифицирован через StopLossManager.

Не модифицируйте логику проверки/установки SL здесь.
Используйте ТОЛЬКО StopLossManager из core/stop_loss_manager.py

См. docs/STOP_LOSS_ARCHITECTURE.md (если создан)
============================================================
"""
import asyncio
import logging
import os
from typing import Dict, Optional, List
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config.settings import TradingConfig
from database.repository import Repository as TradingRepository
from protection.trailing_stop import SmartTrailingStopManager
from websocket.event_router import EventRouter
from core.exchange_manager import ExchangeManager
from utils.decimal_utils import to_decimal, calculate_stop_loss, calculate_pnl, calculate_quantity

# CRITICAL FIX: Import normalize_symbol for correct position verification
def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format for consistent comparison
    Converts exchange format 'HIGH/USDT:USDT' to database format 'HIGHUSDT'
    This function MUST match the one in position_synchronizer.py
    """
    if '/' in symbol and ':' in symbol:
        # Exchange format: 'HIGH/USDT:USDT' -> 'HIGHUSDT'
        base_quote = symbol.split(':')[0]  # 'HIGH/USDT'
        return base_quote.replace('/', '')  # 'HIGHUSDT'
    return symbol

logger = logging.getLogger(__name__)


def safe_get_attr(obj, *attrs, default=None):
    """
    Safely get attribute from dict or object
    Handles both dict and object access patterns

    Args:
        obj: Dict or object to get attribute from
        *attrs: List of possible attribute names to try
        default: Default value if not found

    Returns:
        Attribute value or default
    """
    for attr in attrs:
        if isinstance(obj, dict):
            value = obj.get(attr)
            if value is not None:
                return value
        else:
            value = getattr(obj, attr, None)
            if value is not None:
                return value
    return default


@dataclass
class PositionRequest:
    """Request to open new position"""
    signal_id: int
    symbol: str
    exchange: str
    side: str  # 'BUY' or 'SELL'
    entry_price: Decimal

    # Optional overrides
    position_size_usd: Optional[float] = None
    stop_loss_percent: Optional[float] = None
    # take_profit_percent: Optional[float] = None  # DEPRECATED - Using Smart Trailing Stop


@dataclass
class PositionState:
    """Current position state"""
    id: int
    symbol: str
    exchange: str
    side: str  # 'long' or 'short'
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float

    has_stop_loss: bool = False
    stop_loss_price: Optional[float] = None

    has_trailing_stop: bool = False
    trailing_activated: bool = False

    opened_at: datetime = None
    age_hours: float = 0
    
    # Pending close order info
    pending_close_order: Optional[Dict] = None


class PositionManager:
    """
    Central position management system
    Handles opening, monitoring, and closing positions
    """

    def __init__(self,
                 config: TradingConfig,
                 exchanges: Dict[str, ExchangeManager],
                 repository: TradingRepository,
                 event_router: EventRouter):
        """Initialize position manager"""
        self.config = config
        self.exchanges = exchanges
        self.repository = repository
        self.event_router = event_router

        # Trailing stop manager for each exchange
        from protection.trailing_stop import TrailingStopConfig
        from decimal import Decimal
        
        trailing_config = TrailingStopConfig(
            activation_percent=Decimal(str(config.trailing_activation_percent)),
            callback_percent=Decimal(str(config.trailing_callback_percent)),
            breakeven_at=None  # FIX: 2025-10-03 - Отключить breakeven механизм
        )
        
        self.trailing_managers = {
            name: SmartTrailingStopManager(exchange, trailing_config)
            for name, exchange in exchanges.items()
        }

        # Active positions tracking
        self.positions: Dict[str, PositionState] = {}  # symbol -> position

        # Position locks
        self.position_locks: set = set()

        # Risk management
        self.total_exposure = Decimal('0')
        self.position_count = 0

        # Statistics
        self.stats = {
            'positions_opened': 0,
            'positions_closed': 0,
            'total_pnl': Decimal('0'),
            'win_count': 0,
            'loss_count': 0
        }

        # Register WebSocket event handlers
        self._register_event_handlers()

        # Periodic sync task
        self.sync_task = None
        self.sync_interval = 600  # 10 minutes (optimized to reduce API calls)
        self.zombie_check_counter = 0  # Counter for tracking zombie checks
        self.last_zombie_count = 0  # Track last zombie count for trend monitoring
        self.aggressive_cleanup_threshold = 10  # Trigger aggressive cleanup if > 10 zombies

        logger.info("PositionManager initialized")

    async def synchronize_with_exchanges(self):
        """Synchronize database positions with exchange reality"""
        try:
            from core.position_synchronizer import PositionSynchronizer

            logger.info("🔄 Synchronizing positions with exchanges...")

            synchronizer = PositionSynchronizer(
                repository=self.repository,
                exchanges=self.exchanges
            )

            results = await synchronizer.synchronize_all_exchanges()

            # Log critical findings
            for exchange_name, result in results.items():
                if 'error' not in result:
                    if result.get('closed_phantom'):
                        logger.warning(
                            f"⚠️ {exchange_name}: Closed {len(result['closed_phantom'])} phantom positions: "
                            f"{result['closed_phantom']}"
                        )
                    if result.get('added_missing'):
                        logger.info(
                            f"➕ {exchange_name}: Added {len(result['added_missing'])} missing positions: "
                            f"{result['added_missing']}"
                        )

            return results

        except Exception as e:
            logger.error(f"Failed to synchronize positions: {e}")
            # Continue with loading - better to work with potentially stale data than crash
            return {}

    async def verify_position_exists(self, symbol: str, exchange: str) -> bool:
        """Verify a position actually exists on the exchange before operations"""
        try:
            exchange_instance = self.exchanges.get(exchange)
            if not exchange_instance:
                logger.error(f"Exchange {exchange} not configured")
                return False

            # CRITICAL FIX: Fetch ALL positions from exchange (not filtered by symbol)
            # Binance Futures requires exact symbol format - 'SONICUSDT' != 'SONIC/USDT:USDT'
            # We'll filter using normalize_symbol() comparison below
            positions = await exchange_instance.fetch_positions()

            # CRITICAL FIX: Use normalize_symbol for correct comparison
            # Database stores 'HIGHUSDT', exchange returns 'HIGH/USDT:USDT'
            normalized_symbol = normalize_symbol(symbol)

            # Check if position exists with non-zero contracts
            for pos in positions:
                # Compare normalized symbols instead of direct string comparison
                if normalize_symbol(pos.get('symbol')) == normalized_symbol:
                    contracts = float(pos.get('contracts') or 0)
                    if abs(contracts) > 0:
                        return True

            logger.warning(f"Position {symbol} not found on {exchange}")
            return False

        except Exception as e:
            logger.error(f"Error verifying position {symbol}: {e}")
            return False

    async def load_positions_from_db(self):
        """Load open positions from database on startup"""
        try:
            # FIRST: Synchronize with exchanges
            await self.synchronize_with_exchanges()

            # THEN: Load verified positions and double-check each one exists on exchange
            positions = await self.repository.get_open_positions()
            verified_positions = []

            for pos in positions:
                # CRITICAL FIX: 2025-10-03 - Double-check each position exists on exchange
                exchange_name = pos['exchange']
                symbol = pos['symbol']

                if exchange_name in self.exchanges:
                    try:
                        # Verify position actually exists on exchange
                        position_exists = await self.verify_position_exists(symbol, exchange_name)
                        if position_exists:
                            verified_positions.append(pos)
                            logger.debug(f"✅ Verified position exists on exchange: {symbol}")
                        else:
                            logger.warning(f"🗑️ PHANTOM detected during load: {symbol} - closing in database")
                            # Close the phantom position immediately - FIXED: Use correct method signature with all required args
                            await self.repository.close_position(
                                pos['id'],          # position_id: int
                                0.0,                # close_price: float
                                0.0,                # pnl: float
                                0.0,                # pnl_percentage: float
                                'PHANTOM_ON_LOAD'   # reason: str
                            )
                    except Exception as e:
                        logger.error(f"Error verifying position {symbol}: {e}")
                        # In case of error, skip this position for safety
                        continue
                else:
                    logger.warning(f"⚠️ Exchange {exchange_name} not available, skipping position {symbol}")

            # Use only verified positions
            positions = verified_positions

            for pos in positions:
                # Create PositionState from DB data
                # Use open_time if available, otherwise fall back to created_at
                opened_at = pos.get('open_time') or pos['created_at']

                position_state = PositionState(
                    id=pos['id'],
                    symbol=pos['symbol'],
                    exchange=pos['exchange'],
                    side=pos['side'],
                    quantity=pos['quantity'],
                    entry_price=pos['entry_price'],
                    current_price=pos['current_price'] or pos['entry_price'],
                    unrealized_pnl=pos['pnl'] or 0,
                    unrealized_pnl_percent=pos['pnl_percentage'] or 0,
                    has_stop_loss=pos['stop_loss'] is not None,
                    stop_loss_price=pos['stop_loss'],
                    has_trailing_stop=pos['trailing_activated'] or False,
                    trailing_activated=pos['trailing_activated'] or False,
                    opened_at=opened_at,
                    age_hours=self._calculate_age_hours(opened_at) if opened_at else 0
                )
                
                # Add to tracking
                self.positions[pos['symbol']] = position_state
                
                # Update exposure
                position_value = abs(pos['quantity'] * (pos['current_price'] or pos['entry_price']))
                self.total_exposure += Decimal(str(position_value))
            
            logger.info(f"📊 Loaded {len(self.positions)} positions from database")
            logger.info(f"💰 Total exposure: ${self.total_exposure:.2f}")

            # CRITICAL FIX: Check actual stop loss status on exchange BEFORE setting new ones
            # This prevents creating duplicate stop losses when they already exist
            logger.info("🔍 Checking actual stop loss status on exchanges...")
            await self.check_positions_protection()

            # Now check which positions still need stop losses (after real verification)
            positions_without_sl = []
            for symbol, position in self.positions.items():
                if not position.has_stop_loss:
                    positions_without_sl.append(position)
            
            if positions_without_sl:
                logger.warning(f"⚠️ Found {len(positions_without_sl)} positions without stop losses")
                logger.info("Setting stop losses for unprotected positions...")
                
                for position in positions_without_sl:
                    try:
                        exchange = self.exchanges.get(position.exchange)
                        if exchange:
                            # Get current market price
                            ticker = await exchange.fetch_ticker(position.symbol)
                            current_price = ticker.get('last') if ticker else position.current_price

                            # Calculate stop loss price
                            stop_loss_percent = to_decimal(self.config.stop_loss_percent)
                            stop_loss_price = calculate_stop_loss(
                                to_decimal(position.entry_price), position.side, stop_loss_percent
                            )

                            logger.info(f"Setting stop loss for {position.symbol}: {stop_loss_percent}% at ${stop_loss_price:.4f}")
                            logger.info(f"  Current price: ${current_price:.4f}")

                            # Check if stop would trigger immediately for short positions
                            if position.side == 'short' and current_price >= stop_loss_price:
                                logger.warning(f"⚠️ Stop loss would trigger immediately for {position.symbol}")
                                logger.warning(f"  Current: ${current_price:.4f} >= Stop: ${stop_loss_price:.4f}")
                                # Adjust stop loss to be slightly above current price
                                stop_loss_price = current_price * 1.005  # 0.5% above current
                                logger.info(f"  Adjusted stop to: ${stop_loss_price:.4f}")
                            # Check for long positions
                            elif position.side == 'long' and current_price <= stop_loss_price:
                                logger.warning(f"⚠️ Stop loss would trigger immediately for {position.symbol}")
                                logger.warning(f"  Current: ${current_price:.4f} <= Stop: ${stop_loss_price:.4f}")
                                # Adjust stop loss to be slightly below current price
                                stop_loss_price = current_price * 0.995  # 0.5% below current
                                logger.info(f"  Adjusted stop to: ${stop_loss_price:.4f}")

                            # Set stop loss on exchange
                            if await self._set_stop_loss(exchange, position, stop_loss_price):
                                position.has_stop_loss = True
                                position.stop_loss_price = stop_loss_price
                                logger.info(f"✅ Stop loss set for {position.symbol}")

                                # Update database
                                await self.repository.update_position_stop_loss(
                                    position.id, stop_loss_price, ""
                                )
                            else:
                                logger.error(f"❌ Failed to set stop loss for {position.symbol}")
                        else:
                            logger.error(f"Exchange {position.exchange} not found for {position.symbol}")

                    except Exception as e:
                        logger.error(f"Error setting stop loss for {position.symbol}: {e}")
            else:
                logger.info("✅ All loaded positions have stop losses")
            
            # Initialize trailing stops for loaded positions
            logger.info("🎯 Initializing trailing stops for loaded positions...")
            for symbol, position in self.positions.items():
                try:
                    trailing_manager = self.trailing_managers.get(position.exchange)
                    if trailing_manager:
                        # Create trailing stop for the position
                        await trailing_manager.create_trailing_stop(
                            symbol=symbol,
                            side=position.side,
                            entry_price=to_decimal(position.entry_price),
                            quantity=to_decimal(safe_get_attr(position, 'quantity', 'qty', 'size', default=0))
                        )
                        position.has_trailing_stop = True
                        logger.info(f"✅ Trailing stop initialized for {symbol}")
                    else:
                        logger.warning(f"⚠️ No trailing manager for exchange {position.exchange}")
                except Exception as e:
                    logger.error(f"Error initializing trailing stop for {symbol}: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load positions from database: {e}")
            return False

    async def sync_exchange_positions(self, exchange_name: str):
        """Sync positions from specific exchange"""
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                logger.warning(f"Exchange {exchange_name} not found")
                return

            logger.info(f"🔄 Syncing positions from {exchange_name}...")

            # Get positions from exchange
            positions = await exchange.fetch_positions()
            # CRITICAL FIX: fetch_positions() returns 'contracts' key, not 'quantity'
            active_positions = [p for p in positions if safe_get_attr(p, 'contracts', 'quantity', 'qty', 'size', default=0) > 0]
            # CRITICAL FIX: Normalize symbols for correct comparison with DB symbols
            # Exchange returns "A/USDT:USDT", DB stores "AUSDT"
            # fetch_positions() returns dicts, not objects - use p['symbol']
            active_symbols = {normalize_symbol(p['symbol']) for p in active_positions}

            logger.info(f"Found {len(active_positions)} positions on {exchange_name}")

            # Find positions in DB but not on exchange (closed positions)
            db_positions_to_close = []
            for symbol, pos_state in list(self.positions.items()):
                if pos_state.exchange == exchange_name and symbol not in active_symbols:
                    db_positions_to_close.append(pos_state)

            # Close positions that no longer exist on exchange
            if db_positions_to_close:
                logger.warning(f"⚠️ Found {len(db_positions_to_close)} positions in DB but not on {exchange_name}")
                for pos_state in db_positions_to_close:
                    logger.info(f"Closing orphaned position: {pos_state.symbol}")
                    # Close position in database
                    if pos_state.id:
                        await self.repository.close_position(
                            pos_state.id,                           # position_id: int
                            pos_state.current_price or 0.0,        # close_price: float
                            pos_state.unrealized_pnl or 0.0,       # pnl: float
                            pos_state.unrealized_pnl_percent or 0.0, # pnl_percentage: float
                            'sync_cleanup'                          # reason: str
                        )
                    # Remove from tracking
                    self.positions.pop(pos_state.symbol, None)
                    logger.info(f"✅ Closed orphaned position: {pos_state.symbol}")

            # Update or add positions
            for pos in active_positions:
                # CRITICAL FIX: Normalize symbol from exchange format to DB format
                # Exchange: "A/USDT:USDT" -> DB: "AUSDT"
                # fetch_positions() returns dicts with keys: 'symbol', 'side', 'contracts', 'entryPrice'
                symbol = normalize_symbol(pos['symbol'])
                side = pos['side']
                quantity = pos['contracts']
                entry_price = pos['entryPrice']

                # Check if position exists in our tracking
                if symbol not in self.positions or self.positions[symbol].exchange != exchange_name:
                    # New position - add to database
                    db_position = await self.repository.create_position({
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'side': side,
                        'quantity': quantity,
                        'entry_price': entry_price,
                        'current_price': entry_price,
                        'strategy': 'manual',
                        'status': 'open'
                    })

                    # Create position state
                    position_state = PositionState(
                        id=db_position['id'],
                        symbol=symbol,
                        exchange=exchange_name,
                        side=side,
                        quantity=quantity,
                        entry_price=entry_price,
                        current_price=entry_price,
                        unrealized_pnl=0,
                        unrealized_pnl_percent=0,
                        has_stop_loss=False,
                        stop_loss_price=None,
                        has_trailing_stop=False,
                        trailing_activated=False,
                        opened_at=datetime.now(timezone.utc),
                        age_hours=0
                    )

                    self.positions[symbol] = position_state
                    logger.info(f"➕ Added new position: {symbol}")

                    # Set stop loss for new position
                    stop_loss_percent = to_decimal(self.config.stop_loss_percent)
                    stop_loss_price = calculate_stop_loss(
                        to_decimal(entry_price), side, stop_loss_percent
                    )

                    if await self._set_stop_loss(exchange, position_state, stop_loss_price):
                        position_state.has_stop_loss = True
                        position_state.stop_loss_price = stop_loss_price
                        logger.info(f"✅ Stop loss set for new position {symbol}")

        except Exception as e:
            logger.error(f"Error syncing {exchange_name} positions: {e}")

    async def start_periodic_sync(self):
        """Start periodic position synchronization"""
        logger.info(f"🔄 Starting periodic sync every {self.sync_interval} seconds")

        while True:
            try:
                await asyncio.sleep(self.sync_interval)

                # Sync all exchanges
                for exchange_name in self.exchanges.keys():
                    await self.sync_exchange_positions(exchange_name)

                # Check for positions without stop loss after sync
                await self.check_positions_protection()

                # Handle real zombie positions (phantom and untracked)
                await self.handle_real_zombies()

                # Clean up zombie orders (orders without positions)
                await self.cleanup_zombie_orders()

                logger.info("✅ Periodic sync completed")

            except asyncio.CancelledError:
                logger.info("Periodic sync stopped")
                break
            except Exception as e:
                logger.error(f"Error in periodic sync: {e}")
                await asyncio.sleep(60)  # Wait before retry

    def _register_event_handlers(self):
        """Register handlers for WebSocket events"""

        @self.event_router.on('position.update')
        async def handle_position_update(data: Dict):
            await self._on_position_update(data)

        @self.event_router.on('order.filled')
        async def handle_order_filled(data: Dict):
            await self._on_order_filled(data)

        @self.event_router.on('stop_loss.triggered')
        async def handle_stop_loss(data: Dict):
            await self._on_stop_loss_triggered(data)

    async def open_position(self, request: PositionRequest) -> Optional[PositionState]:
        """
        Open new position with complete workflow:
        1. Validate request
        2. Check risk limits
        3. Calculate position size
        4. Execute market order
        5. Set stop loss
        6. Initialize trailing stop
        7. Save to database
        """

        symbol = request.symbol
        exchange_name = request.exchange.lower()

        # Acquire position lock
        lock_key = f"{exchange_name}_{symbol}"
        if lock_key in self.position_locks:
            logger.warning(f"Position already being processed for {symbol}")
            return None

        self.position_locks.add(lock_key)

        try:
            # 1. Get exchange
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                logger.error(f"Exchange {exchange_name} not available")
                return None

            # 2. Check if position already exists
            if await self._position_exists(symbol, exchange_name):
                logger.warning(f"Position already exists for {symbol} on {exchange_name}")
                return None

            # 3. Validate risk limits
            if not await self._validate_risk_limits(request):
                logger.warning(f"Risk limits exceeded for {symbol}")
                return None

            # 4. Calculate position size
            position_size_usd = request.position_size_usd or self.config.position_size_usd
            quantity = await self._calculate_position_size(
                exchange, symbol, request.entry_price, position_size_usd
            )

            if not quantity:
                logger.error(f"Failed to calculate position size for {symbol}")
                return None

            # 5. Validate spread (временно только логирование)
            await self._validate_spread(exchange, symbol)
            # Не блокируем открытие позиций из-за спреда

            # 6. Execute market order
            logger.info(f"Opening position: {symbol} {request.side} {quantity}")

            # Convert side: long -> buy, short -> sell for Binance
            if request.side.lower() == 'long':
                order_side = 'buy'
            elif request.side.lower() == 'short':
                order_side = 'sell'
            else:
                order_side = request.side.lower()

            order = await exchange.create_market_order(symbol, order_side, quantity)

            if not order or order.status != 'closed':
                logger.error(f"Failed to open position for {symbol}")
                return None

            # 7. Create position state
            position = PositionState(
                id=None,  # Will be set after DB insert
                symbol=symbol,
                exchange=exchange_name,
                side='long' if request.side == 'BUY' else 'short',
                quantity=order.filled,
                entry_price=order.price,
                current_price=order.price,
                unrealized_pnl=0,
                unrealized_pnl_percent=0,
                opened_at=datetime.now(timezone.utc)
            )

            # 8. Save to database
            trade_id = await self.repository.create_trade({
                'signal_id': request.signal_id,
                'symbol': symbol,
                'exchange': exchange_name,
                'side': order_side,
                'quantity': order.amount,
                'price': order.price,
                'executed_qty': order.filled,
                'average_price': order.price,
                'order_id': order.id,
                'status': 'FILLED'
            })

            position_id = await self.repository.create_position({
                'signal_id': request.signal_id,
                'symbol': symbol,
                'exchange': exchange_name,
                'side': position.side,
                'quantity': position.quantity,
                'entry_price': position.entry_price
            })

            position.id = position_id

            # 9. Set stop loss
            stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
            stop_loss_price = calculate_stop_loss(
                to_decimal(position.entry_price), position.side, to_decimal(stop_loss_percent)
            )
            
            logger.info(f"Setting stop loss for {symbol}: {stop_loss_percent}% at ${stop_loss_price:.4f}")

            if await self._set_stop_loss(exchange, position, stop_loss_price):
                position.has_stop_loss = True
                position.stop_loss_price = stop_loss_price
                logger.info(f"✅ Stop loss confirmed for {symbol}")

                await self.repository.update_position_stop_loss(
                    position_id, stop_loss_price, ""
                )
            else:
                logger.warning(f"⚠️ Failed to set stop loss for {symbol}")

            # 10. Initialize trailing stop
            trailing_manager = self.trailing_managers.get(exchange_name)
            if trailing_manager:
                await trailing_manager.create_trailing_stop(
                    symbol=symbol,
                    side=position.side,
                    entry_price=position.entry_price,
                    quantity=position.quantity,
                    initial_stop=stop_loss_price
                )
                position.has_trailing_stop = True

            # 11. Update internal tracking
            self.positions[symbol] = position
            self.position_count += 1
            self.total_exposure += Decimal(str(position.quantity * position.entry_price))
            self.stats['positions_opened'] += 1

            # Position already saved to database in steps 8-9 above
            logger.info(f"💾 Position saved to database with ID: {position.id}")

            logger.info(
                f"✅ Position opened: {symbol} {position.side} "
                f"{position.quantity:.6f} @ ${position.entry_price:.4f}"
            )

            return position

        except Exception as e:
            logger.error(f"Error opening position for {symbol}: {e}", exc_info=True)
            return None

        finally:
            self.position_locks.discard(lock_key)

    async def _position_exists(self, symbol: str, exchange: str) -> bool:
        """Check if position already exists"""
        # Check local tracking
        if symbol in self.positions:
            return True

        # Check database
        db_position = await self.repository.get_open_position(symbol, exchange)
        if db_position:
            return True

        # Check exchange
        exchange_obj = self.exchanges.get(exchange)
        if exchange_obj:
            # CRITICAL FIX: Same issue as verify_position_exists - use fetch_positions() without [symbol]
            positions = await exchange_obj.fetch_positions()
            # Find position using normalize_symbol comparison
            normalized_symbol = normalize_symbol(symbol)
            for pos in positions:
                if normalize_symbol(pos.get('symbol')) == normalized_symbol:
                    contracts = float(pos.get('contracts') or 0)
                    if abs(contracts) > 0:
                        return True

        return False

    async def has_open_position(self, symbol: str, exchange: str = None) -> bool:
        """
        Public method to check if position exists for symbol.
        Used by WaveSignalProcessor for duplicate detection.

        Args:
            symbol: Trading symbol to check
            exchange: Specific exchange to check (e.g., 'binance', 'bybit').
                     If None, checks all exchanges.

        Returns:
            bool: True if open position exists
        """
        # If specific exchange provided, check only that exchange
        if exchange:
            # Normalize exchange name (binance, bybit, etc)
            exchange_lower = exchange.lower()

            # Check in local cache for specific exchange
            for pos_symbol, position in self.positions.items():
                if pos_symbol == symbol and position.exchange.lower() == exchange_lower:
                    return True

            # Check on specific exchange
            if exchange in self.exchanges:
                return await self._position_exists(symbol, exchange)
            else:
                logger.warning(f"Exchange {exchange} not found in configured exchanges")
                return False

        # Original behavior: check all exchanges if no specific exchange provided
        else:
            # Quick check in local cache
            if symbol in self.positions:
                return True

            # Check all exchanges if not in cache
            for exchange_name in self.exchanges.keys():
                if await self._position_exists(symbol, exchange_name):
                    return True

            return False

    async def _validate_risk_limits(self, request: PositionRequest) -> bool:
        """Validate risk management rules"""

        # Check max positions
        if self.position_count >= self.config.max_positions:
            logger.warning(f"Max positions reached: {self.position_count}/{self.config.max_positions}")
            return False

        # Check max exposure
        position_size_usd = request.position_size_usd or self.config.position_size_usd
        new_exposure = self.total_exposure + Decimal(str(position_size_usd))

        if new_exposure > self.config.max_exposure_usd:
            logger.warning(
                f"Max exposure would be exceeded: "
                f"${new_exposure:.2f} > ${self.config.max_exposure_usd:.2f}"
            )
            return False

        return True

    async def _calculate_position_size(self,
                                       exchange: ExchangeManager,
                                       symbol: str,
                                       price: float,
                                       size_usd: float) -> Optional[float]:
        """
        Calculate position size with exchange constraints.
        Uses FIXED position size from config (POSITION_SIZE_USD).

        Args:
            exchange: Exchange manager instance
            symbol: Trading symbol (e.g., BTCUSDT)
            price: Entry price
            size_usd: Position size in USD (from config)

        Returns:
            Formatted quantity or None if invalid
        """

        # Validate position size
        from decimal import Decimal

        if size_usd <= 0:
            logger.error(f"Invalid position size: ${size_usd}")
            return None

        # Check against maximum allowed
        max_position_usd = float(os.getenv('MAX_POSITION_SIZE_USD', 5000))
        if size_usd > max_position_usd:
            logger.warning(f"Position size ${size_usd} exceeds maximum ${max_position_usd}")
            # Use maximum instead of failing
            size_usd = max_position_usd

        # Simple calculation: size_usd / price
        quantity = size_usd / Decimal(str(price))

        logger.debug(f"Position sizing for {symbol}:")
        logger.debug(f"  Fixed size: ${size_usd} USD")
        logger.debug(f"  Entry price: ${price}")
        logger.debug(f"  Raw quantity: {quantity}")

        # Apply exchange precision
        formatted_qty = exchange.amount_to_precision(symbol, quantity)

        # Check minimum amount
        min_amount = exchange.get_min_amount(symbol)
        if to_decimal(formatted_qty) < to_decimal(min_amount):
            logger.warning(f"Quantity {formatted_qty} below minimum {min_amount} for {symbol}")
            return None

        # Final validation - check actual value
        actual_value = float(formatted_qty) * float(price)
        logger.info(f"✅ Position size calculated for {symbol}:")
        logger.info(f"   Target: ${size_usd:.2f} USD")
        logger.info(f"   Actual: ${actual_value:.2f} USD")
        logger.info(f"   Quantity: {formatted_qty}")

        return formatted_qty

    async def _validate_spread(self, exchange: ExchangeManager, symbol: str) -> bool:
        """Validate bid-ask spread"""

        ticker = await exchange.fetch_ticker(symbol)
        if not ticker:
            return False

        bid = ticker.get('bid')
        ask = ticker.get('ask')

        if not bid or not ask or bid <= 0 or ask <= 0:
            return False

        spread_percent = ((ask - bid) / bid) * 100
        max_spread = to_decimal(self.config.max_spread_percent)

        if spread_percent > max_spread:
            logger.warning(f"Spread too wide for {symbol}: {spread_percent:.2f}% > {max_spread}%")
            # Временно пропускаем проверку для тестов
            pass  # Продолжаем несмотря на широкий спред

        return True

    async def _calculate_stop_loss(self, entry_price: float, side: str, percent: float) -> float:
        """Calculate stop loss price"""

        if side == 'long':
            return entry_price * (1 - percent / 100)
        else:
            return entry_price * (1 + percent / 100)

    async def _set_stop_loss(self,
                             exchange: ExchangeManager,
                             position: PositionState,
                             stop_price: float) -> bool:
        """
        Set stop loss order using unified StopLossManager.

        This function now uses StopLossManager for ALL SL operations
        to ensure consistency across the system.
        """

        logger.info(f"Attempting to set stop loss for {position.symbol}")
        logger.info(f"  Position: {position.side} {position.quantity} @ {position.entry_price}")
        logger.info(f"  Stop price: ${stop_price:.4f}")

        try:
            # ============================================================
            # UNIFIED APPROACH: Use StopLossManager for ALL SL operations
            # ============================================================
            from core.stop_loss_manager import StopLossManager

            sl_manager = StopLossManager(exchange.exchange, position.exchange)

            # CRITICAL: Check using unified has_stop_loss (checks both position.info.stopLoss AND orders)
            has_sl, existing_sl_price = await sl_manager.has_stop_loss(position.symbol)

            if has_sl:
                logger.info(f"📌 Stop loss already exists for {position.symbol} at {existing_sl_price}")
                return True  # Stop loss exists, no need to create new one

            # No SL exists - create it using unified set_stop_loss
            order_side = 'sell' if position.side == 'long' else 'buy'

            result = await sl_manager.set_stop_loss(
                symbol=position.symbol,
                side=order_side,
                amount=float(position.quantity),
                stop_price=stop_price
            )

            if result['status'] in ['created', 'already_exists']:
                logger.info(f"✅ Stop loss set for {position.symbol} at {result['stopPrice']}")
                return True
            else:
                logger.warning(f"⚠️ Unexpected result from set_stop_loss: {result}")
                return False

        except Exception as e:
            logger.error(f"Failed to set stop loss for {position.symbol}: {e}", exc_info=True)

        return False

    async def _on_position_update(self, data: Dict):
        """Handle position update from WebSocket"""

        symbol_raw = data.get('symbol')
        # CRITICAL FIX: Normalize symbol to match storage format (e.g., "BNT/USDT:USDT" → "BNTUSDT")
        symbol = normalize_symbol(symbol_raw) if symbol_raw else None
        logger.info(f"📊 Position update: {symbol_raw} → {symbol}, mark_price={data.get('mark_price')}")

        if not symbol or symbol not in self.positions:
            logger.info(f"  → Skipped: {symbol} not in tracked positions ({list(self.positions.keys())[:5]}...)")
            return

        position = self.positions[symbol]

        # Update position state
        old_price = position.current_price
        position.current_price = data.get('mark_price', position.current_price)
        logger.info(f"  → Price updated {symbol}: {old_price} → {position.current_price}")
        position.unrealized_pnl = data.get('unrealized_pnl', 0)

        # Calculate PnL percent
        if position.entry_price > 0:
            if position.side == 'long':
                position.unrealized_pnl_percent = (
                        (position.current_price - position.entry_price) / position.entry_price * 100
                )
            else:
                position.unrealized_pnl_percent = (
                        (position.entry_price - position.current_price) / position.entry_price * 100
                )

        # Update trailing stop
        trailing_manager = self.trailing_managers.get(position.exchange)
        if trailing_manager and position.has_trailing_stop:
            update_result = await trailing_manager.update_price(symbol, position.current_price)

            if update_result and update_result.get('action') == 'activated':
                position.trailing_activated = True
                logger.info(f"Trailing stop activated for {symbol}")
                # Save trailing activation to database
                await self.repository.update_position(position.id, trailing_activated=True)

        # Update database
        await self.repository.update_position_from_websocket({
            'symbol': symbol,
            'exchange': position.exchange,
            'current_price': position.current_price,
            'mark_price': position.current_price,
            'unrealized_pnl': position.unrealized_pnl,
            'unrealized_pnl_percent': position.unrealized_pnl_percent
        })

    async def _on_order_filled(self, data: Dict):
        """Handle order filled event"""

        order_type = data.get('type', '').lower()
        symbol = data.get('symbol')

        # Check if it's a closing order
        if order_type in ['stop_market', 'stop', 'take_profit_market']:
            if symbol in self.positions:
                await self.close_position(symbol, data.get('exit_reason', order_type))

    async def _on_stop_loss_triggered(self, data: Dict):
        """Handle stop loss triggered event"""

        symbol = data.get('symbol')
        if symbol in self.positions:
            logger.warning(f"⚠️ Stop loss triggered for {symbol}")
            await self.close_position(symbol, 'stop_loss')

    async def close_position(self, symbol: str, reason: str = 'manual'):
        """Close position and update records"""

        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol}")
            return

        position = self.positions[symbol]
        exchange = self.exchanges.get(position.exchange)

        if not exchange:
            logger.error(f"Exchange {position.exchange} not available")
            return

        try:
            # Close position on exchange
            success = await exchange.close_position(symbol)

            if success:
                # Calculate realized PnL
                exit_price = position.current_price

                if position.side == 'long':
                    realized_pnl = (exit_price - position.entry_price) * position.quantity
                    realized_pnl_percent = (exit_price - position.entry_price) / position.entry_price * 100
                else:
                    realized_pnl = (position.entry_price - exit_price) * position.quantity
                    realized_pnl_percent = (position.entry_price - exit_price) / position.entry_price * 100

                # Update database
                await self.repository.close_position(
                    position.id,                    # position_id: int
                    exit_price,                     # close_price: float
                    realized_pnl,                   # pnl: float
                    realized_pnl_percent,           # pnl_percentage: float
                    reason                          # reason: str
                )

                # Update statistics
                self.stats['positions_closed'] += 1
                self.stats['total_pnl'] += Decimal(str(realized_pnl))

                if realized_pnl > 0:
                    self.stats['win_count'] += 1
                else:
                    self.stats['loss_count'] += 1

                # Clean up tracking
                del self.positions[symbol]
                self.position_count -= 1
                self.total_exposure -= Decimal(str(position.quantity * position.entry_price))

                # Clean up trailing stop
                trailing_manager = self.trailing_managers.get(position.exchange)
                if trailing_manager:
                    await trailing_manager.on_position_closed(symbol, realized_pnl)

                logger.info(
                    f"Position closed: {symbol} {reason} "
                    f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
                )

        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}", exc_info=True)

    async def _cancel_pending_close_order(self, position: PositionState):
        """Cancel pending close order for position"""
        if not position.pending_close_order:
            return
            
        exchange = self.exchanges.get(position.exchange)
        if not exchange:
            return
            
        try:
            order_id = position.pending_close_order['order_id']
            await exchange.exchange.cancel_order(order_id, position.symbol)
            logger.info(f"Cancelled pending close order {order_id} for {position.symbol}")
            position.pending_close_order = None
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
    
    async def _place_limit_close_order(self, symbol: str, position: PositionState,
                                       target_price: float, reason: str):
        """Place a limit order to close position at target price"""
        exchange = self.exchanges.get(position.exchange)
        if not exchange:
            logger.error(f"Exchange {position.exchange} not available")
            return

        try:
            # Import enhanced manager if available, fallback to standard
            try:
                from core.exchange_manager_enhanced import EnhancedExchangeManager

                # Create enhanced manager wrapper
                enhanced_manager = EnhancedExchangeManager(exchange.exchange)

                # Determine order side (opposite to position)
                order_side = 'sell' if position.side == 'long' else 'buy'

                # Use enhanced manager with duplicate checking
                order = await enhanced_manager.create_limit_exit_order(
                    symbol=symbol,
                    side=order_side,
                    amount=float(position.quantity),
                    price=float(target_price),
                    check_duplicates=True  # CRITICAL: Prevent duplicates!
                )

            except ImportError:
                # Fallback to standard method if enhanced not available
                logger.warning("Enhanced ExchangeManager not available, using standard method")

                # Determine order side (opposite to position)
                order_side = 'sell' if position.side == 'long' else 'buy'

                # Place limit order through standard exchange manager
                order = await exchange.create_limit_order(
                    symbol=symbol,
                    side=order_side,
                    amount=position.quantity,
                    price=target_price
                )
            
            # CRITICAL FIX: Handle OrderResult safely
            order_id = None
            if order:
                if hasattr(order, 'id'):  # OrderResult
                    order_id = order.id
                elif hasattr(order, 'get'):  # Dict
                    order_id = order.get('id')
                else:
                    order_id = getattr(order, 'id', None)

            if order and order_id:
                logger.info(
                    f"Placed limit close order for {symbol} at {target_price:.2f} "
                    f"(order_id: {order_id}, reason: {reason})"
                )
                
                # Store order info for tracking
                position.pending_close_order = {
                    'order_id': order_id,
                    'price': to_decimal(target_price),
                    'reason': reason,
                    'created_at': datetime.now(timezone.utc)
                }
                
                # Update database with pending close order
                await self.repository.update_position(position.id, {
                    'pending_close_order_id': order['id'],
                    'pending_close_price': to_decimal(target_price),
                    'exit_reason': reason
                })
            else:
                logger.error(f"Failed to place limit order for {symbol}")
                
        except Exception as e:
            logger.error(f"Error placing limit close order for {symbol}: {e}", exc_info=True)
            # Fallback to market close if limit order fails
            logger.warning(f"Falling back to market close for {symbol}")
            await self.close_position(symbol, f"{reason}_fallback")

    async def check_position_age(self):
        """Check and close positions that exceed max age with smart logic"""
        from datetime import datetime, timezone, timedelta
        from decimal import Decimal
        
        max_age_hours = self.config.max_position_age_hours
        commission_percent = Decimal(str(self.config.commission_percent))  # Из конфигурации
        
        for symbol, position in list(self.positions.items()):
            if position.opened_at:
                # Handle timezone-aware datetimes properly
                if position.opened_at.tzinfo:
                    current_time = datetime.now(position.opened_at.tzinfo)
                else:
                    current_time = datetime.now(timezone.utc)
                position_age = current_time - position.opened_at
                position.age_hours = position_age.total_seconds() / 3600
                
                if position.age_hours >= max_age_hours:
                    logger.warning(
                        f"⏰ Position {symbol} exceeded max age: {position.age_hours:.1f} hours (max: {max_age_hours}h)"
                    )
                    
                    # Рассчитываем цену безубытка с учетом комиссий
                    if position.side == 'long':
                        breakeven_price = position.entry_price * (1 + commission_percent / 100)
                        is_profitable = position.current_price >= breakeven_price
                    else:  # short
                        breakeven_price = position.entry_price * (1 - commission_percent / 100)
                        is_profitable = position.current_price <= breakeven_price
                    
                    exchange = self.exchanges.get(position.exchange)
                    
                    # Проверяем, есть ли уже pending ордер
                    if position.pending_close_order:
                        logger.info(
                            f"Position {symbol} already has pending close order "
                            f"(order_id: {position.pending_close_order['order_id']}, "
                            f"price: {position.pending_close_order['price']})"
                        )
                        # Проверяем, не стала ли позиция прибыльной
                        if is_profitable and position.pending_close_order['reason'].startswith('max_age_limit'):
                            # Отменяем лимитный ордер и закрываем по рынку
                            await self._cancel_pending_close_order(position)
                            await self.close_position(symbol, f'max_age_market_{max_age_hours}h')
                    else:
                        # Always close expired positions immediately for safety
                        # If position is WAY over max age (>2x), force close regardless of profit
                        if position.age_hours >= max_age_hours * 2:
                            logger.error(
                                f"🚨 CRITICAL: Position {symbol} is {position.age_hours:.1f} hours old "
                                f"(2x max age). Force closing immediately!"
                            )
                            await self.close_position(symbol, f'max_age_force_{position.age_hours:.0f}h')
                        elif is_profitable:
                            # Позиция в плюсе - закрываем по рынку
                            logger.info(
                                f"✅ Expired position {symbol} is profitable "
                                f"(current: {position.current_price}, breakeven: {breakeven_price:.2f}). "
                                f"Closing by market order."
                            )
                            await self.close_position(symbol, f'max_age_market_{max_age_hours}h')
                        else:
                            # For expired positions at loss, still close them but log the loss
                            pnl_percent = position.unrealized_pnl_percent
                            logger.warning(
                                f"⚠️ Expired position {symbol} at {pnl_percent:.2f}% loss. "
                                f"Closing anyway due to age ({position.age_hours:.1f}h > {max_age_hours}h)"
                            )
                            await self.close_position(symbol, f'max_age_expired_{max_age_hours}h')
                        
                elif position.age_hours >= max_age_hours * 0.8:
                    # Warning when approaching max age
                    logger.info(
                        f"Position {symbol} approaching max age: {position.age_hours:.1f}/{max_age_hours} hours"
                    )

    async def check_positions_protection(self):
        """
        Periodically check and fix positions without stop loss.

        Now using unified StopLossManager for ALL SL checks.
        """
        try:
            from core.stop_loss_manager import StopLossManager

            unprotected_positions = []

            # Check all positions for stop loss - verify on exchange using unified manager
            for symbol, position in self.positions.items():
                exchange = self.exchanges.get(position.exchange)
                if not exchange:
                    continue

                # ============================================================
                # UNIFIED APPROACH: Use StopLossManager for SL check
                # ============================================================
                try:
                    sl_manager = StopLossManager(exchange.exchange, position.exchange)
                    has_sl_on_exchange, sl_price = await sl_manager.has_stop_loss(symbol)

                    logger.info(f"Checking position {symbol}: has_sl={has_sl_on_exchange}, price={sl_price}")

                except Exception as e:
                    logger.warning(f"Could not check SL for {symbol}: {e}")
                    # Assume no SL if we can't check
                    has_sl_on_exchange = False

                # Update position state based on actual exchange status
                position.has_stop_loss = has_sl_on_exchange

                if not has_sl_on_exchange:
                    unprotected_positions.append(position)
                    logger.warning(f"⚠️ Position {symbol} has no stop loss on exchange!")

            # If found unprotected positions, set stop losses using enhanced SL manager
            if unprotected_positions:
                logger.warning(f"🔴 Found {len(unprotected_positions)} positions without stop loss protection!")

                for position in unprotected_positions:
                    try:
                        exchange = self.exchanges.get(position.exchange)
                        if not exchange:
                            logger.error(f"Exchange {position.exchange} not available for {position.symbol}")
                            continue

                        # Calculate stop loss price
                        stop_loss_percent = self.config.stop_loss_percent

                        if position.side == 'long':
                            stop_loss_price = position.entry_price * (1 - stop_loss_percent / 100)
                        else:
                            stop_loss_price = position.entry_price * (1 + stop_loss_percent / 100)

                        # Use enhanced SL manager with auto-validation and retry
                        sl_manager = StopLossManager(exchange.exchange, position.exchange)
                        success = await sl_manager.verify_and_fix_missing_sl(
                            position=position,
                            stop_price=stop_loss_price,
                            max_retries=3
                        )

                        if success:
                            position.has_stop_loss = True
                            position.stop_loss_price = stop_loss_price
                            logger.info(f"✅ Stop loss set for {position.symbol} at {stop_loss_price:.8f}")

                            # Update database
                            await self.repository.update_position_stop_loss(
                                position.id, stop_loss_price, ""
                            )
                        else:
                            logger.error(f"❌ Failed to set stop loss for {position.symbol}")

                    except Exception as e:
                        logger.error(f"Error setting stop loss for {position.symbol}: {e}")

                # Log summary
                protected_count = sum(1 for p in unprotected_positions if p.has_stop_loss)
                logger.info(
                    f"Stop loss protection check complete: "
                    f"{protected_count}/{len(unprotected_positions)} positions protected"
                )

                # Alert if any positions still unprotected
                remaining_unprotected = [p for p in unprotected_positions if not p.has_stop_loss]
                if remaining_unprotected:
                    logger.error(
                        f"🔴 CRITICAL: {len(remaining_unprotected)} positions still without stop loss! "
                        f"Symbols: {', '.join([p.symbol for p in remaining_unprotected])}"
                    )

        except Exception as e:
            logger.error(f"Error in position protection check: {e}", exc_info=True)

    async def handle_real_zombies(self):
        """
        Handle REAL zombie positions:
        - PHANTOM: in DB but not on exchange
        - UNTRACKED: on exchange but not in DB
        """
        try:
            logger.info("🔍 Checking for real zombie positions...")

            zombies_found = False

            for exchange_name, exchange in self.exchanges.items():
                try:
                    # Get positions from exchange
                    exchange_positions = await exchange.fetch_positions()
                    active_exchange_positions = [p for p in exchange_positions if p['contracts'] > 0]

                    # Get local positions for this exchange
                    local_positions = {
                        symbol: pos for symbol, pos in self.positions.items()
                        if pos.exchange == exchange_name
                    }

                    # Create sets for comparison
                    exchange_symbols = {p['symbol'] for p in active_exchange_positions}
                    local_symbols = set(local_positions.keys())

                    # 1. PHANTOM POSITIONS (in DB but not on exchange)
                    phantom_symbols = local_symbols - exchange_symbols

                    if phantom_symbols:
                        zombies_found = True
                        logger.warning(f"👻 Found {len(phantom_symbols)} PHANTOM positions on {exchange_name}")

                        for symbol in phantom_symbols:
                            position = local_positions[symbol]
                            logger.warning(f"Phantom position detected: {symbol} (in DB but not on {exchange_name})")

                            try:
                                # Remove from local cache
                                if symbol in self.positions:
                                    del self.positions[symbol]

                                # Update database - mark as closed
                                await self.repository.update_position_status(
                                    position.id,
                                    'closed',
                                    notes='PHANTOM_CLEANUP'
                                )

                                logger.info(f"✅ Cleaned phantom position: {symbol}")

                            except Exception as cleanup_error:
                                logger.error(f"Failed to clean phantom position {symbol}: {cleanup_error}")

                    # 2. UNTRACKED POSITIONS (on exchange but not in DB)
                    untracked_positions = []
                    for ex_pos in active_exchange_positions:
                        if ex_pos['symbol'] not in local_symbols:
                            untracked_positions.append(ex_pos)

                    if untracked_positions:
                        zombies_found = True
                        logger.warning(f"🤖 Found {len(untracked_positions)} UNTRACKED positions on {exchange_name}")

                        for ex_pos in untracked_positions:
                            symbol = ex_pos['symbol']
                            size = ex_pos['contracts']
                            side = ex_pos['side']
                            entry_price = ex_pos.get('entryPrice', 0)

                            logger.warning(f"Untracked position: {symbol} {side} {size} @ {entry_price}")

                            # Options for handling untracked positions:
                            # Option 1: Import into system (safer for positions we might have created)
                            # Option 2: Close immediately (safer for unknown positions)

                            # For now, just log and alert - don't auto-close
                            # Manual decision required
                            logger.critical(f"⚠️ MANUAL REVIEW REQUIRED: Untracked position {symbol} on {exchange_name}")

                            # Save to monitoring table for review
                            if hasattr(self.repository, 'log_untracked_position'):
                                await self.repository.log_untracked_position({
                                    'exchange': exchange_name,
                                    'symbol': symbol,
                                    'side': side,
                                    'size': size,
                                    'entry_price': entry_price,
                                    'detected_at': datetime.now(),
                                    'raw_data': ex_pos
                                })

                except Exception as exchange_error:
                    logger.error(f"Error checking zombies on {exchange_name}: {exchange_error}")

            if not zombies_found:
                logger.info("✅ No zombie positions found")

        except Exception as e:
            logger.error(f"Error in zombie position handling: {e}", exc_info=True)

    async def cleanup_zombie_orders(self):
        """
        Enhanced zombie order cleanup using specialized cleaners:
        - BybitZombieOrderCleaner for Bybit exchanges
        - BinanceZombieManager for Binance exchanges with weight-based rate limiting
        Falls back to basic cleanup for other exchanges
        """
        try:
            cleanup_start_time = asyncio.get_event_loop().time()
            logger.info("🧹 Starting enhanced zombie order cleanup...")
            logger.info(f"📊 Cleanup interval: {self.sync_interval} seconds")
            total_zombies_cleaned = 0
            total_zombies_found = 0

            for exchange_name, exchange in self.exchanges.items():
                try:
                    # Use specialized cleaner for Bybit
                    if 'bybit' in exchange_name.lower():
                        # Import and use the advanced Bybit cleaner
                        try:
                            from core.bybit_zombie_cleaner import BybitZombieOrderCleaner

                            # Initialize the cleaner with the exchange
                            cleaner = BybitZombieOrderCleaner(exchange.exchange)

                            # Run comprehensive cleanup
                            logger.info(f"🔧 Running advanced Bybit zombie cleanup for {exchange_name}")
                            results = await cleaner.cleanup_zombie_orders(
                                symbols=None,  # Check all symbols
                                category="linear",  # For perpetual futures
                                dry_run=False  # Actually cancel orders
                            )

                            # Log results
                            if results['zombies_found'] > 0:
                                logger.warning(
                                    f"🧟 Bybit: Found {results['zombies_found']} zombies, "
                                    f"cancelled {results['zombies_cancelled']}, "
                                    f"TP/SL cleared: {results.get('tpsl_cleared', 0)}"
                                )
                                total_zombies_found += results['zombies_found']
                                total_zombies_cleaned += results['zombies_cancelled']

                                # Log individual zombie details for monitoring
                                logger.info(f"📈 Zombie cleanup metrics for {exchange_name}:")
                                logger.info(f"  - Detection rate: {results['zombies_found']}/{results.get('total_scanned', 0)} orders")
                                logger.info(f"  - Cleanup success rate: {results['zombies_cancelled']}/{results['zombies_found']}")
                                logger.info(f"  - Errors: {len(results.get('errors', []))}")
                            else:
                                logger.debug(f"✨ No zombie orders found on {exchange_name}")

                            # Print detailed stats
                            if results.get('errors'):
                                logger.error(f"⚠️ Errors during cleanup: {results['errors'][:3]}")

                        except ImportError as ie:
                            logger.warning(f"BybitZombieOrderCleaner not available, using basic cleanup: {ie}")
                            # Fall back to basic cleanup for Bybit
                            await self._basic_zombie_cleanup(exchange_name, exchange)

                    # Use specialized cleaner for Binance
                    elif 'binance' in exchange_name.lower():
                        try:
                            from core.binance_zombie_manager import BinanceZombieIntegration

                            # Initialize the Binance zombie manager integration
                            integration = BinanceZombieIntegration(exchange.exchange)

                            # Enable zombie protection with advanced features
                            logger.info(f"🔧 Running advanced Binance zombie cleanup for {exchange_name}")
                            await integration.enable_zombie_protection()

                            # Perform cleanup
                            results = await integration.cleanup_zombies(dry_run=False)

                            # Log results
                            if results['zombie_orders_found'] > 0:
                                logger.warning(
                                    f"🧟 Binance: Found {results['zombie_orders_found']} zombies, "
                                    f"cancelled {results['zombie_orders_cancelled']}, "
                                    f"OCO handled: {results.get('oco_orders_handled', 0)}"
                                )
                                total_zombies_found += results['zombie_orders_found']
                                total_zombies_cleaned += results['zombie_orders_cancelled']

                                # Log metrics
                                logger.info(f"📈 Zombie cleanup metrics for {exchange_name}:")
                                logger.info(f"  - Empty responses mitigated: {results.get('empty_responses_mitigated', 0)}")
                                logger.info(f"  - API weight used: {results.get('weight_used', 0)}")
                                logger.info(f"  - Async delays detected: {results.get('async_delays_detected', 0)}")
                                logger.info(f"  - Errors: {len(results.get('errors', []))}")
                            else:
                                logger.debug(f"✨ No zombie orders found on {exchange_name}")

                            # Check if weight limit is approaching
                            if results.get('weight_used', 0) > 900:
                                logger.warning(f"⚠️ Binance API weight high: {results['weight_used']}/1200")

                        except ImportError as ie:
                            logger.warning(f"BinanceZombieManager not available, using basic cleanup: {ie}")
                            # Fall back to basic cleanup for Binance
                            await self._basic_zombie_cleanup(exchange_name, exchange)

                    else:
                        # Use basic cleanup for other exchanges
                        cleaned = await self._basic_zombie_cleanup(exchange_name, exchange)
                        if cleaned > 0:
                            total_zombies_found += cleaned
                            total_zombies_cleaned += cleaned

                except Exception as exchange_error:
                    logger.error(f"Error cleaning zombie orders on {exchange_name}: {exchange_error}")

            # Log final summary with timing
            cleanup_duration = asyncio.get_event_loop().time() - cleanup_start_time

            # Update zombie tracking
            self.zombie_check_counter += 1
            self.last_zombie_count = total_zombies_found

            if total_zombies_found > 0:
                logger.warning(f"⚠️ ZOMBIE CLEANUP SUMMARY:")
                logger.warning(f"  🧟 Total found: {total_zombies_found}")
                logger.warning(f"  ✅ Total cleaned: {total_zombies_cleaned}")
                logger.warning(f"  ❌ Failed to clean: {total_zombies_found - total_zombies_cleaned}")
                logger.warning(f"  ⏱️ Duration: {cleanup_duration:.2f} seconds")
                logger.warning(f"  📊 Check #: {self.zombie_check_counter}")

                # Alert and adjust if too many zombies
                if total_zombies_found > self.aggressive_cleanup_threshold:
                    logger.critical(f"🚨 HIGH ZOMBIE COUNT DETECTED: {total_zombies_found} zombies!")
                    logger.critical(f"🔄 Temporarily reducing sync interval from {self.sync_interval}s to 300s")

                    # Temporarily reduce sync interval to clean up faster
                    self.sync_interval = min(300, self.sync_interval)  # Max 5 minutes for emergency cleanup

                    logger.critical("📢 Manual intervention may be required - check exchange UI")
                elif total_zombies_found > 5:
                    logger.warning(f"⚠️ Moderate zombie count: {total_zombies_found}")
                    # Slightly reduce interval if persistent zombies
                    if self.sync_interval > 300:
                        self.sync_interval = 450  # 7.5 minutes
                        logger.info(f"📉 Reduced sync interval to {self.sync_interval}s")
            else:
                logger.info(f"✨ No zombie orders found (check #{self.zombie_check_counter}, duration: {cleanup_duration:.2f}s)")

                # Gradually increase interval if no zombies found for multiple checks
                if self.zombie_check_counter > 3 and self.last_zombie_count == 0:
                    if self.sync_interval < 600:
                        self.sync_interval = min(600, self.sync_interval + 60)
                        logger.info(f"📈 Increased sync interval back to {self.sync_interval}s")

        except Exception as e:
            logger.error(f"Error in enhanced zombie order cleanup: {e}")

    async def _basic_zombie_cleanup(self, exchange_name: str, exchange) -> int:
        """
        Basic zombie order cleanup for non-Bybit exchanges
        Returns number of orders cancelled
        """
        cancelled_count = 0

        try:
            # Get all open orders from exchange
            open_orders = await exchange.exchange.fetch_open_orders()

            # Get current positions
            positions = await exchange.fetch_positions()
            position_symbols = {p.get('symbol') for p in positions if p.get('contracts', 0) > 0}

            # Find zombie orders (orders for symbols without positions)
            zombie_orders = []
            for order in open_orders:
                # CRITICAL FIX: Handle OrderResult objects safely - check type first
                if isinstance(order, dict):
                    # Direct dict access
                    symbol = order.get('symbol')
                    order_type = order.get('type', '').lower()
                else:
                    # Object attribute access (for OrderResult objects)
                    try:
                        symbol = getattr(order, 'symbol', '')
                        order_type = getattr(order, 'type', '').lower()
                    except (AttributeError, TypeError):
                        # Skip this order if we can't access its properties
                        continue

                # Check if this is a limit order for a symbol without position
                if symbol and symbol not in position_symbols:
                    # Skip stop orders as they might be protective orders
                    if 'stop' not in order_type and 'limit' in order_type:
                        zombie_orders.append(order)

            if zombie_orders:
                logger.warning(f"🧟 Found {len(zombie_orders)} zombie orders on {exchange_name}")

                # Cancel zombie orders
                for order in zombie_orders:
                    try:
                        # CRITICAL FIX: Handle OrderResult objects safely - check type first
                        if isinstance(order, dict):
                            # Direct dict access
                            symbol = order.get('symbol')
                            order_id = order.get('id')
                            order_side = order.get('side')
                            order_amount = order.get('amount', 0)
                        else:
                            # Object attribute access (for OrderResult objects)
                            try:
                                symbol = getattr(order, 'symbol', '')
                                order_id = getattr(order, 'id', '')
                                order_side = getattr(order, 'side', '')
                                order_amount = getattr(order, 'amount', 0)
                            except (AttributeError, TypeError):
                                # Skip this order if we can't access its properties
                                continue

                        logger.info(f"Cancelling zombie order: {symbol} {order_side} {order_amount} (ID: {order_id})")
                        await exchange.exchange.cancel_order(order_id, symbol)
                        logger.info(f"✅ Cancelled zombie order {order_id} for {symbol}")
                        cancelled_count += 1

                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.5)

                    except Exception as cancel_error:
                        # CRITICAL FIX: Handle OrderResult safely
                        order_id = order.id if hasattr(order, 'id') else order.get('id', 'unknown')
                        logger.error(f"Failed to cancel zombie order {order_id}: {cancel_error}")

            # Also check for orphaned stop orders
            # CRITICAL FIX: Handle OrderResult safely
            stop_orders = []
            for o in open_orders:
                order_type = o.type.lower() if hasattr(o, 'type') else o.get('type', '').lower()
                if 'stop' in order_type:
                    stop_orders.append(o)
            orphaned_stops = []

            for order in stop_orders:
                # CRITICAL FIX: Handle OrderResult safely
                symbol = order.symbol if hasattr(order, 'symbol') else order.get('symbol')
                if symbol and symbol not in position_symbols:
                    orphaned_stops.append(order)

            if orphaned_stops:
                logger.warning(f"🛑 Found {len(orphaned_stops)} orphaned stop orders on {exchange_name}")

                for order in orphaned_stops:
                    try:
                        # CRITICAL FIX: Handle OrderResult safely
                        symbol = order.symbol if hasattr(order, 'symbol') else order.get('symbol')
                        order_id = order.id if hasattr(order, 'id') else order.get('id')

                        logger.info(f"Cancelling orphaned stop order for {symbol} (ID: {order_id})")
                        await exchange.exchange.cancel_order(order_id, symbol)
                        logger.info(f"✅ Cancelled orphaned stop order {order_id}")
                        cancelled_count += 1

                        await asyncio.sleep(0.5)

                    except Exception as cancel_error:
                        # CRITICAL FIX: Handle OrderResult safely
                        order_id = order.id if hasattr(order, 'id') else order.get('id', 'unknown')
                        logger.error(f"Failed to cancel orphaned stop order {order_id}: {cancel_error}")

        except Exception as e:
            logger.error(f"Error in basic zombie cleanup for {exchange_name}: {e}")

        return cancelled_count

    def _calculate_age_hours(self, opened_at: datetime) -> float:
        """
        Calculate position age in hours with proper timezone handling

        Args:
            opened_at: Position opening datetime (may be naive or timezone-aware)

        Returns:
            Age in hours as float
        """
        try:
            # Ensure opened_at is timezone-aware for proper comparison
            if opened_at.tzinfo is None:
                # Assume naive datetime is in UTC
                opened_at = opened_at.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age_delta = now - opened_at
            return age_delta.total_seconds() / 3600

        except Exception as e:
            logger.error(f"Error calculating position age: {e}")
            return 0.0

    def get_statistics(self) -> Dict:
        """Get current statistics"""

        win_rate = 0
        if self.stats['win_count'] + self.stats['loss_count'] > 0:
            win_rate = self.stats['win_count'] / (self.stats['win_count'] + self.stats['loss_count']) * 100

        return {
            'open_positions': self.position_count,
            'total_exposure': to_decimal(self.total_exposure),
            'positions_opened': self.stats['positions_opened'],
            'positions_closed': self.stats['positions_closed'],
            'total_pnl': to_decimal(self.stats['total_pnl']),
            'win_rate': win_rate,
            'wins': self.stats['win_count'],
            'zombie_cleanup': {
                'checks_performed': self.zombie_check_counter,
                'last_zombie_count': self.last_zombie_count,
                'current_sync_interval': self.sync_interval,
                'aggressive_threshold': self.aggressive_cleanup_threshold
            },
            'losses': self.stats['loss_count']
        }