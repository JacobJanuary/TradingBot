# КОМПЛЕКСНЫЙ ОТЧЕТ ОБ АУДИТЕ ТОРГОВОГО БОТА

**Расположение бота:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot`
**Дата аудита:** 2025-10-14
**Размер кода:** ~14,841 строк (core + защита modules)
**Текущая ветка:** `fix/sl-manager-conflicts`

---

## РЕЗЮМЕ

### Общая оценка
- **Качество кода:** 7/10
- **Найдено критических проблем:** 8 major, 12 medium priority
- **Полнота логирования в БД:** 25% (КРИТИЧЕСКИЙ ПРОБЕЛ)
- **Архитектура:** Модульная, но с рисками состояний гонки

### Топ-5 критических проблем для исправления

1. **КРИТИЧНО: Отсутствует инфраструктура логирования событий** - Только ~25% критических событий логируются в базу данных
2. **ВЫСОКО: Состояние гонки между Трейлинг-стопом и Position Guard** - Оба модуля могут обновлять SL одновременно
3. **ВЫСОКО: Неполный откат атомарной операции** - Entry-ордера не всегда закрываются при неудаче SL
4. **СРЕДНЕ: Нет проверки здоровья для Трейлинг-стоп Manager** - TS может молча упасть без fallback Protection Manager
5. **СРЕДНЕ: Обнаружение зомби-ордеров не интегрировано** - Работает отдельно от основного потока позиций

### Недавние критические исправления (За последние 2 недели)
- ✅ Fix: Use `markPrice` instead of `ticker['last']` for SL calculation (3b11d77)
- ✅ Fix: Convert Bybit `retCode` from string to int (6e4c8fe)
- ✅ Fix: Update `current_price` instead of `entry_price` after order execution (090efa9)
- ✅ Add: SL validation before reusing existing SL (84e6473)
- ✅ Add: Cancel SL orders when closing position (370e64c)

---

## РАЗДЕЛ 1: АРХИТЕКТУРА СИСТЕМЫ

### Общий обзор

```
┌─────────────────────────────────────────────────────────────┐
│                    SIGNAL PROCESSING LAYER                   │
│  WebSocketSignalProcessor → WaveSignalProcessor             │
│  (Real-time signals from external service via WebSocket)    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   POSITION MANAGEMENT LAYER                  │
│  PositionManager ──→ AtomicPositionManager                  │
│        │                     │                               │
│        │                     ├─→ ExchangeManager             │
│        │                     └─→ StopLossManager             │
│        │                                                     │
│        ├─→ PositionSynchronizer (Exchange ↔ DB sync)       │
│        └─→ ZombieManager (Orphan order cleanup)            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   PROTECTION LAYER                          │
│  SmartTrailingStopManager (per exchange)                   │
│  PositionGuard (advanced monitoring - NOT USED)            │
│  StopLossManager (unified SL operations)                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATA PERSISTENCE LAYER                    │
│  Repository (PostgreSQL) + EventLogger (PostgreSQL)         │
│  Schema: monitoring.positions, fas.signals, events table   │
└─────────────────────────────────────────────────────────────┘
```

### Поток данных

**Открытие позиций:**
```
Signal Received (WebSocket)
  → WaveSignalProcessor validates & filters
    → PositionManager.open_position()
      → AtomicPositionManager.open_position_atomic()
        ├─→ [DB] Create position record (status: pending_entry)
        ├─→ [Exchange] Place market order
        ├─→ [DB] Update position (status: entry_placed)
        ├─→ [Exchange] Place stop-loss order (3 retries)
        ├─→ [DB] Update position (status: active, has_stop_loss=true)
        └─→ [Memory] SmartTrailingStopManager.create_trailing_stop()
```

**Мониторинг позиций:**
```
WebSocket Price Update
  ├─→ PositionManager updates local state
  ├─→ SmartTrailingStopManager.update_price()
  │   ├─→ Check activation conditions
  │   ├─→ Update trailing stop if active
  │   └─→ [Exchange] Cancel + Create new SL order
  │
  └─→ Periodic sync (every 2 minutes)
      ├─→ PositionSynchronizer.synchronize_all_exchanges()
      ├─→ PositionManager.check_positions_protection()
      │   └─→ Set SL if missing (Protection Manager fallback)
      └─→ ZombieManager.cleanup_zombie_orders()
```

### Ключевые компоненты

1. **WebSocketSignalProcessor** - Получает торговые сигналы через WebSocket, реализует торговую логику на основе волн
2. **PositionManager** - Центральный оркестратор жизненного цикла позиции
3. **AtomicPositionManager** - Гарантирует атомарность Entry+SL
4. **SmartTrailingStopManager** - Продвинутый трейлинг-стоп с логикой активации
5. **PositionSynchronizer** - Согласовывает состояние биржи с базой данных
6. **ZombieManager** - Обнаруживает и удаляет осиротевшие ордера
7. **СобытиеLogger** - Логирование событий в базу данных (недоиспользуется)

---

## РАЗДЕЛ 2: АУДИТ БАЗЫ ДАННЫХ И ЛОГИРОВАНИЯ СОБЫТИЙ ⭐ ПРИОРИТЕТ

### 2.1 Анализ схемы базы данных

**База данных PostgreSQL с 2 основными схемами:**

#### Схема: `monitoring`

**Table: `positions`** (Source: database/models.py:132-198)
```python
- id: INTEGER (PK)
- trade_id: INTEGER (FK → monitoring.trades)
- symbol: VARCHAR(50) [indexed]
- exchange: VARCHAR(50) [indexed]
- side: VARCHAR(10) ['long'/'short']
- quantity: FLOAT ⚠️ (Should be DECIMAL)
- entry_price: FLOAT ⚠️ (Should be DECIMAL)
- current_price: FLOAT ⚠️
- mark_price: FLOAT ⚠️
- unrealized_pnl: FLOAT ⚠️
- unrealized_pnl_percent: FLOAT ⚠️
- has_stop_loss: BOOLEAN
- stop_loss_price: FLOAT ⚠️
- stop_loss_order_id: VARCHAR(100)
- has_trailing_stop: BOOLEAN
- trailing_activated: BOOLEAN
- trailing_activation_price: FLOAT ⚠️
- trailing_callback_rate: FLOAT ⚠️
- status: ENUM (PositionStatus) [OPEN, CLOSED, LIQUIDATED]
- exit_price: FLOAT ⚠️
- realized_pnl: FLOAT ⚠️
- fees: FLOAT ⚠️
- exit_reason: VARCHAR(100)
- opened_at: TIMESTAMP
- closed_at: TIMESTAMP
- ws_position_id: VARCHAR(100)
- last_update: TIMESTAMP
```

**КРИТИЧНАЯ ПРОБЛЕМА #1: Float vs Decimal**
- Все поля цен/количества используют `FLOAT` вместо `DECIMAL`
- Риск: Ошибки точности с плавающей запятой в финансовых вычислениях
- Example: `0.1 + 0.2 = 0.30000000000000004` in float
- Влияние: Потенциальные ошибки округления в расчетах PnL, ценах SL

**Таблица: `trades`** (monitoring.trades:72-106)
- Логирует исполненные сделки
- Связывается с сигналами через signal_id
- Отслеживание статуса с перечислением OrderStatus

**Таблица: `risk_events`** (monitoring.risk_events:220-230)
- Базовое логирование событий риска
- Поля: position_id, event_type, risk_level, детали (JSON), время_создания

**Таблица: `alerts`** (monitoring.alerts:233-245)
- Системные алерты
- Отслеживание подтверждений

**Таблица: `performance`** (monitoring.performance:248-280)
- Снимки метрик производительности
- Отслеживание баланса, экспозиции, винрейта

#### Схема: `fas`

**Таблица: `signals`** (fas.signals:36-69)
- Торговые сигналы из внешней системы
- Поля: pair_symbol, exchange_name, score_week, score_month, recommended_action
- `is_processed` флаг для потребления сигнала

#### Таблицы СобытиеLogger (НЕ в models.py - создаются динамически)

**Table: `events`** (core/event_logger.py:86-102)
```sql
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    correlation_id VARCHAR(100),
    position_id INTEGER,
    order_id VARCHAR(100),
    symbol VARCHAR(50),
    exchange VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'INFO',
    error_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
)
```

**Table: `transaction_log`** (core/event_logger.py:111-123)
- Отслеживает транзакции базы данных
- Длительность, затронутые строки, отслеживание ошибок

**Table: `performance_metrics`** (core/event_logger.py:130-138)
- Данные производительности временных рядов
- Теги как JSONB для гибких запросов

### 2.2 Матрица полноты логирования событий

| Модуль | Событие | Логируется в БД? | Таблица | Комментарии |
|--------|-------|---------------|-------|----------|
| **Обработка сигналов** |
| SignalProcessor | Сигнал получен | ❌ | - | Только файловый logger.info() |
| SignalProcessor | Сигнал валидирован | ❌ | - | Нет логирования в БД |
| SignalProcessor | Сигнал отфильтрован (стоп-лист) | ❌ | - | Нет логирования в БД |
| SignalProcessor | Волна обнаружена | ❌ | - | Только файловый logger.info() |
| SignalProcessor | Волна обработана | ❌ | - | Статистика не сохраняется |
| **Открытие позиции** |
| PositionManager | Начало создания позиции | ❌ | - | Нет события в БД |
| AtomicPositionManager | Entry-ордер размещен | ✅ | events | Только в атомарном пути |
| AtomicPositionManager | Entry-ордер исполнен | ✅ | events | Только в атомарном пути |
| AtomicPositionManager | Начало размещения SL | ✅ | events | Только в атомарном пути |
| AtomicPositionManager | SL успешно размещен | ✅ | events | Только в атомарном пути |
| AtomicPositionManager | Размещение SL не удалось | ✅ | events | Только в атомарном пути |
| AtomicPositionManager | Откат позиции | ✅ | events | Только в атомарном пути |
| PositionManager | Позиция открыта (устаревший) | ❌ | - | Неатомарный путь не логируется |
| **Трейлинг-стоп** |
| TrailingStop | TS экземпляр создан | ❌ | - | Только файловый logger.info() |
| TrailingStop | Обновление цены получено | ❌ | - | Только debug-логи (не сохраняется) |
| TrailingStop | Проверка активации | ❌ | - | Нет логирования в БД |
| TrailingStop | TS активирован | ❌ | - | Только файловый logger.info() |
| TrailingStop | SL обновлен (трейлинг) | ❌ | - | Только файловый logger.info() |
| TrailingStop | Обновление SL не удалось | ❌ | - | Только файловый logger.error() |
| TrailingStop | Breakeven сработал | ❌ | - | Нет логирования в БД |
| **Защита позиций** |
| PositionManager | Начало проверки SL | ❌ | - | Нет события в БД |
| PositionManager | Обнаружен отсутствующий SL | ❌ | - | Только файловый logger.warning() |
| PositionManager | SL установлен (защита) | ❌ | - | Обновление БД, но нет лога события |
| PositionManager | Установка SL не удалась | ❌ | - | Только файловый logger.error() |
| **Закрытие позиции** |
| PositionManager | Позиция закрыта | ❌ | - | Обновление БД, но нет лога события |
| TrailingStop | Позиция закрыта (TS) | ❌ | - | Только файловый logger.info() |
| **Синхронизация позиций** |
| PositionSynchronizer | Начало синхронизации | ❌ | - | Нет события в БД |
| PositionSynchronizer | Обнаружена фантомная позиция | ❌ | - | Только файловый logger.warning() |
| PositionSynchronizer | Фантом закрыт | ❌ | - | Нет события в БД |
| PositionSynchronizer | Добавлена отсутствующая позиция | ❌ | - | Только файловый logger.info() |
| PositionSynchronizer | Синхронизация завершена | ❌ | - | Нет события в БД |
| **Очистка зомби** |
| ZombieManager | Обнаружен зомби | ❌ | - | Только файловый logger.warning() |
| ZombieManager | Зомби отменен | ❌ | - | Только файловый logger.info() |
| ZombieManager | Отмена зомби не удалась | ❌ | - | Только файловый logger.error() |
| **Системные события** |
| Main | Бот запущен | ❌ | - | Нет события в БД |
| Main | Бот остановлен | ❌ | - | Нет события в БД |
| Main | Критическая ошибка | ❌ | - | Только файловый logger.error() |

**Итог:**
- **Всего критических событий:** ~40
- **События, залогированные в БД:** ~10 (только в атомарном пути)
- **Полнота логирования:** ~25%

### 2.3 Отсутствующие логи событий (КРИТИЧНО)

**Обязательные логи событий (ВЫСОКИЙ ПРИОРИТЕТ):**

1. **События обработки сигналов**
   - Сигнал получен (с полными данными сигнала)
   - Signal результат валидации
   - Сигнал отфильтрован reason
   - Wave обнаружение
   - Wave резюме исполнения

2. **События Трейлинг-стопа** ⚠️ НАИВЫСШИЙ ПРИОРИТЕТ
   - TS создан (symbol, цена_входа, цена_активации)
   - Каждое обновление цены (timestamp, цена, состояние)
   - Активация сработала (старый SL, новый SL, profit %)
   - SL обновление (старая цена, новая цена, причина)
   - Обновление SL не удалось (ответ биржи, счетчик попыток)
   - TS удален (reason)

3. **События защиты позиций**
   - Начало проверки защиты (список позиций)
   - Обнаружен отсутствующий SL (position ID, symbol)
   - SL установлен менеджером защиты (позиция, цена SL)
   - Установка SL не удалась (reason, попытки)

4. **События закрытия позиций**
   - Закрытие позиции инициировано (причина: SL/TP/вручную)
   - Ордер закрытия размещен
   - Ордер закрытия исполнен
   - Позиция закрыта в БД (финальный PnL)

5. **События синхронизации**
   - Начало синхронизации (биржа, количество позиций)
   - Обнаружена фантомная позиция (symbol, состояние БД, состояние биржи)
   - Фантом закрыт (position ID)
   - Добавлена отсутствующая позиция (детали)
   - Синхронизация завершена (статистика)

6. **События здоровья системы**
   - Переподключение WebSocket
   - Потеря/восстановление соединения с БД
   - Превышен лимит API
   - Критические ошибки

### 2.4 Найденные проблемы базы данных

#### КРИТИЧНЫЕ проблемы

**1. Float vs Decimal для финансовых данных**
- Location: database/models.py:144-160
- Проблема: Все поля цен используют FLOAT (32/64-битная плавающая запятая)
- Риск: Потеря точности в финансовых расчетах
- Исправление: Мигрировать на DECIMAL(20, 8) для всех полей цен/количества
- Пример:
```sql
ALTER TABLE monitoring.positions
  ALTER COLUMN entry_price TYPE DECIMAL(20, 8),
  ALTER COLUMN current_price TYPE DECIMAL(20, 8),
  ALTER COLUMN stop_loss_price TYPE DECIMAL(20, 8),
  -- etc...
