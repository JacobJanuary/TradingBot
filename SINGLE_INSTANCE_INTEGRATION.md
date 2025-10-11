# 🔒 Интеграция Single Instance Protection

## Установка зависимостей

```bash
pip install filelock>=3.12.0 psutil>=5.9.0
```

## Быстрый старт

### Вариант 1: Простое использование

```python
from utils.single_instance import SingleInstance

# В начале main.py
app_lock = SingleInstance('trading_bot')

# Остальной код приложения
...
```

### Вариант 2: С контекстным менеджером

```python
from utils.single_instance import SingleInstance

def main():
    with SingleInstance('trading_bot'):
        # Код приложения
        run_bot()

if __name__ == '__main__':
    main()
```

### Вариант 3: С декоратором

```python
from utils.single_instance import single_instance

@single_instance('trading_bot')
def main():
    # Код приложения
    run_bot()

if __name__ == '__main__':
    main()
```

## Интеграция в main.py

### Текущий код (УДАЛИТЬ):

```python
# СТАРЫЙ КОД - УДАЛИТЬ
from utils.process_lock import ProcessLock

process_lock = ProcessLock('bot.pid')  # ❌ НЕ РАБОТАЕТ!
if not process_lock.acquire():
    sys.exit(1)
```

### Новый код (ИСПОЛЬЗОВАТЬ):

```python
# НОВЫЙ КОД - НАДЁЖНЫЙ
from utils.single_instance import SingleInstance

# Опция 1: С автоматическим exit при второй попытке
app_lock = SingleInstance('trading_bot')

# Опция 2: С ручной обработкой
try:
    app_lock = SingleInstance('trading_bot', auto_exit=False)
except SingleInstanceError as e:
    logger.error(f"Cannot start: {e}")
    sys.exit(1)
```

## CLI опции

### Проверка запущен ли бот:

```bash
python -m utils.single_instance trading_bot --check
# Output: Application 'trading_bot': RUNNING
# Exit code: 0 (running) or 1 (not running)
```

### Завершение запущенного бота:

```bash
# Graceful shutdown (SIGTERM)
python -m utils.single_instance trading_bot --kill

# Force kill (SIGKILL)
python -m utils.single_instance trading_bot --kill --force
```

### Программное использование:

```python
from utils.single_instance import check_running, kill_running

# Проверка
if check_running('trading_bot'):
    print("Bot is running")

# Завершение
if kill_running('trading_bot'):
    print("Bot terminated")
```

## Добавление CLI в main.py

```python
import argparse
from utils.single_instance import check_running, kill_running

parser = argparse.ArgumentParser()
parser.add_argument('--check-instance', action='store_true',
                   help='Check if bot is already running')
parser.add_argument('--kill-instance', action='store_true',
                   help='Kill running instance')
parser.add_argument('--force-kill', action='store_true',
                   help='Force kill (use with --kill-instance)')

args = parser.parse_args()

if args.check_instance:
    running = check_running('trading_bot')
    print(f"Trading bot: {'RUNNING' if running else 'NOT RUNNING'}")
    sys.exit(0 if running else 1)

if args.kill_instance:
    if kill_running('trading_bot', force=args.force_kill):
        print("Bot terminated successfully")
        sys.exit(0)
    else:
        print("Failed to terminate bot")
        sys.exit(1)

# Основной код
app_lock = SingleInstance('trading_bot')
# ...
```

## Расположение lock файлов

По умолчанию файлы создаются в системной temp директории:

- **Mac OS**: `/var/folders/.../T/`
- **Linux**: `/tmp/`
- **Windows**: `C:\Users\...\AppData\Local\Temp\`

Файлы:
- `trading_bot.lock` - основной lock файл
- `trading_bot.pid` - PID процесса
- `trading_bot.info` - детальная информация

### Пользовательская директория:

```python
app_lock = SingleInstance(
    'trading_bot',
    lock_dir='/custom/path/to/locks'
)
```

## Graceful Shutdown

Блокировка автоматически освобождается при:
- Нормальном завершении программы
- Ctrl+C (SIGINT)
- `kill <PID>` (SIGTERM)
- Исключении в коде
- Вызове `sys.exit()`

```python
import signal
import atexit

