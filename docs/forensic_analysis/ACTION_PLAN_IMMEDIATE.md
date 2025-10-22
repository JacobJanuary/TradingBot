# IMMEDIATE ACTION PLAN
## Critical Fixes for Trading Bot - 2025-10-22

**Status**: 🔴 HIGH PRIORITY - Execute ASAP
**Estimated Time**: 4-6 hours for critical fixes
**Risk**: Active position without stop loss

---

## ⚠️ RIGHT NOW (Next 15 minutes)

### 1. Secure HNTUSDT Position Manually

```
🚨 CRITICAL: Position at risk for 90+ minutes

Action Steps:
1. Open browser → https://www.bybit.com
2. Login to account
3. Navigate to: Derivatives → USDT Perpetual → Positions
4. Find: HNTUSDT position (60 units @ ~$1.75)
5. Click "Set SL/TP"
6. Set Stop Loss: $1.58 (2% below current $1.616)
7. Confirm order
8. Verify: SL order appears in "Conditional Orders"

⏱️ Time: 5 minutes
✅ Success: HNTUSDT has stop loss protection
```

### 2. Check Bot Status

```bash
# Is bot still running?
ps aux | grep "python.*main.py\|trading_bot" | grep -v grep

# If running and unfixed:
# Option A: Stop bot temporarily
kill -TERM <PID>

# Option B: Let run if manual SL set
# Monitor logs while implementing fix

⏱️ Time: 2 minutes
```

---

## 🔴 PHASE 1: Critical Fixes (Next 3-4 hours)

### Fix #1: Symbol Conversion (60 min)

**File**: `core/position_manager.py`

**Step 1**: Add conversion method (15 min)

```python
# Add near top of PositionManager class

def _convert_to_exchange_symbol(self, db_symbol: str, exchange_id: str) -> str:
    """
    Convert database symbol format to exchange-specific format

    Args:
        db_symbol: Symbol from database (e.g. "HNTUSDT")
        exchange_id: Exchange identifier ("bybit" or "binance")

    Returns:
        str: Exchange-specific symbol format

    Examples:
        >>> _convert_to_exchange_symbol("HNTUSDT", "bybit")
        'HNT/USDT:USDT'
        >>> _convert_to_exchange_symbol("BTCUSDT", "binance")
        'BTCUSDT'
    """
    if exchange_id == 'bybit':
        # Bybit perpetuals use CCXT unified format: BASE/QUOTE:SETTLE
        if db_symbol.endswith('USDT'):
            base_currency = db_symbol[:-4]  # Remove "USDT" suffix
            return f"{base_currency}/USDT:USDT"

        logger.warning(f"Unexpected Bybit symbol format: {db_symbol}")
        return db_symbol

    elif exchange_id == 'binance':
        # Binance Futures use same format as database
        return db_symbol

    else:
        # Unknown exchange - use as-is with warning
        logger.warning(
            f"Unknown exchange '{exchange_id}' for symbol {db_symbol}. "
            f"Using symbol as-is - may cause issues!"
        )
        return db_symbol
```

**Step 2**: Update ticker fetch (10 min)

Find line ~2689 in `core/position_manager.py`:

```python
# BEFORE (line ~2689) ❌
ticker = await exchange.fetch_ticker(position.symbol)

# AFTER ✅
exchange_symbol = self._convert_to_exchange_symbol(
    position.symbol,
    exchange.id  # Will be 'bybit' or 'binance'
)

logger.debug(f"Fetching ticker: {position.symbol} → {exchange_symbol}")
ticker = await exchange.fetch_ticker(exchange_symbol)
```

**Step 3**: Add unit test (20 min)

Create `tests/test_symbol_conversion.py`:

