# 🔍 РАССЛЕДОВАНИЕ: Попытка обновления entry_price

## 📋 SUMMARY

**Дата**: 2025-10-12 21:06:25
**Позиция**: #5 (1000WHYUSDT)
**Проблема**: Код пытается обновить `entry_price` после размещения entry order
**Статус**: ✅ Защита сработала корректно, но код содержит ЛОГИЧЕСКУЮ ОШИБКУ

---

## 🚨 ЧТО ПРОИЗОШЛО

### Лог-запись:
```
2025-10-12 21:06:25,922 - database.repository - WARNING - ⚠️ Attempted to update entry_price for position 5 - IGNORED (entry_price is immutable)
```

### Timeline событий:
```
21:06:25,036 - Position record created: ID=5
21:06:25,116 - Entry order placed: 13942421
21:06:25,922 - ⚠️ Attempted to update entry_price - IGNORED  ← ЗДЕСЬ
21:06:26,101 - Placing stop-loss
```

---

## 🔎 ROOT CAUSE ANALYSIS

### Источник проблемы: `core/atomic_position_manager.py:197-201`

```python
# Step 2: После размещения entry order
logger.info(f"✅ Entry order placed: {entry_order.id}")

# Extract execution price from normalized order
exec_price = ExchangeResponseAdapter.extract_execution_price(entry_order)

# FIX: Use only columns that exist in database schema
await self.repository.update_position(position_id, **{
    'entry_price': exec_price,  # ❌ ПРОБЛЕМА ЗДЕСЬ!
    'status': state.value,
    'exchange_order_id': entry_order.id
})
```

### Что происходит:

1. **Создание позиции** (строка ~135):
   ```python
   position_id = await self.repository.create_position({
       'signal_id': position_data.get('signal_id'),
       'symbol': symbol,
       'exchange': exchange,
       'side': side,
       'quantity': quantity,
       'entry_price': entry_price,  # ← Цена от сигнала (например, 2.75e-05)
       'exchange_order_id': None
   })
   ```

2. **Размещение entry order** (строка 172):
   ```python
   raw_order = await exchange_instance.create_market_order(
       symbol, side, quantity
   )
   ```

3. **Извлечение цены исполнения** (строка 194):
   ```python
   exec_price = ExchangeResponseAdapter.extract_execution_price(entry_order)
   # exec_price может отличаться от entry_price (например, 2.7501e-05)
   ```

4. **ПОПЫТКА ОБНОВИТЬ entry_price** (строка 197-198):
   ```python
   await self.repository.update_position(position_id, **{
       'entry_price': exec_price,  # ❌ Пытается перезаписать!
       ...
   })
   ```

5. **Защита срабатывает** (`database/repository.py:476-482`):
   ```python
   if 'entry_price' in kwargs:
       logger.warning(f"⚠️ Attempted to update entry_price for position {position_id} - IGNORED")
       del kwargs['entry_price']
   ```

---

## 🎯 ПРАВИЛЬНОЕ ПОНИМАНИЕ ПОЛЕЙ

### `entry_price` (IMMUTABLE):
- **Назначение**: Цена ВХОДА в позицию (price at which position was opened)
- **Устанавливается**: ОДИН РАЗ при создании позиции
- **Используется для**:
  - Расчета Stop-Loss
  - Расчета PnL
  - Исторического анализа
- **НИКОГДА не должна меняться** после создания позиции!

### `current_price` (MUTABLE):
- **Назначение**: Текущая рыночная цена актива
- **Обновляется**: Постоянно (из WebSocket, из проверок, при закрытии)
- **Используется для**:
  - Отображения текущего состояния
  - Расчета unrealized PnL
  - Trailing stop logic

### `exec_price` vs `entry_price`:
```python
# exec_price = цена исполнения ордера на бирже
# entry_price = цена входа (может быть от сигнала ИЛИ exec_price)

# ПРАВИЛЬНО:
entry_price = exec_price  # При создании позиции

# НЕПРАВИЛЬНО:
entry_price = exec_price  # После создания позиции ❌
```

---

## 💡 КОРНЕВАЯ ПРИЧИНА: КОНЦЕПТУАЛЬНАЯ ОШИБКА

### Проблема в дизайне:

Код пытается реализовать следующую логику:
1. Создать позицию с **предварительной** ценой (от сигнала)
2. Разместить entry order
3. Обновить entry_price **реальной** ценой исполнения

### Почему это неправильно:

1. **entry_price должна быть ФИНАЛЬНОЙ** с самого начала
2. Если цена исполнения важна, она должна быть entry_price с САМОГО СОЗДАНИЯ
3. Обновление entry_price после создания = изменение истории

### Правильный подход:

**Вариант A**: Использовать exec_price как entry_price с самого начала
```python
# Step 1: Создать позицию
position_id = await self.repository.create_position({
    'entry_price': None,  # Пока не знаем
    ...
})

# Step 2: Разместить entry order
raw_order = await exchange.create_market_order(...)
exec_price = extract_execution_price(raw_order)

# Step 3: ПЕРВОЕ и ЕДИНСТВЕННОЕ обновление entry_price
await self.repository.update_position(position_id, **{
    'entry_price': exec_price,  # ✅ Первое заполнение, не обновление
    ...
})
```

