"""
Unified Price Monitor - MINIMAL implementation for hybrid approach
NO refactoring, NO optimization - just working integration
"""

import asyncio
import logging
from typing import Dict, List, Callable, Optional
from datetime import datetime
from decimal import Decimal
from collections import defaultdict
import time

logger = logging.getLogger(__name__)


class UnifiedPriceMonitor:
    """
    MINIMAL unified price monitor for TrailingStop + AgedPosition integration

    NO fancy features - just what's needed:
    - Price distribution to subscribers
    - Simple priority handling
    - Basic error isolation
    """

    def __init__(self):
        # Subscribers: symbol -> list of (module, callback, priority)
        self.subscribers = defaultdict(list)

        # Simple price cache
        self.last_prices = {}

        # Rate limiting - prevent flooding
        self.last_update_time = defaultdict(float)
        self.min_update_interval = 0.1  # 100ms between updates per symbol

        # ✅ ENHANCEMENT #2A: Staleness tracking
        # ✅ PHASE 1: Per-module thresholds
        self.staleness_thresholds = {
            'trailing_stop': 30,      # 30 seconds for trailing stops
            'aged_position': 30,      # 30 seconds for aged positions
            'default': 300            # 5 minutes for other modules
        }
        self.stale_symbols = set()  # Symbols with stale prices
        self.staleness_warnings_logged = set()  # Prevent spam

        # Simple stats
        self.update_count = 0
        self.error_count = 0

        self.running = False

    async def start(self):
        """Start monitor - minimal setup"""
        self.running = True
        logger.info("UnifiedPriceMonitor started (minimal mode)")

    async def stop(self):
        """Stop monitor"""
        self.running = False
        logger.info("UnifiedPriceMonitor stopped")

    async def subscribe(
        self,
        symbol: str,
        callback: Callable,
        module: str,
        priority: int = 100
    ):
        """
        Subscribe to price updates - SIMPLE version

        Lower priority number = higher priority (executed first)
        """
        # Add subscriber
        self.subscribers[symbol].append({
            'module': module,
            'callback': callback,
            'priority': priority
        })

        # Sort by priority
        self.subscribers[symbol].sort(key=lambda x: x['priority'])

        logger.info(f"✅ {module} subscribed to {symbol} (priority={priority})")

    async def unsubscribe(self, symbol: str, module: str):
        """Unsubscribe from price updates"""
        if symbol in self.subscribers:
            self.subscribers[symbol] = [
                s for s in self.subscribers[symbol]
                if s['module'] != module
            ]

            if not self.subscribers[symbol]:
                del self.subscribers[symbol]

    async def update_price(self, symbol: str, price: Decimal):
        """
        Main entry point - distribute price to subscribers
        Called by PositionManager._on_position_update()
        """

        # Rate limiting
        now = time.time()
        if now - self.last_update_time[symbol] < self.min_update_interval:
            return  # Skip too frequent updates

        self.last_update_time[symbol] = now
        self.last_prices[symbol] = price
        self.update_count += 1

        # Notify subscribers
        if symbol in self.subscribers:
            for subscriber in self.subscribers[symbol]:
                try:
                    # Call with error isolation
                    await subscriber['callback'](symbol, price)
                except Exception as e:
                    logger.error(
                        f"Error in {subscriber['module']} callback for {symbol}: {e}"
                    )
                    self.error_count += 1

    async def check_staleness(
        self,
        symbols_to_check: list = None,
        module: str = None
    ) -> dict:
        """
        ✅ ENHANCEMENT #2B + PHASE 1: Check if price updates are stale for given symbols

        Args:
            symbols_to_check: List of symbols to check, or None for all subscribed
            module: Module name to use specific threshold (trailing_stop, aged_position)

        Returns:
            dict: {symbol: {'stale': bool, 'seconds_since_update': float, 'threshold_used': int}}
        """
        import time

        now = time.time()
        result = {}

        # Determine threshold based on module
        if module and module in self.staleness_thresholds:
            threshold = self.staleness_thresholds[module]
        else:
            threshold = self.staleness_thresholds['default']

        # Default to all subscribed symbols
        if symbols_to_check is None:
            symbols_to_check = list(self.subscribers.keys())

        for symbol in symbols_to_check:
            if symbol not in self.last_update_time:
                # Never received update
                result[symbol] = {
                    'stale': True,
                    'seconds_since_update': float('inf'),
                    'last_update': None,
                    'threshold_used': threshold
                }
                continue

            last_update = self.last_update_time[symbol]
            seconds_since = now - last_update
            is_stale = seconds_since > threshold

            result[symbol] = {
                'stale': is_stale,
                'seconds_since_update': seconds_since,
                'last_update': last_update,
                'threshold_used': threshold
            }

            # Track stale symbols
            if is_stale:
                self.stale_symbols.add(symbol)

                # Log warning once per symbol
                if symbol not in self.staleness_warnings_logged:
                    logger.warning(
                        f"⚠️ STALE PRICE: {symbol} - no updates for {seconds_since:.0f}s "
                        f"(threshold: {threshold}s, module: {module or 'default'})"
                    )
                    self.staleness_warnings_logged.add(symbol)
            else:
                # No longer stale - clear tracking
                self.stale_symbols.discard(symbol)
                self.staleness_warnings_logged.discard(symbol)

        return result

    def get_last_price(self, symbol: str) -> Optional[Decimal]:
        """Get last known price for symbol"""
        return self.last_prices.get(symbol)

    def get_stats(self) -> Dict:
        """Get simple statistics"""
        return {
            'update_count': self.update_count,
            'error_count': self.error_count,
            'symbols_tracked': len(self.last_prices),
            'total_subscribers': sum(len(subs) for subs in self.subscribers.values())
        }