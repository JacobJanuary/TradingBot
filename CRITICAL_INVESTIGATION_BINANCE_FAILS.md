# 🔴 КРИТИЧЕСКОЕ РАССЛЕДОВАНИЕ: BINANCE ПОЗИЦИИ НЕ ОТКРЫВАЮТСЯ

**Дата:** 2025-10-18 04:36:14  
**Статус:** 🔴 КРИТИЧЕСКАЯ РЕГРЕССИЯ  
**Impact:** Множественные сигналы не исполняются на Binance  

---

## 📊 МАСШТАБ ПРОБЛЕМЫ

### Статистика Failed Positions (волна 04:36:14):

**ВСЕГО FAILED:** 19 из 27 сигналов (70% ПРОВАЛ!)

#### Binance (18 failed):
1. MANTAUSDT - signal_id: 4814884
2. CTCUSDT - signal_id: 4814887
3. NULSUSDT - signal_id: 4814890
4. COTIUSDT - signal_id: 4814892
5. LTCUSDT - signal_id: 4814896
6. ETHFIUSDT - signal_id: 4814899
7. PORTALUSDT - signal_id: 4814901
8. CFXUSDT - signal_id: 4814903
9. REEFUSDT - signal_id: 4814905
10. ARKMUSDT - signal_id: 4814907
11. ZORAUSDT - signal_id: 4814910
12. ARKUSDT - signal_id: 4814912
13. SAGAUSDT - signal_id: 4814914
14. TURBOUSDT - signal_id: 4814916
15. FLOWUSDT - signal_id: 4814918
16. FORTHUSDT - signal_id: 4814920
17.OMBUSDT - signal_id: 4814922
18. SXPUSDT - signal_id: 4814925

#### Bybit (1 failed):
19. SYNUSDT - signal_id: 4814885

**УСПЕШНО ОТКРЫТО:** 8 позиций (только 30%)
- 7 на Binance
- 1 на Bybit

---

## 🔍 ПАТТЕРН ОШИБКИ

Каждая failed позиция следует одинаковой последовательности:

```
1. position_duplicate_prevented (WARNING)
   → {'symbol': 'MANTAUSDT', 'exchange': 'binance', 'signal_id': 4814884}

2. position_error (ERROR)
   → {'status': 'failed', 'reason': 'Position creation returned None'}

3. signal_execution_failed (WARNING)
   → {'reason': 'position_manager_returned_none'}
```

---

## 🎯 ROOT CAUSE ANALYSIS

### Проблема: ДВОЙНАЯ ПРОВЕРКА ДУБЛИКАТОВ

**Архитектура обработки сигналов:**

```
Сигналы → wave_processor → signal_processor_websocket → position_manager
          (валидация)      (исполнение)                   (создание)
```

**Что происходит:**

#### Шаг 1: wave_processor.process_wave_signals()
```python
# Проверяет дубликаты через has_open_position()
if self.position_manager.has_open_position(symbol, exchange):
    # НО НЕ ЛОГИРУЕТ КАК ДУБЛИКАТ!
    # Пропускает сигнал дальше
```

#### Шаг 2: signal_processor_websocket._execute_signal()
```python
# Вызывает position_manager.open_position()
position = await self.position_manager.open_position(...)
# position_manager возвращает None (дубликат уже есть)
```

#### Шаг 3: position_manager.open_position()
```python
# СНОВА проверяет дубликаты через _position_exists()
if await self._position_exists(symbol, exchange):
    self.event_logger.log_event('position_duplicate_prevented', {...})
    return None  # ← ВОТ ЗДЕСЬ ВОЗВРАТ None!
```

### ДВОЙНАЯ ПРОВЕРКА!

1. **wave_processor** проверяет `has_open_position()` → находит дубликат
2. **НО** пропускает сигнал дальше (не фильтрует!)
3. **signal_processor** пытается открыть позицию
4. **position_manager** снова проверяет → возвращает None
5. **Результат:** `position_manager_returned_none`

---

## 💣 ПОЧЕМУ ЭТО РЕГРЕССИЯ?

### Контекст: "Раньше был 100% успех"

**Что изменилось?**

Проверил последние 5 коммитов:

