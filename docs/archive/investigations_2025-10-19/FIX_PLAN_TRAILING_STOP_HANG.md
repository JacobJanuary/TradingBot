# 🔧 ПЛАН ИСПРАВЛЕНИЯ: Зависание Trailing Stop

**Дата:** 2025-10-19
**Статус:** 📋 ГОТОВ К ВЫПОЛНЕНИЮ
**Приоритет:** 🔴 P0 - КРИТИЧЕСКИЙ

---

## 📊 КРАТКОЕ СОДЕРЖАНИЕ

**Проблема:** Волна зависает после открытия 1 позиции из-за бесконечного ожидания в `get_open_positions()`

**Корневая причина:** DB запрос без таймаута в `repository.py:460`

**Решение:** Двухфазное исправление - немедленный таймаут + корректировка корневой причины

---

## 🎯 ФАЗА 1: НЕМЕДЛЕННОЕ ИСПРАВЛЕНИЕ (15 минут)

### Цель
Предотвратить блокировку обработки волны, если `create_trailing_stop()` зависнет.

### Изменения

**Файл:** `core/position_manager.py:1016-1022`

**БЫЛО:**
```python
trailing_manager = self.trailing_managers.get(exchange_name)
if trailing_manager:
    await trailing_manager.create_trailing_stop(
        symbol=symbol,
        side=position.side,
        entry_price=position.entry_price,
        quantity=position.quantity,
        initial_stop=None  # Не создавать SL сразу - ждать активации
    )
    position.has_trailing_stop = True
```

**СТАНЕТ:**
```python
trailing_manager = self.trailing_managers.get(exchange_name)
if trailing_manager:
    try:
        await asyncio.wait_for(
            trailing_manager.create_trailing_stop(
                symbol=symbol,
                side=position.side,
                entry_price=position.entry_price,
                quantity=position.quantity,
                initial_stop=None  # Не создавать SL сразу - ждать активации
            ),
            timeout=5.0  # 5 секунд максимум на создание trailing stop
        )
        position.has_trailing_stop = True
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Trailing stop creation timed out for {symbol} after 5s")
        logger.warning(f"⚠️ Position {symbol} opened WITHOUT trailing stop (manual setup needed)")
        position.has_trailing_stop = False
        # НЕ прерываем - позиция уже открыта с protection SL
```

**Также добавить импорт в начало файла:**
```python
import asyncio  # Если еще не импортирован
```

### Обоснование

1. ✅ **Не ломает существующую логику** - позиция уже открыта с SL
2. ✅ **Предотвращает зависание** - через 5s продолжается обработка
3. ✅ **Сохраняет защиту** - Protection SL уже установлен StopLossManager
4. ✅ **Минимальные изменения** - 10 строк кода
5. ✅ **Откатывается легко** - просто убрать try/except

### Риски

- 🟡 **СРЕДНИЙ**: Trailing stop может не создаться → позиция без автоматического трейлинга
- **Митигация**: Protection SL остается активным, позиция защищена
- **Мониторинг**: Логи покажут "timed out" → ручная проверка

### Тестирование

**После применения:**
1. Мониторим следующую волну
2. Проверяем логи на "⏱️ Trailing stop creation timed out"
3. Проверяем что ВСЕ 6 сигналов обрабатываются
4. Проверяем что позиции открываются с Protection SL

**Ожидаемый результат:**
- Волна обрабатывает все 6 сигналов
- Если таймаут - видим предупреждение в логах
- Позиции защищены Protection SL

---

## 🎯 ФАЗА 2: КОРРЕКТИРОВКА КОРНЕВОЙ ПРИЧИНЫ (30 минут)

### Цель
Исправить отсутствие таймаута в `get_open_positions()` и других DB запросах.

### Изменения

**Файл:** `database/repository.py:448-462`

**БЫЛО:**
```python
async def get_open_positions(self) -> List[Dict]:
    """Get all open positions from database"""
    query = """
        SELECT id, symbol, exchange, side, entry_price, current_price,
               quantity, leverage, stop_loss, take_profit,
               status, pnl, pnl_percentage, trailing_activated,
               has_trailing_stop, created_at, updated_at
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY created_at DESC
    """

    async with self.pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]
```

