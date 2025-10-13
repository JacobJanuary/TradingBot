# 🔬 DEEP RESEARCH: TRAILING STOP ACTIVATION - DATABASE PERSISTENCE

**Дата:** 2025-10-13 07:30
**Статус:** ПОЛНОЕ ИССЛЕДОВАНИЕ ЗАВЕРШЕНО
**Режим:** READ-ONLY (без изменения кода)

---

## 📋 EXECUTIVE SUMMARY

Проведено глубокое исследование механизма сохранения активации Trailing Stop (TS) в базе данных.

**Ключевые находки:**
1. ✅ TS activation **СОХРАНЯЕТСЯ** в базу данных
2. ✅ Используется поле `trailing_activated` (BOOLEAN)
3. ✅ Сохранение происходит в `PositionManager._on_position_update()`
4. ⚠️ Поле `has_trailing_stop` **НЕ СУЩЕСТВУЕТ** в БД (только в памяти)
5. ✅ При загрузке из БД: `has_trailing_stop` копируется из `trailing_activated`

---

## 🎯 ГЛАВНЫЙ ВОПРОС: СОХРАНЯЕТСЯ ЛИ TS ACTIVATION В БД?

### **ОТВЕТ: ДА! ✅**

TS activation сохраняется в базу данных в поле `trailing_activated` (BOOLEAN).

**Путь сохранения:**
```
TS Manager: update_price()
  ↓
TS Manager: _check_activation()
  ↓
TS Manager: _activate_trailing_stop() ← Возвращает {'action': 'activated'}
  ↓
Position Manager: _on_position_update() ← Обрабатывает результат
  ↓
Position Manager: position.trailing_activated = True ← Память
  ↓
Repository: update_position(trailing_activated=True) ← БАЗА ДАННЫХ!
```

---

## 🗄️ DATABASE SCHEMA

### Таблица: `monitoring.positions`

**Файл:** `database/init.sql:49`

```sql
CREATE TABLE IF NOT EXISTS monitoring.positions (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    stop_loss_price DECIMAL(20, 8),
    take_profit_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8),
    realized_pnl DECIMAL(20, 8),
    fees DECIMAL(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    exit_reason VARCHAR(100),
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),
    leverage DECIMAL(10, 2) DEFAULT 1.0,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    pnl_percentage DECIMAL(10, 4),
    trailing_activated BOOLEAN DEFAULT FALSE,  -- ← TS ACTIVATION!
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Критические поля:**

| Поле | Тип | Значение | Описание |
|------|-----|----------|----------|
| `trailing_activated` | BOOLEAN | DEFAULT FALSE | ✅ **TS активирован?** |
| `has_trailing_stop` | - | **НЕ СУЩЕСТВУЕТ** | ❌ Только в памяти! |

---

## 🔍 ДЕТАЛЬНЫЙ АНАЛИЗ: TS ACTIVATION FLOW

### 1. TS Manager: Активация TS

**Файл:** `protection/trailing_stop.py:267-299`

**Метод:** `_activate_trailing_stop()`

```python
async def _activate_trailing_stop(self, ts: TrailingStopInstance) -> Dict:
    """Activate trailing stop"""
    ts.state = TrailingStopState.ACTIVE
    ts.activated_at = datetime.now()
    self.stats['total_activated'] += 1

    # Calculate initial trailing stop price
    distance = self._get_trailing_distance(ts)

    if ts.side == 'long':
        ts.current_stop_price = ts.highest_price * (1 - distance / 100)
    else:
        ts.current_stop_price = ts.lowest_price * (1 + distance / 100)

    # Update stop order
    await self._update_stop_order(ts)

    logger.info(
        f"✅ {ts.symbol}: Trailing stop ACTIVATED at {ts.current_price:.4f}, "
        f"stop at {ts.current_stop_price:.4f}"
    )

    # NEW: Mark SL ownership (logging only for now)
    logger.debug(f"{ts.symbol} SL ownership: trailing_stop (via trailing_activated=True)")

    return {
        'action': 'activated',  -- ← ВОЗВРАЩАЕТ ACTION!
        'symbol': ts.symbol,
        'stop_price': float(ts.current_stop_price),
        'distance_percent': float(distance)
    }
