# ШПАРГАЛКА: ВНЕДРЕНИЕ EVENT LOGGING

**Быстрый гайд для разработчиков**

---

## 🚀 БЫСТРЫЙ СТАРТ (5 МИНУТ)

### 1. Добавь новые EventType (1 минута)

Открой `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/event_logger.py`

Найди `class EventType(Enum):` и добавь:

```python
class EventType(Enum):
    # ... existing types ...

    # Wave events
    WAVE_MONITORING_STARTED = "wave_monitoring_started"
    WAVE_DETECTED = "wave_detected"
    WAVE_COMPLETED = "wave_completed"
    WAVE_NOT_FOUND = "wave_not_found"

    # Trailing Stop events
    TRAILING_STOP_CREATED = "trailing_stop_created"
    TRAILING_STOP_ACTIVATED = "trailing_stop_activated"
    TRAILING_STOP_UPDATED = "trailing_stop_updated"

    # Synchronization events
    PHANTOM_POSITION_CLOSED = "phantom_position_closed"
    MISSING_POSITION_ADDED = "missing_position_added"
    QUANTITY_MISMATCH = "quantity_mismatch_detected"

    # Zombie events
    ZOMBIE_ORDERS_DETECTED = "zombie_orders_detected"
    ZOMBIE_ORDER_CANCELLED = "zombie_order_cancelled"

    # Position Manager events
    POSITION_DUPLICATE_PREVENTED = "position_duplicate_prevented"
    RISK_LIMITS_EXCEEDED = "risk_limits_exceeded"
    SYMBOL_UNAVAILABLE = "symbol_unavailable"
    ORPHANED_SL_CLEANED = "orphaned_sl_cleaned"
```

### 2. Добавь импорт в файл (30 секунд)

В начале файла, который будешь инструментировать:

```python
from core.event_logger import get_event_logger, EventType
```

### 3. Используй шаблон (1 минута)

```python
# В критичном месте кода
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.YOUR_EVENT_NAME,  # Выбери из списка выше
        {
            'key1': value1,
            'key2': value2,
            # Добавь все важные данные
        },
        position_id=position_id,    # Если применимо
        symbol=symbol,              # Если применимо
        exchange=exchange,          # Если применимо
        severity='INFO',            # INFO/WARNING/ERROR/CRITICAL
        correlation_id=operation_id # Опционально, для связанных событий
    )
```

---

## 📋 ШАБЛОНЫ ПО КОМПОНЕНТАМ

### A. Position Manager (position_manager.py)

#### Phantom Detection
```python
# После обнаружения phantom
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.PHANTOM_POSITION_CLOSED,
        {
            'symbol': symbol,
            'position_id': position_id,
            'reason': 'not_on_exchange',
            'db_quantity': db_quantity
        },
        position_id=position_id,
        symbol=symbol,
        exchange=exchange_name,
        severity='WARNING'
    )
```

#### Risk Limits
```python
# При превышении лимитов
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.RISK_LIMITS_EXCEEDED,
        {
            'symbol': symbol,
            'current_exposure': float(self.total_exposure),
            'max_exposure': float(self.config.max_exposure_usd),
            'position_count': self.position_count,
            'max_positions': self.config.max_positions,
            'attempted_position_size': position_size_usd
        },
        symbol=symbol,
        exchange=exchange_name,
        severity='WARNING'
    )
```

#### Position Closed
```python
# При закрытии позиции
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.POSITION_CLOSED,
        {
            'symbol': symbol,
            'reason': reason,
            'realized_pnl': realized_pnl,
            'realized_pnl_percent': realized_pnl_percent,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'quantity': position.quantity,
            'side': position.side,
            'duration_hours': (datetime.now(timezone.utc) - position.opened_at).total_seconds() / 3600
        },
        position_id=position.id,
        symbol=symbol,
        exchange=position.exchange,
        severity='INFO'
    )
```

---

### B. Trailing Stop (trailing_stop.py)

#### TS Created
```python
# После создания TS
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.TRAILING_STOP_CREATED,
        {
            'symbol': symbol,
            'side': side,
            'entry_price': float(entry_price),
            'activation_price': float(ts.activation_price),
            'initial_stop': float(initial_stop) if initial_stop else None,
            'activation_percent': float(self.config.activation_percent)
        },
        symbol=symbol,
        severity='INFO'
    )
```

