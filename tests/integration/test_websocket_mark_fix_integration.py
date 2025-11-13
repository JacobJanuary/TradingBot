"""
Integration tests for WebSocket Mark Price Subscription Fixes
Tests real-world scenarios combining FIX #1, #2, #3
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from websocket.binance_hybrid_stream import BinanceHybridStream


class TestMarkPriceIntegration:
    """Integration tests for mark price subscription fixes"""

    @pytest.mark.asyncio
    async def test_position_opening_during_disconnect(self):
        """
        TEST SCENARIO 1: Position opens while mark stream disconnected

        Simulates the real-world bug:
        1. Mark stream disconnected
        2. Position opens (signal processor requests subscription)
        3. Subscription deferred to pending
        4. Mark stream reconnects
        5. Pending subscriptions processed automatically

        Expected: Symbol subscribed successfully after reconnect
        """
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = False  # Disconnected!

        # Start subscription manager
        manager_task = asyncio.create_task(stream._subscription_manager())

        # Simulate position opening (3 symbols rapid fire)
        await stream._request_mark_subscription("QNTUSDT", subscribe=True)
        await stream._request_mark_subscription("DOGSUSDT", subscribe=True)
        await stream._request_mark_subscription("MOODENGUSDT", subscribe=True)
        await asyncio.sleep(0.3)

        # Verify all symbols in pending (not subscribed yet)
        assert len(stream.pending_subscriptions) == 3
        assert "QNTUSDT" in stream.pending_subscriptions
        assert "DOGSUSDT" in stream.pending_subscriptions
        assert "MOODENGUSDT" in stream.pending_subscriptions
        assert len(stream.subscribed_symbols) == 0

        # Simulate reconnect
        stream.mark_connected = True
        stream.mark_ws = MagicMock()
        stream.mark_ws.send_str = AsyncMock()
        stream.mark_ws.closed = False

        # Call restore subscriptions (simulates reconnect logic)
        await stream._restore_subscriptions()

        # Verify all pending processed
        assert len(stream.pending_subscriptions) == 0
        assert len(stream.subscribed_symbols) == 3
        assert "QNTUSDT" in stream.subscribed_symbols
        assert "DOGSUSDT" in stream.subscribed_symbols
        assert "MOODENGUSDT" in stream.subscribed_symbols

        # Cleanup
        stream.running = False
        await manager_task

    @pytest.mark.asyncio
    async def test_multiple_positions_rapid_fire(self):
        """
        TEST SCENARIO 2: Multiple positions open rapidly (stress test)

        Simulates wave execution:
        1. Mark stream connected
        2. 10 positions open in rapid succession
        3. All should be subscribed successfully
        4. No duplicates in subscribed_symbols

        Expected: All symbols subscribed, no duplicates, no errors
        """
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True

        # Mock WebSocket
        stream.mark_ws = MagicMock()
        stream.mark_ws.send_str = AsyncMock()
        stream.mark_ws.closed = False

        # Start subscription manager
        manager_task = asyncio.create_task(stream._subscription_manager())

        # Rapid fire 10 symbols
        symbols = [
            "BTCUSDT", "ETHUSDT", "QNTUSDT", "DOGSUSDT", "MOODENGUSDT",
            "ADAUSDT", "SOLUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT"
        ]

        # Request all at once
        for symbol in symbols:
            await stream._request_mark_subscription(symbol, subscribe=True)

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify all subscribed
        assert len(stream.subscribed_symbols) == 10
        for symbol in symbols:
            assert symbol in stream.subscribed_symbols

        # Verify no duplicates (set property)
        assert len(stream.subscribed_symbols) == len(set(stream.subscribed_symbols))

        # Cleanup
        stream.running = False
        await manager_task

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_pending(self):
        """
        TEST SCENARIO 3: Full lifecycle - disconnect, pending, reconnect, process

        Complete end-to-end flow:
        1. Stream connected, 2 positions open
        2. Stream disconnects (silent disconnect)
        3. 3 more positions open → go to pending
        4. Heartbeat detects idle stream (0 active, 3 pending)
        5. Stream reconnects
        6. All 3 pending processed
        7. Periodic processor continues monitoring

        Expected: All 5 symbols eventually subscribed
        """
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True

        # Mock WebSocket
        stream.mark_ws = MagicMock()
        stream.mark_ws.send_str = AsyncMock()
        stream.mark_ws.closed = False

        # Start all tasks
        manager_task = asyncio.create_task(stream._subscription_manager())
        heartbeat_task = asyncio.create_task(
            stream._heartbeat_monitoring_task(check_interval=1, timeout=5)
        )
        processor_task = asyncio.create_task(
            stream._process_pending_subscriptions_task(check_interval=2)
        )

        # STEP 1: Open 2 positions (stream connected)
        await stream._request_mark_subscription("BTCUSDT", subscribe=True)
        await stream._request_mark_subscription("ETHUSDT", subscribe=True)
        await asyncio.sleep(0.3)

        # Verify subscribed
        assert len(stream.subscribed_symbols) == 2
        assert len(stream.pending_subscriptions) == 0

        # STEP 2: Simulate silent disconnect
        stream.mark_connected = False
        stream.subscribed_symbols.clear()  # Simulate lost subscriptions

        # STEP 3: Open 3 more positions (stream disconnected)
        await stream._request_mark_subscription("QNTUSDT", subscribe=True)
        await stream._request_mark_subscription("DOGSUSDT", subscribe=True)
        await stream._request_mark_subscription("MOODENGUSDT", subscribe=True)
        await asyncio.sleep(0.3)

        # Verify in pending (not subscribed)
        assert len(stream.pending_subscriptions) == 3
        assert len(stream.subscribed_symbols) == 0

        # STEP 4: Heartbeat should detect idle stream (0 active, 3 pending)
        # Already running in background

        # STEP 5: Simulate reconnect
        stream.mark_connected = True
        stream.mark_ws = MagicMock()
        stream.mark_ws.send_str = AsyncMock()
        stream.mark_ws.closed = False

        # Manually call restore subscriptions (simulates reconnect logic)
        await stream._restore_subscriptions()

        # STEP 6: Verify all pending processed immediately
        assert len(stream.pending_subscriptions) == 0
        assert len(stream.subscribed_symbols) == 3
        assert "QNTUSDT" in stream.subscribed_symbols
        assert "DOGSUSDT" in stream.subscribed_symbols
        assert "MOODENGUSDT" in stream.subscribed_symbols

        # Wait for processor cycle to confirm no issues
        await asyncio.sleep(2.5)

        # Cleanup
        stream.running = False
        await manager_task
        await heartbeat_task
        await processor_task

    @pytest.mark.asyncio
    async def test_heartbeat_triggers_reconnect_with_pending(self):
        """
        TEST SCENARIO 4: Heartbeat detects idle stream and triggers reconnect

        Tests FIX #2 integration:
        1. Stream connected but 0 subscriptions
        2. 2 symbols in pending
        3. Heartbeat detects idle stream with pending
        4. Forces reconnect (mark_connected = False)

        Expected: Heartbeat forces reconnect when idle with pending
        """
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True
        stream.subscribed_symbols = set()  # 0 active
        stream.pending_subscriptions = {"BTCUSDT", "ETHUSDT"}  # 2 pending

        # Start heartbeat with short interval
        heartbeat_task = asyncio.create_task(
            stream._heartbeat_monitoring_task(check_interval=1, timeout=5)
        )

        # Wait for heartbeat check
        await asyncio.sleep(1.5)

        # Verify reconnect triggered
        assert stream.mark_connected == False

        # Cleanup
        stream.running = False
        await heartbeat_task

    @pytest.mark.asyncio
    async def test_pending_processor_retries_on_failure(self):
        """
        TEST SCENARIO 5: Pending processor handles failures gracefully

        Tests FIX #3 resilience:
        1. Pending processor running
        2. First attempt fails (simulated error)
        3. Processor continues (doesn't crash)
        4. Second attempt succeeds

        Expected: Processor recovers from errors and retries
        """
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True
        stream.pending_subscriptions.add("BTCUSDT")

        # Mock _restore_subscriptions to fail once, then succeed
        call_count = 0
        original_restore = stream._restore_subscriptions

        async def mock_restore_fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated network error")
            else:
                await original_restore()

        stream._restore_subscriptions = mock_restore_fail_once

        # Mock WebSocket
        stream.mark_ws = MagicMock()
        stream.mark_ws.send_str = AsyncMock()
        stream.mark_ws.closed = False

        # Start processor with short interval
        processor_task = asyncio.create_task(
            stream._process_pending_subscriptions_task(check_interval=1)
        )

        # Wait for first attempt (should fail)
        await asyncio.sleep(1.5)
        assert len(stream.pending_subscriptions) == 1  # Still pending

        # Wait for second attempt (should succeed)
        await asyncio.sleep(1.5)
        assert len(stream.pending_subscriptions) == 0  # Processed!
        assert "BTCUSDT" in stream.subscribed_symbols

        # Cleanup
        stream.running = False
        await processor_task
