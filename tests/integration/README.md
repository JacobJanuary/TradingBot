# 🧪 Real Integration Test

## Описание

Полноценный end-to-end интеграционный тест торговой системы с имитацией реальных условий.

## Компоненты

### 1. Database Setup (`real_test_db_setup.sql`)
- Создает тестовую схему `test`
- Создает таблицу `test.scoring_history` (копия `fas.scoring_history`)
- Создает вспомогательные функции и представления

### 2. Liquid Pairs Fetcher (`real_test_fetch_liquid_pairs.py`)
- Получает 30 самых ликвидных пар с Binance Futures
- Получает 30 самых ликвидных пар с Bybit Linear
- Сохраняет в `liquid_pairs.json` (60 пар total)
- Обеспечивает достаточное разнообразие для многочасовых тестов

### 3. Signal Generator (`real_test_signal_generator.py`)
- Генерирует тестовые сигналы каждые 15 минут (волны)
- Включает новые пары + дубликаты из предыдущих волн
- Реалистичные score (70-95) и метаданные

### 4. Real-time Monitor (`real_test_monitor.py`)
- Отображает статистику в реальном времени
- Отслеживает обработку сигналов
- Мониторит позиции и стоп-лоссы
- Показывает недавние операции

### 5. Launcher (`real_test_launcher.sh`)
- Автоматически запускает все компоненты
- Управляет жизненным циклом процессов
- Graceful cleanup при выходе

---

## 🚀 Быстрый Старт

### Шаг 1: Подготовка

```bash
# Перейти в корень проекта
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Проверить подключение к БД
psql postgresql://localhost/trading_bot -c "SELECT 1"
```

### Шаг 2: Запуск Теста

```bash
# Запустить launcher (по умолчанию: 1 час теста)
./tests/integration/real_test_launcher.sh

# Или с custom параметрами
TEST_DURATION=7200 WAVE_INTERVAL=900 ./tests/integration/real_test_launcher.sh
```

### Шаг 3: Ручной Запуск (альтернатива)

Если хотите запускать компоненты отдельно:

#### 3.1. Setup Database
```bash
psql postgresql://localhost/trading_bot -f tests/integration/real_test_db_setup.sql
```

#### 3.2. Fetch Liquid Pairs
```bash
python tests/integration/real_test_fetch_liquid_pairs.py
```

#### 3.3. Start Signal Generator (в отдельном терминале)
```bash
# Запустить на 1 час
python tests/integration/real_test_signal_generator.py --duration 3600

# Или бесконечно
python tests/integration/real_test_signal_generator.py
```

#### 3.4. Start Trading Bot (в отдельном терминале)
```bash
# TODO: Требуется модификация main.py для TEST_MODE
# Пока что: запустите main.py с TEST_MODE=true в .env
python main.py
```

#### 3.5. Start Monitor (в отдельном терминале)
```bash
python tests/integration/real_test_monitor.py --interval 10
```

---

## 📊 Что Проверяется

### ✅ Обработка Сигналов
- Чтение из `test.scoring_history`
- Фильтрация дубликатов
- Валидация через `SymbolFilter`
- Score threshold проверка

### ✅ Управление Позициями
- Открытие позиций (с правильным мультипликатором)
- Размещение stop-loss ордеров
- Закрытие позиций
- Синхронизация с биржами

### ✅ Stop Loss & Trailing Stop
- Создание SL сразу после позиции
- Правильный расчет SL price
- Trailing stop активация
- Обновление SL при движении цены

### ✅ Zombie Cleanup
- Обнаружение phantom positions
- Обнаружение untracked positions
- Очистка zombie orders
- Adaptive sync interval

### ✅ WebSocket Streams
- Подключение к Binance/Bybit streams
- Обработка execution events
- Reconnection при разрыве
- Graceful shutdown

### ✅ Database Transactions
- Атомарность операций
- Rollback при ошибках
- PostgreSQL Advisory Locks

### ✅ Risk Management
- Max open positions limit
- Position size limits
- Drawdown protection

---

## 🎯 Success Criteria

Тест считается успешным, если:

- ✅ Все сигналы обработаны без ошибок
- ✅ Дубликаты корректно отфильтрованы
- ✅ Все позиции созданы с SL
- ✅ WebSocket стримы стабильны
- ✅ Нет race conditions
- ✅ Нет zombie orders
- ✅ Graceful shutdown отработал
- ✅ Нет критических ошибок в логах

---

## 📝 Логи

Все компоненты пишут логи:

- **Signal Generator**: `tests/integration/signal_generator.log`
- **Trading Bot**: `logs/trading_bot.log` (основной)
- **Monitor**: Real-time вывод в терминал

---

## 🛠️ Конфигурация

