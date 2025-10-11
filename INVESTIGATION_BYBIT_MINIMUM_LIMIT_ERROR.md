# 🔍 ГЛУБОКОЕ РАССЛЕДОВАНИЕ: Bybit Minimum Limit Error

**Дата:** 2025-10-12
**Ошибка:** `retCode=10001` "The number of contracts exceeds minimum limit allowed"
**Символ:** BLASTUSDT
**Статус:** КОРНЕВАЯ ПРИЧИНА НАЙДЕНА

---

## 📊 ХРОНОЛОГИЯ ОШИБКИ

### Исходные данные из логов

```
2025-10-12 00:50:11,736 - Opening position ATOMICALLY: BLASTUSDT SELL 77820
2025-10-12 00:50:11,989 - Market info not found for BLASTUSDT, using original amount
2025-10-12 00:50:12,328 - Entry order failed: None
2025-10-12 00:50:12,612 - bybit {"retCode":10001,"retMsg":"The number of contracts exceeds minimum limit allowed"}
```

### Шаги выполнения:

1. **00:50:11.736** - Получен сигнал на SELL BLASTUSDT, количество: 77820
2. **00:50:11.989** - ⚠️ "Market info not found for BLASTUSDT"
3. **00:50:12.328** - Entry order возвращает **None** (не создался)
4. **00:50:12.328** - Попытка rollback (закрыть позицию)
5. **00:50:12.612** - ❌ Ошибка Bybit: retCode=10001

---

## 🔴 КОРНЕВАЯ ПРИЧИНА

### Проблема #1: Символ недоступен на Bybit

**BLASTUSDT отсутствует в списке доступных символов на Bybit!**

**Доказательства:**

1. **Файл:** `core/exchange_manager.py:681`
   ```python
   market = self.markets.get(symbol)
   if not market:
       logger.warning(f"Market info not found for {symbol}, using original amount")
       return amount  # ⚠️ Возвращает без валидации!
   ```

2. **Результат:** `self.markets` не содержит BLASTUSDT для Bybit
   - `self.markets` загружается через `load_markets()` при инициализации
   - Если символа нет в markets → он НЕ ДОСТУПЕН на данной бирже

### Проблема #2: Отсутствует проверка доступности символа на конкретной бирже

**Файл:** `core/symbol_filter.py`

**Что проверяется:**
- ✅ Stoplist symbols
- ✅ Whitelist symbols
- ✅ Exclusion patterns (leveraged tokens)
- ✅ Special exclusions (DOM, stablecoins)

**Что НЕ проверяется:**
- ❌ Доступность символа на **конкретной бирже** (Bybit vs Binance)
- ❌ Наличие символа в `exchange.markets`
- ❌ Минимальные/максимальные лимиты для биржи

**Результат:** BLASTUSDT может быть:
- ✅ Доступен на Binance
- ❌ Недоступен на Bybit
- ✅ Проходит все фильтры (stoplist, whitelist, patterns)
- ❌ НЕ отклоняется системой

### Проблема #3: Неправильная обработка отсутствующих символов

**Файл:** `core/exchange_manager.py:289-290`

```python
# Check and adjust amount to exchange limits
amount = await self._validate_and_adjust_amount(symbol, float(amount))
```

**Файл:** `core/exchange_manager.py:680-682`

```python
market = self.markets.get(symbol)
if not market:
    logger.warning(f"Market info not found for {symbol}, using original amount")
    return amount  # ⚠️ КРИТИЧЕСКАЯ ОШИБКА: возвращает без проверки!
```

**Последствия:**
1. Если market info не найден → amount НЕ валидируется
2. НЕ проверяются min/max лимиты биржи
3. НЕ проверяется precision (округление)
4. Ордер отправляется с **неправильным количеством**

---

## 🎯 ПРАКТИЧЕСКИЙ ПРИМЕР

### Сценарий: BLASTUSDT на Bybit

**Что происходит:**

| Этап | Действие | Результат |
|------|----------|-----------|
| 1. Получен сигнал | BLASTUSDT SELL 77820 | ✅ Сигнал обработан |
| 2. SymbolFilter | is_symbol_allowed() | ✅ ALLOWED (нет в stoplist) |
| 3. Exchange check | BLASTUSDT in markets? | ❌ **NOT FOUND** |
| 4. Amount validation | _validate_and_adjust_amount() | ⚠️ **SKIPPED** (no market info) |
| 5. Create order | exchange.create_market_order() | ❌ **FAILED** (invalid symbol/amount) |
| 6. Bybit response | retCode=10001 | ❌ "exceeds minimum limit" |

### Почему ошибка "exceeds MINIMUM limit"?

