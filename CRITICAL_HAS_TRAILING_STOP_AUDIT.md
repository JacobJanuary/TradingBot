# КРИТИЧЕСКИЙ АУДИТ: Проблема has_trailing_stop=False

## Дата: 2025-10-24
## Статус: КРИТИЧЕСКАЯ ОШИБКА ОБНАРУЖЕНА

---

## 1. ПОДТВЕРЖДЕНИЕ ПРОБЛЕМЫ

### База данных (текущее состояние):
```
Активные позиции:
- 40 позиций с has_trailing_stop=TRUE  ✅
- 15 позиций с has_trailing_stop=FALSE ❌ КРИТИЧЕСКАЯ ОШИБКА!
```

### Примеры проблемных позиций:
```
ID   | SYMBOL       | EXCHANGE | CREATED_AT          | has_trailing_stop | trailing_activated
-----|--------------|----------|---------------------|-------------------|-------------------
3016 | IDEXUSDT     | bybit    | 2025-10-24 02:34:08 | FALSE ❌          | false
3015 | SOSOUSDT     | bybit    | 2025-10-24 02:34:08 | FALSE ❌          | false
3014 | BOBAUSDT     | bybit    | 2025-10-24 02:34:08 | FALSE ❌          | false
2920 | SAROSUSDT    | bybit    | 2025-10-23 17:15:03 | FALSE ❌          | TRUE ⚠️ (рассинхр!)
```

**ОСОБОЕ ВНИМАНИЕ:** Позиция SAROSUSDT имеет `trailing_activated=TRUE` при `has_trailing_stop=FALSE` - это критическая рассинхронизация состояния!

---

## 2. КОРНЕВАЯ ПРИЧИНА ПРОБЛЕМЫ

### 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА #1: Неправильный DEFAULT в схеме БД
**Файл:** `database/models.py:127`
```python
has_trailing_stop = Column(Boolean, default=False)  # ❌ ДОЛЖНО БЫТЬ default=True
```

**Последствия:** Все позиции, создаваемые без явного указания `has_trailing_stop`, получают значение FALSE.

---

## 3. ВСЕ ОБНАРУЖЕННЫЕ ПРОБЛЕМНЫЕ МЕСТА

### 3.1. МОДУЛЬ ВОССТАНОВЛЕНИЯ ПОЗИЦИЙ С БИРЖИ ✅ (Предположение пользователя подтверждено!)

#### 🔴 Место #1: Восстановление существующей позиции из БД
**Файл:** `core/position_manager.py:773`
**Метод:** `sync_exchange_positions()`

```python
has_trailing_stop=db_position.get('has_trailing_stop', False),  # ❌ Default False!
```

**Проблема:** При восстановлении позиции из БД, если поле `has_trailing_stop` отсутствует или NULL, используется False.

**Сценарий:**
1. Позиция существует в БД, но не в памяти (после рестарта)
2. Позиция на бирже есть
3. Система восстанавливает позицию из БД с `has_trailing_stop=False`

#### 🔴 Место #2: Создание НОВОЙ позиции для позиций с биржи
**Файл:** `core/position_manager.py:815`
**Метод:** `sync_exchange_positions()`

```python
position_state = PositionState(
    id=position_id,
    symbol=symbol,
    exchange=exchange_name,
    side=side,
    quantity=quantity,
    entry_price=entry_price,
    current_price=entry_price,
    unrealized_pnl=0,
    unrealized_pnl_percent=0,
    has_stop_loss=False,
    stop_loss_price=None,
    has_trailing_stop=False,  # ❌ ЯВНО УСТАНОВЛЕНО FALSE!
    trailing_activated=False,
    opened_at=datetime.now(timezone.utc),
    age_hours=0
)
```

**Проблема:** Позиции, которые есть на бирже, но отсутствуют в БД, создаются с `has_trailing_stop=False`.

**Сценарий:**
1. Позиция открыта на бирже вручную или через другую систему
2. Позиции нет в локальной БД
3. `sync_exchange_positions()` создаёт новую позицию с `has_trailing_stop=False`
4. Trailing stop для этой позиции НЕ инициализируется!

---

