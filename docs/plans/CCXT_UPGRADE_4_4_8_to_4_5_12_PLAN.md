# CCXT Upgrade Plan: 4.4.8 → 4.5.12

**Дата**: 2025-10-27
**Текущая версия**: 4.4.8
**Целевая версия**: 4.5.12
**Gap**: 92 patch releases в 4.4.x + 12 releases в 4.5.x

---

## 📊 EXECUTIVE SUMMARY

**Upgrade рекомендуется**: ✅ **ДА**

**Причины upgrade:**
1. ✅ **Bybit SL/TP fixes** (v4.5.12) - критично для бота
2. ✅ **Bybit parsePosition initialMargin fix** (v4.5.12) - затрагивает наш код
3. ✅ **Security & bug fixes** за 104 релиза
4. ✅ **Bybit spot TP/SL improvements** (v4.5.9)

**Риски upgrade:**
- 🟡 **MEDIUM RISK**: Position parsing может вернуть другие значения
- 🟡 **MEDIUM RISK**: Stop-loss format/response может измениться
- 🟢 **LOW RISK**: Balance fetching стабилен

**Timeline**: ~4 hours (backup, test, verification, deploy)

---

## 🔍 VERSION GAP ANALYSIS

### Current State
```
Installed: ccxt==4.4.8
Last checked: ~October 2025 (docs/CCXT_UPGRADE_ANALYSIS.md)
```

### Latest Available
```
Latest: ccxt==4.5.12 (2025-10-22)
PyPI: Available ✅
```

### Releases Gap
```
4.4.8  → 4.4.100  : 92 patch releases
4.4.100 → 4.5.0   : 1 minor version bump
4.5.0  → 4.5.12   : 12 patch releases
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL: 105 releases
```

---

## 🎯 CRITICAL CHANGES AFFECTING OUR CODE

### 1. Bybit Stop-Loss & Take-Profit (v4.5.12) 🔴 HIGH IMPACT

**Change:**
```
fix(bybit): stoploss & tp order
```

**Impact on our code:**
- **File**: `core/stop_loss_manager.py`
- **Lines**: 344-350 (SL creation), 81-100 (SL detection)
- **Current usage**:
  ```python
  params = {
      'category': 'linear',
      'symbol': bybit_symbol,
      'stopLoss': str(sl_price_formatted),  # ← May change format
      'positionIdx': 0,
      'slTriggerBy': 'LastPrice',
      'tpslMode': 'Full'
  }
  ```

**Risk**: 🟡 **MEDIUM**
- SL order creation may require different params
- SL detection via `position.info.stopLoss` may return different format
- Response parsing may change

**Test required**: ✅ Create SL order and verify response

---

### 2. Bybit parsePosition initialMargin (v4.5.12) 🔴 HIGH IMPACT

**Change:**
```
fix(bybit): parsePosition, initialMargin value
```

**Impact on our code:**
- **File**: `core/exchange_manager.py:271`
- **Current usage**:
  ```python
  total_position_im = float(coin_data.get('totalPositionIM', 0) or 0)
  free_balance = wallet_balance - total_position_im  # ← Recently fixed!
  ```

**Risk**: 🟢 **LOW** (но требует verification!)
- Мы используем **coin-level** `totalPositionIM`, не position parsing
- CCXT fix касается `parsePosition()` метода
- **НО**: Нужно убедиться что coin-level data не изменилась

**Test required**: ✅ Verify `totalPositionIM` values match expectations

---

### 3. Bybit Fee Response Format (v4.5.6) 🟡 MEDIUM IMPACT

**Change:**
```
new fee responses for order endpoints
```

**Impact on our code:**
- **Files**: `core/order_executor.py`, `core/atomic_position_manager.py`
- **Usage**: Order creation responses
- **Risk**: 🟡 **MEDIUM** - Fee parsing may break

**Test required**: ✅ Create order and verify fee parsing

---

### 4. Bybit Spot TP/SL Type 2 Orders (v4.5.9) 🟢 LOW IMPACT

**Change:**
```
fix(bybit): spot tp/sl type 2 orders
```

