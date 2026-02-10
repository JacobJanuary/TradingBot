
import asyncio
import logging
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

# Configure Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- MOCKING DEPENDENCIES ---

@dataclass
class ReentrySignal:
    """Tracks a signal for potential re-entry (Simplified Mock)"""
    signal_id: int
    symbol: str
    exchange: str
    side: str
    original_entry_price: Decimal
    original_entry_time: datetime
    last_exit_price: Decimal
    last_exit_time: datetime
    last_exit_reason: str
    db_id: int = 1
    reentry_count: int = 0
    max_reentries: int = 5
    max_price_after_exit: Decimal = None
    min_price_after_exit: Decimal = None
    cooldown_sec: int = 300
    drop_percent: Decimal = Decimal('5.0')
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24))
    current_price: Decimal = None
    status: str = 'active'
    
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_in_cooldown(self) -> bool:
        # Mock: Assume cooldown passed for testing trigger
        return False
    
    def can_reenter(self) -> bool:
        return (
            self.status == 'active' and
            not self.is_expired() and
            # not self.is_in_cooldown() and # Skipped for test
            self.reentry_count < self.max_reentries
        )
    
    def get_reentry_trigger_price(self) -> Decimal:
        return Decimal('100.0') # Always trigger if price < 100

# Copy of ReentryManager class (Skeleton with critical logic)
class ReentryManager:
    def __init__(self, position_manager, repository=None):
        self.position_manager = position_manager
        self.repository = repository
        self.signals = {}
        self._processing_signals = set()
        self.stats = {
            'reentries_triggered': 0, 
            'reentries_successful': 0,
            'instant_reentries': 0
        }
        self.instant_reentry_counts = {}

    async def _save_signal_state(self, signal):
        logger.info(f"💾 [MOCK DB] Saving signal {signal.symbol}: status={signal.status}, count={signal.reentry_count}")
        # Mock DB delay
        await asyncio.sleep(0.01)

    async def _is_position_already_open(self, symbol, exchange):
        # Mock: Returns False (simulating 'position not found' which causes the loop)
        logger.info(f"🔎 [CHECK] Checking position for {symbol} -> False")
        return False

    async def _check_delta_confirmation(self, signal):
        return True

    # --- PASTE THE CRITICAL FUNCTIONS HERE (As they exist on server) ---
    
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
                f"price={current_price}"
            )
            
            # CRITICAL FIX: Mark signal as 'reentered' IMMEDIATELY
            signal.status = 'reentered'
            signal.reentry_count += 1
            
            self.stats['reentries_triggered'] += 1
            
            try:
                # Mock Position Request
                logger.info("📤 Sending Open Position Request...")
                # Simulate API call duration
                await asyncio.sleep(0.2)
                
                # SIMULATE FAILURE (Duplicate Error)
                result = None 
                
                if result:
                    self.stats['reentries_successful'] += 1
                    logger.info(f"✅ {signal.symbol}: Reentry position opened successfully")
                else:
                    logger.error(f"❌ {signal.symbol}: Failed to open reentry position (Mock)")
                
                # Save signal state (status already set to 'reentered')
                await self._save_signal_state(signal)
            
            except Exception as e:
                logger.error(f"❌ {signal.symbol}: Reentry failed: {e}")
                await self._save_signal_state(signal)
        finally:
            self._processing_signals.discard(signal.symbol)

    async def update_price(self, symbol: str, price: Decimal):
        signal = self.signals.get(symbol)
        if not signal: return
        
        logger.info(f"📈 Update Price: {symbol}={price}, Status={signal.status}")
        
        if signal.status != 'active':
            logger.info(f"⏭️ Signal not active ({signal.status}), skipping")
            return

        # Simplified trigger check
        if price < 100: # Trigger condition
             await self._trigger_reentry(signal, price)


    async def register_exit(self, symbol, status_override=None):
        logger.info(f"🚪 Register Exit called for {symbol}")
        existing = self.signals.get(symbol)
        if existing:
            # ORIGINAL LOGIC
            if existing.status == 'reentered':
                 logger.info("⚠️ Signal was reentered, setting EXPIRED")
                 existing.status = 'expired'
            else:
                 logger.info("🔄 Reactivating signal (ACTIVE)")
                 existing.status = 'active'
            await self._save_signal_state(existing)


