# WebSocket Monitoring - Конкретные Места в Коде

## 1. TIMESTAMPS ХРАНЯТСЯ ЗДЕСЬ

### Основное место (UnifiedPriceMonitor):
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/unified_price_monitor.py`

```python
Line 35-36:
    self.last_update_time = defaultdict(float)  # ← float timestamp per symbol
    self.min_update_interval = 0.1              # ← 100ms rate limiting

Line 96-102:
    async def update_price(self, symbol: str, price: Decimal):
        now = time.time()
        if now - self.last_update_time[symbol] < self.min_update_interval:
            return  # Skip too frequent updates
        
        self.last_update_time[symbol] = now  # ← TIMESTAMP UPDATED HERE
        self.last_prices[symbol] = price
        self.update_count += 1
```

**ПРОБЛЕМА:** Это float timestamp, нет datetime, нет способа узнать когда был последний update для символа вне этого класса.

**НУЖНО ДОБАВИТЬ:**
```python
# Add datetime tracking
self.last_update_timestamp = defaultdict(lambda: datetime.now())  # datetime per symbol
self.symbol_health = defaultdict(lambda: {'status': 'healthy', 'last_update': None})

async def update_price(self, symbol: str, price: Decimal):
    now = time.time()
    now_dt = datetime.now()
    
    if now - self.last_update_time[symbol] < self.min_update_interval:
        return
    
    self.last_update_time[symbol] = now
    self.last_update_timestamp[symbol] = now_dt  # ← NEW: datetime timestamp
    self.last_prices[symbol] = price
    self.update_count += 1
    
    # Update health status
    self.symbol_health[symbol]['status'] = 'healthy'
    self.symbol_health[symbol]['last_update'] = now_dt
    
    # Notify subscribers with staleness check
    if symbol in self.subscribers:
        staleness = self.get_staleness_seconds(symbol)
        if staleness > 300:  # 5 minutes
            logger.warning(f"Price for {symbol} is {staleness}s old")
            return  # Skip if stale
        
        for subscriber in self.subscribers[symbol]:
            # ... rest of callback logic
```

**GET STALENESS METHOD:**
```python
def get_staleness_seconds(self, symbol: str) -> float:
    """Get how many seconds since last update for symbol"""
    if symbol not in self.last_update_timestamp:
        return float('inf')
    
    last_update = self.last_update_timestamp[symbol]
    age = (datetime.now() - last_update).total_seconds()
    return age
```

---

## 2. HEALTH CHECK ДЛЯ WEBSOCKET

### Место 1: Connection-level health (ImprovedStream)
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/websocket/improved_stream.py`

```python
Lines 376-405:
    async def _check_connection_health(self) -> bool:
        """Check if connection is healthy"""
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
            logger.critical(f"🔴 CRITICAL: No pong for {time_since_pong:.0f}s")
            return False
```

**ПРОБЛЕМА:** Это check только CONNECTION, не per-symbol.

**НУЖНО ДОБАВИТЬ:**
```python
# In ImprovedStream.__init__:
self.symbol_last_message_time = defaultdict(datetime.now)  # per symbol tracking

# In _process_message or where message is handled:
async def _track_message_for_symbol(self, symbol: str):
    """Track when we last received message for this symbol"""
    self.symbol_last_message_time[symbol] = datetime.now()

# Add new method:
async def get_symbol_health(self) -> Dict[str, Dict]:
    """Get health status per symbol"""
    health = {}
    now = datetime.now()
    
    for symbol, last_time in self.symbol_last_message_time.items():
        age = (now - last_time).total_seconds()
        
        if age > 300:  # 5 minutes
            status = 'stale'
        elif age > 180:  # 3 minutes
            status = 'degraded'
        else:
            status = 'healthy'
        
        health[symbol] = {
            'status': status,
            'seconds_since_update': age,
            'last_update': last_time.isoformat()
        }
    
    return health
```

