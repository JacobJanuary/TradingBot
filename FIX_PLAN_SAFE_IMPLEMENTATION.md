# 🔒 ПЛАН БЕЗОПАСНОГО УСТРАНЕНИЯ КРИТИЧЕСКИХ БАГОВ

## 📋 СОДЕРЖАНИЕ
1. [Общие принципы безопасности](#общие-принципы-безопасности)
2. [Подготовка окружения](#подготовка-окружения)
3. [Детальный план исправлений](#детальный-план-исправлений)
4. [Тестирование и валидация](#тестирование-и-валидация)
5. [Rollback стратегия](#rollback-стратегия)

---

## 🛡️ ОБЩИЕ ПРИНЦИПЫ БЕЗОПАСНОСТИ

### Правила внесения изменений:
1. **НИКОГДА** не вносить несколько критических изменений одновременно
2. **ВСЕГДА** создавать git checkpoint перед каждым изменением
3. **ОБЯЗАТЕЛЬНО** писать тесты ДО внесения изменений
4. **ТЕСТИРОВАТЬ** на тестовой среде минимум 24 часа
5. **ПРОВЕРЯТЬ** влияние на другие модули
6. **ДОКУМЕНТИРОВАТЬ** каждое изменение

### Git Strategy:
```bash
# Создаем ветку для исправлений
git checkout -b fix/critical-bugs-safe-implementation
git push -u origin fix/critical-bugs-safe-implementation

# После КАЖДОГО шага:
git add -A
git commit -m "🔒 [Step X] Description"
git push
git tag -a "checkpoint-X" -m "Checkpoint before next change"
git push --tags
```

---

## 🔧 ПОДГОТОВКА ОКРУЖЕНИЯ

### ШАГ 0: Backup и подготовка

```bash
# 1. Полный backup текущего состояния
git checkout main
git pull origin main
git tag -a "pre-fix-backup-$(date +%Y%m%d-%H%M%S)" -m "Backup before critical fixes"
git push --tags

# 2. Создание тестовой БД
pg_dump trading_bot_production > backup_$(date +%Y%m%d).sql
createdb trading_bot_test
psql trading_bot_test < backup_$(date +%Y%m%d).sql

# 3. Настройка тестового окружения
cp .env .env.production.backup
cp .env.test .env
# Изменить в .env: DATABASE_URL на тестовую БД, EXCHANGE_MODE=testnet

# 4. Создание feature branch
git checkout -b fix/critical-bugs-safe-implementation
```

### Создание системы мониторинга:

```python
# monitoring/fix_validator.py
"""
Валидатор для проверки корректности исправлений
"""
import logging
from typing import Dict, List, Tuple
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class FixValidator:
    """Проверка что исправления не сломали существующий функционал"""

    def __init__(self):
        self.checks = {
            'position_creation': self.check_position_creation,
            'stop_loss_placement': self.check_stop_loss_placement,
            'synchronization': self.check_synchronization,
            'race_conditions': self.check_race_conditions,
        }
        self.results = {}

    async def run_all_checks(self) -> Dict[str, bool]:
        """Запуск всех проверок"""
        for name, check_func in self.checks.items():
            try:
                self.results[name] = await check_func()
                logger.info(f"✅ Check {name}: {'PASSED' if self.results[name] else 'FAILED'}")
            except Exception as e:
                logger.error(f"❌ Check {name} error: {e}")
                self.results[name] = False

        return self.results

    async def check_position_creation(self) -> bool:
        """Проверка что позиции создаются корректно"""
        # TODO: Implement
        return True

    async def check_stop_loss_placement(self) -> bool:
        """Проверка что SL устанавливается"""
        # TODO: Implement
        return True

    async def check_synchronization(self) -> bool:
        """Проверка синхронизации с биржей"""
        # TODO: Implement
        return True

    async def check_race_conditions(self) -> bool:
        """Проверка на race conditions"""
        # TODO: Implement
        return True
```

**Git checkpoint:**
```bash
git add -A
git commit -m "🔒 [Step 0] Setup monitoring and test environment"
git push
git tag -a "checkpoint-0-setup" -m "Environment setup complete"
git push --tags
```

---

## 📝 ДЕТАЛЬНЫЙ ПЛАН ИСПРАВЛЕНИЙ

### 🔴 FIX #1: АТОМАРНОСТЬ ENTRY + STOP-LOSS [КРИТИЧНО]

#### Анализ проблемы:
- **Где:** `core/position_manager.py:573-722`
- **Проблема:** Entry и SL создаются отдельно без транзакции
- **Риск:** Позиция может остаться без защиты при сбое
- **Влияние:** PositionManager, StopLossManager, Repository

#### Исследование best practices:

```python
# research/atomicity_research.py
"""
Исследование реализации атомарности в других проектах
"""

# 1. Freqtrade approach - использует состояния
# https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/persistence/trade_model.py
# State: "pending_entry" -> "pending_sl" -> "active"

# 2. CCXT best practice - использует batch orders
# https://github.com/ccxt/ccxt/wiki/Manual#placing-orders
# exchange.create_orders([entry_order, sl_order])

# 3. Binance OCO (One-Cancels-Other)
# https://binance-docs.github.io/apidocs/spot/en/#new-oco-trade
# Позволяет создать entry и SL атомарно

# 4. Database transactions (PostgreSQL)
# BEGIN; INSERT position; INSERT stop_loss; COMMIT;
```

#### Решение с минимальным риском:

```python
# core/position_manager_atomic.py
"""
Атомарная версия открытия позиций
"""
import asyncio
from typing import Optional, Dict
from enum import Enum
from contextlib import asynccontextmanager

class PositionState(Enum):
    """Состояния позиции для атомарности"""
    PENDING_ENTRY = "pending_entry"
    ENTRY_PLACED = "entry_placed"
    PENDING_SL = "pending_sl"
    ACTIVE = "active"
    FAILED = "failed"

class AtomicPositionManager:
    """
    Менеджер с атомарным созданием позиций

    Approach: State machine + Database transactions + Recovery
    """

    @asynccontextmanager
    async def atomic_operation(self, operation_id: str):
        """Контекстный менеджер для атомарных операций"""
        tx = await self.repository.begin_transaction()
        try:
            # Создаем запись операции
            await tx.execute(
                "INSERT INTO atomic_operations (id, status, started_at) VALUES (%s, %s, NOW())",
                (operation_id, 'in_progress')
            )
            yield tx
            await tx.commit()
            await self.repository.execute(
                "UPDATE atomic_operations SET status = 'completed', completed_at = NOW() WHERE id = %s",
                (operation_id,)
            )
        except Exception as e:
            await tx.rollback()
            await self.repository.execute(
                "UPDATE atomic_operations SET status = 'failed', error = %s WHERE id = %s",
                (str(e), operation_id)
            )
            raise

    async def open_position_atomic(self, request: PositionRequest) -> Optional[Dict]:
        """
        Атомарное открытие позиции с гарантией SL

        Flow:
        1. Create position record with state=PENDING_ENTRY
        2. Place entry order on exchange
        3. Update state=ENTRY_PLACED
        4. Place SL order
        5. Update state=ACTIVE
        6. If any step fails - rollback and cleanup
        """
        operation_id = f"pos_{request.symbol}_{datetime.now().timestamp()}"

        async with self.atomic_operation(operation_id) as tx:
            try:
                # Step 1: Create position record with pending state
                position_id = await tx.execute(
                    """
                    INSERT INTO positions
                    (symbol, exchange, side, state, operation_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING id
                    """,
                    (request.symbol, request.exchange, request.side,
                     PositionState.PENDING_ENTRY.value, operation_id)
                )

                # Step 2: Place entry order
                entry_order = await self._place_entry_order(
                    request.symbol, request.side, request.quantity
                )

                # Step 3: Update with entry details
                await tx.execute(
                    """
                    UPDATE positions
                    SET state = %s, entry_order_id = %s, entry_price = %s
                    WHERE id = %s
                    """,
                    (PositionState.ENTRY_PLACED.value, entry_order.id,
                     entry_order.price, position_id)
                )

                # Step 4: Place stop loss WITH RETRY
                sl_placed = False
                for attempt in range(3):
                    try:
                        sl_order = await self._place_stop_loss_order(
                            request.symbol, request.side, request.quantity,
                            stop_price=self._calculate_sl_price(entry_order.price, request.side)
                        )
                        sl_placed = True
                        break
                    except Exception as e:
                        if attempt == 2:
                            # Last attempt failed - MUST cleanup
                            await self._emergency_close_position(entry_order)
                            raise Exception(f"Failed to place SL after 3 attempts: {e}")
                        await asyncio.sleep(2 ** attempt)

                # Step 5: Update to active
                await tx.execute(
                    """
                    UPDATE positions
                    SET state = %s, sl_order_id = %s, sl_price = %s
                    WHERE id = %s
                    """,
                    (PositionState.ACTIVE.value, sl_order.id,
                     sl_order.price, position_id)
                )

                return {
                    'position_id': position_id,
                    'entry_order': entry_order,
                    'sl_order': sl_order,
                    'state': PositionState.ACTIVE.value
                }

            except Exception as e:
                logger.error(f"Failed atomic position creation: {e}")
                # Rollback происходит автоматически в context manager
                raise

    async def recover_incomplete_positions(self):
        """
        Recovery механизм для незавершенных позиций при старте
        Запускается при инициализации бота
        """
        incomplete = await self.repository.fetch_all(
            """
            SELECT * FROM positions
            WHERE state IN (%s, %s, %s)
            AND created_at > NOW() - INTERVAL '1 hour'
            """,
            (PositionState.PENDING_ENTRY.value,
             PositionState.ENTRY_PLACED.value,
             PositionState.PENDING_SL.value)
        )

        for pos in incomplete:
            try:
                if pos['state'] == PositionState.PENDING_ENTRY.value:
                    # Entry не был размещен - можно безопасно удалить
                    await self.repository.execute(
                        "UPDATE positions SET state = %s WHERE id = %s",
                        (PositionState.FAILED.value, pos['id'])
                    )

                elif pos['state'] == PositionState.ENTRY_PLACED.value:
                    # Entry размещен, но нет SL - КРИТИЧНО!
                    await self._recover_position_without_sl(pos)

                elif pos['state'] == PositionState.PENDING_SL.value:
                    # В процессе установки SL - проверить и довершить
                    await self._complete_sl_placement(pos)

            except Exception as e:
                logger.error(f"Failed to recover position {pos['id']}: {e}")
```

#### Тесты для атомарности:

```python
# tests/test_atomic_position.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from core.position_manager_atomic import AtomicPositionManager, PositionState

class TestAtomicPosition:
    """Тесты атомарного создания позиций"""

    @pytest.mark.asyncio
    async def test_successful_atomic_creation(self):
        """Тест успешного атомарного создания"""
        manager = AtomicPositionManager()

        with patch.object(manager, '_place_entry_order') as mock_entry:
            mock_entry.return_value = Mock(id='entry_1', price=50000)

            with patch.object(manager, '_place_stop_loss_order') as mock_sl:
                mock_sl.return_value = Mock(id='sl_1', price=49000)

                result = await manager.open_position_atomic(
                    Mock(symbol='BTC/USDT', side='buy', quantity=0.001)
                )

                assert result['state'] == PositionState.ACTIVE.value
                assert mock_entry.called
                assert mock_sl.called

    @pytest.mark.asyncio
    async def test_rollback_on_sl_failure(self):
        """Тест отката при неудаче установки SL"""
        manager = AtomicPositionManager()

        with patch.object(manager, '_place_entry_order') as mock_entry:
            mock_entry.return_value = Mock(id='entry_1', price=50000)

            with patch.object(manager, '_place_stop_loss_order') as mock_sl:
                mock_sl.side_effect = Exception("SL placement failed")

                with patch.object(manager, '_emergency_close_position') as mock_close:
                    with pytest.raises(Exception) as exc:
                        await manager.open_position_atomic(
                            Mock(symbol='BTC/USDT', side='buy', quantity=0.001)
                        )

                    assert "Failed to place SL" in str(exc.value)
                    assert mock_close.called  # Позиция закрыта

    @pytest.mark.asyncio
    async def test_recovery_on_startup(self):
        """Тест восстановления незавершенных позиций"""
        manager = AtomicPositionManager()

        # Mock незавершенные позиции
        incomplete_positions = [
            {'id': 1, 'state': PositionState.PENDING_ENTRY.value},
            {'id': 2, 'state': PositionState.ENTRY_PLACED.value},
        ]

        with patch.object(manager.repository, 'fetch_all') as mock_fetch:
            mock_fetch.return_value = incomplete_positions

            with patch.object(manager, '_recover_position_without_sl') as mock_recover:
                await manager.recover_incomplete_positions()

                # Проверяем что recovery был вызван для позиции без SL
                mock_recover.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_position_creation(self):
        """Тест защиты от одновременного создания позиций"""
        manager = AtomicPositionManager()

        # Запускаем два одновременных создания для одного символа
        tasks = [
            manager.open_position_atomic(
                Mock(symbol='BTC/USDT', side='buy', quantity=0.001)
            )
            for _ in range(2)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Одна должна успешно создаться, вторая - получить ошибку
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        assert success_count == 1
```

#### Integration тест:

```python
# tests/integration/test_atomic_position_flow.py
import pytest
from datetime import datetime
import asyncio

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_atomic_flow_with_real_exchange():
    """
    Полный тест с реальным testnet
    """
    # Используем Binance Testnet
    exchange = ccxt.binance({
        'apiKey': 'testnet_key',
        'secret': 'testnet_secret',
        'options': {
            'defaultType': 'future',
            'test': True
        }
    })

    manager = AtomicPositionManager(exchange=exchange)

    # Тестовый запрос
    request = PositionRequest(
        symbol='BTC/USDT',
        side='buy',
        quantity=0.001,
        stop_loss_percent=2.0
    )

    # Создаем позицию
    result = await manager.open_position_atomic(request)

    # Проверки
    assert result['state'] == PositionState.ACTIVE.value

    # Проверяем на бирже
    positions = await exchange.fetch_positions()
    assert any(p['symbol'] == 'BTC/USDT' for p in positions)

    # Проверяем SL
    orders = await exchange.fetch_open_orders('BTC/USDT')
    sl_orders = [o for o in orders if o['type'] == 'stop_market']
    assert len(sl_orders) > 0

    # Cleanup
    await exchange.cancel_all_orders('BTC/USDT')
    await exchange.close_position('BTC/USDT')
```

**Git checkpoint:**
```bash
git add -A
git commit -m "🔒 [Fix #1] Implement atomic position creation with SL"
git push
git tag -a "checkpoint-1-atomicity" -m "Atomic position creation implemented"
git push --tags

# Тестирование
pytest tests/test_atomic_position.py -v
pytest tests/integration/test_atomic_position_flow.py -v --log-cli-level=INFO
```

---

### 🔴 FIX #2: ЗАЩИТА ОТ RACE CONDITIONS [КРИТИЧНО]

#### Проблема:
- position_locks это set, не настоящий lock
- Нет защиты concurrent SL updates
- SingleInstance недостаточно

#### Решение:

```python
# core/lock_manager.py
"""
Централизованный менеджер блокировок
"""
import asyncio
from typing import Dict, Optional
from contextlib import asynccontextmanager
import time

class LockManager:
    """
    Менеджер блокировок для предотвращения race conditions

    Features:
    - Async locks для каждой позиции
    - Deadlock detection
    - Lock timeout
    - Monitoring
    """

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_holders: Dict[str, str] = {}  # lock_key -> holder_id
        self._lock_times: Dict[str, float] = {}  # lock_key -> acquisition_time
        self._lock_creation = asyncio.Lock()

    @asynccontextmanager
    async def acquire_lock(self, resource: str, operation: str, timeout: float = 30.0):
        """
        Получение блокировки с timeout и monitoring

        Args:
            resource: Ресурс для блокировки (например, "position_BTC/USDT")
            operation: Название операции (для отладки)
            timeout: Максимальное время ожидания
        """
        lock_key = f"lock_{resource}"

        # Создаем lock если не существует (thread-safe)
        async with self._lock_creation:
            if lock_key not in self._locks:
                self._locks[lock_key] = asyncio.Lock()

        lock = self._locks[lock_key]
        holder_id = f"{operation}_{time.time()}"

        # Пытаемся получить lock с timeout
        try:
            await asyncio.wait_for(
                lock.acquire(),
                timeout=timeout
            )

            # Записываем информацию о владельце
            self._lock_holders[lock_key] = holder_id
            self._lock_times[lock_key] = time.time()

            logger.debug(f"🔒 Lock acquired: {resource} by {operation}")

            yield

        except asyncio.TimeoutError:
            current_holder = self._lock_holders.get(lock_key, 'unknown')
            hold_time = time.time() - self._lock_times.get(lock_key, 0)

            raise Exception(
                f"Lock timeout for {resource}. "
                f"Current holder: {current_holder}, "
                f"holding for {hold_time:.2f}s"
            )
        finally:
            if lock.locked() and self._lock_holders.get(lock_key) == holder_id:
                lock.release()
                del self._lock_holders[lock_key]
                del self._lock_times[lock_key]
                logger.debug(f"🔓 Lock released: {resource}")

    def get_lock_stats(self) -> Dict:
        """Получение статистики блокировок"""
        now = time.time()
        return {
            'total_locks': len(self._locks),
            'active_locks': len(self._lock_holders),
            'long_held_locks': [
                {
                    'resource': key.replace('lock_', ''),
                    'holder': holder,
                    'duration': now - self._lock_times[key]
                }
                for key, holder in self._lock_holders.items()
                if now - self._lock_times[key] > 10  # Держится больше 10 секунд
            ]
        }

# Singleton instance
lock_manager = LockManager()
```

#### Обновление PositionManager с правильными locks:

```python
# core/position_manager_safe.py
from core.lock_manager import lock_manager

class SafePositionManager:
    """Position Manager с защитой от race conditions"""

    async def open_position(self, request: PositionRequest) -> Optional[PositionState]:
        """Открытие позиции с защитой от race"""

        # Используем правильный lock
        async with lock_manager.acquire_lock(
            resource=f"position_{request.symbol}",
            operation="open_position"
        ):
            # Проверяем что позиция еще не создается/не существует
            if await self._position_exists(request.symbol, request.exchange):
                logger.warning(f"Position already exists for {request.symbol}")
                return None

            # Критическая секция - создание позиции
            return await self._create_position_internal(request)

    async def update_stop_loss(self, symbol: str, new_sl_price: float):
        """Обновление SL с защитой от concurrent updates"""

        async with lock_manager.acquire_lock(
            resource=f"sl_{symbol}",
            operation="update_sl"
        ):
            # Получаем текущий SL
            current_sl = await self._get_current_sl(symbol)

            # Проверяем что новый SL отличается
            if current_sl and abs(current_sl - new_sl_price) < 0.0001:
                logger.debug(f"SL already at {new_sl_price}, skipping update")
                return

            # Обновляем SL
            await self._update_sl_internal(symbol, new_sl_price)

    async def trailing_stop_check(self, symbol: str):
        """Проверка trailing stop с защитой"""

        # Два уровня блокировок для предотвращения deadlock
        async with lock_manager.acquire_lock(
            resource=f"trailing_{symbol}",
            operation="trailing_check",
            timeout=5.0  # Короткий timeout для частых проверок
        ):
            # Быстрая проверка условий
            should_update = await self._should_update_trailing(symbol)

            if should_update:
                # Получаем lock для обновления SL
                async with lock_manager.acquire_lock(
                    resource=f"sl_{symbol}",
                    operation="trailing_update"
                ):
                    await self._update_trailing_stop(symbol)
```

#### Тесты для race conditions:

```python
# tests/test_race_conditions.py
import asyncio
import pytest
from unittest.mock import Mock, patch

class TestRaceConditions:
    """Тесты защиты от race conditions"""

    @pytest.mark.asyncio
    async def test_concurrent_position_creation_prevented(self):
        """Тест что две позиции на один символ не создаются одновременно"""
        manager = SafePositionManager()

        async def try_create_position(idx: int):
            request = Mock(symbol='BTC/USDT', side='buy')
            try:
                result = await manager.open_position(request)
                return {'idx': idx, 'success': result is not None}
            except Exception as e:
                return {'idx': idx, 'error': str(e)}

        # Запускаем 5 одновременных попыток
        tasks = [try_create_position(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        # Только одна должна успешно создаться
        successful = [r for r in results if r.get('success')]
        assert len(successful) == 1

    @pytest.mark.asyncio
    async def test_concurrent_sl_updates_serialized(self):
        """Тест что обновления SL выполняются последовательно"""
        manager = SafePositionManager()
        update_times = []

        async def update_sl_tracking(symbol: str, price: float):
            start = asyncio.get_event_loop().time()
            await manager.update_stop_loss(symbol, price)
            end = asyncio.get_event_loop().time()
            update_times.append((start, end))

        # Запускаем 3 параллельных обновления
        tasks = [
            update_sl_tracking('BTC/USDT', 49000 + i*100)
            for i in range(3)
        ]
        await asyncio.gather(*tasks)

        # Проверяем что обновления не перекрываются
        for i in range(len(update_times) - 1):
            assert update_times[i][1] <= update_times[i+1][0], \
                "Updates should be serialized, not concurrent"

    @pytest.mark.asyncio
    async def test_lock_timeout_handling(self):
        """Тест обработки timeout при получении lock"""
        from core.lock_manager import lock_manager

        resource = "test_resource"

        # Первый захватывает lock и держит
        async def hold_lock():
            async with lock_manager.acquire_lock(resource, "holder"):
                await asyncio.sleep(10)  # Держим 10 секунд

        # Второй пытается получить с коротким timeout
        async def try_acquire():
            try:
                async with lock_manager.acquire_lock(resource, "waiter", timeout=1.0):
                    pass
            except Exception as e:
                return str(e)

        # Запускаем параллельно
        holder_task = asyncio.create_task(hold_lock())
        await asyncio.sleep(0.1)  # Даем время первому захватить lock

        error = await try_acquire()

        assert "Lock timeout" in error
        holder_task.cancel()

    @pytest.mark.asyncio
    async def test_deadlock_prevention(self):
        """Тест предотвращения deadlock"""
        from core.lock_manager import lock_manager

        deadlock_detected = False

        async def task1():
            async with lock_manager.acquire_lock("resource_A", "task1"):
                await asyncio.sleep(0.1)
                try:
                    async with lock_manager.acquire_lock("resource_B", "task1", timeout=1.0):
                        pass
                except Exception:
                    nonlocal deadlock_detected
                    deadlock_detected = True

        async def task2():
            async with lock_manager.acquire_lock("resource_B", "task2"):
                await asyncio.sleep(0.1)
                try:
                    async with lock_manager.acquire_lock("resource_A", "task2", timeout=1.0):
                        pass
                except Exception:
                    nonlocal deadlock_detected
                    deadlock_detected = True

        # Запускаем обе задачи
        await asyncio.gather(task1(), task2(), return_exceptions=True)

        # Хотя бы одна должна обнаружить deadlock
        assert deadlock_detected
```

#### Stress test:

```python
# tests/stress/test_concurrent_load.py
import asyncio
import random
import time

async def stress_test_concurrent_operations():
    """Stress test с множественными параллельными операциями"""

    manager = SafePositionManager()
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT']

    stats = {
        'positions_created': 0,
        'sl_updates': 0,
        'trailing_checks': 0,
        'errors': 0
    }

    async def random_operation():
        try:
            op_type = random.choice(['create', 'update_sl', 'trailing'])
            symbol = random.choice(symbols)

            if op_type == 'create':
                await manager.open_position(Mock(symbol=symbol))
                stats['positions_created'] += 1
            elif op_type == 'update_sl':
                await manager.update_stop_loss(symbol, random.uniform(40000, 50000))
                stats['sl_updates'] += 1
            else:
                await manager.trailing_stop_check(symbol)
                stats['trailing_checks'] += 1

        except Exception as e:
            stats['errors'] += 1

    # Запускаем 100 параллельных операций
    start = time.time()
    tasks = [random_operation() for _ in range(100)]
    await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start

    print(f"Stress test completed in {duration:.2f}s")
    print(f"Stats: {stats}")

    # Проверяем что система выдержала нагрузку
    assert stats['errors'] < 10  # Менее 10% ошибок
    assert duration < 30  # Выполнено за разумное время
```

**Git checkpoint:**
```bash
git add -A
git commit -m "🔒 [Fix #2] Implement proper lock management for race condition prevention"
git push
git tag -a "checkpoint-2-locks" -m "Lock management system implemented"
git push --tags

# Тестирование
pytest tests/test_race_conditions.py -v
pytest tests/stress/test_concurrent_load.py -v
```

---

### 🟡 FIX #3: DATABASE TRANSACTIONS И LOGGING

#### Реализация транзакций:

```python
# database/transactional_repository.py
"""
Repository с поддержкой транзакций
"""
from contextlib import asynccontextmanager
import asyncpg
from typing import Optional
import uuid

class TransactionalRepository:
    """Repository с ACID транзакциями"""

    def __init__(self, connection_pool):
        self.pool = connection_pool

    @asynccontextmanager
    async def transaction(self, isolation_level='read_committed'):
        """
        Контекстный менеджер для транзакций

        Usage:
            async with repo.transaction() as tx:
                await tx.execute("INSERT ...")
                await tx.execute("UPDATE ...")
                # Auto-commit on success, auto-rollback on exception
        """
        conn = await self.pool.acquire()
        tx = conn.transaction(isolation=isolation_level)
        tx_id = str(uuid.uuid4())

        try:
            await tx.start()

            # Log transaction start
            await conn.execute(
                """
                INSERT INTO transaction_log
                (id, started_at, status)
                VALUES ($1, NOW(), 'in_progress')
                """,
                tx_id
            )

            yield conn

            await tx.commit()

            # Log success
            await conn.execute(
                """
                UPDATE transaction_log
                SET completed_at = NOW(), status = 'committed'
                WHERE id = $1
                """,
                tx_id
            )

        except Exception as e:
            await tx.rollback()

            # Log failure
            await conn.execute(
                """
                UPDATE transaction_log
                SET completed_at = NOW(), status = 'rolled_back', error = $2
                WHERE id = $1
                """,
                tx_id, str(e)
            )
            raise
        finally:
            await self.pool.release(conn)
```

#### Добавление event logging:

```sql
-- migrations/add_event_logging.sql
-- Таблица для всех событий системы
CREATE TABLE IF NOT EXISTS trading.events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_subtype VARCHAR(50),
    entity_type VARCHAR(50),  -- 'position', 'order', 'signal', etc
    entity_id VARCHAR(100),

    -- Event data
    data JSONB NOT NULL,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(100),  -- module/function that created event

    -- Indexing
    INDEX idx_events_type (event_type),
    INDEX idx_events_entity (entity_type, entity_id),
    INDEX idx_events_created (created_at DESC),
    INDEX idx_events_data_gin (data) -- GIN index for JSONB queries
);

-- Таблица для транзакций
CREATE TABLE IF NOT EXISTS trading.transaction_log (
    id UUID PRIMARY KEY,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL, -- 'in_progress', 'committed', 'rolled_back'
    error TEXT,

    INDEX idx_tx_status (status),
    INDEX idx_tx_started (started_at DESC)
);

-- Таблица для lock событий
CREATE TABLE IF NOT EXISTS trading.lock_events (
    id BIGSERIAL PRIMARY KEY,
    resource VARCHAR(100) NOT NULL,
    operation VARCHAR(100) NOT NULL,
    action VARCHAR(20) NOT NULL, -- 'acquired', 'released', 'timeout', 'conflict'
    holder_id VARCHAR(100),
    wait_time_ms INTEGER,
    hold_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    INDEX idx_lock_resource (resource),
    INDEX idx_lock_action (action),
    INDEX idx_lock_created (created_at DESC)
);

-- Функция для автоматического логирования
CREATE OR REPLACE FUNCTION log_event(
    p_event_type VARCHAR,
    p_entity_type VARCHAR,
    p_entity_id VARCHAR,
    p_data JSONB
) RETURNS BIGINT AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    INSERT INTO trading.events (event_type, entity_type, entity_id, data)
    VALUES (p_event_type, p_entity_type, p_entity_id, p_data)
    RETURNING id INTO v_event_id;

    RETURN v_event_id;
END;
$$ LANGUAGE plpgsql;
```

#### Event logger:

```python
# core/event_logger.py
"""
Централизованный event logger
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
import asyncpg

class EventLogger:
    """Логирование всех событий в БД"""

    def __init__(self, db_pool):
        self.pool = db_pool

    async def log_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        data: Dict[str, Any],
        event_subtype: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> int:
        """
        Логирование события в БД

        Returns:
            Event ID
        """
        async with self.pool.acquire() as conn:
            event_id = await conn.fetchval(
                """
                INSERT INTO trading.events
                (event_type, event_subtype, entity_type, entity_id, data, created_by)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                event_type,
                event_subtype,
                entity_type,
                entity_id,
                json.dumps(data),
                created_by or self.__class__.__name__
            )
            return event_id

    async def log_position_created(self, position_id: str, details: Dict):
        """Логирование создания позиции"""
        return await self.log_event(
            event_type='POSITION_CREATED',
            entity_type='position',
            entity_id=position_id,
            data=details
        )

    async def log_sl_placed(self, position_id: str, sl_details: Dict):
        """Логирование установки SL"""
        return await self.log_event(
            event_type='STOP_LOSS_PLACED',
            entity_type='position',
            entity_id=position_id,
            data=sl_details
        )

    async def log_sl_updated(self, position_id: str, old_sl: float, new_sl: float, reason: str):
        """Логирование обновления SL"""
        return await self.log_event(
            event_type='STOP_LOSS_UPDATED',
            entity_type='position',
            entity_id=position_id,
            data={
                'old_sl': old_sl,
                'new_sl': new_sl,
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            }
        )

    async def log_sync_run(self, exchange: str, results: Dict):
        """Логирование синхронизации"""
        return await self.log_event(
            event_type='SYNC_COMPLETED',
            entity_type='sync',
            entity_id=f"sync_{exchange}_{datetime.now().timestamp()}",
            data=results
        )

    async def log_error(self, error_type: str, error_details: Dict):
        """Логирование ошибок"""
        return await self.log_event(
            event_type='ERROR',
            event_subtype=error_type,
            entity_type='system',
            entity_id='error',
            data=error_details
        )
```

#### Тесты для транзакций и логирования:

```python
# tests/test_transactions_logging.py
import pytest
import asyncpg
from database.transactional_repository import TransactionalRepository
from core.event_logger import EventLogger

class TestTransactionsAndLogging:
    """Тесты транзакций и логирования"""

    @pytest.mark.asyncio
    async def test_transaction_commit(self, db_pool):
        """Тест успешной транзакции"""
        repo = TransactionalRepository(db_pool)

        async with repo.transaction() as tx:
            # Создаем позицию
            position_id = await tx.fetchval(
                "INSERT INTO positions (symbol) VALUES ($1) RETURNING id",
                "BTC/USDT"
            )

            # Создаем SL
            await tx.execute(
                "INSERT INTO orders (position_id, type) VALUES ($1, $2)",
                position_id, "stop_loss"
            )

        # Проверяем что записи созданы
        async with db_pool.acquire() as conn:
            position = await conn.fetchrow(
                "SELECT * FROM positions WHERE id = $1", position_id
            )
            assert position is not None

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, db_pool):
        """Тест отката транзакции при ошибке"""
        repo = TransactionalRepository(db_pool)

        with pytest.raises(Exception):
            async with repo.transaction() as tx:
                position_id = await tx.fetchval(
                    "INSERT INTO positions (symbol) VALUES ($1) RETURNING id",
                    "BTC/USDT"
                )

                # Симулируем ошибку
                raise Exception("Simulated error")

        # Проверяем что записи откатились
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM positions WHERE symbol = $1",
                "BTC/USDT"
            )
            assert count == 0

    @pytest.mark.asyncio
    async def test_event_logging(self, db_pool):
        """Тест логирования событий"""
        logger = EventLogger(db_pool)

        # Логируем создание позиции
        event_id = await logger.log_position_created(
            position_id="pos_123",
            details={
                'symbol': 'BTC/USDT',
                'side': 'buy',
                'quantity': 0.001,
                'entry_price': 50000
            }
        )

        assert event_id > 0

        # Проверяем что событие записано
        async with db_pool.acquire() as conn:
            event = await conn.fetchrow(
                "SELECT * FROM trading.events WHERE id = $1",
                event_id
            )
            assert event['event_type'] == 'POSITION_CREATED'
            assert event['entity_id'] == 'pos_123'

    @pytest.mark.asyncio
    async def test_concurrent_logging(self, db_pool):
        """Тест параллельного логирования"""
        logger = EventLogger(db_pool)

        async def log_many_events():
            tasks = []
            for i in range(100):
                task = logger.log_event(
                    event_type='TEST_EVENT',
                    entity_type='test',
                    entity_id=f"test_{i}",
                    data={'index': i}
                )
                tasks.append(task)

            return await asyncio.gather(*tasks)

        event_ids = await log_many_events()

        # Все события должны быть записаны
        assert len(event_ids) == 100
        assert all(eid > 0 for eid in event_ids)
```

**Git checkpoint:**
```bash
git add -A
git commit -m "🔒 [Fix #3] Add database transactions and comprehensive event logging"
git push
git tag -a "checkpoint-3-transactions" -m "Transactions and logging implemented"
git push --tags

# Применяем миграции
psql trading_bot_test < migrations/add_event_logging.sql

# Тестирование
pytest tests/test_transactions_logging.py -v
```

---

## 📊 ВАЛИДАЦИЯ И МОНИТОРИНГ

### Создание системы валидации:

```python
# validation/fix_validator.py
"""
Валидация что все исправления работают корректно
"""
import asyncio
from typing import Dict, List
from datetime import datetime, timedelta

class FixValidator:
    """Проверка корректности всех исправлений"""

    async def validate_atomicity(self) -> bool:
        """Проверка атомарности Entry+SL"""
        # 1. Создаем тестовую позицию
        test_request = PositionRequest(
            symbol='TEST/USDT',
            side='buy',
            quantity=0.001
        )

        # 2. Симулируем сбой после Entry
        with patch('position_manager.place_sl_order') as mock_sl:
            mock_sl.side_effect = Exception("Simulated SL failure")

            try:
                await manager.open_position_atomic(test_request)
            except Exception:
                pass

        # 3. Проверяем что позиция откатилась
        positions = await repo.fetch_all(
            "SELECT * FROM positions WHERE symbol = $1",
            'TEST/USDT'
        )

        return len(positions) == 0  # Не должно быть позиции

    async def validate_no_race_conditions(self) -> bool:
        """Проверка отсутствия race conditions"""
        results = []

        # Запускаем 10 параллельных операций
        async def concurrent_operation(idx):
            try:
                await manager.update_stop_loss('BTC/USDT', 49000 + idx)
                return True
            except Exception:
                return False

        tasks = [concurrent_operation(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Все должны выполниться успешно (последовательно)
        return all(results)

    async def validate_logging_completeness(self) -> bool:
        """Проверка полноты логирования"""
        # Создаем позицию
        position = await manager.open_position_atomic(...)

        # Проверяем события в БД
        events = await repo.fetch_all(
            """
            SELECT event_type FROM trading.events
            WHERE entity_id = $1
            ORDER BY created_at
            """,
            position['position_id']
        )

        expected_events = [
            'POSITION_CREATED',
            'ENTRY_ORDER_PLACED',
            'STOP_LOSS_PLACED'
        ]

        actual_events = [e['event_type'] for e in events]

        return expected_events == actual_events[:3]

    async def run_full_validation(self) -> Dict[str, bool]:
        """Полная валидация всех исправлений"""
        results = {
            'atomicity': await self.validate_atomicity(),
            'race_conditions': await self.validate_no_race_conditions(),
            'logging': await self.validate_logging_completeness(),
        }

        all_passed = all(results.values())

        print("="*50)
        print("VALIDATION RESULTS")
        print("="*50)
        for check, passed in results.items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{check}: {status}")
        print("="*50)
        print(f"Overall: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")

        return results
```

### Performance monitoring:

```python
# monitoring/performance_monitor.py
"""
Мониторинг производительности после исправлений
"""
import time
import psutil
import asyncio

class PerformanceMonitor:
    """Мониторинг влияния исправлений на производительность"""

    def __init__(self):
        self.metrics = {
            'operation_times': [],
            'lock_wait_times': [],
            'db_query_times': [],
            'memory_usage': [],
            'cpu_usage': []
        }

    async def measure_operation_time(self, operation_name: str, func, *args, **kwargs):
        """Измерение времени выполнения операции"""
        start = time.time()
        result = await func(*args, **kwargs)
        duration = time.time() - start

        self.metrics['operation_times'].append({
            'operation': operation_name,
            'duration': duration,
            'timestamp': datetime.now()
        })

        if duration > 5.0:  # Предупреждение если операция медленная
            logger.warning(f"⚠️ Slow operation: {operation_name} took {duration:.2f}s")

        return result

    def get_performance_report(self) -> Dict:
        """Отчет о производительности"""
        avg_operation_time = np.mean([m['duration'] for m in self.metrics['operation_times']])
        max_operation_time = max([m['duration'] for m in self.metrics['operation_times']])

        return {
            'avg_operation_time': avg_operation_time,
            'max_operation_time': max_operation_time,
            'slow_operations': [
                m for m in self.metrics['operation_times']
                if m['duration'] > 5.0
            ],
            'memory_usage_mb': psutil.Process().memory_info().rss / 1024 / 1024,
            'cpu_percent': psutil.Process().cpu_percent()
        }
```

---

## 🔄 ROLLBACK СТРАТЕГИЯ

### Для каждого изменения:

```bash
# Быстрый rollback к checkpoint
rollback_to_checkpoint() {
    checkpoint=$1
    echo "Rolling back to checkpoint: $checkpoint"

    # 1. Сохраняем текущее состояние
    git stash

    # 2. Возвращаемся к checkpoint
    git checkout $checkpoint

    # 3. Создаем hotfix branch
    git checkout -b hotfix/rollback-$(date +%Y%m%d-%H%M%S)

    # 4. Восстанавливаем БД если нужно
    if [ -f "migrations/rollback_$checkpoint.sql" ]; then
        psql trading_bot < migrations/rollback_$checkpoint.sql
    fi

    echo "Rollback completed. Current branch: $(git branch --show-current)"
}

# Пример использования
rollback_to_checkpoint checkpoint-2-locks
```

### Rollback скрипты для БД:

```sql
-- migrations/rollback_checkpoint-3-transactions.sql
-- Откат изменений БД для checkpoint-3

DROP TABLE IF EXISTS trading.events CASCADE;
DROP TABLE IF EXISTS trading.transaction_log CASCADE;
DROP TABLE IF EXISTS trading.lock_events CASCADE;
DROP FUNCTION IF EXISTS log_event CASCADE;
```

---

## 🚀 ФИНАЛЬНОЕ ТЕСТИРОВАНИЕ

### Integration test suite:

```python
# tests/final_integration_test.py
"""
Финальный интеграционный тест всех исправлений
"""
import pytest
import asyncio
from datetime import datetime

@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_trading_flow_with_all_fixes():
    """
    Полный тест торгового цикла с всеми исправлениями
    """
    # 1. Инициализация с SingleInstance
    from utils.single_instance import SingleInstance
    app_lock = SingleInstance('trading_bot_test')

    # 2. Создание менеджеров
    from core.position_manager_atomic import AtomicPositionManager
    from core.lock_manager import lock_manager
    from core.event_logger import EventLogger

    manager = AtomicPositionManager()
    logger = EventLogger(db_pool)

    # 3. Тест атомарного создания позиции
    position = await manager.open_position_atomic(
        PositionRequest(
            symbol='BTC/USDT',
            side='buy',
            quantity=0.001
        )
    )

    assert position['state'] == 'active'

    # 4. Проверка логирования
    events = await db_pool.fetch(
        "SELECT * FROM trading.events WHERE entity_id = $1",
        position['position_id']
    )
    assert len(events) >= 3  # Created, Entry, SL

    # 5. Тест защиты от race conditions
    async def update_sl():
        async with lock_manager.acquire_lock(f"sl_{position['symbol']}", "test"):
            await asyncio.sleep(0.1)
            return True

    # Запускаем параллельно
    results = await asyncio.gather(
        update_sl(),
        update_sl(),
        return_exceptions=True
    )

    # Одна должна получить timeout
    assert any(isinstance(r, Exception) for r in results)

    # 6. Тест синхронизации
    from core.position_synchronizer import PositionSynchronizer
    sync = PositionSynchronizer(repo, exchanges)

    sync_results = await sync.synchronize_all_exchanges()
    assert 'error' not in sync_results

    # 7. Проверка recovery при рестарте
    await manager.recover_incomplete_positions()

    # 8. Cleanup
    await cleanup_test_data()

    print("✅ All integration tests passed!")
```

### Запуск полного тестирования:

```bash
# run_complete_tests.sh
#!/bin/bash

echo "Running complete test suite..."

# 1. Unit tests
echo "1. Running unit tests..."
pytest tests/unit -v --cov=core --cov-report=html

# 2. Integration tests
echo "2. Running integration tests..."
pytest tests/integration -v

# 3. Stress tests
echo "3. Running stress tests..."
pytest tests/stress -v

# 4. Validation
echo "4. Running validation..."
python -m validation.fix_validator

# 5. Performance check
echo "5. Checking performance..."
python -m monitoring.performance_monitor

echo "Complete test suite finished!"
```

---

## 📅 ПЛАН РАЗВЕРТЫВАНИЯ

### Поэтапное развертывание:

```yaml
# deployment/staged_rollout.yaml
stages:
  - name: "Stage 1: Test Environment"
    duration: "24 hours"
    config:
      environment: "testnet"
      monitoring: "enhanced"
      alerts: "all"
    validation:
      - "No critical errors"
      - "All positions have SL"
      - "No race condition errors"

  - name: "Stage 2: Limited Production"
    duration: "48 hours"
    config:
      environment: "production"
      position_limit: 5
      max_position_size: 0.001
      monitoring: "enhanced"
    validation:
      - "Success rate > 95%"
      - "No fund losses"
      - "Response time < 1s"

  - name: "Stage 3: Full Production"
    config:
      environment: "production"
      restrictions: "none"
      monitoring: "standard"
```

---

## 📝 КОНТРОЛЬНЫЙ ЧЕКЛИСТ

### Перед deployment:

- [ ] Все тесты проходят успешно
- [ ] Код review выполнен
- [ ] Документация обновлена
- [ ] Rollback план готов
- [ ] Monitoring настроен
- [ ] Alerts настроены
- [ ] Backup БД создан
- [ ] Performance метрики в норме

### После deployment:

- [ ] Мониторинг первые 24 часа
- [ ] Проверка логов каждый час
- [ ] Валидация что все позиции имеют SL
- [ ] Нет timeout или deadlock ошибок
- [ ] Performance не деградировала

---

## ЗАКЛЮЧЕНИЕ

Этот план обеспечивает:

1. **Безопасность** - каждое изменение тестируется и может быть откачено
2. **Контроль** - git checkpoints на каждом шаге
3. **Валидация** - автоматические тесты подтверждают исправления
4. **Мониторинг** - отслеживание влияния на производительность
5. **Восстановление** - быстрый rollback при проблемах

**ВАЖНО:** Выполнять исправления последовательно, не пропуская тестирование!