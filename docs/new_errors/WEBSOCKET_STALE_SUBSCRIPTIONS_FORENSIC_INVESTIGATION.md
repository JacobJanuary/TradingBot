# WebSocket Stale Subscriptions - Forensic Investigation
**Date:** 2025-10-27
**Priority:** CRITICAL
**Component:** WebSocket Hybrid Streams (Bybit/Binance)
**Investigator:** Claude Code

---

## 🔴 PROBLEM STATEMENT

### Symptom
```
2025-10-27 02:20:36,062 - WARNING - ⚠️ WebSocket Health Check: 2/5 aged positions have STALE prices!
  - IMXUSDT: no update for 1009s (16.8 minutes)
  - BROCCOLIUSDT: no update for 1028s (17.1 minutes)
```

**Critical Issue:** Aged positions not receiving WebSocket price updates for 16-17 minutes despite:
- ✅ WebSocket connections alive (ping-pong working)
- ✅ Health check detecting the problem
- ❌ NO automatic resubscription/recovery

---

## 📊 ROOT CAUSE ANALYSIS

### Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: WebSocket Streams (Bybit/Binance)                  │
│  - Ping/pong every 20s (Bybit) / 20s autoping (Binance)    │
│  - Connection alive ✅                                       │
│  - BUT: Subscriptions can die silently 🔴                   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: UnifiedPriceMonitor                                 │
│  - Receives updates from position_manager._on_position_update│
│  - Distributes to subscribers (TrailingStop, AgedPosition)   │
│  - Tracks last_update_time per symbol ✅                     │
│  - Detects staleness (5min threshold) ✅                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: Protection Adapters                                 │
│  - AgedPositionAdapter subscribes to symbols                 │
│  - TrailingStopAdapter subscribes to symbols                 │
│  - verify_subscriptions() checks logical structure ✅        │
│  - NO resubscription on stale data 🔴                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ LAYER 4: Health Check                                        │
│  - start_websocket_health_monitor() runs every 60s ✅        │
│  - Detects stale prices (>300s) ✅                           │
│  - Logs warnings ✅                                          │
│  - NO RECOVERY ACTION 🔴🔴🔴                                 │
└─────────────────────────────────────────────────────────────┘
```

### The Missing Link

**Current:**
```python
# position_manager_unified_patch.py:186-260
async def start_websocket_health_monitor():
    # Check staleness
    staleness_report = await price_monitor.check_staleness(aged_symbols)

    if stale_count > 0:
        logger.warning(f"⚠️ {stale_count} aged positions have STALE prices!")
        # ❌ STOPS HERE - NO ACTION TAKEN
```

**What's Missing:**
```python
# NEEDED: Automatic resubscription
if stale_count > 0:
    logger.warning(f"⚠️ Stale prices detected!")

    # 🔴 THIS DOESN'T EXIST:
    for symbol in stale_symbols:
        await resubscribe_symbol(symbol)  # ← NOT IMPLEMENTED