**Вариант B**: Оставить entry_price immutable, но использовать exec_price для СОЗДАНИЯ
```python
# Step 1: Разместить entry order СНАЧАЛА
raw_order = await exchange.create_market_order(...)
exec_price = extract_execution_price(raw_order)

# Step 2: Создать позицию с exec_price
position_id = await self.repository.create_position({
    'entry_price': exec_price,  # ✅ Финальная цена с самого начала
    ...
})
```

**Вариант C** (ТЕКУЩИЙ): Использовать цену от сигнала, НЕ ОБНОВЛЯТЬ
```python
# Step 1: Создать позицию с ценой от сигнала
position_id = await self.repository.create_position({
    'entry_price': signal_price,  # ✅ Остается навсегда
    ...
})

# Step 2: Разместить entry order
raw_order = await exchange.create_market_order(...)
exec_price = extract_execution_price(raw_order)

# Step 3: Обновить CURRENT_PRICE (не entry_price!)
await self.repository.update_position(position_id, **{
    'current_price': exec_price,  # ✅ Текущая цена, не цена входа
    'status': state.value,
    'exchange_order_id': entry_order.id
})
```

---

## 🔧 РЕКОМЕНДОВАННОЕ ИСПРАВЛЕНИЕ

### Файл: `core/atomic_position_manager.py:197-201`

#### ❌ ТЕКУЩИЙ КОД:
```python
await self.repository.update_position(position_id, **{
    'entry_price': exec_price,  # ❌ Попытка обновить immutable поле
    'status': state.value,
    'exchange_order_id': entry_order.id
})
```

#### ✅ ИСПРАВЛЕННЫЙ КОД:
```python
# CRITICAL FIX: Update current_price, NOT entry_price
# entry_price is immutable and set once at position creation
# exec_price should update current_price to track market movement
await self.repository.update_position(position_id, **{
    'current_price': exec_price,  # ✅ Обновляем текущую цену
    'status': state.value,
    'exchange_order_id': entry_order.id
})
```

### Обоснование:

1. **entry_price уже установлена** при создании позиции (строка ~135)
2. **exec_price = текущая цена** на момент исполнения ордера
3. **current_price** - правильное поле для отслеживания текущей цены
4. **Сохраняем GOLDEN RULE**: Минимальное изменение (1 слово)

---

## 📊 IMPACT ANALYSIS

### Текущее поведение (С защитой):

```
CREATE position: entry_price = 2.75e-05, current_price = NULL
↓
PLACE entry order: exec_price = 2.7501e-05
↓
TRY UPDATE: entry_price = 2.7501e-05  ← ЗАБЛОКИРОВАНО
↓
RESULT: entry_price = 2.75e-05 (original), current_price = NULL
```

**Проблемы**:
- ✅ entry_price защищена
- ❌ current_price не обновляется
- ❌ Нет информации о реальной цене исполнения

### После исправления:

```
CREATE position: entry_price = 2.75e-05, current_price = NULL
↓
PLACE entry order: exec_price = 2.7501e-05
↓
UPDATE: current_price = 2.7501e-05  ← ПРАВИЛЬНО
↓
RESULT: entry_price = 2.75e-05 (original), current_price = 2.7501e-05
```

**Преимущества**:
- ✅ entry_price защищена и неизменна
- ✅ current_price отражает реальную цену исполнения
- ✅ PnL расчеты корректны
- ✅ WebSocket updates будут обновлять current_price дальше

---

## 🎯 RELATED ISSUES

### 1. Stop-Loss расчет

Текущий код использует `entry_price` для расчета SL (ПРАВИЛЬНО):
```python
stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
```

После исправления ничего не изменится:
- entry_price остается такой же
- SL расчитывается от entry_price (как и должно быть)

### 2. PnL расчет

```python
pnl = (current_price - entry_price) / entry_price * 100
```

После исправления:
- entry_price = цена от сигнала (2.75e-05)
- current_price = цена исполнения → WebSocket updates (2.7501e-05, 2.76e-05, ...)
- PnL корректный ✅

### 3. WebSocket position updates

```python
# update_position_from_websocket обновляет current_price
UPDATE monitoring.positions
SET current_price = $1,
    unrealized_pnl = $2,
    updated_at = NOW()
WHERE symbol = $3 AND exchange = $4 AND status = 'active'
```

После исправления будет корректно обновлять current_price ✅

---

## ✅ ВЫВОДЫ

1. **Защита работает корректно**: entry_price правильно защищена от изменений

2. **Код содержит логическую ошибку**: Пытается обновить entry_price вместо current_price

3. **Исправление простое**: Заменить `'entry_price'` на `'current_price'` (1 слово)

4. **Исправление безопасное**:
   - GOLDEN RULE compliant (минимальное изменение)
   - Не влияет на SL расчеты
   - Не влияет на PnL расчеты
   - Улучшает корректность current_price tracking

5. **Приоритет**: MEDIUM
   - Не критично (защита работает)
   - Но желательно исправить (current_price не обновляется корректно)

---

## 📝 NEXT STEPS

### Рекомендация:

**Применить хирургическое исправление:**

```python
# File: core/atomic_position_manager.py:197-198
# Change: entry_price → current_price (1 word)

- 'entry_price': exec_price,
+ 'current_price': exec_price,
```

**После применения:**
1. Тест: Создать позицию и проверить current_price
2. Commit: "🔧 FIX: Update current_price instead of entry_price after order execution"
3. Monitor: Убедиться что current_price обновляется корректно

---

## 🏷️ TAGS

`#entry_price` `#immutable` `#atomic_position_manager` `#logical_error` `#current_price` `#investigation`
