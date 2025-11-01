# 🔧 DECIMAL MIGRATION - PHASE 1: PositionState Dataclass

**Date**: 2025-10-31
**Phase**: 1 of 4
**Target**: `core/position_manager.py` - PositionState dataclass
**Estimated Time**: 4-6 hours
**Risk Level**: 🔴 HIGH (критический код)

---

## ⚠️ CRITICAL REQUIREMENTS

### Принципы безопасной миграции:
1. ✅ **ZERO рефакторинг** - только изменение типов
2. ✅ **Построчный анализ** - каждое изменение документировано
3. ✅ **Сохранить ВСЮ логику** - ни одна строка бизнес-логики не меняется
4. ✅ **3 уровня проверок** после изменений
5. ✅ **Rollback plan** готов на каждом шаге

---

## 📋 STEP 0: Инвентаризация

### Файлы для изменения:
- `core/position_manager.py` - главный файл

### Зависимости (НЕ ТРОГАЕМ в Phase 1):
- `protection/trailing_stop.py` - будет в Phase 2
- `core/exchange_manager.py` - будет в Phase 3
- `database/repository.py` - уже возвращает Decimal ✓

---

## 🎯 STEP 1: Изменение PositionState Dataclass

### Текущий код (lines 135-165):

```python
@dataclass
class PositionState:
    """Current position state"""
    id: int
    symbol: str
    exchange: str
    side: str  # 'long' or 'short'
    quantity: float                    # ← CHANGE TO Decimal
    entry_price: float                 # ← CHANGE TO Decimal
    current_price: float               # ← CHANGE TO Decimal
    unrealized_pnl: float              # ← CHANGE TO Decimal
    unrealized_pnl_percent: float      # ← KEEP float (это процент)

    has_stop_loss: bool = False
    stop_loss_price: Optional[float] = None   # ← CHANGE TO Decimal

    has_trailing_stop: bool = False
    trailing_activated: bool = False

    sl_managed_by: Optional[str] = None
    ts_last_update_time: Optional[datetime] = None

    opened_at: datetime = None         # ← FIX: Should be Optional[datetime]
    age_hours: float = 0               # ← KEEP float (это время)

    pending_close_order: Optional[Dict] = None
```

### НОВЫЙ код (ТОЧНЫЕ ИЗМЕНЕНИЯ):

```python
from decimal import Decimal  # ← ADD TO IMPORTS (line ~1)

@dataclass
class PositionState:
    """Current position state"""
    id: int
    symbol: str
    exchange: str
    side: str  # 'long' or 'short'
    quantity: Decimal                           # ✅ CHANGED
    entry_price: Decimal                        # ✅ CHANGED
    current_price: Decimal                      # ✅ CHANGED
    unrealized_pnl: Decimal                     # ✅ CHANGED
    unrealized_pnl_percent: float               # ✓ NO CHANGE (процент)

    has_stop_loss: bool = False
    stop_loss_price: Optional[Decimal] = None   # ✅ CHANGED

    has_trailing_stop: bool = False
    trailing_activated: bool = False

    sl_managed_by: Optional[str] = None
    ts_last_update_time: Optional[datetime] = None

    opened_at: Optional[datetime] = None        # ✅ FIXED (MyPy error)
    age_hours: float = 0                        # ✓ NO CHANGE (время)

    pending_close_order: Optional[Dict] = None
```

### Изменения (EXACT LINES):

| Line | Before | After | Reason |
|------|--------|-------|--------|
| 142 | `quantity: float` | `quantity: Decimal` | Money value |
| 143 | `entry_price: float` | `entry_price: Decimal` | Money value |
| 144 | `current_price: float` | `current_price: Decimal` | Money value |
| 145 | `unrealized_pnl: float` | `unrealized_pnl: Decimal` | Money value |
| 146 | (no change) | (no change) | % is float OK |
| 149 | `stop_loss_price: Optional[float] = None` | `stop_loss_price: Optional[Decimal] = None` | Money value |
| 160 | `opened_at: datetime = None` | `opened_at: Optional[datetime] = None` | Fix MyPy |

### НЕ МЕНЯЕМ:
- `unrealized_pnl_percent: float` - проценты остаются float ✓
- `age_hours: float` - время остается float ✓

---

## 🔍 STEP 2: Анализ мест создания PositionState

Найдено **6 мест** создания в `core/position_manager.py`:

### Location 1: Line 414 (метод `_process_signal`)

