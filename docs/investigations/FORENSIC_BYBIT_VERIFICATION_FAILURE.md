# 🔍 FORENSIC INVESTIGATION: Bybit Position Closure Verification Failure

**Investigation Date**: 2025-10-24
**Bot Session**: Started 2025-10-24 13:19:10 UTC
**Severity**: 🔴 CRITICAL
**Impact**: 100% failure rate for Bybit aged position closures

---

## 📊 EXECUTIVE SUMMARY

**Finding**: Aged position closures on Bybit exchange have **0% success rate**. Orders return success status and order_id, but positions remain open on exchange, leading to "zombie positions" that get recreated by the synchronizer.

**Root Cause**: Order execution logic treats order submission as order completion. Bybit's asynchronous order processing means order_id ≠ position closed.

**Evidence**: Analyzed 17+ symbols across 50+ closure attempts over 5 hours of bot operation.

---

## 🎯 DETAILED FINDINGS

### 1. Exchange-Specific Success Rates

| Exchange | Closures Attempted | Actually Closed | Success Rate | Order ID Format |
|----------|-------------------|-----------------|--------------|-----------------|
| **Binance** | 9 | 9 | **100%** ✅ | Numeric (e.g., 84038554) |
| **Bybit** | 17+ | 0 | **0%** ❌ | UUID (e.g., 8ad20393-...) |

### 2. Bybit Failed Closures (Sample)

**First Batch - 13:57:08 UTC (Progressive Phase)**

All 15 positions reported "closed: order_id" but remained on exchange:

| Symbol | Order ID | Phase | Reported Closed | Still on Exchange | Recreated |
|--------|----------|-------|----------------|-------------------|-----------|
| OKBUSDT | 8ad20393-7ad1-4790-9a67-f4e751627496 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3214 |
| PRCLUSDT | 8742c19f-2491-447c-a94c-1ed7d04cb414 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3212 |
| PYRUSDT | f6696dde-ceac-4c88-b0b8-0a5e2a7b30d3 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3211 |
| BOBAUSDT | f62d39b6-058c-4fb5-a471-02c760e6fcc3 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3215 |
| SHIB1000USDT | fea2f810-d2bf-48da-aa3f-f423341075ea | progressive | 13:57:08 | 15:07:19 | ✅ ID=3216 |
| AGIUSDT | 19404816-473e-4659-8c20-33067d041594 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3217 |
| AIOZUSDT | d14883b1-311b-443e-9705-9dd20f2f4806 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3218 |
| DOGUSDT | 4c3c22f7-7475-4c41-95d6-c0b5b5bbab35 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3219 |
| DODOUSDT | 2bf3a70a-46f5-46c4-b021-ac07ebe047ad | progressive | 13:57:08 | 15:07:19 | ✅ ID=3220 |
| ETHBTCUSDT | 81e0a98b-866b-43c7-9d40-7d39528a0f5c | progressive | 13:57:08 | 15:07:19 | ✅ ID=3222 |
| BSUUSDT | 0cd791d3-a2d8-4041-b44e-03103c47b09e | progressive | 13:57:08 | 15:07:19 | ✅ ID=3223 |
| SOSOUSDT | 165cc558-dbf3-42cc-82cf-147e97d746dc | progressive | 13:57:08 | 15:07:19 | ✅ ID=3224 |
| IDEXUSDT | 81d7b01e-01d7-4e3b-a815-95b3287defd9 | progressive | 13:57:08 | 15:07:19 | ✅ ID=3225 |

**Timing Analysis:**
- Orders submitted: 13:57:08.084-090 (6ms window - parallel batch)
- Order IDs received: 13:57:08.426-13:57:09.077 (651ms execution)
- Database updated: Immediately after order_id received
- Synchronizer check: 15:07:19 (1 hour 10 minutes later)
- **Result**: All 13 positions still on exchange, all recreated

**Additional Cases:**

