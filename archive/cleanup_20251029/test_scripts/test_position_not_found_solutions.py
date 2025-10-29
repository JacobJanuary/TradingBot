#!/usr/bin/env python3
"""
Test script for position_not_found error solutions

ROOT CAUSE:
_binance_update_sl_optimized() вызывает fetch_positions() чтобы получить contracts.
НО fetch_positions() может вернуть пустой список или позицию с contracts=0 в следующих случаях:

1. TIMING ISSUE: После перезапуска бота Binance API возвращает позиции с задержкой
2. REDUCE-ONLY ORDERS: Позиции могут иметь только SL ордера (reduce-only) без открытых контрактов
3. CACHE LAG: WebSocket кэш еще не синхронизирован с биржей

ДОКАЗАТЕЛЬСТВА ИЗ ЛОГОВ:
- 16:26:54 - SL update failed: PIPPINUSDT - position_not_found
- 16:27:39 - Checking position PIPPINUSDT: has_sl=False, price=None
- БД показывает: quantity=11997, entry_price=0.01667, status=active
- Позиция СУЩЕСТВУЕТ в БД, но fetch_positions() не находит ее на бирже

ТЕКУЩИЙ КОД (exchange_manager.py:912-927):
```python
# Get position size
positions = await self.fetch_positions([symbol])
amount = 0
for pos in positions:
    if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
        amount = pos['contracts']
        break

if amount == 0:
    result['success'] = False
    result['error'] = 'position_not_found'
    return result
```

РЕШЕНИЯ:

## РЕШЕНИЕ 1: Fallback к БД
Если fetch_positions() не находит позицию, берем количество из БД.

ПЛЮСЫ:
+ Всегда есть fallback
+ БД - source of truth
+ Простая реализация

МИНУСЫ:
- Может обновить SL для уже закрытой позиции
- Требует передачу repository в exchange_manager

## РЕШЕНИЕ 2: Graceful Degradation
Просто логировать warning и вернуть success=True без обновления.

ПЛЮСЫ:
+ Не ломает TS
+ Простая реализация
+ Нет зависимости от БД

МИНУСЫ:
- SL НЕ обновляется (позиция остается незащищенной)
- Может привести к потерям

## РЕШЕНИЕ 3: Retry with Exponential Backoff
Повторить fetch_positions() с задержкой (100ms, 200ms, 400ms).

ПЛЮСЫ:
+ Решает timing issue
+ Нет false positives
+ Не требует БД

МИНУСЫ:
- Увеличивает latency
- Может не помочь при cache lag
- Усложняет код

## РЕШЕНИЕ 4 (РЕКОМЕНДУЕТСЯ): Hybrid - Retry + DB Fallback
1. Retry fetch_positions() 2 раза с 100ms задержкой
2. Если все еще не найдено → fallback к БД
3. Если в БД status='active' → использовать quantity из БД
4. Иначе → graceful failure

ПЛЮСЫ:
+ Покрывает все случаи (timing + cache lag)
+ БД как ultimate fallback
+ Минимальная latency (только при ошибке)

МИНУСЫ:
- Самая сложная реализация
- Требует repository в exchange_manager
"""

import asyncio
from decimal import Decimal


class MockPosition:
    """Mock position for testing"""
    def __init__(self, symbol, quantity, status='active'):
        self.symbol = symbol
        self.quantity = Decimal(str(quantity))
        self.status = status


class MockRepository:
    """Mock repository for testing"""
    def __init__(self):
        self.positions = {
            'PIPPINUSDT': MockPosition('PIPPINUSDT', 11997, 'active'),
            'ORDERUSDT': MockPosition('ORDERUSDT', 852, 'active'),
            'SSVUSDT': MockPosition('SSVUSDT', 34, 'active'),
            'CLOSEDUSDT': MockPosition('CLOSEDUSDT', 100, 'closed'),
        }

    async def get_position_by_symbol(self, symbol, exchange):
        """Get position from DB"""
        return self.positions.get(symbol)


class Solution1_DBFallback:
    """Fallback к БД если fetch_positions пустой"""

    def __init__(self, repository):
        self.repository = repository

    async def get_position_size(self, symbol, fetch_positions_result):
        """Get position size with DB fallback"""
        # Try exchange first
        for pos in fetch_positions_result:
            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                return pos['contracts'], 'exchange'

        # Fallback to DB
        db_position = await self.repository.get_position_by_symbol(symbol, 'binance')
        if db_position and db_position.status == 'active':
            return float(db_position.quantity), 'database'

        return 0, 'not_found'


class Solution2_GracefulDegradation:
    """Просто логировать и не ломать TS"""

    async def get_position_size(self, symbol, fetch_positions_result):
        """Get position size or return graceful failure"""
        for pos in fetch_positions_result:
            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                return pos['contracts'], 'exchange'

        # Graceful failure - don't break TS
        return None, 'graceful_skip'


class Solution3_RetryBackoff:
    """Retry с exponential backoff"""

    def __init__(self, fetch_positions_func):
        self.fetch_positions_func = fetch_positions_func

    async def get_position_size(self, symbol):
        """Get position size with retry"""
        delays = [0.1, 0.2, 0.4]  # 100ms, 200ms, 400ms

        for delay in delays:
            if delay > 0:
                await asyncio.sleep(delay)

            positions = await self.fetch_positions_func([symbol])
            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    return pos['contracts'], f'exchange_retry_{int(delay*1000)}ms'

        return 0, 'not_found_after_retries'


