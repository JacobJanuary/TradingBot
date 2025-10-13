# ДЕТАЛЬНЫЙ ПЛАН БЕЗОПАСНОЙ РЕАЛИЗАЦИИ: Очистка fas.signals (Вариант 2)

**Дата создания:** 2025-10-14
**Статус:** 🔍 RESEARCH COMPLETE - IMPLEMENTATION PLAN READY
**Ветка:** `fix/sl-manager-conflicts` → новая ветка `cleanup/remove-fas-signals`
**Приоритет:** 🟡 СРЕДНИЙ (не критично, но улучшает кодовую базу)

**⚠️ КРИТИЧЕСКИ ВАЖНО: ЭТОТ ДОКУМЕНТ - ТОЛЬКО ПЛАН! БЕЗ ИЗМЕНЕНИЯ КОДА!**

---

## EXECUTIVE SUMMARY

### Что будем делать?

**ПОЛНАЯ ОЧИСТКА** устаревшей таблицы `fas.signals` и модели `Signal`:
1. Удалить класс `Signal` из `database/models.py`
2. Изменить тип `signal_id` с `INTEGER` на `VARCHAR(100)` в БД
3. Исправить тесты (заменить `Signal()` на словари)
4. Обновить комментарии и документацию
5. Дропнуть FK constraints если они существуют в БД

### Почему безопасно?

✅ **Production код НЕ использует** Signal model
✅ **Сигналы приходят через WebSocket**, не из БД
✅ FK constraints **закомментированы** в коде
✅ FK constraints **не созданы** в БД (проверено в init.sql)
✅ **Нет запросов** к fas.signals в коде

### Риски

🟡 **СРЕДНИЙ РИСК:**
- Тесты упадут (4 теста в 2 файлах)
- Нужна миграция БД
- Нужен rollback plan

🟢 **НИЗКИЙ РИСК для production:**
- Production код не затронут
- Нет downtime при миграции
- Можно откатить изменения

### Оценка трудозатрат

| Этап | Время | Сложность |
|------|-------|-----------|
| Pre-flight checks | 10 мин | Легко |
| Создание бэкапа БД | 5 мин | Легко |
| Миграция БД | 10 мин | Средне |
| Изменение кода | 20 мин | Легко |
| Исправление тестов | 15 мин | Легко |
| Запуск тестов | 10 мин | Легко |
| Документация | 10 мин | Легко |
| **ИТОГО** | **80 мин** | **🟡 Средне** |

---

## ПРЕДВАРИТЕЛЬНЫЕ УСЛОВИЯ (Pre-flight Checks)

### ✅ Checklist ПЕРЕД началом

Выполнить ВСЕ проверки перед началом работ:

```bash
# 1. Проверка текущей ветки
git branch --show-current
# Ожидается: fix/sl-manager-conflicts

# 2. Проверка статуса git (должен быть clean)
git status
# Ожидается: "nothing to commit, working tree clean"

# 3. Проверка подключения к БД
psql -h <host> -U <user> -d <database> -c "SELECT 1;"
# Ожидается: успешное подключение

# 4. Проверка таблицы fas.signals существует
psql -h <host> -U <user> -d <database> -c "SELECT COUNT(*) FROM fas.scoring_history;"
# Ожидается: число (может быть 0)

# 5. Проверка signal_id в production tables
psql -h <host> -U <user> -d <database> -c "
SELECT
    (SELECT COUNT(*) FROM monitoring.positions WHERE signal_id IS NOT NULL) as positions_count,
    (SELECT COUNT(*) FROM monitoring.trades WHERE signal_id IS NOT NULL) as trades_count;
"
# Запомнить результат для rollback

# 6. Проверка FK constraints
psql -h <host> -U <user> -d <database> -c "
SELECT
    conname AS constraint_name,
    conrelid::regclass AS table_name,
    confrelid::regclass AS referenced_table
FROM pg_constraint
WHERE confrelid = 'fas.scoring_history'::regclass
   OR confrelid IN (SELECT oid FROM pg_class WHERE relname = 'signals' AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'fas'));
"
# Ожидается: пустой результат (нет FK)

# 7. Проверка тестов проходят СЕЙЧАС (до изменений)
pytest tests/conftest.py -v
pytest tests/integration/test_trading_flow.py -v
# Запомнить результаты

# 8. Проверка версий зависимостей
pip list | grep -E "sqlalchemy|alembic|asyncpg"
# Запомнить версии

# 9. Проверка доступного места на диске (для бэкапа)
df -h | grep -E "/$|/var"
# Нужно минимум 500MB свободного места

# 10. Проверка прав доступа к БД
psql -h <host> -U <user> -d <database> -c "
SELECT
    has_schema_privilege('fas', 'USAGE') as fas_usage,
    has_schema_privilege('monitoring', 'USAGE') as monitoring_usage,
    has_table_privilege('fas.scoring_history', 'SELECT') as fas_select,
    has_table_privilege('monitoring.positions', 'UPDATE') as positions_update;
"
# Все должны быть true
```

**❌ STOP! Если хотя бы одна проверка не прошла - НЕ ПРОДОЛЖАТЬ!**

---

## ЭТАП 1: СОЗДАНИЕ BACKUP И SAFETY NET

### 1.1 Создание backup базы данных

