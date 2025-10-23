# Trailing Stop: Полный отчёт о логике обновления SL
**Дата**: 2025-10-20
**Автор**: Claude Code Investigation

---

## Оглавление
1. [Краткое резюме](#краткое-резюме)
2. [Конфигурация](#конфигурация)
3. [Основной flow обновления](#основной-flow-обновления)
4. [Условия обновления SL](#условия-обновления-sl)
5. [Условия сохранения пиков в БД](#условия-сохранения-пиков-в-бд)
6. [Расчёт trailing distance](#расчёт-trailing-distance)
7. [Примеры работы](#примеры-работы)

---

## Краткое резюме

**Основная логика**: SL обновляется, когда цена движется в благоприятном направлении и выполняются все проверки:
1. ✅ Новый SL лучше текущего (для short: ниже, для long: выше)
2. ✅ Улучшение >= 0.1% ИЛИ прошло >= 60 секунд с последнего обновления
3. ✅ (Emergency override: если улучшение >= 1.0%, обновляется немедленно, минуя все лимиты)

**Ответ на твой вопрос**: `min_improvement = 0.2%` - это **НЕВЕРНО**!
**Правильный ответ**: `min_improvement = 0.1%` (задаётся в `config/settings.py:53`)

---

## Конфигурация

### 1. Глобальные параметры (config/settings.py)

```python
# Базовые параметры TS
trailing_activation_percent: Decimal = Decimal('1.5')  # Активация TS при профите >= 1.5%
trailing_callback_percent: Decimal = Decimal('0.5')    # Расстояние SL от пика (0.5%)

# Параметры обновления SL (Freqtrade-inspired)
trailing_min_update_interval_seconds: int = 60           # Мин 60 сек между обновлениями
trailing_min_improvement_percent: Decimal = Decimal('0.1')  # ⚠️ ЗДЕСЬ! Обновлять только если >= 0.1%
trailing_alert_if_unprotected_window_ms: int = 500      # Алерт если без защиты > 500ms
```

**Где используется**:
- `config.trading.trailing_min_update_interval_seconds` → Rule 1 в `_should_update_stop_loss()` (строка 900)
- `config.trading.trailing_min_improvement_percent` → Rule 2 в `_should_update_stop_loss()` (строка 908)

---

### 2. TrailingStopConfig параметры (protection/trailing_stop.py:38-62)

```python
@dataclass
class TrailingStopConfig:
    activation_percent: Decimal = Decimal('1.5')  # Активация при профите >= 1.5%
    callback_percent: Decimal = Decimal('0.5')    # Дистанция от пика = 0.5%

    # Продвинутые фичи
    use_atr: bool = False                         # Использовать ATR для динамической дистанции
    atr_multiplier: Decimal = Decimal('2.0')

    step_activation: bool = False                 # Шаговая активация (разная дистанция для разного профита)
    activation_steps: List[Dict] = [
        {'profit': 1.0, 'distance': 0.5},         # При 1% профита → дистанция 0.5%
        {'profit': 2.0, 'distance': 0.3},         # При 2% профита → дистанция 0.3%
        {'profit': 3.0, 'distance': 0.2},         # При 3% профита → дистанция 0.2%
    ]

    breakeven_at: Optional[Decimal] = Decimal('0.5')  # Передвинуть SL в breakeven при 0.5%

    # Time-based активация
    time_based_activation: bool = False           # Активировать по времени даже без профита
    min_position_age_minutes: int = 10           # Мин возраст позиции для time-based активации

    # Acceleration (ужесточение SL при сильном импульсе)
    accelerate_on_momentum: bool = False
    momentum_threshold: Decimal = Decimal('0.1')  # Порог импульса (% в минуту)
```

---

### 3. Константы для сохранения пиков (protection/trailing_stop.py:24-26)

```python
TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC = 10    # Мин 10 сек между сохранениями пика в БД
TRAILING_MIN_PEAK_CHANGE_PERCENT = 0.2      # ⚠️ ЗДЕСЬ 0.2%! Сохранять если пик изменился > 0.2%
TRAILING_EMERGENCY_PEAK_CHANGE = 1.0        # Emergency: сохранять немедленно если пик изменился > 1.0%
```

**Важно!** Это параметры для **сохранения пиков в БД**, НЕ для обновления SL!

---

## Основной flow обновления

### 1. update_price() вызывается от WebSocket (строка 406)

```python
async def update_price(self, symbol: str, price: float) -> Optional[Dict]:
    """Вызывается на каждый тик цены от WebSocket"""

    # 1. Обновить current_price
    ts.current_price = Decimal(str(price))

    # 2. Обновить пики (highest/lowest)
    if ts.side == 'long':
        if ts.current_price > ts.highest_price:
            ts.highest_price = ts.current_price  # ✅ Новый максимум
    else:
        if ts.current_price < ts.lowest_price:
            ts.lowest_price = ts.current_price    # ✅ Новый минимум

    # 3. Сохранить пик в БД (если нужно)
    if peak_updated and ts.state == ACTIVE:
        should_save, skip_reason = _should_save_peak(ts, current_peak)
        if should_save:
            await _save_state(ts)  # Сохранить в БД

    # 4. State machine
    if ts.state == INACTIVE or ts.state == WAITING:
        return await _check_activation(ts)      # Проверить активацию
    elif ts.state == ACTIVE:
        return await _update_trailing_stop(ts)  # ⚠️ Попытка обновить SL
```

---

### 2. _update_trailing_stop() вычисляет новый SL (строка 582)

```python
async def _update_trailing_stop(self, ts: TrailingStopInstance):
    """Попытка обновить SL если цена движется благоприятно"""

    # 1. Получить расстояние от пика (0.5% по умолчанию)
    distance = _get_trailing_distance(ts)  # → 0.5%

    # 2. Вычислить potential_stop
    if ts.side == 'long':
        potential_stop = ts.highest_price * (1 - distance/100)  # SL ниже пика
        if potential_stop > ts.current_stop_price:              # Только если ВЫШЕ текущего
            new_stop_price = potential_stop
    else:
        potential_stop = ts.lowest_price * (1 + distance/100)   # SL выше пика
        if potential_stop < ts.current_stop_price:              # Только если НИЖЕ текущего
            new_stop_price = potential_stop

    # 3. Если есть улучшение → проверить условия
    if new_stop_price:
        should_update, skip_reason = _should_update_stop_loss(ts, new_stop_price, old_stop)

        if not should_update:
            logger.debug(f"⏭️ {ts.symbol}: SKIPPED - {skip_reason}")
            return None  # ⛔ НЕ ОБНОВЛЯТЬ

        # 4. ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ → ОБНОВИТЬ
        ts.current_stop_price = new_stop_price
        ts.update_count += 1
        await _update_stop_order(ts)  # Обновить SL на бирже
        logger.info(f"📈 {ts.symbol}: SL moved to {new_stop_price}")
```

---

## Условия обновления SL

### Функция: _should_update_stop_loss() (строка 846)

**3 правила проверяются последовательно:**

#### Rule 0: EMERGENCY OVERRIDE (строка 874-883)

```python
EMERGENCY_THRESHOLD = 1.0  # 1.0% улучшение

improvement_percent = abs((new_stop - old_stop) / old_stop * 100)

if improvement_percent >= EMERGENCY_THRESHOLD:
    logger.info(f"⚡ Emergency SL update - {improvement_percent:.2f}% >= 1.0%")
    return (True, None)  # ✅ ОБНОВИТЬ НЕМЕДЛЕННО, минуя все лимиты!
```

**Цель**: Защита от быстрых ценовых движений. Если цена резко ушла в профит (SL улучшился на 1%+), обновляем немедленно.

**Пример**:
- OLD SL: 0.3500
- NEW SL: 0.3465 (для short)
- Improvement: (0.3500 - 0.3465) / 0.3500 * 100 = **1.0%**
- Результат: ✅ **Обновить немедленно** (минуя Rate Limit и Min Improvement)

---

#### Rule 1: RATE LIMITING (строка 885-904)

```python
min_interval = config.trading.trailing_min_update_interval_seconds  # 60 сек

if ts.last_sl_update_time:
    elapsed_seconds = (now - ts.last_sl_update_time).total_seconds()

    if elapsed_seconds < min_interval:
        remaining = min_interval - elapsed_seconds
        return (False, f"rate_limit: {elapsed_seconds:.1f}s elapsed, need {min_interval}s")
```

**Цель**: Предотвратить спам обновлений на биржу. Минимум 60 секунд между обновлениями.

**Пример**:
- Последнее обновление: 30 сек назад
- Результат: ⛔ **SKIP** - "rate_limit: 30.0s elapsed, need 60s (wait 30.0s)"

**Важно**:
- Проверка применяется ТОЛЬКО если `ts.last_sl_update_time` существует (т.е. было хотя бы одно обновление)
- Первое обновление после активации TS НЕ проверяется на rate limit
- Emergency override (Rule 0) **минует** этот лимит

---

#### Rule 2: MINIMUM IMPROVEMENT (строка 906-911)

```python
min_improvement = float(config.trading.trailing_min_improvement_percent)  # 0.1%

if ts.last_updated_sl_price:
    if improvement_percent < min_improvement:
        return (False, f"improvement_too_small: {improvement_percent:.3f}% < {min_improvement}%")
```

**Цель**: Обновлять SL только когда улучшение значительное (>= 0.1%).

**Пример**:
- OLD SL: 0.3500
- NEW SL: 0.3498
- Improvement: (0.3500 - 0.3498) / 0.3500 * 100 = **0.057%**
- Результат: ⛔ **SKIP** - "improvement_too_small: 0.057% < 0.1%"

**Важно**:
- Проверка применяется ТОЛЬКО если `ts.last_updated_sl_price` существует
- Первое обновление после активации НЕ проверяется на min improvement
- Emergency override (Rule 0) **минует** эту проверку

---

### Таблица решений

| Улучшение | Время с последнего update | Результат | Причина |
|-----------|---------------------------|-----------|---------|
| 1.5% | 10 сек | ✅ UPDATE | Emergency override (>= 1.0%) |
| 0.5% | 10 сек | ⛔ SKIP | Rate limit (< 60 сек) |
| 0.5% | 70 сек | ✅ UPDATE | Rate limit OK, improvement OK |
| 0.05% | 70 сек | ⛔ SKIP | Improvement too small (< 0.1%) |
| 0.2% | NULL (первый раз) | ✅ UPDATE | Нет last_sl_update_time → Rate limit не применяется |
| 0.05% | NULL (первый раз) | ✅ UPDATE | Нет last_updated_sl_price → Min improvement не применяется |

---

## Условия сохранения пиков в БД

### Функция: _should_save_peak() (строка 916)

**Зачем?** Пиковые цены (highest/lowest) обновляются в памяти на каждом тике, но сохранять их в БД на каждом тике — это слишком частые записи. Поэтому есть rate limiting.

#### Rule 0: EMERGENCY PEAK SAVE (строка 932-943)

```python
TRAILING_EMERGENCY_PEAK_CHANGE = 1.0  # 1.0%

if ts.last_saved_peak_price:
    peak_change_percent = abs((new_peak - ts.last_saved_peak_price) / ts.last_saved_peak_price * 100)

    if peak_change_percent >= TRAILING_EMERGENCY_PEAK_CHANGE:
        logger.debug(f"⚡ Emergency peak save - {peak_change_percent:.2f}% >= 1.0%")
        return (True, None)
```

**Пример**:
- Last saved peak: 0.3400
- New peak: 0.3434
- Change: 1.0%
- Результат: ✅ **Сохранить немедленно**

---

#### Rule 1: TIME-BASED PEAK SAVE (строка 945-951)

```python
TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC = 10  # 10 сек

if ts.last_peak_save_time:
    elapsed_seconds = (datetime.now() - ts.last_peak_save_time).total_seconds()

    if elapsed_seconds < TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC:
        return (False, f"peak_save_rate_limit: {elapsed_seconds:.1f}s elapsed, need 10s")
```

**Пример**:
- Последнее сохранение: 5 сек назад
- Результат: ⛔ **SKIP** - "peak_save_rate_limit: 5.0s elapsed, need 10s"

---

#### Rule 2: PEAK CHANGE THRESHOLD (строка 953-960)

```python
TRAILING_MIN_PEAK_CHANGE_PERCENT = 0.2  # ⚠️ ЗДЕСЬ 0.2%!

if ts.last_saved_peak_price:
    peak_change_percent = abs((new_peak - ts.last_saved_peak_price) / ts.last_saved_peak_price * 100)

    if peak_change_percent < TRAILING_MIN_PEAK_CHANGE_PERCENT:
        return (False, f"peak_change_too_small: {peak_change_percent:.3f}% < 0.2%")
```

**Пример**:
- Last saved peak: 0.3400
- New peak: 0.3403
- Change: 0.088%
- Результат: ⛔ **SKIP** - "peak_change_too_small: 0.088% < 0.2%"

---

**Итого для пиков**:
- **0.2%** — это порог для сохранения пиков В БД
- **0.1%** — это порог для обновления SL на бирже
- Это **разные** параметры для **разных** операций!

---

## Расчёт trailing distance

### Функция: _get_trailing_distance() (строка 693)

**Базовая логика**: Возвращает расстояние от пика до SL (в процентах).

#### 1. Step-based distance (если включено)

```python
if self.config.step_activation:  # По умолчанию = False
    profit = _calculate_profit_percent(ts)

    for step in reversed(self.config.activation_steps):
        if profit >= step['profit']:
            return Decimal(str(step['distance']))
```

**Пример** (если step_activation=True):
- Profit 3.5% → distance = 0.2%
- Profit 2.5% → distance = 0.3%
- Profit 1.5% → distance = 0.5%

**Смысл**: Чем больше профит, тем **ближе** SL к цене (защита прибыли).

---

#### 2. Momentum-based acceleration (если включено)

```python
if self.config.accelerate_on_momentum:  # По умолчанию = False
    time_diff = (datetime.now() - ts.last_stop_update).seconds / 60
    price_change_rate = abs((ts.current_price - ts.entry_price) / ts.entry_price / time_diff * 100)

    if price_change_rate > self.config.momentum_threshold:  # > 0.1% в минуту
        return self.config.callback_percent * Decimal('0.7')  # 0.5% * 0.7 = 0.35%
```

**Смысл**: Если цена движется очень быстро (сильный импульс), ужесточить SL (уменьшить distance) для защиты прибыли.

---

#### 3. Default

```python
return self.config.callback_percent  # 0.5% (из settings.py)
```

**По умолчанию**: SL находится в **0.5%** от пика.

---

## Примеры работы

### Пример 1: SHORT позиция с обновлением SL

**Начальное состояние**:
- Entry price: 0.3500
- Side: short
- TS ACTIVE
- Current SL: 0.3401
- Lowest price: 0.3384

**Tick 1**: Price = 0.3380
```
1. Update lowest_price: 0.3380 < 0.3384 → lowest_price = 0.3380 ✅
2. Calculate potential_stop: 0.3380 * 1.005 = 0.3397
3. Check: 0.3397 < 0.3401? → YES ✅
4. new_stop_price = 0.3397
5. Improvement: (0.3401 - 0.3397) / 0.3401 * 100 = 0.12%
6. Check Emergency (>= 1.0%)? → NO
7. Check Rate Limit (< 60s)? → last_update = 65s ago → OK ✅
8. Check Min Improvement (>= 0.1%)? → 0.12% >= 0.1% → OK ✅
9. Result: ✅ UPDATE SL: 0.3401 → 0.3397
10. Log: "📈 SYMBOL: SL moved from 0.3401 to 0.3397 (+0.12%)"
```

---

### Пример 2: SHORT позиция со skip (improvement too small)

**Состояние**:
- Current SL: 0.3401
- Lowest price: 0.3400

**Tick 1**: Price = 0.3399
```
1. Update lowest_price: 0.3399 < 0.3400 → lowest_price = 0.3399 ✅
2. Calculate potential_stop: 0.3399 * 1.005 = 0.3416
3. Check: 0.3416 < 0.3401? → NO ⛔
4. Result: NO UPDATE (potential_stop не лучше текущего)
```

**Tick 2**: Price = 0.3398
```
1. Update lowest_price: 0.3398 < 0.3399 → lowest_price = 0.3398 ✅
2. Calculate potential_stop: 0.3398 * 1.005 = 0.3415
3. Check: 0.3415 < 0.3401? → NO ⛔
4. Result: NO UPDATE
```

Видишь проблему? Lowest обновляется, но potential_stop всё равно ХУЖЕ текущего SL!

**Tick 3**: Price = 0.3385
```
1. Update lowest_price: 0.3385 < 0.3398 → lowest_price = 0.3385 ✅
2. Calculate potential_stop: 0.3385 * 1.005 = 0.3402
3. Check: 0.3402 < 0.3401? → NO ⛔
4. Result: NO UPDATE (всё ещё хуже на 0.03%)
```

**Tick 4**: Price = 0.3384
```
1. Update lowest_price: 0.3384 < 0.3385 → lowest_price = 0.3384 ✅
2. Calculate potential_stop: 0.3384 * 1.005 = 0.3401
3. Check: 0.3401 < 0.3401? → NO ⛔ (равны!)
4. Result: NO UPDATE
```

**Tick 5**: Price = 0.3380 (сильное падение)
```
1. Update lowest_price: 0.3380 < 0.3384 → lowest_price = 0.3380 ✅
2. Calculate potential_stop: 0.3380 * 1.005 = 0.3397
3. Check: 0.3397 < 0.3401? → YES ✅
4. new_stop_price = 0.3397
5. Improvement: (0.3401 - 0.3397) / 0.3401 * 100 = 0.12%
6. Check Rate Limit: last_update = 65s ago → OK ✅
7. Check Min Improvement: 0.12% >= 0.1% → OK ✅
8. Result: ✅ UPDATE SL: 0.3401 → 0.3397
```

---

### Пример 3: Emergency override

**Состояние**:
- Current SL: 0.3500
- Lowest price: 0.3450
- Last update: 10 секунд назад (rate limit должен блокировать!)

**Tick**: Price = 0.3415 (резкое падение на 1%!)
```
1. Update lowest_price: 0.3415 < 0.3450 → lowest_price = 0.3415 ✅
2. Calculate potential_stop: 0.3415 * 1.005 = 0.3432
3. Check: 0.3432 < 0.3500? → YES ✅
4. new_stop_price = 0.3432
5. Improvement: (0.3500 - 0.3432) / 0.3500 * 100 = 1.94%
6. Check Emergency (>= 1.0%)? → YES! 1.94% >= 1.0% ⚡
7. Result: ✅ UPDATE IMMEDIATELY (минуя rate limit!)
8. Log: "⚡ Emergency SL update - 1.94% >= 1.0% - bypassing rate limit"
9. Log: "📈 SYMBOL: SL moved from 0.3500 to 0.3432 (+1.94%)"
```

---

## Итоговая таблица параметров

| Параметр | Значение | Где задаётся | Что контролирует |
|----------|----------|--------------|------------------|
| `trailing_activation_percent` | **1.5%** | config/settings.py:48 | Активация TS при профите >= 1.5% |
| `trailing_callback_percent` | **0.5%** | config/settings.py:49 | Расстояние SL от пика |
| `trailing_min_update_interval_seconds` | **60 сек** | config/settings.py:52 | Мин интервал между обновлениями SL |
| **`trailing_min_improvement_percent`** | **0.1%** ⚠️ | config/settings.py:53 | **Мин улучшение для обновления SL** |
| `EMERGENCY_THRESHOLD` | **1.0%** | trailing_stop.py:876 | Emergency override для SL (минует лимиты) |
| `TRAILING_MIN_PEAK_SAVE_INTERVAL_SEC` | **10 сек** | trailing_stop.py:24 | Мин интервал между сохранениями пика в БД |
| `TRAILING_MIN_PEAK_CHANGE_PERCENT` | **0.2%** | trailing_stop.py:25 | Мин изменение пика для сохранения в БД |
| `TRAILING_EMERGENCY_PEAK_CHANGE` | **1.0%** | trailing_stop.py:26 | Emergency save пика в БД |

---

## Выводы

1. **Min improvement для SL = 0.1%**, НЕ 0.2%!
2. **0.2%** — это параметр для сохранения пиков в БД (совсем другая операция)
3. SL обновляется если:
   - Улучшение >= 1.0% (emergency) ИЛИ
   - (Прошло >= 60 сек И улучшение >= 0.1%)
4. Emergency override минует ВСЕ лимиты при улучшении >= 1.0%
5. Первое обновление после активации не проверяется на rate limit и min improvement

---

**Конец отчёта** 📊
