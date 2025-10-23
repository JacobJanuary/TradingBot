# РАССЛЕДОВАНИЕ: Aged позиции не закрываются

**Дата:** 2025-10-23 05:41
**Статус:** 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА
**Автор:** Claude (AI Assistant)

---

## 🎯 ПРОБЛЕМА

Пользователь сообщил:
> "я вижу несколько позиции в плюсе, которые MAX_POSITION_AGE_HOURS>3 почему модуль их не закрывает?"

---

## 📊 НАХОДКИ

### 1. Текущее состояние БД

Найдено **15 активных позиций старше 3 часов:**

| Возраст | Количество | Символы | Trailing | PnL Range |
|---------|------------|---------|----------|-----------|
| 7.0h    | 14         | PRCLUSDT, XDCUSDT, OKBUSDT, SAROSUSDT, etc. | false | -7.68% to +3.97% |
| 4.4h    | 1          | **A2ZUSDT** | false | **+0.77%** |

**Позиции 7.0h в плюсе:**
- RADUSDT: +3.97%
- STOUSDT: +0.88%
- IDUSDT: +1.03%
- SAROSUSDT: +0.19%
- OKBUSDT: +0.08%
- SOSOUSDT: +0.08%
- SHIB1000USDT: +0.12%

### 2. Конфигурация

**Ожидаемая конфигурация:**
```env
MAX_POSITION_AGE_HOURS=3        # Порог aged
AGED_GRACE_PERIOD_HOURS=8       # Grace период
```

**Фактическая конфигурация:**
```env
# .env строка 37:
AGED_GRACE_PERIOD_HOURS=8

# .env строка 202:
AGED_GRACE_PERIOD_HOURS=1    ← ПЕРЕОПРЕДЕЛЯЕТ!
```

**Лог подтверждает:**
```
2025-10-23 05:29:21,280 - core.aged_position_monitor_v2 - INFO - AgedPositionMonitorV2 initialized: max_age=3h, grace=1h
```

### 3. Логика aged_position_manager

**Из кода (`core/aged_position_monitor_v2.py`):**

1. **Определение aged:**
   ```python
   async def check_position_age(self, position) -> bool:
       age_hours = self._calculate_age_hours(position)
       return age_hours > self.max_age_hours  # > 3h
   ```

2. **Закрытие profitable позиций:**
   ```python
   async def check_price_target(self, symbol: str, current_price: Decimal):
       pnl_percent = self._calculate_pnl_percent(position, current_price)

       if pnl_percent > 0:
           # Profitable - close immediately
           should_close = True
           logger.info(f"💰 {symbol} profitable at {pnl_percent:.2f}% - triggering close")
   ```

3. **Принудительное закрытие:**
   - После `MAX_POSITION_AGE + AGED_GRACE_PERIOD`
   - С фактическими настройками: `3 + 1 = 4 часов`

---

## 🔍 КОРНЕВЫЕ ПРИЧИНЫ

### Проблема #1: 🔴 ДУБЛИКАТ КОНФИГУРАЦИИ

**Файл:** `.env`
**Строки:** 37 и 202

```env
# Строка 37 (верная):
AGED_GRACE_PERIOD_HOURS=8          # Grace period for breakeven attempts after MAX_POSITION_AGE

# Строка 202 (переопределение):
AGED_GRACE_PERIOD_HOURS=1
```

**Последствия:**
- Grace period = 1 час вместо 8
- Позиции должны закрываться после `3 + 1 = 4 часов`
- Позиции 7.0h **давно перешли порог** 4h

---

### Проблема #2: 🟡 A2ZUSDT НЕ В AGED MONITOR

**Позиция A2ZUSDT:**
- Возраст: 4.4 часа (> 3h порога)
- PnL: +0.77% (в плюсе!)
- Trailing: false (не пропущена фильтром)
- Статус: active

**Но в логах:**
```
2025-10-23 05:39:10 - 📍 Aged position added: HNTUSDT (age=3.9h)
2025-10-23 05:39:10 - 📍 Aged position added: RADUSDT (age=3.9h)
...
(A2ZUSDT отсутствует)
```

**Причина:**
A2ZUSDT не в `position_manager.positions` в момент сканирования (05:17-05:39).

Проверка логов показывает:
- Последнее обновление A2ZUSDT price: 01:21 (перед рестартом)
- При рестарте в 05:17: "Checking position A2ZUSDT: has_sl=True"
- Но позиция не добавлена в aged_targets

**Возможные причины:**
1. Позиция не загружена в memory `positions` dict
2. Ошибка в `check_position_age()` (не залогирована)
3. Race condition при старте

---

### Проблема #3: 🔴 МЕХАНИЗМ ЗАКРЫТИЯ НЕ РАБОТАЕТ

**Ожидаемые логи (если бы механизм работал):**
```
💰 RADUSDT profitable at 3.97% - triggering close
🎯 Aged target reached for RADUSDT
```

**Фактические логи:**
- ❌ Нет логов "💰 profitable"
- ❌ Нет логов "🎯 Aged target reached"
- ❌ Нет вызовов `_trigger_market_close`

**Причина:**
Метод `check_price_target()` **не вызывается**.

**Проверка кода:**
```python
# aged_position_monitor_v2.py:113
async def check_price_target(self, symbol: str, current_price: Decimal):
    """
    Check if current price reached target for aged position
    Called by UnifiedPriceMonitor through adapter
    """
```

**UnifiedPriceMonitor статус:**
```
2025-10-23 05:29:21,284 - websocket.unified_price_monitor - INFO - UnifiedPriceMonitor started (minimal mode)
```

**Проблема:** "minimal mode" может не вызывать aged_position_monitor callbacks.

---

## 📈 ХРОНОЛОГИЯ

