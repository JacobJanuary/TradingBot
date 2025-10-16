# PROTECTION GUARD LIVE TEST REPORT

**Дата:** 2025-10-15
**Длительность теста:** 10 минут (600 секунд)
**Ветка:** cleanup/fas-signals-model
**Коммит:** 0d7a1d1 (Merge Protection Guard Fixes #2 and #3)

---

## EXECUTIVE SUMMARY

### Статус: ⚠️ ЧАСТИЧНО УСПЕШНО

Protection Guard **активен и работает**, проводит проверки SL каждые ~2 минуты, но обнаружена **критическая проблема** с позицией HNT/USDT:USDT.

**Ключевые находки:**
- ✅ Protection Guard работает и регулярно проверяет позиции
- ✅ Система логирования работает корректно
- ✅ Retry механизм функционирует (3 попытки)
- ⚠️ **Критическая проблема:** Позиция HNTUSDT БЕЗ SL более 10 минут
- ❌ **Ошибка Bybit API:** Некорректное значение SL (3.24 вместо ожидаемого < 1.616)

---

## МЕТРИКИ ЗАЩИТЫ ПОЗИЦИЙ

### Общая статистика (10 минут)

```
SL проверок выполнено:         2 проверки
SL создано (попыток):          12 попыток
Ошибок SL:                     37 ошибок
Позиций без SL:                1 (HNTUSDT)
```

### Активность по времени

| Время | Проверка # | SL создано | Ошибок | Статус |
|-------|-----------|-----------|--------|---------|
| 01:23 | #4        | 0         | 0      | ✅ Проверка OK |
| 01:23 | #5        | 3         | 9      | ❌ Ошибка HNTUSDT |
| 01:24 | #7        | 3         | 9      | ❌ Ошибка HNTUSDT |
| 01:26 | #10       | 1         | 4      | ❌ Ошибка HNTUSDT |
| 01:26 | #11       | 2         | 9      | ❌ Ошибка HNTUSDT |
| 01:28 | #15       | 1         | 4      | ✅ Другие позиции OK |
| 01:28 | #16       | 3         | 9      | ❌ Ошибка HNTUSDT |
| 01:29 | #18       | 3         | 9      | ❌ Ошибка HNTUSDT |
| 01:31 | #20       | 3         | 8      | ❌ Ошибка HNTUSDT |

---

## КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### ❌ ПРОБЛЕМА: Позиция HNTUSDT без Stop Loss

**Серьезность:** CRITICAL

**Описание:**
Позиция HNT/USDT:USDT (Bybit) остается без SL на протяжении всего теста (10+ минут).

**Детали ошибки:**
```
bybit {"retCode":10001,"retMsg":"StopLoss:324000000 set for Buy position should lower than base_price:161600000??LastPrice"}
```

**Анализ:**
- **Позиция:** LONG HNT/USDT
- **SL который пытается установить бот:** 3.24 USDT (324000000 в виде integer с 7 decimal places)
- **Base price (entry price?):** 1.616 USDT (161600000)
- **Проблема:** Для LONG позиции SL должен быть **НИЖЕ** entry price, но бот пытается установить 3.24 > 1.616

**Количество попыток:** 37+ за 10 минут (с retry logic: 3 попытки за раз)

**Предупреждения системы:**
```
[01:23:04] CRITICAL: Position HNTUSDT WITHOUT STOP LOSS for 306 seconds! Position at risk!
[01:24:27] CRITICAL: 1 positions still without stop loss! Symbols: HNTUSDT
[01:28:45] CRITICAL: 1 positions still without stop loss! Symbols: HNTUSDT
[01:31:01] CRITICAL: 1 positions still without stop loss! Symbols: HNTUSDT
```

**Возможная причина:**
Ошибка в вычислении target SL price для LONG позиций на Bybit. Возможно:
1. Используется неправильная логика (SL выше вместо ниже entry)
2. Перепутаны SHORT и LONG
3. Используется старая цена из базы данных

---

## УСПЕШНЫЕ ОПЕРАЦИИ

### ✅ Позиции С Stop Loss

Protection Guard успешно подтвердил наличие SL для следующих позиций:

```
[01:23:02] ✅ FXSUSDT has Stop Loss order: 19865220
[01:23:03] ✅ 1000000PEIPEIUSDT has Stop Loss: 0.03106
[01:23:03] ✅ DOGUSDT has Stop Loss: 0.001419
[01:23:04] ✅ 10000WENUSDT has Stop Loss: 0.2547
[01:23:05] ✅ XDCUSDT has Stop Loss: 1
[01:28:33] ✅ DOGUSDT has Stop Loss: 0.001419
[01:28:34] ✅ 10000WENUSDT has Stop Loss: 0.2547
[01:28:35] ✅ XDCUSDT has Stop Loss: 1
[01:28:35] ✅ SCAUSDT has Stop Loss: 0.09527
[01:31:05] ✅ RADUSDT has Stop Loss: 2.501
[01:31:06] ✅ OSMOUSDT has Stop Loss: 0.1396
```

**Итого:** 8-10 позиций с корректными SL

---

## РАБОТА НОВЫХ ФИКСОВ

### Fix #3: Side Validation
**Статус:** ⚠️ Не протестирован

В логах не обнаружено срабатывания side validation (нет сообщений о "wrong side" или "skip SL order").

**Возможные причины:**
- Все SL ордера имеют корректный side
- Validation логика не срабатывает в данном сценарии
- Требуется специальный тестовый сценарий

**Рекомендация:** Создать unit-тест с намеренно неправильным side

### Fix #2: Price Validation
**Статус:** ⚠️ Не протестирован явно

В логах не обнаружено срабатывания price validation ("old position" или "too close to entry").

**Возможные причины:**
- Существующие SL ордера находятся в допустимом диапазоне (±5%)
- Validation применяется только к существующим SL (не к новым)
- Требуется специальный тестовый сценарий

**Рекомендация:** Проверить логику расчета target SL price

---

## PERFORMANCE ANALYSIS

### Периодичность проверок

```
Настроено: каждые 120 секунд (2 минуты)
Фактически: ~120-180 секунд между проверками
```

**Вывод:** Периодичность соответствует настройкам ✅

### Retry Logic

```
Настроено: 3 попытки с интервалом ~1 секунда
Фактически: Все 3 попытки выполняются, всего ~3 секунды
```

**Вывод:** Retry logic работает корректно ✅

### Event Logging

```
События успешно записываются в DB:
- stop_loss_error
- health_check_failed
- position_check
```

**Вывод:** EventLogger функционирует ✅

---

## АНАЛИЗ КОДА

### Возможная проблема в `core/stop_loss_manager.py`

**Гипотеза:** Ошибка в расчете target SL price для LONG позиций.

**Код для проверки:**
```python
# В методе _set_bybit_stop_loss() или _calculate_stop_loss_price()
# Проверить логику:

if side == 'long':
    # SL должен быть НИЖЕ entry price
    sl_price = entry_price * (1 - sl_percent/100)  # Корректно
    # НЕ ДОЛЖНО БЫТЬ:
    # sl_price = entry_price * (1 + sl_percent/100)  # Неправильно!
```

**Проверка в логах:**
```
Entry price: 1.616
Пытается установить SL: 3.24
Соотношение: 3.24 / 1.616 = 2.00 (200%)
```

Это указывает на то, что SL = entry * 2, что явно неправильно для -2% SL.

---

## RECOMMENDATIONS

### Критически важно (исправить немедленно)

1. **Исправить расчет SL для LONG позиций на Bybit**
   - Файл: `core/stop_loss_manager.py`
   - Метод: `_set_bybit_stop_loss()` или `_calculate_stop_loss_price()`
   - Проблема: SL устанавливается выше entry вместо ниже
   - Действие: Проверить формулу расчета SL для LONG

2. **Добавить validation перед отправкой в Bybit API**
   ```python
   if side == 'long' and sl_price >= entry_price:
       raise ValueError(f"LONG SL must be below entry: {sl_price} >= {entry_price}")
   if side == 'short' and sl_price <= entry_price:
       raise ValueError(f"SHORT SL must be above entry: {sl_price} <= {entry_price}")
   ```

3. **Создать позицию HNT/USDT в ручную с SL** для защиты открытой позиции

### Высокий приоритет

4. **Добавить unit-тесты для `_calculate_stop_loss_price()`**
   - Тестировать LONG и SHORT отдельно
   - Проверять граничные случаи (0%, 100%, отрицательные значения)

5. **Создать integration test с mock Bybit API**
   - Проверить корректность параметров запроса
   - Убедиться что SL направление соответствует position side

6. **Добавить debug logging для расчета SL**
   ```python
   logger.debug(f"Calculating SL: side={side}, entry={entry}, sl%={sl_percent}, result={sl_price}")
   ```

### Средний приоритет

7. **Улучшить сообщения об ошибках**
   - Парсить ошибки Bybit API
   - Выводить понятные сообщения на русском/английском
   - Предлагать решение (например: "SL должен быть ниже entry для LONG")

8. **Добавить метрики в мониторинг**
   - Количество позиций без SL за последние 5/10/30 минут
   - Средняя длительность позиции без SL
   - Процент успешных SL установок

---

## ТЕСТИРОВАНИЕ НОВЫХ ФИКСОВ

### Требуется дополнительное тестирование

**Fix #3: Side Validation**
- [ ] Создать позицию с неправильным side SL ордером
- [ ] Проверить что validation отклоняет wrong-side order
- [ ] Убедиться что correct-side order принимается

**Fix #2: Price Validation**
- [ ] Создать SL далеко от target (>5%)
- [ ] Проверить что validation отклоняет old position SL
- [ ] Убедиться что SL в пределах tolerance принимается

### Рекомендуемые тесты

```python
# Test scenario для Fix #3
async def test_side_validation_rejects_wrong_side():
    # LONG position с BUY stop order (wrong!)
    # Ожидается: has_stop_loss возвращает False

# Test scenario для Fix #2
async def test_price_validation_rejects_old_sl():
    # LONG @ 50k, existing SL @ 49k, target SL @ 58.8k
    # Diff = 16.67% > 5% tolerance
    # Ожидается: _validate_existing_sl возвращает False
```

---

## ВЫВОДЫ

### ✅ Что работает хорошо

1. **Protection Guard активен** и выполняет проверки регулярно
2. **Event logging** работает корректно
3. **Retry mechanism** функционирует (3 попытки)
4. **Периодичность** соответствует настройкам (120 сек)
5. **Большинство позиций защищены** SL (8-10 из 9-11)

### ❌ Критические проблемы

1. **Ошибка расчета SL** для LONG позиций на Bybit (SL выше вместо ниже entry)
2. **1 позиция БЕЗ защиты** более 10 минут (HNTUSDT)
3. **37+ неудачных попыток** создать SL за 10 минут

### ⚠️ Требует внимания

1. Новые фиксы (#2 и #3) **не протестированы** в реальных условиях
2. Отсутствует **pre-validation** перед отправкой в API
3. Нет **автоматического detection** неправильного SL направления

---

## NEXT STEPS

### Немедленные действия

1. ✅ **Остановить бота** (выполнено)
2. 🔴 **Установить SL вручную** для HNTUSDT на бирже
3. 🔴 **Исправить расчет SL** в `core/stop_loss_manager.py`
4. 🔴 **Добавить validation** SL direction перед API call
5. 🔴 **Запустить unit-тесты** для SL calculation

### После исправления

6. **Повторить live test** (10-15 минут)
7. **Проверить логи** на наличие ошибок Bybit API
8. **Убедиться** что HNTUSDT получил SL
9. **Мониторить** первые 24 часа после deploy

---

## ФАЙЛЫ ОТЧЕТА

- `bot_protection_test.log` - Полный лог бота (10 минут)
- `protection_guard_monitor_results.log` - Результаты мониторинга
- `PROTECTION_GUARD_LIVE_TEST_REPORT.md` - Этот отчет

---

**Тест завершен:** 2025-10-15 01:31:36
**Отчет создан:** 2025-10-15 01:32:00
**Статус:** ⚠️ ТРЕБУЕТСЯ ИСПРАВЛЕНИЕ КРИТИЧЕСКОЙ ОШИБКИ
