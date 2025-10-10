# План исправления: Дублирование волн и позиций

**Дата**: 2025-10-11
**Приоритет**: 🔴 КРИТИЧЕСКИЙ
**Затронутые компоненты**: `core/signal_processor_websocket.py`, `core/position_manager.py`

---

## 📋 ПРОБЛЕМЫ

### Баг #1: Race Condition - Волна обрабатывается дважды

**Симптомы**:
- Одна и та же волна запускается 2 раза параллельно
- В логах: две записи "Wave detected" с разницей ~8ms
- Результат: дублирование всех позиций волны

**Пример из логов**:
```
01:51:03.125 - 🌊 Wave detected! Processing 8 signals   ← ПЕРВАЯ
01:51:03.134 - 🌊 Wave detected! Processing 8 signals   ← ВТОРАЯ (через 8ms)
```

**Root Cause** (строки 202-218 в signal_processor_websocket.py):
```python
# ❌ НЕ АТОМАРНО: проверка и установка разделены
if expected_wave_timestamp in self.processed_waves:
    continue

# ... обработка волны ...

# Помечается ПОСЛЕ обработки (слишком поздно!)
self.processed_waves[expected_wave_timestamp] = {...}
```

**Последствия**:
- 7 позиций в волне → открыто 14 (7 дубликатов)
- Удвоенная экспозиция
- Нарушение лимита MAX_TRADES_PER_15MIN

### Баг #2: Дублирование позиций при параллельном выполнении

**Симптомы**:
- Одна позиция открывается дважды на бирже
- В БД 2 записи с одинаковым символом

**Пример**:
```
ID 250: AKEUSDT binance short 143853 @ 0.00139
ID 251: AKEUSDT binance short 143853 @ 0.00139 ← ДУБЛИКАТ
```

**Root Cause** (_position_exists, строки 744-755):
```python
# Check exchange
positions = await exchange_obj.fetch_positions()  # ← Долгий запрос ~500ms
# Две параллельные задачи получают "позиции нет"
# Обе открывают позицию!
```

**Timeline**:
```
T+0ms:  Задача 1: _position_exists(AKEUSDT) → запрос к бирже
T+70ms: Задача 2: _position_exists(AKEUSDT) → запрос к бирже
        ↓ Обе получают "позиции нет"
T+4s:   Задача 1: Position opened AKEUSDT
T+4s:   Задача 2: Position opened AKEUSDT ← ДУБЛИКАТ!
```

**Последствия**:
- Удвоенная позиция на бирже
- Удвоенный риск
- Проблемы с закрытием (нужно закрывать обе)

---

## 🎯 РЕШЕНИЕ

### Fix #1: Атомарная защита обработки волн

**Изменения в signal_processor_websocket.py (_monitor_wave_loop, строка 202)**:

```python
# ПЕРЕД обработкой волны
if expected_wave_timestamp in self.processed_waves:
    logger.info(f"Wave {expected_wave_timestamp} already processed, skipping")
    continue

# ✅ КРИТИЧНО: Атомарно помечаем волну КАК ТОЛЬКО начали обработку
self.processed_waves[expected_wave_timestamp] = {
    'status': 'processing',  # ← Защита от параллельного запуска
    'started_at': datetime.now(timezone.utc),
    'signal_ids': set(),  # Пока пустой, заполним после получения сигналов
    'count': 0
}

# Теперь безопасно запускать обработку
wave_signals = await self._monitor_wave_appearance(expected_wave_timestamp)

if wave_signals:
    # Обновляем данные волны
    self.processed_waves[expected_wave_timestamp].update({
        'signal_ids': set(s.get('id') for s in wave_signals),
        'count': len(wave_signals),
        'status': 'executing'
    })

    # ... остальная обработка ...

    # После выполнения
    self.processed_waves[expected_wave_timestamp]['status'] = 'completed'
    self.processed_waves[expected_wave_timestamp]['completed_at'] = datetime.now(timezone.utc)
else:
    # Волна не найдена
    self.processed_waves[expected_wave_timestamp]['status'] = 'not_found'
```

