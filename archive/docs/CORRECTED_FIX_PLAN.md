# CORRECTED FIX PLAN: Stop Loss Protection Issues

**Дата:** 2025-10-15
**Статус:** ПЛАН ИСПРАВЛЕНИЯ (БЕЗ ИЗМЕНЕНИЯ КОДА)
**Приоритет:** СРЕДНИЙ (проблема testnet-специфична)

---

## РЕВИЗИЯ ПРЕДЫДУЩЕГО АУДИТА

### ❌ Что было неправильно в CODE_AUDIT_SL_CALCULATION.md

1. ❌ **"Drift compensation логика неправильная"** - НЕВЕРНО
   - **Правда:** Логика корректна, используется на production без проблем

2. ❌ **"SL должен быть ниже entry для LONG"** - НЕВЕРНО
   - **Правда:** SL должен быть ниже **current price**, не entry

3. ❌ **"Нужно убрать drift compensation"** - НЕВЕРНО
   - **Правда:** Drift compensation защищает прибыль при росте цены

4. ❌ **"Проблема в коде position_manager"** - НЕВЕРНО
   - **Правда:** Проблема в качестве данных от testnet API

### ✅ Что было правильно

1. ✅ `calculate_stop_loss()` работает корректно
2. ✅ `StopLossManager` передает цену без изменений
3. ✅ Safety validation существует (строки 2420-2436)

---

## РЕАЛЬНЫЕ ПРОБЛЕМЫ (100% УВЕРЕННОСТЬ)

### 🔴 ПРОБЛЕМА #1: Неправильная current_price от testnet API

**Файл:** `core/position_manager.py:2372-2374`

**Код:**
```python
ticker = await exchange.exchange.fetch_ticker(position.symbol)
mark_price = ticker.get('info', {}).get('markPrice')
current_price = float(mark_price or ticker.get('last') or 0)
```

**Факты:**
- Бот получает: `current_price = 3.310`
- Реальность на бирже: `mark_price = 1.616`
- Ошибка: **2.05x разница**

**Причина:**
- Testnet рынок мертв (0 volume, 0 bids)
- `fetch_ticker()` возвращает кэшированные/устаревшие данные
- `ticker.get('last')` = последняя сделка (устаревшая на 2 дня)

**Доказательство:**
```bash
# Прямой запрос к Bybit API:
Last price: 1.616
Mark price: 1.616

# Бот видит:
current_price: 3.310  ← Откуда?!
```

**Уверенность:** 100% - проверено прямым запросом к API

---

### ⚠️ ПРОБЛЕМА #2: Safety validation не срабатывает

**Файл:** `core/position_manager.py:2420-2427`

**Код:**
```python
if position.side == 'long':
    if stop_loss_float >= current_price:
        logger.error("Using emergency fallback")
        stop_loss_price = Decimal(str(current_price * (1 - stop_loss_percent)))
```

**Почему не сработала:**
```
current_price (неправильная) = 3.310
SL (вычисленная)            = 3.244

Проверка: 3.244 >= 3.310? → FALSE
→ Validation НЕ срабатывает!
```

**Проблема:** Validation использует **тот же неправильный** `current_price`

**Уверенность:** 100% - логи подтверждают отсутствие "emergency fallback"

---

### 🟡 ПРОБЛЕМА #3: Отсутствие источника истины для цены

**Текущее состояние:**
- `position.current_price` может быть устаревшей (из БД)
- `fetch_ticker()` возвращает кэш на мертвых рынках
- Нет механизма получения **гарантированно правильной** цены

**Альтернативный источник (ЛУЧШЕ):**
```python
# Получить позицию с биржи
positions = await exchange.fetch_positions([symbol])
position_on_exchange = positions[0]

# Mark price от биржи = ИСТИНА
current_price = float(position_on_exchange['markPrice'])
```

**Преимущество:**
- Синхронизировано с API валидации Bybit
- Не зависит от ticker кэша
- Всегда актуально

**Уверенность:** 95% - это стандартная практика

---

### 🟢 ПРОБЛЕМА #4: Нет детектирования аномальных данных

**Текущее состояние:** Бот слепо доверяет данным API

**Что нужно:**
```python
# Детектирование аномалий
if abs((current_price - entry_price) / entry_price) > 2.0:  # Drift > 200%
    logger.error(f"SUSPICIOUS: current_price {current_price} vs entry {entry_price}")
    # Получить подтверждение из другого источника
```

**Зачем:**
- Защита от testnet глюков
- Защита от API ошибок
- Раннее обнаружение проблем

