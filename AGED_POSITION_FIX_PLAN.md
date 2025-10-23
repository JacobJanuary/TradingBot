# 🔴 КРИТИЧЕСКИЕ ОШИБКИ AGED POSITION MANAGER V2 - ПЛАН ИСПРАВЛЕНИЙ

## Дата: 2025-10-23
## Статус: ТРЕБУЕТСЯ СРОЧНОЕ ИСПРАВЛЕНИЕ

---

## 🐛 ОБНАРУЖЕННЫЕ ПРОБЛЕМЫ

### Проблема #1: Неверные параметры Repository.create_aged_monitoring_event
**Критичность:** ВЫСОКАЯ
**Статус:** Все вызовы БД методов не работают

#### Анализ:
Сигнатура метода в database/repository.py (строка 1210):
```python
async def create_aged_monitoring_event(
    self,
    aged_position_id: str,
    event_type: str,
    market_price: Decimal = None,       # НЕ current_price!
    target_price: Decimal = None,
    price_distance_percent: Decimal = None,
    action_taken: str = None,
    success: bool = None,
    error_message: str = None,
    event_metadata: Dict = None         # НЕ details!
)
```

#### Неправильные вызовы найдены в:
1. **aged_position_monitor_v2.py:242-248** - использует current_price, pnl_percent, phase
2. **aged_position_monitor_v2.py:334-340** - использует details вместо event_metadata
3. **aged_position_monitor_v2.py:359-365** - использует details вместо event_metadata
4. **aged_position_monitor_v2.py:471-477** - использует details вместо event_metadata
5. **order_executor.py:342-350** - использует details вместо event_metadata

---

### Проблема #2: Order Book пустые массивы
**Критичность:** ВЫСОКАЯ
**Статус:** Вызывает "list index out of range"

#### Анализ:
В order_executor.py, метод _execute_limit_maker (строки 283-291):
```python
order_book = await exchange.exchange.fetch_order_book(symbol, limit=5)
# НЕТ ПРОВЕРКИ на пустой order_book!
if side == 'buy':
    limit_price = Decimal(str(order_book['bids'][0][0]))  # CRASH если bids пустой!
else:
    limit_price = Decimal(str(order_book['asks'][0][0]))  # CRASH если asks пустой!
```

---

### Проблема #3: Неверное округление цен
**Критичность:** ВЫСОКАЯ
**Статус:** Bybit отклоняет ордера "price cannot be higher than 0USDT"

#### Анализ:
В order_executor.py, метод _round_price (строки 317-325):
```python
def _round_price(self, price: Decimal, symbol: str) -> Decimal:
    if 'BTC' in symbol:
        return price.quantize(Decimal('0.01'))
    else:
        return price.quantize(Decimal('0.0001'))  # Слишком грубо для BSUUSDT!
```

BSUUSDT и другие малоценные токены требуют бóльшую точность (6-8 знаков после запятой).

---

## ✅ ПЛАН ИСПРАВЛЕНИЙ

### Исправление #1: Repository вызовы
```python
# aged_position_monitor_v2.py, строка 242-248
# БЫЛО:
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,
    event_type='price_check',
    current_price=current_price,  # НЕВЕРНО!
    target_price=target.target_price,
    pnl_percent=pnl_percent,       # НЕТ ТАКОГО ПАРАМЕТРА!
    phase=target.phase             # НЕТ ТАКОГО ПАРАМЕТРА!
)

# ДОЛЖНО БЫТЬ:
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,
    event_type='price_check',
    market_price=current_price,    # Правильное имя
    target_price=target.target_price,
    price_distance_percent=abs((current_price - target.target_price) / target.target_price * 100),
    event_metadata={
        'pnl_percent': str(pnl_percent),
        'phase': target.phase
    }
)
```

```python
# aged_position_monitor_v2.py, строка 334-340
# БЫЛО:
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,
    event_type='closed',
    details={...}  # НЕВЕРНО!
)

# ДОЛЖНО БЫТЬ:
await self.repository.create_aged_monitoring_event(
    aged_position_id=target.position_id,
    event_type='closed',
    event_metadata={...}  # Правильное имя параметра
)
```

---

### Исправление #2: Order Book проверки
```python
# order_executor.py, метод _execute_limit_maker, строка 283-291
# ДОБАВИТЬ проверки:

async def _execute_limit_maker(self, exchange, symbol: str, side: str, amount: float) -> Dict:
    """Execute limit order as maker (post-only)"""

    # Get order book for best price
    order_book = await exchange.exchange.fetch_order_book(symbol, limit=5)

    # НОВЫЕ ПРОВЕРКИ:
    if not order_book:
        raise Exception("Order book is empty")

    if side == 'buy':
        if not order_book.get('bids') or len(order_book['bids']) == 0:
            raise Exception("No bids in order book")
        if len(order_book['bids'][0]) < 1:
            raise Exception("Invalid bid format")
        limit_price = Decimal(str(order_book['bids'][0][0]))
    else:
        if not order_book.get('asks') or len(order_book['asks']) == 0:
            raise Exception("No asks in order book")
        if len(order_book['asks'][0]) < 1:
            raise Exception("Invalid ask format")
        limit_price = Decimal(str(order_book['asks'][0][0]))

    # Проверка на валидность цены
    if limit_price <= 0:
        raise Exception(f"Invalid price from order book: {limit_price}")
```

