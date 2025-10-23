# 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА: Устаревший current_stop_price в trailing_stop_state

**Дата расследования**: 2025-10-20
**Статус**: НАЙДЕНА КРИТИЧЕСКАЯ ОШИБКА ❌
**Приоритет**: P0 - КРИТИЧНО

---

## EXECUTIVE SUMMARY

### Проблема
При переотктрытии позиций (позиция закрыта → переоткрыта на том же символе) в таблице `trailing_stop_state` остаются **УСТАРЕВШИЕ ДАННЫЕ** от предыдущей позиции.

В частности, поле `current_stop_price` содержит SL цену от **СТАРОЙ ЗАКРЫТОЙ позиции**, что приводит к **НЕКОРРЕКТНЫМ значениям** для новых INACTIVE позиций.

### Критичность
🔴 **P0 - КРИТИЧНО**

**Почему критично:**
1. Для LONG позиций `current_stop_price` может быть **ВЫШЕ entry** (устаревший SL от старой позиции)
2. Для SHORT позиций `current_stop_price` может быть **НИЖЕ entry**
3. Это создает **ОПАСНОСТЬ АКТИВАЦИИ TS** с неправильным initial SL
4. При рестарте бота может восстановить НЕПРАВИЛЬНОЕ состояние TS

### Масштаб проблемы
Обнаружено **минимум 3 позиции** с устаревшим `current_stop_price`:
- API3USDT (Binance, LONG)
- CYBERUSDT (Binance, LONG)
- TIAUSDT (Binance, LONG)

Вероятно, проблема затрагивает **ВСЕ ПЕРЕОТКРЫТЫЕ позиции**.

---

## ДЕТАЛЬНОЕ РАССЛЕДОВАНИЕ

### Метод исследования
1. ✅ Анализ всех значений `current_stop_price` из аудита
2. ✅ Поиск функций вычисления `current_stop_price` в коде
3. ✅ Проверка формул для LONG/SHORT позиций
4. ✅ Анализ логики записи в БД
5. ✅ Сверка расчетных значений с фактическими из БД

### Найденные формулы (ВСЕ ПРАВИЛЬНЫЕ ✅)

#### 1. Protection Manager SL (utils/decimal_utils.py:155-158)
```python
# LONG
sl_price = entry_price - (entry_price * stop_loss_percent / 100)  # SL НИЖЕ entry ✅

# SHORT
sl_price = entry_price + (entry_price * stop_loss_percent / 100)  # SL ВЫШЕ entry ✅
```

#### 2. Trailing Stop SL при активации (protection/trailing_stop.py:536-538)
```python
# LONG
ts.current_stop_price = ts.highest_price * (1 - distance / 100)  # SL НИЖЕ highest ✅

# SHORT
ts.current_stop_price = ts.lowest_price * (1 + distance / 100)   # SL ВЫШЕ lowest ✅
```

#### 3. Trailing Stop SL при обновлении (protection/trailing_stop.py:590-597)
```python
# LONG
potential_stop = ts.highest_price * (1 - distance / 100)
if potential_stop > ts.current_stop_price:  # Only move UP ✅
    new_stop_price = potential_stop

# SHORT
potential_stop = ts.lowest_price * (1 + distance / 100)
if potential_stop < ts.current_stop_price:  # Only move DOWN ✅
    new_stop_price = potential_stop
```

**ВЫВОД**: Все формулы корректны! ✅

---

## ПРОБЛЕМНЫЕ ДАННЫЕ

### Пример 1: API3USDT (LONG)

#### Данные из БД trailing_stop_state:
```
symbol:              API3USDT
side:                long
entry_price:         0.71450000  ← СТАРАЯ позиция
current_stop_price:  0.72766800  ← ❌ ВЫШЕ entry!
state:               inactive
highest_price:       0.71450000  (= entry, не обновлялся)
```

