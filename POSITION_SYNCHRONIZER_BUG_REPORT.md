# 🐛 КРИТИЧЕСКИЙ БАГ: Position Synchronizer создаёт фантомные записи

## 📋 ПРОБЛЕМА

**130 из 177 позиций (73%)** за день созданы **НЕ через волновой механизм**, а через **Position Synchronizer** с `signal_id=NULL` и `exchange_order_id=NULL`.

### Волна 17:09 - 38 фантомных позиций:
```
17:09:37-17:09:45 → 38 позиций
  signal_id = NULL (не через волны)
  exchange_order_id = NULL (НЕТ на бирже!)
  Закрыто: 28 причиной "sync_cleanup" в 19:53-20:16
  До сих пор открыто: 10 позиций
```

---

## 🔍 КОРНЕВАЯ ПРИЧИНА

### Механизм синхронизации

**Файл**: `core/position_manager.py:244`
```python
async def load_positions_from_db(self):
    """Load open positions from database on startup"""
    # FIRST: Synchronize with exchanges
    await self.synchronize_with_exchanges()  # ← ПРОБЛЕМА ТУТ
    
    # THEN: Load verified positions
    positions = await self.repository.get_open_positions()
```

**Вызывается**: При старте бота

### Логика синхронизатора

**Файл**: `core/position_synchronizer.py:96-185`

```python
async def synchronize_exchange(self, exchange_name: str, exchange):
    # 1. Получить позиции из БД
    db_positions = await self.repository.get_open_positions()
    
    # 2. Получить позиции с биржи
    exchange_positions = await self._fetch_exchange_positions(exchange)
    
    # 3. Проверить БД позиции на бирже
    for symbol in db_positions:
        if symbol not in exchange_positions:
            # Закрыть фантом в БД ✅ ПРАВИЛЬНО
            await self._close_phantom_position(db_pos)
    
    # 4. Добавить "недостающие" позиции с биржи
    for symbol in exchange_positions:
        if symbol not in db_map:
            # ❌ ПРОБЛЕМА: Добавить в БД без проверки реальности!
            await self._add_missing_position(exchange_name, exchange_pos)
```

### Метод добавления "недостающих" позиций

**Файл**: `core/position_synchronizer.py:249-298`

```python
async def _add_missing_position(self, exchange_name: str, exchange_position: Dict):
    """Add a position that exists on exchange but missing from database"""
    
    # Создать запись в БД
    position_data = {
        'symbol': normalize_symbol(symbol),
        'exchange': exchange_name,
        'side': side,
        'quantity': abs(contracts),
        'entry_price': entry_price,
        'current_price': current_price,
        'strategy': 'MANUAL',
        'signal_id': None,  # ← Нет signal_id!
        # ← НЕТ exchange_order_id!
    }
    
    # Добавить в БД
    position_id = await self.repository.open_position(position_data)
```

**ПРОБЛЕМА**: Метод создаёт запись **БЕЗ exchange_order_id**!

### Откуда берутся "позиции с биржи"

**Файл**: `core/position_synchronizer.py:187-218`

```python
async def _fetch_exchange_positions(self, exchange, exchange_name: str):
    # Получить позиции от CCXT
    positions = await exchange.fetch_positions()
    
    # Фильтр: только с contracts > 0
    active_positions = []
    for pos in positions:
        contracts = float(pos.get('contracts') or 0)
        if abs(contracts) > 0:  # ❌ ЕДИНСТВЕННАЯ ПРОВЕРКА!
            active_positions.append(pos)
    
    return active_positions
```

**КРИТИЧЕСКАЯ ОШИБКА**:
- Проверка только `abs(contracts) > 0`
- **НЕТ проверки** что позиция реально существует
- CCXT может вернуть **старые/кэшированные/закрытые** позиции
- Все они попадут в список "активных"

---

## 🕵️ ЧТО ПРОИЗОШЛО В 17:09?

### Хронология:
```
17:00:44 - Первые 2 синхронизированные позиции
17:09:37-45 - МАССОВАЯ синхронизация 38 позиций (за 7.5 сек!)
```

### Гипотеза:
1. **Бот перезапустился** около 17:00
2. Вызвался `load_positions_from_db()` → `synchronize_with_exchanges()`
3. CCXT `fetch_positions()` вернул **СТАРЫЕ данные** (кэш/задержка)
4. Синхронизатор добавил ВСЕ 38 "позиций" в БД
5. Реально на бирже их **НЕ БЫЛО**

---

## 📊 МАСШТАБ ПРОБЛЕМЫ

### Статистика за день:
- **177 позиций** всего
- **49 через волны** (signal_id есть) ✅
- **130 синхронизированы** (signal_id=NULL) ❌
  - Из них с exchange_order_id: **~50** (реальные)
  - Без exchange_order_id: **~80** (фантомы!)

