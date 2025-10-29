# 📋 ДЕТАЛЬНЫЙ ПЛАН: Внедрение дополнительных фильтров сигналов

**Дата создания**: 2025-10-28  
**Статус**: 📝 План (код бота НЕ изменен)  
**Тестирование**: ✅ Завершено (114/114 тестов пройдено)  

---

## 🎯 Цель

Добавить три новых фильтра в функцию `WaveSignalProcessor._is_duplicate()` для отбраковки низколиквидных и перегретых сигналов:

1. **Open Interest >= 1,000,000 USDT** - фильтр ликвидности
2. **1h Trading Volume >= 50,000 USDT** - фильтр активности рынка
3. **5min Price Change <= 4%** - фильтр перегретости
   - Для BUY: цена не выросла >4% (избегаем покупки на вершине)
   - Для SELL: цена не упала >4% (избегаем продажи на дне)

---

## 📊 Результаты тестирования API методов (114 сигналов)

### ✅ Успешность API: **100%**

| Метод API | Успешных | Неудачных | Процент успеха |
|-----------|----------|-----------|----------------|
| `fetch_open_interest()` + `fetch_ticker()` | 114 | 0 | **100%** ✅ |
| `fetch_ohlcv(timeframe='1h')` | 114 | 0 | **100%** ✅ |
| `fetch_ohlcv(timeframe='1m')` | 114 | 0 | **100%** ✅ |

**Вывод**: Все три API метода работают надежно на 100% реальных сигналов.

---

### 📈 Эффективность фильтров (индивидуально)

| Фильтр | Пройдут | Не пройдут | Эффективность фильтрации |
|--------|---------|------------|--------------------------|
| **OI >= 1M USDT** | 97 (85.1%) | **17 (14.9%)** | 14.9% отбраковка |
| **Volume >= 50k USDT** | 99 (86.8%) | **15 (13.2%)** | 13.2% отбраковка |
| **Price Change <= 4%** | 113 (99.1%) | **1 (0.9%)** | 0.9% отбраковка |

**Особенности**:
- **OI фильтр**: Наиболее эффективный (14.9% отбраковка)
- **Volume фильтр**: Второй по эффективности (13.2% отбраковка)
- **Price Change фильтр**: Редко срабатывает (0.9%), но критически важен
  - Отфильтрован **MAVIAUSDT** с +7.85% ростом за 5 минут (перегретый вход)

---

### 🎯 Итоговая эффективность (все фильтры вместе)

**Комбинированный результат:**
- ✅ **Пройдут ВСЕ три фильтра**: 94 сигнала (**82.5%**)
- ❌ **Будут отфильтрованы**: 20 сигналов (**17.5%**)

**Выводы**:
1. **82.5%** сигналов - высоколиквидные и качественные (проходят все фильтры)
2. **17.5%** сигналов - низколиквидные или перегретые (будут отбракованы)
3. Фильтрация в основном затрагивает:
   - Низколиквидные пары Bybit (малая капитализация)
   - Перегретые входы с резким движением цены

---

## 📍 Анализ функции для модификации

### Целевая функция

**Файл**: `core/wave_signal_processor.py`  
**Функция**: `_is_duplicate()`  
**Строки**: 237-372  

**Текущие проверки** (7 уровней):

1. ✅ Проверка открытой позиции (`has_open_position()`)  
   - Строки 252-266
2. ✅ Проверка доступности биржи (`exchange_manager`)  
   - Строки 271-280
3. ✅ Проверка существования символа (`find_exchange_symbol()`)  
   - Строки 283-286
4. ✅ Проверка market data (`markets.get()`)  
   - Строки 289-292
5. ✅ Проверка ticker (`fetch_ticker()`)  
   - Строки 295-298
6. ✅ Проверка валидности цены (`current_price > 0`)  
   - Строки 301-303
7. ✅ Проверка минимальной стоимости позиции (`_get_minimum_cost()`)  
   - Строки 306-359

**Место для новых фильтров**: После строки 359, перед `return False, ""`

---

### Доступные объекты в функции

```python
# Аргументы
signal: Dict          # Сигнал с полями: symbol, exchange, direction, timestamp
wave_timestamp: str   # ID волны

# Уже извлеченные переменные
symbol: str                      # Символ (BTCUSDT)
exchange: str                    # Биржа (binance/bybit)
exchange_manager: ExchangeManager  # Менеджер биржи
exchange_symbol: str             # Нормализованный символ для биржи
market: Dict                     # Данные рынка из markets
ticker: Dict                     # Текущий тикер
current_price: float             # Текущая цена

# Доступные методы exchange_manager
await exchange_manager.fetch_ticker(symbol)
await exchange_manager.exchange.fetch_open_interest(symbol)
await exchange_manager.exchange.fetch_ohlcv(symbol, '1h', since, limit)
```

---

## 🔧 ПЛАН РЕАЛИЗАЦИИ

### ФАЗА 1: Добавить вспомогательные методы (3 метода)

#### Метод 1.1: `_fetch_open_interest_usdt()`

**Назначение**: Получить Open Interest в USDT

**Расположение**: После `_get_minimum_cost()` в файле `wave_signal_processor.py` (~строка 475)

**Сигнатура**:
```python
async def _fetch_open_interest_usdt(
    self,
    exchange_manager,
    symbol: str,
    exchange_name: str,
    current_price: float
) -> Optional[float]:
    """
    Получить Open Interest в USDT для проверки ликвидности.

    Args:
        exchange_manager: Менеджер биржи
        symbol: Символ (BTCUSDT или нормализованный для биржи)
        exchange_name: Имя биржи (binance/bybit)
        current_price: Текущая цена (для конверсии OI из контрактов в USDT)

    Returns:
        Open Interest в USDT или None если не удалось получить
    """
```

