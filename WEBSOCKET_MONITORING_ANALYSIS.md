# WebSocket Monitoring Analysis Report

## 1. LAST UPDATE TIMESTAMPS ДЛЯ СИМВОЛОВ

### Текущая реализация:
**Файл: `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/unified_price_monitor.py`**

```python
# Lines 35-36: Хранение timestamp
self.last_update_time = defaultdict(float)
self.min_update_interval = 0.1  # 100ms between updates per symbol

# Lines 96-101: Update timestamp при update_price
async def update_price(self, symbol: str, price: Decimal):
    now = time.time()
    if now - self.last_update_time[symbol] < self.min_update_interval:
        return  # Skip too frequent updates
    
    self.last_update_time[symbol] = now  # TIMESTAMP SAVED HERE
    self.last_prices[symbol] = price
```

**Проблемы:**
- Timestamps хранятся как FLOAT (time.time())
- Нет привязки per-symbol timestamp к базе данных
- Нет механизма для отслеживания staleness > 5 минут
- Нет health check для каждого символа

### Где нужны улучшения:
1. Добавить дополнительное хранилище per-symbol timestamp с datetime
2. Интегрировать с database для persistence
3. Добавить staleness detection

---

## 2. HEALTH CHECK ДЛЯ WEBSOCKET PER SYMBOL

### Текущая реализация:

**Файл: `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/improved_stream.py`**

```python
# Lines 376-405: Connection health check (ГЛОБАЛЬНЫЙ, не per-symbol)
async def _check_connection_health(self) -> bool:
    if not self.ws or self.ws.closed:
        return False
    
    # Check last heartbeat
    time_since_heartbeat = (datetime.now() - self.last_heartbeat).total_seconds()
    if time_since_heartbeat > self.heartbeat_timeout:
        logger.warning(f"No heartbeat for {time_since_heartbeat:.0f}s")
        return False
    
    # Check last pong - CRITICAL FIX
    time_since_pong = (datetime.now() - self.last_pong).total_seconds()
    
    # IMMEDIATE reconnect if no pong for 120 seconds
    if time_since_pong > 120:
        logger.critical(f"🔴 CRITICAL: No pong for {time_since_pong:.0f}s - FORCE RECONNECT!")
        return False
```

**Проблемы:**
- Health check ТОЛЬКО на уровне соединения
- Нет per-symbol health monitoring
- Нет detection stale price updates per symbol
- Нет отслеживания, что символ не обновлялся > 5 минут

### Файл: `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py`

```python
# Lines 324-340: WebSocket health check (mock implementation)
async def _check_websocket(self) -> ComponentHealth:
    # Should check actual WebSocket status
    
    return ComponentHealth(
        name="WebSocket Streams",
        type=ComponentType.WEBSOCKET,
        status=HealthStatus.HEALTHY,
        last_check=datetime.now(timezone.utc),
        response_time_ms=10,
        metadata={
            'binance_ws': 'connected',
            'bybit_ws': 'connected',
            'message_rate': 100  # messages per second - MOCK!
        }
    )
```

**Проблемы:**
- MOCK implementation - не реальный health check
- Нет отслеживания per-symbol updates
- Нет alerts для stale data

---

## 3. ALERTS ДЛЯ UPDATES > 5 МИНУТ

### Текущая реализация:

**Файл: `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py`**

```python
# Lines 342-384: Signal processor check (PARTIAL решение)
async def _check_signal_processor(self) -> ComponentHealth:
    last_signal = await self.repository.get_last_signal_time()
    
    if last_signal:
        time_since = datetime.now(timezone.utc) - last_signal
        
        if time_since > timedelta(minutes=5):
            status = HealthStatus.DEGRADED
            error_message = f"No signals for {time_since.seconds//60} minutes"
        else:
            status = HealthStatus.HEALTHY
            error_message = None
```

**Проблемы:**
- Это для SIGNALS, не для WebSocket price updates
- Нет integration с UnifiedPriceMonitor
- Нет per-symbol staleness alerts
- Не отслеживает стоп-лосс или aged positions которым нужны обновления

---

## 4. UPDATE_PRICE В UNIFIEDPRICEMONITOR

### Текущая реализация:

**Файл: `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/unified_price_monitor.py`**

