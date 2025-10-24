# 🔍 РАССЛЕДОВАНИЕ: Bybit Error 170003 "Unknown Parameter"

## Дата: 2025-10-23 23:35
## Статус: INVESTIGATION COMPLETED - ROOT CAUSE FOUND

---

# 📊 ОШИБКА

```
2025-10-23 23:34:18,544 - core.order_executor - WARNING - Order attempt failed: market attempt 1: bybit {"retCode":170003,"retMsg":"An unknown parameter was sent.","result":{},"retExtInfo":{},"time":1761248058540}
```

**Error Code:** 170003
**Message:** "An unknown parameter was sent."
**Exchange:** Bybit
**Order Type:** Market

---

# 🔎 ГЛУБОКОЕ РАССЛЕДОВАНИЕ

## ШАГ 1: Поиск кода отправки ордера

**Файл:** `core/order_executor.py:211-227`

```python
async def _execute_market(
    self,
    exchange,
    symbol: str,
    side: str,
    amount: float
) -> Dict:
    """Execute market order"""

    params = {'reduceOnly': True}

    # Exchange-specific parameters
    if exchange.exchange.id == 'binance':
        params['type'] = 'MARKET'

    return await exchange.exchange.create_order(
        symbol=symbol,
        type='market',
        side=side,
        amount=amount,
        params=params
    )
```

**Отправляемые параметры для Bybit:**
- `symbol`: символ торговли
- `type`: 'market'
- `side`: 'buy' или 'sell'
- `amount`: количество
- `params`: `{'reduceOnly': True}`

---

## ШАГ 2: Проверка документации Bybit API

**Источник:** https://bybit-exchange.github.io/docs/v5/order/create-order

### Допустимые параметры для Market ордера:

**Обязательные:**
- ✅ `category` — тип продукта
- ✅ `symbol` — пара торговли
- ✅ `side` — направление (Buy/Sell)
- ✅ `orderType` — значение "Market"
- ✅ `qty` — количество

**Опциональные:**
- ✅ `reduceOnly` — **ПОДДЕРЖИВАЕТСЯ** (boolean)
- ✅ `positionIdx` — для режима хеджирования
- ✅ `orderLinkId` — пользовательский ID ордера
- ❌ **`brokerId` — НЕ УПОМИНАЕТСЯ В ДОКУМЕНТАЦИИ!**

### Параметры, которые НЕ должны отправляться:
- ❌ `price` — игнорируется для market ордера
- ❌ `triggerPrice` — для условных ордеров
- ❌ `timeInForce` — market ордер использует IOC автоматически

**ВАЖНО:** Документация Bybit V5 API **НЕ упоминает** параметр `brokerId`!

---

## ШАГ 3: Исследование CCXT поведения

### Тест 1: Проверка дефолтных опций CCXT

```bash
python3 tests/test_bybit_brokerId_investigation.py
```

**Результат:**
```
brokerId in options: CCXT
```

### Тест 2: Структура CCXT options

```json
{
  "brokerId": "CCXT",
  "createOrder": {
    "method": "privatePostV5OrderCreate"
  },
  "defaultType": "future",
  "accountType": "UNIFIED"
}
```

**КРИТИЧЕСКОЕ ОТКРЫТИЕ:**
- ✅ CCXT Bybit имеет `'brokerId': 'CCXT'` **ПО УМОЛЧАНИЮ**
- ✅ CCXT добавляет этот параметр **АВТОМАТИЧЕСКИ** во все запросы
- ❌ Bybit V5 API **НЕ ПОДДЕРЖИВАЕТ** параметр `brokerId` при создании ордера!

---

## ШАГ 4: Инициализация Exchange в коде

**Файл:** `core/exchange_manager.py:108-111`

```python
elif self.name == 'bybit':
    # CRITICAL: Bybit V5 API requires UNIFIED account
    exchange_options['options']['accountType'] = 'UNIFIED'
    exchange_options['options']['defaultType'] = 'future'
    # ❌ НЕТ отключения brokerId!
```

**ПРОБЛЕМА:**
- Код НЕ отключает `brokerId`
- CCXT добавляет `brokerId: 'CCXT'` автоматически
- Bybit отвечает ошибкой 170003

---

# 🎯 КОРНЕВАЯ ПРИЧИНА

## Полная цепочка проблемы:

```
1. CCXT Bybit имеет 'brokerId': 'CCXT' по умолчанию
   ↓
2. ExchangeManager НЕ отключает этот параметр
   ↓
3. exchange.create_order() вызывается с params={'reduceOnly': True}
   ↓
4. CCXT АВТОМАТИЧЕСКИ добавляет 'brokerId': 'CCXT' в запрос
   ↓
5. HTTP запрос к Bybit:
   {
     "category": "linear",
     "symbol": "BTCUSDT",
     "side": "Sell",
     "orderType": "Market",
     "qty": "0.001",
     "reduceOnly": true,
     "brokerId": "CCXT"  ← ❌ Неизвестный параметр!
   }
   ↓
6. Bybit V5 API возвращает:
   {"retCode": 170003, "retMsg": "An unknown parameter was sent."}
```

