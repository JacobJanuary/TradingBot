"""
Unit tests for BinanceHybridStream reconnect logic
Tests subscription restoration after WebSocket reconnection

Date: 2025-10-25
"""

import pytest
import asyncio
from unittest.mock import AsyncMock
from websocket.binance_hybrid_stream import BinanceHybridStream


class TestReconnectLogic:
    """Test subscription restoration after reconnect"""

    @pytest.mark.asyncio
    async def test_restore_subscriptions_empty(self):
        """Test restoration with no subscriptions"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # No subscriptions
        stream.subscribed_symbols = set()

        # Should not raise error
        await stream._restore_subscriptions()

        assert len(stream.subscribed_symbols) == 0

    @pytest.mark.asyncio
    async def test_restore_subscriptions_single(self):
        """Test restoration with one subscription"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Mock subscribe method to add symbol back
        async def mock_subscribe(symbol):
            stream.subscribed_symbols.add(symbol)

        stream._subscribe_mark_price = mock_subscribe

        # Add one subscription
        stream.subscribed_symbols = {'BTCUSDT'}

        # Restore
        await stream._restore_subscriptions()

        # Verify resubscribed
        assert 'BTCUSDT' in stream.subscribed_symbols

    @pytest.mark.asyncio
    async def test_restore_subscriptions_multiple(self):
        """Test restoration with multiple subscriptions"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Track calls
        call_count = 0

        # Mock subscribe method to add symbols back
        async def mock_subscribe(symbol):
            nonlocal call_count
            call_count += 1
            stream.subscribed_symbols.add(symbol)

        stream._subscribe_mark_price = mock_subscribe

        # Add multiple subscriptions
        symbols = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT'}
        stream.subscribed_symbols = symbols.copy()

        # Restore
        await stream._restore_subscriptions()

        # Verify all resubscribed
        assert call_count == 3
        assert len(stream.subscribed_symbols) == 3

    @pytest.mark.asyncio
    async def test_restore_subscriptions_with_error(self):
        """Test restoration handles errors gracefully"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Mock subscribe method to fail on second symbol
        call_count = 0
        async def mock_subscribe(symbol):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Connection error")
            stream.subscribed_symbols.add(symbol)

        stream._subscribe_mark_price = mock_subscribe

        # Add multiple subscriptions
        stream.subscribed_symbols = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT'}

        # Restore (should not raise)
        await stream._restore_subscriptions()

        # Should have attempted all 3
        assert call_count == 3
        # Should have 2 successful (1st and 3rd)
        assert len(stream.subscribed_symbols) == 2


class TestHealthCheckIntegration:
    """Test health check compatibility after reconnect"""

    def test_restore_method_exists(self):
        """Test stream has _restore_subscriptions method"""
        stream = BinanceHybridStream("key", "secret", testnet=True)

        # Should not raise AttributeError
        assert hasattr(stream, '_restore_subscriptions')
        assert callable(stream._restore_subscriptions)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
