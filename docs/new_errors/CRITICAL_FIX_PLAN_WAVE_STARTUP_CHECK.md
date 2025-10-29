# 🔴 CRITICAL FIX PLAN: Wave Processing Startup Check

**Priority:** 🔴 P0 - IMMEDIATE (BLOCKS TRADING)
**File:** `core/signal_processor_websocket.py`
**Lines:** 180-250 (approximately)
**Estimated Time:** 10 minutes
**Risk:** LOW (adds startup check, doesn't change existing logic)

---

## 📋 PROBLEM SUMMARY

**CRITICAL:** Bot waits until next check time on startup, ignoring signals already in buffer.

**Current Situation:**
- Bot started: 16:33:17
- Signals received: 16:33:17, 16:35:01 (~155 signals in buffer)
- Bot waiting until: 16:48:00 (15 minute delay)
- Trading: COMPLETELY BLOCKED

**Impact:** 1-23 minute trading delay on every restart between check times.

---

## 🎯 SOLUTION STRATEGY

**Add startup buffer check BEFORE first wait:**
1. On startup: Check if signals already in buffer for recent wave timestamps
2. If found: Process immediately
3. If not found: Wait for next check time as usual

**Preserve existing logic:**
- Don't change wave processing logic
- Don't change wait calculation
- Just add ONE check at the beginning

---

## 🔧 IMPLEMENTATION PLAN

### Change #1: Add First Check Flag (Line ~188)

**Location:** `_monitor_waves()` method start

**BEFORE:**
```python
async def _monitor_waves(self):
    """
    Мониторить появление новых волн и обработать их

    Логика:
    1. Ждать до следующего времени проверки волны (например, 22 минута)
    2. Вычислить timestamp ожидаемой волны (например, 00 минута = 15 минут назад)
    3. Мониторить появление сигналов с этим timestamp (до 120 секунд)
    4. Обработать волну когда сигналы появились
    """
    logger.info("🌊 Wave monitoring loop started")

    while self.running:
        try:
            # 1. Ждём до следующего времени проверки волны
            await self._wait_for_next_wave_check()
```

**AFTER:**
```python
async def _monitor_waves(self):
    """
    Мониторить появление новых волн и обработать их

    Логика:
    0. [NEW] При старте: проверить буфер на готовые волны
    1. Ждать до следующего времени проверки волны (например, 22 минута)
    2. Вычислить timestamp ожидаемой волны (например, 00 минута = 15 минут назад)
    3. Мониторить появление сигналов с этим timestamp (до 120 секунд)
    4. Обработать волну когда сигналы появились
    """
    logger.info("🌊 Wave monitoring loop started")

    # Flag to check buffer on first iteration (startup case)
    first_iteration = True

    while self.running:
        try:
            # 0. [NEW] Startup check: look for waves already in buffer
            if first_iteration:
                logger.info("🔍 Startup: checking for waves in buffer...")
                first_iteration = False

                # Try to find and process waves from recent timestamps
                wave_found = await self._check_recent_waves()

                if wave_found:
                    logger.info("✅ Startup wave processed, continuing to next")
                    continue  # Skip wait, go to next iteration
                else:
                    logger.info("No waves in buffer, will wait for next check time")

            # 1. Ждём до следующего времени проверки волны
            await self._wait_for_next_wave_check()
```

**Changes:**
- Add `first_iteration = True` flag
- Add startup check before first wait
- If wave found: process and continue
- If no wave: proceed with normal wait

---

### Change #2: Add _check_recent_waves() Method (After line ~486)

**Location:** After `_wait_for_next_wave_check()` method

**NEW METHOD:**
```python
async def _check_recent_waves(self) -> bool:
    """
    Check buffer for signals from recent wave timestamps (startup case)

    When bot starts between check times (e.g., minute 33),
    there might be signals from previous waves (e.g., 15:15, 15:30)
    already in buffer. This method checks for them.

    Logic:
    - Check last 3 possible wave times (15-min intervals)
    - If now = 16:33, check: 16:30, 16:15, 16:00
    - For each: look for signals with that timestamp
    - If found: process wave immediately

    Returns:
        True if wave found and processed, False otherwise
    """
    now = datetime.now(timezone.utc)

    logger.info(f"🔍 Checking buffer for recent waves (current time: {now.strftime('%H:%M:%S')})")

    # Check last 3 possible 15-minute wave timestamps
    # Going back: 3 min, 18 min, 33 min (covers last 3 waves)
    for minutes_back in [3, 18, 33]:
        check_time = now - timedelta(minutes=minutes_back)

        # Round down to nearest 15-minute mark (:00, :15, :30, :45)
        wave_minute = (check_time.minute // 15) * 15
        wave_time = check_time.replace(minute=wave_minute, second=0, microsecond=0)
        wave_timestamp = wave_time.strftime("%Y-%m-%d %H:%M:%S")

        logger.info(f"  Checking for wave: {wave_timestamp} ({minutes_back} min ago)")

        # Check if this wave was already processed
        if wave_timestamp in self.processed_waves:
            logger.info(f"  Wave {wave_timestamp} already processed, skipping")
            continue

        # Look for signals with this timestamp in buffer
        signals = self._find_signals_by_timestamp(wave_timestamp)

        if signals and len(signals) > 0:
            logger.info(f"✅ Found wave {wave_timestamp} in buffer with {len(signals)} signals!")

            # Mark wave as processing (atomic protection)
            self.processed_waves[wave_timestamp] = {
                'status': 'processing',
                'started_at': datetime.now(timezone.utc)
            }

            # Process this wave
            try:
                await self._process_wave(wave_timestamp, signals)
                logger.info(f"✅ Startup wave {wave_timestamp} processed successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to process startup wave {wave_timestamp}: {e}")
                # Mark as failed
                self.processed_waves[wave_timestamp] = {
                    'status': 'failed',
                    'error': str(e)
                }
                # Continue checking other waves
                continue
        else:
            logger.debug(f"  No signals found for {wave_timestamp}")

    logger.info("No waves found in buffer")
    return False
```

**Method Features:**
- Checks last 3 waves (covers ~45 minutes of history)
- Respects processed_waves cache (no duplicates)
- Uses existing _find_signals_by_timestamp() helper
- Uses existing _process_wave() logic
- Returns True if wave processed (allows continue in loop)

---

### Change #3: Verify Helper Method Exists

**Check:** `_find_signals_by_timestamp()` method

**Location:** Should exist in signal_processor_websocket.py

**If NOT exist, add:**
```python
def _find_signals_by_timestamp(self, timestamp: str) -> List[Dict]:
    """
    Find signals in buffer with given timestamp

    Args:
        timestamp: Wave timestamp in format "YYYY-MM-DD HH:MM:SS"

    Returns:
        List of signals matching timestamp
    """
    matching_signals = []

    for signal in self.signal_buffer:
        if signal.get('timestamp') == timestamp:
            matching_signals.append(signal)

    return matching_signals
```

---

## 📝 STEP-BY-STEP IMPLEMENTATION

### Step 1: Read Current Code
```bash
# Read _monitor_waves() method
# Verify line numbers
# Check for _find_signals_by_timestamp() existence
```

### Step 2: Apply Change #1
```
Location: _monitor_waves() method (line ~180)
Action: Add first_iteration flag and startup check
Lines to add: ~15 lines
```

### Step 3: Apply Change #2
```
Location: After _wait_for_next_wave_check() method (line ~486)
Action: Add _check_recent_waves() method
Lines to add: ~70 lines
```

### Step 4: Apply Change #3 (if needed)
```
Location: After _check_recent_waves() method
Action: Add _find_signals_by_timestamp() if missing
Lines to add: ~15 lines (only if not exists)
```

### Step 5: Verification
```bash
# Grep for syntax errors
python3 -m py_compile core/signal_processor_websocket.py

# Check logic
grep "first_iteration" core/signal_processor_websocket.py
grep "_check_recent_waves" core/signal_processor_websocket.py
```

---

## ✅ VERIFICATION CHECKLIST

### Code Changes

- [ ] `first_iteration = True` flag added
- [ ] Startup check added before first wait
- [ ] `_check_recent_waves()` method added
- [ ] `_find_signals_by_timestamp()` verified/added
- [ ] `continue` logic correct (skip wait if wave found)
- [ ] Python syntax valid (no compilation errors)

### Logic Verification

- [ ] First iteration: checks buffer
- [ ] Wave found: processed immediately, continues loop
- [ ] No wave found: proceeds with normal wait
- [ ] Second+ iterations: skip startup check, wait normally
- [ ] processed_waves cache respected (no duplicates)

### Testing

- [ ] Restart bot with signals in buffer: wave processed immediately
- [ ] Restart bot with empty buffer: waits for next check
- [ ] After startup wave: normal cycle continues
- [ ] Multiple waves in buffer: all processed

---

## 🧪 TESTING PLAN

### Test 1: Restart with Signals in Buffer

**Setup:**
1. Ensure signal server sending signals
2. Wait for signals to accumulate (30 seconds)
3. Restart bot

**Expected:**
```
16:XX:XX - 🌊 Wave monitoring loop started
16:XX:XX - 🔍 Startup: checking for waves in buffer...
16:XX:XX -   Checking for wave: 2025-10-26 15:30:00 (3 min ago)
16:XX:XX - ✅ Found wave 2025-10-26 15:30:00 in buffer with 12 signals!
16:XX:XX - ✅ Startup wave 2025-10-26 15:30:00 processed successfully
16:XX:XX - ⏰ Waiting XXXs until next wave check at XX:XX UTC
```

**Timing:** Wave processed within 5 seconds of startup

### Test 2: Restart with Empty Buffer

**Setup:**
1. Stop signal server
2. Clear buffer
3. Restart bot

**Expected:**
```
16:XX:XX - 🌊 Wave monitoring loop started
16:XX:XX - 🔍 Startup: checking for waves in buffer...
16:XX:XX -   Checking for wave: 2025-10-26 15:30:00 (3 min ago)
16:XX:XX -   No signals found for 2025-10-26 15:30:00
16:XX:XX -   Checking for wave: 2025-10-26 15:15:00 (18 min ago)
16:XX:XX -   No signals found for 2025-10-26 15:15:00
16:XX:XX -   Checking for wave: 2025-10-26 15:00:00 (33 min ago)
16:XX:XX -   No signals found for 2025-10-26 15:00:00
16:XX:XX - No waves found in buffer
16:XX:XX - ⏰ Waiting XXXs until next wave check at XX:XX UTC
```

**Timing:** Wait begins immediately (no delay)

### Test 3: Multiple Waves in Buffer

**Setup:**
1. Stop bot for 30+ minutes
2. Let signals accumulate (2-3 waves)
3. Restart bot

**Expected:**
```
16:XX:XX - ✅ Found wave 2025-10-26 15:30:00 in buffer with 12 signals!
16:XX:XX - ✅ Startup wave processed successfully
16:XX:XX - ⏰ Waiting XXXs until next wave check at XX:XX UTC
```

**Note:** Only processes FIRST found wave, then resumes normal cycle (other waves will be caught at next check)

---

## 🚀 DEPLOYMENT PLAN

### Pre-Deployment

- [ ] Read current code
- [ ] Identify exact line numbers
- [ ] Plan surgical changes

### Deployment

- [ ] Apply Change #1 (first_iteration flag + startup check)
- [ ] Apply Change #2 (_check_recent_waves method)
- [ ] Apply Change #3 if needed (_find_signals helper)
- [ ] Verify syntax: `python3 -m py_compile core/signal_processor_websocket.py`
- [ ] Git commit with detailed message
- [ ] Push to origin/main

### Post-Deployment

- [ ] Restart bot immediately
- [ ] Monitor logs for startup check
- [ ] Verify wave processed within 5 seconds
- [ ] Verify normal cycle continues
- [ ] Monitor next few waves (verify no regressions)

---

## 🔄 ROLLBACK PLAN

### If Issues Occur

**Option 1: Git Revert**
```bash
git revert HEAD
git push origin main
# Bot will return to waiting behavior (safe, but trading blocked)
```

**Option 2: Quick Fix**
```python
# If _check_recent_waves() has bug, disable it:
if first_iteration:
    first_iteration = False
    # COMMENTED OUT: wave_found = await self._check_recent_waves()
    pass  # Skip startup check, use old behavior
```

**Safety:** Rollback safe - returns to current (waiting) behavior

---

## 📊 EXPECTED RESULTS

### Before Fix

```
16:33:17 - ⏰ Waiting 882s until next wave check at 12:48 UTC
[... 15 minutes of silence ...]
16:48:00 - 🔍 Looking for wave with timestamp: 2025-10-26 15:30:00
```

**Delay:** 15 minutes
**Signals:** Sitting in buffer, ignored

### After Fix

```
16:33:17 - 🌊 Wave monitoring loop started
16:33:17 - 🔍 Startup: checking for waves in buffer...
16:33:17 - ✅ Found wave 2025-10-26 15:30:00 in buffer with 12 signals!
16:33:19 - ✅ Startup wave processed successfully
16:33:19 - ⏰ Waiting 876s until next wave check at 12:48 UTC
```

**Delay:** 2 seconds
**Signals:** Processed immediately

### Metrics

| Metric | Before | After |
|--------|--------|-------|
| Startup delay | 1-23 minutes | <5 seconds |
| Signals processed | After wait | Immediately |
| Trading blocked | Yes | No |
| Wave processing | At check time | On startup + check times |

---

## 🔐 RISK ASSESSMENT

### Implementation Risk: LOW 🟢

**Why:**
- Only adds check at beginning
- Doesn't modify existing wave processing
- Uses existing methods (_process_wave, _find_signals_by_timestamp)
- first_iteration flag prevents repeated checks
- Continue logic skips wait, resumes normal cycle

### Testing Risk: LOW 🟢

**Why:**
- Easy to test (just restart bot)
- Observable in logs (startup check messages)
- Quick feedback (5 seconds to see result)
- Safe to test in production (isolated change)

### Deployment Risk: LOW 🟢

**Why:**
- No database changes
- No breaking changes
- Rollback simple (git revert)
- Worst case: returns to current behavior (waiting)

---

## 🎯 SUCCESS CRITERIA

### Implementation Success

✅ **Code:**
- first_iteration flag added
- Startup check added
- _check_recent_waves() method added
- Syntax valid
- Git committed and pushed

### Runtime Success

✅ **Logs:**
- "Startup: checking for waves in buffer" message
- "Found wave" or "No waves in buffer" message
- Wave processed within 5 seconds (if in buffer)
- Normal cycle continues after startup

✅ **Trading:**
- Positions opened immediately on restart (if wave ready)
- No 15-minute delay
- Normal wave processing continues

---

**Plan Status:** ✅ READY FOR IMMEDIATE IMPLEMENTATION
**Created by:** Claude Code
**Date:** 2025-10-26 16:40:00
**Priority:** 🔴 P0 - CRITICAL
**Estimated Time:** 10 minutes
**Risk:** LOW 🟢