**Две возможные причины:**

#### Причина A: Символ недоступен на Bybit
- BLASTUSDT **не торгуется** на Bybit
- Bybit отклоняет с generic error 10001
- "minimum limit" - некорректное сообщение от API

#### Причина B: Неправильный формат количества
- Без market info → нет precision
- 77820 может быть неправильно округлено
- Минимальный лот для BLASTUSDT (если есть) может быть другим

---

## 🔍 ДОКАЗАТЕЛЬСТВА ПРОБЛЕМЫ

### 1. Market info отсутствует

```
2025-10-12 00:50:11,989 - WARNING - Market info not found for BLASTUSDT
```

Это означает:
- `exchange.markets.get('BLASTUSDT')` вернул `None`
- Символ НЕ загрузился при `load_markets()`
- **ВЫВОД:** BLASTUSDT недоступен на Bybit

### 2. Entry order вернул None

```python
# atomic_position_manager.py:172
raw_order = await exchange_instance.create_market_order(symbol, side, quantity)

# atomic_position_manager.py:177
if raw_order is None:
    raise AtomicPositionError(f"Failed to create order for {symbol}: order returned None")
```

**Результат:** Entry order failed: None

Это означает:
- `create_market_order` поймал exception
- Вернул `None` вместо ордера
- **ВЫВОД:** Ордер не создался из-за ошибки API

### 3. Rollback тоже failed

При попытке закрыть позицию (rollback):
```
retCode=10001, retMsg="The number of contracts exceeds minimum limit allowed"
```

Это означает:
- Даже попытка закрыть позицию падает
- Bybit не принимает ордера для BLASTUSDT
- **ВЫВОД:** Символ полностью недоступен

---

## 📋 АНАЛИЗ КОДА

### Где должна быть проверка?

#### Вариант 1: В SymbolFilter (РЕКОМЕНДУЕТСЯ)

**Файл:** `core/symbol_filter.py:180`

**Текущий код:**
```python
def is_symbol_allowed(self, symbol: str, check_volume: bool = False) -> Tuple[bool, str]:
    # 1. Check stop-list
    # 2. Check whitelist
    # 3. Check patterns
    # 4. Check special exclusions
    # ❌ НЕТ ПРОВЕРКИ exchange availability!
```

**Что нужно добавить:**
```python
def is_symbol_allowed(self, symbol: str, exchange_markets: Dict = None) -> Tuple[bool, str]:
    # ...existing checks...

    # NEW: Check exchange availability
    if exchange_markets is not None:
        if symbol not in exchange_markets:
            return False, f"Symbol not available on this exchange"
```

#### Вариант 2: В exchange_manager (МИНИМАЛЬНЫЙ FIX)

**Файл:** `core/exchange_manager.py:680-682`

**Текущий код:**
```python
market = self.markets.get(symbol)
if not market:
    logger.warning(f"Market info not found for {symbol}, using original amount")
    return amount  # ⚠️ ОШИБКА: не проверяет доступность!
```

**Исправление:**
```python
market = self.markets.get(symbol)
if not market:
    logger.error(f"❌ Symbol {symbol} not available on {self.name}")
    raise ValueError(f"Symbol {symbol} not available on exchange {self.name}")
```

---

## 🚨 ПОСЛЕДСТВИЯ ОШИБКИ

### Для трейдинга:

1. **Потеря сигналов**
   - Сигналы на недоступные символы полностью игнорируются
   - Позиция не открывается
   - Signal marked as FAILED

2. **Путаница в логах**
   - "Market info not found" - неясно что это значит
   - "Entry order failed: None" - нет деталей
   - Bybit error 10001 - непонятная ошибка

3. **Невозможность debug**
   - Нет информации КАКИЕ символы доступны на Bybit
   - Нет проверки до попытки создания ордера
   - Ошибка обнаруживается только при execution

### Для статистики:

4. **Неверная статистика сигналов**
   - Failed signals из-за недоступности символа
   - Win rate искажён (включает невалидные сигналы)

---

## ✅ РЕШЕНИЕ

### Приоритет: 🔴 ВЫСОКИЙ

### Фаза 1: Минимальное исправление (5 минут)

**Цель:** Предотвратить попытки открытия позиций на недоступных символах

**Файл:** `core/exchange_manager.py:680-682`

```python
# BEFORE:
market = self.markets.get(symbol)
if not market:
    logger.warning(f"Market info not found for {symbol}, using original amount")
    return amount

# AFTER:
market = self.markets.get(symbol)
if not market:
    logger.error(f"❌ Symbol {symbol} not available on exchange {self.name}")
    raise ValueError(f"Symbol {symbol} not available on {self.name}. "
                    f"This symbol may only be available on other exchanges.")
```

