# BYBIT VERIFICATION SOURCE 1 FIX - IMPLEMENTATION PLAN
**Date**: 2025-10-29 06:25
**Status**: READY TO IMPLEMENT
**Priority**: CRITICAL
**Estimated Time**: 5 minutes

---

## PLAN OVERVIEW

**Problem**: SOURCE 1 (fetch_order) fails for Bybit UUID order IDs with "500 order limit" error, preventing position verification

**Solution**: Skip SOURCE 1 for Bybit, rely on SOURCE 2 (WebSocket) and SOURCE 3 (REST API)

**Files to Change**: 1 file
**Lines to Change**: 3 lines
**Tests Required**: Integration test (next wave cycle)

---

## PHASE 1: CODE IMPLEMENTATION

### File 1: core/atomic_position_manager.py

**Location**: Lines 256-313 (SOURCE 1 block in `_verify_position_exists_multi_source`)

**Change Type**: Add conditional skip for Bybit

#### BEFORE (Current Code):
```python
# ============================================================
# SOURCE 1 (PRIORITY 1): Order filled status
# САМЫЙ НАДЕЖНЫЙ - ордер УЖЕ ИСПОЛНЕН в exchange
# ============================================================
if not sources_tried['order_status']:
    try:
        # DIAGNOSTIC PATCH 2025-10-29: Changed to WARNING for visibility
        logger.warning(f"🔍 [SOURCE 1/3] Checking order status for {entry_order.id}")

        # Refetch order to get latest status
        # Small delay first only on first attempt
        if attempt == 1:
            await asyncio.sleep(0.5)

        # DIAGNOSTIC PATCH 2025-10-29: Log BEFORE fetch_order call
        logger.warning(f"🔄 [SOURCE 1] About to call fetch_order(id={entry_order.id}, symbol={symbol})")

        order_status = await exchange_instance.fetch_order(entry_order.id, symbol)
```

#### AFTER (Fixed Code):
```python
# ============================================================
# SOURCE 1 (PRIORITY 1): Order filled status
# САМЫЙ НАДЕЖНЫЙ - ордер УЖЕ ИСПОЛНЕН в exchange
# SKIP for Bybit: UUID order IDs cannot be queried via fetch_order (API v5 limitation)
# ============================================================
if exchange == 'bybit':
    logger.info(f"ℹ️  [SOURCE 1] SKIPPED for Bybit (UUID order IDs cannot be queried, API v5 limitation)")
    sources_tried['order_status'] = True
elif not sources_tried['order_status']:
    try:
        # DIAGNOSTIC PATCH 2025-10-29: Changed to WARNING for visibility
        logger.warning(f"🔍 [SOURCE 1/3] Checking order status for {entry_order.id}")

        # Refetch order to get latest status
        # Small delay first only on first attempt
        if attempt == 1:
            await asyncio.sleep(0.5)

        # DIAGNOSTIC PATCH 2025-10-29: Log BEFORE fetch_order call
        logger.warning(f"🔄 [SOURCE 1] About to call fetch_order(id={entry_order.id}, symbol={symbol})")

        order_status = await exchange_instance.fetch_order(entry_order.id, symbol)
```

**Lines Changed**:
- Line 256: Change `if not sources_tried['order_status']:` to add Bybit check
- Add 3 new lines (257-259)

**Justification**:
1. ✅ Bybit UUID order IDs NEVER work with fetch_order (proven in logs)
2. ✅ Skipping SOURCE 1 allows SOURCE 2/3 to run immediately
3. ✅ WebSocket (SOURCE 2) already sees positions (proven: "Position update: 1000NEIROCTOUSDT size=31.0")
4. ✅ REST API (SOURCE 3) uses fetch_positions with symbol conversion (proven to work)
5. ✅ NO impact on Binance (still uses SOURCE 1)

---

## PHASE 2: CODE REVIEW (BEFORE COMMIT)

### Checklist:

