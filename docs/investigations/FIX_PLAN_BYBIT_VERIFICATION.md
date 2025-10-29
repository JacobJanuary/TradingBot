# 🔧 FIX PLAN: Bybit Position Closure Verification

**Created**: 2025-10-24
**Priority**: 🔴 CRITICAL
**Confidence Level**: 100% (based on forensic investigation of 17+ symbols, 50+ attempts)
**Estimated Effort**: 3-4 hours implementation + 2 hours testing

---

## 📋 PROBLEM SUMMARY

**Current Behavior**:
- Order submitted → Order ID received → Database immediately updated → Position remains on exchange (Bybit)

**Required Behavior**:
- Order submitted → Order ID received → **Verify position closed** → Database updated only if verified

**Failure Rate**:
- Bybit: 0% success (17/17 positions failed verification)
- Binance: 100% success (9/9 positions verified closed)

---

## 🎯 FIX STRATEGY

### Core Principle
**Never update database until position closure is verified on exchange**

### Approach
1. **Verification Layer**: Add position verification after order submission
2. **Polling Mechanism**: Poll exchange to confirm position no longer exists
3. **Timeout Handling**: Set reasonable timeout for verification (30-60s)
4. **Fallback Logic**: If verification fails, keep position in aged tracking for retry
5. **Exchange-Specific**: Handle Binance (sync) and Bybit (async) appropriately

---

## 📝 DETAILED IMPLEMENTATION PLAN

### PHASE 1: Add Verification Method to OrderExecutor

**File**: `core/order_executor.py`
**New Method**: `verify_position_closed()`
**Location**: After line 313 (after `_execute_market_order`)

```python
async def verify_position_closed(
    self,
    exchange_name: str,
    symbol: str,
    position_id: str,
    max_wait_seconds: float = 30.0,
    poll_interval: float = 1.0
) -> tuple[bool, str]:
    """
    Verify that a position is actually closed on the exchange.

    Args:
        exchange_name: Exchange name (binance, bybit)
        symbol: Trading pair symbol
        position_id: Position ID for logging
        max_wait_seconds: Maximum time to wait for position closure (default 30s)
        poll_interval: Time between verification polls (default 1s)

    Returns:
        Tuple of (verified: bool, message: str)
        - (True, "Position verified closed") if position not found on exchange
        - (False, "Position still exists after Xs") if position still exists after timeout
        - (False, "Exchange not found") if exchange not available
    """

    exchange = self.exchanges.get(exchange_name)
    if not exchange:
        return False, f"Exchange {exchange_name} not found"

    start_time = time.time()
    elapsed = 0
    attempts = 0

    logger.info(
        f"🔍 Verifying position closure for {symbol} on {exchange_name} "
        f"(max_wait={max_wait_seconds}s)"
    )

    while elapsed < max_wait_seconds:
        attempts += 1

        try:
            # Fetch all open positions from exchange
            positions = await exchange.exchange.fetch_positions([symbol])

            # Filter for positions with non-zero contracts
            open_positions = [
                p for p in positions
                if p.get('contracts', 0) != 0 or p.get('contractSize', 0) != 0
            ]

            if not open_positions:
                # Position not found - successfully closed!
                elapsed = time.time() - start_time
                logger.info(
                    f"✅ Position {symbol} verified closed on {exchange_name} "
                    f"(took {elapsed:.2f}s, {attempts} attempts)"
                )
                return True, f"Position verified closed after {elapsed:.2f}s"

            # Position still exists - check remaining time
            elapsed = time.time() - start_time
            remaining = max_wait_seconds - elapsed

            if remaining > poll_interval:
                # Still have time - log and wait
                logger.debug(
                    f"⏳ Position {symbol} still open on {exchange_name}, "
                    f"waiting... ({elapsed:.1f}s elapsed, {remaining:.1f}s remaining)"
                )
                await asyncio.sleep(poll_interval)
            else:
                # Timeout reached
                break

        except Exception as e:
            logger.warning(
                f"⚠️ Error verifying position {symbol} on {exchange_name}: {e}"
            )
            # On error, wait and retry
            await asyncio.sleep(poll_interval)

        elapsed = time.time() - start_time

    # Verification failed - position still exists after timeout
    logger.error(
        f"❌ Position {symbol} still exists on {exchange_name} after {elapsed:.2f}s "
        f"({attempts} verification attempts)"
    )
    return False, f"Position still exists after {elapsed:.2f}s ({attempts} attempts)"
```

