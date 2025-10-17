# Архитектурная карта системы Trading Bot

## Структура проекта

```
TradingBot/
├── main.py                          # Точка входа, оркестрация всех компонентов
├── config/
│   └── settings.py                  # Конфигурация из .env файла
├── core/                           # Основная бизнес-логика
│   ├── exchange_manager.py         # Управление биржами через CCXT
│   ├── position_manager.py         # Управление позициями (центральный модуль)
│   ├── signal_processor_websocket.py # Обработка торговых сигналов через WebSocket
│   ├── wave_signal_processor.py    # Обработка волн (групп сигналов)
│   ├── aged_position_manager.py    # Управление устаревшими позициями
│   ├── stop_loss_manager.py        # Унифицированное управление стоп-лоссами
│   ├── binance_zombie_cleaner.py   # Очистка зомби-ордеров
│   ├── symbol_filter.py            # Фильтрация символов (стоп-лист)
│   ├── risk_manager.py             # Риск-менеджмент
│   └── event_logger.py             # Логирование событий в БД
├── protection/                      # Защитные механизмы
│   ├── trailing_stop.py            # Трейлинг стоп
│   ├── stop_loss_manager.py        # Управление стоп-лоссами
│   └── position_guard.py           # Защита позиций
├── websocket/                       # WebSocket соединения
│   ├── binance_stream.py           # Binance WebSocket
│   ├── bybit_stream.py             # Bybit WebSocket
│   ├── signal_client.py            # Клиент для получения торговых сигналов
│   ├── signal_adapter.py           # Адаптер сигналов
│   ├── event_router.py             # Роутинг событий
│   └── adaptive_stream.py          # Адаптивный стрим для testnet (REST polling)
├── database/                        # Работа с БД
│   ├── repository.py               # Основной репозиторий (PostgreSQL)
│   ├── models.py                   # SQLAlchemy модели
│   └── transactional_repository.py # Транзакционный репозиторий
├── monitoring/                      # Мониторинг и метрики
│   ├── health_check.py             # Проверка здоровья системы
│   ├── performance.py              # Отслеживание производительности
│   └── metrics.py                  # Сбор метрик
├── utils/                          # Вспомогательные утилиты
│   ├── logger.py                   # Настройка логирования
│   ├── single_instance.py          # Блокировка множественных экземпляров
│   ├── decimal_utils.py            # Работа с Decimal
│   ├── rate_limiter.py             # Rate limiting для API
│   └── validators.py               # Валидация данных
├── tests/                          # Тесты
│   ├── unit/                       # Unit тесты
│   ├── integration/                # Интеграционные тесты
│   └── critical_fixes/             # Тесты критических исправлений
├── tools/                          # Инструменты и утилиты
│   ├── diagnostics/                # Диагностические скрипты
│   ├── emergency/                  # Экстренные скрипты
│   └── maintenance/                # Обслуживание
└── logs/                           # Логи
    └── trading_bot.log             # Основной лог файл

```

## Модули и их ответственность

### Core модули

- **main.py** [/main.py] - Точка входа, инициализация всех компонентов, координация работы
- **position_manager.py** [/core/position_manager.py] - Центральный модуль управления позициями, координация между биржами и БД
- **signal_processor_websocket.py** [/core/signal_processor_websocket.py] - Получение и обработка торговых сигналов через WebSocket
- **wave_signal_processor.py** [/core/wave_signal_processor.py] - Обработка волн (групп сигналов) с проверкой лимитов
- **aged_position_manager.py** [/core/aged_position_manager.py] - Закрытие устаревших позиций по возрасту
- **exchange_manager.py** [/core/exchange_manager.py] - Обертка над CCXT для работы с биржами
- **stop_loss_manager.py** [/core/stop_loss_manager.py] - Унифицированное управление стоп-лосс ордерами
- **binance_zombie_cleaner.py** [/core/binance_zombie_cleaner.py] - Очистка зависших ордеров
- **symbol_filter.py** [/core/symbol_filter.py] - Фильтрация символов по стоп-листу

### WebSocket модули

- **binance_stream.py** [/websocket/binance_stream.py] - WebSocket подключение к Binance
- **bybit_stream.py** [/websocket/bybit_stream.py] - WebSocket подключение к Bybit
- **signal_client.py** [/websocket/signal_client.py] - Клиент для получения торговых сигналов
- **event_router.py** [/websocket/event_router.py] - Маршрутизация событий между компонентами
- **adaptive_stream.py** [/websocket/adaptive_stream.py] - Адаптивный стрим для testnet (REST polling вместо WebSocket)

