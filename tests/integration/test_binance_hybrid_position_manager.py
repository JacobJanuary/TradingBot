"""
Integration tests for BinanceHybridStream with Position Manager
Date: 2025-10-25
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from websocket.binance_hybrid_stream import BinanceHybridStream


class TestEventEmission:
    """Test event emission to Position Manager"""

    @pytest.mark.asyncio
    async def test_event_handler_called(self):
        """Test event handler is called on position update"""
        event_mock = AsyncMock()

        stream = BinanceHybridStream("key", "secret", event_handler=event_mock, testnet=True)

        position_data = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'size': '1.0',
            'entry_price': '50000',
            'mark_price': '50100'
        }

        await stream._emit_combined_event('BTCUSDT', position_data)

        # Verify event was emitted
        event_mock.assert_called_once_with('position.update', position_data)

    @pytest.mark.asyncio
    async def test_event_format_compatibility(self):
        """Test event format matches Position Manager expectations"""
        received_events = []

        async def capture_event(event_type, data):
            received_events.append((event_type, data))

        stream = BinanceHybridStream("key", "secret", event_handler=capture_event, testnet=True)

        position_data = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'size': '1.0',
            'entry_price': '50000',
            'mark_price': '50100',
            'unrealized_pnl': '100'
        }

        await stream._emit_combined_event('BTCUSDT', position_data)

        # Verify format
        assert len(received_events) == 1
        event_type, data = received_events[0]

        assert event_type == 'position.update'
        assert data['symbol'] == 'BTCUSDT'
        assert data['side'] == 'LONG'
        assert data['size'] == '1.0'
        assert data['entry_price'] == '50000'
        assert data['mark_price'] == '50100'
        assert 'unrealized_pnl' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
