# 🔴 КОМПЛЕКСНЫЙ АУДИТ ОШИБОК - 2025-10-20 17:03:47

**Время рестарта:** 2025-10-20 17:03:47
**Период анализа:** 17:03:47 - 17:07:30 (~4 минуты)

---

## 📊 КАТЕГОРИИ ОШИБОК

### ❌ КРИТИЧЕСКАЯ ОШИБКА #1: DB Fallback Failed

**Количество:** 14 раз
**Символы:** PIPPINUSDT, USELESSUSDT (повторяющиеся)

**Пример:**
```
17:04:39 - ERROR - ❌ PIPPINUSDT: DB fallback failed: 'Repository' object has no attribute 'get_position_by_symbol'
17:04:39 - ERROR - ❌ SL update failed: PIPPINUSDT - position_not_found
```

**КОРНЕВАЯ ПРИЧИНА:**
- Код вызывает `repository.get_position_by_symbol(symbol, exchange)`
- НО этот метод НЕ СУЩЕСТВУЕТ в Repository!
- Правильный метод: `repository.get_open_position(symbol, exchange)`

**IMPACT:**
- DB fallback НЕ РАБОТАЕТ
- SL не обновляется для активных позиций
- Позиции остаются БЕЗ ЗАЩИТЫ

---

### ❌ ОШИБКА #2: Trailing Stop Not Found

**Количество:** 20+ раз
**Символы:** BLASTUSDT, PIPPINUSDT, USELESSUSDT, TSTUSDT, DMCUSDT, SSVUSDT, ORDERUSDT, IDEXUSDT

**Пример:**
```
17:04:16 - ERROR - [TS] Trailing stop not found for BLASTUSDT! This should not happen. Available TS: []
17:04:59 - ERROR - [TS] Trailing stop not found for IDEXUSDT! This should not happen. Available TS: ['OKBUSDT', 'BLASTUSDT', 'SAROSUSDT', 'DOGUSDT']
```

**ДВА СЦЕНАРИЯ:**

**Сценарий A: Available TS = []** (первые 30 секунд после рестарта)
- TS еще не восстановлены из БД
- WebSocket уже получает price updates
- update_price() вызывается для symbols без TS

**Сценарий B: Available TS = [список]** (после восстановления)
- IDEXUSDT есть в БД как active
- НО TS для него не восстановлен
- Возможно orphaned или проблема с синхронизацией

**IMPACT:**
- Спам в логах (не критично)
- TS не обновляется для некоторых позиций

---

### ❌ ОШИБКА #3: entry_price is 0 (Corrupted Data)

**Количество:** 8 раз
**Символы:** DODOUSDT, ALEOUSDT

**Пример:**
```
17:06:52 - ERROR - ❌ DODOUSDT: entry_price is 0, cannot calculate profit (corrupted data)
17:06:52 - ERROR - ❌ ALEOUSDT: entry_price is 0, cannot calculate profit (corrupted data)
```

**КОРНЕВАЯ ПРИЧИНА:**
- TS восстановлен из БД с `entry_price=0`
- Деление на 0 при расчете profit
- Защита сработала (исправление от предыдущего раза работает!)

**IMPACT:**
- TS не может рассчитать profit
- Активация/обновление TS заблокированы
- НО crash предотвращен

---

### 🔴 КРИТИЧЕСКАЯ ОШИБКА #4: Atomic Position Creation Failed

**Количество:** 1 раз
**Символ:** BADGERUSDT

**Пример:**
```
17:06:38 - ERROR - ❌ Position not found for BADGERUSDT after order. Order status: closed, filled: 0.0
17:06:38 - CRITICAL - ⚠️ CRITICAL: Position without SL detected, closing immediately!
17:06:46 - CRITICAL - ❌ Position BADGERUSDT not found after 10 attempts!
17:06:46 - CRITICAL - ⚠️ ALERT: Open position without SL may exist on exchange!
```

**КОРНЕВАЯ ПРИЧИНА:**
- Order создан, но статус = `closed`, filled = 0
- Позиция не найдена на бирже после 10 попыток
- Вероятно order rejected или instant fill+close

**IMPACT:**
- Position creation rollback
- Возможно потеря средств если позиция все же открылась
- CRITICAL alert

---

## 📈 СТАТИСТИКА ОШИБОК

| Ошибка | Количество | Severity | Fixed? |
|--------|-----------|----------|--------|
| DB fallback failed | 14 | 🔴 CRITICAL | ❌ NO |
| TS not found (startup) | ~15 | ⚠️ MEDIUM | ❓ Expected |
| TS not found (IDEXUSDT) | ~10 | ⚠️ MEDIUM | ❌ NO |
| entry_price=0 | 8 | ⚠️ MEDIUM | ✅ Protected |
| Atomic position failed | 1 | 🔴 CRITICAL | ❓ Separate issue |

---

## 🎯 ПРИОРИТИЗАЦИЯ

### P0 - CRITICAL (Немедленно)

**1. DB Fallback Failed**
- Блокирует основное исправление
- SL не обновляется
- Позиции БЕЗ ЗАЩИТЫ