### 01:20 - A2ZUSDT открыта
```
01:20:31 - Opening position ATOMICALLY: A2ZUSDT BUY 51934.0
01:20:42 - ✅ Position A2ZUSDT has Stop Loss order: 10675670 at 0.00378
```

### 05:14 - Первый рестарт
```
05:14:33 - AgedPositionMonitorV2 initialized: max_age=3h, grace=1h
```

### 05:17 - Сканирование позиций
```
05:17:13 - Checking position A2ZUSDT: has_sl=True, price=0.00378
05:17:18 - 📍 Aged position added: HNTUSDT (age=3.5h)
05:17:18 - 📍 Aged position added: RADUSDT (age=3.5h)
...
(A2ZUSDT не добавлена)
```

### 05:29 - Второй рестарт (деплой duplicate fix)
```
05:29:21 - AgedPositionMonitorV2 initialized: max_age=3h, grace=1h
05:29:21 - UnifiedPriceMonitor started (minimal mode)
```

### 05:36-05:41 - Позиции добавлены, но не закрываются
```
05:36:48 - 📍 Aged position added: XDCUSDT (age=3.9h, phase=grace, target=$0.0599)
05:39:10 - 📍 Aged position added: HNTUSDT (age=3.9h, phase=grace, target=$1.7533)
...
(Нет попыток закрытия)
```

---

## 🛠️ РЕШЕНИЕ

### 1. Исправить дубликат в .env

**Действие:** Удалить строку 202

```bash
# Найти дубликат
grep -n "AGED_GRACE_PERIOD_HOURS" .env

# Удалить строку 202
sed -i '202d' .env
```

**Ожидаемый результат:**
- Grace period = 8 часов
- Позиции будут закрываться после `3 + 8 = 11 часов`

### 2. Добавить A2ZUSDT в aged monitor вручную

**Временное решение:** Дождаться следующего цикла сканирования

**Долгосрочное решение:** Исследовать, почему позиция не загружается в `position_manager.positions`

### 3. Проверить UnifiedPriceMonitor

**Проблема:** "minimal mode" может не вызывать aged callbacks

**Действие:** Проверить код `UnifiedPriceMonitor` и настройки

---

## 📊 ОЖИДАЕМОЕ ПОВЕДЕНИЕ

### С AGED_GRACE_PERIOD_HOURS=8:

| Возраст | Статус | Действие |
|---------|--------|----------|
| 0-3h    | Normal | Нет действий |
| 3-11h   | Aged (grace) | Breakeven attempts, НЕ закрывать |
| 11h+    | Aged (force) | Принудительное закрытие |

**Текущие позиции:**
- 7.0h → В grace фазе → **НЕ закрывать** (правильно)
- 4.4h → В grace фазе → **НЕ закрывать** (правильно)

### С AGED_GRACE_PERIOD_HOURS=1 (текущее):

| Возраст | Статус | Действие |
|---------|--------|----------|
| 0-3h    | Normal | Нет действий |
| 3-4h    | Aged (grace) | Breakeven attempts |
| 4h+     | Aged (force) | **ДОЛЖНЫ БЫТЬ ЗАКРЫТЫ!** |

**Текущие позиции:**
- 7.0h → Старше 4h → **ДОЛЖНЫ БЫТЬ ЗАКРЫТЫ** ❌
- 4.4h → Старше 4h → **ДОЛЖНА БЫТЬ ЗАКРЫТА** ❌

**Проблема:** Механизм закрытия НЕ работает!

---

## 🎯 КРИТИЧНОСТЬ

**Уровень:** 🔴 HIGH

**Причины:**
1. **Дубликат конфигурации** - легко исправить
2. **A2ZUSDT не отслеживается** - средняя проблема
3. **Механизм закрытия не работает** - **КРИТИЧНО**

**Последствия:**
- Позиции накапливаются без закрытия
- Риск больших убытков
- aged_position_manager фактически **не функционирует**

---

## 📝 РЕКОМЕНДАЦИИ

### Немедленно:

1. ✅ **Исправить .env** - удалить дубликат AGED_GRACE_PERIOD_HOURS на строке 202
2. ✅ **Перезапустить бота** - применить правильную конфигурацию
3. ✅ **Мониторить логи** - проверить, появятся ли закрытия aged позиций

### Краткосрочно (24 часа):

1. Исследовать, почему UnifiedPriceMonitor в "minimal mode" не вызывает callbacks
2. Проверить, почему A2ZUSDT не в `position_manager.positions`
3. Добавить тесты для aged_position_monitor_v2

### Долгосрочно:

1. Добавить validation для .env на дубликаты
2. Добавить health check для aged_position_manager
3. Добавить алерты, если позиции старше MAX_POSITION_AGE не закрываются

---

## 🔍 ДИАГНОСТИЧЕСКИЕ КОМАНДЫ

### Проверить дубликаты в .env:
```bash
grep "AGED_GRACE_PERIOD_HOURS" .env
```

### Проверить aged позиции в БД:
```sql
SELECT
    symbol,
    ROUND(EXTRACT(EPOCH FROM (NOW() - created_at))/3600, 1) as age_hours,
    trailing_activated,
    ROUND(((current_price - entry_price) / entry_price * 100)::numeric, 2) as pnl_percent
FROM monitoring.positions
WHERE status = 'active'
  AND created_at < NOW() - INTERVAL '3 hours'
ORDER BY created_at ASC;
```

### Мониторить закрытия:
```bash
tail -f logs/trading_bot.log | grep -E "💰|🎯|market.*close|Aged target"
```

---

## ✅ СТАТУС

- [x] Проблема выявлена
- [x] Корневые причины найдены
- [ ] Исправление применено
- [ ] Тестирование завершено
- [ ] Проблема решена

---

END OF INVESTIGATION REPORT