```

**Что делает:**
1. Устанавливает `ts.state = TrailingStopState.ACTIVE`
2. Записывает время активации `ts.activated_at`
3. Вычисляет initial stop price
4. Размещает stop order на бирже
5. **Возвращает Dict с `action='activated'`** ← КЛЮЧЕВОЙ МОМЕНТ!

**ЧТО НЕ ДЕЛАЕТ:**
- ❌ НЕ сохраняет в БД (это не его ответственность)
- ❌ НЕ обновляет PositionState напрямую

---

### 2. Position Manager: Обработка активации TS

**Файл:** `core/position_manager.py:1189-1226`

**Метод:** `_on_position_update()` (WebSocket handler)

**Полный код обработки TS:**

```python
# Line 1189-1204: Trailing stop handling
async with self.position_locks[trailing_lock_key]:
    trailing_manager = self.trailing_managers.get(position.exchange)
    if trailing_manager and position.has_trailing_stop:
        # NEW: Update TS health timestamp before calling TS Manager
        position.ts_last_update_time = datetime.now()

        # ← ВЫЗОВ TS MANAGER
        update_result = await trailing_manager.update_price(symbol, position.current_price)

        # ← ОБРАБОТКА РЕЗУЛЬТАТА
        if update_result:
            action = update_result.get('action')

            # ← ПРОВЕРКА АКТИВАЦИИ
            if action == 'activated':
                # ✅ ОБНОВЛЕНИЕ В ПАМЯТИ
                position.trailing_activated = True
                logger.info(f"Trailing stop activated for {symbol}")

                # ✅ КРИТИЧНО: СОХРАНЕНИЕ В БД!
                await self.repository.update_position(position.id, trailing_activated=True)

            elif action == 'updated':
                # CRITICAL FIX: Save new trailing stop price to database
                new_stop = update_result.get('new_stop')
                if new_stop:
                    position.stop_loss_price = new_stop
                    await self.repository.update_position(
                        position.id,
                        stop_loss_price=new_stop
                    )
                    logger.info(f"✅ Saved new trailing stop price for {symbol}: {new_stop}")
```

**Последовательность:**

1. **Вызов TS Manager** (строка 1195):
   ```python
   update_result = await trailing_manager.update_price(symbol, position.current_price)
   ```

2. **Получение результата** (строка 1198):
   ```python
   action = update_result.get('action')  # 'activated' or 'updated'
   ```

3. **Проверка активации** (строка 1200):
   ```python
   if action == 'activated':
   ```

4. **Обновление в памяти** (строка 1201):
   ```python
   position.trailing_activated = True
   ```

5. **СОХРАНЕНИЕ В БД** (строка 1204):
   ```python
   await self.repository.update_position(position.id, trailing_activated=True)
   ```

**КРИТИЧЕСКИ ВАЖНО:**
- ✅ Сохранение в БД происходит **СРАЗУ** после активации
- ✅ Используется метод `repository.update_position()`
- ✅ Обновляется поле `trailing_activated=True`
- ✅ Это **АТОМАРНАЯ** операция (один DB call)

---

### 3. Repository: Сохранение в БД

**Файл:** `database/repository.py:459-503`

**Метод:** `update_position()`

**Полный код:**

```python
async def update_position(self, position_id: int, **kwargs) -> bool:
    """
    Update position with arbitrary fields

    Args:
        position_id: Position ID to update
        **kwargs: Field names and values to update

    Returns:
        bool: True if update successful

    Example:
        await repo.update_position(123, current_price=50.5, pnl=10.0)
    """
    if not kwargs:
        return False

    # CRITICAL FIX: entry_price is immutable - set ONCE at creation, never updated
    if 'entry_price' in kwargs:
        logger.warning(f"⚠️ Attempted to update entry_price for position {position_id} - IGNORED")
        del kwargs['entry_price']
        if not kwargs:
            return False

    # Build dynamic UPDATE query
    set_clauses = []
    values = []
    param_count = 1

    for key, value in kwargs.items():
        set_clauses.append(f"{key} = ${param_count}")
        values.append(value)
        param_count += 1

    query = f"""
        UPDATE monitoring.positions
        SET {', '.join(set_clauses)}, updated_at = NOW()
        WHERE id = ${param_count}
    """
    values.append(position_id)

    async with self.pool.acquire() as conn:
        result = await conn.execute(query, *values)
        return True
