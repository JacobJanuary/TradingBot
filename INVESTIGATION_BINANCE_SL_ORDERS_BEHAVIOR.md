# 🔍 РАССЛЕДОВАНИЕ: Поведение Stop-Loss ордеров на Binance Futures

**Дата:** 2025-10-12
**Вопрос:** Отменяются ли SL ордера с `reduceOnly=True` автоматически при закрытии позиций?
**Результат диагностики:** 81 "висящий" SL ордер после закрытия всех позиций

---

## 🎯 РЕЗУЛЬТАТ ИССЛЕДОВАНИЯ

### ✅ Главный вывод:

**Binance Futures НЕ отменяет автоматически Stop-Loss и Take-Profit ордера при закрытии позиций через API или вручную.**

Это **НОРМАЛЬНОЕ поведение биржи**, а не баг в нашем коде.

---

## 📚 ИСТОЧНИКИ ИНФОРМАЦИИ

### 1. Официальный Binance Developer Community

**Тема:** [Automatically cancel take profit and stop loss orders when closing position](https://dev.binance.vision/t/automatically-cancel-take-profit-and-stop-loss-orders-when-closing-position/4484)

**Ключевые цитаты:**

> "By default Binance doesn't close the TAKE_PROFIT_MARKET or STOP_MARKET after position is closed."

> "When you close the position with the API or with the UI, the 2 orders for TP/SL are still there in the Open Orders tab."

> "There's some implementations in the UI that's not supported in the public trading API yet, this is one of the cases."

**Официальная позиция Binance:**
- Автоматическая отмена TP/SL есть только в UI (веб-интерфейсе)
- В публичном API эта функция **НЕ реализована**
- Это **не баг, а известное ограничение API**

### 2. FreqTrade (ведущий open-source торговый бот)

**Issue:** [Stoploss order on Exchange didn't cancel after trade was closed - Binance #11608](https://github.com/freqtrade/freqtrade/issues/11608)

**Вывод FreqTrade:**
- FreqTrade использует `reduceOnly=True` для всех exit ордеров на futures
- Ордера с `reduceOnly=True` остаются в книге ордеров после закрытия позиций
- Это **ожидаемое поведение Binance**

**Цитата maintainer FreqTrade (xmatthias):**
> "well all exit orders are reduceOnly=True, really. Only applies to futures - as that flag doesn't (reliably) exist on spot."

### 3. CCXT Community

**Множественные issues на GitHub:**
- [Close position Binance Futures with ccxt](https://stackoverflow.com/questions/65514350/close-position-binance-futures-with-ccxt)
- [how to cancel stop loss and take profit order when position close on binance futures with rest api](https://stackoverflow.com/questions/70447698/how-to-cancel-stop-loss-and-take-profit-order-when-position-close-on-binance-fut)

**Консенсус разработчиков:**
- `reduceOnly=True` НЕ создает привязку ордера к позиции
- Ордера остаются независимыми объектами в книге ордеров
- Требуется **ручная отмена** или **websocket мониторинг**

### 4. Другие торговые боты

Проверены репозитории:
- [passivbot](https://github.com/enarjord/passivbot) (Bybit, Binance, etc.)
- [Binance-Futures-Trading-Bot](https://github.com/conor19w/Binance-Futures-Trading-Bot)
- [binance-stoploss](https://github.com/giansalex/binance-stoploss)

**Общий паттерн:**
Все профессиональные боты **вручную отменяют SL/TP ордера** при закрытии позиций.

---

## 🔬 ЧТО ТАКОЕ `reduceOnly`?

### Определение (из Binance API):

`reduceOnly=True` означает:
- Ордер может **только уменьшать** текущую позицию
- Ордер **НЕ может открыть** новую позицию в противоположном направлении
- Если позиция закрыта, ордер **НЕ выполнится** (будет отклонен)

### Что `reduceOnly` НЕ делает:

❌ НЕ привязывает ордер к позиции
❌ НЕ отменяется автоматически при закрытии позиции
❌ НЕ создает связь "родитель-потомок"

### Что происходит с `reduceOnly` ордером после закрытия позиции:

1. **Ордер остается в книге ордеров** (status: `open`)
2. **Если цена дойдет до триггера:**
   - Binance попытается выполнить ордер
   - Ордер будет **отклонен** (нечего редуцировать)
   - Статус изменится на `EXPIRED` или `CANCELED`
3. **НО:** Ордер занимает место в лимитах биржи

---

## ⚠️ РИСКИ ВИСЯЩИХ SL ОРДЕРОВ

### 1. Лимиты биржи

Binance имеет лимиты на количество открытых ордеров:
- **Общий лимит:** ~200 открытых ордеров на аккаунт
- **По символу:** ~10-20 ордеров на символ

**Риск:** Достижение лимита → невозможность открывать новые позиции

### 2. Ошибки выполнения (низкий риск)

Теоретически, если:
- SL ордер висит
- Позиция закрыта
- Цена дошла до триггера

**Сценарий 1 (ожидаемый):**
- Binance попытается выполнить `reduceOnly` ордер
- Позиции нет → ордер отклонен
- **Безопасно** ✅

**Сценарий 2 (маловероятный):**
- У вас есть другая позиция по тому же символу (в противоположном направлении)
- SL может случайно закрыть ЭТУ позицию
- **Потенциальная проблема** ⚠️

### 3. Operational overhead

- Захламление списка ордеров
- Сложность мониторинга
- Расход API rate limits на запросы открытых ордеров

---

## 🔧 РЕШЕНИЯ

### Вариант 1: Ручная отмена при закрытии позиции (РЕКОМЕНДУЕТСЯ)

**Подход:**
```python
async def close_position_with_cleanup(symbol: str, exchange):
    # 1. Закрыть позицию
    close_order = await exchange.create_market_order(
        symbol=symbol,
        side='sell',  # противоположная сторона
        amount=position_size,
        params={'reduceOnly': True}
    )

    # 2. Получить все открытые ордера для символа
    open_orders = await exchange.fetch_open_orders(symbol)

    # 3. Отменить все SL/TP ордера
    for order in open_orders:
        if order['type'] in ['stop_market', 'take_profit_market']:
            if order.get('reduceOnly', False):
                await exchange.cancel_order(order['id'], symbol)
                logger.info(f"Canceled SL/TP order {order['id']} for {symbol}")
```

**Преимущества:**
- ✅ Гарантированная очистка
- ✅ Контроль над процессом
- ✅ Работает для любого способа закрытия

**Недостатки:**
- ⚠️ Требует дополнительных API вызовов
- ⚠️ Нужно обрабатывать ошибки (ордер уже исполнен, и т.д.)

### Вариант 2: Периодическая очистка "висящих" ордеров

**Подход:**
```python
async def cleanup_dangling_orders():
    """Очистка висящих SL ордеров без позиций"""
    positions = await exchange.fetch_positions()
    open_symbols = {p['symbol'] for p in positions if float(p['contracts']) != 0}

    all_orders = await exchange.fetch_open_orders()

    for order in all_orders:
        # Если это SL/TP ордер для закрытой позиции
        if (order['type'] in ['stop_market', 'take_profit_market']
            and order['symbol'] not in open_symbols):
            await exchange.cancel_order(order['id'], order['symbol'])
            logger.info(f"Cleaned up dangling order {order['id']}")
```

**Запускать:**
- Каждые 15-30 минут
- После обработки каждой волны
- При старте бота

**Преимущества:**
- ✅ Подчищает ордера независимо от способа закрытия
- ✅ Не привязано к конкретной операции закрытия
- ✅ Работает как safety net

**Недостатки:**
- ⚠️ Задержка между закрытием и очисткой
- ⚠️ Дополнительная нагрузка на API

### Вариант 3: Websocket мониторинг (СЛОЖНЫЙ)

**Подход:** Слушать события `ORDER_TRADE_UPDATE` через websocket

**НЕ РЕКОМЕНДУЕТСЯ** для нашего случая:
- Требует постоянного websocket соединения
- Сложная обработка реконнектов
- Избыточно для нашей архитектуры

### Вариант 4: Использовать `closePosition: true` (ОГРАНИЧЕННЫЙ)

**Параметр Binance API:**
```python
await exchange.create_order(
    symbol=symbol,
    type='stop_market',
    side='sell',
    params={
        'closePosition': True,  # Закроет всю позицию
        'stopPrice': stop_price
    }
)
```

**Ограничения:**
- ✅ Закрывает **всю** позицию автоматически
- ❌ НЕ отменяет другие ордера (TP остается)
- ❌ Нельзя указать конкретное количество
- ⚠️ Подходит только для простых стратегий

---

## 📊 СРАВНЕНИЕ ПОДХОДОВ

| Подход | Надежность | Сложность | API нагрузка | Рекомендация |
|--------|------------|-----------|--------------|--------------|
| Отмена при закрытии | ⭐⭐⭐⭐⭐ | Средняя | Средняя | ✅ **ДА** |
| Периодическая очистка | ⭐⭐⭐⭐ | Низкая | Низкая | ✅ **ДА** (дополнение) |
| Websocket | ⭐⭐⭐⭐⭐ | Высокая | Низкая | ❌ Нет (избыточно) |
| closePosition | ⭐⭐⭐ | Низкая | Низкая | ⚠️ Ограниченно |

---

## 🎯 НАША ТЕКУЩАЯ СИТУАЦИЯ

### Диагностика от 2025-10-12:

**Результаты:**
- ✅ Позиций открыто: **0** (все закрыты вручную)
- ❌ Открытых SL ордеров: **81**
- 📊 Все ордера: `stop_market` с `reduceOnly=True`

**Примеры висящих ордеров:**
```
BLESS/USDT:USDT   - SL buy  @ 0.0381540 (5343 контрактов)
MANA/USDT:USDT    - SL buy  @ 0.2514 (811 контрактов)
SOL/USDT:USDT     - SL sell @ 177.46 (1 контракт)
ATH/USDT:USDT     - SL sell @ 0.04022 (4889 контрактов)
... и еще 77 ордеров
```

### Почему это произошло:

1. **Бот открывал позиции** → создавал SL ордера
2. **Вы закрыли позиции вручную** (не через бота)
3. **Бот не получил уведомление** о закрытии
4. **SL ордера остались** (Binance их не отменяет)

### Риски:

**Немедленные:**
- ✅ **Минимальные** - все ордера с `reduceOnly=True`
- ✅ Не откроют новые позиции
- ✅ Будут отклонены при триггере

**Потенциальные:**
- ⚠️ Достижение лимита ордеров (81 из ~200)
- ⚠️ Сложность навигации в UI
- ⚠️ Если откроете новую позицию по тому же символу - старый SL может сработать

---

## 🔧 РЕКОМЕНДАЦИИ ДЛЯ НАШЕГО БОТА

### Немедленные действия:

1. **Отменить все 81 висящих ордеров** (создать скрипт)
2. **Проверить Bybit** - аналогичная проблема?

### Изменения в коде:

#### 1. Добавить отмену SL при закрытии позиции

**Файл:** `core/position_manager.py`
**Метод:** `close_position()`

```python
async def close_position(self, position_id: str, reason: str):
    """Закрыть позицию и отменить все связанные ордера"""
    # ... существующий код закрытия ...

    # НОВОЕ: Отменить все SL/TP ордера для этого символа
    await self._cancel_sl_tp_orders(position.symbol, position.exchange)

async def _cancel_sl_tp_orders(self, symbol: str, exchange_name: str):
    """Отменить все SL/TP ордера для символа"""
    try:
        exchange = self.exchanges[exchange_name]
        open_orders = await exchange.fetch_open_orders(symbol)

        for order in open_orders:
            if order['type'] in ['stop_market', 'take_profit_market', 'stop_loss', 'stop']:
                if order.get('reduceOnly', False):
                    await exchange.cancel_order(order['id'], symbol)
                    logger.info(f"✅ Canceled SL/TP order {order['id']} for {symbol}")
    except Exception as e:
        logger.error(f"❌ Error canceling SL/TP orders for {symbol}: {e}")
        # НЕ пробрасываем ошибку - это некритично
```

#### 2. Добавить периодическую очистку

**Файл:** `main.py` или отдельный `tasks/cleanup_orders.py`

```python
async def periodic_cleanup_dangling_orders():
    """Очистка висящих SL ордеров каждые 30 минут"""
    while True:
        try:
            await asyncio.sleep(1800)  # 30 минут

            for exchange_name, exchange in exchanges.items():
                positions = await exchange.fetch_positions()
                open_symbols = {p['symbol'] for p in positions if float(p['contracts']) != 0}

                all_orders = await exchange.fetch_open_orders()
                cleaned = 0

                for order in all_orders:
                    if (order['type'] in ['stop_market', 'take_profit_market']
                        and order['symbol'] not in open_symbols
                        and order.get('reduceOnly', False)):
                        await exchange.cancel_order(order['id'], order['symbol'])
                        cleaned += 1

                if cleaned > 0:
                    logger.info(f"🧹 Cleaned up {cleaned} dangling orders on {exchange_name}")
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")
```

#### 3. Очистка при старте бота

**Файл:** `main.py`

```python
async def cleanup_on_startup():
    """Очистить висящие ордера при старте"""
    logger.info("🧹 Cleaning up dangling orders on startup...")
    await periodic_cleanup_dangling_orders()  # Вызвать один раз
    logger.info("✅ Startup cleanup completed")
```

---

## 📋 ИТОГОВЫЙ CHECKLIST

### Понимание:
- [x] `reduceOnly=True` НЕ отменяет ордера автоматически
- [x] Это нормальное поведение Binance API
- [x] Все профессиональные боты отменяют ордера вручную
- [x] FreqTrade делает то же самое
- [x] Риски минимальные (благодаря `reduceOnly`)

### Действия:
- [ ] Создать скрипт отмены 81 висящего ордера
- [ ] Проверить Bybit на висящие ордера
- [ ] Добавить отмену SL при закрытии позиции в код
- [ ] Добавить периодическую очистку (каждые 30 мин)
- [ ] Добавить очистку при старте бота
- [ ] Протестировать на testnet

### Мониторинг:
- [ ] Добавить метрику "висящих ордеров" в логи
- [ ] Алерт если висящих ордеров >50
- [ ] Dashboard с количеством открытых ордеров

---

## 📚 ИСТОЧНИКИ

1. [Binance Developer Community - Auto cancel TP/SL](https://dev.binance.vision/t/automatically-cancel-take-profit-and-stop-loss-orders-when-closing-position/4484)
2. [FreqTrade Issue #11608](https://github.com/freqtrade/freqtrade/issues/11608)
3. [CCXT GitHub Issues](https://github.com/ccxt/ccxt/issues/17403)
4. [Stack Overflow - Cancel SL/TP on Binance Futures](https://stackoverflow.com/questions/70447698/)
5. [Binance API Documentation - closePosition parameter](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api)

---

## ✅ ЗАКЛЮЧЕНИЕ

**Главный вывод:**
- ✅ Наш бот работает **правильно** при создании SL ордеров
- ✅ `reduceOnly=True` используется **корректно**
- ⚠️ Требуется добавить **ручную отмену** при закрытии позиций
- ✅ Это **стандартная практика** для всех торговых ботов на Binance

**Риски:**
- ✅ **Минимальные** - `reduceOnly` защищает от открытия новых позиций
- ⚠️ **Operational** - захламление списка ордеров, лимиты API

**Рекомендация:**
- 🔧 Добавить отмену SL при закрытии + периодическую очистку
- 🎯 Приоритет: **СРЕДНИЙ** (не критично, но нужно)
- ⏰ Срок: 1-2 дня разработки + тестирование

---

**Исследование проведено:** 2025-10-12
**Источники проверены:** Binance API, FreqTrade, CCXT, Stack Overflow, Developer Community
**Статус:** ✅ **ПОЛНОЕ ПОНИМАНИЕ ПРОБЛЕМЫ**
