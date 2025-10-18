# ✅ DEBUG ЛОГИ ВКЛЮЧЕНЫ

**Дата:** 2025-10-18 15:00
**Статус:** ✅ ГОТОВО К ТЕСТИРОВАНИЮ

---

## 📝 ИЗМЕНЕНИЯ

### 1. Исправлен main.py (строка 30)

**Было (захардкожено):**
```python
level=logging.INFO,
```

**Стало (читает из .env):**
```python
level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
```

**Backup:**
```
main.py.backup.20251018_150055_before_loglevel_fix
```

### 2. Изменен .env (строка 70)

**Было:**
```
LOG_LEVEL=INFO
```

**Стало:**
```
LOG_LEVEL=DEBUG
```

---

## ✅ ПРОВЕРКИ

### 1. Backup создан
```bash
✅ main.py.backup.20251018_150055_before_loglevel_fix exists
```

### 2. Синтаксис Python
```bash
$ python3 -c "import main"
✅ No errors
```

### 3. Изменения минимальные
```bash
✅ main.py: изменена 1 строка (30)
✅ .env: изменена 1 строка (70)
✅ Логика НЕ изменена
✅ Golden Rule соблюдён
```

---

## 🎯 ЧТО ТЕПЕРЬ БУДЕТ

### При следующем запуске бота:

**1. Startup (загрузка позиций):**
```
DEBUG - 📊 Loaded 82 positions from database
DEBUG -    ✅ Loaded: FORTHUSDT on binance (id=854)
DEBUG -    ✅ Loaded: LDOUSDT on binance (id=855)
DEBUG -    ✅ Loaded: ALGOUSDT on binance (id=XXX)
DEBUG -    ...
DEBUG -    Loaded symbols: ['1000CHEEMSUSDT', ..., 'ALGOUSDT', ...]
```

**Теперь увидим:**
- Полный список всех загруженных позиций
- ID каждой позиции
- Был ли ALGOUSDT (и другие проблемные символы) загружен

---

**2. Wave Processing (проверка дубликатов):**
```
DEBUG - 🔍 has_open_position(symbol='ALGOUSDT', exchange='binance')
DEBUG -    Cache size: 82 positions
DEBUG -    ❌ Not in cache, checking DB/exchange via _position_exists()...
DEBUG - 🔍 _position_exists(symbol='ALGOUSDT', exchange='binance')
DEBUG -    Step 1/3: Checking cache...
DEBUG -    ❌ Not in cache
DEBUG -    Step 2/3: Checking database...
DEBUG -    ❌ Not in DB
DEBUG -    Step 3/3: Checking exchange API...
DEBUG -    ❌ Not on exchange
DEBUG -    Final result: FALSE (not found anywhere)
DEBUG -    _position_exists() returned: FALSE
```

**Теперь увидим:**
- Был ли символ в кэше
- Вызывался ли _position_exists()
- Проверялась ли БД
- Что вернула каждая проверка

---

**3. Position Manager (блокировка дубликата):**
```
WARNING - Position already exists for ALGOUSDT on binance
DEBUG - 🔍 _position_exists(symbol='ALGOUSDT', exchange='binance')
DEBUG -    Step 1/3: Checking cache...
DEBUG -    ❌ Not in cache
DEBUG -    Step 2/3: Checking database...
DEBUG -    ✅ Found in DB: position_id=874
```

**Теперь увидим:**
- Почему нашёл в БД (position_id)
- Почему НЕ нашёл в кэше
- Разницу между двумя вызовами

---

## 🔍 АНАЛИЗ КОТОРЫЙ СТАНЕТ ВОЗМОЖНЫМ

### Сценарий A: Позиция НЕ загружена при старте

**Если увидим:**
```
DEBUG - Loaded symbols: [...] (нет ALGOUSDT)
```

**Тогда проблема:** Позиция не загрузилась → нужно искать почему
- verify_position_exists() failed?
- PHANTOM detection?
- Symbol normalization issue?

---

### Сценарий B: Позиция загружена но удалилась из кэша

**Если увидим:**
```
DEBUG - Loaded symbols: [..., 'ALGOUSDT', ...]  (есть при старте)
DEBUG - has_open_position() → Cache size: 82   (есть в кэше)
DEBUG - Not in cache                            (но не нашли!)
```