```python
import pytest
from core.position_manager import PositionManager

@pytest.fixture
def manager():
    # Create minimal PositionManager instance
    return PositionManager(config=mock_config)

def test_bybit_symbol_conversion(manager):
    """Test Bybit symbol format conversion"""
    assert manager._convert_to_exchange_symbol("HNTUSDT", "bybit") == "HNT/USDT:USDT"
    assert manager._convert_to_exchange_symbol("BTCUSDT", "bybit") == "BTC/USDT:USDT"
    assert manager._convert_to_exchange_symbol("ETHUSDT", "bybit") == "ETH/USDT:USDT"

def test_binance_symbol_unchanged(manager):
    """Test Binance symbols remain unchanged"""
    assert manager._convert_to_exchange_symbol("BTCUSDT", "binance") == "BTCUSDT"
    assert manager._convert_to_exchange_symbol("ETHUSDT", "binance") == "ETHUSDT"

def test_unknown_exchange(manager):
    """Test unknown exchange returns symbol as-is"""
    result = manager._convert_to_exchange_symbol("BTCUSDT", "unknown_exchange")
    assert result == "BTCUSDT"

# Run test
# pytest tests/test_symbol_conversion.py -v
```

**Step 4**: Test manually (15 min)

```bash
# Start Python REPL
python3

>>> from core.position_manager import PositionManager
>>> from config.settings import settings
>>>
>>> # Test conversion
>>> pm = PositionManager(settings)
>>> pm._convert_to_exchange_symbol("HNTUSDT", "bybit")
'HNT/USDT:USDT'
>>>
>>> # Good!
>>> exit()
```

---

### Fix #2: Price Sanity Validation (30 min)

**File**: `core/position_manager.py`

**Location**: After line ~2691 (after `current_price = float(...)`)

```python
# Existing code (line ~2691)
current_price = float(mark_price or ticker.get('last') or 0)

# ADD THIS VALIDATION ⬇️
if current_price == 0:
    logger.error(f"Failed to get current price for {position.symbol}, skipping SL setup")
    continue

# NEW: Sanity check for obviously wrong price
entry_price = float(position.entry_price)
price_drift_pct = abs((current_price - entry_price) / entry_price)

# Maximum reasonable drift in short timeframe
MAX_REASONABLE_DRIFT = 0.50  # 50%

if price_drift_pct > MAX_REASONABLE_DRIFT:
    logger.error(
        f"❌ {position.symbol}: Fetched price {current_price:.6f} differs "
        f"{price_drift_pct*100:.1f}% from entry {entry_price:.6f}. "
        f"This is likely a data error (wrong symbol used?). "
        f"Skipping SL setup for safety."
    )
    # Log for investigation
    logger.error(
        f"   Debug: DB symbol='{position.symbol}', "
        f"exchange symbol='{exchange_symbol}', "
        f"ticker symbol='{ticker.get('symbol')}'"
    )
    continue  # Skip this position - don't use bad data
```

---

### Fix #3: Safe SL Calculation (45 min)

**File**: `core/position_manager.py` or `core/stop_loss_manager.py`

**Step 1**: Add safe calculation method (30 min)

```python
def _calculate_safe_stop_loss(
    self,
    position_side: str,
    entry_price: float,
    current_market_price: float,
    sl_percent: float
) -> float:
    """
    Calculate stop loss that exchange will accept

    Key insight: Exchange validates SL against CURRENT price, not entry price.
    For LONG: SL must be < current market price
    For SHORT: SL must be > current market price

    Args:
        position_side: 'long' or 'short'
        entry_price: Original entry price
        current_market_price: Current market price on exchange
        sl_percent: Stop loss percentage (e.g. 2.0 for 2%)

    Returns:
        float: Stop loss price that exchange will accept

    Raises:
        ValueError: If unable to calculate valid SL
    """
    sl_decimal = sl_percent / 100  # Convert 2.0 → 0.02

    if position_side == 'long':
        # Try entry-based SL first (protects initial capital)
        sl_from_entry = entry_price * (1 - sl_decimal)

        # Check if price moved significantly since entry
        if sl_from_entry >= current_market_price:
            # Price dropped below entry → entry-based SL is now ABOVE market
            # Exchange will reject this!
            # Solution: Use current market price as base instead

            sl_final = current_market_price * (1 - sl_decimal)

            logger.warning(
                f"⚠️ Price moved down: entry={entry_price:.6f}, current={current_market_price:.6f}. "
                f"Entry-based SL ({sl_from_entry:.6f}) >= current market. "
                f"Using market-based SL: {sl_final:.6f}"
            )
        else:
            # Price stable or increased → entry-based SL is fine
            sl_final = sl_from_entry
            logger.debug(
                f"✓ Using entry-based SL: {sl_final:.6f} < current {current_market_price:.6f}"
            )

        # Final safety check
        if sl_final >= current_market_price:
            raise ValueError(
                f"LOGIC ERROR: Calculated SL {sl_final:.6f} >= current {current_market_price:.6f} "
                f"for LONG position. This should never happen!"
            )

        return sl_final

    else:  # short
        sl_from_entry = entry_price * (1 + sl_decimal)

        if sl_from_entry <= current_market_price:
            # Price rose above entry
            sl_final = current_market_price * (1 + sl_decimal)
            logger.warning(
                f"⚠️ Price moved up: entry={entry_price:.6f}, current={current_market_price:.6f}. "
                f"Using market-based SL: {sl_final:.6f}"
            )
        else:
            sl_final = sl_from_entry

        if sl_final <= current_market_price:
            raise ValueError(
                f"LOGIC ERROR: Calculated SL {sl_final:.6f} <= current {current_market_price:.6f} "
                f"for SHORT position"
            )

        return sl_final
```