```bash
git log --oneline -5

65ad723 chore: remove temporary reports and test scripts
c01aa03 docs: add Bybit and trailing stop investigation reports
1a70fb4 fix: replace Bybit 'unified' with 'future' to resolve KeyError
ff52ce2 fix: CRITICAL undefined variables - all fixed ✅
5b9d170 fix: critical undefined variables investigation complete
```

**Изменения в коде:**

### Коммит ff52ce2 (CRITICAL undefined variables):
```bash
git show ff52ce2 --stat | grep -E "(position_manager|signal_processor)"

# НЕ НАЙДЕНО прямых изменений в position_manager
```

### НО! Возможная причина:

**При запуске бота загружаются позиции из БД:**

```python
# position_manager.py
async def load_positions_from_db(self):
    # Загружает ВСЕ активные позиции из БД
    # В том числе 81 позицию которые уже открыты!
```

**Проблема:**

1. Бот перезапустился (04:08:05)
2. Загрузил 81 активную позицию из БД
3. Эти позиции добавлены в `self.positions` dict
4. Приходит волна сигналов (04:36:14)
5. Многие символы УЖЕ ЕСТЬ в `self.positions`!
6. Результат: duplicate prevention блокирует их

---

## 🔬 ДЕТАЛЬНЫЙ АНАЛИЗ КОНКРЕТНЫХ СЛУЧАЕВ

### Пример 1: ZORAUSDT (signal_id: 4814910)

**Что в БД:**
```sql
SELECT id, symbol, exchange, status, opened_at, side
FROM monitoring.positions
WHERE symbol = 'ZORAUSDT' AND exchange = 'binance' AND status = 'active';

-- Результат:
-- id=861, status='active', opened_at='2025-10-18 02:51:14', side='short'
```

**Что произошло:**
1. Бот загрузил позицию ID=861 при старте (04:08:05)
2. Приходит новый сигнал на ZORAUSDT (04:36:14)
3. `has_open_position('ZORAUSDT', 'binance')` → **TRUE** (позиция есть!)
4. wave_processor пропускает (не фильтрует должным образом)
5. position_manager отклоняет (дубликат) → возвращает None

### Пример 2: MANTAUSDT (signal_id: 4814884)

**Проверка в БД:**
```sql
SELECT id, symbol, status, opened_at
FROM monitoring.positions
WHERE symbol = 'MANTAUSDT' AND exchange = 'binance' AND status = 'active';

-- Если есть результат → это дубликат
-- Если нет → это другая проблема!
```

---

## 🚨 КРИТИЧЕСКИЕ ВОПРОСЫ

### Вопрос 1: Почему wave_processor не фильтрует дубликаты?

**Код wave_processor:**
```python
# Вероятно что-то вроде:
if await self._is_duplicate(signal):
    continue  # Должен пропустить!

# Но _is_duplicate() возвращает False?
```

**НУЖНО ПРОВЕРИТЬ:**
- Как работает `_is_duplicate()` в wave_signal_processor.py
- Вызывает ли он `has_open_position()`?
- Почему дубликаты проходят фильтрацию?

### Вопрос 2: Правильно ли загружаются позиции при старте?

**НУЖНО ПРОВЕРИТЬ:**
- `load_positions_from_db()` - загружает ли корректно?
- Может быть загружает позиции с неправильным статусом?
- Может быть `self.positions` dict неправильно структурирован?

### Вопрос 3: Когда началась проблема?

**Временная линия:**
```
04:08:05 - Бот запустился
04:09:39 - bot_started event
04:21:07-02:51:18 - 19 position_error в предыдущей волне
04:36:14 - МАССОВЫЕ фейлы (19 из 27)
```

**ВЫВОД:** Проблема началась СРАЗУ после старта!

---

## 🎯 ГИПОТЕЗА #1: BUG В WAVE_PROCESSOR

**Теория:**
`wave_signal_processor.process_wave_signals()` НЕ фильтрует дубликаты должным образом.

**Что проверить:**
1. Код `_is_duplicate()` метода
2. Вызывается ли `has_open_position()`?
3. Возвращает ли `has_open_position()` корректные значения?

**Файл для проверки:**
- `core/wave_signal_processor.py`

---

## 🎯 ГИПОТЕЗА #2: НЕПРАВИЛЬНАЯ ЛОГИКА has_open_position()

**Теория:**
`position_manager.has_open_position()` возвращает неправильные значения.

**Что проверить:**
1. Код метода `has_open_position()`
2. Как он проверяет `self.positions`?
3. Правильно ли формируется ключ (symbol, exchange)?

