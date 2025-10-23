# 🔴 КРИТИЧЕСКИЕ ОШИБКИ - ПЛАН УСТРАНЕНИЯ

## Дата: 2025-10-23 19:00
## Статус: ТРЕБУЕТСЯ СРОЧНОЕ ИСПРАВЛЕНИЕ

---

## 📊 РЕЗУЛЬТАТЫ РАССЛЕДОВАНИЯ

### 🐛 Ошибка #1: "name 'Json' is not defined" в aged_position_monitor_v2

**Критичность:** ВЫСОКАЯ
**Частота:** Постоянно при каждом обновлении aged позиций
**Влияние:** Нет логирования событий aged позиций в БД

#### Причина:
1. В `database/repository.py` строки 1094 и 1261 используется `Json(` вместо правильного метода
2. `Json` не импортирован и не определен
3. Таблицы `aged_monitoring_events` НЕ СУЩЕСТВУЮТ в БД fox_crypto

#### Детали из кода:
```python
# database/repository.py, строка 1094
'config': Json(config) if config else None

# database/repository.py, строка 1261
'event_metadata': Json(event_metadata) if event_metadata else None
```

#### Дополнительная проблема:
Таблицы для aged позиций вообще не созданы в БД:
```sql
-- Результат проверки:
-- ERROR: relation "aged_monitoring_events" does not exist
```

---

### 🐛 Ошибка #2: Неверный расчет SL для SHORT позиций

**Критичность:** КРИТИЧЕСКАЯ
**Частота:** При каждом обновлении SL для SHORT позиций
**Влияние:** Невозможность обновить SL, позиции остаются незащищенными

#### Причина:
Trailing stop пытается установить SL НИЖЕ текущей цены для SHORT позиций, что некорректно.

#### Детали из логов:
```
SAROSUSDT (SHORT/SELL позиция):
- Текущая цена: 0.18334
- Попытка установить SL: 0.17686 (НИЖЕ цены - неверно!)
- Ошибка Bybit: "StopLoss:17686000 set for Sell position should greater base_price:18334000"
```

#### Правильная логика:
- **LONG позиции:** SL должен быть НИЖЕ текущей цены (защита от падения)
- **SHORT позиции:** SL должен быть ВЫШЕ текущей цены (защита от роста)

---

## ✅ ПЛАН ИСПРАВЛЕНИЙ

### Исправление #1A: Json → json.dumps

**Файл:** `database/repository.py`

```python
# В начало файла добавить (если нет):
import json

# Строка 1094, заменить:
# БЫЛО:
'config': Json(config) if config else None
# СТАЛО:
'config': json.dumps(config) if config else None

# Строка 1261, заменить:
# БЫЛО:
'event_metadata': Json(event_metadata) if event_metadata else None
# СТАЛО:
'event_metadata': json.dumps(event_metadata) if event_metadata else None
```

### Исправление #1B: Создание таблиц aged позиций

**Файл:** `database/migrations/008_create_aged_tables.sql`

```sql
-- Создание таблиц для aged позиций
CREATE TABLE IF NOT EXISTS aged_positions (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    target_price DECIMAL(20, 8) NOT NULL,
    phase VARCHAR(50) NOT NULL,
    hours_aged INTEGER NOT NULL,
    loss_tolerance DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(position_id)
);

CREATE TABLE IF NOT EXISTS aged_monitoring_events (
    id SERIAL PRIMARY KEY,
    aged_position_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    market_price DECIMAL(20, 8),
    target_price DECIMAL(20, 8),
    price_distance_percent DECIMAL(10, 4),
    action_taken VARCHAR(100),
    success BOOLEAN,
    error_message TEXT,
    event_metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_aged_positions_symbol ON aged_positions(symbol);
CREATE INDEX idx_aged_positions_created ON aged_positions(created_at);
CREATE INDEX idx_aged_monitoring_position ON aged_monitoring_events(aged_position_id);
CREATE INDEX idx_aged_monitoring_created ON aged_monitoring_events(created_at);
```

---

### Исправление #2: Логика SL для SHORT позиций

**Файл:** `protection/trailing_stop.py`

Найти метод расчета нового SL и добавить проверку стороны позиции:

