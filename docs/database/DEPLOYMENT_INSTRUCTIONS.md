# 📦 DATABASE DEPLOYMENT INSTRUCTIONS

## Развертывание базы данных на новом сервере

### Требования
- PostgreSQL 12+ (рекомендуется 14+)
- Права на создание схем и таблиц
- Минимум 1GB свободного места

---

## 🚀 Быстрое развертывание

### Вариант 1: Через psql (рекомендуется)

```bash
# 1. Создайте базу данных
createdb fox_crypto

# 2. Примените схему
psql -d fox_crypto -f database/DEPLOY_SCHEMA.sql

# 3. Проверьте результат
psql -d fox_crypto -c "\dt fas.*"
psql -d fox_crypto -c "\dt monitoring.*"
```

### Вариант 2: Через pgAdmin или другой GUI

1. Создайте новую базу данных `fox_crypto`
2. Откройте Query Tool
3. Загрузите и выполните `database/DEPLOY_SCHEMA.sql`
4. Проверьте результат в Object Browser

### Вариант 3: Через Python скрипт

```python
import psycopg2

# Подключение
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="fox_crypto",
    user="your_user",
    password="your_password"
)

# Выполнение скрипта
with open('database/DEPLOY_SCHEMA.sql', 'r') as f:
    sql = f.read()
    
with conn.cursor() as cur:
    cur.execute(sql)
    conn.commit()

print("✅ Database deployed successfully!")
conn.close()
```

---

## 📋 Что будет создано

### Схемы (1):
- `monitoring` - Позиции, ордера, события бота

### Таблицы (10):
1. **monitoring.positions** - Торговые позиции
2. **monitoring.orders** - Все ордера (market, limit, SL, TP)
3. **monitoring.trades** - Отдельные сделки (fills)
4. **monitoring.events** - Лог событий бота
5. **monitoring.trailing_stop_state** - Состояние trailing stop
6. **monitoring.performance_metrics** - Метрики производительности
7. **monitoring.event_performance_metrics** - Event-based метрики
8. **monitoring.risk_events** - События риск-менеджмента
9. **monitoring.risk_violations** - Нарушения риск-правил
10. **monitoring.transaction_log** - Лог транзакций БД

### Индексы (37):
- По символам, биржам, статусам
- По временным меткам (для быстрых запросов)
- По связанным ID (foreign keys)
- Композитные индексы для частых запросов
- Partial indexes для оптимизации

### Триггеры (2):
- Auto-update `updated_at` для positions
- Auto-update `updated_at` для trades

---

## ✅ Проверка развертывания

После выполнения скрипта проверьте:

```sql
-- 1. Проверка схем
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'monitoring';

-- 2. Проверка таблиц
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname = 'monitoring'
ORDER BY schemaname, tablename;

-- 3. Проверка индексов
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname = 'monitoring'
ORDER BY schemaname, tablename;

-- 4. Проверка триггеров
SELECT trigger_schema, trigger_name, event_object_table
FROM information_schema.triggers
WHERE trigger_schema = 'monitoring';

-- 5. Размер базы данных
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'monitoring'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

Ожидаемый результат:
- ✅ 1 схема (monitoring)
- ✅ 10 таблиц
- ✅ 37 индексов
- ✅ 2 триггера
- ✅ 1 foreign key

---

## 🔐 Настройка прав доступа (опционально)

Если используете отдельного пользователя для бота:

```sql
-- Создайте пользователя
CREATE USER trading_bot_user WITH PASSWORD 'secure_password';

-- Выдайте права
GRANT USAGE ON SCHEMA monitoring TO trading_bot_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA monitoring TO trading_bot_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA monitoring TO trading_bot_user;

-- Сделайте права постоянными для новых таблиц
ALTER DEFAULT PRIVILEGES IN SCHEMA monitoring
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO trading_bot_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA monitoring
    GRANT USAGE, SELECT ON SEQUENCES TO trading_bot_user;
```

---

## 🔧 Настройка PostgreSQL (рекомендации)

Для оптимальной производительности добавьте в `postgresql.conf`:

```conf
# Memory settings (adjust based on available RAM)
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB

# Write-ahead log
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# Query planner
random_page_cost = 1.1  # For SSD storage
effective_io_concurrency = 200

# Logging (for debugging)
log_min_duration_statement = 1000  # Log queries > 1s
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

Затем перезапустите PostgreSQL:
```bash
sudo systemctl restart postgresql
```

---

## 📊 Мониторинг производительности

### Проверка медленных запросов:

```sql
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
WHERE query LIKE '%monitoring.%'
ORDER BY mean_time DESC
LIMIT 10;
```

### Проверка размера таблиц:

```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as indexes_size
FROM pg_tables
WHERE schemaname = 'monitoring'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

---

## 🗑️ Очистка старых данных (опционально)

Для production окружения рекомендуется периодически чистить старые данные:

```sql
-- Удалить закрытые позиции старше 3 месяцев
DELETE FROM monitoring.positions 
WHERE status = 'closed' 
AND closed_at < NOW() - INTERVAL '3 months';

-- Удалить события старше 1 месяца
DELETE FROM monitoring.events 
WHERE created_at < NOW() - INTERVAL '1 month';


-- После очистки обновите статистику
VACUUM ANALYZE;
```

Можно настроить как cron job:
```bash
# Добавьте в crontab: crontab -e
0 3 * * 0 psql -d fox_crypto -f /path/to/cleanup_script.sql
```

---

## 🆘 Troubleshooting

### Ошибка: "database does not exist"
```bash
createdb fox_crypto
```

### Ошибка: "permission denied to create schema"
```bash
# Выдайте права суперпользователя или владельца БД
ALTER DATABASE fox_crypto OWNER TO your_user;
```

### Ошибка: "relation already exists"
Скрипт использует `CREATE ... IF NOT EXISTS`, поэтому безопасно выполнять повторно.
Если нужно пересоздать с нуля:
```sql
DROP SCHEMA monitoring CASCADE;
-- Затем выполните DEPLOY_SCHEMA.sql снова
```

### Проверка подключения бота к БД
```bash
# В корне проекта
python3 -c "
from database.repository import Repository
import asyncio

async def test():
    repo = Repository()
    await repo.connect()
    print('✅ Connection successful!')
    await repo.close()

asyncio.run(test())
"
```

---

## 📚 Дополнительная информация

- **Документация PostgreSQL**: https://www.postgresql.org/docs/
- **Оптимизация индексов**: https://www.postgresql.org/docs/current/indexes.html
- **Мониторинг производительности**: https://www.postgresql.org/docs/current/monitoring-stats.html

---

## ✅ Checklist для развертывания

- [ ] PostgreSQL установлен и запущен
- [ ] База данных `fox_crypto` создана
- [ ] Скрипт `DEPLOY_SCHEMA.sql` выполнен успешно
- [ ] Все таблицы созданы (10 штук)
- [ ] Индексы созданы (37 штук)
- [ ] Триггеры работают (2 штуки)
- [ ] Foreign key создан (1 штука)
- [ ] Права доступа настроены (если нужно)
- [ ] Бот может подключиться к БД
- [ ] Первый тест бота выполнен успешно

**🎉 База данных готова к работе!**