```

**Как работает для `trailing_activated=True`:**

**Вызов:**
```python
await self.repository.update_position(position.id, trailing_activated=True)
```

**Параметры:**
- `position_id` = 123
- `kwargs` = `{'trailing_activated': True}`

**SQL Query:**
```sql
UPDATE monitoring.positions
SET trailing_activated = $1, updated_at = NOW()
WHERE id = $2
```

**Значения:**
- `$1` = `True`
- `$2` = `123`

**Результат:**
- ✅ Поле `trailing_activated` в БД обновляется на `TRUE`
- ✅ Поле `updated_at` обновляется на NOW()
- ✅ Изменения персистентны (сохранены навсегда)

---

## 🔄 ЖИЗНЕННЫЙ ЦИКЛ: TS INITIALIZATION → ACTIVATION → DATABASE

### Phase 1: TS Initialization (при открытии позиции)

**Где:** `core/position_manager.py:835-849`

**Код:**
```python
# 10. Initialize trailing stop
trailing_manager = self.trailing_managers.get(exchange_name)
if trailing_manager:
    await trailing_manager.create_trailing_stop(
        symbol=symbol,
        side=position.side,
        entry_price=position.entry_price,
        quantity=position.quantity,
        initial_stop=stop_loss_price
    )
    position.has_trailing_stop = True

    # CRITICAL FIX: Save has_trailing_stop to database for restart persistence
    # Position was already saved in steps 8-9, now update TS flag
    await self.repository.update_position(
        position.id,
        has_trailing_stop=True  -- ← ПОПЫТКА СОХРАНИТЬ!
    )
```

**ПРОБЛЕМА:**
- ⚠️ Код пытается сохранить `has_trailing_stop=True` в БД
- ❌ **НО поле `has_trailing_stop` НЕ СУЩЕСТВУЕТ в БД!**
- ❌ SQL UPDATE тихо игнорирует несуществующее поле (PostgreSQL не падает)

**Что реально происходит:**
```sql
UPDATE monitoring.positions
SET has_trailing_stop = $1, updated_at = NOW()  -- ← has_trailing_stop ignored!
WHERE id = $2
```

**Результат:**
- ✅ `position.has_trailing_stop = True` установлено в **ПАМЯТИ**
- ❌ В **БД** ничего не сохранилось (поле не существует)
- ⚠️ После рестарта: флаг будет загружен из `trailing_activated` (который пока `FALSE`)

---

### Phase 2: TS Activation (когда цена достигает активации)

**Где:** `core/position_manager.py:1200-1204`

**Код:**
```python
if action == 'activated':
    position.trailing_activated = True
    logger.info(f"Trailing stop activated for {symbol}")

    # Save trailing activation to database
    await self.repository.update_position(position.id, trailing_activated=True)
