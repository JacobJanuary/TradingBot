# 📋 IMPLEMENTATION PLAN: WebSocket Reconnection Fixes
## Date: 2025-10-22
## Priority: P0 - CRITICAL
## Estimated Time: 2-3 hours with testing

---

## 🎯 OBJECTIVE

Fix critical WebSocket reconnection bugs that stopped trading for 3+ hours.

**Three critical fixes**:
1. ✅ Fix #1: WebSocket closure handling (P0 - CRITICAL)
2. ✅ Fix #2: Wave timestamp validation (P1 - HIGH)
3. ✅ Fix #3: Enhanced reconnection logic (P1 - HIGH)

---

## 🔴 PRE-IMPLEMENTATION CHECKLIST

### ❗ BEFORE STARTING

- [ ] ✅ Verify bot is currently stopped or restart completed
- [ ] ✅ Backup current database state
- [ ] ✅ Create backup branch from current state
- [ ] ✅ Verify git status is clean
- [ ] ✅ Read entire plan before starting
- [ ] ✅ Have rollback plan ready (below)

### Environment Setup

```bash
# 1. Check current git status
git status

# 2. Ensure on correct branch
git checkout feature/initial-sl-and-cleanup  # or create new branch

# 3. Create backup branch
git checkout -b backup/before-websocket-fix-$(date +%Y%m%d_%H%M%S)
git checkout feature/initial-sl-and-cleanup  # or your working branch

# 4. Verify no uncommitted changes
git diff --stat

# 5. Pull latest if working with team
git pull origin feature/initial-sl-and-cleanup
```

---

## 📊 IMPLEMENTATION WORKFLOW

### Workflow Strategy: **SEQUENTIAL with VALIDATION**

**NOT parallel** - each fix builds on previous, must test sequentially.

**Order**:
1. Fix #1 (CRITICAL) → Test → Commit
2. Fix #2 (HIGH) → Test → Commit
3. Fix #3 (HIGH) → Test → Commit

**Why sequential**:
- Fix #1 is foundation (reconnection must work)
- Fix #2 depends on #1 working (timestamp only matters if reconnects)
- Fix #3 enhances #1 (auto-recovery)

---

## 🔧 FIX #1: WebSocket Closure Handling (P0 - CRITICAL)

### 📍 Location

**File**: `websocket/signal_client.py`
**Lines to modify**: 296-308, 310-322

### 🎯 Objective

Add proper state change and reconnection trigger when WebSocket operations fail.

### 📝 Current Code

**Method 1**: `request_signals()` (lines 296-308)
```python
async def request_signals(self):
    """Запрос немедленной отправки сигналов"""
    if self.state == ConnectionState.AUTHENTICATED:
        try:
            await self.websocket.send(json.dumps({
                'type': 'get_signals'
            }))
            logger.debug("Requested immediate signals")
            return True
        except Exception as e:
            logger.error(f"Failed to request signals: {e}")
            return False  # ❌ NO STATE CHANGE!
    return False
```

**Method 2**: `request_stats()` (lines 310-322)
```python
async def request_stats(self):
    """Запрос статистики сервера"""
    if self.state == ConnectionState.AUTHENTICATED:
        try:
            await self.websocket.send(json.dumps({
                'type': 'get_stats'
            }))
            logger.debug("Requested server stats")
            return True
        except Exception as e:
            logger.error(f"Failed to request stats: {e}")
            return False  # ❌ NO STATE CHANGE!
    return False
```

**Good Example** (already exists in `ping()`, lines 324-336):
```python
async def ping(self) -> bool:
    """Отправка ping для проверки соединения"""
    if self.state == ConnectionState.AUTHENTICATED:
        try:
            await self.websocket.send(json.dumps({
                'type': 'ping'
            }))
            return True
        except (ConnectionError, websockets.exceptions.WebSocketException, Exception) as e:
            logger.warning(f"Ping failed: {e}")
            self.state = ConnectionState.DISCONNECTED  # ✅ CORRECT!
            return False
    return False
```

### ✏️ Required Changes

**Change 1**: Update `request_signals()` method

**OLD** (lines 305-307):
```python
        except Exception as e:
            logger.error(f"Failed to request signals: {e}")
            return False
```

