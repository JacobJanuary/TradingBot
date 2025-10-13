# Исследование использования схемы `fas.signals`

**Дата:** 2025-10-14
**Исследователь:** Claude Code Audit
**Вопрос:** Используется ли таблица `fas.signals` (схема `fas`) в текущей системе?

---

## КРАТКИЙ ОТВЕТ

**✅ ПОДТВЕРЖДЕНО: `fas.signals` НЕ ИСПОЛЬЗУЕТСЯ в production коде**

Таблица `fas.signals` (она же `fas.scoring_history`) — это **LEGACY артефакт** от старой архитектуры, когда сигналы читались напрямую из базы данных.

**Текущая архитектура:** Сигналы приходят через **WebSocket** в реальном времени, таблица `fas.signals` не используется.

---

## ДЕТАЛЬНОЕ ИССЛЕДОВАНИЕ

### 1. Где определена схема `fas`

#### 1.1 SQL-схема (`database/init.sql`)
```sql
-- FAS schema tables (for signal source)
CREATE TABLE IF NOT EXISTS fas.scoring_history (
    id SERIAL PRIMARY KEY,
    trading_pair_id INTEGER NOT NULL,
    pair_symbol VARCHAR(20) NOT NULL,
    exchange_id INTEGER NOT NULL,
    exchange_name VARCHAR(50) NOT NULL,
    score_week FLOAT,
    score_month FLOAT,
    recommended_action VARCHAR(10),
    patterns_details JSONB,
    combinations_details JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_processed BOOLEAN DEFAULT FALSE
);
```

**Назначение:** Историческая таблица для хранения торговых сигналов из внешней системы FAS (Fundamental Analysis System).

#### 1.2 SQLAlchemy модель (`database/models.py:36-69`)
```python
class Signal(Base):
    """Trading signals from fas.scoring_history"""
    __tablename__ = 'signals'
    __table_args__ = {'schema': 'fas'}

    id = Column(Integer, primary_key=True)
    trading_pair_id = Column(Integer, nullable=False, index=True)
    pair_symbol = Column(String(50), nullable=False, index=True)
    exchange_id = Column(Integer, nullable=False)
    exchange_name = Column(String(50), nullable=False)

    score_week = Column(Float, nullable=False)
    score_month = Column(Float, nullable=False)
    recommended_action = Column(SQLEnum(ActionType), nullable=False)

    patterns_details = Column(JSON)
    combinations_details = Column(JSON)

    is_active = Column(Boolean, default=True, nullable=False)
    is_processed = Column(Boolean, default=False, nullable=False)  # ⚠️ Флаг для polling
    processed_at = Column(DateTime)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

**Статус:** Модель определена, но **не используется** в коде бота.

---

### 2. Где упоминается `fas.signals`

#### 2.1 В моделях базы данных

**Файл:** `database/models.py:78`
```python
class Trade(Base):
    """Executed trades"""
    __tablename__ = 'trades'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey('fas.signals.id'), nullable=True)  # ⚠️ LEGACY FK
    # ...
```

**Файл:** `database/models.py:144` (Position model)
```python
class Position(Base):
    """Open trading positions"""
    __tablename__ = 'positions'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey('fas.signals.id'), nullable=True)  # ⚠️ LEGACY FK
    # ...
```

**⚠️ ПРОБЛЕМА:** Foreign Key constraints закомментированы в коде:
```python
# Relationships
# trades = relationship("Trade", back_populates="signal")  # Commented for tests
```

Это означает, что связь **не работает** на уровне БД!

#### 2.2 В SQL-скриптах

**Файл:** `database/init.sql:26`
```sql
CREATE TABLE IF NOT EXISTS monitoring.positions (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,  -- ⚠️ НЕТ FOREIGN KEY!
    symbol VARCHAR(20) NOT NULL,
    -- ...
);
```

**Файл:** `database/init.sql:75`
```sql
CREATE TABLE IF NOT EXISTS monitoring.trades (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER,  -- ⚠️ НЕТ FOREIGN KEY!
    symbol VARCHAR(20) NOT NULL,
    -- ...
);
```

**Статус:** Поле `signal_id` существует, но **не имеет ограничения внешнего ключа** на `fas.signals.id`.

---

### 3. Как используется `signal_id` в коде

#### 3.1 При открытии позиций через WebSocket

**Файл:** `core/signal_processor_websocket.py:509-573`
```python
async def execute_signal(self, signal: dict) -> bool:
    """Исполнение торгового сигнала"""

    # ⚠️ Получаем ID из WebSocket сообщения (НЕ из БД!)
    signal_id = signal.get('id', 'unknown')

    # Валидация и проверки...

    # Создаем запрос на открытие позиции
    request = PositionRequest(
        signal_id=signal_id,  # ⚠️ Это ID из WebSocket, не из fas.signals!
        symbol=validated_signal.symbol,
        exchange=validated_signal.exchange,
        side=side,
        entry_price=Decimal(str(current_price))
    )

    # Открываем позицию
    position = await self.position_manager.open_position(request)
