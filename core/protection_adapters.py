"""
Minimal adapters for protection modules integration
NO changes to original modules - just adapters
"""

import asyncio
import logging
from typing import Optional
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


class AgedPositionAdapter:
    """
    Adapter for Aged Position monitoring through unified system
    Wraps the FUTURE AgedPositionMonitor
    """

    def __init__(self, aged_monitor, price_monitor):
        self.aged_monitor = aged_monitor  # Will be AgedPositionMonitor instance
        self.price_monitor = price_monitor
        self.monitoring_positions = {}

    async def add_aged_position(self, position):
        """Add position to aged monitoring with subscription verification"""

        symbol = position.symbol

        # ✅ FIX #1: Duplicate Subscription Protection
        # Prevent multiple subscriptions for same symbol
        if symbol in self.monitoring_positions:
            logger.debug(f"⏭️ Skipping {symbol} - already in aged monitoring")
            return

        # Check if qualifies as aged
        age_hours = self._get_position_age_hours(position)
        if age_hours < 3:
            return  # Not aged yet

        # Check if trailing stop is active (skip if yes)
        if hasattr(position, 'trailing_activated') and position.trailing_activated:
            logger.debug(f"Skipping {symbol} - trailing stop active")
            return

        # Subscribe to price updates
        await self.price_monitor.subscribe(
            symbol=symbol,
            callback=self._on_unified_price,
            module='aged_position',
            priority=40  # Lower priority than TrailingStop
        )

        # ✅ PHASE 2: Verify Subscription with Timeout
        verified = await self._verify_subscription_active(symbol, timeout=30)

        if not verified:
            logger.error(
                f"❌ CRITICAL: Subscription verification FAILED for {symbol}! "
                f"No price update received within 30s"
            )
            # Cleanup failed subscription
            await self.price_monitor.unsubscribe(symbol, 'aged_position')
            return

        self.monitoring_positions[symbol] = position
        logger.info(
            f"✅ Aged position {symbol} registered and verified (age={age_hours:.1f}h)"
        )

    async def _on_unified_price(self, symbol: str, price: Decimal):
        """
        Callback from UnifiedPriceMonitor for aged positions
        """
        if symbol not in self.monitoring_positions:
            return

        position = self.monitoring_positions[symbol]

        # Skip if trailing stop became active
        if hasattr(position, 'trailing_activated') and position.trailing_activated:
            await self.remove_aged_position(symbol)
            return

        # Forward to aged monitor when implemented
        if self.aged_monitor:
            await self.aged_monitor.check_price_target(symbol, price)

    async def remove_aged_position(self, symbol: str):
        """Remove position from aged monitoring"""

        if symbol in self.monitoring_positions:
            await self.price_monitor.unsubscribe(symbol, 'aged_position')
            del self.monitoring_positions[symbol]
            logger.debug(f"Aged position {symbol} unregistered")

        # ✅ FIX: Also remove from aged_monitor.aged_targets
        if self.aged_monitor and symbol in self.aged_monitor.aged_targets:
            del self.aged_monitor.aged_targets[symbol]

    async def _verify_subscription_active(self, symbol: str, timeout: int = 30) -> bool:
        """
        ✅ PHASE 2: Verify subscription is receiving data

        Waits for at least one price update within timeout period.

        Args:
            symbol: Symbol to verify
            timeout: Max seconds to wait (default: 30)

        Returns:
            True if subscription verified, False otherwise
        """
        import time

        # Record current last update time
        start_time = time.time()
        initial_update_time = self.price_monitor.last_update_time.get(symbol, 0)

        logger.debug(
            f"🔍 Verifying subscription for {symbol} (timeout: {timeout}s)..."
        )

        # Wait for update
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(1)
            elapsed = time.time() - start_time

            # Check if we received an update
            current_update_time = self.price_monitor.last_update_time.get(symbol, 0)
            if current_update_time > initial_update_time:
                logger.info(
                    f"✅ Subscription verified for {symbol} "
                    f"(received update after {elapsed:.1f}s)"
                )
                return True

        # Timeout - no update received
        logger.error(
            f"❌ Subscription verification timeout for {symbol} "
            f"(no update after {timeout}s)"
        )
        return False

    def _get_position_age_hours(self, position) -> float:
        """Calculate position age in hours"""
        from datetime import datetime, timezone

        if not hasattr(position, 'opened_at'):
            return 0

        now = datetime.now(timezone.utc)
        opened_at = position.opened_at

        # Handle timezone
        if not hasattr(opened_at, 'tzinfo') or opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        age = now - opened_at
        return age.total_seconds() / 3600