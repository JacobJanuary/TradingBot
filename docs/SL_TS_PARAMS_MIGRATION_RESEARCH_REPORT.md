# ОТЧЕТ: ИССЛЕДОВАНИЕ ПАРАМЕТРОВ SL/TS ДЛЯ МИГРАЦИИ НА PER-EXCHANGE КОНФИГУРАЦИЮ

**Дата**: 2025-10-28
**Статус**: ✅ ЭТАП 1 ЗАВЕРШЕН - Полная инвентаризация
**Критичность**: 🔴 HIGH
**Тип**: Исследование и планирование (БЕЗ изменений кода)

---

## EXECUTIVE SUMMARY

### Цель
Подготовить полный план миграции параметров Stop-Loss и Trailing Stop с глобальной конфигурации (.env) на per-exchange конфигурацию (БД таблица `monitoring.params`).

### Текущее состояние (AS-IS)
```env
# .env - одинаковые параметры для ВСЕХ бирж
STOP_LOSS_PERCENT=4.0
TRAILING_ACTIVATION_PERCENT=2.0
TRAILING_CALLBACK_PERCENT=0.5
```

### Целевое состояние (TO-BE)
```sql
-- Новая таблица monitoring.params
CREATE TABLE monitoring.params (
    exchange VARCHAR(20) PRIMARY KEY,  -- 'binance', 'bybit'
    stop_loss_percent NUMERIC(5,2),
    trailing_activation_percent NUMERIC(5,2),
    trailing_callback_percent NUMERIC(5,2),
    updated_at TIMESTAMP
);

-- Расширение таблицы monitoring.positions
ALTER TABLE monitoring.positions
ADD COLUMN trailing_activation_percent NUMERIC(5,2),
ADD COLUMN trailing_callback_percent NUMERIC(5,2);
```

### Масштаб изменений
- **Файлов проанализировано**: 7 core files
- **Мест использования найдено**: 23+ locations
- **Критичных изменений требуется**: 5-7 major changes
- **Новых компонентов**: ParamsManager (новый класс)
- **Изменений БД**: 1 новая таблица, 2 новых поля в positions

### Оценка рисков
🔴 **ВЫСОКАЯ** - Изменяет критичную логику защиты капитала

### Рекомендация
⚠️ **ТРЕБУЕТ ТЩАТЕЛЬНОГО ПЛАНИРОВАНИЯ** - Готов к детальному проектированию после review этого отчета

---

## 1. ПОЛНАЯ ИНВЕНТАРИЗАЦИЯ ИСПОЛЬЗОВАНИЯ ПАРАМЕТРОВ

### 1.1 STOP_LOSS_PERCENT

| # | Файл:Строка | Контекст использования | Тип | Биржа доступна? | Критичность |
|---|-------------|------------------------|-----|----------------|-------------|
| 1 | `config/settings.py:47` | `stop_loss_percent: Decimal = Decimal('4.0')` | Default значение | N/A | LOW |
| 2 | `config/settings.py:213-214` | `config.stop_loss_percent = Decimal(val)` | Загрузка из .env | N/A | LOW |
| 3 | `config/settings.py:330` | `if self.trading.stop_loss_percent <= 0:` | Валидация | N/A | LOW |
| 4 | `position_manager.py:1073` | `stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent` | **Создание позиции** | ✅ YES (request.exchange) | 🔴 CRITICAL |
| 5 | `position_manager.py:1107` | `stop_loss_percent=float(stop_loss_percent)` | Передача в AtomicPositionManager | ✅ YES | 🔴 CRITICAL |
| 6 | `position_manager.py:497` | `stop_loss_percent = to_decimal(self.config.stop_loss_percent)` | Создание SL для позиции | ✅ YES (position.exchange) | 🔴 CRITICAL |
| 7 | `position_manager.py:792` | `stop_loss_percent = to_decimal(self.config.stop_loss_percent)` | Создание SL (другая ветка) | ✅ YES | 🔴 CRITICAL |
| 8 | `position_manager.py:854` | `stop_loss_percent = to_decimal(self.config.stop_loss_percent)` | Создание SL (третья ветка) | ✅ YES | 🔴 CRITICAL |
| 9 | `position_manager.py:1340` | `stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent` | Обновление позиции | ✅ YES | 🔴 CRITICAL |
| 10 | `position_manager.py:3038-3061` | `stop_loss_percent = self.config.stop_loss_percent` | **Recovery при рестарте** | ✅ YES (position.exchange) | 🔴 CRITICAL |
| 11 | `atomic_position_manager.py:200` | `stop_loss_percent: float` | Параметр метода (принимает значение) | ✅ YES | HIGH |
| 12 | `stop_loss_manager.py:576` | `STOP_LOSS_SAFETY_MARGIN_PERCENT` | Safety margin (другой параметр) | N/A | LOW |

**Всего использований STOP_LOSS_PERCENT**: 12 мест
**Критичных**: 7 мест (требуют изменения для per-exchange)

---

### 1.2 TRAILING_ACTIVATION_PERCENT

| # | Файл:Строка | Контекст использования | Тип | Биржа доступна? | Критичность |
|---|-------------|------------------------|-----|----------------|-------------|
| 1 | `config/settings.py:48` | `trailing_activation_percent: Decimal = Decimal('2.0')` | Default значение | N/A | LOW |
| 2 | `config/settings.py:215-216` | `config.trailing_activation_percent = Decimal(val)` | Загрузка из .env | N/A | LOW |
| 3 | `position_manager.py:189` | `activation_percent=Decimal(str(config.trailing_activation_percent))` | **Создание TrailingStopConfig** | ⚠️ NO (глобальный!) | 🔴 CRITICAL |
| 4 | `trailing_stop.py:40` | `activation_percent: Decimal = Decimal('1.5')` | Default в TrailingStopConfig | N/A | LOW |
| 5 | `trailing_stop.py:119` | `self.config = config or TrailingStopConfig()` | Инициализация TS Manager | ⚠️ NO | 🔴 CRITICAL |
| 6 | `trailing_stop.py:200` | `'activation_percent': float(self.config.activation_percent)` | **Сохранение в БД state** | ⚠️ NO (из config!) | 🔴 CRITICAL |
| 7 | `trailing_stop.py:489-492` | `ts.activation_price = ts.entry_price * (1 + self.config.activation_percent / 100)` | **Расчет activation price** | ⚠️ NO | 🔴 CRITICAL |
| 8 | `trailing_stop.py:654-656` | `should_activate = ts.current_price >= ts.activation_price` | Проверка активации (использует pre-calculated price) | ✅ OK | MEDIUM |

**Всего использований TRAILING_ACTIVATION_PERCENT**: 8 мест
**Критичных**: 5 мест
**⚠️ ПРОБЛЕМА**: Все расчеты используют ГЛОБАЛЬНЫЙ config, не зависят от биржи!

---

### 1.3 TRAILING_CALLBACK_PERCENT

| # | Файл:Строка | Контекст использования | Тип | Биржа доступна? | Критичность |
|---|-------------|------------------------|-----|----------------|-------------|
| 1 | `config/settings.py:49` | `trailing_callback_percent: Decimal = Decimal('0.5')` | Default значение | N/A | LOW |
| 2 | `config/settings.py:217-218` | `config.trailing_callback_percent = Decimal(val)` | Загрузка из .env | N/A | LOW |
| 3 | `position_manager.py:190` | `callback_percent=Decimal(str(config.trailing_callback_percent))` | **Создание TrailingStopConfig** | ⚠️ NO | 🔴 CRITICAL |
| 4 | `trailing_stop.py:41` | `callback_percent: Decimal = Decimal('0.5')` | Default в TrailingStopConfig | N/A | LOW |
| 5 | `trailing_stop.py:201` | `'callback_percent': float(self.config.callback_percent)` | Сохранение в БД state | ⚠️ NO | 🔴 CRITICAL |
| 6 | `trailing_stop.py:682-684` | `ts.current_stop_price = ts.highest_price * (1 - distance / 100)` | **Расчет trailing SL** | ⚠️ NO (distance из config) | 🔴 CRITICAL |
| 7 | `trailing_stop.py:901-927` | `_get_trailing_distance()` возвращает `self.config.callback_percent` | Получение distance | ⚠️ NO | 🔴 CRITICAL |

**Всего использований TRAILING_CALLBACK_PERCENT**: 7 мест
**Критичных**: 5 мест

---

## 2. ДЕТАЛЬНЫЙ АНАЛИЗ ЖИЗНЕННОГО ЦИКЛА ПОЗИЦИИ

### 2.1 Создание позиции - Flow Analysis

#### Entry Point: `PositionManager.open_position()`
**Файл**: `position_manager.py`
**Строка**: 1073

**Полная цепочка**:

```python
# ШАГИ СОЗДАНИЯ ПОЗИЦИИ
# =======================

# 1. PositionManager.open_position(request: PositionRequest)
#    Строка 1073:
stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent  # ← ГЛОБАЛЬНЫЙ!

# 2. Расчет SL price
#    Строка 1074-1076:
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),
    position_side,
    to_decimal(stop_loss_percent)  # ← Использует глобальный параметр
)

# 3. Передача в AtomicPositionManager
#    Строка 1100-1108:
atomic_result = await atomic_manager.open_position_atomic(
    signal_id=request.signal_id,
    symbol=symbol,
    exchange=exchange_name,  # ← БИРЖА ДОСТУПНА ЗДЕСЬ!
    side=order_side,
    quantity=quantity,
    entry_price=float(request.entry_price),
    stop_loss_percent=float(stop_loss_percent)  # ← Передает глобальный параметр
)

# 4. AtomicPositionManager.open_position_atomic()
#    Файл: atomic_position_manager.py
#    Строка 192-201:
async def open_position_atomic(
    self,
    signal_id: int,
    symbol: str,
    exchange: str,  # ← БИРЖА ДОСТУПНА!
    side: str,
    quantity: float,
    entry_price: float,
    stop_loss_percent: float  # ← Использует переданное значение
)

# 5. Создание entry ордера и SL ордера
#    (используется stop_loss_percent для расчета SL цены)

# 6. Сохранение в БД (monitoring.positions)
#    ⚠️ ПРОБЛЕМА: trailing_activation_percent НЕ сохраняется в позицию!
```

**Доступная информация в точке создания**:
- ✅ `exchange` (название биржи) - ДОСТУПНА на шаге 1
- ✅ `symbol` - доступен
- ✅ `position_side` - доступен
- ✅ `entry_price` - доступен
- ❌ `trailing_activation_percent` - НЕ сохраняется в позицию
- ❌ `trailing_callback_percent` - НЕ сохраняется в позицию

---

### 2.2 Инициализация Trailing Stop

#### Entry Point: `SmartTrailingStopManager.__init__()`
**Файл**: `protection/trailing_stop.py`
**Строка**: 107-120

```python
# ИНИЦИАЛИЗАЦИЯ TRAILING STOP MANAGER (на старте бота)
# ====================================================

# position_manager.py:188-202
trailing_config = TrailingStopConfig(
    activation_percent=Decimal(str(config.trailing_activation_percent)),  # ← ГЛОБАЛЬНЫЙ!
    callback_percent=Decimal(str(config.trailing_callback_percent)),      # ← ГЛОБАЛЬНЫЙ!
    breakeven_at=None
)

self.trailing_managers = {
    name: SmartTrailingStopManager(
        exchange,
        trailing_config,  # ← ОДИН config для ВСЕХ бирж!
        exchange_name=name,
        repository=repository
    )
    for name, exchange in exchanges.items()
}
```

**⚠️ КРИТИЧЕСКАЯ ПРОБЛЕМА**:
- `TrailingStopConfig` создается ОДИН РАЗ при старте бота
- ОДИНАКОВЫЙ для Binance и Bybit
- НЕ зависит от биржи позиции

---

### 2.3 Создание Trailing Stop Instance

#### Entry Point: `SmartTrailingStopManager.create_trailing_stop()`
**Файл**: `protection/trailing_stop.py`
**Строка**: 446-548

```python
# СОЗДАНИЕ TS ДЛЯ КОНКРЕТНОЙ ПОЗИЦИИ
# ==================================

async def create_trailing_stop(self,
                               symbol: str,
                               side: str,
                               entry_price: float,
                               quantity: float,
                               initial_stop: Optional[float] = None):
    # Строка 472-492:
    ts = TrailingStopInstance(
        symbol=symbol,
        entry_price=Decimal(str(entry_price)),
        # ... другие поля
        side=side.lower(),
        quantity=Decimal(str(quantity))
    )

    # ⚠️ КРИТИЧЕСКОЕ МЕСТО - расчет activation_price
    # Строка 489-492:
    if side == 'long':
        ts.activation_price = ts.entry_price * (1 + self.config.activation_percent / 100)
                                                      # ↑ ГЛОБАЛЬНЫЙ config!
    else:
        ts.activation_price = ts.entry_price * (1 - self.config.activation_percent / 100)
                                                      # ↑ ГЛОБАЛЬНЫЙ config!

    # Сохранение в БД
    # Строка 523:
    await self._save_state(ts)
```

**Что сохраняется в БД** (`_save_state`, строка 144-223):

```python
state_data = {
    'symbol': ts.symbol,
    'exchange': self.exchange_name,
    'position_id': position_id,
    'state': ts.state.value,
    # ... другие поля ...
    'activation_price': float(ts.activation_price),  # ← Рассчитанная цена (хорошо)
    'activation_percent': float(self.config.activation_percent),  # ← ГЛОБАЛЬНЫЙ! (плохо)
    'callback_percent': float(self.config.callback_percent),      # ← ГЛОБАЛЬНЫЙ! (плохо)
    'entry_price': float(ts.entry_price),
    'side': ts.side,
    # ...
}
```

**⚠️ ПРОБЛЕМЫ**:
1. `activation_price` рассчитывается от ГЛОБАЛЬНОГО `self.config.activation_percent`
2. `activation_percent` сохраняется в state, но берется из ГЛОБАЛЬНОГО config
3. При изменении .env параметров - новые позиции получат ДРУГОЙ activation_percent

---

### 2.4 Recovery при рестарте бота

#### Entry Point: `SmartTrailingStopManager._restore_state()`
**Файл**: `protection/trailing_stop.py`
**Строка**: 225-421

```python
# ВОССТАНОВЛЕНИЕ TS ИЗ БД ПРИ РЕСТАРТЕ
# ====================================

async def _restore_state(self, symbol: str, position_data: Optional[Dict] = None):
    # Загрузка state из БД
    # Строка 246:
    state_data = await self.repository.get_trailing_stop_state(symbol, self.exchange_name)

    # Реконструкция TS instance
    # Строка 369-390:
    ts = TrailingStopInstance(
        symbol=state_data['symbol'],
        entry_price=Decimal(str(state_data['entry_price'])),
        # ...
        # ⚠️ КРИТИЧНО: activation_price восстанавливается из БД (хорошо!)
        activation_price=Decimal(str(state_data['activation_price'])),  # ← ИЗ БД
        # ...
        side=side_value,
        quantity=Decimal(str(state_data['quantity']))
    )

    return ts
```

**✅ ХОРОШО**:
- `activation_price` восстанавливается из БД (была рассчитана при создании)
- TS продолжит работать с тем же activation порогом, что был при создании

**⚠️ ПРОБЛЕМА**:
- Если в БД нет `activation_price` (legacy позиции) - что делать?
- `callback_percent` читается из state, но при активации TS будет использовать `self.config.callback_percent` (глобальный!)

---

### 2.5 Активация Trailing Stop

#### Entry Point: `SmartTrailingStopManager._activate_trailing_stop()`
**Файл**: `protection/trailing_stop.py`
**Строка**: 672-732

```python
# АКТИВАЦИЯ TS (КОГДА ЦЕНА ДОСТИГЛА ACTIVATION_PRICE)
# ===================================================

async def _activate_trailing_stop(self, ts: TrailingStopInstance):
    # Строка 679:
    distance = self._get_trailing_distance(ts)  # ← Использует config!

    # Строка 682-684 (для long):
    ts.current_stop_price = ts.highest_price * (1 - distance / 100)
                                                     # ↑ distance из config
```

**`_get_trailing_distance()` - строка 901-927**:

```python
def _get_trailing_distance(self, ts: TrailingStopInstance) -> Decimal:
    # ... step activation logic ...

    # Строка 926:
    return self.config.callback_percent  # ← ГЛОБАЛЬНЫЙ config!
```

**⚠️ ПРОБЛЕМА**:
- При активации TS использует **ТЕКУЩИЙ** `self.config.callback_percent`
- Если .env изменился с момента создания позиции - будет использован **НОВЫЙ** callback!
- Inconsistency: позиция могла создаваться с callback=0.5%, а активируется с callback=0.3%

---

## 3. ТЕКУЩАЯ АРХИТЕКТУРА КОНФИГУРАЦИИ

### 3.1 Структура Config

**Файл**: `config/settings.py`

```python
# DATACLASS STRUCTURE
# ===================

@dataclass
class TradingConfig:
    """Trading parameters from .env ONLY"""

    # Risk management - строки 47-49
    stop_loss_percent: Decimal = Decimal('4.0')            # ← DEFAULT
    trailing_activation_percent: Decimal = Decimal('2.0')  # ← DEFAULT
    trailing_callback_percent: Decimal = Decimal('0.5')    # ← DEFAULT

    # ... другие параметры ...


class Config:
    """Main configuration class"""

    def __init__(self):
        # Строка 137:
        load_dotenv(override=True)

        # Строка 140-143:
        self.exchanges = self._init_exchanges()  # ← Загружает Binance, Bybit
        self.trading = self._init_trading()      # ← Загружает trading params
        self.safety = self._init_safety_constants()
        self.database = self._init_database()

    def _init_trading(self) -> TradingConfig:
        # Строка 198:
        config = TradingConfig()  # ← Defaults загружаются

        # Строка 213-218 - переопределение из .env:
        if val := os.getenv('STOP_LOSS_PERCENT'):
            config.stop_loss_percent = Decimal(val)
        if val := os.getenv('TRAILING_ACTIVATION_PERCENT'):
            config.trailing_activation_percent = Decimal(val)
        if val := os.getenv('TRAILING_CALLBACK_PERCENT'):
            config.trailing_callback_percent = Decimal(val)

        return config


# Singleton instance - строка 338:
config = Config()
```