**Step 2**: Replace existing calculation (15 min)

Find the existing SL calculation (around line 2728):

```python
# BEFORE ❌
stop_loss_price = calculate_stop_loss(
    entry_price=Decimal(str(base_price)),
    side=position.side,
    stop_loss_percent=Decimal(str(stop_loss_percent))
)

# AFTER ✅
try:
    stop_loss_float = self._calculate_safe_stop_loss(
        position_side=position.side,
        entry_price=entry_price,
        current_market_price=current_price,
        sl_percent=stop_loss_percent
    )
    stop_loss_price = Decimal(str(stop_loss_float))

except ValueError as e:
    logger.error(f"❌ Cannot calculate valid SL for {position.symbol}: {e}")
    continue  # Skip this position
```

---

### Testing Phase 1 Fixes (30 min)

**Step 1**: Unit tests (10 min)

```bash
# Run symbol conversion tests
pytest tests/test_symbol_conversion.py -v

# Should see:
# ✓ test_bybit_symbol_conversion PASSED
# ✓ test_binance_symbol_unchanged PASSED
```

**Step 2**: Run reproduction test (10 min)

```bash
# Run the forensic test
python tests/test_case_01_hntusdt_symbol_mismatch.py

# Expected output:
# ✓ Test 1: Lists HNT/USDT:USDT
# ✓ Test 2: HNTUSDT price
# ✓ Test 3: HNT/USDT:USDT price (should match)
# ✓ Test 4: Prices should be similar now!
```

**Step 3**: Manual verification (10 min)

```python
# Python REPL test
python3

>>> from core.position_manager import PositionManager
>>> from config.settings import settings
>>>
>>> pm = PositionManager(settings)
>>>
>>> # Test safe SL calculation
>>> # Scenario: LONG position, price dropped
>>> sl = pm._calculate_safe_stop_loss(
...     position_side='long',
...     entry_price=1.75,
...     current_market_price=1.60,  # Dropped 8.5%
...     sl_percent=2.0
... )
>>>
>>> print(f"SL: {sl}")
>>> # Should be ~1.568 (1.60 * 0.98)
>>> assert sl < 1.60, "SL must be below current market"
>>> print("✓ Test passed!")
```

---

### Deploy Phase 1 (30 min)

**Step 1**: Commit changes (5 min)

```bash
# Check what changed
git diff core/position_manager.py

# Stage changes
git add core/position_manager.py
git add tests/test_symbol_conversion.py

# Commit with descriptive message
git commit -m "fix(critical): CASE #1 - Fix symbol mismatch causing invalid SL

Root cause: Database symbols (HNTUSDT) used directly in exchange API calls.
Bybit requires CCXT format (HNT/USDT:USDT).

Fixes:
- Add _convert_to_exchange_symbol() for format conversion
- Add price sanity validation (reject >50% drift)
- Add _calculate_safe_stop_loss() respecting current market price

Impact:
- Prevents 300+ SL placement errors
- Ensures all positions get valid stop loss
- Eliminates 'position without SL' critical alerts

Refs: docs/forensic_analysis/CASE_01_HNTUSDT_NO_SL.md"

# Push
git push origin main
```

**Step 2**: Deploy (10 min)

