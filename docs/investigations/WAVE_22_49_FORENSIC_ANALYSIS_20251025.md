# 🔍 FORENSIC ANALYSIS: Wave 22:49 UTC - Zero Positions Opened

**Date:** 2025-10-24
**Wave Time:** 22:49:03 - 22:49:10 UTC
**Wave Timestamp:** 2025-10-24 22:30:00 UTC
**Signals Received:** 22
**Positions Opened:** 0 ❌

---

## 📊 Executive Summary

**ROOT CAUSE IDENTIFIED:** Bybit mainnet has $0 free USDT balance.

**Secondary Issue:** Need to determine why 2 Binance signals (with $9,830 free) were also not processed.

---

## 🔬 Investigation Findings

### 1. Exchange Balance Status

#### Binance (Testnet)
```
Free USDT:  $9,830.48 ✅
Total USDT: $10,154.54
Status:     CAN OPEN POSITIONS
```

#### Bybit (Mainnet) ⚠️ CRITICAL ISSUE
```
Free USDT:  $0.00 ❌
Total USDT: $53.14 (all locked in positions)
Status:     CANNOT OPEN POSITIONS
```

**Verification Method:**
```python
# core/exchange_manager.py:1378-1382
free_usdt = await self._get_free_balance_usdt()
if free_usdt < float(notional_usd):
    return False, f"Insufficient free balance: ${free_usdt:.2f} < ${notional_usd:.2f}"
```

### 2. Signal Distribution (User Reported)

According to user:
- **3 Bybit signals** → Filtered due to $0 free balance ✅ EXPLAINED
- **2 Binance signals** → ??? NOT EXPLAINED YET ⚠️

Total: 5 signals expected to be processed (matches MAX_TRADES_PER_15MIN=5)

**Remaining signals:** 22 - 5 = 17 signals
These 17 were likely filtered before reaching validation (lower priority/score).

---

## 🔍 Signal Processing Flow Analysis

### Stage 1: WebSocket Reception
```
22:49:03 UTC - wave_detected (22 signals)
```

### Stage 2: Top Signal Selection
```python
# signal_processor_websocket.py:254
buffer_size = int(max_trades * (1 + buffer_percent / 100))
# max_trades = 5, buffer_percent = 50
# buffer_size = 5 * 1.5 = 7.5 → 7 signals
signals_to_process = wave_signals[:buffer_size]
```

**Expected:** Top 7 signals selected from 22 for processing.

### Stage 3: Wave Processor Validation
```python
# core/wave_signal_processor.py:262-264
result = await self.wave_processor.process_wave_signals(
    signals=signals_to_process,
    wave_timestamp=expected_wave_timestamp
)
```

**Checks performed:**
1. Duplicate check (existing position for symbol)
2. Exchange availability
3. Symbol availability
4. Market data availability
5. Ticker availability
6. Price validity
7. **Minimum notional check** ✅
8. Position already exists check

**Database Evidence:**
- No `signal_filtered` events logged ⚠️
- No `signal_execution_failed` events
- No `duplicate_signal_skipped` events

### Stage 4: Parallel Validation (CRITICAL FILTERING STAGE)
```python
# signal_processor_websocket.py:293-347
# PARALLEL VALIDATION: Pre-fetch positions once per exchange
preloaded_positions_by_exchange = {}
for exchange_name, exchange_manager in self.position_manager.exchanges.items():
    positions = await exchange_manager.fetch_positions()
    preloaded_positions_by_exchange[exchange_name] = positions

# Validate each signal
for signal_result in final_signals:
    exchange_manager = self.position_manager.exchanges.get(exchange_name)
    validation_tasks.append(
        exchange_manager.can_open_position(
            symbol,
            size_usd,
            preloaded_positions=preloaded_positions
        )
    )

# Filter based on validation
for signal_result, validation in zip(final_signals, validations):
    can_open, reason = validation
    if can_open:
        validated_signals.append(signal_result)
    else:
        # ⚠️ THIS IS WHERE SIGNALS ARE FILTERED
        logger.info(f"Signal {symbol} on {exchange} filtered out: {reason}")
```