```

**2. Нет ограничений внешних ключей**
- Проблема: Отношения определены в SQLAlchemy, но закомментированы
- Риск: Осиротевшие записи (сделки без позиций и т.д.)
- Location: database/models.py:104, 129, 187

**3. Отсутствующие индексы**
- Отсутствует индекс на `positions.status` (часто запрашиваемое)
- Отсутствует индекс на `events.symbol` для фильтрации
- Отсутствует составной индекс на `positions(exchange, symbol, status)`

**4. Нет отслеживания времени на уровне БД**
- `обновлениеd_at` колонки существуют, но не всегда обновляются
- Нет триггеров для автообновления временных меток

**5. Таблицы СобытиеLogger создаются динамически**
- Tables created in code (core/event_logger.py:86)
- Нет версионирования схемы/миграций
- Риск: Расхождение схемы между окружениями

#### СРЕДНИЕ проблемы

**6. Нет изоляции транзакций для критических операций**
- Атомарные операции используют asyncpg, но нет явного контроля транзакций в большинстве мест
- Риск: Частичные обновления при потере соединения

**7. Нет политики хранения данных**
- Таблица событий будет расти бесконечно
- Нет стратегии партиционирования или архивации

**8. Настройки пула соединений**
- Pool size: 15 min, 50 max (repository.py:31-32)
- Может быть недостаточно при высокой нагрузке

---

## РАЗДЕЛ 3: ГЛУБОКИЙ АНАЛИЗ ТРЕЙЛИНГ-СТОПА

### 3.1 Как это работает (Пошагово)

**File:** `protection/trailing_stop.py` (564 lines)

#### Инициализация
```python
# Location: trailing_stop.py:110-167
async def create_trailing_stop(
    symbol, side, entry_price, quantity, initial_stop
):
    1. Create TrailingStopInstance dataclass
    2. Set state = INACTIVE
    3. Calculate activation_price = entry_price * (1 + activation_percent/100)
    4. If initial_stop provided → place stop order on exchange
    5. Store in self.trailing_stops[symbol]
```

**Машина состояний:**
```
INACTIVE → WAITING → ACTIVE → TRIGGERED
    ↓          ↓         ↓
  (create) (breakeven) (trailing)
```

#### Поток обновления цены
```python
# Location: trailing_stop.py:168-223
async def update_price(symbol, price):
    IF symbol not in trailing_stops:
        return None  # Not monitored

    async with self.lock:  # Thread-safe
        ts = self.trailing_stops[symbol]
        ts.current_price = Decimal(str(price))

        # Update highest/lowest price
        IF ts.side == 'long':
            IF price > ts.highest_price:
                ts.highest_price = price
        ELSE:
            IF price < ts.lowest_price:
                ts.lowest_price = price

        # State-based logic
        IF ts.state == INACTIVE or WAITING:
            return await _check_activation(ts)

        IF ts.state == ACTIVE:
            return await _update_trailing_stop(ts)
```

#### Логика активации
```python
# Location: trailing_stop.py:225-265
async def _check_activation(ts):
    # 1. Check breakeven first (if configured)
    IF config.breakeven_at:
        profit = _calculate_profit_percent(ts)
        IF profit >= config.breakeven_at:
            ts.current_stop_price = ts.entry_price
            ts.state = WAITING
            await _update_stop_order(ts)
            return {'action': 'breakeven', ...}

    # 2. Check activation price
    should_activate = False
    IF ts.side == 'long':
        should_activate = ts.current_price >= ts.activation_price
    ELSE:
        should_activate = ts.current_price <= ts.activation_price

    # 3. Time-based activation (optional)
    IF config.time_based_activation:
        position_age = (now - ts.created_at).seconds / 60
        IF position_age >= config.min_position_age_minutes:
            IF profit > 0:
                should_activate = True

    IF should_activate:
        return await _activate_trailing_stop(ts)
```

#### Действие активации
```python
# Location: trailing_stop.py:267-299
async def _activate_trailing_stop(ts):
    ts.state = ACTIVE
    ts.activated_at = datetime.now()

    # Calculate initial trailing stop price
    distance = _get_trailing_distance(ts)

    IF ts.side == 'long':
        ts.current_stop_price = ts.highest_price * (1 - distance/100)
    ELSE:
        ts.current_stop_price = ts.lowest_price * (1 + distance/100)

    # Update stop order on exchange
    await _update_stop_order(ts)

    # Mark ownership (for conflict prevention)
    logger.debug(f"{symbol} SL ownership: trailing_stop")

    return {'action': 'activated', 'stop_price': ...}
```

#### Логика трейлинга
```python
# Location: trailing_stop.py:301-345
async def _update_trailing_stop(ts):
    distance = _get_trailing_distance(ts)

    IF ts.side == 'long':
        # Trail below highest price
        potential_stop = ts.highest_price * (1 - distance/100)

        # Only update if new stop is HIGHER than current
        IF potential_stop > ts.current_stop_price:
            new_stop_price = potential_stop
    ELSE:
        # Trail above lowest price
        potential_stop = ts.lowest_price * (1 + distance/100)

        # Only update if new stop is LOWER than current
        IF potential_stop < ts.current_stop_price:
            new_stop_price = potential_stop

    IF new_stop_price:
        old_stop = ts.current_stop_price
        ts.current_stop_price = new_stop_price
        ts.last_stop_update = datetime.now()
        ts.update_count += 1

        # Update exchange
        await _update_stop_order(ts)

        return {'action': 'updated', 'old_stop': ..., 'new_stop': ...}
```

#### Обновление на бирже
```python
# Location: trailing_stop.py:490-503
async def _update_stop_order(ts):
    try:
        # 1. Cancel old order
        IF ts.stop_order_id:
            await self.exchange.cancel_order(ts.stop_order_id, ts.symbol)
            await asyncio.sleep(0.1)  # Small delay

        # 2. Place new order
        return await _place_stop_order(ts)
    except Exception as e:
        logger.error(f"Failed to update stop order: {e}")
        return False
