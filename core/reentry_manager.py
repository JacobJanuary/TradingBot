"""
Reentry Manager - Trailing REENTRY Strategy

Monitors closed positions for re-entry opportunities within 24h window.

Strategy:
- After trailing stop closes a position
- Wait for cooldown (REENTRY_COOLDOWN_SEC, default 300s)
- If price drops by REENTRY_DROP_PERCENT (default 5%) from exit price
- AND delta shows renewed momentum (large_buy > large_sell)
- Re-enter position up to max re-entries

Date: 2026-01-02
"""

import asyncio
import logging
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


@dataclass
class ReentrySignal:
    """Tracks a signal for potential re-entry"""
    signal_id: int

    symbol: str
    exchange: str
    side: str  # 'long' or 'short'
    
    # Original entry info
    original_entry_price: Decimal
    original_entry_time: datetime
    
    # Last exit info
    last_exit_price: Decimal
    last_exit_time: datetime
    last_exit_reason: str  # 'trailing_stop', 'delta_filter', etc.
    db_id: Optional[int] = None  # Row ID in monitoring.reentry_signals
    
    # Tracking
    reentry_count: int = 0
    max_reentries: int = 5
    
    # Price tracking after exit
    max_price_after_exit: Optional[Decimal] = None
    min_price_after_exit: Optional[Decimal] = None
    
    # Config (loaded from env)
    cooldown_sec: int = 300
    drop_percent: Decimal = Decimal('5.0')
    
    # Signal lifetime
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24))
    
    # Current price tracking (updated by update_price)
    current_price: Optional[Decimal] = None
    
    # Status
    status: str = 'active'  # active, reentered, expired, max_reached
    
    def is_expired(self) -> bool:
        """Check if signal has expired (24h from original entry)"""
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_in_cooldown(self) -> bool:
        """Check if still in cooldown period after exit"""
        cooldown_end = self.last_exit_time + timedelta(seconds=self.cooldown_sec)
        return datetime.now(timezone.utc) < cooldown_end
    
    def can_reenter(self) -> bool:
        """Check if re-entry is allowed"""
        return (
            self.status == 'active' and
            not self.is_expired() and
            not self.is_in_cooldown() and
            self.reentry_count < self.max_reentries
        )
    
    def get_reentry_trigger_price(self) -> Decimal:
        """Calculate price that triggers re-entry
        
        Uses dynamic max/min tracking after exit:
        - LONG: triggers when price drops X% from max_price_after_exit
        - SHORT: triggers when price rises X% from min_price_after_exit
        
        Fallback to last_exit_price if max/min not yet tracked.
        """
        drop_mult = 1 - (self.drop_percent / 100)
        
        if self.side == 'long':
            # For long: re-enter when price drops X% from max since exit
            baseline = self.max_price_after_exit or self.last_exit_price
            return baseline * drop_mult
        else:
            # For short: re-enter when price rises X% from min since exit
            baseline = self.min_price_after_exit or self.last_exit_price
            rise_mult = 1 + (self.drop_percent / 100)
            return baseline * rise_mult


