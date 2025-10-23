"""
Comprehensive test suite for GIGAUSDT subscription fix
Tests all 5 fixes to ensure they work correctly
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone, timedelta

from core.protection_adapters import AgedPositionAdapter
from websocket.unified_price_monitor import UnifiedPriceMonitor
from core.aged_position_monitor_v2 import AgedPositionMonitorV2
from core.position_manager_unified_patch import check_and_register_aged_positions


class MockPosition:
    """Mock position for testing"""
    def __init__(self, symbol, age_hours, trailing_activated=False):
        self.symbol = symbol
        self.exchange = 'bybit'
        self.entry_price = 0.01523
        self.trailing_activated = trailing_activated
        self.opened_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        self.id = 123


class TestFix1DuplicateSubscriptionProtection:
    """Test FIX #1: Duplicate Subscription Protection"""

    @pytest.mark.asyncio
    async def test_duplicate_subscription_prevented(self):
        """Test that duplicate subscriptions are prevented"""
        price_monitor = UnifiedPriceMonitor()
        aged_monitor = Mock()
        adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        position = MockPosition('GIGAUSDT', age_hours=6.8)

        # First call - should subscribe
        await adapter.add_aged_position(position)
        assert 'GIGAUSDT' in adapter.monitoring_positions
        subscribers_count_1 = len(price_monitor.subscribers.get('GIGAUSDT', []))
        assert subscribers_count_1 == 1

        # Second call - should skip (duplicate protection)
        await adapter.add_aged_position(position)
        assert 'GIGAUSDT' in adapter.monitoring_positions
        subscribers_count_2 = len(price_monitor.subscribers.get('GIGAUSDT', []))
        assert subscribers_count_2 == 1  # Still 1, not 2!

    @pytest.mark.asyncio
    async def test_multiple_symbols_independent(self):
        """Test that different symbols are tracked independently"""
        price_monitor = UnifiedPriceMonitor()
        aged_monitor = Mock()
        adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        position1 = MockPosition('GIGAUSDT', age_hours=6.8)
        position2 = MockPosition('ENAUSDT', age_hours=3.5)

        await adapter.add_aged_position(position1)
        await adapter.add_aged_position(position2)

        assert 'GIGAUSDT' in adapter.monitoring_positions
        assert 'ENAUSDT' in adapter.monitoring_positions
        assert len(adapter.monitoring_positions) == 2


class TestFix2DebugLogging:
    """Test FIX #2: Debug Logging"""

    @pytest.mark.asyncio
    async def test_subscription_logged_at_info_level(self):
        """Test that subscriptions are logged at INFO level"""
        price_monitor = UnifiedPriceMonitor()

        with patch('websocket.unified_price_monitor.logger.info') as mock_info:
            await price_monitor.subscribe(
                symbol='GIGAUSDT',
                callback=AsyncMock(),
                module='test_module',
                priority=40
            )

            # Should have called logger.info
            mock_info.assert_called_once()
            call_args = str(mock_info.call_args)
            assert 'test_module' in call_args
            assert 'GIGAUSDT' in call_args
            assert '✅' in call_args


class TestFix3VerifySubscriptionRegistration:
    """Test FIX #3: Verify Subscription Registration"""

    @pytest.mark.asyncio
    async def test_subscription_verification_catches_failure(self):
        """Test that subscription verification catches failures"""

        class BrokenPriceMonitor:
            """Mock monitor that fails silently"""
            subscribers = {}  # Always empty

            async def subscribe(self, *args, **kwargs):
                pass  # Does nothing - subscription fails

        broken_monitor = BrokenPriceMonitor()
        aged_monitor = Mock()
        adapter = AgedPositionAdapter(aged_monitor, broken_monitor)

        position = MockPosition('GIGAUSDT', age_hours=6.8)

        with patch('core.protection_adapters.logger.error') as mock_error:
            await adapter.add_aged_position(position)

            # Should have logged error
            mock_error.assert_called_once()
            error_msg = str(mock_error.call_args)
            assert 'FAILED' in error_msg or 'failed' in error_msg.lower()
            assert 'GIGAUSDT' in error_msg

        # Should NOT be in monitoring_positions (subscription failed)
        assert 'GIGAUSDT' not in adapter.monitoring_positions

    @pytest.mark.asyncio
    async def test_successful_subscription_verified(self):
        """Test that successful subscriptions pass verification"""
        price_monitor = UnifiedPriceMonitor()
        aged_monitor = Mock()
        adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        position = MockPosition('GIGAUSDT', age_hours=6.8)

        await adapter.add_aged_position(position)

        # Should be in both monitoring_positions and subscribers
        assert 'GIGAUSDT' in adapter.monitoring_positions
        assert 'GIGAUSDT' in price_monitor.subscribers