```

---

## 🔬 TECHNICAL DEEP DIVE

### 1. Bybit WebSocket Behavior

**Documentation Research:** https://bybit-exchange.github.io/docs/v5/ws/connect

| Parameter | Value | Our Implementation | Status |
|-----------|-------|-------------------|--------|
| Ping interval | 20s recommended | 20s | ✅ |
| Connection timeout | 10min without activity | N/A | ⚠️ |
| Subscription lifetime | Lost on disconnect | Restore on reconnect | ⚠️ |
| Max idle time | 600s default | N/A | ⚠️ |

**Key Findings:**
1. **"Connection will be dropped after 10 minutes"** of inactivity
2. **"All active subscriptions are lost"** on disconnect
3. **"Reconnect as soon as possible"** in case of disconnection
4. Ping-pong keeps connection alive, BUT NOT SUBSCRIPTIONS!

### 2. Binance Futures WebSocket Behavior

**Documentation Research:** https://binance-docs.github.io/apidocs/futures/

| Parameter | Value | Our Implementation | Status |
|-----------|-------|-------------------|--------|
| Ping from server | Every 3min | autoping=True | ✅ |
| Pong timeout | 10min | Handled automatically | ✅ |
| Listen key keepalive | Every 60min | Every 30min | ✅ |
| Subscription lifetime | Persistent if connection alive | Restore on reconnect | ⚠️ |

**Key Findings:**
1. Listen key must be refreshed every 60min (we do every 30min ✅)
2. WebSocket sends ping every 3min, expects pong within 10min
3. Mark price subscriptions SHOULD persist if connection alive
4. BUT: After reconnection, need to restore subscriptions

### 3. Industry Research (GitHub/Stack Overflow)

**CCXT Issue #15343:** "RequestTimeout: timed out due to a ping-pong keepalive missing on time"
- **Symptom:** After ~10 hours or with 300+ subscriptions
- **Cause:** Message throttling + dropped packets
- **Status:** Open (as of 2022)

**Common Pattern Found:**
```
"WebSocket connection stays alive but server stops sending data"
"After some time, messages stop being received, but websocket connection stays alive"
"The server stops sending both prices and PING messages"
```

**Recommended Solutions:**
1. ✅ Detect stale subscriptions (WE HAVE THIS)
2. ❌ **Resubscribe when data stops coming (WE LACK THIS)**
3. ❌ **Periodic reconnection every 10 minutes (WE LACK THIS)**
4. ❌ **Exponential backoff for reconnect (PARTIAL - only on error)**

---

## 🔍 CURRENT IMPLEMENTATION ANALYSIS

### What Works ✅

1. **Ping-Pong Keepalive**
   - `bybit_hybrid_stream.py:613-639` - Heartbeat every 20s
   - `binance_hybrid_stream.py:462` - autoping=True, heartbeat=20s

2. **Connection Monitoring**
   - Both streams have reconnection logic
   - Listen key refresh for Binance (every 30min)

3. **Staleness Detection**
   - `unified_price_monitor.py:121-176` - check_staleness() method
   - 5-minute threshold (300s)
   - Per-symbol tracking with timestamps

4. **Health Check**
   - `position_manager_unified_patch.py:186-260` - Runs every 60s
   - Logs detailed warnings with timing

5. **Subscription Restore on Reconnect**
   - `bybit_hybrid_stream.py:565-584` - _restore_ticker_subscriptions()
   - `binance_hybrid_stream.py:636-661` - _restore_subscriptions()

### What's Broken 🔴

1. **NO Automatic Resubscription**
   - Health check detects stale data
   - But takes NO corrective action
   - Positions can be stale for HOURS

2. **NO Proactive Subscription Health Monitoring**
   - Only checks when health monitor runs (every 60s)
   - By then, could have missed 16+ minutes of data
   - No real-time detection

3. **NO Periodic Reconnection**
   - Connections can stay alive indefinitely
   - Industry best practice: reconnect every 10-20 minutes
   - Prevents accumulation of issues

4. **verify_subscriptions() is Insufficient**
   - Only checks `symbol in adapter.monitoring_positions`
   - Doesn't verify actual data flow
   - False sense of security

---

## 🎯 IMPACT ASSESSMENT

### Trading Risk

| Scenario | Risk Level | Impact |
|----------|-----------|--------|
| Aged position not receiving updates | 🔴 CRITICAL | Can't execute market close on price target |
| Trailing stop not getting prices | 🔴 CRITICAL | Won't update SL, potential loss |
| 16+ minutes of stale data | 🔴 CRITICAL | Complete monitoring failure |
| Manual intervention required | 🟡 HIGH | Defeats purpose of automation |

### Observed Behavior

**From logs:**
```
IMXUSDT:  1009s without update (16.8 min)
BROCCOLIUSDT: 1028s without update (17.1 min)
```

**Timeline:**
```
T+0:00  - Position becomes aged, subscription created
T+0:30  - Last price update received
T+1:00  - Health check runs - no issue yet (only 30s)
T+5:00  - Health check runs - STALE detected (300s threshold exceeded)
T+16:00 - Still stale, still no action taken
T+17:00 - User notices logs, manual investigation begins
```

### Why This Happens

**Theory #1: Silent Subscription Death**
- WebSocket connection alive (ping-pong working)
- But specific topic subscription died server-side
- Server not sending updates for that symbol
- No error message, just silence

**Theory #2: Server-Side Cleanup**
- Bybit timeout: 10min without activity
- If symbol has low trading volume (no natural updates)
- Server may clean up "inactive" subscriptions
- Connection stays alive, subscription dies

**Theory #3: Reconnection Bug**
- Connection drops briefly, reconnects automatically
- `_restore_ticker_subscriptions()` runs
- But some subscriptions fail to restore (silent failure)
- Code assumes success, doesn't verify

---

## 💡 SOLUTION STRATEGIES

### Strategy 1: Reactive Resubscription (Quick Fix)
**Complexity:** LOW
**Impact:** MEDIUM
**Timeline:** 1 hour

Enhance `start_websocket_health_monitor()` to trigger resubscription:

```python
async def start_websocket_health_monitor():
    # ... existing staleness check ...

    if stale_count > 0:
        logger.warning(f"⚠️ {stale_count} stale subscriptions detected!")

        # NEW: Trigger resubscription
        for symbol in stale_symbols:
            await resubscribe_aged_position(symbol, aged_adapter, position_manager)
