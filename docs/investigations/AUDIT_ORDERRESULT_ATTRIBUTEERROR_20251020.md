# Аудит: AttributeError в _cancel_protection_sl_if_binance

**Дата**: 2025-10-20
**Ошибка**: `'OrderResult' object has no attribute 'get'`
**Файл**: `protection/trailing_stop.py:791`
**Символ**: ICNTUSDT (Binance)

## Текст ошибки

```
2025-10-20 18:50:15,147 - protection.trailing_stop - ERROR - ❌ ICNTUSDT: Failed to cancel Protection SL: 'OrderResult' object has no attribute 'get'
Traceback (most recent call last):
  File "/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/protection/trailing_stop.py", line 791, in _cancel_protection_sl_if_binance
    order_type = order.get('type', '').upper()
                 ^^^^^^^^^
AttributeError: 'OrderResult' object has no attribute 'get'
```

## Анализ root cause

### 1. Проблемный код (trailing_stop.py:780-798)

```python
# Line 780
orders = await self.exchange.fetch_open_orders(ts.symbol)

# Lines 790-798
for order in orders:
    order_type = order.get('type', '').upper()  # ❌ ОШИБКА ЗДЕСЬ
    order_side = order.get('side', '').lower()
    reduce_only = order.get('reduceOnly', False)

    if (order_type == 'STOP_MARKET' and
        order_side == expected_side and
        reduce_only):
        protection_sl_orders.append(order)
```

### 2. Тип данных OrderResult

**Определение** (exchange_manager.py:40-53):
```python
@dataclass
class OrderResult:
    """Order execution result"""
    id: str
    symbol: str
    side: str
    type: str
    amount: Decimal
    price: Decimal
    filled: Decimal
    remaining: Decimal
    status: str
    timestamp: datetime
    info: Dict  # Оригинальный CCXT ответ
```

**Доступ к полям**:
- ✅ Правильно: `order.type`, `order.side`, `order.id`
- ❌ Неправильно: `order.get('type')`, `order['type']`

### 3. Где создаётся OrderResult

**exchange_manager.py:1042-1055**:
```python
async def fetch_open_orders(self, symbol: str = None, params: Dict = None) -> List[OrderResult]:
    """Fetch open orders"""
    if params:
        orders = await self.exchange.fetch_open_orders(symbol, params)
    else:
        orders = await self.exchange.fetch_open_orders(symbol)

    # Преобразование CCXT dict -> OrderResult
    return [self._parse_order(order) for order in orders]
```

**exchange_manager.py:1180-1200**:
```python
def _parse_order(self, order: Dict) -> OrderResult:
    """Parse CCXT order to standardized format"""
    return OrderResult(
        id=order['id'],
        symbol=order['symbol'],
        side=order['side'],
        type=order['type'],  # ← Извлекаем из CCXT dict
        amount=order['amount'],
        price=order['price'] or 0,
        filled=order.get('filled', 0),
        remaining=order.get('remaining', order['amount']),
        status=order['status'],
        timestamp=timestamp,
        info=order['info']  # ← Сохраняем оригинальный ответ
    )
```

### 4. Почему код ожидал dict?

**Историческая причина**: Раньше `self.exchange` был CCXT объектом напрямую:
```python
# Старый код (прямой CCXT)
orders = await self.exchange.exchange.fetch_open_orders(symbol)  # Returns List[Dict]

for order in orders:
    order_type = order.get('type')  # ✅ Работает для dict
```

**Новый код (через ExchangeManager)**:
```python
# Новый код (через wrapper)
orders = await self.exchange.fetch_open_orders(symbol)  # Returns List[OrderResult]

for order in orders:
    order_type = order.get('type')  # ❌ OrderResult не имеет .get()
```

### 5. Где ExchangeManager используется правильно

**Нигде в trailing_stop.py!** Весь код ожидает CCXT dict, а не OrderResult.

**Примеры правильного использования OrderResult** (из других модулей):

```python
# Правильно: доступ к атрибутам
for order in orders:
    order_id = order.id
    order_type = order.type
    order_side = order.side

    # Для дополнительных полей используй order.info
    stop_price = order.info.get('stopPrice')
    reduce_only = order.info.get('reduceOnly', False)
```

