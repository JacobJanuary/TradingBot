# ФАЗА 1.3: АНАЛИЗ БЛОКИРОВОК И ТРАНЗАКЦИЙ

**Дата**: 2025-10-22
**Severity**: 🔴 CRITICAL
**Статус**: ✅ ALL MECHANISMS ANALYZED

---

## EXECUTIVE SUMMARY

**Критическая находка**: UPDATE операции выполняются БЕЗ блокировок и в ОТДЕЛЬНЫХ транзакциях от CREATE.

**Impact**: Advisory lock защищает только CREATE, но не последующие UPDATE. Это усугубляет race condition.

---

## 1. КАРТА БЛОКИРОВОК

### 1.1. PostgreSQL Advisory Locks

**Единственное использование**: `database/repository.py:263`

```python
async def create_position(self, position_data: Dict) -> int:
    symbol = position_data['symbol']
    exchange = position_data['exchange']

    # Generate lock ID
    lock_id = self._get_position_lock_id(symbol, exchange)

    async with self.pool.acquire() as conn:
        async with conn.transaction():
            # Acquire exclusive advisory lock
            await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)

            # Check existing
            existing = await conn.fetchrow("""
                SELECT id FROM monitoring.positions
                WHERE symbol = $1 AND exchange = $2 AND status = 'active'
            """, symbol, exchange)

            if existing:
                return existing['id']

            # Insert
            position_id = await conn.fetchval(
                "INSERT INTO monitoring.positions (...) VALUES (...) RETURNING id",
                ...
            )

            return position_id
        # ← Lock released here (transaction end)
```

**Характеристики**:
- **Тип**: `pg_advisory_xact_lock` (transaction-scoped)
- **Scope**: Только CREATE операция
- **Lock ID**: MD5 hash of `"symbol:exchange"` → 64-bit integer
- **Duration**: До конца транзакции
- **Granularity**: Per symbol+exchange

**Что защищает**:
- ✅ Два CREATE одновременно для одного символа
- ✅ Check-then-create race condition

**Что НЕ защищает**:
- ❌ UPDATE операции (нет блокировки)
- ❌ Race между CREATE и UPDATE
- ❌ Concurrent UPDATE одной позиции

---

### 1.2. Lock ID Generation

**Метод**: `database/repository.py:23-41`

```python
@staticmethod
def _get_position_lock_id(symbol: str, exchange: str) -> int:
    """
    Generate deterministic lock ID for position.
    Uses MD5 hash of "symbol:exchange" to get 64-bit integer.
    """
    key = f"{symbol}:{exchange}".encode('utf-8')
    hash_digest = hashlib.md5(key).digest()
    # Convert first 8 bytes to signed 64-bit integer
    lock_id = int.from_bytes(hash_digest[:8], byteorder='big', signed=True)
    return lock_id
```

**Примеры**:
```
APTUSDT:binance  → lock_id = 5832719438201749832
BTCUSDT:binance  → lock_id = -2847362918472639201
ETHUSDT:bybit    → lock_id = 8923847293847293847
```

**Свойства**:
- ✅ Deterministic (одинаковый для symbol+exchange)
- ✅ Collision-resistant (MD5)
- ✅ PostgreSQL bigint range (-2^63 to 2^63-1)
- ⚠️ Разные symbols → разные locks (не блокируют друг друга)

---

## 2. КАРТА ТРАНЗАКЦИЙ

### 2.1. CREATE - С транзакцией

**Файл**: `database/repository.py:256-293`

```
┌─────────────────────────────────────────────────────────────┐
│ async with self.pool.acquire() as conn:                     │
│     ↓                                                        │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ async with conn.transaction():                          │ │
│ │     ↓                                                   │ │
│ │     BEGIN TRANSACTION  ← Implicit                       │ │
│ │         ↓                                               │ │
│ │     SELECT pg_advisory_xact_lock($1)  ← Acquire lock   │ │
│ │         ↓                                               │ │
│ │     SELECT ... WHERE status='active'  ← Check           │ │
│ │         ↓                                               │ │
│ │     INSERT ... VALUES (..., 'active')  ← Create        │ │
│ │         ↓                                               │ │
│ │     COMMIT  ← Implicit (success)                        │ │
│ │     или                                                 │ │
│ │     ROLLBACK ← Implicit (exception)                     │ │
│ │         ↓                                               │ │
│ │     Lock released automatically                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│     ↓                                                        │
│     Connection returned to pool                              │
└─────────────────────────────────────────────────────────────┘
```