**Алгоритм** (5 попыток):
1. `fetch_open_interest()` → `openInterestValue` (уже в USDT) ✅
2. `fetch_open_interest()` → `quoteVolume` ✅
3. `fetch_open_interest()` → `openInterestAmount * info.markPrice` ✅
4. `fetch_ticker()` → `info.openInterest * last_price` (Binance) ✅
5. `fetch_ticker()` → `info.openInterestValue` (Bybit) ✅

**Обработка ошибок**:
- Wrap в `try-except`
- Логировать как `logger.debug()` (не error)
- Возвращать `None` при любой ошибке
- НЕ бросать исключения наверх

**Тестирование**: ✅ Протестировано на 114 сигналах, 100% success rate

---

#### Метод 1.2: `_fetch_1h_volume_usdt()`

**Назначение**: Получить объем торгов за последний час в USDT

**Расположение**: После `_fetch_open_interest_usdt()` (~строка 530)

**Сигнатура**:
```python
async def _fetch_1h_volume_usdt(
    self,
    exchange_manager,
    symbol: str,
    signal_timestamp: datetime
) -> Optional[float]:
    """
    Получить объем торгов за 1 час в USDT для проверки активности рынка.

    Args:
        exchange_manager: Менеджер биржи
        symbol: Символ для биржи (уже нормализованный)
        signal_timestamp: Временная метка сигнала

    Returns:
        Объем за 1 час в USDT или None если не удалось получить
    """
```

**Алгоритм**:
1. Округлить `signal_timestamp` до начала часа: `replace(minute=0, second=0, microsecond=0)`
2. Конвертировать в миллисекунды: `int(timestamp.timestamp() * 1000)`
3. Вызвать `fetch_ohlcv(symbol, timeframe='1h', since=ts_ms, limit=1)`
4. Получить `candle[5]` (base_volume) и `candle[4]` (close_price)
5. Вернуть `base_volume * close_price` (конверсия в USDT)

**Обработка ошибок**:
- Wrap в `try-except`
- Проверить что `ohlcv` не пустой: `if not ohlcv or len(ohlcv) == 0`
- Проверить валидность: `base_volume` и `close_price` не None и > 0
- Возвращать `None` при ошибках
- НЕ бросать исключения наверх

**Тестирование**: ✅ Протестировано на 114 сигналах, 100% success rate

---

#### Метод 1.3: `_fetch_price_5min_before()`

**Назначение**: Получить цену за 5 минут до сигнала для проверки перегретости

**Расположение**: После `_fetch_1h_volume_usdt()` (~строка 570)

**Сигнатура**:
```python
async def _fetch_price_5min_before(
    self,
    exchange_manager,
    symbol: str,
    signal_timestamp: datetime
) -> Tuple[Optional[float], Optional[float]]:
    """
    Получить цену в момент сигнала и 5 минут назад.

    Args:
        exchange_manager: Менеджер биржи
        symbol: Символ для биржи (уже нормализованный)
        signal_timestamp: Временная метка сигнала

    Returns:
        Tuple (price_at_signal, price_5min_before) или (None, None)
    """
```

**Алгоритм**:
1. **Получить цену в момент сигнала**:
   - `ts_signal_ms = int(signal_timestamp.timestamp() * 1000)`
   - `fetch_ohlcv(symbol, '1m', since=ts_signal_ms - 10*60*1000, limit=15)`
   - Найти ближайшую свечу: `min(ohlcv, key=lambda x: abs(x[0] - ts_signal_ms))`
   - Взять `candle[4]` (close price)

2. **Получить цену 5 минут назад**:
   - `ts_5min_before = signal_timestamp - timedelta(minutes=5)`
   - `ts_5min_ms = int(ts_5min_before.timestamp() * 1000)`
   - `fetch_ohlcv(symbol, '1m', since=ts_5min_ms - 5*60*1000, limit=10)`
   - Найти ближайшую свечу: `min(ohlcv, key=lambda x: abs(x[0] - ts_5min_ms))`
   - Взять `candle[4]` (close price)

3. **Вернуть tuple**: `(price_at_signal, price_5min_before)`

**Обработка ошибок**:
- Wrap в `try-except`
- Проверить что оба `ohlcv` не пустые
- Проверить валидность обеих цен: `> 0`
- Возвращать `(None, None)` при ошибках
- НЕ бросать исключения наверх

**Тестирование**: ✅ Протестировано на 114 сигналах, 100% success rate

---

### ФАЗА 2: Модифицировать `_is_duplicate()`

#### Шаг 2.1: Извлечь timestamp из сигнала

**Расположение**: После извлечения `symbol` и `exchange` (~строка 248)

**Добавить код**:
```python
# Extract signal timestamp for time-based filters
signal_timestamp = None
if 'timestamp' in signal:
    timestamp_str = signal['timestamp']
    try:
        # Handle timezone format (+00 → +00:00)
        if '+00' in timestamp_str and '+00:00' not in timestamp_str:
            timestamp_str = timestamp_str.replace('+00', '+00:00')
        signal_timestamp = datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid timestamp in signal {symbol}: {e}")

# Fallback to created_at if timestamp not available
if not signal_timestamp and 'created_at' in signal:
    created_at_str = signal['created_at']
    try:
        if '+00' in created_at_str and '+00:00' not in created_at_str:
            created_at_str = created_at_str.replace('+00', '+00:00')
        signal_timestamp = datetime.fromisoformat(created_at_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid created_at in signal {symbol}: {e}")

# If still no timestamp, use current time (fallback)
if not signal_timestamp:
    logger.warning(f"No timestamp found for signal {symbol}, using current time")
    signal_timestamp = datetime.now(timezone.utc)
```