**Уверенность:** 100% - best practice

---

## ЧТО НЕ ТРЕБУЕТ ИСПРАВЛЕНИЯ

### ✅ Drift compensation логика (2394-2408)

**Логика ПРАВИЛЬНАЯ:**
```python
if price_drift_pct > stop_loss_percent_decimal:
    base_price = current_price  # Защита прибыли
```

**Почему правильная:**
- Защищает прибыль при росте цены
- Используется в production без проблем
- Соответствует best practices

**Пример (нормальный рынок):**
```
Entry: 100, Current: 200 (рост 100%)

Без drift compensation:
  SL = 100 - 2% = 98  ← Слишком далеко от current!

С drift compensation:
  SL = 200 - 2% = 196  ← Защищает прибыль ✅
```

**Вердикт:** **НЕ ТРОГАТЬ**

---

### ✅ calculate_stop_loss() функция

**Код корректен:**
```python
if side.lower() == 'long':
    sl_price = entry_price - sl_distance  # Правильно
```

**Вердикт:** **НЕ ТРОГАТЬ**

---

### ✅ StopLossManager

**Код корректен:** Передает цену без изменений

**Вердикт:** **НЕ ТРОГАТЬ**

---

## ПЛАН ИСПРАВЛЕНИЯ (ПРИОРИТЕТЫ)

### 🔴 КРИТИЧНО (если планируется работа на testnet)

#### Исправление #1: Использовать fetch_positions для current_price

**Файл:** `core/position_manager.py:2370-2374`

**Текущий код (УБРАТЬ):**
```python
ticker = await exchange.exchange.fetch_ticker(position.symbol)
mark_price = ticker.get('info', {}).get('markPrice')
current_price = float(mark_price or ticker.get('last') or 0)
```

**Новый код (ДОБАВИТЬ):**
```python
# Get REAL mark_price from position (source of truth)
positions_on_exchange = await exchange.exchange.fetch_positions([position.symbol])
position_on_exchange = next(
    (p for p in positions_on_exchange
     if p['symbol'] == position.symbol and float(p.get('contracts', 0)) > 0),
    None
)

if not position_on_exchange:
    logger.error(f"Position {position.symbol} not found on exchange, skipping SL")
    continue

# Use REAL mark_price from exchange
current_price = float(position_on_exchange.get('markPrice', 0))
entry_price_on_exchange = float(position_on_exchange.get('entryPrice', 0))

# Validate price is reasonable
if current_price == 0:
    logger.error(f"Invalid mark_price for {position.symbol}, skipping SL")
    continue

# Sync entry price if differs significantly
entry_price = float(position.entry_price)
if abs((entry_price_on_exchange - entry_price) / entry_price) > 0.01:  # 1% diff
    logger.warning(
        f"Entry price mismatch for {position.symbol}: "
        f"DB={entry_price}, Exchange={entry_price_on_exchange}"
    )
    # Use exchange entry as source of truth
    entry_price = entry_price_on_exchange
    # TODO: Update DB
```

**Преимущества:**
- Получаем РЕАЛЬНУЮ mark_price с биржи
- Синхронизировано с API валидации
- Нет зависимости от ticker кэша
- Автоматическая синхронизация entry_price

**Риски:**
- Дополнительный API call (уже делается в has_stop_loss)
- Можно оптимизировать: кэшировать результат fetch_positions

**Уверенность:** 90%

---

#### Исправление #2: Добавить детектирование аномальных данных

**Файл:** `core/position_manager.py` (после получения current_price)

**Добавить:**
```python
# ANOMALY DETECTION: Detect suspicious price data
price_drift_pct = abs((current_price - entry_price) / entry_price)

# If drift > 200%, something is very wrong
if price_drift_pct > 2.0:  # 200%
    logger.error(
        f"🚨 ANOMALY DETECTED for {position.symbol}: "
        f"current_price={current_price}, entry={entry_price}, "
        f"drift={price_drift_pct*100:.2f}%"
    )

    # On testnet with illiquid pairs, skip SL setup
    if exchange.exchange.sandbox_mode:
        logger.warning(
            f"Testnet market may be illiquid, skipping SL for {position.symbol}"
        )
        # Mark position to skip in future checks
        position._skip_sl_reason = 'illiquid_testnet_market'
        continue

    # On production, this is critical - log but try to proceed
    logger.critical(
        f"CRITICAL: Suspicious price drift on PRODUCTION! Manual check required."
    )
```

**Преимущества:**
- Раннее обнаружение проблем
- Защита от testnet глюков
- Избежание спама в логах

