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

    def __init__(self, exchange_manager, config: TrailingStopConfig = None):
        """Initialize trailing stop manager"""
        self.exchange = exchange_manager
        self.config = config or TrailingStopConfig()

        # Active trailing stops
        self.trailing_stops: Dict[str, TrailingStopInstance] = {}

        # Lock for thread safety
        self.lock = asyncio.Lock()

        # Statistics
        self.stats = {
            'total_created': 0,
            'total_activated': 0,
            'total_triggered': 0,
            'average_profit_on_trigger': Decimal('0'),
            'best_profit': Decimal('0')
        }

        logger.info(f"SmartTrailingStopManager initialized with config: {self.config}")

    async def create_trailing_stop(self,
                                   symbol: str,
                                   side: str,
                                   entry_price: float,
                                   quantity: float,
                                   initial_stop: Optional[float] = None) -> TrailingStopInstance:
        """
        Create new trailing stop instance

        Args:
            symbol: Trading symbol
            side: Position side ('long' or 'short')
            entry_price: Entry price of position
            quantity: Position size
            initial_stop: Initial stop loss price (optional)
        """
        async with self.lock:
            # Check if already exists
            if symbol in self.trailing_stops:
                logger.warning(f"Trailing stop for {symbol} already exists")
                return self.trailing_stops[symbol]

            # Create instance
            ts = TrailingStopInstance(
                symbol=symbol,
                entry_price=Decimal(str(entry_price)),
                current_price=Decimal(str(entry_price)),
                highest_price=Decimal(str(entry_price)) if side == 'long' else Decimal('999999'),
                lowest_price=Decimal('999999') if side == 'long' else Decimal(str(entry_price)),
                side=side.lower(),
                quantity=Decimal(str(quantity))
            )

            # Set initial stop if provided
            if initial_stop:
                ts.current_stop_price = Decimal(str(initial_stop))

                # Place initial stop order
                await self._place_stop_order(ts)

            # Calculate activation price
            if side == 'long':
                ts.activation_price = ts.entry_price * (1 + self.config.activation_percent / 100)
            else:
                ts.activation_price = ts.entry_price * (1 - self.config.activation_percent / 100)

            # Store instance
            self.trailing_stops[symbol] = ts
            self.stats['total_created'] += 1

            logger.info(
                f"Created trailing stop for {symbol} {side}: "
                f"entry={entry_price}, activation={ts.activation_price}, "
                f"initial_stop={initial_stop}"
            )

            # Log trailing stop creation
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

            return ts

    async def update_price(self, symbol: str, price: float) -> Optional[Dict]:
        """
        Update price and check trailing stop logic
        Called from WebSocket on every price update

        Returns:
            Dict with action if stop needs update, None otherwise
        """
        # DEBUG: Log entry point
        logger.debug(f"[TS] update_price called: {symbol} @ {price}")

        if symbol not in self.trailing_stops:
            logger.debug(f"[TS] Symbol {symbol} NOT in trailing_stops dict (available: {list(self.trailing_stops.keys())[:5]}...)")
            return None

        async with self.lock:
            ts = self.trailing_stops[symbol]
            old_price = ts.current_price
            ts.current_price = Decimal(str(price))

            # Update highest/lowest
            if ts.side == 'long':
                if ts.current_price > ts.highest_price:
                    old_highest = ts.highest_price
                    ts.highest_price = ts.current_price
                    logger.debug(f"[TS] {symbol} highest_price updated: {old_highest} → {ts.highest_price}")
            else:
                if ts.current_price < ts.lowest_price:
                    old_lowest = ts.lowest_price
                    ts.lowest_price = ts.current_price
                    logger.debug(f"[TS] {symbol} lowest_price updated: {old_lowest} → {ts.lowest_price}")

            # Calculate current profit
            profit_percent = self._calculate_profit_percent(ts)
            if profit_percent > ts.highest_profit_percent:
                ts.highest_profit_percent = profit_percent

            # DEBUG: Log current state
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
            ts.current_stop_price = new_stop_price
            ts.last_stop_update = datetime.now()
            ts.update_count += 1

            # NEW: Check rate limiting and conditional update rules
            should_update, skip_reason = self._should_update_stop_loss(ts, new_stop_price, old_stop)

            if not should_update:
                # Skip update - log reason
                logger.debug(
                    f"⏭️  {ts.symbol}: SL update SKIPPED - {skip_reason} "
                    f"(new_stop={new_stop_price:.4f})"
                )

                # Log skip event (optional - для статистики)
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.TRAILING_STOP_UPDATED,  # Same event type but with skip_reason
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

                # IMPORTANT: Revert changes since we're not updating
                ts.current_stop_price = old_stop  # Restore old price
                ts.last_stop_update = None  # Clear update timestamp
                ts.update_count -= 1  # Revert counter

                return None  # Return None to indicate no action taken

            # Update stop order on exchange
            await self._update_stop_order(ts)

            improvement = abs((new_stop_price - old_stop) / old_stop * 100)
            logger.info(
                f"📈 {ts.symbol}: Trailing stop updated from {old_stop:.4f} to {new_stop_price:.4f} "
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
            if self.exchange.id.lower() != 'binance':
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
                order_type = order.get('type', '').upper()
                order_side = order.get('side', '').lower()
                reduce_only = order.get('reduceOnly', False)

                if (order_type == 'STOP_MARKET' and
                    order_side == expected_side and
                    reduce_only):
                    protection_sl_orders.append(order)

            # Cancel found Protection SL orders
            if protection_sl_orders:
                for order in protection_sl_orders:
                    order_id = order['id']
                    stop_price = order.get('stopPrice', 'unknown')

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
            elapsed_seconds = (datetime.now() - ts.last_sl_update_time).total_seconds()
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

    async def _update_stop_order(self, ts: TrailingStopInstance) -> bool:
        """
        Update stop order using atomic method when available

        NEW IMPLEMENTATION:
        - Bybit: Uses trading-stop endpoint (ATOMIC - no race condition)
        - Binance: Uses optimized cancel+create (minimal race window)
        """
        try:
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
