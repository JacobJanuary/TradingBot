# 🔍 РАССЛЕДОВАНИЕ: Symbol Format Conversion Problem

**Дата:** 2025-10-12
**Ошибка:** `retCode=10001` "The number of contracts exceeds minimum limit allowed"
**Символ:** BLASTUSDT
**Статус:** ✅ КОРНЕВАЯ ПРИЧИНА НАЙДЕНА

---

## 📊 РЕЗЮМЕ ПРОБЛЕМЫ

**BLASTUSDT доступен на Bybit testnet, НО в формате `BLAST/USDT:USDT`**

Diagnostic script показал:
```
❌ BLASTUSDT NOT FOUND in markets
✅ Found similar: ['BLAST/USDT:USDT']
```

**Корневая причина:** Отсутствует конверсия символов из формата БД (`BLASTUSDT`) в формат CCXT для конкретной биржи (`BLAST/USDT:USDT`).

---

## 🔴 КРИТИЧЕСКАЯ ОШИБКА АРХИТЕКТУРЫ

### Текущая логика работы с символами

**Есть нормализация (Exchange → DB):**
```python
# core/position_manager.py:40-50
def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format for consistent comparison
    Converts exchange format 'HIGH/USDT:USDT' to database format 'HIGHUSDT'
    """
    if '/' in symbol and ':' in symbol:
        # Exchange format: 'HIGH/USDT:USDT' -> 'HIGHUSDT'
        base_quote = symbol.split(':')[0]  # 'HIGH/USDT'
        return base_quote.replace('/', '')  # 'HIGHUSDT'
    return symbol
```

**❌ НЕТ денормализации (DB → Exchange):**
- Нет функции для конверсии `BLASTUSDT` → `BLAST/USDT:USDT`
- Нет логики определения формата для конкретной биржи
- Символы из сигналов используются напрямую без конверсии

---

## 🎯 ПРАКТИЧЕСКИЙ ПРИМЕР ПРОБЛЕМЫ

### Сценарий: Сигнал на BLASTUSDT для Bybit

**Шаг 1: Получение сигнала**
```python
# Signal приходит в формате БД
signal = {
    'symbol': 'BLASTUSDT',  # Формат БД (нормализованный)
    'exchange': 'bybit',
    'action': 'sell',
    'quantity': 77820
}
```

**Шаг 2: Валидация символа**
```python
# models/validation.py:175-182
def validate_symbol(cls, v):
    # Remove common separators and standardize
    cleaned = v.upper().replace('/', '').replace('-', '').replace('_', '')
    # 'BLAST/USDT' → 'BLASTUSDT'
    return cleaned
```

**Результат:** Символ остаётся `BLASTUSDT`

**Шаг 3: Создание позиции**
```python
# core/signal_processor_websocket.py:572-577
request = PositionRequest(
    signal_id=signal_id,
    symbol=validated_signal.symbol,  # 'BLASTUSDT'
    exchange=validated_signal.exchange,  # 'bybit'
    side=side,
    entry_price=Decimal(str(current_price))
)
```

**Результат:** `symbol = 'BLASTUSDT'` передаётся в position_manager

**Шаг 4: Валидация количества**
```python
# core/exchange_manager.py:676-682
if symbol not in self.markets:
    await self.exchange.load_markets()

market = self.markets.get(symbol)  # self.markets.get('BLASTUSDT')
if not market:
    logger.warning(f"Market info not found for {symbol}, using original amount")
    return amount  # ⚠️ Возвращает без валидации!
```

**Результат:**
- `self.markets` содержит `'BLAST/USDT:USDT'`, НЕ `'BLASTUSDT'`
- `market = None`
- Валидация пропущена ❌

**Шаг 5: Создание ордера**
```python
# core/exchange_manager.py:250-257
order = await self.rate_limiter.execute_request(
    self.exchange.create_order,
    symbol=symbol,  # ❌ 'BLASTUSDT' вместо 'BLAST/USDT:USDT'
    type=type,
    side=side.lower(),
    amount=amount,  # ❌ Не валидирован!
    price=price,
    params=params or {}
)
```

**Результат:** Bybit отклоняет с ошибкой:
```
retCode=10001, retMsg="The number of contracts exceeds minimum limit allowed"
```

---

## 🔍 ФОРМАТЫ СИМВОЛОВ ПО БИРЖАМ

### Binance Futures (CCXT)
**Формат:** Может быть оба формата в зависимости от версии CCXT
- Spot style: `BTCUSDT`
- Unified style: `BTC/USDT:USDT`

