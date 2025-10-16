# CODE AUDIT: Stop Loss Calculation Logic

**Дата аудита:** 2025-10-15
**Аудитор:** Claude Code
**Задача:** Проверить гипотезу о неправильном расчете SL для LONG позиций
**Статус:** ✅ АУДИТ ЗАВЕРШЕН

---

## EXECUTIVE SUMMARY

### 🔍 Гипотеза

> Ошибка в расчете target SL price для LONG позиций в `core/stop_loss_manager.py`

### ✅ Результат аудита

**Гипотеза ОПРОВЕРГНУТА частично:**
- ❌ Функция `calculate_stop_loss()` работает **КОРРЕКТНО**
- ❌ `StopLossManager` передает цену **без изменений**
- ✅ **ПРОБЛЕМА НАЙДЕНА** в другом месте: `position_manager.py:2388-2415`

### 🎯 Корневая причина

**Неправильная логика "drift compensation"** в методе `check_positions_protection()`:

```python
# position_manager.py:2394-2401
if price_drift_pct > stop_loss_percent_decimal:
    # Price has moved significantly - use current price as base
    logger.warning(f"Using current price {current_price} instead of entry {entry_price}")
    base_price = current_price  # ← ПРОБЛЕМА!
```

**Что происходит:**
1. Entry price: **1.772732 USDT**
2. Current price: **3.310000 USDT** (цена выросла на +86.72%)
3. Drift threshold: **2%** (stop_loss_percent)
4. Drift: **86.72% > 2%** → использует current price как базу
5. SL = 3.310 - 2% = **3.243800 USDT** ← **ВЫШЕ entry!**

**Bybit отклоняет:** SL для LONG должен быть **ниже** entry price (1.616-1.772), но получает 3.24.

---

## ДЕТАЛЬНЫЙ АНАЛИЗ КОДА

### 1. Функция `calculate_stop_loss()` в `utils/decimal_utils.py:118-147`

**Статус:** ✅ **КОРРЕКТНА**

```python
def calculate_stop_loss(
    entry_price: Decimal,
    side: str,
    stop_loss_percent: Decimal,
    tick_size: Optional[Decimal] = None
) -> Decimal:
    sl_distance = entry_price * (stop_loss_percent / Decimal('100'))

    if side.lower() == 'long':
        sl_price = entry_price - sl_distance  # ✅ ПРАВИЛЬНО: SL ниже entry
    else:  # short
        sl_price = entry_price + sl_distance  # ✅ ПРАВИЛЬНО: SL выше entry

    return sl_price
```

**Проверка логики:**

| Side  | Entry | SL% | Expected SL | Calculation | Result |
|-------|-------|-----|-------------|-------------|--------|
| LONG  | 100   | 2%  | 98 (ниже)   | 100 - 2     | ✅ 98  |
| SHORT | 100   | 2%  | 102 (выше)  | 100 + 2     | ✅ 102 |

**Вывод:** Функция работает корректно для обоих направлений.

---

### 2. Метод `StopLossManager.set_stop_loss()` в `core/stop_loss_manager.py:157-227`

**Статус:** ✅ **КОРРЕКТЕН**

```python
async def set_stop_loss(
    self,
    symbol: str,
    side: str,
    amount: float,
    stop_price: float  # ← Принимает ГОТОВУЮ цену
) -> Dict:
    self.logger.info(f"Setting Stop Loss for {symbol} at {stop_price}")

    # ... validation ...

    if self.exchange_name == 'bybit':
        return await self._set_bybit_stop_loss(symbol, stop_price)
    else:
        return await self._set_generic_stop_loss(symbol, side, amount, stop_price)
```

**Анализ:**
- Метод **НЕ вычисляет** SL price
- Принимает готовое значение `stop_price` и передает его в биржу
- Не модифицирует цену

**Вывод:** StopLossManager передает цену **без изменений**. Проблема НЕ здесь.

---

### 3. Метод `_set_bybit_stop_loss()` в `core/stop_loss_manager.py:327-356`

**Статус:** ✅ **КОРРЕКТЕН**

```python
async def _set_bybit_stop_loss(self, symbol: str, stop_price: float) -> Dict:
    bybit_symbol = symbol.replace('/', '').replace(':USDT', '')
    sl_price_formatted = self.exchange.price_to_precision(symbol, stop_price)

    params = {
        'category': 'linear',
        'symbol': bybit_symbol,
        'stopLoss': str(sl_price_formatted),  # ← Передает цену как есть
        'positionIdx': 0,
        'slTriggerBy': 'LastPrice',
        'tpslMode': 'Full'
    }

    result = await self.exchange.private_post_v5_position_trading_stop(params)
```