# Блокировка автоматически регистрирует обработчики:
# - atexit.register(app_lock.release)
# - signal.signal(SIGTERM, handler)
# - signal.signal(SIGINT, handler)
```

## Информация о запущенном экземпляре

При попытке второго запуска:

```
[ERROR] ❌ Another instance is already running
[ERROR] 📍 Running instance PID: 12345
[ERROR] Instance details:
[ERROR]   pid=12345
[ERROR]   started=2024-01-15T10:30:45.123456
[ERROR]   executable=/usr/bin/python3
[ERROR]   argv=python main.py --exchange binance
[ERROR]   cwd=/home/user/TradingBot
[ERROR]   user=evgeniy
[ERROR]   Process status: running
[ERROR]   CPU: 2.5%
[ERROR]   Memory: 145.3 MB
[ERROR] 💡 To force start: rm /tmp/trading_bot.lock
```

## Тестирование

```bash
# Запуск всех тестов
pytest tests/test_single_instance.py -v

# Запуск конкретного теста
pytest tests/test_single_instance.py::TestSingleInstance::test_basic_lock -v

# С покрытием
pytest tests/test_single_instance.py --cov=utils.single_instance --cov-report=html
```

## Миграция с ProcessLock

### До (старый код):

```python
from utils.process_lock import ProcessLock

process_lock = ProcessLock('bot.pid')
if not process_lock.acquire():
    logger.error("❌ Cannot start: another instance is already running")
    sys.exit(1)

# В конце
process_lock.release()
```

### После (новый код):

```python
from utils.single_instance import SingleInstance

# Вариант 1: Автоматический
app_lock = SingleInstance('trading_bot')

# Вариант 2: С контекстным менеджером (рекомендуется)
with SingleInstance('trading_bot'):
    run_application()

# release() вызывается автоматически!
```

## Преимущества новой системы

✅ **100% кроссплатформенность** (Mac, Linux, Windows)
✅ **Атомарность операций** через filelock
✅ **Автоматическая очистка** устаревших блокировок
✅ **Проверка валидности** PID через psutil
✅ **Graceful shutdown** (SIGTERM, SIGINT)
✅ **Детальное логирование**
✅ **CLI утилиты** (--check, --kill)
✅ **Контекстный менеджер** и **декоратор**
✅ **Production-ready** с обработкой всех edge cases

## Устранение багов

### Проблема в старой системе:

```python
# ❌ БАГОВЫЙ КОД
ProcessLock('bot.pid')  # Относительный путь!
```

**Результат:** Каждый экземпляр создавал СВОЙ файл `bot.pid`, fcntl.flock работал на РАЗНЫХ файлах → **два бота работали одновременно** → дубликаты позиций!

### Решение в новой системе:

```python
# ✅ ПРАВИЛЬНЫЙ КОД
SingleInstance('trading_bot')  # Абсолютный путь в /tmp/
```

**Результат:** Все экземпляры используют ОДИН файл `/tmp/trading_bot.lock` → filelock гарантирует атомарность → только один бот работает.

## Дополнительные возможности

### Таймаут ожидания:

```python
# Подождать до 5 секунд для получения блокировки
try:
    app_lock = SingleInstance('trading_bot', timeout=5, auto_exit=False)
except SingleInstanceError:
    print("Timeout acquiring lock")
```

### Отключение автоматической очистки:

```python
app_lock = SingleInstance('trading_bot', cleanup_on_exit=False)
# Нужно вызвать release() вручную
app_lock.release()
```

### Проверка без блокировки:

```python
from utils.single_instance import check_running

if check_running('trading_bot'):
    print("Already running, exiting")
    sys.exit(0)

# Продолжаем запуск
app_lock = SingleInstance('trading_bot')
```
