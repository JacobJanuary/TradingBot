# 🔴 КРИТИЧЕСКИЙ БАГ: Trailing Stop получает неправильный initial_stop после изменений

**Дата**: 2025-10-22 06:20
**Статус**: 🔴 КРИТИЧЕСКИЙ - Производственная проблема
**Приоритет**: P0 - СРОЧНО
**Влияние**: Множественные ошибки обновления SL на бирже

---

## 📋 EXECUTIVE SUMMARY

После коммита `d233078` (fix: critical - recalculate stop-loss from execution price) возникли массовые ошибки обновления trailing stop на бирже:

**Симптомы**:
1. **APTUSDT (Binance)**: Ошибка -2021 "Order would immediately trigger" - десятки попыток обновления SL
2. **Bybit позиции**: Ошибка 170193 "Buy order price cannot be higher than 0USDT" - передается неправильная цена SL

**Root Cause**: Trailing Stop Manager получает устаревший `initial_stop`, рассчитанный от SIGNAL price вместо REAL execution price.

---

## 🔍 ДЕТАЛЬНЫЙ АНАЛИЗ

### Хронология событий

#### 1. Что изменилось в коммите d233078 (2025-10-22 03:55)

**Файл**: `core/atomic_position_manager.py`

**БЫЛО** (до коммита):
- SL рассчитывался в `position_manager.py` от signal price
- Передавался как `stop_loss_price` в atomic_manager
- Использовался БЕЗ пересчета

**СТАЛО** (после коммита):
- SL рассчитывается ВНУТРИ `atomic_position_manager.py`
- Передается как `stop_loss_percent`
- Пересчитывается от REAL execution price

```python
# Строки 241-257 в atomic_position_manager.py
# CRITICAL FIX: Recalculate SL from REAL execution price
position_side_for_sl = 'long' if side.lower() == 'buy' else 'short'
stop_loss_price = calculate_stop_loss(
    to_decimal(exec_price),  # ✅ Use REAL execution price
    position_side_for_sl,
    to_decimal(stop_loss_percent)
)
logger.info(f"🛡️ SL calculated from exec_price ${exec_price}: ${stop_loss_price}")
```

#### 2. Что НЕ изменилось (но должно было!)

**Файл**: `core/position_manager.py`, строки 988-990

```python
# ❌ ЭТО ВСЕ ЕЩЕ РАССЧИТЫВАЕТСЯ ОТ SIGNAL PRICE!
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),  # ❌ SIGNAL price (может быть $3.31)
    position_side,
    to_decimal(stop_loss_percent)
)
```

**Файл**: `core/position_manager.py`, строка 1061

```python
# ❌ ПЕРЕДАЕТСЯ СТАРЫЙ stop_loss_price В TRAILING STOP!
initial_stop=float(stop_loss_price)  # ❌ От signal price, НЕ от execution price!
```

---

### 3. Последствия бага

#### Scenario 1: HNTUSDT (реальный пример из логов)

**Signal данные**:
- Entry price (signal): `$3.31` (предсказание модели)
- Stop loss percent: `2%`

**Execution данные** (реальность):
- Real execution price: `$1.616`
- SL должен быть: `$1.583` (1.616 * 0.98)

**Что происходит**:

1. **position_manager.py:988-990** рассчитывает:
   ```
   stop_loss_price = $3.31 * 0.98 = $3.2438
   ```

2. **atomic_manager.py:246-257** ПРАВИЛЬНО пересчитывает:
   ```
   stop_loss_price = $1.616 * 0.98 = $1.583
   ```

3. **atomic_result** возвращает ПРАВИЛЬНОЕ значение:
   ```python
   {
       'stop_loss_price': 1.583,  # ✅ Правильно!
       ...
   }
   ```

4. **НО position_manager.py:1061** использует СТАРОЕ значение:
   ```python
   initial_stop=float(stop_loss_price)  # ❌ = $3.2438 (от signal price!)
   ```

