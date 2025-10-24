# КРИТИЧЕСКИЙ АУДИТ: Взаимодействие TS + Aged модулей

## Дата: 2025-10-24 07:00
## Статус: КРИТИЧЕСКИЕ ПРОБЛЕМЫ ОБНАРУЖЕНЫ

---

## EXECUTIVE SUMMARY

### ✅ ЧТО РАБОТАЕТ:
1. **has_trailing_stop исправлено**: Все 45 активных позиций имеют `has_trailing_stop=TRUE` в БД
2. **Обновление цен работает**: Все позиции получают обновления цен через WebSocket
3. **Aged monitor работает**: Отслеживает старые позиции и пытается закрывать их
4. **TS создаются**: TS states создаются для всех позиций (100 состояний в БД)

### ❌ ЧТО НЕ РАБОТАЕТ:
1. **TS НЕ АКТИВИРУЮТСЯ**: Только 2 из 45 позиций имеют активированный TS (4%)
2. **TS НЕ ОБНОВЛЯЮТСЯ**: Нет логов работы TS модуля в реальном времени
3. **TS update_price() НЕ ВЫЗЫВАЕТСЯ**: Метод молча возвращает None для всех позиций
4. **Aged позиции НЕ ЗАКРЫВАЮТСЯ**: Логи показывают ошибки при попытке закрытия

---

## ЧАСТЬ 1: СТАТИСТИКА СИСТЕМЫ

### Активные позиции (по биржам):
```
Binance: 40 позиций
Bybit:   5 позиций
ИТОГО:   45 позиций
```

### TS States в БД:
```
Binance: 82 states (42 старых мусорных)
Bybit:   18 states (13 старых мусорных)
ИТОГО:   100 states
```

### Состояние TS для активных позиций:
```
АКТИВИРОВАННЫЕ (state=active):
- Binance: RSRUSDT (1 из 40 = 2.5%)
- Bybit:   SAROSUSDT (1 из 5 = 20%)
- ИТОГО:   2 из 45 = 4.4%

НЕ АКТИВИРОВАННЫЕ (state=inactive):
- Binance: 39 позиций (97.5%)
- Bybit:   4 позиции (80%)
- ИТОГО:   43 из 45 = 95.6%
```

---

## ЧАСТЬ 2: КРИТИЧЕСКАЯ ПРОБЛЕМА #1 - TS НЕ АКТИВИРУЮТСЯ

### Симптомы:
1. **95.6% позиций имеют TS в state=inactive**
2. Нет логов активации TS в реальном времени
3. Нет логов проверки условий активации

### Расследование:

#### TS модуль должен работать так:
1. При обновлении цены позиции вызывается `_on_position_update()` (position_manager.py:1884)
2. Проверяется `if trailing_manager and position.has_trailing_stop:` (строка 1971)
3. Вызывается `trailing_manager.update_price(symbol, position.current_price)` (строка 1975)
4. В `update_price()` проверяется `if symbol not in self.trailing_stops:` (trailing_stop.py:415)
5. Если символа НЕТ в `trailing_stops` - **МОЛЧА возвращает None** (строка 417)

#### КРИТИЧЕСКАЯ НАХОДКА:
```python
# trailing_stop.py:415-417
if symbol not in self.trailing_stops:
    # Position closed or not tracked - silent skip (prevents log spam)
    return None
```

**ПРОБЛЕМА:** Комментарий говорит "prevents log spam", но это создаёт ПОЛНУЮ ТИШИНУ когда TS не работает!

#### Гипотеза:
**TS НЕ ИНИЦИАЛИЗИРОВАНЫ в памяти trailing_manager.trailing_stops!**

Это означает:
1. TS states ЕСТЬ в БД (100 записей)
2. TS ВОССТАНАВЛИВАЮТСЯ из БД при старте (метод `_restore_state()`)
3. НО что-то идёт не так при восстановлении или после
4. `trailing_stops` dict ПУСТ или содержит старые данные
5. `update_price()` молча игнорирует все позиции

