# 🔍 ДЕТАЛЬНЫЙ ОТЧЁТ РАССЛЕДОВАНИЯ - BINANCE STOP-LOSS

**Дата:** 2025-10-11
**Проблема:** 7 позиций на Binance Testnet остались без защиты (stop-loss)
**Статус расследования:** ЗАВЕРШЕНО

---

## 📊 ЧТО БЫЛО ОБНАРУЖЕНО

### 1. ТЕКУЩЕЕ СОСТОЯНИЕ (через API)
✅ **Проверка прямо сейчас показала:**
- 6 активных позиций на Binance Testnet
- **У ВСЕХ ЕСТЬ STOP-LOSS ордера:**
  - ONDO/USDT: SL order #26346488 at 0.7593
  - HOME/USDT: SL order #4292306 at 0.027552
  - FLUX/USDT: SL order #9559619 at 0.1289
  - HYPER/USDT: SL order #8311662 at 0.2063
  - 1000X/USDT: SL order #27289476 at 0.03296
  - TAC/USDT: SL order #9421238 at 0.00501

### 2. ХРОНОЛОГИЯ ПРОБЛЕМЫ

**21:35:07-21:35:26** - Создано 5 позиций БЕЗ добавления в tracked_positions:
- PUFFERUSDT (ID 389) - SL создан at 0.105648
- VOXELUSDT (ID 390) - SL создан at 0.03624
- ANIMEUSDT (ID 391) - SL создан at 0.00927
- DMCUSDT (ID 392) - SL создан at 0.002332
- ATAUSDT (ID 393) - SL создан at 0.03

**21:35:08-21:35:29** - Позиции получают обновления от биржи, но:
```
→ Skipped: PUFFERUSDT not in tracked positions (['KSMUSDT', 'FLUXUSDT'...]...)
```

**21:39:16** - Система обнаружила 5 позиций БЕЗ SL:
```
⚠️ Position 389 has no stop loss on exchange!
⚠️ Position 390 has no stop loss on exchange!
⚠️ Position 391 has no stop loss on exchange!
⚠️ Position 392 has no stop loss on exchange!
⚠️ Position 393 has no stop loss on exchange!
```

**21:43:59-21:44:02** - binance_zombie_manager запустился:
- Проверил 16 ордеров
- Нашёл 1 "orphaned" order: #26732942 на ONDO/USDT
- **Причина:** "No balance for trading pair"
- Отменил 1 ордер

**22:14:25** - Бот перезапущен:
- tracked_positions = [] (ПУСТОЙ!)
- Биржа прислала 7 позиций, но они проигнорированы

**22:14:30** - Позиции загружены из БД:
- "📊 Loaded 11 positions from database"
- check_positions_protection проверил их и нашёл SL

---

## 🔍 НАЙДЕННЫЕ ВИНОВНИКИ

### ВИНОВНИК #1: Позиции не добавляются в tracked_positions
**Файл:** `core/position_manager.py:706`
**Проблема:** После атомарного создания позиции отслеживаются по ID вместо символа
**Статус:** ✅ УЖЕ ИСПРАВЛЕНО (ваше предыдущее исправление)

```python
# БЫЛО:
self.positions[atomic_result['position_id']] = position

# СТАЛО:
self.positions[symbol] = position  # Track by symbol, not ID
```

### ВИНОВНИК #2: binance_zombie_manager (ПОТЕНЦИАЛЬНЫЙ)
**Файл:** `core/binance_zombie_manager.py`
**Что делает:** Отменяет "orphaned" ордера (ордера без баланса на паре)
**Защита:** ЕСТЬ - пропускает STOP_LOSS ордера

```python
PROTECTIVE_ORDER_TYPES = [
    'STOP_LOSS', 'STOP_LOSS_LIMIT', 'STOP_MARKET',
    ...
]
if order_type.upper() in PROTECTIVE_ORDER_TYPES:
    return None  # НЕ удаляет!
```

**НО!** Возможная проблема: если CCXT возвращает order_type в другом формате, защита может не сработать.

### ВИНОВНИК #3: Отсутствие real-time проверки SL на бирже
**Файл:** `core/position_manager.py:1469`
**Проблема:** `check_positions_protection()` итерирует по `self.positions`
- Если позиция не в tracked - она НЕ проверяется
- Проверка происходит раз в 5 минут (из main.py)
- За это время SL могут быть удалены другими модулями

---

## 🐛 КОРНЕВАЯ ПРИЧИНА

**ГЛАВНАЯ ПРОБЛЕМА:** Недостаточная защита от удаления SL

1. **Новые позиции не отслеживаются немедленно** (уже исправлено)
2. **binance_zombie_manager может ошибочно считать SL "orphaned"**
   - Если позиция создана, но ещё не загружена в `active_symbols`
   - Если CCXT возвращает order_type который не в PROTECTIVE_ORDER_TYPES
3. **Нет непрерывного мониторинга SL** - проверка раз в 5 минут недостаточна

---

## ⚠️ ПОЧЕМУ SL УДАЛЯЮТСЯ

### Сценарий 1: Timing Issue
1. Позиция создана в 21:35:07 со SL
2. Позиция НЕ добавлена в tracked_positions (старый bug)
3. В 21:43:59 zombie_manager запускается
4. Загружает balances и проверяет какие символы активны
5. Если позиция PUFFERUSDT НЕ в active_symbols → SL считается "orphaned"
6. SL ордер МОЖЕТ быть удалён (если защита не сработала)