**СТАНЕТ:**
```python
async def get_open_positions(self, timeout: float = 3.0) -> List[Dict]:
    """
    Get all open positions from database

    Args:
        timeout: Maximum time to wait for query (seconds)

    Returns:
        List of position dicts, or empty list if timeout
    """
    query = """
        SELECT id, symbol, exchange, side, entry_price, current_price,
               quantity, leverage, stop_loss, take_profit,
               status, pnl, pnl_percentage, trailing_activated,
               has_trailing_stop, created_at, updated_at
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY created_at DESC
    """

    try:
        async with asyncio.timeout(timeout):
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [dict(row) for row in rows]
    except asyncio.TimeoutError:
        logger.error(f"⏱️ get_open_positions() timed out after {timeout}s")
        return []  # Возвращаем пустой список вместо зависания
    except Exception as e:
        logger.error(f"❌ Error in get_open_positions(): {e}")
        return []
```

**Также добавить импорт в начало файла:**
```python
import asyncio  # Если еще не импортирован
```

### Дополнительные Проверки

Проверить ВСЕ методы в `repository.py` на наличие таймаутов:

**Критические методы БЕЗ таймаутов:**
```bash
grep -n "async with self.pool.acquire()" database/repository.py
```

**Добавить таймауты в:**
1. `create_position()` - критично для atomic operations
2. `update_position()` - используется часто
3. `get_position_by_id()` - может зависнуть
4. `save_trailing_stop_state()` - корневая причина!

### Обоснование

1. ✅ **Исправляет корневую причину** - DB запросы не зависают навсегда
2. ✅ **Graceful degradation** - возвращаем [] вместо зависания
3. ✅ **Применимо широко** - все DB запросы станут безопаснее
4. ✅ **Настраиваемый таймаут** - можно увеличить если нужно

### Риски

- 🟡 **СРЕДНИЙ**: Если DB действительно медленная, запросы будут таймаутиться
- **Митигация**: Таймаут 3s достаточно щедрый (обычно <100ms)
- **Мониторинг**: Логи покажут если таймауты частые → проблема с DB

### Тестирование

**После применения:**
1. Прогнать 5-10 волн
2. Проверить логи на "⏱️ get_open_positions() timed out"
3. Проверить что trailing stops создаются нормально
4. Профилировать время выполнения DB запросов

**Ожидаемый результат:**
- Нет таймаутов в нормальных условиях
- Если DB зависла - graceful fallback вместо блокировки

---

## 🎯 ФАЗА 3: ОПТИМИЗАЦИЯ (ОПЦИОНАЛЬНО, 1 час)

### Цель
Уменьшить latency от `can_open_position()` чтобы вернуть скорость волны.

### Вариант A: Кэширование

**Идея:** Кэшировать результаты `fetch_positions()` на время волны

**Файл:** `core/exchange_manager.py`

```python
class ExchangeManager:
    def __init__(self, ...):
        ...
        self._positions_cache = None
        self._positions_cache_time = 0
        self._positions_cache_ttl = 10  # 10 секунд

    async def can_open_position(self, symbol: str, notional_usd: float) -> Tuple[bool, str]:
        # Step 1: Check free balance
        balance = await self.exchange.fetch_balance()
        free_usdt = float(balance.get('USDT', {}).get('free', 0) or 0)

        # Step 2: Get total current notional (С КЭШЕМ!)
        now = time.time()
        if self._positions_cache is None or (now - self._positions_cache_time) > self._positions_cache_ttl:
            self._positions_cache = await self.exchange.fetch_positions()
            self._positions_cache_time = now

        positions = self._positions_cache
        total_notional = sum(abs(float(p.get('notional', 0)))
                            for p in positions if float(p.get('contracts', 0)) > 0)
        ...
```

**Выгода:**
- Убирает 1 API вызов (fetch_positions) для 2-6 сигналов волны
- Экономия: ~1s × 5 = ~5s на волну

**Риск:**
- Устаревшие данные (TTL=10s)
- Может не учесть позиции открытые в этой же волне

---

### Вариант B: Батчинг Валидации

**Идея:** Проверить ВСЕ сигналы волны за один раз, а не по одному

**Изменения:**
1. Добавить метод `can_open_positions_batch(symbols, sizes)`
2. Сделать один `fetch_positions()` для всей волны
3. Проверить каждый символ против общего баланса

**Выгода:**
- 1 API вызов вместо 6
- Экономия: ~5s на волну

**Риск:**
- Более сложная логика
- Нужно учитывать последовательность открытия