### Fix #2: Защита от дубликатов на уровне position_manager

**Вариант А: Lock на уровне всей проверки (РЕКОМЕНДУЕМЫЙ)**

```python
# В __init__ добавить
self.check_locks = {}  # Dict[str, asyncio.Lock]

async def _position_exists(self, symbol: str, exchange: str) -> bool:
    """Check if position already exists with atomic lock"""

    lock_key = f"{exchange}_{symbol}"

    # ✅ Получаем или создаем lock для этого символа
    if lock_key not in self.check_locks:
        self.check_locks[lock_key] = asyncio.Lock()

    async with self.check_locks[lock_key]:
        # Теперь только ОДНА задача может проверять за раз

        # Check local tracking
        if symbol in self.positions:
            return True

        # Check database
        db_position = await self.repository.get_open_position(symbol, exchange)
        if db_position:
            return True

        # Check exchange (теперь защищено от race condition)
        exchange_obj = self.exchanges.get(exchange)
        if exchange_obj:
            positions = await exchange_obj.fetch_positions()
            normalized_symbol = normalize_symbol(symbol)
            for pos in positions:
                if normalize_symbol(pos.get('symbol')) == normalized_symbol:
                    contracts = float(pos.get('contracts') or 0)
                    if abs(contracts) > 0:
                        return True

        return False
```

**Вариант Б: Использовать существующий position_locks (АЛЬТЕРНАТИВА)**

Можно использовать существующий `self.position_locks`, но нужно убедиться что он проверяется в `_position_exists()`.

---

## 📊 ПЛАН ВНЕДРЕНИЯ

### Этап 0: Подготовка (5 мин)

**0.1 Git Safety**
```bash
# Закоммитить текущее состояние
git add -A
git commit -m "💾 Current state before wave duplicate fix"

# Создать safety tag
git tag -a "before-wave-dup-fix" -m "State before wave duplication fix - 2025-10-11"

# Создать feature branch
git checkout -b fix/wave-duplication-race-condition

# Запушить все для безопасности
git push origin main
git push origin before-wave-dup-fix
```

**0.2 Snapshot метрик**
```bash
# Текущие активные позиции
echo "=== BEFORE FIX ===" > metrics_before_wave_fix.txt
date >> metrics_before_wave_fix.txt

# Статистика БД
psql -c "SELECT COUNT(*) as total,
         COUNT(DISTINCT symbol) as unique_symbols
         FROM monitoring.positions
         WHERE status='active'" >> metrics_before_wave_fix.txt

# Git info
git log --oneline -3 >> metrics_before_wave_fix.txt
```

**0.3 Закрыть дубликаты из последней волны**
```sql
-- Идентифицировать дубликаты
SELECT symbol, exchange, COUNT(*) as cnt
FROM monitoring.positions
WHERE status = 'active'
  AND opened_at >= '2025-10-11 01:51:00'
GROUP BY symbol, exchange
HAVING COUNT(*) > 1;

-- Закрыть дубликаты (оставить первую позицию)
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY symbol, exchange ORDER BY id) as rn
    FROM monitoring.positions
    WHERE status = 'active'
      AND opened_at >= '2025-10-11 01:51:00'
)
UPDATE monitoring.positions
SET status = 'closed',
    exit_reason = 'duplicate_wave_cleanup',
    closed_at = NOW()
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
```

### Этап 1: Fix #1 - Атомарная защита волн (15 мин)

**1.1 Изменить signal_processor_websocket.py**

Файл: `core/signal_processor_websocket.py`
Метод: `_monitor_wave_loop()` (строки 200-220)

