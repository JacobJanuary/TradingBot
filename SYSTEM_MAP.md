# SYSTEM MAP - Trading Bot Architecture
Generated: 2025-09-29

## 📁 Структура проекта

```
TradingBot/
│
├── 📂 config/                 # Конфигурация системы
│   ├── __init__.py
│   ├── config.yaml            # Основная конфигурация
│   ├── config_bybit_unified.yaml
│   ├── config_manager.py      # Менеджер конфигураций
│   ├── exchanges.yaml         # Настройки бирж
│   ├── settings.py            # Глобальные настройки
│   └── strategies.yaml        # Торговые стратегии
│
├── 📂 core/                   # Ядро системы
│   ├── __init__.py
│   ├── exchange_manager.py    # Управление биржами
│   ├── position_manager.py    # Управление позициями
│   ├── risk_manager.py        # Управление рисками
│   ├── shutdown_manager.py    # Graceful shutdown
│   └── signal_processor.py    # Обработка сигналов
│
├── 📂 database/               # База данных
│   ├── __init__.py
│   ├── create_missing_tables.py
│   ├── models.py              # Модели данных
│   └── repository.py          # Репозиторий БД
│
├── 📂 monitoring/             # Мониторинг
│   ├── __init__.py
│   ├── health_check.py        # Проверка здоровья системы
│   ├── metrics.py             # Метрики
│   ├── performance.py         # Производительность
│   └── prometheus.yml         # Конфиг Prometheus
│
├── 📂 protection/             # Защита позиций
│   ├── __init__.py
│   ├── position_guard.py      # Охрана позиций
│   ├── stop_loss_manager.py   # Управление стоп-лоссами
│   └── trailing_stop.py       # Трейлинг-стоп
│
├── 📂 scripts/                # Утилиты и скрипты
│   ├── __init__.py
│   ├── backtest.py            # Бэктестинг
│   ├── bybit_manager.py       # Управление Bybit
│   ├── cleanup.py             # Очистка
│   ├── encrypt_keys.py        # Шифрование ключей
│   ├── graceful_shutdown.py   # Мягкое завершение
│   ├── init_trading_schema.py # Инициализация БД
│   ├── pre_start_check.py     # Проверка перед запуском
│   ├── setup_ssh_tunnel.sh    # SSH туннель
│   └── trading_simulation.py  # Симуляция торговли
│
├── 📂 tests/                  # Тесты
│   ├── __init__.py
│   ├── conftest.py            # Конфигурация pytest
│   ├── test_requirements.txt
│   ├── 📂 integration/        # Интеграционные тесты
│   │   ├── test_trading_flow.py
│   │   └── test_websocket_streams.py
│   └── 📂 unit/              # Юнит-тесты
│       ├── test_performance_tracker.py
│       ├── test_position_guard.py
│       ├── test_risk_manager.py
│       └── test_stop_loss_manager.py
│
├── 📂 utils/                  # Утилиты
│   ├── __init__.py
│   ├── crypto_manager.py      # Шифрование
│   ├── decimal_utils.py       # Работа с числами
│   ├── decorators.py          # Декораторы
│   ├── logger.py              # Логирование
│   ├── process_lock.py        # Блокировка процессов
│   ├── rate_limiter.py        # Ограничение запросов
│   └── validators.py          # Валидация
│
├── 📂 websocket/              # WebSocket подключения
│   ├── __init__.py
│   ├── adaptive_stream.py     # Адаптивный поток
│   ├── base_stream.py         # Базовый класс
│   ├── binance_stream.py      # Binance WebSocket
│   ├── bybit_stream.py        # Bybit WebSocket
│   ├── event_router.py        # Маршрутизация событий
│   ├── improved_stream.py     # Улучшенный поток
│   ├── memory_manager.py      # Управление памятью
│   └── public_price_stream.py # Публичные цены
│
├── 📂 models/                 # Модели данных
│   └── validation.py          # Модели валидации
│
├── 📂 docs/                   # Документация
│   └── BYBIT_UNIFIED_SETUP.md
│
├── 📄 main.py                 # 🎯 ГЛАВНАЯ ТОЧКА ВХОДА
├── 📄 run_bot_bybit.py        # Запуск для Bybit
│
├── 🔧 Утилиты диагностики
├── cancel_duplicate_orders.py
├── check_bot_signals.py
├── check_bybit.py
├── check_bybit_detail.py
├── check_bybit_direct.py
├── check_orders.py
├── check_positions_age.py
├── clean_zombie_orders.py
├── close_all_positions.py
├── diagnose_issues.py
├── emergency_close.py
├── protect_bybit.py
├── sync_bybit_positions.py
├── sync_bybit_to_foxcrypto.py
├── test_signal_processing.py
├── test_signal_query.py
├── test_wave_detection.py
├── fix_validators.py
│
├── 📄 Конфигурационные файлы
├── .env                       # Переменные окружения
├── .env.example              # Пример переменных
├── requirements.txt          # Python зависимости
├── docker-compose.yml        # Docker конфигурация
│
├── 📄 Документация
├── README.md
├── AUDIT_REPORT.md
├── DEPLOYMENT.md
├── ENCRYPTION_GUIDE.md
├── ERROR_HANDLING_GUIDE.md
├── RATE_LIMITING_ANALYSIS.md
├── RATE_LIMITING_GUIDE.md
├── SIGNAL_WAVE_PROCESSING.md
├── USER_MANUAL.md
└── VALIDATION_GUIDE.md
```

