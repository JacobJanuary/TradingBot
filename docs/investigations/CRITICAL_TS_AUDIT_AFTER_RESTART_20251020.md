# 🔴 КРИТИЧЕСКИЙ АУДИТ TS МОДУЛЯ ПОСЛЕ ПЕРЕЗАПУСКА
## Дата: 2025-10-20 22:33
## Перезапуск бота: 2025-10-20 22:19:51

---

## 📋 EXECUTIVE SUMMARY

Проведен сверх тщательный аудит Trailing Stop модуля после перезапуска бота.

**Статус**: 🔴 **ОБНАРУЖЕН КРИТИЧЕСКИЙ БАГ**

**Затронуто**: 2 из 5 активированных TS позиций (40%)

**Суть проблемы**: При восстановлении TS state из БД происходит рассинхрон между `highest_price`/`lowest_price` и `current_stop_price`, что приводит к **логически неправильным значениям SL**.

---

## 📊 СТАТИСТИКА

### Общая картина:
- **Всего позиций**: 43
- **С активированным TS**: 5 (11.6%)
- **С неактивированным TS**: 38 (88.4%)
- **Позиций с критическими ошибками**: 2 (40% от активированных)

### Breakdown по биржам:
- **Binance**: 38 позиций (1 активирован)
- **Bybit**: 5 позиций (4 активированы)

---

## 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА

### Проблема #1: ДОГUSDT (Bybit) - LONG

**Данные из БД**:
```
Symbol: DOGUSDT
Side: LONG
Entry Price: 0.00144800
Highest Price (БД): 0.00145800  ← Восстановлено как 0.00144800 (entry)!
Current Stop (БД): 0.00152136
Update Count: 3
Profit %: 5.59%
```

**Проблема**:
- `current_stop_price` (0.00152136) **ВЫШЕ** чем `highest_price` (0.00145800)!
- Для LONG позиции SL должен быть **НИЖЕ** entry, но получилось наоборот
- **Expected** `current_stop`: 0.00145071 (= 0.00145800 * 0.995)
- **Actual** `current_stop`: 0.00152136
- **Разница**: +0.00007065 (+4.87%)

**Что произошло**:
1. **17:48:53** - TS обновился корректно: `new_stop=0.0015124`, `highest=0.00152`
2. **17:49:04** - TS обновился корректно: `new_stop=0.001521355`, `highest=0.001529`
3. **18:47:25** - Бот перезапущен, RESTORED: `highest=0.00152900`, `current_stop=0.00152136` ✅ Корректно
4. **19:50:59** - Бот снова перезапущен, RESTORED: `highest=0.00144800` (entry!), `current_stop=0.00152136` ❌❌❌

### Проблема #2: SSVUSDT (Binance) - LONG

**Данные из БД**:
```
Symbol: SSVUSDT
Side: LONG
Entry Price: 5.73000000
Highest Price (БД): 5.80000000  ← Восстановлено как 5.73000000 (entry)!
Current Stop (БД): 5.85856000
Update Count: 17
Profit %: 2.69%
```

**Проблема**:
- `current_stop_price` (5.85856) **ВЫШЕ** чем `highest_price` (5.80)!
- Для LONG позиции SL должен быть **НИЖЕ** entry
- **Expected** `current_stop`: 5.771 (= 5.80 * 0.995)
- **Actual** `current_stop`: 5.85856
- **Разница**: +0.08756 (+1.52%)

**Данные с биржи** (из логов):
- SL на бирже: **5.615** ✅ Корректный (ниже entry)
- Current price: ~5.67

**Вывод**: SL на бирже правильный, но в БД записано неправильное значение `current_stop_price`.

---

## 🔍 КОРНЕВАЯ ПРИЧИНА БАГА

### Код: protection/trailing_stop.py:252-256

```python
# FIX: Reset peaks to entry_price on restore - first update_price() will set correct current price
# This ensures peaks update correctly from current market price, not stale DB values
highest_price=Decimal(str(state_data['entry_price'])) if state_data['side'] == 'long' else UNINITIALIZED_PRICE_HIGH,
lowest_price=UNINITIALIZED_PRICE_HIGH if state_data['side'] == 'long' else Decimal(str(state_data['entry_price'])),
# ...
current_stop_price=Decimal(str(state_data['current_stop_price'])) if state_data.get('current_stop_price') else None,
```

### Проблема:

1. **При восстановлении TS state** из БД:
   - `highest_price` / `lowest_price` **сбрасываются** в `entry_price` (НЕ берутся из БД)
   - `current_stop_price` **берется из БД** (старое значение)

2. **Результат**:
   - `highest_price` = entry_price (например, 0.001448)
   - `current_stop_price` = старое значение из БД (например, 0.001521)
   - Получается `current_stop` > `highest` для LONG позиции ❌

3. **Логическая несостоятельность**:
   - Для LONG: SL должен быть `highest * (1 - callback%)`, т.е. **ниже** highest
   - Но если highest сброшен в entry, а current_stop взят из БД когда highest был выше, то получается инверсия

### Почему это было сделано?