### 3.2. ЗАГРУЗКА ПОЗИЦИЙ ПРИ СТАРТЕ СИСТЕМЫ

#### 🔴 Место #3: Метод _load_positions()
**Файл:** `core/position_manager.py:425`

```python
has_trailing_stop=pos['trailing_activated'] or False,  # ❌ Некорректная логика!
```

**Проблема:**
- Использует `trailing_activated` вместо `has_trailing_stop`
- Если `trailing_activated=False`, то `has_trailing_stop` тоже будет False
- Это НЕПРАВИЛЬНО: trailing stop может быть создан, но ещё не активирован!

**Правильная логика:** `has_trailing_stop` должен отражать наличие trailing stop менеджера, а не его активацию!

---

### 3.3. ОБРАБОТКА ОШИБОК СОЗДАНИЯ TRAILING STOP

#### 🔴 Место #4: Ошибка создания TS при новой позиции
**Файл:** `core/position_manager.py:1389-1395`
**Метод:** Обработка новых позиций (вероятно `_handle_new_position()`)

```python
try:
    await asyncio.wait_for(
        trailing_manager.create_trailing_stop(...),
        timeout=10.0
    )
    position.has_trailing_stop = True  # ✅ Только если успешно
except asyncio.TimeoutError:
    logger.error(f"❌ Timeout creating trailing stop for {symbol}")
    position.has_trailing_stop = False  # ❌ ПОЗИЦИЯ ОСТАЁТСЯ БЕЗ TS!
except Exception as e:
    logger.error(f"❌ Failed to create trailing stop for {symbol}: {e}")
    position.has_trailing_stop = False  # ❌ ПОЗИЦИЯ ОСТАЁТСЯ БЕЗ TS!
```

**Проблема:** При ошибке создания trailing stop (таймаут или exception), позиция продолжает работать БЕЗ trailing stop!

**Последствия:**
- Позиция без защиты trailing stop
- Возможны большие убытки
- Нарушен базовый принцип системы: "ВСЕ позиции должны иметь trailing stop"

**Правильное поведение:** При невозможности создать trailing stop - ЗАКРЫТЬ ПОЗИЦИЮ или повторить попытку!

---

### 3.4. FALLBACK TS MANAGER → PROTECTION MANAGER

#### 🔴 Место #5: Переход управления от TS к Protection Manager
**Файл:** `core/position_manager.py:2791-2800`

```python
if ts_inactive_minutes > 5:
    logger.warning(
        f"⚠️ {symbol} TS Manager inactive for {ts_inactive_minutes:.1f} minutes, "
        f"Protection Manager taking over"
    )

    # Reset TS flags to allow Protection Manager control
    position.has_trailing_stop = False  # ❌ СБРАСЫВАЕТСЯ В FALSE!
    position.trailing_activated = False
    position.sl_managed_by = 'protection'

    # Save to DB
    await self.repository.update_position(
        position.id,
        has_trailing_stop=False,  # ❌ СОХРАНЯЕТСЯ В БД КАК FALSE!
        trailing_activated=False
    )
```

**Проблема:** При переходе управления от TS Manager к Protection Manager, флаг `has_trailing_stop` устанавливается в False и сохраняется в БД.

**Почему это неправильно:**
- `has_trailing_stop` должен означать "позиция ДОЛЖНА иметь trailing stop", а не "кто управляет SL"
- После восстановления (рестарт) позиция не получит trailing stop обратно
- Нарушается базовый принцип: все позиции с trailing stop

**Правильное решение:** Использовать отдельный флаг `sl_managed_by` для управления, но НЕ сбрасывать `has_trailing_stop`.

---

### 3.5. SQL INSERT БЕЗ has_trailing_stop

#### 🔴 Место #6: database/repository.py
**Файл:** `database/repository.py:250-253`
**Метод:** `create_position()`

```python
query = """
    INSERT INTO monitoring.positions (
        symbol, exchange, side, quantity,
        entry_price, status
    ) VALUES ($1, $2, $3, $4, $5, 'active')
    RETURNING id
"""
```

**Проблема:** Не включает `has_trailing_stop` в INSERT, используется DEFAULT из models.py (False).

---

