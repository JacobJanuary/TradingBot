# ⚡ QUICK START: FIX EVENT LOGGER

**Проблема:** События логируются в консоль, но НЕ сохраняются в БД (таблица не существует)

**Решение:** Выполнить 3 команды за 1 минуту

---

## 🚀 ТРИ КОМАНДЫ

### 1. Backup (на всякий случай)
```bash
pg_dump -U elcrypto -d fox_crypto -p 5433 -h localhost -n monitoring -f /tmp/monitoring_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 2. Создать таблицы
```bash
psql -U elcrypto -d fox_crypto -p 5433 -h localhost -f database/migrations/004_create_event_logger_tables.sql
```

### 3. Проверить что работает
```bash
pytest tests/phase8/test_event_logger_tables.py -v
```

**Ожидаемый результат:** 10/10 tests passed

---

## ✅ ПРОВЕРКА ПОСЛЕ ПЕРЕЗАПУСКА БОТА

```bash
# Перезапустить бота
pkill -f "python main.py" && python main.py --mode production --exchange both &

# Подождать 1 минуту, затем проверить события
sleep 60
psql -U elcrypto -d fox_crypto -p 5433 -h localhost -c "SELECT event_type, COUNT(*) FROM monitoring.events WHERE created_at > NOW() - INTERVAL '5 minutes' GROUP BY event_type;"
```

**Ожидаемый результат:** Видим события (bot_started, stop_loss_error, etc.)

---

## 📊 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ

- `DEEP_RESEARCH_EVENT_LOGGER_TABLES_REPORT.md` - полный технический отчет (800+ строк)
- `EXECUTION_PLAN_EVENT_LOGGER_TABLES.md` - пошаговый план с troubleshooting
- `audit_verify_current_coverage.sql` - SQL запросы для анализа событий

---

**Время выполнения:** 1 минута
**Риск:** Минимальный (создаем новые таблицы, не трогаем существующие)
**Rollback:** `psql ... -f /tmp/monitoring_backup_TIMESTAMP.sql`
