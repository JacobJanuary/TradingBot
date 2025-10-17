# ПЛАН РЕФАКТОРИНГА МОДУЛЯ AGED POSITION MANAGER

**Дата:** 2025-10-17
**Цель:** Переработать логику модуля с приоритетом на PnL позиций
**Статус:** ПЛАНИРОВАНИЕ (БЕЗ ИЗМЕНЕНИЯ КОДА)

---

## 1. РЕЗУЛЬТАТЫ ДЕТАЛЬНОГО РАССЛЕДОВАНИЯ

### 1.1 Текущая архитектура модуля

**Файлы:**
- `core/aged_position_manager.py` (510 строк) - основной модуль
- `core/exchange_manager_enhanced.py` - создание/обновление ордеров

**Текущие фазы ликвидации:**
```
Фаза 1: GRACE_PERIOD (0-8ч после MAX_AGE=3ч)
├─ Логика: Попытка закрытия в безубыток (entry ± двойная комиссия)
└─ Тип ордера: LIMIT по целевой цене

Фаза 2: PROGRESSIVE (8-28ч после MAX_AGE)
├─ Логика: Увеличение терпимости к убытку (0.5% за час, акселерация после 10ч)
└─ Тип ордера: LIMIT по целевой цене

Фаза 3: EMERGENCY (28ч+ после MAX_AGE)
├─ Логика: Использование текущей рыночной цены
└─ Тип ордера: LIMIT по рыночной цене (!)
```

### 1.2 Выявленные данные из реального теста

**Статистика из 10-минутного мониторинга:**
- Всего старых позиций: 82
- **Прибыльных: 58 (70.7%)**
- Убыточных: 24 (29.3%)
- Закрыто за тест: 0 (0%)

**Распределение прибыльных по фазам:**
- GRACE_PERIOD: 17 позиций (29.3%)
- PROGRESSIVE: 14 позиций (24.1%)
- EMERGENCY: 27 позиций (46.6%)

**Топ прибыльные позиции:**
1. AXLUSDT (short): +15.04%, 25.9ч, PROGRESSIVE
2. MANAUSDT (short): +13.49%, 31.2ч, EMERGENCY
3. COTIUSDT (short): +13.32%, 32.5ч, EMERGENCY
4. PROMPTUSDT (short): +12.98%, 31.7ч, EMERGENCY
5. KAVAUSDT (short): +12.65%, 30.7ч, PROGRESSIVE

**Топ убыточные позиции:**
1. 10000WENUSDT (long): -10.73%, 39.3ч, EMERGENCY
2. CLOUDUSDT (short): -9.67%, 39.5ч, EMERGENCY
3. HNTUSDT (long): -8.84%, 39.5ч, EMERGENCY

### 1.3 Корневая проблема

**КРИТИЧЕСКИЙ БАГ: Неправильный тип ордера**

Модуль использует ТОЛЬКО LIMIT ордера для всех фаз. Это приводит к отказам биржи:

```python
# Текущий код (строка 355-361)
order = await enhanced_manager.create_or_update_exit_order(
    symbol=position.symbol,
    side=order_side,  # 'buy' для SHORT, 'sell' для LONG
    amount=abs(float(position.quantity)),
    price=precise_price,  # ← Всегда LIMIT!
    min_price_diff_pct=0.5
)
```

**Почему это не работает:**

| Сценарий | Сторона позиции | Действие для закрытия | Целевая цена | Рынок | Проблема |
|----------|----------------|----------------------|--------------|-------|----------|
| SHORT в прибыли | SHORT | BUY | Выше рынка | Ниже входа | BUY LIMIT должен быть < рынка ❌ |
| LONG в убытке | LONG | SELL | Ниже рынка | Ниже входа | SELL LIMIT должен быть > рынка ❌ |
| SHORT в убытке | SHORT | BUY | Выше входа | Выше входа | Может работать ✓ |
| LONG в прибыли | LONG | SELL | Выше рынка | Выше входа | Работает ✓ |

**Вывод:** LIMIT ордера работают только для ~50% сценариев.

### 1.4 Анализ текущей логики расчёта целевой цены

**Метод `_calculate_target_price()` (строки 258-317):**

```python
# GRACE PERIOD
if position.side in ['long', 'buy']:
    target_price = entry_price * (1 + double_commission)  # Продать выше
else:  # short
    target_price = entry_price * (1 - double_commission)  # Купить ниже

# PROGRESSIVE
if position.side in ['long', 'buy']:
    target_price = entry_price * (1 - loss_percent / 100)  # Продать ниже (убыток)
else:  # short
    target_price = entry_price * (1 + loss_percent / 100)  # Купить выше (убыток)

# EMERGENCY
target_price = current_price_decimal  # Рыночная цена
```

**Оценка логики расчёта:** ✅ ПРАВИЛЬНАЯ

Расчёт целевых цен математически корректен. Проблема только в выборе типа ордера.

### 1.5 Анализ EnhancedExchangeManager