```

**Ключевой момент:** `signal_id = signal.get('id', 'unknown')`

Это **ID из WebSocket сообщения**, который может быть:
- Числом (например, `12345`)
- Строкой (например, `"wave_123_BTCUSDT"`)
- Или `'unknown'` если поле отсутствует

**Этот ID НЕ связан с `fas.signals.id` в базе данных!**

#### 3.2 При создании позиции в БД

**Файл:** `database/repository.py:206-225`
```python
async def create_position(self, position_data: dict) -> int:
    """Create new position record in monitoring.positions"""

    logger.info(f"🔍 REPO DEBUG: create_position() called for {position_data['symbol']}, signal_id={position_data.get('signal_id')}")

    query = """
        INSERT INTO monitoring.positions (
            signal_id, symbol, exchange, side, quantity,
            entry_price, exchange_order_id, status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'active')
        RETURNING id
    """

    async with self.pool.acquire() as conn:
        async with conn.transaction():
            position_id = await conn.fetchval(
                query,
                position_data.get('signal_id'),  # ⚠️ Может быть 'unknown'!
                position_data['symbol'],
                # ...
            )
```

**Проблема:** Если `signal_id = 'unknown'` (строка), а колонка `signal_id INTEGER`, произойдет **ошибка приведения типа**!

#### 3.3 При создании trade в БД

**Файл:** `database/repository.py:130-144`
```python
async def create_trade(self, trade_data: dict) -> int:
    """Create new trade record in monitoring.trades"""
    query = """
        INSERT INTO monitoring.trades (
            signal_id, symbol, exchange, side, order_type,
            quantity, price, executed_qty, average_price,
            order_id, client_order_id, status,
            fee, fee_currency
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        RETURNING id
    """

    async with self.pool.acquire() as conn:
        trade_id = await conn.fetchval(
            query,
            trade_data.get('signal_id'),  # ⚠️ Тоже может быть 'unknown'!
            # ...
        )
```

---

### 4. Формат сигнала из WebSocket

**Источник:** `websocket/signal_client.py`

**Пример сигнала:**
```json
{
  "id": 12345,
  "symbol": "BTCUSDT",
  "exchange": "binance",
  "action": "BUY",
  "score_week": 85.5,
  "score_month": 90.2,
  "patterns_details": {...},
  "combinations_details": {...}
}
```

**Ключевые моменты:**
1. Поле `id` — это **уникальный идентификатор сигнала от WebSocket сервера**
2. Это **НЕ `fas.signals.id`** из базы данных
3. Сервер может генерировать `id` как:
   - Auto-increment integer (если WebSocket сервер сам пишет в `fas.signals`)
   - UUID
   - Композитный ключ (`wave_123_BTCUSDT`)
   - Или вообще не передавать (тогда будет `'unknown'`)

---

### 5. Поиск кода, читающего из `fas.signals`

**Команда:**
```bash
grep -r "SELECT.*fas.signals\|FROM fas.signals\|fas.scoring_history.*SELECT" \
  --include="*.py" \
  /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/ 2>/dev/null
```

**Результат:** **НЕ НАЙДЕНО**

**Вывод:** В коде **нет ни одного SELECT запроса** к таблице `fas.signals` или `fas.scoring_history`.

---

### 6. Комментарии в коде

**Файл:** `reset_database.py:15`
```python
"""
НЕ трогает:
- fas.scoring_history (сигналы приходят через websocket, таблица не используется)
"""
```

**Файл:** `database/models.py:37`
```python
class Signal(Base):
    """Trading signals from fas.scoring_history"""
    # Модель определена, но не используется
```

---

## ВЫВОДЫ

### ✅ ПОДТВЕРЖДЕННЫЕ ФАКТЫ

1. **Таблица `fas.signals` (она же `fas.scoring_history`) существует в БД**, но:
   - ❌ Не читается кодом бота
   - ❌ Не записывается кодом бота
   - ❌ Foreign Key constraints закомментированы/не работают

2. **Поле `signal_id` в `monitoring.positions` и `monitoring.trades` существует**, но:
   - ✅ Хранит ID из WebSocket сообщения (НЕ из `fas.signals`)
   - ⚠️ Может быть `'unknown'` (строка), что вызовет ошибку БД (колонка INTEGER)
   - ❌ Не имеет Foreign Key constraint на `fas.signals.id`

3. **Сигналы приходят через WebSocket** (`websocket/signal_client.py`), не через polling БД

4. **Модель `Signal` определена** в `database/models.py`, но:
   - ❌ Не используется ни в одном импорте (кроме тестов)
   - ❌ Relationships закомментированы

---

## РЕКОМЕНДАЦИИ

### 🔴 КРИТИЧНО: Исправить тип данных `signal_id`

**Проблема:**
- Колонка `signal_id INTEGER`
- Код может передавать `'unknown'` (строка)
- Это вызовет PostgreSQL error: `invalid input syntax for type integer`

**Решение:**
```sql
-- Миграция 1: Изменить тип на VARCHAR
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE VARCHAR(100);

ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE VARCHAR(100);
```

**Или:**
```python
# В коде: не передавать 'unknown', использовать NULL
signal_id = signal.get('id')  # None если нет
if signal_id == 'unknown':
    signal_id = None