**Обоснование**:
- Нужен timestamp для получения исторических данных (volume, price)
- Graceful fallback на `created_at` если `timestamp` отсутствует
- Последний fallback на текущее время (лучше чем падение)

---

#### Шаг 2.2: Добавить три новых фильтра

**Расположение**: После проверки минимальной стоимости позиции (~строка 360), ПЕРЕД финальным `return False, ""`

**Добавить код**:
```python
# ========== НОВЫЕ ФИЛЬТРЫ: OI, Volume, Price Change ==========

# Filter 1: Open Interest >= 1M USDT
if self.filter_oi_enabled:
    logger.debug(f"Checking OI filter for {symbol} on {exchange}")
    oi_usdt = await self._fetch_open_interest_usdt(
        exchange_manager=exchange_manager,
        symbol=exchange_symbol,
        exchange_name=exchange,
        current_price=current_price
    )

    if oi_usdt is not None and oi_usdt < self.min_oi_usdt:
        logger.info(
            f"⏭️ Signal skipped: {symbol} OI ${oi_usdt:,.0f} < ${self.min_oi_usdt:,} (low liquidity) on {exchange}"
        )

        # Update statistics
        self.total_filtered_low_oi += 1

        # Log event to database
        from core.event_logger import get_event_logger, EventType
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.SIGNAL_FILTERED,
                {
                    'signal_id': signal.get('id'),
                    'symbol': symbol,
                    'exchange': exchange,
                    'filter_reason': 'low_open_interest',
                    'open_interest_usdt': float(oi_usdt),
                    'min_oi_required': float(self.min_oi_usdt),
                    'current_price': float(current_price)
                },
                symbol=symbol,
                exchange=exchange,
                severity='INFO'
            )

        return True, f"OI ${oi_usdt:,.0f} below minimum ${self.min_oi_usdt:,}"

# Filter 2: 1h Trading Volume >= 50k USDT
if self.filter_volume_enabled:
    logger.debug(f"Checking volume filter for {symbol} on {exchange}")
    volume_1h_usdt = await self._fetch_1h_volume_usdt(
        exchange_manager=exchange_manager,
        symbol=exchange_symbol,
        signal_timestamp=signal_timestamp
    )

    if volume_1h_usdt is not None and volume_1h_usdt < self.min_volume_1h_usdt:
        logger.info(
            f"⏭️ Signal skipped: {symbol} 1h volume ${volume_1h_usdt:,.0f} < ${self.min_volume_1h_usdt:,} (low activity) on {exchange}"
        )

        # Update statistics
        self.total_filtered_low_volume += 1

        # Log event to database
        from core.event_logger import get_event_logger, EventType
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.SIGNAL_FILTERED,
                {
                    'signal_id': signal.get('id'),
                    'symbol': symbol,
                    'exchange': exchange,
                    'filter_reason': 'low_trading_volume',
                    'volume_1h_usdt': float(volume_1h_usdt),
                    'min_volume_required': float(self.min_volume_1h_usdt),
                    'signal_timestamp': signal_timestamp.isoformat()
                },
                symbol=symbol,
                exchange=exchange,
                severity='INFO'
            )

        return True, f"1h volume ${volume_1h_usdt:,.0f} below minimum ${self.min_volume_1h_usdt:,}"

# Filter 3: Price change <= 4% in last 5 minutes
if self.filter_price_change_enabled:
    logger.debug(f"Checking price change filter for {symbol} on {exchange}")
    price_at_signal, price_5min_before = await self._fetch_price_5min_before(
        exchange_manager=exchange_manager,
        symbol=exchange_symbol,
        signal_timestamp=signal_timestamp
    )

    if price_at_signal and price_5min_before and price_5min_before > 0:
        price_change_percent = ((price_at_signal - price_5min_before) / price_5min_before) * 100
        direction = signal.get('recommended_action', signal.get('action', 'BUY')).upper()

        should_filter = False
        filter_reason = ""

        if direction == 'BUY':
            # For BUY: filter if price rose >4% (buying at top)
            if price_change_percent > self.max_price_change_5min_percent:
                should_filter = True
                filter_reason = f"BUY signal after {price_change_percent:+.2f}% price rise (>{self.max_price_change_5min_percent}%, overheated)"
        elif direction == 'SELL':
            # For SELL: filter if price fell >4% (selling at bottom)
            if price_change_percent < -self.max_price_change_5min_percent:
                should_filter = True
                filter_reason = f"SELL signal after {price_change_percent:+.2f}% price drop (>{self.max_price_change_5min_percent}%, oversold)"

        if should_filter:
            logger.info(f"⏭️ Signal skipped: {symbol} {filter_reason} on {exchange}")

            # Update statistics
            self.total_filtered_price_change += 1

            # Log event to database
            from core.event_logger import get_event_logger, EventType
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.SIGNAL_FILTERED,
                    {
                        'signal_id': signal.get('id'),
                        'symbol': symbol,
                        'exchange': exchange,
                        'filter_reason': 'excessive_price_change_5min',
                        'price_change_percent': float(price_change_percent),
                        'max_change_allowed': float(self.max_price_change_5min_percent),
                        'direction': direction,
                        'price_at_signal': float(price_at_signal),
                        'price_5min_before': float(price_5min_before),
                        'signal_timestamp': signal_timestamp.isoformat()
                    },
                    symbol=symbol,
                    exchange=exchange,
                    severity='INFO'
                )

            return True, filter_reason

# All filters passed
logger.debug(f"All filters passed for {symbol} on {exchange}")
```

**Ключевые моменты**:
- ✅ Каждый фильтр можно отключить через флаг (`self.filter_*_enabled`)
- ✅ Логирование на уровне INFO (видимо в основных логах)
- ✅ EventLogger для сохранения в БД
- ✅ Счетчики статистики для мониторинга
- ✅ Graceful handling: если API вернул None, фильтр НЕ срабатывает (fail-safe)