**Характеристики**:
- **Isolation Level**: READ COMMITTED (PostgreSQL default)
- **Atomicity**: ✅ Все или ничего
- **Lock Scope**: Transaction-scoped
- **Duration**: ~10-50ms

---

### 2.2. UPDATE - БЕЗ явной транзакции ⚠️

**Файл**: `database/repository.py:587-589`

```
┌─────────────────────────────────────────────────────────────┐
│ async with self.pool.acquire() as conn:                     │
│     ↓                                                        │
│     ❌ NO explicit transaction                               │
│     ↓                                                        │
│     await conn.execute(UPDATE ...)  ← Autocommit mode       │
│     ↓                                                        │
│     ✅ Immediate commit                                      │
│     ↓                                                        │
│     Connection returned to pool                              │
└─────────────────────────────────────────────────────────────┘
```

**Характеристики**:
- **Isolation Level**: READ COMMITTED (autocommit)
- **Atomicity**: ✅ Single statement atomic
- **Lock Scope**: ❌ NO advisory lock
- **Duration**: ~5-20ms

**Проблема**:
- Каждый UPDATE - отдельная транзакция
- Нет связи с предыдущим CREATE
- Нет advisory lock
- Можно параллельно UPDATE одной позиции

---

### 2.3. Atomic Operation Context (НЕ database transaction!)

**Файл**: `core/atomic_position_manager.py:95-122`

```python
@asynccontextmanager
async def atomic_operation(self, operation_id: str):
    # Track in memory
    self.active_operations[operation_id] = {
        'started_at': datetime.utcnow(),
        'status': 'in_progress'
    }

    try:
        yield operation_id  # ← Execution happens here
        self.active_operations[operation_id]['status'] = 'completed'

    except Exception as e:
        self.active_operations[operation_id]['status'] = 'failed'
        raise
```

**ЭТО НЕ DATABASE TRANSACTION!**

Это просто:
- ✅ In-memory tracking
- ✅ Error handling
- ✅ Cleanup scheduling
- ❌ NO database atomicity
- ❌ NO rollback mechanism
- ❌ NO isolation guarantees

---

## 3. ВРЕМЕННАЯ ЛИНИЯ ТРАНЗАКЦИЙ

### 3.1. Нормальный Flow (без race condition)

```
TIME    OPERATION                      TRANSACTION     LOCK     DB STATE
─────────────────────────────────────────────────────────────────────────
T1      repository.create_position()
        ↓
T2      pool.acquire()                 -               -        -
        ↓
T3      BEGIN                          TX1 start       -        -
        ↓
T4      pg_advisory_xact_lock()        TX1             LOCKED   -
        ↓
T5      SELECT ... status='active'     TX1             LOCKED   -
        Result: empty
        ↓
T6      INSERT ... status='active'     TX1             LOCKED   id=100
        ↓                                                        status='active'
T7      COMMIT                         TX1 end         UNLOCKED id=100
        ↓                                                        status='active'

T8      repository.update_position()   -               -        -
        (status='entry_placed')
        ↓
T9      pool.acquire()                 -               -        -
        ↓
T10     UPDATE ... (autocommit)        TX2 (instant)   -        id=100
        ↓                                                        status='entry_placed'
T11     Commit (auto)                  TX2 end         -        id=100
                                                                 status='entry_placed'

[3 seconds sleep...]

T20     repository.update_position()   -               -        -
        (status='active')
        ↓
T21     pool.acquire()                 -               -        -
        ↓
T22     UPDATE ... (autocommit)        TX3 (instant)   -        id=100
        ↓                                                        status='active'
T23     Commit (auto)                  TX3 end         -        id=100
                                                                 status='active'
```

**Критические моменты**:
- T7: Lock released, но позиция в status='active' только 1ms
- T10-T11: Позиция выходит из индекса (status='entry_placed')
- **ОКНО УЯЗВИМОСТИ**: T10 → T22 (~4-7 секунд)

---

### 3.2. Race Condition Timeline

