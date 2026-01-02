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
from datetime import datetime, timedelta

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
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))
    
    # Status
    status: str = 'active'  # active, reentered, expired, max_reached
    
    def is_expired(self) -> bool:
        """Check if signal has expired (24h from original entry)"""
        return datetime.utcnow() > self.expires_at
    
    def is_in_cooldown(self) -> bool:
        """Check if still in cooldown period after exit"""
        cooldown_end = self.last_exit_time + timedelta(seconds=self.cooldown_sec)
        return datetime.utcnow() < cooldown_end
    
    def can_reenter(self) -> bool:
        """Check if re-entry is allowed"""
        return (
            self.status == 'active' and
            not self.is_expired() and
            not self.is_in_cooldown() and
            self.reentry_count < self.max_reentries
        )
    
    def get_reentry_trigger_price(self) -> Decimal:
        """Calculate price that triggers re-entry"""
        drop_mult = 1 - (self.drop_percent / 100)
        
        if self.side == 'long':
            # For long: re-enter when price drops X% from exit
            return self.last_exit_price * drop_mult
        else:
            # For short: re-enter when price rises X% from exit
            rise_mult = 1 + (self.drop_percent / 100)
            return self.last_exit_price * rise_mult


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
            cooldown_sec: Seconds to wait after exit before checking (default: 300)
            drop_percent: Price drop % to trigger re-entry (default: 5.0)
            max_reentries: Max re-entries per signal (default: 5)
        """
        self.position_manager = position_manager
        self.aggtrades_stream = aggtrades_stream
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
                       cooldown_sec, drop_percent, expires_at, status
                FROM monitoring.reentry_signals
                WHERE status = 'active'
            """
            async with self.repository.pool.acquire() as conn:
                rows = await conn.fetch(query)
            
            for row in rows:
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
                    status=row['status']
                )
                self.signals[signal.symbol] = signal
                self.monitoring_symbols.add(signal.symbol)
                
                # Resubscribe to stream
                if self.aggtrades_stream:
                    await self.aggtrades_stream.subscribe(signal.symbol)
            
            if rows:
                logger.info(f"📥 Loaded {len(rows)} active reentry signals from DB")
                
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
            existing.last_exit_time = datetime.utcnow()
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
                last_exit_time=datetime.utcnow(),
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
        if not signal or signal.status != 'active':
            return
        
        # Update price tracking
        if signal.max_price_after_exit is None:
            signal.max_price_after_exit = price
            signal.min_price_after_exit = price
        else:
            signal.max_price_after_exit = max(signal.max_price_after_exit, price)
            signal.min_price_after_exit = min(signal.min_price_after_exit, price)
        
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
        now = datetime.utcnow()
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
    
    async def _trigger_instant_reentry(
        self,
        signal_id: int,
        symbol: str,
        exchange: str,
        side: str,
        entry_price: Decimal
    ):
        """Execute instant re-entry (no cooldown)"""
        logger.info(
            f"🚀 {symbol}: INSTANT REENTRY executing at {entry_price}"
        )
        
        self.stats['instant_reentries'] += 1
        
        # Track for rate limiting
        now = datetime.utcnow()
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
    
    async def _trigger_reentry(self, signal: ReentrySignal, current_price: Decimal):
        """Execute re-entry for signal"""
        logger.info(
            f"🚀 {signal.symbol}: REENTRY TRIGGERED! "
            f"price={current_price}, exit_price={signal.last_exit_price}, "
            f"drop={float((signal.last_exit_price - current_price) / signal.last_exit_price * 100):.2f}%"
        )
        
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
                
                # Update status in DB
                await self._save_signal_state(signal)
                
                logger.info(f"✅ {signal.symbol}: Reentry position opened successfully")
            else:
                logger.error(f"❌ {signal.symbol}: Failed to open reentry position")
        
        except Exception as e:
            logger.error(f"❌ {signal.symbol}: Reentry failed: {e}")
    
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
                    
                    # Check safe unsubscription (Expired OR Max Reached)
                    if signal.status in ['expired', 'max_reached']:
                        # Only unsubscribe if NO active position
                        is_position_open = symbol in self.position_manager.positions
                        
                        if not is_position_open:
                            if self.aggtrades_stream:
                                await self.aggtrades_stream.unsubscribe(symbol)
                            
                            # Cleanup inactive signals from memory only if they are old enough
                            # (Keep them in DB)
                            time_since_update = datetime.utcnow() - signal.last_exit_time
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
                
                # Log stats every 5 minutes (every 5th cycle)
                import random
                if random.randint(1, 5) == 1 and self.signals:
                    active_sigs = [s for s in self.signals.values() if s.status == 'active']
                    for sig in active_sigs[:3]:  # Log up to 3
                        time_left = (sig.expires_at - datetime.utcnow()).total_seconds() / 3600
                        cooldown_left = max(0, (sig.last_exit_time + timedelta(seconds=sig.cooldown_sec) - datetime.utcnow()).total_seconds())
                        trigger_price = sig.get_reentry_trigger_price()
                        logger.info(
                            f"📈 {sig.symbol}: awaiting reentry | "
                            f"trigger={trigger_price:.4f} | "
                            f"cooldown={cooldown_left:.0f}s | "
                            f"expires={time_left:.1f}h | "
                            f"count={sig.reentry_count}/{sig.max_reentries}"
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