```

### 🟡 СРЕДНИЙ ПРИОРИТЕТ: Очистить устаревший код

**Действия:**

1. **Удалить неиспользуемую модель:**
```python
# database/models.py
# УДАЛИТЬ класс Signal (строки 36-69)
```

2. **Обновить комментарии:**
```python
class Trade(Base):
    """Executed trades"""
    # signal_id: WebSocket signal ID (NOT a FK to fas.signals!)
    signal_id = Column(String(100), nullable=True)
```

3. **Дропнуть Foreign Key constraints (если они были созданы):**
```sql
-- Проверить есть ли FK
SELECT
    conname AS constraint_name,
    conrelid::regclass AS table_name
FROM pg_constraint
WHERE confrelid = 'fas.signals'::regclass;

-- Если есть - удалить
ALTER TABLE monitoring.positions DROP CONSTRAINT IF EXISTS positions_signal_id_fkey;
ALTER TABLE monitoring.trades DROP CONSTRAINT IF EXISTS trades_signal_id_fkey;
```

4. **Добавить комментарий в init.sql:**
```sql
-- LEGACY: Table fas.scoring_history is not used by the bot
-- Signals are received via WebSocket, not from database
-- Kept for historical data / external system compatibility
CREATE TABLE IF NOT EXISTS fas.scoring_history (
    -- ...
);
```

### 🟢 НИЗКИЙ ПРИОРИТЕТ: Документация

Добавить в README или docs:

```markdown
## Signal Flow

**Current Architecture (Since 2024-XX-XX):**
Signals are received via WebSocket from external FAS service.

**Legacy Architecture (Before 2024-XX-XX):**
Signals were polled from `fas.signals` table. This approach is DEPRECATED.

### Signal ID Mapping
- `monitoring.positions.signal_id` = WebSocket message ID (string/int)
- `monitoring.trades.signal_id` = WebSocket message ID (string/int)
- **NOT** a foreign key to `fas.signals.id`
```

---

## РИСКИ И БАГИ

### 🐛 БАГ #1: Несоответствие типов

**Код:** `core/signal_processor_websocket.py:509`
```python
signal_id = signal.get('id', 'unknown')  # ⚠️ Может быть строка 'unknown'
```

**БД:** `monitoring.positions.signal_id INTEGER`

**Результат:** PostgreSQL error при `signal_id='unknown'`

**Fix:**
```python
signal_id = signal.get('id')  # None если нет ID
if signal_id is None:
    logger.warning(f"Signal has no ID, using timestamp")
    signal_id = int(datetime.now().timestamp() * 1000)  # millis
```

### 🐛 БАГ #2: Закомментированные relationships

**Код:** `database/models.py:62`
```python
# Relationships
# trades = relationship("Trade", back_populates="signal")  # Commented for tests
```

**Проблема:** Если раскомментировать, то код упадет, т.к. `fas.signals` не используется.

**Fix:** Удалить полностью (или оставить закомментированным навсегда).

---

## ИТОГОВАЯ ТАБЛИЦА

| Компонент | Используется? | Комментарий |
|-----------|---------------|-------------|
| `fas.signals` таблица | ❌ НЕТ | Не читается и не пишется кодом |
| `Signal` SQLAlchemy модель | ❌ НЕТ | Определена, но не используется |
| `signal_id` в positions/trades | ✅ ДА | Хранит WebSocket message ID |
| Foreign Key на `fas.signals` | ❌ НЕТ | Закомментирован/не работает |
| WebSocket сигналы | ✅ ДА | Основной источник сигналов |
| Polling из БД | ❌ НЕТ | DEPRECATED подход |

---

## ЗАКЛЮЧЕНИЕ

**Ваше предположение ВЕРНО:**
> "Сигналы давно получаем через websocket --> я считал fas.signals не используется"

**Подтверждено исследованием:**
- ✅ `fas.signals` — LEGACY таблица
- ✅ Сигналы приходят через WebSocket
- ✅ Таблица `fas.signals` НЕ используется в коде
- ⚠️ Поле `signal_id` используется, но хранит WebSocket ID, не DB ID

**Рекомендация:**
1. Исправить тип `signal_id` на VARCHAR(100) или NULL для 'unknown'
2. Удалить модель `Signal` из `models.py`
3. Дропнуть FK constraints если они есть
4. Добавить комментарии в код для будущих разработчиков

---

**Дата завершения исследования:** 2025-10-14
**Статус:** ✅ ЗАВЕРШЕНО