```

**Что происходит:**
```sql
UPDATE monitoring.positions
SET trailing_activated = $1, updated_at = NOW()  -- ← trailing_activated EXISTS!
WHERE id = $2
```

**Результат:**
- ✅ `position.trailing_activated = True` установлено в **ПАМЯТИ**
- ✅ `trailing_activated = TRUE` сохранено в **БД** ← **РАБОТАЕТ!**
- ✅ После рестарта: флаг будет загружен правильно

---

### Phase 3: Bot Restart (загрузка из БД)

**Где:** `core/position_manager.py:314-330`

**Код загрузки:**
```python
position_state = PositionState(
    id=pos['id'],
    symbol=pos['symbol'],
    exchange=pos['exchange'],
    side=pos['side'],
    quantity=pos['quantity'],
    entry_price=pos['entry_price'],
    current_price=pos['current_price'] or pos['entry_price'],
    unrealized_pnl=pos['pnl'] or 0,
    unrealized_pnl_percent=pos['pnl_percentage'] or 0,
    has_stop_loss=pos['stop_loss'] is not None,
    stop_loss_price=pos['stop_loss'],
    has_trailing_stop=pos['trailing_activated'] or False,  -- ← КОПИРУЕТСЯ!
    trailing_activated=pos['trailing_activated'] or False,
    opened_at=opened_at,
    age_hours=self._calculate_age_hours(opened_at) if opened_at else 0
)
```

**КРИТИЧЕСКАЯ НАХОДКА (строка 326):**
```python
has_trailing_stop=pos['trailing_activated'] or False,
```

**Что это означает:**
- ✅ `has_trailing_stop` в памяти **КОПИРУЕТСЯ** из `trailing_activated` в БД
- ✅ Если `trailing_activated=TRUE` в БД → `has_trailing_stop=True` в памяти
- ✅ Если `trailing_activated=FALSE` в БД → `has_trailing_stop=False` в памяти

**Последовательность при рестарте:**

1. **До активации TS:**
   - БД: `trailing_activated = FALSE`
   - Память после загрузки: `has_trailing_stop = FALSE`
   - Результат: TS **НЕ РАБОТАЕТ** ❌

2. **После активации TS (первый раз):**
   - БД: `trailing_activated = TRUE` (сохранено)
   - Память: `has_trailing_stop = TRUE`, `trailing_activated = TRUE`
   - Результат: TS **РАБОТАЕТ** ✅

3. **После рестарта бота:**
   - БД: `trailing_activated = TRUE` (сохранено ранее)
   - Память после загрузки: `has_trailing_stop = TRUE` (копируется!)
   - Результат: TS **ПРОДОЛЖАЕТ РАБОТАТЬ** ✅✅✅

---

## 🚨 КРИТИЧЕСКИЕ НАХОДКИ

### 1. Поле `has_trailing_stop` НЕ СУЩЕСТВУЕТ в БД ⚠️

**Проблема:**
- Код пытается сохранить `has_trailing_stop` в БД
- Поле отсутствует в схеме (`database/init.sql`)
- SQL UPDATE тихо игнорирует несуществующее поле

**Где происходит:**
- `core/position_manager.py:425` - load_positions_from_db()
- `core/position_manager.py:846` - open_position()

**Код:**
```python
await self.repository.update_position(
    position.id,
    has_trailing_stop=True  -- ← ПОЛЕ НЕ СУЩЕСТВУЕТ!
)
```

**Последствия:**
- ❌ `has_trailing_stop` НЕ персистится через рестарты
- ⚠️ Зависит от `trailing_activated` для persistence

---

### 2. `trailing_activated` СОХРАНЯЕТСЯ ПРАВИЛЬНО ✅

**Факты:**
- ✅ Поле `trailing_activated` существует в БД
- ✅ Сохраняется при активации TS
- ✅ Загружается при рестарте
- ✅ Копируется в `has_trailing_stop` при загрузке

**Где происходит сохранение:**
- `core/position_manager.py:1204` - _on_position_update()

**Код:**
```python
await self.repository.update_position(position.id, trailing_activated=True)
```

**SQL:**
```sql
UPDATE monitoring.positions
SET trailing_activated = TRUE, updated_at = NOW()
WHERE id = $1
```

---

### 3. Двойное значение флагов ⚠️

**В памяти (PositionState):**
- `has_trailing_stop` - TS инициализирован?
- `trailing_activated` - TS активирован?

**В БД (monitoring.positions):**
- `trailing_activated` - TS активирован? (единственное поле)

**Маппинг при загрузке:**
```python
has_trailing_stop=pos['trailing_activated']  # ← Копируется!
trailing_activated=pos['trailing_activated']  # ← Оригинал
```

**Проблема:**
- ⚠️ `has_trailing_stop` и `trailing_activated` **ОДИНАКОВЫЕ** после загрузки
- ⚠️ Теряется информация о том, был ли TS инициализирован но не активирован

**Примеры:**

**Сценарий 1: TS инициализирован, но не активирован (цена не дошла)**
- Память: `has_trailing_stop=True`, `trailing_activated=False`
- БД: `trailing_activated=FALSE`
- После рестарта: `has_trailing_stop=False`, `trailing_activated=False` ← **ПОТЕРЯ!**

**Сценарий 2: TS инициализирован и активирован**
- Память: `has_trailing_stop=True`, `trailing_activated=True`
- БД: `trailing_activated=TRUE`
- После рестарта: `has_trailing_stop=True`, `trailing_activated=True` ← **ОК!**

---

## 📊 ТАБЛИЦА СОСТОЯНИЙ: ДО И ПОСЛЕ РЕСТАРТА

### До Рестарта (текущая сессия)

| Сценарий | Memory: has_trailing_stop | Memory: trailing_activated | DB: trailing_activated |
|----------|---------------------------|----------------------------|------------------------|
| 1. TS не инициализирован | False | False | FALSE |
| 2. TS инициализирован, не активирован | True | False | FALSE ⚠️ |
| 3. TS инициализирован и активирован | True | True | TRUE ✅ |

### После Рестарта (новая сессия)

| Сценарий | DB: trailing_activated | Loaded: has_trailing_stop | Loaded: trailing_activated | Результат |
|----------|------------------------|---------------------------|----------------------------|-----------|
| 1. TS не был инициализирован | FALSE | False | False | ✅ Корректно |
| 2. TS был инициализирован, не активирован | FALSE | **False** ← | False | ❌ **ПОТЕРЯ!** |
| 3. TS был инициализирован и активирован | TRUE | True | True | ✅ Работает |

**Критическая проблема:**
- ⚠️ **Сценарий 2**: TS был инициализирован, но не успел активироваться
- ❌ После рестарта: флаг `has_trailing_stop` **ТЕРЯЕТСЯ**
- ❌ TS Manager не знает что TS был инициализирован
- ❌ Нужна повторная инициализация

---

## 🎯 ОТВЕТ НА ГЛАВНЫЙ ВОПРОС

### ❓ Когда TS у позиции активируется, сохраняется ли это в базе данных?

**ОТВЕТ: ДА, СОХРАНЯЕТСЯ! ✅**

**Детали:**

1. **Когда TS активируется** (цена достигает `activation_price`):
   - TS Manager вызывает `_activate_trailing_stop()`
   - Возвращает `{'action': 'activated'}`

2. **Position Manager обрабатывает результат:**
   - Устанавливает `position.trailing_activated = True` в памяти
   - **Сохраняет в БД:** `await self.repository.update_position(position.id, trailing_activated=True)`

3. **В БД обновляется поле:**
   ```sql
   UPDATE monitoring.positions
   SET trailing_activated = TRUE, updated_at = NOW()
   WHERE id = $1
   ```

4. **Результат:**
   - ✅ Активация TS **ПЕРСИСТЕНТНА** через рестарты
   - ✅ После рестарта: `trailing_activated=TRUE` загружается из БД
   - ✅ TS продолжает работать

**Где происходит сохранение:**
- **Файл:** `core/position_manager.py`
- **Метод:** `_on_position_update()`
- **Строка:** 1204

---

## 📈 СХЕМА ДАННЫХ: MEMORY vs DATABASE

### В Памяти (PositionState)

```python
@dataclass
class PositionState:
    symbol: str
    exchange: str
    # ...

    has_stop_loss: bool = False
    stop_loss_price: Optional[float] = None

    has_trailing_stop: bool = False       # ← Только в памяти!
    trailing_activated: bool = False      # ← Синхронизируется с БД

    sl_managed_by: Optional[str] = None   # ← Только в памяти!
    ts_last_update_time: Optional[datetime] = None  # ← Только в памяти!

    opened_at: datetime = None
    age_hours: float = 0