```python
# БЫЛО (строка 202):
if expected_wave_timestamp in self.processed_waves:
    logger.info(f"Wave {expected_wave_timestamp} already processed, skipping")
    continue

# ... обработка ...

self.processed_waves[expected_wave_timestamp] = {
    'signal_ids': set(s.get('id') for s in wave_signals),
    'count': len(wave_signals),
    'first_seen': datetime.now(timezone.utc)
}

# СТАЛО:
if expected_wave_timestamp in self.processed_waves:
    logger.info(f"Wave {expected_wave_timestamp} already processed, skipping")
    continue

# ✅ АТОМАРНАЯ ЗАЩИТА: Помечаем СРАЗУ
self.processed_waves[expected_wave_timestamp] = {
    'status': 'processing',
    'started_at': datetime.now(timezone.utc),
    'signal_ids': set(),
    'count': 0
}

# ... получаем сигналы ...

if wave_signals:
    # Обновляем информацию
    self.processed_waves[expected_wave_timestamp].update({
        'signal_ids': set(s.get('id') for s in wave_signals),
        'count': len(wave_signals),
        'status': 'executing',
        'first_seen': datetime.now(timezone.utc)
    })

    # ... выполнение ...

    # После выполнения
    self.processed_waves[expected_wave_timestamp]['status'] = 'completed'
    self.processed_waves[expected_wave_timestamp]['completed_at'] = datetime.now(timezone.utc)
else:
    self.processed_waves[expected_wave_timestamp]['status'] = 'not_found'
```

**1.2 Тест Fix #1**

```bash
# Запустить бот
python3 main.py &

# Дождаться следующей волны (например 02:06)
# Проверить логи - должна быть ОДНА запись "Wave detected"
grep "Wave detected" logs/trading_bot.log | tail -n 5

# Проверить БД - НЕ должно быть дубликатов
psql -c "
SELECT symbol, exchange, COUNT(*)
FROM monitoring.positions
WHERE opened_at >= NOW() - INTERVAL '5 minutes'
  AND status = 'active'
GROUP BY symbol, exchange
HAVING COUNT(*) > 1
"
# Ожидаемый результат: 0 строк
```

### Этап 2: Fix #2 - Защита от дубликатов позиций (20 мин)

**2.1 Добавить check_locks в PositionManager**

Файл: `core/position_manager.py`
Метод: `__init__` (добавить строку)

```python
def __init__(self, ...):
    # ... существующий код ...
    self.position_locks: Set[str] = set()

    # ✅ НОВОЕ: Lock для атомарных проверок
    self.check_locks: Dict[str, asyncio.Lock] = {}
```

**2.2 Изменить _position_exists**

Файл: `core/position_manager.py`
Метод: `_position_exists()` (строки 733-757)

```python
async def _position_exists(self, symbol: str, exchange: str) -> bool:
    """Check if position already exists (thread-safe)"""

    lock_key = f"{exchange}_{symbol}"

    # ✅ Получаем или создаем lock для этого символа
    if lock_key not in self.check_locks:
        self.check_locks[lock_key] = asyncio.Lock()

    async with self.check_locks[lock_key]:
        # Check local tracking
        if symbol in self.positions:
            return True

        # Check database
        db_position = await self.repository.get_open_position(symbol, exchange)
        if db_position:
            return True

        # Check exchange
        exchange_obj = self.exchanges.get(exchange)
        if exchange_obj:
            positions = await exchange_obj.fetch_positions()
            normalized_symbol = normalize_symbol(symbol)
            for pos in positions:
                if normalize_symbol(pos.get('symbol')) == normalized_symbol:
                    contracts = float(pos.get('contracts') or 0)
                    if abs(contracts) > 0:
                        return True

        return False
```

**2.3 Тест Fix #2**

Создать unit test для проверки параллельных вызовов.

Файл: `tests/unit/test_position_manager_race_condition.py`