---

### Вариант C: Асинхронная Валидация

**Идея:** Запустить `can_open_position()` для всех сигналов параллельно

**Код:**
```python
# В signal_processor_websocket.py
validations = await asyncio.gather(
    *[exchange.can_open_position(s.symbol, s.size) for s in signals]
)
```

**Выгода:**
- 3 API вызова параллельно вместо последовательно
- Экономия: ~1.5s × 5 = ~7.5s

**Риск:**
- Rate limit от Binance
- Сложнее отлаживать

---

## 📋 ЧЕКЛИСТ ВЫПОЛНЕНИЯ

### Фаза 1: Немедленное Исправление

- [ ] Прочитать текущий `position_manager.py:1016-1033`
- [ ] Добавить `import asyncio` если нужно
- [ ] Обернуть `create_trailing_stop()` в `asyncio.wait_for()`
- [ ] Добавить обработку `TimeoutError`
- [ ] Добавить логирование таймаута
- [ ] Установить `has_trailing_stop = False` при таймауте
- [ ] Запустить тесты
- [ ] Commit: "fix: add timeout to prevent trailing stop hang"
- [ ] Мониторить следующую волну

### Фаза 2: Корректировка Корневой Причины

- [ ] Прочитать текущий `repository.py:448-462`
- [ ] Добавить параметр `timeout` в сигнатуру
- [ ] Обернуть запрос в `asyncio.timeout()`
- [ ] Добавить обработку `TimeoutError`
- [ ] Вернуть `[]` при таймауте
- [ ] Проверить другие методы на таймауты
- [ ] Добавить таймауты в `save_trailing_stop_state()`
- [ ] Запустить тесты
- [ ] Commit: "fix: add timeout to all critical DB queries"
- [ ] Мониторить 5-10 волн

### Фаза 3: Оптимизация (Опционально)

- [ ] Профилировать время выполнения `can_open_position()`
- [ ] Решить какой вариант оптимизации (A/B/C)
- [ ] Реализовать выбранный вариант
- [ ] Протестировать на 10+ волнах
- [ ] Измерить улучшение latency
- [ ] Commit: "perf: optimize can_open_position() with caching"

---

## 🧪 ТЕСТИРОВАНИЕ

### Тест 1: Подтверждение Проблемы

**Скрипт:** `scripts/test_trailing_stop_hang.py`

```python
#!/usr/bin/env python3
"""
Тест: воспроизвести зависание trailing stop
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from database.repository import Repository

async def test_get_open_positions_hang():
    """Проверить зависает ли get_open_positions()"""
    config = Config()
    repo = Repository(config.database)
    await repo.connect()

    print("Testing get_open_positions() with no timeout...")
    start = asyncio.get_event_loop().time()

    try:
        positions = await asyncio.wait_for(
            repo.get_open_positions(),
            timeout=5.0
        )
        elapsed = asyncio.get_event_loop().time() - start
        print(f"✅ SUCCESS: Got {len(positions)} positions in {elapsed:.2f}s")
    except asyncio.TimeoutError:
        elapsed = asyncio.get_event_loop().time() - start
        print(f"❌ TIMEOUT: get_open_positions() hung for {elapsed:.2f}s")
        print("🔍 This confirms the hang issue!")

    await repo.close()

if __name__ == '__main__':
    asyncio.run(test_get_open_positions_hang())
```

**Запуск:**
```bash
python3 scripts/test_trailing_stop_hang.py
```

**Ожидаемый результат:**
- Если ✅ SUCCESS - проблема не воспроизводится (DB быстрая)
- Если ❌ TIMEOUT - проблема подтверждена

---

### Тест 2: Проверка Фикса

**После Фазы 1:**
```bash
# Запустить бота
python3 main.py

# Дождаться следующей волны
# Проверить логи:
grep "Executing signal" logs/trading_bot.log | tail -20
grep "executed successfully" logs/trading_bot.log | tail -20
grep "Trailing stop creation timed out" logs/trading_bot.log | tail -5
```

**Ожидаемый результат:**
- Видим "Executing signal 1/6", "2/6", ..., "6/6"
- Видим "executed successfully" для КАЖДОГО сигнала
- Может быть "Trailing stop creation timed out" для некоторых

---

### Тест 3: Проверка Корректировки

