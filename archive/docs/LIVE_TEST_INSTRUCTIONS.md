# ИНСТРУКЦИИ: LIVE ТЕСТИРОВАНИЕ WAVE DETECTOR (PRODUCTION MODE)

**Дата подготовки:** 2025-10-15
**Цель:** Верификация корректности Stop-Loss ордеров в реальных условиях

---

## ⚠️ ВАЖНО ПЕРЕД ЗАПУСКОМ

### Проверка окружения
Бот настроен на **TESTNET**:
```bash
BINANCE_TESTNET=true
BYBIT_TESTNET=true
```

✅ **БЕЗОПАСНО** - тестирование на testnet, реальные деньги не затронуты

---

## ШАГИ ПОДГОТОВКИ

### Шаг 1: Остановить существующего бота

```bash
# Проверить запущенные процессы
ps aux | grep "python.*main.py"

# Если бот запущен - остановить
pkill -f "python.*main.py"

# Проверить что процесс остановлен
ps aux | grep "python.*main.py"
# Должно быть пусто или только grep
```

### Шаг 2: Очистить кэш Python

```bash
# Удалить .pyc файлы и __pycache__
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete

# Очистить логи (опционально)
> logs/trading_bot.log

echo "✅ Кэш Python очищен"
```

### Шаг 3: Проверить конфигурацию

```bash
# Проверить критичные настройки
grep -E "WAVE_CHECK_MINUTES|MAX_TRADES_PER_15MIN|POSITION_SIZE_USD|TESTNET" .env

# Ожидаемый вывод:
# WAVE_CHECK_MINUTES=5,20,35,50
# MAX_TRADES_PER_15MIN=5
# POSITION_SIZE_USD=200
# BINANCE_TESTNET=true
# BYBIT_TESTNET=true
```

**Проверьте:**
- ✅ `TESTNET=true` для обеих бирж (безопасность)
- ✅ `POSITION_SIZE_USD=200` (небольшой размер для теста)
- ✅ `MAX_TRADES_PER_15MIN=5` (ограничение позиций)

---

## ЗАПУСК LIVE ТЕСТИРОВАНИЯ

### Вариант 1: Полностью автоматический (РЕКОМЕНДУЕТСЯ)

```bash
# Запуск диагностического скрипта в production mode
# Скрипт автоматически запустит бота и будет мониторить 15+ минут
python monitor_wave_detector_live.py
```

**ЧТО СКРИПТ ДЕЛАЕТ:**
1. Запускает `python main.py --mode production`
2. Мониторит логи в реальном времени
3. Отслеживает:
   - Получение волн каждые 15 минут
   - Размещение позиций
   - Размещение SL ордеров
   - **КРИТИЧНО:** Наличие `reduceOnly=True` в SL
4. Через 15+ минут:
   - Останавливает бота
   - Генерирует детальный отчет

### Вариант 2: Ручной мониторинг

Если хотите контролировать процесс вручную:

```bash
# Терминал 1: Запуск бота
python main.py --mode production

# Терминал 2: Мониторинг логов
tail -f logs/trading_bot.log | grep -E "Wave|Signal|Position|Stop Loss|reduceOnly"
```

**Наблюдайте за:**
```
🌊 Wave detected                    # Волна обнаружена
📡 Received N signals               # Получены сигналы
📈 Position opened: SYMBOL          # Позиция открыта
🛡️ Stop Loss set at PRICE          # SL размещен
✅ reduceOnly: True                 # КРИТИЧНО - проверка
```

---

## ЧТО ПРОВЕРЯТЬ ВО ВРЕМЯ ТЕСТА

### 1. Волны приходят регулярно

**Ожидание:** Волна каждые ~15 минут

```bash
# Следить за логом
tail -f logs/trading_bot.log | grep "Wave detected"

# Должно быть примерно:
# [00:05] Wave detected
# [00:20] Wave detected
# [00:35] Wave detected
# [00:50] Wave detected
```

### 2. Позиции открываются

**Ожидание:** До 5 позиций за волну

```bash
# Следить за открытиями
tail -f logs/trading_bot.log | grep "Position opened"
```

### 3. КРИТИЧНО: Stop-Loss с reduceOnly

**Ожидание:** Каждая позиция имеет SL с `reduceOnly=True`

```bash
# Следить за SL ордерами
tail -f logs/trading_bot.log | grep -i "stop.*loss\|reduceonly"
```

**ПРАВИЛЬНЫЙ ЛОГ (Binance):**
```
Stop Loss set at 45000.00
params={'stopPrice': 45000.00, 'reduceOnly': True}
✅ Stop Loss order created: 12345678
```

**ПРАВИЛЬНЫЙ ЛОГ (Bybit):**
```
Stop Loss set at 45000.00
Bybit set_trading_stop params: {'stopLoss': '45000.00', 'positionIdx': 0, ...}
✅ Stop Loss set successfully
```

### 4. Проверка на бирже (опционально)

Если хотите увидеть своими глазами:

**Binance Testnet:**
1. Открыть https://testnet.binancefuture.com
2. Войти с тестовыми ключами
3. Открыть "Positions" → проверить открытые позиции
4. Открыть "Open Orders" → проверить SL ордера
5. Проверить что SL ордер имеет:
   - ✅ Type: STOP_MARKET
   - ✅ Reduce Only: Yes