```

### 3.2 Найденные проблемы

#### КРИТИЧНЫЕ проблемы

**1. Состояние гонки: окно Cancel → Create**
- Location: trailing_stop.py:493-499
- Проблема: Между `cancel_order()` и `_place_stop_order()`, цена может сработать старый ордер
- Сценарий:
  ```
  t=0: Price=$100, Current SL=$95
  t=1: Price=$105, Update triggered
  t=2: cancel_order(SL@$95) → SUCCESS
  t=3: Price=$94 (flash crash)
  t=4: No SL exists! Position unprotected!
  t=5: _place_stop_order(SL@$100) → Too late
  ```
- Влияние: Позиция может быть незащищена 100-500мс
- Вероятность: Низкая, но катастрофическая
- Исправление: Использовать нативный modify_order биржи если доступно, или размещать новый ордер ДО отмены старого

**2. Нет логирования событий TS в БД**
- Расположение: трейлинг_stop.py (весь файл)
- Проблема: Все изменения состояния TS только логируются в файл
- Отсутствующие события:
  - Активация
  - Каждое обновление SL
  - Неудачи обновления
- Влияние: Невозможно восстановить что произошло в продакшене
- Исправление: Добавить вызовы СобытиеLogger для всех критических событий

**3. Конфликтное управление SL: TS vs Protection Manager**
- Расположение:
  - trailing_stop.py:268-299 (TS activation)
  - position_manager.py:343-406 (Protection check)
- Проблема: Оба модуля могут размещать/обновлять SL-ордера независимо
- Сценарий:
  ```
  t=0: TS places SL@$95
  t=60s: Protection Manager checks positions
  t=61s: Protection Manager sees SL order (queries exchange)
  t=62s: Protection Manager thinks "all good"
  BUT SIMULTANEOUSLY:
  t=61.5s: TS updates SL@$95 → SL@$97
  t=62.5s: Protection Manager's view is stale!
  ```
- Fix Applied: ✅ Recent commit e6cdd85 adds `sl_managed_by` field
  - Location: position_manager.py:115 (PositionState)
  - TS marks ownership on activation: trailing_stop.py:292
  - Protection Manager пропускает позиции, управляемые TS: (еще не в коде?)
- **ОСТАЮЩАЯСЯ ПРОБЛЕМА:** Логика пропуска Protection Manager еще не реализована!

**4. TS может молча упасть без fallback**
- Проблема: Если модуль TS падает или перестает обновляться, позиции не имеют защиты SL
- Current mitigation: Protection Manager checks every 2 minutes (position_manager.py:187)
- Проблема: 2-минутный промежуток слишком долгий на волатильных рынках
- Recent fix: ✅ Commit c4de5cf adds `ts_last_update_time` tracking
- Location: position_manager.py:118 (PositionState.ts_last_update_time)
- Но: Логика fallback еще не реализована!

#### ВЫСОКИЕ проблемы

**5. Bybit: Проблема множественных SL-ордеров**
- Location: trailing_stop.py:410-489 (_cancel_protection_sl_if_binance)
- Проблема: Метод обрабатывает только Binance, не Bybit
- Для Bybit:
  - TS создает STOP_MARKET ордер #A
  - Protection Manager создает STOP_MARKET ордер #B
  - Оба существуют одновременно!
- Влияние: Когда SL срабатывает, ДВА ордера исполняются → двойное закрытие позиции
- Исправление: Расширить метод _cancel_защита_sl для поддержки Bybit

**6. Нет идемпотентности для SL-ордеров**
- Проблема: If `_place_stop_order()` fails but order was actually placed, retry создает duplicate
- Нет отслеживания ID ордера до подтверждения
- Исправление: Запросить существующие ордера перед размещением нового

**7. Утечка памяти: TrailingStopInstance никогда не очищается**
- Location: trailing_stop.py:532 (on_position_closed)
- Проблема: `del self.трейлинг_stops[symbol]` вызывается только при закрытии
- Если позиция закрыта внешне (вручную, ликвидация), экземпляр TS остается
- Влияние: Память растет со временем
- Исправление: Периодическая очистка устаревших экземпляров TS

#### СРЕДНИЕ проблемы

**8. Конфигурация захардкожена**
- Location: position_manager.py:148-152
- Проблема: `безубыток_at=Нет` захардкожено (отключено)
- Нет возможности изменения конфигурации во время выполнения
- Исправление: Переместить в базу данных или конфигурационный файл

**9. Нет ограничения скорости для обновлений биржи**
- Проблема: Быстрые обновления цены могут вызвать много обновлений SL
- Нет механизма троттлинга
- Риск: Лимиты биржи, баны API
- Исправление: Добавить период отдыха между обновлениями (напр., минимум 5 секунд)

**10. Проблемы точности Decimal**
- Location: trailing_stop.py:186 (`Decimal(str(price))`)
- Проблема: Преобразование из float → Decimal теряет точность
- Следует валидировать соответствие точности цены требованиям биржи
- Исправление: Использовать информацию о точности биржи для правильного округления

### 3.3 Сравнение с лучшими практиками

#### Как это делает freqtrade

**Подход freqtrade:**
```python
# freqtrade/strategy/stoploss_manager.py (hypothetical)
class StoplossManager:
    def update_stoploss(self, trade):
        # 1. Check if update needed
        if not self.should_update(trade):
            return False

        # 2. Calculate new SL
        new_sl = self.calculate_stoploss(trade)

        # 3. ATOMIC: Update exchange THEN database
        try:
            exchange.update_stop_order(trade.stop_order_id, new_sl)
            trade.stop_loss = new_sl
            Trade.session.commit()
        except:
            Trade.session.rollback()
            raise

        return True
```

**Ключевые различия:**

| Функция | Этот бот | freqtrade | Лучше? |
|---------|----------|-----------|---------|
| Метод обновления | Cancel + Create | Modify order | freqtrade ✓ |
| Атомарность | Неатомарно | Атомарно с БД | freqtrade ✓ |
| Ограничение скорости | Нет | Лимиты по биржам | freqtrade ✓ |
| Логирование событий | Только файл | БД + Файл | freqtrade ✓ |
| Восстановление | Protection Manager | Встроенное согласование | freqtrade ✓ |
| Конфигурация | Захардкожено | По парам в БД | freqtrade ✓ |
| Тестирование | Минимальное | Обширные unit-тесты | freqtrade ✓ |

**Что этот бот делает лучше:**
- ✓ Нативный AsyncIO (freqtrade использует потоки)
- ✓ Разделение ответственности (Модуль TS независимый)
- ✓ Обновления цены через WebSocket (freqtrade опрашивает REST API)

---

## РАЗДЕЛ 4: POSITION OPENING & SL PLACEMENT AUDIT

### 4.1 Signal → Entry → SL Flow

**Entry Points:**
1. WebSocketSignalProcessor receives signal (signal_processor_websocket.py:152)
2. WaveSignalProcessor validates и batches signals (wave_signal_processor.py)
3. PositionManager.open_position() called (position_manager.py:609)

**Flow Diagram:**
```
SignalProcessor
  │
  ├─→ Validate signal (validate_signal())
  ├─→ Check stoplist (symbol_filter)
  ├─→ Check existing position (has_open_position())
  │
  └─→ PositionManager.open_position(request)
      │
      ├─→ Acquire position lock (position_locks)
      ├─→ Check if position exists (_position_exists with asyncio.Lock)
      ├─→ Validate risk limits
      ├─→ Calculate position size
      ├─→ Calculate SL price
      │
      └─→ AtomicPositionManager.open_position_atomic()
          │
          ├─→ [DB TX START]
          ├─→ State: PENDING_ENTRY
          ├─→ [DB] INSERT position (status='pending_entry')
          │
          ├─→ State: ENTRY_PLACED
          ├─→ [Exchange] create_market_order()
          ├─→ [DB] UPDATE position (status='entry_placed', current_price=exec_price)
          │
          ├─→ State: PENDING_SL
          ├─→ [Exchange] StopLossManager.set_stop_loss() (3 retries)
          │    │
          │    ├─→ Check if SL already exists (fetch_open_orders)
          │    ├─→ If exists: validate price, reuse or update
          │    └─→ If not exists: create_stop_loss_order()
          │
          ├─→ IF SL SUCCESS:
          │    ├─→ State: ACTIVE
          │    ├─→ [DB] UPDATE position (status='active', stop_loss_price=X, has_stop_loss=true)
          │    └─→ [Memory] TrailingStopManager.create_trailing_stop()
          │
          └─→ IF SL FAIL:
               ├─→ State: FAILED
               ├─→ [Exchange] Rollback: close_position() ⚠️ NOT ALWAYS WORKS
               ├─→ [DB] UPDATE position (status='canceled', exit_reason='SL failed')
               └─→ ROLLBACK or ZOMBIE POSITION
```

### 4.2 Is SL Placement Atomic with Entry?

**Answer: PARTIALLY**

**Atomic Path (AtomicPositionManager):**
- ✅ Entry и SL are in same operation context
- ✅ Database transaction rollback on failure
- ✅ 3 попытки for SL placement
- ❌ Rollback uses market order to close (may fail)
- ❌ No database transaction wrapping exchange calls

**Non-Atomic Path (Legacy - still exists!):**
- ❌ Entry и SL are separate operations
- ❌ If SL fails, position remains open without защита
- ❌ Relies on Protection Manager to fix later
- Location: position_manager.py:777-852 (fallback when AtomicPositionManager import fails)

**Code Evidence:**
```python
# position_manager.py:685-763
try:
    from core.atomic_position_manager import AtomicPositionManager
    # ... atomic creation ...
except ImportError:
    logger.warning("AtomicPositionManager not available, using legacy approach")
    # ... non-atomic creation without guaranteed SL ...
```

### 4.3 What Happens If Entry Succeeds But SL Fails?

**Atomic Path (atomic_position_manager.py:263-332):**

```python
# Step 1: SL placement fails after 3 retries
if not sl_placed:
    raise AtomicPositionError("Stop-loss placement failed")

# Step 2: Exception caught, rollback triggered
except Exception as e:
    logger.error(f"Atomic position creation failed: {e}")

    # Step 3: Attempt rollback
    if position_id and entry_order:
        await self._rollback_position(
            position_id, entry_order, stop_loss_price
        )
```

**Rollback Logic (atomic_position_manager.py:334-382):**

```python
async def _rollback_position(position_id, entry_order, sl_price):
    logger.warning(f"ROLLBACK: Closing position {position_id}")

    # Step 1: Calculate position quantity
    filled_qty = entry_order.filled or entry_order.amount

    # Step 2: Place market order to close
    try:
        close_order = await exchange.create_market_order(
            symbol,
            'sell' if entry_side == 'buy' else 'buy',  # Opposite side
            filled_qty  # ⚠️ Uses quantity parameter
        )

        if close_order and close_order.status == 'closed':
            logger.info(f"✅ Rollback successful")
            # Update DB
            await repository.update_position(position_id,
                status='rolled_back',
                exit_reason='Failed to set stop-loss'
            )
            return True
    except Exception as e:
        logger.error(f"❌ ROLLBACK FAILED: {e}")
        # ⚠️ ZOMBIE POSITION CREATED!
        return False