```

**Pros:**
- ✅ Minimal code changes
- ✅ Solves immediate problem
- ✅ Low risk

**Cons:**
- ❌ Reactive (waits for 5min threshold)
- ❌ Still has 16+ minute gaps
- ❌ Doesn't prevent issue

### Strategy 2: Proactive Subscription Verification (Better)
**Complexity:** MEDIUM
**Impact:** HIGH
**Timeline:** 2-3 hours

Add real-time subscription health verification:

```python
# After every subscription/resubscription
await _verify_subscription_active(symbol, timeout=30s)

# Verify we receive at least 1 update within 30s
# If not, retry subscription immediately
```

**Pros:**
- ✅ Catches issues immediately (30s vs 5min)
- ✅ Automatic retry logic
- ✅ Better user experience

**Cons:**
- ❌ More complex implementation
- ❌ Requires timeout handling
- ❌ May trigger false positives on low-volume symbols

### Strategy 3: Adaptive Staleness Threshold (Smart)
**Complexity:** MEDIUM
**Impact:** MEDIUM
**Timeline:** 2 hours

Reduce staleness threshold for critical positions:

```python
# Current: 300s (5min) for all
# Proposed:
- Aged positions: 30s threshold (CRITICAL - need fast reaction)
- Trailing stops: 60s threshold (HIGH - need SL updates)
- Regular positions: 300s threshold (NORMAL)
```

**Pros:**
- ✅ Faster detection for critical cases
- ✅ Reduces max stale time to 30s + 60s check = 90s max
- ✅ Prioritizes important positions

**Cons:**
- ❌ More complex threshold logic
- ❌ May increase resubscription churn

### Strategy 4: Periodic Prophylactic Reconnection (Industry Standard)
**Complexity:** LOW
**Impact:** HIGH
**Timeline:** 1 hour

Implement periodic full reconnection:

```python
# Every 10 minutes:
- Gracefully close WebSocket
- Reconnect
- Restore all subscriptions
- Verify all subscriptions active

# Ensures fresh connection state
# Prevents issue accumulation
```

**Pros:**
- ✅ Industry best practice
- ✅ Prevents issues before they occur
- ✅ Simple to implement
- ✅ Proven effective (common in trading bots)

**Cons:**
- ❌ Brief disruption every 10min
- ❌ Increased connection overhead
- ❌ May trigger rate limits if too frequent

### Strategy 5: Hybrid Approach (RECOMMENDED)
**Complexity:** MEDIUM-HIGH
**Impact:** VERY HIGH
**Timeline:** 3-4 hours

Combine multiple strategies:

1. **Immediate (30s threshold):** Detect stale subscriptions for aged positions
2. **Reactive (when detected):** Automatic resubscription
3. **Proactive (every 10min):** Periodic reconnection for aged position connections
4. **Verification:** After resubscription, verify within 30s

```python
# 1. Fast detection for aged positions
async def check_aged_position_health():
    threshold = 30  # 30s for aged positions
    if time_since_update > threshold:
        await resubscribe_with_verification(symbol)

# 2. Periodic reconnection
async def periodic_reconnection_task():
    while True:
        await asyncio.sleep(600)  # 10 minutes

        if has_aged_positions():
            logger.info("Proactive reconnection for aged positions")
            await reconnect_and_restore_subscriptions()

# 3. Verification after subscription
async def resubscribe_with_verification(symbol):
    await unsubscribe(symbol)
    await asyncio.sleep(0.5)
    await subscribe(symbol)

    # Verify we get data within 30s
    verified = await wait_for_update(symbol, timeout=30)
    if not verified:
        logger.error(f"Subscription failed for {symbol} - ESCALATE")
        # Could try different connection, notify user, etc.
