# 🔍 FORENSIC INVESTIGATION: Aged Positions Not Closing (INTERIM REPORT)

**Status**: ⚠️ IN PROGRESS - CRITICAL FINDING IDENTIFIED
**Date**: 2025-10-24
**Issue**: Просроченные позиции в плюсе висят на биржах и НЕ закрываются

---

## ✅ ЭТАП 1 COMPLETED: АЛГОРИТМЫ ИЗУЧЕНЫ

### 1.1 Trailing Stop (Эталон) - Работает Корректно

**Файл**: `protection/trailing_stop.py` (1218 строк)

**Алгоритм активации**:
```python
# Активация при profit >= 1.5%
if profit_pct >= activation_percent:  # 1.5%
    activate_trailing_stop()
```

**State Machine**:
- INACTIVE → WAITING → ACTIVE → TRIGGERED

**Peak Price Persistence**:
- ✅ Сохраняется в БД (`monitoring.trailing_stop_state`)
- ✅ Обновляется при новом максимуме
- ✅ Rate limiting: min 10s interval, min 0.2% change

---

### 1.2 Aged Position Monitor V2 - АЛГОРИТМ НАЙДЕН

**Файл**: `core/aged_position_monitor_v2.py` (817 строк)

#### Параметры (из кода):
```python
self.max_age_hours = Decimal('3')  # 3 часа
self.grace_period_hours = Decimal('8')  # 8 часов grace
self.loss_step_percent = Decimal('0.5')  # 0.5% за час
self.commission_percent = Decimal('0.1')  # 0.1% commission
```

#### Фазы обработки:

**GRACE PERIOD** (0-8 часов после max_age):
```python
# Цель: закрыть по breakeven
if hours_over_limit <= grace_period_hours:
    phase = 'grace'
    loss_tolerance = 0

    # Breakeven = entry + 2*commission
    double_commission = 2 * 0.1% = 0.2%

    # LONG
    target_price = entry_price * 1.002

    # SHORT
    target_price = entry_price * 0.998
```

**PROGRESSIVE LIQUIDATION** (после grace period):
```python
hours_in_progressive = hours_over_limit - grace_period_hours
loss_tolerance = hours_in_progressive * 0.5%

# LONG
target_price = entry_price * (1 - loss_tolerance/100)

# SHORT
target_price = entry_price * (1 + loss_tolerance/100)
```

#### Логика закрытия (КРИТИЧНАЯ!):

**Метод**: `check_price_target()` (строка 224)

```python
async def check_price_target(self, symbol: str, current_price: Decimal):
    # Проверяет достигнут ли target

    pnl_percent = _calculate_pnl_percent(position, current_price)

    if pnl_percent > 0:
        # 🔴 ПОЗИЦИЯ В ПЛЮСЕ - ЗАКРЫВАЕТ СРАЗУ!
        should_close = True
        logger.info(f"💰 {symbol} profitable at {pnl_percent:.2f}% - triggering close")
    else:
        # Позиция в минусе - ждет target_price
        if position.side in ['long', 'buy']:
            should_close = current_price >= target_price
        else:
            should_close = current_price <= target_price

    if should_close:
        await _trigger_market_close(position, target, current_price)
        del aged_targets[symbol]
```

---

## 🔴 КРИТИЧНАЯ НАХОДКА #1

### Проблема: check_price_target НЕ ВЫЗЫВАЕТСЯ АВТОМАТИЧЕСКИ!

**Где вызывается**:
```python
# Вызывается ТОЛЬКО из UnifiedPriceMonitor через adapter!
# НЕ вызывается из periodic_full_scan!
```

**Метод periodic_full_scan (строка 769)**:
```python
async def periodic_full_scan(self):
    """Scan all active positions for aged detection"""

    for symbol, position in position_manager.positions.items():
        # Skip if already tracked
        if symbol in aged_targets:
            continue  # ← ПРОПУСКАЕТ УЖЕ ОТСЛЕЖИВАЕМЫЕ!

        # Check age
        age_hours = _calculate_age_hours(position)

        if age_hours > max_age_hours:
            await add_aged_position(position)  # ← ТОЛЬКО ДОБАВЛЯЕТ!
            # ❌ НЕ ПРОВЕРЯЕТ ЦЕНУ!
            # ❌ НЕ ВЫЗЫВАЕТ check_price_target!
```

### Следствие:

1. **Periodic scan** (каждые 5 мин):
   - ✅ Находит просроченные позиции
   - ✅ Добавляет их в `aged_targets`
   - ❌ НЕ проверяет цену
   - ❌ НЕ пытается закрыть