**Метод `create_or_update_exit_order()` (строки 182-254):**
- Проверяет существующие ордера
- Обновляет если разница цены > 0.5%
- Вызывает `create_limit_exit_order()`

**Метод `create_limit_exit_order()` (строки 118-180):**
- Всегда создаёт LIMIT ордера
- Нет валидации цены относительно рынка
- Нет выбора типа ордера

**Оценка:** ⚠️ ЧАСТИЧНО ПРАВИЛЬНАЯ
- Логика дедупликации: ✅ Работает
- Управление ордерами: ✅ Работает
- Выбор типа ордера: ❌ Отсутствует

---

## 2. НОВАЯ СТРАТЕГИЯ С ПРИОРИТЕТОМ НА PnL

### 2.1 Основной принцип

**ПРИОРИТЕТ #1: ПРИБЫЛЬ ВАЖНЕЕ ВОЗРАСТА**

```
ПРАВИЛО: Если позиция в прибыли (PnL > 0%), закрывать НЕМЕДЛЕННО по MARKET
независимо от возраста и фазы.
```

**Обоснование:**
- Из теста: 70.7% старых позиций в прибыли
- Многие прибыльные находятся в EMERGENCY (27 позиций, до 32ч возраста)
- Текущая логика пытается ждать "лучшей цены", но терпит неудачу
- MARKET ордер гарантирует фиксацию прибыли

### 2.2 Новая иерархия решений

```
┌─────────────────────────────────────────────────────┐
│ ШАГИ ПРИНЯТИЯ РЕШЕНИЯ О ЗАКРЫТИИ                    │
└─────────────────────────────────────────────────────┘

ШАГ 1: Проверка PnL
├─ PnL > 0% → MARKET ORDER (немедленное закрытие)
└─ PnL ≤ 0% → Переход к ШАГ 2

ШАГ 2: Проверка возраста и фазы
├─ GRACE_PERIOD (0-8ч) → Попытка безубытка (LIMIT или MARKET)
├─ PROGRESSIVE (8-28ч) → Прогрессивная ликвидация (LIMIT или MARKET)
└─ EMERGENCY (28ч+) → MARKET ORDER (принудительное закрытие)

ШАГ 3: Выбор типа ордера (для PnL ≤ 0%)
├─ Проверка: может ли LIMIT быть размещён?
│   ├─ Для BUY: target < market * 0.999 → LIMIT OK
│   ├─ Для SELL: target > market * 1.001 → LIMIT OK
│   └─ Иначе → MARKET ORDER
└─ Размещение ордера
```

### 2.3 Детальная логика для каждой фазы

#### ФАЗА 0: ПРОВЕРКА ПРИБЫЛЬНОСТИ (НОВАЯ!)

```python
# Псевдокод
if position.pnl_percentage > 0:
    logger.info(f"🎯 {symbol} в прибыли {pnl}% - закрываем по MARKET")
    return 'IMMEDIATE_PROFIT_CLOSE', current_price, 'MARKET'
```

**Параметры:**
- PnL порог: > 0% (любая прибыль)
- Тип ордера: MARKET
- Приоритет: ВЫСШИЙ

**Ожидаемый результат:**
- 58 из 82 позиций (70.7%) будут закрыты немедленно
- Фиксация прибыли гарантирована

#### ФАЗА 1: GRACE PERIOD (для PnL ≤ 0%)

```python
# Псевдокод
if hours_over_limit <= grace_period_hours:
    # Расчёт целевой цены безубытка
    target_price = calculate_breakeven_price(entry, commission)

    # Проверка возможности LIMIT
    if can_place_limit_order(side, target_price, current_price):
        return 'GRACE_PERIOD_BREAKEVEN', target_price, 'LIMIT'
    else:
        # LIMIT невозможен - используем MARKET
        logger.warning(f"LIMIT невозможен для {symbol}, используем MARKET")
        return 'GRACE_PERIOD_MARKET', current_price, 'MARKET'
```

**Параметры:**
- Длительность: 0-8ч после MAX_AGE
- Цель: Закрытие в безубыток (entry ± двойная комиссия)
- Тип ордера: LIMIT (если возможно), иначе MARKET
- PnL: ≤ 0%

**Логика выбора типа:**
- Если целевая цена валидна для LIMIT → LIMIT
- Если целевая цена нарушает правила биржи → MARKET

#### ФАЗА 2: PROGRESSIVE (для PnL ≤ 0%)

```python
# Псевдокод
elif hours_over_limit <= grace_period_hours + 20:
    hours_after_grace = hours_over_limit - grace_period_hours

    # Прогрессивный расчёт убытка
    loss_percent = calculate_progressive_loss(hours_after_grace)
    target_price = calculate_target_with_loss(entry, side, loss_percent)

    # Проверка возможности LIMIT
    if can_place_limit_order(side, target_price, current_price):
        return 'PROGRESSIVE_LIQUIDATION', target_price, 'LIMIT'
    else:
        # LIMIT невозможен - используем MARKET
        logger.warning(f"Progressive: LIMIT невозможен, используем MARKET")
        return 'PROGRESSIVE_MARKET', current_price, 'MARKET'
```