```bash
# Создать директорию для backup
mkdir -p ./backups/fas_cleanup_$(date +%Y%m%d_%H%M%S)
cd ./backups/fas_cleanup_$(date +%Y%m%d_%H%M%S)

# Backup только нужных схем
pg_dump -h <host> -U <user> -d <database> \
    --schema=fas \
    --schema=monitoring \
    --format=custom \
    --file=pre_cleanup_backup.dump

# Backup в SQL формате (для ручного просмотра)
pg_dump -h <host> -U <user> -d <database> \
    --schema=fas \
    --schema=monitoring \
    --format=plain \
    --file=pre_cleanup_backup.sql

# Проверить backup создан
ls -lh *.dump *.sql

# Создать snapshot текущих данных signal_id
psql -h <host> -U <user> -d <database> -c "
COPY (
    SELECT 'positions' as source, id, signal_id, symbol, created_at
    FROM monitoring.positions
    WHERE signal_id IS NOT NULL
    UNION ALL
    SELECT 'trades' as source, id, signal_id, symbol, executed_at as created_at
    FROM monitoring.trades
    WHERE signal_id IS NOT NULL
) TO STDOUT WITH CSV HEADER
" > signal_id_snapshot.csv

# Verify snapshot
wc -l signal_id_snapshot.csv
head -5 signal_id_snapshot.csv
```

**✅ Checkpoint:** Backup файлы созданы, размер > 0 bytes

### 1.2 Создание новой git ветки

```bash
# Вернуться в корень проекта
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Создать новую ветку от текущей
git checkout -b cleanup/remove-fas-signals

# Проверить ветка создана
git branch --show-current
# Ожидается: cleanup/remove-fas-signals
```

**✅ Checkpoint:** Новая ветка создана, можно работать

### 1.3 Создание тестовой копии БД (optional, но рекомендуется)

```bash
# Создать test database
psql -h <host> -U <user> -d postgres -c "
CREATE DATABASE trading_test_cleanup
WITH TEMPLATE <original_database>;
"

# Проверить создана
psql -h <host> -U <user> -d trading_test_cleanup -c "SELECT COUNT(*) FROM monitoring.positions;"
```

**✅ Checkpoint:** Test database создана (если выбрали этот путь)

---

## ЭТАП 2: МИГРАЦИЯ БАЗЫ ДАННЫХ

### 2.1 Создание файла миграции

**Файл:** `database/migrations/003_cleanup_fas_signals.sql`

**Содержание:**