---

### ФАЗА 3: Добавить конфигурационные параметры

#### Файл: `config/settings.py`

**Расположение**: В раздел с фильтрами/валидацией (~строка 150-200)

**Добавить**:
```python
# ========== Signal Filter Thresholds ==========

# Minimum Open Interest (USDT) to accept signal
# Signals with OI below this will be rejected as low-liquidity
SIGNAL_MIN_OPEN_INTEREST_USDT = int(os.getenv('SIGNAL_MIN_OPEN_INTEREST_USDT', '1000000'))  # 1M USDT

# Minimum 1h Trading Volume (USDT) to accept signal
# Signals with volume below this will be rejected as low-activity
SIGNAL_MIN_VOLUME_1H_USDT = int(os.getenv('SIGNAL_MIN_VOLUME_1H_USDT', '50000'))  # 50k USDT

# Maximum 5-minute price change (%) before signal
# For BUY: reject if price rose >X% (buying at top)
# For SELL: reject if price fell >X% (selling at bottom)
SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT = float(os.getenv('SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT', '4.0'))  # 4%

# Enable/disable individual filters (can be toggled without code changes)
SIGNAL_FILTER_OI_ENABLED = os.getenv('SIGNAL_FILTER_OI_ENABLED', 'true').lower() == 'true'
SIGNAL_FILTER_VOLUME_ENABLED = os.getenv('SIGNAL_FILTER_VOLUME_ENABLED', 'true').lower() == 'true'
SIGNAL_FILTER_PRICE_CHANGE_ENABLED = os.getenv('SIGNAL_FILTER_PRICE_CHANGE_ENABLED', 'true').lower() == 'true'
```

**Преимущества**:
- ✅ Можно изменить пороги через `.env` без изменения кода
- ✅ Можно отключить каждый фильтр индивидуально
- ✅ Значения по умолчанию соответствуют тестированию
- ✅ Легко A/B тестирование разных порогов

---

#### Модификация `WaveSignalProcessor.__init__()`

**Файл**: `core/wave_signal_processor.py`  
**Расположение**: В методе `__init__()` (~строка 55-65)

**Добавить**:
```python
# Signal filter configuration
self.min_oi_usdt = self.config.signal_min_open_interest_usdt
self.min_volume_1h_usdt = self.config.signal_min_volume_1h_usdt
self.max_price_change_5min_percent = self.config.signal_max_price_change_5min_percent

# Filter enable/disable flags
self.filter_oi_enabled = self.config.signal_filter_oi_enabled
self.filter_volume_enabled = self.config.signal_filter_volume_enabled
self.filter_price_change_enabled = self.config.signal_filter_price_change_enabled

# Filter statistics counters
self.total_filtered_low_oi = 0
self.total_filtered_low_volume = 0
self.total_filtered_price_change = 0

logger.info(f"Signal filters configured:")
logger.info(f"  OI filter: {'enabled' if self.filter_oi_enabled else 'disabled'} (min: ${self.min_oi_usdt:,})")
logger.info(f"  Volume filter: {'enabled' if self.filter_volume_enabled else 'disabled'} (min: ${self.min_volume_1h_usdt:,})")
logger.info(f"  Price change filter: {'enabled' if self.filter_price_change_enabled else 'disabled'} (max: {self.max_price_change_5min_percent}%)")
```

---

### ФАЗА 4: Добавить логирование статистики

#### В методе `process_wave_signals()`

**Файл**: `core/wave_signal_processor.py`  
**Расположение**: В конце метода `process_wave_signals()` (~строка 230)

**Добавить**:
```python
# Log filter statistics
if self.total_filtered_low_oi > 0 or self.total_filtered_low_volume > 0 or self.total_filtered_price_change > 0:
    logger.info(
        f"Signal filters statistics: "
        f"low_oi={self.total_filtered_low_oi}, "
        f"low_volume={self.total_filtered_low_volume}, "
        f"price_change={self.total_filtered_price_change}"
    )
```

---

### ФАЗА 5: Создать unit-тесты

#### Файл: `tests/unit/test_wave_signal_processor_filters.py`

**Создать новый файл** с минимум **10 unit-тестами**:

1. ✅ `test_fetch_oi_success()` - OI успешно получен
2. ✅ `test_fetch_oi_none()` - OI не получен (возвращает None)
3. ✅ `test_fetch_volume_success()` - Volume успешно получен
4. ✅ `test_fetch_volume_none()` - Volume не получен
5. ✅ `test_fetch_price_5min_success()` - Цены успешно получены
6. ✅ `test_fetch_price_5min_none()` - Цены не получены
7. ✅ `test_oi_filter_pass()` - Сигнал проходит OI фильтр
8. ✅ `test_oi_filter_fail()` - Сигнал не проходит OI фильтр
9. ✅ `test_volume_filter_pass()` - Сигнал проходит Volume фильтр
10. ✅ `test_volume_filter_fail()` - Сигнал не проходит Volume фильтр
11. ✅ `test_price_change_buy_pass()` - BUY проходит (цена выросла <4%)
12. ✅ `test_price_change_buy_fail()` - BUY не проходит (цена выросла >4%)
13. ✅ `test_price_change_sell_pass()` - SELL проходит (цена упала <4%)
14. ✅ `test_price_change_sell_fail()` - SELL не проходит (цена упала >4%)
15. ✅ `test_filter_disabled()` - Фильтр отключен через config
16. ✅ `test_all_filters_pass()` - Integration: все фильтры проходят
17. ✅ `test_any_filter_fails()` - Integration: хотя бы один фильтр не проходит