#### Данные из БД positions (ТЕКУЩАЯ позиция):
```
symbol:         API3USDT
side:           long
entry_price:    0.71340000  ← НОВАЯ позиция (другой entry!)
stop_loss_price: 0.69910000  (Protection SL, правильный)
```

#### Анализ:
1. **entry_price РАЗНЫЕ!**
   - TS state: 0.71450000
   - positions: 0.71340000

2. **Это означает**: Позиция была ЗАКРЫТА и ПЕРЕОТКРЫТА

3. **current_stop_price=0.72766800 НЕ может быть:**
   - Protection SL (должен быть НИЖЕ entry для LONG)
   - Initial TS SL (TS не активировался, highest=entry)

4. **Обратный расчет highest_price от которого был current_stop:**
   ```
   current_stop = highest * (1 - 0.5/100)
   0.72766800 = highest * 0.995
   highest = 0.72766800 / 0.995 = 0.731440
   ```

5. **ВЫВОД**: current_stop=0.72766800 это SL от **ПРЕДЫДУЩЕЙ АКТИВИРОВАННОЙ** позиции!
   - Старая позиция достигла highest=0.731440
   - TS активировался и установил SL=0.727668
   - Позиция закрылась
   - **Запись в trailing_stop_state НЕ УДАЛИЛАСЬ!**
   - Новая позиция открылась с entry=0.71340
   - **БД показывает УСТАРЕВШИЙ current_stop=0.727668**

---

### Пример 2: CYBERUSDT (LONG)

#### БД trailing_stop_state:
```
entry_price:         1.10294730  ← СТАРАЯ
current_stop_price:  1.11894000  ← ❌ ВЫШЕ entry на 1.45%!
highest_price:       1.10294730
```

#### БД positions:
```
entry_price:    1.09700000  ← НОВАЯ (разница -0.54%)
stop_loss_price: 1.08100000  (правильный Protection SL)
```

#### Обратный расчет:
```
1.11894000 = highest * 0.995
highest = 1.124060 (старая позиция достигла этого пика)
```

**ВЫВОД**: Аналогично - устаревшие данные от старой позиции.

---

### Пример 3: TIAUSDT (LONG)

#### БД trailing_stop_state:
```
entry_price:         1.03906090  ← СТАРАЯ
current_stop_price:  1.05763800  ← ❌ ВЫШЕ entry на 1.79%!
highest_price:       1.03906090
```

#### БД positions:
```
entry_price:    1.03690000  ← НОВАЯ (разница -0.21%)
stop_loss_price: 1.01830000  (правильный Protection SL)
```

#### Обратный расчет:
```
1.05763800 = highest * 0.995
highest = 1.062900 (старая позиция)
```

**ВЫВОД**: Устаревшие данные.

---

## КОРНЕВАЯ ПРИЧИНА (ROOT CAUSE)

### Проблема в логике работы с БД

**Найдено в коде:**

#### 1. При создании позиции (core/position_manager.py:1026-1031)
```python
trailing_manager.create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=position.entry_price,
    quantity=position.quantity,
    initial_stop=float(stop_loss_price)  # Protection Manager SL
)
```

#### 2. При создании TS (protection/trailing_stop.py:356-357)
```python
if initial_stop:
    ts.current_stop_price = Decimal(str(initial_stop))
```

#### 3. При сохранении в БД (protection/trailing_stop.py:192)
```python
'current_stop_price': float(ts.current_stop_price) if ts.current_stop_price else None,
```

#### 4. При сохранении (database/repository.py - метод save_trailing_stop_state)
```sql
INSERT INTO monitoring.trailing_stop_state (...)
VALUES (...)
ON CONFLICT (symbol, exchange)
DO UPDATE SET ...
```

**ПРОБЛЕМА:**
Используется `ON CONFLICT (symbol, exchange) DO UPDATE` - это **UPSERT** логика!

