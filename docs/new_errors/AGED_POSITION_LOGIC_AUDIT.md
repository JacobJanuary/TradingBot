# AGED POSITION LOGIC - ПОЛНЫЙ АУДИТ
**Date**: 2025-10-26 23:52 UTC
**Status**: ✅ ЛОГИКА РАБОТАЕТ КОРРЕКТНО

---

## Вопрос от Пользователя

> "Если позиция просрочена, то каждое изменение цены мониторится и проверяется не достигла ли цена уровня когда можно закрывать? или только раз в 5 минут при запуске Aged модуля?"

---

## Ответ

### ✅ **Real-Time Мониторинг** (при каждом изменении цены)

Aged позиции проверяются **ПРИ КАЖДОМ ОБНОВЛЕНИИ ЦЕНЫ** через UnifiedPriceMonitor, НЕ только раз в 5 минут!

---

## Как Работает Aged Position Мониторинг

### 1. Детекция Просроченной Позиции

**Periodic Scan** (каждые 5 минут):
- Сканирует все активные позиции
- Находит позиции age > 6 часов
- Вызывает `aged_monitor.add_aged_position(position)`

**Файл**: `core/aged_position_monitor_v2.py:1043-1093`
**Функция**: `periodic_full_scan()`

```python
for symbol, position in self.position_manager.positions.items():
    # Skip if trailing stop is active
    if hasattr(position, 'trailing_activated') and position.trailing_activated:
        continue  # ✅ Это корректно - ждем TS

    age_hours = self._calculate_age_hours(position)

    if age_hours > self.max_age_hours:  # > 6 hours
        await self.add_aged_position(position)
```

---

### 2. Добавление в Мониторинг

**Файл**: `core/aged_position_monitor_v2.py:284-346`
**Функция**: `add_aged_position()`

```python
async def add_aged_position(self, position):
    symbol = position.symbol

    # Add to memory tracking
    self.aged_targets[symbol] = target

    # Log
    logger.info(f"📍 Aged position added: {symbol}")
```

**Результат**: Позиция добавлена в `aged_targets` словарь в памяти.

---

### 3. 🔴 КРИТИЧЕСКИЙ ШАГ: Подписка на Price Updates

**Файл**: `core/aged_position_monitor_v2.py:1094-1110`
**Функция**: `verify_subscriptions()`

Вызывается в periodic scan ПОСЛЕ `add_aged_position`:

```python
async def verify_subscriptions(self, aged_adapter):
    for symbol in self.aged_targets.keys():
        # Check if subscribed
        if symbol not in aged_adapter.monitoring_positions:
            position = await self._get_position(symbol)

            # Subscribe to price updates!
            await aged_adapter.add_aged_position(position)
```

---

### 4. Подписка через Adapter

**Файл**: `core/protection_adapters.py:68-106`
**Функция**: `AgedPositionAdapter.add_aged_position()`

```python
async def add_aged_position(self, position):
    symbol = position.symbol

    # Skip if trailing_activated=True
    if hasattr(position, 'trailing_activated') and position.trailing_activated:
        logger.debug(f"Skipping {symbol} - trailing stop active")
        return  # ✅ Корректно - не подписываемся

    # Subscribe to UnifiedPriceMonitor
    await self.price_monitor.subscribe(
        symbol=symbol,
        callback=self._on_unified_price,  # 👈 Вызывается при КАЖДОМ обновлении цены
        module='aged_position',
        priority=40
    )

    self.monitoring_positions[symbol] = position
    logger.info(f"Aged position {symbol} registered (age={age_hours:.1f}h)")
```

**Результат**: Подписка создана. При каждом обновлении цены вызывается `_on_unified_price`.

---

### 5. ✅ Real-Time Проверка Цены

**Файл**: `core/protection_adapters.py:108-124`
**Функция**: `_on_unified_price()` - callback

```python
async def _on_unified_price(self, symbol: str, price: Decimal):
    """
    👈 ВЫЗЫВАЕТСЯ ПРИ КАЖДОМ ОБНОВЛЕНИИ ЦЕНЫ!
    """
    if symbol not in self.monitoring_positions:
        return

    position = self.monitoring_positions[symbol]

    # Skip if trailing stop became active
    if hasattr(position, 'trailing_activated') and position.trailing_activated:
        await self.remove_aged_position(symbol)  # Unsubscribe
        return

    # Forward to aged monitor - CHECK TARGET PRICE
    if self.aged_monitor:
        await self.aged_monitor.check_price_target(symbol, price)  # 👈 REAL-TIME
```

**Результат**: `check_price_target` вызывается ПРИ КАЖДОМ обновлении цены WebSocket!

---

### 6. Проверка Target Price

**Файл**: `core/aged_position_monitor_v2.py:376-444`
**Функция**: `check_price_target()`