```sql
-- Migration: Cleanup fas.signals legacy table
-- Date: 2025-10-14
-- Description: Remove fas.signals dependencies and fix signal_id type mismatch
-- Issue: signal_id column is INTEGER but code passes string 'unknown'
--
-- ВАЖНО: Этот файл создается вручную ПЕРЕД запуском миграции!
--
-- Estimated duration: ~10 seconds
-- Risk level: MEDIUM (changes data type, affects indexes)
-- Rollback: Available in migration file comments

-- ==============================================================================
-- PHASE 1: PRE-FLIGHT CHECKS
-- ==============================================================================

DO $$
DECLARE
    positions_count INTEGER;
    trades_count INTEGER;
BEGIN
    -- Check current data
    SELECT COUNT(*) INTO positions_count
    FROM monitoring.positions
    WHERE signal_id IS NOT NULL;

    SELECT COUNT(*) INTO trades_count
    FROM monitoring.trades
    WHERE signal_id IS NOT NULL;

    RAISE NOTICE 'Pre-migration data: positions=%, trades=%', positions_count, trades_count;

    -- Check for FK constraints (should be none)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'monitoring'
        AND table_name IN ('positions', 'trades')
        AND constraint_type = 'FOREIGN KEY'
        AND constraint_name LIKE '%signal%'
    ) THEN
        RAISE EXCEPTION 'FK constraints found! Check before proceeding.';
    END IF;

    RAISE NOTICE 'Pre-flight checks passed';
END $$;

-- ==============================================================================
-- PHASE 2: BACKUP CURRENT DATA (inside transaction)
-- ==============================================================================

-- Create temporary backup table
CREATE TEMP TABLE signal_id_backup AS
SELECT
    'positions' as source_table,
    id,
    signal_id,
    symbol,
    created_at
FROM monitoring.positions
WHERE signal_id IS NOT NULL

UNION ALL

SELECT
    'trades' as source_table,
    id,
    signal_id,
    symbol,
    executed_at as created_at
FROM monitoring.trades
WHERE signal_id IS NOT NULL;

-- Verify backup
DO $$
DECLARE
    backup_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO backup_count FROM signal_id_backup;
    RAISE NOTICE 'Backed up % rows', backup_count;
END $$;

-- ==============================================================================
-- PHASE 3: ALTER COLUMN TYPES
-- ==============================================================================

-- Step 1: Drop existing FK constraints (if any)
-- NOTE: Should be none based on init.sql, but check anyway
DO $$
DECLARE
    fk_name TEXT;
BEGIN
    -- Check positions table
    FOR fk_name IN
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'monitoring'
        AND table_name = 'positions'
        AND constraint_type = 'FOREIGN KEY'
        AND constraint_name LIKE '%signal%'
    LOOP
        EXECUTE format('ALTER TABLE monitoring.positions DROP CONSTRAINT %I', fk_name);
        RAISE NOTICE 'Dropped FK constraint: %', fk_name;
    END LOOP;

    -- Check trades table
    FOR fk_name IN
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'monitoring'
        AND table_name = 'trades'
        AND constraint_type = 'FOREIGN KEY'
        AND constraint_name LIKE '%signal%'
    LOOP
        EXECUTE format('ALTER TABLE monitoring.trades DROP CONSTRAINT %I', fk_name);
        RAISE NOTICE 'Dropped FK constraint: %', fk_name;
    END LOOP;
END $$;

-- Step 2: Change signal_id type from INTEGER to VARCHAR(100)
-- monitoring.positions
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE VARCHAR(100)
USING signal_id::VARCHAR;

-- monitoring.trades
ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE VARCHAR(100)
USING signal_id::VARCHAR;

-- Verify type changed
DO $$
DECLARE
    pos_type TEXT;
    trades_type TEXT;
BEGIN
    SELECT data_type INTO pos_type
    FROM information_schema.columns
    WHERE table_schema = 'monitoring'
    AND table_name = 'positions'
    AND column_name = 'signal_id';

    SELECT data_type INTO trades_type
    FROM information_schema.columns
    WHERE table_schema = 'monitoring'
    AND table_name = 'trades'
    AND column_name = 'signal_id';

    IF pos_type != 'character varying' OR trades_type != 'character varying' THEN
        RAISE EXCEPTION 'Type change failed! pos_type=%, trades_type=%', pos_type, trades_type;
    END IF;

    RAISE NOTICE 'Types changed successfully: positions=%, trades=%', pos_type, trades_type;
END $$;

-- ==============================================================================
-- PHASE 4: UPDATE COMMENTS
-- ==============================================================================

COMMENT ON COLUMN monitoring.positions.signal_id IS
'WebSocket message ID (NOT a FK to fas.signals!) - can be integer, string, or NULL.
Legacy field kept for audit trail.';

COMMENT ON COLUMN monitoring.trades.signal_id IS
'WebSocket message ID (NOT a FK to fas.signals!) - can be integer, string, or NULL.
Legacy field kept for audit trail.';

-- ==============================================================================
-- PHASE 5: VERIFY DATA INTEGRITY
-- ==============================================================================

DO $$
DECLARE
    positions_after INTEGER;
    trades_after INTEGER;
    positions_before INTEGER;
    trades_before INTEGER;
BEGIN
    -- Count after migration
    SELECT COUNT(*) INTO positions_after
    FROM monitoring.positions
    WHERE signal_id IS NOT NULL;

    SELECT COUNT(*) INTO trades_after
    FROM monitoring.trades
    WHERE signal_id IS NOT NULL;

    -- Count from backup
    SELECT COUNT(*) INTO positions_before
    FROM signal_id_backup
    WHERE source_table = 'positions';

    SELECT COUNT(*) INTO trades_before
    FROM signal_id_backup
    WHERE source_table = 'trades';

    -- Verify no data lost
    IF positions_after != positions_before OR trades_after != trades_before THEN
        RAISE EXCEPTION 'Data loss detected! Before: pos=%, trades=%, After: pos=%, trades=%',
            positions_before, trades_before, positions_after, trades_after;
    END IF;

    RAISE NOTICE 'Data integrity verified: positions=%, trades=%', positions_after, trades_after;
END $$;

-- ==============================================================================
-- PHASE 6: MIGRATION COMPLETE
-- ==============================================================================

-- Log migration
INSERT INTO monitoring.risk_events (event_type, risk_level, details)
VALUES (
    'database_migration',
    'info',
    json_build_object(
        'migration', '003_cleanup_fas_signals',
        'date', NOW(),
        'changes', json_build_array(
            'Changed signal_id type from INTEGER to VARCHAR(100)',
            'Removed FK constraints to fas.signals (if any)',
            'Added column comments'
        )
    )::jsonb
);

RAISE NOTICE '✅ Migration 003_cleanup_fas_signals completed successfully';

-- ==============================================================================
-- ROLLBACK SCRIPT (run separately if needed)
-- ==============================================================================
/*
-- ROLLBACK: Revert signal_id back to INTEGER
-- WARNING: This will fail if signal_id contains non-numeric values!

BEGIN;

-- Step 1: Check for non-numeric values
DO $$
DECLARE
    non_numeric_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO non_numeric_count
    FROM monitoring.positions
    WHERE signal_id IS NOT NULL
    AND signal_id !~ '^\d+$';

    IF non_numeric_count > 0 THEN
        RAISE EXCEPTION 'Cannot rollback: % positions have non-numeric signal_id', non_numeric_count;
    END IF;
END $$;

-- Step 2: Revert type
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE INTEGER
USING CASE
    WHEN signal_id ~ '^\d+$' THEN signal_id::INTEGER
    ELSE NULL
END;

ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE INTEGER
USING CASE
    WHEN signal_id ~ '^\d+$' THEN signal_id::INTEGER
    ELSE NULL
END;

-- Step 3: Log rollback
INSERT INTO monitoring.risk_events (event_type, risk_level, details)
VALUES (
    'database_migration_rollback',
    'warning',
    json_build_object(
        'migration', '003_cleanup_fas_signals',
        'date', NOW(),
        'action', 'ROLLED BACK'
    )::jsonb
);

COMMIT;

RAISE NOTICE 'Rollback completed';
*/
```

**✅ Checkpoint:** Файл миграции создан и сохранен

### 2.2 Запуск миграции (ТОЛЬКО ПОСЛЕ BACKUP!)

```bash
# Проверить backup существует
ls -lh ./backups/fas_cleanup_*/

# OPTION 1: Запуск на test database (РЕКОМЕНДУЕТСЯ СНАЧАЛА)
psql -h <host> -U <user> -d trading_test_cleanup \
    -f database/migrations/003_cleanup_fas_signals.sql \
    -v ON_ERROR_STOP=1 \
    --echo-all

# Проверить результат на test DB
psql -h <host> -U <user> -d trading_test_cleanup -c "
SELECT
    table_name,
    column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'monitoring'
AND table_name IN ('positions', 'trades')
AND column_name = 'signal_id';
"
# Ожидается: data_type = 'character varying', length = 100

# Если test прошел успешно - запустить на production DB
# OPTION 2: Запуск на production database
psql -h <host> -U <user> -d <production_database> \
    -f database/migrations/003_cleanup_fas_signals.sql \
    -v ON_ERROR_STOP=1 \
    --echo-all \
    2>&1 | tee migration_003_output.log

# Проверить логи
grep -E "ERROR|EXCEPTION|✅" migration_003_output.log
```

**✅ Checkpoint:** Миграция выполнена, ошибок нет, data integrity verified

### 2.3 Post-migration verification