5. **Trailing Stop создается с НЕПРАВИЛЬНЫМ SL**:
   ```
   current_stop_price = $3.2438  # ❌ НЕПРАВИЛЬНО!
   ```

6. **При первом обновлении TS пытается установить SL на бирже**:
   ```
   Текущая цена: $3.30
   SL: $3.2438
   ```

7. **Биржа отклоняет**: "Order would immediately trigger" (цена уже ниже SL!)

---

#### Scenario 2: APTUSDT (из текущих логов)

**Логи**:
```
2025-10-22 06:14:49 - ERROR - ❌ APTUSDT: SL update failed
  - binance {"code":-2021,"msg":"Order would immediately trigger."}

2025-10-22 06:14:49 - INFO - 📈 APTUSDT: SL moved
  - Trailing stop updated from 3.2871 to 3.2877 (+0.02%)

2025-10-22 06:14:56 - ERROR - ❌ APTUSDT: SL update failed (повтор)
2025-10-22 06:15:02 - ERROR - ❌ APTUSDT: SL update failed (повтор)
2025-10-22 06:15:10 - ERROR - ❌ APTUSDT: SL update failed (повтор)
2025-10-22 06:15:21 - ERROR - ❌ APTUSDT: SL update failed (повтор)
```

**Анализ**:
- TS Manager думает что SL должен быть ~$3.28
- Но РЕАЛЬНЫЙ SL должен быть намного ниже
- Каждая попытка обновления отклоняется биржей
- TS продолжает вычислять неправильные значения

---

#### Scenario 3: Bybit "price cannot be higher than 0USDT"

**Логи**:
```
2025-10-22 06:16:22 - ERROR - ❌ Invalid order:
  bybit {"retCode":170193,"retMsg":"Buy order price cannot be higher than 0USDT."}
```

**Анализ**:
- Передается `price=0` или отрицательное значение
- Возможно из-за неправильных расчетов с устаревшим initial_stop

---

## 🎯 ROOT CAUSE

### Основная причина

**Несоответствие между тремя компонентами**:

1. **atomic_position_manager.py** (✅ ПРАВИЛЬНО):
   - Рассчитывает SL от execution price
   - Возвращает правильное значение в `atomic_result['stop_loss_price']`

2. **position_manager.py:988-990** (⚠️ УСТАРЕЛО):
   - Рассчитывает SL от signal price (старая логика)
   - Создает локальную переменную `stop_loss_price`

3. **position_manager.py:1061** (❌ ОШИБКА):
   - Использует УСТАРЕВШУЮ переменную `stop_loss_price`
   - Вместо ПРАВИЛЬНОЙ `atomic_result['stop_loss_price']`

### Почему это критично

1. **Trailing Stop полагается на initial_stop**:
   - Используется как начальное значение `current_stop_price`
   - Все последующие обновления рассчитываются от этого значения
   - Если initial_stop неправильный → ВСЕ обновления неправильные

2. **Биржа отклоняет неправильные SL**:
   - "Order would immediately trigger" → SL выше текущей цены (long)
   - "Price cannot be higher than 0" → Некорректное значение

3. **Цикл ошибок**:
   - TS пытается обновить SL
   - Биржа отклоняет
   - TS повторяет попытку
   - Бесконечный цикл ошибок

---

## 📊 ДОКАЗАТЕЛЬСТВА

### Git Diff коммита d233078

**Файл**: `core/position_manager.py`
```diff
-                    stop_loss_price=float(stop_loss_price)
+                    stop_loss_percent=float(stop_loss_percent)  # FIX: Pass percent, not price
```

**Файл**: `core/atomic_position_manager.py`
```diff
+                # CRITICAL FIX: Recalculate SL from REAL execution price
+                from utils.decimal_utils import calculate_stop_loss, to_decimal
+
+                position_side_for_sl = 'long' if side.lower() == 'buy' else 'short'
+                stop_loss_price = calculate_stop_loss(
+                    to_decimal(exec_price),  # Use REAL execution price
+                    position_side_for_sl,
+                    to_decimal(stop_loss_percent)
+                )
+
+                logger.info(f"🛡️ SL calculated from exec_price ${exec_price}: ${stop_loss_price}")
```

