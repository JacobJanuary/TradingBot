# 🔴 CRITICAL BUG: Trailing Stop параметры не берутся из БД

**Дата**: 2025-11-02
**Тип**: CRITICAL - Trailing Stop использует ENV вместо БД
**Статус**: ✅ ROOT CAUSE IDENTIFIED

---

## 📊 EXECUTIVE SUMMARY

**Проблема**: При открытии новых позиций Trailing Stop создается с параметрами из `.env` (2.0% activation), хотя в таблице `monitoring.params` указано 1.0%.

**Impact**:
- TS активируется при 2% profit вместо 1%
- Нарушается централизованное управление параметрами через БД
- Параметры из БД игнорируются

**Root Cause**: `position_manager.py` НЕ передает `position_params` в `trailing_manager.create_trailing_stop()`

---

## 🔍 ДОКАЗАТЕЛЬСТВА ПРОБЛЕМЫ

### 1. Данные в БД (ПРАВИЛЬНЫЕ)

```sql
SELECT exchange_id, trailing_activation_filter, trailing_distance_filter
FROM monitoring.params;

 exchange_id | trailing_activation_filter | trailing_distance_filter
-------------+----------------------------+--------------------------
           1 |                     1.0000 |                   0.4000  -- Binance
           2 |                     1.0000 |                   0.5000  -- Bybit
```

### 2. Данные в позициях (ПРАВИЛЬНЫЕ)

```sql
SELECT symbol, trailing_activation_percent, trailing_callback_percent, opened_at
FROM monitoring.positions
WHERE status = 'active'
ORDER BY opened_at DESC
LIMIT 5;

  symbol   | trailing_activation_percent | trailing_callback_percent | opened_at
-----------+-----------------------------+---------------------------+------------
 CRVUSDT   |                      1.0000 |                    0.4000 | 16:50:42  ✅
 KAITOUSDT |                      1.0000 |                    0.4000 | 16:50:35  ✅
 XCHUSDT   |                      1.0000 |                    0.5000 | 16:50:12  ✅
 ZECUSDT   |                      1.0000 |                    0.5000 | 14:35:39  ✅
```

**Position Manager правильно сохраняет в БД!**

### 3. Trailing Stop создание (НЕПРАВИЛЬНЫЕ)

Логи для ZECUSDT (открыта 20:35:26):

```
2025-11-02 20:35:27 - trailing_stop_created: {
  'symbol': 'ZECUSDT',
  'entry_price': 384.22,
  'activation_price': 391.9044,
  'activation_percent': 2.0,      ❌ ДОЛЖНО БЫТЬ 1.0!
  'callback_percent': 0.5
}
```

**Расхождение**:
- БД: `trailing_activation_percent = 1.0`
- TS: `activation_percent = 2.0` (из ENV)

---

## 🐛 ROOT CAUSE ANALYSIS

### ЦЕПОЧКА ДАННЫХ

#### ✅ ЭТАП 1: Wave Processing → DB (РАБОТАЕТ)

`core/signal_processor_websocket.py:575-581`:
```python
return {
    'max_trades_filter': db_params['max_trades_filter'],
    'stop_loss_filter': db_params.get('stop_loss_filter'),
    'trailing_activation_filter': db_params.get('trailing_activation_filter'),  # ✅ 1.0
    'trailing_distance_filter': db_params.get('trailing_distance_filter')        # ✅ 0.4
}
```

#### ✅ ЭТАП 2: Position Creation → DB (РАБОТАЕТ)

`core/position_manager.py:1210-1239`:
```python
# Get trailing params from monitoring.params
if exchange_params:
    if exchange_params.get('trailing_activation_filter') is not None:
        trailing_activation_percent = float(exchange_params['trailing_activation_filter'])  # ✅ 1.0

# Save to DB
{
    'trailing_activation_percent': trailing_activation_percent,  # ✅ 1.0 сохраняется в БД
    'trailing_callback_percent': trailing_callback_percent
}
```

#### ❌ ЭТАП 3: TS Creation (НЕ РАБОТАЕТ)

`core/position_manager.py:1317-1323`:
```python
trailing_manager.create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=position.entry_price,
    quantity=position.quantity,
    initial_stop=to_decimal(atomic_result['stop_loss_price'])
)
# ❌ position_params НЕ ПЕРЕДАЕТСЯ!
```