**Тогда проблема:** Баг в проверке кэша → логическая ошибка

---

### Сценарий C: БД query даёт временный сбой

**Если увидим:**
```
07:22:04 - _position_exists() → Step 2/3: ❌ Not in DB
07:22:11 - _position_exists() → Step 2/3: ✅ Found in DB: position_id=874
```

**Тогда проблема:** БД connection/timeout/transaction isolation

---

### Сценарий D: _position_exists() НЕ вызывался

**Если увидим:**
```
DEBUG - has_open_position()
DEBUG -    Cache size: 82 positions
(НЕТ строки "_position_exists() returned:")
```

**Тогда проблема:** Баг в has_open_position() - не вызывает _position_exists()

---

## 🚀 СЛЕДУЮЩИЕ ШАГИ

### 1. Перезапустить бота
```bash
# Остановить текущий бот (Ctrl+C)
# Запустить снова
python main.py 2>&1 | tee monitoring_logs/bot_$(date +%Y%m%d_%H%M%S).log
```

### 2. Проверить DEBUG логи работают
```bash
# Сразу после старта проверить
tail -f monitoring_logs/bot_*.log | grep "DEBUG"

# Должны увидеть:
# DEBUG - ✅ Loaded: FORTHUSDT on binance (id=854)
# DEBUG - ✅ Loaded: LDOUSDT on binance (id=855)
# ...
```

### 3. Дождаться следующей волны
- Особенно волны с дубликатами
- Или создать искусственный дубликат (послать сигнал для существующей позиции)

### 4. Проанализировать DEBUG логи
```bash
# Найти все вызовы has_open_position
grep "🔍 has_open_position" monitoring_logs/bot_*.log

# Найти все вызовы _position_exists
grep "🔍 _position_exists" monitoring_logs/bot_*.log

# Найти все проверки БД
grep "Step 2/3:" monitoring_logs/bot_*.log
```

---

## ⚠️ ВАЖНО: Размер логов

**DEBUG логи ОЧЕНЬ многословны!**

### Ожидаемый размер:
- INFO логи: ~100 MB за 8 часов
- **DEBUG логи: ~500-1000 MB за 8 часов** (в 5-10 раз больше!)

### Рекомендации:
1. **Не оставлять DEBUG надолго** - только для диагностики
2. После нахождения проблемы - вернуть LOG_LEVEL=INFO
3. Возможно логи заполнят диск - следить за местом

### Мониторинг места на диске:
```bash
df -h .
du -sh monitoring_logs/
```

---

## 🔄 ОТКАТ (если нужно)

### Вернуть INFO логи:

**Вариант 1: Просто изменить .env**
```bash
# В .env изменить:
LOG_LEVEL=INFO

# Перезапустить бота
```

**Вариант 2: Восстановить старый main.py**
```bash
cp main.py.backup.20251018_150055_before_loglevel_fix main.py

# В .env изменить:
LOG_LEVEL=INFO

# Перезапустить бота
```

---

## 📊 ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

### Если DEBUG логи покажут проблему:

**Сценарий A - Позиции не загружаются:**
→ Исправим verify_position_exists()

**Сценарий B - Баг в проверке кэша:**
→ Исправим has_open_position()

**Сценарий C - БД query fails:**
→ Добавим retry logic или увеличим timeout

**Сценарий D - _position_exists() не вызывается:**
→ Исправим логику в has_open_position()

### После исправления:
1. Вернём LOG_LEVEL=INFO
2. Удалим DEBUG логи из кода (если не нужны)
3. Протестируем 24 часа
4. Подтвердим что проблема решена

---

## ✅ СТАТУС

**main.py:** ✅ Исправлен (читает LOG_LEVEL из env)
**LOG_LEVEL:** ✅ Установлен в DEBUG
**Backup:** ✅ Создан
**Синтаксис:** ✅ Валиден
**Готово к запуску:** ✅ ДА

**Следующее действие:** Перезапустить бота и ждать DEBUG логов

---

**Применил:** Claude Code
**Дата:** 2025-10-18 15:00
**Цель:** Включить DEBUG логи для диагностики
**Приоритет:** 🔴 CRITICAL

---