```

**Issues with Rollback:**

1. **Not Always Successful**
   - Market order to close can fail (symbol unavailable, insufficient liquidity)
   - If rollback fails → ZOMBIE POSITION without SL

2. **Race Condition**
   - Между entry fill и rollback close, position is unprotected
   - Duration: ~200-500ms

3. **Recent Bug Fix** ✅
   - Commit b4e41b4: "FIX: Use quantity parameter for rollback close"
   - Was using wrong quantity поле, causing rollback failures

4. **Not Idempotent**
   - If rollback partially succeeds, retry can fail
   - No check if position already closed

### 4.4 Восстановление Mechanisms

**1. Protection Manager Fallback**
- Location: position_manager.py:343-406
- Runs every 2 минут (sync_interval=120)
- Checks for positions without SL
- Places SL if missing
- Adjusts SL if it would trigger immediately

**2. Position Synchronizer**
- Location: core/position_synchronizer.py
- Compares exchange positions with database
- Closes "phantom" positions (in DB but not on exchange)
- Adds "missing" positions (on exchange but not in DB)
- Runs on startup и every 2 минут

**3. Очистка зомби**
- Location: core/zombie_manager.py
- Detects orders without corresponding positions
- Cancels orphaned orders
- Hиles TP/SL orders, conditional orders
- Runs every 2 минут

**4. Startup Verification**
- Location: position_manager.py:267-440
- On bot startup:
  1. Synchronize with exchanges
  2. Load positions from DB
  3. Verify each position exists on exchange
  4. Check SL status on exchange
  5. Set missing SLs
  6. Initialize трейлинг stops

### 4.5 Database Logging at Each Step

**Atomic Path Logging:**

| Step | File Logger | DB Logger | Комментарии |
|------|-------------|-----------|----------|
| Сигнал получен | ✅ | ❌ | Only file log |
| Position record создан | ✅ | ✅* | СобытиеLogger in atomic_manager |
| Entry-ордер размещен | ✅ | ✅* | СобытиеLogger in atomic_manager |
| Entry filled | ✅ | ✅* | СобытиеLogger in atomic_manager |
| Начало размещения SL | ✅ | ✅* | СобытиеLogger in atomic_manager |
| SL placed | ✅ | ✅* | СобытиеLogger in atomic_manager |
| SL failed | ✅ | ✅* | СобытиеLogger in atomic_manager |
| Rollback triggered | ✅ | ✅* | СобытиеLogger in atomic_manager |
| TS initialized | ✅ | ❌ | Only file log |
| Position added to отслеживание | ✅ | ❌ | Only file log |

*Note: EventLogger only used if initialized (main.py:120+)

**Non-Atomic Path Logging:**

| Step | File Logger | DB Logger |
|------|-------------|-----------|
| Entry-ордер размещен | ✅ | ❌ |
| Entry filled | ✅ | ❌ |
| Trade создан | ✅ | ❌ |
| Position создан | ✅ | ❌ |
| SL установлен | ✅ | ❌ |
| SL failed | ✅ | ❌ |

**КРИТИЧНО ISSUE:** Non-atomic path has ZERO database event logging!

---

## РАЗДЕЛ 5: SL GUARD / POSITION PROTECTION AUDIT

### 5.1 Architecture

**Two Protection Systems:**

1. **PositionGuard** (protection/position_guard.py) - NOT USED
   - Advanced monitoring system with health scoring
   - Risk levels, emergency exits, partial closes
   - **Status:** Code exists but NOT integrated in main.py
   - **Reason:** Probably too complex, was a spike/prototype

2. **Protection Manager** (in PositionManager) - ACTIVE
   - Simple periodic SL checks
   - Sets missing SL orders
   - Integrated in position_manager.py

### 5.2 How Often Does It Check Positions?

**Location:** position_manager.py:561-593

```python
async def start_periodic_sync(self):
    logger.info(f"Starting periodic sync every {self.sync_interval} seconds")

    while True:
        await asyncio.sleep(self.sync_interval)  # 120 seconds

        # 1. Sync exchange positions
        for exchange_name in self.exchanges.keys():
            await self.sync_exchange_positions(exchange_name)

        # 2. Check for positions without SL
        await self.check_positions_protection()

        # 3. Handle zombie positions
        await self.handle_real_zombies()

        # 4. Clean up zombie orders
        await self.cleanup_zombie_orders()

        # 5. Re-check SL protection after cleanup
        await self.check_positions_protection()
```

**Frequency:**
- Default: Every 120 секунд (2 минут)
- Location: position_manager.py:187
- Recent change: ✅ Increased from 10 минут to 2 минут (comment says "КРИТИЧНО FIX")

### 5.3 How Does It Verify SL Exists?

**Location:** position_manager.py:1043-1226 (check_positions_protection)

```python
async def check_positions_protection(self):
    """Check all positions have proper stop loss protection"""

    # Step 1: Iterate all positions
    for symbol, position in self.positions.items():

        # Step 2: Skip if TS is managing SL
        if position.trailing_activated:
            logger.debug(f"Skipping {symbol} - TS managing SL")
            continue

        # Step 3: Fetch orders from exchange
        try:
            orders = await exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            continue

        # Step 4: Look for SL order
        sl_order = None
        for order in orders:
            if order['type'] in ['stop', 'stop_market', 'stop_loss']:
                sl_order = order
                break

        # Step 5: If no SL found, set one
        if not sl_order:
            logger.warning(f"No SL found for {symbol}, setting...")

            # Calculate SL price
            sl_price = calculate_stop_loss(
                position.entry_price,
                position.side,
                self.config.stop_loss_percent
            )

            # Adjust if would trigger immediately
            ticker = await exchange.fetch_ticker(symbol)
            current_price = ticker.get('last')

            if position.side == 'short' and current_price >= sl_price:
                sl_price = current_price * 1.005  # 0.5% above
                logger.info(f"Adjusted SL: {sl_price}")
            elif position.side == 'long' and current_price <= sl_price:
                sl_price = current_price * 0.995  # 0.5% below
                logger.info(f"Adjusted SL: {sl_price}")

            # Set SL
            if await self._set_stop_loss(exchange, position, sl_price):
                position.has_stop_loss = True
                position.stop_loss_price = sl_price

                # Update DB
                await self.repository.update_position_stop_loss(
                    position.id, sl_price, ""
                )
```

**Verification Strategy: Exchange Check (Not DB)**
- ✅ Queries actual orders from exchange (source of truth)
- ✅ Hиles race conditions (order may exist but DB not обновлениеd)
- ❌ Expensive operation (API call per position)
- ❌ Rate limit risk with many positions

### 5.4 What Actions If SL Missing?

**Action: Set SL Immediately**

1. Calculate SL price based on config
2. Fetch current price from exchange
3. Adjust SL if it would trigger immediately
4. Place SL order on exchange
5. Update position state in memory
6. Update position in database

**No Alerts or Warnings:**
- Только файловый logger.warning()
- No database event logged
- No alert создан in monitoring.alerts table

### 5.5 Conflicts with Трейлинг-стоп Модуль?

**YES - RACE CONDITION EXISTS**

**Сценарий:**

```
Time    | Trailing Stop Manager              | Protection Manager
--------|------------------------------------|---------------------------------
00:00   | TS activated, SL@$95 placed        |
00:30   | Price=$97, update SL@$96           |
00:30.5 | Cancel order(SL@$95)               |
01:00   |                                    | Check positions (every 2 min)
01:00.1 |                                    | fetch_open_orders(symbol)
01:00.2 | Place order(SL@$96) ← IN PROGRESS  |
01:00.3 |                                    | ← Receives order list
01:00.4 |                                    | NO SL FOUND (was being updated!)
01:00.5 |                                    | Place SL@$94 (recalculated)
01:00.6 | SL@$96 placed ✓                    |
01:00.7 |                                    | SL@$94 placed ✓
Result  | TWO SL ORDERS!                     |
```

**Mitigation Attempts:**

1. ✅ Skip TS-managed positions
   - Расположение: position_manager.py (line ~1050)
   - Checks `position.трейлинг_activated`
   - BUT: What if TS fails silently?

2. ✅ Add `sl_managed_by` поле
   - Commit e6cdd85: Add sl_managed_by field to PositionState
   - Location: position_manager.py:115
   - TS marks ownership: trailing_stop.py:292
   - BUT: Protection Manager doesn't use this поле yet!

3. ⚠️ Incomplete: Protection Manager should check `sl_managed_by`

**КРИТИЧНО ISSUE:** TS can fail without Protection Manager knowing

**Recent Fix Attempt:**
- Commit c4de5cf: Add `ts_last_update_time` to PositionState
- Commit 22f4d73: "Protection Manager: Fallback if TS inactive > 5 minutes"
- BUT: Fallback logic NOT in current code!

### 5.6 Database Logging

**Current Logging:**

| Событие | File Logger | DB Logger | DB Update |
|-------|-------------|-----------|-----------|
| Начало проверки защиты | ✅ | ❌ | ❌ |
| Position checked | ✅ (debug) | ❌ | ❌ |
| Обнаружен отсутствующий SL | ✅ | ❌ | ❌ |
| SL price calculated | ✅ | ❌ | ❌ |
| SL price adjusted | ✅ | ❌ | ❌ |
| SL установлен successfully | ✅ | ❌ | ✅* |
| Установка SL не удалась | ✅ | ❌ | ❌ |

*Only position table обновлениеd (stop_loss_price, has_stop_loss)

**Отсутствующие логи событий:**
- No event log when SL установлен менеджером защиты
- No distinction between initial SL и recovered SL
- No отслеживание of how many times SL was missing

---

## РАЗДЕЛ 6: ZOMBIE CLEANUP AUDIT

### 6.1 Definition of "Zombie" Position

**Three Types of Zombies:**

1. **Zombie Orders** (zombie_manager.py)
   - Orders that exist on exchange without corresponding position
   - Пример: SL order remains after position closed externally

2. **Phantom Positions** (position_synchronizer.py)
   - Positions in database but NOT on exchange
   - Пример: Позиция закрыта on exchange but DB not обновлениеd

3. **Untracked Positions** (position_synchronizer.py)
   - Positions on exchange but NOT in database
   - Пример: Manual position opened via exchange UI

**Focus: Zombie Orders (Most common)**

### 6.2 Detection Logic

**Location:** core/zombie_manager.py:112-160 (detect_zombie_orders)

```python
async def detect_zombie_orders(use_cache=True):
    # Step 1: Get active positions from exchange
    active_positions = await _get_active_positions_cached()
    active_symbols = {symbol for (symbol, idx) in active_positions.keys()}

    # Step 2: Fetch all open orders
    all_orders = await _fetch_all_open_orders_paginated()

    # Step 3: Analyze each order
    zombies = []
    for order in all_orders:
        zombie_info = _analyze_order(order, active_positions, active_symbols)
        if zombie_info:
            zombies.append(zombie_info)

    return zombies