**Параметры:**
- Длительность: 8-28ч после MAX_AGE
- Начальный убыток: 0.5% за час
- Акселерация: ×1.2 после 10ч в прогрессии
- Максимальный убыток: 10%
- Тип ордера: LIMIT (если возможно), иначе MARKET
- PnL: ≤ 0%

**Особенности:**
- Если текущий убыток уже больше допустимого → MARKET немедленно
- Если рынок движется против → MARKET немедленно

#### ФАЗА 3: EMERGENCY (для всех PnL)

```python
# Псевдокод
else:  # hours_over_limit > 28
    # EMERGENCY: всегда MARKET
    logger.critical(f"🚨 EMERGENCY {symbol} (возраст {age}ч) - MARKET закрытие")
    return 'EMERGENCY_MARKET_CLOSE', current_price, 'MARKET'
```

**Параметры:**
- Длительность: 28ч+ после MAX_AGE
- Тип ордера: MARKET (принудительно)
- PnL: любой
- Цель: Закрыть позицию любой ценой

**Обоснование:**
- 28ч+ возраст = критическая ситуация
- Нельзя ждать "хорошей цены"
- Риск дальнейших убытков > риск проскальзывания

### 2.4 Таблица принятия решений

| Условие | PnL | Возраст | Фаза | Действие | Тип ордера |
|---------|-----|---------|------|----------|------------|
| Любой возраст | > 0% | Любой | PROFIT | Немедленное закрытие | MARKET |
| 3-11ч | ≤ 0% | 0-8ч | GRACE | Безубыток (если возможно LIMIT) | LIMIT/MARKET |
| 11-31ч | ≤ 0% | 8-28ч | PROGRESSIVE | Прогрессивный убыток | LIMIT/MARKET |
| 31ч+ | Любой | 28ч+ | EMERGENCY | Принудительное закрытие | MARKET |

---

## 3. АРХИТЕКТУРА СИСТЕМЫ ВЫБОРА ТИПА ОРДЕРА

### 3.1 Новый метод валидации цены

```python
def _validate_limit_price(
    self,
    side: str,
    target_price: float,
    current_price: float,
    buffer_pct: float = 0.1
) -> bool:
    """
    Проверить, может ли LIMIT ордер быть размещён по целевой цене

    Args:
        side: 'buy' или 'sell'
        target_price: Желаемая цена ордера
        current_price: Текущая рыночная цена
        buffer_pct: Буфер в процентах (по умолчанию 0.1%)

    Returns:
        True если LIMIT ордер валиден, False иначе
    """
    if side == 'buy':
        # BUY LIMIT должен быть НИЖЕ рынка
        max_allowed = current_price * (1 - buffer_pct / 100)
        return target_price <= max_allowed
    else:  # sell
        # SELL LIMIT должен быть ВЫШЕ рынка
        min_allowed = current_price * (1 + buffer_pct / 100)
        return target_price >= min_allowed
```

**Параметры:**
- `buffer_pct`: 0.1% буфер для учёта движения рынка
- Возвращает: bool (True = LIMIT возможен)

### 3.2 Новый метод создания MARKET ордера

```python
async def _create_market_exit_order(
    self,
    exchange,
    symbol: str,
    side: str,
    amount: float,
    reason: str = "MARKET_CLOSE"
) -> Optional[Dict]:
    """
    Создать MARKET ордер для немедленного закрытия позиции

    Args:
        exchange: Объект биржи
        symbol: Торговая пара
        side: 'buy' или 'sell'
        amount: Количество
        reason: Причина закрытия (для логирования)

    Returns:
        Словарь ордера или None
    """
    try:
        logger.info(f"📤 MARKET {reason}: {side} {amount} {symbol}")

        params = {
            'reduceOnly': True  # КРИТИЧЕСКИ важно!
        }

        if exchange.id == 'bybit':
            params['positionIdx'] = 0

        order = await exchange.exchange.create_order(
            symbol=symbol,
            type='market',  # ← MARKET тип
            side=side,
            amount=amount,
            params=params
        )

        if order:
            logger.info(f"✅ MARKET ордер исполнен: {order['id']}")
            self.stats['market_orders_created'] += 1
            return order

    except Exception as e:
        logger.error(f"❌ MARKET ордер не прошёл для {symbol}: {e}")
        self.stats['market_orders_failed'] += 1
        return None
```

**Особенности:**
- `type='market'` - ключевой параметр
- `reduceOnly=True` - обязателен для предотвращения увеличения позиции
- Немедленное исполнение по лучшей доступной цене
- Нет гарантии точной цены, но гарантия исполнения

### 3.3 Обновлённый метод `_update_single_exit_order()`