- [ ] **Logic Review**: Bybit check is correct (`exchange == 'bybit'`)
- [ ] **Side Effects**: Verify no impact on Binance code path
- [ ] **Exception Handling**: Unchanged (SOURCE 1 exception handling still works for Binance)
- [ ] **SOURCE 2/3**: Verify SOURCE 2 and SOURCE 3 code unchanged
- [ ] **Logging**: Info level log added (visible in production)
- [ ] **Indentation**: Python indentation is correct
- [ ] **Syntax**: Python syntax valid (test with `python -m py_compile`)

### Manual Code Inspection:

**Check 1**: Verify exchange variable available in scope
```python
# From method signature (line 192):
async def _verify_position_exists_multi_source(
    self,
    exchange_instance,
    symbol: str,
    exchange: str,  # ← YES, exchange is available
    entry_order: Any,
    expected_quantity: float,
    timeout: float = 10.0
) -> bool:
```
✅ PASS - `exchange` parameter available

**Check 2**: Verify Binance path unchanged
```python
elif not sources_tried['order_status']:  # ← Binance enters here
    try:
        logger.warning(f"🔍 [SOURCE 1/3] Checking order status...")
        order_status = await exchange_instance.fetch_order(entry_order.id, symbol)
        # ... rest of logic UNCHANGED
```
✅ PASS - Binance logic unchanged

**Check 3**: Verify SOURCE 2 still runs
```python
# SOURCE 2 (PRIORITY 2): WebSocket position updates
if self.position_manager and hasattr(...) and not sources_tried['websocket']:
    # ... WebSocket check logic UNCHANGED
```
✅ PASS - SOURCE 2 unchanged

**Check 4**: Verify SOURCE 3 still runs
```python
# SOURCE 3 (PRIORITY 3): REST API fetch_positions
if not sources_tried['rest_api'] or attempt % 3 == 0:
    # ... REST API logic UNCHANGED
```
✅ PASS - SOURCE 3 unchanged

---

## PHASE 3: SYNTAX VALIDATION

### Command:
```bash
python -m py_compile core/atomic_position_manager.py
```

### Expected Output:
```
(no output = success)
```

### If Syntax Error:
- Review indentation (Python is whitespace-sensitive!)
- Check for missing colons
- Verify parentheses balanced

---

## PHASE 4: GIT COMMIT

### Commit Message:
```
fix(bybit): skip SOURCE 1 verification for UUID order IDs (API v5 limitation)

ROOT CAUSE:
- Bybit API v5 returns UUID client order IDs
- fetch_order endpoint has 500 order limit
- UUID orders cannot be queried → "500 order limit" error
- SOURCE 1 fails → retry loop → timeout → rollback

SOLUTION:
- Skip SOURCE 1 (fetch_order) for Bybit
- Use SOURCE 2 (WebSocket) - already sees positions
- Fallback to SOURCE 3 (REST API fetch_positions) - proven to work

IMPACT:
- Bybit positions now verified via WebSocket/REST API
- NO more "500 order limit" errors
- NO more verification timeout → rollback
- NO more phantom positions
- Binance unchanged (still uses SOURCE 1)

EVIDENCE:
- Production logs show WebSocket sees position: "Position update: 1000NEIROCTOUSDT size=31.0"
- Entry block already uses fetch_positions for Bybit (working)
- SOURCE 3 uses fetch_positions with symbol conversion (working)

FILES CHANGED:
- core/atomic_position_manager.py (3 lines added)

TESTING:
- Integration test: Next wave cycle
- Monitor for "[SOURCE 1] SKIPPED for Bybit" logs
- Verify "[SOURCE 2] WebSocket CONFIRMED" appears
- Verify stop-loss placed for Bybit positions

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Commands:
```bash
git add core/atomic_position_manager.py
git commit -m "$(cat <<'EOF'
fix(bybit): skip SOURCE 1 verification for UUID order IDs (API v5 limitation)

ROOT CAUSE:
- Bybit API v5 returns UUID client order IDs
- fetch_order endpoint has 500 order limit
- UUID orders cannot be queried → "500 order limit" error
- SOURCE 1 fails → retry loop → timeout → rollback