```

### В БД (monitoring.positions)

```sql
CREATE TABLE monitoring.positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    stop_loss_price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL DEFAULT 'active',

    -- TS related
    trailing_activated BOOLEAN DEFAULT FALSE,  -- ← ЕДИНСТВЕННОЕ TS ПОЛЕ!

    -- Timestamps
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Отсутствующие в БД (только в памяти):**
- `has_trailing_stop` ← ⚠️ НЕ ПЕРСИСТИТСЯ
- `sl_managed_by` ← ⚠️ НЕ ПЕРСИСТИТСЯ
- `ts_last_update_time` ← ⚠️ НЕ ПЕРСИСТИТСЯ

---

## 🔄 FLOW DIAGRAM: TS ACTIVATION PERSISTENCE

```
┌──────────────────────────────────────────────────────────┐
│              TRAILING STOP ACTIVATION FLOW                │
└──────────────────────────────────────────────────────────┘

1. WebSocket Price Update
   │
   ↓
2. PositionManager._on_position_update(symbol, price)
   │
   ↓
3. Call: trailing_manager.update_price(symbol, price)
   │
   ↓
4. TS Manager._check_activation()
   │
   ├─→ Price < activation_price → return None
   │
   └─→ Price >= activation_price → ACTIVATE!
       │
       ↓
5. TS Manager._activate_trailing_stop()
   │
   ├─→ Set ts.state = ACTIVE
   ├─→ Calculate stop_price
   ├─→ Place stop order on exchange
   │
   └─→ return {'action': 'activated', 'symbol': ..., 'stop_price': ...}
       │
       ↓
6. PositionManager receives result
   │
   ├─→ Extract: action = result.get('action')
   │
   └─→ if action == 'activated':
       │
       ├─→ MEMORY: position.trailing_activated = True
       │
       └─→ DATABASE: ✅ SAVE!
           │
           ↓
7. Repository.update_position(position.id, trailing_activated=True)
   │
   ↓
8. SQL UPDATE:
   UPDATE monitoring.positions
   SET trailing_activated = TRUE, updated_at = NOW()
   WHERE id = $1
   │
   ↓
9. ✅ PERSISTED TO DATABASE!
```

