"""
Tests for WebSocket Health Monitoring
Validates Enhancement #2: WebSocket Health Monitoring
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

from websocket.unified_price_monitor import UnifiedPriceMonitor


class TestStalenessDetection:
    """Test staleness detection in UnifiedPriceMonitor"""

    @pytest.mark.asyncio
    async def test_fresh_price_not_stale(self):
        """Test that recently updated price is not stale"""
        monitor = UnifiedPriceMonitor()

        # Simulate price update
        await monitor.update_price('BTCUSDT', Decimal('50000'))

        # Check staleness
        report = await monitor.check_staleness(['BTCUSDT'])

        assert not report['BTCUSDT']['stale']
        assert report['BTCUSDT']['seconds_since_update'] < 1

    @pytest.mark.asyncio
    async def test_old_price_is_stale(self):
        """Test that old price is detected as stale"""
        monitor = UnifiedPriceMonitor()
        monitor.staleness_threshold_seconds = 1  # 1 second for testing

        # Simulate price update
        await monitor.update_price('BTCUSDT', Decimal('50000'))

        # Wait for staleness
        await asyncio.sleep(1.5)

        # Check staleness
        report = await monitor.check_staleness(['BTCUSDT'])

        assert report['BTCUSDT']['stale']
        assert report['BTCUSDT']['seconds_since_update'] >= 1

    @pytest.mark.asyncio
    async def test_never_updated_is_stale(self):
        """Test that never-updated symbol is stale"""
        monitor = UnifiedPriceMonitor()

        # Check staleness for symbol that never received update
        report = await monitor.check_staleness(['NEVERUSDT'])

        assert report['NEVERUSDT']['stale']
        assert report['NEVERUSDT']['seconds_since_update'] == float('inf')

    @pytest.mark.asyncio
    async def test_staleness_warning_logged_once(self):
        """Test that staleness warning is logged only once"""
        monitor = UnifiedPriceMonitor()
        monitor.staleness_threshold_seconds = 0.5

        # Simulate stale price
        monitor.last_update_time['TESTUSDT'] = time.time() - 10

        # First check - should log warning
        await monitor.check_staleness(['TESTUSDT'])
        assert 'TESTUSDT' in monitor.staleness_warnings_logged

        # Second check - should not log again
        initial_warnings = len(monitor.staleness_warnings_logged)
        await monitor.check_staleness(['TESTUSDT'])
        assert len(monitor.staleness_warnings_logged) == initial_warnings


class TestHealthMonitorIntegration:
    """Test integration with aged position monitor"""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self):
        """Test health check when all prices are fresh"""
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2

        # Mock components
        price_monitor = UnifiedPriceMonitor()

        # Simulate fresh prices for aged symbols
        await price_monitor.update_price('GIGAUSDT', Decimal('0.01671'))
        await price_monitor.update_price('ENAUSDT', Decimal('0.5'))

        # Create aged monitor with mocked aged_targets
        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.price_monitor = price_monitor
        monitor.aged_targets = {
            'GIGAUSDT': Mock(),
            'ENAUSDT': Mock()
        }

        # Check health
        health = await monitor.check_websocket_health()

        assert health['healthy']
        assert health['aged_count'] == 2
        assert health['stale_count'] == 0

    @pytest.mark.asyncio
    async def test_health_check_detects_stale(self):
        """Test health check detects stale prices"""
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2

        price_monitor = UnifiedPriceMonitor()
        price_monitor.staleness_threshold_seconds = 1

        # One fresh, one stale
        await price_monitor.update_price('GIGAUSDT', Decimal('0.01671'))
        price_monitor.last_update_time['ENAUSDT'] = time.time() - 10

        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.price_monitor = price_monitor
        monitor.aged_targets = {
            'GIGAUSDT': Mock(),
            'ENAUSDT': Mock()
        }

        # Check health
        health = await monitor.check_websocket_health()

        assert not health['healthy']
        assert health['aged_count'] == 2
        assert health['stale_count'] == 1
        assert 'ENAUSDT' in health['stale_symbols']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
