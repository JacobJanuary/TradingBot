# 🧪 План Реального Интеграционного Теста

## Дата создания: 2025-10-04

---

## 🎯 Цель

Проверить работу всей торговой системы end-to-end в условиях, максимально приближенных к реальным, но с контролируемыми тестовыми данными.

---

## 📋 Компоненты Тестовой Системы

### 1. Тестовая База Данных
- **Таблица**: `test_scoring_history` (копия `fas.scoring_history`)
- **Данные**: Тестовые сигналы для самых ликвидных пар

### 2. Генератор Сигналов
- **Периодичность**: Каждые 15 минут (имитация волн)
- **Пары**: 30 Binance + 30 Bybit (самые ликвидные) = 60 пар
- **Логика**: Новые пары + часть старых (проверка дубликатов)
- **Score**: Достаточный для попадания в обработку
- **Разнообразие**: Достаточно для многочасовых тестов

### 3. Модифицированный Бот
- **Режим**: TEST_MODE
- **Источник сигналов**: `test_scoring_history`
- **Биржи**: Реальные API (но без реальных ордеров)
- **Dry-run**: Опционально

### 4. Система Мониторинга
- **Real-time логи**: Форматированный вывод
- **Метрики**: Позиции, ордера, балансы
- **Проверки**: Автоматическая валидация

---

## 🔍 Что Проверяем

### Основные Функции

1. **Обработка Сигналов**
   - ✅ Чтение из `test_scoring_history`
   - ✅ Фильтрация дубликатов (по `signal_id` или `symbol+timestamp`)
   - ✅ Валидация через `SymbolFilter`
   - ✅ Проверка score threshold

2. **Открытие Позиций**
   - ✅ Расчет размера позиции (мультипликатор)
   - ✅ Проверка баланса
   - ✅ Размещение ордера через CCXT
   - ✅ Сохранение в БД (`monitoring.positions`)
   - ✅ PostgreSQL Advisory Locks (защита от дубликатов)

3. **Stop Loss Management**
   - ✅ Создание SL ордера сразу после позиции
   - ✅ Правильный расчет SL price
   - ✅ Отмена старых SL при обновлении
   - ✅ Обработка orphaned SL orders

4. **Trailing Stop**
   - ✅ Активация при достижении threshold
   - ✅ Обновление SL при движении цены
   - ✅ Callback механизм
   - ✅ Breakeven отключен (FIX 2025-10-03)

5. **Zombie Cleanup**
   - ✅ Обнаружение phantom positions
   - ✅ Обнаружение untracked positions
   - ✅ Очистка zombie orders
   - ✅ Adaptive sync interval
   - ✅ Делегирование в `ZombieCleanupService`

6. **WebSocket Streams**
   - ✅ Подключение к Binance User Data Stream
   - ✅ Подключение к Bybit Private Stream
   - ✅ Обработка `executionReport` events
   - ✅ Обработка `position` updates
   - ✅ Reconnection при разрыве
   - ✅ Graceful shutdown

7. **Position Synchronization**
   - ✅ Periodic sync (каждые 10 минут)
   - ✅ Сравнение local cache vs exchange
   - ✅ Обработка расхождений
   - ✅ Делегирование в `PositionSynchronizer`

8. **Risk Management**
   - ✅ Max open positions limit
   - ✅ Max position size per symbol
   - ✅ Drawdown protection
   - ✅ Exposure limits

9. **Database Transactions**
   - ✅ Атомарность операций
   - ✅ Rollback при ошибках
   - ✅ Использование `repository.transaction()`

10. **Graceful Shutdown**
    - ✅ Остановка WebSocket streams
    - ✅ Закрытие соединений с биржами
    - ✅ Закрытие пула БД
    - ✅ Сохранение состояния

---

## 🛠️ Компоненты для Создания

### 1. SQL Scripts
- `tests/integration/real_test_db_setup.sql` - Создание тестовой таблицы
- `tests/integration/real_test_db_cleanup.sql` - Очистка после теста

### 2. Python Scripts
- `tests/integration/real_test_fetch_liquid_pairs.py` - Получение ликвидных пар
- `tests/integration/real_test_signal_generator.py` - Генератор сигналов (фоновый)
- `tests/integration/real_test_bot_wrapper.py` - Обертка для запуска бота в TEST_MODE
- `tests/integration/real_test_monitor.py` - Мониторинг работы бота
- `tests/integration/real_test_validator.py` - Валидация результатов
- `tests/integration/real_test_launcher.sh` - Launcher для всей системы

