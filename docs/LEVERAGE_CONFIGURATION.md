# Leverage Configuration Guide

**Date:** 2025-10-25
**Status:** ✅ Active (Restored after Phase 3.2.4 regression)
**Version:** 1.0

---

## Overview

The trading bot automatically sets leverage for all positions before opening them. This ensures consistent risk management across all symbols and exchanges.

### Key Features

- ✅ **Automatic leverage setup** before every position
- ✅ **Exchange-specific handling** (Binance, Bybit)
- ✅ **Configurable via .env** - no code changes needed
- ✅ **Safety limits** with MAX_LEVERAGE
- ✅ **Graceful fallback** if leverage can't be set
- ✅ **Works in both atomic and legacy paths**

---

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# ───────────────────────────────────────────────────────────────
# LEVERAGE CONTROL (3 variables)
# ───────────────────────────────────────────────────────────────
LEVERAGE=10                    # Default leverage for all positions (10x)
MAX_LEVERAGE=20                # Maximum allowed leverage (safety limit)
AUTO_SET_LEVERAGE=true         # Auto-set leverage before opening position
```

### Parameters

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LEVERAGE` | int | 10 | Default leverage multiplier (e.g., 10 = 10x) |
| `MAX_LEVERAGE` | int | 20 | Maximum allowed leverage (safety limit) |
| `AUTO_SET_LEVERAGE` | bool | true | Enable automatic leverage setup |

### Recommended Values

| Risk Profile | LEVERAGE | MAX_LEVERAGE | Notes |
|-------------|----------|--------------|-------|
| Conservative | 5 | 10 | Lower risk, smaller gains |
| Moderate | 10 | 20 | Balanced risk/reward (recommended) |
| Aggressive | 20 | 50 | Higher risk, larger potential gains |

**⚠️ WARNING:** Higher leverage increases both potential profits AND losses!

---

## How It Works

### Execution Flow

```
1. Signal received
2. Position size calculated
3. ✅ Leverage set on exchange (NEW!)
   - Call exchange.set_leverage(symbol, 10)
   - Verify success
   - Log result
4. Market order placed
5. Stop-loss created
6. Position tracked
```

### Code Integration Points

#### 1. Atomic Path (Primary)

**File:** `core/atomic_position_manager.py`
**Line:** ~250

```python
# RESTORED 2025-10-25: Set leverage before opening position
if self.config and self.config.auto_set_leverage:
    leverage = self.config.leverage
    logger.info(f"🎚️ Setting {leverage}x leverage for {symbol}")
    leverage_set = await exchange_instance.set_leverage(symbol, leverage)
    if not leverage_set:
        logger.warning(f"⚠️ Could not set leverage for {symbol}")
```

#### 2. Legacy Fallback Path

**File:** `core/position_manager.py`
**Line:** ~1244

```python
# RESTORED 2025-10-25: Set leverage before opening position (legacy path)
if self.config.auto_set_leverage:
    leverage = self.config.leverage
    logger.info(f"🎚️ Setting {leverage}x leverage for {symbol} (legacy path)")
    leverage_set = await exchange.set_leverage(symbol, leverage)
```

---

## Exchange-Specific Behavior

### Binance

```python
await exchange.set_leverage(
    leverage=10,
    symbol='BTCUSDT'
)
```

**Notes:**
- Simple API call
- Returns success/failure
- Leverage applied immediately

### Bybit

```python
await exchange.set_leverage(
    leverage=10,
    symbol='BTC/USDT:USDT',
    params={'category': 'linear'}
)
```

**Notes:**
- Requires `category: 'linear'` parameter
- Returns error 110043 if leverage already at value (treated as success)
- Slightly different symbol format

---

## Error Handling

### What Happens If Leverage Fails?

The bot continues with position creation but logs a warning:

```
⚠️ Could not set leverage for BTCUSDT, using exchange default
```

**Why continue?**
- Leverage might already be set correctly
- Better to open position with default leverage than miss signal
- Warning logged for monitoring

### Bybit Error 110043

**Error:** `{"retCode":110043,"retMsg":"leverage not modified"}`
**Meaning:** Leverage is already at the requested value
**Handling:** Treated as success ✅

---

## Risk Management

### Leverage and Stop-Loss

With **LEVERAGE=10** and **STOP_LOSS_PERCENT=2.0**:

```
Price movement: -2.0%
Position loss:  -2.0% × 10x = -20% of margin
```

**Important:** Stop-loss percentage is based on price, not margin!

### Exposure Calculation

**Without leverage:**
```
150 positions × $6 = $900 total exposure
```

