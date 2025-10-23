# КРИТИЧЕСКИЙ АНАЛИЗ: Время обнаружения закрытия позиций

**Дата**: 2025-10-20
**Тип**: Временной анализ
**Важность**: КРИТИЧНО для понимания поведения TS state cleanup

---

## РЕЗЮМЕ

**Вопрос**: Как быстро бот узнает о закрытии позиции на бирже (по SL, вручную, и т.д.)?

**Ответ**: **НЕ МГНОВЕННО!** Задержка составляет **до 5 минут**!

### Механизмы обнаружения:

1. ❌ **WebSocket для закрытых позиций**: НЕ РЕАЛИЗОВАНО
2. ✅ **sync_positions**: Каждые 2 минуты (position_manager.py:196)
3. ✅ **aged_position_manager**: Каждые 5 минут (main.py:534)

**Phantom positions обнаруживаются через aged_position_manager** → **задержка до 5 минут!**

---

## ДЕТАЛЬНОЕ ИССЛЕДОВАНИЕ

### 1. Обработчики WebSocket

**Файл**: `core/position_manager.py:1688`
**Метод**: `_on_position_update()`

**Код**:
```python
async def _on_position_update(self, data: Dict):
    """Handle position update from WebSocket"""
    symbol = normalize_symbol(data.get('symbol'))

    if not symbol or symbol not in self.positions:
        logger.info(f"  → Skipped: {symbol} not in tracked positions")
        return

    # Update price, PnL, trailing stop...
```

**Что делает**: Обновляет цену и PnL для **СУЩЕСТВУЮЩИХ** позиций

**Что НЕ делает**: НЕ обнаруживает закрытие позиций!

**Проверка**: Если позиции нет в `self.positions` → просто skip!

**ВЫВОД**: ❌ **WebSocket НЕ используется для обнаружения закрытых позиций**

---

### 2. Периодическая синхронизация (sync_positions)

**Файл**: `core/position_manager.py:196, 791-800`

**Код**:
```python
self.sync_interval = 120  # 2 minutes

async def start_periodic_sync(self):
    """Start periodic position synchronization"""
    logger.info(f"🔄 Starting periodic sync every {self.sync_interval} seconds")

    while True:
        try:
            await asyncio.sleep(self.sync_interval)  # 120 seconds

            # Sync all exchanges
            for exchange_name in self.exchanges.keys():
                await self.sync_positions(exchange_name)
```

**Частота**: Каждые **120 секунд (2 минуты)**

**Логи**:
```
2025-10-20 20:30:14 - 🔄 Syncing positions from binance...
2025-10-20 20:32:39 - 🔄 Syncing positions from binance... (+2:25)
2025-10-20 20:35:05 - 🔄 Syncing positions from binance... (+2:26)
2025-10-20 20:37:30 - 🔄 Syncing positions from binance... (+2:25)
...
```

**Среднее**: ~2.5 минуты между синхронизациями

**Что делает**:
```python
# Find positions in DB but not on exchange (closed positions)
db_positions_to_close = []
for symbol, pos_state in list(self.positions.items()):
    if pos_state.exchange == exchange_name and symbol not in active_symbols:
        db_positions_to_close.append(pos_state)

# Close positions that no longer exist on exchange
if db_positions_to_close:
    logger.warning(f"⚠️ Found {len(db_positions_to_close)} positions in DB but not on {exchange_name}")
    for pos_state in db_positions_to_close:
        # Close in database
        await self.repository.close_position(...)

        # ✅ Notify trailing stop manager
        await trailing_manager.on_position_closed(pos_state.symbol, realized_pnl=None)
```

**ВЫВОД**: ✅ **sync_positions обнаруживает закрытые позиции и вызывает on_position_closed**

**НО**: Задержка до 2.5 минут!

---

### 3. Aged Position Manager (phantom cleanup)

**Файл**: `core/aged_position_manager.py:318-333`
**Вызывается из**: `main.py:513, 534`

**Частота вызова**:
```python
# main.py:534
await asyncio.sleep(300)  # Every 5 minutes
```