### Protection модули

- **trailing_stop.py** [/protection/trailing_stop.py] - Реализация трейлинг стопа
- **stop_loss_manager.py** [/protection/stop_loss_manager.py] - Проверка и установка стоп-лосс ордеров
- **position_guard.py** [/protection/position_guard.py] - Защита позиций от незащищенного состояния

### Database модули

- **repository.py** [/database/repository.py] - Основной репозиторий для работы с PostgreSQL
- **models.py** [/database/models.py] - SQLAlchemy модели (Position, Trade, Order, Signal и др.)
- **transactional_repository.py** [/database/transactional_repository.py] - Транзакционные операции

## Граф зависимостей

```
main.py
  ├── config/settings.py
  ├── core/exchange_manager.py
  │     └── ccxt (внешняя библиотека)
  ├── core/position_manager.py
  │     ├── core/stop_loss_manager.py
  │     ├── protection/trailing_stop.py
  │     ├── database/repository.py
  │     └── websocket/event_router.py
  ├── core/signal_processor_websocket.py
  │     ├── websocket/signal_client.py
  │     ├── core/wave_signal_processor.py
  │     └── core/symbol_filter.py
  ├── core/aged_position_manager.py
  │     └── core/position_manager.py
  ├── websocket/binance_stream.py
  ├── websocket/bybit_stream.py
  ├── monitoring/health_check.py
  └── monitoring/performance.py
```

## Точки входа

- **Main:** main.py - Основная точка входа через CLI
- **WebSocket handlers:**
  - websocket/binance_stream.py - обработчики для Binance
  - websocket/bybit_stream.py - обработчики для Bybit
  - websocket/signal_client.py - обработчики торговых сигналов
- **Cron/schedulers:**
  - position_manager.start_periodic_sync() - периодическая синхронизация
  - aged_position_manager.check_and_process_aged_positions() - проверка устаревших позиций
  - _monitor_loop() и _health_check_loop() в main.py

## База данных

- **Тип:** PostgreSQL (asyncpg)
- **Конфигурация:** Из .env файла
  - Host: DB_HOST (default: localhost)
  - Port: DB_PORT (default: 5433)
  - Database: DB_NAME (default: fox_crypto)
  - User: DB_USER (default: elcrypto)

- **Схемы:**
  - monitoring - для мониторинга и отслеживания
  - trading - для торговых операций

- **Основные таблицы:**
  - **positions** - Открытые позиции
    - id, signal_id, trade_id, symbol, exchange, side, quantity, entry_price
    - stop_loss_price, stop_loss_order_id, has_stop_loss
    - trailing_activated, trailing_activation_price
    - status (OPEN/CLOSED/LIQUIDATED)
  - **trades** - Исполненные сделки
    - id, signal_id, symbol, exchange, side, order_type
    - quantity, price, executed_qty, order_id
    - status, fee, created_at
  - **orders** - Ордера на биржах
    - id, position_id, exchange, exchange_order_id
    - symbol, type, side, price, size, status
  - **signals** - Торговые сигналы (источник)
  - **event_log** - Логи системных событий

- **Критичные связи:**
  - Position -> Trade (через trade_id)
  - Position -> Order (через position_id)
  - Position -> Signal (через signal_id)

## Логирование

- **Библиотека:** Python logging (стандартная)
- **Формат:** '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
- **Обработчики:**
  - RotatingFileHandler - logs/trading_bot.log (100MB, 10 backups)
  - StreamHandler - вывод в консоль
- **Уровни:** DEBUG/INFO/WARNING/ERROR/CRITICAL
- **Дополнительно:** EventLogger для записи событий в БД (event_log таблица)

## Конфигурация из .env

Система полностью конфигурируется через .env файл:
- API ключи бирж (BINANCE_API_KEY, BYBIT_API_KEY и др.)
- Параметры торговли (POSITION_SIZE_USD, STOP_LOSS_PERCENT и др.)
- База данных (DB_HOST, DB_PORT, DB_NAME и др.)
- WebSocket настройки (SIGNAL_WS_URL и др.)
- Символы в стоп-листе (STOPLIST_SYMBOLS)
- Временные параметры волн (WAVE_CHECK_MINUTES)