`protection/trailing_stop.py:514-523`:
```python
if position_params and position_params.get('trailing_activation_percent') is not None:
    # Use per-position params from monitoring.positions
    activation_percent = Decimal(str(position_params['trailing_activation_percent']))
    logger.debug(f"📊 {symbol}: Using per-position trailing params...")
else:
    # ❌ Fallback to config (ENV)
    activation_percent = self.config.activation_percent  # ❌ 2.0 из ENV!
    logger.debug(f"📊 {symbol}: Using config trailing params (fallback)...")
```

---

## 📍 ПРОБЛЕМНЫЕ МЕСТА В КОДЕ

### 1. position_manager.py:1317 (atomic position opening)

```python
# ❌ БАГ: не передается position_params
await trailing_manager.create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=position.entry_price,
    quantity=position.quantity,
    initial_stop=to_decimal(atomic_result['stop_loss_price'])
)

# ✅ ДОЛЖНО БЫТЬ:
await trailing_manager.create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=position.entry_price,
    quantity=position.quantity,
    initial_stop=to_decimal(atomic_result['stop_loss_price']),
    position_params={
        'trailing_activation_percent': trailing_activation_percent,
        'trailing_callback_percent': trailing_callback_percent
    }
)
```

### 2. position_manager.py:1613 (non-atomic position opening)

Аналогично - `position_params` не передается.

### 3. position_manager.py:644 (position sync/restoration)

Аналогично - `position_params` не передается.

---

## ✅ ПРОВЕРКА ГИПОТЕЗЫ (3 СПОСОБА)

### Метод 1: Проверка БД vs Логи

**БД (ZECUSDT):**
```sql
SELECT trailing_activation_percent FROM monitoring.positions WHERE symbol='ZECUSDT';
-- Result: 1.0000 ✅
```

**Логи (ZECUSDT):**
```
trailing_stop_created: {'activation_percent': 2.0}  ❌
```

**Вывод:** Расхождение подтверждено.

### Метод 2: Анализ кода

**Факты:**
1. `create_trailing_stop()` принимает `position_params: Optional[Dict] = None`
2. При вызове из `position_manager.py` параметр НЕ передается
3. Fallback срабатывает: `activation_percent = self.config.activation_percent` (2.0 из ENV)

**Вывод:** Логика подтверждена - код использует ENV fallback.

### Метод 3: Временная корреляция

**Факты:**
1. До 16:50: позиции с `trailing_activation_percent = 2.0` (старые, до обновления params)
2. После 16:50: позиции с `trailing_activation_percent = 1.0` (новые, после обновления params)
3. НО: TS для новых позиций создается с `activation_percent = 2.0`

**Вывод:** Position manager использует новые параметры (1.0) при сохранении в БД, но TS создается со старыми (2.0 из ENV).

---

## 🎯 РЕКОМЕНДАЦИИ

### PRIORITY 1: FIX IMMEDIATE

**Файл:** `core/position_manager.py`
**Строки:** 1317, 1613, 644, 914

**Действие:** Передать `position_params` в `create_trailing_stop()`:

```python
position_params={
    'trailing_activation_percent': trailing_activation_percent,
    'trailing_callback_percent': trailing_callback_percent
}
```

### PRIORITY 2: VERIFICATION

После фикса проверить:
1. Логи создания TS показывают `activation_percent = 1.0`
2. События `trailing_stop_created` содержат корректные значения
3. Активация TS происходит при 1% (не 2%)

### PRIORITY 3: TESTING

Тестовые кейсы:
1. Открыть новую позицию → проверить `activation_percent` в логах
2. Дождаться 1% profit → проверить что TS активируется
3. Проверить что значения берутся из таблицы, а не из ENV

---

## 📈 IMPACT ASSESSMENT

**До фикса:**
- TS активируется при 2% profit (ENV)
- Параметры из БД игнорируются при создании TS
- Невозможно централизованно управлять параметрами через БД

**После фикса:**
- TS активируется при 1% profit (из БД)
- Централизованное управление параметрами работает
- Разные параметры для разных бирж (Binance: 0.4%, Bybit: 0.5%)

---

## ✅ CONCLUSION

**Root Cause:** `position_params` не передается в `trailing_manager.create_trailing_stop()`

**Fix Location:** `core/position_manager.py` (4 места)

**Verification:** Проверить логи `trailing_stop_created` после фикса

**Status:** ✅ READY FOR IMPLEMENTATION