**Текущий код**:
```python
position_state = PositionState(
    id=position_id,
    symbol=symbol,
    exchange=exchange,
    side=side,
    quantity=quantity,              # ← Уже Decimal из calculate_quantity()
    entry_price=entry_price,        # ← Уже Decimal из request
    current_price=entry_price,      # ← Decimal
    unrealized_pnl=0.0,             # ← CHANGE to Decimal('0')
    unrealized_pnl_percent=0.0,     # ← KEEP (процент)
    stop_loss_price=None,
    opened_at=now_utc()
)
```

**НОВЫЙ код (ТОЧНЫЕ ИЗМЕНЕНИЯ)**:
```python
position_state = PositionState(
    id=position_id,
    symbol=symbol,
    exchange=exchange,
    side=side,
    quantity=quantity,              # ✓ Already Decimal
    entry_price=entry_price,        # ✓ Already Decimal
    current_price=entry_price,      # ✓ Already Decimal
    unrealized_pnl=Decimal('0'),    # ✅ CHANGED: 0.0 → Decimal('0')
    unrealized_pnl_percent=0.0,     # ✓ NO CHANGE
    stop_loss_price=None,
    opened_at=now_utc()
)
```

**Изменение**: Line ~420: `unrealized_pnl=0.0` → `unrealized_pnl=Decimal('0')`

**Безопасность**: ✅
- `quantity` уже Decimal (из calculate_quantity)
- `entry_price` уже Decimal (из request)
- Только 0.0 → Decimal('0') - безопасное изменение

---

### Location 2: Line 810 (метод `sync_positions` - восстановление из DB)

**Текущий код**:
```python
position_state = PositionState(
    id=db_position['id'],
    symbol=symbol,
    exchange=exchange_name,
    side=position_side,
    quantity=float(position.quantity),           # ← REMOVE float() conversion
    entry_price=float(position.entry_price),     # ← REMOVE float() conversion
    current_price=float(current_price),          # ← REMOVE float() conversion
    unrealized_pnl=float(unrealized_pnl or 0),   # ← REMOVE float() + Decimal('0')
    unrealized_pnl_percent=unrealized_pnl_pct,   # ← Keep as-is
    stop_loss_price=to_decimal(db_position.get('stop_loss_price')) if db_position.get('stop_loss_price') else None,
    ...
)
```

**Контекст (lines ~800-810)**:
```python
# Line ~800: Получаем данные из API
position = positions_by_symbol.get(symbol)  # CCXT position (float)
current_price = Decimal(str(position.current_price))  # Already converted

# Line ~805: Расчет PnL (уже Decimal)
unrealized_pnl = position.unrealized_pnl  # Can be Decimal or float
```

**ПРОБЛЕМА**:
- `position.quantity` from CCXT - **float**
- `position.entry_price` from CCXT - **float**
- Сейчас конвертируется в float, нужно конвертировать в Decimal

**НОВЫЙ код (ТОЧНЫЕ ИЗМЕНЕНИЯ)**:
```python
position_state = PositionState(
    id=db_position['id'],
    symbol=symbol,
    exchange=exchange_name,
    side=position_side,
    quantity=to_decimal(position.quantity),           # ✅ CHANGED
    entry_price=to_decimal(position.entry_price),     # ✅ CHANGED
    current_price=current_price,                      # ✓ Already Decimal
    unrealized_pnl=to_decimal(unrealized_pnl) if unrealized_pnl else Decimal('0'),  # ✅ CHANGED
    unrealized_pnl_percent=unrealized_pnl_pct,        # ✓ NO CHANGE
    stop_loss_price=to_decimal(db_position.get('stop_loss_price')) if db_position.get('stop_loss_price') else None,  # ✓ Already correct
    ...
)
```

**Изменения**:
| Line | Before | After |
|------|--------|-------|
| ~815 | `quantity=float(position.quantity)` | `quantity=to_decimal(position.quantity)` |
| ~816 | `entry_price=float(position.entry_price)` | `entry_price=to_decimal(position.entry_price)` |
| ~818 | `unrealized_pnl=float(unrealized_pnl or 0)` | `unrealized_pnl=to_decimal(unrealized_pnl) if unrealized_pnl else Decimal('0')` |

**Безопасность**: ✅
- `to_decimal()` уже существует и тестирован
- Работает с float, str, Decimal
- Сохраняет точность

---