### Сценарий 2: Order Type Mismatch
1. CCXT возвращает order_type = 'stop_market' (lowercase)
2. Код делает `.upper()` → 'STOP_MARKET'
3. Проверяет `'STOP_MARKET' in PROTECTIVE_ORDER_TYPES` → ✅ OK
4. **НО!** Если CCXT вернёт другой формат (например 'StopMarket' или 'stopMarket')
5. После `.upper()` получится 'STOPMARKET' (без подчёркивания)
6. Защита НЕ сработает → SL удаляется!

### Сценарий 3: Асинхронность
1. Позиция создана, SL установлен
2. Zombie manager проверяет позиции ДО того как они загрузились в memory
3. Считает SL orphaned и удаляет

---

## 📋 РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ

### 1. Усилить защиту PROTECTIVE_ORDER_TYPES
**Приоритет:** КРИТИЧЕСКИЙ
**Что делать:** Проверять не только точное совпадение, но и вхождение подстроки

```python
# Текущий код:
if order_type.upper() in PROTECTIVE_ORDER_TYPES:
    return None

# Улучшенный код:
PROTECTIVE_KEYWORDS = ['STOP', 'TAKE_PROFIT', 'TRAILING']
order_type_upper = order_type.upper()

# Check exact match first
if order_type_upper in PROTECTIVE_ORDER_TYPES:
    return None

# Check if contains protective keywords
if any(keyword in order_type_upper for keyword in PROTECTIVE_KEYWORDS):
    logger.debug(f"Skipping protective order {order_id} ({order_type})")
    return None
```

### 2. Проверять reduceOnly flag
**Приоритет:** ВЫСОКИЙ
**Что делать:** SL ордера всегда имеют `reduceOnly=True`

```python
# Дополнительная защита:
if order.get('reduceOnly') == True:
    logger.debug(f"Skipping reduceOnly order {order_id} - likely SL/TP")
    return None
```

### 3. Добавить whitelist для SL ордеров
**Приоритет:** СРЕДНИЙ
**Что делать:** Вести список order_id которые являются SL

```python
# При создании SL сохранять ID:
self.protected_order_ids = set()

# В StopLossManager при создании SL:
order = await self.exchange.create_order(...)
self.protected_order_ids.add(order['id'])

# В zombie_manager:
if order_id in self.protected_order_ids:
    return None
```

### 4. Логировать перед удалением
**Приоритет:** ВЫСОКИЙ
**Что делать:** Всегда логировать ЧТО удаляется

```python
# Перед отменой ордера:
logger.warning(
    f"🧟 DELETING ORDER: {order_id} on {symbol}\n"
    f"  Type: {order_type}, Side: {side}, Amount: {amount}\n"
    f"  Reason: {zombie.reason}\n"
    f"  ⚠️ IF THIS IS A STOP-LOSS - CRITICAL BUG!"
)
```

### 5. Проверять наличие SL после zombie cleanup
**Приоритет:** КРИТИЧЕСКИЙ
**Что делать:** После работы zombie_manager проверять все позиции

```python
# После zombie cleanup:
await self.position_manager.check_positions_protection()
```

---

## 🎯 ПЛАН ДЕЙСТВИЙ (требует вашего утверждения)

### Фаза 1: Немедленная защита (5 минут)
1. ✅ Усилить проверку PROTECTIVE_ORDER_TYPES (keyword matching)
2. ✅ Добавить проверку reduceOnly flag
3. ✅ Добавить детальное логирование перед удалением

### Фаза 2: Улучшенный мониторинг (10 минут)
4. ✅ Добавить проверку SL сразу после zombie cleanup
5. ✅ Уменьшить интервал check_positions_protection с 5 до 2 минут
6. ✅ Добавить алерт если SL отсутствует более 30 секунд

### Фаза 3: Долгосрочная защита (15 минут)
7. ✅ Добавить whitelist для protected order IDs
8. ✅ Сохранять mapping position_id → sl_order_id в БД
9. ✅ Проверять whitelist перед любой отменой ордера

---

## 📊 МЕТРИКИ ДЛЯ ТЕСТИРОВАНИЯ

После внедрения исправлений проверить:
1. ✅ Создать 5 позиций с SL
2. ✅ Подождать 10 минут
3. ✅ Проверить что SL всё ещё на месте
4. ✅ Запустить zombie_manager вручную
5. ✅ Проверить что SL НЕ были удалены
6. ✅ Проверить логи на наличие warning о protective orders

---

## 🚨 КРИТИЧЕСКИЕ ВЫВОДЫ

1. **SL НЕ удаляются сейчас** - текущие 6 позиций защищены
2. **Проблема была раньше** - 5 позиций потеряли SL из-за bug с tracking
3. **Защита ЕСТЬ но НЕ идеальна** - keyword matching улучшит надёжность
4. **Нужен дополнительный мониторинг** - проверка каждые 2 минуты вместо 5

---

## ✅ ГОТОВО К УТВЕРЖДЕНИЮ

Жду вашего решения:
- ✅ Утвердить план и начать внедрение
- ⏸️ Запросить дополнительную информацию
- 🔄 Изменить приоритеты исправлений