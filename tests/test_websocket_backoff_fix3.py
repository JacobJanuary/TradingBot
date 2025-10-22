#!/usr/bin/env python3
"""
Test Fix #3: Exponential backoff in reconnection
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from unittest.mock import Mock, AsyncMock, patch
from websocket.signal_client import SignalWebSocketClient


async def test_exponential_backoff():
    """Test that reconnect delay increases exponentially"""

    config = {
        'SIGNAL_WS_URL': 'ws://test:8765',
        'SIGNAL_WS_TOKEN': 'test',
        'AUTO_RECONNECT': True,
        'RECONNECT_INTERVAL': 2,  # base 2 seconds
        'MAX_RECONNECT_ATTEMPTS': 5
    }

    client = SignalWebSocketClient(config)
    client.connect = AsyncMock(return_value=False)  # Always fail to trigger reconnect

    delays = []
    original_sleep = asyncio.sleep
    async def mock_sleep(delay):
        delays.append(delay)
        await original_sleep(0.001)  # Sleep very short for test

    with patch('asyncio.sleep', side_effect=mock_sleep):
        # Trigger 4 reconnect attempts
        for i in range(4):
            await client.reconnect()

    # Expected delays: 2, 4, 8, 16 (exponential: 2 * 2^n)
    expected = [2, 4, 8, 16]

    assert delays == expected, f"Expected {expected}, got {delays}"
    print(f"✅ Exponential backoff working: {delays}")


if __name__ == "__main__":
    asyncio.run(test_exponential_backoff())
    print("✅ Fix #3 backoff test passed!")
