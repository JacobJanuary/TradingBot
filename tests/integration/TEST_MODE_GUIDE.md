# 🧪 TEST MODE - Руководство

## Описание

TEST MODE позволяет запустить торгового бота с тестовыми сигналами из `test.scoring_history` вместо реальных сигналов из `fas.scoring_history`.

## Как Работает

При включении TEST MODE:

1. **SignalProcessor** читает сигналы из `test.scoring_history`
2. Все остальные компоненты работают в обычном режиме:
   - Реальные подключения к биржам (Binance, Bybit)
   - Реальная база данных для позиций
   - Реальные WebSocket стримы
   - Реальные ордера (если не включен DRY_RUN)

⚠️ **ВНИМАНИЕ**: TEST MODE только меняет источник сигналов, но **не симулирует торговлю**. Ордера будут реальными!

---

## 🚀 Быстрый Старт

### Шаг 1: Включить TEST MODE

Добавьте в `.env` файл:

```bash
# Enable Test Mode
TEST_MODE=true
```

Или запустите через переменную окружения:

```bash
TEST_MODE=true python main.py
```

### Шаг 2: Убедиться что тестовые сигналы есть

```bash
# Проверить наличие тестовых сигналов
PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto \
  -c "SELECT COUNT(*) FROM test.scoring_history WHERE NOT processed;"
```

### Шаг 3: Запустить бота

```bash
python main.py
```

Вы должны увидеть в логах:

```
================================================================================
🧪 TEST MODE ENABLED - Reading signals from test.scoring_history
================================================================================
```

---

## 📊 Комбинация с Integration Test

### Полный Setup (Рекомендуется)

1. **Терминал 1: Signal Generator**
   ```bash
   python tests/integration/real_test_signal_generator.py \
     --db-dsn "postgresql://elcrypto:LohNeMamont@!21@localhost:5433/fox_crypto" \
     --duration 3600
   ```

2. **Терминал 2: Monitor**
   ```bash
   python tests/integration/real_test_monitor.py \
     --db-dsn "postgresql://elcrypto:LohNeMamont@!21@localhost:5433/fox_crypto" \
     --interval 10
   ```

3. **Терминал 3: Trading Bot (TEST MODE)**
   ```bash
   TEST_MODE=true python main.py
   ```

---

## ⚙️ Настройка .env для TEST MODE

### Минимальная конфигурация

```bash
# ============================================================================
# TEST MODE CONFIGURATION
# ============================================================================

# Enable test mode (reads from test.scoring_history)
TEST_MODE=true

# Optional: Use testnet exchanges (recommended for testing)
BINANCE_TESTNET=true
BYBIT_TESTNET=true
```

### Полная конфигурация с безопасностью

```bash
# ============================================================================
# TEST MODE CONFIGURATION (SAFE)
# ============================================================================

# Enable test mode
TEST_MODE=true

# Use testnet exchanges (NO REAL TRADING)
BINANCE_TESTNET=true
BYBIT_TESTNET=true

# Testnet API keys (get from testnet.binance.vision / testnet.bybit.com)
BINANCE_API_KEY=your_testnet_api_key
BINANCE_API_SECRET=your_testnet_api_secret
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret

# Reduce position sizes for testing
POSITION_SIZE_MULTIPLIER=0.01  # 1% of normal size

# Reduce max positions
MAX_OPEN_POSITIONS=5
```

---

## 🔍 Проверка Режима

### Через Логи

При старте бота проверьте логи:

```bash
tail -f logs/trading_bot.log | grep "TEST MODE"
```

Должно быть:
```
🧪 TEST MODE ENABLED - Reading signals from test.scoring_history
```

### Через SQL

Проверить что сигналы читаются из правильной таблицы:

```sql
-- Посмотреть непроцессированные тестовые сигналы
SELECT 
    id, symbol, exchange, score, 
    processed, position_opened, 
    timestamp 
FROM test.scoring_history 
WHERE NOT processed 
ORDER BY score DESC 
LIMIT 10;
```

---

## 📋 Различия между TEST MODE и Production

| Параметр | Production | TEST MODE |
|----------|-----------|-----------|
| Источник сигналов | `fas.scoring_history` | `test.scoring_history` |
| Query сложность | Complex (JOIN с trading_pairs) | Simplified (прямой SELECT) |
| Exchange field | Через JOIN | Прямо в таблице |
| Биржи | Реальные | Реальные (или testnet если настроено) |
| Ордера | Реальные | Реальные (или testnet если настроено) |
| Database | Реальная | Реальная (same DB, но test schema) |
| WebSocket | Реальные | Реальные |

---

## ⚠️ Безопасность

### Для реального тестирования

1. **Используйте testnet биржи:**
   ```bash
   BINANCE_TESTNET=true
   BYBIT_TESTNET=true
   ```

2. **Уменьшите размеры позиций:**
   ```bash
   POSITION_SIZE_MULTIPLIER=0.01
   ```

3. **Ограничьте количество позиций:**
   ```bash
   MAX_OPEN_POSITIONS=3
   ```

### Для DRY RUN (без реальных ордеров)

Если хотите только логировать без реальных ордеров:

```bash
TEST_MODE=true
DRY_RUN=true  # Если поддерживается
```

---

## 🧹 Cleanup после теста

### Удалить тестовые сигналы

```sql
-- Удалить все тестовые сигналы
DELETE FROM test.scoring_history;

-- Или пометить как обработанные
UPDATE test.scoring_history SET processed = true;
```

### Удалить тестовые позиции

```sql
-- Закрыть все тестовые позиции
UPDATE monitoring.positions 
SET status = 'CLOSED', closed_at = NOW()
WHERE status = 'OPEN' 
  AND created_at > '2025-10-04';  -- Замените на дату начала теста
```

### Удалить тестовую схему (полная очистка)

```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -p 5433 -U elcrypto -d fox_crypto \
  -c "DROP SCHEMA IF EXISTS test CASCADE"
```

---

## 🐛 Troubleshooting

### Проблема: Bot не видит тестовые сигналы

**Решение:**
```sql
-- Убедитесь что сигналы не обработаны
SELECT COUNT(*) FROM test.scoring_history WHERE processed = false;

-- Сбросить processed флаг если нужно
UPDATE test.scoring_history SET processed = false;
```

### Проблема: "TEST MODE ENABLED" не появляется в логах

**Решение:**
```bash
# Проверить переменную окружения
echo $TEST_MODE

# Или принудительно установить
export TEST_MODE=true
python main.py
```

### Проблема: Ошибки SQL в тестовом режиме

**Решение:**
```sql
-- Проверить структуру таблицы
\d test.scoring_history

-- Убедиться что колонки совпадают
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'test' 
  AND table_name = 'scoring_history';
```

---

## 📚 Дополнительная Информация

- **Integration Test Plan**: [REAL_INTEGRATION_TEST_PLAN.md](REAL_INTEGRATION_TEST_PLAN.md)
- **README**: [README.md](README.md)
- **Signal Generator**: [real_test_signal_generator.py](real_test_signal_generator.py)
- **Monitor**: [real_test_monitor.py](real_test_monitor.py)

---

## ✅ Checklist перед запуском

- [ ] `TEST_MODE=true` установлен
- [ ] Тестовая таблица создана (`test.scoring_history`)
- [ ] Тестовые сигналы загружены (через signal generator)
- [ ] (Опционально) Testnet биржи настроены
- [ ] (Опционально) Размеры позиций уменьшены
- [ ] (Опционально) Monitor запущен для отслеживания

---

*Последнее обновление: 2025-10-04*