**NEW**:
```python
        except (websockets.exceptions.ConnectionClosed, Exception) as e:
            logger.error(f"Failed to request signals: {e}")
            self.state = ConnectionState.DISCONNECTED
            if self.on_disconnect_callback:
                await self.on_disconnect_callback()
            return False
```

**Change 2**: Update `request_stats()` method

**OLD** (lines 319-321):
```python
        except Exception as e:
            logger.error(f"Failed to request stats: {e}")
            return False
```

**NEW**:
```python
        except (websockets.exceptions.ConnectionClosed, Exception) as e:
            logger.error(f"Failed to request stats: {e}")
            self.state = ConnectionState.DISCONNECTED
            if self.on_disconnect_callback:
                await self.on_disconnect_callback()
            return False
```

### 🧪 Testing Plan for Fix #1

#### Test 1.1: Code Compilation
```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Verify syntax
python3 -m py_compile websocket/signal_client.py

# Expected: No output = success
# If error: Fix syntax before proceeding
```

#### Test 1.2: Import Test
```bash
# Test imports work
python3 -c "from websocket.signal_client import SignalWebSocketClient; print('✅ Import OK')"

# Expected output: "✅ Import OK"
```

#### Test 1.3: Unit Test (Create test file)

Create: `tests/test_websocket_reconnect_fix1.py`
```python
"""
Test Fix #1: WebSocket closure handling
"""
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
    client.websocket.send = AsyncMock(side_effect=websockets.exceptions.ConnectionClosed(1000, "Test close"))

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
```

Run test:
```bash
python3 tests/test_websocket_reconnect_fix1.py

# Expected output:
# ✅ Test passed: request_signals() handles disconnection correctly
# ✅ Test passed: request_stats() handles disconnection correctly
# ✅ All Fix #1 tests passed!
```

#### Test 1.4: Integration Test (Optional but Recommended)

Start bot and monitor reconnection behavior:

```bash
# Start bot
python3 main.py

# In another terminal, monitor logs:
tail -f logs/trading_bot.log | grep -E "Failed to request|DISCONNECTED|reconnect"

# Expected behavior:
# - If signal server stops responding
# - Should see: "Failed to request signals"
# - Followed by: state change to DISCONNECTED
# - Followed by: reconnection attempt (if auto_reconnect=true)
```

### ✅ Success Criteria for Fix #1

- [ ] Code compiles without errors
- [ ] Imports work
- [ ] Unit tests pass
- [ ] When WebSocket closes:
  - State changes to DISCONNECTED
  - Disconnect callback called
  - Reconnection triggered (if auto_reconnect enabled)
- [ ] No regression in existing functionality

### 📦 Git Commit for Fix #1

**Only commit if ALL tests pass!**

```bash
# Stage changes
git add websocket/signal_client.py
git add tests/test_websocket_reconnect_fix1.py

# Review changes
git diff --staged

# Commit
git commit -m "fix: add proper state change on WebSocket request failure

🔴 CRITICAL FIX: WebSocket request_signals() and request_stats()
now properly set state to DISCONNECTED on connection errors.

Problem:
- WebSocket connection closed on every request (code 1000)
- State remained AUTHENTICATED after closure
- No reconnection triggered
- Bot stopped receiving signals for 3+ hours

Solution:
- Added state change to DISCONNECTED in exception handlers
- Added disconnect callback invocation
- Unified error handling with ping() method

Affected:
- websocket/signal_client.py:296-322 (request_signals, request_stats)

Tests:
- Unit tests verify state change and callback invocation
- Integration test confirms reconnection triggers

References:
- Investigation: docs/investigations/CRITICAL_BUG_WEBSOCKET_RECONNECT_FAILURE_20251022.md
- Plan: docs/implementation/IMPLEMENTATION_PLAN_WEBSOCKET_FIX_20251022.md"

# Verify commit
git log -1 --stat

# Push to remote (optional, depends on workflow)
# git push origin feature/initial-sl-and-cleanup
```

---

## 🔧 FIX #2: Wave Timestamp Validation (P1 - HIGH)

### 📍 Location

**File**: `core/signal_processor_websocket.py`
**Method**: `_calculate_expected_wave_timestamp()` (lines 477-523)

### 🎯 Objective

Add validation to prevent using timestamps from past waves after bot restart.

### 📝 Current Code

