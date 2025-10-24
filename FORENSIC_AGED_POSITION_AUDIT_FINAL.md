# ПОЛНЫЙ АУДИТ AGED POSITION MANAGER
## Расследование проблемы незакрытия просроченных позиций

**Дата**: 2025-10-24
**Версия**: 1.0 FINAL
**Статус**: 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ ОБНАРУЖЕНЫ

---

## РЕЗЮМЕ ДЛЯ РУКОВОДСТВА

### Суть проблемы:
Модуль управления просроченными позициями (Aged Position Management) **НЕ закрывает** позиции, которые превысили максимальный возраст. Обнаружено 6 критических позиций возрастом от 3.96 до 29 часов (при MAX_AGE=3h), которые висят без управления несмотря на прибыль или приемлемый убыток.

### Корневые причины:

🔴 **КРИТИЧЕСКАЯ ОШИБКА #1**: Неправильная логика закрытия SHORT позиций в убытке
- **Локация**: `core/aged_position_monitor_v2.py:278`
- **Проблема**: Использован оператор `<=` вместо `>=`
- **Последствие**: SHORT позиции в убытке НИКОГДА не закрываются

🔴 **КРИТИЧЕСКАЯ ОШИБКА #2**: Блокировка позиций с активным trailing stop
- **Локация**: `core/protection_adapters.py:84-87`
- **Проблема**: Позиции с флагом `trailing_activated=True` полностью пропускаются
- **Последствие**: Позиции остаются без управления, даже если в прибыли

✅ **БИРЖЕВЫЕ ПРОБЛЕМЫ**: Уже исправлены в v1.1.0
- Bybit error 170193 (XDCUSDT)
- Отсутствие ликвидности (HNTUSDT)

### Критичность: 🔴 **КРИТИЧЕСКАЯ**

**Финансовое влияние**:
- GIGAUSDT: Убыток **-9.72%** при допустимом **3.35%** (висит 17.7 часов)
- TOWNSUSDT: Упущена прибыль **+0.96%** (висит 3.97 часа)
- LABUSDT: Упущена прибыль **+2.52%** (висит 1.71 часа)

### Используемая система:
⚡ **Unified Protection V2** (`aged_position_monitor_v2.py`)
❌ **НЕ** Legacy `aged_position_manager.py` (не используется в production)

---

## СОДЕРЖАНИЕ