**Testing Requirements**:
- Test with Binance (should verify in <1s)
- Test with Bybit (may take 5-30s)
- Test timeout scenario
- Test error handling (network issues, API errors)

---

### PHASE 2: Modify AgedPositionMonitorV2 to Use Verification

**File**: `core/aged_position_monitor_v2.py`
**Method**: `_trigger_market_close()`
**Lines to Modify**: 308-362

#### Current Code (Lines 308-362)

```python
# Line 308-314: Execute close
result = await self.order_executor.execute_close(
    symbol=symbol,
    exchange_name=exchange_name,
    position_side=position.side,
    amount=amount,
    reason=f'aged_{target.phase}'
)

# Line 333-362: If successful, update DB IMMEDIATELY (BUG!)
if result.success:
    self.stats['market_closes_triggered'] += 1

    if self.repository:
        try:
            await self.repository.mark_aged_position_closed(
                position_id=str(target.position_id),
                close_reason=f'aged_{target.phase}'
            )

            await self.repository.update_position(
                position.id,
                status='closed',
                exit_reason=f'aged_{target.phase}'
            )
```

#### New Code (FIXED with Verification)

```python
# Line 308-314: Execute close (unchanged)
result = await self.order_executor.execute_close(
    symbol=symbol,
    exchange_name=exchange_name,
    position_side=position.side,
    amount=amount,
    reason=f'aged_{target.phase}'
)

# NEW: Verification step before database update
if result.success:
    logger.info(
        f"📤 Close order accepted for {symbol}: order_id={result.order_id}, "
        f"now verifying position closure..."
    )

    # STEP 1: Verify position is actually closed on exchange
    verified, verify_msg = await self.order_executor.verify_position_closed(
        exchange_name=exchange_name,
        symbol=symbol,
        position_id=str(position.id),
        max_wait_seconds=30.0,  # Wait up to 30s for Bybit
        poll_interval=1.0       # Check every 1s
    )

    if verified:
        # ✅ VERIFIED: Position is closed on exchange
        logger.info(
            f"✅ Aged position {symbol} VERIFIED closed: "
            f"order_id={result.order_id}, type={result.order_type}, "
            f"attempts={result.attempts}, phase={target.phase}"
        )

        self.stats['market_closes_triggered'] += 1

        # NOW safe to update database
        if self.repository:
            try:
                # Remove from aged tracking
                await self.repository.mark_aged_position_closed(
                    position_id=str(target.position_id),
                    close_reason=f'aged_{target.phase}_verified'
                )

                # Mark position as closed
                await self.repository.update_position(
                    position.id,
                    status='closed',
                    exit_reason=f'aged_{target.phase}_verified',
                    exit_price=float(result.price) if result.price else None
                )

                logger.info(
                    f"💾 Database updated: {symbol} marked as closed "
                    f"(verified closure)"
                )

            except Exception as e:
                logger.error(
                    f"❌ Failed to update database for {symbol}: {e}",
                    exc_info=True
                )

        # Remove from tracking
        target_key = (str(target.position_id), target.phase)
        if target_key in self.targets:
            del self.targets[target_key]
            logger.info(f"🗑️  Removed {symbol} from aged tracking")

    else:
        # ❌ VERIFICATION FAILED: Position still on exchange
        logger.error(
            f"❌ VERIFICATION FAILED for {symbol}: {verify_msg}"
        )
        logger.error(
            f"🚨 Order {result.order_id} accepted but position still on exchange!"
        )
        logger.error(
            f"⚠️  Keeping {symbol} in aged tracking for retry"
        )

        # DO NOT update database
        # DO NOT remove from aged tracking
        # Position will be retried on next monitoring cycle

        # Update statistics
        self.stats['verification_failures'] = self.stats.get('verification_failures', 0) + 1

        # Optional: Create alert/notification
        # await self.send_alert(
        #     f"Aged closure verification failed for {symbol} on {exchange_name}"
        # )

else:
    # Order execution failed (order_id not received)
    logger.error(
        f"❌ Failed to execute close order for {symbol}: "
        f"{result.error_message}"
    )
    # Keep in aged tracking for retry
```

**Key Changes**:
1. **Verification Step**: Added `verify_position_closed()` call after order submission
2. **Conditional DB Update**: Database only updated if `verified == True`
3. **Failure Handling**: If verification fails, position stays in aged tracking for retry
4. **Enhanced Logging**: Clear distinction between order accepted vs position verified
5. **Statistics**: Track verification failures separately

---