#### 🔴 Место #7: database/sqlite_repository.py
**Файл:** `database/sqlite_repository.py:58-61`
**Метод:** `create_position()`

```python
query = """
    INSERT INTO positions (
        signal_id, symbol, exchange, side, quantity,
        entry_price, stop_loss_price, status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
```

**Проблема:** Не включает `has_trailing_stop` в INSERT.

---

#### 🔴 Место #8: database/transactional_repository.py
**Файл:** `database/transactional_repository.py:150-154`
**Метод:** `create_position_atomic()`

```python
position_query = """
    INSERT INTO positions (
        signal_id, symbol, exchange, side, quantity,
        entry_price, stop_loss_price, stop_loss_order_id,
        has_stop_loss, status, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    RETURNING id
"""
```

**Проблема:** Не включает `has_trailing_stop` в INSERT (хотя включает `has_stop_loss`).

---

## 4. АНАЛИЗ ВОЗДЕЙСТВИЯ

### Сценарии создания позиций с has_trailing_stop=False:

#### Сценарий 1: Рестарт системы + позиции в БД с has_trailing_stop=False
1. Система перезапускается
2. `_load_positions()` загружает позиции из БД
3. Для позиций с `has_trailing_stop=False` в БД, trailing stop НЕ инициализируется
4. Позиции работают БЕЗ trailing stop

#### Сценарий 2: Синхронизация с биржей (восстановление из БД)
1. `sync_exchange_positions()` находит позицию на бирже
2. Позиция есть в БД, но не в памяти
3. Восстанавливает из БД с `has_trailing_stop=db_position.get('has_trailing_stop', False)`
4. Если в БД было False - остаётся False

#### Сценарий 3: Синхронизация с биржей (создание новой позиции)
1. `sync_exchange_positions()` находит позицию на бирже
2. Позиции НЕТ в БД
3. Создаёт новую позицию с `has_trailing_stop=False` (строка 815)
4. Trailing stop НЕ создаётся
5. Позиция работает БЕЗ trailing stop

#### Сценарий 4: Ошибка создания trailing stop
1. Создаётся новая позиция (сигнал)
2. Попытка создать trailing stop
3. Таймаут или ошибка
4. `has_trailing_stop` устанавливается в False
5. Позиция продолжает работать БЕЗ trailing stop

#### Сценарий 5: Fallback TS → Protection Manager
1. TS Manager перестаёт обновляться (> 5 минут)
2. Protection Manager берёт управление
3. `has_trailing_stop` сбрасывается в False и сохраняется в БД
4. После рестарта позиция не получит TS обратно

---

## 5. КРИТИЧНОСТЬ ПРОБЛЕМЫ

### 🔴 КРИТИЧНОСТЬ: МАКСИМАЛЬНАЯ (P0)

**Причины:**
1. **Безопасность торговли:** Позиции без trailing stop могут привести к большим убыткам
2. **Нарушение базового принципа:** Система спроектирована так, что ВСЕ позиции ДОЛЖНЫ иметь trailing stop
3. **Массовость проблемы:** 15 из 55 активных позиций (27%) затронуты
4. **Скрытый характер:** Позиции работают, но БЕЗ важной защиты
5. **Накопление проблемы:** С каждым рестартом и синхронизацией проблемных позиций может становиться больше

---

## 6. ПЛАН ИСПРАВЛЕНИЯ

### ЭТАП 1: СРОЧНОЕ ИСПРАВЛЕНИЕ СУЩЕСТВУЮЩИХ ПОЗИЦИЙ (Priority: P0)

#### Задача 1.1: SQL-скрипт для немедленного исправления БД
**Цель:** Установить `has_trailing_stop=TRUE` для всех активных позиций

```sql
-- РЕЗЕРВНАЯ КОПИЯ ПЕРЕД ИЗМЕНЕНИЯМИ
CREATE TABLE monitoring.positions_backup_20251024 AS
SELECT * FROM monitoring.positions WHERE status = 'active';

-- ИСПРАВЛЕНИЕ: Установить has_trailing_stop=TRUE для всех активных
UPDATE monitoring.positions
SET has_trailing_stop = TRUE
WHERE status = 'active' AND has_trailing_stop = FALSE;

-- ПРОВЕРКА
SELECT COUNT(*), has_trailing_stop
FROM monitoring.positions
WHERE status = 'active'
GROUP BY has_trailing_stop;
```

