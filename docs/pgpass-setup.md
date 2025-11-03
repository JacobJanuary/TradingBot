# PostgreSQL Password File (.pgpass)

## Описание

Проект использует стандартный PostgreSQL механизм хранения паролей через файл `~/.pgpass` для безопасности. Пароли **не хранятся** в `.env` файле.

## Настройка

### 1. Создайте файл .pgpass

```bash
nano ~/.pgpass
```

### 2. Добавьте строку подключения

Формат: `hostname:port:database:username:password`

Пример:
```
localhost:5432:tradingbot_db:tradingbot:AKaipZAktswUeWIlVAXnaf5hvKtkChbX
```

### 3. Установите правильные права доступа

**ОБЯЗАТЕЛЬНО!** PostgreSQL требует права `0600` (только владелец может читать/писать):

```bash
chmod 600 ~/.pgpass
```

### 4. Проверьте права

```bash
ls -la ~/.pgpass
```

Должно быть: `-rw------- 1 username username ...`

## Использование wildcards

Можно использовать `*` для любого поля кроме пароля:

```
# Любая база данных на localhost для пользователя tradingbot
localhost:5432:*:tradingbot:password123

# Любой хост для конкретной базы
*:5432:tradingbot_db:tradingbot:password123
```

## Приоритет паролей

1. Переменная окружения `DB_PASSWORD` в `.env` (если установлена)
2. Файл `~/.pgpass` (если `DB_PASSWORD` пустой)
3. Пустой пароль (если ничего не найдено)

## Проверка подключения

### С помощью psql
```bash
psql -h localhost -p 5432 -U tradingbot -d tradingbot_db
```

### С помощью скрипта проекта
```bash
python scripts/complete_cleanup.py --dry-run
```

Если видите `✅ Connected to database` - все настроено правильно!

## Безопасность

- ✅ `.pgpass` хранится **локально** и не попадает в git
- ✅ Права доступа `0600` защищают от чтения другими пользователями
- ✅ Стандартный механизм PostgreSQL, используется всеми официальными клиентами
- ❌ **НИКОГДА** не коммитьте `.pgpass` в git
- ❌ **НЕ ДОБАВЛЯЙТЕ** пароли в `.env` файл проекта

## Утилиты проекта

Модуль `utils/pgpass.py` предоставляет:

- `read_pgpass(host, port, database, user)` - читает пароль из .pgpass
- `get_db_password()` - получает пароль из env или .pgpass
- `build_db_url()` - строит полный connection URL

## Пример использования в коде

```python
from utils.pgpass import get_db_password, build_db_url

# Вариант 1: Получить только пароль
password = get_db_password()
conn = await asyncpg.connect(
    host='localhost',
    port=5432,
    database='tradingbot_db',
    user='tradingbot',
    password=password
)

# Вариант 2: Получить полный URL
db_url = build_db_url()
conn = await asyncpg.connect(db_url)
```

## Troubleshooting

### Ошибка: password authentication failed

Проверьте:
1. Правильность пароля в `.pgpass`
2. Права доступа к файлу (`chmod 600 ~/.pgpass`)
3. Формат строки (5 полей через `:`)
4. Совпадение host, port, database, user

### Файл .pgpass игнорируется

- PostgreSQL игнорирует `.pgpass` если права не `0600`
- Проверьте: `ls -la ~/.pgpass` должно показывать `-rw-------`

### Пароль не читается

- Убедитесь что `DB_PASSWORD` в `.env` пустой или закомментирован
- Проверьте что файл `.pgpass` существует: `cat ~/.pgpass`