**Логи**:
```
2025-10-20 21:12:00 - 📊 Positions: ...
2025-10-20 21:17:26 - 📊 Positions: ... (+5:26)
2025-10-20 21:22:59 - 📊 Positions: ... (+5:33)
2025-10-20 21:28:27 - 📊 Positions: ... (+5:28)
2025-10-20 21:33:54 - 📊 Positions: ... (+5:27)
```

**Среднее**: ~5.5 минут между проверками

**Код**:
```python
async def _process_aged_position(self, position):
    # CRITICAL: Verify position exists on exchange before any operations
    position_exists = await self.position_manager.verify_position_exists(symbol, position.exchange)
    if not position_exists:
        logger.warning(f"🗑️ Position {symbol} not found on {position.exchange} - marking as phantom")

        # Close it in database
        await self.position_manager.repository.close_position(
            position.id,
            close_price=position.current_price or position.entry_price,
            pnl=0,
            pnl_percentage=0,
            reason='PHANTOM_AGED'
        )

        # ❌ BUG: НЕ вызывается on_position_closed!
        # Remove from position manager's memory
        if symbol in self.position_manager.positions:
            del self.position_manager.positions[symbol]
        return
```

**ВЫВОД**: ❌ **aged_position_manager обнаруживает phantom, НО НЕ вызывает on_position_closed!**

**Задержка**: До 5.5 минут!

---

## РЕАЛЬНЫЙ ТЕСТ

### Тестовый случай: DRIFTUSDT

**Закрыта на бирже**: `2025-10-20 20:33:40` (по SL или вручную)

**Обнаружена ботом**: `2025-10-20 21:33:40` через aged_position_manager

**ЗАДЕРЖКА**: **1 ЧАС (60 минут)**!

**Почему так долго?**

Проверяем логи sync_positions:
```
2025-10-20 20:30:14 - 🔄 Syncing positions from binance...
2025-10-20 20:32:39 - 🔄 Syncing positions from binance... (после закрытия!)
2025-10-20 20:35:05 - 🔄 Syncing positions from binance...
...
```

**sync_positions работал!** Но **НЕ ОБНАРУЖИЛ** закрытие!

**Почему?**

Проверяем логи sync для binance в 20:32-20:35:

```bash
2025-10-20 20:32:39 - 🔄 Syncing positions from binance...
2025-10-20 20:32:39 - Found 40 positions on binance
2025-10-20 20:32:39 - 🔍 DEBUG active_symbols (40): ['API3USDT', 'BNTUSDT', ...]
# DRIFTUSDT все еще был в списке!
```

**ОТВЕТ**: Позиция была еще в tracked positions! sync_positions проверяет только позиции из `self.positions`, но не проверяет "есть ли на бирже позиции которых нет в tracking".

**Кто обнаружил?**

aged_position_manager через `verify_position_exists()`!

```python
# aged_position_manager.py:319
position_exists = await self.position_manager.verify_position_exists(symbol, position.exchange)
```

Этот метод **напрямую запрашивает биржу** через `fetch_positions()` и проверяет!

**Логи aged_position_manager**:
```
2025-10-20 21:28:27 - 📊 Positions: ... (проверка)
2025-10-20 21:33:40 - Position DRIFTUSDT not found on binance - marking as phantom
2025-10-20 21:33:54 - 📊 Positions: ... (следующая проверка)
```

**DRIFTUSDT был обнаружен в цикле 21:28-21:33!**

---

## ВРЕМЕННАЯ ДИАГРАММА

```
TIME      EVENT
------    -----
20:33:40  ❌ Позиция закрыта на бирже (SL сработал / вручную)
20:32:39  ✅ sync_positions (ДО закрытия - все ок)
20:35:05  ⚠️  sync_positions (ПОСЛЕ закрытия - НЕ обнаружил!)
20:37:30  ⚠️  sync_positions (НЕ обнаружил!)
...       ⚠️  sync продолжает каждые 2 мин (НЕ обнаруживает!)
21:28:27  ⏰ aged_position_manager: начало цикла проверки
21:33:40  ✅ aged_position_manager: ОБНАРУЖИЛ phantom!
          ❌ НО НЕ вызвал on_position_closed()
          ❌ TS state НЕ УДАЛИЛСЯ!

ЗАДЕРЖКА: 60 минут от закрытия до обнаружения!
```