**Пример из diagnostic:**
```
Sample USDT symbols: ['BTC/USDT', 'ETH/USDT', 'EOS/USDT', ...]
```

### Bybit Futures (CCXT)
**Формат:** Только unified style
- ✅ `BLAST/USDT:USDT`
- ❌ `BLASTUSDT` - НЕ СУЩЕСТВУЕТ

**Пример из diagnostic:**
```
✅ Total markets loaded: 2550
❌ BLASTUSDT NOT FOUND in markets
✅ Found similar: ['BLAST/USDT:USDT']
```

### Database Format
**Формат:** Нормализованный (без разделителей)
- `BLASTUSDT`
- `BTCUSDT`
- `ETHUSDT`

---

## 📋 ГДЕ ИСПОЛЬЗУЕТСЯ normalize_symbol()

### 1. Получение позиций с биржи
```python
# core/position_manager.py:490-493
for pos in active_positions:
    # Exchange: "A/USDT:USDT" -> DB: "AUSDT"
    symbol = normalize_symbol(pos['symbol'])
```
✅ **Работает:** Конвертирует формат биржи в формат БД

### 2. Сравнение символов
```python
# core/position_manager.py:242-248
normalized_symbol = normalize_symbol(symbol)

for pos in positions:
    if normalize_symbol(pos['symbol']) == normalized_symbol:
        # Position found
```
✅ **Работает:** Сравнивает нормализованные символы

### 3. WebSocket обновления
```python
# core/position_manager.py:1133-1134
symbol_raw = data.get('symbol')
symbol = normalize_symbol(symbol_raw) if symbol_raw else None
```
✅ **Работает:** Конвертирует формат биржи в формат БД

### 4. ❌ НЕТ конверсии при создании ордеров!

**Проблема:** Когда нужно создать ордер, символ из БД (`BLASTUSDT`) передаётся напрямую в API биржи без конверсии в формат биржи!

---

## 🚨 ПОСЛЕДСТВИЯ ОШИБКИ

### Для Binance:
✅ **Работает** - Binance принимает оба формата (`BTCUSDT` и `BTC/USDT:USDT`)

### Для Bybit:
❌ **НЕ работает** - Bybit принимает только `BLAST/USDT:USDT`, отклоняет `BLASTUSDT`

**Результат:**
1. ❌ Позиции не открываются на Bybit
2. ❌ Ошибка 10001 вместо корректного сообщения
3. ❌ "Market info not found" в логах
4. ❌ Валидация пропущена (amounts, prices не проверяются)

---

## ✅ РЕШЕНИЕ

### Приоритет: 🔴 КРИТИЧЕСКИЙ

### Решение: Добавить функцию денормализации символа

**Цель:** Конвертировать `BLASTUSDT` → `BLAST/USDT:USDT` для конкретной биржи

**Подход 1: Поиск в markets (РЕКОМЕНДУЕТСЯ)**

```python
def find_exchange_symbol(self, normalized_symbol: str) -> Optional[str]:
    """
    Find exchange-specific symbol format by searching markets

    Args:
        normalized_symbol: Database format symbol (e.g., 'BLASTUSDT')

    Returns:
        Exchange format symbol (e.g., 'BLAST/USDT:USDT') or None if not found

    Examples:
        Binance: 'BTCUSDT' → 'BTC/USDT:USDT' or 'BTCUSDT'
        Bybit: 'BLASTUSDT' → 'BLAST/USDT:USDT'
    """
    # Try exact match first (for Binance compatibility)
    if normalized_symbol in self.markets:
        return normalized_symbol

    # Search for matching symbol in all markets
    for market_symbol in self.markets.keys():
        if normalize_symbol(market_symbol) == normalized_symbol:
            return market_symbol

    return None
```

**Подход 2: Реконструкция формата (НЕ рекомендуется)**

```python
def denormalize_symbol(normalized_symbol: str) -> str:
    """Convert 'BLASTUSDT' to 'BLAST/USDT:USDT'"""
    # Проблема: Нужно знать где заканчивается base и начинается quote
    # Для 'BLASTUSDT' это может быть:
    # - BLAST/USDT ✅
    # - BLASTU/SDT ❌
    # - BLA/STUSDT ❌
    # НЕ НАДЁЖНО!
```

---

## 🔧 ПЛАН ИСПРАВЛЕНИЯ

### Фаза 1: Минимальное исправление (10 минут)

**Файл:** `core/exchange_manager.py`

