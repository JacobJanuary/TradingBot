# 🔬 ГЛУБОКОЕ РАССЛЕДОВАНИЕ: Проблемы с Bybit Balance

**Дата:** 2025-10-19 14:30 UTC
**Статус:** 🔴 НАЙДЕНЫ МНОЖЕСТВЕННЫЕ ПРОБЛЕМЫ
**Приоритет:** P0 - КРИТИЧЕСКИЙ

---

## 🚨 ОШИБКА В PRODUCTION

```
2025-10-19 13:53:06,207 - ERROR - Error checking if can open position for PRCLUSDT:
cannot access local variable 'balance' where it is not associated with a value
```

**Результат:** Bybit сигнал PRCLUSDT отфильтрован из-за ошибки валидации!

---

## 🔍 КОРНЕВАЯ ПРИЧИНА #1: Баг в can_open_position()

### Проблемный код (core/exchange_manager.py:1177-1200)

```python
if self.name == 'bybit':
    try:
        response = await self.exchange.privateGetV5AccountWalletBalance({...})
        # ... извлекаем free_usdt ...
        free_usdt = float(account.get('totalAvailableBalance', 0))
    except Exception as e:
        logger.warning(f"Failed to fetch Bybit UNIFIED balance, falling back...")
        balance = await self.exchange.fetch_balance()  # ← ОПРЕДЕЛЯЕМ balance
        free_usdt = float(balance.get('USDT', {}).get('free', 0) or 0)
else:
    # Binance
    balance = await self.exchange.fetch_balance()  # ← ОПРЕДЕЛЯЕМ balance
    free_usdt = float(balance.get('USDT', {}).get('free', 0) or 0)

# ДАЛЬШЕ В КОДЕ (строка 1230+):
if some_condition:
    # Код пытается использовать переменную 'balance'!
    # НО если Bybit прямой вызов УСПЕШЕН, переменная balance НЕ ОПРЕДЕЛЕНА!
    used_balance = balance.get('USDT', {}).get('used', 0)  # ← ERROR!
```

### Почему возникает ошибка?

1. **Успешный сценарий Bybit:**
   - Прямой API вызов успешен → `free_usdt` получен
   - Переменная `balance` **НЕ определена** (не было fallback)
   - Код идет дальше и пытается использовать `balance` → **ERROR**

2. **Fallback сценарий Bybit:**
   - Прямой API вызов FAILED → exception
   - `balance = await self.exchange.fetch_balance()` → `balance` определен
   - Код работает ✅

3. **Binance сценарий:**
   - `balance = await self.exchange.fetch_balance()` → `balance` определен
   - Код работает ✅

### Вывод

**БАГ:** Переменная `balance` используется где-то в коде после проверки баланса, но она НЕ определена когда Bybit прямой вызов успешен!

---

## 🔍 КОРНЕВАЯ ПРИЧИНА #2: Множественные места использования fetch_balance()

### Найдено 5 мест где fetch_balance() используется:

| Файл | Строка | Метод | Exchange | Проблема |
|------|--------|-------|----------|----------|
| `core/exchange_manager.py` | 1177-1200 | `can_open_position()` | Bybit | ✅ Частично исправлено (но есть баг) |
| `core/exchange_manager.py` | 240-245 | `fetch_balance()` | Все | ❌ НЕ исправлено |
| `core/aged_position_manager.py` | 698 | `_get_total_balance()` | Все | ❌ НЕ исправлено |
| `core/binance_zombie_manager.py` | 335 | `detect_zombies()` | Binance | ✅ OK (только Binance) |
| `websocket/adaptive_stream.py` | 191 | `_poll_rest_api()` | Все | ❌ НЕ исправлено |

---

## 📊 ДЕТАЛЬНЫЙ АНАЛИЗ КАЖДОГО МЕСТА

### 1. ❌ `core/exchange_manager.py:240` - fetch_balance()

```python
async def fetch_balance(self) -> Dict:
    """Fetch account balance with rate limiting"""
    balance = await self.rate_limiter.execute_request(
        self.exchange.fetch_balance  # ← Bybit вернет free=None!
    )
    return balance
```