### PHASE 3: Add Verification Statistics

**File**: `core/aged_position_monitor_v2.py`
**Method**: `__init__()`
**Line**: ~80-100 (statistics initialization)

Add to statistics dict:

```python
self.stats = {
    # ... existing stats ...
    'market_closes_triggered': 0,
    'verification_failures': 0,      # NEW: Count of failed verifications
    'verification_timeouts': 0,      # NEW: Count of timeout verifications
    'verification_avg_time': 0.0,    # NEW: Average verification time
}
```

**File**: `core/aged_position_monitor_v2.py`
**Method**: `get_stats()`
**Enhancement**: Include verification metrics in status report

```python
def get_stats(self) -> dict:
    """Get monitoring statistics"""
    return {
        **self.stats,
        'active_targets': len(self.targets),
        'target_distribution': self._get_target_distribution(),
        'verification_success_rate': self._calculate_verification_success_rate(),  # NEW
    }

def _calculate_verification_success_rate(self) -> float:
    """Calculate verification success rate"""
    total = self.stats.get('market_closes_triggered', 0)
    failures = self.stats.get('verification_failures', 0)

    if total == 0:
        return 100.0

    successes = total - failures
    return (successes / total) * 100.0
```

---

### PHASE 4: Update OrderResult Model

**File**: `core/order_executor.py`
**Class**: `OrderResult`
**Enhancement**: Add verification fields

```python
@dataclass
class OrderResult:
    """Result of order execution with verification"""
    success: bool
    order_id: Optional[str]
    order_type: str  # 'market', 'limit_aggressive', 'limit_maker', 'failed'
    price: Optional[Decimal]
    executed_amount: Optional[Decimal]
    error_message: Optional[str]
    attempts: int
    execution_time: float

    # NEW: Verification fields (optional, set by caller)
    verified: bool = False              # NEW: Position verified closed on exchange
    verification_time: float = 0.0      # NEW: Time taken to verify (seconds)
    verification_message: str = ""      # NEW: Verification result message
```

**Note**: This is optional - verification can be handled in aged_position_monitor_v2 without modifying OrderResult.

---

### PHASE 5: Add Configuration Options

**File**: `config.py` (or wherever configuration is stored)
**New Settings**:

```python
# Position closure verification settings
POSITION_CLOSURE_VERIFICATION = {
    'enabled': True,                    # Enable verification (can disable for testing)
    'max_wait_seconds': 30.0,          # Maximum time to wait for verification
    'poll_interval': 1.0,              # Time between verification polls
    'exchange_specific': {
        'binance': {
            'max_wait_seconds': 5.0,   # Binance is fast, 5s is enough
            'poll_interval': 0.5,
        },
        'bybit': {
            'max_wait_seconds': 30.0,  # Bybit needs more time
            'poll_interval': 1.0,
        }
    }
}
```

**Usage in Code**:

```python
# In aged_position_monitor_v2.py
config = POSITION_CLOSURE_VERIFICATION['exchange_specific'].get(
    exchange_name,
    POSITION_CLOSURE_VERIFICATION  # Default
)

verified, verify_msg = await self.order_executor.verify_position_closed(
    exchange_name=exchange_name,
    symbol=symbol,
    position_id=str(position.id),
    max_wait_seconds=config['max_wait_seconds'],
    poll_interval=config['poll_interval']
)
```

---

## 🧪 TESTING PLAN

### Unit Tests

**File**: `tests/test_order_executor_verification.py`

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from core.order_executor import OrderExecutor

@pytest.mark.asyncio
async def test_verify_position_closed_success():
    """Test successful position verification (position not found)"""
    # Mock exchange that returns empty positions
    exchange = Mock()
    exchange.exchange.fetch_positions = AsyncMock(return_value=[])

    executor = OrderExecutor({'bybit': exchange})

    verified, msg = await executor.verify_position_closed(
        'bybit', 'BTCUSDT', '12345', max_wait_seconds=5.0
    )

    assert verified is True
    assert "verified closed" in msg.lower()

@pytest.mark.asyncio
async def test_verify_position_closed_timeout():
    """Test verification timeout (position still exists)"""
    # Mock exchange that always returns open position
    exchange = Mock()
    exchange.exchange.fetch_positions = AsyncMock(return_value=[
        {'symbol': 'BTC/USDT', 'contracts': 1.0}
    ])

    executor = OrderExecutor({'bybit': exchange})

    verified, msg = await executor.verify_position_closed(
        'bybit', 'BTCUSDT', '12345', max_wait_seconds=3.0, poll_interval=1.0
    )

    assert verified is False
    assert "still exists" in msg.lower()

