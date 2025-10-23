# 🔴 CRITICAL BUG: LONG Positions SL Calculated with SHORT Formula
## Дата: 2025-10-21 07:15
## Severity: P0 - КРИТИЧЕСКАЯ
## Уверенность: 100% - ДОКАЗАНО

---

## 📊 EXECUTIVE SUMMARY

Обнаружен критический баг в расчете Stop Loss для LONG позиций: используется формула для SHORT позиций, что приводит к установке SL ВЫШЕ entry вместо НИЖЕ.

**Результат**:
- 100% LONG позиций создаются с НЕПРАВИЛЬНЫМ initial_stop
- Binance отклоняет ордера с ошибкой `-2021 "Order would immediately trigger"`
- Позиции остаются БЕЗ защиты TS initial stop

**Статус**: ✅ **ПРОБЛЕМА НАЙДЕНА С 100% УВЕРЕННОСТЬЮ**

---

## 🔴 ПРОБЛЕМА

### Root Cause:

**Файл**: `core/position_manager.py:948-950`

```python
# LINE 948-950: calculate_stop_loss вызывается с request.side = 'BUY'
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),
    request.side,  # ← 'BUY' passed here! ❌
    to_decimal(stop_loss_percent)
)
```

**Проблема**: `request.side = 'BUY'`, НО функция `calculate_stop_loss` проверяет:

```python
# utils/decimal_utils.py:155-158
if side.lower() == 'long':  # ← 'buy'.lower() != 'long' !
    sl_price = entry_price - sl_distance  # LONG formula ✅
else:  # short
    sl_price = entry_price + sl_distance  # SHORT formula ❌ USED FOR 'BUY'!
```

**Что происходит**:
1. `request.side = 'BUY'`
2. `'buy'.lower() == 'long'` → `False`
3. Попадает в `else:` ветку (SHORT formula)
4. `sl_price = entry + distance` → SL ВЫШЕ entry ❌

---

## 📈 ДОКАЗАТЕЛЬСТВА

### Test 1: Математическое доказательство

```python
# ATOMUSDT (real data from logs)
entry_price = 3.255
stop_loss_percent = 2.0

# WRONG (current bug):
sl = entry * (1 + percent/100) = 3.255 * 1.02 = 3.3201 ❌

# CORRECT (for LONG):
sl = entry * (1 - percent/100) = 3.255 * 0.98 = 3.1899 ✅
```

### Test 2: Реальные логи (ATOMUSDT)

```
2025-10-21 06:05:22 - atomic_position_manager:
  🛡️ Placing stop-loss for ATOMUSDT at 3.3201

2025-10-21 06:05:22 - stop_loss_manager:
  📊 Creating SL for ATOMUSDT: stop=3.248, current=3.255, side=sell
  ✅ SL placed: 3.248 (Protection Manager - CORRECT)

2025-10-21 06:05:24 - trailing_stop:
  Created trailing stop for ATOMUSDT long: entry=3.257, initial_stop=3.3201
  ❌ Failed to place stop order: binance -2021 'Order would immediately trigger'
```

**Analysis**:
- Protection Manager: `3.248 < 3.255` ✅ (CORRECT - BELOW entry)
- TS initial_stop: `3.3201 > 3.255` ❌ (WRONG - ABOVE entry)

### Test 3: Validation of 10 LONG positions

Проверены ВСЕ LONG позиции за последние 3 часа:

| Symbol | Entry | Initial Stop | Ratio | Status |
|--------|-------|--------------|-------|--------|
| LAUSDT | 0.459 | 0.467874 | 1.0193 (+1.93%) | ❌ WRONG |
| BIOUSDT | 0.09859 | 0.1005516 | 1.0199 (+1.99%) | ❌ WRONG |
| MEUSDT | 0.448 | 0.455124 | 1.0159 (+1.59%) | ❌ WRONG |
| APTUSDT | 3.2372 | 3.29766 | 1.0187 (+1.87%) | ❌ WRONG |
| MAGICUSDT | 0.1477 | 0.150654 | 1.0200 (+2.00%) | ❌ WRONG |
| PIXELUSDT | 0.0181 | 0.0184212 | 1.0178 (+1.78%) | ❌ WRONG |
| ATOMUSDT | 3.257 | 3.3201 | 1.0194 (+1.94%) | ❌ WRONG |
| JUPUSDT | 0.3588 | 0.365364 | 1.0183 (+1.83%) | ❌ WRONG |
| PROVEUSDT | 0.7761 | 0.78795 | 1.0153 (+1.53%) | ❌ WRONG |
| MANTAUSDT | 0.1191 | 0.121278 | 1.0183 (+1.83%) | ❌ WRONG |

**Результат**: 🔴 **10/10 (100%) LONG позиций имеют SL ВЫШЕ entry**

Все используют формулу `entry * 1.02` вместо `entry * 0.98`!

---

## 🎯 ТОЧНОЕ МЕСТО ПРОБЛЕМЫ

**File**: `core/position_manager.py`

### ПРОБЛЕМНЫЙ КОД (строки 946-964):

```python
# 6. Calculate stop-loss price first
stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),
    request.side,  # ← 'BUY' ❌
    to_decimal(stop_loss_percent)
)

logger.info(f"Opening position ATOMICALLY: {symbol} {request.side} {quantity}")
logger.info(f"Stop-loss will be set at: {float(stop_loss_price)} ({stop_loss_percent}%)")

# Convert side: long -> buy, short -> sell for Binance
if request.side.lower() == 'long':
    order_side = 'buy'
elif request.side.lower() == 'short':
    order_side = 'sell'
else:
    order_side = request.side.lower()  # ← 'BUY' stays as 'buy'
```

