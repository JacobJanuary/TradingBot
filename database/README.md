# 📁 Database Scripts

Все скрипты для управления базой данных торгового бота.

---

## 🎯 Основные скрипты

### 1. DEPLOY_SCHEMA.sql
**Назначение:** Полная схема БД для развертывания на новом сервере
**Версия:** 3.0 (извлечена из production)
**Содержит:** 1 schema, 10 tables, 37 indexes, 2 triggers, 1 FK

**Использование:**
```bash
# На новом сервере
createdb fox_crypto
psql -d fox_crypto -f database/DEPLOY_SCHEMA.sql
```

**Документация:** [DEPLOYMENT_INSTRUCTIONS.md](DEPLOYMENT_INSTRUCTIONS.md)

---

### 2. REDEPLOY_CLEAN.sql + redeploy_clean.sh
**Назначение:** Удалить старую неправильную структуру и создать новую
**⚠️ ВНИМАНИЕ:** Удаляет ВСЕ ДАННЫЕ!

**Использование:**
```bash
# Интерактивно с подтверждением
bash database/redeploy_clean.sh

# Или напрямую через psql
psql -d fox_crypto -f database/REDEPLOY_CLEAN.sql
```

**Документация:** [REDEPLOY_INSTRUCTIONS.md](REDEPLOY_INSTRUCTIONS.md)

---

### 3. test_deployment.sh
**Назначение:** Автоматическое тестирование DEPLOY_SCHEMA.sql

**Использование:**
```bash
bash database/test_deployment.sh
```

**Что проверяет:**
- ✅ Создание схемы
- ✅ Создание всех таблиц (10)
- ✅ Создание индексов (37)
- ✅ Создание триггеров (2)
- ✅ Работоспособность триггеров

---

## 📂 Структура файлов

```
database/
├── README.md                          # Этот файл
├── DEPLOY_SCHEMA.sql                  # ⭐ Основной скрипт развертывания
├── DEPLOYMENT_INSTRUCTIONS.md         # 📖 Инструкции по развертыванию
├── REDEPLOY_CLEAN.sql                 # 🔄 Скрипт пересоздания БД
├── redeploy_clean.sh                  # 🔄 Bash обёртка для REDEPLOY
├── REDEPLOY_INSTRUCTIONS.md           # 📖 Инструкции по пересозданию
├── test_deployment.sh                 # ✅ Тест развертывания
├── init.sql                           # Legacy init script
├── FULL_DB_SCHEMA.sql                 # Legacy (не использовать)
└── migrations/                        # Миграции (history)
    ├── 001_*.sql
    ├── 002_*.sql
    └── ...
```

---

## 🚀 Сценарии использования

### Сценарий 1: Новый сервер (чистая установка)
```bash
# 1. Создать БД
createdb fox_crypto

# 2. Развернуть схему
psql -d fox_crypto -f database/DEPLOY_SCHEMA.sql

# 3. Проверить
psql -d fox_crypto -c "\dt monitoring.*"
```

**Документация:** [DEPLOYMENT_INSTRUCTIONS.md](DEPLOYMENT_INSTRUCTIONS.md)

---

### Сценарий 2: Исправить старую неправильную структуру
```bash
# 1. ОСТАНОВИТЬ БОТА!
pkill -f "python.*main.py"

# 2. Пересоздать БД (удалит данные!)
bash database/redeploy_clean.sh
# Ввести: YES

# 3. Запустить бота снова
python main.py
```

**Документация:** [REDEPLOY_INSTRUCTIONS.md](REDEPLOY_INSTRUCTIONS.md)

---

### Сценарий 3: Протестировать перед production
```bash
# Запустить автотест
bash database/test_deployment.sh

# Ожидаемый результат:
# ✅ Schemas verified (1/1)
# ✅ Tables verified (10/10)
# ✅ Indexes verified (37/37)
# ✅ Triggers verified (2/2)
# 🎉 ALL TESTS PASSED!
```

---