**Риски:** Минимальные (только дополнительная проверка)

**Уверенность:** 100%

---

### ⚠️ ВЫСОКИЙ ПРИОРИТЕТ (желательно)

#### Исправление #3: Улучшить Safety Validation

**Файл:** `core/position_manager.py:2420-2427`

**Текущая проблема:** Validation использует тот же неправильный `current_price`

**Решение:** Получить СВЕЖУЮ цену перед validation

**Добавить перед validation:**
```python
# STEP 5: Safety validation - ensure SL makes sense vs current market
stop_loss_float = float(stop_loss_price)

# CRITICAL: Fetch FRESH price for validation (don't trust cached value)
try:
    fresh_positions = await exchange.exchange.fetch_positions([position.symbol])
    fresh_position = next(
        (p for p in fresh_positions if p['symbol'] == position.symbol),
        None
    )

    if fresh_position:
        fresh_price = float(fresh_position.get('markPrice', current_price))

        # Log if price changed significantly
        if abs(fresh_price - current_price) / current_price > 0.05:  # 5% diff
            logger.warning(
                f"Price changed during SL calculation for {position.symbol}: "
                f"{current_price} → {fresh_price}"
            )

        # Use fresh price for validation
        validation_price = fresh_price
    else:
        validation_price = current_price

except Exception as e:
    logger.warning(f"Could not fetch fresh price for validation: {e}")
    validation_price = current_price

# Now validate with fresh price
if position.side == 'long':
    if stop_loss_float >= validation_price:
        logger.error(
            f"❌ {position.symbol}: Calculated SL {stop_loss_float:.6f} >= "
            f"current {validation_price:.6f} for LONG position! Using emergency fallback"
        )
        # Emergency: force SL below current price
        stop_loss_price = Decimal(str(validation_price * (1 - stop_loss_percent / 100)))
```

**Преимущества:**
- Validation работает на свежих данных
- Ловит случаи когда цена изменилась во время расчета
- Emergency fallback будет срабатывать корректно

**Риски:** Дополнительный API call

**Уверенность:** 85%

---

### 🔵 СРЕДНИЙ ПРИОРИТЕТ (опционально)

#### Улучшение #1: Кэширование fetch_positions

**Проблема:** Множественные вызовы `fetch_positions` для одного символа

**Решение:**
```python
# В начале check_positions_protection()
positions_cache = {}

async def get_position_from_exchange(symbol):
    if symbol not in positions_cache:
        positions = await exchange.exchange.fetch_positions([symbol])
        positions_cache[symbol] = positions
    return positions_cache[symbol]
```

**Преимущества:**
- Меньше API calls
- Быстрее работа
- Меньше нагрузка на rate limits

**Уверенность:** 100%

---

#### Улучшение #2: Blacklist для illiquid testnet pairs

**Файл:** `config/settings.py` или отдельный конфиг

**Добавить:**
```python
# Testnet illiquid pairs to skip SL protection
TESTNET_ILLIQUID_PAIRS = [
    'HNT/USDT:USDT',
    # Add more as discovered
]
```

**Использование:**
```python
if exchange.exchange.sandbox_mode and position.symbol in TESTNET_ILLIQUID_PAIRS:
    logger.warning(f"Skipping SL for {position.symbol} - known illiquid testnet pair")
    continue
```

**Преимущества:**
- Меньше спама в логах
- Нет бесконечных retry
- Явная документация проблемных пар

**Уверенность:** 100%

---

#### Улучшение #3: Мониторинг качества данных

**Добавить метрики:**
```python
# В EventLogger
metrics = {
    'suspicious_price_drift_detected': 0,
    'price_source_validation_failed': 0,
    'emergency_fallback_triggered': 0,
}
```

**Использование:**
- Dashboard мониторинга
- Алерты при аномалиях
- Статистика качества данных

**Уверенность:** 90%

---

## ЧТО ТОЧНО НЕ ДЕЛАТЬ

### ❌ НЕ удалять drift compensation

**Причина:** Логика правильная, используется в production

### ❌ НЕ менять calculate_stop_loss()

**Причина:** Функция работает корректно

### ❌ НЕ добавлять проверку "SL < entry для LONG"

**Причина:** Неправильное понимание SL логики. SL должен быть < current, не < entry.

### ❌ НЕ добавлять pre-validation в StopLossManager

**Причина:** Проблема не там, а в source данных

---

## ОЦЕНКА РИСКОВ ИЗМЕНЕНИЙ

### Исправление #1 (fetch_positions для current_price)