## Масштаб проблемы

### Затронутые файлы

**1. protection/trailing_stop.py** (проблемный файл):

Функция `_cancel_protection_sl_if_binance()` (строки 757-832):
- Строка 791: `order.get('type')`
- Строка 792: `order.get('side')`
- Строка 793: `order.get('reduceOnly')`
- Строка 804: `order.get('stopPrice')`
- Строка 803: `order['id']` (тоже неправильно!)

### Другие потенциальные проблемы в trailing_stop.py

Проверил все использования `self.exchange.fetch_open_orders()`:

**Результат**: Только одно место - `_cancel_protection_sl_if_binance()`

### Почему ошибка проявилась только сейчас?

**Причина**: Функция `_cancel_protection_sl_if_binance()` вызывается только при активации TS для Binance позиций.

**Условия вызова** (trailing_stop.py:664-673):
```python
async def _check_activation(self, ts: TrailingStopInstance):
    # ...
    if should_activate:
        # For Binance, cancel Protection Manager SL first
        if self.exchange_name == 'binance':
            await self._cancel_protection_sl_if_binance(ts)  # ← Вызов здесь

        # Activate trailing
        ts.state = TrailingStopState.ACTIVE
```

**Почему сработало сейчас**:
1. Запустили бота после изменений Initial SL
2. TS теперь управляет SL с момента создания
3. Позиция ICNTUSDT достигла 1.5% прибыли
4. TS попытался активировать trailing
5. Для Binance вызвался `_cancel_protection_sl_if_binance()`
6. **BOOM!** AttributeError

**До изменений Initial SL**:
- TS не управлял SL до активации
- Protection Manager создавал SL
- При активации TS пытался удалить Protection SL
- Но эта функция редко вызывалась (только если позиция сразу в профите)

**После изменений Initial SL**:
- TS управляет SL с создания
- TS создаёт свой SL ордер
- При активации TS проверяет наличие старых Protection SL
- Функция вызывается ЧАЩЕ
- Ошибка проявилась!

## План исправления

### Вариант 1: Использовать OrderResult атрибуты ✅ РЕКОМЕНДУЕТСЯ

**Плюсы**:
- Типобезопасно (dataclass)
- Соответствует архитектуре ExchangeManager
- Минимальные изменения

**Минусы**:
- Нужно учесть, что `reduceOnly` и `stopPrice` в `order.info`

**Код**:
```python
for order in orders:
    # Основные поля из OrderResult
    order_type = order.type.upper() if order.type else ''
    order_side = order.side.lower() if order.side else ''

    # Дополнительные поля из order.info (CCXT raw data)
    reduce_only = order.info.get('reduceOnly', False)

    if (order_type == 'STOP_MARKET' and
        order_side == expected_side and
        reduce_only):
        protection_sl_orders.append(order)

# При отмене
for order in protection_sl_orders:
    order_id = order.id  # Используем атрибут, не ['id']
    stop_price = order.info.get('stopPrice', 'unknown')

    await self.exchange.cancel_order(order_id, ts.symbol)
```

### Вариант 2: Использовать прямой CCXT API ❌ НЕ РЕКОМЕНДУЕТСЯ

**Плюсы**:
- Минимальные изменения кода

**Минусы**:
- Обходит ExchangeManager (нарушает архитектуру)
- Не использует rate limiting
- Дублирует логику

**Код**:
```python
# Обход ExchangeManager
orders = await self.exchange.exchange.fetch_open_orders(ts.symbol)  # Прямой CCXT

for order in orders:
    order_type = order.get('type', '').upper()  # Теперь dict, работает
    # ...
```

### Вариант 3: Добавить метод to_dict() в OrderResult ❌ ИЗБЫТОЧНО

**Плюсы**:
- Обратная совместимость

**Минусы**:
- Усложняет OrderResult
- Не решает архитектурную проблему
- Избыточная работа

## Рекомендуемое решение

### Шаг 1: Исправить _cancel_protection_sl_if_binance()

**Файл**: `protection/trailing_stop.py:790-804`