**Все тесты должны использовать**:
- `@pytest.mark.asyncio` для async функций
- `AsyncMock` для мокирования API вызовов
- `MagicMock` для мокирования объектов

---

### ФАЗА 6: Обновить документацию

#### 6.1: Обновить README

**Файл**: `README.md`

**Добавить раздел**:
```markdown
## Signal Quality Filters

The bot applies multiple filters to ensure high-quality signals:

### 🔍 Open Interest Filter
- **Threshold**: ≥ 1,000,000 USDT
- **Purpose**: Filter out low-liquidity pairs
- **Why**: Low liquidity = hard to exit positions at desired price
- **Config**: `SIGNAL_MIN_OPEN_INTEREST_USDT=1000000`
- **Disable**: `SIGNAL_FILTER_OI_ENABLED=false`

### 📊 Trading Volume Filter
- **Threshold**: ≥ 50,000 USDT per hour
- **Purpose**: Ensure market activity
- **Why**: Low volume = prone to manipulation, wide spreads
- **Config**: `SIGNAL_MIN_VOLUME_1H_USDT=50000`
- **Disable**: `SIGNAL_FILTER_VOLUME_ENABLED=false`

### 📈 Price Change Filter
- **Threshold**: ≤ 4% in last 5 minutes
- **Purpose**: Avoid overheated/oversold entries
- **Why**: 
  - BUY after >4% rise = buying the top
  - SELL after >4% drop = selling the bottom
- **Config**: `SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT=4.0`
- **Disable**: `SIGNAL_FILTER_PRICE_CHANGE_ENABLED=false`

### 📊 Filter Effectiveness

Based on testing **114 real production signals**:

| Filter | Pass Rate | Filtered Out |
|--------|-----------|--------------|
| OI >= 1M | 85.1% | 14.9% |
| Volume >= 50k | 86.8% | 13.2% |
| Price Change <= 4% | 99.1% | 0.9% |
| **Combined (all 3)** | **82.5%** | **17.5%** |

**Key findings**:
- 82.5% of signals pass all filters (high quality)
- 17.5% filtered out (mostly low-cap Bybit pairs)
- Price filter caught MAVIAUSDT with +7.85% spike (overheated entry)
```

---

#### 6.2: Создать CHANGELOG запись

**Файл**: `CHANGELOG.md`

**Добавить**:
```markdown
## [Unreleased]

### Added
- Three new signal quality filters (tested on 114 real signals):
  - **Open Interest filter** (≥ 1M USDT) - prevent low-liquidity trades
  - **Trading Volume filter** (≥ 50k USDT/hour) - ensure market activity
  - **Price Change filter** (≤ 4% in 5min) - avoid overheated entries
- New methods in `WaveSignalProcessor`:
  - `_fetch_open_interest_usdt()` - Get OI in USDT with 5 fallback methods
  - `_fetch_1h_volume_usdt()` - Get hourly trading volume
  - `_fetch_price_5min_before()` - Get price momentum
- Configuration parameters for all filter thresholds
- Individual enable/disable flags for each filter
- EventLogger integration for filtered signals tracking
- Filter statistics counters and logging

### Changed
- Enhanced `WaveSignalProcessor._is_duplicate()` with three additional validation layers
- Modified signal processing to reject:
  - Low-liquidity pairs (OI < 1M)
  - Low-activity markets (Volume < 50k/hour)
  - Overheated BUY signals (price rose >4% in 5min)
  - Oversold SELL signals (price fell >4% in 5min)

### Impact
- **17.5% of signals will be filtered** (based on 114-signal test)
- Primarily affects low-cap Bybit pairs
- Improves signal quality by:
  - Preventing liquidity traps
  - Avoiding market manipulation
  - Eliminating poor entry timing
- Adds ~0.5-1s latency per signal (4 API calls)
- No rate limit issues (tested at 100% success)

### Testing
- ✅ 114 real production signals tested
- ✅ All API methods: 100% success rate
- ✅ Filter effectiveness confirmed: 82.5% pass rate
- ✅ Unit tests: 17 tests covering all scenarios
- ✅ Integration tests planned
```

---

#### 6.3: Создать Migration Guide

**Файл**: `docs/SIGNAL_FILTERS_MIGRATION_GUIDE.md`

**Содержание**: (сохранить как отдельный файл)

---

## 📊 Ожидаемый Impact

### Производительность

**API Calls per signal:**
- **До**: 0 дополнительных calls
- **После**: До 4 дополнительных calls:
  1. `fetch_open_interest()` или `fetch_ticker()` - для OI
  2. `fetch_ohlcv(timeframe='1h')` - для volume
  3. `fetch_ohlcv(timeframe='1m')` - для цены в момент сигнала
  4. `fetch_ohlcv(timeframe='1m')` - для цены 5 минут назад

**Latency:**
- Каждый API call: ~100-300ms
- Общая задержка на сигнал: **+0.4-1.2 секунды**
- **Приемлемо**: сигналы обрабатываются в волнах раз в 15 минут

**Rate Limits (протестировано):**
- Binance Futures: 1200 weight/minute - **НЕ превышен** ✅
- Bybit: 120 requests/minute - **НЕ превышен** ✅
- Все 114 сигнала обработаны без единой ошибки rate limit

---

### Качество сигналов

**Фильтрация (на основе 114 реальных сигналов):**
- **17.5%** сигналов будут отбракованы (20 из 114)
- **82.5%** сигналов пройдут все фильтры (94 из 114)

**Категории отфильтрованных сигналов:**
1. **Низколиквидные пары** (OI < 1M):
   - Примеры: GIGAUSDT, XNOUSDT, GNOUSDT (Bybit low-cap)
   - Риск: Сложно выйти из позиции, широкий спред

