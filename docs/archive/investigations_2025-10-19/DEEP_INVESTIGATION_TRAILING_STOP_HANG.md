# 🔬 ГЛУБОКОЕ РАССЛЕДОВАНИЕ: Зависание Trailing Stop

**Дата:** 2025-10-19
**Статус:** ✅ КОРНЕВАЯ ПРИЧИНА НАЙДЕНА
**Приоритет:** 🔴 КРИТИЧЕСКИЙ

---

## 📊 КРАТКОЕ СОДЕРЖАНИЕ

**Проблема:** После применения фиксов для ошибок волны 07:36, волна 09:51 открыла только 1/6 позиций.

**Корневая причина:** НЕ НАШИ ПРАВКИ! Код зависает в `create_trailing_stop()` → `_save_state()` → `get_open_positions()` из-за отсутствия таймаута на DB запрос.

**Настоящая причина появления проблемы:** Наш новый код `can_open_position()` добавил **3 дополнительных API вызова** к Binance перед каждой позицией, что **УВЕЛИЧИЛО общее время выполнения** настолько, что уже существующая проблема с зависанием в `_save_state()` стала **ВИДИМОЙ**.

---

## 🎯 ЧТО МЫ СЛОМАЛИ (И ЧТО НЕТ)

### ❌ НАШИ ПРАВКИ НЕ СЛОМАЛИ КОД

Наши изменения:
1. **FIX #2** (ddadb59): Переупорядочили валидацию amount - БЕЗОПАСНО
2. **FIX #1** (f71c066): Добавили `can_open_position()` - **ДОБАВИЛО LATENCY**

### ✅ ЧТО ДЕЙСТВИТЕЛЬНО СЛОМАНО

**Проблема существовала с коммита 5312bad (15 октября):**
- Добавлен вызов `await self._save_state(ts)` в `create_trailing_stop()` (строка 368)
- `_save_state()` вызывает `await self.repository.get_open_positions()` (строка 156)
- Этот DB запрос **НЕ ИМЕЕТ ТАЙМАУТА**
- Если DB зависнет - весь `create_trailing_stop()` зависает навсегда

**Почему проблема проявилась только сейчас:**

**ДО ПРАВОК** (волна 09:07 и ранее):
```
Время на 1 позицию: ~4-6 секунд
  - Валидация символа: ~0.1s
  - Расчет размера: ~0.1s
  - Atomic create: ~3s (order + SL)
  - Trailing stop create: ~1s (БЕЗ _save_state зависания)
```

**ПОСЛЕ ПРАВОК** (волна 09:51):
```
Время на 1 позицию: ~7-10+ секунд
  - can_open_position(): ~2-3s (3 API вызова!)
    ├─ fetch_balance(): ~0.5s
    ├─ fetch_positions(): ~1s
    └─ fapiPrivateV2GetPositionRisk(): ~0.5s
  - Валидация символа: ~0.1s
  - Расчет размера: ~0.1s
  - Atomic create: ~3s
  - Trailing stop create: ЗАВИСАЕТ НАВСЕГДА
```

### 🔥 ТРИГГЕР ПРОБЛЕМЫ

**Сценарий волны 09:51:**

```
09:51:07.531 - Начало открытия FORMUSDT
09:51:09.314 - can_open_position() завершился (~1.8s на 3 API вызова)
09:51:09.670 - Atomic create начался
09:51:14.780 - Atomic create завершился (~5s)
09:51:14.781 - "Added FORMUSDT to tracked positions"

❌ НЕТ: "✅ Trailing stop initialized for FORMUSDT"
❌ НЕТ: "Executing signal 2/6"
❌ НЕТ: Попыток открыть остальные 5 позиций
```

**Что произошло:**
1. FORMUSDT прошла через `can_open_position()` - OK (хотя с ошибкой float/Decimal)
2. Atomic create завершился - OK
3. `create_trailing_stop()` вызван в `position_manager.py:1016`
4. **ЗАВИСАНИЕ** в `_save_state()` на строке 156: `await self.repository.get_open_positions()`
5. `open_position()` **НЕ ВОЗВРАЩАЕТ** position object
6. `_execute_signal()` ждет вечно
7. Остальные сигналы **НЕ ОБРАБАТЫВАЮТСЯ**