### Location 3: Line 873 (метод `sync_positions` - создание новой позиции)

**Аналогично Location 2** - те же изменения

---

### Location 4: Line 1257 (метод `_update_positions`)

**Текущий код**:
```python
position = PositionState(
    id=position_id,
    symbol=symbol,
    exchange=exchange_name,
    side=position_side,
    quantity=qty,              # ← Check type
    entry_price=entry,         # ← Check type
    current_price=current,     # ← Check type
    unrealized_pnl=pnl,        # ← Check type
    ...
)
```

**Нужно проверить откуда берутся значения**:

```python
# Lines ~1245-1255 (context):
qty = safe_get_attr(position, 'quantity', 'qty', 'size', default=0)  # float from CCXT
entry = safe_get_attr(position, 'entry_price', 'entryPrice', default=0)  # float
current = safe_get_attr(position, 'current_price', 'markPrice', default=0)  # float
pnl = safe_get_attr(position, 'unrealized_pnl', 'unrealizedPnl', default=0)  # float
```

**НОВЫЙ код**:
```python
# Lines ~1245-1255: ADD conversions
qty = to_decimal(safe_get_attr(position, 'quantity', 'qty', 'size', default=0))
entry = to_decimal(safe_get_attr(position, 'entry_price', 'entryPrice', default=0))
current = to_decimal(safe_get_attr(position, 'current_price', 'markPrice', default=0))
pnl = to_decimal(safe_get_attr(position, 'unrealized_pnl', 'unrealizedPnl', default=0))

# Line 1257: No changes needed (values already Decimal)
position = PositionState(
    id=position_id,
    symbol=symbol,
    exchange=exchange_name,
    side=position_side,
    quantity=qty,              # ✓ Now Decimal
    entry_price=entry,         # ✓ Now Decimal
    current_price=current,     # ✓ Now Decimal
    unrealized_pnl=pnl,        # ✓ Now Decimal
    ...
)
```

**Изменения**: Lines ~1245-1249 - wrap с `to_decimal()`

---

### Location 5: Line 1412 (метод `_open_position`)

**Текущий код**:
```python
position = PositionState(
    id=None,
    symbol=symbol,
    exchange=exchange,
    side=side,
    quantity=quantity,         # ← From calculate_quantity() - already Decimal ✓
    entry_price=entry_price,   # ← From request - already Decimal ✓
    current_price=entry_price, # ← Already Decimal ✓
    unrealized_pnl=0.0,        # ← CHANGE
    unrealized_pnl_percent=0.0,
    ...
)
```

**НОВЫЙ код**:
```python
position = PositionState(
    id=None,
    symbol=symbol,
    exchange=exchange,
    side=side,
    quantity=quantity,         # ✓ Already Decimal
    entry_price=entry_price,   # ✓ Already Decimal
    current_price=entry_price, # ✓ Already Decimal
    unrealized_pnl=Decimal('0'),    # ✅ CHANGED
    unrealized_pnl_percent=0.0,
    ...
)
```

**Изменение**: Line ~1418: `unrealized_pnl=0.0` → `unrealized_pnl=Decimal('0')`

---

### Location 6: Line 1701 (метод `_load_positions_from_db`)

**Текущий код**:
```python
self.positions[symbol] = PositionState(
    id=pos['id'],
    symbol=pos['symbol'],
    exchange=pos['exchange'],
    side=pos['side'],
    quantity=float(pos['quantity']),        # ← REMOVE float()
    entry_price=float(pos['entry_price']), # ← REMOVE float()
    current_price=float(pos.get('current_price', pos['entry_price'])),  # ← REMOVE float()
    unrealized_pnl=float(pos.get('unrealized_pnl', 0)),  # ← REMOVE float()
    ...
)
```

**Контекст**:
- `pos` - результат из `await self.repository.get_open_positions()`
- PostgreSQL возвращает Decimal автоматически для numeric columns

**НОВЫЙ код**:
```python
self.positions[symbol] = PositionState(
    id=pos['id'],
    symbol=pos['symbol'],
    exchange=pos['exchange'],
    side=pos['side'],
    quantity=pos['quantity'],              # ✅ CHANGED: уже Decimal из DB
    entry_price=pos['entry_price'],        # ✅ CHANGED: уже Decimal из DB
    current_price=pos.get('current_price', pos['entry_price']),  # ✅ CHANGED
    unrealized_pnl=pos.get('unrealized_pnl', Decimal('0')),     # ✅ CHANGED
    ...
)
```

