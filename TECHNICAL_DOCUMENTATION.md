# ТЕХНИЧЕСКАЯ ДОКУМЕНТАЦИЯ ТОРГОВОГО БОТА

## ОГЛАВЛЕНИЕ

1. [Executive Summary](#1-executive-summary)
2. [Архитектура системы](#2-архитектура-системы)
3. [Инфраструктура и окружение](#3-инфраструктура-и-окружение)
4. [Модули системы](#4-модули-системы)
5. [Критичные механизмы](#5-критичные-механизмы)
6. [Интеграции](#6-интеграции)
7. [Потоки данных и сценарии](#7-потоки-данных-и-сценарии)
8. [Состояние и персистентность](#8-состояние-и-персистентность)
9. [Логирование и мониторинг](#9-логирование-и-мониторинг)
10. [Конфигурация](#10-конфигурация)
11. [Безопасность](#11-безопасность)
12. [Известные ограничения и особенности](#12-известные-ограничения-и-особенности)
13. [Глоссарий](#13-глоссарий)

---

## 1. EXECUTIVE SUMMARY

### Что делает бот
Автоматизированная система торговли криптовалютами на биржах **Binance** и **Bybit**, работающая на основе внешних сигналов, поступающих через WebSocket. Бот обеспечивает полный жизненный цикл позиции: от открытия по сигналу до закрытия с управлением рисками.

### Архитектурный подход
- **Монолитное приложение** с модульной структурой
- **Асинхронная архитектура** (asyncio/aiohttp)
- **Event-driven система** с WebSocket интеграцией
- **Repository pattern** для работы с БД

### Технологический стек
- **Python 3.12** - основной язык
- **PostgreSQL** - хранение данных
- **CCXT + python-binance + pybit** - интеграция с биржами
- **WebSocket** - real-time данные
- **Prometheus** - метрики
- **Pydantic** - валидация данных

### Основные модули
1. **PositionManager** (3108 строк) - управление позициями
2. **ExchangeManager** (1172 строк) - абстракция бирж
3. **SignalProcessor** (718 строк) - обработка сигналов
4. **StopLossManager** (879 строк) - управление stop-loss
5. **TrailingStop** (1021 строк) - trailing stop механизм
6. **ZombieManager** (724 строк) - очистка зомби-ордеров
7. **PositionGuard** (835 строк) - мониторинг здоровья позиций
8. **HealthChecker** (673 строк) - мониторинг системы
9. **Repository** (937 строк) - работа с БД
10. **WebSocketStreams** - real-time потоки данных

---

## 2. АРХИТЕКТУРА СИСТЕМЫ

### 2.1 Архитектурная диаграмма

```
┌────────────────────────────────────────────────────┐
│                    ENTRY POINT                      │
│               main.py (810 lines)                   │
│          • Инициализация компонентов                │
│          • Управление жизненным циклом              │
└───────────────────┬─────────────────────────────────┘
                    │
        ┌───────────┴───────────────────────┐
        │                                    │
        ▼                                    ▼
┌─────────────────────────┐    ┌─────────────────────────┐
│   SIGNAL PROCESSING     │    │   EXCHANGE LAYER        │
├─────────────────────────┤    ├─────────────────────────┤
│ WebSocketSignalProcessor│    │   ExchangeManager       │
│ • Wave detection        │    │   • CCXT abstraction    │
│ • Signal validation     │    │   • Rate limiting       │
│ • Symbol filtering      │    │   • Symbol normalization│
└──────────┬──────────────┘    └───────────┬─────────────┘
           │                                │
           └────────────┬───────────────────┘
                        ▼
          ┌─────────────────────────────┐
          │    POSITION MANAGEMENT      │
          ├─────────────────────────────┤
          │     PositionManager         │
          │ • Lifecycle management      │
          │ • Risk validation           │
          │ • Position synchronization  │
          └──────────┬──────────────────┘
                     │
     ┌───────────────┼───────────────────────┐
     │               │                        │
     ▼               ▼                        ▼
┌──────────┐  ┌──────────────┐  ┌────────────────────┐
│ ATOMIC   │  │  PROTECTION   │  │   MONITORING       │
│ CREATION │  │   SYSTEM      │  │   & HEALTH         │
├──────────┤  ├──────────────┤  ├────────────────────┤
│ Atomic   │  │ StopLoss     │  │ HealthChecker      │
│ Position │  │ TrailingStop │  │ PerformanceTracker │
│ Manager  │  │ PositionGuard│  │ MetricsCollector   │
└──────────┘  │ ZombieManager│  └────────────────────┘
              └──────────────┘
                     │
              ┌──────┴──────┐
              │             │
              ▼             ▼
     ┌────────────┐  ┌────────────┐
     │  WebSocket │  │  Database  │
     │  Streams   │  │ Repository │
     └────────────┘  └────────────┘
          │                │
          ▼                ▼
    ┌───────────────────────────┐
    │   EXTERNAL SYSTEMS        │
    │ • Binance API/WebSocket   │
    │ • Bybit API/WebSocket     │
    │ • Signal WebSocket Server │
    │ • PostgreSQL Database     │
    └───────────────────────────┘
```

### 2.2 Описание слоев архитектуры

#### Entry Layer
- **main.py** - точка входа, инициализация, orchestration
- **config/settings.py** - загрузка конфигурации из .env

#### Signal Processing Layer
- **WebSocketSignalProcessor** - обработка торговых сигналов
- **WaveSignalProcessor** - волновая логика (15-минутные свечи)
- **SymbolFilter** - фильтрация символов (stop-list)

#### Exchange Integration Layer
- **ExchangeManager** - унифицированный интерфейс к биржам
- **BinanceStream/BybitStream** - WebSocket потоки данных
- **ExchangeResponseAdapter** - нормализация ответов

#### Position Management Layer
- **PositionManager** - центральный менеджер позиций
- **AtomicPositionManager** - атомарное создание позиций
- **AgedPositionManager** - управление старыми позициями

#### Protection Layer
- **StopLossManager** - единая точка управления SL
- **SmartTrailingStopManager** - динамическая защита прибыли
- **PositionGuard** - real-time мониторинг здоровья
- **ZombieManager** - очистка зомби-ордеров

#### Monitoring Layer
- **HealthChecker** - проверка здоровья компонентов
- **PerformanceTracker** - расчет метрик производительности
- **MetricsCollector** - Prometheus метрики
- **EventLogger** - аудит всех операций

#### Data Layer
- **Repository** - PostgreSQL репозиторий
- **TransactionalRepository** - транзакционные операции
- **Models** - SQLAlchemy модели

### 2.3 Паттерны проектирования

1. **Repository Pattern** - абстракция работы с БД
2. **Strategy Pattern** - различные стратегии trailing stop
3. **Observer Pattern** - EventRouter для событий
4. **Singleton** - конфигурация, логгер
5. **Context Manager** - атомарные операции
6. **State Machine** - состояния позиций и trailing stop

### 2.4 Потоки данных (high-level)

```
Signal Flow:
WebSocket Server → SignalClient → SignalProcessor → PositionManager
    → AtomicPositionManager → ExchangeManager → Exchange API

Position Updates:
Exchange WebSocket → BinanceStream/BybitStream → EventRouter
    → PositionManager → TrailingStop/PositionGuard → Repository

Protection Flow:
Position Created → StopLossManager sets SL → TrailingStop monitors
    → PositionGuard checks health → ZombieManager cleanup
```

---

## 3. ИНФРАСТРУКТУРА И ОКРУЖЕНИЕ

### 3.1 Зависимости и библиотеки

#### Основные зависимости
- **python-binance==1.0.19** - Binance API клиент
- **ccxt==4.1.22** - универсальная библиотека для бирж
- **pybit==5.6.2** - Bybit V5 API клиент
- **asyncpg==0.29.0** - асинхронный PostgreSQL
- **aiohttp==3.9.1** - асинхронный HTTP
- **pydantic==2.5.2** - валидация данных

#### База данных
- **sqlalchemy==2.0.23** - ORM
- **alembic==1.13.0** - миграции

#### Мониторинг
- **prometheus-client==0.19.0** - метрики
- **psutil==5.9.6** - системные ресурсы

### 3.2 Конфигурация

Вся конфигурация загружается из **.env файла**:

```bash
# Exchanges
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
BINANCE_TESTNET=false

BYBIT_API_KEY=xxx
BYBIT_API_SECRET=xxx
BYBIT_TESTNET=false

# Database
DB_HOST=localhost
DB_PORT=5433
DB_NAME=fox_crypto
DB_USER=elcrypto
DB_PASSWORD=xxx
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Trading
POSITION_SIZE_USD=200
MAX_POSITIONS=10
MAX_EXPOSURE_USD=30000
STOP_LOSS_PERCENT=2.0
TRAILING_ACTIVATION_PERCENT=1.5
TRAILING_CALLBACK_PERCENT=0.5
```

### 3.3 Требования к окружению

- **Python 3.12+**
- **PostgreSQL 14+** с схемами: monitoring, fas, public
- **RAM: 2GB minimum**
- **Network: стабильное соединение для WebSocket**
- **Disk: 10GB для логов и БД**

### 3.4 Процесс запуска и остановки

#### Запуск
```bash
# Обычный запуск
python main.py --mode production

# С принудительным закрытием предыдущих экземпляров
python main.py --mode production --force

# Проверка запущенных экземпляров
python main.py --check-instances
```

#### Остановка
- **Graceful**: SIGINT (Ctrl+C) или SIGTERM
- **Force**: kill процесса через SingleInstance

---

## 4. МОДУЛИ СИСТЕМЫ

### 4.1 Position Manager

**Файл**: `core/position_manager.py` (3108 строк)

**Назначение**: Центральный координатор управления позициями

**Ключевые компоненты**:

```python
class PositionManager:
    # Основные методы
    async def open_position(request: PositionRequest) -> PositionState
    async def close_position(symbol: str, reason: str)
    async def synchronize_with_exchanges()
    async def check_positions_protection()

    # WebSocket обработчики
    async def _on_position_update(data: Dict)
    async def _on_stop_loss_triggered(data: Dict)

    # Защитные механизмы
    async def handle_real_zombies()
    async def cleanup_zombie_orders()
```

**Детальное описание работы**:

1. **Открытие позиции**:
   - Валидация риск-лимитов (max positions, max exposure)
   - Проверка существования через `_position_exists()` с блокировкой
   - Атомарное создание через `AtomicPositionManager`
   - Инициализация trailing stop
   - Сохранение в БД

2. **Синхронизация**:
   - Каждые 120 секунд полная синхронизация с биржами
   - Обработка фантомных позиций (в БД но не на бирже)
   - Обнаружение untracked позиций (на бирже но не в БД)
   - Нормализация символов для multi-exchange

3. **Защита позиций**:
   - Проверка наличия SL каждые 60 секунд
   - Обработка price drift (>2% от entry)
   - Fallback если Trailing Stop неактивен >5 минут
   - 3 попытки установки SL с экспоненциальным backoff

**Статистика**:
- positions_opened/closed
- total_pnl, win_rate
- zombie_cleanup stats

### 4.2 Exchange Manager

**Файл**: `core/exchange_manager.py` (1172 строк)

**Назначение**: Абстракция взаимодействия с биржами

**Особенности реализации**:

```python
class ExchangeManager:
    # Rate limits
    RATE_LIMITS = {
        'binance': {'orders': 50, 'weight': 1200},
        'bybit': {'orders': 10, 'weight': 120}
    }

    # Symbol normalization
    def normalize_symbol(symbol: str) -> str
    def find_exchange_symbol(normalized: str) -> str

    # Order management
    async def create_market_order(symbol, side, amount)
    async def create_stop_loss_order(symbol, side, amount, stop_price)
    async def update_stop_loss_atomic(symbol, new_sl_price, position_side)
```

**Exchange-specific реализации**:

**Binance**:
- Тип: futures
- SL: STOP_MARKET ордера с reduceOnly=True
- Обновление SL: cancel + create (оптимизировано)
- Max quantity handling: split orders

**Bybit V5**:
- Тип: UNIFIED account
- SL: trading-stop endpoint (атомарно)
- Обновление SL: прямое обновление через API
- Order cache: решение лимита 500 ордеров

### 4.3 Signal Processor

**Файл**: `core/signal_processor_websocket.py` (718 строк)

**Назначение**: Обработка торговых сигналов в реальном времени

**Wave Processing Logic**:

```python
# Временная логика волн (КРИТИЧНО - НЕ МЕНЯТЬ!)
def _calculate_expected_wave_timestamp():
    """
    Сигналы для 15-мин свечей, приходят через 5-8 минут

    0-15 минут → timestamp :45 (предыдущий час)
    16-30 минут → timestamp :00
    31-45 минут → timestamp :15
    46-59 минут → timestamp :30
    """
```

**Процесс обработки**:
1. Ожидание времени проверки (6, 20, 35, 50 минуты)
2. Расчет ожидаемого timestamp волны
3. Мониторинг появления (до 120 секунд)
4. Буферная обработка (33% сверх лимита)
5. Выполнение до достижения target

### 4.4 Stop-Loss Manager

**Файл**: `core/stop_loss_manager.py` (879 строк)

**Назначение**: Единая точка управления всеми stop-loss операциями

**Критичные методы**:

```python
class StopLossManager:
    async def has_stop_loss(symbol, position_side) -> (bool, Optional[price])
    async def set_stop_loss(symbol, side, amount, stop_price)
    async def verify_and_fix_missing_sl(position, stop_price)

    # Валидация существующих SL
    def _validate_existing_sl(existing_sl, target_sl, side, tolerance=5%)
```

**Приоритеты проверки SL**:
1. Position-attached SL (Bybit position.info.stopLoss)
2. Conditional stop orders (все биржи)

**Критичный fix**: Валидация существующих SL предотвращает использование старых SL от предыдущих позиций

### 4.5 Trailing Stop Manager

**Файл**: `protection/trailing_stop.py` (1021 строк)

**Назначение**: Динамическая защита прибыли

**State Machine**:
```
INACTIVE → WAITING → ACTIVE → TRIGGERED
         ↓         ↓
      (breakeven) (trailing)
```

**Rate Limiting (Freqtrade-inspired)**:
- Минимальный интервал: 60 секунд
- Минимальное улучшение: 0.1%
- Emergency override: 1.0% улучшение

**Persistence**: Состояние сохраняется в БД для восстановления после рестарта

### 4.6 Zombie Manager

**Файл**: `core/zombie_manager.py` (724 строк)

**Назначение**: Обнаружение и очистка зомби-ордеров

**Критерии зомби**:
1. Reduce-only ордера без позиции
2. TP/SL ордера без позиции
3. Неверный positionIdx (hedge mode)
4. Ордера, которые перевернут позицию

**Очистка**:
- Обычные ордера: cancel_order()
- Условные: cancel_order(params={'stop': True})
- TP/SL: trading-stop endpoint (Bybit)

### 4.7 Position Guard

**Файл**: `protection/position_guard.py` (835 строк)

**Назначение**: Real-time мониторинг здоровья позиций

**Health Scoring**:
```python
health = (pnl_score * 0.3) +
         (drawdown_score * 0.2) +
         (volatility_score * 0.2) +
         (time_score * 0.15) +
         (liquidity_score * 0.15)
```

**Risk Levels & Actions**:
- **LOW**: Monitor only
- **MEDIUM**: Adjust stops
- **HIGH**: Partial close
- **CRITICAL**: Full close
- **EMERGENCY**: Market exit

---

## 5. КРИТИЧНЫЕ МЕХАНИЗМЫ

### 5.1 Атомарное создание позиций

**Модуль**: `core/atomic_position_manager.py`

**Гарантии**:
1. Позиция ВСЕГДА создается со stop-loss
2. При ошибке SL позиция откатывается
3. Recovery для незавершенных операций

**Flow**:
```
PENDING_ENTRY → ENTRY_PLACED → PENDING_SL → ACTIVE
                     ↓              ↓
                  ROLLBACK    если ошибка
```

**Rollback Logic**:
- Если entry размещен но нет SL → немедленное закрытие
- Polling до 10 попыток для видимости позиции
- Emergency close при невозможности установить SL

### 5.2 Stop-Loss Price Drift Handling

**Проблема**: Цена может сильно отойти от entry до установки SL

**Решение**:
```python
if price_drift_pct > stop_loss_percent:
    base_price = current_price  # Используем текущую
else:
    base_price = entry_price    # Используем entry

stop_loss = calculate_sl(base_price, side, sl_percent)
```

### 5.3 Symbol Normalization

**Проблема**: Разные форматы символов на биржах

**Решение**:
```python
# Database → Exchange
'BLASTUSDT' → 'BLAST/USDT:USDT' (Bybit)
'BTCUSDT' → 'BTCUSDT' (Binance)

# Exchange → Database
'HIGH/USDT:USDT' → 'HIGHUSDT'
```

### 5.4 Wave Buffer Logic

**Проблема**: Не все сигналы проходят валидацию

**Решение**:
```python
max_trades = 10
buffer_percent = 33
buffer_size = 13  # 10 * 1.33

# Берем больше сигналов чем нужно
signals[:13] → validate → 8 passed
# Если мало, берем еще
signals[13:16] → validate → добавляем до 10
```

### 5.5 Aged Position Management

**Модуль**: `core/aged_position_manager.py`

**Фазы**:
1. **Grace period** (0-8ч после max_age): Попытки breakeven
2. **Progressive** (после grace): Увеличение допустимого убытка
3. **Emergency** (очень старые): Market close

**Логика**:
```python
hours_over_limit = age - max_position_age
if hours_over_limit < grace_period:
    # Breakeven attempts
    target_price = entry * (1 + commission)
else:
    # Progressive liquidation
    loss_tolerance = loss_step * hours_beyond_grace
    if hours > 10:
        loss_tolerance *= acceleration_factor
```

---

## 6. ИНТЕГРАЦИИ

### 6.1 Binance API

**Endpoints**:
- **REST API**: Orders, positions, balance
- **WebSocket**: User data stream (listen key)

**Особенности**:
- Futures account type
- STOP_MARKET для SL
- Mark price для позиций
- Weight limits: 1200/min

**WebSocket Events**:
- ACCOUNT_UPDATE: балансы и позиции
- ORDER_TRADE_UPDATE: статусы ордеров

### 6.2 Bybit API

**Version**: V5 API (UNIFIED account)

**Endpoints**:
- **trading-stop**: Атомарное управление SL/TP
- **positions**: Информация о позициях
- **orders**: Управление ордерами

**Особенности**:
- Обязательный UNIFIED account
- Position-attached SL
- 500 order limit (решено через cache)
- Custom ping каждые 20 секунд

**WebSocket Channels**:
- position: обновления позиций
- order: статусы ордеров
- execution: исполненные сделки
- wallet: балансы

### 6.3 WebSocket Streams

**Архитектура**:
```
ImprovedStream (base)
├── BinancePrivateStream
├── BybitPrivateStream
├── BybitMarketStream
└── AdaptiveStream (testnet polling)
```

**Reconnection Strategy**:
- Exponential backoff: 2^attempt секунд (max 60s)
- Immediate reconnect при health failure
- Heartbeat: 20s для Bybit, 30s для Binance

### 6.4 Signal WebSocket

**URL**: Настраивается через SIGNAL_WS_URL

**Protocol**:
1. Connect → auth_required
2. Send auth token
3. Receive auth_success
4. Request signals periodically
5. Process waves по timestamp

---

## 7. ПОТОКИ ДАННЫХ И СЦЕНАРИИ

### 7.1 Полный жизненный цикл позиции

```
1. SIGNAL ARRIVAL
   Signal WS → SignalClient → buffer

2. WAVE DETECTION
   Timer (6,20,35,50) → check timestamp → find wave

3. SIGNAL PROCESSING
   Wave signals → filter → validate → sort by score

4. POSITION OPENING
   PositionManager → AtomicPositionManager
   → Create entry order → Set stop-loss → Activate

5. MONITORING
   WebSocket updates → Update prices/PnL
   HealthChecker → Protection checks
   TrailingStop → Dynamic SL updates

6. AGING CHECK
   Every 60 min → Check age → Progressive liquidation

7. CLOSURE
   Stop triggered OR Manual close OR Aged out
   → Calculate PnL → Update stats → Cleanup
```

### 7.2 Сценарий: Нормальная работа

```python
# 1. Сигнал приходит в 00:06 для волны 23:45
signal = {
    'timestamp': '2024-01-01T23:45:00Z',
    'symbol': 'BTCUSDT',
    'side': 'BUY',
    'score_week': 85
}

# 2. Обработка сигнала
if score_week > MIN_SCORE and symbol not in STOPLIST:
    # 3. Создание позиции
    position = await open_position_atomic(
        symbol='BTCUSDT',
        side='BUY',
        quantity=0.005,
        entry_price=42000,
        stop_loss_price=41160  # -2%
    )

    # 4. Мониторинг
    # Price rises to 42630 (+1.5%)
    trailing_stop.activate()
    # Updates stop to 42417 (-0.5% from peak)

    # 5. Закрытие
    # Price drops, stop triggered at 42417
    # PnL: +$20.85 (0.99% profit)
```

### 7.3 Сценарий: Обработка ошибок

```python
# 1. Ошибка при установке SL
try:
    sl_order = await set_stop_loss()
except Exception:
    # 2. Retry логика
    for attempt in range(3):
        await asyncio.sleep(2**attempt)
        if await set_stop_loss():
            break
    else:
        # 3. Rollback
        await close_position_immediately()
        mark_as_rolled_back()
```

### 7.4 Сценарий: Восстановление после сбоя

```python
# 1. Bot restart
await recover_incomplete_positions()

# 2. Find incomplete
positions = get_positions_by_status([
    'pending_entry', 'entry_placed', 'pending_sl'
])

# 3. Recovery actions
for pos in positions:
    if status == 'entry_placed':
        # Critical - no SL!
        if not await set_stop_loss():
            await emergency_close()

    elif status == 'pending_sl':
        # Complete SL placement
        await complete_sl_placement()
```

---

## 8. СОСТОЯНИЕ И ПЕРСИСТЕНТНОСТЬ

### 8.1 Какие данные хранятся

#### В памяти (runtime)
- Активные позиции (PositionManager.positions)
- Trailing stop состояния (TrailingStopManager.instances)
- WebSocket буферы (последние 100 сообщений)
- Метрики и статистика

#### В базе данных
- Позиции (monitoring.positions)
- Ордера (monitoring.orders_cache)
- Сделки (monitoring.trades)
- Trailing stop состояния (monitoring.trailing_stop_state)
- События (monitoring.events)
- Производительность (monitoring.performance_snapshots)

### 8.2 Схема БД

```sql
-- Основные таблицы
monitoring.positions         -- Активные и закрытые позиции
monitoring.trades            -- Исполненные сделки
monitoring.orders_cache      -- Кеш ордеров (Bybit 500 limit)
monitoring.trailing_stop_state -- Состояние TS
monitoring.events            -- Аудит всех событий
monitoring.performance_snapshots -- Снимки производительности

-- Связи
positions.id → trades.position_id
positions.id → orders_cache.position_id
positions.id → trailing_stop_state.position_id
```

### 8.3 Механизмы синхронизации

1. **Startup sync**: Полная синхронизация с биржами
2. **Periodic sync**: Каждые 120 секунд
3. **WebSocket updates**: Real-time обновления
4. **Database persistence**: Немедленная запись критичных данных

### 8.4 Recovery при рестарте

1. Загрузка позиций из БД
2. Проверка на биржах (существуют ли)
3. Восстановление trailing stop состояний
4. Проверка наличия SL
5. Запуск мониторинга

---

## 9. ЛОГИРОВАНИЕ И МОНИТОРИНГ

### 9.1 Что логируется

#### INFO уровень
- Старт/стоп системы
- Открытие/закрытие позиций
- Активация trailing stop
- Успешные операции

#### WARNING уровень
- Старые позиции
- Отсутствующие SL
- Неудачные попытки (retry)
- Деградация производительности

#### ERROR уровень
- Ошибки API
- Ошибки БД
- Невозможность установить SL
- WebSocket разрывы

#### CRITICAL уровень
- Позиции без защиты
- Emergency close
- Rollback операции
- Margin call

### 9.2 Формат логов

```
2024-01-01 12:00:00 - module.name - LEVEL - message
```

Ротация: 100MB per file, 10 backups

### 9.3 Метрики (Prometheus)

**Trading метрики**:
- positions_opened_total
- positions_closed_total
- stop_losses_triggered_total
- trailing_stops_activated_total
- total_pnl_gauge
- win_rate_gauge

**System метрики**:
- websocket_messages_total
- api_calls_total
- api_latency_histogram
- db_query_duration_histogram
- health_check_status

**URL**: http://localhost:8000/metrics

### 9.4 Алертинг

События для алертов:
- CRITICAL health status
- Позиция без SL > 30 секунд
- Zombie orders > threshold
- WebSocket disconnected > 5 минут
- Emergency close triggered

---

## 10. КОНФИГУРАЦИЯ

### 10.1 Все параметры системы (.env)

```bash
# === EXCHANGES ===
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=false

BYBIT_API_KEY=
BYBIT_API_SECRET=
BYBIT_TESTNET=false

# === DATABASE ===
DB_HOST=localhost
DB_PORT=5433
DB_NAME=fox_crypto
DB_USER=elcrypto
DB_PASSWORD=
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# === TRADING PARAMETERS ===
# Position sizing
POSITION_SIZE_USD=200
MIN_POSITION_SIZE_USD=10
MAX_POSITION_SIZE_USD=5000
MAX_POSITIONS=10
MAX_EXPOSURE_USD=30000

# Risk management
STOP_LOSS_PERCENT=2.0
TRAILING_ACTIVATION_PERCENT=1.5
TRAILING_CALLBACK_PERCENT=0.5

# Trailing Stop updates
TRAILING_MIN_UPDATE_INTERVAL_SECONDS=60
TRAILING_MIN_IMPROVEMENT_PERCENT=0.1
TRAILING_ALERT_IF_UNPROTECTED_WINDOW_MS=500

# Aged positions
MAX_POSITION_AGE_HOURS=3
AGED_GRACE_PERIOD_HOURS=8
AGED_LOSS_STEP_PERCENT=0.5
AGED_MAX_LOSS_PERCENT=10.0
AGED_ACCELERATION_FACTOR=1.2
AGED_CHECK_INTERVAL_MINUTES=60
COMMISSION_PERCENT=0.1

# Signal filtering
MIN_SCORE_WEEK=0
MIN_SCORE_MONTH=50
MAX_SPREAD_PERCENT=2.0

# Wave processing
WAVE_CHECK_MINUTES=6,20,35,50
WAVE_CHECK_DURATION_SECONDS=120
MAX_TRADES_PER_15MIN=10
SIGNAL_BUFFER_PERCENT=33

# Symbol filtering
STOPLIST_SYMBOLS=SYMBOL1,SYMBOL2,SYMBOL3

# === WEBSOCKET ===
SIGNAL_WS_URL=ws://localhost:8765
SIGNAL_WS_TOKEN=
SIGNAL_WS_AUTO_RECONNECT=true
SIGNAL_WS_RECONNECT_INTERVAL=5
SIGNAL_WS_MAX_RECONNECT_ATTEMPTS=-1
SIGNAL_BUFFER_SIZE=100

# === MONITORING ===
DEBUG=false
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### 10.2 Значения по умолчанию

Все значения имеют defaults в коде, система может работать с минимальной конфигурацией (только API ключи)

### 10.3 Рекомендации по настройке

#### Production
- POSITION_SIZE_USD: 1-2% от капитала
- MAX_POSITIONS: 5-10
- STOP_LOSS_PERCENT: 1.5-3%
- MAX_POSITION_AGE_HOURS: 2-4

#### Testing
- Использовать TESTNET=true
- POSITION_SIZE_USD: минимальный
- DEBUG=true, LOG_LEVEL=DEBUG

---

## 11. БЕЗОПАСНОСТЬ

### 11.1 Хранение API ключей
- Только в .env файле
- Никогда не коммитить
- Ограниченные права (только trading)

### 11.2 Rate limiting
- Per-exchange limiters
- Automatic backoff
- Weight tracking

### 11.3 Защита от несанкционированного доступа
- SingleInstance lock
- Database user permissions
- No external API endpoints

### 11.4 Критичные проверки
- Позиция ВСЕГДА со stop-loss
- Rollback при ошибках
- Emergency close механизмы
- Duplicate position prevention

---

## 12. ИЗВЕСТНЫЕ ОГРАНИЧЕНИЯ И ОСОБЕННОСТИ

### 12.1 Ограничения текущей реализации

1. **Single instance** - только один экземпляр бота
2. **PostgreSQL only** - нет поддержки других БД
3. **Fixed wave times** - жестко заданные времена проверки
4. **No backtesting** - только live trading
5. **Limited strategies** - одна стратегия trailing stop

### 12.2 Известные баги

1. **Bybit 500 order limit** - решено через cache, но не идеально
2. **Symbol delisting** - обрабатывается, но может вызвать ошибки
3. **Time drift** - требует синхронизации времени системы

### 12.3 Особенности поведения

1. **Wave timestamp logic** - КРИТИЧНО, не менять без разрешения
2. **Bybit UNIFIED account** - обязательно для V5 API
3. **Position visibility delay** - polling до 10 попыток
4. **SL validation tolerance** - 5% для reuse проверки

---

## 13. ГЛОССАРИЙ

**Aged position** - позиция старше MAX_POSITION_AGE_HOURS

**Atomic operation** - операция, которая либо выполняется полностью, либо откатывается

**Breakeven** - безубыточная цена с учетом комиссии

**Callback percent** - расстояние trailing stop от максимума цены

**Drift** - отклонение текущей цены от цены входа

**Grace period** - период попыток закрытия по breakeven для старых позиций

**Normalized symbol** - унифицированный формат символа для БД

**Phantom position** - позиция в БД, которой нет на бирже

**Position Guard** - система мониторинга здоровья позиций

**Rate limiter** - ограничитель частоты запросов к API

**Rollback** - откат операции при ошибке

**Stop-loss (SL)** - ордер на закрытие позиции при убытке

**Trailing stop** - динамический stop-loss, следующий за ценой

**Untracked position** - позиция на бирже, которой нет в БД

**Wave** - группа сигналов с одинаковым timestamp

**WebSocket stream** - постоянное соединение для real-time данных

**Zombie order** - ордер без связанной позиции

---

## ПРИЛОЖЕНИЯ

### A. Полный список файлов с описаниями

| Файл | Строк | Назначение |
|------|-------|------------|
| main.py | 810 | Главная точка входа |
| monitor_bot.py | 880 | Альтернативный мониторинг бот |
| config/settings.py | 282 | Конфигурация из .env |
| core/position_manager.py | 3108 | Управление позициями |
| core/exchange_manager.py | 1172 | Интеграция с биржами |
| core/signal_processor_websocket.py | 718 | Обработка сигналов |
| core/stop_loss_manager.py | 879 | Управление stop-loss |
| core/atomic_position_manager.py | 610 | Атомарное создание позиций |
| core/aged_position_manager.py | ~400 | Управление старыми позициями |
| core/zombie_manager.py | 724 | Очистка зомби-ордеров |
| protection/trailing_stop.py | 1021 | Trailing stop механизм |
| protection/position_guard.py | 835 | Мониторинг здоровья |
| monitoring/health_check.py | 673 | Проверка системы |
| monitoring/performance.py | 624 | Трекинг производительности |
| monitoring/metrics.py | 617 | Prometheus метрики |
| database/repository.py | 937 | Работа с БД |
| websocket/signal_client.py | ~500 | WebSocket клиент сигналов |
| websocket/binance_stream.py | ~400 | Binance WebSocket |
| websocket/bybit_stream.py | ~350 | Bybit WebSocket |

### B. Матрица зависимостей модулей

| Модуль → | PosMan | ExMan | SigProc | SLMan | TSMan | Guard |
|----------|--------|-------|---------|-------|-------|-------|
| **PositionManager** | - | ✓ | | ✓ | ✓ | ✓ |
| **ExchangeManager** | | - | | | | |
| **SignalProcessor** | ✓ | | - | | | |
| **StopLossManager** | | ✓ | | - | | |
| **TrailingStop** | ✓ | ✓ | | ✓ | - | |
| **PositionGuard** | ✓ | ✓ | | | | - |

### C. Критичные константы

```python
# Wave timing - НЕ МЕНЯТЬ!
WAVE_CHECK_MINUTES = [6, 20, 35, 50]

# Bybit heartbeat - HARDCODED
HEARTBEAT_INTERVAL = 20  # seconds

# Position locks timeout
LOCK_TIMEOUT = 30  # seconds

# Recovery attempts
MAX_RECOVERY_ATTEMPTS = 10

# Zombie cleanup threshold
ZOMBIE_THRESHOLD = 10  # orders
```

---

**Документ подготовлен**: 2025-10-17
**Версия системы**: 2.0
**Общий объем кода**: ~15,000 строк production кода
**Модулей проанализировано**: 20+

---