class ReentryManager:
    """
    Manages re-entry signals after trailing stop exits
    
    Integration points:
    - trailing_stop.py: Register exit when TS triggers
    - position_manager.py: Open new position on re-entry
    - binance_aggtrades_stream.py: Check delta for confirmation
    """
    
    def __init__(self, 
                 position_manager,
                 aggtrades_stream=None,
                 mark_price_stream=None,  # NEW: For subscribing reentry signals to mark price
                 cooldown_sec: int = 300,
                 drop_percent: float = 5.0,
                 max_reentries: int = 5,
                 # Instant Reentry params
                 instant_reentry_enabled: bool = True,
                 instant_reentry_delta_mult: float = 1.5,
                 instant_reentry_max_per_hour: int = 2,
                 instant_reentry_min_profit_pct: float = 5.0,
                 repository=None):
        """
        Initialize ReentryManager
        
        Args:
            position_manager: PositionManager instance
            aggtrades_stream: BinanceAggTradesStream for delta confirmation
            mark_price_stream: BinanceHybridStream for subscribing to mark prices
            cooldown_sec: Seconds to wait after exit before checking (default: 300)
            drop_percent: Price drop % to trigger re-entry (default: 5.0)
            max_reentries: Max re-entries per signal (default: 5)
        """
        self.position_manager = position_manager
        self.aggtrades_stream = aggtrades_stream
        self.mark_price_stream = mark_price_stream  # NEW
        self.repository = repository
        
        # Config
        self.cooldown_sec = cooldown_sec
        self.drop_percent = Decimal(str(drop_percent))
        self.max_reentries = max_reentries
        
        # Active reentry signals
        self.signals: Dict[str, ReentrySignal] = {}  # symbol -> ReentrySignal
        
        # Symbols being monitored for price
        self.monitoring_symbols: Set[str] = set()
        
        # Task for monitoring
        self.monitor_task = None
        self.running = False
        
        # Instant Reentry config
        self.instant_reentry_enabled = instant_reentry_enabled
        self.instant_reentry_delta_mult = Decimal(str(instant_reentry_delta_mult))
        self.instant_reentry_max_per_hour = instant_reentry_max_per_hour
        self.instant_reentry_min_profit_pct = Decimal(str(instant_reentry_min_profit_pct))
        
        # Instant reentry tracking (per symbol)
        self.instant_reentry_counts: Dict[str, list] = {}  # symbol -> [timestamps]
        
        # Concurrency Lock (Per Symbol)
        # Prevents race conditions where multiple updates trigger parallel reentries before status is saved
        self._processing_signals: Set[str] = set()
        
        # Stats
        self.stats = {
            'signals_registered': 0,
            'reentries_triggered': 0,
            'reentries_successful': 0,
            'signals_expired': 0,
            'signals_max_reached': 0,
            'instant_reentries': 0
        }
        
        logger.info(
            f"ReentryManager initialized: "
            f"cooldown={cooldown_sec}s, drop={drop_percent}%, max={max_reentries}, "
            f"instant_reentry={'ON' if instant_reentry_enabled else 'OFF'}"
        )
    
    async def start(self):
        """Start monitoring loop"""
        if self.running:
            return
        
        self.running = True
        
        # Load active signals from DB
        await self._load_active_signals()
        
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("🔄 ReentryManager started")

    async def _load_active_signals(self):
        """Load active signals from database"""
        if not self.repository:
            return
            
        try:
            query = """
                SELECT id, signal_id, symbol, exchange, side,
                       original_entry_price, original_entry_time,
                       last_exit_price, last_exit_time, last_exit_reason,
                       reentry_count, max_reentries,
                       cooldown_sec, drop_percent, expires_at, status,
                       max_price_after_exit, min_price_after_exit
                FROM monitoring.reentry_signals
                WHERE status = 'active'
            """
            async with self.repository.pool.acquire() as conn:
                rows = await conn.fetch(query)
            
            for row in rows:
                # Parse max/min prices (may be NULL)
                max_price = Decimal(str(row['max_price_after_exit'])) if row['max_price_after_exit'] else None
                min_price = Decimal(str(row['min_price_after_exit'])) if row['min_price_after_exit'] else None
                
                signal = ReentrySignal(
                    signal_id=row['signal_id'],
                    db_id=row['id'],
                    symbol=row['symbol'],
                    exchange=row['exchange'],
                    side=row['side'],
                    original_entry_price=Decimal(str(row['original_entry_price'])),
                    original_entry_time=row['original_entry_time'],
                    last_exit_price=Decimal(str(row['last_exit_price'])),
                    last_exit_time=row['last_exit_time'],
                    last_exit_reason=row['last_exit_reason'],
                    reentry_count=row['reentry_count'],
                    max_reentries=row['max_reentries'],
                    cooldown_sec=row['cooldown_sec'],
                    drop_percent=Decimal(str(row['drop_percent'])),
                    expires_at=row['expires_at'],
                    status=row['status'],
                    max_price_after_exit=max_price,
                    min_price_after_exit=min_price,
                )
                self.signals[signal.symbol] = signal
                self.monitoring_symbols.add(signal.symbol)
                
                # Resubscribe to stream
                if self.aggtrades_stream:
                    await self.aggtrades_stream.subscribe(signal.symbol)
                
                # CRITICAL FIX 2026-01-03: Subscribe to Mark Price for price updates
                if self.mark_price_stream:
                    await self.mark_price_stream.subscribe_symbol(signal.symbol)
            
            if rows:
                logger.info(f"📥 Loaded {len(rows)} active reentry signals from DB")
                if self.mark_price_stream:
                    logger.info(f"🔌 Subscribed {len(rows)} signals to Mark Price")
                
        except Exception as e:
            logger.error(f"Failed to load active signals: {e}")

    async def _save_signal_state(self, signal: ReentrySignal):
        """Save or update signal state in DB"""
        if not self.repository:
            return
            
        try:
            if signal.db_id:
                # Update existing
                # Update existing
                query = """
                    UPDATE monitoring.reentry_signals
                    SET last_exit_price = $1,
                        last_exit_time = $2,
                        last_exit_reason = $3,
                        reentry_count = $4,
                        max_price_after_exit = $5,
                        min_price_after_exit = $6,
                        status = $7,
                        updated_at = NOW()
                    WHERE id = $8
                """
                async with self.repository.pool.acquire() as conn:
                    await conn.execute(query,
                        float(signal.last_exit_price),
                        signal.last_exit_time,
                        signal.last_exit_reason,
                        signal.reentry_count,
                        float(signal.max_price_after_exit) if signal.max_price_after_exit else None,
                        float(signal.min_price_after_exit) if signal.min_price_after_exit else None,
                        signal.status,
                        signal.db_id
                    )
            else:
                # Insert new
                # Insert new
                query = """
                    INSERT INTO monitoring.reentry_signals (
                        signal_id, symbol, exchange, side,
                        original_entry_price, original_entry_time,
                        last_exit_price, last_exit_time, last_exit_reason,
                        reentry_count, max_reentries,
                        cooldown_sec, drop_percent, expires_at, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    RETURNING id
                """
                async with self.repository.pool.acquire() as conn:
                    row = await conn.fetchrow(query,
                        signal.signal_id,
                        signal.symbol,
                        signal.exchange,
                        signal.side,
                        float(signal.original_entry_price),
                        signal.original_entry_time,
                        float(signal.last_exit_price),
                        signal.last_exit_time,
                        signal.last_exit_reason,
                        signal.reentry_count,
                        signal.max_reentries,
                        signal.cooldown_sec,
                        float(signal.drop_percent),
                        signal.expires_at,
                        signal.status
                    )
                if row:
                    signal.db_id = row['id']
                    
        except Exception as e:
            logger.error(f"Failed to save signal state for {signal.symbol}: {e}")
    
    async def stop(self):
        """Stop monitoring"""
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️ ReentryManager stopped")
    
    async def register_exit(self,
                           signal_id: int,
                           symbol: str,
                           exchange: str,
                           side: str,
                           original_entry_price: Decimal,
                           original_entry_time: datetime,
                           exit_price: Decimal,
                           exit_reason: str):
        """
        Register a position exit for potential re-entry
        
        Called by:
        - trailing_stop.py after TS triggers
        - position_manager.py after any close
        
        Args:
            signal_id: Original signal ID
            symbol: Trading symbol
            exchange: Exchange name
            side: Position side ('long' or 'short')
            original_entry_price: First entry price
            original_entry_time: When signal was first entered
            exit_price: Price at exit
            exit_reason: Why position was closed
        """
        # ===== INSTANT REENTRY CHECK =====
        # If delta is strong during SL exit, re-enter immediately without cooldown
        if self.instant_reentry_enabled and exit_reason == 'trailing_stop':
            should_instant, reason = await self._check_instant_reentry(
                symbol, side, original_entry_price, exit_price
            )
            if should_instant:
                logger.info(f"⚡ {symbol}: INSTANT REENTRY triggered - {reason}")
                await self._trigger_instant_reentry(
                    signal_id=signal_id,
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    entry_price=exit_price  # Re-enter at current price
                )
                return  # Don't register normal reentry signal
        
        # ===== NORMAL REENTRY REGISTRATION =====
        # Check if we already have a signal for this symbol
        existing = self.signals.get(symbol)
        
        if existing:
            # Update existing signal with new exit info
            existing.last_exit_price = exit_price
            existing.last_exit_time = datetime.now(timezone.utc)
            existing.last_exit_reason = exit_reason
            existing.reentry_count += 1
            existing.max_price_after_exit = None  # Reset tracking
            existing.min_price_after_exit = None
            
            logger.info(
                f"🔄 {symbol}: Updated reentry signal (count={existing.reentry_count})"
            )
            
            # Check if max reached
            if existing.reentry_count >= existing.max_reentries:
                existing.status = 'max_reached'
                self.stats['signals_max_reached'] += 1
                logger.info(f"🛑 {symbol}: Max reentries reached ({existing.max_reentries})")
            elif existing.status == 'reentered':
                # Don't reactivate if this exit is from our own reentry position
                # This prevents: reentry->position->exit->reactivate->reentry loop
                logger.info(f"⚠️ {symbol}: Signal was reentered, keeping expired (prevents loop)")
                existing.status = 'expired'
            else:
                existing.status = 'active'
                logger.info(f"🔄 {symbol}: Reactivated reentry signal")
            
            # Save state
            await self._save_signal_state(existing)
        else:
            # Create new signal
            signal = ReentrySignal(
                signal_id=signal_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                original_entry_price=original_entry_price,
                original_entry_time=original_entry_time,
                last_exit_price=exit_price,
                last_exit_time=datetime.now(timezone.utc),
                last_exit_reason=exit_reason,
                cooldown_sec=self.cooldown_sec,
                drop_percent=self.drop_percent,
                max_reentries=self.max_reentries,
                expires_at=original_entry_time + timedelta(hours=24)
            )
            
            self.signals[symbol] = signal
            self.monitoring_symbols.add(symbol)
            self.stats['signals_registered'] += 1
            
            logger.info(
                f"📝 {symbol}: Registered reentry signal "
                f"(exit_price={exit_price}, expires={signal.expires_at})"
            )
            
            # Save state (creates new record)
            await self._save_signal_state(signal)
            
            # Subscribe to aggTrades for this symbol
            if self.aggtrades_stream:
                await self.aggtrades_stream.subscribe(symbol)
            
            # CRITICAL FIX 2026-01-03: Subscribe to Mark Price for price updates
            # Without this, reentry signals show 0% price change
            if self.mark_price_stream:
                await self.mark_price_stream.subscribe_symbol(symbol)
                logger.info(f"🔌 {symbol}: Subscribed to Mark Price for reentry monitoring")
    
    async def update_price(self, symbol: str, price: Decimal):
        """
        Update price for monitored symbol
        
        Called by mark price stream or ticker updates.
        Checks if re-entry should trigger.
        
        Args:
            symbol: Trading symbol
            price: Current price
        """
        signal = self.signals.get(symbol)
        
        # DEBUG: Log every call to trace the issue
        if self.signals:  # Only log if we have signals
            monitored = list(self.signals.keys())[:3]
            if symbol in self.signals:
                logger.debug(f"📈 [REENTRY] update_price called: {symbol}={price} (FOUND in signals)")
            # For performance, only log misses occasionally
        
        if not signal or signal.status != 'active':
            return
        
        # Update price tracking
        signal.current_price = price  # Always store latest price for reporting
        max_changed = False
        
        if signal.max_price_after_exit is None:
            # Initialize from exit price, then update with current if higher/lower
            signal.max_price_after_exit = max(signal.last_exit_price, price)
            signal.min_price_after_exit = min(signal.last_exit_price, price)
            max_changed = True
        else:
            old_max = signal.max_price_after_exit
            old_min = signal.min_price_after_exit
            signal.max_price_after_exit = max(signal.max_price_after_exit, price)
            signal.min_price_after_exit = min(signal.min_price_after_exit, price)
            # Track if max/min actually changed (for LONG we care about max, for SHORT about min)
            if signal.side == 'long' and signal.max_price_after_exit > old_max:
                max_changed = True
            elif signal.side == 'short' and signal.min_price_after_exit < old_min:
                max_changed = True
        
        # REAL-TIME PERSISTENCE: Save immediately when max/min changes
        # This ensures we don't lose tracking data on bot restart
        if max_changed and signal.db_id:
            asyncio.create_task(self._save_signal_state(signal))
        
        # Check if we should re-enter
        if signal.can_reenter():
            trigger_price = signal.get_reentry_trigger_price()
            
            should_trigger = False
            if signal.side == 'long' and price <= trigger_price:
                should_trigger = True
            elif signal.side == 'short' and price >= trigger_price:
                should_trigger = True
            
            if should_trigger:
                # Check delta confirmation
                if await self._check_delta_confirmation(signal):
                    await self._trigger_reentry(signal, price)
    
    async def _check_delta_confirmation(self, signal: ReentrySignal) -> bool:
        """
        Check if delta confirms re-entry
        
        For LONG: large_buy > large_sell (whales accumulating)
        For SHORT: large_sell > large_buy (whales distributing)
        """
        if not self.aggtrades_stream:
            return True  # No delta stream = allow
        
        large_buys, large_sells = self.aggtrades_stream.get_large_trade_counts(
            signal.symbol, 60
        )
        
        if signal.side == 'long':
            if large_buys > large_sells:
                logger.info(
                    f"✅ {signal.symbol}: Delta confirms reentry "
                    f"(large_buys={large_buys} > large_sells={large_sells})"
                )
                return True
            else:
                logger.debug(
                    f"⏳ {signal.symbol}: Delta not confirming reentry yet "
                    f"(large_buys={large_buys} <= large_sells={large_sells})"
                )
                return False
        else:
            if large_sells > large_buys:
                logger.info(
                    f"✅ {signal.symbol}: Delta confirms reentry "
                    f"(large_sells={large_sells} > large_buys={large_buys})"
                )
                return True
            else:
                logger.debug(
                    f"⏳ {signal.symbol}: Delta not confirming reentry yet "
                    f"(large_sells={large_sells} <= large_buys={large_buys})"
                )
                return False
    
    async def _check_instant_reentry(
        self, 
        symbol: str, 
        side: str,
        entry_price: Decimal,
        exit_price: Decimal
    ) -> tuple[bool, str]:
        """
        Check if instant reentry should trigger (no cooldown)
        
        Conditions:
        1. Delta is strong (> avg * threshold)
        2. Position was profitable
        3. Haven't exceeded max instant reentries per hour
        
        Returns:
            tuple[bool, str]: (should_trigger, reason)
        """
        # Check rate limit
        now = datetime.now(timezone.utc)
        timestamps = self.instant_reentry_counts.get(symbol, [])
        
        # Filter to last hour
        hour_ago = now - timedelta(hours=1)
        recent = [t for t in timestamps if t > hour_ago]
        self.instant_reentry_counts[symbol] = recent
        
        if len(recent) >= self.instant_reentry_max_per_hour:
            return (False, f"rate_limit:{len(recent)}/{self.instant_reentry_max_per_hour}")
        
        # Check profitability
        if side == 'long':
            profit_pct = (exit_price - entry_price) / entry_price * 100
        else:
            profit_pct = (entry_price - exit_price) / entry_price * 100
        
        if profit_pct < self.instant_reentry_min_profit_pct:
            return (False, f"low_profit:{profit_pct:.2f}%")
        
        # Check delta
        if not self.aggtrades_stream:
            return (False, "no_delta_stream")
        
        rolling_delta = self.aggtrades_stream.get_rolling_delta(symbol, 20)
        avg_delta = self.aggtrades_stream.get_avg_delta(symbol, 100)
        threshold = avg_delta * self.instant_reentry_delta_mult
        
        # For LONG: strong buying (delta > threshold)
        if side == 'long' and rolling_delta > threshold:
            return (True, f"strong_buying:delta={float(rolling_delta):.0f}>{float(threshold):.0f}")
        
        # For SHORT: strong selling (delta < -threshold)
        if side == 'short' and rolling_delta < -threshold:
            return (True, f"strong_selling:delta={float(rolling_delta):.0f}<-{float(threshold):.0f}")
        
        return (False, f"weak_delta:{float(rolling_delta):.0f}")
    
    async def _is_position_already_open(self, symbol: str, exchange: str) -> bool:
        """
        Robustly check if position exists using 3 layers:
        1. Normalized Cache
        2. Database
        3. Exchange API
        """
        position_exists = False
        
        # 1. Check Cache with Normalization
        try:
            clean_symbol = symbol.replace('/', '').split(':')[0]
            for pos_symbol in list(self.position_manager.positions.keys()):
                if pos_symbol.replace('/', '').split(':')[0] == clean_symbol:
                    logger.warning(f"⚠️ {symbol}: Found in cache as '{pos_symbol}'")
                    return True
        except Exception as e:
            logger.error(f"Error checking cache for {symbol}: {e}")

        # 2. Check Database
        if hasattr(self, 'repository') and self.repository:
            try:
                db_pos = await self.repository.get_open_position(symbol, exchange)
                if db_pos:
                    logger.warning(f"⚠️ {symbol}: Found in database (id={db_pos.get('id')})")
                    return True
            except Exception as e:
                logger.error(f"Error checking DB for {symbol}: {e}")

        # 3. Check Exchange API
        if hasattr(self.position_manager, 'verify_position_exists'):
            try:
                exists = await self.position_manager.verify_position_exists(symbol, exchange)
                if exists:
                    logger.warning(f"⚠️ {symbol}: Found on EXCHANGE (API verification)")
                    return True
            except Exception as e:
                logger.error(f"Error checking Exchange for {symbol}: {e}")
                
        return False

    async def _trigger_instant_reentry(
        self,
        signal_id: int,
        symbol: str,
        exchange: str,
        side: str,
        entry_price: Decimal
    ):
        """Execute instant re-entry (no cooldown)"""
        
        # FIX v5: Concurrency Lock
        if symbol in self._processing_signals:
            logger.debug(f"🔒 {symbol}: Already processing, skipping concurrent trigger")
            return
            
        self._processing_signals.add(symbol)
        try:
            # CRITICAL FIX 3: Add Robust Check to Instant Reentry too
            if await self._is_position_already_open(symbol, exchange):
                logger.warning(f"⚠️ {symbol}: Position already exists, skipping instant reentry")
                return

            logger.info(
                f"🚀 {symbol}: INSTANT REENTRY executing at {entry_price}"
            )
            
            self.stats['instant_reentries'] += 1
            
            # Track for rate limiting
            now = datetime.now(timezone.utc)
            if symbol not in self.instant_reentry_counts:
                self.instant_reentry_counts[symbol] = []
            self.instant_reentry_counts[symbol].append(now)
            
            try:
                from core.position_manager import PositionRequest
                
                request = PositionRequest(
                    signal_id=signal_id,
                    symbol=symbol,
                    exchange=exchange,
                    side='BUY' if side == 'long' else 'SELL',
                    entry_price=entry_price
                )
                
                result = await self.position_manager.open_position(request)
                
                if result:
                    logger.info(f"✅ {symbol}: Instant reentry position opened!")
                else:
                    logger.error(f"❌ {symbol}: Failed to open instant reentry position")
            
            except Exception as e:
                logger.error(f"❌ {symbol}: Instant reentry failed: {e}")
        finally:
            self._processing_signals.discard(symbol)
    
    async def _trigger_reentry(self, signal: ReentrySignal, current_price: Decimal):
        """Execute re-entry for signal"""
        
        # FIX v5: Concurrency Lock
        if signal.symbol in self._processing_signals:
            logger.debug(f"🔒 {signal.symbol}: Already processing, skipping concurrent trigger")
            return
            
        self._processing_signals.add(signal.symbol)
        try:
            # CRITICAL FIX v2 + v3: Robust position check (Helper method)
            if await self._is_position_already_open(signal.symbol, signal.exchange):
                logger.warning(
                    f"⚠️ {signal.symbol}: Position already exists, marking signal as reentered"
                )
                signal.status = 'reentered'
                signal.reentry_count += 1
                await self._save_signal_state(signal)
                return
        
        logger.info(
            f"🚀 {signal.symbol}: REENTRY TRIGGERED! "
            f"price={current_price}, exit_price={signal.last_exit_price}, "
            f"drop={float((signal.last_exit_price - current_price) / signal.last_exit_price * 100):.2f}%"
        )
        
        # CRITICAL FIX: Mark signal as 'reentered' IMMEDIATELY to prevent duplicate attempts
        # This prevents infinite loop if price stays in trigger zone
        signal.status = 'reentered'
        signal.reentry_count += 1
        
        self.stats['reentries_triggered'] += 1
        
        try:
            # Create position request
            from core.position_manager import PositionRequest
            
            request = PositionRequest(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                exchange=signal.exchange,
                side='BUY' if signal.side == 'long' else 'SELL',
                entry_price=current_price
            )
            
            # Open position through position manager
            result = await self.position_manager.open_position(request)
            
            if result:
                self.stats['reentries_successful'] += 1
                logger.info(f"✅ {signal.symbol}: Reentry position opened successfully")
            else:
                logger.error(f"❌ {signal.symbol}: Failed to open reentry position")
            
            # Save signal state (status already set to 'reentered')
            await self._save_signal_state(signal)
        
        except Exception as e:
            logger.error(f"❌ {signal.symbol}: Reentry failed: {e}")
            # Still save the 'reentered' status to prevent infinite retries
            await self._save_signal_state(signal)
        finally:
            self._processing_signals.discard(signal.symbol)
    
    async def _monitor_loop(self):
        """Background loop to check and cleanup signals"""
        logger.info("🔄 Reentry monitor loop started")
        
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                expired_count = 0
                for symbol, signal in list(self.signals.items()):
                    should_save = False
                    
                    # Check expiration
                    if signal.is_expired() and signal.status == 'active':
                        signal.status = 'expired'
                        expired_count += 1
                        self.stats['signals_expired'] += 1
                        logger.info(f"⏰ {symbol}: Reentry signal expired")
                        should_save = True
                    
                    # NOTE: max_price_after_exit is now saved in real-time in update_price()
                    
                    # Check safe unsubscription (Expired OR Max Reached)
                    if signal.status in ['expired', 'max_reached']:
                        # Only unsubscribe if NO active position
                        is_position_open = symbol in self.position_manager.positions
                        
                        if not is_position_open:
                            if self.aggtrades_stream:
                                await self.aggtrades_stream.unsubscribe(symbol)
                            
                            # Cleanup inactive signals from memory only if they are old enough
                            # (Keep them in DB)
                            time_since_update = datetime.now(timezone.utc) - signal.last_exit_time
                            if time_since_update > timedelta(hours=1):
                                del self.signals[symbol]
                                self.monitoring_symbols.discard(symbol)
                                logger.info(f"🗑️ {symbol}: Removed inactive signal from memory")
                        else:
                            logger.debug(f"⏳ {symbol}: Signal {signal.status}, but position open - keeping subscription")

                    if should_save:
                        await self._save_signal_state(signal)
                
                if expired_count > 0:
                    logger.info(f"📊 Reentry signals: {len(self.signals)} active, {expired_count} expired this cycle")
                
                # Log detailed status report for ALL active signals (every 1 minute)
                active_sigs = [s for s in self.signals.values() if s.status == 'active']
                if active_sigs:
                    logger.info(f"📡 [REENTRY MONITOR] {len(active_sigs)} active signal(s):")
                    
                    for sig in active_sigs:
                        # Calculate price change % from exit price
                        current_price = sig.current_price if hasattr(sig, 'current_price') and sig.current_price else sig.last_exit_price
                        
                        # Dynamic max/min tracking for re-entry trigger
                        if sig.side == 'long':
                            baseline = sig.max_price_after_exit or sig.last_exit_price
                            drop_from_max = ((baseline - current_price) / baseline * 100) if baseline else Decimal('0')
                            drop_str = f"drop={drop_from_max:.1f}%"
                        else:
                            baseline = sig.min_price_after_exit or sig.last_exit_price
                            rise_from_min = ((current_price - baseline) / baseline * 100) if baseline else Decimal('0')
                            drop_str = f"rise={rise_from_min:.1f}%"
                        
                        trigger_price = sig.get_reentry_trigger_price()
                        
                        # Get delta from aggtrades stream (raw USDT value is more meaningful)
                        delta_usdt = Decimal('0')
                        if self.aggtrades_stream:
                            try:
                                # Get rolling delta (buy_volume - sell_volume in USDT over 60s)
                                delta_usdt = self.aggtrades_stream.get_rolling_delta(sig.symbol, window_sec=60)
                            except Exception as e:
                                logger.debug(f"Delta fetch error for {sig.symbol}: {e}")
                        
                        # Format delta as USDT value (K for thousands)
                        if abs(delta_usdt) >= 1000:
                            delta_str = f"{delta_usdt/1000:+.1f}K"
                        else:
                            delta_str = f"{delta_usdt:+.0f}"
                        
                        # Calculate expiration time (HH:MM)
                        expires_at_str = sig.expires_at.strftime('%H:%M') if sig.expires_at else 'N/A'
                        
                        logger.info(
                            f"  → {sig.symbol} ({sig.side.upper()}) | "
                            f"now={current_price:.4f} max={baseline:.4f} {drop_str} | "
                            f"trigger={trigger_price:.4f} | Δ=${delta_str} | "
                            f"until {expires_at_str}"
                        )
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reentry monitor error: {e}")
                await asyncio.sleep(10)
    
    def get_stats(self) -> Dict:
        """Get reentry statistics"""
        active = sum(1 for s in self.signals.values() if s.status == 'active')
        return {
            **self.stats,
            'active_signals': active,
            'total_monitored': len(self.signals)
        }