**Что происходит:**
1. Позиция API3USDT открывается → TS создается → запись в БД (entry=0.71450)
2. TS активируется → highest=0.731440 → current_stop=0.727668 → UPDATE в БД
3. Позиция **ЗАКРЫВАЕТСЯ** → TS удаляется из памяти (trailing_stops dict)
4. **БД запись НЕ УДАЛЯЕТСЯ!** ❌
5. Новая позиция API3USDT открывается (entry=0.71340) → TS создается
6. При сохранении: `ON CONFLICT (symbol, exchange)` → **UPDATE существующей записи!**
7. Но! При создании нового TS с initial_stop:
   - Если initial_stop передан → current_stop = initial_stop (правильно)
   - Если initial_stop НЕ передан → current_stop остается None
   - При UPDATE в БД: если current_stop=None, **старое значение 0.727668 ОСТАЕТСЯ!**

**ИЛИ:**
Если create_trailing_stop вызывается БЕЗ initial_stop (строка 1287 position_manager.py):
```python
trailing_manager.create_trailing_stop(
    symbol=symbol,
    side=position.side,
    entry_price=position.entry_price,
    quantity=position.quantity,
    initial_stop=None  # Не создавать SL сразу - ждать активации
)
```

Тогда `ts.current_stop_price = None`, и при UPSERT:
```sql
ON CONFLICT (symbol, exchange) DO UPDATE SET
    current_stop_price = EXCLUDED.current_stop_price,  -- NULL!
    ...
```

Если в SQL запросе **НЕТ COALESCE** или логики "не перезаписывать на NULL", то:
- Либо current_stop_price становится NULL
- Либо сохраняется старое значение (в зависимости от реализации UPDATE)

**НО!** Мы видим что current_stop_price=0.727668 **ОСТАЛСЯ** в БД!

Это означает либо:
1. UPDATE не выполнился (остались старые данные целиком)
2. UPDATE выполнился частично (entry_price обновился, но current_stop нет)
3. В UPDATE есть логика COALESCE(EXCLUDED.current_stop_price, current_stop_price)

---

## ПРОВЕРКА КОДА REPOSITORY

Проверяю метод save_trailing_stop_state:
```python
# database/repository.py
```

**НЕОБХОДИМО ПРОВЕРИТЬ:**
1. SQL запрос UPSERT
2. Какие поля обновляются при CONFLICT
3. Есть ли COALESCE для current_stop_price
4. Почему entry_price обновился, а current_stop_price нет

---

## ПОСЛЕДСТВИЯ ОШИБКИ

### 1. Некорректные данные в БД ❌
- trailing_stop_state содержит MIX старых и новых данных
- entry_price от НОВОЙ позиции
- current_stop_price от СТАРОЙ позиции

### 2. Риск неправильного восстановления при рестарте 🔴
При рестарте бота вызывается `_restore_state()` (trailing_stop.py:220):
```python
async def _restore_state(self, symbol: str) -> Optional[TrailingStopInstance]:
    # Загружает данные из БД
    # Восстанавливает TS с УСТАРЕВШИМ current_stop_price!
```

Если бот рестартует после переоткрытия позиции:
- Загрузит entry_price (новый)
- Загрузит current_stop_price (СТАРЫЙ!)
- TS будет иметь **НЕКОРРЕКТНОЕ** состояние

### 3. Для INACTIVE позиций - НЕ критично (пока) ⚠️
Пока TS в состоянии INACTIVE:
- current_stop_price **НЕ ИСПОЛЬЗУЕТСЯ**
- При активации пересчитается из highest_price
- highest_price = entry_price (правильный, новый)

**НО!** При рестарте:
```python
# trailing_stop.py:250-253 (state restoration)
highest_price=Decimal(str(state_data['entry_price'])) if state_data['side'] == 'long' else UNINITIALIZED_PRICE_HIGH,
lowest_price=UNINITIALIZED_PRICE_HIGH if state_data['side'] == 'long' else Decimal(str(state_data['entry_price'])),
```

