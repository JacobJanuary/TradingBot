# WebSocket Monitoring Architecture

## CURRENT FLOW

```
PositionManager
    |
    +-> update_price(symbol, price)
         |
         +-> UnifiedPriceMonitor.update_price()
              |
              +-> Rate limiting check (100ms)
              |
              +-> Store: last_update_time[symbol] = now  (FLOAT!)
              |
              +-> Store: last_prices[symbol] = price
              |
              +-> Notify subscribers
                   |
                   +-> AgedPositionMonitorV2.check_price_target()
                   |    |
                   |    +-> Check if target price reached
                   |    |
                   |    +-> Log event to DB
                   |    |
                   |    +-> Trigger close if needed
                   |
                   +-> TrailingStopManager.update_price()
                        |
                        +-> Update trailing stop levels
```

---

## PROBLEM: MISSING PER-SYMBOL HEALTH TRACKING

```
Current:                          Missing:
==========                         ==========
UnifiedPriceMonitor              Per-Symbol Health Monitor
├─ last_update_time              ├─ last_update_timestamp (datetime)
│  └─ Dict[symbol, float]         │  └─ Dict[symbol, datetime]
├─ last_prices                    ├─ symbol_health
│  └─ Dict[symbol, Decimal]       │  └─ Dict[symbol, {
└─ update_count (global)          │      status, staleness_seconds,
                                  │      last_update, ...
ImprovedStream                    │    }]
├─ last_heartbeat                 └─ get_staleness_seconds(symbol)
├─ last_pong                         └─ returns seconds since update
└─ _check_connection_health()
   └─ Global connection check only

HealthChecker                     Enhanced HealthChecker
├─ _check_websocket() MOCK!       ├─ _check_websocket() with real data
├─ _check_signal_processor()      ├─ _check_price_updates() NEW!
└─ No per-symbol monitoring       └─ Per-symbol staleness detection
```

---

## PROPOSED SOLUTION ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                     UnifiedPriceMonitor                       │
├─────────────────────────────────────────────────────────────┤
│ Storage:                                                      │
│  - last_update_time: Dict[symbol, float]        [EXISTING]  │
│  - last_update_timestamp: Dict[symbol, datetime] [NEW]      │
│  - last_prices: Dict[symbol, Decimal]           [EXISTING]  │
│  - symbol_health: Dict[symbol, HealthDict]      [NEW]       │
│                                                              │
│ Methods:                                                     │
│  - update_price(symbol, price)      [ENHANCED]              │
│  - get_staleness_seconds(symbol)    [NEW]                   │
│  - get_symbol_health(symbol)        [NEW]                   │
│  - cleanup_stale_data()             [NEW]                   │
└─────────────────────────────────────────────────────────────┘
           │                                       │
           │                                       │
           ▼                                       ▼
┌──────────────────────────┐  ┌────────────────────────────────┐
│   AgedPositionMonitor    │  │    HealthChecker (Monitoring)  │
├──────────────────────────┤  ├────────────────────────────────┤
│ check_price_target():    │  │ _check_price_updates():        │
│  - NEW: Check staleness  │  │  - Check all symbols           │
│  - Skip if > 5min        │  │  - Alert if > 5min stale       │
│  - Log warning/critical  │  │  - Save to DB                  │
│  - Continue if healthy   │  │  - Set status CRITICAL         │
│                          │  │                                 │
│ + Staleness guards      │  │ _check_websocket():            │
│   (3+ min = WARNING)     │  │  - Real, not MOCK!             │
│   (5+ min = CRITICAL)    │  │  - Per-symbol metrics          │
└──────────────────────────┘  │  - Dependency tracking         │
                               └────────────────────────────────┘
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │  Database    │
                                 ├──────────────┤
                                 │ alerts table │
                                 │ health_logs  │
                                 └──────────────┘
```

---

## STALENESS DETECTION FLOW

```
Price Update Received
│
├─ Update timestamp
│  └─ last_update_timestamp[symbol] = datetime.now()
│
├─ Check staleness before callback
│  └─ if get_staleness_seconds(symbol) > 300:  [5 MINUTES]
│     └─ LOG: "Price for {symbol} is stale"
│     └─ ALERT: Generate critical alert
│     └─ SKIP: Don't process checks
│
└─ If staleness OK
   └─ Notify subscribers
      ├─ AgedPositionMonitor.check_price_target()
      │  └─ Can safely execute close
      │
      └─ TrailingStopManager.update_price()
         └─ Can safely update levels
```

---

## HEALTH STATUS LEVELS

```
Symbol Health States:
═════════════════════