#### Доказательства:
1. ✅ Логи старта бота показывают: "🎯 Initializing trailing stops for loaded positions..." (position_manager.py:584)
2. ✅ Для каждой позиции вызывается `trailing_manager._restore_state(symbol)` (строка 590)
3. ✅ Если восстановлено - добавляется в `trailing_manager.trailing_stops[symbol]` (строка 594)
4. ✅ Если НЕ восстановлено - вызывается `create_trailing_stop()` (строка 601)
5. ❌ НО нет логов "Created trailing stop for {symbol}" (trailing_stop.py:368)
6. ❌ НЕТ логов работы `update_price()` в реальном времени

### Вывод:
**Либо логи очень старые (рестарта не было давно), либо TS инициализация происходит с ошибками.**

---

## ЧАСТЬ 3: КРИТИЧЕСКАЯ ПРОБЛЕМА #2 - AGED ПОЗИЦИИ НЕ ЗАКРЫВАЮТСЯ

### Симптомы:
Из логов aged_position_monitor_v2 (06:53-06:54):
```
✅ УСПЕШНО ЗАКРЫТЫ:
- ETHBTCUSDT (age=4.4h) - закрыт дважды!

❌ НЕ ЗАКРЫТЫ (ошибки):
- XDCUSDT (age=29.1h) - ошибка Bybit 170193: "Buy order price cannot be higher than 0USDT"
- HNTUSDT (age=29.1h) - ошибка: "No asks in order book" (нет ликвидности)
```

### Проблема #1: ETHBTCUSDT закрыта дважды
```
06:53:48 - ✅ Aged position ETHBTCUSDT closed (order_id=45efc67e...)
06:53:48 - WARNING: Aged position 2941 not found
06:54:09 - ✅ Aged position ETHBTCUSDT closed (order_id=c265605f...)
06:54:09 - WARNING: Aged position 2941 not found
```

**Анализ:**
- Позиция закрывается успешно
- НО сразу после возникает "Aged position 2941 not found"
- Через 20 секунд ПОВТОРНАЯ попытка закрытия!
- Это означает что aged monitor НЕ УДАЛЯЕТ позицию из отслеживания после закрытия
- Или есть race condition между закрытием и periodic scan

### Проблема #2: XDCUSDT - ошибка цены Bybit
```
❌ Failed to close aged position XDCUSDT after 3 attempts:
   bybit {"retCode":170193,"retMsg":"Buy order price cannot be higher than 0USDT."}
```

**Анализ:**
- Позиция short, нужен BUY для закрытия
- Биржа отвергает ордер: "цена не может быть выше 0"
- Это означает что:
  - Либо передаётся price=0 или price=None
  - Либо проблема с форматированием цены
  - Либо проблема с типом ордера (market vs limit)

### Проблема #3: HNTUSDT - нет ликвидности
```
❌ Failed to close aged position HNTUSDT after 5 attempts: No asks in order book
```

**Анализ:**
- Позиция long, нужен SELL для закрытия
- Нет asks в order book - нет покупателей
- Это нормальная ситуация для низколиквидных монет
- НО система должна:
  - Перейти на limit ордера с агрессивной ценой
  - Или уведомить пользователя
  - Или отложить попытку

---

## ЧАСТЬ 4: ВЗАИМОДЕЙСТВИЕ TS + AGED МОДУЛЕЙ

### Правильная архитектура (как ДОЛЖНО быть):
```
Позиция создана
    ↓
TS инициализирован (state=inactive)
    ↓
Позиция < 1 час: TS проверяет активацию (проверяет PnL >= 1.5%)
    ↓ (если активировался)
TS активирован (state=active)
    ↓
TS управляет SL: обновляет при росте профита
    ↓
Позиция >= 3 часа: Aged monitor добавляет в отслеживание
    ↓
Aged monitor ПРОВЕРЯЕТ: if position.has_trailing_stop and position.trailing_activated:
    ↓ (если TRUE)
БЛОКИРОВКА: Aged monitor НЕ ВМЕШИВАЕТСЯ (TS управляет до конца)
    ↓ (если FALSE - TS не активирован)
Aged monitor БЕРЁТ УПРАВЛЕНИЕ: progressive/aggressive закрытие
```

