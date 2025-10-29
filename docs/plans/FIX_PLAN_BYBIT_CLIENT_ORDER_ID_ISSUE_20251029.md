# FIX PLAN: Bybit Client Order ID Issue
## Date: 2025-10-29
## Issue: GIGAUSDT "missing 'side' field" - CLIENT ORDER ID vs EXCHANGE ORDER ID

---

## PROBLEM STATEMENT

**Root Cause (100% Confirmed):**

Bybit's `create_market_order()` returns CLIENT ORDER ID (UUID format) in the `id` field, NOT the exchange order ID. When code tries to `fetch_order(client_order_id)`, Bybit returns "500 order limit" error, causing:

1. All 5 retry attempts to fail
2. `raw_order` remains as minimal `create_market_order` response (no 'side' field)
3. `normalize_order()` raises `ValueError`
4. Position rollback despite actual position created on exchange
5. Phantom position (found later by position_synchronizer)

**Evidence:**
- GIGAUSDT order ID: `92f32008-68fc-4acf-96da-096a62d41007` (UUID = client order ID)
- Successful Binance orders: `314479319`, `607048514` (numeric = exchange order IDs)
- All 5 `fetch_order` attempts returned None with "500 order limit" error
- Position actually existed (WebSocket confirmed at T+346ms)

**Forensic Report:** `docs/investigations/GIGAUSDT_MISSING_SIDE_FIELD_FORENSIC_20251029.md`

---

## FIX OPTIONS

### Option A: Extract Exchange Order ID from Response ⭐ RECOMMENDED

**Approach:**
Use Bybit's `info['orderId']` field instead of CCXT's `id` field for `fetch_order` calls.

**Changes Required:**

1. **File:** `core/atomic_position_manager.py`
   **Location:** Lines 586-614 (fetch_order retry loop)

   **Before:**
   ```python
   if raw_order and raw_order.id:
       order_id = raw_order.id  # ← May be client order ID!

       for attempt in range(1, max_retries + 1):
           fetched_order = await exchange_instance.fetch_order(order_id, symbol)
   ```

   **After:**
   ```python
   if raw_order and raw_order.id:
       # CRITICAL FIX: For Bybit, extract EXCHANGE order ID from info
       # Bybit returns client order ID in 'id' but exchange order ID in info['orderId']
       if exchange == 'bybit' and hasattr(raw_order, 'info') and 'orderId' in raw_order.info:
           order_id = raw_order.info['orderId']
           logger.info(f"✅ Using Bybit exchange order ID from info: {order_id}")
       else:
           order_id = raw_order.id

       for attempt in range(1, max_retries + 1):
           fetched_order = await exchange_instance.fetch_order(order_id, symbol)
   ```

**Pros:**
- ✅ Minimal code changes (3-5 lines)
- ✅ Fixes root cause directly
- ✅ Works with existing retry logic
- ✅ No impact on other exchanges (Binance continues to work)
- ✅ fetch_order will work (exchange order ID is queryable)

**Cons:**
- ⚠️ Assumes `info['orderId']` always exists (need to verify with test script)
- ⚠️ Bybit-specific logic (but isolated with `if exchange == 'bybit'`)

**Risk Level:** LOW

**Testing Required:**
1. Run `test_bybit_order_id_investigation.py` to confirm `info['orderId']` exists
2. Test with real Bybit testnet order
3. Verify Binance still works

**Implementation Time:** 10 minutes

---

### Option B: Use fetch_positions Instead of fetch_order

**Approach:**
Skip `fetch_order` entirely for Bybit. Use `fetch_positions` to verify order was filled.

**Changes Required:**