#### Задача 1.2: Рестарт position_manager для применения изменений
После обновления БД необходимо перезапустить систему, чтобы:
- Загрузить обновлённые значения `has_trailing_stop=TRUE`
- Инициализировать trailing stop для всех позиций

**ВАЖНО:** Проверить после рестарта, что все позиции имеют активные trailing stop менеджеры!

---

### ЭТАП 2: ИСПРАВЛЕНИЕ СХЕМЫ БД (Priority: P0)

#### Задача 2.1: Изменить DEFAULT значение в models.py
**Файл:** `database/models.py:127`

```python
# БЫЛО:
has_trailing_stop = Column(Boolean, default=False)

# ДОЛЖНО БЫТЬ:
has_trailing_stop = Column(Boolean, default=True, nullable=False)
```

#### Задача 2.2: Миграция БД для изменения DEFAULT
```sql
-- Изменить DEFAULT на уровне БД
ALTER TABLE monitoring.positions
ALTER COLUMN has_trailing_stop SET DEFAULT TRUE;

-- Установить NOT NULL constraint (опционально, для безопасности)
ALTER TABLE monitoring.positions
ALTER COLUMN has_trailing_stop SET NOT NULL;
```

---

### ЭТАП 3: ИСПРАВЛЕНИЕ REPOSITORY МЕТОДОВ (Priority: P0)

#### Задача 3.1: database/repository.py - create_position()
**Файл:** `database/repository.py:250`

```python
# БЫЛО:
query = """
    INSERT INTO monitoring.positions (
        symbol, exchange, side, quantity,
        entry_price, status
    ) VALUES ($1, $2, $3, $4, $5, 'active')
    RETURNING id
"""

# ДОЛЖНО БЫТЬ:
query = """
    INSERT INTO monitoring.positions (
        symbol, exchange, side, quantity,
        entry_price, status, has_trailing_stop
    ) VALUES ($1, $2, $3, $4, $5, 'active', TRUE)
    RETURNING id
"""
```

#### Задача 3.2: database/sqlite_repository.py - create_position()
**Файл:** `database/sqlite_repository.py:58`

Добавить `has_trailing_stop` в INSERT с значением TRUE.

#### Задача 3.3: database/transactional_repository.py - create_position_atomic()
**Файл:** `database/transactional_repository.py:150`

Добавить `has_trailing_stop` в INSERT с значением TRUE.

---

### ЭТАП 4: ИСПРАВЛЕНИЕ position_manager.py (Priority: P0)

#### Задача 4.1: Исправить sync_exchange_positions() - восстановление из БД
**Файл:** `core/position_manager.py:773`

```python
# БЫЛО:
has_trailing_stop=db_position.get('has_trailing_stop', False),

# ДОЛЖНО БЫТЬ:
has_trailing_stop=db_position.get('has_trailing_stop', True),  # Default TRUE!

# ИЛИ ЕЩЁ ЛУЧШЕ - всегда TRUE:
has_trailing_stop=True,  # Все позиции ДОЛЖНЫ иметь TS
```

#### Задача 4.2: Исправить sync_exchange_positions() - создание новой позиции
**Файл:** `core/position_manager.py:815`

```python
# БЫЛО:
position_state = PositionState(
    ...
    has_trailing_stop=False,
    ...
)

# ДОЛЖНО БЫТЬ:
position_state = PositionState(
    ...
    has_trailing_stop=True,  # Все позиции ДОЛЖНЫ иметь TS
    ...
)
```

#### КРИТИЧЕСКОЕ ДОПОЛНЕНИЕ: Инициализировать TS для новых позиций!
После строки 822 (`self.positions[symbol] = position_state`) добавить:

