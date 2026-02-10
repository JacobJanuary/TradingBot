
import asyncio
import logging
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

# Setup Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("Sim")

# --- MOCK CLASSES ---
@dataclass
class ReentrySignal:
    symbol: str
    status: str = 'active'
    reentry_count: int = 0
    max_reentries: int = 5
    last_exit_time: datetime = datetime.now(timezone.utc)
    # ... other fields ignored for logic test

class ReentryManager:
    def __init__(self):
        self.signals = {'CVXUSDT': ReentrySignal('CVXUSDT')}
        self._processing_signals = set()
        self.instant_reentry_enabled = False # Simplify

    async def _is_position_already_open(self, symbol, exchange):
        # Simulate delay
        await asyncio.sleep(0.1)
        return False

    async def _save_signal_state(self, signal):
        # logging.debug(f"💾 Saving: {signal.status}, Count: {signal.reentry_count}")
        pass

    async def _trigger_reentry(self, signal, price):
        logging.info(f"🚀 TRIGGER START: Status={signal.status}")
        
        # LOCK CHECK
        if signal.symbol in self._processing_signals:
            logging.info("🔒 LOCKED. Skipping.")
            return
        self._processing_signals.add(signal.symbol)
        
        try:
            # 1. Check Pos
            logging.info("🔎 Checking DB...")
            if await self._is_position_already_open(signal.symbol, 'binance'):
                logging.info("⚠️ Pos Exists. Stop.")
                return

            # 2. Set Status
            logging.info(f"✅ Setting Status REENTERED (Was {signal.status})")
            signal.status = 'reentered'
            signal.reentry_count += 1
            await self._save_signal_state(signal)
            
            # 3. Open Position (Simulate Latency)
            logging.info("📤 Opening Position... (Wait 0.3s)")
            await asyncio.sleep(0.3) 
            logging.info("📥 Position Result: Success")
            
        finally:
            self._processing_signals.discard(signal.symbol)
            logging.info("🔓 LOCK RELEASED")

    async def register_exit(self, symbol, reason='trailing_stop'):
        logging.info(f"🚪 EXIT EVENT START: Symbol={symbol}")
        
        # --- THE FIX (Uncomment to test) ---
        # if symbol in self._processing_signals:
        #     logging.warning("Shield activated! Ignoring exit.")
        #     return
        # -----------------------------------
        
        existing = self.signals.get(symbol)
        if existing:
            logging.info(f"   Current Status: {existing.status}")
            
            if existing.status == 'reentered':
                existing.status = 'expired'
                logging.info("   -> Set EXPIRED")
            else:
                existing.status = 'active'
                logging.info("   -> Set ACTIVE")
            
            existing.reentry_count += 1
            await self._save_signal_state(existing)

# --- SCENARIOS ---

async def run_scenario_1_phantom_exit_during_check(manager):
    """
    Scenario 1: 'register_exit' runs WHILE '_trigger_reentry' is checking DB.
    (Before Status Update)
    Current Bug: Trigger sets 'reentered', Exit sets 'active'.
    Who wins?
    """
    logging.info("\n--- SCENARIO 1: Phantom Exit DURING DB Check ---")
    sig = manager.signals['CVXUSDT']
    sig.status = 'active'
    sig.reentry_count = 0
    
    async def trigger():
        await manager._trigger_reentry(sig, Decimal('100'))
        
    async def phantom_exit():
        await asyncio.sleep(0.05) # Run while trigger is sleeping (0.1s)
        await manager.register_exit('CVXUSDT')
        
    await asyncio.gather(trigger(), phantom_exit())
    
    logging.info(f"RESULT: Status={sig.status}, Count={sig.reentry_count}")
    # Expected: 2 (1 from exit, 1 from trigger). Status: reentered (Trigger writes last)

async def run_scenario_2_phantom_exit_during_open(manager):
    """
    Scenario 2: 'register_exit' runs WHILE '_trigger_reentry' is opening position.
    (After Status Update)
    Current Bug: Trigger sets 'reentered'. Exit sees 'reentered' -> sets 'expired'.
    """
    logging.info("\n--- SCENARIO 2: Phantom Exit DURING Open Position ---")
    sig = manager.signals['CVXUSDT']
    sig.status = 'active'
    
    async def trigger():
        await manager._trigger_reentry(sig, Decimal('100'))
        
    async def phantom_exit():
        await asyncio.sleep(0.2) # Run while trigger is opening (0.3s)
        await manager.register_exit('CVXUSDT')
        
    await asyncio.gather(trigger(), phantom_exit())
    
    logging.info(f"RESULT: Status={sig.status}")
    # Expected: expired (Exit overwrites reentered)

if __name__ == "__main__":
    m = ReentryManager()
    asyncio.run(run_scenario_1_phantom_exit_during_check(m))
    asyncio.run(run_scenario_2_phantom_exit_during_open(m))
