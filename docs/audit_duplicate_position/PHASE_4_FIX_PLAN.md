# ФАЗА 4: ПЛАН ИСПРАВЛЕНИЯ
## Surgical Fix Options for Duplicate Position Error

**Дата:** 2025-10-23
**Статус:** В РАЗРАБОТКЕ
**Принцип:** "If it ain't broke, don't fix it" - МИНИМАЛЬНЫЕ изменения
**Confidence:** HIGH (85% based on Phase 3 evidence)

---

## 📋 EXECUTIVE SUMMARY

На основе детективного расследования (Фаза 3) разработано **5 вариантов исправления** с разным балансом риска/эффективности.

**Рекомендация:** Комбинированный подход (Option 3 + Option 4)
- Изменить проверку существования в `create_position()`
- Добавить defensive check перед final UPDATE
- Минимальный риск, максимальная эффективность

**Timeline:** 2-4 часа реализации + тестирование

---

## 🎯 ТАБЛИЦА ПРОБЛЕМНЫХ МЕСТ

### Матрица проблем

| # | Локация | Файл:Строка | Проблема | Severity | Fix Priority |
|---|---------|-------------|----------|----------|--------------|
| **1** | Partial Unique Index | `database/add_unique_active_position_constraint.sql:1-5` | `WHERE status='active'` создает gap | 🔴 CRITICAL | #1 |
| **2** | Check only 'active' | `database/repository.py:267-270` | `WHERE status='active'` пропускает intermediate | 🔴 CRITICAL | #1 |
| **3** | UPDATE without lock | `database/repository.py:545-589` | Autocommit, no advisory lock | 🟠 HIGH | #2 |
| **4** | Separate transactions | `core/atomic_position_manager.py:390-420` | CREATE и UPDATE не в одной TX | 🟠 HIGH | #3 |
| **5** | Sleep during vulnerability | `core/atomic_position_manager.py:412` | `await asyncio.sleep(3.0)` | 🟡 MEDIUM | #4 |
| **6** | Sync doesn't check intermediate | `core/position_manager.py:700-750` | Только `status='active'` | 🔴 CRITICAL | #1 |

### Детальный анализ проблемных мест

#### Problem #1: Partial Unique Index
```sql
-- File: database/add_unique_active_position_constraint.sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_position
ON monitoring.positions (symbol, exchange)
WHERE status = 'active';  -- ⚠️ PROBLEM: только для active
```

**Проблема:**
- Index работает ТОЛЬКО для `status = 'active'`
- Когда position в `entry_placed` или `pending_sl` - вне индекса
- Можно создать дубликат пока первый вне индекса

**Consequence:**
- Race condition window 3-7 секунд
- Duplicate key violation при попытке вернуться в 'active'

---

#### Problem #2: Check only 'active' status
```python
# File: database/repository.py:267-270
existing = await conn.fetchrow("""
    SELECT id FROM monitoring.positions
    WHERE symbol = $1 AND exchange = $2 AND status = 'active'  -- ⚠️ PROBLEM
""", symbol, exchange)
```

**Проблема:**
- Проверяет только позиции со `status='active'`
- НЕ видит позиции в `entry_placed`, `pending_sl`
- Считает что можно создавать новую позицию

**Consequence:**
- Позволяет создать дубликат если первая позиция в intermediate state

---

#### Problem #3: UPDATE without advisory lock
```python
# File: database/repository.py:545-589
async def update_position(self, position_id: int, **kwargs) -> bool:
    # ⚠️ NO LOCK
    # ⚠️ Autocommit (no explicit transaction)
    async with self.pool.acquire() as conn:
        result = await conn.execute(query, *values)
```

**Проблема:**
- UPDATE не использует advisory lock
- Каждый UPDATE - отдельная transaction (autocommit)
- Нет защиты от concurrent updates

**Consequence:**
- Potential lost updates
- Status transitions не atomic

---

#### Problem #4: Separate transactions CREATE/UPDATE
```python
# File: core/atomic_position_manager.py:390-420
# TX1: CREATE
position_id = await self.repository.create_position(...)  # Advisory lock here

# TX2: UPDATE (separate, no lock)
await self.repository.update_position(position_id, status='entry_placed')

# sleep 3s - vulnerable window

# TX3: UPDATE (separate, no lock)
await self.repository.update_position(position_id, status='active')  # ❌ Duplicate error
```