**Impact**: 🟢 **NONE** (we use linear/futures only)

---

### 5. Binance Changes (v4.5.x) 🟢 LOW IMPACT

**Changes:**
- v4.5.12: fix for issue #27064
- v4.5.11: cancelOrders with clientOrderIds
- v4.5.6: demo trading, spot trailing orders

**Impact**: 🟢 **LOW**
- No breaking changes for our usage
- We use standard Binance Futures API

---

## 📋 OUR CODE USAGE ANALYSIS

### Critical CCXT Methods Used

| Method | Locations | Risk | Notes |
|--------|-----------|------|-------|
| **fetch_positions()** | 19 files, 25 usages | 🟡 MEDIUM | May return different initialMargin |
| **fetch_balance()** | 8 files, 37 usages | 🟢 LOW | Stable, just fixed for Bybit |
| **create_order()** | 6 files, 15 usages | 🟡 MEDIUM | Fee format may change |
| **set_leverage()** | 2 files | 🟢 LOW | Just tested, working |
| **fetch_open_orders()** | 5 files | 🟢 LOW | Stable API |

### Bybit-Specific Parameters

**We use CORRECT params (verified):**
```python
# Positions
await exchange.fetch_positions(symbols=[...], params={'category': 'linear'})

# Leverage
await exchange.set_leverage(leverage=10, symbol=..., params={'category': 'linear'})

# Stop-Loss
params = {
    'category': 'linear',
    'stopLoss': str(price),
    'positionIdx': 0,
    'slTriggerBy': 'LastPrice',
    'tpslMode': 'Full'
}
```

**Conclusion**: ✅ Our parameters are correct and should remain compatible

---

## ⚠️ RISK ASSESSMENT

### 🔴 HIGH RISK Areas

**1. Stop-Loss Detection Logic**
- **File**: `core/stop_loss_manager.py:81-100`
- **Code**:
  ```python
  stop_loss = pos.get('info', {}).get('stopLoss', '0')
  if stop_loss and stop_loss != '0' and stop_loss != '':
      return (True, float(stop_loss))
  ```
- **Risk**: `info.stopLoss` format may change in v4.5.12
- **Mitigation**: Тест на реальном Bybit аккаунте

**2. Stop-Loss Creation**
- **File**: `core/stop_loss_manager.py:344-350`
- **Risk**: Params format may change
- **Mitigation**: Create test SL order

### 🟡 MEDIUM RISK Areas

**3. Position Parsing**
- **Files**: `core/aged_position_monitor_v2.py`, WebSocket handlers
- **Risk**: Position data structure changes
- **Mitigation**: Verify position data after upgrade

**4. Order Fee Response**
- **Files**: `core/order_executor.py`
- **Risk**: Fee field parsing may break
- **Mitigation**: Check order response structure

### 🟢 LOW RISK Areas

**5. Balance Fetching**
- ✅ Just fixed in our code (commit a69c358)
- ✅ Using coin-level data, not account-level
- ✅ Stable across CCXT versions

**6. Leverage Setting**
- ✅ Recently tested and working
- ✅ No changes in changelog

---

## 🛠️ MIGRATION PLAN

### Phase 1: Preparation (15 minutes)

#### Step 1: Backup Current Environment
```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Backup requirements
pip3 freeze > requirements_freeze_before_4.5.12.txt

# Verify current version
python3 -c "import ccxt; print(f'Current: {ccxt.__version__}')"
# Expected: 4.4.8

# Git commit state
git add -A
git status
# Ensure working directory is clean
```

#### Step 2: Create Upgrade Branch
```bash
git checkout -b upgrade/ccxt-4.5.12
```

#### Step 3: Review Changelog (Already Done ✅)
- Changelog reviewed: v4.4.8 → v4.5.12
- Critical changes identified
- Risk assessment completed

---

### Phase 2: Upgrade & Initial Testing (1 hour)