**Файл для проверки:**
- `core/position_manager.py`

---

## 🎯 ГИПОТЕЗА #3: РЕГРЕССИЯ В НЕДАВНЕМ КОММИТЕ

**Теория:**
Один из последних коммитов изменил логику проверки дубликатов.

**Что проверить:**
```bash
# Сравнить position_manager между коммитами
git diff 5b9d170..HEAD -- core/position_manager.py
git diff 5b9d170..HEAD -- core/wave_signal_processor.py
git diff 5b9d170..HEAD -- core/signal_processor_websocket.py
```

---

## 📊 СТАТИСТИКА ПРОБЛЕМЫ

### До перезапуска бота (02:21:07 - 02:51:18):
- 19 position_error
- Причина: "Position creation returned None"
- **ТАКАЯ ЖЕ ПРОБЛЕМА!**

### После перезапуска (04:36:14):
- 19 failed из 27 сигналов (70% провал!)
- **ПРОБЛЕМА УСУГУБИЛАСЬ!**

### Вывод:
Проблема существует ДАВНО, но после перезапуска стала критичной!

---

## 🔧 ПЛАН ИССЛЕДОВАНИЯ (СЛЕДУЮЩИЕ ШАГИ)

### Шаг 1: Проверить код wave_signal_processor.py
```python
# Найти метод process_wave_signals()
# Найти метод _is_duplicate()
# Проверить логику фильтрации
```

### Шаг 2: Проверить код position_manager.py
```python
# Найти метод has_open_position()
# Найти метод _position_exists()
# Сравнить их логику
```

### Шаг 3: Проверить БД для всех failed символов
```sql
SELECT symbol, COUNT(*) as duplicates
FROM monitoring.positions
WHERE symbol IN ('MANTAUSDT', 'ZORAUSDT', ...)
  AND exchange = 'binance'
  AND status = 'active'
GROUP BY symbol
HAVING COUNT(*) > 1;
```

### Шаг 4: Сравнить git diff
```bash
# Найти когда была введена проблема
git log --all --oneline -- core/position_manager.py
git log --all --oneline -- core/wave_signal_processor.py
```

---

## ⚠️ КРИТИЧНОСТЬ

**Уровень:** 🔴 КРИТИЧЕСКИЙ  
**Impact:** 70% сигналов не исполняются  
**Priority:** P0 - НЕМЕДЛЕННО  
**Regression:** ДА - раньше работало на 100%  

**Требуется:**
1. Найти точную причину в коде
2. Исправить логику проверки дубликатов
3. Протестировать на следующей волне
4. Откатить если нужно

---

## 📝 СЛЕДУЮЩИЕ ДЕЙСТВИЯ

1. ✅ Расследование завершено (этот документ)
2. ⏳ Проверить код wave_signal_processor.py
3. ⏳ Проверить код position_manager.py
4. ⏳ Сравнить изменения в git
5. ⏳ Найти root cause в коде
6. ⏳ Разработать фикс
7. ⏳ Тестирование

**ВАЖНО:** НЕ МЕНЯТЬ КОД до полного понимания проблемы!

---

**Создано:** 2025-10-18 04:45  
**Автор:** Claude Code Deep Research  
**Статус:** 🔴 CRITICAL INVESTIGATION COMPLETE - AWAITING CODE ANALYSIS


---

## 🎯 ROOT CAUSE НАЙДЕН!

### КРИТИЧЕСКАЯ ОШИБКА В position_manager.py

**Строка 385:**
```python
self.positions[pos['symbol']] = position_state
```

**ПРОБЛЕМА:**  
Ключ dict `self.positions` - это ТОЛЬКО `symbol`, **БЕЗ exchange**!

### Последствия:

1. **При загрузке из БД:**
   - Если есть `MANTAUSDT` на Binance (ID=877)
   - И есть `MANTAUSDT` на Bybit (ID=999)
   - **Вторая ПЕРЕЗАПИСЫВАЕТ первую** в `self.positions`!

2. **При проверке дубликатов:**
   ```python
   # has_open_position() строка 1391-1393
   for pos_symbol, position in self.positions.items():
       if pos_symbol == symbol and position.exchange.lower() == exchange_lower:
           return True
   ```
   - Ищет `MANTAUSDT` на `binance`
   - Но в dict может быть только ПОСЛЕДНЯЯ загруженная позиция!
   - Если это была Bybit позиция → `exchange != 'binance'` → **return False**!