```python
# ВАЖНО: Инициализировать trailing stop для новой позиции
trailing_manager = self.trailing_managers.get(exchange_name)
if trailing_manager:
    try:
        await trailing_manager.create_trailing_stop(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            initial_stop=stop_loss_price  # Использовать Protection SL как initial
        )
        position_state.has_trailing_stop = True
        await self.repository.update_position(
            position_id,
            has_trailing_stop=True
        )
        logger.info(f"✅ Trailing stop initialized for synced position {symbol}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize TS for synced {symbol}: {e}")
        # ВОПРОС: Закрыть позицию или оставить с Protection SL?
```

#### Задача 4.3: Исправить _load_positions()
**Файл:** `core/position_manager.py:425`

```python
# БЫЛО:
has_trailing_stop=pos['trailing_activated'] or False,

# ДОЛЖНО БЫТЬ:
has_trailing_stop=pos.get('has_trailing_stop', True),  # Читать из БД, default TRUE
```

#### Задача 4.4: Исправить обработку ошибок создания TS
**Файл:** `core/position_manager.py:1389-1395`

**Вариант 1: Повторные попытки (Retry)**
```python
try:
    await asyncio.wait_for(
        trailing_manager.create_trailing_stop(...),
        timeout=10.0
    )
    position.has_trailing_stop = True
except (asyncio.TimeoutError, Exception) as e:
    logger.error(f"❌ Failed to create trailing stop for {symbol}: {e}")

    # RETRY: Попробовать ещё раз через 5 секунд
    await asyncio.sleep(5)
    try:
        await trailing_manager.create_trailing_stop(...)
        position.has_trailing_stop = True
        logger.info(f"✅ Trailing stop created on retry for {symbol}")
    except Exception as retry_error:
        logger.error(f"❌ TS creation retry failed for {symbol}: {retry_error}")
        # КРИТИЧНО: Позиция БЕЗ TS - требуется решение!
        # Вариант A: Закрыть позицию
        # Вариант B: Установить флаг для ручного вмешательства
        # Вариант C: Продолжить с Protection SL, но отметить в логах
        position.has_trailing_stop = False  # Временно, требует внимания
```

**Вариант 2: Отложенная инициализация (Lazy Init)**
```python
except (asyncio.TimeoutError, Exception) as e:
    logger.error(f"❌ Failed to create trailing stop for {symbol}: {e}")

    # Отметить позицию для повторной попытки
    position.has_trailing_stop = False
    position.ts_init_failed = True
    position.ts_retry_count = 0

    # В следующем цикле мониторинга будет повторная попытка
```

#### Задача 4.5: Пересмотреть логику Fallback TS → Protection
**Файл:** `core/position_manager.py:2791-2800`

```python
# БЫЛО:
position.has_trailing_stop = False
await self.repository.update_position(
    position.id,
    has_trailing_stop=False,
    trailing_activated=False
)

# ДОЛЖНО БЫТЬ:
# НЕ сбрасывать has_trailing_stop - это постоянный признак!
# Использовать только sl_managed_by для управления
position.sl_managed_by = 'protection'  # Кто управляет SL сейчас
# has_trailing_stop остаётся TRUE - TS должен быть всегда!

await self.repository.update_position(
    position.id,
    # has_trailing_stop НЕ изменяем - остаётся TRUE!
    # trailing_activated можно сбросить временно
    trailing_activated=False,
    # Можно добавить поле sl_managed_by в БД
)

# Важно: Попытаться восстановить TS в следующем цикле мониторинга!
```

---

### ЭТАП 5: УЛУЧШЕНИЯ АРХИТЕКТУРЫ (Priority: P1 - после критических исправлений)

#### Задача 5.1: Добавить валидацию при создании позиций
```python
async def create_position(...):
    # ВАЛИДАЦИЯ: Проверить, что has_trailing_stop установлен
    if position_data.get('has_trailing_stop') is not True:
        logger.warning(
            f"⚠️ Attempt to create position without has_trailing_stop=True! "
            f"Forcing to True. Symbol: {position_data['symbol']}"
        )
        position_data['has_trailing_stop'] = True

    # Продолжить создание...
```

#### Задача 5.2: Добавить проверку консистентности при загрузке
```python
async def _load_positions(self):
    # После загрузки позиций
    for symbol, pos_state in self.positions.items():
        if not pos_state.has_trailing_stop:
            logger.error(
                f"❌ CRITICAL: Position {symbol} loaded with has_trailing_stop=False! "
                f"This should NEVER happen. Fixing..."
            )
            pos_state.has_trailing_stop = True

            # Обновить БД
            await self.repository.update_position(
                pos_state.id,
                has_trailing_stop=True
            )
```