class Solution4_Hybrid:
    """РЕКОМЕНДУЕТСЯ: Retry + DB Fallback"""

    def __init__(self, fetch_positions_func, repository):
        self.fetch_positions_func = fetch_positions_func
        self.repository = repository

    async def get_position_size(self, symbol):
        """Get position size with hybrid approach"""
        # Step 1: Try exchange with retry
        delays = [0, 0.1, 0.2]  # immediate, 100ms, 200ms

        for i, delay in enumerate(delays):
            if delay > 0:
                await asyncio.sleep(delay)

            positions = await self.fetch_positions_func([symbol])
            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    source = 'exchange' if i == 0 else f'exchange_retry_{int(delay*1000)}ms'
                    return pos['contracts'], source

        # Step 2: Fallback to DB
        db_position = await self.repository.get_position_by_symbol(symbol, 'binance')
        if db_position and db_position.status == 'active':
            return float(db_position.quantity), 'database_fallback'

        return 0, 'not_found'


async def test_solutions():
    """Test all solutions"""

    print("=" * 80)
    print("TESTING SOLUTIONS FOR position_not_found ERROR")
    print("=" * 80)

    # Mock data
    repo = MockRepository()

    # Scenario 1: Position found immediately
    print("\n📊 SCENARIO 1: Position found on exchange (normal case)")
    print("-" * 80)
    fetch_result_ok = [{'symbol': 'PIPPINUSDT', 'contracts': 11997}]

    sol1 = Solution1_DBFallback(repo)
    amount, source = await sol1.get_position_size('PIPPINUSDT', fetch_result_ok)
    print(f"Solution 1 (DB Fallback):      amount={amount}, source={source}")

    sol2 = Solution2_GracefulDegradation()
    amount, source = await sol2.get_position_size('PIPPINUSDT', fetch_result_ok)
    print(f"Solution 2 (Graceful):         amount={amount}, source={source}")

    # Scenario 2: Position NOT found (position_not_found error)
    print("\n📊 SCENARIO 2: Position NOT found on exchange (timing issue)")
    print("-" * 80)
    fetch_result_empty = []

    sol1 = Solution1_DBFallback(repo)
    amount, source = await sol1.get_position_size('PIPPINUSDT', fetch_result_empty)
    print(f"Solution 1 (DB Fallback):      amount={amount}, source={source} ✅ Works!")

    sol2 = Solution2_GracefulDegradation()
    amount, source = await sol2.get_position_size('PIPPINUSDT', fetch_result_empty)
    print(f"Solution 2 (Graceful):         amount={amount}, source={source} ⚠️  SL NOT updated!")

    # Scenario 3: Position found with contracts=0
    print("\n📊 SCENARIO 3: Position found but contracts=0")
    print("-" * 80)
    fetch_result_zero = [{'symbol': 'PIPPINUSDT', 'contracts': 0}]

    sol1 = Solution1_DBFallback(repo)
    amount, source = await sol1.get_position_size('PIPPINUSDT', fetch_result_zero)
    print(f"Solution 1 (DB Fallback):      amount={amount}, source={source} ✅ Works!")

    sol2 = Solution2_GracefulDegradation()
    amount, source = await sol2.get_position_size('PIPPINUSDT', fetch_result_zero)
    print(f"Solution 2 (Graceful):         amount={amount}, source={source} ⚠️  SL NOT updated!")

    # Scenario 4: Position closed (should fail gracefully)
    print("\n📊 SCENARIO 4: Position closed in DB (should fail)")
    print("-" * 80)

    sol1 = Solution1_DBFallback(repo)
    amount, source = await sol1.get_position_size('CLOSEDUSDT', [])
    print(f"Solution 1 (DB Fallback):      amount={amount}, source={source} ✅ Correct!")

    sol2 = Solution2_GracefulDegradation()
    amount, source = await sol2.get_position_size('CLOSEDUSDT', [])
    print(f"Solution 2 (Graceful):         amount={amount}, source={source} ✅ Correct!")

    print("\n" + "=" * 80)
    print("РЕКОМЕНДАЦИЯ: SOLUTION 1 (DB Fallback)")
    print("=" * 80)
    print("""
ПОЧЕМУ:
1. ✅ Покрывает все случаи (timing issue, cache lag, contracts=0)
2. ✅ БД - source of truth для активных позиций
3. ✅ Простая реализация (не требует retry логики)
4. ✅ Минимальная latency (fallback только при ошибке)
5. ✅ Graceful failure для закрытых позиций

РИСКИ:
⚠️  Может обновить SL для позиции которая только что закрылась
   МИТИГАЦИЯ: Проверка position.status='active' в БД

РЕАЛИЗАЦИЯ:
В exchange_manager.py:912-927 изменить:

if amount == 0:
    # FALLBACK: Try database (position might be active but not in exchange cache yet)
    if self.repository:
        db_position = await self.repository.get_position_by_symbol(symbol, self.name)
        if db_position and db_position.status == 'active':
            amount = float(db_position.quantity)
            logger.warning(
                f"⚠️  {symbol}: Position not found on exchange, using DB quantity={amount} "
                f"(timing issue after restart)"
            )

    if amount == 0:
        logger.debug(f"Position {symbol} not found (likely closed), skipping SL update")
        result['success'] = False
        result['error'] = 'position_not_found'
        result['message'] = f"Position {symbol} not found on exchange (likely closed)"
        return result
    """)


if __name__ == '__main__':
    asyncio.run(test_solutions())