```bash
# 1. Проверить типы колонок
psql -h <host> -U <user> -d <database> -c "
SELECT
    table_name,
    column_name,
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'monitoring'
AND table_name IN ('positions', 'trades')
AND column_name = 'signal_id'
ORDER BY table_name;
"

# 2. Проверить данные не потеряны
psql -h <host> -U <user> -d <database> -c "
SELECT
    (SELECT COUNT(*) FROM monitoring.positions WHERE signal_id IS NOT NULL) as positions_count,
    (SELECT COUNT(*) FROM monitoring.trades WHERE signal_id IS NOT NULL) as trades_count;
"
# Сравнить с snapshot из pre-flight checks

# 3. Проверить нет FK constraints
psql -h <host> -U <user> -d <database> -c "
SELECT
    conname AS constraint_name,
    conrelid::regclass AS table_name,
    confrelid::regclass AS referenced_table
FROM pg_constraint
WHERE confrelid::regclass::text LIKE '%fas%';
"
# Ожидается: 0 rows

# 4. Проверить комментарии добавлены
psql -h <host> -U <user> -d <database> -c "
SELECT
    pgd.description
FROM pg_catalog.pg_statio_all_tables as st
INNER JOIN pg_catalog.pg_description pgd ON (pgd.objoid=st.relid)
INNER JOIN information_schema.columns c ON (
    pgd.objsubid=c.ordinal_position AND
    c.table_schema=st.schemaname AND
    c.table_name=st.relname
)
WHERE c.table_schema = 'monitoring'
AND c.column_name = 'signal_id';
"
```

**✅ Checkpoint:** Все проверки пройдены, БД в новом состоянии

---

## ЭТАП 3: ИЗМЕНЕНИЕ КОДА

**⚠️ ВНИМАНИЕ: Делаем изменения ТОЛЬКО в git ветке cleanup/remove-fas-signals!**

### 3.1 Удалить класс Signal из models.py

**Файл:** `database/models.py`

**Действие:** Удалить строки 36-69 (класс Signal)

**BEFORE:**
```python
class PositionStatus(enum.Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class Signal(Base):  # ← УДАЛИТЬ ЭТИ 34 СТРОКИ
    """Trading signals from fas.scoring_history"""
    __tablename__ = 'signals'
    __table_args__ = {'schema': 'fas'}

    id = Column(Integer, primary_key=True)
    trading_pair_id = Column(Integer, nullable=False, index=True)
    ...
    # trades = relationship("Trade", back_populates="signal")  # Commented for tests


class Trade(Base):
    """Executed trades"""
    __tablename__ = 'trades'
```

**AFTER:**
```python
class PositionStatus(enum.Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class Trade(Base):
    """Executed trades"""
    __tablename__ = 'trades'
```

**✅ Checkpoint:** Класс Signal удален, синтаксис Python корректен

### 3.2 Удалить ForeignKey на fas.signals

**Файл:** `database/models.py`

**Действие:** Изменить строку 78 (в Trade model)

**BEFORE:**
```python
class Trade(Base):
    """Executed trades"""
    __tablename__ = 'trades'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey('fas.signals.id'), nullable=True)  # ← ИЗМЕНИТЬ
```

**AFTER:**
```python
class Trade(Base):
    """Executed trades"""
    __tablename__ = 'trades'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)
    # signal_id: WebSocket message ID (NOT a FK to fas.signals!)
    signal_id = Column(String(100), nullable=True)  # Changed from Integer + ForeignKey
```

**✅ Checkpoint:** ForeignKey удален, тип изменен на String(100)

### 3.3 Удалить закомментированные relationships

**Файл:** `database/models.py`

**Действие:** Найти и удалить все закомментированные строки с relationship к Signal

**Поиск:**
```bash
grep -n "# signal = relationship" database/models.py
```

**Удалить найденные строки** (примерно line 104):
```python
# signal = relationship("Signal", back_populates="trades", foreign_keys=[signal_id])  # Commented for tests
```

**✅ Checkpoint:** Все references на Signal удалены из models.py

### 3.4 Исправить signal_id = 'unknown' на None

**Файл:** `core/signal_processor_websocket.py`

**Действие:** Изменить строку 509

**BEFORE:**
```python
signal_id = signal.get('id', 'unknown')  # ⚠️ Может быть строка 'unknown'
```

**AFTER:**
```python
signal_id = signal.get('id')  # None if no ID (NULL in DB instead of 'unknown')
if signal_id is None:
    logger.warning(f"Signal has no ID for {signal.get('symbol')}, using NULL")
```

**✅ Checkpoint:** 'unknown' больше не используется

### 3.5 Добавить комментарий в repository.py

**Файл:** `database/repository.py`

**Действие:** Добавить комментарий к signal_id usage

**Локация:** Перед строкой 210

**Добавить:**
```python
async def create_position(self, position_data: dict) -> int:
    """Create new position record in monitoring.positions

    Args:
        position_data: Position data including:
            - signal_id: WebSocket message ID (str/int/None), NOT a FK!
            - symbol, exchange, side, quantity, entry_price, etc.
    """
```

**✅ Checkpoint:** Документация обновлена

### 3.6 Обновить init.sql комментарий

**Файл:** `database/init.sql`

**Действие:** Добавить комментарий к fas.scoring_history

**Локация:** Перед строкой 6

**Добавить:**
```sql
-- LEGACY NOTE: Table fas.scoring_history (mapped as 'signals' in SQLAlchemy)
-- is not used by the bot anymore. Signals are received via WebSocket.
-- Kept for historical data / external system compatibility.
-- Last used: Before 2024-XX-XX
CREATE TABLE IF NOT EXISTS fas.scoring_history (
```

**Локация:** В таблице monitoring.positions, перед строкой 26