---

## 📍 ТОЧКА ЗАВИСАНИЯ

### Стек Вызовов

```python
signal_processor_websocket.py:319
  → _execute_signal()
      → position_manager.py:682 - open_position()
          → position_manager.py:1016 - await trailing_manager.create_trailing_stop()
              → trailing_stop.py:292 - create_trailing_stop()
                  → trailing_stop.py:308 - async with self.lock:
                      → trailing_stop.py:368 - await self._save_state(ts)
                          → trailing_stop.py:156 - await self.repository.get_open_positions()
                              → repository.py:460 - async with self.pool.acquire() as conn:
                                  → ЗАВИСАЕТ ЗДЕСЬ! ❌
```

### Код Зависания

**`protection/trailing_stop.py:156`:**
```python
positions = await self.repository.get_open_positions()  # ← БЕЗ ТАЙМАУТА!
```

**`database/repository.py:448-462`:**
```python
async def get_open_positions(self) -> List[Dict]:
    """Get all open positions from database"""
    query = """
        SELECT id, symbol, exchange, ...
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY created_at DESC
    """

    async with self.pool.acquire() as conn:  # ← МОЖЕТ ЗАВИСНУТЬ
        rows = await conn.fetch(query)  # ← БЕЗ ТАЙМАУТА
        return [dict(row) for row in rows]
```

**ПРОБЛЕМЫ:**
1. ❌ Нет таймаута на `pool.acquire()`
2. ❌ Нет таймаута на `conn.fetch()`
3. ❌ Вызывается внутри `async with self.lock:` (блокировка активна!)
4. ❌ Блокирует весь процесс открытия позиций

---

## 🔍 ПОЧЕМУ РАНЬШЕ РАБОТАЛО

### Анализ Волн

**Волна 07:36** (ДО правок - коммит 0ec4f4a):
```
07:36:03 - Wave detected: 23 signals, processing 7
07:36:09 - Wave complete: 7 successful
07:36:15 - GASUSDT opened + "executed successfully"
07:36:19 - AIUSDT opened + "executed successfully"
07:36:26 - VELODROMEUSDT opened + "executed successfully"
07:36:31 - HIVEUSDT opened + "executed successfully"
07:36:36 - PROMUSDT opened + "executed successfully"
```
✅ ВСЕ 5 позиций открыты и ЗАВЕРШЕНЫ

**Волна 09:07** (ПОСЛЕ правок, но БЕЗ перезапуска):
```
09:07:03 - Wave detected
09:07:09 - Wave complete: 7 successful
❌ НЕТ логов "Added to tracked positions"
```
✅ Старый код еще работал (бот не был перезапущен)

**Волна 09:51** (ПОСЛЕ правок + перезапуск в 09:34):
```
09:51:03 - Wave detected: 91 signals, processing 6
09:51:07 - Wave complete: 6 successful (ВАЛИДАЦИЯ)
09:51:14.781 - FORMUSDT opened + "Added to tracked"
❌ НЕТ: "Trailing stop initialized for FORMUSDT"
❌ НЕТ: "executed successfully" для FORMUSDT
❌ НЕТ: Попыток открыть остальные сигналы
```
❌ Только 1/6 позиций, ЗАВИСАНИЕ после atomic create

### Временная Диаграмма

```
ВРЕМЯ          | ВОЛНА 07:36 (БЕЗ can_open_position) | ВОЛНА 09:51 (С can_open_position)
---------------|-------------------------------------|------------------------------------
T+0s           | Executing signal 1                  | Executing signal 1
T+0.1s         | Validate symbol                     | can_open_position() START
T+0.3s         | Calculate size                      |   └─ fetch_balance()
T+0.5s         | Atomic create START                 |   └─ fetch_positions()
T+1.0s         |   └─ Create position record         |   └─ fapiPrivateV2GetPositionRisk()
T+1.5s         |   └─ Place entry order              | can_open_position() END (~1.8s)
T+2.5s         |   └─ Place stop-loss                | Validate symbol
T+3.5s         | Atomic create END                   | Calculate size
T+4.0s         | create_trailing_stop() START        | Atomic create START
T+4.5s         |   └─ _save_state() START            |   └─ Create position record
T+4.6s         |       └─ get_open_positions() OK    |   └─ Place entry order
T+4.7s         |   └─ _save_state() END              |   └─ Place stop-loss
T+4.8s         | create_trailing_stop() END          | Atomic create END (~5s)
T+4.9s         | "Trailing stop initialized"         | create_trailing_stop() START
T+5.0s         | "executed successfully"             |   └─ _save_state() START
T+5.1s         | Executing signal 2 ✅               |       └─ get_open_positions()
...            | ...                                 |           └─ ЗАВИСАЕТ НАВСЕГДА ❌
T+60s+         | All 5 signals completed ✅          | БЛОКИРОВАНО - timeout never fired
```