## 🎯 Точки входа

### Основная точка входа
- **main.py** - главный файл запуска бота
  - Параметры: `--mode production/test`
  - Инициализирует все компоненты
  - Запускает event loop

### Альтернативные точки входа
- **run_bot_bybit.py** - специализированный запуск для Bybit

### Команды запуска
```bash
# Production mode
python main.py --mode production

# Test mode
python main.py --mode test

# Bybit specific
python run_bot_bybit.py
```

## 📊 Основные компоненты

### Core (Ядро)
1. **exchange_manager.py** - Управление подключениями к биржам
2. **position_manager.py** - Открытие/закрытие позиций
3. **signal_processor.py** - Обработка торговых сигналов
4. **risk_manager.py** - Контроль рисков
5. **shutdown_manager.py** - Безопасное завершение

### Protection (Защита)
1. **stop_loss_manager.py** - Автоматические стоп-лоссы
2. **position_guard.py** - Мониторинг позиций
3. **trailing_stop.py** - Динамические стоп-лоссы

### WebSocket
1. **binance_stream.py** - Реальное время от Binance
2. **bybit_stream.py** - Реальное время от Bybit
3. **adaptive_stream.py** - Адаптивная обработка потоков

## 🔄 Поток данных

```
Сигналы из БД → signal_processor
                    ↓
              position_manager
                    ↓
            exchange_manager → Биржа
                    ↓
              risk_manager
                    ↓
           stop_loss_manager
                    ↓
            База данных (repository)
```

## 🗄️ База данных

- **PostgreSQL** (fox_crypto)
- Схема: `trading_bot`
- Основные таблицы:
  - positions
  - orders
  - trades
  - signals

## ⚙️ Конфигурация

- **config/settings.py** - глобальные настройки
- **config/strategies.yaml** - торговые стратегии
- **config/exchanges.yaml** - настройки бирж
- **.env** - секретные ключи API

## 🔐 Безопасность

- **utils/crypto_manager.py** - шифрование ключей
- **scripts/encrypt_keys.py** - утилита шифрования
- **utils/validators.py** - валидация входных данных

## 📈 Мониторинг

- **monitoring/health_check.py** - статус системы
- **monitoring/metrics.py** - сбор метрик
- **monitoring/performance.py** - производительность
- Prometheus интеграция

## 🧪 Тестирование

- **tests/unit/** - юнит-тесты
- **tests/integration/** - интеграционные тесты
- **scripts/trading_simulation.py** - симуляция торговли
- **scripts/backtest.py** - бэктестинг

## 🚨 Диагностика и экстренные ситуации

- **diagnose_issues.py** - полная диагностика
- **emergency_close.py** - экстренное закрытие позиций
- **clean_zombie_orders.py** - очистка зависших ордеров
- **check_positions_age.py** - проверка возраста позиций