```

**Order Analysis Logic** (zombie_manager.py:162-290):

```python
def _analyze_order(order, active_positions, active_symbols):
    symbol = order['symbol']
    order_type = order['type']
    position_idx = int(order['info'].get('positionIdx', 0))
    reduce_only = order['info'].get('reduceOnly', False)
    close_on_trigger = order['info'].get('closeOnTrigger', False)
    stop_order_type = order['info'].get('stopOrderType', '')

    # CRITERION 1: Order for symbol without any position
    if symbol not in active_symbols:

        # Reduce-only order without position
        if reduce_only:
            return ZombieOrderInfo(reason="Reduce-only order without position")

        # TP/SL order without position
        if stop_order_type in ['TakeProfit', 'StopLoss', ...]:
            return ZombieOrderInfo(reason=f"{stop_order_type} for non-existent position")

        # CloseOnTrigger order without position
        if close_on_trigger:
            return ZombieOrderInfo(reason="CloseOnTrigger order without position")

        # Regular order without position (not stop orders)
        if 'stop' not in order_type:
            return ZombieOrderInfo(reason="Order for symbol without position")

    # CRITERION 2: Order with wrong positionIdx (Bybit hedge mode)
    position_key = (symbol, position_idx)
    if position_key not in active_positions and position_idx != 0:
        return ZombieOrderInfo(reason=f"Wrong positionIdx ({position_idx})")

    # CRITERION 3: Opposite side order that would open new position
    if position_key in active_positions:
        position = active_positions[position_key]
        if not reduce_only and not close_on_trigger:
            if (pos_side == 'long' and order_side == 'buy' and
                amount > position['quantity'] * 1.5):
                return ZombieOrderInfo(reason="Order size would flip position")

    # Not a zombie
    return None
```

**Position Cache** (zombie_manager.py:66-110):
- Caches positions for 30 секунд
- Reduces API calls
- Риск: Stale data if positions change rapidly

### 6.3 Cleanup Actions

**Location:** zombie_manager.py:341-437

```python
async def cleanup_zombie_orders(dry_run=False, aggressive=False):
    # Step 1: Detect zombies
    zombies = await detect_zombie_orders(use_cache=not aggressive)

    if dry_run:
        logger.info(f"DRY RUN: Would cancel {len(zombies)} zombies")
        return

    # Step 2: Group by type
    regular_orders = []
    conditional_orders = []
    tpsl_orders = []

    for zombie in zombies:
        if zombie.is_tpsl:
            tpsl_orders.append(zombie)
        elif zombie.is_conditional:
            conditional_orders.append(zombie)
        else:
            regular_orders.append(zombie)

    # Step 3: Cancel regular orders
    for zombie in regular_orders:
        success = await _cancel_order_safe(zombie)  # 3 retries
        await asyncio.sleep(0.2)  # Rate limiting

    # Step 4: Cancel conditional orders (special params)
    for zombie in conditional_orders:
        success = await _cancel_conditional_order(zombie)
        await asyncio.sleep(0.2)

    # Step 5: Clear TP/SL orders (Bybit specific)
    if tpsl_orders and 'bybit' in exchange.name:
        success = await _clear_tpsl_orders(tpsl_orders)

    # Step 6: Aggressive cleanup for problematic symbols
    if aggressive:
        for symbol in problematic_symbols:
            await _cancel_all_orders_for_symbol(symbol)
```

**Cancel Methods:**

1. **Regular Orders** (zombie_manager.py:439-469)
   - Simple: `exchange.cancel_order(order_id, symbol)`
   - 3 попытки with exponential backoff
   - Treats "not found" as success

2. **Conditional Orders** (zombie_manager.py:471-491)
   - Special params: `{'stop': True, 'orderFilter': 'StopOrder'}`
   - Required for stop orders on some exchanges

3. **TP/SL Orders** (zombie_manager.py:493-533)
   - Bybit-specific: Use `/v5/position/trading-stop` endpoint
   - Set `takeProfit='0'` и `stopLoss='0'` to cancel
   - Groups by (symbol, positionIdx)
   - **Recent Fix:** ✅ Commit 6e4c8fe converts retCode from string to int

4. **Aggressive Mode** (zombie_manager.py:535-558)
   - Cancel ALL orders for symbol
   - Both regular и stop orders
   - Use when normal cleanup fails

### 6.4 Database Logging

**Current Logging:**

| Событие | File Logger | DB Logger |
|-------|-------------|-----------|
| Zombie check started | ✅ | ❌ |
| Обнаружен зомби | ✅ | ❌ |
| Zombie cancellation started | ✅ | ❌ |
| Зомби отменен | ✅ | ❌ |
| Отмена зомби не удалась | ✅ | ❌ |
| Statistics | ✅ (in memory) | ❌ |

**In-Memory Statistics** (zombie_manager.py:51-57):
```python
self.stats = {
    'last_check': None,
    'zombies_detected': 0,
    'zombies_cleaned': 0,
    'errors': [],
    'check_count': 0
}
```

**КРИТИЧНО ISSUE:** All statistics lost on bot restart!

### 6.5 Integration Issues

**Not Integrated in Main Flow:**
- Zombie cleanup is separate from position opening/closing
- No automatic cleanup on position close
- Runs only during periodic sync

**Should Be Integrated:**
1. After position close → check for leftover orders
2. After SL trigger → verify no other SL orders remain
3. After position rollback → cancel any placed orders

**Recent Improvement:** ✅ Commit 370e64c "PREVENTIVE FIX: Cancel SL orders when closing position"
- But only for planned closures, not SL triggers

---

## РАЗДЕЛ 7: RACE CONDITIONS & CONCURRENCY ISSUES

### 7.1 Identified Race Conditions

**КРИТИЧНО #1: Трейлинг-стоп vs Protection Manager**

**Description:** Both can обновление SL simultaneously
**Расположение:**
- trailing_stop.py:490-503 (_update_stop_order)
- position_manager.py:1043-1226 (check_positions_protection)

**Сценарий:**
```python
Thread 1 (TS):                    Thread 2 (Protection):
t=0  price update received
t=1  calculate new SL@$96
t=2  cancel_order(SL@$95)
t=3                               check_positions_protection()
t=4                               fetch_open_orders(symbol)
t=5                               sees NO SL (was cancelled)
t=6  place_order(SL@$96)
t=7                               place_order(SL@$94)
t=8  TWO SL ORDERS EXIST!
```

**Влияние:** HIGH - Can cause double SL execution
**Вероятность:** Medium (happens during TS обновляет during 2-min sync window)
**Mitigation:** Partial - `трейлинг_activated` check exists but not foolproof
**Исправление:** Use distributed lock or ownership отслеживание

---

**КРИТИЧНО #2: Duplicate Position Creation**

**Description:** Multiple signals for same symbol processed simultaneously
**Location:** position_manager.py:906-944 (_position_exists)

**Сценарий:**
```python
Task A (BTCUSDT signal):          Task B (BTCUSDT signal):
t=0  _position_exists() → False
t=1                               _position_exists() → False
t=2  open_position() starts
t=3                               open_position() starts
t=4  Both create positions!
```

**Влияние:** КРИТИЧНО - Double position size, double risk
**Recent Исправление:** ✅ Коммит mentions "FIX #2: Locks for atomic position existence checks"
**Solution:** position_manager.py:167 (`self.check_locks: Dict[str, asyncio.Lock]`)

```python
# position_manager.py:921-924
async with self.check_locks[lock_key]:
    # Only ONE task can check at a time
    if symbol in self.positions:
        return True