**Добавить:**
```sql
CREATE TABLE IF NOT EXISTS monitoring.positions (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(100),  -- WebSocket message ID (NOT a FK to fas.signals!)
```

**✅ Checkpoint:** SQL комментарии добавлены

---

## ЭТАП 4: ИСПРАВЛЕНИЕ ТЕСТОВ

### 4.1 Исправить tests/conftest.py

**Файл:** `tests/conftest.py`

**Действие:** Заменить Signal import и fixture

**BEFORE (line 19):**
```python
from database.models import Position, Order, Signal, Trade
```

**AFTER:**
```python
from database.models import Position, Order, Trade  # Signal removed
```

**BEFORE (lines 160-172):**
```python
@pytest.fixture
def sample_signal() -> Signal:
    """Sample signal for testing"""
    return Signal(
        id='sig_789',
        source='strategy_1',
        symbol='BTC/USDT',
        action='open_long',
        strength=Decimal('0.8'),
        entry_price=Decimal('50000'),
        stop_loss=Decimal('49000'),
        take_profit=Decimal('51000'),
        created_at=datetime.now(timezone.utc)
    )
```

**AFTER:**
```python
@pytest.fixture
def sample_signal() -> Dict[str, Any]:
    """Sample signal for testing (dict, not SQLAlchemy model)"""
    return {
        'id': 'sig_789',
        'source': 'strategy_1',
        'symbol': 'BTC/USDT',
        'action': 'open_long',
        'strength': 0.8,
        'entry_price': 50000,
        'stop_loss': 49000,
        'take_profit': 51000,
        'created_at': datetime.now(timezone.utc)
    }
```

**✅ Checkpoint:** conftest.py исправлен

### 4.2 Исправить tests/integration/test_trading_flow.py

**Файл:** `tests/integration/test_trading_flow.py`

**Действие 1:** Удалить Signal из import (line 16)

**BEFORE:**
```python
from database.models import Signal, Position, Order
```

**AFTER:**
```python
from database.models import Position, Order  # Signal removed (legacy)
```

**Действие 2:** Заменить все Signal() на dict

**Метод:** `test_signal_to_position_flow` (lines 75-85)

**BEFORE:**
```python
signal = Signal(
    trading_pair_id=1,
    pair_symbol='BTC/USDT',
    exchange_id=1,
    exchange_name='binance',
    score_week=0.8,
    score_month=0.75,
    recommended_action='BUY',
    patterns_details={},
    combinations_details={}
)
```

**AFTER:**
```python
signal = {
    'id': 'test_signal_1',  # Add ID field
    'trading_pair_id': 1,
    'pair_symbol': 'BTC/USDT',
    'exchange_id': 1,
    'exchange_name': 'binance',
    'score_week': 0.8,
    'score_month': 0.75,
    'recommended_action': 'BUY',
    'patterns_details': {},
    'combinations_details': {}
}
```

**Повторить для всех Signal() instances:**
- Line 140 - `test_risk_violation_blocks_trade`
- Lines 256, 265, 274 - `test_multiple_signals_processing`

**✅ Checkpoint:** Все тесты исправлены

---

## ЭТАП 5: ПРОВЕРКА И ТЕСТИРОВАНИЕ

### 5.1 Статическая проверка кода

```bash
# 1. Проверка синтаксиса Python
python3 -m py_compile database/models.py
python3 -m py_compile tests/conftest.py
python3 -m py_compile tests/integration/test_trading_flow.py
python3 -m py_compile core/signal_processor_websocket.py
python3 -m py_compile database/repository.py

# 2. Проверка импортов
python3 -c "from database.models import Trade, Position, Order; print('OK')"

# 3. Поиск оставшихся references на Signal
grep -r "from.*models.*import.*Signal" --include="*.py" .
# Ожидается: только в закомментированном коде или строках

grep -r "Signal\(" --include="*.py" . | grep -v "SignalAdapter\|SignalProcessor\|SignalWebSocket"
# Ожидается: только в комментариях

# 4. Проверка ForeignKey не осталось
grep -r "ForeignKey.*fas\.signals" --include="*.py" .
# Ожидается: пусто
```

**✅ Checkpoint:** Статические проверки пройдены

### 5.2 Запуск тестов

```bash
# 1. Запустить измененные тесты
pytest tests/conftest.py::sample_signal -v
# Ожидается: PASSED

pytest tests/integration/test_trading_flow.py::TestTradingFlow::test_signal_to_position_flow -v
pytest tests/integration/test_trading_flow.py::TestTradingFlow::test_risk_violation_blocks_trade -v
pytest tests/integration/test_trading_flow.py::TestTradingFlow::test_multiple_signals_processing -v
# Ожидается: ВСЕ PASSED

# 2. Запустить весь test suite
pytest tests/ -v --tb=short
# Проверить нет новых failures

# 3. Запустить только быстрые тесты
pytest tests/ -m "not slow" -v
```

**✅ Checkpoint:** Все тесты проходят

### 5.3 Integration test с БД

```bash
# Запустить бота в dev mode (если есть dev конфиг)
python3 main.py --config config/dev.yaml --dry-run

# Проверить логи на ошибки
tail -f logs/trading_bot.log | grep -E "ERROR|EXCEPTION|Signal"

# Проверить можно создать позицию
python3 -c "
import asyncio
from database.repository import Repository
from config.settings import Config

async def test():
    config = Config()
    repo = Repository(config.database)
    await repo.initialize()

    # Test create position with string signal_id
    position_id = await repo.create_position({
        'signal_id': 'websocket_test_123',  # String теперь ОК
        'symbol': 'BTCUSDT',
        'exchange': 'binance',
        'side': 'long',
        'quantity': 0.001,
        'entry_price': 50000
    })
    print(f'✅ Created position: {position_id}')

    await repo.close()

asyncio.run(test())
"
```