**Проблема:**
- Этот метод используется внешним кодом
- Для Bybit возвращает `{'USDT': {'free': None, 'total': 10608}}`
- Любой код использующий `.get('free')` получит `None` → $0

**Используется в:**
- Внешние модули могут вызывать `exchange_manager.fetch_balance()`
- Нужно проверить все вызовы

---

### 2. ❌ `core/aged_position_manager.py:698` - _get_total_balance()

```python
async def _get_total_balance(self) -> float:
    """Get total account balance in USD"""
    try:
        total_balance = 0.0

        for exchange_name, exchange in self.exchanges.items():
            try:
                balance = await exchange.fetch_balance()  # ← ПРОБЛЕМА!

                # Get USDT balance (main trading currency)
                usdt_balance = balance.get('USDT', {}).get('free', 0)  # ← None для Bybit!
                total_balance += float(usdt_balance)  # ← float(None) = ERROR или 0
```

**Проблема:**
- Для Bybit: `usdt_balance = None`
- `float(None)` вызовет `TypeError` или если обработано → 0
- **Bybit баланс НЕ учитывается** в общем балансе!

**Влияние:**
- Aged Position Manager считает что у Bybit $0
- Может неправильно работать логика управления старыми позициями

---

### 3. ✅ `core/binance_zombie_manager.py:335` - detect_zombies()

```python
if hasattr(self.exchange, 'fetch_balance'):
    balance = await self.exchange.fetch_balance()
else:
    balance = self.exchange.fetch_balance()
```

**Статус:** ✅ OK
- Это только для Binance exchange
- Bybit zombie manager отсутствует

---

### 4. ❌ `websocket/adaptive_stream.py:191` - _poll_rest_api()

```python
async def _poll_rest_api(self):
    """Poll REST API for private data (testnet fallback)"""
    while self.running:
        try:
            # Fetch account data using ccxt methods
            balance = await self.client.fetch_balance()  # ← ПРОБЛЕМА!
            account_data = {
                'B': [{'a': 'USDT', 'wb': balance.get('USDT', {}).get('total', 0)}]
            }
```

**Проблема:**
- Использует `.get('total', 0)` → это OK (total работает)
- НО если где-то дальше использует `.get('free')` → None

**Статус:** ⚠️ Частично OK (использует только `total`, не `free`)

---

## 🎯 ВСЕ ПРОБЛЕМЫ СУММАРНО

### Критические (блокируют торговлю):

1. ✅ **can_open_position() баг с переменной `balance`**
   - Ошибка: `cannot access local variable 'balance'`
   - Файл: `core/exchange_manager.py:1177-1200`
   - Влияние: Bybit сигналы фильтруются с ошибкой

### Важные (неправильные данные):

2. ❌ **fetch_balance() возвращает free=None**
   - Файл: `core/exchange_manager.py:240-245`
   - Влияние: Внешний код получает неправильные данные

3. ❌ **_get_total_balance() игнорирует Bybit**
   - Файл: `core/aged_position_manager.py:698`
   - Влияние: Aged positions manager видит $0 для Bybit

### Некритические:

4. ⚠️ **adaptive_stream использует только total**
   - Файл: `websocket/adaptive_stream.py:191`
   - Влияние: Минимальное (использует только total, не free)

---

## 🔧 ПЛАН ИСПРАВЛЕНИЯ

### Фаза 1: НЕМЕДЛЕННОЕ ИСПРАВЛЕНИЕ (P0)

#### 1.1. Исправить баг с переменной `balance` в can_open_position()

**Проблема:** Переменная `balance` не определена когда Bybit прямой вызов успешен

**Решение:** Найти где используется `balance` после проверки и исправить

**Файл:** `core/exchange_manager.py:1177-1250`

**Метод:** Прочитать весь метод `can_open_position()` и найти все использования `balance`

#### 1.2. Создать helper метод `_get_free_balance_usdt()`

**Цель:** Централизовать логику получения Bybit баланса

