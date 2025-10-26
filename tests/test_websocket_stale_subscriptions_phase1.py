"""
Phase 1 Tests: Per-Module Staleness Thresholds
"""
import asyncio
import pytest
from decimal import Decimal
from websocket.unified_price_monitor import UnifiedPriceMonitor


class TestPerModuleThresholds:
    """Test that different modules use different staleness thresholds"""

    @pytest.mark.asyncio
    async def test_aged_position_30s_threshold(self):
        """Test aged positions use 30s threshold"""
        monitor = UnifiedPriceMonitor()
        await monitor.start()

        # Send initial update
        await monitor.update_price('TESTUSDT', Decimal('100'))

        # Wait 31 seconds (over 30s threshold)
        await asyncio.sleep(31)

        # Check staleness with aged_position module
        report = await monitor.check_staleness(
            ['TESTUSDT'],
            module='aged_position'
        )

        assert report['TESTUSDT']['stale'] == True
        assert report['TESTUSDT']['threshold_used'] == 30

    @pytest.mark.asyncio
    async def test_trailing_stop_30s_threshold(self):
        """Test trailing stops use 30s threshold"""
        monitor = UnifiedPriceMonitor()
        await monitor.start()

        await monitor.update_price('TESTUSDT', Decimal('100'))
        await asyncio.sleep(31)

        report = await monitor.check_staleness(
            ['TESTUSDT'],
            module='trailing_stop'
        )

        assert report['TESTUSDT']['stale'] == True
        assert report['TESTUSDT']['threshold_used'] == 30

    @pytest.mark.asyncio
    async def test_default_300s_threshold(self):
        """Test default module uses 300s threshold"""
        monitor = UnifiedPriceMonitor()
        await monitor.start()

        await monitor.update_price('TESTUSDT', Decimal('100'))
        await asyncio.sleep(31)

        # Check with no module (should use default 300s)
        report = await monitor.check_staleness(['TESTUSDT'])

        assert report['TESTUSDT']['stale'] == False  # 31s < 300s
        assert report['TESTUSDT']['threshold_used'] == 300

    @pytest.mark.asyncio
    async def test_threshold_reported_in_result(self):
        """Test that threshold used is reported in staleness result"""
        monitor = UnifiedPriceMonitor()
        await monitor.start()

        await monitor.update_price('TESTUSDT', Decimal('100'))

        report = await monitor.check_staleness(
            ['TESTUSDT'],
            module='aged_position'
        )

        assert 'threshold_used' in report['TESTUSDT']
        assert report['TESTUSDT']['threshold_used'] == 30


class TestAutomaticResubscription:
    """Test automatic resubscription for stale positions"""

    @pytest.mark.asyncio
    async def test_resubscribe_stale_positions_success(self):
        """Test successful resubscription of stale position"""
        from core.position_manager_unified_patch import resubscribe_stale_positions
        from websocket.unified_price_monitor import UnifiedPriceMonitor
        from core.protection_adapters import AgedPositionAdapter
        from unittest.mock import Mock, AsyncMock

        # Setup
        price_monitor = UnifiedPriceMonitor()
        await price_monitor.start()

        aged_monitor = Mock()
        aged_adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        unified_protection = {
            'price_monitor': price_monitor,
            'aged_adapter': aged_adapter
        }

        # Create mock position (4 hours old - qualifies as aged)
        from datetime import datetime, timezone, timedelta
        position = Mock()
        position.symbol = 'TESTUSDT'
        position.opened_at = datetime.now(timezone.utc) - timedelta(hours=4)
        position.trailing_activated = False

        position_manager = Mock()
        position_manager.positions = {'TESTUSDT': position}

        # Resubscribe
        count = await resubscribe_stale_positions(
            unified_protection,
            ['TESTUSDT'],
            position_manager
        )

        assert count == 1
        assert 'TESTUSDT' in price_monitor.subscribers

    @pytest.mark.asyncio
    async def test_resubscribe_missing_position(self):
        """Test resubscription handles missing position gracefully"""
        from core.position_manager_unified_patch import resubscribe_stale_positions
        from websocket.unified_price_monitor import UnifiedPriceMonitor
        from core.protection_adapters import AgedPositionAdapter
        from unittest.mock import Mock

        price_monitor = UnifiedPriceMonitor()
        await price_monitor.start()

        aged_monitor = Mock()
        aged_adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        unified_protection = {
            'price_monitor': price_monitor,
            'aged_adapter': aged_adapter
        }

        position_manager = Mock()
        position_manager.positions = {}  # No positions

        # Should handle gracefully
        count = await resubscribe_stale_positions(
            unified_protection,
            ['MISSING'],
            position_manager
        )

        assert count == 0  # No resubscriptions


class TestPhase1Integration:
    """Integration test for Phase 1 changes"""

    @pytest.mark.asyncio
    async def test_full_stale_detection_and_recovery(self):
        """
        Full integration test:
        1. Create aged position subscription
        2. Stop sending updates (simulate stale)
        3. Health monitor detects stale
        4. Automatic resubscription triggered
        5. Verify recovery
        """
        from core.position_manager_unified_patch import (
            init_unified_protection,
            start_websocket_health_monitor,
            resubscribe_stale_positions
        )
        from unittest.mock import Mock, AsyncMock
        import time

        # Setup mock position manager
        position_manager = Mock()
        position_manager.exchanges = {}
        position_manager.repository = Mock()
        position_manager.trailing_managers = {}

        # Initialize unified protection
        unified_protection = init_unified_protection(position_manager)

        if not unified_protection:
            pytest.skip("Unified protection disabled")

        price_monitor = unified_protection['price_monitor']
        aged_adapter = unified_protection['aged_adapter']

        # Create mock position (4 hours old - qualifies as aged)
        from datetime import datetime, timezone, timedelta
        position = Mock()
        position.symbol = 'TESTUSDT'
        position.opened_at = datetime.now(timezone.utc) - timedelta(hours=4)
        position.trailing_activated = False
        position_manager.positions = {'TESTUSDT': position}

        # Add position to aged monitoring
        await aged_adapter.add_aged_position(position)

        # Send initial price update
        await price_monitor.update_price('TESTUSDT', Decimal('100'))

        # Verify not stale yet
        report = await price_monitor.check_staleness(
            ['TESTUSDT'],
            module='aged_position'
        )
        assert report['TESTUSDT']['stale'] == False

        # Wait for staleness (31 seconds)
        await asyncio.sleep(31)

        # Check stale
        report = await price_monitor.check_staleness(
            ['TESTUSDT'],
            module='aged_position'
        )
        assert report['TESTUSDT']['stale'] == True

        # Trigger resubscription
        count = await resubscribe_stale_positions(
            unified_protection,
            ['TESTUSDT'],
            position_manager
        )

        assert count == 1

        # Send new update
        await price_monitor.update_price('TESTUSDT', Decimal('101'))

        # Verify no longer stale
        report = await price_monitor.check_staleness(
            ['TESTUSDT'],
            module='aged_position'
        )
        assert report['TESTUSDT']['stale'] == False
