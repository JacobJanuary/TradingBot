"""
Unit tests for BinanceHybridStream core functionality
Date: 2025-10-25
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from websocket.binance_hybrid_stream import BinanceHybridStream


class TestInitialization:
    """Test initialization logic"""

    def test_init_testnet(self):
        """Test initialization with testnet=True"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        assert stream.testnet is True
        assert "testnet.binance.vision" in stream.rest_url
        assert "stream.binance.vision" in stream.user_ws_url

    def test_init_mainnet(self):
        """Test initialization with testnet=False"""
        stream = BinanceHybridStream("key", "secret", testnet=False)

        assert stream.testnet is False
        assert "fapi.binance.com" in stream.rest_url
        assert "fstream.binance.com" in stream.user_ws_url

    def test_init_state(self):
        """Test initial state"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        assert stream.user_connected is False
        assert stream.mark_connected is False
        assert stream.running is False
        assert len(stream.positions) == 0
        assert len(stream.mark_prices) == 0
        assert len(stream.subscribed_symbols) == 0


class TestPositionManagement:
    """Test position state management"""

    def test_add_position(self):
        """Test adding position"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        position_data = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'size': '1.0',
            'entry_price': '50000',
            'mark_price': '50100'
        }

        stream.positions['BTCUSDT'] = position_data

        assert 'BTCUSDT' in stream.positions
        assert stream.positions['BTCUSDT']['side'] == 'LONG'

    def test_remove_position(self):
        """Test removing position"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        stream.positions['BTCUSDT'] = {'symbol': 'BTCUSDT', 'side': 'LONG'}

        del stream.positions['BTCUSDT']

        assert 'BTCUSDT' not in stream.positions

    def test_update_mark_price(self):
        """Test updating mark price"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        stream.mark_prices['BTCUSDT'] = '50000'
        assert stream.mark_prices['BTCUSDT'] == '50000'

        stream.mark_prices['BTCUSDT'] = '50100'
        assert stream.mark_prices['BTCUSDT'] == '50100'


class TestStatusReporting:
    """Test status reporting"""

    def test_get_status_empty(self):
        """Test status with no positions"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        status = stream.get_status()

        assert status['running'] is False
        assert status['active_positions'] == 0
        assert status['subscribed_symbols'] == 0

    def test_get_status_with_positions(self):
        """Test status with positions"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        stream.positions['BTCUSDT'] = {'symbol': 'BTCUSDT'}
        stream.positions['ETHUSDT'] = {'symbol': 'ETHUSDT'}
        stream.subscribed_symbols = {'BTCUSDT', 'ETHUSDT'}
        stream.running = True
        stream.user_connected = True
        stream.mark_connected = True

        status = stream.get_status()

        assert status['running'] is True
        assert status['user_connected'] is True
        assert status['mark_connected'] is True
        assert status['active_positions'] == 2
        assert status['subscribed_symbols'] == 2
        assert 'BTCUSDT' in status['positions']
        assert 'ETHUSDT' in status['positions']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
