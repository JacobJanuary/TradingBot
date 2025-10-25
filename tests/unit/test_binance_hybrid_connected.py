"""
Unit tests for BinanceHybridStream.connected property
Date: 2025-10-25
"""

import pytest
from websocket.binance_hybrid_stream import BinanceHybridStream


class TestConnectedProperty:
    """Test connected property logic"""

    def test_connected_false_when_both_disconnected(self):
        """Test connected is False when both WS disconnected"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        stream.user_connected = False
        stream.mark_connected = False

        assert stream.connected is False

    def test_connected_false_when_only_user_connected(self):
        """Test connected is False when only user WS connected"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        stream.user_connected = True
        stream.mark_connected = False

        assert stream.connected is False

    def test_connected_false_when_only_mark_connected(self):
        """Test connected is False when only mark WS connected"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        stream.user_connected = False
        stream.mark_connected = True

        assert stream.connected is False

    def test_connected_true_when_both_connected(self):
        """Test connected is True when both WS connected"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        stream.user_connected = True
        stream.mark_connected = True

        assert stream.connected is True


class TestHealthCheckIntegration:
    """Test health check compatibility"""

    def test_has_connected_attribute(self):
        """Test stream has connected attribute"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Should not raise AttributeError
        assert hasattr(stream, 'connected')

    def test_connected_is_boolean(self):
        """Test connected returns boolean"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        result = stream.connected
        assert isinstance(result, bool)

    def test_health_check_loop_simulation(self):
        """Simulate health check loop"""
        websockets = {
            'binance_hybrid': BinanceHybridStream("key", "secret", testnet=True)
        }

        # Simulate health check code from main.py:590
        for name, stream in websockets.items():
            is_healthy = stream.connected  # Should not raise AttributeError
            assert isinstance(is_healthy, bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
