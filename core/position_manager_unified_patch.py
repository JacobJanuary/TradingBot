"""
MINIMAL patch for PositionManager to add UnifiedPriceMonitor support
This is NOT a replacement - just additions to be imported

Usage in position_manager.py:

1. Add imports at the top:
    from core.position_manager_unified_patch import init_unified_protection, handle_unified_price_update

2. In __init__ after self.trailing_managers initialization:
    # UNIFIED PROTECTION (if enabled)
    self.unified_protection = init_unified_protection(self)

3. In _on_position_update after position.current_price update (line ~1803):
    # UNIFIED PRICE UPDATE (if enabled)
    if self.unified_protection:
        await handle_unified_price_update(self.unified_protection, symbol, position.current_price)

That's it! Everything else remains unchanged.
"""

import os
import asyncio
import logging
from typing import Optional, Dict
from decimal import Decimal

logger = logging.getLogger(__name__)


def init_unified_protection(position_manager) -> Optional[Dict]:
    """
    Initialize unified protection if enabled
    Returns dict with components or None
    """

    # Read feature flag dynamically (not at import time!)
    use_unified = os.getenv('USE_UNIFIED_PROTECTION', 'false').lower() == 'true'

    if not use_unified:
        logger.info("Unified protection disabled (USE_UNIFIED_PROTECTION=false)")
        return None

    try:
        logger.info("Initializing unified protection system...")

        # Import components
        from websocket.unified_price_monitor import UnifiedPriceMonitor
        from core.protection_adapters import TrailingStopAdapter, AgedPositionAdapter
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2

        # Create unified price monitor
        price_monitor = UnifiedPriceMonitor()

        # Create aged position monitor V2
        aged_monitor = AgedPositionMonitorV2(
            exchange_managers=position_manager.exchanges,
            repository=position_manager.repository,
            position_manager=position_manager
        )

        # Create adapters for each exchange's trailing stop
        ts_adapters = {}
        for exchange_name, ts_manager in position_manager.trailing_managers.items():
            ts_adapters[exchange_name] = TrailingStopAdapter(
                trailing_manager=ts_manager,
                price_monitor=price_monitor
            )

        # Create aged position adapter
        aged_adapter = AgedPositionAdapter(
            aged_monitor=aged_monitor,
            price_monitor=price_monitor
        )

        # Price monitor will be started when event loop is ready
        # (from async context, e.g. in start_periodic_sync)

        logger.info("✅ Unified protection initialized successfully")

        return {
            'price_monitor': price_monitor,
            'ts_adapters': ts_adapters,
            'aged_adapter': aged_adapter,
            'aged_monitor': aged_monitor
        }

    except Exception as e:
        logger.error(f"Failed to initialize unified protection: {e}")
        logger.info("Continuing without unified protection")
        return None


async def handle_unified_price_update(unified_protection: Dict, symbol: str, price: float):
    """
    Handle price update through unified system
    This is called from _on_position_update
    """

    if not unified_protection:
        return

    try:
        price_monitor = unified_protection['price_monitor']

        # Convert to Decimal
        price_decimal = Decimal(str(price))

        # Update unified price monitor
        await price_monitor.update_price(symbol, price_decimal)

    except Exception as e:
        # Silent fail - don't break existing flow
        logger.debug(f"Unified price update error for {symbol}: {e}")


async def recover_aged_positions_state(unified_protection: Dict) -> int:
    """
    Recover aged positions state from database on startup
    CRITICAL: This MUST be called after position_manager.load_positions_from_db()

    Returns number of recovered aged positions
    """

    if not unified_protection:
        return 0

    try:
        aged_monitor = unified_protection.get('aged_monitor')
        if not aged_monitor:
            return 0

        # Recover aged positions from database
        recovered_count = await aged_monitor.recover_state()

        if recovered_count > 0:
            logger.info(f"✅ Recovered {recovered_count} aged position(s) from database")
        else:
            logger.info("No aged positions to recover from database")

        return recovered_count

    except Exception as e:
        logger.error(f"Failed to recover aged positions state: {e}")
        return 0


async def start_periodic_aged_scan(unified_protection: Dict, interval_minutes: int = 5):
    """
    Start background task for periodic aged position scanning
    Provides defense in depth - catches positions missed by instant detection

    Args:
        unified_protection: Unified protection components dict
        interval_minutes: Scan interval in minutes (default: 5)
    """

    if not unified_protection:
        return

    aged_monitor = unified_protection.get('aged_monitor')
    if not aged_monitor:
        return

    logger.info(f"🔍 Starting periodic aged scan task (interval: {interval_minutes} minutes)")

    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)
            await aged_monitor.periodic_full_scan()

        except asyncio.CancelledError:
            logger.info("Periodic aged scan task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic aged scan: {e}")
            # Continue running despite errors
            await asyncio.sleep(60)  # Wait 1 minute before retry


async def check_and_register_aged_positions(position_manager, unified_protection: Dict):
    """
    Check all positions for aged status and register them
    This should be called periodically (e.g., every 30-60 minutes)

    DEPRECATED: Use start_periodic_aged_scan() instead for automatic background scanning
    """

    if not unified_protection:
        return

    try:
        aged_adapter = unified_protection['aged_adapter']
        aged_monitor = unified_protection['aged_monitor']

        # Check all positions
        for symbol, position in position_manager.positions.items():
            # Check if aged
            if await aged_monitor.check_position_age(position):
                # ✅ FIX #4: Only add to monitor if NOT already tracked
                if not aged_monitor.is_position_tracked(symbol):
                    await aged_monitor.add_aged_position(position)
                    logger.info(f"Position {symbol} added to aged monitor")

                # ALWAYS call adapter (handles duplicates via Fix #1)
                await aged_adapter.add_aged_position(position)
                logger.debug(f"Position {symbol} registered as aged")

    except Exception as e:
        logger.error(f"Failed to check aged positions: {e}")


def get_unified_stats(unified_protection: Dict) -> Dict:
    """Get statistics from unified protection system"""

    if not unified_protection:
        return {'enabled': False}

    try:
        stats = {
            'enabled': True,
            'price_monitor': unified_protection['price_monitor'].get_stats(),
            'aged_monitor': unified_protection['aged_monitor'].get_stats()
        }
        return stats

    except Exception as e:
        logger.error(f"Failed to get unified stats: {e}")
        return {'enabled': True, 'error': str(e)}