**Как используется**:

```python
# В любом файле:
from config.settings import config

# Доступ к параметрам:
sl_percent = config.trading.stop_loss_percent  # ← ГЛОБАЛЬНЫЙ для всех бирж
```

**Характеристики**:
- ✅ Singleton: Да (один экземпляр)
- ❌ Reload возможен: Нет (создается при импорте)
- ✅ Thread-safe: Да (только чтение после инициализации)
- ❌ Per-exchange: Нет (одинаковые параметры для всех бирж)

---

### 3.2 Текущая БД структура

**Файл**: `database/models.py`

#### Таблица `monitoring.positions` (строки 95-162):

```python
class Position(Base):
    __tablename__ = 'positions'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)
    signal_id = Column(String(100), nullable=True)
    trade_id = Column(Integer, ForeignKey('monitoring.trades.id'), nullable=False)

    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(50), nullable=False, index=True)  # ✅ ЕСТЬ!

    side = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)

    # Trailing stop
    has_trailing_stop = Column(Boolean, default=True, nullable=False)
    trailing_activated = Column(Boolean, default=False)
    trailing_activation_price = Column(Float)      # ✅ ЕСТЬ (цена активации)
    trailing_callback_rate = Column(Float)         # ⚠️ ЕСТЬ, но НЕ используется?

    # ❌ ОТСУТСТВУЮТ:
    # - trailing_activation_percent  (процент для активации)
    # - trailing_callback_percent    (процент callback)

    # Stop loss
    has_stop_loss = Column(Boolean, default=False)
    stop_loss_price = Column(Float)
    stop_loss_order_id = Column(String(100))

    # Status
    status = Column(SQLEnum(PositionStatus), default=PositionStatus.OPEN, nullable=False)

    opened_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    closed_at = Column(TIMESTAMP(timezone=True))
    # ... другие поля ...
```

**❌ КРИТИЧНЫЕ ПРОБЛЕМЫ**:
1. **НЕТ** поля `trailing_activation_percent` - процент НЕ сохраняется при создании позиции
2. **НЕТ** поля `trailing_callback_percent` - процент НЕ сохраняется
3. `trailing_callback_rate` существует, но не используется (dead code?)
4. При рестарте невозможно восстановить параметры из позиции - только из TS state

---

#### Таблица `monitoring.trailing_stop_states` (неявная, используется через repository)

**Структура state_data** (из `trailing_stop.py:189-213`):

```python
state_data = {
    'symbol': str,
    'exchange': str,
    'position_id': int,
    'state': str,  # 'inactive', 'waiting', 'active', 'triggered'
    'is_activated': bool,
    'highest_price': float,
    'lowest_price': float,
    'current_stop_price': float,
    'stop_order_id': str,
    'activation_price': float,           # ✅ Рассчитанная цена активации
    'activation_percent': float,         # ⚠️ Из ГЛОБАЛЬНОГО config!
    'callback_percent': float,           # ⚠️ Из ГЛОБАЛЬНОГО config!
    'entry_price': float,
    'side': str,
    'quantity': float,
    'update_count': int,
    'highest_profit_percent': float,
    'activated_at': datetime,
    'last_update_time': datetime,
    # ...
}
```

**⚠️ ПРОБЛЕМЫ**:
- `activation_percent` сохраняется, но берется из `self.config.activation_percent` (глобальный)
- `callback_percent` сохраняется, но берется из `self.config.callback_percent` (глобальный)
- При создании TS для разных бирж - будут сохранены ОДИНАКОВЫЕ проценты
- **НЕТ** связи с таблицей `monitoring.params` (такой таблицы вообще нет)

---

### 3.3 Таблица `monitoring.params` - НЕ СУЩЕСТВУЕТ

**Требуется создать**:

```sql
CREATE TABLE monitoring.params (
    exchange VARCHAR(20) PRIMARY KEY,
    stop_loss_percent NUMERIC(5,2) NOT NULL,
    trailing_activation_percent NUMERIC(5,2) NOT NULL,
    trailing_callback_percent NUMERIC(5,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Default values (из текущего .env)
INSERT INTO monitoring.params VALUES
    ('binance', 4.0, 2.0, 0.5),
    ('bybit', 4.0, 2.0, 0.5);
```

---

## 4. КРИТИЧНЫЕ МЕСТА ДЛЯ ИЗМЕНЕНИЯ

### 4.1 PositionManager: Создание позиции

**Файл**: `position_manager.py`
**Метод**: `open_position()`
**Строки**: 1073-1108

**Текущий код**:
```python
# Строка 1073:
stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
                                                  # ↑ ГЛОБАЛЬНЫЙ - ПРОБЛЕМА!

# Строка 1074-1076:
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),
    position_side,
    to_decimal(stop_loss_percent)
)
```

**Доступная информация**:
- ✅ `request.exchange` - название биржи ДОСТУПНО
- ✅ `request.symbol` - символ
- ✅ `position_side` - сторона позиции
- ✅ `self.config` - глобальная конфигурация

**Требуемые изменения**:

```python
# ПСЕВДОКОД желаемой логики:

# 1. Получить параметры для конкретной биржи
exchange_params = await self.params_manager.get_params(request.exchange)

# 2. Использовать per-exchange параметры
stop_loss_percent = request.stop_loss_percent or exchange_params.stop_loss_percent
trailing_activation_percent = exchange_params.trailing_activation_percent
trailing_callback_percent = exchange_params.trailing_callback_percent

# 3. Рассчитать SL price
stop_loss_price = calculate_stop_loss(
    to_decimal(request.entry_price),
    position_side,
    to_decimal(stop_loss_percent)
)

# 4. СОХРАНИТЬ trailing params в позицию при создании!
position_data = {
    'symbol': symbol,
    'exchange': request.exchange,
    'side': position_side,
    # ... другие поля ...
    'trailing_activation_percent': float(trailing_activation_percent),  # ← НОВОЕ ПОЛЕ
    'trailing_callback_percent': float(trailing_callback_percent),      # ← НОВОЕ ПОЛЕ
}
await self.repository.create_position(position_data)
```

**Зависимости**:
1. ❌ `ParamsManager` - не существует, нужно создать
2. ❌ `get_params(exchange)` - метод не существует
3. ❌ БД поля `trailing_activation_percent`, `trailing_callback_percent` - не существуют
4. ❌ Таблица `monitoring.params` - не существует

---

### 4.2 PositionManager: Инициализация TrailingStopConfig

**Файл**: `position_manager.py`
**Метод**: `__init__()`
**Строки**: 184-202

**Текущий код**:
```python
trailing_config = TrailingStopConfig(
    activation_percent=Decimal(str(config.trailing_activation_percent)),  # ← ГЛОБАЛЬНЫЙ
    callback_percent=Decimal(str(config.trailing_callback_percent)),      # ← ГЛОБАЛЬНЫЙ
    breakeven_at=None
)

self.trailing_managers = {
    name: SmartTrailingStopManager(
        exchange,
        trailing_config,  # ← ОДИН config для ВСЕХ бирж!
        exchange_name=name,
        repository=repository
    )
    for name, exchange in exchanges.items()
}
```

**⚠️ ПРОБЛЕМА**:
- `TrailingStopConfig` создается ОДИН РАЗ для ВСЕХ бирж
- Не учитывает per-exchange параметры

**Возможные подходы к решению**:

#### **Вариант A: Per-Exchange TrailingStopConfig** (простой)

```python
# Создавать отдельный config для каждой биржи
self.trailing_managers = {}
for name, exchange in exchanges.items():
    # Загрузить params для этой биржи
    exchange_params = await self.params_manager.get_params(name)

    # Создать config специфичный для биржи
    trailing_config = TrailingStopConfig(
        activation_percent=exchange_params.trailing_activation_percent,
        callback_percent=exchange_params.trailing_callback_percent,
        breakeven_at=None
    )

    self.trailing_managers[name] = SmartTrailingStopManager(
        exchange,
        trailing_config,
        exchange_name=name,
        repository=repository
    )
```

**Плюсы**:
- Минимальные изменения
- TrailingStopManager продолжает использовать `self.config`

**Минусы**:
- Параметры фиксируются при старте бота
- Для изменения нужен рестарт
- Не решает проблему сохранения params в позицию

---

#### **Вариант B: Dynamic params from position** (правильный)

