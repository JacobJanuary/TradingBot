"""
Minimal adapters for protection modules integration
NO changes to original modules - just adapters

NOTE: AgedPositionAdapter removed 2026-02-12
Timeout logic handled by Smart Timeout v2.0 in signal_lifecycle.py
"""

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class TrailingStopAdapter:
    """
    Adapter to connect TrailingStop to UnifiedPriceMonitor
    WITHOUT changing TrailingStop code
    """

    def __init__(self, trailing_manager, price_monitor):
        self.trailing_manager = trailing_manager
        self.price_monitor = price_monitor
        self.subscribed_symbols = set()

    async def register_position(self, position):
        """Register position for monitoring through unified system"""

        symbol = position.symbol

        if symbol not in self.subscribed_symbols:
            # Subscribe to unified price updates
            await self.price_monitor.subscribe(
                symbol=symbol,
                callback=self._on_unified_price,
                module='trailing_stop',
                priority=10  # High priority for profitable positions
            )
            self.subscribed_symbols.add(symbol)

            logger.debug(f"TrailingStop subscribed to {symbol} via unified monitor")

    async def _on_unified_price(self, symbol: str, price: Decimal):
        """
        Callback from UnifiedPriceMonitor
        Routes to original trailing_manager.update_price()
        """
        # Call original method without any changes
        await self.trailing_manager.update_price(symbol, price)

    async def unregister_position(self, symbol: str):
        """Unregister position from monitoring"""

        if symbol in self.subscribed_symbols:
            await self.price_monitor.unsubscribe(symbol, 'trailing_stop')
            self.subscribed_symbols.remove(symbol)