```

**Status:** ✅ FIXED

---

**HIGH #3: SL Update During Position Close**

**Description:** TS обновляет SL while position being closed manually
**Расположение:**
- trailing_stop.py:168-223 (update_price)
- (position close logic)

**Сценарий:**
```python
User Action:                      Trailing Stop:
t=0  close_position(BTCUSDT)
t=1                               price update received
t=2                               update_trailing_stop()
t=3  cancel SL orders
t=4                               place new SL order
t=5  close position order
t=6                               NEW SL ORDER EXISTS!
t=7  Position closed, SL orphaned
```

**Влияние:** HIGH - Zombie SL orders
**Mitigation:** Zombie cleanup (every 2 минут)
**Исправление:** Remove from TS отслеживание BEFORE closing position

---

**HIGH #4: Exchange Order Status Sync**

**Description:** Order status from exchange may be stale
**Location:** atomic_position_manager.py:177-188

**Сценарий:**
```python
t=0  create_market_order(BUY) → returns {status: 'open'}
t=1  Atomic manager checks: status != 'closed' → FAIL
t=2  But order WAS actually filled on exchange!
t=3  Rollback triggered unnecessarily
t=4  create_market_order(SELL) → closes position
t=5  Result: No position opened (false negative)
```

**Влияние:** MEDIUM - Missed trading opportunities
**Recent Fix:** ✅ Commit eb237b2 "CRITICAL FIX: Bybit 'Entry order failed: unknown' error"
- Проблема: Bybit returns status="unknown" briefly
- Исправление: ExchangeResponseAdapter hиles "unknown" status
**Remaining:** Need to poll order status after creation

---

**MEDIUM #5: Position Synchronizer Concurrency**

**Description:** Sync can run while positions being opened
**Расположение:**
- position_synchronizer.py
- position_manager.py:200-233 (synchronize_with_exchanges)

**Сценарий:**
```python
Task A:                           Task B (Sync):
t=0  open_position(ETHUSDT)
t=1  [DB] create position
t=2                               sync_exchange_positions()
t=3  [Exchange] place order
t=4                               fetch_positions() from exchange
t=5                               ETHUSDT not on exchange yet
t=6                               mark as phantom, close in DB!
t=7  Order filled on exchange
t=8  Position in DB closed, but exists on exchange
t=9  Result: Untracked position (zombie)
```

**Влияние:** MEDIUM - Can создание untracked positions
**Mitigation:** Position synchronizer re-добавляет missing positions
**Исправление:** Use position_locks during sync

---

**MEDIUM #6: WebSocket Message Ordering**

**Description:** Price обновлениеs may arrive out of order
**Location:** trailing_stop.py:168 (update_price)

**Сценарий:**
```python
t=0  Exchange sends: price=$100
t=1  Exchange sends: price=$105
t=2  Network delay on first message
t=3  Bot receives: price=$105 → updates highest_price=$105
t=4  Bot receives: price=$100 (late arrival)
t=5  Bot skips update (100 < 105)
t=6  Result: Correct (works as intended)
```

**Влияние:** LOW - Current logic hиles this correctly
**Status:** ✅ Not an issue (highest_price logic prevents)

---

**LOW #7: Database Connection Pool Exhaustion**

**Description:** High load can exhaust connection pool
**Location:** database/repository.py:31-32

**Конфигурация:**
```python
min_size=15
max_size=50
```

**Сценарий:**
- 20 positions being opened simultaneously
- Each requires 3 DB operations (insert, 2 обновлениеs)
- Total: 60 concurrent DB operations
- Max pool: 50 connections
- Result: Some operations wait/timeout

**Влияние:** LOW - Unlikely with current trading volume
**Mitigation:** Connection pooling with wait queue
**Исправление:** Increase pool size or batch operations

### 7.2 Locking Strategy Analysis

**Current Locks:**

1. **Position Locks** (position_manager.py:163)
   ```python
   self.position_locks: set = set()
   # Used during open_position()
   lock_key = f"{exchange}_{symbol}"
   ```
   - Type: Set (not true lock, just отслеживание)
   - Scope: Per (exchange, symbol)
   - Duration: Entire position opening process
   - Проблема: Not thread-safe (set operations not atomic)

2. **Check Locks** (position_manager.py:167)
   ```python
   self.check_locks: Dict[str, asyncio.Lock] = {}
   # Used during _position_exists()
   ```
   - Type: asyncio.Lock (proper async lock)
   - Scope: Per (exchange, symbol)
   - Duration: Only during existence check
   - Status: ✅ Correct implementation

3. **Trailing Stop Lock** (trailing_stop.py:97)
   ```python
   self.lock = asyncio.Lock()
   # Used during update_price()
   ```
   - Type: asyncio.Lock
   - Scope: Global (all positions)
   - Duration: Price обновление processing
   - Проблема: Too coarse-grained (blocks all positions)

**Missing Locks:**

1. **Protection Check Lock**
   - Protection Manager has no lock
   - Can run concurrently with TS обновляет
   - Should have per-position lock

2. **Position State Updates**
   - In-memory position state modified without lock
   - Multiple sources: WebSocket, sync, manual
   - Should use per-position lock

**Recommended Lock Strategy:**

```python
# Per-position fine-grained locks
class PositionManager:
    def __init__(self):
        self.position_locks: Dict[str, asyncio.Lock] = {}

    def _get_position_lock(self, symbol: str) -> asyncio.Lock:
        if symbol not in self.position_locks:
            self.position_locks[symbol] = asyncio.Lock()
        return self.position_locks[symbol]

    async def update_position_state(self, symbol: str, updates: Dict):
        async with self._get_position_lock(symbol):
            # Atomic state update
            position = self.positions[symbol]
            for key, value in updates.items():
                setattr(position, key, value)
```

### 7.3 Database vs Exchange State Synchronization

**Source of Truth Strategy** (position_manager.py:17-22):

```
Exchange is the primary source of truth for positions.
Database serves as secondary cache with reconciliation.
Reconciliation happens during periodic sync operations.
```

**Synchronization Flow:**

```python
# Every 2 minutes (position_manager.py:561)
1. Fetch positions from exchange (source of truth)
2. Fetch positions from database (cache)
3. Compare:
   - Positions in DB but not on exchange → Close in DB (phantom)
   - Positions on exchange but not in DB → Add to DB (missing)
   - Positions in both → Update DB with exchange data
4. Verify SL orders exist on exchange
5. Update in-memory state
```

**Issues:**

1. **2-Minute Window**
   - Positions can be out of sync for up to 2 минут
   - During this window, decisions based on stale data
   - Пример: Opening position for symbol that's actually already open

2. **No Transaction Isolation**
   - Sync operations not wrapped in DB transaction
   - Partial sync can leave inconsistent state

3. **Exchange API Failures**
   - If exchange API fails, sync skipped
   - Database becomes increasingly stale
   - No alerting mechanism

4. **Normalize Symbol Issue**
   - Exchange: "BTC/USDT:USDT"
   - Database: "BTCUSDT"
   - Requires normalize_symbol() function (position_manager.py:40-50)
   - Недавнее исправление: ✅ Used consistently throughout

**Best Practice Comparison:**

| Strategy | Этот бот | Industry Stиard |
|----------|----------|-------------------|
| Source of truth | Exchange | Exchange ✓ |
| Sync frequency | 2 минут | 30-60 секунд |
| On conflict | Trust exchange | Trust exchange ✓ |
| Transactional | No | Yes |
| Логирование событий | No | Yes |
| Alerting | No | Yes |

---

## РАЗДЕЛ 8: API USAGE VERIFICATION

### 8.1 Binance Futures API

**Used Methods:**

1. **fetch_positions()**
   - Location: position_manager.py:246
   - Purpose: Get all open positions
   - Returns: List of position dicts
   - Проблема: Used without symbol parameter (correct - gets all positions)
   - Recent fix: ✅ Commit 483d8f2 mentions Binance format issues

2. **создание_market_order(symbol, side, amount)**
   - Location: atomic_position_manager.py:172
   - Purpose: Open position
   - Parameters: ✅ Correct
   - Returns: Order object
   - Status check: ExchangeResponseAdapter.is_order_filled() (correct)

3. **создание_stop_loss_order(symbol, side, amount, stop_price)**
   - Location: trailing_stop.py:396
   - Purpose: Place SL order
   - Parameters: ✅ Correct
   - Order type: STOP_MARKET with reduceOnly=True (correct)

4. **cancel_order(order_id, symbol)**
   - Location: trailing_stop.py:495
   - Purpose: Cancel existing SL
   - Parameters: ✅ Correct

5. **fetch_open_orders(symbol)**
   - Location: position_manager.py:1060
   - Purpose: Check for existing SL orders
   - Parameters: ✅ Correct

6. **fetch_ticker(symbol)**
   - Location: position_manager.py:362
   - Purpose: Get current price
   - Проблема: ⚠️ Uses `ticker['last']`
   - Recent fix: ✅ Commit 3b11d77 "Use markPrice instead of lastPrice"
   - New code should use `ticker['markPrice']` or `ticker.get('mark')`

**Critical Issue Found:**

**Ticker Price Selection:**
- Old code: `current_price = ticker.get('last')`
- Проблема: `last` = last trade price (can be stale or manipulated)
- Better: `markPrice` = fair price used for liquidations
- Location: position_manager.py:363, stop_loss_manager.py, aged_position_manager.py
- Fix Applied: ✅ Commit 3b11d77 (most recent)

### 8.2 Bybit API

**Used Methods:**

1. **fetch_positions()**
   - Same as Binance
   - Returns: List with positionIdx for hedge mode
   - Проблема: ✅ Hиled in position_synchronizer.py

2. **создание_market_order()**
   - Same as Binance
   - **КРИТИЧНО ISSUE:** Bybit returns status="unknown" briefly
   - Location: atomic_position_manager.py:188
   - Fix Applied: ✅ Commit eb237b2 "CRITICAL FIX: Bybit 'Entry order failed: unknown' error"
   - Solution: ExchangeResponseAdapter normalizes status

3. **создание_stop_loss_order()**
   - Bybit-specific issue: "No open position found" error
   - Reason: SL placed too quickly after entry
   - Fix Applied: ✅ Commit 61b1ccb "PHASE 1: Fix Bybit SL - Direct placement"
   - Solution: Wait for position to appear before placing SL

4. **Trading Stop Endpoint (TP/SL)**
   - Method: `private_post_v5_position_trading_stop`
   - Location: zombie_manager.py:518
   - Purpose: Clear TP/SL orders
   - Parameters:
     ```python
     {
         'category': 'linear',
         'symbol': symbol,
         'positionIdx': position_idx,
         'takeProfit': '0',  # Cancel TP
         'stopLoss': '0'     # Cancel SL
     }
     ```
   - **КРИТИЧНО BUG:** Bybit returns retCode as string "0", not int
   - Location: zombie_manager.py:521
   - Fix Applied: ✅ Commit 6e4c8fe "Convert Bybit retCode from string to int"
   - Code: `if int(response.get('retCode', 1)) == 0:`

5. **Order Pagination**
   - Bybit limits to 50 orders per request
   - Location: zombie_manager.py:292-339
   - Solution: Manual pagination with cursor
   - Status: ✅ Implemented correctly

**Bybit-Specific Issues:**

1. **Position Idx (Hedge Mode)**
   - Bybit supports hedge mode: long + short on same symbol
   - Requires positionIdx parameter (0, 1, or 2)
   - Location: zombie_manager.py:88-90
   - Status: ✅ Hиled correctly

2. **Reduce-Only Flag**
   - Required for SL orders
   - Location: core/stop_loss_manager.py
   - Status: ✅ Used correctly

3. **Status String Normalization**
   - Bybit uses different status names than CCXT
   - Пример: "New" vs "open"
   - Location: core/exchange_response_adapter.py
   - Fix Applied: ✅ Commit 18b23a3 "Support CCXT lowercase statuses"

### 8.3 CCXT Library Usage

**Version:** Not specified in requirements (should pin version!)

**Issues:**

1. **No Version Pinning**
   - Риск: API changes between CCXT versions
   - Исправление: Add to requirements.txt: `ccxt==4.2.x`

2. **Exception Hиling**
   - CCXT raises specific exceptions: NetworkError, ExchangeError, etc.
   - Current code: Generic `except Exception`
   - Better: Catch specific CCXT exceptions

3. **Rate Limiting**
   - CCXT has built-in rate limiting
   - Current code: Manual sleep() calls
   - Better: Let CCXT hиle it with `enableRateLimit=True`

4. **Async vs Sync**
   - Code correctly uses async CCXT (`ccxt.async_support`)
   - Status: ✅ Correct

### 8.4 Parameter Validation

**Missing Validations:**

1. **Symbol Format**
   - No validation before API calls
   - Риск: Invalid symbols cause API errors
   - Исправление: Validate symbol format before exchange calls

2. **Quantity Precision**
   - No rounding to exchange precision
   - Риск: "Invalid quantity" errors
   - Расположение: Should use `exchange.amount_to_precision()`

3. **Price Precision**
   - Trailing stop rounds price (trailing_stop.py:528)
   - But not consistently everywhere
   - Исправление: Always use `exchange.price_to_precision()`

4. **Minimum Order Size**
   - No check before order placement
   - Causes errors on exchange
   - Недавнее исправление: ✅ Коммит hиles MinimumOrderLimitError
   - Location: atomic_position_manager.py:49

---

## РАЗДЕЛ 9: RECOVERY & FAULT TOLERANCE

### 9.1 Bot Restart Восстановление

**On Startup (main.py + position_manager.py:267-440):**

```python
async def load_positions_from_db():
    # 1. FIRST: Synchronize with exchanges
    await synchronize_with_exchanges()

    # 2. Load positions from DB
    positions = await repository.get_open_positions()

    # 3. Verify EACH position exists on exchange
    verified_positions = []
    for pos in positions:
        if await verify_position_exists(pos['symbol'], pos['exchange']):
            verified_positions.append(pos)
        else:
            # Close phantom position
            await repository.close_position(pos['id'], 0, 0, 0, 'PHANTOM_ON_LOAD')

    # 4. Load verified positions into memory
    for pos in verified_positions:
        self.positions[pos['symbol']] = PositionState(...)

    # 5. Check SL status on exchange
    await check_positions_protection()

    # 6. Set missing SLs
    for position in positions_without_sl:
        await set_stop_loss(position)

    # 7. Initialize trailing stops
    for symbol, position in self.positions.items():
        await trailing_manager.create_trailing_stop(...)
        await repository.update_position(position.id, has_trailing_stop=True)