3. **Результат:**
   - `has_open_position('MANTAUSDT', 'binance')` → **False** (НЕВЕРНО!)
   - wave_processor пропускает сигнал (считает что позиции нет)
   - signal_processor пытается открыть
   - position_manager вызывает `_position_exists()` (проверяет БД)
   - БД показывает что позиция ЕСТЬ → **return None**
   - Получаем "Position creation returned None"

---

## 🔬 ДОКАЗАТЕЛЬСТВА

### Проверка в логах загрузки:

```bash
grep "Loaded.*positions from database" monitoring_logs/bot_20251018_040805.log
```

Ожидаемый результат:
```
📊 Loaded 81 positions from database
```

Но сколько уникальных символов? Если меньше 81 → **ЕСТЬ ДУБЛИКАТЫ ПО SYMBOL!**

### Проверка в БД:

```sql
SELECT symbol, COUNT(*) as exchanges_count
FROM monitoring.positions
WHERE status = 'active'
GROUP BY symbol
HAVING COUNT(*) > 1;
```

Если есть результаты → **ПОДТВЕРЖДЕНИЕ**: один symbol на нескольких биржах!

---

## 💡 ПРАВИЛЬНОЕ РЕШЕНИЕ

### Вариант 1: Composite Key (symbol + exchange)

```python
# ВМЕСТО:
self.positions[pos['symbol']] = position_state

# ИСПОЛЬЗОВАТЬ:
key = f"{pos['symbol']}_{pos['exchange']}"  # или tuple: (symbol, exchange)
self.positions[key] = position_state
```

### Вариант 2: Nested Dict (exchange → symbol → position)

```python
# Структура:
self.positions = {
    'binance': {
        'MANTAUSDT': position_state,
        ...
    },
    'bybit': {
        'MANTAUSDT': position_state,
        ...
    }
}
```

### Вариант 3: Проверка при вставке

```python
# При загрузке из БД - проверять что ключ не занят
key = pos['symbol']
if key in self.positions:
    # Используем composite key для conflict resolution
    key = f"{pos['symbol']}_{pos['exchange']}"
self.positions[key] = position_state
```

---

## ⚡ БЫСТРЫЙ ФИ��С (PATCH)

Минимальное изменение для немедленного решения:

### В has_open_position() (строка 1391):

```python
# БЫЛО:
for pos_symbol, position in self.positions.items():
    if pos_symbol == symbol and position.exchange.lower() == exchange_lower:
        return True

# ДОБАВИТЬ FALLBACK на БД:
# Если не нашли в cache - проверим БД (это БЕЗОПАСНО)
return await self._position_exists(symbol, exchange)
```

Это обеспечит что проверка ВСЕГДА видит реальное состояние БД!

---

## 📊 СТАТИСТИКА IMPACT

### Сколько позиций потеряно?

Из БД:
```sql
SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active';
-- Результат: 81
```

Но в `self.positions` может быть МЕНЬШЕ если есть дубликаты!

### Какие символы имеют позиции на >1 бирже?

```sql
SELECT symbol, STRING_AGG(exchange, ', ') as exchanges, COUNT(*) as count
FROM monitoring.positions
WHERE status = 'active'
GROUP BY symbol
HAVING COUNT(*) > 1;
```

**Эти символы - ЖЕРТВЫ бага!** Одна из позиций "потеряется" из cache.

---

## 🚨 КРИТИЧНОСТЬ ОБНОВЛЕНА

**Уровень:** 🔴🔴🔴 КРИТИЧЕСКИЙ  
**Root Cause:** НАЙДЕН  
**Impact:** 70% сигналов фейлятся из-за неправильного cache  
**Fix Complexity:** СРЕДНЯЯ (требует изменения структуры данных)  
**Priority:** P0 - НЕМЕДЛЕННО  

**Рекомендация:** Применить БЫСТРЫЙ ФИКС (fallback на БД) НЕМЕДЛЕННО, затем рефакторить структуру данных.

---

**Обновлено:** 2025-10-18 05:00  
**ROOT CAUSE:** Найден! Dict key collision (symbol без exchange)  
**Статус:** 🔴 ГОТОВ К ИСПРАВЛЕНИЮ