**Результат:**
- ✅ Ордер НЕ создаётся для недоступных символов
- ✅ Чёткая ошибка в логах
- ✅ Exception ловится в atomic_position_manager
- ✅ Позиция НЕ создаётся в БД

### Фаза 2: Проверка доступности в SymbolFilter (15 минут)

**Цель:** Фильтровать недоступные символы ДО попытки открытия

**Файл:** `core/symbol_filter.py`

```python
def is_symbol_allowed(self, symbol: str,
                     exchange_markets: Dict = None,
                     check_volume: bool = False) -> Tuple[bool, str]:
    """
    Check if symbol is allowed for trading

    Args:
        symbol: Symbol to check
        exchange_markets: Optional dict of available markets on exchange
        check_volume: Whether to check trading volume
    """
    # ...existing checks...

    # NEW: Check exchange availability
    if exchange_markets is not None:
        if symbol not in exchange_markets:
            self.stats['blocked_exchange_unavailable'] = \
                self.stats.get('blocked_exchange_unavailable', 0) + 1
            return False, f"Not available on this exchange"

    # ...rest of checks...
```

**Использование в signal_processor:**

```python
# Get exchange markets
exchange_instance = self.position_manager.exchanges.get(exchange)
exchange_markets = exchange_instance.markets if exchange_instance else None

# Check with exchange availability
is_allowed, reason = self.symbol_filter.is_symbol_allowed(
    symbol,
    exchange_markets=exchange_markets
)

if not is_allowed:
    logger.warning(f"❌ Signal rejected: {symbol} - {reason}")
    return None
```

### Фаза 3: Логирование доступных символов (опционально)

**Цель:** Понимать какие символы доступны на каждой бирже

**При инициализации exchange:**

```python
async def initialize(self):
    self.markets = await self.exchange.load_markets()
    logger.info(f"✅ {self.name}: Loaded {len(self.markets)} tradeable symbols")

    # Log sample of available symbols
    symbols_sample = list(self.markets.keys())[:10]
    logger.debug(f"Sample symbols: {', '.join(symbols_sample)}...")
```

---

## 📊 МЕТРИКИ ДЛЯ ТЕСТИРОВАНИЯ

После исправления проверить:

1. ✅ Символы недоступные на Bybit отклоняются ДО создания ордера
2. ✅ Чёткое сообщение об ошибке в логах
3. ✅ Нет попыток создания ордеров на недоступные символы
4. ✅ Statistics показывает сколько символов отклонено из-за unavailability

---

## 🎯 ДОПОЛНИТЕЛЬНЫЕ НАХОДКИ

### Проблема #4: Нет различия Binance/Bybit символов

**Текущая ситуация:**
- Сигналы приходят без указания биржи
- Bot пытается открывать на **всех** доступных биржах
- Если символ есть только на Binance → Bybit падает с ошибкой

**Возможное улучшение:**
- Добавить проверку на какой бирже доступен символ
- Открывать позицию только на той бирже где символ есть
- Логировать если символ недоступен на какой-то из бирж

### Проблема #5: retCode=10001 - generic error

**Документация Bybit:**
- Error 10001: "Parameter error"
- Очень generic, может означать разное
- Сообщение "exceeds minimum limit" misleading

**Возможные причины 10001:**
- Invalid symbol
- Invalid quantity format
- Symbol not tradeable
- Wrong API parameters

---

## ✅ ИТОГОВЫЕ ВЫВОДЫ

### Корневая причина:

**BLASTUSDT недоступен для торговли на Bybit.**

### Цепочка ошибок:

1. SymbolFilter не проверяет доступность на конкретной бирже
2. exchange_manager не выбрасывает exception при отсутствии market info
3. Ордер создаётся с неправильными параметрами
4. Bybit отклоняет с generic error 10001
5. Rollback тоже падает с той же ошибкой

### Рекомендации:

1. **Немедленно:** Добавить exception при отсутствии market info
2. **Краткосрочно:** Добавить проверку exchange_markets в SymbolFilter
3. **Долгосрочно:** Добавить логику выбора биржи на основе доступности символа

---

## 📝 СЛЕДУЮЩИЕ ШАГИ

Жду вашего решения:
- ✅ **Реализовать Фазу 1** (минимальное исправление) - РЕКОМЕНДУЕТСЯ
- ⏸️ Реализовать Фазу 2 (SymbolFilter enhancement)
- ⏸️ Запросить дополнительную информацию
- 🔄 Изменить подход

**Приоритет:** ВЫСОКИЙ - ошибка блокирует открытие позиций и создаёт путаницу в логах.