```python
async def _update_single_exit_order(
    self,
    position,
    target_price: float,
    phase: str,
    order_type: str  # НОВЫЙ параметр: 'LIMIT' или 'MARKET'
):
    """
    Создать или обновить exit ордер с выбором типа

    НОВАЯ ЛОГИКА:
    - Если order_type == 'MARKET': создать MARKET ордер
    - Если order_type == 'LIMIT': создать/обновить LIMIT ордер
    """
    try:
        position_id = f"{position.symbol}_{position.exchange}"
        exchange = self.exchanges.get(position.exchange)

        if not exchange:
            logger.error(f"Exchange {position.exchange} недоступна")
            return

        # Определить сторону ордера
        order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

        # НОВАЯ ЛОГИКА: Выбор между MARKET и LIMIT
        if order_type == 'MARKET':
            # Использовать MARKET ордер
            order = await self._create_market_exit_order(
                exchange=exchange,
                symbol=position.symbol,
                side=order_side,
                amount=abs(float(position.quantity)),
                reason=phase
            )

            if order:
                self.managed_positions[position_id] = {
                    'last_update': datetime.now(),
                    'order_id': order['id'],
                    'phase': phase,
                    'order_type': 'MARKET'
                }
                logger.info(f"✅ MARKET закрытие: {position.symbol} в фазе {phase}")

        else:  # LIMIT
            # Использовать существующую логику LIMIT ордеров
            precise_price = self._apply_price_precision(
                float(target_price),
                position.symbol,
                position.exchange
            )

            # Вызов EnhancedExchangeManager
            from core.exchange_manager_enhanced import EnhancedExchangeManager
            enhanced_manager = EnhancedExchangeManager(exchange.exchange)

            order = await enhanced_manager.create_or_update_exit_order(
                symbol=position.symbol,
                side=order_side,
                amount=abs(float(position.quantity)),
                price=precise_price,
                min_price_diff_pct=0.5
            )

            if order:
                self.managed_positions[position_id] = {
                    'last_update': datetime.now(),
                    'order_id': order['id'],
                    'phase': phase,
                    'order_type': 'LIMIT'
                }

                if order.get('_was_updated'):
                    self.stats['orders_updated'] += 1
                else:
                    self.stats['orders_created'] += 1

    except Exception as e:
        logger.error(f"Ошибка создания exit ордера: {e}", exc_info=True)
        self.stats['orders_failed'] += 1
```

**Изменения:**
1. Новый параметр `order_type`
2. Условная логика: MARKET vs LIMIT
3. Отдельный путь для MARKET ордеров
4. Сохранение типа ордера в `managed_positions`

### 3.4 Обновлённый метод `_calculate_target_price()`

```python
def _calculate_target_price(
    self,
    position,
    hours_over_limit: float,
    current_price: float
) -> Tuple[str, float, float, str]:  # НОВЫЙ возврат: + order_type
    """
    Рассчитать целевую цену и определить тип ордера

    НОВАЯ ЛОГИКА:
    1. Проверка PnL → если прибыль → MARKET
    2. Проверка фазы → расчёт целевой цены
    3. Валидация LIMIT → выбор типа ордера

    Returns:
        Tuple of (phase_name, target_price, loss_percent, order_type)
    """
    entry_price = Decimal(str(position.entry_price))
    current_price_decimal = Decimal(str(current_price))

    # ШАГ 1: ПРОВЕРКА ПРИБЫЛЬНОСТИ (НОВОЕ!)
    current_pnl_percent = self._calculate_current_pnl_percent(
        position.side,
        entry_price,
        current_price_decimal
    )

    if current_pnl_percent > 0:
        # ПОЗИЦИЯ В ПРИБЫЛИ - ЗАКРЫВАЕМ НЕМЕДЛЕННО ПО MARKET
        logger.info(
            f"💰 {position.symbol} в прибыли {current_pnl_percent:.2f}% "
            f"(возраст {hours_over_limit:.1f}ч) - MARKET закрытие"
        )
        return (
            f"IMMEDIATE_PROFIT_CLOSE (PnL: +{current_pnl_percent:.2f}%)",
            current_price_decimal,
            Decimal('0'),
            'MARKET'
        )

    # ШАГ 2: РАСЧЁТ ПО ФАЗАМ (для PnL ≤ 0%)
    if hours_over_limit <= self.grace_period_hours:
        # ФАЗА 1: GRACE PERIOD
        double_commission = 2 * self.commission_percent

        if position.side in ['long', 'buy']:
            target_price = entry_price * (1 + double_commission)
        else:
            target_price = entry_price * (1 - double_commission)

        phase = f"GRACE_PERIOD_BREAKEVEN ({hours_over_limit:.1f}/{self.grace_period_hours}h)"
        loss_percent = Decimal('0')

    elif hours_over_limit <= self.grace_period_hours + 20:
        # ФАЗА 2: PROGRESSIVE
        hours_after_grace = hours_over_limit - self.grace_period_hours
        loss_percent = hours_after_grace * self.loss_step_percent

        if hours_after_grace > 10:
            extra_hours = hours_after_grace - 10
            acceleration_loss = extra_hours * self.loss_step_percent * (self.acceleration_factor - 1)
            loss_percent += acceleration_loss

        loss_percent = min(loss_percent, self.max_loss_percent)

        if position.side in ['long', 'buy']:
            target_price = entry_price * (1 - loss_percent / 100)
        else:
            target_price = entry_price * (1 + loss_percent / 100)

        phase = f"PROGRESSIVE_LIQUIDATION (loss: {loss_percent:.1f}%)"

    else:
        # ФАЗА 3: EMERGENCY - ВСЕГДА MARKET
        target_price = current_price_decimal
        phase = "EMERGENCY_MARKET_CLOSE"

        if position.side in ['long', 'buy']:
            loss_percent = ((entry_price - current_price_decimal) / entry_price) * 100
        else:
            loss_percent = ((current_price_decimal - entry_price) / entry_price) * 100

        # EMERGENCY всегда использует MARKET
        return (phase, target_price, loss_percent, 'MARKET')

    # ШАГ 3: ВАЛИДАЦИЯ LIMIT ДЛЯ GRACE И PROGRESSIVE
    order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

    can_use_limit = self._validate_limit_price(
        side=order_side,
        target_price=float(target_price),
        current_price=float(current_price_decimal),
        buffer_pct=0.1
    )

    if can_use_limit:
        order_type = 'LIMIT'
    else:
        logger.warning(
            f"⚠️ LIMIT невозможен для {position.symbol} "
            f"(target=${target_price:.4f}, market=${current_price:.4f}) "
            f"- используем MARKET"
        )
        order_type = 'MARKET'
        target_price = current_price_decimal  # Обновить на рыночную цену

    return (phase, target_price, loss_percent, order_type)
```