```python
# Lines 89-114: Main entry point
async def update_price(self, symbol: str, price: Decimal):
    """
    Main entry point - distribute price to subscribers
    Called by PositionManager._on_position_update()
    """
    
    # Rate limiting
    now = time.time()
    if now - self.last_update_time[symbol] < self.min_update_interval:
        return  # Skip too frequent updates
    
    self.last_update_time[symbol] = now
    self.last_prices[symbol] = price
    self.update_count += 1
    
    # Notify subscribers
    if symbol in self.subscribers:
        for subscriber in self.subscribers[symbol]:
            try:
                # Call with error isolation
                await subscriber['callback'](symbol, price)
            except Exception as e:
                logger.error(
                    f"Error in {subscriber['module']} callback for {symbol}: {e}"
                )
                self.error_count += 1
```

**Где вызывается:**
- `core/position_manager.py`: `await trailing_manager.update_price(symbol, position.current_price)`
- Интегрируется с AgedPositionMonitorV2 через подписку

**Как интегрируется:**

**Файл: `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/aged_position_monitor_v2.py`**

```python
# Lines 224-288: Price target checking
async def check_price_target(self, symbol: str, current_price: Decimal):
    """
    Check if current price reached target for aged position
    Called by UnifiedPriceMonitor through adapter
    """
    
    if symbol not in self.aged_targets:
        return
    
    target = self.aged_targets[symbol]
    
    # Log monitoring event to database
    if self.repository:
        try:
            await self.repository.create_aged_monitoring_event(
                aged_position_id=target.position_id,
                event_type='price_check',
                market_price=current_price,
                target_price=target.target_price,
                price_distance_percent=abs((current_price - target.target_price) / target.target_price * Decimal('100')),
                event_metadata={
                    'pnl_percent': str(pnl_percent),
                    'phase': target.phase
                }
            )
```

---

## SUMMARY: ЧТО РЕАЛИЗОВАНО VS ЧТО НУЖНО

### РЕАЛИЗОВАНО:
✅ Сохранение last_update_time per symbol (float timestamp)
✅ Rate limiting на update_price (100ms minimum)
✅ Callback система для подписчиков
✅ Connection-level health check (Bybit heartbeat 20s, pong timeout 120s)
✅ Per-symbol aged position monitoring
✅ Database logging of monitoring events

### НУЖНО ДОБАВИТЬ:

#### 1. Per-Symbol Staleness Detection (5+ minutes)
ОТСУТСТВУЕТ:
- Tracking последнего обновления per symbol в datetime формате
- Health check что символ не обновлялся > 5 минут
- Alerts для stale price data
- Graceful degradation для старых данных

#### 2. Per-Symbol Health Monitoring
ОТСУТСТВУЕТ:
- Health status для каждого символа в мониторе
- Отслеживание count failed updates per symbol
- Recovery mechanism для reconnection по символам
- Metadata о quality price data per symbol

#### 3. Database Persistence для Health Status
ОТСУТСТВУЕТ:
- Сохранение per-symbol health metrics в DB
- Historical tracking staleness events
- Alerts table для отправки нотификаций

#### 4. Adaptive Behavior при Stale Data
ОТСУТСТВУЕТ:
- Fallback to last known price при stale
- Warning logs при 3+ минут без обновления
- Critical alerts при 5+ минут без обновления
- Temporary pause aged position checks при stale data

---

## КОНКРЕТНЫЕ МЕСТА КОТОРЫЕ НУЖНО УЛУЧШИТЬ

### 1. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/unified_price_monitor.py`
Lines 35-102: Нужны изменения:
- Добавить `self.last_update_timestamp` (datetime per symbol)
- Добавить `self.symbol_health` (per-symbol status)
- Добавить метод `get_staleness_seconds(symbol)`
- Добавить check staleness перед callback

### 2. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py`
Lines 324-340: Заменить mock на real:
- Добавить `_check_websocket_per_symbol()`
- Отслеживать staleness для активных символов
- Генерировать alerts для stale updates

### 3. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/aged_position_monitor_v2.py`
Lines 224-288: Добавить safety checks:
- Skip check_price_target если price стale > 5 минут
- Log warning если обновление не было > 3 минуты
- Emit alert если обновление не было > 5 минут

### 4. `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/improved_stream.py`
Lines 376-405: Добавить per-symbol tracking:
- Track timestamp последнего message per symbol
- Detect stale symbols independently от connection health