```python
# В SmartTrailingStopManager:

async def create_trailing_stop(self,
                               symbol: str,
                               side: str,
                               entry_price: float,
                               quantity: float,
                               position_data: Dict):  # ← НОВЫЙ ПАРАМЕТР!
    # ...

    # Использовать params из позиции (были сохранены при создании)
    activation_percent = position_data.get('trailing_activation_percent')
    callback_percent = position_data.get('trailing_callback_percent')

    # Рассчитать activation price от params позиции
    if side == 'long':
        ts.activation_price = ts.entry_price * (1 + activation_percent / 100)
    else:
        ts.activation_price = ts.entry_price * (1 - activation_percent / 100)

    # Сохранить в instance
    ts.activation_percent = activation_percent  # ← НОВОЕ ПОЛЕ в TrailingStopInstance
    ts.callback_percent = callback_percent      # ← НОВОЕ ПОЛЕ
```

**Плюсы**:
- ✅ Каждая позиция имеет свои параметры
- ✅ При изменении params в БД - старые позиции НЕ затрагиваются
- ✅ Восстановление после рестарта работает правильно

**Минусы**:
- Требует изменения структуры `TrailingStopInstance`
- Требует изменения БД (новые поля в positions)
- Больше изменений кода

**Рекомендация**: Вариант B более правильный с точки зрения архитектуры

---

### 4.3 SmartTrailingStopManager: create_trailing_stop()

**Файл**: `protection/trailing_stop.py`
**Метод**: `create_trailing_stop()`
**Строки**: 446-548

**Текущий код** (строки 489-492):
```python
# Calculate activation price
if side == 'long':
    ts.activation_price = ts.entry_price * (1 + self.config.activation_percent / 100)
                                                 # ↑ ГЛОБАЛЬНЫЙ config!
else:
    ts.activation_price = ts.entry_price * (1 - self.config.activation_percent / 100)
```

**Требуемые изменения** (Вариант B):

```python
async def create_trailing_stop(self,
                               symbol: str,
                               side: str,
                               entry_price: float,
                               quantity: float,
                               initial_stop: Optional[float] = None,
                               position_params: Optional[Dict] = None):  # ← НОВЫЙ ПАРАМЕТР!
    # ...

    # Get params from position or fallback to config
    if position_params:
        activation_percent = Decimal(str(position_params['trailing_activation_percent']))
        callback_percent = Decimal(str(position_params['trailing_callback_percent']))
    else:
        # Fallback для legacy позиций без params
        logger.warning(f"{symbol}: No trailing params in position, using config fallback")
        activation_percent = self.config.activation_percent
        callback_percent = self.config.callback_percent

    ts = TrailingStopInstance(
        # ... существующие поля ...
        # ← НОВЫЕ ПОЛЯ:
        activation_percent=activation_percent,  # Сохранить в instance!
        callback_percent=callback_percent       # Сохранить в instance!
    )

    # Calculate activation price from position-specific params
    if side == 'long':
        ts.activation_price = ts.entry_price * (1 + activation_percent / 100)
    else:
        ts.activation_price = ts.entry_price * (1 - activation_percent / 100)
```

**Требует изменения `TrailingStopInstance`** (строки 66-99):

```python
@dataclass
class TrailingStopInstance:
    symbol: str
    entry_price: Decimal
    # ... существующие поля ...

    # ← НОВЫЕ ПОЛЯ:
    activation_percent: Decimal = Decimal('0')   # Percent to activate (from position)
    callback_percent: Decimal = Decimal('0')     # Trail distance (from position)
```

---

### 4.4 SmartTrailingStopManager: _get_trailing_distance()

**Файл**: `protection/trailing_stop.py`
**Метод**: `_get_trailing_distance()`
**Строки**: 901-927

**Текущий код**:
```python
def _get_trailing_distance(self, ts: TrailingStopInstance) -> Decimal:
    # ... step activation logic ...

    # Строка 926:
    return self.config.callback_percent  # ← ГЛОБАЛЬНЫЙ config!
```

**Требуемые изменения**:

```python
def _get_trailing_distance(self, ts: TrailingStopInstance) -> Decimal:
    # ... step activation logic ...

    # Используем callback_percent из TS instance (был сохранен при создании)
    return ts.callback_percent  # ← ИЗ ПОЗИЦИИ!
```

**✅ ПРОСТОЕ ИЗМЕНЕНИЕ** - просто читать из `ts.callback_percent` вместо `self.config.callback_percent`

---

### 4.5 SmartTrailingStopManager: _save_state()

**Файл**: `protection/trailing_stop.py`
**Метод**: `_save_state()`
**Строки**: 144-223

**Текущий код** (строки 200-201):
```python
state_data = {
    # ...
    'activation_percent': float(self.config.activation_percent),  # ← ГЛОБАЛЬНЫЙ!
    'callback_percent': float(self.config.callback_percent),      # ← ГЛОБАЛЬНЫЙ!
    # ...
}
```

**Требуемые изменения**:

```python
state_data = {
    # ...
    'activation_percent': float(ts.activation_percent),  # ← ИЗ INSTANCE!
    'callback_percent': float(ts.callback_percent),      # ← ИЗ INSTANCE!
    # ...
}
```

**✅ ПРОСТОЕ ИЗМЕНЕНИЕ** - читать из `ts` вместо `self.config`

---

## 5. EDGE CASES И РИСКИ

### 5.1 Сценарий: Создание позиции на Binance

#### Текущее поведение:
```
1. Signal приходит для BTCUSDT на Binance
2. PositionManager.open_position() вызывается
3. Читает stop_loss_percent = config.stop_loss_percent = 4.0%
4. Создает SL на 4%
5. TrailingStopManager создает TS с activation = 2.0%, callback = 0.5%
6. Сохраняет в БД:
   - positions: НЕТ trailing params
   - trailing_stop_states: activation_percent = 2.0%, callback_percent = 0.5%
```

#### Желаемое поведение после миграции:
```
1. Signal приходит для BTCUSDT на Binance
2. PositionManager.open_position() вызывается
3. ParamsManager.get_params('binance') → {sl: 3.5%, activation: 1.5%, callback: 0.4%}
4. Создает SL на 3.5%
5. Сохраняет в БД positions:
   - trailing_activation_percent = 1.5%
   - trailing_callback_percent = 0.4%
6. TrailingStopManager.create_trailing_stop(position_params=...)
7. TS создается с activation = 1.5%, callback = 0.4% (из позиции!)
8. Сохраняет в trailing_stop_states: activation_percent = 1.5%, callback = 0.4%
```

#### Требуемые изменения:
- [x] Таблица monitoring.params с записью ('binance', 3.5, 1.5, 0.4)
- [x] БД поля positions.trailing_activation_percent, positions.trailing_callback_percent
- [x] ParamsManager класс с методом get_params()
- [x] Изменение position_manager.py:1073 - использовать params_manager
- [x] Изменение create_position() - сохранять trailing params
- [x] Изменение create_trailing_stop() - принимать position_params
- [x] Изменение TrailingStopInstance - поля activation/callback_percent

---

### 5.2 Сценарий: Рестарт бота с активными позициями

#### Текущее поведение:
```
День 1 (15:00):
- Создана позиция ETHUSDT на Bybit
- activation_percent из config = 2.0%
- TS state сохранен с activation_percent = 2.0%

День 1 (16:00):
- .env изменен: TRAILING_ACTIVATION_PERCENT=1.5%
- Бот перезапущен
- Config загружается: activation_percent = 1.5%
```

**⚠️ ЧТО ПРОИСХОДИТ С ETHUSDT ПОЗИЦИЕЙ?**

```
1. Загружаются позиции из БД
2. Для каждой позиции вызывается trailing_manager.create_trailing_stop()
3. activation_price рассчитывается как:
   entry * (1 + self.config.activation_percent / 100)
              # ↑ НОВОЕ значение 1.5% вместо 2.0%!
4. TS будет ждать 1.5% профита вместо 2.0%
5. НЕПРАВИЛЬНО - параметры изменились после создания позиции!
```

**❌ БАГ**: При рестарте используются НОВЫЕ параметры из .env, а не те, что были при создании

#### Желаемое поведение после миграции:

**Вариант A: Восстановление из trailing_stop_states** (текущий подход, частично работает):
```
1. Загружаются позиции из БД
2. Вызывается trailing_manager._restore_state(symbol)
3. Из trailing_stop_states загружается activation_price = 50000 (рассчитанная при создании)
4. TS восстанавливается с правильной activation_price
5. ✅ РАБОТАЕТ ПРАВИЛЬНО
```

**Но при создании НОВОЙ позиции:**
```
1. create_trailing_stop() вызывается без _restore_state()
2. activation_price рассчитывается от self.config.activation_percent (НОВЫЙ!)
3. ❌ БАГ сохраняется
```