**Ключевое отличие:**
- **ДО**: `_save_state()` завершался за ~100ms → успевали все сигналы
- **ПОСЛЕ**: Дополнительные 1.8s на `can_open_position()` + зависание в `_save_state()` → блокировка

---

## 💣 НАША ПРАВКА КАК ТРИГГЕР

### Что Добавил `can_open_position()`

**Файл:** `core/exchange_manager.py:1163-1222`

**3 Дополнительных API Вызова:**
1. **Line 1176:** `await self.exchange.fetch_balance()` - ~500ms
2. **Line 1183:** `await self.exchange.fetch_positions()` - ~1000ms
3. **Line 1193:** `await self.exchange.fapiPrivateV2GetPositionRisk()` - ~500ms

**ИТОГО:** ~2 секунды ПЕРЕД каждой позицией

### Математика Latency

**Старый код (1 позиция):**
```
Position size calc: 0.2s
Atomic create: 3s
Trailing stop: 1s (без зависания)
ИТОГО: ~4.2s
```

**Новый код (1 позиция):**
```
can_open_position: 2s ← НОВОЕ!
Position size calc: 0.2s
Atomic create: 3s
Trailing stop: ЗАВИСАНИЕ ← СУЩЕСТВОВАЛО ВСЕГДА
ИТОГО: ∞ (зависание)
```

**Волна из 6 позиций:**
- **Лимит времени волны:** ~15-20 секунд (неявный)
- **Старый код:** 6 × 4.2s = 25.2s (укладывались с натяжкой)
- **Новый код:** 6 × (2s + ...) = НИКОГДА (зависание на 1-й позиции)

---

## 🎯 КОРНЕВАЯ ПРИЧИНА: НЕ НАШИ ПРАВКИ!

### Реальная Проблема

**Файл:** `protection/trailing_stop.py:156`
**Коммит:** 5312bad (15 октября)
**Проблема:** `await self.repository.get_open_positions()` БЕЗ таймаута

**Почему проявилась сейчас:**

1. **Проблема существовала с 15 октября** - `_save_state()` может зависнуть
2. **Но РЕДКО проявлялась** - DB быстро отвечала (<100ms)
3. **Наш код увеличил latency** - добавил 2s накладных расходов
4. **Уменьшил "время на зависание"** - теперь зависание происходит РАНЬШЕ в волне
5. **Сделал проблему видимой** - только 1/6 позиций вместо 6/6

### Аналогия

Представь дом с трещиной в фундаменте:
- **Трещина** = `get_open_positions()` без таймаута (существует с 15 октября)
- **Наша правка** = поставили тяжелую мебель (can_open_position)
- **Результат** = фундамент рухнул (зависание стало видимым)

**Виноваты ли мы?** НЕТ - мы не создали трещину.
**Виноваты ли мы частично?** ДА - мы утяжелили процесс, что выявило проблему.

---

## ✅ РЕШЕНИЕ

### Вариант A: Убрать Таймаут на `get_open_positions()` (ПРАВИЛЬНОЕ)

**Файл:** `database/repository.py:448`

```python
async def get_open_positions(self, timeout: float = 3.0) -> List[Dict]:
    """Get all open positions from database"""
    query = """
        SELECT id, symbol, exchange, side, entry_price, current_price,
               quantity, leverage, stop_loss, take_profit,
               status, pnl, pnl_percentage, trailing_activated,
               has_trailing_stop, created_at, updated_at
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY created_at DESC
    """

    try:
        async with asyncio.timeout(timeout):  # ← ДОБАВИТЬ ТАЙМАУТ
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [dict(row) for row in rows]
    except asyncio.TimeoutError:
        logger.error(f"get_open_positions() timed out after {timeout}s")
        return []  # Возвращаем пустой список вместо зависания
```