### Место 2: System health check (health_check.py) - MOCK
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py`

```python
Lines 324-340:
    async def _check_websocket(self) -> ComponentHealth:
        """Check WebSocket connections"""
        
        # Should check actual WebSocket status
        
        return ComponentHealth(
            name="WebSocket Streams",
            type=ComponentType.WEBSOCKET,
            status=HealthStatus.HEALTHY,  # ← MOCK! Always healthy
            last_check=datetime.now(timezone.utc),
            response_time_ms=10,
            metadata={
                'binance_ws': 'connected',      # ← HARDCODED
                'bybit_ws': 'connected',        # ← HARDCODED
                'message_rate': 100             # ← MOCK
            }
        )
```

**ПРОБЛЕМА:** Это MOCK implementation, всегда возвращает healthy.

**НУЖНО ЗАМЕНИТЬ НА:**
```python
async def _check_websocket(self) -> ComponentHealth:
    """Check WebSocket connections with per-symbol health"""
    try:
        # Get unified price monitor from position manager
        if not hasattr(self, 'price_monitor'):
            return ComponentHealth(
                name="WebSocket Streams",
                type=ComponentType.WEBSOCKET,
                status=HealthStatus.UNHEALTHY,
                last_check=datetime.now(timezone.utc),
                response_time_ms=0,
                error_message="Price monitor not available"
            )
        
        # Check per-symbol health
        stale_symbols = []
        degraded_symbols = []
        
        for symbol in self.price_monitor.last_prices.keys():
            staleness = self.price_monitor.get_staleness_seconds(symbol)
            
            if staleness > 300:  # 5 minutes
                stale_symbols.append((symbol, staleness))
            elif staleness > 180:  # 3 minutes
                degraded_symbols.append((symbol, staleness))
        
        # Determine overall status
        if stale_symbols:
            status = HealthStatus.CRITICAL
            error_msg = f"{len(stale_symbols)} symbols stale > 5min: {stale_symbols[:3]}"
        elif degraded_symbols:
            status = HealthStatus.DEGRADED
            error_msg = f"{len(degraded_symbols)} symbols degraded > 3min"
        else:
            status = HealthStatus.HEALTHY
            error_msg = None
        
        return ComponentHealth(
            name="WebSocket Streams",
            type=ComponentType.WEBSOCKET,
            status=status,
            last_check=datetime.now(timezone.utc),
            response_time_ms=0,
            error_message=error_msg,
            metadata={
                'total_symbols': len(self.price_monitor.last_prices),
                'healthy_symbols': len(self.price_monitor.last_prices) - len(stale_symbols) - len(degraded_symbols),
                'stale_symbols': len(stale_symbols),
                'degraded_symbols': len(degraded_symbols)
            }
        )
    except Exception as e:
        return ComponentHealth(
            name="WebSocket Streams",
            type=ComponentType.WEBSOCKET,
            status=HealthStatus.CRITICAL,
            last_check=datetime.now(timezone.utc),
            response_time_ms=0,
            error_message=str(e)
        )
```

---

## 3. ALERTS ДЛЯ UPDATES > 5 МИНУТ

### Текущее место (неправильное):
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/monitoring/health_check.py`

```python
Lines 342-384:
    async def _check_signal_processor(self) -> ComponentHealth:
        """Check signal processing system"""
        
        # This checks SIGNALS, not price updates!
        last_signal = await self.repository.get_last_signal_time()
        
        if last_signal:
            time_since = datetime.now(timezone.utc) - last_signal
            
            if time_since > timedelta(minutes=5):
                status = HealthStatus.DEGRADED
                error_message = f"No signals for {time_since.seconds//60} minutes"
```

**ПРОБЛЕМА:** Это для signals, не для price updates.

