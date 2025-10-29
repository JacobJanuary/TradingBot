# 🔍 ENVIRONMENT VARIABLES AUDIT REPORT

**Audit Date**: 2025-10-24
**Project**: Trading Bot
**Auditor**: Claude Code

---

## 📊 EXECUTIVE SUMMARY

**Total variables in .env**: 97
**Total variables used in code**: 60
**Unused/obsolete variables**: 37 (38%)
**Missing from .env.example**: ~70 variables

**Recommendation**: Clean up .env by removing 37 unused variables and update .env.example

---

## ✅ VARIABLES CURRENTLY IN USE (60)

### 1. Database Configuration (7 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `DB_HOST` | config/settings.py, database/* | ✅ Active |
| `DB_PORT` | config/settings.py, database/* | ✅ Active |
| `DB_NAME` | config/settings.py, database/* | ✅ Active |
| `DB_USER` | config/settings.py, database/* | ✅ Active |
| `DB_PASSWORD` | config/settings.py, database/* | ✅ Active |
| `DB_POOL_SIZE` | config/settings.py | ✅ Active |
| `DB_MAX_OVERFLOW` | config/settings.py | ✅ Active |

**Note**: `DATABASE_URL` is used in some migration scripts but NOT in main code.

### 2. Exchange API Keys (6 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `BINANCE_API_KEY` | main.py, config/settings.py, tools/* | ✅ Active |
| `BINANCE_API_SECRET` | main.py, config/settings.py, tools/* | ✅ Active |
| `BINANCE_TESTNET` | config/settings.py, tools/* | ✅ Active |
| `BYBIT_API_KEY` | main.py, config/settings.py, tools/* | ✅ Active |
| `BYBIT_API_SECRET` | main.py, config/settings.py, tools/* | ✅ Active |
| `BYBIT_TESTNET` | config/settings.py, tools/* | ✅ Active |

### 3. Position Sizing (5 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `POSITION_SIZE_USD` | config/settings.py | ✅ Active |
| `MIN_POSITION_SIZE_USD` | config/settings.py, core/position_manager.py | ✅ Active |
| `MAX_POSITION_SIZE_USD` | config/settings.py, core/position_manager.py | ✅ Active |
| `MAX_POSITIONS` | config/settings.py | ✅ Active |
| `MAX_EXPOSURE_USD` | config/settings.py | ✅ Active (duplicated line 24 & 70!) |

**⚠️ WARNING**: `MAX_EXPOSURE_USD` defined TWICE in .env (lines 24 and 70)!

### 4. Risk Management - Trailing Stop (6 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `STOP_LOSS_PERCENT` | config/settings.py | ✅ Active |
| `TRAILING_ACTIVATION_PERCENT` | config/settings.py | ✅ Active |
| `TRAILING_CALLBACK_PERCENT` | config/settings.py | ✅ Active |
| `TRAILING_MIN_UPDATE_INTERVAL_SECONDS` | config/settings.py | ✅ Active |
| `TRAILING_MIN_IMPROVEMENT_PERCENT` | config/settings.py | ✅ Active |
| `TRAILING_ALERT_IF_UNPROTECTED_WINDOW_MS` | config/settings.py | ✅ Active |

### 5. Aged Position System (6 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `MAX_POSITION_AGE_HOURS` | config/settings.py, core/aged_*.py | ✅ Active (duplicated line 32 & 193!) |
| `AGED_GRACE_PERIOD_HOURS` | config/settings.py, core/aged_*.py | ✅ Active |
| `AGED_LOSS_STEP_PERCENT` | config/settings.py, core/aged_*.py | ✅ Active |
| `AGED_MAX_LOSS_PERCENT` | config/settings.py, core/aged_*.py | ✅ Active |
| `AGED_ACCELERATION_FACTOR` | config/settings.py, core/aged_*.py | ✅ Active |
| `COMMISSION_PERCENT` | config/settings.py, core/aged_*.py | ✅ Active |

**⚠️ WARNING**: `MAX_POSITION_AGE_HOURS` defined TWICE in .env (lines 32 and 193)!

**ℹ️ NOTE**: `AGED_CHECK_INTERVAL_MINUTES` defined in .env but NOT loaded in config/settings.py!

### 6. Signal Filtering (4 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `MIN_SCORE_WEEK` | config/settings.py | ✅ Active |
| `MIN_SCORE_MONTH` | config/settings.py | ✅ Active |
| `MAX_SPREAD_PERCENT` | config/settings.py | ✅ Active |
| `STOPLIST_SYMBOLS` | config/settings.py | ✅ Active |

### 7. Wave Processing (5 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `WAVE_CHECK_MINUTES` | core/signal_processor_websocket.py | ✅ Active |
| `WAVE_CHECK_DURATION_SECONDS` | core/signal_processor_websocket.py | ✅ Active |
| `WAVE_CHECK_INTERVAL_SECONDS` | core/signal_processor_websocket.py | ✅ Active |
| `SIGNAL_BUFFER_PERCENT` | config/settings.py | ✅ Active |
| `MAX_TRADES_PER_15MIN` | config/settings.py | ✅ Active |

### 8. Rate Limiting (6 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `BINANCE_RATE_LIMIT_PER_SEC` | core/exchange_manager.py | ✅ Active |
| `BINANCE_RATE_LIMIT_PER_MIN` | core/exchange_manager.py | ✅ Active |
| `BYBIT_RATE_LIMIT_PER_SEC` | core/exchange_manager.py | ✅ Active |
| `BYBIT_RATE_LIMIT_PER_MIN` | core/exchange_manager.py | ✅ Active |
| `DEFAULT_RATE_LIMIT_PER_SEC` | core/exchange_manager.py | ✅ Active |
| `DEFAULT_RATE_LIMIT_PER_MIN` | core/exchange_manager.py | ✅ Active |

### 9. WebSocket Signal Server (6 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `SIGNAL_WS_URL` | core/signal_processor_websocket.py | ✅ Active |
| `SIGNAL_WS_TOKEN` | core/signal_processor_websocket.py | ✅ Active |
| `SIGNAL_WS_RECONNECT_INTERVAL` | core/signal_processor_websocket.py | ✅ Active |
| `SIGNAL_WS_AUTO_RECONNECT` | core/signal_processor_websocket.py | ✅ Active |
| `SIGNAL_WS_MAX_RECONNECT_ATTEMPTS` | core/signal_processor_websocket.py | ✅ Active |
| `SIGNAL_BUFFER_SIZE` | core/signal_processor_websocket.py | ✅ Active |

### 10. System Configuration (3 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `ENVIRONMENT` | config/settings.py, main.py | ✅ Active |
| `LOG_LEVEL` | config/settings.py, main.py | ✅ Active |
| `DEBUG` | config/settings.py | ✅ Active |

### 11. Unified Protection (1 variable)
| Variable | Used In | Status |
|----------|---------|--------|
| `USE_UNIFIED_PROTECTION` | main.py, core/position_manager_unified_patch.py | ✅ Active |

### 12. Encryption (2 variables)
| Variable | Used In | Status |
|----------|---------|--------|
| `MASTER_KEY` | utils/crypto_manager.py | ✅ Active |
| `USERNAME` | utils/crypto_manager.py | ✅ Active |

---

## ❌ UNUSED VARIABLES (37) - МОЖНО УДАЛИТЬ

### 1. Monitoring/Metrics (3 variables) - NOT USED
```bash
PROMETHEUS_PORT=8000          # ❌ NO prometheus integration in code
HEALTH_CHECK_PORT=8080        # ❌ NOT used
METRICS_ENABLED=true          # ❌ NOT checked anywhere
```

**Reason**: Code has health monitoring system but doesn't use these specific variables.

### 2. Health Check Configuration (11 variables) - NOT USED
```bash
HEALTH_CHECK_ENABLED=true                # ❌ NOT checked in code
HEALTH_CHECK_INTERVAL=60                 # ❌ NOT used
CRITICAL_CHECK_INTERVAL=10               # ❌ NOT used
MAX_RESPONSE_TIME_MS=1000                # ❌ NOT used
MAX_ERROR_COUNT=3                        # ❌ NOT used
DEGRADED_THRESHOLD=0.8                   # ❌ NOT used
HEALTH_ALERT_ENABLED=true                # ❌ NOT used
MIN_BALANCE_ALERT=100                    # ❌ NOT used
MAX_MEMORY_MB=1000                       # ❌ NOT used
MAX_POSITION_AGE_ALERT=48                # ❌ NOT used
AUTO_RECOVERY_ENABLED=true               # ❌ NOT used
MAX_RECOVERY_ATTEMPTS=3                  # ❌ NOT used
```

**Reason**: Health monitoring system exists but uses hardcoded values, not these env vars.

### 3. Emergency Liquidation System (18 variables) - NOT USED
```bash
EMERGENCY_LIQUIDATION_ENABLED=false              # ❌ NOT checked
EMERGENCY_BALANCE_DROP_THRESHOLD=50              # ❌ NOT used
EMERGENCY_BALANCE_TIME_WINDOW=10                 # ❌ NOT used
EMERGENCY_BALANCE_PEAK_LOOKBACK=60               # ❌ NOT used
EMERGENCY_UNREALIZED_LOSS_THRESHOLD=80           # ❌ NOT used
EMERGENCY_EXPOSURE_MULTIPLIER=2.0                # ❌ NOT used
EMERGENCY_CASCADE_THRESHOLD=10                   # ❌ NOT used
EMERGENCY_CASCADE_WINDOW=5                       # ❌ NOT used
EMERGENCY_API_FAILURE_THRESHOLD=20               # ❌ NOT used
EMERGENCY_CONFIRMATION_CHECKS=3                  # ❌ NOT used
EMERGENCY_COOLDOWN_MEDIUM=3600                   # ❌ NOT used
EMERGENCY_COOLDOWN_HIGH=7200                     # ❌ NOT used
EMERGENCY_COOLDOWN_CRITICAL=14400                # ❌ NOT used
EMERGENCY_MANUAL_REQUIRE_CONFIRMATION=true       # ❌ NOT used
EMERGENCY_MANUAL_GRACE_PERIOD=30                 # ❌ NOT used
EMERGENCY_ALERT_TELEGRAM=false                   # ❌ NOT used
EMERGENCY_ALERT_EMAIL=false                      # ❌ NOT used
EMERGENCY_ALERT_WEBHOOK=false                    # ❌ NOT used
EMERGENCY_ALERT_SMS=false                        # ❌ NOT used
```

**Reason**: Emergency liquidation system commented as "DISABLED for safety" and not implemented.

### 4. Symbol Filtering (5 variables) - NOT USED IN config/settings.py
```bash
USE_SYMBOL_WHITELIST=false    # ❌ Defined but NOT loaded in config/settings.py
WHITELIST_SYMBOLS=            # ❌ Defined but NOT loaded
EXCLUDED_PATTERNS=*UP,*DOWN,*BEAR,*BULL,*3S,*3L,*2S,*2L  # ❌ NOT loaded
MIN_SYMBOL_VOLUME_USD=0       # ❌ NOT loaded
DELISTED_SYMBOLS=LUNAUSDT,USTUSDT,FTMUSDT  # ❌ NOT loaded
```

**Reason**: Variables exist in .env but config/settings.py doesn't load them. May be used directly elsewhere.

### 5. Other Unused Variables
```bash
MAX_COOL_DOWN_LIMIT=8         # ❌ NOT found in code
TEST_MODE=false               # ❌ NOT checked anywhere
SIGNAL_TIME_WINDOW_MINUTES=30 # ❌ Defined but NOT used (was in old code?)
LEVERAGE=10                   # ❌ NOT used (leverage set per-exchange in code)
WAVE_CLEANUP_HOURS=2          # ❌ NOT used
USE_WEBSOCKET_SIGNALS=true    # ❌ NOT checked (bot always uses WebSocket now)
DUPLICATE_CHECK_ENABLED=true  # ❌ NOT used
ALLOW_MULTIPLE_POSITIONS=false  # ❌ NOT used
```

---

## 🔴 CRITICAL ISSUES FOUND

### 1. Duplicate Variable Definitions ⚠️

**`MAX_EXPOSURE_USD`** defined TWICE:
- Line 24: `MAX_EXPOSURE_USD=300000`
- Line 70: `MAX_EXPOSURE_USD=30000`

**`MAX_POSITION_AGE_HOURS`** defined TWICE:
- Line 32: `MAX_POSITION_AGE_HOURS=3`
- Line 193: `MAX_POSITION_AGE_HOURS=3`

**Action Required**: Remove duplicates, keep only one definition!

### 2. .env.example is SEVERELY OUTDATED ⚠️

**.env.example has only 45 variables, but .env has 97!**

Missing from .env.example:
- All aged position variables
- All trailing stop variables
- All wave processing variables
- All rate limiting variables
- All WebSocket signal variables
- All emergency liquidation variables
- All health check variables

**Action Required**: Completely rewrite .env.example based on current .env

### 3. Variables in .env.example but NOT in .env ⚠️

```bash
# From .env.example but MISSING in .env:
DATABASE_URL=postgresql://...           # ❌ Not in .env (uses separate DB_* vars)
DISCORD_WEBHOOK_URL=...                 # ❌ Not in .env
TELEGRAM_BOT_TOKEN=...                  # ❌ Not in .env
TELEGRAM_CHAT_ID=...                    # ❌ Not in .env
REPORT_INTERVAL=daily                   # ❌ Not in .env
BENCHMARK_SYMBOL=BTC/USDT               # ❌ Not in .env
API_RATE_LIMIT=100                      # ❌ Not in .env
API_RATE_PERIOD=60                      # ❌ Not in .env
MAX_RETRIES=3                           # ❌ Not in .env
RETRY_DELAY=60                          # ❌ Not in .env
BACKUP_ENABLED=false                    # ❌ Not in .env
BACKUP_S3_BUCKET=...                    # ❌ Not in .env
AWS_ACCESS_KEY_ID=...                   # ❌ Not in .env
AWS_SECRET_ACCESS_KEY=...               # ❌ Not in .env
```

**These are obsolete** - were probably used in earlier version.

### 4. Variables NOT Loaded by config/settings.py

These variables exist in .env but config/settings.py doesn't load them:

```bash
AGED_CHECK_INTERVAL_MINUTES    # ❌ NOT in config/settings.py
USE_SYMBOL_WHITELIST           # ❌ NOT in config/settings.py
WHITELIST_SYMBOLS              # ❌ NOT in config/settings.py
EXCLUDED_PATTERNS              # ❌ NOT in config/settings.py
MIN_SYMBOL_VOLUME_USD          # ❌ NOT in config/settings.py
DELISTED_SYMBOLS               # ❌ NOT in config/settings.py
```

**Action**: Either add these to config/settings.py or remove from .env if not needed.

---

## 📋 RECOMMENDED ACTIONS

### Priority 1: Fix Critical Issues (IMMEDIATE)

1. **Remove duplicate definitions**:
   ```bash
   # Remove line 70: MAX_EXPOSURE_USD=30000
   # Keep line 24: MAX_EXPOSURE_USD=300000 (or decide which value is correct!)

   # Remove line 193: MAX_POSITION_AGE_HOURS=3
   # Keep line 32: MAX_POSITION_AGE_HOURS=3
   ```

2. **Verify which MAX_EXPOSURE_USD value is correct**:
   - Line 24: `300000` (300K USD)
   - Line 70: `30000` (30K USD)
   - Check which one is actually intended!

### Priority 2: Clean Up .env (HIGH)

**Remove 37 unused variables** from .env:

```bash
# Create backup first
cp .env .env.backup_before_cleanup

# Remove these sections:
# 1. All PROMETHEUS_*, HEALTH_CHECK_PORT, METRICS_ENABLED
# 2. All HEALTH_CHECK_* variables (11 vars)
# 3. All EMERGENCY_* variables (19 vars)
# 4. MAX_COOL_DOWN_LIMIT, TEST_MODE, LEVERAGE, WAVE_CLEANUP_HOURS
# 5. USE_WEBSOCKET_SIGNALS, DUPLICATE_CHECK_ENABLED, ALLOW_MULTIPLE_POSITIONS
```

Estimated size reduction: **~50 lines** from .env

### Priority 3: Update .env.example (MEDIUM)

**Completely rewrite .env.example** based on current .env active variables:

```bash
# Include ONLY the 60 active variables
# Group by category
# Add clear comments
# Use placeholder values (not real API keys!)
```

### Priority 4: Add Missing Variables to config/settings.py (LOW)

If symbol filtering variables are actually needed:

```python
# Add to config/settings.py _init_trading():
if val := os.getenv('USE_SYMBOL_WHITELIST'):
    config.use_symbol_whitelist = val.lower() == 'true'
if val := os.getenv('WHITELIST_SYMBOLS'):
    config.whitelist_symbols = val
if val := os.getenv('EXCLUDED_PATTERNS'):
    config.excluded_patterns = val
if val := os.getenv('MIN_SYMBOL_VOLUME_USD'):
    config.min_symbol_volume_usd = Decimal(val)
if val := os.getenv('DELISTED_SYMBOLS'):
    config.delisted_symbols = val
```

Or remove these from .env if not needed.

---

## 📊 PROPOSED CLEAN .env STRUCTURE

```bash
# ==========================================
# DATABASE CONFIGURATION (7 vars)
# ==========================================
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fox_crypto
DB_USER=evgeniyyanvarskiy
DB_PASSWORD=
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# ==========================================
# EXCHANGE API KEYS (6 vars)
# ==========================================
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET=true

BYBIT_API_KEY=...
BYBIT_API_SECRET=...
BYBIT_TESTNET=true

# ==========================================
# POSITION SIZING (5 vars)
# ==========================================
POSITION_SIZE_USD=6
MIN_POSITION_SIZE_USD=5
MAX_POSITION_SIZE_USD=5000
MAX_POSITIONS=150
MAX_EXPOSURE_USD=300000  # Choose correct value: 300K or 30K?

# ==========================================
# RISK MANAGEMENT - TRAILING STOP (6 vars)
# ==========================================
STOP_LOSS_PERCENT=2.0
TRAILING_ACTIVATION_PERCENT=1.5
TRAILING_CALLBACK_PERCENT=0.5
TRAILING_MIN_UPDATE_INTERVAL_SECONDS=30
TRAILING_MIN_IMPROVEMENT_PERCENT=0.2
TRAILING_ALERT_IF_UNPROTECTED_WINDOW_MS=300

# ==========================================
# AGED POSITION SYSTEM (6 vars)
# ==========================================
MAX_POSITION_AGE_HOURS=3
AGED_GRACE_PERIOD_HOURS=1
AGED_LOSS_STEP_PERCENT=0.5
AGED_MAX_LOSS_PERCENT=10.0
AGED_ACCELERATION_FACTOR=1.2  # If needed
COMMISSION_PERCENT=0.05

# ==========================================
# SIGNAL FILTERING (4 vars)
# ==========================================
MIN_SCORE_WEEK=62
MIN_SCORE_MONTH=58
MAX_SPREAD_PERCENT=2.0
STOPLIST_SYMBOLS=BTCDOMUSDT,USDCUSDT,BUSDUSDT,EURBUSD,GBPBUSD

# ==========================================
# WAVE PROCESSING (5 vars)
# ==========================================
WAVE_CHECK_MINUTES=5,20,35,50
WAVE_CHECK_DURATION_SECONDS=240
WAVE_CHECK_INTERVAL_SECONDS=1
SIGNAL_BUFFER_PERCENT=50
MAX_TRADES_PER_15MIN=5

# ==========================================
# RATE LIMITING (6 vars)
# ==========================================
BINANCE_RATE_LIMIT_PER_SEC=16
BINANCE_RATE_LIMIT_PER_MIN=960
BYBIT_RATE_LIMIT_PER_SEC=8
BYBIT_RATE_LIMIT_PER_MIN=96
DEFAULT_RATE_LIMIT_PER_SEC=5
DEFAULT_RATE_LIMIT_PER_MIN=60

# ==========================================
# WEBSOCKET SIGNAL SERVER (6 vars)
# ==========================================
SIGNAL_WS_URL=ws://10.8.0.1:8765
SIGNAL_WS_TOKEN=secure_websocket_pass_2024
SIGNAL_WS_RECONNECT_INTERVAL=5
SIGNAL_WS_AUTO_RECONNECT=true  # Add if used
SIGNAL_WS_MAX_RECONNECT_ATTEMPTS=-1  # Add if used
SIGNAL_BUFFER_SIZE=100  # Add if used

# ==========================================
# SYSTEM CONFIGURATION (3 vars)
# ==========================================
ENVIRONMENT=development
LOG_LEVEL=INFO
DEBUG=false

# ==========================================
# UNIFIED PROTECTION (1 var)
# ==========================================
USE_UNIFIED_PROTECTION=true

# ==========================================
# ENCRYPTION (2 vars) - Optional
# ==========================================
# MASTER_KEY=...  # If using encryption
# USERNAME=...    # If using encryption
```

**Total: ~60 variables** (down from 97)

---

## ✅ VERIFICATION CHECKLIST

After cleanup, verify:

- [ ] No duplicate variable definitions
- [ ] All 60 active variables present
- [ ] All 37 unused variables removed
- [ ] .env.example updated to match .env structure
- [ ] No real API keys in .env.example
- [ ] Config comments are clear and helpful
- [ ] Run bot and verify it starts without errors
- [ ] Check logs for "Environment variable X not found" warnings

---

## 📝 NOTES

1. **symbol filtering variables** (USE_SYMBOL_WHITELIST, WHITELIST_SYMBOLS, EXCLUDED_PATTERNS, etc.) exist in .env but are NOT loaded by config/settings.py. Need to verify if they're used directly by other modules.

2. **Emergency liquidation system** has 19 variables but the entire system is commented as "DISABLED for safety" and not implemented. Safe to remove.

3. **Health monitoring variables** (12 vars) exist but the health monitoring system uses hardcoded values. Could either implement these or remove them.

4. **DATABASE_URL** is used in migration scripts but NOT in main code (which uses individual DB_* variables). Keep for migration compatibility.

---

**Audit Complete** ✅

**Next Steps**:
1. Review this report
2. Approve cleanup plan
3. Create backup: `cp .env .env.backup_audit_20251024`
4. Apply recommended changes
5. Test bot startup
6. Update .env.example

---

**Report Location**: `docs/ENV_AUDIT_REPORT.md`
**Generated**: 2025-10-24