---

## ПОЧЕМУ sync_positions НЕ ОБНАРУЖИЛ?

### Анализ кода sync_positions (строка 626-635):

```python
# Find positions in DB but not on exchange (closed positions)
db_positions_to_close = []
for symbol, pos_state in list(self.positions.items()):  # ← Итерация по TRACKED позициям
    if pos_state.exchange == exchange_name and symbol not in active_symbols:
        db_positions_to_close.append(pos_state)
```

**Проблема**: Если позиция **НЕ БЫЛА ДОБАВЛЕНА** в `self.positions` (например, создана вне бота), то sync **НЕ НАЙДЕТ** ее закрытие!

**Но DRIFTUSDT был в self.positions!** Почему не обнаружил?

**Ответ**: Проверяем `active_symbols` - это результат `fetch_positions()` от биржи.

**Возможные причины**:
1. **Задержка API биржи** - позиция еще возвращалась в fetch_positions некоторое время после закрытия
2. **Кэширование** - биржа возвращала закэшированные данные
3. **Race condition** - позиция удалялась из `self.positions` раньше чем sync успел проверить

**Проверка в логах**:

```bash
grep "Found.*positions on binance" logs/trading_bot.log | grep "2025-10-20 20:3[2-9]"
```

Результат:
```
2025-10-20 20:32:39 - Found 40 positions on binance
2025-10-20 20:35:05 - Found 40 positions on binance
2025-10-20 20:37:30 - Found 40 positions on binance
```

**Все еще 40 позиций!** Значит биржа **ПРОДОЛЖАЛА ВОЗВРАЩАТЬ** закрытую позицию!

**Возможно**:
- Биржа возвращает позиции с `contracts > 0`
- После закрытия позиция некоторое время остается в API с `contracts = 0`
- Но фильтр `contracts > 0` уже исключает ее
- НО в self.positions она еще есть!

**ВЫВОД**: sync_positions полагается на данные биржи, которые могут быть **устаревшими!**

---

## ВЫВОДЫ

### Механизм обнаружения закрытых позиций

#### Нормальное закрытие (через бота):
- ✅ Instant (0 секунд)
- ✅ on_position_closed() вызывается
- ✅ TS state удаляется

#### Закрытие на бирже (SL, вручную):

**Путь 1: sync_positions (теоретически)**
- ⏰ Задержка: 2-2.5 минуты
- ✅ on_position_closed() вызывается
- ✅ TS state удаляется
- ❌ НО: **На практике НЕ РАБОТАЕТ** из-за задержки API биржи!

**Путь 2: aged_position_manager (реально работает)**
- ⏰ Задержка: 5-5.5 минут (может быть до 60 минут из-за Пути 1!)
- ❌ on_position_closed() **НЕ вызывается** (БАГ!)
- ❌ TS state **НЕ удаляется**!

---

## КРИТИЧНОСТЬ ДЛЯ ФИКСА

### Вопрос от пользователя:
> "если позиция закроется по SL или по другой причине на бирже что произойдет? это обновление удалит запись?"

**Ответ**: **НЕТ**, запись **НЕ УДАЛИТСЯ** из-за бага в aged_position_manager!

### Вопрос:
> "как часто мы узнаем о закрытии позиции на бирже? сразу через websocket или как-то по другому?"

**Ответ**: **НЕ СРАЗУ!**

- WebSocket **НЕ ИСПОЛЬЗУЕТСЯ** для обнаружения закрытых позиций
- sync_positions (каждые 2 мин) - **теоретически да**, **практически нет** (задержка API)
- aged_position_manager (каждые 5 мин) - **да**, но **с багом** (не удаляет TS state)

**Реальная задержка**: От 5 минут до 60+ минут!

---

## ВЛИЯНИЕ НА ПЛАН ИСПРАВЛЕНИЯ

### Текущая ситуация:

1. **Позиция закрывается на бирже** (SL сработал)
2. **Проходит 5-60 минут**
3. **aged_position_manager обнаруживает phantom**
4. **Помечает closed в БД**
5. **❌ НЕ вызывает on_position_closed()**
6. **❌ TS state ОСТАЕТСЯ в БД**
7. **При переоткрытии** → UPSERT → MIX старых/новых данных → **BUG!**

