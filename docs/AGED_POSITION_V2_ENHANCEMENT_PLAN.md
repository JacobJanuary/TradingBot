# 🚀 ПЛАН УЛУЧШЕНИЯ: Aged Position Monitor V2

**Дата:** 2025-10-23
**Текущая версия:** V2 Minimal (302 строки)
**Цель:** Полнофункциональная V2 с БД и мониторингом

---

## 📊 ТЕКУЩЕЕ СОСТОЯНИЕ V2

### Что уже реализовано ✅

```python
# core/aged_position_monitor_v2.py

✅ WebSocket интеграция через UnifiedPriceMonitor
✅ MARKET ордера для гарантированного закрытия
✅ Правильная временная логика (grace → progressive)
✅ Расчет target price с учетом комиссий
✅ Обработка LONG/SHORT позиций
```

### Что отсутствует ❌

```python
❌ Использование таблиц aged_positions
❌ Детальное логирование в БД
❌ Retry механизм для failed ордеров
❌ Метрики для мониторинга
❌ Recovery после рестарта
```

---

## 🎯 ПЛАН УЛУЧШЕНИЙ

### PHASE 1: Интеграция с БД (Приоритет: ВЫСОКИЙ)

#### 1.1 Создание aged_position записи при обнаружении

```python
# В методе add_aged_position() добавить:

async def add_aged_position(self, position):
    """Add position to aged monitoring WITH database tracking"""

    symbol = position.symbol

    if symbol in self.aged_targets:
        return

    # ... existing code ...

    # NEW: Create database entry
    if self.repository:
        try:
            aged_entry = await self.repository.create_aged_position(
                position_id=position.id,
                symbol=symbol,
                exchange=position.exchange,
                side=position.side,
                entry_price=position.entry_price,
                quantity=position.quantity,
                position_opened_at=position.opened_at,
                detected_at=datetime.now(timezone.utc),
                status='detected',
                target_price=target_price,
                breakeven_price=self._calculate_breakeven(position),
                config={
                    'max_age_hours': self.max_age_hours,
                    'grace_period_hours': self.grace_period_hours,
                    'loss_step_percent': str(self.loss_step_percent),
                    'max_loss_percent': str(self.max_loss_percent)
                }
            )

            # Store DB ID for later updates
            target.db_id = aged_entry.id

            logger.info(f"📝 Created aged_position entry {aged_entry.id} for {symbol}")

        except Exception as e:
            logger.error(f"Failed to create aged_position in DB: {e}")
            # Continue anyway - DB is for tracking, not critical
```

#### 1.2 Обновление статуса при изменении фазы

```python
async def _update_phase_if_needed(self, target: AgedPositionTarget):
    """Check and update phase based on current age"""

    position = await self._get_position(target.symbol)
    if not position:
        return

    age_hours = self._calculate_age_hours(position)
    hours_over_limit = age_hours - self.max_age_hours

    new_phase, new_target_price, new_loss_tolerance = self._calculate_target(
        position, hours_over_limit
    )

    # Phase transition detected
    if new_phase != target.phase:
        old_phase = target.phase
        target.phase = new_phase
        target.target_price = new_target_price
        target.loss_tolerance = new_loss_tolerance

        # Update in database
        if self.repository and hasattr(target, 'db_id'):
            await self.repository.update_aged_position_status(
                aged_id=target.db_id,
                new_status=f'{new_phase}_active',
                target_price=new_target_price,
                current_loss_tolerance_percent=new_loss_tolerance,
                hours_aged=age_hours
            )

        logger.info(
            f"📊 Phase transition for {target.symbol}: "
            f"{old_phase} → {new_phase}, new target: ${new_target_price:.4f}"
        )
```

#### 1.3 Логирование мониторинга