### Последствия:
1. **База замусорена** фантомными записями
2. **Статистика искажена** (130 vs 49)
3. **Cleanup приходится запускать** вручную
4. **Логи засорены** попытками установить SL на фантомы

---

## ✅ РЕШЕНИЕ

### 1. КРИТИЧЕСКОЕ: Проверять exchange_order_id

**Файл**: `core/position_synchronizer.py:187-218`

```python
async def _fetch_exchange_positions(self, exchange, exchange_name: str):
    positions = await exchange.fetch_positions()
    
    active_positions = []
    for pos in positions:
        contracts = float(pos.get('contracts') or 0)
        
        # ✅ КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Проверить реальность позиции
        if abs(contracts) > 0:
            # Дополнительная проверка: есть ли order ID или timestamp недавний
            info = pos.get('info', {})
            
            # Для Binance: проверить positionAmt + timestamp
            if exchange_name == 'binance':
                position_amt = float(info.get('positionAmt', 0))
                if abs(position_amt) <= 0.0001:  # Позиция закрыта
                    logger.debug(f"Skipping closed position: {pos['symbol']}")
                    continue
            
            # Для Bybit: проверить size + updated timestamp
            elif exchange_name == 'bybit':
                size = float(info.get('size', 0))
                if abs(size) <= 0.0001:  # Позиция закрыта
                    logger.debug(f"Skipping closed position: {pos['symbol']}")
                    continue
            
            active_positions.append(pos)
    
    return active_positions
```

### 2. ВАЖНО: Сохранять exchange_order_id

**Файл**: `core/position_synchronizer.py:249-298`

```python
async def _add_missing_position(self, exchange_name: str, exchange_position: Dict):
    # Получить exchange order ID
    info = exchange_position.get('info', {})
    
    # Для Binance
    if exchange_name == 'binance':
        exchange_order_id = info.get('positionId') or info.get('id')
    
    # Для Bybit
    elif exchange_name == 'bybit':
        exchange_order_id = info.get('positionIdx') or info.get('orderId')
    else:
        exchange_order_id = None
    
    # ✅ ДОБАВИТЬ exchange_order_id В ДАННЫЕ
    position_data = {
        'symbol': normalize_symbol(symbol),
        'exchange': exchange_name,
        'side': side,
        'quantity': abs(contracts),
        'entry_price': entry_price,
        'current_price': current_price,
        'exchange_order_id': exchange_order_id,  # ✅ КРИТИЧЕСКОЕ!
        'strategy': 'MANUAL',
        'signal_id': None
    }
```

### 3. ДОПОЛНИТЕЛЬНО: Добавить валидацию перед добавлением

```python
async def _add_missing_position(self, exchange_name: str, exchange_position: Dict):
    # ✅ ВАЛИДАЦИЯ: Не добавлять позиции БЕЗ order ID
    if not exchange_order_id:
        logger.warning(
            f"Skipping position without exchange_order_id: "
            f"{symbol} (likely stale data)"
        )
        return
    
    # ✅ ВАЛИДАЦИЯ: Проверить что позиция недавняя
    timestamp = exchange_position.get('timestamp')
    if timestamp:
        age_seconds = (datetime.now(timezone.utc).timestamp() * 1000 - timestamp) / 1000
        if age_seconds > 3600:  # Старше 1 часа
            logger.warning(
                f"Skipping old position: {symbol} "
                f"(age: {age_seconds/60:.1f} min)"
            )
            return
    
    # Далее создание записи...
```

---

## 🎯 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

### После исправления:
```
✅ Синхронизатор добавляет ТОЛЬКО реальные позиции с биржи
✅ Все добавленные позиции имеют exchange_order_id
✅ Старые/закрытые позиции игнорируются
✅ База данных чистая
```

### Статистика станет:
```
Всего позиций: ~100 (вместо 177)
  ├─ Через волны: 49 (50%)
  └─ Синхронизированы: ~50 (50%, только реальные)
```

---

## 🔧 ПРИОРИТЕТ

**КРИТИЧЕСКИЙ** - синхронизатор мусорит БД фантомными записями на каждом старте бота

**ETA исправления**: 10-15 минут

---

## 📝 ДОПОЛНИТЕЛЬНО

### Вопросы для проверки:
1. Как часто перезапускается бот? (каждый перезапуск = волна фантомов)
2. Есть ли автоматический cleanup? (видим "sync_cleanup" в 19:53-20:16)
3. Нужна ли вообще синхронизация при старте? (может лучше trust БД?)

### Альтернативное решение:
**Отключить автоматическую синхронизацию** при старте:
```python
async def load_positions_from_db(self):
    # ОТКЛЮЧИТЬ автосинхронизацию
    # await self.synchronize_with_exchanges()
    
    # Загрузить позиции и проверить каждую
    positions = await self.repository.get_open_positions()
    for pos in positions:
        position_exists = await self.verify_position_exists(...)
```

