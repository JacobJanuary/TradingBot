"""
Unit tests for ExchangeManager position lookup with position_manager integration

Tests the fix for SOONUSDT issue where exchange_manager.self.positions
was empty, causing database fallback with stale data.

Solution: Use position_manager.positions (real-time WebSocket data)
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass
from typing import Optional

# Import classes
import sys
sys.path.insert(0, '/home/elcrypto/TradingBot')

from core.exchange_manager import ExchangeManager
from core.position_manager import PositionState


@dataclass
class MockRepository:
    """Mock repository for testing"""
    async def get_open_position(self, symbol: str, exchange: str):
        # Return None by default (no DB fallback)
        return None


class TestPositionLookupWithPositionManager:
    """Test suite for position lookup using position_manager"""

    @pytest.fixture
    def exchange_manager(self):
        """Create ExchangeManager with mocked dependencies"""
        config = {
            'api_key': 'test',
            'api_secret': 'test',
            'testnet': True
        }

        em = ExchangeManager('binance', config, repository=None, position_manager=None)

        # Mock exchange methods
        em.exchange = Mock()
        em.exchange.create_order = AsyncMock(return_value={'id': '12345', 'status': 'NEW'})
        em.exchange.cancel_order = AsyncMock(return_value={'status': 'CANCELED'})
        em.exchange.fetch_open_orders = AsyncMock(return_value=[
            {
                'id': '999',
                'symbol': 'SOON/USDT:USDT',
                'type': 'STOP_MARKET',
                'side': 'SELL',
                'stopPrice': 1.9113,
                'info': {'reduceOnly': True}
            }
        ])

        # Mock rate limiter - must await async functions
        async def execute_mock(fn, *args, **kwargs):
            return await fn(*args, **kwargs)

        em.rate_limiter = Mock()
        em.rate_limiter.execute_request = AsyncMock(side_effect=execute_mock)

        return em

    @pytest.fixture
    def mock_position_manager(self):
        """Create mock PositionManager with positions dict"""
        pm = Mock()
        pm.positions = {}
        return pm

    # ========================================
    # Test 1: Position Found in position_manager (HAPPY PATH)
    # ========================================
    @pytest.mark.asyncio
    async def test_priority1_position_found_in_position_manager(self, exchange_manager, mock_position_manager):
        """
        Test: Position exists in position_manager.positions with quantity > 0
        Expected: Use position_manager data, NO API call, NO DB fallback
        """
        # Setup
        exchange_manager.position_manager = mock_position_manager

        # Add position to position_manager
        mock_position_manager.positions['SOONUSDT'] = PositionState(
            id=548,
            symbol='SOONUSDT',
            exchange='binance',
            side='long',
            quantity=Decimal('4.0'),
            entry_price=Decimal('2.03332500'),
            current_price=Decimal('2.06801642'),
            unrealized_pnl=Decimal('0.1388'),
            unrealized_pnl_percent=1.71
        )

        # Mock fetch_positions to verify it's NOT called
        exchange_manager.fetch_positions = AsyncMock(side_effect=AssertionError("fetch_positions should NOT be called"))

        # Execute
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='SOONUSDT',
            new_sl_price=2.05974435,
            position_side='long'
        )

        # Assert
        assert result['success'] is True, f"Expected success, got: {result}"
        # Note: lookup_method might not be in result dict, that's OK
        # Key assertion: create_order was called with correct amount

        # Verify create_order called with correct amount
        create_call = exchange_manager.exchange.create_order.call_args
        assert create_call is not None, "create_order should be called"
        assert create_call[1]['amount'] == 4.0, f"Expected amount=4.0, got {create_call[1]['amount']}"

    # ========================================
    # Test 2: Position Closed (quantity=0) in position_manager
    # ========================================
    @pytest.mark.asyncio
    async def test_priority1_position_closed_in_position_manager(self, exchange_manager, mock_position_manager):
        """
        Test: Position exists in position_manager but quantity=0 (closed)
        Expected: ABORT immediately, NO API call, NO DB fallback
        """
        # Setup
        exchange_manager.position_manager = mock_position_manager

        # Add closed position
        mock_position_manager.positions['SOONUSDT'] = PositionState(
            id=548,
            symbol='SOONUSDT',
            exchange='binance',
            side='long',
            quantity=Decimal('0.0'),  # ← CLOSED
            entry_price=Decimal('2.03332500'),
            current_price=Decimal('2.06801642'),
            unrealized_pnl=Decimal('0.0'),
            unrealized_pnl_percent=0.0
        )

        # Mock fetch_positions to verify NOT called
        exchange_manager.fetch_positions = AsyncMock(side_effect=AssertionError("Should NOT call API"))

        # Execute
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='SOONUSDT',
            new_sl_price=2.05974435,
            position_side='long'
        )

        # Assert
        assert result['success'] is False, "Should fail (position closed)"
        assert result.get('error') == 'position_closed_realtime', f"Expected position_closed_realtime, got {result.get('error')}"
        assert 'quantity=0' in result.get('message', '').lower() or 'closed' in result.get('message', '').lower()

        # Verify create_order NOT called
        assert exchange_manager.exchange.create_order.call_count == 0, "Should NOT create order for closed position"

    # ========================================
    # Test 3: Position NOT in position_manager, fallback to API
    # ========================================
    @pytest.mark.asyncio
    async def test_priority2_fallback_to_exchange_api(self, exchange_manager, mock_position_manager):
        """
        Test: Position NOT in position_manager (cache miss)
        Expected: Fallback to Exchange API, find position there
        """
        # Setup
        exchange_manager.position_manager = mock_position_manager
        mock_position_manager.positions = {}  # Empty (cache miss)

        # Mock fetch_positions to return position
        exchange_manager.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'SOONUSDT',
                'side': 'long',
                'contracts': 4.0,
                'entryPrice': 2.03332500,
                'markPrice': 2.06801642
            }
        ])

        # Execute
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='SOONUSDT',
            new_sl_price=2.05974435,
            position_side='long'
        )

        # Assert
        assert result['success'] is True
        # Verify fetch_positions WAS called
        assert exchange_manager.fetch_positions.call_count >= 1, "fetch_positions should be called"

    # ========================================
    # Test 4: No position_manager (backward compatibility)
    # ========================================
    @pytest.mark.asyncio
    async def test_backward_compat_no_position_manager(self, exchange_manager):
        """
        Test: ExchangeManager without position_manager (old scripts)
        Expected: Skip Priority 1, fallback to Exchange API
        """
        # Setup
        exchange_manager.position_manager = None  # No position_manager

        # Mock fetch_positions
        exchange_manager.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'SOONUSDT',
                'side': 'long',
                'contracts': 4.0,
                'entryPrice': 2.03332500,
                'markPrice': 2.06801642
            }
        ])

        # Execute
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='SOONUSDT',
            new_sl_price=2.05974435,
            position_side='long'
        )

        # Assert
        assert result['success'] is True
        assert exchange_manager.fetch_positions.call_count >= 1, "Should fallback to API"

    # ========================================
    # Test 5: Database Fallback - Bot Restart Scenario
    # ========================================
    @pytest.mark.asyncio
    async def test_priority3_database_fallback_on_restart(self, exchange_manager, mock_position_manager):
        """
        Test: Bot restart - position NOT in position_manager, API fails, use DB
        Expected: Database fallback used
        """
        # Setup
        exchange_manager.position_manager = mock_position_manager
        mock_position_manager.positions = {}  # Empty (restart)

        # Mock repository
        mock_repo = MockRepository()
        async def mock_get_open_position(symbol, exchange):
            return {
                'symbol': symbol,
                'status': 'active',
                'quantity': 4.0,
                'side': 'long'
            }
        mock_repo.get_open_position = mock_get_open_position
        exchange_manager.repository = mock_repo

        # Mock fetch_positions to return empty (API glitch)
        exchange_manager.fetch_positions = AsyncMock(return_value=[])

        # Execute
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='SOONUSDT',
            new_sl_price=2.05974435,
            position_side='long'
        )

        # Assert
        assert result['success'] is True

    # ========================================
    # Test 6: Database Fallback BLOCKED - Position in position_manager
    # ========================================
    @pytest.mark.asyncio
    async def test_database_fallback_blocked_when_in_position_manager(self, exchange_manager, mock_position_manager):
        """
        Test: Position in position_manager but API fails
        Expected: Use position_manager, NO database fallback

        This is the SOONUSDT fix - position in position_manager means
        it's active, don't use potentially stale DB data
        """
        # Setup
        exchange_manager.position_manager = mock_position_manager

        # Position in position_manager
        mock_position_manager.positions['SOONUSDT'] = PositionState(
            id=548,
            symbol='SOONUSDT',
            exchange='binance',
            side='long',
            quantity=Decimal('4.0'),
            entry_price=Decimal('2.03332500'),
            current_price=Decimal('2.06801642'),
            unrealized_pnl=Decimal('0.1388'),
            unrealized_pnl_percent=1.71
        )

        # Mock repository with WRONG data (stale)
        mock_repo = MockRepository()
        async def mock_get_open_position_stale(symbol, exchange):
            return {
                'symbol': symbol,
                'status': 'active',
                'quantity': 1216.0,  # ← STALE/WRONG data
                'side': 'long'
            }
        mock_repo.get_open_position = mock_get_open_position_stale
        exchange_manager.repository = mock_repo

        # Execute
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='SOONUSDT',
            new_sl_price=2.05974435,
            position_side='long'
        )

        # Assert
        assert result['success'] is True

        # Verify amount is 4.0 (from position_manager), NOT 1216.0 (from DB)
        create_call = exchange_manager.exchange.create_order.call_args
        assert create_call[1]['amount'] == 4.0, f"Should use position_manager amount (4.0), not DB amount (1216.0)"

    # ========================================
    # Test 7: Decimal to Float Conversion
    # ========================================
    @pytest.mark.asyncio
    async def test_decimal_to_float_conversion(self, exchange_manager, mock_position_manager):
        """
        Test: PositionState.quantity is Decimal, ensure correct float conversion
        Expected: Decimal('4.0') → 4.0 (float) without precision loss
        """
        # Setup
        exchange_manager.position_manager = mock_position_manager

        # Test various Decimal values
        test_cases = [
            Decimal('4.0'),
            Decimal('1216.0'),
            Decimal('0.5'),
            Decimal('123.456'),
        ]

        for qty in test_cases:
            mock_position_manager.positions['TESTUSDT'] = PositionState(
                id=1,
                symbol='TESTUSDT',
                exchange='binance',
                side='long',
                quantity=qty,
                entry_price=Decimal('100.0'),
                current_price=Decimal('100.0'),
                unrealized_pnl=Decimal('0.0'),
                unrealized_pnl_percent=0.0
            )

            result = await exchange_manager._binance_update_sl_optimized(
                symbol='TESTUSDT',
                new_sl_price=95.0,
                position_side='long'
            )

            assert result['success'] is True
            create_call = exchange_manager.exchange.create_order.call_args
            assert create_call[1]['amount'] == float(qty), f"Decimal {qty} → float conversion failed"

    # ========================================
    # Test 8: Position Not Found Anywhere (ABORT)
    # ========================================
    @pytest.mark.asyncio
    async def test_abort_position_not_found_anywhere(self, exchange_manager, mock_position_manager):
        """
        Test: Position not found in position_manager, API, or DB
        Expected: ABORT with error
        """
        # Setup
        exchange_manager.position_manager = mock_position_manager
        mock_position_manager.positions = {}

        # Mock fetch_positions to return empty
        exchange_manager.fetch_positions = AsyncMock(return_value=[])

        # Mock repository to return None
        mock_repo = MockRepository()
        exchange_manager.repository = mock_repo

        # Execute
        result = await exchange_manager._binance_update_sl_optimized(
            symbol='GHOSTUSDT',  # Non-existent position
            new_sl_price=1.0,
            position_side='long'
        )

        # Assert
        assert result['success'] is False
        assert result.get('error') == 'position_not_found_abort'
        assert exchange_manager.exchange.create_order.call_count == 0, "Should NOT create order"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