```python
async def check_price_target(self, symbol: str, current_price: Decimal):
    """Check if current price reached target WITH monitoring logs"""

    if symbol not in self.aged_targets:
        return

    target = self.aged_targets[symbol]

    # Log monitoring event
    if self.repository and hasattr(target, 'db_id'):
        await self.repository.create_aged_monitoring_event(
            aged_position_id=target.db_id,
            event_type='price_check',
            market_price=current_price,
            target_price=target.target_price,
            price_distance_percent=abs((current_price - target.target_price) / target.target_price * 100)
        )

    # ... rest of existing code ...
```

### PHASE 2: Robust Order Execution (Приоритет: ВЫСОКИЙ)

#### 2.1 Retry механизм для MARKET ордеров

```python
async def _trigger_market_close(self, position, target, trigger_price):
    """Execute MARKET close with retry logic"""

    MAX_RETRIES = 3
    RETRY_DELAY = [1, 3, 5]  # Exponential backoff

    for attempt in range(MAX_RETRIES):
        try:
            # Existing order creation code
            order = await exchange.exchange.create_order(...)

            if order:
                # Success - update DB and return
                if self.repository and hasattr(target, 'db_id'):
                    await self.repository.mark_aged_position_closed(
                        aged_id=target.db_id,
                        close_price=trigger_price,
                        close_order_id=order['id'],
                        actual_pnl=self._calculate_actual_pnl(position, trigger_price),
                        actual_pnl_percent=self._calculate_pnl_percent(position, trigger_price),
                        close_reason=self._determine_close_reason(target.phase, pnl_percent)
                    )

                return True

        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")

            # Log attempt in DB
            if self.repository and hasattr(target, 'db_id'):
                await self.repository.increment_close_attempt(
                    target.db_id,
                    error_message=str(e)
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY[attempt])
            else:
                # Final failure - mark as error
                if self.repository and hasattr(target, 'db_id'):
                    await self.repository.update_aged_position_status(
                        target.db_id,
                        new_status='error',
                        last_error_message=str(e)
                    )

                # Send alert
                await self._send_critical_alert(
                    f"Failed to close aged position {position.symbol} after {MAX_RETRIES} attempts"
                )

    return False
```

#### 2.2 Проверка позиции перед закрытием

```python
async def _verify_position_before_close(self, position) -> bool:
    """Verify position still exists on exchange"""

    exchange = self.exchanges.get(position.exchange)
    if not exchange:
        return False

    try:
        # Fetch current position from exchange
        positions = await exchange.exchange.fetch_positions([position.symbol])

        for pos in positions:
            if pos['symbol'] == position.symbol and abs(pos['contracts']) > 0:
                # Update quantity if changed
                if abs(pos['contracts']) != abs(position.quantity):
                    logger.warning(
                        f"Position size changed: {position.quantity} → {pos['contracts']}"
                    )
                    position.quantity = pos['contracts']

                return True

        # Position not found
        logger.warning(f"Position {position.symbol} not found on exchange")
        return False

    except Exception as e:
        logger.error(f"Failed to verify position: {e}")
        return False  # Assume doesn't exist if can't verify
```

### PHASE 3: Recovery & Persistence (Приоритет: СРЕДНИЙ)

#### 3.1 Загрузка активных aged позиций при старте

```python
async def initialize(self):
    """Load active aged positions from database on startup"""

    if not self.repository:
        return

    try:
        # Load all non-closed aged positions
        active_entries = await self.repository.get_active_aged_positions(
            statuses=['detected', 'grace_active', 'progressive_active']
        )

        logger.info(f"📥 Loading {len(active_entries)} active aged positions from DB")

        for entry in active_entries:
            # Verify position still exists
            position = await self.position_manager.get_position(entry.symbol)

            if position:
                # Recreate target tracking
                target = AgedPositionTarget(
                    symbol=entry.symbol,
                    entry_price=entry.entry_price,
                    target_price=entry.target_price,
                    phase=self._status_to_phase(entry.status),
                    loss_tolerance=entry.current_loss_tolerance_percent,
                    hours_aged=entry.hours_aged,
                    position_id=str(entry.position_id)
                )
                target.db_id = entry.id

                self.aged_targets[entry.symbol] = target
                logger.info(f"✅ Restored aged tracking for {entry.symbol}")
            else:
                # Position no longer exists - mark as error
                await self.repository.update_aged_position_status(
                    entry.id,
                    new_status='error',
                    last_error_message='Position not found after restart'
                )

    except Exception as e:
        logger.error(f"Failed to load aged positions from DB: {e}")
```