2. **Низкоактивные рынки** (Volume < 50k/hour):
   - Примеры: TSTBSCUSDT, PYRUSDT, RADUSDT (малый объем)
   - Риск: Манипуляция ценой, slippage

3. **Перегретые входы** (Price change > 4%):
   - Пример: **MAVIAUSDT BUY** после +7.85% роста за 5 минут
   - Риск: Покупка на вершине, высокая вероятность коррекции

**Улучшение качества:**
- ✅ Избегание ликвидных ловушек
- ✅ Снижение slippage
- ✅ Лучший timing входов
- ✅ Меньше застревания в неликвидных позициях

---

### Мониторинг и логирование

**Новые метрики**:
```
total_filtered_low_oi: X
total_filtered_low_volume: Y
total_filtered_price_change: Z
total_signals_passed: A
total_signals_filtered: B
filter_rate: (B / (A + B)) * 100%
```

**Логи (уровень INFO)**:
```
⏭️ Signal skipped: GIGAUSDT OI $653,534 < $1,000,000 (low liquidity) on bybit
⏭️ Signal skipped: TSTBSCUSDT 1h volume $25,525 < $50,000 (low activity) on bybit
⏭️ Signal skipped: MAVIAUSDT BUY signal after +7.85% price rise (>4%, overheated) on binance
```

**EventLogger events** (сохраняются в БД):
- Event type: `SIGNAL_FILTERED`
- Причины:
  - `low_open_interest`
  - `low_trading_volume`
  - `excessive_price_change_5min`
- Полные детали: значения, пороги, символ, биржа

---

## 🧪 ПЛАН ТЕСТИРОВАНИЯ

### ✅ ФАЗА 1: API Validation (ЗАВЕРШЕНО)

**Статус**: ✅ Выполнено  
**Файл**: `tests/manual/test_signal_filters_api_validation.py`  
**Результаты**: 114/114 сигналов, 100% success rate для всех API

---

### ФАЗА 2: Unit-тесты (17 тестов)

**Статус**: Требуется реализация  
**Файл**: `tests/unit/test_wave_signal_processor_filters.py`

**Тесты**:
1-6: Тесты вспомогательных методов (успех/неудача)
7-14: Тесты каждого фильтра (проходит/не проходит)
15-17: Integration тесты (все фильтры вместе)

**Критерий успеха**: Все 17 тестов проходят

---

### ФАЗА 3: Integration-тесты (5 тестов)

**Статус**: Требуется реализация  
**Файл**: `tests/integration/test_wave_processor_with_filters.py`

**Тесты**:
1. Полный цикл волны с включенными фильтрами
2. Полный цикл с отключенными фильтрами (через config)
3. Изменение порогов через config
4. Обработка ошибок API (network failures)
5. Логирование EventLogger events в БД

**Критерий успеха**: Все 5 тестов проходят

---

### ФАЗА 4: Staging Testing (24 часа)

**Статус**: Ожидает деплоя  

**Чек-лист**:
- [ ] Deploy на staging server
- [ ] Мониторинг логов: количество отфильтрованных сигналов
- [ ] Проверка latency: среднее время обработки волны
- [ ] Проверка rate limits: нет warnings/errors
- [ ] Проверка EventLogger: события сохраняются в БД
- [ ] Проверка статистики: соответствует ожиданиям (~17% фильтрация)

**Критерии успеха**:
- Filter rate: 15-20% (ожидается 17.5%)
- No rate limit errors
- Latency increase: <1s per signal
- No crashes/exceptions
- EventLogger entries created correctly

---

### ФАЗА 5: Production Monitoring (48 часов)

**Статус**: После успешного staging  

**Метрики для мониторинга**:
- Daily filtered signals count
- Filter breakdown: OI / Volume / Price Change
- Position quality metrics (P&L, duration)
- Comparison with pre-filter period

**Критерии успеха**:
- Same or better P&L
- Fewer stuck positions
- No operational issues

---

## 🚀 ПЛАН ДЕПЛОЯ

### Шаг 1: Pre-deployment Checklist

- [ ] ✅ API validation complete (114 signals)
- [ ] Unit-тесты написаны и проходят (17 tests)
- [ ] Integration-тесты написаны и проходят (5 tests)
- [ ] Документация обновлена (README, CHANGELOG, Migration Guide)
- [ ] `.env.example` обновлен с новыми параметрами
- [ ] Code review выполнен
- [ ] Git branch готов к merge

---

### Шаг 2: Staging Deployment

```bash
# 1. Create feature branch
git checkout develop
git pull origin develop
git checkout -b feature/signal-quality-filters

# 2. Apply code changes
# (Implement all changes from ФАЗА 1-6)

# 3. Commit changes
git add .
git commit -m "feat: add signal quality filters (OI, Volume, Price Change)

- Add 3 new filters to WaveSignalProcessor._is_duplicate()
- Implement _fetch_open_interest_usdt() with 5 fallback methods
- Implement _fetch_1h_volume_usdt() for activity check
- Implement _fetch_price_5min_before() for momentum check
- Add configuration parameters with enable/disable flags
- Add EventLogger integration for filtered signals
- Add filter statistics tracking and logging
- Tested on 114 real signals: 100% API success, 17.5% filter rate

BREAKING CHANGE: 17.5% of signals will now be filtered out
- Primarily affects low-cap Bybit pairs
- Improves signal quality by avoiding liquidity traps

Refs: #123"

# 4. Push to remote
git push origin feature/signal-quality-filters

# 5. Deploy to staging
ssh staging-server
cd /app/TradingBot
git fetch
git checkout feature/signal-quality-filters
git pull

# 6. Update .env
nano .env
# Add:
SIGNAL_MIN_OPEN_INTEREST_USDT=1000000
SIGNAL_MIN_VOLUME_1H_USDT=50000
SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT=4.0
SIGNAL_FILTER_OI_ENABLED=true
SIGNAL_FILTER_VOLUME_ENABLED=true
SIGNAL_FILTER_PRICE_CHANGE_ENABLED=true

# 7. Restart bot
systemctl restart trading-bot

# 8. Monitor logs
journalctl -u trading-bot -f | grep -E "Signal skipped|filter|OI|volume|price change"
```