### Переменные Окружения

```bash
# Database
export DB_DSN="postgresql://localhost/trading_bot"

# Test Duration (seconds)
export TEST_DURATION=3600  # 1 hour

# Wave Interval (seconds)
export WAVE_INTERVAL=900  # 15 minutes

# Monitor Update Interval (seconds)
export MONITOR_INTERVAL=10
```

### Параметры Signal Generator

```bash
python real_test_signal_generator.py \
    --duration 3600 \
    --db-dsn "postgresql://localhost/trading_bot" \
    --wave-interval 900
```

### Параметры Monitor

```bash
python real_test_monitor.py \
    --interval 10 \
    --db-dsn "postgresql://localhost/trading_bot"
```

---

## 🧹 Cleanup

### Остановка Теста

Нажмите `Ctrl+C` - все процессы будут остановлены gracefully.

### Очистка База Данных

```bash
# Удалить тестовую схему
psql postgresql://localhost/trading_bot -c "DROP SCHEMA IF EXISTS test CASCADE"

# Или удалить только таблицу
psql postgresql://localhost/trading_bot -c "DROP TABLE IF EXISTS test.scoring_history CASCADE"
```

### Удаление Логов

```bash
rm tests/integration/signal_generator.log
rm tests/integration/bot.log
rm tests/integration/liquid_pairs.json
```

---

## 📊 Пример Вывода Monitor

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🧪 REAL INTEGRATION TEST MONITOR                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ ⏰ Time: 2025-10-04 15:45:30 UTC                          ⏱️  Uptime:    15.5m ║
╚══════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 SIGNAL PROCESSING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Signals:          20    Current Wave:             2
Processed:              18    Unique Symbols:          10
Positions Opened:       15    Total Waves:              2
Binance Signals:        10    Bybit Signals:           10
Avg Score (proc):     82.45

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💼 POSITIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Positions:        15    Open:                    15
Closed:                  0    With Stop Loss:          15
Binance Positions:       8    Bybit Positions:          7

────────────────────────────────────────────────────────────────────────────────
📝 Recent Positions (Last 5):
────────────────────────────────────────────────────────────────────────────────
Symbol          Exchange    Status   Size         Entry        SL          
────────────────────────────────────────────────────────────────────────────────
BTC/USDT        binance     OPEN     0.0500       $96,500.00   $94,500.00  
ETH/USDT        bybit       OPEN     2.5000       $3,450.00    $3,380.00   
SOL/USDT        binance     OPEN     15.0000      $150.25      $147.25     
...

🔄 Next update in 10s | Press Ctrl+C to stop
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## ❓ FAQ

### Q: Можно ли запустить тест без реальных ордеров?

A: Да, используйте `DRY_RUN` режим в конфигурации бота. Тогда все операции будут симулироваться.

### Q: Сколько времени занимает тест?

A: По умолчанию 1 час (4 волны по 15 минут). Можно изменить через `TEST_DURATION`.

### Q: Можно ли остановить тест досрочно?

A: Да, нажмите `Ctrl+C`. Все процессы остановятся gracefully.

### Q: Что делать если тест упал?

A: Проверьте логи:
1. `tests/integration/signal_generator.log`
2. `logs/trading_bot.log`
3. PostgreSQL logs

### Q: Можно ли запустить несколько тестов параллельно?

A: Не рекомендуется, так как они будут писать в одну и ту же тестовую таблицу.

---

## 🐛 Troubleshooting

### Problem: "liquid_pairs.json not found"

**Solution:**
```bash
python tests/integration/real_test_fetch_liquid_pairs.py
```

### Problem: "Permission denied: real_test_launcher.sh"

**Solution:**
```bash
chmod +x tests/integration/real_test_launcher.sh
```

### Problem: "Database connection error"

**Solution:**
```bash
# Check PostgreSQL is running
psql postgresql://localhost/trading_bot -c "SELECT 1"

# Or update DB_DSN
export DB_DSN="postgresql://user:pass@localhost/trading_bot"
```

### Problem: "CCXT rate limit exceeded"

**Solution:** Подождите 1-2 минуты и попробуйте снова. CCXT автоматически управляет rate limits.

---

## 📚 Дополнительная Информация

- **План теста**: [REAL_INTEGRATION_TEST_PLAN.md](REAL_INTEGRATION_TEST_PLAN.md)
- **Основной README**: [../../README.md](../../README.md)
- **Audit Report**: [../../COMPREHENSIVE_AUDIT_REPORT.md](../../COMPREHENSIVE_AUDIT_REPORT.md)

---

## ✅ Статус

**READY FOR TESTING** ✅

Все компоненты созданы и готовы к запуску.

---

*Последнее обновление: 2025-10-04*