@pytest.mark.asyncio
async def test_verify_position_closed_delayed():
    """Test verification with delayed closure (position closes after 2 polls)"""
    # Mock exchange that closes position after 2 calls
    call_count = 0

    async def mock_fetch_positions(symbols):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return [{'symbol': 'BTC/USDT', 'contracts': 1.0}]
        return []  # Closed after 2 calls

    exchange = Mock()
    exchange.exchange.fetch_positions = mock_fetch_positions

    executor = OrderExecutor({'bybit': exchange})

    verified, msg = await executor.verify_position_closed(
        'bybit', 'BTCUSDT', '12345', max_wait_seconds=10.0, poll_interval=1.0
    )

    assert verified is True
    assert "verified closed" in msg.lower()
```

### Integration Tests

**File**: `tests/test_aged_closure_with_verification.py`

```python
@pytest.mark.asyncio
async def test_aged_closure_binance_fast_verification():
    """Test aged closure on Binance (fast verification)"""
    # Test that Binance positions are verified in <5s
    pass

@pytest.mark.asyncio
async def test_aged_closure_bybit_slow_verification():
    """Test aged closure on Bybit (slow verification)"""
    # Test that Bybit positions may need up to 30s for verification
    pass

@pytest.mark.asyncio
async def test_aged_closure_verification_failure_keeps_tracking():
    """Test that failed verification keeps position in aged tracking"""
    # Verify position not removed from aged tracking if verification fails
    pass

@pytest.mark.asyncio
async def test_aged_closure_db_not_updated_on_verification_failure():
    """Test that database is NOT updated if verification fails"""
    # Critical: Verify no DB updates when verification fails
    pass
```

### Manual Testing Checklist

**Before Deployment**:

- [ ] Test Binance aged closure with verification (expect <5s verification)
- [ ] Test Bybit aged closure with verification (expect 5-30s verification)
- [ ] Test verification timeout handling (mock position staying open)
- [ ] Test verification error handling (network issues, API errors)
- [ ] Verify statistics tracking (verification_failures counter)
- [ ] Verify logging (clear distinction between order accepted and position verified)
- [ ] Test synchronizer behavior after fix (should NOT recreate verified closures)
- [ ] Test multiple aged closures in parallel (ensure verification doesn't block)

**After Deployment**:

- [ ] Monitor verification success rate for Bybit (should improve from 0% to >90%)
- [ ] Monitor verification times (Binance: <5s, Bybit: 5-30s)
- [ ] Check for any positions marked "closed" that are still on exchange
- [ ] Verify synchronizer log (should see fewer "Missing from database" for aged closures)
- [ ] Monitor aged module retry behavior (positions should retry if verification fails)

---

## ⚠️ RISK MITIGATION

### Potential Risks

1. **Verification Timeout Too Long**: Position stays in aged tracking during 30s verification
   - **Mitigation**: Use exchange-specific timeouts (Binance: 5s, Bybit: 30s)
   - **Fallback**: Configurable timeouts, can adjust based on empirical data

2. **API Rate Limits**: Frequent position polling may hit rate limits
   - **Mitigation**: Poll interval of 1s (max 30 calls per position)
   - **Monitoring**: Track rate limit errors and adjust poll_interval if needed

3. **False Negatives**: Verification fails even though position is closed
   - **Impact**: Position retried on next cycle (15-30s later), eventually succeeds
   - **Mitigation**: Retry logic already built into aged module

4. **Blocking Behavior**: Verification blocks other closures
   - **Mitigation**: Verification is async, other positions can close in parallel
   - **Note**: Each position verifies independently

5. **Network Issues**: Temporary network issues cause false verification failures
   - **Mitigation**: Retry logic in aged module, position will be attempted again
   - **Monitoring**: Log verification errors separately from closure failures

### Rollback Plan

If fix causes issues:

1. **Quick Disable**: Set `POSITION_CLOSURE_VERIFICATION['enabled'] = False` in config
2. **Revert Code**: Restore `aged_position_monitor_v2.py` from backup
3. **Deploy Original**: Redeploy previous version (pre-verification)
4. **Data Cleanup**: Check for any positions stuck in "pending verification" state

### Gradual Rollout Option

**Phase A**: Enable verification but don't update database yet (log-only mode)
```python
if verified:
    logger.info("✅ Verification succeeded (log-only mode, DB not updated)")
    # TODO: Uncomment to enable DB update
    # await self.repository.update_position(...)