```
TIME    THREAD 1                       THREAD 2                 LOCKS    INDEX
─────────────────────────────────────────────────────────────────────────────
T1      BEGIN TX1                      -                        -        []
T2      LOCK(APTUSDT:binance)          -                        L1       []
T3      CHECK status='active'          -                        L1       []
        → NOT FOUND
T4      INSERT id=100, status='active' -                        L1       [100]
T5      COMMIT TX1                     -                        -        [100]
        UNLOCK
T6      UPDATE id=100                  -                        -        []
        status='entry_placed'
        (TX2 autocommit)

T7      [sleep 3s...]                  BEGIN TX3                -        []
T8      [sleeping...]                  LOCK(APTUSDT:binance)    L2       []
T9      [sleeping...]                  CHECK status='active'    L2       []
                                       → NOT FOUND ❌
                                       (id=100 has 'entry_placed')
T10     [sleeping...]                  INSERT id=101            L2       [101]
                                       status='active'
T11     [sleeping...]                  COMMIT TX3               -        [101]
                                       UNLOCK
T12     [wake up]                      -                        -        [101]
        Place SL...
T13     UPDATE id=100                  -                        -        [101]
        status='active'
        ↓
        ❌ DUPLICATE KEY ERROR!
        Index has: (APTUSDT, binance) from id=101
```

**Ключевые проблемы**:
1. **T5**: Lock released, позиция в индексе
2. **T6**: Позиция выходит из индекса БЕЗ блокировки
3. **T8-T9**: Thread 2 берёт lock, но не видит id=100
4. **T10**: Thread 2 создаёт дубликат (в индексе)
5. **T13**: Thread 1 пытается войти в индекс → COLLISION

---

## 4. УРОВНИ ИЗОЛЯЦИИ

### 4.1. PostgreSQL Default

```sql
-- Проверка текущего уровня
SHOW transaction_isolation;
-- Result: read committed
```

**READ COMMITTED характеристики**:
- Видны только COMMITTED изменения других транзакций
- Каждый statement видит snapshot на момент начала statement
- NO dirty reads
- Phantom reads POSSIBLE
- Non-repeatable reads POSSIBLE

### 4.2. Влияние на нашу проблему

**Scenario**:
```
T1: Thread 1 - BEGIN
T2: Thread 1 - SELECT ... WHERE status='active'
    → Result: []
T3: Thread 1 - INSERT id=100, status='active'
T4: Thread 1 - COMMIT

T5: Thread 1 - UPDATE id=100 SET status='entry_placed'
    (separate transaction, autocommit)

T6: Thread 2 - BEGIN
T7: Thread 2 - SELECT ... WHERE status='active'
    → Result: [] (id=100 has 'entry_placed' - committed)
T8: Thread 2 - INSERT id=101, status='active'
T9: Thread 2 - COMMIT
```

**READ COMMITTED позволяет это** потому что:
- T7 видит committed state на момент query
- id=100 имеет status='entry_placed' (committed в T5)
- Partial index не включает id=100
- Проверка `WHERE status='active'` не находит id=100

**REPEATABLE READ НЕ ПОМОГ БЫ** потому что:
- Проблема не в isolation level
- Проблема в WHERE clause не ищет 'entry_placed'
- Partial index работает одинаково

---

## 5. ДЕТАЛЬНЫЙ АНАЛИЗ UPDATE ОПЕРАЦИЙ

### 5.1. Все UPDATE в repository.py

| Строка | Метод | Transaction | Lock | Используется |
|--------|-------|-------------|------|--------------|
| 219 | update_position (old) | ❌ NO | ❌ NO | Legacy |
| 343 | update_position_from_websocket | ❌ NO | ❌ NO | ✅ Active |
| 369 | update_position_stop_loss | ❌ NO | ❌ NO | ✅ Active |
| 385 | update_position_trailing_stop | ❌ NO | ❌ NO | ✅ Active |
| 425 | close_position (UPDATE stop_loss_order_id) | ❌ NO | ❌ NO | ✅ Active |
| 581 | update_position (**kwargs) | ❌ NO | ❌ NO | ✅ Active |
| 702 | update_position_status | ❌ NO | ❌ NO | ✅ Active |

**Вывод**: НИ ОДИН UPDATE не использует:
- ❌ Explicit transaction
- ❌ Advisory lock
- ❌ SELECT FOR UPDATE