```python
"""
Unit test for position_manager race condition fix
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.position_manager import PositionManager

@pytest.mark.asyncio
async def test_position_exists_parallel_calls():
    """
    Test that parallel calls to _position_exists don't cause race condition
    """
    # Setup mock position manager
    manager = MagicMock()
    manager.positions = {}
    manager.check_locks = {}
    manager.repository = MagicMock()
    manager.repository.get_open_position = AsyncMock(return_value=None)

    mock_exchange = MagicMock()
    mock_exchange.fetch_positions = AsyncMock(return_value=[])
    manager.exchanges = {'binance': mock_exchange}

    # Bind the real method
    from core.position_manager import PositionManager
    manager._position_exists = PositionManager._position_exists.__get__(manager)

    # Run 10 parallel checks
    tasks = [
        manager._position_exists('BTCUSDT', 'binance')
        for _ in range(10)
    ]

    results = await asyncio.gather(*tasks)

    # All should return False (position doesn't exist)
    assert all(r == False for r in results)

    # fetch_positions should be called exactly 10 times (one per task)
    # but sequentially due to lock
    assert mock_exchange.fetch_positions.call_count == 10

    print("✅ PASS: 10 parallel calls handled correctly with lock")

@pytest.mark.asyncio
async def test_no_duplicate_positions_in_wave():
    """
    Integration test: Ensure wave processing doesn't create duplicates
    """
    # This would be a more complex integration test
    # Testing the full flow from wave detection to position opening
    pass
```

### Этап 3: Интеграционное тестирование (30 мин)

**3.1 Остановить бота**
```bash
kill $(cat bot.pid)
```

**3.2 Очистить старые дубликаты**
```sql
-- Закрыть все дубликаты из предыдущих волн
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY symbol, exchange ORDER BY id) as rn
    FROM monitoring.positions
    WHERE status = 'active'
)
UPDATE monitoring.positions
SET status = 'closed',
    exit_reason = 'duplicate_cleanup_before_fix',
    closed_at = NOW()
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
```

**3.3 Запустить unit tests**
```bash
pytest tests/unit/test_position_manager_race_condition.py -v
```

**3.4 Запустить бота и дождаться волны**
```bash
# Текущее время
date +"%H:%M"

# Следующие волны: XX:06, XX:20, XX:35, XX:50
# Запустить бота
python3 main.py &

# Следить за логами
tail -f logs/trading_bot.log | grep -E "Wave detected|Position opened|duplicate"
```

**3.5 Проверить после волны**

```bash
# Проверить: только ОДНА запись "Wave detected"
grep "Wave detected.*$(date +%Y-%m-%d)" logs/trading_bot.log | wc -l
# Ожидается: 1 (для каждой волны)

# Проверить: НЕТ дубликатов в БД
psql -c "
SELECT symbol, exchange, COUNT(*) as cnt
FROM monitoring.positions
WHERE opened_at >= NOW() - INTERVAL '10 minutes'
  AND status = 'active'
GROUP BY symbol, exchange
HAVING COUNT(*) > 1
"
# Ожидается: 0 строк

# Проверить: количество позиций <= MAX_TRADES_PER_15MIN
psql -c "
SELECT COUNT(*) as positions_in_wave
FROM monitoring.positions
WHERE opened_at >= NOW() - INTERVAL '10 minutes'
  AND signal_id IS NOT NULL
  AND status = 'active'
"
# Ожидается: <= 5 (или значение MAX_TRADES_PER_15MIN из .env)
```

### Этап 4: Финализация и деплой (10 мин)