**✅ Checkpoint:** Integration tests пройдены

---

## ЭТАП 6: ФИНАЛИЗАЦИЯ И ДОКУМЕНТАЦИЯ

### 6.1 Коммит изменений

```bash
# Проверить статус
git status

# Добавить измененные файлы
git add database/models.py
git add database/migrations/003_cleanup_fas_signals.sql
git add database/init.sql
git add database/repository.py
git add core/signal_processor_websocket.py
git add tests/conftest.py
git add tests/integration/test_trading_flow.py

# Создать коммит
git commit -m "♻️ refactor: Remove legacy fas.signals table and Signal model

BREAKING CHANGE: Signal SQLAlchemy model removed

Changes:
- Remove Signal class from database/models.py
- Change signal_id type from INTEGER to VARCHAR(100) in DB
- Remove ForeignKey constraint to fas.signals
- Fix signal_id = 'unknown' → None in signal processor
- Update tests to use dict instead of Signal()
- Add migration 003_cleanup_fas_signals.sql
- Update documentation and comments

Rationale:
- fas.signals table is LEGACY from old architecture
- Signals now received via WebSocket, not from DB
- Signal model not used in production code
- Only tests were affected (fixed)

Migration:
- database/migrations/003_cleanup_fas_signals.sql
- Backup created in ./backups/fas_cleanup_*
- Rollback available in migration comments

Tests:
- All tests passing
- Integration tests verified with DB

Closes: #ISSUE_NUMBER (if applicable)
"

# Проверить коммит
git log -1 --stat
```

**✅ Checkpoint:** Изменения закоммичены

### 6.2 Создать Pull Request (если используется)

```bash
# Push ветку в remote
git push -u origin cleanup/remove-fas-signals

# Создать PR через gh CLI (если установлен)
gh pr create \
    --title "♻️ Remove legacy fas.signals table and Signal model" \
    --body "$(cat <<'EOF'
## Summary
Remove legacy `fas.signals` table and `Signal` SQLAlchemy model that are no longer used in production.

## Context
- **Old architecture:** Signals were polled from `fas.signals` database table
- **New architecture:** Signals received via WebSocket in real-time
- **Usage:** Only test files were using Signal model, not production code

## Changes
- ✅ Removed `Signal` class from `database/models.py`
- ✅ Changed `signal_id` column type from `INTEGER` to `VARCHAR(100)`
- ✅ Removed `ForeignKey` constraint to `fas.signals.id`
- ✅ Fixed `signal_id = 'unknown'` → `None` (NULL in DB)
- ✅ Updated tests to use dict instead of Signal()
- ✅ Added migration with rollback script
- ✅ Updated documentation

## Migration
- File: `database/migrations/003_cleanup_fas_signals.sql`
- Duration: ~10 seconds
- Risk: MEDIUM (type change, but no production usage)
- Rollback: Available in migration file comments
- Backup: Created before migration

## Testing
- ✅ All unit tests passing
- ✅ Integration tests verified
- ✅ Manual DB verification completed
- ✅ No FK constraints found
- ✅ Data integrity verified

## Checklist
- [x] Migration script created and tested
- [x] Backup created before migration
- [x] Code changes completed
- [x] Tests fixed and passing
- [x] Documentation updated
- [x] Rollback plan documented

## Breaking Changes
- `Signal` model removed from `database.models`
- Tests using `Signal()` must use dict instead
- `signal_id` column now `VARCHAR(100)` instead of `INTEGER`

## Risk Assessment
- Production risk: **LOW** (not used in production)
- Test risk: **MEDIUM** (tests updated, verified)
- DB risk: **MEDIUM** (type change, but nullable column)

## Related Issues
Closes #ISSUE_NUMBER (if applicable)

---

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" \
    --base main \
    --head cleanup/remove-fas-signals
```

**✅ Checkpoint:** PR создан

### 6.3 Обновить документацию

**Создать файл:** `docs/CHANGELOG_fas_signals_cleanup.md`

**Содержание:**

```markdown
# Changelog: fas.signals Cleanup

## Date: 2025-10-14

## Summary
Removed legacy `fas.signals` table and `Signal` SQLAlchemy model.

## Background
The `fas.signals` table (also known as `fas.scoring_history`) was part of the old architecture where trading signals were stored in the database and polled by the bot.

**Old flow:**
```
External system → fas.signals table → Bot polls DB → Process signal
```

**New flow (current):**
```
External system → WebSocket → Bot receives real-time → Process signal
```

The `fas.signals` table has not been used since ~2024-XX-XX.

## Changes Made

### Database
1. Changed `signal_id` column type: `INTEGER` → `VARCHAR(100)`
   - Table: `monitoring.positions`
   - Table: `monitoring.trades`
   - Reason: Code passes WebSocket message IDs (can be strings like 'wave_123')

2. Removed Foreign Key constraints (if any existed)
   - From: `monitoring.trades.signal_id` → `fas.signals.id`
   - Status: Constraints were already commented out in SQLAlchemy

3. Added column comments documenting new semantic
   - `signal_id`: "WebSocket message ID (NOT a FK to fas.signals!)"

### Code
1. Removed `Signal` class from `database/models.py` (lines 36-69)
2. Removed `ForeignKey('fas.signals.id')` from `Trade` model
3. Fixed `signal_id = signal.get('id', 'unknown')` → `signal.get('id')`
   - Location: `core/signal_processor_websocket.py:509`
4. Removed commented relationships to Signal model

### Tests
1. Updated `tests/conftest.py`:
   - Removed `Signal` from imports
   - Changed `sample_signal()` fixture to return dict

2. Updated `tests/integration/test_trading_flow.py`:
   - Removed `Signal` from imports
   - Replaced all `Signal()` instances with dicts

### Documentation
1. Added comments to `database/init.sql`
2. Updated docstrings in `database/repository.py`
3. Created this changelog

## Migration

### File
`database/migrations/003_cleanup_fas_signals.sql`

### What it does
1. Pre-flight checks (data counts, FK constraints)
2. Creates temp backup table
3. Drops FK constraints (if exist)
4. Changes column type: `INTEGER` → `VARCHAR(100)`
5. Adds column comments
6. Verifies data integrity
7. Logs migration event

### Rollback
Available in migration file comments. **WARNING:** Rollback will fail if any `signal_id` contains non-numeric values after cleanup!

### Duration
~10 seconds on typical database

## Impact

### Production Code
✅ **NO IMPACT** - Production code never used Signal model

### Tests
⚠️ **BREAKING** - Tests must be updated (already done in this branch)

### Database
⚠️ **SCHEMA CHANGE** - `signal_id` type changed, but column nullable

### Data
✅ **NO DATA LOSS** - All existing data preserved

## Verification

### Before migration
```sql
-- Check signal_id type
SELECT data_type FROM information_schema.columns
WHERE table_name = 'positions' AND column_name = 'signal_id';
-- Result: integer