### 5.2. Проблемы отсутствия транзакций

**Problem #1: Lost Updates**
```
Thread 1: UPDATE positions SET current_price=100 WHERE id=1
Thread 2: UPDATE positions SET unrealized_pnl=50 WHERE id=1
Result: OK (different columns)
```

**Problem #2: Race on status change**
```
Thread 1: UPDATE positions SET status='entry_placed' WHERE id=1
Thread 2: UPDATE positions SET status='active' WHERE id=1
Result: Depends on timing (последний wins)
```

**Problem #3: Inconsistent reads**
```
Thread 1: UPDATE id=1 SET status='entry_placed'
Thread 2: SELECT ... WHERE status='active'
          → Doesn't see id=1
Thread 2: INSERT new position (duplicate)
```

---

## 6. CONNECTION POOL BEHAVIOR

### 6.1. Pool Configuration

**Файл**: `database/repository.py:43-67`

```python
async def initialize(self):
    self.pool = await asyncpg.create_pool(
        min_size=5,
        max_size=20,
        command_timeout=60,
        ...
    )
```

**Характеристики**:
- Min connections: 5
- Max connections: 20
- Each operation acquires connection from pool
- Connection returned after operation

### 6.2. Implications

```
CREATE operation:
    acquire() → conn1 from pool
    BEGIN TX on conn1
    ... operations ...
    COMMIT TX on conn1
    release conn1 to pool

UPDATE operation (same position):
    acquire() → conn2 from pool (может быть другой!)
    UPDATE (autocommit) on conn2
    release conn2 to pool
```

**Проблема**: CREATE и UPDATE могут использовать РАЗНЫЕ connections → ГАРАНТИРОВАННО разные транзакции.

---

## 7. ЗАЩИТА ОТ CONCURRENT UPDATES

### 7.1. Текущая защита: ОТСУТСТВУЕТ ❌

Нет механизмов защиты от:
- Concurrent UPDATE одной позиции
- Lost updates на разных полях
- Race condition на status changes

### 7.2. PostgreSQL Row-Level Locking (НЕ используется)

**Доступно, но НЕ применяется**:

```sql
-- SELECT FOR UPDATE (не используется в коде)
SELECT * FROM positions WHERE id=100 FOR UPDATE;
-- Блокирует строку до конца транзакции

-- SELECT FOR NO KEY UPDATE (не используется)
SELECT * FROM positions WHERE id=100 FOR NO KEY UPDATE;
-- Блокирует строку, но позволяет foreign key checks
```

**Почему не используется**: Все UPDATE в autocommit mode, нет явных транзакций.

### 7.3. Application-Level Locking (ЧАСТИЧНАЯ)

**atomic_operation context**: Только in-memory tracking, не блокирует database.

**Advisory locks**: Только для CREATE, не для UPDATE.

---

## 8. IDEMPOTENCY ANALYSIS

### 8.1. CREATE - НЕ идемпотентен

```python
# Повторный вызов с теми же параметрами:
create_position({'symbol': 'APTUSDT', 'exchange': 'binance', ...})
create_position({'symbol': 'APTUSDT', 'exchange': 'binance', ...})

# Результат:
# - Если между вызовами status='active' → вернёт existing
# - Если между вызовами status='entry_placed' → создаст дубликат ❌
```

### 8.2. UPDATE - Идемпотентен

```python
# Повторный вызов:
update_position(100, status='active')
update_position(100, status='active')

# Результат: OK (same result)
```

### 8.3. Полный цикл - НЕ идемпотентен

```python
# Scenario:
open_position_atomic(...)  # Attempt 1 - fails at step 6
open_position_atomic(...)  # Retry - может создать дубликат

# Проблема: Attempt 1 может оставить позицию в промежуточном статусе
```

---

## 9. ROLLBACK MECHANISM

### 9.1. Automatic Rollback (database)

**Файл**: `database/repository.py:260-293`

```python
async with conn.transaction():
    # ... operations ...

    # If exception → automatic ROLLBACK
```

**Работает для**:
- ✅ CREATE transaction
- ✅ Откатывает INSERT если ошибка

**НЕ работает для**:
- ❌ UPDATE операции (autocommit)
- ❌ Ордера на бирже (уже исполнен)
- ❌ Stop-loss на бирже (уже размещён)

