# ✅ DEBUG ЛОГИ ДОБАВЛЕНЫ

**Дата:** 2025-10-18 07:05
**Файл:** `core/position_manager.py`
**Цель:** Диагностика inconsistency между has_open_position() и _position_exists()

---

## 📝 ИЗМЕНЕНИЯ

### Backup создан
```bash
core/position_manager.py.backup.20251018_070420_before_debug
```

### Добавлено DEBUG логирование

#### 1. В `load_positions_from_db()` (строки 387, 395-396)

**Что логируется:**
- Каждая загруженная позиция: `✅ Loaded: {symbol} on {exchange} (id={id})`
- Полный список всех загруженных символов после завершения

**Пример вывода:**
```
   ✅ Loaded: FORTHUSDT on binance (id=854)
   ✅ Loaded: LDOUSDT on binance (id=855)
   ✅ Loaded: B3USDT on binance (id=874)
   ...
📊 Loaded 81 positions from database
   Loaded symbols: ['1000CHEEMSUSDT', '1000SATSUSDT', ..., 'B3USDT', ...]
💰 Total exposure: $17467.83
```

**Зачем:** Увидим был ли B3USDT загружен при старте

---

#### 2. В `has_open_position()` (строки 1388-1389, 1399, 1402, 1406-1407)

**Что логируется:**
- Вызов метода с параметрами
- Размер кэша
- Результат проверки кэша
- Вызов _position_exists()
- Результат _position_exists()

**Пример вывода:**
```
🔍 has_open_position(symbol='B3USDT', exchange='binance')
   Cache size: 81 positions
   ❌ Not in cache, checking DB/exchange via _position_exists()...
   _position_exists() returned: True
```

**Или если в кэше:**
```
🔍 has_open_position(symbol='B3USDT', exchange='binance')
   Cache size: 81 positions
   ✅ Found in cache: B3USDT on binance
```

**Зачем:** Увидим почему вернул FALSE в 04:36:03

---

#### 3. В `_position_exists()` (строки 1349, 1352, 1356-1358, 1361, 1364-1366, 1369, 1380, 1382, 1384, 1386)

**Что логируется:**
- Вызов метода с параметрами
- Step 1/3: Проверка кэша + результат
- Step 2/3: Проверка БД + результат (включая position_id если найдено)
- Step 3/3: Проверка биржи API + результат
- Финальный результат

**Пример вывода (нашли в БД):**
```
🔍 _position_exists(symbol='B3USDT', exchange='binance')
   Step 1/3: Checking cache...
   ❌ Not in cache
   Step 2/3: Checking database...
   ✅ Found in DB: position_id=874
```

**Пример вывода (не нашли нигде):**
```
🔍 _position_exists(symbol='B3USDT', exchange='binance')
   Step 1/3: Checking cache...
   ❌ Not in cache
   Step 2/3: Checking database...
   ❌ Not in DB
   Step 3/3: Checking exchange API...
   ❌ Not on exchange
   Final result: FALSE (not found anywhere)
```

**Зачем:** Увидим почему вернул TRUE в 04:36:09 но FALSE в 04:36:03

---

## ✅ ПРОВЕРКИ

### 1. Backup создан
```bash
✅ core/position_manager.py.backup.20251018_070420_before_debug exists
```

### 2. Синтаксис Python
```bash
$ python3 -m py_compile core/position_manager.py
✅ Syntax OK
```

### 3. Только логи, без изменения логики
```bash
✅ Добавлены только logger.debug() вызовы
✅ НЕ изменена логика проверок
✅ НЕ изменены условия if/else
✅ НЕ изменены return значения
✅ НЕ добавлены новые переменные
✅ НЕ изменена структура кода
```

---

## 🎯 ЧТО ДАСТ ЭТО ЛОГИРОВАНИЕ

### При следующем старте бота увидим:

1. **Загрузился ли B3USDT в кэш?**
   ```
   ✅ Loaded: B3USDT on binance (id=874)
   ```
   Или его нет в списке?

2. **Полный список загруженных позиций:**
   ```
   Loaded symbols: ['...', 'B3USDT', '...']
   ```