**Проблема:**
- CREATE и final UPDATE в разных транзакциях
- Lock released после CREATE
- Другой thread может создать дубликат между TX1 и TX3

**Consequence:**
- 3-7 second vulnerability window
- Race condition с Sync или другим Signal

---

#### Problem #5: Sleep during vulnerability
```python
# File: core/atomic_position_manager.py:412
await asyncio.sleep(3.0)  # ⚠️ Waiting for order settlement
```

**Проблема:**
- Fixed 3 second sleep
- Позиция вне индекса все это время
- Расширяет окно уязвимости

**Consequence:**
- Гарантированно 3s+ window
- Увеличивает probability of collision

---

#### Problem #6: Sync doesn't check intermediate states
```python
# File: core/position_manager.py:700-750 (approximate)
db_position = await self.repository.get_open_position(symbol, exchange_name)
# get_open_position checks: WHERE status = 'active'  -- ⚠️ PROBLEM

if db_position:
    # Restore from DB
else:
    # Position doesn't exist - create new one  ⚠️ FALSE if status != 'active'
    await self.repository.create_position(...)
```

**Проблема:**
- Sync использует тот же check (status='active')
- Не видит positions в intermediate states
- Решает создать новую позицию

**Consequence:**
- Scenario B (Signal + Sync) race condition
- Confirmed в APTUSDT case

---

## 🛠️ ВАРИАНТЫ ИСПРАВЛЕНИЯ

### Option 1: Change Unique Index (Full Coverage)
**Идея:** Убрать WHERE clause из unique index

#### Implementation
```sql
-- File: database/migrations/008_fix_unique_index.sql
DROP INDEX IF EXISTS monitoring.idx_unique_active_position;

CREATE UNIQUE INDEX idx_unique_active_position
ON monitoring.positions (symbol, exchange);
-- NO WHERE CLAUSE - всегда unique
```

#### Pros ✅
- Полностью предотвращает дубликаты
- Защищает на уровне БД (самый надежный)
- Простая реализация (1 SQL statement)

#### Cons ❌
- **BREAKING CHANGE**: Не позволит иметь closed позиции для того же символа
- Нужно изменить логику:
  - Либо использовать soft delete
  - Либо архивировать closed в другую таблицу
  - Либо добавить `closed_at IS NULL` в index
- Потребует миграцию существующих данных

#### Risk Assessment
- **Complexity:** 🟡 MEDIUM (нужна миграция)
- **Risk:** 🔴 HIGH (breaking change)
- **Effectiveness:** 🟢 100%
- **Performance:** 🟢 No impact (может быть лучше)

#### Recommendation
⚠️ **НЕ РЕКОМЕНДУЕТСЯ** как standalone solution
- Слишком breaking
- Требует изменений в других частях
- Можно использовать как part of larger refactoring

---

### Option 2: Change Unique Index (Conditional)
**Идея:** Изменить WHERE clause чтобы покрыть больше статусов

#### Implementation
```sql
-- File: database/migrations/008_fix_unique_index.sql
DROP INDEX IF EXISTS monitoring.idx_unique_active_position;

CREATE UNIQUE INDEX idx_unique_active_position
ON monitoring.positions (symbol, exchange)
WHERE status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry');
-- Covers all "open" states
```

#### Pros ✅
- Защищает все open states
- Не breaking для closed позиций
- Просто реализовать