**Вариант B: Восстановление из positions.trailing_activation_percent** (правильное решение):
```
1. Загружаются позиции из БД
2. position.trailing_activation_percent = 2.0% (было сохранено при создании)
3. create_trailing_stop(position_params={'trailing_activation_percent': 2.0})
4. activation_price рассчитывается от 2.0% (из позиции, не config!)
5. ✅ РАБОТАЕТ ПРАВИЛЬНО для всех позиций (новых и восстановленных)
```

---

### 5.3 Сценарий: Изменение параметров в БД во время работы

#### Вопрос:
Администратор меняет `monitoring.params` для Binance: `trailing_activation_percent` с 2.0% на 1.8%
**Должны ли существующие позиции быть затронуты?**

#### Анализ:

**1. Stop Loss (SL)**:
- Создается ОДИН РАЗ при открытии позиции
- После создания - фиксирован (ордер на бирже)
- ✅ **Ответ**: НЕТ, изменения params НЕ влияют на существующие позиции

**2. Trailing Stop Activation Percent**:
- Используется для расчета `activation_price` при создании позиции
- `activation_price` фиксируется и сохраняется
- После активации - не используется
- ✅ **Ответ**: НЕТ, изменения params НЕ влияют (activation_price уже рассчитан)

**3. Trailing Stop Callback Percent**:
- Используется КАЖДЫЙ РАЗ при обновлении SL
- При каждом update_trailing_stop() вызывается _get_trailing_distance()
- ⚠️ **Вопрос**: Можно ли менять динамически?

**Варианты для callback_percent**:

**Вариант A: Зафиксировать при создании позиции** (безопасный):
```python
# Сохранить в positions.trailing_callback_percent
# Читать из position при каждом update
return ts.callback_percent  # Всегда тот же, что был при создании
```

**Плюсы**:
- Предсказуемость - поведение не меняется после создания
- Простота тестирования

**Минусы**:
- Невозможно "подтянуть" SL ближе для старых позиций

**Вариант B: Читать из params динамически** (гибкий):
```python
# Каждый раз читать из monitoring.params
exchange_params = await params_manager.get_params(position.exchange)
return exchange_params.trailing_callback_percent
```

**Плюсы**:
- Можно корректировать стратегию на ходу
- Единый source of truth

**Минусы**:
- Непредсказуемость - поведение позиций может внезапно измениться
- Риск: более агрессивный callback может закрыть позицию раньше

#### Рекомендация:
**Вариант A** (зафиксировать) - более безопасный
**Обоснование**: Trailing Stop - это часть стратегии позиции, зафиксированная при входе. Изменение callback во время жизни позиции может привести к неожиданному поведению.

---

### 5.4 Сценарий: Миграция существующих позиций

#### Проблема:
```
1. Миграция добавляет поля в monitoring.positions:
   - trailing_activation_percent NUMERIC(5,2)
   - trailing_callback_percent NUMERIC(5,2)

2. Существующие позиции имеют NULL в этих полях

3. При рестарте бота:
   - Загружаются позиции из БД
   - position.trailing_activation_percent = NULL
   - Что делать?
```

#### Возможные решения:

**Вариант A: Data migration script**:
```sql
-- При добавлении полей - сразу заполнить текущими значениями из .env
ALTER TABLE monitoring.positions
ADD COLUMN trailing_activation_percent NUMERIC(5,2),
ADD COLUMN trailing_callback_percent NUMERIC(5,2);

-- Заполнить текущими значениями для активных позиций
UPDATE monitoring.positions
SET
    trailing_activation_percent = 2.0,  -- Из текущего .env
    trailing_callback_percent = 0.5
WHERE status = 'OPEN'
  AND (trailing_activation_percent IS NULL OR trailing_callback_percent IS NULL);

-- Сделать NOT NULL после миграции
ALTER TABLE monitoring.positions
ALTER COLUMN trailing_activation_percent SET NOT NULL,
ALTER COLUMN trailing_callback_percent SET NOT NULL;
```

**Вариант B: Application-level fallback**:
```python
# В create_trailing_stop():
activation_percent = position.trailing_activation_percent
if activation_percent is None:
    # Legacy позиция - использовать fallback
    logger.warning(f"{symbol}: Legacy position without trailing params, using .env fallback")
    activation_percent = self.config.activation_percent
```

**Вариант C: Восстановление из trailing_stop_states**:
```python
# Попытаться восстановить из TS state
ts_state = await self.repository.get_trailing_stop_state(symbol, exchange)
if ts_state:
    activation_percent = ts_state['activation_percent']
    callback_percent = ts_state['callback_percent']
else:
    # Fallback на .env
    activation_percent = self.config.activation_percent
```

#### Рекомендация:
**Комбинация A + B**:
1. Data migration для заполнения текущих позиций (Вариант A)
2. Application-level fallback на случай NULL (Вариант B)
3. Логирование WARNING при использовании fallback (для мониторинга)

---

### 5.5 Сценарий: Fallback при недоступности БД

#### Проблема:
```
1. БД недоступна или таблица monitoring.params пустая
2. ParamsManager.get_params('binance') - что вернуть?
3. Бот должен продолжить работу или остановиться?
```

#### Стратегия Fallback:

```python
class ParamsManager:
    async def get_params(self, exchange: str) -> ExchangeParams:
        try:
            # 1. Попытка загрузки из БД
            params = await self.repository.get_exchange_params(exchange)
            if params:
                logger.debug(f"✅ Loaded params for {exchange} from DB")
                return params
        except Exception as e:
            logger.error(f"❌ DB error loading params for {exchange}: {e}")

        # 2. Fallback на .env
        logger.warning(f"⚠️  Using .env fallback for {exchange} (DB unavailable)")
        return ExchangeParams(
            exchange=exchange,
            stop_loss_percent=self.config.trading.stop_loss_percent,
            trailing_activation_percent=self.config.trading.trailing_activation_percent,
            trailing_callback_percent=self.config.trading.trailing_callback_percent
        )
```

**Уровни деградации**:
1. ✅ **Ideal**: Параметры из `monitoring.params` (per-exchange)
2. ⚠️ **Degraded**: Параметры из `.env` (глобальные, но бот работает)
3. ❌ **Failed**: Бот не может создавать позиции (критичная ошибка)

**Рекомендация**: Уровень 2 (Degraded) приемлем для production
**Обоснование**: Лучше использовать fallback параметры, чем прекратить торговлю

---

## 6. ПРОЕКТИРОВАНИЕ НОВЫХ КОМПОНЕНТОВ

### 6.1 ParamsManager

#### Назначение
Централизованное управление trading параметрами с загрузкой из БД и fallback на .env

#### Интерфейс

```python
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

@dataclass
class ExchangeParams:
    """Per-exchange trading parameters"""
    exchange: str
    stop_loss_percent: Decimal
    trailing_activation_percent: Decimal
    trailing_callback_percent: Decimal
    updated_at: Optional[datetime] = None


class ParamsManager:
    """
    Manages exchange-specific trading parameters

    Load order:
    1. Try database (monitoring.params table)
    2. Fallback to .env if DB unavailable

    Caching:
    - 5-minute TTL cache to reduce DB load
    - Invalidate on explicit update
    """

    def __init__(self, repository, config):
        self.repository = repository
        self.config = config  # Fallback
        self._cache: Dict[str, ExchangeParams] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = 300  # 5 minutes

    async def get_params(self, exchange: str) -> ExchangeParams:
        """
        Get trading params for exchange

        Args:
            exchange: Exchange name ('binance', 'bybit')

        Returns:
            ExchangeParams with stop loss and trailing stop settings
        """
        # 1. Check cache
        if self._is_cached(exchange):
            return self._cache[exchange]

        # 2. Try load from database
        try:
            params = await self.repository.get_exchange_params(exchange)
            if params:
                self._update_cache(exchange, params)
                return params
        except Exception as e:
            logger.error(f"Failed to load params from DB for {exchange}: {e}")

        # 3. Fallback to .env
        logger.warning(f"Using .env fallback for {exchange}")
        return self._get_fallback_params(exchange)

    async def get_stop_loss_percent(self, exchange: str) -> Decimal:
        """Shortcut: Get only SL percent"""
        params = await self.get_params(exchange)
        return params.stop_loss_percent

    async def get_trailing_activation_percent(self, exchange: str) -> Decimal:
        """Shortcut: Get only TS activation percent"""
        params = await self.get_params(exchange)
        return params.trailing_activation_percent

    async def get_trailing_callback_percent(self, exchange: str) -> Decimal:
        """Shortcut: Get only TS callback percent"""
        params = await self.get_params(exchange)
        return params.trailing_callback_percent

    def _is_cached(self, exchange: str) -> bool:
        """Check if cached and not expired"""
        if exchange not in self._cache:
            return False

        cache_age = (datetime.now() - self._cache_time[exchange]).total_seconds()
        return cache_age < self._cache_ttl

    def _update_cache(self, exchange: str, params: ExchangeParams):
        """Update cache with fresh params"""
        self._cache[exchange] = params
        self._cache_time[exchange] = datetime.now()

    def invalidate_cache(self, exchange: Optional[str] = None):
        """Invalidate cache (all or specific exchange)"""
        if exchange:
            self._cache.pop(exchange, None)
            self._cache_time.pop(exchange, None)
        else:
            self._cache.clear()
            self._cache_time.clear()

    def _get_fallback_params(self, exchange: str) -> ExchangeParams:
        """Return params from .env (fallback)"""
        return ExchangeParams(
            exchange=exchange,
            stop_loss_percent=self.config.trading.stop_loss_percent,
            trailing_activation_percent=self.config.trading.trailing_activation_percent,
            trailing_callback_percent=self.config.trading.trailing_callback_percent
        )
```