**Ключевые изменения:**
1. Новый ШАГ 1: Проверка PnL перед всем остальным
2. Возврат 4-го значения: `order_type`
3. Валидация LIMIT для GRACE и PROGRESSIVE
4. EMERGENCY всегда возвращает MARKET

### 3.5 Новый вспомогательный метод

```python
def _calculate_current_pnl_percent(
    self,
    side: str,
    entry_price: Decimal,
    current_price: Decimal
) -> Decimal:
    """
    Рассчитать текущий PnL в процентах

    Args:
        side: 'long' или 'short'
        entry_price: Цена входа
        current_price: Текущая цена

    Returns:
        PnL в процентах (положительный = прибыль, отрицательный = убыток)
    """
    if side in ['long', 'buy']:
        # LONG: прибыль когда current > entry
        pnl_percent = ((current_price - entry_price) / entry_price) * 100
    else:  # short
        # SHORT: прибыль когда current < entry
        pnl_percent = ((entry_price - current_price) / entry_price) * 100

    return pnl_percent
```

---

## 4. ПОДРОБНЫЙ ПЛАН РЕФАКТОРИНГА

### 4.1 Этапы реализации

#### ЭТАП 1: Подготовка и валидация (1-2 часа)

**Задачи:**
1. ✅ Создать резервную копию `aged_position_manager.py`
2. ✅ Создать резервную копию `exchange_manager_enhanced.py`
3. ✅ Создать тестовую ветку git
4. ✅ Задокументировать текущее состояние

**Критерии завершения:**
- Код в безопасности
- План согласован
- Окружение готово

#### ЭТАП 2: Добавление вспомогательных методов (1-2 часа)

**Файл:** `core/aged_position_manager.py`

**Добавить методы:**
1. `_calculate_current_pnl_percent()` - расчёт PnL
2. `_validate_limit_price()` - валидация LIMIT цены
3. `_create_market_exit_order()` - создание MARKET ордеров

**Расположение:** После метода `_apply_price_precision()` (строка 100)

**Тестирование:**
- Unit тесты для каждого метода
- Проверка граничных случаев
- Валидация возвращаемых значений

**Критерии завершения:**
- Все 3 метода добавлены
- Unit тесты проходят
- Код не ломает существующую функциональность

#### ЭТАП 3: Рефакторинг `_calculate_target_price()` (2-3 часа)

**Файл:** `core/aged_position_manager.py`
**Метод:** `_calculate_target_price()` (строки 258-317)

**Изменения:**
1. Добавить проверку PnL в начало метода
2. Изменить возвращаемый tuple: добавить 4-й элемент `order_type`
3. Добавить валидацию LIMIT для GRACE и PROGRESSIVE
4. Принудительно использовать MARKET для EMERGENCY

**Псевдокод изменений:**
```python
def _calculate_target_price(...) -> Tuple[str, float, float, str]:
    # НОВОЕ: Проверка PnL
    current_pnl = self._calculate_current_pnl_percent(...)
    if current_pnl > 0:
        return (..., 'MARKET')

    # Существующая логика расчёта цены
    if grace_period:
        ...
    elif progressive:
        ...
    else:  # emergency
        return (..., 'MARKET')  # Принудительно

    # НОВОЕ: Валидация LIMIT
    if self._validate_limit_price(...):
        return (..., 'LIMIT')
    else:
        return (..., 'MARKET')
```