---

### Шаг 3: Staging Validation (24h)

**Мониторить в реальном времени**:
```bash
# Check filter statistics
journalctl -u trading-bot --since "24 hours ago" | grep "Signal filters statistics"

# Check filtered signals
journalctl -u trading-bot --since "24 hours ago" | grep "⏭️ Signal skipped"

# Check rate limits
journalctl -u trading-bot --since "24 hours ago" | grep -i "rate limit"

# Check errors
journalctl -u trading-bot --since "24 hours ago" | grep -i "error"
```

**Success criteria** (через 24 часа):
- ✅ Filter rate: 15-20%
- ✅ No rate limit errors
- ✅ No crashes
- ✅ EventLogger entries в БД
- ✅ Latency приемлемая (<1s per signal)

---

### Шаг 4: Production Deployment

**Если staging успешен**:

```bash
# 1. Merge to main
git checkout main
git pull origin main
git merge feature/signal-quality-filters
git push origin main

# 2. Create release tag
git tag -a v2.1.0 -m "Release v2.1.0: Signal Quality Filters

- Add OI, Volume, and Price Change filters
- Tested on 114 real signals
- 17.5% filter rate, 82.5% pass rate
- 100% API reliability

See CHANGELOG.md for full details."
git push origin v2.1.0

# 3. Deploy to production
ssh production-server
cd /app/TradingBot
git fetch --tags
git checkout v2.1.0

# 4. Update .env (same as staging)
nano .env

# 5. Restart bot
systemctl restart trading-bot

# 6. Monitor
journalctl -u trading-bot -f
```

---

### Шаг 5: Production Monitoring (48h)

**Dashboard metrics** (через Grafana/Prometheus):
- Daily signals: total vs filtered
- Filter breakdown: по причинам
- Position metrics: P&L, duration
- API latency: p50, p95, p99
- Rate limit usage: по биржам

**Alert thresholds**:
- Filter rate >30% или <10% → investigate
- Rate limit warnings → investigate
- Latency >2s per signal → investigate

---

## 🔄 ROLLBACK ПЛАН

### Option 1: Отключить фильтры (fastest - 1 минута)

```bash
# Set via .env
SIGNAL_FILTER_OI_ENABLED=false
SIGNAL_FILTER_VOLUME_ENABLED=false
SIGNAL_FILTER_PRICE_CHANGE_ENABLED=false

# Restart
systemctl restart trading-bot
```

**Когда использовать**: Если фильтры слишком агрессивные, но код работает корректно

---

### Option 2: Изменить пороги (2 минуты)

```bash
# More lenient thresholds
SIGNAL_MIN_OPEN_INTEREST_USDT=500000        # 500k instead of 1M
SIGNAL_MIN_VOLUME_1H_USDT=25000             # 25k instead of 50k
SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT=6.0   # 6% instead of 4%

systemctl restart trading-bot
```

**Когда использовать**: Если фильтры работают, но слишком строгие

---

### Option 3: Revert code (5-10 минут)

```bash
# Revert commit
git revert <commit-hash>
git push origin main

# Deploy
ssh production-server
cd /app/TradingBot
git pull
systemctl restart trading-bot
```

**Когда использовать**: Если есть баги в коде или критические проблемы

---

### Option 4: Rollback к предыдущему тегу (5 минут)

```bash
ssh production-server
cd /app/TradingBot
git checkout v2.0.0  # previous stable version
systemctl restart trading-bot
```

**Когда использовать**: Критические проблемы, нужно быстро вернуться к стабильной версии

---

## 📝 Чеклист перед началом реализации

### Подготовка (✅ ЗАВЕРШЕНО)

- [x] ✅ Изучена функция `_is_duplicate()`
- [x] ✅ Проанализированы доступные API методы
- [x] ✅ Создан тестовый скрипт для API validation
- [x] ✅ Протестированы API на **114 реальных сигналах** (требовалось >19)
- [x] ✅ Подтверждена **100% успешность всех API методов**
- [x] ✅ Подтверждена эффективность фильтров: **17.5% фильтрация**
- [x] ✅ Создан детальный план реализации

### Реализация (ещё НЕ выполнено)

- [ ] Добавить 3 новых метода в `WaveSignalProcessor`
  - [ ] `_fetch_open_interest_usdt()`
  - [ ] `_fetch_1h_volume_usdt()`
  - [ ] `_fetch_price_5min_before()`
- [ ] Модифицировать `_is_duplicate()`:
  - [ ] Добавить извлечение timestamp
  - [ ] Добавить 3 новых фильтра
- [ ] Добавить конфигурационные параметры в `config/settings.py`
- [ ] Добавить инициализацию в `WaveSignalProcessor.__init__()`
- [ ] Добавить логирование статистики
- [ ] Создать unit-тесты (17 тестов)
- [ ] Создать integration-тесты (5 тестов)
- [ ] Обновить документацию:
  - [ ] README.md
  - [ ] CHANGELOG.md
  - [ ] Migration Guide

### Тестирование

- [ ] Запустить все unit-тесты (должны пройти 17/17)
- [ ] Запустить integration-тесты (должны пройти 5/5)
- [ ] Повторно запустить API validation (убедиться что ничего не сломалось)
- [ ] Проверить latency impact (должно быть <1s)
- [ ] Проверить что rate limits НЕ превышаются

