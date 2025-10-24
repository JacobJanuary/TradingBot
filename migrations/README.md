# UTC Timezone Migration

## Описание

Комплексная миграция для перевода всей системы на UTC timezone и исправления проблем со схемами таблиц.

### Проблемы, которые решает миграция:

1. **Timezone Bug**: База данных использует `Europe/Moscow` (UTC+3), что вызывает 3-часовую погрешность в расчете возраста позиций
2. **Schema Inconsistency**: Таблицы `aged_positions` и `aged_monitoring_events` находятся в схеме `public` вместо `monitoring`
3. **Timestamp Types**: 11 таблиц (21 колонка) используют `timestamp without time zone` вместо `timestamptz`
4. **Code Issues**: 232 использования `datetime.now()` вместо `datetime.now(timezone.utc)`

## Структура миграции

```
migrations/
├── README.md                                    # Этот файл
├── pre_migration_check.sql                      # Проверка текущего состояния
├── migration_001_move_aged_tables_to_monitoring.sql  # Перенос aged таблиц
├── migration_002_convert_timestamps_to_utc.sql  # Конвертация timestamp → timestamptz
└── migration_003_verify.sql                     # Верификация миграции
```

## Пошаговая инструкция

### Подготовка (ЭТАП 0)

✅ **1. Git commit текущего состояния**
```bash
git add -A
git commit -m "Pre-migration: Current state before UTC timezone and schema migration"
```

✅ **2. Создание backup'ов базы данных**
```bash
# Binary backup (быстрое восстановление)
pg_dump -h localhost -U fox_user -d fox_crypto \
  --format=custom \
  -f backups/pre_utc_migration_$(date +%Y%m%d_%H%M%S).dump

# SQL backup (читаемый формат)
pg_dump -h localhost -U fox_user -d fox_crypto \
  > backups/pre_utc_migration_$(date +%Y%m%d_%H%M%S).sql
```

✅ **3. Проверка текущего состояния**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U fox_user -d fox_crypto \
  -f migrations/pre_migration_check.sql
```

Ожидаемые результаты:
- Database timezone: `Europe/Moscow`
- Aged tables: в схеме `public` (неправильно)
- Timestamp columns: 21 колонка типа `timestamp without time zone`

### ЭТАП 1: Database Migration

⚠️ **ВАЖНО: Останавливаем бот перед миграцией!**

```bash
# Останавливаем бот (если запущен)
pkill -f main.py

# Или если используется systemd/supervisor
# systemctl stop trading-bot
```

**1. Перенос aged таблиц из public в monitoring**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U fox_user -d fox_crypto \
  -f migrations/migration_001_move_aged_tables_to_monitoring.sql
```

**2. Конвертация timestamp → timestamptz + изменение DEFAULT**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U fox_user -d fox_crypto \
  -f migrations/migration_002_convert_timestamps_to_utc.sql
```

**3. Изменение timezone базы данных на UTC**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U fox_user -d fox_crypto \
  -c "ALTER DATABASE fox_crypto SET timezone TO 'UTC';"
```

**4. Переподключение к БД для применения изменений**
```bash
# Завершаем все активные соединения
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U fox_user -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'fox_crypto' AND pid != pg_backend_pid();"
```

**5. Верификация миграции**
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U fox_user -d fox_crypto \
  -f migrations/migration_003_verify.sql
```

Ожидаемый результат:
```
✅ ALL MIGRATIONS COMPLETED SUCCESSFULLY!
✓ Database timezone: UTC
✓ All aged tables in monitoring schema
✓ All timestamp columns are timestamptz
✓ monitoring.aged_positions: N records
✓ monitoring.aged_monitoring_events: N records
```

**6. Git commit после database migration**
```bash
git add -A
git commit -m "ЭТАП 1: Database migration to UTC completed - schema and timezone changes"
```

### ЭТАП 2: Code Refactor - Database Layer

**1. Обновление database/models.py**

Изменения:
```python
# БЫЛО:
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
created_at = Column(DateTime, default=func.now(), nullable=False)

# СТАЛО:
from sqlalchemy import Column, Integer, String, Float, Boolean, TIMESTAMP
created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
```

Файлы для изменения:
- `database/models.py`: 9 таблиц, множество колонок

**2. Обновление database/repository.py**

Изменения:
- Добавить `from utils.datetime_helpers import now_utc, ensure_utc`
- Исправить schema prefixes: `INSERT INTO aged_positions` → `INSERT INTO monitoring.aged_positions`
- Заменить `datetime.now()` → `now_utc()` (3 места)

**3. Git commit**
```bash
git add database/
git commit -m "ЭТАП 2: Updated database layer - models and repository for UTC"
```

### ЭТАП 3: Code Refactor - Core Layer

**1. Исправление core/aged_position_monitor_v2.py**

Критическое изменение в методе `_calculate_age_hours()`:
```python
# УДАЛИТЬ workaround (больше не нужен после миграции на timestamptz):
# if not hasattr(opened_at, 'tzinfo') or opened_at.tzinfo is None:
#     opened_at = opened_at.replace(tzinfo=timezone.utc)  # ← УДАЛИТЬ ЭТО!