SOLUTION:
- Skip SOURCE 1 (fetch_order) for Bybit
- Use SOURCE 2 (WebSocket) - already sees positions
- Fallback to SOURCE 3 (REST API fetch_positions) - proven to work

IMPACT:
- Bybit positions now verified via WebSocket/REST API
- NO more "500 order limit" errors
- NO more verification timeout → rollback
- NO more phantom positions
- Binance unchanged (still uses SOURCE 1)

EVIDENCE:
- Production logs show WebSocket sees position: "Position update: 1000NEIROCTOUSDT size=31.0"
- Entry block already uses fetch_positions for Bybit (working)
- SOURCE 3 uses fetch_positions with symbol conversion (working)

FILES CHANGED:
- core/atomic_position_manager.py (3 lines added)

TESTING:
- Integration test: Next wave cycle
- Monitor for "[SOURCE 1] SKIPPED for Bybit" logs
- Verify "[SOURCE 2] WebSocket CONFIRMED" appears
- Verify stop-loss placed for Bybit positions

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## PHASE 5: INTEGRATION TESTING

### Test Environment: Production (Next Wave Cycle)

### Expected Wave Times:
- 06:18
- 06:33
- 06:48
- 07:03
- etc (every 15 minutes)

### Monitoring Commands:
```bash
# Monitor logs in real-time
tail -f logs/bot.log | grep -E "(SKIPPED|SOURCE|verified|stop-loss|ACTIVE)"

# Check for Bybit positions
grep "bybit" logs/bot.log | grep -E "(Opening position|Position verified|stop-loss placed)"

# Check for errors
grep -E "(500 order limit|verification timeout|rollback)" logs/bot.log
```

### Success Criteria:

**For EACH Bybit Position**:
```log
✅ Opening position ATOMICALLY: DBRUSDT SELL 170.0
✅ fetch_positions returned 1 positions
✅ Fetched bybit position on attempt 1/5
✅ Position record created: ID=XXXX
✅ Verifying position exists for DBRUSDT...
✅ [SOURCE 1] SKIPPED for Bybit (UUID order IDs limitation)  ← NEW LOG!
✅ [SOURCE 2] WebSocket CONFIRMED position exists!  ← OR THIS
✅ Position verified for DBRUSDT
✅ Placing stop-loss for DBRUSDT at 0.03500
✅ Stop-loss placed successfully
✅ Position DBRUSDT is ACTIVE with protection
```

**NO errors like**:
```log
❌ 500 order limit reached  ← SHOULD NOT APPEAR
❌ verification timeout     ← SHOULD NOT APPEAR
❌ rollback                 ← SHOULD NOT APPEAR
```

### If Test FAILS:

**Scenario 1**: Still seeing "500 order limit" errors
- **Diagnosis**: Fix not applied (code not deployed)
- **Action**: Verify bot restarted, check git log for commit

**Scenario 2**: "[SOURCE 1] SKIPPED" appears but verification still fails
- **Diagnosis**: SOURCE 2 (WebSocket) and SOURCE 3 (REST API) both failing
- **Action**: Check WebSocket connection, check fetch_positions logs

**Scenario 3**: Verification timeout
- **Diagnosis**: All 3 sources failing
- **Action**: Deep investigation of SOURCE 2 and SOURCE 3 failures

---

## PHASE 6: VERIFICATION (24 HOURS)

### Metrics to Check:

1. **Bybit Position Success Rate**:
   ```bash
   # Count Bybit positions opened
   grep "Opening position ATOMICALLY" logs/bot.log | grep "bybit" | wc -l

   # Count Bybit positions with stop-loss
   grep "Position.*is ACTIVE with protection" logs/bot.log | grep -B 10 "bybit" | wc -l

   # Should be EQUAL
   ```

2. **NO "500 order limit" Errors**:
   ```bash
   grep "500 order limit" logs/bot.log
   # Should return NO results
   ```

3. **NO Verification Timeouts**:
   ```bash
   grep "verification.*timeout" logs/bot.log
   # Should return NO results for Bybit
   ```