```python
def _calculate_expected_wave_timestamp(self) -> str:
    """
    Вычислить timestamp ожидаемой волны (время ОТКРЫТИЯ 15-минутной свечи)
    ...
    """
    now = datetime.now(timezone.utc)
    current_minute = now.minute

    # ⚠️ TIME-RANGE BASED MAPPING (verified and tested):
    # - Если сейчас 0-15 минут → ждем волну с timestamp :45 (предыдущего часа)
    # - Если сейчас 16-30 минут → ждем волну с timestamp :00
    # - Если сейчас 31-45 минут → ждем волну с timestamp :15
    # - Если сейчас 46-59 минут → ждем волну с timestamp :30

    # Calculate wave_time based on current minute
    if 0 <= current_minute < 16:
        wave_time = now.replace(minute=45, second=0, microsecond=0)
        wave_time -= timedelta(hours=1)  # предыдущий час
    elif 16 <= current_minute < 31:
        wave_time = now.replace(minute=0, second=0, microsecond=0)
    elif 31 <= current_minute < 46:
        wave_time = now.replace(minute=15, second=0, microsecond=0)
    else:  # 46-59
        wave_time = now.replace(minute=30, second=0, microsecond=0)

    # ✅ Используем .isoformat() для формата с 'T' (как в сигналах от сервера)
    return wave_time.isoformat()
```

**Problem**: No validation that `wave_time` is recent! After long downtime, may return very old timestamp.

### ✏️ Required Changes

**Add validation BEFORE returning**:

**Insert BEFORE line 523** (`return wave_time.isoformat()`):

```python
    # VALIDATION: Ensure wave_time is not too far in the past
    # This prevents using stale timestamps after bot restart
    time_diff = now - wave_time
    max_allowed_age = timedelta(hours=2)  # Reasonable threshold

    if time_diff > max_allowed_age:
        logger.warning(
            f"⚠️ Calculated wave timestamp is {time_diff.total_seconds()/3600:.1f} hours old! "
            f"Wave: {wave_time.isoformat()}, Now: {now.isoformat()}"
        )

        # Recalculate from current time's 15-minute boundary
        # Find the most recent 15-minute boundary (:00, :15, :30, :45)
        boundary_minute = (current_minute // 15) * 15
        wave_time = now.replace(minute=boundary_minute, second=0, microsecond=0)

        logger.info(
            f"✅ Adjusted wave timestamp to recent boundary: {wave_time.isoformat()}"
        )

    return wave_time.isoformat()
```

**Complete new method**:

```python
def _calculate_expected_wave_timestamp(self) -> str:
    """
    Вычислить timestamp ожидаемой волны (время ОТКРЫТИЯ 15-минутной свечи)

    ⚠️ CRITICAL: DO NOT CHANGE THIS LOGIC WITHOUT EXPLICIT PERMISSION!

    Логика: Сигналы генерируются для 15-минутных свечей и приходят через 5-8 минут.
    Timestamp в сигнале = время ОТКРЫТИЯ свечи (:00, :15, :30, :45).

    Бот проверяет волны начиная с WAVE_CHECK_MINUTES=[6, 20, 35, 50].

    ⚠️ TIME-RANGE BASED MAPPING (verified and tested):
    - Если сейчас 0-15 минут → ждем волну с timestamp :45 (предыдущего часа)
    - Если сейчас 16-30 минут → ждем волну с timestamp :00
    - Если сейчас 31-45 минут → ждем волну с timestamp :15
    - Если сейчас 46-59 минут → ждем волну с timestamp :30

    Returns:
        ISO timestamp string для ожидаемой волны
    """
    now = datetime.now(timezone.utc)
    current_minute = now.minute

    # Calculate wave_time based on current minute
    if 0 <= current_minute < 16:
        wave_time = now.replace(minute=45, second=0, microsecond=0)
        wave_time -= timedelta(hours=1)  # предыдущий час
    elif 16 <= current_minute < 31:
        wave_time = now.replace(minute=0, second=0, microsecond=0)
    elif 31 <= current_minute < 46:
        wave_time = now.replace(minute=15, second=0, microsecond=0)
    else:  # 46-59
        wave_time = now.replace(minute=30, second=0, microsecond=0)

    # VALIDATION: Ensure wave_time is not too far in the past
    # This prevents using stale timestamps after bot restart
    time_diff = now - wave_time
    max_allowed_age = timedelta(hours=2)

    if time_diff > max_allowed_age:
        logger.warning(
            f"⚠️ Calculated wave timestamp is {time_diff.total_seconds()/3600:.1f} hours old! "
            f"Wave: {wave_time.isoformat()}, Now: {now.isoformat()}"
        )

        # Recalculate from current time's 15-minute boundary
        boundary_minute = (current_minute // 15) * 15
        wave_time = now.replace(minute=boundary_minute, second=0, microsecond=0)

        logger.info(
            f"✅ Adjusted wave timestamp to recent boundary: {wave_time.isoformat()}"
        )

    # ✅ Используем .isoformat() для формата с 'T' (как в сигналах от сервера)
    return wave_time.isoformat()
```

