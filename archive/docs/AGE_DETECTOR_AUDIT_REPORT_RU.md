# Модуль Age Detector - Полный отчет аудита

**Дата:** 2025-10-15
**Аудитор:** Claude Code
**Модуль:** `core/aged_position_manager.py`
**Версия:** Текущая (ветка cleanup/fas-signals-model)

---

## Резюме

**КРИТИЧЕСКАЯ ПРОБЛЕМА ПОДТВЕРЖДЕНА:** Модуль Age Detector содержит серьезный баг множественного создания ордеров, из-за которого он создает несколько лимитных ордеров на выход для одной позиции вместо обновления единственного ордера. Анализ production логов показывает **7,165 созданных exit-ордеров** против только **2,227 обновлений**, при этом символы типа `1000NEIROCTOUSDT` получают новый ордер каждые 5-6 минут вместо обновления существующего.

**Статус:** ❌ **НЕ ГОТОВ К ПРОДАКШЕНУ** - Требуется критическое исправление перед безопасной эксплуатацией

**Последствия:**
- Множественные лимитные ордера накапливаются на бирже для одной позиции
- Риск переполнения позиции (множественное исполнение)
- Увеличенная нагрузка на API и риск rate limit
- Потенциальные ошибки расчета баланса/маржи

---

## 1. Идентификация модуля и структура

### 1.1 Найденные файлы

| Файл | Назначение | Строк |
|------|---------|-------|
| `core/aged_position_manager.py` | Основной модуль | 497 |
| `tests/unit/test_aged_position_decimal_fix.py` | Unit-тесты (исправление Decimal) | 105 |
| `tools/diagnostics/check_positions_age.py` | Диагностический инструмент | 142 |
| `config/settings.py` | Конфигурация (строки 56-63) | - |

### 1.2 Точки интеграции

**Главный цикл:** `main.py:484`
```python
if self.aged_position_manager:
    aged_count = await self.aged_position_manager.check_and_process_aged_positions()
```

**Инициализация:** `main.py:259-264`
```python
self.aged_position_manager = AgedPositionManager(
    settings.trading,
    self.position_manager,
    self.exchanges
)
```

**Частота вызова:** Каждую итерацию главного цикла (приблизительно каждые 30-60 секунд на основе другой обработки)

### 1.3 Параметры конфигурации

Из файла `.env` (со значениями по умолчанию из `config/settings.py:56-63`):

| Параметр | По умолчанию | Описание |
|-----------|---------|-------------|
| `MAX_POSITION_AGE_HOURS` | 3 | Время до признания позиции устаревшей |
| `AGED_GRACE_PERIOD_HOURS` | 8 | Льготный период для попыток закрытия в безубыток |
| `AGED_LOSS_STEP_PERCENT` | 0.5 | Увеличение убытка в час (%) |
| `AGED_MAX_LOSS_PERCENT` | 10.0 | Максимально допустимый убыток (%) |
| `AGED_ACCELERATION_FACTOR` | 1.2 | Ускорение убытка после 10ч |
| `COMMISSION_PERCENT` | 0.1 | Торговая комиссия (%) |

---

## 2. Анализ алгоритма

### 2.1 Спецификация vs Реализация

#### ТРЕБУЕМЫЙ АЛГОРИТМ (из спецификации):

```
1. Выявление устаревших позиций (возраст > MAX_POSITION_AGE_HOURS)
2. Стратегия:
   a) Если прибыльная → закрыть немедленно market-ордером
   b) Если убыточная/безубыточная:
      - Разместить лимитный ордер на уровне безубытка
      - Если не исполнился через интервал → ИЗМЕНИТЬ ордер на цену с убытком loss_step_1
      - Если не исполнился → ИЗМЕНИТЬ ордер на цену с убытком loss_step_2
      - Продолжать до исполнения или достижения max_loss
3. Управление ордерами:
   - ОДИН лимитный ордер на позицию
   - ИЗМЕНЯТЬ существующий ордер (amend/cancel+replace)
   - Хранить order_id для отслеживания активного ордера
```

#### ФАКТИЧЕСКАЯ РЕАЛИЗАЦИЯ:

**Определение фазы** (`aged_position_manager.py:205-264`):
- ✅ Grace Period (0-8ч после max age): Безубыток
- ✅ Progressive Liquidation (8-28ч после max age): Инкрементальный убыток
- ✅ Emergency (>28ч после max age): Рыночная цена

**Расчет цены** (`aged_position_manager.py:216-263`):
- ✅ Безубыток = entry_price ± (2 × commission)
- ✅ Прогрессивный = entry_price ± (hours_after_grace × loss_step_percent)
- ✅ Ускорение после 10 часов реализовано корректно
- ✅ Правильная обработка long/short сторон