# Теперь opened_at всегда будет timezone-aware из БД
```

**2. Обновление core/position_manager.py**

Заменить `datetime.now()` → `now_utc()` (22 места):
- Line 1978: `position.ts_last_update_time = now_utc()`
- Line 2806: `(now_utc() - ts_last_update).total_seconds()`
- И т.д.

**3. Обновление core/exchange_manager.py**

Аналогичные замены для таймингов.

**4. Git commit**
```bash
git add core/
git commit -m "ЭТАП 3: Updated core layer - fixed timezone handling in all managers"
```

### ЭТАП 4: Fix Diagnostic Files

Обновление диагностических скриптов:

**Файлы для изменения:**
- `forensic_aged_diagnosis.py`: `public.aged_positions` → `monitoring.aged_positions`
- `simple_aged_diagnosis.py`: аналогично
- `tests/test_aged_*.py`: обновление schema prefixes

**Git commit**
```bash
git add forensic_*.py simple_*.py tests/
git commit -m "ЭТАП 4: Updated diagnostic scripts and tests for monitoring schema"
```

### ЭТАП 5: Testing and Launch

**1. Запуск верификационных тестов**
```bash
# Тесты будут созданы во время реализации
python -m pytest tests/test_utc_migration.py -v
```

**2. Запуск бота**
```bash
python main.py
```

**3. Мониторинг в течение 30 минут**

Проверяем:
- Позиции старше 3 часов должны детектироваться aged модулем
- Логи не содержат timezone-related ошибок
- Trailing stop активируется корректно

**4. Проверка конкретных проблемных позиций**

Если FLMUSDT, THETAUSDT, POLYXUSDT и другие позиции все еще открыты (маловероятно, т.к. прошло время), они должны быть:
- Детектированы как aged (age > 3 hours)
- Попытки закрытия залогированы
- Закрыты по aged механизму

**5. Final git commit**
```bash
git add -A
git commit -m "ЭТАП 5: UTC migration completed and verified - system operational"
```

## Rollback Plan (на случай проблем)

Если что-то пошло не так:

**1. Остановить бот**
```bash
pkill -f main.py
```

**2. Восстановить базу данных из backup**
```bash
# Если база сильно повреждена, создать новую и восстановить
dropdb -h localhost -U fox_user fox_crypto
createdb -h localhost -U fox_user fox_crypto

# Восстановить из binary backup (быстрее)
pg_restore -h localhost -U fox_user -d fox_crypto \
  backups/pre_utc_migration_YYYYMMDD_HHMMSS.dump

# Или из SQL backup
psql -h localhost -U fox_user -d fox_crypto \
  < backups/pre_utc_migration_YYYYMMDD_HHMMSS.sql
```

**3. Откатить код**
```bash
git reset --hard <commit-before-migration>
```

**4. Перезапустить бот**
```bash
python main.py
```

## Verification Checklist

После завершения миграции проверьте:

- [ ] Database timezone = UTC (`SHOW timezone;`)
- [ ] Все aged таблицы в схеме `monitoring`
- [ ] Все timestamp колонки имеют тип `timestamptz`
- [ ] Бот запускается без ошибок
- [ ] Aged positions детектируются корректно
- [ ] Trailing stop работает
- [ ] Новые позиции создаются с UTC timestamps
- [ ] Логи не содержат timezone warnings

## Timeline

- **ЭТАП 0 (Подготовка)**: ~10 минут
- **ЭТАП 1 (Database)**: ~5 минут (downtime)
- **ЭТАП 2 (Code - DB)**: ~20 минут
- **ЭТАП 3 (Code - Core)**: ~30 минут
- **ЭТАП 4 (Diagnostics)**: ~10 минут
- **ЭТАП 5 (Testing)**: ~30 минут

**Общее время**: ~2 часа (включая тестирование)
**Downtime бота**: ~5-10 минут (только ЭТАП 1)

## Support

При возникновении проблем:
1. Проверьте логи бота
2. Запустите `migration_003_verify.sql`
3. Проверьте git log для отката
4. В крайнем случае - используйте rollback plan
