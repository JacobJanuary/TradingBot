"""
Smart Trailing Stop Manager
Based on best practices from:
- https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/strategy/stoploss_manager.py
- https://github.com/jesse-ai/jesse/blob/master/jesse/strategies/
"""
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from decimal import Decimal
from core.event_logger import get_event_logger, EventType

logger = logging.getLogger(__name__)

# ============== CONSTANTS ==============

# Price sentinel values for uninitialized tracking
UNINITIALIZED_PRICE_HIGH = Decimal('999999')  # For highest_price in short positions, lowest_price in long

# Peak price persistence configuration
TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC = 10    # Min 10s between peak saves
TRAILING_MIN_PEAK_CHANGE_PERCENT = 0.2      # Save if peak changed > 0.2%
TRAILING_EMERGENCY_PEAK_CHANGE = 1.0        # Always save if peak changed > 1.0%


class TrailingStopState(Enum):
    """Trailing stop states"""
    INACTIVE = "inactive"  # Not activated yet
    WAITING = "waiting"  # Waiting for activation price
    ACTIVE = "active"  # Actively trailing
    TRIGGERED = "triggered"  # Stop triggered


@dataclass
class TrailingStopConfig:
    """Configuration for trailing stop"""
    activation_percent: Decimal = Decimal('1.5')  # Profit % to activate
    callback_percent: Decimal = Decimal('0.5')  # Trail distance %

    # Advanced features
    use_atr: bool = False  # Use ATR for dynamic distance
    atr_multiplier: Decimal = Decimal('2.0')  # ATR multiplier

    step_activation: bool = False  # Step-based activation
    activation_steps: List[Dict] = field(default_factory=lambda: [
        {'profit': 1.0, 'distance': 0.5},
        {'profit': 2.0, 'distance': 0.3},
        {'profit': 3.0, 'distance': 0.2},
    ])

    breakeven_at: Optional[Decimal] = Decimal('0.5')  # Move SL to breakeven at X%

    # Time-based features
    time_based_activation: bool = False
    min_position_age_minutes: int = 10

    # Acceleration feature
    accelerate_on_momentum: bool = False
    momentum_threshold: Decimal = Decimal('0.1')  # Price change % per minute


@dataclass
class TrailingStopInstance:
    """Individual trailing stop instance"""
    symbol: str
    entry_price: Decimal
    current_price: Decimal
    highest_price: Decimal
    lowest_price: Decimal

    state: TrailingStopState = TrailingStopState.INACTIVE
    activation_price: Optional[Decimal] = None
    current_stop_price: Optional[Decimal] = None
    last_stop_update: Optional[datetime] = None

    # SL Update tracking (for rate limiting)
    last_sl_update_time: Optional[datetime] = None  # Last SUCCESSFUL SL update on exchange
    last_updated_sl_price: Optional[Decimal] = None  # Last SUCCESSFULLY updated SL price on exchange

    # Peak price persistence tracking
    last_peak_save_time: Optional[datetime] = None  # Last time peak was saved to DB
    last_saved_peak_price: Optional[Decimal] = None  # Last saved peak value

    # Order tracking
    stop_order_id: Optional[str] = None

    # Statistics
    created_at: datetime = field(default_factory=datetime.now)
    activated_at: Optional[datetime] = None
    highest_profit_percent: Decimal = Decimal('0')
    update_count: int = 0

    # Position info
    side: str = 'long'  # 'long' or 'short'
    quantity: Decimal = Decimal('0')


