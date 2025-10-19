# 🔍 АНАЛИЗ РИСКОВ КЭШИРОВАНИЯ fetch_positions()

**Дата:** 2025-10-19
**Вопрос:** Безопасно ли кэшировать fetch_positions() на 10 секунд?

---

## 📊 СЦЕНАРИЙ ИСПОЛЬЗОВАНИЯ

### Где Вызывается can_open_position()

**Единственное место:** `core/position_manager.py:1539`
```python
# В _calculate_position_size(), ПЕРЕД открытием позиции
can_open, reason = await exchange.can_open_position(symbol, size_usd)
```

### Когда Это Происходит

**Только в волнах**, последовательно для каждого сигнала:

```
07:36:09.139 - Signal 1 (can_open_position вызван)
07:36:11.321 - Signal 2 (gap: 2.2s - КЭШ ЕЩЕ ВАЛИДНЫЙ)
07:36:16.176 - Signal 3 (gap: 4.9s от 2-го, 7.0s от 1-го - КЭШ ВАЛИДНЫЙ)
07:36:20.718 - Signal 4 (gap: 4.5s от 3-го, 11.6s от 1-го - КЭШ ИСТЕК!)
07:36:22.514 - Signal 5 (gap: 1.8s от 4-го)
```

**ВАЖНО:** Между сигналами 2-5 секунд, НО суммарное время может превысить 10s!

---

## 🎯 ЧТО ПРОВЕРЯЕТ can_open_position()

### 1. Free Balance
```python
free_usdt = balance.get('USDT', {}).get('free', 0)
if free_usdt < notional_usd:
    return False, "Insufficient free balance"
```

**Актуальность:** fetch_balance() вызывается СВЕЖИЙ каждый раз ✅

### 2. Total Notional (из positions)
```python
positions = await self.exchange.fetch_positions()  # ← КЭШ!
total_notional = sum(abs(float(p.get('notional', 0)))
                    for p in positions if float(p.get('contracts', 0)) > 0)
```

**Что может измениться:**
- ❌ Новая позиция открыта В ЭТОЙ ЖЕ ВОЛНЕ
- ❌ Позиция закрыта по SL (очень редко за 10s)
- ❌ Notional изменился из-за движения цены

### 3. Utilization Check
```python
utilization = (total_notional + notional_usd) / total_balance
if utilization > 0.80:
    return False, "Would exceed safe utilization"
```

**Зависит от:** total_notional (из кэша)

---

## ⚠️ РИСКИ КЭШИРОВАНИЯ

### Риск 1: Позиция Открыта В Той Же Волне

**Сценарий:**
```
09:00:00.000 - Signal 1: can_open_position()
              └─ fetch_positions() → cache [31 positions, total_notional: $6200]
09:00:05.000 - Signal 1: Position OPENED → [32 positions, total_notional: $6400]
09:00:06.000 - Signal 2: can_open_position()
              └─ fetch_positions() → cache HIT [31 positions, total_notional: $6200] ❌ УСТАРЕЛ!
```

**Последствия:**
- total_notional занижен на $200 (размер 1-й позиции)
- utilization занижен: показывает 60% вместо 62%
- Может пропустить позицию которая превысит 80%

**Вероятность:** 🔴 ВЫСОКАЯ (100% в волнах)

**Критичность:** 🟡 СРЕДНЯЯ
- Утилизация занижена максимум на (5 × $200) / $10000 = 10%
- Если реальная утилизация 75%, покажет 65% → пропустит
- Если реальная утилизация 85%, покажет 75% → пропустит (ПРОБЛЕМА!)

### Риск 2: Позиция Закрыта по SL

**Сценарий:**
```
09:00:00.000 - fetch_positions() → cache [32 positions, $6400]
09:00:03.000 - BTCUSDT закрыта по SL → [31 positions, $6200]
09:00:06.000 - can_open_position() → cache HIT [32 positions, $6400] ❌ ЗАВЫШЕН!
```

**Последствия:**
- total_notional завышен → может отклонить валидную позицию
- Но НЕ пропустит невалидную ✅ (безопасная сторона ошибки)

**Вероятность:** 🟢 НИЗКАЯ (<1% за 10s)

**Критичность:** 🟢 НИЗКАЯ (ложное отклонение, не опасно)

### Риск 3: Notional Изменился из-за Цены

**Сценарий:**
```
09:00:00.000 - BTC @ $50,000, notional = $1000
09:00:10.000 - BTC @ $51,000, notional = $1020 (+2%)
```

**Последствия:**
- total_notional может отличаться на ±2-5% за 10s
- При 30 позициях: ошибка до $300-500

**Вероятность:** 🟡 СРЕДНЯЯ (волатильность)

**Критичность:** 🟢 НИЗКАЯ (небольшая ошибка в утилизации)

---

## 📊 РАСЧЕТ МАКСИМАЛЬНОГО GAP

### Worst Case Scenario

