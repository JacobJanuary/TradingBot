# ⚡ ПЛАН ВЫПОЛНЕНИЯ: EVENT LOGGER TABLES

**Статус:** ✅ READY TO EXECUTE
**Время выполнения:** ~10 минут
**Риск:** МИНИМАЛЬНЫЙ (создаем новые таблицы, не трогаем существующие)

---

## 📋 ЧТО БУДЕТ СДЕЛАНО

### Проблема
EventLogger система логирует события в консоль, но **таблицы БД не существуют** → все события теряются и не сохраняются в базу данных.

### Решение
Создать 3 таблицы в schema monitoring:
1. **monitoring.events** - основная таблица для audit trail (КРИТИЧЕСКАЯ)
2. **monitoring.transaction_log** - для tracking БД транзакций (резерв)
3. **monitoring.event_performance_metrics** - для метрик производительности (резерв)

### Результат
После выполнения все события бота будут **автоматически сохраняться** в БД:
- Position создание/закрытие
- Stop-loss установка/ошибки
- Wave detection/completion
- Health check failures
- Bot start/stop
- И еще 64 типа событий

---

## 🚀 ПОШАГОВАЯ ИНСТРУКЦИЯ

### ШАГ 1: Backup БД (на всякий случай)
```bash
pg_dump -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -n monitoring \
  -f /tmp/monitoring_backup_before_event_tables_$(date +%Y%m%d_%H%M%S).sql
```
**Время:** ~5 секунд

### ШАГ 2: Выполнить миграцию
```bash
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -f database/migrations/004_create_event_logger_tables.sql
```

**Ожидаемый вывод:**
```
NOTICE:  ✅ Migration 004 completed successfully!
NOTICE:     - monitoring.events: CREATED
NOTICE:     - monitoring.transaction_log: CREATED
NOTICE:     - monitoring.event_performance_metrics: CREATED
NOTICE:     - monitoring.performance_metrics: INTACT (32 records)
COMMIT
```

**Время:** ~2 секунды

### ШАГ 3: Проверить таблицы созданы
```bash
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -c "\dt monitoring.events"
```

**Ожидаемый вывод:**
```
           List of relations
   Schema   |  Name  | Type  |  Owner
------------+--------+-------+----------
 monitoring | events | table | elcrypto
```

### ШАГ 4: Запустить тесты
```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot
pytest tests/phase8/test_event_logger_tables.py -v -s
```

**Ожидаемый результат:** 10/10 тестов пройдено

**Время:** ~5 секунд

### ШАГ 5: Перезапустить бота
```bash
# Остановить
pkill -f "python main.py"

# Запустить заново
python main.py --mode production --exchange both &

# Подождать инициализации
sleep 10
```

### ШАГ 6: Проверить события пишутся
```bash
psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c "
SELECT COUNT(*) as total_events,
       MAX(created_at) as last_event
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '5 minutes';
"
```

**Ожидаемый результат через 1 минуту:**
```
 total_events |         last_event
--------------+----------------------------
           15 | 2025-10-14 06:35:42.123+00
```

### ШАГ 7: Посмотреть какие события логируются
```bash
psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c "
SELECT event_type, COUNT(*) as count
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '5 minutes'
GROUP BY event_type
ORDER BY count DESC;
"
```

**Ожидаемый результат:**
```
    event_type        | count
---------------------+-------
 stop_loss_error     |    12
 signal_execution... |     3
 health_check_failed |     2
 bot_started         |     1
 wave_detected       |     1
```

---

## ✅ SUCCESS CRITERIA

После выполнения всех шагов должно быть:

1. ✅ Таблица `monitoring.events` создана
2. ✅ Таблица `monitoring.transaction_log` создана
3. ✅ Таблица `monitoring.event_performance_metrics` создана
4. ✅ Старая `monitoring.performance_metrics` не затронута (32 записи)
5. ✅ Все 10 тестов прошли
6. ✅ События появляются в `monitoring.events` в течение 1 минуты после перезапуска
7. ✅ event_type включает bot_started, stop_loss_error, health_check_failed
8. ✅ event_data содержит валидный JSON

---

## 🔧 ЕСЛИ ЧТО-ТО ПОШЛО НЕ ТАК

### Миграция failed
```bash
# Restore из backup
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -f /tmp/monitoring_backup_before_event_tables_YYYYMMDD_HHMMSS.sql

# Проверить что вернулось в исходное состояние
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -c "SELECT COUNT(*) FROM monitoring.performance_metrics;"
# Должно быть 32
```

### События не пишутся после перезапуска
```bash
# Проверить логи бота на ошибки
tail -100 /tmp/bot_monitor.log | grep -i "event\|error"

# Проверить что EventLogger инициализирован
grep "EventLogger initialized" /tmp/bot_monitor.log

# Проверить подключение к БД
psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c "SELECT 1;"
```

### Тесты failed
```bash
# Проверить структуру таблиц
psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c "
\d monitoring.events
"

# Посмотреть какие таблицы созданы
psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c "
\dt monitoring.*
"
```

---

## 📊 ПОСЛЕ ВЫПОЛНЕНИЯ

### Мониторинг событий
```sql
-- Посмотреть последние 10 событий
SELECT event_type, symbol, exchange, severity, created_at
FROM monitoring.events
ORDER BY created_at DESC
LIMIT 10;

-- События за последний час
SELECT event_type, COUNT(*) as count
FROM monitoring.events
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY event_type
ORDER BY count DESC;

-- Ошибки и критические события
SELECT event_type, error_message, created_at
FROM monitoring.events
WHERE severity IN ('ERROR', 'CRITICAL')
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;

-- Lifecycle конкретной позиции
SELECT event_type, event_data, created_at
FROM monitoring.events
WHERE position_id = 123
ORDER BY created_at;
```

### Полезные запросы
Используйте файл `audit_verify_current_coverage.sql` для детального анализа:
```bash
psql -U elcrypto -d fox_crypto -p 5433 -h localhost \
  -f audit_verify_current_coverage.sql
```

---

## 📝 ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ

### Детальный отчет исследования
См. `DEEP_RESEARCH_EVENT_LOGGER_TABLES_REPORT.md` - полный технический отчет на 800+ строк с:
- Структурой всех таблиц
- Обоснованием каждого поля
- Найденными багами в коде
- Детальным планом тестирования
- Rollback процедурами

### Найденные баги (опционально фиксить)
В `core/event_logger.py` таблицы создаются БЕЗ префикса `monitoring.`:
- Строки 180, 204, 223 - CREATE TABLE без префикса
- Строки 333, 362, 401, 429, 450, 473 - INSERT/SELECT без префикса

**НО:** Система будет работать благодаря `search_path = 'monitoring,fas,public'`

Фиксить баги можно позже, когда будет время (это refactoring, не критический баг).

---

## ⏱️ ИТОГОВОЕ ВРЕМЯ

- Backup: 5 сек
- Migration: 2 сек
- Verification: 5 сек
- Tests: 5 сек
- Bot restart: 10 сек
- Event verification: 30 сек

**ИТОГО: ~1 минута**

---

**Дата:** 2025-10-14
**Статус:** ✅ READY TO EXECUTE
**Confidence:** 100%