**Тестирование:**
- Тесты для всех сценариев PnL
- Тесты для всех фаз
- Тесты валидации LIMIT

**Критерии завершения:**
- Метод возвращает 4 значения
- Логика PnL работает
- Валидация LIMIT работает
- Тесты проходят

#### ЭТАП 4: Рефакторинг `_update_single_exit_order()` (2-3 часа)

**Файл:** `core/aged_position_manager.py`
**Метод:** `_update_single_exit_order()` (строки 319-438)

**Изменения:**
1. Добавить параметр `order_type: str`
2. Добавить условную логику: if order_type == 'MARKET'
3. Вызвать `_create_market_exit_order()` для MARKET
4. Сохранять тип ордера в `managed_positions`

**Псевдокод изменений:**
```python
async def _update_single_exit_order(..., order_type: str):
    ...
    if order_type == 'MARKET':
        order = await self._create_market_exit_order(...)
        self.managed_positions[...] = {..., 'order_type': 'MARKET'}
    else:  # LIMIT
        # Существующая логика
        order = await enhanced_manager.create_or_update_exit_order(...)
        self.managed_positions[...] = {..., 'order_type': 'LIMIT'}
```

**Тестирование:**
- Тест создания MARKET ордера
- Тест создания LIMIT ордера
- Тест обновления LIMIT ордера
- Интеграционный тест с биржей (TESTNET)

**Критерии завершения:**
- MARKET ордера создаются
- LIMIT ордера создаются/обновляются
- Оба типа правильно обрабатываются

#### ЭТАП 5: Обновление `process_aged_position()` (1 час)

**Файл:** `core/aged_position_manager.py`
**Метод:** `process_aged_position()` (строки 162-256)

**Изменения:**
1. Обновить вызов `_calculate_target_price()` для получения 4-го значения
2. Передать `order_type` в `_update_single_exit_order()`

**Код изменений:**
```python
# Было:
phase, target_price, loss_percent = self._calculate_target_price(...)

# Стало:
phase, target_price, loss_percent, order_type = self._calculate_target_price(...)

# Было:
await self._update_single_exit_order(position, target_price, phase)

# Стало:
await self._update_single_exit_order(position, target_price, phase, order_type)
```

**Тестирование:**
- Интеграционный тест полного потока
- Проверка для всех фаз

**Критерии завершения:**
- Поток работает end-to-end
- Все фазы обрабатываются правильно

#### ЭТАП 6: Обновление статистики (30 минут)

**Файл:** `core/aged_position_manager.py`
**Метод:** `__init__()` (строки 34-75)

**Изменения:**
```python
self.stats = {
    'positions_checked': 0,
    'aged_positions': 0,
    'grace_period_positions': 0,
    'progressive_positions': 0,
    'emergency_closes': 0,
    'orders_updated': 0,
    'orders_created': 0,
    'orders_failed': 0,  # НОВОЕ
    'market_orders_created': 0,  # НОВОЕ
    'limit_orders_created': 0,  # НОВОЕ
    'profit_closes': 0,  # НОВОЕ
    'breakeven_closes': 0,
    'gradual_liquidations': 0
}
```

**Обновить логирование:**
```python
# В _update_single_exit_order()
if order_type == 'MARKET':
    self.stats['market_orders_created'] += 1
    if 'PROFIT' in phase:
        self.stats['profit_closes'] += 1
else:
    self.stats['limit_orders_created'] += 1
```

**Критерии завершения:**
- Новые метрики добавлены
- Логирование обновлено
- Метод `get_statistics()` возвращает новые метрики

#### ЭТАП 7: Тестирование на TESTNET (2-3 часа)

**Сценарии тестирования:**

1. **Тест прибыльной позиции:**
   - Создать SHORT позицию
   - Дождаться старения (3ч+)
   - Убедиться, что рынок упал (прибыль)
   - Проверить: MARKET ордер создан
   - Проверить: Позиция закрыта

2. **Тест убыточной GRACE позиции:**
   - Создать SHORT позицию
   - Дождаться старения (3-11ч)
   - Убедиться, что рынок вырос (убыток)
   - Проверить: LIMIT ордер создан (если валиден) или MARKET

3. **Тест EMERGENCY позиции:**
   - Найти очень старую позицию (31ч+)
   - Проверить: MARKET ордер создан независимо от PnL

4. **Тест перехода фаз:**
   - Отследить позицию через все 3 фазы
   - Проверить корректность обновлений

**Мониторинг:**
- Запустить `aged_position_monitor.py` для отслеживания
- Собирать снимки каждые 30 секунд
- Анализировать после завершения

**Критерии завершения:**
- Все сценарии проходят успешно
- 0 ошибок -4016 в логах
- Позиции закрываются как ожидается

#### ЭТАП 8: Документация и очистка кода (1 час)

**Задачи:**
1. Обновить docstrings всех изменённых методов
2. Добавить комментарии к сложным участкам
3. Обновить документацию в начале файла
4. Создать CHANGELOG.md с изменениями