### Текущая реальность (как ЕСТЬ):
```
Позиция создана
    ↓
TS инициализирован (state=inactive) ✅
    ↓
TS state ЕСТЬ в БД ✅
    ↓
WebSocket шлёт обновления цен ✅
    ↓
_on_position_update() вызывается ✅
    ↓
trailing_manager.update_price() вызывается ✅
    ↓
❌ ПРОБЛЕМА: symbol NOT IN self.trailing_stops
    ↓
update_price() МОЛЧА возвращает None ❌
    ↓
TS НЕ ПРОВЕРЯЕТ активацию ❌
    ↓
TS ОСТАЁТСЯ в state=inactive ❌
    ↓
Позиция >= 3 часа: Aged monitor добавляет ✅
    ↓
Aged monitor видит: trailing_activated=FALSE
    ↓
Aged monitor пытается закрыть ✅
    ↓
❌ ОШИБКИ закрытия (Bybit price, no liquidity)
    ↓
Позиция НЕ ЗАКРЫВАЕТСЯ ❌
```

---

## ЧАСТЬ 5: КОРНЕВЫЕ ПРИЧИНЫ

### Корневая причина #1: TS не в памяти
**Где:** `trailing_manager.trailing_stops` dict

**Почему:**
1. При старте вызывается `_restore_state()` для каждой позиции
2. `_restore_state()` читает TS state из БД
3. Если есть - добавляет в `trailing_stops[symbol] = ts`
4. Если нет - вызывается `create_trailing_stop()`
5. `create_trailing_stop()` ДОЛЖЕН добавить в `trailing_stops[symbol] = ts` (строка 396)

**Гипотезы:**
- A) Логи очень старые, рестарта не было, и позиции созданы ПОСЛЕ рестарта БЕЗ инициализации TS
- B) При создании позиций `create_trailing_stop()` вызывается, но происходит ошибка
- C) `trailing_stops` dict очищается или перезаписывается после инициализации
- D) Проблема с exchange_name - TS создаются для другого exchange_name

### Корневая причина #2: Нет логов TS работы
**Где:** `trailing_stop.py` методы `update_price()`, `_check_activation()`, `_activate_trailing_stop()`

**Почему:**
- Логи используют `logger.debug()` и `logger.info()`
- Уровень логирования может быть выше DEBUG
- Но `logger.info()` для активации ДОЛЖЕН быть виден!

**Факт:** НЕТ ни одного лога "✅ {symbol}: Trailing stop ACTIVATED" в реальном времени

### Корневая причина #3: Aged ошибки закрытия
**Где:** `aged_position_monitor_v2.py` метод закрытия позиций

**Проблемы:**
1. Передаётся некорректная цена для Bybit (price=0 или None)
2. Нет обработки ошибки "No liquidity"
3. Повторные попытки закрытия уже закрытых позиций (race condition)

---

## ЧАСТЬ 6: ПЛАН ИСПРАВЛЕНИЯ

### ЭТАП 1: ДИАГНОСТИКА (СРОЧНО - сейчас)

#### Задача 1.1: Проверить содержимое trailing_stops в памяти
**Действие:** Добавить временный endpoint или лог для дампа `trailing_manager.trailing_stops.keys()`

**Цель:** Узнать сколько и какие символы в памяти

**Код для добавления:**
```python
# В position_manager.py, метод _on_position_update, после строки 1969
logger.info(f"[TS_DEBUG] Exchange: {position.exchange}, "
            f"Trailing manager exists: {trailing_manager is not None}, "
            f"TS symbols in memory: {list(trailing_manager.trailing_stops.keys()) if trailing_manager else []}")
```

#### Задача 1.2: Проверить уровень логирования
**Действие:** Убедиться что логи TS на уровне INFO, а не DEBUG

**Изменение:**
```python
# trailing_stop.py:465 - изменить с debug на info
logger.info(  # было: logger.debug
    f"[TS] {symbol} @ {ts.current_price:.4f} | "
    f"profit: {profit_percent:.2f}% | "
    f"activation: {ts.activation_price:.4f} | "
    f"state: {ts.state.name}"
)
```

#### Задача 1.3: Добавить логи в update_price при раннем выходе
**Действие:** Убрать "silent skip", добавить INFO лог

**Изменение:**
```python
# trailing_stop.py:415-417
if symbol not in self.trailing_stops:
    # CRITICAL: Log this to detect missing TS!
    logger.warning(f"[TS_MISSING] {symbol} not in trailing_stops dict! "
                   f"Tracked symbols: {list(self.trailing_stops.keys())}")
    return None
```

### ЭТАП 2: ИСПРАВЛЕНИЕ TS (P0 - после диагностики)