**Анализ:**
- Форматирует цену через `price_to_precision` (округление)
- Отправляет в Bybit API **без изменения направления**
- Не проверяет что SL корректен относительно entry

**Вывод:** Метод корректно передает цену в API. Проблема НЕ здесь.

---

### 4. ❌ **ПРОБЛЕМА НАЙДЕНА:** Метод `check_positions_protection()` в `position_manager.py:2366-2415`

**Статус:** ❌ **НЕКОРРЕКТНАЯ ЛОГИКА "DRIFT COMPENSATION"**

#### Код с проблемой:

```python
# STEP 1: Get current market price
ticker = await exchange.exchange.fetch_ticker(position.symbol)
current_price = float(mark_price or ticker.get('last') or 0)

# STEP 2: Calculate price drift from entry
entry_price = float(position.entry_price)
price_drift_pct = abs((current_price - entry_price) / entry_price)

# STEP 3: Choose base price for SL calculation
stop_loss_percent = self.config.stop_loss_percent
stop_loss_percent_decimal = float(stop_loss_percent) / 100  # 2.0 -> 0.02

if price_drift_pct > stop_loss_percent_decimal:  # ← ПРОБЛЕМА!
    # Price has moved significantly - use current price as base
    logger.warning(
        f"⚠️ {position.symbol}: Price drifted {price_drift_pct*100:.2f}% "
        f"(threshold: {stop_loss_percent*100:.2f}%). Using current price {current_price:.6f} "
        f"instead of entry {entry_price:.6f} for SL calculation"
    )
    base_price = current_price  # ← ОШИБКА: использует current вместо entry
else:
    base_price = entry_price

# STEP 4: Calculate SL from chosen base price
stop_loss_price = calculate_stop_loss(
    entry_price=Decimal(str(base_price)),  # ← Неправильная база!
    side=position.side,
    stop_loss_percent=Decimal(str(stop_loss_percent))
)
```

#### Анализ проблемы:

**Реальный сценарий для HNT/USDT:**

```
Entry price:    1.772732 USDT
Current price:  3.310000 USDT
Price drift:    |3.310 - 1.772| / 1.772 = 0.8672 = 86.72%
Threshold:      2% (stop_loss_percent)

Условие: 86.72% > 2% → TRUE
Действие: base_price = current_price = 3.310

Расчет SL:
  side = 'long'
  sl_distance = 3.310 * 0.02 = 0.0662
  sl_price = 3.310 - 0.0662 = 3.243800 USDT

Результат: SL = 3.244 USDT (ВЫШЕ entry 1.772!)
```

**Почему Bybit отклоняет:**

```json
{
  "retCode": 10001,
  "retMsg": "StopLoss:324000000 set for Buy position should lower than base_price:161600000??LastPrice"
}
```

Расшифровка:
- `StopLoss: 324000000` = 3.24 USDT (с 7 decimal places)
- `base_price: 161600000` = 1.616 USDT
- Ошибка: SL (3.24) должен быть **ниже** base_price (~1.616)

**base_price на Bybit** ≠ current_price из бота!
**base_price** = entry price позиции на бирже

---

### 5. Логика "Drift Compensation" - анализ намерений

#### Комментарий в коде:

```python
# CRITICAL FIX (2025-10-13): Use current_price instead of entry_price when price
# has drifted significantly. This prevents "base_price validation" errors from Bybit.
# See: CORRECT_SOLUTION_SL_PRICE_DRIFT.md for details
```

**Предполагаемая цель:**
- Избежать ошибок валидации Bybit при большом drift
- Адаптировать SL к текущей рыночной ситуации

**Фактический эффект:**
- Создает SL **в неправильном направлении** для LONG позиций
- Bybit отклоняет, потому что SL выше entry
- **Противоположный эффект** от ожидаемого

#### Почему логика неправильна:

**Для LONG позиций:**
- Entry: 1.772
- Price → 3.310 (рост +86%)
- Drift compensation: base = 3.310
- SL = 3.310 - 2% = **3.244** ← **ВЫШЕ entry!**

**Правильная логика должна быть:**
- SL всегда **ниже entry** для LONG
- SL всегда **выше entry** для SHORT
- Независимо от current price

**Current price можно использовать для:**
- Trailing stop (перемещение SL за ценой)
- Но **НЕ для initial SL установки**

---

## ДОКАЗАТЕЛЬСТВА ИЗ ЛОГОВ