HEALTHY:
  ├─ Last update < 180 seconds
  ├─ Updates coming regularly
  └─ Safe to process all checks

DEGRADED:
  ├─ Last update 180-300 seconds (3-5 minutes)
  ├─ Should log warnings
  └─ Can process but with caution

STALE:
  ├─ Last update > 300 seconds (5+ minutes)
  ├─ Should log critical alerts
  └─ SKIP all position-related checks

CRITICAL:
  ├─ No updates for > 1 hour
  ├─ Likely connection issue
  └─ Require immediate reconnection
```

---

## DATABASE INTEGRATION

```
New Tables to Create:
═════════════════════

1. price_staleness_alerts
   ├─ id (PK)
   ├─ symbol
   ├─ detected_at
   ├─ staleness_seconds
   ├─ alert_level ('warning', 'critical')
   ├─ resolved_at
   └─ notes

2. symbol_health_history
   ├─ id (PK)
   ├─ symbol
   ├─ timestamp
   ├─ status ('healthy', 'degraded', 'stale', 'critical')
   ├─ staleness_seconds
   └─ update_count

3. websocket_health_logs
   ├─ id (PK)
   ├─ timestamp
   ├─ component ('unified_monitor', 'improved_stream', 'health_checker')
   ├─ message
   ├─ status_code
   └─ metadata (JSON)
```

---

## TIMELINE: MIGRATION PLAN

```
Phase 1: Add Staleness Detection (HIGH PRIORITY)
  Week 1:
    - Add datetime tracking to UnifiedPriceMonitor
    - Implement get_staleness_seconds() method
    - Add staleness check in aged_position_monitor
    └─ Risk: MINIMAL (additive only)

Phase 2: Health Monitoring (MEDIUM PRIORITY)
  Week 2-3:
    - Implement real _check_websocket() in HealthChecker
    - Add _check_price_updates() method
    - Database table for alerts
    └─ Risk: LOW (no changes to existing code)

Phase 3: Per-Symbol Tracking (LOW PRIORITY)
  Week 4:
    - Add symbol_health in UnifiedPriceMonitor
    - Per-symbol health in ImprovedStream
    - Dashboard/API endpoints
    └─ Risk: LOW (enhancements only)

Phase 4: Alerts & Automation (OPTIONAL)
  Future:
    - Email/Slack alerts for stale data
    - Auto-reconnection per symbol
    - Fallback to REST API if WebSocket stale
    └─ Risk: MEDIUM (requires external services)
```

---

## CRITICAL INTEGRATION POINTS

```
1. UnifiedPriceMonitor ←→ HealthChecker
   ├─ New: HealthChecker needs reference to price_monitor
   ├─ Method: Set during initialization
   └─ Fallback: Check if attribute exists

2. AgedPositionMonitor ←→ UnifiedPriceMonitor
   ├─ Current: Gets called via callback
   ├─ New: Check staleness before processing
   └─ Fallback: Skip check if staleness info unavailable

3. PositionManager ←→ UnifiedPriceMonitor
   ├─ Current: Calls update_price()
   ├─ No changes needed
   └─ Works with enhanced version transparently

4. ImprovedStream ←→ UnifiedPriceMonitor
   ├─ Current: Sends messages to handler
   ├─ New: Could track per-symbol timestamps
   └─ Optional enhancement
```

---

## SAFETY MECHANISMS

```
Fallback Strategies:
═════════════════════

IF get_staleness_seconds() not available:
  └─ Use time.time() based calculation
  └─ Fall back to float timestamp

IF price_monitor reference missing:
  └─ Health check returns UNKNOWN
  └─ All checks execute normally

IF database unavailable:
  └─ Log to memory cache
  └─ Write to DB when available

IF WebSocket stale for > 10 minutes:
  └─ Force reconnection
  └─ Don't wait for next health check
```

---

## TESTING CHECKLIST

```
Unit Tests:
  [ ] get_staleness_seconds() with various ages
  [ ] Staleness threshold logic (3, 5, 10 min)
  [ ] Per-symbol health updates
  [ ] Database alert creation

Integration Tests:
  [ ] UnifiedPriceMonitor → aged position checks
  [ ] HealthChecker → real WebSocket data
  [ ] Alert generation pipeline
  [ ] Recovery after stale → healthy transition

Scenario Tests:
  [ ] WebSocket stale for 5 minutes
  [ ] Multiple symbols with different ages
  [ ] Connection drop and recovery
  [ ] Aged position during stale price
  [ ] High-frequency price updates
```