**ДО**:
```python
for order in orders:
    order_type = order.get('type', '').upper()
    order_side = order.get('side', '').lower()
    reduce_only = order.get('reduceOnly', False)

    if (order_type == 'STOP_MARKET' and
        order_side == expected_side and
        reduce_only):
        protection_sl_orders.append(order)

# ...
for order in protection_sl_orders:
    order_id = order['id']
    stop_price = order.get('stopPrice', 'unknown')
```

**ПОСЛЕ**:
```python
for order in orders:
    # OrderResult атрибуты
    order_type = order.type.upper() if order.type else ''
    order_side = order.side.lower() if order.side else ''

    # CCXT raw data из order.info
    reduce_only = order.info.get('reduceOnly', False)

    if (order_type == 'STOP_MARKET' and
        order_side == expected_side and
        reduce_only):
        protection_sl_orders.append(order)

# ...
for order in protection_sl_orders:
    order_id = order.id  # OrderResult атрибут
    stop_price = order.info.get('stopPrice', 'unknown')  # CCXT raw
```

### Шаг 2: Создать бэкап

```bash
cp protection/trailing_stop.py protection/trailing_stop.py.backup_before_orderresult_fix
```

### Шаг 3: Применить исправление

1. Заменить `order.get('type')` → `order.type`
2. Заменить `order.get('side')` → `order.side`
3. Заменить `order['id']` → `order.id`
4. Заменить `order.get('stopPrice')` → `order.info.get('stopPrice')`
5. Заменить `order.get('reduceOnly')` → `order.info.get('reduceOnly')`

### Шаг 4: Проверить синтаксис

```bash
python -m py_compile protection/trailing_stop.py
```

### Шаг 5: Коммит

```bash
git add protection/trailing_stop.py
git commit -m "fix: use OrderResult attributes instead of dict access

Changes:
- trailing_stop.py:791: order.get('type') -> order.type
- trailing_stop.py:792: order.get('side') -> order.side
- trailing_stop.py:793: order.get('reduceOnly') -> order.info.get('reduceOnly')
- trailing_stop.py:803: order['id'] -> order.id
- trailing_stop.py:804: order.get('stopPrice') -> order.info.get('stopPrice')

Root cause: ExchangeManager.fetch_open_orders() returns List[OrderResult],
not List[Dict]. OrderResult is a dataclass with attributes, not dict methods.

Fixes: AttributeError when TS activation tries to cancel Protection SL on Binance"
```

## Тестирование

### Тест 1: Синтаксис
```bash
python -m py_compile protection/trailing_stop.py
```

### Тест 2: Проверка типов (опционально)
```bash
mypy protection/trailing_stop.py --ignore-missing-imports
```

### Тест 3: Интеграционный тест
1. Запустить бота
2. Открыть Binance позицию
3. Дождаться прибыли 1.5%
4. Проверить, что TS активировался без ошибок
5. Проверить логи на отсутствие AttributeError

## Профилактика

### Проверить другие файлы на похожие проблемы

**Поиск**:
```bash
grep -r "fetch_open_orders" --include="*.py" | grep -v "\.git"
```

**Проверить**:
1. Все места, где используется `self.exchange.fetch_open_orders()`
2. Убедиться, что используются OrderResult атрибуты, а не dict методы

### Добавить type hints

```python
async def _cancel_protection_sl_if_binance(self, ts: TrailingStopInstance) -> bool:
    # Явно указать тип
    orders: List[OrderResult] = await self.exchange.fetch_open_orders(ts.symbol)

    for order in orders:
        # IDE и mypy будут подсказывать правильные атрибуты
        order_type = order.type.upper()
```

## Заключение

### Root Cause
ExchangeManager возвращает `List[OrderResult]` (dataclass), а код ожидал `List[Dict]` (CCXT raw).

### Impact
- **Критичность**: 🟡 MEDIUM
- **Частота**: Редко (только при активации TS на Binance)
- **Последствия**: TS не активируется, позиция остаётся в INACTIVE/WAITING

### Fix
Заменить dict доступ (`order.get()`, `order['key']`) на атрибуты dataclass (`order.type`, `order.id`).

### Risk
🟢 **Очень низкий** - чистое исправление типов, логика не меняется.

### Effort
⏱️ **5 минут** - 5 строк кода

---

**Подготовлено**: 2025-10-20
**Статус**: Ready for fix
**Приоритет**: P1 (блокирует активацию TS на Binance)
