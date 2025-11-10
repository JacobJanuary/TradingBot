"""
Unit tests for StopLossManager TS-awareness fixes.

Tests Fix #1: TS-Awareness for stop_loss_manager
- Test constructor accepts position_manager parameter
- Test _is_trailing_stop_active() detection logic
- Test set_stop_loss() skips SL recreation when TS active
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from decimal import Decimal

from core.stop_loss_manager import StopLossManager
from protection.trailing_stop import TrailingStopState


class TestStopLossManagerTSAwareness:
    """Test TS-awareness features added to StopLossManager."""

    @pytest.fixture
    def mock_exchange(self):
        """Mock CCXT exchange instance."""
        exchange = Mock()
        exchange.fetch_positions = AsyncMock(return_value=[])
        exchange.fetch_open_orders = AsyncMock(return_value=[])
        exchange.create_order = AsyncMock(return_value={'id': '12345'})
        exchange.cancel_order = AsyncMock()
        return exchange

    @pytest.fixture
    def mock_position_manager(self):
        """Mock PositionManager with trailing_managers."""
        pm = Mock()
        pm.trailing_managers = {}
        pm.positions = {}
        return pm

    def test_constructor_accepts_position_manager(self, mock_exchange):
        """Test #1.1: Constructor accepts position_manager parameter."""
        pm = Mock()

        # Should accept position_manager parameter
        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance',
            position_manager=pm
        )

        assert sl_manager.position_manager is pm
        assert sl_manager.exchange_name == 'binance'

    def test_constructor_defaults_to_none(self, mock_exchange):
        """Test #1.1: Constructor defaults position_manager to None."""
        # Should work without position_manager (backward compatibility)
        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance'
        )

        assert sl_manager.position_manager is None
        assert sl_manager.exchange_name == 'binance'

    @pytest.mark.asyncio
    async def test_is_trailing_stop_active_no_position_manager(self, mock_exchange):
        """Test #1.2: _is_trailing_stop_active returns False if no position_manager."""
        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance',
            position_manager=None  # No PM
        )

        result = await sl_manager._is_trailing_stop_active('BTCUSDT')

        assert result is False

    @pytest.mark.asyncio
    async def test_is_trailing_stop_active_via_trailing_manager(self, mock_exchange, mock_position_manager):
        """Test #1.2: _is_trailing_stop_active detects TS via trailing_manager."""
        # Setup trailing manager with active TS
        mock_ts_instance = Mock()
        mock_ts_instance.state = TrailingStopState.ACTIVE
        mock_ts_instance.current_stop_price = Decimal('50000')

        mock_trailing_manager = Mock()
        mock_trailing_manager.trailing_stops = {
            'BTCUSDT': mock_ts_instance
        }

        mock_position_manager.trailing_managers = {
            'binance': mock_trailing_manager
        }

        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance',
            position_manager=mock_position_manager
        )

        result = await sl_manager._is_trailing_stop_active('BTCUSDT')

        assert result is True

    @pytest.mark.asyncio
    async def test_is_trailing_stop_active_via_position_flags(self, mock_exchange, mock_position_manager):
        """Test #1.2: _is_trailing_stop_active detects TS via position flags (fallback)."""
        # No trailing manager, but position has TS flags
        mock_position = Mock()
        mock_position.has_trailing_stop = True
        mock_position.trailing_activated = True

        mock_position_manager.trailing_managers = {}  # No trailing manager
        mock_position_manager.positions = {
            'BTCUSDT': mock_position
        }

        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance',
            position_manager=mock_position_manager
        )

        result = await sl_manager._is_trailing_stop_active('BTCUSDT')

        assert result is True

    @pytest.mark.asyncio
    async def test_is_trailing_stop_active_ts_not_active(self, mock_exchange, mock_position_manager):
        """Test #1.2: _is_trailing_stop_active returns False when TS exists but not active."""
        # TS exists but state is MONITORING (not ACTIVE)
        mock_ts_instance = Mock()
        mock_ts_instance.state = TrailingStopState.MONITORING  # Not ACTIVE

        mock_trailing_manager = Mock()
        mock_trailing_manager.trailing_stops = {
            'BTCUSDT': mock_ts_instance
        }

        mock_position_manager.trailing_managers = {
            'binance': mock_trailing_manager
        }

        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance',
            position_manager=mock_position_manager
        )

        result = await sl_manager._is_trailing_stop_active('BTCUSDT')

        assert result is False

    @pytest.mark.asyncio
    async def test_set_stop_loss_skips_when_ts_active(self, mock_exchange, mock_position_manager):
        """Test #1.3: set_stop_loss skips SL recreation when TS active."""
        # Setup active TS
        mock_ts_instance = Mock()
        mock_ts_instance.state = TrailingStopState.ACTIVE

        mock_trailing_manager = Mock()
        mock_trailing_manager.trailing_stops = {
            'BTCUSDT': mock_ts_instance
        }

        mock_position_manager.trailing_managers = {
            'binance': mock_trailing_manager
        }

        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance',
            position_manager=mock_position_manager
        )

        # Mock has_stop_loss to return True (SL exists)
        sl_manager.has_stop_loss = AsyncMock(return_value=(True, '50000'))

        # Call set_stop_loss
        result = await sl_manager.set_stop_loss(
            symbol='BTCUSDT',
            stop_price=Decimal('49000'),
            side='BUY'
        )

        # Should return early with ts_active status
        assert result['status'] == 'ts_active'
        assert 'Trailing Stop active' in result['reason']

        # Should NOT have called create_order (no SL created)
        mock_exchange.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_stop_loss_proceeds_when_no_ts(self, mock_exchange, mock_position_manager):
        """Test #1.3: set_stop_loss proceeds normally when TS not active."""
        # No active TS
        mock_position_manager.trailing_managers = {}
        mock_position_manager.positions = {}

        sl_manager = StopLossManager(
            exchange=mock_exchange,
            exchange_name='binance',
            position_manager=mock_position_manager
        )

        # Mock has_stop_loss to return False (no SL)
        sl_manager.has_stop_loss = AsyncMock(return_value=(False, None))

        # Mock create_stop_loss_order to succeed
        mock_exchange.create_order.return_value = {
            'id': 'order_12345',
            'stopPrice': '49000',
            'status': 'NEW'
        }

        # Call set_stop_loss
        result = await sl_manager.set_stop_loss(
            symbol='BTCUSDT',
            stop_price=Decimal('49000'),
            side='BUY'
        )

        # Should proceed to create SL order
        assert result['status'] == 'success'

        # Should have called create_order
        mock_exchange.create_order.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