#### Cons ❌
- Если добавятся новые intermediate статусы, нужно обновлять index
- Не защищает на этапе проверки (Problem #2)

#### Risk Assessment
- **Complexity:** 🟢 LOW
- **Risk:** 🟡 MEDIUM (index rebuild)
- **Effectiveness:** 🟢 95%
- **Performance:** 🟢 No impact

#### Recommendation
✅ **ХОРОШИЙ ВАРИАНТ** как defensive measure
- Можно комбинировать с другими options
- Low risk, high reward

---

### Option 3: Fix Check Logic in create_position()
**Идея:** Проверять ВСЕ open статусы, не только 'active'

#### Implementation
```python
# File: database/repository.py:267-270
existing = await conn.fetchrow("""
    SELECT id FROM monitoring.positions
    WHERE symbol = $1 AND exchange = $2
      AND status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')  -- ✅ FIX
""", symbol, exchange)

if existing:
    logger.warning(f"Position already exists for {symbol} on {exchange}: #{existing['id']}")
    return existing['id']  # Return existing instead of creating duplicate
```

#### Pros ✅
- **МИНИМАЛЬНОЕ изменение** (1 line!)
- Прямо решает Problem #2 и #6
- Не требует миграции БД
- Быстро реализовать и тестировать
- Легко откатить если проблемы

#### Cons ❌
- Не защищает если кто-то вызовет create напрямую с другой логикой
- Нужно дублировать fix в других местах (Sync)

#### Risk Assessment
- **Complexity:** 🟢 LOW (1 line change)
- **Risk:** 🟢 LOW (defensive, не breaking)
- **Effectiveness:** 🟢 90%
- **Performance:** 🟢 No impact

#### Recommendation
✅✅ **STRONGLY RECOMMENDED** as primary fix
- Surgical, minimal
- Follows "If it ain't broke, don't fix it"
- Can be deployed immediately

#### Detailed Changes Required

**1. Fix repository.py:create_position()**
```python
# File: database/repository.py
# Line: 267-270 (approximate)

# OLD:
existing = await conn.fetchrow("""
    SELECT id FROM monitoring.positions
    WHERE symbol = $1 AND exchange = $2 AND status = 'active'
""", symbol, exchange)

# NEW:
existing = await conn.fetchrow("""
    SELECT id, status FROM monitoring.positions
    WHERE symbol = $1 AND exchange = $2
      AND status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')
    ORDER BY created_at DESC
    LIMIT 1
""", symbol, exchange)

if existing:
    logger.warning(
        f"⚠️  Position already exists: {symbol} on {exchange}, "
        f"id={existing['id']}, status={existing['status']}. "
        f"Returning existing position instead of creating duplicate."
    )
    return existing['id']
```

**2. Fix position_manager.py:sync (if different method)**
Нужно найти точное место где Sync проверяет позицию.

---

### Option 4: Add Defensive Check Before Final UPDATE
**Идея:** Проверить перед final UPDATE что нет дубликата

#### Implementation
```python
# File: core/atomic_position_manager.py:417-420 (approximate)

# Before final UPDATE to 'active':
async def _safe_update_to_active(self, position_id: int, symbol: str, exchange: str, **kwargs):
    """Safely update position to active with duplicate check"""

    # Defensive check: is there already an active position?
    existing_active = await self.repository.conn.fetchrow("""
        SELECT id FROM monitoring.positions
        WHERE symbol = $1 AND exchange = $2 AND status = 'active'
          AND id != $3
    """, symbol, exchange, position_id)

    if existing_active:
        logger.error(
            f"🔴 DUPLICATE DETECTED: Cannot update position #{position_id} to active. "
            f"Position #{existing_active['id']} is already active for {symbol} on {exchange}. "
            f"Rolling back position #{position_id}."
        )
        # Trigger rollback instead of UPDATE
        await self._rollback_position(position_id, ...)
        return False

    # Safe to update
    await self.repository.update_position(position_id, status='active', **kwargs)
    return True
```

#### Pros ✅
- Catch-all safety net
- Предотвращает duplicate key error
- Graceful degradation (rollback instead of crash)

#### Cons ❌
- Добавляет extra DB query
- Не предотвращает race (только обнаруживает)
- Reactive, не proactive

#### Risk Assessment
- **Complexity:** 🟡 MEDIUM (новая функция)
- **Risk:** 🟢 LOW (defensive добавление)
- **Effectiveness:** 🟢 85% (обнаруживает, но не предотвращает)
- **Performance:** 🟡 Minor impact (1 extra query)

#### Recommendation
✅ **RECOMMENDED** as additional safety layer
- Комбинировать с Option 3
- Defense in depth

---

### Option 5: Keep Everything in One Transaction
**Идея:** Держать advisory lock от CREATE до final UPDATE

#### Implementation
```python
# File: core/atomic_position_manager.py or новый wrapper

async def open_position_atomic_safe(self, ...):
    """Atomic position opening with extended lock"""

    symbol, exchange = position_data['symbol'], position_data['exchange']
    lock_id = self.repository._get_position_lock_id(symbol, exchange)

    async with self.repository.pool.acquire() as conn:
        async with conn.transaction():
            # Acquire lock for ENTIRE operation
            await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)

            # All operations inside ONE transaction:
            # 1. Check + CREATE
            position_id = await self._create_in_transaction(conn, position_data)

            # 2. Place entry order (outside DB)
            entry_order = await exchange.create_market_order(...)

            # 3. UPDATE with entry order info (same TX)
            await conn.execute("""
                UPDATE monitoring.positions
                SET exchange_order_id = $1, updated_at = NOW()
                WHERE id = $2
            """, entry_order.id, position_id)

            # 4. Place SL order (outside DB)
            sl_order = await exchange.create_order(...)

            # 5. Final UPDATE to active (same TX)
            await conn.execute("""
                UPDATE monitoring.positions
                SET stop_loss_price = $1, has_stop_loss = true,
                    status = 'active', updated_at = NOW()
                WHERE id = $2
            """, sl_price, position_id)

            # Commit entire transaction
        # Lock released ONLY here
```

#### Pros ✅
- Полностью исключает race condition
- Advisory lock защищает весь flow
- Atomic на уровне БД

#### Cons ❌
- **MAJOR REFACTORING** - нужно переписать весь flow
- Длинная транзакция (3+ секунд)
- Блокирует другие threads дольше
- Exchange API calls внутри транзакции (плохая практика)
- Сложно тестировать
- Высокий риск deadlocks

#### Risk Assessment
- **Complexity:** 🔴 HIGH (major refactoring)
- **Risk:** 🔴 HIGH (breaking changes, deadlocks)
- **Effectiveness:** 🟢 100%
- **Performance:** 🔴 BAD (long locks)

#### Recommendation
❌ **НЕ РЕКОМЕНДУЕТСЯ**
- Too complex
- Too risky
- Нарушает best practices (external calls in TX)
- "If it ain't broke, don't fix it" violation

---

### Option 6 (Bonus): Optimistic Locking Pattern
**Идея:** Использовать version/timestamp для optimistic concurrency control

#### Implementation
```python
# Add version column to positions table
ALTER TABLE monitoring.positions ADD COLUMN version INTEGER DEFAULT 0;

# On UPDATE:
result = await conn.execute("""
    UPDATE monitoring.positions
    SET status = $1, version = version + 1, updated_at = NOW()
    WHERE id = $2 AND version = $3
    RETURNING id
""", new_status, position_id, current_version)

if not result:
    # Version mismatch - concurrent modification detected
    raise ConcurrentModificationError()
```

#### Pros ✅
- Обнаруживает concurrent modifications
- Standard pattern
- No locks needed

#### Cons ❌
- Требует schema change
- Не предотвращает duplicate CREATE
- Только для UPDATEs

#### Recommendation
⚠️ **OPTIONAL** for future enhancement
- Not directly solving our problem
- Good for UPDATE conflicts

---

## 📊 СРАВНЕНИЕ ВАРИАНТОВ

### Comparison Matrix

| Option | Complexity | Risk | Effectiveness | Performance | Time to Implement |
|--------|------------|------|---------------|-------------|-------------------|
| **1. Full Index** | 🟡 MEDIUM | 🔴 HIGH | 🟢 100% | 🟢 Good | 4-8 hours |
| **2. Conditional Index** | 🟢 LOW | 🟡 MEDIUM | 🟢 95% | 🟢 Good | 1-2 hours |
| **3. Fix Check Logic** | 🟢 LOW | 🟢 LOW | 🟢 90% | 🟢 Good | 1-2 hours |
| **4. Defensive Check** | 🟡 MEDIUM | 🟢 LOW | 🟢 85% | 🟡 OK | 2-3 hours |
| **5. One Transaction** | 🔴 HIGH | 🔴 HIGH | 🟢 100% | 🔴 BAD | 8+ hours |
| **6. Optimistic Lock** | 🟡 MEDIUM | 🟡 MEDIUM | 🟡 60% | 🟢 Good | 4-6 hours |

### Scoring System

**Overall Score = (Effectiveness × 0.4) + (Safety × 0.3) + (Simplicity × 0.2) + (Performance × 0.1)**

```
Option 1: (100 × 0.4) + (60 × 0.3) + (60 × 0.2) + (90 × 0.1) = 79 points
Option 2: (95 × 0.4) + (70 × 0.3) + (90 × 0.2) + (90 × 0.1) = 84 points ⭐
Option 3: (90 × 0.4) + (90 × 0.3) + (95 × 0.2) + (90 × 0.1) = 91 points ⭐⭐⭐
Option 4: (85 × 0.4) + (90 × 0.3) + (70 × 0.2) + (80 × 0.1) = 83 points ⭐
Option 5: (100 × 0.4) + (50 × 0.3) + (30 × 0.2) + (40 × 0.1) = 65 points
Option 6: (60 × 0.4) + (70 × 0.3) + (60 × 0.2) + (90 × 0.1) = 66 points
```

**Winner: Option 3 (Fix Check Logic) - 91 points**

---

## ✅ РЕКОМЕНДУЕМЫЙ ПОДХОД

### Primary Recommendation: **Option 3 + Option 2 + Option 4**

Комбинированный подход из трех layers:

#### Layer 1: Fix Check Logic (Option 3) - PRIMARY
```python
# database/repository.py:create_position()
existing = await conn.fetchrow("""
    SELECT id, status FROM monitoring.positions
    WHERE symbol = $1 AND exchange = $2
      AND status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')
    ORDER BY created_at DESC
    LIMIT 1
""", symbol, exchange)

if existing:
    logger.warning(f"Position exists: {symbol}, status={existing['status']}, returning #{existing['id']}")
    return existing['id']
```

**Why:** Минимальное изменение, максимальный эффект

#### Layer 2: Fix Unique Index (Option 2) - DEFENSIVE
```sql
-- database/migrations/008_fix_unique_index.sql
DROP INDEX IF EXISTS monitoring.idx_unique_active_position;

CREATE UNIQUE INDEX idx_unique_active_position
ON monitoring.positions (symbol, exchange)
WHERE status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry');
```

**Why:** Database-level protection

#### Layer 3: Defensive Check (Option 4) - SAFETY NET
```python
# core/atomic_position_manager.py - перед final UPDATE
async def _safe_activate_position(self, position_id, symbol, exchange, **kwargs):
    # Check for existing active
    existing = await self.repository.get_active_position(symbol, exchange, exclude_id=position_id)
    if existing:
        logger.error(f"Duplicate active position detected, rolling back #{position_id}")
        await self._rollback_position(...)
        return False

    # Safe to activate
    await self.repository.update_position(position_id, status='active', **kwargs)
    return True
```

**Why:** Catch-all если Layers 1&2 не сработали

---

## 📝 ДЕТАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ

### Phase 1: Preparation (30 min)
1. ✅ Create git branch: `fix/duplicate-position-race-condition`
2. ✅ Backup production DB
3. ✅ Review Phase 3 findings
4. ✅ Prepare test cases

### Phase 2: Layer 1 Implementation (1 hour)
**File:** `database/repository.py`

```python
# BEFORE:
async def create_position(self, position_data: Dict) -> int:
    # ...
    existing = await conn.fetchrow("""
        SELECT id FROM monitoring.positions
        WHERE symbol = $1 AND exchange = $2 AND status = 'active'
    """, symbol, exchange)
    # ...

# AFTER:
async def create_position(self, position_data: Dict) -> int:
    # ...
    # FIX: Check ALL open statuses, not just 'active'
    existing = await conn.fetchrow("""
        SELECT id, status, created_at FROM monitoring.positions
        WHERE symbol = $1 AND exchange = $2
          AND status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')
        ORDER BY created_at DESC
        LIMIT 1
    """, symbol, exchange)

    if existing:
        logger.warning(
            f"⚠️  Position already exists for {symbol} on {exchange}: "
            f"id={existing['id']}, status={existing['status']}, "
            f"created_at={existing['created_at']}. "
            f"Returning existing position to prevent duplicate."
        )
        return existing['id']
    # ... продолжение CREATE
```

**Testing:**
```python
# Test case: Create position, then try to create again while status='entry_placed'
position_id_1 = await repository.create_position({...})
await repository.update_position(position_id_1, status='entry_placed')
position_id_2 = await repository.create_position({...})  # Should return position_id_1
assert position_id_1 == position_id_2
```

### Phase 3: Layer 2 Implementation (30 min)
**File:** `database/migrations/008_fix_unique_index.sql`

```sql
-- Migration: Fix unique index to cover all open positions
-- Date: 2025-10-23
-- Issue: Duplicate position race condition

BEGIN;

-- Drop old partial index
DROP INDEX IF EXISTS monitoring.idx_unique_active_position;

-- Create new partial index covering all "open" statuses
CREATE UNIQUE INDEX idx_unique_active_position
ON monitoring.positions (symbol, exchange)
WHERE status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry');

-- Verify no existing violations
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT symbol, exchange, COUNT(*) as cnt
        FROM monitoring.positions
        WHERE status IN ('active', 'entry_placed', 'pending_sl', 'pending_entry')
        GROUP BY symbol, exchange
        HAVING COUNT(*) > 1
    ) violations;

    IF violation_count > 0 THEN
        RAISE EXCEPTION 'Cannot create index: % existing violations found', violation_count;
    END IF;
END $$;

COMMIT;
```

**Migration application:**
```bash
# Apply migration
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -f database/migrations/008_fix_unique_index.sql

# Verify index
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -c "
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'positions' AND indexname LIKE '%unique%';
"
```

### Phase 4: Layer 3 Implementation (1.5 hours)
**File:** `core/atomic_position_manager.py`

```python
# Add new method for safe activation
async def _safe_activate_position(
    self,
    position_id: int,
    symbol: str,
    exchange: str,
    **update_fields
) -> bool:
    """
    Safely activate position with duplicate detection.

    Returns:
        True if activated successfully
        False if duplicate detected (triggers rollback)
    """
    try:
        # Defensive check: is there already an active position?
        async with self.repository.pool.acquire() as conn:
            existing_active = await conn.fetchrow("""
                SELECT id, created_at FROM monitoring.positions
                WHERE symbol = $1 AND exchange = $2
                  AND status = 'active'
                  AND id != $3
            """, symbol, exchange, position_id)

            if existing_active:
                logger.error(
                    f"🔴 DUPLICATE ACTIVE POSITION DETECTED!\n"
                    f"   Cannot activate position #{position_id} ({symbol} on {exchange}).\n"
                    f"   Position #{existing_active['id']} is already active "
                    f"(created {existing_active['created_at']}).\n"
                    f"   This position will be rolled back to prevent data corruption."
                )
                return False

        # Safe to activate
        update_fields['status'] = PositionState.ACTIVE.value
        await self.repository.update_position(position_id, **update_fields)

        logger.info(f"✅ Position #{position_id} successfully activated")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to activate position #{position_id}: {e}")
        return False

# Modify open_position_atomic to use safe activation:
async def open_position_atomic(self, position_data: Dict, exchange_name: str) -> Dict:
    # ... existing code до final UPDATE ...

    # OLD:
    # await self.repository.update_position(position_id, **{
    #     'status': PositionState.ACTIVE.value,
    #     'stop_loss_price': sl_price,
    #     'has_stop_loss': True
    # })

    # NEW:
    activation_successful = await self._safe_activate_position(
        position_id=position_id,
        symbol=symbol,
        exchange=exchange_name,
        stop_loss_price=sl_price,
        has_stop_loss=True
    )

    if not activation_successful:
        # Duplicate detected - trigger rollback
        logger.critical(
            f"⚠️  CRITICAL: Duplicate position detected during activation. "
            f"Rolling back position #{position_id}."
        )
        await self._rollback_position(
            position_id, entry_order, symbol, exchange_name,
            PositionState.PENDING_SL, quantity,
            "duplicate active position detected"
        )
        raise RuntimeError(f"Duplicate position prevented: {symbol} on {exchange_name}")

    # ... остальной код ...
```

### Phase 5: Testing (2 hours)

#### Test 1: Unit Test для Layer 1
```python
# tests/test_duplicate_position_fix.py
import pytest
import asyncio

class TestDuplicatePositionFix:

    @pytest.mark.asyncio
    async def test_create_returns_existing_when_intermediate_state(self, repository):
        """Test that create_position returns existing ID when position in intermediate state"""

        # Create first position
        position_data = {
            'symbol': 'TESTUSDT',
            'exchange': 'binance',
            'side': 'LONG',
            'quantity': 100,
            'entry_price': 1.0
        }

        position_id_1 = await repository.create_position(position_data)
        assert position_id_1 is not None

        # Simulate intermediate state
        await repository.update_position(position_id_1, status='entry_placed')

        # Try to create again - should return existing
        position_id_2 = await repository.create_position(position_data)

        assert position_id_1 == position_id_2, "Should return existing position ID"

        # Verify only ONE position exists
        positions = await repository.conn.fetch("""
            SELECT id FROM monitoring.positions
            WHERE symbol = 'TESTUSDT' AND exchange = 'binance'
        """)
        assert len(positions) == 1
```

#### Test 2: Integration Test для Race Condition
```python
@pytest.mark.asyncio
async def test_race_condition_signal_sync(self, position_manager, repository):
    """Simulate Scenario B: Signal + Sync race condition"""

    symbol = 'RACEUSDT'
    exchange = 'binance'

    async def signal_flow():
        """Simulates Signal thread"""
        await asyncio.sleep(0.1)  # Small delay
        position_data = {...}
        result = await position_manager.open_position_atomic(position_data, exchange)
        return result

    async def sync_flow():
        """Simulates Sync thread"""
        await asyncio.sleep(0.5)  # Wake up during Signal's sleep
        # Try to create same position
        position_data = {...}
        position_id = await repository.create_position(position_data)
        return position_id

    # Run both concurrently
    results = await asyncio.gather(signal_flow(), sync_flow(), return_exceptions=True)

    # Verify: should have only ONE position
    positions = await repository.conn.fetch("""
        SELECT id FROM monitoring.positions
        WHERE symbol = $1 AND exchange = $2
    """, symbol, exchange)

    assert len(positions) == 1, "Should have exactly ONE position (no duplicate)"
```

#### Test 3: Stress Test
```python
@pytest.mark.asyncio
async def test_stress_concurrent_creates(self, repository):
    """Stress test: many concurrent create attempts"""

    symbol = 'STRESSUSDT'
    exchange = 'binance'
    num_threads = 10

    async def create_attempt(i):
        position_data = {
            'symbol': symbol,
            'exchange': exchange,
            'side': 'LONG',
            'quantity': 100 + i,  # Slightly different
            'entry_price': 1.0 + i * 0.01
        }
        return await repository.create_position(position_data)

    # Launch 10 concurrent creates
    results = await asyncio.gather(*[create_attempt(i) for i in range(num_threads)])

    # All should return SAME position_id
    assert len(set(results)) == 1, "All creates should return same position ID"

    # Verify: only ONE position in DB
    positions = await repository.conn.fetch("""
        SELECT id FROM monitoring.positions
        WHERE symbol = $1 AND exchange = $2
    """, symbol, exchange)

    assert len(positions) == 1, "Should have exactly ONE position"
```

### Phase 6: Deployment (1 hour)

#### Pre-deployment Checklist
- [ ] All tests pass (unit + integration + stress)
- [ ] Code review completed
- [ ] Migration tested on staging DB
- [ ] Backup created
- [ ] Rollback plan ready
- [ ] Monitoring dashboard ready

#### Deployment Steps
```bash
# 1. Stop bot gracefully
pkill -SIGTERM trading_bot  # Graceful shutdown

# 2. Backup DB
pg_dump -h localhost -p 5432 -U evgeniyyanvarskiy fox_crypto > backup_pre_fix_$(date +%Y%m%d_%H%M%S).sql

# 3. Apply migration
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto -f database/migrations/008_fix_unique_index.sql

# 4. Deploy new code
git checkout fix/duplicate-position-race-condition
git pull

# 5. Restart bot
python main.py

# 6. Monitor logs for 15 minutes
tail -f logs/trading_bot.log | grep -E "(DUPLICATE|Position.*exists|⚠️)"
```

#### Monitoring После Deploy
```sql
-- Query 1: Check for any duplicate errors
SELECT * FROM monitoring.positions
WHERE status = 'rolled_back'
  AND exit_reason LIKE '%duplicate%'
  AND created_at > NOW() - INTERVAL '1 hour';

-- Query 2: Check for concurrent creations
SELECT
    p1.symbol, p1.id as id1, p2.id as id2,
    EXTRACT(EPOCH FROM (p2.created_at - p1.created_at)) as seconds_between
FROM monitoring.positions p1
JOIN monitoring.positions p2 ON
    p1.symbol = p2.symbol AND p1.exchange = p2.exchange AND p1.id < p2.id
WHERE p1.created_at > NOW() - INTERVAL '1 hour'
  AND EXTRACT(EPOCH FROM (p2.created_at - p1.created_at)) < 10;

-- Query 3: Check positions in intermediate states
SELECT symbol, exchange, status,
       EXTRACT(EPOCH FROM (NOW() - created_at)) / 60 as age_minutes
FROM monitoring.positions
WHERE status IN ('entry_placed', 'pending_sl', 'pending_entry')
ORDER BY created_at DESC;
```

### Phase 7: Rollback Plan (if needed)

#### Rollback Triggers
- Duplicate errors continue after fix
- New unexpected errors
- Performance degradation
- Tests fail in production

#### Rollback Steps
```bash
# 1. Stop bot
pkill -SIGTERM trading_bot

# 2. Revert code
git checkout main
git pull

# 3. Revert migration
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto <<EOF
BEGIN;
DROP INDEX IF EXISTS monitoring.idx_unique_active_position;
CREATE UNIQUE INDEX idx_unique_active_position
ON monitoring.positions (symbol, exchange)
WHERE status = 'active';
COMMIT;
EOF

# 4. Restore DB from backup (if needed)
psql -h localhost -p 5432 -U evgeniyyanvarskiy -d fox_crypto < backup_pre_fix_YYYYMMDD_HHMMSS.sql

# 5. Restart
python main.py
```

---

## 🎯 SUCCESS CRITERIA

### Immediate (Post-deployment)
- [ ] No duplicate key violations in logs (first 24h)
- [ ] No new rolled_back with "duplicate" reason
- [ ] All positions have valid states
- [ ] No performance degradation

### Short-term (Week 1)
- [ ] Zero duplicate errors
- [ ] Rolled_back rate < 5% (down from 10%)
- [ ] Position creation time unchanged
- [ ] No orphaned positions

### Long-term (Month 1)
- [ ] Sustained zero duplicates
- [ ] System stability maintained
- [ ] No side effects discovered
- [ ] Code review positive

---

## 📊 RISK MITIGATION

### Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Fix doesn't work | LOW | HIGH | Layer 2&3 as backup |
| New bugs introduced | LOW | MEDIUM | Comprehensive tests |
| Performance hit | VERY LOW | LOW | Minimal code changes |
| Migration fails | VERY LOW | HIGH | Test on staging first |
| Rollback needed | LOW | MEDIUM | Clear rollback plan |

### Contingency Plans

**If duplicate errors continue:**
1. Check logs for new error patterns
2. Run diagnostic tools from Phase 2
3. Verify all layers deployed correctly
4. Consider Option 5 (full transaction) if critical

**If performance degrades:**
1. Check query plan for new check
2. Add index if needed
3. Optimize query (use LIMIT 1)

**If unexpected side effects:**
1. Immediate rollback
2. Detailed analysis
3. Adjust fix
4. Redeploy

---

## ✅ ЗАКЛЮЧЕНИЕ ФАЗЫ 4

### Summary

**Рекомендуемый подход:** 3-layer defense
1. **Layer 1:** Fix check logic (Option 3) - PRIMARY
2. **Layer 2:** Fix unique index (Option 2) - DEFENSIVE
3. **Layer 3:** Safe activation (Option 4) - SAFETY NET

**Characteristics:**
- ✅ Минимальные изменения
- ✅ Низкий риск
- ✅ Высокая эффективность (90-95%)
- ✅ Быстрая реализация (3-4 часа)
- ✅ Легко тестировать
- ✅ Легко откатить

**Timeline:**
```
Preparation:    30 min
Layer 1:        1 hour
Layer 2:        30 min
Layer 3:        1.5 hours
Testing:        2 hours
Deployment:     1 hour
───────────────────────
Total:          6.5 hours
```

**Expected Outcome:**
- 🎯 Zero duplicate errors
- 🎯 Rolled_back rate < 5%
- 🎯 No performance impact
- 🎯 System more robust

### Next Steps

1. ✅ Review this plan with stakeholders
2. ⏳ Get approval to proceed
3. ⏳ Create git branch
4. ⏳ Implement Layer 1
5. ⏳ Implement Layer 2
6. ⏳ Implement Layer 3
7. ⏳ Run tests
8. ⏳ Deploy to production
9. ⏳ Monitor for 24h
10. ⏳ Mark as RESOLVED

---

**ФАЗА 4 ЗАВЕРШЕНА ✅**
**СТАТУС: READY FOR IMPLEMENTATION**
**CONFIDENCE: HIGH (90%)**
**RISK: LOW**

