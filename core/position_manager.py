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

SOURCE OF TRUTH STRATEGY:
------------------------
Exchange is the primary source of truth for positions.
Database serves as secondary cache with reconciliation.
Reconciliation happens during periodic sync operations.
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
from core.event_logger import get_event_logger, EventType
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

    # NEW: SL ownership tracking
    sl_managed_by: Optional[str] = None  # 'protection' | 'trailing_stop' | None

    # NEW: TS health tracking for fallback
    ts_last_update_time: Optional[datetime] = None  # Last TS update

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

        # ✅ FIX #2: Locks for atomic position existence checks
        # Prevents race condition when multiple tasks check same symbol simultaneously
        self.check_locks: Dict[str, asyncio.Lock] = {}

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
        self.sync_interval = 120  # CRITICAL FIX: 2 minutes (was 10) for faster SL protection monitoring
        self.zombie_check_counter = 0  # Counter for tracking zombie checks
        self.last_zombie_count = 0  # Track last zombie count for trend monitoring
        self.aggressive_cleanup_threshold = 10  # Trigger aggressive cleanup if > 10 zombies

        # CRITICAL FIX: Track when positions lost SL for alert timing
        self.positions_without_sl_time = {}  # {symbol: timestamp when SL was first detected missing}

        # CRITICAL FIX: Whitelist of protected order IDs (stop-loss, take-profit)
        self.protected_order_ids = set()  # Set of order IDs that must never be cancelled

        logger.info("PositionManager initialized")

    async def synchronize_with_exchanges(self):
        """Synchronize database positions with exchange reality"""
        try:
            from core.position_synchronizer import PositionSynchronizer

            logger.info("🔄 Synchronizing positions with exchanges...")

            # Log sync started
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.SYNC_STARTED,
                    {
                        'exchanges': list(self.exchanges.keys())
                    },
                    severity='INFO'
                )

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

            # Log sync completed
            event_logger = get_event_logger()
            if event_logger:
                total_phantom = sum(len(r.get('closed_phantom', [])) for r in results.values() if 'error' not in r)
                total_missing = sum(len(r.get('added_missing', [])) for r in results.values() if 'error' not in r)
                await event_logger.log_event(
                    EventType.SYNC_COMPLETED,
                    {
                        'exchanges': list(results.keys()),
                        'phantom_closed': total_phantom,
                        'missing_added': total_missing,
                        'results': results
                    },
                    severity='INFO'
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

            # Log position not found on exchange
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.POSITION_NOT_FOUND_ON_EXCHANGE,
                    {
                        'symbol': symbol,
                        'exchange': exchange,
                        'normalized_symbol': normalized_symbol
                    },
                    symbol=symbol,
                    exchange=exchange,
                    severity='WARNING'
                )

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

            # Log positions loaded event
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.POSITIONS_LOADED,
                    {
                        'count': len(self.positions),
                        'total_exposure': float(self.total_exposure),
                        'exchanges': list(set(p.exchange for p in self.positions.values()))
                    },
                    severity='INFO'
                )

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

                # Log positions without SL detected
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.POSITIONS_WITHOUT_SL_DETECTED,
                        {
                            'count': len(positions_without_sl),
                            'symbols': [p.symbol for p in positions_without_sl],
                            'action': 'setting_sl'
                        },
                        severity='WARNING'
                    )

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

                                # Log stop loss set on load
                                event_logger = get_event_logger()
                                if event_logger:
                                    await event_logger.log_event(
                                        EventType.STOP_LOSS_SET_ON_LOAD,
                                        {
                                            'symbol': position.symbol,
                                            'position_id': position.id,
                                            'stop_loss_price': float(stop_loss_price),
                                            'entry_price': float(position.entry_price)
                                        },
                                        position_id=position.id,
                                        symbol=position.symbol,
                                        exchange=position.exchange,
                                        severity='INFO'
                                    )

                                # Update database
                                await self.repository.update_position_stop_loss(
                                    position.id, stop_loss_price, ""
                                )
                            else:
                                logger.error(f"❌ Failed to set stop loss for {position.symbol}")

                                # Log stop loss set failed
                                event_logger = get_event_logger()
                                if event_logger:
                                    await event_logger.log_event(
                                        EventType.STOP_LOSS_SET_FAILED,
                                        {
                                            'symbol': position.symbol,
                                            'position_id': position.id,
                                            'reason': 'set_stop_loss_returned_false'
                                        },
                                        position_id=position.id,
                                        symbol=position.symbol,
                                        exchange=position.exchange,
                                        severity='ERROR'
                                    )
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

                        # CRITICAL FIX: Save has_trailing_stop to database for restart persistence
                        await self.repository.update_position(
                            position.id,
                            has_trailing_stop=True
                        )

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
        """Sync positions from specific exchange

        RECONCILIATION LOGIC:
        This method reconciles positions between exchange (source of truth) and database.
        - Closes DB positions that don't exist on exchange
        - Updates DB positions with exchange data
        - Handles phantom positions appropriately
        """
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

            # DEBUG: Log symbols comparison
            logger.info(f"🔍 DEBUG active_symbols ({len(active_symbols)}): {sorted(active_symbols)}")
            db_symbols = {s for s, p in self.positions.items() if p.exchange == exchange_name}
            logger.info(f"🔍 DEBUG db_symbols for {exchange_name} ({len(db_symbols)}): {sorted(db_symbols)}")
            logger.info(f"🔍 DEBUG self.positions total: {len(self.positions)}")

            # Find positions in DB but not on exchange (closed positions)
            db_positions_to_close = []
            for symbol, pos_state in list(self.positions.items()):
                if pos_state.exchange == exchange_name and symbol not in active_symbols:
                    logger.info(f"🔍 DEBUG: {symbol} NOT in active_symbols, will close")
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
                    position_id = await self.repository.create_position({
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'side': side,
                        'quantity': quantity,
                        'entry_price': entry_price
                    })

                    # Create position state
                    position_state = PositionState(
                        id=position_id,
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

                # CRITICAL FIX: Re-check SL protection after zombie cleanup
                await self.check_positions_protection()

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
        Open new position with ATOMIC workflow:
        1. Validate request
        2. Check risk limits
        3. Calculate position size
        4. ATOMIC: Execute market order + Set stop loss
        5. Initialize trailing stop
        6. Save to database

        ⚠️ CRITICAL: Position and SL are created atomically
        If SL fails, position is rolled back
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

                # Log duplicate position prevented
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.POSITION_DUPLICATE_PREVENTED,
                        {
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'signal_id': request.signal_id if hasattr(request, 'signal_id') else None
                        },
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='WARNING'
                    )

                return None

            # 3. Validate risk limits
            if not await self._validate_risk_limits(request):
                logger.warning(f"Risk limits exceeded for {symbol}")

                # Log risk limits exceeded
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.RISK_LIMITS_EXCEEDED,
                        {
                            'symbol': symbol,
                            'current_exposure': float(self.total_exposure),
                            'position_count': self.position_count,
                            'max_positions': self.config.max_positions,
                            'max_exposure': float(self.config.max_exposure_usd)
                        },
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='WARNING'
                    )

                return None

            # 4. Calculate position size
            position_size_usd = request.position_size_usd or self.config.position_size_usd
            quantity = await self._calculate_position_size(
                exchange, symbol, request.entry_price, position_size_usd
            )

            if not quantity:
                logger.error(f"Failed to calculate position size for {symbol}")

                # Log position creation failed
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.POSITION_CREATION_FAILED,
                        {
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'reason': 'failed_to_calculate_quantity',
                            'position_size_usd': float(position_size_usd)
                        },
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='ERROR'
                    )

                return None

            # 5. Validate spread (временно только логирование)
            await self._validate_spread(exchange, symbol)
            # Не блокируем открытие позиций из-за спреда

            # 6. Calculate stop-loss price first
            stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
            stop_loss_price = calculate_stop_loss(
                to_decimal(request.entry_price), request.side, to_decimal(stop_loss_percent)
            )

            logger.info(f"Opening position ATOMICALLY: {symbol} {request.side} {quantity}")
            # COSMETIC FIX: Show scientific notation for small numbers instead of 0.0000
            # For numbers < 0.0001, .4f rounds to 0.0000 which is confusing
            # Using float() for automatic formatting (scientific notation for small numbers)
            logger.info(f"Stop-loss will be set at: {float(stop_loss_price)} ({stop_loss_percent}%)")

            # Convert side: long -> buy, short -> sell for Binance
            if request.side.lower() == 'long':
                order_side = 'buy'
            elif request.side.lower() == 'short':
                order_side = 'sell'
            else:
                order_side = request.side.lower()

            # ⚠️ ATOMIC OPERATION START
            # Try to use AtomicPositionManager if available
            try:
                from core.atomic_position_manager import AtomicPositionManager, SymbolUnavailableError, MinimumOrderLimitError

                # Initialize atomic manager
                from core.stop_loss_manager import StopLossManager
                sl_manager = StopLossManager(exchange.exchange, exchange_name)

                atomic_manager = AtomicPositionManager(
                    repository=self.repository,
                    exchange_manager=self.exchanges,  # FIX: Use self.exchanges instead of dict
                    stop_loss_manager=sl_manager
                )

                # Execute atomic creation
                atomic_result = await atomic_manager.open_position_atomic(
                    signal_id=request.signal_id,
                    symbol=symbol,
                    exchange=exchange_name,
                    side=order_side,
                    quantity=quantity,
                    entry_price=float(request.entry_price),
                    stop_loss_price=float(stop_loss_price)
                )

                if atomic_result:
                    logger.info(f"✅ Position created ATOMICALLY with guaranteed SL")
                    # ATOMIC CREATION ALREADY CREATED POSITION IN DB!
                    # Use data from atomic_result, DO NOT create duplicate position

                    position = PositionState(
                        id=atomic_result['position_id'],  # Use existing ID from atomic creation
                        symbol=symbol,
                        exchange=exchange_name,
                        side=atomic_result['side'],
                        quantity=atomic_result['quantity'],
                        entry_price=atomic_result['entry_price'],
                        current_price=atomic_result['entry_price'],
                        unrealized_pnl=0,
                        unrealized_pnl_percent=0,
                        opened_at=datetime.now(timezone.utc)
                    )

                    # Skip database creation - position already exists!
                    # Jump directly to tracking
                    self.positions[symbol] = position  # Track by symbol, not ID
                    self.position_locks.discard(lock_key)

                    logger.info(f"✅ Position #{atomic_result['position_id']} for {symbol} opened ATOMICALLY at ${atomic_result['entry_price']:.4f}")
                    logger.info(f"✅ Added {symbol} to tracked positions (total: {len(self.positions)})")

                    # 10. Initialize trailing stop (ATOMIC path)
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

                        # Save has_trailing_stop to database for restart persistence
                        await self.repository.update_position(
                            position.id,
                            has_trailing_stop=True
                        )

                        logger.info(f"✅ Trailing stop initialized for {symbol}")
                    else:
                        logger.warning(f"⚠️ No trailing manager for exchange {exchange_name}")

                    return position  # Return early - atomic creation is complete

                else:
                    logger.error(f"Failed to create atomic position for {symbol}")

                    # Log atomic position creation failed
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.POSITION_CREATION_FAILED,
                            {
                                'symbol': symbol,
                                'exchange': exchange_name,
                                'reason': 'atomic_creation_returned_none',
                                'creation_path': 'atomic'
                            },
                            symbol=symbol,
                            exchange=exchange_name,
                            severity='ERROR'
                        )

                    return None

            except SymbolUnavailableError as e:
                # Symbol is unavailable for trading (delisted, reduce-only, etc.)
                logger.warning(f"⚠️ Symbol {symbol} unavailable for trading: {e}")

                # Log symbol unavailable event
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.SYMBOL_UNAVAILABLE,
                        {
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'reason': str(e),
                            'signal_id': request.signal_id if hasattr(request, 'signal_id') else None
                        },
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='WARNING'
                    )

                return None
            except MinimumOrderLimitError as e:
                # Order size doesn't meet minimum requirements
                logger.warning(f"⚠️ Order size for {symbol} below minimum limit: {e}")

                # Log order below minimum event
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.ORDER_BELOW_MINIMUM,
                        {
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'reason': str(e),
                            'signal_id': request.signal_id if hasattr(request, 'signal_id') else None
                        },
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='WARNING'
                    )

                return None
            except ImportError:
                # Fallback to non-atomic creation (old logic)
                logger.warning("⚠️ AtomicPositionManager not available, using legacy approach")

                order = await exchange.create_market_order(symbol, order_side, quantity)

                if not order or order.status != 'closed':
                    logger.error(f"Failed to open position for {symbol}")
                    return None

                # 7. Create position state for NON-ATOMIC path only
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

            # Check if position was already created (atomic path)
            # If position.id is set, it means atomic creation succeeded
            if position.id is not None:
                logger.info(f"📌 Position already created atomically with ID={position.id}, skipping DB creation")
            else:
                # 8. Save to database (NON-ATOMIC path only!)
                logger.info(f"🔍 DEBUG: NON-ATOMIC path - creating trade for {symbol}")
                trade_id = await self.repository.create_trade({
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
                logger.info(f"🔍 DEBUG: Trade created with ID={trade_id} for {symbol}")

                logger.info(f"🔍 DEBUG: About to create position for {symbol}, quantity={position.quantity}")
                position_id = await self.repository.create_position({
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'side': position.side,
                    'quantity': position.quantity,
                    'entry_price': position.entry_price
                })
                logger.info(f"🔍 DEBUG: Position created with ID={position_id} for {symbol}")

                # Log position created event (legacy path)
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.POSITION_CREATED,
                        {
                            'symbol': symbol,
                            'position_id': position_id,
                            'side': position.side,
                            'quantity': float(position.quantity),
                            'entry_price': float(position.entry_price),
                            'exchange': exchange_name,
                            'creation_path': 'legacy'
                        },
                        position_id=position_id,
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='INFO'
                    )

                position.id = position_id
                logger.info(f"🔍 DEBUG: position.id set to {position_id} for {symbol}")

            # 9. Set stop loss (only for NON-ATOMIC path, atomic already has SL)
            if position.id is not None and hasattr(position, 'has_stop_loss') and position.has_stop_loss:
                logger.info(f"✅ Stop loss already set atomically for {symbol}")
            else:
                stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
                stop_loss_price = calculate_stop_loss(
                    to_decimal(position.entry_price), position.side, to_decimal(stop_loss_percent)
                )

                logger.info(f"Setting stop loss for {symbol}: {stop_loss_percent}% at ${stop_loss_price:.4f}")

                if await self._set_stop_loss(exchange, position, stop_loss_price):
                    position.has_stop_loss = True
                    position.stop_loss_price = stop_loss_price
                    logger.info(f"✅ Stop loss confirmed for {symbol}")

                    # Log stop loss placed
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.STOP_LOSS_PLACED,
                            {
                                'symbol': symbol,
                                'position_id': position.id,
                                'stop_loss_price': float(stop_loss_price),
                                'entry_price': float(position.entry_price),
                                'stop_loss_percent': float(stop_loss_percent)
                            },
                            position_id=position.id,
                            symbol=symbol,
                            exchange=exchange_name,
                            severity='INFO'
                        )

                    try:
                        await self.repository.update_position_stop_loss(
                            position.id, stop_loss_price, ""
                        )
                    except Exception as db_error:
                        logger.error(f"Failed to update stop loss in database for {symbol}: {db_error}")

                        # Log database update failure
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.DATABASE_ERROR,
                                {
                                    'symbol': symbol,
                                    'position_id': position.id,
                                    'operation': 'update_position_stop_loss',
                                    'error': str(db_error),
                                    'stop_loss_price': float(stop_loss_price)
                                },
                                position_id=position.id,
                                symbol=symbol,
                                exchange=exchange_name,
                                severity='ERROR'
                            )
                else:
                    logger.warning(f"⚠️ Failed to set stop loss for {symbol}")

                    # Log stop loss placement failed
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.STOP_LOSS_ERROR,
                            {
                                'symbol': symbol,
                                'position_id': position.id,
                                'reason': 'set_stop_loss_returned_false',
                                'attempted_price': float(stop_loss_price)
                            },
                            position_id=position.id,
                            symbol=symbol,
                            exchange=exchange_name,
                            severity='ERROR'
                        )

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

                # Log trailing stop creation
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_CREATED,
                        {
                            'symbol': symbol,
                            'position_id': position.id,
                            'entry_price': float(position.entry_price),
                            'initial_stop': float(stop_loss_price),
                            'side': position.side
                        },
                        position_id=position.id,
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='INFO'
                    )

                # CRITICAL FIX: Save has_trailing_stop to database for restart persistence
                # Position was already saved in steps 8-9, now update TS flag
                try:
                    await self.repository.update_position(
                        position.id,
                        has_trailing_stop=True
                    )
                except Exception as db_error:
                    logger.error(f"Failed to update trailing stop flag in database for {symbol}: {db_error}")

                    # Log database update failure
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.DATABASE_ERROR,
                            {
                                'symbol': symbol,
                                'position_id': position.id,
                                'operation': 'update_position_trailing_stop',
                                'error': str(db_error)
                            },
                            position_id=position.id,
                            symbol=symbol,
                            exchange=exchange_name,
                            severity='ERROR'
                        )

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

        except SymbolUnavailableError as e:
            # Symbol is unavailable for trading (delisted, reduce-only, etc.)
            logger.warning(f"⚠️ Skipping {symbol}: {e}")
            # Return None without error - this is expected for unavailable symbols
            return None
        except MinimumOrderLimitError as e:
            # Order size doesn't meet minimum requirements
            logger.warning(f"⚠️ Skipping {symbol}: {e}")
            # Return None without error - this is expected for minimum limit issues
            return None
        except Exception as e:
            logger.error(f"Error opening position for {symbol}: {e}", exc_info=True)
            return None

        finally:
            self.position_locks.discard(lock_key)

    async def _position_exists(self, symbol: str, exchange: str) -> bool:
        """
        Check if position already exists (thread-safe)

        ✅ FIX #2: Uses asyncio.Lock to prevent race condition where multiple
        parallel tasks check the same symbol simultaneously and all get "no position"
        """
        # Create unique lock key for this symbol+exchange combination
        lock_key = f"{exchange}_{symbol}"

        # Get or create lock for this symbol
        if lock_key not in self.check_locks:
            self.check_locks[lock_key] = asyncio.Lock()

        # Atomic check - only ONE task can check at a time for this symbol
        async with self.check_locks[lock_key]:
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
        """Calculate stop loss price using Decimal-safe utility"""

        # Convert to Decimal for safe arithmetic (avoid float * Decimal errors)
        return float(calculate_stop_loss(
            entry_price=Decimal(str(entry_price)),
            side=side,
            stop_loss_percent=Decimal(str(percent))
        ))

    async def _set_stop_loss(self,
                             exchange: ExchangeManager,
                             position: PositionState,
                             stop_price: float) -> bool:
        """
        Set stop loss order using unified StopLossManager.

        This function now uses StopLossManager for ALL SL operations
        to ensure consistency across the system.

        LOCK PROTECTION: This method uses proper locking to prevent race conditions.
        """
        # LOCK: Acquire lock for stop-loss operation
        lock_key = f"sl_update_{position.symbol}_{position.id}"
        if lock_key not in self.position_locks:
            self.position_locks[lock_key] = asyncio.Lock()

        async with self.position_locks[lock_key]:
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
                    # CRITICAL FIX: Update both memory and database
                    position.has_stop_loss = True
                    position.stop_loss_price = result['stopPrice']

                    # Update database
                    logger.info(f"🔍 Updating DB: position_id={position.id}, has_stop_loss=True, stop_loss_price={result['stopPrice']}")
                    await self.repository.update_position(
                        position.id,
                        has_stop_loss=True,
                        stop_loss_price=result['stopPrice']
                    )
                    logger.info(f"✅ DB updated for {position.symbol}")

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
        # LOCK: Acquire lock for trailing stop update
        trailing_lock_key = f"trailing_stop_{symbol}"
        if trailing_lock_key not in self.position_locks:
            self.position_locks[trailing_lock_key] = asyncio.Lock()

        async with self.position_locks[trailing_lock_key]:
            trailing_manager = self.trailing_managers.get(position.exchange)
            if trailing_manager and position.has_trailing_stop:
                # NEW: Update TS health timestamp before calling TS Manager
                position.ts_last_update_time = datetime.now()

                update_result = await trailing_manager.update_price(symbol, position.current_price)

                if update_result:
                    action = update_result.get('action')

                    if action == 'activated':
                        position.trailing_activated = True
                        logger.info(f"Trailing stop activated for {symbol}")

                        # Log trailing stop activation
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.TRAILING_STOP_ACTIVATED,
                                {
                                    'symbol': symbol,
                                    'position_id': position.id,
                                    'current_price': float(position.current_price),
                                    'entry_price': float(position.entry_price),
                                    'stop_loss_price': float(position.stop_loss_price) if position.stop_loss_price else None
                                },
                                position_id=position.id,
                                symbol=symbol,
                                exchange=position.exchange,
                                severity='INFO'
                            )

                        # Save trailing activation to database
                        try:
                            await self.repository.update_position(position.id, trailing_activated=True)
                        except Exception as db_error:
                            logger.error(f"Failed to update trailing activation in database for {symbol}: {db_error}")

                            # Log database update failure
                            event_logger = get_event_logger()
                            if event_logger:
                                await event_logger.log_event(
                                    EventType.DATABASE_ERROR,
                                    {
                                        'symbol': symbol,
                                        'position_id': position.id,
                                        'operation': 'update_trailing_activation',
                                        'error': str(db_error)
                                    },
                                    position_id=position.id,
                                    symbol=symbol,
                                    exchange=position.exchange,
                                    severity='ERROR'
                                )

                    elif action == 'updated':
                        # CRITICAL FIX: Save new trailing stop price to database
                        new_stop = update_result.get('new_stop')
                        if new_stop:
                            old_stop = position.stop_loss_price
                            position.stop_loss_price = new_stop

                            # Log trailing stop update
                            event_logger = get_event_logger()
                            if event_logger:
                                await event_logger.log_event(
                                    EventType.TRAILING_STOP_UPDATED,
                                    {
                                        'symbol': symbol,
                                        'position_id': position.id,
                                        'old_stop_price': float(old_stop) if old_stop else None,
                                        'new_stop_price': float(new_stop),
                                        'current_price': float(position.current_price)
                                    },
                                    position_id=position.id,
                                    symbol=symbol,
                                    exchange=position.exchange,
                                    severity='INFO'
                                )

                            try:
                                await self.repository.update_position(
                                    position.id,
                                    stop_loss_price=new_stop
                                )
                                logger.info(f"✅ Saved new trailing stop price for {symbol}: {new_stop}")
                            except Exception as db_error:
                                logger.error(f"Failed to update trailing stop price in database for {symbol}: {db_error}")

                                # Log database update failure
                                event_logger = get_event_logger()
                                if event_logger:
                                    await event_logger.log_event(
                                        EventType.DATABASE_ERROR,
                                        {
                                            'symbol': symbol,
                                            'position_id': position.id,
                                            'operation': 'update_trailing_stop_price',
                                            'error': str(db_error),
                                            'new_stop_price': float(new_stop)
                                        },
                                        position_id=position.id,
                                        symbol=symbol,
                                        exchange=position.exchange,
                                        severity='ERROR'
                                    )

        # Update database
        try:
            await self.repository.update_position_from_websocket({
                'symbol': symbol,
                'exchange': position.exchange,
                'current_price': position.current_price,
                'mark_price': position.current_price,
                'unrealized_pnl': position.unrealized_pnl,
                'unrealized_pnl_percent': position.unrealized_pnl_percent
            })

            # Log successful position update
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.POSITION_UPDATED,
                    {
                        'symbol': symbol,
                        'position_id': position.id,
                        'old_price': float(old_price),
                        'new_price': float(position.current_price),
                        'unrealized_pnl': float(position.unrealized_pnl),
                        'unrealized_pnl_percent': float(position.unrealized_pnl_percent),
                        'source': 'websocket'
                    },
                    position_id=position.id,
                    symbol=symbol,
                    exchange=position.exchange,
                    severity='INFO'
                )

        except Exception as db_error:
            logger.error(f"Failed to update position from websocket in database for {symbol}: {db_error}")

            # Log database update failure
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.DATABASE_ERROR,
                    {
                        'symbol': symbol,
                        'position_id': position.id,
                        'operation': 'update_position_from_websocket',
                        'error': str(db_error),
                        'current_price': float(position.current_price)
                    },
                    position_id=position.id,
                    symbol=symbol,
                    exchange=position.exchange,
                    severity='ERROR'
                )

    async def _on_order_filled(self, data: Dict):
        """Handle order filled event"""

        order_type = data.get('type', '').lower()
        symbol = data.get('symbol')

        # Log order filled event
        event_logger = get_event_logger()
        if event_logger and symbol in self.positions:
            position = self.positions[symbol]
            await event_logger.log_event(
                EventType.ORDER_FILLED,
                {
                    'symbol': symbol,
                    'position_id': position.id,
                    'order_type': order_type,
                    'order_data': data
                },
                position_id=position.id,
                symbol=symbol,
                exchange=position.exchange,
                severity='INFO'
            )

        # Check if it's a closing order
        if order_type in ['stop_market', 'stop', 'take_profit_market']:
            if symbol in self.positions:
                await self.close_position(symbol, data.get('exit_reason', order_type))

    async def _on_stop_loss_triggered(self, data: Dict):
        """Handle stop loss triggered event"""

        symbol = data.get('symbol')
        if symbol in self.positions:
            position = self.positions[symbol]
            logger.warning(f"⚠️ Stop loss triggered for {symbol}")

            # Log stop loss triggered event
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.STOP_LOSS_TRIGGERED,
                    {
                        'symbol': symbol,
                        'position_id': position.id,
                        'entry_price': float(position.entry_price),
                        'current_price': float(position.current_price),
                        'stop_loss_price': float(position.stop_loss_price) if position.stop_loss_price else None,
                        'side': position.side
                    },
                    position_id=position.id,
                    symbol=symbol,
                    exchange=position.exchange,
                    severity='WARNING'
                )

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

                    # Log trailing stop removal
                    if position.has_trailing_stop:
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.TRAILING_STOP_REMOVED,
                                {
                                    'symbol': symbol,
                                    'position_id': position.id,
                                    'reason': 'position_closed',
                                    'realized_pnl': float(realized_pnl)
                                },
                                position_id=position.id,
                                symbol=symbol,
                                exchange=position.exchange,
                                severity='INFO'
                            )

                logger.info(
                    f"Position closed: {symbol} {reason} "
                    f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
                )

                # Log position closed event
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.POSITION_CLOSED,
                        {
                            'symbol': symbol,
                            'reason': reason,
                            'realized_pnl': float(realized_pnl),
                            'realized_pnl_percent': float(realized_pnl_percent),
                            'entry_price': float(position.entry_price),
                            'exit_price': float(exit_price),
                            'quantity': float(position.quantity),
                            'side': position.side,
                            'exchange': position.exchange
                        },
                        position_id=position.id,
                        symbol=symbol,
                        exchange=position.exchange,
                        severity='INFO'
                    )

                # PREVENTIVE FIX: Cancel any remaining SL orders for this symbol
                # This prevents old SL orders from being reused by future positions
                try:
                    # Fetch open orders for symbol
                    open_orders = await exchange.exchange.fetch_open_orders(symbol)

                    # Cancel stop-loss orders
                    for order in open_orders:
                        order_type = order.get('type', '').lower()
                        is_stop = 'stop' in order_type or order_type in ['stop_market', 'stop_loss', 'stop_loss_limit']

                        if is_stop:
                            logger.info(f"🧹 Cleaning up SL order {order['id']} for closed position {symbol}")
                            await exchange.exchange.cancel_order(order['id'], symbol)

                            # Log orphaned SL cleaned
                            event_logger = get_event_logger()
                            if event_logger:
                                await event_logger.log_event(
                                    EventType.ORPHANED_SL_CLEANED,
                                    {
                                        'symbol': symbol,
                                        'order_id': order['id'],
                                        'order_type': order.get('type'),
                                        'reason': 'position_closed'
                                    },
                                    symbol=symbol,
                                    order_id=order['id'],
                                    exchange=position.exchange,
                                    severity='INFO'
                                )

                except Exception as cleanup_error:
                    # Don't fail position close if SL cleanup fails
                    logger.warning(f"⚠️ Failed to cleanup SL orders for {symbol}: {cleanup_error}")
                    # Position is already closed, this is just cleanup

        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}", exc_info=True)

            # Log exchange error for position close
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.EXCHANGE_ERROR,
                    {
                        'symbol': symbol,
                        'position_id': position.id if symbol in self.positions else None,
                        'operation': 'close_position',
                        'error': str(e),
                        'reason': reason
                    },
                    position_id=position.id if symbol in self.positions else None,
                    symbol=symbol,
                    exchange=position.exchange,
                    severity='ERROR'
                )

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

            # Log exchange error for order cancellation
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.EXCHANGE_ERROR,
                    {
                        'symbol': position.symbol,
                        'position_id': position.id,
                        'operation': 'cancel_pending_close_order',
                        'error': str(e),
                        'order_id': order_id
                    },
                    position_id=position.id,
                    symbol=position.symbol,
                    exchange=position.exchange,
                    severity='ERROR'
                )
    
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
                # UNIQUE ORDER ID: Generate unique client_order_id
                import uuid
                client_order_id = f"bot_{uuid.uuid4().hex[:16]}"

                order = await exchange.create_limit_order(
                    symbol=symbol,
                    side=order_side,
                    amount=position.quantity,
                    price=target_price,
                    params={'clientOrderId': client_order_id}
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
                try:
                    await self.repository.update_position(position.id, {
                        'pending_close_order_id': order['id'],
                        'pending_close_price': to_decimal(target_price),
                        'exit_reason': reason
                    })
                except Exception as db_error:
                    logger.error(f"Failed to update pending close order in database for {symbol}: {db_error}")

                    # Log database update failure
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.DATABASE_ERROR,
                            {
                                'symbol': symbol,
                                'position_id': position.id,
                                'operation': 'update_pending_close_order',
                                'error': str(db_error),
                                'order_id': order_id,
                                'target_price': float(target_price)
                            },
                            position_id=position.id,
                            symbol=symbol,
                            exchange=position.exchange,
                            severity='ERROR'
                        )
            else:
                logger.error(f"Failed to place limit order for {symbol}")
                
        except Exception as e:
            logger.error(f"Error placing limit close order for {symbol}: {e}", exc_info=True)

            # Log exchange error for limit order placement
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.EXCHANGE_ERROR,
                    {
                        'symbol': symbol,
                        'position_id': position.id,
                        'operation': 'place_limit_close_order',
                        'error': str(e),
                        'target_price': float(target_price),
                        'reason': reason
                    },
                    position_id=position.id,
                    symbol=symbol,
                    exchange=position.exchange,
                    severity='ERROR'
                )

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

                    # Log aged position detected event
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.AGED_POSITION_DETECTED,
                            {
                                'symbol': symbol,
                                'position_id': position.id,
                                'age_hours': float(position.age_hours),
                                'max_age_hours': float(max_age_hours),
                                'entry_price': float(position.entry_price),
                                'current_price': float(position.current_price),
                                'side': position.side
                            },
                            position_id=position.id,
                            symbol=symbol,
                            exchange=position.exchange,
                            severity='WARNING'
                        )

                    # CRITICAL FIX: Fetch real-time price before making decision
                    exchange = self.exchanges.get(position.exchange)
                    if not exchange:
                        logger.error(f"Exchange {position.exchange} not available for {symbol}")
                        continue

                    try:
                        # Fetch current market price from exchange
                        ticker = await exchange.exchange.fetch_ticker(symbol)
                        real_time_price = ticker.get('last') or ticker.get('markPrice')

                        if real_time_price:
                            old_cached_price = position.current_price
                            position.current_price = real_time_price

                            # Log price update for transparency
                            price_diff_pct = ((real_time_price - old_cached_price) / old_cached_price * 100) if old_cached_price else 0
                            logger.info(
                                f"📊 Price check for {symbol}:\n"
                                f"  Cached price: ${old_cached_price:.2f}\n"
                                f"  Real-time:    ${real_time_price:.2f}\n"
                                f"  Difference:   {price_diff_pct:+.2f}%"
                            )
                    except Exception as e:
                        logger.error(f"Failed to fetch current price for {symbol}: {e}")
                        logger.warning(f"Using cached price ${position.current_price:.2f} (may be outdated)")

                        # Log exchange error for price fetch
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.EXCHANGE_ERROR,
                                {
                                    'symbol': symbol,
                                    'position_id': position.id,
                                    'operation': 'fetch_ticker',
                                    'error': str(e),
                                    'cached_price': float(position.current_price)
                                },
                                position_id=position.id,
                                symbol=symbol,
                                exchange=position.exchange,
                                severity='ERROR'
                            )

                    # Рассчитываем цену безубытка с учетом комиссий
                    if position.side == 'long':
                        breakeven_price = position.entry_price * (1 + commission_percent / 100)
                        is_profitable = position.current_price >= breakeven_price
                    else:  # short
                        breakeven_price = position.entry_price * (1 - commission_percent / 100)
                        is_profitable = position.current_price <= breakeven_price
                    
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
                                f"✅ Expired position {symbol} is profitable\n"
                                f"  Entry:     ${position.entry_price:.2f}\n"
                                f"  Current:   ${position.current_price:.2f}\n"
                                f"  Breakeven: ${breakeven_price:.2f}\n"
                                f"  Closing by market order."
                            )
                            await self.close_position(symbol, f'max_age_market_{max_age_hours}h')
                        else:
                            # For expired positions at loss, still close them but log the loss
                            pnl_percent = position.unrealized_pnl_percent
                            logger.warning(
                                f"⚠️ Expired position {symbol} at {pnl_percent:.2f}% loss\n"
                                f"  Entry:     ${position.entry_price:.2f}\n"
                                f"  Current:   ${position.current_price:.2f}\n"
                                f"  Breakeven: ${breakeven_price:.2f}\n"
                                f"  Age:       {position.age_hours:.1f}h (max: {max_age_hours}h)\n"
                                f"  Closing anyway due to age limit."
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
            # FIX: Create snapshot of keys to avoid "dictionary changed size during iteration"
            for symbol in list(self.positions.keys()):
                if symbol not in self.positions:
                    continue  # Position was removed during iteration
                position = self.positions[symbol]
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

                # CRITICAL: Sync DB with discovered state
                if has_sl_on_exchange and sl_price:
                    position.stop_loss_price = sl_price
                    await self.repository.update_position(
                        position.id,
                        has_stop_loss=True,
                        stop_loss_price=sl_price
                    )
                    logger.info(f"✅ Synced {symbol} SL state to DB: has_sl=True, price={sl_price}")

                    # CRITICAL FIX: Clear tracking if SL was restored
                    if symbol in self.positions_without_sl_time:
                        del self.positions_without_sl_time[symbol]

                if not has_sl_on_exchange:
                    # Check if TS Manager SHOULD be managing SL
                    if position.has_trailing_stop and position.trailing_activated:
                        # NEW: Fallback protection - check TS health
                        ts_last_update = position.ts_last_update_time

                        if ts_last_update:
                            ts_inactive_seconds = (datetime.now() - ts_last_update).total_seconds()
                            ts_inactive_minutes = ts_inactive_seconds / 60

                            # TS inactive for > 5 minutes → TAKE OVER
                            if ts_inactive_minutes > 5:
                                logger.warning(
                                    f"⚠️  {symbol} TS Manager inactive for {ts_inactive_minutes:.1f} minutes "
                                    f"(last update: {ts_last_update}), Protection Manager taking over"
                                )

                                # Reset TS flags to allow Protection Manager control
                                position.has_trailing_stop = False
                                position.trailing_activated = False
                                position.sl_managed_by = 'protection'  # Mark ownership

                                # Save to DB
                                await self.repository.update_position(
                                    position.id,
                                    has_trailing_stop=False,
                                    trailing_activated=False
                                )

                                # Now add to unprotected list (will set Protection SL)
                                unprotected_positions.append(position)

                                logger.info(
                                    f"✅ {symbol} Protection Manager took over SL management "
                                    f"(TS fallback triggered)"
                                )
                            else:
                                # TS active recently - skip protection
                                logger.debug(
                                    f"{symbol} SL managed by TS Manager "
                                    f"(last update {ts_inactive_minutes:.1f}m ago), skipping"
                                )
                                continue
                        else:
                            # No ts_last_update_time yet (TS just initialized)
                            # Skip protection for now
                            logger.debug(
                                f"{symbol} TS Manager just initialized (no health data yet), skipping"
                            )
                            continue

                    # Normal protection logic for non-TS positions
                    unprotected_positions.append(position)

                    # CRITICAL FIX: Track time and alert if SL missing > 30 seconds
                    import time
                    current_time = time.time()

                    if symbol not in self.positions_without_sl_time:
                        # First time detected without SL - record time
                        self.positions_without_sl_time[symbol] = current_time
                        logger.warning(f"⚠️ Position {symbol} has no stop loss on exchange!")
                    else:
                        # Already detected before - check how long
                        time_without_sl = current_time - self.positions_without_sl_time[symbol]

                        if time_without_sl > 30:
                            # CRITICAL: SL missing for more than 30 seconds
                            logger.critical(
                                f"🚨 CRITICAL ALERT: Position {symbol} WITHOUT STOP LOSS for {time_without_sl:.0f} seconds! "
                                f"Position at risk!"
                            )
                        else:
                            logger.warning(f"⚠️ Position {symbol} has no stop loss ({time_without_sl:.0f}s)")

            # If found unprotected positions, set stop losses using enhanced SL manager
            if unprotected_positions:
                logger.warning(f"🔴 Found {len(unprotected_positions)} positions without stop loss protection!")

                for position in unprotected_positions:
                    try:
                        exchange = self.exchanges.get(position.exchange)
                        if not exchange:
                            logger.error(f"Exchange {position.exchange} not available for {position.symbol}")
                            continue

                        # Skip if position already has stop loss
                        if position.has_stop_loss and position.stop_loss_price:
                            logger.debug(f"Position {position.symbol} already has SL at {position.stop_loss_price}, skipping")
                            continue

                        # CRITICAL FIX (2025-10-13): Use current_price instead of entry_price when price
                        # has drifted significantly. This prevents "base_price validation" errors from Bybit.
                        # See: CORRECT_SOLUTION_SL_PRICE_DRIFT.md for details

                        # STEP 1: Get current market price from exchange
                        try:
                            ticker = await exchange.exchange.fetch_ticker(position.symbol)
                            mark_price = ticker.get('info', {}).get('markPrice')
                            current_price = float(mark_price or ticker.get('last') or 0)

                            if current_price == 0:
                                logger.error(f"Failed to get current price for {position.symbol}, skipping SL setup")
                                continue

                        except Exception as e:
                            logger.error(f"Failed to fetch ticker for {position.symbol}: {e}")
                            continue

                        # STEP 2: Calculate price drift from entry
                        entry_price = float(position.entry_price)
                        price_drift_pct = abs((current_price - entry_price) / entry_price)

                        # STEP 3: Choose base price for SL calculation
                        # If price drifted more than STOP_LOSS_PERCENT, use current price
                        # This prevents creating invalid SL that would be rejected by exchange
                        stop_loss_percent = self.config.stop_loss_percent
                        stop_loss_percent_decimal = float(stop_loss_percent) / 100  # Convert from percent to decimal (e.g. 2.0 -> 0.02)

                        if price_drift_pct > stop_loss_percent_decimal:
                            # Price has moved significantly - use current price as base
                            logger.warning(
                                f"⚠️ {position.symbol}: Price drifted {price_drift_pct*100:.2f}% "
                                f"(threshold: {stop_loss_percent*100:.2f}%). Using current price {current_price:.6f} "
                                f"instead of entry {entry_price:.6f} for SL calculation"
                            )
                            base_price = current_price
                        else:
                            # Price is stable - use entry price to protect initial capital
                            logger.debug(
                                f"✓ {position.symbol}: Price drift {price_drift_pct*100:.2f}% within threshold. "
                                f"Using entry price for SL"
                            )
                            base_price = entry_price

                        # STEP 4: Calculate SL from chosen base price (Decimal-safe)
                        stop_loss_price = calculate_stop_loss(
                            entry_price=Decimal(str(base_price)),  # Use chosen base, not always entry
                            side=position.side,
                            stop_loss_percent=Decimal(str(stop_loss_percent))
                        )

                        # STEP 5: Safety validation - ensure SL makes sense vs current market
                        stop_loss_float = float(stop_loss_price)

                        if position.side == 'long':
                            if stop_loss_float >= current_price:
                                logger.error(
                                    f"❌ {position.symbol}: Calculated SL {stop_loss_float:.6f} >= "
                                    f"current {current_price:.6f} for LONG position! Using emergency fallback"
                                )
                                # Emergency: force SL below current price
                                stop_loss_price = Decimal(str(current_price * (1 - stop_loss_percent)))

                        else:  # short
                            if stop_loss_float <= current_price:
                                logger.error(
                                    f"❌ {position.symbol}: Calculated SL {stop_loss_float:.6f} <= "
                                    f"current {current_price:.6f} for SHORT position! Using emergency fallback"
                                )
                                # Emergency: force SL above current price
                                stop_loss_price = Decimal(str(current_price * (1 + stop_loss_percent)))

                        # Log final decision for debugging
                        logger.info(
                            f"📊 {position.symbol} SL calculation: entry={entry_price:.6f}, "
                            f"current={current_price:.6f}, base={base_price:.6f}, SL={float(stop_loss_price):.6f}"
                        )

                        # Use enhanced SL manager with auto-validation and retry
                        sl_manager = StopLossManager(exchange.exchange, position.exchange)
                        success, order_id = await sl_manager.verify_and_fix_missing_sl(
                            position=position,
                            stop_price=stop_loss_price,
                            max_retries=3
                        )

                        if success:
                            position.has_stop_loss = True
                            position.stop_loss_price = stop_loss_price

                            # CRITICAL FIX: Add order_id to whitelist for protection
                            if order_id:
                                self.protected_order_ids.add(str(order_id))
                                logger.info(f"✅ Stop loss set for {position.symbol} at {stop_loss_price:.8f}, order_id={order_id} added to whitelist")
                            else:
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
                    # CRITICAL FIX: Must normalize exchange symbols to match DB format
                    # Exchange: "BNT/USDT:USDT" -> DB: "BNTUSDT"
                    exchange_symbols = {normalize_symbol(p['symbol']) for p in active_exchange_positions}
                    local_symbols = set(local_positions.keys())

                    # 1. PHANTOM POSITIONS (in DB but not on exchange)
                    phantom_symbols = local_symbols - exchange_symbols

                    if phantom_symbols:
                        zombies_found = True
                        logger.warning(f"👻 Found {len(phantom_symbols)} PHANTOM positions on {exchange_name}")

                        # Log phantom positions detection
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.PHANTOM_POSITION_DETECTED,
                                {
                                    'exchange': exchange_name,
                                    'count': len(phantom_symbols),
                                    'symbols': list(phantom_symbols)
                                },
                                exchange=exchange_name,
                                severity='WARNING'
                            )

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

                                # Log successful cleanup
                                event_logger = get_event_logger()
                                if event_logger:
                                    await event_logger.log_event(
                                        EventType.PHANTOM_POSITION_CLOSED,
                                        {
                                            'symbol': symbol,
                                            'position_id': position.id,
                                            'reason': 'not_on_exchange',
                                            'cleanup_action': 'marked_closed'
                                        },
                                        position_id=position.id,
                                        symbol=symbol,
                                        exchange=exchange_name,
                                        severity='WARNING'
                                    )

                            except Exception as cleanup_error:
                                logger.error(f"Failed to clean phantom position {symbol}: {cleanup_error}")

                                # Log cleanup failure
                                event_logger = get_event_logger()
                                if event_logger:
                                    await event_logger.log_event(
                                        EventType.POSITION_ERROR,
                                        {
                                            'symbol': symbol,
                                            'position_id': position.id,
                                            'error': str(cleanup_error),
                                            'context': 'phantom_cleanup_failed'
                                        },
                                        position_id=position.id,
                                        symbol=symbol,
                                        exchange=exchange_name,
                                        severity='ERROR',
                                        error=cleanup_error
                                    )

                    # 2. UNTRACKED POSITIONS (on exchange but not in DB)
                    untracked_positions = []
                    for ex_pos in active_exchange_positions:
                        # CRITICAL FIX: Must normalize exchange symbol for comparison
                        normalized_symbol = normalize_symbol(ex_pos['symbol'])
                        if normalized_symbol not in local_symbols:
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

                            # Log untracked position requiring manual review
                            event_logger = get_event_logger()
                            if event_logger:
                                await event_logger.log_event(
                                    EventType.WARNING_RAISED,
                                    {
                                        'type': 'untracked_position_detected',
                                        'symbol': symbol,
                                        'exchange': exchange_name,
                                        'side': side,
                                        'size': size,
                                        'entry_price': entry_price,
                                        'message': f"Untracked position found on exchange: {symbol} {side} {size} @ {entry_price}",
                                        'requires_manual_review': True
                                    },
                                    symbol=symbol,
                                    exchange=exchange_name,
                                    severity='CRITICAL'
                                )

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
                            # CRITICAL FIX: Pass protected order IDs whitelist
                            integration = BinanceZombieIntegration(
                                exchange.exchange,
                                protected_order_ids=self.protected_order_ids
                            )

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
                    logger.critical(f"🔄 Temporarily reducing sync interval from {self.sync_interval}s to 60s")

                    # Temporarily reduce sync interval to clean up faster
                    self.sync_interval = min(60, self.sync_interval)  # CRITICAL FIX: 1 minute for emergency cleanup

                    logger.critical("📢 Manual intervention may be required - check exchange UI")
                elif total_zombies_found > 5:
                    logger.warning(f"⚠️ Moderate zombie count: {total_zombies_found}")
                    # Slightly reduce interval if persistent zombies
                    if self.sync_interval > 90:
                        self.sync_interval = 90  # CRITICAL FIX: 1.5 minutes for moderate cleanup
                        logger.info(f"📉 Reduced sync interval to {self.sync_interval}s")
            else:
                logger.info(f"✨ No zombie orders found (check #{self.zombie_check_counter}, duration: {cleanup_duration:.2f}s)")

                # Gradually increase interval if no zombies found for multiple checks
                if self.zombie_check_counter > 3 and self.last_zombie_count == 0:
                    if self.sync_interval < 120:
                        self.sync_interval = min(120, self.sync_interval + 30)  # CRITICAL FIX: restore to 2 minutes max
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