### Лог #1: Drift compensation срабатывает

```
2025-10-15 01:18:11,403 - core.position_manager - WARNING -
⚠️ HNTUSDT: Price drifted 86.72% (threshold: 200.00%).
Using current price 3.310000 instead of entry 1.772732 for SL calculation

2025-10-15 01:18:11,403 - core.position_manager - INFO -
📊 HNTUSDT SL calculation:
   entry=1.772732,
   current=3.310000,
   base=3.310000,      ← base = current (неправильно!)
   SL=3.243800         ← SL выше entry!
```

### Лог #2: Bybit отклоняет

```
2025-10-15 01:18:13,110 - core.stop_loss_manager - ERROR -
Failed to set Stop Loss for HNTUSDT: bybit {
  "retCode":10001,
  "retMsg":"StopLoss:324000000 set for Buy position should lower than base_price:161600000??LastPrice"
}
```

**Расшифровка:**
- SL который пытается установить: **3.24** (324000000)
- Base price на Bybit: **1.616** (161600000)
- Ошибка: 3.24 > 1.616 для LONG → неправильно

### Лог #3: Попытка с entry price (но тоже отклоняется)

```
2025-10-15 01:18:19,144 - core.stop_loss_manager - INFO -
Setting Stop Loss for HNTUSDT at 1.7372773600000000

2025-10-15 01:18:20,168 - core.stop_loss_manager - ERROR -
Failed to set Stop Loss for HNTUSDT: bybit {
  "retCode":10001,
  "retMsg":"StopLoss:174000000 set for Buy position should lower than base_price:161600000??LastPrice"
}
```

**Расшифровка:**
- SL: **1.737** (174000000)
- Base price: **1.616** (161600000)
- 1.737 > 1.616 → все еще выше!

**Вывод:** Entry price в базе (1.772) **НЕ совпадает** с entry price на бирже (1.616).

---

## ROOT CAUSE ANALYSIS

### Проблема #1: Неправильная логика drift compensation

**Файл:** `core/position_manager.py:2394-2401`

**Текущая логика:**
```python
if price_drift_pct > stop_loss_percent_decimal:
    base_price = current_price  # ← НЕПРАВИЛЬНО
```

**Проблема:**
- Использует current_price как базу для SL
- Для LONG с ростом цены создает SL **выше** entry
- Bybit отклоняет такой SL

**Правильная логика:**
- **ВСЕГДА** использовать entry_price как базу для initial SL
- Current_price использовать только для trailing stop (перемещение существующего SL)

---

### Проблема #2: Расхождение entry price между базой и биржей

**База данных:** entry_price = **1.772732**
**Bybit API:** base_price = **1.616000**

**Возможные причины:**
1. **Усреднение позиции** (DCA) на бирже, но не обновлено в базе
2. **Частичное закрытие** с последующим открытием
3. **Старая позиция** не синхронизировалась

**Эффект:**
- SL вычисляется от 1.772 → 1.737
- Bybit ожидает SL < 1.616
- 1.737 > 1.616 → отклонение

---

### Проблема #3: Отсутствие pre-validation перед API call

**Текущее состояние:**
- Код вычисляет SL
- Отправляет в Bybit
- Bybit отклоняет
- Retry 3 раза
- Все 3 попытки проваливаются

**Правильный подход:**
- **ДО отправки в API** проверить:
  - Для LONG: `sl_price < entry_price`
  - Для SHORT: `sl_price > entry_price`
- Если проверка не прошла → логировать ошибку, не отправлять

---

## ТЕСТИРОВАНИЕ ГИПОТЕЗЫ

### ✅ Гипотеза 1: `calculate_stop_loss()` неправильно вычисляет SL

**Статус:** ❌ ОПРОВЕРГНУТА

**Доказательство:**
```python
# Для LONG:
sl_price = entry_price - sl_distance  # Корректно: SL ниже entry

# Тест:
entry = 100, sl% = 2%
sl_distance = 100 * 0.02 = 2
sl_price = 100 - 2 = 98  ✅ Правильно (ниже entry)
```

---

### ✅ Гипотеза 2: `StopLossManager` меняет направление SL

**Статус:** ❌ ОПРОВЕРГНУТА

**Доказательство:**
- `set_stop_loss()` принимает `stop_price` и передает **без изменений**
- `_set_bybit_stop_loss()` передает в API **как есть**
- Нет кода, который меняет знак или направление

---

### ✅ Гипотеза 3 (новая): Drift compensation использует неправильную базу

**Статус:** ✅ **ПОДТВЕРЖДЕНА**