**Управление ордерами** (`aged_position_manager.py:266-432`):
- ⚠️ Использует `EnhancedExchangeManager` для предотвращения дубликатов
- ❌ **БАГ:** Вызывает `_check_existing_exit_order` БЕЗ параметра `target_price`
- ❌ **БАГ:** Затем вызывает `create_limit_exit_order` с `check_duplicates=True`, вызывая двойную проверку
- ❌ **РЕЗУЛЬТАТ:** Обнаружение дубликатов не срабатывает, создается новый ордер каждый раз

---

## 3. Выявленные критические баги

### БАГ #1: МНОЖЕСТВЕННОЕ СОЗДАНИЕ ОРДЕРОВ (КРИТИЧЕСКИЙ)

**Местоположение:** `aged_position_manager.py:295-358`

**Описание:**
Модуль вызывает `_check_existing_exit_order(symbol, order_side)` на строке 295 **без** передачи параметра `target_price`. Это приводит к сбою проверки дубликатов в `EnhancedExchangeManager`, потому что:

1. Строка 295: `existing = await enhanced_manager._check_existing_exit_order(position.symbol, order_side)`
2. `_check_existing_exit_order` получает `target_price=None`
3. Логика на `exchange_manager_enhanced.py:219-227` никогда не выполняется (сравнение цен пропускается)
4. Метод возвращает существующий ордер
5. НО: Строка 300-304 проверяет `if existing:` → вычисляет разницу в цене
6. Строка 304: `if price_diff_pct > 0.5:` → Всегда true для меняющихся цен
7. Строка 345: `else:` → Считается как "нет существующего ордера"
8. Строка 353: Создается НОВЫЙ ордер с `check_duplicates=True`
9. `create_limit_exit_order` вызывает `_check_existing_exit_order` СНОВА с `target_price`
10. Но к этому времени кэш ордеров может быть устаревшим или ордер был отменен

**Доказательства из production логов:**

```bash
$ grep "📝 Creating initial" logs/trading_bot.log | wc -l
7165  # "Creating initial exit order" залогировано 7,165 раз

$ grep "Exit order already exists" logs/trading_bot.log | wc -l
0     # Предотвращение дубликатов НИКОГДА не срабатывало!
```

**Пример для символа `1000NEIROCTOUSDT`:**
```
2025-10-15 01:35:09 - Creating initial exit order for 1000NEIROCTOUSDT @ 0.1599
2025-10-15 01:40:39 - Creating initial exit order for 1000NEIROCTOUSDT @ 0.1598
2025-10-15 01:46:10 - Creating initial exit order for 1000NEIROCTOUSDT @ 0.1597
2025-10-15 01:51:41 - Creating initial exit order for 1000NEIROCTOUSDT @ 0.1596
[... продолжается каждые 5-6 минут ...]
```

Результат: **30+ ордеров создано для одной позиции** вместо 1 обновляемого ордера.

**Последствия:**
- Множественные активные лимитные ордера на бирже
- Риск множественного исполнения → закрытие больше размера позиции
- Ошибки расчета баланса
- Увеличенное использование API rate limit

**Сложность исправления:** Средняя

---

### БАГ #2: ПУТАНИЦА В ЛОГИКЕ - ДВОЙНАЯ ПРОВЕРКА ДУБЛИКАТОВ

**Местоположение:** `aged_position_manager.py:295 и 353`

**Описание:**
Код выполняет проверку дубликатов на ДВУХ уровнях:
1. Строка 295: Вручную вызывает `_check_existing_exit_order`
2. Строка 353/325: Вызывает `create_limit_exit_order(check_duplicates=True)`

Это создает путаницу и race conditions:
- Если `existing` найден на строке 295, код пытается его обновить
- Но строка 325/353 вызывает `create_limit_exit_order`, который делает СВОЮ проверку дубликатов
- Эта вторая проверка может дать другие результаты (устаревание кэша, тайминг)

**Правильный паттерн:**
Либо:
- A) Позволить `create_limit_exit_order` обрабатывать всю логику дубликатов (убрать проверку на строке 295)
- B) Использовать только проверку на строке 295, вызывать raw CCXT создание ордера (не `create_limit_exit_order`)

**Последствия:** Средние - способствует Багу #1

**Сложность исправления:** Легкая

---

### БАГ #3: RACE CONDITION ПРИ ИНВАЛИДАЦИИ КЭША ОРДЕРОВ

**Местоположение:** `exchange_manager_enhanced.py:159` и `aged_position_manager.py:322`

**Описание:**
При отмене старого ордера:
1. Строка 315-319: Отменить старый ордер через `safe_cancel_with_verification`
2. Строка 322: `await asyncio.sleep(0.2)` - Ждать 200мс
3. Строка 325: Создать новый ордер
4. `create_limit_exit_order` на строке 159 инвалидирует кэш

Но есть временное окно, где:
- Старый ордер отменен
- Кэш инвалидирован операцией отмены
- Новая проверка на строке 108 (`_check_existing_exit_order`) происходит
- Кэш обновляется, но отмененный ордер может все еще отображаться как "open" на бирже
- Обнаружение дубликатов не срабатывает

