#!/usr/bin/env python3
"""
Unit tests for placeholder filtering in protection check
Tests the fix for ENSOUSDT false positive issue
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from core.position_manager import PositionManager, PositionState


class TestPlaceholderProtectionCheck:
    """Test that placeholder positions are skipped in protection check"""

    def setup_method(self):
        """Setup test fixtures"""
        # Mock config
        self.mock_config = MagicMock()
        self.mock_config.stop_loss_percent = 4.0
        self.mock_config.max_open_positions = 10
        self.mock_config.trailing_activation_percent = 2.0
        self.mock_config.trailing_callback_percent = 0.5

        # Mock repository
        self.mock_repository = AsyncMock()

        # Mock exchange
        self.mock_exchange = AsyncMock()
        self.mock_exchange.name = 'binance'

        # Mock event router
        self.mock_event_router = MagicMock()

    @pytest.mark.asyncio
    async def test_placeholder_entry_price_zero_skipped(self):
        """Test placeholder with entry_price=0 is skipped"""
        # Create position manager
        pm = PositionManager(
            config=self.mock_config,
            repository=self.mock_repository,
            exchanges={'binance': self.mock_exchange},
            event_router=self.mock_event_router
        )

        # Add placeholder position (entry_price=0)
        pm.positions['BTCUSDT'] = PositionState(
            id='pending',
            symbol='BTCUSDT',
            exchange='binance',
            side='BUY',
            quantity=10.0,
            entry_price=0,  # PLACEHOLDER
            current_price=0,
            unrealized_pnl=0,
            unrealized_pnl_percent=0,
            opened_at=datetime.now(timezone.utc)
        )

        # Mock StopLossManager.has_stop_loss to track if it's called
        with patch('core.stop_loss_manager.StopLossManager') as mock_sl_manager_class:
            mock_sl_manager = AsyncMock()
            mock_sl_manager.has_stop_loss = AsyncMock(return_value=(False, None, None))
            mock_sl_manager_class.return_value = mock_sl_manager

            # Run protection check
            await pm.check_positions_protection()

            # CRITICAL: has_stop_loss should NOT be called for placeholder
            mock_sl_manager.has_stop_loss.assert_not_called()

    @pytest.mark.asyncio
    async def test_placeholder_quantity_zero_skipped(self):
        """Test placeholder with quantity=0 is skipped"""
        pm = PositionManager(
            config=self.mock_config,
            repository=self.mock_repository,
            exchanges={'binance': self.mock_exchange},
            event_router=self.mock_event_router
        )

        # Add placeholder position (quantity=0)
        pm.positions['ETHUSDT'] = PositionState(
            id='pending',
            symbol='ETHUSDT',
            exchange='binance',
            side='BUY',
            quantity=0,  # PLACEHOLDER
            entry_price=2500.0,
            current_price=0,
            unrealized_pnl=0,
            unrealized_pnl_percent=0,
            opened_at=datetime.now(timezone.utc)
        )

        # Mock StopLossManager.has_stop_loss
        with patch('core.stop_loss_manager.StopLossManager') as mock_sl_manager_class:
            mock_sl_manager = AsyncMock()
            mock_sl_manager.has_stop_loss = AsyncMock(return_value=(False, None, None))
            mock_sl_manager_class.return_value = mock_sl_manager

            # Run protection check
            await pm.check_positions_protection()

            # CRITICAL: has_stop_loss should NOT be called for placeholder
            mock_sl_manager.has_stop_loss.assert_not_called()

    @pytest.mark.asyncio
    async def test_real_position_is_checked(self):
        """Test real position (non-placeholder) IS checked"""
        pm = PositionManager(
            config=self.mock_config,
            repository=self.mock_repository,
            exchanges={'binance': self.mock_exchange},
            event_router=self.mock_event_router
        )

        # Add REAL position (entry_price > 0 and quantity > 0)
        pm.positions['SOLUSDT'] = PositionState(
            id='12345',
            symbol='SOLUSDT',
            exchange='binance',
            side='BUY',
            quantity=50.0,  # REAL
            entry_price=100.0,  # REAL
            current_price=105.0,
            unrealized_pnl=250.0,
            unrealized_pnl_percent=5.0,
            opened_at=datetime.now(timezone.utc)
        )

        # Mock StopLossManager.has_stop_loss
        with patch('core.stop_loss_manager.StopLossManager') as mock_sl_manager_class:
            mock_sl_manager = AsyncMock()
            # Return True (position has SL)
            mock_sl_manager.has_stop_loss = AsyncMock(return_value=(True, 96.0))
            mock_sl_manager_class.return_value = mock_sl_manager

            # Run protection check
            await pm.check_positions_protection()

            # CRITICAL: has_stop_loss SHOULD be called for real position
            mock_sl_manager.has_stop_loss.assert_called_once_with('SOLUSDT')

    @pytest.mark.asyncio
    async def test_no_api_call_for_placeholder(self):
        """Test no API call is made for placeholder positions"""
        pm = PositionManager(
            config=self.mock_config,
            repository=self.mock_repository,
            exchanges={'binance': self.mock_exchange},
            event_router=self.mock_event_router
        )

        # Add placeholder
        pm.positions['ENSUSDT'] = PositionState(
            id='pending',
            symbol='ENSUSDT',
            exchange='binance',
            side='BUY',
            quantity=0,  # PLACEHOLDER
            entry_price=0,  # PLACEHOLDER
            current_price=0,
            unrealized_pnl=0,
            unrealized_pnl_percent=0,
            opened_at=datetime.now(timezone.utc)
        )

        # Mock StopLossManager
        with patch('core.stop_loss_manager.StopLossManager') as mock_sl_manager_class:
            mock_sl_manager = AsyncMock()
            mock_sl_manager.has_stop_loss = AsyncMock(return_value=(False, None, None))
            mock_sl_manager_class.return_value = mock_sl_manager

            # Run protection check
            await pm.check_positions_protection()

            # Verify StopLossManager was NOT instantiated for placeholder
            # (it's only instantiated when we call has_stop_loss)
            assert mock_sl_manager.has_stop_loss.call_count == 0

    @pytest.mark.asyncio
    async def test_mixed_positions_only_real_checked(self):
        """Test that only real positions are checked, placeholders skipped"""
        pm = PositionManager(
            config=self.mock_config,
            repository=self.mock_repository,
            exchanges={'binance': self.mock_exchange},
            event_router=self.mock_event_router
        )

        # Add 2 placeholders + 1 real position
        pm.positions['PLACEHOLDER1'] = PositionState(
            id='pending',
            symbol='PLACEHOLDER1',
            exchange='binance',
            side='BUY',
            quantity=0,  # PLACEHOLDER
            entry_price=0,
            current_price=0,
            unrealized_pnl=0,
            unrealized_pnl_percent=0,
            opened_at=datetime.now(timezone.utc)
        )

        pm.positions['PLACEHOLDER2'] = PositionState(
            id='pending',
            symbol='PLACEHOLDER2',
            exchange='binance',
            side='BUY',
            quantity=10.0,
            entry_price=0,  # PLACEHOLDER
            current_price=0,
            unrealized_pnl=0,
            unrealized_pnl_percent=0,
            opened_at=datetime.now(timezone.utc)
        )

        pm.positions['REALUSDT'] = PositionState(
            id='67890',
            symbol='REALUSDT',
            exchange='binance',
            side='BUY',
            quantity=100.0,  # REAL
            entry_price=50.0,  # REAL
            current_price=51.0,
            unrealized_pnl=100.0,
            unrealized_pnl_percent=2.0,
            opened_at=datetime.now(timezone.utc)
        )

        # Mock StopLossManager
        with patch('core.stop_loss_manager.StopLossManager') as mock_sl_manager_class:
            mock_sl_manager = AsyncMock()
            mock_sl_manager.has_stop_loss = AsyncMock(return_value=(True, 48.0))
            mock_sl_manager_class.return_value = mock_sl_manager

            # Run protection check
            await pm.check_positions_protection()

            # CRITICAL: has_stop_loss called ONLY once (for REALUSDT)
            assert mock_sl_manager.has_stop_loss.call_count == 1
            mock_sl_manager.has_stop_loss.assert_called_with('REALUSDT')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