### 3. Configuration
- `tests/integration/real_test_config.yaml` - Настройки теста
- `.env.test` - Тестовые переменные окружения

---

## 🚀 Workflow Теста

### Phase 1: Setup (5 мин)
1. Создать `test_scoring_history` таблицу
2. Получить 10 самых ликвидных пар (5 Binance + 5 Bybit)
3. Заполнить первую волну сигналов (текущая 15-минутная волна)

### Phase 2: Start Services (1 мин)
1. Запустить Signal Generator в фоне
2. Запустить Bot в TEST_MODE
3. Запустить Monitor

### Phase 3: Observation (30-60 мин)
1. Наблюдать за обработкой сигналов (каждые 15 мин новая волна)
2. Проверять создание позиций
3. Проверять SL ордера
4. Проверять WebSocket события
5. Проверять zombie cleanup
6. Проверять trailing stop

### Phase 4: Validation (5 мин)
1. Остановить все сервисы (graceful shutdown)
2. Запустить validator скрипт
3. Проверить логи
4. Сгенерировать отчет

### Phase 5: Cleanup (1 мин)
1. Удалить тестовые данные
2. Закрыть тестовые позиции (если есть)
3. Удалить test таблицы

---

## 📊 Метрики для Проверки

### Обязательные
- ✅ Signals processed (должно быть > 0)
- ✅ Positions opened (должно соответствовать валидным сигналам)
- ✅ Stop loss created (должно быть = positions opened)
- ✅ Duplicate signals rejected (при повторной обработке)
- ✅ WebSocket connections (stable, no disconnects)
- ✅ Zombie orders cleaned (если появились)
- ✅ No race conditions (проверка через БД)
- ✅ No uncaught exceptions (проверка логов)

### Опциональные
- 📈 Trailing stop activations
- 📈 Position syncs performed
- 📈 Risk checks passed
- 📈 Transaction rollbacks (если были ошибки)

---

## 🎨 Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 REAL INTEGRATION TEST - Running
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[15:30:00] 🚀 Signal Generator: Wave 1 - 10 signals generated
[15:30:05] 🔍 Bot: Processing signals...
[15:30:10] ✅ Position opened: BTC/USDT (Binance) - SL: $94,500
[15:30:12] ✅ Position opened: ETH/USDT (Bybit) - SL: $3,400
[15:30:15] 📊 Monitor: 2 positions, 2 SL orders, 0 zombies
...
[15:45:00] 🚀 Signal Generator: Wave 2 - 10 signals (3 duplicates)
[15:45:05] 🔍 Bot: Processing signals...
[15:45:08] ⚠️  Signal duplicate rejected: BTC/USDT
[15:45:10] ✅ Position opened: SOL/USDT (Binance) - SL: $145.20
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ TEST COMPLETED - All checks passed!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🔧 Технические Детали

### Test Mode Configuration
```python
TEST_MODE = True
TEST_SIGNAL_TABLE = "test_scoring_history"
TEST_DRY_RUN = True  # Не размещать реальные ордера
TEST_DURATION = 3600  # 1 час
TEST_SIGNAL_INTERVAL = 900  # 15 минут
```

### Signal Score Formula
```python
# Для попадания в обработку нужен score > threshold
MIN_SCORE = 70  # Пример
test_signal_score = random.uniform(70, 95)  # Все сигналы валидны
```

### Duplicate Detection
```python
# В новых волнах:
# - 30% старые пары (проверка дубликатов)
# - 70% новые пары
duplicate_ratio = 0.3
```

---

## 🎯 Success Criteria

Тест считается успешным, если:

1. ✅ Все сигналы обработаны без ошибок
2. ✅ Дубликаты корректно отфильтрованы
3. ✅ Все позиции созданы с SL
4. ✅ WebSocket стримы стабильны
5. ✅ Нет race conditions
6. ✅ Нет zombie orders
7. ✅ Graceful shutdown отработал
8. ✅ Нет критических ошибок в логах
9. ✅ Все транзакции успешны
10. ✅ Метрики соответствуют ожиданиям

---

## 📝 Notes

- Используем реальные биржи, но с минимальными суммами (если не dry-run)
- Все операции логируются для анализа
- После теста обязательная очистка
- Тест можно прервать в любой момент (Ctrl+C)
- Все компоненты должны поддерживать graceful shutdown

---

## 🚦 Status: READY TO IMPLEMENT

Следующий шаг: Создание компонентов согласно плану