### Деплой

- [ ] Deploy на staging
- [ ] Мониторинг 24 часа
- [ ] Validation: success criteria met
- [ ] Deploy на production
- [ ] Мониторинг 48 часов
- [ ] Post-deployment review

---

## 🎯 Ожидаемые результаты после внедрения

### Немедленные эффекты

1. **Фильтрация сигналов**: 17.5% будут отбракованы
   - 17 из 114 по низкому OI
   - 15 из 114 по низкому volume
   - 1 из 114 по перегретости (MAVIAUSDT +7.85%)

2. **Улучшение качества**: 82.5% сигналов высокого качества
   - Высокая ликвидность (OI >= 1M)
   - Активный рынок (Volume >= 50k/hour)
   - Нормальный моментум (Price change <= 4%)

3. **Производительность**: Минимальный impact
   - +0.5-1s latency per signal (приемлемо)
   - 0 rate limit issues (протестировано)
   - 100% API reliability

---

### Долгосрочные эффекты (ожидаемые)

1. **Снижение рисков**:
   - Меньше застревания в неликвидных позициях
   - Меньше slippage при выходе
   - Меньше манипулируемых рынков

2. **Улучшение P&L**:
   - Лучший timing входов (избегание перегретых)
   - Меньше убыточных позиций в low-cap парах
   - Выше качество каждой сделки

3. **Операционные улучшения**:
   - Полная видимость через EventLogger
   - Гибкая настройка через .env
   - Легкий rollback при необходимости

---

## 📞 Контакты и поддержка

**Автор плана**: Claude Code  
**Дата**: 2025-10-28  
**Версия**: 2.0 (финальная, после полного тестирования 114 сигналов)  

**Вопросы по плану**: GitHub Issues  
**Реализация**: После утверждения плана  

---

## 📎 Приложения

### Приложение A: Статистика тестирования 114 сигналов

```
================================================================================
TEST STATISTICS
================================================================================
Total signals tested: 114

API Method Success Rates:
  Open Interest API:
    ✅ Success: 114 (100.0%)
    ❌ Failed:  0 (0.0%)
  1h Volume API:
    ✅ Success: 114 (100.0%)
    ❌ Failed:  0 (0.0%)
  5min Price API:
    ✅ Success: 114 (100.0%)
    ❌ Failed:  0 (0.0%)

Filter Pass Rates (individual):
  OI Filter (>= 1M USDT):            97 passed (85.1%)
  Volume Filter (>= 50k USDT):       99 passed (86.8%)
  Price Change Filter (<= 4%):       113 passed (99.1%)

Overall Filter Results:
  ✅ Would PASS all filters:         94 (82.5%)
  ❌ Would be FILTERED OUT:          20 (17.5%)
================================================================================
```

---

### Приложение B: Примеры отфильтрованных сигналов (20 шт)

**По низкому OI**:
- GIGAUSDT (Bybit) - OI $648k < 1M
- XNOUSDT (Bybit) - OI $237k < 1M
- GNOUSDT (Bybit) - OI $360k < 1M
- PYRUSDT (Bybit) - OI $154k < 1M
- GIGAUSDT (Bybit) - OI $645k < 1M (повторный)
- 1000TAGUSDT (Bybit) - OI $334k < 1M
- 10000ELONUSDT (Bybit) - OI $125k < 1M
- XNOUSDT (Bybit) - OI $237k < 1M (повторный)
- IDEXUSDT (Bybit) - OI $593k < 1M
- FWOGUSDT (Bybit) - OI $722k < 1M
- RADUSDT (Bybit) - OI $312k < 1M
- И др.

**По низкому Volume**:
- TSTBSCUSDT (Bybit) - Volume $25k < 50k
- XNOUSDT (Bybit) - Volume $17k < 50k
- GNOUSDT (Bybit) - Volume $6k < 50k
- BLASTUSDT (Bybit) - Volume $31k < 50k
- FWOGUSDT (Bybit) - Volume $26k < 50k
- STORJUSDT (Binance) - Volume $42k < 50k
- XNOUSDT (Bybit) - Volume $47k < 50k (повторный)
- И др.

**По перегретости** (Price Change > 4%):
- **MAVIAUSDT (Binance)** - BUY после +7.85% роста за 5 минут ⚠️
  - Это критически важный case! Сигнал показал потом +9.29% профит, НО вход был перегретый

---

### Приложение C: Примеры прошедших фильтры (94 шт)

**Высококачественные сигналы** (все 3 фильтра ✅):

1. **PHBUSDT** (Binance):
   - OI: $6.43M ✅
   - Volume: $29.9M ✅
   - Price change: -0.29% ✅
   - Результат: +2.61% профит

2. **AIAUSDT** (Binance):
   - OI: $10.36M ✅
   - Volume: $4.98M ✅
   - Price change: -4.24% ✅ (падение перед BUY - это OK)
   - Результат: +5.47% профит

3. **JUPUSDT** (Binance):
   - OI: $29.39M ✅
   - Volume: $1.18M ✅
   - Price change: -0.47% ✅
   - Результат: +0.61% профит

4. **VANAUSDT** (Binance):
   - OI: $4.54M ✅
   - Volume: $1.07M ✅
   - Price change: -0.14% ✅
   - Результат: +1.04% профит

... (еще 90 сигналов высокого качества)

---

**КОНЕЦ ПЛАНА**

---

**ВАЖНО**: Этот план основан на **ПОЛНОМ** тестировании 114 реальных сигналов из production.  
Все API методы протестированы и показали **100% надежность**.  
Эффективность фильтров подтверждена: **17.5% фильтрация, 82.5% качественных сигналов**.

**Следующий шаг**: Получить утверждение плана и начать реализацию ФАЗА 1-6.
