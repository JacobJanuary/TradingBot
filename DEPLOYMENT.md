# 📚 Руководство по развёртыванию и эксплуатации Trading Bot

## 📋 Содержание
1. [Требования к системе](#требования-к-системе)
2. [Установка и настройка](#установка-и-настройка)
3. [Конфигурация](#конфигурация)
4. [Архитектура системы](#архитектура-системы)
5. [Описание модулей](#описание-модулей)
6. [Запуск системы](#запуск-системы)
7. [Мониторинг и управление](#мониторинг-и-управление)
8. [Обслуживание системы](#обслуживание-системы)
9. [Устранение неполадок](#устранение-неполадок)

## 🖥 Требования к системе

### Минимальные требования:
- **ОС**: Ubuntu 20.04+ / macOS 12+ / Windows 10+
- **Python**: 3.12+
- **PostgreSQL**: 14+
- **RAM**: 4GB
- **CPU**: 2 cores
- **Disk**: 20GB SSD
- **Network**: Стабильное интернет-соединение (low latency для HFT)

### Рекомендуемые требования для production:
- **ОС**: Ubuntu 22.04 LTS
- **Python**: 3.12.7
- **PostgreSQL**: 15+
- **RAM**: 16GB
- **CPU**: 8 cores
- **Disk**: 100GB SSD
- **Network**: Dedicated server с low latency (<10ms к биржам)

## 🛠 Установка и настройка

### 1. Клонирование репозитория
```bash
git clone https://github.com/your-org/TradingBot.git
cd TradingBot
```

### 2. Создание виртуального окружения
```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или
.venv\Scripts\activate  # Windows
```

### 3. Установка зависимостей
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Для разработки
```

### 4. Настройка PostgreSQL

#### Создание базы данных:
```sql
CREATE DATABASE trading_bot;
CREATE USER trading_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE trading_bot TO trading_user;

-- Создание схем
\c trading_bot;
CREATE SCHEMA IF NOT EXISTS fas;
CREATE SCHEMA IF NOT EXISTS monitoring;
GRANT ALL ON SCHEMA fas TO trading_user;
GRANT ALL ON SCHEMA monitoring TO trading_user;
```

#### Применение миграций:
```bash
alembic upgrade head
```

### 5. Настройка API ключей бирж

Создайте файл `.env` в корне проекта:
```bash
cp .env.example .env
```

Заполните API ключи:
```env
# Database
DATABASE_URL=postgresql://trading_user:password@localhost:5432/trading_bot

# Binance
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_secret_key
BINANCE_TESTNET=false

# Bybit
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_secret_key
BYBIT_TESTNET=false

# System
LOG_LEVEL=INFO
ENVIRONMENT=production
PROMETHEUS_PORT=8000
```

## ⚙️ Конфигурация

### Основной конфигурационный файл `config/config.yaml`:

```yaml
# Trading Configuration
trading:
  exchanges:
    - name: binance
      enabled: true
      markets: [BTC/USDT, ETH/USDT, BNB/USDT]
      leverage: 5
      testnet: false
    
    - name: bybit
      enabled: true
      markets: [BTC/USDT, ETH/USDT]
      leverage: 10
      testnet: false

# Risk Management
risk:
  max_position_size: 10000  # USD
  max_daily_loss: 1000      # USD
  max_open_positions: 5
  max_leverage: 10
  max_correlation: 0.7
  default_stop_loss: 2.0    # %
  risk_per_trade: 1.0       # % от капитала

# Position Protection
protection:
  max_drawdown_pct: 5.0
  critical_loss_pct: 3.0
  max_position_hours: 48
  volatility_threshold: 2.0
  correlation_threshold: 0.7
  
  stop_loss:
    enabled: true
    type: combined  # fixed, trailing, combined
    fixed_percentage: 2.0
    trailing_percentage: 1.5
    atr_multiplier: 2.5
    time_based_hours: 24

# Signal Processing
signals:
  min_score_week: 70
  min_score_month: 80
  time_window_minutes: 5
  max_signals_per_hour: 10

# Monitoring
monitoring:
  health_check_interval: 60  # seconds
  metrics_port: 8000
  alert_webhook_url: https://discord.com/api/webhooks/...
  
# Performance Tracking
performance:
  report_interval: daily
  benchmark_symbol: BTC/USDT
  save_reports: true
  report_path: ./reports

# System
system:
  auto_restart: true
  max_retries: 3
  retry_delay: 60  # seconds
  cleanup_old_data_days: 30
  backup_enabled: true
  backup_path: ./backups
```

## 🏗 Архитектура системы

```
┌─────────────────────────────────────────────────────────┐
│                     Signal Source (FAS DB)               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    Signal Processor                       │
│  • Фильтрация по score                                   │
│  • Проверка риск-менеджмента                            │
│  • Генерация ордеров                                    │
└─────────────────────┬───────────────────────────────────┘
                      │
           ┌──────────┴──────────┐
           │                     │
           ▼                     ▼
┌──────────────────┐   ┌──────────────────┐
│  Exchange Manager │   │  Position Manager │
│  • Binance       │   │  • Открытие      │
│  • Bybit         │   │  • Закрытие      │
│  • Order routing │   │  • Обновление    │
└──────────────────┘   └──────────────────┘
           │                     │
           └──────────┬──────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   Protection System                       │
├─────────────────────┬─────────────────────┬─────────────┤
│   StopLossManager   │   PositionGuard     │TrailingStop │
│   • Fixed stops     │   • Health monitor  │ • Dynamic   │
│   • ATR-based       │   • Risk assessment │ • Profit    │
│   • Time-based      │   • Auto-liquidation│   lock      │
└─────────────────────┴─────────────────────┴─────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   Monitoring System                       │
├──────────────┬──────────────┬──────────────┬────────────┤
│   Metrics    │ Health Check │ Performance  │  Alerts    │
│   Prometheus │   Endpoint   │   Tracker    │  Discord   │
└──────────────┴──────────────┴──────────────┴────────────┘
```

## 📦 Описание модулей

### Core Modules

#### 1. **SignalProcessor** (`core/signal_processor.py`)
Обрабатывает торговые сигналы от системы FAS.

**Использование:**
```python
from core.signal_processor import SignalProcessor

processor = SignalProcessor(
    exchange_manager=exchange_manager,
    risk_manager=risk_manager,
    repository=repository,
    config=config['signals']
)

# Обработка одного сигнала
result = await processor.process_signal(signal)

# Пакетная обработка
results = await processor.process_signals_batch()
```

**Функции:**
- Фильтрация сигналов по score
- Проверка риск-лимитов
- Расчёт размера позиции
- Создание ордеров на биржах

#### 2. **ExchangeManager** (`core/exchange_manager.py`)
Управляет подключениями к биржам через CCXT.

**Использование:**
```python
from core.exchange_manager import ExchangeManager

manager = ExchangeManager(config['trading']['exchanges'])
await manager.initialize()

# Создание ордера
order = await manager.create_order(
    exchange='binance',
    symbol='BTC/USDT',
    type='limit',
    side='buy',
    amount=0.1,
    price=50000
)

# Получение баланса
balance = await manager.fetch_balance('binance')

# Закрытие позиции
await manager.close_position('BTC/USDT', 'long', 0.1)
```

#### 3. **PositionManager** (`core/position_manager.py`)
Управляет жизненным циклом позиций.

**Использование:**
```python
from core.position_manager import PositionManager

pm = PositionManager(exchange_manager, repository, config)

# Открытие позиции
position = await pm.open_position(
    signal=signal,
    size=0.1,
    leverage=5
)

# Частичное закрытие (30%)
await pm.partial_close(position_id, close_percent=30)

# Полное закрытие
result = await pm.close_position(position_id)
```

#### 4. **RiskManager** (`core/risk_manager.py`)
Контролирует риски на уровне позиций и портфеля.

**Использование:**
```python
from core.risk_manager import RiskManager

rm = RiskManager(repository, config['risk'])

# Проверка возможности открытия позиции
can_open = await rm.check_position_limit('binance')

# Проверка дневного лимита убытков
within_limit = await rm.check_daily_loss_limit()

# Расчёт размера позиции
size = await rm.calculate_position_size(
    symbol='BTC/USDT',
    price=Decimal('50000'),
    stop_loss=Decimal('49000'),
    account_balance=Decimal('10000')
)

# Анализ риска портфеля
portfolio_risk = await rm.calculate_portfolio_risk()
```

### Protection Modules

#### 5. **StopLossManager** (`protection/stop_loss_manager.py`)
Управляет стоп-лоссами с различными стратегиями.

**Использование:**
```python
from protection.stop_loss_manager import StopLossManager

slm = StopLossManager(exchange_manager, repository, config['protection']['stop_loss'])

# Установка стоп-лоссов для позиции
stops = await slm.setup_stops(position)

# Обновление стопов при изменении цены
await slm.update_stops(position, new_price)

# Отмена всех стопов
await slm.cancel_position_stops(position_id)
```

**Типы стоп-лоссов:**
- **Fixed**: Фиксированный процент от входа
- **ATR-based**: На основе волатильности (ATR)
- **Time-based**: Ужесточение со временем
- **Combined**: Комбинация всех типов

#### 6. **PositionGuard** (`protection/position_guard.py`)
Продвинутая система защиты позиций.

**Использование:**
```python
from protection.position_guard import PositionGuard

guard = PositionGuard(
    exchange_manager=exchange_manager,
    risk_manager=risk_manager,
    stop_loss_manager=slm,
    trailing_stop_manager=tsm,
    repository=repository,
    event_router=router,
    config=config['protection']
)

# Начать мониторинг позиции
await guard.start_protection(position)

# Проверка здоровья всех позиций
await guard.monitor_all_positions()

# Экстренная ликвидация
await guard.emergency_liquidation(reason="Critical market event")
```

**Функции защиты:**
- Мониторинг здоровья позиций
- Автоматическое ужесточение защиты
- Частичное закрытие при росте риска
- Экстренная ликвидация

#### 7. **TrailingStopManager** (`protection/trailing_stop.py`)
Динамические трейлинг-стопы.

**Использование:**
```python
from protection.trailing_stop import TrailingStopManager

tsm = TrailingStopManager(exchange_manager, repository, config)

# Активация трейлинг-стопа
await tsm.activate_trailing_stop(
    position=position,
    trail_percent=1.5,
    activation_price=position.entry_price * 1.02
)

# Обновление при движении цены
await tsm.update_trailing_stops(position_id, new_price)
```

### WebSocket Modules

#### 8. **BinanceStream** (`websocket/binance_stream.py`)
WebSocket подключение к Binance.

**Использование:**
```python
from websocket.binance_stream import BinancePrivateStream

stream = BinancePrivateStream(config['binance'])

# Регистрация обработчиков
stream.register_callback('position', handle_position_update)
stream.register_callback('order', handle_order_update)

# Подключение и запуск
await stream.connect()
await stream.subscribe_user_data()
```

#### 9. **BybitStream** (`websocket/bybit_stream.py`)
WebSocket подключение к Bybit через CCXT Pro.

**Использование:**
```python
from websocket.bybit_stream import BybitStream

stream = BybitStream(config['bybit'])

# Подписка на рыночные данные
await stream.subscribe_orderbook('BTC/USDT')
await stream.subscribe_trades('ETH/USDT')

# Подписка на приватные данные
await stream.subscribe_positions()
await stream.subscribe_orders()
```

#### 10. **EventRouter** (`websocket/event_router.py`)
Маршрутизация событий от WebSocket.

**Использование:**
```python
from websocket.event_router import EventRouter

router = EventRouter()

# Регистрация обработчиков
@router.on('position.update')
async def handle_position(data):
    print(f"Position updated: {data}")

router.add_handler('price.update', price_handler)

# Отправка событий
await router.emit('price.update', {
    'symbol': 'BTC/USDT',
    'price': 50000
})
```

### Monitoring Modules

#### 11. **MetricsCollector** (`monitoring/metrics.py`)
Сбор метрик для Prometheus.

**Использование:**
```python
from monitoring.metrics import MetricsCollector

metrics = MetricsCollector(config['monitoring'])

# Регистрация метрик
metrics.record_trade(symbol='BTC/USDT', pnl=100)
metrics.record_signal_processed()
metrics.record_position_opened()

# Запуск HTTP сервера для Prometheus
await metrics.start_http_server(port=8000)
```

**Доступные метрики:**
- `trading_bot_trades_total` - Общее количество сделок
- `trading_bot_pnl` - P&L по позициям
- `trading_bot_positions_active` - Активные позиции
- `trading_bot_signals_processed` - Обработанные сигналы
- `trading_bot_errors_total` - Ошибки системы

#### 12. **HealthCheck** (`monitoring/health_check.py`)
Проверка здоровья системы.

**Использование:**
```python
from monitoring.health_check import HealthCheck

health = HealthCheck(
    exchange_manager=exchange_manager,
    repository=repository,
    config=config
)

# Запуск HTTP endpoint
await health.start_server(port=8080)

# Ручная проверка
status = await health.check_system_health()
```

**Endpoint:** `GET http://localhost:8080/health`

**Ответ:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "checks": {
    "database": "ok",
    "exchanges": {
      "binance": "ok",
      "bybit": "ok"
    },
    "websockets": "ok",
    "risk_limits": "ok"
  }
}
```

#### 13. **PerformanceTracker** (`monitoring/performance.py`)
Анализ эффективности торговли.

**Использование:**
```python
from monitoring.performance import PerformanceTracker

tracker = PerformanceTracker(repository, config['performance'])

# Расчёт метрик
metrics = await tracker.calculate_metrics()

# Генерация отчёта
report = await tracker.generate_report(period='daily')

# Сохранение отчёта
await tracker.save_report(report, format='json')
```

**Метрики производительности:**
- Win Rate
- Profit Factor
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown
- Calmar Ratio
- Average Win/Loss
- Recovery Factor

### Utility Modules

#### 14. **Database Repository** (`database/repository.py`)
Слой доступа к данным.

**Использование:**
```python
from database.repository import Repository

repo = Repository(db_config)
await repo.initialize()

# Получение сигналов
signals = await repo.get_unprocessed_signals(
    min_score_week=70,
    min_score_month=80
)

# Работа с позициями
positions = await repo.get_active_positions('binance')
await repo.update_position(position)

# Получение метрик
daily_pnl = await repo.get_daily_pnl()
```

#### 15. **Validators** (`utils/validators.py`)
Валидация данных.

**Использование:**
```python
from utils.validators import (
    validate_symbol,
    validate_order_type,
    validate_leverage,
    validate_price
)

# Валидация символа
is_valid = validate_symbol('BTC/USDT')

# Валидация цены
is_valid = validate_price(Decimal('50000'), symbol='BTC/USDT')
```

#### 16. **Decorators** (`utils/decorators.py`)
Полезные декораторы.

**Использование:**
```python
from utils.decorators import (
    retry_on_error,
    rate_limit,
    require_connection,
    log_execution_time
)

@retry_on_error(max_retries=3, delay=1)
async def risky_operation():
    pass

@rate_limit(calls=10, period=60)
async def api_call():
    pass
```

## 🚀 Запуск системы

### 1. Запуск в режиме разработки
```bash
python main.py --config config/config.yaml --debug
```

### 2. Запуск в production
```bash
# Использование systemd (Linux)
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl enable trading-bot
sudo systemctl start trading-bot

# Или через Docker
docker-compose up -d
```

### 3. Запуск отдельных компонентов

**Только мониторинг:**
```bash
python -m monitoring.health_check --port 8080
```

**Только WebSocket streams:**
```bash
python -m websocket.binance_stream --config config/config.yaml
```

**Бэктестинг:**
```bash
python scripts/backtest.py \
    --start-date 2024-01-01 \
    --end-date 2024-01-31 \
    --symbol BTC/USDT \
    --strategy momentum
```

### 4. Docker Compose конфигурация

```yaml
version: '3.8'

services:
  trading-bot:
    build: .
    container_name: trading-bot
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./reports:/app/reports
    ports:
      - "8000:8000"  # Prometheus metrics
      - "8080:8080"  # Health check
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:15
    container_name: trading-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=trading_bot
      - POSTGRES_USER=trading_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    container_name: trading-cache
    restart: unless-stopped
    ports:
      - "6379:6379"

  prometheus:
    image: prom/prometheus
    container_name: trading-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    container_name: trading-grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/dashboards:/etc/grafana/provisioning/dashboards
    ports:
      - "3000:3000"

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:
```

## 📊 Мониторинг и управление

### 1. Prometheus метрики
Доступны на `http://localhost:8000/metrics`

### 2. Grafana дашборды
Доступны на `http://localhost:3000`

Импортируйте дашборды из `monitoring/dashboards/`:
- `trading_overview.json` - Общий обзор
- `positions.json` - Мониторинг позиций
- `performance.json` - Анализ эффективности
- `risk.json` - Риск-метрики

### 3. Логирование

Логи сохраняются в `logs/` директории:
- `trading.log` - Основной лог
- `errors.log` - Только ошибки
- `trades.log` - Торговые операции
- `signals.log` - Обработка сигналов

Настройка логирования в `utils/logger.py`:
```python
from utils.logger import setup_logger

logger = setup_logger(
    name='trading_bot',
    level='INFO',
    log_file='logs/trading.log'
)
```

### 4. Управление через CLI

```bash
# Проверка статуса
python cli.py status

# Остановка всех позиций
python cli.py positions close-all --confirm

# Экстренная остановка
python cli.py emergency-stop --reason "Market crash"

# Просмотр активных позиций
python cli.py positions list --active

# Анализ производительности
python cli.py performance --period 30d
```

## 🔧 Обслуживание системы

### 1. Ежедневные задачи

**Автоматическая очистка старых данных:**
```bash
python scripts/cleanup.py --days 30
```

**Бэкап базы данных:**
```bash
python scripts/backup.py --destination s3://backups/
```

### 2. Еженедельные задачи

**Анализ производительности:**
```bash
python scripts/weekly_report.py --email admin@example.com
```

**Обновление зависимостей:**
```bash
pip list --outdated
pip-audit  # Проверка безопасности
```

### 3. Ежемесячные задачи

**Оптимизация базы данных:**
```sql
VACUUM ANALYZE;
REINDEX DATABASE trading_bot;
```

**Ротация логов:**
```bash
logrotate -f /etc/logrotate.d/trading-bot
```

## 🔨 Устранение неполадок

### Частые проблемы и решения

#### 1. Ошибка подключения к бирже
```
Error: Exchange connection timeout
```
**Решение:**
- Проверьте API ключи
- Проверьте IP whitelist на бирже
- Проверьте сетевое соединение
- Увеличьте timeout в конфигурации

#### 2. Превышение rate limit
```
Error: Rate limit exceeded
```
**Решение:**
- Уменьшите частоту запросов в конфигурации
- Используйте WebSocket вместо REST API
- Добавьте задержки между запросами

#### 3. Недостаточно средств
```
Error: Insufficient balance
```
**Решение:**
- Проверьте баланс на бирже
- Уменьшите размер позиций
- Проверьте настройки leverage

#### 4. Позиция не закрывается
```
Error: Failed to close position
```
**Решение:**
- Проверьте открытые ордера
- Проверьте margin mode (isolated/cross)
- Закройте вручную через биржу

### Команды диагностики

```bash
# Проверка подключений
python diagnose.py connections

# Проверка конфигурации
python diagnose.py config

# Проверка базы данных
python diagnose.py database

# Полная диагностика
python diagnose.py full --verbose
```

### Логи для отладки

Включите debug режим в `.env`:
```env
LOG_LEVEL=DEBUG
```

Или временно через CLI:
```bash
LOG_LEVEL=DEBUG python main.py
```

## 📞 Поддержка

### Контакты
- **Email**: support@tradingbot.com
- **Discord**: https://discord.gg/tradingbot
- **GitHub Issues**: https://github.com/your-org/TradingBot/issues

### Полезные ресурсы
- [CCXT Documentation](https://docs.ccxt.com)
- [Binance API Docs](https://binance-docs.github.io/apidocs)
- [Bybit API Docs](https://bybit-exchange.github.io/docs)
- [PostgreSQL Tuning](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)

## 📝 Лицензия

Proprietary Software - All rights reserved.

---

*Последнее обновление: 26.09.2024*