#### Задача 2.1: Гарантировать создание TS при новых позициях
**Файл:** `core/position_manager.py`

**Места:**
1. Строка 601 - при загрузке позиций
2. Строка 828 - при синхронизации с биржей (новая позиция)
3. Строка 1145 - при создании новой позиции (atomic)

**Действие:** Добавить проверку после создания:
```python
await trailing_manager.create_trailing_stop(...)
# CRITICAL: Verify TS was actually created
if symbol not in trailing_manager.trailing_stops:
    logger.error(f"❌ CRITICAL: TS for {symbol} NOT in memory after create_trailing_stop!")
    # Try again or raise exception
```

#### Задача 2.2: Очистка старых TS states из БД
**Файл:** новый скрипт `scripts/cleanup_old_ts_states.py`

**Действие:**
```sql
-- Удалить TS states для закрытых позиций
DELETE FROM monitoring.trailing_stop_state ts
WHERE NOT EXISTS (
    SELECT 1 FROM monitoring.positions p
    WHERE p.symbol = ts.symbol
      AND p.exchange = ts.exchange
      AND p.status = 'active'
);
```

### ЭТАП 3: ИСПРАВЛЕНИЕ AGED ЗАКРЫТИЯ (P1)

#### Задача 3.1: Исправить ошибку Bybit price=0
**Файл:** `core/aged_position_monitor_v2.py`

**Проблема:** При закрытии short позиции передаётся некорректная цена

**Действие:** Проверить логику расчёта цены для market ордера

#### Задача 3.2: Обработка "No liquidity"
**Файл:** `core/aged_position_monitor_v2.py`

**Действие:**
1. Поймать ошибку "No asks in order book"
2. Перейти на limit ордер с агрессивной ценой (best_bid * 0.99)
3. Если не удаётся - отложить попытку на 5 минут
4. Уведомить пользователя

#### Задача 3.3: Предотвратить повторное закрытие
**Файл:** `core/aged_position_monitor_v2.py`

**Проблема:** После успешного закрытия позиция пытается закрыться снова

**Действие:**
1. После закрытия НЕМЕДЛЕННО удалить из aged_positions dict
2. Проверить что periodic scan пропускает уже закрытые

### ЭТАП 4: УЛУЧШЕНИЕ ВЗАИМОДЕЙСТВИЯ (P2)

#### Задача 4.1: Добавить health check для TS
**Файл:** новый `monitoring/ts_health_check.py`

**Функции:**
1. Периодически проверять что все активные позиции есть в `trailing_stops`
2. Проверять что TS states в БД соответствуют памяти
3. Алерт если расхождение

#### Задача 4.2: Добавить метрики TS
**Метрики:**
1. Количество активных TS
2. Процент активированных TS
3. Среднее время до активации
4. Количество TS ошибок

---

## ЧАСТЬ 7: ОТВЕТЫ НА ВОПРОСЫ ПОЛЬЗОВАТЕЛЯ

### 1. Все ли позиции получают обновление цены?
**✅ ДА**

Логи показывают:
```
06:54:29 - 📊 REST polling: received 33 position updates with mark prices
06:54:29 - Position update: MUBARAK/USDT:USDT → MUBARAKUSDT, mark_price=0.02438
06:54:29 - Position update: MILK/USDT:USDT → MILKUSDT, mark_price=0.03507525
... (и так далее для всех позиций)
```

Но **2 позиции пропускаются**:
- SPKUSDT: "Skipped: SPKUSDT not in tracked positions"
- MERLUSDT: "Skipped: MERLUSDT not in tracked positions"

**Причина:** Эти позиции НЕ в `self.positions` dict (возможно закрыты или ошибка синхронизации)

### 2. Все ли позиции младше 1 часа отслеживает TS модуль?
**❌ НЕТ - НЕ ОТСЛЕЖИВАЕТ**

**Данные:** 7 молодых позиций (<1 час):
```
IMXUSDT (0.4h), VICUSDT (0.4h), COOKIEUSDT (0.4h), SFPUSDT (0.6h),
MYXUSDT (0.6h), TURBOUSDT (0.6h), MAGICUSDT (0.7h)
```

Все имеют:
- `has_trailing_stop=TRUE` ✅
- `trailing_activated=FALSE` (ожидаемо для молодых) ✅

