"""
Unit tests for Bybit Hybrid Stream position sync
Tests sync_positions() method for cold start scenarios

Date: 2025-10-25
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from websocket.bybit_hybrid_stream import BybitHybridStream


class TestPositionSync:
    """Test position synchronization on startup"""

    @pytest.mark.asyncio
    async def test_sync_positions_empty(self):
        """Test sync with no positions"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Should not raise error with empty list
        await stream.sync_positions([])

        # No subscriptions should be created
        assert len(stream.positions) == 0
        assert len(stream.subscribed_tickers) == 0

    @pytest.mark.asyncio
    async def test_sync_positions_single(self):
        """Test sync with one position"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription request
        stream._request_ticker_subscription = AsyncMock()

        # Sync one position
        positions = [
            {'symbol': 'BTCUSDT', 'side': 'Buy', 'quantity': 1.0, 'entry_price': 50000}
        ]
        await stream.sync_positions(positions)

        # Verify subscription requested
        stream._request_ticker_subscription.assert_called_once_with('BTCUSDT', subscribe=True)

        # Verify position stored
        assert 'BTCUSDT' in stream.positions
        assert stream.positions['BTCUSDT']['symbol'] == 'BTCUSDT'

    @pytest.mark.asyncio
    async def test_sync_positions_multiple(self):
        """Test sync with multiple positions"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription request
        stream._request_ticker_subscription = AsyncMock()

        # Sync 5 positions
        positions = [
            {'symbol': f'SYM{i}USDT', 'side': 'Buy', 'quantity': 1.0, 'entry_price': 100}
            for i in range(5)
        ]
        await stream.sync_positions(positions)

        # Verify all subscriptions requested
        assert stream._request_ticker_subscription.call_count == 5

        # Verify all positions stored
        assert len(stream.positions) == 5
        for i in range(5):
            assert f'SYM{i}USDT' in stream.positions

    @pytest.mark.asyncio
    async def test_sync_positions_missing_symbol(self):
        """Test sync handles positions without symbol gracefully"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription request
        stream._request_ticker_subscription = AsyncMock()

        # Sync with one invalid position
        positions = [
            {'side': 'Buy', 'quantity': 1.0},  # Missing symbol!
            {'symbol': 'ETHUSDT', 'side': 'Buy', 'quantity': 2.0}
        ]
        await stream.sync_positions(positions)

        # Should only subscribe to valid position
        stream._request_ticker_subscription.assert_called_once_with('ETHUSDT', subscribe=True)
        assert len(stream.positions) == 1
        assert 'ETHUSDT' in stream.positions

    @pytest.mark.asyncio
    async def test_sync_positions_subscription_error(self):
        """Test sync handles subscription errors gracefully"""
        stream = BybitHybridStream("key", "secret", testnet=False)

        # Mock subscription to fail on second position
        call_count = 0
        async def mock_request_sub(symbol, subscribe):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Connection error")

        stream._request_ticker_subscription = mock_request_sub

        # Sync 3 positions
        positions = [
            {'symbol': 'SYM1USDT', 'side': 'Buy', 'quantity': 1.0},
            {'symbol': 'SYM2USDT', 'side': 'Buy', 'quantity': 1.0},
            {'symbol': 'SYM3USDT', 'side': 'Buy', 'quantity': 1.0}
        ]

        # Should not raise
        await stream.sync_positions(positions)

        # Should have attempted all 3
        assert call_count == 3

        # All positions should be stored (subscription failure doesn't prevent storage)
        assert len(stream.positions) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