### При следующей волне увидим:

3. **Как wave_processor проверял дубликаты:**
   ```
   🔍 has_open_position(symbol='B3USDT', exchange='binance')
   Cache size: 81 positions
   ```
   - Был ли в кэше?
   - Вызывался ли _position_exists()?
   - Что вернул _position_exists()?

4. **Что проверял _position_exists():**
   ```
   Step 1/3: Checking cache... ❌
   Step 2/3: Checking database... ✅ position_id=874
   ```
   - Почему не нашёл в кэше?
   - Нашёл ли в БД?
   - С каким position_id?

5. **Почему position_manager нашёл дубликат:**
   ```
   🔍 _position_exists(symbol='B3USDT', exchange='binance')
   Step 2/3: Checking database...
   ✅ Found in DB: position_id=874
   ```

### Сравнение результатов:

Если увидим:
```
04:36:03 - has_open_position() → _position_exists() → Step 2/3: ❌ Not in DB
04:36:09 - _position_exists() → Step 2/3: ✅ Found in DB: position_id=874
```

Тогда **БД query дала сбой в 04:36:03!**

Если увидим:
```
04:36:03 - has_open_position() → Cache size: 0 positions
04:36:09 - _position_exists() → Step 1/3: ❌ Not in cache
```

Тогда **кэш был пустой!**

---

## 🚀 СЛЕДУЮЩИЕ ШАГИ

### 1. Перезапустить бота

**ВНИМАНИЕ:** DEBUG логи будут выводиться **ТОЛЬКО** если уровень логирования установлен в DEBUG!

Проверить настройки логирования в конфиге:
```python
# Должно быть:
logging.basicConfig(level=logging.DEBUG)

# Или:
logger.setLevel(logging.DEBUG)
```

### 2. Дождаться событий

- Старт бота → проверить загрузку позиций
- Следующая волна → проверить проверку дубликатов
- Любой сигнал для существующей позиции

### 3. Проанализировать логи

Искать паттерны:
```bash
# Загрузка позиций
grep "Loaded:" monitoring_logs/bot_*.log
grep "Loaded symbols:" monitoring_logs/bot_*.log

# Проверки дубликатов
grep "🔍 has_open_position" monitoring_logs/bot_*.log
grep "🔍 _position_exists" monitoring_logs/bot_*.log

# Детали проверок
grep "Step 1/3" monitoring_logs/bot_*.log
grep "Step 2/3" monitoring_logs/bot_*.log
grep "Step 3/3" monitoring_logs/bot_*.log
```

### 4. Найти root cause

С этими логами мы на 100% поймём:
- Загружаются ли позиции в кэш
- Почему has_open_position() может вернуть FALSE
- Почему _position_exists() может вернуть TRUE
- В чём разница между двумя вызовами

---

## 📊 СТАТИСТИКА ИЗМЕНЕНИЙ

**Файлов изменено:** 1 (core/position_manager.py)
**Строк добавлено:** ~25 debug логов
**Строк изменено логики:** 0
**Методов затронуто:** 3
- load_positions_from_db()
- has_open_position()
- _position_exists()

---

## 🔄 ROLLBACK

Если DEBUG логи слишком verbose или вызывают проблемы:

```bash
# Восстановить версию БЕЗ debug логов
cp core/position_manager.py.backup.20251018_070420_before_debug core/position_manager.py

# Или восстановить версию С исправлением но БЕЗ debug
cp core/position_manager.py.backup.20251018_051812 core/position_manager.py
```

---

## ✅ GOLDEN RULE СОБЛЮДЁН

- ✅ НЕ рефакторил код
- ✅ НЕ улучшал структуру
- ✅ НЕ менял логику
- ✅ НЕ оптимизировал
- ✅ ТОЛЬКО добавил DEBUG логи

**Хирургическая точность:** Добавлено 25 строк логирования, 0 строк изменения логики.

---

**Применил:** Claude Code
**Дата:** 2025-10-18 07:05
**Цель:** Диагностика inconsistency
**Статус:** ✅ ГОТОВО К ТЕСТИРОВАНИЮ

---
