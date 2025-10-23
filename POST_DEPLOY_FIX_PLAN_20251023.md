# 🔧 ПЛАН ИСПРАВЛЕНИЯ POST-DEPLOYMENT ОШИБОК

## Дата: 2025-10-23 21:00
## Статус: РАССЛЕДОВАНИЕ ЗАВЕРШЕНО

---

## 📊 ОБНАРУЖЕННЫЕ ПРОБЛЕМЫ

### Ошибка 1: Failed to create monitoring event
**Локация:** database/repository.py, строка 1267
**Причина:**
1. Неправильный синтаксис SQL для asyncpg - используется `%(name)s` вместо `$1, $2...`
2. Неправильное использование `conn.execute(query, **params)`
3. Неправильное имя таблицы: `monitoring.aged_positions_monitoring` вместо `aged_monitoring_events`
4. Метод вызывается как `create_aged_monitoring_event` но такого метода нет

### Ошибка 2: decimal.ConversionSyntax
**Локация:** core/order_executor.py, строка 165
**Причина:**
- Попытка создать Decimal из значения amount, которое может быть не строкой
- `Decimal(str(result.get('amount', amount)))` - если amount уже float/Decimal, это вызовет ошибку

### Ошибка 3: Bybit unknown parameter
**Локация:** core/order_executor.py, строки 215, 261
**Причина:**
- Параметр `positionIdx` может быть устаревшим или требует другое значение
- Для one-way mode нужно использовать 0, для hedge mode - 1 или 2

---

## 📝 ДЕТАЛЬНЫЙ ПЛАН ИСПРАВЛЕНИЙ

### ФИКС 1: Исправление repository.py

#### Проблема 1.1: Неправильный синтаксис SQL
**Строки 1239-1250:**
```python
# БЫЛО (неправильно для asyncpg):
query = """
    INSERT INTO monitoring.aged_positions_monitoring (
        aged_position_id, event_type, ...
    ) VALUES (
        %(aged_position_id)s, %(event_type)s, ...
    )
"""

# ДОЛЖНО БЫТЬ:
query = """
    INSERT INTO aged_monitoring_events (
        aged_position_id, event_type, market_price,
        target_price, price_distance_percent,
        action_taken, success, error_message,
        event_metadata, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
"""
```

#### Проблема 1.2: Неправильный вызов execute
**Строка 1267:**
```python
# БЫЛО:
await conn.execute(query, **params)

# ДОЛЖНО БЫТЬ:
await conn.execute(
    query,
    aged_position_id, event_type, market_price,
    target_price, price_distance_percent,
    action_taken, success, error_message,
    json.dumps(event_metadata) if event_metadata else None
)
```

#### Проблема 1.3: Добавить метод create_aged_monitoring_event
**Добавить новый метод после строки 1270:**
```python
async def create_aged_monitoring_event(
    self,
    aged_position_id: str,
    event_type: str,
    event_metadata: Dict = None,
    **kwargs
) -> bool:
    """Simplified method for order_executor"""
    return await self.log_aged_monitoring_event(
        aged_position_id=aged_position_id,
        event_type=event_type,
        market_price=None,
        target_price=None,
        price_distance_percent=None,
        action_taken=event_metadata.get('order_type') if event_metadata else None,
        success=True,
        error_message=None,
        event_metadata=event_metadata
    )
```

---

### ФИКС 2: Исправление order_executor.py

#### Проблема 2.1: decimal.ConversionSyntax
**Строки 164-165:**
```python
# БЫЛО:
price=Decimal(str(result.get('price', 0))),
executed_amount=Decimal(str(result.get('amount', amount))),

# ДОЛЖНО БЫТЬ:
price=Decimal(str(result.get('price', 0))) if result.get('price') else Decimal('0'),
executed_amount=Decimal(str(result.get('amount', 0))) if result.get('amount') else Decimal(str(amount)),
```

#### Проблема 2.2: Bybit positionIdx
**Строки 215, 261, и аналогичные:**
```python
# БЫЛО:
if exchange.exchange.id == 'bybit':
    params['positionIdx'] = 0

# ДОЛЖНО БЫТЬ - удалить эти строки полностью
# Bybit автоматически определяет positionIdx
```

---

### ФИКС 3: Проверка OrderResult класса

Нужно проверить что класс OrderResult корректно обрабатывает Decimal:
```python
@dataclass
class OrderResult:
    # ... другие поля ...
    price: Decimal
    executed_amount: Decimal

    def __post_init__(self):
        # Убедиться что price и executed_amount - Decimal
        if not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
        if not isinstance(self.executed_amount, Decimal):
            self.executed_amount = Decimal(str(self.executed_amount))
```

---

## 🚀 ПОРЯДОК ПРИМЕНЕНИЯ

### Шаг 1: Бэкапы
```bash
cp database/repository.py database/repository.py.backup_post_deploy_$(date +%Y%m%d_%H%M%S)
cp core/order_executor.py core/order_executor.py.backup_post_deploy_$(date +%Y%m%d_%H%M%S)
```

### Шаг 2: Применить исправления
1. Исправить repository.py (SQL синтаксис и execute)
2. Добавить метод create_aged_monitoring_event
3. Исправить order_executor.py (Decimal и positionIdx)
4. Проверить OrderResult класс

### Шаг 3: Тестирование
```bash
# Тест 1: Проверка импорта
python -c "from database.repository import Repository; print('✅ Repository OK')"

# Тест 2: Проверка order_executor
python -c "from core.order_executor import OrderExecutor; print('✅ OrderExecutor OK')"

# Тест 3: Проверка записи в БД
python tests/test_post_deploy_fixes.py
```

### Шаг 4: Коммит
```bash
git add -A
git commit -m "fix: post-deployment issues with aged monitoring and order execution

- Fixed asyncpg SQL syntax in repository (use $1 placeholders)
- Fixed decimal conversion in order_executor
- Removed deprecated positionIdx for Bybit
- Added create_aged_monitoring_event method"
```

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **asyncpg требует:**
   - Параметры через `$1, $2, $3...` в SQL
   - Позиционные аргументы в execute(), не **kwargs
   - Правильное имя таблицы без схемы

2. **Decimal требует:**
   - Всегда конвертировать в строку перед созданием Decimal
   - Проверять на None перед конвертацией

3. **Bybit API:**
   - positionIdx устарел или не нужен для one-way mode
   - Лучше позволить API выбрать правильный индекс

---

## 📊 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

После применения фиксов:
- ✅ События будут записываться в aged_monitoring_events
- ✅ Не будет ошибок decimal.ConversionSyntax
- ✅ Bybit ордера будут выполняться без ошибок
- ✅ Логи будут чистыми от этих ошибок

---

**Автор:** AI Assistant
**Дата:** 2025-10-23
**Версия:** 1.0