## 📊 Структура БД v3.0

### Schema: monitoring

#### Core Tables (5)
1. **positions** - Торговые позиции
   Критичные колонки: `has_trailing_stop`, `has_stop_loss`, `error_details`

2. **orders** - Все ордера
   Types: market, limit, stop_loss, take_profit

3. **trades** - Индивидуальные сделки (fills)

4. **events** - Лог всех событий бота
   Поля: correlation_id, severity, error_message, stack_trace

5. **trailing_stop_state** - Состояние trailing stop
   FK → positions (ON DELETE CASCADE)

#### Metrics Tables (2)
6. **performance_metrics** - Метрики по периодам
7. **event_performance_metrics** - Event-based метрики

#### Risk Tables (2)
8. **risk_events** - События риск-менеджмента
9. **risk_violations** - Нарушения риск-правил

#### Audit Tables (1)
10. **transaction_log** - Аудит транзакций БД

### Indexes: 37
- Primary keys (10)
- Performance indexes (27)
  - Symbol, exchange, status
  - Timestamps (DESC)
  - Foreign keys
  - Partial indexes (WHERE clauses)

### Triggers: 2
- `update_positions_updated_at` - positions
- `update_trades_updated_at` - trades

### Foreign Keys: 1
- `trailing_stop_state.position_id` → `positions.id`

---

## ⚠️ Важные замечания

### ❌ НЕ используйте:
- `FULL_DB_SCHEMA.sql` - устарел, не соответствует production
- `init.sql` - legacy, используйте DEPLOY_SCHEMA.sql
- Миграции напрямую - они для history, используйте DEPLOY_SCHEMA.sql

### ✅ Используйте:
- **DEPLOY_SCHEMA.sql** - для новых серверов
- **REDEPLOY_CLEAN.sql** - для исправления старых структур
- **test_deployment.sh** - для проверки перед production

---

## 🔍 Проверка здоровья БД

### Проверить структуру таблицы positions
```sql
\d monitoring.positions
```

Должны быть колонки:
- ✅ `has_trailing_stop` BOOLEAN
- ✅ `has_stop_loss` BOOLEAN
- ✅ `error_details` JSONB
- ✅ `retry_count` INTEGER
- ✅ `last_error_at` TIMESTAMP

### Подсчитать объекты
```sql
-- Таблицы (должно быть 10)
SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'monitoring';

-- Индексы (должно быть 37)
SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'monitoring';

-- Триггеры (должно быть 2)
SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = 'monitoring';
```

### Проверить размер БД
```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'monitoring'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

---

## 🆘 Помощь

### Проблемы с развертыванием?
См. [DEPLOYMENT_INSTRUCTIONS.md](DEPLOYMENT_INSTRUCTIONS.md) → Troubleshooting

### Проблемы с пересозданием?
См. [REDEPLOY_INSTRUCTIONS.md](REDEPLOY_INSTRUCTIONS.md) → Troubleshooting

### Нужен backup?
```bash
# Полный backup БД
pg_dump -h localhost -U evgeniyyanvarskiy -d fox_crypto > backup_full.sql

# Только схема monitoring
pg_dump -h localhost -U evgeniyyanvarskiy -d fox_crypto -n monitoring > backup_monitoring.sql

# Только данные (без структуры)
pg_dump -h localhost -U evgeniyyanvarskiy -d fox_crypto -n monitoring --data-only > backup_data.sql
```

---

## ✅ Checklist перед production

- [ ] DEPLOY_SCHEMA.sql протестирован через test_deployment.sh
- [ ] Все 10 таблиц созданы
- [ ] Все 37 индексов созданы
- [ ] Триггеры работают (2 штуки)
- [ ] Таблица positions имеет `has_trailing_stop`, `has_stop_loss`
- [ ] Бот может подключиться к БД
- [ ] Сделан backup старых данных (если нужны)

---

**Последнее обновление:** 2025-10-17
**Версия схемы:** 3.0 (production)