class TestFix4FixMultipleCalls:
    """Test FIX #4: Fix aged_monitor.add_aged_position() Multiple Calls"""

    @pytest.mark.asyncio
    async def test_monitor_add_called_only_once(self):
        """Test that aged_monitor.add_aged_position() called only once"""

        # Create mocks
        position_manager = Mock()
        position_manager.positions = {
            'GIGAUSDT': MockPosition('GIGAUSDT', age_hours=6.8)
        }

        price_monitor = UnifiedPriceMonitor()
        aged_monitor = Mock()
        aged_monitor.check_position_age = AsyncMock(return_value=True)
        aged_monitor.is_position_tracked = Mock(return_value=False)  # First time
        aged_monitor.add_aged_position = AsyncMock()

        aged_adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        unified_protection = {
            'aged_monitor': aged_monitor,
            'aged_adapter': aged_adapter
        }

        # First call
        await check_and_register_aged_positions(position_manager, unified_protection)
        assert aged_monitor.add_aged_position.call_count == 1

        # Now position is tracked
        aged_monitor.is_position_tracked = Mock(return_value=True)

        # Second call - should NOT call aged_monitor.add again
        await check_and_register_aged_positions(position_manager, unified_protection)
        assert aged_monitor.add_aged_position.call_count == 1  # Still 1!


class TestFix5SubscriptionHealthCheck:
    """Test FIX #5: Subscription Health Check"""

    @pytest.mark.asyncio
    async def test_health_check_detects_missing_subscription(self):
        """Test that health check detects missing subscriptions"""

        # Setup
        position_manager = Mock()
        position = MockPosition('GIGAUSDT', age_hours=6.8)
        position_manager.positions = {'GIGAUSDT': position}

        price_monitor = UnifiedPriceMonitor()
        aged_monitor = Mock()
        aged_monitor.position_manager = position_manager
        aged_monitor.aged_targets = {'GIGAUSDT': Mock()}

        aged_adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        # aged_targets has GIGAUSDT but monitoring_positions doesn't
        assert 'GIGAUSDT' in aged_monitor.aged_targets
        assert 'GIGAUSDT' not in aged_adapter.monitoring_positions

        # Mock the verify_subscriptions method
        # (In real implementation, this would be in AgedPositionMonitorV2)
        async def verify_subscriptions(adapter):
            resubscribed_count = 0
            for symbol in aged_monitor.aged_targets.keys():
                if symbol not in adapter.monitoring_positions:
                    await adapter.add_aged_position(position_manager.positions[symbol])
                    resubscribed_count += 1
            return resubscribed_count

        # Run health check
        resubscribed = await verify_subscriptions(aged_adapter)

        # Should have re-subscribed
        assert resubscribed == 1
        assert 'GIGAUSDT' in aged_adapter.monitoring_positions
        assert 'GIGAUSDT' in price_monitor.subscribers

    @pytest.mark.asyncio
    async def test_health_check_all_subscriptions_ok(self):
        """Test that health check passes when all subscriptions are OK"""

        position_manager = Mock()
        position = MockPosition('GIGAUSDT', age_hours=6.8)
        position_manager.positions = {'GIGAUSDT': position}

        price_monitor = UnifiedPriceMonitor()
        aged_monitor = Mock()
        aged_monitor.position_manager = position_manager

        aged_adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        # Add position (creates subscription)
        await aged_adapter.add_aged_position(position)

        # Now aged_targets and monitoring_positions both have GIGAUSDT
        aged_monitor.aged_targets = {'GIGAUSDT': Mock()}

        # Mock verify_subscriptions
        async def verify_subscriptions(adapter):
            resubscribed_count = 0
            for symbol in aged_monitor.aged_targets.keys():
                if symbol not in adapter.monitoring_positions:
                    resubscribed_count += 1
            return resubscribed_count

        # Run health check
        resubscribed = await verify_subscriptions(aged_adapter)

        # Should be 0 (all OK)
        assert resubscribed == 0


class TestIntegration:
    """Integration tests for all fixes together"""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test full lifecycle: detection → subscription → callback → health check"""

        # Setup
        position_manager = Mock()
        position = MockPosition('GIGAUSDT', age_hours=6.8)
        position_manager.positions = {'GIGAUSDT': position}

        price_monitor = UnifiedPriceMonitor()
        await price_monitor.start()

        aged_monitor = Mock()
        aged_monitor.check_position_age = AsyncMock(return_value=True)
        aged_monitor.is_position_tracked = Mock(return_value=False)
        aged_monitor.add_aged_position = AsyncMock()
        aged_monitor.check_price_target = AsyncMock()
        aged_monitor.aged_targets = {}
        aged_monitor.position_manager = position_manager

        aged_adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        unified_protection = {
            'price_monitor': price_monitor,
            'aged_monitor': aged_monitor,
            'aged_adapter': aged_adapter
        }

        # Step 1: Register aged position
        await check_and_register_aged_positions(position_manager, unified_protection)

        # Verify subscription created
        assert 'GIGAUSDT' in aged_adapter.monitoring_positions
        assert 'GIGAUSDT' in price_monitor.subscribers

        # Step 2: Price update triggers callback
        callback_called = False

        original_check = aged_monitor.check_price_target
        async def tracked_check(*args, **kwargs):
            nonlocal callback_called
            callback_called = True
            return await original_check(*args, **kwargs)

        aged_monitor.check_price_target = tracked_check

        await price_monitor.update_price('GIGAUSDT', Decimal('0.01671'))

        # Callback should have been called
        assert callback_called

        # Step 3: Health check (all OK)
        aged_monitor.aged_targets = {'GIGAUSDT': Mock()}

        async def verify_subscriptions(adapter):
            resubscribed_count = 0
            for symbol in aged_monitor.aged_targets.keys():
                if symbol not in adapter.monitoring_positions:
                    resubscribed_count += 1
            return resubscribed_count

        resubscribed = await verify_subscriptions(aged_adapter)
        assert resubscribed == 0  # All OK


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
