# 🔄 ИНСТРУКЦИЯ ПО ПЕРЕРАЗВЕРТЫВАНИЮ БД

## ⚠️ ВНИМАНИЕ: ВСЕ ДАННЫЕ БУДУТ УДАЛЕНЫ!

Этот скрипт полностью удаляет старую структуру БД и создаёт новую с нуля.

---

## 🎯 Когда использовать

- У вас есть старая схема из недоделанного скрипта
- Структура БД не соответствует production
- Нужно пересоздать БД с правильной структурой
- Отсутствуют критичные колонки (например, `has_trailing_stop`)

---

## 📋 Что делает скрипт

1. **DROP SCHEMA monitoring CASCADE** - удаляет всё из monitoring
2. **DROP SCHEMA fas CASCADE** - удаляет legacy FAS (если есть)
3. **DROP FUNCTION update_updated_at_column()** - удаляет orphaned функции
4. **Проверка очистки** - верифицирует что всё удалено
5. **\i database/DEPLOY_SCHEMA.sql** - разворачивает свежую схему v3.0
6. **Финальная проверка** - показывает что создано

---

## 🚀 Использование

### Вариант 1: Через bash скрипт (рекомендуется)

```bash
# Запуск с подтверждением
bash database/redeploy_clean.sh

# Или с явным указанием параметров
bash database/redeploy_clean.sh fox_crypto evgeniyyanvarskiy localhost 5432
```

**Скрипт попросит подтверждение:**
```
⚠️  WARNING: DESTRUCTIVE OPERATION ⚠️
...
Are you ABSOLUTELY sure? Type 'YES' to continue:
```

Введите `YES` (заглавными!) для продолжения.

### Вариант 2: Напрямую через psql

```bash
# С паролем из переменной окружения
PGPASSWORD='your_password' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -f database/REDEPLOY_CLEAN.sql

# Или интерактивно (попросит пароль)
psql -h localhost -U evgeniyyanvarskiy -d fox_crypto -f database/REDEPLOY_CLEAN.sql
```

---

## 📊 Что будет создано

После выполнения скрипта вы получите:

### ✅ 1 Schema
- `monitoring` - вся структура бота

### ✅ 10 Tables
1. `monitoring.positions` - позиции (с `has_trailing_stop`, `has_stop_loss`, `error_details`)
2. `monitoring.orders` - ордера
3. `monitoring.trades` - сделки
4. `monitoring.events` - события
5. `monitoring.trailing_stop_state` - trailing stop состояния
6. `monitoring.performance_metrics` - метрики производительности
7. `monitoring.event_performance_metrics` - event-based метрики
8. `monitoring.risk_events` - риск события
9. `monitoring.risk_violations` - нарушения риск-правил
10. `monitoring.transaction_log` - лог транзакций

### ✅ 37 Indexes
- Оптимизированные для всех частых запросов
- Partial indexes для фильтрации
- Composite indexes для сложных запросов

### ✅ 2 Triggers
- `update_positions_updated_at` - авто-обновление updated_at для positions
- `update_trades_updated_at` - авто-обновление updated_at для trades

### ✅ 1 Foreign Key
- `trailing_stop_state.position_id` → `positions.id` (ON DELETE CASCADE)

---

## 🔍 Проверка результата

После выполнения скрипт автоматически покажет:

```
✅ Schema: monitoring | table_count: 10
✅ Total indexes: 37
✅ Total triggers: 2
```

Дополнительная ручная проверка:

```sql
-- Проверить таблицы
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname = 'monitoring'
ORDER BY tablename;

-- Проверить что has_trailing_stop существует
\d monitoring.positions

-- Проверить индексы
SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'monitoring';
```

---

## ⚡ Быстрый старт (для нетерпеливых)

```bash
# 1. Остановите бота (если запущен)
pkill -f "python.*main.py"

# 2. Запустите переразвертывание
bash database/redeploy_clean.sh

# 3. Введите YES когда попросит подтверждение

# 4. Дождитесь "🎉 SUCCESS!"

# 5. Запустите бота снова
python main.py
```

---

## 🛡️ Безопасность

### Что НЕ удаляется:
- ❌ Сама база данных `fox_crypto`
- ❌ Другие схемы (public, pg_catalog, etc.)
- ❌ Пользователи и права доступа

### Что удаляется:
- ✅ Вся схема `monitoring` со всеми данными
- ✅ Все позиции, ордера, сделки, события
- ✅ Вся статистика и метрики
- ✅ Legacy схема `fas` (если была)

### Рекомендации:
1. **Сделайте backup** если нужны данные:
   ```bash
   pg_dump -h localhost -U evgeniyyanvarskiy -d fox_crypto -n monitoring > backup_monitoring.sql
   ```

2. **Проверьте что бот остановлен** перед переразвертыванием

3. **Используйте на тестовой БД** сначала:
   ```bash
   bash database/redeploy_clean.sh fox_crypto_test
   ```

---

## 🆘 Troubleshooting

### Ошибка: "database does not exist"
```bash
createdb fox_crypto
```

### Ошибка: "permission denied"
Убедитесь что пользователь имеет права:
```sql
ALTER DATABASE fox_crypto OWNER TO evgeniyyanvarskiy;
```

### Ошибка: "cannot drop schema monitoring because other objects depend on it"
Это не должно происходить (используется CASCADE), но если произошло:
```sql
-- Принудительная очистка
DROP SCHEMA monitoring CASCADE;
DROP SCHEMA fas CASCADE;
```

### Скрипт завис на "Are you ABSOLUTELY sure?"
Введите `YES` (заглавными буквами), не `yes` или `Yes`.

---

## 📝 После переразвертывания

1. **Проверьте структуру**:
   ```sql
   \d monitoring.positions
   ```
   Должны быть колонки: `has_trailing_stop`, `has_stop_loss`, `error_details`

2. **Проверьте подключение бота**:
   ```bash
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

3. **Запустите бота** и убедитесь что нет ошибок связанных с БД

---

## ✅ Готово!

После успешного выполнения у вас будет:
- ✅ Чистая БД с правильной структурой (v3.0)
- ✅ Все нужные таблицы и колонки
- ✅ Оптимизированные индексы
- ✅ Работающие триггеры
- ✅ Готово к production использованию

**Теперь бот готов к работе с правильной структурой БД!** 🎉