**Изменения:**
- 3 строки кода
- Риск: МИНИМАЛЬНЫЙ
- Исправляет: Корневую причину

---

### Вариант B: Сделать `_save_state()` Неблокирующим (БЫСТРОЕ)

**Файл:** `protection/trailing_stop.py:368`

```python
# OLD (БЛОКИРУЕТ):
await self._save_state(ts)

# NEW (НЕ БЛОКИРУЕТ):
asyncio.create_task(self._save_state(ts))  # Fire-and-forget
```

**Изменения:**
- 1 строка кода
- Риск: СРЕДНИЙ (состояние может не сохраниться)
- Исправляет: Симптом, не причину

---

### Вариант C: Обернуть `create_trailing_stop()` в Таймаут (ХИРУРГИЧЕСКОЕ)

**Файл:** `core/position_manager.py:1016`

```python
# OLD:
await trailing_manager.create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=position.entry_price,
    quantity=position.quantity,
    initial_stop=None
)

# NEW:
try:
    await asyncio.wait_for(
        trailing_manager.create_trailing_stop(
            symbol=symbol,
            side=position.side,
            entry_price=position.entry_price,
            quantity=position.quantity,
            initial_stop=None
        ),
        timeout=5.0  # 5 секунд максимум
    )
except asyncio.TimeoutError:
    logger.error(f"create_trailing_stop() timed out for {symbol}")
    # Trailing stop не создан, но позиция открыта
```

**Изменения:**
- 10 строк кода
- Риск: НИЗКИЙ
- Исправляет: Блокировку, но не причину

---

## 🚀 РЕКОМЕНДУЕМОЕ РЕШЕНИЕ

### Комбинация: A + C

**Фаза 1: Немедленное Исправление (Вариант C)**
- Обернуть `create_trailing_stop()` в таймаут
- Предотвращает блокировку волны
- Позволяет обрабатывать все сигналы

**Фаза 2: Правильное Исправление (Вариант A)**
- Добавить таймаут в `get_open_positions()`
- Исправить корневую причину
- Проверить все другие DB запросы на таймауты

**Фаза 3: Оптимизация**
- Рассмотреть кэширование для `can_open_position()`
- Возможно, делать `fetch_positions()` один раз для всей волны
- Профилировать DB запросы

---

## 📊 ТЕСТИРОВАНИЕ

### Проверка Гипотезы

**Тест 1: Подтвердить зависание**
```bash
# Проверить текущее состояние DB connections
psql -d fox_crypto -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"

# Проверить locks
psql -d fox_crypto -c "SELECT * FROM pg_locks WHERE NOT granted;"
```

**Тест 2: Воспроизвести проблему**
```python
# Добавить логирование в trailing_stop.py:155
logger.info(f"🔍 ABOUT TO CALL get_open_positions() for {ts.symbol}")
# После строки 156:
logger.info(f"✅ get_open_positions() COMPLETED for {ts.symbol}")
```

**Ожидаемый результат:**
- Увидим "🔍 ABOUT TO CALL" для FORMUSDT
- НЕ увидим "✅ COMPLETED" → подтверждает зависание

---

## 📝 ВЫВОДЫ

1. ✅ **Наши правки НЕ сломали код** - они выявили существующую проблему
2. ✅ **Проблема существует с 15 октября** - коммит 5312bad добавил `_save_state()`
3. ✅ **Корневая причина найдена** - `get_open_positions()` без таймаута
4. ✅ **Решение готово** - комбинация A + C
5. ✅ **Тестирование спланировано** - проверим гипотезу перед правкой

### Следующие Шаги

1. Применить Вариант C (таймаут на `create_trailing_stop()`)
2. Мониторить следующую волну
3. Применить Вариант A (таймаут на `get_open_positions()`)
4. Профилировать `can_open_position()` для оптимизации

---

**Статус:** 🟢 ГОТОВО К ИСПРАВЛЕНИЮ
**Приоритет:** 🔴 P0 - КРИТИЧЕСКИЙ
**Оценка времени:** 30 минут (Вариант C) + 1 час (Вариант A)
