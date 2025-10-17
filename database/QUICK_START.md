# ⚡ БЫСТРЫЙ СТАРТ

## 🎯 Сценарий 1: У меня НОВЫЙ сервер

```bash
# 1. Создать БД
createdb fox_crypto

# 2. Развернуть схему
psql -d fox_crypto -f database/DEPLOY_SCHEMA.sql

# 3. Готово! ✅
```

---

## 🔄 Сценарий 2: У меня СТАРАЯ неправильная структура

```bash
# 1. ОСТАНОВИТЬ БОТА!
pkill -f "python.*main.py"

# 2. Пересоздать БД (удалит данные!)
bash database/redeploy_clean.sh
# Ввести: YES

# 3. Запустить бота
python main.py

# Готово! ✅
```

---

## ✅ Проверка что всё OK

```bash
# Должно показать 10 таблиц
psql -d fox_crypto -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'monitoring';"

# Должны быть критичные колонки
psql -d fox_crypto -c "\d monitoring.positions" | grep has_trailing_stop
```

---

## 📚 Подробная документация

- **Новый сервер:** [DEPLOYMENT_INSTRUCTIONS.md](DEPLOYMENT_INSTRUCTIONS.md)
- **Переразвертывание:** [REDEPLOY_INSTRUCTIONS.md](REDEPLOY_INSTRUCTIONS.md)
- **Вся информация:** [README.md](README.md)
