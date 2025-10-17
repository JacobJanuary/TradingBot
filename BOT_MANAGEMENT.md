# 🤖 Bot Management Guide

Удобные скрипты для управления ботом.

## 📋 Быстрый старт

### Запуск бота

```bash
./start_bot.sh
```

**Что делает:**
- ✅ Проверяет, не запущен ли уже бот
- ✅ Автоматически останавливает старые инстансы (с подтверждением)
- ✅ Очищает lock файлы
- ✅ Запускает бот в фоновом режиме
- ✅ Создаёт лог файл с timestamp'ом
- ✅ Проверяет успешность запуска

**Вывод:**
```
🤖 Starting Trading Bot...
🚀 Starting bot...
✅ Bot started successfully!
   PID: 72189
   Log: logs/production_bot_20251017_201040.log

Commands:
  - Check status: ps -p 72189
  - View logs: tail -f logs/production_bot_20251017_201040.log
  - Stop bot: kill 72189
```

### Остановка бота

```bash
./stop_bot.sh
```

**Что делает:**
- ✅ Находит все процессы бота
- ✅ Пытается graceful shutdown (SIGTERM)
- ✅ Ждёт до 10 секунд
- ✅ Force kill если не остановился (SIGKILL)
- ✅ Очищает lock файлы

**Вывод:**
```
🛑 Stopping Trading Bot...
Found bot processes: 72189
Sending SIGTERM to PID 72189...
Waiting for graceful shutdown (max 10 seconds)...
✅ All bots stopped gracefully
✅ All bot processes stopped
🧹 Removing lock file...
✅ Bot stopped successfully
```

## 🔧 Ручное управление

### Проверка статуса

```bash
# Найти все процессы бота
ps aux | grep "python.*main.py.*production" | grep -v grep

# Проверить конкретный PID
ps -p <PID> -o pid,etime,command

# Проверить lock file
ls -la /var/folders/pb/fz5jyb914bl60s5lpb_yhnc40000gn/T/trading_bot.lock
```

### Просмотр логов

```bash
# Последние логи (real-time)
tail -f logs/production_bot_*.log

# Последние 100 строк
tail -100 logs/production_bot_20251017_201040.log

# Поиск ошибок
grep -i error logs/production_bot_*.log
grep -i "aged" logs/production_bot_*.log
```

### Ручной запуск

```bash
# Простой запуск
python main.py --mode production

# В фоне с логом
python main.py --mode production > logs/production_bot_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $!  # Запомнить PID
```

### Ручная остановка

```bash
# Graceful shutdown
kill <PID>

# Force kill (если не реагирует)
kill -9 <PID>

# Очистить lock file
rm -f /var/folders/pb/fz5jyb914bl60s5lpb_yhnc40000gn/T/trading_bot.lock
```

## 🚨 Решение проблем

### Проблема: "Bot already running"

```bash
# Вариант 1: Использовать скрипт (он спросит про restart)
./start_bot.sh

# Вариант 2: Остановить вручную
./stop_bot.sh
./start_bot.sh
```

### Проблема: "Lock timeout"

```bash
# Проверить, есть ли реально запущенный бот
ps aux | grep "python.*main.py" | grep -v grep

# Если бота нет - удалить lock
rm -f /var/folders/pb/fz5jyb914bl60s5lpb_yhnc40000gn/T/trading_bot.lock

# Запустить
./start_bot.sh
```

### Проблема: Зомби-процесс

```bash
# Найти все процессы бота
ps aux | grep "python.*main.py"

# Убить все найденные
pkill -9 -f "python.*main.py.*production"

# Очистить lock
rm -f /var/folders/pb/fz5jyb914bl60s5lpb_yhnc40000gn/T/trading_bot.lock

# Запустить заново
./start_bot.sh
```

## 📊 Мониторинг

### Проверка активности Aged Position Manager

```bash
# Найти упоминания aged в логах
grep -i "aged" logs/production_bot_*.log | tail -20

# Проверить количество обработанных позиций
grep "Aged positions processed" logs/production_bot_*.log | tail -5
```

### Проверка ошибок

```bash
# NoneType errors (должно быть 0)
grep -i "nonetype" logs/production_bot_*.log

# Error -4016 (должно быть 0)
grep -i "error.*-4016" logs/production_bot_*.log

# Все критические ошибки
grep -i "critical\|error" logs/production_bot_*.log | tail -30
```

### Проверка позиций

```bash
# Последняя синхронизация позиций
grep "SYNCHRONIZATION SUMMARY" logs/production_bot_*.log | tail -10

# WebSocket соединения
grep "Connected to.*stream" logs/production_bot_*.log | tail -5
```

## 🔄 Рекомендации

1. **Всегда используйте скрипты** вместо ручных команд
2. **Проверяйте логи** после запуска (первые 5 минут)
3. **Мониторьте ошибки** регулярно
4. **Не запускайте несколько ботов** одновременно
5. **Делайте git pull** перед запуском новой версии

## 📝 История изменений

### 2025-10-17
- ✅ Создан `start_bot.sh` - безопасный запуск
- ✅ Создан `stop_bot.sh` - graceful shutdown
- ✅ Добавлен None check для Bybit символов
- ✅ Исправлено: 0 ошибок NoneType
- ✅ Исправлено: 0 ошибок -4016