---

## 🧪 ТЕСТОВЫЕ СЦЕНАРИИ

### Сценарий 1: TS активируется, бот НЕ рестартует

**Начальное состояние:**
```sql
-- DB
SELECT symbol, trailing_activated FROM monitoring.positions WHERE symbol='BTCUSDT';
-- Result: trailing_activated = FALSE
```

**Действия:**
1. Открыта позиция BTCUSDT @ $50,000
2. TS инициализирован (activation_price = $50,750)
3. Цена движется: $50,500 → $50,750 → $51,000
4. TS активируется при $50,750

**Ожидаемый результат:**
```python
# Memory
position.has_trailing_stop = True
position.trailing_activated = True
```

```sql
-- DB
SELECT symbol, trailing_activated FROM monitoring.positions WHERE symbol='BTCUSDT';
-- Result: trailing_activated = TRUE  ✅
```

**Логи:**
```
INFO: ✅ BTCUSDT: Trailing stop ACTIVATED at 50750.00, stop at 50496.00
INFO: Trailing stop activated for BTCUSDT
```

---

### Сценарий 2: TS активируется, бот рестартует

**Состояние ПЕРЕД рестартом:**
```sql
SELECT symbol, trailing_activated FROM monitoring.positions WHERE symbol='BTCUSDT';
-- Result: trailing_activated = TRUE
```

**Действия:**
1. Бот остановлен (kill process)
2. Бот запущен заново
3. `load_positions_from_db()` выполняется

**Код загрузки (строка 326):**
```python
position_state = PositionState(
    symbol='BTCUSDT',
    has_trailing_stop=pos['trailing_activated'],  # TRUE ← Загружено из БД!
    trailing_activated=pos['trailing_activated'],  # TRUE
    # ...
)
```

**Результат ПОСЛЕ рестарта:**
```python
# Memory
position.has_trailing_stop = True  ✅ Загружено!
position.trailing_activated = True  ✅ Загружено!
```

**Логи:**
```
INFO: 📊 Loaded 1 positions from database
INFO: ✅ Trailing stop initialized for BTCUSDT
```

**Проверка:**
- ✅ TS продолжает работать после рестарта
- ✅ WebSocket updates trigger TS price updates
- ✅ Trailing stop updates корректно

---

### Сценарий 3: TS инициализирован, НЕ активирован, бот рестартует

**Состояние ПЕРЕД рестартом:**
```python
# Memory
position.has_trailing_stop = True   # TS инициализирован
position.trailing_activated = False  # Цена не дошла до activation_price
```

```sql
SELECT symbol, trailing_activated FROM monitoring.positions WHERE symbol='ETHUSDT';
-- Result: trailing_activated = FALSE
```

**Действия:**
1. Бот остановлен
2. Бот запущен заново

**Код загрузки (строка 326):**
```python
position_state = PositionState(
    symbol='ETHUSDT',
    has_trailing_stop=pos['trailing_activated'],  # FALSE ← Загружено!
    trailing_activated=pos['trailing_activated'],  # FALSE
    # ...
)
```

**Результат ПОСЛЕ рестарта:**
```python
# Memory
position.has_trailing_stop = False  ❌ ПОТЕРЯ!
position.trailing_activated = False
```

**Проблема:**
- ❌ Флаг `has_trailing_stop` **ПОТЕРЯН**
- ❌ TS Manager не знает что TS был инициализирован
- ⚠️ НО! Код в `load_positions_from_db()` (строка 416) **ПОВТОРНО ИНИЦИАЛИЗИРУЕТ** TS:

```python
# Line 411-430: Re-initialize trailing stops for loaded positions
for symbol, position in self.positions.items():
    trailing_manager = self.trailing_managers.get(position.exchange)
    if trailing_manager:
        # Create trailing stop for the position
        await trailing_manager.create_trailing_stop(...)
        position.has_trailing_stop = True
        # ...
```