# --- SIMULATION ---

async def run_simulation():
    print("="*60)
    print("STARTING REENTRY LOOP SIMULATION")
    print("="*60)
    
    # Setup
    pm_mock = AsyncMock()
    # pm_mock.open_position.return_value = None # Fail by default
    
    manager = ReentryManager(pm_mock)
    
    # Create Signal
    sig = ReentrySignal(
        signal_id=303, symbol='CVXUSDT', exchange='binance', side='long',
        original_entry_price=Decimal('110'), original_entry_time=datetime.now(timezone.utc),
        last_exit_price=Decimal('105'), last_exit_time=datetime.now(timezone.utc),
        last_exit_reason='trailing_stop'
    )
    manager.signals['CVXUSDT'] = sig
    
    print(f"Initial Status: {sig.status}")
    
    # Step 1: Trigger Reentry (Should set status to 'reentered')
    print("\n--- TICK 1: Price Drop ---")
    await manager.update_price('CVXUSDT', Decimal('99.0'))
    
    print(f"Status After Tick 1: {sig.status}")
    
    if sig.status != 'reentered':
        print("❌ FAILURE: Status did not change to 'reentered'!")
    else:
        print("✅ SUCCESS: Status changed to 'reentered'")

    # Step 2: Next Tick (Should skip)
    print("\n--- TICK 2: Next Price Update ---")
    await manager.update_price('CVXUSDT', Decimal('98.0'))
    
    # Step 3: Simulate Concurrent Access (Race Condition)
    print("\n--- CONCURRENCY TEST ---")
    # Reset status for test
    sig.status = 'active' 
    print("Resetting status to 'active' for concurrency test")
    
    # Run 5 concurrent updates
    print("Launching 5 concurrent update_price calls...")
    tasks = [manager.update_price('CVXUSDT', Decimal(f'9{i}.0')) for i in range(5)]
    await asyncio.gather(*tasks)
    
    print(f"Status After Concurrency: {sig.status}")
    print(f"Reentries Triggered Stats: {manager.stats['reentries_triggered']}")
    
    if manager.stats['reentries_triggered'] == 1:
        print("✅ SUCCESS: Only 1 reentry triggered (Lock worked)")
    else:
        print(f"❌ FAILURE: {manager.stats['reentries_triggered']} reentries triggered (Lock failed)")

    # Step 4: Interleaved register_exit Test
    print("\n--- INTERLEAVED EXIT TEST ---")
    # Scenario: _trigger_reentry starts -> register_exit happens (e.g. from phantom close) -> _trigger_reentry finishes
    
    # Reset
    sig.status = 'active'
    manager.stats['reentries_triggered'] = 0
    manager._processing_signals.clear()
    
    async def trigger_with_delay():
        await manager.update_price('CVXUSDT', Decimal('95.0'))

    async def interfere_exit():
        await asyncio.sleep(0.1) # Wait for trigger to start
        print("⚠️ Calling register_exit (Phantom Close)...")
        await manager.register_exit('CVXUSDT')

    # Run both
    # NOTE: In real code, _trigger_reentry runs sequentially inside update_price.
    # But register_exit comes from WebSocket task (parallel).
    # So they CAN interleave if _trigger is 'awaiting' something (like DB or API).
    
    print("Running interleaved tasks...")
    await asyncio.gather(trigger_with_delay(), interfere_exit())
    
    print(f"Status After Interleaving: {sig.status}")
    
    if sig.status == 'reentered':
         print("✅ SUCCESS: Status remained 'reentered' (Trigger checked last)")
    elif sig.status == 'expired':
         print("✅ SUCCESS: Status became 'expired' (Correct handshake)")
    else:
         print(f"❌ FAILURE: Status is '{sig.status}' (Loop Condition!)")

if __name__ == "__main__":
    asyncio.run(run_simulation())