**Доказательства из логов:**
```
2025-10-14 05:34:24 - Error cancelling order 9114c6d0-...: bybit fetchOrder()
can only access an order if it is in last 500 orders
```

API Bybit не сразу отражает отмены, но код предполагает, что это происходит мгновенно.

**Последствия:** Средние - способствует Багу #1

**Сложность исправления:** Средняя

---

### БАГ #4: НЕПРОТЕСТИРОВАННЫЙ FALLBACK-ПУТЬ

**Местоположение:** `aged_position_manager.py:369-432`

**Описание:**
Fallback-путь (когда импорт `EnhancedExchangeManager` не удается) на строках 369-432 имеет другую логику:
- Строка 373-386: Получает открытые ордера напрямую
- Строка 388-400: Проверяет существующий ордер
- Строка 393-400: Отменяет, если разница в цене > 0.5%
- Строка 402-418: Создает новый ордер

Этот путь:
- ✅ НЕ страдает от проблемы двойной проверки
- ✅ Правильно проверяет `reduceOnly == True`
- ✅ Фильтрует stop loss ордера проверкой `stopOrderType`
- ⚠️ Но может иметь те же проблемы с кэшем

**Последствия:** Низкие - редко выполняется (только если импорт не удается)

**Сложность исправления:** Легкая (выровнять с основным путем после исправления Бага #1)

---

### БАГ #5: НЕТ ПРОВЕРКИ СУЩЕСТВОВАНИЯ ОРДЕРА ПЕРЕД ОБНОВЛЕНИЕМ

**Местоположение:** `aged_position_manager.py:295-319`

**Описание:**
Когда найден `existing` ордер:
1. Код вычисляет разницу в цене
2. Решает обновить, если > 0.5% разницы
3. Пытается отменить ордер

Но НЕ проверяет:
- Находится ли ордер все еще в статусе "NEW"?
- Частично ли исполнен ордер?
- Был ли ордер уже отменен другим процессом?

**Доказательства из логов:**
```
Error cancelling order: bybit fetchOrder() can only access an order
if it is in last 500 orders
```

Это происходит, когда:
- Ордер уже был исполнен/отменен
- Но код все еще пытается его отменить
- Bybit возвращает ошибку, потому что ордер больше не в активном списке

**Последствия:** Низкие - вызывает предупреждающие логи, но восстанавливается созданием нового ордера

**Сложность исправления:** Средняя

---

## 4. Результаты анализа live-логов

### 4.1 Метрики из production логов

**Анализируемый период:** 2025-10-14 05:34:17 до 2025-10-15 04:09:55 (приблизительно 23 часа)

| Метрика | Количество | Примечания |
|--------|-------|-------|
| "Creating initial exit order" | 7,165 | Должно быть ~1 на символ |
| "Updating exit order" | 2,227 | Правильный путь обновления |
| "Exit order created" | 9,392 | Всего создано ордеров |
| "Exit order already exists" | 0 | **Предотвращение дубликатов никогда не срабатывало!** |
| Обработано устаревших позиций | ~14 за цикл | Множество циклов |
| Уникальных символов с устаревшими позициями | ~14 | Оценочно |

### 4.2 Доказательства множественного создания ордеров

**Символ: 1000NEIROCTOUSDT** (из логов):
- 30+ создания "initial order" за 2.5 часа
- Ордера создаются каждые ~5.5 минут
- Каждый с немного другой ценой (движение рынка)
- Разные order ID каждый раз

**Ожидаемое поведение:**
- 1 ордер создан изначально
- Тот же ордер изменяется/отменяется+заменяется при изменении цены

**Фактическое поведение:**
- Новый ордер создается при каждой проверке
- Предыдущие ордера остаются на бирже (или отменяются отдельно)

### 4.3 Паттерны ошибок

**Часто встречающиеся ошибки:**

1. **"This trading pair is only available to the China region"** (HNTUSDT)
   - Не баг, географическое ограничение
   - Должно обрабатываться корректно

2. **"Buy order price cannot be higher than 0USDT"** (XDCUSDT)
   - Проблема расчета цены для активов с очень низкой ценой
   - Нужна лучшая обработка точности

3. **"fetchOrder() can only access an order if it is in last 500 orders"**
   - Попытка проверить/отменить уже исполненные ордера
   - Bybit-специфичное ограничение API

---

## 5. Анализ первопричин

### Почему возникает Баг #1

**Основная причина:**
Несоответствие между ожиданиями aged_position_manager и дизайном API EnhancedExchangeManager.

**Цепочка сбоев:**

1. **Предположение дизайна:** `_check_existing_exit_order(symbol, side)` возвращает существующий ордер
2. **Реальность:** Он возвращает ордер, но БЕЗ знания о том, нужно ли обновление цены
3. **aged_position_manager:** Сам вычисляет разницу в цене (строка 302)
4. **Проблема:** Эта логика ДУБЛИРУЕТСЯ из внутренней логики `_check_existing_exit_order`
5. **Результат:** Когда `existing` найден, код входит в путь "обновления"
6. **Но:** Он все равно вызывает `create_limit_exit_order`, который имеет СВОЮ проверку дубликатов
7. **Финальная проблема:** Вторая проверка может не сработать (кэш, тайминг) → создает дубликат

**Вторичная причина:**
Особенности API Bybit:
- Отмененные ордера не исчезают мгновенно из `fetch_open_orders`
- Иногда требуется 1-2 секунды для отражения
- Тем временем проверка дубликатов видит "старый ордер все еще открыт"

**Третичная причина:**
Тайминг инвалидации кэша:
- TTL кэша 5 секунд
- Но главный цикл работает быстрее
- Старые закэшированные данные могут использоваться для проверки дубликатов

---

## 6. Сравнение со спецификацией

| Требование | Статус | Примечания к реализации |
|-------------|--------|----------------------|
| Обнаружение устаревших позиций | ✅ Корректно | Строки 96-112, правильная обработка часовых поясов |
| 3-фазная стратегия | ✅ Корректно | Фазы Grace/Progressive/Emergency |
| Расчет безубытка | ✅ Корректно | Включает двойную комиссию |
| Прогрессивные шаги убытка | ✅ Корректно | С фактором ускорения |
| **ОДИН ордер на позицию** | ❌ **НЕ РАБОТАЕТ** | **Создает множество ордеров** |
| **ИЗМЕНЯТЬ существующий ордер** | ❌ **НЕ РАБОТАЕТ** | **Создает новый вместо изменения** |
| Хранить order_id | ⚠️ Частично | Строки 334-338, 362-366 хранят, но не используют для дедупликации |
| Прибыль → market close | ⚠️ Не реализовано | Нет логики для немедленного market close если прибыльно |

---

## 7. План исправлений

### 7.1 Немедленные действия (КРИТИЧНО)

#### Исправление #1: Упростить логику управления ордерами

**Приоритет:** КРИТИЧЕСКИЙ
**Сложность:** Средняя
**Оценочное время:** 2-3 часа

**Требуемые изменения:**

**Файл:** `core/aged_position_manager.py:266-370`

**Вариант A: Использовать EnhancedExchangeManager правильно**

```python
async def _update_single_exit_order(self, position, target_price: float, phase: str):
    """ИСПРАВЛЕНО: Позволить EnhancedExchangeManager обрабатывать всю логику дубликатов"""
    try:
        position_id = f"{position.symbol}_{position.exchange}"
        exchange = self.exchanges.get(position.exchange)
        if not exchange:
            logger.error(f"Exchange {position.exchange} not available")
            return

        order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

        # ИЗМЕНЕНО: Использовать enhanced manager правильно
        from core.exchange_manager_enhanced import EnhancedExchangeManager
        enhanced_manager = EnhancedExchangeManager(exchange.exchange)

        # ВАРИАНТ 1: Проверить существующий и решить, обновлять ли
        existing = await enhanced_manager._check_existing_exit_order(
            position.symbol, order_side, target_price  # ИСПРАВЛЕНИЕ: Передать target_price!
        )

        if existing:
            existing_price = Decimal(str(existing.get('price', 0)))
            price_diff_pct = abs(target_price - existing_price) / existing_price * 100

            if price_diff_pct > 0.5:
                # Нужно обновление
                logger.info(
                    f"📊 Обновление exit ордера для {position.symbol}:\n"
                    f"  Старая цена: ${existing_price:.4f}\n"
                    f"  Новая цена: ${target_price:.4f}\n"
                    f"  Разница: {price_diff_pct:.1f}%"
                )

                # Отменить старый ордер
                await enhanced_manager.safe_cancel_with_verification(
                    existing['id'], position.symbol
                )
                await asyncio.sleep(0.5)  # Увеличенное время ожидания

                # Создать новый ордер БЕЗ проверки дубликатов (мы уже проверили!)
                order = await enhanced_manager.create_limit_exit_order(
                    symbol=position.symbol,
                    side=order_side,
                    amount=abs(float(position.quantity)),
                    price=target_price,
                    check_duplicates=False  # ИСПРАВЛЕНИЕ: Не проверять дважды!
                )

                if order:
                    self.managed_positions[position_id] = {
                        'last_update': datetime.now(),
                        'order_id': order['id'],
                        'phase': phase
                    }
                    self.stats['orders_updated'] += 1
            else:
                # Цена приемлема, оставить существующий ордер
                logger.debug(
                    f"Цена exit ордера приемлема для {position.symbol}, "
                    f"оставляем на ${existing_price:.4f}"
                )
                # Обновить отслеживание даже если не меняем ордер
                self.managed_positions[position_id] = {
                    'last_update': datetime.now(),
                    'order_id': existing['id'],
                    'phase': phase
                }
        else:
            # Нет существующего ордера, создать новый
            logger.info(
                f"📝 Создание начального exit ордера для {position.symbol}:\n"
                f"  Цена: ${target_price:.4f}\n"
                f"  Фаза: {phase}"
            )

            order = await enhanced_manager.create_limit_exit_order(
                symbol=position.symbol,
                side=order_side,
                amount=abs(float(position.quantity)),
                price=target_price,
                check_duplicates=True  # Проверка здесь OK (первый раз)
            )

            if order:
                self.managed_positions[position_id] = {
                    'last_update': datetime.now(),
                    'order_id': order['id'],
                    'phase': phase
                }
                self.stats['orders_created'] += 1

    except Exception as e:
        logger.error(f"Ошибка обновления exit ордера: {e}", exc_info=True)
```

**Ключевые изменения:**
1. Строка 295: **Передать `target_price`** в `_check_existing_exit_order`
2. Строка 330/358: **Установить `check_duplicates=False`** при создании после ручной проверки
3. Строка 322: **Увеличить sleep** с 0.2с до 0.5с для распространения отмены ордера
4. Строки 340-350: **Обновить отслеживание** даже когда не меняем ордер

---

**Вариант B: Проще - Позволить create_limit_exit_order обрабатывать все**

```python
async def _update_single_exit_order(self, position, target_price: float, phase: str):
    """УПРОЩЕНО: Позволить EnhancedExchangeManager обрабатывать ВСЮ логику"""
    try:
        position_id = f"{position.symbol}_{position.exchange}"
        exchange = self.exchanges.get(position.exchange)
        if not exchange:
            logger.error(f"Exchange {position.exchange} not available")
            return

        order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

        from core.exchange_manager_enhanced import EnhancedExchangeManager
        enhanced_manager = EnhancedExchangeManager(exchange.exchange)

        # УПРОЩЕНО: Просто вызвать create_limit_exit_order, он обрабатывает дубликаты!
        order = await enhanced_manager.create_or_update_exit_order(
            symbol=position.symbol,
            side=order_side,
            amount=abs(float(position.quantity)),
            price=target_price,
            min_price_diff_pct=0.5  # Обновить если цена изменилась > 0.5%
        )

        if order:
            self.managed_positions[position_id] = {
                'last_update': datetime.now(),
                'order_id': order['id'],
                'phase': phase
            }

            # Проверить, было ли это обновление или создание
            if order.get('_was_updated'):
                self.stats['orders_updated'] += 1
            else:
                self.stats['orders_created'] += 1

    except Exception as e:
        logger.error(f"Ошибка управления exit ордером: {e}", exc_info=True)
```

**Требует добавления в `EnhancedExchangeManager`:**

```python
async def create_or_update_exit_order(
    self,
    symbol: str,
    side: str,
    amount: float,
    price: float,
    min_price_diff_pct: float = 0.5
) -> Optional[Dict]:
    """
    Унифицированный метод: создать exit ордер или обновить если существует

    Обрабатывает:
    - Проверку существующего ордера
    - Решение о необходимости обновления цены
    - Отмену старого + создание нового при необходимости
    - Всю логику предотвращения дубликатов

    Возвращает:
        Dict ордера с флагом '_was_updated'
    """
    existing = await self._check_existing_exit_order(symbol, side, price)

    if existing:
        existing_price = float(existing.get('price', 0))
        price_diff_pct = abs(price - existing_price) / existing_price * 100

        if price_diff_pct > min_price_diff_pct:
            # Нужно обновить
            logger.info(f"Обновление exit ордера {existing['id']} для {symbol}: "
                       f"${existing_price:.4f} → ${price:.4f}")

            # Отменить старый
            await self.safe_cancel_with_verification(existing['id'], symbol)
            await asyncio.sleep(0.5)

            # Создать новый
            order = await self.create_limit_exit_order(
                symbol, side, amount, price, check_duplicates=False
            )
            if order:
                order['_was_updated'] = True
            return order
        else:
            # Цена OK, вернуть существующий
            logger.debug(f"Цена exit ордера OK для {symbol}, оставляем существующий")
            existing['_was_updated'] = False
            return existing
    else:
        # Нет существующего, создать новый
        order = await self.create_limit_exit_order(
            symbol, side, amount, price, check_duplicates=True
        )
        if order:
            order['_was_updated'] = False
        return order
```

**Рекомендация:** Использовать **Вариант B** - он чище и централизует всю логику в одном месте.

---

#### Исправление #2: Улучшить тайминг инвалидации кэша

**Файл:** `core/exchange_manager_enhanced.py:159, 277-298`

**Проблема:** Кэш может показывать старые отмененные ордера как все еще открытые

**Решение:**

```python
async def safe_cancel_with_verification(
    self,
    order_id: str,
    symbol: str
) -> Dict:
    """ИСПРАВЛЕНО: Добавить инвалидацию кэша после успешной отмены"""
    operation_key = f"{symbol}:{order_id}"

    if operation_key in self._pending_operations:
        logger.warning(f"⚠️ Отмена уже в процессе для {order_id}")
        return {'status': 'already_pending', 'order': None}

    self._pending_operations.add(operation_key)

    try:
        # Попытка отмены
        result = await self.exchange.cancel_order(order_id, symbol)
        logger.info(f"✅ Ордер {order_id[:12]}... успешно отменен")

        # ДОБАВЛЕНО: Инвалидировать кэш НЕМЕДЛЕННО после отмены
        await self._invalidate_order_cache(symbol)

        # ДОБАВЛЕНО: Ждать дольше для обработки биржей
        await asyncio.sleep(0.5)  # Увеличено с типичных 0.1-0.2с

        # Проверить отмену
        try:
            order = await self.exchange.fetch_order(order_id, symbol)
            if order['status'] not in ['canceled', 'cancelled']:
                logger.warning(f"Статус ордера {order_id}: {order['status']}")
        except Exception as e:
            # Ордер не найден = успешно отменен
            logger.debug(f"Ордер {order_id} больше не найден (ожидаемо после отмены)")

        self.stats['orders_cancelled'] += 1
        return {'status': 'cancelled', 'order': result}

    except ccxt.OrderNotFound:
        logger.info(f"Ордер {order_id} уже исполнен/отменен")
        # ДОБАВЛЕНО: Все равно инвалидировать кэш
        await self._invalidate_order_cache(symbol)
        return {'status': 'not_found', 'order': None}

    except Exception as e:
        logger.error(f"Ошибка отмены ордера {order_id}: {e}")
        # ДОБАВЛЕНО: Инвалидировать кэш и при ошибке (может быть частичное состояние)
        await self._invalidate_order_cache(symbol)
        raise

    finally:
        self._pending_operations.discard(operation_key)
```

---

#### Исправление #3: Лучшая обработка ошибок для географических ограничений

**Файл:** `core/aged_position_manager.py:202-203`

**Добавить перед обработкой:**

```python
async def process_aged_position(self, position):
    """Обработать одну устаревшую позицию на основе возраста"""
    try:
        # ... существующий код ...

        # Обновить или создать лимитный exit ордер
        await self._update_single_exit_order(position, target_price, phase)

    except ccxt.ExchangeError as e:
        error_msg = str(e)
        if '170209' in error_msg or 'China region' in error_msg:
            # Географическое ограничение - не повторять
            logger.error(
                f"⛔ {position.symbol} недоступен в этом регионе - "
                f"пропускаем управление устаревшей позицией"
            )
            # Пометить позицию для пропуска в будущих проверках
            self.managed_positions[f"{position.symbol}_{position.exchange}"] = {
                'last_update': datetime.now(),
                'order_id': None,
                'phase': 'SKIPPED_GEO_RESTRICTED',
                'skip_until': datetime.now() + timedelta(days=1)  # Повторить через 24ч
            }
        else:
            raise  # Перебросить другие ошибки биржи

    except Exception as e:
        logger.error(f"Ошибка обработки устаревшей позиции {position.symbol}: {e}", exc_info=True)
```

---

### 7.2 Краткосрочные улучшения (ВЫСОКИЙ приоритет)

#### Улучшение #1: Добавить логику взятия прибыли

**Сейчас отсутствует:** Строки 175-178 вычисляют целевую цену, но не проверяют, прибыльна ли позиция для немедленного market close.

**Добавить в `process_aged_position` перед строкой 175:**

```python
# Проверить, прибыльна ли позиция - закрыть немедленно market ордером
if position.side in ['long', 'buy']:
    is_profitable = current_price > position.entry_price * (1 + 0.002)  # > 0.2% прибыли
else:
    is_profitable = current_price < position.entry_price * (0.998)

if is_profitable:
    logger.info(
        f"💰 Устаревшая позиция {position.symbol} прибыльна - "
        f"закрываем market ордером"
    )
    # Закрыть market ордером
    await self._close_with_market_order(position, current_price)
    self.stats['breakeven_closes'] += 1  # Фактически прибыльное закрытие
    return  # Готово с этой позицией
```

**Добавить новый метод:**

```python
async def _close_with_market_order(self, position, current_price: float):
    """Закрыть позицию немедленно market ордером"""
    exchange = self.exchanges.get(position.exchange)
    if not exchange:
        return

    order_side = 'sell' if position.side in ['long', 'buy'] else 'buy'

    try:
        order = await exchange.create_order(
            symbol=position.symbol,
            type='market',
            side=order_side,
            amount=abs(float(position.quantity)),
            params={'reduceOnly': True}
        )
        logger.info(
            f"✅ Market close ордер размещен для {position.symbol}: "
            f"{order['id']}"
        )
    except Exception as e:
        logger.error(f"Ошибка размещения market close ордера: {e}", exc_info=True)
        raise
```

---

#### Улучшение #2: Добавить валидацию состояния ордера

**Добавить перед попыткой отмены:**

```python
async def _validate_order_state(self, order_id: str, symbol: str) -> Optional[str]:
    """Проверить статус ордера перед попыткой изменения"""
    try:
        order = await self.exchange.fetch_order(order_id, symbol)
        status = order['status']

        if status in ['closed', 'canceled', 'cancelled']:
            logger.info(f"Ордер {order_id} уже {status}")
            return None  # Не пытаться отменять

        if status == 'partially_filled':
            logger.warning(
                f"Ордер {order_id} частично исполнен: "
                f"{order['filled']}/{order['amount']}"
            )
            # Решение: отменить все равно для обновления остатка?
            return status

        return status  # 'open', 'new', и т.д.

    except ccxt.OrderNotFound:
        logger.info(f"Ордер {order_id} не найден")
        return None
    except Exception as e:
        logger.error(f"Ошибка валидации состояния ордера: {e}")
        return 'unknown'
```

Использовать перед отменой:

```python
# Перед строкой 315
state = await enhanced_manager._validate_order_state(
    existing['id'], position.symbol
)
if state and state not in ['closed', 'canceled', 'cancelled']:
    # Безопасно отменять
    await enhanced_manager.safe_cancel_with_verification(...)
else:
    # Ордер исчез, просто создать новый
    logger.info("Старый ордер больше не активен, создаем новый")
```

---

#### Улучшение #3: Мониторинг и алертинг

**Добавить в отслеживание статистики:**

```python
# В __init__, добавить в self.stats:
'duplicate_orders_prevented': 0,
'orders_actually_duplicated': 0,  # Критическая метрика!
'phantom_orders_found': 0,

# Добавить метод для обнаружения дубликатов в managed_positions:
async def _detect_duplicate_orders(self) -> List[Dict]:
    """
    Активно проверять дублирующиеся ордера на бирже
    Должно вызываться периодически (каждые 5 минут)
    """
    duplicates = []

    for exchange_name, exchange in self.exchanges.items():
        try:
            # Получить все открытые ордера
            for symbol in self.active_symbols:
                orders = await exchange.fetch_open_orders(symbol)

                # Фильтровать reduceOnly limit ордера (exit ордера)
                exit_orders = [
                    o for o in orders
                    if o.get('reduceOnly') == True
                    and o.get('type') == 'limit'
                    and not self._is_stop_loss_order(o)
                ]

                if len(exit_orders) > 1:
                    # КРИТИЧНО: Найдено множество exit ордеров!
                    duplicates.append({
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'count': len(exit_orders),
                        'orders': exit_orders
                    })
                    self.stats['orders_actually_duplicated'] += len(exit_orders) - 1

                    logger.error(
                        f"🚨 ОБНАРУЖЕНЫ ДУБЛИРУЮЩИЕСЯ EXIT ОРДЕРА для {symbol}!\n"
                        f"   Найдено {len(exit_orders)} exit ордеров:\n" +
                        "\n".join([
                            f"   - {o['id']}: {o['side']} @ ${o['price']}"
                            for o in exit_orders
                        ])
                    )

        except Exception as e:
            logger.error(f"Ошибка проверки дубликатов на {exchange_name}: {e}")

    return duplicates
```

---

### 7.3 Средний/Низкий приоритет

1. **Unit-тесты** - Создать комплексные тесты для логики управления ордерами
2. **Интеграционные тесты** - Тестировать с mock ответами биржи
3. **Производительность** - Кэшировать рыночные цены для уменьшения API вызовов
4. **Логирование** - Добавить структурированное логирование для более легкого анализа

---

## 8. Рекомендации по тестированию

### До исправления:

1. ✅ **Анализ завершен** - Логи подтверждают существование бага
2. ✅ **Создан скрипт мониторинга** - `monitor_age_detector.py`

### После исправления:

1. **Unit-тесты:**
   ```bash
   pytest tests/unit/test_aged_position_manager.py -v
   ```
   - Тест создания ордера
   - Тест логики обновления ордера
   - Тест предотвращения дубликатов
   - Тест расчета цены

2. **Интеграционный тест с тестовой биржей:**
   ```bash
   # В режиме testnet
   python -c "
   import asyncio
   from core.aged_position_manager import AgedPositionManager
   # ... запустить check_and_process_aged_positions()
   # Проверить только 1 ордер на символ на бирже
   "
   ```

3. **Live-мониторинг (15 минут):**
   ```bash
   # Запустить бота
   python main.py &

   # Мониторить с диагностическим скриптом
   python monitor_age_detector.py logs/trading_bot.log
   ```

   **Критерии успеха:**
   - "Exit order already exists" логируется, когда ордер не требует обновления
   - "Updating exit order" когда цена меняется > 0.5%
   - НЕТ множественных "Creating initial exit order" для того же символа
   - Массив `proliferation_issues` пуст в отчете

4. **Расширенный мониторинг (2-4 часа):**
   - Мониторить множество позиций, становящихся устаревшими
   - Проверить фазы прогрессивной ликвидации
   - Проверить использование памяти (dict отслеживания ордеров)
   - Проверить отсутствие накопления ордеров на бирже

5. **Граничные случаи:**
   - Позиция исполнена во время обновления ордера
   - Ошибки API биржи во время отмены
   - Множество устаревших позиций обновляются одновременно
   - Цена движется очень быстро (>1% за проверку)

---

## 9. Использование скрипта мониторинга

Создан диагностический скрипт: `monitor_age_detector.py`

### Использование:

```bash
# Запустить торгового бота в одном терминале
python main.py

# В другом терминале запустить монитор
python monitor_age_detector.py logs/trading_bot.log
```

Скрипт будет:
- Мониторить логи 15 минут
- Отслеживать события создания/обновления ордеров
- Обнаруживать множественное создание ордеров на символ
- Генерировать JSON отчет с полным таймлайном

### Ожидаемый вывод (после исправления):

```
AGE DETECTOR MODULE - DIAGNOSTIC REPORT
================================================================================
Продолжительность мониторинга: 15.0 минут
...

SUMMARY METRICS
--------------------------------------------------------------------------------
Выявлено устаревших позиций: 42
Отслежено уникальных символов: 14
Логов 'Creating initial exit order': 14  # По одному на символ!
Логов 'Updating exit order': 28          # Обновления при изменении цен
Всего событий 'Exit order created': 42   # = 14 начальных + 28 обновлений
Предотвращено дубликатов: 15             # Когда цена недостаточно изменилась

ORDER PROLIFERATION ANALYSIS
--------------------------------------------------------------------------------
✅ Множественное создание ордеров не обнаружено

VERDICT
================================================================================
✅ PASS: Явных проблем не обнаружено
   Предотвращение дубликатов работает корректно
   Ордера обновляются вместо пересоздания
```

---

## 10. Заключение

### Текущее состояние: ❌ НЕ ГОТОВ К ПРОДАКШЕНУ

**Критические проблемы:**
1. **Баг множественного создания ордеров** - Создает множество ордеров вместо обновления одного
2. **Предотвращение дубликатов сломано** - Никогда не срабатывает в продакшене

**Подтверждено:**
- Анализом кода (выявлены логические ошибки)
- Анализом production логов (7,165 создания ордеров vs ожидаемых ~14)
- Ноль событий предотвращения дубликатов в логах

**Уровень риска:** 🔴 **ВЫСОКИЙ**
- Финансовое влияние: Возможно множественное исполнение
- Операционное влияние: Увеличенное использование API, потенциальные rate limits
- Влияние на стабильность: Ошибки расчета баланса

### После исправлений: ✅ ПОТЕНЦИАЛЬНО ГОТОВ

**С реализацией:**
1. Исправление #1: Упрощенная логика управления ордерами
2. Исправление #2: Улучшенная инвалидация кэша
3. Исправление #3: Обработка географических ограничений
4. Улучшение #1: Логика взятия прибыли
5. Валидация скриптом мониторинга

**Оценка усилий:**
- Критические исправления: 4-6 часов разработки
- Тестирование: 2-3 часа
- Мониторинг: 15 мин - 4 часа
- Всего: 1 рабочий день

**Рекомендация:**
1. Реализовать Вариант B (упрощенная логика) из Исправления #1
2. Добавить мониторинг обнаружения дубликатов (Улучшение #3)
3. Протестировать в testnet минимум 4 часа
4. Развернуть в production с мониторингом 24ч
5. Держать скрипт мониторинга запущенным первую неделю

---

## Приложение A: Измененные файлы

### Критические исправления:

| Файл | Измененных строк | Тип |
|------|--------------|------|
| `core/aged_position_manager.py` | 266-370 | MAJOR REFACTOR |
| `core/exchange_manager_enhanced.py` | Добавить новый метод | НОВЫЙ МЕТОД |
| `core/exchange_manager_enhanced.py` | 277-320 | МОДИФИКАЦИЯ |

### Тестирование:

| Файл | Назначение |
|------|---------|
| `monitor_age_detector.py` | НОВЫЙ - Диагностический мониторинг |
| `tests/unit/test_aged_position_manager_fixes.py` | НОВЫЙ - Unit-тесты для исправлений |

---

## Приложение B: Рекомендации по конфигурации

Для более безопасного начального развертывания после исправления:

```env
# Консервативные настройки для первой недели
MAX_POSITION_AGE_HOURS=6          # Больше времени до устаревания
AGED_GRACE_PERIOD_HOURS=12        # Более длительный период попыток безубытка
AGED_LOSS_STEP_PERCENT=0.3        # Более медленная прогрессия убытка
AGED_MAX_LOSS_PERCENT=5.0         # Более низкий max loss изначально
AGED_CHECK_INTERVAL_MINUTES=60    # Менее частые проверки
```

После валидации:

```env
# Обычные операционные настройки
MAX_POSITION_AGE_HOURS=3
AGED_GRACE_PERIOD_HOURS=8
AGED_LOSS_STEP_PERCENT=0.5
AGED_MAX_LOSS_PERCENT=10.0
AGED_CHECK_INTERVAL_MINUTES=60
```

---

**Конец отчета**

Подготовлено: Claude Code Audit System
Дата: 2025-10-15
Уровень уверенности: ВЫСОКИЙ (на основе анализа кода + верификации логов)
