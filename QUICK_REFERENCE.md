# 🚀 Быстрая справка - Trading Bot Service

## 📋 Основные команды

```bash
# Управление
./manage-service.sh start       # Запустить
./manage-service.sh stop        # Остановить
./manage-service.sh restart     # Перезапустить
./manage-service.sh status      # Статус
./manage-service.sh logs        # Живые логи

# Проверка
systemctl is-active trading-bot     # Запущен ли?
systemctl is-enabled trading-bot    # Автозапуск включен?
```

## 📊 Мониторинг

```bash
# Статус сервиса
./manage-service.sh status

# Живые логи
./manage-service.sh logs

# Логи бота
tail -f logs/trading_bot.log

# Использование памяти
ps aux | grep "python.*main.py"
```

## 🔄 После перезагрузки сервера

Бот запустится **АВТОМАТИЧЕСКИ** - ничего делать не нужно! ✅

## 📞 Если что-то не так

```bash
# Перезапустить
./manage-service.sh restart

# Посмотреть ошибки
tail -n 50 logs/systemd-error.log

# Сбросить failed state
sudo systemctl reset-failed trading-bot
sudo systemctl restart trading-bot
```

---

**Полная документация:** `SERVICE_SUCCESS.md`