-- Check FK constraints
SELECT conname FROM pg_constraint WHERE confrelid = 'fas.scoring_history'::regclass;
-- Result: (empty)
```

### After migration
```sql
-- Check signal_id type
SELECT data_type FROM information_schema.columns
WHERE table_name = 'positions' AND column_name = 'signal_id';
-- Result: character varying

-- Verify data preserved
SELECT COUNT(*) FROM monitoring.positions WHERE signal_id IS NOT NULL;
-- Result: (same as before)
```

## Rollback Plan

If issues occur, follow these steps:

1. **Code rollback:**
   ```bash
   git revert <commit-hash>
   git push
   ```

2. **Database rollback:**
   ```sql
   -- See migration file comments for full rollback script
   ALTER TABLE monitoring.positions
   ALTER COLUMN signal_id TYPE INTEGER USING signal_id::INTEGER;
   ```

3. **Restore from backup:**
   ```bash
   pg_restore -h <host> -U <user> -d <database> \
       --schema=monitoring \
       ./backups/fas_cleanup_*/pre_cleanup_backup.dump
   ```

## Future Work

### Optional (Low priority)
1. Drop `fas.scoring_history` table entirely (if confirmed unused by external systems)
2. Rename `signal_id` column to `webhook_message_id` for clarity
3. Add index on `signal_id` if queries by this field become common

## Questions & Answers

**Q: Why not just drop the fas.signals table?**
A: Table might be used by external systems. We only removed Python code dependency.

**Q: What if old backups need to be restored?**
A: Old backups will restore fine. The column exists, just different type now.

**Q: Will this break existing production data?**
A: No. All existing data is preserved and accessible.

**Q: Can we rollback after 'unknown' strings are stored?**
A: Rollback to INTEGER will fail. Must clean data first or use custom USING clause.

## References
- Initial research: `FAS_SIGNALS_USAGE_RESEARCH.md`
- Deep research: `FAS_SIGNALS_DEEP_RESEARCH_REPORT.md`
- Implementation plan: `FAS_SIGNALS_CLEANUP_SAFE_IMPLEMENTATION_PLAN.md` (this file)
```

**✅ Checkpoint:** Документация создана

---

## ЭТАП 7: ROLLBACK STRATEGY

### Сценарий 1: Откат до применения изменений в production

**Ситуация:** Обнаружены проблемы после merge в main, но до deploy

**Действия:**
```bash
# 1. Revert коммит
git revert <commit-hash>
git push origin main

# 2. БД откатывать НЕ НУЖНО (миграция еще не запускалась)
```

### Сценарий 2: Откат после миграции БД

**Ситуация:** Миграция применена, но возникли проблемы

**Действия:**

```bash
# 1. Остановить бота
systemctl stop trading-bot  # или kill process

# 2. Восстановить код
git checkout main  # или revert commit
git pull

# 3. Откат миграции БД
psql -h <host> -U <user> -d <database> <<'EOF'
BEGIN;

-- Verify no non-numeric signal_id values (критично!)
DO $$
DECLARE
    non_numeric_pos INTEGER;
    non_numeric_trades INTEGER;
BEGIN
    SELECT COUNT(*) INTO non_numeric_pos
    FROM monitoring.positions
    WHERE signal_id IS NOT NULL AND signal_id !~ '^\d+$';

    SELECT COUNT(*) INTO non_numeric_trades
    FROM monitoring.trades
    WHERE signal_id IS NOT NULL AND signal_id !~ '^\d+$';

    IF non_numeric_pos > 0 OR non_numeric_trades > 0 THEN
        RAISE EXCEPTION 'Cannot rollback: Found non-numeric values (pos=%, trades=%)',
            non_numeric_pos, non_numeric_trades;
    END IF;
END $$;

-- Rollback type changes
ALTER TABLE monitoring.positions
ALTER COLUMN signal_id TYPE INTEGER
USING CASE
    WHEN signal_id ~ '^\d+$' THEN signal_id::INTEGER
    ELSE NULL
END;

ALTER TABLE monitoring.trades
ALTER COLUMN signal_id TYPE INTEGER
USING CASE
    WHEN signal_id ~ '^\d+$' THEN signal_id::INTEGER
    ELSE NULL
END;

-- Log rollback
INSERT INTO monitoring.risk_events (event_type, risk_level, details)
VALUES (
    'database_migration_rollback',
    'critical',
    json_build_object(
        'migration', '003_cleanup_fas_signals',
        'date', NOW(),
        'action', 'ROLLED BACK',
        'reason', 'Production issues detected'
    )::jsonb
);

COMMIT;
EOF

# 4. Restore Signal class в models.py
git checkout main -- database/models.py

# 5. Restore тесты
git checkout main -- tests/conftest.py tests/integration/test_trading_flow.py

# 6. Запустить тесты
pytest tests/ -v

# 7. Перезапустить бота
systemctl start trading-bot
```