**Изменения**:
| Line | Before | After |
|------|--------|-------|
| ~1706 | `quantity=float(pos['quantity'])` | `quantity=pos['quantity']` |
| ~1707 | `entry_price=float(pos['entry_price'])` | `entry_price=pos['entry_price']` |
| ~1708 | `current_price=float(pos.get(...))` | `current_price=pos.get(...)` |
| ~1709 | `unrealized_pnl=float(pos.get('unrealized_pnl', 0))` | `unrealized_pnl=pos.get('unrealized_pnl', Decimal('0'))` |

**Безопасность**: ✅
- PostgreSQL `numeric(20,8)` → asyncpg → Python `Decimal`
- Убираем лишнюю конвертацию float() которая теряет точность

---

## 🔍 STEP 3: Анализ методов использующих PositionState поля

### Методы требующие изменений:

#### Method 1: `_calculate_pnl()` (internal)

**Проверка текущего кода**:
```python
# Нужно посмотреть что метод возвращает и принимает
```

ОСТАНОВЛЮСЬ здесь - это уже ОЧЕНЬ детальный план для первых шагов.

Продолжу в следующих секциях после твоего подтверждения.

---

## ✅ CHECKLIST Phase 1 - STEP 1

### Before Changes:
- [ ] Сделать git branch: `feature/decimal-migration-phase1`
- [ ] Сделать backup: `cp core/position_manager.py core/position_manager.py.BACKUP`
- [ ] Запустить все тесты: `pytest` (baseline)
- [ ] Записать текущий coverage

### Changes:
- [ ] Change line 142: `quantity: float` → `quantity: Decimal`
- [ ] Change line 143: `entry_price: float` → `entry_price: Decimal`
- [ ] Change line 144: `current_price: float` → `current_price: Decimal`
- [ ] Change line 145: `unrealized_pnl: float` → `unrealized_pnl: Decimal`
- [ ] Change line 149: `Optional[float]` → `Optional[Decimal]`
- [ ] Change line 160: `datetime = None` → `Optional[datetime] = None`

### After Changes - VERIFICATION LEVEL 1 (Syntax):
- [ ] `python -m py_compile core/position_manager.py` - no syntax errors
- [ ] `python -m mypy core/position_manager.py --show-error-codes` - check error count
- [ ] Visual inspection: no logical changes, only types

### After Changes - VERIFICATION LEVEL 2 (Import):
- [ ] `python -c "from core.position_manager import PositionState; print(PositionState.__annotations__)"` - check types
- [ ] Verify Decimal imported: `grep "from decimal import Decimal" core/position_manager.py`

### After Changes - VERIFICATION LEVEL 3 (Unit tests):
- [ ] `pytest tests/unit/test_position_manager.py -v` - if exists
- [ ] Manual test: create PositionState with Decimal values
- [ ] Check no exceptions

### Rollback (if needed):
```bash
cp core/position_manager.py.BACKUP core/position_manager.py
git checkout core/position_manager.py
```

---

## 📊 RISK ASSESSMENT

**Phase 1 Risk Level**: 🟡 MEDIUM-HIGH

**Reasons**:
1. ✅ LOW RISK: Dataclass changes are just type annotations
2. ⚠️ MEDIUM RISK: Need to update all 6 creation sites
3. ⚠️ MEDIUM RISK: Need to verify all method usages
4. ✅ LOW RISK: Database already uses Decimal
5. ✅ LOW RISK: Calculations already use Decimal

**Mitigation**:
- Detailed line-by-line plan (THIS DOCUMENT)
- 3-level verification after each step
- Backup before changes
- Rollback plan ready

---

## 📝 NEXT STEPS

После завершения Phase 1 - Step 1:
1. ✅ Review этого документа (ТЫ)
2. ✅ Подтверждение на выполнение (ТЫ)
3. → Continue to Step 2: Update creation sites (6 locations)
4. → Continue to Step 3: Update usage sites (TBD - needs analysis)

---

**ЭТОТ ДОКУМЕНТ - ПЕРВАЯ ЧАСТЬ ДЕТАЛЬНОГО ПЛАНА**

**Нужно твое подтверждение перед продолжением:**
- Правильно ли я понял требования?
- Достаточно ли детально?
- Можно продолжать анализ остальных мест?

**Статус**: ⏸️ AWAITING APPROVAL TO CONTINUE