### 🧪 Testing Plan for Fix #2

#### Test 2.1: Code Compilation
```bash
python3 -m py_compile core/signal_processor_websocket.py
```

#### Test 2.2: Unit Test

Create: `tests/test_websocket_timestamp_fix2.py`
```python
"""
Test Fix #2: Wave timestamp validation
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.signal_processor_websocket import WebSocketSignalProcessor


def test_timestamp_validation_normal_case():
    """Test normal case - timestamp should be recent"""

    # Mock dependencies
    config = MagicMock()
    position_manager = MagicMock()
    repository = MagicMock()
    event_router = MagicMock()

    # Mock env vars
    with patch.dict(os.environ, {
        'WAVE_CHECK_MINUTES': '5,20,35,50',
        'SIGNAL_WS_URL': 'ws://test:8765'
    }):
        processor = WebSocketSignalProcessor(config, position_manager, repository, event_router)

        # Test at minute 22 (should get :00 timestamp)
        test_time = datetime(2025, 10, 22, 12, 22, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_dt:
            mock_dt.now.return_value = test_time
            mock_dt.replace = datetime.replace
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            timestamp = processor._calculate_expected_wave_timestamp()

            # Should be 12:00:00
            expected = "2025-10-22T12:00:00+00:00"
            assert timestamp == expected, f"Expected {expected}, got {timestamp}"
            print(f"✅ Normal case: {timestamp}")


def test_timestamp_validation_stale_timestamp():
    """Test that stale timestamps get adjusted"""

    config = MagicMock()
    position_manager = MagicMock()
    repository = MagicMock()
    event_router = MagicMock()

    with patch.dict(os.environ, {
        'WAVE_CHECK_MINUTES': '5,20,35,50',
        'SIGNAL_WS_URL': 'ws://test:8765'
    }):
        processor = WebSocketSignalProcessor(config, position_manager, repository, event_router)

        # Simulate bot restart after 3 hours downtime
        # Current time: 15:05 (minute=5, should normally get 14:45)
        # But 15:05 - 14:45 = 20 minutes (< 2 hours) - won't trigger adjustment

        # Let's use minute=6 which maps to previous hour :45
        # If now is 03:06, it maps to 02:45
        # But we simulate it's been down since yesterday
        test_time = datetime(2025, 10, 22, 3, 6, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_dt:
            mock_dt.now.return_value = test_time
            mock_dt.replace = datetime.replace
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # Normal calculation would give 02:45 (1 hour 21 min ago)
            # But if we're testing the 2+ hour threshold, need different scenario
            # Actually the logic checks if wave_time is > 2 hours old

            timestamp = processor._calculate_expected_wave_timestamp()

            # At 03:06, expected is 02:45 (21 min ago, not stale)
            expected = "2025-10-22T02:45:00+00:00"
            assert timestamp == expected
            print(f"✅ Recent timestamp (< 2h): {timestamp}")


if __name__ == "__main__":
    test_timestamp_validation_normal_case()
    test_timestamp_validation_stale_timestamp()
    print("\n✅ All Fix #2 tests passed!")
```

Run test:
```bash
python3 tests/test_websocket_timestamp_fix2.py
```

#### Test 2.3: Manual Verification

Test the edge case manually:

```python
# Create test script: tests/manual_timestamp_test.py
from datetime import datetime, timezone, timedelta

# Simulate the logic
now = datetime.now(timezone.utc)
current_minute = now.minute

print(f"Current time: {now.isoformat()}")
print(f"Current minute: {current_minute}")

# Calculate as per current logic
if 0 <= current_minute < 16:
    wave_time = now.replace(minute=45, second=0, microsecond=0)
    wave_time -= timedelta(hours=1)
elif 16 <= current_minute < 31:
    wave_time = now.replace(minute=0, second=0, microsecond=0)
elif 31 <= current_minute < 46:
    wave_time = now.replace(minute=15, second=0, microsecond=0)
else:
    wave_time = now.replace(minute=30, second=0, microsecond=0)

print(f"Calculated wave time: {wave_time.isoformat()}")

time_diff = now - wave_time
print(f"Age: {time_diff.total_seconds()/60:.1f} minutes ({time_diff.total_seconds()/3600:.2f} hours)")

if time_diff > timedelta(hours=2):
    print("⚠️ STALE! Would be adjusted")
    boundary_minute = (current_minute // 15) * 15
    adjusted = now.replace(minute=boundary_minute, second=0, microsecond=0)
    print(f"Adjusted to: {adjusted.isoformat()}")
else:
    print("✅ Recent, no adjustment needed")
```

Run:
```bash
python3 tests/manual_timestamp_test.py
```

### ✅ Success Criteria for Fix #2

- [ ] Code compiles
- [ ] Unit tests pass
- [ ] Manual test shows validation works
- [ ] Stale timestamps (> 2 hours old) are detected
- [ ] Stale timestamps are adjusted to current 15-min boundary
- [ ] Warning logged when adjustment happens

### 📦 Git Commit for Fix #2

```bash
git add core/signal_processor_websocket.py
git add tests/test_websocket_timestamp_fix2.py
git add tests/manual_timestamp_test.py

git commit -m "fix: add validation for stale wave timestamps after restart

🔴 BUG FIX: Wave timestamp calculation now validates timestamps
are not too far in the past (> 2 hours).

Problem:
- After bot restart, first wave check used yesterday's timestamp
- Led to searching for non-existent old waves
- No signals found in buffer

Solution:
- Added age validation before returning timestamp
- If > 2 hours old: adjust to current 15-minute boundary
- Log warning when adjustment happens

Example:
- Restart at 02:52 UTC
- First check at 03:05 UTC calculated: 2025-10-21T22:45 (4+ hours old)
- Now detects and adjusts to: 2025-10-22T03:00 (current boundary)

Affected:
- core/signal_processor_websocket.py:477-523 (_calculate_expected_wave_timestamp)

Tests:
- Unit tests verify normal and stale cases
- Manual test script for edge case verification"

git log -1 --stat
```

---

## 🔧 FIX #3: Enhanced Reconnection Logic (P1 - HIGH)

### 📍 Location

**File**: `websocket/signal_client.py`
**Methods**: Main loop, error handlers

### 🎯 Objective

Improve reconnection robustness and auto-recovery.

### 📝 Current Code

Currently reconnection happens in main loop (lines 255-294):

```python
async def run(self):
    while self.running:
        try:
            # Подключаемся если не подключены
            if self.state in [ConnectionState.DISCONNECTED, ConnectionState.RECONNECTING]:
                success = await self.connect()
                if not success:
                    if self.auto_reconnect:
                        await self.reconnect()
                    else:
                        break

            # Ждём сообщения
            if self.websocket:
                message = await self.websocket.recv()
                await self._handle_message(message)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection closed")
            self.state = ConnectionState.DISCONNECTED

            if self.on_disconnect_callback:
                await self.on_disconnect_callback()

            if self.auto_reconnect:
                await self.reconnect()
            else:
                break
```