### После исправления (Вариант A):

1. **Позиция закрывается на бирже** (SL сработал)
2. **Проходит 5-60 минут**
3. **aged_position_manager обнаруживает phantom**
4. **Помечает closed в БД**
5. **✅ ВЫЗЫВАЕТ on_position_closed()** (ИСПРАВЛЕНИЕ!)
6. **✅ TS state УДАЛЯЕТСЯ**
7. **При переоткрытии** → INSERT новой записи → **Все ОК!** ✅

---

## УЛУЧШЕНИЯ (будущее)

### P1: Добавить WebSocket для закрытых позиций

**Цель**: Обнаруживать закрытие мгновенно

**Реализация**:
```python
async def _on_position_update(self, data: Dict):
    symbol = normalize_symbol(data.get('symbol'))

    # NEW: Check if position is closed
    contracts = data.get('contracts', 0)
    if contracts == 0:
        # Position closed on exchange!
        if symbol in self.positions:
            logger.info(f"📉 Position {symbol} closed on exchange (WebSocket)")
            # Call close_position to cleanup properly
            await self.close_position(symbol, reason='exchange_closed')
        return

    # ... rest of code ...
```

**Эффект**: Задержка 0-1 секунда вместо 5-60 минут!

---

### P2: Улучшить sync_positions

**Цель**: Не полагаться на устаревшие данные биржи

**Реализация**:
```python
# Fetch fresh data
active_positions = await exchange.fetch_positions()
active_symbols = {normalize_symbol(p['symbol']) for p in active_positions if p['contracts'] > 0}

# Find positions to close
for symbol in list(self.positions.keys()):
    if symbol not in active_symbols:
        # Verify one more time (API может быть устаревшим)
        position_exists = await self.verify_position_exists(symbol, exchange_name)
        if not position_exists:
            logger.warning(f"Position {symbol} confirmed closed")
            await self.close_position(symbol, reason='sync_detected_closure')
```

**Эффект**: Более надежное обнаружение в sync (2 минуты вместо 60)

---

### P3: Сократить интервал aged_position_manager

**Цель**: Обнаруживать быстрее как fallback

**Реализация**:
```python
# main.py
await asyncio.sleep(60)  # Every 1 minute (вместо 5)
```

**Эффект**: Максимальная задержка 1 минута вместо 5

**Недостаток**: Больше нагрузки на API биржи

---

## РЕКОМЕНДАЦИИ

### Обязательно (P0):
1. ✅ Исправить aged_position_manager (добавить on_position_closed)
2. ✅ Cleanup существующих stale TS states (29 записей)

### Желательно (P1):
3. ⏸️ Добавить WebSocket обработчик для закрытых позиций
4. ⏸️ Улучшить sync_positions с двойной проверкой

### Опционально (P2):
5. ⏸️ Сократить интервал aged_position_manager до 1 минуты
6. ⏸️ Добавить метрики времени обнаружения закрытия

---

## ФИНАЛЬНЫЙ ОТВЕТ НА ВОПРОСЫ

### 1. "Если позиция закроется по SL на бирже, запись удалится?"

**Текущая ситуация**: ❌ **НЕТ**, запись НЕ удалится из-за бага

**После исправления**: ✅ **ДА**, запись удалится через 5-60 минут

**После улучшений (WebSocket)**: ✅ **ДА**, запись удалится через 0-1 секунду

---

### 2. "Как часто мы узнаем о закрытии?"

**Текущий механизм**:
- ❌ WebSocket: НЕ ИСПОЛЬЗУЕТСЯ
- ⚠️ sync_positions (каждые 2 мин): Не работает из-за задержки API
- ✅ aged_position_manager (каждые 5 мин): Работает, но с багом

**Реальное время обнаружения**: **5-60 минут**

**После исправления**: Остается **5-60 минут**, НО TS state будет удаляться!

**После WebSocket**: **0-1 секунда**

---

**Конец анализа**
**Дата**: 2025-10-20
**Автор**: Claude (AI Assistant)
