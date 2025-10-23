# ✅ AGED V2 ACTIVATION CHECKLIST

**Purpose:** Step-by-step guide to activate Aged Position Monitor V2
**Time Required:** 15 minutes + monitoring
**Risk Level:** Minimal (instant rollback available)

---

## 📋 PRE-ACTIVATION CHECKLIST

### Verify Current State
- [ ] Check current environment variable:
  ```bash
  echo $USE_UNIFIED_PROTECTION
  # Should be empty or "false"
  ```

- [ ] Check current aged positions:
  ```bash
  grep "aged" trading_bot.log | tail -20
  ```

- [ ] Note current metrics:
  - Number of aged positions: _____
  - Average close time: _____
  - Failed orders in last 24h: _____

---

## 🚀 ACTIVATION STEPS

### Step 1: Backup Current State
```bash
# Create backup point
cp trading_bot.log trading_bot.log.pre_v2_$(date +%Y%m%d_%H%M%S)
```

### Step 2: Activate V2
```bash
# Set environment variable
export USE_UNIFIED_PROTECTION=true

# Verify it's set
echo $USE_UNIFIED_PROTECTION
# Should show: true
```

### Step 3: Restart Bot
```bash
# Stop current instance (if running)
# Ctrl+C or kill process

# Start with V2 enabled
python main.py
```

### Step 4: Verify Activation
```bash
# Check logs for V2 initialization
grep -i "unified\|v2" trading_bot.log | tail -10

# Should see messages about UnifiedProtection initialization
```

---

## 🔍 MONITORING CHECKLIST (First 24 Hours)

### Every Hour:
- [ ] Check for aged positions being detected:
  ```bash
  grep "aged" trading_bot.log | grep -v "skipped" | tail -10
  ```

- [ ] Check for successful MARKET closes:
  ```bash
  grep "MARKET.*aged" trading_bot.log | tail -10
  ```

- [ ] Check for any errors:
  ```bash
  grep -i "error.*aged" trading_bot.log | tail -10
  ```

### After 6 Hours:
- [ ] Count aged position closures:
  ```bash
  grep "Closed aged position" trading_bot.log | wc -l
  ```

- [ ] Check execution success rate:
  ```bash
  # Successful closes
  grep "Successfully closed aged" trading_bot.log | wc -l
  # Failed attempts
  grep "Failed to close aged" trading_bot.log | wc -l
  ```

### After 24 Hours:
- [ ] Compare metrics with pre-activation baseline
- [ ] Document improvements
- [ ] Decision: Keep V2 or rollback

---

## 🚨 INSTANT DETECTION FIX (CRITICAL)

### Add to `core/position_manager.py` (line ~1850):
```python
# In method _on_position_update, after position update logic:

# Check if position just became aged (instant detection)
if self.unified_protection and symbol in self.positions:
    position = self.positions[symbol]
    age_hours = self._calculate_position_age_hours(position)

    if age_hours > self.max_position_age_hours:
        aged_monitor = self.unified_protection.get('aged_monitor')
        if aged_monitor and symbol not in aged_monitor.aged_targets:
            await aged_monitor.add_aged_position(position)
            logger.info(f"⚡ INSTANT AGED DETECTION: {symbol}")
```

### Verify Fix Working:
```bash
# Should see instant detection messages
grep "INSTANT AGED DETECTION" trading_bot.log
```

---

## 🔄 ROLLBACK PROCEDURE (If Needed)

### Immediate Rollback:
```bash
# Unset or set to false
export USE_UNIFIED_PROTECTION=false

# Restart
python main.py

# Verify rollback
grep "AgedPositionManager" trading_bot.log | tail -5
# Should show legacy manager initialization
```

---

## 📊 SUCCESS CRITERIA

### V2 is Working Properly If:
- ✅ Aged positions detected within 1 second of becoming aged
- ✅ MARKET orders execute successfully (>95% success rate)
- ✅ No position blocking errors
- ✅ No increase in failed closures
- ✅ Faster average closure time

### Consider Rollback If:
- ❌ Repeated MARKET order failures (>10%)
- ❌ Unexpected errors in aged monitoring
- ❌ Positions not being detected at all
- ❌ System instability

---

## 📞 TROUBLESHOOTING

### Issue: V2 Not Activating
```bash
# Check if unified protection initialized
grep "UnifiedProtection" trading_bot.log
# If missing, environment variable not set correctly
```

### Issue: Positions Not Being Monitored
```bash
# Check if aged monitor is running
grep "AgedPositionMonitorV2" trading_bot.log
# Check WebSocket connection
grep "WebSocket.*connected" trading_bot.log
```

### Issue: MARKET Orders Failing
```bash
# Check exchange connectivity
grep "exchange.*error" trading_bot.log
# Check order details
grep "MARKET.*failed" trading_bot.log
```

---

## 📝 POST-ACTIVATION TASKS

### Day 1:
- [ ] Monitor metrics hourly
- [ ] Document any issues
- [ ] Apply instant detection fix if not already done

### Day 2-3:
- [ ] Analyze 48-hour metrics
- [ ] Compare with baseline
- [ ] Make keep/rollback decision

### Week 1:
- [ ] If keeping V2, remove legacy code flag
- [ ] Update documentation
- [ ] Plan Phase 2 enhancements

---

## 🎯 QUICK REFERENCE

**Activate V2:**
```bash
export USE_UNIFIED_PROTECTION=true && python main.py
```

**Check Status:**
```bash
echo $USE_UNIFIED_PROTECTION
grep -c "aged" trading_bot.log
```

**Emergency Rollback:**
```bash
export USE_UNIFIED_PROTECTION=false && python main.py
```

---

**Document Version:** 1.0
**Last Updated:** 2025-10-23
**Next Review:** After 48 hours of V2 operation