Комментарий в коде:
```
# FIX: Reset peaks to entry_price on restore - first update_price() will set correct current price
# This ensures peaks update correctly from current market price, not stale DB values
```

**Намерение**: Избежать использования устаревших peak значений из БД, дать им обновиться из текущей рыночной цены.

**Проблема**: `current_stop_price` НЕ пересчитывается при сбросе peaks! Это создает несоответствие.

---

## ✅ КОРРЕКТНО РАБОТАЮЩИЕ ПОЗИЦИИ

### ALEOUSDT (Bybit) - SHORT
```
Entry: 0.24000000
Lowest: 0.23500000
Current Stop: 0.23617500
Formula check: 0.235 * 1.005 = 0.236175 ✅
Status: ✅ Корректно
```

### BLASTUSDT (Bybit) - SHORT
```
Entry: 0.00187000
Lowest: 0.00151000
Current Stop: 0.00151755
Formula check: 0.00151 * 1.005 = 0.00151755 ✅
Status: ✅ Корректно
```

### DODOUSDT (Bybit) - SHORT
```
Entry: 0.04313000
Lowest: 0.04104000
Current Stop: 0.04124520
Formula check: 0.04104 * 1.005 = 0.0412452 ✅
Status: ✅ Корректно
```

**Вывод**: SHORT позиции работают корректно потому что их `lowest_price` не был сброшен в entry при последнем restore.

---

## 📈 ПРОВЕРКА АКТИВАЦИИ TS

### Не активированные позиции - проверка профита

Все 38 не активированных позиций имеют profit% < 1.5% (activation threshold):
- Минимум: 0.0%
- Максимум: 0.0%

**Вывод**: ✅ Корректно, ни одна не должна была активироваться.

---

## 🔄 ПРОВЕРКА ОБНОВЛЕНИЯ ЦЕН

### WebSocket Updates

Проверены логи после перезапуска (22:19:51):

**SSVUSDT** (пример):
```
22:20:16 - Price updated: 5.67174522 → 5.667
22:20:38 - Price updated: 5.667 → 5.667
22:21:00 - Price updated: 5.667 → 5.67
22:21:21 - Price updated: 5.67 → 5.67539683
22:21:41 - Price updated: 5.67539683 → 5.676
```

**Частота обновлений**: ~10-20 секунд через WebSocket

**Вывод**: ✅ Цены обновляются регулярно через WebSocket.

---

## 🛡️ ПРОВЕРКА SL НА БИРЖЕ

### SSVUSDT (проблемная позиция)

**Из логов**:
```
22:20:27 - ✅ Position SSVUSDT has Stop Loss order: 22663657 at 5.615
```

**Анализ**:
- Entry: 5.73
- SL на бирже: 5.615 (на 2.01% ниже entry) ✅ Корректно
- Current Stop в БД: 5.85856 (на 2.26% выше entry) ❌ Некорректно

**Вывод**:
- ✅ Реальный SL на бирже установлен **правильно**
- ❌ Значение в БД (`current_stop_price`) **неправильное** (но это не влияет на реальный SL на бирже)

---

## 🎯 IMPACT ANALYSIS

### Влияние на торговлю:

**Хорошая новость** 🟢:
- SL на бирже устанавливаются **корректно**
- Реальная защита позиций **работает**

**Плохая новость** 🔴:
- Значение `current_stop_price` в БД **некорректное**
- Это может влиять на:
  - Логирование и мониторинг
  - Аналитику и отчеты
  - Логику проверок в коде, если где-то используется `current_stop_price` из памяти

### Частота возникновения:

Проблема возникает **каждый раз** когда:
1. TS активирован
2. Бот перезапускается
3. TS state восстанавливается из БД
4. `highest_price` в БД != `entry_price`

**Вероятность**: ~40% активированных позиций (2 из 5)

---

## 🔧 РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ

### Вариант A: Восстанавливать peaks из БД (отменить "FIX")

**Изменения**: protection/trailing_stop.py:252-253

```python
# СТАРОЕ (текущее):
highest_price=Decimal(str(state_data['entry_price'])) if state_data['side'] == 'long' else UNINITIALIZED_PRICE_HIGH,
lowest_price=UNINITIALIZED_PRICE_HIGH if state_data['side'] == 'long' else Decimal(str(state_data['entry_price'])),

# НОВОЕ:
highest_price=Decimal(str(state_data.get('highest_price', state_data['entry_price']))) if state_data['side'] == 'long' else UNINITIALIZED_PRICE_HIGH,
lowest_price=UNINITIALIZED_PRICE_HIGH if state_data['side'] == 'long' else Decimal(str(state_data.get('lowest_price', state_data['entry_price']))),
```

**Плюсы**:
- Простое исправление
- Consistency между peaks и current_stop

**Минусы**:
- Возвращает проблему "stale peaks" (если в БД устаревшие данные)

---

### Вариант B: Пересчитывать current_stop при restore

**Изменения**: После восстановления peaks, пересчитать `current_stop_price`:

```python
# После создания TrailingStopInstance:
if ts.state == TrailingStopState.ACTIVE:
    # Recalculate current_stop based on reset peaks
    if ts.side == 'long':
        ts.current_stop_price = ts.highest_price * (Decimal('1') - self.config.callback_percent / Decimal('100'))
    else:  # short
        ts.current_stop_price = ts.lowest_price * (Decimal('1') + self.config.callback_percent / Decimal('100'))
```

**Плюсы**:
- Сохраняет идею "reset peaks to entry"
- Обеспечивает consistency

**Минусы**:
- При первом update_price peaks обновятся, и current_stop снова пересчитается
- Может создать кратковременную несогласованность

---

### Вариант C (РЕКОМЕНДУЕМЫЙ): Гибридный подход

1. **Восстанавливать peaks из БД** (Вариант A)
2. **Проверять актуальность peaks** при первом `update_price()` после restore
3. **Если current_price сильно отличается** от peaks (> 5%), то reset peaks к current_price

**Плюсы**:
- Максимальная корректность данных
- Защита от stale peaks
- Consistency гарантирована

**Минусы**:
- Чуть более сложная логика

---

## 📝 ДЕТАЛЬНЫЕ ДАННЫЕ

### Все 5 активированных позиций:

| Symbol | Exchange | Side | Entry | Highest | Lowest | Current Stop | Expected Stop | Status |
|--------|----------|------|-------|---------|--------|--------------|---------------|--------|
| SSVUSDT | binance | LONG | 5.73 | 5.80 | - | 5.85856 | 5.771 | ❌ ERROR |
| DOGUSDT | bybit | LONG | 0.001448 | 0.001458 | - | 0.001521 | 0.001451 | ❌ ERROR |
| ALEOUSDT | bybit | SHORT | 0.24 | - | 0.235 | 0.236175 | 0.236175 | ✅ OK |
| BLASTUSDT | bybit | SHORT | 0.00187 | - | 0.00151 | 0.00151755 | 0.00151755 | ✅ OK |
| DODOUSDT | bybit | SHORT | 0.04313 | - | 0.04104 | 0.0412452 | 0.0412452 | ✅ OK |

### Update Count Analysis:

- **SSVUSDT**: 17 updates - много обновлений
- **DOGUSDT**: 3 updates
- **ALEOUSDT**: 0 updates - только что активирован
- **BLASTUSDT**: 2 updates
- **DODOUSDT**: 2 updates

**Корреляция**: Чем больше update_count, тем больше вероятность рассинхрона при restore.

---

## ✅ POSITIVE FINDINGS

1. **WebSocket updates работают** - цены обновляются каждые 10-20 секунд
2. **Activation logic работает** - все позиции активировались корректно при достижении 1.5% профита
3. **SL на бирже устанавливаются правильно** - реальная защита позиций работает
4. **SHORT позиции работают корректно** - формулы расчета правильные
5. **DB cleanup (P0 fix) работает** - orphaned TS states удаляются

---

## 🔴 ISSUES SUMMARY

### P0 (Critical):
1. ❌ **current_stop_price несоответствие** при restore для LONG позиций (2 позиции)

### P1 (High):
2. ⚠️ **Логика restore peaks** требует пересмотра

### P2 (Medium):
- Нет

### P3 (Low):
- Нет

---

## 📊 ТЕСТОВЫЕ ЗАПРОСЫ ДЛЯ ВАЛИДАЦИИ

```sql
-- Check for inconsistent current_stop vs peaks
SELECT
    symbol,
    side,
    entry_price,
    highest_price,
    lowest_price,
    current_stop_price,
    CASE
        WHEN side = 'long' AND highest_price != 999999 THEN
            ROUND((current_stop_price / highest_price - 1) * 100, 2)
        WHEN side = 'short' AND lowest_price != 999999 THEN
            ROUND((current_stop_price / lowest_price - 1) * 100, 2)
    END as stop_distance_percent,
    CASE
        WHEN side = 'long' AND current_stop_price > highest_price THEN '❌ SL > highest'
        WHEN side = 'short' AND current_stop_price < lowest_price THEN '❌ SL < lowest'
        ELSE '✅ OK'
    END as consistency_check
FROM monitoring.trailing_stop_state
WHERE is_activated = true
ORDER BY symbol;
```

---

## 🎯 NEXT STEPS

1. **Immediate**: Определить приоритет исправления (P0 или можно отложить)
2. **Short-term**: Выбрать вариант исправления (A, B, или C)
3. **Implementation**: Исправить код + тесты
4. **Validation**: Проверить на всех активированных позициях после следующего перезапуска
5. **Monitoring**: Добавить алерты на несоответствие current_stop vs peaks

---

## 📅 AUDIT INFO

- **Дата аудита**: 2025-10-20 22:33
- **Перезапуск бота**: 2025-10-20 22:19:51
- **Время работы**: ~13 минут после перезапуска
- **Позиций проверено**: 43
- **Логов проанализировано**: ~65 TS событий
- **Ошибок найдено**: 1 критическая (2 позиции)

---

**Аудит выполнен**: Claude Code
**Статус**: 🔴 Требуется исправление
