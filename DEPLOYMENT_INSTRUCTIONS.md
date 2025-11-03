# 🚀 DEPLOYMENT INSTRUCTIONS - Trailing Stop Fix

**Branch:** `fix/trailing-stop-params-load-positions`  
**Commits:** 2 (fix + docs)  
**Status:** READY FOR DEPLOYMENT

---

## ✅ ЗАВЕРШЕНО (Фазы 1-5)

- [x] Feature branch создан
- [x] Backup создан
- [x] Фикс реализован
- [x] Статический анализ пройден
- [x] Коммиты созданы

---

## 📋 СЛЕДУЮЩИЕ ШАГИ (РУЧНЫЕ)

### ВАРИАНТ A: Прямой deploy на Production (БЕЗ STAGING)

**⚠️ ТОЛЬКО ЕСЛИ НЕТ STAGING ОКРУЖЕНИЯ**

```bash
# 1. Остановить бота
sudo systemctl stop trading-bot

# 2. Merge в main
git checkout main
git merge --no-ff fix/trailing-stop-params-load-positions
git push origin main

# 3. Запустить бота
sudo systemctl start trading-bot

# 4. Мониторинг (2-3 минуты)
tail -f logs/trading_bot.log | grep -i "trailing\|TS\|error"

# 5. Проверка успеха
# Должно быть 0 новых ошибок "Error initializing trailing stop"
grep "Error initializing trailing stop" logs/trading_bot.log | \
  grep "$(date +%Y-%m-%d)" | wc -l

# 6. Проверка TS создан для всех позиций
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT COUNT(*) FROM monitoring.trailing_stop_state;"

# Должно быть = количеству активных позиций
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT COUNT(*) FROM monitoring.positions WHERE status='active';"
```

---

### ВАРИАНТ B: С использованием Staging

```bash
# На STAGING сервере
git fetch origin
git checkout fix/trailing-stop-params-load-positions

sudo systemctl stop trading-bot
sudo systemctl start trading-bot

# Проверка логов
tail -f logs/trading_bot.log | grep -i "trailing\|error"

# После успешного staging -> deploy на PROD
```

---

## 🔍 КРИТЕРИИ УСПЕХА

После deployment проверить:

1. **НЕТ ОШИБОК TS:**
```bash
grep "Error initializing trailing stop" logs/trading_bot.log | \
  grep "$(date +%Y-%m-%d)" | tail -10
# Ожидается: 0 строк с новыми ошибками
```

2. **TS СОЗДАН ДЛЯ ВСЕХ ПОЗИЦИЙ:**
```bash
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT 
    (SELECT COUNT(*) FROM monitoring.trailing_stop_state) as ts_count,
    (SELECT COUNT(*) FROM monitoring.positions WHERE status='active') as pos_count;"
# Ожидается: ts_count = pos_count
```

3. **ПАРАМЕТРЫ ЗАПОЛНЕНЫ:**
```bash
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT symbol, activation_percent, callback_percent 
   FROM monitoring.trailing_stop_state 
   LIMIT 3;"
# Ожидается: activation_percent и callback_percent НЕ NULL
```

---

## 🔄 ROLLBACK (если что-то пошло не так)

```bash
# БЫСТРЫЙ ОТКАТ (2 минуты)

# 1. Остановить бота
sudo systemctl stop trading-bot

# 2. Откат к предыдущему коммиту
git log --oneline -5  # Найти hash коммита ПЕРЕД fix
git reset --hard 237b343  # Заменить на актуальный hash

# ИЛИ использовать backup
cp core/position_manager.py.BACKUP_TS_FIX_20251102_234831 core/position_manager.py

# 3. Запустить бота
sudo systemctl start trading-bot

# 4. Проверить
tail -f logs/trading_bot.log
```

---

## 📊 МОНИТОРИНГ (24 часа)

После deployment запустить monitoring скрипт:

```bash
./monitor_ts_health.sh &
```

Или вручную каждые 30 минут:

```bash
# Проверка ошибок
grep "Error initializing trailing stop" logs/trading_bot.log | wc -l

# Проверка количества TS
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -t -c \
  "SELECT COUNT(*) FROM monitoring.trailing_stop_state;"

# Проверка активаций
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT COUNT(*) FROM monitoring.trailing_stop_state WHERE state='active';"
```

---

## 📞 В СЛУЧАЕ ПРОБЛЕМ

1. **Немедленный откат** (см. ROLLBACK выше)
2. **Сохранить логи** для анализа
3. **Проверить** TRAILING_STOP_AUDIT_REPORT.md

---

**ВАЖНО:** После успешного deployment удалить feature branch:

```bash
git branch -d fix/trailing-stop-params-load-positions
git push origin --delete fix/trailing-stop-params-load-positions
```

---

*Инструкции подготовлены: 2025-11-02*  
*Автор: Automated Deployment Guide*