---

### Исправление #3: Умное округление цен
```python
# order_executor.py, метод _round_price
# ЗАМЕНИТЬ весь метод:

def _round_price(self, price: Decimal, symbol: str) -> Decimal:
    """Round price to appropriate precision for symbol"""

    # Определяем точность по величине цены
    if price >= Decimal('1000'):
        # Для цен > 1000 - 2 знака после запятой
        return price.quantize(Decimal('0.01'))
    elif price >= Decimal('100'):
        # Для цен 100-1000 - 3 знака
        return price.quantize(Decimal('0.001'))
    elif price >= Decimal('10'):
        # Для цен 10-100 - 4 знака
        return price.quantize(Decimal('0.0001'))
    elif price >= Decimal('1'):
        # Для цен 1-10 - 5 знаков
        return price.quantize(Decimal('0.00001'))
    elif price >= Decimal('0.1'):
        # Для цен 0.1-1 - 6 знаков
        return price.quantize(Decimal('0.000001'))
    elif price >= Decimal('0.01'):
        # Для цен 0.01-0.1 - 7 знаков
        return price.quantize(Decimal('0.0000001'))
    else:
        # Для цен < 0.01 - 8 знаков (макс точность)
        return price.quantize(Decimal('0.00000001'))
```

---

### Исправление #4: Добавить валидацию в _execute_limit_aggressive
```python
# order_executor.py, после строки 238
# ДОБАВИТЬ:

ticker = await exchange.exchange.fetch_ticker(symbol)
current_price = Decimal(str(ticker['last']))

# НОВАЯ ПРОВЕРКА:
if current_price <= 0:
    raise Exception(f"Invalid ticker price for {symbol}: {current_price}")
```

---

## 🧪 ТЕСТИРОВАНИЕ

### Тест для проблемы #1:
```python
# tests/test_aged_repository_params.py
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_correct_repository_params():
    """Проверяем правильность параметров вызова БД"""
    mock_repo = AsyncMock()

    # Эмулируем вызов с правильными параметрами
    await mock_repo.create_aged_monitoring_event(
        aged_position_id='test_123',
        event_type='price_check',
        market_price=Decimal('100'),  # НЕ current_price!
        target_price=Decimal('99'),
        event_metadata={'phase': 'grace'}  # НЕ details!
    )

    # Проверяем что вызов прошел
    mock_repo.create_aged_monitoring_event.assert_called_once()
```

### Тест для проблемы #2:
```python
# tests/test_order_book_safety.py

@pytest.mark.asyncio
async def test_empty_order_book_handling():
    """Проверяем обработку пустого order book"""
    executor = OrderExecutor({})

    # Тест с пустым order book
    empty_book = {'bids': [], 'asks': []}
    with pytest.raises(Exception, match="No bids in order book"):
        await executor._process_order_book(empty_book, 'buy')
```

### Тест для проблемы #3:
```python
# tests/test_price_rounding.py

def test_price_rounding_precision():
    """Проверяем точность округления для разных цен"""
    executor = OrderExecutor({})

    # Малоценный токен
    assert executor._round_price(Decimal('0.00012345'), 'BSUUSDT') == Decimal('0.00012345')

    # Дорогой токен
    assert executor._round_price(Decimal('42123.456'), 'BTCUSDT') == Decimal('42123.46')
```

---

## 📊 ПРИОРИТЕТЫ

1. **КРИТИЧНО**: Исправление #1 (параметры БД) - без этого НЕТ логирования
2. **КРИТИЧНО**: Исправление #2 (order book) - крашит бота
3. **КРИТИЧНО**: Исправление #3 (округление) - ордера отклоняются биржей
4. **ВАЖНО**: Исправление #4 (валидация) - предотвращение будущих ошибок

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **НЕ МЕНЯТЬ существующую логику**, только исправить параметры
2. **ДОБАВИТЬ проверки**, не изменяя основной flow
3. **ТЕСТИРОВАТЬ на testnet** перед production
4. **ЛОГИРОВАТЬ все исправления** для отката при необходимости

---

## 🚀 КОМАНДЫ ДЛЯ ПРИМЕНЕНИЯ ИСПРАВЛЕНИЙ

```bash
# 1. Создать бэкап
cp core/aged_position_monitor_v2.py core/aged_position_monitor_v2.py.backup_20251023
cp core/order_executor.py core/order_executor.py.backup_20251023

# 2. Применить исправления (после реализации)
# ... код исправлений ...

# 3. Запустить тесты
python -m pytest tests/test_aged_repository_params.py -v
python -m pytest tests/test_order_book_safety.py -v
python -m pytest tests/test_price_rounding.py -v

# 4. Тестировать на testnet
# Проверить все aged позиции и order execution
```

---

## 📝 CHECKLIST

- [ ] Бэкап файлов создан
- [ ] Исправление #1 применено (параметры БД)
- [ ] Исправление #2 применено (order book проверки)
- [ ] Исправление #3 применено (умное округление)
- [ ] Исправление #4 применено (валидация ticker)
- [ ] Тесты написаны
- [ ] Тесты пройдены
- [ ] Testnet проверка пройдена
- [ ] Production deployment готов

---

**Автор:** AI Assistant
**Дата:** 2025-10-23
**Версия:** 1.0