**✅ Checkpoint:** Rollback выполнен, система в исходном состоянии

### Сценарий 3: Полное восстановление из backup

**Ситуация:** Катастрофический сбой, нужно полное восстановление

**Действия:**

```bash
# 1. Остановить бота
systemctl stop trading-bot

# 2. Найти backup
ls -lht ./backups/fas_cleanup_*/

# 3. Восстановить БД из backup
pg_restore -h <host> -U <user> -d <database> \
    --clean \
    --if-exists \
    --schema=monitoring \
    --schema=fas \
    ./backups/fas_cleanup_YYYYMMDD_HHMMSS/pre_cleanup_backup.dump \
    -v

# 4. Verify restore
psql -h <host> -U <user> -d <database> -c "
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'monitoring'
AND table_name IN ('positions', 'trades')
AND column_name = 'signal_id';
"

# 5. Restore code
git checkout main
git pull
pip install -r requirements.txt

# 6. Restart bot
systemctl start trading-bot

# 7. Verify logs
tail -f logs/trading_bot.log
```

**✅ Checkpoint:** Полное восстановление выполнено

---

## CHECKLIST ФИНАЛЬНОЙ ПРОВЕРКИ

Перед закрытием задачи убедиться ВСЕ пункты выполнены:

### Pre-implementation
- [ ] Backup БД создан и проверен
- [ ] Git ветка создана
- [ ] Pre-flight checks выполнены и прошли

### Database
- [ ] Миграция создана
- [ ] Миграция протестирована на test DB
- [ ] Миграция применена на production DB
- [ ] Post-migration verification пройдена
- [ ] signal_id тип = VARCHAR(100)
- [ ] FK constraints отсутствуют
- [ ] Данные не потеряны (count совпадает)

### Code Changes
- [ ] Signal class удален из models.py
- [ ] ForeignKey удален из Trade model
- [ ] signal_id тип изменен на String(100)
- [ ] 'unknown' заменен на None в signal_processor
- [ ] Комментарии добавлены в repository.py
- [ ] Комментарии добавлены в init.sql
- [ ] Импорты Signal удалены везде

### Tests
- [ ] conftest.py исправлен
- [ ] test_trading_flow.py исправлен
- [ ] Все тесты проходят
- [ ] Integration tests с БД пройдены

### Documentation
- [ ] Коммит message написан
- [ ] CHANGELOG created
- [ ] Комментарии в коде обновлены
- [ ] Rollback plan документирован

### Verification
- [ ] Статические проверки пройдены
- [ ] Unit tests пройдены
- [ ] Integration tests пройдены
- [ ] Manual testing выполнен
- [ ] Production deploy plan готов

### Git
- [ ] Изменения закоммичены
- [ ] Ветка push в remote
- [ ] PR создан (если используется)
- [ ] Code review запрошен (если нужен)

### Rollback Preparedness
- [ ] Backup доступен и проверен
- [ ] Rollback script протестирован
- [ ] Rollback plan документирован
- [ ] Team уведомлена о изменениях

---

## TIMING И EXECUTION PLAN

### Рекомендуемое время выполнения

**🕐 Лучшее время:** В период минимальной активности бота (ночь, выходные)

**Причины:**
- Миграция БД занимает ~10 секунд (можно делать на лету)
- Тесты могут занять 5-10 минут
- Rollback должен быть быстрым если что-то пошло не так

### Execution Timeline

```
T+0:00  - Начало: Pre-flight checks (10 мин)
T+0:10  - Создание backup (5 мин)
T+0:15  - Запуск миграции на test DB (5 мин)
T+0:20  - Verify test DB (5 мин)
T+0:25  - Запуск миграции на production DB (1 мин)
T+0:26  - Verify production DB (4 мин)
T+0:30  - Git branch + код changes (20 мин)
T+0:50  - Test fixes (15 мин)
T+1:05  - Running tests (10 мин)
T+1:15  - Verification + documentation (10 мин)
T+1:25  - Git commit + PR (5 мин)
-------------------------------------------
T+1:30  - ЗАВЕРШЕНО (1 час 30 минут)
```

### Команда для выполнения

**Минимум:** 1 человек (может делать самостоятельно)
**Рекомендуется:** 2 человека (один выполняет, второй проверяет)

---

## CONTACTS И SUPPORT

### В случае проблем

**Rollback:** Следовать "ЭТАП 7: ROLLBACK STRATEGY"

**DB Issues:**
- Проверить backup: `ls -lh ./backups/fas_cleanup_*/`
- Rollback migration (см. migration file comments)
- Restore from backup если критично

**Code Issues:**
- `git revert <commit>`
- Restore Signal class from main branch
- Rerun tests

**Test Failures:**
- Check test logs
- Verify Signal imports removed
- Verify dict format correct

---

## CONCLUSION

Этот план обеспечивает **БЕЗОПАСНУЮ** реализацию очистки `fas.signals`:

✅ Детальные pre-flight checks
✅ Backup strategy
✅ Step-by-step execution
✅ Comprehensive testing
✅ Rollback plan
✅ Documentation

**Estimated risk:** 🟡 MEDIUM (тесты ломаются, но production безопасен)
**Estimated effort:** ~90 minutes
**Recommended:** Выполнять в низкую активность периода

**ВАЖНО:** Это ПЛАН, не выполнение. Код НЕ изменен согласно требованиям!

---

**План создан:** 2025-10-14
**Версия:** 1.0
**Статус:** ✅ READY FOR IMPLEMENTATION

**Следующий шаг:** Получить approval и запланировать execution