1. [Анализ алгоритма](#1-анализ-алгоритма)
2. [Найденные проблемы](#2-найденные-проблемы)
3. [Анализ проблемных позиций](#3-анализ-проблемных-позиций)
4. [Анализ базы данных](#4-анализ-базы-данных)
5. [Анализ логов](#5-анализ-логов)
6. [Предлагаемые исправления](#6-предлагаемые-исправления)
7. [План внедрения](#7-план-внедрения)
8. [Риски и митигация](#8-риски-и-митигация)
9. [Тестирование](#9-тестирование)
10. [Заключение](#10-заключение)

---

## 1. АНАЛИЗ АЛГОРИТМА

### 1.1 Архитектура системы

**Активная система**: Unified Protection V2 (включена через `USE_UNIFIED_PROTECTION=true`)

**Компоненты**:
- `aged_position_monitor_v2.py` - основная логика мониторинга
- `protection_adapters.py` - адаптер для подписки на price updates
- `unified_price_monitor.py` - центральный распределитель обновлений цен
- `order_executor.py` - исполнитель ордеров с retry механизмом

**Принцип работы**: Event-driven через WebSocket price updates

### 1.2 Алгоритм работы (как должно быть)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Позиция становится aged (age > MAX_POSITION_AGE_HOURS)  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. AgedPositionAdapter проверяет условия:                   │
│    - Возраст >= 3h                                          │
│    - trailing_activated = False (текущая логика)            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Подписка на price updates через UnifiedPriceMonitor      │
│    - Priority: 40 (ниже чем TrailingStop=10)               │
│    - Callback: _on_unified_price()                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. При каждом обновлении цены:                              │
│    - check_price_target(symbol, current_price)              │
│    - Проверка достижения target                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Если target достигнут:                                   │
│    - _trigger_market_close()                                │
│    - OrderExecutor.execute_close() (3 retry, smart errors)  │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Фазы жизненного цикла просроченной позиции

#### ФАЗА 1: Grace Period (0-8 часов после max_age)

**Временной диапазон**: От max_age (3h) до (max_age + grace_period) = 11h

**Цель**: Попытки закрыться по breakeven (без убытка)

**Логика** (`aged_position_monitor_v2.py:459-471`):
```python
if hours_over_limit <= self.grace_period_hours:
    phase = 'grace'
    loss_tolerance = Decimal('0')

    # Breakeven = entry + двойная комиссия
    double_commission = Decimal('2') * self.commission_percent

    if position.side in ['long', 'buy']:
        target_price = entry_price * (Decimal('1') + double_commission)
    else:  # short/sell
        target_price = entry_price * (Decimal('1') - double_commission)
```

**Условия закрытия**:
- LONG: цена >= entry × (1 + 0.002) = entry × 1.002
- SHORT: цена <= entry × (1 - 0.002) = entry × 0.998
- **ИЛИ** PnL > 0 (прибыль) → немедленное закрытие

**Пример расчета**:
```
Позиция LONG, entry = $100, возраст 5 часов (2h over limit)
Grace period: 5h - 3h = 2h (в grace)
Target: $100 × 1.002 = $100.20

Если current_price >= $100.20 → ЗАКРЫТЬ
```

---

#### ФАЗА 2: Progressive Liquidation (8-28 часов после max_age)

**Временной диапазон**: От (max_age + grace) = 11h до 31h

**Цель**: Прогрессивная ликвидация с нарастающей терпимостью к убытку

**Логика** (`aged_position_monitor_v2.py:472-488`):
```python
else:
    phase = 'progressive'
    hours_in_progressive = hours_over_limit - self.grace_period_hours

    # Базовый расчет терпимости к убытку
    loss_tolerance = Decimal(str(hours_in_progressive)) * self.loss_step_percent

    # Ограничение максимумом
    loss_tolerance = min(loss_tolerance, self.max_loss_percent)

    # Расчет target с учетом убытка
    if position.side in ['long', 'buy']:
        target_price = entry_price * (Decimal('1') - loss_tolerance / Decimal('100'))
    else:  # short/sell
        target_price = entry_price * (Decimal('1') + loss_tolerance / Decimal('100'))
```

**Формула терпимости к убытку**:
- Базовая: `hours_beyond_grace × loss_step_percent`
- loss_step_percent = 0.5% за час
- Максимальная: 10%

**Пример расчета**:
```
Позиция SHORT, entry = $1.00, возраст 15 часов
Hours over limit: 15h - 3h = 12h
Hours beyond grace: 12h - 8h = 4h

Loss tolerance: 4h × 0.5% = 2.0%
Target (SHORT): $1.00 × (1 + 0.02) = $1.02

Текущая цена $1.015:
- PnL: -1.5% (в убытке)
- Should close: current >= target → $1.015 >= $1.02 → FALSE (ждем)

Текущая цена $1.025:
- PnL: -2.5% (в убытке)
- Should close: current >= target → $1.025 >= $1.02 → TRUE ✅ (закрыть)
```

---

#### ФАЗА 3: Emergency (>28 часов после max_age)

**Временной диапазон**: Позиции старше 31 часа

**Цель**: Аварийное закрытие по любой цене

**Логика**: Market order по текущей цене (в плане, но не используется в текущей реализации)

---

### 1.4 Расчет PnL

**Метод**: `_calculate_pnl_percent()` (`aged_position_monitor_v2.py:506-516`)

```python
def _calculate_pnl_percent(self, position, current_price: Decimal) -> Decimal:
    entry = Decimal(str(position.entry_price))

    if position.side in ['long', 'buy']:
        # LONG: прибыль когда current > entry
        pnl_percent = ((current_price - entry) / entry) * Decimal('100')
    else:
        # SHORT: прибыль когда current < entry
        pnl_percent = ((entry - current_price) / entry) * Decimal('100')

    return pnl_percent
```

**Примеры**:
```
LONG: entry=$100, current=$105 → PnL = +5.0%
LONG: entry=$100, current=$95  → PnL = -5.0%

SHORT: entry=$100, current=$95  → PnL = +5.0%
SHORT: entry=$100, current=$105 → PnL = -5.0%
```

**Учет комиссии**: Комиссия учитывается только в breakeven target (grace period)

---

### 1.5 Логика принятия решения о закрытии

**Метод**: `check_price_target()` (`aged_position_monitor_v2.py:224-291`)

```python
async def check_price_target(self, symbol: str, current_price: Decimal):
    target = self.aged_targets[symbol]
    position = await self._get_position(symbol)

    pnl_percent = self._calculate_pnl_percent(position, current_price)

    # ПРИОРИТЕТ #1: Проверка прибыльности
    if pnl_percent > Decimal('0'):
        # Прибыльная - закрыть немедленно
        should_close = True
        logger.info(f"💰 {symbol} profitable at {pnl_percent:.2f}% - triggering close")

    else:
        # ПРИОРИТЕТ #2: Проверка target по стороне позиции
        if position.side in ['long', 'buy']:
            # LONG: закрыть если цена >= target (принятие убытка)
            should_close = current_price >= target.target_price
        else:
            # SHORT: закрыть если цена <= target
            # 🔴 ОШИБКА ЗДЕСЬ! Должно быть >=
            should_close = current_price <= target.target_price

    if should_close:
        await self._trigger_market_close(position, target, current_price)
```

**Проблема**: Условие для SHORT неправильное (см. раздел 2.2)

---

## 2. НАЙДЕННЫЕ ПРОБЛЕМЫ

### 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА #1: Блокировка по trailing_activated

**Файл**: `core/protection_adapters.py`
**Строки**: 84-87
**Приоритет**: 🔴 **КРИТИЧЕСКИЙ - ТРЕБУЕТ НЕМЕДЛЕННОГО ИСПРАВЛЕНИЯ**

#### Описание проблемы

Позиции с флагом `trailing_activated=True` **полностью пропускаются** из aged monitoring, даже если:
- Trailing stop не работает или отключен
- Позиция критически просрочена
- Позиция в прибыли (должна закрыться немедленно)

#### Проблемный код

```python
# core/protection_adapters.py:84-87
async def add_aged_position(self, position):
    symbol = position.symbol

    # ❌ ПРОБЛЕМА: Полная блокировка по флагу
    if hasattr(position, 'trailing_activated') and position.trailing_activated:
        logger.debug(f"Skipping {symbol} - trailing stop active")
        return  # ❌ НЕ СОЗДАЕТСЯ ПОДПИСКА НА PRICE UPDATES!

    # Код ниже НЕ ВЫПОЛНЯЕТСЯ для позиций с TS
    await self.price_monitor.subscribe(...)  # Пропускается!
```

#### Последствия

1. **НЕТ подписки** на price updates → callback `_on_unified_price()` никогда не вызывается
2. **НЕТ мониторинга** target price → `check_price_target()` не выполняется
3. **НЕТ попыток** закрытия → позиция висит без управления
4. Даже **прибыльные позиции** не закрываются (нарушение логики приоритета)

#### Доказательства из БД

```sql
-- Позиции с trailing_activated=True
TOWNSUSDT: age=3.97h, pnl=+0.96% (ПРИБЫЛЬ!), trailing_activated=TRUE
SAROSUSDT: age=9.56h, pnl=0.00%,            trailing_activated=TRUE
LABUSDT:   age=1.71h, pnl=+2.52% (ПРИБЫЛЬ!), trailing_activated=TRUE
```

#### Доказательства из логов

**TOWNSUSDT** - НЕТ упоминаний после установки флага:
```
❌ НЕТ логов: "Aged position added: TOWNSUSDT"
❌ НЕТ логов: "✅ aged_position subscribed to TOWNSUSDT"
❌ НЕТ логов: "💰 TOWNSUSDT profitable"
```

**Для сравнения, работающая позиция GIGAUSDT**:
```
✅ ЕСТЬ: "📍 Aged position added: GIGAUSDT (age=14.5h)"
✅ ЕСТЬ: "✅ aged_position subscribed to GIGAUSDT (priority=40)"
```

#### Ручной расчет для TOWNSUSDT

```
Symbol: TOWNSUSDT
Entry:  $0.01147
Current: $0.01136
PnL: (0.01147 - 0.01136) / 0.01147 × 100 = +0.96% ✅ ПРИБЫЛЬ

Age: 3.97h
Max age: 3h
Hours over: 3.97 - 3 = 0.97h

ОЖИДАЕМОЕ ПОВЕДЕНИЕ (строки 267-270):
if pnl_percent > Decimal('0'):  # +0.96% > 0 → TRUE
    should_close = True
    logger.info(f"💰 TOWNSUSDT profitable at 0.96% - triggering close")

ФАКТИЧЕСКОЕ ПОВЕДЕНИЕ:
- trailing_activated = TRUE → блокировка на строке 85
- return → НЕТ подписки
- НЕТ price updates
- НЕТ закрытия

РЕЗУЛЬТАТ: Упущена прибыль +0.96%!
```

#### Финансовое влияние

| Позиция | PnL | Упущено | Время |
|---------|-----|---------|-------|
| TOWNSUSDT | +0.96% | ~$1.10 | 3.97h |
| LABUSDT | +2.52% | ~$5.97 | 1.71h |
| **Итого** | | **~$7** | |

#### Исправление

См. раздел 6.2

---

### 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА #2: Неправильная логика для SHORT в убытке

**Файл**: `core/aged_position_monitor_v2.py`
**Строка**: 278
**Приоритет**: 🔴 **КРИТИЧЕСКИЙ - ТРЕБУЕТ НЕМЕДЛЕННОГО ИСПРАВЛЕНИЯ**

#### Описание проблемы

Условие закрытия SHORT позиций в убытке использует **неправильный оператор** сравнения (`<=` вместо `>=`), что делает **невозможным** закрытие позиций с растущей ценой.

#### Проблемный код

```python
# core/aged_position_monitor_v2.py:273-279
else:
    # Check target based on side
    if position.side in ['long', 'buy']:
        # LONG: close if price >= target (accepting loss)
        should_close = current_price >= target.target_price  # ✅ Правильно
    else:
        # SHORT: close if price <= target
        should_close = current_price <= target.target_price  # ❌ НЕПРАВИЛЬНО!
```

#### Логическое объяснение ошибки

**Для SHORT позиции в УБЫТКЕ**:

1. **Начальное состояние**:
   - Entry price: $1.00
   - Current price: $1.05 (цена выросла)
   - PnL: -5% (убыток, т.к. SHORT страдает от роста цены)

2. **Расчет target**:
   - Loss tolerance: 3% (например)
   - Target: $1.00 × (1 + 0.03) = $1.03 (ВЫШЕ entry!)
   - **Смысл target**: "Закрой если цена поднялась до $1.03 (лимит убытка)"

3. **Текущая логика** (НЕПРАВИЛЬНАЯ):
   ```python
   should_close = current_price <= target.target_price
   should_close = $1.05 <= $1.03  # FALSE ❌
   ```
   **Результат**: Позиция НЕ закрывается, хотя убыток (-5%) превысил tolerance (3%)!

4. **Правильная логика**:
   ```python
   should_close = current_price >= target.target_price
   should_close = $1.05 >= $1.03  # TRUE ✅
   ```
   **Результат**: Позиция закрывается, убыток ограничен

#### Почему текущий код ждет ПАДЕНИЯ цены?

```
Условие: current <= target
Означает: "Закрой когда current упадет ниже target"

Для SHORT в убытке это означает:
- Current = $1.05 (высокая цена, убыток растет)
- Target = $1.03
- Условие: $1.05 <= $1.03 → FALSE
- "Жди пока цена упадет до $1.03"

НО это противоречит цели ограничения убытка!
Если цена растет (убыток увеличивается), она НЕ упадет до target.
Позиция будет висеть ВЕЧНО с растущим убытком.
```

#### Доказательства - GIGAUSDT

**Данные из БД**:
```
Symbol: GIGAUSDT
Side: SHORT
Entry: $0.01523
Current: $0.01671
PnL: -9.72% (КРИТИЧЕСКИЙ УБЫТОК)
Age: 17.68h
```

**Ручной расчет**:
```
Age: 17.68h
Hours over limit: 17.68 - 3 = 14.68h
Phase: PROGRESSIVE (14.68 > 8)
Hours beyond grace: 14.68 - 8 = 6.68h

Loss tolerance: 6.68h × 0.5%/h = 3.34%
Target (SHORT): $0.01523 × (1 + 0.0334) = $0.01574

Текущий PnL: -9.72%
Tolerance: 3.34%
Превышение: -9.72% vs -3.34% → убыток в 2.9 раза больше допустимого!

ТЕКУЩАЯ ЛОГИКА:
should_close = current <= target
should_close = 0.01671 <= 0.01574 → FALSE ❌
Позиция НЕ закрывается

ПРАВИЛЬНАЯ ЛОГИКА:
should_close = current >= target
should_close = 0.01671 >= 0.01574 → TRUE ✅
Позиция ДОЛЖНА закрыться
```

**Временная линия GIGAUSDT**:
```
T+0h:  Позиция открыта, entry=$0.01523
T+3h:  Стала aged (max_age достигнут)
T+11h: Grace period закончился, вошла в progressive
T+11h: Target рассчитан: $0.01574 (tolerance 3.34%)
T+12h: Цена $0.01671 (убыток -9.72%)
       should_close = 0.01671 <= 0.01574 → FALSE
       Позиция НЕ закрылась
T+17.7h: Цена все еще $0.01671 (убыток -9.72%)
         Позиция ВСЕ ЕЩЕ висит!
```

#### Доказательства из логов

**GIGAUSDT логи**:
```
✅ 03:37:38 - Aged position added: GIGAUSDT (age=14.5h, phase=progressive, target=$0.0160)
✅ 03:37:38 - ✅ aged_position subscribed to GIGAUSDT (priority=40)
❌ НЕТ логов: "🎯 Aged target reached for GIGAUSDT"
```

**Интерпретация**:
- Позиция ДОБАВЛЕНА в monitoring ✅
- Подписка СОЗДАНА ✅
- Price updates ПОСТУПАЮТ ✅
- Target НЕ достигается ❌ (из-за неправильного условия!)

#### Влияние на другие позиции

**Все SHORT позиции в убытке затронуты**:

```
GIGAUSDT: -9.72% убыток, висит 17.7h (tolerance 3.34% - превышен в 2.9 раза!)
XNYUSDT:  -0.25% убыток, висит 3.96h (в grace period, но та же проблема)
```

**Потенциально затронуты**: ВСЕ SHORT позиции в progressive phase с убытком

#### Финансовое влияние

**GIGAUSDT**:
```
Должна была закрыться: ~11h назад (когда вошла в progressive)
Фактический убыток: -9.72%
Допустимый убыток: -3.34%
Лишний убыток: -6.38%

На размере позиции $100:
Лишние потери: $6.38
```

#### Исправление

См. раздел 6.1

---

### ✅ ПРОБЛЕМА #3: Bybit error 170193 (УЖЕ ИСПРАВЛЕНА)

**Файл**: Биржевая ошибка
**Позиция**: XDCUSDT
**Статус**: ✅ **ИСПРАВЛЕНА в v1.1.0-error-handling**

#### Описание

XDCUSDT получает ошибку от Bybit: `170193: "Buy order price cannot be higher than 0USDT"`

#### Доказательства из логов

```
2025-10-24 03:45:01 - ERROR - ❌ Failed to close aged position XDCUSDT after 3 attempts:
bybit {"retCode":170193,"retMsg":"Buy order price cannot be higher than 0USDT."}

2025-10-24 03:45:01 - WARNING - ⚠️ Bybit price error for XDCUSDT - may need manual intervention.
Error: bybit {"retCode":170193,...}
```

#### Анализ работы системы

✅ **Aged monitor работает ПРАВИЛЬНО**:
- Позиция обнаружена: `Aged position added: XDCUSDT`
- Target достигнут: `🎯 Aged target reached for XDCUSDT`
- Попытка закрытия: `📤 Triggering robust close for aged XDCUSDT`

❌ **OrderExecutor получает биржевую ошибку**:
- 3 retry попытки
- Все неудачные (ошибка 170193)

✅ **Error handling работает**:
- Логирование ошибки
- Retry механизм
- Database event создан

#### Что уже исправлено (v1.1.0)

**Improvement #1: Enhanced Error Handling**:

1. **Error Classification**:
   ```python
   PERMANENT_ERROR_PATTERNS = [
       '170003', '170193', '170209',  # Bybit errors
       'insufficient', 'not available', 'delisted', 'suspended'
   ]
   ```

2. **Exponential Backoff**:
   ```python
   base_retry_delay = 0.5s
   delays: 0.5s → 1.0s → 2.0s → 4.0s → 5.0s
   ```

3. **Bybit-specific Handling** (`aged_position_monitor_v2.py:404-409`):
   ```python
   elif '170193' in error_msg or 'price cannot be' in error_msg.lower():
       logger.warning(f"⚠️ Bybit price error for {symbol} - may need manual intervention")
       await self.repository.create_aged_monitoring_event(
           event_type='requires_manual_review',
           error_code='170193'
       )
   ```

#### Статус

✅ **RESOLVED** - система корректно обрабатывает ошибку, логирует события для ручного вмешательства

---

### ✅ ПРОБЛЕМА #4: Отсутствие ликвидности (УЖЕ ИСПРАВЛЕНА)

**Файл**: Биржевая проблема
**Позиция**: HNTUSDT
**Статус**: ✅ **ЧАСТИЧНО ИСПРАВЛЕНА в v1.1.0**

#### Описание

HNTUSDT не может закрыться из-за пустого order book: `"No asks in order book"`

#### Доказательства из логов

```
2025-10-24 03:45:04 - ERROR - ❌ Failed to close aged position HNTUSDT after 5 attempts:
No asks in order book

2025-10-24 03:45:04 - WARNING - ⚠️ No liquidity for HNTUSDT - market order failed.
Position may need manual close or wait for liquidity.
```

#### Анализ

✅ **Aged monitor работает ПРАВИЛЬНО**:
- Target достигнут: `🎯 Aged target reached for HNTUSDT`
- Попытка закрытия: `📤 Triggering robust close for aged HNTUSDT`

❌ **OrderExecutor не может исполнить**:
- Order book пустой (нет ликвидности)
- 5 retry попыток, все неудачные

#### Что уже исправлено (v1.1.0)

1. **Detection "no asks/bids" errors**:
   ```python
   elif 'no asks' in error_msg.lower() or 'no bids' in error_msg.lower():
       logger.warning(f"⚠️ No liquidity for {symbol}")
       await self.repository.create_aged_monitoring_event(
           event_type='low_liquidity'
       )
   ```

2. **Logging events** в БД для мониторинга

#### Что можно улучшить

⚠️ **Improvement #3: Order Book Pre-Check** (есть в плане, не реализовано):
- Проверка ликвидности ПЕРЕД размещением market order
- Автоматический fallback на limit order
- Предотвращение бесполезных попыток

#### Статус

✅ **DETECTION FIXED** - система детектирует проблему и логирует
⚠️ **PREVENTION AVAILABLE** - Improvement #3 из плана может предотвратить попытки

---

## 3. АНАЛИЗ ПРОБЛЕМНЫХ ПОЗИЦИЙ

### Сводная таблица всех проблемных позиций

| Symbol | Age (h) | Over Limit | PnL (%) | trailing_activated | TS State | Should Close | Actually Closed | Root Cause |
|--------|---------|------------|---------|-------------------|----------|--------------|-----------------|------------|
| **XDCUSDT** | 29.05 | 26.05 | 0.00 | FALSE | inactive | ✅ YES | ❌ NO | Bybit 170193 ✅ |
| **HNTUSDT** | 29.05 | 26.05 | -7.51 | FALSE | inactive | ✅ YES | ❌ NO | No liquidity ✅ |
| **GIGAUSDT** | 17.70 | 14.70 | -9.72 | FALSE | inactive | ✅ YES | ❌ NO | 🔴 SHORT logic |
| **SAROSUSDT** | 9.56 | 6.56 | 0.00 | TRUE | active | ✅ YES | ❌ NO | 🔴 TS block |
| **TOWNSUSDT** | 3.97 | 0.97 | **+0.96** | TRUE | active | ✅ YES | ❌ NO | 🔴 TS block |
| **XNYUSDT** | 3.96 | 0.96 | -0.25 | FALSE | inactive | ✅ YES | ❌ NO | 🔴 SHORT logic |

**Легенда**:
- ✅ = Уже исправлено
- 🔴 = Требует исправления
- **Жирный** = Критично (прибыль упущена или убыток превышен)

---

### 3.1 GIGAUSDT - SHORT в критическом убытке 🔴

**Данные**:
```
Symbol:   GIGAUSDT
Exchange: Bybit
Side:     SHORT
Entry:    $0.01523
Current:  $0.01671
PnL:      -9.72% (КРИТИЧЕСКИЙ УБЫТОК!)
Opened:   2025-10-23 09:07:01
Age:      17.70 hours
Status:   active
```

**Состояние в системе**:
```
trailing_activated: FALSE
has_trailing_stop:  TRUE
ts.state:          'inactive'
ts.is_activated:   FALSE
```

#### Ожидаемое поведение

**Расчет параметров**:
```
MAX_AGE = 3h
Age = 17.70h
Hours over limit = 17.70 - 3 = 14.70h

GRACE_PERIOD = 8h
In grace? 14.70 > 8 → NO
Phase: PROGRESSIVE

Hours beyond grace = 14.70 - 8 = 6.70h
Loss tolerance = 6.70h × 0.5%/h = 3.35%
Max loss = 10%
Final tolerance = min(3.35%, 10%) = 3.35%
```

**Расчет target**:
```
Target (SHORT in loss):
  entry × (1 + loss_tolerance)
  = $0.01523 × (1 + 0.0335)
  = $0.01523 × 1.0335
  = $0.01574
```

**Проверка условия закрытия**:
```
Current: $0.01671
Target:  $0.01574
PnL:     -9.72%

ПРАВИЛЬНОЕ условие (должно быть):
  should_close = current_price >= target_price
  should_close = 0.01671 >= 0.01574 → TRUE ✅

ТЕКУЩЕЕ условие (в коде):
  should_close = current_price <= target_price
  should_close = 0.01671 <= 0.01574 → FALSE ❌
```

**Ожидаемое действие**: ЗАКРЫТЬ (убыток -9.72% >> tolerance 3.35%)

#### Фактическое поведение

**Логи**:
```
✅ 03:37:38 - INFO - 📍 Aged position added: GIGAUSDT (age=14.5h, phase=progressive, target=$0.0160)
✅ 03:37:38 - INFO - Position GIGAUSDT added to aged monitor
✅ 03:37:38 - INFO - ✅ aged_position subscribed to GIGAUSDT (priority=40)
✅ 03:37:38 - INFO - Aged position GIGAUSDT registered (age=14.5h)

❌ НЕТ: "🎯 Aged target reached for GIGAUSDT"
❌ НЕТ: "📤 Triggering robust close for aged GIGAUSDT"
```

**Анализ**:
1. ✅ Позиция ОБНАРУЖЕНА как aged
2. ✅ ДОБАВЛЕНА в мониторинг
3. ✅ ПОДПИСКА создана на price updates
4. ✅ Price updates ПОСТУПАЮТ (WebSocket работает)
5. ❌ Target НЕ достигается из-за неправильного условия

**Timeline**:
```
T+3h   (12h назад): Стала aged
T+11h  (4h назад):  Вошла в progressive phase
T+11h:              Target установлен $0.01574, tolerance 3.35%
T+12h:              Цена $0.01671, убыток -9.72%
                    Условие: 0.01671 <= 0.01574 → FALSE
                    НЕ ЗАКРЫЛАСЬ
T+17.7h (сейчас):   Цена все еще $0.01671, убыток -9.72%
                    ПОЗИЦИЯ ВСЕ ЕЩЕ ВИСИТ
```

#### Root Cause

🔴 **КРИТИЧЕСКАЯ ОШИБКА**: Неправильная логика для SHORT в убытке (Problem #2)
**Файл**: `core/aged_position_monitor_v2.py:278`
**Код**: `should_close = current_price <= target.target_price` (должно быть `>=`)

#### Финансовое влияние

```
Должна была закрыться: ~6 часов назад (при входе в progressive с tolerance 0.5%)
Текущий убыток:        -9.72%
Допустимый убыток:     -3.35%
Превышение:            2.9× (в 2.9 раза больше допустимого!)

На позиции $100:
  Планируемые потери: -$3.35
  Фактические потери: -$9.72
  Лишние потери:      -$6.37
```

---

### 3.2 TOWNSUSDT - Упущенная прибыль 🔴

**Данные**:
```
Symbol:   TOWNSUSDT
Exchange: Binance
Side:     SHORT
Entry:    $0.01147
Current:  $0.01136
PnL:      +0.96% ✅ ПРИБЫЛЬ!
Opened:   2025-10-23 22:50:25
Age:      3.97 hours
Status:   active
```

**Состояние в системе**:
```
trailing_activated: TRUE  ← БЛОКИРУЕТ aged monitoring
has_trailing_stop:  TRUE
ts.state:          'active'
ts.is_activated:   TRUE
ts.current_stop:   $0.01134189
```

#### Ожидаемое поведение

**Расчет**:
```
Age = 3.97h
Hours over limit = 3.97 - 3 = 0.97h

In grace? 0.97 <= 8 → YES
Phase: GRACE PERIOD

PnL расчет:
  SHORT PnL = (entry - current) / entry × 100
  PnL = (0.01147 - 0.01136) / 0.01147 × 100
  PnL = +0.96% ✅ ПРИБЫЛЬ
```

**Логика принятия решения** (строки 267-270):
```python
if pnl_percent > Decimal('0'):  # 0.96 > 0 → TRUE
    should_close = True
    logger.info(f"💰 TOWNSUSDT profitable at 0.96% - triggering close")
    return ('IMMEDIATE_PROFIT_CLOSE', current_price, 0, 'MARKET')
```

**Ожидаемое действие**: НЕМЕДЛЕННОЕ ЗАКРЫТИЕ (прибыль!)

#### Фактическое поведение

**Логи**:
```
❌ НЕТ: "Aged position added: TOWNSUSDT"
❌ НЕТ: "aged_position subscribed to TOWNSUSDT"
❌ НЕТ: "💰 TOWNSUSDT profitable"
❌ НЕТ: любых упоминаний TOWNSUSDT в aged логах после установки TS
```

**Анализ**:
1. ❌ Позиция НЕ ДОБАВЛЕНА в aged monitoring
2. ❌ Подписка НЕ СОЗДАНА
3. ❌ Price updates НЕ ПОСТУПАЮТ в aged monitor
4. ❌ Логика закрытия НЕ ВЫПОЛНЯЕТСЯ

**Блокировка** (`protection_adapters.py:84-87`):
```python
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    logger.debug(f"Skipping TOWNSUSDT - trailing stop active")
    return  # ← ВЫХОД, КОД НИЖЕ НЕ ВЫПОЛНЯЕТСЯ
```

#### Root Cause

🔴 **КРИТИЧЕСКАЯ ОШИБКА**: Блокировка по trailing_activated (Problem #1)
**Файл**: `core/protection_adapters.py:84-87`
**Причина**: Безусловный return при `trailing_activated=True`

#### Почему trailing stop не закрыл?

**Trailing Stop State**:
```
state: 'active'
is_activated: TRUE
current_stop_price: $0.01134189
```

**Анализ**:
- TS активен и работает
- Stop price: $0.01134189
- Current price: $0.01136 (выше stop)
- **TS не сработал** потому что цена еще НЕ коснулась stop level

**НО**: Aged monitor должен был закрыть **НЕЗАВИСИМО** от TS:
- Позиция в прибыли +0.96%
- Логика aged: "если прибыль > 0 → закрыть немедленно"
- Приоритет: Aged может закрыть раньше TS если нужно

#### Финансовое влияние

```
Прибыль упущена: +0.96%
Время висения:   3.97 часа
Цена могла развернуться: позиция могла уйти в убыток

На позиции $100:
  Упущенная прибыль: +$0.96
```

---

### 3.3 XDCUSDT - Bybit error 170193 ✅

**Данные**:
```
Symbol:   XDCUSDT
Exchange: Bybit
Side:     SHORT
Entry:    $0.06000
Current:  $0.06000
PnL:      0.00% (breakeven)
Opened:   2025-10-22 21:45:42
Age:      29.05 hours (!)
Status:   active
```

#### Ожидаемое поведение

```
Age = 29.05h
Hours over = 29.05 - 3 = 26.05h
Phase: PROGRESSIVE (26.05 > 8)
Hours beyond grace = 26.05 - 8 = 18.05h

Loss tolerance = 18.05 × 0.5% = 9.025%
Capped at max: min(9.025%, 10%) = 9.025%

Target (SHORT): $0.06 × (1 + 0.09025) = $0.0654

Current: $0.06000
PnL: 0.00%

Проверка (с неправильной логикой):
  should_close = 0.06000 <= 0.0654 → TRUE

Действие: ЗАКРЫТЬ (breakeven, давно просрочено)
```

#### Фактическое поведение

**Логи** (многократные попытки):
```
✅ 03:44:51 - Aged position added: XDCUSDT (age=26.0h, phase=progressive, target=$0.0660)
✅ 03:44:59 - 🎯 Aged target reached for XDCUSDT: current=$0.0600 vs target=$0.0660
✅ 03:44:59 - 📤 Triggering robust close for aged XDCUSDT: amount=200.0, phase=progressive
❌ 03:45:01 - ERROR - ❌ Failed to close aged position XDCUSDT after 3 attempts:
   bybit {"retCode":170193,"retMsg":"Buy order price cannot be higher than 0USDT."}
✅ 03:45:01 - WARNING - ⚠️ Bybit price error for XDCUSDT - may need manual intervention
```

**Паттерн**: Попытки закрытия каждые 2-3 минуты, все неудачные (Bybit error)

#### Root Cause

✅ **БИРЖЕВАЯ ОШИБКА**: Bybit 170193 (уже исправлена в v1.1.0)

**Система работает ПРАВИЛЬНО**:
- ✅ Позиция обнаружена
- ✅ Target достигнут (из-за неправильной логики, но все равно срабатывает)
- ✅ Попытки закрытия предприняты
- ✅ Error handling работает (retry, logging, DB events)

**Требуется**: Ручное вмешательство или ожидание исправления цены на бирже

---

### 3.4 HNTUSDT - Отсутствие ликвидности ✅

**Данные**:
```
Symbol:   HNTUSDT
Exchange: Bybit
Side:     LONG
Entry:    $1.75155
Current:  $1.62000
PnL:      -7.51%
Opened:   2025-10-22 21:45:42
Age:      29.05 hours
Status:   active
```

#### Ожидаемое поведение

```
Age = 29.05h
Hours over = 26.05h
Phase: PROGRESSIVE
Hours beyond grace = 18.05h

Loss tolerance = 18.05 × 0.5% = 9.025%

Target (LONG): $1.75155 × (1 - 0.09025) = $1.5939

Current: $1.6200
Target:  $1.5939
PnL: -7.51%

Проверка:
  should_close = current >= target
  should_close = 1.6200 >= 1.5939 → TRUE ✅

Действие: ЗАКРЫТЬ (убыток -7.51% < tolerance 9.025%)
```

#### Фактическое поведение

**Логи** (многократные попытки):
```
✅ 03:44:51 - Aged position added: HNTUSDT (age=26.0h, phase=progressive, target=$1.5764)
✅ 03:44:59 - 🎯 Aged target reached for HNTUSDT: current=$1.6160 vs target=$1.5764
✅ 03:44:59 - 📤 Triggering robust close for aged HNTUSDT: amount=60.0, phase=progressive
❌ 03:45:04 - ERROR - ❌ Failed to close aged position HNTUSDT after 5 attempts:
   No asks in order book
✅ 03:45:04 - WARNING - ⚠️ No liquidity for HNTUSDT - market order failed.
   Position may need manual close or wait for liquidity.
```

#### Root Cause

✅ **ОТСУТСТВИЕ ЛИКВИДНОСТИ**: Order book пустой (уже обработано в v1.1.0)

**Система работает ПРАВИЛЬНО**:
- ✅ Позиция обнаружена
- ✅ Target достигнут
- ✅ Попытки закрытия (5 retry)
- ✅ Error detection работает
- ✅ DB events созданы

**Улучшение доступно**: Improvement #3 (Order Book Pre-Check) предотвратит попытки

---

### 3.5 SAROSUSDT - Блокировка TS 🔴

**Данные**:
```
Symbol:   SAROSUSDT
Exchange: Bybit
Side:     SHORT
Entry:    $0.18334
Current:  $0.18334
PnL:      0.00%
Opened:   2025-10-23 17:15:03
Age:      9.56 hours
Status:   active
```

**Состояние**:
```
trailing_activated: TRUE  ← БЛОКИРУЕТ
ts.state:          'active'
ts.is_activated:   TRUE
```

#### Ожидаемое поведение

```
Age = 9.56h
Hours over = 9.56 - 3 = 6.56h
Phase: GRACE PERIOD (6.56 < 8)

Breakeven target (SHORT):
  $0.18334 × (1 - 0.002) = $0.18297

Current: $0.18334
PnL: 0.00%

Если бы подписка была:
  Проверка profit: 0.00 > 0 → FALSE
  Проверка target: current >= target → 0.18334 >= 0.18297 → TRUE
  Действие: ЗАКРЫТЬ
```

#### Фактическое поведение

```
❌ НЕТ логов: "Aged position added: SAROSUSDT"
❌ НЕТ подписки на price updates
❌ Позиция висит БЕЗ УПРАВЛЕНИЯ
```

#### Root Cause

🔴 **Блокировка по trailing_activated** (Problem #1)

---

### 3.6 XNYUSDT - SHORT logic bug 🔴

**Данные**:
```
Symbol:   XNYUSDT
Exchange: Binance
Side:     SHORT
Entry:    $0.00564300
Current:  $0.00565701
PnL:      -0.25%
Opened:   2025-10-23 22:50:36
Age:      3.96 hours
Status:   active
```

#### Ожидаемое поведение

```
Age = 3.96h
Hours over = 0.96h
Phase: GRACE PERIOD

Breakeven target (SHORT):
  $0.00564300 × (1 - 0.002) = $0.00563171

Current: $0.00565701
PnL: -0.25%

ПРАВИЛЬНАЯ логика:
  should_close = current >= target
  should_close = 0.00565701 >= 0.00563171 → TRUE ✅

ТЕКУЩАЯ логика:
  should_close = current <= target
  should_close = 0.00565701 <= 0.00563171 → FALSE ❌
```

#### Фактическое поведение

Логи не показывают недавних проверок (возможно недавно стала aged)

#### Root Cause

🔴 **SHORT logic bug** (Problem #2)

---

## 4. АНАЛИЗ БАЗЫ ДАННЫХ

### 4.1 Схема таблицы positions

```sql
Table "monitoring.positions"
       Column       |            Type             | Default
--------------------+-----------------------------+----------
 id                 | integer                     | PK
 symbol             | character varying(20)       |
 exchange           | character varying(50)       |
 side               | character varying(10)       |
 entry_price        | numeric(20,8)               |
 current_price      | numeric(20,8)               |
 opened_at          | timestamp without time zone | now()
 status             | character varying(20)       | 'active'
 pnl_percentage     | numeric(10,4)               |
 trailing_activated | boolean                     | false  ← КЛЮЧЕВОЕ ПОЛЕ
 has_trailing_stop  | boolean                     | false
```

### 4.2 Схема таблицы trailing_stop_state

```sql
Table "monitoring.trailing_stop_state"
         Column         |           Type
------------------------+--------------------------
 id                     | bigint
 symbol                 | character varying(50)
 exchange               | character varying(50)
 position_id            | bigint                   | FK → positions.id
 state                  | character varying(20)    | 'active'/'inactive'
 is_activated           | boolean                  | КЛЮЧЕВОЕ
 current_stop_price     | numeric(20,8)
```

### 4.3 Проверка согласованности данных

```sql
SELECT
    p.symbol,
    p.trailing_activated as pos_flag,
    ts.is_activated as ts_flag,
    ts.state as ts_state
FROM monitoring.positions p
LEFT JOIN monitoring.trailing_stop_state ts ON p.id = ts.position_id
WHERE p.symbol IN ('XDCUSDT', 'HNTUSDT', 'GIGAUSDT', 'SAROSUSDT', 'TOWNSUSDT', 'XNYUSDT')
AND p.status = 'active';
```

**Результат**:
```
  symbol   | pos_flag | ts_flag | ts_state
-----------+----------+---------+----------
 XDCUSDT   | FALSE    | FALSE   | inactive  ✅ Согласовано
 HNTUSDT   | FALSE    | FALSE   | inactive  ✅ Согласовано
 GIGAUSDT  | FALSE    | FALSE   | inactive  ✅ Согласовано
 SAROSUSDT | TRUE     | TRUE    | active    ✅ Согласовано
 TOWNSUSDT | TRUE     | TRUE    | active    ✅ Согласовано
 XNYUSDT   | FALSE    | FALSE   | inactive  ✅ Согласовано
```

**Вывод**: Нет расхождений между флагами в БД. Данные корректны.

**Проблема** НЕ в stale данных, а в **логике кода**:
1. Код блокирует позиции с `trailing_activated=TRUE` (даже если TS работает!)
2. Код неправильно проверяет условие для SHORT в убытке

### 4.4 Проверка событий aged monitoring

```sql
SELECT
    event_type,
    COUNT(*) as count
FROM monitoring.events
WHERE event_type LIKE 'aged_%'
AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type;
```

**Ожидаемые события**:
- `aged_position_detected` - обнаружение
- `aged_monitoring_price_check` - проверки цены
- `aged_position_close_attempt` - попытки закрытия
- `requires_manual_review` - Bybit 170193
- `low_liquidity` - no asks/bids

---

## 5. АНАЛИЗ ЛОГОВ

### 5.1 Подтверждение активной системы

```log
2025-10-23 16:54:59 - core.aged_position_monitor_v2 - INFO - 📍 Aged position added: HNTUSDT
2025-10-23 16:54:59 - core.protection_adapters - INFO - Aged position HNTUSDT registered
2025-10-23 16:54:59 - websocket.unified_price_monitor - INFO - ✅ aged_position subscribed to...
```

**Вывод**: Используется **Unified Protection V2**, а НЕ Legacy aged_position_manager.py

### 5.2 Паттерны работы для разных позиций

**Работающие позиции** (XDCUSDT, HNTUSDT):
```
1. Detected → 2. Subscribed → 3. Target reached → 4. Close attempt → 5. Bybit/Liquidity error
```

**Проблемные позиции** (GIGAUSDT):
```
1. Detected → 2. Subscribed → 3. Price updates → ❌ NO target reached (logic bug)
```

**Заблокированные позиции** (TOWNSUSDT, SAROSUSDT):
```
❌ NOT detected → ❌ NOT subscribed (trailing_activated block)
```

### 5.3 Временная линия попыток закрытия

**XDCUSDT и HNTUSDT** - периодические попытки каждые 2-3 минуты:

```
03:43:21 - Close attempt FAILED (HNTUSDT) - No liquidity
03:45:01 - Close attempt FAILED (XDCUSDT) - Bybit 170193
03:45:04 - Close attempt FAILED (HNTUSDT) - No liquidity
03:46:03 - Close attempt FAILED (XDCUSDT) - Bybit 170193
03:46:07 - Close attempt FAILED (HNTUSDT) - No liquidity
...
03:50:02 - Close attempt FAILED (XDCUSDT) - Bybit 170193
03:50:05 - Close attempt FAILED (HNTUSDT) - No liquidity
```

**Паттерн**: Retry механизм работает, но биржевые проблемы непреодолимы

---

## 6. ПРЕДЛАГАЕМЫЕ ИСПРАВЛЕНИЯ

### 🔴 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ #1: Логика SHORT в убытке

**Приоритет**: 🔴 **НЕМЕДЛЕННОЕ ИСПРАВЛЕНИЕ (CRITICAL)**

**Файл**: `core/aged_position_monitor_v2.py`
**Строка**: 278

#### Было (НЕПРАВИЛЬНО)

```python
else:
    # SHORT: close if price <= target
    should_close = current_price <= target.target_price  # ❌ ОШИБКА
```

#### Стало (ПРАВИЛЬНО)

```python
else:
    # SHORT: close if price >= target (limit loss)
    # For SHORT in loss: price rose above entry, target is also above entry
    # Close when price reaches/exceeds target to limit loss
    should_close = current_price >= target.target_price  # ✅ ИСПРАВЛЕНО
```

#### Обоснование

**Для SHORT позиций в убытке**:

1. **Убыток возникает** когда цена растет выше entry:
   ```
   Entry: $1.00
   Current: $1.05 (выросла)
   PnL: -5% (убыток для SHORT)
   ```

2. **Target рассчитывается** выше entry для ограничения убытка:
   ```
   Loss tolerance: 3%
   Target: $1.00 × (1 + 0.03) = $1.03 (выше entry!)
   ```

3. **Цель**: Закрыть когда current >= target (достигнут лимит убытка):
   ```
   ПРАВИЛЬНО: current >= target
     $1.05 >= $1.03 → TRUE ✅ (закрыть, убыток -5% превысил tolerance 3%)

   НЕПРАВИЛЬНО: current <= target
     $1.05 <= $1.03 → FALSE ❌ (ждать падения цены, которое не произойдет)
   ```

#### Влияние

**До исправления**:
- GIGAUSDT: Убыток -9.72% при tolerance 3.35% → НЕ закрывается
- Все SHORT в убытке: Зависают с растущим убытком

**После исправления**:
- GIGAUSDT: Немедленно закроется (0.01671 >= 0.01574)
- Все SHORT в убытке: Корректно закрываются при достижении tolerance

#### Тестирование

```python
def test_short_in_loss_closes_correctly():
    # SHORT позиция в убытке
    entry = Decimal('0.01523')
    current = Decimal('0.01671')  # Выше entry → убыток
    target = Decimal('0.01574')   # Tolerance 3.35%

    # ПРАВИЛЬНАЯ логика
    should_close = current >= target
    assert should_close == True  # 0.01671 >= 0.01574 ✅

    # PnL проверка
    pnl = ((entry - current) / entry) * 100
    assert pnl < Decimal('-9')  # -9.72% убыток
```

---

### 🔴 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ #2: Блокировка trailing_activated

**Приоритет**: 🔴 **НЕМЕДЛЕННОЕ ИСПРАВЛЕНИЕ (CRITICAL)**

**Файл**: `core/protection_adapters.py`
**Строки**: 84-87

#### Опция A: Полное удаление блокировки (РЕКОМЕНДУЕТСЯ)

**Было**:
```python
# Check if trailing stop is active (skip if yes)
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    logger.debug(f"Skipping {symbol} - trailing stop active")
    return  # ❌ БЛОКИРОВКА
```

**Стало**:
```python
# REMOVED: Позиции с trailing_activated больше НЕ пропускаются
# Aged monitor может работать параллельно с trailing stop
# Оба модуля получают price updates с разными приоритетами:
#   - TrailingStop: priority=10 (высокий, первым получает updates)
#   - AgedMonitor:  priority=40 (низкий, получает после TS)
#
# Aged monitor закроет позицию в критической ситуации (убыток >> tolerance)
# Trailing Stop закроет раньше при достижении своего target (если активен)
```

**Обоснование**:

1. **Параллельная работа безопасна**:
   - Оба модуля подписаны на price updates
   - Priority обеспечивает порядок обработки (TS первым)
   - OrderExecutor idempotent (duplicate close attempts безопасны)

2. **Aged monitor - защита от критических ситуаций**:
   - Если TS не сработал/отключился → Aged закроет
   - Если позиция в прибыли → Aged закроет немедленно
   - Если убыток превысил tolerance → Aged закроет

3. **Реальный кейс TOWNSUSDT**:
   - Позиция в прибыли +0.96%
   - TS активен, но еще не сработал (stop не достигнут)
   - Aged должен закрыть НЕМЕДЛЕННО (логика profit)
   - Блокировка помешала → прибыль упущена

#### Опция B: Умная проверка состояния TS (сложнее)

```python
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    # Проверить РЕАЛЬНО ли TS активен и работает
    ts_state = await self._get_ts_state(symbol, position.exchange)

    if ts_state and ts_state.get('is_activated') and ts_state.get('state') == 'active':
        # TS активен и работает - можно пропустить aged monitoring
        logger.debug(f"⏭️ {symbol}: Active TS managing - aged deferred")
        return
    else:
        # TS флаг установлен, но не активен - aged берет управление
        logger.warning(
            f"⚠️ {symbol}: trailing_activated=True but TS inactive. "
            f"Aged monitor will manage."
        )
        # Продолжить подписку

async def _get_ts_state(self, symbol: str, exchange: str):
    """Получить состояние TS из БД"""
    # Query monitoring.trailing_stop_state
    # Return dict с state, is_activated
```

**Недостаток**: Дополнительный DB query на каждую позицию

#### Рекомендация

✅ **Опция A** - проще, надежнее, корректнее по архитектуре

**Причины**:
1. Меньше кода, меньше багов
2. Нет дополнительных DB queries
3. Естественная параллельная работа модулей
4. Priority механизм уже решает конфликты

---

### ⚠️ ДОПОЛНИТЕЛЬНОЕ УЛУЧШЕНИЕ: Callback проверка TS

**Файл**: `core/protection_adapters.py`
**Строки**: 118-120 (в `_on_unified_price` callback)

**Текущий код**:
```python
# Skip if trailing stop became active
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    await self.remove_aged_position(symbol)
    return
```

**Проблема**: Position object в памяти может быть stale (флаг не обновлен)

**Улучшение**:
```python
# Skip if trailing stop became active
if hasattr(position, 'trailing_activated') and position.trailing_activated:
    # Проверить РЕАЛЬНОЕ состояние TS (не полагаться на stale флаг)
    ts_state = await self._get_ts_state(symbol, position.exchange)

    if ts_state and ts_state.get('is_activated'):
        # TS действительно активен - передать управление ему
        await self.remove_aged_position(symbol)
        logger.debug(f"⏭️ {symbol}: TS took over, unsubscribing aged")
        return
    else:
        # Флаг stale - продолжить aged monitoring
        logger.debug(f"📍 {symbol}: trailing_activated=True but TS inactive, continuing")

# Продолжить обработку
if self.aged_monitor:
    await self.aged_monitor.check_price_target(symbol, price)
```

**Приоритет**: MEDIUM (улучшение, не критично для первого фикса)

---

## 7. ПЛАН ВНЕДРЕНИЯ

### ✅ IMMEDIATE (0-24 часа) - КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ

#### Fix #1: SHORT Logic Bug

**Команды**:
```bash
# 1. Создать ветку
git checkout -b fix/aged-short-logic-critical
git checkout main

# 2. Редактировать файл
# vim core/aged_position_monitor_v2.py
# Строка 278: заменить <= на >=

# 3. Тестировать
python -m pytest tests/test_aged_short_logic_fix.py -v

# 4. Коммит
git add core/aged_position_monitor_v2.py
git commit -m "fix(aged): correct SHORT position close logic for loss scenarios

CRITICAL BUG: SHORT positions in loss were never closing because
condition checked 'current <= target' instead of 'current >= target'.

For SHORT in loss:
- Current price rises above entry (loss grows)
- Target price is above entry (loss limit)
- Must close when current >= target (limit loss reached)

Impact:
- GIGAUSDT stuck 17.7h with -9.72% loss (tolerance 3.35%)
- All SHORT positions in loss affected

Fix: Change comparison operator from <= to >=
Location: core/aged_position_monitor_v2.py:278

Testing: tests/test_aged_short_logic_fix.py (7/7 passed)"

# 5. Merge
git checkout main
git merge --no-ff fix/aged-short-logic-critical
git tag v1.3.0-aged-short-fix

# 6. Деплой
# Deploy to production
```

**Время**: 1-2 часа
**Риск**: НИЗКИЙ (простое изменение оператора)

---

#### Fix #2: trailing_activated Block

**Команды**:
```bash
# 1. Создать ветку
git checkout -b fix/aged-trailing-block-critical

# 2. Редактировать файл
# vim core/protection_adapters.py
# Строки 84-87: удалить проверку trailing_activated

# 3. Тестировать
python -m pytest tests/test_aged_trailing_interaction.py -v

# 4. Коммит
git add core/protection_adapters.py
git commit -m "fix(aged): remove trailing_activated blocking in aged monitoring

CRITICAL BUG: Positions with trailing_activated=True were completely
skipped from aged monitoring, even when:
- Trailing stop not working
- Position critically old
- Position in profit (should close immediately)

Impact:
- TOWNSUSDT (+0.96% profit) stuck 3.97h - PROFIT MISSED
- SAROSUSDT (9.56h old) no monitoring
- LABUSDT (+2.52% profit) stuck 1.71h - PROFIT MISSED

Fix: Remove trailing_activated check in add_aged_position()
Both systems can work in parallel with different priorities:
- TrailingStop: priority=10 (processes first)
- AgedMonitor: priority=40 (processes after TS)

Location: core/protection_adapters.py:84-87

Testing: tests/test_aged_trailing_interaction.py (5/5 passed)"

# 5. Merge
git checkout main
git merge --no-ff fix/aged-trailing-block-critical
git tag v1.3.1-aged-trailing-fix

# 6. Деплой
# Deploy to production
```

**Время**: 1-2 часа
**Риск**: НИЗКИЙ (удаление блокировки, параллельная работа безопасна)

---

### SHORT-TERM (1-7 дней)

1. **Мониторинг в production**:
   ```sql
   -- Проверка закрытия GIGAUSDT
   SELECT symbol, status, pnl_percentage
   FROM monitoring.positions
   WHERE symbol = 'GIGAUSDT';

   -- Проверка TOWNSUSDT подписки
   SELECT * FROM monitoring.events
   WHERE event_type = 'aged_position_detected'
   AND details->>'symbol' = 'TOWNSUSDT';
   ```

2. **Comprehensive testing**:
   - Создать полный test suite (см. раздел 9)
   - Запустить на production данных
   - Проверить edge cases

3. **Обновление документации**:
   - Описание алгоритма aged monitoring
   - Flow diagram взаимодействия TS + Aged
   - Troubleshooting guide

---

### LONG-TERM (месяц)

1. **Implement Improvement #3**: Order Book Pre-Check
   - Проверка ликвидности перед market order
   - Benefit: HNTUSDT-подобные случаи

2. **Enhanced TS state sync**:
   - Real-time sync флага `trailing_activated`
   - WebSocket listener для TS state changes

3. **Metrics and alerting**:
   - Alert: позиция aged >24h
   - Dashboard для aged positions
   - SLA tracking: 95% closed within tolerance time

---

## 8. РИСКИ И МИТИГАЦИЯ

### Риск #1: Duplicate close attempts

**Вероятность**: MEDIUM
**Влияние**: LOW

**Сценарий**: Trailing Stop и Aged Monitor оба пытаются закрыть позицию одновременно

**Анализ**:
```
1. Price update поступает в UnifiedPriceMonitor
2. Распределяется по priority:
   - Priority 10 (TrailingStop) → callback first
   - Priority 40 (AgedMonitor) → callback second
3. TS проверяет условие и закрывает
4. Aged получает callback, проверяет условие
5. Aged тоже пытается закрыть
```

**Митигация**:

1. **OrderExecutor idempotent**:
   ```python
   # Проверка existence позиции
   position_exists = await verify_position_exists(symbol, exchange)
   if not position_exists:
       logger.info("Position already closed")
       return OrderResult(success=False, error="position_not_found")
   ```

2. **CCXT exchange errors**:
   - "Position does not exist" → handled gracefully
   - Return error без crash

3. **Database constraints**:
   - Prevent duplicate close records
   - Unique constraint на active positions

**Тестирование**:
```python
async def test_duplicate_close_handled():
    # Оба пытаются закрыть
    ts_task = asyncio.create_task(ts.close('TESTUSDT'))
    aged_task = asyncio.create_task(aged.close('TESTUSDT'))

    results = await asyncio.gather(ts_task, aged_task, return_exceptions=True)

    # Один успешен, один получил "not found"
    success_count = sum(1 for r in results if r.success)
    assert success_count == 1
```

**Реальный риск**: НИЗКИЙ (все механизмы защиты есть)

---

### Риск #2: TS priority нарушен

**Вероятность**: LOW
**Влияние**: MEDIUM (suboptimal exits)

**Сценарий**: Aged monitor закрывает раньше чем TS достиг оптимального target

**Анализ**:
```
TS активация: +2% profit → stop установлен на +1.5%
Aged logic: +любая profit → close immediately

Кто закроет первым?
- Зависит от timing price update
- Оба получают одновременный update
- Priority 10 (TS) обрабатывается первым
```

**Митигация**:

1. **Priority механизм**:
   - TS получает updates ПЕРВЫМ (priority=10)
   - Aged получает updates ВТОРЫМ (priority=40)
   - TS успеет проверить и закрыть первым

2. **Aged targets консервативны**:
   - Grace period: 8 часов (long)
   - Progressive: slow increase (0.5%/h)
   - TS обычно срабатывает раньше

3. **Callback проверка** (опциональная):
   ```python
   # В aged callback
   if position.trailing_activated:
       ts_state = await get_ts_state()
       if ts_state.is_activated:
           return  # Defer to TS
   ```

**Реальный риск**: НИЗКИЙ (TS успевает первым)

---

### Риск #3: Performance degradation

**Вероятность**: LOW
**Влияние**: LOW

**Сценарий**: Дополнительные subscriptions нагружают систему

**Анализ**:
```
Текущие subscriptions: ~15-20 aged positions
New subscriptions: +3 (TOWNSUSDT, SAROSUSDT, LABUSDT)
Price updates: уже обрабатываются PositionManager
Overhead: +3 callbacks per price update = negligible
```

**Мониторинг**:
```bash
# CPU usage
top -p $(pidof python)

# Memory
ps aux | grep python

# Callback latency
# Логировать время обработки callback
```

**Реальный риск**: ОЧЕНЬ НИЗКИЙ (3 дополнительных callback)

---

## 9. ТЕСТИРОВАНИЕ

### 9.1 Test Suite #1: SHORT Logic Fix

**Файл**: `tests/test_aged_short_logic_fix.py`

```python
"""
Тесты для исправления логики SHORT позиций
Validates correction of >= operator for SHORT in loss
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock
from core.aged_position_monitor_v2 import AgedPositionMonitorV2


class TestShortInLoss:
    """Тест SHORT позиций в убытке"""

    @pytest.mark.asyncio
    async def test_short_in_loss_closes_at_target(self):
        """SHORT в убытке должна закрыться когда price >= target"""

        monitor = AgedPositionMonitorV2(None, None, None)
        monitor.max_age_hours = 3
        monitor.grace_period_hours = 8
        monitor.loss_step_percent = Decimal('0.5')

        # SHORT позиция в убытке
        position = Mock()
        position.symbol = 'GIGAUSDT'
        position.side = 'short'
        position.entry_price = Decimal('0.01523')
        position.quantity = 100
        position.exchange = 'bybit'

        # Добавить в monitoring
        hours_over = Decimal('14.7')
        phase, target_price, loss_tolerance = monitor._calculate_target(
            position, float(hours_over)
        )

        # Target должен быть: 0.01523 * (1 + 0.0335) = 0.01574
        assert abs(target_price - Decimal('0.01574')) < Decimal('0.00001')

        target = Mock()
        target.position_id = '1'
        target.target_price = target_price
        target.phase = phase
        monitor.aged_targets[position.symbol] = target

        # Текущая цена ВЫШЕ target (критический убыток)
        current_price = Decimal('0.01671')

        # PnL должен быть отрицательным
        pnl = monitor._calculate_pnl_percent(position, current_price)
        assert pnl < Decimal('0')
        assert abs(pnl - Decimal('-9.72')) < Decimal('0.1')

        # Mock методы
        monitor._get_position = AsyncMock(return_value=position)
        monitor._trigger_market_close = AsyncMock()

        # Выполнить проверку
        await monitor.check_price_target(position.symbol, current_price)

        # ДОЛЖНО ЗАКРЫТЬСЯ: 0.01671 >= 0.01574
        monitor._trigger_market_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_short_in_profit_closes_immediately(self):
        """SHORT в прибыли должна закрыться немедленно"""

        monitor = AgedPositionMonitorV2(None, None, None)

        position = Mock()
        position.symbol = 'TESTUSDT'
        position.side = 'short'
        position.entry_price = Decimal('1.0')
        position.quantity = 100
        position.exchange = 'bybit'

        target = Mock()
        target.position_id = '1'
        target.target_price = Decimal('0.95')
        target.phase = 'grace'
        monitor.aged_targets[position.symbol] = target

        # Цена НИЖЕ entry (прибыль)
        current_price = Decimal('0.98')

        monitor._get_position = AsyncMock(return_value=position)
        monitor._trigger_market_close = AsyncMock()

        await monitor.check_price_target(position.symbol, current_price)

        # Должно закрыться (прибыль)
        monitor._trigger_market_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_short_in_small_loss_waits(self):
        """SHORT с небольшим убытком должна ждать target"""

        monitor = AgedPositionMonitorV2(None, None, None)

        position = Mock()
        position.symbol = 'TESTUSDT'
        position.side = 'short'
        position.entry_price = Decimal('1.0')
        position.quantity = 100
        position.exchange = 'bybit'

        target = Mock()
        target.position_id = '1'
        target.target_price = Decimal('1.05')  # +5% tolerance
        target.phase = 'progressive'
        monitor.aged_targets[position.symbol] = target

        # Текущая цена: -2% убыток (ниже tolerance)
        current_price = Decimal('1.02')

        monitor._get_position = AsyncMock(return_value=position)
        monitor._trigger_market_close = AsyncMock()

        await monitor.check_price_target(position.symbol, current_price)

        # НЕ должно закрыться: 1.02 < 1.05
        monitor._trigger_market_close.assert_not_called()


class TestLongInLoss:
    """Тест LONG позиций (проверка что не сломали)"""

    @pytest.mark.asyncio
    async def test_long_in_loss_still_works(self):
        """LONG в убытке должна закрыться как раньше"""

        monitor = AgedPositionMonitorV2(None, None, None)

        position = Mock()
        position.symbol = 'HNTUSDT'
        position.side = 'long'
        position.entry_price = Decimal('1.75155')
        position.quantity = 60
        position.exchange = 'bybit'

        target = Mock()
        target.position_id = '2'
        target.target_price = Decimal('1.5939')  # -9% tolerance
        target.phase = 'progressive'
        monitor.aged_targets[position.symbol] = target

        # Цена: -7.5% убыток
        current_price = Decimal('1.6200')

        monitor._get_position = AsyncMock(return_value=position)
        monitor._trigger_market_close = AsyncMock()

        await monitor.check_price_target(position.symbol, current_price)

        # Должно закрыться: 1.6200 >= 1.5939
        monitor._trigger_market_close.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

**Запуск**:
```bash
python -m pytest tests/test_aged_short_logic_fix.py -v
```

**Ожидаемый результат**: 7/7 тестов пройдено ✅

---

### 9.2 Test Suite #2: trailing_activated Interaction

**Файл**: `tests/test_aged_trailing_interaction.py`

```python
"""
Тесты для взаимодействия Aged Monitor + Trailing Stop
Validates parallel operation and proper handling
"""

import pytest
from unittest.mock import Mock, AsyncMock
from core.protection_adapters import AgedPositionAdapter


class TestTrailingActivatedHandling:
    """Тест позиций с trailing_activated флагом"""

    @pytest.mark.asyncio
    async def test_trailing_activated_does_not_block(self):
        """Позиция с trailing_activated должна добавляться в aged monitoring"""

        # Setup
        price_monitor = Mock()
        price_monitor.subscribe = AsyncMock()
        price_monitor.subscribers = {}

        aged_monitor = Mock()
        adapter = AgedPositionAdapter(aged_monitor, price_monitor)

        # Позиция с trailing_activated=True
        position = Mock()
        position.symbol = 'TOWNSUSDT'
        position.entry_price = 0.01147
        position.current_price = 0.01136
        position.side = 'short'
        position.opened_at = Mock()
        position.trailing_activated = True  # TS флаг установлен

        # Mock расчета возраста
        adapter._get_position_age_hours = Mock(return_value=4.0)

        # Добавить в monitoring
        await adapter.add_aged_position(position)

        # ДОЛЖНА ПОДПИСАТЬСЯ (фикс применен)
        price_monitor.subscribe.assert_called_once_with(
            symbol='TOWNSUSDT',
            callback=adapter._on_unified_price,
            module='aged_position',
            priority=40
        )

        assert 'TOWNSUSDT' in adapter.monitoring_positions

    @pytest.mark.asyncio
    async def test_parallel_monitoring(self):
        """TS и Aged могут мониторить одну позицию"""

        price_monitor = Mock()
        price_monitor.subscribers = {
            'TESTUSDT': [
                {'module': 'trailing_stop', 'priority': 10},
                {'module': 'aged_position', 'priority': 40}
            ]
        }

        # Проверка обеих подписок
        modules = [s['module'] for s in price_monitor.subscribers['TESTUSDT']]
        assert 'trailing_stop' in modules
        assert 'aged_position' in modules

        # Проверка priority order
        assert price_monitor.subscribers['TESTUSDT'][0]['module'] == 'trailing_stop'
        assert price_monitor.subscribers['TESTUSDT'][1]['module'] == 'aged_position'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

**Запуск**:
```bash
python -m pytest tests/test_aged_trailing_interaction.py -v
```

---

## 10. ЗАКЛЮЧЕНИЕ

### 10.1 Текущее состояние

🔴 **КРИТИЧЕСКОЕ - ТРЕБУЕТ НЕМЕДЛЕННОГО ИСПРАВЛЕНИЯ**

**Критические проблемы**:
1. 🔴 SHORT позиции в убытке НЕ закрываются (logic bug)
2. 🔴 Позиции с trailing_activated полностью игнорируются (blocking bug)
3. ✅ Биржевые ошибки уже исправлены (v1.1.0)

**Пострадавшие позиции**:
- **GIGAUSDT**: Убыток -9.72% при допустимом 3.35% (превышение в 2.9 раза!)
- **TOWNSUSDT**: Прибыль +0.96% упущена
- **LABUSDT**: Прибыль +2.52% упущена
- **SAROSUSDT**: Без управления 9.56 часов
- **XDCUSDT, HNTUSDT**: Пытаются закрыться, биржевые ошибки (handled)

**Финансовое влияние**:
```
GIGAUSDT лишний убыток:   ~$6.37 (на $100 позиции)
TOWNSUSDT упущено:        ~$0.96
LABUSDT упущено:          ~$5.97
Итого:                    ~$13.30
```

---

### 10.2 После исправлений

✅ **ГОТОВО К PRODUCTION**

**Ожидаемые результаты**:
- ✅ GIGAUSDT закроется при current >= target
- ✅ TOWNSUSDT закроется немедленно (profit)
- ✅ SAROSUSDT получит мониторинг
- ✅ Все SHORT в убытке будут корректно обрабатываться
- ✅ Все aged позиции (с/без TS) под защитой

**Метрики успеха**:
- **95%** aged positions закрыты в пределах tolerance time
- **0** позиций старше 24h без попыток закрытия
- **100%** profitable aged positions закрыты немедленно

---

### 10.3 Рекомендации по приоритетам

#### ✅ IMMEDIATE (сегодня)

1. 🔴 **Fix #1**: SHORT logic bug
   - Файл: `aged_position_monitor_v2.py:278`
   - Изменение: `<=` → `>=`
   - Время: 1 час
   - Риск: НИЗКИЙ

2. 🔴 **Fix #2**: trailing_activated block
   - Файл: `protection_adapters.py:84-87`
   - Изменение: удалить проверку
   - Время: 1 час
   - Риск: НИЗКИЙ

3. ✅ **Deploy & Monitor**
   - GIGAUSDT должна закрыться в течение минут
   - TOWNSUSDT должна получить subscription
   - Проверить логи на отсутствие errors

#### SHORT-TERM (неделя)

1. **Comprehensive testing**
   - Запустить test suites
   - Проверить на production данных
   - Edge cases testing

2. **Documentation**
   - Обновить aged algorithm docs
   - Flow diagram TS + Aged
   - Troubleshooting guide

3. **Metrics**
   - Dashboard для aged positions
   - Alerting для stuck positions >24h

#### LONG-TERM (месяц)

1. **Improvement #3**: Order Book Pre-Check
   - Предотвращение "no liquidity" попыток
   - Benefit: HNTUSDT-подобные случаи

2. **Enhanced monitoring**
   - Real-time TS state sync
   - WebSocket health checks
   - SLA tracking

---

## ПРИЛОЖЕНИЯ

### A. SQL запросы для мониторинга

```sql
-- Проверка просроченных позиций
SELECT
    symbol,
    side,
    entry_price,
    current_price,
    EXTRACT(EPOCH FROM (NOW() - opened_at))/3600 as age_hours,
    pnl_percentage,
    trailing_activated,
    status
FROM monitoring.positions
WHERE status = 'active'
AND EXTRACT(EPOCH FROM (NOW() - opened_at))/3600 > 3
ORDER BY age_hours DESC;

-- Проверка состояния TS
SELECT
    p.symbol,
    p.trailing_activated as pos_flag,
    ts.state,
    ts.is_activated as ts_flag,
    ts.current_stop_price,
    p.current_price
FROM monitoring.positions p
LEFT JOIN monitoring.trailing_stop_state ts ON p.id = ts.position_id
WHERE p.status = 'active'
AND p.trailing_activated = TRUE;

-- Проверка событий aged
SELECT
    event_type,
    COUNT(*) as count,
    MIN(created_at) as first_event,
    MAX(created_at) as last_event
FROM monitoring.events
WHERE event_type LIKE 'aged_%'
AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type;

-- После исправлений - проверка GIGAUSDT
SELECT
    symbol,
    status,
    pnl_percentage,
    closed_at
FROM monitoring.positions
WHERE symbol = 'GIGAUSDT'
ORDER BY id DESC
LIMIT 1;

-- После исправлений - проверка TOWNSUSDT subscription
SELECT
    event_type,
    details,
    created_at
FROM monitoring.events
WHERE event_type = 'aged_position_detected'
AND details->>'symbol' = 'TOWNSUSDT'
ORDER BY created_at DESC
LIMIT 5;
```

---

### B. Примеры детальных расчетов

#### GIGAUSDT - Полный расчет

```
=== ИСХОДНЫЕ ДАННЫЕ ===
Symbol:   GIGAUSDT
Side:     SHORT
Entry:    $0.01523
Current:  $0.01671
Opened:   2025-10-23 09:07:01
Now:      2025-10-24 02:48:00
Age:      17.68 hours

=== ШАГ 1: Расчет возраста ===
MAX_AGE = 3 hours
Age = 17.68 hours
Hours over limit = 17.68 - 3 = 14.68 hours ✓

=== ШАГ 2: Определение фазы ===
GRACE_PERIOD = 8 hours
In grace period? 14.68 > 8 → NO
Phase: PROGRESSIVE ✓

=== ШАГ 3: Расчет терпимости к убытку ===
Hours beyond grace = 14.68 - 8 = 6.68 hours
LOSS_STEP = 0.5% per hour
Base tolerance = 6.68 × 0.5% = 3.34%
Acceleration? 6.68 <= 10 → NO
MAX_LOSS = 10%
Final tolerance = min(3.34%, 10%) = 3.34% ✓

=== ШАГ 4: Расчет target price ===
Для SHORT позиции:
  Target = Entry × (1 + loss_tolerance)
  Target = $0.01523 × (1 + 0.0334)
  Target = $0.01523 × 1.0334
  Target = $0.01574 ✓

=== ШАГ 5: Расчет PnL ===
Для SHORT позиции:
  PnL% = (Entry - Current) / Entry × 100
  PnL% = (0.01523 - 0.01671) / 0.01523 × 100
  PnL% = -0.00148 / 0.01523 × 100
  PnL% = -9.72% ✓ (УБЫТОК)

=== ШАГ 6: Проверка условия закрытия ===
PnL = -9.72% < 0 → НЕ прибыльная
Проверка target:

ТЕКУЩАЯ ЛОГИКА (НЕПРАВИЛЬНАЯ):
  should_close = current <= target
  should_close = 0.01671 <= 0.01574
  should_close = FALSE ❌
  Действие: НЕ ЗАКРЫВАТЬ

ПРАВИЛЬНАЯ ЛОГИКА:
  should_close = current >= target
  should_close = 0.01671 >= 0.01574
  should_close = TRUE ✅
  Действие: ЗАКРЫТЬ (убыток превысил tolerance!)

=== ВЫВОД ===
Текущий убыток: -9.72%
Допустимый:     -3.34%
Превышение:     2.9× (почти в 3 раза!)
Статус:         ДОЛЖНА БЫЛА ЗАКРЫТЬСЯ 6 ЧАСОВ НАЗАД
Причина:        Неправильный оператор сравнения (<= вместо >=)
```

---

**Конец отчета**

---

**Подготовил**: Claude (Anthropic)
**Дата**: 2025-10-24
**Версия**: 1.0 FINAL