#### TS Activated
```python
# При активации TS
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.TRAILING_STOP_ACTIVATED,
        {
            'symbol': ts.symbol,
            'activation_price': float(ts.current_price),
            'stop_price': float(ts.current_stop_price),
            'distance_percent': float(distance),
            'entry_price': float(ts.entry_price),
            'profit_percent': float(self._calculate_profit_percent(ts))
        },
        symbol=ts.symbol,
        severity='INFO',
        correlation_id=f"ts_lifecycle_{ts.symbol}"
    )
```

#### TS Updated
```python
# При обновлении TS
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.TRAILING_STOP_UPDATED,
        {
            'symbol': ts.symbol,
            'old_stop': float(old_stop),
            'new_stop': float(new_stop_price),
            'improvement_percent': float(improvement),
            'highest_price': float(ts.highest_price),
            'update_count': ts.update_count
        },
        symbol=ts.symbol,
        severity='INFO',
        correlation_id=f"ts_lifecycle_{ts.symbol}"
    )
```

---

### C. Signal Processor (signal_processor_websocket.py)

#### Wave Detected
```python
# При обнаружении волны
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.WAVE_DETECTED,
        {
            'wave_timestamp': expected_wave_timestamp,
            'signal_count': len(wave_signals),
            'first_seen': datetime.now(timezone.utc).isoformat()
        },
        severity='INFO',
        correlation_id=f"wave_{expected_wave_timestamp}"
    )
```

#### Wave Completed
```python
# После обработки волны
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.WAVE_COMPLETED,
        {
            'wave_timestamp': expected_wave_timestamp,
            'positions_opened': executed_count,
            'failed': failed_count,
            'validation_errors': len(result.get('failed', [])),
            'duplicates': len(result.get('skipped', [])),
            'duration_seconds': (datetime.now(timezone.utc) - started_at).total_seconds(),
            'target': max_trades
        },
        severity='INFO',
        correlation_id=f"wave_{expected_wave_timestamp}"
    )
```

#### Signal Executed
```python
# После исполнения сигнала
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.SIGNAL_EXECUTED,
        {
            'wave_timestamp': wave_timestamp,
            'signal_id': signal.get('id'),
            'symbol': symbol,
            'signal_index': idx + 1,
            'total_signals': len(final_signals),
            'executed_count': executed_count
        },
        symbol=symbol,
        severity='INFO',
        correlation_id=f"wave_{wave_timestamp}"
    )
```

---

### D. Position Synchronizer (position_synchronizer.py)

#### Sync Started
```python
# Начало синхронизации
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.SYNCHRONIZATION_STARTED,
        {
            'exchanges': list(exchanges.keys()),
            'timestamp': datetime.now(timezone.utc).isoformat()
        },
        severity='INFO',
        correlation_id=f"sync_{datetime.now().timestamp()}"
    )
```

#### Missing Position Added
```python
# При добавлении недостающей позиции
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.MISSING_POSITION_ADDED,
        {
            'symbol': symbol,
            'exchange': exchange_name,
            'side': side,
            'quantity': abs(contracts),
            'entry_price': entry_price,
            'exchange_order_id': exchange_order_id
        },
        symbol=symbol,
        exchange=exchange_name,
        severity='INFO'
    )
```

---

### E. Zombie Manager (zombie_manager.py)

#### Zombies Detected
```python
# После обнаружения zombie orders
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.ZOMBIE_ORDERS_DETECTED,
        {
            'exchange': self.exchange.name,
            'count': len(zombies),
            'zombies': [
                {
                    'symbol': z.symbol,
                    'order_id': z.order_id,
                    'reason': z.reason,
                    'order_type': z.order_type
                }
                for z in zombies[:10]  # First 10
            ]
        },
        exchange=self.exchange.name,
        severity='WARNING'
    )
```

#### Zombie Cancelled
```python
# После отмены zombie order
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.ZOMBIE_ORDER_CANCELLED,
        {
            'order_id': zombie.order_id,
            'symbol': zombie.symbol,
            'exchange': zombie.exchange,
            'order_type': zombie.order_type,
            'reason': zombie.reason
        },
        symbol=zombie.symbol,
        exchange=zombie.exchange,
        severity='INFO'
    )
```

---

## 🎯 SEVERITY GUIDELINES

### INFO
- Нормальные операции
- Успешные действия
- Статистика

**Примеры:**
- Position created
- Wave detected
- TS activated
- Sync completed

### WARNING
- Ненормальные ситуации, но не критичные
- Пропущенные возможности
- Soft limits

**Примеры:**
- Risk limits exceeded
- Symbol filtered (stop-list)
- Wave not found
- Quantity mismatch

### ERROR
- Неудачные операции
- Ошибки, требующие внимания
- Потенциальные проблемы