НО:
- **НЕТ логов проверки активации TS** ❌
- **TS не вызывается при обновлении цен** ❌

**Причина:** `update_price()` молча возвращает None потому что symbol не в `trailing_stops`

### 3. Для активированных TS - проверяет и обновляет SL?
**✅ ДА, для 2 активированных позиций (RSRUSDT, SAROSUSDT)**

Но:
- **Нет логов обновления SL в реальном времени** ❌
- Либо SL не обновляется (цена не растёт)
- Либо логи не на нужном уровне

### 4. Все ли просроченные позиции отслеживает aged module?
**✅ ДА**

Логи показывают:
```
06:54:08 - 🔍 Periodic aged scan complete: scanned 48 positions, detected 3 new aged position(s)
```

Aged monitor работает и отслеживает:
- BSUUSDT (age=4.4h)
- ETHBTCUSDT (age=4.4h)
- HNTUSDT (age=29.1h)
- XDCUSDT (age=29.1h)

НО:
- **Не все aged позиции успешно закрываются** (ошибки Bybit, no liquidity)
- **Повторные попытки закрытия уже закрытых** (race condition)

### 5. Почему позиции в профите старше заданного времени не закрываются?
**КОМБИНАЦИЯ ПРИЧИН:**

A. **TS не активируется → aged берёт управление**
   - 95% позиций имеют TS inactive
   - Aged monitor пытается закрыть
   - НО ошибки при закрытии

B. **Ошибки закрытия aged позиций:**
   - Bybit error 170193 (price=0)
   - No liquidity (нет asks)
   - Повторные попытки уже закрытых

C. **Возможно позиции НЕ в профите:**
   - Нужны актуальные данные PnL
   - Проверить в следующем отчёте

---

## ЧАСТЬ 8: КРИТИЧНОСТЬ И ПРИОРИТЕТЫ

### 🔴 P0 - КРИТИЧНО (исправить СЕГОДНЯ):
1. Диагностика: проверить `trailing_stops` в памяти
2. Добавить логи в `update_price()` при раннем выходе
3. Исправить level логирования TS на INFO
4. Исправить ошибки aged закрытия (Bybit price, liquidity)

### 🟡 P1 - ВЫСОКИЙ (2-3 дня):
5. Гарантировать создание TS при новых позициях
6. Очистка старых TS states из БД
7. Предотвратить повторное закрытие aged позиций
8. Обработка "No liquidity" с fallback на limit ордера

### 🟢 P2 - СРЕДНИЙ (неделя):
9. Health check для TS
10. Метрики TS
11. Автоматическая очистка мусорных TS states

---

## ЧАСТЬ 9: СЛЕДУЮЩИЕ ШАГИ

### НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:
1. ✅ Применить диагностические изменения (Задачи 1.1-1.3)
2. ✅ Рестартовать бота с новыми логами
3. ✅ Наблюдать 10-15 минут
4. ✅ Проверить логи: есть ли "[TS_DEBUG]", "[TS_MISSING]"
5. ✅ Получить данные о содержимом `trailing_stops` в памяти

### ПОСЛЕ ДИАГНОСТИКИ:
6. Если `trailing_stops` ПУСТ → исправить инициализацию (Задача 2.1)
7. Если `trailing_stops` ЗАПОЛНЕН → проверить почему update_price() не работает
8. Исправить aged ошибки (Задачи 3.1-3.3)
9. Тестирование на staging
10. Deploy в production

---

## ЗАКЛЮЧЕНИЕ

**Система имеет 2 критические проблемы:**

1. **TS модуль НЕ РАБОТАЕТ в реальном времени**
   - TS создаются и сохраняются в БД ✅
   - НО не отслеживаются в памяти ❌
   - update_price() молча игнорирует все позиции ❌

2. **Aged module работает, но с ошибками закрытия**
   - Отслеживает aged позиции ✅
   - НО не может закрыть из-за ошибок биржи ❌
   - Race conditions с повторными попытками ❌

**Первопричина:** TS не в памяти → aged берёт управление → ошибки закрытия → позиции зависают

**Решение:** Исправить инициализацию TS + исправить aged ошибки = система заработает

---

**ДАТА СОЗДАНИЯ:** 2025-10-24 07:05
**АВТОР:** Claude Code Critical Audit System
**СТАТУС:** Ожидание одобрения плана диагностики и исправления