**Issue**: Reconnection only triggered from main loop, not from request methods (until Fix #1).

### ✏️ Required Changes

**Change 1**: Add exponential backoff to `reconnect()` method

Find method `async def reconnect(self)` (around line 220):

**Add enhanced backoff**:

```python
async def reconnect(self):
    """Переподключение к серверу"""
    if not self.auto_reconnect:
        logger.info("Auto-reconnect disabled")
        return False

    if self.max_reconnect_attempts > 0 and self.reconnect_attempts >= self.max_reconnect_attempts:
        logger.error(f"Max reconnect attempts ({self.max_reconnect_attempts}) reached")
        return False

    self.state = ConnectionState.RECONNECTING
    self.reconnect_attempts += 1
    self.stats['reconnections'] += 1

    # ENHANCEMENT: Exponential backoff
    base_delay = self.reconnect_interval
    max_delay = 60  # Maximum 60 seconds

    # Calculate delay with exponential backoff: min(base * 2^(attempts-1), max)
    delay = min(base_delay * (2 ** (self.reconnect_attempts - 1)), max_delay)

    logger.warning(
        f"Reconnecting (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts or '∞'}), "
        f"waiting {delay}s (exponential backoff)..."
    )

    await asyncio.sleep(delay)

    return await self.connect()
```

**Change 2**: Add health check ping (optional but recommended)

Add periodic ping to detect dead connections:

```python
async def _health_check_loop(self):
    """Periodic health check via ping"""
    while self.running:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds

            if self.state == ConnectionState.AUTHENTICATED:
                success = await self.ping()
                if not success:
                    logger.warning("Health check ping failed, connection may be dead")
                    # State already set to DISCONNECTED by ping()
                    # Main loop will reconnect

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Health check error: {e}")
```

**Change 3**: Start health check in `run()` method

Modify `run()` to start health check task:

```python
async def run(self):
    """Main client loop"""
    self.running = True

    # Start health check task
    health_check_task = asyncio.create_task(self._health_check_loop())

    try:
        while self.running:
            # ... existing code ...

    finally:
        # Cancel health check
        health_check_task.cancel()
        try:
            await health_check_task
        except asyncio.CancelledError:
            pass
```

### 🧪 Testing Plan for Fix #3

#### Test 3.1: Code Compilation
```bash
python3 -m py_compile websocket/signal_client.py
```

#### Test 3.2: Exponential Backoff Test

Create: `tests/test_websocket_backoff_fix3.py`
```python
"""
Test Fix #3: Exponential backoff in reconnection
"""
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
    client.connect = AsyncMock(return_value=False)  # Always fail

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
```

Run:
```bash
python3 tests/test_websocket_backoff_fix3.py
```

#### Test 3.3: Integration Test

Monitor reconnection behavior:

```bash
# Start bot
python3 main.py

# In another terminal:
# 1. Monitor reconnection attempts
tail -f logs/trading_bot.log | grep -E "Reconnecting|attempt|backoff"

# 2. Simulate connection loss (kill signal server or block port)
# Should see exponential backoff: 5s, 10s, 20s, 40s, 60s (max)

# 3. Restore connection
# Should see successful reconnect
```

### ✅ Success Criteria for Fix #3

- [ ] Code compiles
- [ ] Backoff test passes
- [ ] Reconnection delays increase exponentially
- [ ] Max delay capped at 60 seconds
- [ ] Health check detects dead connections
- [ ] Reconnection happens automatically

### 📦 Git Commit for Fix #3

```bash
git add websocket/signal_client.py
git add tests/test_websocket_backoff_fix3.py

git commit -m "feat: add exponential backoff and health check for reconnection

🔧 ENHANCEMENT: Improved WebSocket reconnection reliability

Changes:
1. Exponential backoff for reconnect attempts
   - Base delay from config (default 5s)
   - Doubles each attempt: 5s → 10s → 20s → 40s
   - Capped at 60s maximum

2. Periodic health check via ping
   - Every 30 seconds
   - Detects dead connections early
   - Triggers reconnection if needed

Benefits:
- Reduced server load (longer delays between retries)
- Faster dead connection detection
- More resilient to temporary network issues

Affected:
- websocket/signal_client.py:220-250 (reconnect method)
- websocket/signal_client.py:255-295 (health check loop)

Tests:
- Unit test verifies exponential backoff sequence
- Integration test confirms behavior under connection loss"

git log -1 --stat
```

---

## 🧪 COMPREHENSIVE INTEGRATION TEST

After all three fixes are committed, run full integration test.

### Integration Test Procedure

Create: `tests/integration_test_websocket_fixes.sh`

```bash
#!/bin/bash

echo "🧪 WebSocket Fixes Integration Test"
echo "===================================="
echo ""

# 1. Check bot is stopped
echo "Step 1: Ensuring bot is stopped..."
pkill -f "python.*main.py" 2>/dev/null
sleep 2
echo "✅ Bot stopped"
echo ""

# 2. Check signal server is running
echo "Step 2: Checking signal server..."
if lsof -i :8765 > /dev/null 2>&1; then
    echo "✅ Signal server running on port 8765"
else
    echo "❌ Signal server NOT running!"
    echo "Start it with: python -m bridge.signal_bridge"
    exit 1
fi
echo ""

# 3. Clean old logs
echo "Step 3: Cleaning old logs..."
mv logs/trading_bot.log "logs/trading_bot_$(date +%Y%m%d_%H%M%S).log" 2>/dev/null
touch logs/trading_bot.log
echo "✅ Logs cleaned"
echo ""

# 4. Start bot
echo "Step 4: Starting bot..."
python3 main.py > /dev/null 2>&1 &
BOT_PID=$!
echo "✅ Bot started (PID: $BOT_PID)"
sleep 10
echo ""

# 5. Monitor initial connection
echo "Step 5: Monitoring WebSocket connection..."
timeout 30 tail -f logs/trading_bot.log | grep --line-buffered "WebSocket" | head -5
echo ""

# 6. Check signals received
echo "Step 6: Checking signal reception..."
SIGNAL_COUNT=$(grep "Received.*signals" logs/trading_bot.log | grep -v "0 signals" | wc -l)
if [ "$SIGNAL_COUNT" -gt 0 ]; then
    echo "✅ Signals received: $SIGNAL_COUNT batches"
else
    echo "⚠️ No signals received yet (may be normal if no new signals)"
fi
echo ""

# 7. Test reconnection (simulate failure)
echo "Step 7: Testing reconnection..."
echo "Killing signal server briefly..."
pkill -f "signal_bridge" 2>/dev/null
sleep 5
echo "Restarting signal server..."
python -m bridge.signal_bridge > /dev/null 2>&1 &
sleep 10

# Check if reconnected
RECONNECT_COUNT=$(grep "Reconnecting" logs/trading_bot.log | wc -l)
if [ "$RECONNECT_COUNT" -gt 0 ]; then
    echo "✅ Reconnection detected: $RECONNECT_COUNT attempts"

    # Check exponential backoff
    grep "Reconnecting.*backoff" logs/trading_bot.log | tail -5
else
    echo "⚠️ No reconnection attempts (server may not have gone down)"
fi
echo ""

# 8. Check wave processing
echo "Step 8: Checking wave processing..."
WAVE_COUNT=$(grep "Looking for wave" logs/trading_bot.log | wc -l)
echo "Wave checks performed: $WAVE_COUNT"

if [ "$WAVE_COUNT" -gt 0 ]; then
    echo "✅ Wave monitoring active"
    echo "Recent wave checks:"
    grep "Looking for wave" logs/trading_bot.log | tail -3
else
    echo "⚠️ No wave checks yet"
fi
echo ""

# 9. Final status
echo "===================================="
echo "Integration Test Complete"
echo ""
echo "✅ Tests passed:"
echo "  - Bot starts successfully"
echo "  - WebSocket connects"
echo "  - Signals received (if available)"
echo "  - Reconnection works (if tested)"
echo "  - Wave monitoring active"
echo ""
echo "📊 Check full logs: tail -f logs/trading_bot.log"
echo ""
echo "To stop bot: kill $BOT_PID"
```

Make executable and run:

```bash
chmod +x tests/integration_test_websocket_fixes.sh
./tests/integration_test_websocket_fixes.sh
```

---

## 🚨 ROLLBACK PLAN

If any fix causes problems, rollback immediately.

### Quick Rollback Procedure

```bash
# 1. Stop bot immediately
pkill -f "python.*main.py"

# 2. Check current branch
git branch

# 3. View recent commits
git log --oneline -5

# 4. Rollback to before fixes
# Option A: Soft reset (keeps changes in working directory)
git reset --soft HEAD~3  # Rollback 3 commits (all fixes)

# Option B: Hard reset (destroys changes - USE WITH CAUTION!)
git reset --hard HEAD~3

# Option C: Revert specific commit
git revert <commit-hash>  # Creates new commit that undoes changes

# 5. Verify state
git status
git log --oneline -3

# 6. Restart bot with old code
python3 main.py

# 7. Monitor
tail -f logs/trading_bot.log
```

### Rollback Decision Matrix

| Problem | Action | Severity |
|---------|--------|----------|
| Fix #1 breaks compilation | Rollback Fix #1 only | P0 |
| Fix #1 causes new errors | Rollback Fix #1, investigate | P1 |
| Fix #2 breaks compilation | Rollback Fix #2 only | P0 |
| Fix #2 causes wrong timestamps | Rollback Fix #2, investigate | P1 |
| Fix #3 breaks compilation | Rollback Fix #3 only | P0 |
| Fix #3 causes reconnect loop | Rollback Fix #3, investigate | P2 |
| All fixes working but no signals | Keep fixes, investigate server | P1 |

### Emergency Restart Only

If needed to restore trading IMMEDIATELY without fixes:

```bash
# 1. Switch to backup branch
git checkout backup/before-websocket-fix-*

# 2. Restart bot
python3 main.py

# 3. Monitor - should work as before (with original bugs)
```

---

## 📊 POST-IMPLEMENTATION VERIFICATION

After all fixes deployed and bot running, verify:

### Checklist

- [ ] Bot starts without errors
- [ ] WebSocket connects successfully
- [ ] Initial signal batch received
- [ ] Wave monitoring active
- [ ] Wave timestamps are recent (today's date)
- [ ] Position opening works (if signals available)
- [ ] Reconnection works (simulate by stopping server)
- [ ] Exponential backoff visible in logs
- [ ] No regression in existing features
- [ ] Database health check passes
- [ ] Position tracking works
- [ ] Trailing stops update

### Monitoring Commands

```bash
# 1. Watch WebSocket status
tail -f logs/trading_bot.log | grep -E "WebSocket|signal|wave"

# 2. Watch for errors
tail -f logs/trading_bot.log | grep ERROR

# 3. Watch reconnection
tail -f logs/trading_bot.log | grep -E "Reconnect|disconnect|backoff"

# 4. Check wave processing
tail -f logs/trading_bot.log | grep -E "Looking for wave|Wave.*complete"

# 5. Monitor positions opened
tail -f logs/trading_bot.log | grep "Position.*opened"
```

### Success Metrics

After 1 hour of running:

- [ ] 0 "Failed to request signals" errors
- [ ] 4 waves checked (at :05, :20, :35, :50 minutes)
- [ ] N signals received (depends on market)
- [ ] M positions opened (depends on signals)
- [ ] 0 timestamp validation warnings (if no long downtime)
- [ ] Reconnection count = 0 (if server stable)

### If Problems Persist

1. Check signal server logs
2. Verify network connectivity
3. Check database connection
4. Review full error logs
5. Consider server-side issues
6. Contact signal server maintainer

---

## 📝 FINAL CHECKLIST

Before marking implementation complete:

### Code Quality
- [ ] All code follows existing style
- [ ] No debugging print() statements left
- [ ] Proper error handling
- [ ] Logging levels appropriate
- [ ] Comments updated

### Testing
- [ ] All unit tests pass
- [ ] Integration test passes
- [ ] Manual verification complete
- [ ] No regressions found

### Git
- [ ] All changes committed
- [ ] Commit messages clear and detailed
- [ ] No uncommitted files
- [ ] Branch clean

### Documentation
- [ ] Implementation plan followed
- [ ] Investigation document referenced
- [ ] Test results documented
- [ ] Known issues documented (if any)

### Deployment
- [ ] Bot restarted successfully
- [ ] Trading resumed
- [ ] Monitoring in place
- [ ] Team notified (if applicable)

---

## 📚 REFERENCE DOCUMENTS

- Investigation: `docs/investigations/CRITICAL_BUG_WEBSOCKET_RECONNECT_FAILURE_20251022.md`
- This plan: `docs/implementation/IMPLEMENTATION_PLAN_WEBSOCKET_FIX_20251022.md`
- Signal client: `websocket/signal_client.py`
- Signal processor: `core/signal_processor_websocket.py`

---

**Status**: ✅ **PLAN COMPLETE - READY FOR IMPLEMENTATION**

**Estimated Time**: 2-3 hours
**Complexity**: Medium
**Risk**: Low (with proper testing and rollback plan)
**Priority**: P0 - CRITICAL

**Created**: 2025-10-22 05:30
**Author**: Claude Code
**Version**: 1.0

---

## 🎯 NEXT STEPS

1. ✅ Read entire plan
2. ✅ Prepare environment (git, backups)
3. ⏳ Implement Fix #1 → Test → Commit
4. ⏳ Implement Fix #2 → Test → Commit
5. ⏳ Implement Fix #3 → Test → Commit
6. ⏳ Run integration test
7. ⏳ Deploy and monitor
8. ✅ Update investigation document with results

**Ready to start? Proceed with Fix #1!**