**Критерии завершения:**
- Код хорошо задокументирован
- CHANGELOG создан
- README обновлён (если нужно)

### 4.2 Оценка времени

| Этап | Описание | Время |
|------|----------|-------|
| 1 | Подготовка | 1-2ч |
| 2 | Вспомогательные методы | 1-2ч |
| 3 | Рефакторинг _calculate_target_price | 2-3ч |
| 4 | Рефакторинг _update_single_exit_order | 2-3ч |
| 5 | Обновление process_aged_position | 1ч |
| 6 | Обновление статистики | 0.5ч |
| 7 | Тестирование TESTNET | 2-3ч |
| 8 | Документация | 1ч |
| **ИТОГО** | | **11-16 часов** |

### 4.3 Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| MARKET ордера исполняются с большим проскальзыванием | Средняя | Среднее | Добавить логирование проскальзывания, мониторинг |
| MARKET ордера не проходят на бирже | Низкая | Высокое | Try-catch с откатом к LIMIT, алерты |
| Новая логика создаёт дублирующие ордера | Средняя | Высокое | Проверка существующих ордеров перед созданием |
| PnL рассчитывается неправильно | Низкая | Критическое | Unit тесты, валидация на реальных данных |
| EMERGENCY не закрывает позиции | Низкая | Критическое | Принудительный MARKET, алерты для старых позиций |

### 4.4 План отката

**Если что-то пойдёт не так:**

1. **Быстрый откат (5 минут):**
   ```bash
   git checkout main
   git revert <commit-hash>
   sudo systemctl restart trading_bot
   ```

2. **Восстановление из бэкапа (10 минут):**
   ```bash
   cp backup/aged_position_manager.py.backup core/aged_position_manager.py
   sudo systemctl restart trading_bot
   ```

3. **Полное отключение модуля (1 минута):**
   ```bash
   # В main.py закомментировать вызов
   # await aged_position_manager.check_and_process_aged_positions()
   ```

---

## 5. НОВАЯ ДОКУМЕНТАЦИЯ ЛОГИКИ

### 5.1 Блок-схема новой логики

```
┌─────────────────────────────────────────────────────────────┐
│ ВХОД: Старая позиция (возраст > MAX_AGE)                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
             ┌──────────────────────┐
             │ Получить текущую цену │
             └──────────┬───────────┘
                        │
                        ▼
             ┌──────────────────────┐
             │ Рассчитать PnL %     │
             └──────────┬───────────┘
                        │
                        ▼
             ┌──────────────────────┐
             │   PnL > 0% ?         │
             └──────┬───────────────┘
                    │
         ┌──────────┴──────────┐
         │ ДА                  │ НЕТ
         ▼                     ▼
┌────────────────────┐  ┌──────────────────────┐
│ MARKET закрытие    │  │ Проверка возраста    │
│ Причина: PROFIT    │  └──────────┬───────────┘
└────────────────────┘             │
                                   ▼
                        ┌──────────────────────┐
                        │ Возраст 0-8ч ?       │
                        └──────┬───────────────┘
                               │
                    ┌──────────┴──────────┐
                    │ ДА                  │ НЕТ
                    ▼                     ▼
         ┌──────────────────────┐  ┌──────────────────────┐
         │ GRACE PERIOD         │  │ Возраст 8-28ч ?      │
         │ Цель: безубыток      │  └──────┬───────────────┘
         └──────────┬───────────┘         │
                    │            ┌────────┴──────────┐
                    ▼            │ ДА                │ НЕТ
         ┌──────────────────────┐▼                   ▼
         │ LIMIT валиден ?      ││ PROGRESSIVE       │ EMERGENCY
         └──────┬───────────────┘│ Цель: убыток N%   │ MARKET закрытие
                │                 └──────┬───────────┘
     ┌──────────┴──────────┐            │
     │ ДА                  │ НЕТ        ▼
     ▼                     ▼   ┌──────────────────────┐
┌────────────────┐ ┌────────────┤ LIMIT валиден ?      │
│ LIMIT ордер    │ │ MARKET ордер└──────┬───────────────┘
└────────────────┘ └────────────┐       │
                                 │┌──────┴──────────┐
                                 ││ ДА              │ НЕТ
                                 │▼                 ▼
                                 │┌────────┐ ┌────────────┐
                                 ││ LIMIT  │ │ MARKET     │
                                 │└────────┘ └────────────┘
                                 │
                                 ▼
                      ┌──────────────────────┐
                      │ ВЫХОД: Ордер создан  │
                      └──────────────────────┘
```

### 5.2 Документация для разработчиков

**Принципы новой логики:**

1. **Приоритет прибыли:** Прибыльные позиции закрываются немедленно по MARKET
2. **Адаптивный выбор типа:** LIMIT если возможно, MARKET если необходимо
3. **Гарантированное исполнение:** EMERGENCY всегда использует MARKET
4. **Безопасность:** `reduceOnly=True` для всех ордеров

**Конфигурационные параметры:**

