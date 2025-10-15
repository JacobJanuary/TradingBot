# 🚨 КРИТИЧЕСКИЙ БАГ: Исправление дублирования волн НЕ СРАБОТАЛО

## Факты

### Волна 03:20 (23:21 UTC) - Ожидалось 4 позиции, получено 7 (3 дубликата)

| ID  | Symbol  | Signal ID | Открыто (UTC)       | Разница | Статус  | Exit Reason  |
|-----|---------|-----------|---------------------|---------|---------|--------------|
| 275 | KASUSDT | 12330417  | 23:21:12.819456     | -       | closed  | sync_cleanup |
| 276 | KASUSDT | 12330417  | 23:21:12.853998     | **34ms** | closed  | sync_cleanup |
| 277 | BIDUSDT | 12330424  | 23:21:17.749808     | -       | **active** | -         |
| 278 | BIDUSDT | 12330424  | 23:21:18.057063     | **307ms** | **active** | -       |
| 279 | SKYUSDT | 12330439  | 23:21:22.884992     | -       | closed  | sync_cleanup |
| 280 | SKYUSDT | 12330439  | 23:21:23.031290     | **146ms** | closed  | sync_cleanup |

**Недостающая позиция**: AKEUSDT (должна была быть открыта, но в БД нет записи)

## Выводы

1. ✅ **Fix #1 (atomic wave protection)** - Возможно работает (волна обработалась один раз)
2. ❌ **Fix #2 (position check locks)** - **НЕ РАБОТАЕТ!** Дубликаты создаются с разницей 34-307ms

## Корневая причина (Root Cause Analysis)

### Баг в `core/position_manager.py:589-594`

```python
# ТЕКУЩИЙ КОД (БАГОВАННЫЙ):
lock_key = f"{exchange_name}_{symbol}"
if lock_key in self.position_locks:  # ❌ НЕ THREAD-SAFE!
    logger.warning(f"Position already being processed for {symbol}")
    return None

self.position_locks.add(lock_key)  # ❌ RACE CONDITION!
```

**Проблема**: Используется простой `set` вместо `asyncio.Lock`

**Почему это не работает**:
1. Task A проверяет: `lock_key not in self.position_locks` → True
2. Task B проверяет: `lock_key not in self.position_locks` → True (все еще!)
3. Task A добавляет: `self.position_locks.add(lock_key)`
4. Task B добавляет: `self.position_locks.add(lock_key)` (поздно!)
5. Обе Task A и Task B продолжают открывать позицию

**Временные интервалы** (34-307ms) подтверждают параллельное выполнение asyncio.gather()

### Правильная реализация ЕСТЬ в `_position_exists()` (строки 737-775)

```python
# ПРАВИЛЬНЫЙ КОД в _position_exists():
if lock_key not in self.check_locks:
    self.check_locks[lock_key] = asyncio.Lock()  # ✅ Создаем Lock

async with self.check_locks[lock_key]:  # ✅ Атомарная блокировка
    # Только ОДНА task может выполнять этот код
    ...
```

**НО**: Эта блокировка вызывается **ПОСЛЕ** багованной проверки в `open_position()`!

## Необходимое исправление

Заменить строки 589-594 в `open_position()` на:

```python
# ИСПРАВЛЕННЫЙ КОД:
lock_key = f"{exchange_name}_{symbol}"

# Создать Lock если его нет
if lock_key not in self.position_locks:
    self.position_locks[lock_key] = asyncio.Lock()

# ✅ АТОМАРНАЯ БЛОКИРОВКА - только одна task может открывать позицию
async with self.position_locks[lock_key]:
    # ВСЯ логика открытия позиции внутри блокировки
    # включая _position_exists(), _open_position_on_exchange(), и т.д.
    ...
```

## Следующие шаги

1. Сравнить с паттернами Freqtrade/CCXT (как они предотвращают дубликаты)
2. Изменить тип `self.position_locks` с `Set[str]` на `Dict[str, asyncio.Lock]`
3. Обернуть ВСЮ логику `open_position()` в `async with lock`
4. Протестировать с чистого листа