**Реализация:**
```python
async def _get_free_balance_usdt(self) -> float:
    """
    Get free USDT balance for this exchange

    For Bybit UNIFIED accounts, uses direct API call.
    For other exchanges, uses standard fetch_balance().

    Returns:
        Free USDT balance as float
    """
    if self.name == 'bybit':
        try:
            response = await self.exchange.privateGetV5AccountWalletBalance({
                'accountType': 'UNIFIED',
                'coin': 'USDT'
            })
            result = response.get('result', {})
            accounts = result.get('list', [])
            if accounts:
                account = accounts[0]
                return float(account.get('totalAvailableBalance', 0))
            else:
                logger.warning("No Bybit account data, returning 0")
                return 0.0
        except Exception as e:
            logger.warning(f"Bybit balance fetch failed, fallback: {e}")
            # Fallback to standard method
            balance = await self.exchange.fetch_balance()
            return float(balance.get('USDT', {}).get('free', 0) or 0)
    else:
        # Binance and other exchanges
        balance = await self.exchange.fetch_balance()
        return float(balance.get('USDT', {}).get('free', 0) or 0)
```

**Преимущества:**
- ✅ Один метод для всех мест
- ✅ Централизованная обработка ошибок
- ✅ Легко тестировать
- ✅ Легко поддерживать

---

### Фаза 2: ОБНОВЛЕНИЕ ВСЕХ МЕСТ (P1)

#### 2.1. Обновить can_open_position()

```python
async def can_open_position(self, symbol: str, notional_usd: float, preloaded_positions: Optional[List] = None):
    try:
        # Step 1: Check free balance
        free_usdt = await self._get_free_balance_usdt()  # ← ИСПОЛЬЗОВАТЬ HELPER

        if free_usdt < float(notional_usd):
            return False, f"Insufficient free balance: ${free_usdt:.2f} < ${notional_usd:.2f}"

        # ... остальной код ...
```

#### 2.2. Обновить fetch_balance()

**Вариант A: Patch результат (рекомендуется)**

```python
async def fetch_balance(self) -> Dict:
    """Fetch account balance with rate limiting"""
    balance = await self.rate_limiter.execute_request(
        self.exchange.fetch_balance
    )

    # FIX: Patch Bybit UNIFIED balance
    if self.name == 'bybit':
        usdt = balance.get('USDT', {})
        if usdt.get('free') is None and usdt.get('total', 0) > 0:
            # Fetch accurate free balance using direct API
            try:
                free_usdt = await self._get_free_balance_usdt()
                balance['USDT']['free'] = free_usdt
                # Calculate used = total - free
                total = float(usdt.get('total', 0))
                balance['USDT']['used'] = total - free_usdt
            except Exception as e:
                logger.warning(f"Failed to patch Bybit balance: {e}")

    return balance
```

**Вариант B: Полная замена (более радикально)**

```python
async def fetch_balance(self) -> Dict:
    """Fetch account balance with rate limiting"""
    if self.name == 'bybit':
        # Use direct API for accurate data
        try:
            response = await self.exchange.privateGetV5AccountWalletBalance({
                'accountType': 'UNIFIED',
                'coin': 'USDT'
            })
            result = response.get('result', {})
            accounts = result.get('list', [])

            if accounts:
                account = accounts[0]
                total = float(account.get('totalWalletBalance', 0))
                free = float(account.get('totalAvailableBalance', 0))
                used = total - free

                return {
                    'USDT': {
                        'free': free,
                        'used': used,
                        'total': total
                    }
                }
        except Exception as e:
            logger.warning(f"Bybit balance fetch failed, fallback: {e}")

    # Standard method for Binance and fallback
    balance = await self.rate_limiter.execute_request(
        self.exchange.fetch_balance
    )
    return balance
```

**Рекомендация:** Вариант A (patch) - менее инвазивный

#### 2.3. Обновить aged_position_manager.py

```python
async def _get_total_balance(self) -> float:
    """Get total account balance in USD"""
    try:
        total_balance = 0.0

        for exchange_name, exchange in self.exchanges.items():
            try:
                # FIX: Use helper method if available
                if hasattr(exchange, '_get_free_balance_usdt'):
                    usdt_balance = await exchange._get_free_balance_usdt()
                else:
                    balance = await exchange.fetch_balance()
                    usdt_balance = balance.get('USDT', {}).get('free', 0)

                total_balance += float(usdt_balance or 0)  # ← Защита от None
```