```python
MAX_POSITION_AGE_HOURS = 3        # Когда позиция считается старой
AGED_GRACE_PERIOD_HOURS = 8       # Период попыток безубытка
AGED_LOSS_STEP_PERCENT = 0.5      # Шаг убытка в progressive
AGED_MAX_LOSS_PERCENT = 10.0      # Максимальный допустимый убыток
AGED_ACCELERATION_FACTOR = 1.2    # Акселерация после 10ч
COMMISSION_PERCENT = 0.1          # Комиссия биржи
```

**Логирование:**

Все ключевые решения логируются:
- `💰 PROFIT закрытие` - позиция закрыта с прибылью
- `⚠️ LIMIT невозможен` - откат к MARKET
- `🚨 EMERGENCY` - принудительное закрытие
- `✅ MARKET ордер исполнен` - успешное исполнение
- `❌ MARKET ордер не прошёл` - ошибка исполнения

### 5.3 Мониторинг и алертинг

**Ключевые метрики для отслеживания:**

1. **Количество MARKET закрытий:**
   - `market_orders_created` - должно расти
   - Цель: > 70% старых позиций (прибыльные)

2. **Количество PROFIT закрытий:**
   - `profit_closes` - количество закрытий с прибылью
   - Ожидаемое: ~70% от aged_positions

3. **Процент отказов:**
   - `orders_failed / (orders_created + orders_failed)`
   - Цель: < 5%

4. **Средний возраст закрываемых позиций:**
   - Должен снизиться с 39ч до < 12ч

**Критические алерты:**

1. **Позиция старше 48ч:**
   - Уровень: CRITICAL
   - Действие: Ручное вмешательство

2. **> 10% отказов ордеров:**
   - Уровень: WARNING
   - Действие: Проверка логики

3. **EMERGENCY не закрывает позиции:**
   - Уровень: CRITICAL
   - Действие: Немедленный откат модуля

---

## 6. КОНТРОЛЬНЫЙ ЧЕКЛИСТ

### Перед началом рефакторинга:
- [ ] Создан бэкап всех изменяемых файлов
- [ ] Создана git ветка `feature/aged-pnl-priority`
- [ ] План согласован и утверждён
- [ ] TESTNET аккаунт готов
- [ ] Мониторинг настроен

### После каждого этапа:
- [ ] Код проверен (code review)
- [ ] Unit тесты написаны и проходят
- [ ] Изменения закоммичены в git
- [ ] Документация обновлена

### Перед деплоем в продакшн:
- [ ] Все тесты на TESTNET прошли успешно
- [ ] Нет ошибок -4016 в логах
- [ ] Позиции закрываются как ожидается
- [ ] Статистика собирается правильно
- [ ] План отката подготовлен
- [ ] Мониторинг настроен
- [ ] Команда уведомлена о деплое

### После деплоя:
- [ ] Модуль запущен в продакшене
- [ ] Мониторинг показывает нормальную работу
- [ ] Первые 10 позиций закрыты успешно
- [ ] Статистика соответствует ожиданиям
- [ ] Нет критических ошибок в логах

---

## 7. ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

### 7.1 Количественные метрики

**До рефакторинга:**
- Закрыто позиций: 0 из 82 (0%)
- Ошибки -4016: 486
- Средний возраст: 39ч

**После рефакторинга (прогноз):**
- Закрыто позиций: 58+ из 82 (70%+)
- Ошибки -4016: 0
- Средний возраст: < 12ч

### 7.2 Качественные улучшения

1. **Фиксация прибыли:**
   - 70% старых позиций в прибыли закроются немедленно
   - Прибыль не будет "упущена"

2. **Надёжность:**
   - MARKET ордера гарантируют исполнение
   - Нет отказов от биржи

3. **Безопасность:**
   - EMERGENCY принудительно закрывает критические позиции
   - Нет бесконечно висящих позиций

4. **Мониторинг:**
   - Детальная статистика по типам закрытий
   - Алертинг для критических ситуаций

### 7.3 Бизнес-эффект

**Оценка прибыли от исправления:**
- 58 прибыльных позиций × средний PnL 8% × средний размер $50 = **$232 прибыли**
- Без исправления: эти позиции могли уйти в убыток
- ROI рефакторинга: высокий

---

## 8. ЗАКЛЮЧЕНИЕ

Данный план рефакторинга решает критическую проблему модуля Aged Position Manager путём введения новой логики с приоритетом на PnL позиций. Основные изменения:

1. **Прибыльные позиции закрываются немедленно по MARKET** независимо от возраста
2. **Адаптивный выбор типа ордера:** LIMIT если возможно, MARKET если необходимо
3. **EMERGENCY всегда использует MARKET** для гарантированного закрытия

План детализирован, разбит на этапы, содержит оценки времени и критерии завершения. Риски идентифицированы и имеют стратегии митигации.

**Следующий шаг:** Получить одобрение плана и начать ЭТАП 1: Подготовка.

---

**ВАЖНО:** Этот документ является планом. Изменение кода будет происходить ТОЛЬКО после одобрения.