1. **File:** `core/atomic_position_manager.py`
   **Location:** Lines 586-632

   **Before:**
   ```python
   for attempt in range(1, max_retries + 1):
       await asyncio.sleep(retry_delay)
       fetched_order = await exchange_instance.fetch_order(order_id, symbol)
       if fetched_order:
           raw_order = fetched_order
           break
   ```

   **After:**
   ```python
   if exchange == 'bybit':
       # BYBIT-SPECIFIC: Use fetch_positions instead of fetch_order
       # Reason: Bybit has 500 order query limit + client order ID issue
       logger.info(f"ℹ️  Using fetch_positions for Bybit verification (not fetch_order)")

       for attempt in range(1, max_retries + 1):
           await asyncio.sleep(retry_delay)

           positions = await exchange_instance.fetch_positions(
               symbols=[symbol],
               params={'category': 'linear'}
           )

           # Find our position
           for pos in positions:
               if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                   # Position exists! Construct order-like response for normalization
                   fetched_order = {
                       'id': raw_order.id,
                       'symbol': symbol,
                       'side': side,  # We know the side from our call
                       'type': 'market',
                       'status': 'closed',
                       'filled': float(pos.get('contracts', 0)),
                       'amount': quantity,
                       'price': float(pos.get('entryPrice', 0)),
                       'info': raw_order.info
                   }
                   logger.info(f"✅ Verified position via fetch_positions on attempt {attempt}")
                   raw_order = fetched_order
                   break

           if fetched_order:
               break
   else:
       # BINANCE and others: Use fetch_order as before
       for attempt in range(1, max_retries + 1):
           await asyncio.sleep(retry_delay)
           fetched_order = await exchange_instance.fetch_order(order_id, symbol)
           if fetched_order:
               raw_order = fetched_order
               break
   ```

**Pros:**
- ✅ Completely avoids Bybit 500 order limit issue
- ✅ Completely avoids client order ID issue
- ✅ Uses data we already have (we know side, quantity, symbol)
- ✅ fetch_positions is more reliable for Bybit V5
- ✅ Already have WebSocket confirmation at this point anyway

**Cons:**
- ⚠️ More code changes (~30 lines)
- ⚠️ Need to construct order-like dict manually
- ⚠️ Different code paths for Bybit vs Binance
- ⚠️ Relies on position existing (but we already have WebSocket confirmation)

**Risk Level:** MEDIUM (more complex changes)

**Testing Required:**
1. Test with Bybit testnet
2. Verify constructed order dict works with normalize_order
3. Test edge cases (what if position not found?)
4. Verify Binance unaffected

**Implementation Time:** 30 minutes

---

### Option C: Dual Cache (Exchange ID + Client ID)

**Approach:**
Cache orders using BOTH exchange order ID and client order ID, so lookups work with either.

**Changes Required:**

1. **File:** `core/exchange_manager.py`
   **Location:** Lines 429-431 (cache_order)

   **Before:**
   ```python
   # Cache order locally (Phase 3: Bybit 500 order limit solution)
   if self.repository:
       await self.repository.cache_order(self.name, order)
   ```

   **After:**
   ```python
   # Cache order locally (Phase 3: Bybit 500 order limit solution)
   if self.repository:
       # Cache by primary ID (CCXT id field)
       await self.repository.cache_order(self.name, order)

       # BYBIT FIX: Also cache by exchange order ID if different
       if self.name == 'bybit' and 'orderId' in order.get('info', {}):
           exchange_order_id = order['info']['orderId']
           if exchange_order_id != order['id']:
               # Cache again with exchange order ID
               order_copy = order.copy()
               order_copy['id'] = exchange_order_id
               await self.repository.cache_order(self.name, order_copy)
               logger.debug(f"Cached Bybit order with both client ID and exchange ID")
   ```

2. **File:** `core/repositories/exchange_repository.py`
   **Location:** Cache implementation (need to review)

   **Change:** Allow storing same order with multiple keys

**Pros:**
- ✅ Cache fallback will work with either ID type
- ✅ Fixes the cache miss issue
- ✅ Backward compatible

**Cons:**
- ⚠️ Still need to fix the primary issue (using wrong ID for fetch_order)
- ⚠️ More memory (storing same order twice)
- ⚠️ Cache complexity increases
- ⚠️ Doesn't solve fetch_order failure, only cache miss

**Risk Level:** MEDIUM

**Note:** This should be COMBINED with Option A or B, not used alone!

**Implementation Time:** 20 minutes

---

### Option D: Skip fetch_order if WebSocket Already Confirmed ⭐ ELEGANT