**После Фазы 2:**
```bash
# Запустить тестовый скрипт снова
python3 scripts/test_trailing_stop_hang.py

# Должно быть:
# ✅ SUCCESS или ❌ TIMEOUT (но с graceful fallback)
```

---

## 📊 КРИТЕРИИ УСПЕХА

### Фаза 1

✅ **Успех если:**
- Все 6 сигналов волны обрабатываются
- Логи показывают "executed successfully" для каждого
- Нет блокировки после 1-й позиции

⚠️ **Приемлемо если:**
- Некоторые позиции без trailing stop (таймаут)
- Но все позиции открыты с Protection SL

❌ **Провал если:**
- Все еще только 1/6 позиций открывается
- Волна зависает

### Фаза 2

✅ **Успех если:**
- Нет таймаутов в логах "get_open_positions() timed out"
- Trailing stops создаются для всех позиций
- DB запросы < 100ms в среднем

⚠️ **Приемлемо если:**
- Редкие таймауты (<5% волн)
- Graceful fallback работает

❌ **Провал если:**
- Частые таймауты (>20% волн)
- Проблемы с производительностью DB

---

## 🔄 ПЛАН ОТКАТА

### Откат Фазы 1

```bash
git revert <commit_hash>
# Или просто убрать try/except блок
```

**Когда откатывать:**
- Если таймауты слишком агрессивны (все позиции без TS)
- Если появились новые ошибки

### Откат Фазы 2

```bash
git revert <commit_hash>
# Или убрать asyncio.timeout() обертки
```

**Когда откатывать:**
- Если DB запросы начали массово таймаутиться
- Если trailing stops перестали создаваться

---

## 📝 COMMIT MESSAGES

### Commit 1: Фаза 1

```
fix: add timeout to prevent trailing stop hang

Problem:
- Wave processing hangs after 1st position
- create_trailing_stop() blocks indefinitely
- Caused by get_open_positions() DB query without timeout

Solution:
- Wrap create_trailing_stop() in asyncio.wait_for()
- 5 second timeout to prevent indefinite blocking
- Position opens WITH protection SL even if TS times out
- Allows wave to continue processing all signals

Changes:
- core/position_manager.py:1016-1033
- Add timeout wrapper with error handling
- Log timeout events for monitoring

Impact:
- Wave processes all 6 signals instead of 1
- Some positions may lack trailing stop (manual setup needed)
- Protection SL remains active

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Commit 2: Фаза 2

```
fix: add timeout to all critical DB queries

Problem:
- DB queries can hang indefinitely
- No timeout on pool.acquire() or conn.fetch()
- Causes blocking in async context

Root Cause:
- repository.py methods lack timeout protection
- Especially: get_open_positions(), save_trailing_stop_state()
- Discovered in trailing_stop.py:_save_state()

Solution:
- Add timeout parameter (default 3s) to DB methods
- Wrap queries in asyncio.timeout()
- Return empty results on timeout (graceful degradation)
- Log timeout events for monitoring

Changes:
- database/repository.py:448-462 (get_open_positions)
- database/repository.py: other critical methods
- Add timeout to all pool.acquire() calls

Impact:
- No more indefinite hangs
- Graceful degradation if DB slow
- Better observability with timeout logs

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## 🚀 ГОТОВНОСТЬ К ВЫПОЛНЕНИЮ

**Статус:** 🟢 ГОТОВ К ВНЕДРЕНИЮ

**Рекомендация:**
1. Применить Фазу 1 НЕМЕДЛЕННО
2. Мониторить 2-3 волны
3. Если успешно → применить Фазу 2
4. Мониторить 10 волн
5. Если успешно → рассмотреть Фазу 3

**Оценка времени:**
- Фаза 1: 15 минут код + 30 минут тест = 45 минут
- Фаза 2: 30 минут код + 2 часа тест = 2.5 часа
- Фаза 3: 1 час код + 3 часа тест = 4 часа
- **ИТОГО:** ~7 часов с тестированием

**Риск:** 🟡 СРЕДНИЙ (Фаза 1) + 🟡 СРЕДНИЙ (Фаза 2) = 🟡 СРЕДНИЙ ОБЩИЙ

---

**План Создан:** 2025-10-19 10:40 UTC
**Статус:** ГОТОВ К ВЫПОЛНЕНИЮ
**Следующее Действие:** Запросить одобрение пользователя для Фазы 1
