"""
MINIMAL patch for PositionManager to add UnifiedPriceMonitor support
This is NOT a replacement - just additions to be imported

NOTE: Aged position management removed 2026-02-12
Timeout logic handled by Smart Timeout v2.0 in signal_lifecycle.py
Only UnifiedPriceMonitor + TrailingStopAdapter remain.

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
        from core.protection_adapters import TrailingStopAdapter

        # Create unified price monitor
        price_monitor = UnifiedPriceMonitor()

        # Create adapters for each exchange's trailing stop
        ts_adapters = {}
        for exchange_name, ts_manager in position_manager.trailing_managers.items():
            ts_adapters[exchange_name] = TrailingStopAdapter(
                trailing_manager=ts_manager,
                price_monitor=price_monitor
            )

        logger.info("✅ Unified protection initialized (trailing stop only, aged removed)")

        return {
            'price_monitor': price_monitor,
            'ts_adapters': ts_adapters,
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


def get_unified_stats(unified_protection: Dict) -> Dict:
    """Get statistics from unified protection system"""

    if not unified_protection:
        return {'enabled': False}

    try:
        stats = {
            'enabled': True,
            'price_monitor': unified_protection['price_monitor'].get_stats(),
        }
        return stats

    except Exception as e:
        logger.error(f"Failed to get unified stats: {e}")
        return {'enabled': True, 'error': str(e)}