#### Задача 5.3: Добавить мониторинг и алерты
```python
async def check_trailing_stop_health(self):
    """Проверка, что все активные позиции имеют trailing stop"""
    positions_without_ts = []

    for symbol, pos_state in self.positions.items():
        if not pos_state.has_trailing_stop:
            positions_without_ts.append(symbol)
            logger.error(
                f"🚨 ALERT: Position {symbol} does NOT have trailing stop! "
                f"This violates system constraints!"
            )

    if positions_without_ts:
        # Отправить алерт администратору
        await send_critical_alert(
            f"Found {len(positions_without_ts)} positions without trailing stop: "
            f"{positions_without_ts}"
        )

    return positions_without_ts
```

#### Задача 5.4: Разделить понятия has_trailing_stop и sl_managed_by
```python
# has_trailing_stop = Boolean - позиция ДОЛЖНА иметь TS (всегда True для всех позиций)
# sl_managed_by = Enum ['trailing', 'protection'] - КТО управляет SL в данный момент
# trailing_activated = Boolean - активирован ли TS (в прибыли)

# Пример:
position.has_trailing_stop = True  # ВСЕГДА True для всех позиций
position.sl_managed_by = 'trailing'  # или 'protection'
position.trailing_activated = True/False  # зависит от PnL
```

---

### ЭТАП 6: ТЕСТИРОВАНИЕ (Priority: P0)

#### Задача 6.1: Написать тесты для всех сценариев создания позиций
```python
async def test_create_position_always_has_trailing_stop():
    """Проверка, что create_position всегда создаёт has_trailing_stop=True"""
    position_id = await repository.create_position({
        'symbol': 'TESTUSDT',
        'exchange': 'bybit',
        'side': 'long',
        'quantity': 1.0,
        'entry_price': 100.0
    })

    position = await repository.get_position_by_id(position_id)
    assert position['has_trailing_stop'] is True, "has_trailing_stop MUST be True!"
```

#### Задача 6.2: Тест синхронизации позиций с биржи
```python
async def test_sync_exchange_positions_sets_trailing_stop():
    """Проверка, что синхронизированные позиции получают has_trailing_stop=True"""
    # Mock позиция на бирже
    # Запустить sync_exchange_positions()
    # Проверить, что has_trailing_stop=True
    # Проверить, что TS инициализирован
```

#### Задача 6.3: Тест обработки ошибок TS
```python
async def test_ts_creation_error_handling():
    """Проверка, что при ошибке создания TS применяется fallback логика"""
    # Mock ошибку создания TS
    # Проверить retry или закрытие позиции
    # Убедиться, что позиция не остаётся в подвешенном состоянии
```

---

## 7. ПРИОРИТИЗАЦИЯ ИСПРАВЛЕНИЙ

### 🔴 КРИТИЧЕСКИЕ (Выполнить НЕМЕДЛЕННО, сегодня):
1. ✅ **ЭТАП 1:** SQL-скрипт для исправления существующих 15 позиций
2. ✅ **Задача 2.1:** Изменить DEFAULT в models.py
3. ✅ **Задача 4.1:** Исправить sync_exchange_positions (восстановление)
4. ✅ **Задача 4.2:** Исправить sync_exchange_positions (создание) + инициализация TS
5. ✅ **Задача 4.3:** Исправить _load_positions

### 🟡 ВЫСОКИЙ ПРИОРИТЕТ (Выполнить в течение 2-3 дней):
6. **Задача 3.1-3.3:** Исправить все repository методы create_position
7. **Задача 2.2:** Миграция БД для ALTER TABLE DEFAULT
8. **Задача 4.4:** Исправить обработку ошибок создания TS (retry logic)
9. **Задача 5.1:** Добавить валидацию при создании позиций
10. **Задача 6.1-6.3:** Написать критические тесты

