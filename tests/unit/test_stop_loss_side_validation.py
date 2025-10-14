"""
Unit tests for Stop Loss side validation (Fix #3)

Tests verify that has_stop_loss() correctly validates
order side matches position side.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from core.stop_loss_manager import StopLossManager


class TestStopLossSideValidation:
    """Test side validation in has_stop_loss()"""

    @pytest.fixture
    def sl_manager(self):
        """Create StopLossManager instance with mocked exchange"""
        mock_exchange = Mock()
        mock_exchange.fetch_positions = AsyncMock(return_value=[])
        mock_exchange.fetch_open_orders = AsyncMock(return_value=[])

        manager = StopLossManager(mock_exchange, 'binance')
        return manager

    @pytest.mark.asyncio
    async def test_long_position_with_sell_sl_order(self, sl_manager):
        """
        SCENARIO: LONG position has SELL stop loss order
        EXPECTED: Should recognize as valid SL
        """
        # Mock fetch_open_orders to return SELL stop order
        sl_manager.exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    'id': '12345',
                    'type': 'stop_market',
                    'side': 'sell',  # Correct for LONG
                    'stopPrice': 49000.0,
                    'reduceOnly': True,
                    'info': {}
                }
            ]
        )

        # Call with position_side='long'
        has_sl, sl_price = await sl_manager.has_stop_loss('BTC/USDT:USDT', position_side='long')

        # Should recognize as valid SL
        assert has_sl is True
        assert sl_price is not None

    @pytest.mark.asyncio
    async def test_long_position_with_buy_sl_order_rejected(self, sl_manager):
        """
        SCENARIO: LONG position, but stop order has side=BUY (wrong!)
        EXPECTED: Should NOT recognize as SL for this position
        """
        # Mock fetch_open_orders to return BUY stop order (wrong for LONG)
        sl_manager.exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    'id': '12345',
                    'type': 'stop_market',
                    'side': 'buy',  # Wrong for LONG!
                    'stopPrice': 51000.0,
                    'reduceOnly': True,
                    'info': {}
                }
            ]
        )

        # Call with position_side='long'
        has_sl, sl_price = await sl_manager.has_stop_loss('BTC/USDT:USDT', position_side='long')

        # Should NOT recognize (wrong side)
        assert has_sl is False
        assert sl_price is None

    @pytest.mark.asyncio
    async def test_short_position_with_buy_sl_order(self, sl_manager):
        """
        SCENARIO: SHORT position has BUY stop loss order
        EXPECTED: Should recognize as valid SL
        """
        # Mock fetch_open_orders to return BUY stop order
        sl_manager.exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    'id': '12345',
                    'type': 'stop_market',
                    'side': 'buy',  # Correct for SHORT
                    'stopPrice': 51000.0,
                    'reduceOnly': True,
                    'info': {}
                }
            ]
        )

        # Call with position_side='short'
        has_sl, sl_price = await sl_manager.has_stop_loss('BTC/USDT:USDT', position_side='short')

        # Should recognize as valid SL
        assert has_sl is True
        assert sl_price is not None

    @pytest.mark.asyncio
    async def test_short_position_with_sell_sl_order_rejected(self, sl_manager):
        """
        SCENARIO: SHORT position, but stop order has side=SELL (wrong!)
        EXPECTED: Should NOT recognize as SL for this position
        """
        # Mock fetch_open_orders to return SELL stop order (wrong for SHORT)
        sl_manager.exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    'id': '12345',
                    'type': 'stop_market',
                    'side': 'sell',  # Wrong for SHORT!
                    'stopPrice': 49000.0,
                    'reduceOnly': True,
                    'info': {}
                }
            ]
        )

        # Call with position_side='short'
        has_sl, sl_price = await sl_manager.has_stop_loss('BTC/USDT:USDT', position_side='short')

        # Should NOT recognize (wrong side)
        assert has_sl is False
        assert sl_price is None

    @pytest.mark.asyncio
    async def test_no_position_side_provided_accepts_any(self, sl_manager):
        """
        SCENARIO: position_side=None (backward compatibility)
        EXPECTED: Should accept any side order (old behavior)
        """
        # Mock fetch_open_orders to return BUY stop order
        sl_manager.exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    'id': '12345',
                    'type': 'stop_market',
                    'side': 'buy',
                    'stopPrice': 51000.0,
                    'reduceOnly': True,
                    'info': {}
                }
            ]
        )

        # Call WITHOUT position_side (backward compatibility)
        has_sl, sl_price = await sl_manager.has_stop_loss('BTC/USDT:USDT', position_side=None)

        # Should recognize (backward compatibility - accepts any side)
        assert has_sl is True
        assert sl_price is not None