**Примеры:**
- SL placement failed
- Order execution failed
- Symbol unavailable

### CRITICAL
- Серьёзные проблемы
- Требуют немедленных действий
- Угроза целостности системы

**Примеры:**
- Emergency close all
- Phantom position without SL
- Rollback failed
- Data corruption detected

---

## 📊 CORRELATION_ID PATTERNS

### Используй correlation_id для связанных событий:

#### Wave Processing
```python
correlation_id = f"wave_{wave_timestamp}"
```

#### Atomic Position Creation
```python
correlation_id = f"pos_{symbol}_{datetime.now().timestamp()}"
```

#### Trailing Stop Lifecycle
```python
correlation_id = f"ts_lifecycle_{symbol}"
```

#### Synchronization Cycle
```python
correlation_id = f"sync_{exchange}_{datetime.now().timestamp()}"
```

---

## ✅ CHECKLIST ПРИ ВНЕДРЕНИИ

### Перед коммитом:
- [ ] Добавлен импорт `from core.event_logger import get_event_logger, EventType`
- [ ] Добавлены новые EventType в event_logger.py
- [ ] Все вызовы log_event обёрнуты в `if event_logger:`
- [ ] Все вызовы log_event используют `await`
- [ ] Severity выбран правильно (INFO/WARNING/ERROR/CRITICAL)
- [ ] event_data содержит все критичные поля
- [ ] Добавлен symbol/exchange/position_id где применимо
- [ ] Использован correlation_id для связанных событий
- [ ] Протестировано на testnet
- [ ] Проверено что события пишутся в БД

### После деплоя:
- [ ] Запустить audit_verify_current_coverage.sql
- [ ] Проверить что новые event_type появились
- [ ] Убедиться что нет ошибок в логах
- [ ] Проверить performance (overhead <5ms)

---

## 🐛 TROUBLESHOOTING

### События не пишутся в БД
```python
# 1. Проверь что EventLogger инициализирован в main.py
event_logger = get_event_logger()
print(f"EventLogger available: {event_logger is not None}")

# 2. Проверь что таблица events существует
# Запусти SQL: SELECT * FROM monitoring.events LIMIT 1;

# 3. Проверь ошибки в логах
# grep "EventLogger" logs/trading_bot.log
```

### Async ошибки
```python
# НЕ ПРАВИЛЬНО (забыли await):
if event_logger:
    event_logger.log_event(...)  # ❌ Missing await

# ПРАВИЛЬНО:
if event_logger:
    await event_logger.log_event(...)  # ✅ Correct
```

### TypeError в event_data
```python
# НЕ ПРАВИЛЬНО (не JSON-serializable):
{
    'price': Decimal('123.45'),  # ❌ Decimal не serializable
    'time': datetime.now()       # ❌ datetime не serializable
}

# ПРАВИЛЬНО:
{
    'price': float(price),       # ✅ Convert to float
    'time': datetime.now(timezone.utc).isoformat()  # ✅ Convert to ISO string
}
```

---

## 📁 ФАЙЛЫ ДЛЯ СПРАВКИ

1. **AUDIT_DATABASE_LOGGING_COMPREHENSIVE.md** - Полный список событий по компонентам
2. **AUDIT_SUMMARY_ACTION_PLAN.md** - План внедрения и приоритеты
3. **audit_verify_current_coverage.sql** - SQL для проверки текущего состояния
4. **IMPLEMENTATION_CHEATSHEET.md** - Этот файл

---

## 🎓 ПРИМЕРЫ ДЛЯ ИЗУЧЕНИЯ

Посмотри как это уже реализовано:
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/core/atomic_position_manager.py` (100% coverage)
- `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/main.py` (BOT_STARTED, BOT_STOPPED)

---

## 🚀 НАЧНИ С ЭТОГО

### День 1 (4 часа):
1. Добавь EventType в event_logger.py (10 мин)
2. Инструментируй position_manager.py:
   - Phantom detection (30 мин)
   - Position closing (30 мин)
   - Risk limits (30 мин)
3. Тестируй на testnet (1 час)
4. Проверь результаты SQL запросом (30 мин)

### День 2 (4 часа):
1. Инструментируй trailing_stop.py:
   - TS creation (30 мин)
   - TS activation (30 мин)
   - TS updates (30 мин)
2. Тестируй (1 час)
3. Продолжи position_manager.py (1 час)

### День 3-4:
1. signal_processor_websocket.py
2. Остальные компоненты

---

**УДАЧИ! 🚀**

При вопросах - смотри примеры в atomic_position_manager.py
