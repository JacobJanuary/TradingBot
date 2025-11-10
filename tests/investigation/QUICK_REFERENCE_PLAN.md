# 🚀 QUICK REFERENCE - Implementation Plan

**Полный план**: `IMPLEMENTATION_PLAN_DETAILED.md`

---

## 📋 4 ФАЗЫ - КРАТКО

### Phase 0: Git Backup (10 min)
```bash
git commit -m "backup: pre position_manager cache implementation"
git checkout -b fix/position-manager-cache-integration
cp core/exchange_manager.py core/exchange_manager.py.backup_phase0_$(date +%Y%m%d_%H%M%S)
```

### Phase 1: Add position_manager Reference (30 min)

**Файлы**: `core/exchange_manager.py`, `main.py`

**Изменения**:
1. `ExchangeManager.__init__` - добавить параметр `position_manager=None`
2. Добавить `from typing import TYPE_CHECKING`
3. `main.py` - two-phase initialization:
   ```python
   # Create exchanges
   exchanges = {name: ExchangeManager(..., position_manager=None) for ...}
   # Create position_manager
   position_manager = PositionManager(exchanges=exchanges, ...)
   # Link back
   for ex in exchanges.values():
       ex.position_manager = position_manager
   ```

**Git**: `git commit -m "feat(phase1): add position_manager reference"`

### Phase 2: Modify Position Lookup (45 min)

**Файл**: `core/exchange_manager.py` строки 1043-1074, 1139

**Изменения**:

**Priority 1** (строки 1051-1074):
```python
# ДО:
if symbol in self.positions:
    cached_contracts = float(self.positions[symbol].get('contracts', 0))

# ПОСЛЕ:
if self.position_manager and symbol in self.position_manager.positions:
    position_state = self.position_manager.positions[symbol]
    cached_contracts = float(position_state.quantity)
```

**Database Fallback** (строка 1139):
```python
# ДО:
if amount == 0 and self.repository and symbol not in self.positions:

# ПОСЛЕ:
if amount == 0 and self.repository and (
    not self.position_manager or
    symbol not in self.position_manager.positions
):
```

**Git**: `git commit -m "feat(phase2): use position_manager.positions for lookup"`

### Phase 3: Unit Tests (60 min)

**Файл**: `tests/unit/test_exchange_manager_position_lookup.py` (NEW)

**8 тестов**:
1. Position found in position_manager ✅
2. Position closed (quantity=0) abort ✅
3. Fallback to Exchange API ✅
4. Backward compat (no position_manager) ✅
5. Database fallback on restart ✅
6. Database fallback BLOCKED (SOONUSDT fix) ✅
7. Decimal → float conversion ✅
8. Position not found abort ✅

**Run**:
```bash
python -m pytest tests/unit/test_exchange_manager_position_lookup.py -v
# ТРЕБОВАНИЕ: 8/8 PASSED
```

**Git**: `git commit -m "test(phase3): add comprehensive unit tests"`

### Phase 4: Production Deployment (30 min)

```bash
# 1. Pre-checks
python -m pytest tests/unit/test_exchange_manager_position_lookup.py -v  # 8/8 PASSED
python3 -m py_compile core/exchange_manager.py main.py
git status  # clean

# 2. Stop bot
systemctl stop trading-bot

# 3. Deploy
# (files already modified in Phase 1-2)

# 4. Start bot
systemctl start trading-bot

# 5. Monitor
tail -f logs/trading_bot.log | grep "position_manager_cache\|database_fallback\|TS ACTIVATED"

# 6. Wait for first TS activation
# Expected: lookup_method=position_manager_cache, NO -2021 error
```

**Git**: `git commit -m "deploy(phase4): production deployment"`

---

## ⚡ CRITICAL POINTS

### Must Pass Before Phase 4
- ✅ All 8 unit tests PASSED
- ✅ Syntax check passed
- ✅ Git working tree clean
- ✅ Code review completed

### Expected Results After Deployment
- ✅ Log: `Using position_manager cache: X contracts`
- ✅ Log: `lookup_method: position_manager_cache`
- ❌ NO Log: `database_fallback` (except after restart)
- ❌ NO Error: `-2021`

### Success Metrics (24h)
- Position lookup: <1ms (was 620ms)
- Database fallback: 0 (except restart)
- TS activation success: 100%
- -2021 errors: 0

---

## 🚨 ROLLBACK (if needed)

```bash
systemctl stop trading-bot
cp core/exchange_manager.py.backup_phase0_* core/exchange_manager.py
cp main.py.backup_phase0_* main.py
systemctl start trading-bot
```

---

## 📊 CHANGES SUMMARY

| Файл | Строки изменены | Критичность |
|------|----------------|-------------|
| `core/exchange_manager.py` | ~80 lines | **HIGH** |
| `main.py` | ~15 lines | MEDIUM |
| `tests/.../test_exchange_manager_position_lookup.py` | ~400 lines (NEW) | LOW |

**Total time**: ~2.5 hours
**Risk**: MEDIUM
**Success probability**: 95%

---

## 🎯 ONE-LINE SUMMARY

**Использовать `position_manager.positions` (real-time WebSocket) вместо `exchange_manager.self.positions` (only updated on fetch_positions call) для position lookup при SL update.**

---

**Детальный план**: См. `IMPLEMENTATION_PLAN_DETAILED.md`
**Расследование**: См. `SOONUSDT_ROOT_CAUSE_FINAL.md`
