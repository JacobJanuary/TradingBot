"""
Unit tests for BinanceHybridStream fixes
Tests FIX #1, #2, #3 in isolation
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from websocket.binance_hybrid_stream import BinanceHybridStream


class TestFix1SubscriptionManager:
    """Test FIX #1: Subscription manager handles disconnected stream"""

    @pytest.mark.asyncio
    async def test_subscription_deferred_when_disconnected(self):
        """Subscriptions queued when mark stream disconnected"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = False  # Симулируем disconnected

        # Start subscription manager
        manager_task = asyncio.create_task(stream._subscription_manager())

        # Request subscription
        await stream._request_mark_subscription("BTCUSDT", subscribe=True)
        await asyncio.sleep(0.2)  # Дать время на обработку

        # Verify symbol in pending
        assert "BTCUSDT" in stream.pending_subscriptions
        assert "BTCUSDT" not in stream.subscribed_symbols  # Не подписан пока

        # Cleanup
        stream.running = False
        await manager_task

    @pytest.mark.asyncio
    async def test_pending_processed_after_reconnect(self):
        """Pending subscriptions processed after reconnect"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = False

        # Add to pending during disconnect
        stream.pending_subscriptions.add("BTCUSDT")
        stream.pending_subscriptions.add("ETHUSDT")

        # Simulate reconnect
        stream.mark_connected = True
        stream.mark_ws = MagicMock()  # Mock WebSocket
        stream.mark_ws.send_str = AsyncMock()  # Mock send method
        stream.mark_ws.closed = False

        # Call restore subscriptions
        await stream._restore_subscriptions()

        # Verify pending cleared after subscription
        assert len(stream.pending_subscriptions) == 0
        assert "BTCUSDT" in stream.subscribed_symbols
        assert "ETHUSDT" in stream.subscribed_symbols

    @pytest.mark.asyncio
    async def test_duplicate_pending_handling(self):
        """Test that duplicate pending subscriptions are handled correctly"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = False

        manager_task = asyncio.create_task(stream._subscription_manager())

        # Request same subscription twice
        await stream._request_mark_subscription("BTCUSDT", subscribe=True)
        await stream._request_mark_subscription("BTCUSDT", subscribe=True)
        await asyncio.sleep(0.3)

        # Should only be in pending once (set prevents duplicates)
        assert "BTCUSDT" in stream.pending_subscriptions
        assert len(stream.pending_subscriptions) == 1  # Only one unique symbol

        # Cleanup
        stream.running = False
        await manager_task


class TestFix2HeartbeatMonitoring:
    """Test FIX #2: Enhanced heartbeat monitoring"""

    @pytest.mark.asyncio
    async def test_heartbeat_detects_idle_with_pending(self):
        """Heartbeat detects idle stream with pending subscriptions"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True
        stream.subscribed_symbols = set()  # 0 active
        stream.pending_subscriptions = {"BTCUSDT", "ETHUSDT"}  # 2 pending

        # Start heartbeat (with short interval for testing)
        heartbeat_task = asyncio.create_task(
            stream._heartbeat_monitoring_task(check_interval=1, timeout=5)
        )

        # Wait for check
        await asyncio.sleep(1.5)

        # Verify reconnect triggered
        assert stream.mark_connected == False

        # Cleanup
        stream.running = False
        await heartbeat_task

    @pytest.mark.asyncio
    async def test_heartbeat_detects_stale_data(self):
        """Heartbeat detects subscriptions without data"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True
        stream.subscribed_symbols = {"BTCUSDT"}
        stream.mark_prices = {}  # No data received

        # Mock _get_data_age to return high value (old data)
        stream._get_data_age = lambda symbol: 200.0  # 200s old

        # Start heartbeat
        heartbeat_task = asyncio.create_task(
            stream._heartbeat_monitoring_task(check_interval=1, timeout=5)
        )

        # Wait for check (idle_stream_threshold = 120s)
        await asyncio.sleep(1.5)

        # Verify reconnect triggered
        assert stream.mark_connected == False

        # Cleanup
        stream.running = False
        await heartbeat_task

    @pytest.mark.asyncio
    async def test_heartbeat_ignores_normal_idle(self):
        """Heartbeat doesn't trigger on normal idle (0 positions)"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True
        stream.subscribed_symbols = set()  # 0 active
        stream.pending_subscriptions = set()  # 0 pending

        # Start heartbeat
        heartbeat_task = asyncio.create_task(
            stream._heartbeat_monitoring_task(check_interval=1, timeout=5)
        )

        # Wait for check
        await asyncio.sleep(1.5)

        # Verify reconnect NOT triggered (normal idle is OK)
        assert stream.mark_connected == True

        # Cleanup
        stream.running = False
        await heartbeat_task


class TestFix3PendingProcessor:
    """Test FIX #3: Periodic pending processor"""

    @pytest.mark.asyncio
    async def test_processor_handles_pending(self):
        """Processor periodically attempts pending subscriptions"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True

        # Add pending subscriptions
        stream.pending_subscriptions.add("BTCUSDT")
        stream.pending_subscriptions.add("ETHUSDT")

        # Mock WebSocket and _restore_subscriptions
        stream.mark_ws = MagicMock()
        stream.mark_ws.send_str = AsyncMock()
        stream.mark_ws.closed = False

        # Start processor with short interval for testing
        processor_task = asyncio.create_task(
            stream._process_pending_subscriptions_task(check_interval=1)
        )

        # Wait for first check (1s interval + processing time)
        await asyncio.sleep(1.5)

        # Verify pending were processed
        assert len(stream.pending_subscriptions) == 0
        assert "BTCUSDT" in stream.subscribed_symbols
        assert "ETHUSDT" in stream.subscribed_symbols

        # Cleanup
        stream.running = False
        await processor_task

    @pytest.mark.asyncio
    async def test_processor_skips_when_disconnected(self):
        """Processor doesn't process when stream disconnected"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = False  # Disconnected!

        # Add pending subscriptions
        stream.pending_subscriptions.add("BTCUSDT")
        stream.pending_subscriptions.add("ETHUSDT")

        # Start processor with short interval
        processor_task = asyncio.create_task(
            stream._process_pending_subscriptions_task(check_interval=1)
        )

        # Wait for check
        await asyncio.sleep(1.5)

        # Verify pending NOT processed (stream disconnected)
        assert len(stream.pending_subscriptions) == 2
        assert "BTCUSDT" in stream.pending_subscriptions
        assert "ETHUSDT" in stream.pending_subscriptions
        assert "BTCUSDT" not in stream.subscribed_symbols

        # Cleanup
        stream.running = False
        await processor_task

    @pytest.mark.asyncio
    async def test_processor_handles_failures(self):
        """Processor continues on subscription failures"""
        stream = BinanceHybridStream(api_key="test", api_secret="test")
        stream.running = True
        stream.mark_connected = True

        # Add pending subscriptions
        stream.pending_subscriptions.add("BTCUSDT")

        # Mock _restore_subscriptions to fail once, then succeed
        call_count = 0
        original_restore = stream._restore_subscriptions

        async def mock_restore_fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated subscription failure")
            else:
                # On second call, actually process pending
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

        # Wait for first check (should fail)
        await asyncio.sleep(1.5)

        # Verify processor didn't crash and pending still there
        assert len(stream.pending_subscriptions) == 1

        # Wait for second check (should succeed)
        await asyncio.sleep(1.5)

        # Verify pending processed on retry
        assert len(stream.pending_subscriptions) == 0
        assert "BTCUSDT" in stream.subscribed_symbols

        # Cleanup
        stream.running = False
        await processor_task