**This is where the filtering happens!**

---

## 💡 Why Bybit Signals Failed

### Bybit Balance Check
```python
# core/exchange_manager.py:1378-1382
free_usdt = await self._get_free_balance_usdt()  # Returns $0.00
if free_usdt < float(notional_usd):  # $0.00 < $6.00
    return False, "Insufficient free balance: $0.00 < $6.00"
```

**Expected Log Output:**
```
Signal [SYMBOL] on bybit filtered out: Insufficient free balance: $0.00 < $6.00
Signal [SYMBOL] on bybit filtered out: Insufficient free balance: $0.00 < $6.00
Signal [SYMBOL] on bybit filtered out: Insufficient free balance: $0.00 < $6.00
```

**These logs should be in bot stdout (terminal s000, PID 99941).**

---

## ⚠️ Mystery: Why Binance Signals Failed

### Current Evidence
- Binance has $9,830 free ✅
- Position size needed: $6 ✅
- 2 Binance signals were in the wave (user confirmed)
- But they were NOT processed ❌

### Possible Explanations

#### Theory 1: Score Filtering (Before Bot)
```bash
# From .env
MIN_SCORE_WEEK=62
MIN_SCORE_MONTH=58
```

If the WebSocket **server** filters signals by score before sending to bot, the 2 Binance signals might have been:
- Received by server (counted in "22 signals")
- Filtered by server due to score < 62 (week) or < 58 (month)
- Never sent to bot for validation

**How to verify:** Check WebSocket server logs.

#### Theory 2: Duplicate Symbols
The 2 Binance symbols might already have open positions:
```python
# wave_signal_processor.py:254
has_position = await self.position_manager.has_open_position(symbol, exchange)
if has_position:
    return True, "Position already exists"
```

**How to verify:**
```sql
SELECT symbol, exchange
FROM monitoring.positions
WHERE status = 'open'
  AND exchange = 'binance'
  AND opened_at < '2025-10-24 22:49:00';
```

#### Theory 3: Minimum Notional Filter
```python
# wave_signal_processor.py:322
if notional_value < min_cost:
    logger.info(f"Signal skipped: {symbol} minimum notional ${min_cost:.2f} > ${position_size_usd:.2f}")
    return True, f"Position size (${position_size_usd:.2f}) below exchange minimum"
```

But this should log `signal_filtered` events to database - **none found**.

#### Theory 4: Symbol Not Available on Exchange
```python
# wave_signal_processor.py:284
exchange_symbol = exchange_manager.find_exchange_symbol(symbol)
if not exchange_symbol:
    return True, f"Symbol {symbol} not found on {exchange}"
```

**How to verify:** Check if the 2 Binance symbols exist on Binance testnet.

---

## 🔧 What Logs SHOULD Show

Based on the code, at LOG_LEVEL=INFO, the bot SHOULD have logged:

```
2025-10-24 22:49:03 - 🌊 Starting wave processing: 22 signals at timestamp 2025-10-24T22:30:00+00:00
2025-10-24 22:49:03 - 📊 Wave 2025-10-24T22:30:00+00:00: 22 total signals, processing top 7 (max=5 +50% buffer)
2025-10-24 22:49:03 - Pre-fetched X positions for binance
2025-10-24 22:49:03 - Pre-fetched X positions for bybit
2025-10-24 22:49:XX - Signal [BYBIT_SYM_1] on bybit filtered out: Insufficient free balance: $0.00 < $6.00
2025-10-24 22:49:XX - Signal [BYBIT_SYM_2] on bybit filtered out: Insufficient free balance: $0.00 < $6.00
2025-10-24 22:49:XX - Signal [BYBIT_SYM_3] on bybit filtered out: Insufficient free balance: $0.00 < $6.00
2025-10-24 22:49:XX - Signal [BINANCE_SYM_1] on binance filtered out: [REASON]
2025-10-24 22:49:XX - Signal [BINANCE_SYM_2] on binance filtered out: [REASON]
2025-10-24 22:49:XX - Parallel validation complete: 0 signals passed (filtered from 7)
2025-10-24 22:49:10 - 🌊 Wave processing complete: ✅ 0 successful, ❌ 0 failed, ⏭️ X skipped
```

