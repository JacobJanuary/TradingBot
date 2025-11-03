# 🚀 Быстрый старт - Systemd Service

## 3 команды для установки:

```bash
# 1. Установить сервис
./install-service.sh

# 2. Запустить бота
sudo systemctl start trading-bot

# 3. Проверить статус
sudo systemctl status trading-bot
```

---

## Управление одной командой:

```bash
./manage-service.sh start       # Запустить
./manage-service.sh stop        # Остановить
./manage-service.sh restart     # Перезапустить
./manage-service.sh status      # Статус
./manage-service.sh logs        # Живые логи
```

---

## Важные проверки ПЕРЕД установкой:

```bash
# 1. Убедиться что бот работает вручную
python3 main.py --mode production

# 2. Остановить текущий процесс (если есть)
pkill -f "python.*main.py.*production"

# 3. Проверить PostgreSQL
sudo systemctl status postgresql
```

---

## После установки:

```bash
# Смотреть логи в реальном времени
./manage-service.sh logs

# Проверить автозапуск
sudo systemctl is-enabled trading-bot  # должно быть: enabled
```

---

## Файлы логов:

- `logs/trading_bot.log` - основные логи бота
- `logs/systemd-output.log` - stdout systemd
- `logs/systemd-error.log` - stderr systemd

---

**Полная документация:** см. `SERVICE_SETUP_GUIDE.md`
