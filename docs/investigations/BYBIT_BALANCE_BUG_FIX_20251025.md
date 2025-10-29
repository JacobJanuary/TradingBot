# 🐛 BUG FIX: Bybit Mainnet Balance Detection

**Date:** 2025-10-25
**Severity:** 🔴 CRITICAL
**Impact:** ALL Bybit signals were incorrectly filtered since mainnet switch
**Status:** ✅ FIXED

---

## 📊 Problem Summary

**Symptom:**
- User has $52.71 USDT available on Bybit mainnet
- Bot detected $0.00 free USDT
- ALL Bybit signals filtered with "Insufficient free balance"

**Impact:**
- Wave 22:34: 3 Bybit signals filtered
- Wave 22:49: 3 Bybit signals filtered
- Wave 23:05: 1 Bybit signal filtered
- **Total:** ~7+ trading opportunities missed

---

## 🔍 Root Cause Analysis

### API Response Issue

Bybit UNIFIED account API returns:
```json
{
  "totalAvailableBalance": "",    ← EMPTY STRING!
  "totalWalletBalance": "53.13915183",
  "coin": [
    {
      "coin": "USDT",
      "walletBalance": "52.71527456",  ← CORRECT VALUE HERE
      "locked": "0"
    }
  ]
}
```

### Bug Location

**File:** `core/exchange_manager.py:262`

**Broken Code:**
```python
account = accounts[0]
return float(account.get('totalAvailableBalance', 0))
```

**What Happened:**
1. `totalAvailableBalance` returns empty string `""`
2. `float("")` raises ValueError
3. Exception caught, fallback to `fetch_balance()`
4. `fetch_balance()` also returns `free: null` for Bybit
5. Final result: $0.00 free balance ❌

**Error Log:**
```
WARNING:core.exchange_manager:Bybit balance fetch failed, fallback:
could not convert string to float: ''
```

---

## ✅ Solution

### Fixed Code

```python
# FIX: totalAvailableBalance is often empty string "" for UNIFIED accounts
# Use coin[].walletBalance instead
coins = account.get('coin', [])
for coin_data in coins:
    if coin_data.get('coin') == 'USDT':
        # walletBalance - locked = available for new positions
        wallet_balance = float(coin_data.get('walletBalance', 0) or 0)
        locked = float(coin_data.get('locked', 0) or 0)
        free_balance = wallet_balance - locked
        logger.debug(f"Bybit USDT: wallet={wallet_balance:.2f}, locked={locked:.2f}, free={free_balance:.2f}")
        return free_balance
```

### Why This Works

**Bybit UNIFIED Account Structure:**
- `totalAvailableBalance` - Often empty for UNIFIED accounts
- `totalWalletBalance` - Total equity (includes unrealized PnL)
- `coin[].walletBalance` - Actual USDT wallet balance
- `coin[].locked` - Amount locked in orders/positions
- **Free = walletBalance - locked** ✅

---

## 🧪 Verification

### Before Fix
```
Bybit (mainnet):
  Free USDT:  $0.00 ❌
  Total USDT: $53.14
  Status:     CANNOT OPEN POSITIONS
```

### After Fix
```
Bybit (mainnet):
  Free USDT:  $52.72 ✅
  Total USDT: $53.14
  Status:     CAN OPEN POSITIONS
```

### User UI Match
```
User's Bybit UI:
  Available Balance: 52.7152 USDT ✅

Bot after fix:
  Free USDT: $52.72 ✅

Difference: $0.00 (PERFECT MATCH)
```

---

## 📈 Impact on Trading

### Missed Opportunities (Estimated)

**Since mainnet switch (~Oct 24):**
- Waves processed: ~10
- Bybit signals per wave: ~3
- Total Bybit signals: ~30
- All filtered: 30 ❌

**With fix:**
- Can now open Bybit positions ✅
- $52.72 available = ~8 positions ($6 each)
- Additional trading opportunities restored

---

## 🔧 Files Modified

### 1. core/exchange_manager.py

**Function:** `_get_free_balance_usdt()`
**Lines:** 242-286
**Changes:**
- Fixed Bybit UNIFIED account balance parsing
- Now reads from `coin[]` array instead of `totalAvailableBalance`
- Added debug logging for transparency

---

## 🎯 Why This Bug Wasn't Detected Earlier

1. **Testnet vs Mainnet:**
   - Bybit testnet may return `totalAvailableBalance` correctly
   - Mainnet returns empty string for UNIFIED accounts
   - Bug only appeared after mainnet switch

2. **Silent Failure:**
   - Exception was caught silently
   - Logged as WARNING, not ERROR
   - Fallback returned $0.00 without loud failure
   - No alerts triggered

3. **Confusing Metrics:**
   - Wave showed 0 opened, 0 failed
   - Signals were "filtered" not "failed"
   - Database didn't record filter reason
   - Looked like signals were just low quality

---

## 🚀 Testing Recommendations

### Immediate Testing

1. **Restart Bot:**
   ```bash
   # Kill current instance
   pkill -f "python main.py"

   # Restart
   python main.py
   ```

2. **Monitor Next Wave:**
   - Wait for next signal wave
   - Check if Bybit positions open
   - Verify logs show: `Bybit USDT: wallet=52.72, locked=0.00, free=52.72`

3. **Manual Test:**
   ```python
   from core.exchange_manager import ExchangeManager
   from config.settings import config

   em = ExchangeManager('bybit', config.get_exchange_config('bybit').__dict__)
   await em.initialize()
   free = await em._get_free_balance_usdt()
   print(f"Free: ${free:.2f}")  # Should be ~52.72
   ```

### Long-term Monitoring

- Track Bybit position open rate
- Compare Binance vs Bybit success rate
- Monitor for "Insufficient balance" filters

---

## 📝 Related Issues

### Wave 22:49 Investigation

This bug explains why wave 22:49 had 0 positions opened:
- 3 Bybit signals: Filtered due to this bug ✅
- 2 Binance signals: Still unknown (likely duplicates)

**Next steps:**
- Check terminal logs for Binance filter reasons
- Likely duplicate symbols already in positions

---

## 🎓 Lessons Learned

1. **Always validate external API responses:**
   - Bybit API doesn't follow expected format for UNIFIED accounts
   - Can't trust field names alone, must inspect actual values

2. **Silent failures are dangerous:**
   - Exception → Warning → Fallback → $0.00
   - Should have been ERROR level with alert

3. **Testnet != Mainnet:**
   - API behavior can differ between test and production
   - Always test on mainnet before full deployment

4. **Log DEBUG data for critical calculations:**
   - Added: `Bybit USDT: wallet=X, locked=Y, free=Z`
   - Makes debugging much easier

---

## ✅ Fix Validation Checklist

- [x] Code review: Logic is correct
- [x] Local testing: Returns $52.72 ✅
- [x] Matches user UI: 52.7152 USDT ✅
- [x] No exceptions: Clean execution
- [ ] Live testing: Wait for next wave
- [ ] Monitor 24h: Check position open rate
- [ ] Git commit: Save fix permanently

---

**Fixed by:** Claude Code
**Verified by:** Balance check script
**Deployed:** Pending bot restart
**Risk:** Low (isolated to Bybit balance detection, clear improvement)

---

## 🔗 References

- Bybit API Docs: https://bybit-exchange.github.io/docs/v5/account/wallet-balance
- UNIFIED Account: Uses `coin[]` array for per-asset balances
- Previous similar fix: commit [REFERENCE] (if exists)