**НУЖНО ДОБАВИТЬ НОВЫЙ МЕТОД:**
```python
async def _check_price_updates(self) -> ComponentHealth:
    """Check price update staleness for all symbols"""
    try:
        stale_alerts = []
        
        if not hasattr(self, 'price_monitor'):
            return ComponentHealth(
                name="Price Updates",
                type=ComponentType.WEBSOCKET,  # Reuse type
                status=HealthStatus.UNHEALTHY,
                last_check=datetime.now(timezone.utc),
                error_message="Price monitor not initialized"
            )
        
        # Check each symbol
        for symbol in self.price_monitor.last_prices.keys():
            staleness = self.price_monitor.get_staleness_seconds(symbol)
            
            if staleness > 300:  # 5 minutes - CRITICAL
                stale_alerts.append({
                    'symbol': symbol,
                    'staleness_seconds': staleness,
                    'level': 'critical'
                })
            elif staleness > 180:  # 3 minutes - WARNING
                stale_alerts.append({
                    'symbol': symbol,
                    'staleness_seconds': staleness,
                    'level': 'warning'
                })
        
        # Generate alerts
        if stale_alerts:
            critical = [a for a in stale_alerts if a['level'] == 'critical']
            warnings = [a for a in stale_alerts if a['level'] == 'warning']
            
            error_msg = f"Critical stale: {len(critical)}, Warnings: {len(warnings)}"
            status = HealthStatus.CRITICAL if critical else HealthStatus.DEGRADED
            
            # Log to database
            await self.repository.create_alert(
                alert_type='price_staleness',
                severity='critical' if critical else 'warning',
                message=error_msg,
                metadata={'stale_symbols': [a['symbol'] for a in critical]}
            )
        else:
            error_msg = None
            status = HealthStatus.HEALTHY
        
        return ComponentHealth(
            name="Price Updates",
            type=ComponentType.WEBSOCKET,
            status=status,
            last_check=datetime.now(timezone.utc),
            error_message=error_msg,
            metadata={
                'critical_stale': len([a for a in stale_alerts if a['level'] == 'critical']),
                'warning_stale': len([a for a in stale_alerts if a['level'] == 'warning']),
                'stale_alerts': stale_alerts[:5]  # Top 5
            }
        )
    except Exception as e:
        return ComponentHealth(
            name="Price Updates",
            type=ComponentType.WEBSOCKET,
            status=HealthStatus.UNHEALTHY,
            last_check=datetime.now(timezone.utc),
            error_message=str(e)
        )
```

---

## 4. UPDATE_PRICE INTEGRATION

### Где вызывается:
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/position_manager.py`

```
# From grep output:
await trailing_manager.update_price(symbol, position.current_price)
```

### Где используется:
**File:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/aged_position_monitor_v2.py`

```python
Lines 224-288:
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
                    ...
                )
```

**НУЖНО ДОБАВИТЬ STALENESS CHECK:**
```python
async def check_price_target(self, symbol: str, current_price: Decimal):
    """
    Check if current price reached target for aged position
    Called by UnifiedPriceMonitor through adapter
    """
    
    if symbol not in self.aged_targets:
        return
    
    target = self.aged_targets[symbol]
    
    # NEW: Check price staleness
    if hasattr(self.position_manager, 'price_monitor'):
        staleness = self.position_manager.price_monitor.get_staleness_seconds(symbol)
        
        if staleness > 300:  # 5 minutes
            logger.error(f"⚠️ {symbol}: Price data is stale ({staleness}s). Skipping aged check.")
            # Log critical event
            await self.repository.create_aged_monitoring_event(
                aged_position_id=target.position_id,
                event_type='stale_price_warning',
                event_metadata={'staleness_seconds': staleness}
            )
            return  # Skip this check
        
        elif staleness > 180:  # 3 minutes
            logger.warning(f"⚠️ {symbol}: Price data is degraded ({staleness}s)")
    
    # Continue with normal logic...
    # Log monitoring event to database
    if self.repository:
        try:
            await self.repository.create_aged_monitoring_event(
                ...
            )
```

---

## SUMMARY TABLE

| Компонент | Файл | Линии | Что есть | Что нужно |
|-----------|------|-------|----------|-----------|
| Timestamps | unified_price_monitor.py | 35-102 | float timestamp | datetime + staleness check |
| Health Check (Connection) | improved_stream.py | 376-405 | Global | Per-symbol tracking |
| Health Check (System) | health_check.py | 324-340 | MOCK | Real per-symbol check |
| Price Staleness Alerts | health_check.py | 342-384 | For signals | New method for prices |
| Update Price Distribution | unified_price_monitor.py | 89-114 | Basic callback | Staleness validation |
| Aged Position Checks | aged_position_monitor_v2.py | 224-288 | Basic logic | Staleness guards |