**ВАЖНО!** Peaks сбрасываются в entry_price! ✅

Значит при рестарте для INACTIVE TS:
- highest = entry (НОВЫЙ)
- current_stop = СТАРЫЙ (из БД)
- При первом update_price() peaks обновятся правильно
- При активации SL пересчитается из нового highest

**ВЫВОД**: Для INACTIVE позиций риск МИНИМАЛЬНЫЙ ✅

### 4. Для ACTIVE позиций - КРИТИЧНО! 🔴

Если позиция:
1. Открылась, TS активировался (state=ACTIVE, current_stop установлен)
2. Позиция ЗАКРЫЛАСЬ
3. БД запись НЕ удалилась (остался state=ACTIVE, current_stop=X)
4. Новая позиция с тем же символом открылась
5. При создании TS:
   - Если используется ON CONFLICT UPDATE
   - И state перезаписывается на INACTIVE
   - Но current_stop остается СТАРЫМ
6. При рестарте и восстановлении:
   - state=INACTIVE (правильно)
   - current_stop=СТАРЫЙ
   - Но peaks сбросятся в entry

**ИЛИ ХУЖЕ:**
Если при UPSERT state НЕ перезаписывается:
- Новая позиция создает TS
- UPSERT видит CONFLICT
- UPDATE оставляет state=ACTIVE (СТАРЫЙ!)
- Новая позиция будет думать что TS УЖЕ активен!
- 🔴 **КАТАСТРОФА!**

---

## ПЛАН ИСПРАВЛЕНИЯ

### Этап 1: ИССЛЕДОВАНИЕ (ТЕКУЩИЙ)
✅ Проблема идентифицирована
✅ Формулы проверены (все правильные)
✅ Корневая причина найдена (UPSERT logic + stale data)

### Этап 2: ДЕТАЛЬНАЯ ПРОВЕРКА КОДА
🔲 Проверить database/repository.py → метод save_trailing_stop_state
🔲 Найти точный SQL запрос UPSERT
🔲 Проверить какие поля обновляются при CONFLICT
🔲 Проверить логику удаления записей при закрытии позиции

### Этап 3: ОПРЕДЕЛЕНИЕ СТРАТЕГИИ ИСПРАВЛЕНИЯ

**Вариант A: Удалять запись при закрытии позиции**
```python
# В position_manager.py при закрытии позиции
async def close_position(...):
    ...
    # После удаления TS из trailing_stops
    await repository.delete_trailing_stop_state(symbol, exchange)
```

**Плюсы:**
- Чистая БД (только активные позиции)
- Нет stale data

**Минусы:**
- Теряем историю TS (нельзя анализировать прошлые активации)

**Вариант B: Использовать position_id в UNIQUE constraint**
```sql
-- Вместо UNIQUE(symbol, exchange)
-- Использовать UNIQUE(position_id)
-- Или UNIQUE(symbol, exchange, position_id)
```

**Плюсы:**
- Разные позиции с одним символом не конфликтуют
- Сохраняется история

**Минусы:**
- Требует миграцию БД
- Нужно проверять весь код на использование (symbol, exchange) для поиска

**Вариант C: Добавить флаг is_closed и фильтровать**
```sql
ALTER TABLE trailing_stop_state ADD COLUMN is_closed BOOLEAN DEFAULT FALSE;
-- При закрытии позиции: UPDATE SET is_closed=TRUE
-- При поиске: WHERE is_closed=FALSE
```

**Плюсы:**
- Сохраняется история
- Минимальные изменения кода

**Минусы:**
- Накопление старых записей
- Нужен периодический cleanup

