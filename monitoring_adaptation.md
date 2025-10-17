# Адаптация скрипта мониторинга

## Найденные пути
- **Лог файл:** logs/trading_bot.log
- **База данных:** PostgreSQL
  - Host: из DB_HOST в .env (default: localhost)
  - Port: из DB_PORT в .env (default: 5433)
  - Database: из DB_NAME в .env (default: fox_crypto)
  - User: из DB_USER в .env (default: elcrypto)
  - Password: из DB_PASSWORD в .env

## Формат логов
Примеры реальных строк из логов:
```
2025-10-17 04:56:54,682 - core.event_logger - INFO - position_updated: {'symbol': 'IDEXUSDT', 'position_id': 379, 'old_price': 0.02245, 'new_price': 0.02246}
2025-10-17 04:57:00,592 - core.aged_position_manager - ERROR - Error checking aged positions: Invalid format specifier
2025-10-17 04:57:01,081 - core.stop_loss_manager - INFO - ✅ Position AINUSDT has Stop Loss order: 8801554 at 0.13521
2025-10-17 04:57:01,081 - core.position_manager - INFO - Checking position AINUSDT: has_sl=True, price=0.13521
```

## Адаптированные паттерны
Скрипт monitor_bot.py уже содержит адаптированные регулярные выражения на основе анализа реального формата логов:

- Волны и сигналы
- Позиции (открытие, закрытие, обновление)
- Stop Loss (создание, проверка, движение)
- Trailing Stop (активация, обновление)
- Protection модуль (проверки)
- Zombie orders (обнаружение, удаление)
- Aged позиции (обнаружение, обработка)
- WebSocket события
- Ошибки и предупреждения

## Схема БД

### Схема monitoring
- **positions** - Открытые позиции
  - id, symbol, exchange, side, quantity
  - entry_price, has_stop_loss, stop_loss_price
  - trailing_activated, status, opened_at
  - unrealized_pnl

### Схема trading
- **orders** - Ордера
  - id, symbol, exchange, type, side
  - status, created_at

## Адаптированные SQL запросы
Запросы в monitor_bot.py уже адаптированы под реальную схему:
```sql
-- Получение открытых позиций
SELECT * FROM monitoring.positions WHERE status = 'OPEN';

-- Получение активных ордеров
SELECT * FROM trading.orders
WHERE status IN ('open', 'NEW', 'PARTIALLY_FILLED', 'PENDING');
```

## Специфичные проверки для проекта

### 1. Проверка reduceOnly параметра
Скрипт специально отслеживает ошибки связанные с отсутствием reduceOnly в SL ордерах

### 2. Проверка heartbeat для Bybit
Мониторинг WebSocket disconnects и reconnects для выявления проблем с heartbeat

### 3. Проверка aged позиций
Отслеживание позиций старше MAX_POSITION_AGE_HOURS

### 4. Zombie order detection
Мониторинг обнаружения и удаления зомби-ордеров

## Как запустить мониторинг

1. **Убедитесь что бот запущен:**
```bash
# Проверить что процесс бота работает
ps aux | grep "python.*main.py"

# Проверить что лог-файл обновляется
tail -f logs/trading_bot.log
```

2. **Запустите скрипт мониторинга:**
```bash
# Из корневой директории проекта
python monitor_bot.py
```

3. **Интерпретация вывода:**
- Каждые 10 минут генерируется отчет
- Критические проблемы помечаются 🔴
- Высокий риск помечается 🟠
- JSON отчеты сохраняются в monitoring_report_XXX.json
- Финальный отчет в monitoring_final_report.json

## Что отслеживает монитор

### События
- 🌊 Получение и обработка волн
- 📈 Открытие позиций
- 🛡️ Создание Stop Loss
- 🎯 Активация Trailing Stop
- ✅/❌ Закрытие позиций с PnL
- 🧟 Обнаружение zombie orders
- ⏰ Aged позиции
- 🔌 WebSocket разрывы и реконнекты

### Аномалии
- Позиции без SL более 60 секунд
- Рассинхронизация БД и логов
- Высокая частота ошибок (>5 за 10 мин)
- Критические ошибки
- Отсутствие reduceOnly в SL ордерах

### Статистика
- Количество открытых позиций
- Позиции с активным Trailing Stop
- Позиции ожидающие SL
- Aged позиции
- Общее количество событий по типам