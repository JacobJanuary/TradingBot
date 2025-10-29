#!/usr/bin/env python3
"""
FORENSIC TEST: Aged Position Cleanup Bug Investigation

BUG:
- Closed positions remain in aged_monitor.aged_targets
- WebSocket health monitor tries to resubscribe them
- Gets ERROR "Position not found"

ROOT CAUSE:
- position_manager.close_position() does NOT call aged_adapter.remove_aged_position()
- Only calls trailing_manager.on_position_closed()
- Aged positions not cleaned up on closure

VERIFICATION:
1. Check if aged_targets contains closed positions
2. Check if monitoring_positions contains closed positions
3. Verify position_manager.positions does NOT contain them
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def diagnose_aged_cleanup_bug():
    """
    Diagnose the aged position cleanup bug
    """
    print("=" * 100)
    print("FORENSIC INVESTIGATION: Aged Position Cleanup Bug")
    print("=" * 100)
    print()

    # Import after path setup
    from core.position_manager import PositionManager
    from config.settings import Config

    config = Config()

    # Create position manager
    position_manager = PositionManager(config=config)

    try:
        # Initialize
        await position_manager.initialize()

        print("─" * 100)
        print("STEP 1: Check position_manager.positions (active positions)")
        print("─" * 100)

        active_symbols = list(position_manager.positions.keys())
        print(f"Active positions in memory: {len(active_symbols)}")
        for symbol in sorted(active_symbols):
            print(f"  - {symbol}")
        print()

        # Check unified protection
        if not position_manager.unified_protection:
            print("❌ Unified protection not enabled (USE_UNIFIED_PROTECTION=false)")
            print("   Cannot test aged_adapter")
            return

        print("✅ Unified protection enabled")
        print()

        print("─" * 100)
        print("STEP 2: Check aged_monitor.aged_targets (aged positions being monitored)")
        print("─" * 100)

        aged_monitor = position_manager.unified_protection.get('aged_monitor')
        if aged_monitor:
            aged_symbols = list(aged_monitor.aged_targets.keys())
            print(f"Aged targets in memory: {len(aged_symbols)}")
            for symbol in sorted(aged_symbols):
                print(f"  - {symbol}")
            print()
        else:
            print("⚠️ aged_monitor not found")
            aged_symbols = []

        print("─" * 100)
        print("STEP 3: Check aged_adapter.monitoring_positions (subscribed to price updates)")
        print("─" * 100)

        aged_adapter = position_manager.unified_protection.get('aged_adapter')
        if aged_adapter:
            monitored_symbols = list(aged_adapter.monitoring_positions.keys())
            print(f"Monitoring positions: {len(monitored_symbols)}")
            for symbol in sorted(monitored_symbols):
                print(f"  - {symbol}")
            print()
        else:
            print("⚠️ aged_adapter not found")
            monitored_symbols = []

        print("=" * 100)
        print("CRITICAL ANALYSIS: Find STALE aged positions (closed but still tracked)")
        print("=" * 100)

        # Find positions that are in aged_targets BUT NOT in active positions
        stale_in_aged_targets = set(aged_symbols) - set(active_symbols)

        # Find positions that are in monitoring BUT NOT in active positions
        stale_in_monitoring = set(monitored_symbols) - set(active_symbols)

        if stale_in_aged_targets:
            print(f"🚨 BUG CONFIRMED! Found {len(stale_in_aged_targets)} positions in aged_targets BUT NOT in active positions:")
            for symbol in sorted(stale_in_aged_targets):
                print(f"  ❌ {symbol} - STALE (should have been removed on close)")
            print()
        else:
            print("✅ No stale positions in aged_targets")
            print()

        if stale_in_monitoring:
            print(f"🚨 BUG CONFIRMED! Found {len(stale_in_monitoring)} positions in monitoring_positions BUT NOT in active positions:")
            for symbol in sorted(stale_in_monitoring):
                print(f"  ❌ {symbol} - STALE (should have been removed on close)")
            print()
        else:
            print("✅ No stale positions in monitoring_positions")
            print()

        print("=" * 100)
        print("ROOT CAUSE VERIFICATION")
        print("=" * 100)

        if stale_in_aged_targets or stale_in_monitoring:
            print("🔍 ROOT CAUSE IDENTIFIED:")
            print()
            print("In position_manager.py:2414-2417, close_position() method:")
            print()
            print("  ✅ CALLS:   trailing_manager.on_position_closed()")
            print("  ❌ MISSING: aged_adapter.remove_aged_position()")
            print()
            print("This causes aged positions to remain in aged_targets after closure!")
            print()
            print("CONSEQUENCE:")
            print("  1. Position closed → removed from position_manager.positions")
            print("  2. Position NOT removed from aged_monitor.aged_targets")
            print("  3. WebSocket health monitor sees stale entry")
            print("  4. Tries to resubscribe stale position")
            print("  5. Cannot find in position_manager.positions")
            print("  6. ERROR: 'Position X not found'")
            print()
        else:
            print("✅ No evidence of bug found in current state")
            print("   (All aged positions match active positions)")
            print()

        print("=" * 100)
        print("SPECIFIC CASE: OMUSDT and 1000TAGUSDT")
        print("=" * 100)

        for problem_symbol in ['OMUSDT', '1000TAGUSDT']:
            print(f"\n{problem_symbol}:")
            print(f"  In active positions:      {problem_symbol in active_symbols}")
            print(f"  In aged_targets:          {problem_symbol in aged_symbols}")
            print(f"  In monitoring_positions:  {problem_symbol in monitored_symbols}")

            if problem_symbol in aged_symbols and problem_symbol not in active_symbols:
                print(f"  🚨 STALE ENTRY CONFIRMED!")
            print()

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise

    finally:
        await position_manager.close()


if __name__ == '__main__':
    asyncio.run(diagnose_aged_cleanup_bug())