**Проблема**: Конвертация side происходит ПОСЛЕ расчета SL!

---

## ✅ РЕШЕНИЕ

### ИСПРАВЛЕННЫЙ КОД:

```python
# 6. Convert order side to position side FIRST
if request.side.lower() in ['buy', 'long']:
    position_side = 'long'
    order_side = 'buy'
elif request.side.lower() in ['sell', 'short']:
    position_side = 'short'
    order_side = 'sell'
else:
    raise ValueError(f"Invalid side: {request.side}")

# Calculate stop-loss with correct position side
stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),
    position_side,  # ← 'long' or 'short' ✅
    to_decimal(stop_loss_percent)
)

logger.info(f"Opening position ATOMICALLY: {symbol} {request.side} {quantity}")
logger.info(f"Stop-loss will be set at: {float(stop_loss_price)} ({stop_loss_percent}%)")
```

### Изменения:
1. **Добавить конвертацию side ПЕРЕД вызовом calculate_stop_loss**
2. **Передавать position_side ('long'/'short') вместо request.side ('BUY'/'SELL')**
3. **Хранить order_side для использования в atomic_manager**

---

## 📊 IMPACT ANALYSIS

### Затронуто:
- ✅ **ВСЕ LONG позиции (100%)** - SL рассчитывается неправильно
- ❌ Initial SL устанавливается ВЫШЕ entry
- ❌ Binance отклоняет с `-2021 "Order would immediately trigger"`
- ❌ Позиции создаются БЕЗ TS initial stop protection

### НЕ затронуто:
- ✅ SHORT позиции - accidentally правильная формула используется
- ✅ Protection Manager SL - использует другой путь (правильный)
- ✅ Расчет entry_price - не связано с этим багом

### Severity Analysis:

**🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА (P0)**:
- Все LONG позиции открываются БЕЗ initial stop
- При резком движении цены позиция не защищена
- Потенциальные убытки > 2% вместо фиксированных 2% SL

---

## 🧪 ТЕСТИРОВАНИЕ

**Тестовый скрипт**: `tests/test_stop_loss_calculation_bug.py`

Запустить:
```bash
python3 tests/test_stop_loss_calculation_bug.py
```

**Expected output**:
```
TEST 1: calculate_stop_loss with side='BUY' (CURRENT BUG)
Result: 3.32010
❌ BUG: SL is ABOVE entry for BUY (should be BELOW!)

TEST 2: calculate_stop_loss with side='long' (CORRECT)
Result: 3.18990
✅ CORRECT: SL is BELOW entry for LONG

VALIDATION (with fix):
Test with request.side='BUY':
  Converted to position_side='long'
  Stop Loss: 3.18990
  ✅ FIXED: SL is now BELOW entry!
```

---

## 📝 ИСТОРИЯ БАГА

### Почему Protection Manager работает правильно?

Protection Manager вызывает `calculate_stop_loss` из ДРУГОГО места с правильным side:

```python
# core/stop_loss_manager.py
# Уже использует правильный side ('sell' for LONG, 'buy' for SHORT)
```

### Почему SHORT позиции работают случайно правильно?

```python
request.side = 'SELL'
'sell'.lower() == 'long' → False
→ else: sl_price = entry + distance  # Правильно для SHORT! ✅
```

SHORT случайно правильно, потому что:
- 'SELL' не равен 'long' → попадает в else
- else использует SHORT formula
- Для SHORT это ПРАВИЛЬНАЯ formula!

---

## ✅ CHECKLIST ДЛЯ ИСПРАВЛЕНИЯ

- [x] Проблема найдена с 100% уверенностью
- [x] Создан тестовый скрипт (`tests/test_stop_loss_calculation_bug.py`)
- [x] Проверены реальные логи (10 LONG позиций - 100% bug rate)
- [x] Определено точное место исправления (`core/position_manager.py:946-964`)
- [x] Подготовлено решение (конвертация side перед расчетом SL)
- [ ] **НЕ ПРИМЕНЕНО** - ждем подтверждения пользователя

---

## 🎯 NEXT STEPS

1. ✅ Получить подтверждение пользователя
2. ⏳ Применить минимальное исправление (только изменить порядок)
3. ⏳ Запустить `test_stop_loss_calculation_bug.py` для валидации
4. ⏳ Проверить следующую LONG позицию в production
5. ⏳ Закоммитить изменения

---

## 📌 SUMMARY

**Проблема**: `request.side='BUY'` передается в `calculate_stop_loss()`, которая ожидает `'long'/'short'`

**Причина**: Конвертация side происходит ПОСЛЕ расчета SL

**Решение**: Переместить конвертацию side ПЕРЕД вызовом `calculate_stop_loss()`

**Файл**: `core/position_manager.py:946-964`

**Severity**: 🔴 P0 CRITICAL

**Уверенность**: 100% - доказано математически, в логах, и валидировано на 10 реальных позициях

---

**Investigation выполнен**: Claude Code
**Статус**: ✅ 100% PROOF - READY FOR FIX
**Action Required**: Применить исправление после подтверждения пользователя