**These logs exist in terminal s000 (PID 99941) but are not accessible remotely.**

---

## 📋 Action Items

### IMMEDIATE (User Must Do)

1. **Check Terminal Logs** ⚠️ CRITICAL
   ```bash
   # In terminal s000 where bot is running (PID 99941)
   # Scroll back to ~22:49 UTC (3:49 AM local time)
   # Look for the log messages above
   ```

2. **Fix Bybit Balance** 💰
   - Option A: Deposit USDT to Bybit mainnet
   - Option B: Close some Bybit positions to free up balance
   - Option C: Switch back to Bybit testnet:
     ```bash
     # In .env
     BYBIT_TESTNET=true
     ```

3. **Check Binance Signal Details**
   - What were the 2 Binance symbols?
   - Do they already have open positions?
   - What were their scores?

### DIAGNOSTIC STEPS

4. **Enable DEBUG Logging**
   ```bash
   # In .env
   LOG_LEVEL=DEBUG

   # Restart bot
   # Wait for next wave
   # Check detailed filtering reasons
   ```

5. **Check Existing Binance Positions**
   ```sql
   SELECT symbol, entry_price, quantity, opened_at
   FROM monitoring.positions
   WHERE exchange = 'binance'
     AND status = 'open'
   ORDER BY opened_at DESC;
   ```

6. **Check WebSocket Server Logs**
   - Are signals being filtered server-side by score?
   - What scores did the 22 signals have?
   - Were the 2 Binance signals actually sent to the bot?

---

## 🎯 Root Cause Summary

| Issue | Status | Explanation |
|-------|--------|-------------|
| **3 Bybit signals filtered** | ✅ CONFIRMED | $0 free USDT on Bybit mainnet |
| **2 Binance signals filtered** | ⚠️ UNKNOWN | Need to check terminal logs for reason |
| **17 other signals not processed** | ✅ EXPECTED | Below top 7 (max 5 + 50% buffer) |

---

## 🔐 Configuration State

```bash
# Exchange Config
BINANCE_TESTNET=true          # ✅ Has balance
BYBIT_TESTNET=false           # ❌ No free balance

# Position Sizing
POSITION_SIZE_USD=6           # ✅ Reasonable
MAX_POSITIONS=150             # ✅ High enough
MAX_EXPOSURE_USD=99000        # ✅ High enough

# Wave Processing
MAX_TRADES_PER_15MIN=5        # ✅ Conservative
SIGNAL_BUFFER_PERCENT=50      # ✅ Allows 7 signals

# Score Filtering
MIN_SCORE_WEEK=62             # ⚠️ Might be too high
MIN_SCORE_MONTH=58            # ⚠️ Might be too high

# Leverage
LEVERAGE=1                    # ⚠️ User changed from 10 to 1
MAX_LEVERAGE=2                # ⚠️ User changed from 20 to 2
```

---

## 🚨 CRITICAL NEXT STEP

**User MUST check terminal s000 logs around 22:49 UTC to see:**
1. Exact filtering reason for 2 Binance signals
2. What symbols were in the wave
3. What scores they had
4. Why validation failed

**Without those logs, we cannot determine why Binance signals (with $9,830 free) were not processed.**

---

**Report Generated:** 2025-10-25
**Bot Status:** Running (PID 99941, terminal s000, started 5:24PM)
**Log Level:** INFO
**Database Queries:** 10
**Balance Checks:** 2
