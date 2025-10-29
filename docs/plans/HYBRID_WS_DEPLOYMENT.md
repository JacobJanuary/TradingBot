# BYBIT HYBRID WEBSOCKET - DEPLOYMENT & ROLLOUT PLAN
**Date**: 2025-10-25
**Status**: 📋 READY FOR EXECUTION
**Type**: PRODUCTION DEPLOYMENT STRATEGY

---

## Table of Contents

1. [Deployment Strategy](#deployment-strategy)
2. [Rollout Phases](#rollout-phases)
3. [Monitoring & Observability](#monitoring--observability)
4. [Rollback Plan](#rollback-plan)
5. [Success Metrics](#success-metrics)
6. [Risk Mitigation](#risk-mitigation)

---

## Deployment Strategy

### Philosophy
- **Incremental**: Deploy in stages, validate at each step
- **Reversible**: Always have rollback option
- **Observable**: Monitor metrics at every stage
- **Safe**: Never risk existing production positions

### Approach
```
Week 1-3: Development + Testing
    ↓
Week 4 Day 1-2: Canary Deployment (Monitor Only)
    ↓
Week 4 Day 3: Parallel Run (Hybrid + REST)
    ↓
Week 4 Day 4: Gradual Cutover (50% → 100%)
    ↓
Week 4 Day 5: Full Production + REST Deprecation
```

---

## Rollout Phases

### Phase 1: Canary Deployment (Monitor Only)
**Duration**: 2 days
**Risk**: VERY LOW (no trading impact)

#### Goals
- Verify hybrid WebSocket connects and runs
- Validate event flow
- Monitor performance metrics
- Do NOT use for actual position management yet

#### Implementation

**File**: `main.py` modification

```python
# main.py: Canary mode

class TradingBot:
    def __init__(self):
        self.bybit_hybrid_stream = None
        self.bybit_adaptive_stream = None  # Keep existing

    async def _setup_bybit_streams(self):
        """Setup Bybit streams"""
        is_testnet = self.exchange_manager.is_testnet('bybit')
        bybit_config = config.get_exchange_config('bybit')

        if not is_testnet:
            # CANARY MODE: Run both streams in parallel
            logger.info("🐤 CANARY MODE: Running hybrid + REST in parallel")

            # Primary: Existing REST polling (active)
            self.bybit_adaptive_stream = AdaptiveBybitStream(
                exchange_manager=self.exchange_manager,
                event_handler=self._handle_stream_event,
                testnet=False
            )
            await self.bybit_adaptive_stream.start()

            # Canary: Hybrid WebSocket (monitor only)
            from websocket.bybit_hybrid_stream import BybitHybridStream

            self.bybit_hybrid_stream = BybitHybridStream(
                api_key=bybit_config.api_key,
                api_secret=bybit_config.api_secret,
                event_handler=self._handle_canary_event,  # Separate handler!
                testnet=False
            )
            await self.bybit_hybrid_stream.start()

            logger.info("✅ Canary + REST both running")
        else:
            # Testnet: Use existing REST
            self.bybit_adaptive_stream = AdaptiveBybitStream(
                exchange_manager=self.exchange_manager,
                event_handler=self._handle_stream_event,
                testnet=True
            )
            await self.bybit_adaptive_stream.start()

    async def _handle_canary_event(self, event_type: str, data: Dict):
        """Handle canary events - MONITOR ONLY"""
        if event_type == 'position.update':
            symbol = data.get('symbol')
            mark_price = data.get('mark_price')

            # Log for comparison
            logger.info(f"🐤 CANARY: {symbol} @ ${mark_price}")

            # Store for comparison metrics
            self.canary_metrics['events'] = self.canary_metrics.get('events', 0) + 1
            self.canary_metrics['last_update'] = time.time()

            # Do NOT pass to Position Manager yet!
```

#### Validation Criteria
- ✅ Hybrid WebSocket connects successfully
- ✅ Both streams connected (private + public)
- ✅ Canary receives position updates
- ✅ Canary receives ticker updates (100ms frequency)
- ✅ No errors in logs
- ✅ Memory usage stable

#### Monitoring Dashboard
```python
# Add to main.py monitoring

async def _print_canary_metrics(self):
    """Print canary metrics every 60 seconds"""
    while self.running:
        await asyncio.sleep(60)

        if hasattr(self, 'canary_metrics'):
            events = self.canary_metrics.get('events', 0)
            last_update = self.canary_metrics.get('last_update', 0)
            elapsed = time.time() - last_update if last_update else 0

            logger.info("=" * 80)
            logger.info("🐤 CANARY METRICS (last 60s)")
            logger.info(f"   Events received: {events}")
            logger.info(f"   Last update: {elapsed:.1f}s ago")
            logger.info(f"   Status: {'✅ ACTIVE' if elapsed < 10 else '⚠️ STALE'}")
            logger.info("=" * 80)

            # Reset counter
            self.canary_metrics['events'] = 0
```

#### Success Criteria
- At least 60 events/minute received
- Last update < 10 seconds old
- No connection failures
- No memory leaks

---

### Phase 2: Parallel Run (Data Validation)
**Duration**: 1 day
**Risk**: LOW (still using REST for trading)

#### Goals
- Compare hybrid vs REST data
- Validate event accuracy
- Measure performance difference
- Build confidence in hybrid stream

#### Implementation

```python
# main.py: Parallel validation mode

class TradingBot:
    async def _handle_stream_event(self, event_type: str, data: Dict):
        """Main event handler - using REST"""
        # Existing handler - still active
        await self.position_manager.handle_event(event_type, data)

    async def _handle_canary_event(self, event_type: str, data: Dict):
        """Canary event handler - validation only"""
        if event_type == 'position.update':
            symbol = data.get('symbol')
            canary_price = data.get('mark_price')

            # Compare with REST data
            if symbol in self.position_manager.positions:
                position = self.position_manager.positions[symbol]
                rest_price = position.current_price

                diff = abs(float(canary_price) - float(rest_price))
                diff_pct = (diff / float(rest_price)) * 100 if rest_price else 0

                logger.info(f"📊 VALIDATION: {symbol}")
                logger.info(f"   Hybrid WS: ${canary_price}")
                logger.info(f"   REST API:  ${rest_price}")
                logger.info(f"   Diff: ${diff:.8f} ({diff_pct:.4f}%)")

                # Track metrics
                self.validation_metrics['comparisons'] = \
                    self.validation_metrics.get('comparisons', 0) + 1

                if diff_pct > 0.1:  # > 0.1% difference
                    logger.warning(f"⚠️ Price divergence: {diff_pct:.4f}%")
                    self.validation_metrics['divergences'] = \
                        self.validation_metrics.get('divergences', 0) + 1
```

#### Validation Metrics
- Price difference: < 0.1%
- Update frequency: Hybrid 10x faster than REST
- Latency: Hybrid < 200ms, REST ~10s
- Accuracy: 99.9% match rate

#### Success Criteria
- ✅ Price accuracy: >99.9% within 0.1%
- ✅ Zero critical divergences
- ✅ Hybrid consistently faster
- ✅ All positions tracked by both

---

### Phase 3: Gradual Cutover
**Duration**: 1 day
**Risk**: MEDIUM (transitioning to hybrid)

#### Step 3.1: 50% Cutover (Morning)

```python
# main.py: 50% cutover

HYBRID_CUTOVER_PERCENTAGE = 50  # Start with 50%

class TradingBot:
    async def _handle_stream_event(self, event_type: str, data: Dict):
        """Main event handler - mixed mode"""
        symbol = data.get('symbol', '')

        # Use symbol hash to determine which stream to use
        use_hybrid = (hash(symbol) % 100) < HYBRID_CUTOVER_PERCENTAGE

        if use_hybrid:
            logger.debug(f"🔀 {symbol}: Using HYBRID")
            # Already handled by hybrid stream
        else:
            logger.debug(f"🔀 {symbol}: Using REST")
            # Use REST data
            await self.position_manager.handle_event(event_type, data)
```

**Monitoring**: Watch for 4 hours

**Validation**:
- ✅ Hybrid positions work correctly
- ✅ TS activates properly
- ✅ No missed updates
- ✅ No errors

#### Step 3.2: 100% Cutover (Afternoon)

**After 4 hours of stable 50% operation**:

```python
# main.py: Full cutover

class TradingBot:
    async def _setup_bybit_streams(self):
        """Setup Bybit streams"""
        is_testnet = self.exchange_manager.is_testnet('bybit')
        bybit_config = config.get_exchange_config('bybit')

        if not is_testnet:
            # FULL CUTOVER: Hybrid only
            logger.info("🚀 PRODUCTION: Using Hybrid WebSocket")

            from websocket.bybit_hybrid_stream import BybitHybridStream

            self.bybit_hybrid_stream = BybitHybridStream(
                api_key=bybit_config.api_key,
                api_secret=bybit_config.api_secret,
                event_handler=self._handle_stream_event,  # Main handler now!
                testnet=False
            )
            await self.bybit_hybrid_stream.start()

            logger.info("✅ Hybrid WebSocket active")

            # REST polling DISABLED
            # self.bybit_adaptive_stream = None
        else:
            # Testnet: Still using REST for now
            self.bybit_adaptive_stream = AdaptiveBybitStream(
                exchange_manager=self.exchange_manager,
                event_handler=self._handle_stream_event,
                testnet=True
            )
            await self.bybit_adaptive_stream.start()
```

**Monitoring**: Watch closely for 4 hours

**Validation**:
- ✅ All positions tracked
- ✅ All price updates flowing
- ✅ TS activating correctly
- ✅ Aged monitor working
- ✅ No errors

---

### Phase 4: Full Production
**Duration**: Ongoing
**Risk**: LOW (validated in previous phases)

#### Implementation
- Hybrid WebSocket as primary
- REST polling deprecated
- Full monitoring active
- Rollback plan ready

#### Post-Deployment Tasks

**Day 1-2**: Intensive monitoring
- Check logs every 2 hours
- Validate all metrics
- Watch for anomalies

**Week 1**: Daily checks
- Review metrics daily
- Check for errors
- Validate performance

**Week 2+**: Normal monitoring
- Standard monitoring
- Weekly reviews
- Continuous optimization

---

## Monitoring & Observability

### Key Metrics to Monitor

#### 1. Connection Health
```python
# Metrics to track

connection_metrics = {
    'private_ws_connected': True/False,
    'public_ws_connected': True/False,
    'private_ws_uptime': seconds,
    'public_ws_uptime': seconds,
    'reconnection_count': int,
    'last_reconnection': timestamp
}
```

**Alerts**:
- ⚠️ Warning: Disconnected for > 30 seconds
- 🚨 Critical: Disconnected for > 2 minutes
- 🚨 Critical: > 5 reconnections in 1 hour

#### 2. Event Flow
```python
event_flow_metrics = {
    'position_updates_count': int,
    'ticker_updates_count': int,
    'events_per_second': float,
    'last_event_timestamp': timestamp
}
```

**Alerts**:
- ⚠️ Warning: No events for > 60 seconds
- 🚨 Critical: No events for > 5 minutes

#### 3. Subscription Health
```python
subscription_metrics = {
    'active_subscriptions': int,
    'active_positions': int,
    'subscription_failures': int,
    'unsubscribe_failures': int
}
```

**Alerts**:
- ⚠️ Warning: Subscription failures > 5
- 🚨 Critical: Active subscriptions = 0 but positions > 0

#### 4. Performance Metrics
```python
performance_metrics = {
    'avg_latency_ms': float,
    'p95_latency_ms': float,
    'p99_latency_ms': float,
    'events_per_second': float,
    'memory_usage_mb': float
}
```

**Alerts**:
- ⚠️ Warning: Avg latency > 500ms
- 🚨 Critical: Avg latency > 1000ms
- ⚠️ Warning: Memory growth > 20%/hour

#### 5. Data Accuracy (During Parallel Run)
```python
accuracy_metrics = {
    'comparisons_count': int,
    'divergences_count': int,
    'max_divergence_pct': float,
    'avg_divergence_pct': float
}
```

**Alerts**:
- ⚠️ Warning: Divergence > 0.1%
- 🚨 Critical: Divergence > 1%

### Monitoring Dashboard

**File**: `monitoring/hybrid_ws_dashboard.py`

```python
#!/usr/bin/env python3
"""
Hybrid WebSocket Monitoring Dashboard
"""

import asyncio
import time
from datetime import datetime
from collections import deque


class HybridWSMonitor:
    """Monitor hybrid WebSocket health"""

    def __init__(self, hybrid_stream):
        self.stream = hybrid_stream
        self.event_timestamps = deque(maxlen=1000)
        self.start_time = time.time()

    async def run_dashboard(self):
        """Run monitoring dashboard"""
        while True:
            await asyncio.sleep(30)  # Update every 30s
            self._print_dashboard()

    def _print_dashboard(self):
        """Print monitoring dashboard"""
        print("\n" + "=" * 80)
        print(f"HYBRID WEBSOCKET DASHBOARD - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        # Connection status
        print("\n📡 CONNECTION STATUS:")
        print(f"   Private WS:  {'✅ Connected' if self.stream.private_connected else '❌ Disconnected'}")
        print(f"   Public WS:   {'✅ Connected' if self.stream.public_connected else '❌ Disconnected'}")

        # Uptime
        uptime = time.time() - self.start_time
        print(f"   Uptime:      {uptime / 3600:.1f} hours")

        # Subscriptions
        print("\n📊 SUBSCRIPTIONS:")
        print(f"   Active tickers: {len(self.stream.subscribed_tickers)}")
        print(f"   Active positions: {len(self.stream.positions)}")

        # Event flow
        recent_events = len([ts for ts in self.event_timestamps
                           if time.time() - ts < 60])
        print("\n📈 EVENT FLOW (last 60s):")
        print(f"   Events: {recent_events}")
        print(f"   Rate: {recent_events / 60:.2f} events/sec")

        # Performance
        if self.event_timestamps:
            last_event = time.time() - self.event_timestamps[-1]
            print(f"   Last event: {last_event:.1f}s ago")

        print("=" * 80)

    def on_event(self, event_type, data):
        """Track event"""
        self.event_timestamps.append(time.time())
```

Usage in main.py:
```python
# main.py

from monitoring.hybrid_ws_dashboard import HybridWSMonitor

class TradingBot:
    async def start(self):
        # ... setup streams ...

        # Start monitoring dashboard
        self.hybrid_monitor = HybridWSMonitor(self.bybit_hybrid_stream)
        asyncio.create_task(self.hybrid_monitor.run_dashboard())
```

---

## Rollback Plan

### Trigger Conditions

**Automatic Rollback** if:
1. 🚨 Both WebSockets disconnected for > 5 minutes
2. 🚨 No events for > 5 minutes
3. 🚨 > 10 subscription failures in 1 hour
4. 🚨 Critical error in event processing

**Manual Rollback** if:
1. ⚠️ Latency > 1000ms for > 5 minutes
2. ⚠️ Price divergence > 1%
3. ⚠️ Missed TS activation
4. ⚠️ Any trading error

### Rollback Procedure

#### Step 1: Enable Fallback (30 seconds)

```python
# main.py: Emergency fallback

class TradingBot:
    async def emergency_fallback_to_rest(self):
        """Emergency fallback to REST polling"""
        logger.critical("🚨 EMERGENCY FALLBACK TO REST POLLING")

        # Stop hybrid stream
        if self.bybit_hybrid_stream:
            await self.bybit_hybrid_stream.stop()
            self.bybit_hybrid_stream = None

        # Start REST polling
        from websocket.adaptive_stream import AdaptiveBybitStream

        self.bybit_adaptive_stream = AdaptiveBybitStream(
            exchange_manager=self.exchange_manager,
            event_handler=self._handle_stream_event,
            testnet=False
        )
        await self.bybit_adaptive_stream.start()

        logger.info("✅ REST polling activated")
```

#### Step 2: Validate Fallback (2 minutes)

- ✅ REST polling connected
- ✅ Positions loaded
- ✅ Events flowing
- ✅ TS tracking prices

#### Step 3: Post-Rollback Analysis

1. Collect logs
2. Analyze failure
3. Identify root cause
4. Create fix
5. Re-test on testnet
6. Re-deploy when ready

### Rollback Testing

**Test rollback procedure during canary phase**:

```python
# Test script: tests/manual/test_rollback.py

async def test_rollback():
    """Test emergency rollback"""
    bot = TradingBot()
    await bot.start()

    # Wait for hybrid to stabilize
    await asyncio.sleep(30)

    # Trigger rollback
    logger.info("🧪 Testing rollback...")
    await bot.emergency_fallback_to_rest()

    # Wait for REST to stabilize
    await asyncio.sleep(30)

    # Verify
    assert bot.bybit_adaptive_stream is not None
    assert bot.bybit_hybrid_stream is None

    logger.info("✅ Rollback test passed")
```

---

## Success Metrics

### Technical Metrics

#### Latency
- **Target**: < 200ms average
- **Baseline (REST)**: ~10,000ms
- **Improvement**: 50x faster

#### Update Frequency
- **Target**: 10 updates/second
- **Baseline (REST)**: 0.1 updates/second (every 10s)
- **Improvement**: 100x more frequent

#### Reliability
- **Target**: 99.9% uptime
- **Target**: < 5 reconnections/day
- **Target**: Zero data loss during reconnection

### Business Metrics

#### TS Activation Speed
- **Before**: 10s average delay (REST polling)
- **After**: < 1s delay (WebSocket)
- **Impact**: Faster protection = better PnL

#### False Activations
- **Target**: No increase in false activations
- **Monitoring**: Track TS activation quality

#### Position Tracking
- **Target**: 100% positions tracked
- **Target**: Zero missed updates

---

## Risk Mitigation

### Risk 1: Connection Failures
**Mitigation**:
- ✅ Auto-reconnection with exponential backoff
- ✅ Subscription restoration after reconnect
- ✅ Fallback to REST polling on failure
- ✅ Alerts on repeated failures

### Risk 2: Event Loss During Reconnection
**Mitigation**:
- ✅ Fetch latest position data on reconnect
- ✅ Re-subscribe to all active tickers
- ✅ Validate position state after reconnect
- ✅ Alert if position count mismatch

### Risk 3: Price Divergence
**Mitigation**:
- ✅ Parallel run validation phase
- ✅ Continuous price validation
- ✅ Alert on divergence > 0.1%
- ✅ Rollback if critical divergence

### Risk 4: Performance Degradation
**Mitigation**:
- ✅ Performance monitoring
- ✅ Memory leak detection
- ✅ Load testing before production
- ✅ Rate limiting on subscriptions

### Risk 5: Subscription Failures
**Mitigation**:
- ✅ Retry logic for subscriptions
- ✅ Subscription health monitoring
- ✅ Alert on repeated failures
- ✅ Fallback to polling if can't subscribe

---

## Timeline Summary

### Week 1-3: Development & Testing
- Unit tests
- Integration tests
- System tests
- Performance tests
- Failover tests

### Week 4: Production Deployment

**Day 1-2**: Canary
- Deploy hybrid in monitor-only mode
- Validate connections and events
- Monitor performance

**Day 3**: Parallel Run
- Both hybrid and REST active
- Compare data accuracy
- Build confidence

**Day 4**: Gradual Cutover
- Morning: 50% cutover
- Afternoon: 100% cutover (if stable)
- Intensive monitoring

**Day 5**: Full Production
- Hybrid as primary
- REST deprecated
- Normal monitoring

---

## Deployment Checklist

### Pre-Deployment
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] All system tests passing
- [ ] Performance benchmarks met
- [ ] Failover tests passing
- [ ] Code review complete
- [ ] Documentation complete
- [ ] Monitoring dashboard ready
- [ ] Rollback procedure tested

### Canary Phase
- [ ] Hybrid stream deployed
- [ ] Both WebSockets connected
- [ ] Events flowing to canary handler
- [ ] Metrics dashboard active
- [ ] No errors in logs
- [ ] Performance metrics good

### Parallel Run Phase
- [ ] Both streams running
- [ ] Data validation active
- [ ] Comparison metrics tracking
- [ ] Price accuracy > 99.9%
- [ ] No critical divergences
- [ ] Team approval to proceed

### Cutover Phase
- [ ] 50% cutover deployed
- [ ] 4 hours stable operation
- [ ] 100% cutover deployed
- [ ] All positions tracked
- [ ] All events flowing
- [ ] TS activating correctly

### Production Phase
- [ ] Hybrid as primary
- [ ] REST polling removed
- [ ] Monitoring active
- [ ] Team notified
- [ ] Documentation updated
- [ ] Deployment successful

---

## Conclusion

This deployment plan provides:

1. **Safety**: Incremental rollout with validation at each step
2. **Reversibility**: Clear rollback procedure tested in advance
3. **Observability**: Comprehensive monitoring and alerts
4. **Confidence**: Parallel validation before cutover
5. **Speed**: 4-day deployment timeline

**Total Timeline**: 4 weeks (3 weeks dev/test + 1 week deployment)

**Risk Level**: LOW (with proper execution of this plan)

**Next Step**: Begin Phase 1 development (Unit Tests)