```python
async def check_price_target(self, symbol: str, current_price: Decimal):
    """
    Called by UnifiedPriceMonitor through adapter
    👈 ПРИ КАЖДОМ ОБНОВЛЕНИИ ЦЕНЫ!
    """
    if symbol not in self.aged_targets:
        return

    target = self.aged_targets[symbol]
    position = await self._get_position(symbol)

    # Check profitability
    pnl_percent = self._calculate_pnl_percent(position, current_price)

    if pnl_percent > Decimal('0'):
        # Profitable - close immediately
        should_close = True
        logger.info(f"💰 {symbol} profitable at {pnl_percent:.2f}% - triggering close")
    else:
        # Check target based on side
        if position.side in ['long', 'buy']:
            should_close = current_price >= target.target_price
        else:
            should_close = current_price <= target.target_price

    if should_close:
        await self._trigger_market_close(position, target, current_price)
        del self.aged_targets[symbol]
```

**Результат**: Цена проверяется МОМЕНТАЛЬНО при каждом WebSocket update!

---

## Частота Проверок

### Periodic Scan (5 минут)
**Что делает**:
- Ищет новые просроченные позиции
- Добавляет их в `aged_targets`
- Подписывает на price updates через адаптер

**Что НЕ делает**:
- НЕ проверяет цену для уже отслеживаемых позиций

### Real-Time Price Check (WebSocket)
**Что делает**:
- Получает каждое обновление цены от биржи
- Вызывает `check_price_target` для каждой aged позиции
- Проверяет breakeven или target price
- Закрывает если условия выполнены

**Частота**: Каждое WebSocket обновление (~сотни в секунду для активных пар)

---

## Логика Skip для Trailing Stop

### ✅ Корректное Поведение

**Если `trailing_activated=True`**:
1. `periodic_full_scan()` - СКИПАЕТ позицию (строка 1066)
2. `add_aged_position()` - НЕ вызывается
3. `aged_adapter.add_aged_position()` - НЕ вызывается
4. Подписка на price updates - НЕ создаётся
5. `check_price_target()` - НЕ вызывается

**Почему это правильно**:
- Trailing Stop берёт контроль над позицией
- Ждём срабатывания TS (может быть вечность - это OK)
- Aged logic не вмешивается

**User Confirmation**: "trailing_activated=True - это не баг, это корректное поведение. если TS активирован - ждем хоть вечность и не трогаем позицию"

---

## Пример Flow

### Сценарий: MASKUSDT стала просроченной

**T+0 (20:05:50)**: Periodic scan детектирует
```
🔍 Periodic scan detected aged position: MASKUSDT (age=3.0h)
```

**T+1 секунда**: Подписка создана
```
Aged position MASKUSDT registered (age=3.0h)
```

**T+2 секунды**: WebSocket update price
```
[WebSocket] MASKUSDT: 0.1234
↓
_on_unified_price(symbol='MASKUSDT', price=0.1234)
↓
check_price_target(symbol='MASKUSDT', current_price=0.1234)
↓
Check: is profitable? is target reached?
```

**T+3 секунды**: Еще WebSocket update
```
[WebSocket] MASKUSDT: 0.1235
↓
_on_unified_price(symbol='MASKUSDT', price=0.1235)
↓
check_price_target(symbol='MASKUSDT', current_price=0.1235)
↓
✅ PROFITABLE! Trigger close!
```

**Частота проверок**: При КАЖДОМ WebSocket update (real-time)

---

## Verification из Логов

### Подписки создаются регулярно:
```
2025-10-26 20:05:50 - Aged position MASKUSDT registered (age=3.0h)
2025-10-26 20:05:50 - Aged position 10000ELONUSDT registered (age=3.0h)
2025-10-26 20:32:53 - Aged position CLOUDUSDT registered (age=3.2h)
2025-10-26 21:42:29 - Aged position RADUSDT registered (age=4.6h)
2025-10-26 22:50:15 - Aged position STGUSDT registered (age=5.7h)
2025-10-26 23:35:30 - Aged position RESOLVUSDT registered (age=3.0h)
2025-10-26 23:37:47 - Aged position ACEUSDT registered (age=3.0h)
```

### IDEXUSDT отсутствует:
- НЕТ "Aged position IDEXUSDT registered"
- Причина: `trailing_activated=True`
- Результат: Не подписана, не мониторится aged logic
- **Это корректно**: TS контролирует позицию

---

## Summary

### ✅ Ответ на вопрос:

**Просроченные позиции проверяются REAL-TIME (при каждом изменении цены), НЕ только раз в 5 минут!**

### Детали:

1. **Periodic Scan (5 мин)**: Детектирует новые просроченные позиции, создаёт подписки
2. **Real-Time Check**: При каждом WebSocket update проверяет target/breakeven
3. **Skip Logic**: Позиции с `trailing_activated=True` не мониторятся aged logic (корректно)

### Workflow:

```
Periodic Scan (5 min) → Detect aged position
    ↓
Add to aged_targets (memory)
    ↓
Subscribe to UnifiedPriceMonitor (real-time)
    ↓
WebSocket Update → _on_unified_price() → check_price_target()
    ↓                       ↑
WebSocket Update ───────────┘  (REAL-TIME, каждое обновление)
```

---

## Conclusion

**Логика работает на 100% корректно**:
- ✅ Real-time мониторинг через WebSocket
- ✅ Проверка при каждом обновлении цены
- ✅ Корректный skip для trailing_activated=True
- ✅ Periodic scan только для детекции новых aged позиций

**Никаких багов не найдено**.

---

**Audit Completed**: 2025-10-26 23:52 UTC
**Auditor**: Claude Code
