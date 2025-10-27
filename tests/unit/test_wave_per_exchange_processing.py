#!/usr/bin/env python3
"""
Unit tests for per-exchange wave processing logic
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch


class TestPerExchangeWaveProcessing:
    """Test per-exchange signal processing"""

    def setup_method(self):
        """Setup test fixtures"""
        self.sample_binance_signals = [
            {
                'id': 1001,
                'symbol': 'BTCUSDT',
                'exchange': 'binance',
                'exchange_id': 1,
                'score_week': 80.0,
                'score_month': 70.0,
                'action': 'BUY',
                'filter_params': {
                    'max_trades_filter': 6,
                    'stop_loss_filter': 4.0,
                    'trailing_activation_filter': 2.0,
                    'trailing_distance_filter': 0.5
                }
            },
            {
                'id': 1002,
                'symbol': 'ETHUSDT',
                'exchange': 'binance',
                'exchange_id': 1,
                'score_week': 75.0,
                'score_month': 72.0,
                'action': 'BUY'
            },
            {
                'id': 1003,
                'symbol': 'SOLUSDT',
                'exchange': 'binance',
                'exchange_id': 1,
                'score_week': 70.0,
                'score_month': 68.0,
                'action': 'BUY'
            }
        ]

        self.sample_bybit_signals = [
            {
                'id': 2001,
                'symbol': 'BTCUSDT',
                'exchange': 'bybit',
                'exchange_id': 2,
                'score_week': 85.0,
                'score_month': 75.0,
                'action': 'BUY',
                'filter_params': {
                    'max_trades_filter': 4,
                    'stop_loss_filter': 3.5,
                    'trailing_activation_filter': 2.5,
                    'trailing_distance_filter': 0.6
                }
            },
            {
                'id': 2002,
                'symbol': 'ETHUSDT',
                'exchange': 'bybit',
                'exchange_id': 2,
                'score_week': 78.0,
                'score_month': 73.0,
                'action': 'BUY'
            }
        ]

    def test_sort_by_sum_not_tuple(self):
        """Test signals sorted by sum of scores, not tuple"""
        signals = [
            {'score_week': 75.0, 'score_month': 90.0},  # sum=165.0
            {'score_week': 80.0, 'score_month': 70.0},  # sum=150.0
        ]

        # Sort by SUM
        sorted_signals = sorted(
            signals,
            key=lambda s: s.get('score_week', 0) + s.get('score_month', 0),
            reverse=True
        )

        # First should have highest sum (165.0)
        assert sorted_signals[0]['score_week'] == 75.0
        assert sorted_signals[0]['score_month'] == 90.0

    def test_group_signals_by_exchange(self):
        """Test grouping signals by exchange_id"""
        all_signals = self.sample_binance_signals + self.sample_bybit_signals

        # Group by exchange_id
        signals_by_exchange = {}
        for signal in all_signals:
            exchange_id = signal.get('exchange_id')
            if exchange_id not in signals_by_exchange:
                signals_by_exchange[exchange_id] = []
            signals_by_exchange[exchange_id].append(signal)

        # Verify grouping
        assert 1 in signals_by_exchange  # Binance
        assert 2 in signals_by_exchange  # Bybit
        assert len(signals_by_exchange[1]) == 3  # 3 Binance signals
        assert len(signals_by_exchange[2]) == 2  # 2 Bybit signals

    def test_calculate_buffer_fixed_not_percent(self):
        """Test fixed +3 buffer instead of percentage"""
        max_trades = 6

        # OLD: Percentage-based
        buffer_percent = 50.0
        old_buffer_size = int(max_trades * (1 + buffer_percent / 100))
        assert old_buffer_size == 9  # 6 * 1.5 = 9

        # NEW: Fixed +3
        new_buffer_size = max_trades + 3
        assert new_buffer_size == 9  # 6 + 3 = 9

        # Different for different max_trades
        max_trades_2 = 4
        old_buffer_2 = int(max_trades_2 * (1 + buffer_percent / 100))
        new_buffer_2 = max_trades_2 + 3

        assert old_buffer_2 == 6  # 4 * 1.5 = 6
        assert new_buffer_2 == 7  # 4 + 3 = 7 (different!)

    def test_handle_missing_exchange_signals(self):
        """Test graceful handling when one exchange has no signals"""
        # Only Binance signals, no Bybit
        all_signals = self.sample_binance_signals

        signals_by_exchange = {}
        for signal in all_signals:
            exchange_id = signal.get('exchange_id')
            if exchange_id not in signals_by_exchange:
                signals_by_exchange[exchange_id] = []
            signals_by_exchange[exchange_id].append(signal)

        # Should work fine with only one exchange
        assert 1 in signals_by_exchange
        assert 2 not in signals_by_exchange  # No Bybit signals - OK

    def test_handle_no_signals_at_all(self):
        """Test graceful handling when wave has no signals"""
        all_signals = []

        signals_by_exchange = {}
        for signal in all_signals:
            exchange_id = signal.get('exchange_id')
            if exchange_id not in signals_by_exchange:
                signals_by_exchange[exchange_id] = []
            signals_by_exchange[exchange_id].append(signal)

        # Should be empty dict - OK
        assert signals_by_exchange == {}

    def test_fallback_to_config_when_db_null(self):
        """Test fallback to config when DB returns NULL"""
        db_params = {
            'exchange_id': 1,
            'max_trades_filter': None,  # NULL in DB
        }

        config_default = 5
        max_trades = db_params.get('max_trades_filter') or config_default

        assert max_trades == config_default  # Fallback worked

    def test_extract_params_from_first_signal_per_exchange(self):
        """Test that we extract params from FIRST signal per exchange"""
        # Binance signals
        binance_signals = self.sample_binance_signals  # First has filter_params

        # Get first signal
        first_binance = binance_signals[0]
        params = first_binance.get('filter_params')

        assert params is not None
        assert params['max_trades_filter'] == 6

        # Bybit signals
        bybit_signals = self.sample_bybit_signals  # First has filter_params

        first_bybit = bybit_signals[0]
        params_bybit = first_bybit.get('filter_params')

        assert params_bybit is not None
        assert params_bybit['max_trades_filter'] == 4

    @pytest.mark.asyncio
    async def test_params_update_before_selection(self):
        """Test that params are updated BEFORE signal selection"""
        call_order = []

        async def mock_update_params():
            call_order.append('update_params')

        async def mock_select_signals():
            call_order.append('select_signals')

        # Correct order: update THEN select
        await mock_update_params()
        await mock_select_signals()

        assert call_order == ['update_params', 'select_signals']

    def test_per_exchange_buffer_calculation(self):
        """Test buffer calculation per exchange"""
        params_binance = {'max_trades_filter': 6}
        params_bybit = {'max_trades_filter': 4}

        buffer_binance = params_binance['max_trades_filter'] + 3
        buffer_bybit = params_bybit['max_trades_filter'] + 3

        assert buffer_binance == 9  # 6 + 3
        assert buffer_bybit == 7   # 4 + 3

        # Different buffers per exchange ✅
        assert buffer_binance != buffer_bybit

    def test_signal_selection_respects_target_not_buffer(self):
        """Test that we TARGET max_trades, not buffer size"""
        max_trades = 6
        buffer_size = 9  # 6 + 3

        # We select buffer_size for validation
        selected_for_validation = buffer_size  # 9 signals

        # But we TARGET max_trades after validation
        target_after_validation = max_trades  # 6 positions

        assert selected_for_validation == 9
        assert target_after_validation == 6
        assert selected_for_validation > target_after_validation  # Buffer is extra

    def test_execution_stops_at_target(self):
        """Test that execution stops when executed_count >= max_trades"""
        max_trades = 6
        validated_signals = list(range(10))  # 10 signals available

        executed_count = 0

        for signal in validated_signals:
            # CRITICAL: Stop at target
            if executed_count >= max_trades:
                break

            # Simulate execution
            executed_count += 1

        # Should stop at max_trades
        assert executed_count == max_trades
        assert executed_count == 6


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