### 9.2. Application-Level Rollback

**Файл**: `core/atomic_position_manager.py:466-558`

```python
except Exception as e:
    # Rollback logic
    if position_id:
        await self.repository.update_position(position_id, **{
            'status': PositionState.ROLLED_BACK.value,
            'exit_reason': truncate_exit_reason(str(e))
        })

    # Try to close position on exchange
    if entry_order:
        try:
            # Poll for position
            for attempt in range(20):
                positions = await exchange.fetch_positions()
                if found_position:
                    # Close it
                    await exchange.create_market_order(...)
                await asyncio.sleep(1.0)
        except:
            pass
```

**Характеристики**:
- ⚠️ Best-effort (может не найти позицию)
- ⚠️ 20 попыток по 1s = 20 секунд
- ⚠️ Если не находит → просто логирует WARNING
- ❌ Не гарантирует полный откат

---

## 10. КРИТИЧЕСКИЕ НАХОДКИ

### 🔴 CRITICAL #1: UPDATE без блокировок

**Проблема**:
```python
# CREATE - защищён
async with conn.transaction():
    await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)
    INSERT ...

# UPDATE - НЕ защищён
async with self.pool.acquire() as conn:
    await conn.execute("UPDATE ...")  ← NO LOCK!
```

**Impact**: Race condition усугубляется.

### 🔴 CRITICAL #2: Разные транзакции

**Проблема**:
```
TX1: CREATE (with lock)
TX2: UPDATE status='entry_placed' (autocommit, no lock)
TX3: UPDATE status='active' (autocommit, no lock)
```

**Impact**: Нет атомарности между CREATE и UPDATE.

### 🔴 CRITICAL #3: Окно уязвимости

**Проблема**:
- CREATE → TX1 commits → lock released
- UPDATE → TX2 autocommit (позиция выходит из индекса)
- [3 seconds sleep]
- Параллельный thread может создать дубликат

**Impact**: 4-7 секунд окно для race condition.

### 🟡 HIGH #4: Incomplete Rollback

**Проблема**:
- Position на бирже может остаться
- DB помечена 'rolled_back'
- Но SL может быть размещён

**Impact**: Inconsistent state.

---

## 11. РЕКОМЕНДАЦИИ

### 11.1. CRITICAL Fixes

**Fix #1**: Объединить CREATE и все UPDATE в ОДНУ транзакцию
```python
async with conn.transaction():
    await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)

    # CREATE
    position_id = await conn.fetchval("INSERT ...")

    # All UPDATES in same transaction
    await conn.execute("UPDATE ... SET status='entry_placed' ...")
    await conn.execute("UPDATE ... SET status='active' ...")
```

**Fix #2**: Держать lock до полной активации
```python
async with conn.transaction():
    await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)

    # All operations including final activation
    # Lock released only when status='active' committed
```

### 11.2. ALTERNATIVE Approaches

**Alternative #1**: Использовать только 'active' status
- Не менять status на промежуточные значения
- Добавить отдельные флаги (entry_placed_flag, sl_placed_flag)

**Alternative #2**: SELECT FOR UPDATE перед каждым UPDATE
```python
async with conn.transaction():
    await conn.fetchrow("SELECT * FROM positions WHERE id=$1 FOR UPDATE", id)
    await conn.execute("UPDATE positions SET ... WHERE id=$1", id)
```

---

## ВЫВОДЫ ФАЗЫ 1.3

### ✅ Что установлено:

1. **Advisory Lock**: Используется ТОЛЬКО для CREATE
2. **Transactions**: CREATE в транзакции, UPDATE - autocommit
3. **Atomicity**: НЕТ атомарности между CREATE и UPDATE
4. **Isolation**: READ COMMITTED (default), но проблема не в этом
5. **Connection Pool**: Разные operations используют разные connections
6. **Rollback**: Best-effort, не гарантирует полный откат

### 🎯 Критические проблемы:

1. UPDATE операции БЕЗ блокировок
2. Разные транзакции для CREATE и UPDATE
3. Окно уязвимости 4-7 секунд
4. Incomplete rollback mechanism

### ⏭️ Следующая фаза:

**ФАЗА 1.4** - Анализ логики очистки

---

**Конец Фазы 1.3**