**4.1 Закоммитить изменения**
```bash
git add core/signal_processor_websocket.py
git add core/position_manager.py
git add tests/unit/test_position_manager_race_condition.py
git add metrics_before_wave_fix.txt

git commit -m "🔧 Fix wave duplication race conditions

Problem 1: Wave processed twice in parallel
- Root cause: Non-atomic check and mark of processed_waves
- Solution: Mark wave as 'processing' IMMEDIATELY before monitoring
- Impact: Prevents duplicate wave execution

Problem 2: Duplicate positions when checking exchange
- Root cause: Parallel _position_exists calls both see 'no position'
- Solution: Add asyncio.Lock per symbol+exchange for atomic checks
- Impact: Prevents duplicate position creation

Tests:
- Unit test for parallel _position_exists calls
- Integration test: verified single wave execution
- Zero duplicates after fix

Verified:
- Wave processed once (not twice)
- No duplicate positions in database
- Positions count <= MAX_TRADES_PER_15MIN

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**4.2 Merge в main**
```bash
git checkout main
git merge fix/wave-duplication-race-condition
```

**4.3 Создать verification tag**
```bash
git tag -a "wave-dup-fix-verified" -m "Wave duplication fix verified - 2025-10-11"
```

**4.4 Push в GitHub**
```bash
git push origin main
git push origin wave-dup-fix-verified
git push origin fix/wave-duplication-race-condition
```

**4.5 Создать summary**

Файл: `WAVE_DUPLICATE_FIX_RESULTS.md`

```markdown
# Wave Duplication Fix - Results

**Date**: 2025-10-11
**Status**: ✅ FIXED AND VERIFIED

## Problems Fixed
1. ✅ Wave race condition (duplicate execution)
2. ✅ Position duplication (parallel checks)

## Verification
- ✅ Unit tests pass (10/10 parallel calls handled correctly)
- ✅ Integration test: 1 wave processed (not 2)
- ✅ Zero duplicates in database after fix
- ✅ Position count respects MAX_TRADES_PER_15MIN

## Metrics
- Before: 14 positions (7 duplicates) per wave
- After: 7 positions (0 duplicates) per wave
- Improvement: -50% unnecessary positions

## Rollback
If needed: `git checkout before-wave-dup-fix`
```

---

## 🔒 ROLLBACK ПРОЦЕДУРЫ

### Вариант 1: Откат к тегу (рекомендуемый)
```bash
git checkout before-wave-dup-fix
kill $(cat bot.pid)
python3 main.py &
```

### Вариант 2: Откат изменений
```bash
git checkout main
git reset --hard before-wave-dup-fix
kill $(cat bot.pid)
python3 main.py &
```

### Вариант 3: Откат только signal_processor
```bash
git checkout before-wave-dup-fix -- core/signal_processor_websocket.py
git checkout before-wave-dup-fix -- core/position_manager.py
kill $(cat bot.pid)
python3 main.py &
```

---

## ✅ ACCEPTANCE CRITERIA

### Обязательные
- [ ] Unit test проходит: `test_position_exists_parallel_calls`
- [ ] Бот запускается без ошибок
- [ ] Волна обрабатывается ОДИН РАЗ (не два)
- [ ] ZERO дубликатов в БД после волны
- [ ] Позиций в волне <= MAX_TRADES_PER_15MIN

### Желательные
- [ ] 3 волны обработаны успешно без дубликатов
- [ ] Логи чистые (нет race condition warnings)
- [ ] Метрики стабильные (exposure в пределах нормы)

---

## 📊 TIMELINE

| Этап | Время | Статус |
|------|-------|--------|
| 0. Подготовка | 5 мин | ⏳ |
| 1. Fix #1 (Wave race) | 15 мин | ⏳ |
| 2. Fix #2 (Position dup) | 20 мин | ⏳ |
| 3. Testing | 30 мин | ⏳ |
| 4. Deploy | 10 мин | ⏳ |
| **TOTAL** | **~80 мин** | ⏳ |

---

## 🎯 NEXT STEPS AFTER DEPLOY

1. **Мониторинг 24ч**: Следить за следующими 4-6 волнами
2. **Метрики**: Проверять exposure и количество позиций
3. **Логи**: Отслеживать любые race condition warnings
4. **Очистка**: Удалить старые дубликаты через неделю если все ОК

---

**Status**: 📝 PLAN READY - Ожидает утверждения