### PHASE 4: Метрики и мониторинг (Приоритет: СРЕДНИЙ)

#### 4.1 Prometheus метрики

```python
from prometheus_client import Counter, Gauge, Histogram

# Define metrics
aged_positions_total = Gauge(
    'aged_positions_total',
    'Total number of aged positions being monitored'
)

aged_positions_by_phase = Gauge(
    'aged_positions_by_phase',
    'Number of aged positions by phase',
    ['phase']
)

aged_position_close_duration = Histogram(
    'aged_position_close_duration_seconds',
    'Time taken to close aged position',
    buckets=[1, 5, 10, 30, 60, 120, 300]
)

aged_position_closes = Counter(
    'aged_position_closes_total',
    'Total aged position closes',
    ['phase', 'reason', 'success']
)

# Update metrics in methods
def update_metrics(self):
    """Update Prometheus metrics"""

    aged_positions_total.set(len(self.aged_targets))

    # Count by phase
    phase_counts = {'grace': 0, 'progressive': 0}
    for target in self.aged_targets.values():
        phase_counts[target.phase] = phase_counts.get(target.phase, 0) + 1

    for phase, count in phase_counts.items():
        aged_positions_by_phase.labels(phase=phase).set(count)
```

#### 4.2 Статистика из БД

```python
async def get_statistics(self) -> Dict:
    """Get comprehensive statistics from database"""

    if not self.repository:
        return self.stats  # Return basic in-memory stats

    try:
        db_stats = await self.repository.get_aged_positions_statistics(
            from_date=datetime.now() - timedelta(days=7)  # Last 7 days
        )

        return {
            'current': {
                'monitored': len(self.aged_targets),
                'by_phase': self._count_by_phase(),
                'oldest_hours': self._get_oldest_age()
            },
            'historical': {
                'total_processed': db_stats['total_count'],
                'successful_closes': db_stats['closed_count'],
                'error_count': db_stats['error_count'],
                'avg_age_at_close': db_stats['avg_age_hours'],
                'avg_pnl_percent': db_stats['avg_pnl_percent'],
                'by_close_reason': db_stats['by_close_reason']
            },
            'performance': {
                'avg_close_time_seconds': db_stats['avg_close_duration'],
                'success_rate': db_stats['success_rate'],
                'retry_rate': db_stats['avg_close_attempts']
            }
        }

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        return self.stats
```

### PHASE 5: Интеграция и оркестрация (Приоритет: НИЗКИЙ)

#### 5.1 События и callbacks

```python
class AgedPositionEvents:
    """Event types for aged position lifecycle"""

    POSITION_DETECTED = 'aged.position.detected'
    PHASE_CHANGED = 'aged.phase.changed'
    CLOSE_TRIGGERED = 'aged.close.triggered'
    CLOSE_COMPLETED = 'aged.close.completed'
    CLOSE_FAILED = 'aged.close.failed'

async def emit_event(self, event_type: str, data: Dict):
    """Emit event for other components"""

    if hasattr(self, 'event_emitter'):
        await self.event_emitter.emit(event_type, data)

    # Log important events
    if event_type in [AgedPositionEvents.CLOSE_FAILED]:
        logger.critical(f"CRITICAL EVENT: {event_type} - {data}")
```

---

## 📝 REPOSITORY МЕТОДЫ

### Новые методы для database/repository.py