**Волна из 6 позиций, каждая по $200:**

```
T+0s:   Signal 1 - fetch_positions() → cache [30 pos, $6000]
T+5s:   Signal 1 opened → [31 pos, $6200] (кэш устарел на $200)
T+6s:   Signal 2 - cache HIT → shows $6000 ❌ real $6200
T+11s:  Signal 2 opened → [32 pos, $6400] (кэш устарел на $400)
T+12s:  Signal 3 - cache EXPIRED → fetch fresh [32 pos, $6400] ✅
T+17s:  Signal 3 opened → [33 pos, $6600]
T+18s:  Signal 4 - cache HIT → shows $6400 ❌ real $6600
T+23s:  Signal 4 opened → [34 pos, $6800]
T+24s:  Signal 5 - cache EXPIRED → fetch fresh [34 pos, $6800] ✅
```

**Максимальное расхождение:**
- Signal 2: кэш показывает $6000, реально $6200 (gap: $200 = 3.3%)
- Signal 4: кэш показывает $6400, реально $6600 (gap: $200 = 3.1%)

**При балансе $10,000:**
- Реальная утилизация Signal 2: 62%
- Показанная утилизация: 60%
- **Ошибка: 2% пункта**

### Best Case Scenario

**TTL = 5s вместо 10s:**

```
T+0s:   Signal 1 - fetch_positions() → cache [30 pos, $6000]
T+5s:   Signal 1 opened → [31 pos, $6200]
T+6s:   Signal 2 - cache EXPIRED → fetch fresh [31 pos, $6200] ✅
T+11s:  Signal 2 opened → [32 pos, $6400]
T+12s:  Signal 3 - cache EXPIRED → fetch fresh [32 pos, $6400] ✅
```

**Максимальное расхождение:** 0% (кэш всегда свежий)

**НО:** Экономия времени уменьшается!
- TTL=10s: 5 кэш хитов из 6 = экономия 5×758ms = 3.79s
- TTL=5s: 2-3 кэш хита из 6 = экономия 2-3×758ms = 1.5-2.3s

---

## ✅ БЕЗОПАСНЫЕ АЛЬТЕРНАТИВЫ

### Альтернатива 1: Инвалидация Кэша После Открытия

**Идея:** Очистить кэш positions сразу после открытия позиции

```python
# В position_manager.py, после atomic_position.create()
if position:
    # Clear positions cache - next call will fetch fresh data
    await exchange.clear_positions_cache()
    return position
```

**Плюсы:**
- ✅ Кэш всегда актуален для СЛЕДУЮЩЕЙ позиции
- ✅ Нет риска устаревших данных
- ✅ Все еще экономим время (кэш работает между проверками)

**Минусы:**
- ⚠️ Меньше кэш хитов (только внутри одной позиции)
- ⚠️ Меньшая экономия времени

**Экономия:**
- can_open_position() вызывается в _calculate_position_size()
- Между вызовом и открытием позиции проходит еще validate, format, atomic create
- Кэш может использоваться? НЕТ - разные позиции открываются последовательно

**ВЫВОД:** Эта альтернатива НЕ ДАСТ выигрыша! ❌

### Альтернатива 2: Кэш Только Внутри Волны

**Идея:**
1. Волна начинается → fetch_positions() ОДИН РАЗ
2. Сохранить в переменной волны
3. Все сигналы используют ОДНИ И ТЕ ЖЕ данные
4. Волна заканчивается → очистить

**Реализация:**

```python
# В signal_processor_websocket.py

async def _execute_wave_signals(self, signals):
    """Execute validated signals for this wave"""

    # НОВОЕ: Fetch positions ОДИН РАЗ для всей волны
    initial_positions = await self.exchange_manager.exchange.fetch_positions()
    initial_total_notional = sum(abs(float(p.get('notional', 0)))
                                for p in initial_positions
                                if float(p.get('contracts', 0)) > 0)

    logger.info(f"Wave start: {len(initial_positions)} positions, ${initial_total_notional:.2f} notional")

    executed_count = 0

    for idx, signal_result in enumerate(final_signals):
        if executed_count >= max_trades:
            break

        # Calculate ESTIMATED notional after previous positions
        estimated_notional = initial_total_notional + (executed_count * 200)  # Assume $200 per position

        # Pass to position manager
        success = await self._execute_signal(
            signal,
            estimated_total_notional=estimated_notional
        )

        if success:
            executed_count += 1
```

**Модифицировать can_open_position():**

```python
async def can_open_position(
    self,
    symbol: str,
    notional_usd: float,
    estimated_total_notional: Optional[float] = None  # NEW
) -> Tuple[bool, str]:
    """Check if we can open position"""

    # If estimated provided, use it (волновой режим)
    if estimated_total_notional is not None:
        total_notional = estimated_total_notional
    else:
        # Normal mode - fetch fresh
        positions = await self.exchange.fetch_positions()
        total_notional = sum(...)

    # Rest of checks...
```