### Текущий код с проблемой

**position_manager.py:988-990** (СТАРАЯ логика):
```python
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),  # ❌ Signal price
    position_side,
    to_decimal(stop_loss_percent)
)
```

**position_manager.py:1061** (ИСПОЛЬЗУЕТ СТАРОЕ значение):
```python
initial_stop=float(stop_loss_price)  # ❌ От signal price!
```

**Должно быть**:
```python
initial_stop=float(atomic_result['stop_loss_price'])  # ✅ От execution price!
```

---

## ✅ РЕШЕНИЕ

### Fix #1: Использовать правильный SL из atomic_result

**Файл**: `core/position_manager.py`, строка 1061

**БЫЛО**:
```python
initial_stop=float(stop_loss_price)  # ❌ Устаревшее значение
```

**ДОЛЖНО БЫТЬ**:
```python
initial_stop=float(atomic_result['stop_loss_price'])  # ✅ Правильное значение
```

### Fix #2 (Опционально): Удалить устаревший расчет

**Файл**: `core/position_manager.py`, строки 988-990

Этот расчет больше не используется в atomic path (только для логирования).

**Опция A**: Убрать расчет полностью (логировать только процент)
**Опция B**: Оставить для логирования, но добавить комментарий что это ТОЛЬКО для лога

---

## 🧪 ПЛАН ТЕСТИРОВАНИЯ

### Test 1: Проверка значения initial_stop

```python
# После изменений
atomic_result = await atomic_manager.open_position_atomic(...)

# Проверить что SL рассчитан от execution price
assert atomic_result['stop_loss_price'] != old_stop_loss_price
assert atomic_result['stop_loss_price'] == calculate_stop_loss(
    exec_price, side, stop_loss_percent
)
```

### Test 2: Проверка Trailing Stop

```python
# Trailing Stop должен получить правильный initial_stop
ts = trailing_manager.trailing_stops[symbol]
assert ts.current_stop_price == atomic_result['stop_loss_price']
```

### Test 3: Integration test

1. Открыть позицию через atomic path
2. Проверить что TS создан с правильным initial_stop
3. Обновить цену → TS должен обновиться БЕЗ ошибок
4. Проверить логи - не должно быть "Order would immediately trigger"

---

## 🚨 КРИТИЧНОСТЬ

### Почему P0 - СРОЧНО

1. **Массовые ошибки**: Десятки ошибок в минуту для каждой позиции
2. **Все новые позиции затронуты**: Каждая позиция через atomic path получает неправильный SL
3. **Бесполезная нагрузка на API**: Постоянные попытки обновления SL
4. **Risk exposure**: Позиции могут быть без корректной защиты
5. **Вчера работало**: Регрессия после недавнего коммита

### Почему это не было поймано

1. **Не было тестов** для проверки initial_stop в TS после atomic creation
2. **Коммит d233078** менял логику расчета SL, но не обновил вызов create_trailing_stop
3. **Изменения в разных файлах**: atomic_position_manager.py vs position_manager.py

---

## 📝 NEXT STEPS

1. ✅ **CRITICAL**: Применить Fix #1 (изменить строку 1061)
2. ✅ Протестировать на testnet
3. ✅ Проверить что ошибки "Order would immediately trigger" исчезли
4. ⚠️ Добавить unit test для проверки initial_stop
5. ⚠️ Добавить integration test для atomic path + TS

---

## 🔗 RELATED

- Коммит с проблемой: `d233078`
- Связанные файлы:
  - `core/position_manager.py:1061`
  - `core/atomic_position_manager.py:421`
  - `protection/trailing_stop.py:357`