2. **check_price_target**:
   - ✅ Умеет закрывать позиции в плюсе
   - ❌ Вызывается ТОЛЬКО через UnifiedPriceMonitor
   - ❌ Если WebSocket update НЕ приходит → позиция НЕ закрывается!

---

## 🔴 КРИТИЧНАЯ НАХОДКА #2

### Две системы Aged Manager - конфликт?

**В коде**:

1. **Старый AgedPositionManager** (`core/aged_position_manager.py`, 755 строк)
   - Импортируется в `main.py:24`
   - Используется если `USE_UNIFIED_PROTECTION=false`

2. **Новый AgedPositionMonitorV2** (`core/aged_position_monitor_v2.py`, 817 строк)
   - Используется через `unified_protection`
   - Активен если `USE_UNIFIED_PROTECTION=true`

**Текущая конфигурация** (`.env`):
```bash
USE_UNIFIED_PROTECTION=true
```

**Логика в main.py** (строка 286-316):
```python
if not use_unified_protection:
    # Старый менеджер
    self.aged_position_manager = AgedPositionManager(...)
else:
    # Новый v2 через unified_protection
    self.aged_position_manager = None

    # CRITICAL FIX: Recover aged positions state
    if position_manager.unified_protection:
        recovered = await recover_aged_positions_state(...)

        # Start periodic scan
        asyncio.create_task(start_periodic_aged_scan(
            ...,
            interval_minutes=5  # Каждые 5 минут
        ))
```

**Вывод**: V2 активен, старый НЕ используется.

---

## 🎯 ГИПОТЕЗЫ ROOT CAUSE

### Гипотеза #1: WebSocket Updates НЕ приходят для просроченных позиций

**Почему**:
- `check_price_target()` вызывается ТОЛЬКО при price update
- Если WebSocket connection для символа не активен → updates не приходят
- Позиция в плюсе, но check_price_target НЕ вызывается → НЕ закрывается

**Что проверить**:
- Логи WebSocket connections для просроченных символов
- Вызывается ли `check_price_target()` для этих символов
- Есть ли price updates в логах

### Гипотеза #2: UnifiedPriceMonitor НЕ подписан на просроченные позиции

**Почему**:
- UnifiedPriceMonitor может не знать о позициях добавленных через periodic scan
- Нужна explicit подписка на price updates

**Что проверить**:
- Как UnifiedPriceMonitor получает список символов для мониторинга
- Добавляются ли туда символы из periodic scan

### Гипотеза #3: periodic_full_scan НЕ триггерит price check

**Почему**:
- periodic_full_scan ТОЛЬКО добавляет позиции в tracking
- НЕ вызывает check_price_target для уже добавленных

**Решение**:
- periodic_full_scan должен вызывать check_price_target для всех aged позиций

---

## 📋 СЛЕДУЮЩИЕ ШАГИ

### ЭТАП 2: Анализ логов (NEXT)
- [ ] Найти логи последней сессии
- [ ] Проверить periodic scan активность
- [ ] Найти события aged positions
- [ ] Проверить WebSocket updates для просроченных символов
- [ ] Найти вызовы check_price_target

### ЭТАП 3: Анализ БД
- [ ] Найти просроченные позиции
- [ ] Проверить aged_targets записи
- [ ] Проверить события в monitoring.events
- [ ] Сравнить БД vs биржи

### ЭТАП 4: Проверка UnifiedPriceMonitor
- [ ] Как подписывается на символы
- [ ] Вызывает ли check_price_target
- [ ] Логи price updates

---

## 💡 ПРЕДВАРИТЕЛЬНЫЕ ВЫВОДЫ

### Архитектурная проблема:

Aged Position Monitor V2 имеет **архитектурное разделение**:

1. **Detection (периодический scan)**:
   - ✅ Работает: находит просроченные позиции каждые 5 мин
   - ✅ Добавляет в `aged_targets`

2. **Closing (price-driven)**:
   - ⚠️ Зависит от WebSocket price updates
   - ❌ Если updates не приходят → позиция НЕ закрывается
   - ❌ periodic_full_scan НЕ триггерит закрытие

### Ключевое отличие от Trailing Stop:

**Trailing Stop**: активно обновляется при каждом price update
**Aged Manager**: пассивно ждет price update для проверки target

### Возможное решение:

`periodic_full_scan()` должен НЕ ТОЛЬКО добавлять позиции, но и:
1. Проверять уже добавленные aged позиции
2. Получать текущую цену
3. Вызывать `check_price_target()` для всех aged символов

---

**Status**: Продолжаю расследование → ЭТАП 2: Анализ логов