```python
# === AGED POSITIONS ===

async def create_aged_position(
    self,
    position_id: int,
    symbol: str,
    exchange: str,
    side: str,
    entry_price: Decimal,
    quantity: Decimal,
    position_opened_at: datetime,
    detected_at: datetime,
    status: str,
    target_price: Decimal,
    breakeven_price: Decimal,
    config: Dict
) -> Dict:
    """Create new aged position entry"""

    query = """
        INSERT INTO monitoring.aged_positions (
            position_id, symbol, exchange, side,
            entry_price, quantity, position_opened_at,
            detected_at, status, target_price,
            breakeven_price, config
        ) VALUES (
            %(position_id)s, %(symbol)s, %(exchange)s, %(side)s,
            %(entry_price)s, %(quantity)s, %(position_opened_at)s,
            %(detected_at)s, %(status)s, %(target_price)s,
            %(breakeven_price)s, %(config)s
        )
        RETURNING *
    """
    # ... implementation ...

async def get_active_aged_positions(
    self,
    statuses: List[str] = None
) -> List[Dict]:
    """Get all active aged positions"""

    if not statuses:
        statuses = ['detected', 'grace_active', 'progressive_active']

    query = """
        SELECT * FROM monitoring.aged_positions
        WHERE status = ANY(%(statuses)s)
        ORDER BY detected_at DESC
    """
    # ... implementation ...

async def update_aged_position_status(
    self,
    aged_id: str,
    new_status: str,
    **kwargs
) -> bool:
    """Update aged position status and optional fields"""

    # Build dynamic update query
    fields = ['status = %(new_status)s']
    params = {'aged_id': aged_id, 'new_status': new_status}

    for key, value in kwargs.items():
        fields.append(f"{key} = %({key})s")
        params[key] = value

    query = f"""
        UPDATE monitoring.aged_positions
        SET {', '.join(fields)}, updated_at = NOW()
        WHERE id = %(aged_id)s
        RETURNING *
    """
    # ... implementation ...

async def create_aged_monitoring_event(
    self,
    aged_position_id: str,
    event_type: str,
    market_price: Decimal = None,
    target_price: Decimal = None,
    price_distance_percent: Decimal = None,
    action_taken: str = None,
    success: bool = None,
    error_message: str = None,
    event_metadata: Dict = None
) -> bool:
    """Log monitoring event"""

    query = """
        INSERT INTO monitoring.aged_positions_monitoring (
            aged_position_id, event_type, market_price,
            target_price, price_distance_percent,
            action_taken, success, error_message,
            event_metadata
        ) VALUES (
            %(aged_position_id)s, %(event_type)s, %(market_price)s,
            %(target_price)s, %(price_distance_percent)s,
            %(action_taken)s, %(success)s, %(error_message)s,
            %(event_metadata)s
        )
    """
    # ... implementation ...
```

---

## 🚦 ПРИОРИТЕТЫ ВНЕДРЕНИЯ

### Immediate (1-2 дня)
1. ✅ Включить V2 через флаг
2. ⚡ Добавить базовое логирование в БД (Phase 1.1)
3. ⚡ Добавить retry для ордеров (Phase 2.1)

### Short-term (1 неделя)
1. 📊 Полная интеграция с БД (Phase 1)
2. 🔄 Recovery после рестарта (Phase 3)
3. 📈 Базовые метрики (Phase 4.1)

### Long-term (2-4 недели)
1. 📊 Расширенная статистика (Phase 4.2)
2. 🎯 События и интеграция (Phase 5)
3. 📱 Алерты и нотификации

---

## ✅ КРИТЕРИИ УСПЕХА

1. **Нет "застрявших" aged позиций** - все закрываются вовремя
2. **Success rate > 95%** - редкие failures
3. **Среднее время закрытия < 5 секунд** после достижения target
4. **Полный аудит в БД** - можно проследить всю историю
5. **Recovery работает** - после рестарта продолжает мониторинг

---

**Подготовил:** AI Assistant
**Статус:** План готов к реализации
**Следующий шаг:** Включить V2 и начать Phase 1