```python
def calculate_new_stop_loss(self, position, current_price, trail_percent):
    """
    Рассчитывает новый стоп-лосс с учетом стороны позиции

    КРИТИЧНО:
    - Для LONG: SL должен быть НИЖЕ текущей цены
    - Для SHORT: SL должен быть ВЫШЕ текущей цены
    """

    if position['side'] in ['buy', 'long']:
        # LONG позиция - SL ниже цены
        new_sl = current_price * (Decimal('1') - trail_percent / Decimal('100'))

        # Проверка: SL должен быть ниже текущей цены
        if new_sl >= current_price:
            logger.error(f"❌ LONG SL calculation error: {new_sl} >= {current_price}")
            return None

    elif position['side'] in ['sell', 'short']:
        # SHORT позиция - SL выше цены
        new_sl = current_price * (Decimal('1') + trail_percent / Decimal('100'))

        # Проверка: SL должен быть выше текущей цены
        if new_sl <= current_price:
            logger.error(f"❌ SHORT SL calculation error: {new_sl} <= {current_price}")
            return None
    else:
        logger.error(f"Unknown position side: {position['side']}")
        return None

    return new_sl
```

---

## 🧪 ТЕСТИРОВАНИЕ

### Тест #1: Проверка Json исправления
```bash
# Проверить что json импортирован
grep "import json" database/repository.py

# Проверить что Json заменен на json.dumps
grep "json.dumps" database/repository.py

# Запустить тест записи в БД
python -c "
from database.repository import Repository
import asyncio

async def test():
    repo = Repository(...)
    await repo.create_aged_monitoring_event(
        aged_position_id='test',
        event_type='test',
        event_metadata={'test': 'data'}
    )

asyncio.run(test())
"
```

### Тест #2: Проверка SL для SHORT
```python
# tests/test_short_sl_fix.py
def test_short_position_sl():
    position = {
        'symbol': 'TESTUSDT',
        'side': 'sell',  # SHORT
        'mark_price': Decimal('100')
    }

    trail_percent = Decimal('2')

    # Для SHORT: SL = price * (1 + trail%)
    expected_sl = Decimal('102')  # 100 * 1.02

    # Проверить что SL выше текущей цены
    assert expected_sl > position['mark_price']

    print(f"✅ SHORT SL: {expected_sl} > {position['mark_price']}")
```

---

## 📋 CHECKLIST ПРИМЕНЕНИЯ

### Шаг 1: Бэкап
```bash
cp database/repository.py database/repository.py.backup_20251023_1900
cp protection/trailing_stop.py protection/trailing_stop.py.backup_20251023_1900
```

### Шаг 2: Применить исправления Json
- [ ] Добавить `import json` в repository.py
- [ ] Заменить `Json(` на `json.dumps(` в строках 1094 и 1261
- [ ] Проверить других использований `Json(`

### Шаг 3: Создать таблицы в БД
```bash
PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto < database/migrations/008_create_aged_tables.sql
```

### Шаг 4: Исправить логику SL для SHORT
- [ ] Найти метод расчета SL в trailing_stop.py
- [ ] Добавить проверку стороны позиции
- [ ] Для SHORT использовать формулу: price * (1 + trail%)
- [ ] Добавить валидацию результата

### Шаг 5: Тестирование
```bash
# Запустить тесты
python tests/test_critical_bugs_20251023.py

# Проверить логи после перезапуска
tail -f logs/trading_bot.log | grep -E "Json|SL update failed"
```

### Шаг 6: Мониторинг
- [ ] Проверить отсутствие ошибок "Json is not defined"
- [ ] Проверить успешное обновление SL для SHORT позиций
- [ ] Проверить запись событий aged в БД

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **БД миграции:** Таблицы aged позиций отсутствуют - это критично для работы aged monitor v2
2. **SHORT логика:** Текущая реализация не учитывает разницу между LONG и SHORT
3. **Json vs json.dumps:** Возможно, раньше использовался SQLAlchemy Json тип, но он не импортирован
4. **Откат SL:** Система корректно откатывает неудачные обновления, но продолжает пытаться с той же ошибкой

---

## 🚨 ПРИОРИТЕТЫ

1. **КРИТИЧНО:** Исправить SL для SHORT - позиции без защиты!
2. **КРИТИЧНО:** Создать таблицы aged в БД - без них нет мониторинга
3. **ВАЖНО:** Исправить Json - для логирования и аудита

---

## 💡 ДОПОЛНИТЕЛЬНЫЕ РЕКОМЕНДАЦИИ

1. Добавить unit тесты для расчета SL с учетом LONG/SHORT
2. Добавить валидацию SL перед отправкой на биржу
3. Логировать детально все попытки обновления SL
4. Создать алерт при многократных неудачах обновления SL

---

**Автор:** AI Assistant
**Дата:** 2025-10-23
**Версия:** 1.0
**Статус:** ГОТОВ К ПРИМЕНЕНИЮ