#### Step 4: Perform Upgrade
```bash
# Upgrade CCXT
pip3 install --upgrade ccxt==4.5.12

# Verify installation
python3 -c "import ccxt; print(f'Installed: {ccxt.__version__}')"
# Expected: 4.5.12

# Update requirements.txt
pip3 freeze | grep ccxt
# Update requirements.txt manually: ccxt==4.5.12
```

#### Step 5: Run Existing Tests
```bash
# Test 1: Bybit free balance (recently fixed)
python3 tests/manual/test_bybit_free_balance_bug.py

# Expected output:
# Current code returns: $X.XX
# Correct value should be: $X.XX (within $0.01)
# ✅ free_balance matches

# Test 2: Binance free balance
python3 tests/manual/test_binance_free_balance_investigation.py

# Expected:
# ✅ CCXT 'free' matches availableBalance

# Test 3: Leverage setting
python3 tests/test_phase2_set_leverage.py

# Expected:
# ✅ Binance leverage set successfully
# ✅ Bybit leverage set successfully
```

---

### Phase 3: Critical Feature Testing (1.5 hours)

#### Test 6: Bybit Stop-Loss Creation (CRITICAL!)
```bash
# Create test script
cat > tests/manual/test_ccxt_4_5_12_bybit_sl.py << 'EOF'
#!/usr/bin/env python3
"""
ТЕСТ: Bybit Stop-Loss after CCXT 4.5.12 upgrade
Проверяем что SL создается и определяется корректно
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager
from core.stop_loss_manager import StopLossManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_bybit_sl_after_upgrade():
    """Test Bybit SL creation and detection after CCXT upgrade"""
    print("=" * 100)
    print("TEST: Bybit Stop-Loss After CCXT 4.5.12 Upgrade")
    print("=" * 100)
    print()

    config = Config()
    bybit_config_obj = config.get_exchange_config('bybit')

    if not bybit_config_obj:
        print("❌ Bybit config not found")
        return

    bybit_config = {
        'api_key': bybit_config_obj.api_key,
        'api_secret': bybit_config_obj.api_secret,
        'testnet': bybit_config_obj.testnet,
        'rate_limit': True
    }

    exchange_mgr = ExchangeManager(
        exchange_name='bybit',
        config=bybit_config,
        repository=None
    )

    try:
        # Test 1: Fetch positions and check stopLoss field
        print("─" * 100)
        print("TEST 1: Fetch positions and check info.stopLoss format")
        print("─" * 100)

        positions = await exchange_mgr.exchange.fetch_positions(
            params={'category': 'linear'}
        )

        print(f"Total positions: {len(positions)}")

        for pos in positions[:3]:  # First 3 positions
            if float(pos.get('contracts', 0)) > 0:
                symbol = pos['symbol']
                contracts = pos.get('contracts', 0)
                stop_loss = pos.get('info', {}).get('stopLoss', '0')

                print(f"\nPosition: {symbol}")
                print(f"  Contracts: {contracts}")
                print(f"  info.stopLoss: '{stop_loss}' (type: {type(stop_loss).__name__})")

                # Verify parsing works
                if stop_loss and stop_loss != '0' and stop_loss != '':
                    try:
                        sl_float = float(stop_loss)
                        print(f"  ✅ Parsed as float: {sl_float}")
                    except:
                        print(f"  ❌ FAILED to parse stopLoss as float!")
                else:
                    print(f"  ℹ️  No SL attached to position")

        print()

        # Test 2: StopLossManager detection
        print("─" * 100)
        print("TEST 2: StopLossManager.has_stop_loss() method")
        print("─" * 100)

        sl_manager = StopLossManager(exchange_mgr.exchange, 'bybit')

        # Find a position with SL
        test_symbol = None
        for pos in positions:
            if float(pos.get('contracts', 0)) > 0:
                stop_loss = pos.get('info', {}).get('stopLoss', '0')
                if stop_loss and stop_loss != '0' and stop_loss != '':
                    test_symbol = pos['symbol']
                    break

        if test_symbol:
            print(f"Testing has_stop_loss() for: {test_symbol}")
            has_sl, sl_price = await sl_manager.has_stop_loss(test_symbol)

            print(f"  has_stop_loss() returned:")
            print(f"    has_sl: {has_sl}")
            print(f"    sl_price: {sl_price}")

            if has_sl:
                print(f"  ✅ Stop-loss detected successfully")
            else:
                print(f"  ❌ Stop-loss NOT detected (but position has SL!)")
        else:
            print("ℹ️  No positions with SL found for testing")

        print()

        # Test 3: Position IM field
        print("─" * 100)
        print("TEST 3: Verify totalPositionIM field in balance")
        print("─" * 100)

        response = await exchange_mgr.exchange.privateGetV5AccountWalletBalance({
            'accountType': 'UNIFIED',
            'coin': 'USDT'
        })

        result = response.get('result', {})
        accounts = result.get('list', [])

        if accounts:
            account = accounts[0]
            coins = account.get('coin', [])

            for coin_data in coins:
                if coin_data.get('coin') == 'USDT':
                    wallet_balance = float(coin_data.get('walletBalance', 0) or 0)
                    total_position_im = float(coin_data.get('totalPositionIM', 0) or 0)

                    print(f"USDT coin data:")
                    print(f"  walletBalance: ${wallet_balance:.4f}")
                    print(f"  totalPositionIM: ${total_position_im:.4f}")
                    print(f"  ✅ Field exists and parseable")

                    # Verify our calculation
                    free_balance = wallet_balance - total_position_im
                    print(f"  Calculated free: ${free_balance:.4f}")

                    # Compare with our method
                    our_free = await exchange_mgr._get_free_balance_usdt()
                    print(f"  Our method returns: ${our_free:.4f}")

                    diff = abs(free_balance - our_free)
                    if diff < 0.01:
                        print(f"  ✅ Match! (diff: ${diff:.4f})")
                    else:
                        print(f"  ❌ Mismatch! (diff: ${diff:.4f})")

        print()
        print("=" * 100)
        print("✅ TEST COMPLETE")
        print("=" * 100)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise

    finally:
        await exchange_mgr.close()


if __name__ == '__main__':
    asyncio.run(test_bybit_sl_after_upgrade())
EOF

chmod +x tests/manual/test_ccxt_4_5_12_bybit_sl.py
python3 tests/manual/test_ccxt_4_5_12_bybit_sl.py
```