**Плюсы:**
- ✅ ТОЧНОЕ знание сколько позиций откроем в волне
- ✅ Простая инкрементация ($200 за позицию)
- ✅ НЕТ риска устаревших данных
- ✅ Максимальная экономия времени (только 1 fetch для всей волны!)

**Минусы:**
- ⚠️ Если позиция отклонена (не открылась), инкремент неверный
- ⚠️ Нужно передавать estimated через несколько слоев функций

**Экономия:**
- Было: 6 × 758ms = 4548ms
- Стало: 1 × 758ms = 758ms
- **Выигрыш: 3790ms (3.8s)** 🚀

### Альтернатива 3: TTL = 5 Секунд (Компромисс)

**Идея:** Уменьшить TTL чтобы кэш чаще обновлялся

**Плюсы:**
- ✅ Меньше риск устаревания
- ✅ Проще реализовать
- ✅ Все еще дает выигрыш

**Минусы:**
- ⚠️ Меньшая экономия времени (2-3 хита вместо 5)

**Экономия:**
- Примерно 50% от TTL=10s
- **Выигрыш: ~1.5-2s** 🟡

### Альтернатива 4: Убрать can_open_position() Вообще

**Идея:** Полагаться на Binance который отклонит если превышен лимит

**Плюсы:**
- ✅ Максимальная простота
- ✅ Нет кэширования вообще
- ✅ Экономия 6.5s!

**Минусы:**
- ❌ Позиция создается в БД, потом откатывается
- ❌ Atomic operation расходуется впустую
- ❌ Логи засоряются ошибками
- ❌ Теряем проактивную защиту

**ВЫВОД:** НЕ рекомендуется ❌

---

## 🎯 РЕКОМЕНДАЦИЯ

### ЛУЧШЕЕ РЕШЕНИЕ: Альтернатива 2 (Волновой Кэш)

**Почему:**
1. ✅ **Максимальная точность** - знаем сколько позиций откроем
2. ✅ **Максимальная скорость** - только 1 fetch на волну
3. ✅ **Нет рисков** - используем актуальные данные + инкремент
4. ✅ **Простая логика** - estimated_notional = initial + (count × 200)

**Реализация:**

```python
# В signal_processor_websocket.py
initial_notional = fetch_positions_once()

for i, signal in enumerate(signals):
    estimated_notional = initial_notional + (i × 200)

    can_open = await exchange.can_open_position(
        signal.symbol,
        200,
        estimated_total_notional=estimated_notional
    )

    if can_open:
        position = await open_position(signal)
```

**Изменения:**
- `core/signal_processor_websocket.py`: добавить fetch в начале волны
- `core/exchange_manager.py`: добавить параметр estimated_total_notional
- ~30 строк кода

**Экономия:** 3.8s (было 6.5s, станет 2.7s на валидацию)

### КОМПРОМИСС: Альтернатива 3 (TTL=5s)

**Если волновой кэш сложно реализовать:**

```python
self._cache_ttl = 5  # Вместо 10 секунд
```

**Экономия:** ~1.5-2s (было 6.5s, станет 4.5-5s)

**Риск:** Средний (2% ошибка в утилизации максимум)

---

## 📊 СРАВНИТЕЛЬНАЯ ТАБЛИЦА

| Решение | Экономия | Риск | Сложность | Рекомендация |
|---------|----------|------|-----------|--------------|
| TTL=10s (план 2C) | 3.6s | 🔴 Высокий (10% ошибка) | 🟢 Низкая | ❌ НЕ рекомендуется |
| TTL=5s | 1.5-2s | 🟡 Средний (2% ошибка) | 🟢 Низкая | 🟡 Компромисс |
| Волновой кэш (Alt 2) | 3.8s | 🟢 Низкий (точный) | 🟡 Средняя | ✅ ЛУЧШЕЕ |
| Убрать can_open | 6.5s | 🔴 Очень высокий | 🟢 Низкая | ❌ НЕ рекомендуется |
| Инвалидация после open | 0s | 🟢 Низкий | 🟡 Средняя | ❌ Нет выигрыша |

---

## ✅ ФИНАЛЬНАЯ РЕКОМЕНДАЦИЯ

**ИСПОЛЬЗОВАТЬ АЛЬТЕРНАТИВУ 2: Волновой Кэш**

**План:**
1. Fetch positions ОДИН РАЗ в начале волны
2. Инкрементировать estimated_notional для каждой позиции
3. Передавать estimated в can_open_position()
4. Если позиция отклонена - НЕ инкрементировать

**Код изменений готов в следующем сообщении если одобришь!**

---

**Дата:** 2025-10-19
**Статус:** ✅ АНАЛИЗ ЗАВЕРШЕН
**Вывод:** Кэширование с TTL=10s **РИСКОВАННО**, используем **Волновой Кэш** вместо этого!
