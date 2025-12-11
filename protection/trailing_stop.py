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

    # Per-position trailing params (from monitoring.positions)
    activation_percent: Decimal = Decimal('0')  # Saved from position on creation
    callback_percent: Decimal = Decimal('0')    # Saved from position on creation


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

        # CRITICAL: Validate pool is initialized before use
        if not self.repository.pool:
            logger.error(f"❌ {ts.symbol}: Repository pool not initialized!")
            raise RuntimeError("Pool not initialized - TS cannot be persisted")

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
                'activation_percent': float(ts.activation_percent),
                'callback_percent': float(ts.callback_percent),
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

    async def _restore_state(self, symbol: str, position_data: Optional[Dict] = None) -> Optional[TrailingStopInstance]:
        """
        Restore trailing stop state from database

        Called from position_manager.py during bot startup when loading positions

        Args:
            symbol: Trading symbol
            position_data: Optional position data from position_manager (avoids exchange fetch during startup)
                          If provided, will validate against this cached data instead of calling fetch_positions()
                          Format: {'symbol': str, 'side': str, 'size': Decimal, 'entryPrice': Decimal}

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

            # CRITICAL FIX: Validate and normalize side value from database
            # Prevents asymmetry bug between create (normalized) and restore (not normalized)
            # See: docs/new_errors/ERROR3_CORRECTED_INVESTIGATION_FINAL.md
            side_value = state_data.get('side', '').lower()
            if side_value not in ('long', 'short'):
                logger.error(
                    f"❌ {symbol}: Invalid side value in database: '{state_data.get('side')}', "
                    f"defaulting to 'long' (CHECK DATABASE INTEGRITY!)"
                )
                side_value = 'long'

            # ============================================================
            # FIX #1: VALIDATE TS.SIDE AGAINST POSITION.SIDE
            # ============================================================
            # Use cached position data if available (startup mode), otherwise fetch from exchange
            try:
                # Use cached data if passed from position_manager (avoids exchange call during startup)
                if position_data:
                    logger.debug(f"{symbol}: Using cached position data from position_manager (startup mode)")
                    current_position = position_data
                else:
                    logger.debug(f"{symbol}: Validating TS side against exchange position...")
                    positions = await self.exchange.fetch_positions([symbol])

                    # Find position for this symbol
                    current_position = None
                    for pos in positions:
                        if pos.get('symbol') == symbol:
                            # Check if position is open (has size)
                            size = pos.get('contracts', 0) or pos.get('size', 0)
                            if size and size != 0:
                                current_position = pos
                                break

                if not current_position:
                    logger.warning(
                        f"⚠️ {symbol}: TS state exists in DB but no position on exchange - "
                        f"deleting stale TS state"
                    )
                    await self._delete_state(symbol)
                    return None

                # Determine position side from exchange data
                # Bybit: pos['side'] = 'Buy' or 'Sell'
                # Binance: pos['side'] = 'long' or 'short'
                exchange_side_raw = current_position.get('side', '').lower()

                # Normalize exchange side to 'long' or 'short'
                if exchange_side_raw in ('buy', 'long'):
                    exchange_side = 'long'
                elif exchange_side_raw in ('sell', 'short'):
                    exchange_side = 'short'
                else:
                    logger.error(
                        f"❌ {symbol}: Unknown position side from exchange: '{exchange_side_raw}' - "
                        f"cannot validate, deleting TS state"
                    )
                    await self._delete_state(symbol)
                    return None

                # CRITICAL CHECK: Compare TS side vs position side
                if side_value != exchange_side:
                    logger.error(
                        f"🔴 {symbol}: SIDE MISMATCH DETECTED!\n"
                        f"  TS side (from DB):      {side_value}\n"
                        f"  Position side (exchange): {exchange_side}\n"
                        f"  TS entry price (DB):    {state_data.get('entry_price')}\n"
                        f"  Position entry (exchange): {current_position.get('entryPrice')}\n"
                        f"  → Deleting stale TS state (prevents 100% SL failure)"
                    )

                    # Log critical event
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.WARNING_RAISED,
                            {
                                'warning_type': 'ts_side_mismatch_on_restore',
                                'symbol': symbol,
                                'ts_side_db': side_value,
                                'position_side_exchange': exchange_side,
                                'ts_entry_price': float(state_data.get('entry_price', 0)),
                                'position_entry_price': float(current_position.get('entryPrice', 0)),
                                'action': 'deleted_stale_ts_state'
                            },
                            symbol=symbol,
                            exchange=self.exchange_name,
                            severity='ERROR'
                        )

                    # Delete stale state from database
                    await self._delete_state(symbol)

                    # Return None → PositionManager will create new TS with correct side
                    return None

                # Side matches - safe to restore
                data_source = "cached" if position_data else "exchange"
                logger.info(
                    f"✅ {symbol}: TS side validation PASSED "
                    f"(side={side_value}, entry={state_data.get('entry_price')}, source={data_source})"
                )

            except Exception as e:
                logger.error(
                    f"❌ {symbol}: Failed to validate TS side against exchange: {e}\n"
                    f"  → Deleting TS state to be safe (will create new)",
                    exc_info=True
                )
                await self._delete_state(symbol)
                return None

            # ============================================================
            # END FIX #1
            # ============================================================

            # ============================================================
            # FIX #2: RESTORE ACTIVATION_PERCENT AND CALLBACK_PERCENT
            # Bug: These were missing, causing callback_percent=0 and SL=highest_price
            # See: docs/investigations/CRITICAL_TS_CALLBACK_ZERO_BUG_20251028.md
            # ============================================================
            # Read from TS state first
            activation_percent = Decimal(str(state_data.get('activation_percent', 0)))
            callback_percent = Decimal(str(state_data.get('callback_percent', 0)))

            # If zeros in DB (bug), fallback to position table
            if activation_percent == 0 or callback_percent == 0:
                if position_data:
                    # Use position data as fallback
                    activation_percent = Decimal(str(position_data.get('trailing_activation_percent', 2.0)))
                    callback_percent = Decimal(str(position_data.get('trailing_callback_percent', 0.5)))
                    logger.warning(
                        f"⚠️ {symbol}: TS state has zero activation/callback in DB, "
                        f"using position data fallback: activation={activation_percent}%, callback={callback_percent}%"
                    )
                else:
                    # No position data available, use config defaults
                    activation_percent = self.config.activation_percent
                    callback_percent = self.config.callback_percent
                    logger.warning(
                        f"⚠️ {symbol}: TS state has zero activation/callback in DB, "
                        f"using config fallback: activation={activation_percent}%, callback={callback_percent}%"
                    )
            else:
                logger.debug(
                    f"✅ {symbol}: Restored trailing params from DB: "
                    f"activation={activation_percent}%, callback={callback_percent}%"
                )

            # Reconstruct TrailingStopInstance (side already validated)
            ts = TrailingStopInstance(
                symbol=state_data['symbol'],
                entry_price=Decimal(str(state_data['entry_price'])),
                # FIX: Use entry_price for current_price on restore (will be updated on first update_price() call)
                current_price=Decimal(str(state_data['entry_price'])),
                # Restore peaks from DB - these are the actual highest/lowest reached
                # update_price() will naturally update them if price moves beyond these levels
                # CRITICAL FIX: Use normalized side_value instead of state_data['side']
                highest_price=Decimal(str(state_data.get('highest_price', state_data['entry_price']))) if side_value == 'long' else UNINITIALIZED_PRICE_HIGH,
                lowest_price=UNINITIALIZED_PRICE_HIGH if side_value == 'long' else Decimal(str(state_data.get('lowest_price', state_data['entry_price']))),
                state=TrailingStopState(state_data['state'].lower()),  # FIX: Handle legacy uppercase states
                activation_price=Decimal(str(state_data['activation_price'])) if state_data.get('activation_price') else None,
                current_stop_price=Decimal(str(state_data['current_stop_price'])) if state_data.get('current_stop_price') else None,
                stop_order_id=state_data.get('stop_order_id'),
                created_at=state_data.get('created_at', datetime.now()),
                activated_at=state_data.get('activated_at'),
                highest_profit_percent=Decimal(str(state_data.get('highest_profit_percent', 0))),
                update_count=state_data.get('update_count', 0),
                # CRITICAL FIX: Use normalized side_value (matches create_trailing_stop behavior)
                side=side_value,
                quantity=Decimal(str(state_data['quantity'])),
                # FIX #2: Add missing trailing parameters (were defaulting to 0!)
                activation_percent=activation_percent,
                callback_percent=callback_percent
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
                f"side={ts.side} (VALIDATED), "
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
                                   entry_price: Decimal,
                                   quantity: Decimal,
                                   initial_stop: Optional[Decimal] = None,
                                   position_params: Optional[Dict] = None) -> TrailingStopInstance:
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
            position_params: Per-position trailing params (optional, from monitoring.positions)
        """
        # STEP 1: Quick check if already exists (with lock)
        async with self.lock:
            if symbol in self.trailing_stops:
                logger.warning(f"Trailing stop for {symbol} already exists")
                return self.trailing_stops[symbol]

        # STEP 1.5: Determine trailing params (per-position or config fallback)
        if position_params and position_params.get('trailing_activation_percent') is not None:
            # Use per-position params from monitoring.positions
            activation_percent = Decimal(str(position_params['trailing_activation_percent']))
            callback_percent = Decimal(str(position_params.get('trailing_callback_percent', self.config.callback_percent)))
            logger.debug(f"📊 {symbol}: Using per-position trailing params: activation={activation_percent}%, callback={callback_percent}%")
        else:
            # Fallback to config
            activation_percent = self.config.activation_percent
            callback_percent = self.config.callback_percent
            logger.debug(f"📊 {symbol}: Using config trailing params (fallback): activation={activation_percent}%, callback={callback_percent}%")

        # STEP 2: Create instance (NO LOCK - thread-safe, no shared state modified)
        ts = TrailingStopInstance(
            symbol=symbol,
            entry_price=entry_price,
            current_price=entry_price,
            highest_price=entry_price if side == 'long' else UNINITIALIZED_PRICE_HIGH,
            lowest_price=UNINITIALIZED_PRICE_HIGH if side == 'long' else entry_price,
            side=side.lower(),
            quantity=quantity,
            activation_percent=activation_percent,
            callback_percent=callback_percent
        )

        # STEP 3: Set initial stop if provided (NO LOCK - exchange API call)
        if initial_stop:
            ts.current_stop_price = initial_stop
            # Place initial stop order
            await self._place_stop_order(ts)

        # STEP 4: Calculate activation price (NO LOCK - pure computation)
        if side == 'long':
            ts.activation_price = ts.entry_price * (1 + activation_percent / 100)
        else:
            ts.activation_price = ts.entry_price * (1 - activation_percent / 100)

        # STEP 5: Log creation (NO LOCK - event queue is async/thread-safe)
        # FIX #5: Improved logging with side validation
        logger.info(
            f"✅ {symbol}: TS CREATED - "
            f"side={side}, entry={entry_price:.8f}, "
            f"activation={float(ts.activation_price):.8f}, "
            f"initial_stop={f'{initial_stop:.8f}' if initial_stop else 'None'}, "
            f"[SEARCH: ts_created_{symbol}]"
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
                    'activation_percent': float(activation_percent),
                    'callback_percent': float(callback_percent)
                },
                symbol=symbol,
                exchange=self.exchange_name,
                severity='INFO'
            )

        # STEP 6: Save to database (NO LOCK - DB connection pool handles concurrency)
        save_success = await self._save_state(ts)

        # CRITICAL: Verify save succeeded, retry if failed
        if not save_success:
            logger.warning(f"⚠️ {symbol}: Initial TS save failed, retrying with backoff...")
            # Retry 3 times with backoff (1s, 2s, 3s)
            for attempt in range(3):
                await asyncio.sleep(1 * (attempt + 1))
                if await self._save_state(ts):
                    logger.info(f"✅ {symbol}: TS state saved on retry #{attempt + 1}")
                    break
            else:
                # All retries exhausted
                raise RuntimeError(f"Failed to persist TS state for {symbol} after 3 retries")

        # STEP 7: Store instance in dict (QUICK - with lock, double-check pattern)
        async with self.lock:
            # Double-check: another concurrent call might have created it
            if symbol in self.trailing_stops:
                logger.warning(f"Trailing stop for {symbol} created by another task, using existing")
                return self.trailing_stops[symbol]

            self.trailing_stops[symbol] = ts
            self.stats['total_created'] += 1

        return ts

    async def update_price(self, symbol: str, price: Decimal) -> Optional[Dict]:
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
            ts.current_price = price

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

            # CRITICAL FIX: Calculate profit_percent BEFORE using it in logging
            profit_percent = self._calculate_profit_percent(ts)
            if profit_percent > ts.highest_profit_percent:
                ts.highest_profit_percent = profit_percent

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

                    # trailing_stop.py:465 - изменить с debug на info
                    logger.info(  # было: logger.debug
                        f"[TS] {symbol} @ {ts.current_price:.4f} | "
                        f"profit: {profit_percent:.2f}% | "
                        f"activation: {ts.activation_price:.4f} | "
                        f"state: {ts.state.name}"
                    )
                else:
                    logger.debug(f"⏭️  {symbol}: Peak save SKIPPED - {skip_reason}")

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
            should_activate = (
                ts.activation_price is not None
                and ts.current_price >= ts.activation_price
            )
        else:
            should_activate = (
                ts.activation_price is not None
                and ts.current_price <= ts.activation_price
            )

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

    async def _activate_trailing_stop(self, ts: TrailingStopInstance) -> Optional[Dict]:
        """
        Activate trailing stop with retry logic
        
        FIX: Don't mark as activated if SL update fails (prevents unprotected positions)
        Implements 3 retry attempts with exponential backoff
        """
        MAX_RETRIES = 3
        RETRY_DELAYS = [0.3, 0.7, 1.5]  # Exponential backoff in seconds
        
        # Save original state for rollback
        original_state = ts.state
        original_stop_price = ts.current_stop_price
        
        # Calculate initial trailing stop price
        distance = self._get_trailing_distance(ts)

        if ts.side == 'long':
            proposed_stop_price = ts.highest_price * (1 - distance / 100)
        else:
            proposed_stop_price = ts.lowest_price * (1 + distance / 100)
        
        # ============================================================
        # EMERGENCY CLOSE PRE-CHECK
        # ============================================================
        # If price already crossed proposed SL, close immediately
        # Don't retry - position already lost!
        #
        # This prevents:
        # 1. Binance -2021 errors (order would immediately trigger)
        # 2. Unprotected positions during retry loops
        # 3. Unnecessary API calls when result is predetermined
        
        should_emergency_close = False
        if ts.side == 'short' and ts.current_price >= proposed_stop_price:
            should_emergency_close = True
        elif ts.side == 'long' and ts.current_price <= proposed_stop_price:
            should_emergency_close = True
        
        if should_emergency_close:
            logger.error(
                f"🔴 {ts.symbol}: EMERGENCY - Price crossed proposed SL during activation! "
                f"side={ts.side}, current={ts.current_price:.8f}, proposed_sl={proposed_stop_price:.8f}. "
                f"Executing IMMEDIATE MARKET CLOSE (bypassing retry loop). "
                f"[SEARCH: ts_emergency_close_pre_activation_{ts.symbol}]"
            )
            
            try:
                # Close position immediately via market order
                close_side = 'sell' if ts.side == 'long' else 'buy'
                await self.exchange.create_market_order(
                    symbol=ts.symbol,
                    side=close_side,
                    amount=float(ts.quantity),
                    params={'reduceOnly': True}
                )
                
                logger.info(f"✅ {ts.symbol}: Emergency market close executed successfully")
                
                # Log emergency close event
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.WARNING_RAISED,
                        {
                            'warning_type': 'ts_emergency_close_pre_activation',
                            'symbol': ts.symbol,
                            'side': ts.side,
                            'current_price': float(ts.current_price),
                            'proposed_sl': float(proposed_stop_price),
                            'entry_price': float(ts.entry_price),
                            'message': 'Position closed immediately - price crossed SL during activation'
                        },
                        symbol=ts.symbol,
                        exchange=self.exchange_name,
                        severity='ERROR'
                    )
                
                # Return None - don't activate TS, position closed
                return None
                
            except Exception as e:
                error_msg = str(e)
                # Check for "ReduceOnly rejected" - position already closed
                if "-2022" in error_msg or "ReduceOnly" in error_msg:
                    logger.info(
                        f"ℹ️ {ts.symbol}: Emergency close skipped - position already closed "
                        f"(ReduceOnly rejected). SL likely triggered by exchange."
                    )
                    return None
                
                logger.error(
                    f"❌ {ts.symbol}: Emergency market close FAILED: {e}. "
                    f"Will attempt normal TS activation (may fail with -2021).",
                    exc_info=True
                )
                # Fall through to normal retry logic
        
        # ============================================================
        # END EMERGENCY CLOSE PRE-CHECK
        # ============================================================
        
        # Try activation with retries
        for attempt in range(MAX_RETRIES):
            try:
                # Set state for this attempt
                ts.state = TrailingStopState.ACTIVE
                ts.current_stop_price = proposed_stop_price
                
                # Update stop order on exchange
                success = await self._update_stop_order(ts)
                
                if success:
                    # SUCCESS: Mark as activated
                    ts.activated_at = datetime.now()
                    self.stats['total_activated'] += 1
                    
                    logger.info(
                        f"✅ {ts.symbol}: TS ACTIVATED - "
                        f"side={ts.side}, "
                        f"price={ts.current_price:.8f}, "
                        f"sl={ts.current_stop_price:.8f}, "
                        f"entry={ts.entry_price:.8f}, "
                        f"profit={self._calculate_profit_percent(ts):.2f}%, "
                        f"attempt={attempt + 1}/{MAX_RETRIES}, "
                        f"[SEARCH: ts_activated_{ts.symbol}]"
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
                                'profit_percent': float(self._calculate_profit_percent(ts)),
                                'attempts': attempt + 1
                            },
                            symbol=ts.symbol,
                            exchange=self.exchange_name,
                            severity='INFO'
                        )

                    logger.debug(f"{ts.symbol} SL ownership: trailing_stop (via trailing_activated=True)")

                    # Save activated state to database
                    await self._save_state(ts)

                    return {
                        'action': 'activated',
                        'symbol': ts.symbol,
                        'stop_price': float(ts.current_stop_price),
                        'distance_percent': float(distance)
                    }
                
                # FAILED: Rollback state
                ts.state = original_state
                ts.current_stop_price = original_stop_price
                
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"⚠️ {ts.symbol}: TS activation failed (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                # Exception during activation - rollback and retry
                ts.state = original_state
                ts.current_stop_price = original_stop_price
                
                logger.error(
                    f"❌ {ts.symbol}: Exception during TS activation (attempt {attempt + 1}/{MAX_RETRIES}): {e}",
                    exc_info=True
                )
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
        
        # ALL RETRIES FAILED - critical error
        logger.error(
            f"🔴 {ts.symbol}: TS ACTIVATION FAILED after {MAX_RETRIES} attempts! "
            f"Position remains with Protection SL (if exists). "
            f"[SEARCH: ts_activation_failed_{ts.symbol}]"
        )
        
        # Log critical failure event
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.TRAILING_STOP_ACTIVATION_FAILED,
                {
                    'symbol': ts.symbol,
                    'attempts': MAX_RETRIES,
                    'side': ts.side,
                    'current_price': float(ts.current_price),
                    'proposed_sl': float(proposed_stop_price),
                    'entry_price': float(ts.entry_price),
                    'profit_percent': float(self._calculate_profit_percent(ts))
                },
                symbol=ts.symbol,
                exchange=self.exchange_name,
                severity='ERROR'
            )
        
        # Return None to indicate failure (caller should handle)
        return None

    async def _update_trailing_stop(self, ts: TrailingStopInstance) -> Optional[Dict]:
        """Update trailing stop if price moved favorably"""

        distance = self._get_trailing_distance(ts)
        new_stop_price = None

        if ts.side == 'long':
            # For long: trail below highest price
            potential_stop = ts.highest_price * (1 - distance / 100)

            # Only update if new stop is higher than current
            if ts.current_stop_price is not None and potential_stop > ts.current_stop_price:
                new_stop_price = potential_stop
        else:  # SHORT позиция
            # For short: trail above lowest price
            potential_stop = ts.lowest_price * (1 + distance / 100)

            # CRITICAL FIX: Only update SL when price is falling or at minimum
            # Never lower SL when price is rising for SHORT!
            price_at_or_below_minimum = ts.current_price <= ts.lowest_price

            if price_at_or_below_minimum:
                # Price is at minimum or making new low - can update SL
                if ts.current_stop_price is not None and potential_stop < ts.current_stop_price:
                    new_stop_price = potential_stop
                    logger.debug(f"SHORT {ts.symbol}: updating SL on new low, {ts.current_stop_price:.8f} → {potential_stop:.8f}")
            else:
                # Price is above minimum - SL should stay in place
                logger.debug(f"SHORT {ts.symbol}: price {ts.current_price:.8f} > lowest {ts.lowest_price:.8f}, keeping SL at {ts.current_stop_price:.8f}")

        if new_stop_price:
            old_stop = ts.current_stop_price

            # Skip if old_stop is None (first time setting SL)
            if old_stop is None:
                logger.debug(f"{ts.symbol}: No old stop price, setting initial stop")
                ts.current_stop_price = new_stop_price
                ts.last_stop_update = datetime.now()
                ts.update_count += 1
                await self._update_stop_order(ts)
                await self._save_state(ts)
                return {
                    'action': 'initial_set',
                    'symbol': ts.symbol,
                    'new_stop': float(new_stop_price)
                }

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

                    # FIX #5: Improved logging with side validation
                    logger.error(
                        f"❌ {ts.symbol}: SL UPDATE FAILED - "
                        f"side={ts.side}, "
                        f"proposed_sl={new_stop_price:.8f}, "
                        f"kept_old_sl={old_stop:.8f}, "
                        f"price={ts.current_price:.8f}, "
                        f"entry={ts.entry_price:.8f}, "
                        f"peak={('highest' if ts.side == 'long' else 'lowest')}={ts.highest_price if ts.side == 'long' else ts.lowest_price:.8f}, "
                        f"[SEARCH: ts_sl_failed_{ts.symbol}]"
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
            # FIX #5: Improved logging with side validation
            logger.info(
                f"📈 {ts.symbol}: SL UPDATED - "
                f"side={ts.side}, "
                f"old_sl={old_stop:.8f}, "
                f"new_sl={new_stop_price:.8f}, "
                f"improvement={improvement:.2f}%, "
                f"price={ts.current_price:.8f}, "
                f"peak={('highest' if ts.side == 'long' else 'lowest')}={ts.highest_price if ts.side == 'long' else ts.lowest_price:.8f}, "
                f"[SEARCH: ts_sl_updated_{ts.symbol}]"
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
                time_diff = Decimal(str((datetime.now() - ts.last_stop_update).seconds / 60))
                if time_diff > 0:
                    price_change_rate = abs(
                        (ts.current_price - ts.entry_price) / ts.entry_price / time_diff * Decimal('100')
                    )

                    if price_change_rate > self.config.momentum_threshold:
                        # Tighten stop on strong momentum
                        return ts.callback_percent * Decimal('0.7')

        return ts.callback_percent

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
            if ts.current_stop_price is None:
                logger.error(f"Cannot place stop order: stop_price is None for {ts.symbol}")
                return False

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
            
            logger.info(f"🔍 {ts.symbol}: Found {len(orders)} open orders, checking for Protection SL...")

            # Find Protection Manager SL order
            # Characteristics:
            # - type: 'STOP_MARKET' or 'stop_market' or 'STOPMARKET' (variations)
            # - side: opposite of position (sell for long, buy for short)
            # - reduceOnly: True
            expected_side = 'sell' if ts.side == 'long' else 'buy'

            protection_sl_orders = []
            for order in orders:
                # FIX #2: More robust type detection
                # Normalize: uppercase, remove underscores/spaces
                order_type_raw = order.type or ''
                order_type = order_type_raw.upper().replace('_', '').replace(' ', '')
                
                order_side_raw = order.side or ''
                order_side = order_side_raw.lower()
                
                # Check reduceOnly in multiple formats
                reduce_only = order.info.get('reduceOnly', order.info.get('reduce_only', False))
                
                # Log each order for debugging
                logger.debug(
                    f"  Order {order.id}: type={order_type_raw} (normalized: {order_type}), "
                    f"side={order_side_raw}, reduceOnly={reduce_only}"
                )

                # Match any STOP-type order on correct side with reduceOnly
                if ('STOP' in order_type and
                    order_side == expected_side and
                    reduce_only):
                    protection_sl_orders.append(order)
                    logger.info(
                        f"  ✅ Found Protection SL candidate: {order.id} "
                        f"(type={order_type_raw}, side={order_side_raw}, stopPrice={order.info.get('stopPrice', 'N/A')})"
                    )

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

            # ============================================================
            # FIX #2: VALIDATE SL DIRECTION BEFORE EXCHANGE CALL
            # ============================================================
            # Safety check: Ensure new SL price is on correct side of current price
            #
            # Rules:
            # - LONG: SL must be BELOW current price (price falling triggers SL)
            # - SHORT: SL must be ABOVE current price (price rising triggers SL)
            #
            # This catches side mismatch bugs BEFORE they cause exchange errors

            sl_price = ts.current_stop_price
            current_price = ts.current_price

            # Determine if SL direction is valid
            is_sl_valid = False
            validation_error = None

            # NEW: Check for instant price crossing (Emergency Close Condition)
            # If price has already crossed the proposed SL, we must close immediately
            should_emergency_close = False
            if sl_price is not None:
                if ts.side == 'long' and current_price <= sl_price:
                    should_emergency_close = True
                elif ts.side == 'short' and current_price >= sl_price:
                    should_emergency_close = True

            if should_emergency_close:
                logger.warning(
                    f"⚡ {ts.symbol}: Price crossed SL level ({sl_price:.8f}) instantly! "
                    f"Current: {current_price:.8f}. Executing EMERGENCY MARKET CLOSE."
                )
                
                try:
                    # Execute market close
                    close_side = 'sell' if ts.side == 'long' else 'buy'
                    await self.exchange.create_market_order(
                        symbol=ts.symbol,
                        side=close_side,
                        amount=float(ts.quantity),
                        params={'reduceOnly': True}
                    )

                    # Log event
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.WARNING_RAISED,
                            {
                                'warning_type': 'ts_emergency_close_instant_cross',
                                'symbol': ts.symbol,
                                'close_price': float(current_price),
                                'sl_price': float(sl_price),
                                'message': 'Emergency market close triggered due to instant price crossing SL level'
                            },
                            symbol=ts.symbol,
                            exchange=self.exchange_name,
                            severity='WARNING'
                        )
                    
                    return False  # Stop SL update
                except Exception as e:
                    # Check for "ReduceOnly Order is rejected" (Binance code -2022)
                    # This means the position is already closed (or size is 0), which is our goal.
                    error_msg = str(e)
                    if "-2022" in error_msg or "ReduceOnly" in error_msg:
                        logger.info(
                            f"ℹ️ {ts.symbol}: Emergency close skipped - Position already closed by exchange "
                            f"(ReduceOnly rejected). This is expected if SL triggered."
                        )
                        return False
                    
                    logger.error(f"❌ {ts.symbol}: Failed to execute emergency market close: {e}", exc_info=True)
                    return False

            # Normal validation
            if ts.side == 'long':
                # For LONG: SL must be < current price
                if sl_price is not None and sl_price < current_price:
                    is_sl_valid = True
                else:
                    validation_error = (
                        f"LONG position requires SL < current_price, "
                        f"but {f'{sl_price:.8f}' if sl_price is not None else 'None'} >= {current_price:.8f}"
                    )

            elif ts.side == 'short':
                # For SHORT: SL must be > current price
                if sl_price is not None and sl_price > current_price:
                    is_sl_valid = True
                else:
                    validation_error = (
                        f"SHORT position requires SL > current_price, "
                        f"but {f'{sl_price:.8f}' if sl_price is not None else 'None'} <= {current_price:.8f}"
                    )

            else:
                validation_error = f"Unknown side: '{ts.side}'"

            # If validation failed, abort update
            if not is_sl_valid:
                logger.error(
                    f"🔴 {ts.symbol}: SL VALIDATION FAILED - Invalid SL direction!\n"
                    f"  Side:          {ts.side}\n"
                    f"  Current Price: {current_price:.8f}\n"
                    f"  Proposed SL:   {sl_price:.8f}\n"
                    f"  Error:         {validation_error}\n"
                    f"  → ABORTING SL update (would fail on exchange)"
                )

                # Log critical event
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_SL_UPDATE_FAILED,
                        {
                            'symbol': ts.symbol,
                            'error_type': 'sl_direction_validation_failed',
                            'side': ts.side,
                            'current_price': float(current_price),
                            'proposed_sl_price': float(sl_price) if sl_price is not None else None,
                            'validation_error': validation_error,
                            'entry_price': float(ts.entry_price),
                            'highest_price': float(ts.highest_price) if ts.side == 'long' and ts.highest_price is not None else None,
                            'lowest_price': float(ts.lowest_price) if ts.side == 'short' and ts.lowest_price is not None else None,
                            'action': 'aborted_before_exchange_call'
                        },
                        symbol=ts.symbol,
                        exchange=self.exchange_name,
                        severity='ERROR'
                    )

                # Return False → triggers rollback in _update_trailing_stop()
                return False

            # Validation passed - safe to proceed
            logger.debug(
                f"✅ {ts.symbol}: SL validation PASSED - "
                f"side={ts.side}, sl={sl_price:.8f}, price={current_price:.8f}"
            )

            # ============================================================
            # END FIX #2
            # ============================================================

            # Call atomic update (now safe)
            if ts.current_stop_price is None:
                logger.error(f"Cannot update SL: current_stop_price is None for {ts.symbol}")
                return False

            result = await self.exchange.update_stop_loss_atomic(
                symbol=ts.symbol,
                new_sl_price=float(ts.current_stop_price),
                position_side=ts.side
            )

            if result['success']:
                # FIX #3: VERIFY that SL actually exists on exchange
                # Don't trust 'success' blindly - confirm order is there
                try:
                    await asyncio.sleep(0.2)  # Let exchange process the order
                    
                    orders = await self.exchange.fetch_open_orders(ts.symbol)
                    expected_side = 'sell' if ts.side == 'long' else 'buy'
                    
                    sl_exists = any(
                        'STOP' in (o.type or '').upper() and
                        o.side.lower() == expected_side
                        for o in orders
                    )
                    
                    # FIX (Dec 11, 2025): Check Algo Orders for Binance
                    # Since we now use fapiPrivatePostAlgoOrder, orders don't show in standard fetch_open_orders
                    if not sl_exists and self.exchange.name == 'binance':
                        try:
                            # Normalize symbol for Binance
                            binance_symbol = ts.symbol.replace('/', '').replace(':USDT', '')
                            
                            # Fetch open Algo orders
                            algo_res = await self.exchange.exchange.fapiPrivateGetOpenAlgoOrders({
                                'symbol': binance_symbol,
                                'algo_type': 'STOP_MARKET'
                            })
                            
                            # Handle response (list or dict with 'orders')
                            algo_orders = []
                            if isinstance(algo_res, dict) and 'orders' in algo_res:
                                algo_orders = algo_res['orders']
                            elif isinstance(algo_res, list):
                                algo_orders = algo_res
                                
                            for order in algo_orders:
                                # Check matches
                                if (order.get('side', '').lower() == expected_side and 
                                    order.get('orderType') == 'STOP_MARKET'):
                                    sl_exists = True
                                    logger.info(
                                        f"✅ Found SL in Binance Algo API: {order.get('algoId')} "
                                        f"@{order.get('triggerPrice') or order.get('stopPrice')}"
                                    )
                                    break
                                    
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to verify Binance Algo Orders: {e}")
                    
                    if not sl_exists:
                        logger.error(
                            f"❌ {ts.symbol}: SL update claimed success but NO SL found on exchange! "
                            f"Expected {expected_side} STOP order. This is a critical bug."
                        )
                        
                        # Log critical verification failure
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.WARNING_RAISED,
                                {
                                    'warning_type': 'sl_verification_failed',
                                    'symbol': ts.symbol,
                                    'message': 'SL update succeeded but order not found on exchange',
                                    'expected_side': expected_side,
                                    'method': result['method']
                                },
                                symbol=ts.symbol,
                                exchange=self.exchange.name,
                                severity='ERROR'
                            )
                        
                        return False  # Trigger rollback in caller
                    
                    logger.debug(f"✅ {ts.symbol}: SL verified on exchange (expected {expected_side} STOP found)")
                    
                except Exception as e:
                    # Verification failed but don't fail the update
                    # (Exchange might be slow, order might appear later)
                    logger.warning(
                        f"⚠️ {ts.symbol}: Failed to verify SL existence: {e}. "
                        f"Assuming success since exchange returned success."
                    )
                
                # Log success with metrics
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_SL_UPDATED,
                        {
                            'symbol': ts.symbol,
                            'method': result['method'],
                            'execution_time_ms': result['execution_time_ms'],
                            'new_sl_price': float(ts.current_stop_price) if ts.current_stop_price is not None else None,
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

    async def on_position_closed(self, symbol: str, realized_pnl: Optional[Decimal] = None):
        """Handle position closure

        FIX #3: Always clean database state, even if TS not in memory
        """
        if symbol not in self.trailing_stops:
            # TS not in memory, but might exist in DB (orphaned state)
            # FIX #3: Clean database anyway to prevent stale states
            logger.debug(f"{symbol}: Position closed but no TS in memory, checking DB...")
            delete_success = await self._delete_state(symbol)
            if delete_success:
                logger.info(f"✅ {symbol}: Cleaned orphaned TS state from database on position close")
            return

        async with self.lock:
            ts = self.trailing_stops[symbol]
            ts.state = TrailingStopState.TRIGGERED

            # Update statistics
            if ts.state == TrailingStopState.ACTIVE:
                self.stats['total_triggered'] += 1

                if realized_pnl:
                    profit_percent = (realized_pnl / (ts.entry_price * ts.quantity)) * Decimal('100')

                    # Update average
                    current_avg = Decimal(str(self.stats['average_profit_on_trigger']))
                    total = Decimal(str(self.stats['total_triggered']))
                    self.stats['average_profit_on_trigger'] = (
                            (current_avg * (total - Decimal('1')) + profit_percent) / total
                    )

                    best_profit = Decimal(str(self.stats['best_profit']))
                    if profit_percent > best_profit:
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

            # ============================================================
            # FIX #3: VERIFY TS STATE DELETED FROM DATABASE
            # ============================================================
            # Delete state from database and verify success
            delete_success = await self._delete_state(symbol)

            if delete_success:
                logger.info(
                    f"✅ {symbol}: Position closed, TS removed from memory AND database - "
                    f"side={ts.side}, entry={ts.entry_price}, updates={ts.update_count}"
                )
            else:
                logger.error(
                    f"⚠️ {symbol}: Position closed, TS removed from memory BUT database deletion FAILED - "
                    f"side={ts.side}, entry={ts.entry_price} (may leave stale state in DB)"
                )
            # ============================================================
            # END FIX #3
            # ============================================================

    # ============================================================
    # FIX #4: TS-POSITION CONSISTENCY CHECK
    # ============================================================

    async def check_ts_position_consistency(self) -> Dict[str, any]:
        """
        Periodic health check: Verify TS.side matches position.side for all active TS

        Called by scheduler every 5 minutes

        FIX #4: Detects side mismatches that slip through other defenses

        Returns:
            Dict with check results and metrics
        """
        logger.info("🔍 Running TS-Position consistency check...")

        results = {
            'total_ts_checked': 0,
            'mismatches_detected': 0,
            'auto_fixed': 0,
            'check_failures': 0,
            'details': []
        }

        # Get all active TS
        async with self.lock:
            symbols_to_check = list(self.trailing_stops.keys())

        if not symbols_to_check:
            logger.info("✅ No active TS to check")
            return results

        # Check each TS
        for symbol in symbols_to_check:
            results['total_ts_checked'] += 1

            try:
                ts = self.trailing_stops.get(symbol)
                if not ts:
                    continue

                # Fetch position from exchange
                positions = await self.exchange.fetch_positions([symbol])

                # Find position
                current_position = None
                for pos in positions:
                    if pos.get('symbol') == symbol:
                        size = pos.get('contracts', 0) or pos.get('size', 0)
                        if size and size != 0:
                            current_position = pos
                            break

                if not current_position:
                    logger.warning(
                        f"⚠️ {symbol}: TS exists but no position on exchange - "
                        f"orphaned TS (will be cleaned on next position update)"
                    )
                    results['details'].append({
                        'symbol': symbol,
                        'issue': 'orphaned_ts',
                        'action': 'pending_cleanup'
                    })
                    continue

                # Determine position side from exchange
                exchange_side_raw = current_position.get('side', '').lower()

                # Normalize exchange side
                if exchange_side_raw in ('buy', 'long'):
                    exchange_side = 'long'
                elif exchange_side_raw in ('sell', 'short'):
                    exchange_side = 'short'
                else:
                    logger.error(
                        f"❌ {symbol}: Unknown position side from exchange: '{exchange_side_raw}'"
                    )
                    results['check_failures'] += 1
                    results['details'].append({
                        'symbol': symbol,
                        'issue': 'unknown_exchange_side',
                        'exchange_side_raw': exchange_side_raw
                    })
                    continue

                # Compare TS side vs position side
                if ts.side != exchange_side:
                    # MISMATCH DETECTED!
                    results['mismatches_detected'] += 1

                    logger.error(
                        f"🔴 {symbol}: SIDE MISMATCH in consistency check!\n"
                        f"  TS side:       {ts.side}\n"
                        f"  Exchange side: {exchange_side}\n"
                        f"  TS entry:      {ts.entry_price}\n"
                        f"  Exchange entry: {current_position.get('entryPrice')}\n"
                        f"  → AUTO-FIXING: Deleting TS and recreating"
                    )

                    # Log critical event
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.WARNING_RAISED,
                            {
                                'warning_type': 'ts_side_mismatch_in_health_check',
                                'symbol': symbol,
                                'ts_side': ts.side,
                                'position_side_exchange': exchange_side,
                                'ts_entry_price': float(ts.entry_price),
                                'position_entry_price': float(current_position.get('entryPrice', 0)),
                                'action': 'auto_fix_delete_and_recreate'
                            },
                            symbol=symbol,
                            exchange=self.exchange_name,
                            severity='ERROR'
                        )

                    # Auto-fix: Delete TS (will be recreated on next price update)
                    await self.on_position_closed(symbol, realized_pnl=None)

                    results['auto_fixed'] += 1
                    results['details'].append({
                        'symbol': symbol,
                        'issue': 'side_mismatch',
                        'ts_side': ts.side,
                        'exchange_side': exchange_side,
                        'action': 'deleted_ts'
                    })

                else:
                    # Match - all good
                    logger.debug(f"✅ {symbol}: TS side matches position side ({ts.side})")

            except Exception as e:
                logger.error(f"❌ {symbol}: Failed to check TS consistency: {e}", exc_info=True)
                results['check_failures'] += 1
                results['details'].append({
                    'symbol': symbol,
                    'issue': 'check_exception',
                    'error': str(e)
                })

        # Log summary
        logger.info(
            f"✅ TS consistency check complete:\n"
            f"  Checked:    {results['total_ts_checked']}\n"
            f"  Mismatches: {results['mismatches_detected']}\n"
            f"  Auto-fixed: {results['auto_fixed']}\n"
            f"  Failures:   {results['check_failures']}"
        )

        # Log metrics event
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.HEALTH_CHECK_COMPLETED,
                {
                    'check_type': 'ts_position_consistency',
                    'total_checked': results['total_ts_checked'],
                    'mismatches_detected': results['mismatches_detected'],
                    'auto_fixed': results['auto_fixed'],
                    'check_failures': results['check_failures']
                },
                exchange=self.exchange_name,
                severity='INFO'
            )

        return results

    # ============================================================
    # END FIX #4
    # ============================================================

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