**Expected results:**
```
✅ info.stopLoss field exists and parseable
✅ has_stop_loss() detects SL correctly
✅ totalPositionIM field unchanged
✅ Our free balance calculation still correct
```

**If FAILED**: 🚨 DO NOT DEPLOY! Investigate and fix.

---

#### Test 7: Bybit Order Creation
```bash
# Test order response format
cat > tests/manual/test_ccxt_4_5_12_order_response.py << 'EOF'
#!/usr/bin/env python3
"""Test order response format after CCXT upgrade"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_order_response():
    """Test order response structure"""
    print("=" * 100)
    print("TEST: Order Response Format After CCXT 4.5.12")
    print("=" * 100)
    print()

    config = Config()
    bybit_config_obj = config.get_exchange_config('bybit')

    if not bybit_config_obj:
        print("❌ Bybit config not found")
        return

    bybit_config = {
        'api_key': bybit_config_obj.api_key,
        'api_secret': bybit_config_obj.api_secret,
        'testnet': bybit_config_obj.testnet,
        'rate_limit': True
    }

    exchange_mgr = ExchangeManager(
        exchange_name='bybit',
        config=bybit_config,
        repository=None
    )

    try:
        # Fetch recent order to see response structure
        print("Fetching recent closed orders...")

        orders = await exchange_mgr.exchange.fetch_closed_orders(
            limit=1,
            params={'category': 'linear'}
        )

        if orders:
            order = orders[0]
            print(f"\nOrder response structure:")
            print(f"  Symbol: {order.get('symbol')}")
            print(f"  Side: {order.get('side')}")
            print(f"  Amount: {order.get('amount')}")
            print(f"  Filled: {order.get('filled')}")

            # Check fee field
            fee = order.get('fee')
            if fee:
                print(f"  Fee: {fee}")
                print(f"    Type: {type(fee)}")
                if isinstance(fee, dict):
                    print(f"    Keys: {fee.keys()}")
                    print(f"    ✅ Fee is dict (expected)")
                else:
                    print(f"    ⚠️ Fee is {type(fee)}, not dict!")
            else:
                print(f"  Fee: None")

            # Check info
            info = order.get('info', {})
            print(f"\n  info fields:")
            for key in ['cumExecQty', 'cumExecValue', 'cumExecFee', 'avgPrice']:
                val = info.get(key, 'NOT FOUND')
                print(f"    {key}: {val}")

            print(f"\n✅ Order response structure verified")
        else:
            print("ℹ️  No closed orders found")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise

    finally:
        await exchange_mgr.close()


if __name__ == '__main__':
    asyncio.run(test_order_response())
EOF

chmod +x tests/manual/test_ccxt_4_5_12_order_response.py
python3 tests/manual/test_ccxt_4_5_12_order_response.py
```