### P1 - HIGH (В этом sprint)

**2. TS Not Found for IDEXUSDT**
- Orphaned позиция или sync issue
- Recurring error

**3. entry_price=0 Corrupted Data**
- Нужно почистить БД
- Или пересоздать TS

### P2 - MEDIUM (Мониторинг)

**4. TS Not Found During Startup**
- Expected behavior
- Может быть оптимизировано

**5. Atomic Position Creation Failed**
- Отдельная проблема
- Требует отдельного investigation

---

## 🔧 ROOT CAUSES

### #1: Неправильный метод Repository

**Файл:** `core/exchange_manager.py:925`

**Проблема:**
```python
db_position = await self.repository.get_position_by_symbol(symbol, self.name)
```

**Правильно:**
```python
db_position = await self.repository.get_open_position(symbol, self.name)
```

**Структура возврата:**
- `get_open_position()` возвращает `Dict` или `None`
- Нужно проверить доступ к полям: `db_position['status']`, `db_position['quantity']`

---

### #2: TS Synchronization Race Condition

**Проблема:**
- WebSocket price updates приходят БЫСТРЕЕ чем TS восстанавливаются из БД
- update_price() вызывается для symbols без TS

**Решения:**
1. Игнорировать update_price() если TS не найден (текущее)
2. Отложить WebSocket subscription до восстановления TS
3. Buffer updates и apply после initialization

---

### #3: Corrupted DB Data (entry_price=0)

**Проблема:**
- Старые записи в `trailing_stop_state` с поврежденными данными
- Возможно из-за прошлых bugs

**Решения:**
1. SQL cleanup: DELETE WHERE entry_price = 0
2. Или пересоздать TS из positions таблицы
3. Добавить validation при restore

---

## ✅ ЧТО РАБОТАЕТ

1. ✅ **division by zero защита** - entry_price=0 не крашит бот
2. ✅ **Repository передается** - self.repository не None
3. ✅ **DB fallback пытается сработать** - логика вызывается
4. ✅ **Atomic position rollback** - critical alert сработал

---

## 🚨 ЧТО НЕ РАБОТАЕТ

1. ❌ **DB fallback** - неправильный метод
2. ❌ **SL updates** - position_not_found продолжается
3. ❌ **TS для IDEXUSDT** - не восстанавливается
4. ❌ **Corrupted TS data** - entry_price=0 блокирует работу

---

## 📝 PLAN FORWARD

### Шаг 1: Исправить DB Fallback (P0)

**Файл:** `core/exchange_manager.py:925`

**Изменение:**
```python
# БЫЛО:
db_position = await self.repository.get_position_by_symbol(symbol, self.name)

# СТАНЕТ:
db_position = await self.repository.get_open_position(symbol, self.name)
```

**Также проверить:**
- `db_position['status']` вместо `db_position.status`
- `db_position['quantity']` вместо `db_position.quantity`

### Шаг 2: Почистить Corrupted Data (P1)

**SQL:**
```sql
-- Найти все TS с entry_price=0
SELECT symbol, exchange, state, entry_price
FROM monitoring.trailing_stop_state
WHERE entry_price = 0;

-- Удалить corrupted states
DELETE FROM monitoring.trailing_stop_state
WHERE entry_price = 0;
```

### Шаг 3: Исследовать IDEXUSDT (P1)

**Вопросы:**
- Почему TS не восстанавливается?
- Есть ли позиция в БД?
- Orphaned state?

### Шаг 4: Создать Тесты (P0)

**Тесты:**
1. Test DB fallback с mock repository
2. Test get_open_position() возвращает правильные поля
3. Test SL update с DB fallback
4. Integration test: restart → SL update → success

---

## 🎯 SUCCESS CRITERIA

### After Fix #1 (DB Fallback)

- ✅ Логи: "⚠️ PIPPINUSDT: Using DB fallback (quantity=11997)"
- ✅ SL update success: "✅ SL update complete: PIPPINUSDT"
- ❌ NO MORE: "DB fallback failed: 'Repository' object has no attribute"
- ❌ NO MORE: "SL update failed: position_not_found"

### After Fix #2 (Cleanup)

- ✅ NO MORE: "entry_price is 0, cannot calculate profit"
- ✅ TS для DODOUSDT и ALEOUSDT восстановлены или удалены

### After Fix #3 (IDEXUSDT)

- ✅ TS для IDEXUSDT восстановлен
- ❌ NO MORE: "[TS] Trailing stop not found for IDEXUSDT"

---

## 📊 METRICS TO MONITOR

1. **DB Fallback Success Rate**
   - Before: 0% (все падают с AttributeError)
   - Target: 100%

2. **position_not_found Errors**
   - Before: 14 за 4 минуты
   - Target: 0 для active positions

3. **TS Coverage**
   - Current: ~90% (orphaned symbols excluded)
   - Target: 100%

4. **Corrupted Data**
   - Current: 2 symbols (DODOUSDT, ALEOUSDT)
   - Target: 0

---

**ГОТОВ К СОЗДАНИЮ ТЕСТОВ И ПЛАНА ИСПРАВЛЕНИЯ**