```bash
# Stop bot (if running)
ps aux | grep trading_bot
kill -TERM <PID>

# Pull changes on production server
cd /path/to/TradingBot
git pull origin main

# Restart bot
python main.py &

# Or use your deployment process:
# ./deploy.sh
```

**Step 3**: Monitor (15 min)

```bash
# Watch logs in real-time
tail -f logs/trading_bot.log

# Look for:
# ✅ "Fetching ticker: HNTUSDT → HNT/USDT:USDT"  (conversion working)
# ✅ Current price values look reasonable (near entry, not 2x)
# ✅ "Stop loss set successfully"
# ❌ Should NOT see "Price drifted 88%"
# ❌ Should NOT see "Position without SL" CRITICAL alerts

# Monitor HNTUSDT specifically
grep "HNTUSDT" logs/trading_bot.log | tail -20

# Check for errors
grep "ERROR\|CRITICAL" logs/trading_bot.log | tail -20
```

---

## ✅ Success Criteria for Phase 1

After 30 minutes of monitoring, you should see:

```
✅ No "Position without SL" CRITICAL alerts
✅ Exchange symbols show correct format (HNT/USDT:USDT)
✅ Current prices are reasonable (not 2x entry)
✅ Stop losses set successfully
✅ No Bybit error 10001
✅ All new positions protected within 10 seconds

Database check:
✅ All active positions have stop_loss != NULL

Exchange check (Bybit dashboard):
✅ All positions show stop loss orders
```

---

## 🟠 PHASE 2: Additional Fixes (Next 24h)

**These are important but not immediately critical**

### Fix #4: Price Precision Validation (60 min)
- Add validation before sending SL to exchange
- Ensure price meets minimum precision
- Prevents WAVES/GIGA/ALEO type errors

### Fix #5: Position Verification (45 min)
- Improve "position not found" handling
- Better rollback logic
- Distinguish "never opened" vs "already closed"

### Fix #6: Pre-Flight Checks (90 min)
- Check margin before opening position
- Validate SL can be set
- Check position limits
- Prevents Binance error -2027

**Total Phase 2 time**: ~3 hours

---

## 🔧 Rollback Plan (If Something Goes Wrong)

```bash
# Quick rollback
cd /path/to/TradingBot

# Revert last commit
git revert HEAD
git push origin main

# Redeploy
kill <bot_pid>
git pull
python main.py &

# Time to rollback: <5 minutes
```

---

## 📊 Monitoring Checklist (First 24h)

```
Hour 1:
□ No CRITICAL "position without SL" alerts
□ SL placement success rate > 95%
□ Prices look reasonable in logs

Hour 4:
□ Zero symbol mismatch errors
□ All positions have SL in database
□ No Bybit error 10001

Hour 24:
□ 100% position protection rate
□ Zero precision errors
□ Signal execution success > 95%
```

---

## 📞 Emergency Contacts

If you see unexpected behavior:

1. **Stop the bot immediately**:
   ```bash
   kill -TERM <bot_pid>
   ```

2. **Check open positions on exchange**:
   - Login to Bybit/Binance
   - Manually set SL for any unprotected positions

3. **Rollback code** (see Rollback Plan above)

4. **Review logs**:
   ```bash
   grep "ERROR\|CRITICAL" logs/trading_bot.log > /tmp/errors.txt
   ```

---

## 📝 Quick Reference

### Key Files
```
core/position_manager.py           (main fixes here)
tests/test_symbol_conversion.py    (unit tests)
docs/forensic_analysis/            (all reports)
```

### Key Commands
```bash
# Check bot status
ps aux | grep trading_bot

# Watch logs
tail -f logs/trading_bot.log | grep "HNTUSDT\|CRITICAL\|ERROR"

# Check database
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto \
  -c "SELECT symbol, stop_loss, status FROM monitoring.positions WHERE status='active';"

# Run tests
pytest tests/test_symbol_conversion.py -v
python tests/test_case_01_hntusdt_symbol_mismatch.py
```

---

**GOOD LUCK! 🚀**

Remember:
1. Manual SL for HNTUSDT first (5 min) ⚠️
2. Implement fixes (3-4 hours)
3. Test thoroughly (30 min)
4. Deploy and monitor (30 min)
5. Verify success (24h)

**Estimated total time: 4-6 hours**

---

*Generated: 2025-10-22*
*Status: Ready for execution*
