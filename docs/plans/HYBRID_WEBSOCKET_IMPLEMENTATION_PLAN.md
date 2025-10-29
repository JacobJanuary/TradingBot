# BYBIT HYBRID WEBSOCKET - COMPLETE IMPLEMENTATION PLAN
**Date**: 2025-10-25
**Status**: 📋 READY FOR IMPLEMENTATION
**Type**: PRODUCTION-GRADE ARCHITECTURE

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Component Design](#component-design)
4. [Implementation Steps](#implementation-steps)
5. [Code Examples](#code-examples)
6. [Integration Plan](#integration-plan)
7. [Testing Strategy](#testing-strategy)
8. [Rollout Plan](#rollout-plan)
9. [Monitoring & Observability](#monitoring--observability)
10. [Rollback Plan](#rollback-plan)

---

## Executive Summary

### Goal
Replace REST polling with WebSocket-based position price updates for Bybit mainnet using hybrid approach:
- **Private WebSocket** → Position lifecycle (open/close/modify)
- **Public WebSocket** → Mark price updates (100ms frequency)

### Benefits
- ✅ Real-time price updates (100ms vs 10s)
- ✅ Lower API usage (public WS = no rate limits)
- ✅ Faster TS activation (100ms latency vs 10s)
- ✅ Production-grade architecture
- ✅ Proven patterns from existing codebase

### Risk
- **MEDIUM**: Two WebSocket streams to manage
- **Mitigation**: Extensive testing, gradual rollout, clear fallback

---

## Architecture Overview

### Current Architecture (REST Polling)

```
AdaptiveBybitStream (Testnet/Mainnet)
  ↓ [Poll every 5-10s]
fetch_positions()
  ↓ [Extract mark prices]
emit('position.update', {symbol, mark_price, ...})
  ↓ [EventRouter]
Position Manager → TS → Aged Monitor
```

**Problems**:
- ❌ 5-10 second delay
- ❌ API rate limits
- ❌ Not real-time

---

### New Architecture (Hybrid WebSocket)

```
┌─────────────────────────────────────────┐
│   BybitHybridStream                     │
│                                         │
│  ┌───────────────┐  ┌────────────────┐ │
│  │ Private WS    │  │ Public WS      │ │
│  │ (position)    │  │ (tickers)      │ │
│  └───────┬───────┘  └────────┬───────┘ │
│          │                   │         │
│          ↓                   ↓         │
│  ┌───────────────────────────────────┐ │
│  │   Hybrid Event Processor          │ │
│  │   - Combines both streams         │ │
│  │   - Manages ticker subscriptions  │ │
│  │   - Deduplicates events           │ │
│  └───────────────┬───────────────────┘ │
└──────────────────┼─────────────────────┘
                   ↓
        emit('position.update', {
          symbol, mark_price,
          size, side, ...
        })
                   ↓
            Event Router
                   ↓
    ┌──────────────┼──────────────┐
    ↓              ↓              ↓
Position Mgr    TS Module    Aged Monitor
```

---

## Component Design

### 1. BybitHybridStream

**Parent Class**: `ImprovedStream`

**Responsibilities**:
1. Manage TWO WebSocket connections
2. Sync position lifecycle from private WS
3. Stream mark prices from public WS
4. Combine data and emit unified events
5. Handle dynamic ticker subscriptions
6. Provide fallback mechanisms

**Key Features**:
- ✅ Inherits ping-pong (20s for Bybit)
- ✅ Inherits reconnection logic
- ✅ Inherits connection monitoring
- ✅ Custom: Two stream coordination

---

### 2. Private WebSocket Stream

**Purpose**: Position lifecycle tracking

**Subscription**: `"position"`

**Events**:
- Position opened (size > 0)
- Position closed (size = 0)
- Position modified (size changed)
- Stop-loss/Take-profit updates

**Usage**:
```python
# When position opens
→ Add symbol to active_symbols
→ Subscribe to ticker for this symbol

# When position closes
→ Remove symbol from active_symbols
→ Unsubscribe from ticker
```

---

### 3. Public WebSocket Stream

**Purpose**: Real-time mark price updates

**Subscription**: `"tickers.{symbol}"`

**Update Frequency**: 100ms for derivatives

**Data**:
```json
{
  "topic": "tickers.1000NEIROCTOUSDT",
  "data": {
    "symbol": "1000NEIROCTOUSDT",
    "markPrice": "0.1950",
    "lastPrice": "0.1949",
    "volume24h": "1234567",
    ...
  }
}
```

**Usage**:
- Continuous mark price updates for active positions
- No authentication required
- No rate limits (public stream)

---

### 4. Hybrid Event Processor

**Purpose**: Combine data from both streams

**Logic**:
```python
# State
positions = {}  # {symbol: {position_data}}
mark_prices = {}  # {symbol: latest_mark_price}

# Private WS event
def on_position_update(data):
    symbol = data['symbol']
    size = float(data['size'])

    if size > 0:
        # Position active
        positions[symbol] = data
        # Use latest mark price if available
        if symbol in mark_prices:
            data['markPrice'] = mark_prices[symbol]
    else:
        # Position closed
        if symbol in positions:
            del positions[symbol]

    emit_combined_event(symbol, data)

# Public WS event
def on_ticker_update(data):
    symbol = data['symbol']
    mark_price = data['markPrice']

    # Update cache
    mark_prices[symbol] = mark_price

    # If we have position data, emit combined event
    if symbol in positions:
        position_data = positions[symbol].copy()
        position_data['markPrice'] = mark_price
        emit_combined_event(symbol, position_data)
```

---

### 5. Dynamic Subscription Manager

**Purpose**: Subscribe/unsubscribe tickers based on active positions

**Logic**:
```python
# Track subscriptions
subscribed_tickers = set()

async def on_position_opened(symbol):
    """Position opened - subscribe to ticker"""
    if symbol not in subscribed_tickers:
        await subscribe_ticker(symbol)
        subscribed_tickers.add(symbol)

async def on_position_closed(symbol):
    """Position closed - unsubscribe from ticker"""
    if symbol in subscribed_tickers:
        await unsubscribe_ticker(symbol)
        subscribed_tickers.remove(symbol)

async def subscribe_ticker(symbol):
    """Subscribe to ticker topic"""
    msg = {
        "op": "subscribe",
        "args": [f"tickers.{symbol}"]
    }
    await public_ws.send(json.dumps(msg))

async def unsubscribe_ticker(symbol):
    """Unsubscribe from ticker topic"""
    msg = {
        "op": "unsubscribe",
        "args": [f"tickers.{symbol}"]
    }
    await public_ws.send(json.dumps(msg))
```

---

## Implementation Steps

### Phase 1: Core Infrastructure (Week 1)

**Step 1.1**: Create `BybitHybridStream` skeleton
**Step 1.2**: Implement dual WebSocket management
**Step 1.3**: Add private WS with position topic
**Step 1.4**: Add public WS with ticker topic
**Step 1.5**: Implement basic event combining

**Deliverable**: Working dual-stream connection

---

### Phase 2: Event Processing (Week 1-2)

**Step 2.1**: Implement hybrid event processor
**Step 2.2**: Add position state tracking
**Step 2.3**: Add mark price caching
**Step 2.4**: Implement event deduplication
**Step 2.5**: Add event emission logic

**Deliverable**: Combined events emitted correctly

---

### Phase 3: Subscription Management (Week 2)

**Step 3.1**: Implement dynamic ticker subscriptions
**Step 3.2**: Add subscription lifecycle (sub/unsub)
**Step 3.3**: Handle initial positions (restore subs on connect)
**Step 3.4**: Add subscription error handling
**Step 3.5**: Implement subscription rate limiting

**Deliverable**: Automatic ticker sub/unsub on position lifecycle

---

### Phase 4: Integration (Week 2-3)

**Step 4.1**: Integrate with main.py
**Step 4.2**: Update event formats for Position Manager
**Step 4.3**: Test TS integration
**Step 4.4**: Test Aged Monitor integration
**Step 4.5**: Add compatibility layer for existing code

**Deliverable**: Full system integration working

---

### Phase 5: Testing & Validation (Week 3)

**Step 5.1**: Unit tests for each component
**Step 5.2**: Integration tests
**Step 5.3**: Load testing
**Step 5.4**: Failover testing
**Step 5.5**: Performance benchmarking

**Deliverable**: Comprehensive test coverage

---

### Phase 6: Production Rollout (Week 4)

**Step 6.1**: Canary deployment (monitor mode)
**Step 6.2**: Parallel run (hybrid + REST)
**Step 6.3**: Gradual cutover
**Step 6.4**: Full production deployment
**Step 6.5**: REST polling deprecation

**Deliverable**: Production deployment complete

---

## Code Examples

### File Structure