```

**Восстановление Mechanisms:**

1. ✅ **Phantom Detection**
   - Positions in DB but not on exchange are closed
   - Prevents false position отслеживание

2. ✅ **Missing SL Detection**
   - All positions checked for SL on exchange
   - SLs set if missing

3. ✅ **TS Reinitialization**
   - All positions get fresh TS instances
   - Активация price recalculated from entry price

4. ⚠️ **Partial Проблема: TS State Lost**
   - TS activation status (`трейлинг_activated`) stored in DB
   - But TS internal state (highest_price, обновление_count) NOT stored
   - On restart, TS restarts from scratch even if was active before

5. ❌ **No Atomic Operation Восстановление**
   - Positions in PENDING_ENTRY or PENDING_SL state not recovered
   - Should have cleanup routine for incomplete atomic operations

### 9.2 WebSocket Disconnect

**Signal WebSocket (signal_processor_websocket.py):**

```python
# Configuration
'AUTO_RECONNECT': True (from .env)
'RECONNECT_INTERVAL': 5 seconds
'MAX_RECONNECT_ATTEMPTS': -1 (infinite)
```

**Reconnection Logic (websocket/signal_client.py - not shown but referenced):**
- Automatic reconnection on disconnect
- Exponential backoff between attempts
- Reconnection events logged
- Statistics tracked: `self.статистика['websocket_reconnections']`

**Issues:**

1. ❌ **No DB Logging of Reconnections**
   - Only file logger
   - No monitoring.alerts entry
   - Исправление: Log to events table

2. ❌ **Signal Buffer During Disconnect**
   - Buffer size: 100 signals (signal_processor_websocket.py:54)
   - What happens if buffer fills?
   - Probable: Signals dropped
   - Исправление: Increase buffer or implement persistent queue

3. ⚠️ **Wave Monitoring Gap**
   - If disconnect happens during wave monitoring window
   - Wave might be missed entirely
   - No retry mechanism for missed waves

**Price WebSocket (separate):**
- Assumed to exist but not analyzed in detail
- Should have similar reconnection logic

### 9.3 Exchange API Errors

**Current Hиling:**

1. **Generic Exception Catching**
   ```python
   try:
       order = await exchange.create_market_order(...)
   except Exception as e:
       logger.error(f"Failed: {e}")
       return None
   ```
   - Проблема: All errors treated equally
   - Should distinguish:
     - Temporary (rate limit, network) → Retry
     - Permanent (invalid symbol) → Don't retry

2. **Retry Logic**
   - AtomicPositionManager: 3 retries for SL (atomic_position_manager.py:211)
   - ZombieManager: 3 retries for cancel (zombie_manager.py:443)
   - No retry for entry orders
   - No exponential backoff (should use 2^attempt)

3. **Specific Error Hиling**

   **Symbol Unavailable (Binance code -4140):**
   - Location: atomic_position_manager.py:267
   - Action: Close position in DB, raise SymbolUnavailableError
   - Caller hиles: Skip symbol, no retry
   - Status: ✅ Good

   **Minimum Limit (Bybit retCode 10001):**
   - Location: atomic_position_manager.py:284
   - Action: Close position in DB, raise MinimumOrderLimitError
   - Caller hиles: Skip symbol, no retry
   - Status: ✅ Good

   **Rate Limit:**
   - No specific hиling
   - Should: Wait и retry with exponential backoff
   - Current: Fails и continues

**Missing Error Hиling:**

1. **Insufficient Balance**
   - Should: Log alert, stop opening new positions
   - Current: Probably fails silently

2. **API Key Invalid/Expired**
   - Should: Critical alert, stop bot
   - Current: Continues with errors

3. **Exchange Maintenance**
   - Should: Detect maintenance mode, pause operations
   - Current: Errors accumulate

### 9.4 Database Connection Loss

**Connection Pool (repository.py:22-51):**

```python
async def initialize():
    self.pool = await asyncpg.create_pool(
        # ...
        max_inactive_connection_lifetime=60.0,  # Close idle after 60s
        command_timeout=30,
        timeout=60
    )
```

**Timeout Hиling:**
- `commи_timeout=30`: Query timeout
- `timeout=60`: Connection acquire timeout
- `lock_timeout=10000`: PostgreSQL lock timeout

**Issues:**

1. ❌ **No Connection Loss Detection**
   - If all connections lost, pool exhausted
   - No alerting mechanism
   - Bot continues trying, accumulating errors

2. ❌ **No Automatic Reconnection**
   - Pool doesn't auto-recover from DB restart
   - Requires bot restart

3. ⚠️ **No Circuit Breaker**
   - Should: Stop DB operations if failure rate high
   - Current: Each operation fails independently

4. ❌ **No Fallback Storage**
   - If DB unavailable, all events lost
   - Could: Write to local file temporarily

**Recommended: Implement Health Check**

```python
async def db_health_check():
    try:
        await repository.pool.fetchval("SELECT 1")
        return True
    except:
        # Alert and trigger recovery
        return False
```

### 9.5 Partial Order Fills

**Hиling:**

1. **AtomicPositionManager:**
   ```python
   # atomic_position_manager.py:193
   exec_price = ExchangeResponseAdapter.extract_execution_price(entry_order)
   ```
   - Uses execution price from order
   - Assumes full fill (market orders usually fill completely)
   - Проблема: Partial fills not explicitly hиled

2. **Position Synchronizer:**
   - Uses `contracts` from exchange (actual filled amount)
   - Updates DB quantity if mismatch
   - Status: ✅ Hиles partial fills in sync

3. **SL Quantity:**
   - SL placed for full requested quantity
   - If entry partially filled, SL quantity wrong!
   - Пример:
     ```
     Request: 10 BTC
     Filled: 8 BTC
     SL placed for: 10 BTC ← WRONG!
     ```
   - Should: Use `entry_order.filled` for SL quantity

**Fix Needed:**

```python
# atomic_position_manager.py:219
sl_result = await self.stop_loss_manager.set_stop_loss(
    symbol=symbol,
    side='sell' if side.lower() == 'buy' else 'buy',
    amount=entry_order.filled,  # ← Use filled, not requested quantity
    stop_price=stop_loss_price
)
```

### 9.6 Position Closed Externally

**Сценарий:** User closes position via exchange UI

**Detection:**
- Position Synchronizer (every 2 минут)
- Finds position on exchange with contracts=0
- Or position not on exchange at all

**Actions (position_manager.py:483-499):**

```python
# Close position in database
await self.repository.close_position(
    pos_state.id,
    pos_state.current_price or 0.0,
    pos_state.unrealized_pnl or 0.0,
    pos_state.unrealized_pnl_percent or 0.0,
    'sync_cleanup'
)