#### Использование

```python
# main.py - инициализация
params_manager = ParamsManager(repository, config)

# Передать в PositionManager
position_manager = PositionManager(
    config=config,
    exchanges=exchanges,
    repository=repository,
    params_manager=params_manager,  # ← НОВЫЙ ПАРАМЕТР
    event_router=event_router
)

# position_manager.py - использование
exchange_params = await self.params_manager.get_params(request.exchange)
stop_loss_percent = exchange_params.stop_loss_percent
```

---

### 6.2 Database Schema Changes

#### Новая таблица: monitoring.params

```sql
CREATE TABLE monitoring.params (
    exchange VARCHAR(20) PRIMARY KEY,
    stop_loss_percent NUMERIC(5,2) NOT NULL,
    trailing_activation_percent NUMERIC(5,2) NOT NULL,
    trailing_callback_percent NUMERIC(5,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_stop_loss_percent CHECK (stop_loss_percent > 0 AND stop_loss_percent <= 50),
    CONSTRAINT check_activation_percent CHECK (trailing_activation_percent >= 0 AND trailing_activation_percent <= 50),
    CONSTRAINT check_callback_percent CHECK (trailing_callback_percent >= 0 AND trailing_callback_percent <= 50)
);

-- Indexes
CREATE INDEX idx_params_exchange ON monitoring.params(exchange);

-- Initial data (from current .env defaults)
INSERT INTO monitoring.params (exchange, stop_loss_percent, trailing_activation_percent, trailing_callback_percent)
VALUES
    ('binance', 4.0, 2.0, 0.5),
    ('bybit', 4.0, 2.0, 0.5);

-- Comments
COMMENT ON TABLE monitoring.params IS 'Per-exchange trading parameters';
COMMENT ON COLUMN monitoring.params.stop_loss_percent IS 'Stop loss percentage (e.g., 4.0 = 4%)';
COMMENT ON COLUMN monitoring.params.trailing_activation_percent IS 'Profit percentage to activate trailing stop (e.g., 2.0 = 2%)';
COMMENT ON COLUMN monitoring.params.trailing_callback_percent IS 'Trailing stop callback distance (e.g., 0.5 = 0.5%)';
```

#### Изменение таблицы: monitoring.positions

```sql
-- Add new columns
ALTER TABLE monitoring.positions
ADD COLUMN trailing_activation_percent NUMERIC(5,2),
ADD COLUMN trailing_callback_percent NUMERIC(5,2);

-- Data migration: fill existing positions with current .env values
UPDATE monitoring.positions
SET
    trailing_activation_percent = 2.0,
    trailing_callback_percent = 0.5
WHERE status = 'OPEN'
  AND (trailing_activation_percent IS NULL OR trailing_callback_percent IS NULL);

-- Make NOT NULL after migration (optional - can keep nullable for flexibility)
-- ALTER TABLE monitoring.positions
-- ALTER COLUMN trailing_activation_percent SET NOT NULL,
-- ALTER COLUMN trailing_callback_percent SET NOT NULL;

-- Comments
COMMENT ON COLUMN monitoring.positions.trailing_activation_percent IS
    'Trailing stop activation percent for THIS position (saved on creation)';
COMMENT ON COLUMN monitoring.positions.trailing_callback_percent IS
    'Trailing stop callback percent for THIS position (saved on creation)';
```

---

### 6.3 Repository Methods

#### Файл: `database/repository.py`

```python
# Добавить новые методы:

async def get_exchange_params(self, exchange: str) -> Optional[Dict]:
    """
    Load trading params for specific exchange

    Args:
        exchange: Exchange name ('binance', 'bybit')

    Returns:
        Dict with params or None if not found
    """
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                exchange,
                stop_loss_percent,
                trailing_activation_percent,
                trailing_callback_percent,
                updated_at
            FROM monitoring.params
            WHERE exchange = $1
        """, exchange)

        if row:
            return dict(row)
        return None


async def save_exchange_params(self, params: Dict):
    """
    Save or update trading params for exchange

    Args:
        params: Dict with exchange, stop_loss_percent, trailing_activation_percent, trailing_callback_percent
    """
    async with self.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO monitoring.params (
                exchange,
                stop_loss_percent,
                trailing_activation_percent,
                trailing_callback_percent,
                updated_at
            )
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (exchange)
            DO UPDATE SET
                stop_loss_percent = EXCLUDED.stop_loss_percent,
                trailing_activation_percent = EXCLUDED.trailing_activation_percent,
                trailing_callback_percent = EXCLUDED.trailing_callback_percent,
                updated_at = NOW()
        """,
        params['exchange'],
        params['stop_loss_percent'],
        params['trailing_activation_percent'],
        params['trailing_callback_percent']
        )
```

---

## 7. ДЕТАЛЬНЫЙ ПЛАН МИГРАЦИИ

### ФАЗА 0: Подготовка (ТЕКУЩИЙ ЭТАП)
**Статус**: ✅ ЗАВЕРШЕНО
**Тип**: Исследование, БЕЗ изменений кода

**Задачи**:
- [x] Полная инвентаризация использования параметров
- [x] Анализ жизненного цикла позиции
- [x] Проектирование новых компонентов
- [ ] Review плана с командой
- [ ] Утверждение подхода

**Результат**: Утвержденный детальный план миграции

**Риски**: ОТСУТСТВУЮТ (только планирование)

---

### ФАЗА 1: Изменения БД
**Статус**: ⬜ PENDING
**Критичность**: СРЕДНЯЯ
**Estimated time**: 1-2 часа

**Задачи**:
1. Создать SQL migration script:
   ```sql
   -- migrations/add_params_table.sql
   CREATE TABLE monitoring.params (...);
   INSERT INTO monitoring.params VALUES (...);
   ALTER TABLE monitoring.positions ADD COLUMN trailing_activation_percent ...;
   UPDATE monitoring.positions SET trailing_activation_percent = 2.0 ...;
   ```

2. Протестировать migration на копии БД:
   - Создать копию production БД
   - Применить migration
   - Проверить данные
   - Rollback test

3. Создать rollback script:
   ```sql
   -- migrations/rollback_params_table.sql
   ALTER TABLE monitoring.positions DROP COLUMN trailing_activation_percent;
   ALTER TABLE monitoring.positions DROP COLUMN trailing_callback_percent;
   DROP TABLE monitoring.params;
   ```

**Проверки**:
- [ ] Migration применяется без ошибок
- [ ] Rollback работает
- [ ] Существующие позиции имеют заполненные значения
- [ ] Constraints работают (проверить невалидные значения)
- [ ] Indexes созданы

**Deployment**:
1. Остановить бот
2. Создать backup БД
3. Применить migration
4. Проверить таблицы и данные
5. Запустить бот (старый код продолжит работать)

**Риски**:
- 🟡 НИЗКИЕ - только схема, логика не меняется
- Downtime: ~5 минут

**Rollback plan**:
- Остановить бот
- Запустить rollback script
- Восстановить из backup (worst case)

---

### ФАЗА 2: ParamsManager
**Статус**: ⬜ PENDING
**Критичность**: СРЕДНЯЯ
**Estimated time**: 2-3 часа

**Задачи**:
1. Создать файл `core/params_manager.py`:
   - Класс `ExchangeParams` (dataclass)
   - Класс `ParamsManager` (полная реализация из раздела 6.1)

2. Добавить repository methods:
   - `get_exchange_params(exchange)` в `database/repository.py`
   - `save_exchange_params(params)` в `database/repository.py`

3. Написать unit tests:
   - `tests/unit/test_params_manager.py`
   - Тест загрузки из БД
   - Тест fallback на .env
   - Тест кэширования
   - Тест invalid exchange

4. Добавить инициализацию в `main.py`:
   ```python
   # После создания repository
   params_manager = ParamsManager(repository, config)

   # Передать в PositionManager
   position_manager = PositionManager(
       # ... existing params ...
       params_manager=params_manager  # ← НОВЫЙ ПАРАМЕТР
   )
   ```

**Проверки**:
- [ ] ParamsManager загружает params из БД
- [ ] Fallback на .env работает (отключить БД и проверить)
- [ ] Cache работает (проверить логи - только 1 DB query за 5 минут)
- [ ] Все unit tests проходят
- [ ] Бот запускается БЕЗ ошибок