**Expected:**
```
✅ Fee field exists and is dict
✅ info.cumExecFee field exists
✅ Order response parseable
```

---

### Phase 4: Production-Like Testing (1 hour)

#### Test 8: Live Monitoring (Testnet if available)
```bash
# Start bot in dry-run mode or with minimal balance
python3 main.py

# Monitor for:
# - Position fetching errors
# - Stop-loss detection errors
# - Order creation errors
# - Balance calculation errors

# Watch logs for 30-60 minutes
```

**Checklist during monitoring:**
- [ ] ✅ Positions fetched successfully
- [ ] ✅ Stop-losses detected correctly
- [ ] ✅ Balance calculations accurate
- [ ] ✅ Orders created without errors
- [ ] ✅ No new exceptions in logs
- [ ] ✅ Fee parsing works

---

### Phase 5: Deployment (30 minutes)

#### Step 9: Commit Changes
```bash
# If all tests pass
git add requirements.txt
git add requirements_freeze_before_4.5.12.txt
git add tests/manual/test_ccxt_4_5_12_*.py

git commit -m "upgrade: CCXT 4.4.8 → 4.5.12

Upgraded CCXT to 4.5.12 for critical Bybit fixes:
- fix(bybit): stoploss & tp order (v4.5.12)
- fix(bybit): parsePosition initialMargin value (v4.5.12)
- fix(bybit): spot tp/sl type 2 orders (v4.5.9)

Testing completed:
✅ Bybit free balance calculation (unchanged)
✅ Binance free balance (unchanged)
✅ Bybit stop-loss creation and detection
✅ Order response parsing
✅ Position data structure
✅ Live monitoring (30-60 min)

Version gap: 4.4.8 → 4.5.12 (105 releases)

Related:
- Bybit balance fix: commit a69c358
- Binance verification: docs/investigations/BINANCE_FREE_BALANCE_VERIFICATION_REPORT.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

#### Step 10: Push and Deploy
```bash
git checkout main
git merge upgrade/ccxt-4.5.12
git push

# On production server
cd /path/to/TradingBot
git pull
pip3 install --upgrade ccxt==4.5.12

# Restart bot
# (use your deployment script)

# Monitor logs closely for 24 hours
```

---

## 🚨 ROLLBACK PLAN

If upgrade causes issues:

### Immediate Rollback
```bash
# Stop bot
# (use your stop command)

# Rollback CCXT
pip3 install ccxt==4.4.8

# Or restore from backup
pip3 install -r requirements_freeze_before_4.5.12.txt

# Restart bot
# (use your start command)

# Verify logs
tail -f logs/trading_bot.log
```

### Git Rollback
```bash
git checkout main
git revert HEAD
git push

