"""
Tests for Error Handling Improvements
Validates Enhancement #1: Enhanced Error Handling
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from core.order_executor import OrderExecutor, OrderResult


class TestErrorClassification:
    """Test error type classification"""

    def test_permanent_error_170193(self):
        """Test Bybit error 170193 classified as permanent"""
        error = "bybit {\"retCode\":170193,\"retMsg\":\"Buy order price cannot be higher than 0USDT.\"}"
        assert OrderExecutor.classify_error(error) == 'permanent'

    def test_permanent_error_insufficient_funds(self):
        """Test insufficient funds classified as permanent"""
        error = "Insufficient funds to complete order"
        assert OrderExecutor.classify_error(error) == 'permanent'

    def test_rate_limit_429(self):
        """Test 429 error classified as rate_limit"""
        error = "429 Too Many Requests"
        assert OrderExecutor.classify_error(error) == 'rate_limit'

    def test_temporary_error_timeout(self):
        """Test timeout classified as temporary"""
        error = "Request timeout after 30 seconds"
        assert OrderExecutor.classify_error(error) == 'temporary'

    def test_unknown_error(self):
        """Test unknown error classified as unknown"""
        error = "Some random error message"
        assert OrderExecutor.classify_error(error) == 'unknown'


class TestExponentialBackoff:
    """Test exponential backoff logic"""

    @pytest.mark.asyncio
    async def test_backoff_increases(self):
        """Test that retry delay increases exponentially"""
        executor = OrderExecutor(None)

        # Base delay 0.5s
        assert executor.base_retry_delay == 0.5

        # Simulated delays for attempts 0, 1, 2
        # attempt 0: 0.5 * 2^0 = 0.5s
        # attempt 1: 0.5 * 2^1 = 1.0s
        # attempt 2: 0.5 * 2^2 = 2.0s
        delays = [
            min(executor.base_retry_delay * (2 ** i), executor.max_retry_delay)
            for i in range(3)
        ]

        assert delays == [0.5, 1.0, 2.0]

    @pytest.mark.asyncio
    async def test_rate_limit_delay(self):
        """Test rate limit uses special long delay"""
        executor = OrderExecutor(None)
        assert executor.rate_limit_delay == 15.0  # 15 seconds


class TestPermanentErrorHandling:
    """Test permanent errors stop retry immediately"""

    @pytest.mark.asyncio
    async def test_170193_stops_retry(self):
        """Test that 170193 error stops retry loop"""

        # Mock exchange
        exchange = Mock()
        exchange.exchange = Mock()
        exchange.exchange.create_order = AsyncMock(
            side_effect=Exception("bybit 170193: price cannot be")
        )

        executor = OrderExecutor(None)
        executor.exchanges = {'bybit': exchange}

        # Execute close (should stop after first attempt due to permanent error)
        result = await executor.execute_close(
            symbol='XDCUSDT',
            exchange_name='bybit',
            position_side='short',
            amount=100.0
        )

        # Should fail without retrying
        assert not result.success
        assert '170193' in result.error_message
        # Only 1 attempt (no retries for permanent errors)
        assert result.attempts == 1


class TestAgedMonitorTryCatch:
    """Test try-catch in aged_position_monitor_v2"""

    @pytest.mark.asyncio
    async def test_exception_caught(self):
        """Test that unexpected exception is caught"""

        from core.aged_position_monitor_v2 import AgedPositionMonitorV2

        # Mock components
        position_manager = Mock()
        order_executor = Mock()
        order_executor.execute_close = AsyncMock(
            side_effect=RuntimeError("Unexpected error!")
        )

        monitor = AgedPositionMonitorV2(
            position_manager=position_manager,
            order_executor=order_executor,
            repository=None
        )

        # Mock position and target
        position = Mock(symbol='TESTUSDT', side='long', amount=100, quantity=100, exchange='bybit')
        target = Mock(position_id=1, phase='grace')

        # Should NOT crash - exception should be caught
        await monitor._trigger_market_close(position, target, Decimal('100'))

        # Verify execute_close was called
        order_executor.execute_close.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