### 🟢 СРЕДНИЙ ПРИОРИТЕТ (Выполнить в течение недели):
11. **Задача 4.5:** Пересмотреть логику Fallback TS → Protection
12. **Задача 5.2:** Проверка консистентности при загрузке
13. **Задача 5.3:** Мониторинг и алерты
14. **Задача 5.4:** Архитектурное разделение has_trailing_stop и sl_managed_by

---

## 8. РИСКИ И ПРЕДОСТОРОЖНОСТИ

### Риск 1: Изменение схемы БД может сломать совместимость
**Митигация:**
- Сначала изменить код (работать с обоими вариантами)
- Затем миграция БД
- Проверить на staging окружении

### Риск 2: Массовая инициализация TS после исправления может создать нагрузку
**Митигация:**
- Мониторить нагрузку при рестарте
- Добавить rate limiting для создания TS
- Запускать рестарт в период низкой активности

### Риск 3: Позиции в переходном состоянии
**Митигация:**
- Не изменять код во время активных торгов
- Запланировать окно обслуживания
- Подготовить rollback план

---

## 9. КОНТРОЛЬНЫЙ СПИСОК ИСПРАВЛЕНИЙ

### До начала работы:
- [ ] Создать резервную копию БД
- [ ] Создать feature branch для исправлений
- [ ] Запланировать окно обслуживания

### Критические исправления:
- [ ] SQL: Установить has_trailing_stop=TRUE для существующих позиций
- [ ] models.py: Изменить default=True
- [ ] position_manager.py:773: Исправить sync восстановление
- [ ] position_manager.py:815: Исправить sync создание + добавить TS init
- [ ] position_manager.py:425: Исправить _load_positions
- [ ] Тестирование на staging
- [ ] Рестарт системы и проверка

### Дополнительные исправления:
- [ ] repository.py: Добавить has_trailing_stop в INSERT
- [ ] sqlite_repository.py: Добавить has_trailing_stop в INSERT
- [ ] transactional_repository.py: Добавить has_trailing_stop в INSERT
- [ ] position_manager.py:1389-1395: Добавить retry для TS errors
- [ ] position_manager.py:2791: Пересмотреть fallback логику
- [ ] Написать тесты
- [ ] Добавить валидацию и мониторинг

### После исправлений:
- [ ] Проверить все активные позиции: has_trailing_stop=TRUE
- [ ] Проверить логи: нет ошибок создания TS
- [ ] Мониторинг 24 часа: убедиться что проблема не возвращается
- [ ] Документировать изменения
- [ ] Code review и merge в main

---

## 10. ВЫВОДЫ

### Подтверждение предположения пользователя:
✅ **ПОЛНОСТЬЮ ПОДТВЕРЖДЕНО!** Модуль восстановления/синхронизации позиций с биржи (`sync_exchange_positions()`) является ОСНОВНЫМ источником проблемы.

### Дополнительные источники проблемы:
- Неправильный DEFAULT в схеме БД
- Некорректная логика в `_load_positions()`
- Отсутствие обработки ошибок создания TS
- Сброс флага при fallback TS → Protection

### Масштаб проблемы:
- **15 из 55 позиций (27%)** затронуты
- Все проблемные позиции - результат синхронизации с Bybit
- Проблема накапливается при каждом рестарте/синхронизации

### Критичность:
- **P0 - МАКСИМАЛЬНАЯ:** Позиции без trailing stop = риск больших убытков
- Требует НЕМЕДЛЕННОГО исправления
- Необходим комплексный подход: БД + код + тестирование

---

## 11. СЛЕДУЮЩИЕ ШАГИ

1. **СЕЙЧАС:** Получить одобрение плана исправления от пользователя
2. **СЕГОДНЯ:** Выполнить критические исправления (ЭТАП 1 + топ-5 задач)
3. **2-3 ДНЯ:** Завершить все исправления высокого приоритета
4. **НЕДЕЛЯ:** Закончить среднеприоритетные улучшения и тестирование
5. **ПОСТОЯННО:** Мониторинг и предотвращение повторения проблемы

---

**ДАТА СОЗДАНИЯ ОТЧЁТА:** 2025-10-24
**АВТОР:** Claude Code Audit System
**СТАТУС:** Ожидание одобрения плана исправления
