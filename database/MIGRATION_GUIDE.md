# 📚 Руководство по миграциям базы данных

## 🎯 Назначение

Скрипт `apply_migrations.py` автоматически применяет SQL миграции к базе данных.

## 🚀 Использование

### 1. Предварительный просмотр (Dry-Run)

Проверьте, какие миграции будут применены БЕЗ изменения БД:

```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot
python database/apply_migrations.py --dry-run
```

### 2. Применение миграций

Примените все pending миграции:

```bash
python database/apply_migrations.py
```

## 📋 Текущие миграции

### ✅ add_exit_reason_column.sql
**Критично!** Добавляет поле `exit_reason` в таблицу `monitoring.positions`

- **Назначение**: Хранение причины закрытия позиции (SL, TP, manual, PHANTOM_CLEANUP)
- **Влияние**: Исправляет критический баг с закрытием позиций
- **Ссылка**: CRITICAL_BUG_REPORT_20251004.md

### ✅ add_realized_pnl_column.sql
Добавляет поле `realized_pnl` для отслеживания реализованной прибыли

### ✅ fix_field_sync.sql
Синхронизирует структуру полей между кодом и БД

### ✅ add_missing_position_fields.sql
Добавляет недостающие поля для полной функциональности

### ✅ create_processed_signals_table.sql
Создает таблицу для отслеживания обработанных сигналов

## 🔍 Отслеживание миграций

Скрипт автоматически создает таблицу `monitoring.applied_migrations`:

```sql
SELECT * FROM monitoring.applied_migrations ORDER BY applied_at DESC;
```

## ⚠️ Важно

1. **Резервная копия**: Перед применением миграций сделайте backup БД:
   ```bash
   pg_dump -h localhost -p 5433 -U elcrypto fox_crypto > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Проверка**: Всегда сначала используйте `--dry-run`

3. **Откат**: В случае проблем восстановите из backup:
   ```bash
   psql -h localhost -p 5433 -U elcrypto fox_crypto < backup_20251004_120000.sql
   ```

## 🐛 Устранение проблем

### Миграция не применяется

```bash
# Проверьте подключение к БД
psql -h localhost -p 5433 -U elcrypto -d fox_crypto -c "SELECT version();"
```

### Миграция помечена как failed

```sql
-- Сбросьте статус миграции
UPDATE monitoring.applied_migrations 
SET status = 'pending' 
WHERE migration_file = 'имя_файла.sql';

-- Или удалите запись для повторного применения
DELETE FROM monitoring.applied_migrations 
WHERE migration_file = 'имя_файла.sql';
```

## 📞 Поддержка

При проблемах проверьте:
1. Логи: `logs/trading_bot.log`
2. Настройки БД: `.env` файл
3. Статус подключения: `SELECT pg_is_in_recovery();`

