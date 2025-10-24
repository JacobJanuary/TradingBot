# WebSocket Monitoring - Анализ и Рекомендации

## ОТВЕТЫ НА ВОПРОСЫ

### 1. Где хранятся last update timestamps для символов?

**ХРАНЯТСЯ В:**
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/unified_price_monitor.py`
- **Линия 35:** `self.last_update_time = defaultdict(float)` - хранит float timestamp (time.time())
- **Линия 100-101:** При каждом обновлении: `self.last_update_time[symbol] = now`

**ТЕКУЩИЙ ФОРМАТ:**
```python
self.last_update_time: Dict[str, float]  # Unix timestamp in seconds
Example: {'BTCUSDT': 1729711234.567, 'ETHUSDT': 1729711234.123}
```

**ПРОБЛЕМА:**
- Это float timestamp (секунды с Unix epoch)
- Нет datetime для читаемости
- Нет способа получить staleness вне этого класса
- Нет отслеживания per-symbol здоровья

**РЕКОМЕНДАЦИЯ:**
Добавить дополнительное хранилище с datetime:
```python
self.last_update_timestamp = defaultdict(lambda: datetime.now())  # datetime per symbol
self.symbol_health = defaultdict(lambda: {'status': 'healthy'})
```

---

### 2. Есть ли health check для WebSocket per symbol?

**НЕТ. Есть только:**

**Connection-level health check:**
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/improved_stream.py`
- **Линии 376-405:** `_check_connection_health()` - проверяет только соединение
- Проверяет: heartbeat, pong timeout, error rate
- НЕ проверяет обновления отдельных символов

**System health check (MOCK):**
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py`
- **Линии 324-340:** `_check_websocket()` - HARDCODED mock status
- Всегда возвращает HEALTHY
- Не проверяет реальное состояние

**ЧТО НУЖНО:**
```python
# Per-symbol health tracking
self.symbol_health = {
    'BTCUSDT': {'status': 'healthy', 'last_update': datetime.now(), 'staleness': 5},
    'ETHUSDT': {'status': 'stale', 'last_update': datetime.now() - timedelta(minutes=10)},
}

# Health check method
def get_staleness_seconds(self, symbol: str) -> float:
    """Get how old is price for this symbol"""
    # Return seconds since last update
```

---

### 3. Есть ли alerts если нет updates > 5 минут?

**ЧАСТИЧНО. Есть для SIGNALS, не для PRICE UPDATES:**

**Существует:**
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py`
- **Линии 342-384:** `_check_signal_processor()` - проверяет signals > 5 minutes
- Но это для торговых сигналов, не для price updates от WebSocket

**ОТСУТСТВУЕТ:**
- Нет alerts для stale price updates (> 5 минут без обновления)
- Нет per-symbol price staleness monitoring
- Нет интеграции с UnifiedPriceMonitor
- Нет автоматических действий при stale data (например, пауза aged position checks)

**РЕКОМЕНДАЦИЯ:**
Добавить метод `_check_price_updates()` в HealthChecker:
```python
async def _check_price_updates(self) -> ComponentHealth:
    """Check price update staleness for all symbols"""
    # Check each symbol: staleness > 300s = CRITICAL
    # staleness > 180s = DEGRADED
    # Generate alerts to database
```

---

### 4. Где происходит update_price в UnifiedPriceMonitor?

**ВЫЗЫВАЕТСЯ ИЗ:**
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py`
- `await trailing_manager.update_price(symbol, position.current_price)`
- При каждом обновлении позиции

**РЕАЛИЗУЕТСЯ В:**
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/unified_price_monitor.py`
- **Линии 89-114:** `async def update_price(self, symbol: str, price: Decimal)`

**ЛОГИКА:**
1. Проверка rate limiting (минимум 100мс между обновлениями)
2. Сохранение timestamp и цены
3. Обновление счётчика обновлений
4. Вызов callbacks для всех подписчиков

**ИНТЕГРАЦИЯ С AGED POSITIONS:**
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/aged_position_monitor_v2.py`
- **Линии 224-288:** `check_price_target()` - вызывается из UnifiedPriceMonitor callback
- Проверяет достигнут ли целевой price для aged позиции
- Логирует события в DB

**ТЕКУЩАЯ ПРОБЛЕМА:**
Нет проверки staleness перед check_price_target:
- Если цена не обновлялась > 5 минут, check всё равно выполняется
- Может привести к закрытию позиции на устаревшей цене

**РЕКОМЕНДАЦИЯ:**
Добавить staleness check перед callback:
```python
# In check_price_target
staleness = self.price_monitor.get_staleness_seconds(symbol)
if staleness > 300:
    logger.error(f"Price for {symbol} is stale ({staleness}s). Skipping check.")
    return
```

---

## ИТОГОВАЯ ТАБЛИЦА РЕАЛИЗАЦИИ

| Требование | Статус | Где | Проблема |
|-----------|--------|-----|----------|
| Last update timestamp per symbol | ✅ Частично | unified_price_monitor.py:35 | Только float, нет datetime |
| Health check per symbol | ❌ НЕТ | - | Нужно добавить |
| Alerts > 5 min | ❌ НЕТ | - | Есть для signals, нужны для prices |
| update_price в monitor | ✅ ДА | unified_price_monitor.py:89 | Работает, нет staleness check |
| Staleness detection | ❌ НЕТ | - | Нужен метод get_staleness_seconds() |
| Database persistence | ❌ Частично | aged_position_monitor_v2.py | Только для aged events, не для health |

---

## РЕКОМЕНДУЕМЫЕ УЛУЧШЕНИЯ (ПРИОРИТЕТ)

### ВЫСОКИЙ ПРИОРИТЕТ:

**1. Добавить per-symbol staleness detection в UnifiedPriceMonitor**
```python
# Файл: websocket/unified_price_monitor.py
- Добавить self.last_update_timestamp с datetime
- Добавить метод get_staleness_seconds(symbol)
- Проверка staleness перед callback
```

**2. Исправить health check в health_check.py**
```python
# Файл: monitoring/health_check.py
- Заменить MOCK на реальный _check_websocket()
- Добавить _check_price_updates() для staleness
```

**3. Добавить staleness guard в aged_position_monitor_v2.py**
```python
# Файл: core/aged_position_monitor_v2.py
- Check staleness в check_price_target()
- Skip check если цена > 5 минут старая
```

### СРЕДНИЙ ПРИОРИТЕТ:

**4. Добавить per-symbol health tracking в ImprovedStream**
```python
# Файл: websocket/improved_stream.py
- Отслеживать timestamp per symbol
- Метод get_symbol_health()
```

**5. Добавить alerts table в database**
```python
# Сохранять stale price alerts в DB
# Для аналитики и аудита
```

---

## ФАЙЛЫ ДЛЯ ПРАВКИ

1. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/unified_price_monitor.py` (Lines 27-127)
2. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py` (Lines 323-340 и добавить new method)
3. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/aged_position_monitor_v2.py` (Lines 224-288)
4. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/improved_stream.py` (Lines 30-406)

---

## РИСКИ БЕЗ ЭТИХ УЛУЧШЕНИЙ

1. **Stale Price Execution:** Aged позиции могут закрыться на цене которая не обновлялась > 5 минут
2. **Silent Failures:** WebSocket может быть мёртв для конкретного символа, но health check показывает OK
3. **Trade Loss:** Стоп-лосс может не срабатать если price data застарелась
4. **Silent Monitoring:** Нет visibility что происходит с каждым символом в реальности