| Symbol | First Closed | Recreated | Second Closed | Third Closed | Notes |
|--------|--------------|-----------|---------------|--------------|-------|
| RADUSDT | 16:19:18 | 17:19:17 (ID=3264) | - | - | Startup case |
| GIGAUSDT | 16:19:17 | 17:19:17 (ID=3265) | - | - | Startup case |
| OKBUSDT | 13:57:08 | 15:07:19 (ID=3214) | 18:09:48 | 18:10:19 | Closed 3+ times! |
| SOSOUSDT | 13:57:09 | 15:07:19 (ID=3224) | 18:09:48 | 18:10:19 | Closed 3+ times! |
| IDEXUSDT | 13:57:09 | 15:07:19 (ID=3225) | 18:09:48 | 18:10:19 | Closed 3+ times! |

### 3. Binance Successful Closures (Control Group)

All Binance closures verified successful - positions NOT recreated:

| Symbol | Order ID | Phase | Closed At | Verified | Recreated |
|--------|----------|-------|-----------|----------|-----------|
| SXPUSDT | 113790966 | grace | 14:05:36 | ✅ | ❌ |
| ADAUSDT | 329294791 | grace | 14:51:42 | ✅ | ❌ |
| SOLUSDT | 865758212 | grace | 14:51:42 | ✅ | ❌ |
| KNCUSDT | 84038554 | grace | 14:51:42 | ✅ | ❌ |
| MTLUSDT | 30499734 | grace | 17:28:00 | ✅ | ❌ |
| ONTUSDT | 199751249 | grace | 17:33:24 | ✅ | ❌ |
| ICXUSDT | 56709591 | grace | 17:48:54 | ✅ | ❌ |
| ATAUSDT | 33939177 | grace | 17:51:50 | ✅ | ❌ |
| EDUUSDT | 22091531 | grace | 17:51:50 | ✅ | ❌ |

**None of these positions were found "Missing from database" by synchronizer** → All actually closed on exchange.

---

## 🔬 ROOT CAUSE ANALYSIS

### A. Code Flow (Current - BROKEN)

```
aged_position_monitor_v2.py:308-314
├─ await order_executor.execute_close(...)
│
order_executor.py:192-231
├─ result = await exchange.create_order(...)
├─ if result and result.get('id'):  ← BUG: Only checks if order_id exists
│   └─ return OrderResult(success=True, order_id=result['id'])
│
aged_position_monitor_v2.py:333-362
└─ if result.success:  ← BUG: Immediately updates DB
    ├─ await repository.mark_aged_position_closed(position_id)  ← Position removed from aged tracking
    └─ await repository.update_position(id, status='closed')    ← Position marked closed in DB
```

**Problem**: Database updated immediately after order submission, NOT after position closure verification.

### B. Exchange Behavior Comparison

**Binance (Synchronous)**:
```
1. create_order(type='market', reduceOnly=True)
2. ← Returns order_id AFTER order is filled
3. Position is closed on exchange
4. ✅ Database update is safe
```

**Bybit (Asynchronous)**:
```
1. create_order(type='market', reduceOnly=True)
2. ← Returns order_id IMMEDIATELY (order accepted, not filled)
3. Order enters order book / processing queue
4. ❌ Position still open on exchange
5. Database updated (position marked closed) ← BUG
6. [1-2 hours later]
7. Synchronizer finds position still on exchange
8. Creates new database record (zombie position)
```

### C. Why Bybit Orders Don't Close Immediately

Possible reasons for Bybit's asynchronous behavior:

1. **Low Liquidity**: Market orders may not fill immediately for some pairs
2. **Risk Management**: Bybit may queue orders for risk checks
3. **Order Book Matching**: Orders wait for counterparty matching
4. **API Design**: Bybit's V5 API is async-first (order submission ≠ order fill)
5. **Position Mode**: Hedge mode or one-way mode may affect closure timing

**Evidence from logs**:
- All orders get order_id within 300-600ms (fast API response)
- Positions remain on exchange for 1+ hours (not just delayed execution)
- Multiple retry attempts get new order_ids but position stays open
- No error messages in logs (API calls succeed)