**Доказательство:**
```python
# Из логов:
entry = 1.772732
current = 3.310000
drift = 86.72% > 2%

# Код выбирает:
base_price = current_price  # ← 3.310

# Расчет SL:
sl = 3.310 - (3.310 * 0.02) = 3.244  # ВЫШЕ entry!

# Bybit отклоняет:
"StopLoss:324000000 should lower than base_price:161600000"
```

---

## РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ

### 🔴 КРИТИЧНО: Исправить drift compensation логику

**Файл:** `core/position_manager.py:2388-2415`

**Текущий код (НЕПРАВИЛЬНЫЙ):**
```python
if price_drift_pct > stop_loss_percent_decimal:
    base_price = current_price  # ← УБРАТЬ
```

**Правильный вариант #1: Всегда использовать entry price**
```python
# Убрать drift compensation полностью для initial SL
base_price = entry_price  # Всегда!

# Drift compensation применять ТОЛЬКО для trailing stop
```

**Правильный вариант #2: Синхронизировать entry с биржи**
```python
# Получить РЕАЛЬНЫЙ entry price с биржи
positions = await exchange.fetch_positions(symbol)
real_entry_price = positions[0]['entryPrice']

# Обновить в базе если отличается
if abs(real_entry_price - position.entry_price) > threshold:
    position.entry_price = real_entry_price

# Использовать РЕАЛЬНЫЙ entry для SL
base_price = real_entry_price
```

**Правильный вариант #3: Добавить direction validation**
```python
# После расчета SL, проверить направление
if position.side == 'long':
    if sl_price >= entry_price:
        raise ValueError(f"LONG SL must be < entry: {sl_price} >= {entry_price}")
elif position.side == 'short':
    if sl_price <= entry_price:
        raise ValueError(f"SHORT SL must be > entry: {sl_price} <= {entry_price}")
```

---

### 🔴 КРИТИЧНО: Добавить pre-validation перед API call

**Файл:** `core/stop_loss_manager.py:327` (в начале `_set_bybit_stop_loss`)

```python
async def _set_bybit_stop_loss(self, symbol: str, stop_price: float) -> Dict:
    # ===== ДОБАВИТЬ PRE-VALIDATION =====

    # Получить позицию с биржи для проверки
    positions = await self.exchange.fetch_positions([symbol])
    position = next((p for p in positions if p['symbol'] == symbol), None)

    if not position:
        raise ValueError(f"Position {symbol} not found on exchange")

    entry_price = float(position['entryPrice'])
    side = position['side']  # 'long' or 'short'

    # Validate SL direction
    if side == 'long':
        if stop_price >= entry_price:
            raise ValueError(
                f"LONG SL validation failed: SL {stop_price} >= entry {entry_price}. "
                f"For LONG, SL must be BELOW entry price."
            )
    else:  # short
        if stop_price <= entry_price:
            raise ValueError(
                f"SHORT SL validation failed: SL {stop_price} <= entry {entry_price}. "
                f"For SHORT, SL must be ABOVE entry price."
            )

    # ===== END VALIDATION =====

    # Existing code...
    bybit_symbol = symbol.replace('/', '').replace(':USDT', '')
    # ...
```

---

### ⚠️ ВЫСОКИЙ ПРИОРИТЕТ: Синхронизация entry price с биржей

**Проблема:** Entry price в базе (1.772) ≠ entry на бирже (1.616)

**Решение:**
1. При каждой проверке SL получать **реальный entry** с биржи
2. Сравнивать с entry в базе
3. Если разница > 1% → обновить базу
4. Логировать все расхождения

**Код:**
```python
# В check_positions_protection()
positions_on_exchange = await exchange.fetch_positions([position.symbol])
real_position = next((p for p in positions_on_exchange if p['symbol'] == position.symbol), None)

if real_position:
    real_entry = float(real_position['entryPrice'])
    db_entry = float(position.entry_price)

    diff_pct = abs((real_entry - db_entry) / db_entry) * 100

    if diff_pct > 1.0:  # Расхождение > 1%
        logger.warning(
            f"⚠️ Entry price mismatch for {position.symbol}: "
            f"DB={db_entry}, Exchange={real_entry}, diff={diff_pct:.2f}%"
        )

        # Обновить в базе
        position.entry_price = real_entry
        # session.commit()
```

---

### 🔵 СРЕДНИЙ ПРИОРИТЕТ: Улучшить логирование

**Добавить:**
1. Debug лог с полными деталями расчета SL
2. Warning при обнаружении drift > 5%
3. Error с детальной информацией при отклонении Bybit