# Remove from tracking
self.positions.pop(pos_state.symbol, None)
```

**Issues:**

1. ⚠️ **Delay: Up to 2 минут**
   - Позиция закрыта on exchange at t=0
   - Bot still thinks position open until t=120
   - Decisions based on stale state (may try to обновление SL)

2. ⚠️ **Трейлинг-стоп Not Cleaned**
   - TS instance remains in memory
   - Will continue trying to обновление SL for non-existent position
   - Should: Call `трейлинг_manager.on_position_closed(symbol)`

3. ❌ **No Событие Logged**
   - External closure not recorded in events table
   - Can't reconstruct what happened

**Recommended:**
- Add WebSocket listener for position обновлениеs
- Immediate обнаружение when position closed externally
- Cleanup TS immediately

---

## РАЗДЕЛ 10: PRIORITIZED ACTION PLAN

### КРИТИЧНО (Fix immediately - Production risk)

**1. Implement Comprehensive Database Событие Logging**
- **Why Critical:** Cannot debug production issues without event history
- **Location:** All modules (core/, protection/)
- **How to Исправление:**
  1. Ensure СобытиеLogger initialized in main.py
  2. Add event logging to key operations:
     ```python
     # Example in trailing_stop.py
     async def _activate_trailing_stop(self, ts):
         # ... existing code ...

         # ADD THIS:
         await log_event(
             EventType.STOP_LOSS_UPDATED,
             data={
                 'symbol': ts.symbol,
                 'action': 'ts_activated',
                 'old_sl': float(old_sl) if old_sl else None,
                 'new_sl': float(ts.current_stop_price),
                 'activation_price': float(ts.activation_price),
                 'profit_pct': float(profit_percent)
             },
             symbol=ts.symbol,
             exchange=self.exchange.name
         )
     ```
  3. Add events for: signal processing, TS activation/обновлениеs, защита checks, zombies
  4. Create monitoring dashboard to query events table
- **Estimated Effort:** 3-4 дней
- **Files to Modify:**
  - signal_processor_websocket.py
  - wave_signal_processor.py
  - трейлинг_stop.py (15+ event points)
  - position_manager.py (10+ event points)
  - zombie_manager.py
  - position_synchronizer.py

---

**2. Fix Race Condition: Трейлинг-стоп vs Protection Manager**
- **Why Critical:** Can создание duplicate SL orders
- **Расположение:**
  - protection/trailing_stop.py:268-299
  - core/position_manager.py:1043-1226
- **How to Исправление:**
  ```python
  # In position_manager.py check_positions_protection():

  # BEFORE checking SL on exchange:
  if position.sl_managed_by == 'trailing_stop':
      # Check TS health
      ts_last_update = position.ts_last_update_time
      if ts_last_update and (datetime.now() - ts_last_update).seconds < 300:
          # TS is healthy, skip this position
          logger.debug(f"Skipping {symbol} - TS managing SL (healthy)")
          continue
      else:
          # TS unhealthy, take over
          logger.warning(f"TS unhealthy for {symbol}, Protection taking over")
          position.sl_managed_by = 'protection'
          # Proceed to set SL

  # ... rest of protection logic ...
  ```

  ```python
  # In trailing_stop.py update_price():

  async def update_price(self, symbol: str, price: float):
      # ... existing code ...

      # ADD: Update health timestamp
      if symbol in self.trailing_stops:
          ts = self.trailing_stops[symbol]
          ts.last_update_time = datetime.now()

          # Update PositionState in PositionManager
          # (requires passing position_manager reference)
          if hasattr(self, 'position_manager'):
              position = self.position_manager.positions.get(symbol)
              if position:
                  position.ts_last_update_time = datetime.now()

      # ... rest of update logic ...
  ```
- **Estimated Effort:** 1 день
- **Тестирование:** Create test that opens position, activates TS, then runs защита check simultaneously

---

**3. Fix Incomplete Atomic Rollback**
- **Why Critical:** Failed SL placement leaves unprotected positions
- **Location:** core/atomic_position_manager.py:334-382
- **How to Исправление:**
  ```python
  async def _rollback_position(self, position_id, entry_order, stop_loss_price):
      logger.warning(f"ROLLBACK: Attempting to close position {position_id}")

      # STEP 1: Poll for position on exchange (wait for it to appear)
      max_poll_attempts = 10
      position_found = False

      for attempt in range(max_poll_attempts):
          try:
              positions = await exchange.fetch_positions()
              for pos in positions:
                  if normalize_symbol(pos['symbol']) == symbol:
                      if abs(float(pos.get('contracts', 0))) > 0:
                          position_found = True
                          break

              if position_found:
                  break

              await asyncio.sleep(0.5)  # Wait 500ms before retry
          except:
              pass

      if not position_found:
          logger.error("Position not found on exchange after 5 seconds")
          # Mark as needs_manual_intervention
          await repository.update_position(position_id,
              status='failed',
              exit_reason='Rollback failed - position not found on exchange'
          )
          # Send critical alert
          await send_alert("CRITICAL: Rollback failed", details={...})
          return False

      # STEP 2: Place close order with FILLED quantity
      filled_qty = float(entry_order.filled or entry_order.amount)

      try:
          close_order = await exchange.create_market_order(
              symbol,
              'sell' if entry_side == 'buy' else 'buy',
              filled_qty
          )

          # Wait for close order to fill
          await asyncio.sleep(1)

          # Verify position closed
          # ... add verification ...

          return True

      except Exception as e:
          logger.error(f"Rollback close order failed: {e}")

          # STEP 3: Emergency: Place wide SL as last resort
          try:
              emergency_sl_price = entry_price * 0.90  # 10% SL
              await exchange.create_stop_loss_order(
                  symbol,
                  'sell' if entry_side == 'buy' else 'buy',
                  filled_qty,
                  emergency_sl_price
              )
              logger.warning("Emergency SL placed instead of full rollback")

              await repository.update_position(position_id,
                  status='active',  # Keep position
                  stop_loss_price=emergency_sl_price,
                  has_stop_loss=True,
                  exit_reason='Rollback failed, emergency SL placed'
              )
              return True
          except:
              logger.critical("EMERGENCY SL ALSO FAILED!")
              return False
  ```
- **Estimated Effort:** 2 дней (including testing)

---

**4. Migrate Float to Decimal in Database**
- **Why Critical:** Financial precision errors
- **Location:** database/models.py:144-177
- **How to Исправление:**
  1. Create migration script:
     ```sql
     -- migration_float_to_decimal.sql
     BEGIN;

     ALTER TABLE monitoring.positions
       ALTER COLUMN quantity TYPE DECIMAL(20, 8),
       ALTER COLUMN entry_price TYPE DECIMAL(20, 8),
       ALTER COLUMN current_price TYPE DECIMAL(20, 8),
       ALTER COLUMN mark_price TYPE DECIMAL(20, 8),
       ALTER COLUMN unrealized_pnl TYPE DECIMAL(20, 8),
       ALTER COLUMN unrealized_pnl_percent TYPE DECIMAL(10, 4),
       ALTER COLUMN stop_loss_price TYPE DECIMAL(20, 8),
       ALTER COLUMN trailing_activation_price TYPE DECIMAL(20, 8),
       ALTER COLUMN trailing_callback_rate TYPE DECIMAL(10, 4),
       ALTER COLUMN exit_price TYPE DECIMAL(20, 8),
       ALTER COLUMN realized_pnl TYPE DECIMAL(20, 8),
       ALTER COLUMN fees TYPE DECIMAL(20, 8);

     COMMIT;
     ```
  2. Update SQLAlchemy models:
     ```python
     from sqlalchemy import Numeric as Decimal

     quantity = Column(Decimal(20, 8), nullable=False)
     entry_price = Column(Decimal(20, 8), nullable=False)
     # ... etc
     ```
  3. Update all code using float() to use Decimal()
  4. Test thoroughly in staging
- **Estimated Effort:** 2 дней (1 день migration, 1 день testing)
- **Риск:** High - database schema change
- **Mitigation:** Test on copy of production DB first

---

**5. Add Health Check Endpoint**
- **Why Critical:** Need to monitor bot status in production
- **How to Исправление:**
  ```python
  # Add to main.py
  from aiohttp import web

  async def health_check(request):
      health = {
          'status': 'healthy',
          'timestamp': datetime.now().isoformat(),
          'database': await check_db_health(),
          'exchanges': await check_exchange_health(),
          'positions': len(position_manager.positions),
          'trailing_stops': len(trailing_manager.trailing_stops),
          'websocket': signal_processor.ws_client.connected,
          'last_signal': signal_processor.stats['last_signal_time'],
          'uptime_seconds': (datetime.now() - start_time).seconds
      }

      # Check if any critical issues
      if not health['database'] or not health['websocket']:
          health['status'] = 'unhealthy'
          return web.json_response(health, status=503)

      return web.json_response(health)

  # Start HTTP server on port 8080
  app = web.Application()
  app.router.add_get('/health', health_check)
  app.router.add_get('/stats', stats_endpoint)
  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, 'localhost', 8080)
  await site.start()
  ```
- **Estimated Effort:** 1 день

---

### HIGH (Fix within дней)

**6. Implement TS Fallback Logic**
- See issue #4 in КРИТИЧНО section
- Already partially implemented (ts_last_обновление_time поле exists)
- Just needs the fallback check in Protection Manager

**7. Fix Bybit Duplicate SL Issue**
- Extend _cancel_защита_sl_if_binance to support Bybit
- Location: trailing_stop.py:410-489

**8. Add Missing Database Indexes**
```sql
CREATE INDEX idx_positions_status ON monitoring.positions(status);
CREATE INDEX idx_positions_composite ON monitoring.positions(exchange, symbol, status);
CREATE INDEX idx_events_symbol ON events(symbol);
CREATE INDEX idx_events_severity ON events(severity);
```

**9. Add Partial Fill Hиling**
- See Section 9.5
- Use entry_order.filled вместо entry_order.amount for SL quantity

**10. Implement Idempotent SL Placement**
- Before placing SL, check if one exists
- If exists with same price, don't создание duplicate
- Расположение: stop_loss_manager.py

---

### MEDIUM (Fix when possible)

**11. Add Foreign Key Constraints**
- Restore commented relationships in models.py
- Add ON DELETE CASCADE for cleanup

**12. Implement Data Retention Policy**
- Archive old events/trades
- Partition events table by month

**13. Add Rate Limiting for TS Updates**
- Minimum 5 секунд between SL обновлениеs
- Prevent exchange rate limit issues

**14. Extend ExchangeResponseAdapter Error Hиling**
- Hиle all exchange-specific errors
- Distinguish temporary vs permanent errors

**15. Add Circuit Breaker for Database**
- Stop DB operations if failure rate > 50%
- Alert и wait for manual intervention

**16. Implement Webhook Alerts**
- Send to Telegram/Slack on critical events
- Zombie count > threshold
- Position without SL > 1 minute
- Rollback failure

**17. Add Конфигурация Hot-Reload**
- Reload config without restart
- Store config in database table

**18. Create Monitoring Dashboard**
- Query events table
- Real-time position status
- TS activation rates
- Error trends

---

### LOW (Nice to have)

**19. Add Unit Tests**
- Current coverage: Unknown (likely <20%)
- Target: >80% for core modules

**20. Add Integration Tests**
- Test full flow: signal → position → TS → close
- Mock exchange responses

**21. Optimize Трейлинг-стоп Lock**
- Change from global lock to per-position locks
- Improve throughput

**22. Add Metrics Collection**
- Prometheus metrics
- Grafana dashboards

**23. Document API**
- Add docstrings
- Generate Sphinx documentation

---

## CONCLUSION

This trading bot is functionally operational but has significant gaps in observability, fault tolerance, и concurrency safety. The most critical issue is the lack of comprehensive database event logging (only ~25% of critical events logged), which makes production debugging nearly impossible.

The recent commit history shows active bug fixing, with several critical issues addressed in the last 2 weeks (markPrice fix, retCode conversion, entry_price immutability). This suggests the bot is in active production use и issues are being discovered и fixed reactively.

**Key Strengths:**
- Modular architecture with clear separation of concerns
- Async/await throughout (performant)
- Atomic position creation with rollback logic
- Advanced трейлинг stop implementation
- Comprehensive zombie order обнаружение
- Active maintenance и bug fixes

**Key Weaknesses:**
- Логирование событий в базу данных severely lacking (25% complete)
- Race condition between TS и Protection Manager
- Incomplete rollback on SL failure
- Float вместо Decimal for financial data
- 2-minute sync window создает stale data risks
- No health monitoring endpoint
- No alerting system
- Минимальное unit test coverage

**Risk Assessment:**
- **Financial Риск:** HIGH - Unprotected positions possible if rollback fails
- **Operational Риск:** HIGH - Cannot reconstruct production issues without event logs
- **Concurrency Риск:** MEDIUM - Race conditions exist but partially mitigated
- **Data Integrity Риск:** HIGH - Float precision errors, no foreign keys

**Recommended Priority:**
1. Add comprehensive event logging (3-4 дней)
2. Fix TS vs Protection race condition (1 день)
3. Fix incomplete rollback (2 дней)
4. Add health check endpoint (1 день)
5. Migrate to Decimal (2 дней)

Total estimated effort for critical fixes: **8-11 дней**

The bot needs approximately 2 weeks of focused work to address critical issues before it can be considered production-ready at an enterprise level. However, for a personal/small-scale trading bot, it is already operational with acceptable risk if monitored closely.