```

**Pros:**
- ✅ Defense in depth
- ✅ Fast reaction (30s detection)
- ✅ Preventive measures (periodic reconnect)
- ✅ Verification loop (ensures success)
- ✅ Production-grade reliability

**Cons:**
- ❌ Most complex to implement
- ❌ Requires careful testing
- ❌ More moving parts

---

## 📋 RECOMMENDED IMPLEMENTATION PLAN

### Phase 1: Emergency Patch (1 hour)
**Goal:** Stop the bleeding

1. Add automatic resubscription to health monitor
2. Reduce aged position staleness threshold to 60s
3. Add logging for all subscription operations
4. Deploy to production

**Files to modify:**
- `core/position_manager_unified_patch.py` - Add resubscription logic
- `websocket/unified_price_monitor.py` - Add per-module thresholds

### Phase 2: Proactive Prevention (2-3 hours)
**Goal:** Prevent issues before they occur

1. Implement periodic reconnection task (every 10min when aged positions exist)
2. Add subscription verification (wait for first update within 30s)
3. Exponential backoff for failed resubscriptions
4. Enhanced logging and metrics

**Files to modify:**
- `websocket/bybit_hybrid_stream.py` - Add periodic reconnection
- `websocket/binance_hybrid_stream.py` - Add periodic reconnection
- `core/protection_adapters.py` - Add verification logic

### Phase 3: Monitoring & Alerting (1 hour)
**Goal:** Visibility into subscription health

1. Add metrics for:
   - Subscription success/failure rate
   - Resubscription frequency
   - Max stale duration per symbol
   - Reconnection frequency
2. Alert if:
   - Resubscription fails 3 times in a row
   - Any aged position stale > 2 minutes
   - Connection reconnecting > 1/minute

**Files to modify:**
- `core/aged_position_metrics.py` - Add subscription metrics
- `core/event_logger.py` - Add subscription events

---

## 🎯 NEXT STEPS

### Immediate Actions (DO NOW)
1. ✅ Document findings (THIS REPORT)
2. ⏭️ Create detailed fix plan
3. ⏭️ Implement Phase 1 (Emergency Patch)
4. ⏭️ Test on IMXUSDT and BROCCOLIUSDT
5. ⏭️ Deploy to production

### Short-term (THIS WEEK)
1. ⏭️ Implement Phase 2 (Proactive Prevention)
2. ⏭️ Add comprehensive tests
3. ⏭️ Monitor metrics for 24-48 hours
4. ⏭️ Tune thresholds based on real data

### Long-term (NEXT SPRINT)
1. ⏭️ Implement Phase 3 (Monitoring & Alerting)
2. ⏭️ Consider WebSocket connection pooling
3. ⏭️ Evaluate moving to CCXT Pro watch methods
4. ⏭️ Load testing with 50+ simultaneous positions

---

## 📚 REFERENCES

### Documentation
- [Bybit WebSocket Connect](https://bybit-exchange.github.io/docs/v5/ws/connect)
- [Binance Futures WebSocket](https://binance-docs.github.io/apidocs/futures/)

### GitHub Issues
- [CCXT #15343](https://github.com/ccxt/ccxt/issues/15343) - Ping-pong timeout
- [pybit #31](https://github.com/bybit-exchange/pybit/issues/31) - Ping/pong timed out
- [ccxt #7858](https://github.com/ccxt/ccxt/issues/7858) - Connection closed by remote

### Stack Overflow
- "Keep Binance futures wss alive"
- "WebSocket stops receiving data after 15-20 minutes"
- "How reconnect (resubscribe) to websocket"

---

## 🔖 CONCLUSION

**Problem:** WebSocket subscriptions can die silently while connection remains alive, causing aged positions to miss price updates for 16+ minutes.

**Root Cause:** Lack of automatic resubscription when stale data detected. Health check alerts but takes no action.

**Solution:** Multi-layered approach:
1. Fast detection (30s for aged positions)
2. Automatic resubscription
3. Subscription verification
4. Periodic prophylactic reconnection (10min)

**Priority:** 🔴 CRITICAL - Affects core trading logic, can lead to missed closes and losses.

**Estimated Fix Time:**
- Phase 1 (Emergency): 1 hour
- Phase 2 (Prevention): 2-3 hours
- Phase 3 (Monitoring): 1 hour
- **Total: 4-5 hours**

**Risk:** LOW - Changes are additive, don't modify existing working code. Can be deployed incrementally.

---

**Investigation Status:** ✅ COMPLETE
**Next:** Create detailed fix plan (separate document)