**Approach:**
If WebSocket position update was received, skip `fetch_order` entirely - we already know position exists!

**Changes Required:**

1. **File:** `core/atomic_position_manager.py`
   **Location:** Before fetch_order retry loop (line 586)

   **Add:**
   ```python
   # OPTIMIZATION: If WebSocket already confirmed position, skip fetch_order
   # We pre-register position before order creation, WebSocket updates arrive in <1ms
   # By the time we get here (500ms+ later), WebSocket has definitely seen the position
   if self.position_manager:
       # Check if WebSocket has already seen this position
       ws_position = await self.position_manager.get_position_from_ws_cache(symbol, exchange)

       if ws_position and abs(float(ws_position.get('contracts', 0)) - quantity) < 0.01:
           logger.info(
               f"✅ WebSocket already confirmed position exists "
               f"(size={ws_position.get('contracts')}), skipping fetch_order"
           )

           # Use WebSocket data to enrich minimal order response
           raw_order_dict = raw_order.__dict__ if hasattr(raw_order, '__dict__') else raw_order
           raw_order_dict['side'] = side  # We know the side from our call
           raw_order_dict['status'] = 'closed'  # Position exists = order filled
           raw_order_dict['filled'] = quantity
           raw_order_dict['price'] = float(ws_position.get('entryPrice', 0))

           # Skip fetch_order entirely
           logger.info("ℹ️  Skipping fetch_order - using WebSocket-confirmed data")
       else:
           # WebSocket didn't see it yet OR size mismatch - use fetch_order as fallback
           logger.info("ℹ️  WebSocket data unavailable, falling back to fetch_order")
           # ... existing fetch_order retry logic ...
   ```

2. **File:** `core/position_manager.py`
   **Add method:**
   ```python
   async def get_position_from_ws_cache(self, symbol: str, exchange: str) -> Optional[Dict]:
       """
       Get position data from WebSocket cache

       Returns None if not found or WebSocket not connected
       """
       # Implementation depends on how WebSocket data is stored
       # Need to check websocket handler implementation
   ```

**Pros:**
- ✅ Most elegant solution - uses data we already have
- ✅ Faster (no API call needed)
- ✅ Avoids rate limits completely
- ✅ Works for both Bybit and Binance
- ✅ WebSocket is most reliable source (instant updates)
- ✅ We already pre-register position - designed for this!

**Cons:**
- ⚠️ Requires WebSocket to be working (but we have fallback if not)
- ⚠️ Need to implement WebSocket cache access method
- ⚠️ More complex logic (but cleaner architecture)

**Risk Level:** MEDIUM (requires WebSocket integration)

**Testing Required:**
1. Verify WebSocket data is available at this point
2. Test with WebSocket disconnected (fallback to fetch_order)
3. Test edge cases (size mismatch, delayed WebSocket, etc.)
4. Verify works on both exchanges

**Implementation Time:** 45 minutes

---

## RECOMMENDATION

### Primary Solution: **Option A + Option C**

**Why:**
1. **Option A** fixes the immediate issue (wrong order ID used)
2. **Option C** ensures cache fallback works
3. Minimal code changes
4. Low risk
5. Fast to implement and test

**Implementation Order:**
1. First: Implement Option A (5-10 min)
2. Test with test script
3. Then: Add Option C (20 min)
4. Deploy and verify in production

### Future Enhancement: **Option D**

**Why:**
- More elegant long-term solution
- Better architecture (use WebSocket data)
- Avoids API limits entirely
- But requires more work to implement safely

**Timeline:**
- Short term (today): Option A + C
- Medium term (next week): Option D as enhancement

---

## TESTING PLAN

### Phase 1: Test Script Validation
```bash
cd tests/manual
python test_bybit_order_id_investigation.py
```

**Expected Results:**
- Confirm `info['orderId']` exists in Bybit response
- Confirm `info['orderId']` != `order['id']`
- Confirm `fetch_order(info['orderId'])` works
- Confirm `fetch_order(order['id'])` fails

### Phase 2: Code Implementation (Option A)
1. Make changes to `atomic_position_manager.py` lines 586-614
2. Add Bybit-specific order ID extraction
3. Verify syntax (no code execution yet)