4. **NO Rollbacks**:
   ```bash
   grep "rollback" logs/bot.log | grep "bybit"
   # Should return NO results
   ```

5. **Binance Still Works**:
   ```bash
   grep "[SOURCE 1].*Order status CONFIRMED" logs/bot.log | grep "binance"
   # Should show Binance using SOURCE 1 successfully
   ```

---

## ROLLBACK PLAN

**If Fix Doesn't Work**:

### Step 1: Revert Commit
```bash
git revert HEAD
git push
```

### Step 2: Restart Bot
```bash
# Stop bot
pkill -f bot.py

# Start bot
python bot.py &
```

### Step 3: Verify Rollback
```bash
tail -f logs/bot.log
# Should see old behavior (no SKIPPED logs)
```

**Rollback Time**: < 2 minutes
**Risk**: Returns to broken state (but no worse than before)

---

## RISK ANALYSIS

### Risks:

1. **Risk**: Bybit SOURCE 2 (WebSocket) not available
   - **Mitigation**: SOURCE 3 (REST API) fallback
   - **Probability**: LOW (WebSocket proven working in logs)

2. **Risk**: Bybit SOURCE 3 (REST API) fails
   - **Mitigation**: Same timeout behavior as before
   - **Probability**: VERY LOW (fetch_positions proven working)

3. **Risk**: Binance affected
   - **Mitigation**: Conditional check only affects Bybit
   - **Probability**: NONE (Binance uses elif branch)

4. **Risk**: Syntax error in code
   - **Mitigation**: py_compile validation before commit
   - **Probability**: LOW (simple 3-line change)

### Benefits:

1. ✅ NO more "500 order limit" errors
2. ✅ NO more verification timeout → rollback
3. ✅ NO more phantom positions without stop-loss
4. ✅ Bybit positions verified via WebSocket (proven working)
5. ✅ Fallback to REST API (proven working)
6. ✅ Binance unchanged
7. ✅ MINIMAL code change (3 lines)

**Risk/Benefit Ratio**: EXCELLENT

---

## SUCCESS METRICS SUMMARY

| Metric | Target | How to Verify |
|--------|--------|---------------|
| NO "500 order limit" errors | 0 | `grep "500 order limit" logs/bot.log` |
| Bybit verification success | 100% | Check logs for "Position verified" |
| Bybit SL placement | 100% | Check logs for "Stop-loss placed" |
| NO rollbacks | 0 | `grep rollback logs/bot.log \| grep bybit` |
| Binance unchanged | 100% | Check SOURCE 1 logs for Binance |
| "[SOURCE 1] SKIPPED" appears | 100% | Check logs for Bybit positions |

---

## IMPLEMENTATION STEPS SUMMARY

1. [ ] **Phase 1**: Implement code change (3 lines in atomic_position_manager.py)
2. [ ] **Phase 2**: Code review (6 checks)
3. [ ] **Phase 3**: Syntax validation (`python -m py_compile`)
4. [ ] **Phase 4**: Git commit with detailed message
5. [ ] **Phase 5**: Integration test (next wave cycle)
6. [ ] **Phase 6**: 24h monitoring

**Estimated Total Time**: 10 minutes implementation + 24h monitoring

---

## CONFIDENCE LEVEL

**95%** - Solution will work because:
1. ✅ WebSocket PROVEN to see positions (production logs)
2. ✅ REST API fetch_positions PROVEN to work (entry block)
3. ✅ Symbol conversion PROVEN to work (PRIMARY FIX)
4. ✅ SOURCE 1 NEVER works for Bybit UUID (root cause confirmed)
5. ✅ Minimal code change (low risk of regression)
6. ✅ Binance path unchanged (no risk to Binance)

---

## NEXT STEPS

1. Get user approval
2. Implement code change
3. Review code 3 times
4. Validate syntax
5. Commit to git
6. Monitor next wave cycle
7. Verify success metrics
8. Document outcome

---

**STATUS**: ✅ PLAN READY
**READY TO IMPLEMENT**: ✅ YES
**USER APPROVAL**: ⏳ PENDING

---

END OF IMPLEMENTATION PLAN
