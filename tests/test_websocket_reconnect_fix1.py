"""
Test Fix #1: WebSocket closure handling
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from websocket.signal_client import SignalWebSocketClient, ConnectionState
import websockets.exceptions


@pytest.mark.asyncio
async def test_request_signals_disconnects_on_error():
    """Test that request_signals() sets state to DISCONNECTED on error"""

    # Setup
    config = {
        'SIGNAL_WS_URL': 'ws://test:8765',
        'SIGNAL_WS_TOKEN': 'test',
        'AUTO_RECONNECT': False
    }

    client = SignalWebSocketClient(config)
    client.state = ConnectionState.AUTHENTICATED
    client.websocket = AsyncMock()
    client.websocket.send = AsyncMock(side_effect=Exception("Connection closed"))

    disconnect_called = False
    async def mock_disconnect():
        nonlocal disconnect_called
        disconnect_called = True

    client.on_disconnect_callback = mock_disconnect

    # Execute
    result = await client.request_signals()

    # Verify
    assert result == False, "Should return False on error"
    assert client.state == ConnectionState.DISCONNECTED, "State should be DISCONNECTED"
    assert disconnect_called, "Disconnect callback should be called"
    print("✅ Test passed: request_signals() handles disconnection correctly")


@pytest.mark.asyncio
async def test_request_stats_disconnects_on_error():
    """Test that request_stats() sets state to DISCONNECTED on error"""

    config = {
        'SIGNAL_WS_URL': 'ws://test:8765',
        'SIGNAL_WS_TOKEN': 'test',
        'AUTO_RECONNECT': False
    }

    client = SignalWebSocketClient(config)
    client.state = ConnectionState.AUTHENTICATED
    client.websocket = AsyncMock()
    client.websocket.send = AsyncMock(side_effect=Exception("Connection failed"))

    disconnect_called = False
    async def mock_disconnect():
        nonlocal disconnect_called
        disconnect_called = True

    client.on_disconnect_callback = mock_disconnect

    # Execute
    result = await client.request_stats()

    # Verify
    assert result == False
    assert client.state == ConnectionState.DISCONNECTED
    assert disconnect_called
    print("✅ Test passed: request_stats() handles disconnection correctly")


if __name__ == "__main__":
    asyncio.run(test_request_signals_disconnects_on_error())
    asyncio.run(test_request_stats_disconnects_on_error())
    print("\n✅ All Fix #1 tests passed!")
