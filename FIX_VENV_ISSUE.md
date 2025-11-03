# 🔧 ИСПРАВЛЕНИЕ: ModuleNotFoundError

## Проблема

Сервис падал с ошибкой:
```
ModuleNotFoundError: No module named 'dotenv'
```

**Причина:** Сервис использовал системный Python (`/usr/bin/python3`), а зависимости установлены в venv.

## ✅ Решение

Файл `trading-bot.service` обновлен для использования Python из venv.

### Было:
```ini
ExecStart=/usr/bin/python3 /home/elcrypto/TradingBot/main.py --mode production
```

### Стало:
```ini
ExecStart=/home/elcrypto/TradingBot/venv/bin/python /home/elcrypto/TradingBot/main.py --mode production
```

---

## 🚀 Переустановка сервиса (1 команда)

```bash
./fix-and-reinstall.sh
```

Этот скрипт:
1. ✅ Остановит старый сервис
2. ✅ Скопирует исправленный файл в `/etc/systemd/system/`
3. ✅ Перезагрузит systemd daemon
4. ✅ Запустит сервис с venv Python
5. ✅ Покажет статус

---

## ✅ После переустановки

Проверить статус:
```bash
./manage-service.sh status
```

Должно быть:
```
Active: active (running)
```

Посмотреть логи:
```bash
./manage-service.sh logs
```

---

## 🔍 Если все еще не работает

Проверить, что venv активирован и зависимости установлены:
```bash
# Активировать venv
source venv/bin/activate

# Проверить зависимости
pip list | grep -E "ccxt|psycopg2|dotenv|asyncio"

# Если что-то отсутствует:
pip install -r requirements.txt
```

Запустить бота вручную для проверки:
```bash
./venv/bin/python main.py --mode production
```

Если работает - значит проблема в сервисе. Проверить:
```bash
# Посмотреть какой Python использует сервис
grep ExecStart /etc/systemd/system/trading-bot.service
```

Должно быть:
```
ExecStart=/home/elcrypto/TradingBot/venv/bin/python ...
```
