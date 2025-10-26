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
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ✅ PHASE 3: Global metrics instance
_subscription_metrics = None


def get_subscription_metrics():
    """Get or create subscription metrics instance"""
    global _subscription_metrics
    if _subscription_metrics is None:
        try:
            from core.aged_position_metrics import SubscriptionMetrics
            _subscription_metrics = SubscriptionMetrics()
        except ImportError:
            _subscription_metrics = None
    return _subscription_metrics


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

            # ✅ FIX #5: Run subscription health check
            aged_adapter = unified_protection.get('aged_adapter')
            if aged_adapter:
                await aged_monitor.verify_subscriptions(aged_adapter)

        except asyncio.CancelledError:
            logger.info("Periodic aged scan task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic aged scan: {e}")
            # Continue running despite errors
            await asyncio.sleep(60)  # Wait 1 minute before retry


async def resubscribe_stale_positions(
    unified_protection: Dict,
    stale_symbols: list,
    position_manager,
    max_retries: int = 3
) -> int:
    """
    ✅ PHASE 1 + PHASE 2 + PHASE 3: Automatic resubscription with exponential backoff and metrics

    Args:
        unified_protection: Unified protection components
        stale_symbols: List of symbols with stale data
        position_manager: Position manager instance
        max_retries: Maximum retry attempts per symbol (default: 3)

    Returns:
        Number of positions resubscribed
    """
    aged_adapter = unified_protection.get('aged_adapter')
    price_monitor = unified_protection.get('price_monitor')

    if not aged_adapter or not price_monitor:
        logger.error("Cannot resubscribe - missing components")
        return 0

    # ✅ PHASE 3: Get metrics instance
    metrics = get_subscription_metrics()

    resubscribed = 0

    for symbol in stale_symbols:
        success = False

        # ✅ PHASE 2: Exponential backoff retry
        for attempt in range(1, max_retries + 1):
            try:
                logger.warning(
                    f"🔄 Attempting resubscription for {symbol} "
                    f"(attempt {attempt}/{max_retries})"
                )

                # Get position
                position = position_manager.positions.get(symbol)
                if not position:
                    logger.warning(f"⚠️ Position {symbol} not found")
                    break

                # Unsubscribe first
                if symbol in aged_adapter.monitoring_positions:
                    await aged_adapter.remove_aged_position(symbol)
                    logger.debug(f"📤 Unsubscribed {symbol}")

                # Exponential backoff wait
                if attempt > 1:
                    wait_time = 2 ** (attempt - 1)  # 2, 4, 8 seconds
                    logger.debug(f"⏳ Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(0.5)

                # Re-subscribe (with verification in Phase 2)
                await aged_adapter.add_aged_position(position)

                # Check if successful
                if symbol in price_monitor.subscribers:
                    resubscribed += 1
                    success = True
                    logger.info(
                        f"✅ Successfully resubscribed {symbol} "
                        f"(attempt {attempt})"
                    )
                    break
                else:
                    logger.warning(
                        f"⚠️ Resubscription attempt {attempt} failed for {symbol}"
                    )

            except Exception as e:
                logger.error(
                    f"❌ Error resubscribing {symbol} (attempt {attempt}): {e}",
                    exc_info=True
                )

        # All retries failed
        if not success:
            logger.error(
                f"❌ FAILED to resubscribe {symbol} after {max_retries} attempts! "
                f"MANUAL INTERVENTION REQUIRED"
            )

    if resubscribed > 0:
        logger.warning(
            f"🔄 Resubscribed {resubscribed}/{len(stale_symbols)} stale positions"
        )

        # ✅ PHASE 3: Record metrics
        if metrics:
            metrics.resubscription_count += resubscribed
            metrics.last_resubscription_at = datetime.now(timezone.utc)

    return resubscribed


async def check_alert_conditions(
    unified_protection: Dict,
    staleness_report: dict
):
    """
    ✅ PHASE 3: Check alert conditions and log critical warnings

    Alerts:
    - Any aged position stale > 2 minutes
    - High resubscription rate (>10)
    - High verification failure rate (>5)
    """
    metrics = get_subscription_metrics()

    # Alert 1: Aged position stale > 2 minutes
    for symbol, data in staleness_report.items():
        if data['stale'] and data['seconds_since_update'] > 120:  # 2 minutes
            logger.critical(
                f"🚨 CRITICAL ALERT: {symbol} stale for "
                f"{data['seconds_since_update']/60:.1f} minutes! "
                f"Exceeds 2-minute alert threshold"
            )

    # Alert 2: High resubscription rate
    if metrics and metrics.resubscription_count > 10:
        logger.critical(
            f"🚨 HIGH RESUBSCRIPTION RATE: "
            f"{metrics.resubscription_count} resubscriptions! "
            f"May indicate connection instability"
        )

    # Alert 3: Verification failures
    if metrics and metrics.verification_failure_count > 5:
        logger.critical(
            f"🚨 HIGH VERIFICATION FAILURE RATE: "
            f"{metrics.verification_failure_count} failures! "
            f"Check WebSocket connection health"
        )


async def start_websocket_health_monitor(
    unified_protection: Dict,
    check_interval_seconds: int = 60,
    position_manager = None
):
    """
    ✅ ENHANCEMENT #2C + PHASE 1 + PHASE 3: Monitor WebSocket health for aged positions
    NOW with automatic resubscription for stale subscriptions and metrics collection

    Periodically checks if aged positions are receiving price updates.
    Alerts if prices are stale (> 30 seconds without update).

    Args:
        unified_protection: Unified protection components
        check_interval_seconds: Check interval (default: 60s)
        position_manager: Position manager instance (for resubscription)
    """
    if not unified_protection:
        return

    aged_monitor = unified_protection.get('aged_monitor')
    price_monitor = unified_protection.get('price_monitor')

    if not aged_monitor or not price_monitor:
        logger.warning("WebSocket health monitor disabled - missing components")
        return

    # ✅ PHASE 3: Get metrics instance
    metrics = get_subscription_metrics()

    logger.info(
        f"🔍 Starting WebSocket health monitor "
        f"(interval: {check_interval_seconds}s, threshold: 30s for aged/trailing)"
    )

    while True:
        try:
            await asyncio.sleep(check_interval_seconds)

            # Get list of aged position symbols
            aged_symbols = list(aged_monitor.aged_targets.keys())

            if not aged_symbols:
                continue  # No aged positions to monitor

            # Check staleness for aged symbols with 30s threshold
            staleness_report = await price_monitor.check_staleness(
                aged_symbols,
                module='aged_position'
            )

            # Count stale aged positions
            stale_symbols = [
                symbol for symbol, data in staleness_report.items()
                if data['stale']
            ]
            stale_count = len(stale_symbols)

            if stale_count > 0:
                logger.warning(
                    f"⚠️ WebSocket Health Check: {stale_count}/{len(aged_symbols)} "
                    f"aged positions have STALE prices (threshold: 30s)!"
                )

                # ✅ PHASE 3: Record stale detection metrics
                if metrics:
                    metrics.stale_detection_count += stale_count
                    metrics.last_stale_detected_at = datetime.now(timezone.utc)

                    # Update max stale duration
                    max_stale = max(
                        data['seconds_since_update']
                        for data in staleness_report.values()
                        if data['stale']
                    )
                    if max_stale > metrics.max_stale_duration_seconds:
                        metrics.max_stale_duration_seconds = max_stale

                # Log each stale position
                for symbol, data in staleness_report.items():
                    if data['stale']:
                        seconds = data['seconds_since_update']
                        logger.warning(
                            f"  - {symbol}: no update for {seconds:.0f}s "
                            f"({seconds/60:.1f} minutes)"
                        )

                # ✅ PHASE 3: Check alert conditions
                await check_alert_conditions(unified_protection, staleness_report)

                # ✅ NEW: AUTOMATIC RESUBSCRIPTION
                if position_manager:
                    resubscribed_count = await resubscribe_stale_positions(
                        unified_protection,
                        stale_symbols,
                        position_manager
                    )

                    if resubscribed_count > 0:
                        logger.info(
                            f"✅ Resubscription completed: {resubscribed_count} "
                            f"positions recovered"
                        )
                else:
                    logger.error(
                        "⚠️ Cannot resubscribe - position_manager not provided!"
                    )
            else:
                # All good
                logger.debug(
                    f"✅ WebSocket Health Check: all {len(aged_symbols)} "
                    f"aged positions receiving updates"
                )

        except asyncio.CancelledError:
            logger.info("WebSocket health monitor stopped")
            break
        except Exception as e:
            logger.error(f"Error in WebSocket health monitor: {e}", exc_info=True)
            await asyncio.sleep(10)  # Wait before retry


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