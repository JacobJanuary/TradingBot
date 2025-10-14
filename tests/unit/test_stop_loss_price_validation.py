"""
Unit tests for Stop Loss price validation (Fix #2)

Tests verify that _validate_existing_sl() correctly validates
existing SL price against target, considering position direction.
"""

import pytest
from core.stop_loss_manager import StopLossManager
from unittest.mock import Mock


class TestStopLossPriceValidation:
    """Test price validation in _validate_existing_sl()"""

    @pytest.fixture
    def sl_manager(self):
        """Create StopLossManager instance"""
        mock_exchange = Mock()
        manager = StopLossManager(mock_exchange, 'binance')
        return manager

    def test_long_position_valid_sl_within_tolerance(self, sl_manager):
        """
        LONG position
        Existing SL: $49,000 (below entry)
        Target SL: $49,500
        Diff: 1.01% (< 5%)
        Expected: VALID (reuse existing)
        """
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=49000.0,
            target_sl_price=49500.0,
            side='sell',  # LONG position closes with SELL
            tolerance_percent=5.0
        )

        assert is_valid is True
        assert 'acceptable' in reason.lower()

    def test_long_position_existing_sl_too_high(self, sl_manager):
        """
        LONG position @ $50,000
        Existing SL: $51,000 (ABOVE entry - wrong!)
        Target SL: $49,000
        Expected: INVALID (existing SL worse than target)
        """
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=51000.0,
            target_sl_price=49000.0,
            side='sell',  # LONG position
            tolerance_percent=5.0
        )

        assert is_valid is False
        assert 'close to entry' in reason.lower() or 'too' in reason.lower()

    def test_long_position_existing_sl_from_old_position(self, sl_manager):
        """
        Old position LONG @ $50,000, SL @ $49,000
        New position LONG @ $60,000, target SL @ $58,800
        Existing SL too far: 16.67%
        Expected: INVALID (from old position, too low)
        """
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=49000.0,
            target_sl_price=58800.0,
            side='sell',  # LONG position
            tolerance_percent=5.0
        )

        assert is_valid is False
        assert 'old position' in reason.lower()

    def test_short_position_valid_sl_within_tolerance(self, sl_manager):
        """
        SHORT position
        Existing SL: $51,000 (above entry)
        Target SL: $50,500
        Diff: 0.99% (< 5%)
        Expected: VALID (reuse existing)
        """
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=51000.0,
            target_sl_price=50500.0,
            side='buy',  # SHORT position closes with BUY
            tolerance_percent=5.0
        )

        assert is_valid is True
        assert 'acceptable' in reason.lower()

    def test_short_position_existing_sl_too_low(self, sl_manager):
        """
        SHORT position @ $50,000
        Existing SL: $49,000 (BELOW entry - wrong!)
        Target SL: $51,000
        Expected: INVALID (existing SL worse than target)
        """
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=49000.0,
            target_sl_price=51000.0,
            side='buy',  # SHORT position
            tolerance_percent=5.0
        )

        assert is_valid is False
        assert 'close to entry' in reason.lower() or 'too' in reason.lower()

    def test_edge_case_exact_match(self, sl_manager):
        """
        Existing SL: $50,000
        Target SL: $50,000
        Expected: VALID (exact match)
        """
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=50000.0,
            target_sl_price=50000.0,
            side='sell',
            tolerance_percent=5.0
        )

        assert is_valid is True
        assert 'acceptable' in reason.lower()

    def test_short_position_old_sl_too_high(self, sl_manager):
        """
        Old SHORT position @ $50,000, SL @ $51,000
        New SHORT position @ $40,000, target SL @ $40,800
        Existing SL too high (from old position)
        Expected: INVALID
        """
        is_valid, reason = sl_manager._validate_existing_sl(
            existing_sl_price=51000.0,
            target_sl_price=40800.0,
            side='buy',  # SHORT position
            tolerance_percent=5.0
        )

        assert is_valid is False
        assert 'old position' in reason.lower()