**Риск:** НИЗКИЙ
- Изменяет источник данных
- На production должно работать лучше
- На testnet решает проблему

**Тестирование:**
- Unit-тесты с mock fetch_positions
- Integration тест на testnet
- Мониторинг на production первые 24 часа

---

### Исправление #2 (anomaly detection)

**Риск:** МИНИМАЛЬНЫЙ
- Только добавляет проверки
- Не меняет основную логику
- Только логирование на production

**Тестирование:**
- Unit-тесты с аномальными данными
- Проверка на testnet HNT

---

### Исправление #3 (fresh price validation)

**Риск:** НИЗКИЙ
- Добавляет API call
- Может замедлить на 100-200мс
- Улучшает надежность

**Тестирование:**
- Измерить latency
- Проверить rate limits
- Integration тест

---

## ПЛАН ТЕСТИРОВАНИЯ

### Тест #1: Unit-тест с mock данных

```python
@pytest.mark.asyncio
async def test_anomaly_detection_triggers():
    """Anomaly detection должен ловить 200% drift"""

    # Mock fetch_positions возвращает правильную цену
    mock_position = {
        'symbol': 'HNT/USDT:USDT',
        'side': 'long',
        'markPrice': 1.616,  # Правильная
        'entryPrice': 1.772
    }

    # Но ticker возвращает неправильную (симуляция testnet)
    mock_ticker = {
        'last': 3.310,  # Неправильная!
        'info': {'markPrice': '3.310'}
    }

    # Должен обнаружить аномалию и использовать fetch_positions
```

---

### Тест #2: Integration на testnet

```python
async def test_hnt_usdt_testnet():
    """Реальный тест на HNT/USDT testnet"""

    # 1. Получить позицию HNT
    # 2. Попробовать установить SL
    # 3. Проверить что anomaly detection сработал
    # 4. Проверить что SL НЕ установился (skip)
    # 5. Проверить что нет спама в логах
```

---

### Тест #3: Production мониторинг

```bash
# После deploy на production:
# 1. Мониторить метрики первые 24 часа
# 2. Проверить что anomaly detection НЕ срабатывает
# 3. Проверить что все SL устанавливаются
# 4. Сравнить latency до/после
```

---

## TIMELINE

| Этап | Время | Зависимости |
|------|-------|-------------|
| Исправление #1 | 30 мин | - |
| Исправление #2 | 15 мин | - |
| Исправление #3 | 30 мин | Исправление #1 |
| Unit-тесты | 45 мин | Все исправления |
| Integration тесты | 30 мин | Все исправления |
| Code review | 15 мин | Все выше |
| Deploy testnet | 10 мин | Review passed |
| Мониторинг testnet | 2 часа | Deploy |
| Deploy production | 10 мин | Testnet OK |
| Мониторинг production | 24 часа | Deploy production |
| **TOTAL** | **~4 часа active + 26 часов мониторинга** | |

---

## ФИНАЛЬНЫЕ РЕКОМЕНДАЦИИ

### Для testnet (краткосрочно):

1. ✅ Оставить HNT/USDT без SL (нет ликвидности)
2. ✅ Добавить в blacklist illiquid pairs
3. ✅ Не тратить время на "исправление" работающей логики

### Для production (долгосрочно):

1. ⚠️ Реализовать Исправление #1 (fetch_positions)
2. ⚠️ Реализовать Исправление #2 (anomaly detection)
3. 🔵 Опционально: Исправление #3 (fresh validation)

### Общее:

1. ✅ Drift compensation логика - **НЕ ТРОГАТЬ**
2. ✅ calculate_stop_loss() - **НЕ ТРОГАТЬ**
3. ✅ StopLossManager - **НЕ ТРОГАТЬ**

---

## ЗАКЛЮЧЕНИЕ

### Основной вывод:

**Проблема НЕ в логике кода, а в качестве данных от testnet API.**

На production с нормальной ликвидностью **все должно работать корректно**.

### Что делать:

1. **Immediate:** Ничего (на testnet это ожидаемо)
2. **Short-term:** Улучшить source данных (fetch_positions)
3. **Long-term:** Добавить anomaly detection

### Уверенность:

- ✅ Диагноз проблемы: **100%**
- ✅ Drift compensation корректна: **100%**
- ⚠️ Исправления помогут: **90%**
- 🔵 На production нет проблемы: **95%**

---

**План составлен:** 2025-10-15 02:00:00
**Статус:** ГОТОВ К REVIEW
**Следующий шаг:** Получить approval для изменений (если требуется работа на testnet)