### Phase 3: Testnet Verification
1. Use Bybit testnet to create test order
2. Verify fetch_order succeeds with exchange order ID
3. Verify normalize_order succeeds
4. Verify position created correctly

### Phase 4: Production Monitoring
1. Deploy fix
2. Monitor next wave cycle (03:48, 04:03, 04:18)
3. Watch for:
   - ✅ "Using Bybit exchange order ID from info" log
   - ✅ "Fetched bybit order on attempt 1/5" log
   - ✅ Successful position creation
   - ❌ NO "missing 'side' field" errors

### Phase 5: Verification
1. Check that ALL Bybit positions open successfully
2. Check that NO phantom positions created
3. Check that Binance positions still work
4. Monitor for 24 hours

---

## ROLLBACK PLAN

**If Option A causes issues:**

```python
# Revert changes - remove lines added
if exchange == 'bybit' and hasattr(raw_order, 'info') and 'orderId' in raw_order.info:
    order_id = raw_order.info['orderId']
    logger.info(f"✅ Using Bybit exchange order ID from info: {order_id}")
else:
    order_id = raw_order.id
```

Back to:
```python
order_id = raw_order.id
```

**Rollback time:** < 1 minute

**Risk:** MINIMAL (only 3-5 lines added, easy to revert)

---

## IMPLEMENTATION CHECKLIST

### Pre-Implementation
- [x] Root cause identified (CLIENT ORDER ID issue)
- [x] Forensic investigation completed
- [x] Test script created
- [ ] Test script executed and results analyzed
- [ ] Confirm `info['orderId']` exists in Bybit response

### Implementation
- [ ] Implement Option A changes
- [ ] Add logging for visibility
- [ ] Test with Bybit testnet
- [ ] Verify Binance unaffected
- [ ] Code review

### Deployment
- [ ] Commit changes with detailed message
- [ ] Deploy to production
- [ ] Monitor first wave cycle
- [ ] Verify success metrics

### Post-Deployment
- [ ] Monitor for 24 hours
- [ ] Document any issues
- [ ] Consider implementing Option D as enhancement

---

## SUCCESS METRICS

**Fix is successful if:**

1. ✅ NO "missing 'side' field" errors for Bybit orders
2. ✅ ALL Bybit positions open successfully (100% success rate)
3. ✅ NO phantom positions created
4. ✅ fetch_order succeeds on first attempt (no retries needed)
5. ✅ Binance positions continue to work normally
6. ✅ No new errors introduced

**Expected Logs (Bybit):**
```
INFO  - ✅ Using Bybit exchange order ID from info: 1234567890
INFO  - ✅ Fetched bybit order on attempt 1/5: id=1234567890, side=sell, status=closed, filled=920.0
INFO  - ✅ Entry order placed: 1234567890
```

**Expected Logs (Binance - unchanged):**
```
INFO  - ✅ Fetched binance order on attempt 1/5: id=314479319, side=SELL, status=FILLED
INFO  - ✅ Entry order placed: 314479319
```

---

## TIMELINE

**Immediate (Next 1 hour):**
- [ ] Run test script
- [ ] Analyze results
- [ ] Present findings to user

**Short Term (After user approval):**
- [ ] Implement Option A (10 min)
- [ ] Test with testnet (15 min)
- [ ] Deploy to production (5 min)
- [ ] Monitor first wave (15 min)

**Total Time to Fix:** ~45 minutes after approval

---

## ALTERNATIVE: If Test Script Shows Different Behavior

**If `info['orderId']` doesn't exist:**
- Fall back to Option B (fetch_positions)
- OR Option D (WebSocket data)

**If `info['orderId']` == `order['id']`:**
- Root cause is different than expected
- Need deeper investigation
- May need to check CCXT version or Bybit API changes

**If test script shows 'side' field EXISTS:**
- Problem may be environment-specific
- Check production CCXT version vs test environment
- May be timing-related (minimal response becomes full after delay)

---

END OF FIX PLAN

**Next Step:** Execute `test_bybit_order_id_investigation.py` and analyze results before proceeding with implementation.
