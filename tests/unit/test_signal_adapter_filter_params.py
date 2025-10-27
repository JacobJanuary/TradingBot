#!/usr/bin/env python3
"""
Unit tests for SignalAdapter filter parameter extraction
"""
import pytest
from datetime import datetime, timezone
from websocket.signal_adapter import SignalAdapter


class TestSignalAdapterFilterParams:
    """Test filter parameter extraction"""

    def setup_method(self):
        """Setup test instance"""
        self.adapter = SignalAdapter()

    def test_extract_all_filter_params(self):
        """Test extraction of all filter parameters"""
        ws_signal = {
            'id': 12345,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 1,

            # Filter parameters
            'score_week_filter': 65.0,
            'score_month_filter': 60.0,
            'max_trades_filter': 10,
            'stop_loss_filter': 2.5,
            'trailing_activation_filter': 3.0,
            'trailing_distance_filter': 1.5
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify filter_params extracted
        assert 'filter_params' in adapted
        assert adapted['filter_params'] is not None

        params = adapted['filter_params']
        assert params['max_trades_filter'] == 10
        assert params['stop_loss_filter'] == 2.5
        assert params['trailing_activation_filter'] == 3.0
        assert params['trailing_distance_filter'] == 1.5

    def test_extract_partial_filter_params(self):
        """Test extraction when only some params present"""
        ws_signal = {
            'id': 12346,
            'pair_symbol': 'ETHUSDT',
            'recommended_action': 'SELL',
            'score_week': 70.0,
            'score_month': 65.0,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1235,
            'exchange_id': 2,

            # Only some filter parameters
            'max_trades_filter': 8,
            'stop_loss_filter': None,  # NULL value
            'trailing_activation_filter': 2.8,
            # trailing_distance_filter missing
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify filter_params extracted (with only present values)
        assert 'filter_params' in adapted
        params = adapted['filter_params']

        assert params['max_trades_filter'] == 8
        assert params['trailing_activation_filter'] == 2.8
        assert 'stop_loss_filter' not in params  # NULL excluded
        assert 'trailing_distance_filter' not in params  # Missing excluded

    def test_extract_no_filter_params(self):
        """Test extraction when no filter params present (backward compatibility)"""
        ws_signal = {
            'id': 12347,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 1,
            # NO filter parameters
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify filter_params is None (backward compatibility)
        assert 'filter_params' in adapted
        assert adapted['filter_params'] is None

    def test_extract_invalid_filter_params(self):
        """Test extraction with invalid parameter types"""
        ws_signal = {
            'id': 12348,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 1,

            # Invalid types
            'max_trades_filter': 'not_a_number',
            'stop_loss_filter': 2.5,
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Should handle gracefully (returns None on error)
        assert 'filter_params' in adapted
        # Implementation returns None if extraction fails

    def test_exchange_id_preserved(self):
        """Test that exchange_id is preserved in adapted signal"""
        ws_signal = {
            'id': 12349,
            'pair_symbol': 'BTCUSDT',
            'recommended_action': 'BUY',
            'score_week': 75.5,
            'score_month': 68.2,
            'timestamp': '2025-10-27T14:20:00',
            'created_at': '2025-10-27T14:20:05',
            'trading_pair_id': 1234,
            'exchange_id': 2,  # Bybit
            'max_trades_filter': 10,
        }

        adapted = self.adapter.adapt_signal(ws_signal)

        # Verify exchange_id preserved
        assert 'exchange_id' in adapted
        assert adapted['exchange_id'] == 2
        assert adapted['exchange'] == 'bybit'  # Mapped correctly