**Deployment**:
- Код добавлен, но **НЕ используется** в бизнес-логике
- Бот продолжает работать как раньше
- Риски: МИНИМАЛЬНЫЕ

**Rollback plan**:
- Удалить инициализацию из `main.py`
- Удалить `core/params_manager.py`

---

### ФАЗА 3: Изменение создания позиций
**Статус**: ⬜ PENDING
**Критичность**: 🔴 КРИТИЧЕСКАЯ
**Estimated time**: 4-6 часов

#### 3.1 PositionManager.open_position()

**Файл**: `position_manager.py`
**Строки**: 1073-1108

**Изменения**:

```python
# БЫЛО (строка 1073):
stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent

# СТАНЕТ:
# 1. Загрузить params для биржи
exchange_params = await self.params_manager.get_params(request.exchange)

# 2. Получить параметры
stop_loss_percent = request.stop_loss_percent or exchange_params.stop_loss_percent
trailing_activation_percent = exchange_params.trailing_activation_percent
trailing_callback_percent = exchange_params.trailing_callback_percent

# 3. Передать в atomic_manager (строка 1100):
atomic_result = await atomic_manager.open_position_atomic(
    # ... existing params ...
    stop_loss_percent=float(stop_loss_percent),
    trailing_activation_percent=float(trailing_activation_percent),  # ← НОВЫЙ ПАРАМЕТР
    trailing_callback_percent=float(trailing_callback_percent)       # ← НОВЫЙ ПАРАМЕТР
)
```

**Задачи**:
1. Изменить `position_manager.py:1073` - загрузка params
2. Изменить `atomic_position_manager.py:200` - добавить параметры в signature
3. Изменить `repository.create_position()` - сохранять trailing params
4. Изменить все другие места создания позиций:
   - `position_manager.py:497`
   - `position_manager.py:792`
   - `position_manager.py:854`
   - `position_manager.py:1340`

**Проверки**:
- [ ] Новые позиции на Binance используют Binance params
- [ ] Новые позиции на Bybit используют Bybit params
- [ ] БД records имеют trailing_activation_percent, trailing_callback_percent
- [ ] Fallback работает если params нет в БД
- [ ] Старые позиции НЕ затронуты (уже созданные)

**Тестирование**:
1. Unit tests:
   - `test_open_position_uses_exchange_params()`
   - `test_open_position_fallback_to_env()`
   - `test_open_position_saves_trailing_params()`

2. Integration tests:
   - Создать позицию на Binance → проверить БД
   - Создать позицию на Bybit → проверить БД
   - Изменить params → создать новую позицию → проверить новые params

3. Manual testing:
   - Testnet Binance: создать реальную позицию
   - Testnet Bybit: создать реальную позицию
   - Проверить БД записи

**Deployment**:
1. Code review (ОБЯЗАТЕЛЬНО!)
2. Staged rollout:
   - Развернуть на testnet
   - Мониторить 24 часа
   - Создать несколько тестовых позиций
   - Проверить БД
   - Развернуть на production
3. Мониторинг после деплоя:
   - Проверить логи создания позиций
   - Проверить БД records
   - Alert если trailing params = NULL

**Риски**:
- 🔴 ВЫСОКИЕ - изменяет критичную логику защиты капитала
- При ошибке позиции могут создаваться без trailing params

**Mitigation**:
- Тщательное тестирование
- Code review
- Staged rollout (testnet → production)
- Monitoring и alerts

**Rollback plan**:
1. Git revert изменений
2. Redeploy предыдущей версии
3. Проверка:
   - Новые позиции создаются
   - Trailing params могут быть NULL (не критично, fallback сработает)

---

### ФАЗА 4: Изменение TrailingStop
**Статус**: ⬜ PENDING
**Критичность**: 🔴 КРИТИЧЕСКАЯ
**Estimated time**: 3-5 часов

#### 4.1 TrailingStopInstance - добавление полей

**Файл**: `protection/trailing_stop.py`
**Строки**: 66-99

**Изменения**:

```python
@dataclass
class TrailingStopInstance:
    symbol: str
    entry_price: Decimal
    current_price: Decimal
    highest_price: Decimal
    lowest_price: Decimal

    # ... existing fields ...

    # ← НОВЫЕ ПОЛЯ:
    activation_percent: Decimal = Decimal('0')  # From position, not config!
    callback_percent: Decimal = Decimal('0')    # From position, not config!
```

#### 4.2 create_trailing_stop() - использование params из позиции

**Файл**: `protection/trailing_stop.py`
**Метод**: `create_trailing_stop()`
**Строки**: 446-548

**Изменения**:

```python
async def create_trailing_stop(self,
                               symbol: str,
                               side: str,
                               entry_price: float,
                               quantity: float,
                               initial_stop: Optional[float] = None,
                               position_params: Optional[Dict] = None):  # ← НОВЫЙ ПАРАМЕТР!
    # ...

    # Get params from position or fallback to config
    if position_params:
        activation_percent = Decimal(str(position_params['trailing_activation_percent']))
        callback_percent = Decimal(str(position_params['trailing_callback_percent']))
        logger.debug(f"{symbol}: Using trailing params from position: activation={activation_percent}%, callback={callback_percent}%")
    else:
        # Fallback для legacy позиций
        logger.warning(f"{symbol}: No trailing params in position, using config fallback")
        activation_percent = self.config.activation_percent
        callback_percent = self.config.callback_percent

    ts = TrailingStopInstance(
        # ... existing fields ...
        activation_percent=activation_percent,  # ← НОВОЕ ПОЛЕ
        callback_percent=callback_percent       # ← НОВОЕ ПОЛЕ
    )

    # Calculate activation price from position-specific params
    if side == 'long':
        ts.activation_price = ts.entry_price * (1 + activation_percent / 100)
    else:
        ts.activation_price = ts.entry_price * (1 - activation_percent / 100)

    # ... rest of method ...
```

#### 4.3 _get_trailing_distance() - использование params из instance

**Файл**: `protection/trailing_stop.py`
**Метод**: `_get_trailing_distance()`
**Строки**: 901-927

**Изменения**:

```python
def _get_trailing_distance(self, ts: TrailingStopInstance) -> Decimal:
    # ... step activation logic (без изменений) ...

    # БЫЛО (строка 926):
    # return self.config.callback_percent

    # СТАНЕТ:
    return ts.callback_percent  # ← ИЗ INSTANCE, НЕ CONFIG!
```

#### 4.4 _save_state() - сохранение params из instance

**Файл**: `protection/trailing_stop.py`
**Метод**: `_save_state()`
**Строки**: 144-223

**Изменения**:

```python
state_data = {
    # ... existing fields ...

    # БЫЛО (строки 200-201):
    # 'activation_percent': float(self.config.activation_percent),
    # 'callback_percent': float(self.config.callback_percent),

    # СТАНЕТ:
    'activation_percent': float(ts.activation_percent),  # ← ИЗ INSTANCE!
    'callback_percent': float(ts.callback_percent),      # ← ИЗ INSTANCE!

    # ... other fields ...
}
```

#### 4.5 Обновление вызовов create_trailing_stop()

**Файл**: `position_manager.py`

Найти ВСЕ вызовы `trailing_manager.create_trailing_stop()` и добавить `position_params`:

```python
# Пример (точные строки зависят от реального кода):
await self.trailing_managers[exchange_name].create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=float(position.entry_price),
    quantity=float(position.quantity),
    initial_stop=float(stop_loss_price),
    position_params={  # ← НОВЫЙ ПАРАМЕТР!
        'trailing_activation_percent': position.trailing_activation_percent,
        'trailing_callback_percent': position.trailing_callback_percent
    }
)
```

**Задачи**:
1. Изменить `TrailingStopInstance` - добавить поля
2. Изменить `create_trailing_stop()` - принимать position_params
3. Изменить `_get_trailing_distance()` - использовать ts.callback_percent
4. Изменить `_save_state()` - сохранять из instance
5. Обновить ВСЕ вызовы create_trailing_stop() в position_manager.py
6. Добавить fallback логику для legacy позиций (params = None)

**Проверки**:
- [ ] Новые TS используют params из позиции
- [ ] После рестарта TS использует правильные params
- [ ] Legacy позиции (без params) используют config fallback
- [ ] TS activation работает с правильным порогом
- [ ] TS update использует правильный callback
- [ ] state_data в БД содержит правильные проценты

**Тестирование**:
1. Unit tests:
   - `test_ts_uses_position_params()`
   - `test_ts_fallback_to_config_for_legacy()`
   - `test_ts_restore_from_db_uses_saved_params()`

2. Integration tests:
   - Создать позицию → активировать TS → проверить params
   - Рестарт бота → восстановить TS → проверить params
   - Legacy позиция (без params) → проверить fallback

3. Manual testing:
   - Создать позицию на testnet
   - Дождаться активации TS
   - Перезапустить бота
   - Проверить что TS работает с теми же params

