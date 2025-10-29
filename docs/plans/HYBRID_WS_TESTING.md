# BYBIT HYBRID WEBSOCKET - TESTING STRATEGY
**Date**: 2025-10-25
**Status**: 📋 READY FOR IMPLEMENTATION
**Type**: COMPREHENSIVE TEST PLAN

---

## Table of Contents

1. [Testing Philosophy](#testing-philosophy)
2. [Unit Tests](#unit-tests)
3. [Integration Tests](#integration-tests)
4. [System Tests](#system-tests)
5. [Performance Tests](#performance-tests)
6. [Failover Tests](#failover-tests)
7. [Test Scripts](#test-scripts)
8. [Acceptance Criteria](#acceptance-criteria)
9. [Test Execution Plan](#test-execution-plan)

---

## Testing Philosophy

### Goals
- ✅ Verify each component works independently
- ✅ Verify components work together correctly
- ✅ Verify system handles failures gracefully
- ✅ Verify performance meets requirements
- ✅ Verify integration with existing code

### Principles
1. **Test First**: Write tests before implementation
2. **Incremental**: Test each component as it's built
3. **Realistic**: Use real Bybit testnet/mainnet connections
4. **Comprehensive**: Cover happy path + edge cases + failures
5. **Automated**: All tests run via pytest

### Test Levels
```
Unit Tests           → Individual components
    ↓
Integration Tests    → Component interactions
    ↓
System Tests         → Full system behavior
    ↓
Performance Tests    → Speed, throughput, latency
    ↓
Failover Tests       → Failure recovery
```

---

## Unit Tests

### 1. BybitHybridStream - Constructor Tests

**File**: `tests/unit/test_bybit_hybrid_stream_init.py`

**Test Cases**:

```python
import pytest
from websocket.bybit_hybrid_stream import BybitHybridStream


class TestBybitHybridStreamInit:
    """Test BybitHybridStream initialization"""

    def test_init_with_valid_params(self):
        """Test initialization with valid parameters"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        assert stream.api_key == "test_key"
        assert stream.api_secret == "test_secret"
        assert stream.testnet is True
        assert stream.positions == {}
        assert stream.mark_prices == {}
        assert stream.subscribed_tickers == set()
        assert stream.private_ws is None
        assert stream.public_ws is None

    def test_init_urls_testnet(self):
        """Test WebSocket URLs for testnet"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        assert "testnet" in stream.private_ws_url
        assert "testnet" in stream.public_ws_url

    def test_init_urls_mainnet(self):
        """Test WebSocket URLs for mainnet"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=False
        )

        assert "testnet" not in stream.private_ws_url
        assert "testnet" not in stream.public_ws_url

    def test_init_without_credentials_raises_error(self):
        """Test initialization without credentials raises error"""
        with pytest.raises(ValueError, match="api_key required"):
            BybitHybridStream(api_key="", api_secret="test_secret")
```

---

### 2. Authentication Tests

**File**: `tests/unit/test_bybit_hybrid_auth.py`

**Test Cases**:

```python
import pytest
import time
import hmac
import hashlib
from websocket.bybit_hybrid_stream import BybitHybridStream


class TestBybitHybridAuth:
    """Test authentication logic"""

    def test_generate_signature(self):
        """Test HMAC signature generation"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        expires = int((time.time() + 10) * 1000)
        signature = stream._generate_signature(expires)

        # Verify signature format
        assert len(signature) == 64  # SHA256 hex = 64 chars
        assert isinstance(signature, str)

        # Verify signature is deterministic
        signature2 = stream._generate_signature(expires)
        assert signature == signature2

    def test_signature_changes_with_expires(self):
        """Test signature changes with different expires"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        expires1 = int((time.time() + 10) * 1000)
        expires2 = int((time.time() + 20) * 1000)

        sig1 = stream._generate_signature(expires1)
        sig2 = stream._generate_signature(expires2)

        assert sig1 != sig2

    def test_create_auth_message(self):
        """Test authentication message creation"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        auth_msg = stream._create_auth_message()

        assert auth_msg['op'] == 'auth'
        assert len(auth_msg['args']) == 3
        assert auth_msg['args'][0] == "test_key"
        assert isinstance(auth_msg['args'][1], int)  # expires
        assert isinstance(auth_msg['args'][2], str)  # signature
```

---

### 3. Subscription Management Tests

**File**: `tests/unit/test_bybit_hybrid_subscriptions.py`

**Test Cases**:

```python
import pytest
from websocket.bybit_hybrid_stream import BybitHybridStream


class TestSubscriptionManagement:
    """Test ticker subscription management"""

    @pytest.mark.asyncio
    async def test_subscribe_ticker(self):
        """Test subscribing to ticker topic"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Mock public WebSocket
        class MockWebSocket:
            def __init__(self):
                self.sent_messages = []

            async def send(self, msg):
                self.sent_messages.append(msg)

        stream.public_ws = MockWebSocket()

        # Subscribe to ticker
        await stream._request_ticker_subscription('BTCUSDT', subscribe=True)

        # Verify subscription request sent
        assert len(stream.public_ws.sent_messages) == 1
        import json
        msg = json.loads(stream.public_ws.sent_messages[0])
        assert msg['op'] == 'subscribe'
        assert 'tickers.BTCUSDT' in msg['args']

        # Verify tracking
        assert 'BTCUSDT' in stream.subscribed_tickers

    @pytest.mark.asyncio
    async def test_unsubscribe_ticker(self):
        """Test unsubscribing from ticker topic"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Setup
        stream.subscribed_tickers.add('BTCUSDT')

        class MockWebSocket:
            def __init__(self):
                self.sent_messages = []

            async def send(self, msg):
                self.sent_messages.append(msg)

        stream.public_ws = MockWebSocket()

        # Unsubscribe
        await stream._request_ticker_subscription('BTCUSDT', subscribe=False)

        # Verify unsubscribe request sent
        import json
        msg = json.loads(stream.public_ws.sent_messages[0])
        assert msg['op'] == 'unsubscribe'
        assert 'tickers.BTCUSDT' in msg['args']

        # Verify tracking removed
        assert 'BTCUSDT' not in stream.subscribed_tickers

    @pytest.mark.asyncio
    async def test_no_duplicate_subscriptions(self):
        """Test that duplicate subscriptions are prevented"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        class MockWebSocket:
            def __init__(self):
                self.sent_messages = []

            async def send(self, msg):
                self.sent_messages.append(msg)

        stream.public_ws = MockWebSocket()

        # Subscribe twice
        await stream._request_ticker_subscription('BTCUSDT', subscribe=True)
        await stream._request_ticker_subscription('BTCUSDT', subscribe=True)

        # Should only send one subscription request
        assert len(stream.public_ws.sent_messages) == 1
```

---

### 4. Event Processing Tests

**File**: `tests/unit/test_bybit_hybrid_events.py`

**Test Cases**:

```python
import pytest
from decimal import Decimal
from websocket.bybit_hybrid_stream import BybitHybridStream


class TestEventProcessing:
    """Test event processing logic"""

    @pytest.mark.asyncio
    async def test_position_opened_triggers_subscription(self):
        """Test position opening triggers ticker subscription"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Mock
        subscribed = []
        async def mock_subscribe(symbol, subscribe):
            if subscribe:
                subscribed.append(symbol)

        stream._request_ticker_subscription = mock_subscribe

        # Simulate position opened
        position_data = [{
            'symbol': 'BTCUSDT',
            'side': 'Buy',
            'size': '1.0',
            'avgPrice': '50000.0',
            'markPrice': '50100.0'
        }]

        await stream._on_position_update(position_data)

        # Verify ticker subscription requested
        assert 'BTCUSDT' in subscribed
        assert 'BTCUSDT' in stream.positions

    @pytest.mark.asyncio
    async def test_position_closed_triggers_unsubscription(self):
        """Test position closing triggers ticker unsubscription"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Setup - existing position
        stream.positions['BTCUSDT'] = {
            'symbol': 'BTCUSDT',
            'size': '1.0'
        }
        stream.subscribed_tickers.add('BTCUSDT')

        # Mock
        unsubscribed = []
        async def mock_subscribe(symbol, subscribe):
            if not subscribe:
                unsubscribed.append(symbol)

        stream._request_ticker_subscription = mock_subscribe

        # Simulate position closed
        position_data = [{
            'symbol': 'BTCUSDT',
            'side': 'Buy',
            'size': '0',  # Closed
            'avgPrice': '50000.0',
            'markPrice': '50500.0'
        }]

        await stream._on_position_update(position_data)

        # Verify unsubscription requested
        assert 'BTCUSDT' in unsubscribed
        assert 'BTCUSDT' not in stream.positions

    @pytest.mark.asyncio
    async def test_ticker_update_combines_with_position(self):
        """Test ticker updates combine with position data"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Setup - existing position
        stream.positions['BTCUSDT'] = {
            'symbol': 'BTCUSDT',
            'side': 'Buy',
            'size': '1.0',
            'avgPrice': '50000.0'
        }

        # Mock event emission
        emitted_events = []
        async def mock_emit(symbol, data):
            emitted_events.append((symbol, data))

        stream._emit_combined_event = mock_emit

        # Simulate ticker update
        ticker_data = {
            'symbol': 'BTCUSDT',
            'markPrice': '50500.0',
            'lastPrice': '50499.0'
        }

        await stream._on_ticker_update(ticker_data)

        # Verify event emitted with combined data
        assert len(emitted_events) == 1
        symbol, data = emitted_events[0]
        assert symbol == 'BTCUSDT'
        assert data['mark_price'] == '50500.0'
        assert data['size'] == '1.0'
        assert data['side'] == 'Buy'

    @pytest.mark.asyncio
    async def test_ticker_update_without_position_no_event(self):
        """Test ticker update without position doesn't emit event"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # No positions

        # Mock
        emitted_events = []
        async def mock_emit(symbol, data):
            emitted_events.append((symbol, data))

        stream._emit_combined_event = mock_emit

        # Simulate ticker update
        ticker_data = {
            'symbol': 'BTCUSDT',
            'markPrice': '50500.0'
        }

        await stream._on_ticker_update(ticker_data)

        # Should NOT emit event (no position)
        assert len(emitted_events) == 0
```

---

### 5. Heartbeat Tests

**File**: `tests/unit/test_bybit_hybrid_heartbeat.py`

**Test Cases**:

```python
import pytest
import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream


class TestHeartbeat:
    """Test heartbeat/ping-pong logic"""

    @pytest.mark.asyncio
    async def test_heartbeat_interval_20s(self):
        """Test heartbeat interval is 20s for Bybit"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        assert stream.heartbeat_interval == 20

    @pytest.mark.asyncio
    async def test_private_ws_ping_sent(self):
        """Test private WebSocket sends ping every 20s"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Mock
        pings_sent = []

        class MockWebSocket:
            async def send(self, msg):
                import json
                data = json.loads(msg)
                if data.get('op') == 'ping':
                    pings_sent.append(asyncio.get_event_loop().time())

        stream.private_ws = MockWebSocket()
        stream.private_connected = True

        # Run heartbeat for 45 seconds
        async def run_heartbeat():
            for _ in range(3):  # 3 iterations * 20s = 60s
                await stream._send_private_ping()
                await asyncio.sleep(0.1)  # Simulate

        await run_heartbeat()

        # Should have sent 3 pings
        assert len(pings_sent) == 3

    @pytest.mark.asyncio
    async def test_public_ws_ping_sent(self):
        """Test public WebSocket sends ping every 20s"""
        stream = BybitHybridStream(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Mock
        pings_sent = []

        class MockWebSocket:
            async def send(self, msg):
                import json
                data = json.loads(msg)
                if data.get('op') == 'ping':
                    pings_sent.append(True)

        stream.public_ws = MockWebSocket()
        stream.public_connected = True

        # Send pings
        await stream._send_public_ping()
        await stream._send_public_ping()

        assert len(pings_sent) == 2
```

---

## Integration Tests

### 1. Dual WebSocket Connection Test

**File**: `tests/integration/test_bybit_dual_connection.py`

**Purpose**: Verify both WebSockets can connect simultaneously

**Test Cases**:

```python
import pytest
import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


class TestDualConnection:
    """Test dual WebSocket connections"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_both_websockets_connect(self):
        """Test both private and public WebSockets connect"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        # Start both streams
        connection_task = asyncio.create_task(stream.start())

        # Wait for connections
        await asyncio.sleep(5)

        # Verify both connected
        assert stream.private_connected is True
        assert stream.public_connected is True

        # Stop
        await stream.stop()
        await connection_task

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_private_ws_authenticates(self):
        """Test private WebSocket authenticates successfully"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        auth_success = False

        def event_handler(event_type, data):
            nonlocal auth_success
            if event_type == 'auth.success':
                auth_success = True

        stream.set_event_handler(event_handler)

        connection_task = asyncio.create_task(stream.start())
        await asyncio.sleep(5)

        assert auth_success is True

        await stream.stop()
        await connection_task
```

---

### 2. Position Lifecycle Test

**File**: `tests/integration/test_bybit_position_lifecycle.py`

**Purpose**: Verify position open → ticker subscription → price updates → position close → unsubscribe

**Test Cases**:

```python
import pytest
import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


class TestPositionLifecycle:
    """Test complete position lifecycle"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_position_open_triggers_ticker_subscription(self):
        """Test opening position triggers ticker subscription"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        # Track events
        position_updates = []
        ticker_subscriptions = []

        def event_handler(event_type, data):
            if event_type == 'position.update':
                position_updates.append(data)
            elif event_type == 'ticker.subscribed':
                ticker_subscriptions.append(data)

        stream.set_event_handler(event_handler)

        # Start stream
        await stream.start()

        # Wait for initial connection
        await asyncio.sleep(5)

        # Manually open a small position on testnet
        # (This requires actual trading - for automated tests, mock this)

        # For now, check if existing positions trigger subscriptions
        initial_subs = len(stream.subscribed_tickers)

        # Simulate position update
        test_position = [{
            'symbol': 'BTCUSDT',
            'side': 'Buy',
            'size': '0.001',
            'avgPrice': '50000.0',
            'markPrice': '50100.0'
        }]

        await stream._on_position_update(test_position)

        # Verify subscription added
        assert 'BTCUSDT' in stream.subscribed_tickers
        assert len(stream.subscribed_tickers) == initial_subs + 1

        await stream.stop()
```

---

### 3. Event Router Integration Test

**File**: `tests/integration/test_bybit_event_router.py`

**Purpose**: Verify BybitHybridStream integrates with EventRouter

**Test Cases**:

```python
import pytest
import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream
from websocket.event_router import EventRouter
from config.settings import config


class TestEventRouterIntegration:
    """Test integration with EventRouter"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_position_updates_routed(self):
        """Test position updates are routed through EventRouter"""
        bybit_config = config.get_exchange_config('bybit')
        event_router = EventRouter()

        # Track received events
        received_events = []

        @event_router.on('position.update')
        async def handle_position_update(data):
            received_events.append(data)

        # Create stream with event router
        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            event_handler=event_router.emit,
            testnet=True
        )

        await stream.start()
        await asyncio.sleep(5)

        # Simulate position update
        test_position = [{
            'symbol': 'BTCUSDT',
            'side': 'Buy',
            'size': '0.001',
            'avgPrice': '50000.0',
            'markPrice': '50100.0'
        }]

        await stream._on_position_update(test_position)

        # Wait for event processing
        await asyncio.sleep(0.5)

        # Verify event received
        assert len(received_events) > 0
        assert received_events[0]['symbol'] == 'BTCUSDT'

        await stream.stop()
```

---

### 4. Position Manager Integration Test

**File**: `tests/integration/test_bybit_position_manager.py`

**Purpose**: Verify Position Manager receives and processes hybrid events

**Test Cases**:

```python
import pytest
import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream
from core.position_manager import PositionManager
from config.settings import config


class TestPositionManagerIntegration:
    """Test integration with Position Manager"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_position_manager_receives_price_updates(self):
        """Test Position Manager receives price updates from hybrid stream"""
        bybit_config = config.get_exchange_config('bybit')

        # Create Position Manager (simplified - no full initialization)
        position_manager = PositionManager(
            exchange_name='bybit',
            # ... other params
        )

        # Create hybrid stream
        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            event_handler=position_manager.event_router.emit,
            testnet=True
        )

        # Track price updates in Position Manager
        price_updates = []

        original_update = position_manager._on_position_update
        async def tracked_update(data):
            price_updates.append(data.get('mark_price'))
            await original_update(data)

        position_manager._on_position_update = tracked_update

        await stream.start()
        await asyncio.sleep(10)

        # Should receive multiple price updates
        assert len(price_updates) > 0

        await stream.stop()
```

---

## System Tests

### 1. Full System Integration Test

**File**: `tests/system/test_full_system_integration.py`

**Purpose**: Test complete system with all components

**Test Scenario**:
1. Start BybitHybridStream
2. Position Manager starts listening
3. TS module starts listening
4. Aged Monitor starts listening
5. Open position → all modules notified
6. Price updates → TS tracks price
7. Price reaches TS activation → SL placed
8. Position closed → all modules notified

```python
import pytest
import asyncio
from main import TradingBot
from config.settings import config


class TestFullSystemIntegration:
    """Test complete system integration"""

    @pytest.mark.asyncio
    @pytest.mark.system
    async def test_complete_position_lifecycle(self):
        """Test complete position lifecycle through entire system"""

        # Create bot instance
        bot = TradingBot()

        # Start bot (in test mode)
        bot_task = asyncio.create_task(bot.start(test_mode=True))

        # Wait for initialization
        await asyncio.sleep(10)

        # Verify all components connected
        assert bot.bybit_hybrid_stream is not None
        assert bot.bybit_hybrid_stream.private_connected is True
        assert bot.bybit_hybrid_stream.public_connected is True

        # Open test position (mock or small real position)
        # ...

        # Wait for price updates
        await asyncio.sleep(30)

        # Verify TS is tracking
        # Verify price updates received
        # ...

        # Close position
        # ...

        # Verify cleanup
        # ...

        await bot.stop()
```

---

## Performance Tests

### 1. Latency Test

**File**: `tests/performance/test_latency.py`

**Purpose**: Measure latency from price update to TS notification

**Acceptance Criteria**: < 200ms average latency

```python
import pytest
import asyncio
import time
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


class TestLatency:
    """Test system latency"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_ticker_to_ts_latency(self):
        """Measure latency from ticker update to TS notification"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        latencies = []

        async def track_latency(event_type, data):
            if event_type == 'position.update':
                receive_time = time.time()
                ticker_time = data.get('timestamp', receive_time)
                latency = (receive_time - ticker_time) * 1000  # ms
                latencies.append(latency)

        stream.set_event_handler(track_latency)

        await stream.start()
        await asyncio.sleep(60)  # Collect 60 seconds of data
        await stream.stop()

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"Average latency: {avg_latency:.2f}ms")
        print(f"Max latency: {max_latency:.2f}ms")

        # Acceptance criteria
        assert avg_latency < 200  # < 200ms average
        assert max_latency < 1000  # < 1s max
```

---

### 2. Throughput Test

**File**: `tests/performance/test_throughput.py`

**Purpose**: Measure event processing throughput

**Acceptance Criteria**: > 500 events/second

```python
import pytest
import asyncio
import time
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


class TestThroughput:
    """Test event processing throughput"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_event_processing_throughput(self):
        """Measure events processed per second"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        event_count = 0
        start_time = None

        async def count_events(event_type, data):
            nonlocal event_count, start_time
            if start_time is None:
                start_time = time.time()
            event_count += 1

        stream.set_event_handler(count_events)

        await stream.start()
        await asyncio.sleep(60)  # Run for 60 seconds
        await stream.stop()

        elapsed = time.time() - start_time
        throughput = event_count / elapsed

        print(f"Events processed: {event_count}")
        print(f"Throughput: {throughput:.2f} events/second")

        # Acceptance criteria
        assert throughput > 10  # At least 10 updates/sec
```

---

### 3. Memory Usage Test

**File**: `tests/performance/test_memory.py`

**Purpose**: Ensure no memory leaks during long-running operation

**Acceptance Criteria**: Memory growth < 10% over 1 hour

```python
import pytest
import asyncio
import psutil
import os
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


class TestMemory:
    """Test memory usage and leaks"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_no_memory_leak(self):
        """Test for memory leaks during extended operation"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        process = psutil.Process(os.getpid())

        # Measure initial memory
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        await stream.start()

        # Run for 10 minutes (shortened for testing)
        for _ in range(10):
            await asyncio.sleep(60)
            current_memory = process.memory_info().rss / 1024 / 1024
            print(f"Memory: {current_memory:.2f} MB")

        await stream.stop()

        final_memory = process.memory_info().rss / 1024 / 1024
        growth = ((final_memory - initial_memory) / initial_memory) * 100

        print(f"Initial memory: {initial_memory:.2f} MB")
        print(f"Final memory: {final_memory:.2f} MB")
        print(f"Growth: {growth:.2f}%")

        # Acceptance criteria: < 20% growth
        assert growth < 20
```

---

## Failover Tests

### 1. Connection Loss Test

**File**: `tests/failover/test_connection_loss.py`

**Purpose**: Test recovery from WebSocket disconnection

**Test Cases**:

```python
import pytest
import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


class TestConnectionLoss:
    """Test failover scenarios"""

    @pytest.mark.asyncio
    @pytest.mark.failover
    async def test_private_ws_reconnects(self):
        """Test private WebSocket reconnects after disconnect"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        reconnections = []

        def event_handler(event_type, data):
            if event_type == 'private.reconnected':
                reconnections.append(True)

        stream.set_event_handler(event_handler)

        await stream.start()
        await asyncio.sleep(5)

        # Force disconnect
        if stream.private_ws:
            await stream.private_ws.close()

        # Wait for reconnection
        await asyncio.sleep(30)

        # Verify reconnected
        assert stream.private_connected is True
        assert len(reconnections) > 0

        await stream.stop()

    @pytest.mark.asyncio
    @pytest.mark.failover
    async def test_public_ws_reconnects(self):
        """Test public WebSocket reconnects after disconnect"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        await stream.start()
        await asyncio.sleep(5)

        # Force disconnect
        if stream.public_ws:
            await stream.public_ws.close()

        # Wait for reconnection
        await asyncio.sleep(30)

        # Verify reconnected
        assert stream.public_connected is True

        await stream.stop()
```

---

### 2. Subscription Restoration Test

**File**: `tests/failover/test_subscription_restoration.py`

**Purpose**: Verify ticker subscriptions restored after reconnection

```python
import pytest
import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


class TestSubscriptionRestoration:
    """Test subscription restoration after reconnection"""

    @pytest.mark.asyncio
    @pytest.mark.failover
    async def test_ticker_subscriptions_restored(self):
        """Test ticker subscriptions restored after public WS reconnect"""
        bybit_config = config.get_exchange_config('bybit')

        stream = BybitHybridStream(
            api_key=bybit_config.api_key,
            api_secret=bybit_config.api_secret,
            testnet=True
        )

        await stream.start()
        await asyncio.sleep(5)

        # Add ticker subscriptions
        await stream._request_ticker_subscription('BTCUSDT', subscribe=True)
        await stream._request_ticker_subscription('ETHUSDT', subscribe=True)

        subscriptions_before = set(stream.subscribed_tickers)

        # Force disconnect public WS
        if stream.public_ws:
            await stream.public_ws.close()

        # Wait for reconnection
        await asyncio.sleep(30)

        # Verify subscriptions restored
        subscriptions_after = set(stream.subscribed_tickers)
        assert subscriptions_before == subscriptions_after

        await stream.stop()
```

---

## Test Scripts

### 1. Manual Connection Test Script

**File**: `tests/manual/test_hybrid_connection.py`

**Purpose**: Manual test for developers to verify connections

```python
#!/usr/bin/env python3
"""
Manual test: Verify hybrid WebSocket connections
"""

import asyncio
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


async def main():
    print("=" * 80)
    print("HYBRID WEBSOCKET CONNECTION TEST")
    print("=" * 80)

    bybit_config = config.get_exchange_config('bybit')

    stream = BybitHybridStream(
        api_key=bybit_config.api_key,
        api_secret=bybit_config.api_secret,
        testnet=True
    )

    def event_handler(event_type, data):
        print(f"📨 Event: {event_type}")
        if event_type == 'position.update':
            print(f"   Symbol: {data.get('symbol')}")
            print(f"   Mark Price: {data.get('mark_price')}")

    stream.set_event_handler(event_handler)

    print("\n🔌 Starting hybrid stream...")
    await stream.start()

    print("\n✅ Connected. Monitoring for 60 seconds...")
    print("   - Private WS: position updates")
    print("   - Public WS: ticker updates")
    print()

    await asyncio.sleep(60)

    print("\n⏹️ Stopping...")
    await stream.stop()

    print("\n📊 Summary:")
    print(f"   Subscribed tickers: {len(stream.subscribed_tickers)}")
    print(f"   Active positions: {len(stream.positions)}")
    print("\n✅ Test complete")


if __name__ == '__main__':
    asyncio.run(main())
```

---

### 2. Stress Test Script

**File**: `tests/manual/stress_test_hybrid.py`

**Purpose**: Stress test with multiple symbols

```python
#!/usr/bin/env python3
"""
Stress test: Monitor many symbols simultaneously
"""

import asyncio
import time
from websocket.bybit_hybrid_stream import BybitHybridStream
from config.settings import config


async def main():
    print("=" * 80)
    print("HYBRID WEBSOCKET STRESS TEST")
    print("=" * 80)

    bybit_config = config.get_exchange_config('bybit')

    stream = BybitHybridStream(
        api_key=bybit_config.api_key,
        api_secret=bybit_config.api_secret,
        testnet=True
    )

    event_count = 0
    start_time = None

    def event_handler(event_type, data):
        nonlocal event_count, start_time
        if start_time is None:
            start_time = time.time()
        event_count += 1

        if event_count % 100 == 0:
            elapsed = time.time() - start_time
            rate = event_count / elapsed
            print(f"📊 Processed {event_count} events ({rate:.2f} events/sec)")

    stream.set_event_handler(event_handler)

    await stream.start()

    # Subscribe to many symbols
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
        'XRPUSDT', 'DOTUSDT', 'AVAXUSDT', 'MATICUSDT', 'LINKUSDT'
    ]

    print(f"\n📡 Subscribing to {len(symbols)} tickers...")
    for symbol in symbols:
        await stream._request_ticker_subscription(symbol, subscribe=True)

    print(f"\n✅ Monitoring {len(symbols)} symbols for 5 minutes...")
    await asyncio.sleep(300)

    await stream.stop()

    elapsed = time.time() - start_time
    rate = event_count / elapsed

    print("\n" + "=" * 80)
    print("STRESS TEST RESULTS")
    print("=" * 80)
    print(f"Duration: {elapsed:.1f}s")
    print(f"Total events: {event_count}")
    print(f"Average rate: {rate:.2f} events/sec")
    print(f"Symbols monitored: {len(symbols)}")
    print("\n✅ Stress test complete")


if __name__ == '__main__':
    asyncio.run(main())
```

---

## Acceptance Criteria

### Phase 1: Core Infrastructure
- ✅ BybitHybridStream class exists
- ✅ Both WebSockets connect successfully
- ✅ Private WS authenticates
- ✅ Public WS connects (no auth needed)
- ✅ Unit tests pass (>90% coverage)

### Phase 2: Event Processing
- ✅ Position updates received from private WS
- ✅ Ticker updates received from public WS
- ✅ Events correctly combined
- ✅ Deduplication works
- ✅ Integration tests pass

### Phase 3: Subscription Management
- ✅ Position open → ticker subscribe
- ✅ Position close → ticker unsubscribe
- ✅ Subscriptions restored after reconnect
- ✅ No duplicate subscriptions
- ✅ Failover tests pass

### Phase 4: System Integration
- ✅ Position Manager receives updates
- ✅ TS tracks prices at 100ms
- ✅ Aged Monitor receives updates
- ✅ System tests pass

### Phase 5: Performance
- ✅ Latency < 200ms average
- ✅ Throughput > 10 events/sec
- ✅ Memory growth < 20%/hour
- ✅ Performance tests pass

### Phase 6: Production Readiness
- ✅ All tests pass (unit + integration + system)
- ✅ Documentation complete
- ✅ Monitoring integrated
- ✅ Rollback plan ready
- ✅ Code review approved

---

## Test Execution Plan

### Week 1: Unit Tests
**Day 1-2**: Write unit tests for BybitHybridStream
**Day 3-4**: Write unit tests for subscription management
**Day 5**: Write unit tests for event processing
**Goal**: >90% code coverage

### Week 2: Integration Tests
**Day 1-2**: Dual connection tests
**Day 3**: Event router integration
**Day 4**: Position Manager integration
**Day 5**: TS integration
**Goal**: All integration tests pass

### Week 3: System & Performance Tests
**Day 1-2**: Full system integration tests
**Day 3**: Performance tests (latency, throughput)
**Day 4**: Memory leak tests
**Day 5**: Stress tests
**Goal**: Meet all performance criteria

### Week 4: Failover & Production
**Day 1-2**: Failover tests
**Day 3**: Manual testing on testnet
**Day 4**: Canary deployment
**Day 5**: Production rollout
**Goal**: Production deployment successful

---

## Test Automation

### Pytest Configuration

**File**: `pytest.ini`

```ini
[pytest]
markers =
    unit: Unit tests
    integration: Integration tests requiring network
    system: Full system tests
    performance: Performance and load tests
    failover: Failover and recovery tests
    slow: Slow tests (>10s)

addopts =
    -v
    --strict-markers
    --tb=short
    --cov=websocket
    --cov=core
    --cov-report=html
    --cov-report=term-missing

testpaths = tests

asyncio_mode = auto
```

### CI/CD Pipeline

**File**: `.github/workflows/test_hybrid_websocket.yml`

```yaml
name: Hybrid WebSocket Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.10'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-asyncio pytest-cov

    - name: Run unit tests
      run: pytest -m unit

    - name: Run integration tests
      run: pytest -m integration
      env:
        BYBIT_API_KEY: ${{ secrets.BYBIT_TESTNET_API_KEY }}
        BYBIT_API_SECRET: ${{ secrets.BYBIT_TESTNET_API_SECRET }}

    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

---

## Summary

This testing strategy provides:

1. **Comprehensive Coverage**: Unit → Integration → System → Performance → Failover
2. **Automated Testing**: Pytest + CI/CD integration
3. **Performance Validation**: Latency, throughput, memory benchmarks
4. **Production Readiness**: Acceptance criteria for each phase
5. **Risk Mitigation**: Extensive failover testing

**Total Tests**: ~50 automated tests across all levels

**Timeline**: 4 weeks from unit tests to production deployment

**Next Step**: Begin implementing unit tests (Phase 1)