**1. Добавить функцию поиска символа:**
```python
def find_exchange_symbol(self, normalized_symbol: str) -> Optional[str]:
    """Find exchange-specific symbol format"""
    # Try exact match first
    if normalized_symbol in self.markets:
        return normalized_symbol

    # Search for matching normalized symbol
    for market_symbol in self.markets.keys():
        if normalize_symbol(market_symbol) == normalized_symbol:
            logger.info(f"Symbol format conversion: {normalized_symbol} → {market_symbol}")
            return market_symbol

    return None
```

**2. Использовать перед валидацией и созданием ордеров:**
```python
async def _validate_and_adjust_amount(self, symbol: str, amount: float) -> float:
    """Validate and adjust order amount to exchange limits"""
    try:
        # Load market data if not cached
        if symbol not in self.markets:
            await self.exchange.load_markets()

        # CRITICAL FIX: Find exchange-specific symbol format
        exchange_symbol = self.find_exchange_symbol(symbol)

        if not exchange_symbol:
            logger.error(f"❌ Symbol {symbol} not available on {self.name}")
            raise ValueError(f"Symbol {symbol} not available on exchange {self.name}")

        # Use exchange_symbol for all subsequent operations
        market = self.markets.get(exchange_symbol)
        # ... rest of validation ...
```

**3. Обновить create_order для использования правильного формата:**
```python
async def create_order(self, symbol: str, type: str, side: str, amount: Decimal, ...):
    """Create order with automatic symbol format conversion"""

    # CRITICAL FIX: Convert symbol to exchange format
    exchange_symbol = self.find_exchange_symbol(symbol)

    if not exchange_symbol:
        raise ValueError(f"Symbol {symbol} not available on {self.name}")

    # Use exchange_symbol in API call
    order = await self.rate_limiter.execute_request(
        self.exchange.create_order,
        symbol=exchange_symbol,  # ✅ Correct format!
        type=type,
        side=side.lower(),
        amount=amount,
        ...
    )
```

---

## 📊 МЕТРИКИ ДЛЯ ТЕСТИРОВАНИЯ

После исправления проверить:

1. ✅ `BLASTUSDT` находит `BLAST/USDT:USDT` в Bybit markets
2. ✅ Логи показывают конверсию символа
3. ✅ Валидация работает (min/max amounts проверяются)
4. ✅ Ордера создаются успешно
5. ✅ Binance продолжает работать (обратная совместимость)

---

## 🎯 ТЕСТОВЫЕ СЛУЧАИ

### Test Case 1: Bybit BLASTUSDT
**Input:** `symbol = 'BLASTUSDT'`, `exchange = 'bybit'`
**Expected:**
- `find_exchange_symbol('BLASTUSDT')` → `'BLAST/USDT:USDT'`
- Market info found ✅
- Validation passed ✅
- Order created ✅

### Test Case 2: Binance BTCUSDT
**Input:** `symbol = 'BTCUSDT'`, `exchange = 'binance'`
**Expected:**
- `find_exchange_symbol('BTCUSDT')` → `'BTCUSDT'` (exact match)
- Market info found ✅
- Validation passed ✅
- Order created ✅

### Test Case 3: Non-existent symbol
**Input:** `symbol = 'FAKEUSDT'`, `exchange = 'bybit'`
**Expected:**
- `find_exchange_symbol('FAKEUSDT')` → `None`
- ValueError raised ✅
- Clear error message ✅
- Order NOT created ✅

---

## ✅ ИТОГОВЫЕ ВЫВОДЫ

### Корневая причина:

**Односторонняя конверсия символов:**
- ✅ Exchange → DB: `normalize_symbol()` работает
- ❌ DB → Exchange: Функции НЕТ!

### Цепочка ошибок:

1. Сигнал приходит в формате БД: `BLASTUSDT`
2. Валидация НЕ конвертирует в формат биржи
3. `markets.get('BLASTUSDT')` → `None` (на Bybit нет такого символа)
4. Валидация пропущена (возврат без проверки)
5. Ордер создаётся с неправильным символом
6. Bybit отклоняет с generic error 10001

### Рекомендации:

1. **Немедленно:** Добавить `find_exchange_symbol()` в ExchangeManager
2. **Использовать:** Перед валидацией и созданием ордеров
3. **Проверить:** Обратную совместимость с Binance

---

## 📝 СЛЕДУЮЩИЕ ШАГИ

Жду вашего решения:
- ✅ **Реализовать минимальное исправление** - РЕКОМЕНДУЕТСЯ
- ⏸️ Изменить подход
- 🔄 Запросить дополнительную информацию

**Приоритет:** КРИТИЧЕСКИЙ - ошибка блокирует все новые позиции на Bybit.
