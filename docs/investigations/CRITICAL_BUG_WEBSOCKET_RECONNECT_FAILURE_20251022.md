# 🔴 CRITICAL BUG: WebSocket Reconnect Failure - Bot Stopped Trading
## Date: 2025-10-22 05:10
## Severity: P0 - CRITICAL (Trading stopped for 3+ hours)

---

## 📊 EXECUTIVE SUMMARY

**Problem**: Bot stopped processing signal waves after WebSocket restart

**Impact**:
- **Last wave processed**: 02:05:07 (3 hours ago)
- **Trading stopped**: No positions opened since 02:05
- **Missed waves**: ~13 waves (every 15 minutes)
- **Financial impact**: CRITICAL - bot not trading

**Root Cause**:
1. ❌ WebSocket connection closes on every `request_signals()` call
2. ❌ Initial restart used wrong wave timestamp (yesterday's date)
3. ❌ No proper reconnection after 1000 (Normal Closure) errors

**Status**: 🔴 **PRODUCTION BROKEN** - Immediate fix required

---

## 🎯 ROOT CAUSE ANALYSIS

### Problem #1: WebSocket Closes on Request

**Error Message** (repeating since 03:05):
```
SignalWSClient - ERROR - Failed to request signals: received 1000 (OK); then sent 1000 (OK)
```

**What это значит**:
- Code 1000 = Normal Closure (WebSocket стандартный код)
- Connection закрывается сразу после попытки `websocket.send()`
- Это происходит КАЖДЫЙ раз при запросе сигналов

**Location**: `websocket/signal_client.py:306`
```python
async def request_signals(self):
    if self.state == ConnectionState.AUTHENTICATED:
        try:
            await self.websocket.send(json.dumps({'type': 'get_signals'}))
        except Exception as e:
            logger.error(f"Failed to request signals: {e}")  # ← HERE
```

### Problem #2: Wrong Wave Timestamp After Restart

**Timeline**:
```
02:04:59 - Looking for wave: 2025-10-21T21:45:00 ✅ (before restart)
02:06:07 - BOT STOPPED (signal 2 = SIGINT)
02:52:56 - BOT RESTARTED
03:05:00 - Looking for wave: 2025-10-21T22:45:00 ❌ WRONG DATE!
04:20:00 - Looking for wave: 2025-10-22T00:00:00 ✅ (correct date)
```

**Issue**:
- After restart at 02:52, first wave check (03:05) used **yesterday's date** (2025-10-21)
- Should have been: **2025-10-22T22:45:00** (today)
- Correct date only from 04:20 onwards

### Problem #3: No Signals in Buffer

**Evidence**:
```
02:52:58 - Received 291 signals (initial batch on connect) ✅
03:05:01 - buffer of 0 signals ❌
04:20:01 - buffer of 0 signals ❌
05:05:00 - buffer of 0 signals ❌
```

**Reason**: Can't request new signals because connection closes!

---

## 📋 DETAILED TIMELINE

### 02:05:07 - Last Successful Wave
```
🌊 Wave processing complete in 4430ms:
✅ 6 successful, ❌ 0 failed, ⏭️ 1 skipped
📊 Success rate: 85.7%
```

### 02:06:07 - Bot Stopped
```
__main__ - INFO - Received signal 2
signal_processor_websocket - INFO - Stopping WebSocket Signal Processor...
SignalWSClient - INFO - Stopping signal client...
signal_processor_websocket - INFO - Wave monitoring loop cancelled
signal_processor_websocket - INFO - ✅ WebSocket Signal Processor stopped
```

**Cause**: User signal 2 (SIGINT) - manual stop or system signal

### 02:52:56 - Bot Restarted
```
__main__ - INFO - Initializing WebSocket signal processor...
wave_signal_processor - INFO - WaveSignalProcessor initialized
signal_processor_websocket - INFO - WebSocket Signal Processor initialized
```

### 02:52:58 - WebSocket Connected
```
SignalWSClient - INFO - Connecting to signal server: ws://10.8.0.1:8765
SignalWSClient - INFO - Connected to signal server
SignalWSClient - INFO - Received 291 signals ✅
signal_processor_websocket - INFO - 📡 Received 291 RAW signals from WebSocket
signal_processor_websocket - INFO - ⏰ Waiting 722s until next wave check at 23:05 UTC
```

**Status**: Connection OK, initial signals received

### 03:05:00 - First Wave Check After Restart
```
signal_processor_websocket - INFO - 🔍 Looking for wave with timestamp: 2025-10-21T22:45:00+00:00
SignalWSClient - ERROR - Failed to request signals: received 1000 (OK); then sent 1000 (OK)
SignalWSClient - INFO - [DEBUG] Found 0 signals for timestamp 2025-10-21T22:45:00+00:00 in buffer of 0
```

**Problems**:
1. ❌ Wrong date: 2025-10-21 (yesterday) instead of 2025-10-22
2. ❌ Connection closes on request
3. ❌ Buffer empty

### 03:05:00 → 05:10:00 - Continuous Failures

**Every 2 seconds**:
```
SignalWSClient - ERROR - Failed to request signals: received 1000 (OK); then sent 1000 (OK)
```

**Every 15 minutes** (wave checks at :05, :20, :35, :50):
```
🔍 Looking for wave with timestamp: [various timestamps]
[DEBUG] Found 0 signals for timestamp [...] in buffer of 0
```

**Waves checked but FAILED**:
- 03:05 - 2025-10-21T22:45:00 ❌ (wrong date)
- 04:20 - 2025-10-22T00:00:00 ✓ (correct date, but buffer empty)
- 04:35 - 2025-10-22T00:15:00 ✓ (correct date, but buffer empty)
- 04:50 - 2025-10-22T00:30:00 ✓ (correct date, but buffer empty)
- 05:05 - 2025-10-22T00:45:00 ✓ (correct date, but buffer empty)

**Result**: 0 waves processed, 0 positions opened

---

## 🔬 TECHNICAL DETAILS

### WebSocket Connection State

**TCP Level** (verified via netstat):
```
tcp4  ESTABLISHED  10.8.0.2:59358 → 10.8.0.1:8765
```
✅ TCP connection IS established and working

**WebSocket Level**:
```
state: ConnectionState.AUTHENTICATED (presumed)
websocket.send() → Exception: "received 1000 (OK); then sent 1000 (OK)"
```
❌ WebSocket closes on send()

**Signal Server**:
```
PID 75396: /usr/local/bin/python -m bridge.signal_bridge
Listening on: 10.8.0.1:8765
Status: RUNNING ✅
```

### Code Analysis

**websocket/signal_client.py:296-308**
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
            logger.error(f"Failed to request signals: {e}")  # ← Triggering here
            return False
    return False
```

**Problem**:
- No state change to `DISCONNECTED` on error
- No reconnection attempt triggered
- Continues trying with closed connection

**Expected behavior**:
```python
except Exception as e:
    logger.error(f"Failed to request signals: {e}")
    self.state = ConnectionState.DISCONNECTED  # ← Missing!
    # Trigger reconnection
```

### Health Check Warnings

**From 02:52:59 onwards**:
```
__main__ - WARNING - Signal Processor: degraded - No signals processed yet
core.event_logger - WARNING - health_check_failed: status='degraded'
__main__ - WARNING - signal_processor: 12 consecutive failures (02:58)
__main__ - WARNING - signal_processor: 22 consecutive failures (03:03)
```

**Status**: Health check detected the problem but no automatic recovery

---

## 🎯 WHY THIS HAPPENED

### Sequence of Events

1. **02:06** - User/system sent SIGINT → bot stopped gracefully
2. **02:52** - Bot restarted (manually or by systemd/supervisor)
3. **02:52** - WebSocket connected, received initial batch (291 signals)
4. **03:05** - First wave check:
   - Calculated wrong timestamp (yesterday's date)
   - Attempted `request_signals()`
   - WebSocket closed with 1000 (Normal Closure)
5. **03:05+** - Every subsequent request:
   - WebSocket sends request
   - Connection closes immediately
   - No reconnection triggered
   - Buffer stays empty
6. **Present** - Still failing, 3+ hours without trading

### Why Connection Closes

**Hypotheses** (need verification):

1. **Server-side issue**:
   - Signal server closes connection after timeout
   - Server requires re-authentication
   - Server doesn't handle `get_signals` request properly

2. **Client-side issue**:
   - Connection object stale after restart
   - `self.websocket` reference invalid
   - State mismatch (thinks AUTHENTICATED but isn't)

3. **Protocol issue**:
   - Initial connection OK (received 291 signals)
   - Subsequent requests fail
   - Possible authentication expiry?

### Why Wrong Timestamp

**Location**: `core/signal_processor_websocket.py` (wave timestamp calculation logic)

**Issue**: After restart, wave timestamp calculation doesn't account for date change properly.

**Evidence**:
- Before restart (02:04): 2025-10-21T21:45:00 ✓
- After restart (03:05): 2025-10-21T22:45:00 ❌ (should be 2025-10-22)
- Later (04:20): 2025-10-22T00:00:00 ✓

**Theory**:
- Calculation uses "last processed wave" + 15min
- After restart, "last processed" might be from yesterday
- Doesn't validate date is today

---

## 📊 IMPACT ANALYSIS

### Trading Impact

**Time without trading**: 3 hours 5 minutes (02:05 → 05:10)

**Missed waves**: ~13 waves
- Waves occur every 15 minutes
- 4 waves per hour × 3 hours = 12 waves
- Plus current hour: 1 wave
- **Total**: ~13 waves

**Missed signals**: Unknown (each wave has ~5-7 signals)
- Conservative: 13 × 5 = **65 signals**
- Maximum: 13 × 7 = **91 signals**

**Missed positions**:
- If 70% success rate: **45-63 positions** not opened

**Financial impact**:
- Assume $200 per position
- 50 positions × $200 = **$10,000 not deployed**
- Potential profits: **UNKNOWN** (depends on market movement)

### System Health

**Components affected**:
- ✅ REST polling: WORKING (positions still monitored)
- ✅ Position management: WORKING
- ✅ Trailing stop: WORKING
- ❌ Signal reception: **BROKEN**
- ❌ Wave processing: **BROKEN**
- ❌ Position opening: **BROKEN**

**Data integrity**:
- Database: ✅ OK
- Existing positions: ✅ OK
- Stop losses: ✅ OK

---

## 🔍 EVIDENCE

### Log Excerpts

**Bot Stop** (02:06:07):
```
2025-10-22 02:06:07,544 - __main__ - INFO - Received signal 2
2025-10-22 02:06:07,545 - core.signal_processor_websocket - INFO - Stopping WebSocket Signal Processor...
2025-10-22 02:06:07,545 - SignalWSClient - INFO - Stopping signal client...
2025-10-22 02:06:07,613 - core.signal_processor_websocket - INFO - Wave monitoring loop cancelled
2025-10-22 02:06:07,613 - core.signal_processor_websocket - INFO - ✅ WebSocket Signal Processor stopped
```

**Bot Restart** (02:52:56):
```
2025-10-22 02:52:56,045 - __main__ - INFO - Initializing WebSocket signal processor...
2025-10-22 02:52:56,046 - core.wave_signal_processor - INFO - WaveSignalProcessor initialized
2025-10-22 02:52:58,383 - core.signal_processor_websocket - INFO - Starting WebSocket Signal Processor...
2025-10-22 02:52:58,384 - SignalWSClient - INFO - Connecting to signal server: ws://10.8.0.1:8765
2025-10-22 02:52:58,516 - SignalWSClient - INFO - Connected to signal server
2025-10-22 02:52:58,595 - SignalWSClient - INFO - Received 291 signals
```

**First Failure** (03:05:00):
```
2025-10-22 03:05:00,013 - core.signal_processor_websocket - INFO - 🔍 Looking for wave with timestamp: 2025-10-21T22:45:00+00:00
2025-10-22 03:05:00,014 - SignalWSClient - ERROR - Failed to request signals: received 1000 (OK); then sent 1000 (OK)
2025-10-22 03:05:01,014 - SignalWSClient - INFO - [DEBUG] Found 0 signals for timestamp 2025-10-21T22:45:00+00:00 in buffer of 0
```

**Continuous Failures** (every 2 seconds since 03:05):
```
2025-10-22 05:08:50,056 - SignalWSClient - ERROR - Failed to request signals: received 1000 (OK); then sent 1000 (OK)
2025-10-22 05:08:52,056 - SignalWSClient - ERROR - Failed to request signals: received 1000 (OK); then sent 1000 (OK)
2025-10-22 05:08:54,057 - SignalWSClient - ERROR - Failed to request signals: received 1000 (OK); then sent 1000 (OK)
```

### Network Status

**Port 8765**:
```bash
$ lsof -i :8765
COMMAND   PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
Python  75396  user    9u  IPv4  ...      0t0  TCP 10.8.0.2:59358->10.8.0.1:8765 (ESTABLISHED)
```

**Netstat**:
```bash
$ netstat -an | grep 8765
tcp4  ESTABLISHED  10.8.0.2.59358  10.8.0.1.8765
```

---

## ✅ WHAT WORKS

1. ✅ **TCP Connection**: Established and stable
2. ✅ **Signal Server**: Running and accepting connections
3. ✅ **Initial Connection**: Bot connects successfully
4. ✅ **Initial Batch**: Receives 291 signals on connect
5. ✅ **REST Polling**: Continues to work for existing positions
6. ✅ **Position Management**: Still functioning
7. ✅ **Trailing Stops**: Still updating

---

## ❌ WHAT'S BROKEN

1. ❌ **WebSocket request_signals()**: Closes connection on send
2. ❌ **Signal Buffer**: Stays empty (0 signals)
3. ❌ **Wave Processing**: Can't find signals (buffer empty)
4. ❌ **Position Opening**: No new positions since 02:05
5. ❌ **Error Recovery**: No reconnection on 1000 errors
6. ❌ **Wave Timestamp**: Wrong date after restart (until 04:20)
7. ❌ **Health Check Response**: Detects issue but no auto-recovery

---

## 🎯 REQUIRED FIXES

### Fix #1: Handle WebSocket Closure Properly (P0 - CRITICAL)

**Location**: `websocket/signal_client.py:296-308`

**Current Code**:
```python
async def request_signals(self):
    if self.state == ConnectionState.AUTHENTICATED:
        try:
            await self.websocket.send(json.dumps({'type': 'get_signals'}))
            return True
        except Exception as e:
            logger.error(f"Failed to request signals: {e}")
            return False  # ← Returns False but doesn't trigger reconnect!
    return False
```

**Required Fix**:
```python
async def request_signals(self):
    if self.state == ConnectionState.AUTHENTICATED:
        try:
            await self.websocket.send(json.dumps({'type': 'get_signals'}))
            return True
        except (websockets.exceptions.ConnectionClosed, Exception) as e:
            logger.error(f"Failed to request signals: {e}")
            self.state = ConnectionState.DISCONNECTED  # ← Set state to trigger reconnect
            if self.on_disconnect_callback:
                await self.on_disconnect_callback()
            return False
    return False
```

**Impact**: CRITICAL - Will restore signal reception

### Fix #2: Wave Timestamp Calculation After Restart (P1 - HIGH)

**Location**: `core/signal_processor_websocket.py` (wave timestamp logic)

**Issue**: After restart, first wave uses yesterday's date

**Required Fix**:
- Validate calculated timestamp is not in the past
- If timestamp < now - 1 hour: recalculate with today's date
- Add logging for timestamp calculation

**Impact**: HIGH - Prevents missing first waves after restart

### Fix #3: Automatic Reconnection on Error (P1 - HIGH)

**Issue**: No reconnection triggered when WebSocket fails

**Required Fix**:
- Add reconnection logic to `request_signals()`, `request_stats()`, `ping()`
- Trigger reconnect on any WebSocket exception
- Add exponential backoff for reconnect attempts

**Impact**: HIGH - Improves resilience

### Fix #4: Health Check Auto-Recovery (P2 - MEDIUM)

**Issue**: Health check detects problem but doesn't trigger recovery

**Required Fix**:
- Add auto-recovery action when signal_processor fails > N times
- Trigger WebSocket reconnect from health check
- Add alert/notification on consecutive failures

**Impact**: MEDIUM - Better observability and auto-healing

---

## 🧪 TESTING REQUIRED

### Test #1: WebSocket Reconnection
1. Start bot
2. Kill signal server
3. Restart signal server
4. Verify bot reconnects automatically
5. Verify signals resume flowing

### Test #2: Bot Restart
1. Stop bot (SIGINT)
2. Wait 30 minutes
3. Restart bot
4. Verify first wave timestamp is correct (today's date)
5. Verify signals received
6. Verify wave processing starts

### Test #3: Connection Interruption
1. Bot running normally
2. Simulate network interruption (iptables or tcpkill)
3. Restore network
4. Verify reconnection happens automatically
5. Verify trading resumes

---

## 📝 IMMEDIATE ACTIONS

### Now (P0):
1. ⚠️ **RESTART BOT** - temporary fix to restore trading
2. Monitor first wave after restart
3. Verify signals start flowing again

### Today (P0):
1. Implement Fix #1 (WebSocket closure handling)
2. Test reconnection logic
3. Deploy fix
4. Monitor for 24 hours

### This Week (P1):
1. Implement Fix #2 (wave timestamp)
2. Implement Fix #3 (auto-reconnection)
3. Add comprehensive tests
4. Implement Fix #4 (health check recovery)

---

## 📊 RELATED ISSUES

### Similar Past Issues
- ❌ No similar WebSocket issues found in recent history
- ⚠️ First time this specific failure mode observed

### May Be Related To
- User restart at 02:06 (manual or system signal)
- Possible signal server restart around same time?
- Authentication timeout after restart?

---

**Status**: 🔴 **CRITICAL - PRODUCTION BROKEN**

**Next Step**: 🔧 **IMMEDIATE RESTART REQUIRED**

**Created**: 2025-10-22 05:10
**Investigator**: Claude Code
**Severity**: P0 - CRITICAL
**Impact**: Trading stopped for 3+ hours

---

## 🔗 FILES TO CHECK

- `websocket/signal_client.py:296-308` - request_signals() method
- `core/signal_processor_websocket.py` - wave timestamp calculation
- `bridge/signal_bridge.py` - server-side logic (if accessible)
- logs/trading_bot.log - full timeline evidence