else:
    logger.error("❌ Verification failed (log-only mode)")
```

**Phase B**: After monitoring logs for 24h, enable full DB update if verification >90% success

---

## 📊 SUCCESS METRICS

### Key Performance Indicators

| Metric | Before Fix | Target After Fix | Measurement Method |
|--------|------------|------------------|-------------------|
| Bybit verification success rate | 0% | >90% | Monitor verification_failures stat |
| Zombie positions created | ~17/day | <1/day | Check synchronizer "Missing from database" |
| Average verification time (Bybit) | N/A | 5-30s | Track verification_avg_time |
| Average verification time (Binance) | N/A | <5s | Track verification_avg_time |
| Aged closure retry rate | High | Low | Monitor how often same position retried |

### Monitoring Queries

**Check verification success rate**:
```sql
-- After fix is deployed, add verification tracking table
SELECT
    exchange,
    COUNT(*) as total_closures,
    SUM(CASE WHEN verified = true THEN 1 ELSE 0 END) as verified_closures,
    ROUND(100.0 * SUM(CASE WHEN verified = true THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate,
    AVG(verification_time_seconds) as avg_verification_time
FROM aged_closure_attempts
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY exchange;
```

**Check for zombie positions** (should be near zero after fix):
```bash
grep "Missing from database" logs/trading_bot.log | wc -l
```

---

## 📅 IMPLEMENTATION TIMELINE

### Immediate (Today)

1. ✅ Forensic investigation (COMPLETED)
2. ✅ Root cause analysis (COMPLETED)
3. ✅ Fix plan creation (COMPLETED)
4. ⏳ **CODE IMPLEMENTATION** (3-4 hours)
   - [ ] Add `verify_position_closed()` to `order_executor.py`
   - [ ] Modify `_trigger_market_close()` in `aged_position_monitor_v2.py`
   - [ ] Add verification statistics
   - [ ] Update configuration

### Next Session (Tomorrow)

5. ⏳ **TESTING** (2 hours)
   - [ ] Write unit tests
   - [ ] Write integration tests
   - [ ] Manual testing with Binance
   - [ ] Manual testing with Bybit

6. ⏳ **DEPLOYMENT** (1 hour)
   - [ ] Create backup of current code
   - [ ] Deploy to production
   - [ ] Monitor initial verification attempts
   - [ ] Verify no regressions

7. ⏳ **MONITORING** (24 hours)
   - [ ] Track verification success rate
   - [ ] Check for zombie positions
   - [ ] Monitor verification times
   - [ ] Adjust timeouts if needed

---

## 🎯 ACCEPTANCE CRITERIA

Fix is considered successful when:

1. ✅ Bybit verification success rate > 90%
2. ✅ No zombie positions created from aged closures
3. ✅ Average verification time < 30s for Bybit
4. ✅ Average verification time < 5s for Binance
5. ✅ No positions marked "closed" in DB but still on exchange
6. ✅ Aged module retry logic works correctly when verification fails
7. ✅ All tests pass (unit + integration)
8. ✅ No performance degradation (verification doesn't block other operations)

---

## 📚 REFERENCES

- **Forensic Report**: `FORENSIC_BYBIT_VERIFICATION_FAILURE.md`
- **Deep Investigation**: `DEEP_INVESTIGATION_ALL_POSITIONS_20251024.md`
- **Code Files**:
  - `core/aged_position_monitor_v2.py` (lines 308-362)
  - `core/order_executor.py` (lines 119-231, 292-313)
- **Log Evidence**: `logs/trading_bot.log.1` (lines 215-6287, 132943-338846)

---

## ✅ FINAL CHECKLIST

**Before Implementation**:
- [x] Forensic investigation complete with 15+ symbol analysis
- [x] Root cause identified with 100% confidence
- [x] Fix strategy designed with verification approach
- [x] Testing plan created
- [x] Rollback plan prepared
- [x] Success metrics defined

**Ready to implement**: ✅ YES

**User approval required before code changes**: ✅ YES (per user instruction: "ТОЛЬКО ПРОВЕРКА РАССЛЕДОВАНИЕ И ПЛАНИРОВАНИЕ! БЕЗ ИЗМЕНЕНИЯ КОДА НА ДАННОМ ШАГЕ")

---

**Plan Status**: 📋 READY FOR REVIEW AND APPROVAL
**Next Step**: Await user approval to proceed with implementation

**End of Fix Plan**