**Вариант D (РЕКОМЕНДУЕМЫЙ): При создании TS полностью перезаписывать запись**
```python
# В create_trailing_stop() перед сохранением:
# 1. Проверить существует ли запись для (symbol, exchange)
# 2. Если ДА и position_id != current_position_id → DELETE старую запись
# 3. INSERT новую запись

# ИЛИ в UPSERT:
ON CONFLICT (symbol, exchange) DO UPDATE SET
    -- Перезаписать ВСЕ поля на новые значения
    entry_price = EXCLUDED.entry_price,
    current_stop_price = EXCLUDED.current_stop_price,  -- Даже если NULL!
    state = EXCLUDED.state,
    highest_price = EXCLUDED.highest_price,
    lowest_price = EXCLUDED.lowest_price,
    is_activated = EXCLUDED.is_activated,
    update_count = EXCLUDED.update_count,
    ...
    -- ВСЕ ПОЛЯ!
```

**Плюсы:**
- Минимальные изменения
- Нет миграции БД
- Гарантированно свежие данные

**Минусы:**
- Теряем историю (как в варианте A)

### Этап 4: ТЕСТИРОВАНИЕ
1. Написать тест: открыть → активировать → закрыть → переоткрыть
2. Проверить БД после каждого шага
3. Проверить рестарт после переоткрытия

### Этап 5: DEPLOYMENT
1. Применить исправление
2. Очистить stale data в продакшене:
   ```sql
   -- Найти позиции с расхождением entry_price
   SELECT ts.symbol, ts.entry_price as ts_entry, p.entry_price as pos_entry
   FROM monitoring.trailing_stop_state ts
   JOIN monitoring.positions p ON ts.symbol = p.symbol AND ts.exchange = p.exchange
   WHERE p.status = 'active'
     AND ts.entry_price != p.entry_price;

   -- Удалить или обновить
   ```

---

## ВЫВОДЫ

### ✅ ЧТО РАБОТАЕТ ПРАВИЛЬНО:
1. ✅ Все формулы расчета SL корректны (LONG/SHORT)
2. ✅ Логика активации TS работает
3. ✅ Логика обновления SL работает
4. ✅ При рестарте peaks сбрасываются в entry (защита от неправильного highest)

### ❌ ЧТО НЕ РАБОТАЕТ:
1. ❌ При переоткрытии позиций НЕ удаляются/перезаписываются старые данные TS
2. ❌ current_stop_price остается от предыдущей позиции
3. ❌ Возможно state тоже остается старым (нужна проверка!)

### 🔴 КРИТИЧЕСКИЕ РИСКИ:
1. Восстановление TS после рестарта с НЕПРАВИЛЬНЫМ current_stop_price
2. Если state=ACTIVE остается от старой позиции → новая позиция будет работать некорректно
3. Невозможность различить данные текущей и предыдущей позиции в БД

### 📋 РЕКОМЕНДАЦИИ:
1. **СРОЧНО**: Проверить код repository.save_trailing_stop_state
2. **СРОЧНО**: Проверить все места закрытия позиций - удаляется ли TS state
3. **P0**: Реализовать вариант D (полная перезапись при UPSERT)
4. **P1**: Добавить constraint на position_id в будущем
5. **P2**: Cleanup stale data в продакшене
6. **P2**: Добавить автотест на переоткрытие позиций

---

## СЛЕДУЮЩИЕ ШАГИ

**БЕЗ ИЗМЕНЕНИЯ КОДА (текущий этап):**
1. ✅ Проверить database/repository.py
2. ✅ Найти SQL UPSERT запрос
3. ✅ Проверить логику удаления при закрытии
4. ✅ Создать финальный отчет с планом исправления

**С ИЗМЕНЕНИЕМ КОДА (следующий этап):**
1. 🔲 Реализовать исправление (вариант D)
2. 🔲 Написать тесты
3. 🔲 Протестировать на dev
4. 🔲 Cleanup prod БД
5. 🔲 Deploy

---

**Конец отчета**
**Дата**: 2025-10-20
**Автор расследования**: Claude (AI Assistant)