**Deployment**:
1. Code review (ОБЯЗАТЕЛЬНО!)
2. Testing на testnet (минимум 24 часа)
3. Production deployment
4. Мониторинг:
   - Логи активации TS
   - БД state_data
   - Alerts при fallback на config

**Риски**:
- 🔴 ВЫСОКИЕ - изменяет TS логику
- При ошибке TS может использовать неправильные params

**Mitigation**:
- Fallback на config для legacy позиций
- Extensive testing
- Code review
- Staged rollout

**Rollback plan**:
1. Git revert изменений
2. Redeploy предыдущей версии
3. Эффект:
   - TS снова будут использовать config (глобальный)
   - Новые TS instances потеряют position-specific params
   - Но сработает fallback - бот продолжит работу

---

## 8. ОТВЕТЫ НА КРИТИЧНЫЕ ВОПРОСЫ

### Про текущее состояние:

1. ✅ **Сколько ВСЕГО мест использования каждого параметра?**
   - `STOP_LOSS_PERCENT`: 12 мест (7 критичных)
   - `TRAILING_ACTIVATION_PERCENT`: 8 мест (5 критичных)
   - `TRAILING_CALLBACK_PERCENT`: 7 мест (5 критичных)

2. ✅ **Есть ли поле exchange в таблице positions?**
   - ДА, есть: `exchange = Column(String(50), nullable=False, index=True)`
   - Используется для идентификации биржи позиции

3. ❌ **Сохраняется ли trailing_activation_percent сейчас?**
   - НЕТ в `monitoring.positions` (таблица НЕ имеет этих полей)
   - ДА в `monitoring.trailing_stop_states` (но из глобального config!)

4. ✅ **Как восстанавливается TS после рестарта?**
   - Вызывается `_restore_state(symbol, exchange)` для каждой активной позиции
   - Загружается `trailing_stop_state` из БД
   - Восстанавливается `activation_price` (рассчитанная при создании)
   - ⚠️ ПРОБЛЕМА: Для новых позиций без restore - используется глобальный config

### Про изменения:

5. ✅ **Все ли места использования найдены?**
   - ДА, проведена полная инвентаризация через grep
   - Найдены все usage в core files
   - Documented в таблицах раздела 1

6. ✅ **Можно ли получить exchange в каждой точке использования?**
   - ДА:
     - При создании позиции: `request.exchange` доступен
     - В position object: `position.exchange` доступен
     - В TS manager: `self.exchange_name` доступен

7. ⚠️ **Достаточно ли БД изменений для решения?**
   - Требуется:
     - ✅ Новая таблица `monitoring.params` - спроектирована
     - ✅ Новые поля в `monitoring.positions` - спроектированы
     - ⚠️ Нужна миграция данных для существующих позиций
     - ✅ Repository methods - спроектированы

8. ✅ **Учтены ли все edge cases?**
   - ДА, проанализированы в разделе 5:
     - Создание позиций на разных биржах
     - Рестарт бота
     - Изменение params во время работы
     - Миграция legacy позиций
     - Fallback при недоступности БД

### Про риски:

9. ✅ **Что самое рискованное в этой миграции?**
   - **ФАЗА 3** (изменение создания позиций) - самая критичная
   - Риск: Позиции могут создаваться без trailing params
   - Mitigation: Fallback на config + extensive testing

10. ✅ **Есть ли plan B если что-то пойдет не так?**
    - ДА, для каждой фазы:
      - ФАЗА 1: Rollback SQL script
      - ФАЗА 2: Удалить ParamsManager initialization
      - ФАЗА 3: Git revert + redeploy
      - ФАЗА 4: Git revert + redeploy
    - Application-level fallback: Использование .env параметров
    - Database-level fallback: Восстановление из backup

---

## 9. ФИНАЛЬНЫЕ РЕКОМЕНДАЦИИ

### 9.1 Готовность к внедрению

**Статус**: ⚠️ **ТРЕБУЕТ REVIEW И УТВЕРЖДЕНИЯ**

**Что готово**:
- [x] Полная инвентаризация использования параметров
- [x] Детальный анализ жизненного цикла позиций
- [x] Проектирование ParamsManager
- [x] SQL migrations спроектированы
- [x] Детальный план миграции (4 фазы)
- [x] Анализ рисков и mitigation стратегии
- [x] Rollback планы для каждой фазы

**Что требуется**:
- [ ] Review этого отчета командой
- [ ] Утверждение архитектурного подхода
- [ ] Выбор варианта для callback_percent (A или B) - рекомендуется A
- [ ] Планирование downtime для БД миграции
- [ ] Подготовка testnet окружения

---

### 9.2 Последовательность действий

**Немедленно** (сейчас):
1. Review этого отчета
2. Обсуждение с командой
3. Утверждение плана

**После утверждения**:
1. ФАЗА 1: БД миграция (1-2 часа работы + 1 день мониторинга)
2. ФАЗА 2: ParamsManager (2-3 часа работы + тестирование)
3. Перерыв для review и тестирования (2-3 дня)
4. ФАЗА 3: Изменение создания позиций (4-6 часов + testnet тестирование 2-3 дня)
5. ФАЗА 4: Изменение TrailingStop (3-5 часов + testnet тестирование 2-3 дня)

**Total estimated time**: 2-3 недели (включая тестирование)

---

### 9.3 Критерии успеха

**После ФАЗЫ 1** (БД):
- [ ] Таблица `monitoring.params` создана и заполнена
- [ ] Поля в `monitoring.positions` добавлены и заполнены для активных позиций
- [ ] Старый код продолжает работать без изменений

**После ФАЗЫ 2** (ParamsManager):
- [ ] ParamsManager загружает данные из БД
- [ ] Fallback на .env работает
- [ ] Бот запускается без ошибок

**После ФАЗЫ 3** (PositionManager):
- [ ] Новые позиции используют per-exchange параметры
- [ ] БД records содержат trailing params
- [ ] Старые позиции НЕ затронуты

**После ФАЗЫ 4** (TrailingStop):
- [ ] TS использует params из позиции
- [ ] Recovery после рестарта работает правильно
- [ ] Legacy позиции работают через fallback

---

### 9.4 Мониторинг после внедрения

**Метрики для отслеживания**:
1. **Создание позиций**:
   - Логи: "Using params from DB for {exchange}"
   - Alert: "Using .env fallback" (должно быть редко)
   - БД: COUNT positions with trailing_activation_percent IS NOT NULL

2. **TS activation**:
   - Логи: "Using trailing params from position"
   - Alert: "No trailing params in position, using config fallback" (legacy позиции)
   - БД: trailing_stop_states.activation_percent distribution

3. **Errors**:
   - Alert: Failed to load params from DB
   - Alert: Position created without trailing params (NULL)
   - Alert: TS activation failed due to missing params

**Dashboards**:
- Процент позиций с per-exchange params vs fallback
- Распределение параметров по биржам
- Ошибки загрузки params

---

## 10. ПРИЛОЖЕНИЯ

### A. Файлы требующие изменений

| Файл | Тип изменения | Строки | Критичность | Описание |
|------|---------------|--------|-------------|----------|
| `database/migrations/add_params_table.sql` | **NEW** | ~50 | MEDIUM | SQL migration |
| `database/models.py` | MINOR | +10 | LOW | SQLAlchemy model (optional) |
| `database/repository.py` | MINOR | +30 | MEDIUM | Новые методы get/save params |
| `core/params_manager.py` | **NEW** | ~150 | HIGH | Новый компонент |
| `core/position_manager.py` | MAJOR | ~15 | **CRITICAL** | Использование ParamsManager |
| `core/atomic_position_manager.py` | MINOR | +2 | MEDIUM | Новые параметры в signature |
| `protection/trailing_stop.py` | MAJOR | ~30 | **CRITICAL** | Использование params из position |
| `main.py` | MINOR | +3 | LOW | Инициализация ParamsManager |
| `tests/unit/test_params_manager.py` | **NEW** | ~200 | HIGH | Unit tests |
| `tests/integration/test_per_exchange_params.py` | **NEW** | ~300 | HIGH | Integration tests |

**Всего**:
- Новых файлов: 4
- Изменяемых файлов: 6
- Критичных изменений: 2 файла (position_manager, trailing_stop)

---

### B. SQL Scripts

#### migration.sql
```sql
-- См. раздел 6.2
```

#### rollback.sql
```sql
ALTER TABLE monitoring.positions DROP COLUMN trailing_activation_percent;
ALTER TABLE monitoring.positions DROP COLUMN trailing_callback_percent;
DROP TABLE monitoring.params;
```

---

## КОНЕЦ ОТЧЕТА

**Prepared by**: Claude Code Assistant
**Date**: 2025-10-28
**Version**: 1.0
**Status**: ✅ Ready for Review

---

## NEXT STEPS

1. **Review** этого документа командой
2. **Обсуждение** архитектурных решений
3. **Утверждение** плана миграции
4. **Начало ФАЗЫ 1** после утверждения