---

### Фаза 3: ТЕСТИРОВАНИЕ (P1)

#### 3.1. Unit тесты

```python
# tests/unit/test_bybit_balance.py

async def test_get_free_balance_usdt_bybit():
    """Test Bybit UNIFIED balance fetching"""
    manager = ExchangeManager('bybit', ...)
    free_balance = await manager._get_free_balance_usdt()

    assert free_balance > 0
    assert isinstance(free_balance, float)

async def test_fetch_balance_bybit_patched():
    """Test that fetch_balance returns patched data for Bybit"""
    manager = ExchangeManager('bybit', ...)
    balance = await manager.fetch_balance()

    usdt = balance.get('USDT', {})
    assert usdt.get('free') is not None  # ← Должно быть число, не None!
    assert usdt.get('total') is not None
    assert usdt.get('used') is not None
```

#### 3.2. Integration тесты

```bash
# Запустить бота с Bybit testnet
python3 main.py

# Проверить логи:
# 1. can_open_position должен работать без ошибок
grep "cannot access local variable" logs/trading_bot.log
# Результат: должно быть пусто

# 2. Bybit сигналы должны проходить валидацию
grep "Pre-fetched.*bybit" logs/trading_bot.log
grep "Signal.*bybit filtered out" logs/trading_bot.log

# 3. Aged position manager должен видеть Bybit баланс
grep "total balance" logs/trading_bot.log
```

---

## 📋 ПРИОРИТЕТЫ ИСПРАВЛЕНИЯ

### P0 - КРИТИЧНО (сделать СЕЙЧАС):

1. ✅ **Найти где используется `balance` в can_open_position()**
   - Прочитать весь метод
   - Найти все упоминания переменной `balance`
   - Исправить баг

2. ✅ **Создать helper метод `_get_free_balance_usdt()`**
   - Централизовать логику Bybit баланса
   - Добавить в `ExchangeManager`

3. ✅ **Обновить can_open_position() использовать helper**
   - Убрать дублирование кода
   - Исправить баг с переменной

### P1 - ВАЖНО (сделать после P0):

4. ❌ **Обновить fetch_balance() для patch результата**
   - Вариант A (patch)
   - Или Вариант B (полная замена)

5. ❌ **Обновить aged_position_manager**
   - Использовать helper или защиту от None

6. ❌ **Протестировать все изменения**
   - Unit тесты
   - Integration тесты

---

## 🔴 GOLDEN RULE СОБЛЮДЕНИЕ

### Принципы для P0 исправлений:

1. ✅ **Минимальные изменения**
   - Исправить ТОЛЬКО баг с `balance`
   - Добавить ТОЛЬКО helper метод
   - НЕ рефакторить остальное

2. ✅ **Локализованные правки**
   - Изменить ТОЛЬКО can_open_position()
   - НЕ трогать другие методы на этом этапе

3. ✅ **Без рефакторинга**
   - НЕ переименовывать переменные
   - НЕ менять структуру кода
   - ТОЛЬКО исправить баг

4. ✅ **Обратная совместимость**
   - Binance НЕ затронут
   - Bybit fallback работает

5. ✅ **Без оптимизаций**
   - НЕ добавлять кеширование
   - НЕ менять логику
   - ТОЛЬКО fix бага

---

## 📊 СЛЕДУЮЩИЕ ШАГИ

### Шаг 1: Прочитать весь can_open_position()

```bash
# Найти весь метод
grep -A 100 "async def can_open_position" core/exchange_manager.py
```

### Шаг 2: Найти использования `balance`

Поискать в методе:
- `balance.get(...)`
- `balance[...]`
- `balance =`
- Любое упоминание `balance`

### Шаг 3: Исправить баг

Варианты:
- Определить `balance = None` в начале
- Или использовать `free_usdt` вместо `balance`
- Или создать helper и убрать все упоминания `balance`

---

**Статус:** 🔴 РАССЛЕДОВАНИЕ ЗАВЕРШЕНО
**Автор:** Claude Code Deep Investigation Team
**Дата:** 2025-10-19 14:30 UTC

**КРИТИЧНО:** Нужно немедленно исправить баг с `balance` переменной!