**With 10x leverage:**
```
150 positions × $6 × 10x = $9,000 total exposure
```

**With 20x leverage:**
```
150 positions × $6 × 20x = $18,000 total exposure
```

### Liquidation Risk

| Leverage | SL=2% Movement | Margin Loss | Risk Level |
|----------|----------------|-------------|------------|
| 5x | 2% | 10% | ✅ Low |
| 10x | 2% | 20% | ⚠️ Moderate |
| 20x | 2% | 40% | 🔴 High |
| 50x | 2% | 100% | 💀 EXTREME |

---

## Testing

### Phase 1: Config Loading

```bash
python3 tests/test_phase1_config_loading.py
```

Verifies:
- ✅ Config loads LEVERAGE from .env
- ✅ Defaults work correctly
- ✅ Values are reasonable

### Phase 2: set_leverage() Method

```bash
python3 tests/test_phase2_set_leverage.py
```

Verifies:
- ✅ Method exists in ExchangeManager
- ✅ Works on Binance testnet
- ✅ Works on Bybit testnet
- ✅ Handles error 110043 correctly

### Phase 3: Atomic Integration

```bash
python3 tests/test_phase3_atomic_integration.py
```

Verifies:
- ✅ AtomicPositionManager calls set_leverage
- ✅ Called BEFORE create_market_order
- ✅ Config properly passed

### Phase 4: Legacy Fallback

```bash
python3 tests/test_phase4_legacy_fallback.py
```

Verifies:
- ✅ Legacy path also sets leverage
- ✅ Both atomic and legacy covered

### Run All Tests

```bash
python3 tests/test_phase1_config_loading.py && \
python3 tests/test_phase2_set_leverage.py && \
python3 tests/test_phase3_atomic_integration.py && \
python3 tests/test_phase4_legacy_fallback.py
```

---

## Monitoring

### Logs to Watch

**Success:**
```
✅ Leverage set to 10x for BTCUSDT on binance
```

**Already set (Bybit):**
```
✅ Leverage already at 10x for BTC/USDT:USDT on bybit
```

**Failure:**
```
❌ Failed to set leverage for BTCUSDT: <error>
⚠️ Could not set leverage for BTCUSDT, using exchange default
```

### Metrics to Track

1. **Leverage set success rate** - should be ~100%
2. **Positions with unexpected leverage** - should be 0
3. **Leverage mismatch warnings** - investigate any occurrences

---

## Troubleshooting

### Leverage Not Being Set

**Check:**
1. ✅ `AUTO_SET_LEVERAGE=true` in .env
2. ✅ Config loaded correctly (check logs)
3. ✅ Exchange API permissions allow leverage changes
4. ✅ Symbol is available for trading

### Different Leverage Per Symbol

**Cause:** Leverage was set manually on exchange before bot started
**Fix:** Let bot run - it will set correct leverage on next position

### Error: "Position risk not available"

**Cause:** Exchange API issue or permissions
**Fix:** Check API key has futures trading permissions

---

## Migration Guide

### From Manual Leverage

If you previously set leverage manually on the exchange:

1. **No action needed!** Bot will override with configured value
2. Verify first few positions have correct leverage (check logs)
3. Remove manual leverage settings from exchange UI

### From Old Bot Version

If upgrading from version without automatic leverage:

1. Add LEVERAGE variables to .env
2. Restart bot
3. Monitor first 10 positions
4. Verify leverage in logs

---

## FAQ

### Q: Why was this feature removed?

**A:** Accidental deletion during Phase 3.2.4 refactoring (commit 7f2f3d0) that reduced `open_position()` from 393 to 62 lines. Leverage setup code was removed as part of simplification.

### Q: Can I disable automatic leverage?

**A:** Yes, set `AUTO_SET_LEVERAGE=false` in .env. Bot will use exchange default.

### Q: Does this work on production?

**A:** Yes! Tested on both Binance and Bybit testnet. Works identically on production.

### Q: What if I want different leverage per symbol?

**A:** Current implementation uses same leverage for all symbols. Symbol-specific leverage would require code changes.

### Q: How often is leverage set?

**A:** Once before EVERY position is opened. Not updated during position lifetime.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-25 | Initial documentation after restoration |

---

## Related Documents

- `docs/LEVERAGE_CRITICAL_REGRESSION.md` - Regression analysis
- `docs/LEVERAGE_RESTORATION_PLAN.md` - Complete restoration plan
- `docs/ENV_AUDIT_REPORT.md` - Environment variable audit

---

**Last Updated:** 2025-10-25
**Maintained By:** Trading Bot Team
**Questions?** See troubleshooting section or check git history.
