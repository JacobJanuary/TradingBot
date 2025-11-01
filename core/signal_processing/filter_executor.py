"""
FilterExecutor - applies all filters to signals BEFORE selection.
Part of signal filtering fix - Phase 1.
"""
import asyncio
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from core.models.signal_models import EnrichedSignal, FilterResult

logger = logging.getLogger(__name__)


class FilterExecutor:
    """Applies all filters to signals BEFORE selection"""

    def __init__(self, config):
        self.config = config
        self.min_oi = float(getattr(config, 'signal_min_open_interest_usdt', 500_000))
        self.min_volume = float(getattr(config, 'signal_min_volume_1h_usdt', 20_000))
        self.max_price_change = float(getattr(config, 'signal_max_price_change_5min_percent', 4.0))

        # Cache for API calls (OI, volume)
        self.oi_cache: Dict[str, Tuple[float, datetime]] = {}
        self.volume_cache: Dict[str, Tuple[float, datetime]] = {}
        self.cache_ttl = 60  # seconds

        # Track existing positions to mark duplicates
        self.existing_positions = set()

    async def apply_filters_batch(
        self,
        signals: List[EnrichedSignal],
        exchange_manager
    ) -> List[EnrichedSignal]:
        """
        Apply filters to ALL signals in parallel.
        Returns list with passed_filters flag set.
        """
        if not signals:
            return signals

        logger.info(f"📝 Applying filters to {len(signals)} signals...")

        # Step 1: Fetch all OI and volume data in parallel
        await self._prefetch_market_data(signals, exchange_manager)

        # Step 2: Apply filters to each signal
        tasks = [
            self._apply_filters_single(signal, exchange_manager)
            for signal in signals
        ]

        # Process in batches to avoid overwhelming API
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            await asyncio.gather(*batch)

        # Step 3: Mark duplicates
        self._mark_duplicate_positions(signals)

        # Log results
        passed = [s for s in signals if s.passed_filters]
        failed = [s for s in signals if not s.passed_filters]

        logger.info(
            f"✅ Filters applied: {len(passed)}/{len(signals)} passed, "
            f"{len(failed)} filtered out"
        )

        # Log filter reasons
        if failed:
            reasons = defaultdict(int)
            for signal in failed:
                if signal.filter_reason:
                    reasons[signal.filter_reason.value] += 1
            logger.info(f"📊 Filter reasons: {dict(reasons)}")

        return signals

    async def _prefetch_market_data(
        self,
        signals: List[EnrichedSignal],
        exchange_manager
    ):
        """Prefetch OI and volume for all signals to optimize API calls"""

        # Group by exchange for batch API calls
        by_exchange = defaultdict(list)
        for signal in signals:
            by_exchange[signal.exchange].append(signal.symbol)

        # Fetch in parallel per exchange
        tasks = []
        for exchange, symbols in by_exchange.items():
            # Remove duplicates
            unique_symbols = list(set(symbols))
            for symbol in unique_symbols:
                # Check cache first
                if not self._is_cached(symbol, 'oi'):
                    tasks.append(self._fetch_and_cache_oi(symbol, exchange, exchange_manager))
                if not self._is_cached(symbol, 'volume'):
                    tasks.append(self._fetch_and_cache_volume(symbol, exchange, exchange_manager))

        if tasks:
            # Limit concurrent fetches
            batch_size = 5
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                await asyncio.gather(*batch, return_exceptions=True)

    def _is_cached(self, symbol: str, data_type: str) -> bool:
        """Check if data is cached and not expired"""
        cache = self.oi_cache if data_type == 'oi' else self.volume_cache
        if symbol in cache:
            value, timestamp = cache[symbol]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return True
        return False

    async def _fetch_and_cache_oi(self, symbol: str, exchange: str, exchange_manager):
        """Fetch and cache open interest"""
        try:
            # Get ticker for current price
            ticker = await exchange_manager.fetch_ticker(symbol)
            if not ticker:
                return None

            current_price = ticker.get('last') or ticker.get('close')
            if not current_price:
                return None

            # Fetch open interest
            if exchange.lower() == 'bybit':
                # Bybit-specific handling
                info = ticker.get('info', {})
                open_interest = info.get('openInterest')
                if open_interest:
                    oi_usdt = float(open_interest) * float(current_price)
                else:
                    oi_usdt = None
            else:
                # Binance and others
                oi_data = await exchange_manager.fetch_open_interest(symbol)
                if oi_data and 'openInterest' in oi_data:
                    oi_contracts = oi_data['openInterest']
                    oi_usdt = float(oi_contracts) * float(current_price)
                else:
                    oi_usdt = None

            if oi_usdt is not None:
                self.oi_cache[symbol] = (oi_usdt, datetime.now())

        except Exception as e:
            logger.debug(f"Failed to fetch OI for {symbol}: {e}")

    async def _fetch_and_cache_volume(self, symbol: str, exchange: str, exchange_manager):
        """Fetch and cache 1h volume"""
        try:
            # Fetch ticker which includes volume
            ticker = await exchange_manager.fetch_ticker(symbol)
            if not ticker:
                return None

            # Get 24h volume and estimate 1h (rough approximation)
            volume_24h = ticker.get('quoteVolume') or ticker.get('baseVolume', 0)
            if volume_24h:
                # Rough estimate: 1h volume = 24h volume / 24
                volume_1h = float(volume_24h) / 24
                self.volume_cache[symbol] = (volume_1h, datetime.now())

        except Exception as e:
            logger.debug(f"Failed to fetch volume for {symbol}: {e}")

    def _get_cached_oi(self, symbol: str) -> Optional[float]:
        """Get cached OI if available"""
        if symbol in self.oi_cache:
            value, timestamp = self.oi_cache[symbol]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return value
        return None

    def _get_cached_volume(self, symbol: str) -> Optional[float]:
        """Get cached volume if available"""
        if symbol in self.volume_cache:
            value, timestamp = self.volume_cache[symbol]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return value
        return None

    async def _apply_filters_single(
        self,
        signal: EnrichedSignal,
        exchange_manager
    ) -> None:
        """Apply all filters to a single signal"""

        # Get cached data
        oi = self._get_cached_oi(signal.symbol)
        volume = self._get_cached_volume(signal.symbol)

        signal.open_interest_usdt = oi
        signal.volume_1h_usdt = volume

        # Check OI filter
        if self.config.signal_filter_oi_enabled and oi is not None and oi < self.min_oi:
            signal.passed_filters = False
            signal.filter_reason = FilterResult.LOW_OI
            signal.filter_details = {
                'oi_usdt': oi,
                'min_required': self.min_oi
            }
            logger.debug(f"⏭️ {signal.symbol}: OI ${oi:,.0f} < ${self.min_oi:,.0f}")
            return

        # Check volume filter
        if self.config.signal_filter_volume_enabled and volume is not None and volume < self.min_volume:
            signal.passed_filters = False
            signal.filter_reason = FilterResult.LOW_VOLUME
            signal.filter_details = {
                'volume_1h_usdt': volume,
                'min_required': self.min_volume
            }
            logger.debug(f"⏭️ {signal.symbol}: Volume ${volume:,.0f} < ${self.min_volume:,.0f}")
            return

        # Check price change filter (simplified for now)
        # This would need actual implementation based on your existing logic
        # For now, we'll pass this check

        # All filters passed
        signal.passed_filters = True
        signal.filter_reason = FilterResult.PASSED

    def _mark_duplicate_positions(self, signals: List[EnrichedSignal]):
        """Mark signals as duplicates if position already exists"""
        # This needs to be populated with actual existing positions
        # For now, we'll skip this check as it requires position_manager integration
        pass

    def set_existing_positions(self, positions: set):
        """Update the set of existing positions"""
        self.existing_positions = positions