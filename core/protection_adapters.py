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

        # ✅ NEW: Track background verification tasks
        self._verification_tasks = {}  # symbol → asyncio.Task

    async def add_aged_position(self, position):
        """
        Add position to aged monitoring with NON-BLOCKING subscription verification

        ✅ CHANGE: Verification moved to background task to prevent blocking periodic_full_scan()
        ✅ CHANGE: Added cleanup logic for failed verifications
        """

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

        # ✅ CHANGE: Add to monitoring IMMEDIATELY (non-blocking)
        self.monitoring_positions[symbol] = position
        logger.info(
            f"✅ Aged position {symbol} registered (age={age_hours:.1f}h) - verifying subscription..."
        )

        # ✅ CHANGE: Start background verification with cleanup
        # Cancel previous verification task if exists
        if symbol in self._verification_tasks:
            self._verification_tasks[symbol].cancel()

        task = asyncio.create_task(self._background_verify_with_cleanup(symbol, position))
        self._verification_tasks[symbol] = task

    async def _background_verify_with_cleanup(self, symbol: str, position):
        """
        ✅ NEW METHOD: Background subscription verification with automatic cleanup on failure

        This prevents failed subscriptions from blocking periodic_full_scan() while
        ensuring positions with failed subscriptions are properly cleaned up.

        Args:
            symbol: Symbol to verify
            position: Position object (for re-adding to aged_targets if needed)
        """
        try:
            # ✅ CHANGE: Reduced timeout from 30s to 15s (still safe, but less blocking)
            # 15s chosen because:
            # - staleness_threshold = 30s
            # - verification should complete before staleness
            # - allows 2-3 price updates (WebSocket updates every 3-5s)
            verified = await self._verify_subscription_active(symbol, timeout=15)

            if verified:
                logger.info(f"✅ {symbol}: Subscription verified (background check passed)")
                return  # Success - nothing to cleanup

            # ❌ Verification FAILED
            logger.error(
                f"❌ {symbol}: Background subscription verification FAILED! "
                f"No price update received within 15s. Cleaning up..."
            )

            # ✅ CLEANUP: Remove from monitoring
            if symbol in self.monitoring_positions:
                del self.monitoring_positions[symbol]
                logger.warning(f"🧹 {symbol}: Removed from monitoring_positions")

            # ✅ CLEANUP: Unsubscribe from price updates
            try:
                await self.price_monitor.unsubscribe(symbol, 'aged_position')
                logger.debug(f"🧹 {symbol}: Unsubscribed from price updates")
            except Exception as unsub_error:
                logger.error(f"Error unsubscribing {symbol}: {unsub_error}")

            # ✅ CLEANUP: Remove from aged_targets in aged_monitor
            if self.aged_monitor and symbol in self.aged_monitor.aged_targets:
                del self.aged_monitor.aged_targets[symbol]
                logger.warning(f"🧹 {symbol}: Removed from aged_targets")

            # Log summary
            logger.error(
                f"⚠️ {symbol}: Aged monitoring DISABLED due to failed subscription. "
                f"Position will NOT be monitored until next periodic scan or manual intervention."
            )

        except asyncio.CancelledError:
            logger.debug(f"Background verification cancelled for {symbol} (likely due to re-add)")
            raise

        except Exception as e:
            logger.error(
                f"❌ Error in background verification for {symbol}: {e}",
                exc_info=True
            )
            # On error, be conservative: remove from monitoring
            if symbol in self.monitoring_positions:
                del self.monitoring_positions[symbol]
                logger.warning(f"🧹 {symbol}: Removed from monitoring due to verification error")

        finally:
            # ✅ CLEANUP: Remove task reference
            if symbol in self._verification_tasks:
                del self._verification_tasks[symbol]

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

    async def _verify_subscription_active(self, symbol: str, timeout: int = 15) -> bool:
        """
        Verify subscription is receiving data

        ✅ CHANGE: Default timeout reduced from 30s to 15s

        Args:
            symbol: Symbol to verify
            timeout: Max seconds to wait (default: 15)

        Returns:
            True if subscription verified, False otherwise
        """
        import time

        # Record current last update time
        start_time = time.time()
        initial_update_time = self.price_monitor.last_update_time.get(symbol, 0)

        logger.debug(
            f"🔍 Verifying subscription for {symbol} (timeout: {timeout}s, background mode)..."
        )

        # Wait for update
        elapsed: float = 0.0
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