class SmartTrailingStopManager:
    """
    Advanced trailing stop manager with WebSocket integration
    Handles all trailing stop logic independently of exchange implementation
    """

    def __init__(self, exchange_manager, config: TrailingStopConfig = None, exchange_name: str = None, repository=None):
        """
        Initialize trailing stop manager

        Args:
            exchange_manager: ExchangeManager instance
            config: TrailingStopConfig (optional)
            exchange_name: Exchange name (optional)
            repository: Repository instance for state persistence (optional)
        """
        self.exchange = exchange_manager
        self.exchange_name = exchange_name or getattr(exchange_manager, 'name', 'unknown')
        self.config = config or TrailingStopConfig()
        self.repository = repository  # NEW: For database persistence

        # Active trailing stops
        self.trailing_stops: Dict[str, TrailingStopInstance] = {}

        # Lock for thread safety
        self.lock = asyncio.Lock()

        # Per-symbol locks for SL updates
        self.sl_update_locks = {}

        # Statistics
        self.stats = {
            'total_created': 0,
            'total_activated': 0,
            'total_triggered': 0,
            'average_profit_on_trigger': Decimal('0'),
            'best_profit': Decimal('0')
        }

        logger.info(f"SmartTrailingStopManager initialized with config: {self.config}")

    # ============== DATABASE PERSISTENCE ==============

    async def _save_state(self, ts: TrailingStopInstance) -> bool:
        """
        Save trailing stop state to database

        Called after:
        - create_trailing_stop() - initial state
        - _activate_trailing_stop() - activation
        - _update_trailing_stop() - SL updates

        Args:
            ts: TrailingStopInstance to save

        Returns:
            bool: True if saved successfully, False otherwise
        """
        if not self.repository:
            logger.warning(f"{ts.symbol}: No repository configured, cannot save TS state")
            return False

        try:
            # FIX: P0 - Direct position lookup instead of fetching all positions
            # Old way was O(N) with N=45+ causing 10s+ delays
            # New way is O(1) with index lookup
            async with self.repository.pool.acquire() as conn:
                position_row = await conn.fetchrow("""
                    SELECT id
                    FROM monitoring.positions
                    WHERE symbol = $1
                      AND exchange = $2
                      AND status = 'active'
                    LIMIT 1
                """, ts.symbol, self.exchange_name)

            if not position_row:
                logger.error(f"{ts.symbol}: Position not found in DB, cannot save TS state")
                return False

            position_id = position_row['id']

            # Prepare state data
            state_data = {
                'symbol': ts.symbol,
                'exchange': self.exchange_name,
                'position_id': position_id,
                'state': ts.state.value,
                'is_activated': ts.state == TrailingStopState.ACTIVE,
                'highest_price': float(ts.highest_price) if ts.highest_price else None,
                'lowest_price': float(ts.lowest_price) if ts.lowest_price else None,
                'current_stop_price': float(ts.current_stop_price) if ts.current_stop_price else None,
                'stop_order_id': ts.stop_order_id,
                'activation_price': float(ts.activation_price) if ts.activation_price else None,
                'activation_percent': float(self.config.activation_percent),
                'callback_percent': float(self.config.callback_percent),
                'entry_price': float(ts.entry_price),
                'side': ts.side,
                'quantity': float(ts.quantity),
                'update_count': ts.update_count,
                'highest_profit_percent': float(ts.highest_profit_percent),
                'activated_at': ts.activated_at,
                'last_update_time': ts.last_stop_update,
                'last_sl_update_time': ts.last_sl_update_time,
                'last_updated_sl_price': float(ts.last_updated_sl_price) if ts.last_updated_sl_price else None,
                'last_peak_save_time': ts.last_peak_save_time,
                'last_saved_peak_price': float(ts.last_saved_peak_price) if ts.last_saved_peak_price else None
            }

            # Upsert (INSERT ... ON CONFLICT UPDATE)
            await self.repository.save_trailing_stop_state(state_data)

            logger.debug(f"✅ {ts.symbol}: TS state saved to DB (state={ts.state.value}, update_count={ts.update_count})")
            return True

        except Exception as e:
            logger.error(f"❌ {ts.symbol}: Failed to save TS state: {e}", exc_info=True)
            return False

    async def _restore_state(self, symbol: str) -> Optional[TrailingStopInstance]:
        """
        Restore trailing stop state from database

        Called from position_manager.py during bot startup when loading positions

        Args:
            symbol: Trading symbol

        Returns:
            TrailingStopInstance if state exists in DB, None otherwise
        """
        if not self.repository:
            logger.warning(f"{symbol}: No repository configured, cannot restore TS state")
            return None

        try:
            # Fetch state from database
            state_data = await self.repository.get_trailing_stop_state(symbol, self.exchange_name)

            if not state_data:
                logger.debug(f"{symbol}: No TS state in DB, will create new")
                return None

            # Reconstruct TrailingStopInstance
            ts = TrailingStopInstance(
                symbol=state_data['symbol'],
                entry_price=Decimal(str(state_data['entry_price'])),
                # FIX: Use entry_price for current_price on restore (will be updated on first update_price() call)
                current_price=Decimal(str(state_data['entry_price'])),
                # Restore peaks from DB - these are the actual highest/lowest reached
                # update_price() will naturally update them if price moves beyond these levels
                highest_price=Decimal(str(state_data.get('highest_price', state_data['entry_price']))) if state_data['side'] == 'long' else UNINITIALIZED_PRICE_HIGH,
                lowest_price=UNINITIALIZED_PRICE_HIGH if state_data['side'] == 'long' else Decimal(str(state_data.get('lowest_price', state_data['entry_price']))),
                state=TrailingStopState(state_data['state'].lower()),  # FIX: Handle legacy uppercase states
                activation_price=Decimal(str(state_data['activation_price'])) if state_data.get('activation_price') else None,
                current_stop_price=Decimal(str(state_data['current_stop_price'])) if state_data.get('current_stop_price') else None,
                stop_order_id=state_data.get('stop_order_id'),
                created_at=state_data.get('created_at', datetime.now()),
                activated_at=state_data.get('activated_at'),
                highest_profit_percent=Decimal(str(state_data.get('highest_profit_percent', 0))),
                update_count=state_data.get('update_count', 0),
                side=state_data['side'],
                quantity=Decimal(str(state_data['quantity']))
            )

            # Restore rate limiting fields
            if state_data.get('last_sl_update_time'):
                ts.last_sl_update_time = state_data['last_sl_update_time']
            if state_data.get('last_updated_sl_price'):
                ts.last_updated_sl_price = Decimal(str(state_data['last_updated_sl_price']))
            if state_data.get('last_update_time'):
                ts.last_stop_update = state_data['last_update_time']

            # Restore peak persistence tracking fields
            if state_data.get('last_peak_save_time'):
                ts.last_peak_save_time = state_data['last_peak_save_time']
            if state_data.get('last_saved_peak_price'):
                ts.last_saved_peak_price = Decimal(str(state_data['last_saved_peak_price']))

            logger.info(
                f"✅ {symbol}: TS state RESTORED from DB - "
                f"state={ts.state.value}, "
                f"activated={ts.state == TrailingStopState.ACTIVE}, "
                f"highest_price={ts.highest_price if ts.side == 'long' else 'N/A'}, "
                f"lowest_price={ts.lowest_price if ts.side == 'short' else 'N/A'}, "
                f"current_stop={ts.current_stop_price}, "
                f"update_count={ts.update_count}"
            )

            return ts

        except Exception as e:
            logger.error(f"❌ {symbol}: Failed to restore TS state: {e}", exc_info=True)
            return None

    async def _delete_state(self, symbol: str) -> bool:
        """
        Delete trailing stop state from database

        Called when position is closed

        Args:
            symbol: Trading symbol

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        if not self.repository:
            return False

        try:
            await self.repository.delete_trailing_stop_state(symbol, self.exchange_name)
            logger.debug(f"✅ {symbol}: TS state deleted from DB")
            return True
        except Exception as e:
            logger.error(f"❌ {symbol}: Failed to delete TS state: {e}", exc_info=True)
            return False

    async def create_trailing_stop(self,
                                   symbol: str,
                                   side: str,
                                   entry_price: float,
                                   quantity: float,
                                   initial_stop: Optional[float] = None) -> TrailingStopInstance:
        """
        Create new trailing stop instance

        FIX: P0 - Granular locking to prevent wave execution timeouts
        Lock only held for dict access, not entire TS creation (5x faster!)

        Args:
            symbol: Trading symbol
            side: Position side ('long' or 'short')
            entry_price: Entry price of position
            quantity: Position size
            initial_stop: Initial stop loss price (optional)
        """
        # STEP 1: Quick check if already exists (with lock)
        async with self.lock:
            if symbol in self.trailing_stops:
                logger.warning(f"Trailing stop for {symbol} already exists")
                return self.trailing_stops[symbol]

        # STEP 2: Create instance (NO LOCK - thread-safe, no shared state modified)
        ts = TrailingStopInstance(
            symbol=symbol,
            entry_price=Decimal(str(entry_price)),
            current_price=Decimal(str(entry_price)),
            highest_price=Decimal(str(entry_price)) if side == 'long' else UNINITIALIZED_PRICE_HIGH,
            lowest_price=UNINITIALIZED_PRICE_HIGH if side == 'long' else Decimal(str(entry_price)),
            side=side.lower(),
            quantity=Decimal(str(quantity))
        )

        # STEP 3: Set initial stop if provided (NO LOCK - exchange API call)
        if initial_stop:
            ts.current_stop_price = Decimal(str(initial_stop))
            # Place initial stop order
            await self._place_stop_order(ts)

        # STEP 4: Calculate activation price (NO LOCK - pure computation)
        if side == 'long':
            ts.activation_price = ts.entry_price * (1 + self.config.activation_percent / 100)
        else:
            ts.activation_price = ts.entry_price * (1 - self.config.activation_percent / 100)

        # STEP 5: Log creation (NO LOCK - event queue is async/thread-safe)
        logger.info(
            f"Created trailing stop for {symbol} {side}: "
            f"entry={entry_price}, activation={ts.activation_price}, "
            f"initial_stop={initial_stop}"
        )

        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.TRAILING_STOP_CREATED,
                {
                    'symbol': symbol,
                    'side': side,
                    'entry_price': float(entry_price),
                    'activation_price': float(ts.activation_price),
                    'initial_stop': float(initial_stop) if initial_stop else None,
                    'activation_percent': float(self.config.activation_percent),
                    'callback_percent': float(self.config.callback_percent)
                },
                symbol=symbol,
                exchange=self.exchange_name,
                severity='INFO'
            )

        # STEP 6: Save to database (NO LOCK - DB connection pool handles concurrency)
        await self._save_state(ts)

        # STEP 7: Store instance in dict (QUICK - with lock, double-check pattern)
        async with self.lock:
            # Double-check: another concurrent call might have created it
            if symbol in self.trailing_stops:
                logger.warning(f"Trailing stop for {symbol} created by another task, using existing")
                return self.trailing_stops[symbol]

            self.trailing_stops[symbol] = ts
            self.stats['total_created'] += 1

        return ts

    async def update_price(self, symbol: str, price: float) -> Optional[Dict]:
        """
        Update price and check trailing stop logic
        Called from WebSocket on every price update

        Returns:
            Dict with action if stop needs update, None otherwise
        """
        if symbol not in self.trailing_stops:
            # Position closed or not tracked - silent skip (prevents log spam)
            return None

        async with self.lock:
            ts = self.trailing_stops[symbol]
            old_price = ts.current_price
            ts.current_price = Decimal(str(price))

            # Update highest/lowest
            peak_updated = False
            if ts.side == 'long':
                if ts.current_price > ts.highest_price:
                    old_highest = ts.highest_price
                    ts.highest_price = ts.current_price
                    peak_updated = True
                    logger.debug(f"[TS] {symbol} highest_price updated: {old_highest} → {ts.highest_price}")
            else:
                if ts.current_price < ts.lowest_price:
                    old_lowest = ts.lowest_price
                    ts.lowest_price = ts.current_price
                    peak_updated = True
                    logger.debug(f"[TS] {symbol} lowest_price updated: {old_lowest} → {ts.lowest_price}")

            # NEW: Save peak to database if needed (only for ACTIVE TS)
            if peak_updated and ts.state == TrailingStopState.ACTIVE:
                current_peak = ts.highest_price if ts.side == 'long' else ts.lowest_price
                should_save, skip_reason = self._should_save_peak(ts, current_peak)

                if should_save:
                    # Update tracking fields BEFORE saving
                    ts.last_peak_save_time = datetime.now()
                    ts.last_saved_peak_price = current_peak

                    # Save to database
                    await self._save_state(ts)

                    logger.debug(
                        f"💾 {symbol}: Peak price saved to DB - "
                        f"{'highest' if ts.side == 'long' else 'lowest'}={current_peak:.4f}"
                    )
                else:
                    logger.debug(f"⏭️  {symbol}: Peak save SKIPPED - {skip_reason}")

            # Calculate current profit
            profit_percent = self._calculate_profit_percent(ts)
            if profit_percent > ts.highest_profit_percent:
                ts.highest_profit_percent = profit_percent

            # Log current state
            logger.debug(
                f"[TS] {symbol} @ {ts.current_price:.4f} | "
                f"profit: {profit_percent:.2f}% | "
                f"activation: {ts.activation_price:.4f} | "
                f"state: {ts.state.name}"
            )

            # State machine
            if ts.state == TrailingStopState.INACTIVE:
                return await self._check_activation(ts)

            elif ts.state == TrailingStopState.WAITING:
                return await self._check_activation(ts)

            elif ts.state == TrailingStopState.ACTIVE:
                return await self._update_trailing_stop(ts)

            return None

    async def _check_activation(self, ts: TrailingStopInstance) -> Optional[Dict]:
        """Check if trailing stop should be activated"""

        # Check breakeven first (if configured)
        if self.config.breakeven_at and not ts.current_stop_price:
            profit = self._calculate_profit_percent(ts)
            if profit >= self.config.breakeven_at:
                # Move stop to breakeven
                ts.current_stop_price = ts.entry_price
                ts.state = TrailingStopState.WAITING

                await self._update_stop_order(ts)

                logger.info(f"{ts.symbol}: Moving stop to breakeven at {profit:.2f}% profit")
                return {
                    'action': 'breakeven',
                    'symbol': ts.symbol,
                    'stop_price': float(ts.current_stop_price)
                }

        # Check activation conditions
        should_activate = False

        if ts.side == 'long':
            should_activate = ts.current_price >= ts.activation_price
        else:
            should_activate = ts.current_price <= ts.activation_price

        # Time-based activation
        if self.config.time_based_activation and not should_activate:
            position_age = (datetime.now() - ts.created_at).seconds / 60
            if position_age >= self.config.min_position_age_minutes:
                profit = self._calculate_profit_percent(ts)
                if profit > 0:
                    should_activate = True
                    logger.info(f"{ts.symbol}: Time-based activation after {position_age:.0f} minutes")

        if should_activate:
            return await self._activate_trailing_stop(ts)

        return None

    async def _activate_trailing_stop(self, ts: TrailingStopInstance) -> Dict:
        """Activate trailing stop"""
        ts.state = TrailingStopState.ACTIVE
        ts.activated_at = datetime.now()
        self.stats['total_activated'] += 1

        # Calculate initial trailing stop price
        distance = self._get_trailing_distance(ts)

        if ts.side == 'long':
            ts.current_stop_price = ts.highest_price * (1 - distance / 100)
        else:
            ts.current_stop_price = ts.lowest_price * (1 + distance / 100)

        # Update stop order
        await self._update_stop_order(ts)

        logger.info(
            f"✅ {ts.symbol}: Trailing stop ACTIVATED at {ts.current_price:.4f}, "
            f"stop at {ts.current_stop_price:.4f}"
        )

        # Log trailing stop activation
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.TRAILING_STOP_ACTIVATED,
                {
                    'symbol': ts.symbol,
                    'activation_price': float(ts.current_price),
                    'stop_price': float(ts.current_stop_price),
                    'distance_percent': float(distance),
                    'side': ts.side,
                    'entry_price': float(ts.entry_price),
                    'profit_percent': float(self._calculate_profit_percent(ts))
                },
                symbol=ts.symbol,
                exchange=self.exchange_name,
                severity='INFO'
            )

        # NEW: Mark SL ownership (logging only for now)
        # Note: sl_managed_by field already exists in PositionState
        # PositionManager will see trailing_activated=True and skip protection
        logger.debug(f"{ts.symbol} SL ownership: trailing_stop (via trailing_activated=True)")

        # NEW: Save activated state to database
        await self._save_state(ts)

        return {
            'action': 'activated',
            'symbol': ts.symbol,
            'stop_price': float(ts.current_stop_price),
            'distance_percent': float(distance)
        }

    async def _update_trailing_stop(self, ts: TrailingStopInstance) -> Optional[Dict]:
        """Update trailing stop if price moved favorably"""

        distance = self._get_trailing_distance(ts)
        new_stop_price = None

        if ts.side == 'long':
            # For long: trail below highest price
            potential_stop = ts.highest_price * (1 - distance / 100)

            # Only update if new stop is higher than current
            if potential_stop > ts.current_stop_price:
                new_stop_price = potential_stop
        else:
            # For short: trail above lowest price
            potential_stop = ts.lowest_price * (1 + distance / 100)

            # Only update if new stop is lower than current
            if potential_stop < ts.current_stop_price:
                new_stop_price = potential_stop

        if new_stop_price:
            old_stop = ts.current_stop_price

            # NEW APPROACH: Check FIRST, modify AFTER (no rollback needed)
            try:
                should_update, skip_reason = self._should_update_stop_loss(ts, new_stop_price, old_stop)
            except Exception as e:
                logger.error(f"[TS_UPDATE] {ts.symbol}: ERROR in _should_update_stop_loss: {e}", exc_info=True)
                return None

            if not should_update:
                # Skip update - log reason
                logger.debug(
                    f"⏭️  {ts.symbol}: SL update SKIPPED - {skip_reason} "
                    f"(proposed_stop={new_stop_price:.4f})"
                )

                # Log skip event (optional - для статистики)
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_UPDATED,
                        {
                            'symbol': ts.symbol,
                            'action': 'skipped',
                            'skip_reason': skip_reason,
                            'proposed_new_stop': float(new_stop_price),
                            'current_stop': float(old_stop),
                            'update_count': ts.update_count
                        },
                        symbol=ts.symbol,
                        exchange=self.exchange_name,
                        severity='DEBUG'
                    )

                return None  # Don't proceed with update

            # Get or create lock for this symbol
            if ts.symbol not in self.sl_update_locks:
                self.sl_update_locks[ts.symbol] = asyncio.Lock()

            # PESSIMISTIC UPDATE: Try exchange FIRST, commit state ONLY if success
            update_success = False
            async with self.sl_update_locks[ts.symbol]:
                # Temporarily set new stop for _update_stop_order() to use
                ts.current_stop_price = new_stop_price

                # Update stop order on exchange
                update_success = await self._update_stop_order(ts)

                # ROLLBACK if exchange update failed
                if not update_success:
                    # Restore old stop price
                    ts.current_stop_price = old_stop

                    logger.error(
                        f"❌ {ts.symbol}: SL update FAILED on exchange, "
                        f"state rolled back (keeping old stop {old_stop:.4f})"
                    )

                    # Log failure event
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.TRAILING_STOP_SL_UPDATE_FAILED,
                            {
                                'symbol': ts.symbol,
                                'error': 'Exchange update failed, state rolled back',
                                'proposed_new_stop': float(new_stop_price),
                                'kept_old_stop': float(old_stop),
                                'update_count': ts.update_count
                            },
                            symbol=ts.symbol,
                            exchange=self.exchange_name,
                            severity='ERROR'
                        )

                    # DO NOT save to DB, DO NOT log success, DO NOT increment counter
                    return None

            # Only commit state changes if exchange succeeded
            ts.last_stop_update = datetime.now()
            ts.update_count += 1

            improvement = abs((new_stop_price - old_stop) / old_stop * 100)
            logger.info(
                f"📈 {ts.symbol}: SL moved - Trailing stop updated from {old_stop:.4f} to {new_stop_price:.4f} "
                f"(+{improvement:.2f}%)"
            )

            # Log trailing stop update
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.TRAILING_STOP_UPDATED,
                    {
                        'symbol': ts.symbol,
                        'old_stop': float(old_stop),
                        'new_stop': float(new_stop_price),
                        'improvement_percent': float(improvement),
                        'current_price': float(ts.current_price),
                        'highest_price': float(ts.highest_price) if ts.side == 'long' else None,
                        'lowest_price': float(ts.lowest_price) if ts.side == 'short' else None,
                        'update_count': ts.update_count
                    },
                    symbol=ts.symbol,
                    exchange=self.exchange_name,
                    severity='INFO'
                )

            # Save updated state to database ONLY after exchange confirmed success
            await self._save_state(ts)

            return {
                'action': 'updated',
                'symbol': ts.symbol,
                'old_stop': float(old_stop),
                'new_stop': float(new_stop_price),
                'improvement_percent': float(improvement)
            }

        return None

    def _get_trailing_distance(self, ts: TrailingStopInstance) -> Decimal:
        """Get trailing distance based on configuration"""

        # Step-based distance
        if self.config.step_activation:
            profit = self._calculate_profit_percent(ts)

            for step in reversed(self.config.activation_steps):
                if profit >= step['profit']:
                    return Decimal(str(step['distance']))

        # Momentum-based acceleration
        if self.config.accelerate_on_momentum:
            # Calculate price change rate (simplified)
            if ts.last_stop_update:
                time_diff = (datetime.now() - ts.last_stop_update).seconds / 60
                if time_diff > 0:
                    price_change_rate = abs(
                        (ts.current_price - ts.entry_price) / ts.entry_price / time_diff * 100
                    )

                    if price_change_rate > self.config.momentum_threshold:
                        # Tighten stop on strong momentum
                        return self.config.callback_percent * Decimal('0.7')

        return self.config.callback_percent

    def _calculate_profit_percent(self, ts: TrailingStopInstance) -> Decimal:
        """Calculate current profit percentage"""
        # FIX: Prevent division by zero from corrupted DB data
        if ts.entry_price == 0:
            logger.error(f"❌ {ts.symbol}: entry_price is 0, cannot calculate profit (corrupted data)")
            return Decimal('0')

        if ts.side == 'long':
            return (ts.current_price - ts.entry_price) / ts.entry_price * 100
        else:
            return (ts.entry_price - ts.current_price) / ts.entry_price * 100

    async def _place_stop_order(self, ts: TrailingStopInstance) -> bool:
        """Place initial stop order on exchange"""
        try:
            # NEW: For Binance, cancel Protection Manager SL first
            # This prevents duplication (two STOP_MARKET orders)
            await self._cancel_protection_sl_if_binance(ts)

            # Cancel existing stop order if any
            if ts.stop_order_id:
                await self.exchange.cancel_order(ts.stop_order_id, ts.symbol)

            # Determine order side (opposite of position)
            order_side = 'sell' if ts.side == 'long' else 'buy'

            # Place stop market order
            order = await self.exchange.create_stop_loss_order(
                symbol=ts.symbol,
                side=order_side,
                amount=float(ts.quantity),
                stop_price=float(ts.current_stop_price)
            )

            ts.stop_order_id = order.id
            return True

        except Exception as e:
            logger.error(f"Failed to place stop order for {ts.symbol}: {e}")
            return False

    async def _cancel_protection_sl_if_binance(self, ts: TrailingStopInstance) -> bool:
        """
        Cancel Protection Manager SL order before creating TS SL (Binance only)

        WHY: Binance creates separate STOP_MARKET orders
        - Protection Manager: creates Order #A
        - TS Manager: creates Order #B
        - Result: TWO SL orders → duplication → orphan orders

        SOLUTION: Cancel Order #A before creating Order #B

        Returns:
            bool: True if cancelled or not needed, False if error
        """
        try:
            # Only for Binance
            exchange_name = getattr(self.exchange, 'name', self.exchange_name)
            if exchange_name.lower() != 'binance':
                logger.debug(f"{ts.symbol} Not Binance, skipping Protection SL cancellation")
                return True

            # Fetch all open orders for this symbol
            logger.debug(f"{ts.symbol} Fetching open orders to find Protection SL...")
            orders = await self.exchange.fetch_open_orders(ts.symbol)

            # Find Protection Manager SL order
            # Characteristics:
            # - type: 'STOP_MARKET' or 'stop_market'
            # - side: opposite of position (sell for long, buy for short)
            # - reduceOnly: True
            expected_side = 'sell' if ts.side == 'long' else 'buy'

            protection_sl_orders = []
            for order in orders:
                # OrderResult attributes (not dict methods)
                order_type = order.type.upper() if order.type else ''
                order_side = order.side.lower() if order.side else ''
                # CCXT raw data from order.info
                reduce_only = order.info.get('reduceOnly', False)

                if (order_type == 'STOP_MARKET' and
                    order_side == expected_side and
                    reduce_only):
                    protection_sl_orders.append(order)

            # Cancel found Protection SL orders
            if protection_sl_orders:
                for order in protection_sl_orders:
                    # OrderResult attributes
                    order_id = order.id
                    # CCXT raw data from order.info
                    stop_price = order.info.get('stopPrice', 'unknown')

                    logger.info(
                        f"🗑️  {ts.symbol}: Canceling Protection Manager SL "
                        f"(order_id={order_id}, stopPrice={stop_price}) "
                        f"before TS activation"
                    )

                    await self.exchange.cancel_order(order_id, ts.symbol)

                    # Small delay to ensure cancellation processed
                    await asyncio.sleep(0.1)

                logger.info(
                    f"✅ {ts.symbol}: Cancelled {len(protection_sl_orders)} "
                    f"Protection SL order(s)"
                )
                return True
            else:
                logger.debug(
                    f"{ts.symbol} No Protection SL orders found "
                    f"(expected side={expected_side}, reduceOnly=True)"
                )
                return True

        except Exception as e:
            logger.error(
                f"❌ {ts.symbol}: Failed to cancel Protection SL: {e}",
                exc_info=True
            )
            # Don't fail TS activation if cancellation fails
            # Protection SL will remain → duplication (acceptable vs NO SL)
            return False

    def _should_update_stop_loss(self, ts: TrailingStopInstance,
                                  new_stop_price: Decimal,
                                  old_stop_price: Decimal) -> tuple[bool, Optional[str]]:
        """
        Check if SL should be updated based on rate limiting and conditional update rules

        Implements Freqtrade-inspired rate limiting with emergency override:
        Rule 0: Emergency override - ALWAYS update if improvement >= 1.0% (bypass all limits)
        Rule 1: Rate limiting - Min 60s interval between updates
        Rule 2: Conditional update - Min 0.1% improvement

        Args:
            ts: TrailingStopInstance
            new_stop_price: Proposed new SL price
            old_stop_price: Current SL price

        Returns:
            (should_update: bool, skip_reason: Optional[str])
            - (True, None) if update should proceed
            - (False, "reason") if update should be skipped
        """
        from config.settings import config

        # Calculate improvement first (needed for all rules)
        improvement_percent = abs(
            (new_stop_price - old_stop_price) / old_stop_price * 100
        )

        # Rule 0: EMERGENCY OVERRIDE - Always update if improvement is very large
        # This prevents losing profit during fast price movements
        EMERGENCY_THRESHOLD = 1.0  # 1.0% = 10x normal min_improvement

        if improvement_percent >= EMERGENCY_THRESHOLD:
            logger.info(
                f"⚡ {ts.symbol}: Emergency SL update due to large movement "
                f"({improvement_percent:.2f}% >= {EMERGENCY_THRESHOLD}%) - bypassing rate limit"
            )
            return (True, None)  # Skip all other checks - update immediately!

        # Rule 1: Rate limiting - check time since last SUCCESSFUL update
        if ts.last_sl_update_time:
            # FIX: Handle both naive and aware datetimes
            now = datetime.now()
            last_update = ts.last_sl_update_time

            # If last_update is aware, convert now to aware (UTC)
            if last_update.tzinfo is not None:
                from datetime import timezone
                now = datetime.now(timezone.utc)
            # If last_update is naive but now is aware, make both naive
            elif now.tzinfo is not None:
                now = now.replace(tzinfo=None)

            elapsed_seconds = (now - last_update).total_seconds()
            min_interval = config.trading.trailing_min_update_interval_seconds

            if elapsed_seconds < min_interval:
                remaining = min_interval - elapsed_seconds
                return (False, f"rate_limit: {elapsed_seconds:.1f}s elapsed, need {min_interval}s (wait {remaining:.1f}s)")

        # Rule 2: Conditional update - check minimum improvement
        if ts.last_updated_sl_price:
            min_improvement = float(config.trading.trailing_min_improvement_percent)

            if improvement_percent < min_improvement:
                return (False, f"improvement_too_small: {improvement_percent:.3f}% < {min_improvement}%")

        # All checks passed
        return (True, None)

    def _should_save_peak(self, ts: TrailingStopInstance, new_peak: Decimal) -> tuple[bool, Optional[str]]:
        """
        Check if peak price should be saved to database

        Rules:
        Rule 0: Emergency - ALWAYS save if peak changed >= 1.0%
        Rule 1: Time-based - Save if >= 10s since last peak save
        Rule 2: Improvement-based - Save if peak changed >= 0.2% from last saved

        Args:
            ts: TrailingStopInstance
            new_peak: New peak price value

        Returns:
            (should_save: bool, skip_reason: Optional[str])
        """
        # Rule 0: EMERGENCY - Large peak change
        if ts.last_saved_peak_price:
            peak_change_percent = abs(
                (new_peak - ts.last_saved_peak_price) / ts.last_saved_peak_price * 100
            )

            if peak_change_percent >= TRAILING_EMERGENCY_PEAK_CHANGE:
                logger.debug(
                    f"⚡ {ts.symbol}: Emergency peak save - "
                    f"change {peak_change_percent:.2f}% >= {TRAILING_EMERGENCY_PEAK_CHANGE}%"
                )
                return (True, None)

        # Rule 1: Time-based check
        if ts.last_peak_save_time:
            elapsed_seconds = (datetime.now() - ts.last_peak_save_time).total_seconds()

            if elapsed_seconds < TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC:
                remaining = TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC - elapsed_seconds
                return (False, f"peak_save_rate_limit: {elapsed_seconds:.1f}s elapsed, need {TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC}s (wait {remaining:.1f}s)")

        # Rule 2: Improvement-based check
        if ts.last_saved_peak_price:
            peak_change_percent = abs(
                (new_peak - ts.last_saved_peak_price) / ts.last_saved_peak_price * 100
            )

            if peak_change_percent < TRAILING_MIN_PEAK_CHANGE_PERCENT:
                return (False, f"peak_change_too_small: {peak_change_percent:.3f}% < {TRAILING_MIN_PEAK_CHANGE_PERCENT}%")

        # All checks passed
        return (True, None)

    async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
        """
        Update stop order using atomic method when available

        NEW IMPLEMENTATION:
        - Bybit: Uses trading-stop endpoint (ATOMIC - no race condition)
        - Binance: Uses optimized cancel+create (minimal race window)
        """
        try:
            # DISABLED 2025-10-20: False orphan detection causes TS deletion during activation
            # This check was too aggressive - positions may not be in exchange cache yet during TS creation
            # Orphan cleanup should be handled by position_manager notifications, not here
            # See: docs/investigations/CRITICAL_TS_ACTIVATION_FAILURE.md
            #
            # if hasattr(self.exchange, 'fetch_positions'):
            #     try:
            #         positions = await self.exchange.fetch_positions([ts.symbol])
            #         position_exists = any(
            #             p.get('symbol') == ts.symbol and (p.get('contracts', 0) > 0 or p.get('size', 0) > 0)
            #             for p in positions
            #         )
            #
            #         if not position_exists:
            #             logger.warning(
            #                 f"⚠️ {ts.symbol}: Position not found on exchange, "
            #                 f"removing orphaned trailing stop (auto-cleanup)"
            #             )
            #             # Auto-cleanup orphaned trailing stop
            #             await self.on_position_closed(ts.symbol, realized_pnl=None)
            #             return False
            #     except Exception as e:
            #         # If verification fails, log but continue with SL update
            #         # (don't want verification failures to block legitimate updates)
            #         logger.debug(f"Position verification failed for {ts.symbol}: {e}")

            # Check if atomic update is available
            if not hasattr(self.exchange, 'update_stop_loss_atomic'):
                logger.error(f"{ts.symbol}: Exchange does not support atomic SL update")
                return False

            # Call atomic update
            result = await self.exchange.update_stop_loss_atomic(
                symbol=ts.symbol,
                new_sl_price=float(ts.current_stop_price),
                position_side=ts.side
            )

            if result['success']:
                # Log success with metrics
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_SL_UPDATED,
                        {
                            'symbol': ts.symbol,
                            'method': result['method'],
                            'execution_time_ms': result['execution_time_ms'],
                            'new_sl_price': float(ts.current_stop_price),
                            'old_sl_price': result.get('old_sl_price'),
                            'unprotected_window_ms': result.get('unprotected_window_ms', 0),
                            'side': ts.side,
                            'update_count': ts.update_count
                        },
                        symbol=ts.symbol,
                        exchange=self.exchange.name,
                        severity='INFO'
                    )

                # NEW: Update tracking fields after SUCCESSFUL update
                ts.last_sl_update_time = datetime.now()  # Record time of successful update
                ts.last_updated_sl_price = ts.current_stop_price  # Record successfully updated price

                # NEW: Alert if unprotected window is too large (Binance)
                from config.settings import config
                unprotected_window_ms = result.get('unprotected_window_ms', 0)
                alert_threshold = config.trading.trailing_alert_if_unprotected_window_ms

                if unprotected_window_ms > alert_threshold:
                    logger.warning(
                        f"⚠️  {ts.symbol}: Large unprotected window detected! "
                        f"{unprotected_window_ms:.1f}ms > {alert_threshold}ms threshold "
                        f"(exchange: {self.exchange.name}, method: {result['method']})"
                    )

                    # Log high-severity alert
                    if event_logger:
                        await event_logger.log_event(
                            EventType.WARNING_RAISED,
                            {
                                'symbol': ts.symbol,
                                'warning_type': 'large_unprotected_window',
                                'unprotected_window_ms': unprotected_window_ms,
                                'threshold_ms': alert_threshold,
                                'exchange': self.exchange.name,
                                'method': result['method']
                            },
                            symbol=ts.symbol,
                            exchange=self.exchange.name,
                            severity='WARNING'
                        )

                logger.info(
                    f"✅ {ts.symbol}: SL updated via {result['method']} "
                    f"in {result['execution_time_ms']:.2f}ms"
                )
                return True

            else:
                # Log failure
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_SL_UPDATE_FAILED,
                        {
                            'symbol': ts.symbol,
                            'error': result['error'],
                            'execution_time_ms': result['execution_time_ms'],
                            'method_attempted': result.get('method')
                        },
                        symbol=ts.symbol,
                        exchange=self.exchange.name,
                        severity='ERROR'
                    )

                logger.error(f"❌ {ts.symbol}: SL update failed - {result['error']}")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to update stop order for {ts.symbol}: {e}", exc_info=True)
            return False

    async def on_position_closed(self, symbol: str, realized_pnl: float = None):
        """Handle position closure"""
        if symbol not in self.trailing_stops:
            return

        async with self.lock:
            ts = self.trailing_stops[symbol]
            ts.state = TrailingStopState.TRIGGERED

            # Update statistics
            if ts.state == TrailingStopState.ACTIVE:
                self.stats['total_triggered'] += 1

                if realized_pnl:
                    profit_percent = (realized_pnl / float(ts.entry_price * ts.quantity)) * 100

                    # Update average
                    current_avg = self.stats['average_profit_on_trigger']
                    total = self.stats['total_triggered']
                    self.stats['average_profit_on_trigger'] = (
                            (current_avg * (total - 1) + profit_percent) / total
                    )

                    if profit_percent > self.stats['best_profit']:
                        self.stats['best_profit'] = profit_percent

            # Log trailing stop removal
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.TRAILING_STOP_REMOVED,
                    {
                        'symbol': symbol,
                        'reason': 'position_closed',
                        'state': ts.state.value,
                        'was_active': ts.state == TrailingStopState.ACTIVE,
                        'realized_pnl': float(realized_pnl) if realized_pnl else None,
                        'update_count': ts.update_count,
                        'final_stop_price': float(ts.current_stop_price) if ts.current_stop_price else None
                    },
                    symbol=symbol,
                    exchange=self.exchange_name,
                    severity='INFO'
                )

            # Remove from active stops
            del self.trailing_stops[symbol]

            # NEW: Delete state from database
            await self._delete_state(symbol)

            logger.info(f"Position {symbol} closed, trailing stop removed")

    def get_status(self, symbol: str = None) -> Dict:
        """Get status of trailing stops"""
        if symbol:
            if symbol in self.trailing_stops:
                ts = self.trailing_stops[symbol]
                return {
                    'symbol': symbol,
                    'state': ts.state.value,
                    'entry_price': float(ts.entry_price),
                    'current_price': float(ts.current_price),
                    'stop_price': float(ts.current_stop_price) if ts.current_stop_price else None,
                    'profit_percent': float(self._calculate_profit_percent(ts)),
                    'highest_profit': float(ts.highest_profit_percent),
                    'updates': ts.update_count
                }
            return None

        # Return all
        return {
            'active_stops': len(self.trailing_stops),
            'stops': {
                symbol: self.get_status(symbol)
                for symbol in self.trailing_stops
            },
            'statistics': self.stats
        }
# Alias for compatibility
TrailingStopManager = SmartTrailingStopManager
