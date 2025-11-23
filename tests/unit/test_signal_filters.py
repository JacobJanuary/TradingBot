"""
Unit tests for signal filtering functionality in WaveSignalProcessor.

Tests the three new filters:
1. Open Interest filter (>= 1M USDT)
2. Volume filter (>= 50k USDT)
3. Price change filter (<= 4%)
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from decimal import Decimal

from core.wave_signal_processor import WaveSignalProcessor
from config.settings import TradingConfig


@pytest.fixture
def mock_config():
    """Create mock trading config with filter settings."""
    config = Mock(spec=TradingConfig)
    config.max_trades_per_15min = 10
    config.signal_buffer_fixed = 3
    config.duplicate_check_enabled = True

    # Filter settings
    config.signal_min_open_interest_usdt = 1_000_000
    config.signal_min_volume_1h_usdt = 50_000
    config.signal_max_price_change_5min_percent = 4.0
    config.signal_filter_oi_enabled = True
    config.signal_filter_volume_enabled = True
    config.signal_filter_price_change_enabled = True

    # Position sizing
    config.position_size_usd = Decimal('6')

    return config


@pytest.fixture
def mock_position_manager():
    """Create mock position manager."""
    pm = AsyncMock()
    pm.has_open_position = AsyncMock(return_value=False)
    pm.exchanges = {}
    return pm


@pytest.fixture
def mock_exchange_manager():
    """Create mock exchange manager with necessary methods."""
    em = Mock()
    em.exchange = Mock()
    em.find_exchange_symbol = Mock(return_value='BTCUSDT')
    em.fetch_ticker = AsyncMock(return_value={'last': 50000, 'close': 50000})
    em.markets = {'BTCUSDT': {'limits': {'cost': {'min': 5.0}}}}

    # Mock exchange methods for filters
    em.exchange.fetch_open_interest = AsyncMock()
    em.exchange.fetch_ohlcv = AsyncMock()

    return em


@pytest.fixture
async def processor(mock_config, mock_position_manager):
    """Create WaveSignalProcessor instance for testing."""
    processor = WaveSignalProcessor(mock_config, mock_position_manager)
    return processor


class TestOpenInterestFilter:
    """Tests for OI filter."""

    @pytest.mark.asyncio
    async def test_oi_above_threshold_passes(self, processor, mock_position_manager, mock_exchange_manager):
        """Test that signals with OI >= 1M pass the filter."""
        # Setup
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}

        # Mock OI = 2M (above threshold)
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            return_value={'openInterestValue': 2_000_000}
        )

        signal = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        # Test
        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')

        # Should NOT be filtered (is_duplicate = False)
        assert is_duplicate is False
        assert reason == ""

    @pytest.mark.asyncio
    async def test_oi_below_threshold_filtered(self, processor, mock_position_manager, mock_exchange_manager):
        """Test that signals with OI < 1M are filtered."""
        # Setup
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}

        # Mock OI = 500k (below threshold)
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            return_value={'openInterestValue': 500_000}
        )

        signal = {
            'symbol': 'LOWCAPUSDT',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        # Test
        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')

        # Should be filtered (is_duplicate = True)
        assert is_duplicate is True
        assert 'OI' in reason or 'below minimum' in reason
        assert processor.total_filtered_low_oi == 1

    @pytest.mark.asyncio
    async def test_oi_filter_disabled(self, processor, mock_position_manager, mock_exchange_manager):
        """Test that signals pass when OI filter is disabled."""
        # Disable OI filter
        processor.config.signal_filter_oi_enabled = False

        mock_position_manager.exchanges = {'binance': mock_exchange_manager}

        # Mock low OI (would normally be filtered)
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            return_value={'openInterestValue': 100_000}
        )

        signal = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        # Test
        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')

        # Should NOT be filtered (filter disabled)
        assert is_duplicate is False


class TestVolumeFilter:
    """Tests for 1h volume filter."""

    @pytest.mark.asyncio
    async def test_volume_above_threshold_passes(self, processor, mock_position_manager, mock_exchange_manager):
        """Test that signals with 1h volume >= 50k pass."""
        # Setup
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}

        # Mock OI above threshold (to pass OI filter)
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            return_value={'openInterestValue': 2_000_000}
        )

        # Mock volume = 100k (above threshold)
        # OHLCV: [timestamp, open, high, low, close, volume]
        mock_exchange_manager.exchange.fetch_ohlcv = AsyncMock(
            return_value=[[0, 50000, 51000, 49000, 50000, 2.0]]  # 2.0 * 50000 = 100k USDT
        )

        signal = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        # Test
        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')

        # Should NOT be filtered
        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_volume_below_threshold_filtered(self, processor, mock_position_manager, mock_exchange_manager):
        """Test that signals with 1h volume < 50k are filtered."""
        # Setup
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}

        # Mock OI above threshold (to pass OI filter)
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            return_value={'openInterestValue': 2_000_000}
        )

        # Mock volume = 10k (below threshold)
        mock_exchange_manager.exchange.fetch_ohlcv = AsyncMock(
            return_value=[[0, 50000, 51000, 49000, 50000, 0.2]]  # 0.2 * 50000 = 10k USDT
        )

        signal = {
            'symbol': 'LOWVOLUMECOIN',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        # Test
        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')

        # Should be filtered
        assert is_duplicate is True
        assert 'volume' in reason.lower()
        assert processor.total_filtered_low_volume == 1


class TestPriceChangeFilter:
    """Tests for price change (overheating) filter."""

    def _setup_candles(self, mock_exchange_manager, price_at_signal, price_5min_before, price_15min_before=None):
        """Helper to setup mock candles."""
        now = datetime.now(timezone.utc)
        ts_now = int(now.timestamp() * 1000)
        ts_5m = int((now - timedelta(minutes=5)).timestamp() * 1000)
        ts_15m = int((now - timedelta(minutes=15)).timestamp() * 1000)

        candles = [
            [ts_now, price_at_signal, price_at_signal, price_at_signal, price_at_signal, 1.0],
            [ts_5m, price_5min_before, price_5min_before, price_5min_before, price_5min_before, 1.0]
        ]
        
        if price_15min_before is not None:
            candles.append([ts_15m, price_15min_before, price_15min_before, price_15min_before, price_15min_before, 1.0])
        else:
            # Default 15m price same as 5m if not specified (no change)
            candles.append([ts_15m, price_5min_before, price_5min_before, price_5min_before, price_5min_before, 1.0])

        mock_exchange_manager.exchange.fetch_ohlcv = AsyncMock(
            side_effect=[
                [[0, 100000, 102000, 99000, 100000, 2.0]],  # Volume check
                candles                                     # Price check (single call)
            ]
        )
        return now

    @pytest.mark.asyncio
    async def test_buy_signal_small_price_rise_passes(self, processor, mock_position_manager, mock_exchange_manager):
        """Test BUY signal with price rise <= 4% passes."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(return_value={'openInterestValue': 2_000_000})

        # Price rose 2% in 5 min (50000 -> 51000)
        timestamp = self._setup_candles(mock_exchange_manager, 51000, 50000)

        signal = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'timestamp': timestamp.isoformat(),
            'recommended_action': 'BUY'
        }

        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')
        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_buy_signal_large_price_rise_filtered(self, processor, mock_position_manager, mock_exchange_manager):
        """Test BUY signal with price rise > 4% is filtered (overheated)."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(return_value={'openInterestValue': 2_000_000})

        # Price rose 6% in 5 min (50000 -> 53000)
        timestamp = self._setup_candles(mock_exchange_manager, 53000, 50000)

        signal = {
            'symbol': 'OVERHEATED',
            'exchange': 'binance',
            'timestamp': timestamp.isoformat(),
            'recommended_action': 'BUY'
        }

        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')
        assert is_duplicate is True
        assert 'overheated 5m' in reason
        assert processor.total_filtered_price_change == 1

    @pytest.mark.asyncio
    async def test_sell_signal_small_price_drop_passes(self, processor, mock_position_manager, mock_exchange_manager):
        """Test SELL signal with price drop <= 4% passes."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(return_value={'openInterestValue': 2_000_000})

        # Price dropped 2% in 5 min (50000 -> 49000)
        timestamp = self._setup_candles(mock_exchange_manager, 49000, 50000)

        signal = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'timestamp': timestamp.isoformat(),
            'recommended_action': 'SELL'
        }

        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')
        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_sell_signal_large_price_drop_filtered(self, processor, mock_position_manager, mock_exchange_manager):
        """Test SELL signal with price drop > 4% is filtered (oversold)."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(return_value={'openInterestValue': 2_000_000})

        # Price dropped 6% in 5 min (50000 -> 47000)
        timestamp = self._setup_candles(mock_exchange_manager, 47000, 50000)

        signal = {
            'symbol': 'OVERSOLD',
            'exchange': 'binance',
            'timestamp': timestamp.isoformat(),
            'recommended_action': 'SELL'
        }

        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')
        assert is_duplicate is True
        assert 'oversold 5m' in reason

    @pytest.mark.asyncio
    async def test_buy_signal_15m_rise_filtered(self, processor, mock_position_manager, mock_exchange_manager):
        """Test BUY signal with 15m price rise > 8% is filtered."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(return_value={'openInterestValue': 2_000_000})

        # 5m change: 50000 -> 51000 (+2%, OK)
        # 15m change: 46000 -> 51000 (+10.8%, > 8% limit)
        timestamp = self._setup_candles(mock_exchange_manager, 51000, 50000, price_15min_before=46000)

        signal = {
            'symbol': 'PUMP15M',
            'exchange': 'binance',
            'timestamp': timestamp.isoformat(),
            'recommended_action': 'BUY'
        }

        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')
        assert is_duplicate is True
        assert 'overheated 15m' in reason

    @pytest.mark.asyncio
    async def test_sell_signal_15m_drop_filtered(self, processor, mock_position_manager, mock_exchange_manager):
        """Test SELL signal with 15m price drop > 8% is filtered."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(return_value={'openInterestValue': 2_000_000})

        # 5m change: 50000 -> 49000 (-2%, OK)
        # 15m change: 55000 -> 49000 (-10.9%, > 8% limit)
        timestamp = self._setup_candles(mock_exchange_manager, 49000, 50000, price_15min_before=55000)

        signal = {
            'symbol': 'DUMP15M',
            'exchange': 'binance',
            'timestamp': timestamp.isoformat(),
            'recommended_action': 'SELL'
        }

        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')
        assert is_duplicate is True
        assert 'oversold 15m' in reason


class TestFilterStatistics:
    """Tests for filter statistics tracking."""

    @pytest.mark.asyncio
    async def test_statistics_increment(self, processor, mock_position_manager, mock_exchange_manager):
        """Test that filter statistics are correctly incremented."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}

        # Test OI filter count
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            return_value={'openInterestValue': 100_000}  # Below threshold
        )

        signal = {
            'symbol': 'TEST1',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        await processor._is_duplicate(signal, 'test')
        assert processor.total_filtered_low_oi == 1

        # Test volume filter count
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            return_value={'openInterestValue': 2_000_000}  # Passes OI
        )
        mock_exchange_manager.exchange.fetch_ohlcv = AsyncMock(
            return_value=[[0, 50000, 51000, 49000, 50000, 0.1]]  # Low volume
        )

        signal2 = {
            'symbol': 'TEST2',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        await processor._is_duplicate(signal2, 'test')
        assert processor.total_filtered_low_volume == 1

    def test_get_statistics_includes_filters(self, processor):
        """Test that get_statistics() returns filter counts."""
        processor.total_filtered_low_oi = 5
        processor.total_filtered_low_volume = 3
        processor.total_filtered_price_change = 1

        stats = processor.get_statistics()

        assert stats['total_stats']['filtered_low_oi'] == 5
        assert stats['total_stats']['filtered_low_volume'] == 3
        assert stats['total_stats']['filtered_price_change'] == 1

    def test_reset_statistics_clears_filters(self, processor):
        """Test that reset_statistics() clears filter counts."""
        processor.total_filtered_low_oi = 10
        processor.total_filtered_low_volume = 5
        processor.total_filtered_price_change = 2

        processor.reset_statistics()

        assert processor.total_filtered_low_oi == 0
        assert processor.total_filtered_low_volume == 0
        assert processor.total_filtered_price_change == 0


class TestFilterGracefulDegradation:
    """Tests for graceful degradation when API fails."""

    @pytest.mark.asyncio
    async def test_oi_api_failure_does_not_filter(self, processor, mock_position_manager, mock_exchange_manager):
        """Test that signals with OI API failure don't get filtered by OI check."""
        mock_position_manager.exchanges = {'binance': mock_exchange_manager}

        # Mock ticker works (needed for price check)
        mock_exchange_manager.fetch_ticker = AsyncMock(
            return_value={'last': 50000, 'close': 50000}
        )

        # Mock OI API failure
        mock_exchange_manager.exchange.fetch_open_interest = AsyncMock(
            side_effect=Exception("OI API Error")
        )

        # Mock volume and price checks pass
        mock_exchange_manager.exchange.fetch_ohlcv = AsyncMock(
            side_effect=[
                [[0, 50000, 51000, 49000, 50000, 2.0]],  # Volume check passes
                [[0, 51000, 52000, 50000, 51000, 1.0]],  # Price at signal
                [[0, 50000, 51000, 49000, 50000, 1.0]]   # Price 5min before (+2%)
            ]
        )

        signal = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommended_action': 'BUY'
        }

        # Test - should NOT be filtered despite OI API error
        is_duplicate, reason = await processor._is_duplicate(signal, 'test_wave')

        # Graceful degradation: None OI = skip OI filter, check other filters
        assert is_duplicate is False
        assert reason == ""