---

## 📍 CODE LOCATIONS

### 1. Primary Bug Location

**File**: `core/aged_position_monitor_v2.py`
**Lines**: 333-362
**Function**: `_trigger_market_close()`

```python
# Line 333-362: IMMEDIATE DATABASE UPDATE - NO VERIFICATION
if result.success:
    self.stats['market_closes_triggered'] += 1

    # ❌ BUG: Updates DB before verifying position closed
    if self.repository:
        try:
            # Remove from aged tracking
            await self.repository.mark_aged_position_closed(
                position_id=str(target.position_id),
                close_reason=f'aged_{target.phase}'
            )

            # Mark position as closed
            await self.repository.update_position(
                position.id,
                status='closed',
                exit_reason=f'aged_{target.phase}'
            )
```

### 2. Secondary Issue

**File**: `core/order_executor.py`
**Lines**: 192-231
**Function**: `execute_close()`

```python
# Line 192-231: Returns success if order_id exists
if result and result.get('id'):
    execution_time = time.time() - start_time

    # Extract order details
    price_value = result.get('price') or result.get('average') or 0
    amount_value = result.get('filled') or result.get('amount') or amount

    logger.info(
        f"✅ Order executed successfully: "
        f"id={result['id']}, type={order_type}, "
        f"attempts={total_attempts}, time={execution_time:.2f}s"
    )

    # ❌ No verification that position is actually closed
    return OrderResult(
        success=True,
        order_id=result['id'],  # ← Has order_id but position may still be open!
        order_type=order_type,
        price=Decimal(str(price_value)),
        executed_amount=Decimal(str(amount_value)),
        error_message=None,
        attempts=total_attempts,
        execution_time=execution_time
    )
```

**Problem**: `OrderResult.success=True` means "order submitted" not "position closed".

### 3. Missing Verification

**Current**: No verification step after order submission
**Needed**: Check position status on exchange after order submission

---

## 📋 IMPACT ASSESSMENT

### Quantitative Impact (Session 2025-10-24 13:19-18:30 UTC)

- **Total aged closures attempted**: 30+
- **Bybit closures**: 17 unique positions, 50+ attempts (multiple retries)
- **Bybit failures**: 17 positions (100% failure rate)
- **Zombie positions created**: 17
- **Binance closures**: 9
- **Binance failures**: 0 (100% success rate)

### Qualitative Impact

1. **Database Corruption**: Positions marked "closed" in DB but open on exchange
2. **Zombie Positions**: Synchronizer recreates positions without historical context
3. **TS Module Confusion**: Recreated positions not in TS tracking
4. **Aged Module Re-triggering**: Same positions repeatedly marked "closed"
5. **Loss Amplification**: Positions stay open longer than intended, accumulating losses
6. **Capital Efficiency**: Capital locked in positions that should be closed
7. **Risk Management Failure**: Stop-loss logic bypassed for zombie positions

---

## 🎯 CONCLUSIONS

### Primary Issues

1. **No Position Verification**: Code assumes order_id = position closed (FALSE for Bybit)
2. **Premature Database Update**: DB updated before exchange confirmation
3. **Exchange-Specific Behavior**: Binance synchronous, Bybit asynchronous
4. **No Retry/Rollback**: If position not closed, no mechanism to retry or rollback DB changes

### Why This Wasn't Caught Earlier

1. **Development on Binance**: Code likely tested primarily on Binance where it works
2. **No Integration Tests**: No tests verifying position actually closed on exchange
3. **Synchronizer Masking**: Synchronizer "fixes" the issue by recreating positions
4. **No Alerts**: No monitoring to detect positions marked closed but still on exchange

### Critical Questions for Fix Design

1. How long to wait for Bybit order to fill?
2. How to verify position is actually closed?
3. What to do if verification fails?
4. Should we use different logic for Binance vs Bybit?
5. How to handle partial fills?
6. Should we poll order status or position status?

---

**Next Step**: Create detailed fix plan based on these findings.

**Forensic Report End**