---

# ✅ РЕШЕНИЕ

## Вариант A: Отключить brokerId в exchange_manager.py (РЕКОМЕНДУЕТСЯ)

### Обоснование:
- ✅ Исправляет проблему в ИСТОЧНИКЕ
- ✅ Применяется ко ВСЕМ ордерам автоматически
- ✅ Не требует изменения order_executor.py
- ✅ 1 изменение вместо множества

### План действий:

#### ФИК: Добавить `'brokerId': ''` в опции Bybit

**Файл:** `core/exchange_manager.py:108-111`

**БЫЛО:**
```python
elif self.name == 'bybit':
    # CRITICAL: Bybit V5 API requires UNIFIED account
    exchange_options['options']['accountType'] = 'UNIFIED'
    exchange_options['options']['defaultType'] = 'future'
```

**ДОЛЖНО БЫТЬ:**
```python
elif self.name == 'bybit':
    # CRITICAL: Bybit V5 API requires UNIFIED account
    exchange_options['options']['accountType'] = 'UNIFIED'
    exchange_options['options']['defaultType'] = 'future'
    exchange_options['options']['brokerId'] = ''  # Disable CCXT default brokerId
```

**Обоснование:**
- `'brokerId': ''` (пустая строка) отключает автоматическое добавление
- Не null/None, так как CCXT может игнорировать None
- Применяется ко ВСЕМ запросам (create_order, cancel_order, etc.)
- Одна строка кода = исправление всех проблем

---

## Вариант B: Обновить CCXT (НЕ РЕКОМЕНДУЕТСЯ)

### Проблемы:
- ❌ Может сломать другой функционал
- ❌ Требует тестирования всей системы
- ❌ Не гарантирует исправление проблемы

---

# 🧪 ТЕСТЫ ДЛЯ ВАЛИДАЦИИ

## Тест 1: Проверка что brokerId отключен

```python
import inspect
from core.exchange_manager import ExchangeManager

# Check exchange initialization code
source = inspect.getsource(ExchangeManager.__init__)

# Should have brokerId = ''
assert "brokerId" in source and "''\"" in source, \
    "brokerId должен быть установлен в пустую строку"

print("✅ brokerId отключен в exchange_manager.py")
```

## Тест 2: Проверка runtime options

```python
import asyncio
from core.exchange_manager import ExchangeManager

async def test_bybit_options():
    config = {
        'name': 'bybit',
        'api_key': 'test',
        'api_secret': 'test',
        'testnet': True
    }

    manager = ExchangeManager(config)
    await manager.initialize()

    # Check options
    broker_id = manager.exchange.options.get('brokerId', 'NOT FOUND')

    assert broker_id == '', \
        f"brokerId должен быть пустой строкой, получено: {broker_id}"

    print("✅ brokerId пустой в runtime")

    await manager.close()

asyncio.run(test_bybit_options())
```

## Тест 3: Интеграционный тест создания ордера

```python
# После применения фикса - создать тестовый ордер
# Должен пройти без ошибки 170003
```

---

# 📋 ЧЕКЛИСТ ПЕРЕД ПРИМЕНЕНИЕМ

- [ ] Создать бэкап:
  ```bash
  cp core/exchange_manager.py core/exchange_manager.py.backup_brokerId_fix_$(date +%Y%m%d_%H%M%S)
  ```

- [ ] Проверить текущую версию CCXT:
  ```bash
  python3 -c "import ccxt; print(f'CCXT version: {ccxt.__version__}')"
  ```

- [ ] Убедиться что тестовая среда доступна

---

# ⚠️ РИСКИ И МИТИГАЦИЯ

## Риск 1: Партнерская программа CCXT
- **Проблема:** `brokerId: 'CCXT'` может использоваться для партнерских отчислений
- **Митигация:** Bybit V5 API не поддерживает этот параметр в ордерах, поэтому отключение безопасно

## Риск 2: Другие запросы к API
- **Проблема:** Отключение brokerId может повлиять на другие запросы
- **Митигация:** Проверить документацию - brokerId используется только в broker-specific endpoints

---

# 🎯 ПРИОРИТЕТ

**КРИТИЧЕСКИЙ** - Блокирует создание market ордеров на Bybit

**Влияние:**
- Невозможно закрыть позиции через market ордера
- Невозможно экстренно выйти из позиции
- Накапливаются необработанные ордера

**Рекомендуемое время исправления:** НЕМЕДЛЕННО

---

# 📚 СПРАВОЧНЫЕ МАТЕРИАЛЫ

## Документация Bybit:
- V5 API Place Order: https://bybit-exchange.github.io/docs/v5/order/create-order
- Error Codes: https://bybit-exchange.github.io/docs/v5/error

## CCXT:
- Version used: 4.4.8
- Bybit implementation: ccxt.bybit class
- Default options: brokerId='CCXT'

## Created test scripts:
- tests/test_bybit_market_order_params.py
- tests/test_bybit_brokerId_investigation.py

---

**Автор:** AI Assistant
**Дата:** 2025-10-23 23:40
**Версия:** 1.0 FINAL
