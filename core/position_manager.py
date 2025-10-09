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
from typing import Dict, Optional, List, Tuple
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config.settings import TradingConfig
from database.repository import Repository as TradingRepository
from protection.trailing_stop import SmartTrailingStopManager
from websocket.event_router import EventRouter
from core.exchange_manager import ExchangeManager
from core.services.zombie_cleanup_service import ZombieCleanupService
from core.balance_checker import BalanceChecker
from utils.decimal_utils import to_decimal, calculate_stop_loss, calculate_pnl, calculate_quantity
from utils.order_helpers import (
    safe_order_get, get_order_id, get_order_symbol, 
    get_order_type, get_order_side, get_order_amount
)

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
            callback_percent=Decimal(str(config.trailing_callback_percent))
            # breakeven_at removed completely from TrailingStopConfig (2025-10-05)
        )
        
        self.trailing_managers = {
            name: SmartTrailingStopManager(exchange, trailing_config)
            for name, exchange in exchanges.items()
        }

        # Active positions tracking
        self.positions: Dict[str, PositionState] = {}  # symbol -> position

        # Position locks
        self.position_locks: set = set()
        
        # ✅ CRITICAL FIX: SL creation locks to prevent race condition
        self._sl_creation_locks: Dict[str, asyncio.Lock] = {}  # {symbol: lock}
        self._sl_creation_locks_lock = asyncio.Lock()  # Meta-lock for creating locks safely
        
        # ✅ CRITICAL: In-memory cache of created SL to prevent race condition with exchange API lag
        self._sl_cache: Dict[str, bool] = {}  # {symbol: has_sl}
        
        # ✅ CRITICAL FIX: Position opening locks to prevent duplicate positions
        self._position_opening_locks: Dict[str, asyncio.Lock] = {}  # {symbol: lock}
        self._position_opening_locks_lock = asyncio.Lock()  # Meta-lock for creating locks safely
        
        # ✅ CRITICAL: In-memory cache of opened positions to prevent race condition with DB lag
        self._position_cache: Dict[str, bool] = {}  # {exchange_symbol: position_opened}

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
        # ✅ PHASE 3: Reduced from 600 to 300 seconds (10min → 5min) for better backup monitoring
        self.sync_interval = 300  # 5 minutes (backup protection check)
        
        # REFACTORING: Zombie cleanup extracted to service
        self.zombie_cleanup = ZombieCleanupService(
            repository=repository,
            exchanges=exchanges,
            sync_interval=self.sync_interval,
            aggressive_cleanup_threshold=10
        )
        
        # Balance checker for pre-validation
        self.balance_checker = BalanceChecker(
            exchanges=exchanges,
            position_size_usd=float(config.position_size_usd)
        )

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
                            quantity=to_decimal(safe_get_attr(position, 'contracts', 'quantity', 'qty', 'size', default=0))
                        )
                        position.has_trailing_stop = True
                        
                        # ✅ FIX: Update trailing stop status in DB
                        await self.repository.update_position_trailing_stop(
                            position_id=position.id,
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

    async def start_periodic_sync(self):
        """
        Start periodic position synchronization
        
        REFACTORED: 2025-10-04
        Now uses PositionSynchronizer instead of duplicated logic
        """
        logger.info(f"🔄 Starting periodic sync every {self.sync_interval} seconds")

        while True:
            try:
                await asyncio.sleep(self.sync_interval)

                # Sync all exchanges using PositionSynchronizer
                await self.synchronize_with_exchanges()

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

        @self.event_router.on('position_update')
        async def handle_position_update(data: Dict):
            await self._on_position_update(data)

        @self.event_router.on('order_update')
        async def handle_order_filled(data: Dict):
            await self._on_order_filled(data)

        @self.event_router.on('stop_loss_triggered')
        async def handle_stop_loss(data: Dict):
            await self._on_stop_loss_triggered(data)
        
        # ✅ CRITICAL FIX: Register price_update handler for Trailing Stop
        @self.event_router.on('price_update')
        async def handle_price_update(data: Dict):
            """Handle price updates for Trailing Stop monitoring"""
            await self._on_price_update(data)

    async def open_position(self, request: PositionRequest) -> Optional[PositionState]:
        """
        Open new position with complete workflow and race condition protection.
        
        STEPS:
        1. Acquire asyncio Lock (prevents race conditions within same process)
        2. Acquire PostgreSQL advisory lock (cross-process protection)
        3. Get exchange instance
        4. Check if position already exists (protected by locks)
        5. Validate risk limits
        6. Calculate position size
        7. Validate spread
        8. Execute market order
        9. Create position state
        10. Save to database (trade + position records)
        11. Set stop loss
        12. Initialize trailing stop
        13. Update internal tracking
        
        RACE CONDITION PROTECTION (2 layers):
        - ✅ asyncio.Lock: Prevents multiple async tasks from opening same position
        - PostgreSQL advisory lock prevents duplicate positions across bot instances
        - In-memory lock protects against concurrent calls within same process
        - All locks are released in finally block
        
        Args:
            request: PositionRequest with symbol, exchange, side, etc.
            
        Returns:
            PositionState if successful, None otherwise
        """

        symbol = request.symbol
        exchange_name = request.exchange.lower()
        db_lock_acquired = False

        # ✅ CRITICAL FIX: Acquire asyncio Lock to prevent race condition
        # Use meta-lock to safely create per-symbol lock
        lock_key = f"{exchange_name}_{symbol}"
        async with self._position_opening_locks_lock:
            if lock_key not in self._position_opening_locks:
                self._position_opening_locks[lock_key] = asyncio.Lock()
            position_lock = self._position_opening_locks[lock_key]
        
        # ✅ CRITICAL FIX: Hold lock for ENTIRE position creation process
        async with position_lock:
            logger.debug(f"🔒 Acquired position opening lock for {symbol}")
            
            # ✅ CRITICAL: Check in-memory cache FIRST to prevent race condition with DB lag
            if self._position_cache.get(lock_key, False):
                logger.warning(f"📌 Position {symbol} already marked as opened (cache), skipping duplicate")
                logger.debug(f"🔓 Released position opening lock for {symbol} (cache hit)")
                return None
            
            # ✅ CRITICAL: Check if position already exists in DB (atomic check under lock)
            existing_position = await self.repository.get_open_position(symbol, exchange_name)
            if existing_position:
                logger.warning(f"Position for {symbol} already exists (ID: {existing_position.get('id')}), skipping duplicate")
                self._position_cache[lock_key] = True  # Update cache
                logger.debug(f"🔓 Released position opening lock for {symbol} (already exists)")
                return None
            
            # Check if already being processed (fast check with set)
            if lock_key in self.position_locks:
                logger.warning(f"Position already being processed for {symbol} (in-memory lock)")
                logger.debug(f"🔓 Released position opening lock for {symbol} (already processing)")
                return None

            self.position_locks.add(lock_key)
            
            # ✅ CRITICAL: Mark in cache to prevent duplicate position from concurrent tasks
            self._position_cache[lock_key] = True
            logger.debug(f"✅ Position opening lock held - proceeding with creation (cache updated)")

            try:
                # 1. Acquire PostgreSQL advisory lock (protects across processes)
                db_lock_acquired = await self.repository.acquire_position_lock(symbol, exchange_name)
                if not db_lock_acquired:
                    logger.warning(
                        f"Could not acquire database lock for {symbol} on {exchange_name}. "
                        f"Position may be in process by another bot instance."
                    )
                    return None
                
                logger.debug(f"✅ Acquired DB advisory lock for {symbol}")

                # 2. Get exchange
                exchange = self.exchanges.get(exchange_name)
                if not exchange:
                    logger.error(f"Exchange {exchange_name} not available")
                    return None

                # 3. Check if position already exists (now protected by DB lock)
                if await self._position_exists(symbol, exchange_name):
                    logger.warning(f"Position already exists for {symbol} on {exchange_name}")
                    return None

                # 4. Validate risk limits
                if not await self._validate_risk_limits(request):
                    logger.warning(f"Risk limits exceeded for {symbol}")
                    return None

                # 5. Validate symbol exists on exchange
                # CRITICAL: Check if symbol is available for trading before attempting order
                if not exchange.has_market(symbol):
                    logger.error(
                        f"❌ Symbol {symbol} not available on {exchange_name}. "
                        f"Symbol may be delisted, not supported, or invalid."
                    )
                    return None
                
                # Additional check: verify market is active
                market_info = exchange.get_market_info(symbol)
                
                # ✅ CRITICAL FIX: Handle missing market_info
                if not market_info:
                    logger.error(
                        f"❌ Cannot open position for {symbol} on {exchange_name}: market_info unavailable. "
                        f"Symbol may be delisted or markets not loaded. Skipping to avoid blind trading."
                    )
                    return None
                
                if market_info.get('active') is False:
                    logger.error(
                        f"❌ Symbol {symbol} is not active on {exchange_name}. "
                        f"Market status: {market_info.get('info', {}).get('status', 'unknown')}"
                    )
                    return None

                # 6. Calculate position size
                position_size_usd = request.position_size_usd or self.config.position_size_usd
                quantity = await self._calculate_position_size(
                    exchange, symbol, request.entry_price, position_size_usd
                )

                if not quantity:
                    logger.error(f"Failed to calculate position size for {symbol}")
                    return None

                # 6.1. Check available balance BEFORE attempting to open position
                # CRITICAL: Prevents failed order attempts and allows continuing with other exchanges
                has_balance = await self.balance_checker.has_sufficient_balance(
                    exchange_name=exchange_name,
                    required_usd=to_decimal(position_size_usd)
                )
                
                if not has_balance:
                    logger.warning(
                        f"⏸️ Skipping {symbol} on {exchange_name}: insufficient funds. "
                        f"Required: {position_size_usd} USDT. "
                        f"Position will be attempted when funds become available."
                    )
                    return None

                # 6.2. Validate spread (временно только логирование)
                await self._validate_spread(exchange, symbol)
                # Не блокируем открытие позиций из-за спреда

                # 6.3. Set leverage before opening position
                # ✅ CRITICAL FIX: Calculate notional and use smart leverage selection
                leverage = self.config.leverage
                notional = float(quantity) * float(request.entry_price)
                
                # Smart leverage selection based on notional and brackets
                await exchange.set_leverage(symbol, leverage, notional=notional)

                # 7. FINAL CHECK: Verify position doesn't exist on exchange RIGHT BEFORE order creation
                # This is the last line of defense against race conditions
                logger.debug(f"🔍 Final check: verifying {symbol} doesn't exist on exchange...")
                try:
                    exchange_positions = await exchange.fetch_positions()
                    normalized_symbol = symbol.replace('/', '').replace(':USDT', '')
                    
                    for pos in exchange_positions:
                        pos_symbol = pos.get('symbol', '').replace('/', '').replace(':USDT', '')
                        contracts = abs(float(pos.get('contracts', 0)))
                        
                        if pos_symbol == normalized_symbol and contracts > 0:
                            logger.error(
                                f"🚨 CRITICAL: Position {symbol} already exists on exchange with {contracts} contracts! "
                                f"Aborting order creation to prevent duplicate."
                            )
                            return None
                    
                    logger.debug(f"✅ Final check passed: {symbol} not found on exchange")
                except Exception as e:
                    logger.warning(f"Could not perform final exchange check for {symbol}: {e}")
                    # Continue anyway - other checks should catch duplicates

                # 8. Execute market order
                logger.info(f"Opening position: {symbol} {request.side} {quantity}")

                # Convert side: long -> buy, short -> sell for Binance
                if request.side.lower() == 'long':
                    order_side = 'buy'
                elif request.side.lower() == 'short':
                    order_side = 'sell'
                else:
                    order_side = request.side.lower()

                order = await exchange.create_market_order(symbol, order_side, quantity)

                if not order:
                    # ✅ FIX: Enhanced logging for diagnostics
                    logger.error(
                        f"❌ Failed to create order for {symbol}:\n"
                        f"   Exchange: {exchange_name}\n"
                        f"   Side: {order_side}\n"
                        f"   Quantity: {quantity}\n"
                        f"   Market active: {market_info.get('active')}\n"
                        f"   Likely cause: Testnet instability or symbol unavailable"
                    )
                    return None
                
                # ✅ FIX: Additional safety check for order object validity
                if not hasattr(order, 'filled'):
                    logger.error(
                        f"❌ Order object is invalid for {symbol}: "
                        f"missing 'filled' attribute. Order type: {type(order)}"
                    )
                    return None

                # ✅ FREQTRADE-STYLE: Verify order fill with retry and fallbacks
                # This replaces old Bybit/Binance specific logic with unified approach
                if not order.filled or order.filled == 0:
                    logger.info(f"Order created but fill status unknown, verifying with retry logic...")
                    verified_order = await self._verify_order_filled(
                        exchange, 
                        order.id, 
                        symbol, 
                        exchange_name
                    )
                    
                    if verified_order:
                        order = verified_order
                    else:
                        # ✅ COMPENSATING: Order not filled after retries, don't proceed
                        logger.error(
                            f"❌ Order {order.id} not filled after verification retries. "
                            f"Position will NOT be saved to database."
                        )
                        return None
                
                # Final safety checks for all exchanges
                if not order.filled or order.filled <= 0:
                    logger.error(f"Invalid order filled quantity for {symbol}: {order.filled}")
                    return None
                
                if not order.price or order.price <= 0:
                    logger.error(f"Invalid order price for {symbol}: {order.price}")
                    return None

                # 9. Create position state (but DON'T save to DB yet!)
                position = PositionState(
                id=None,  # Will be set after DB insert
                symbol=symbol,
                exchange=exchange_name,
                side=request.side.lower(),  # Use request.side directly (already 'long' or 'short')
                quantity=order.filled,
                entry_price=order.price,
                current_price=order.price,
                unrealized_pnl=0,
                unrealized_pnl_percent=0,
                opened_at=datetime.now(timezone.utc)
                )

                # 10. Set stop loss BEFORE saving to database (Freqtrade-style)
                # ✅ COMPENSATING TRANSACTIONS: If SL fails, we don't save position to DB
                stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
                stop_loss_price = calculate_stop_loss(
                to_decimal(position.entry_price), position.side, to_decimal(stop_loss_percent)
                )
                
                logger.info(f"Setting stop loss for {symbol}: {stop_loss_percent}% at ${stop_loss_price:.4f}")

                sl_success, sl_order_id = await self._set_stop_loss(exchange, position, stop_loss_price)
                
                if not sl_success:
                    # ✅ COMPENSATING TRANSACTION: SL failed, close position on exchange
                    logger.error(f"❌ Stop loss creation failed for {symbol}, executing compensating transaction...")
                    await self._compensate_failed_sl(exchange, position, order)
                    return None
                
                # SL created successfully
                position.has_stop_loss = True
                position.stop_loss_price = stop_loss_price
                logger.info(f"✅ Stop loss confirmed for {symbol}, order_id={sl_order_id}")

                # 11. NOW save to database (after SL is confirmed)
                # ✅ FREQTRADE ORDER: create_order() → check_filled() → set_stop_loss() → save_to_db()
                try:
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
                        'trade_id': trade_id,
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'side': position.side,
                        'quantity': position.quantity,
                        'entry_price': position.entry_price,
                        'leverage': leverage  # CRITICAL: Save leverage to database
                    })

                    position.id = position_id
                    logger.info(f"💾 Position saved to database with ID: {position.id}")

                    # Update SL in database
                    await self.repository.update_position_stop_loss(
                        position_id, stop_loss_price, ""
                    )
                    logger.info(f"✅ Stop Loss status updated in DB for {symbol}: has_stop_loss=TRUE")

                except Exception as db_error:
                    # ✅ COMPENSATING TRANSACTION: DB save failed, close position and cancel SL
                    logger.error(f"❌ Database save failed for {symbol}, executing compensating transaction...")
                    await self._compensate_failed_db_save(exchange, position, order, sl_order_id)
                    raise db_error

                # 12. Initialize trailing stop WITH stop_order_id
                trailing_manager = self.trailing_managers.get(exchange_name)
                if trailing_manager:
                    await trailing_manager.create_trailing_stop(
                        symbol=symbol,
                        side=position.side,
                        entry_price=position.entry_price,
                        quantity=position.quantity,
                        initial_stop=stop_loss_price,
                        stop_order_id=sl_order_id  # ✅ ПЕРЕДАЁМ ID ОРДЕРА!
                    )
                    position.has_trailing_stop = True
                    
                    # ✅ FIX: Update trailing stop status in DB
                    await self.repository.update_position_trailing_stop(
                        position_id=position.id,
                        has_trailing_stop=True
                    )

                # 13. Update internal tracking
                self.positions[symbol] = position
                self.position_count += 1
                self.total_exposure += Decimal(str(position.quantity * position.entry_price))
                self.stats['positions_opened'] += 1

                logger.info(
                f"✅ Position opened: {symbol} {position.side} "
                f"{position.quantity:.6f} @ ${position.entry_price:.4f}"
                )
                
                # CRITICAL: Invalidate balance cache so spent funds are reflected immediately
                # This prevents opening too many positions in quick succession
                self.balance_checker.invalidate_cache(exchange_name)
                logger.debug(f"✅ Invalidated balance cache for {exchange_name} (funds spent)")
                
                # ✅ CRITICAL: Emit position_opened event for dynamic WebSocket subscription
                await self.event_router.emit('position_opened', {
                'symbol': symbol,
                'exchange': exchange_name,
                'side': position.side,
                'quantity': position.quantity,
                'entry_price': position.entry_price
                })

                return position

            except Exception as e:
                logger.error(f"Error opening position for {symbol}: {e}", exc_info=True)
                return None

            finally:
                # Release PostgreSQL advisory lock
                if db_lock_acquired:
                    try:
                        await self.repository.release_position_lock(symbol, exchange_name)
                        logger.debug(f"🔓 Released DB advisory lock for {symbol}")
                    except Exception as lock_error:
                        logger.error(f"Failed to release DB lock for {symbol}: {lock_error}")
                
                # Release in-memory lock
            self.position_locks.discard(lock_key)
            logger.debug(f"🔓 Released position opening lock for {symbol} (completed)")

    async def _position_exists(self, symbol: str, exchange: str) -> bool:
        """Check if position already exists"""
        logger.debug(f"[_position_exists] Checking {symbol} on {exchange}")
        
        # Check local tracking
        if symbol in self.positions:
            logger.debug(f"[_position_exists] ✅ Found in local tracking: {symbol}")
            return True

        # Check database
        db_position = await self.repository.get_open_position(symbol, exchange)
        if db_position:
            logger.debug(f"[_position_exists] ✅ Found in DB: {symbol}")
            return True

        # Check exchange
        exchange_obj = self.exchanges.get(exchange)
        if exchange_obj:
            logger.debug(f"[_position_exists] Checking exchange API for {symbol}")
            # CRITICAL FIX: Same issue as verify_position_exists - use fetch_positions() without [symbol]
            positions = await exchange_obj.fetch_positions()
            # Find position using normalize_symbol comparison
            normalized_symbol = normalize_symbol(symbol)
            logger.debug(f"[_position_exists] Normalized: {symbol} → {normalized_symbol}, checking {len(positions)} positions")
            for pos in positions:
                pos_symbol = normalize_symbol(pos.get('symbol'))
                contracts = float(pos.get('contracts') or 0)
                if pos_symbol == normalized_symbol and abs(contracts) > 0:
                    logger.warning(f"[_position_exists] ✅ FOUND ON EXCHANGE: {pos.get('symbol')} ({contracts} contracts)")
                    return True

        logger.debug(f"[_position_exists] ❌ NOT FOUND: {symbol}")
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
            logger.warning(f"❌ Spread too wide for {symbol}: {spread_percent:.2f}% > {max_spread}% - REJECTING")
            return False

        return True

    async def _verify_order_filled(self, 
                                     exchange: ExchangeManager, 
                                     order_id: str, 
                                     symbol: str,
                                     exchange_name: str) -> Optional[Dict]:
        """
        Verify order fill status with retry and multiple fallback methods.
        
        Implements Freqtrade-style verification using:
        1. fetch_order() - universal method (works for Binance)
        2. fetch_closed_orders() - for market orders (works for Bybit)
        3. Exponential backoff retry logic
        
        This solves the race condition where market orders are filled instantly
        but API replication has a 3-10 second delay.
        
        Args:
            exchange: Exchange manager instance
            order_id: Order ID to verify
            symbol: Symbol (e.g., 'BTCUSDT')
            exchange_name: Exchange name ('binance' or 'bybit')
            
        Returns:
            Order dict with filled status, or None if not found after retries
        """
        max_retries = 3
        retry_delays = [1.0, 2.0, 3.0]  # Exponential backoff
        
        logger.info(f"🔍 Verifying order fill: {order_id} for {symbol} on {exchange_name}")
        
        for attempt in range(max_retries):
            # METHOD 1: fetch_order() - универсальный метод
            try:
                order = await exchange.fetch_order(order_id, symbol)
                if order and order.get('filled', 0) > 0:
                    logger.info(
                        f"✅ Order {order_id} verified via fetch_order: "
                        f"filled={order['filled']}, status={order.get('status')}"
                    )
                    return order
            except Exception as e:
                logger.debug(f"fetch_order attempt {attempt+1} failed: {e}")
            
            # METHOD 2: fetch_closed_orders() - для market ордеров
            try:
                closed_orders = await exchange.fetch_closed_orders(symbol, limit=10)
                for o in closed_orders:
                    if o.get('id') == order_id and o.get('filled', 0) > 0:
                        logger.info(
                            f"✅ Order {order_id} found in closed_orders: "
                            f"filled={o['filled']}, status={o.get('status')}"
                        )
                        return o
            except Exception as e:
                logger.debug(f"fetch_closed_orders attempt {attempt+1} failed: {e}")
            
            # Wait before next retry (exponential backoff)
            if attempt < max_retries - 1:
                delay = retry_delays[attempt]
                logger.warning(
                    f"⏳ Order {order_id} not found (attempt {attempt+1}/{max_retries}), "
                    f"waiting {delay}s for API replication..."
                )
                await asyncio.sleep(delay)
        
        # All retries exhausted
        logger.error(
            f"❌ Order {order_id} not found after {max_retries} attempts. "
            f"This indicates API replication lag or order was not created."
        )
        return None

    async def _set_stop_loss(self,
                             exchange: ExchangeManager,
                             position: PositionState,
                             stop_price: float) -> Tuple[bool, Optional[str]]:
        """
        Set stop loss order using unified StopLossManager.

        This function now uses StopLossManager for ALL SL operations
        to ensure consistency across the system.
        
        ✅ CRITICAL FIX: Uses per-symbol lock to prevent race condition
        when multiple async tasks try to create SL simultaneously.
        
        Returns:
            Tuple[bool, Optional[str]]: (success, order_id)
                - success: True if SL was set successfully
                - order_id: ID of created order (None for Bybit position-attached SL)
        """

        logger.info(f"Attempting to set stop loss for {position.symbol}")
        logger.info(f"  Position: {position.side} {position.quantity} @ {position.entry_price}")
        logger.info(f"  Stop price: ${stop_price:.4f}")

        # ✅ CRITICAL FIX: Acquire lock for this symbol to prevent race condition
        # Use meta-lock to safely create per-symbol lock
        async with self._sl_creation_locks_lock:
            if position.symbol not in self._sl_creation_locks:
                self._sl_creation_locks[position.symbol] = asyncio.Lock()
            symbol_lock = self._sl_creation_locks[position.symbol]
        
        async with symbol_lock:
            logger.debug(f"🔒 Acquired SL creation lock for {position.symbol}")
            
            try:
                # ✅ CRITICAL: Check in-memory cache FIRST to prevent race condition with exchange API lag
                if self._sl_cache.get(position.symbol, False):
                    logger.info(f"📌 Stop loss already marked as created for {position.symbol} (cache)")
                    logger.debug(f"🔓 Released SL creation lock for {position.symbol} (cache hit)")
                    return True, None
                
                # ============================================================
                # UNIFIED APPROACH: Use StopLossManager for ALL SL operations
                # ============================================================
                from core.stop_loss_manager import StopLossManager

                sl_manager = StopLossManager(exchange.exchange, position.exchange)

                # CRITICAL: Check using unified has_stop_loss (checks both position.info.stopLoss AND orders)
                has_sl, existing_sl_price = await sl_manager.has_stop_loss(position.symbol)

                if has_sl:
                    logger.info(f"📌 Stop loss already exists for {position.symbol} at {existing_sl_price}")
                    self._sl_cache[position.symbol] = True  # Update cache
                    logger.debug(f"🔓 Released SL creation lock for {position.symbol} (already exists)")
                    return True, None  # Stop loss exists, no need to create new one

                # No SL exists - create it using unified set_stop_loss
                order_side = 'sell' if position.side == 'long' else 'buy'

                result = await sl_manager.set_stop_loss(
                    symbol=position.symbol,
                    side=order_side,
                    amount=float(position.quantity),
                    stop_price=stop_price
                )

                if result['status'] in ['created', 'already_exists']:
                    order_id = result.get('orderId')  # None for Bybit (position-attached)
                    logger.info(f"✅ Stop loss set for {position.symbol} at {result['stopPrice']}, order_id={order_id}")
                    
                    # ✅ CRITICAL: Mark in cache to prevent duplicate SL from concurrent tasks
                    self._sl_cache[position.symbol] = True
                    
                    logger.debug(f"🔓 Released SL creation lock for {position.symbol} (created)")
                    return True, order_id
                else:
                    logger.warning(f"⚠️ Unexpected result from set_stop_loss: {result}")
                    logger.debug(f"🔓 Released SL creation lock for {position.symbol} (failed)")
                    return False, None

            except Exception as e:
                logger.error(f"Failed to set stop loss for {position.symbol}: {e}", exc_info=True)
                logger.debug(f"🔓 Released SL creation lock for {position.symbol} (exception)")
                return False, None

    async def _compensate_failed_sl(self, exchange: ExchangeManager, position: PositionState, order):
        """
        Compensating transaction: Close position on exchange if SL creation failed.
        
        This prevents unprotected positions from being left on the exchange.
        Freqtrade-style approach: if we can't protect the position, we don't keep it.
        
        Args:
            exchange: Exchange manager instance
            position: Position state object
            order: Original market order that opened the position
        """
        logger.warning(f"🔄 Executing compensating transaction for {position.symbol}: closing unprotected position")
        
        try:
            # Close the position on exchange (market order in opposite direction)
            close_side = 'sell' if position.side == 'long' else 'buy'
            close_order = await exchange.create_market_order(
                position.symbol,
                close_side,
                position.quantity
            )
            
            if close_order and close_order.filled:
                logger.info(
                    f"✅ Compensating transaction completed: closed {position.symbol} "
                    f"at ${close_order.price:.4f} (opened at ${position.entry_price:.4f})"
                )
            else:
                logger.error(
                    f"❌ Compensating transaction FAILED: could not close {position.symbol}. "
                    f"MANUAL INTERVENTION REQUIRED!"
                )
        except Exception as e:
            logger.error(
                f"❌ CRITICAL: Compensating transaction failed for {position.symbol}: {e}. "
                f"Position is UNPROTECTED on exchange! MANUAL INTERVENTION REQUIRED!",
                exc_info=True
            )

    async def _compensate_failed_db_save(self, exchange: ExchangeManager, position: PositionState, 
                                         order, sl_order_id: Optional[str]):
        """
        Compensating transaction: Close position and cancel SL if database save failed.
        
        This ensures consistency between exchange and database.
        If we can't track the position in DB, we don't keep it on exchange.
        
        Args:
            exchange: Exchange manager instance
            position: Position state object
            order: Original market order that opened the position
            sl_order_id: Stop loss order ID (if created)
        """
        logger.warning(
            f"🔄 Executing compensating transaction for {position.symbol}: "
            f"closing position and canceling SL due to DB save failure"
        )
        
        try:
            # 1. Cancel stop loss order (if exists)
            if sl_order_id:
                try:
                    await exchange.cancel_order(sl_order_id, position.symbol)
                    logger.info(f"✅ Canceled SL order {sl_order_id} for {position.symbol}")
                except Exception as cancel_error:
                    logger.error(f"Failed to cancel SL order {sl_order_id}: {cancel_error}")
            
            # 2. Close the position on exchange
            close_side = 'sell' if position.side == 'long' else 'buy'
            close_order = await exchange.create_market_order(
                position.symbol,
                close_side,
                position.quantity
            )
            
            if close_order and close_order.filled:
                logger.info(
                    f"✅ Compensating transaction completed: closed {position.symbol} "
                    f"at ${close_order.price:.4f} (opened at ${position.entry_price:.4f})"
                )
            else:
                logger.error(
                    f"❌ Compensating transaction FAILED: could not close {position.symbol}. "
                    f"MANUAL INTERVENTION REQUIRED!"
                )
        except Exception as e:
            logger.error(
                f"❌ CRITICAL: Compensating transaction failed for {position.symbol}: {e}. "
                f"Position exists on exchange but not in DB! MANUAL INTERVENTION REQUIRED!",
                exc_info=True
            )

    async def _on_price_update(self, data: Dict):
        """
        Handle price update from WebSocket for Trailing Stop monitoring
        
        Args:
            data: {'symbol': 'BTCUSDT', 'price': 50000.0}
        """
        symbol = data.get('symbol')
        price = data.get('price')
        
        if not symbol or not price:
            return

        # Normalize symbol format
        normalized_symbol = symbol.replace('/', '').replace(':USDT', '')
        position_symbol = normalized_symbol if normalized_symbol in self.positions else symbol
        
        if position_symbol not in self.positions:
            # Position not tracked - this is normal for market data we're not trading
            return
        
        position = self.positions[position_symbol]
        
        # Update current price
        old_price = position.current_price
        position.current_price = float(price)
        
        # Calculate PnL percent
        entry_price_float = float(position.entry_price)
        if entry_price_float > 0:
            if position.side == 'long':
                position.unrealized_pnl_percent = (
                    (position.current_price - entry_price_float) / entry_price_float * 100
                )
            else:
                position.unrealized_pnl_percent = (
                    (entry_price_float - position.current_price) / entry_price_float * 100
                )
        
        # Log price update every 3 updates (for monitoring)
        if not hasattr(self, '_price_update_counter'):
            self._price_update_counter = {}
        self._price_update_counter[position_symbol] = self._price_update_counter.get(position_symbol, 0) + 1
        
        if self._price_update_counter[position_symbol] % 3 == 0:
            logger.info(
                f"💹 Price update for {position_symbol}: ${old_price:.4f} → ${position.current_price:.4f}, "
                f"PnL: {position.unrealized_pnl_percent:+.2f}%, has_TS: {position.has_trailing_stop}"
            )
        
        # ✅ CRITICAL: Update Trailing Stop with new price
        if position.has_trailing_stop:
            trailing_manager = self.trailing_managers.get(position.exchange)
            if trailing_manager:
                try:
                    update_result = await trailing_manager.update_price(
                        position_symbol, 
                        float(position.current_price)
                    )
                    
                    if update_result and update_result.get('action') == 'activated':
                        position.trailing_activated = True
                        # Update database to record activation
                        if position.id:
                            await self.repository.update_position(
                                position.id,
                                trailing_activated=True
                            )
                        logger.info(f"🚀 Trailing stop activated for {position_symbol}")
                except Exception as e:
                    logger.error(f"Error updating trailing stop for {position_symbol}: {e}")

    async def _on_position_update(self, data: Dict):
        """
        Handle position update from WebSocket
        
        Args:
            data: Dict of positions {symbol: {side, quantity, mark_price, ...}}
                  OR single position {symbol, side, quantity, mark_price, ...}
        """
        logger.debug(f"[PositionManager] _on_position_update called with data keys: {list(data.keys())[:5]}")
        
        # Handle both formats:
        # 1. Dict of all positions: {'BTCUSDT': {...}, 'ETHUSDT': {...}}
        # 2. Single position: {'symbol': 'BTCUSDT', 'side': 'long', ...}
        
        positions_to_process = []
        
        if 'symbol' in data:
            # Single position format
            positions_to_process = [(data.get('symbol'), data)]
        else:
            # Dict of positions format (AdaptiveStream)
            positions_to_process = list(data.items())
        
        logger.debug(f"[PositionManager] Processing {len(positions_to_process)} position update(s)")
        logger.debug(f"[PositionManager] Tracked positions: {list(self.positions.keys())}")
        
        for symbol, pos_data in positions_to_process:
            if not symbol:
                continue
            
            # Normalize symbol format (SHELL/USDT:USDT → SHELLUSDT)
            normalized_symbol = symbol.replace('/', '').replace(':USDT', '')
            
            # Try both formats
            position_symbol = normalized_symbol if normalized_symbol in self.positions else symbol
            
            if position_symbol not in self.positions:
                logger.debug(f"[PositionManager] Skipping {symbol} (normalized: {normalized_symbol}) - not tracked")
                continue

            position = self.positions[position_symbol]

            # Update position state
            try:
                # CRITICAL: Convert to float to avoid Decimal/float TypeError
                position.current_price = float(pos_data.get('mark_price', pos_data.get('markPrice', position.current_price)))
                position.unrealized_pnl = float(pos_data.get('unrealized_pnl', pos_data.get('unrealizedPnl', 0)))

                # Calculate PnL percent
                # CRITICAL: Convert entry_price to float for calculation
                entry_price_float = float(position.entry_price)
                if entry_price_float > 0:
                    if position.side == 'long':
                        position.unrealized_pnl_percent = (
                            (position.current_price - entry_price_float) / entry_price_float * 100
                        )
                    else:
                        position.unrealized_pnl_percent = (
                            (entry_price_float - position.current_price) / entry_price_float * 100
                        )

                logger.debug(f"[PositionManager] {position_symbol}: price={position.current_price}, pnl%={position.unrealized_pnl_percent:.2f}%")

                # Update trailing stop
                trailing_manager = self.trailing_managers.get(position.exchange)
                
                if trailing_manager and position.has_trailing_stop:
                    logger.debug(f"[PositionManager] Calling trailing_manager.update_price for {position_symbol}")
                    try:
                        update_result = await trailing_manager.update_price(position_symbol, float(position.current_price))
                        logger.debug(f"[PositionManager] update_price result: {update_result}")

                        if update_result and update_result.get('action') == 'activated':
                            position.trailing_activated = True
                            logger.info(f"🚀 Trailing stop activated for {position_symbol}")
                    except Exception as e:
                        logger.error(f"Exception in trailing stop update for {position_symbol}: {e}", exc_info=True)

                # Update database
                await self.repository.update_position_from_websocket({
                    'symbol': position_symbol,
                    'exchange': position.exchange,
                    'current_price': position.current_price,
                    'mark_price': position.current_price,
                    'unrealized_pnl': position.unrealized_pnl,
                    'unrealized_pnl_percent': position.unrealized_pnl_percent
                })
            except Exception as e:
                logger.error(f"Error updating position {position_symbol}: {e}", exc_info=True)

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
        
        # ✅ CRITICAL: Clear position cache when position closes
        position = self.positions[symbol]
        lock_key = f"{position.exchange}_{symbol}"
        if lock_key in self._position_cache:
            del self._position_cache[lock_key]
            logger.debug(f"Cleared position cache for {symbol}")
        
        # ✅ CRITICAL: Clear SL cache when position closes
        if symbol in self._sl_cache:
            del self._sl_cache[symbol]
            logger.debug(f"Cleared SL cache for {symbol}")

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
                
                # CRITICAL: Invalidate balance cache so freed funds are immediately available
                # This allows opening new positions right after closing without waiting for cache TTL
                self.balance_checker.invalidate_cache(position.exchange)
                logger.debug(f"✅ Invalidated balance cache for {position.exchange} (funds freed)")
                
                # ✅ CRITICAL: Emit position_closed event for dynamic WebSocket subscription
                await self.event_router.emit('position_closed', {
                    'symbol': symbol,
                    'exchange': position.exchange,
                    'reason': reason,
                    'realized_pnl': realized_pnl,
                    'realized_pnl_percent': realized_pnl_percent
                })

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
            
            # Use unified order accessor
            order_id = get_order_id(order) if order else None

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
                    'pending_close_order_id': order_id,
                    'pending_close_price': to_decimal(target_price)
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
        
        ✅ ENHANCED: Also checks positions from DB that are not in memory
        """
        try:
            from core.stop_loss_manager import StopLossManager

            unprotected_positions = []

            # ✅ STEP 1: Check all positions IN MEMORY
            # ============================================================
            for symbol, position in list(self.positions.items()):
                exchange = self.exchanges.get(position.exchange)
                if not exchange:
                    continue

                # UNIFIED APPROACH: Use StopLossManager for SL check
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

            # ✅ STEP 2: Check positions from DB that are NOT in memory
            # ============================================================
            logger.info("🔍 Checking database for untracked positions without SL...")
            db_positions = await self.repository.get_open_positions()
            
            for db_pos in db_positions:
                symbol = db_pos['symbol']
                
                # Skip if already in memory (already checked above)
                if symbol in self.positions:
                    continue
                
                # Found position in DB but not in memory - check if it needs protection
                if not db_pos.get('has_stop_loss', False):
                    logger.warning(f"⚠️ Found untracked position without SL: {symbol} on {db_pos['exchange']}")
                    
                    # Verify position exists on exchange
                    if await self.verify_position_exists(symbol, db_pos['exchange']):
                        # Create PositionState object for this untracked position
                        untracked_pos = PositionState(
                            id=db_pos['id'],
                            symbol=symbol,
                            exchange=db_pos['exchange'],
                            side=db_pos['side'],
                            quantity=float(db_pos['quantity']),
                            entry_price=float(db_pos['entry_price']),
                            current_price=float(db_pos['entry_price']),  # Will be updated
                            unrealized_pnl=0.0,
                            unrealized_pnl_percent=0.0,
                            has_stop_loss=False,
                            stop_loss_price=None,
                            has_trailing_stop=False,
                            trailing_activated=False,
                            opened_at=db_pos['created_at']
                        )
                        
                        unprotected_positions.append(untracked_pos)
                        
                        # Add to memory for tracking
                        self.positions[symbol] = untracked_pos
                        logger.info(f"✅ Added untracked position {symbol} to memory for protection")
                    else:
                        logger.warning(f"🗑️ Position {symbol} not found on exchange, marking as closed in DB")
                        await self.repository.close_position(
                            db_pos['id'],
                            close_price=float(db_pos['entry_price']),
                            pnl=0.0,
                            exit_reason='phantom_position'
                        )

            # If found unprotected positions, set stop losses
            if unprotected_positions:
                logger.warning(f"🔴 Found {len(unprotected_positions)} positions without stop loss protection!")

                for position in unprotected_positions:
                    try:
                        exchange = self.exchanges.get(position.exchange)
                        if not exchange:
                            logger.error(f"Exchange {position.exchange} not available for {position.symbol}")
                            continue

                        # Calculate stop loss price
                        stop_loss_percent = float(self.config.stop_loss_percent)
                        entry_price = float(position.entry_price)

                        if position.side == 'long':
                            stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                        else:
                            stop_loss_price = entry_price * (1 + stop_loss_percent / 100)

                        # Get current price to validate stop loss
                        ticker = await exchange.fetch_ticker(position.symbol)
                        current_price = ticker.get('last', position.current_price)

                        # Validate stop loss won't trigger immediately
                        if position.side == 'short' and current_price >= stop_loss_price:
                            logger.warning(f"⚠️ Adjusting stop loss for {position.symbol} to prevent immediate trigger")
                            stop_loss_price = current_price * 1.005  # 0.5% above current
                        elif position.side == 'long' and current_price <= stop_loss_price:
                            logger.warning(f"⚠️ Adjusting stop loss for {position.symbol} to prevent immediate trigger")
                            stop_loss_price = current_price * 0.995  # 0.5% below current

                        # Set stop loss
                        if await self._set_stop_loss(exchange, position, stop_loss_price):
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
        Handle REAL zombie positions (delegated to ZombieCleanupService)
        
        REFACTORED: 2025-10-04
        This method now delegates to ZombieCleanupService
        """
        # Delegate to service and sync local cache
        results = await self.zombie_cleanup.handle_real_zombies(self.positions)
        
        # Clean up local positions cache for phantom positions
        for symbol, pos in list(self.positions.items()):
            # Re-verify position exists after cleanup
            if not await self.verify_position_exists(symbol, pos.exchange):
                if symbol in self.positions:
                    del self.positions[symbol]
                logger.debug(f"Removed phantom position from local cache: {symbol}")
        
        return results

    async def cleanup_zombie_orders(self):
        """
        Enhanced zombie order cleanup (delegated to ZombieCleanupService)
        
        REFACTORED: 2025-10-04
        This method now delegates to ZombieCleanupService
        """
        # Delegate to service
        results = await self.zombie_cleanup.cleanup_zombie_orders()
        
        # Sync interval adjustment (service updates its own interval)
        self.sync_interval = self.zombie_cleanup.sync_interval
        
        return results

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

        zombie_stats = {}
        if self.zombie_cleanup:
            zombie_stats = {
                'checks_performed': self.zombie_cleanup.zombie_check_counter,
                'last_zombie_count': self.zombie_cleanup.last_zombie_count,
                'current_sync_interval': self.sync_interval,
                'aggressive_threshold': self.zombie_cleanup.aggressive_cleanup_threshold
            }

        return {
            'open_positions': self.position_count,
            'total_exposure': to_decimal(self.total_exposure),
            'positions_opened': self.stats['positions_opened'],
            'positions_closed': self.stats['positions_closed'],
            'total_pnl': to_decimal(self.stats['total_pnl']),
            'win_rate': win_rate,
            'wins': self.stats['win_count'],
            'zombie_cleanup': zombie_stats,
            'losses': self.stats['loss_count']
        }