**Код:**
```python
logger.debug(
    f"📊 SL calculation for {symbol}:\n"
    f"  Entry (DB):      {position.entry_price:.6f}\n"
    f"  Entry (Exchange): {real_entry:.6f}\n"
    f"  Current price:   {current_price:.6f}\n"
    f"  Side:            {position.side}\n"
    f"  SL %:            {stop_loss_percent}%\n"
    f"  Base price:      {base_price:.6f}\n"
    f"  Calculated SL:   {stop_loss_price:.6f}\n"
    f"  Direction OK:    {sl_direction_check}"
)
```

---

## ПЛАН ТЕСТИРОВАНИЯ ПОСЛЕ ИСПРАВЛЕНИЯ

### Тест #1: Unit-тест для drift compensation

```python
def test_initial_sl_always_uses_entry_price():
    """Initial SL should ALWAYS use entry price, not current"""

    # Scenario: LONG position with big price rise
    entry = 1.772
    current = 3.310
    sl_percent = 2.0

    # Expected: SL = entry - 2% = 1.737
    expected_sl = 1.737

    # Current buggy behavior: SL = current - 2% = 3.244
    buggy_sl = 3.244

    # Test
    sl = calculate_initial_sl(entry, current, 'long', sl_percent)

    assert sl == expected_sl, f"SL should be based on entry, not current"
    assert sl < entry, f"LONG SL must be below entry"
```

### Тест #2: Integration тест с mock Bybit

```python
async def test_bybit_rejects_wrong_direction_sl():
    """Bybit should reject SL in wrong direction"""

    # Mock position on exchange
    mock_position = {
        'symbol': 'HNT/USDT:USDT',
        'side': 'long',
        'entryPrice': 1.616,
        'contracts': 59.88
    }

    # Try to set SL above entry (wrong!)
    wrong_sl = 3.244

    with pytest.raises(Exception) as exc:
        await sl_manager.set_stop_loss(
            symbol='HNT/USDT:USDT',
            side='sell',
            amount=59.88,
            stop_price=wrong_sl
        )

    assert 'should lower than base_price' in str(exc.value)
```

### Тест #3: Live тест на testnet

1. Открыть LONG позицию на testnet
2. Дождаться роста цены > 5%
3. Проверить что SL устанавливается **ниже entry**
4. Проверить что Bybit принимает SL

---

## ЗАКЛЮЧЕНИЕ

### ✅ Гипотеза проверена

**Исходная гипотеза:**
> Ошибка в расчете target SL price для LONG позиций в `core/stop_loss_manager.py`

**Результат:**
- ❌ Гипотеза **опровергнута** для `StopLossManager`
- ✅ Проблема **найдена** в `PositionManager.check_positions_protection()`

---

### 🎯 Корневая причина

**Файл:** `core/position_manager.py:2388-2415`
**Проблема:** Drift compensation логика использует `current_price` вместо `entry_price` как базу для SL расчета

**Эффект:**
- При росте цены LONG позиции: SL = current - 2% → SL **выше** entry
- Bybit отклоняет: SL для LONG должен быть **ниже** entry

---

### 📋 Приоритеты исправления

| # | Задача | Приоритет | Время |
|---|--------|-----------|-------|
| 1 | Убрать/исправить drift compensation | 🔴 CRITICAL | 15 мин |
| 2 | Добавить pre-validation перед API | 🔴 CRITICAL | 20 мин |
| 3 | Синхронизация entry с биржей | ⚠️ HIGH | 30 мин |
| 4 | Улучшить логирование | 🔵 MEDIUM | 15 мин |
| 5 | Unit-тесты | 🔵 MEDIUM | 30 мин |
| 6 | Integration тесты | 🟢 LOW | 45 мин |
| **TOTAL** | | | **~2.5 часа** |

---

### 🚨 Немедленные действия

1. ✅ **Аудит завершен** - корневая причина найдена
2. 🔴 **Ручное исправление** - установить SL для HNTUSDT на бирже вручную
3. 🔴 **Code fix** - исправить drift compensation логику
4. 🔴 **Testing** - unit + integration тесты
5. 🔴 **Deploy** - deploy после тестов
6. ⚠️ **Monitor** - мониторинг первые 24 часа

---

**Аудит завершен:** 2025-10-15 01:35:00
**Статус:** ✅ ПРОБЛЕМА ИДЕНТИФИЦИРОВАНА
**Следующий шаг:** ИСПРАВЛЕНИЕ КОДА (отдельная задача)