**Bybit Testnet:**
1. Открыть https://testnet.bybit.com
2. Войти с тестовыми ключами
3. Открыть "Positions" → проверить позиции
4. Проверить что в позиции есть "SL" (position-attached)

---

## КРИТЕРИИ УСПЕХА

### ✅ PASS - Тест пройден если:

1. **Волны:** Обнаружено минимум 1 волна за 15 минут
2. **Позиции:** Открыто минимум 1 позиция
3. **Stop-Loss:** Каждая позиция имеет SL
4. **reduceOnly:** Все SL ордера имеют:
   - Binance: `reduceOnly=True` ИЛИ
   - Bybit: Position-attached SL

### ❌ FAIL - Тест провален если:

1. Ни одной волны за 15 минут
2. Позиция открыта БЕЗ Stop-Loss
3. Stop-Loss БЕЗ `reduceOnly=True` (Binance)
4. Критичные ошибки при размещении ордеров

---

## ПОСЛЕ ЗАВЕРШЕНИЯ ТЕСТА

### 1. Остановить бота

```bash
# Если запущен через скрипт - он остановится автоматически через 15 мин

# Если запущен вручную:
# Нажать Ctrl+C в терминале ИЛИ
pkill -f "python.*main.py"
```

### 2. Проверить отчет

Автоматический скрипт создаст:
```
wave_detector_live_diagnostic.log    # Полные логи
```

И выведет отчет в консоль:
```
📊 LIVE ДИАГНОСТИЧЕСКИЙ ОТЧЕТ
⏱️  Длительность: 15.2 минут
🌊 Волн обнаружено: 1
📝 Позиций открыто: 3
🛡️ SL ордеров: 3
🔴 SL с reduceOnly: 3
🔴 SL БЕЗ reduceOnly: 0
✅ Все проверки пройдены
```

### 3. Проверить позиции на бирже

```bash
# Запустить диагностический скрипт для проверки реального состояния
python check_real_orders.py

# Или проверить вручную через Web UI биржи
```

### 4. Закрыть тестовые позиции (опционально)

```bash
# Если хотите закрыть все тестовые позиции сразу
python tools/emergency/close_all_positions.py --confirm
```

---

## TROUBLESHOOTING

### Проблема: Бот не запускается

```bash
# Проверить логи
tail -50 logs/trading_bot.log

# Проверить что БД доступна
psql -h localhost -p 5433 -U elcrypto -d fox_crypto -c "SELECT 1"
```

### Проблема: WebSocket не подключается

```bash
# Проверить доступность сервера сигналов
ping 10.8.0.1

# Проверить что сервер запущен на порту 8765
nc -zv 10.8.0.1 8765
```

### Проблема: Нет сигналов

```bash
# Проверить логи WebSocket клиента
tail -f logs/trading_bot.log | grep -i websocket

# Ожидается:
# "WebSocket connected to signal server"
# "Authenticated successfully"
```

### Проблема: Позиции открываются, но нет SL

**КРИТИЧНО!** Если позиция открыта без SL:

1. Проверить логи на ошибки:
```bash
grep -i "error.*stop.*loss\|sl.*error" logs/trading_bot.log
```

2. Проверить что StopLossManager работает:
```bash
grep "StopLossManager\|set_stop_loss" logs/trading_bot.log
```

3. Если SL не размещается - немедленно закрыть позицию вручную:
```bash
python tools/emergency/close_all_positions.py --symbol BTCUSDT --confirm
```

---

## БЕЗОПАСНОСТЬ

### ✅ Тест БЕЗОПАСЕН потому что:

1. **Testnet:** Бот работает на testnet (fake money)
2. **Малый размер:** `POSITION_SIZE_USD=200` (маленькие позиции)
3. **Ограничение:** `MAX_TRADES_PER_15MIN=5` (максимум 5 позиций)
4. **Stop-Loss:** Каждая позиция защищена SL
5. **Мониторинг:** Скрипт отслеживает все в реальном времени

### ⚠️ ПРЕДОСТЕРЕЖЕНИЯ:

- Не меняй `TESTNET=true` на `false` без понимания последствий
- Не увеличивай `POSITION_SIZE_USD` для теста
- Не оставляй бота запущенным без мониторинга

---

## БЫСТРЫЙ СТАРТ (TL;DR)

```bash
# 1. Остановить бота
pkill -f "python.*main.py"

# 2. Очистить кэш
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 3. Запустить диагностику (15 минут)
python monitor_wave_detector_live.py

# 4. Дождаться завершения и проверить отчет
# Скрипт остановится автоматически через 15+ минут

# 5. Проверить результаты в wave_detector_live_diagnostic.log
```

---

## КОНТАКТЫ ДЛЯ ВОПРОСОВ

- Логи: `logs/trading_bot.log`
- Диагностика: `wave_detector_live_diagnostic.log`
- Отчет аудита: `WAVE_DETECTOR_AUDIT_FULL_REPORT.md`

**Готовы запускать?** 🚀