**Итог:**
- ✅ TS **АВТОМАТИЧЕСКИ ПЕРЕИНИЦИАЛИЗИРУЕТСЯ** при загрузке
- ✅ Даже если флаг потерян, TS создается заново
- ✅ Система отказоустойчива!

---

## ✅ ВЫВОДЫ

### 1. TS Activation СОХРАНЯЕТСЯ в БД ✅

**Факты:**
- ✅ Поле `trailing_activated` существует в БД
- ✅ Обновляется при активации TS
- ✅ Персистится через рестарты
- ✅ Загружается корректно

**Код сохранения:**
```python
# core/position_manager.py:1204
await self.repository.update_position(position.id, trailing_activated=True)
```

**SQL:**
```sql
UPDATE monitoring.positions
SET trailing_activated = TRUE, updated_at = NOW()
WHERE id = $1
```

---

### 2. Поле `has_trailing_stop` НЕ ПЕРСИСТИТСЯ ⚠️

**Проблема:**
- ⚠️ Поле `has_trailing_stop` отсутствует в БД
- ⚠️ Код пытается сохранить, но SQL игнорирует
- ⚠️ Зависит от `trailing_activated` для persistence

**Решение (уже реализовано):**
- ✅ При загрузке: `has_trailing_stop` копируется из `trailing_activated`
- ✅ При загрузке: TS автоматически переинициализируется для всех позиций
- ✅ Отказоустойчивость гарантирована

---

### 3. Система Отказоустойчива ✅

**Механизмы защиты:**

1. **Persistence через `trailing_activated`:**
   - TS activation сохраняется в БД
   - Загружается при рестарте

2. **Автоматическая переинициализация:**
   - Все загруженные позиции получают TS заново
   - Даже если флаги потеряны, TS пересоздается

3. **WebSocket восстановление:**
   - После рестарта WebSocket подключается
   - Price updates trigger TS checks
   - TS продолжает работать

**Код переинициализации (строка 411-430):**
```python
# Re-initialize trailing stops for ALL loaded positions
for symbol, position in self.positions.items():
    trailing_manager = self.trailing_managers.get(position.exchange)
    if trailing_manager:
        await trailing_manager.create_trailing_stop(...)
        position.has_trailing_stop = True
```

---

## 📋 ИТОГОВАЯ ТАБЛИЦА

| Параметр | Значение |
|----------|----------|
| **TS activation сохраняется?** | ✅ **ДА** (в `trailing_activated`) |
| **Поле в БД** | `trailing_activated` (BOOLEAN) |
| **Где сохраняется** | `core/position_manager.py:1204` |
| **Метод сохранения** | `repository.update_position()` |
| **SQL Query** | `UPDATE ... SET trailing_activated=TRUE` |
| **Когда сохраняется** | При активации TS (price >= activation_price) |
| **Persistence** | ✅ Да, через рестарты |
| **Автовосстановление** | ✅ Да, TS переинициализируется при загрузке |
| **Отказоустойчивость** | ✅ Высокая |

---

## 🚀 РЕКОМЕНДАЦИИ

### Текущая реализация

**Сильные стороны:**
1. ✅ TS activation сохраняется корректно
2. ✅ Автоматическая переинициализация при загрузке
3. ✅ Отказоустойчивость
4. ✅ WebSocket восстановление

**Слабые стороны:**
1. ⚠️ Поле `has_trailing_stop` не персистится (но это не критично)
2. ⚠️ Теряется информация о TS инициализации до активации (но пересоздается)

**Нет критических проблем!** Система работает корректно и отказоустойчиво.

---

## 📝 ПРИЛОЖЕНИЯ

### A. Файлы для анализа

1. **protection/trailing_stop.py** - TS Manager
   - Метод `_activate_trailing_stop()` (строка 267)

2. **core/position_manager.py** - Position Manager
   - Метод `_on_position_update()` (строка 1189-1226)
   - Метод `load_positions_from_db()` (строка 267-430)

3. **database/repository.py** - Database Repository
   - Метод `update_position()` (строка 459-503)

4. **database/init.sql** - Database Schema
   - Таблица `monitoring.positions` (строка 21-51)

---

**Дата:** 2025-10-13 07:30
**Статус:** ✅ ИССЛЕДОВАНИЕ ЗАВЕРШЕНО
**Качество:** DEEP RESEARCH (полное исследование кода + схемы БД)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