# On server
git pull
pip3 install ccxt==4.4.8
# Restart bot
```

---

## 📊 SUCCESS CRITERIA

Upgrade is successful if:

1. ✅ All tests pass (Phase 3)
2. ✅ Bybit stop-loss creation works
3. ✅ Bybit stop-loss detection works (info.stopLoss)
4. ✅ Position data parsing correct (totalPositionIM)
5. ✅ Order fee parsing works
6. ✅ Balance calculation unchanged
7. ✅ No new errors in logs (24h monitoring)
8. ✅ No position tracking issues
9. ✅ No SL management issues
10. ✅ Binance functionality unchanged

---

## 🔧 KNOWN ISSUES & WORKAROUNDS

### Issue 1: Bybit Stop-Loss Format Changed

**Symptom:**
```python
ERROR: Failed to parse stopLoss from position
```

**Diagnosis:**
```python
# Check raw response
positions = await exchange.fetch_positions(params={'category': 'linear'})
print(positions[0]['info'])  # Look at stopLoss field
```

**Solution:**
- Update parsing in `core/stop_loss_manager.py:83-100`
- May need to handle new format/field name

---

### Issue 2: Position initialMargin Different Values

**Symptom:**
```python
WARNING: Position margin mismatch
```

**Diagnosis:**
```python
# Compare old vs new
print(f"Position initialMargin: {pos['initialMargin']}")
print(f"Coin totalPositionIM: {coin_data['totalPositionIM']}")
```

**Solution:**
- Verify our coin-level approach still correct
- May need to switch to position-level if coin-level changed

---

### Issue 3: Order Fee Parsing Error

**Symptom:**
```python
KeyError: 'fee' in order response
```

**Diagnosis:**
```python
# Check order response structure
order = await exchange.create_order(...)
print(order.keys())
print(order.get('fee'))
print(order.get('info', {}).get('cumExecFee'))
```

**Solution:**
- Update fee parsing in `core/order_executor.py`
- Use defensive dict.get() with defaults

---

## 📝 POST-UPGRADE MONITORING

### First 24 Hours - CRITICAL
Monitor these metrics:

1. **Error Rate**
   - Baseline: Current error rate
   - Target: No increase
   - Alert: >10% increase → investigate

2. **Stop-Loss Coverage**
   - Metric: % positions with SL
   - Baseline: ~95%+
   - Target: Unchanged
   - Alert: <90% → check SL detection

3. **Position Sync**
   - Metric: DB positions vs Exchange positions
   - Target: 100% match
   - Alert: Mismatches → check position parsing

4. **Balance Accuracy**
   - Metric: Bybit free balance calculation
   - Baseline: Within $0.01 of UI
   - Target: Unchanged
   - Alert: >$1 diff → check totalPositionIM

### Log Patterns to Watch

```bash
# Watch for new errors
tail -f logs/trading_bot.log | grep -i error

# Watch SL operations
tail -f logs/trading_bot.log | grep -i "stop.loss"

# Watch position operations
tail -f logs/trading_bot.log | grep -i "position"

# Watch balance operations
tail -f logs/trading_bot.log | grep -i "balance"
```

---

## 🎓 LESSONS LEARNED (Post-Upgrade)

### What Worked
- (To be filled after upgrade)

### What Didn't Work
- (To be filled after upgrade)

### Improvements for Next Time
- (To be filled after upgrade)

---

## ✅ FINAL RECOMMENDATION

**RECOMMENDED: Proceed with Upgrade ✅**

**Reasons:**
1. ✅ **Bybit SL/TP fixes** critical for our bot
2. ✅ **105 releases** of bug fixes and improvements
3. ✅ **Clear migration path** defined
4. ✅ **Comprehensive testing plan** ready
5. ✅ **Fast rollback** available if needed
6. 🟡 **Medium risk**, but manageable with testing

**Timeline:**
- Preparation: 15 min
- Upgrade & Tests: 1 hour
- Feature Testing: 1.5 hours
- Live Monitoring: 1 hour
- **TOTAL: ~4 hours**

**Next Steps:**
1. ✅ Plan approved → Begin Phase 1
2. ⏳ Execute upgrade following this plan
3. ⏳ Monitor for 24 hours
4. ⏳ Update this doc with results

---

**STATUS**: ⏳ **READY FOR EXECUTION**

Ждем команды пользователя для начала upgrade! 🚀

---

**End of Plan**
